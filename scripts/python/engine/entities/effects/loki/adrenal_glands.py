"""`AdrenalGlands_Effect` (`EffectType` 0x419 = 1049) -- le passif du summon `tyranSmnHormagaunt`
et des CINQ npc Hormagaunt (`tyranNpc1Hormagaunt`, `...Kronos`, `...Gorgon`, `..._SyncPvp_Kronos`,
`..._SyncPvp_Gorgon`).

i2 (`Abilities/AdrenalGlands_CurrentLevelDescription`) : << May move with +{extraMovement} Movement
if that move ends in a hex adjacent to an enemy >> -- `constants = {extraMovement: 1}`.

RESIDU `#1018-r1`, ferme ici (#1048). La RE etait complete dans
`docs/rl/case-1018-passifs-tyranides-hormagaunt.md` sec. 2 ; ce qui manquait etait la CHAINE
CONSOMMATRICE, portee dans le meme commit (`services/range_bonus.py`,
`entities/effects/base.py::range_bonus_for_movement`, `services/movement_query.py::
get_range_bonus_for_unit` / `movement_range_with_applied_bonus` / `get_extra_reachable_tiles`).

================================================================================================
RE (decompile ghidra, build `rnca9r7q6c`)
================================================================================================

`IdunBattle.Entities.Effects.Loki.AdrenalGlandsEffect$$CreateRangeBonusForMovement(owner)` --
SEUL implementeur du hook dans tout le build :

    EffectRangeBonus { Trigger             = null,                                 // +0x00
                       ExtraRange          = GetNumberConstant(0xe = extraMovement),  // +0x08
                       ExtraRangeCondition = tile => IsValidExtraMove(owner, tile),   // +0x10
                       ReduceRange         = null }                                // +0x18

`ReduceRange = null` est ce qui rend ce passif SUBTIL : `MovementQuery$$MovementRangeWithApplied
Bonus` ne lit QUE `ReduceRange`, donc AdrenalGlands **n'augmente pas la portee brute**. Il n'ajoute
que des tuiles supplementaires CONDITIONNELLES, via `GetExtraReachableTiles`.

`...$$IsValidExtraMove(owner, movementEndTile)` (slots `IBattleQuery` LUS dans
`data/symbols/<build>/metadata/interface_slots.tsv`, jamais devines) :

    p   = EntityExtensions$$GetCurrentOwnerEntityId(owner)
    cur = Query.GetAdjacentEnemies(owner,           p, ignoreSteppables: false)   // slot 125 = 0x7d
    end = Query.GetAdjacentEnemies(movementEndTile, p, ignoreSteppables: false)
    foreach (enemy in end)
        if (!cur.Contains(enemy) && IsNearestTileToMoveToMeleeWithEnemy(owner, enemy, movementEndTile))
            return true;
    return false;

-> l'ennemi doit etre **NOUVEAU** (pas deja adjacent avant le mouvement) : le bonus sert a ENTRER
au contact, pas a longer.

`...$$IsNearestTileToMoveToMeleeWithEnemy(owner, enemy, tile)` :

    path = Query.GetPathTo(owner, tile);                       // slot 19 = 0x13, 2 args
    if (path == null) return false;
    d = path.Count;                                            // NOEUDS, extremites incluses
    foreach (t in Query.GetAdjacentTiles(enemy, onlyEmptyOrSteppable: false,
                                         onlyWalkableTiles: true, allowTemporary: true))  // slot 79
    {
        if (t == tile) continue;
        if (!t.IsWalkable(checkFog: true)) continue;
        if (!t.IsFreeTile(State, allowSteppable: true, allowTemporaryTile: false,
                          allowAnyUnit: false)) continue;
        p2 = Query.GetPathTo(owner, t);
        if (p2 != null && p2.Count < d) return false;          // une tuile STRICTEMENT plus proche existe
    }
    return true;

-> parmi les tuiles au contact de CET ennemi, la destination doit etre l'une des PLUS PROCHES (au
sens du nombre de noeuds du chemin de marche). Le bonus ne sert donc jamais a contourner.

⚠ **Le pseudo-C Ghidra ecrit `tile` la ou la boucle porte sur `t`** (registres confondus) : le
`while (tile == t) continue` juste au-dessus n'a de sens que si la suite porte sur `t`, et `tile`
etant par construction une DESTINATION de mouvement (donc walkable et libre), lire `tile` rendrait
les deux filtres invariants -- donc inertes. Cette lecture-ci est celle qui a un sens en C#.

================================================================================================
CE QUI N'EST PAS PORTE, ET C'EST DIT
================================================================================================

* `ignoreSteppables: false` de `GetAdjacentEnemies` : le port n'a pas de canal `Steppable` sur
  l'adjacence d'unite. Degradation PERMISSIVE (un ennemi steppable adjacent compte), inerte tant
  qu'aucun ennemi steppable ne cotoie un Hormagaunt.
* `IsTemporary` d'`IsFreeTile` : aucun substrat offline (residu deja nomme par
  `entities/selectors/tiles.py` et `walk_pathfinder.py`).
* `checkFog` d'`IsWalkable` : le port lit la walkability du board, sans brouillard.

PIEGE DE MONTAGE (mesure #1018) : les Hormagaunts portent `InstinctiveBehaviour_BlockMovement`
(<< si une cible est a portee, cette unite ne bouge pas >>). Tout scenario de mouvement doit etre
monte HORS PORTEE de tout ennemi, sinon le trait masque l'effet mesure.
"""
from __future__ import annotations

