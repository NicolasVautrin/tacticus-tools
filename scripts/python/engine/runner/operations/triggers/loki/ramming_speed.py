"""`IdunBattleLogic.Entities.Abilities.Active.Loki.RammingSpeed_ExtraExplodeEffect` (effet 0x44a = 1098,
pose par `IdunBattleLogic.Entities.Abilities.Active.Loki.RammingSpeedAbility$$ExecuteBehaviour` sur le
CASTER) -- son trigger de RETRAIT. Cloture le residu `#389-r1`.

## Le verrou, et comment il tombe

Le natif POSE l'effet puis le RETIRE avant la fin du meme `applyAction` (mesure #389, canal
`includeInactive`) ; le port le conservait en PERMANENT (`AddEffect` options ZERO -> `remaining = 0`,
cf. `IdunBattle.Operations.AddEffectOperation$$Execute`). Le mecanisme n'etait pas nomme parce que la
classe d'effet **n'a aucune methode a son nom dans les tables** : ses quatre overrides ont des corps
DEDUPLIQUES par IL2CPP, donc attribues a d'autres classes (CLAUDE.md, « l'absence d'une methode dans
les tables ne prouve RIEN »).

Le bloc de methodes du type dans la table de pointeurs IL2CPP (5 entrees consecutives, delimitees par
le `.ctor` en tete et le `.ctor` du type suivant `HealAbility`) les rend tous :

    1. `RammingSpeed_ExtraExplodeEffect$$.ctor`
    2. corps de `IdunBattle.Entities.Effects.Loki.WayOfTheShortBlade_AdditionalAttackMarkerEffect$$CreateActiveCondition`
       = `return dsl.triggers@+0x40`                        -> `CreateActiveCondition`
    3. corps de `IdunBattle.Entities.Effects.Loki.WhisperingWebEffect$$CreateTargetSelector`
       = `return dsl.entities@+0x30`                        -> `CreateTargetSelector` = **Owner**
    4. corps de `IdunBattle.Entities.Effects.Loki.UntilOfEndPhaseEffect$$CreateRemoveEffectTrigger`
       = `IdunBattleLogic.Entities.DSLTriggers$$On(0x3a, ownerNeedsToBeAlive: false)`
                                                            -> `CreateTargetTrigger`
    5. corps de `IdunBattle.Entities.Effects.Loki.MV71SniperDroneSquad_ResetInitialDmgEffect$$CreateTargetTriggerBehaviour`
       = `IdunBattle.Entities.Effects.BaseEffect$$GetRemoveEffectBehaviour(this)`
       = `IdunBattleLogic.Entities.DSLBehaviors$$RemoveEffect(dsl.entities@+0x38 = Effect)`
                                                            -> `CreateTargetTriggerBehaviour`

L'appariement position <-> slot est CALIBRE sur `IdunBattle.Entities.Effects.Loki.PowerTrip_FullHealthEffect`,
dont les quatre overrides sont NOMMES et dont le bloc donne l'ordre canonique `.ctor`,
`CreateActiveCondition`, `CreateTargetSelector` (**meme corps partage**, position 3 des deux cotes),
`CreateEffectHitsBonusForAttack`, `CreateTargetTrigger`, `CreateTargetTriggerBehaviour`. Il est recoupe
par le NOM du proprietaire dedupliquant de chaque corps (qui coincide avec la position) et par la
SIGNATURE (seul `CreateTargetTriggerBehaviour` prend 4 parametres). Les accesseurs d'entites sont
nommes independamment par `IdunBattleLogic.Entities.DSLTriggers$$get_OwnerIsTarget` /
`$$get_OwnerIsActor` / `$$get_CasterIsTarget` (`AreEqual(entities+0x30, +0x60)` etc.) :
**`+0x30 = Owner`**, `+0x38 = Effect`, `+0x40 = Actor`, `+0x48 = Caster`, `+0x60 = Target`.

⚠ Le nom `UntilOfEndPhaseEffect$$CreateRemoveEffectTrigger` de l'entree 4 est celui du PROPRIETAIRE
DEDUPLIQUANT, pas le slot de CE type : `RammingSpeed_ExtraExplodeEffect` herite DIRECTEMENT de
`BaseEffect` (`data/symbols/<build>/frida/classes.tsv`), il n'est pas un `UntilOfEndPhaseEffect`. Les
deux lectures possibles de l'entree 4 (`CreateTargetTrigger` ou `CreateRemoveEffectTrigger`) rendent de
toute facon le MEME verdict de retrait -- seule change la fonction native qui assemble le
`Triggered(trigger, RemoveEffect)` (`BaseEffect$$CreateHandleTriggerAbilitiesInternal` contre
`IdunBattle.Entities.Effects.BaseEffect$$CreateHandleTriggerAbilities`).

## `0x3a` = `EventTriggerType.PhaseEnd` (58), et il tombe DANS le meme `applyAction`

`data/symbols/<build>/frida/enums.tsv`, `IdunBattle.DSL.EventTriggerType` -- appariement verifie par
DEUX noms de classe : `UntilOfEndTurnEffect` -> `On(0x17 = TurnEnd)`, `UntilOfEndPhaseEffect` ->
`On(0x3a = PhaseEnd)`.

L'emetteur est `IdunBattle.Operations.EndPhaseOperation$$Execute` (publie `0x3a` puis
`$$ResetTileReservation` + `$$ResetEntityPhase`), atteint par `Core.Services.OperationProcessor$$EndPhase`
-- qui n'a AUCUN appelant direct dans le binaire, seulement le slot appele par
`IdunBattle.Messages.InputMessageProcessor$$RunPhase` dans sa branche `isInternalPhase == false`. Or
`$$RunPhase` EST le corps d'un `applyAction` : les `InputMessageProcessor$$Visit` (un par type de
message d'entree) l'appellent avec `isInternalPhase = 0` (verifie sur le `Visit` d'AddUnit :
`RunPhase(this, 0x4, action, 0, 0)`), tandis que la cascade interne
`$$ProcessPendingTriggeredAbilities` l'appelle avec `RunPhase(this, 0xf, action, 1, 0)`. **Une phase =
un message top-level**, et sa cloture emet `PhaseEnd`. C'est exactement la fenetre mesuree.

## Consequence pour le port

Cote port, la borne de phase est `Runner.apply` (qui portait deja `state.reset_trigger_phases()`, l'autre
geste d'`EndPhaseOperation`). Le vecteur `phase_end_triggers` y est ajoute EN SORTIE ; cette entree de
registre en est le seul consommateur aujourd'hui.

INERTIE MESUREE : sur les 5 bras de `probe_389_ramming_speed_combat_port.py`, l'ecart etait INVISIBLE --
le seul consommateur de 1098 (`IdunBattleLogic.Entities.Abilities.Active.Loki.ExplodesAbility$$GetDamage`,
`ConditionalAmount(HasEffect(Owner, 1098), ...)`) le lit PENDANT le cast, donc avant `PhaseEnd`. L'ecart
mord des qu'un consommateur lit 1098 APRES le cast -- typiquement le tour suivant, ou la nova d'une mort
survenant plus tard : sans ce retrait, le porteur garderait +50 % de degat d'explosion A VIE.

## Ce qui reste ASSUME

`On(0x3a, ownerNeedsToBeAlive: false)` : le natif ne gate PAS sur la vie du porteur, le dispatch du port
si (`CanGet*Trigger`). Ecart identique a `UntilOfEndTurnRemove` et sans effet observable -- un caster tue
par son propre contrecoup a deja perdu tous ses effets par `IdunBattle.Operations.KillUnitOperation$$RemoveEffects`.

COLLAPSE ASSUME, identique a `ChronometronExtraDamageRemove` : le natif retire L'INSTANCE
(`RemoveEffect(Effect@0x38)`), le port retire tous les 1098 non consommes du porteur
(`RemoveEffect(effect_type, Caster())`, la seule forme portee). Les deux coincident -- le gate « deja
present » d'`AddEffectOperation` garantit au plus UNE instance par unite.
"""
from __future__ import annotations

