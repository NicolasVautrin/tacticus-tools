"""Primitives IBattleQuery — requêtes spatiales sur l'état de bataille (une fonction par slot natif).

Mirror des slots `IBattleQuery` que le playbook natif appelle pour ses heuristiques NonComparable :
  - `GetAdjacentEnemies @18105af60`  (slot 126, `FUN_180007c20(0x7e,...)`)
  - `GetAdjacentFriends`             (slot 128)
Ces méthodes construisent leurs voisins via `IterateAdjacentTiles.<>d__8.MoveNext @1810acef0`
puis `GetUnitsOnTiles`. On porte le comptage (ce que les feuilles consomment : `.Count`).
"""
from __future__ import annotations

import hexgeo


def count_adjacent(tile: tuple, positions: list, elev_by_pos: dict | None = None) -> int:
    """`GetAdjacentEnemies/Friends(tile).Count` — nombre d'unités de `positions` sur une tuile
    ADJACENTE à `tile`, filtrées par la PORTE D'ÉLÉVATION native.

    `IterateAdjacentTiles.<>d__8.MoveNext @1810acef0` applique, APRÈS les filtres terrain
    optionnels (temporary/walkable/emptyOrSteppable), un gate INCONDITIONNEL :
    `iVar4 = abs(elev(tile) - elev(voisin)) ; if (iVar4 < 2) yield`. Pour un COMPTAGE d'unités,
    les filtres terrain ne retirent jamais une tuile occupée (une unité y stationne) → seule
    l'élévation discrimine ; le gate est symétrique (abs). elev = champ `tile→[0x20]→[0x18]`
    (= tileMeta.elevation). `elev_by_pos = {(col,row): elev}` : fourni ET les 2 élévations connues
    -> gate `|Δ| < 2` ; sinon on compte (fallback hexgeo pur = dégradation sûre)."""
    te = elev_by_pos.get((tile[0], tile[1])) if elev_by_pos else None
    cnt = 0
    for p in (positions or []):
        if hexgeo.distance((tile[0], tile[1]), p) != 1:
            continue
        if elev_by_pos is not None and te is not None:
            pe = elev_by_pos.get((p[0], p[1]))
            if pe is not None and abs(te - pe) >= 2:
                continue   # voisin hors portée d'élévation (|Δelev| >= 2) — natif l'exclut
        cnt += 1
    return cnt
