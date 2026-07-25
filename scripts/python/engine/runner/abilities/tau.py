"""Abilities actives TAU (namespace natif `IdunBattleLogic.Entities.Abilities.Active.Loki.*`).

Contenu :
- `HeavyRailRifle` (1160, `tauBroadside` -- Tson'ji, MachineOfWar) : ability MoW **2-PHASES** dont le
  behaviour de CAST est une PURE POSE D'EFFETS (aucune attaque, aucun spawn, aucune stat touchee) --
  patron « pose d'effet(s) seule » du lot #90-B (cf. `docs/rl/case-90-mow-effect-posers.md`). Le cast
  ARME la phase 1 ; le degat vient de la phase 2 (`Abilities.Triggered.Loki.HeavyRailRifle_AttackAbility`,
  porte par l'effet `HeavyRailRifle_PendingAttack`) -- HORS de ce port (cf. residus du case doc).
- `TwinSmartMissileSystem` (1161, MEME porteur `tauBroadside`) : patron « ATTAQUE DSL filtree par un
  ETAT + entretien de cet etat » (groupe B du case doc) -- l'attaque ne porte QUE sur les ennemis deja
  MARQUES (`Markerlight` 1122), et le cast (re)pose/rafraichit ce marquage sur sa cible.
"""
from __future__ import annotations

from typing import Optional, TYPE_CHECKING

from .base import ActiveAbility, convert_rounds_to_turns
from .behaviours import (AddEffect, AttackWithAttackDamage, ChangeEffectTurns, entities_from_state)
from ...dsl.effects import ExecutionContext
from ...entities.active_ability_type import ActiveAbilityType
from ...entities.behaviours import op_and, If as IfBehaviour
from ...entities.effect_type import EffectType
from ...entities.selectors import AllUnits, Caster, Enemies, EntitiesWithAnyEffect, Target
from ...entities.triggers import HasEffect

if TYPE_CHECKING:
    from ..state import State

HEAVY_RAIL_RIFLE_PENDING_ATTACK = int(EffectType.HeavyRailRifle_PendingAttack)   # 0x535 = 1333
HEAVY_RAIL_RIFLE_PENDING_TARGET = int(EffectType.HeavyRailRifle_PendingTarget)   # 0x536 = 1334
MARKERLIGHT = int(EffectType.Markerlight)                                        # 0x462 = 1122


def heavy_rail_rifle_tree():
    """Arbre de `IdunBattleLogic.Entities.Abilities.Active.Loki.HeavyRailRifleAbility$$ExecuteBehaviour` -- MIRROR 1:1 du DECOMPILE :

        Execute(   AddEffect(0x536=1334 HeavyRailRifle_PendingTarget, AbilityStateReference,
                             source=caster@0x160, targets=target@0x178, options=ZERO)
                 & AddEffect(0x535=1333 HeavyRailRifle_PendingAttack, AbilityStateReference,
                             source=caster@0x160, targets=caster@0x160,  options=ZERO) )

    DEUX `DSLFactory.AddEffect` combines par `AbilityBehaviour.op_BitwiseAnd`, passes a
    `AActiveAbility.Execute` (PAS `ExecuteAtomic`). AUCUN autre noeud : ni attaque, ni `ChangeStat`,
    ni `Spawn` -- le cast ne fait que MARQUER (la cible) et ARMER (la MoW).

    Les DEUX options-structs sont ZERO-initialisees (`local_178..uStack_160 = 0`) : pas de
    `TurnsFromRounds` -> duree = `DefaultAmountOfRounds` de l'effet. 1333/1334 sont ABSENTS de la table
    `idun.Idun.Source.Shared.Battle.StaticBattleRules.StaticBattleRules.Effect$$DefaultAmountOfRounds` -> Nullable null -> `remaining = 0` = PERMANENT (l'effet est consomme par la phase 2,
    pas expire par un timer). CONFIRME LIVE : les deux effets sortent a `remaining 0, level 1`."""
    return op_and(
        AddEffect(HEAVY_RAIL_RIFLE_PENDING_TARGET, EffectType.HeavyRailRifle_PendingTarget.name,
                  Target(), duration_rounds=None),
        AddEffect(HEAVY_RAIL_RIFLE_PENDING_ATTACK, EffectType.HeavyRailRifle_PendingAttack.name,
                  Caster(), duration_rounds=None))