from ..base import BaseEffect
from ..magnitude import ability_var
import engine.battle_query as _bq                       # FORME B : le module, pas les noms
import engine.services.range_bonus as _rb               # FEUILLE (aucun import du paquet)
import engine.entities.pathfinding.walk_pathfinder as _wpf   # FORME B. Aretes GRATUITES : charger
import engine.entities.traits.unit_trait as _ut              #   ces deux modules seuls ne tire pas
#     CE module (mesure #485) -- aucune boucle a fermer, donc rien a differer.

#: `GetNumberConstant(0xe)` -> `gameconfig.abilities.AdrenalGlands.constants["extraMovement"]`.
ADRENAL_GLANDS = "AdrenalGlands"
EXTRA_MOVEMENT_KEY = "extraMovement"


def _unit_positions(state) -> dict:
    """`{entityId: (col, row)}` des unites VIVANTES posees sur le plateau -- le substrat de
    `GetAdjacentEnemies`. Les morts sont exclus : `KillUnitOperation -> RemoveUnitFromTiles` vide
    le `TileContentComponent`, donc un cadavre n'occupe plus rien cote natif non plus."""
    from ....runner.components import (OwnerComponent, PositionComponent, UnitComponent)
    out = {}
    for uid, e in (getattr(state, "entities", None) or {}).items():
        uc = e.get_component(UnitComponent)
        pc = e.get_component(PositionComponent)
        oc = e.get_component(OwnerComponent)
        if uc is None or not uc.alive or pc is None or oc is None:
            continue
        out[int(uid)] = ((pc.col, pc.row), oc.team)
    return out


def _adjacent_enemies(state, board, pos, team) -> set:
    """`IdunBattle.Core.Services.BattleQuery$$GetAdjacentEnemies(from, playerId, ignoreSteppables)`
    (slot 125) en domaine POSITION : les unites vivantes d'une AUTRE equipe posees sur une tuile
    adjacente a `pos`, au sens d'`is_adjacent` (liste STOCKEE de voisins + porte d'elevation)."""
    neigh, _walk, elev = board.walk_maps_by_pos() if board is not None else (None, None, None)
    out = set()
    for uid, (upos, uteam) in _unit_positions(state).items():
        if uteam == team:
            continue
        if _bq.is_adjacent(tuple(pos), tuple(upos), elev_by_pos=elev, neigh_by_pos=neigh):
            out.add(int(uid))
    return out


def is_nearest_tile_to_move_to_melee_with_enemy(mctx, enemy_pos, tile, path_counts) -> bool:
    """Mirror 1:1 de `AdrenalGlandsEffect$$IsNearestTileToMoveToMeleeWithEnemy` (cf. l'en-tete).

    `path_counts` = `{(col,row) -> GetPathTo(owner, pos).Count}` calcule UNE FOIS par decision
    (`walk_pathfinder.get_path_node_counts_by_pos`) : le natif rappelle `GetPathTo` a chaque tour
    de boucle, mais c'est la MEME requete depuis la MEME origine, donc la memoisation est exacte.
    Une position ABSENTE du dict = `GetPathTo == null` (pas de chemin)."""
    d = path_counts.get(tuple(tile))
    if d is None:
        return False                                   # `if (path == null) return false;`
    board, state = mctx.board, mctx.state
    neigh, walk, elev = board.walk_maps_by_pos()
    occupied = {p for p, _t in _unit_positions(state).values()}
    for t in _bq.get_adjacent_tiles(
            tuple(enemy_pos),
            walkable_at=lambda p: bool(walk.get(p)),
            elevation_at=lambda p: elev.get(p),
            tile_exists=lambda p: p in walk,
            only_empty_or_steppable=False, only_walkable_tiles=True, allow_temporary=True):
        if t == tuple(tile):
            continue                                   # `if (t == tile) continue;`
        if not walk.get(t):
            continue                                   # `IsWalkable(t, checkFog: true)`
        if t in occupied:
            continue                                   # `IsFreeTile(t, allowAnyUnit: false)`
        c2 = path_counts.get(t)
        if c2 is not None and c2 < d:
            return False                               # une tuile STRICTEMENT plus proche existe
    return True


