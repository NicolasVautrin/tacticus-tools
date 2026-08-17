"""#106 -- fork `IsMeleeAttack` : les gates NATURE-DU-COUP des deux axes doivent s'accorder (offline pur).

RE (decompile = verite) -- `IdunBattle.Core.Services.BattleQuery$$IsMeleeAttack` et
`IdunBattle.Core.Services.BattleQuery$$IsRangedAttack` (consommes par
`IdunBattle.Entities.Triggers.IsMeleeAttackAbilityTrigger$$ShouldTrigger` /
`IdunBattle.Entities.Triggers.IsRangedAttackAbilityTrigger$$ShouldTrigger`, qui materialisent les noeuds
`IdunBattleLogic.Entities.DSLTriggers$$IsMeleeAttack` / `$$IsRangedAttack` des `CreateEffectDamageBonusForAttack`)
partent TOUS DEUX de `IdunBattle.Core.Services.BattleQuery$$GetAbilityAttackRangeType(ability du coup)` :

    Nullable<AbilityOrEffect> VIDE  -> rangeType 0      -> melee=FALSE  ranged=FALSE
    0 = None                        -> melee=FALSE  ranged=FALSE   (ni l'un ni l'autre)
    1 = Melee                       -> melee=TRUE   ranged=FALSE
    2 = Ranged                      -> melee=FALSE  ranged=TRUE
    3 = Both                        -> HasFlag(unit,0x15) ? ranged : AreUnitsInMelee(attPos,tgtPos)

=> le natif rend un BOOL, jamais un tri-etat, et surtout il ne se rabat JAMAIS sur "melee" quand la nature
n'est pas determinee. Cote port, `is_ranged=None` (facade qui ne threade pas la nature) doit donc faire
TAIRE les DEUX familles de gates.

LE FORK CORRIGE : `Waaagh_ExtraDamageEffect` (axe DEGAT,
`IdunBattle.Entities.Effects.Loki.Waaagh_ExtraDamageEffect$$CreateEffectDamageBonusForAttack`) et
`Waaagh_ExtraHitsEffect` (axe COUPS,
`IdunBattle.Entities.Effects.Loki.Waaagh_ExtraHitsEffect$$CreateEffectHitsBonusForAttack`) portent la
**MEME condition native** `IsNormalAttack & IsMeleeAttack & get_OwnerIsCaster`. Le port representait ce
MEME fait de deux facons divergentes sur nature inconnue : `if is_ranged:` (None FALSY -> la contribution
DEGAT s'appliquait) contre `att_ctx["is_melee"] is not True` (None -> la contribution COUPS se taisait).
Ce test verrouille l'accord des deux axes, nature par nature.

OFFLINE PUR (aucun runner, aucune session) : ces gates sont des predicats sur les arguments, la magnitude
vient du gameconfig sur disque. ASCII-only.
"""
from __future__ import annotations

import pytest

from engine.entities.effects.base import is_melee_attack, is_ranged_attack
from engine.entities.effects.loki.extra_damage import (
    BeastSlayerExtraDmgEffect, CrushingStrikeEffect, HeavyWeaponExtraDmgEffect,
    RangedSpecialistEffect,
)
from engine.entities.effects.loki.hits import (
    BigTargetAdjacentEffect, CamouflageHitReductionEffect, DiminutiveHitReductionEffect,
    LightCoverEffect, ParryEffect,
)
from engine.entities.effects.loki.status import WaaaghExtraDamageEffect, WaaaghExtraHitsEffect

MELEE, RANGED, UNKNOWN = False, True, None

# axe COUPS DEFENSEUR : la signature est `is_melee` (et non `is_ranged`) -> meme nature, autre convention.
M_MELEE, M_RANGED, M_UNKNOWN = True, False, None


def test_battlequery_predicates_mirror_native_truth_table():
    """`BattleQuery$$IsMeleeAttack` / `$$IsRangedAttack` : bool, jamais un rabat sur melee."""
    assert (is_melee_attack(MELEE), is_ranged_attack(MELEE)) == (True, False)
    assert (is_melee_attack(RANGED), is_ranged_attack(RANGED)) == (False, True)
    # rangeType None / ability absente du contexte : les DEUX predicats sont FAUX (cf. docstring).
    assert (is_melee_attack(UNKNOWN), is_ranged_attack(UNKNOWN)) == (False, False)


