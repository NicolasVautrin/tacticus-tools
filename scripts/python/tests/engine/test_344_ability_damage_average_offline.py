"""#344 -- la PREDICTION d'ability moyenne minDmg/maxDmg par DEUX chaines natives, pas une.

Le 6e argument que `<X>Playbook$$MakeDamagePredictions` passe a
`ComparablePlaybook<T>$$GenerateMultiHitAttackPredictions` prend l'une de DEUX formes, portees
chacune par UN corps DEDUPLIQUE (donc un seul nom ghidra pour tous ses proprietaires) :

  (a) `<X>Ability$$GetDamageAmountMain`  (corps etiquete
      `IdunBattleLogic.Entities.Abilities.Active.Loki.StranglethornCannonAbility$$GetDamageAmountMain`)
      -> `IdunBattle.Entities.Abilities.AActiveAbility$$MinMaxDamageAverage` = `Half(Sum(...), 0)`
      -> `IdunBattle.Entities.Formulas.DivideAmount$$Calculate`
      -> `IdunBattle.DSL.AAmountFormula$$RoundFix64Result(., 0)` = demi-vers-le-PAIR.

  (b) `<X>Ability$$GetDamage`  (corps etiquete
      `IdunBattleLogic.Entities.Abilities.Active.Loki.VigilanceEternalAbility$$GetDamage`)
      -> `AActiveAbility$$MinMaxDamage(state, isPrediction: FALSE)` = `RandomAmount(min, max)`,
      pris par le playbook au slot 4 = `IdunBattle.DSL.AAmountFormula$$CalculateAverage` = TRONCATURE.

Elles ne divergent que sur `minDmg + maxDmg = 3 mod 4`, d'exactement 1. Les DEUX faces sont mesurees
live par `probe_344_ability_damage_average.py` (4 montages, 2 par famille).

Ce que la garde verrouille :
A. `AActiveAbility.get_damage` rend la moyenne de la BONNE famille, sur un couple `3 mod 4` -- et
   les deux familles y DIFFERENT (sans quoi le test ne discriminerait rien) ;
B. les deux registres sont DISJOINTS, non vides, et chaque id resout a un nom d'ability gameconfig ;
C. les trois sites voisins de #344 sont cables sur la primitive de LEUR artefact -- verifie sur
   l'objet importe par le module, pas sur le texte du fichier ;
D. `IdunBattle.Core.HitDamage$$GetDamage` TRONQUE (division entiere C, aucun Fix64) : c'est le
   verdict "rien a changer" du site `runner/operations/damage_hits` ;
E. `UnitContext.normal_base` n'existe plus (dead code retire : aucun symbole natif, aucun appelant).

ASCII only.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

PYDIR = Path(__file__).resolve().parents[2]                 # scripts/python
sys.path.insert(0, str(PYDIR))

import gameconfig as GC                                                          # noqa: E402
from engine.dsl.base import calculate_average, _round_fix64                      # noqa: E402
from engine.services.min_max_damage import min_max_avg                           # noqa: E402
from engine.entities.abilities.ability_configuration import AbilityConfiguration  # noqa: E402
from engine.entities.abilities.active_ability import (AActiveAbility,            # noqa: E402
                                                      _PREDICTION_MINMAX_AVERAGE,
                                                      _PREDICTION_MINMAX_RANDOM_READ)
from engine.entities.unit_context import UnitContext                             # noqa: E402
from engine.runner.operations.damage_hits import HitDamage                       # noqa: E402


def _ability(ability_type: int, mn: int, mx: int) -> AActiveAbility:
    """Une ability SYNTHETIQUE : la config ne porte que `minDmg`/`maxDmg` au niveau 1, ce qui isole
    exactement l'etage mesure (`GetVariableForLevel` -> moyenne)."""
    cfg = AbilityConfiguration(name="synthetique", variables={"minDmg": [mn], "maxDmg": [mx]},
                               constants={})
    return AActiveAbility(ability_type=ability_type, caster=UnitContext(entity_id=1),
                          config=cfg, ability_state={"level": 1, "multiplier": 100})


