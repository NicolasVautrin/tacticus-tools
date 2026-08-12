"""#975 -- DIAGNOSTIC par etage des trois faces qui divergent (1139 utilite, 1116/1087 muets).

Decompose, position par position et cible par cible, ce que le PORT calcule, et affiche a cote le
substrat qu'il a recu (`abilityTargets`, plan, epos). ASCII only. PROBE : il imprime, il n'assertionne pas.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PYDIR))

from rl_collect_batch import _resolve_session, _rpc     # noqa: E402
import probe_975_kit_decision_faces as P975             # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--state-file", required=True)
    ap.add_argument("--seed-bc", required=True)
    ap.add_argument("--seed", type=int, default=777)
    ap.add_argument("--montage", default="A")
    a = ap.parse_args()
    sid = _resolve_session()
    sf = Path(a.state_file)
    rid = P975.build(sf, a.seed, a.montage, Path(a.seed_bc))
    print("[diag] runner=%d" % rid)
    try:
        obs = P975._r(sid, rid, "observeBattle", {}, 60)
        by_vis = {}
        for u in (obs.get("units") or []):
            by_vis.setdefault(u.get("visualId"), []).append(u)
        ids = {u.get("visualId"): P975._uid(u) for u in (obs.get("units") or [])}
        pos_by_id = {P975._uid(u): (u.get("col"), u.get("row"))
                     for u in (obs.get("units") or [])}
        print("[diag] ids=%s" % json.dumps({k: v for k, v in ids.items()}, ensure_ascii=True))
        dv = P975._r(sid, rid, "decisionView", {"allAbilities": True, "maxRank": 32}, 240)

        # ---------------- 1139 : utilite par (position, cible) ----------------
        cid = int(ids["admecDestroyer"])
        nc = P975.port_context(sid, rid, cid, dv)
        from engine.playbook import noncomparable as NC
        pb = NC.PLAYBOOKS[1139]
        print("\n=== 1139 SentinelDirectives : utilite PORT par (position, cible) ===")
        pairs = []
        for ev in (nc.plan.get("evals") or []):
            if ev.get("abilityId") != 1139 or not ev.get("rankCount"):
                continue
            rset = {(rk.get("col"), rk.get("row")) for rk in (ev.get("ranked") or [])
                    if rk.get("col") is not None}
            if rset:
                pairs.append((ev.get("targetId"), pb.eligible_positions(nc, ev.get("targetId"),
                                                                       rset, ev)))
        print("  paires (cible, #positions) = %s"
              % [(t, len(s), pos_by_id.get(t)) for t, s in pairs])
        for Pp in nc.reach_nc:
            row = []
            for tgt, rset in pairs:
                if Pp not in rset:
                    continue
                u = pb.evaluate_non_comparable(Pp, tgt, nc)
                row.append((tgt, None if u is None else round(u, 4)))
            if row:
                print("   pos=%s -> %s" % (Pp, row))
        dp = pb._ability_prediction(nc.origin, pairs[0][0] if pairs else None, nc)
        print("  prediction ORIGINE vs cible %s : %s" % (pairs[0][0] if pairs else None, dp))

        # ---------------- 1116 : substrat d'aims ----------------
        cid = int(ids["admecDominus"])
        nc = P975.port_context(sid, rid, cid, dv)
        at = nc.ability_targets(cid, 1116) or {}
        print("\n=== 1116 RadBombardment : substrat ===")
        for u in (at.get("units") or []):
            if u.get("unitId") != cid:
                continue
            for ab in (u.get("abilities") or []):
                if ab.get("abilityId") != 1116:
                    continue
                print("  fromHere=%s" % [(t.get("kind"), (t.get("tile") or {}).get("col"),
                                          (t.get("tile") or {}).get("row"))
                                         for t in (ab.get("fromHere") or [])])
                print("  targets =%s" % [(t.get("kind"), (t.get("tile") or {}).get("col"),
                                          (t.get("tile") or {}).get("row"))
                                         for t in (ab.get("targets") or [])])
        from engine.playbook.noncomparable import rad_bombardment as RB
        n = RB.affected_tile_amount(nc)
        print("  origin=%s n_tiles=%s reach=%s" % (nc.origin, n, nc.reach_nc))
        print("  epos=%s" % nc.epos)
        for T in [(2, 3), (1, 4), (2, 4)]:
            for src in (nc.origin, (1, 4)):
                line = RB.affected_tiles(nc, src, T, n)
                print("   src=%s aim=%s -> line=%s enemies=%d"
                      % (src, T, line, sum(1 for t in line if t in set(nc.epos))))

        # ---------------- 1087 : substrat d'aims + gate ----------------
        cid = int(ids["tauShadowsun"])
        nc = P975.port_context(sid, rid, cid, dv)
        at = nc.ability_targets(cid, 1087) or {}
        print("\n=== 1087 ExemplarOfTheKauyon : substrat ===")
        found = False
        for u in (at.get("units") or []):
            if u.get("unitId") != cid:
                continue
            for ab in (u.get("abilities") or []):
                if ab.get("abilityId") != 1087:
                    continue
                found = True
                fh = [((t.get("tile") or {}).get("col"), (t.get("tile") or {}).get("row"))
                      for t in (ab.get("fromHere") or []) if t.get("kind") == "tile"]
                tg = [((t.get("tile") or {}).get("col"), (t.get("tile") or {}).get("row"))
                      for t in (ab.get("targets") or []) if t.get("kind") == "tile"]
                print("  usable=%s fromHereCount=%s" % (ab.get("usable"), ab.get("fromHereCount")))
                print("  fromHere(tile)=%s" % fh)
                print("  targets(tile)=%s" % tg)
                from engine.playbook.noncomparable import exemplar_of_the_kauyon as EK
                print("  visual=%s" % EK._visual_id_of(nc, cid))
                for T in (fh or tg)[:12]:
                    print("   aim=%s has_enemy_in_range=%s tileId=%s"
                          % (T, EK.has_enemy_in_range(nc, T),
                             (nc.tile_id_by_pos or {}).get(T)))
        if not found:
            print("  AUCUNE entree abilityTargets pour 1087 -- keys=%s"
                  % [(u.get("unitId"), [ab.get("abilityId") for ab in (u.get("abilities") or [])])
                     for u in (at.get("units") or [])])
        print("  epos=%s" % nc.epos)
        return 0
    finally:
        P975._r(sid, rid, "disposeRunner", {}, 30)
        print("\n[diag] runner %d dispose" % rid)


if __name__ == "__main__":
    raise SystemExit(main())
