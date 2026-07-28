"""Abilities actives de la faction TYRANIDS (namespace natif `Abilities.Active.Loki.*`) -- port isole (case-220 §6.16).

Module DEDIE a la faction Tyranids (comme `necrons.py`/`sisterhood.py`/`votann.py` : une classe par ability,
l'arbre SPECIFIQUE vit avec sa classe). Les abilities Tyranides HISTORIQUES (CrushingClaws 1105, SpiritLeech
1104, ScythingTalons 1065...) vivent dans le package `loki/` ; ce fichier accueille les nouveaux ports
case-220. RE ghidra gqfc5mff6c (VA citees). Doc : docs/rl/case-220/tyranids.md §6.16.

Contenu :
- `SporeMineLauncher` (1145, `tyranBiovore` -- Biovore, MachineOfWar) : spawn UN `tyranSmnSporeMine` sur la
  TUILE ciblee par le cast (tile-target), `WithStatsFromConfig` level-scale, SANS on-appearance et SANS cap.
  Corps `IdunBattleLogic.Entities.Abilities.Active.Loki.SporeMineLauncherAbility$$ExecuteBehaviour` = MEME structure Spawn que le corps partage
  `AberrantHypermorph/IronkinSteeljack IdunBattleLogic.Entities.Abilities.Active.Loki.AberrantHypermorphAbility$$ExecuteBehaviour`, MOINS l'on-appearance (`PerformAIAttackFromCurrentPosition`
  ABSENT). Le spore mine spawne est INERTE offline : son passif de detonation `FloatingDeath` (kit summon
  SEPARE, non porte) n'est pas cable -> l'AoE aval = 0 (residu documente, cf. case doc §6.16).
- `AlphaWarrior` (1112, `tyranWingedPrime` -- Winged Prime, unite NORMALE non-MoW) : spawn UN `tyranSmnWarrior`
  sur la TUILE ciblee (tile-target), `WithStatsFromConfig` level-scale, AVEC on-appearance
  `PerformAIAttackFromCurrentPosition` (le summon attaque a l'apparition). Corps
  `IdunBattleLogic.Entities.Abilities.Active.Loki.AlphaWarriorAbility$$ExecuteBehaviour` = MEME structure Spawn+on-appearance que
  `AberrantHypermorph IdunBattleLogic.Entities.Abilities.Active.Loki.AberrantHypermorphAbility$$ExecuteBehaviour` (template EXACT), a TROIS details pres (config AlphaWarrior ; nœud amount
  de `WithStatsFromConfig` = null au lieu de `AbilityLevelAmount(Self)` ; sujet de l'on-appearance =
  `Spawned@0x180` au lieu de `Target@0x178` -- les deux resolvent au MEME summon, cf. MasterOfTheTutelaries).
  Gate de legalite `IsInTeamSynapseRange` (`IdunBattleLogic.Entities.Abilities.Active.Loki.AlphaWarriorAbility$$GetDynamicInvalidTargetReason`) = ciblage live/RPC,
  HORS ExecuteBehaviour -- ABSENT du port COMBAT (IA sur-permissive, residu documente).
"""
from __future__ import annotations

from typing import Optional, TYPE_CHECKING

import gameconfig as GC

from .base import ActiveAbility, convert_rounds_to_turns
from .behaviours import entities_from_state, AddEffect, TriggerAbility
from .targeting import RANGE_SELF, RANGED_BOOL_FALSE, TargetingOptions
from .targeting_rule import TargetingRule as TR
from ..components import OwnerComponent, StatsComponent
from ...dsl.base import Const
from ...entities.active_ability_type import ActiveAbilityType
from ...entities.behaviours import If as IfBehaviour, op_add
from ...entities.effect_type import EffectType
from ...entities.effects.magnitude import ability_var
from ...entities.selectors import (Caster, Enemies, SurroundingUnits,
                                   non_steppable_or_object_units)
from ...entities.triggers import HasUnitFlag, Not
from ...entities.triggered_ability_type import TriggeredAbilityType
from ...dsl.effects import ExecutionContext, AbilityBehaviour, OperationResult

if TYPE_CHECKING:
    from ..state import State


