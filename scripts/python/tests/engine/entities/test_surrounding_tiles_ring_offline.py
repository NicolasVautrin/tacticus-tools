"""`BattleQuery$$GetSurroundingTiles` (le ring de `ThriceBlessedConflagration`, #129) — OFFLINE.

Ce que le LIVE ne peut PAS distinguer, et qui doit quand meme etre garde :
  * l'ORDRE d'emission du disque (`(cube.x, cube.y)` croissant) — a comptes EGAUX, deux directions
    donnent la MEME utilite, donc la MEME decision : le tie-break n'est observable que cote COMBAT ;
  * le fait que `SurroundingTiles` et `AdjacentTiles` DIVERGENT structurellement (porte d'elevation),
    au-dela des deux boards ou la divergence a ete confrontee au natif ;
  * les settings de ligne `0/0` de `ThriceBlessedConflagrationAbility$$GetTilesInLine` vs `1/1` de
    `DarkTalonStrikeAbility$$GetTilesInLine`.

Aucun live, aucun runner. ASCII only.
"""
from __future__ import annotations

from engine import battle_query as bq


def _grid(w=6, h=6, elev_over=None, blocked=()):
    elev = {(c, r): 0 for c in range(w) for r in range(h)}
    elev.update(elev_over or {})
    walk = {k: (k not in blocked) for k in elev}
    return (lambda p: bool(walk.get((p[0], p[1]), False)),
            lambda p: elev.get((p[0], p[1])),
            lambda p: (p[0], p[1]) in elev)


def test_ring_ignores_elevation_where_adjacent_tiles_gates_it():
    """`TileQuery.u003CIterateSurroundingTilesu003Ed__6$$MoveNext` appelle
    `TileUtil$$IsTileValidForList(tile, src, checkWalkable, 0)` — 4e argument LITTERAL `0` : PAS de
    porte d'elevation. `TileQuery.u003CIterateAdjacentTilesu003Ed__8$$MoveNext`, lui, applique
    `|Delta elev| < 2` INCONDITIONNELLEMENT. Une tuile a +4 est donc DANS le ring de 1187 et HORS du
    ring-1 de 1092 -- c'est la difference qui fait caster (ou non) sur un relief."""
    wa, ea, te = _grid(elev_over={(2, 1): 4})
    ring = bq.get_surrounding_tiles((2, 2), 1, False, True, wa, ea, te)
    adj = bq.get_adjacent_tiles((2, 2), walkable_at=wa, elevation_at=ea, tile_exists=te)
    assert (2, 1) in ring, f"le disque SurroundingTiles exclut un palier +4 : {ring}"
    assert (2, 1) not in adj, f"le ring-1 AdjacentTiles garde un palier +4 : {adj}"


def test_ring_keeps_walkable_gate_and_board_edge():
    """`checkWalkable` vaut `1` a la chaine de call-sites portee (`SurroundingTilesSelector$$Select`
    passe `(this+0x29 == 0)`, et les deux call-sites DSL portes passent `p6 = 0`) -> le ring FILTRE
    les non-walkables. `GetTileEntityAt == null` borne le plateau."""
    wa, ea, te = _grid(blocked={(3, 2)})
    ring = bq.get_surrounding_tiles((2, 2), 1, False, True, wa, ea, te)
    assert (3, 2) not in ring, f"une tuile non-walkable est entree dans le ring : {ring}"
    corner = bq.get_surrounding_tiles((0, 0), 1, False, True, wa, ea, te)
    assert corner and all(0 <= p[0] < 6 and 0 <= p[1] < 6 for p in corner), \
        f"le ring deborde du plateau : {corner}"


def test_ring_excludes_center_unless_include_center():
    """`SurroundingTiles(entity, includeCenter=0, ...)` = `SurroundingTiles(entity, 1, ...) -
    Tiles(entity)` cote DSL ; l'itinerant natif porte le meme gate (`includeSelf`)."""
    wa, ea, te = _grid()
    assert (2, 2) not in bq.get_surrounding_tiles((2, 2), 1, False, True, wa, ea, te)
    assert (2, 2) in bq.get_surrounding_tiles((2, 2), 1, True, True, wa, ea, te)


def test_ring_order_is_cube_lexicographic():
    """La triple boucle cube ASCENDANTE de l'iterateur natif emet en ordre LEXICOGRAPHIQUE
    `(cube.x, cube.y)` -- c'est la cle deja portee (`iterate_surrounding_tiles_order_key`). Comme
    1187 n'a QU'UN `SortByFormula` (stable), cet ordre EST son tie-break entre directions d'egal
    compte (DarkTalonStrike, lui, intercale un tri par ANGLE)."""
    wa, ea, te = _grid()
    ring = bq.get_surrounding_tiles((2, 2), 1, False, True, wa, ea, te)
    keys = [bq.iterate_surrounding_tiles_order_key(p) for p in ring]
    assert keys == sorted(keys), f"ordre du ring non cube-lexicographique : {list(zip(ring, keys))}"


def test_line_settings_0_0_vs_1_1():
    """`ThriceBlessedConflagrationAbility$$GetTilesInLine` ecrit `*(byte*)(settings+0x10) = 0` et
    laisse `+0x11` au ctor -> `checkWalkable = updateReference = False` : la marche d'elevation ne
    coupe RIEN, seul le `FilterContinuous` borne la ligne. `DarkTalonStrikeAbility$$GetTilesInLine`
    ecrit `*(u16*)(settings+0x10) = 0x101` -> `1/1` : la meme ligne est VIDE."""
    wa, ea, te = _grid(elev_over={(2, 1): 4})
    assert bq.get_tiles_behind((2, 2), (2, 1), None, False, False, wa, ea, te)[:1] == [(2, 1)]
    assert bq.get_tiles_behind((2, 2), (2, 1), None, True, True, wa, ea, te) == []


def test_check_elevation_is_a_parameter_not_a_constant():
    """Le 4e argument natif d'`IdunBattle.Core.Services.TileUtil$$IsTileValidForList` est un
    LITTERAL DIFFERENT par call-site (`1` chez `BattleQuery$$GetTilesBehind`, `0` chez
    `TileQuery.u003CIterateSurroundingTilesu003Ed__6$$MoveNext`) : le port doit l'exposer, pas le
    cabler."""
    wa, ea, te = _grid(elev_over={(2, 1): 4})
    assert bq.is_tile_valid_for_list((2, 1), (2, 2), True, wa, ea) is False
    assert bq.is_tile_valid_for_list((2, 1), (2, 2), True, wa, ea, check_elevation=False) is True
