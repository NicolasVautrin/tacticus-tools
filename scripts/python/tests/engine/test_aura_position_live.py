"""Agrement #153 : l'aura d'ATTAQUE-STAT (RitesOfBattle @181225340 / PathOfCommand @181110f10) en
PREDICTION DISPLAY est re-evaluee a la TUILE CANDIDATE — PAS bakee a la position reelle de
l'attaquant. REMPLACE l'ancien test #67 qui etait CIRCULAIRE (il mesurait la constance de la base
du PORT contre le port lui-meme, jamais l'oracle natif : `_base()` appelait
`prediction.make_normal_attack_predictions`).

Verite native (verdict #153, mesure discriminante + decompile) :
- la chaine display threade la UnitPosition candidate de bout en bout :
  `DamagePredictionQuery.GetAllPredictions @181090f50` construit `UnitPosition(tuile de selection)`
  -> `DamagePrediction.PredictNormalAttack @181037cd0` la pose comme CasterTile dans
  `AbilityEntities.ctor` ;
- mesure discriminante seed-31337 (UN decisionView, attaquant reel FIXE hex-adjacent au porteur,
  seule la tuile candidate varie) : tuiles out-ring -> base Initial (aura PERDUE malgre le stat-mod
  +1298 present live via statModSources) ; converse : attaquant reel LOIN du porteur, tuile
  candidate in-ring -> base Initial+aura (aura GAGNEE).

Ce test est NON-circulaire : l'oracle = `decisionView.attackPlans[].evals[].ranked[]` NATIF
(dmgMin/dmgMax PAR TUILE candidate col/row), l'offline = le port. Assertions GENERIQUES (aucune
valeur hardcodee) et seed-parametrable (env AURA_SEED, defaut 31337 ou la config discriminante
existe) :
  (1) chaque ligne clean (att avec porteur d'aura allie a proximite variable) : offline == oracle
      (tolerance arrondi 3) sur CHAQUE tuile candidate rankee ;
  (2) le lot contient AU MOINS une tuile ou l'aura fire et une ou elle ne fire pas pour le MEME
      attaquant (sinon skip : configuration non discriminante, le test ne prouverait rien).
Skip propre si pas de porteur d'aura, pas de plan d'attaque, ou groupes non separables.
ASCII-only (cp1252)."""
from __future__ import annotations

import os

import pytest

import gameconfig as GC
from engine.playbook import scene as SC
from engine.playbook.scene import Scene
from engine.playbook import prediction
from engine.entities.effects import aura_attack_bonus_from_allies

TOL = 3   # arrondi //100 vs Fix64 (meme tolerance que predict_samples.sample_is_ok)


def _carriers(scene, att_id):
    return [(uid, scene.pos(uid), scene.team(uid), scene.mult(uid), scene.ablvl_by_id.get(uid),
             (GC.unit(scene.vis_by_id.get(uid)) or {}).get("GrandAllianceId"),
             (GC.unit(scene.vis_by_id.get(uid)) or {}).get("FactionId"), scene.effects(uid))
            for uid in scene.pos_by_id if uid != att_id and (scene.hp(uid) or 0) > 0]


def _aura_at(scene, att_id, att_pos):
    agu = GC.unit(scene.vis_by_id.get(att_id)) or {}
    ctx = {"att_id": att_id, "att_pos": att_pos, "att_team": scene.team(att_id),
           "att_grand_alliance": agu.get("GrandAllianceId"), "att_faction": agu.get("FactionId"),
           "board": scene.board}
    return aura_attack_bonus_from_allies(_carriers(scene, att_id), ctx)


def test_attack_stat_aura_follows_candidate_tile(rpc, build_runner):
    import predict_samples as PV

    seed = os.environ.get("AURA_SEED", "31337")
    info = build_runner(seed=seed)
    rid, my_team = info["rid"], info["my_team"]

    sid_rpc = lambda m, b, t: rpc(m, b, t)
    # drive au contact (harnais standard predict) — PV._drive_into_range utilise PV.rpc(sid, ...) ;
    # on le route (sid-agnostique) sur le fixture rpc de la session de test.
    orig_rpc = PV.rpc
    PV.rpc = lambda _sid, m, b=None, t=60: rpc(m, b, t)
    try:
        PV._drive_into_range(None, rid, my_team, int(os.environ.get("PREDICT_MAX_TURNS", "6")))
        predictor = SC.build_predictor(sid_rpc, rid)
        if predictor is None:
            pytest.skip("combatSnapshot KO")
        dec = rpc("decisionView", {"runnerId": rid, "maxRank": 99, "allAbilities": True}, 120)
    finally:
        PV.rpc = orig_rpc
    if not (isinstance(dec, dict) and dec.get("units")):
        pytest.skip("decisionView vide")
    sctx = SC.step_context(predictor, dec)
    scene = Scene.from_predictor_sctx(predictor, sctx, None)
    pos_by_id = sctx["pos_by_id"]

    rows = []
    for ap in (dec.get("attackPlans") or []):
        a_id = ap.get("unitId")
        if a_id not in predictor["ctx_by_id"]:
            continue
        norm_ids = {ab.get("id") for u in (dec.get("units") or []) if u.get("id") == a_id
                    for ab in (u.get("abilities") or []) if ab.get("kind") == "normal"}
        for ev in (ap.get("evals") or []):
            if norm_ids and ev.get("abilityId") not in norm_ids:
                continue
            for rk in (ev.get("ranked") or []):
                if rk.get("dmgMax") is None or rk.get("predOptimistic"):
                    continue
                tile = ((rk["col"], rk["row"]) if rk.get("col") is not None
                        else pos_by_id.get(a_id))
                ev_off, meta = prediction.make_normal_attack_predictions(
                    scene, a_id, ev.get("targetId"), tile, meta=True)
                res = ev_off.prediction.accurate_health_damage
                rows.append({"att": a_id, "tgt": ev.get("targetId"), "tgtVis": ev.get("targetVis"),
                             "tile": tile, "aura": _aura_at(scene, a_id, tile),
                             "oracle": (rk.get("dmgMin"), rk.get("dmgMax")),
                             "offline": (res.min, res.max), "base": meta["base"]})
    if not rows:
        pytest.skip("aucune tuile candidate rankee d'attaque normale (drive insuffisant)")

    # (2) exigence discriminante : pour AU MOINS un attaquant, l'aura fire sur certaines tuiles
    # candidates et pas d'autres (sinon la constance/variation de base n'est pas testable).
    by_att = {}
    for r in rows:
        by_att.setdefault(r["att"], set()).add(r["aura"] > 0)
    disc_atts = [a for a, flags in by_att.items() if flags == {True, False}]
    if not disc_atts:
        pytest.skip("configuration non discriminante : aucun attaquant avec tuiles in-ring ET "
                    "out-ring d'un porteur d'aura (AURA_SEED=%s)" % seed)

    # (1) agrement offline == oracle NATIF sur CHAQUE tuile candidate (aura per-tuile incluse)
    bad = ["u%s->u%s\\%s tile=%s aura=%s oracle=%s offline=%s base=%s" % (
        r["att"], r["tgt"], r["tgtVis"], r["tile"], r["aura"], r["oracle"], r["offline"], r["base"])
        for r in rows
        if max(abs(r["oracle"][0] - r["offline"][0]), abs(r["oracle"][1] - r["offline"][1])) > TOL]
    assert not bad, ("prediction offline != oracle natif per-tuile (%d/%d ; attaquants "
                     "discriminants %s) :\n" % (len(bad), len(rows), disc_atts)) + "\n".join(bad)