class SpawnSporeMine(AbilityBehaviour):
    """Feuille `Spawn` de `IdunBattleLogic.Entities.Abilities.Active.Loki.SporeMineLauncherAbility$$ExecuteBehaviour` (id 1145, `tyranBiovore`).

    Le corps natif partage la MEME structure Spawn que `AberrantHypermorph/IronkinSteeljack IdunBattleLogic.Entities.Abilities.Active.Loki.AberrantHypermorphAbility$$ExecuteBehaviour`
    (RE croise ci-dessous), il decompile en :
        Execute( Spawn(caster@0x160, TARGET@0x178 = la TUILE ciblee par le cast (tile-target),
                       unitId = GetStringConstant(config, 0) = "tyranSmnSporeMine",
                       SpawnUnitOptions.WithStatsFromConfig(config 1145, Get(param_2[0]), Get(param_2[1]))) )

    DIFFERENCE avec IdunBattleLogic.Entities.Abilities.Active.Loki.AberrantHypermorphAbility$$ExecuteBehaviour (VERIFIE par decompile IdunBattleLogic.Entities.Abilities.Active.Loki.SporeMineLauncherAbility$$ExecuteBehaviour vs IdunBattleLogic.Entities.Abilities.Active.Loki.AberrantHypermorphAbility$$ExecuteBehaviour) : AUCUN
    `PerformAIAttackFromCurrentPosition` et AUCUN `*(options+0x18) = onAppearance` -> le spore mine ne fait
    RIEN a l'apparition (coherent gameconfig : `tyranSmnSporeMine` a `weapons=[]`, `activeAbilities=[]`,
    `summonDmg=0` a tous les niveaux -- son seul passif est `FloatingDeath`, la detonation, NON portee).
    L'amount node de WithStatsFromConfig est retrouve via `DSLFactory.Get(param_2[i])` (pre-enregistre) au
    lieu d'etre construit inline `AbilityLevelAmount(Self)` comme IdunBattleLogic.Entities.Abilities.Active.Loki.AberrantHypermorphAbility$$ExecuteBehaviour -- MEME semantique (le summon
    scale au niveau actif de l'ability du CASTER, via la machinerie identique `SetStatFromConfig`
    summonHp/summonDmg/summonArmor de `IdunBattle.Entities.Behaviours.SpawnUnitOptions$$WithStatsFromConfig`).

    Le placement N'EST PAS un selecteur : la tuile EST la cible du cast (choisie par le joueur/l'IA, legalite
    = `IdunBattleLogic.Entities.Abilities.Active.Loki.SporeMineLauncherAbility$$GetDynamicInvalidTargetReason` : tuile valide ssi PAS occupee par un ennemi -- tuile vide ou
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
    """Arbre de `IdunBattleLogic.Entities.Abilities.Active.Loki.SporeMineLauncherAbility$$ExecuteBehaviour` (id 1145, `tyranBiovore` -- MIRROR 1:1
    du DECOMPILE) :
        Execute( Spawn(caster@0x160, Target@0x178=TUILE, "tyranSmnSporeMine",
                       WithStatsFromConfig(config 1145, Get(param_2[0]), Get(param_2[1]))) )
    UN SEUL noeud `Spawn` (plain `AActiveAbility.Execute`, PAS d'AddEffect, PAS d'op_BitwiseAnd, PAS de
    `.onAppearance`). Count=1 (une seule tuile-cible ; pas de cap). Port : feuille `SpawnSporeMine` (== la
    feuille `SpawnSteeljack`/`SpawnAberrant` avec la config 1145, MOINS l'attaque a l'apparition)."""
    return SpawnSporeMine(tile_id)


class SporeMineLauncherAbility(ActiveAbility):
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.SporeMineLauncherAbility$$ExecuteBehaviour` (id 1145, `tyranBiovore` -- Biovore MachineOfWar,
    namespace natif `Abilities.Active.Loki`). Cast TILE-TARGET (« Launch a spore mine on a target tile ») :
    spawn UN `tyranSmnSporeMine` sur la tuile ciblee, `WithStatsFromConfig` level-scale, SANS on-appearance et
    SANS cap. Pas de triggered, pas d'effet pose sur le caster.

    RE (ghidra gqfc5mff6c) :
    - `IdunBattleLogic.Entities.Abilities.Active.Loki.SporeMineLauncherAbility$$ExecuteBehaviour` : UN `Spawn(caster@0x160, target-tile@0x178, GetStringConstant(config,0),
      WithStatsFromConfig(config, Get(param_2[0]), Get(param_2[1])))` passe a `AActiveAbility.Execute`.
      STRUCTURELLEMENT = le corps partage `AberrantHypermorph/IronkinSteeljack IdunBattleLogic.Entities.Abilities.Active.Loki.AberrantHypermorphAbility$$ExecuteBehaviour`, MOINS le volet
      on-appearance (`PerformAIAttackFromCurrentPosition` + `*(options+0x18)=onAppearance` ABSENTS ici,
      PRESENTS la-bas). C'est la SEULE difference structurelle (verifie par comparaison des deux decompiles).
    - `IdunBattleLogic.Entities.Abilities.Active.Loki.SporeMineLauncherAbility$$.ctor` : `AActiveAbility.ctor(..., 2, 0)` (IDENTIQUE Ironkin/Aberrant -> flags de tour par
      defaut) + `TargetingOptions(0, statsFromClass, 1, 0x40046001042, ...)` (tile-target ; legalite live).
    - `IdunBattleLogic.Entities.Abilities.Active.Loki.SporeMineLauncherAbility$$GetDynamicInvalidTargetReason` : tuile valide ssi PAS occupee par un ennemi (`HasSteppableUnit`
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


class SpawnAlphaWarrior(AbilityBehaviour):
    """Feuille `Spawn` de `IdunBattleLogic.Entities.Abilities.Active.Loki.AlphaWarriorAbility$$ExecuteBehaviour` (id 1112, `tyranWingedPrime`).

    Le corps natif DECOMPILE en (mirror 1:1) :
        Execute( Spawn(caster@0x160, TARGET@0x178 = la TUILE ciblee par le cast (tile-target),
                       unitId = GetStringConstant(config, 0) = "tyranSmnWarrior",
                       SpawnUnitOptions.WithStatsFromConfig(config 1112, amount=null)
                         .onAppearance(+0x18) = PerformAIAttackFromCurrentPosition(Spawned@0x180)) )
    C'est le TEMPLATE EXACT de `SpawnAberrant` (IdunBattleLogic.Entities.Abilities.Active.Loki.AberrantHypermorphAbility$$ExecuteBehaviour, live-valide) -- meme sequence
    `WithStatsFromConfig ; options.onAppearance = PerformAIAttackFromCurrentPosition ; GetStringConstant ;
    Spawn ; AActiveAbility.Execute` -- a TROIS details pres (verifies par comparaison des deux decompiles) :
      1. config = "AlphaWarrior" (unitId `tyranSmnWarrior`).
      2. Le nœud `amount` de `WithStatsFromConfig` est passe NULL (IdunBattleLogic.Entities.Abilities.Active.Loki.AlphaWarriorAbility$$ExecuteBehaviour : `WithStatsFromConfig(config,
         &target, 0, 0, 0)`), la ou IdunBattleLogic.Entities.Abilities.Active.Loki.AberrantHypermorphAbility$$ExecuteBehaviour passe `AbilityLevelAmount(Self@0x148, AbilityType(1166))`. Ce
         nœud alimente la resolution du dynamic-variable-type (`GetDynamicVariableType`) de chaque stat ; le
         LEVEL qui indexe summonHp/summonDmg/summonArmor vient du contexte d'ability du caster (structure
         param_2), PAS de ce nœud -- comme le confirme SporeMineLauncher (IdunBattleLogic.Entities.Abilities.Active.Loki.SporeMineLauncherAbility$$ExecuteBehaviour : amount = `Get(param_2[i])`)
         valide BIT-EXACT vs `_spawn_config_grot(level=active_ability_level)`. -> MEME semantique de scale que
         Aberrant/Spore ; confront LIVE bit-exact (test_alpha_warrior_live).
      3. L'onAppearance vise `Spawned@0x180` (comme MasterOfTheTutelaries IdunBattleLogic.Entities.Abilities.Active.Loki.MasterOfTheTutelariesAbility$$ExecuteBehaviour) la ou Aberrant vise
         `Target@0x178` : les DEUX resolvent au MEME summon (l'unite POSEE sur la tuile-cible = le summon
         fraichement cree, la tuile etant libre AVANT le spawn par la legalite du cast). Outcome identique.

    Le placement N'EST PAS un selecteur : la tuile EST la cible du cast (choisie par le joueur/l'IA, legalite
    = `IsInTeamSynapseRange`, cf. `IdunBattleLogic.Entities.Abilities.Active.Loki.AlphaWarriorAbility$$GetDynamicInvalidTargetReason` -- ciblage live/RPC HORS de ce
    behaviour, ABSENT du port). -> la feuille porte `tile_id` resolu par la classe. Spawn delegue a l'Operation
    VALIDEE `_spawn_config_grot` (`WithStatsFromConfig` = summonHp/summonDmg/summonArmor[level actif du caster]
    x mult, CopyOwner team+player) puis l'on-appearance `perform_ai_attack_from_current_position(state, gid)`
    (pipeline attaque normale COMPLET, arme par distance : le `tyranSmnWarrior` a une arme melee 3-hit Physical
    et une arme ranged r2 3-hit Bio -> attaque l'ennemi le plus proche a portee). Emet
    'SpawnUnit'/'SummonOnAppearance'. Effet PUR (stop=False)."""
    __slots__ = ("tile_id",)

    def __init__(self, tile_id):
        self.tile_id = tile_id

    def execute(self, entities, ectx):
        from ..operations.spawn import _spawn_config_grot
        from .loki import perform_ai_attack_from_current_position
        state = ectx.state
        caster_id = (entities.caster or {}).get("id")
        if state is None or caster_id is None or self.tile_id is None:
            return OperationResult.ok()
        consts = (GC.ability("AlphaWarrior") or {}).get("constants") or {}
        vid = consts.get("unitId")                       # tyranSmnWarrior (GetStringConstant(config, 0))
        ce = state.get_entity(caster_id)
        coc = ce.get_component(OwnerComponent) if ce is not None else None
        csc = ce.get_component(StatsComponent) if ce is not None else None
        c_ctx = csc.ctx if csc is not None else None
        if vid is None or coc is None or c_ctx is None:
            return OperationResult.ok()
        level = getattr(c_ctx, "active_ability_level", None)   # WithStatsFromConfig scale = niveau actif caster
        mult = int(getattr(c_ctx, "ability_variables_multiplier", 100) or 100)
        gid = _spawn_config_grot(state, vid, self.tile_id, "AlphaWarrior", level, mult,
                                 coc.team, coc.player)
        if gid is None:
            return OperationResult.ok()
        ectx.emit("SpawnUnit", unit=gid)
        att = perform_ai_attack_from_current_position(state, gid)   # onAppearance = PerformAIAttackFromCurrentPosition(Spawned@0x180)
        if att is not None:
            ectx.emit("SummonOnAppearance", summon=gid, target=att["target"], total=att["total"])
        return OperationResult.ok()


def alpha_warrior_tree(tile_id) -> SpawnAlphaWarrior:
    """Arbre de `IdunBattleLogic.Entities.Abilities.Active.Loki.AlphaWarriorAbility$$ExecuteBehaviour` (id 1112, `tyranWingedPrime` -- MIRROR 1:1
    du DECOMPILE) :
        Execute( Spawn(caster@0x160, Target@0x178=TUILE, "tyranSmnWarrior",
                       WithStatsFromConfig(config 1112, amount=null)
                         .onAppearance = PerformAIAttackFromCurrentPosition(Spawned@0x180)) )
    UN SEUL noeud `Spawn` (plain `AActiveAbility.Execute`, PAS `ExecuteAtomic`, PAS d'AddEffect, PAS de
    op_BitwiseAnd -- le noeud top-level passe a Execute EST le Spawn seul). Count=1 (une seule tuile-cible).
    Port : feuille `SpawnAlphaWarrior` (== la feuille `SpawnAberrant` avec la config 1112)."""
    return SpawnAlphaWarrior(tile_id)


class AlphaWarriorAbility(ActiveAbility):
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.AlphaWarriorAbility$$ExecuteBehaviour` (id 1112, `tyranWingedPrime` -- Winged Prime, unite
    NORMALE non-MoW, namespace natif `Abilities.Active.Loki`). Cast TILE-TARGET : spawn UN `tyranSmnWarrior`
    sur la tuile ciblee, `WithStatsFromConfig` level-scale, qui attaque immediatement sans bouger
    (`PerformAIAttackFromCurrentPosition`). Pas de triggered, pas d'effet pose sur le caster.

    RE (ghidra gqfc5mff6c) :
    - `IdunBattleLogic.Entities.Abilities.Active.Loki.AlphaWarriorAbility$$ExecuteBehaviour` : UN `Spawn(caster@0x160, target-tile@0x178, GetStringConstant(config,0)=
      "tyranSmnWarrior", WithStatsFromConfig(config, amount=null))` avec `options.onAppearance(+0x18) =
      PerformAIAttackFromCurrentPosition(Spawned@0x180)`, passe a `AActiveAbility.Execute`. STRUCTURELLEMENT =
      `AberrantHypermorph IdunBattleLogic.Entities.Abilities.Active.Loki.AberrantHypermorphAbility$$ExecuteBehaviour` (template EXACT Spawn+on-appearance), a trois details pres (config
      AlphaWarrior ; nœud amount null ; sujet on-appearance `Spawned@0x180` -- cf. `SpawnAlphaWarrior`).
    - `IdunBattleLogic.Entities.Abilities.Active.Loki.AlphaWarriorAbility$$.ctor` : `AActiveAbility.ctor(..., 2, 0)` (IDENTIQUE Ironkin/Aberrant/Spore -> flags de tour
      par defaut) + `TargetingOptions(0, statsFromClass, 1, 0x6001052, ...)` (tile-target ; legalite live).
    - `IdunBattleLogic.Entities.Abilities.Active.Loki.AlphaWarriorAbility$$GetDynamicInvalidTargetReason` -> `IdunBattleLogic.Entities.Abilities.Active.Loki.AlphaWarriorAbility$$IsInSynapseRange` ->
      `DSLFactory.IsInTeamSynapseRange` : tuile valide ssi DANS la portee synapse de l'equipe (raison 2 sinon).
      Gate live/RPC (ciblage), HORS ExecuteBehaviour -> ABSENT du port COMBAT : l'IA offline est SUR-PERMISSIVE
      (peut cibler hors synapse), residu documente (comme SporeMineLauncher/obscuring).

    La behaviour EST l'arbre DSL `alpha_warrior_tree(tile_id)` (feuille `SpawnAlphaWarrior`). La feuille
    delegue le SPAWN a l'Operation VALIDEE `_spawn_config_grot` (tyranSmnWarrior team/player du caster, stats
    summonHp/summonDmg/summonArmor[level actif] x mult) puis l'on-appearance (le summon attaque l'ennemi le
    plus proche a portee) -- MEME spawn+attaque que Aberrant/MasterOfTheTutelaries (live-valides).

    `target_id` = id de TUILE (cast tile-target, abilityTargets kind="tile"). Un target_id qui n'est pas une
    tuile du board -> Spawn no-op (diag `spawned=[]`).

    Flags de tour : defauts base (1112 absent de `NO_END_TURN_ABILITY_TYPES`/`NO_ABILITY_USED_FLAG_ABILITY_TYPES`
    -> `SetsEndTurnFlags`/`SetsActiveAbilityUsedFlag` = True, coherent `.ctor(..., 2, 0)`) -> l'ability TERMINE
    le tour du caster + pose ActiveAbilityUsed (identique Aberrant)."""
    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.AlphaWarrior)  # 1112
    ABILITY_ID = "AlphaWarrior"

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        board = state.board
        tile_id = target_id if (board is not None and target_id in board.by_id) else None
        ectx = ExecutionContext(state=state, rng=state.rng)
        alpha_warrior_tree(tile_id).execute(entities_from_state(state, caster_id), ectx)
        spawned = [p["unit"] for n, p in ectx.emitted if n == "SpawnUnit"]
        attacks = [{"summon": p["summon"], "target": p["target"], "total": p["total"]}
                   for n, p in ectx.emitted if n == "SummonOnAppearance"]
        return {"summon": "tyranSmnWarrior", "spawned": spawned, "attacks": attacks,
                "tile": tile_id, "dsl": True}


