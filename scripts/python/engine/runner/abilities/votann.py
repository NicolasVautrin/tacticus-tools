"""Abilities actives de la faction VOTANN (namespace natif `Abilities.Active.Loki.*`) -- port isole (case-220 §6.10).

Module DEDIE a la faction Leagues of Votann (comme `genestealer.py`/`deathguard.py`/`blacklegion.py` : une
classe par ability, l'arbre SPECIFIQUE vit avec sa classe). RE ghidra gqfc5mff6c (VA citees). Doc :
docs/rl/case-220/votann.md.

Contenu :
- `IronkinSteeljack` (1219, `votanMemnyr` -- Memnyr) : summon `votanSmnSteeljack` sur un hex LIBRE adjacent au
  caster (cast tile-target), `WithStatsFromConfig` level-scale, attaque a l'apparition
  (`PerformAIAttackFromCurrentPosition`). CLONE du corps `AberrantHypermorphAbility.ExecuteBehaviour @1811b0550`
  (dedup IL2CPP -- cf. classe).
"""
from __future__ import annotations

from typing import Optional, TYPE_CHECKING

import gameconfig as GC

from .base import ActiveAbility
from .behaviours import entities_from_state
from .loki import perform_ai_attack_from_current_position
from ..components import OwnerComponent, StatsComponent
from ...entities.active_ability_type import ActiveAbilityType
from ...dsl.effects import ExecutionContext, AbilityBehaviour, OperationResult

if TYPE_CHECKING:
    from ..state import State


class SpawnSteeljack(AbilityBehaviour):
    """Feuille `Spawn` de `IronkinSteeljackAbility.ExecuteBehaviour` (id 1219, `votanMemnyr`). Le corps natif
    est DEDUPLIQUE avec `AberrantHypermorphAbility.ExecuteBehaviour @1811b0550` (RE ci-dessous : les DEUX
    classes pointent leur slot ExecuteBehaviour vers le MEME code @1811b0550 -- byte-identique, seule la
    config per-instance @0x30/@0x60 differe) ; il decompile en :
        Execute( Spawn(caster@0x160, TARGET@0x178 = la TUILE ciblee par le cast (hex libre adjacent au caster),
                       unitId = GetStringConstant(config, 0) = "votanSmnSteeljack",
                       SpawnUnitOptions.WithStatsFromConfig(config 1219,
                                                            AbilityLevelAmount(Self@0x148, AbilityType(1219)))
                         .onAppearance(+0x18) = PerformAIAttackFromCurrentPosition(Target@0x178)) )
    Mirror 1:1 de `SpawnAberrant` (@1811b0550 = le MEME corps) avec la config 1219. Le placement N'EST PAS un
    selecteur : la tuile EST la cible du cast (choisie par le joueur/l'IA, legalite = abilityTargets kind="tile",
    hex libre adjacent au caster via `TargetingOptions(0, statsFromClass, 1, 0x1040)` -- ctor @1811ebc30
    IDENTIQUE a AberrantHypermorph @1811b0730 / MasterOfTheTutelaries @1811f3310) -> la feuille porte `tile_id`
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
        from ..operations.spawn import _spawn_config_grot
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
    """Arbre de `IronkinSteeljackAbility.ExecuteBehaviour @1811b0550` (id 1219, `votanMemnyr` -- MIRROR 1:1 du
    DECOMPILE, corps DEDUPLIQUE avec AberrantHypermorph) :
        Execute( Spawn(caster@0x160, Target@0x178=TUILE, "votanSmnSteeljack",
                       WithStatsFromConfig(config, AbilityLevelAmount(Self@0x148, 1219))
                         .onAppearance = PerformAIAttackFromCurrentPosition(Target@0x178)) )
    UN SEUL noeud `Spawn` (plain `AActiveAbility.Execute`, PAS `ExecuteAtomic`, PAS d'AddEffect, PAS de
    op_BitwiseAnd -- le noeud top-level passe a Execute EST le Spawn seul). Count=1 (une seule tuile-cible ; le
    `2` litteral de `TestSummonAbility @1811c7cd0` -- une AUTRE forme de summon a `count=Nullable(2)`@options+0x40
    -- N'EST PAS present dans @1811b0550). DISTINCT de MasterOfTheTutelaries @1811f30c0 (op_BitwiseAnd(AddEffect
    (1197), Spawn)). Port : feuille `SpawnSteeljack` (== `SpawnAberrant` avec la config 1219)."""
    return SpawnSteeljack(tile_id)


class IronkinSteeljackAbility(ActiveAbility):
    """`IronkinSteeljackAbility.ExecuteBehaviour @1811b0550` (id 1219, `votanMemnyr` -- Memnyr, namespace natif
    `Abilities.Active.Loki`). Cast TILE-TARGET (« Summon an Ironkin Steeljack on a free hex adjacent to Memnyr »)
    : spawn UN `votanSmnSteeljack` sur la tuile ciblee (hex libre adjacent au caster), qui attaque
    immediatement sans bouger (`PerformAIAttackFromCurrentPosition`). Pas de triggered, pas d'effet pose sur le
    caster.

    RE (ghidra gqfc5mff6c) -- l'ExecuteBehaviour est un corps GSHARED HERITE NON ATTACHE (aucun symbole
    `IronkinSteeljackAbility$$ExecuteBehaviour` ; seul le ctor @1811ebc30 est symbolise). Pin via la table
    methodPointers : le slot ExecuteBehaviour d'IronkinSteeljack (0x1830f8110, juste apres son ctor @1811ebc30
    a 0x1830f8108) = **0x1811b0550** = EXACTEMENT le slot ExecuteBehaviour d'AberrantHypermorph (0x1830f6fb0,
    apres son ctor @1811b0730 a 0x1830f6fa8). Les DEUX classes partagent donc le MEME corps @1811b0550 (dedup
    IL2CPP de code byte-identique) -> IronkinSteeljack = clone exact d'AberrantHypermorph, seule la config
    per-instance differe : ctor @1811ebc30 = `TargetingOptions(0, statsFromClass, 1, 0x1040)` + `AActiveAbility
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
    « cannot-move-this-turn » que le natif pose SUR LE SUMMON (`TriggerSpawnedUnitBehaviours` @180fd57b0 : flag
    0x23) est un NO-OP runner : le summon a agi a l'apparition et n'est pas rejoue ce tour dans notre modele
    (aucun consommateur offline) -- meme raisonnement qu'AberrantHypermorph."""
    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.IronkinSteeljack)  # 1219
    ABILITY_ID = "IronkinSteeljack"

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
