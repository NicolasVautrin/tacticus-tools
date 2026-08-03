"""#462-r4b-r1-r1-r1 -- GARDES OFFLINE de la POSE de `Neuroparasite` et de sa montee en niveau.

Ce que chaque garde est SEUL a voir :

  1. `test_les_trois_Triggered_natifs_sont_INSCRITS` -- le CLIQUET DU CANAL. Le natif construit
     TROIS `Triggered()` (un `AbilityTrigger` pour la pose, deux `EffectTrigger` pour la montee) ;
     s'il en disparaissait un du registre, le parasite cesserait d'apparaitre -- ou cesserait de
     monter -- **sans qu'aucun test de magnitude ne bouge**, exactement le profil de regression
     silencieuse qui a produit ce cas.
  2. `test_le_cap_..._NornCrown` -- la SEULE branche de `$$GetMaximumLevel` qui n'est PAS
     confrontable live (il faudrait 15 frappes pour que le cap morde, et la relique ne change le
     cap que d'un cran). Elle est donc gardee ICI, ou nulle part.
  3. `test_le_clamp_..._quirk_natif` -- le comportement de bord d'
     `IdunBattle.Operations.IncreaseEffectLevelOperation$$Execute` (`max < cur` continue
     d'incrementer), que la voie `Neuroparasite` consomme desormais.
  4. `test_les_enums_HOMONYMES_...` -- 1183/1218 et 1495 sont des paires d'enums homonymes. Une
     confusion y est silencieuse : le port lirait une autre ability, une autre config, sans erreur.
  5. `test_AddBondEffect_transporte_l_abilityState` -- le 3e argument natif. Sans lui l'entite-effet
     ne bake pas l'etat d'ability du poseur et `$$GetMaximumLevel` n'a plus de niveau a indexer.

ASCII only.
"""
from __future__ import annotations

import inspect
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_PY = os.path.dirname(os.path.dirname(_HERE))
if _PY not in sys.path:
    sys.path.insert(0, _PY)

from engine.entities import UnitContext                                       # noqa: E402
from engine.entities.effect_type import EffectType                            # noqa: E402
from engine.entities.effects.magnitude import ability_var                     # noqa: E402
from engine.entities.triggered_ability_type import TriggeredAbilityType       # noqa: E402
from engine.runner.abilities.behaviours.effects import AddBondEffect          # noqa: E402
from engine.runner.components import StatsComponent                           # noqa: E402
from engine.runner.state import Entity, State                                 # noqa: E402
from engine.runner.operations.triggers.dispatch.registry import (             # noqa: E402
    ABILITY_TRIGGERS, EFFECT_TRIGGERS)
from engine.runner.operations.triggers.loki.neuroparasite import (            # noqa: E402
    NEUROPARASITE_EFFECT, NeuroparasiteAddBondEffectAbility,
    NeuroparasiteIncreaseLevelOnPinned, NeuroparasiteIncreaseLevelOnPsychicHit,
    neuroparasite_maximum_level)

_ON_ATTACK = 9                     # `EventTriggerType.Attack`
_ON_PRE_EFFECT_ADDED = 0x3d        # 61 -- `EventTriggerType.PreEffectAdded`
_PASSIVE_LEVEL = 50
_BUFF_MAX_LEVEL_50 = 15            # `ConfigVar(0x4c = buffMaxLevel)[50]`
_NORN_CROWN_EFFECT_LEVEL = 1       # `ConfigConst(0x73 = effectLevel)` de `NornCrown`


class _FakeEffect:
    """L'etat BAKE d'une instance 1218 : ce que `AddEffectOperation` ecrit et ce que
    `$$GetMaximumLevel` relit. On n'a pas besoin d'un `BaseEffect` complet -- la fonction sous test
    ne lit que ces trois champs."""
    def __init__(self, ability_level, multiplier=100, bonded=None):
        self.ability_level = ability_level
        self.ability_variables_multiplier = multiplier
        self.bonded = bonded


