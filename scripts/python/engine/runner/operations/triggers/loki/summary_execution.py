"""`SummaryExecution` (passif d'`astraYarrick` << Yarrick >>, `TriggeredAbilityType` 1033) -- #955,
face TRIGGER. La face AURA (les deux `ADynamicStatModifierEffect`) vit dans
`entities/effects/loki/summary_execution.py`, qui porte le detail de la RE des effets.

i2 : « ... The first time a friendly unit would flee due to Battle Fatigue, it is executed instead
and all other friendly units with the trait ignore it and gain an additional +146 Damage. »

================================================================================================
RE (decompile ghidra, build `rnca9r7q6c`) -- recensement par le bloc `methodPointers`
================================================================================================
| classe | slots | corps PROPRES | faces DEDUPLIQUEES |
|---|---|---|---|
| `...Active.Loki.SummaryExecutionAbility` | 3 | **2** | `.ctor` (corps vide, ICF) |
| `...Active.Loki.SummaryExecutionAddBaseEffectAbility` | 3 | **1** | `CreateTrigger` (58 refs), `.ctor` |

## `SummaryExecutionAbility$$CreateTrigger`

      NOT HasEffect(Owner@<DSLSelectors+0x30>, 0x407 = EffectType.SummaryExecution_Effect,
                    onlyActive = false, targetType = 6)
    & On(0x33 = EventTriggerType.PreUnitFled, ownerNeedsToBeAlive = true)
    & AreFriends(Owner@+0x30, Actor@<DSLSelectors+0x40>, 0, anyEntity = false)
    & TriggeringAbilityIs( 0x401 = TriggeredAbilityType.BattleFatigue )

Le litteral du dernier conjoint est lu AUX OCTETS (`BA 01 04 00 00` = `mov edx, 0x401` a
`SummaryExecutionAbility$$CreateTrigger+0x11c`) : le decompile ne montre qu'un `local_28` non
initialise passe a `AbilityOrEffect$$op_Implicit`.

Le PREMIER conjoint est le verrou « the FIRST time » : la PRESENCE de l'effet 1031 sur Yarrick
suffit a fermer le trigger, et le behaviour le pose. Aucun compteur, aucun flag dedie.
`ownerNeedsToBeAlive = true` est le 2e argument litteral d'`On`.

## `SummaryExecutionAbility$$CreateBehaviour`

      AddDynamicStatModifierEffectToOwner( 0x407 = SummaryExecution_Effect,
                                           statType = 0 = StatType.Attack,
                                           turns = null, isHidden = false )
    & Kill( Owner@+0x30, Actor@+0x40, KillUnitBehaviourOptions$$ForDirectKill() )

L'ordre est celui du decompile : `op_BitwiseAnd(<AddDyn>, <Kill>)`, donc l'effet est pose AVANT le
`Kill`. Il compte : la victime est un allie porteur de `BattleFatigue`, donc une CIBLE du selecteur
d'aura -- la poser d'abord lui accorde le buff avant qu'elle ne meure, exactement comme le natif.

## `SummaryExecutionAddBaseEffectAbility`

    CreateTrigger   = <DSLTriggers+0x30>    # On(0x21 = AbilityInit) & <YesTrigger> & get_OwnerIsActor
    CreateBehaviour = AddDynamicStatModifierEffectToOwner( 0x413 = SummaryExecution_BaseEffect,
                                                          statType = 0, null, false )

=> registre `ABILITY_INIT_OWNER_EFFECTS`, JAMAIS `ABILITY_TRIGGERS` (meme arbitrage que #948/#952).

================================================================================================
CE QUE CETTE TRANCHE A DU AJOUTER EN AMONT, ET POURQUOI
================================================================================================
`EventTriggerType.PreUnitFled` (0x33) n'avait **AUCUN emetteur** dans tout `engine/**` : le mirror
du port de `IdunBattle.Operations.FleeOperation$$Execute` (`runner/operations/behaviour.py`)
commencait a `RemoveUnit`, alors que le natif ouvre sur

    IOperationProcessor.<slot 81 = EvaluateAbilities>(unit, unit, unit, 0x33, triggeringAbilityOrEffect)
    if (UnitExtensions.IsDead(unit)) return;

Sans ces DEUX gestes, ce passif n'aurait jamais pu se poser -- et le « executed **instead** » de
l'i2 n'aurait pas eu de mecanisme : c'est le `return` sur `IsDead` qui ANNULE la fuite, pas le
passif. Les deux sont desormais portes (`move_death.pre_unit_fled_triggers` + la garde dans
`FleeOperation.execute`), et le canal `triggering_ability` est seede par l'unique appelant porte,
`BattleFatigueAbility.execute_behaviour`.

RESIDUS NOMMES
* `HasEffect(..., targetType = 6)` : le 4e argument (`EffectTargetType`) n'a pas de contrepartie
  portee -- `EffectsState.has_effect` ne distingue pas les cibles d'effet. Sans consequence ici
  (l'effet 1031 est pose sur le porteur, donc present sous n'importe quelle lecture).
* `onlyActive = false` : le port teste la presence, pas l'activite -- c'est exactement ce que
  `false` demande.
* `#955-r3` -- `SummaryExecutionEffect$$ApplyInternal` pose `IgnoreBattleFatigue` sur CHAQUE cible
  du selecteur, et le natif le RE-JOUE quand les cibles changent (`UpdateEffectTargets`). Le driver
  d'aura du port (`runner/operations/aura_stat_mods.py`) n'a pas d'etage `ApplyInternal` par-cible :
  la pose est donc faite ICI, une fois, au moment de la materialisation de 1031. Un allie qui
  ACQUERRAIT `BattleFatigue` apres coup recevrait le stat-mod (le driver re-evalue) mais PAS
  l'immunite. Aucun montage porte ne produit ce regime (le trait est statique).
"""
from __future__ import annotations

