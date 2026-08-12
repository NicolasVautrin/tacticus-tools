"""`IBattleQuery` slot 195 `HasSummonTargetInAttackRangeAtTile` -- foyer UNIQUE des DEUX branches.

Le slot **195 = 0xc3** est `HasSummonTargetInAttackRangeAtTile` (3 params) --
`data/symbols/<build>/metadata/interface_slots.tsv`, pas une deduction de nom. Corps natif
(`IdunBattle.Core.Services.BattleQuery$$HasSummonTargetInAttackRangeAtTile`) :

    if (EntityExtensions.IsMachine(parent))
        return HasSummonTargetInAttackRangeAtTileWithMachineParent(parent, unitId, tile)
    nearest = GetNearestEnemy(parent, position: Nullable(new UnitPosition(tile)))
    return IsTargetInAttackRangeForSummon(parent, unitId, tile, nearest)

Les DEUX branches vivent ici depuis #967. La branche MACHINE etait le residu **#945-r1**, ouvert
par `AlphaWarriorPlaybook` (1112) dont le porteur `tyranWingedPrime` est une UNITE : elle etait
INATTEIGNABLE pour lui, et donc non portee. `ForwardSpotter` (1143) la rend obligatoire -- son
porteur `astraOrdnanceBattery` est une **MACHINE OF WAR**, donc c'est la SEULE branche qu'il
emprunte. `IdunBattle.Core.Services.BattleQuery$$HasSummonTargetInAttackRangeAtTileWithMachineParent` :

    player  = EntityExtensions.GetOriginalPlayer(machineParent, state)
    enemies = GetAllEnemiesOf(player.Id)
    foreach target in enemies:
        if (IsTargetInAttackRangeForSummon(machineParent, unitId, tile, target)) return true
    return false

La difference avec la branche UNITE n'est donc PAS un detail : la branche unite ne teste QUE le
plus proche ennemi (`GetNearestEnemy`), la branche machine les teste **TOUS** et rend vrai des que
l'un passe. Un port qui recopierait la branche unite sur une MoW serait donc STRICTEMENT plus
restrictif -- il refuserait des tuiles que le natif accepte.

`IdunBattle.Core.Services.BattleQuery$$IsTargetInAttackRangeForSummon(parent, unitId, tile, target)`
est commun aux deux ; son corps, etage par etage, est cite dans `_is_target_in_attack_range_for_summon`.
"""
from __future__ import annotations

import gameconfig as _gc
import hexgeo

from engine import battle_query as bq

from ._base import NCContext, _unit_cfg

#: `AbilityConfiguration` : `constants.unitId` = l'unite que le natif passe au slot 195.
#: LU dans le gameconfig, jamais code en dur (`<X>Ability$$GetSummonId` est le corps DEDUPLIQUE
#: etiquete `IdunBattleLogic.Entities.Abilities.Active.Loki.SporeMineLauncherAbility$$GetSummonId`,
#: dont le corps est `AbilityConfiguration.GetStringConstant(config, 0)` -- l'index 0 EST `unitId`).
CONST_SUMMON_ID = "unitId"


def summon_id(ability_name: str) -> str | None:
    """`<X>Ability$$GetSummonId(ability)` = `constants.unitId` de la config de l'ability."""
    cfg = _gc.ability(ability_name) or {}
    v = (cfg.get("constants") or {}).get(CONST_SUMMON_ID)
    return str(v) if v else None


def summon_attack_range(sid: str | None) -> int | None:
    """`foreach w in GetUnitConfig(unitId).weapons: range = Max(range, w.Range ?? 1)`.

    Le `?? 1` est LU : une arme de melee (pas de `Range`) compte pour **1**, pas pour 0. Une
    config introuvable rend `None` = « non mesure » (et non `0`, qui refuserait tout)."""
    if not sid:
        return None
    weapons = _unit_cfg(sid).get("weapons")
    if not weapons:
        return None
    return max(int(w.get("Range") or 1) for w in weapons)


def nearest_enemy(ctx: NCContext, frm: tuple):
    """`IdunBattle.Core.Services.BattleQuery$$GetNearestEnemy(caster, position: <tuile de spawn>)`
    -> `(id, position)` ou `None`. La `position` fournie REMPLACE celle du caster, donc les
    distances sont mesurees DEPUIS LA TUILE DE SPAWN.

    Le tie-break natif n'est PAS un simple `min` : `d < bestDist || (adj && !bestAdj)`. Un
    candidat ADJACENT evince donc un candidat plus proche non adjacent -- configuration
    impossible en distance hex, mais le natif l'ecrit et le port le transcrit tel quel.
    `AreEntitiesAdjacent` (court-circuit d'identite + porte d'elevation, cf. #433-r1) et non
    `is_adjacent` : c'est ce corps-la que le natif appelle.

    `IsIrrelevantObject` n'est pas porte : `ctx.enemies` ne publie pas le trait `Object`. Ecart
    PERMISSIF nomme (un decor pourrait etre elu « plus proche ennemi »)."""
    neigh = bq.neigh_map(ctx)
    best = None            # (id, pos, dist, adj)
    for e in (ctx.enemies or []):
        p = e.get("pos") or {}
        if p.get("col") is None:
            continue
        q = (p["col"], p["row"])
        d = hexgeo.distance(frm, q)
        adj = bq.are_entities_adjacent(frm, q, ctx.elev_by_pos, neigh)
        if best is None or d < best[2] or (adj and not best[3]):
            best = (e.get("id"), q, d, adj)
    return None if best is None else (best[0], best[1])


