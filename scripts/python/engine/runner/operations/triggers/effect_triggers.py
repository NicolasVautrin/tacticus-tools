"""Effet-triggers du namespace natif `IdunBattleLogic.Entities.Effects.*` — effets porteurs de leur
propre trigger (`IdunBattle.Operations.EvaluateTriggerOperation$$EvaluateEffectTrigger). 1 classe par
`Triggered()` natif (symbole cité) :
- `Overwatch_AutoAttackEffect` — auto-attaque after-move (`RangedAutoAttackEffect$$CreateTargetTrigger`).
- les TROIS `Triggered()` de `RangedAutoAttackEffect$$CreateHandleTriggerAbilitiesInternal`, qui
  pilotent l'etat `EffectComponent.IsActive @+0x5c` de l'instance 1009 : activation au tour adverse,
  desactivation au tour du porteur, desactivation des que le porteur attaque (« un seul tir par
  activation », case-127 §8).
- `ContaminatedEffect` — tile-effet posant le sous-effet -X% armure sur l'occupant.
(Le DISPATCH itère ces classes via `EFFECT_TRIGGERS` dans `dispatch.py`.)"""
from __future__ import annotations

from typing import Optional

from ...state import State
from ...components import OwnerComponent, StatsComponent, UnitComponent, UnitFlagsComponent
from ....entities.stats import StatType
from ....entities.effect_type import EffectType
from ....dsl.event_trigger_type import EventTriggerType
from ..damage import AttackDamageOperation
from .base import EffectTrigger, TileEffectTrigger, _unit_trait_names, _in_attack_range

# --- Contaminated (tile-effect, RE #132/#128) : enter-tile + tick posent le sous-effet -X% armure --------
CONTAMINATED_TILE = int(EffectType.Contaminated)        # 1244 — effet de TUILE (posé par attaque Toxic, OnToxicDamage).
CONTAMINATED_UNIT = int(EffectType.Contaminated_Unit)   # 1245 — sous-effet -X% FixedArmor posé sur l'unité.
# #158 : ex-`CONTAMINATED_IMMUNE_TRAIT = 2027` retiré. #224 : la liste de traits elle-même a migré vers
# la CLASSE d'effet (`ContaminatedEffect.entity_is_immune_to_effect`) — un seul nœud natif, une seule
# porte offline (cf. `_is_immune_to_contaminated` plus bas).
# Magnitude Contaminated_Unit (#132, RE re-expert 2026-07-14) : `ContaminatedStatModifierEffect.GetDynamicStat
# ModificationAmount IdunBattle.Entities.Effects.Loki.ContaminatedStatModifierEffect$$GetDynamicStatModificationAmount` = `-BattleQuery.GetEffectConfig(EffectType=6)` ; `BattleQuery.GetEffectConfig
# IdunBattle.Core.Services.BattleQuery$$GetEffectConfig` lit `BattleConfiguration.Effect[+0x28]` = **`ContaminatedArmorReductionPct`** (=30). => le sous-effet
# reduit le FixedArmor cible de -30 %. Source = section `Effect` de la BC (seed-bc.json), lue ICI (PAS un hardcode ;
# defaut 30 = miroir de la valeur BC connue, comme `_DMG_CFG.get('TrenchReductionPercentage', -50)` en prediction).
import json as _json_cfg
from .... import weights as _weights_cfg
from ...abilities.base import convert_rounds_to_turns
from ..effects import AddEffectOperation
from ..effects import entity_is_immune_to_effect
from ....entities.effects.magnitude import ability_var as _ability_var
from ..heal import HealUnitOperation
_EFF_CFG: dict = (_json_cfg.loads(_weights_cfg.DEFAULT_BC.read_text(encoding="utf-8")).get("Effect", {})
                  if _weights_cfg.DEFAULT_BC.exists() else {})
CONTAMINATED_ARMOR_REDUCTION_PCT: int = int(_EFF_CFG.get("ContaminatedArmorReductionPct", 30))

# --- Overwatch (effet-trigger after-move) ---------------------------------------------------------
OVERWATCH_AUTO_ATTACK = int(EffectType.Overwatch_AutoAttack)   # 1009 — effectType de l'effet porteur du trigger
#   (ATTENTION #158 : 1009 = EffectType.Overwatch_AutoAttack ICI, PAS UnitTrait.Resilient=1009 — contexte = effet)
OVERWATCH_TARGET_IMMUNE = int(EffectType.Infiltrate)  # 1048 — mover immunisé (Overwatch_AutoAttackEffect.AdditionalTriggers : NOT)
OVERWATCH_SOURCE_DISABLE = int(EffectType.Pinned)     # 1065 — overwatch désactivé sur l'overwatcher (AdditionalActivateTrigger : NOT)
# 1302 = `EffectType.IgnoreUsedAbilityInOverwatch` (0x516). ⚠ QUALIFICATION D'ENUM (case-127) : 1302 est
# AUSSI `TriggeredAbilityType.VoltagheistField` — c'est CE second sens qu'on lit dans
# `IdunBattle.Entities.Effects.Loki.VoltagheistField_ExtraHitEffect$$.ctor` (`AbilityOrEffect(0x516)` =
# l'ability SOURCE de l'effet, dont l'EffectType est 1381). Ici le contexte est un `IdunBattleLogic.Entities.DSLTriggers$$HasEffect`
# -> le 1302 est bien un EffectType (meme famille que 0x429=Pinned / 0x418=Infiltrate juste au-dessus).
OVERWATCH_IGNORE_ABILITY_USED = int(EffectType.IgnoreUsedAbilityInOverwatch)   # 1302 — branche OR du gate


