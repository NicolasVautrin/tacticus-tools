"""Primitives IBattleQuery — requêtes spatiales sur l'état de bataille (une fonction par slot natif).

Mirror des slots `IBattleQuery` que le playbook natif appelle pour ses heuristiques NonComparable :
  - `IdunBattle.Core.Services.BattleQuery$$GetAdjacentEnemies`  (slot 126, `FUN_180007c20(0x7e,...)`)
  - `GetAdjacentFriends`             (slot 128)
Ces méthodes construisent leurs voisins via `IdunBattle.Core.Services.TileQuery.u003CIterateAdjacentTilesu003Ed__8$$MoveNext`
puis `GetUnitsOnTiles`. On porte le comptage (ce que les feuilles consomment : `.Count`).
"""
from __future__ import annotations

import hexgeo

from .hex_corner import Corner

# ⚠ CE MODULE NE DOIT IMPORTER NI `engine.entities` NI RIEN QUI L'EXECUTE (#477-r35).
# C'est ce qui le rend importable EN PREMIER, et plusieurs probes VERSIONNES en dependent
# (`probe_433_r1_identity_shortcircuit.py` fait `from engine.battle_query import ...` en tete).
# MESURE : y avoir ajoute `from .entities.traits.unit_trait import UnitTrait` a rendu
# `python -c "import engine.battle_query"` IMPOSSIBLE en process frais --
# `entities/__init__` -> `effects_state` -> `effects/__init__` -> `factory` -> `loki/__init__`
# -> `ability_modifications` -> `selectors/units.py` -> `from ...battle_query import
# is_target_tile_obscured`, sur un `battle_query` PARTIELLEMENT initialise. Le cycle est
# SENSIBLE A L'ORDRE : il disparait des qu'un appelant importe `entities` d'abord, donc aucune
# passe pytest ne le voit. Le foyer `GetSteppableUnit`, qui a besoin d'`UnitTrait`, vit pour
# cette raison dans `engine/entities/tile_extensions.py` -- ou il porte AUSSI le bon nom natif.
# Garde de cet invariant : `probe_477r35_import_isole.py`.

# --- `IdunBattle.Core.Services.BattleQuery$$GetTilesInTriangleShape(tile, direction)` -----------
# Rend `new List<>(new HashSet{tile, t1, t2})` = l'ancre PUIS les deux tuiles de la direction
# demandee (ordre d'INSERTION du HashSet, conserve par le ctor de List). Le natif lit (col,row)
# dans le `PositionComponent` de l'ancre et branche sur la PARITE de la COLONNE (`col & 1`), puis
# switch sur les 6 directions. Les deux tables ci-dessous sont la transcription LITTERALE de ce
# switch (deltas `(dcol, drow)` appliques a l'ancre) ; chaque paire est bien constituee de deux
# voisins ADJACENTS ENTRE EUX de l'ancre dans le repere odd-q de `hexgeo` (verifie par le
# self-test du module de tests) -> l'aire est toujours un TRIANGLE de 3 tuiles mutuellement
# voisines, ce qu'exige `MovementQuery$$IsValidUnitFeetList(3, ...)`.
_TRIANGLE_EVEN_COL = {
    Corner.NorthWest: ((-1, +1), (0, +1)),  # 0
    Corner.NorthEast: ((0, +1), (+1, +1)),  # 1
    Corner.West: ((-1, +1), (-1, 0)),  # 2
    Corner.East: ((+1, +1), (+1, 0)),  # 3
    Corner.SouthWest: ((-1, 0), (0, -1)),  # 4
    Corner.SouthEast: ((0, -1), (+1, 0)),  # 5
}
_TRIANGLE_ODD_COL = {
    Corner.NorthWest: ((-1, 0), (0, +1)),  # 0
    Corner.NorthEast: ((+1, 0), (0, +1)),  # 1
    Corner.West: ((-1, 0), (-1, -1)),  # 2
    Corner.East: ((+1, -1), (+1, 0)),  # 3
    Corner.SouthWest: ((-1, -1), (0, -1)),  # 4
    Corner.SouthEast: ((+1, -1), (0, -1)),  # 5
}


# `IdunBattle.Core.Services.MovementQuery$$GetDistance(originTiles, destinationTiles)` rend
# `int.MaxValue` quand l'une des deux enumerations est VIDE : le minimum n'est jamais abaisse et la
# fonction rend sa valeur d'initialisation. Les deux surcharges qui prennent des ENTITES
# (`GetDistance(origin, destination)` / `GetDistance(originTiles, destination)`) rendent la meme
# sentinelle sur un argument nul, AVANT meme d'appeler `GetTiles`.
DISTANCE_UNREACHABLE = 0x7FFFFFFF


def get_distance(origin_tiles, destination_tiles) -> int:
    """`IdunBattle.Core.Services.MovementQuery$$GetDistance(originTiles, destinationTiles)` — mirror
    1:1 du corps, celui auquel les quatre surcharges de
    `IdunBattle.Core.Services.BattleQuery$$GetDistance` delegent (slots 9 / 10 / 0xb de l'interface
    de `MovementQuery` ; les surcharges a entites passent d'abord par
    `IdunBattle.Entities.EntityExtensions$$GetTiles`) :

        min = int.MaxValue
        foreach (a in originTiles)
            foreach (b in destinationTiles)
                min = Min(min, CubeCoordinate.Distance(a.Position.GetCubeCoordinate(),
                                                       b.Position.GetCubeCoordinate()))
        return min

    C'est la distance HEXAGONALE minimale entre deux ENSEMBLES de tuiles : **aucun pathfinding**,
    aucun contournement d'obstacle, aucune elevation. A ne pas confondre avec
    `IdunBattle.Core.Services.BattleQuery$$GetNumTilesMoved` (= `path.Count - 1`, la longueur du
    CHEMIN), que `IdunBattle.Operations.MoveUnitOperation$$Execute` utilise. Les deux repondent a
    des questions differentes et divergent des qu'un detour existe (mesure #335 : un pas de
    distance 3 peut couter 4 tuiles de chemin).

    Entrees = des `(col, row)` (le port collapse une `UnitPosition` en sa tuile principale).
    Ensemble vide d'un cote -> `DISTANCE_UNREACHABLE`, exactement comme le natif."""
    best = DISTANCE_UNREACHABLE
    for a in (origin_tiles or ()):
        for b in (destination_tiles or ()):
            d = hexgeo.distance((a[0], a[1]), (b[0], b[1]))
            if d < best:
                best = d
    return best


def get_tiles_in_triangle_shape(anchor: tuple, direction: int) -> list:
    """`IdunBattle.Core.Services.BattleQuery$$GetTilesInTriangleShape(tile, direction)` — mirror :

        var set = new HashSet<TileEntity> { tile };
        var pos = tile.GetComponent<PositionComponent>();      // (col, row)
        if (direction <= 5) {
            (t1, t2) = <switch parite(col) x direction>;        // deux GetTileAt(col', row')
            if (t1 != null) set.Add(t1);
            if (t2 != null) set.Add(t2);
        }
        return new List<TileEntity>(set);

    Le port rend les 3 COORDONNEES sans les clipper au plateau : le natif, lui, laisse tomber une
    tuile hors-plateau (`GetTileAt` -> null) et rend alors une aire de 2 elements, que
    `CorrectArea` refuse (`area.Count != 3`). L'appelant (`spawn_tile_shape.correct_area`) refuse
    de la meme facon toute coordonnee absente du board -> comportement identique.
    `direction > 5` -> l'aire se reduit a `[tile]` (le natif saute le switch)."""
    col, row = int(anchor[0]), int(anchor[1])
    if direction > 5 or direction < 0:
        return [(col, row)]
    table = _TRIANGLE_ODD_COL if (col & 1) else _TRIANGLE_EVEN_COL
    (d1c, d1r), (d2c, d2r) = table[int(direction)]
    return [(col, row), (col + d1c, row + d1r), (col + d2c, row + d2r)]


def neigh_map(ctx) -> dict | None:
    """Le canal de VOISINAGE NATIF porté par un contexte de décision, en TRI-ETAT — `None` = le
    porteur ne le publie pas (jamais `{}`, qui se lirait comme « aucune tuile n'a de voisin »).

    FOYER UNIQUE d'accès au canal, et c'est ce qui le rend brancheable partout : les contextes du
    port sont de trois formes (`AiDecisionContext` et `Scene` = objets, `tile_leaf_ctx` = dict), et
    un accès écrit à la main à chaque call-site retomberait sur `AttributeError` chez l'une ou
    l'autre. Substrat : `boardGraph.neighbours` (`ai/context.py::_board_neighbours`,
    `ai/state_bridge.py::_board_topology_maps`, `utilities/tile.py`), c'est-à-dire la liste STOCKEE
    du `ConnectivityComponent` telle que `BattleQuery$$GetAdjacentTiles(t, 0, 0, 1)` la rend.

    Consommé par `is_adjacent` et ses trois dérivées (#433-r4-r1-r4-r2)."""
    if ctx is None:
        return None
    if isinstance(ctx, dict):
        return ctx.get("neigh_by_pos")
    return getattr(ctx, "neigh_by_pos", None)


def is_adjacent(tile: tuple, pos: tuple, elev_by_pos: dict | None = None,
                neigh_by_pos: dict | None = None) -> bool:
    """`pos` est-il sur une tuile ADJACENTE à `tile` selon l'adjacence NATIVE ?

    Primitive d'adjacence COMMUNE à tous les usages du playbook : les comptages `GetAdjacent*`
    (slots 124/126/128) ET `IdunBattleLogic.Entities.DSLFactory$$AdjacentUnits` (= `AdjacentTiles` puis `Units`,
    ciblage des heals `IdunBattleLogic.Entities.Abilities.Active.Loki.CombatRestorativesAbility$$HealTargets`). Les deux passent par `IterateAdjacentTiles`, donc
    le MÊME substrat et la MÊME porte d'élévation doivent s'appliquer.

    `IdunBattle.Core.Services.TileQuery.u003CIterateAdjacentTilesu003Ed__8$$MoveNext`, structure LUE
    -- une ENUMERATION puis une PORTE, dans cet ordre :

        elev0 = tile.TileComponent.Elevation;                       // d__8+0x48, lu une fois
        foreach (nid in tile.ConnectivityComponent.Neighbours) {     // la liste STOCKEE
            t = state.GetTileEntity(nid);  if (t == null) continue;
            <filtres terrain optionnels : IsTemporary / IsWalkable / IsEmptyOrSteppable>
            if (Math.Abs(elev0 - t.Elevation) < 2) yield return t;   // porte INCONDITIONNELLE
        }

    Le port porte les DEUX étages, et `neigh_by_pos` est le premier (#433-r4-r1-r4-r2) :

      * **`neigh_by_pos` fourni ET la tuile y figure** -> l'énumération est la liste STOCKEE, mirror
        exact. Substrat : `boardGraph.neighbours` (`{(col,row): [(col,row), ...]}`, cf.
        `ai/context.py::_board_neighbours` et `ai/state_bridge.py::_board_topology_maps`), capté par
        `BattleQuery$$GetAdjacentTiles(t, 0, 0, 1)` -- donc par CE MEME itérateur.
      * **canal absent** (carte non fournie, ou tuile hors capture) -> repli GEOMETRIQUE nommé :
        la couronne hex `hexgeo.distance == 1`. Dégradation PERMISSIVE et documentée, jamais un
        voisinage vide -- un `{}` lu comme « aucun voisin » rendrait le prédicat FAUX partout
        (dégradation restrictive massive, le vice exact de `#381-r3`). D'où le tri-état : c'est la
        présence de LA CLE qui décide, pas la vérité du dict.

    La porte, elle, s'applique dans les DEUX voies : elle est le second étage du natif, pas une
    propriété du substrat. Sur le canal capté elle est idempotente (`neighbours` la porte déjà) --
    la rejouer est le mirror, pas une défense ajoutée.

    POURQUOI LE SUBSTRAT COMPTE, mesuré (`probe_433r4r1r4r2_is_adjacent_substrat_live.py`) : la
    couronne hex sur-atteint la liste stockée de **4** arêtes dirigées sur `C1_74` et de **38** sur
    `C3_14` -- les tuiles `Bridge`, que `IdunBattle.Operations.InitializeConnectivityOperation$$Execute`
    ne relie pas à leur voisin de niveau (`TileComponent$$HasEdge` exigé des DEUX côtés). Ecart
    strictement PERMISSIF : **0** arête restrictive sur les quatre boards mesurés.

    elev = champ `tile→[0x20]→[0x18]` (= tileMeta.elevation). `elev_by_pos = {(col,row): elev}` :
    fourni ET les 2 élévations connues -> gate `|Δ| < 2` ; sinon on retient."""
    t = (tile[0], tile[1])
    p = (pos[0], pos[1])
    neigh = None if neigh_by_pos is None else neigh_by_pos.get(t)
    if neigh is None:
        # Canal absent POUR CETTE TUILE -> repli geometrique (cf. docstring : jamais un vide).
        if hexgeo.distance(t, p) != 1:
            return False
    elif p not in {(q[0], q[1]) for q in neigh}:
        return False       # `foreach (nid in Neighbours)` : la tuile n'y est pas -> jamais yieldee
    if elev_by_pos is not None:
        te = elev_by_pos.get(t)
        pe = elev_by_pos.get(p)
        if te is not None and pe is not None and abs(te - pe) >= 2:
            return False   # voisin hors portée d'élévation (|Δelev| >= 2) — natif l'exclut
    return True


def are_entities_adjacent(a: tuple, b: tuple, elev_by_pos: dict | None = None,
                          neigh_by_pos: dict | None = None) -> bool:
    """`IdunBattle.Core.Services.BattleQuery$$AreEntitiesAdjacent` -> `IdunBattle.Core.Services.
    MovementUtil$$AreTilesAdjacent`, et ce N'EST PAS `is_adjacent` ci-dessus.

    Les deux natifs sont DISTINCTS et ne rendent pas la même chose sur une paire identique :

        MovementUtil$$AreTilesAdjacent(t1, t2) = (|dElev| < 2) & (t1 == t2 || IsNeighbour(t1, t2))
        TileQuery$$IterateAdjacentTiles(t, ...) parcourt la liste d'adjacence STOCKÉE sur `t`,
                                                donc ne rend JAMAIS `t` elle-même

    `is_adjacent` mirrore le SECOND (les comptages `GetAdjacent*`, `DSLFactory$$AdjacentUnits`) et a
    donc raison de ne pas compter la tuile source. Le premier, lui, porte le COURT-CIRCUIT
    D'IDENTITÉ : `t1 == t2` court-circuite `IsNeighbour` et rend VRAI, et `|dElev| = 0 < 2` ne peut
    pas le contredire. Confondre les deux fait REFUSER une adjacence que le natif accorde — sans
    erreur ni crash (#433-r1, `docs/rl/case-433-r1-identite-adjacence.md`).

    La porte d'élévation ET le substrat de voisinage sont communs aux deux, et restent délégués à
    `is_adjacent` (`neigh_by_pos` : cf. sa docstring)."""
    if a is None or b is None:
        return False
    if (a[0], a[1]) == (b[0], b[1]):
        return True                    # `tile1 == tile2` -> `b = 1`, et `|dElev| = 0 < 2`
    return is_adjacent(a, b, elev_by_pos, neigh_by_pos)


