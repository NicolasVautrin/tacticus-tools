"""`Abilities.Effects.Loki.TaintedNarthecium_ReviveEffect` (base `ReviveEffect`) -- passif de deathRotbone
(Death Guard/Chaos) : un allie Chaos adjacent(2) vaincu a 75% de chance d'etre revive-EN-PLACE a
min(reviveHP[level], maxPV), even-if-Overkilled, once-per-turn. case-66 (debloqueur sous-systeme REVIVE).

RE ghidra gqfc5mff6c (VA citees) + i2 authoritatif (« An adjacent friendly Chaos unit that is defeated has
a {chance}% chance to be revived with a maximum of {hp} Health, even if Overkilled. Can only be triggered
once per turn. »).

Artefact natif (frontiere #149) -- la BASE (`triggers/revive_effect.py`, mirror de
`IdunBattle.Entities.Effects.ReviveEffect`) porte le trigger + le behaviour ; CETTE classe ne surcharge
QUE le filtre et le gate d'overkill :

  base IdunBattle.Entities.Effects.ReviveEffect$$CreateTargetTrigger  OnPreDeath(target, get_ReviveOnOverkill) &
                                                           CanBeRevived(target) & CreateTargetFilter
  TaintedNarthecium.CreateTargetFilter (0x758) IdunBattle.Entities.Effects.Loki.TaintedNarthecium_ReviveEffect$$CreateTargetFilter  baseFilter(0x98) & AreFriends(self,target) &
                                                           HasTrait(target, Chaos=0x7ea=2026) &
                                                           IsAdjacent(self, target, 2)

⚠ LE `2` D'`IsAdjacent` N'EST PAS UN RAYON -- c'est un `UnitSelectionType` (#462-r4b-r1-r1-r1-r1-b-r1).
Le decompile de CE filtre sur `rnca9r7q6c` appelle le MEME noeud que Narthecium, avec le MEME litteral :
`IdunBattleLogic.Entities.DSLTriggers$$IsAdjacent(this, sel@+0x30, sel@+0x60, 0x2)` ->
`IdunBattle.Entities.Triggers.IsAdjacentAbilityTrigger$$.ctor` range `(int)selectionType` en `+0x18`, et
`$$ShouldTrigger` ne lit ce champ QUE comme 2e argument du `Select` des deux selecteurs -- le predicat
par paire est `query.AreEntitiesAdjacent(x, y)` (slot 0x60), SANS rayon. Enum
`IdunBattle.Entities.Enum.UnitSelectionType` : `0=Any, 1=OnlyAlive, 2=OnlyTargetable,
3=OnlyAliveAndTargetable`. Le port lisait `distance <= 2` -> il ACCEPTAIT des revives a 2 hex que le
natif REFUSE. Corrige : le terme passe par le mirror `entities/triggers.py::IsAdjacent`.
Demonstration complete + confrontation live : `docs/rl/case-462-r4b-r1-r1-r1-r1-b-r1-isadjacent-selection-type.md`.
  TaintedNarthecium.get_ReviveOnOverkill (0x738) GameCamera$$get_ShouldDisableRenderingWhenBehindSomething = `return 1`  -> AUCUN gate overkill
                                                           (« even if Overkilled ») -- lu LIVE par
                                                           `probe_79_revive_vtable.py`, PAS deduit.
  base IdunBattle.Entities.Effects.ReviveEffect$$CreateTargetTriggerBehaviour Maybe(chance){ Revive(...) ; DeactivateEffect }
  TaintedNarthecium..IdunBattle.Entities.Effects.Loki.TaintedNarthecium_ReviveEffect$$.ctor : `ReviveEffect..ctor(2, 1, AbilityOrEffect(0x42b=1067
                                       TriggeredAbilityType.TaintedNarthecium), removeEffect=0)` ;
                                       GetReviveHP (var 0x1d='hp') / GetReviveChance (const 0x2a='chance')
                                       ont un corps IDENTIQUE a celui de Narthecium (ICF fold IdunBattle.Entities.Effects.Loki.Narthecium_ReviveEffect$$GetReviveHP /
                                       IdunBattle.Entities.Effects.Loki.Narthecium_ReviveEffect$$GetReviveChance) -> memes formules, config par instance.
"""
from __future__ import annotations

from ....state import State
from .....entities.traits.unit_trait import UnitTrait
from .....entities.selectors import Caster, Target
from .....entities.triggers import IsAdjacent
from ..base import TriggerEvent
from ..revive_effect import ReviveEffectAbility, are_friends

ABILITY_ID = "TaintedNarthecium"
CHAOS = int(UnitTrait.Chaos)                     # 0x7ea=2026 (HasTrait(target, Chaos))
# 3e argument d'`DSLTriggers$$IsAdjacent` = `UnitSelectionType`, PAS un rayon (cf. en-tete).
ONLY_TARGETABLE = 2                              # UnitSelectionType.OnlyTargetable
_IS_ADJACENT = IsAdjacent(Caster(), Target(), ONLY_TARGETABLE)


class TaintedNartheciumReviveAbility(ReviveEffectAbility):
    """`TaintedNarthecium_ReviveEffect` (IdunBattle.Entities.Effects.Loki.TaintedNarthecium_ReviveEffect$$.ctor / filter IdunBattle.Entities.Effects.Loki.TaintedNarthecium_ReviveEffect$$CreateTargetFilter) -- passif revive-en-place de
    deathRotbone. Tout le reste (trigger OnPreDeath/CanBeRevived, behaviour Maybe/Revive/DeactivateEffect,
    gate once-per-turn) vient de la base `ReviveEffectAbility`."""
    ability_id = ABILITY_ID
    revive_on_overkill = True                    # get_ReviveOnOverkill GameCamera$$get_ShouldDisableRenderingWhenBehindSomething = 1 (even if Overkilled)

    def create_target_filter(self, state: State, ev: TriggerEvent, entities) -> bool:
        """`IdunBattle.Entities.Effects.Loki.TaintedNarthecium_ReviveEffect$$CreateTargetFilter` = `baseFilter & AreFriends(self,target) &
        HasTrait(target, Chaos=0x7ea=2026) & IsAdjacent(self, target, UnitSelectionType.OnlyTargetable)`."""
        dying = ev.dying_id
        # AreFriends(self@sel+0x30, target@sel+0x60)
        if not are_friends(state, self.owner_id, dying):
            return False
        tgt = entities.target
        ht = entities.has_trait
        # HasTrait(target, Chaos=0x7ea=2026)  (== GrandAlliance Chaos)
        if ht is None or not ht(tgt, CHAOS):
            return False
        # `IsAdjacent(self, target, 2)` : ADJACENCE STRICTE (le `2` va au selecteur -- cf. en-tete).
        if not _IS_ADJACENT.should_trigger(entities):
            return False
        return True
