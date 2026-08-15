"""Abilities actives de la faction VOTANN (namespace natif `Abilities.Active.Loki.*`) -- port isole (case-220 §6.10).

Module DEDIE a la faction Leagues of Votann (comme `genestealer.py`/`deathguard.py`/`blacklegion.py` : une
classe par ability, l'arbre SPECIFIQUE vit avec sa classe). RE ghidra gqfc5mff6c (VA citees). Doc :
docs/rl/case-220/votann.md.

Contenu :
- `IronkinSteeljack` (1219, `votanMemnyr` -- Memnyr) : summon `votanSmnSteeljack` sur un hex LIBRE adjacent au
  caster (cast tile-target), `WithStatsFromConfig` level-scale, attaque a l'apparition
  (`PerformAIAttackFromCurrentPosition`). CLONE du corps `IdunBattleLogic.Entities.Abilities.Active.Loki.AberrantHypermorphAbility$$ExecuteBehaviour`
  (dedup IL2CPP -- cf. classe).
- `AugmentedAssault` (1221, `votanBeserk` -- Havyr) : 4x Eviscerate sur la cible + stat-mod NEGATIF
  FixedArmor sur CETTE cible (`AugmentedAssault_ReduceArmor` 1541, permanent).
- `GravitonRifle` (1206, `votanIronmaster` -- Vynn) : 3x Physical range-2 + `Stunned` (1162) nrOfRounds
  rounds ; l'owner-effect `GravitonRifle_ExtraPierce` (1484) ajoute +extraPierceRatio au percage de CE
  cast contre TerminatorArmour/MkXGravis/Mechanical (canal percage, cf. `entities/effects/loki/votann.py`).
- `AncestralFortune` (1207, `votanUthar` -- Uthar) : self-buff +critChance (1485) & +blockChance (1486)
  1 round, puis attaque conditionnelle 3x Plasma sur le meilleur ennemi ADJACENT.
- `MassDriverAccelerator` (1222, `votanChampion` -- Kimm, #525) : CHARGE a SPLASH -- +extraMovement
  (`MassDriverAccelerator_ExtraMovement` 1542) sur l'OWNER **et ses amis ADJACENTS**, puis charge de la
  cible, puis 1x `DirectDamage` sur elle et 1x `Physical` sur les ENNEMIS adjacents a elle.
"""
from __future__ import annotations

from fractions import Fraction
from typing import Optional, TYPE_CHECKING

import gameconfig as GC

from .base import ActiveAbility
from .targeting import (RANGE_ADJACENT, RANGE_FROM_CONFIG, RANGE_SELF, RANGE_WHOLE_BOARD,
                        RANGED_BOOL_FALSE, RANGED_BOOL_TRUE, TargetingOptions)
from .targeting_rule import TargetingRule as TR
from .behaviours.combat import AttackWithAttackDamage
from .behaviours.context import entities_from_state
from .behaviours.effects import (AddDynamicStatModifierEffect, AddEffect,
                                 AddStaticStatModifierEffect)
from .behaviours.movement import MoveUnit
from .loki import perform_ai_attack_from_current_position
from ..components import OwnerComponent, StatsComponent, UnitComponent, PositionComponent
from ...battle_query import is_adjacent
from ...entities.pathfinding.board import adjacent_neigh_by_pos, elevations_by_pos
from ...entities.ability_constant_type import AbilityConstantType
from ...entities.active_ability_type import ActiveAbilityType
from ...entities.effect_type import EffectType
from ...entities.stats import StatType, StatPart
from ...entities.behaviours import (AtomicGroup, Group, SetCache, op_and, op_add,
                                    If as IfBehaviour)
from ...entities.effects.magnitude import ability_var
from ...entities.selectors.accessors import CasterTile, FixedTiles, Owner, SelectTile, Target
from ...entities.selectors.geometry import Cache
from ...entities.selectors.tiles import Caster, tiles_unit_can_move_to_charge_target
from ...entities.selectors.units import AdjacentFriends, AdjacentUnits, Alive, Enemies, Union
from ...dsl.base import Const, _round_fix64   # `IdunBattle.DSL.AAmountFormula$$RoundFix64Result`
from ...dsl.effects import ExecutionContext, AbilityBehaviour, OperationResult
from ...entities.formulas import StatAmount, Count
from ...entities.triggers import AmountIsGreaterThanZero, IsAlive
from ...streams.group_type import GroupType
from ...utilities.tile import first_tile_by_utility
from ...utilities.utility_type import UtilityType
from ..operations.damage_utility import first_by_damage_utility
from ..operations.spawn import _spawn_config_grot

if TYPE_CHECKING:
    from ..state import State


class SpawnSteeljack(AbilityBehaviour):
    """Feuille `Spawn` de `IronkinSteeljackAbility.ExecuteBehaviour` (id 1219, `votanMemnyr`). Le corps natif
    est DEDUPLIQUE avec `IdunBattleLogic.Entities.Abilities.Active.Loki.AberrantHypermorphAbility$$ExecuteBehaviour` (RE ci-dessous : les DEUX
    classes pointent leur slot ExecuteBehaviour vers le MEME code IdunBattleLogic.Entities.Abilities.Active.Loki.AberrantHypermorphAbility$$ExecuteBehaviour -- byte-identique, seule la
    config per-instance @0x30/@0x60 differe) ; il decompile en :
        Execute( Spawn(caster@0x160, TARGET@0x178 = la TUILE ciblee par le cast (hex libre adjacent au caster),
                       unitId = GetStringConstant(config, 0) = "votanSmnSteeljack",
                       SpawnUnitOptions.WithStatsFromConfig(config 1219,
                                                            AbilityLevelAmount(Self@0x148, AbilityType(1219)))
                         .onAppearance(+0x18) = PerformAIAttackFromCurrentPosition(Target@0x178)) )
    Mirror 1:1 de `SpawnAberrant` (IdunBattleLogic.Entities.Abilities.Active.Loki.AberrantHypermorphAbility$$ExecuteBehaviour = le MEME corps) avec la config 1219. Le placement N'EST PAS un
    selecteur : la tuile EST la cible du cast (choisie par le joueur/l'IA, legalite = abilityTargets kind="tile",
    hex libre adjacent au caster via `TargetingOptions(0, statsFromClass, 1, 0x1040)` -- IdunBattleLogic.Entities.Abilities.Active.Loki.IronkinSteeljackAbility$$.ctor
    IDENTIQUE a AberrantHypermorph IdunBattleLogic.Entities.Abilities.Active.Loki.AberrantHypermorphAbility$$.ctor / MasterOfTheTutelaries IdunBattleLogic.Entities.Abilities.Active.Loki.MasterOfTheTutelariesAbility$$.ctor) -> la feuille porte `tile_id`
    resolu par la classe. Spawn delegue a `_spawn_config_grot` (WithStatsFromConfig = summonHp/summonDmg/
    summonArmor[level actif du caster] x mult, CopyOwner team+player du caster).

    ON-APPEARANCE : le natif passe `Target@0x178` (le MEME selecteur que la tuile de spawn) comme SUJET de
    `PerformAIAttackFromCurrentPosition` -- apres le spawn, `Target@0x178` resout a l'unite POSEE sur la
    tuile-cible = le summon fraichement cree (tuile libre AVANT le spawn par la legalite du cast). Outcome
    identique a AberrantHypermorph -> port = `perform_ai_attack_from_current_position(state, gid)` (pipeline
    attaque normale COMPLET, arme choisie par distance : `votanSmnSteeljack` a DEUX armes -- melee Physical
    2-hit et ranged Energy 2-hit range-2 -> attaque l'ennemi le plus proche a portee, sinon no-op fidele).
    Emet 'SpawnUnit'/'SummonOnAppearance'. Effet PUR (stop=False)."""
    __slots__ = ("tile_id",)

    def __init__(self, tile_id):
        self.tile_id = tile_id

    def execute(self, entities, ectx):
        state = ectx.state
        caster_id = (entities.caster or {}).get("id")
        if state is None or caster_id is None or self.tile_id is None:
            return OperationResult.ok()
        consts = (GC.ability("IronkinSteeljack") or {}).get("constants") or {}
        vid = consts.get("unitId")                       # votanSmnSteeljack (GetStringConstant(config, 0))
        ce = state.get_entity(caster_id)
        coc = ce.get_component(OwnerComponent) if ce is not None else None
        csc = ce.get_component(StatsComponent) if ce is not None else None
        c_ctx = csc.ctx if csc is not None else None
        if vid is None or coc is None or c_ctx is None:
            return OperationResult.ok()
        level = getattr(c_ctx, "active_ability_level", None)   # AbilityLevelAmount(Self, 1219)
        mult = int(getattr(c_ctx, "ability_variables_multiplier", 100) or 100)
        gid = _spawn_config_grot(state, vid, self.tile_id, "IronkinSteeljack", level, mult,
                                 coc.team, coc.player)
        if gid is None:
            return OperationResult.ok()
        ectx.emit("SpawnUnit", unit=gid)
        att = perform_ai_attack_from_current_position(state, gid)
        if att is not None:
            ectx.emit("SummonOnAppearance", summon=gid, target=att["target"], total=att["total"])
        return OperationResult.ok()


