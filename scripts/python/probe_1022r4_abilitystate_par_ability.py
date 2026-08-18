"""#1022-r4 -- UN REGIME SEPARANT EXISTE-T-IL ENTRE LE SCALAIRE ET L'`AbilityState` PAR ABILITY ?

CRITERE. `IdunBattle.Entities.Behaviours.SpawnUnitOptions$$WithStatsFromConfig(config, abilityState,
ordinal, abilitiesLevel, variableMultiplierPercentage)` indexe les variables `summon*` sous
l'`abilityState` de l'ability CASTEE. Cote port, la feuille `Spawn` lit par defaut le SCALAIRE
`UnitContext.active_ability_level`, que `engine.runner.snapshot._machine_ability_state` remplit avec
la PREMIERE active de la MoW portant un etat -- et que `_load_unit_stats` remplit, pour une unite
reguliere, avec `combatSnapshot.unitConfig.activeAbilityLevel`. Les deux lectures divergent SSI une
meme unite porte DEUX abilities a des couples `(level, multiplier)` DIFFERENTS.

CE QUE CE PROBE MESURE, ET CE QU'IL NE MESURE PAS. Il monte UN runner (montage #1022 : MoW greffee,
mais `replace=False` -- la MoW garde SES actives natives EN PLUS de 1208) et imprime, pour chaque
MoW et pour chaque unite reguliere, l'ensemble des couples distincts. Il ne conclut RIEN sur le
natif : il repond a « le harnais peut-il produire un etat ou les deux lectures du port different ».

    python probe_1022r4_abilitystate_par_ability.py [--board MC1_67] [--seed 777]

ASCII only.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import uuid
from pathlib import Path

import catalog_inject as CI
from rl_collect_batch import _load_seed_bc, _rpc, _resolve_session

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]
MOW = "ultraDreadnought"
AETHER_STRIDE = 1208


def rpc(sid, method, args, timeout=120):
    """MEME enveloppe que `probe_1022_aether_stride.rpc` : `_rpc` rend `{"result": ...}` et lire a
    cote fait conclure « le canal ne rend rien » sur une reponse pourtant complete."""
    r = _rpc(sid, method, [args], timeout=timeout)
    return r.get("result", r) if isinstance(r, dict) else r


def seed_bc_greffe() -> Path:
    """MEME greffe que `probe_1022_aether_stride.graft_seed_bc`, a UNE difference PRES et elle est
    tout l'objet du probe : `replace=False`, donc la MoW conserve ses actives natives (1158/1159)
    EN PLUS de 1208. C'est le seul moyen d'obtenir une unite a PLUSIEURS actives dont on puisse
    comparer les `AbilityState`."""
    bc = _load_seed_bc()
    rap = CI.graft_active_ability(bc, MOW, "AetherStride", replace=False)
    out = ROOT / "logs" / "runners" / ("bc-1022r4-%s.json" % uuid.uuid4().hex[:8])
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(bc), encoding="utf-8")
    print("[greffe] %s" % json.dumps(rap))
    return out


def build(seed: str, board: str, bc: Path):
    state = ROOT / "logs" / "runners" / ("st-1022r4-%s.json" % uuid.uuid4().hex[:8])
    state.parent.mkdir(parents=True, exist_ok=True)
    p = subprocess.run(
        [sys.executable, "rl_duel.py", "build", "--seed", seed, "--board", board,
         "--seed-bc", str(bc), "--state-file", str(state), "--no-ai",
         "--p-units", "ultraTigurius,ultraCalgar", "--a-units", "necroWarden,necroSpyder",
         "--p-mow", MOW],
        cwd=str(PYDIR), capture_output=True, text=True, encoding="utf-8", errors="replace")
    if not state.exists():
        print("BUILD KO : %s" % (p.stderr or p.stdout or "")[-500:])
        return None
    return json.loads(state.read_text())["runnerId"]


def _couples(abilities) -> set:
    """Les couples `(level, multiplier)` DISTINCTS d'une ligne d'abilities. Une entree sans etat
    (l'attaque `normal`, qui n'a pas d'objet `ActiveAbility` derriere) est ECARTEE : elle n'entre
    pas non plus dans `_machine_ability_state`."""
    return {(x.get("level"), x.get("multiplier")) for x in (abilities or [])
            if x.get("level") is not None or x.get("multiplier") is not None}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--board", default="MC1_67")
    ap.add_argument("--seed", default="777")
    ap.add_argument("--keep", action="store_true")
    a = ap.parse_args()
    sid = _resolve_session()

    rid = build(a.seed, a.board, seed_bc_greffe())
    if rid is None:
        return 2
    print("[build] runner=%s board=%s" % (rid, a.board))
    try:
        v = rpc(sid, "decisionView", {"runnerId": rid, "allAbilities": True})
        lignes = [("mow", m.get("visualId"), m.get("abilities")) for m in (v.get("mows") or [])] \
            + [("unit", u.get("visualId"), u.get("abilities")) for u in (v.get("units") or [])]
        if not lignes:
            # LEVER l'echec plutot que rendre un zero : on imprime la reponse BRUTE.
            print("NON MESURE : `decisionView` ne rend ni mows ni units -- brut=%s"
                  % json.dumps(v)[:500])
            return 2
        divergents, mesurees = 0, 0
        for genre, vis, abs_ in lignes:
            c = _couples(abs_)
            if not c:
                continue
            mesurees += 1
            divergents += int(len(c) > 1)
            marque = "  <-- SEPARANT" if len(c) > 1 else ""
            print("%-5s %-22s : %d ability(s) | couples distincts=%s%s"
                  % (genre, vis, len(abs_ or []), sorted(c, key=str), marque))
            if len(c) > 1:
                # LA VENTILATION EST LE RESULTAT, pas le compte : une ligne separante n'est
                # exploitable que si l'ability qui SPAWNE est celle dont l'etat differe du
                # scalaire. On imprime donc `(id, kind, level, mult)` un par un.
                for x in (abs_ or []):
                    print("        id=%-6s kind=%-8s level=%-4s mult=%s"
                          % (x.get("id"), x.get("kind"), x.get("level"), x.get("multiplier")))
        print("")
        print("LIGNES A ETAT       : %d" % mesurees)
        print("LIGNES SEPARANTES   : %d" % divergents)
        if mesurees == 0:
            print("NON MESURE : aucune ligne ne porte d'`AbilityState` -- ce zero n'est PAS un "
                  "resultat")
            return 2
        if divergents == 0:
            print("VERDICT : sur ce runner, TOUTE unite porte un couple (level, multiplier) UNIQUE")
            print("          pour toutes ses abilities. Le scalaire du port et l'`AbilityState` par")
            print("          ability COINCIDENT donc partout -- aucun regime SEPARANT n'est")
            print("          constructible ici, et la separation des deux lectures reste gardee")
            print("          OFFLINE (`test_1022r4_abilitystate_du_call_site_offline.py`).")
        else:
            print("VERDICT : %d ligne(s) portent DEUX couples distincts -- la divergence entre le"
                  % divergents)
            print("          scalaire et l'`AbilityState` par ability EXISTE sur un runner reel.")
            print("          !! SEPARANT N'EST PAS EXPLOITABLE : encore faut-il que l'ability")
            print("          DIVERGENTE soit celle qui SPAWNE. Mesure du 2026-08-18 : la seule")
            print("          ligne separante est `necroSpyder`, dont l'active qui spawne")
            print("          (`1007 ScarabHive`) porte (50, 200) -- c'est-a-dire EXACTEMENT le")
            print("          scalaire, que `_load_active_ability_levels` derive du MAX ; ce qui")
            print("          diverge est sa `granted` `28` a (1, 200), qui ne spawne rien.")
            print("          Lire la VENTILATION ci-dessus, jamais le seul compte.")
        return 0
    finally:
        if rid and not a.keep:
            try:
                rpc(sid, "disposeRunner", {"runnerId": rid}, timeout=30)
                print("[1022r4] runner %s dispose" % rid)
            except Exception as exc:                                     # noqa: BLE001
                print("[1022r4] dispose KO : %s" % exc)


if __name__ == "__main__":
    sys.exit(main())