def _is_immune_to_contaminated(state: State, unit_id: int) -> bool:
    """`IdunBattle.Entities.Effects.Loki.ContaminatedEffect$$EntityIsImmuneToEffect` — DÉLÉGUÉ au canal
    DÉCLARATIF depuis #224 : la liste de traits vit sur la classe d'effet (`ContaminatedEffect`,
    `entities/effects/loki/status.py`), plus EN DUR ici. Le nœud natif est UNIQUE (un seul virtuel
    d'effet) ⇒ une seule porte offline : `entity_is_immune_to_effect` (mirror
    `IdunBattle.Core.Services.BattleQuery$$IsUnitImmuneTo`), la même que consulte le gate de
    `IdunBattle.Operations.AddEffectOperation$$Execute`. La 3e branche (`base` = `HasTrait(Immune) &&
    CanBeImmuneTo`) est désormais portée elle aussi."""
    return entity_is_immune_to_effect(state, unit_id, CONTAMINATED_TILE,
                                      name=EffectType.Contaminated.name)


def _ranged_auto_attack_is_active(state: State, owner_id: int) -> bool:
    """Condition d'**ACTIVATION** de l'effet auto-attaque (`Overwatch_AutoAttack` 1009) — mirror du 1er
    `Triggered()` de l'`ArraySet` rendu par
    `IdunBattle.Entities.Effects.RangedAutoAttackEffect$$CreateHandleTriggerAbilitiesInternal` :

        On(TurnStart_EffectActivation = 0x12)
          & NOT IsTurnOf(owner@0x148)                                              # df@0xa0
          & (   HasEffect(owner@0x148, IgnoreUsedAbilityInOverwatch = 0x516)
              | DoesNotHaveFlag(owner@0x148, UnitFlag.ActiveAbilityUsed = 2) )
          & AdditionalActivateTrigger()                                            # vtable +0x738
        -> ActivateEffect(effect@0x150)

    et, pour `Overwatch_AutoAttackEffect`,
    `IdunBattle.Entities.Effects.Loki.Overwatch_AutoAttackEffect$$AdditionalActivateTrigger`
    = `NOT HasEffect(owner@0x148, Pinned = 0x429)`.

    Le NIVEAU natif de ce gate n'est PAS le trigger de tir (`CreateTargetTrigger`) : c'est l'etat
    `EffectComponent.IsActive @+0x5c` de l'instance d'effet, ecrit par `ActivateEffect`/`DeactivateEffect`
    et RELU par `IdunBattle.Operations.EvaluateTriggerOperation$$EvaluateEffectTriggerTargets` avant
    d'evaluer le trigger de cible.

    Cette fonction est utilisee AUX DEUX NIVEAUX, et ce n'est pas une redondance :
      * comme condition du trigger d'ACTIVATION (`RangedAutoAttackActivateOnTurnStart` -> ecrit le flag) ;
      * REPLIEE dans le `matches` du TIR — exactement comme le port repliait deja
        `AdditionalActivateTrigger` (Pinned) avant #127. Le repli reste indispensable : un replay-diff
        SEEDE un etat mi-tour et dispatche directement l'after-move, sans jamais passer par un
        `StartTurnOperation` (donc sans `On(0x12)`) ; sans lui, le seul flag rendrait le port permissif
        sur ce regime, qui est celui de tous les tests de #127.
    Le repli est observationnellement equivalent au flag sur les vecteurs portes :

      * `DoesNotHaveFlag(owner, ActiveAbilityUsed)` : le flag 2 n'est POSE que pendant le tour de l'owner
        (`IdunBattle.Operations.ActiveAbilityOperation$$AddFlagsAfterAbilityExecution`) et n'est PURGE
        qu'au debut du tour suivant de l'owner (`RemoveTurnFlags` de
        `IdunBattle.Operations.StartTurnOperation$$Execute`) — il est donc CONSTANT sur toute la fenetre
        pendant laquelle un ennemi peut bouger. Lire le flag au tir == le lire au `On(0x12)`.
      * `NOT IsTurnOf(owner)` : redondant avec le 2e `Triggered()` de la meme ArraySet
        (`On(0x12,1) & IsTurnOf(owner) -> DeactivateEffect`) ; evalue au tir il rend le meme verdict
        (un move d'ennemi survenant PENDANT le tour de l'overwatcher — deplacement force — ne doit pas
        declencher l'overwatch, l'effet etant desactive depuis le debut de ce tour).

    Le 3e `Triggered()` de la meme ArraySet (`On(AttackDamageAttack=10, 1) & OwnerIsActor ->
    DeactivateEffect`) = « l'overwatch est CONSOMME des que son porteur attaque » : il n'est PAS foldable
    (il depend d'un EVENEMENT survenu PENDANT la fenetre, pas d'une condition constante) -> il est porte
    en ECRITURE sur le flag `EffectComponent.IsActive @+0x5c` (`BaseEffect.active`), cf.
    `RangedAutoAttackDeactivateOnAttack` plus bas."""
    if state.current_player_id is not None:                  # NOT IsTurnOf(owner@0x148)  (df@0xa0)
        ow = state.get_entity(owner_id)
        oc = ow.get_component(OwnerComponent) if ow is not None else None
        if oc is not None and oc.player is not None and int(oc.player) == int(state.current_player_id):
            return False
    if state.effects is not None and state.effects.has_effect(
            owner_id, effect_type=OVERWATCH_SOURCE_DISABLE):  # AdditionalActivateTrigger : NOT Pinned
        return False
    # ( HasEffect(owner, 1302) | DoesNotHaveFlag(owner, 2) ) — la 1re branche NEUTRALISE la 2e.
    if state.effects is not None and state.effects.has_effect(
            owner_id, effect_type=OVERWATCH_IGNORE_ABILITY_USED):
        return True
    ow = state.get_entity(owner_id)
    fl = ow.get_component(UnitFlagsComponent) if ow is not None else None
    #   `HasFlagAbilityTrigger$$ShouldTrigger` = `UnitFlagsComponent.Has(flag)` (XOR 1 quand `expected`
    #   est faux, ce qui est le cas de `DSLTriggers$$DoesNotHaveFlag`). Composant absent = aucun flag.
    return fl is None or not fl.has(UnitFlagsComponent.ACTIVE_ABILITY_USED)


