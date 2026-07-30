"""WalkPathfinder — port FIDÈLE du pathfinder de marche natif
(`IdunBattle.Entities.Pathfinding.WalkPathfinder` + `BasePathfinder
.GetMovablePositions`). RE ghidra gqfc5mff6c (cf. docs/rl/playbook-engine.md §18).

ÉNUMÉRATION des tuiles atteignables = flood-fill PAR NIVEAUX (1 pas = 1 niveau,
`range` niveaux), SANS coût accumulé (le IdunBattle.Entities.Pathfinding.WalkPathfinder$$WeightCost ne sert qu'à
GetPath A*, pas à l'énumération). `IdunBattle.Entities.Pathfinding.BasePathfinder$$GetMovablePositions
(itérateur IdunBattle.Entities.Pathfinding.BasePathfinder.u003CGetMovablePositionsu003Ed__23$$MoveNext) fait un BFS niveau-par-niveau via `NodesInNextLevel`,
profondeur décrémentée de 1 par niveau.

PRÉDICAT D'ARÊTE (`IdunBattle.Entities.Pathfinding.WalkPathfinder$$IsValidPathNode) — peut-on entrer
sur `to` depuis `from` :
  1. IsWalkable(to)                                 (IdunBattle.Entities.TileExtensions$$IsWalkable)
  2. |elev(to) - elev(from)| <= 1                   (IdunBattle.Entities.Pathfinding.WalkPathfinder$$IsReachableElevationDifference)
     (exception téléporteurs : non modélisée ici — board basique sans téléporteur)
  3. !UnitIsBlockedByEnemyUnit(to, unit)            (IdunBattle.Entities.Pathfinding.WalkPathfinder$$UnitIsBlockedByEnemyUnit : un ENNEMI sur la
     tuile bloque le passage ; un ALLIÉ laisse passer — sauf trait 0x1b non modélisé)

TUILE D'ARRÊT valide = tuile NON occupée (ni allié ni ennemi). On peut TRAVERSER un
allié mais pas s'y arrêter. Le start (tuile courante) est exclu du set.

GATE D'EXPANSION (#131, mesuré le 2026-07-27) — `IdunBattle.Entities.Pathfinding
.BasePathfinder$$NodesInNextLevel` commence par :

    if (currentTile != startTile && !IsValidContinuePathTile(this, unit, currentTile))
        return <liste vide>;          // aucun voisin -> la tuile est un CUL-DE-SAC

`IdunBattle.Entities.Pathfinding.WalkPathfinder$$IsValidContinuePathTile` =
`GetTileBlockingReasons(tile, unit) == 0` ; le bit 0x1 de
`IdunBattle.Entities.Pathfinding.WalkPathfinder$$GetTileBlockingReasons` vient d'un EFFET de
tuile (EffectType 0 = `BlockEnteringUnitsTileEffect`, posé sur les Swamp par
`ThornsBlockMovementAbility`), sauf si l'unité porte un trait de
`StaticBattleRules.Effect$$NotBlockingMovementOfTraits` (Mounted/Vehicle/Unstoppable).

⇒ une tuile block-entering **reste un STOP légal** (mesure live : les Swamp sont dans
`aiMovableTiles`) mais **la flood-fill ne s'étend PAS depuis elle**. C'est le `can_continue`
de `get_reachable_levels`. Sans lui le port sur-atteint : mesure MC1_67, `admecMarshall`
move 3 depuis (3,7) — natif 6/16/25 tuiles à portée 1/2/3, port 6/17/27 (les 2 tuiles en
trop, (0,5) et (6,5), ne pendent QUE d'un Swamp). C'est ce sur-atteint qui faisait choisir
à la passe IA générique une tuile ILLÉGALE (cf. case-r5).

⚠ `GetEffectiveDepth` (`WalkPathfinder$$GetEffectiveDepth` = `Min(1, depth)` quand
`GetTileBlockingReasons & 2`, bit posé par le MÊME effet sous une condition non mesurée)
reste NON porté : c'est le volet « l'hex FINIT le mouvement » de #131, sans datapoint.

API : `occupants` = dict {tile_id -> team_of_occupant}. `moving_team` = team de
l'unité qui bouge. `can_continue` = prédicat {tile_id -> bool} (None = aucun gate, comportement
d'avant #131). Aucun RVA, aucun appel natif — pur calcul depuis le Board capté.

SECOND MOTEUR, en domaine POSITION (#304) : `get_path_node_counts_by_pos` porte l'AUTRE face du
`WalkPathfinder`, celle du **CHEMIN EXACT pondéré** (`GetPathTo` -> `BasePathfinder$$FindPath` ->
`$$GenerateBreadthFirstTree`), que l'en-tête du package annonçait « non porté ». Elle est
consommée par la face DÉCISION (`engine/playbook/modified_exoarmour.py`), qui ne dispose pas d'un
`Board` mais des cartes par-position du `tile_leaf_ctx` — même choix de domaine que
`engine.battle_query` (positions) contre `engine.runner` (tile ids).
"""
from __future__ import annotations