def ironkin_steeljack_tree(tile_id) -> SpawnSteeljack:
    """Arbre de `IdunBattleLogic.Entities.Abilities.Active.Loki.AberrantHypermorphAbility$$ExecuteBehaviour` (id 1219, `votanMemnyr` -- MIRROR 1:1 du
    DECOMPILE, corps DEDUPLIQUE avec AberrantHypermorph) :
        Execute( Spawn(caster@0x160, Target@0x178=TUILE, "votanSmnSteeljack",
                       WithStatsFromConfig(config, AbilityLevelAmount(Self@0x148, 1219))
                         .onAppearance = PerformAIAttackFromCurrentPosition(Target@0x178)) )
    UN SEUL noeud `Spawn` (plain `AActiveAbility.Execute`, PAS `ExecuteAtomic`, PAS d'AddEffect, PAS de
    op_BitwiseAnd -- le noeud top-level passe a Execute EST le Spawn seul). Count=1 (une seule tuile-cible ; le
    `2` litteral de `TestSummonAbility IdunBattleLogic.Entities.Abilities.Active.TestSummonAbility$$ExecuteBehaviour` -- une AUTRE forme de summon a `count=Nullable(2)`@options+0x40
    -- N'EST PAS present dans IdunBattleLogic.Entities.Abilities.Active.Loki.AberrantHypermorphAbility$$ExecuteBehaviour). DISTINCT de MasterOfTheTutelaries IdunBattleLogic.Entities.Abilities.Active.Loki.MasterOfTheTutelariesAbility$$ExecuteBehaviour (op_BitwiseAnd(AddEffect
    (1197), Spawn)). Port : feuille `SpawnSteeljack` (== `SpawnAberrant` avec la config 1219)."""
    return SpawnSteeljack(tile_id)


class IronkinSteeljackAbility(ActiveAbility):
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.AberrantHypermorphAbility$$ExecuteBehaviour` (id 1219, `votanMemnyr` -- Memnyr, namespace natif
    `Abilities.Active.Loki`). Cast TILE-TARGET (« Summon an Ironkin Steeljack on a free hex adjacent to Memnyr »)
    : spawn UN `votanSmnSteeljack` sur la tuile ciblee (hex libre adjacent au caster), qui attaque
    immediatement sans bouger (`PerformAIAttackFromCurrentPosition`). Pas de triggered, pas d'effet pose sur le
    caster.

    RE (ghidra gqfc5mff6c) -- l'ExecuteBehaviour est un corps GSHARED HERITE NON ATTACHE (aucun symbole
    `IronkinSteeljackAbility$$ExecuteBehaviour` ; seul le IdunBattleLogic.Entities.Abilities.Active.Loki.IronkinSteeljackAbility$$.ctor est symbolise). Pin via la table
    methodPointers : le slot ExecuteBehaviour d'IronkinSteeljack (0x1830f8110, juste apres son IdunBattleLogic.Entities.Abilities.Active.Loki.IronkinSteeljackAbility$$.ctor
    a 0x1830f8108) = **IdunBattleLogic.Entities.Abilities.Active.Loki.AberrantHypermorphAbility$$ExecuteBehaviour** = EXACTEMENT le slot ExecuteBehaviour d'AberrantHypermorph (0x1830f6fb0,
    apres son IdunBattleLogic.Entities.Abilities.Active.Loki.AberrantHypermorphAbility$$.ctor a 0x1830f6fa8). Les DEUX classes partagent donc le MEME corps IdunBattleLogic.Entities.Abilities.Active.Loki.AberrantHypermorphAbility$$ExecuteBehaviour (dedup
    IL2CPP de code byte-identique) -> IronkinSteeljack = clone exact d'AberrantHypermorph, seule la config
    per-instance differe : IdunBattleLogic.Entities.Abilities.Active.Loki.IronkinSteeljackAbility$$.ctor = `TargetingOptions(0, statsFromClass, 1, 0x1040)` + `AActiveAbility
    (…, 2, 0)` IDENTIQUE, gameconfig = `{unitId: votanSmnSteeljack}` + summonHp/summonDmg/summonArmor (memes
    variables que 1166).

    La behaviour EST l'arbre DSL `ironkin_steeljack_tree(tile_id)` (feuille `SpawnSteeljack`). La feuille
    delegue le SPAWN a l'Operation VALIDEE `_spawn_config_grot` (votanSmnSteeljack team/player du caster, stats
    summonHp/summonDmg/summonArmor[level actif] x mult) puis l'on-appearance (le summon attaque l'ennemi le plus
    proche a portee de SES armes -- melee Physical 2-hit / ranged Energy 2-hit range-2).

    `target_id` = id de TUILE (cast tile-target, abilityTargets kind="tile"). Un target_id qui n'est pas une
    tuile du board -> Spawn no-op (diag `spawned=[]`).

    Flags de tour : defauts base (1219 absent de `NO_END_TURN_ABILITY_TYPES`/`NO_ABILITY_USED_FLAG_ABILITY_TYPES`
    -> `SetsEndTurnFlags`/`SetsActiveAbilityUsedFlag` = True) -> l'ability TERMINE le tour du caster
    (`FinishUnitTurn` : le caster ne peut plus bouger ce tour = no-move-this-turn) + pose ActiveAbilityUsed. Le
    « cannot-move-this-turn » que le natif pose SUR LE SUMMON (`IdunBattle.Entities.Behaviours.SpawnUnitBehaviour$$TriggerSpawnedUnitBehaviours : flag
    0x23) est un NO-OP runner : le summon a agi a l'apparition et n'est pas rejoue ce tour dans notre modele
    (aucun consommateur offline) -- meme raisonnement qu'AberrantHypermorph."""
    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.IronkinSteeljack)  # 1219
    ABILITY_ID = "IronkinSteeljack"

    # GATE DE CIBLE (#115). `IdunBattleLogic.Entities.Abilities.Active.Loki.IronkinSteeljackAbility$$.ctor` :
    #     TargetingOptions..ctor(&opts, 0, &statsFromClass, 1, 0x1040, 0, 0, 0)
    #     AActiveAbility..ctor(this, &opts, 2, 0)
    # Overload « flags DIRECTS » (5e argument -> `options+0x28`) : le litteral EST le masque effectif
    # (c'est le `0x1040` deja cite dans la docstring de `SpawnSteeljack`, ici LU au ctor et transcrit).
    # Decomposition (`IdunBattle.Core.Services.TargetingRule`) :
    #     0x40     TargetIsTile     -> cast TILE-TARGET (domaine TILE non porte)
    #     0x1000   TargetTileIsFree -> `CanAddUnit` sur la tuile visee, NON PORTE
    # Aucune regle du domaine UNITE -> aucun refus mesurable offline ; masque pose par FIDELITE.
    # ⚠ Le ctor est BYTE-IDENTIQUE a ceux d'AberrantHypermorph et de MasterOfTheTutelaries (meme
    # famille « summon sur hex libre adjacent »).
    # PORTEE (#241) : `range = TargetingRange` statique `+0x30` = `onlyAdjacent = True` +
    # `overrideRange = 1` -> le filtre statique bascule sur `BattleQuery.AreEntitiesAdjacent`
    # (adjacence, pas distance <= N) ; `forceMeleeTarget = False`.
    TARGETING_OPTIONS = TargetingOptions(rules=TR.TargetIsTile | TR.TargetTileIsFree,
                                         range=RANGE_ADJACENT,
                                         force_melee_target=RANGED_BOOL_FALSE)

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        # #287-r14 RESOLUTION DE CIBLE -- `IdunBattle.Core.Services.TargetingQuery$$GetActualTarget`
        # via le slot 16 d'`IActiveAbility` : pour un masque `TargetIsTile`, le role `target` du
        # natif est TOUJOURS l'entite-TUILE, que l'appelant ait passe la tuile ou son occupant.
        # IDEMPOTENT (`GetMainTile(<tuile>)` rend la tuile) -> inerte quand `AbilityHandler` a
        # deja resolu, mordant sur tout appel DIRECT (tests de migration, probes).
        target_id = self.get_actual_target(state, caster_id, target_id)
        board = state.board
        tile_id = target_id if (board is not None and target_id in board.by_id) else None
        ectx = ExecutionContext(state=state, rng=state.rng)
        ironkin_steeljack_tree(tile_id).execute(entities_from_state(state, caster_id), ectx)
        spawned = [p["unit"] for n, p in ectx.emitted if n == "SpawnUnit"]
        attacks = [{"summon": p["summon"], "target": p["target"], "total": p["total"]}
                   for n, p in ectx.emitted if n == "SummonOnAppearance"]
        return {"summon": "votanSmnSteeljack", "spawned": spawned, "attacks": attacks,
                "tile": tile_id, "dsl": True}


# ---------------------------------------------------------------------------------------------------
# #113 -- AugmentedAssault (1221) / GravitonRifle (1206) / AncestralFortune (1207).
# ---------------------------------------------------------------------------------------------------

