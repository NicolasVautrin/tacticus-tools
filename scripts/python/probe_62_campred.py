#!/usr/bin/env python
"""Probe #62 — agreement PREDICTION per-tuile : cible Camouflage posee sur DryBush.

Scenario (MC1_67) : p-units = admecRuststalker (porteur Camouflage 1037, drive sur la tuile
DryBush (3,2)) + bloodSanguinary (cible CONTROLE hors-cover) ; a-units = necroDestroyer (Gauss
R2, 6 coups) + blackObliterator (HeavyRound R3, 6 coups -> exerce la branche dist>2). Au TOUR IA,
l'oracle NATIF = decisionView.attackPlans[].evals[].ranked[] (dmgMin/dmgMax par tuile candidate,
facade IdunBattle.Core.Services.DamagePrediction$$GetAttackHits -> formule partagee IdunBattle.Entities.Formulas.AttackHitsWithModifiersFormula$$Calculate) ; l'offline =
make_normal_attack_predictions (meme formule portee).

Discriminant #62 : sur la cible DryBush le natif prend la branche Camouflage -3
(HasTile(TilesWithTriggeredAbility(Target,57)) IdunBattleLogic.Entities.Abilities.Triggered.Loki.Camouflage_HitReductionEffect$$CreateEffectHitsBonusForAttack) + LightCover -2 gate
AreEqual(coverPatch,target) IdunBattle.Entities.Effects.Loki.LightCoverEffect$$CreateEffectHitsBonusForAttack -> plancher 1 coup. PRE-FIX l'offline passait
defender_on_cover=None -> -1/-2 (distance) + LightCover-sur-presence = 3 coups. Le probe
imprime aussi le COUNTERFACTUEL pre-fix (Board.terrain_at patche -> None) : les lignes vs
la cible DryBush doivent DIVERGER de l'oracle (preuve que le cas est discriminant), les
lignes vs la cible controle rester identiques.

Historique : la ligne u77 (4,3) round-2 (+748 FLAT) etait l'aura alliee SpotterReworked
(Thaddeus) non portee -> porte tache #66 (SpotterReworkedExtraDamageEffect, extra_damage.py).
Depuis, 24/24 lignes exactes (re-run 2026-07-22 post-port) ; ce probe exerce au passage la
variante extraDmg (attaquant non-HeavyWeapon) de l'aura, probe_66_spotter.py couvre le reste.

ASCII only (cp1252). Usage: python probe_62_campred.py [--seed 62001] [--max-rounds 6]
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))

from rl_collect_batch import _resolve_session, _rpc  # noqa: E402
from engine.playbook import scene as SC  # noqa: E402
from engine.playbook.scene import Scene  # noqa: E402
from engine.playbook import prediction  # noqa: E402
from engine.entities.pathfinding.board import Board  # noqa: E402

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]
STATE = ROOT / "data" / "_62_campred_state.json"
TOL = 3                      # arrondi //100 vs Fix64 (meme tolerance que predict_samples)
COVER_POS = (3, 2)           # tuile DryBush de MC1_67
P_UNITS = "admecRuststalker,bloodSanguinary"
# blackObliterator ECARTE historiquement : FleshmetalGuns non porte a l'epoque -> contaminait
# l'agreement. PORTE depuis (#65, case-65 : forme amount-midpoint, probe_65_fleshmetal 30/30) —
# l'exclusion ici est conservee (roster fige, la couverture Volk vit dans probe_65). astraOrdnance
# (Thaddeus) = 3h Blast R3, seul R3 multi-hit du pool rank-17 -> exerce dist>2 vs DryBush
# (priorite branche -3 sur distance). IndirectFire : residuel connu #182 = Trench only (absent
# de MC1_67) -> lignes jugees a part si divergence.
A_UNITS = "necroDestroyer,astraOrdnance"


def _r(sid: int, method: str, body: dict, t: float = 90) -> dict:
    return (_rpc(sid, method, [body], timeout=t).get("result") or {})


def build(seed: int) -> int:
    STATE.unlink(missing_ok=True)   # sinon un STATE perime masque un build KO
    proc = subprocess.run(
        [sys.executable, "rl_duel.py", "build", "--seed", str(seed),
         "--state-file", str(STATE), "--board", "MC1_67",
         "--p-units", P_UNITS, "--a-units", A_UNITS,
         "--hp-player", "30000"],    # cibles increvables : le scenario survit aux tours IA d'approche
        cwd=str(PYDIR), capture_output=True, text=True, encoding="utf-8", errors="replace")
    if not STATE.exists():
        print(f"[62] build KO: {(proc.stderr or proc.stdout or '')[-400:]}", file=sys.stderr)
        sys.exit(2)
    return json.loads(STATE.read_text())["runnerId"]


def _units_by_vis(dv: dict) -> dict:
    return {u.get("visualId"): u for u in (dv.get("units") or []) if u.get("alive")}


def _collect_rows(dec: dict, predictor: dict, scene, tgt_ids: set) -> list[dict]:
    """Lignes (att, tgt, tile, oracle, offline) des attaques NORMALES rankees vs tgt_ids."""
    pos_by_id = {u["id"]: ((u.get("pos") or {}).get("col"), (u.get("pos") or {}).get("row"))
                 for u in (dec.get("units") or [])}
    rows = []
    for ap in (dec.get("attackPlans") or []):
        a_id = ap.get("unitId")
        if a_id not in predictor["ctx_by_id"]:
            continue
        norm_ids = {ab.get("id") for u in (dec.get("units") or []) if u.get("id") == a_id
                    for ab in (u.get("abilities") or []) if ab.get("kind") == "normal"}
        for ev in (ap.get("evals") or []):
            if ev.get("targetId") not in tgt_ids:
                continue
            if norm_ids and ev.get("abilityId") not in norm_ids:
                continue
            for rk in (ev.get("ranked") or []):
                # predOptimistic ACCEPTE ici (contrairement au test aura) : le tag est un
                # regex NOM sur-large (/HitReduction/ matche Camouflage_HitReduction) or le
                # canal hits-malus EST folde dans la prediction native (verdict #59 : formule
                # partagee IdunBattle.Entities.Formulas.AttackHitsWithModifiersFormula$$Calculate, PAS predOptimistic) -> les dmgMin/dmgMax rankes de la
                # cible Camouflage sont comparables. (Aucun effet resolve-only type
                # TerminatorArmour_ReduceDmg sur nos cibles.)
                if rk.get("dmgMax") is None:
                    continue
                tile = ((rk["col"], rk["row"]) if rk.get("col") is not None
                        else pos_by_id.get(a_id))
                ev_off = prediction.make_normal_attack_predictions(
                    scene, a_id, ev.get("targetId"), tile)
                res = ev_off.prediction.accurate_health_damage
                rows.append({"att": a_id, "tgt": ev.get("targetId"),
                             "tgtVis": ev.get("targetVis"), "tile": tile,
                             "ab": ev.get("abilityId"), "abName": ev.get("ability"),
                             "opt": bool(rk.get("predOptimistic")),
                             "crit": bool(rk.get("mightCrit")),
                             "oracle": (rk.get("dmgMin"), rk.get("dmgMax")),
                             "offline": (res.min, res.max)})
    return rows


def _agree(r: dict) -> bool:
    return max(abs(r["oracle"][0] - r["offline"][0]),
               abs(r["oracle"][1] - r["offline"][1])) <= TOL


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=62001)
    ap.add_argument("--max-rounds", type=int, default=6)
    args = ap.parse_args(argv)
    sid = _resolve_session()
    rid = build(args.seed)
    rpc = lambda m, b, t=60: _r(sid, m, b, t)   # noqa: E731
    print(f"[62] seed={args.seed} runner={rid}")
    try:
        dv0 = rpc("decisionView", {"runnerId": rid, "maxRank": 1}, 60)
        byvis = _units_by_vis(dv0)
        rust = byvis.get("admecRuststalker")
        sang = byvis.get("bloodSanguinary")
        if not rust or not sang:
            print(f"[62] roster KO (vis presents: {sorted(byvis)})"); return 2
        rust_id, sang_id = rust["id"], sang["id"]
        print(f"[62] rust=u{rust_id} pos={rust.get('pos')}  sang=u{sang_id} "
              f"pos={sang.get('pos')}  currentPlayer={dv0.get('currentPlayer')}")

        # Tour JOUEUR 1 : poser le rust sur la tuile DryBush, le sang (controle hors-cover)
        # sur une tuile Grass voisine — cibles co-localisees => les plans IA couvrent les
        # deux a la meme profondeur d'approche. Le tour passe a l'IA de lui-meme quand la
        # DERNIERE unite finit (pas d'endturn explicite).
        acts = [{"kind": "move", "unitId": rust_id,
                 "to": {"col": COVER_POS[0], "row": COVER_POS[1]}},
                {"kind": "finish", "unitId": rust_id},
                {"kind": "move", "unitId": sang_id, "to": {"col": 1, "row": 2}},
                {"kind": "finish", "unitId": sang_id}]
        r = rpc("applyAction", {"runnerId": rid, "actions": acts}, 60)
        if not (isinstance(r, dict) and r.get("ok", True)):
            print(f"[62] applyAction tour-1 KO: {r}"); return 2

        rows_rust, rows_ctrl, dec = [], [], None
        cf_pairs = []    # (dec, predictor, scene) des rounds a lignes rust, pour le counterfactuel
        for rnd in range(args.max_rounds):
            dec = rpc("decisionView", {"runnerId": rid, "maxRank": 99,
                                       "allAbilities": True}, 120)
            byvis = _units_by_vis(dec)
            ru = byvis.get("admecRuststalker")
            rp = (ru or {}).get("pos") or {}
            if not ru or (rp.get("col"), rp.get("row")) != COVER_POS:
                print(f"[62] rust hors position ({rp}) round {rnd} -> abort"); return 2
            lc = [e.get("name") for e in (ru.get("effects") or [])]
            predictor = SC.build_predictor(rpc, rid)
            if predictor is None:
                print("[62] combatSnapshot KO"); return 2
            sctx = SC.step_context(predictor, dec)
            scene = Scene.from_predictor_sctx(predictor, sctx, None)
            rows = _collect_rows(dec, predictor, scene, {rust_id, sang_id})
            _rr = [x for x in rows if x["tgt"] == rust_id]
            _rc = [x for x in rows if x["tgt"] == sang_id]
            rows_rust += _rr
            rows_ctrl += _rc
            if _rr:
                cf_pairs.append((dec, predictor, scene))
            print(f"[62] round {rnd}: cp={dec.get('currentPlayer')} rustEff={lc} "
                  f"rows rust=+{len(_rr)} ctrl=+{len(_rc)}")
            if rows_rust and rows_ctrl:
                break
            # IA hors de portee -> jouer son tour (approche), parquer mes unites, reessayer.
            subprocess.run([sys.executable, "rl_duel.py", "aiturn",
                            "--state-file", str(STATE)], cwd=str(PYDIR),
                           capture_output=True, text=True, encoding="utf-8", errors="replace")
            byvis = _units_by_vis(rpc("decisionView", {"runnerId": rid, "maxRank": 1}, 60))
            park = [{"kind": "finish", "unitId": u["id"]}
                    for v, u in byvis.items() if v in ("admecRuststalker", "bloodSanguinary")]
            rpc("applyAction", {"runnerId": rid, "actions": park}, 60)
        if not rows_rust:
            print("[62] AUCUNE ligne rankee vs le rust apres approche -> scenario KO")
            return 3

        # (1) agrement offline == oracle natif, cible DryBush + cible controle
        bad = [r for r in rows_rust + rows_ctrl if not _agree(r)]
        for r in rows_rust + rows_ctrl:
            tag = "DRYBUSH" if r["tgt"] == rust_id else "control"
            print(f"  [{tag}] u{r['att']}->u{r['tgt']} ab={r['ab']}({r['abName']}) "
                  f"tile={r['tile']} oracle={r['oracle']} offline={r['offline']} "
                  f"opt={int(r['opt'])} crit={int(r['crit'])} "
                  f"{'OK' if _agree(r) else '** MISS **'}")

        # (2) counterfactuel PRE-FIX : terrain inconnu (Board.terrain_at -> None) =>
        # defender_on_cover=None => Camouflage branche distance + LightCover sur-presence.
        # Attendu : rows vs rust DIVERGENT de l'oracle (cas discriminant), controle stable.
        cf_rust = []
        with mock.patch.object(Board, "terrain_at", lambda self, c, r: None):
            for _dec, _pred, _scene in cf_pairs:
                cf = _collect_rows(_dec, _pred, _scene, {rust_id})
                cf_rust += [x for x in cf if x["tgt"] == rust_id]
        cf_diverg = [x for x in cf_rust if not _agree(x)]
        # Attendu : divergent EXACTEMENT les lignes ranged dont le plancher DECLAMPE en
        # pre-fix (6 coups : 6-3-2=1 vs 6-1-2=3). Les attaquants 3 coups planchent a 1 des
        # deux cotes (3-3-2 vs 3-1-2) et la melee ne touche pas au cover -> inchangees.
        print(f"[62] counterfactuel pre-fix : {len(cf_diverg)}/{len(cf_rust)} lignes "
              f"DryBush divergent de l'oracle (attendu: les ranged multi-coups declampees)")
        if cf_rust and not cf_diverg:
            print("[62] /!\\ counterfactuel NON discriminant (le fix ne change rien ici)")
            return 4

        if bad:
            print(f"[62] ECHEC : {len(bad)}/{len(rows_rust) + len(rows_ctrl)} lignes en miss")
            return 1
        print(f"[62] OK : {len(rows_rust)} lignes DryBush + {len(rows_ctrl)} controle "
              f"= agreement 100% (TOL {TOL}), counterfactuel discriminant")
        return 0
    finally:
        try:
            _r(sid, "disposeRunner", {"runnerId": rid}, 15)
            print(f"[62] runner {rid} dispose")
        except Exception as e:
            print(f"[62] dispose KO: {e}")


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