# Couples `3 mod 4` : le SEUL regime ou les deux familles se separent (ToEven = trunc + 1).
DIVERGENT = [(54, 61), (17, 22), (29, 38), (2758, 2765), (0, 3), (1, 2)]
# Couples hors `3 mod 4` : les deux familles doivent COINCIDER -- c'est ce qui rend un montage non
# pilote incapable de conclure quoi que ce soit.
AGREEING = [(54, 62), (14, 19), (25, 32), (0, 1), (2, 2)]

A_ID = 1042      # FlailSwing            -- famille (a), MESUREE live
B_ID = 1150      # PlasmaCannon          -- famille (b), MESUREE live


def test_get_damage_follows_the_family_of_its_playbook():
    """A : sur `3 mod 4`, une ability de la famille (a) MONTE et une de la famille (b) TRONQUE --
    et l'ecart vaut exactement 1."""
    assert A_ID in _PREDICTION_MINMAX_AVERAGE
    assert B_ID in _PREDICTION_MINMAX_RANDOM_READ
    for mn, mx in DIVERGENT:
        assert (mn + mx) % 4 == 3, "couple %d+%d hors du regime discriminant" % (mn, mx)
        got_a, got_b = _ability(A_ID, mn, mx).get_damage(), _ability(B_ID, mn, mx).get_damage()
        assert got_a == min_max_avg(mn, mx), (
            "famille (a) `MinMaxDamageAverage` sur (%d,%d) : %d, attendu %d (demi-vers-le-pair)"
            % (mn, mx, got_a, min_max_avg(mn, mx)))
        assert got_b == calculate_average(mn, mx), (
            "famille (b) `RandomAmount` + `CalculateAverage` sur (%d,%d) : %d, attendu %d "
            "(troncature)" % (mn, mx, got_b, calculate_average(mn, mx)))
        assert got_a == got_b + 1, (
            "les deux familles doivent differer d'exactement 1 sur `3 mod 4` -- sinon la garde ne "
            "discrimine RIEN (a=%d b=%d)" % (got_a, got_b))


def test_the_two_families_agree_outside_3_mod_4():
    """A (contre-epreuve) : hors `3 mod 4` elles coincident. Un montage tombant la ne prouve rien."""
    for mn, mx in AGREEING:
        assert (mn + mx) % 4 != 3
        assert _ability(A_ID, mn, mx).get_damage() == _ability(B_ID, mn, mx).get_damage()


def test_unknown_ability_falls_back_on_the_truncating_family():
    """A (defaut) : une ability qui n'est dans AUCUN des deux registres n'est pas "lue (b)", elle est
    NON LUE -- et retombe sur le comportement historique du port (troncature). Le verrouiller evite
    qu'un futur changement de defaut deplace silencieusement 60+ abilities."""
    unknown = 999999
    assert unknown not in _PREDICTION_MINMAX_AVERAGE
    assert unknown not in _PREDICTION_MINMAX_RANDOM_READ
    assert _ability(unknown, 54, 61).get_damage() == calculate_average(54, 61)


def test_registries_are_disjoint_and_resolve_to_real_abilities():
    """B : les deux ensembles viennent des xrefs de DEUX corps distincts -- ils ne peuvent pas se
    recouvrir, et chaque id doit resoudre a une ability du gameconfig portant `minDmg`."""
    assert _PREDICTION_MINMAX_AVERAGE and _PREDICTION_MINMAX_RANDOM_READ
    inter = _PREDICTION_MINMAX_AVERAGE & _PREDICTION_MINMAX_RANDOM_READ
    assert not inter, (
        "une ability ne peut pas relever des DEUX corps natifs a la fois : %s" % sorted(inter))
    for aid in sorted(_PREDICTION_MINMAX_AVERAGE | _PREDICTION_MINMAX_RANDOM_READ):
        name = GC.ability_name(aid)
        assert name, "id %d ne resout a aucune ability (`ActiveAbilityType`)" % aid
        cfg = GC.ability(name) or {}
        assert (cfg.get("variables") or {}).get("minDmg"), (
            "%s (%d) n'a pas de `minDmg` en config : il n'aurait rien a moyenner" % (name, aid))


