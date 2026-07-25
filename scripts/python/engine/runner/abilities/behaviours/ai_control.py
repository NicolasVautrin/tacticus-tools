"""Feuille DSL de la famille AI-CONTROL : `PerformAIAction` — faire AGIR une ou plusieurs unites TIERCES.

Namespace natif `IdunBattle.Entities.Behaviours`. Wrapper MINCE au-dessus de l'Operation portee
`runner/operations/summon_ai.py::ComputerActionOperation` (la frontiere DSL/imperatif = ce `.execute`).
Sa soeur `PerformAIAttack` (`PerformAIAbilityUnitBehaviour`) vit dans `summon.py` (couplee au spawn
GetEmRuntz). cf. docs/rl/dsl-effect-nodes.md.
"""
from __future__ import annotations

from ....dsl.base import TargetsSelector
from ....dsl.effects import AbilityBehaviour, OperationResult


class PerformAIAction(AbilityBehaviour):
    """`DSLFactory.PerformAIAction(selector, asGroup, resetTurnFlags) @180df8990` ->
    `PerformAIActionBehaviour` (ctor @180fcbda0 : selector@+0x50, asGroup@+0x58, resetTurnFlags@+0x59)
    -> `PerformAIActionBehaviour.Execute @180fcba10` (MIRROR 1:1) :

        units = selector.Select(entities)                       # iface TargetsSelector slot 4
        if (!asGroup)  foreach (u in units) proc.ComputerAction(u, resetTurnFlags)    # iface slot 0x34
        else                                proc.ComputerAction(units, resetTurnFlags) # iface slot 0x35

    `OperationProcessor.ComputerAction` @180e07330 (mono) / @180e07360 (groupe) ->
    `ComputerActionOperation.Execute` @180e641e0 / @180e63d80.

    Les deux booleens (LUS du decompile, pas devines) :
      • `asGroup` (+0x58) : FAUX -> une action AI **par unite, sequentielle et independante**
        (`AiControl.ExecuteFor(unit)` @180ffbda0, une seule passe de decision par unite) ;
        VRAI -> le set est confie au GROUP OPERATOR (`AiControl.ExecuteFor(group)` @180ffbeb0 qui
        BOUCLE `PickNextUnit` jusqu'a epuisement des unites valides).
      • `resetTurnFlags` (+0x59) : VRAI -> les flags de tour de chaque cible sont **sauvegardes,
        effaces, puis restaures** autour de l'action -> l'unite agit meme si elle avait deja fini son
        tour, ET **l'action supplementaire ne consomme pas son tour**. C'est la semantique
        d'ordonnancement du mecanisme (cf. `ComputerActionOperation`).

    Appels natifs recenses (xrefs @180df8990) : `SupremeCommanderAbility.ExecuteBehaviour @18120df30`
    (`asGroup=1, reset=1`), `CultDemagogueAbility.ExecuteBehaviour @1811cdc30` (`0, 1`),
    `WaaaghAbility.ExecuteBehaviour @18122b010` + `GetTriggerSummonsBehaviour`,
    `ReanimationBeamAbility.GetSummonsTakeActionBehaviour @1811ff510`,
    `BlackRage_ActivationAbility.CreateBehaviour @180e19ef0`, `AdaptiveStrategyAbility.ExecuteBehaviour`.

    Effet PUR (`stop=False`). Journalise `PerformAIAction` (diag replay-diff)."""
    __slots__ = ("selector", "as_group", "reset_turn_flags")

    def __init__(self, selector: TargetsSelector, as_group: bool = False,
                 reset_turn_flags: bool = True):
        self.selector = selector
        self.as_group = bool(as_group)
        self.reset_turn_flags = bool(reset_turn_flags)

    def execute(self, entities, ectx):
        from ...operations.summon_ai import ComputerActionOperation
        state = ectx.state
        if state is None:
            return OperationResult.ok()
        units = self.selector.evaluate(entities) or []
        uids = [u.get("id") for u in units if isinstance(u, dict) and u.get("id") is not None]
        if self.as_group:
            res = ComputerActionOperation.execute_group(state, uids, self.reset_turn_flags)
        else:
            res = [ComputerActionOperation.execute(state, uid, self.reset_turn_flags)
                   for uid in uids]
        ectx.emit("PerformAIAction", units=uids, as_group=self.as_group,
                  reset_turn_flags=self.reset_turn_flags, results=res)
        return OperationResult.ok()
