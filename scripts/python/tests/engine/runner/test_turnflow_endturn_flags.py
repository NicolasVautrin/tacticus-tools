"""#139 — flag « does not end turn » : mirror OFFLINE pur de la queue d'execution d'ability.

Chaine native validee par RE (VAs) :
    IdunBattle.Operations.ActiveAbilityOperation$$ExecuteInternal
      -> IdunBattle.Operations.ActiveAbilityOperation$$GetSkipEndTurnFlag     = options.skip || !ability.SetsEndTurnFlags().Evaluate(...)
      -> IdunBattle.Operations.ActiveAbilityOperation$$GetSkipAbilityUsedFlag = options.skip || !ability.SetsActiveAbilityUsedFlag(caster)...
      -> IdunBattle.Operations.ActiveAbilityOperation$$AddFlagsAfterAbilityExecution :
           !skipAbilityUsed -> UnitFlags.Add(ActiveAbilityUsed=2)
           !skipEndTurn     -> Core.Services.OperationProcessor$$FinishUnitTurn
                               -> IdunBattle.Operations.FinishUnitTurnOperation$$Execute (flags 1+3)
    IdunBattle.Operations.StartTurnOperation$$Execute -> IdunBattle.Entities.Components.UnitFlagsComponent$$RemoveTurnFlags (0,1) par unite du joueur entrant.

Tests OFFLINE purs (aucune session live) : on construit un State minimal et on verifie le cycle
pose/lecture/reset des UnitFlags, y compris l'override famille « does not end turn » (ArmoriumCherub 1014
= Vindicta, WarHowl 1106 = Ragnar) et le conditionnel FightingRetreat 1081 (adjacence ennemie).
ASCII only.
"""
from __future__ import annotations

from engine.runner.state import State
from engine.runner.components import (UnitComponent, OwnerComponent, PositionComponent,
                                      UnitFlagsComponent)
from engine.runner.messages import ActiveAbilityMessage, FinishUnitTurnMessage
from engine.runner.operations.turnflow import (FinishUnitTurnOperation, StartTurnOperation,
                                               add_flags_after_ability_execution)
from engine.runner.abilities.base import (sets_end_turn_flags_for, sets_active_ability_used_flag_for,
                                          NO_END_TURN_ABILITY_TYPES,
                                          NO_ABILITY_USED_FLAG_ABILITY_TYPES)
from engine.runner.abilities.handler import AbilityHandler


def _mk_state(two_teams: bool = True, adjacent: bool = False) -> State:
    """State minimal : u1 (team 1, player 3) en (3,3) ; u2 (team 2, player 4) adjacente (4,3) ou
    lointaine (9,9)."""
    st = State()
    st.current_player_id = 3
    e1 = st.add_entity(1)
    e1.add_component(UnitComponent("unitA", True))
    e1.add_component(OwnerComponent(team=1, player=3))
    e1.add_component(PositionComponent(3, 3))
    if two_teams:
        e2 = st.add_entity(2)
        e2.add_component(UnitComponent("unitB", True))
        e2.add_component(OwnerComponent(team=2, player=4))
        pos = (4, 3) if adjacent else (9, 9)
        e2.add_component(PositionComponent(*pos))
    return st


# ---------------------------------------------------------------- FinishUnitTurnOperation IdunBattle.Operations.FinishUnitTurnOperation$$Execute

def test_finish_unit_turn_sets_flags_1_and_3():
    st = _mk_state()
    r = FinishUnitTurnOperation.execute(st, 1)
    fl = st.get_entity(1).get_component(UnitFlagsComponent)
    assert fl is not None
    assert fl.has(UnitFlagsComponent.ARRIVED_AT_FINAL_TILE)      # flag 1
    assert fl.has(UnitFlagsComponent.TURN_FINISHED)              # flag 3
    assert fl.turn_ended()                                       # IdunBattle.Entities.Components.UnitFlagsComponent$$TurnEnded = Contains(3)
    assert not fl.has(UnitFlagsComponent.TURN_FINISHED_FORCED)
    assert r["newly_finished"] is True
    # idempotence : re-executer ne re-marque pas "newly"
    r2 = FinishUnitTurnOperation.execute(st, 1)
    assert r2["newly_finished"] is False


def test_finish_unit_turn_forced_adds_flag_27():
    st = _mk_state()
    FinishUnitTurnOperation.execute(st, 1, forced=True)
    fl = st.get_entity(1).get_component(UnitFlagsComponent)
    assert fl.has(UnitFlagsComponent.TURN_FINISHED_FORCED)       # flag 0x1b
    assert fl.turn_ended()


# ------------------------------------------------- IdunBattle.Operations.ActiveAbilityOperation$$AddFlagsAfterAbilityExecution

def test_add_flags_normal_ability_ends_turn():
    st = _mk_state()
    add_flags_after_ability_execution(st, 1, skip_ability_used=False, skip_end_turn=False)
    fl = st.get_entity(1).get_component(UnitFlagsComponent)
    assert fl.has(UnitFlagsComponent.ACTIVE_ABILITY_USED)        # flag 2
    assert fl.turn_ended()                                       # flags 1+3 via FinishUnitTurn


def test_add_flags_skip_end_turn_keeps_unit_playable():
    st = _mk_state()
    add_flags_after_ability_execution(st, 1, skip_ability_used=True, skip_end_turn=True)
    fl = st.get_entity(1).get_component(UnitFlagsComponent)
    # composant potentiellement absent (aucun flag pose) — les deux formes sont acceptables
    assert fl is None or (not fl.turn_ended()
                          and not fl.has(UnitFlagsComponent.ACTIVE_ABILITY_USED))