# ================== FearOfTheUnseen (Deathleaper `tyranDeathleaper`, actif 1115) ==================
#
# Indices de config (`AbilityConfiguration.Get*`) lus au decompile de
# `IdunBattleLogic.Entities.Abilities.Active.Loki.FearOfTheUnseenAbility$$ExecuteBehaviour` :
FEAR_CONST_RANGE = 0x16                 # GetNumberConstant(0x16) -> `constants.range` = 2
FEAR_PINNED = int(EffectType.Pinned)                                  # 0x429 = 1065 (UI "Suppressed")
FEAR_TELEPORTING_IN = int(EffectType.FearOfTheUnseen_TeleportingIn)   # 0x4d6 = 1238
FEAR_EXTRA_DAMAGE = int(EffectType.FearOfTheUnseen_ExtraDamage)       # 0x4d7 = 1239
FEAR_BATTLE_FATIGUE = int(TriggeredAbilityType.BattleFatigue)         # 0x401 = 1025
UNIT_FLAG_MOVED = 0                     # `IdunBattle.Entities.Enum.UnitFlag.Moved`


def fear_of_the_unseen_enemies_selector(range_val: int):
    """Selecteur des ennemis affectes -- MIRROR 1:1 du 1er etage de
    `IdunBattleLogic.Entities.Abilities.Active.Loki.FearOfTheUnseenAbility$$ExecuteBehaviour`
    (identique dans son jumeau `$$SuppressAndTriggerBattleFatigue`) :

        SurroundingUnits(Self@0x148, GetNumberConstant(0x16 = range), unique=1, includeCenter=1, sel=3)
        |> NonSteppableOrObjectUnits(., 3)
        |> Enemies(Self@0x148, ., 3)

    - `includeCenter = 1` -> le DISQUE inclut la tuile du caster ; le `Enemies` qui suit l'evacue de
      toute facon (team != Self), donc l'observable est "les ennemis a distance hex <= range".
    - `NonSteppableOrObjectUnits` = `(src & UnitsWithoutTrait(src, 0x1b Steppable)) &
      UnitsWithoutTrait(src, 0xd Object)` : ni decoy/mine traversable, ni objet de plateau.
    - i2 : "all enemies within 2 hexes get Suppressed and trigger Battle Fatigue, if they have it"."""
    return Enemies(non_steppable_or_object_units(
        SurroundingUnits(Caster(), Const(range_val), include_center=True)))


