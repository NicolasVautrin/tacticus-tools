"""#975 -- ETAGE 2 de la decomposition de `1139` : quelle ENTREE de degat reproduit l'oracle ?

L'utilite native d'une position ou UNE SEULE cible est eligible identifie sans ambiguite le couple
(cible, utilite). On balaie alors `base_override` et on cherche la valeur qui reproduit l'oracle --
puis on REGARDE ce que cette valeur est dans le gameconfig. C'est une mesure d'ETAGE (quelle entree
donne cette sortie), pas un fit : si la valeur trouvee ne correspond a AUCUNE lecture du decompile,
le verdict est << non explique >>, pas << calibre >>.

ASCII only. PROBE.
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
    print("[1139b] runner=%d" % rid)
    try:
        obs = P975._r(sid, rid, "observeBattle", {}, 60)
        ids = {u.get("visualId"): P975._uid(u) for u in (obs.get("units") or [])}
        cid = int(ids["admecDestroyer"])
        tgt = int(ids["tauCrisis"])          # la SEULE cible eligible depuis (1,7)/(0,6)/(1,8)
        POSN = (1, 7)
        dv = P975._r(sid, rid, "decisionView", {"allAbilities": True, "maxRank": 32}, 240)
        nat = P975._r(sid, rid, "ncEvaluate",
                      {"unitId": cid, "abilityType": ABILITY, "sweep": True}, 240)
        target_util = None
        for p in (nat.get("positions") or []):
            if tuple(p.get("pos") or ()) == POSN:
                target_util = p.get("util")
        print("[1139b] oracle a %s = %s (cible unique %s)" % (POSN, target_util, tgt))

        nc = P975.port_context(sid, rid, cid, dv)
        from engine.entities.abilities.ability_configuration import AbilityConfiguration
        from engine.entities.abilities.active_ability import active_ability_for
        from engine.playbook.prediction.abilities import generate_multi_hit_attack_prediction
        from engine.playbook.probable_damage_event import (ProbableDamageEvent,
                                                           calculate_utility_from_damage_event)
        import gameconfig as GC
        ctx0 = nc.scene.ctx(cid)
        cfg = AbilityConfiguration.from_gameconfig(NAME, GC.ability(NAME))
        ab = active_ability_for(NAME, ABILITY, ctx0, cfg,
                                ability_state=nc.scene.ability_state(cid, ABILITY))
        lvl, mult = ab.level, ab.multiplier
        consts = cfg.constants or {}
        prof = consts.get("damageProfile")

        def util_for(base, hits=1, profile=prof):
            dp = generate_multi_hit_attack_prediction(nc.scene, cid, tgt, ABILITY, NAME,
                                                      attack_pos=POSN, base_override=base,
                                                      hits_override=hits, profile_override=profile)
            if dp is None:
                return None, None
            u = 1.0 + calculate_utility_from_damage_event(
                ProbableDamageEvent(target=tgt, prediction=dp), nc.wt, nc.scene.hpmax(tgt))
            return u, dp

        print("[1139b] level=%s mult=%s" % (lvl, mult))
        for nm in ("minDmg", "maxDmg"):
            for m in (None, 100, mult):
                try:
                    v = cfg.get_variable_for_level(nm, lvl, 0, m)
                except Exception as e:                                   # noqa: BLE001
                    v = "ERR %s" % e
                print("   %s(lvl=%s, mult=%s) = %s" % (nm, lvl, m, v))

        lo, hi = 1000.0, 20000.0
        for _ in range(60):                     # dichotomie sur une utilite CROISSANTE en base
            mid = (lo + hi) / 2.0
            u, _dp = util_for(mid)
            if u is None:
                break
            if u < target_util:
                lo = mid
            else:
                hi = mid
        base_star, _ = (lo + hi) / 2.0, None
        u_star, dp_star = util_for(base_star)
        print("[1139b] base* qui reproduit l'oracle = %.3f  -> util %.6f (cible %.6f)"
              % (base_star, u_star, target_util))
        print("[1139b] prediction a base* : %s" % (dp_star,))
        minv = cfg.get_variable_for_level("minDmg", lvl, 0, mult)
        maxv = cfg.get_variable_for_level("maxDmg", lvl, 0, mult)
        print("[1139b] repere : minDmg=%s maxDmg=%s moyenne=%s  base*/minDmg=%.4f "
              "base*/maxDmg=%.4f base*/moyenne=%.4f"
              % (minv, maxv, ab.get_damage(), base_star / minv, base_star / maxv,
                 base_star / ab.get_damage()))
        for h in (1, 2, 3):
            u, _ = util_for(minv, hits=h)
            print("   minDmg h=%d -> %s" % (h, None if u is None else round(u, 4)))
        for pr in ("Physical", "None", "Power", "Piercing"):
            u, _ = util_for(minv, profile=pr)
            print("   minDmg profil=%-9s -> %s" % (pr, None if u is None else round(u, 4)))
        return 0
    finally:
        P975._r(sid, rid, "disposeRunner", {}, 30)
        print("\n[1139b] runner %d dispose" % rid)


if __name__ == "__main__":
    raise SystemExit(main())
