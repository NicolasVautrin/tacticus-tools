#!/usr/bin/env python
"""#942-r3 -- le gate slot-4 de `1210 ExemplarOfTheMontka` BASCULE, et on le mesure des DEUX cotes.

CE QUE CE PROBE MESURE, ET POURQUOI C'EST LE CAS RARE OU LE PORT PEUT ETRE EXACT
---------------------------------------------------------------------------------
`...ExemplarOfTheMontkaPlaybook$$ShouldEvaluate` SURCHARGE DIRECTEMENT le slot 4 -- il ne passe
PAS par `GetUseProbability`, donc il n'y a AUCUN tirage aleatoire a ne pas modeliser (contraste
`BlackRage`, `Waaagh`, `EmpyricAmbush`). Son corps, verbatim :

    naType = UnitExtensions$$GetNormalAttackType(unit)
    res    = <IBattleQuery slot 0x45>(unit, naType, false)
    foreach (kv in res) foreach (target in kv.Value)
        if (!BasePlaybook$$WillNormalAttackKill(this, unit, target, kv.Key.get_MainTile()))
            return true
    return false

⚠ **LE NOM MENT** : ce n'est pas << ai-je une cible ? >> mais << ai-je une cible que mon attaque
normale NE TUE PAS ? >>. Le gate est donc BASCULABLE par un seul levier : les PV des ennemis.

LE MONTAGE, ET SON TEMOIN
--------------------------
Deux regimes, meme board, meme placement, meme roster -- SEULS les PV des a-units changent :

    A  `--hp-target 1`        toute cible est SURE-KILL  -> le natif doit rendre **False**
    B  `--hp-target <haut>`   aucune ne l'est            -> le natif doit rendre **True**

⚠ **LE TEMOIN EST OBLIGATOIRE** : un `False` en A ne prouve rien s'il n'y a AUCUNE cible
d'attaque normale (le natif rendrait `false` par liste vide, pas par sure-kill). Le probe exige
donc, DANS LES DEUX REGIMES, que `abilityTargets(uid, <normal attack>)` publie au moins une
cible. Sans ce controle, A et B pourraient differer pour une raison qui n'est pas le gate.

⚠ **ET LA BASCULE ELLE-MEME EST LE CONTROLE DE NON-DEGENERESCENCE** : deux mesures IDENTIQUES
(True/True ou False/False) sont un ECHEC, meme si le port les reproduit -- un gate qui ne bascule
pas ne discrimine rien, et l'accord y serait sans valeur.

`tauFarsight` est HORS POOL : il est injecte au catalogue (`catalog_inject`), pas declare
<< non confrontable >>.

Tri-etat : 0 = mesure faite et conforme ; 1 = mesure faite et DIVERGENTE ; 2 = PAS MESURE
(session, cap de runners, montage impossible) -- jamais rabattu sur un vert.

Usage (depuis scripts/python) :
    python probe_942r3_montka_gate_live.py --state-file <ABSOLU> [--board MC1_67] [--seed 777]
ASCII only (cp1252).
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import requests

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

HOST = "http://127.0.0.1:8765"
CASTER = "tauFarsight"
ENEMIES = "orksNob,tyranWingedPrime"
MONTKA = 1210

EX_VERT, EX_ROUGE, EX_PAS_MESURE = 0, 1, 2

DECLENCHEUR = {
    "chemins": ("scripts/python/engine/playbook/noncomparable/exemplar_of_the_montka.py",
                "scripts/python/engine/playbook/noncomparable/_base.py",
                "scripts/python/engine/playbook/base.py",
                "scripts/python/probe_942r3_montka_gate_live.py"),
    "build": True,
    "toujours": False,
    "raison": "Il invoque le SLOT 4 de la vtable d'`IPlaybook` (un renumerotage d'interface le "
              "perime) et confronte au port `ExemplarOfTheMontkaPlaybook.should_evaluate`, dont "
              "le gate emprunte le foyer `engine.playbook.base.will_normal_attack_kill`.",
}


def sid() -> int:
    return int(requests.get("%s/api/admin/status" % HOST, timeout=10).json()["session"]["id"])


def rpc(s: int, method: str, args=None, timeout: int = 90):
    r = requests.post("%s/api/scripts/%d/rpc" % (HOST, s),
                      json={"method": method, "args": [args or {}], "timeout": int(timeout) * 1000},
                      timeout=timeout + 30)
    if r.status_code >= 400:
        raise RuntimeError("%s HTTP %d: %s" % (method, r.status_code, r.text[:400]))
    body = r.json()
    if body.get("error"):
        raise RuntimeError(str(body["error"])[:400])
    return body.get("result") or {}


def _bool_natif(g):
    """Decode le `System.Boolean` de `pbGate`. `retRaw` est une CHAINE HEXA -- `bool(retRaw)` rend
    `True` pour `"0"` aussi (la faute que `probe_974` a commise a son premier tir). `retLow` porte
    les 8 bits de poids faible, exactement la largeur d'un `bool` C#."""
    v = g.get("retLow")
    return None if v is None else bool(int(v) & 0xff)


