"""CLIQUET OFFLINE #1049 -- les deux passifs de SUMMON portes par la tranche, cotes STRUCTURE.

Ce fichier ne monte AUCUN runner : il fige ce qu'un rejeu live ne peut PAS voir tomber
silencieusement -- l'appariement ability -> effet, les ORDINAUX ecrits aux sites, la
QUALIFICATION D'ENUM (le meme ordinal nomme autre chose ailleurs), et la magnitude lue au
gameconfig.

  * `RedThirst` (`TriggeredAbilityType` 0x4e1 = 1249) -> owner-effect PERMANENT
    `RedThirst_ExtraDamageAndHit` (0x52a = 1322).
  * `CursedOfTheWalkingPox` (`TriggeredAbilityType` 0x430 = 1072) -> `ABILITY_TRIGGERS`.

⚠ **L'ORDINAL 1072 NOMME AUTRE CHOSE DANS `ActiveAbilityType` (`MyWillBeDone`)**, et le namespace
natif de la classe est `...Abilities.**Active**.Loki` : deux invitations a se tromper d'enum, dont
aucune ne leverait la moindre erreur. L'etage 3 les tient ensemble.

ASCII only.
"""
from __future__ import annotations

from dataclasses import fields

import pytest

import gameconfig as GC
from engine.dsl.event_trigger_type import EventTriggerType
from engine.entities.ability_constant_type import AbilityConstantType
from engine.entities.ability_variable_type import AbilityVariableType
from engine.entities.active_ability_type import ActiveAbilityType
from engine.entities.effect_type import EffectType
from engine.entities.effects.factory import ABILITY_INIT_OWNER_EFFECTS, EFFECT_CLASSES
from engine.entities.effects.loki.hits import RedThirstExtraDamageAndHitEffect
from engine.entities.stats import StatType
from engine.entities.traits.unit_trait import UnitTrait
from engine.entities.triggered_ability_type import TriggeredAbilityType
from engine.entities.unit_context import UnitContext
from engine.runner.operations.spawn import SpawnUnitOperation, _COPY_OWNER_STATS
from engine.runner.operations.triggers.dispatch.registry import ABILITY_TRIGGERS
from engine.runner.operations.triggers.loki.cursed_of_the_walking_pox import (
    CursedOfTheWalkingPoxSummonAbility)

#: Les fichiers qui peuvent faire MENTIR ce cliquet -- la fermeture COMPLETE de ses imports, pas
#: les seuls foyers que la tranche a edites : un renumerotage d'enum, un mirror regenere ou un
#: gameconfig migre le feraient tomber sans qu'aucun des trois modules de port n'ait bouge.
DECLENCHEUR = {
    "chemins": (
        "scripts/python/engine/entities/effects/factory.py",
        "scripts/python/engine/entities/effects/loki/hits.py",
        "scripts/python/engine/runner/operations/spawn.py",
        "scripts/python/engine/runner/operations/triggers/dispatch/registry.py",
        "scripts/python/engine/runner/operations/triggers/loki/cursed_of_the_walking_pox.py",
        "scripts/python/engine/entities/triggered_ability_type.py",
        "scripts/python/engine/entities/active_ability_type.py",
        "scripts/python/engine/entities/effect_type.py",
        "scripts/python/engine/entities/ability_constant_type.py",
        "scripts/python/engine/entities/ability_variable_type.py",
        "scripts/python/engine/entities/traits/unit_trait.py",
        "scripts/python/engine/dsl/event_trigger_type.py",
        "scripts/python/gameconfig.py",
    ),
    "build": False,
    "toujours": False,
    "raison": "Purement offline : aucun runner, aucun RPC, aucune lecture du binaire. Il fige "
              "l'appariement ability -> effet, les ordinaux ECRITS aux sites et la magnitude lue "
              "au gameconfig ; seuls ces treize fichiers peuvent le faire mentir.",
}


# --------------------------------------------------------------- etage 1 : REGISTRES

def test_registres_les_deux_passifs_sont_cables():
    """`RedThirst` arrive par l'owner-effect, `CursedOfTheWalkingPox` par le trigger : DEUX
    registres DIFFERENTS, et se tromper de registre donne un passif silencieusement inerte."""
    assert EFFECT_CLASSES.get("RedThirst_ExtraDamageAndHit") is RedThirstExtraDamageAndHitEffect
    assert ABILITY_INIT_OWNER_EFFECTS.get("RedThirst") == ["RedThirst_ExtraDamageAndHit"]
    assert ABILITY_TRIGGERS.get("CursedOfTheWalkingPox") == [CursedOfTheWalkingPoxSummonAbility]


# --------------------------------------------------------------- etage 2 : ORDINAUX ECRITS