AUGMENTED_ASSAULT_REDUCE_ARMOR = int(EffectType.AugmentedAssault_ReduceArmor)   # 0x605 = 1541
GRAVITON_RIFLE_EXTRA_PIERCE = int(EffectType.GravitonRifle_ExtraPierce)        # 0x5cc = 1484
ANCESTRAL_FORTUNE_EXTRA_CRIT = int(EffectType.AncestralFortune_ExtraCritChance)   # 0x5cd = 1485
ANCESTRAL_FORTUNE_EXTRA_BLOCK = int(EffectType.AncestralFortune_ExtraBlockChance)  # 0x5ce = 1486
STUNNED = int(EffectType.Stunned)                                              # 0x48a = 1162


def augmented_assault_tree() -> object:
    """Arbre de `IdunBattleLogic.Entities.Abilities.Active.Loki.AugmentedAssaultAbility$$ExecuteBehaviour`
    (id 1221, `votanBeserk` -- Havyr), MIRROR 1:1 du DECOMPILE :

        op_BitwiseAnd(
            AttackWithAttackDamage( caster@0x160, target@0x178,
                                    MinMaxDamage(entities, 0) = RandomAmount(minDmg[lvl], maxDmg[lvl]),
                                    Nullable(GetDamageProfile(0)),
                                    GetHits(0) = GetNumberConstant(0x2f = nrOfHits),
                                    AbilityOrEffect(this+0x10 = 1221) ),
            AddDynamicStatModifierEffect( targets = target@0x178, source = self@0x148,
                                          0x605 = 1541, stat = 0x10 = 16 FixedArmor,
                                          AbilityStateReference, duree = <aucun noeud> ) )

    DEUX noeuds seulement, combines par `AbilityBehaviour.op_BitwiseAnd` (== `Seq`), passes tels quels a
    `AActiveAbility.Execute`. Le profil (`Eviscerate`) et le nb de coups (4) viennent de la config 1221
    (`constants.damageProfile` / `constants.nrOfHits`) — l'ability est `attackRangeType = Melee`.

    La cible du stat-mod EST la cible de l'attaque (`target@0x178` dans les DEUX noeuds) : le malus
    d'armure frappe l'ennemi, pas le caster (cf. `AugmentedAssaultReduceArmorEffect` pour la lecture des
    slots source/targets et du flag `isNegative`)."""
    attack = AttackWithAttackDamage(Target(), "AugmentedAssault", "Eviscerate", is_melee=True,
                                    ability_type=int(ActiveAbilityType.AugmentedAssault))
    debuff = AddDynamicStatModifierEffect(Target(), Caster(), AUGMENTED_ASSAULT_REDUCE_ARMOR,
                                          int(StatType.FIXED_ARMOR),
                                          name="AugmentedAssault_ReduceArmor",
                                          duration_rounds=None)      # aucun noeud de duree -> permanent
    return op_and(attack, debuff)