class HeavyRailRifleAbility(ActiveAbility):
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.HeavyRailRifleAbility$$ExecuteBehaviour` (id 1160, `tauBroadside` Broadside -- Tau,
    MachineOfWar). Cast UNIT-TARGET (`abilityTargets` kind="unit").

    RE (ghidra gqfc5mff6c) :
    - `IdunBattleLogic.Entities.Abilities.Active.Loki.HeavyRailRifleAbility$$ExecuteBehaviour` : `Execute( AddEffect(0x536, absRef, caster@0x160, target@0x178,
      opts=0) & AddEffect(0x535, absRef, caster@0x160, caster@0x160, opts=0) )` -- cf.
      `heavy_rail_rifle_tree`.
    - `.IdunBattleLogic.Entities.Abilities.Active.Loki.HeavyRailRifleAbility$$.ctor` : `AActiveAbility.ctor(..., TargetingOptions unit-target)`.
    - PHASE 2 (NON PORTEE) : `IdunBattleLogic.Entities.Abilities.Triggered.Loki.HeavyRailRifle_AttackAbility`
      (`IdunBattleLogic.Entities.Abilities.Triggered.Loki.HeavyRailRifle_AttackAbility$$GetFinalUnitDamageAmount`) -- l'attaque differee portee par `HeavyRailRifle_PendingAttack`
      sur la MoW, qui frappe l'unite marquee `HeavyRailRifle_PendingTarget`. Le degat (minDmg/maxDmg,
      profil Piercing, nrOfHits=2, `dmgPctReduction`/`extraDmgPct`) appartient a CETTE phase, pas au cast.

    OBSERVABLE DU CAST (mesure live, runner MoW C1_02, caster 53, cible 49) :
        49    : + HeavyRailRifle_PendingTarget (1334, remaining 0, level 1)
        mow53 : + HeavyRailRifle_PendingAttack (1333, remaining 0, level 1)

    Flags de tour : defauts base (1160 absent des tables d'override `NO_END_TURN_ABILITY_TYPES` /
    `NO_ABILITY_USED_FLAG_ABILITY_TYPES`) -> l'ability termine le tour + pose ActiveAbilityUsed."""
    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.HeavyRailRifle)   # 1160
    ABILITY_ID = "HeavyRailRifle"

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        entities = entities_from_state(state, caster_id, target_id)
        ectx = ExecutionContext(state=state, rng=state.rng)
        heavy_rail_rifle_tree().execute(entities, ectx)
        posed = [{"target": p["target"], "effect": p["effect_type"]}
                 for n, p in ectx.emitted if n == "AddEffect"]
        return {"posed": posed, "dsl": True}


# ============ TwinSmartMissileSystem (tauBroadside, MACHINE OF WAR, actif 1161) ============
#
# `IdunBattleLogic.Entities.Abilities.Active.Loki.TwinSmartMissileSystemAbility$$ExecuteBehaviour`
# (MIRROR du DECOMPILE) :
#
#   targets = EntitiesWithAnyEffect( Enemies(caster@0x160, @0x80 = AllUnits, 3), 0x462 = Markerlight )
#             (== `IdunBattleLogic.Entities.Abilities.Active.Loki.TwinSmartMissileSystemAbility$$GetAttackTargets`,
#              fonction NOMMEE dont le corps est REPRIS INLINE par ExecuteBehaviour)
#   attack  = AttackWithAbilityDamage( caster@0x160, targets,
#                                      MinMaxDamage(this, entities),           # minDmg/maxDmg[level]
#                                      Direct(Nullable(GetDamageProfile()))=Blast,
#                                      ConfigConst(0x2f)=nrOfHits=3,
#                                      AbilityOrEffect(this+0x10 = 0x489 = 1161) )
#   turns   = TurnsFromRounds(2)
#   refresh = If( HasEffect(target@0x178, 0x462, minLevel 0, source-flag 6),
#                 ChangeEffectTurns(target@0x178, 0x462, turns, ChangeType 0 = Add),
#                 AddEffect(0x462, AbilityStateReference, source=caster@0x160, target@0x178, turns) )
#   AActiveAbility.ExecuteAtomic( attack op_BitwiseAnd refresh, entities, 0x2a )
#
# NOTES DE FIDELITE :
#  - `ChangeType` = `IdunBattle.Entities.Enum.ChangeType` : **0 = Add**, 1 = Set (`IdunBattle.Core.Services.BattleQuery$$GetAmount`
#    lu au decompile). Le call-site passe 0 -> la duree est AJOUTEE a la duree restante (pas un SET).
#  - `TurnsFromRounds(2)` est evalue UNE fois et sert AUX DEUX branches (meme noeud `uVar12`).
#  - l'attaque route la factory `IdunBattleLogic.Entities.DSLFactory$$AttackWithAbilityDamage`
#    -> `AbilityDamageOperation.ExecuteHits` (1 tirage/coup, pas de crit) == Stormcaller/EntropyCannons
#    -> `native_factory="ability"` cote port (classification par XREF, jamais au juge).
#  - `ExecuteAtomic(..., 0x2a)` = groupe atomique de presentation (meme flag que JakhalStimms) : aucun
#    effet sur l'etat porte (les Operations sont deja appliquees en sequence).

TWIN_SMART_MISSILE_SYSTEM_ID = "TwinSmartMissileSystem"


def twin_smart_missile_system_attack_targets() -> EntitiesWithAnyEffect:
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.TwinSmartMissileSystemAbility$$GetAttackTargets`
    (MIRROR) = `EntitiesWithAnyEffect(Enemies(caster@0x160, @0x80), 0x462 Markerlight)`.

    `@0x80` = le selecteur PARTAGE `AllAliveMachinesSelector` pose par
    `IdunBattleLogic.Entities.DSLFactory$$InitializeShared` = `AllUnits` (VIVANTS) cote port -- meme source
    que `Enemies(Owner@0x148, @0x80, 3)` de Waaagh/Stormcaller. AUCUN rayon : l'ability frappe TOUT ennemi
    marque du plateau."""
    return EntitiesWithAnyEffect(Enemies(AllUnits()), [MARKERLIGHT])


def twin_smart_missile_system_tree(state: "State"):
    """Arbre de `IdunBattleLogic.Entities.Abilities.Active.Loki.TwinSmartMissileSystemAbility$$ExecuteBehaviour`
    (MIRROR 1:1, cf. le bloc de commentaire ci-dessus) :

        op_BitwiseAnd( AttackWithAbilityDamage(<ennemis marques>),
                       If(HasEffect(cible, Markerlight), ChangeEffectTurns(+2 rounds),
                                                         AddEffect(Markerlight, 2 rounds)) )

    `TurnsFromRounds(2)` est CALCULE ICI (`convert_rounds_to_turns`, mirror
    `IdunBattle.Core.Services.BattleQuery$$ConvertRoundsToTurns`) parce que les deux consommateurs en ont
    besoin sous des formes differentes : `AddEffect` prend une duree DEJA en tours (`duration_turns`),
    `ChangeEffectTurns` prend le MONTANT a ajouter -- c'est le MEME scalaire natif."""
    turns = convert_rounds_to_turns(state, 2)             # noeud `TurnsFromRounds(2)`, evalue une fois
    attack = AttackWithAttackDamage(twin_smart_missile_system_attack_targets(),
                                    TWIN_SMART_MISSILE_SYSTEM_ID, "Blast", is_melee=False, multi=True,
                                    native_factory="ability",
                                    ability_type=int(ActiveAbilityType.TwinSmartMissileSystem))
    refresh = IfBehaviour(
        HasEffect(Target(), MARKERLIGHT),
        ChangeEffectTurns(Target(), MARKERLIGHT, turns, change_type=0),     # ChangeType.Add
        AddEffect(MARKERLIGHT, EffectType.Markerlight.name, Target(), duration_turns=turns))
    return op_and(attack, refresh)


