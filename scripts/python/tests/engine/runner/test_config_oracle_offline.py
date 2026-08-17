"""Gardes OFFLINE des oracles CONFIG (`_config_oracle`) -- #110.

Convertir « `assert pierce == 40` » en « `assert pierce == damage_profile_pierce("Power")` » ne vaut que si
l'oracle a DEUX proprietes, et elles se testent ici, sans jeu :

  (1) IL ECHOUE quand la cle n'existe pas. Un `GC.<lookup>(...) or 0` rendrait 0, l'assertion comparerait
      0 a 0 et resterait VERTE en n'ayant plus rien verifie -- exactement le faux negatif qu'on chasse.
  (2) IL LIT LA CLE NOMMEE. Des cles voisines partagent la valeur (`parryHitReduction`,
      `camouflageHitReduction_1`, `diminutiveHitReduction` valent 1 ; toutes trois passent par le meme
      `GetNumberConstant(config, 0x2c)`, chacune depuis la config de SON ability). Lire la voisine passe
      vert aujourd'hui et devient faux au prochain rebalance -- donc la cle est un argument, et une cle
      inconnue doit echouer plutot que se rabattre sur quoi que ce soit.

ASCII only. Aucune session Frida requise (lecture gameconfig seule).
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))      # import du helper sibling
from _config_oracle import (ability_damage_profile,          # noqa: E402
                            ability_variable_levels,
                            assert_ability_damage_profile,
                            damage_profile_pierce,
                            global_constant,
                            trait_variable)


# ------------------------------------------------------------------ (1) cle absente => ECHEC, jamais 0

def test_missing_keys_fail_loudly():
    """Chaque oracle ECHOUE sur une cle inconnue. Sans ca, l'assertion appelante deviendrait vacue."""
    with pytest.raises(AssertionError):
        damage_profile_pierce("ProfilQuiNExistePas")
    with pytest.raises(AssertionError):
        trait_variable("GetStuckIn", "getStuckInChanceQuiNExistePas")
    with pytest.raises(AssertionError):
        global_constant("firstAidRecoveryQuiNExistePas")
    with pytest.raises(AssertionError):
        ability_variable_levels("HypersensoryAbilities", "hpPctQuiNExistePas")
    with pytest.raises(AssertionError):
        assert_ability_damage_profile("FlailSwing", "ProfilQuiNExistePas")


# ------------------------------------------------------------------ (2) la cle NOMMEE est load-bearing

def test_neighbouring_hit_reduction_keys_are_indistinguishable_by_value():
    """Les trois `*HitReduction` du slot 0x2c partagent leur valeur : SEUL le nom les separe.

    C'est la raison d'etre de l'argument `key` -- si un test lisait la voisine, il serait vert AUJOURD'HUI
    et faux des que l'une des trois bouge. Ce test documente l'ambiguite et echouera si elle disparait
    (auquel cas la garde peut etre relachee)."""
    parry = trait_variable("Parry", "parryHitReduction")
    camouflage = trait_variable("Camouflage", "camouflageHitReduction_1")
    diminutive = trait_variable("Diminutive", "diminutiveHitReduction")
    assert parry == camouflage == diminutive, (
        f"les cles 0x2c ne partagent plus leur valeur (parry={parry} camouflage={camouflage} "
        f"diminutive={diminutive}) -- la garde « lire la BONNE cle » peut etre reevaluee")


def test_damage_profiles_used_by_the_suite_are_distinct():
    """Les profils dont la suite derive un percage ont des `PiercingRatio` DISTINCTS : une assertion qui
    lirait le mauvais profil vire au rouge au lieu de passer par coincidence."""
    used = ["Power", "HeavyRound", "Energy", "DirectDamage", "Physical", "Las"]
    ratios = {p: damage_profile_pierce(p) for p in used}
    assert len(set(ratios.values())) == len(used), \
        f"deux profils partagent leur PiercingRatio -- une lecture de profil erronee passerait : {ratios}"


# ------------------------------------------------------------------ profil declare par l'ability

def test_ability_damage_profile_reads_the_config_constant():
    """Les abilities dont le behaviour natif appelle `AbilityConfiguration$$GetDamageProfile` exposent bien
    `constants.damageProfile` ; celles qui passent un litteral `DamageProfileType` a
    `IdunBattleLogic.Entities.DSLBehaviors$$AttackWithAttackDamage` (HarvesterOfSouls -> 0x13 = HeavyRound) n'ont RIEN a y lire."""
    for ability, profile in (("FlailSwing", "Power"), ("MartialApotheosis", "Energy"),
                             ("HarbingerOfDestruction", "DirectDamage"),
                             ("DestroyerHive", "DirectDamage")):
        assert_ability_damage_profile(ability, profile)
    assert ability_damage_profile("HarvesterOfSouls") is None, \
        "HarvesterOfSouls declare desormais un damageProfile en config -- le litteral 0x13 est a re-verifier"