@pytest.mark.parametrize("nature,expect_contrib", [(MELEE, True), (RANGED, False), (UNKNOWN, False)])
def test_waaagh_damage_and_hits_axes_agree(nature, expect_contrib):
    """Les DEUX canaux Waaagh (1100 degat / 1101 coups) portent la MEME condition native -> meme verdict."""
    dmg = WaaaghExtraDamageEffect(name="Waaagh_ExtraDamage", effect_type=1100, ability_level=50,
                                  active_ability_level=50)
    hits = WaaaghExtraHitsEffect(name="Waaagh_ExtraHits", effect_type=1101, ability_level=50,
                                 active_ability_level=50)
    d = dmg.create_effect_damage_bonus_for_attack(is_ranged=nature, is_normal_attack=True)
    h = hits.create_effect_hits_bonus_for_attack(True, {"is_melee": is_melee_attack(nature)})
    assert (d is not None) == expect_contrib, f"axe DEGAT: nature={nature} -> {d!r}"
    assert (h is not None) == expect_contrib, f"axe COUPS: nature={nature} -> {h!r}"
    assert (d is not None) == (h is not None), (
        f"FORK: les deux canaux jumeaux divergent sur nature={nature} (degat={d!r} coups={h!r})")


@pytest.mark.parametrize("nature,expect", [(MELEE, True), (RANGED, False), (UNKNOWN, False)])
def test_melee_only_damage_bonuses_stay_silent_on_unknown_nature(nature, expect):
    """Gates `IsMeleeAttack` de l'axe DEGAT : contribution SSI la nature est PROUVEE melee."""
    cs = CrushingStrikeEffect(name="CrushingStrike", effect_type=1186)
    got = cs.create_effect_damage_bonus_for_attack(is_ranged=nature, has_moved=False,
                                                   is_normal_attack=True)
    assert (got is not None) == expect, f"CrushingStrike nature={nature} -> {got!r}"

    bs = BeastSlayerExtraDmgEffect(name="BeastSlayer_ExtraDmg")
    got_bs = bs.create_effect_damage_bonus_for_attack(is_ranged=nature,
                                                      target_traits=frozenset({"Vehicle"}))
    assert (got_bs is not None) == expect, f"BeastSlayer nature={nature} -> {got_bs!r}"


@pytest.mark.parametrize("nature,expect", [(MELEE, False), (RANGED, True), (UNKNOWN, False)])
def test_ranged_only_damage_bonuses_stay_silent_on_unknown_nature(nature, expect):
    """Gates `IsRangedAttack` de l'axe DEGAT : contribution SSI la nature est PROUVEE distance
    (deja le cas avant #106 -- verrou de non-regression du foyer partage)."""
    rs = RangedSpecialistEffect(name="RangedSpecialist")
    got_rs = rs.create_effect_damage_bonus_for_attack(is_ranged=nature)
    assert (got_rs is not None) == expect, f"RangedSpecialist nature={nature} -> {got_rs!r}"

    hw = HeavyWeaponExtraDmgEffect(name="HeavyWeapon_ExtraDmg", effect_type=1008)
    got_hw = hw.create_effect_damage_bonus_for_attack(is_ranged=nature, has_moved=False)
    assert (got_hw is not None) == expect, f"HeavyWeapon nature={nature} -> {got_hw!r}"


# --------------------------------------------------------- #122 : axe COUPS, cote DEFENSEUR
#
# Les triggers sont LUS au decompile (jamais deduits du nom) :
#   IdunBattle.Entities.Effects.Loki.ParryEffect$$CreateEffectHitsBonusForAttack
#       -> OwnerIsTarget & IsMeleeAttack
#   IdunBattle.Entities.Effects.Loki.LightCoverEffect$$CreateEffectHitsBonusForAttack
#       -> AreEqual(Tiles(coverPatch), Tiles(Target)) & op_LogicalNot(IsMeleeAttack)
#   IdunBattleLogic.Entities.Abilities.Triggered.Loki.Camouflage_HitReductionEffect$$CreateEffectHitsBonusForAttack
#       -> OwnerIsTarget & IsRangedAttack
#   IdunBattle.Entities.Effects.Loki.BigTargetAdjacentEffect$$CreateEffectHitsBonusForAttack
#       -> OwnerIsTarget & IsRangedAttack
#   IdunBattle.Entities.Effects.Loki.Diminutive_HitReductionEffect$$CreateEffectHitsBonusForAttack
#       -> OwnerIsTarget SEUL (aucun gate de nature)
#
# La distinction qui compte sur nature INCONNUE (`rangeType 0` : les DEUX predicats faux) :
# `!IsMeleeAttack` est VRAI (LightCover s'applique) alors qu'`IsRangedAttack` est FAUX
# (Camouflage/BigTarget se taisent). Confondre les deux = le bug #122.