def get_nearest_enemy(ctx, position: tuple | None = None):
    """`IdunBattle.Core.Services.BattleQuery$$GetNearestEnemy(caster, position)` -> `(id, pos)` ou
    `None` -- FOYER UNIQUE (#971-r1).

    Corps natif, TERME A TERME (`caster:IdunBattle.Core.IEntity,
    position:System.Nullable<IdunBattle.Core.UnitPosition>` -> `IdunBattle.Core.IEntity`, signature
    LUE dans `data/symbols/<build>/frida/methods.tsv`) :

        tilesA = position.HasValue ? position.Value
                                   : EntityExtensions.GetUnitPosition(caster, this.state)
        best = null ; bestDist = int.MaxValue ; bestAdj = false
        foreach u in GetAllAliveUnits(null):
            if (!UnitExtensions.IsEnemy(caster, u, this.state))  continue
            if (UnitExtensions.IsIrrelevantObject(u))            continue
            d   = GetDistance(tilesA, u)
            adj = AreEntitiesAdjacent(tilesA, u)
            if (d < bestDist || (adj && !bestAdj)) { best = u ; bestDist = d ; bestAdj = adj }
        return best

    LES DEUX SURCHARGES SONT TRANCHEES PAR LES XREFS SORTANTES, pas par le nom du parametre :
    `IdunBattle.Core.Services.BattleQuery$$GetDistance` a QUATRE surcharges et
    `$$AreEntitiesAdjacent` TROIS ; le corps de `GetNearestEnemy` appelle celles de signature
    `(tilesA:IList<IEntity>, tileB:IEntity)` et `(tiles:IList<IEntity>, unit:IEntity)`. La seconde
    fait `MovementUtil$$AreTilesAdjacent(tiles, EntityExtensions.GetTiles(unit))` -- donc
    `are_entities_adjacent` (court-circuit d'identite + porte `|dElev| < 2`) et **jamais**
    `is_adjacent`, qui mirrore `TileQuery$$IterateAdjacentTiles`, une primitive DIFFERENTE.
    La premiere delegue a `IdunBattle.Core.Services.MovementQuery$$GetDistance`, dont ce module
    porte deja le mirror (`get_distance` ci-dessus) : ce foyer l'APPELLE au lieu de refaire un
    `hexgeo.distance`, ce que ne faisait AUCUNE des trois copies.

    L'ANCRE EST LE PARAMETRE, et c'est la seule chose qui distinguait les trois appelants :
    `position` fournie -> les distances partent de CETTE tuile (`Nullable` PLEIN, ex. la tuile de
    SPAWN d'un summon) ; `position=None` -> `GetUnitPosition(caster)`, c.-a-d. `ctx.origin`
    (`Nullable` VIDE). Aucune des deux n'est un cas particulier du natif : c'est le `HasValue`.

    `bestDist` demarre a `int.MaxValue` (`DISTANCE_UNREACHABLE`) et non a « pas de best » : le
    natif garde un candidat par `d < bestDist`, jamais par « c'est le premier ». Le tie-break
    `(adj && !bestAdj)` peut donc faire AUGMENTER `bestDist` -- un candidat ADJACENT evince un
    candidat plus proche non adjacent. Le port le transcrit tel quel plutot que de le collapser en
    `min` : l'adjacence native est la liste STOCKEE, rien ne garantit qu'un voisin soit a
    distance 1.

    SUBSTRAT. `ctx.enemies` (`{id, pos}`) EST la source, parce qu'elle seule porte l'identifiant
    que le natif rend ; `ctx.epos` en est la projection (`epos = [(e.pos.col, e.pos.row) for e in
    enemies]`, `ai/context.py`), donc MEME ensemble et MEME ordre -- le repli sur `epos` ne sert
    qu'aux contextes qui ne peuplent pas `enemies` (quelques probes), et rend alors `id = None`.

    ECARTS NOMMES, communs aux trois mirrors d'origine et INCHANGES par la convergence :
      * `IsIrrelevantObject` n'est pas porte -- ni `enemies` ni `epos` ne publient le trait
        `Object` ; ecart PERMISSIF (un decor pourrait etre elu « plus proche ennemi ») ;
      * le natif compare des EMPREINTES (`GetUnitPosition(caster)` x `GetTiles(u)`) la ou le port
        compare des tuiles principales (#419-r1-tr10-r2) ;
      * l'ordre d'enumeration natif (`GetAllAliveUnits`, un `IOrderedSet`) est approxime par celui
        de `ctx.enemies` -- il ne departage que les ex aequo STRICTS (tie residuel)."""
    frm = position if position is not None else getattr(ctx, "origin", None)
    if frm is None:
        return None                      # pas d'ancre -> le port ne devine pas `GetUnitPosition`
    frm = (frm[0], frm[1])
    elev = getattr(ctx, "elev_by_pos", None)
    neigh = neigh_map(ctx)
    best = None
    best_dist = DISTANCE_UNREACHABLE     # `int.MaxValue`
    best_adj = False
    for eid, q in _enemy_id_pos(ctx):
        d = get_distance([frm], [q])                     # `GetDistance(tilesA, u)`
        adj = are_entities_adjacent(frm, q, elev, neigh)  # `AreEntitiesAdjacent(tilesA, u)`
        if d < best_dist or (adj and not best_adj):
            best, best_dist, best_adj = (eid, q), d, adj
    return best


def _enemy_id_pos(ctx):
    """Les ennemis d'un contexte de decision en `(id, (col, row))` -- `ctx.enemies` d'abord (elle
    seule porte l'id), repli sur `ctx.epos` (id `None`). Cf. `get_nearest_enemy` (SUBSTRAT)."""
    out = []
    for e in (getattr(ctx, "enemies", None) or ()):
        p = (e or {}).get("pos") or {}
        if p.get("col") is None:
            continue
        out.append((e.get("id"), (p["col"], p["row"])))
    if out:
        return out
    return [(None, (p[0], p[1])) for p in (getattr(ctx, "epos", None) or ())]


def count_adjacent(tile: tuple, positions: list, elev_by_pos: dict | None = None,
                   neigh_by_pos: dict | None = None) -> int:
    """`GetAdjacentEnemies/Friends(tile).Count` — nombre d'unités de `positions` sur une tuile
    ADJACENTE à `tile`, au sens de `is_adjacent` (liste STOCKEE puis porte d'élévation)."""
    return sum(1 for p in (positions or [])
               if is_adjacent(tile, p, elev_by_pos, neigh_by_pos))


def count_adjacent_matching(tile: tuple, units: list, pred, elev_by_pos: dict | None = None,
                            neigh_by_pos: dict | None = None) -> int:
    """`Enumerable.Count(GetAdjacentEnemies(tile, unit, ignoreSteppables: false), pred)` — le
    comptage d'`is_adjacent` (donc la MÊME porte d'élévation d'`IterateAdjacentTiles`), mais sur des
    UNITÉS et non des positions nues, avec un prédicat par unité.

    Nécessaire dès que le natif filtre la liste rendue par `GetAdjacent*` au lieu de la compter en
    bloc : `...MartialExemplarPlaybook$$CalculateCustomUtility` compte les `IsNormalUnit`,
    `...TheLionsWrathPlaybook$$CalculateCustomUtility` les `IsNormalUnit && HasTrait(Chaos) &&
    HasTrait(Hero)`. `count_adjacent` reste le cas non filtré — les deux partagent `is_adjacent`,
    donc aucun fork d'adjacence.

    `units` = dicts d'unité de `decisionView` (`{"pos": {"col","row"}, ...}`) ; une unité sans
    position est ignorée (elle n'est sur aucune tuile, donc sur aucune tuile adjacente)."""
    n = 0
    for u in (units or []):
        p = (u or {}).get("pos") or {}
        if p.get("col") is None or p.get("row") is None:
            continue
        if is_adjacent(tile, (p["col"], p["row"]), elev_by_pos, neigh_by_pos) and pred(u):
            n += 1
    return n


def get_chained_units(unit, occupant_by_pos: dict, team_by_id: dict,
                      elev_by_pos: dict | None = None, neigh_by_pos: dict | None = None,
                      only_friends: bool = True) -> set:
    """`IdunBattle.Core.Services.BattleQuery$$GetChainedUnits(unit, onlyFriends,
    additionalCondition)` -- la COMPOSANTE CONNEXE d'unites atteinte de proche en proche depuis
    `unit`, `unit` COMPRISE.

    Le natif delegue a `IdunBattle.Core.Services.BattleQuery$$GetChainedUnitsInternal` apres avoir
    cree un `OrderedSet` vide ; l'interne, VERBATIM :

        tile = EntityExtensions.GetMainTileEntity(unit, state)
        adj  = GetAdjacentTiles(tile, null, onlyWalkable: true, allowTemporary: true)
        adj.Add(tile)                          # <- LA TUILE DE `unit` EST DANS L'ENUMERATION
        foreach t in adj:
            u = UnitExtensions.GetUnit(t, state);  if (u == null) continue
            if (alreadyChained.Contains(u)) continue
            if (onlyFriends && !UnitExtensions.IsFriend(u, unit, state)) continue
            if (additionalCondition != null && !additionalCondition(t)) continue
            alreadyChained.Add(u)
            GetChainedUnitsInternal(u, alreadyChained, onlyFriends, additionalCondition)
        return alreadyChained

    ⚠ `adj.Add(tile)` fait entrer la racine elle-meme des le premier niveau
    (`IsFriend(unit, unit)` est vrai) : une unite ISOLEE rend un ensemble de cardinal **1**, pas 0.
    C'est ce qui donne son sens au seuil `MIN_UTILITY = 2` de ses deux consommateurs (« il faut au
    moins un rebond »).

    FOYER PARTAGE, et c'est le natif qui le dit : `IBattleQuery` slot **16**
    (`data/symbols/<build>/metadata/interface_slots.tsv` : `IBattleQuery 16 GetChainedUnits 3`) est
    invoque a l'IDENTIQUE -- memes litteraux `(cible, onlyFriends: 1, additionalCondition: 0)` --
    par `IdunBattle.AI.Playbook.Loki.StormOfWrathPlaybook$$EvaluateNonComparable` (1019) et par
    `IdunBattle.AI.Playbook.Loki.KissOfDeathPlaybook$$EvaluateNonComparable` (1108). Un seul corps
    natif, donc un seul foyer porte : le dupliquer forkerait l'adjacence (#419-r1-tr14, meme geste
    pour `BattleQuery$$IsMeleeAttack`).

    SUBSTRAT. `occupant_by_pos` = `{(col, row): <id d'unite>}` et `team_by_id` = `{<id>: teamId}` --
    l'index inverse du `GetUnit(tile, state)` natif. `unit` absente de `team_by_id` -> ensemble
    VIDE (borne INF assumee : le port ne fabrique pas une chaine sur une unite qu'il ne voit pas).

    `additionalCondition` n'est PAS porte : il vaut `null` aux deux call-sites lus. `only_friends`
    est un parametre parce que le natif en fait un, mais les deux consommateurs passent `true`.
    """
    if unit not in team_by_id:
        return set()
    pos_by_id = {uid: p for p, uid in (occupant_by_pos or {}).items()}
    chained: set = set()
    stack = [unit]
    while stack:
        cur = stack.pop()
        src = pos_by_id.get(cur)
        if src is None:
            continue
        for p, uid in (occupant_by_pos or {}).items():
            if uid in chained:
                continue                                     # `alreadyChained.Contains(u)`
            # `adj.Add(tile)` : la tuile de `cur` fait partie de son propre voisinage.
            if p != src and not is_adjacent(src, p, elev_by_pos, neigh_by_pos):
                continue
            if only_friends and team_by_id.get(uid) != team_by_id.get(cur):
                continue                                     # `!IsFriend(u, unit, state)`
            chained.add(uid)
            stack.append(uid)                                # RECURSION du natif
    return chained


def is_surrounding(tile: tuple, pos: tuple, radius: int,
                   include_center_tile: bool = True) -> bool:
    """`pos` est-il dans le DISQUE de rayon `radius` autour de `tile` au sens de
    `IdunBattle.Core.Services.TileQuery.u003CIterateSurroundingTilesu003Ed__6$$MoveNext` ?

    L'itérateur natif est PUREMENT GEOMETRIQUE — triple boucle cube
    `for x in cx-R..cx+R: for y in cy-R..cy+R: for z in cz-R..cz+R: if (x+y+z == 0)` puis
    `CubeCoordinate.ToAxialCoordinate` + `StateExtensions.GetTileEntityAt` — c'est-a-dire le
    disque hex EXACT de rayon R. Trois differences DECISIVES avec `is_adjacent` (qui, lui,
    mirror `IterateAdjacentTiles`) :
      * AUCUNE porte d'elevation : le `abs(elev(a)-elev(b)) < 2` d'`IterateAdjacentTiles`
        n'existe pas dans ce corps ;
      * la tuile CENTRALE est emise sauf si le flag `d__6+0x52` est faux (`... || tile !=
        d__6+0x38`) -> parametre `include_center_tile` ;
      * le filtre `IsEmptyOrSteppable` (`d__6+0x50`) est optionnel et n'est PAS pose par le
        chemin `GetSurroundingUnits` (il retirerait toutes les tuiles occupees, donc toutes
        les unites cherchees).
    """
    d = hexgeo.distance((tile[0], tile[1]), (pos[0], pos[1]))
    if d == 0:
        return bool(include_center_tile)
    return d <= int(radius)


def count_surrounding(tile: tuple, positions: list, radius: int,
                      include_center_tile: bool = True) -> int:
    """`IdunBattle.Core.Services.BattleQuery$$GetSurroundingFriends(unit, tile, range, flag).Count`
    — nombre d'unites de `positions` dans le disque `is_surrounding`.

    Le natif enchaine `GetSurroundingFriends` -> `GetSurroundingUnits` (disque + `GetUnit` par
    tuile, doublons absorbes par l'`OrderedSet`) -> `ListExtensions.FilterInPlace(estAmiDe unit)`.
    `positions` porte donc DEJA le filtre de camp ; l'appelant decide s'il y inclut l'unite qui
    evalue (le natif ne l'exclut PAS : `GetSurroundingUnits` ne retire que les ENNEMIS via
    `UnitExtensions.IsEnemy`, cf. `AstartesBannerPlaybook` qui ne fait aucun test `!= case.unit`
    la ou `FirstAmongTraitorsPlaybook`, lui, en fait un explicite)."""
    return sum(1 for p in (positions or [])
               if is_surrounding(tile, p, radius, include_center_tile))


def get_in_range_aura_amount(effect_type, team, target, units, has_trait, get_turns_started,
                             return_first: bool = True) -> int:
    """`IdunBattle.Core.Services.BattleQuery$$GetInRangeAuraAmount(effectType, team, target,
    returnFirst)` -- MIRROR du decompile :

        aura = <effets>.GetEffect(effectType) as IAuraEffect
        if (aura == null) return 0                                   # cast d'interface ECHOUE
        trait    = aura.GetTrait()                                   # slot 0
        entities.<Target> = target
        maxRange = aura.GetMaxRange().Calculate(entities)            # slot 1 -> Direct(3)
        count = 0
        foreach (unit in GetSurroundingUnits(target, maxRange, friendsOf: null, includeCenter: false))
            if (!UnitExtensions.HasTrait(unit, trait))               continue
            if (EntityExtensions.GetCurrentTeamId(unit) != team)     continue
            entities.<Owner> = unit
            r = aura.GetCurrentRange().Calculate(entities)           # slot 2, evalue SUR le porteur
            if (r < GetDistance(unit, target))                       continue
            count++ ; if (returnFirst) break
        return count

    Le comparateur est **INCLUSIF** (`continue` seulement quand `r < d`, donc on compte des que
    `d <= r`).

    ⚠ Le predicat par-UNITE (`triggers.IsInUnitAura`) est INCLUSIF **lui aussi** : meme rayon
    effectif, aucune distinction a re-introduire. Il construit un
    `IdunBattle.Entities.Conditions.AmountIsEqualOrGreaterAbilityTrigger` (`minAmount <= amount`),
    et non l'`AmountIsGreaterAbilityTrigger` que suggere le nom du `.ctor` visible au decompile --
    ce ctor est un corps TRIVIAL DEDUPLIQUE par IL2CPP, dont la table ne nomme qu'un proprietaire
    (#293). Re-derivation mecanique :
    `python scripts/python/probe_293_aura_predicate_comparator.py --inventory`.

    Les deux partagent EXACTEMENT le meme etage de portee (`entities/effects/aura.py`
    -> `GetTrait` + `GetCurrentRange`), ce qui rend la version EQUIPE confrontable live (elle est
    exposee par `abilityTargets`) et l'etage commun mesurable.

    `IdunBattle.Core.Services.BattleQuery$$IsInTeamAuraRange` = ce compte `> 0` avec
    `returnFirst = true` -> `is_in_team_aura_range` ci-dessous.

    Substrat du port : `target`/`units` = dicts d'unite DSL (`{id, team, pos}`) ; `has_trait(unit,
    traitId)->bool` et `get_turns_started(unit)->int` sont les DEUX accesseurs que le natif prend
    respectivement par `UnitExtensions.HasTrait` et par `StatAmount(Owner, 0xc)`. Le balayage
    `GetSurroundingUnits` est mirrore par `is_surrounding(..., include_center_tile=False)` -- le
    disque hex PUR de `TileQuery.IterateSurroundingTiles`, sans porte d'elevation. Une unite MORTE
    n'est plus sur sa tuile cote natif (`KillUnit` la retire du board) -> exclue ici aussi."""
    from .entities.effects.aura import aura_trait, aura_max_range, aura_current_range
    trait = aura_trait(effect_type)
    if trait is None:
        return 0                                             # `as IAuraEffect` == null
    max_range = aura_max_range(effect_type)
    tp = (target or {}).get("pos")
    if tp is None or tp.get("col") is None:
        return 0                                             # cible sans tuile -> aucun voisinage
    tkey = (tp["col"], tp["row"])
    count = 0
    for u in (units or []):
        if not isinstance(u, dict) or u.get("id") == (target or {}).get("id"):
            continue
        if not bool(u.get("alive", True)) or (u.get("hp") or 0) <= 0:
            continue                                         # un mort n'occupe plus de tuile
        p = u.get("pos")
        if p is None or p.get("col") is None:
            continue
        upos = (p["col"], p["row"])
        if not is_surrounding(tkey, upos, max_range, include_center_tile=False):
            continue                                         # hors `GetSurroundingUnits(target, max)`
        if not has_trait(u, trait):
            continue                                         # `!HasTrait(unit, aura.GetTrait())`
        if u.get("team") is None or int(u["team"]) != int(team):
            continue                                         # `GetCurrentTeamId(unit) != team`
        r = aura_current_range(effect_type, int(get_turns_started(u) or 0))
        if int(r or 0) < hexgeo.distance(upos, tkey):
            continue                                         # `r < GetDistance(unit, target)`
        count += 1
        if return_first:
            break
    return count


