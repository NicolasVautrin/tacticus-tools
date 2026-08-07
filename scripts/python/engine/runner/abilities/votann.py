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
"""
from __future__ import annotations

from fractions import Fraction
from typing import Optional, TYPE_CHECKING

import gameconfig as GC

from .base import ActiveAbility
from .targeting import (RANGE_ADJACENT, RANGE_FROM_CONFIG, RANGE_SELF, RANGED_BOOL_FALSE,
                        RANGED_BOOL_TRUE, TargetingOptions)
from .targeting_rule import TargetingRule as TR
from .behaviours.combat import AttackWithAttackDamage
from .behaviours.context import entities_from_state
from .behaviours.effects import AddDynamicStatModifierEffect, AddEffect
from .loki import perform_ai_attack_from_current_position
from ..components import OwnerComponent, StatsComponent, UnitComponent, PositionComponent
from ...entities.active_ability_type import ActiveAbilityType
from ...entities.effect_type import EffectType
from ...entities.stats import StatType, StatPart
from ...entities.behaviours import op_and, op_add, If as IfBehaviour
from ...entities.effects.magnitude import ability_var
from ...entities.selectors.accessors import Target
from ...entities.selectors.tiles import Caster
from ...dsl.base import _round_fix64   # `IdunBattle.DSL.AAmountFormula$$RoundFix64Result`
from ...dsl.effects import ExecutionContext, AbilityBehaviour, OperationResult
from ...entities.formulas import StatAmount, Count
from ...entities.triggers import AmountIsGreaterThanZero
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

    - `AdjacentEnemies(caster, 1)` = ennemis VIVANTS a distance hex 1 du caster.
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
    import hexgeo
    e = state.get_entity(caster_id)
    pc = e.get_component(PositionComponent) if e is not None else None
    oc = e.get_component(OwnerComponent) if e is not None else None
    sc = e.get_component(StatsComponent) if e is not None else None
    if pc is None or oc is None:
        return None
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
        if hexgeo.distance(src, (opc.col, opc.row)) == 1:          # radius 1
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
    return first_by_damage_utility(state, cands, avg, avg)


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