def _is_target_in_attack_range_for_summon(ctx: NCContext, tile: tuple, rng: int | None,
                                          target_pos) -> bool:
    """`IdunBattle.Core.Services.BattleQuery$$IsTargetInAttackRangeForSummon(parent, unitId, tile,
    target)`, etage par etage :

        if (target == null || !UnitExtensions.IsTargetable(target)) return false
        range = 0
        foreach w in GetUnitConfig(unitId).weapons:  range = Math.Max(range, w.Range ?? 1)
        if (DamageCalculations.ShouldApplyRangedInMelee(parent, [tile], state, true)) {
            range = 1 ; if (!TileExtensions.IsAdjacentTo(tile, GetTiles(target))) return false
        } else if (range == 1) {
            if (!TileExtensions.IsAdjacentTo(tile, GetTiles(target))) return false
        }
        if (GetDistance(tile, target) > range) return false
        foreach t in GetTiles(target):
            if (!SetExtensions.IsNullOrEmpty(movementQuery.<slot itf 16>(tile, t, 6, 2))) return false
        if (range == 1 && !DamageCalculations.CanMeleeAttackOverElevationDifference(tile,
                                                        GetMainTile(target))) return false
        return true

    Le slot **16 d'`IMovementQuery` est `GetTilesObscuringTerrain`** (4 params, meme table) : test
    de LIGNE DE VUE, un resultat NON VIDE fait echouer. Mask `6` = elevation + murs, seuil `2` --
    exactement les arguments de `battle_query.is_target_tile_obscured` (foyer partage).

    `ShouldApplyRangedInMelee` est gate sur `HasTrait(attaquant, 0xb = UnitTrait.Ranged)`, trait
    qu'AUCUNE unite ne porte (mesure de `playbook.prediction._shared._should_apply_ranged_in_melee`)
    -> branche morte, non portee.

    `GetTiles(target)` = la seule tuile principale pour une unite mono-tuile."""
    if target_pos is None:
        return False                       # `target == null` (et `IsTargetable` non porte :
        #                                     `ctx.enemies` ne publie que des unites vivantes)
    if rng is None:
        return False                       # portee non mesurable -> le port ne devine pas
    if rng == 1 and not bq.is_adjacent(tile, target_pos, ctx.elev_by_pos, bq.neigh_map(ctx)):
        return False                       # `range == 1 -> IsAdjacentTo(tile, GetTiles(target))`
    if hexgeo.distance(tile, target_pos) > rng:
        return False                       # `GetDistance(tile, target) > range`
    # `movementQuery.GetTilesObscuringTerrain(tile, t, 6, 2)` NON VIDE -> refus.
    if bq.is_target_tile_obscured(tile, target_pos, ctx.elev_by_pos):
        return False
    # `range == 1 && !CanMeleeAttackOverElevationDifference(...)` -- meme porte |d| < 2.
    if rng == 1 and ctx.elev_by_pos:
        ef, et = ctx.elev_by_pos.get(tile), ctx.elev_by_pos.get(target_pos)
        if ef is not None and et is not None and abs(ef - et) >= 2:
            return False
    return True


def has_summon_target_in_attack_range_at_tile(ctx: NCContext, tile: tuple, sid: str | None,
                                              machine_parent: bool) -> bool:
    """`IBattleQuery` slot 195, LES DEUX BRANCHES.

    `machine_parent` = `EntityExtensions.IsMachine(parent)` -- le porteur de l'ability est-il une
    MACHINE OF WAR ? C'est une propriete du KIT (trait `MachineOfWar` du gameconfig), pas de
    l'etat : l'appelant la fixe une fois pour son ability."""
    rng = summon_attack_range(sid)
    if machine_parent:
        # `...WithMachineParent` : TOUS les ennemis du proprietaire, court-circuit au 1er qui passe.
        for e in (ctx.enemies or []):
            p = e.get("pos") or {}
            if p.get("col") is None:
                continue
            if _is_target_in_attack_range_for_summon(ctx, tile, rng, (p["col"], p["row"])):
                return True
        return False
    near = nearest_enemy(ctx, tile)
    if near is None:
        return False
    return _is_target_in_attack_range_for_summon(ctx, tile, rng, near[1])