class AugmentedAssaultAbility(ActiveAbility):
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.AugmentedAssaultAbility$$ExecuteBehaviour` (id 1221,
    `votanBeserk` -- Havyr). Attaque MELEE mono-cible 4x Eviscerate + pose sur la CIBLE le stat-mod
    NEGATIF `AugmentedAssault_ReduceArmor` (FixedArmor -= armorReduction[lvl] x mult, permanent).

    Behaviour = l'arbre `augmented_assault_tree()` (mirror 1:1). Turn-flags = defauts base (1221 absent de
    `NO_END_TURN_ABILITY_TYPES`/`NO_ABILITY_USED_FLAG_ABILITY_TYPES` -> le cast TERMINE le tour).

    Face DECISION (`IdunBattle.AI.Playbook.Loki.AugmentedAssaultPlaybook$$EvaluateNonComparable` /
    `$$.ctor`) NON portee dans ce lot — signalee telle quelle, pas empilee ici."""
    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.AugmentedAssault)   # 1221
    ABILITY_ID = "AugmentedAssault"

    # GATE DE CIBLE (#115). `IdunBattleLogic.Entities.Abilities.Active.Loki.AugmentedAssaultAbility$$.ctor`
    # COPIE le PRESET STATIQUE `IdunBattle.Core.Services.TargetingOptions` statics `+0x40` (pose par
    # `IdunBattle.Core.Services.TargetingOptions$$.cctor`), puis `AActiveAbility..ctor(this, &opts, 0, 0)`.
    # Masque effectif = `preset+0x28` = statics `+0x68` -> `0x4000`.
    # Decomposition (`IdunBattle.Core.Services.TargetingRule`) :
    #     0x4000   TargetIsEnemy -> PORTE, et SEULE regle du masque (refus sur soi-meme / un allie).
    # PORTEE (#241) : preset `TargetingOptions` statique `+0x40` -> `TargetingRange` statique
    # `+0x30` = `onlyAdjacent = True` + `overrideRange = 1` -> cible ADJACENTE obligatoire.
    TARGETING_OPTIONS = TargetingOptions(rules=TR.TargetIsEnemy,
                                         range=RANGE_ADJACENT,
                                         force_melee_target=RANGED_BOOL_FALSE)

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        if target_id is None:
            return None
        ectx = ExecutionContext(state=state, rng=state.rng)
        augmented_assault_tree().execute(entities_from_state(state, caster_id, target_id), ectx)
        atk = next((p for n, p in ectx.emitted if n == "AttackWithAttackDamage"), {})
        mod = next((p for n, p in ectx.emitted if n == "AddDynamicStatModifierEffect"), {})
        return {"ability": "AugmentedAssault", "caster": caster_id, "target": target_id,
                "attack": atk.get("attack"), "total": atk.get("total"),
                "armor_debuff": {"target": mod.get("target"), "placed": mod.get("placed"),
                                 "effect_type": AUGMENTED_ASSAULT_REDUCE_ARMOR},
                "dsl": True}


def graviton_rifle_tree(rounds: int) -> object:
    """Arbre de `IdunBattleLogic.Entities.Abilities.Active.Loki.GravitonRifleAbility$$ExecuteBehaviour`
    (id 1206, `votanIronmaster` -- Vynn), MIRROR 1:1 du DECOMPILE :

        op_Addition(
            AttackWithAttackDamage( caster@0x160, target@0x178, MinMaxDamage(entities, 0),
                                    Nullable(GetDamageProfile(0)), GetHits(0),
                                    AbilityOrEffect(this+0x10 = 1206) ),
            AddEffect( 0x48a = 1162 Stunned, AbilityStateReference, target@0x178,
                       TurnsFromRounds( GetNumberConstant(config@0x60, 0x45 = 69 nrOfRounds) ) ) )

    `rounds` = la constante config lue par l'appelant (`nrOfRounds` = 1) : le noeud natif est un
    `TurnsFromRounds(<constante>)`, donc `duration_rounds` (converti par `ConvertRoundsToTurns`).
    Profil `Physical`, 3 coups, `attackRangeType = Ranged` (range 2 -> la portee est un gate de CIBLAGE,
    cote decision ; la cible arrive par le message)."""
    attack = AttackWithAttackDamage(Target(), "GravitonRifle", "Physical", is_melee=False,
                                    ability_type=int(ActiveAbilityType.GravitonRifle))
    stun = AddEffect(STUNNED, "Stunned", Target(), duration_rounds=rounds)
    return op_add(attack, stun)


class GravitonRifleAbility(ActiveAbility):
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.GravitonRifleAbility$$ExecuteBehaviour` (id 1206,
    `votanIronmaster` -- Vynn). Attaque RANGED (range 2) mono-cible 3x Physical + `Stunned` (1162,
    composite) sur la cible pour `nrOfRounds` (=1) round.

    PERCAGE CONDITIONNEL : l'owner-effect `GravitonRifle_ExtraPierce` (1484), ajoute a Vynn a la creation
    par le dict natif `GetEffectToBeAddedToOwnerForAbility`, ajoute `+extraPierceRatio[lvl]` au ratio de
    percage de CE cast quand la cible porte TerminatorArmour(1039) / MkXGravis(1013) / Mechanical(5) —
    branche par la feuille `AttackWithAttackDamage` (canal `BaseEffect$$PiercingBonusForAttack`, cf.
    `ability_pierce_effect_bonus`), PAS recable ici.

    Turn-flags = defauts base (1206 absent des deux frozensets -> le cast termine le tour)."""
    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.GravitonRifle)   # 1206
    ABILITY_ID = "GravitonRifle"

    # GATE DE CIBLE (#115). `IdunBattleLogic.Entities.Abilities.Active.Loki.GravitonRifleAbility$$.ctor`
    # COPIE le PRESET STATIQUE `IdunBattle.Core.Services.TargetingOptions` statics `+0x140` (le MEME que
    # MultiThreatEliminator, cf. necrons.py), puis `AActiveAbility..ctor(this, &opts, 2, 0)`.
    # Masque effectif = `preset+0x28` = statics `+0x168` -> `0x4002`.
    # Decomposition (`IdunBattle.Core.Services.TargetingRule`) :
    #     0x2      TargetMatchesDynamicRule -> non surcharge cote port -> defaut 0 (PERMISSIF assume)
    #     0x4000   TargetIsEnemy            -> PORTE (refus sur soi-meme / un allie)
    # NB la PORTEE (range 2) n'est PAS dans ce masque : le natif la teste hors bit, via
    # `IdunBattle.Core.Services.TargetingQuery$$GetRange` — volet NON PORTE (cf. targeting.py).
    # PORTEE (#241) : preset `TargetingOptions` statique `+0x140` -> `TargetingRange`
    # statique `+0x18` (`useRangeFromConfig` -> `GravitonRifle.constants.range` = 2) +
    # `forceMeleeTarget = True`.
    TARGETING_OPTIONS = TargetingOptions(rules=TR.TargetMatchesDynamicRule | TR.TargetIsEnemy,
                                         range=RANGE_FROM_CONFIG,
                                         force_melee_target=RANGED_BOOL_TRUE)

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        if target_id is None:
            return None
        # `GetNumberConstant(config@0x60, 0x45 = nrOfRounds)` — le natif rend 0 pour une constante absente.
        rounds = ability_var("GravitonRifle", "nrOfRounds", is_constant=True) or 0
        ectx = ExecutionContext(state=state, rng=state.rng)
        graviton_rifle_tree(int(rounds)).execute(
            entities_from_state(state, caster_id, target_id), ectx)
        atk = next((p for n, p in ectx.emitted if n == "AttackWithAttackDamage"), {})
        stun = next((p for n, p in ectx.emitted if n == "AddEffect"
                     and p.get("effect_type") == STUNNED), {})
        return {"ability": "GravitonRifle", "caster": caster_id, "target": target_id,
                "attack": atk.get("attack"), "total": atk.get("total"),
                "stunned": {"target": stun.get("target"), "placed": stun.get("placed"),
                            "rounds": int(rounds)},
                "dsl": True}


def _ancestral_fortune_attack_target(state: "State", caster_id: int) -> Optional[int]:
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.AncestralFortuneAbility$$GetAttackTarget` (le corps
    est INLINE dans l'`ExecuteBehaviour`) :

        First( SortUnitsByDamageUtility( NormalUnits( AdjacentEnemies(caster@0x160, @0x168, 1), 3 ),
                                         MinMaxDamage(entities, 1), 3 ),
               1 )

    - `AdjacentEnemies(caster, 1)` = ennemis VIVANTS ADJACENTS au caster. Substrat LU
      (#943-r4) : `DSLSelectors$$AdjacentEnemies(unit, unique, selType)` =
      `Enemies(unit, Units(AdjacentTiles(unit)) - unit, selType)`, et `AdjacentTiles` descend sur
      `IterateAdjacentTiles` -- la liste STOCKEE du `ConnectivityComponent`, puis la porte
      `|dElev| < 2`. Ce n'est PAS la couronne hex, qui la SUR-ATTEINT (4 aretes sur `C1_74`,
      38 sur `C3_14`, 0 dans l'autre sens) : d'ou les deux canaux ci-dessous.
    - `NormalUnits(sel, 3)` = `FromTrigger(Units(sel, 1, 3), <IsNormalUnit @dsl+0x180>)` : filtre les
      entites non-unites (objets/decor). Offline, `state.entities` ne contient QUE des unites de combat
      -> le filtre est un no-op DOCUMENTE (aucun objet n'y entre).
    - `MinMaxDamage(entities, 1)` = branche `useAverage != 0` de
      `IdunBattle.Entities.Abilities.AActiveAbility$$MinMaxDamage` = `Half(Sum(Direct(minDmg[lvl]),
      Direct(maxDmg[lvl])))` -> min == max == moyenne des bornes de l'ability (le noeud de degat que
      `SortUnitsByDamageUtility` branche sur son slot +0x40).
    - le TRI + le `First` sont le port PARTAGE `first_by_damage_utility`
      (`IdunBattle.Entities.Selectors.SortUnitsByDamageUtilitySelector$$Select` = argmax du composite
      Damage(35)), le meme etage que FinalJustice.

    Selecteur AI-target (kind S lourd, chevauche le playbook) -> COLLAPSE imperativement, comme
    `_finaljustice_target`, puis injecte dans l'arbre via `Target()`. None si aucun ennemi adjacent."""
    e = state.get_entity(caster_id)
    pc = e.get_component(PositionComponent) if e is not None else None
    oc = e.get_component(OwnerComponent) if e is not None else None
    sc = e.get_component(StatsComponent) if e is not None else None
    if pc is None or oc is None:
        return None
    board = getattr(state, "board", None)
    elev_by_pos = elevations_by_pos(board)
    neigh_by_pos = adjacent_neigh_by_pos(board)
    src = (pc.col, pc.row)
    cands = []
    for eid, other in state.entities.items():
        if eid == caster_id:
            continue
        ooc = other.get_component(OwnerComponent)
        opc = other.get_component(PositionComponent)
        ouc = other.get_component(UnitComponent)
        if ooc is None or opc is None or ooc.team == oc.team:      # AdjacentEnemies : team != caster
            continue
        if ouc is not None and not ouc.alive:
            continue
        # `AdjacentTiles` -> `IterateAdjacentTiles` : liste STOCKEE puis porte d'elevation.
        if is_adjacent(src, (opc.col, opc.row), elev_by_pos, neigh_by_pos):
            cands.append(eid)
    if not cands:
        return None
    ctx = sc.ctx if sc is not None else None
    lvl = int(getattr(ctx, "active_ability_level", 0) or 0) if ctx is not None else 0
    mult = int(getattr(ctx, "ability_variables_multiplier", 100) or 100) if ctx is not None else 100
    bmin = int(ability_var("AncestralFortune", "minDmg", lvl, multiplier_pct=mult) or 0)
    bmax = int(ability_var("AncestralFortune", "maxDmg", lvl, multiplier_pct=mult) or 0)
    # `IdunBattleLogic.Entities.Abilities.Active.Loki.AncestralFortuneAbility$$GetAttackTarget` passe
    # `AActiveAbility$$MinMaxDamage(state, isPrediction: true)` = `Half(Sum(Direct(minDmg), Direct(maxDmg)), 0)`
    # a `SortUnitsByDamageUtility`, dont le `$$Select` evalue la formule par le slot 1 de `IAmountFormula`
    # (= `Calculate`) -> `IdunBattle.Entities.Formulas.DivideAmount$$Calculate` ->
    # `IdunBattle.DSL.AAmountFormula$$RoundFix64Result(., 0)` = `Fix64.Round` demi-vers-le-PAIR.
    # #344 : c'etait une TRONCATURE, fausse d'exactement 1 quand `bmin + bmax` vaut 3 mod 4.
    avg = _round_fix64(Fraction(bmin + bmax, 2), 0)
    # `owner_id = caster` (#494-r1) : le selecteur natif passe la POSITION du caster a la prediction
    # PAR CIBLE -> la cle porte les feuilles positionnelles (elevation / trench).
    # #494-r1-r1 : AUCUN profil/percage n'est passe, et c'est une LECTURE. Ce call-site emploie la
    # surcharge `SortUnitsByDamageUtility(targets, damage, unitSelectionType, hits)` -- SANS noeud
    # d'ability (`+0x28` nul) -- donc le natif predit avec
    # `AbilityOrEffect(UnitExtensions$$GetNormalAttackType(owner))` : le profil et le percage sont
    # ceux de l'ARME NORMALE du caster, pas le `Plasma` de l'ability. `hits` est nul -> UN coup.
    return first_by_damage_utility(state, cands, avg, avg, owner_id=caster_id)


