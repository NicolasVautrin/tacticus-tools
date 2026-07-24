"""Abilities actives de la faction TYRANIDS (namespace natif `Abilities.Active.Loki.*`) -- port isole (case-220 §6.16).

Module DEDIE a la faction Tyranids (comme `necrons.py`/`sisterhood.py`/`votann.py` : une classe par ability,
l'arbre SPECIFIQUE vit avec sa classe). Les abilities Tyranides HISTORIQUES (CrushingClaws 1105, SpiritLeech
1104, ScythingTalons 1065...) vivent dans le package `loki/` ; ce fichier accueille les nouveaux ports
case-220. RE ghidra gqfc5mff6c (VA citees). Doc : docs/rl/case-220/tyranids.md §6.16.

Contenu :
- `SporeMineLauncher` (1145, `tyranBiovore` -- Biovore, MachineOfWar) : spawn UN `tyranSmnSporeMine` sur la
  TUILE ciblee par le cast (tile-target), `WithStatsFromConfig` level-scale, SANS on-appearance et SANS cap.
  Corps `SporeMineLauncherAbility.ExecuteBehaviour @18120a3f0` = MEME structure Spawn que le corps partage
  `AberrantHypermorph/IronkinSteeljack @1811b0550`, MOINS l'on-appearance (`PerformAIAttackFromCurrentPosition`
  ABSENT). Le spore mine spawne est INERTE offline : son passif de detonation `FloatingDeath` (kit summon
  SEPARE, non porte) n'est pas cable -> l'AoE aval = 0 (residu documente, cf. case doc §6.16).
"""
from __future__ import annotations

from typing import Optional, TYPE_CHECKING

import gameconfig as GC

from .base import ActiveAbility
from .behaviours import entities_from_state
from ..components import OwnerComponent, StatsComponent
from ...entities.active_ability_type import ActiveAbilityType
from ...dsl.effects import ExecutionContext, AbilityBehaviour, OperationResult

if TYPE_CHECKING:
    from ..state import State


class SpawnSporeMine(AbilityBehaviour):
    """Feuille `Spawn` de `SporeMineLauncherAbility.ExecuteBehaviour @18120a3f0` (id 1145, `tyranBiovore`).

    Le corps natif partage la MEME structure Spawn que `AberrantHypermorph/IronkinSteeljack @1811b0550`
    (RE croise ci-dessous), il decompile en :
        Execute( Spawn(caster@0x160, TARGET@0x178 = la TUILE ciblee par le cast (tile-target),
                       unitId = GetStringConstant(config, 0) = "tyranSmnSporeMine",
                       SpawnUnitOptions.WithStatsFromConfig(config 1145, Get(param_2[0]), Get(param_2[1]))) )

    DIFFERENCE avec @1811b0550 (VERIFIE par decompile @18120a3f0 vs @1811b0550) : AUCUN
    `PerformAIAttackFromCurrentPosition` et AUCUN `*(options+0x18) = onAppearance` -> le spore mine ne fait
    RIEN a l'apparition (coherent gameconfig : `tyranSmnSporeMine` a `weapons=[]`, `activeAbilities=[]`,
    `summonDmg=0` a tous les niveaux -- son seul passif est `FloatingDeath`, la detonation, NON portee).
    L'amount node de WithStatsFromConfig est retrouve via `DSLFactory.Get(param_2[i])` (pre-enregistre) au
    lieu d'etre construit inline `AbilityLevelAmount(Self)` comme @1811b0550 -- MEME semantique (le summon
    scale au niveau actif de l'ability du CASTER, via la machinerie identique `SetStatFromConfig`
    summonHp/summonDmg/summonArmor de `WithStatsFromConfig @180fd65b0`).

    Le placement N'EST PAS un selecteur : la tuile EST la cible du cast (choisie par le joueur/l'IA, legalite
    = `GetDynamicInvalidTargetReason @18120a590` : tuile valide ssi PAS occupee par un ennemi -- tuile vide ou
    alliee OK ; abilityTargets kind="tile"). -> la feuille porte `tile_id` resolu par la classe. Spawn delegue
    a l'Operation VALIDEE `_spawn_config_grot` (`WithStatsFromConfig` = summonHp/summonDmg/summonArmor[level
    actif du caster] x mult, CopyOwner team+player du caster) -- EXACTEMENT le meme spawn que Ironkin/Aberrant/
    ScarabHive (live-valides), MOINS l'attaque a l'apparition.

    Emet 'SpawnUnit'. Effet PUR (stop=False)."""
    __slots__ = ("tile_id",)

    def __init__(self, tile_id):
        self.tile_id = tile_id

    def execute(self, entities, ectx):
        from ..operations.spawn import _spawn_config_grot
        state = ectx.state
        caster_id = (entities.caster or {}).get("id")
        if state is None or caster_id is None or self.tile_id is None:
            return OperationResult.ok()
        consts = (GC.ability("SporeMineLauncher") or {}).get("constants") or {}
        vid = consts.get("unitId")                       # tyranSmnSporeMine (GetStringConstant(config, 0))
        ce = state.get_entity(caster_id)
        coc = ce.get_component(OwnerComponent) if ce is not None else None
        csc = ce.get_component(StatsComponent) if ce is not None else None
        c_ctx = csc.ctx if csc is not None else None
        if vid is None or coc is None or c_ctx is None:
            return OperationResult.ok()
        level = getattr(c_ctx, "active_ability_level", None)   # WithStatsFromConfig amount = niveau actif caster
        mult = int(getattr(c_ctx, "ability_variables_multiplier", 100) or 100)
        gid = _spawn_config_grot(state, vid, self.tile_id, "SporeMineLauncher", level, mult,
                                 coc.team, coc.player)
        if gid is None:
            return OperationResult.ok()
        ectx.emit("SpawnUnit", unit=gid)
        return OperationResult.ok()