def _state_with_bonded(bonded_id, triggered_ids):
    """Un `State` portant l'entite BONDEE avec son kit DECLENCHE mesure (`UnitContext.
    triggered_abilities` = l'image de l'`AbilitiesComponent`) -- le substrat que lit
    `entity_triggered_ability_ids`, foyer partage de `ActorHasTriggeredAbility`."""
    st = State()
    e = Entity(bonded_id)
    e.add_component(StatsComponent(UnitContext(bonded_id, visual_id="tyranNeurothrope",
                                               passive_ability_level=_PASSIVE_LEVEL,
                                               triggered_abilities=list(triggered_ids))))
    st.entities[bonded_id] = e
    return st


# ------------------------------------------------------------------ (1) le cliquet du canal

def test_les_trois_Triggered_natifs_sont_INSCRITS():
    """`IdunBattleLogic.Entities.Abilities.Triggered.Loki.NeuroparasiteAbility` (la POSE, `On(9)`)
    et les DEUX `Triggered()` que
    `IdunBattle.Entities.Effects.Loki.NeuroparasiteEffect$$CreateHandleTriggerAbilitiesInternal`
    ajoute a l'`ArraySet` (`On(9)` et `On(0x3d)`, tous deux vers `$$GetIncreaseLevelBehaviour`).

    Le REGISTRE est le seul endroit ou leur disparition serait visible : un canal desinscrit ne
    leve rien, ne casse aucun test de magnitude, et rend simplement le parasite invisible."""
    assert NeuroparasiteAddBondEffectAbility in ABILITY_TRIGGERS.get("Neuroparasite", []), (
        "la POSE n'est plus inscrite au registre des passiveAbilities -- en self-play le parasite "
        "n'apparaitrait jamais")
    assert NeuroparasiteAddBondEffectAbility.event_id == _ON_ATTACK
    got = EFFECT_TRIGGERS.get(NEUROPARASITE_EFFECT, [])
    assert NeuroparasiteIncreaseLevelOnPsychicHit in got, (
        "la montee sur frappe PSYCHIQUE n'est plus inscrite -> tout parasite resterait au niveau 1")
    assert NeuroparasiteIncreaseLevelOnPinned in got, (
        "la montee sur `Pinned` (`On(0x3d)`) n'est plus inscrite")
    assert NeuroparasiteIncreaseLevelOnPsychicHit.event_id == _ON_ATTACK
    assert NeuroparasiteIncreaseLevelOnPinned.event_id == _ON_PRE_EFFECT_ADDED
    for cls in (NeuroparasiteIncreaseLevelOnPsychicHit, NeuroparasiteIncreaseLevelOnPinned):
        assert cls.effect_type == NEUROPARASITE_EFFECT


# ---------------------------------------------- (2) la branche NON confrontable de GetMaximumLevel

def test_le_cap_vaut_buffMaxLevel_seul_quand_le_bonde_n_a_PAS_NornCrown():
    """`$$GetMaximumLevel` = `Sum(ConfigVar(0x4c = buffMaxLevel, GetAbilityState(effect)), If(...))`.

    `0x4c` est QUALIFIE par EXCLUSION sur la config REELLEMENT SERVIE : `BC.Abilities.
    PassiveAbilities.Neuroparasite.Variables` n'a que DEUX entrees -- `extraDmg` (index 8, atteste
    bit-exact par #86 puis #553) et `buffMaxLevel`. `Neuroparasite` est d'ailleurs la SEULE ability
    du BC a porter `buffMaxLevel` en VARIABLE (ailleurs c'est une CONSTANTE, lue par
    `GetNumberConstant`)."""
    st = _state_with_bonded(7, [int(TriggeredAbilityType.Neuroparasite)])
    eff = _FakeEffect(_PASSIVE_LEVEL, multiplier=180, bonded=7)
    assert neuroparasite_maximum_level(st, eff) == _BUFF_MAX_LEVEL_50
    # `buffMaxLevel` n'est PAS dans `variablesAffectedByRarityBonus` -> le multiplier est un NO-OP.
    # Si un jour il l'etait, le cap dependrait de la rarete du porteur : ce serait un vrai changement
    # de comportement, et il doit se voir ici.
    assert neuroparasite_maximum_level(st, _FakeEffect(_PASSIVE_LEVEL, 100, 7)) == \
        neuroparasite_maximum_level(st, eff), (
        "le cap depend du multiplier de rarete -> `buffMaxLevel` est devenue rarity-affected")


