"""Raisons de BLOCAGE d'une tuile — mirror de `IdunBattle.Entities.Pathfinding.WalkPathfinder
$$GetTileBlockingReasons` / `$$IsValidContinuePathTile` (#131, mesuré le 2026-07-27).

Le natif (décompile lu VERBATIM) énumère les ENTITÉS posées sur la tuile et accumule un masque :

    foreach (occ in tile.occupants) {
        if (Enumerable.Any(NotBlockingMovementOfTraits(occ.kind), t => HasTrait(unit, t))) continue;
        if (occ.kind == 0) { reasons |= 1; if (<flag> == 1) reasons |= 3; }
        else if (IsEnemy(occ, unit))       reasons |= 4;
    }

- **bit 0x1** = un EFFET de tuile `BlockEnteringUnitsTileEffect` (EffectType 0) est posé dessus.
  C'est ce que `ThornsBlockMovementAbility$$CreateBehaviour` (`AddBlockEnteringUnitsEffect`) pose
  sur les tuiles **Swamp** — mesuré live sur `MC1_67` : `tileMeta` rend
  `{name: BlockEnteringUnits, effectType: 0}` **et** `{Thorns_DefenseReduction, 0xb}` dès la
  construction du runner.
- **bit 0x4** = occupant ENNEMI (déjà porté, dans `walk_pathfinder.is_valid_path_node`).
- **bit 0x2** = le volet « l'hex FINIT le mouvement » (`WalkPathfinder$$GetEffectiveDepth` ->
  `Min(1, depth)`). La condition qui le pose n'a AUCUN datapoint → NON porté (résidu #131).

Consommateur porté ici : `IsValidContinuePathTile` = `reasons == 0`, que
`BasePathfinder$$NodesInNextLevel` teste AVANT d'étendre la flood-fill depuis une tuile (le start
en est exempt). Une tuile block-entering reste donc un **STOP légal** — vérifié live : les Swamp
sont dans `aiMovableTiles` — mais devient un **cul-de-sac**.

DEUX sources pour ce bit, et c'est la seconde qui ferme le résidu case-224 §4 (cf.
`make_can_continue`) : le canal DYNAMIQUE (`State.effects`, exact mais opt-in) et, à défaut, le
repli TERRAIN (`TERRAIN_BLOCK_ENTERING`, reconstruction de la pose faite au setup par l'ability
hébergée par le tile-def).

MESURE (2026-07-27, `probe_r5c_tile_stage.py`, board `MC1_67`, `admecMarshall` move 3 depuis (3,7)) :

    portée      1      2      3
    natif       6     16     25
    port AVANT  6     17     27      (+ (5,6) puis (0,5) et (6,5) — tous pendus à un Swamp)
    port APRÈS  6     16     25      (0 écart, aux deux sens)
"""
from __future__ import annotations

from ...services.static_battle_rules import (BLOCK_ENTERING_UNITS_EFFECT_TYPE,
                                             not_blocking_movement_of_traits)
from ..traits.unit_trait import has_any_trait
from ..effect_type import EffectType   # #270-r1-r1 : les elements du set ci-dessous sont des EffectType


# --- QUELS effets de tuile s'enregistrent comme BLOQUEURS -----------------------------------------
# Ce n'est PAS `BlockEnteringUnits` seul. `IdunBattle.Entities.Effects.BlockTileMovementEffect$$ApplyInternal`
# est le corps commun : il pousse dans le registre `MovementComponent` de la TUILE une entrée
# `{ blockerId, effectId, tileBlockingType@+0x480, exemptTraits@+0x488 }`, où
# `blockerId = owner.IsUnit() ? owner.OwnerComponent.CurrentPlayerEntityId : 0`. C'est CE registre que
# `WalkPathfinder$$GetTileBlockingReasons` énumère, et son test n'est pas un EffectType mais
# `blockerId == 0` (→ bit 0x1, blocage NEUTRE) sinon `IsEnemy(state[blockerId], unit)` (→ bit 0x4).
#
# Les classes qui s'enregistrent sont donc EXACTEMENT celles qui appellent
# `StaticBattleRules.Effect$$NotBlockingMovementOfTraits` dans leur `.ctor` — SIX, lues une par une
# (l'`EffectType` est le littéral écrit à `+0x10` par chaque ctor) :
#     0x00  `IdunBattle.Entities.Effects.BlockEnteringUnitsTileEffect$$.ctor`        (Swamp, BrokenIce)
#     0x05  `IdunBattle.Entities.Effects.FireEffect$$.ctor`
#     0x11  `IdunBattle.Entities.Effects.IceEffect$$.ctor`
#     0x3a  `IdunBattle.Entities.Effects.Idun.DarknessEffect$$.ctor`
#     0x5e  `IdunBattle.Entities.Effects.Idun.LandMineBlockTileMovementEffect$$.ctor`
#     ----  `IdunBattle.Entities.Effects.BlockTileMovementEffect$$.ctor` : la BASE, `effectType`
#           PARAMÉTRÉ — aucun appelant nommé dans le dump, donc aucun type de plus à lister ici.
# ⚠ Ne pas confondre avec `_MOVEMENT_BLOCKING_EFFECT_TYPES` de `static_battle_rules` : celui-là est
# l'ensemble des types qui PARTAGENT l'exemption Mounted/Vehicle/Unstoppable — Darkness (NightVision)
# et LandMine (aucune exemption) en sont absents alors qu'ils bloquent bel et bien.
#
# MESURÉ (`probe_pathfinding_overreach`, EMC2_02/4242) : les trois tuiles `Fire` du décor sont des
# CULS-DE-SAC natifs exactement comme les Swamp — 6 tuiles sur-atteintes par le port tant que seul
# l'EffectType 0 était reconnu.
# #270-r1-r1 : membres nommes -- le discriminant est le ctor natif deja cite ligne par ligne
# ci-dessus (`FireEffect$$.ctor`, `IceEffect$$.ctor`, ...), qui matche 5/5 `EffectType`.
TILE_MOVEMENT_BLOCKING_EFFECT_TYPES: frozenset = frozenset({
    EffectType.BlockEnteringUnits,          # 0x00
    EffectType.Fire,                        # 0x05
    EffectType.Ice,                         # 0x11
    EffectType.Darkness,                    # 0x3a = 58
    EffectType.LandMine_BlockTileMovement,  # 0x5e = 94
})