def _ranged_auto_attack_instances(state: State, owner_id: int) -> list:
    """Les instances d'effet `Overwatch_AutoAttack` (1009) NON consommees portees par `owner_id` —
    c'est-a-dire les entites-effet dont les 3 `Triggered()` de
    `IdunBattle.Entities.Effects.RangedAutoAttackEffect$$CreateHandleTriggerAbilitiesInternal` ecrivent
    le `EffectComponent.IsActive @+0x5c` (`e.active`). Liste (et non instance unique) parce que le natif
    raisonne PAR ENTITE-EFFET ; en pratique `AddEffectOperation` no-ope sur un meme-type deja present,
    donc il y en a 0 ou 1. [] si l'etat n'a pas d'`EffectsState`."""
    if state.effects is None:
        return []
    return [e for e in state.effects.by_unit.get(int(owner_id), [])
            if not e.consumed and e.effect_type == OVERWATCH_AUTO_ATTACK]


def _ranged_auto_attack_flag_is_set(state: State, owner_id: int) -> bool:
    """Le flag `EffectComponent.IsActive @+0x5c` de l'instance 1009 du porteur — mirror EXACT du gate
    que `IdunBattle.Operations.EvaluateTriggerOperation$$EvaluateEffectTriggerTargets` applique AVANT
    d'evaluer le trigger de CIBLE (`if (*(char *)(effectEntity + 0x5c) == 0) -> pas d'evaluation`), et
    qu'il RELIT par cible dans sa boucle de drain (une desactivation en cours de drain stoppe les cibles
    suivantes).

    Aucune instance trouvee -> True : degradation PERMISSIVE (on ne fabrique pas un refus). Le cas se
    presente quand l'etat n'a pas d'`EffectsState` ; si l'effet est reellement absent, c'est
    `collect_effect_triggers` qui n'aura instancie aucun trigger."""
    insts = _ranged_auto_attack_instances(state, owner_id)
    return (not insts) or any(e.active for e in insts)


def _set_ranged_auto_attack_active(state: State, owner_id: int, value: bool) -> bool:
    """Ecrit `EffectComponent.IsActive @+0x5c` sur l'instance 1009 du porteur — mirror de
    `IdunBattle.Operations.RefreshEffectsOperation$$ActivateEffect` (`+0x5c = 1`) /
    `IdunBattle.Operations.RefreshEffectsOperation$$DeactivateEffect` (`+0x5c = 0`, precede du gate
    « deja inactif -> no-op »). Renvoie True si un flag a CHANGE (diagnostic ; permet aux behaviours
    de ne rien emettre quand l'ecriture est un no-op, comme le natif)."""
    changed = False
    for e in _ranged_auto_attack_instances(state, owner_id):
        if bool(e.active) != bool(value):
            e.active = bool(value)
            changed = True
    return changed