@pytest.mark.parametrize("nature,parry,light_cover,camouflage,big_target", [
    (M_MELEE,   True,  False, False, False),
    (M_RANGED,  False, True,  True,  True),
    (M_UNKNOWN, False, True,  False, False),
])
def test_defender_hits_gates_mirror_native_triggers(nature, parry, light_cover, camouflage,
                                                    big_target):
    """Table de verite des gates de NATURE du canal de coups DEFENSEUR (#122)."""
    p = ParryEffect(name="Parry_ReduceHits").create_effect_hits_malus_for_defense(nature)
    assert (p is not None) == parry, f"Parry nature={nature} -> {p!r}"

    lc = LightCoverEffect(name="LightCover").create_effect_hits_malus_for_defense(
        nature, defender_on_cover=True)
    assert (lc is not None) == light_cover, f"LightCover nature={nature} -> {lc!r}"

    cam = CamouflageHitReductionEffect(
        name="Camouflage_HitReduction", effect_type=1134).create_effect_hits_malus_for_defense(
            nature, dist=1)
    assert (cam is not None) == camouflage, f"Camouflage nature={nature} -> {cam!r}"

    bt = BigTargetAdjacentEffect(name="BigTarget_AdjacentEffect").create_aura_hits_malus_for_defense(
        {"is_melee": nature, "owner_id": 1, "tgt_id": 2, "owner_team": 0, "tgt_team": 0,
         "owner_pos": (3, 3), "t_pos": (3, 4)})
    assert (bt is not None) == big_target, f"BigTarget nature={nature} -> {bt!r}"


@pytest.mark.parametrize("nature", [M_MELEE, M_RANGED, M_UNKNOWN])
def test_diminutive_has_no_nature_gate(nature):
    """`Diminutive_HitReduction` = `OwnerIsTarget` SEUL : la reduction s'applique a TOUTE attaque,
    quelle que soit la nature (temoin negatif du test precedent : si Diminutive se mettait a suivre la
    nature, c'est que le gate a ete recopie au mauvais endroit)."""
    d = DiminutiveHitReductionEffect(
        name="Diminutive_HitReduction").create_effect_hits_malus_for_defense(nature)
    assert d is not None, f"Diminutive nature={nature} -> {d!r} (aucun gate de nature au decompile)"


def test_no_nature_means_no_side_wins():
    """Nature inconnue : AUCUNE des deux familles ne contribue (le natif ne penche d'aucun cote)."""
    melee_only = [
        CrushingStrikeEffect(name="CrushingStrike", effect_type=1186)
        .create_effect_damage_bonus_for_attack(is_ranged=UNKNOWN, has_moved=False),
        WaaaghExtraDamageEffect(name="Waaagh_ExtraDamage", effect_type=1100, ability_level=50,
                                active_ability_level=50)
        .create_effect_damage_bonus_for_attack(is_ranged=UNKNOWN),
    ]
    ranged_only = [
        RangedSpecialistEffect(name="RangedSpecialist")
        .create_effect_damage_bonus_for_attack(is_ranged=UNKNOWN),
        HeavyWeaponExtraDmgEffect(name="HeavyWeapon_ExtraDmg", effect_type=1008)
        .create_effect_damage_bonus_for_attack(is_ranged=UNKNOWN, has_moved=False),
    ]
    assert melee_only == [None, None], f"melee-only applique sur nature inconnue: {melee_only}"
    assert ranged_only == [None, None], f"ranged-only applique sur nature inconnue: {ranged_only}"