def test_le_cap_gagne_un_cran_si_le_bonde_porte_NornCrown():
    """`If(ActorHasTriggeredAbility(BondedEntity, 0x5d7), ConfigConst(0x5d7, BondedEntity,
    0x73 = effectLevel), Direct(0))`.

    Branche NON CONFRONTABLE LIVE : le cap ne mord qu'a `buffMaxLevel` frappes, et cette relique ne
    le deplace que d'UN cran -- il faudrait 15 puis 16 frappes pour separer les deux modeles. Elle
    est donc gardee ICI, ou nulle part.

    `0x73` est QUALIFIE par EXCLUSION : `gameconfig.NornCrown.constants` n'a qu'UNE entree,
    `effectLevel = 1`."""
    ids_sans = [int(TriggeredAbilityType.Neuroparasite)]
    ids_avec = ids_sans + [int(TriggeredAbilityType.NornCrown)]
    eff = _FakeEffect(_PASSIVE_LEVEL, 100, bonded=7)
    sans = neuroparasite_maximum_level(_state_with_bonded(7, ids_sans), eff)
    avec = neuroparasite_maximum_level(_state_with_bonded(7, ids_avec), eff)
    assert avec == sans + _NORN_CROWN_EFFECT_LEVEL, (
        "cap sans NornCrown = %s, avec = %s -- le terme conditionnel ne mord pas" % (sans, avec))
    assert ability_var("NornCrown", "effectLevel", None, is_constant=True) == \
        _NORN_CROWN_EFFECT_LEVEL


def test_le_cap_est_NUL_quand_l_etat_d_ability_n_est_pas_bake():
    """`ConfigVar(0x4c, GetAbilityState(effect), ...)` sans niveau -> `TryGetVariableArrayForLevel`
    n'a rien a indexer. Le port rend alors `None`, que `IncreaseEffectLevelOperation` traite comme
    « pas de cap » (`!max.HasValue`).

    C'est la DEGRADATION assumee, et elle est PERMISSIVE : un parasite monterait sans plafond au
    lieu de ne pas monter du tout. Ce test existe pour que ce bord soit un CHOIX lisible, pas une
    surprise -- et pour qu'un `None` inattendu (regression du transport de l'`abilityState`) se
    voie ailleurs, dans le garde live du cap."""
    st = _state_with_bonded(7, [])
    assert neuroparasite_maximum_level(st, _FakeEffect(None, 100, bonded=7)) == \
        ability_var("Neuroparasite", "buffMaxLevel", None), (
        "un `ability_level` absent doit retomber sur l'index 0 de la table, pas lever")


# ------------------------------------------------------- (3) le clamp natif que cette voie consomme

def test_le_clamp_IncreaseEffectLevel_garde_le_quirk_natif():
    """`IdunBattle.Operations.IncreaseEffectLevelOperation$$Execute` :

        if (!max.HasValue || max.Value < cur || cur + amount <= max.Value)  level = cur + amount
        else                                                               level = max.Value

    La 2e disjonction est un QUIRK : un niveau DEJA au-dessus du cap continue d'etre incremente.
    `Neuroparasite` en devient un consommateur (son cap peut BAISSER si le porteur de `NornCrown`
    perd sa relique en cours de bataille), d'ou ce garde ici et pas seulement chez le proprietaire
    historique du clamp."""
    from engine.runner.abilities.behaviours.effects import IncreaseEffectLevel

    def clamp(cur, amount, mx):
        if mx is None or mx < cur or cur + amount <= mx:
            return cur + amount
        return mx

    src = inspect.getsource(IncreaseEffectLevel.execute)
    assert "mx < cur" in src, (
        "le quirk `max.Value < cur` a disparu du clamp porte -- un niveau au-dessus du cap serait "
        "desormais rabattu, ce que le natif ne fait pas")
    assert clamp(1, 1, 15) == 2                # regime nominal
    assert clamp(15, 1, 15) == 15              # le cap mord
    assert clamp(16, 1, 15) == 17              # QUIRK : deja au-dessus -> continue de monter
    assert clamp(3, 1, None) == 4              # pas de cap