from typing import Optional

from .....dsl.effects import ExecutionContext
from .....dsl.event_trigger_type import EventTriggerType
from .....entities.effect_type import EffectType
from .....entities.effects.loki.summary_execution import (IGNORE_BATTLE_FATIGUE,
                                                          summary_execution_target_selector)
from .....entities.selectors.accessors import Actor, Owner
from .....entities.stats import StatType
from .....entities.triggered_ability_type import TriggeredAbilityType
from ....abilities.behaviours.context import entities_from_state
from ....abilities.behaviours.effects import AddDynamicStatModifierEffect
from ....abilities.behaviours.lifecycle import Kill
from ....components import OwnerComponent, UnitComponent
from ....state import State
from ..base import TriggeredAbility, TriggerEvent

ABILITY_ID = "SummaryExecution"
_ON_PRE_UNIT_FLED = int(EventTriggerType.PreUnitFled)                 # `On(0x33, ownerAlive = true)`
#: 1er conjoint ET effet pose par le behaviour -- le MEME type, c'est ce qui fait le verrou one-shot.
SUMMARY_EXECUTION_EFFECT = int(EffectType.SummaryExecution_Effect)    # 0x407 = 1031
#: 4e conjoint : `TriggeringAbilityIs(0x401)` -- litteral lu AUX OCTETS (cf. en-tete).
BATTLE_FATIGUE = int(TriggeredAbilityType.BattleFatigue)              # 0x401 = 1025
#: `statType` litteral du `AddDynamicStatModifierEffectToOwner`.
_STAT_ATTACK = int(StatType.ATTACK)                                   # 0


def summary_execution_behaviour_tree() -> AddDynamicStatModifierEffect:
    """1er terme de `SummaryExecutionAbility$$CreateBehaviour` :
    `AddDynamicStatModifierEffectToOwner(0x407, statType = 0, turns = null, isHidden = false)` =
    le MEME appel que `AddDynamicStatModifierEffect` avec `Owner@+0x30` dans les DEUX slots
    (source `+0x58` et cibles `+0x60`). `duration_rounds = None` = pas d'override de duree, donc
    `DefaultAmountOfRounds(1031)` -- mirror du `turns = null` natif."""
    return AddDynamicStatModifierEffect(Owner(), Owner(), SUMMARY_EXECUTION_EFFECT, _STAT_ATTACK,
                                        name=EffectType.SummaryExecution_Effect.name,
                                        duration_rounds=None)


def summary_execution_kill_tree() -> Kill:
    """2e terme : `Kill(Owner@+0x30, Actor@+0x40, ForDirectKill())` -- le porteur est le TUEUR
    impute, la victime est l'ACTEUR de l'evenement (l'unite qui allait fuir)."""
    return Kill(Owner(), Actor())


def _immunisable_targets(state: State, owner_id: int) -> list:
    """Les cibles du selecteur d'aura, evaluees contre l'etat courant -- le MEME foyer que le driver
    (`SummaryExecutionEffect.aura_stat_modification_targets`). Sert de TRACE au retour du behaviour,
    pas de decision : c'est le driver qui pose."""
    entities = entities_from_state(state, int(owner_id))
    out: list = []
    for u in (summary_execution_target_selector().evaluate(entities) or []):
        uid = u.get("id") if isinstance(u, dict) else None
        if uid is not None:
            out.append(int(uid))
    return out