def test_neighbouring_sites_are_wired_on_their_own_native_average():
    """C : chaque site consomme la primitive de SON artefact. Verifie sur l'objet importe par le
    module (pas sur le texte), comme la garde Fury de #339."""
    import engine.entities.abilities.active_ability as AA
    import engine.runner.abilities.votann as V
    import engine.runner.abilities.darkangels as D
    import engine.playbook.fury_of_the_ancients as F

    # `active_ability` arbitre entre les DEUX familles : il lui faut les deux primitives.
    assert AA._round_fix64 is _round_fix64 and AA.calculate_average is calculate_average

    # votann : `AncestralFortuneAbility$$GetAttackTarget` passe `MinMaxDamage(isPrediction: true)`
    # = `Half(Sum(...), 0)`, evalue par `SortUnitsByDamageUtilitySelector$$Select` au slot 1
    # (`Calculate`) -> `DivideAmount$$Calculate` -> `RoundFix64Result(., 0)`.
    assert V._round_fix64 is _round_fix64, (
        "`votann` n'importe plus `AAmountFormula$$RoundFix64Result` : son collapse de cible "
        "repasserait par une AUTRE moyenne que celle du natif")
    assert not hasattr(V, "calculate_average"), (
        "`votann` importe `CalculateAverage` : ce n'est PAS son artefact natif (#344)")

    # darkangels : `SortAttackersByDamagePredictionSelector.<Select>b__0` finit par `MinMaxDamage$$Avg`.
    assert D.min_max_avg is min_max_avg, (
        "`darkangels` n'importe plus `MinMaxDamage$$Avg` : la cle de tri des attaquants "
        "repasserait par une AUTRE moyenne")

    # fury : PIEGE de #344 -- il RESSEMBLE aux deux autres et n'en est PAS (`CalculateAverage`).
    assert F.calculate_average is calculate_average
    assert not hasattr(F, "min_max_avg")


def test_hit_damage_midpoint_truncates():
    """D : `IdunBattle.Core.HitDamage$$GetDamage` fait `(Max + Min) / 2` en division ENTIERE C --
    aucun Fix64 sur ce chemin. Sur `3 mod 4` il rend donc UNE unite de MOINS que les deux moyennes
    Fix64, et c'est le comportement NATIF : ne pas l'aligner."""
    for mn, mx in DIVERGENT:
        got = HitDamage(mn, mx).get_damage(rng=None, use_midpoint=True)
        assert got == calculate_average(mn, mx) == (mn + mx) // 2
        assert got == min_max_avg(mn, mx) - 1, (
            "sur `3 mod 4`, `HitDamage$$GetDamage` doit rester UNE unite SOUS `MinMaxDamage$$Avg` "
            "(%d vs %d) -- sinon la garde ne temoigne plus de la distinction" % (got, min_max_avg(mn, mx)))
    # Min == Max court-circuite le midpoint (aucun tirage, aucune moyenne).
    assert HitDamage(7, 7).get_damage(rng=None, use_midpoint=True) == 7


def test_unit_context_no_longer_exposes_normal_base():
    """E : `normal_base` (moyenne TRONQUEE sans artefact natif, zero appelant) est retiree."""
    assert not hasattr(UnitContext, "normal_base"), (
        "`UnitContext.normal_base` est revenue : c'etait une moyenne sans symbole natif ni "
        "consommateur (#344) -- si un chemin en a besoin, il doit citer SON artefact")
