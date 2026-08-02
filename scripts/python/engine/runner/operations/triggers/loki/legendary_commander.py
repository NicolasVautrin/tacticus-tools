"""`IdunBattle.Entities.Effects.Loki.LegendaryCommander_ExtraHitsEffect` (effet 0x573 = 1395, pose
sur `custoTrajann` par son passif) -- son TARGET-TRIGGER, c'est-a-dire l'ECRIVAIN du << first
attack >>. #419-r1-tr9-r4-r1-r2-r1.

## Ce qui manquait

La contribution de coups (`entities/effects/loki/hits.py::LegendaryCommanderExtraHitsEffect`) est
gatee par `!IsInPersistentDataList(...)`. SANS cet ecrivain, la liste resterait vide a jamais et le
bonus s'appliquerait a CHAQUE attaque d'ability, la ou l'i2 dit << their FIRST attack that is not a
normal attack >> : regression PERMISSIVE et silencieuse, exactement la forme de #436 (un effet au
registre sans son cycle).

## RE native (decompile ghidra, build `rnca9r7q6c`)

`IdunBattle.Entities.Effects.Loki.LegendaryCommander_ExtraHitsEffect$$CreateTargetTrigger` :

    On(0xa = AttackDamageAttack, ownerNeedsToBeAlive: 1)
      & IsValidAttack( Effect@DSLSelectors+0x38 )

`...$$CreateTargetTriggerBehaviour(effect, abilityState, abilityEntities)` :

    AddToPersistentDataList( <AbilityOrEffect de l'effet>,
                             unit  = EffectSource( Get(effect) ),      # custoTrajann
                             key   = EntityId( Owner@0x30 ),           # l'ENNEMI marque
                             value = EntityId( Caster@0x48 ) )         # l'ATTAQUANT

`IsValidAttack` est LE MEME predicat que celui du canal COUPS (meme methode native, appelee des deux
endroits) -- d'ou l'appel a `LegendaryCommanderExtraHitsEffect.is_valid_attack` ci-dessous : un seul
foyer, jamais deux transcriptions du meme arbre.

`On(0xa)` est le 2e event de cloture de `IdunBattle.Operations.FinishAttackOperation$$Execute`, emis
APRES `On(9)` et SEULEMENT si `currentAttack@+0x2c` est pose -- c'est-a-dire si l'attaque a traverse
`AttackDamageOperation$$Execute` (famille ATTACK). Cote port c'est exactement le drapeau
`is_attack_damage_op` de `damage_ops/ability.py`, qui conditionne deja l'emission. La consequence est
FIDELE et importante : le marquage a lieu APRES le calcul des coups, donc l'attaque qui MARQUE
beneficie elle-meme du bonus, et seules les SUIVANTES sont exclues.

## Frontiere DSL/imperatif (#149)

Le behaviour est un noeud `DSLBehaviors.AddToPersistentDataList` -> porte comme un ARBRE (la feuille
`AddToPersistentDataList` de `runner/abilities/behaviours/persistent_data.py`, deja ecrite pour
`MyWillBeDone`) ; le predicat du trigger est COLLAPSE imperativement dans `matches`, meme doctrine
que `ChronometronExtraDamageRemove` / `InspiredToGreatnessOverrideLevelRemove`.

## Ce que ce module NE porte PAS (residus nommes)

* `$$GetMarkCasterBehaviour` (corps IDENTIQUE a `CreateTargetTriggerBehaviour`) et
  `$$IsCasterMarked` (le pendant lecteur) : xrefs = metadata IL2CPP seule, AUCUN appelant. Doublons
  morts -- le couple vivant est `CreateTargetTrigger`/`CreateTargetTriggerBehaviour`.
* `$$GetClearAllMarkedAttackersBehaviour` : idem, sans appelant.
* `$$RevertInternal` = `ExecuteBehaviour(ClearPersistentData(<AbilityOrEffect>, EffectSource(
  Get(effect)), EntityId(Target@0x60)))`. `LegendaryCommanderAbility$$CreateBehaviour` pose 1395
  SANS duree (`AddEffect(0x573, .., Owner, Owner, <turns VIDE>)`), donc aucun vecteur de retrait
  n'est atteignable dans les montages portes : le clear n'a pas de site d'appel a mirrorer.
"""
from __future__ import annotations

from typing import Optional

from ....state import State
from ....components import OwnerComponent, PositionComponent
from ....damage_model import build_hits_board
from ....abilities.behaviours.persistent_data import AddToPersistentDataList
from .....entities.effects.loki.hits import (LEGENDARY_COMMANDER_EXTRA_HITS,
                                             legendary_commander_marked_key)
from .....entities.selectors import Caster
from .....dsl.effects import ExecutionContext
from .....dsl.event_trigger_type import EventTriggerType
from ..base import EffectTrigger, TriggerEvent


