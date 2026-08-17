"""CLIQUET `IsCharging` du canal COUPS (case-ischarging-hits) -- `SagaOfTheWarriorBorn_Owner` (1223, Ragnar).

Le canal COUPS (`CreateEffectHitsBonusForAttack`) n'etait porte sur AUCUN de ses consommateurs
gates par `IdunBattleLogic.Entities.DSLTriggers$$IsCharging`. Le premier a entrer est
`IdunBattle.Entities.Effects.Loki.SagaOfTheWarriorBorn_OwnerEffect$$CreateEffectHitsBonusForAttack` :

    EffectBonus.ForAddition( get_OwnerIsCaster & IsCharging(owner@0x148, target@0x178),
                             ConfigVar(0x13 = extraHits, GetAbilityState(effect), config@+0x60) )

DEUX noeuds trigger : ni `IsNormalAttack`, ni `IsMeleeAttack`.

POURQUOI LE NOMBRE DE COUPS, ET PAS UN SCALAIRE DE DEGAT : l'observable est DISCRETE
(`len(per_hit)`). Un ecart d'un coup ne peut etre ni absorbe ni compense par un regime d'armure,
de percage ou de crit -- contrairement a un total de degat. Les deux modeles sont donc separes par
une egalite d'entiers, pas par une tolerance.

TROIS REGIMES, TROIS ROLES DISTINCTS (montage : `_charge_regime.py`) :

  * `CHARGE`        -- part a distance 2, arrive AU CONTACT. `IsCharging` VRAI -> base + extraHits.
                       VUE ROUGE AVANT LE FIX, message verbatim :
                           AssertionError: CHARGE : le port n'applique pas le +extraHits de charge --
                           live n=10 [1879, 1411, 1917, 1681, 2101, 1998, 1761, 1658, 1853, 2090]
                           offline n=7 [1879, 1411, 1917, 1681, 2101, 1998, 1761] (delta hits=-3)
                       Les 7 premiers coups etaient DEJA bit-exacts : la divergence etait localisee
                       au NOMBRE de coups, pas a leur valeur.
  * `STEP_ADJACENT` -- part DEJA au contact et se decale vers une AUTRE tuile adjacente.
                       `UpdateCharging` n'inscrit que les unites NOUVELLEMENT adjacentes -> la cible
                       n'y entre pas -> `IsCharging` FAUX alors que `UnitFlag.Moved` est VRAI.
                       C'est LE regime DISCRIMINANT : un port gate par le proxy `has_moved` y
                       rendrait la base + extraHits, le natif rend la base NUE.
  * `NO_STEP`       -- aucun pas. TEMOIN : les deux modeles y coincident, avant comme apres.

ASCII only.
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))      # helpers siblings
from _charge_regime import (CHARGE, NO_STEP, STEP_ADJACENT,       # noqa: E402,F401  (fixture)
                            charge_regime)

from engine.entities.effects.factory import EFFECT_CLASSES        # noqa: E402
from engine.entities.effects.loki.hits import SagaOfTheWarriorBornOwnerEffect  # noqa: E402

_CASTER = "spaceBlackmane"          # <<Ragnar>>, HERO du pool, porteur du passif SagaOfTheWarriorBorn
_EFFECT_NAME = "SagaOfTheWarriorBorn_Owner"


@pytest.fixture(scope="module")
def ragnar(charge_regime):
    """`spaceBlackmane` (HERO du pool) porte le passif `SagaOfTheWarriorBorn` -> l'effet 1223 sur
    lui-meme des le debut de bataille (aucun cast a monter). Cibles Necrons a PV gonfles."""
    return charge_regime(p_units=_CASTER, a_units="necroOverlord,necroWarden")


@pytest.fixture(scope="module")
def ragnar_alt(charge_regime):
    """GENERALISATION : meme invariant, AUTRE board, AUTRE seed, AUTRES cibles."""
    return charge_regime(p_units=_CASTER, a_units="orksNob,tyranTyrantGuard",
                         seed="31337", board="C1_25")


def _run(h, regime):
    rec = h.run(caster_visual=_CASTER, regime=regime)
    if rec is None:
        pytest.skip("geometrie %s non realisable sur ce board" % regime)
    if not rec["live_ok"] or not rec["live_per_hit"]:
        pytest.skip("attaque normale live refusee/vide (%s)" % regime)
    return rec, h.replay_offline(rec)


def _saga_effect(rec, off):
    """L'effet 1223 doit etre MATERIALISE offline sur le caster -- sinon le test compare deux
    absences et son verdict ne vaut rien."""
    st = off["state"]
    return [e for e in (st.effects.by_unit.get(rec["caster"]) or [])
            if e.effect_type == 1223 or e.name == _EFFECT_NAME]


def test_registry_carries_the_effect():
    """Garde STRUCTURELLE (offline, sans jeu) : l'effet est enregistre ET son gate est TRI-ETAT.
    Une contribution rendue sans `is_charging` PROUVE serait un bonus inconditionnel."""
    assert EFFECT_CLASSES.get(_EFFECT_NAME) is SagaOfTheWarriorBornOwnerEffect
    e = SagaOfTheWarriorBornOwnerEffect(name=_EFFECT_NAME, effect_type=1223, level=1,
                                        ability_level=50)
    assert e.create_effect_hits_bonus_for_attack(True, None) is None, \
        "contexte ABSENT -> aucune contribution (le natif commence par AreEntitiesAdjacent)"
    assert e.create_effect_hits_bonus_for_attack(True, {"is_charging": False}) is None
    got = e.create_effect_hits_bonus_for_attack(True, {"is_charging": True})
    assert got is not None and got.kind == "Addition" and got.value > 0, \
        "charge PROUVEE -> ForAddition(extraHits) ; obtenu %r" % (got,)


def test_charge_grants_extra_hits(ragnar):
    """CAS ROUGE AVANT LE FIX -- la charge ajoute `extraHits[level]` coups.

    L'assertion est PROBANTE : on exige AUSSI que le live porte STRICTEMENT plus de coups que
    l'arme seule, sinon un etat ou personne n'accorde rien passerait trivialement."""
    rec, off = _run(ragnar, CHARGE)
    assert _saga_effect(rec, off), \
        "l'effet 1223 n'est pas materialise offline -- le test comparerait deux absences"
    assert rec["target"] in off["charged"], (
        "la cible DOIT entrer dans ChargedUnitIds (nouvellement adjacente) ; charged=%s target=%s"
        % (off["charged"], rec["target"]))
    assert len(off["per_hit"]) == len(rec["live_per_hit"]), (
        "CHARGE : le port n'applique pas le +extraHits de charge -- live n=%d %s offline n=%d %s "
        "(delta hits=%d)" % (len(rec["live_per_hit"]), rec["live_per_hit"],
                             len(off["per_hit"]), off["per_hit"],
                             len(off["per_hit"]) - len(rec["live_per_hit"])))
    assert off["per_hit"] == rec["live_per_hit"], (
        "CHARGE : meme nombre de coups mais valeurs differentes -- live=%s offline=%s"
        % (rec["live_per_hit"], off["per_hit"]))


def test_step_adjacent_grants_nothing(ragnar):
    """REGIME DISCRIMINANT -- le caster BOUGE, mais la cible etait DEJA adjacente avant le pas.

    `UpdateCharging` ne l'ajoute donc PAS aux `ChargedUnitIds` : `IsCharging` FAUX, aucun coup
    supplementaire, alors que le flag `Moved` est VRAI. Un gate `has_moved` en accorderait ici."""
    rec, off = _run(ragnar, STEP_ADJACENT)
    assert _saga_effect(rec, off), "l'effet 1223 doit etre present (sinon le gate n'est pas exerce)"
    assert rec["target"] not in off["charged"], (
        "la cible ne doit PAS entrer dans ChargedUnitIds (deja adjacente avant le pas) ; "
        "charged=%s target=%s" % (off["charged"], rec["target"]))
    assert len(off["per_hit"]) == len(rec["live_per_hit"]), (
        "STEP_ADJACENT : le port sur-applique le +extraHits (gate `has_moved` ?) -- live n=%d %s "
        "offline n=%d %s" % (len(rec["live_per_hit"]), rec["live_per_hit"],
                             len(off["per_hit"]), off["per_hit"]))
    assert off["per_hit"] == rec["live_per_hit"], (
        "STEP_ADJACENT : live=%s offline=%s" % (rec["live_per_hit"], off["per_hit"]))


def test_no_step_grants_nothing(ragnar):
    """TEMOIN -- aucun pas du tour : ni `Moved` ni `ChargedUnitIds`. Les deux modeles coincident ;
    ce test verrouille que le port n'a rien deplace sur le seul regime deja juste avant lui."""
    rec, off = _run(ragnar, NO_STEP)
    assert off["charged"] == [], "aucun pas -> ChargedUnitIds vide, obtenu %s" % (off["charged"],)
    assert len(off["per_hit"]) == len(rec["live_per_hit"]), (
        "NO_STEP : live n=%d %s offline n=%d %s" % (len(rec["live_per_hit"]), rec["live_per_hit"],
                                                    len(off["per_hit"]), off["per_hit"]))
    assert off["per_hit"] == rec["live_per_hit"], (
        "NO_STEP : live=%s offline=%s" % (rec["live_per_hit"], off["per_hit"]))


