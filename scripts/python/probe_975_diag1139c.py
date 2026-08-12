"""#975 -- ETAGE 3 de la decomposition de `1139` : on SEPARE la prediction du composite.

`ncPlaybookPredict --via evaluate` capture les `ProbableDamageEvent` que le playbook NATIF
CONSTRUIT (`healthDmgMin` / `healthDmgMax` / `appliedHits`), en plus de l'utilite finale du bucket.
On compare donc DEUX etages separement :
   (1) la PREDICTION  -- natif `captured[]` contre le `DamagePredictionResult` du port ;
   (2) le COMPOSITE   -- natif `bucketUtil` contre `1 + calculate_utility_from_damage_event(...)`.
Un ecart au seul etage (2) accuse le composite ; un ecart en (1) accuse les entrees de degat.

ASCII only. PROBE.
"""
from __future__ import annotations

import argparse
import json
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
    print("[1139c] runner=%d" % rid)
    try:
        obs = P975._r(sid, rid, "observeBattle", {}, 60)
        ids = {u.get("visualId"): P975._uid(u) for u in (obs.get("units") or [])}
        cid = int(ids["admecDestroyer"])
        tgt = int(ids["tauCrisis"])
        dv = P975._r(sid, rid, "decisionView", {"allAbilities": True, "maxRank": 32}, 240)
        for (c, r) in ((1, 7), (1, 6)):
            nat = P975._r(sid, rid, "ncPlaybookPredict",
                          {"unitId": cid, "abilityType": ABILITY, "via": "evaluate",
                           "col": c, "row": r}, 240)
            print("\n[1139c] pos=(%d,%d) posSrc=%s abilityState=%s bucketUtil=%s"
                  % (c, r, nat.get("posSrc"), json.dumps(nat.get("abilityState") or {}),
                     nat.get("bucketUtil")))
            for e in (nat.get("captured") or []):
                print("   NATIF event tgt=%s min=%s max=%s hits=%s prob=%s"
                      % (e.get("targetId"), e.get("healthDmgMin"), e.get("healthDmgMax"),
                         e.get("appliedHits"), e.get("probability")))
        nc = P975.port_context(sid, rid, cid, dv)
        from engine.playbook import noncomparable as NC
        pb = NC.PLAYBOOKS[ABILITY]
        for (c, r) in ((1, 7), (1, 6)):
            dp = pb._ability_prediction((c, r), tgt, nc)
            print("\n[1139c] PORT pos=(%d,%d) tgt=%s -> min=%s max=%s hits=%s"
                  % (c, r, tgt,
                     dp.accurate_health_damage.min if dp else None,
                     dp.accurate_health_damage.max if dp else None,
                     dp.applied_hits if dp else None))
            print("   PORT util = %s" % pb.evaluate_non_comparable((c, r), tgt, nc))
        return 0
    finally:
        P975._r(sid, rid, "disposeRunner", {}, 30)
        print("\n[1139c] runner %d dispose" % rid)


if __name__ == "__main__":
    raise SystemExit(main())
