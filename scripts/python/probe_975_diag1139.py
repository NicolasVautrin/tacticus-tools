"""#975 -- DECOMPOSITION PAR ETAGE de l'ecart d'utilite de `1139 SentinelDirectives`.

Le port et le natif s'accordent sur la POSITION d'argmax et sur la structure, mais pas sur la
VALEUR. On ne fitte pas un scalaire : on fait varier UN etage a la fois (base de degat, nombre de
coups, profil, plancher) et on regarde lequel reproduit l'oracle, position par position.

ASCII only. PROBE : il imprime.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PYDIR))

from rl_collect_batch import _resolve_session          # noqa: E402
import probe_975_kit_decision_faces as P975            # noqa: E402

ABILITY = 1139
NAME = "SentinelDirectives"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--state-file", required=True)
    ap.add_argument("--seed-bc", required=True)
    ap.add_argument("--seed", type=int, default=777)
    a = ap.parse_args()
    sid = _resolve_session()
    rid = P975.build(Path(a.state_file), a.seed, "A", Path(a.seed_bc))
    print("[1139] runner=%d" % rid)
    try:
        obs = P975._r(sid, rid, "observeBattle", {}, 60)
        ids = {u.get("visualId"): P975._uid(u) for u in (obs.get("units") or [])}
        hp = {P975._uid(u): u.get("hp") for u in (obs.get("units") or [])}
        cid = int(ids["admecDestroyer"])
        dv = P975._r(sid, rid, "decisionView", {"allAbilities": True, "maxRank": 32}, 240)
        nat = P975._r(sid, rid, "ncEvaluate",
                      {"unitId": cid, "abilityType": ABILITY, "sweep": True}, 240)
        nat_by_pos = {tuple(p["pos"]): p.get("util") for p in (nat.get("positions") or [])}
        print("[1139] natif par position : %s"
              % {k: (None if v is None else round(v, 4)) for k, v in nat_by_pos.items()})

        nc = P975.port_context(sid, rid, cid, dv)
        from engine.playbook import noncomparable as NC
        from engine.entities.abilities.ability_configuration import AbilityConfiguration
        from engine.entities.abilities.active_ability import active_ability_for
        from engine.playbook.prediction.abilities import generate_multi_hit_attack_prediction
        from engine.playbook.probable_damage_event import (ProbableDamageEvent,
                                                           calculate_utility_from_damage_event)
        import gameconfig as GC

        pb = NC.PLAYBOOKS[ABILITY]
        ctx0 = nc.scene.ctx(cid)
        cfg = AbilityConfiguration.from_gameconfig(NAME, GC.ability(NAME))
        ab = active_ability_for(NAME, ABILITY, ctx0, cfg,
                                ability_state=nc.scene.ability_state(cid, ABILITY))
        lvl, mult = ab.level, ab.multiplier
        minv = cfg.get_variable_for_level("minDmg", lvl, 0, mult)
        maxv = cfg.get_variable_for_level("maxDmg", lvl, 0, mult)
        consts = cfg.constants or {}
        print("[1139] level=%s mult=%s minDmg=%s maxDmg=%s get_damage=%s consts=%s"
              % (lvl, mult, minv, maxv, ab.get_damage(), consts))

        pairs = []
        for ev in (nc.plan.get("evals") or []):
            if ev.get("abilityId") != ABILITY or not ev.get("rankCount"):
                continue
            rset = {(rk.get("col"), rk.get("row")) for rk in (ev.get("ranked") or [])
                    if rk.get("col") is not None}
            if rset:
                pairs.append((ev.get("targetId"),
                              pb.eligible_positions(nc, ev.get("targetId"), rset, ev)))

        variants = {
            "minDmg  h=nrOfHits": dict(base_override=minv, hits_override=1,
                                       profile_override=consts.get("damageProfile")),
            "maxDmg  h=nrOfHits": dict(base_override=maxv, hits_override=1,
                                       profile_override=consts.get("damageProfile")),
            "moyenne h=nrOfHits": dict(base_override=ab.get_damage(), hits_override=1,
                                       profile_override=consts.get("damageProfile")),
            "GENERIQUE (aucun override)": dict(),
            "minDmg  h=2": dict(base_override=minv, hits_override=2,
                                profile_override=consts.get("damageProfile")),
            "minDmg  profil None": dict(base_override=minv, hits_override=1,
                                        profile_override="None"),
        }
        for label, kw in variants.items():
            out = {}
            for P in nc.reach_nc:
                best = None
                for tgt, rset in pairs:
                    if P not in rset:
                        continue
                    dp = generate_multi_hit_attack_prediction(nc.scene, cid, tgt, ABILITY, NAME,
                                                              attack_pos=P, **kw)
                    if dp is None:
                        continue
                    u = 1.0 + calculate_utility_from_damage_event(
                        ProbableDamageEvent(target=tgt, prediction=dp), nc.wt,
                        nc.scene.hpmax(tgt))
                    if best is None or u > best[1]:
                        best = (tgt, u)
                if best is not None:
                    out[P] = (best[0], round(best[1], 4))
            print("\n--- variante %s" % label)
            for P, (tgt, u) in out.items():
                nv = nat_by_pos.get(P)
                mark = "  <== EGAL" if (nv is not None and abs(nv - u) < 0.01) else ""
                print("    pos=%-8s port=%-10s (tgt %s, hp %s)  natif=%-10s%s"
                      % (P, u, tgt, hp.get(tgt),
                         "None" if nv is None else round(nv, 4), mark))
        return 0
    finally:
        P975._r(sid, rid, "disposeRunner", {}, 30)
        print("\n[1139] runner %d dispose" % rid)


if __name__ == "__main__":
    raise SystemExit(main())
