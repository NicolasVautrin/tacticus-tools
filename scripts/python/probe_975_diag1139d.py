"""#975 -- ETAGE 4 : l'ecart de PREDICTION de `1139` est-il PROPRE a la face DECISION ?

Le plan natif (`decisionView.plans[].evals[].ranked[].dmgMin/dmgMax`) publie les bornes que le
NATIF calcule pour la MEME ability, par une voie INDEPENDANTE du playbook
(`computeAttackPlans` -> `AttackQuery$$GetBestTileToAttackFrom` -> prediction). Si le plan concorde
avec l'oracle NC et diverge du port, l'ecart est dans le FOYER DE PREDICTION du port -- donc en
AMONT de la face DECISION, et hors du perimetre de cette tranche.

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


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--state-file", required=True)
    ap.add_argument("--seed-bc", required=True)
    ap.add_argument("--seed", type=int, default=777)
    a = ap.parse_args()
    sid = _resolve_session()
    rid = P975.build(Path(a.state_file), a.seed, "A", Path(a.seed_bc))
    print("[1139d] runner=%d" % rid)
    try:
        obs = P975._r(sid, rid, "observeBattle", {}, 60)
        ids = {u.get("visualId"): P975._uid(u) for u in (obs.get("units") or [])}
        cid = int(ids["admecDestroyer"])
        dv = P975._r(sid, rid, "decisionView", {"allAbilities": True, "maxRank": 32}, 240)
        nc0 = P975.port_context(sid, rid, cid, dv)
        plan = nc0.plan or {}
        print("[1139d] PLAN NATIF de u%d (bornes publiees par computeAttackPlans) :" % cid)
        for ev in (plan.get("evals") or []):
            if ev.get("abilityId") != 1139:
                continue
            for rk in (ev.get("ranked") or [])[:6]:
                print("   tgt=%s tile=(%s,%s) dmgMin=%s dmgMax=%s killSure=%s"
                      % (ev.get("targetId"), rk.get("col"), rk.get("row"),
                         rk.get("dmgMin"), rk.get("dmgMax"), rk.get("killSure")))
        nc = P975.port_context(sid, rid, cid, dv)
        from engine.playbook import noncomparable as NC
        pb = NC.PLAYBOOKS[1139]
        print("\n[1139d] PORT (memes couples) :")
        for ev in (plan.get("evals") or []):
            if ev.get("abilityId") != 1139:
                continue
            for rk in (ev.get("ranked") or [])[:6]:
                pos = (rk.get("col"), rk.get("row"))
                dp = pb._ability_prediction(pos, ev.get("targetId"), nc)
                print("   tgt=%s tile=%s -> min=%s max=%s hits=%s"
                      % (ev.get("targetId"), pos,
                         dp.accurate_health_damage.min if dp else None,
                         dp.accurate_health_damage.max if dp else None,
                         dp.applied_hits if dp else None))
        return 0
    finally:
        P975._r(sid, rid, "disposeRunner", {}, 30)
        print("\n[1139d] runner %d dispose" % rid)


if __name__ == "__main__":
    raise SystemExit(main())