def is_valid_extra_move(mctx, end_pos, path_counts) -> bool:
    """Mirror 1:1 de `AdrenalGlandsEffect$$IsValidExtraMove` (cf. l'en-tete) : la destination doit
    amener au contact d'un ennemi qui ne l'etait PAS, et par l'une de ses tuiles les plus proches."""
    state, board = mctx.state, mctx.board
    upos = _unit_positions(state).get(int(mctx.unit_id))
    if upos is None:
        return False
    owner_pos, team = upos
    cur = _adjacent_enemies(state, board, owner_pos, team)
    end = _adjacent_enemies(state, board, end_pos, team)
    positions = _unit_positions(state)
    for enemy in end:
        if enemy in cur:
            continue                                   # `!cur.Contains(enemy)`
        epos = positions.get(int(enemy))
        if epos is None:
            continue
        if is_nearest_tile_to_move_to_melee_with_enemy(mctx, epos[0], end_pos, path_counts):
            return True
    return False


class AdrenalGlandsEffect(BaseEffect):
    """`AdrenalGlands_Effect` (0x419 = 1049) -- owner-effect PERMANENT dont la SEULE face est le
    hook `CreateRangeBonusForMovement`. Aucune stat-modification, aucun `EffectBonus` : il n'agit
    QUE sur l'ensemble des tuiles atteignables, via `MovementQuery$$GetExtraReachableTiles`."""

    def create_range_bonus_for_movement(self, mctx):
        """`AdrenalGlandsEffect$$CreateRangeBonusForMovement(owner)` -- verbatim de l'en-tete.

        Contexte incomplet (`board`/`state`/`unit_id` absents) -> `None` : SANS la condition, le
        bonus deviendrait un `+extraMovement` INCONDITIONNEL, c'est-a-dire l'inverse exact du
        natif. On rend donc rien plutot qu'un bonus permissif."""
        if mctx is None or mctx.board is None or mctx.state is None or mctx.unit_id is None:
            return None
        n = ability_var(ADRENAL_GLANDS, EXTRA_MOVEMENT_KEY, is_constant=True)
        if not n:
            return None
        # `GetPathTo(owner, .)` est invariant sur toute l'evaluation du bonus (meme origine, meme
        # etat) -> une seule passe Dijkstra, memoisee dans la closure. Mirror EXACT du natif, qui
        # rappelle le slot 19 a chaque tuile.
        counts = {}

        def _cond(pos, _counts=counts):
            if not _counts:
                _counts.update(_path_counts(mctx))
            return is_valid_extra_move(mctx, tuple(pos), _counts)

        return _rb.EffectRangeBonus(trigger=None, extra_range=int(n),
                                    extra_range_condition=_cond, reduce_range=None)


def _path_counts(mctx) -> dict:
    """`{(col,row) -> GetPathTo(owner, pos).Count}` -- `IPathfinders.GetPath` de la MARCHE, foyer
    partage `walk_pathfinder.get_path_node_counts_by_pos` (`Count` = NOEUDS, extremites incluses).

    `blocking_positions` = `WalkPathfinder$$UnitIsBlockedByEnemyUnit` : occupant ENNEMI vivant non
    `Steppable`. Un allie ne bloque pas le passage."""
    from ....runner.components import StatsComponent
    state, board = mctx.state, mctx.board
    positions = _unit_positions(state)
    me = positions.get(int(mctx.unit_id))
    if me is None or board is None:
        return {}
    owner_pos, team = me
    neigh, walk, elev = board.walk_maps_by_pos()
    blocking = set()
    for uid, (upos, uteam) in positions.items():
        if int(uid) == int(mctx.unit_id) or uteam == team:
            continue
        e = state.get_entity(int(uid))
        sc = e.get_component(StatsComponent) if e is not None else None
        # FOYER `entity_trait_names` (#462-...-r3), jamais la lecture brute `ctx.traits` : c'est
        # le substrat COMPLET de `BaseUnitComponent$$HasTrait` -- kit gameconfig, traits ACCORDES
        # en bataille (`AddTraitOperation`) et pseudo-trait de grande-alliance. Un occupant qui
        # RECOIT `Steppable` en cours de partie cesse alors de bloquer, comme cote natif.
        if _ut.has_trait(_ut.entity_trait_names(getattr(sc, "ctx", None)), _ut.UnitTrait.Steppable):
            continue                                   # `HasTrait(occ, 0x1b)` court-circuite
        blocking.add(tuple(upos))
    return _wpf.get_path_node_counts_by_pos(tuple(owner_pos), neigh_by_pos=neigh,
                                            walkable_by_pos=walk, elev_by_pos=elev,
                                            blocking_positions=blocking)
