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


def tile_blocks_entering(effects_state, tile_id: int, mover_traits=None) -> bool:
    """Bit 0x1 de `GetTileBlockingReasons` pour CETTE tuile et CETTE unité : la tuile porte-t-elle un
    effet block-entering (EffectType 0) dont l'unité n'est PAS exemptée ?

    `effects_state` = `State.effects` (`EffectsState`) — la tuile est une ENTITÉ, ses effets vivent
    dans `by_unit[tile_entity_id]` (ids de tuile disjoints des ids d'unité, cf.
    `damage_model.tile_status_effects_by_pos`). `mover_traits` = noms de traits gameconfig de l'unité
    qui se déplace (`ctx.traits`) ; l'exemption vient de
    `StaticBattleRules.Effect$$NotBlockingMovementOfTraits` (Mounted/Vehicle/Unstoppable)."""
    if effects_state is None:
        return False
    for e in effects_state.by_unit.get(int(tile_id), []):
        if e.consumed:
            continue
        if int(e.effect_type or 0) != BLOCK_ENTERING_UNITS_EFFECT_TYPE:
            continue
        if has_any_trait(mover_traits, not_blocking_movement_of_traits(e.effect_type)):
            continue                       # `Any(exemptTraits, t => HasTrait(unit, t))` -> pas une raison
        return True
    return False


def make_can_continue(effects_state, mover_traits=None):
    """Prédicat `IsValidContinuePathTile` prêt pour `walk_pathfinder.get_reachable_levels`, ou **None**
    si aucune tuile de l'état ne porte d'effet block-entering (aucun gate à poser → BFS inchangé,
    zéro coût sur les boards sans Swamp).

    ⚠ SEED REQUIS : `State.effects` ne contient les effets de TUILE que si `load_state` a reçu le
    canal `tiles=` (`tileMeta`). Sans lui la fonction rend None et le gate est un no-op — c'est la
    dégradation SÛRE (comportement d'avant #131), mais elle est SILENCIEUSE : tout harnais qui veut
    la fidélité de portée doit passer `tiles=rpc("tileMeta", ...)` à `load_state`."""
    if effects_state is None:
        return None
    blocked = {int(tid) for tid in effects_state.by_unit
               if tile_blocks_entering(effects_state, int(tid), mover_traits)}
    if not blocked:
        return None
    return lambda tid: int(tid) not in blocked