from typing import Optional

from ....state import State
from ....abilities.behaviours import RemoveEffect, entities_from_state
from .....entities.effect_type import EffectType
from .....entities.selectors import Caster
from .....dsl.effects import ExecutionContext
from .....dsl.event_trigger_type import EventTriggerType
from ..base import EffectTrigger, TriggerEvent

RAMMING_SPEED_EXTRA_EXPLODE = int(EffectType.RammingSpeed_ExtraExplode)   # 0x44a = 1098


class RammingSpeedExtraExplodeRemove(EffectTrigger):
    """`RammingSpeed_ExtraExplodeEffect$$CreateTargetTrigger` = `DSLTriggers$$On(PhaseEnd = 0x3a,
    ownerNeedsToBeAlive: false)` -> `$$CreateTargetTriggerBehaviour` =
    `BaseEffect$$GetRemoveEffectBehaviour` = `DSLBehaviors$$RemoveEffect(<cette instance>)`.

    AUCUN predicat : le trigger natif est un `On(...)` NU (pas de `& OwnerIs*`, pas de `& AreEqual`).
    Rien a evaluer dans `matches` -- le sur-ensemble de gates du dispatch (event_id + porteur vivant)
    suffit, et le sujet du retrait est le porteur lui-meme (`CreateTargetSelector` = `Owner`)."""
    effect_type = RAMMING_SPEED_EXTRA_EXPLODE
    event_id = int(EventTriggerType.PhaseEnd)              # On(0x3a = 58)

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        return True

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        if state.effects is None:
            return None
        ectx = ExecutionContext(state=state, rng=state.rng)
        RemoveEffect(RAMMING_SPEED_EXTRA_EXPLODE, Caster()).execute(
            entities_from_state(state, self.owner_id, self.owner_id), ectx)
        removed = sum(int(p.get("removed") or 0) for n, p in ectx.emitted if n == "RemoveEffect")
        if not removed:
            return None
        return {"effect": "RammingSpeed_ExtraExplode", "owner": int(self.owner_id),
                "removed": removed}
