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
- `Burrowers` (1023, `tyranSmnRipperSwarm` + 5 `tyranNpc2RipperSwarm*`) -- SELF-CAST : le caster
  QUITTE le plateau (`RemoveUnitFromItsTiles(Caster, true)`) & `RemoveAllForcedAttackTargets(Caster)`
  & `AddEffect(0x410 Burrowers_Hidden -> Caster, PERMANENT)`. 2e appelant de la primitive #366-r1 ;
  tranche 1 du residu `#366-r1-tunnel-family`.
"""
from __future__ import annotations

from typing import Optional, TYPE_CHECKING

import gameconfig as GC

from .base import ActiveAbility, active_ability_state, convert_rounds_to_turns
from .behaviours.combat import AttackWithAttackDamage, InformWeapon
from .behaviours.context import entities_from_state
from .behaviours.effects import AddBondEffect, AddEffect, AddStaticStatModifierEffect
from .behaviours.lifecycle import (
    Kill, RemoveAllForcedAttackTargets, RemoveUnitFromItsTiles, TriggerAbility
)
from .behaviours.movement import (DisplaceUnitInAdjacentDirection, RemoveReservation, Reserve,
                                  ResetMovement)
from .behaviours.summon import PerformAIAttack, Spawn
from .targeting import (RANGE_ADJACENT, RANGE_FROM_CONFIG, RANGE_SELF, RANGE_WHOLE_BOARD,
                        RANGED_BOOL_FALSE, RANGED_BOOL_TRUE, TargetingOptions,
                        has_steppable_unit, unit_of_entity, units_are_enemies)
from .targeting_rule import TargetingRule as TR
from ..components import OwnerComponent, StatsComponent, get_unit_feet, is_teleporting
from ..operations.displace import _dir_index      # foyer de `IBattleQuery` slot 113 `GetVector`
from ...dsl.base import Const
from ...entities.active_ability_type import ActiveAbilityType
from ...entities.behaviours import AtomicGroup, Group, If as IfBehaviour, op_add, op_and
from ...entities.effect_type import EffectType
from ...entities.effects.magnitude import ability_var
from ...entities.selectors.accessors import (ActiveTarget, CasterTile, FixedTileIds, Owner, Target)
from ...entities.formulas import AverageDistance
from ...entities.selectors.geometry import Cache, Entity, PickFirstN
from ...entities.selectors.tiles import (AdjacentTiles, AllAliveUnits, AllTiles, CanAddUnit, Caster,
                                         TileIntersect, TileUnion)
from ...entities.selectors.units import (AdjacentUnits, DeadUnits, Enemies, Friends, SortByFormula,
                                         Sub, SurroundingUnits, Tiles, Units, UnitsFromFaction,
                                         non_steppable_or_object_units)
from ...entities.stats import StatType
from ...entities.triggers import HasUnitFlag, IsInTeamAura, Not
from ...entities.triggered_ability_type import TriggeredAbilityType
from ...entities.unit_selection_type import UnitSelectionType
from ...dsl.effects import ExecutionContext, AbilityBehaviour, OperationResult
from ...entities.ability_constant_type import AbilityConstantType   # #270-r1-r1-r3
from ...streams.group_type import GroupType
from ..operations.spawn import _spawn_config_grot
from .loki import perform_ai_attack_from_current_position

#: `UnitSelectionType` LU au DERNIER argument des `IdunBattleLogic.Entities.DSLSelectors$$*` du lot
#: Hive Tyrant (`Catalyst` : `UnitsFromFaction`/`Friends` ; `StranglethornCannon` : `AdjacentUnits`)
#: -- le litteral natif est `3` aux SIX call-sites.
SELECTION = int(UnitSelectionType.OnlyAliveAndTargetable)     # 3

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
    # `IdunBattleLogic.Entities.Abilities.Active.Loki.SporeMineLauncherAbility$$.ctor` -- FORME
    # « FLAGS DIRECTS » :
    #   TargetingOptions..ctor(&opts, 0, &<TargetingRange statics>+0x48, 1, 0x40046001042, 0, 0, 0)
    #     isSelfCasting    = 0
    #     range            = `TargetingRange` statics+0x48 = RANGE_WHOLE_BOARD
    #     forceMeleeTarget = 1 = RangedBool.False
    #     rules            = 0x40046001042 = TargetMatchesDynamicRule | TargetIsTile | TargetTileIsFree
    #                                      | AllowObscuredTarget | AllowNullCasterTile
    #                                      | TargetIsNotAdjacentToEnemy
    # A comparer avec `SquigMineAbility` (1201, orks.py) = le MEME masque SANS le bit 42
    # `TargetIsNotAdjacentToEnemy` : les deux poses de mine ne se generalisent pas l'une l'autre.
    # Le bit 42 est PORTE depuis #243 (`targeting.py`, `battleQuery` slot 0x7f) : une tuile ayant un
    # ennemi du Biovore sur une de ses voisines marchables est refusee. Regles restees non portees
    # (domaine TILE : `TargetTileIsFree` ; volet caster : `AllowNullCasterTile`) -> permissif.
    TARGETING_OPTIONS = TargetingOptions(rules=(
          TR.TargetMatchesDynamicRule
        | TR.TargetIsTile
        | TR.TargetTileIsFree
        | TR.AllowObscuredTarget
        | TR.AllowNullCasterTile
        | TR.TargetIsNotAdjacentToEnemy),
        range=RANGE_WHOLE_BOARD, force_melee_target=RANGED_BOOL_FALSE)

    def get_dynamic_invalid_target_reason(self, state: "State", caster_id: int,
                                          target_id: Optional[int]) -> int:
        """`IdunBattleLogic.Entities.Abilities.Active.Loki.SporeMineLauncherAbility$$GetDynamicInvalidTargetReason`
        -- MIRROR du decompile, ligne a ligne (#287-r4-r1) :

            if (TileExtensions.HasSteppableUnit(target, state)) {
                unit = UnitExtensions.GetUnit(target, state);
                return UnitExtensions.IsEnemy(unit, caster, state) ? 2 : 0;
            }
            return 0;                       // 2 = TargetingRule.TargetMatchesDynamicRule

        SEMANTIQUE : la tuile est refusee UNIQUEMENT si elle porte une unite `Steppable` ENNEMIE du
        caster. Une tuile vide passe ; une tuile portant un allie steppable passe aussi -- c'est bien
        `IsEnemy` que le natif teste, pas « occupee ». Le premier terme est donc une GARDE : sans
        unite steppable, la regle ne dit rien, quel que soit l'occupant non-steppable.

        ⚠ NE PAS confondre avec le bit 42 `TargetIsNotAdjacentToEnemy` du meme masque, deja porte
        (#243) : celui-la regarde les VOISINES de la tuile et compte tout ennemi ; celle-ci regarde
        la tuile ELLE-MEME et n'y voit que les `Steppable`. Les deux coexistent dans la cascade.

        `IsEnemy(a, b, state)` = `GetCurrentPlayer(a).Player.Team != GetCurrentPlayer(b).Player.Team`
        (rabats a `0` quand un maillon manque) = `units_are_enemies`, et surtout PAS
        `not units_are_friendly` -- cf. la docstring de `units_are_enemies`, qui l'etablit."""
        if target_id is None:
            return 0
        if not has_steppable_unit(state, int(target_id)):
            return 0
        occupant = unit_of_entity(state, int(target_id))
        return (int(TR.TargetMatchesDynamicRule)
                if units_are_enemies(state, occupant, caster_id) else 0)

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
    # `IdunBattleLogic.Entities.Abilities.Active.Loki.AlphaWarriorAbility$$.ctor` -- FORME
    # « FLAGS DIRECTS » :
    #   TargetingOptions..ctor(&opts, 0, &<TargetingRange statics>+0x48, 1, 0x6001052, 0, 0, 0)
    #     isSelfCasting    = 0
    #     range            = `TargetingRange` statics+0x48 = RANGE_WHOLE_BOARD
    #     forceMeleeTarget = 1 = RangedBool.False
    #     rules            = 0x6001052 = TargetMatchesDynamicRule | CasterHasNotMoved | TargetIsTile
    #                                  | TargetTileIsFree | AllowObscuredTarget
    # `CasterHasNotMoved` (0x10) EST porte (volet caster) : le spawn est interdit apres un
    # deplacement du caster. Le domaine TILE et la regle dynamique restent permissifs.
    TARGETING_OPTIONS = TargetingOptions(rules=(
          TR.TargetMatchesDynamicRule
        | TR.CasterHasNotMoved
        | TR.TargetIsTile
        | TR.TargetTileIsFree
        | TR.AllowObscuredTarget),
        range=RANGE_WHOLE_BOARD, force_melee_target=RANGED_BOOL_FALSE)

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
        alpha_warrior_tree(tile_id).execute(entities_from_state(state, caster_id), ectx)
        spawned = [p["unit"] for n, p in ectx.emitted if n == "SpawnUnit"]
        attacks = [{"summon": p["summon"], "target": p["target"], "total": p["total"]}
                   for n, p in ectx.emitted if n == "SummonOnAppearance"]
        return {"summon": "tyranSmnWarrior", "spawned": spawned, "attacks": attacks,
                "tile": tile_id, "dsl": True}

    def get_dynamic_invalid_target_reason(self, state: "State", caster_id: int,
                                          target_id: Optional[int]) -> int:
        """`IdunBattleLogic.Entities.Abilities.Active.Loki.AlphaWarriorAbility$$GetDynamicInvalidTargetReason`
        (1112, `tyranWingedPrime`) -- MIRROR du decompile, qui tient en une ligne :

            return IsInSynapseRange(caster, target) ? 0 : 2;   // TargetMatchesDynamicRule

        et la surcharge d'`IsInSynapseRange` REELLEMENT appelee (celle qui EVALUE ; l'autre se
        contente de FABRIQUER le trigger) :

            trigger = DSLTriggers.IsInTeamSynapseRange( DSLSelectors.Entity(target),
                                                        DSLSelectors.Entity(caster) );
            return trigger.ShouldTrigger( AbilityEntities(caster, caster, target, ...) );

        ⚠ LA SURCHARGE EST TRANCHEE PAR SES XREFS, pas par sa place dans le fichier : les deux
        homonymes ont la MEME signature `(this, caster, target)` et Ghidra ne les distingue que par
        adresse. Celle que `GetDynamicInvalidTargetReason` appelle est celle qui construit les deux
        selecteurs `Entity`, monte l'`AbilityEntities` et invoque le trigger -- la seule des deux qui
        rende un BOOL (l'autre rend l'objet trigger, dont l'octet bas du pointeur n'a aucun sens
        comme predicat).

        L'ETAGE ETAIT DEJA PORTE, et c'est ce qu'il fallait verifier avant d'ecrire quoi que ce soit.
        `DSLTriggers$$IsInTeamSynapseRange(target, team)` n'est PAS un trigger dedie : son corps
        alloue `IdunBattle.Entities.Triggers.IsInAuraRangeTrigger$$.ctor(state, query, 0x41c, target,
        team)` -- le MEME trigger que `DSLTriggers$$IsInTeamContagionsOfNurgleAura`, fige sur un autre
        `EffectType`. Le mirror generique `entities/triggers.py::IsInTeamAura` le porte deja, avec
        son etage de portee (`battle_query.get_in_range_aura_amount`, `entities/effects/aura.py`).
        Seul le CALL-SITE manquait. `0x41c` = `EffectType.Synapse_Effect`.

        SEMANTIQUE, avec le masque `0x6001052` : la TUILE visee doit etre dans la bulle synapse d'une
        unite de l'equipe du caster -- le Winged Prime ne fait apparaitre un Warrior que sous synapse.
        Le volet STATIQUE porte deja `CasterHasNotMoved` et `TargetTileIsFree` ; cette regle-ci ajoute
        la seule contrainte SPATIALE de l'ability (sa portee est `RANGE_WHOLE_BOARD`).

        ⚠ L'ARGUMENT `unit` DU TRIGGER EST LA CIBLE, pas le caster, et le `teamReference` est le
        caster : `IsInTeamSynapseRange(Entity(target), Entity(caster))`, dans cet ordre. Les inverser
        rendrait « le caster est-il dans la synapse de l'equipe de la tuile ? » -- une question dont
        la reponse est presque toujours differente, et jamais fausse assez pour crasher.

        ⚠ LA CIBLE EST UNE TUILE, ET LE ROLE `target` DE L'`AbilityEntities` LA MATERIALISE. Cette
        methode a porte la parade EN LOCAL (#287-r8), parce que le foyer `entities_from_state`
        rendait `None` sur ce role et que l'elargir sans confronter les abilities atteintes aurait
        change leurs arbres a l'aveugle. Depuis #287-r12 le foyer le fait lui-meme : le rayon a ete
        MESURE (`probe_287r12_role_target_tuile.py --rayon`) a **2** abilities (`1017 FragBomb`,
        `1018 ValkyrieStrike`), et les deux ont ete confrontees. Il ne reste donc AUCUNE copie de ce
        dict minimal -- ni ici, ni dans `targeting.py`, ni dans une fonction specialisee.

        Cote natif il n'y a pas d'ecart : le selecteur n'est PAS le role `Target()` mais
        `DSLSelectors$$Entity(<l'entite cible capturee>)` -- un selecteur FERME sur l'entite, que
        l'`AbilityEntities` porte aussi en `+0x178`. Les deux chemins designent la meme entite.

        Cible non resolue -> `0` : le natif y evaluerait le trigger sur un selecteur vide, dont le
        `SelectSingle` rend null et `ShouldTrigger` false, donc `2` ; mais la cascade n'atteint cette
        regle que sur une cible enumeree. Convention permissive du module."""
        if target_id is None:
            return 0
        ents = entities_from_state(state, int(caster_id), int(target_id))
        if ents.target is None:
            return 0                           # ni unite ni tuile du board -> substrat non mesure
        trigger = IsInTeamAura(Entity(Target()), int(EffectType.Synapse_Effect), Entity(Caster()))
        return 0 if trigger.should_trigger(ents) else int(TR.TargetMatchesDynamicRule)


# ================== FearOfTheUnseen (Deathleaper `tyranDeathleaper`, actif 1115) ==================
#
# Indices de config (`AbilityConfiguration.Get*`) lus au decompile de
# `IdunBattleLogic.Entities.Abilities.Active.Loki.FearOfTheUnseenAbility$$ExecuteBehaviour` :
FEAR_CONST_RANGE = AbilityConstantType.range                 # GetNumberConstant(0x16) -> `constants.range` = 2
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
      * `$$GetDynamicInvalidCasterReason` = `IsTeleporting(caster) ? 4 : 0` -- ⚠ FICHE CORRIGEE
        (#447) : ce residu est FERME. La regle-delegue CASTER n'est effectivement PAS invoquee par
        `GetInvalidCasterReason` (le bit `CasterMatchesDynamicRule` 0x4 n'est pas dans le masque) ;
        elle l'est par `TargetingQuery$$GetCasterNotAddedReason` sous
        `AddCasterIfMatchesDynamicRule` (0x8), etage DESORMAIS porte -- cf.
        `targeting.get_caster_not_added_reason` et `get_dynamic_invalid_caster_reason` ci-dessous.
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

    def get_dynamic_invalid_caster_reason(self, state: "State", caster_id: int) -> int:
        """`IdunBattleLogic.Entities.Abilities.Active.Loki.FearOfTheUnseenAbility$$GetDynamicInvalidCasterReason`
        — mirror 1:1 du decompile, qui tient en une ligne :

            return -(uint)(IsTeleporting(caster, state) != 0) & 4;

        soit `IsTeleporting(caster) ? 4 : 0`, et `4` est le litteral
        `TargetingRule.CasterMatchesDynamicRule` (le natif rend le code de la DELEGUE tel quel, cf.
        `targeting.get_caster_not_added_reason`).

        QUI L'INVOQUE : **pas** `GetInvalidCasterReason` -- le masque `0x18` de cette ability ne pose
        PAS le bit `CasterMatchesDynamicRule` (0x4). C'est `TargetingQuery$$GetCasterNotAddedReason`,
        sous le bit `AddCasterIfMatchesDynamicRule` (0x8), atteint parce que 1115 est SELF-CASTEE et
        que la cible du cast est son propre caster.

        CE QUE CA REFUSE, en clair : le cast de `FearOfTheUnseen` pendant que le Deathleaper est en
        **DEEP STRIKE** (`TeleportStrike_TeleportingIn` 0x40b au deploiement, ou
        `FearOfTheUnseen_TeleportingIn` 0x4d6 apres un premier cast). C'est litteralement le « and is
        not in Deep Strike » du texte i2 de l'ability -- l'autre moitie, « has not moved this turn »,
        etant le bit `CasterHasNotMoved` (0x10) du meme masque, deja porte.

        MESURE (#447, `probe_447_add_caster_dynamic_rule.py`, board MC1_67 / seed 777) : au tour de
        deploiement le natif rend **0 cible** pour 1115 (`abilityTargets.fromHere`), et **1** (le
        caster) une fois `TeleportStrike_TeleportingIn` expire. Le port rendait `0` (= valide) dans
        les DEUX regimes : c'est la degradation permissive que ce port ferme."""
        return int(TR.CasterMatchesDynamicRule) if is_teleporting(state, caster_id) else 0

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


# ============== Burrowers (tyranSmnRipperSwarm / tyranNpc2RipperSwarm*, actif 1023) ===============
#
# 2e appelant de la primitive `IdunBattle.Operations.RemoveUnitFromTilesOperation$$Execute` (portee
# par #366-r1 pour `TunnelingHorror` 1011). Les xrefs EXHAUSTIVES de
# `IdunBattleLogic.Entities.DSLBehaviors$$RemoveUnitFromItsTiles` en donnent QUATRE : 1011, 1023,
# `...GrapnelLauncherAbility$$ExecuteBehaviour` (1090) et
# `...StormboyzStrike_TeleportAbility$$CreateBehaviour` (1141). Et celles de
# `...DSLBehaviors$$RemoveAllForcedAttackTargets` en donnent DEUX -- 1011 et 1023, exactement.
#
# ⚠ « JUMEAU EXACT de 1011 » etait l'HYPOTHESE d'entree ; le decompile la REFUTE sur TROIS points,
# et chacun change le port :
#
#   (a) L'ETAGE 3 N'EST PAS UN BOND. 1011 pose `AddBondEffect(0x459, ..., targets: TargetTiles,
#       bondedEntity: Caster)` -- l'effet vit sur la TUILE visee. 1023 appelle la surcharge SANS
#       selecteur SOURCE d'`IdunBattleLogic.Entities.DSLBehaviors$$AddEffect` (5 arguments :
#       `effectType, abilityState, targets, turns`), avec `targets` = le MEME selecteur `<ctx+0x90>
#       +0x30` que les deux etages precedents -> l'effet `0x410 Burrowers_Hidden` vit sur le CASTER.
#   (b) LE GATE EST CASTER, PAS CIBLE. 1011 surcharge `GetDynamicInvalidTargetReason` (2 refus) ;
#       1023 surcharge `GetDynamicInvalidCasterReason` -- une methode DIFFERENTE, armee par un bit
#       DIFFERENT (`CasterMatchesDynamicRule` 0x4 et non `TargetMatchesDynamicRule` 0x2), qui rend le
#       litteral **4** et non **2**.
#   (c) LE MASQUE N'EST PAS DU MEME CTOR. 1011 appelle l'overload FLAGS DIRECTS a 6 arguments
#       (`rules = 0x8000000001042`, cast TILE-TARGET plateau entier) ;
#       `IdunBattleLogic.Entities.Abilities.Active.Loki.BurrowersAbility$$.ctor` n'appelle AUCUN ctor
#       de `TargetingOptions` -- il RECOPIE les 0x40 octets du preset statique `+0x280` (cf. la
#       docstring de `TARGETING_OPTIONS`), donc SELF-CAST portee 0, `rules = 0x8004`.
#
# i2 (`Burrowers`) : « This unit may burrow in its turn, disappearing from the battlefield. In its
# following turn it must surface and may do so in any free hex. If adjacent to an enemy unit, it may
# attack in melee immediately. »
#
# RE complete + mesures live : `docs/rl/case-366-r1-tunneling-horror-pending-summon.md` §5.

BURROWERS_ID = "Burrowers"
BURROWERS_HIDDEN = int(EffectType.Burrowers_Hidden)      # 0x410 = 1040


def burrowers_remove_tree() -> RemoveUnitFromItsTiles:
    """1er des TROIS `IdunBattle.Entities.Abilities.AActiveAbility$$Execute` de
    `IdunBattleLogic.Entities.Abilities.Active.Loki.BurrowersAbility$$ExecuteBehaviour` :

        RemoveUnitFromItsTiles( <selecteur pre-construit du contexte DSL : <ctx+0x90> -> +0x30>,
                                removeTileFromUnit: true )

    MEME appel, MEME champ de contexte et MEME litteral `true` que le 1er etage de
    `...TunnelingHorrorAbility$$ExecuteBehaviour`. Le champ `+0x30` n'est pas nomme dans ce corps ;
    il resout au CASTER -- lecture confirmee par les DEUX autres corps qui le consomment
    (`...BurrowersAbility_Appear$$ExecuteBehaviour` s'en sert comme sujet de son `Kill` et de son
    `RemoveEffect(0x410)`, et la mesure live de 1011 rend `RemoveUnitFromTiles e=<caster>`)."""
    return RemoveUnitFromItsTiles(Caster(), remove_tile_from_unit=True)


def burrowers_forced_targets_tree() -> RemoveAllForcedAttackTargets:
    """2e `Execute` : `RemoveAllForcedAttackTargets(<meme selecteur +0x30>)` = le caster.

    Le porteur reel `tyranSmnRipperSwarm` porte le trait `InstinctiveBehaviour` -- ce 2e etage n'est
    donc PAS decoratif chez lui (contrairement a 1011, dont la mesure live n'a rien emis : la liste
    de cibles forcees du greffon etait vide). Observable des que le caster est sous Taunt ou sous
    `InstinctiveBehaviour` au moment du cast."""
    return RemoveAllForcedAttackTargets(Caster())


def burrowers_hidden_tree() -> AddEffect:
    """3e `Execute`, lu sur la surcharge SANS SOURCE d'`IdunBattleLogic.Entities.DSLBehaviors$$AddEffect`
    (`effectType, abilityState, targets, turns`) :

        AddEffect( 0x410, AbilityStateReference, targets: <ctx+0x90 -> +0x30> = Caster, turns: null )

    TROIS lectures, toutes au decompile :

    * `source_from_target=True` -- la factory passe LITTERALEMENT `0` en 5e argument de
      `IdunBattle.Entities.Behaviours.AddEffectBehaviour$$.ctor` (le selecteur SOURCE). Le fallback
      natif d'`AddEffectBehaviour$$Execute` est alors « la source EST la cible » (cf. la docstring
      d'`AddEffect`). Ici cible == caster, donc source == caster : le resultat coincide avec le
      defaut historique, mais on transcrit la forme NATIVE, pas la coincidence.
    * `duration_rounds=None` / `duration_turns=None` -- l'argument `turns` est un `Nullable<int>`
      VIDE (le ctor passe `0`, `HasValue` faux). Pas d'override -> la duree vient de
      `idun...StaticBattleRules.Effect$$DefaultAmountOfRounds`, dont le switch, RELU en entier, ne
      connait que {5, 0x11, 0x12, 0x3a, 0x4dc, 0x5c4} -> 2, {0x429, 0x48a} -> 1, {0x4f} -> 3.
      **0x410 n'y est pas** (branche `0x3a < t < 0x42a`, `t != 0x4f`, `t != 0x429` -> `return 0` =
      Nullable null) -> `AddEffectOperation` retombe sur `lVar14 = 0` = **PERMANENT**
      (`remaining = 0`). Le retrait est explicite, par le `RemoveEffect(Owner, Nullable(0x410))` de
      `...BurrowersAbility_Appear$$ExecuteBehaviour` (1024, hors perimetre).
    * AUCUNE classe d'effet dediee, et c'est une MESURE, pas un oubli : la table VERSIONNEE
      `data/symbols/rnca9r7q6c/frida/classes.tsv` ne contient AUCUNE classe `Burrowers*Effect`
      (13 lignes `Burrower*`, toutes des `Ability`/`Playbook`/`Visuals`). L'effet natif est donc
      generique -- exactement ce que le port materialise en laissant 1040 hors d'`EFFECT_CLASSES`
      (`EffectFactory` rend un `BaseEffect` nu). Sa mecanique observable est portee AILLEURS : c'est
      le `HasEffect(caster, 0x410)` de `...BurrowersAbility_Appear$$GetDynamicInvalidCasterReason`
      qui la lit, et 1024 n'est pas porte."""
    return AddEffect(BURROWERS_HIDDEN, EffectType.Burrowers_Hidden.name, Caster(),
                     duration_rounds=None, source_from_target=True)


class BurrowersAbility(ActiveAbility):
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.BurrowersAbility$$ExecuteBehaviour` (id 1023,
    `tyranSmnRipperSwarm` « Ripper Swarm », namespace natif `Abilities.Active.Loki`). SELF-CAST.

    TROIS `AActiveAbility$$Execute` SUCCESSIFS (le decompile re-copie les 0x148 octets du contexte
    `entities` AVANT chacun -- meme forme que `TunnelingHorrorAbility`/`WaaaghAbility`), dans cet
    ordre LOAD-BEARING : le caster quitte le plateau AVANT que l'effet ne soit pose, donc au moment
    de la pose la cible de l'`AddEffect` est une unite SANS position. Le port re-materialise
    `entities_from_state` avant chaque etage, comme le natif re-copie son contexte.

      1. `RemoveUnitFromItsTiles(Caster, removeTileFromUnit: true)`
      2. `RemoveAllForcedAttackTargets(Caster)`
      3. `AddEffect(0x410 Burrowers_Hidden, AbilityStateReference, targets: Caster, turns: null)`

    Le caster passe a `pos = null` / `alive = true` : il est HORS PLATEAU, **pas mort**.
    (⚠ `rl_duel` l'affiche « TUE » -- son heuristique lit `hp = null` comme 0 ; faux positif
    d'AFFICHAGE deja documente en #366-r1.)

    PORTEURS ET VOIE DE CONFRONTATION. `unit_map.py find --ability Burrowers` rend **6** unites :
    `tyranSmnRipperSwarm` (SUMMON) et cinq `tyranNpc2RipperSwarm*` (NPC). Le summon a bien DEUX
    invocateurs (`ItItches` et `BarbedOvipositor`, `constants.unitId = tyranSmnRipperSwarm`), mais un
    summon s'OBSERVE et ne se COMMANDE pas (#291) -- pour CONFRONTER un cast on prend le recours 3 de
    `docs/rl/case-92-catalog-injection.md` §5bis : GREFFE de 1023 sur des heros DU POOL. Legitime
    ici, condition VERIFIEE : `gameconfig.ability("Burrowers")` = `{upgrades: null, variables: {}}`
    (aucune variable, aucune constante) et le behaviour ne lit ni stat, ni trait, ni arme du caster
    -- il ne lit que les TUILES du caster.

    L'ability 1024 `Burrowers_Appear` (la resurgence) est hors perimetre : arbre nettement plus gros
    (`Enemies -> AdjacentTiles -> CanAddUnit -> Unique` `Otherwise` `First(SortTilesByUtility(
    CanAddUnit(...), 7))` puis `PerformAIAbility` / `If(!AmountIsEqualOrGreater, MoveUnit)` /
    `If(..., Kill)` / `RemoveEffect(0x410)`), AUCUNE config au gameconfig -- RESIDU NOMME.

    Renvoie {ability, caster, removed_from_tiles, posed, dsl}."""
    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.Burrowers)          # 1023
    ABILITY_ID = BURROWERS_ID

    # GATE DE CIBLE (#115) -- forme de ctor = **PRESET STATIQUE COPIE**, la 3e des trois (meme forme
    # que `GetEmRuntzAbility`, MEME preset). `...BurrowersAbility$$.ctor` n'appelle AUCUN
    # `IdunBattle.Core.Services.TargetingOptions$$.ctor` : il recopie les 0x40 octets du champ
    # STATIQUE de `TargetingOptions` a l'offset RELATIF +0x280 du bloc `<TargetingOptions class>+0xb8`,
    # puis `AActiveAbility..ctor(this, &opts, 2)` (3e argument = 2 = AbilityAttackType.Others).
    # Aucun litteral de masque n'est visible dans le ctor -- le contenu est ecrit par
    # `IdunBattle.Core.Services.TargetingOptions$$.cctor` (bloc statics+0x280), RELU champ par champ
    # (offsets de la struct pris sur l'overload FLAGS DIRECTS de `TargetingOptions$$.ctor`) :
    #     <preset>+0x00 isSelfCasting    = 1
    #     <preset>+0x08 range            <- `TargetingRange` statics+0x60 = RANGE_SELF
    #     <preset>+0x20 forceMeleeTarget = 1 = RangedBool.False
    #     <preset>+0x28 rules            = 0x8004
    #     <preset>+0x30/+0x38 delegues   = 0 (ecrases par `AActiveAbility$$.ctor`)
    # Decomposition EXHAUSTIVE de 0x8004 (0x4 + 0x8000, aucun bit residuel) :
    #     0x4     (bit 2)  CasterMatchesDynamicRule -> regle du volet CASTER, PORTEE ci-dessous.
    #     0x8000  (bit 15) CasterIsPossibleTarget   -> DECLARATIF (lu par
    #                      `TargetingOptions$$get_CanTargetCaster`), jamais une regle de refus.
    # PORTEE : `TargetingRange` statics+0x60 (`TargetingRange$$.cctor` : `+0x60` = 1 -> onlyAdjacent =
    # `RangedBool.False`, `+0x68` = `Nullable(0)` overrideRange, `+0x70` = null) = `RANGE_SELF` ->
    # portee **0** : toute cible autre que le caster est refusee sur `TargetIsInRange`.
    # `isSelfCasting = 1` -> cible == caster : aiguillage `GetCasterNotAddedReason` (non porte -> 0,
    # permissif documente).
    TARGETING_OPTIONS = TargetingOptions(
        rules=TR.CasterMatchesDynamicRule | TR.CasterIsPossibleTarget,
        self_cast=True, range=RANGE_SELF, force_melee_target=RANGED_BOOL_FALSE)

    def get_dynamic_invalid_caster_reason(self, state: "State", caster_id: int) -> int:
        """`IdunBattleLogic.Entities.Abilities.Active.Loki.BurrowersAbility$$GetDynamicInvalidCasterReason`
        -- MIRROR du decompile (la regle-delegue `options+0x30` armee par le bit
        `CasterMatchesDynamicRule` du masque ci-dessus) :

            if (casterTiles != null && casterTiles.<Count>() != 0) {
                foreach (t in casterTiles)
                    if (IdunBattle.Entities.TileExtensions$$IsTemporary(t)) break;   // -> 4
                else return 0;                                                       // aucune temporaire
            }
            return 4;

        Autrement dit DEUX refus, et le litteral rendu est **4** (`CasterMatchesDynamicRule`) -- pas
        **2** comme chez `GetEmRuntz`/`TunnelingHorror` : ce n'est pas une erreur de transcription, le
        natif rend ce code tel quel et `GetInvalidCasterReason` le re-emballe par
        `GenericBrokenTargetingRule(r)`.

        (a) PORTE, mais **PREEMPTE sur le chemin `ActiveAbilityOperation$$ExecuteInternal`** -- et ce
        n'est pas une nuance : c'est la MESURE qui l'a etabli. `casterTiles` VIDE est exactement
        l'etat que le cast lui-meme cree (`RemoveUnitFromItsTiles` -> `feet = []`), donc une unite
        DEJA enfouie ne peut pas re-creuser ; mais le refus RENDU n'est PAS `4`, c'est
        `AllowNullCasterTile` (0x40000000), parce que la clause TUILE-NULLE de
        `IdunBattle.Core.Services.TargetingQuery$$GetInvalidCasterReason` PRECEDE l'invocation de
        cette regle-delegue (cf. `targeting.py::get_invalid_caster_reason`, clause 4a, portee par
        cette meme tranche). Le mirror est conserve tel quel -- le natif porte bien ce test, et le
        rang de la cascade generique n'est pas une propriete de cette ability. Meme forme d'inertie
        que `CasterHasFreeAdjacentTile` chez ses deux porteurs. Le port lit `get_unit_feet` =
        l'equivalent 1:1 d'`IdunBattle.Entities.EntityExtensions$$GetTiles`, que le natif passe en
        `casterTiles`.

        (b) **RESIDU NOMME, identique a celui de 1011** : `IsTemporary` lit le booleen `@+0x2c` du
        `TileComponent`, que le port ne materialise PAS cote RUNNER (`state.board` ne porte que la
        geometrie et `walkable` ; le canal `tileMeta.isTemporary` n'est seede que du cote DECISION,
        cf. `engine/ai/context.py::is_temporary_by_pos`). Degradation PERMISSIVE, jamais un refus
        invente. Pour le fermer il faudrait seeder `isTemporary` dans le board du runner."""
        if state is None or caster_id is None:
            return 0
        if not get_unit_feet(state, int(caster_id)):
            return int(TR.CasterMatchesDynamicRule)          # litteral 4 du decompile
        # (b) `IsTemporary` : non decidable cote runner -> aucun refus (cf. docstring).
        return 0

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        ectx = ExecutionContext(state=state, rng=state.rng)
        # 1) Execute(RemoveUnitFromItsTiles(Caster, true))
        burrowers_remove_tree().execute(entities_from_state(state, caster_id), ectx)
        # 2) Execute(RemoveAllForcedAttackTargets(Caster))
        burrowers_forced_targets_tree().execute(entities_from_state(state, caster_id), ectx)
        # 3) Execute(AddEffect(0x410, ...)) -- `entities` RE-MATERIALISE : le caster n'a plus de tuile.
        burrowers_hidden_tree().execute(entities_from_state(state, caster_id), ectx)
        removed = next((p for n, p in ectx.emitted if n == "RemoveUnitFromItsTiles"), None)
        posed = [{"target": p["target"], "effect": p["effect_type"], "placed": p.get("placed")}
                 for n, p in ectx.emitted if n == "AddEffect"]
        forced = [p["removed"] for n, p in ectx.emitted if n == "RemoveAllForcedAttackTargets"]
        return {"ability": BURROWERS_ID, "caster": caster_id, "target": target_id,
                "removed_from_tiles": removed, "posed": posed, "forced_targets_removed": forced,
                "dsl": True}


# ============== ItItches (Parasite of Mortrex `tyranParasiteOfMortrex`, actif 1121) ===============
#
# ⚠ LA FICHE D'AUDIT DISAIT « SUMMON », ET C'EST VRAI MAIS TRES INCOMPLET (#550). La colonne de
# `docs/rl/combat-ability-coverage.md` derive du `damageProfile` de l'ARME du porteur, pas du
# behaviour. Le decompile de `...ItItchesAbility$$ExecuteBehaviour` est un COMPOSITE de cinq
# mecaniques, dont le summon n'est que la derniere : PIN + POUSSEE VECTORIELLE + ECRASEMENT des
# steppables + RESET du deplacement du caster + SPAWN sur les hex liberes.
#
# i2 (`ItItches`) : « Suppresses and pushes an adjacent enemy unit and all enemy units adjacent to
# both the target and the Parasite of Mortrex one hex backwards. Enemy steppables on affected hexes
# are destroyed. Then summons a Ripper Swarm in each hex vacated by this ability. The Ripper Swarms
# can immediately attack. The Parasite of Mortrex may move again after activating this ability. »
#
# Les cinq propositions du tooltip s'apparient UNE A UNE aux noeuds du decompile, et c'est ce qui a
# permis de valider la lecture : « Suppresses » = `AddEffect(0x429 = Pinned)` ; « pushes ... one hex
# backwards » = `DisplaceUnitInAdjacentDirection(vector = VectorFromAdjacentTo(CasterTile, Tiles(
# Target), 1))` ; « steppables are destroyed » = la tete d'`IdunBattle.Operations.
# DisplaceUnitOperation$$Execute` (`if (IsSteppable(target)) Kill(...)`) suivie du `Kill(DeadUnits)` ;
# « summons ... in each hex vacated » = `Foreach(CanAddUnit(<tuiles des cibles>), t => Spawn(t))` ;
# « may move again » = `ResetMovement(Owner)`.

IT_ITCHES_ID = "ItItches"
IT_ITCHES_PINNED = int(EffectType.Pinned)         # 0x429 = 1065 -- UI « Suppressed »


def _it_itches_selectors(tile_id):
    """Les QUATRE selecteurs partages de `...ItItchesAbility$$ExecuteBehaviour`, construits UNE FOIS
    par cast -- comme le natif, qui alloue ses noeuds au debut du corps et les repasse aux trois
    `Execute`. Rend `(zone, targets, target_tiles)`.

    MIRROR, en remontant les slots `DSLSelectors` (carte LUE dans
    `IdunBattleLogic.Entities.DSLSelectors$$InitializeShared` : `+0x30 Owner · +0x38 Effect ·
    +0x40 Actor · +0x48 Caster · +0x50 CasterTile · +0x58 CasterTiles · +0x60 Target ·
    +0x68 ActiveTarget · ...`) :

        tilesOfTarget = Cache(Tiles(Target@0x60), true)
        targetUnits   = Cache(Enemies(Caster@0x48,
                                      Target@0x60 op_Addition
                                      AdjacentTilesIntersection(CasterTile@0x50, Target@0x60),
                                      UnitSelectionType.OnlyAliveAndTargetable), true)
        targetTiles   = Cache(Tiles(targetUnits), true)

    `targetUnits` est LITTERALEMENT le corps de `...ItItchesAbility$$GetTargetUnits`, et la somme
    `Target + AdjacentTilesIntersection(...)` celui de `$$GetTargetTiles` -- les deux accesseurs
    existent separement parce que le PLAYBOOK les rappelle (`...ItItchesPlaybook$$
    GetAffectedUnitsSelector`), ce qui donne une seconde lecture concordante de la geometrie.
    `AdjacentTilesIntersection(a, b)` n'a pas de noeud dedie cote port : son corps natif EST
    `AdjacentTiles(a) op_BitwiseAnd AdjacentTiles(b)` (relu), donc on ecrit la composition.

    ⚠ **DOMAINE.** Le natif reste en domaine TUILE de bout en bout : `Target` est une entite-TUILE
    (masque `TargetIsTile`), et `IdunBattle.Entities.Selectors.UnitsByTeamSelector$$CountOrAdd`
    resout l'occupant (`GetUnitOrMachine`) pour le TEST `IsFriend` mais ajoute l'ENTITE SOURCE au
    resultat -- donc `Enemies(<tuiles>)` rend des TUILES. Le port passe en domaine UNITE par un
    `Units(...)` EXPLICITE, et l'ecart est de REPRESENTATION, pas de semantique : les consommateurs
    aval (`AddEffectOperation`, `DisplaceUnitOperation`, `KillUnitOperation`) resolvent tous
    l'occupant, et `Tiles(<unite>)` rend sa main tile, c'est-a-dire la tuile de depart. Le seul
    regime ou les deux divergeraient est une unite MULTI-HEX (`Tiles(tuile)` = LA tuile,
    `Tiles(unite)` = sa main tile) -- inatteignable ici, `IsDisplaceable` refusant `BigTarget`.

    ⚠ **LE `Cache` EST LOAD-BEARING**, il n'est pas decoratif : `targets` est relu APRES la poussee
    par `DeadUnits(targets)`, et la poussee TUE les steppables. Sans memoisation, `Units` (qui ne
    rend que des VIVANTS) les aurait deja exclus -> `DeadUnits` vide. cf. la docstring de
    `entities/selectors/units.py::DeadUnits`.

    `tile_id` materialise `Target@0x60` : le cast est TILE-TARGET (`abilityTargets` kind=tile, et la
    face DECISION emet bien un id de TUILE -- `playbook/noncomparable/it_itches.py`)."""
    target = FixedTileIds([tile_id])
    zone = TileUnion(target,                                   # `Target op_Addition ...`
                     TileIntersect(AdjacentTiles(CasterTile(as_ids=True)),   # `AdjacentTilesIntersection`
                                   AdjacentTiles(target)))
    targets = Cache(Enemies(Units(zone)))                      # `Cache(Enemies(Caster, zone, 3))`
    target_tiles = Cache(Tiles(targets, as_ids=True))          # `Cache(Tiles(targetUnits))`
    return zone, targets, target_tiles


def it_itches_tree(tile_id, vector_dir):
    """Les TROIS arbres de `...ItItchesAbility$$ExecuteBehaviour`, dans l'ordre NATIF. Le corps se
    termine par trois appels distincts -- `ExecuteAtomic(...)`, `Execute(...)`, `return Execute(...)`
    -- chacun precede d'une re-copie des 0x148 octets du contexte `entities` (meme forme que
    `BurrowersAbility` ci-dessus). MIRROR :

        [1] ExecuteAtomic( ((AddEffect(0x429 Pinned, AbilityStateReference, source: Caster@0x48,
                                       targets: targetUnits, options: <Nullable VIDE>)
                             op_BitwiseAnd Reserve(Owner@0x30, targetTiles))
                            op_BitwiseAnd DisplaceUnitInAdjacentDirection(
                                Caster@0x48, targetUnits,
                                VectorFromAdjacentTo(CasterTile@0x50, tilesOfTarget, 1)))
                           op_BitwiseAnd RemoveReservation(Owner@0x30, targetTiles),
                           entities, GroupType.Ability_AtomicGroup /* 0x2a */ )

        [2] Execute( ResetMovement(Owner@0x30), entities )

        [3] Execute( Group( ((Reserve(Owner@0x30, targetTiles)
                              op_BitwiseAnd Kill(Caster@0x48, DeadUnits(targetUnits),
                                                 KillUnitBehaviourOptions.ForClearDeadUnits() /*0x100*/))
                             op_BitwiseAnd Foreach(CanAddUnit(targetTiles, Owner@0x30,
                                                              isSteppable: <DSLTriggers+0x48>),
                                                   t => Spawn(Caster@0x48, t, unitId, opts)))
                            op_BitwiseAnd RemoveReservation(Owner@0x30, targetTiles),
                            Owner@0x30, GroupType.Ability_Summon /* 0x22 */ ),
                     entities )

           avec opts = SpawnUnitOptions.WithStatsFromConfig(config 1121, abilityState, null, null)
                       .onAppearance(+0x18) = RemoveReservation(Owner@0x30, Tiles(ActiveTarget@0x68))
                                              op_Addition
                                              PerformAIAbility(ActiveTarget@0x68, <getAbilityType>,
                                                               allowOnlyMove: false,
                                                               overrideMovement: <DSLFormulas+0x18>,
                                                               utilityEntity: null,
                                                               customUtility: null)

    Les deux GroupType sont LUS (`0x2a` / `0x22`), pas deduits, et nommes par le mirror
    `engine/streams/group_type.py`.

    ORDRE LOAD-BEARING : le `Pinned` precede la poussee (le natif compose `op_BitwiseAnd` de gauche a
    droite), et le `ResetMovement` du caster precede le spawn. Les trois blocs sont executes
    INCONDITIONNELLEMENT par le natif (trois appels separes) -- le port les rend separement pour la
    meme raison, plutot que de les chainer par `op_and`, dont le court-circuit `Seq` ne serait
    equivalent que tant qu'aucune feuille ne pose `stop` (elles sont toutes PURES aujourd'hui, mais
    ce n'est pas une propriete de l'arbre, c'est une propriete de ses feuilles).

    `Foreach(sel, t => Spawn(caster, t, ...))` est FOLD en `Spawn(sel, ...)` : la feuille `Spawn` du
    port ITERE son tile-selecteur EN INTERNE (mirror de `IdunBattle.Entities.Behaviours.
    SpawnUnitBehaviour$$Execute`), et le `Foreach` natif fige sa liste AVANT la premiere pose --
    exactement comme le `Spawn` porte fige la sienne. Le lambda `<>c__DisplayClass2_0.
    <ExecuteBehaviour>b__1` ne fait rien d'autre que `Spawn(Caster@0x48, <la tuile>, dc.unitId,
    dc.opts)`, relu ; il ne lit ni `Subject` ni `ActiveTarget`, donc le fold ne perd aucune liaison.

    ⚠ `getAbilityType` EST UNE HYPOTHESE, ET ELLE EST DECLAREE COMME TELLE. Le natif passe une lambda
    de `...ItItchesAbility.<>c` dont le corps (`<ExecuteBehaviour>b__2_0`) est ABSENT des DEUX tables
    de symboles (`frida/methods.tsv` et `ghidra/functions.tsv` du build `rnca9r7q6c`) : IL2CPP l'a
    DEDUPLIQUEE, donc son corps est partage avec un homonyme trivial. Le seul autre producteur de ce
    parametre dans le binaire est `IdunBattleLogic.Entities.DSLBehaviors$$
    PerformAIAttackFromCurrentPosition`, dont la lambda (`DSLBehaviors.<>c`) est ELLE AUSSI absente
    des deux tables, et que le port a deja tranchee en `IdunBattle.Entities.UnitExtensions$$
    GetNormalAttackType` (`loki/summon.py::perform_ai_ability_unit_behaviour`). Les deux `<>c` sont
    des classes de lambda SANS CAPTURE, et `GetNormalAttackType(unit:IEntity)` est justement
    statique a un seul argument -- une lambda sans capture peut l'appeler, et deux corps identiques
    expliquent la deduplication. S'y ajoute que les DEUX call-sites construisent le MEME
    `PerformAIAbilityUnitBehaviour` champ pour champ (`+0x70 = 0`, `+0x78 = <DSLFormulas+0x18>` =
    `Direct(0)`, `+0x80 = null`, `+0x90 = null`) : la seule chose qui les distingue est justement
    cette lambda. Le port prend donc `PerformAIAttack(...)` avec ses defauts, qui sont EXACTEMENT ces
    champs-la. **CONFRONTATION LIVE requise** : si la lambda rendait autre chose (le seul autre
    candidat plausible est `1023 Burrowers`, la seule active du `tyranSmnRipperSwarm`), le Ripper
    Swarm s'enfouirait au lieu d'attaquer -- observable, et c'est le test qui tranche.

    `WithStatsFromConfig(config, abilityState, null, null)` : `ability_state=None` cote port, comme
    `AlphaWarrior`/`SporeMineLauncher` (le niveau vient de l'`active_ability_level` du caster, chemin
    valide live bit-exact par `test_alpha_warrior_live`)."""
    zone, targets, target_tiles = _it_itches_selectors(tile_id)

    # [1] -- le bloc ATOMIQUE : pin, puis poussee, encadres par la (non-)reservation des tuiles.
    atomic = op_and(
        op_and(
            op_and(AddEffect(IT_ITCHES_PINNED, EffectType.Pinned.name, targets,
                             duration_rounds=None),          # options natives = Nullable VIDE
                   Reserve(Owner(), target_tiles)),
            DisplaceUnitInAdjacentDirection(Caster(), targets, vector_dir)),
        RemoveReservation(Owner(), target_tiles))

    # [2] -- « The Parasite of Mortrex may move again after activating this ability. »
    reset = ResetMovement(Owner())

    # [3] -- le bloc SUMMON. `on_appearance` = `SpawnUnitOptions+0x18`, fire PAR summon par
    # `TriggerSpawnedUnitBehaviours` avec `ActiveTarget@0x68` lie au summon fraichement pose.
    on_appearance = op_add(RemoveReservation(Owner(), Tiles(ActiveTarget(), as_ids=True)),
                           PerformAIAttack(ActiveTarget()))     # defauts = les champs natifs, cf. supra
    spawn = Spawn(CanAddUnit(target_tiles, allow_steppable=True), IT_ITCHES_ID,
                  on_appearance=on_appearance)
    group = Group(op_and(op_and(op_and(Reserve(Owner(), target_tiles),
                                       Kill(Caster(), DeadUnits(targets))),
                                spawn),
                         RemoveReservation(Owner(), target_tiles)),
                  group_id=int(GroupType.Ability_Summon),        # 0x22, LU au call-site
                  targets_sel=Owner())
    return atomic, reset, group


class ItItchesAbility(ActiveAbility):
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.ItItchesAbility$$ExecuteBehaviour` (id 1121,
    `tyranParasiteOfMortrex` -- Parasite of Mortrex, namespace natif `Abilities.Active.Loki`).
    Cast TILE-TARGET sur une tuile ADJACENTE occupee par un ennemi.

    Etait un **NO-OP SILENCIEUX** avant #550 : absente d'`ABILITY_CLASSES`, donc
    `AbilityHandler.visit_ActiveAbilityMessage` l'ignorait -- 0 degat, 0 effet, aucune erreur, alors
    que la face DECISION (`playbook/noncomparable/it_itches.py`, deja portee) pouvait la choisir.

    La face COMBAT est l'arbre `it_itches_tree(tile_id, vector_dir)` (trois blocs, cf. sa docstring).
    `vector_dir` est resolu ICI parce que le natif l'obtient d'une FORMULE (`VectorFromAdjacentTo(
    CasterTile@0x50, Cache(Tiles(Target@0x60)), 1)`) dont les deux operandes sont constants sur la
    duree du cast : la tuile du caster (qui n'a pas encore bouge) et la tuile ciblee.

    ⚠ **LA DIRECTION EST LA MEME POUR TOUTES LES CIBLES**, et c'est le point ou ce push differe de
    tous les autres du port. `DisplaceUnitOperation` direction **3** (`AdjacentVector`) applique le
    vecteur `casterTile -> tuile ciblee` a CHAQUE unite poussee, la ou `FindTileToPush`
    (direction 0) recalculerait `pousseur -> poussee` par cible. Sur un ennemi lateral (adjacent a
    la fois au caster et a la cible, mais pas dans l'axe), les deux geometries donnent des tuiles
    DIFFERENTES -- c'est exactement le « one hex backwards » du tooltip, un balayage coherent et non
    un ecartement radial.

    RESIDUS NOMMES :
    - `Reserve`/`RemoveReservation` (QUATRE occurrences) sont des NO-OP portes : le port n'a aucun
      modele de reservation de tuile (deja nomme par `CanAddUnit`). Ils journalisent, pour que
      l'arbre reste confrontable au decompile et que le rang soit tenu.
    - `Kill(Caster, DeadUnits(targetUnits), ForClearDeadUnits)` est un NO-OP STRUCTUREL cote port,
      au meme titre que `KillDeadUnits` : la mort est finalisee INLINE chez nous (le displace appelle
      deja `AttackDamageOperation._kill_unit_operation` pour le steppable ecrase), et le gate
      `HasFlag(6 = Dead)` du natif -- collapse en `alive` cote port -- ecarte de toute facon les
      unites deja mortes. Il est porte pour la structure et le journal.
    - `getAbilityType` de `PerformAIAbility` : HYPOTHESE declaree (cf. `it_itches_tree`), a
      confronter live.
    - Le `TargetTileHasEnemyUnit` du masque n'a pas de volet dynamique a porter (aucun
      `GetDynamicInvalidTargetReason` sur cette classe -- verifie : la table de symboles n'en porte
      AUCUN pour `ItItchesAbility`, qui n'expose que `.ctor`, `ExecuteBehaviour`, `GetPushVector`,
      `GetTargetTiles`, `GetTargetUnits`).

    Renvoie {ability, caster, target, tile, direction, pinned, pushed, spawned, attacks, dsl}."""
    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.ItItches)     # 1121
    ABILITY_ID = IT_ITCHES_ID

    # GATE DE CIBLE -- forme de ctor = **FLAGS DIRECTS** (la 1re des trois formes), LUE verbatim dans
    # `...ItItchesAbility$$.ctor` :
    #   TargetingOptions..ctor(&opts, 0, &<TargetingRange statics+0x30>, 0, 0x80040, 0, 0)
    #     isSelfCasting    = 0
    #     range            <- `TargetingRange` statics+0x30 = RANGE_ADJACENT
    #     forceMeleeTarget = 0 = `RangedBool.True` (l'enum natif est INVERSE : 0 = True, 1 = False)
    #     rules            = 0x80040
    # Decomposition EXHAUSTIVE de 0x80040 (0x40 + 0x80000, aucun bit residuel) :
    #     0x40     (bit 6)  TargetIsTile           -> la cible EST une entite-tuile.
    #     0x80000  (bit 19) TargetTileHasEnemyUnit -> cette tuile doit porter un ENNEMI.
    # ⚠ `forceMeleeTarget = 0` est l'une des DEUX valeurs hors defaut du lot (cf. le commentaire
    # historique de `abilities/targeting.py`, d'ou cette entree a MIGRE dans le meme commit --
    # CONTRAT DE DISJONCTION : un masque se declare a UN seul endroit).
    TARGETING_OPTIONS = TargetingOptions(
        rules=TR.TargetIsTile | TR.TargetTileHasEnemyUnit,
        self_cast=False, range=RANGE_ADJACENT, force_melee_target=RANGED_BOOL_TRUE)

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        # #287-r14 : pour un masque `TargetIsTile`, le role `target` du natif est TOUJOURS
        # l'entite-TUILE (`TargetingQuery$$GetActualTarget`), que l'appelant ait passe la tuile ou
        # son occupant. IDEMPOTENT -> inerte quand `AbilityHandler` a deja resolu.
        target_id = self.get_actual_target(state, caster_id, target_id)
        board = state.board
        tile_id = target_id if (board is not None and target_id in board.by_id) else None
        if tile_id is None:
            return {"ability": IT_ITCHES_ID, "caster": caster_id, "target": target_id,
                    "tile": None, "direction": None, "dsl": True}
        # `VectorFromAdjacentTo(CasterTile@0x50, Cache(Tiles(Target@0x60)), 1)` -> `GetVector`
        # (`IBattleQuery` slot 113). `_dir_index` est le foyer porte de ce mirror (il sert deja a la
        # face DECISION de CETTE ability). None = tuiles non adjacentes -> le natif rend son vecteur
        # par defaut, dont `GetTileInDirection` ne tire aucune tuile : AUCUNE poussee.
        feet = get_unit_feet(state, int(caster_id))     # `EntityExtensions$$GetTiles(Caster)`
        cpos = feet[0] if feet else None                # `SelectTile` = la PREMIERE tuile (main tile)
        tpos = board.coord(tile_id)
        vector_dir = (None if (cpos is None or tpos is None)
                      else _dir_index(cpos[0], cpos[1], tpos[0], tpos[1]))
        ectx = ExecutionContext(state=state, rng=state.rng)
        atomic, reset, group = it_itches_tree(tile_id, vector_dir)
        # TROIS executions natives distinctes, `entities` RE-MATERIALISE entre chacune (le natif
        # re-copie les 0x148 octets du contexte avant chaque appel).
        atomic.execute(entities_from_state(state, caster_id, tile_id), ectx)   # ExecuteAtomic(0x2a)
        reset.execute(entities_from_state(state, caster_id, tile_id), ectx)    # Execute(ResetMovement)
        group.execute(entities_from_state(state, caster_id, tile_id), ectx)    # Execute(Group(0x22))
        pinned = [p["target"] for n, p in ectx.emitted
                  if n == "AddEffect" and int(p.get("effect_type") or 0) == IT_ITCHES_PINNED]
        pushed = [{"unit": p["pushed"], "moved": p["moved"], "to": p.get("to"),
                   "killed": p.get("killed"), "reason": p.get("reason")}
                  for n, p in ectx.emitted if n == "DisplaceUnitInAdjacentDirection"]
        spawned = [{"unit": p["unit"], "tile": p.get("tile")}
                   for n, p in ectx.emitted if n == "SpawnUnit"]
        attacks = [a for n, p in ectx.emitted if n == "PerformAIAttack" for a in (p.get("attacks") or [])]
        reopened = [p["subject"] for n, p in ectx.emitted if n == "ResetMovement"]
        return {"ability": IT_ITCHES_ID, "caster": caster_id, "target": target_id, "tile": tile_id,
                "direction": vector_dir, "summon": "tyranSmnRipperSwarm",
                "pinned": pinned, "pushed": pushed, "spawned": spawned, "attacks": attacks,
                "movement_reset": reopened, "dsl": True}


# ============ Catalyst (Hive Tyrant `tyranBossHiveTyrantLeviathan`, actif 1032) ================= #
#
# ⚠ LA FICHE D'AUDIT DISAIT « EFFECT/BUFF », ET C'EST EXACT ICI (#890) -- verifie au decompile, pas
# herite : `...CatalystAbility$$ExecuteBehaviour` ne contient AUCUN noeud d'attaque, seulement TROIS
# `AddStaticStatModifierEffect`. La colonne d'audit derive du `damageProfile` de l'ARME du porteur ;
# elle se trouve concorder, ce qui ne la rend pas fiable pour autant.
#
# `IdunBattleLogic.Entities.Abilities.Active.Loki.CatalystAbility$$ExecuteBehaviour` (MIRROR du
# DECOMPILE, build `rnca9r7q6c`) :
#
#     armor       = GetVariableForLevel(config@0x60, 0x1b = 27 extraArmor,  abilityState, 0)
#     blockDmg    = GetVariableForLevel(config@0x60, 0x14 = 20 blockDmg,    abilityState, 0)
#     blockChance = GetNumberConstant   (config@0x60, 0x2d = 45 blockChance)
#     factionId   = GetStringConstant   (config@0x60, 0x3d = 61 factionId)          # "Tyranids"
#     targets = Cache( op_Subtraction( Friends( gs@0x48 = Caster,
#                                               UnitsFromFaction(gs@0x20 = AllAliveUnits,
#                                                                factionId, 3), 3 ),
#                                      gs@0x48 = Caster ),
#                      unique = 1 )
#     Execute( op_Addition( op_Addition(
#         AddStaticStatModifierEffect(targets, 0x420 Catalyst_ExtraArmor_Effect,
#                                     0x10 FixedArmor,  Direct(armor),       Nullable(2), isHidden=0),
#         AddStaticStatModifierEffect(targets, 0x422 Catalyst_ExtraBlockChance_Effect,
#                                     0x07 BlockChance, Direct(blockChance), Nullable(2), isHidden=0) ),
#         AddStaticStatModifierEffect(targets, 0x421 Catalyst_ExtraBlockDamage_Effect,
#                                     0x08 BlockDamage, Direct(blockDmg),    Nullable(2), isHidden=0) ) )
#
# i2 : « All friendly Tyranid units get +<extraArmor> Armour and a <blockChance>% chance to Block
# <blockDmg> Damage for the rest of this turn and the coming enemy turn. »
#
# TROIS points LUS, aucun devine :
#  * L'ORDRE des trois volets est armure -> chance de blocage -> montant de blocage (les trois
#    `AddStaticStatModifierEffect` sont composes `op_Addition(op_Addition(armor, chance), damage)`).
#    Il est SANS EFFET observable ici (trois stats disjointes, aucune ne lit les autres), mais on le
#    mirror : c'est l'ordre d'emission des events, donc l'ordre de la cascade live.
#  * `turns` = un `System.Nullable<int>(2)` LITTERAL -- PAS un `TurnsFromRounds`. La surcharge
#    appelee (`IdunBattleLogic.Entities.DSLBehaviors$$AddStaticStatModifierEffect`, tranchee par ses
#    XREFS ENTRANTES : les TROIS call-sites de `CatalystAbility$$ExecuteBehaviour` pointent la MEME,
#    celle qui prend un `Nullable<int>` et le convertit elle-meme en noeud `Direct`) => la duree est
#    DEJA EN TOURS => `duration_turns=2`, jamais `duration_rounds`.
#  * Le CASTER est EXCLU (`op_Subtraction(..., Caster)`), alors que le masque de ciblage le declare
#    `CasterIsPossibleTarget` : les deux ne se contredisent pas -- le masque gouverne la LEGALITE du
#    cast (self-cast), le selecteur gouverne QUI recoit l'effet.
CATALYST_ID = "Catalyst"
CATALYST_EXTRA_ARMOR = int(EffectType.Catalyst_ExtraArmor_Effect)              # 0x420 = 1056
CATALYST_EXTRA_BLOCK_DAMAGE = int(EffectType.Catalyst_ExtraBlockDamage_Effect)  # 0x421 = 1057
CATALYST_EXTRA_BLOCK_CHANCE = int(EffectType.Catalyst_ExtraBlockChance_Effect)  # 0x422 = 1058
#: `System.Nullable<int>(2)` litteral des TROIS `AddStaticStatModifierEffect` du decompile -- deja en
#: TOURS (cf. le bloc ci-dessus). i2 : « the rest of this turn and the coming enemy turn ».
CATALYST_TURNS = 2


def catalyst_targets_selector():
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.CatalystAbility$$GetEffectTargetsSelector`
    (MIRROR 1:1) -- le MEME sous-arbre que celui reconstruit inline par `$$ExecuteBehaviour` :

        op_Subtraction( Friends( gs@0x48 = Caster,
                                 UnitsFromFaction(gs@0x20 = AllAliveUnits, factionId, 3), 3 ),
                        gs@0x48 = Caster )

    `factionId` = `GetStringConstant(config, 0x3d)` -- LU au gameconfig, pas code en dur : le natif
    lit la config d'ability, donc un rework de la config change la faction buffee sans toucher au
    code. (`Catalyst.constants.factionId` = `"Tyranids"` sur `rnca9r7q6c`.)

    `Friends` (et non `UnitsFromFaction` seul) est ce qui restreint a l'EQUIPE du caster : sans lui,
    un Tyranide ENNEMI serait buffe. Les deux filtres sont bien presents au decompile, dans cet
    ordre : la faction D'ABORD (le pool `AllAliveUnits`), l'equipe ENSUITE.

    ⚠ `GetEffectTargetsSelector` est le point d'ancrage de la face PREDICTION (la surbrillance des
    cibles) ; `ExecuteBehaviour` reconstruit le MEME arbre et l'enveloppe d'un `Cache`. Le port
    partage donc la fonction, et seul l'arbre d'execution ajoute le `Cache`."""
    faction = ((GC.ability(CATALYST_ID) or {}).get("constants") or {}).get("factionId")
    return Sub(Friends(UnitsFromFaction(AllAliveUnits(), faction, selection_type=SELECTION),
                       Caster(), selection_type=SELECTION),
               Caster())


def catalyst_tree(extra_armor: int, block_chance: int, block_dmg: int):
    """Arbre COMPLET de `...CatalystAbility$$ExecuteBehaviour` (MIRROR ; cf. le bloc en tete).

    `Cache(targets)` = `IdunBattleLogic.Entities.DSLSelectors$$Cache(sel, unique: 1)` : les TROIS
    feuilles partagent LA MEME liste resolue une seule fois. Ce n'est pas cosmetique -- si une des
    trois modifications tuait/reveillait une unite, les deux suivantes verraient quand meme
    l'ensemble d'origine. (Aucune des trois ne le fait ici : trois stats defensives.)

    `Const(x)` = `IdunBattleLogic.Entities.DSLFormulas$$Direct(x)` : le montant est FIGE a la pose
    (stat-mod STATIQUE), pas re-evalue -- c'est exactement le contrat d'
    `AddStaticStatModifierEffect`."""
    targets = Cache(catalyst_targets_selector())
    armor = AddStaticStatModifierEffect(targets, CATALYST_EXTRA_ARMOR, int(StatType.FIXED_ARMOR),
                                        Const(int(extra_armor)),
                                        name="Catalyst_ExtraArmor_Effect",
                                        duration_turns=CATALYST_TURNS)
    chance = AddStaticStatModifierEffect(targets, CATALYST_EXTRA_BLOCK_CHANCE,
                                         int(StatType.BLOCK_CHANCE), Const(int(block_chance)),
                                         name="Catalyst_ExtraBlockChance_Effect",
                                         duration_turns=CATALYST_TURNS)
    damage = AddStaticStatModifierEffect(targets, CATALYST_EXTRA_BLOCK_DAMAGE,
                                         int(StatType.BLOCK_DAMAGE), Const(int(block_dmg)),
                                         name="Catalyst_ExtraBlockDamage_Effect",
                                         duration_turns=CATALYST_TURNS)
    return op_add(op_add(armor, chance), damage)


class CatalystAbility(ActiveAbility):
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.CatalystAbility$$ExecuteBehaviour` (id 1032,
    `tyranBossHiveTyrantLeviathan` « Hive Tyrant », Tyranids -- SEUL porteur). SELF-CAST : le buff
    d'equipe des Tyranides ALLIES du caster, caster EXCLU.

    Trois effets STATIQUES de 2 tours, poses sur le MEME ensemble de cibles :
      * `0x420 Catalyst_ExtraArmor_Effect`       -> `StatType.FIXED_ARMOR`  = `extraArmor[level]`
      * `0x422 Catalyst_ExtraBlockChance_Effect` -> `StatType.BLOCK_CHANCE` = `blockChance` (constante)
      * `0x421 Catalyst_ExtraBlockDamage_Effect` -> `StatType.BLOCK_DAMAGE` = `blockDmg[level]`

    ⚠ L'appariement effet <-> stat n'est PAS devinable du nom : `0x421` s'appelle
    `Catalyst_ExtraBlockDamage_Effect` et porte bien `BLOCK_DAMAGE`, mais il est le TROISIEME volet
    du decompile alors que `0x422` (`...BlockChance`) est le DEUXIEME -- les ids ne suivent pas
    l'ordre d'emission. Les trois couples sont LUS au call-site, jamais tries par ordinal.

    `extraArmor` et `blockDmg` sont TOUS DEUX dans `variablesAffectedByRarityBonus` -> scales par
    `AbilityVariablesMultiplierPercentage` de l'unite (200 % au palier haut du boss). `blockChance`
    est une CONSTANTE -> jamais scalee (`ability_var(..., is_constant=True)`)."""
    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.Catalyst)          # 1032
    ABILITY_ID = CATALYST_ID

    # GATE DE CIBLE (#115) -- forme de ctor = **PRESET STATIQUE COPIE** (la 3e des six formes), MEME
    # preset que `BurrowersAbility` ci-dessus. `...CatalystAbility$$.ctor` n'appelle AUCUN
    # `IdunBattle.Core.Services.TargetingOptions$$.ctor` : il recopie les 0x40 octets du champ
    # STATIQUE de `TargetingOptions` a l'offset RELATIF +0x280 du bloc `<TargetingOptions class>+0xb8`,
    # puis `AActiveAbility..ctor(this, &opts, 2)` (3e argument = 2 = `AbilityAttackType.Others`).
    # Contenu RELU champ par champ dans `IdunBattle.Core.Services.TargetingOptions$$.cctor` :
    #     <preset>+0x00 isSelfCasting    = 1
    #     <preset>+0x08 range            <- `TargetingRange` statics+0x60 = RANGE_SELF
    #     <preset>+0x20 forceMeleeTarget = 1 = RangedBool.False
    #     <preset>+0x28 rules            = 0x8004
    # Decomposition EXHAUSTIVE de 0x8004 (0x4 + 0x8000, aucun bit residuel) :
    #     0x4     (bit 2)  CasterMatchesDynamicRule -> arme la regle-delegue `options+0x30` ; 1032 ne
    #             surcharge PAS `GetDynamicInvalidCasterReason` (aucun symbole
    #             `CatalystAbility$$GetDynamic*` dans le build) -> defaut 0, mirror exact.
    #     0x8000  (bit 15) CasterIsPossibleTarget   -> DECLARATIF (lu par
    #             `IdunBattle.Core.Services.TargetingOptions$$get_CanTargetCaster`), jamais un refus.
    # PORTEE : `TargetingRange` statics+0x60 = `RANGE_SELF` -> portee 0, toute cible autre que le
    # caster est refusee sur `TargetIsInRange`. `isSelfCasting = 1` -> cible == caster.
    TARGETING_OPTIONS = TargetingOptions(
        rules=TR.CasterMatchesDynamicRule | TR.CasterIsPossibleTarget,
        self_cast=True, range=RANGE_SELF, force_melee_target=RANGED_BOOL_FALSE)

    def _params(self, state: "State", caster_id: int) -> tuple:
        """`(extraArmor, blockChance, blockDmg)` = les trois amounts collapses.

        Niveau et multiplicateur = l'`AbilityState` de **1032 elle-meme** (`active_ability_state`),
        pas un niveau global d'unite : c'est ce que le natif passe a `GetVariableForLevel`. Les DEUX
        variables sont dans `variablesAffectedByRarityBonus` (`['extraArmor', 'blockDmg']`) donc
        scalees par `AbilityVariablesMultiplierPercentage` ; `blockChance` est une CONSTANTE
        (`GetNumberConstant`), jamais scalee -- trois nombres, deux regimes, et c'est ce qui rend la
        confrontation live discriminante."""
        level, mult = active_ability_state(state, caster_id, self.ABILITY_TYPE)
        armor = ability_var(CATALYST_ID, "extraArmor", level, multiplier_pct=mult) or 0
        block_dmg = ability_var(CATALYST_ID, "blockDmg", level, multiplier_pct=mult) or 0
        chance = ability_var(CATALYST_ID, "blockChance", is_constant=True) or 0
        return int(armor), int(chance), int(block_dmg)

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        if state.get_entity(caster_id) is None:
            return None
        armor, chance, block_dmg = self._params(state, caster_id)
        ectx = ExecutionContext(state=state, rng=state.rng)
        catalyst_tree(armor, chance, block_dmg).execute(
            entities_from_state(state, caster_id, target_id), ectx)
        buffs = [{"unit": p["unit"], "effect": p["effect_type"], "stat": p["stat"],
                  "amount": p["amount"]}
                 for n, p in ectx.emitted if n == "AddStaticStatModifierEffect"]
        return {"ability": CATALYST_ID, "caster": caster_id, "target": target_id,
                "extra_armor": armor, "block_chance": chance, "block_damage": block_dmg,
                "buffs": buffs, "buffed": sorted({b["unit"] for b in buffs}), "dsl": True}


# ====== StranglethornCannon (Hive Tyrant `tyranBossHiveTyrantLeviathan`, actif 1056) ============= #
#
# `IdunBattleLogic.Entities.Abilities.Active.Loki.StranglethornCannonAbility$$ExecuteBehaviour`
# (MIRROR du DECOMPILE, build `rnca9r7q6c`) :
#
#     profile   = GetDamageProfile(config@0x60).Value                         # Blast
#     mainDmg   = AActiveAbility.MinMaxDamage (this, abilityState)            # minDmg  / maxDmg
#     adjDmg    = AActiveAbility.MinMaxDamage2(this, abilityState)            # minDmg_2/ maxDmg_2
#     hits      = GetNumberConstant(config@0x60, 0x2f = 47 nrOfHits)          # 3
#     hits2     = GetNumberConstant(config@0x60, 0x32 = 50 nrOfHits_2)        # 1
#     adj       = DSLSelectors.AdjacentUnits(gs@0x60 = Target, unique = 1, 3)
#     ExecuteAtomic( op_BitwiseAnd( op_BitwiseAnd(
#           DSLBehaviors.InformWeapon(Nullable(profile), isMelee: 0, useSpecial: 0),
#           DSLBehaviors.AttackWithAttackDamage(gs@0x48 = Caster, gs@0x60 = Target, mainDmg,
#                                               Nullable(profile), hits, AbilityOrEffect(this), ., 2) ),
#           DSLBehaviors.AttackWithAttackDamage(gs@0x48 = Caster, adj,            adjDmg,
#                                               Nullable(profile), hits2, AbilityOrEffect(this), ., 2) ),
#        entities, 0x55 = GroupType.StranglethornCannon_AtomicGroup )
#
# i2 : « The Hive Tyrant attacks using its Stranglethorn Cannon, dealing 3x <minDmg-maxDmg> Blast
# Damage to an initial target within 3 hexes. Any units adjacent to the target suffer
# 1x <minDmg_2-maxDmg_2> Blast Damage. »
#
# QUATRE points LUS :
#  * `AdjacentUnits` est passe **BRUT**, sans wrapper `Enemies(...)` -- contraste avec PlasmaGrenade /
#    ScythingTalons / HarvesterOfSouls, qui enveloppent tous leur ring-1. Consequence PORTEE :
#    FRIENDLY-FIRE, les allies du caster adjacents a la cible prennent le volet splash. C'est ce que
#    dit l'i2 (« Any units adjacent »), et c'est ce que le decompile ecrit -- pas une deduction.
#    Le CASTER lui-meme ne peut pas etre du lot : son masque porte `TargetIsNotAdjacent`, donc la
#    cible n'est jamais dans son ring-1, donc lui n'est jamais dans le ring-1 de la cible.
#  * `AdjacentUnits` EXCLUT son origine (`op_Subtraction(Units(AdjacentTiles(origin), ...), origin)`)
#    -> la cible principale ne prend PAS le coup splash en plus : 3 coups, pas 3+1.
#  * Le `selectionType = 3` (`OnlyAliveAndTargetable`) est porte PAR le selecteur -- c'est le SEUL
#    filtre de l'ensemble splash, faute de wrapper. On ne rajoute donc PAS d'`Alive(...)` : le natif
#    le fait deja, ici, a l'interieur du noeud.
#  * `InformWeapon` (1er terme du `op_BitwiseAnd`) EST MATERIALISE en feuille depuis #890-r1. Son
#    `Nullable` n'est PAS VIDE, contrairement a ce que cette note affirmait : le decompile construit
#    `Nullable__ctor(&local_210, local_res8)` sur le MEME `local_res8` que les deux
#    `AttackWithAttackDamage`, c'est-a-dire la VALEUR du profil (`GetDamageProfile(config@0x60)
#    .Value`). L'ecart comptait : un Nullable vide aurait fait ecrire `Attack_Weapon_DamageProfile =
#    -1` (`DamageProfileType.None_`) la ou le natif ecrit `Blast` -- MESURE live : `18`.
#    Les deux autres arguments sont des litteraux `0` -> `Attack_Weapon_IsMelee = 0`, et
#    `Attack_Weapon_Use_Special` ABSENT (le natif ne pose cette 3e cle que si `useSpecial != 0`).
#    Le noeud est COMBAT-INERTE (aucune Operation d'etat, aucun tirage) : il n'altere pas l'ordre
#    `state.rng` de l'attaque qui le suit.
STRANGLETHORN_ID = "StranglethornCannon"
#: `GetDamageProfile(config@0x60)` -> `StranglethornCannon.constants.damageProfile` = `Blast`.
STRANGLETHORN_PROFILE = "Blast"
#: ⚠ **`None`, PAS `False`** -- et l'ecart est OBSERVABLE, il a ete mesure live (cf. la docstring de
#: la classe). La NATURE du coup ne se deduit PAS de la portee : elle est DECLAREE par l'ability, via
#: `IdunBattle.Core.Services.BattleQuery$$GetAbilityAttackRangeType` = `gameconfig.abilities[<nom>]
#: .attackRangeType`. La config 1056 n'en a **AUCUN** (ses constantes : `damageProfile`, `nrOfHits`,
#: `nrOfHits_2`, `range`) -- contraste `HarvesterOfSouls`/`Supercharge`/`Stikkbomb`, tous `Ranged`.
#: `rangeType` absent => `IsMeleeAttack` FAUX **et** `IsRangedAttack` FAUX => les gates de nature des
#: effets sont TOUS inertes (convention `hits_channel_is_melee(is_melee=None)`, cf. `EntropyCannons`).
STRANGLETHORN_IS_MELEE = None


def stranglethorn_cannon_tree() -> AtomicGroup:
    """Arbre de `...StranglethornCannonAbility$$ExecuteBehaviour` (MIRROR ; cf. le bloc en tete) :

        AtomicGroup( op_and( op_and(
            InformWeapon(profile, isMelee: 0, useSpecial: 0),                                     # TAGS
            AttackWithAttackDamage(Target(),                    minDmg  /maxDmg  , nrOfHits  ) ), # MAIN
            AttackWithAttackDamage(AdjacentUnits(Target(), 3),  minDmg_2/maxDmg_2, nrOfHits_2) ) ) # SPLASH

    ORDRE : inform PUIS main PUIS splash -- c'est l'ASSOCIATION du natif,
    `op_and(op_and(inform, main), splash)`, donc l'ordre de consommation de `state.rng`. Un splash
    joue avant le coup principal desynchroniserait tous les tirages ; `InformWeapon`, lui, est
    COMBAT-INERTE (0 tirage, 0 mutation), donc sa presence en tete ne DEPLACE aucun tirage --
    l'attaque reste bit-exacte (#890-r1).

    `multi=True` sur le splash folde l'`OrderBy` de
    `IdunBattle.Entities.Behaviours.AttackBehaviour$$Execute` (tri par id = ordre de lecture natif).
    `native_factory="attack"` : le decompile appelle bien
    `IdunBattleLogic.Entities.DSLBehaviors$$AttackWithAttackDamage` aux DEUX volets (XREF), donc
    2 tirages/coup a cc=0 -- pas la variante `AbilityDamage` a 1 tirage.

    `hits_key="nrOfHits_2"` sur le splash : le natif lit `GetNumberConstant(0x32)`, PAS le meme
    `nrOfHits` que le main (3 contre 1). Le confondre multiplierait le splash par 3."""
    ability_type = int(ActiveAbilityType.StranglethornCannon)   # AbilityOrEffect(this+0x10)
    main = AttackWithAttackDamage(Target(), STRANGLETHORN_ID, STRANGLETHORN_PROFILE,
                                  is_melee=STRANGLETHORN_IS_MELEE, native_factory="attack",
                                  ability_type=ability_type)
    splash = AttackWithAttackDamage(AdjacentUnits(Target(), selection_type=SELECTION),
                                    STRANGLETHORN_ID, STRANGLETHORN_PROFILE,
                                    is_melee=STRANGLETHORN_IS_MELEE,
                                    min_key="minDmg_2", max_key="maxDmg_2", hits_key="nrOfHits_2",
                                    multi=True, native_factory="attack", ability_type=ability_type)
    # `InformWeapon(Nullable(profile), isMelee: 0, useSpecial: 0)` -- les DEUX derniers sont des
    # litteraux `0` LUS au call-site, jamais deduits du profil ni de `STRANGLETHORN_IS_MELEE` (qui
    # est `None` et repond, lui, a une AUTRE question : la nature du COUP, pas le tag d'arme).
    inform = InformWeapon(STRANGLETHORN_PROFILE, is_melee=False, use_special=False)
    return AtomicGroup(op_and(op_and(inform, main), splash))


class StranglethornCannonAbility(ActiveAbility):
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.StranglethornCannonAbility$$ExecuteBehaviour`
    (id 1056, `tyranBossHiveTyrantLeviathan` « Hive Tyrant », Tyranids -- SEUL porteur). Cast RANGED
    (`constants.range` = 3) : `nrOfHits`(3) coups Blast sur la cible, puis `nrOfHits_2`(1) coup Blast
    (bornes `MinMaxDamage2`) sur CHAQUE unite adjacente a la cible, ALLIES DU CASTER COMPRIS.

    Profil `Blast` (`PiercingRatio` 15, trait de profil `HitsMultipleMembers`).

    Face DECISION : `...$$GetDamageAmountMain` = `AActiveAbility$$MinMaxDamageAverage`,
    `...$$GetDamageAmountAdjacent` = `AActiveAbility$$MinMaxDamage2Average`,
    `...$$GetAdjacentDamageTargets` = le MEME `AdjacentUnits(Target, unique: 1, 3)` que le volet
    splash de `$$ExecuteBehaviour` -- les deux faces partagent donc leur selecteur, et le port
    l'ecrit une seule fois (`stranglethorn_cannon_tree`)."""
    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.StranglethornCannon)   # 1056
    ABILITY_ID = STRANGLETHORN_ID

    # GATE DE CIBLE (#115) -- forme de ctor = **PRESET + FLAGS** (la 2e des six formes).
    # `...StranglethornCannonAbility$$.ctor` recopie les 0x40 octets du preset statique
    # `<TargetingOptions statics>+0x140`, puis appelle
    # `IdunBattle.Core.Services.TargetingOptions$$.ctor(&opts, &preset, 0x100000000)`.
    # SURCHARGE TRANCHEE PAR SES XREFS ENTRANTES (methode obligatoire -- les trois surcharges
    # decompilent sous le MEME nom) : le call-site de `StranglethornCannonAbility$$.ctor` figure dans
    # les xrefs de la surcharge `(this, template, additionalRules)`, celle-la meme qu'appellent
    # `ThunderousAssaultAbility` et `TheQuickeningAbility`. Son corps, LU :
    #     this+0x28 = (ulonglong)additionalRules | template+0x28      <- OU, pas remplacement
    # Le preset `+0x140`, RELU dans `IdunBattle.Core.Services.TargetingOptions$$.cctor` :
    #     <preset>+0x00 isSelfCasting    = 0
    #     <preset>+0x08 range            <- `TargetingRange` statics+0x18 = RANGE_FROM_CONFIG
    #     <preset>+0x20 forceMeleeTarget = 0 = RangedBool.True
    #     <preset>+0x28 rules            = 0x4002
    # => masque EFFECTIF = 0x4002 | 0x100000000 = **0x100004002**, decompose EXHAUSTIVEMENT :
    #     0x2         (bit 1)  TargetMatchesDynamicRule -> arme la regle-delegue `options+0x38` ; 1056
    #                 ne surcharge PAS `GetDynamicInvalidTargetReason` (aucun symbole
    #                 `StranglethornCannonAbility$$GetDynamic*` dans le build) -> defaut 0.
    #     0x4000      (bit 14) TargetIsEnemy            -> refus sur soi-meme / un allie.
    #     0x100000000 (bit 32) TargetIsNotAdjacent      -> refus si la cible est ADJACENTE au caster.
    #                 C'est le flag AJOUTE par le ctor (le preset ne le porte pas) : sans lui, le port
    #                 laisserait le boss tirer au contact, ce que le natif REFUSE.
    # PORTEE : `useRangeFromConfig` (`StranglethornCannon.constants.range` = 3) +
    # `forceMeleeTarget = True` (le preset `+0x140`, celui de PlasmaCannon/Supercharge/Harvester --
    # a NE PAS confondre avec `+0x180`, qui porte le MEME masque 0x4002 et `forceMeleeTarget = 1`).
    TARGETING_OPTIONS = TargetingOptions(
        rules=TR.TargetMatchesDynamicRule | TR.TargetIsEnemy | TR.TargetIsNotAdjacent,
        self_cast=False, range=RANGE_FROM_CONFIG, force_melee_target=RANGED_BOOL_TRUE)

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        if target_id is None:
            return None
        ectx = ExecutionContext(state=state, rng=state.rng)
        stranglethorn_cannon_tree().execute(
            entities_from_state(state, caster_id, target_id), ectx)
        atks = [p for n, p in ectx.emitted if n == "AttackWithAttackDamage"]
        main = next((p["attack"] for p in atks if p.get("target") == target_id), None)
        splash = [{"target": p["target"], "attack": p["attack"]}
                  for p in atks if p.get("target") != target_id]
        return {"ability": STRANGLETHORN_ID, "caster": caster_id, "target": target_id,
                "main_attack": main, "splash": splash, "dsl": True}


# ============ CallRipperSwarms (`tyranBossHiveTyrantLeviathan`, NPC boss, actif 1052) ============
#
# `IdunBattleLogic.Entities.Abilities.Active.Loki.CallRipperSwarmsAbility$$ExecuteBehaviour` --
# MIRROR 1:1 du DECOMPILE. Le cast ne SPAWNE RIEN : il pose UN SEUL behaviour, un effet-BOND de
# summon EN ATTENTE sur des tuiles choisies. Meme decoupe 2-PHASES que `TunnelingHorror` 1011
# (`runner/abilities/necrons.py`) et que les trois `Nova*` du Riptide (`tau.py`).
#
#   n       = AbilityConfiguration.GetNumberConstant(config@this+0x60, 0x10 = nrOfSummons)
#   enemies = DSLSelectors.Enemies( of = Caster@DSLSelectors+0x48,
#                                   entities = AllAliveUnits@+0x20,
#                                   selectionType = 3 = OnlyAliveAndTargetable )
#   tiles   = DSLSelectors.First(
#               DSLSelectors.SortByFormula(
#                   DSLSelectors.CanAddUnit(AllTiles@+0x18),                # surcharge 2-ARGS
#                   DSLFormulas.AverageDistance(ActiveTarget@+0x68, enemies),
#                   ascending: FALSE ),
#               amount = n, ignoreForcedTargets: false )
#   Execute( DSLBehaviors.AddBondEffect( 0x446 = 1094 CallRipperSwarms_PendingSummon,
#                                        AbilityStateReference,
#                                        source       = Caster@+0x48,
#                                        targets      = tiles,
#                                        bondedEntity = Caster@+0x48,
#                                        options      = <struct 0x20 octets ZERO> ) )
#
# ⚠ `CanAddUnit` est la surcharge a DEUX arguments (`DSLSelectors$$CanAddUnit(this, tiles)`), qui
# construit `CanAddUnitTileSelector(state, tiles, parent = <DirectSelector null>,
# isSteppable = <DSLTriggers+0x48>)`. Ce slot de trigger est `op_LogicalNot(<le trigger SANS
# operande>)`, donc `ShouldTrigger` y est TOUJOURS FAUX, donc
# `CanAddUnitTileSelector$$Select`, qui l'INVERSE (`allowSteppable = !ShouldTrigger(...)`), tourne
# TOUJOURS en `allowSteppable = true` -> `allow_steppable=True` cote port. La surcharge a TROIS
# arguments, elle, laisse l'appelant choisir. La difference est INVISIBLE au nom de la fonction et
# se lit uniquement a l'ARITE du call-site (meme piege que l'arite d'`AddEffect` sur les `Nova*`).
#
# ⚠ Le tri est DESCENDANT (`ascending = false`, le 3e argument litteral). La cle est la distance
# MOYENNE de la tuile candidate aux ENNEMIS DU CASTER -- le caster etant le boss, ses ennemis sont
# l'equipe du joueur. Le natif fait donc apparaitre les rippers sur les tuiles les PLUS ELOIGNEES
# du joueur, pas les plus proches. C'est contre-intuitif et c'est LU, pas deduit :
# `IdunBattle.Entities.Selectors.SortByFormulaSelector$$Select` prend `OrderByDescending` quand le
# flag est 0. Une tuile sans aucun ennemi mesurable rend `AVERAGE_DISTANCE_EMPTY` = 10000 et passe
# donc EN TETE de ce tri -- comportement natif, pas une degradation du port.
#
# PHASE 2, HORS de ce port : `IdunBattle.Entities.Effects.Loki.CallRipperSwarms_PendingSummonEffect`
# (`CreateHandleTriggerAbilitiesInternal` = deux `DSLFactory.Triggered` --
# `On(0x15) & IsTurnOf(bonded)` et `On(0x1f) & OwnerIsTargetTile`, tous deux vers
# `If(IsCanAddUnit(Owner), TriggerAbility(<GetSpawnAbilityType>)) & GetRemoveEffectBehaviour()`),
# puis `IdunBattleLogic.Entities.Abilities.Triggered.Loki.CallRipperSwarms_SpawnAbility$$
# CreateBehaviour` (`Spawn(Caster, Target, GetStringConstant(0 = unitId),
# SpawnUnitOptions.WithStatsFromConfig(...).onAppearance = PerformAIAttack(...))`).

CALL_RIPPER_SWARMS_ID = "CallRipperSwarms"
CALL_RIPPER_SWARMS_PENDING_SUMMON = int(EffectType.CallRipperSwarms_PendingSummon)   # 0x446 = 1094


def call_ripper_swarms_spawn_tiles(amount):
    """Le SELECTEUR de tuiles de `...CallRipperSwarmsAbility$$ExecuteBehaviour` (MIRROR) :

        First( SortByFormula( CanAddUnit(AllTiles@+0x18),
                              AverageDistance(ActiveTarget@+0x68, Enemies(Caster, AllAliveUnits, 3)),
                              ascending: false ),
               amount = nrOfSummons )

    `ActiveTarget()` est le slot que `SortByFormulaSelector$$Select` ecrit AVANT chaque evaluation
    de la cle (`AbilityEntities+0x20`, cf. `selectors/units.py::SortByFormula`) : la formule voit
    donc la TUILE CANDIDATE courante, pas la cible du cast. `Enemies(...)`, lui, ne depend d'aucun
    element courant et se re-evalue a l'identique a chaque comparaison -- le natif le construit
    UNE fois, hors du tri, et le port fait de meme (le noeud est partage par toutes les cles)."""
    enemies = Enemies(AllAliveUnits(), selection_type=SELECTION)
    return PickFirstN(SortByFormula(CanAddUnit(AllTiles(), allow_steppable=True),
                                    AverageDistance(ActiveTarget(), enemies),
                                    ascending=False),
                      amount)


def call_ripper_swarms_tree():
    """Arbre de `...CallRipperSwarmsAbility$$ExecuteBehaviour` (MIRROR 1:1) : UNE feuille.

    `nrOfSummons` (`AbilityConstantType.nrOfSummons` = 0x10) est un `GetNumberConstant`, donc une
    CONSTANTE de kit (pas un `GetVariableForLevel`) -- le natif la lit AVANT de batir l'arbre et la
    passe en `int` a la surcharge `First(entities, amount: int, ignoreForcedTargets)`, qui la
    re-enveloppe en `Direct(n)`. Le port collapse ce `Direct` en scalaire, comme le natif l'a
    lui-meme aplati. Kit `CallRipperSwarms` : `nrOfSummons = 4`.

    Duree de l'effet-BOND : le 7e argument natif est une struct de 0x20 octets ZERO-initialisee
    (pas un `TurnsFromRounds(n)`) -> duree DEFAUT de l'effet (`DefaultAmountOfRounds`), meme
    regime que `NovaShield_PendingAttack` (`tau.py`) et `ValkyrieStrike` 1022."""
    n = int(ability_var(CALL_RIPPER_SWARMS_ID, "nrOfSummons", is_constant=True) or 0)
    return AddBondEffect(CALL_RIPPER_SWARMS_PENDING_SUMMON,
                         EffectType.CallRipperSwarms_PendingSummon.name,
                         Caster(), call_ripper_swarms_spawn_tiles(n),
                         duration_rounds=None, bonded_ref=Caster())


class CallRipperSwarmsAbility(ActiveAbility):
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.CallRipperSwarmsAbility$$ExecuteBehaviour`
    (id 1052, `tyranBossHiveTyrantLeviathan` -- Tyranids, **NPC boss de guilde**). Cast SELF.

    OBSERVABLE DU CAST : l'effet-BOND 1094 `CallRipperSwarms_PendingSummon` sur `nrOfSummons` = 4
    TUILES (les plus eloignees en moyenne de l'equipe adverse, parmi celles ou une unite peut etre
    ajoutee), source ET bonded = le caster, duree DEFAUT. AUCUN spawn, AUCUN degat, AUCUN
    deplacement au cast -- le ripper apparait en PHASE 2 (cf. le bloc ci-dessus).

    La face DECISION (`IdunBattle.AI.Playbook.Loki.CallRipperSwarmsPlaybook$$EvaluateNonComparable`,
    `$$GetMaxSummons`) est un AUTRE artefact, hors de ce port COMBAT.

    Flags de tour : defauts base (1052 absent des tables d'override `NO_END_TURN_ABILITY_TYPES` /
    `NO_ABILITY_USED_FLAG_ABILITY_TYPES`) -> l'ability termine le tour + pose ActiveAbilityUsed."""
    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.CallRipperSwarms)     # 1052
    ABILITY_ID = CALL_RIPPER_SWARMS_ID

    # GATE DE CIBLE (#115) + PORTEE (#241) -- forme de ctor = **PRESET STATIQUE COPIE** (la 3e des
    # trois formes) : `...CallRipperSwarmsAbility$$.ctor` n'appelle AUCUN
    # `IdunBattle.Core.Services.TargetingOptions$$.ctor`. Il recopie les 0x40 octets du champ
    # STATIQUE de `TargetingOptions` a l'offset **`+0x280`** du bloc `<class>+0xb8`, puis :
    #     AActiveAbility..ctor(this, &opts, 2)   # 3e arg = 2 = AbilityAttackType.Others
    # Le preset lu EN ENTIER dans `IdunBattle.Core.Services.TargetingOptions$$.cctor` :
    #     <preset>+0x00 = *(statics+0x280) = 1                -> isSelfCasting = TRUE
    #     <preset>+0x08 = copie de `TargetingRange` statics+0x60 -> **RANGE_SELF**
    #                     (`overrideRange = Nullable(0)`)
    #     <preset>+0x20 = *(statics+0x2a0) = 1                -> forceMeleeTarget = RangedBool.False
    #     <preset>+0x28 = *(statics+0x2a8) = **0x8004**       -> le masque
    #     <preset>+0x30/+0x38 = 0                             -> ecrases par `AActiveAbility$$.ctor`
    #
    # Decomposition EXHAUSTIVE -- 0x4 + 0x8000 = 0x8004, aucun bit residuel :
    #     0x4     (bit  2) CasterMatchesDynamicRule  -> la regle dynamique du CASTER ; la classe
    #             native ne surcharge PAS `GetDynamicInvalidCasterReason` (son bloc de
    #             `methodPointers` ne porte que `ExecuteBehaviour` et `.ctor`).
    #             ⚠ CETTE PHRASE CONCLUAIT « donc le delegue reste le DEFAUT d'`AActiveAbility`,
    #             qui ne refuse rien » -- une conclusion que la preuve ne porte PAS : IL2CPP
    #             DEDUPLIQUE les corps triviaux et n'en attribue qu'UN proprietaire, donc
    #             l'absence d'un symbole ne prouve pas l'absence de surcharge. Regime inscrit :
    #             `CASTER_GATE_NOT_READ` (`services/ability_caster_gates.py`), comme les sept
    #             autres porteurs du bit dont la surcharge n'est pas ETABLIE -- le port ne refuse
    #             rien, mais l'ecart est NOMME PERMISSIF au lieu d'etre affirme inexistant.
    #     0x8000  (bit 15) CasterIsPossibleTarget    -> le caster est une cible legale (self-cast).
    # AUCUNE regle de CAMP ni de TUILE : le cast ne vise que lui-meme.
    # C'est le MEME preset que celui d'`ExemplarOfTheMontkaAbility` (`tau.py`) -- deux lectures
    # independantes du meme bloc du `.cctor`, memes quatre champs.
    TARGETING_OPTIONS = TargetingOptions(
        rules=TR.CasterMatchesDynamicRule | TR.CasterIsPossibleTarget,
        self_cast=True, range=RANGE_SELF, force_melee_target=RANGED_BOOL_FALSE)

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        entities = entities_from_state(state, caster_id, target_id)
        ectx = ExecutionContext(state=state, rng=state.rng)
        call_ripper_swarms_tree().execute(entities, ectx)
        return {"ability": CALL_RIPPER_SWARMS_ID, "caster": caster_id, "target": target_id,
                "pending": [{"target": p.get("target"), "bonded": p.get("bonded")}
                            for n, p in ectx.emitted if n == "AddBondEffect"],
                "dsl": True}

