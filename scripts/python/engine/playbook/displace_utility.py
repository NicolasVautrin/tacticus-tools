"""`Playbook<T>$$GetPushableTiles` et `Playbook<T>$$GetTargetUtilityDiffOnDisplace` -- foyer PARTAGE.

Les deux corps vivent sur la BASE generique `IdunBattle.AI.Playbook.Playbook`1`, donc un playbook
Comparable et un playbook NonComparable les appellent tous les deux. Ils etaient portes en un seul
exemplaire, INLINE dans `loki_custom.MortisRoundPlaybook.calculate_custom_utility` (#27) ; la
tranche #977 (`1043 ThunderousAssault`, NonComparable) en avait besoin a l'identique. On DEPLACE
plutot que dupliquer -- l'option (1) de la doctrine « un import differe est un outil a cycle » :
le module est une FEUILLE (il n'importe que `engine.battle_query`, `engine.playbook.base` et deux
feuilles d'entites), donc aucun cycle a fermer.

CORPS NATIFS, relus VERBATIM sur `rnca9r7q6c`.

    IdunBattle.AI.Playbook.Playbooku003C__Il2CppFullySharedGenericTypeu003E$$GetPushableTiles
        (casterTile, target):
            if (!UnitExtensions.IsDisplaceable(target)) return new List();
            tiles = battleQuery.<slot itf 0x4e>(casterTile, target);
            sel   = DSLSelectors.EmptyOrHasSteppableUnit(DSLSelectors.Entities(tiles));
            return sel.SelectTiles(entities);

    IdunBattle.AI.Playbook.Playbooku003C__Il2CppFullySharedGenericTypeu003E$$GetTargetUtilityDiffOnDisplace
        (caster, casterTile, tilesFunc, target):
            best = (target, Fix64(0));
            if (!UnitExtensions.IsDisplaceable(target)) return best;
            util = GetUtility(UtilityType.Tile);                          // composite 7
            t0   = EntityExtensions.GetMainTile(target);
            u0   = util.EvaluateAttack(UtilityAttackCase.Base(target, UnitPosition(t0), t0, aoe));
            foreach (tile in tilesFunc(casterTile, target)) {
                uN   = util.EvaluateAttack(UtilityAttackCase.Base(target, UnitPosition(tile), tile, aoe));
                diff = u0 - uN;
                if (diff > Fix64(0) && diff > best.value) best = (target, diff);
            }
            return best;

Les CINQ points de RE (l'unite du `UtilityAttackCase` est la CIBLE ; `EvaluateAttack` sur Tile(7)
EST `EvaluateMovement` ; c'est un MAX gate a `> 0` ; la liste de tuiles est l'arc ARRIERE, pas la
destination reelle du push ; le slot 0x4e est
`IdunBattle.Core.Services.BattleQuery$$GetMinimumTiles180BehindFromTile`) vivent dans la docstring
de `loki_custom.MortisRoundPlaybook`, l'appelant historique. La TRONCATURE vers `int`, elle, N'EST
PAS ici : elle appartient a `MortisRoundPlaybook$$CalculateCustomUtility`
(`Fix64$$op_Explicit` -> `op_Implicit`), pas au corps generique -- `ThunderousAssaultPlaybook`
consomme la valeur BRUTE.
"""
from __future__ import annotations

from .. import battle_query as bq
from ..entities.traits.unit_trait import UnitTrait, entity_trait_names, has_any_trait
from ..runner.components import NOT_DISPLACEABLE_TRAITS   # foyer UNIQUE de la liste (#498-r4)

from .base import tile_utility_for_unit


def unit_of(ctx, entity_id):
    """L'entree `ctx.units` d'un id d'entite, ou `None`."""
    for u in (ctx.units or []):
        if u.get("id") == entity_id:
            return u
    return None


def main_tile_of(ctx, entity_id):
    """`EntityExtensions$$GetMainTile(entity)` -> `(col, row)` ou `None`."""
    u = unit_of(ctx, entity_id)
    p = (u or {}).get("pos") or {}
    if p.get("col") is None:
        return None
    return (p["col"], p["row"])


