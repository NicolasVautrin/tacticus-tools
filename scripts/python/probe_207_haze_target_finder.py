"""case-207 -- les DEUX tirages `genrand` en TROP de `deathBlightlord` a l'entree d'une melee.

QUESTION (binaire) : quel etage NOMME consomme les 2 tirages que le natif fait et que le port ne
fait pas, et le port les reproduit-il DANS LE MEME ORDRE ?

Mesure de reference (case-dpw §7, re-derivee ici) : montage `deathBlightlord` melee nue sur
`astraCreed` (porteur de `SwornProtector`), board MC1_67, seed 777 :
    natif 5 genrand -- port 3.
Les 3 coups d'arme LIVE valent exactement `raw[2], raw[3], raw[4]` de la MEME cellule que le port
(`[890, 1934]`) -> la cellule et l'ordre du port sont JUSTES, il manque 2 tirages EN AMONT.

Le candidat lu au decompile :
  `IdunBattleLogic.Entities.Abilities.Active.Loki.HazeOfCorruption_TargetFinderAbility`
    $$CreateTrigger  = On(0x2a = PreUnitAbility, 1) & get_OwnerIsCaster
    $$CreateBehaviour= PickRandomly( Damageable( AdjacentEnemies(Self@0x148, 1, 3)
                                               & AdjacentFriends(Target@0x178, 1, 3) ),
                                     2, 0, 0x7fffffff, false )
                       ... AddBondEffect(0x435 = HazeOfCorruption_DamageTransfer) x {1, 2}
`PickRandomly` consomme `min(len(pool), amount)` tirages, bornes decroissantes (case-130).

Ce probe SEPARE les regimes en faisant varier le CARDINAL du pool, et lit les evenements natifs
pour compter les bonds 0x435 reellement poses -- c'est le temoin direct de `len(pool)`.

CLI (depuis scripts/python) :
  python probe_207_haze_target_finder.py --seeds 777                     # montage Creed (k attendu > 0)
  python probe_207_haze_target_finder.py --seeds 777 --target astraBullgryn   # controle 1v1 (k = 0)
  python probe_207_haze_target_finder.py --seeds 777 --dump-events       # tous les evenements natifs

Discipline runner : state-file ABSOLU sous logs/, board explicite, dispose en fin. ASCII only.
"""
from __future__ import annotations

import argparse
import json
import sys

from probe_r6_round_materialize import _build, _mkrpc                      # noqa: F401
from probe_159_ah_bounds import _board, _genrand_steps, _pos, _unit        # noqa: F401
from probe_dpw_weapon_cell import _drive_plain_melee, _replay_recording, _raw_stream


def replay_without_haze(dv, ob, snap, board, rng0, cid, tid, moved):
    """CONTREFACTUEL : le MEME rejeu sur le MEME flux, trigger `HazeOfCorruption_TargetFinderAbility`
    NEUTRALISE -- c'est EXACTEMENT le port d'avant case-207. Sert d'anti-tautologie : si ce modele
    reproduit aussi le live, la mesure ne prouve rien."""
    from engine.runner.operations.triggers.loki.haze_of_corruption import (
        HazeOfCorruptionTargetFinderAbility as _H)
    orig = _H.matches
    _H.matches = lambda self, state, ev: False
    try:
        return _replay_recording(dv, ob, snap, board, rng0, cid, tid, moved)
    finally:
        _H.matches = orig


def _roster(dv, snap):
    arm = {u.get("entityId"): (u.get("stats") or {}).get("fixedArmor")
           for u in (snap.get("units") or [])}
    out = []
    for u in (dv.get("units") or []):
        p = u.get("pos") or {}
        out.append({"id": u.get("id"), "vis": u.get("visualId"),
                    "pos": [p.get("col"), p.get("row")], "alive": u.get("alive"),
                    "fixedArmor": arm.get(u.get("id")),
                    "eff": [e.get("effectType") for e in (u.get("effects") or ())]})
    return out


