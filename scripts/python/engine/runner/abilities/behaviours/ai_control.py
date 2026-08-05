"""Feuille DSL de la famille AI-CONTROL : `PerformAIAction` — faire AGIR une ou plusieurs unites TIERCES.

Namespace natif `IdunBattle.Entities.Behaviours`. Wrapper MINCE au-dessus de l'Operation portee
`runner/operations/summon_ai.py::ComputerActionOperation` (la frontiere DSL/imperatif = ce `.execute`).
Sa soeur `PerformAIAttack` (`PerformAIAbilityUnitBehaviour`) vit dans `summon.py` (couplee au spawn
GetEmRuntz). cf. docs/rl/dsl-effect-nodes.md.
"""
from __future__ import annotations

from ....dsl.base import TargetsSelector
from ....dsl.effects import AbilityBehaviour, OperationResult
from ...operations.summon_ai import ComputerActionOperation


class PerformAIAction(AbilityBehaviour):
    """`IdunBattleLogic.Entities.DSLFactory$$PerformAIAction(selector, asGroup, resetTurnFlags)` ->
    `PerformAIActionBehaviour` (IdunBattle.Entities.Behaviours.PerformAIActionBehaviour$$.ctor : selector@+0x50, asGroup@+0x58, resetTurnFlags@+0x59)
    -> `IdunBattle.Entities.Behaviours.PerformAIActionBehaviour$$Execute` (MIRROR 1:1) :

        units = selector.Select(entities)                       # iface TargetsSelector slot 4
        if (!asGroup)  foreach (u in units) proc.ComputerAction(u, resetTurnFlags)    # iface slot 0x34
        else                                proc.ComputerAction(units, resetTurnFlags) # iface slot 0x35

    `Core.Services.OperationProcessor$$ComputerAction (mono) / Core.Services.OperationProcessor$$ComputerAction (groupe) ->
    `IdunBattle.Operations.ComputerActionOperation$$Execute / IdunBattle.Operations.ComputerActionOperation$$Execute.

    Les deux booleens (LUS du decompile, pas devines) :
      • `asGroup` (+0x58) : FAUX -> une action AI **par unite, sequentielle et independante**
        (`IdunBattle.Core.Services.AiControl$$ExecuteFor(unit), une seule passe de decision par unite) ;
        VRAI -> le set est confie au GROUP OPERATOR (`IdunBattle.Core.Services.AiControl$$ExecuteFor(group) qui
        BOUCLE `PickNextUnit` jusqu'a epuisement des unites valides).
      • `resetTurnFlags` (+0x59) : VRAI -> les flags de tour de chaque cible sont **sauvegardes,
        effaces, puis restaures** autour de l'action -> l'unite agit meme si elle avait deja fini son
        tour, ET **l'action supplementaire ne consomme pas son tour**. C'est la semantique
        d'ordonnancement du mecanisme (cf. `ComputerActionOperation`).

    Appels natifs recenses (xrefs IdunBattleLogic.Entities.DSLFactory$$PerformAIAction) : `IdunBattleLogic.Entities.Abilities.Active.Loki.SupremeCommanderAbility$$ExecuteBehaviour`
    (`asGroup=1, reset=1`), `IdunBattleLogic.Entities.Abilities.Active.Loki.CultDemagogueAbility$$ExecuteBehaviour` (`0, 1`),
    `IdunBattleLogic.Entities.Abilities.Active.Loki.WaaaghAbility$$ExecuteBehaviour` + `GetTriggerSummonsBehaviour`,
    `IdunBattleLogic.Entities.Abilities.Active.Loki.ReanimationBeamAbility$$GetSummonsTakeActionBehaviour`,
    `IdunBattleLogic.Entities.Abilities.Triggered.Loki.BlackRage_ActivationAbility$$CreateBehaviour`, `AdaptiveStrategyAbility.ExecuteBehaviour`.

    Effet PUR (`stop=False`). Journalise `PerformAIAction` (diag replay-diff)."""
    __slots__ = ("selector", "as_group", "reset_turn_flags")

    def __init__(self, selector: TargetsSelector, as_group: bool = False,
                 reset_turn_flags: bool = True):
        self.selector = selector
        self.as_group = bool(as_group)
        self.reset_turn_flags = bool(reset_turn_flags)

    def execute(self, entities, ectx):
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