def ancestral_fortune_tree(attack_target: Optional[int]) -> object:
    """Arbre de `IdunBattleLogic.Entities.Abilities.Active.Loki.AncestralFortuneAbility$$ExecuteBehaviour`
    (id 1207, `votanUthar` -- Uthar), MIRROR 1:1 du DECOMPILE :

        turns  = TurnsFromRounds(1)
        crit   = If( AmountIsGreaterThanZero( StatAmount(self@0x148, 9 = CritChance,  3 = INITIAL) ),
                     AddDynamicStatModifierEffectToOwner(0x5cd = 1485, stat 9, turns) )
        block  = If( AmountIsGreaterThanZero( StatAmount(self@0x148, 7 = BlockChance, 3 = INITIAL) ),
                     AddDynamicStatModifierEffectToOwner(0x5ce = 1486, stat 7, turns) )
        tgt    = First(SortUnitsByDamageUtility(NormalUnits(AdjacentEnemies(caster,1),3),
                                                MinMaxDamage(entities,1), 3), 1)
        atk    = If( AmountIsGreaterThanZero(tgt),
                     AttackWithAttackDamage(caster@0x160, tgt, MinMaxDamage(entities,0),
                                            Nullable(GetDamageProfile(0)), GetHits(0),
                                            AbilityOrEffect(1207)) )
        clear  = ClearPersistentData( AbilityOrEffect(this+0x10 = 1207), self@0x148, <type> )
        Execute( op_BitwiseAnd( op_BitwiseAnd( op_BitwiseAnd(crit, block), clear ), atk ) )

    Les DEUX gates `StatAmount(..., INITIAL)` sont des mirrors EXACTS de
    `…AncestralFortuneAbility$$CanAddCritChance` / `$$CanAddBlockChance` (memes corps) : le buff n'est pose
    que si le caster a une valeur de BASE > 0 sur la stat correspondante.

    `attack_target` = le collapse imperatif du selecteur AI (cf. `_ancestral_fortune_attack_target`) ;
    None -> le gate `AmountIsGreaterThanZero(tgt)` est FAUX et l'attaque ne s'execute pas.

    `ClearPersistentData(1207, self)` : RESIDU DOCUMENTE — le substrat persistent-data (compteur de
    blocs/crits arme par `…AncestralFortune_CountResetAbility$$CreateTrigger` et consomme par
    `…AncestralFortune_TriggerResetAbility$$CreateTrigger` pour le `ResetActiveAbility` au 6e) N'EST PAS
    porte ; le noeud est donc un NO-OP fidele ici (rien a effacer), et le RESET de l'ability reste hors
    perimetre de ce lot.

    ================================================================================================
    ORDRE D'EXECUTION + RESIDU MESURE (regime CRIT)
    ================================================================================================
    Les buffs sont poses AVANT l'attaque (ordre de l'arbre natif) ET l'attaque du MEME cast en
    BENEFICIE. GROUND TRUTH (`probe_113_votann.py`, Uthar crit-base 10 / block-base 12 via
    `rl_duel build --crit/--block-player`) :
      * la sequence d'events natifs est g22 `AncestralFortune_ExtraCritChance`
        (`UnitStats_CritChance_Modification: 30`) PUIS g22 `_ExtraBlockChance` (+30) PUIS les 3 g26
        de degat -> les stat-mods sont appliques avant les coups ;
      * MC1_67/31337 : le natif crit **3/3** (`Attack_DidCrit` = 1,1,1) -- impossible a crit-chance 10
        (le port y tire 0/3), reproduit exactement a crit-chance **40** = 10 base + 30 buff.

    RESIDU MESURE, NON impute a ce lot : sur C1_74/777 le natif crit 1/3 la ou le port (meme rng cale,
    meme crit-chance 40) crit 2/3 -- le 3e coup a le MEME roll de degat des deux cotes (1339) mais un
    verdict de crit different. C'est UN verdict sur 6 mesures, sur le canal PARTAGE
    `IdunBattle.Core.Services.DamageCalculations$$RollCritical` (hors perimetre #113) ; le regime SANS
    buff (`fortune_gated`) est lui bit-exact sur les deux boards. Documente dans
    docs/rl/case-220/votann.md."""

    crit = IfBehaviour(
        AmountIsGreaterThanZero(StatAmount(Caster(), int(StatType.CRIT_CHANCE),
                                           variant=int(StatPart.INITIAL))),
        AddDynamicStatModifierEffect(Caster(), Caster(), ANCESTRAL_FORTUNE_EXTRA_CRIT,
                                     int(StatType.CRIT_CHANCE),
                                     name="AncestralFortune_ExtraCritChance", duration_rounds=1))
    block = IfBehaviour(
        AmountIsGreaterThanZero(StatAmount(Caster(), int(StatType.BLOCK_CHANCE),
                                           variant=int(StatPart.INITIAL))),
        AddDynamicStatModifierEffect(Caster(), Caster(), ANCESTRAL_FORTUNE_EXTRA_BLOCK,
                                     int(StatType.BLOCK_CHANCE),
                                     name="AncestralFortune_ExtraBlockChance", duration_rounds=1))
    # `AmountIsGreaterThanZero(<le selecteur de cible>)` = « le selecteur a rendu >= 1 element » ; le
    # collapse impératif est injecte dans `entities.target` -> `Count(Target())` EST ce cardinal (0 ou 1).
    atk = IfBehaviour(
        AmountIsGreaterThanZero(Count(Target())),
        AttackWithAttackDamage(Target(), "AncestralFortune", "Plasma", is_melee=True,
                               ability_type=int(ActiveAbilityType.AncestralFortune)))
    # Ordre NATIF : `((crit & block) & clear) & atk` -- les buffs AVANT l'attaque (le `clear` est le
    # no-op documente ci-dessus). GROUND TRUTH : sur MC1_67/31337 le natif crit 3/3 avec le crit-chance
    # BUFFE (40), ce que seul cet ordre reproduit.
    return op_and(op_and(crit, block), atk)


class AncestralFortuneAbility(ActiveAbility):
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.AncestralFortuneAbility$$ExecuteBehaviour` (id 1207,
    `votanUthar` -- Uthar). SELF-CAST : Uthar gagne +extraCritChance (1485) et +extraBlockChance (1486)
    pendant 1 round, puis — s'il est adjacent a un ennemi — frappe 3x Plasma le meilleur d'entre eux.

    Behaviour = l'arbre `ancestral_fortune_tree()` (mirror 1:1). `target_id` du message est IGNORE : le
    natif RE-DERIVE sa cible d'attaque par selecteur (`GetAttackTarget`), le cast est un self-cast
    (`GetPossibleAttackTargets` ne sert qu'au preview cote UI/decision).

    HORS PERIMETRE de ce lot (prerequis absents, signales et NON empiles ici) :
      * `…AncestralFortune_CountResetAbility$$CreateTrigger` / `$$CreateBehaviour` (compteur de blocs+crits
        via persistent-data) et `…AncestralFortune_TriggerResetAbility$$CreateTrigger` / `$$CanReset`
        (`ResetActiveAbility` au 6e = `nrOfAttacks`) — substrat persistent-data + ResetActiveAbility +
        predicat WasBlock (event UnitBlocked) non portes.
      * face DECISION (`IdunBattle.AI.Playbook.Loki.AncestralFortunePlaybook$$MakeDamagePredictions` /
        `$$ShouldExecute`).
    Turn-flags = defauts base (1207 absent des deux frozensets -> le cast termine le tour)."""
    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.AncestralFortune)   # 1207
    ABILITY_ID = "AncestralFortune"

    # GATE DE CIBLE (#115). `IdunBattleLogic.Entities.Abilities.Active.Loki.AncestralFortuneAbility$$.ctor`
    # COPIE le PRESET STATIQUE `IdunBattle.Core.Services.TargetingOptions` statics `+0x280` (pose par
    # `IdunBattle.Core.Services.TargetingOptions$$.cctor`), puis `AActiveAbility..ctor(this, &opts, 2, 0)`.
    # Masque effectif = `preset+0x28` = statics `+0x2a8` -> `0x8004`.
    # Decomposition (`IdunBattle.Core.Services.TargetingRule`) :
    #     0x4      CasterMatchesDynamicRule -> volet CASTER (regle-delegue), NON PORTE
    #     0x8000   bit 15 CanTargetCaster (`TargetingOptions$$get_CanTargetCaster` = `(rules >> 0xf) & 1`)
    #              -> flag DECLARATIF : il n'apparait dans AUCUNE branche de
    #              `TargetingQuery$$GetInvalidTargetReason` NI de `$$GetInvalidCasterReason` (verifie
    #              exhaustivement au decompile des deux cascades) ; il ne sert qu'aux consommateurs de
    #              ciblage (preview / IA). Coherent avec le SELF-CAST de l'ability.
    # => masque FIDELE, mais AUCUNE regle de refus armee : le gate reste muet pour 1207, par construction
    # native et non par trou de port.
    # Le BYTE `options+0x00` du preset vaut **1** (`.cctor` : `*(statics + 0x280) = 1`) ->
    # `self_cast=True`, coherent avec le SELF-CAST documente dans la docstring de la classe : le cast
    # sur Uthar lui-meme est aiguille vers `TargetingQuery$$GetCasterNotAddedReason`, pas vers le
    # filtre statique.
    # PORTEE (#241) : preset `TargetingOptions` statique `+0x280` -> `TargetingRange`
    # statique `+0x60` = `overrideRange = 0` (portee NULLE, cast SELF) + `forceMeleeTarget =
    # False`.
    TARGETING_OPTIONS = TargetingOptions(rules=(
          TR.CasterMatchesDynamicRule
        | TR.CasterIsPossibleTarget
    ), self_cast=True, range=RANGE_SELF, force_melee_target=RANGED_BOOL_FALSE)

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        atk_tgt = _ancestral_fortune_attack_target(state, caster_id)
        ectx = ExecutionContext(state=state, rng=state.rng)
        ancestral_fortune_tree(atk_tgt).execute(
            entities_from_state(state, caster_id, atk_tgt), ectx)
        buffs = [{"effect_type": p.get("effect_type"), "stat": p.get("stat"),
                  "placed": p.get("placed")}
                 for n, p in ectx.emitted if n == "AddDynamicStatModifierEffect"]
        atk = next((p for n, p in ectx.emitted if n == "AttackWithAttackDamage"), {})
        return {"ability": "AncestralFortune", "caster": caster_id,
                "attack_target": atk_tgt, "buffs": buffs,
                "attack": atk.get("attack"), "total": atk.get("total"), "dsl": True}


