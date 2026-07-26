"""Helpers de NORMALISATION partages par plusieurs tranches de selecteurs.

`_entity_pos` et `_tile_positions` etaient definis au milieu de `selectors.py` et
utilises par les tranches `units`, `tiles` et `geometry` (et, hors package, par
`entities/formulas.py`). Les isoler ici est ce qui rend le decoupage ACYCLIQUE :
les trois tranches dependent de ce module, ce module ne depend d'aucune.
Mirror du `EntityExtensions.GetMainTile(entity)` natif (domaine MIXTE)."""
from __future__ import annotations

from dataclasses import replace

import hexgeo

from ... import battle_query          # mirror UNIQUE de GetTilesBehind/IsTileValidForList (#117/#124)
from ...dsl.base import (TargetsSelector, Const, _pos, _within, _is_alive, _units_of, _effect_field,
                         resolve_unit)


def _entity_pos(item, board):
    """Position (col,row) d'UN element du domaine MIXTE (dict d'unite / id de tuile / position) — mirror
    du `EntityExtensions.GetMainTile(entity)` natif, qui rend la tuile d'une UNITE comme d'une TUILE.
    None si non resolvable (board absent pour un id de tuile, unite sans position)."""
    if isinstance(item, dict):
        return _pos(item)
    if isinstance(item, bool):
        return None
    if isinstance(item, int):
        if board is None or item not in board.by_id:
            return None
        c = board.coord(item)
        return (int(c[0]), int(c[1]))
    if isinstance(item, (tuple, list)) and len(item) == 2 and all(isinstance(x, int) for x in item):
        return (int(item[0]), int(item[1]))
    return None


def _tile_positions(sel: TargetsSelector, ctx, board) -> list:
    """Normalise l'evaluation d'un selecteur en liste de POSITIONS (col,row) : id de tuile (int) ->
    `board.coord`, position (col,row) -> telle quelle, dict d'unite -> sa position, liste -> chacun.
    Helper PARTAGE des selecteurs tile-domain ancres sur une tuile (triangle/vecteur/elevation) — le
    natif, lui, manipule des entites-tuiles homogenes."""
    v = sel.evaluate(ctx)
    if v is None:
        return []
    if isinstance(v, tuple) and len(v) == 2 and all(isinstance(x, int) for x in v):
        items = [v]
    elif isinstance(v, (dict, int)):
        items = [v]
    else:
        items = list(v)
    out = []
    for it in items:
        p = _entity_pos(it, board)             # domaine mixte unite / id de tuile / position
        if p is not None:
            out.append((int(p[0]), int(p[1])))
    return out
