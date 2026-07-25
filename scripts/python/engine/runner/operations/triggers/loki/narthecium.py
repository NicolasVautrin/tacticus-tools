"""`IdunBattle.Entities.Effects.Loki.Narthecium_ReviveEffect` (base `ReviveEffect`) -- passif de
ultraApothecary (« Incisus », Ultramarines/Imperial) : un allie adjacent(2) NON-Mechanical vaincu est
revive-EN-PLACE a min(reviveHP[level], maxPV), **unless Overkilled**, once-per-turn, chance=100.
case-66 retrofit (#79) : premier consommateur retrofit de la base `ReviveEffect` deja portee.

i2 authoritatif : « When an adjacent friendly non-Mechanical unit is defeated, it is immediately revived
with a maximum of {hp} Health, unless Overkilled. Can only be triggered once per turn. »
(gameconfig `Narthecium` : constants {"chance":"100"} -> le `Maybe(100)` reussit TOUJOURS.)

Artefact natif (RE ghidra gqfc5mff6c, VA citees) -- la BASE (`triggers/revive_effect.py`) porte le trigger
et le behaviour ; CETTE classe ne surcharge QUE le filtre et le gate d'overkill :

  base ReviveEffect.CreateTargetTrigger        @180f46d80  OnPreDeath(target, get_ReviveOnOverkill) &
                                                           CanBeRevived(target) & CreateTargetFilter
  Narthecium.CreateTargetFilter (0x758)        @180f5acf0  baseFilter(0x98) & AreFriends(self,target) &
                                                           IsAdjacent(self, target, 2)
                                                           (PAS de HasTrait -- contraste TaintedNarthecium
                                                            qui ajoute HasTrait(target, Chaos))
  Narthecium.get_ReviveOnOverkill (0x738)      @1802b15a0 = `return 0` (= la BASE, aucun override)
                                                           -> `OnDeathEvent(1, 0, 0) @180df7ad0` AJOUTE
                                                           `NOT(HasFlag(dying, 8=overkill))`
                                                           => « **unless** Overkilled » (lu LIVE par
                                                           `probe_79_revive_vtable.py`, PAS deduit).
  base ReviveEffect.CreateTargetTriggerBehaviour @180f46a70 Maybe(chance){ Revive(...) ; DeactivateEffect }
  Narthecium..ctor @180f5ae20 : `ReviveEffect..ctor(2, 1, AbilityOrEffect(0x3e9=1001
                                TriggeredAbilityType.Narthecium), removeEffect=0)` -- STRICTEMENT identique
                                a TaintedNarthecium..ctor @180f70a90 hors le sourceId.
  Narthecium.GetReviveChance @180f5ada0 = `GetNumberConstant(config, 0x2a='chance')`
  Narthecium.GetReviveHP     @180f5add0 = `GetVariableForLevel(config, 0x1d='hp', level)`

Le « non-Mechanical » de l'i2 N'EST PAS dans le filtre : il EMERGE du noeud `CanBeRevived` de la base
(`BattleQuery.CanBeRevived @181058a50` -> `IsAffectedByHealType(0) @180ed77d0` = `HasTrait(
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
    """`Narthecium_ReviveEffect` (ctor @180f5ae20 / filter @180f5acf0) -- passif revive-en-place de
    ultraApothecary. Structure 100% heritee de la base ; seuls le filtre (pas de HasTrait) et
    `revive_on_overkill=False` (« unless Overkilled ») different de TaintedNarthecium."""
    ability_id = ABILITY_ID
    revive_on_overkill = False                   # get_ReviveOnOverkill @1802b15a0 = 0 (unless Overkilled)

    def create_target_filter(self, state: State, ev: TriggerEvent, entities) -> bool:
        """`CreateTargetFilter @180f5acf0` = `baseFilter & AreFriends(self,target) &
        IsAdjacent(self, target, 2)`."""
        # AreFriends(self@0x148, target@0x178)
        if not are_friends(state, self.owner_id, ev.dying_id):
            return False
        # IsAdjacent(self, target, 2) : distance hex <= 2
        pa, pb = _pos(entities.caster), _pos(entities.target)
        if pa is None or pb is None or hexgeo.distance(pa, pb) > ADJACENCY_RANGE:
            return False
        return True