class OverwatchAutoAttack(EffectTrigger):
    """`Overwatch_AutoAttackEffect` (base `RangedAutoAttackEffect`) — auto-attaque after-move.
    Trigger de TIR `IdunBattle.Entities.Effects.RangedAutoAttackEffect$$CreateTargetTrigger =
    `On(4) & NOT AreFriends(overwatcher,mover) & IsInAttackRange(overwatcher,mover,3) & AdditionalTriggers`
    (`IdunBattle.Entities.Effects.Loki.Overwatch_AutoAttackEffect$$AdditionalTriggers` = `NOT mover a 0x418`).
    Behaviour `IdunBattle.Entities.Effects.Loki.Overwatch_AutoAttackEffect$$GetAttackBehaviour =
    `UseActiveAbility(NormalAttack)` sur le mover ⇒ **attaque NORMALE** de l'overwatcher (chemin
    `AttackDamageOperation.execute`, déjà bit-exact).

    ⚠ Le tir n'est evalue par
    `IdunBattle.Operations.EvaluateTriggerOperation$$EvaluateEffectTriggerTargets` que si l'instance
    d'effet est ACTIVE (`EffectComponent.IsActive @+0x5c`). Cet etat est pilote par les 3 `Triggered()` de
    `IdunBattle.Entities.Effects.RangedAutoAttackEffect$$CreateHandleTriggerAbilitiesInternal`, portes
    en trois classes soeurs (`RangedAutoAttack{ActivateOnTurnStart,DeactivateOnTurnStart,
    DeactivateOnAttack}`) ; sa condition d'ACTIVATION est de plus repliee ici par
    `_ranged_auto_attack_is_active` (#127) — c'est elle qui porte `DoesNotHaveFlag(owner,
    ActiveAbilityUsed)` et `NOT HasEffect(owner, Pinned)` sur les etats SEEDES mi-tour."""
    event_id = EventTriggerType.UnitAfterMove
    effect_type = OVERWATCH_AUTO_ATTACK

    def matches(self, state: State, ev: "TriggerEvent") -> bool:
        # Gate `EffectComponent.IsActive @+0x5c` de l'instance — mirror EXACT du premier test de
        # `EvaluateEffectTriggerTargets`, AVANT toute evaluation du trigger de cible. C'est lui qui
        # porte le 3e `Triggered()` (« un seul tir par activation ») : le tir de l'overwatcher a
        # desactive SON instance, donc le mover SUIVANT ne declenche plus rien.
        if not _ranged_auto_attack_flag_is_set(state, self.owner_id):
            return False
        mover = ev.actor_id                                   # l'unité qui vient de bouger
        ow = state.get_entity(self.owner_id)
        mv = state.get_entity(mover)
        if ow is None or mv is None:
            return False
        # TARGET-VALIDITY = leg de re-validation du PUMP FIFO (#201). Le mover (cible de l'overwatch)
        # doit etre VIVANT. Natif : les pending triggered-abilities after-move (les 2 overwatch) sont
        # draines UN PAR UN par `IdunBattle.Messages.InputMessageProcessor$$ProcessPendingTriggeredAbilities` (snapshot+Clear de la file
        # #5) ; chaque item = un `IdunBattle.Messages.InputMessageProcessor$$RunPhase(PhaseType.ProcessPendingTriggeredAbilities /*0xf*/)` qui appelle `IdunBattle.Messages.InputMessageProcessor$$VerifyDeaths` juste
        # apres son callback, AVANT l'item suivant. Donc si le 1er overwatch TUE le mover, VerifyDeaths le
        # retire et le 2e overwatch ne trouve plus de cible : `IdunBattle.Entities.Effects.Loki.Overwatch_AutoAttackEffect$$GetAttackBehaviour` =
        # `UseActiveAbility(NormalAttack)` sur une unite morte = fizzle (les selecteurs DSL de cible operent
        # sur AllAliveMachines, #202). Le port COLLAPSE ce pump dans `evaluate_trigger_operation` (registre
        # snapshot + drain par-item re-evaluant `matches` contre l'etat courant + morts appliquees INLINE via
        # `_fire_death_if_killed` = alive=False) : ce gate est la re-validation de cible du drain. Sans lui,
        # le 2e overwatch tirait sur le CADAVRE (double-fire = divergence #201 prouvee deterministe + live).
        mvu = mv.get_component(UnitComponent)
        if mvu is not None and not mvu.alive:
            return False
        owc = ow.get_component(OwnerComponent)
        mvc = mv.get_component(OwnerComponent)
        if owc is None or mvc is None or owc.team == mvc.team:   # NOT AreFriends ⇒ ennemi
            return False
        if not _in_attack_range(state, self.owner_id, mover):    # IsInAttackRange(...,3)
            return False
        if state.effects is not None and state.effects.has_effect(   # AdditionalTriggers : NOT 0x418
                mover, effect_type=OVERWATCH_TARGET_IMMUNE):
            return False
        # #127 — gate d'ACTIVATION de l'effet (repli de `CreateHandleTriggerAbilitiesInternal` :
        # NOT IsTurnOf(owner) & (HasEffect(owner,1302) | NOT HasFlag(owner, ActiveAbilityUsed)) &
        # AdditionalActivateTrigger = NOT HasEffect(owner, Pinned)). Le `NOT Pinned` etait deja porte
        # ICI (seule branche du gate qui l'etait) ; il a rejoint ses conjoints dans le helper.
        if not _ranged_auto_attack_is_active(state, self.owner_id):
            return False
        return True

    def execute_behaviour(self, state: State, ev: "TriggerEvent") -> Optional[dict]:
        if state.rng is None:                                    # l'attaque consomme le RNG (spread/rolls)
            return None
        # `is_overwatch=True` : le natif resout ce coup par `UseActiveAbility(NormalAttack)` (donc une
        # attaque NORMALE), mais le predicat `IsOverwatchAttack` le distingue -- consomme par la
        # disjonction `IsRangedAttack | IsOverwatchAttack` du bonus de percage Hailstrike (case-117 ph.2).
        # `triggering_ability` (#114) : le natif resout ce coup par `UseActiveAbility(NormalAttack)`
        # DEPUIS l'effet 1009 -> `StaticBattleRules$$GetDamageSourceAbility(currentAbility = attaque
        # REGULIERE, triggeringAbility = 1009)` attribue le degat (et donc la RAISON DE MORT gravee sur
        # la victime) a l'EFFET 1009, pas a l'attaque normale. C'est ce que teste
        # `AReactivateOverwatchEffect$$LegitDeathReasons` (`HasDeathReason(dying, Ability, 0x3f1)`).
        res = AttackDamageOperation.execute(state, self.owner_id, ev.actor_id, 20,  # attaque NORMALE
                                            is_overwatch=True,
                                            triggering_ability=OVERWATCH_AUTO_ATTACK)
        return {"effect": "Overwatch_AutoAttack", "attacker": self.owner_id,
                "target": ev.actor_id, "result": res}


