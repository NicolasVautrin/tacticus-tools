"""FIXTURE NOMMEE -- confronter la face PREDICTION du port a l'oracle NATIF, sur un montage donne.

POURQUOI CE MODULE EXISTE. Plusieurs residus (#950-r2, #953-r1, et la meme forme pour #974-r2)
disent la meme chose : un passif est porte SYMETRIQUEMENT dans les deux facades -- COMBAT
(`runner/damage_model.py`, `runner/operations/damage.py`) et PREDICTION
(`playbook/prediction/_shared.py`, `normal_attack.py`) -- mais seule la face COMBAT est confrontee.
Un fork prediction/combat y serait SILENCIEUX : l'IA n'ajusterait pas ses candidats, aucune erreur
ne serait levee, et aucun test ne rougirait. C'est exactement le motif que #462-r4b-r1-r1 a trouve
sur l'additif defenseur.

L'ORACLE EST `decisionView.attackPlans[].evals[].ranked[]` -- les bornes `dmgMin`/`dmgMax` que le
natif publie PAR TUILE CANDIDATE (`IdunBattle.Core.Services.DamagePredictionQuery$$GetAllPredictions`
construit une `UnitPosition(tuile de selection)` que
`IdunBattle.Core.Services.DamagePrediction$$PredictNormalAttack` pose comme CasterTile dans
`AbilityEntities..ctor`). Le port est `engine.playbook.prediction.make_normal_attack_predictions`,
appele sur LA MEME tuile candidate. C'est la recette NON CIRCULAIRE de
`tests/engine/test_aura_position_live.py` (#153), extraite ici pour etre partagee.

DEUX FILTRES, TOUS DEUX DITS :
  * `predOptimistic` -- ces lignes sont la borne OPTIMISTE du natif (crit suppose), pas la
    prediction de reference ; les melanger comparerait deux grandeurs differentes ;
  * `dmgMax is None` -- ligne sans borne publiee, rien a confronter.
Les deux sont COMPTES et rendus dans `ecartes`, jamais retires en silence.

TOLERANCE. `TOL = 3` : le port arrondit en `//100`, le natif en Fix64. C'est la meme tolerance que
`predict_samples.sample_is_ok` et que #153 -- elle n'est PAS un ajustement de cette tranche.

ASCII only (console Windows cp1252).
"""
from __future__ import annotations

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

#: Ecart tolere entre borne native et borne du port (arrondi //100 vs Fix64).
TOL = 3


def construire_scene(rpc, rid, dec=None):
    """Rend `(scene, sctx, dec)` -- la `Scene` du port batie sur l'etat LIVE du runner `rid`.

    `rpc` a la signature `(method, body=None, timeout=60)`. Rend `(None, None, dec)` si le
    substrat ne publie pas ce qu'il faut : l'appelant DIT alors pourquoi, il ne rend pas un zero.
    """
    from engine.playbook import scene as SC
    # #1045 -- LA PORTE, pas un corps a la main (#443-r2-b1). Ce module fabriquait
    # `{"runnerId": ..., "maxRank": 99, "allAbilities": True}` lui-meme, donc SANS `includeInactive` :
    # le capteur `readEffectsByUnit` (`frida/hooks/game/effects.ts`, `if (info && !info.active &&
    # !includeInactive) continue;`) DROPPE alors les instances posees-mais-INERTES, et la `Scene` du
    # port confrontait un etat AMPUTE a un oracle natif COMPLET -- l'ecart aurait ete mis au compte de
    # la prediction. La degradation est silencieuse : ni erreur, ni ligne manquante, juste des bornes
    # fausses. Forme B (`SNAP.<fn>`) et non `from ... import <fn>` : un binding de module n'est jamais
    # gele, donc un `monkeypatch` du foyer mord encore ici.
    # ⚠ `includeInactive` ne touche QUE le canal EFFETS (`rpc-decision.ts` ne le passe qu'a
    # `readEffectsByUnit`) : l'ORACLE `attackPlans[].evals[].ranked[]` est identique des deux cotes,
    # donc ce correctif ne peut pas deplacer la reference a laquelle on se compare.
    from engine.runner import snapshot as SNAP
    predictor = SC.build_predictor(lambda m, b, t: rpc(m, b, t), rid)
    if predictor is None:
        return None, None, dec
    if dec is None:
        dec = rpc("decisionView",
                  SNAP.decision_view_seed_body(rid, maxRank=99, allAbilities=True), 120)
    if not (isinstance(dec, dict) and dec.get("units")):
        return None, None, dec
    sctx = SC.step_context(predictor, dec)
    return SC.Scene.from_predictor_sctx(predictor, sctx, None), sctx, dec