def tile_blocks_entering(effects_state, tile_id: int, mover_traits=None) -> bool:
    """Bit 0x1 de `GetTileBlockingReasons` pour CETTE tuile et CETTE unité : la tuile porte-t-elle un
    effet BLOQUEUR **neutre** dont l'unité n'est PAS exemptée ?

    `effects_state` = `State.effects` (`EffectsState`) — la tuile est une ENTITÉ, ses effets vivent
    dans `by_unit[tile_entity_id]` (ids de tuile disjoints des ids d'unité, cf.
    `damage_model.tile_status_effects_by_pos`). `mover_traits` = noms de traits gameconfig de l'unité
    qui se déplace (`ctx.traits`) ; l'exemption est celle du type de l'effet
    (`StaticBattleRules.Effect$$NotBlockingMovementOfTraits` : Mounted/Vehicle/Unstoppable pour
    0/5/0x11, NightVision pour 0x3a, PERSONNE pour 0x5e).

    **NEUTRE** = `blockerId == 0` côté natif, c.-à-d. l'`owner` de l'effet n'est pas une unité. Le
    pendant offline est `e.source is None or e.source == tile_id` : l'effet est porté par la TUILE
    elle-même (décor). MESURÉ live sur les trois boards du cas : `BlockEnteringUnits`,
    `Thorns_DefenseReduction` et les `Fire` de décor ont TOUS `source == <id de leur propre tuile>`.
    RÉSIDU ASSUMÉ : un bloqueur posé par une UNITÉ (`blockerId != 0`) donne le bit 0x4 et ne bloque
    que les ENNEMIS de son poseur — non porté (il faudrait la team du mover ici) ; on ne bloque donc
    PAS, ce qui sur-atteint au lieu de sur-restreindre, et reste mesurable."""
    if effects_state is None:
        return False
    for e in effects_state.by_unit.get(int(tile_id), []):
        if e.consumed:
            continue
        et = e.effect_type
        if et is None or int(et) not in TILE_MOVEMENT_BLOCKING_EFFECT_TYPES:
            continue
        if e.source is not None and int(e.source) != int(tile_id):
            continue                       # `blockerId != 0` -> bit 0x4 (ennemis du poseur), non porté
        if has_any_trait(mover_traits, not_blocking_movement_of_traits(et)):
            continue                       # `Any(exemptTraits, t => HasTrait(unit, t))` -> pas une raison
        return True
    return False


# --- REPLI STATIQUE : l'ability de tuile HÉBERGÉE par le terrain, posée AU SETUP ------------------
# `IdunBattleLogic.Entities.Abilities.Tiles.ThornsBlockMovementAbility$$CreateBehaviour` (l'ability
# que la tile-config Unity assigne au tile-def **Swamp** — description localisée
# `idun.shared.utils.IdunLocalization.Abilities$$SwampBlockMovementDescription`, membre d'enum
# `TriggeredAbilityType.SwampBlockMovement` = 5) =
#     `AddBlockEnteringUnitsEffect(0) & AddStaticStatModifierEffectToOwner(0xb, 3, Direct(GetNumberConstant(0x14)))`
# ⇒ chaque Swamp porte `BlockEnteringUnits`(EffectType 0) **dès la construction de la bataille**,
# avant toute action. MESURÉ live (`probe_pathfinding_overreach`, MC1_67) : `tileMeta` rend
# `BlockEnteringUnits` sur les 4 tuiles `Swamp` du board, et sur AUCUNE autre.
#
# HARDCODE (source Unity asset, NON dérivable offline) — même nature et même garde que le jumeau
# `engine/runner/operations/triggers/tiles.TILE_DEFENSE_STAT_MODS` : l'association tile-def →
# ability vit dans `idun.IdunUniverse$$GetTileConfigurations`, absente du gameconfig ET de la BC
# (`Board.Tiles[].TileId` ne porte que le NOM du terrain). À RE-CAPTURER si les assets tuile
# changent (spécifique au hash de build). Ne JAMAIS y ajouter un terrain « par ressemblance » :
# `IdunBattleLogic.Entities.Abilities.Tiles.BrokenIceAbility$$CreateBehaviour` pose lui aussi
# `AddBlockEnteringUnitsEffect(0)` mais **sous condition de trigger** (`triggerType == 0x19` ;
# sinon `AddEffect(0x12)`) — un état de trigger ne se devine pas, donc `BrokenIce` reste HORS
# table et ne dépend que du canal dynamique.
TERRAIN_BLOCK_ENTERING: frozenset = frozenset({"Swamp"})