# --- Les 3 `Triggered()` de `CreateHandleTriggerAbilitiesInternal` : l'ETAT ACTIF de l'instance -----
#
# `IdunBattle.Entities.Effects.RangedAutoAttackEffect$$CreateHandleTriggerAbilitiesInternal` rend un
# `ArraySet` de TROIS `Triggered()` qui ne font qu'une chose : ecrire `EffectComponent.IsActive @+0x5c`
# de l'instance (`effect@0x150`). Lus 1:1 au decompile :
#
#   (1) On(0x12 = TurnStart_EffectActivation)                        # BaseEffect$$On -> IdunBattleLogic.Entities.DSLTriggers$$On(.., false)
#         & NOT IsTurnOf(owner@0x148)                                # df@0xa0
#         & ( HasEffect(owner, IgnoreUsedAbilityInOverwatch = 0x516)
#             | DoesNotHaveFlag(owner, ActiveAbilityUsed = 2) )
#         & AdditionalActivateTrigger()                              # vtable +0x738 = NOT Pinned
#       -> ActivateEffect(effect@0x150)
#   (2) On(0x12, 1) & IsTurnOf(owner@0x148)   -> DeactivateEffect(effect@0x150)
#   (3) On(10 = AttackDamageAttack, 1) & OwnerIsActor -> DeactivateEffect(effect@0x150)
#
# Chacun = UNE classe ci-dessous (1 `Triggered()` natif = 1 artefact offline), toutes enregistrees dans
# `EFFECT_TRIGGERS[1009]` a cote du trigger de TIR (`OverwatchAutoAttack`) — l'`ArraySet` natif porte
# bien N triggers pour un meme effet. Elles sont evaluees par
# `IdunBattle.Operations.EvaluateTriggerOperation$$EvaluateEffectTriggerEffectAbilities`, qui — contrairement
# a `EvaluateEffectTriggerTargets` — n'applique AUCUN gate `IsActive` : c'est ce qui permet a (1) de
# RE-ACTIVER une instance desactivee (sinon l'overwatch s'eteindrait definitivement). Le port fait pareil :
# `collect_effect_triggers` ne filtre PAS sur `e.active`.
#
# ⚠ CONJOINT NON QUALIFIE : le 2e argument de `IdunBattleLogic.Entities.DSLTriggers$$On(ctx, evt, bool)` selectionne un trigger
# pre-construit du contexte (`ctx@+0x128` si false, `ctx@+0x98` si true, cf.
# `IdunBattleLogic.Entities.DSLTriggers$$InitializeShared`). `ctx@+0x128` est la classe qu'un `is`-test de
# `IdunBattle.Entities.Effects.BaseEffect$$NeedsRefreshing` traite comme trigger TRIVIAL (= toujours vrai) ;
# `ctx@+0x98` (present sur (2) et (3), absent de (1)) n'est PAS qualifie — il est VRAI dans l'execution
# reelle (ground truth live : le tir desactive bien l'overwatch), et le port ne le modelise pas.
class RangedAutoAttackActivateOnTurnStart(EffectTrigger):
    """`Triggered()` (1) — ACTIVE l'instance au debut d'un tour qui n'est PAS celui du porteur.
    `matches` = la conjonction lue plus haut (`_ranged_auto_attack_is_active`) ; `execute_behaviour` =
    `ActivateEffect(effect@0x150)` = `IdunBattle.Operations.RefreshEffectsOperation$$ActivateEffect`
    (`+0x5c = 1`). C'est le CONTREPOIDS de (2)/(3) : sans lui un overwatch consomme ne reviendrait
    jamais."""
    event_id = EventTriggerType.TurnStart_EffectActivation
    effect_type = OVERWATCH_AUTO_ATTACK

    def matches(self, state: State, ev: "TriggerEvent") -> bool:
        return _ranged_auto_attack_is_active(state, self.owner_id)

    def execute_behaviour(self, state: State, ev: "TriggerEvent") -> Optional[dict]:
        if not _set_ranged_auto_attack_active(state, self.owner_id, True):
            return None                                  # deja actif -> aucune ecriture (no-op)
        return {"effect": "Overwatch_AutoAttack", "owner": self.owner_id, "activated": True}


