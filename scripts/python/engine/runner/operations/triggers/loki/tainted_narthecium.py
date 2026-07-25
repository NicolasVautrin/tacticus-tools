"""`Abilities.Effects.Loki.TaintedNarthecium_ReviveEffect` (base `ReviveEffect`) -- passif de deathRotbone
(Death Guard/Chaos) : un allie Chaos adjacent(2) vaincu a 75% de chance d'etre revive-EN-PLACE a
min(reviveHP[level], maxPV), even-if-Overkilled, once-per-turn. case-66 (debloqueur sous-systeme REVIVE).

RE ghidra gqfc5mff6c (VA citees) + i2 authoritatif (« An adjacent friendly Chaos unit that is defeated has
a {chance}% chance to be revived with a maximum of {hp} Health, even if Overkilled. Can only be triggered
once per turn. »).

Artefact natif (frontiere #149) -- la BASE (`triggers/revive_effect.py`, mirror de
`IdunBattle.Entities.Effects.ReviveEffect`) porte le trigger + le behaviour ; CETTE classe ne surcharge
QUE le filtre et le gate d'overkill :

  base ReviveEffect.CreateTargetTrigger        @180f46d80  OnPreDeath(target, get_ReviveOnOverkill) &
                                                           CanBeRevived(target) & CreateTargetFilter
  TaintedNarthecium.CreateTargetFilter (0x758) @180f709b0  baseFilter(0x98) & AreFriends(self,target) &
                                                           HasTrait(target, Chaos=0x7ea=2026) &
                                                           IsAdjacent(self, target, 2)
  TaintedNarthecium.get_ReviveOnOverkill (0x738) @1802b1590 = `return 1`  -> AUCUN gate overkill
                                                           (« even if Overkilled ») -- lu LIVE par
                                                           `probe_79_revive_vtable.py`, PAS deduit.
  base ReviveEffect.CreateTargetTriggerBehaviour @180f46a70 Maybe(chance){ Revive(...) ; DeactivateEffect }
  TaintedNarthecium..ctor @180f70a90 : `ReviveEffect..ctor(2, 1, AbilityOrEffect(0x42b=1067
                                       TriggeredAbilityType.TaintedNarthecium), removeEffect=0)` ;
                                       GetReviveHP (var 0x1d='hp') / GetReviveChance (const 0x2a='chance')
                                       ont un corps IDENTIQUE a celui de Narthecium (ICF fold @180f5add0 /
                                       @180f5ada0) -> memes formules, config par instance.
"""
from __future__ import annotations

from ....state import State
from .....entities.traits.unit_trait import UnitTrait
from .....dsl.base import _pos
from ..base import TriggerEvent
from ..revive_effect import ReviveEffectAbility, are_friends

import hexgeo

ABILITY_ID = "TaintedNarthecium"
CHAOS = int(UnitTrait.Chaos)                     # 0x7ea=2026 (HasTrait(target, Chaos))
ADJACENCY_RANGE = 2                              # IsAdjacent(self, target, 2)


class TaintedNartheciumReviveAbility(ReviveEffectAbility):
    """`TaintedNarthecium_ReviveEffect` (ctor @180f70a90 / filter @180f709b0) -- passif revive-en-place de
    deathRotbone. Tout le reste (trigger OnPreDeath/CanBeRevived, behaviour Maybe/Revive/DeactivateEffect,
    gate once-per-turn) vient de la base `ReviveEffectAbility`."""
    ability_id = ABILITY_ID
    revive_on_overkill = True                    # get_ReviveOnOverkill @1802b1590 = 1 (even if Overkilled)

    def create_target_filter(self, state: State, ev: TriggerEvent, entities) -> bool:
        """`CreateTargetFilter @180f709b0` = `baseFilter & AreFriends(self,target) &
        HasTrait(target, Chaos=0x7ea=2026) & IsAdjacent(self, target, 2)`."""
        dying = ev.dying_id
        # AreFriends(self@0x148, target@0x178)
        if not are_friends(state, self.owner_id, dying):
            return False
        tgt = entities.target
        ht = entities.has_trait
        # HasTrait(target, Chaos=0x7ea=2026)  (== GrandAlliance Chaos)
        if ht is None or not ht(tgt, CHAOS):
            return False
        # IsAdjacent(self, target, 2) : distance hex <= 2
        pa, pb = _pos(entities.caster), _pos(tgt)
        if pa is None or pb is None or hexgeo.distance(pa, pb) > ADJACENCY_RANGE:
            return False
        return True
