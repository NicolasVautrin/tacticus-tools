"""`IdunBattle.Entities.Effects.Loki.Narthecium_ReviveEffect` (base `ReviveEffect`) -- passif de
ultraApothecary (« Incisus », Ultramarines/Imperial) : un allie adjacent(2) NON-Mechanical vaincu est
revive-EN-PLACE a min(reviveHP[level], maxPV), **unless Overkilled**, once-per-turn, chance=100.
case-66 retrofit (#79) : premier consommateur retrofit de la base `ReviveEffect` deja portee.

i2 authoritatif : « When an adjacent friendly non-Mechanical unit is defeated, it is immediately revived
with a maximum of {hp} Health, unless Overkilled. Can only be triggered once per turn. »
(gameconfig `Narthecium` : constants {"chance":"100"} -> le `Maybe(100)` reussit TOUJOURS.)

Artefact natif (RE ghidra gqfc5mff6c, VA citees) -- la BASE (`triggers/revive_effect.py`) porte le trigger
et le behaviour ; CETTE classe ne surcharge QUE le filtre et le gate d'overkill :

  base IdunBattle.Entities.Effects.ReviveEffect$$CreateTargetTrigger  OnPreDeath(target, get_ReviveOnOverkill) &
                                                           CanBeRevived(target) & CreateTargetFilter
  Narthecium.CreateTargetFilter (0x758)        IdunBattle.Entities.Effects.Loki.Narthecium_ReviveEffect$$CreateTargetFilter  baseFilter(0x98) & AreFriends(self,target) &
                                                           IsAdjacent(self, target, 2)
                                                           (PAS de HasTrait -- contraste TaintedNarthecium
                                                            qui ajoute HasTrait(target, Chaos))
  Narthecium.get_ReviveOnOverkill (0x738)      GameCamera$$ShouldBlurBackground = `return 0` (= la BASE, aucun override)
                                                           -> `IdunBattleLogic.Entities.DSLFactory$$OnDeathEvent(1, 0, 0)` AJOUTE
                                                           `NOT(HasFlag(dying, 8=overkill))`
                                                           => « **unless** Overkilled » (lu LIVE par
                                                           `probe_79_revive_vtable.py`, PAS deduit).
  base IdunBattle.Entities.Effects.ReviveEffect$$CreateTargetTriggerBehaviour Maybe(chance){ Revive(...) ; DeactivateEffect }
  Narthecium..IdunBattle.Entities.Effects.Loki.Narthecium_ReviveEffect$$.ctor : `ReviveEffect..ctor(2, 1, AbilityOrEffect(0x3e9=1001
                                TriggeredAbilityType.Narthecium), removeEffect=0)` -- STRICTEMENT identique
                                a TaintedNarthecium..IdunBattle.Entities.Effects.Loki.TaintedNarthecium_ReviveEffect$$.ctor hors le sourceId.
  IdunBattle.Entities.Effects.Loki.Narthecium_ReviveEffect$$GetReviveChance = `GetNumberConstant(config, 0x2a='chance')`
  IdunBattle.Entities.Effects.Loki.Narthecium_ReviveEffect$$GetReviveHP = `GetVariableForLevel(config, 0x1d='hp', level)`

Le « non-Mechanical » de l'i2 N'EST PAS dans le filtre : il EMERGE du noeud `CanBeRevived` de la base
(`IdunBattle.Core.Services.BattleQuery$$CanBeRevived` -> `IdunBattle.Entities.UnitExtensions$$IsAffectedByHealType(0)` = `HasTrait(
AffectedByHealAndRepair) OR NOT IsMechanical`) -- porte une seule fois dans `revive_effect.can_be_revived`.
"""
from __future__ import annotations

from ....state import State
from .....dsl.base import _pos
from ..base import TriggerEvent
from ..revive_effect import ReviveEffectAbility, are_friends

import hexgeo

ABILITY_ID = "Narthecium"
ADJACENCY_RANGE = 2                              # IsAdjacent(self, target, 2)


class NartheciumReviveAbility(ReviveEffectAbility):
    """`Narthecium_ReviveEffect` (IdunBattle.Entities.Effects.Loki.Narthecium_ReviveEffect$$.ctor / filter IdunBattle.Entities.Effects.Loki.Narthecium_ReviveEffect$$CreateTargetFilter) -- passif revive-en-place de
    ultraApothecary. Structure 100% heritee de la base ; seuls le filtre (pas de HasTrait) et
    `revive_on_overkill=False` (« unless Overkilled ») different de TaintedNarthecium."""
    ability_id = ABILITY_ID
    revive_on_overkill = False                   # get_ReviveOnOverkill GameCamera$$ShouldBlurBackground = 0 (unless Overkilled)

    def create_target_filter(self, state: State, ev: TriggerEvent, entities) -> bool:
        """`IdunBattle.Entities.Effects.Loki.Narthecium_ReviveEffect$$CreateTargetFilter` = `baseFilter & AreFriends(self,target) &
        IsAdjacent(self, target, 2)`."""
        # AreFriends(self@0x148, target@0x178)
        if not are_friends(state, self.owner_id, ev.dying_id):
            return False
        # IsAdjacent(self, target, 2) : distance hex <= 2
        pa, pb = _pos(entities.caster), _pos(entities.target)
        if pa is None or pb is None or hexgeo.distance(pa, pb) > ADJACENCY_RANGE:
            return False
        return True