class RangedAutoAttackDeactivateOnTurnStart(EffectTrigger):
    """`Triggered()` (2) — DESACTIVE l'instance au debut du tour DE SON PORTEUR (`IsTurnOf(owner@0x148)`,
    df@0xa0). Observationnellement redondant avec le conjoint `NOT IsTurnOf(owner)` replie dans le
    `matches` du tir, mais porte quand meme : 1 `Triggered()` natif = 1 classe, et c'est LUI qui explique
    pourquoi 1009 est absent de `decisionView` pendant le tour de son porteur."""
    event_id = EventTriggerType.TurnStart_EffectActivation
    effect_type = OVERWATCH_AUTO_ATTACK

    def matches(self, state: State, ev: "TriggerEvent") -> bool:
        if state.current_player_id is None:              # etat sans tour courant -> conjoint inerte
            return False
        ow = state.get_entity(self.owner_id)
        oc = ow.get_component(OwnerComponent) if ow is not None else None
        return (oc is not None and oc.player is not None
                and int(oc.player) == int(state.current_player_id))

    def execute_behaviour(self, state: State, ev: "TriggerEvent") -> Optional[dict]:
        if not _set_ranged_auto_attack_active(state, self.owner_id, False):
            return None                                  # gate natif « deja inactif -> no-op »
        return {"effect": "Overwatch_AutoAttack", "owner": self.owner_id, "deactivated": "turn_of_owner"}


class RangedAutoAttackDeactivateOnAttack(EffectTrigger):
    """`Triggered()` (3) — **UN SEUL TIR PAR ACTIVATION** : `On(AttackDamageAttack = 10, 1) &
    OwnerIsActor -> DeactivateEffect(effect@0x150)`. Des que le PORTEUR de l'effet est l'ACTEUR d'une
    attaque-a-degats, son overwatch est consomme.

    `OwnerIsActor` = `IdunBattleLogic.Entities.DSLTriggers$$get_OwnerIsActor`, qui construit son trigger
    avec le couple (owner@0x148, actor@0x158) — donc « l'acteur de l'evenement est le porteur ».

    GROUND TRUTH LIVE (case-127 §6.1) : au 1er deplacement ennemi entrant dans la portee, les DEUX
    overwatchers tirent (`hp 400000 -> 385014`) et 1009 disparait des DEUX ; le deplacement SUIVANT ne
    declenche RIEN (`delta 0`). Chaque overwatcher desactive SA propre instance via SON propre tir (le
    tir est une attaque normale -> `AttackDamageOperation`), d'ou la disparition symetrique."""
    event_id = EventTriggerType.AttackDamageAttack
    effect_type = OVERWATCH_AUTO_ATTACK

    def matches(self, state: State, ev: "TriggerEvent") -> bool:
        return int(ev.actor_id) == int(self.owner_id)    # OwnerIsActor (owner@0x148 == actor@0x158)

    def execute_behaviour(self, state: State, ev: "TriggerEvent") -> Optional[dict]:
        if not _set_ranged_auto_attack_active(state, self.owner_id, False):
            return None                                  # gate natif « deja inactif -> no-op »
        return {"effect": "Overwatch_AutoAttack", "owner": self.owner_id, "deactivated": "owner_attacked"}


BLOOD_CHALICE_HEAL_ON_ATTACK = int(EffectType.BloodChalice_HealOnAttack)   # 0x558 = 1368