# ---------------------------------------------------------- (4) les enums HOMONYMES, qualifies

def test_les_enums_HOMONYMES_sont_bien_qualifies():
    """Trois paires qui se confondent SILENCIEUSEMENT :

      * `1183` = `TriggeredAbilityType.Neuroparasite` (l'ABILITY) mais aussi
        `EffectType.DefenderOfTheGreaterGood_ExtraHits` ;
      * `1218` = `EffectType.Neuroparasite` (l'EFFET, pose sur la victime) mais aussi
        `TriggeredAbilityType.TheBetrayer` ;
      * `1495` = `TriggeredAbilityType.NornCrown` (ce que lit `ActorHasTriggeredAbility`) mais aussi
        `EffectType.HunterOfSouls_ExtraDamage`.

    Le port doit poser l'EFFET 1218 et interroger l'ABILITY 1495 -- jamais l'inverse."""
    assert NEUROPARASITE_EFFECT == int(EffectType.Neuroparasite) == 1218
    assert int(TriggeredAbilityType.Neuroparasite) == 1183
    assert NeuroparasiteAddBondEffectAbility.TRIGGERED_ABILITY_ID == 1183
    assert int(TriggeredAbilityType.NornCrown) == 1495
    # Les homonymes existent bel et bien : sans eux ce test ne garderait plus rien.
    assert int(EffectType.DefenderOfTheGreaterGood_ExtraHits) == 1183
    assert int(TriggeredAbilityType.TheBetrayer) == 1218
    assert int(EffectType.HunterOfSouls_ExtraDamage) == 1495


# --------------------------------------------- (5) le 3e argument natif d'AddBondEffect

def test_AddBondEffect_transporte_l_abilityState():
    """`IdunBattleLogic.Entities.DSLBehaviors$$AddBondEffect(effectType, abilityState, source,
    targets, bondedEntity, options)` -- le 3e argument est transmis tel quel a
    `IdunBattle.Entities.Behaviours.AddEffectBehaviour$$.ctor` : l'entite-effet BAKE l'etat d'ability
    du POSEUR, ce que relit `IdunBattle.Entities.Effects.BaseEffect$$GetAbilityState`.

    Le port ne l'exprimait PAS sur cette feuille (seul son jumeau `AddEffect` l'avait). Sans lui,
    l'instance 1218 posee offline n'aurait ni niveau ni multiplier, et `$$GetMaximumLevel` rendrait
    `None`. Le defaut reste `False` -- les trois call-sites historiques sont inchanges."""
    params = inspect.signature(AddBondEffect.__init__).parameters
    assert "scale_from_source" in params, (
        "`AddBondEffect` ne transporte plus l'`abilityState` -- le 3e argument natif est perdu")
    assert params["scale_from_source"].default is False, (
        "le defaut doit rester False : les call-sites historiques ne passent pas cet argument")
    tree = NeuroparasiteAddBondEffectAbility(1)
    src = inspect.getsource(type(tree).execute_behaviour)
    assert "scale_from_source=True" in src, (
        "la POSE de Neuroparasite ne bake plus l'etat d'ability du Neurothrope")
    assert "duration_rounds=None" in src, (
        "la POSE natif passe des options VIDES -> duree DEFAUT (absente) = PERMANENT ; un "
        "`duration_rounds` explicite serait un timer INVENTE")