def is_in_team_aura_range(effect_type, team, target, units, has_trait, get_turns_started) -> bool:
    """`IdunBattle.Core.Services.BattleQuery$$IsInTeamAuraRange(effectType, team, target)` -- MIRROR :
    `GetInRangeAuraAmount(effectType, team, target, returnFirst: true) > 0`."""
    return get_in_range_aura_amount(effect_type, team, target, units, has_trait,
                                    get_turns_started, return_first=True) > 0


def is_charging(caster_pos: tuple | None, target_pos: tuple | None, target_id,
                charged_unit_ids, elev_by_pos: dict | None = None,
                neigh_by_pos: dict | None = None) -> bool:
    """`IdunBattle.Core.Services.BattleQuery$$IsCharging(caster, target)` — MIRROR du decompile,
    DEUX termes joints par `&` :

        return AreEntitiesAdjacent(caster, target)
               && GetComponent<UnitComponent>(caster).ChargedUnitIds@+0x190.Contains(target.Id)

    FOYER UNIQUE du predicat de CHARGE cote port (case-231 pour le socle, case-r32 pour ce cablage).
    Les DEUX faces l'appellent : le COMBAT lui passe la liste reelle du `UnitComponent`
    (`components.charged_unit_ids`, alimentee par `MoveUnitOperation$$UpdateCharging` et videe par
    `FinishUnitTurnOperation$$Execute`), la PREDICTION lui passe la liste que le pas CANDIDAT
    produirait (meme mirror d'`UpdateCharging`, applique a la tuile evaluee).

    ⚠ « charger » n'est PAS « avoir bouge » (`UnitFlag.Moved`) : une unite qui bouge SANS arriver au
    contact, ou qui etait DEJA adjacente avant son pas, n'a pas charge — `UpdateCharging` n'ajoute que
    les unites NOUVELLEMENT adjacentes. Le proxy `has_moved` est donc strictement PLUS LARGE (il
    sur-accorde), et c'est exactement l'ecart que ce foyer supprime.

    `AreEntitiesAdjacent` = `MovementUtil$$AreTilesAdjacent(GetTiles(caster), GetTiles(target))`, dont
    l'overload scalaire vaut `abs(elev(b) - elev(a)) < 2 && (a == b || ConnectivityComponent(a).
    IsNeighbour(b))` -> `are_entities_adjacent` ci-dessus, et NON `is_adjacent` : ce dernier mirrore
    `IterateAdjacentTiles`, qui ne rend jamais la tuile source, alors que la primitive de PORTEE
    porte le COURT-CIRCUIT D'IDENTITE (#433-r1).

    ⚠ LE SUBSTRAT DE VOISINAGE EST LA LISTE STOCKEE, pas la couronne hex (#433-r4-r1-r4-r2-r1) --
    `IdunBattle.Entities.Components.ConnectivityComponent$$IsNeighbour` est LU comme
    `this[+0x10].Contains(<id de tile2>)`, c'est-a-dire exactement la `List<int>` que
    `IdunBattle.Operations.InitializeConnectivityOperation$$Execute` construit, celle-la meme
    qu'enumere `IdunBattle.Core.Services.TileQuery.u003CIterateAdjacentTilesu003Ed__8$$MoveNext`.
    Les DEUX natifs partagent donc le meme substrat ; ils ne different que par le court-circuit
    d'identite. D'ou `neigh_by_pos`, propage tel quel a `are_entities_adjacent` -> `is_adjacent`.
    Rejouer la porte d'elevation sur le canal capte reste idempotent (cf. `is_adjacent`) : dans
    `MovementUtil$$AreTilesAdjacent` elle est un terme SEPARE (`iVar7 < 2 & bVar3`), et le canal la
    porte deja.

    Canal absent (`neigh_by_pos=None`) -> repli GEOMETRIQUE nomme dans `is_adjacent` ;
    `elev_by_pos=None` degrade en hex pur.

    ⚠ Le court-circuit est ici SANS EFFET OBSERVABLE, et par COMPOSITION -- pas par chance : le 2e
    terme (`ChargedUnitIds.Contains`) est ecrit par `MoveUnitOperation$$UpdateCharging`, qui n'ajoute
    que les unites NOUVELLEMENT rendues par `GetAdjacentUnits` (donc `IterateAdjacentTiles`, qui ne
    rend JAMAIS la tuile d'arrivee elle-meme). Une unite partageant la tuile du caster n'entre donc
    jamais dans cette liste, et la conjonction reste FAUSSE des deux cotes. Le mirror est pose par
    FIDELITE, pas parce qu'un regime l'exige.

    Position manquante (unite hors plateau) -> False (le natif deref `MainTile` et sortirait ; la
    degradation fidele est « pas de charge »)."""
    if caster_pos is None or target_pos is None or target_id is None:
        return False
    if not are_entities_adjacent(caster_pos, target_pos, elev_by_pos,
                                 neigh_by_pos):                          # AreEntitiesAdjacent
        return False
    return int(target_id) in {int(i) for i in (charged_unit_ids or ())}   # ChargedUnitIds.Contains


def newly_adjacent_ids(old_pos, new_pos, positions_by_id: dict,
                       elev_by_pos: dict | None = None,
                       neigh_by_pos: dict | None = None) -> set:
    """`IdunBattle.Operations.MoveUnitOperation$$UpdateCharging` — volet SPATIAL : les ids ADJACENTS
    a la position d'ARRIVEE qui ne l'etaient PAS a la position de DEPART.

        before = GetAdjacentUnits(oldPosition, unit) ; after = GetAdjacentUnits(newPosition, unit)
        foreach u in after: if (!before.Contains(u)) ChargedUnitIds.Add(u.Id)

    ⚠ « ADJACENT » Y EST `IterateAdjacentTiles`, PAS `hexgeo.distance == 1` (#433-r4-r1-r4-r2-r1).
    La chaine est LUE : `IdunBattle.Core.Services.BattleQuery$$GetAdjacentUnits(from, ...)` =
    `IterateAdjacentTiles(from, ...)` puis `GetUnitsOnTiles(...)`, et
    `IdunBattle.Core.Services.TileQuery.u003CIterateAdjacentTilesu003Ed__8$$MoveNext` enumere la
    liste STOCKEE du `ConnectivityComponent` (`+0x10`) puis applique la porte `|dElev| < 2`. Le port
    ne portait NI l'un NI l'autre : DEUX etages manquants, tous deux PERMISSIFS (la couronne hex
    sur-atteint la liste stockee de 4 aretes dirigees sur `C1_74` et 38 sur `C3_14`, cf. #433-r4-r1-r4-r2).
    D'ou la delegation a `is_adjacent`, qui est le mirror des DEUX etages -- et non un second port.

    `positions_by_id` = {id: (col,row)} des AUTRES unites (l'unite qui bouge en est exclue par le
    natif via son parametre `unit`). `old_pos=None` (unite sans MainTile avant le pas, ex. spawn) ->
    `before` vide, mirror du `MainTile == null` natif. Canaux absents -> repli GEOMETRIQUE nomme
    d'`is_adjacent` (le comportement d'avant), jamais un voisinage vide.

    Le pendant ECS vit dans `runner.components.update_charging` (il MUTE le `UnitComponent`) et doit
    voir le MEME substrat, sinon les faces PREDICTION et COMBAT divergent sur un natif unique ; ici
    on ne rend que l'ensemble, ce dont la face PREDICTION a besoin pour savoir ce qu'un pas CANDIDAT
    chargerait sans muter quoi que ce soit."""
    def _adj(p):
        if p is None:
            return set()
        return {int(i) for i, q in (positions_by_id or {}).items()
                if q is not None and is_adjacent(tuple(p), tuple(q), elev_by_pos, neigh_by_pos)}
    return _adj(new_pos) - _adj(old_pos)


def will_be_charging(target_id, cur_pos, from_pos, positions_by_id: dict,
                     elev_by_pos: dict | None = None,
                     neigh_by_pos: dict | None = None) -> bool:
    """`IdunBattle.Core.Services.BattleQuery$$WillBeCharging(caster, fromTile, target)`
    (`IBattleQuery` slot 0xcd, arite 3 -- LUE dans
    `data/symbols/<build>/metadata/interface_slots.tsv`, jamais devinee) -- MIRROR :

        current = GetAdjacentUnits(GetUnitPosition(caster), null, <joueur du caster>, false)
        newly   = []
        foreach u in GetUnitsOnTiles(IterateAdjacentTiles(fromTile, null, true, true),
                                     null, <joueur du caster>, false)
            if (!current.Contains(u)) newly.Add(u.Id)
        return newly.Contains(target.Id)

    C'est le pendant PROSPECTIF d'`is_charging` : « si le caster se pose sur `from_pos`, la cible
    lui deviendra-t-elle NOUVELLEMENT adjacente ? ». Le natif reutilise exactement la paire
    before/after de `IdunBattle.Operations.MoveUnitOperation$$UpdateCharging` -- d'ou la delegation
    a `newly_adjacent_ids`, qui EST ce corps-la (meme primitive `is_adjacent`, donc meme liste
    STOCKEE et meme porte d'elevation). Ecrire ici une seconde adjacence ferait diverger le
    predicat de DECISION du predicat de COMBAT sur un natif unique.

    ⚠ `is_charging` et `will_be_charging` ne sont PAS interchangeables : le premier lit la liste
    DEJA constituee (`UnitComponent.ChargedUnitIds`, donc un pas DEJA joue), le second n'a besoin
    d'aucun etat -- il compare deux voisinages. `TacticalPrecisionPlaybook` interroge le second,
    parce qu'il score une position CANDIDATE que le caster n'a pas encore prise.

    `from_pos = None` -> repli sur `cur_pos` (le natif recoit alors la tuile courante, et l'ensemble
    `newly` est vide : aucune charge). `target_id` absent -> False."""
    if target_id is None:
        return False
    frm = cur_pos if from_pos is None else from_pos
    return int(target_id) in newly_adjacent_ids(cur_pos, frm, positions_by_id,
                                                elev_by_pos, neigh_by_pos)


def in_arc(tile: tuple, pos: tuple) -> bool:
    """`pos` est-il dans l'ARC de `tile` (ring-1 UNION ring-2) ? = dist hex <= 2, **GEOMETRIQUE PUR**.

    ⚠ CE PREDICAT NE PASSE PAS PAR `IterateAdjacentTiles` — donc ni liste stockee, ni porte
    d'elevation (#433-r4-r1-r4-r2-r1). La chaine native de l'ELIGIBILITE est LUE de bout en bout :

        BasePlaybook$$GetEligibleTargetsSelectable  ->  IBattleQuery slot 0x42
          -> AttackQuery$$GetValidTargetsWithCache -> TargetingQuery$$GetValidTargets
          -> TargetingQuery$$GetUnitsInRange -> BattleQuery$$GetUnitsAtDistance
          -> BattleQuery$$GetTilesAtDistance -> BattleQuery$$GetSurroundingTiles
          -> TileQuery.u003CIterateSurroundingTilesu003Ed__6$$MoveNext

    `IdunBattle.Core.Services.BattleQuery$$GetTilesAtDistance` filtre le disque de
    `IdunBattle.Core.Services.BattleQuery$$GetSurroundingTiles` par
    `IdunBattle.Entities.Components.PositionComponent$$Distance(t, centre) == distance` — une
    distance hexagonale, sur un disque cube PUREMENT geometrique. **Aucun `ConnectivityComponent`,
    aucun `|dElev| < 2` sur ce chemin** ; brancher `neigh_by_pos` ici FABRIQUERAIT une divergence.

    C'est aussi ce que la mesure live disait deja : `eligible_targets_count` ci-dessous porte
    « ennemis a dist <= 2, SANS porte d'elevation au ring-1 » avec son datapoint (probe_49x phase B,
    `C1_25` : T=(0,2) elev 4, ennemi (1,3) elev 2 adjacent -> `|dElev| = 2` l'exclurait via
    `IterateAdjacentTiles`, or le natif GENERE une action). Les deux fonctions mirroraient le MEME
    natif en se contredisant sur le ring-1 : `in_arc` gatait, `eligible_targets_count` non. Le fork
    est ferme du cote LU — la porte est retiree, le parametre `elev_by_pos` avec elle (un parametre
    accepte mais non lu se refait passer un jour pour un canal actif).

    ring-2 : `Unobscured` PASSE-TOUT v1 pour ce predicat d'ELIGIBILITE (non exerce par les seeds ;
    cf. `is_target_tile_obscured` si un cas le falsifie). Predicat PARTAGE par
    `count_enemies_in_arc` (gate d'eligibilite par-position) et `enemies_in_arc` (cible emise).

    dist 0 : hors regime, et le natif n'y repond PAS par la distance --
    `IdunBattle.Core.Services.TargetingQuery$$GetUnitsInRange` traite `range == 0` a part et rend
    `{caster}` ou l'ensemble VIDE selon le bit 15 des `options`, jamais le disque. Les appelants ne
    passent que des positions d'ENNEMIS, jamais celle du caster, donc `<= 2` et `1 <= d <= 2` sont
    indiscernables ici ; `<= 2` est retenu pour etre litteralement `eligible_targets_count`."""
    return hexgeo.distance((tile[0], tile[1]), (pos[0], pos[1])) <= 2


def count_enemies_in_arc(tile: tuple, positions: list) -> int:
    """`IdunBattle.AI.Playbook.BasePlaybook$$GetEligibleTargetsSelectable(unit, MainTile(T))` (compte) — nombre
    d'unités de `positions` (ennemis) dans l'ARC de `tile` = ring-1 UNION ring-2 (`in_arc`), l'ensemble
    des CIBLES ÉLIGIBLES depuis la position T. C'est le set ancré à T que le natif énumère pour
    `GenerateAction(pos, eligible_target, util)` : si ce set est VIDE à T, AUCUNE action n'est générée
    (bucket vide) quelle que soit l'utilité — gate PROUVÉ live (probe_49x_realanchor phase B, C1_25 :
    23/23 positions, les 6 vides = exactement celles sans ennemi à dist <= 2 de T).
    ⚠ CASE-49x (2026-07-21) : ce compte n'est PAS l'utilité Gauntlets. L'utilité =
    `|ring1(T) ∪ surrounding_enemies(TUILE RÉELLE)|` (cf. `surrounding_enemies` + le playbook) —
    la conclusion antérieure « ring-2 mort » (case-49 §2bis) confondait les deux ancrages.
    ⚠ #433-r4-r1-r4-r2-r1 : `in_arc` est GEOMETRIQUE PUR (ni liste stockee ni porte d'elevation) —
    la chaine native de l'eligibilite passe par `GetTilesAtDistance`, pas par `IterateAdjacentTiles`
    (lecture complete dans `in_arc`). Ce compte devient donc l'exact jumeau d'`eligible_targets_count`.
    AUCUN appelant dans le depot (mesure du 2026-08-04, balayage AST de `git ls-files *.py`)."""
    return sum(1 for p in (positions or []) if in_arc(tile, p))