class BloodChaliceHealOnMeleeAttack(EffectTrigger):
    """`IdunBattle.Entities.Effects.Loki.BloodChalice_HealOnAttackEffect` (1368, pose par
    `1175 BloodChalice`) -- le volet SOIN. #576

    `$$CreateTargetTrigger` -- MIRROR du decompile :

        On(0x9 = EventTriggerType.Attack, 1)
          op_BitwiseAnd get_OwnerIsCaster
          op_BitwiseAnd IsMeleeAttack

    `$$CreateTargetTriggerBehaviour` -- MIRROR du decompile :

        amount = ConfigVar(0x20 = hpToHeal, <abilityState du poseur>, config@+0x60)
        healer = DSLSelectors.EffectSource(effects@DSLSelectors+0x38)
        cible  = Owner@DSLSelectors+0x30
        return DSLBehaviors.Heal(healer, cible, amount,
                                 IdunBattle.Entities.Behaviours.HealBehaviourOptions$$**ForHeal**)

    ⚠ FABRIQUE D'OPTIONS **LUE**, pas devinee : `ForHeal` -> `(scope 0, removeEffects 1)`. Ce n'est
    PAS `ForRegenerate` (`(1, 0)`), et les deux ne sont pas interchangeables -- `scope 1` armerait
    le cap de groupe `GetGroupUnitHealLimit` de `PredictHeal`, et `removeEffects 0` retirerait le
    disjunct `HasNegativeUnitEffect` du gate.

    ⚠ LES DEUX ENTITES DU SOIN SONT DISTINCTES, ET LES CONFONDRE FAUSSERAIT LE GATE : le SOIGNEUR
    est la SOURCE de l'effet (le Sanguinary Priest qui a lance le calice), la CIBLE est le PORTEUR
    (l'allie qui vient de frapper). C'est ce couple que
    `IdunBattle.Core.Services.AttackQuery$$EntityCanBeHealed(caster, target, scope, removeEffects)`
    consulte -- d'ou le passage par `HealUnitOperation.execute`, qui porte le gate ET `PredictHeal`,
    jamais une mutation directe de `HealthComponent` (c'est exactement le trou que #520 a trouve sur
    `HealUnitOperation` et #564 sur `ResurrectUnitOperation`, deux fois la MEME panne).
    Source non captee -> on retombe sur le porteur (`EffectSource` rendrait alors `None`, et le natif
    passerait `null` au gate) : degradation NOMMEE, jamais un soin fabrique sans soigneur.

    ⚠ `OwnerIsCaster` (couple owner@0x148 / caster@0x160) est transcrit `ev.actor_id ==
    self.owner_id` : `TriggerEvent` ne thread PAS le slot CASTER separement de l'ACTEUR. Les deux
    coincident sur une attaque ordinaire ; ils divergeraient sur une attaque emise POUR le porteur
    par l'ability d'une autre unite. Ecart NOMME, non mesure ici.

    i2 : « performing a melee attack heals this unit for {hpToHeal} Health. »"""
    event_id = EventTriggerType.Attack                       # 0x9
    effect_type = BLOOD_CHALICE_HEAL_ON_ATTACK

    def _instance(self, state: State):
        """L'entite-effet 1368 portee par `owner_id` -- porte l'`AbilityState` du POSEUR
        (`active_ability_level` / multiplier, poses par `scale_from_source=True`) et sa SOURCE."""
        if state.effects is None:
            return None
        for e in state.effects.by_unit.get(int(self.owner_id), []):
            if not e.consumed and e.effect_type == BLOOD_CHALICE_HEAL_ON_ATTACK:
                return e
        return None

    def matches(self, state: State, ev: "TriggerEvent") -> bool:
        # Gate `EffectComponent.IsActive @+0x5c` (#231, pose ici par #547-r2) -- ce trigger vient de
        # `$$CreateTargetTrigger`, donc du rail que
        # `IdunBattle.Operations.EvaluateTriggerOperation$$EvaluateEffectTriggerTargets` gate AVANT
        # d'appeler `ShouldTrigger` (slot 0x13) : sa boucle PAR CIBLE recharge l'`EffectComponent`
        # depuis l'entite-effet et n'evalue rien `if (*(char *)(<component> + 0x5c) == '\0')`.
        # C'est le gate du rail TARGETS SEUL -- `EvaluateEffectTriggerEffectAbilities`, l'autre
        # rail, n'accede JAMAIS a `+0x5c` (case-229). Sans lui, le calice soignait encore alors que
        # son effet etait DESACTIVE : ni erreur, ni crash, juste un soin de trop.
        inst = self._instance(state)
        if inst is None or not inst.active:
            return False
        if ev.ranged is None:                                # IsMeleeAttack -- tri-etat : on se tait
            return False
        return int(ev.actor_id) == int(self.owner_id) and not bool(ev.ranged)

    def execute_behaviour(self, state: State, ev: "TriggerEvent") -> Optional[dict]:
        inst = self._instance(state)
        lvl = mult = None
        healer = self.owner_id
        if inst is not None:
            lvl = (inst.active_ability_level if inst.active_ability_level is not None
                   else inst.ability_level)
            mult = inst.ability_variables_multiplier
            if inst.source is not None:                      # DSLSelectors.EffectSource
                healer = int(inst.source)
        amount = _ability_var("BloodChalice", "hpToHeal", lvl,
                              multiplier_pct=(100 if mult is None else int(mult)))
        if not amount:
            return None
        # `HealBehaviourOptions$$ForHeal` = (scope 0, removeEffects 1) -- LITTERAUX du call-site.
        healed = HealUnitOperation.execute(state, healer, int(self.owner_id), int(amount),
                                           scope=0, remove_effects=True)
        if not healed:
            return None                                      # gate refuse / deja plein : le natif n'emet rien
        return {"effect": "BloodChalice_HealOnAttack", "owner": self.owner_id,
                "healer": healer, "healed": healed}


