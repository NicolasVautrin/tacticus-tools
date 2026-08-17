"""`IdunBattleLogic.Entities.Abilities.Active.Loki.ListenUpMaggotsAbility` (triggered 1063 = 0x427,
passiveAbility d'`astraSmnKell` « Colour Sergeant Kell ») — le maillon qui POSE l'effet 0x426.

RE (decompile ghidra, build `gqfc5mff6c`) :

  `IdunBattleLogic.Entities.Abilities.Active.Loki.ListenUpMaggotsAbility$$CreateTrigger` :
      df@0xa8  &  HasUnit( Parent(caster@0x160), 3 )
  ou `df@0xa8` est le trigger de base PRE-CACHE construit par
  `IdunBattleLogic.Entities.DSLTriggers$$InitializeShared` :
      On(0x21 = AbilityInit) & df@0x128 & OwnerIsActor(owner@0x148, actor@0x158)
  (le MEME `df@0xa8` que `IdunBattleLogic.Entities.Abilities.Triggered.LifewardsAddEffectAbility$$CreateTrigger`,
  corps dedupliqe de toute la famille des owner-effects poses A L'INIT DE L'ABILITY).
  => « a l'initialisation des abilities de Kell, SI Kell a un parent (= il a ete invoque par
  quelqu'un) ».

  `IdunBattleLogic.Entities.Abilities.Active.Loki.ListenUpMaggotsAbility$$CreateBehaviour` (feuille E unique) :
      AddEffect( 0x426 = ListenUpMaggotsEffect,
                 AbilityStateReference,          # source = Kell
                 cible = owner@0x148 )           # SELF : l'effet est porte par KELL
  L'effet, lui, vise `Parent(Self)` = Creed via son `CreateTargetSelector` (cf.
  `entities/effects/loki/ability_modifications.py`). C'est cette INDIRECTION qui rend le kit lisible :
  « tant que Kell est en jeu (= porte son effet), Creed est buffe ».

DISPATCH : vecteur `ability_init_triggers` (`On(AbilityInit = 0x21 = 33)`), emis par la feuille `Spawn`
apres chaque pose de summon (mirror `IdunBattle.Operations.InitializeActorAbilitiesOperation$$Execute`).
Aucun autre trigger porte n'ecoute cet event.

i2 : « When Kell is in play, Lord Castellan Creed's active ability summons 1 extra Cadian Guardsman and
has 3 hexes range instead of 2. »

DOCTRINE #149 : les predicats du trigger sont COLLAPSES imperativement dans `matches` (OwnerIsActor +
`HasUnit(Parent(caster))`), la feuille E (`AddEffect` unit-domain) reste un noeud DSL qui delegue a
`AddEffectOperation` ; l'ecriture des modifications vit dans l'effet (part DATA) + l'Operation
`AddUnitActiveAbilityModificationOperation` (part imperative).
"""
from __future__ import annotations

from typing import Optional

from ....state import State
from ....components import parent_of
from ....abilities.behaviours.context import entities_from_state
from ....abilities.behaviours.effects import AddEffect
from .....entities.selectors.tiles import Caster
from .....entities.effect_type import EffectType
from .....dsl.effects import ExecutionContext
from .....dsl.event_trigger_type import EventTriggerType
from ..base import TriggeredAbility, TriggerEvent

LISTEN_UP_MAGGOTS_EFFECT = int(EffectType.ListenUpMaggotsEffect)   # 0x426 = 1062
_ON_ABILITY_INIT = int(EventTriggerType.AbilityInit)               # 0x21 = 33


def listen_up_maggots_tree():
    """Feuille de `IdunBattleLogic.Entities.Abilities.Active.Loki.ListenUpMaggotsAbility$$CreateBehaviour`
    (MIRROR 1:1) : `AddEffect(0x426, source = AbilityStateReference, cible = owner@0x148 = SELF)`.

    `Caster()` = le porteur (Owner == Caster pour une triggered ability). `duration_rounds=None` =
    struct de duree ZERO natif -> `DefaultAmountOfRounds(0x426)` (absent de la table) -> PERMANENT
    (`remaining = 0`). Ground truth live : `ListenUpMaggotsEffect` reste sur Kell tant qu'il vit."""
    return AddEffect(LISTEN_UP_MAGGOTS_EFFECT, EffectType.ListenUpMaggotsEffect.name,
                     Caster(), duration_rounds=None)


class ListenUpMaggotsAddEffectAbility(TriggeredAbility):
    """`ListenUpMaggotsAbility` — pose `ListenUpMaggotsEffect` (1062) sur Kell a l'init de ses abilities,
    a condition qu'il ait un PARENT. C'est le seul chemin qui rende
    `IdunBattle.Entities.UnitExtensions$$GetAbilityStatModification` non nul dans tout le build."""
    event_id = _ON_ABILITY_INIT

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        if ev.actor_id != self.owner_id:          # get_OwnerIsActor (df@0xa8)
            return False
        # `HasUnit(Parent(caster@0x160), 3)` : le selecteur `Parent` rend-il une unite ? (un summon a
        # toujours un parent ; une instance PRE-PLACEE de Kell — cas campagne — n'en aurait pas.)
        return parent_of(state, self.owner_id) is not None

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        if state.effects is None:
            return None                            # pas d'EffectsState -> pose impossible
        ectx = ExecutionContext(state=state, rng=state.rng)
        listen_up_maggots_tree().execute(entities_from_state(state, self.owner_id), ectx)
        placed = any(p.get("placed") for n, p in ectx.emitted if n == "AddEffect")
        par = parent_of(state, self.owner_id)
        return {"ability": "ListenUpMaggots", "unit": self.owner_id,
                "parent": par.id if par is not None else None, "placed": bool(placed)}
