"""#996-r1 -- diagnostic ETAGE PAR ETAGE du mouvement de 1053 (candidates, ctx de feuille, score).

Le mouvement est un empilement : `ComputerMovementActionOperation` -> `build_from_state(max_distance)`
-> `movement_action_with_override` -> `get_movement_utility` -> feuille 53. Quand la tuile d'arrivee
diverge, il faut savoir a QUEL etage -- jamais fitter le score final.

Usage : python probe_996r1_move_diag.py --state-file <ABSOLU propre>
ASCII only.
"""
from __future__ import annotations

import argparse
import sys

import probe_996r1_devout_push as P


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--state-file", required=True)
    ap.add_argument("--keep", action="store_true")
    a = ap.parse_args()
    sid = P._sid()
    rid = P._build(sid, a.state_file, P.GEOMETRIE, p_places={P.PORTEUR: P.CASTER_TILE})
    try:
        cap = P._capture(sid, rid)
        caster = P._by_vis(cap, P.PORTEUR_VIS)
        st = P._state(cap)
        uid = int(caster["id"])

        from engine.ai.state_bridge import build_from_state
        from engine.ai.action_generators import movement_candidate_positions
        from engine.utilities.tile import tile_leaf_ctx, utilities_database
        import engine.ai.utilities as AU
        from engine.utilities.utility_type import UtilityType

        ctx = build_from_state(st, uid, max_distance=1)
        print("[diag] uid=%s origin=%s wt=%s" % (uid, getattr(ctx, "origin", None),
                                                 type(getattr(ctx, "wt", None)).__name__))
        leaf = utilities_database(int(UtilityType.DevoutPush_AdjacentRangedEnemies))
        print("[diag] feuille 53 au registre : %r" % (type(leaf).__name__ if leaf else None,))
        lc = tile_leaf_ctx(ctx)
        print("[diag] leaf_ctx uid=%r self_pos=%r n_enemy=%d" %
              (lc.get("uid"), lc.get("self_pos"), len(lc.get("enemy_units") or ())))
        for e in (lc.get("enemy_units") or ()):
            print("[diag]    ennemi vis=%-18s pos=%s" % (e.get("vis"), e.get("pos")))
        print("[diag] elev_by_pos=%d neigh_by_pos=%d"
              % (len(lc.get("elev_by_pos") or {}), len(lc.get("neigh_by_pos") or {})))
        cands = movement_candidate_positions(ctx)
        print("[diag] candidates (%d) :" % len(cands))
        for c in cands:
            p = (c["col"], c["row"])
            u = AU.get_movement_utility(ctx, p, int(UtilityType.DevoutPush_AdjacentRangedEnemies))
            direct = leaf.evaluate(p, None, lc, ctx.wt) if leaf is not None else None
            print("[diag]    %s  get_movement_utility=%s  feuille.evaluate=%s" % (p, u, direct))
        wt = getattr(ctx, "wt", None)
        if wt is not None:
            print("[diag] poids BC : ranged=%r melee=%r"
                  % (wt.sub("DevoutPush_AdjacentRangedEnemies", "DEVOUTPUSH_AdjacentRangedEnemy"),
                     wt.sub("DevoutPush_AdjacentRangedEnemies", "DEVOUTPUSH_AdjacentMeleeEnemy")))
    finally:
        if not a.keep:
            P._dispose(sid, rid)
    return 0


if __name__ == "__main__":
    sys.exit(main())