class ContaminatedTileEffect(TileEffectTrigger):
    """`IdunBattle.Entities.Effects.Loki.ContaminatedEffect$$CreateHandleTriggerAbilitiesInternal (effet de tuile 0x4dc) — pose le
    sous-effet `Contaminated_Unit` (0x4dd, -X% FixedArmor, 1 round) sur l'unité qui ENTRE (`On(4)` &
    `AreEqual(triggeringTile, effectTile)`) ou qui OCCUPE au tick de tour (`On(0x12)`) la tuile contaminée,
    sauf si déjà présent (`!HasEffect(0x4dd)`) ou immune (trait 2027 / Mechanical IdunBattle.Entities.Effects.Loki.ContaminatedEffect$$EntityIsImmuneToEffect). Enter+tick
    partagent le behaviour (appliquer à la cible) → `event_ids=(4, 0x12)`.
    ⚠ MAGNITUDE (X%) NON RÉSOLUE (#132) → l'effet est posé avec `value=None` (PRÉSENT mais inerte-stat)."""
    effect_type = CONTAMINATED_TILE
    event_ids = (EventTriggerType.UnitAfterMove, EventTriggerType.TurnStart_EffectActivation)

    def _target_unit(self, state: State, ev: "TriggerEvent") -> Optional[int]:
        occ = self._unit_on_tile(state)
        if occ is None:
            return None
        if ev.event_id == EventTriggerType.UnitAfterMove:
            # ENTER : gate `AreEqual(triggeringTile, effectTile)` = le MOVER doit être sur MA tuile (pas un
            # occupant d'une autre tuile contaminée qui se déclencherait à chaque move ailleurs).
            return occ if occ == ev.actor_id else None
        return occ                                        # TICK : occupant courant

    def matches(self, state: State, ev: "TriggerEvent") -> bool:
        return self._target_unit(state, ev) is not None

    def execute_behaviour(self, state: State, ev: "TriggerEvent") -> Optional[dict]:
        uid = self._target_unit(state, ev)
        if uid is None or state.effects is None:
            return None
        if state.effects.has_effect(uid, effect_type=CONTAMINATED_UNIT):
            return None                                   # !HasEffect(0x4dd) : pas de re-pose
        if _is_immune_to_contaminated(state, uid):        # trait 2027 / Mechanical
            return None
        # MAGNITUDE #132 (RE IdunBattle.Entities.Effects.Loki.ContaminatedStatModifierEffect$$GetDynamicStatModificationAmount = -GetEffectConfig(6) = -ContaminatedArmorReductionPct%, cf. constante) :
        # le sous-effet reduit le FixedArmor de -30 %. Le stat-layer applique `get_stat_modification_amount` en
        # ADDITIF -> on materialise le -X% en DELTA PLAT pre-calcule = -round(FixedArmor * pct/100). Lu AVANT la
        # pose (gate has_effect -> pas de recursion). `value=None` si stats absentes = present mais stat-inerte.
        val: Optional[int] = None
        te = state.get_entity(uid)
        tsc = te.get_component(StatsComponent) if te is not None else None
        if tsc is not None and CONTAMINATED_ARMOR_REDUCTION_PCT > 0:
            armor = int(tsc.ctx.stat(StatType.FIXED_ARMOR))
            if armor > 0:
                val = -round(armor * CONTAMINATED_ARMOR_REDUCTION_PCT / 100)
        # #98 : `IdunBattle.Entities.Effects.Loki.ContaminatedEffect$$AddEffectBehavior` = `AddDynamicStatModifierEffect(sel,
        # 0x4dd, 0x10, **TurnsFromRounds(1)**)` -> la duree passe par `BattleQuery.ConvertRoundsToTurns`
        # IdunBattle.Core.Services.BattleQuery$$ConvertRoundsToTurns (le port envoyait 1 TOUR en dur, soit la moitie dans un duel a 2 joueurs).
        eff = AddEffectOperation.execute(
            state, source=self.owner_id, target=uid, effect_type=CONTAMINATED_UNIT,
            name="Contaminated_Unit", duration_override=convert_rounds_to_turns(state, 1),
            value=val)                                       # #132 : -pct% FixedArmor (BC Effect config)
        if eff is None:
            return None
        return {"tile_effect": "Contaminated", "tile": self.owner_id, "unit": uid,
                "applied": "Contaminated_Unit", "armor_delta": val, "on_event": ev.event_id}
