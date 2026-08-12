"""#975 -- CONTRE-EPREUVES : chaque mutation doit CHANGER la sortie, sinon elle est MUETTE.

Deux familles :

  1. REACHABILITY (le vice « enregistre ET inerte ») -- on retire le playbook de `PLAYBOOKS` et on
     rejoue le chemin de PRODUCTION `engine_validate.engine_decide` sur le porteur. Si la decision
     ne bouge pas, la feuille n'etait PAS atteinte et son inscription ne prouve rien.

  2. FIDELITE -- on mute UN terme du port a la fois (le gate `1 < Count` de 1221, le `MIN_UTILITY`
     de 1116, le double gate de 1206, le predicat de 1087, le plancher `+1` de 1139) et on verifie
     que `generate_candidates` / `should_evaluate` CHANGE. Une mutation qui ne change rien est
     rapportee `MUETTE` -- c'est un trou de banc, pas un succes.

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

CARRIER_OF = {1139: "admecDestroyer", 1116: "admecDominus", 1206: "votanIronmaster",
              1221: "votanBeserk", 1087: "tauShadowsun"}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--state-file", required=True)
    ap.add_argument("--seed-bc", required=True)
    ap.add_argument("--seed", type=int, default=777)
    ap.add_argument("--montage", default="B")
    ap.add_argument("--advance-turns", type=int, default=0,
                    help="tours a passer avant de mesurer -- 1087 porte `initialCooldownTurns: 1`, "
                         "donc le NATIF ne la publie pas comme utilisable au 1er tour")
    a = ap.parse_args()
    sid = _resolve_session()
    rid = P975.build(Path(a.state_file), a.seed, a.montage, Path(a.seed_bc))
    print("[mut] montage=%s runner=%d" % (a.montage, rid))
    for _ in range(max(0, a.advance_turns)):
        for _side in (1, 2):
            P975._r(sid, rid, "applyAction", {"action": {"kind": "endturn"}}, 60)
    muettes, mordantes = [], []
    try:
        obs = P975._r(sid, rid, "observeBattle", {}, 60)
        ids = {u.get("visualId"): P975._uid(u) for u in (obs.get("units") or [])}
        dv = P975._r(sid, rid, "decisionView", {"allAbilities": True, "maxRank": 32}, 240)
        from engine.playbook import noncomparable as NC
        import engine_validate as EV
        from engine import weights as W

        ctxs = {aid: P975.port_context(sid, rid, int(ids[v]), dv)
                for aid, v in CARRIER_OF.items()}
        base = {}
        for aid, nc in ctxs.items():
            pb = NC.PLAYBOOKS[aid]
            base[aid] = (pb.should_evaluate(nc), pb.generate_candidates(nc))
            print("  BASE %d : gate=%s cands=%s" % (aid, base[aid][0], base[aid][1]))

        def check(label, aid, got):
            ref = base[aid][1]
            if got == ref:
                muettes.append(label)
                print("  MUETTE  %-52s -> %s (inchange)" % (label, got))
            else:
                mordantes.append(label)
                print("  MORDANTE %-51s -> %s" % (label, got))

        # ---- 1. REACHABILITY : retirer du registre change-t-il la DECISION de production ? ----
        mov = P975._r(sid, rid, "aiMovableTiles", {}, 60)
        mov_by_unit = {u.get("unitId"): u for u in ((mov or {}).get("units") or [])}
        wt = W.load()
        # ⚠ LE `predictor` EST OBLIGATOIRE, et l'oublier FABRIQUE un faux « inerte » : sans lui
        # `ctx.scene` est None, donc `1139._ability_prediction` rend None et `1116
        # .affected_tile_amount` retombe sur son plancher -- les deux playbooks s'abstiennent pour
        # une raison qui n'a rien a voir avec leur inscription. Mesure #975 : 3 faux INERTE sur 5
        # au premier passage de ce probe.
        from engine.playbook import scene as _scene
        rpc2 = lambda m, b, t=60: P975._r(sid, rid, m, b, t)              # noqa: E731
        predictor = _scene.build_predictor(rpc2, rid)
        print("\n[mut] REACHABILITY (chemin de PRODUCTION engine_decide, predictor CABLE)")
        for aid, v in CARRIER_OF.items():
            cid = int(ids[v])
            with_pb = EV.engine_decide(sid, rid, dv, mov_by_unit, cid, wt, predictor)
            saved = NC.PLAYBOOKS.pop(aid)
            try:
                without = EV.engine_decide(sid, rid, dv, mov_by_unit, cid, wt, predictor)
            finally:
                NC.PLAYBOOKS[aid] = saved
            same = (with_pb == without)
            (muettes if same else mordantes).append("reachability %d" % aid)
            print("  %-9s %d [%s] : avec=%s" % ("INERTE" if same else "ATTEINTE", aid, v,
                                                str(with_pb)[:130]))
            print("                    sans=%s" % str(without)[:130])

        # ---- 2. FIDELITE, un terme a la fois ----
        print("\n[mut] FIDELITE")
        pb = NC.PLAYBOOKS[1221]
        old = pb.__class__.min_eligible_targets
        pb.__class__.min_eligible_targets = lambda self: 1
        try:
            check("1221 gate `1 < Count` neutralise (2 -> 1)", 1221,
                  pb.generate_candidates(ctxs[1221]))
        finally:
            pb.__class__.min_eligible_targets = old

        pb = NC.PLAYBOOKS[1116]
        old_min = pb.MIN_UTILITY
        pb.__class__.MIN_UTILITY = 3.0
        try:
            check("1116 MIN_UTILITY 2 -> 3 (le cctor est le seul a valoir 2)", 1116,
                  pb.generate_candidates(ctxs[1116]))
        finally:
            pb.__class__.MIN_UTILITY = old_min

        from engine.playbook.noncomparable import rad_bombardment as RB
        old_amt = RB.affected_tile_amount
        RB.affected_tile_amount = lambda ctx: 1          # ligne rabattue a `Get(1)`
        try:
            check("1116 AffectedTileAmount rabattu a 1 (RoundsStarted ignore)", 1116,
                  NC.PLAYBOOKS[1116].generate_candidates(ctxs[1116]))
        finally:
            RB.affected_tile_amount = old_amt

        from engine.playbook.noncomparable import graviton_rifle as GR
        old_rep = GR.has_any_repair_target
        GR.has_any_repair_target = lambda ctx: True
        try:
            g = NC.PLAYBOOKS[1206].should_evaluate(ctxs[1206])
            if g == base[1206][0]:
                muettes.append("1206 HasAnyRepairTarget force a True")
                print("  MUETTE  1206 HasAnyRepairTarget force a True -> gate=%s (inchange)" % g)
            else:
                mordantes.append("1206 HasAnyRepairTarget force a True")
                print("  MORDANTE 1206 HasAnyRepairTarget force a True -> gate=%s" % g)
        finally:
            GR.has_any_repair_target = old_rep

        from engine.playbook.noncomparable import exemplar_of_the_kauyon as EK
        old_her = EK.has_enemy_in_range
        EK.has_enemy_in_range = lambda ctx, tile: False
        try:
            check("1087 HasEnemyInRange force a False", 1087,
                  NC.PLAYBOOKS[1087].generate_candidates(ctxs[1087]))
        finally:
            EK.has_enemy_in_range = old_her

        pb = NC.PLAYBOOKS[1139]
        old_b = pb.__class__._BASE_UTILITY
        pb.__class__._BASE_UTILITY = 0.0
        try:
            check("1139 plancher `Fix64(1)` retire (1.0 -> 0.0)", 1139,
                  pb.generate_candidates(ctxs[1139]))
        finally:
            pb.__class__._BASE_UTILITY = old_b

        print("\n[mut] BILAN : %d mordante(s), %d MUETTE(s)" % (len(mordantes), len(muettes)))
        for m in muettes:
            print("   MUETTE : %s" % m)
        return 0
    finally:
        P975._r(sid, rid, "disposeRunner", {}, 30)
        print("[mut] runner %d dispose" % rid)


if __name__ == "__main__":
    raise SystemExit(main())
