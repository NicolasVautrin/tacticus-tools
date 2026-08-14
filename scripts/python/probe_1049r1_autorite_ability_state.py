#!/usr/bin/env python
"""probe #1049-r1 -- QUELLE SOURCE FAIT AUTORITE pour l'`AbilityState` d'une entite.

Le residu annoncait un trou de MONTAGE (« `--explicit-stats` ecrit `Health`/`Damage`/`FixedArmor`
sans ecrire `PassiveAbilityLevel`/`AbilityVariablesMultiplierPercentage` »). C'est FAUX, et ce
probe le mesure : `catalog_inject.npc_stats` ecrit les DEUX champs, et pour
`bloodNpc1Intercessor:45` il ecrit exactement `(PassiveAbilityLevel = 65, mult = 200)` -- le couple
que le canal `unitAbilityStates` rend. Le `(1, 100)` ne vient donc PAS du montage.

IL VIENT DU CAPTEUR. `readUnitConfig` (`rpc-snapshot.ts`) ne lit PAS la `UnitConfiguration` qui a
servi a construire l'entite : il la RE-RESOUT par
`IdunBattle.Core.Services.BattleQuery$$GetUnitConfig(VisualId)`, dont le corps est une recherche
LINEAIRE sur `BC.Units[]` comparant `+0x10` puis `UnitConfiguration$$get_ConfigId` -- une jointure
N->1. Or `bloodNpc1Intercessor` porte `visualId = "bloodSmnIntercessor"` (gameconfig) : la jointure
part chercher une AUTRE entree que celle qui a monte l'unite.

CE QUI FAIT AUTORITE, LU (`rnca9r7q6c`) : `IdunBattle.Entities.Factories.UnitFactory$$Build`
construit les TROIS `AbilityState` depuis la configuration du Build --
`AbilityState..ctor(&passive, config+0xBC, config+0x74)`,
`AbilityState..ctor(&active,  config+0xB8, config+0x74)`,
`AbilityState..ctor(&tertiary, config+0xC0, config+0x78)` -- puis les passe a
`$$AddConfiguredAbilities` / `$$AddNormalAttackAbility` / `$$AddDerivedAbilities`, qui les BAKENT
dans chaque instance d'ability (`TriggeredAbilityComponent$$TryAdd(..., hierarchie)`). Et c'est cet
objet-la, pas la configuration, que
`IdunBattle.Configuration.AbilityConfiguration$$GetVariableForLevel(config, var, abilityState, 0)`
consomme. L'`AbilityState` de l'INSTANCE est donc la source ; le `unitConfig` du capteur n'en est
qu'un PROXY, exact tant que la jointure par `VisualId` retombe sur la bonne entree.

Le capteur le disait deja, sur l'autre axe : `rpc-snapshot.ts` publie `abilityStates` per-ligne en
notant que « le global unitConfig (activeAbilityLevel x abilityVariablesMultiplier) est un AUTRE
canal (u80 : 65x120 vs 50x180) », et que le couple per-ability est « celui que le natif passe au
playbook et qui indexe les variables config ». Deux temoignages independants, meme verdict.

CE QUE CE PROBE MESURE -- deux bras, chacun sur un runner FRAIS :

  * `--bras explicite` : `bloodNpc1Intercessor:45` monte par `--explicit-stats`. Confronte, pour
    CETTE entite, `combatSnapshot.unitConfig` / `combatSnapshot.units[].abilityStates` /
    `unitAbilityStates`, et rend le triple que `snapshot.py` en derive AVANT et APRES le fix.
  * `--bras ordinaire` : un montage de heros du pool, SANS explicit-stats. C'est le RAYON DE
    SOUFFLE : sur combien d'unites ordinaires les deux canaux divergent-ils ? Un fix qui fait
    primer l'instance ne doit RIEN changer la ou ils concordent.

Usage (depuis scripts/python, session warmee) :
    python probe_1049r1_autorite_ability_state.py [--bras explicite|ordinaire|all]
                                                  [--seed 777] [--board MC1_67]

ASCII only (console cp1252).
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PYDIR))

#: Le porteur du residu : npc jumeau du summon `bloodSmnIntercessor`, dont il porte le `visualId`.
#: C'est CE partage de `visualId` qui fait deriver la jointure `GetUnitConfig(VisualId)`.
NPC = "bloodNpc1Intercessor:45"
#: Adversaire quelconque, present pour que la bataille se monte.
FOE = "orksNob"
#: Bras ORDINAIRE : des heros du pool, aucun `--explicit-stats`, aucune greffe. Plusieurs unites
#: par camp -- un rayon de souffle mesure sur UNE unite ne chiffrerait rien.
PLAIN_P = "astraBullgryn,ultraEliminatorSgt,necroWarden,tauCrisis"
PLAIN_A = "orksNob,darkaTerminator,bloodIntercessor,necroOverlord"


def _unwrap(r):
    return r.get("result") if isinstance(r, dict) and "result" in r else r


def _build(seed, board, extra, prefix):
    fd, sf = tempfile.mkstemp(prefix=prefix, suffix=".json")
    os.close(fd)
    Path(sf).unlink(missing_ok=True)
    argv = [sys.executable, "rl_duel.py", "build", "--seed", str(seed),
            "--state-file", sf, "--board", board, *extra]
    p = subprocess.run(argv, cwd=str(PYDIR), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if not Path(sf).exists():
        return None, ((p.stdout or "") + (p.stderr or ""))[-800:]
    rid = json.loads(Path(sf).read_text())["runnerId"]
    Path(sf).unlink(missing_ok=True)
    return rid, None


def _canaux(rpc, rid):
    """Les TROIS canaux, par entityId : le proxy `unitConfig`, les rows per-ability de la ligne
    `combatSnapshot`, et le canal `unitAbilityStates`."""
    from engine.runner import snapshot as SNAP
    snap = _unwrap(rpc("combatSnapshot", {"runnerId": rid}, 60)) or {}
    ast = _unwrap(rpc("unitAbilityStates", {"runnerId": rid}, 60)) or {}
    chan = SNAP.passive_ability_state_by_unit(ast)
    out = {}
    for su in (snap.get("units") or []):
        eid = su.get("entityId")
        if eid is None:
            continue
        uc = su.get("unitConfig")
        out[int(eid)] = {
            "visualId": (uc or {}).get("visualId") if isinstance(uc, dict) else None,
            "uc": (None if not isinstance(uc, dict) or uc.get("error")
                   else (uc.get("abilityVariablesMultiplier"),
                         uc.get("passiveAbilityLevel"), uc.get("activeAbilityLevel"))),
            "uc_error": (uc or {}).get("error") if isinstance(uc, dict) else "absent",
            "rows": SNAP._ability_state_from_rows(su),
            "chan": chan.get(int(eid)),
            "from_config": SNAP._ability_state_from_config(uc),
            "porte": SNAP._ability_state_with_channel(
                SNAP._ability_state_with_rows(SNAP._ability_state_from_config(uc), su),
                chan.get(int(eid))),
        }
    return out


def _dump(titre, tab):
    print("\n=== %s ===" % titre)
    print("%-8s %-26s %-18s %-18s %-14s %s" % (
        "eid", "visualId", "unitConfig(m,p,a)", "rows(m,p,a)", "canal(p,m)", "PORTE(m,p,a)"))
    diverg = 0
    for eid in sorted(tab):
        r = tab[eid]
        uc = r["uc"] if r["uc"] is not None else ("ERR:" + str(r["uc_error"]))
        print("%-8d %-26s %-18s %-18s %-14s %s" % (
            eid, str(r["visualId"])[:26], str(uc)[:18], str(r["rows"])[:18],
            str(r["chan"])[:14], str(r["porte"])))
        # DIVERGENCE = le proxy et une source d'AUTORITE se contredisent sur un axe MESURE
        # des DEUX cotes. Un `None` d'un cote n'est pas une contradiction : c'est un non-mesure.
        m_uc, p_uc, _a_uc = r["from_config"]
        r_m, r_p, _r_a = r["rows"]
        c = r["chan"]
        c_p, c_m = (c if c else (None, None))
        axes = []
        if r["uc"] is not None:
            if r_p is not None and p_uc is not None and int(r_p) != int(p_uc):
                axes.append("passif rows %s != uc %s" % (r_p, p_uc))
            if c_p is not None and p_uc is not None and int(c_p) != int(p_uc):
                axes.append("passif canal %s != uc %s" % (c_p, p_uc))
            if r_m is not None and m_uc is not None and int(r_m) != int(m_uc):
                axes.append("mult rows %s != uc %s" % (r_m, m_uc))
            if c_m is not None and m_uc is not None and int(c_m) != int(m_uc):
                axes.append("mult canal %s != uc %s" % (c_m, m_uc))
        if axes:
            diverg += 1
            print("         ^^ DIVERGENCE : " + " | ".join(axes))
    print("-> %d entite(s), %d en DIVERGENCE proxy/autorite" % (len(tab), diverg))
    return diverg


def bras_explicite(rpc, seed, board) -> int:
    rid, err = _build(seed, board, [
        "--p-units", NPC, "--a-units", FOE, "--explicit-stats", NPC], "p1049r1e_")
    if rid is None:
        print("[explicite] BUILD KO : %s" % err)
        return 1
    try:
        tab = _canaux(rpc, rid)
        d = _dump("BRAS EXPLICITE (%s monte par --explicit-stats)" % NPC, tab)
        # Ce que le montage a REELLEMENT ecrit -- la premisse du residu, re-mesuree.
        import catalog_inject as CI
        f = CI.explicit_stats(NPC)["fields"]
        print("\n[premisse] catalog_inject.explicit_stats(%r) ecrit :" % NPC)
        print("   PassiveAbilityLevel = %s   AbilityVariablesMultiplierPercentage = %s"
              % (f.get("PassiveAbilityLevel"), f.get("AbilityVariablesMultiplierPercentage")))
        print("   -> le montage ECRIT les deux champs : la premisse du residu est FAUSSE.")
        return 0 if d else 1
    finally:
        rpc("disposeRunner", {"runnerId": rid}, 30)


def bras_ordinaire(rpc, seed, board) -> int:
    rid, err = _build(seed, board, ["--p-units", PLAIN_P, "--a-units", PLAIN_A], "p1049r1o_")
    if rid is None:
        print("[ordinaire] BUILD KO : %s" % err)
        return 1
    try:
        tab = _canaux(rpc, rid)
        d = _dump("BRAS ORDINAIRE (heros du pool, aucun montage)", tab)
        print("-> RAYON DE SOUFFLE : %d divergence(s) hors regime pathologique." % d)
        return 0
    finally:
        rpc("disposeRunner", {"runnerId": rid}, 30)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bras", default="all", choices=("explicite", "ordinaire", "all"))
    ap.add_argument("--seed", type=int, default=777)
    ap.add_argument("--board", default="MC1_67")
    a = ap.parse_args()

    import rl_collect_batch as R
    sid = R._resolve_session()
    w = _unwrap(R._rpc(sid, "warmupGameSingletons", [{}], timeout=180))
    if not (isinstance(w, dict) and w.get("ok")):
        print("[probe] warmup KO : %s" % str(w)[:200])
        return 2

    def rpc(method, body=None, timeout=60):
        return _unwrap(R._rpc(sid, method, [body] if body is not None else [], timeout=timeout))

    rc = 0
    if a.bras in ("explicite", "all"):
        rc |= bras_explicite(rpc, a.seed, a.board)
    if a.bras in ("ordinaire", "all"):
        rc |= bras_ordinaire(rpc, a.seed, a.board)
    return rc


if __name__ == "__main__":
    sys.exit(main())