def spore_mine_launcher_tree(tile_id) -> SpawnSporeMine:
    """Arbre de `SporeMineLauncherAbility.ExecuteBehaviour @18120a3f0` (id 1145, `tyranBiovore` -- MIRROR 1:1
    du DECOMPILE) :
        Execute( Spawn(caster@0x160, Target@0x178=TUILE, "tyranSmnSporeMine",
                       WithStatsFromConfig(config 1145, Get(param_2[0]), Get(param_2[1]))) )
    UN SEUL noeud `Spawn` (plain `AActiveAbility.Execute`, PAS d'AddEffect, PAS d'op_BitwiseAnd, PAS de
    `.onAppearance`). Count=1 (une seule tuile-cible ; pas de cap). Port : feuille `SpawnSporeMine` (== la
    feuille `SpawnSteeljack`/`SpawnAberrant` avec la config 1145, MOINS l'attaque a l'apparition)."""
    return SpawnSporeMine(tile_id)


class SporeMineLauncherAbility(ActiveAbility):
    """`SporeMineLauncherAbility.ExecuteBehaviour @18120a3f0` (id 1145, `tyranBiovore` -- Biovore MachineOfWar,
    namespace natif `Abilities.Active.Loki`). Cast TILE-TARGET (« Launch a spore mine on a target tile ») :
    spawn UN `tyranSmnSporeMine` sur la tuile ciblee, `WithStatsFromConfig` level-scale, SANS on-appearance et
    SANS cap. Pas de triggered, pas d'effet pose sur le caster.

    RE (ghidra gqfc5mff6c) :
    - `ExecuteBehaviour @18120a3f0` : UN `Spawn(caster@0x160, target-tile@0x178, GetStringConstant(config,0),
      WithStatsFromConfig(config, Get(param_2[0]), Get(param_2[1])))` passe a `AActiveAbility.Execute`.
      STRUCTURELLEMENT = le corps partage `AberrantHypermorph/IronkinSteeljack @1811b0550`, MOINS le volet
      on-appearance (`PerformAIAttackFromCurrentPosition` + `*(options+0x18)=onAppearance` ABSENTS ici,
      PRESENTS la-bas). C'est la SEULE difference structurelle (verifie par comparaison des deux decompiles).
    - `ctor @18120a610` : `AActiveAbility.ctor(..., 2, 0)` (IDENTIQUE Ironkin/Aberrant -> flags de tour par
      defaut) + `TargetingOptions(0, statsFromClass, 1, 0x40046001042, ...)` (tile-target ; legalite live).
    - `GetDynamicInvalidTargetReason @18120a590` : tuile valide ssi PAS occupee par un ennemi (`HasSteppableUnit`
      + `IsEnemy` -> raison 2 si ennemi ; tuile vide ou unite alliee = 0/valide). Gate live/RPC.

    La behaviour EST l'arbre DSL `spore_mine_launcher_tree(tile_id)` (feuille `SpawnSporeMine`). La feuille
    delegue le SPAWN a l'Operation VALIDEE `_spawn_config_grot` (tyranSmnSporeMine team/player du caster, stats
    summonHp/summonDmg/summonArmor[level actif] x mult) -- MEME spawn que les summons frere live-valides.

    ⚠ RESIDU DOCUMENTE (case doc §6.16) : le spore mine est INERTE offline. Son passif de detonation
    `FloatingDeath` (kit summon SEPARE, Toxic, non porte) n'est pas cable -> l'ability EXECUTE (le mine
    apparait, avec ses PV summonHp[level]) mais l'AoE aval = 0. `tyranSmnSporeMine` n'ayant NI arme NI ability
    active (summonDmg=0), le summon ne fait rien d'observable a part exister (trait InstinctiveBehaviour ->
    mouvement instinctif non porte non plus). Le port de FloatingDeath = tache summon-downstream separee.

    `target_id` = id de TUILE (cast tile-target, abilityTargets kind="tile"). Un target_id qui n'est pas une
    tuile du board -> Spawn no-op (diag `spawned=[]`).

    Flags de tour : defauts base (1145 absent de `NO_END_TURN_ABILITY_TYPES`/`NO_ABILITY_USED_FLAG_ABILITY_TYPES`
    -> `SetsEndTurnFlags`/`SetsActiveAbilityUsedFlag` = True) -> l'ability TERMINE le tour du caster + pose
    ActiveAbilityUsed (identique Ironkin)."""
    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.SporeMineLauncher)  # 1145
    ABILITY_ID = "SporeMineLauncher"

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        board = state.board
        tile_id = target_id if (board is not None and target_id in board.by_id) else None
        ectx = ExecutionContext(state=state, rng=state.rng)
        spore_mine_launcher_tree(tile_id).execute(entities_from_state(state, caster_id), ectx)
        spawned = [p["unit"] for n, p in ectx.emitted if n == "SpawnUnit"]
        return {"summon": "tyranSmnSporeMine", "spawned": spawned, "tile": tile_id, "dsl": True}
