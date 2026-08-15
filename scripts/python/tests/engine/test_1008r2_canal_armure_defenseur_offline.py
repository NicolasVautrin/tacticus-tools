"""#1008-r2 -- GARDE du canal `IgnoreArmor` cote DEFENSEUR (offline, sans runner).

Ce que ce fichier empeche de revenir : la magnitude `armorIgnored` d'un effet pose sur le
DEFENSEUR n'atteignait pas le calcul de degat, parce que `get_armor_penetration` n'etait appele
que par `_attacker_effect_bonuses`. La degradation etait SILENCIEUSE (pas d'erreur, juste une
penetration a 0), et elle a survecu a une tranche entiere en se faisant passer pour un ETAGE
manquant -- alors que le lecteur natif existait.

Structure native gardee (RE : `docs/rl/case-1008r2-ignorearmor-canal-defenseur.md`) :

    <Effect>$$IgnoreArmor   (vtable +0x718, slot 94)     -> IAmountFormula
      invoque par `IdunBattle.Entities.Effects.BaseEffect$$DamageMalusForDefense` (slot 0x1a)
      ET par `IdunBattle.Entities.Effects.BaseEffect$$DamageBonusForAttack`     (slot 0x16)
      -> `DamageBonus+0x38` -> `DamageModifiers+0x28`
      -> SOMME des deux faces par
         `IdunBattle.Core.Services.DamagePrediction$$CalculateBaseDamageWithAllModifiers`
      -> argument `ignoreArmor` de `$$GetBaseDamageWithFixedPiercedArmor` :
         `armor_eff = Max(defender.GetStat(0x10) - ignoreArmor, 0)`
"""
from __future__ import annotations

import inspect

import pytest

from engine.entities.effects import (build_attacker_modifiers_from_effects,
                                     build_defender_modifiers_from_effects)
from engine.entities.effects.base import BaseEffect
from engine.entities.effects.factory import EFFECT_CLASSES, EffectFactory

#: L'effet DEFENSEUR de reference : `EffectType` 1583, pose sur `Target` par
#: `IdunBattleLogic.Entities.Abilities.Triggered.Loki.Helspear_BuffActiveAbility$$CreateBehaviour`.
HELSPEAR = "Helspear_IgnoreArmor"
#: Palier TERTIAIRE de la relique (#1007) -- surtout pas le palier passif.
ABLVL = 50
#: `attacker_ctx` minimal qui QUALIFIE l'attaquant comme une unite (gate `IsUnit(Caster)`).
CTX_UNITE = {"id": 7, "is_normal_attack": True}


def _helspear(ability_level: int = ABLVL):
    e = EffectFactory.create({"name": HELSPEAR, "level": 1})
    e.ability_level = ability_level
    return e


def test_magnitude_lue_et_non_degeneree():
    """`ConfigVar(AbilityVariableType.armorIgnored = 0x40)` rend une valeur NON NULLE et
    CROISSANTE avec le niveau. Un temoin nul rendrait tous les autres etages vacants."""
    bas = _helspear(1).ignore_armor()
    haut = _helspear(ABLVL).ignore_armor()
    assert bas is not None and haut is not None, "armorIgnored introuvable dans le gameconfig"
    assert bas > 0 and haut > 0, f"magnitude degeneree: bas={bas} haut={haut}"
    assert haut > bas, f"armorIgnored doit croitre avec le niveau: L1={bas} L{ABLVL}={haut}"


def test_le_canal_defenseur_mord():
    """LE CRAN CENTRAL. Sans le correctif, `armor_penetration` restait a 0."""
    attendu = _helspear().ignore_armor()
    acc = build_defender_modifiers_from_effects([_helspear()], attacker_ctx=CTX_UNITE)
    assert acc.armor_penetration == attendu, (
        f"la penetration du DEFENSEUR n'atteint pas DamageModifiers+0x28 "
        f"(attendu {attendu}, obtenu {acc.armor_penetration})")


