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
    neighbours=None,
) -> dict:
    """BFS niveau-par-niveau → {tile_id -> distance-en-pas depuis start}. Inclut
    le start (niveau 0). `max_depth` borne la profondeur (None = illimité). Le
    start lui-même n'est pas filtré par son propre occupant (on part de là).

    `edge(board, from_id, to_id, occupants, moving_team) -> bool` = prédicat d'arête
    (peut-on TRAVERSER vers `to`). Défaut = `is_valid_path_node` (WalkPathfinder) ;
    le FlyPathfinder passe son propre prédicat (mirror natif `BasePathfinder` = BFS
    générique, chaque pathfinder override `IsValidPathNode`).

    `neighbours(tile_id) -> [tile_id]` = le VOISINAGE, et c'est un SECOND slot virtuel, distinct
    de l'arête (#381-r3). `BasePathfinder$$GetValidNeighbours` appelle `AddNeighbours` par la
    VTABLE (`vslot 0x238`), et les deux corps ne lisent pas la même chose :

      * `IdunBattle.Entities.Pathfinding.BasePathfinder$$AddNeighbours`
        (`u003CAddNeighboursu003Ed__19$$MoveNext`) énumère la `List` du `ConnectivityComponent`
        de la tuile (`connectivity+0x10`) et résout chaque id sur l'état — la liste d'adjacence
        **STOCKÉE** ⇒ `board.base_add_neighbours`, le DÉFAUT ici. C'est le canal BRUT depuis
        `#448-r1-r1-r1-r1-r2-r1` (avant : le champ hérité `neighbours`, amputé par la porte
        `|Δelev| < 2` du capteur). NO-OP **prouvé** sur cette route : les arêtes que le canal
        ajoute sont exactement celles de `|Δelev| >= 2`, que `IsReachableElevationDifference`
        (point 2 du prédicat ci-dessus) refuse toutes ;
      * `IdunBattle.Entities.Pathfinding.FlyPathfinder$$AddNeighbours` OVERRIDE et interroge la
        requête de tuiles au rayon 1 — la **GÉOMÉTRIE** ⇒ `board.neighbours_geometric`, que
        `fly_pathfinder` passe explicitement.

    ⚠ Ce n'est PAS `board.neighbours()` : celui-là dépend du `adjacency=` de l'instance, donc du
    montage de l'appelant, alors que le natif n'a jamais qu'une source par pathfinder. `evenq`
    faisait SUR-atteindre la marche (mesuré `C1_74`/3811 `overrideRange` 5 : `tauAunShi` 36 contre
    34 au natif — (4,2) et (5,3), atteintes en franchissant l'arête (1,5)→(2,4) que le
    `ConnectivityComponent` ne porte pas) et `native_sym` faisait SOUS-atteindre le vol
    (`bloodIntercessor` 45 contre 46 — (3,1) manquante).

    `can_continue(tile_id) -> bool` = `IsValidContinuePathTile` (#131) : peut-on ÉTENDRE
    la fill DEPUIS cette tuile ? Le start en est exempt (`currentTile != startTile` du natif).
    None = pas de gate (le board n'a pas d'effet block-entering, ou l'appelant ne le connaît
    pas) → BFS d'avant #131.

    NON PORTÉS, et ce sont les DEUX autres sources de voisins de `GetValidNeighbours` (elles
    s'ajoutent à `AddNeighbours`, elles ne le remplacent pas) :
      * `BasePathfinder$$AddTeleportationTiles` — si la tuile courante est une tuile de
        téléportation (`ConnectivityComponent+0x18 != 0`, cf.
        `IdunBattle.Entities.TileExtensions$$IsTeleportationTile`), sa jumelle devient voisine
        (sauf si un ENNEMI l'occupe). Le `boardGraph` ne publie pas ce champ : la paire n'est ni
        dans `neighbours_native` ni dérivable. Dégradation RESTRICTIVE, bornée aux boards à
        téléporteur — aucune arête non-géométrique n'apparaît dans le `boardGraph` de `C1_74`,
        `MC1_67`, `C2_26` ni `PVP_desert_04`.
      * `BasePathfinder$$AddShadewalkerTiles` — sous trait `0x23` ET effet `0x3a` sur la tuile de
        départ, TOUTE tuile du board portant ce même effet devient voisine.
    Même absence côté capteur pour l'exemption d'élévation du couple téléporteur : `IsValidPathNode`
    saute le test `|Δelev| <= 1` quand les DEUX tuiles sont des téléporteurs, alors que la porte
    `|Δelev| < 2` de `IdunBattle.Core.Services.TileQuery$$IterateAdjacentTiles` (par laquelle passe
    le capteur) est INCONDITIONNELLE."""
    nb = neighbours if neighbours is not None else board.base_add_neighbours
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
            for n in nb(cur):
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
    neighbours=None,
) -> tuple[set, set]:
    """Renvoie (visited, stop_set) pour une portée `depth` (niveaux).
      - visited : toutes les tuiles atteintes en ≤ depth pas (start inclus), PRIVÉES de celles
                  qu'`IsMovableTile` retire — cf. ci-dessous ;
      - stop_set: tuiles où l'unité peut S'ARRÊTER = visited \\ occupées \\ {start}.
    `edge` = prédicat de TRAVERSÉE (défaut walk ; fly passe le sien).

    LE FILTRE `IsWalkable` EST EXPLICITE DEPUIS #403. Le natif sépare deux étages que le port
    collapse : `MovementQuery$$AnyOrFillMoveableTiles` fait
    `GetReachableTiles(...).RemoveAll(t => !IsMovableTile(this, unit, t, ignoreUnitsOnTiles))`, et
    `IdunBattle.Core.Services.MovementQuery$$IsMovableTile` délègue à
    `IdunBattle.Entities.TileExtensions$$IsFreeTile(tile, state, allowSteppable: true, null,
    ignoreUnitsOnTiles)`, dont les DEUX PREMIERS tests sont, verbatim,
    `MovementComponent[+0x10] == 0` puis `TileComponent[+0x40] == 0` — c'est-à-dire EXACTEMENT
    `TileExtensions$$IsWalkable(tile, checkFog: true)`, donc `board.walkable`. Et ils sont testés
    AVANT le `if (!allowAnyUnit)` : même sous `ignoreUnitsOnTiles`, une tuile non walkable sort du
    pool.

    Le test était jusqu'ici IMPLICITE (l'arête walk exige déjà `IsWalkable`) — il reste un no-op
    pour la MARCHE. Il devient NÉCESSAIRE pour le VOL, dont l'arête ne teste que `!IsWall` depuis
    #403 : le vol TRAVERSE une tuile `Block`/`Water` mais ne s'y pose pas.

    `can_continue` = gate d'EXPANSION #131 (cf. `get_reachable_levels`) ; il ne retire RIEN du stop
    set — une tuile block-entering reste un arrêt légal (mesuré live). Il ne vaut QUE pour la
    branche MARCHE (`pathfinders.continue_gate_for`).

    `neighbours` = le voisinage, second slot virtuel (cf. `get_reachable_levels`) ; défaut =
    `board.base_add_neighbours` (la liste STOCKÉE que lit `BasePathfinder$$AddNeighbours`)."""
    level = get_reachable_levels(board, start_id, occupants, moving_team, max_depth=depth,
                                 edge=edge, can_continue=can_continue, neighbours=neighbours)
    visited = set()
    stop = set()
    for tid in level:
        if tid == start_id:
            visited.add(tid)                        # le depart n'est jamais filtre
            continue
        if not board.walkable(tid):                 # `IsFreeTile` : `movement[0x10] && !fog`
            continue                                # (retire AUSSI de `visited`, cf. docstring)
        visited.add(tid)
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