def terrain_blocks_entering(board, tile_id: int, mover_traits=None) -> bool:
    """Repli STATIQUE du bit 0x1 : le TERRAIN de cette tuile héberge-t-il l'ability qui pose
    `BlockEnteringUnits` au setup, et l'unité n'en est-elle PAS exemptée ? (cf. `TERRAIN_BLOCK_ENTERING`).

    L'exemption est la MÊME que celle du canal dynamique — `StaticBattleRules.Effect$$NotBlockingMovementOfTraits(0)`
    = Mounted/Vehicle/Unstoppable — parce que c'est le MÊME effet natif qui est reconstruit."""
    if board is None:
        return False
    if (board.tile_def_id(int(tile_id)) or "") not in TERRAIN_BLOCK_ENTERING:
        return False
    if has_any_trait(mover_traits, not_blocking_movement_of_traits(BLOCK_ENTERING_UNITS_EFFECT_TYPE)):
        return False
    return True


def state_carries_tile_effects(effects_state, board) -> bool:
    """L'état porte-t-il le canal des effets de TUILE (`load_state(tiles=tileMeta)`) ? On le lit
    directement : au moins UNE entité-tuile du board a une entrée dans `EffectsState.by_unit`.

    C'est ce booléen qui arbitre entre canal dynamique et repli terrain — pas un flag posé à la main.
    Un état hydraté fait AUTORITÉ (il connaît les poses/retraits survenus en cours de bataille) ; un
    état non hydraté n'a AUCUNE information de tuile, et c'est là, et là seulement, que le repli
    reconstruit ce que l'ability de terrain a posé au setup."""
    if effects_state is None or board is None:
        return False
    return any(effects_state.by_unit.get(int(tid)) for tid in board.by_id)


def make_can_continue(effects_state, mover_traits=None, board=None):
    """Prédicat `IsValidContinuePathTile` prêt pour `walk_pathfinder.get_reachable_levels`, ou **None**
    si aucune tuile ne bloque l'entrée (aucun gate à poser → BFS inchangé, zéro coût sur les boards
    sans Swamp).

    DEUX sources, dans cet ordre de priorité :

      1. le canal DYNAMIQUE `State.effects` — la vérité, mais il n'existe que si `load_state` a reçu
         `tiles=` (`tileMeta`) ;
      2. à défaut SEULEMENT, le repli TERRAIN `board.tile_def_id` (`terrain_blocks_entering`), qui
         reconstruit la pose faite AU SETUP par l'ability hébergée par le tile-def.

    ⚠ Pourquoi le repli existe (résidu case-224 §4, fermé ici) : `_move_tiles` est appelé sur des
    états chargés SANS `tiles=` (le canal est opt-in et l'immense majorité des call-sites ne le
    passe pas). Le gate #131 y était alors INERTE **en silence**, et la flood-fill s'étendait DEPUIS
    une Swamp : elle atteignait UNE tuile de plus — celle qui ne pend que d'un Swamp. MESURÉ
    (`probe_pathfinding_overreach`) : MC1_67/777 `worldJakhal` (2,3) via la Swamp (1,3),
    `necroWarden` (3,6) via la Swamp (4,6) ; ces tuiles entrent dans l'ensemble natif à `mv+1`, pas
    à `mv` — c'est bien un pas de flood-fill en trop, pas un filtre d'arrêt manquant.

    `board=None` (appelant sans board) ⇒ pas de repli, comportement strictement inchangé."""
    blocked = set()
    if effects_state is not None:
        blocked = {int(tid) for tid in effects_state.by_unit
                   if tile_blocks_entering(effects_state, int(tid), mover_traits)}
    if board is not None and not state_carries_tile_effects(effects_state, board):
        blocked |= {int(tid) for tid in board.by_id
                    if terrain_blocks_entering(board, int(tid), mover_traits)}
    if not blocked:
        return None
    return lambda tid: int(tid) not in blocked