# ==================================================================================================
# MassDriverAccelerator (1222, `votanChampion` -- Kimm) -- #525
# ==================================================================================================
MASS_DRIVER_ACCELERATOR_ID = "MassDriverAccelerator"

#: `AbilityConfiguration$$GetNumberConstant(config, 0xe)` -> cle gameconfig `extraMovement` (= 1).
#: LUE au decompile, jamais deduite du nom : `...MassDriverAcceleratorAbility$$ExecuteBehaviour` ET
#: `...MassDriverAcceleratorAbility$$GetPossibleMoveTiles` appellent tous deux `GetNumberConstant(0xe)`.
MASS_DRIVER_CONST_EXTRA_MOVEMENT = AbilityConstantType.extraMovement          # 0xe = 14

#: `AddStaticStatModifierEffect(..., 0x606, ...)` / `UnitMovementRangeWithBonus(..., 0x606, ...)`.
#: 0x606 = 1542 = `EffectType.MassDriverAccelerator_ExtraMovement` (resolu dans
#: `data/symbols/<build>/frida/enums.tsv`, pas devine : l'ordinal 1542 est AUSSI un membre valide
#: d'autres enums d'id, seul le NOM discrimine).
MASS_DRIVER_EXTRA_MOVEMENT = int(EffectType.MassDriverAccelerator_ExtraMovement)   # 0x606 = 1542


def mass_driver_buff_targets_selector():
    """`...MassDriverAcceleratorAbility$$GetBuffTargets` -- ARBRE DSL, MIRROR 1:1 du decompile :

        TargetsSelector.op_Addition( owner@0x30,
                                     AdjacentFriends(owner@0x30, unique: 1, selectionType: 3) )

    = l'OWNER **et** ses allies hex-adjacents. C'est ce sur quoi porte le buff de mouvement, et c'est
    ce que l'utilite `MassDriverAccelerator_AdjacentFriendly` du scoreur natif recompense.

    `...MassDriverAcceleratorAbility$$ExecuteBehaviour` RE-INLINE exactement le meme couple
    (`AdjacentFriends(*(selectors+0x30), 1, 3)` puis `op_Addition`) plutot que d'appeler ce getter :
    les deux faces voient donc le MEME ensemble, et ce foyer est l'unique mirror.

    ⚠ La REFERENCE d'equipe d'`AdjacentFriends` est son PROPRE 1er argument (surcharge 3-args
    `IdunBattleLogic.Entities.DSLSelectors$$AdjacentFriends(unit, unique, selectionType)` ->
    `Friends(reference = unit, ...)`), pas le caster : elle est passee EXPLICITEMENT ici, meme si
    `Owner == Caster` sur une ability active la rend numeriquement egale au defaut."""
    return Union(Owner(), AdjacentFriends(Owner(), Const(1), reference=Owner()))


def mass_driver_buff_tree(extra_movement: int):
    """1er terme de l'arbre natif -- MIRROR du decompile :

        AddStaticStatModifierEffect( GetBuffTargets(),
                                     0x606 = MassDriverAccelerator_ExtraMovement,
                                     0x1   = StatType.Movement,
                                     amount = DSLFormulas$$Get(GetNumberConstant(0xe = extraMovement)),
                                     turns  = <DSLFormulas+0x20>,
                                     isHidden = 0 )

    `<DSLFormulas+0x20>` = `Direct(1)`, LU dans `IdunBattleLogic.Entities.DSLFormulas$$.ctor` qui
    alloue `+0x18 Direct(0) · +0x20 Direct(1) · +0x28 Direct(2) · +0x30 Direct(100) · +0x38 Direct(-1)`
    -> la duree est **1 TOUR** (`duration_turns`, PAS `TurnsFromRounds`).

    La surcharge est celle a `turns:IAmountFormula`
    (`IdunBattleLogic.Entities.DSLBehaviors$$AddStaticStatModifierEffect(targets, effectType,
    statType, amount:IAmountFormula, turns:IAmountFormula, isHidden)`) -- le 6e argument natif est un
    NOEUD du champ `+0x20` des formules partagees, pas un `Nullable<int>`.

    `isHidden = 0` (7e argument) : le port ne modelise pas la visibilite UI d'un effet -- inerte
    offline, note pour ne pas le croire absent."""
    return AddStaticStatModifierEffect(mass_driver_buff_targets_selector(),
                                       MASS_DRIVER_EXTRA_MOVEMENT, int(StatType.MOVEMENT),
                                       Const(int(extra_movement)),
                                       name="MassDriverAccelerator_ExtraMovement",
                                       duration_turns=1)


def mass_driver_move_range(state: "State", caster_id: int) -> int:
    """`IdunBattleLogic.Entities.DSLFormulas$$UnitMovementRangeWithBonus(caster@0x48,
    0x606 = MassDriverAccelerator_ExtraMovement, Get(GetNumberConstant(0xe = extraMovement)))`, le 4e
    argument du `TilesUnitCanMoveToChargeTarget` de
    `...MassDriverAcceleratorAbility$$GetPossibleMoveTiles` -- MIRROR 1:1 du decompile :

        If( HasEffect(caster, 0x606, onlyActive: 0, targetType: 6),
            StatAmountFormula(caster, 0x1 = StatType.Movement),
            Sum(StatAmountFormula(caster, 0x1), movementBonus) )

    ANTI-DOUBLE-COMPTE, et c'est le natif qui le porte, pas nous : les DEUX consommateurs de
    `GetPossibleMoveTiles` voient la MEME portee effective, mais par des branches DIFFERENTES.
      * `...MassDriverAcceleratorAbility$$GetDynamicInvalidTargetReason` (le GATE) l'evalue AVANT
        tout cast -> l'effet 1542 n'est pas pose -> branche `Movement + extraMovement` ;
      * l'etage MOVE d'`ExecuteBehaviour` l'evalue APRES l'`AddStaticStatModifierEffect` (les
        selecteurs natifs sont PARESSEUX) -> l'effet EST pose et la stat MOVEMENT est deja bonifiee
        -> branche `Movement` NU.
    Les deux coincident donc, et la fidelite du stat-mod est DIRECTEMENT observable sur la portee de
    charge. MEME forme, MEME foyer natif que `orks.py::waaagh_move_range` (1099) et
    `loki/strike.py::_black_rage_move_range` (1342) -- seul l'`EffectType` differe."""
    e = state.get_entity(int(caster_id))
    sc = e.get_component(StatsComponent) if e is not None else None
    stats = getattr(sc.ctx, "stats", None) if sc is not None else None
    mv = int(stats.get_stat(int(StatType.MOVEMENT), 0)) if stats is not None else 0
    has_eff = (state.effects is not None
               and state.effects.has_effect(int(caster_id),
                                            effect_type=MASS_DRIVER_EXTRA_MOVEMENT))
    if has_eff:
        return mv
    bonus = ability_var(MASS_DRIVER_ACCELERATOR_ID, MASS_DRIVER_CONST_EXTRA_MOVEMENT.name,
                        is_constant=True) or 0                # GetNumberConstant(0xe) = 1
    return mv + int(bonus)


def mass_driver_possible_move_tiles_selector(move_range: int):
    """`...MassDriverAcceleratorAbility$$GetPossibleMoveTiles` -- ARBRE DSL, MIRROR 1:1 :

        TilesUnitCanMoveToChargeTarget( caster@0x48, casterTile@0x50, targetTiles@0x78,
                                        UnitMovementRangeWithBonus(caster@0x48, 0x606,
                                                                   Get(GetNumberConstant(0xe))),
                                        ignoreFlags = 0 )

    MEME appel, MEMES slots que `LeadingTheChargeAbility$$GetPossibleMoveTiles` et
    `BlackRageAbility$$GetPossibleMovementTiles` : le port passe donc par le MEME foyer
    (`entities/selectors/tiles.tiles_unit_can_move_to_charge_target`), qui se developpe en
    `CanAddUnit(AdjacentTiles(target)) op_BitwiseAnd MovableTilesInRange(caster, casterTile, range,
    0, 0)`.

    `ignoreFlags = 0` -- CONTRASTE avec `VigilanceEternalAbility$$GetPossibleMovementTiles` (1). Le
    terme reste NON EXERCE cote port (residu #381) ; il est propage tel quel pour que les deux
    call-sites divergent le jour ou le substrat existe.

    `SelectTile(CasterTile())` = mirror du `TargetsSelector$$SelectTile` (vslot 0xc) par lequel
    `MovableTilesInRangeSelector$$Select` resout son `casterTiles` (#459).

    `move_range` arrive DEJA CALCULE (`mass_driver_move_range`) : c'est LA valeur du 4e argument
    natif, presentee au noeud par un `Const`."""
    return tiles_unit_can_move_to_charge_target(Caster(), SelectTile(CasterTile()), Target(),
                                                Const(int(move_range)), ignore_flags=False)