def fear_of_the_unseen_tree(range_val: int, self_effect_turns: int):
    """Arbre COMPLET de
    `IdunBattleLogic.Entities.Abilities.Active.Loki.FearOfTheUnseenAbility$$ExecuteBehaviour`
    -- MIRROR 1:1 du DECOMPILE :

        notMoved = op_LogicalNot( HasFlag(Self@0x148, 0 = Moved) )
        enemies  = <fear_of_the_unseen_enemies_selector>
        trigger  = TriggerAbility(enemies, 0x401 = BattleFatigue, actor@0x158, caster@0x160,
                                  target@0x178, unitFeetTiles = null, selectionType = 3,
                                  ignoreUnitHavingAbility = false)
        suppress = AddEffect(0x429 = Pinned, abilityStateRef, source = caster@0x160, targets = enemies,
                             options = <struct ZERO-initialisee>)
        Execute( ( If(notMoved, suppress op_Addition trigger, null)
                   op_Addition AddEffect(0x4d6 TeleportingIn, stateRef, Self@0x148, turns) )
                 op_Addition AddEffect(0x4d7 ExtraDamage,   stateRef, Self@0x148, turns) )

    avec, pour LES DEUX effets self, `turns = Sum(TurnsFromRounds(1), Direct(1))`.

    POINTS DE FIDELITE :
    - **`Execute` PLAIN, pas `ExecuteAtomic`** (contraste DoomSiren 0x2a) -- aucun groupe atomique.
    - **Le gate `!Moved` ne couvre QUE le volet ennemis** (suppress + BattleFatigue). Les DEUX effets
      SELF sont poses INCONDITIONNELLEMENT : ils sont a l'EXTERIEUR du `If` dans l'arbre natif.
      L'i2 ("If the Deathleaper has not moved this turn ...") ne decrit que le premier volet.
    - **Duree des effets self** : `Sum(TurnsFromRounds(1), Direct(1))` -- le `TurnsFromRounds(1)` est
      converti par `IdunBattle.Core.Services.BattleQuery$$ConvertRoundsToTurns` (#98, facteur = nb de
      joueurs non-Environment), PUIS `+1` en TOURS. Le port FOLDE ce noeud VALEUR (RNG-libre,
      state-only) au moment du cast et passe le resultat en `duration_turns` (deja en tours, donc NON
      reconverti par `_resolve_duration`).
    - **`AddEffect(Pinned)` sans noeud de duree** (le 5e argument natif est une struct d'options
      ZERO-initialisee, PAS un `TurnsFromRounds`) -> duree DEFAUT `DefaultAmountOfRounds(1065)`,
      exactement comme le Pinned de CrushingClaws. D'ou `duration_rounds=None`.
    - **`scale_from_source` sur 1239** : sa magnitude vient de `ConfigVar(minDmg/maxDmg,
      AbilityStateFromEffect)` -> l'effet doit resoudre ses variables contre le niveau d'ability et le
      multiplier de rarete du POSEUR (meme canal que FleshmetalGuns/TerrifyingCrescendo).

    `range_val` = `GetNumberConstant(config, 0x16)` resolu par la classe ; `self_effect_turns` = le
    `Sum(TurnsFromRounds(1), Direct(1))` deja folde."""
    enemies = fear_of_the_unseen_enemies_selector(range_val)
    suppress = AddEffect(FEAR_PINNED, "Pinned", enemies, duration_rounds=None)
    trigger = TriggerAbility(enemies, FEAR_BATTLE_FATIGUE)
    not_moved = Not(HasUnitFlag(Caster(), UNIT_FLAG_MOVED))
    volet_ennemis = IfBehaviour(not_moved, op_add(suppress, trigger))
    teleporting = AddEffect(FEAR_TELEPORTING_IN, "FearOfTheUnseen_TeleportingIn", Caster(),
                            duration_rounds=None, duration_turns=self_effect_turns)
    extra_damage = AddEffect(FEAR_EXTRA_DAMAGE, "FearOfTheUnseen_ExtraDamage", Caster(),
                             duration_rounds=None, duration_turns=self_effect_turns,
                             scale_from_source=True)
    return op_add(op_add(volet_ennemis, teleporting), extra_damage)


