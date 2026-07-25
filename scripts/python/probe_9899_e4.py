#!/usr/bin/env python
"""Probe #98 E4 -- INSTANT DE LECTURE : le `remaining` lu apres un cast est-il pris AVANT ou APRES le
tick de fin de tour ?

Le cast d'une ability queue `AddFlagsAfterAbilityExecution` -> `FinishUnitTurn(caster)`. Si le caster
etait la DERNIERE unite activable de son camp, le moteur cloture le tour -> `EndTurnOperation` ->
`RefreshEffects` (tick -1 de TOUS les effets a duree) AVANT que `decisionView` soit relu.

On imprime `currentPlayer` AVANT et APRES le cast + le `remaining` du Stun. Si `currentPlayer` change,
la lecture est POST-TICK (valeur affichee = duree_initiale - 1).

ASCII only. Usage : python probe_9899_e4.py --state-file <abs>
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import hexgeo                                            # noqa: E402
from rl_collect_batch import _resolve_session, _rpc      # noqa: E402

STUNNER, ENEMY = "templSwordBrother", "necroWarden"


def _r(sid, m, b, t=180):
    return (_rpc(sid, m, [b], timeout=t).get("result") or {})


def dv(sid, rid):
    return _r(sid, "decisionView", {"runnerId": rid, "maxRank": 99, "allAbilities": True})


def act(sid, rid, a):
    return _r(sid, "applyAction", {"runnerId": rid, "action": a, "captureEvents": False})


def U(d, vis):
    return [u for u in (d.get("units") or []) if u.get("visualId") == vis and u.get("alive")]


def byid(d, uid):
    return next((u for u in (d.get("units") or []) if u.get("id") == uid), None)


def P(u):
    return (u["pos"]["col"], u["pos"]["row"])


def rem_of(u, et):
    for e in ((u or {}).get("effects") or []):
        if e.get("effectType") == et:
            return e.get("remaining")
    return None


def movable(sid, rid, uid):
    mov = _r(sid, "aiMovableTiles", {"runnerId": rid}, 90)
    for m in (mov.get("units") or []):
        if m.get("unitId") == uid:
            return [(t["col"], t["row"]) for t in (m.get("tiles") or [])]
    return []


def drive_to(sid, rid, uid, anchor, want):
    tiles = movable(sid, rid, uid)
    if not tiles:
        return None
    best = min(tiles, key=lambda t: abs(hexgeo.distance(t, anchor) - want))
    act(sid, rid, {"kind": "move", "unitId": uid, "to": {"col": best[0], "row": best[1]}})
    return hexgeo.distance(best, anchor)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--state-file", required=True)
    ap.add_argument("--stunner", default=STUNNER)
    ap.add_argument("--enemy", default=ENEMY)
    args = ap.parse_args()
    sid = _resolve_session()
    rid = json.loads(Path(args.state_file).read_text())["runnerId"]
    print("[e4] session=%s runner=%s" % (sid, rid))

    for _ in range(14):
        d = dv(sid, rid)
        sb = U(d, args.stunner)
        ens = U(d, args.enemy)
        if not sb or not ens:
            print("  SKIP roster"); return
        caster = sb[0]
        if d.get("currentPlayer") != caster.get("owner"):
            act(sid, rid, {"kind": "endturn"}); continue
        tgt = min(ens, key=lambda e: hexgeo.distance(P(e), P(caster)))
        if hexgeo.distance(P(tgt), P(caster)) > 1:
            drive_to(sid, rid, caster["id"], P(tgt), 1)
            d = dv(sid, rid)
            caster = U(d, args.stunner)[0]
            tgt = byid(d, tgt["id"])
            if hexgeo.distance(P(tgt), P(caster)) > 1:
                act(sid, rid, {"kind": "endturn"})
                d = dv(sid, rid)
                c2 = U(d, args.stunner)[0]
                drive_to(sid, rid, tgt["id"], P(c2), 1)
                act(sid, rid, {"kind": "endturn"})
                continue
        # unites de MON camp encore activables (le decisionView expose `acted`/`ctrl`)
        mine = [u for u in (d.get("units") or []) if u.get("owner") == caster.get("owner")
                and u.get("alive")]
        print("  AVANT cast : currentPlayer=%s  mes unites vivantes=%d (%s)"
              % (d.get("currentPlayer"), len(mine), [u["id"] for u in mine]))
        r = act(sid, rid, {"kind": "ability", "casterId": caster["id"],
                           "targetId": tgt["id"], "abilityType": 1043})
        d2 = dv(sid, rid)
        t2 = byid(d2, tgt["id"])
        print("  APRES cast : ok=%s currentPlayer=%s  remaining(1162)=%s"
              % (r.get("ok"), d2.get("currentPlayer"), rem_of(t2, 1162)))
        print("  VERDICT : tour %s -> lecture %s"
              % ("CHANGE (tick auto)" if d2.get("currentPlayer") != d.get("currentPlayer")
                 else "INCHANGE (pas de tick)",
                 "POST-TICK" if d2.get("currentPlayer") != d.get("currentPlayer") else "PRE-TICK"))
        return
    print("  pas de cast realise")


if __name__ == "__main__":
    main()
