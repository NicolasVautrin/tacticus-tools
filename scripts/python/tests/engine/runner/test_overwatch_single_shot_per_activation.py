"""UN SEUL TIR PAR ACTIVATION — machine a etats `EffectComponent.IsActive @+0x5c` de l'overwatch.

`IdunBattle.Entities.Effects.RangedAutoAttackEffect$$CreateHandleTriggerAbilitiesInternal` (DECOMPILE)
rend un `ArraySet` de TROIS `Triggered()` qui n'ecrivent qu'une chose : le flag `IsActive` de
l'instance d'effet (`effect@0x150`) :

    (1) On(0x12) & NOT IsTurnOf(owner) & (HasEffect(owner,0x516) | DoesNotHaveFlag(owner,2))
                & AdditionalActivateTrigger                       -> ActivateEffect
    (2) On(0x12, 1) & IsTurnOf(owner)                             -> DeactivateEffect
    (3) On(10 = AttackDamageAttack, 1) & OwnerIsActor             -> DeactivateEffect

Le flag est RELU par `IdunBattle.Operations.EvaluateTriggerOperation$$EvaluateEffectTriggerTargets`
AVANT le trigger de TIR (`RangedAutoAttackEffect$$CreateTargetTrigger`) -- et RELU PAR CIBLE dans sa
boucle de drain. (3) est donc « l'overwatch est consomme des que son porteur attaque ».

CE QUE CE FICHIER VERROUILLE (offline pur, aucune session live) : la machine a etats complete, et
SURTOUT sa SYMETRIE -- desactivation par le tir PUIS re-activation au tour adverse suivant, en
passant par le VRAI turn-flow (`EndTurnOperation` -> `ChangeTurn` -> `StartTurnOperation` -> On(0x12)),
pas en appelant les triggers a la main. Un fix qui eteindrait l'overwatch DEFINITIVEMENT passerait le
premier critere et echouerait ici.

La confrontation LIVE (le tir lui-meme, bit-exact) vit dans
`test_overwatch_single_shot_per_activation_live.py`. ASCII only.
"""
from __future__ import annotations

from engine.runner.state import State
from engine.runner.components import UnitComponent, OwnerComponent, UnitFlagsComponent
from engine.entities.effects_state import EffectsState
from engine.runner.operations.turnflow import EndTurnOperation
from engine.runner.operations.triggers import TriggerEvent, evaluate_trigger_operation
from engine.dsl.event_trigger_type import EventTriggerType
from engine.runner.operations.triggers.effect_triggers import (
    OVERWATCH_AUTO_ATTACK, RangedAutoAttackDeactivateOnAttack,
    RangedAutoAttackActivateOnTurnStart, RangedAutoAttackDeactivateOnTurnStart,
    _ranged_auto_attack_flag_is_set, _ranged_auto_attack_instances)

OWNER = 1               # l'overwatcher (player 3)
ENEMY = 2               # une unite adverse (player 4) -- fait exister le 2e joueur du turn-flow
OWNER_PLAYER = 3
OTHER_PLAYER = 4


def _state(current_player=OTHER_PLAYER, ability_used=False, extra_effects=()) -> State:
    """Etat minimal : un overwatcher portant 1009 + un ennemi, tour de l'ENNEMI (fenetre overwatch)."""
    st = State()
    st.current_player_id = current_player
    ow = st.add_entity(OWNER)
    ow.add_component(UnitComponent("overwatcher", True))
    ow.add_component(OwnerComponent(team=1, player=OWNER_PLAYER))
    if ability_used:
        ow.add_component(UnitFlagsComponent()).add(UnitFlagsComponent.ACTIVE_ABILITY_USED)
    en = st.add_entity(ENEMY)
    en.add_component(UnitComponent("mover", True))
    en.add_component(OwnerComponent(team=2, player=OTHER_PLAYER))
    effs = [{"name": "Overwatch_AutoAttack", "effectType": OVERWATCH_AUTO_ATTACK}]
    effs += [{"name": f"e{t}", "effectType": int(t)} for t in extra_effects]
    st.effects = EffectsState.seed({OWNER: effs})
    return st


def _fire_attack_event(st: State, actor: int, target: int) -> list:
    """Le vecteur `On(AttackDamageAttack = 10)` tel que l'emet `attack_damage_attack_triggers`."""
    return evaluate_trigger_operation(
        st, TriggerEvent(EventTriggerType.AttackDamageAttack, actor, target,
                         ranged=True, profile=None))


# --------------------------------------------------------------------------- flag & seed

def test_seeded_effect_is_active():
    """Un effet SEEDE est actif : le canal de seed DROPPE deja les `IsActive == 0` (case-127 §80),
    donc « present == IsActive ». Sans ce defaut, tout etat live rechargé serait mort-ne."""
    st = _state()
    assert _ranged_auto_attack_instances(st, OWNER), "fixture cassee : 1009 absent"
    assert all(e.active for e in _ranged_auto_attack_instances(st, OWNER))
    assert _ranged_auto_attack_flag_is_set(st, OWNER) is True


def test_no_instance_is_permissive():
    """Pas d'instance 1009 (etat sans `EffectsState`) -> le gate ne fabrique pas un refus."""
    st = State()
    assert _ranged_auto_attack_flag_is_set(st, OWNER) is True


# --------------------------------------------------------------------------- (3) OwnerIsActor

def test_owner_attack_deactivates_the_instance():
    """`On(10) & OwnerIsActor -> DeactivateEffect` : l'attaque DU PORTEUR consomme SON overwatch."""
    st = _state()
    out = _fire_attack_event(st, actor=OWNER, target=ENEMY)
    assert any(r.get("deactivated") == "owner_attacked" for r in out), out
    assert _ranged_auto_attack_flag_is_set(st, OWNER) is False


