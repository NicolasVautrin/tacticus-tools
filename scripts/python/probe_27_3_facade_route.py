"""probe #27-3 -- la route OFFLINE de SorcerousFacade (1100) est-elle conforme ?

Question binaire : le moteur evalue-t-il `SorcerousFacadePlaybook.
calculate_custom_utility` sur des cibles ENNEMIES, alors que le natif ne
l'evalue JAMAIS que sur un ALLIE Psyker (mesure `abilityTargets`) ?

Construit le ctx moteur depuis un runner vivant et imprime, pour l'unite
demandee, les paires (ability, cible) que `state_bridge` a produites plus la
valeur du terme custom sur chacune.

Usage : python probe_27_3_facade_route.py <runnerId> <unitId> [abilityId]
ASCII only.
"""
from __future__ import annotations

import sys

import engine_validate as EV
import engine.playbook as PB
from engine import weights as W
from engine.ai import context as AICTX


def main() -> int:
    rid = int(sys.argv[1])
    uid = int(sys.argv[2])
    ab_filter = int(sys.argv[3]) if len(sys.argv) > 3 else None
    sid = EV._sid() if hasattr(EV, "_sid") else None
    if sid is None:
        import probe_27_3_live as L
        sid = L.INV._session_id()
    rpc = lambda m, b, t: EV._r(sid, m, b, t)          # noqa: E731
    dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True,
                              "maxRank": 32}, 180)
    mov = rpc("aiMovableTiles", {"runnerId": rid}, 60)
    mov_by_unit = {u.get("unitId"): u for u in (mov.get("units") or [])}
    wt = W.load()
    from engine.playbook import scene as _scene
    predictor = _scene.build_predictor(rpc, rid)
    ctx = AICTX.build(rpc, rid, dv, mov_by_unit, uid, wt, predictor)
    plan = (ctx.plans.get(uid) or {})
    seen = set()
    mp = ctx.me.get("pos") or {}
    here = (mp.get("col"), mp.get("row"))
    print("unit=%s tuile=%s equipe=%s" % (uid, here, ctx.me.get("team")))
    team_by_id = {u.get("id"): u.get("team") for u in (ctx.units or [])}
    for ev in (plan.get("evals") or []):
        ab = ev.get("abilityId")
        tgt = ev.get("targetId")
        if ab_filter is not None and ab != ab_filter:
            continue
        if (ab, tgt) in seen:
            continue
        seen.add((ab, tgt))
        pb = PB.get_playbook_or_default(ab)
        try:
            cu = pb.calculate_custom_utility(ctx, here, tgt, ab)
        except Exception as exc:                        # noqa: BLE001
            cu = "ERR %s" % exc
        try:
            cand = pb.calculate_action_utility(ctx, here, tgt, ab)
            ufull = None if cand is None else cand.get("u_full")
        except Exception as exc:                        # noqa: BLE001
            ufull = "ERR %s" % exc
        print("  ability=%-6s cible=%-5s equipe_cible=%-4s playbook=%-28s"
              " u_full=%-20r custom=%s"
              % (ab, tgt, team_by_id.get(tgt), type(pb).__name__, ufull, cu))
    if not seen:
        print("  (aucune paire produite)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