def test_gate_is_unit_caster_ferme_sans_attaquant_qualifie():
    """`get_OwnerIsTarget & IsUnit(Caster)` -- attaquant non qualifiable => degradation
    RESTRICTIVE (on n'active pas une vulnerabilite qu'on ne peut pas justifier)."""
    for ctx in (None, {}, {"is_normal_attack": True}):
        acc = build_defender_modifiers_from_effects([_helspear()], attacker_ctx=ctx)
        assert acc.armor_penetration == 0, f"gate ouverte a tort pour attacker_ctx={ctx!r}"


def test_pas_de_gate_attaque_normale_sur_helspear():
    """Le trigger natif de CET effet est `get_OwnerIsTarget & IsUnit(Caster)` : il ne regarde
    PAS la nature de l'attaque. Recopier la gate `IsNormalAttack` de `PowerTrip` serait un port
    FAUX -- les deux triggers sont mesures et ils different."""
    ctx_special = dict(CTX_UNITE, is_normal_attack=False)
    acc = build_defender_modifiers_from_effects([_helspear()], attacker_ctx=ctx_special)
    assert acc.armor_penetration == _helspear().ignore_armor(), (
        "une gate `is_normal_attack` a ete introduite sur Helspear : le trigger natif n'en a pas")


def test_non_regression_face_attaquant():
    """La face ATTAQUANT ne bouge pas -- et son porteur, lui, EST gate `IsNormalAttack`
    (`PowerTrip_IgnoreArmorEffect$$CreateEffectDamageBonusForAttack`)."""
    pt = EffectFactory.create({"name": "PowerTrip_IgnoreArmor", "level": 1})
    pt.ability_level = ABLVL
    normal = build_attacker_modifiers_from_effects([pt], is_normal_attack=True)
    special = build_attacker_modifiers_from_effects([pt], is_normal_attack=False)
    assert normal.armor_penetration > 0, "temoin ATTAQUANT degenere : PowerTrip ne penetre plus"
    assert special.armor_penetration == 0, (
        "la gate IsNormalAttack de PowerTrip a saute (i2 : << NORMAL attacks ignore X Armour >>)")


def test_un_effet_defenseur_sans_penetration_reste_a_zero():
    """Le canal neuf ne doit rien inventer sur les effets qui ne surchargent pas le slot."""
    autre = EffectFactory.create({"name": "Stunned_DamageModifier", "level": 1})
    acc = build_defender_modifiers_from_effects([autre], attacker_ctx=CTX_UNITE)
    assert acc.armor_penetration == 0


def test_toutes_les_surcharges_acceptent_attacker_ctx():
    """DERIVE, jamais enumere : toute surcharge de `get_armor_penetration` doit accepter le
    kwarg `attacker_ctx`, sinon le site DEFENSEUR leve `TypeError` a l'appel -- une panne dure
    qui n'apparaitrait que sur le board ou ce porteur est present."""
    surcharges = {}
    for nom, cls in EFFECT_CLASSES.items():
        fn = getattr(cls, "get_armor_penetration", None)
        if fn is not None and fn is not BaseEffect.get_armor_penetration:
            surcharges[nom] = fn
    # Le test ne peut pas rendre zero en silence : un ensemble vide passerait pour vert.
    assert surcharges, "aucune surcharge trouvee -- le recenseur est casse, pas le code"
    manquants = [nom for nom, fn in surcharges.items()
                 if "attacker_ctx" not in inspect.signature(fn).parameters]
    assert not manquants, f"surcharges sans kwarg `attacker_ctx` (TypeError au site defenseur): {manquants}"


@pytest.mark.parametrize("nom", ["StrikeFromTheShadows"])
def test_porteur_defenseur_non_encore_porte_est_declare(nom):
    """#1008-r4 : `StrikeFromTheShadows` (`EffectType` 1549) porte le MEME canal defenseur et
    n'est PAS au registre. Ce test ECRIT l'absence au lieu de la laisser muette : le jour ou
    quelqu'un l'ajoute, il rougit et rappelle que sa gate (`IsRangedAttack & get_OwnerIsTarget`)
    DIFFERE de celle de Helspear et ne doit pas etre recopiee."""
    assert nom not in EFFECT_CLASSES, (
        f"{nom} est entre au registre : porter sa gate `IsRangedAttack & get_OwnerIsTarget` "
        f"(surtout PAS celle de Helspear) et retirer ce garde-fou -- cf. #1008-r4")