def lignes_de_confrontation(scene, sctx, dec, att_id=None, tgt_id=None, ability_id=None):
    """Apparie, PAR TUILE CANDIDATE, la borne NATIVE et celle du PORT.

    Rend `(lignes, ecartes)` ou chaque ligne est
    `{att, tgt, ability, tile, oracle: (min, max), port: (min, max), delta: (dmin, dmax)}`
    et `ecartes` est le compte VENTILE de ce que les deux filtres ont retire.
    """
    from engine.playbook import prediction

    pos_by_id = sctx["pos_by_id"]
    lignes, ecartes = [], {"predOptimistic": 0, "sans_borne": 0, "hors_selection": 0}
    for ap in (dec.get("attackPlans") or []):
        a_id = ap.get("unitId")
        if att_id is not None and int(a_id) != int(att_id):
            ecartes["hors_selection"] += 1
            continue
        for ev in (ap.get("evals") or []):
            if tgt_id is not None and int(ev.get("targetId", -1)) != int(tgt_id):
                ecartes["hors_selection"] += 1
                continue
            if ability_id is not None and int(ev.get("abilityId", -1)) != int(ability_id):
                ecartes["hors_selection"] += 1
                continue
            for rk in (ev.get("ranked") or []):
                if rk.get("dmgMax") is None:
                    ecartes["sans_borne"] += 1
                    continue
                if rk.get("predOptimistic"):
                    ecartes["predOptimistic"] += 1
                    continue
                tile = ((rk["col"], rk["row"]) if rk.get("col") is not None
                        else pos_by_id.get(a_id))
                ev_off, meta = prediction.make_normal_attack_predictions(
                    scene, a_id, ev.get("targetId"), tile, meta=True)
                res = ev_off.prediction.accurate_health_damage
                lignes.append({
                    "att": a_id, "tgt": ev.get("targetId"), "ability": ev.get("abilityId"),
                    "tile": tuple(tile) if tile else None,
                    "oracle": (rk.get("dmgMin"), rk.get("dmgMax")),
                    "port": (res.min, res.max),
                    "delta": ((res.min or 0) - (rk.get("dmgMin") or 0),
                              (res.max or 0) - (rk.get("dmgMax") or 0)),
                    "base": meta.get("base"),
                })
    return lignes, ecartes


def divergences(lignes, tol=TOL):
    """Les lignes dont une borne s'ecarte de plus de `tol`. Une liste VIDE n'est un accord que si
    `lignes` est NON VIDE -- l'appelant doit l'assertionner (accord en regime degenere = zero
    preuve)."""
    return [l for l in lignes if abs(l["delta"][0]) > tol or abs(l["delta"][1]) > tol]


def resume(lignes, ecartes, tol=TOL):
    """Rend une chaine ASCII : le compte, les ecartes VENTILES, et les divergences."""
    div = divergences(lignes, tol)
    out = ["lignes confrontees : %d (tolerance %d)" % (len(lignes), tol),
           "ecartees : %s" % ", ".join("%s=%d" % (k, v) for k, v in sorted(ecartes.items()))]
    if not lignes:
        out.append("AUCUNE LIGNE -- aucun accord ne peut etre conclu (regime degenere)")
    elif not div:
        out.append("ACCORD : les %d lignes concordent a +/-%d" % (len(lignes), tol))
    else:
        out.append("DIVERGENCES : %d / %d" % (len(div), len(lignes)))
        for l in div[:12]:
            out.append("  tile=%s oracle=%s port=%s delta=%s"
                       % (l["tile"], l["oracle"], l["port"], l["delta"]))
    return "\n".join(out)
