"""#975 -- pourquoi le DRIVER n'atteint-il pas 1139 / 1116 / 1087 ?

`generate_candidates` rend un candidat, mais `engine_decide` rend un `move` : la feuille est
INSCRITE et INERTE. On remonte la chaine du driver etage par etage -- abilities publiees pour
l'unite, `usable` / cooldown, filtre `can_use_ability`, tier de priorite, et enfin ce que
`NonComparableGenerator.generate` rend reellement.

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

CARRIER_OF = {1139: "admecDestroyer", 1116: "admecDominus", 1206: "votanIronmaster",
              1221: "votanBeserk", 1087: "tauShadowsun"}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--state-file", required=True)
    ap.add_argument("--seed-bc", required=True)
    ap.add_argument("--seed", type=int, default=777)
    ap.add_argument("--montage", default="B")
    a = ap.parse_args()
    sid = _resolve_session()
    rid = P975.build(Path(a.state_file), a.seed, a.montage, Path(a.seed_bc))
    print("[reach] runner=%d" % rid)
    try:
        obs = P975._r(sid, rid, "observeBattle", {}, 60)
        ids = {u.get("visualId"): P975._uid(u) for u in (obs.get("units") or [])}
        dv = P975._r(sid, rid, "decisionView", {"allAbilities": True, "maxRank": 32}, 240)
        from engine import battle_query as bq
        from engine.ai import context as AICTX
        from engine.ai import action_generators as AG
        from engine.playbook import noncomparable as NC
        from engine.playbook import scene as _scene
        from engine import weights as W
        mov = P975._r(sid, rid, "aiMovableTiles", {}, 60)
        mov_by_unit = {u.get("unitId"): u for u in ((mov or {}).get("units") or [])}

        for aid, vis in CARRIER_OF.items():
            cid = int(ids[vis])
            rpc2 = lambda m, b, t=60: P975._r(sid, rid, m, b, t)          # noqa: E731
            ctx = AICTX.build(rpc2, rid, dv, mov_by_unit, cid, W.load(),
                              _scene.build_predictor(rpc2, rid))
            me = ctx.me or {}
            abs_ = me.get("abilities") or []
            print("\n=== %d [%s] u%d ===" % (aid, vis, cid))
            print("  ctx.me abilities = %s"
                  % json.dumps([{k: v for k, v in ab.items()
                                 if k in ("id", "name", "kind", "usable", "cooldown",
                                          "remainingCooldown", "disabled", "ammo")}
                                for ab in abs_], ensure_ascii=True)[:700])
            mine = [ab for ab in abs_ if ab.get("id") == aid]
            print("  entree de CETTE ability : %s" % (mine or "ABSENTE"))
            for ab in mine:
                print("   can_use_ability=%s can_currently_be_used=%s"
                      % (bq.can_use_ability(me, ab), bq.can_currently_be_used(ab)))
            print("  is_noncomp(%d)=%s  playbook=%s  PRIORITY=%s"
                  % (aid, NC.is_noncomp(aid), type(NC.PLAYBOOKS.get(aid)).__name__,
                     getattr(NC.PLAYBOOKS.get(aid), "PRIORITY", None)))
            try:
                gen = AG.NonComparableGenerator()
                out = gen.generate(ctx)
                print("  NonComparableGenerator.generate -> %s" % (str(out)[:300]))
            except Exception as e:                                     # noqa: BLE001
                import traceback
                print("  generate EXCEPTION %s" % e)
                traceback.print_exc()
        return 0
    finally:
        P975._r(sid, rid, "disposeRunner", {}, 30)
        print("\n[reach] runner %d dispose" % rid)


if __name__ == "__main__":
    raise SystemExit(main())
