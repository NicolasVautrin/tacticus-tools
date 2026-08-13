"""#1020 -- la feuille DSL `TransferDamage`, couplee a l'Operation
`engine/runner/operations/transfer_damage.py` (mirror `IdunBattle.Operations.TransferDamageOperation`).

Frontiere DSL/imperatif (doctrine #149) : l'artefact natif est un `CreateBehaviour`
(`IdunBattleLogic.Entities.Abilities.Triggered.Loki.SaviorProtocolsAbility$$CreateBehaviour` =
`If(Maybe(ConfigConst(chance)), TransferDamage(...), null)`), donc la STRUCTURE est un arbre DSL ;
la feuille, elle, appelle l'Operation impérative, comme `DirectDamage` appelle
`AttackDamageOperation.execute_direct`.
"""
from __future__ import annotations

from typing import Optional

from ....dsl.base import TargetsSelector, resolve_unit
from ....dsl.effects import AbilityBehaviour, OperationResult
from ...operations.transfer_damage import transfer_damage_operation


class TransferDamage(AbilityBehaviour):
    """`IdunBattleLogic.Entities.DSLBehaviors$$TransferDamage(caster, originalTarget,
    transferTargets, transferAbility, attackAbility)` ->
    `IdunBattle.Entities.Behaviours.TransferDamageBehaviour$$Execute`, LU :

        caster         = <behaviour+0x50>.SelectSingle(entities)     # nul -> return (rien)
        originalTarget = <behaviour+0x58>.SelectSingle(entities)
        transferTargets= <behaviour+0x60>.Select(entities)           # une LISTE
        transferAbility= <behaviour+0x68>   (Nullable<AbilityOrEffect>)  # !HasValue -> return
        attackAbility  = <behaviour+0x70>   (Nullable<AbilityOrEffect>)  # !HasValue -> return
        hitIndex       = GetValueOrDefault(entities.<+0x108>)         # le coup COURANT
        -> processor.<slot 68 = TransferDamage>(caster, originalTarget, transferTargets,
                                                transferAbility, attackAbility, hitIndex)

    Le natif prend le caster de `<+0x58>` quand `<+0x50>` rend nul (`lVar20 = lVar17 != 0 ? lVar17
    : local_res8`) -- porte tel quel par le repli `source_sel -> entities.caster`.

    `transfer_ability` / `attack_ability` : les deux `Nullable<AbilityOrEffect>` ne servent, cote
    natif, qu'a nommer la source du degat dans le flux et dans l'attribution de mort. Le port les
    porte en argument nomme mais ne les CONSOMME pas encore (residu `#1020-r2`) : l'attribution de
    mort du protecteur passe par `caster` (la source du degat), ce qui est le comportement de tous
    les autres vecteurs portes.

    Emet `TransferDamage` PAR CIBLE (le natif emet un pas de flux `0x23` par cible). PUR
    (stop=False) : `TransferDamageBehaviour$$Execute` recopie les 8 slots de l'`OperationResult`
    de l'operation, dont l'octet `+0x20` que `TransferDamageOperation$$Execute` ne pose jamais
    (il ne fait que `Combine` des resultats de `DirectDamage`)."""

    __slots__ = ("caster_sel", "original_target_sel", "transfer_targets_sel",
                 "transfer_ability", "attack_ability")

    def __init__(self, caster_sel: TargetsSelector, original_target_sel: TargetsSelector,
                 transfer_targets_sel: TargetsSelector,
                 transfer_ability=None, attack_ability=None):
        self.caster_sel = caster_sel
        self.original_target_sel = original_target_sel
        self.transfer_targets_sel = transfer_targets_sel
        self.transfer_ability = transfer_ability
        self.attack_ability = attack_ability

    def execute(self, entities, ectx):
        state = ectx.state
        if state is None:
            ectx.emit("TransferDamage", original_target=None, transfer_target=None, result=None)
            return OperationResult.ok()
        src_u = (resolve_unit(self.caster_sel, entities) if self.caster_sel is not None
                 else entities.caster)
        orig_u = resolve_unit(self.original_target_sel, entities)
        orig = (orig_u or {}).get("id")
        if orig is None:                       # `originalTarget` nul -> `Execute` RETOURNE
            ectx.emit("TransferDamage", original_target=None, transfer_target=None, result=None)
            return OperationResult.ok()
        src = (src_u or {}).get("id")
        hit_index = getattr(entities, "hit_index", None)     # `AbilityEntities+0x108`
        for u in self.transfer_targets_sel.evaluate(entities):
            tid = u.get("id") if isinstance(u, dict) else None
            if tid is None:
                continue
            res = transfer_damage_operation(state, src, int(orig), int(tid),
                                            hit_index=hit_index)
            ectx.emit("TransferDamage", original_target=int(orig), transfer_target=int(tid),
                      result=res)
        return OperationResult.ok()