def eligible_targets_count(tile: tuple, positions: list,
                           elev_by_pos: dict | None = None) -> int:
    """`BasePlaybook.GetEligibleTargetsEntities(unit, MainTile(T))` (via `IdunBattle.AI.Playbook.BasePlaybook$$GetEligibleTargetsSelectable`) — nombre de CIBLES ÉLIGIBLES depuis la position T = ennemis à dist hex <= 2 de T,
    **SANS porte d'élévation au ring-1** : PROUVÉ live (probe_49x phase B, C1_25 : T=(0,2) elev 4,
    ennemi (1,3) elev 2 adjacent -> |Δelev|=2 exclurait via IterateAdjacentTiles, or le natif GÉNÈRE
    une action -> l'éligibilité n'utilise pas cette porte, contrairement au terme utilité
    `AdjacentTiles`). Si 0 : la boucle `GenerateAction` n'est jamais entrée -> bucket VIDE à T quelle
    que soit l'utilité (gate par-position, 23/23 sur E1-repro). v1 FLAG : dist-2 sans filtre
    Unobscured (non exercé par les mesures ; cf. `is_target_tile_obscured` si un cas le falsifie)."""
    tk = (tile[0], tile[1])
    return sum(1 for p in (positions or [])
               if hexgeo.distance(tk, (p[0], p[1])) <= 2)


def is_target_tile_obscured(frm: tuple, to: tuple, elev_by_pos: dict | None = None) -> bool:
    """`IdunBattle.Core.Services.TargetingQuery$$IsTargetTileObscured` -> `IdunBattle.Core.Services.MovementQuery$$GetTilesObscuringTerrain` (mask 6 : élévation bit 2 + murs bit 4 — pas d'IndirectFire ici), TERRAIN uniquement,
    restreint à dist hex == 2 (le seul cas où le playbook NC l'exerce ; à dist 1 le natif ne teste
    rien : `2 < count` faux -> jamais obscurci ; dist > 2 hors périmètre Gauntlets).

    Élévation (`DetermineBlockingTiles IdunBattle.Core.Services.MovementQuery$$u003CGetTilesObscuringTerrainu003Eg__DetermineBlockingTiles|40_0`, seuil closure[3]=2) : la ligne from->to (dist 2,
    count=3) teste l'UNIQUE tuile intermédiaire idx=1 (== count-2) contre elev(from) PUIS elev(to) ;
    bloque si `elev(mid) - elevRef >= 2` pour l'UNE des deux réfs. Fat-line (lignes A/B ±eps ->
    candidates différentes = les 2 voisins communs) : bloque SSI les DEUX candidates passent le
    seuil pour la MÊME réf (`bVar1 & bVar2`). Mids offline = voisins communs hexgeo (bit-exact
    cube-line pour dist 2 : trajet droit -> 1 mid ; diagonal -> midpoint sur l'arête -> ±eps
    départage les 2 candidates). LIMITES v1 (flaggées) : murs (bit 4) non modélisés (aucun
    `wall_by_pos` offline ; aucun board d'agreement n'a de mur en zone jouable) ; nudge eps natif
    (FloatCube @DAT_1832593f8+0xb8) supposé départager les 2 candidates du cas diagonal (si les
    lignes A/B tombaient sur la MÊME candidate, le natif bloquerait sur elle seule)."""
    fk, tk = (frm[0], frm[1]), (to[0], to[1])
    if hexgeo.distance(fk, tk) != 2 or not elev_by_pos:
        return False
    ef, et = elev_by_pos.get(fk), elev_by_pos.get(tk)
    if ef is None or et is None:
        return False
    mids = [p for p in hexgeo.neighbors(*fk) if hexgeo.distance((p[0], p[1]), tk) == 1]
    mids = [elev_by_pos[p] for p in mids if p in elev_by_pos]   # GetTileAt null -> pas bloquant
    if not mids:
        return False
    if len(mids) == 1:                                          # ligne DROITE : 1 seul mid
        return (mids[0] - ef >= 2) or (mids[0] - et >= 2)
    blk_f = all(m - ef >= 2 for m in mids)                      # fat-line : ET des 2 candidates
    blk_t = all(m - et >= 2 for m in mids)
    return blk_f or blk_t


def is_tile_valid_for_list(tile: tuple, ref: tuple | None, check_walkable: bool,
                           walkable_at=None, elevation_at=None,
                           check_elevation: bool = True, is_wall_at=None) -> bool:
    """`IdunBattle.Core.Services.TileUtil$$IsTileValidForList(tile, refTile, checkWalkable,
    checkElevation)` en domaine POSITION. Le 4e argument natif est un LITTERAL, different par
    call-site porte -> il est ici un PARAMETRE, jamais une deduction :
      * `IdunBattle.Core.Services.BattleQuery$$GetTilesBehind` passe `1` (defaut) ;
      * `IdunBattle.Core.Services.TileQuery.u003CIterateSurroundingTilesu003Ed__6$$MoveNext` passe
        `0` (cf. `get_surrounding_tiles`) — le disque `SurroundingTiles` n'a AUCUNE porte
        d'elevation, contrairement au ring-1 `IterateAdjacentTiles`.

        if (tileComponent+0x41 != 0)            return false            # mur
        if (!checkWalkable)                     return tileComponent+0x40 == 0
        if (!TileExtensions.IsWalkable(tile))   return false
        if (!checkElevation)                    return true
        if (refTile != null)                    return |elev(ref) - elev(tile)| < 2

    Le gate d'ELEVATION vit DANS la branche walkable : `checkWalkable == False` le desactive AUSSI.
    C'est la consequence non evidente qui a coute la face COMBAT (#117) puis la face DECISION (#124).

    `walkable_at(pos) -> bool` / `elevation_at(pos) -> int|None` : accesseurs injectes (board du
    runner cote COMBAT, `walkable_by_pos`/`elev_by_pos` cote DECISION). Accesseur absent ou donnee
    manquante -> le gate correspondant est INERTE (borne SUPERIEURE : on ne coupe jamais une ligne
    a l'aveugle).

    ⚠ **`is_wall_at` SEPARE LES DEUX GATES QUE LE PORT FONDAIT, et la fonte n'etait PAS inerte
    (#889-r6).** Le natif teste `+0x41` (le MUR) INCONDITIONNELLEMENT, puis met `IsWalkable` DANS la
    branche `checkWalkable`. Le port appliquait `walkable_at` inconditionnellement -- une
    degradation RESTRICTIVE, qui coupe la ligne la ou le natif la continue. La docstring precedente
    la disait << inerte pour les call-sites portes >> ; elle ne l'est plus, et la mesure est directe
    (board `CE6_boss`, `...InstrumentsOfVengeanceAbility$$GetEffectBehavior`, `settings = null` donc
    `checkWalkable = 0`) :

      * le natif MARQUE `(6,4)` et `(6,6)`, deux tuiles `Unplayable` (`walkable = false`,
        `isWall = false`), et traverse aussi les `Block` -- donc **NI `Block` NI `Unplayable` ne
        posent `+0x40`** ;
      * le port s'arretait dessus, ce qui RACCOURCISSAIT `Count(TilesBehindInLine(...))` de 6 a 5
        sur une tuile candidate -- et cette longueur est une CLE DE TRI de 1215. La ligne choisie
        n'etait donc pas la meme : divergence de SELECTION, pas de geometrie.

    Ce qui reste NON PORTE, et c'est nomme : `+0x40` lui-meme, dont aucun substrat offline ne publie
    la valeur (le `boardGraph` donne `walkable`, `isWall`, `isTemporary`, `isInFog`, `tileDefId` --
    aucun ne coincide avec les deux mesures ci-dessus). Le gate reste donc INERTE, borne SUPERIEURE,
    comme tout accesseur absent. `is_wall_at` absent -> ANCIEN comportement (fonte), pour ne pas
    changer un call-site qui ne cable pas le nouveau substrat."""
    if is_wall_at is not None:
        # ORDRE NATIF : `+0x41` (mur) d'abord et INCONDITIONNEL, `IsWalkable` seulement ensuite.
        if is_wall_at(tile):
            return False
        if not check_walkable:
            return True                   # `return tileComponent+0x40 == 0` -- gate INERTE (pas de substrat)
        if walkable_at is not None and not walkable_at(tile):
            return False
    elif walkable_at is not None and not walkable_at(tile):
        return False                      # substrat FONDU (pas d'`is_wall_at`) : comportement d'avant
    if not check_walkable:
        return True                       # branche `!checkWalkable` : PAS de gate d'elevation
    if not check_elevation:
        return True                       # 4e argument natif == 0 (`IterateSurroundingTiles`)
    if ref is None or elevation_at is None:
        return True
    et, er = elevation_at(tile), elevation_at(ref)
    if et is None or er is None:
        return True                       # elevation inconnue -> gate inerte (borne SUP)
    return abs(er - et) < 2


def get_tiles_behind(frm: tuple, to: tuple, max_count: int | None = None,
                     check_walkable: bool = False, update_reference: bool = False,
                     walkable_at=None, elevation_at=None, tile_exists=None,
                     is_wall_at=None) -> list:
    """`IdunBattle.Core.Services.BattleQuery$$GetTilesBehind(from, to, checkWalkable,
    updateReference, maxCount)` en domaine POSITION — LE mirror UNIQUE de la ligne hex, consomme
    par la face COMBAT (`engine.entities.selectors.TilesBehindInLine`) ET par les deux feuilles de
    DECISION (`DarkTalonStrikePlaybook`, `ExcruciatingFrequenciesPlaybook`).

        dir = CubeCoordinate.DirectionTo(cube(from), cube(to))
        ref = MainTileEntity(from)                       # tuile de REFERENCE d'elevation
        cur = cube(from)
        loop:
            if maxCount.HasValue && maxCount.Value <= list.Count : return list
            next = cur - dir                             # 1re iteration -> `to`
            tile = GetTileEntityAt(next) ; if (tile == null) return list
            if (!TileUtil.IsTileValidForList(tile, ref, checkWalkable, 1)) return list
            list.Add(tile)
            if (updateReference) ref = tile              # la reference SUIT la ligne
            cur = next

    La ligne S'ARRETE au 1er echec (`return list`) : c'est un PREFIXE, pas un filtre. Geometrie CUBE
    droite (parite-INDEPENDANTE) : `tile_k = cube(from) + (k+1)*step`, ou
    `step = -DirectionTo(cube(from), cube(to))` -- le PAS UNITAIRE de `from` vers `to`. La 1re tuile
    rendue est `from + step` et la reference initiale est `from`.

    ⚠ **Le pas est UNITAIRE, et il ne l'etait pas (`#510-r2`).** Le mirror posait
    `dir = cube(to) - cube(from)` SANS clamp, la ou `IdunBattle.Utils.Hex.CubeCoordinate$$DirectionTo`
    fait `Max(Min(delta, 1), -1)` **par composante** (le mirror `direction_to` ci-dessous, lui, etait
    exact -- l'ecart etait ICI, au site qui ne l'appelait pas). Les deux coincident exactement quand
    `to` est ADJACENT a `from` -- le regime de TROIS des quatre call-sites recenses ci-dessous et de
    tous les montages joues jusqu'ici -- et divergent des que la cible est plus loin : la ligne
    avancait alors par bonds de `d(from, to)`, sautant `d - 1` tuiles a chaque pas. Dans ce regime
    les gates `tile_exists` / `IsTileValidForList` n'etaient meme pas evalues sur les tuiles sautees,
    donc la ligne pouvait TRAVERSER un mur sans s'arreter -- degradation PERMISSIVE, silencieuse.
    Trouve en portant `#498-r1` (`UnstoppableMomentumReworked` est la 1re ability portee dont la
    cible n'est pas adjacente). Son playbook contourne en passant le PAS UNITAIRE comme `to`
    (`unstoppable_momentum._first_step`) : ce contournement devient un NO-OP exact une fois le clamp
    pose (`clamp(from - (from + step)) == -step`), il n'a donc pas besoin d'etre retire, et le
    retirer ne changerait rien.

    `check_walkable` / `update_reference` = les DEUX bools de la struct `settings` que chaque
    call-site alloue et passe a `IdunBattleLogic.Entities.DSLFactory$$TilesBehindInLine` (champs
    `+0x10` / `+0x11`). INVENTAIRE des call-sites (LU au decompile, #117) :
      | `DarkTalonStrikeAbility$$GetTilesInLine`            | 1 | 1 |
      | `ExcruciatingFrequenciesAbility$$GetAffectedTiles`  | 1 | 1 |
      | `DeathOnTheWindAbility$$GetTilesInLine`             | 0 | 1 |
      | `ThriceBlessedConflagrationAbility$$GetTilesInLine` | 0 | 0 |
    Defauts `False/False` = le comportement de ThriceBlessedConflagration.

    `tile_exists(pos) -> bool` mirrore `GetTileEntityAt(next) == null -> return list` (bord du
    plateau). Absent -> pas de borne de plateau ; `max_count is None` retombe alors sur le
    garde-fou `k > 64`."""
    ox, _oy, oz = hexgeo.to_cube(frm[0], frm[1])
    # `dir = CubeCoordinate$$DirectionTo(cube(from), cube(to))` = `clamp(from - to, -1, +1)`, puis
    # `next = cur - dir`. Le pas d'avance est donc `-dir`, UNITAIRE par composante (#510-r2). On
    # passe par le foyer `direction_to` plutot que de re-transcrire le clamp : deux transcriptions
    # du meme natif, c'est deux endroits ou il peut devenir faux.
    ddx, _ddy, ddz = direction_to(frm, to)
    dx, dz = -ddx, -ddz
    if dx == 0 and dz == 0:
        return []
    out, ref, k = [], (frm[0], frm[1]), 0
    while max_count is None or len(out) < max_count:
        p = hexgeo.from_cube(ox + dx * (k + 1), oz + dz * (k + 1))
        if tile_exists is not None and not tile_exists(p):
            break                          # `GetTileEntityAt == null` -> fin de ligne
        if not is_tile_valid_for_list(p, ref, check_walkable, walkable_at, elevation_at,
                                      is_wall_at=is_wall_at):
            break                          # `return list` natif : PREFIXE, pas un filtre
        out.append(p)
        if update_reference:               # settings+0x11 : la reference d'elevation suit la ligne
            ref = p
        k += 1
        if max_count is None and k > 64:   # garde-fou (plateau borne ; jamais atteint)
            break
    return out


def direction_to(frm: tuple, to: tuple) -> tuple:
    """`IdunBattle.Utils.Hex.CubeCoordinate$$DirectionTo(toPositionCube)` -- MIRROR du decompile,
    en domaine POSITION (odd-q), retour en CUBE `(x, y, z)`.

    Corps natif (convention x64 : `RCX` = buffer de retour, `RDX` = `this`, `R8` = l'argument --
    Ghidra decale d'un cran et nomme `RDX` `toPositionCube`, d'ou la lecture par les registres) :

        c0 = Max(Min(to.x - this.x, 1), -1)
        c1 = Max(Min(to.y - this.y, 1), -1)
        c2 = Max(Min(to.z - this.z, 1), -1)
        return (-c0, -c1, -c2)                       # soit clamp(this - to, -1, 1)

    Donc **`a.DirectionTo(b) == clamp(a - b, -1, +1)`**, composante par composante : un pas
    UNITAIRE pointant de `b` VERS `a`. Le sens est contre-intuitif et c'est ce que confirme le seul
    autre consommateur porte, `get_tiles_behind` : il pose `dir = DirectionTo(cube(from), cube(to))`
    puis avance par `next = cur - dir` en partant de `cur = from`, et sa 1re tuile rendue EST `to`
    -- ce qui n'est vrai que si `dir` pointe de `to` vers `from`.

    ⚠ Le clamp est INDEPENDANT par composante : sur un delta non aligne, la somme des trois
    composantes du resultat n'est pas forcement nulle (donc ce n'est pas toujours un vecteur cube
    canonique). C'est le comportement NATIF, transcrit tel quel -- ne pas le "corriger"."""
    fx, fy, fz = hexgeo.to_cube(frm[0], frm[1])
    tx, ty, tz = hexgeo.to_cube(to[0], to[1])
    clamp = lambda v: max(min(v, 1), -1)                       # noqa: E731 -- Max(Min(v,1),-1) natif
    return (clamp(fx - tx), clamp(fy - ty), clamp(fz - tz))