class FearOfTheUnseenAbility(ActiveAbility):
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.FearOfTheUnseenAbility$$ExecuteBehaviour`
    (id 1115, `tyranDeathleaper` "Deathleaper", HERO Tyranids).

    i2 : "If the Deathleaper has not moved this turn and is not in Deep Strike, all enemies within
    {range} hexes get Suppressed and trigger Battle Fatigue, if they have it. The Deathleaper vanishes
    and cannot be targeted or damaged for 1 round. In its next turn, its attacks deal an additional
    {nrOfHits}x {minDmg}-{maxDmg} Direct Damage [...]"

    LE CAST NE FAIT AUCUN DEGAT. C'est un POSEUR D'EFFETS pur (meme famille que les MoW effect-posers,
    cf. `docs/rl/case-90-mow-effect-posers.md`) : le DirectDamage annonce par la config 1115 vit dans
    la PHASE 2, l'effet `FearOfTheUnseen_ExtraDamage` (1239), qui declare des COUPS ADDITIONNELS sur
    les attaques MELEE du porteur via le canal #179 (`IdunBattle.Entities.Effects.Loki.
    FearOfTheUnseen_ExtraDamageEffect$$CreateAdditionalHits` -> `EffectAdditionalHits$$Create`).
    Cf. `engine/entities/effects/loki/hits.py::FearOfTheUnseenExtraDamageEffect`.

    Arbre : `fear_of_the_unseen_tree` (mirror 1:1, cf. sa docstring).

    RESIDUS NOMMES (hors ExecuteBehaviour, donc hors de ce port) :
      * `FearOfTheUnseen_TeleportingIn` (1238) est POSE (l'effet existe sur le porteur, diffable) mais
        reste un `BaseEffect` nu : sa mecanique -- untargetable + teleport libre au tour suivant, base
        native `BlockUnitMovementEffect`, `$$GetMovingEffectType` -> 0x4d9 = 1241
        `FearOfTheUnseen_Moving`, `$$GetAdditionalRemoveTriggers` = `AmountIsEqual(EffectRemainingTurns
        (Effect@0x150), dsl@0xc0 = 1)`, et le pathfinder dedie
        `IdunBattle.Entities.Pathfinding.FearOfTheUnseenPathfinder$$IsValidTeleportTile` -- est un
        sous-systeme MOUVEMENT separe, non porte.
      * `$$GetDynamicInvalidCasterReason` = `IsTeleporting(caster) ? 4 : 0` : cette regle-delegue
        CASTER n'est PAS invoquee par la cascade de REFUS (le bit `CasterMatchesDynamicRule` 0x4
        n'est pas dans le masque), elle l'est par le constructeur de LISTE de cibles via
        `AddCasterIfMatchesDynamicRule` (0x8), etage non porte (`get_caster_not_added_reason` rend 0,
        permissif documente). Consequence : offline, un cast depuis le Deep Strike n'est pas refuse
        alors que le natif le refuse -- ecart du cote PERMISSIF, nomme.
      * Le `Maybe(GetFleeChance)` de `BattleFatigueAbility$$CreateBehaviour` garde son residu
        pre-existant : la feuille `TriggerAbility` (behaviours/lifecycle.py) RESOUT et TRACE le set
        declenche mais ne DISPATCHE pas 1025 -- `GetFleeChance` lit une `AbilityConfiguration` absente
        du gameconfig, donc dispatcher ferait fuir 0 % ou 100 % des cibles la ou le natif tire une
        piece. Meme residu que la voie trigger-sur-mort (`runner/operations/behaviour.py`)."""
    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.FearOfTheUnseen)   # 1115
    ABILITY_ID = "FearOfTheUnseen"

    # GATE DE CIBLE (#115). `IdunBattleLogic.Entities.Abilities.Active.Loki.FearOfTheUnseenAbility$$.ctor`
    # appelle l'overload FLAGS DIRECTS (aucun preset statique) :
    #     TargetingOptions..ctor(&opts, 1, &range, 1, 0x18, 0, 0, 0)
    # soit `isSelfCasting = 1`, `range = <copie de TargetingRange statics+0x60>`,
    # `forceMeleeTarget = 1` (RangedBool.False), `Rules = 0x18`, les deux regles-delegues a 0
    # (elles sont ECRASEES juste apres par `AActiveAbility..ctor`).
    #   TargetingRange statics+0x60 = `RANGE_SELF` (`overrideRange = 0`) -> portee NULLE, coherent
    #   avec un self-cast (la config 1115 n'a pas d'`attackRangeType`).
    #   Rules 0x18 = `AddCasterIfMatchesDynamicRule` (0x8) | `CasterHasNotMoved` (0x10).
    #     - 0x10 est PORTE (`get_invalid_caster_reason`) : un caster qui a BOUGE ce tour ne peut plus
    #       caster -- pendant "gate de legalite" du `If(!HasFlag(Moved))` interne a la behaviour.
    #     - 0x8 route le verdict vers `GetCasterNotAddedReason`, non porte (cf. les residus ci-dessus).
    TARGETING_OPTIONS = TargetingOptions(
        rules=TR.AddCasterIfMatchesDynamicRule | TR.CasterHasNotMoved,
        self_cast=True, range=RANGE_SELF, force_melee_target=RANGED_BOOL_FALSE)

    def _range(self) -> int:
        """`GetNumberConstant(config, 0x16)` = `constants.range` (CONSTANTE, pas une variable par
        niveau). Defaut 1 si absente (aucune portee inventee)."""
        return int(ability_var(self.ABILITY_ID, "range", is_constant=True) or 1)

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        # `Sum(TurnsFromRounds(1), Direct(1))` folde ICI (noeud VALEUR pur : aucun rng, seul le nb de
        # joueurs du tour-order entre en jeu) -> duree deja exprimee en TOURS.
        turns = convert_rounds_to_turns(state, 1) + 1
        entities = entities_from_state(state, caster_id, target_id)
        ectx = ExecutionContext(state=state, rng=state.rng)
        fear_of_the_unseen_tree(self._range(), turns).execute(entities, ectx)
        posed = [{"unit": p.get("target"), "effect": p.get("effect_type"), "placed": p.get("placed")}
                 for n, p in ectx.emitted if n == "AddEffect"]
        # `TriggerAbility` emet `targets` (le SET declenche) + `dispatched` — cf. sa docstring dans
        # `behaviours/lifecycle.py` : `BattleFatigue` n'est volontairement PAS dispatchee (sa chance de
        # fuite n'a aucune source offline), on ne trace donc que les unites concernees.
        fatigue = [t for n, p in ectx.emitted if n == "TriggerAbility"
                   for t in (p.get("targets") or [])]
        return {"ability": "FearOfTheUnseen", "caster": caster_id, "target": target_id,
                "effects": posed, "battle_fatigue": fatigue, "self_effect_turns": turns, "dsl": True}