def test_ordinaux_ecrits_aux_sites():
    """Fige les ordinaux MESURES a la conversion. `probe_313` compare le mirror au BUILD et
    redevient VERT des qu'on regenere le mirror apres un renumerotage -- il ne voit donc PAS que
    la valeur ecrite AU SITE a change. C'est le cran du dessous."""
    assert int(TriggeredAbilityType.RedThirst) == 0x4e1 == 1249
    assert int(EffectType.RedThirst_ExtraDamageAndHit) == 0x52a == 1322
    assert int(TriggeredAbilityType.CursedOfTheWalkingPox) == 0x430 == 1072
    assert int(CursedOfTheWalkingPoxSummonAbility.TRIGGERED_ABILITY_ID) == 1072
    assert int(CursedOfTheWalkingPoxSummonAbility.event_id) == int(EventTriggerType.PostUnitKill)
    assert int(EventTriggerType.PostUnitKill) == 0x35 == 53
    assert int(UnitTrait.Mechanical) == 5
    assert int(AbilityConstantType.healthPct) == 0x4f == 79
    assert int(AbilityConstantType.extraHit) == 0x2b == 43
    assert int(AbilityVariableType.extraDmg) == 8


# --------------------------------------------------------------- etage 3 : QUALIFICATION D'ENUM

def test_le_meme_ordinal_nomme_autre_chose_dans_l_autre_enum():
    """`CursedOfTheWalkingPox` vit dans `TriggeredAbilityType`, malgre le namespace natif
    `...Abilities.**Active**.Loki` de sa classe. La VOIE gameconfig (`passiveAbilities`) et l'enum
    CONCORDENT : ce n'est PAS une voie inversee facon `ShroudPsalm`/`Maugetar`.

    Le controle ASSERTIONNE SON PROPRE NON-VIDE : un `ActiveAbilityType` qui n'aurait pas de membre
    1072 rendrait ce test vert POUR RIEN."""
    par_ordinal = {int(m): m.name for m in ActiveAbilityType}
    assert 1072 in par_ordinal, "controle VIDE : `ActiveAbilityType` n'a pas d'ordinal 1072"
    assert par_ordinal[1072] != "CursedOfTheWalkingPox"
    assert par_ordinal[1072] == "MyWillBeDone"
    assert "CursedOfTheWalkingPox" not in {m.name for m in ActiveAbilityType}
    # Et l'ability qui INVOQUE le Poxwalker (l'active de `deathBlightbringer`) est un AUTRE objet.
    assert int(ActiveAbilityType.Poxwalkers) == 1040


# --------------------------------------------------------------- etage 4 : MAGNITUDES

def test_magnitudes_lues_au_gameconfig():
    """`healthPct`/`extraHit` sont des CONSTANTES, `extraDmg` une VARIABLE par niveau -- et c'est
    la difference qui decide du scaling de rarete. Un port qui prendrait `extraDmg` pour une
    constante lirait `None` et n'ajouterait RIEN (no-op silencieux)."""
    cfg = GC.ability("RedThirst") or {}
    consts = cfg.get("constants") or {}
    assert consts.get("healthPct") == "50"
    assert consts.get("extraHit") == "1"
    variables = cfg.get("variables") or {}
    assert len(variables.get("extraDmg") or []) == 65
    # SEULE `extraDmg` est scalee par le multiplicateur de rarete.
    assert list(cfg.get("variablesAffectedByRarityBonus") or []) == ["extraDmg"]
    # `CursedOfTheWalkingPox` n'a NI constante NI variable : c'est ce qui IMPOSE `CopyOwner` +
    # `UnitIdFromUnit` (aucun `GetStringConstant`/`WithStatsFromConfig` n'aurait quoi lire).
    pox = GC.ability("CursedOfTheWalkingPox") or {}
    assert not (pox.get("constants") or {})
    assert not (pox.get("variables") or {})


# --------------------------------------------------------------- etage 5 : ACTIVE-CONDITION

@pytest.mark.parametrize("hp,mx,attendu", [
    (100, 100, False),      # PV pleins -> inactif
    (51, 100, False),       # juste au-dessus du seuil
    (50, 100, True),        # AU seuil : `<=`, l'egalite compte (Fix64 rend 0.5 exact)
    (49, 100, True),
    (1, 100, True),
])
def test_active_condition_health_pct(hp, mx, attendu):
    """`HealthPctIsBelowOrEqual(Owner, ConfigConst(healthPct))` -- comparaison ENTIERE exacte
    `100 * courant <= healthPct * maximum`, meme foyer que `HammerOfWrathConditionalDamageEffect`."""
    eff = RedThirstExtraDamageAndHitEffect(name="RedThirst_ExtraDamageAndHit",
                                           effect_type=int(EffectType.RedThirst_ExtraDamageAndHit))
    assert eff.is_active({"hp": hp, "max_hp": mx}) is attendu


