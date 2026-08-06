"""Feuille DSL de mutation de l'ETAT D'UTILISATION des abilities actives : `ResetActiveAbility`.
Wrapper MINCE au-dessus de `runner/operations/ability_reset.py`. Namespace natif
`Entities.Behaviours.*`.
"""
from __future__ import annotations

from ....dsl.base import TargetsSelector, _units_of
from ....dsl.effects import AbilityBehaviour, OperationResult
from ...operations.ability_reset import ResetActiveAbilityOperation


class ResetActiveAbility(AbilityBehaviour):
    """`IdunBattleLogic.Entities.DSLFactory$$ResetActiveAbility(unitSel, flag)` ->
    `IdunBattle.Entities.Behaviours.ResetActiveAbilityBehaviour$$Execute` -- MIRROR du DECOMPILE :

        foreach unit in (this+0x50).Select(entities, kind 4) :
            proc.<slot 0x75>(unit, this+0x58 /* flag ignoreTurnFlag */)

    -> `IdunBattle.Operations.ResetActiveAbilityOperation$$Execute` (porte, cf.
    `operations/ability_reset.py`) : re-arme les abilities actives de l'unite (`CanStillBeUsed = 1`,
    cooldown remis a zero), sous le gate `BattleQuery.EntityCanHaveActiveAbilityReset`.

    Unique consommateur porte : `IdunBattleLogic.Entities.Abilities.Active.Loki.
    InspiredToGreatnessAbility$$ExecuteBehaviour` (`ResetActiveAbility(canReset, 0)` -- 4e et dernier
    terme de son `op_BitwiseAnd`). Emet 'ResetActiveAbility' par unite. PUR (stop=False)."""
    __slots__ = ("unit_sel", "ignore_turn_flag")

    def __init__(self, unit_sel: TargetsSelector, ignore_turn_flag: bool = False):
        self.unit_sel, self.ignore_turn_flag = unit_sel, bool(ignore_turn_flag)

    def execute(self, entities, ectx):
        state = ectx.state
        if state is None:
            return OperationResult.ok()
        for u in _units_of(self.unit_sel, entities):
            uid = u.get("id") if isinstance(u, dict) else None
            if uid is None:
                continue
            r = ResetActiveAbilityOperation.execute(state, int(uid), self.ignore_turn_flag)
            ectx.emit("ResetActiveAbility", unit=int(uid), reset=r["reset"], gate=r["gate"])
        return OperationResult.ok()

# TEMP mesure #486-r11