def _owner_ctx(state: State, owner_id: int, ev: TriggerEvent) -> Optional[dict]:
    """Contexte d'evaluation d'`IsValidAttack` pour le porteur `owner_id`, monte depuis le FOYER
    UNIQUE du board de coups (`build_hits_board`) -- aucune table re-derivee ici."""
    att, tgt = ev.actor_id, ev.target_id
    if att is None or tgt is None:
        return None
    ap = state.get_entity(att)
    tp = state.get_entity(tgt)
    if ap is None or tp is None:
        return None
    apc = ap.get_component(PositionComponent)
    tpc = tp.get_component(PositionComponent)
    if apc is None or tpc is None:
        return None
    board, _auras, _tgt_eff = build_hits_board(state, int(att), int(tgt),
                                               (apc.col, apc.row), (tpc.col, tpc.row),
                                               is_melee=None)
    oe = state.get_entity(int(owner_id))
    opc = oe.get_component(PositionComponent) if oe is not None else None
    ooc = oe.get_component(OwnerComponent) if oe is not None else None
    if opc is None or ooc is None:
        return None
    return {**board,
            "owner_id": int(owner_id), "owner_pos": (opc.col, opc.row), "owner_team": ooc.team,
            # `!IsNormalAttack(CurrentAbility@0x88)` : la nature du VECTEUR, threadee par la facade
            # d'attaque (meme donnee que celle passee a `attack_hits_with_modifiers`).
            # `None` = non threadee -> le port ne CONCLUT PAS (`is_valid_attack` lit le defaut
            # `True`, donc referme le gate) : jamais un << pas normale >> invente.
            "is_normal_attack": (True if ev.is_normal_attack is None else bool(ev.is_normal_attack)),
            # `TriggeringAbilityIsNormalAttack` = `IsNormalAttack(TriggeringAbility@0x90)`.
            "trigger_ability_type": ev.triggering_effect}


class LegendaryCommanderExtraHitsMarkCaster(EffectTrigger):
    """`LegendaryCommander_ExtraHitsEffect$$CreateTargetTrigger` = `On(0xa = AttackDamageAttack) &
    IsValidAttack(Effect@0x38)` -> `$$CreateTargetTriggerBehaviour` = `AddToPersistentDataList(
    <AbilityOrEffect>, EffectSource(Get(effect)), EntityId(Owner@0x30), EntityId(Caster@0x48))`.

    OBSERVABLE : la PREMIERE attaque d'ability d'un allie de Trajann contre un ennemi couvert par
    l'aura gagne `nrOfHits` coups ; les suivantes du MEME allie contre le MEME ennemi n'en gagnent
    plus, tandis qu'un AUTRE allie (valeur differente dans la liste) les gagne encore."""
    effect_type = LEGENDARY_COMMANDER_EXTRA_HITS
    event_id = EventTriggerType.AttackDamageAttack             # 0xa = 10

    def _instance(self, state: State):
        """L'instance 1395 portee par `owner_id` (pour lire son `EffectSource`)."""
        eff = getattr(state, "effects", None)
        if eff is None:
            return None
        for e in eff.by_unit.get(int(self.owner_id), []):
            if not e.consumed and e.effect_type == LEGENDARY_COMMANDER_EXTRA_HITS:
                return e
        return None

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        inst = self._instance(state)
        if inst is None:
            return False
        ctx = _owner_ctx(state, int(self.owner_id), ev)
        if ctx is None:
            return False
        return bool(inst.is_valid_attack(ctx))

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        inst = self._instance(state)
        if inst is None:
            return None
        # `unit = EffectSource(Get(effect))` -- le sac vit sur le POSEUR (Trajann), pas sur l'ennemi.
        src = inst.source if inst.source is not None else int(self.owner_id)
        ectx = ExecutionContext(state=state, rng=state.rng)
        # La feuille resout son selecteur d'unite sur les `entities` : on lui donne un contexte dont
        # le CASTER est la source de l'effet, exactement ce que designe `EffectSource(Get(effect))`.
        from ....abilities.behaviours import entities_from_state
        # `key = EntityId(Owner@0x30)` = l'ENNEMI marque (la cible de l'effet ; ici la cible de
        # l'attaque, puisque `get_OwnerIsTarget` vient de tenir) ; `value = EntityId(Caster@0x48)` =
        # l'ATTAQUANT. La feuille recompose la cle composite `(ability_or_effect, data_key)` du port,
        # soit exactement `legendary_commander_marked_key(ev.target_id)` -- meme foyer que le LECTEUR.
        _data_key = legendary_commander_marked_key(int(ev.target_id))[1]
        AddToPersistentDataList(
            LEGENDARY_COMMANDER_EXTRA_HITS, Caster(), _data_key, int(ev.actor_id)).execute(
                entities_from_state(state, int(src), int(src)), ectx)
        added = [p for n, p in ectx.emitted if n == "AddToPersistentDataList"]
        if not added:
            return None
        return {"effect": "LegendaryCommander_ExtraHits", "owner": int(self.owner_id),
                "source": int(src), "marked": int(ev.target_id), "attacker": int(ev.actor_id)}