def test_someone_else_attack_does_not_deactivate():
    """`OwnerIsActor` est un vrai gate : l'attaque d'une AUTRE unite ne consomme pas l'overwatch
    (sans lui, n'importe quelle attaque de la bataille eteindrait tous les overwatch)."""
    st = _state()
    _fire_attack_event(st, actor=ENEMY, target=OWNER)
    assert _ranged_auto_attack_flag_is_set(st, OWNER) is True


def test_deactivation_is_idempotent():
    """`RefreshEffectsOperation$$DeactivateEffect` porte le gate « deja inactif -> no-op » : le 2e
    passage n'emet rien (et ne re-declenche aucun effet de bord)."""
    st = _state()
    assert _fire_attack_event(st, OWNER, ENEMY)
    assert _fire_attack_event(st, OWNER, ENEMY) == []


def test_matches_is_owner_is_actor():
    """`get_OwnerIsActor` compare owner@0x148 et actor@0x158 -- rien d'autre."""
    st = _state()
    ev_ok = TriggerEvent(EventTriggerType.AttackDamageAttack, OWNER, ENEMY, ranged=True, profile=None)
    ev_ko = TriggerEvent(EventTriggerType.AttackDamageAttack, ENEMY, OWNER, ranged=True, profile=None)
    assert RangedAutoAttackDeactivateOnAttack(OWNER).matches(st, ev_ok) is True
    assert RangedAutoAttackDeactivateOnAttack(OWNER).matches(st, ev_ko) is False


# --------------------------------------------------------------------------- (1) et (2) On(0x12)

def test_activate_trigger_matches_only_outside_owner_turn():
    """(1) porte la conjonction complete (`_ranged_auto_attack_is_active`) : elle est FAUSSE pendant
    le tour du porteur et quand il a consomme son activation d'ability."""
    ev = TriggerEvent(EventTriggerType.TurnStart_EffectActivation, -1, -1, ranged=False, profile=None)
    assert RangedAutoAttackActivateOnTurnStart(OWNER).matches(_state(), ev) is True
    assert RangedAutoAttackActivateOnTurnStart(OWNER).matches(
        _state(current_player=OWNER_PLAYER), ev) is False
    assert RangedAutoAttackActivateOnTurnStart(OWNER).matches(
        _state(ability_used=True), ev) is False


def test_deactivate_on_owner_turn_start():
    """(2) `On(0x12,1) & IsTurnOf(owner) -> DeactivateEffect` : c'est ce qui explique que 1009 soit
    absent de `decisionView` pendant le tour de son porteur."""
    ev = TriggerEvent(EventTriggerType.TurnStart_EffectActivation, -1, -1, ranged=False, profile=None)
    st = _state(current_player=OWNER_PLAYER)
    assert RangedAutoAttackDeactivateOnTurnStart(OWNER).matches(st, ev) is True
    RangedAutoAttackDeactivateOnTurnStart(OWNER).execute_behaviour(st, ev)
    assert _ranged_auto_attack_flag_is_set(st, OWNER) is False
    assert RangedAutoAttackDeactivateOnTurnStart(OWNER).matches(_state(), ev) is False


# --------------------------------------------------------------------------- SYMETRIE (le controle)

def test_full_turn_cycle_reactivates_the_overwatch():
    """CONTROLE SYMETRIQUE, par le VRAI turn-flow : l'overwatch consomme par le tir doit REVENIR au
    tour adverse suivant. `EndTurnOperation` -> `ChangeTurnOperation` -> `StartTurnOperation` emet
    `On(0x12)`, donc (2) puis (1). Un fix qui eteindrait l'overwatch definitivement echoue ICI."""
    st = _state()                                            # tour de l'ennemi, overwatch arme
    _fire_attack_event(st, OWNER, ENEMY)                     # le porteur tire -> consomme
    assert _ranged_auto_attack_flag_is_set(st, OWNER) is False

    EndTurnOperation.execute(st, advance=True)               # -> tour du PORTEUR : (2) desactive
    assert st.current_player_id == OWNER_PLAYER
    assert _ranged_auto_attack_flag_is_set(st, OWNER) is False

    EndTurnOperation.execute(st, advance=True)               # -> tour de l'ENNEMI : (1) re-active
    assert st.current_player_id == OTHER_PLAYER
    assert _ranged_auto_attack_flag_is_set(st, OWNER) is True, (
        "l'overwatch n'est jamais revenu : le port l'aurait eteint DEFINITIVEMENT")


def test_full_turn_cycle_does_not_reactivate_when_ability_was_used():
    """Meme cycle, mais le porteur a consomme son activation d'ability (#127) : (1) ne matche pas,
    donc l'overwatch NE revient PAS. Les deux gates cohabitent sans se recouvrir."""
    st = _state()
    _fire_attack_event(st, OWNER, ENEMY)
    EndTurnOperation.execute(st, advance=True)               # tour du porteur
    # `AddFlagsAfterAbilityExecution` : le porteur caste pendant SON tour
    fl = st.get_entity(OWNER).get_component(UnitFlagsComponent)
    if fl is None:
        fl = st.get_entity(OWNER).add_component(UnitFlagsComponent())
    fl.add(UnitFlagsComponent.ACTIVE_ABILITY_USED)
    EndTurnOperation.execute(st, advance=True)               # tour de l'ennemi : (1) doit se taire
    assert _ranged_auto_attack_flag_is_set(st, OWNER) is False
