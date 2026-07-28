"""Probe DakkaDakkaDakka (1171, orksKillaKan) -- MESURE du cast live + du diag offline.

But : distinguer les deux signatures homonymes du harnais (cf. CLAUDE.md / brief case-decision-noop) :
  * NO-OP SILENCIEUX  = le cast est ACCEPTE et ne mute rien (ce que le port doit fermer) ;
  * MONTAGE RATE      = `applyAction` rend ok=True mais le natif a refuse le cast en silence
                        (unite pas dans `toActivate`, pas son tour, cible hors gate...).
Le probe imprime : `abilityReason`, `decisionView.toActivate`, le nb d'evenements, les tags de degat,
et le `last` COMPLET du `AbilityHandler` offline. ASCII only.

    python probe_ddd_1171_cast.py [--seed 777] [--board MC1_67] [--hp-target 500000]
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys

import rl_collect_batch as R

_SID = None


def _unwrap(r):
    return r.get("result") if isinstance(r, dict) and "result" in r else r


def rpc(method, params, timeout=90):
    global _SID
    if _SID is None:
        _SID = R._resolve_session()
    return _unwrap(R._rpc(_SID, method, [params], timeout=timeout))


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", default="777")
    ap.add_argument("--board", default="MC1_67")
    ap.add_argument("--hp-target", default="500000")
    ap.add_argument("--a-units", default="orksNob,tyranTyrantGuard,templAggressor")
    ap.add_argument("--state-file", default=None)
    a = ap.parse_args(argv)

    sf = a.state_file or os.path.abspath(os.path.join(os.path.dirname(__file__),
                                                      "..", "..", "logs", "probe_ddd_1171.json"))
    os.makedirs(os.path.dirname(sf), exist_ok=True)
    cmd = [sys.executable, os.path.join(os.path.dirname(__file__), "rl_duel.py"), "build",
           "--seed", a.seed, "--board", a.board, "--state-file", sf,
           "--p-units", "orksKillaKan", "--a-units", a.a_units,
           "--crit", "0,0", "--block-target", "0,0", "--hp-target", a.hp_target]
    print("[build]", " ".join(cmd[2:]))
    subprocess.run(cmd, check=True, cwd=os.path.dirname(__file__))
    rid = json.load(open(sf))["runnerId"]
    print("[build] runnerId =", rid)
    try:
        dv = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True})
        alive = [u for u in (dv.get("units") or []) if u.get("alive")]
        snappa = next((u for u in alive if u.get("visualId") == "orksKillaKan"), None)
        print("[state] currentPlayer =", dv.get("currentPlayer"),
              "| toActivate =", dv.get("toActivate"))
        print("[state] snappa =", None if snappa is None else
              {k: snappa.get(k) for k in ("id", "owner", "pos", "hp", "hpMax")})
        if snappa is None:
            return 1
        abil = [{k: ab.get(k) for k in ("id", "usable", "reason")}
                for ab in (snappa.get("abilities") or [])]
        print("[state] abilities du caster =", abil)
        ens = [u for u in alive if u.get("owner") != snappa.get("owner")]
        print("[state] ennemis =", [(u["id"], u.get("visualId"), u.get("pos"), u.get("hp"))
                                    for u in ens])
        tgt = ens[0]["id"]
        # AMENER la cible a portee : `applyAction move` ignore la propriete (cf.
        # `feedback_drive_positions_dont_blame_geometry`). PLACER D'ABORD, atteindre son tour ENSUITE
        # (un `move` fait basculer le joueur courant -> le cast suivant serait refuse EN SILENCE).
        cp = snappa.get("pos") or {}
        import hexgeo as _hg
        bg = rpc("boardGraph", {"runnerId": rid}, 60)
        occupied = {(u["pos"]["col"], u["pos"]["row"]) for u in alive if u.get("pos")}
        dest = None
        for t in (bg.get("tiles") or []):
            c = (t.get("col"), t.get("row"))
            if (t.get("walkable") and c not in occupied
                    and _hg.distance((cp.get("col"), cp.get("row")), c) == 2):
                dest = c
                break
        print("[place] cible u%d -> %s (caster @%s)" % (tgt, dest, (cp.get("col"), cp.get("row"))))
        if dest is not None:
            rpc("applyAction", {"runnerId": rid, "action": {
                "kind": "move", "unitId": tgt, "to": {"col": dest[0], "row": dest[1]}}}, 40)
        for _ in range(12):
            dv = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True})
            if dv.get("currentPlayer") == snappa.get("owner"):
                break
            rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 40)
        print("[state] currentPlayer =", dv.get("currentPlayer"),
              "| toActivate =", dv.get("toActivate"))
        print("[gate] abilityReason =",
              rpc("abilityReason", {"runnerId": rid, "casterId": snappa["id"],
                                    "targetId": tgt, "abilityType": 1171}))
        res = rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "ability", "casterId": snappa["id"], "targetId": tgt, "abilityType": 1171}})
        a0 = (res.get("actions") or [{}])[0]
        print("[cast] ok =", res.get("ok"), a0.get("ok"), "| mutated =", a0.get("mutated"),
              "| #events =", len(a0.get("events") or []))
        for e in (a0.get("events") or [])[:40]:
            td = e.get("tags")
            td = json.loads(td) if isinstance(td, str) else td
            print("   ev", e.get("name") or e.get("type"), td)
    finally:
        rpc("disposeRunner", {"runnerId": rid}, 20)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