class TwinSmartMissileSystemAbility(ActiveAbility):
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.TwinSmartMissileSystemAbility$$ExecuteBehaviour`
    (id 1161, `tauBroadside` Broadside -- Tau, MachineOfWar). Cast UNIT-TARGET.

    Kit gameconfig 1161 : `damageProfile=Blast`, `nrOfHits=3`, `minDmg`/`maxDmg`[level] (rarity-affected),
    `attackRangeType=Ranged`, `initialCooldownTurns=0`.

    OBSERVABLE : (1) 3 coups Blast famille ABILITY sur CHAQUE ennemi porteur de `Markerlight` (1122) --
    ensemble VIDE tant que personne n'est marque, donc le 1er cast d'un runner frais ne fait AUCUN degat ;
    (2) marquage de la cible : pose `Markerlight` (duree = `ConvertRoundsToTurns(2)`) si absente, sinon
    AJOUT de cette meme duree a la duree restante.

    Flags de tour : defauts base (1161 absent des tables d'override) -> termine le tour + ActiveAbilityUsed."""
    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.TwinSmartMissileSystem)   # 1161
    ABILITY_ID = TWIN_SMART_MISSILE_SYSTEM_ID

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        if target_id is None:
            return None
        ectx = ExecutionContext(state=state, rng=state.rng)
        twin_smart_missile_system_tree(state).execute(
            entities_from_state(state, caster_id, target_id), ectx)
        attacks = [{"target": p.get("target"), "total": p.get("total")}
                   for n, p in ectx.emitted if n == "AttackWithAttackDamage"]
        marked = [{"target": p.get("target"), "effect": p.get("effect_type")}
                  for n, p in ectx.emitted if n == "AddEffect"]
        refreshed = [{"owner": p.get("owner"), "remaining": p.get("remaining")}
                     for n, p in ectx.emitted if n == "ChangeEffectTurns"]
        return {"ability": TWIN_SMART_MISSILE_SYSTEM_ID, "caster": caster_id, "target": target_id,
                "attacks": attacks, "marked": marked, "refreshed": refreshed, "dsl": True}
