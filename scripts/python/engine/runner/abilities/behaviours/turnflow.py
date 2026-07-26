"""Feuilles DSL de TURN-FLOW runner-couplees : `ResetTurn` (`ResetUnitTurnBehaviour`, rouvre le tour
d'une unite) et `FinishTurn` (`FinishUnitTurnBehaviour`, le clot). Wrappers MINCES au-dessus de
`runner/operations/turnflow.py` + `UnitFlagsComponent`. Namespace natif `Entities.Behaviours.*`.

Ces deux feuilles sont les DEUX branches du dernier volet de
`IdunBattleLogic.Entities.Abilities.Active.Loki.FightingRetreatAbility$$ExecuteBehaviour` :
`If(AmountIsGreater(<nb d'ennemis adjacents>, 0), ResetTurn(Owner, 1), FinishTurn(Owner))`.
"""
from __future__ import annotations

from ....dsl.base import TargetsSelector, _units_of
from ....dsl.effects import AbilityBehaviour, OperationResult
from ...components import UnitFlagsComponent


class ResetTurn(AbilityBehaviour):
    """`IdunBattleLogic.Entities.DSLFactory$$ResetTurn(unitSel, newActivation)` ->
    `IdunBattle.Entities.Behaviours.ResetUnitTurnBehaviour$$Execute` -- MIRROR du DECOMPILE :

        foreach unit in (this+0x58).Select(entities) :
            UnitFlagsComponent.RemoveTurnFlags(unit, includeNoAction = 1, newActivation = this+0x60)
            Events.Publish(0xd, unit, { 0x70 : 0 })

    Le `includeNoAction` est CONSTANT (litteral `1` au call-site du behaviour) ; seul `newActivation`
    vient du 2e argument de la factory (`ResetTurn(Owner@0x148, 1)` pour FightingRetreat -> 1).
    `RemoveTurnFlags(includeNoAction, newActivation)` (mirror porte `UnitFlagsComponent.remove_turn_flags`)
    retire {ActiveAbilityUsed(2), TurnFinished(3), TurnFinishedForced(27)} TOUJOURS, + {NoActionAvailable(4)}
    si `includeNoAction`, + {Moved(0), Teleported(12), ArrivedAtFinalTile(1)} si `newActivation`.

    => l'unite REDEVIENT activable dans le tour courant : elle peut re-bouger (Moved retire, i2 Darkstrider
    « he can move again if already moved in this turn ») et re-caster. L'event 0xd est un vecteur de VUE
    (non modelise offline, comme `Inform`). Emet 'ResetTurn' (flags retires) PAR unite. PUR (stop=False)."""
    __slots__ = ("unit_sel", "new_activation")

    def __init__(self, unit_sel: TargetsSelector, new_activation: bool = True):
        self.unit_sel, self.new_activation = unit_sel, bool(new_activation)

    def execute(self, entities, ectx):
        state = ectx.state
        if state is None:
            return OperationResult.ok()
        for u in _units_of(self.unit_sel, entities):
            uid = u.get("id") if isinstance(u, dict) else None
            if uid is None:
                continue
            e = state.get_entity(int(uid))
            if e is None:
                continue
            fl = e.get_component(UnitFlagsComponent)
            if fl is None:
                fl = e.add_component(UnitFlagsComponent())
            removed = fl.remove_turn_flags(include_no_action=True,          # litteral 1 du behaviour
                                           new_activation=self.new_activation)
            ectx.emit("ResetTurn", unit=int(uid), removed=sorted(int(f) for f in removed))
        return OperationResult.ok()


class FinishTurn(AbilityBehaviour):
    """`IdunBattleLogic.Entities.DSLFactory$$FinishTurn(unitSel)` ->
    `IdunBattle.Entities.Behaviours.FinishUnitTurnBehaviour$$Execute` -- MIRROR du DECOMPILE :

        foreach unit in (this+0x50).Select(entities) :
            proc.<slot 0x23>(unit, forced = 0)      # Core.Services.OperationProcessor$$FinishUnitTurn

    -> `IdunBattle.Operations.FinishUnitTurnOperation$$Execute` (deja porte : pose ArrivedAtFinalTile(1) +
    TurnFinished(3), `forced=False` donc PAS le flag 27). Feuille DECLARATIVE ici / Operation IMPERATIVE
    en dessous (frontiere #149). Emet 'FinishTurn' par unite. PUR (stop=False)."""
    __slots__ = ("unit_sel",)

    def __init__(self, unit_sel: TargetsSelector):
        self.unit_sel = unit_sel

    def execute(self, entities, ectx):
        from ...operations.turnflow import FinishUnitTurnOperation
        state = ectx.state
        if state is None:
            return OperationResult.ok()
        for u in _units_of(self.unit_sel, entities):
            uid = u.get("id") if isinstance(u, dict) else None
            if uid is None:
                continue
            r = FinishUnitTurnOperation.execute(state, int(uid), forced=False)
            ectx.emit("FinishTurn", unit=int(uid), **{k: r[k] for k in ("newly_finished",) if k in r})
        return OperationResult.ok()