def is_displaceable(ctx, unit: dict) -> bool:
    """`IdunBattle.Entities.UnitExtensions$$IsDisplaceable(unit)` : vivante, et sans aucun des trois
    traits refusants (`NOT_DISPLACEABLE_TRAITS`, foyer UNIQUE cote runner).

    DEUX des cinq conditions natives ne sont PAS portees, et #498-r4 les a MESUREES plutot que
    supposees -- verdicts « ne pas cabler », pour deux raisons DIFFERENTES : `HasFlag(unit, 0x19 =
    UnitFlag.Undisplaceable)` n'est pose que par `UnstoppableMomentumReworkedAbility$$
    ExecuteBehaviour`, a l'INTERIEUR d'une execution d'ability, ou la decision n'evalue jamais
    (direction de l'ecart : PERMISSIVE) ; `GetEntityType(unit) != EntityType.Unit` est
    STRUCTURELLEMENT inerte (le `unit` vient de `ctx.units`, dont les deux foyers excluent deja les
    MoW). Le gate `alive` en tete, lui, est un ECART RESTRICTIF du port, conserve.

    Corps DEPLACE depuis `loki_custom.MortisRoundPlaybook._is_displaceable` (#977) -- les jumeaux
    d'`it_itches` et d'`unstoppable_momentum` restent, eux, sur leur propre substrat (dict `unit`
    d'une autre provenance) : les fusionner sort du perimetre de cette tranche."""
    if not unit or not unit.get("alive"):
        return False
    scene = getattr(ctx, "scene", None)
    uctx = scene.ctx(unit.get("id")) if scene is not None else None
    names = entity_trait_names(uctx, unit.get("visualId"))
    return not has_any_trait(names, NOT_DISPLACEABLE_TRAITS)


def pushable_tiles(ctx, caster_tile, target_id) -> list:
    """`Playbook<T>$$GetPushableTiles(casterTile, target)` -> liste de `(col, row)`.

    Trois etages, dans l'ordre natif :
      1. `UnitExtensions.IsDisplaceable(target)` -> vide sinon ;
      2. `IBattleQuery` slot 0x4e = `IdunBattle.Core.Services.BattleQuery$$GetMinimumTiles180BehindFromTile`
         (l'arc ARRIERE de la cible vu depuis `casterTile`) ;
      3. `DSLSelectors.EmptyOrHasSteppableUnit` : la tuile doit etre LIBRE, ou portee par une unite
         a trait `Steppable` -- l'occupant que le push ecrase au lieu de bloquer.
    """
    tu = unit_of(ctx, target_id)
    if tu is None or not is_displaceable(ctx, tu):
        return []
    tpos = main_tile_of(ctx, target_id)
    if tpos is None or caster_tile is None:
        return []
    walkable_at, elevation_at, tile_exists = bq.tiles_behind_accessors(
        getattr(ctx, "walkable_by_pos", None), getattr(ctx, "elev_by_pos", None))
    tiles = bq.get_minimum_tiles_180_behind_from_tile(
        caster_tile, tpos, walkable_at=walkable_at, elevation_at=elevation_at,
        tile_exists=tile_exists)
    if not tiles:
        return []
    occ = {}
    for u in (ctx.units or []):
        p = u.get("pos") or {}
        if u.get("alive") and p.get("col") is not None and u.get("id") != target_id:
            occ[(p["col"], p["row"])] = u
    scene = getattr(ctx, "scene", None)
    keep = []
    for p in tiles:
        o = occ.get(p)
        if o is None:
            keep.append(p)
            continue
        octx = scene.ctx(o.get("id")) if scene is not None else None
        if has_any_trait(entity_trait_names(octx, o.get("visualId")), (UnitTrait.Steppable,)):
            keep.append(p)
    return keep


def target_utility_diff_on_displace(ctx, caster_tile, target_id) -> float:
    """`Playbook<T>$$GetTargetUtilityDiffOnDisplace(...).<+0x18>` -- la valeur BRUTE (Fix64), pas
    tronquee. Le MAX, sur l'arc arriere, de `Tile(7)@tuileCourante - Tile(7)@tuileDePush`, gate a
    `> 0` : les tuiles qui AMELIORENT la position de la cible n'apportent aucun malus, et deux
    tuiles candidates ne s'additionnent pas.

    Rend `0.0` sur la branche `!IsDisplaceable` et sur l'arc vide -- exactement le `best` seed du
    natif (`(target, Fix64(0))`)."""
    tu = unit_of(ctx, target_id)
    if tu is None or not is_displaceable(ctx, tu):
        return 0.0
    tpos = main_tile_of(ctx, target_id)
    if tpos is None:
        return 0.0
    keep = pushable_tiles(ctx, caster_tile, target_id)
    if not keep:
        return 0.0
    u0 = tile_utility_for_unit(ctx, tu, tpos)
    best = 0.0
    for p in keep:
        diff = u0 - tile_utility_for_unit(ctx, tu, p)
        if diff > 0.0 and diff > best:
            best = diff
    return best
