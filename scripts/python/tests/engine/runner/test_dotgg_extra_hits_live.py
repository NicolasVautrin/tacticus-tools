"""CLIQUET du canal AURA de la formule de COUPS (#372) -- `DefenderOfTheGreaterGood_ExtraHits`
(1183, `tauShadowsun`) et ses jumeaux drone (1306 / 1307).

L'axe DEGAT de cette ability (`1182 DefenderOfTheGreaterGood_ExtraDmg`) etait DEJA porte ; l'axe
COUPS ne l'etait pas. C'est le profil exact d'un bug qui ne casse aucun test : le degat PAR COUP est
juste, le NOMBRE de coups est faux, et la somme est fausse sans que rien ne proteste.

L'artefact natif tranche le canal :
`IdunBattle.Entities.Effects.Loki.DefenderOfTheGreaterGood_ExtraHitsEffect$$CreateEffectHitsBonusForAttack`
= `EffectBonus.ForAddition( get_OwnerIsCaster & IsRangedAttack & !DamageProfileIs(0xd) &
Maybe(chance), ConfigConst(0x2b = extraHit) )` -- donc un TERME de
`IdunBattle.Entities.Formulas.AttackHitsWithModifiersFormula$$Calculate` (un coup d'ARME de plus),
et NON un `CreateAdditionalHits` (canal #179, groupe a degat propre). Cf. #204/#227, ici dans
l'autre sens.

VUE ROUGE AVANT LE FIX (obtenue par RETRAIT de l'inscription `DefenderOfTheGreaterGood_ExtraHits`
d'`EFFECT_CLASSES` -- le port d'AVANT, reconstitue), messages VERBATIM :

    AssertionError: ADJACENT : le port n'applique pas le +extraHit de l'aura DotGG --
    live n=2 [6930, 7105] offline n=1 [7329] (delta hits=-1)

    AssertionError: RING2_TAU (C1_25/31337) : live n=10 [1533, 1694, 1599, 1709, 1562, 1707, 1506,
    1585, 1815, 1701] offline n=9 [1442, 1533, 1694, 1599, 1709, 1562, 1498, 1585, 1815]
    (delta hits=-1)

    AssertionError: face PREDICTION : 1/1 tuiles en desaccord (TOL 3) --
    [((0, 2), 1, (11288, 16308), (5644, 8154))]

Le troisieme est le plus net : la tuile a d=1 diverge d'un FACTEUR 2 EXACT (11288/5644 = 16308/8154
= 2) -- deux coups contre un. La face DECISION consomme donc bien la meme formule.

LES REGIMES (montage : `_dotgg_aura_regime.py`) -- le selecteur natif
`DefenderOfTheGreaterGoodAbility$$GetBaseBuffTargetSelector` a DEUX tiers, ce test les separe :

  * `ADJACENT`      -- beneficiaire NON-T'au a d=1 du porteur  : DANS le selecteur (`AdjacentFriends`,
                       toute faction) -> +1 coup.
  * `RING2_NON_TAU` -- LE MEME beneficiaire a d=2               : `SurroundingFriends(2)` est filtre
                       par `UnitsFromFaction(9 = Tau)` -> rien. REGIME DISCRIMINANT du tier de
                       DISTANCE : meme unite, meme arme, meme cible ; seule la distance change.
  * `RING2_TAU`     -- beneficiaire T'AU a d=2                  : DANS le selecteur -> +1 coup.
                       Discrimine le tier de FACTION contre `RING2_NON_TAU`.
  * `FAR`           -- d=4                                      : TEMOIN.

LA CHANCE EST PILOTEE, PAS SUBIE : le bonus est gate par `Maybe( Min(Direct(100),
Multiply(ConfigConst(0x2a = chance = 25), UnitTurnsStarted(porteur))) )`. Le harnais fait tourner
des tours a vide jusqu'a `turnsStarted(Shadowsun) >= 4`, ou la chance vaut 100 : les deux faces y
concordent sans aleatoire (`MaybeTrigger$$ShouldTrigger` : `99 < chance` sans PRNG, `NextBool(100)`
avec). En-dessous, le coup serait un TIRAGE et la mesure ne conclurait rien.

ASCII only.
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))      # helpers siblings
from _dotgg_aura_regime import (ADJACENT, CARRIER, FAR, RING2_NON_TAU,       # noqa: E402,F401
                                RING2_TAU, dotgg_aura_regime)

from engine.entities.effects.factory import EFFECT_CLASSES                   # noqa: E402
from engine.entities.effects.loki.extra_damage_aura import (
    DefenderOfTheGreaterGoodExtraDmgDroneEffect
)
from engine.entities.effects.loki.hits import (
    DefenderOfTheGreaterGoodExtraHitsDroneEffect, DefenderOfTheGreaterGoodExtraHitsEffect
)  # noqa: E402

_EFFECT_NAME = "DefenderOfTheGreaterGood_ExtraHits"
_BENEF_NON_TAU = "darkaHellblaster"     # Imperial, arme RANGED, aucun effet de coups parasite
_BENEF_TAU = "tauCrisis"                # T'au, arme RANGED -> exerce le tier `UnitsFromFaction(9)`


# --------------------------------------------------------------------- gardes STRUCTURELLES (offline)

def test_registry_carries_the_four_effect_types():
    """Les QUATRE `EffectType` de l'ability sont au registre, et les jumeaux drone sont bien les
    sous-classes `isDrone` -- pas des classes inventees.

    Le natif n'a que DEUX classes pour ces quatre ids : `..._Extra{Dmg,Hits}Effect$$.ctor(this,
    isDrone)` ecrit `isDrone` a `this+0x480`."""
    assert EFFECT_CLASSES.get(_EFFECT_NAME) is DefenderOfTheGreaterGoodExtraHitsEffect
    assert (EFFECT_CLASSES.get("DefenderOfTheGreaterGood_ExtraHitsDrone")
            is DefenderOfTheGreaterGoodExtraHitsDroneEffect)
    assert (EFFECT_CLASSES.get("DefenderOfTheGreaterGood_ExtraDmgDrone")
            is DefenderOfTheGreaterGoodExtraDmgDroneEffect)
    assert issubclass(DefenderOfTheGreaterGoodExtraHitsDroneEffect,
                      DefenderOfTheGreaterGoodExtraHitsEffect)
    assert DefenderOfTheGreaterGoodExtraHitsDroneEffect._IS_DRONE is True
    assert DefenderOfTheGreaterGoodExtraHitsEffect._IS_DRONE is False


def _eff(cls=DefenderOfTheGreaterGoodExtraHitsEffect, effect_type=1183):
    return cls(name=_EFFECT_NAME, effect_type=effect_type, level=1, ability_level=50)


def _ctx(**over):
    base = {"owner_id": 1, "owner_pos": (0, 4), "owner_team": 1,
            "att_id": 2, "att_team": 1, "att_pos": (0, 3), "att_faction": "SpaceMarines",
            "is_melee": False, "damage_profile": "Physical",
            "turns_started_by_id": {1: 4, 2: 4}}
    base.update(over)
    return base


def test_selector_tiers_offline():
    """Le SELECTEUR a deux tiers DISTINCTS, et le port les separe : d=1 toute faction, d=2 T'au
    SEULEMENT. Un port sans le gate de faction accorderait aussi a `RING2_NON_TAU`."""
    e = _eff()
    assert e.create_aura_hits_bonus_for_attack(_ctx()) is not None, "d=1 non-T'au doit mordre"
    assert e.create_aura_hits_bonus_for_attack(_ctx(att_pos=(0, 2))) is None, \
        "d=2 NON-T'au ne doit RIEN accorder (UnitsFromFaction(9 = Tau) filtre le ring 2)"
    assert e.create_aura_hits_bonus_for_attack(
        _ctx(att_pos=(0, 2), att_faction="Tau")) is not None, "d=2 T'au doit mordre"
    assert e.create_aura_hits_bonus_for_attack(
        _ctx(att_pos=(0, 0), att_faction="Tau")) is None, "d=4 ne doit rien accorder"
    assert e.create_aura_hits_bonus_for_attack(_ctx(att_id=1)) is None, \
        "`sel - Owner` : le porteur ne se bonifie pas lui-meme"
    assert e.create_aura_hits_bonus_for_attack(_ctx(att_team=2)) is None, \
        "Adjacent/SurroundingFRIENDS : un ennemi n'est jamais dans le selecteur"


def test_gates_and_chance_offline():
    """Les gates du trigger et la formule de chance, un a un.

    `chance = Min(Direct(100), Multiply(ConfigConst(0x2a = 25), UnitTurnsStarted(src)))` -- le
    `Maybe` sans PRNG rend `99 < chance`, donc le bonus n'existe qu'a 100 (>= 4 tours)."""
    e = _eff()
    assert e.current_extra_hit_chance(_ctx(turns_started_by_id={1: 1, 2: 9})) == 25
    assert e.current_extra_hit_chance(_ctx(turns_started_by_id={1: 3, 2: 9})) == 75
    assert e.current_extra_hit_chance(_ctx(turns_started_by_id={1: 4, 2: 9})) == 100
    assert e.current_extra_hit_chance(_ctx(turns_started_by_id={1: 40, 2: 9})) == 100, \
        "Min(Direct(100), .) -- la chance PLAFONNE a 100"
    assert e.current_extra_hit_chance(_ctx(turns_started_by_id={})) is None, \
        "substrat absent -> None, jamais un 0 deguise en mesure"
    # `Maybe` sans PRNG (face DECISION/PREDICTION) = `99 < chance`
    assert e.create_aura_hits_bonus_for_attack(_ctx(turns_started_by_id={1: 3})) is None, \
        "chance 75 sans PRNG -> `99 < 75` FAUX : aucun coup en prediction"
    assert e.create_aura_hits_bonus_for_attack(_ctx(turns_started_by_id={1: 4})) is not None
    # gates du trigger / du selecteur
    assert e.create_aura_hits_bonus_for_attack(_ctx(is_melee=True)) is None, "IsRangedAttack"
    assert e.create_aura_hits_bonus_for_attack(_ctx(is_melee=None)) is None, \
        "TRI-ETAT : nature non declaree -> le gate `IsRangedAttack` se tait"
    assert e.create_aura_hits_bonus_for_attack(_ctx(damage_profile="Psychic")) is None, \
        "UnitsWithRangedWeaponsExcludingDamageProfile(0xd = Psychic)"


def test_chance_reads_the_parent_for_the_drone_offline():
    """Le jumeau DRONE lit les tours de son PARENT (Shadowsun), pas les siens :
    `If( AmountIsGreaterThanZero(Parent(EffectSource)), Parent(EffectSource), EffectSource )`.

    Sans ce nœud, un drone fraichement invoque (0 tour) n'accorderait JAMAIS le coup."""
    d = _eff(DefenderOfTheGreaterGoodExtraHitsDroneEffect, 1307)
    # porteur = 3 (le drone, 0 tour), parent = 1 (Shadowsun, 4 tours)
    c = _ctx(owner_id=3, turns_started_by_id={1: 4, 3: 0}, parent_by_id={3: 1})
    assert d.current_extra_hit_chance(c) == 100, "le drone doit lire les tours de son summoner"
    assert d.current_extra_hit_chance({**c, "parent_by_id": {}}) == 0, \
        "sans lien parent, le drone retombe sur SES tours (sous-estimation NOMMEE)"


def test_drone_does_not_double_count_offline():
    """`EntitiesIsNotTargetOfEffect(sel, 0x49f)` -- la branche `isDrone` du selecteur retire du
    drone toute unite DEJA ciblee par l'effet de Shadowsun. Sans elle, une unite couverte par les
    DEUX auras prendrait +2 coups au lieu de +1."""
    src = _eff()                                                     # 1183 sur Shadowsun (id 1)
    drone = _eff(DefenderOfTheGreaterGoodExtraHitsDroneEffect, 1307)  # 1307 sur le drone (id 3)
    peers = [(1, (0, 4), 1, [src]), (3, (0, 2), 1, [drone])]
    c = _ctx(owner_id=3, owner_pos=(0, 2), turns_started_by_id={1: 4, 3: 4}, aura_peers=peers)
    # CONTROLE : sans la branche `isDrone`, ce meme contexte accorderait -- c'est ce que rend la
    # classe SOURCE, dont le drone n'herite que le tronc du selecteur.
    assert src.create_aura_hits_bonus_for_attack({**c, "owner_id": 1, "owner_pos": (0, 4)}) \
        is not None, "controle : la classe SOURCE accorde bien sur cette geometrie"
    # l'attaquant est en (0,3) : adjacent AUX DEUX -> le drone doit se taire
    assert drone.create_aura_hits_bonus_for_attack(c) is None, \
        "l'attaquant est deja cible de l'effet 1183 de Shadowsun -> le drone n'ajoute RIEN"
    # meme drone, attaquant HORS du selecteur de Shadowsun (d=3 d'elle, d=1 du drone) -> il accorde
    c2 = _ctx(owner_id=3, owner_pos=(0, 2), att_pos=(0, 1),
              turns_started_by_id={1: 4, 3: 4}, aura_peers=peers)
    assert drone.create_aura_hits_bonus_for_attack(c2) is not None, \
        "hors de l'aura de Shadowsun, le drone accorde bien son coup"


# --------------------------------------------------------------------- confrontation LIVE

@pytest.fixture(scope="module")
def shadowsun(dotgg_aura_regime):
    """`tauShadowsun` (HERO du pool) porte le passif `DefenderOfTheGreaterGood` -> les effets 1182 et
    1183 sur elle-meme des le debut de bataille (aucun cast a monter). Beneficiaire NON-T'au : il
    donne les DEUX tiers de distance avec la MEME unite."""
    return dotgg_aura_regime(benef=_BENEF_NON_TAU)


@pytest.fixture(scope="module")
def shadowsun_tau(dotgg_aura_regime):
    """Beneficiaire T'AU, AUTRE board et AUTRE seed : exerce `UnitsFromFaction(9 = Tau)` du ring 2
    ET generalise la geometrie."""
    return dotgg_aura_regime(benef=_BENEF_TAU, seed="31337", board="C1_25")


def _run(h, regime, benef):
    rec = h.run(benef, regime)
    if rec is None:
        pytest.fail("montage dotgg NON INSTALLE (regime %s, benef %s)" % (regime, benef),
                    pytrace=False)
    if not rec["live_ok"] or not rec["live_per_hit"]:
        pytest.fail("attaque normale live refusee/vide (%s)" % regime, pytrace=False)
    assert rec["turns_started"] is not None and rec["turns_started"] >= 4, (
        "le montage doit saturer la chance (turnsStarted(%s) >= 4) ; obtenu %s -- en-dessous le "
        "coup est un TIRAGE et la mesure ne conclut rien" % (CARRIER, rec["turns_started"]))
    return rec, h.replay_offline(rec)


def _carrier_has_effect(off):
    return _EFFECT_NAME in (off["carrier_effects"] or [])


def test_adjacent_grants_the_extra_hit(shadowsun):
    """CAS ROUGE AVANT LE FIX -- un allie ADJACENT au porteur gagne `extraHit` coup.

    L'assertion est PROBANTE : on exige AUSSI que l'effet soit MATERIALISE offline sur le porteur,
    sinon le test comparerait deux absences."""
    rec, off = _run(shadowsun, ADJACENT, _BENEF_NON_TAU)
    assert _carrier_has_effect(off), (
        "l'effet %s n'est pas materialise offline sur le porteur -- le test comparerait deux "
        "absences ; effets vus = %s" % (_EFFECT_NAME, off["carrier_effects"]))
    assert len(off["per_hit"]) == len(rec["live_per_hit"]), (
        "ADJACENT : le port n'applique pas le +extraHit de l'aura DotGG -- live n=%d %s "
        "offline n=%d %s (delta hits=%d)"
        % (len(rec["live_per_hit"]), rec["live_per_hit"], len(off["per_hit"]), off["per_hit"],
           len(off["per_hit"]) - len(rec["live_per_hit"])))
    assert off["per_hit"] == rec["live_per_hit"], (
        "ADJACENT : meme nombre de coups mais valeurs differentes -- live=%s offline=%s"
        % (rec["live_per_hit"], off["per_hit"]))


def test_ring2_non_tau_grants_nothing(shadowsun):
    """REGIME DISCRIMINANT du tier de DISTANCE -- LE MEME beneficiaire, un hex plus loin.

    `SurroundingFriends(owner, 2)` est filtre par `UnitsFromFaction(9 = Tau)` : un NON-T'au a d=2
    n'est pas dans le selecteur. Un port qui traiterait `d <= 2` sans le gate de faction en
    accorderait ici."""
    rec, off = _run(shadowsun, RING2_NON_TAU, _BENEF_NON_TAU)
    assert _carrier_has_effect(off), "l'effet doit etre present (sinon le gate n'est pas exerce)"
    assert len(off["per_hit"]) == len(rec["live_per_hit"]), (
        "RING2_NON_TAU : le port SUR-applique le +extraHit (gate de faction manquant ?) -- "
        "live n=%d %s offline n=%d %s" % (len(rec["live_per_hit"]), rec["live_per_hit"],
                                          len(off["per_hit"]), off["per_hit"]))
    assert off["per_hit"] == rec["live_per_hit"], (
        "RING2_NON_TAU : live=%s offline=%s" % (rec["live_per_hit"], off["per_hit"]))


def test_far_grants_nothing(shadowsun):
    """TEMOIN -- d=4, hors de toute portee. Verrouille que le port n'a rien deplace sur le seul
    regime deja juste avant lui."""
    rec, off = _run(shadowsun, FAR, _BENEF_NON_TAU)
    assert len(off["per_hit"]) == len(rec["live_per_hit"]), (
        "FAR : live n=%d %s offline n=%d %s" % (len(rec["live_per_hit"]), rec["live_per_hit"],
                                                len(off["per_hit"]), off["per_hit"]))
    assert off["per_hit"] == rec["live_per_hit"], (
        "FAR : live=%s offline=%s" % (rec["live_per_hit"], off["per_hit"]))


def test_adjacent_beats_ring2_live(shadowsun):
    """Le NATIF separe bien les deux regimes -- sinon les deux tests ci-dessus passeraient pour une
    raison triviale (aucun bonus nulle part). On compare deux mesures LIVE, pas le port."""
    rec_a, _ = _run(shadowsun, ADJACENT, _BENEF_NON_TAU)
    rec_r, _ = _run(shadowsun, RING2_NON_TAU, _BENEF_NON_TAU)
    assert len(rec_a["live_per_hit"]) > len(rec_r["live_per_hit"]), (
        "le natif doit porter PLUS de coups a d=1 qu'a d=2 pour un NON-T'au -- ADJACENT n=%d, "
        "RING2_NON_TAU n=%d (si egal, le montage n'exerce pas le bonus)"
        % (len(rec_a["live_per_hit"]), len(rec_r["live_per_hit"])))


_PRED_TOL = 3          # meme tolerance que `probe_220_dotgg.py` (arrondis de la chaine de degat)


def test_prediction_face_agrees(shadowsun):
    """L'AUTRE FACE -- la formule de coups est PARTAGEE par le combat et la prediction (le natif ne
    la duplique pas), donc le port doit accorder sur les DEUX.

    On confronte l'oracle natif per-tuile (`decisionView.attackPlans[].evals[].ranked`, issu de
    `IdunBattle.Core.Services.DamagePredictionQuery$$GetAllPredictions`) a
    `playbook.prediction.make_normal_attack_predictions`, dans le regime `chance = 100` ou le
    `Maybe` est DETERMINISTE des deux cotes (sans PRNG : `99 < chance`).

    L'assertion exige AUSSI qu'au moins une tuile rankee soit DANS l'aura (d <= 1) : sinon le
    verdict porterait sur des tuiles ou le bonus n'existe pas, et ne prouverait rien."""
    rec = shadowsun.run(_BENEF_NON_TAU, ADJACENT)
    if rec is None:
        pytest.fail("montage dotgg NON INSTALLE (prediction)", pytrace=False)
    rows = rec.get("predict_rows")
    assert rows, "aucune tuile rankee pour le beneficiaire -- la face PREDICTION n'a rien confronte"
    assert any(r["d_carrier"] <= 1 for r in rows), (
        "aucune tuile rankee n'est DANS l'aura (d <= 1 du porteur) : le verdict porterait sur des "
        "tuiles ou le bonus n'existe pas ; distances vues = %s"
        % sorted({r["d_carrier"] for r in rows}))
    bad = [r for r in rows
           if max(abs(r["oracle"][0] - r["offline"][0]),
                  abs(r["oracle"][1] - r["offline"][1])) > _PRED_TOL]
    assert not bad, (
        "face PREDICTION : %d/%d tuiles en desaccord (TOL %d) -- %s"
        % (len(bad), len(rows), _PRED_TOL,
           [(r["tile"], r["d_carrier"], r["oracle"], r["offline"]) for r in bad[:6]]))


def test_ring2_tau_grants_the_extra_hit(shadowsun_tau):
    """GENERALISATION -- tier de FACTION du selecteur, sur un AUTRE board (`C1_25`) et un AUTRE seed
    (31337) : un T'AU a d=2 EST dans le selecteur, la ou le non-T'au du meme rayon ne l'est pas."""
    rec, off = _run(shadowsun_tau, RING2_TAU, _BENEF_TAU)
    assert _carrier_has_effect(off), "l'effet doit etre materialise offline sur le porteur"
    assert len(off["per_hit"]) == len(rec["live_per_hit"]), (
        "RING2_TAU (C1_25/31337) : live n=%d %s offline n=%d %s (delta hits=%d)"
        % (len(rec["live_per_hit"]), rec["live_per_hit"], len(off["per_hit"]), off["per_hit"],
           len(off["per_hit"]) - len(rec["live_per_hit"])))


def test_tau_ring2_beats_far_live(shadowsun_tau):
    """Contre-epreuve LIVE du tier T'au : le MEME beneficiaire T'au a d=4 perd le coup."""
    rec_r, _ = _run(shadowsun_tau, RING2_TAU, _BENEF_TAU)
    rec_f, _ = _run(shadowsun_tau, FAR, _BENEF_TAU)
    assert len(rec_r["live_per_hit"]) > len(rec_f["live_per_hit"]), (
        "le natif doit porter PLUS de coups a d=2 (T'au) qu'a d=4 -- RING2_TAU n=%d, FAR n=%d"
        % (len(rec_r["live_per_hit"]), len(rec_f["live_per_hit"])))