def get_tile_behind_target_from_source_direction(source: tuple, target: tuple,
                                                 tile_exists=None) -> list:
    """`IdunBattle.Core.Services.BattleQuery$$GetTileBehindTargetFromSourceDirection(sourceTile,
    targetTile)` en domaine POSITION -- MIRROR du decompile :

        a = GetMainTile(sourceTile) ; b = GetMainTile(targetTile)
        if (a == b)                       return new List<TileEntity>()     # meme tuile -> VIDE
        dir  = cube(a).DirectionTo(cube(b))            # = clamp(cube(a) - cube(b), -1, +1)
        res  = cube(b) - dir                           # = cube(b) + clamp(cube(b) - cube(a), -1, +1)
        tile = state.GetTileAt(res.ToAxialCoordinate())
        return tile != null ? tile.ToList() : new List<TileEntity>()

    En clair : **la tuile adjacente a la CIBLE, dans la direction source -> cible** -- « un pas
    au-dela de la cible ». C'est ce que la fiche i2 de `Loki_SwoopingHawk` decrit par « Lands in
    the hex directly behind the last target hit ».

    L'ORDRE DES ARGUMENTS a ete tranche au ctor, pas au nom : `TileBehindTargetFromSourceDirection
    Selector$$.ctor(this, state, query, targetTileSelector, sourceTileSelector)` ecrit
    `+0x18 = sourceTileSelector` et `+0x20 = targetTileSelector`, et
    `...Selector$$Select` appelle `query.<slot 0x59>(Select(+0x18), Select(+0x20))` -- donc bien
    `(source, target)`, dans cet ordre. Les inverser rendrait la tuile situee DEVANT la cible
    (entre elle et le caster), ce qui est directement observable en live.

    AUCUN gate de walkabilite / d'occupation ici : le natif rend la tuile telle quelle, et c'est
    le `CanAddUnit(...)` du call-site (`DiveAttackAbilityBase$$GetMovementBehavior`) qui filtre.
    `tile_exists(pos) -> bool` mirrore `GetTileAt(res) == null -> liste vide` (bord du plateau)."""
    if source is None or target is None:
        return []
    if (source[0], source[1]) == (target[0], target[1]):        # `a == b` -> List vide
        return []
    dx, dy, dz = direction_to(source, target)
    bx, by, bz = hexgeo.to_cube(target[0], target[1])
    p = hexgeo.from_cube(bx - dx, bz - dz)                      # `res = cube(b) - dir`
    if tile_exists is not None and not tile_exists(p):
        return []                                              # `GetTileAt == null`
    return [p]


def is_on_straight_line(a: tuple, b: tuple) -> bool:
    """`IdunBattle.Utils.Hex.AxialCoordinate$$IsOnStraightLine(this, coordinate)` -- MIRROR du
    decompile, en domaine POSITION (odd-q).

    Corps natif (`this` = `a`, champs `+0x0 = col`, `+0x4 = row`, `+0x8 = offsetType`) :

        aAdj = a.row - ((a.offsetType == 0 ? (a.col & 1) + a.col : a.col & ~1) / 2)
        bAdj = b.row - ((b.offsetType == 0 ? (b.col & 1) + b.col : b.col & ~1) / 2)
        if (a.offsetType != b.offsetType) throw
        d = (b.col + bAdj) - (a.col + aAdj)
        if (a.col != b.col && d != 0) return aAdj == bAdj
        return true

    `aAdj` est EXACTEMENT la composante `z` de `hexgeo.to_cube` (les deux offsets du dump sont
    odd-q, le seul que le port manipule), et `col` en est la composante `x` ; `x + z = -y`. Le corps
    se relit donc : **VRAI ssi les deux positions partagent au moins une composante CUBE** (`x`, `y`
    ou `z`) -- la definition usuelle d'une ligne droite hexagonale. Seul consommateur porte :
    `get_tiles_behind_filled` ci-dessous."""
    ax, ay, az = hexgeo.to_cube(a[0], a[1])
    bx, by, bz = hexgeo.to_cube(b[0], b[1])
    return ax == bx or ay == by or az == bz


def get_tiles_behind_filled(frm: tuple, to: tuple, check_elevation: bool = True,
                            tile_exists=None, elevation_at=None) -> list:
    """`IdunBattle.Core.Services.BattleQuery$$GetTilesBehindFilled(from, direction, checkElevation)`
    en domaine POSITION -- la ou `GetTileBehindTargetFromSourceDirection` rend UNE tuile, celle-ci
    en rend UNE ou DEUX (d'ou « Filled »).

        if (!AxialCoordinate.IsOnStraightLine(pos(from), pos(direction))) {
            (d1, d2) = MovementUtil.RoundDirection(cube(from), cube(direction), <les 2 nudges>)
            t1 = GetTileAt(cube(direction) - d1) ; si non nul et elevation OK -> Add
            t2 = GetTileAt(cube(direction) - d2) ; idem                       -> Add
        } else {
            dir = CubeCoordinate.DirectionTo(cube(from), cube(direction))
            t   = GetTileAt(cube(direction) - dir) ; si non nul et elevation OK -> Add
        }

    Le gate d'elevation est `BattleQuery$$IsReachableElevation(from, tile)` ->
    `IdunBattle.Core.Services.TileUtil$$IsReachableElevation(a, b)`, dont le corps ENTIER est
    `abs(elev(a) - elev(b)) < 2` -- la MEME borne que
    `IdunBattle.Entities.Pathfinding.WalkPathfinder$$IsReachableElevationDifference`, deja portee
    ailleurs. `elevation_at` absent -> gate INERTE (le port ne tronque jamais une ligne a tort).

    ⚠ **LA BRANCHE NON-ALIGNEE N'EST PAS PORTEE -- residu `#1052-r1`.** Elle appelle
    `IdunBattle.Core.Services.MovementUtil$$RoundDirection(from, to, RotationDirection)`, dont le
    corps est `RoundFloatCubeCoordinates(FloatCubeCoordinate(from).Lerp(FloatCubeCoordinate(to),
    <by:Fix64>) +/- <nudge statique>)` puis `DirectionTo(<arrondi>, to)`. Le facteur `by` du `Lerp`
    passe par XMM et le nudge est un champ STATIQUE ecrit par un `.cctor` : ni l'un ni l'autre n'est
    lisible dans le pseudo-C, donc les DEUX directions candidates ne sont pas derivables sans une
    lecture a l'assembleur. Rendre `[]` ici est une degradation RESTRICTIVE et DITE (le porteur
    frappe une tuile de moins), jamais une geometrie inventee.
    Regime concerne : `from` et `to` NON alignes -- impossible a distance 1 (deux hexes adjacents
    partagent toujours une composante cube), donc uniquement a partir de la distance 2."""
    if frm is None or to is None:
        return []
    if not is_on_straight_line(frm, to):
        return []                     # branche `RoundDirection` NON portee -- residu `#1052-r1`
    dx, dy, dz = direction_to(frm, to)                     # `clamp(cube(from) - cube(to), -1, +1)`
    bx, by, bz = hexgeo.to_cube(to[0], to[1])
    p = hexgeo.from_cube(bx - dx, bz - dz)                 # `cube(direction) - dir`
    if tile_exists is not None and not tile_exists(p):
        return []                                          # `GetTileAt == null`
    if check_elevation and elevation_at is not None:       # `IsReachableElevation(from, tile)`
        ea, eb = elevation_at(frm), elevation_at(p)
        if ea is not None and eb is not None and abs(int(ea) - int(eb)) >= 2:
            return []
    return [p]


def _sgn(v: int) -> int:
    """`x / abs(x)` du decompile (division ENTIERE C, jamais atteinte avec x == 0 : les trois
    branches `composante nulle` sont traitees AVANT)."""
    return (v > 0) - (v < 0)


# Les SIX vecteurs cube que `GetMinimumTiles180Front` ajoute dans sa branche NON-ALIGNEE, dans
# l'ORDRE des tests du decompile. Cle = `(quelle composante vaut le min, laquelle vaut le max)` avec
# `d = cube(caster) - cube(cible)` ; valeur = le vecteur passe a `CubeCoordinate$$Difference`.
# La tuile candidate est `cube(cible) - vec` (cf. `get_minimum_tiles_180_front`).
_FRONT_180_VECS: tuple[tuple[int, int, tuple[int, int, int]], ...] = (
    (0, 1, (1, -1, 0)),
    (0, 2, (1, 0, -1)),
    (1, 2, (0, 1, -1)),
    (1, 0, (-1, 1, 0)),
    (2, 0, (-1, 0, 1)),
    (2, 1, (0, -1, 1)),
)


def get_minimum_tiles_180_front(frm: tuple, to: tuple, check_elevation: bool = False,
                                walkable_at=None, elevation_at=None, tile_exists=None) -> list:
    """`IdunBattle.Core.Services.BattleQuery$$GetMinimumTiles180Front(unit, otherUnit, isReachable)`
    en domaine POSITION -- l'arc AVANT de `otherUnit` : les tuiles a UN hex de `otherUnit` qui vont
    VERS `unit`. C'est le pendant exact de `GetMinimumTiles180Behind` (arc ARRIERE, moteur du PUSH,
    porte dans `runner/operations/displace.py`), au SIGNE des vecteurs pres.

    Unique consommateur natif du slot : `IdunBattle.Operations.DisplaceUnitOperation$$FindTileToPullOnce`
    (case **6** du switch d'`IdunBattle.Operations.DisplaceUnitOperation$$Execute`), qui l'appelle avec
    `isReachable = 0`.

    MIRROR du corps, avec `d = cube(unit) - cube(otherUnit)` :

        if (d.x == 0)  vec = (0, -sgn(d.y), -sgn(d.z))
        elif (d.y == 0) vec = (-sgn(d.x), 0, -sgn(d.z))
        elif (d.z == 0) vec = (-sgn(d.x), -sgn(d.y), 0)
        else            mn = Min(d.x, d.y, d.z) ; mx = Max(...)         # jusqu'a DEUX vecteurs
                        if (d.x == mn) { if (d.y == mx) add(1,-1,0) ; if (d.z == mx) add(1,0,-1) }
                        if (d.y == mn) { if (d.z == mx) add(0,1,-1) ; if (d.x == mx) add(-1,1,0) }
                        if (d.z == mn) { if (d.x == mx) add(-1,0,1) ; if (d.y == mx) add(0,-1,1) }
        foreach vec : AddNewTileToList(row, col of CubeCoordinate.Difference(vec, cube(otherUnit)),
                                       originTile = MainTile(otherUnit), checkWalkability = 1,
                                       checkElevation = isReachable)

    `CubeCoordinate$$Difference(vec, cube)` rend `cube - vec` -- l'orientation est TRANCHEE par la
    comparaison avec la fonction soeur `GetMinimumTiles180Behind`, dont les vecteurs sont les OPPOSES
    (`+sgn` la ou Front a `-sgn`) et qui doit rendre l'arc ARRIERE : avec `cube - vec`, Front rend
    bien un pas de la cible VERS le caster, et Behind un pas a l'oppose. Coherent avec l'i2 de
    `1090 GrapnelLauncher` (« it is then pulled 1 hex towards Tjark »).

    Cas ALIGNE (une composante cube nulle) -> UNE tuile ; cas non aligne -> UNE ou DEUX (deux quand
    une composante est ex-aequo au min ou au max, ex. `d = (2,-1,-1)`).

    `AddNewTileToList` -> `IdunBattle.Core.Services.TileUtil$$IsTileValidForList(tile, originTile,
    checkWalkability = 1, checkElevation)` : une tuile qui echoue est simplement OMISE (contraste
    `get_tiles_behind`, qui ARRETE la ligne). Accesseurs absents -> gate inerte, meme convention que
    tout ce module."""
    ox, oy, oz = hexgeo.to_cube(frm[0], frm[1])
    tx, ty, tz = hexgeo.to_cube(to[0], to[1])
    dx, dy, dz = ox - tx, oy - ty, oz - tz
    vecs: list[tuple[int, int, int]] = []
    if dx == 0:
        vecs.append((0, -_sgn(dy), -_sgn(dz)))
    elif dy == 0:
        vecs.append((-_sgn(dx), 0, -_sgn(dz)))
    elif dz == 0:
        vecs.append((-_sgn(dx), -_sgn(dy), 0))
    else:
        d = (dx, dy, dz)
        mn, mx = min(d), max(d)
        for i_mn, i_mx, vec in _FRONT_180_VECS:
            if d[i_mn] == mn and d[i_mx] == mx:
                vecs.append(vec)
    out: list = []
    for vx, vy, vz in vecs:
        p = hexgeo.from_cube(tx - vx, tz - vz)
        if tile_exists is not None and not tile_exists(p):
            continue                       # `GetTileAt == null` -> tuile simplement OMISE
        if not is_tile_valid_for_list(p, to, True, walkable_at, elevation_at,
                                      check_elevation=check_elevation):
            continue
        out.append(p)
    return out


def get_minimum_tiles_180_behind_from_tile(caster_tile: tuple, to: tuple, walkable_at=None,
                                           elevation_at=None, tile_exists=None) -> list:
    """`IdunBattle.Core.Services.BattleQuery$$GetMinimumTiles180BehindFromTile(casterTile,
    otherUnit)` (slot d'interface **0x4e** = index de vtable 0x52, RE-DERIVE au runtime le
    2026-08-01 par le balayage borne de `probe_27_4g_battlequery_slots.py`) -- l'arc ARRIERE de
    `otherUnit` : les tuiles a UN hex qui s'ELOIGNENT de `casterTile`.

    C'est le pendant EXACT de `get_minimum_tiles_180_front`, aux vecteurs OPPOSES pres. Le
    decompile des deux corps est superposable ligne a ligne : meme `d`, memes trois branches
    alignees, meme paire `Min`/`Max` sur les trois composantes, memes six tests -- seuls les
    vecteurs passes a `CubeCoordinate$$Difference` changent de signe :

        if (d.x == 0)   vec = (0, sgn(d.y), sgn(d.z))
        elif (d.y == 0) vec = (sgn(d.x), 0, sgn(d.z))
        elif (d.z == 0) vec = (sgn(d.x), sgn(d.y), 0)
        else            mn = Min(d.x, d.y, d.z) ; mx = Max(...)         # jusqu'a DEUX vecteurs
                        if (d.x == mn) { if (d.y == mx) add(-1,1,0) ; if (d.z == mx) add(-1,0,1) }
                        if (d.y == mn) { if (d.z == mx) add(0,-1,1) ; if (d.x == mx) add(1,-1,0) }
                        if (d.z == mn) { if (d.x == mx) add(1,0,-1) ; if (d.y == mx) add(0,1,-1) }
        foreach vec : AddNewTileToList(cube(otherUnit) - vec, originTile = MainTile(otherUnit),
                                       checkWalkability = 1, checkElevation = 1)

    avec `d = cube(casterTile) - cube(otherUnit)`. Avec `cube - vec`, Front rend un pas de la cible
    VERS le caster et Behind un pas a l'OPPOSE -- c'est ce qui en fait le moteur du PUSH
    (`IdunBattle.Operations.DisplaceUnitOperation$$FindTileToPush`, deja porte cote COMBAT dans
    `runner/operations/displace.py`).

    DEUX ecarts avec `get_minimum_tiles_180_front`, lus au call-site et non supposes :
    `checkElevation` vaut **1 en litteral** ici (Front le recoit de `isReachable`, que son unique
    consommateur natif passe a 0), et une tuile qui echoue `IsTileValidForList` est simplement
    OMISE (contraste `get_tiles_behind`, qui ARRETE la ligne).

    Cas ALIGNE (une composante cube nulle) -> UNE tuile ; cas non aligne -> UNE ou DEUX."""
    ox, oy, oz = hexgeo.to_cube(caster_tile[0], caster_tile[1])
    tx, ty, tz = hexgeo.to_cube(to[0], to[1])
    dx, dy, dz = ox - tx, oy - ty, oz - tz
    vecs: list[tuple[int, int, int]] = []
    if dx == 0:
        vecs.append((0, _sgn(dy), _sgn(dz)))
    elif dy == 0:
        vecs.append((_sgn(dx), 0, _sgn(dz)))
    elif dz == 0:
        vecs.append((_sgn(dx), _sgn(dy), 0))
    else:
        d = (dx, dy, dz)
        mn, mx = min(d), max(d)
        for i_mn, i_mx, vec in _FRONT_180_VECS:
            if d[i_mn] == mn and d[i_mx] == mx:
                vecs.append((-vec[0], -vec[1], -vec[2]))
    out: list = []
    for vx, vy, vz in vecs:
        p = hexgeo.from_cube(tx - vx, tz - vz)
        if tile_exists is not None and not tile_exists(p):
            continue                       # `GetTileAt == null` -> tuile simplement OMISE
        if not is_tile_valid_for_list(p, to, True, walkable_at, elevation_at,
                                      check_elevation=True):
            continue
        out.append(p)
    return out