import heapq

from .board import Board


def is_valid_path_node(
    board: Board, from_id: int, to_id: int,
    occupants: dict, moving_team: int,
) -> bool:
    """Peut-on TRAVERSER vers `to_id` depuis `from_id` (IsValidPathNode/Walk)."""
    t = board.by_id.get(to_id)
    if t is None or not t["walkable"]:
        return False
    if abs(board.elevation(to_id) - board.elevation(from_id)) > 1:
        return False
    occ = occupants.get(to_id)
    if occ is not None and occ != moving_team:      # ENNEMI sur la tuile → bloque
        return False
    return True


def get_reachable_levels(
    board: Board, start_id: int,
    occupants: dict, moving_team: int,
    max_depth: int | None = None,
    edge=is_valid_path_node,
    can_continue=None,
) -> dict:
    """BFS niveau-par-niveau → {tile_id -> distance-en-pas depuis start}. Inclut
    le start (niveau 0). `max_depth` borne la profondeur (None = illimité). Le
    start lui-même n'est pas filtré par son propre occupant (on part de là).

    `edge(board, from_id, to_id, occupants, moving_team) -> bool` = prédicat d'arête
    (peut-on TRAVERSER vers `to`). Défaut = `is_valid_path_node` (WalkPathfinder) ;
    le FlyPathfinder passe son propre prédicat (mirror natif `BasePathfinder` = BFS
    générique, chaque pathfinder override `IsValidPathNode`).

    `can_continue(tile_id) -> bool` = `IsValidContinuePathTile` (#131) : peut-on ÉTENDRE
    la fill DEPUIS cette tuile ? Le start en est exempt (`currentTile != startTile` du natif).
    None = pas de gate (le board n'a pas d'effet block-entering, ou l'appelant ne le connaît
    pas) → BFS d'avant #131."""
    level = {start_id: 0}
    frontier = [start_id]
    depth = 0
    while frontier and (max_depth is None or depth < max_depth):
        depth += 1
        nxt = []
        for cur in frontier:
            # `NodesInNextLevel` : depuis une tuile block-entering (hors start), AUCUN voisin.
            if can_continue is not None and cur != start_id and not can_continue(cur):
                continue
            for n in board.neighbours(cur):
                if n in level:
                    continue
                if edge(board, cur, n, occupants, moving_team):
                    level[n] = depth
                    nxt.append(n)
        frontier = nxt
    return level


def get_movable_positions(
    board: Board, start_id: int, depth: int,
    occupants: dict, moving_team: int,
    edge=is_valid_path_node,
    can_continue=None,
) -> tuple[set, set]:
    """Renvoie (visited, stop_set) pour une portée `depth` (niveaux).
      - visited : toutes les tuiles atteintes en ≤ depth pas (traversables, start inclus).
      - stop_set: tuiles où l'unité peut S'ARRÊTER = visited \\ occupées \\ {start}
                  (IsValidContinuePathTile : pas d'occupant ; le natif exclut la
                  tuile courante du résultat).
    `edge` = prédicat de TRAVERSÉE (défaut walk ; fly passe le sien). Le stop reste
    identique (tuile libre) : les tuiles visitées sont déjà passables par construction
    (l'arête exige `walkable`), donc « non occupée » suffit pour les deux pathfinders.
    `can_continue` = gate d'EXPANSION #131 (cf. `get_reachable_levels`) ; il ne retire RIEN
    du stop set — une tuile block-entering reste un arrêt légal (mesuré live)."""
    level = get_reachable_levels(board, start_id, occupants, moving_team, max_depth=depth,
                                 edge=edge, can_continue=can_continue)
    visited = set(level)
    stop = set()
    for tid in visited:
        if tid == start_id:
            continue
        if occupants.get(tid) is not None:          # impossible de finir sur une tuile occupée
            continue
        stop.add(tid)
    return visited, stop


