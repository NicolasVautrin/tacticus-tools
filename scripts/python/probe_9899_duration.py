#!/usr/bin/env python
"""Probe #98 -- ETAGES de la duree d'effet (rounds -> turns).

Mesure, sur un runner LIVE pilote des DEUX camps :
  E1  valeur de config : `StaticBattleRules.Effect.DefaultAmountOfRounds` (table portee, ROUNDS)
  E2  unite / FACTEUR  : `BattleQuery.ConvertRoundsToTurns @181058af0` = count(joueurs du turnOrder,
      PlayerType != 2) * rounds -> observable via `observeBattle.counts.player`
  E3  tick de decrement : combien de `endturn` faut-il pour faire baisser `remaining` de 1 ?
  E4  instant de lecture : `remaining` juste apres la pose (avant tout tick).

Deux poses confrontees :
  A. duree EXPLICITE  `TurnsFromRounds(1)` -> ThunderousAssault (1043, templSwordBrother) pose Stunned 1162
  B. duree PAR DEFAUT `DefaultAmountOfRounds` -> SuppressiveFire (trait 1010, emperNoiseMarine) pose
     Pinned 1065 (default 1 round) sur un tir RANGED

ASCII only. Usage : python probe_9899_duration.py --state-file <abs> [--turns 8]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import hexgeo                                            # noqa: E402
from rl_collect_batch import _resolve_session, _rpc      # noqa: E402

STUNNER, SHOOTER, ENEMY = "templSwordBrother", "emperNoiseMarine", "necroWarden"


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


def effs(u, prefix=None):
    out = []
    for e in (u.get("effects") or []):
        if prefix is None or str(e.get("name")).startswith(prefix):
            out.append((e.get("name"), e.get("effectType"), e.get("level"), e.get("remaining")))
    return out


def movable(sid, rid, uid):
    mov = _r(sid, "aiMovableTiles", {"runnerId": rid}, 90)
    for m in (mov.get("units") or []):
        if m.get("unitId") == uid:
            return [(t["col"], t["row"]) for t in (m.get("tiles") or [])]
    return []


def drive_to(sid, rid, uid, anchor, want):
    """Place `uid` a la distance hex `want` de `anchor` (tuile legale la plus proche de l'objectif)."""
    tiles = movable(sid, rid, uid)
    if not tiles:
        return None
    best = min(tiles, key=lambda t: abs(hexgeo.distance(t, anchor) - want))
    act(sid, rid, {"kind": "move", "unitId": uid, "to": {"col": best[0], "row": best[1]}})
    return hexgeo.distance(best, anchor)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--state-file", required=True)
    ap.add_argument("--turns", type=int, default=6)
    ap.add_argument("--stunner", default="templSwordBrother")
    ap.add_argument("--shooter", default="emperNoiseMarine")
    ap.add_argument("--enemy", default="necroWarden")
    args = ap.parse_args()
    global STUNNER, SHOOTER, ENEMY
    STUNNER, SHOOTER, ENEMY = args.stunner, args.shooter, args.enemy
    sid = _resolve_session()
    rid = json.loads(Path(args.state_file).read_text())["runnerId"]
    print("[dur] session=%s runner=%s" % (sid, rid))

    ob = _r(sid, "observeBattle", {"runnerId": rid}, 60)
    counts = ob.get("counts") or {}
    print("[E2] observeBattle.counts = %s" % json.dumps(counts, sort_keys=True))

    d = dv(sid, rid)
    me = d.get("currentPlayer")
    print("[E2] currentPlayer=%s  units=%d" % (me, len(d.get("units") or [])))

    # --- A. duree EXPLICITE TurnsFromRounds(1) : Stunned 1162 par ThunderousAssault ---
    print("\n--- A. Stunned 1162 (TurnsFromRounds(1) explicite) ---")
    for _ in range(12):
        d = dv(sid, rid)
        sb = U(d, STUNNER)
        ens = U(d, ENEMY)
        if not sb or not ens:
            print("  SKIP roster"); break
        if d.get("currentPlayer") != sb[0].get("owner"):
            act(sid, rid, {"kind": "endturn"}); continue
        caster = sb[0]
        tgt = min(ens, key=lambda e: hexgeo.distance(P(e), P(caster)))
        if hexgeo.distance(P(tgt), P(caster)) > 1:
            got = drive_to(sid, rid, caster["id"], P(tgt), 1)
            d = dv(sid, rid)
            caster = U(d, STUNNER)[0]
            tgt = byid(d, tgt["id"])
            if hexgeo.distance(P(tgt), P(caster)) > 1:
                # rapproche la cible ADVERSE (drive des deux camps)
                act(sid, rid, {"kind": "endturn"})
                d = dv(sid, rid)
                c2 = U(d, STUNNER)[0]
                drive_to(sid, rid, tgt["id"], P(c2), 1)
                act(sid, rid, {"kind": "endturn"})
                continue
        r = act(sid, rid, {"kind": "ability", "casterId": caster["id"],
                           "targetId": tgt["id"], "abilityType": 1043})
        d2 = dv(sid, rid)
        t2 = byid(d2, tgt["id"])
        print("  cast ok=%s -> cible u%s effets=%s" % (r.get("ok"), tgt["id"], effs(t2)))
        # E3/E4 : suit `remaining` du 1162 tour par tour
        seq = [(0, next((e[3] for e in effs(t2) if e[1] == 1162), None))]
        for k in range(args.turns):
            act(sid, rid, {"kind": "endturn"})
            dk = dv(sid, rid)
            tk = byid(dk, tgt["id"])
            rem = next((e[3] for e in effs(tk or {}) if e[1] == 1162), None) if tk else None
            seq.append((k + 1, rem))
            if rem is None:
                break
        print("  [E3/E4] remaining(1162) apres N endturn : %s" % seq)
        break

    # --- B. duree PAR DEFAUT : Pinned 1065 (SuppressiveFire, tir ranged de emperNoiseMarine) ---
    print("\n--- B. Pinned 1065 (DefaultAmountOfRounds, aucun TurnsFromRounds) ---")
    for _ in range(12):
        d = dv(sid, rid)
        sh = U(d, SHOOTER)
        ens = U(d, ENEMY)
        if not sh or not ens:
            print("  SKIP roster"); break
        if d.get("currentPlayer") != sh[0].get("owner"):
            # tour adverse : place une cible a distance 2 de Shiron
            tgt = ens[0]
            drive_to(sid, rid, tgt["id"], P(sh[0]), 2)
            act(sid, rid, {"kind": "endturn"}); continue
        shiron = sh[0]
        cand = [e for e in ens if hexgeo.distance(P(e), P(shiron)) >= 2
                and not any(x[1] == 1065 for x in effs(e))]
        if not cand:
            act(sid, rid, {"kind": "endturn"}); continue
        tgt = min(cand, key=lambda e: hexgeo.distance(P(e), P(shiron)))
        r = act(sid, rid, {"kind": "ability", "casterId": shiron["id"],
                           "targetId": tgt["id"], "abilityType": 69})
        d2 = dv(sid, rid)
        t2 = byid(d2, tgt["id"])
        print("  tir ok=%s dist=%d -> cible u%s effets=%s"
              % (r.get("ok"), hexgeo.distance(P(tgt), P(shiron)), tgt["id"], effs(t2)))
        seq = [(0, next((e[3] for e in effs(t2) if e[1] == 1065), None))]
        if seq[0][1] is None:
            act(sid, rid, {"kind": "endturn"}); continue
        for k in range(args.turns):
            act(sid, rid, {"kind": "endturn"})
            dk = dv(sid, rid)
            tk = byid(dk, tgt["id"])
            rem = next((e[3] for e in effs(tk or {}) if e[1] == 1065), None) if tk else None
            seq.append((k + 1, rem))
            if rem is None:
                break
        print("  [E3/E4] remaining(1065) apres N endturn : %s" % seq)
        break


if __name__ == "__main__":
    main()