def tiles_behind_accessors(walkable_by_pos: dict | None, elev_by_pos: dict | None):
    """Accesseurs `(walkable_at, elevation_at, tile_exists)` de `get_tiles_behind` batis sur les
    cartes OFFLINE de la face DECISION (`ctx.walkable_by_pos` = boardGraph `IsWalkableTile`,
    `ctx.elev_by_pos` = tileMeta `elevation`). Carte absente/vide -> accesseur None = gate INERTE
    (le port se degrade vers son comportement pre-#124, jamais vers une ligne tronquee a tort)."""
    walkable_at = ((lambda p: bool(walkable_by_pos.get((p[0], p[1]), False)))
                   if walkable_by_pos else None)
    elevation_at = ((lambda p: elev_by_pos.get((p[0], p[1])))
                    if elev_by_pos else None)
    tile_exists = ((lambda p: (p[0], p[1]) in walkable_by_pos) if walkable_by_pos else
                   ((lambda p: (p[0], p[1]) in elev_by_pos) if elev_by_pos else None))
    return walkable_at, elevation_at, tile_exists


# Deltas CUBE unitaires -> index d'ARETE hexagonale. MIRROR de
# `IdunBattle.Utils.Hex.CubeDirections$$EdgeToNeighbor(diff)` : cle `100*x + 10*y + z` (le natif
# calcule `z + (y + x*10)*10`), SEULES ces 6 valeurs mappent -- tout autre delta rend un
# `Nullable<Edge>` VIDE. L'ordre 0..5 tourne d'un cran de 60 deg a chaque increment, ce qui rend
# `|e1 - e2|` interpretable comme un ecart angulaire (cf. `get_angle_between_vectors`).
_EDGE_BY_CUBE_DELTA = {
    (0, -1, 1): 0,     # cle  -9
    (1, -1, 0): 1,     # cle  90
    (1, 0, -1): 2,     # cle  99
    (0, 1, -1): 3,     # cle   9
    (-1, 1, 0): 4,     # cle -90
    (-1, 0, 1): 5,     # cle -99
}


def connecting_edge(src: tuple, dst: tuple) -> int | None:
    """`IdunBattle.Utils.Hex.AxialCoordinate$$ConnectingEdge(a, b)` (MIRROR) : l'index d'ARETE (0..5)
    du vecteur `b - a` en coordonnees CUBE, `None` si le delta n'est pas une direction hex UNITAIRE
    (le natif convertit les deux offsets en cube puis delegue a `CubeDirections$$EdgeToNeighbor`, qui
    rend un `Nullable<Edge>` vide hors des 6 deltas)."""
    ax, ay, az = hexgeo.to_cube(src[0], src[1])
    bx, by, bz = hexgeo.to_cube(dst[0], dst[1])
    return _EDGE_BY_CUBE_DELTA.get((bx - ax, by - ay, bz - az))


def get_vector(a: tuple | None, b: tuple | None) -> int:
    """`IdunBattle.Core.Services.BattleQuery$$GetVector(a, b)` en domaine POSITION (slot 0x71) :

        tileA = GetMainTile(a) ; tileB = GetMainTile(b)
        if (tileA == tileB)                    return <static IdunVector par defaut>
        edge = AxialCoordinate.ConnectingEdge(coord(tileA), coord(tileB))
        return edge.HasValue ? new Position(edge.Value, 1) : <static IdunVector par defaut>

    Le natif rend un `IdunVector` ; seule son ARETE est consommee (par
    `GetAngleBetweenVectors`), donc le port rend directement l'index 0..5. Tuiles identiques ou
    delta non unitaire -> le vecteur statique par defaut, d'arete 0."""
    if a is None or b is None or (a[0], a[1]) == (b[0], b[1]):
        return 0
    e = connecting_edge(a, b)
    return 0 if e is None else e


def get_angle_between_vectors(v1: int, v2: int) -> int:
    """`IdunBattle.Core.Services.BattleQuery$$GetAngleBetweenVectors(vectorA, vectorB)` (slot 0x72),
    dont le corps EST `IdunBattle.Utils.Hex.EdgeExtensions$$GetAngleTo(edge, edge2)` (MIRROR EXACT) :

        d = |e1 - e2| ; a = d * 60 ; if (a > 120) a = (6 - d) * 60 ; return a

    -> 0 / 60 / 120 / 180 / 120 / 60 pour d = 0..5 : l'ecart angulaire MINIMAL entre deux directions
    hex, en degres. Invariant par rotation ET par reflexion de la numerotation des aretes, donc
    insensible a la convention de cube du port."""
    d = abs(v1 - v2)
    a = d * 60
    return (6 - d) * 60 if a > 120 else a


def get_adjacent_tiles(pos: tuple, walkable_at=None, elevation_at=None, tile_exists=None,
                       only_empty_or_steppable: bool = False, only_walkable_tiles: bool = True,
                       allow_temporary: bool = True) -> list:
    """`IdunBattle.Core.Services.BattleQuery$$GetAdjacentTiles(from, onlyEmptyOrSteppable,
    onlyWalkableTiles, allowTemporary)` (slot 0x4f) en domaine POSITION. Le corps delegue a
    `IdunBattle.Core.Services.TileQuery.u003CIterateAdjacentTilesu003Ed__8$$MoveNext` :

        foreach (neighbour in tile.Neighbours)            # liste PRE-CALCULEE du composant tuile
            if (tile == null)                                             continue
            if (!allowTemporary   && TileExtensions.IsTemporary(tile))    continue
            if (onlyWalkableTiles && !TileExtensions.IsWalkable(tile, 1)) continue
            if (onlyEmptyOrSteppable && !IsEmptyOrSteppable(tile, ...))   continue
            if (|elev(src) - elev(tile)| < 2) yield tile                  # PORTE D'ELEVATION

    La porte `|Delta elev| < 2` est INCONDITIONNELLE (elle ne depend d'aucun flag) : le ring-1 natif
    n'est PAS le ring-1 geometrique des que le relief bouge. Meme porte que le mouvement et que
    `is_tile_valid_for_list` -- un palier a +2 est inaccessible A PIED comme A LA LIGNE.

    Flags PORTES = ceux LUS a l'unique call-site porte (`IdunBattle.Entities.Selectors.AdjacentTilesSelector$$Select`
    appelle le slot avec `(entity, 0, 1, 1)`, cf. `IdunBattleLogic.Entities.DSLFactory$$AdjacentTiles`) :
    `onlyEmptyOrSteppable=False` (les tuiles OCCUPEES passent -- indispensable, on vise des ennemis),
    `onlyWalkableTiles=True`, `allowTemporary=True`. Les deux autres combinaisons ne sont PAS portees
    (pas de substrat offline pour `IsTemporary`/`IsEmptyOrSteppable`) et leve plutot que de mentir.

    ORDRE : le natif suit `tile.Neighbours` (liste pre-calculee du board) ; le port suit
    `hexgeo.neighbors`. Les deux ordres peuvent differer -- RESIDU INERTE pour les consommateurs
    portes, ou l'ordre n'est qu'un tie-break de dernier recours entre directions D'UTILITE EGALE."""
    if only_empty_or_steppable or not only_walkable_tiles or not allow_temporary:
        raise NotImplementedError(
            "get_adjacent_tiles: seule la combinaison du call-site porte "
            "(onlyEmptyOrSteppable=False, onlyWalkableTiles=True, allowTemporary=True) est mirroree")
    src_e = elevation_at(pos) if elevation_at is not None else None
    out = []
    for n in hexgeo.neighbors(pos[0], pos[1]):
        if tile_exists is not None and not tile_exists(n):
            continue                       # `GetTileEntityById == null` / hors board
        if walkable_at is not None and not walkable_at(n):
            continue                       # `onlyWalkableTiles` -> TileExtensions.IsWalkable
        if src_e is not None and elevation_at is not None:
            ne = elevation_at(n)
            if ne is not None and abs(src_e - ne) >= 2:
                continue                   # porte d'elevation INCONDITIONNELLE de l'iterateur
        out.append(n)
    return out


def get_surrounding_tiles(pos: tuple, radius: int = 1, include_center: bool = False,
                          check_walkable: bool = True,
                          walkable_at=None, elevation_at=None, tile_exists=None,
                          only_empty_or_steppable: bool = False,
                          empty_or_steppable_at=None) -> list:
    """`IdunBattle.Core.Services.BattleQuery$$GetSurroundingTiles` (slot 0x65) en domaine POSITION.
    Le corps delegue a `IdunBattle.Core.Services.TileQuery.u003CIterateSurroundingTilesu003Ed__6$$MoveNext` :

        cube = CubeCoordinate(srcTile)
        for x in cube.x-R .. cube.x+R:                       # DISQUE, pas le ring exact
          for y in cube.y-R .. cube.y+R:
            for z in cube.z-R .. cube.z+R:
              if (x + y + z != 0)                                          continue
              tile = GetTileEntityAt(CubeCoordinate(x,y,z).ToAxialCoordinate())
              if (tile == null)                                            continue
              if (requireEmptyOrSteppable && !IsEmptyOrSteppable(tile))    continue
              if (!includeSelf && tile == srcTile)                         continue
              if (TileUtil.IsTileValidForList(tile, srcTile, checkWalkable, 0))  yield tile

    DEUX lectures qui separent ce disque du ring-1 `IterateAdjacentTiles` (`get_adjacent_tiles`) :
    1. le 4e argument d'`IsTileValidForList` est le litteral **`0`** -> **AUCUNE porte d'elevation**
       (un palier a +2 reste dans le disque, alors qu'il sort du ring-1) ;
    2. l'ORDRE est celui de la triple boucle cube ASCENDANTE : pour (x, y) donnes un seul z
       satisfait `x+y+z == 0`, donc l'ordre emis est LEXICOGRAPHIQUE `(cube.x, cube.y)` croissant
       (= `iterate_surrounding_tiles_order_key`), pas l'ordre `tile.Neighbours` du ring-1.

    FLAGS PORTES = ceux LUS a la chaine de call-sites (`IdunBattle.Entities.Selectors.SurroundingTilesSelector$$Select`
    -> slot 0x65 avec `(tile, radius, requireEmptyOrSteppable=0, checkWalkable=(sel+0x29 == 0),
    unitFilter=sel+0x28, includeSelf=1)`, ou `sel+0x28`/`+0x29` sont les 2 derniers arguments de
    `IdunBattleLogic.Entities.DSLFactory$$SurroundingTiles`). Les deux call-sites de ce chemin-la
    (`GauntletsOfUltramarAbility$$GetSurroundingTargetsSelector` r=2, `ThriceBlessedConflagrationAbility$$GetTilesInBestLine`
    r=1) passent `(..., 0, 0)` -> `requireEmptyOrSteppable=False` (les tuiles OCCUPEES passent),
    `checkWalkable=True`, `unitFilter=0`. `includeCenter=0` cote DSL est resolu par la branche
    `SurroundingTiles(entity, includeCenter=1, ...) - Tiles(entity)` -> meme ensemble, meme ordre.

    `only_empty_or_steppable` = le 3e argument natif `onlyEmptyOrSteppable`, POSE par deux autres
    call-sites (#287-r11-r1) qui empruntent l'AUTRE slot d'`IBattleQuery` (**103**, la surcharge
    dont le `center` est une collection de tuiles ; le slot est LU dans
    `data/symbols/<build>/metadata/interface_slots.tsv`, pas deduit) :

      | regle dynamique de ciblage                                    | d     | oEoS | oW | oM | incC |
      | `SendInTheNextWaveAbility$$GetDynamicInvalidTargetReason`     | range | 1    | 1  | 0  | 1    |
      | `HeroicFusilladeAbility$$GetDynamicInvalidTargetReason`       | 1     | 0    | 1  | 0  | 1    |

    Le filtre s'applique AVANT le test `includeCenter` et AVANT `IsTileValidForList`, exactement
    comme au decompile. `empty_or_steppable_at` est l'accesseur (pos -> bool) mirror de
    `IdunBattle.Entities.TileExtensions$$IsEmptyOrSteppable` -- ce module vit en domaine POSITION et
    n'a AUCUN acces au contenu des tuiles, donc le substrat est INJECTE, comme `walkable_at`. Poser
    le flag sans l'accesseur LEVE (meme choix que `get_adjacent_tiles`) : un filtre demande mais
    inapplicable rendrait un ensemble TROP GRAND, donc un port PERMISSIF, en silence.

    `only_movable` (4e argument natif) n'est PAS porte : aucun call-site lu ne le pose (les quatre
    ci-dessus passent 0). Le natif y filtrerait par
    `MovementQuery$$GetMovableTilesFor(unite-sur-le-centre, ignoreUnitFlags: 1, {overrideRange = d})`.

    `include_center=False` retire ici la SEULE tuile `pos` ; le natif retire `Tiles(entity)`,
    c'est-a-dire TOUTES les tuiles de l'entite. Identique pour une entite mono-tuile (le cas de tous
    les porteurs confrontes) — RESIDU documente pour une cible multi-tuiles."""
    if only_empty_or_steppable and empty_or_steppable_at is None:
        raise NotImplementedError(
            "get_surrounding_tiles: `only_empty_or_steppable` demande sans `empty_or_steppable_at` "
            "-- le filtre serait INERTE et le resultat TROP GRAND (port permissif silencieux)")
    cx, cy, cz = hexgeo.to_cube(pos[0], pos[1])
    key = (pos[0], pos[1])
    out = []
    for x in range(cx - radius, cx + radius + 1):
        for y in range(cy - radius, cy + radius + 1):
            z = -x - y                      # unique z tel que x+y+z == 0 (la 3e boucle ne matche qu'une fois)
            if not (cz - radius <= z <= cz + radius):
                continue
            p = hexgeo.from_cube(x, z)
            if tile_exists is not None and not tile_exists(p):
                continue                    # `GetTileEntityAt == null` -> hors board
            if only_empty_or_steppable and not empty_or_steppable_at(p):
                continue                    # `requireEmptyOrSteppable && !IsEmptyOrSteppable(tile)`
            if not include_center and (p[0], p[1]) == key:
                continue                    # `includeSelf == 0` (ou `- Tiles(entity)` cote DSL)
            if not is_tile_valid_for_list(p, pos, check_walkable, walkable_at, elevation_at,
                                          check_elevation=False):
                continue                    # 4e argument natif == 0 : PAS de porte d'elevation
            out.append(p)
    return out


