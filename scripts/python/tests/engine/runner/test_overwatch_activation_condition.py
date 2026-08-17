"""STRUCTURE de la condition d'activation de l'overwatch (case-127) — mirror OFFLINE pur.

Verrouille la CONJONCTION portee par `_ranged_auto_attack_is_active`, mirror du 1er `Triggered()` de
`IdunBattle.Entities.Effects.RangedAutoAttackEffect$$CreateHandleTriggerAbilitiesInternal` :

    NOT IsTurnOf(owner@0x148)                                              # df@0xa0 (IdunBattleLogic.Entities.DSLTriggers$$IsTurnOf)
    & ( HasEffect(owner, IgnoreUsedAbilityInOverwatch = 0x516)
        | DoesNotHaveFlag(owner, UnitFlag.ActiveAbilityUsed = 2) )
    & AdditionalActivateTrigger()                                          # NOT HasEffect(owner, Pinned)

Chaque conjoint est teste ISOLEMENT (les autres au neutre) : un port qui en perdrait un ne passerait
pas. Deux d'entre eux sont EN PLUS confrontes au live (`test_overwatch_active_ability_gate_live`) :
le flag `ActiveAbilityUsed` (avec controle interne SentinelDirectives) et `IsTurnOf` (au deploiement,
pendant le tour du proprietaire, `decisionView` ne liste PAS 1009 sur ses propres overwatchers).
Les deux autres (`Pinned`, `IgnoreUsedAbilityInOverwatch`) n'ont pas de confrontation live ici :
`Pinned` etait deja porte avant #127, et aucun poseur de 1302 n'a ete trouve dans le decompile
(cf. docs/rl/case-127-overwatch-active-condition.md §6). ASCII only, aucune session live requise.
"""
from __future__ import annotations

from engine.runner.state import State
from engine.runner.components import UnitComponent, OwnerComponent, UnitFlagsComponent
from engine.entities.effects_state import EffectsState
from engine.runner.operations.triggers.effect_triggers import (
    _ranged_auto_attack_is_active, OVERWATCH_SOURCE_DISABLE, OVERWATCH_IGNORE_ABILITY_USED)

OWNER = 1
OWNER_PLAYER = 3
OTHER_PLAYER = 4


def _state(effects_on_owner=(), current_player=OTHER_PLAYER, ability_used=False) -> State:
    st = State()
    st.current_player_id = current_player
    e = st.add_entity(OWNER)
    e.add_component(UnitComponent("overwatcher", True))
    e.add_component(OwnerComponent(team=1, player=OWNER_PLAYER))
    if ability_used:
        fl = e.add_component(UnitFlagsComponent())
        fl.add(UnitFlagsComponent.ACTIVE_ABILITY_USED)
    st.effects = EffectsState.seed({OWNER: [{"name": f"e{t}", "effectType": int(t)}
                                            for t in effects_on_owner]})
    return st


def test_nominal_is_active():
    """Aucun conjoint viole -> l'effet est (re)activable."""
    assert _ranged_auto_attack_is_active(_state(), OWNER) is True


def test_active_ability_used_flag_blocks():
    """`DoesNotHaveFlag(owner, ActiveAbilityUsed=2)` — la NEGATION : flag pose => pas d'activation."""
    assert _ranged_auto_attack_is_active(_state(ability_used=True), OWNER) is False


def test_ignore_used_ability_effect_neutralises_the_flag():
    """Branche OR `HasEffect(owner, IgnoreUsedAbilityInOverwatch=0x516)` : elle rend le flag inerte."""
    st = _state(effects_on_owner=(OVERWATCH_IGNORE_ABILITY_USED,), ability_used=True)
    assert _ranged_auto_attack_is_active(st, OWNER) is True


def test_is_turn_of_owner_blocks():
    """`NOT IsTurnOf(owner)` : pendant le tour du porteur, l'effet est desactive (2e `Triggered()`)."""
    assert _ranged_auto_attack_is_active(_state(current_player=OWNER_PLAYER), OWNER) is False


def test_pinned_blocks():
    """`AdditionalActivateTrigger` d'`Overwatch_AutoAttackEffect` = `NOT HasEffect(owner, Pinned)`."""
    st = _state(effects_on_owner=(OVERWATCH_SOURCE_DISABLE,))
    assert _ranged_auto_attack_is_active(st, OWNER) is False


def test_pinned_blocks_even_with_ignore_effect():
    """La branche OR ne couvre QUE le couple (1302 | flag) : `Pinned` est un conjoint SEPARE et
    doit bloquer meme quand `IgnoreUsedAbilityInOverwatch` est porte."""
    st = _state(effects_on_owner=(OVERWATCH_SOURCE_DISABLE, OVERWATCH_IGNORE_ABILITY_USED),
                ability_used=True)
    assert _ranged_auto_attack_is_active(st, OWNER) is False


def test_unknown_current_player_is_permissive():
    """`current_player_id` absent (etat construit hors `load_state`) -> le conjoint `IsTurnOf` est
    INERTE (jamais un refus invente) ; les autres conjoints continuent de s'appliquer."""
    assert _ranged_auto_attack_is_active(_state(current_player=None), OWNER) is True
    assert _ranged_auto_attack_is_active(_state(current_player=None, ability_used=True),
                                         OWNER) is False