# ─────────────────────────────────────────────────────────────────────────────────────────────
# CHEMIN EXACT PONDÉRÉ (`GetPathTo`) — domaine POSITION (#304)
# ─────────────────────────────────────────────────────────────────────────────────────────────
WEIGHT_BASE = 10          # `WalkPathfinder$$WeightCost` : coût nominal d'entrée sur une tuile
WEIGHT_BLOCKED = 10000    # ... quand `GetTileBlockingReasons(tile, unit) & 1` (bloqueur NEUTRE)


def weight_cost(elevation, blocked: bool = False) -> int:
    """`IdunBattle.Entities.Pathfinding.WalkPathfinder$$WeightCost(unit, tile)`, LU au décompilé :

        return (GetTileBlockingReasons(this, tile, unit) & 1 ? 10000 : 10) - tile.<elevation>

    C'est le coût d'ENTRÉE sur la tuile d'ARRIVÉE de l'arête (le natif appelle
    `WeightCost(unit, voisin)` depuis `BasePathfinder$$GenerateBreadthFirstTree`).
    ⚠ Il DIFFÈRE de celui du `PathfinderType = 1` (`IgnoreTerrainPathfinder$$WeightCost` =
    `10 + IsFilled(to)`, cf. `ignore_terrain_pathfinder.py`) : ici l'élévation compte et l'occupant
    non — inverser les deux fait diverger le chemin rendu (mesuré, cf. l'en-tête de l'autre module).
    `elevation` inconnue (carte non fournie) -> 0 : coût uniforme, le chemin de coût minimal
    redevient alors le chemin de LONGUEUR minimale."""
    return (WEIGHT_BLOCKED if blocked else WEIGHT_BASE) - int(elevation or 0)