def surrounding_enemies(origin: tuple, positions: list,
                        elev_by_pos: dict | None = None) -> set:
    """`Unobscured(DSLFactory.SurroundingEnemies(Caster, r=2))` — le terme « surrounding » de
    `IdunBattleLogic.Entities.Abilities.Active.Loki.GauntletsOfUltramarAbility$$GetSurroundingTargetsSelector`, ancré à la TUILE RÉELLE
    du caster (`Caster@+0x160` = CasterSelector -> ENTITÉ -> `GetMainTile` dans
    `IdunBattle.Entities.Selectors.SurroundingTilesSelector$$Select` — PAS la tuile balayée du contexte).

    Chaîne native (décompilée, case-49x) : `IdunBattleLogic.Entities.DSLFactory$$SurroundingEnemies` =
    `Enemies(Units(SurroundingTiles(caster, r=2) - Tiles(caster)))` ; `SurroundingTiles` -> slot
    0x65 = `IdunBattle.Core.Services.BattleQuery$$GetSurroundingTiles` -> `IdunBattle.Core.Services.TileQuery$$IterateSurroundingTiles` (cube-loop DISQUE dist <= 2 — pas le ring exact) avec flags MESURÉS au call-site
    (IdunBattle.Entities.Selectors.SurroundingTilesSelector$$.ctor <- SurroundingTiles(query, caster, 1, r=2, 0, 0)) :
      - requireEmptyOrSteppable = OFF (p4=0) -> les tuiles OCCUPÉES par des ennemis PASSENT
        (la conclusion case-49 §2bis « empty-only / ring-2 mort » était FAUSSE) ;
      - filtre restant = `IdunBattle.Core.Services.TileUtil$$IsTileValidForList(tile, src, 1, 0)` = non-mur +
        walkable, SANS test d'élévation ni d'occupation (une unité stationne sur du walkable -> no-op
        offline) ; PAS de porte |Δelev| ici (contrairement au ring-1 `IterateAdjacentTiles`) ;
      - includeSelf = ON (p7=1) puis `- Tiles(caster)` au niveau DSL -> exclure `origin`.
    `IdunBattleLogic.Entities.DSLFactory$$Unobscured` -> `IdunBattle.Core.Services.TargetingQuery$$IsTargetUnitObscured` depuis la tuile
    RÉELLE : dist 1 jamais obscurci, dist 2 via `is_target_tile_obscured`.
    Retour : set de positions (== unités : 1 unité/tuile) — l'union avec ring1(T) est dédupliquée
    par le `IdunBattle.DSL.TargetsSelector$$SelectUniqueUnits` du playbook.
    VALIDÉ LIVE (probe_49x_realanchor, 2026-07-21) : craft-P MC1_67 plat (disque réel compte : util
    3 = 1 ring1(T) + 2 dist-2-du-réel) ; craft-N (dist-2-de-T ne compte PAS) ; E1-repro C1_25
    (17/23 positions util=2 = les 2 ennemis à dist 2 du réel, indépendant de T)."""
    ok = (origin[0], origin[1])
    out = set()
    for p in (positions or []):
        pk = (p[0], p[1])
        if pk == ok:
            continue
        d = hexgeo.distance(ok, pk)
        if d > 2:
            continue
        if d == 2 and is_target_tile_obscured(ok, pk, elev_by_pos):
            continue
        out.add(pk)
    return out


def surrounding_enemies_in_range(origin: tuple, positions: list, radius: int) -> set:
    """`IdunBattleLogic.Entities.DSLSelectors$$SurroundingEnemies`, surcharge **5 args**
    `(unit, range, unique, unitSelectionType)` — celle dont le 2e parametre est nomme `unit` (une
    ENTITE), PAS `unitTile`. Corps natif :

        Enemies( unit,
                 Units( SurroundingTiles(unit, includeCenter: 1, range) - Tiles(unit),
                        unique, unitSelectionType ),
                 unitSelectionType )

    Trois consequences LUES (jamais deduites) :

    * **le centre est l'ENTITE** : `SurroundingTiles`/`Tiles` partent de
      `IdunBattle.Entities.EntityExtensions$$IterateTiles(unit)`, donc de la MainTile REELLE du sujet
      — pas de la tuile candidate du balayage IA (meme quirk que
      `IdunBattleLogic.Entities.Abilities.Active.Loki.SavageEchoesAbility$$GetDamage`, confronte live
      en #216) ;
    * `- Tiles(unit)` retire le centre (`includeCenter: 1` puis soustraction) ;
    * **aucun `Unobscured`** dans cette surcharge — contrairement a `surrounding_enemies` ci-dessus,
      qui mirroir le `Unobscured(SurroundingEnemies(...))` de
      `IdunBattleLogic.Entities.Abilities.Active.Loki.GauntletsOfUltramarAbility$$GetSurroundingTargetsSelector`.
      Ne PAS reutiliser cette derniere ici : elle retirerait des ennemis a distance 2 obscurcis que ce
      selecteur-ci compte.

    Le filtre de tuiles de `SurroundingTiles` est `IdunBattle.Core.Services.TileUtil$$IsTileValidForList
    (tile, src, 1, 0)` = non-mur + walkable, SANS test d'elevation ni d'occupation : une unite
    stationne forcement sur du walkable, donc no-op offline (meme raisonnement que
    `surrounding_enemies`). `radius` vient du `GetNumberConstant` du call-site, jamais d'un scalaire
    fige.

    Retour : set de positions (1 unite par tuile ; le `unique` natif dedoublonne les unites
    multi-tuiles, sans objet ici)."""
    ok = (origin[0], origin[1])
    out = set()
    for p in (positions or []):
        pk = (p[0], p[1])
        if pk == ok:
            continue                                   # `- Tiles(unit)`
        if hexgeo.distance(ok, pk) > int(radius):
            continue
        out.add(pk)
    return out


def iterate_surrounding_tiles_order_key(pos: tuple) -> tuple:
    """Clé d'ORDRE d'énumération de `TileQuery.IterateSurroundingTiles` (`IdunBattle.Core.Services.TileQuery.u003CIterateSurroundingTilesu003Ed__6$$MoveNext`) —
    le tie-break NATIF de cible à utilité égale au sein d'une position (#57g, 12345 s15).

    Le natif énumère le disque par triple boucle cube ASCENDANTE : `for x in cx-R..cx+R:
    for y in cy-R..cy+R: for z in cz-R..cz+R: if x+y+z==0 -> yield` — pour (x,y) donnés un seul z
    matche, donc l'ordre = LEXICOGRAPHIQUE (cube.x, cube.y) CROISSANT des tuiles émises ; le centre ne
    fait que borner le disque, il ne change PAS l'ordre relatif de deux tuiles. Cet ordre survit à toute
    la chaîne de ciblage (chaque étage filtre en préservant l'ordre via OrderedSet/List.Remove) :
    `IdunBattle.AI.Playbook.ComparablePlaybooku003C__Il2CppFullySharedGenericTypeu003E$$EvaluateInternal` (argmax cibles STRICT `op_GreaterThan` -> PREMIÈRE
    énumérée gagne au tie) <- `IdunBattle.AI.Playbook.BasePlaybook$$GetEligibleTargetsEntities` (List + Remove
    prédicat) <- `IdunBattle.Core.Services.AttackQuery$$GetValidTargetsWithCache` <- `IdunBattle.Core.Services.TargetingQuery$$GetValidTargets` (itère les possibles, OrderedSet.Add si valide) <- `IdunBattle.Core.Services.TargetingQuery$$GetPossibleTargetsForOptions` <- `IdunBattle.Core.Services.TargetingQuery$$GetUnitsInRange` (slot 0x76) <- `IdunBattle.Core.Services.BattleQuery$$GetUnitsAtDistance` (tuiles du ring -> GetUnit, ordre préservé) <- `IdunBattle.Core.Services.BattleQuery$$GetTilesAtDistance`
    (filtre dist==R, ordre préservé) <- `GetSurroundingTiles` -> l'itérateur ci-dessus.

    Champs cube natifs (0,1,2) == (x,y,z) `hexgeo.to_cube` : `IdunBattle.Utils.Hex.CubeCoordinate$$ToAxialCoordinate` (field3==0) = inverse exact de `to_cube` (col=x ; row=z+(x+(x&1))//2). Limites :
    cible multi-tuiles = rang de sa première tuile émise (non exercé) ; l'empilement de rings pour
    range>1 (ordre inter-distances) est non lu — le tie s15 est mêlée R=1 (un seul ring)."""
    x, y, _z = hexgeo.to_cube(pos[0], pos[1])
    return (x, y)


def enemies_in_arc(tile: tuple, enemies: list) -> list:
    """Ennemis (unités decisionView `{id, pos:{col,row}}`) dans l'ARC de `tile` = ring-1 UNION ring-2
    (`in_arc`), DANS L'ORDRE d'énumération de `enemies`. Fallback de `gauntlets_target` sans neighbours.

    ⚠ #433-r4-r1-r4-r2-r1 : plus de porte d'élévation ici — l'ARC est géométrique pur (lecture native
    complète dans `in_arc`). Ce fallback n'est atteint que si `neigh_by_pos` manque à
    `gauntlets_target` ; sa branche NATIVE, elle, énumère bien la liste stockée (ordre observable)."""
    out = []
    for e in (enemies or []):
        p = e.get("pos") if isinstance(e, dict) else None
        if p and p.get("col") is not None and in_arc(tile, (p["col"], p["row"])):
            out.append(e)
    return out


def can_add_unit(pos: tuple, walkable_by_pos: dict | None = None,
                 occupied: set | None = None) -> bool:
    """`IdunBattle.Entities.TileExtensions$$CanAddUnit` (prédicat OFFLINE, args du call Hammer arg3=1/arg4=0/arg5=false).

    Le natif (décodé re-expert #116) réduit, pour ces args, à : la tuile est une tuile de board RÉELLE
    placeable (walkable, non-wall) ET VIDE (`IdunBattle.Entities.Components.TileContentComponent$$IsEmpty` = pas de contenu
    unité). Offline : `walkable_by_pos[pos]` (= `BattleQuery.IsWalkableTile` = `TileExtensions.IsWalkable`,
    qui folds déjà isWall, cf. rpc-board.ts) ET `pos ∉ occupied` (occupation LIVE = TOUTES les unités
    vivantes, lue FRAÎCHE via epos/fpos/origine — PAS le `occupantUnitId` du boardGraph caché = périmé).
    LIMITATION v1 (flaggée par verdict RE + validator FEU VERT) : (a) co-location trait 0x1b — arg3=1
    admet un occupant trait-27 pass-through -> ici une tuile occupée = fail (borne INF, corner négligeable) ;
    (b) les flags runtime `tile[4]+0x40` (bloqué) / `+0x2c` (réservé) ne sont modélisés QUE si `walkable`
    les folds (HYPOTHÈSE : `walkable==false` couvre `+0x40` ; une tuile walkable-mais-réservée serait
    sur-comptée) ; (c) le filtre IsTemporary de l'itérateur natif `GetAdjacentTiles` n'est PAS appliqué
    dans le call Hammer — RE #118 RÉSOLU (non-issue) : le call slot-78 passe
    `GetAdjacentTiles(unit, 1, 1, 1)` (IdunBattle.AI.Playbook.Loki.HammerOfWrathPlaybook$$EvaluateNonComparable) [RE ctors #148 : param3=requireEmptyOrSteppable,
    param4=requireWalkable, param5=allowTemporary (polarite inversee : 1=inclure)] ;
    les 3 bools transitent `<IterateAdjacentTiles>d__94 IdunBattle.Core.Services.BattleQuery.u003CIterateAdjacentTilesu003Ed__94$$MoveNext` (+0x40/+0x42/+0x44) ->
    `TileQuery.<>d__8 IdunBattle.Core.Services.TileQuery.u003CIterateAdjacentTilesu003Ed__8$$MoveNext`. Le gate temporary y est `(field != 0) || !IsTemporary(tile)`, alimenté
    par param5=allowTemporary : param5=1 -> court-circuite VRAI -> tuiles temporaires ACTIVES INCLUSES par le
    natif (comme par le port -> aucune exclusion à ajouter). (Le call jumeau `MovementQuery.IsAdjacent` passe
    (0,1,1) = param3=0 inclut les occupées + param5=1 inclut les temporaires : occupance-independant, adapté à
    un test d'adjacence.) `is_temporary_by_pos` reste hors de ce chemin (légitimement utilisé ailleurs : TemporaryTileUtility)."""
    if occupied is not None and (pos[0], pos[1]) in occupied:
        return False
    if not walkable_by_pos:
        return True   # pas de donnée board (fallback pré-plumbing) -> permissif (borne SUP)
    return bool(walkable_by_pos.get((pos[0], pos[1]), False))   # tuile absente = hors-board -> non placeable


def occupied_positions(ctx, base: set | None = None, include_origin: bool = True) -> set:
    """Les tuiles REMPLIES au sens de `IdunBattle.Entities.Components.TileContentComponent$$IsEmpty`
    -- l'entree `occupied` de `can_add_unit` / `adjacent_addable_count`, DERIVEE DE L'EMPREINTE.

    #969-r3 : quatorze corps de playbook construisaient cet ensemble par
    `set(ctx.epos) | set(ctx.fpos) [| {ctx.origin}]`, c.-a-d. la seule MAIN TILE de chaque unite.
    Le natif, lui, remplit UNE TUILE PAR PIED : `IdunBattle.Entities.TileExtensions$$CanAddUnit`
    interroge le `TileContentComponent` DE LA TUILE, et une entite MULTI-HEX (3 ou 7 pieds) a fait
    poser son contenu sur CHACUNE. Le jumeau DSL de ce meme mecanisme
    (`engine/entities/selectors/tiles.py::CanAddUnit`) lisait DEJA l'empreinte : les deux faces du
    port divergeaient donc ENTRE ELLES, la face DECISION du cote PERMISSIF (elle declarait libres
    des tuiles que le natif refuse, donc SUR-COMPTAIT les placements possibles).

    SUBSTRAT, sans capteur neuf : `decisionView.units[].feet` (mirror
    d'`IdunBattle.Entities.EntityExtensions$$GetTiles`, `feet[0]` = la MainTile), que le porteur
    transporte deja dans `ctx.units`. TRI-ETAT PAR UNITE : une ligne sans `feet` n'est PAS « une
    unite d'un seul pied », elle est NON MESUREE -- sa MainTile reste dans l'ensemble et rien
    d'autre n'est ajoute, c'est-a-dire EXACTEMENT le comportement d'avant. `ctx.units` absent ->
    l'ensemble d'entree est rendu tel quel.

    `base` = l'ensemble de depart quand l'appelant en a un autre que `epos|fpos` (deux corps le
    derivent d'`obs_units`, cf. `doctrina_imperatives` / `master_of_the_tutelaries`). `None` ->
    `epos | fpos`, plus `origin` si `include_origin` (le mover est absent de `fpos`, qui l'exclut).

    ⚠ CE QUE CE FOYER N'ELARGIT PAS, et c'est deliberé : l'UNIVERS des occupants reste celui que
    l'appelant lui donne. Les MACHINES OF WAR n'y entrent pas -- elles vivent dans le canal
    `decisionView.mows`, jamais dans `.units`, donc ni `epos` ni `fpos` ne les ont jamais portees.
    C'est un ecart DISTINCT (l'univers, pas l'empreinte), qui n'est pas celui de #969-r3 : le
    combler ici ferait passer pour une correction d'empreinte un elargissement non confronte."""
    if base is None:
        out = set(getattr(ctx, "epos", None) or ()) | set(getattr(ctx, "fpos", None) or ())
        origin = getattr(ctx, "origin", None)
        if include_origin and origin is not None:
            out.add(tuple(origin))
    else:
        out = set(base)
    for u in (getattr(ctx, "units", None) or ()):
        if not isinstance(u, dict):
            continue
        p = u.get("pos") or {}
        if p.get("col") is None:
            continue
        if (p["col"], p["row"]) not in out:
            continue          # cette unite n'est pas dans l'univers de l'appelant -> on n'ajoute rien
        for f in (u.get("feet") or ()):       # `feet` absent -> NON MESURE, la MainTile suffit
            if isinstance(f, dict) and f.get("col") is not None:
                out.add((int(f["col"]), int(f["row"])))
            elif isinstance(f, (tuple, list)) and len(f) >= 2:
                out.add((int(f[0]), int(f[1])))
    return out


#: `IdunBattle.Entities.Effects.BlockActiveAbilityEffect` — la famille des effets qui posent un
#: BLOQUEUR dans `ActiveAbilityComponent+0x18` (`UpdateActiveAbilityBlockerOperation$$AddBlocker`).
#: Cle = `EffectType` ; valeur = les DEUX booleens du `.ctor`, LUS au decompile :
#: `BlockActiveAbilityEffect$$.ctor(this, hasAutomaticActivation, includeNormalAttack@+0x480,
#: includeMachinePrimaryAbility@+0x481)`.
#:
#: ⚠ **LES TROIS MEMBRES SONT LUS, PAS DEDUITS D'UNE CONVENTION DE NOM** (#1020-r7). Ce canal
#: reconnaissait la famille par le SUFFIXE `_CantUseAbility`, en se declarant « proxy offline du
#: check par CLASSE d'effet, couvre tout futur membre » : c'est FAUX pour le troisieme membre, qui
#: s'appelle `RapidFire_BlockAbilities` et ne porte pas ce suffixe. La faute est celle que le
#: CLAUDE.md nomme deja — la VOIE (ici : la forme du nom) ne dit pas l'enum, seul le LITTERAL du
#: decompile le dit.
#:
#: COMMENT LES TROIS ONT ETE LUS. `BlockActiveAbilityEffect$$.ctor` a exactement TROIS appelants de
#: code (`list_xrefs`), tous des lambdas `EffectsDatabase.<>c$$<InitializeEffects>b__14_{14,165,581}`
#: aux memes litteraux `(1, 0, 1)`. Ces lambdas n'ont AUCUNE xref de code — `InitializeEffects` ne
#: les designe que par leur `MethodInfo*`, resolu au runtime — donc leur `EffectType` n'etait pas
#: lisible par xref. Il l'est par le CODE MACHINE d'`InitializeEffects`, ou la cle de chaque
#: `Dictionary<EffectType, Func<BaseEffect>>.Add` est un immediat : 607 cles pour 607 lambdas, en
#: alternance stricte cle/delegue. `scripts/python/probe_10018_effectsdatabase_registry.py` rejoue
#: la mesure et REFUSE de conclure si l'un de ses six controles tombe.
ACTIVE_ABILITY_BLOCKER_EFFECTS: dict[int, dict] = {
    26:   {"name": "Taunted_CantUseAbility",   # b__14_14
           "include_normal_attack": False, "include_machine_primary_ability": True},
    1137: {"name": "RapidFire_BlockAbilities",  # b__14_165  <- le membre que le suffixe RATAIT
           "include_normal_attack": False, "include_machine_primary_ability": True},
    1165: {"name": "Stunned_CantUseAbility",   # b__14_581
           "include_normal_attack": False, "include_machine_primary_ability": True},
}


