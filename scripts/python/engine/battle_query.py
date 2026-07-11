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


def in_arc(tile: tuple, pos: tuple, elev_by_pos: dict | None = None) -> bool:
    """`pos` est-il dans l'ARC de `tile` (ring-1 UNION ring-2) au sens de `GetAllTargetsSelector
    @1811e2090` ? ring-1 = `is_adjacent` (dist hex 1, porte d'élévation `|Δelev| < 2`) ; ring-2 = dist
    hex EXACTEMENT 2 (`Unobscured` PASSE-TOUT v1, LoS absente offline). Prédicat PARTAGÉ par
    `count_enemies_in_arc` (compte l'utilité) et `enemies_in_arc` (émet la cible représentative)."""
    if is_adjacent(tile, pos, elev_by_pos):                              # ring-1 (dist 1, élévation-gaté)
        return True
    return hexgeo.distance((tile[0], tile[1]), (pos[0], pos[1])) == 2    # ring-2 (dist 2, Unobscured passe-tout)


def count_enemies_in_arc(tile: tuple, positions: list, elev_by_pos: dict | None = None) -> int:
    """`GauntletsOfUltramarAbility.GetAllTargetsSelector @1811e2090` — nombre d'unités de `positions`
    (ennemis) dans l'ARC de `tile` = ring-1 UNION ring-2 (`in_arc`). Le sélecteur natif est la somme
    (`TargetsSelector.op_Addition`) de deux sous-sélecteurs :
      - `GetAdjacentTargetsSelector @1811e2010` = `Unique(Enemies(AdjacentTiles(tile)))` -> ring-1
        (distance hex 1), PORTE d'élévation `|Δelev| < 2` d'`IterateAdjacentTiles` (cf. `is_adjacent`).
      - `GetSurroundingTargetsSelector @1811e20d0` = `Unobscured(SurroundingEnemies(tile, r=2) - Adjacent)`
        = ring-2 STRICT (distance hex EXACTEMENT 2), filtré `Unobscured` (LoS / practicabilité terrain).
    `Unobscured` n'est PAS modélisable offline (pas de donnée LoS) -> PASSE-TOUT v1 (borne SUP sur ring-2 :
    peut sur-compter un ennemi masqué par un obstacle). Chaque unité occupe une tuile distincte -> le compte
    de positions EST déjà unique. Le plafond `SelectUniqueUnits(3)` est appliqué par l'appelant (playbook)."""
    return sum(1 for p in (positions or []) if in_arc(tile, p, elev_by_pos))


def enemies_in_arc(tile: tuple, enemies: list, elev_by_pos: dict | None = None) -> list:
    """Ennemis (unités decisionView `{id, pos:{col,row}}`) dans l'ARC de `tile` = ring-1 UNION ring-2
    (`in_arc`), DANS L'ORDRE d'énumération de `enemies`. Fallback de `gauntlets_target` sans neighbours."""
    out = []
    for e in (enemies or []):
        p = e.get("pos") if isinstance(e, dict) else None
        if p and p.get("col") is not None and in_arc(tile, (p["col"], p["row"]), elev_by_pos):
            out.append(e)
    return out


def gauntlets_target(tile: tuple, enemies: list, neigh_by_pos: dict | None = None,
                     elev_by_pos: dict | None = None):
    """Id de la CIBLE émise par `GauntletsOfUltramarPlaybook.EvaluateNonComparable @18113e5a0`.

    Le natif boucle sur `GetEligibleTargetsSelectable(caster, MainTile)` et `GenerateAction(pos,
    eligible_target, Fix64(count))` : 1 action / eligible target, MÊME utilité (arc-count, tuile-only)
    -> `Bucket.AddAction @1813fbcc0` garde le PREMIER à égalité (remplace SSI `op_GreaterThan` strict).
    L'énumération des eligible targets est INVERSÉE (`DSLFactory.Tiles`=`SortReverseSelector @180dfdc60`)
    -> la cible = 1er ennemi ring-1 dans l'ordre `boardGraph.neighbours` (= `GetAdjacentTiles` natif)
    **INVERSÉ**, sinon ring-2. VALIDÉ LIVE (#117 : caster@(3,5), ring-1 fwd [80,114,78,118] -> inversé ->
    118 = cible native EXACTE).

    `enemies` = unités `{id, pos:{col,row}}` ; `neigh_by_pos` = {(col,row): [voisins ordre natif]}
    (boardGraph, id résolus -> pos). Porte d'élévation `|Δelev|<2` sur ring-1 (comme l'arc ; non validée
    sur terrain à élévation -> assomption documentée). Sans `neigh_by_pos` (offline pur) : fallback = 1er
    ennemi de l'arc dans l'ordre `enemies` (ordre natif indisponible). Ring-2 (dist 2) : ordre exact non
    validé -> dernier (miroir de l'inversion). None si aucun ennemi dans l'arc."""
    if not enemies:
        return None
    pos2e = {(e["pos"]["col"], e["pos"]["row"]): e for e in enemies
             if isinstance(e, dict) and e.get("pos") and e["pos"].get("col") is not None}
    neigh = (neigh_by_pos or {}).get((tile[0], tile[1]))
    if neigh:
        for p in reversed(neigh):                    # ring-1, ordre natif INVERSÉ
            e = pos2e.get((p[0], p[1]))
            if e is None:
                continue
            if elev_by_pos is not None:              # p est un voisin natif -> adjacent ; seul l'élévation filtre
                te, pe = elev_by_pos.get((tile[0], tile[1])), elev_by_pos.get((p[0], p[1]))
                if te is not None and pe is not None and abs(te - pe) >= 2:
                    continue
            return e.get("id")
        # aucun ennemi ring-1 -> ring-2 (dist hex 2) ; dernier (miroir inversion), ordre exact non validé.
        ring2 = [e for (pp, e) in pos2e.items() if hexgeo.distance((tile[0], tile[1]), pp) == 2]
        return ring2[-1].get("id") if ring2 else None
    arc = enemies_in_arc(tile, enemies, elev_by_pos)  # fallback offline (ordre natif indisponible)
    return arc[0].get("id") if arc else None