def get_path_node_counts_by_pos(origin, neigh_by_pos=None, walkable_by_pos=None,
                                elev_by_pos=None, blocking_positions=(),
                                block_entering_positions=()) -> dict:
    """`{(col,row) -> Count}` de `IPathfinders.GetPath(unit, origin, <pos>, null)` pour toutes les
    tuiles joignables depuis `origin` avec le **WalkPathfinder** (`PathfinderType` 0, celui que
    `MovementQuery$$GetPathfinderTypeForUnit` rend pour une unité sans effet de mouvement spécial
    et non volante). `Count` = nombre de **NOEUDS**, extrémités INCLUSES (`route+0x18` =
    `List._size`), donc `arêtes + 1` ; `origin` lui-même vaut 1.

    Mirror de `IdunBattle.Entities.Pathfinding.BasePathfinder$$FindPath` :

        if (from == null || to == null)          return null
        if (!IsValidFinalTile(unit, to))         return null        // vslot 0x1c8
        cameFrom = GenerateBreadthFirstTree(unit, from, to)
        path = [to] ; cur = to
        while (cur != from) { if (!cameFrom.TryGetValue(cur, out cur)) return null
                              path.Add(cur) }
        path.Reverse() ; return path                                // extrémités INCLUSES

    et de `IdunBattle.Entities.Pathfinding.BasePathfinder$$GenerateBreadthFirstTree` :

        costs[from] = (from, 0) ; pq.Enqueue(from, 0)
        while (pq.Count > 0) {
            tile = pq.Dequeue() ; if (tile == to) return costs
            foreach (n in GetValidNeighbours(this, tile, unit, null)) {
                newCost = WeightCost(unit, n) + costs[tile].cost
                if (!costs.ContainsKey(n) || newCost < costs[n].cost) {
                    pq.Enqueue(n, newCost + Heuristic(n, to)) ; costs[n] = (tile, newCost) } } }

    L'heuristique `BasePathfinder$$Heuristic` = `|dcol| + |drow|` (<= 2 par pas, contre un coût réel
    >= 6 sur les élévations du jeu) est ADMISSIBLE : le chemin rendu est de **coût minimal**, et un
    Dijkstra depuis `origin` (ce que fait ce port) le retrouve pour TOUTES les destinations en une
    passe. L'heuristique ne fait qu'ordonner l'exploration ; elle ne change pas l'optimum.

    Gates portés :
      * `IsValidFinalTile(unit, to)` = `!IsTemporary(to) && IsWalkable(to)` — le volet WALKABLE est
        ici implicite (une tuile non walkable n'entre jamais dans le résultat, cf. l'arête) ;
        `IsTemporary` n'a PAS de source dans le `tile_leaf_ctx` -> RÉSIDU (dégradation PERMISSIVE :
        une tuile temporaire recevrait un compte au lieu de rien).
      * arête = `WalkPathfinder$$IsValidPathNode(from, to, unit)` : `IsWalkable(to)` ET
        `|elev(to) - elev(from)| <= 1` ET `!UnitIsBlockedByEnemyUnit(to, unit)`.
        `blocking_positions` = les positions qui portent un occupant ENNEMI non `Steppable`
        (`UnitExtensions.HasTrait(occ, 0x1b)` court-circuite le blocage).
      * `block_entering_positions` = les positions dont `GetTileBlockingReasons & 1` vaut 1 pour
        CETTE unité (effet bloqueur neutre, exemptions de trait déjà appliquées par l'appelant) :
        elles ne sont pas interdites, elles coûtent `10000 - elevation` — le natif ne les exclut du
        chemin que par leur prix. ⚠ Le gate `IsValidContinuePathTile` de `NodesInNextLevel` (qui, LUI,
        en fait des culs-de-sac) n'existe PAS sur cette route : `GenerateBreadthFirstTree` ne
        l'appelle jamais. Une tuile block-entering reste donc TRAVERSABLE par un chemin.

    ⚠ RÉSIDU (identique à `ignore_terrain_pathfinder.get_path_node_counts`) : le départage entre
    deux chemins de MÊME coût et de longueurs différentes n'est PAS lu au décompilé (il dépend de
    l'ordre interne de la `PriorityQueue` native ; le natif garde le PREMIER trouvé, la mise à jour
    étant conditionnée par un `<` STRICT). Ici, moins de noeuds gagne. Sans relief (coût uniforme),
    l'ambiguïté n'existe pas : tous les chemins de coût égal ont la même longueur.

    Substrat : les cartes par-position du `tile_leaf_ctx` (`neigh_by_pos` = voisins NATIFS du
    `boardGraph`, `walkable_by_pos`, `elev_by_pos`). `neigh_by_pos` absent -> repli sur le voisinage
    hexgeo restreint aux positions connues (même dégradation que `battle_query.adjacent_addable_count`)."""
    import hexgeo
    ok = (origin[0], origin[1])
    blocked_cost = {(p[0], p[1]) for p in (block_entering_positions or ())}
    blocked_edge = {(p[0], p[1]) for p in (blocking_positions or ())}
    domain = None
    if neigh_by_pos is None:
        domain = set(walkable_by_pos or ()) | set(elev_by_pos or ())

    def _neighbours(p):
        if neigh_by_pos is not None:
            return [(q[0], q[1]) for q in (neigh_by_pos.get(p) or ())]
        ns = hexgeo.neighbors(p[0], p[1])
        return [q for q in ns if not domain or q in domain]

    def _elev(p):
        return None if elev_by_pos is None else elev_by_pos.get(p)

    best: dict = {ok: (0, 1)}                      # pos -> (cout cumule, nb de noeuds)
    heap = [(0, 1, ok)]
    while heap:
        cost, nodes, cur = heapq.heappop(heap)
        if (cost, nodes) > best.get(cur, (cost, nodes)):
            continue                               # entree perimee de la file
        ce = _elev(cur)
        for n in _neighbours(cur):
            if walkable_by_pos is not None and not walkable_by_pos.get(n, False):
                continue                           # `IsWalkable(to)`
            ne = _elev(n)
            if ce is not None and ne is not None and abs(ne - ce) > 1:
                continue                           # `IsReachableElevationDifference`
            if n in blocked_edge:
                continue                           # `UnitIsBlockedByEnemyUnit(to, unit)`
            cand = (cost + weight_cost(ne, n in blocked_cost), nodes + 1)
            if n not in best or cand < best[n]:
                best[n] = cand
                heapq.heappush(heap, (cand[0], cand[1], n))
    return {p: nodes for p, (_cost, nodes) in best.items()}