def mass_driver_move_tile(state: "State", caster_id: int, target_id: int, move_range: int):
    """`...MassDriverAcceleratorAbility$$GetMoveTile` -- MIRROR du decompile :

        First( SortTilesByUtility( GetPossibleMoveTiles(), caster@0x48,
                                   0x21 = UtilityType.MovementSuggestion, parent = null ),
               1 )

    C'est la surcharge INT de `IdunBattleLogic.Entities.DSLSelectors$$SortTilesByUtility`
    (`utilityType:IdunBattle.Configuration.UtilityType`), PAS la `UtilityDefinition` batie a la main
    de `LeadingTheChargeAbility$$GetMoveTile` / `RammingSpeedAbility$$GetTileToMoveTo`.
    ⚠ `0x21` = **33**, et `33 = MovementSuggestion` dans `enums.tsv` du build courant (`32` y est
    `EnvEndBombardment`) : le littéral a ete RE-LU sur CETTE ability, pas herite d'un port frere.

    `ExecuteBehaviour` re-inline exactement ce couple `SortTilesByUtility(..., 0x21, 0)` + `First(1)`
    plutot que d'appeler ce getter -- les deux voient le meme ensemble.

    Le tri passe par le FOYER `first_tile_by_utility` (`SortTilesByUtilitySelector$$Select` : tri
    DECROISSANT, `OrderBy` LINQ STABLE -> les egalites gardent l'ordre du selecteur source, ZERO
    tirage). `unit_id = caster` = le `dc.unit` du natif (`caster@0x48`). Rend une (col,row) ou None."""
    board = state.board
    if board is None or state.get_entity(int(target_id)) is None:
        return None
    cands = mass_driver_possible_move_tiles_selector(move_range).evaluate(
        entities_from_state(state, caster_id, target_id))
    if not cands:
        return None
    best = first_tile_by_utility(state, cands, unit_id=int(caster_id),
                                 utility_type=int(UtilityType.MovementSuggestion))
    return board.coord(best) if best is not None else None


def mass_driver_adjacent_attack_targets_selector():
    """`...MassDriverAcceleratorAbility$$GetAdjacentAttackTargets` -- ARBRE DSL, MIRROR 1:1 :

        Enemies( of: caster@0x48,
                 entities: AdjacentUnits(target@0x60, unique: 1, selectionType: 3),
                 selectionType: 3 )

    = les ENNEMIS DU CASTER poses sur les tuiles hex-adjacentes A LA CIBLE. La cible elle-meme est
    deja retiree par `AdjacentUnits` (`_within` exclut le centre), et `AdjacentUnits` ne filtre PAS
    l'equipe -- c'est le `Enemies` qui le fait, en prenant le CASTER pour referent (ce que le noeud
    `Enemies` du port mirrore par construction : il lit `ctx.caster`).

    `ExecuteBehaviour` re-inline exactement ce couple pour le passer a `DSLSelectors$$Cache` /
    `DSLBehaviors$$SetCache` ; la face DECISION consomme le MEME artefact
    (`entities/abilities/active_ability.py::MassDriverAcceleratorAbility._AOE`, qui l'exprime en
    `AdjacentEnemies(TargetTile(), 1)` -- meme ensemble, autre substrat)."""
    return Enemies(AdjacentUnits(Target(), Const(1)))


def mass_driver_attack_tree():
    """2e terme de l'arbre natif -- MIRROR du decompile :

        cache   = Cache( GetAdjacentAttackTargets(), matchAbilityEntities: 1 )
        atk1    = AttackWithAttackDamage( caster@0x48, target@0x60,
                                          MinMaxDamage(abilityState),          # minDmg / maxDmg
                                          Nullable(GetDamageProfile()),        # damageProfile
                                          GetHits(),                           # nrOfHits
                                          AbilityOrEffect(this), <options ZERO>,
                                          selectionType = 2 )
        atk2    = AttackWithAttackDamage( caster@0x48, Alive(cache),
                                          MinMaxDamage2(abilityState),         # minDmg_2 / maxDmg_2
                                          Nullable(GetDamageProfile2()),       # damageProfile_2
                                          GetHits2(),                          # nrOfHits_2
                                          AbilityOrEffect(this), <options ZERO>,
                                          selectionType = 2 )
        return    AtomicGroup( ( SetCache(cache) & Group(atk1, caster@0x48, 0x20) )
                               & Group(atk2, caster@0x48, 0x21) )

    et l'appelant l'enveloppe dans `IfAlive(caster@0x48, <ceci>)` (cf. `MassDriverAcceleratorAbility.
    execute_behaviour`).

    ⚠ **INSTANCE FRAICHE PAR CAST** : le noeud `Cache` est STATEFUL (memoisation par instance) -- d'ou
    la FACTORY plutot qu'un attribut de classe. Le `SetCache` FIGE l'ensemble des ennemis adjacents a
    la cible AVANT la 1re attaque ; le `Alive(cache)` de la 2e relit CE cache en n'en gardant que les
    vivants. Sans la memoisation, la 2e attaque re-deriverait la geometrie APRES que la 1re a mute
    l'etat -- ce n'est PAS ce que fait le natif.

    ⚠ **PROFILS ET COUPS DISTINCTS ENTRE LES DEUX VOLETS**, LUS a la config 1222 :
    `damageProfile = DirectDamage` / `nrOfHits = 1` pour la cible, `damageProfile_2 = Physical` /
    `nrOfHits_2 = 1` pour le splash. `minDmg_2`/`maxDmg_2` y sont EGAUX a `minDmg`/`maxDmg`, mais les
    cles sont passees separement (le natif appelle bien `MinMaxDamage2`) : le jour ou un build les
    desaccorde, le port suit sans retouche.
    ⚠ DIVERGENCE natif/natif DEJA DOCUMENTEE cote DECISION : le playbook, lui, repasse la valeur du
    batch PRINCIPAL aux deux volets (`entities/abilities/active_ability.py`). C'est l'EXECUTION qui
    lit `MinMaxDamage2`, pas la prediction.

    `Group(..., caster@0x48, 0x20/0x21)` = `GroupType.Ability_Attack` / `Ability_Attack_2` -- cote
    ETAT c'est un PASS-THROUGH (couche VUE/timeline, cf. #201/#504), porte pour le MIRROR STRUCTUREL
    et parce que le natif EVALUE son selecteur de groupe.
    `selectionType = 2` des deux `AttackWithAttackDamage` : meme valeur que tous les call-sites de
    charge deja portes (Waaagh / UnstoppableMomentum / LeadingTheCharge), foldee dans la feuille."""
    consts = (GC.ability(MASS_DRIVER_ACCELERATOR_ID) or {}).get("constants") or {}
    profile = consts.get("damageProfile")            # GetDamageProfile()  = GetEnumConstant(0x2b)
    profile2 = consts.get("damageProfile_2")         # GetDamageProfile2() = GetEnumConstant(0x3f)
    # `MassDriverAcceleratorAbility$$ExecuteBehaviour` pousse `matchAbilityEntities = 1` (mode
    # DICT), qui est le defaut du noeud.
    cache = Cache(mass_driver_adjacent_attack_targets_selector())
    atk1 = AttackWithAttackDamage(Target(), MASS_DRIVER_ACCELERATOR_ID, profile, is_melee=True,
                                  ability_type=int(ActiveAbilityType.MassDriverAccelerator))
    atk2 = AttackWithAttackDamage(Alive(cache), MASS_DRIVER_ACCELERATOR_ID, profile2,
                                  is_melee=True, min_key="minDmg_2", max_key="maxDmg_2",
                                  hits_key="nrOfHits_2", multi=True,
                                  ability_type=int(ActiveAbilityType.MassDriverAccelerator))
    return AtomicGroup(op_and(
        op_and(SetCache(cache),
               Group(atk1, int(GroupType.Ability_Attack), Caster())),
        Group(atk2, int(GroupType.Ability_Attack_2), Caster())))


