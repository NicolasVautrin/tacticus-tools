"""probe #27-3 -- A/B de DECISION moteur avec et sans un terme custom.

Compare, pour une unite d'un runner vivant :
  - l'action proposee par l'IA NATIVE (`aiDryRunAllUnits`, read-only) ;
  - l'action du MOTEUR telle quelle ;
  - l'action du MOTEUR avec le terme custom de l'ability visee FORCE a 0.

C'est le test de NECESSITE d'un terme : si les deux bras moteur different, le
terme change le resultat observable ; s'ils sont identiques, la mesure ne peut
pas contredire le port (regime non discriminant -> changer le montage).

Usage : python probe_27_3_decide_ab.py <runnerId> <unitId> <abilityId>
ASCII only.
"""
from __future__ import annotations

import json
import sys

import engine_validate as EV
import engine.playbook as PB
from engine import weights as W


def _native(sid, rid, uid):
    r = EV._r(sid, "aiDryRunAllUnits", {"runnerId": rid}, 120)
    for u in (r.get("units") or []):
        if u.get("unitId") == uid:
            return u
    return r


def main() -> int:
    rid, uid, ab = int(sys.argv[1]), int(sys.argv[2]), int(sys.argv[3])
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

    nat = _native(sid, rid, uid)
    print("NATIF   : %s" % json.dumps(nat)[:600])

    eng_a = EV.engine_decide(sid, rid, dv, mov_by_unit, uid, wt, predictor)
    print("MOTEUR  : %s" % json.dumps(eng_a, default=str)[:400])

    pb = PB.REGISTRY.get(ab)
    if pb is None:
        print("ability %s non enregistree -> pas de bras 'custom=0'" % ab)
        return 0
    orig = type(pb).calculate_custom_utility
    type(pb).calculate_custom_utility = (
        lambda self, ctx, tile, target, ability_id: 0.0)
    try:
        eng_b = EV.engine_decide(sid, rid, dv, mov_by_unit, uid, wt, predictor)
    finally:
        type(pb).calculate_custom_utility = orig
    print("MOTEUR0 : %s" % json.dumps(eng_b, default=str)[:400])
    print("DIFF    : %s" % ("OUI (terme NECESSAIRE)" if eng_a != eng_b
                            else "non (regime NON discriminant)"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