def _active_ability_blockers(unit: dict) -> list[dict]:
    """Les BLOQUEURS portes par l'unite — mirror du dictionnaire `ActiveAbilityComponent+0x18`.

    Appariement par `effectType` (l'entier de l'enum) EN PREMIER, comme `entity_has_effect` ; le
    `name` n'est le repli que pour les substrats qui ne publient pas l'ordinal, et il est alors
    compare au nom EXACT du registre — jamais a une forme de nom."""
    out: list[dict] = []
    for e in (unit or {}).get("effects") or []:
        if not isinstance(e, dict):
            continue
        et = e.get("effectType")
        spec = None
        if et is not None:
            spec = ACTIVE_ABILITY_BLOCKER_EFFECTS.get(int(et))
        elif e.get("name"):
            nom = str(e["name"])
            spec = next((s for s in ACTIVE_ABILITY_BLOCKER_EFFECTS.values() if s["name"] == nom), None)
        if spec is not None:
            out.append(spec)
    return out


def can_use_ability(unit: dict, ability: dict) -> bool:
    """`IdunBattle.Core.Services.AttackQuery$$CanUseAbility` — gate d'USABILITE d'une ability (stun/taunt).

    Le natif enchaine : (1) l'unite possede l'ability (slot itf 0x14) ; (2) un bool
    d'interface (slot 0x13) doit etre FAUX — c'est
    `IdunBattle.Entities.UnitExtensions$$IsAbilityBlocked` ; (3) `GetInvalidCasterReason` valide.
    Offline : (1) et (3) sont deja couverts par l'enumeration decisionView
    (`usable`/`disabled`), MAIS le capteur `usable` lit l'entree ActiveAbility et
    IGNORE les effets -> ce mirror porte le maillon (2), le seul manquant.

    `UnitExtensions$$IsAbilityBlocked(unit, abilityType)`, LU verbatim :

        si kind(unit) n'est ni Unit(1) ni Machine(6)      -> false
        si ActiveAbility.IsRegularAttack(abilityType)     -> NormalAttackIsBlocked()
        si kind == Machine && abilityType == comp.<+0x30> -> MachinePrimaryAbilityIsBlocked()
        sinon                                             -> ActiveAbilitiesAreBlocked()

        ActiveAbilitiesAreBlocked()      = blockers.Count > 0        (INCONDITIONNEL)
        NormalAttackIsBlocked()          = any(v.includeNormalAttack)
        MachinePrimaryAbilityIsBlocked() = any(v.includeMachinePrimaryAbility)

    Le port rend les DEUX branches qu'il peut discriminer, et il les DERIVE du registre
    `ACTIVE_ABILITY_BLOCKER_EFFECTS` au lieu de les coder en dur — un futur membre a
    `includeNormalAttack = 1` fermerait donc l'attaque normale sans qu'on retouche ce corps.
    L'attaque NORMALE n'est PAS bloquee AUJOURD'HUI parce que les TROIS membres lus portent
    `includeNormalAttack = 0` (et non par decret) : vecu 777 s15 (u83 stunne par 1183 attaque
    encore 69->87) + wiki §Stunned, valide live seed 97000.

    ⚠ **BRANCHE NON SEPAREE, ET C'EST NOMME** : `abilityType == comp.<+0x30>` (l'ability PRIMAIRE
    d'une Machine of War) n'a pas de substrat dans le canal `decisionView` — le port la fond donc
    dans `ActiveAbilitiesAreBlocked`. Le repli est EXACT tant que tout membre du registre porte
    `includeMachinePrimaryAbility = True`, ce qui est le cas des trois ; c'est un test offline qui
    garde cette condition (`test_10018_rapid_fire_offline.py`), pas cette phrase.

    Les effets decisionView sont deja IsActive-filtres (on ignore `remaining`)."""
    blockers = _active_ability_blockers(unit)
    if (ability or {}).get("kind") == "normal":
        # `IsRegularAttack(abilityType)` -> `NormalAttackIsBlocked() = any(v[+8])`.
        return not any(b["include_normal_attack"] for b in blockers)
    # `ActiveAbilitiesAreBlocked() = blockers.Count > 0` -- INCONDITIONNEL, aucun booleen consulte.
    return not blockers


def can_currently_be_used(ability: dict) -> bool:
    """`IdunBattle.Entities.Components.ActiveAbility$$get_CanCurrentlyBeUsed` sur une entree
    d'ability du canal `decisionView` (`readAbilityState`, qui lit LITTERALEMENT ces champs) :

        CanStillBeUsed(@0x28) && !IsDisabled(@0x35)
          && (!RemainingCooldownTurns(@0x2c).HasValue || Value < 1)
          && (!AmmoCost(@0x38).HasValue || HasEnoughAmmo(@0x40))

    C'est le gate que `ActiveAbilityActionGenerator.<GenerateActions>d__7` applique par ability AVANT
    tout `LoadPlaybook` -- le port ne lisait jusqu'ici que le PREMIER terme (`usable`), donc il etait
    strictement PLUS PERMISSIF que le natif sur le cooldown et les munitions.

    Le terme MUNITIONS n'a de mordant que sur les MACHINES OF WAR (`ammoCost` est null sur toute
    unite reguliere) : mesure live session 4, runner MoW `adeptExorcist` -- `1187` est
    `usable:true, hasAmmo:false` (stock `MachineOfWarAmmo` = 0 au seed BC) et le natif caste `1188`.
    Gate DECISION-ONLY, confirme le 2026-07-29 (`docs/rl/case-mow-ammo-gauge.md`) : un cast force par
    `applyAction` a munition ZERO s'execute et pose ses effets. Le stock (`PlayerComponent+0x6c`) est
    pose une fois depuis la BC et n'est JAMAIS incremente par une operation native.

    L'attaque NORMALE (`kind == 'normal'`) n'a pas d'objet `ActiveAbility` derriere (ni `usable`, ni
    cooldown, ni munitions) -> jamais gatee, comme dans `can_use_ability`."""
    a = ability or {}
    if a.get("kind") == "normal":
        return True
    if a.get("usable") is False or a.get("disabled") is True:
        return False
    cd = a.get("cooldown")
    if cd is not None and int(cd) >= 1:
        return False
    if a.get("ammoCost") is not None and a.get("hasAmmo") is False:
        return False
    return True


def all_enemies_of(units: list) -> list:
    """`IdunBattle.Core.Services.BattleQuery$$GetAllEnemiesOf(playerEntityId)` — slot d'INTERFACE
    `IBattleQuery` **0x8e**, ancre : `IdunBattle.Core.Services.RecordedSimulationRequestsBattleQuery.
    u003Cu003Ec__DisplayClass169_0$$u003CGetAllEnemiesOfu003Eb__0` (le decorateur enregistreur) appelle
    ce meme slot d'interface avec (battleQuery, playerEntityId).

    Corps natif, relu VERBATIM sur `rnca9r7q6c` :

        var set = new OrderedSet<IUnit>();
        foreach (u in <entities service>.slot(0x2f)(0))              // toutes les UNITES du board
            if (EntityExtensions.GetCurrentOwnerEntityId(u) != playerEntityId)
                set.Add(u);
        return set;

    ⚠ Le natif ne filtre NI la mort NI la position : c'est un « toutes les unites dont le proprietaire
    courant n'est pas ce joueur ». Le port lit le canal `decisionView`, ou l'appartenance est portee
    par `ctrl` (vrai = camp de l'unite qui decide) -- MEME predicat, exprime sur la seule donnee que
    le canal expose. `ctx.units` conserve les unites MORTES (cf. `decisionView keeps dead units`),
    donc ce mirror les garde AUSSI, comme le natif ; c'est l'appelant qui decide s'il les ecarte.
    (Le pendant `ctx.enemies` / `_enemies`, lui, filtre `alive` + `pos` : ne PAS le substituer ici,
    il mirroir un AUTRE ensemble.)"""
    return [u for u in (units or []) if not u.get("ctrl")]


def entity_has_effect(unit: dict, effect_type: int) -> bool:
    """`IdunBattle.Entities.EntityExtensions$$HasEffect(entity, state, requestedEffectType, onlyActive)`
    = `IsOwnerOfEffect(entity, state, type, onlyActive) || IsTargetOfEffect(entity, state, type)`.

    Le canal `decisionView` attache a chaque unite `EffectsOwnedComponent.ActiveEffectIds`
    (`frida/hooks/game/effects.ts::readEffectsByUnit`) : la liste des effets qui S'APPLIQUENT a
    l'unite -- exactement les icones de statut. Match par `effectType` (l'entier de l'enum, robuste
    au renommage) et non par `name`.

    DEUX degradations, toutes deux PERMISSIVES-EN-MOINS (le port peut rendre False la ou le natif
    rend True, jamais l'inverse) :
      - branche `IsOwnerOfEffect` : le canal ne remonte pas les effets dont l'unite est la SOURCE
        et une autre la cible (`source` est un champ de l'effet, pas une entree de la liste du
        porteur) -- seul le role CIBLE est donc teste ;
      - `onlyActive` : le hook laisse tomber les effets `removed`, et les `!active` sauf
        `includeInactive` ; le natif recoit ici un `Nullable<bool>` VIDE."""
    for e in (unit or {}).get("effects") or []:
        if not isinstance(e, dict):
            continue
        et = e.get("effectType")
        if et is not None and int(et) == int(effect_type):
            return True
    return False


def scene_has_effect(scene, uid: int, effect_type: int) -> bool:
    """`IdunBattle.Entities.EntityExtensions$$HasEffect(entity, state, requestedEffectType,
    onlyActive: null)` sur le substrat `playbook.Scene` — le MEME natif qu'`entity_has_effect`
    ci-dessus, un autre substrat (meme forme que `Scene.is_effect_target` : un noeud natif, deux
    substrats). Foyer UNIQUE des playbooks ATTACK qui posent ce predicat sur la cible du case
    (`SuppressiveFire` 1044, `Neuroparasite` 1183) : deux copies locales de ces quatre lignes
    seraient un fork de port du meme corps natif.

    Le natif est `IsOwnerOfEffect(entity, state, type, onlyActive) || IsTargetOfEffect(entity,
    state, type)`, et les DEUX branches sont ici :
      - `IsOwnerOfEffect` -> `EffectsState.has_effect` (presence non consommee). `onlyActive` vaut
        le litteral `0` a ces call-sites ⇒ le natif ne lit PAS `EffectComponent.IsActive @+0x5c` ⇒
        surtout pas `active_effects`, qui reboucle sur `is_active` (meme piege que `CamoCloak`, et
        l'inverse exact de `WireweaveNet_FirstAttack` dont le call-site teste `Any(e => e.IsActive)`).
      - `IsTargetOfEffect` -> `Scene.is_effect_target`, TRI-ETAT : `None` = geometrie non portee
        pour ce type ⇒ on ne referme pas dessus (on ne rend `True` que sur un `True` franc)."""
    eff = getattr(scene, "eff_state", None)
    if eff is not None and eff.has_effect(int(uid), effect_type=int(effect_type)):
        return True
    return getattr(scene, "is_effect_target", lambda *_a: None)(
        int(uid), int(effect_type)) is True


def adjacent_addable_count(tile: tuple, neigh_by_pos: dict | None,
                           walkable_by_pos: dict | None, occupied: set | None,
                           elev_by_pos: dict | None = None) -> int:
    """`|{ n ∈ GetAdjacentTiles(unit@tile) : CanAddUnit(n) }|` — nombre de voisins ring-1 de `tile` où
    une unité peut être placée. `GetAdjacentTiles` = IBattleQuery slot 0x4f (IdunBattle.Core.Services.BattleQuery$$GetAdjacentTiles ; prouvé
    re-expert #116 via `IdunBattle.Core.Services.MovementQuery$$IsAdjacent` + le slot-map du décorateur
    RecordedSimulationRequestsBattleQuery) -> `IterateAdjacentTiles` -> voisins `boardGraph.neighbours`
    avec la MÊME porte d'élévation `|Δelev| < 2` que `is_adjacent` (#45). Filtre chaque voisin par
    `can_add_unit`. Utilisé par `HammerOfWrathPlaybook` (+5/voisin, #116). Le call Hammer passe `(1,1,1)` =
    param3=requireEmptyOrSteppable, param4=requireWalkable, param5=allowTemporary (mapping RE via les CTORs
    des itérateurs #148 ; TileQuery inverse l'ordre des champs). Effet : temporaires INCLUS (param5=1, cf.
    `can_add_unit` flag c) ; requireWalkable + requireEmptyOrSteppable subsumés par `can_add_unit` (walkable +
    empty ; empty ⊂ emptyOrSteppable -> l'intersection GetAdjacent ∩ CanAddUnit = {walkable, empty} = ce que le
    port compte -> agree). Sans `neigh_by_pos` (offline
    pur) : fallback `hexgeo.neighbors` (dist-1, même porte d'élévation via `is_adjacent`).

    ⚠ #433-r4-r1-r4-r2-r1 : le canal est désormais propagé au `is_adjacent` du filtre. C'est un
    NO-OP **démontrable** dans les deux branches, et c'est pourquoi il est sûr : branche NATIVE,
    `p ∈ neigh_by_pos[tile]` par construction, donc l'énumération le retrouve ; branche FALLBACK,
    `neigh` est déjà la couronne hex, sur laquelle le repli géométrique rend le même verdict. Il est
    posé pour que le call-site cesse d'être à moitié branché — un demi-branchement est exactement
    ce que le cliquet garde, et le laisser ici invite le prochain à le recopier."""
    tkey = (tile[0], tile[1])
    neigh = (neigh_by_pos or {}).get(tkey)
    if neigh is None:
        neigh = list(hexgeo.neighbors(tile[0], tile[1]))   # fallback (ordre non natif, mais compte identique)
    return sum(1 for p in neigh
               if is_adjacent(tile, p, elev_by_pos, neigh_by_pos)   # 2 étages (IterateAdjacentTiles, #45)
               and can_add_unit(p, walkable_by_pos, occupied))


def gauntlets_target(tile: tuple, enemies: list, neigh_by_pos: dict | None = None,
                     elev_by_pos: dict | None = None):
    """Id de la CIBLE émise par `IdunBattle.AI.Playbook.Loki.GauntletsOfUltramarPlaybook$$EvaluateNonComparable`.

    Le natif boucle sur `GetEligibleTargetsSelectable(caster, MainTile)` et `GenerateAction(pos,
    eligible_target, Fix64(count))` : 1 action / eligible target, MÊME utilité (arc-count, tuile-only)
    -> `IdunBattle.AI.BucketSystem.Bucketu003C__Il2CppFullySharedGenericTypeu003E$$AddAction` garde le PREMIER à égalité (remplace SSI `op_GreaterThan` strict).
    L'énumération des eligible targets est INVERSÉE (`DSLFactory.Tiles`=`SortReverseSelector IdunBattleLogic.Entities.DSLFactory$$Tiles`)
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
    arc = enemies_in_arc(tile, enemies)  # fallback offline (ordre natif indisponible)
    return arc[0].get("id") if arc else None