class SummaryExecutionAbility(TriggeredAbility):
    """`SummaryExecutionAbility` -- la PREMIERE fois qu'un allie de Yarrick va fuir a cause de
    `BattleFatigue`, Yarrick l'EXECUTE (`Kill`) au lieu de la laisser fuir, et gagne l'effet 1031
    qui accorde `+extraDmg_2` (et `IgnoreBattleFatigue`) a tous ses allies porteurs du trait."""
    event_id = _ON_PRE_UNIT_FLED
    TRIGGERED_ABILITY_ID = int(TriggeredAbilityType.SummaryExecution)     # 0x409 = 1033

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        fleeing = ev.actor_id                       # `EvaluateAbilities(unit, unit, unit, 0x33, ...)`
        if fleeing is None or fleeing == self.owner_id:
            return False
        owner, actor = state.get_entity(self.owner_id), state.get_entity(fleeing)
        if owner is None or actor is None:
            return False
        ouc = owner.get_component(UnitComponent)    # `On(..., ownerNeedsToBeAlive = true)`
        if ouc is not None and not ouc.alive:
            return False
        # `NOT HasEffect(Owner@+0x30, 0x407, onlyActive = false, targetType = 6)` -- le VERROU
        # one-shot : la presence de l'effet que le behaviour pose ferme le trigger pour la bataille.
        if state.effects is not None and state.effects.has_effect(
                self.owner_id, effect_type=SUMMARY_EXECUTION_EFFECT):
            return False
        oo, ao = owner.get_component(OwnerComponent), actor.get_component(OwnerComponent)
        if oo is None or ao is None or oo.team != ao.team:    # AreFriends(Owner@+0x30, Actor@+0x40)
            return False
        # `TriggeringAbilityIs(0x401 = BattleFatigue)` -- le canal est SEEDE sur ce vecteur (l'unique
        # appelant de `FleeOperation.execute` est le behaviour de `BattleFatigue` lui-meme). Absent
        # -> le gate FERME : le natif compare a une valeur, il ne devine pas.
        return ev.triggering_ability is not None and int(ev.triggering_ability) == BATTLE_FATIGUE

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        fleeing = ev.actor_id
        ectx = ExecutionContext(state=state, rng=state.rng)
        # `AbilityEntities` du trigger : `Owner`/`Caster` = Yarrick, `Actor` = la fuyarde. Le noeud
        # `Kill` resout `Actor@+0x40`, d'ou `actor_id`.
        entities = entities_from_state(state, self.owner_id, fleeing, actor_id=fleeing)
        # ORDRE NATIF : `op_BitwiseAnd(<AddDynamicStatModifierEffectToOwner>, <Kill>)` -- l'effet
        # d'abord, l'execution ensuite (la victime est elle-meme une cible du selecteur d'aura).
        summary_execution_behaviour_tree().execute(entities, ectx)
        placed = [p for n, p in ectx.emitted if n == "AddDynamicStatModifierEffect"]
        # Le driver d'aura (`RefreshEffectsOperation` / `UpdateEffectTargets`) n'est reveille par le
        # port qu'au SEED, au MOUVEMENT et au SPAWN : l'effet vient d'APPARAITRE, il faut donc le
        # reveiller ici, comme le natif le fait dans la foulee de `AddEffectOperation`.
        #
        # ⚠ IL POSE AUSSI LE SOUS-EFFET, ET C'EST LUI LE FOYER (#955-r3). Ce site jouait
        # `SummaryExecutionEffect$$ApplyInternal` LUI-MEME, une fois, ce qui laissait sans immunite
        # toute cible entrant DANS LE SELECTEUR plus tard -- un summon `BattleFatigue` apparu apres
        # l'execution recevait le stat-mod (le driver re-evalue depuis `spawn.py`) mais pas
        # l'immunite. Le driver joue desormais l'`ApplyInternal` PAR CIBLE, a chacun de ses reveils,
        # via `SummaryExecutionEffect.aura_sub_effects_on_apply` -- exactement comme
        # `ApplyEffectsForTargets` le fait cote natif.
        immunised: list = []
        if any(p.get("placed") for p in placed):
            from ...aura_stat_mods import refresh_aura_stat_modifiers
            refresh_aura_stat_modifiers(state)
            # Trace : les cibles du selecteur qui portent effectivement l'immunite apres le reveil.
            immunised = [uid for uid in _immunisable_targets(state, self.owner_id)
                         if state.effects is not None and state.effects.has_effect(
                             uid, effect_type=IGNORE_BATTLE_FATIGUE)]
        summary_execution_kill_tree().execute(entities, ectx)
        killed = [p for n, p in ectx.emitted if n == "Kill"]
        return {"passive": ABILITY_ID, "owner": int(self.owner_id), "fleeing": int(fleeing),
                "effect_placed": bool(any(p.get("placed") for p in placed)),
                "immunised": immunised,
                "killed": (killed[0].get("killed") if killed else [])}