def test_active_condition_pv_non_captes_ne_masque_pas():
    """PV absents = NON MESURE -> on ne ferme PAS (degradation fidele, meme convention que
    `PowerTripFullHealthEffect` / `AnvilShieldBlockChanceBelowHealthCapEffect`)."""
    eff = RedThirstExtraDamageAndHitEffect(name="RedThirst_ExtraDamageAndHit",
                                           effect_type=int(EffectType.RedThirst_ExtraDamageAndHit))
    assert eff.is_active({}) is True
    assert eff.is_active(None) is True


# --------------------------------------------------------------- etage 6 : LES DEUX CANAUX

def test_canal_degat_n_est_PAS_gate_par_la_charge():
    """Le point ou la PROSE i2 et le DECOMPILE divergent, et c'est le decompile qui fait foi :
    `CreateEffectDamageBonusForAttack` n'a qu'UN noeud de trigger (`get_OwnerIsCaster`, rendu par
    le canal), la ou `CreateEffectHitsBonusForAttack` en a DEUX (`& IsCharging`)."""
    eff = RedThirstExtraDamageAndHitEffect(name="RedThirst_ExtraDamageAndHit",
                                           effect_type=int(EffectType.RedThirst_ExtraDamageAndHit),
                                           ability_level=50, ability_variables_multiplier=180)
    sans_charge = eff.create_effect_damage_bonus_for_attack(att_ctx={"is_charging": False})
    assert sans_charge is not None and int(sans_charge.value) == 599   # extraDmg[50] x 180 %
    avec_charge = eff.create_effect_damage_bonus_for_attack(att_ctx={"is_charging": True})
    assert avec_charge is not None and int(avec_charge.value) == 599
    # Canal COUPS : la charge, elle, GATE -- et le contexte NON THREADE ferme (jamais permissif).
    assert eff.create_effect_hits_bonus_for_attack(att_ctx={"is_charging": False}) is None
    assert eff.create_effect_hits_bonus_for_attack(att_ctx=None) is None
    coups = eff.create_effect_hits_bonus_for_attack(att_ctx={"is_charging": True})
    assert coups is not None and int(coups.value) == 1                 # ConfigConst extraHit


def test_extra_dmg_est_scale_par_le_multiplicateur_et_pas_extra_hit():
    """`extraDmg` EST dans `variablesAffectedByRarityBonus` (donc scalee), `extraHit` est une
    CONSTANTE (donc jamais). Confondre les deux accesseurs ne leverait aucune erreur."""
    def _eff(mult):
        return RedThirstExtraDamageAndHitEffect(
            name="RedThirst_ExtraDamageAndHit",
            effect_type=int(EffectType.RedThirst_ExtraDamageAndHit),
            ability_level=50, ability_variables_multiplier=mult)
    v100 = int(_eff(100).create_effect_damage_bonus_for_attack().value)
    v180 = int(_eff(180).create_effect_damage_bonus_for_attack().value)
    assert (v100, v180) == (333, 599)
    h100 = int(_eff(100).create_effect_hits_bonus_for_attack(att_ctx={"is_charging": True}).value)
    h180 = int(_eff(180).create_effect_hits_bonus_for_attack(att_ctx={"is_charging": True}).value)
    assert h100 == h180 == 1


# --------------------------------------------------------------- etage 7 : FOYER `CopyOwner`

def test_copy_owner_est_un_foyer_partage():
    """`SpawnUnitOptions$$CopyOwner` a DEUX consommateurs natifs (`ScarabSummonAbility` et
    `CursedOfTheWalkingPoxAbility`) ; le port n'en ecrit qu'UN. Les cinq `StatType` que le corps
    natif empile y sont, ET les stats supplementaires que le clonage de `UnitContext` exige."""
    assert hasattr(SpawnUnitOperation, "execute_copy_owner_on_tiles")
    assert hasattr(SpawnUnitOperation, "execute_self_replica")
    ords = {int(s) for s in _COPY_OWNER_STATS}
    # QUATRE des cinq `StatType` du corps natif : Health(5), FixedArmor(16), Attack(0),
    # Movement(1). Le CINQUIEME est `20 = NumberOfMembers` -- il n'est PAS dans la liste, et
    # c'est fidele : `UnitContext.number_of_members` est un CHAMP PLAT, donc le
    # `dataclasses.replace` du clone le recopie deja. Cette assertion FIGE cette lecture : si un
    # jour `number_of_members` devenait adosse a `stats` (comme le percage l'est devenu en
    # #366-r1), le clone le perdrait EN SILENCE et il faudrait l'ajouter ici.
    assert {int(StatType.ATTACK), int(StatType.MOVEMENT), int(StatType.HEALTH),
            int(StatType.FIXED_ARMOR)}.issubset(ords)
    assert int(StatType.NUMBER_OF_MEMBERS) not in ords
    assert "number_of_members" in {f.name for f in fields(UnitContext)}