def seed_bc(out: Path) -> Path:
    if out.exists():
        return out
    out.parent.mkdir(parents=True, exist_ok=True)
    import catalog_inject
    catalog_inject.write_augmented_seed_bc(str(out), [CASTER])
    return out


def build(state_file: Path, bc: Path, board: str, seed: str, hp: int) -> int:
    state_file.parent.mkdir(parents=True, exist_ok=True)
    if state_file.exists():
        state_file.unlink()
    cmd = [sys.executable, "rl_duel.py", "build", "--seed", seed, "--board", board,
           "--seed-bc", str(bc), "--p-units", CASTER, "--a-units", ENEMIES,
           "--hp-target", str(hp), "--place", "%s:4,5" % CASTER, "--a-place", "orksNob:5,5",
           "--state-file", str(state_file)]
    proc = subprocess.run(cmd, cwd=str(HERE), capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    if not state_file.exists():
        raise RuntimeError("build KO: %s" % ((proc.stderr or proc.stdout or "")[-700:]))
    return int(json.loads(state_file.read_text())["runnerId"])


def mesurer(s: int, rid: int, regime: str):
    """`(natif, port, n_cibles, refus)` -- un tri-etat par grandeur, jamais un `False` fabrique."""
    from engine.ai import context as ai_ctx
    from engine.playbook import noncomparable as playbooks
    from engine.playbook import scene as scene_mod
    from engine import weights as W

    _rpc = lambda m, b, t=90: rpc(s, m, b, t)                       # noqa: E731
    dv = _rpc("decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 32}, 180)
    cid = next((u.get("id") for u in (dv.get("units") or [])
                if u.get("visualId") == CASTER and u.get("alive")), None)
    if cid is None:
        return None, None, None, "caster %s absent du decisionView" % CASTER

    # -- NATIF : le slot 4, invoque a la vtable ------------------------------------------------
    sl = _rpc("pbSlots", {"runnerId": rid, "abilityType": MONTKA, "maxSlots": 6}, 60)
    itf = next((i for i in (sl.get("interfaces") or []) if i.get("slots")), None)
    slots = (itf or {}).get("slots") or []
    s4 = next((x for x in slots if x.get("slot") == 4), None)
    if s4 is None:
        return None, None, None, "slot 4 absent de l'interface Playbook"
    # L'ARITE est LUE, pas supposee : `ShouldEvaluate(unit)` prend 1 parametre, et passer le
    # mauvais nombre d'arguments ferait lire le `MethodInfo*` comme si c'etait l'unite.
    nargs = int(s4.get("params") or 0)
    g = _rpc("pbGate", {"runnerId": rid, "unitId": cid, "abilityType": MONTKA,
                        "itf": "Playbook", "slot": 4,
                        "args": ["unit"] * nargs}, 40)
    if not g.get("ok"):
        return None, None, None, "pbGate slot 4 : %s" % (g.get("error") or "invocation KO")
    natif = _bool_natif(g)
    print("   [%s] classe=%s slot4=%r params=%d -> natif=%s (retRaw=%s hex)"
          % (regime, sl.get("playbookClass"), s4.get("name"), nargs, natif, g.get("retRaw")))

    # -- TEMOIN : y a-t-il seulement une cible d'attaque normale ? -----------------------------
    mov = _rpc("aiMovableTiles", {"runnerId": rid}, 60)
    predictor = scene_mod.build_predictor(_rpc, rid)
    mov_by_unit = {u.get("unitId"): u for u in (mov.get("units") or [])}
    ctx = ai_ctx.build(_rpc, rid, dv, mov_by_unit, cid, W.load(), predictor, debug=False)
    nc = playbooks.NCContext(
        uid=ctx.uid, origin=ctx.origin, reach_nc=ctx.reach_nc, epos=ctx.epos, fpos=ctx.fpos,
        enemies=ctx.enemies, neigh_by_pos=ctx.neigh_by_pos, walkable_by_pos=ctx.walkable_by_pos,
        plan=ctx.plans.get(ctx.uid) or {}, plans=ctx.plans, hp_cur_by_id=ctx.hp_cur_by_id,
        elev_by_pos=ctx.elev_by_pos, ability_targets=ctx.ability_targets, wt=ctx.wt,
        is_temporary_by_pos=ctx.is_temporary_by_pos, effects_by_pos=ctx.effects_by_pos,
        obs_units=ctx.obs_units, tile_id_by_pos=ctx.tile_id_by_pos,
        active_levels=ctx.active_ability_levels, units=ctx.units,
        cast_from_tiles=ctx.cast_from_tiles, scene=ctx.scene, debug=False)
    from engine.playbook.noncomparable._base import _normal_attack_ids
    nids = _normal_attack_ids(nc, nc.uid)
    n_cibles = 0
    for na in sorted(nids):
        at = nc.ability_targets(nc.uid, na) or {}
        for u in (at.get("units") or []):
            if u.get("unitId") != nc.uid:
                continue
            for a in (u.get("abilities") or []):
                if a.get("abilityId") == na:
                    n_cibles += len(a.get("targets") or [])

    # -- PORT ----------------------------------------------------------------------------------
    pb = playbooks.PLAYBOOKS.get(MONTKA)
    if pb is None:
        return natif, None, n_cibles, "1210 absente du registre NonComparable"
    port = bool(pb.should_evaluate(nc))
    print("   [%s] normalAttack=%s cibles=%d -> port=%s" % (regime, sorted(nids), n_cibles, port))
    return natif, port, n_cibles, ""


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--state-file", required=True)
    ap.add_argument("--board", default="MC1_67")
    ap.add_argument("--seed", default="777")
    ap.add_argument("--hp-haut", type=int, default=400000)
    a = ap.parse_args(argv)

    try:
        s = sid()
    except Exception as exc:                                            # noqa: BLE001
        print("[942r3] PAS MESURE -- session Frida indisponible : %s" % exc)
        return EX_PAS_MESURE

    sf = Path(a.state_file)
    bc = seed_bc(sf.parent / "seed_montka.json")
    resultats = {}
    for regime, hp in (("A sure-kill", 1), ("B survivant", a.hp_haut)):
        print("[942r3] REGIME %s (hp-target=%d)" % (regime, hp))
        try:
            rid = build(sf, bc, a.board, a.seed, hp)
        except Exception as exc:                                        # noqa: BLE001
            print("[942r3] PAS MESURE -- %s" % str(exc)[:400])
            return EX_PAS_MESURE
        try:
            natif, port, ncib, refus = mesurer(s, rid, regime)
        finally:
            try:
                rpc(s, "disposeRunner", {"runnerId": rid}, 20)
            except Exception as exc:                                    # noqa: BLE001
                print("[942r3] dispose KO: %s" % str(exc)[:200])
        if refus:
            print("[942r3] PAS MESURE -- %s" % refus)
            return EX_PAS_MESURE
        if natif is None or port is None:
            print("[942r3] PAS MESURE -- une des deux faces n'a rien rendu")
            return EX_PAS_MESURE
        resultats[regime] = (natif, port, ncib)

    print("\n[942r3] CONFRONTATION")
    ko = 0
    for regime, (natif, port, ncib) in resultats.items():
        egal = (natif == port)
        print("   %-14s natif=%-5s port=%-5s cibles=%-3d -> %s"
              % (regime, natif, port, ncib, "OK" if egal else "DIVERGENCE"))
        if not egal:
            ko += 1
        if ncib == 0:
            print("      TEMOIN VIDE : aucune cible d'attaque normale -- un `False` natif ne "
                  "viendrait PAS du sure-kill mais de la liste vide. Re-crafter le placement.")
            ko += 1
    nat = [v[0] for v in resultats.values()]
    if len(set(nat)) < 2:
        print("   REGIME DEGENERE : le gate natif rend %r dans les DEUX regimes -- il n'a pas "
              "bascule, donc l'accord ne prouve rien. Re-crafter les PV." % (nat[0],))
        ko += 1
    else:
        print("   LE GATE BASCULE : natif %s -> %s entre A et B. L'accord porte donc sur un "
              "regime DISCRIMINANT." % (nat[0], nat[1]))
    print("\n[942r3] VERDICT : %s" % ("OK" if ko == 0 else "FAIL (%d)" % ko))
    return EX_VERT if ko == 0 else EX_ROUGE


if __name__ == "__main__":
    sys.exit(main())