class MassDriverAcceleratorAbility(ActiveAbility):
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.MassDriverAcceleratorAbility$$ExecuteBehaviour`
    (id 1222, `votanChampion` « Kimm », namespace natif `Abilities.Active.Loki`) -- CHARGE A SPLASH,
    UNE SEULE execution top-level (`AActiveAbility$$Execute`), MIRROR du decompile :

        Execute(
          ( AddStaticStatModifierEffect( owner@0x30 + AdjacentFriends(owner@0x30),
                                         0x606 = MassDriverAccelerator_ExtraMovement,
                                         0x1 = StatType.Movement,
                                         Get(GetNumberConstant(0xe = extraMovement)),
                                         <DSLFormulas+0x20> = Direct(1), isHidden: 0 )
            & MoveUnit( caster@0x48,
                        First(SortTilesByUtility(GetPossibleMoveTiles(), caster@0x48,
                                                 0x21 = MovementSuggestion, null), 1),
                        <options ZERO> ) )
          & IfAlive( caster@0x48,
              AtomicGroup( ( SetCache(cache) & Group(atk1, caster@0x48, 0x20) )
                           & Group(atk2, caster@0x48, 0x21) ) ) )

    LE VERDICT QUI TRANCHE LA CATEGORIE D'AUDIT
    -------------------------------------------
    L'audit classait 1222 en `DAMAGE(DirectDamage)`. C'est **juste mais incomplet** : le
    `damageProfile` de la config VAUT bien `DirectDamage` et le 1er `AttackWithAttackDamage` le
    consomme -- mais l'`ExecuteBehaviour` porte AUSSI un buff de stat et un deplacement, et un SECOND
    volet de degat au profil `Physical`. Ce n'est donc ni « un buff a damageProfile » (la famille
    NovaBoost/NovaCharge/NovaShield), ni une attaque nue : c'est une CHARGE, du meme patron que
    `LeadingTheChargeAbility` (1204) et `BlackRageAbility` (1163). L'indice « une utilite du
    gameconfig nommee `MassDriverAccelerator_AdjacentFriendly` » est CONFIRME au decompile par
    `...$$GetBuffTargets` = `owner + AdjacentFriends(owner)` : le scoreur prefere les positions ou
    Kimm a des allies au contact parce que le buff de mouvement les touche AUSSI.

    ORDRE DES ETAGES, ET POURQUOI IL EST OBSERVABLE
    ------------------------------------------------
    1. le buff `Movement` est pose D'ABORD, sur Kimm ET ses allies adjacents ;
    2. la CHARGE est calculee ENSUITE -- `UnitMovementRangeWithBonus` voit alors l'effet 1542 deja
       pose et lit la stat MOVEMENT DEJA bonifiee (cf. `mass_driver_move_range`) ;
    3. l'attaque principale et le splash ne s'executent QUE si Kimm est encore vivant apres la
       charge (`IfAlive(caster@0x48)` = `If(IsAlive(caster), ...)`, le natif ne faisant que composer
       les deux noeuds).

    La composition `op_BitwiseAnd` de `IdunBattle.DSL.AbilityBehaviour` est SEQUENTIELLE
    (`CombinedBehaviour`), donc executer `buff` puis `move & ifAlive` l'un apres l'autre sur le MEME
    `AbilityEntities` est le mirror exact de l'arbre unique -- c'est ce que fait `execute_behaviour`
    ci-dessous, et c'est ce qui permet de lire la destination de charge APRES la pose du buff,
    exactement comme le natif dont les selecteurs sont PARESSEUX.

    Diag : {move, dest, move_range, buffed, attack, splash, splash_targets}."""
    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.MassDriverAccelerator)   # 1222
    ABILITY_ID = MASS_DRIVER_ACCELERATOR_ID

    # GATE DE CIBLE (#115). `...MassDriverAcceleratorAbility$$.ctor` n'appelle AUCUN
    # `IdunBattle.Core.Services.TargetingOptions$$.ctor` : il RECOPIE les 0x40 octets du champ
    # statique `<TargetingOptions statics>+0x240` puis appelle
    # `AActiveAbility..ctor(this, &opts, 0)` (2e forme du piege, cf. CLAUDE.md). Le masque effectif
    # est donc la constante ecrite par `IdunBattle.Core.Services.TargetingOptions$$.cctor`, RELUE
    # ICI sur ce preset (pas heritee d'un port frere) :
    #     *(statics + 0x240) = 0            -> isSelfCasting = False
    #     *(statics + 0x248..0x25c)         -> copie de `TargetingRange statics+0x48` = useWholeBoard
    #     *(statics + 0x260) = 1            -> forceMeleeTarget = `RangedBool.False`
    #     *(statics + 0x268) = 0x102004032  -> rules
    # Decomposition EXHAUSTIVE de `0x102004032` (reste 0x0 apres les six bits ci-dessous) :
    #     0x2         TargetMatchesDynamicRule       -> `get_dynamic_invalid_target_reason` ci-dessous
    #     0x10        CasterHasNotMoved              -> Kimm ne peut pas charger apres s'etre deplace
    #     0x20        TargetHasFreeAdjacentTile      -> il faut un hex libre au contact de la cible
    #     0x4000      TargetIsEnemy
    #     0x2000000   AllowObscuredTargetByElevation
    #     0x100000000 TargetIsNotAdjacent            -> une cible DEJA au contact est refusee
    # C'est le MEME preset `+0x240` que `1204 LeadingTheCharge` et `1177 LightOfSanguinius` -- ce qui
    # separe ces abilities est leur `GetDynamicInvalidTargetReason`, pas leurs options.
    # PORTEE (#241) : `range` = `TargetingRange` statique -> `useWholeBoard`, donc le volet generique
    # de portee NE TESTE RIEN ; la contrainte de distance vit ENTIEREMENT dans la regle dynamique.
    TARGETING_OPTIONS = TargetingOptions(rules=(
          TR.TargetMatchesDynamicRule
        | TR.CasterHasNotMoved
        | TR.TargetHasFreeAdjacentTile
        | TR.TargetIsEnemy
        | TR.AllowObscuredTargetByElevation
        | TR.TargetIsNotAdjacent
    ), self_cast=False, range=RANGE_WHOLE_BOARD, force_melee_target=RANGED_BOOL_FALSE)

    def get_dynamic_invalid_target_reason(self, state: "State", caster_id: int,
                                          target_id: Optional[int]) -> int:
        """`...MassDriverAcceleratorAbility$$GetDynamicInvalidTargetReason(caster, casterTiles,
        target, targetTiles)` -- MIRROR du decompile :

            tiles = MassDriverAcceleratorAbility.GetPossibleMoveTiles()
            ents  = AbilityEntities(caster, caster, ..., casterTiles, ..., targetTiles, ...)
            return Count( tiles.<slot 2>(ents) ) > 0 ? 0 : 0x8000000

        `0x8000000` = `TargetingRule.TargetIsInRange` : 1222 exprime sa contrainte de DISTANCE ici, et
        pas par le volet portee generique du filtre statique (desarme par `useWholeBoard`). Predicat :
        **il existe au moins un hex LIBRE et marchable adjacent a la cible, atteignable par Kimm en
        `MOVEMENT + extraMovement` pas** -- autrement dit la cible doit etre chargeable ce tour-ci.

        JUMEAU STRUCTUREL de `LeadingTheChargeAbility$$GetDynamicInvalidTargetReason` et de
        `BlackRageAbility$$GetDynamicInvalidTargetReason` (meme forme, meme code rendu, meme appel
        SANS argument a leur `GetPossibleMoveTiles` respectif).

        Au moment du GATE l'effet 1542 n'est PAS pose (aucune execution n'a commence) ->
        `mass_driver_move_range` prend la branche `MOVEMENT + extraMovement` du `If` natif."""
        if target_id is None or state.get_entity(int(target_id)) is None:
            return int(TR.TargetIsInRange)
        move_range = mass_driver_move_range(state, int(caster_id))
        tiles = mass_driver_possible_move_tiles_selector(move_range).evaluate(
            entities_from_state(state, caster_id, target_id))
        return 0 if len(tiles) > 0 else int(TR.TargetIsInRange)

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        if target_id is None:
            return None
        consts = (GC.ability(self.ABILITY_ID) or {}).get("constants") or {}
        # `Get(GetNumberConstant(0xe = extraMovement))` -- une CONSTANTE de config (pas une variable
        # de niveau) : `AbilityConfiguration$$GetNumberConstant`, pas `GetVariableForLevel`.
        extra_movement = int(consts.get(MASS_DRIVER_CONST_EXTRA_MOVEMENT.name) or 0)

        ectx = ExecutionContext(state=state, rng=state.rng)
        entities = entities_from_state(state, caster_id, target_id)

        # ---- 1er terme : le buff de mouvement (owner + amis adjacents) --------------------------
        mass_driver_buff_tree(extra_movement).execute(entities, ectx)
        buffed = [p.get("unit") for n, p in ectx.emitted
                  if n == "AddStaticStatModifierEffect"]

        # ---- 2e terme : la CHARGE. La portee est lue MAINTENANT, donc APRES la pose de l'effet
        # 1542 -- c'est la branche `Movement` NU d'`UnitMovementRangeWithBonus` (selecteurs natifs
        # PARESSEUX). `MoveUnit(caster@0x48, <tuile>, <options ZERO>)` : le decompile met a zero les
        # cinq selecteurs d'options -> aucun flag after-move (meme configuration que Waaagh /
        # LeadingTheCharge).
        move_range = mass_driver_move_range(state, caster_id)
        dest = mass_driver_move_tile(state, caster_id, target_id, move_range)
        MoveUnit(Caster(), FixedTiles([dest] if dest is not None else [])).execute(entities, ectx)
        moved = next((p for n, p in ectx.emitted if n == "MoveUnit"), None)

        # ---- 3e terme : `IfAlive(caster@0x48, AtomicGroup(...))` -- l'attaque principale et le
        # splash ne partent que si Kimm a survecu a la charge.
        IfBehaviour(IsAlive(Caster()), mass_driver_attack_tree()).execute(entities, ectx)

        atks = [p for n, p in ectx.emitted if n == "AttackWithAttackDamage"]
        return {"ability": self.ABILITY_ID, "caster": caster_id, "target": target_id,
                "move": moved, "dest": dest, "move_range": move_range,
                "extra_movement": extra_movement, "buffed": buffed,
                "attack": atks[0] if atks else None,
                "splash": atks[1:],
                "splash_targets": [a.get("target") for a in atks[1:]], "dsl": True}
