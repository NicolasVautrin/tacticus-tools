"""Probe adversarial du fix summon (AberrantHypermorph 1166).

Marche la trajectoire native jusqu'au step ou le summoner (ability 1166) agit,
dump les internals du bloc summon d'engine_decide (origin, reach_nc, spawn_tiles,
distance origin->dest, utilite par tuile de move) et compare a la decision native
(move-tile + spawn cible). Reutilisable: --steps, runner courant.

Usage: python probe_summon.py [--steps 24]
"""
from __future__ import annotations
import argparse
import sys

from rl_collect_batch import _resolve_session, _rpc
from engine import weights, leaves
import hexgeo
import engine_validate as EV
import predict_validate as PV


def _r(sid, method, params, timeout=40):
    return EV._r(sid, method, params, timeout)


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--runner", type=int, default=None)
    ap.add_argument("--steps", type=int, default=24)
    a = ap.parse_args(argv)
    sid = _resolve_session()
    rid = a.runner
    if rid is None:
        rl = _rpc(sid, "listRunners", [], timeout=10).get("result") or []
        rid = (rl[-1]["runnerId"] if isinstance(rl[-1], dict) else rl[-1]) if rl else None
    wt = weights.load()
    predictor = PV.build_predictor(sid, rid)
    print(f"[probe] session={sid} runner={rid}")

    for step in range(a.steps):
        dry = _r(sid, "aiStepDryRun", {"runnerId": rid}, 40)
        if not dry.get("ok") or not dry.get("hasNext"):
            print(f"  step {step}: native epuise")
            break
        nat = EV.native_chunk(dry.get("action") or {})
        uid = dry.get("activatedUnitId") or nat.get("unit")

        # Detecte l'ability summon dans le chunk natif
        is_summon_step = bool(nat["ability"] and leaves.is_summon(nat["ability"]["ability"]))

        if is_summon_step:
            dv = _r(sid, "decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 32}, 180)
            mov = _r(sid, "aiMovableTiles", {"runnerId": rid}, 60)
            tm = _r(sid, "tileMeta", {"runnerId": rid}, 60)
            elev_by_pos = {(t.get("col"), t.get("row")): t.get("elevation")
                           for t in (tm.get("tiles") or [])}
            if predictor is not None:
                PV.refresh_shields(predictor, sid, rid)
            mov_by_unit = {u.get("unitId"): u for u in (mov.get("units") or [])}

            # Reconstitue le contexte du bloc summon (mirroir d'engine_decide)
            units = dv.get("units") or []
            me = next((u for u in units if u.get("id") == uid), None)
            enemies = [u for u in units if u.get("alive") and not u.get("ctrl")
                       and u.get("pos") and u.get("id") != uid]
            epos = [(e["pos"]["col"], e["pos"]["row"]) for e in enemies]
            origin = (me["pos"]["col"], me["pos"]["row"]) if me and me.get("pos") else None
            move_tiles = (mov_by_unit.get(uid) or {}).get("tiles") or []
            reach_nc = ([origin] if origin is not None else []) + \
                [(t["col"], t["row"]) for t in move_tiles]

            aid = nat["ability"]["ability"]
            at = _r(sid, "abilityTargets", {"runnerId": rid, "unitId": uid, "abilityType": aid}, 40)
            spawn_tiles = []
            for u in (at.get("units") or []):
                for ab in (u.get("abilities") or []):
                    if ab.get("abilityId") == aid:
                        spawn_tiles = [(t["tile"].get("col"), t["tile"].get("row"))
                                       for t in (ab.get("targets") or [])
                                       if t.get("kind") == "tile" and t.get("tile")
                                       and t["tile"].get("col") is not None]

            print(f"\n=== STEP {step}: SUMMON u{uid} ability={aid} ===")
            print(f"  origin={origin}")
            print(f"  epos={epos}")
            print(f"  spawn_tiles (abilityTargets from origin, n={len(spawn_tiles)})={spawn_tiles}")
            # portee: distance origin->chaque spawn tile (claim 2 = tous == 1 ?)
            dists = sorted(set(hexgeo.distance(origin, st) for st in spawn_tiles)) if origin else []
            print(f"  PORTEE spawn = distances origin->spawn = {dists}  (claim2: {{1}})")
            print(f"  move_tiles n={len(move_tiles)}  reach_nc n={len(reach_nc)}")
            # Count adjacent GATE |Delta elev| < 2 (mirroir IterateAdjacentTiles natif)
            def gated_count(ST):
                e_st = elev_by_pos.get(ST)
                c = 0
                for p in epos:
                    if hexgeo.distance(ST, p) != 1:
                        continue
                    e_p = elev_by_pos.get(p)
                    if e_st is None or e_p is None or abs(e_st - e_p) < 2:
                        c += 1
                return float(c)

            # utilite par tuile de move T (mirroir exact du fix) + variante gatee
            per_T = []
            for T in reach_nc:
                inter = [ST for ST in spawn_tiles if hexgeo.distance(T, ST) == 1]
                cnt = [leaves.summon_utility(ST, epos) for ST in inter]  # PUR (port actuel)
                cntg = [gated_count(ST) for ST in inter]                 # GATE (natif)
                u_ = max(cnt) if cnt else 0.0
                ug = max(cntg) if cntg else 0.0
                d_orig = hexgeo.distance(origin, T) if origin else None
                per_T.append((T, d_orig, u_, ug, len(inter)))
            arg_pure = max(per_T, key=lambda x: x[2]) if per_T else None
            arg_gate = max(per_T, key=lambda x: x[3]) if per_T else None
            per_T.sort(key=lambda x: -x[2])
            print("  TOP tuiles de move (T, dist_origin, util_PUR, util_GATE, n_spawn):")
            for row in per_T[:8]:
                flag = " <<DIVERGE" if row[2] != row[3] else ""
                print(f"    T={row[0]} dOrig={row[1]} PUR={row[2]} GATE={row[3]} nSpawn={row[4]}{flag}")
            print(f"  ARGMAX pur -> T={arg_pure[0]} (u={arg_pure[2]}) | "
                  f"ARGMAX gate -> T={arg_gate[0]} (u={arg_gate[3]})  "
                  f"{'*** ELEV DIVERGE ***' if arg_pure[0] != arg_gate[0] else 'meme argmax'}")

            eng = EV.engine_decide(sid, rid, dv, mov_by_unit, uid, wt, predictor)
            print(f"  ENGINE decision: kind={eng['kind']} ability={eng.get('ability')} "
                  f"to={eng.get('to')} util={eng.get('util')}")
            print(f"  NATIVE decision: move_to={nat['move']['to'] if nat['move'] else None} "
                  f"ability={aid} spawn_tgt={nat['ability']['target']}")

        # Applique l'action native pour avancer
        acts = []
        for m in (dry["action"]["messages"]):
            if m.get("cls") == "MoveUnitMessage":
                acts.append({"kind": "move", "unitId": m["unitId"],
                             "to": {"col": m["to"]["col"], "row": m["to"]["row"]}})
            elif m.get("cls") == "ActiveAbilityMessage":
                acts.append({"kind": "ability", "casterId": m["casterId"],
                             "targetId": m.get("targetId"), "abilityType": m["abilityType"]})
            elif m.get("cls") == "FinishUnitTurnMessage":
                acts.append({"kind": "finish", "unitId": m["unitId"]})
        if acts:
            _r(sid, "applyAction", {"runnerId": rid, "actions": acts}, 40)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