def _run_seed(rpc, seed, args):
    rid, sf = _build(seed, args.carrier, args.target,
                     extra=["--crit", "0,0", "--block-target", "0,0",
                            "--hp-target", str(args.hp), "--armor-target", str(args.armor)],
                     rank=args.rank)
    if rid is None:
        return None
    try:
        cid, tid, aid, moved, err = _drive_plain_melee(rpc, rid, args.carrier, args.target,
                                                       max_turns=args.max_turns)
        if cid is None:
            print("[207] seed %s: drive KO -- %s" % (seed, err))
            return None
        board = _board(rpc, rid)
        dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 120)
        ob = rpc("observeBattle", {"runnerId": rid}, 60)
        snap = rpc("combatSnapshot", {"runnerId": rid}, 90)
        rng0 = rpc("dumpRng", {"runnerId": rid}, 30)
        res = rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "ability", "casterId": cid, "targetId": tid, "abilityType": aid},
            "captureEvents": True}, 120)
        rng1 = rpc("dumpRng", {"runnerId": rid}, 30)
        n_native = _genrand_steps(rng0, rng1)
        dv2 = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 120)
        snap2 = rpc("combatSnapshot", {"runnerId": rid}, 90)
        evs = []
        for act in (res.get("actions") or []):
            for ev in (act.get("events") or []):
                td = ev.get("tags")
                td = json.loads(td) if isinstance(td, str) else (td or {})
                evs.append({"name": ev.get("name") or ev.get("type") or ev.get("eventType"),
                            "tags": td})
        dmg = [int(e["tags"]["Amount"]) for e in evs if "Amount" in e["tags"]]
        bonds = sum(1 for e in evs if e["tags"].get("Effect_SourceTriggeredAbility") == 1076)
        off = _replay_recording(dv, ob, snap, board, rng0, cid, tid, moved)
        off_cf = replay_without_haze(dv, ob, snap, board, rng0, cid, tid, moved)
        return {"seed": seed, "rid": rid, "cid": cid, "tid": tid, "aid": aid, "moved": moved,
                "n_native": n_native, "n_off": off["n_genrand"], "live": dmg, "bonds": bonds,
                "n_off_cf": off_cf["n_genrand"], "cf_hits": list(off_cf["per_hit"]),
                "off_hits": list(off["per_hit"]), "cell": off["cell"],
                "rolls": off["rolls"], "raw": _raw_stream(rng0, 8),
                "roster_before": _roster(dv, snap), "roster_after": _roster(dv2, snap2),
                "events": evs}
    finally:
        try:
            rpc("disposeRunner", {"runnerId": rid}, 20)
        except Exception:
            pass
        try:
            sf.unlink()
        except Exception:
            pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", default="777")
    ap.add_argument("--carrier", default="deathBlightlord")
    ap.add_argument("--target", default="astraCreed")
    ap.add_argument("--rank", type=int, default=None)
    ap.add_argument("--hp", type=int, default=90000)
    ap.add_argument("--armor", type=int, default=6000)
    ap.add_argument("--max-turns", dest="max_turns", type=int, default=30)
    ap.add_argument("--dump-events", action="store_true")
    args = ap.parse_args()
    rpc = _mkrpc()
    rows = []
    for seed in [s for s in args.seeds.split(",") if s.strip()]:
        row = _run_seed(rpc, seed, args)
        if row is None:
            continue
        rows.append(row)
        print("[207] seed %s %s vs %s : genrand natif=%s port=%s (surplus %s)"
              % (seed, args.carrier, args.target, row["n_native"], row["n_off"],
                 row["n_native"] - row["n_off"]))
        print("   live   = %s   bonds natifs (1076) = %d" % (row["live"], row["bonds"]))
        print("   port   = %s   cellule %s" % (row["off_hits"], row["cell"]))
        print("   CONTREF= %s   (%s tirages, trigger neutralise)"
              % (row["cf_hits"], row["n_off_cf"]))
        print("   rolls  = %s" % (row["rolls"],))
        print("   raw    = %s" % (row["raw"],))
        print("   AVANT  = %s" % json.dumps(row["roster_before"]))
        print("   APRES  = %s" % json.dumps(row["roster_after"]))
        names = {}
        for e in row["events"]:
            names[e["name"]] = names.get(e["name"], 0) + 1
        print("   events = %s" % json.dumps(names))
        if args.dump_events:
            for e in row["events"]:
                print("     %-34s %s" % (e["name"], json.dumps(e["tags"])[:400]))
    return 0 if rows else 1


if __name__ == "__main__":
    sys.exit(main())
