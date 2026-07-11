"""Primitives IBattleQuery — requêtes spatiales sur l'état de bataille (une fonction par slot natif).

Mirror des slots `IBattleQuery` que le playbook natif appelle pour ses heuristiques NonComparable :
  - `GetAdjacentEnemies @18105af60`  (slot 126, `FUN_180007c20(0x7e,...)`)
  - `GetAdjacentFriends`             (slot 128)
Ces méthodes construisent leurs voisins via `IterateAdjacentTiles.<>d__8.MoveNext @1810acef0`
puis `GetUnitsOnTiles`. On porte le comptage (ce que les feuilles consomment : `.Count`).
"""
from __future__ import annotations

import hexgeo


def is_adjacent(tile: tuple, pos: tuple, elev_by_pos: dict | None = None) -> bool:
    """`pos` est-il sur une tuile ADJACENTE à `tile` selon l'adjacence NATIVE ?

    Primitive d'adjacence COMMUNE à tous les usages du playbook : les comptages `GetAdjacent*`
    (slots 124/126/128) ET `DSLFactory.AdjacentUnits @180de8320` (= `AdjacentTiles` puis `Units`,
    ciblage des heals `HealTargets @1811cca50`). Les deux passent par `IterateAdjacentTiles`, donc
    la MÊME porte d'élévation doit s'appliquer.

    `IterateAdjacentTiles.<>d__8.MoveNext @1810acef0` applique, APRÈS les filtres terrain optionnels
    (temporary/walkable/emptyOrSteppable), un gate INCONDITIONNEL :
    `iVar4 = abs(elev(tile) - elev(voisin)) ; if (iVar4 < 2) yield`. Pour un usage sur unités
    (comptage OU somme de poids), les filtres terrain ne retirent jamais une tuile occupée (une unité
    y stationne) → seule l'élévation discrimine ; le gate est symétrique (abs). elev = champ
    `tile→[0x20]→[0x18]` (= tileMeta.elevation). `elev_by_pos = {(col,row): elev}` : fourni ET les 2
    élévations connues -> gate `|Δ| < 2` ; sinon on retient (fallback hexgeo pur = dégradation sûre)."""
    if hexgeo.distance((tile[0], tile[1]), (pos[0], pos[1])) != 1:
        return False
    if elev_by_pos is not None:
        te = elev_by_pos.get((tile[0], tile[1]))
        pe = elev_by_pos.get((pos[0], pos[1]))
        if te is not None and pe is not None and abs(te - pe) >= 2:
            return False   # voisin hors portée d'élévation (|Δelev| >= 2) — natif l'exclut
    return True


def count_adjacent(tile: tuple, positions: list, elev_by_pos: dict | None = None) -> int:
    """`GetAdjacentEnemies/Friends(tile).Count` — nombre d'unités de `positions` sur une tuile
    ADJACENTE à `tile`, filtrées par la porte d'élévation native (cf. `is_adjacent`)."""
    return sum(1 for p in (positions or []) if is_adjacent(tile, p, elev_by_pos))


def count_enemies_in_arc(tile: tuple, positions: list, elev_by_pos: dict | None = None) -> int:
    """`GauntletsOfUltramarAbility.GetAllTargetsSelector @1811e2090` — nombre d'unités de `positions`
    (ennemis) dans l'ARC de `tile` = ring-1 UNION ring-2. Le sélecteur natif est la somme
    (`TargetsSelector.op_Addition`) de deux sous-sélecteurs :
      - `GetAdjacentTargetsSelector @1811e2010` = `Unique(Enemies(AdjacentTiles(tile)))` -> ring-1
        (distance hex 1), PORTE d'élévation `|Δelev| < 2` d'`IterateAdjacentTiles` (cf. `is_adjacent`).
      - `GetSurroundingTargetsSelector @1811e20d0` = `Unobscured(SurroundingEnemies(tile, r=2) - Adjacent)`
        = ring-2 STRICT (distance hex EXACTEMENT 2), filtré `Unobscured` (LoS / practicabilité terrain).
    `Unobscured` n'est PAS modélisable offline (pas de donnée LoS) -> PASSE-TOUT v1 (borne SUP sur ring-2 :
    peut sur-compter un ennemi masqué par un obstacle). Chaque unité occupe une tuile distincte -> le compte
    de positions EST déjà unique. Le plafond `SelectUniqueUnits(3)` est appliqué par l'appelant (playbook)."""
    n = 0
    for p in (positions or []):
        if is_adjacent(tile, p, elev_by_pos):                             # ring-1 (dist 1, élévation-gaté)
            n += 1
        elif hexgeo.distance((tile[0], tile[1]), (p[0], p[1])) == 2:      # ring-2 (dist 2, Unobscured passe-tout)
            n += 1
    return n