def test_charge_beats_step_adjacent_live(ragnar):
    """Le natif SEPARE bien les deux regimes -- sinon les deux tests ci-dessus passeraient pour une
    raison triviale (aucun bonus nulle part). On compare deux mesures LIVE, pas le port."""
    rec_c, _ = _run(ragnar, CHARGE)
    rec_s, _ = _run(ragnar, STEP_ADJACENT)
    assert len(rec_c["live_per_hit"]) > len(rec_s["live_per_hit"]), (
        "le natif doit porter PLUS de coups en charge qu'en decalage adjacent -- "
        "CHARGE n=%d, STEP_ADJACENT n=%d (si egal, le montage n'exerce pas le bonus)"
        % (len(rec_c["live_per_hit"]), len(rec_s["live_per_hit"])))


def test_charge_other_board(ragnar_alt):
    """GENERALISATION du cas rouge : autre board (`C1_25`), autre seed (31337), autres cibles."""
    rec, off = _run(ragnar_alt, CHARGE)
    assert rec["target"] in off["charged"]
    assert len(off["per_hit"]) == len(rec["live_per_hit"]), (
        "CHARGE (C1_25/31337) : live n=%d %s offline n=%d %s"
        % (len(rec["live_per_hit"]), rec["live_per_hit"], len(off["per_hit"]), off["per_hit"]))
    assert off["per_hit"] == rec["live_per_hit"], (
        "CHARGE (C1_25/31337) : live=%s offline=%s" % (rec["live_per_hit"], off["per_hit"]))


def test_step_adjacent_other_board(ragnar_alt):
    """GENERALISATION du regime discriminant."""
    rec, off = _run(ragnar_alt, STEP_ADJACENT)
    assert rec["target"] not in off["charged"]
    assert len(off["per_hit"]) == len(rec["live_per_hit"]), (
        "STEP_ADJACENT (C1_25/31337) : live n=%d %s offline n=%d %s"
        % (len(rec["live_per_hit"]), rec["live_per_hit"], len(off["per_hit"]), off["per_hit"]))
    assert off["per_hit"] == rec["live_per_hit"], (
        "STEP_ADJACENT (C1_25/31337) : live=%s offline=%s" % (rec["live_per_hit"], off["per_hit"]))
