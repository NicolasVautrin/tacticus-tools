"""Feuilles DSL de mutation de l'ETAT D'UTILISATION des abilities actives : `ResetActiveAbility`
(re-arme) et `SetActiveAbilityUsed` (consomme). Wrappers MINCES au-dessus de
`runner/operations/ability_reset.py`. Namespace natif `Entities.Behaviours.*`.
"""
from __future__ import annotations

from ....dsl.base import TargetsSelector, _units_of
from ....dsl.effects import AbilityBehaviour, OperationResult
from ...operations.ability_reset import ResetActiveAbilityOperation, SetActiveAbilityUsedOperation


class ResetActiveAbility(AbilityBehaviour):
    """`IdunBattleLogic.Entities.DSLBehaviors$$ResetActiveAbility(unitSel, flag)` ->
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


class SetActiveAbilityUsed(AbilityBehaviour):
    """`IdunBattleLogic.Entities.DSLBehaviors$$SetActiveAbilityUsed(units, activeAbilityType)` ->
    `IdunBattle.Entities.Behaviours.SetActiveAbilityUsedBehaviour$$Execute` -- MIRROR du DECOMPILE :

        foreach unit in (this+0x58 units).<slot 4 = SelectUniqueUnits>(entities, 3) :
            proc.<slot 0x74>(unit, this+0x50 /* activeAbilityType */)

    -> `IdunBattle.Operations.SetActiveAbilityUsedOperation$$Execute` (porte, cf.
    `operations/ability_reset.py`) : CONSOMME la charge de l'ability nommee sur l'unite
    (`CanStillBeUsed = false`), sous le gate `UnitExtensions.HasUnusedAbility`.

    L'ORDRE DES CHAMPS EST LU, pas devine : `SetActiveAbilityUsedBehaviour$$.ctor(this, units,
    activeAbilityType)` ecrit `this+0x58 <- units` et `this+0x50 <- (int)activeAbilityType`.
    L'INVERSE exact de `ResetActiveAbility` ci-dessus, qui appelle le slot `0x75`.

    Unique consommateur porte : `IdunBattleLogic.Entities.Abilities.Active.Loki.
    PrecisionShot_AimAbility$$ExecuteBehaviour` (`SetActiveAbilityUsed(Owner@+0x30, 0x3f7 = 1015
    PrecisionShot)` -- 2e terme de son `op_BitwiseAnd`).

    ⚠ **L'ENUM DU 2e ARGUMENT EST `ActiveAbilityType`** (`0x3f7` = 1015 = `PrecisionShot`), alors
    que le PREMIER terme du meme arbre pose l'EFFET `0x3f7` = 1015 = `EffectType.PrecisionShot_Aim`.
    Meme ordinal, deux enums, deux choses : le port les nomme tous les deux plutot que d'ecrire
    l'entier une fois pour deux roles.

    Emet 'SetActiveAbilityUsed' par unite. PUR (stop=False)."""
    __slots__ = ("unit_sel", "active_ability_type")

    def __init__(self, unit_sel: TargetsSelector, active_ability_type: int):
        self.unit_sel, self.active_ability_type = unit_sel, int(active_ability_type)

    def execute(self, entities, ectx):
        state = ectx.state
        if state is None:
            return OperationResult.ok()
        for u in _units_of(self.unit_sel, entities):
            uid = u.get("id") if isinstance(u, dict) else None
            if uid is None:
                continue
            r = SetActiveAbilityUsedOperation.execute(state, int(uid), self.active_ability_type)
            ectx.emit("SetActiveAbilityUsed", unit=int(uid),
                      ability_type=self.active_ability_type, used=r["used"], gate=r["gate"])
        return OperationResult.ok()