# ------------------------------------------------- table d'overrides (inventaire RE, symbols.json + i2)

def test_family_overrides_vindicta_ragnar():
    st = _mk_state()
    # 1014 ArmoriumCherub (Vindicta) et 1106 WarHowl (Ragnar) : ne terminent PAS le tour.
    assert sets_end_turn_flags_for(1014, st, 1) is False
    assert sets_end_turn_flags_for(1106, st, 1) is False
    assert sets_active_ability_used_flag_for(1014, st, 1) is False
    # 1063 FireAndReposition (Calandis) : override SetsEndTurnFlags SEULEMENT (pas AbilityUsed).
    assert sets_end_turn_flags_for(1063, st, 1) is False
    assert sets_active_ability_used_flag_for(1063, st, 1) is True
    # 1077 EarlyWarningOverride (Re'vas) : override AbilityUsed SEULEMENT (le tour SE termine).
    assert sets_end_turn_flags_for(1077, st, 1) is True
    assert sets_active_ability_used_flag_for(1077, st, 1) is False
    # hors famille (ex. 1105 CrushingClaws) : defaut base = True (termine le tour).
    assert sets_end_turn_flags_for(1105, st, 1) is True
    assert 1105 not in NO_END_TURN_ABILITY_TYPES


def test_fighting_retreat_conditional_on_adjacency():
    # IdunBattleLogic.Entities.Abilities.Active.Loki.FightingRetreatAbility$$SetsActiveAbilityUsedFlag : Direct(!any ennemi adjacent) — adjacent -> ne pose PAS les flags (tour non fini).
    st_adj = _mk_state(adjacent=True)
    assert sets_end_turn_flags_for(1081, st_adj, 1) is False
    st_far = _mk_state(adjacent=False)
    assert sets_end_turn_flags_for(1081, st_far, 1) is True


# ------------------------------------------------- handler : queue d'IdunBattle.Operations.ActiveAbilityOperation$$ExecuteInternal

def test_handler_armorium_cherub_does_not_end_turn():
    # 1014 est PORTEE (classe ArmoriumCherubAbility) mais le state minimal n'a pas le kit complet ->
    # on passe par le path UNPORTED-like en retirant la classe ? NON : on teste via la table (path
    # unported) avec un id de la famille NON porte : 1106 WarHowl (Ragnar).
    st = _mk_state()
    h = AbilityHandler(st)
    h.visit_ActiveAbilityMessage(ActiveAbilityMessage(caster_id=1, target_id=2, ability_type=1106))
    fl = st.get_entity(1).get_component(UnitFlagsComponent)
    assert h.last["ported"] is False
    assert h.last["flags"]["turn_finished"] is False             # Ragnar peut encore agir
    assert fl is None or not fl.turn_ended()


def test_handler_unported_ability_outside_family_ends_turn():
    st = _mk_state()
    h = AbilityHandler(st)
    # L'id est DERIVE, plus fige : il faut un `ActiveAbilityType` HORS famille turn-flow ET HORS
    # `ABILITY_CLASSES`, et notre propre cadence de portage perime tout litteral choisi ici -- 1039
    # `RitesOfRestoration`, qui tenait ce role, est entree au registre (#564) et rendait ce test
    # ROUGE en le faisant passer par le chemin PORTE.
    from engine.runner.abilities.handler import ABILITY_CLASSES
    from engine.entities.active_ability_type import ActiveAbilityType
    aid = next(int(a) for a in sorted(ActiveAbilityType, key=int)
               if int(a) not in ABILITY_CLASSES and int(a) not in NO_END_TURN_ABILITY_TYPES
               and int(a) not in NO_ABILITY_USED_FLAG_ABILITY_TYPES and int(a) > 1000)
    h.visit_ActiveAbilityMessage(ActiveAbilityMessage(caster_id=1, target_id=2, ability_type=aid))
    fl = st.get_entity(1).get_component(UnitFlagsComponent)
    assert h.last["ported"] is False
    assert h.last["flags"]["turn_finished"] is True
    assert fl is not None and fl.turn_ended()
    assert fl.has(UnitFlagsComponent.ACTIVE_ABILITY_USED)


# ------------------------------------------------- message FinishUnitTurn + reset StartTurn

def test_finish_unit_turn_message_and_startturn_reset():
    from engine.runner.runner import Runner
    st = _mk_state()
    runner = Runner(st).install_default_handlers()
    runner.apply(FinishUnitTurnMessage(unit_id=1))
    fl = st.get_entity(1).get_component(UnitFlagsComponent)
    assert fl.turn_ended()
    # StartTurn du joueur 3 -> IdunBattle.Entities.Components.UnitFlagsComponent$$RemoveTurnFlags(0,1) : flags 0/1/2/3/12/27 retires.
    fl.add(UnitFlagsComponent.ACTIVE_ABILITY_USED)
    fl.add(UnitFlagsComponent.NO_ACTION_AVAILABLE)
    StartTurnOperation.execute(st, 3)
    assert not fl.turn_ended()
    assert not fl.has(UnitFlagsComponent.ARRIVED_AT_FINAL_TILE)
    assert not fl.has(UnitFlagsComponent.ACTIVE_ABILITY_USED)
    # NoActionAvailable est CONSERVE au StartTurn (param_3=0 natif) — leve par VerifyUnitTurnEnded.
    assert fl.has(UnitFlagsComponent.NO_ACTION_AVAILABLE)
    # les flags d'une unite d'un AUTRE joueur ne sont pas touches
    FinishUnitTurnOperation.execute(st, 2)
    StartTurnOperation.execute(st, 3)
    fl2 = st.get_entity(2).get_component(UnitFlagsComponent)
    assert fl2.turn_ended()
