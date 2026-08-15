"""Board — graphe de tuiles STATIQUE pour le pathfinding fidèle.

Source = RPC `boardGraph` (capture LIVE, approche A). Par tuile :
    {id, col, row, elevation, walkable, isWall, neighbours:[id...]}
où `neighbours` = voisins NATIFS via `BattleQuery.GetAdjacentTiles(tile,
false,false,true)` = graphe géométrique COMPLET (#148 : param3=requireEmptyOrSteppable=0
inclut les occupées, param4=requireWalkable=0 inclut les murs, param5=allowTemporary=1 ;
mapping via les CTORs des itérateurs IdunBattle.Core.Services.BattleQuery$$IterateAdjacentTiles/IdunBattle.Core.Services.TileQuery$$IterateAdjacentTiles). L'ANCIEN `(true,true,true)` —
flags de `IdunBattle.Core.Services.BattleQuery$$GetFreeAdjacentTiles` (tuiles LIBRES) — EXCLUAIT les occupées + murs
(bug #148 : graphe amputé). Le board est capté une seule fois par bataille (statique).

Trois modes d'adjacence, pour les consommateurs qui n'ont qu'UNE vue (`neighbours()`) :
  - 'native'     : voisins natifs dirigés tels quels.
                   ⚠ « ~18 arêtes one-way, quirks de capture aux bords » : REFUTE, mesuré le
                   2026-08-04 sur 4 boards (`C1_74`, `C3_14`, `MC1_67`, `C6_25`) —
                   **0 arête one-way** dans les trois vues (`neighbours`, `connectivity`,
                   géométrie). Le critère natif est symétrique par CONSTRUCTION :
                   `IdunBattle.Operations.InitializeConnectivityOperation$$Execute` exige
                   `TileComponent$$HasEdge(e)` chez la tuile ET `HasEdge((e+3) % 6)` chez le
                   voisin, et `AddTileOperation$$RotateTileEdges` fixe le modulo à 6 (donc
                   `opp` est involutive) ; la porte `|dElev| < 2` du capteur est symétrique
                   aussi. L'observation datait des flags `(true,true,true)` d'AVANT #148, dont
                   `onlyEmptyOrSteppable` teste la tuile VOISINE seule — celui-là, oui, était
                   asymétrique. Détail : `docs/rl/case-433r4r1r4r2-substrat-is-adjacent.md`.
  - 'native_sym' : union des deux sens. DÉFAUT (no-op sur un graphe déjà symétrique).
  - 'evenq'      : géométrie hex even-q (parité par COLONNE) recalculée depuis
                   (col,row). Convention VÉRIFIÉE sur les tuiles natives à 6
                   voisins (gqfc5mff6c) :
                     col pair  → (-1,0)(-1,1)(0,-1)(0,1)(1,0)(1,1)
                     col impair→ (-1,-1)(-1,0)(0,-1)(0,1)(1,-1)(1,0)

⚠ **LE MODE N'ARBITRE PAS LE PATHFINDING** (#381-r3). `AddNeighbours` est un slot VIRTUEL et les
deux corps lisent deux sources différentes : la MARCHE (`BasePathfinder$$AddNeighbours`) énumère la
liste STOCKÉE du `ConnectivityComponent` -> `neighbours_native()` ; le VOL
(`FlyPathfinder$$AddNeighbours`) interroge la requête de tuiles au rayon 1 -> `neighbours_geometric()`.
Les deux pathfinders passent donc leur source EXPLICITEMENT et ne lisent jamais `neighbours()`.
Sur `C1_74` les deux vues divergent sur 74 arêtes dirigées, et un mode global se trompait
forcément d'un côté (mesuré : `evenq` sur-atteint la marche de 2 tuiles, `native_sym` sous-atteint
le vol de 1).

⚠ **TROISIÈME canal depuis #448-r1-r1-r1-r1-r2 : `neighbours_connectivity()`**, le
`ConnectivityComponent` BRUT (champ `connectivity` du `boardGraph`). Ce n'est pas un
quatrième « mode » — c'est la MÊME liste stockée que `neighbours_native()`, mais captée
SANS la porte `|Δelev| < 2` que `TileQuery$$IterateAdjacentTiles` applique au champ
`neighbours` (18 arêtes dirigées amputées sur `MC1_67`). Les deux coexistent par fidélité :
`neighbours_native` reste juste pour les sélecteurs `AdjacentTiles` (leur natif porte la
porte), `neighbours_connectivity` l'est pour `BasePathfinder$$AddNeighbours` (le sien
ne la porte pas).

⚠ **LES PATHFINDERS LE LISENT DEPUIS `#448-r1-r1-r1-r1-r2-r1`, mais par `base_add_neighbours()`,
jamais en direct** — c'est cette méthode qui porte le REPLI (canal non capté), et il n'est pas le
même selon la route. Les trois routes qui HÉRITENT `BasePathfinder$$AddNeighbours` y passent
(marche, `IgnoreTerrain`, `Beeline`) ; `FlyPathfinder` l'OVERRIDE (géométrie) et les
`ATeleportPathfinder` n'énumèrent pas de voisinage de chemin. Les trois relations d'inclusion,
MESURÉES sur trois boards : `neighbours ⊆ connectivity ⊆ géométrie`.

⚠ Les MURS sont une PROPRIÉTÉ de tuile (walkable=False), PAS une arête manquante
(cf. IdunBattle.Entities.Pathfinding.WalkPathfinder$$IsValidPathNode qui filtre via IsWalkable). Le
filtrage d'élévation (|Δ|≤1) et d'occupant se fait dans walk_pathfinder, PAS dans
le graphe (le graphe reste la topologie brute).
"""
from __future__ import annotations

EVENQ_EVEN = [(-1, 0), (-1, 1), (0, -1), (0, 1), (1, 0), (1, 1)]
EVENQ_ODD = [(-1, -1), (-1, 0), (0, -1), (0, 1), (1, -1), (1, 0)]


class Board:
    def __init__(self, tiles, adjacency: str = "native_sym"):
        self.by_coord: dict[tuple[int, int], dict] = {}
        self.by_id: dict[int, dict] = {}
        for t in tiles:
            self.by_coord[(t["col"], t["row"])] = t
            self.by_id[t["id"]] = t
        self.mode = adjacency
        self._adj: dict[int, list[int]] = {}
        self._build_adjacency(adjacency)

    def _build_adjacency(self, mode: str) -> None:
        idof = {(t["col"], t["row"]): t["id"] for t in self.by_id.values()}
        adj: dict[int, set[int]] = {tid: set() for tid in self.by_id}
        if mode in ("native", "native_sym"):
            for t in self.by_id.values():
                for n in t.get("neighbours", []):
                    if n in self.by_id:
                        adj[t["id"]].add(n)
            if mode == "native_sym":
                for a in list(adj):
                    for b in list(adj[a]):
                        adj[b].add(a)
        elif mode == "evenq":
            for t in self.by_id.values():
                ds = EVENQ_EVEN if t["col"] % 2 == 0 else EVENQ_ODD
                for dc, dr in ds:
                    nid = idof.get((t["col"] + dc, t["row"] + dr))
                    if nid is not None:
                        adj[t["id"]].add(nid)
        else:
            raise ValueError(f"adjacency mode inconnu: {mode}")
        self._adj = {k: sorted(v) for k, v in adj.items()}

    # --- accès ---
    def neighbours(self, tid: int) -> list[int]:
        return self._adj.get(tid, [])

    def neighbours_native(self, tid: int) -> list[int]:
        """Voisins de `tid` dans l'**ORDRE D'ENUMERATION NATIF**, cad le champ BRUT `neighbours`
        du `boardGraph` tel quel (ni trie, ni symetrise).

        C'est l'ordre que rend `IdunBattle.Core.Services.BattleQuery$$GetAdjacentTiles` ->
        `IdunBattle.Core.Services.BattleQuery$$IterateAdjacentTiles` ->
        `IdunBattle.Core.Services.TileQuery$$IterateAdjacentTiles` (liste d'adjacence STOCKEE sur la
        tuile), donc l'ordre dans lequel `IdunBattle.Entities.Selectors.AdjacentTilesSelector$$Select`
        remplit son `OrderedSet` -- et par consequent l'ordre du POOL que voit
        `IdunBattle.Entities.Selectors.PickRandomAmountSelector$$Select` (qui fait
        `source.Select(entities).ToList()` SANS aucun tri) et celui des `OrderBy` STABLES en aval.

        CONTRASTE avec `neighbours()`, qui trie les ids ET symetrise les aretes : utile au
        pathfinding (topologie), FAUX des que l'ordre est observable (tirage `PickRandomly`, tri
        stable a egalite, `First`). Deja etabli/valide live par `fc23f1e` (case-130 SS5, 9/9
        scenarios) et par le port DECISION `gauntlets_target` (#117).

        Repli sur `neighbours()` (ids tries) quand le champ est **ABSENT** -- board construit a la
        main dans les tests unitaires. Un champ **PRESENT et VIDE** rend `[]`, et les deux cas sont
        distingues depuis `#381-r3` (`raw is None`, pas `not raw`) : ils ne veulent pas dire la
        meme chose, et les confondre INVENTAIT six voisins la ou le natif n'en a aucun.

        Un champ vide est LEGITIME et se produit sur un board reel : `TileQuery$$IterateAdjacentTiles`
        (par lequel passe le capteur) applique une porte `|dElev| < 2` INCONDITIONNELLE, donc une
        tuile dont TOUS les voisins stockes sont a 2 niveaux ou plus ressort avec zero voisin --
        mesure `C1_74` : les deux `Water` `(2,5)` et `(4,5)`, elevation 1, entourees de 3 et 4.
        Rendre `[]` y est EXACT pour les deux consommateurs : `WalkPathfinder$$IsValidPathNode`
        refuse de toute facon ces aretes (meme porte), et `AdjacentTilesSelector` passe par le MEME
        `IterateAdjacentTiles` que le capteur, donc voit lui aussi le vide.

        2e consommateur (2026-07-28) : `IdunBattleLogic.Entities.Abilities.Active.Loki.FragBombAbility$$ExecuteBehaviour`
        attaque `Units(AdjacentTiles(target))` via un `SortedAttackSeries` qui itere le selecteur DANS SON
        ORDRE (aucun `OrderBy`) -> l'ordre des unites splash fixe la sequence de tirages de degat.
        MESURE LIVE (`probe_fragbomb_splash.py`, MC1_67, cible tuile 44) : ordre natif
        `[45, 53, 52, 43, 34, 35]`, coups splash live `53, 52, 43, 35` = l'ordre natif prive du caster
        (45) et de la tuile vide (34) ; l'ordre trie aurait donne `35, 43, 52, 53`."""
        raw = (self.by_id.get(tid) or {}).get("neighbours")
        if raw is None:                       # champ ABSENT != champ VIDE (cf. docstring)
            return self.neighbours(tid)
        return [t for t in raw if t in self.by_id]

    def neighbours_connectivity(self, tid: int) -> "list[int] | None":
        """Le `ConnectivityComponent` BRUT de `tid` -- champ `connectivity` du `boardGraph`
        (#448-r1-r1-r1-r1-r2), en TRI-ETAT.

        `None` = **canal absent** : boardGraph capte par un bundle ANTERIEUR au capteur, ou board
        construit a la main dans un test unitaire. `[]` = composant present, liste vide. Les
        confondre est la faute exacte que `#381-r3` a deja payee sur le champ `neighbours` (elle
        INVENTAIT six voisins la ou le natif n'en a aucun), et un repli silencieux sur
        `neighbours_native()` la rejouerait -- en pire, puisque c'est precisement le champ AMPUTE
        qu'on cherche a contourner.

        CE QUE C'EST. La `List<int>` d'entity ids de tuiles que
        `IdunBattle.Operations.InitializeConnectivityOperation$$Execute` construit une fois par
        bataille, sur un critere purement TOPOLOGIQUE : arete presente des DEUX cotes
        (`TileComponent$$HasEdge` sur la tuile et sur l'opposee) et voisin present sur le plateau.
        **Aucune elevation n'y entre.** C'est la source que
        `IdunBattle.Entities.Pathfinding.BasePathfinder.u003CAddNeighboursu003Ed__19$$MoveNext`
        enumere, et que `IdunBattle.Entities.Components.ConnectivityComponent$$IsNeighbour` teste.

        CONTRASTE avec `neighbours_native()`, qui est le MEME concept vu a travers
        `IdunBattle.Core.Services.TileQuery.u003CIterateAdjacentTilesu003Ed__8$$MoveNext` et sa
        porte `|dElev| < 2` INCONDITIONNELLE -- donc amputee de 18 aretes dirigees sur `MC1_67`.
        Les deux champs coexistent PAR FIDELITE : `neighbours_native` reste juste pour les
        selecteurs `AdjacentTiles` du DSL (leur natif PORTE la porte), `neighbours_connectivity`
        est juste pour le pathfinding (le sien ne la porte pas).

        Les pathfinders ne lisent PAS cette methode directement : ils passent par
        `base_add_neighbours` ci-dessous, qui porte le repli. Le rebranchement a ete fait et
        MESURE (`#448-r1-r1-r1-r1-r2-r1`, cf. la case-doc SS14)."""
        raw = (self.by_id.get(tid) or {}).get("connectivity")
        if raw is None:                       # canal ABSENT != liste VIDE (cf. docstring)
            return None
        return [t for t in raw if t in self.by_id]

    def has_connectivity_channel(self) -> bool:
        """Le `boardGraph` porte-t-il le canal `connectivity` ? (une seule tuile suffit a
        trancher : le capteur publie le champ pour TOUTES les tuiles ou pour aucune).

        Sert aux tests et aux probes a DIRE « canal non capte » au lieu de rendre un chiffre qui
        se lirait comme une mesure."""
        cached = getattr(self, "_has_conn", None)
        if cached is None:
            cached = any(t.get("connectivity") is not None for t in self.by_id.values())
            self._has_conn = cached
        return cached

    def base_add_neighbours(self, tid: int, fallback=None) -> list[int]:
        """`IdunBattle.Entities.Pathfinding.BasePathfinder$$AddNeighbours` -- LE voisinage du
        PATHFINDING, foyer unique des trois routes qui heritent ce slot (marche, `IgnoreTerrain`,
        `Beeline`). `FlyPathfinder` l'OVERRIDE et n'a rien a faire ici.

        LE DECOMPILE (`BasePathfinder.u003CAddNeighboursu003Ed__19$$MoveNext`) : l'iterateur prend
        `List` a `<composant>+0x10` -- le `ConnectivityComponent` -- et ne fait ENSUITE que
        `CheckNeighbour` (`voisin != tile`, `excluded`, vslot `IsValidPathNode` @+0x1e8). **Aucun
        filtre de terrain, aucune porte d'elevation dans l'ENUMERATION** : tout gate appartient au
        predicat d'arete du pathfinder, jamais au voisinage.

        POURQUOI CE N'EST PAS `neighbours_native`. Le champ herite `neighbours` passe par
        `IdunBattle.Core.Services.TileQuery.u003CIterateAdjacentTilesu003Ed__8$$MoveNext`, qui
        itere la MEME liste stockee puis applique, dans cet ordre : `IsTemporary` (si
        `allowTemporary` faux), `IsWalkable` (si `onlyWalkableTiles`), `IsEmptyOrSteppable` (si
        `onlyEmptyOrSteppable`), et **une porte `|dElev| < 2` INCONDITIONNELLE**. Le capteur
        appelle `BattleQuery$$GetAdjacentTiles(tile, false, false, true)`, donc les trois premiers
        filtres sont OFF et il ne reste QUE la porte. D'ou l'identite, LUE et non supposee :

            neighbours == connectivity INTERSECTE {aretes de |dElev| < 2}

        Mesuree le 2026-08-04 (`probe_448r1r1r1r1r2_connectivity_channel_live.py`) : `C \\ N` = 18
        aretes dirigees sur `MC1_67`, 58 sur `C1_74`, 0 sur `C6_25`, et `N \\ C` = **0** partout.

        LE REPLI EST UN CHOIX PAR ROUTE, jamais un defaut universel -- `fallback(tid)` sert
        uniquement quand le `boardGraph` est ANTERIEUR au capteur (`connectivity` absent) :

          * `None` -> `neighbours_native` : le champ ampute, donc une degradation RESTRICTIVE.
            C'est le statu quo des routes a porte d'elevation (marche, `IgnoreTerrain`), pour qui
            l'amputation est de toute facon INERTE -- leur `IsValidPathNode` exige `|dElev| <= 1`
            et refuse donc exactement les aretes que le champ omet ;
          * `self.neighbours_geometric` pour la `Beeline`, dont le `IsValidPathNode` est le corps
            trivial `return true` : sur elle l'amputation MORD, et la geometrie est le proxy que
            la mesure de #448-r1-r1-r1-r1 SS9 avait impose (le natif enregistre 2 la ou le champ
            ampute faisait rendre 3). Retomber sur `neighbours_native` y rejouerait le bug.

        Memoise sur l'instance (le board est STATIQUE pour toute la bataille)."""
        cache = getattr(self, "_conn_adj", None)
        if cache is None:
            cache = {}
            if self.has_connectivity_channel():
                for t in self.by_id.values():
                    raw = t.get("connectivity")
                    if raw is not None:
                        cache[t["id"]] = [n for n in raw if n in self.by_id]
            self._conn_adj = cache
        got = cache.get(int(tid))
        if got is not None:
            return got
        return (fallback or self.neighbours_native)(int(tid))

    def teleport_twin(self, tid: int) -> "int | None":
        """La tuile de TELEPORT jumelle de `tid` (`ConnectivityComponent+0x18`), ou `None`.

        `0` cote natif = « pas une tuile de teleport » -- c'est la valeur exacte que testent les
        quatre surcharges de `IdunBattle.Entities.TileExtensions$$IsTeleportationTile`, et on la
        rend `None` plutot que `0` pour qu'aucun appelant ne la prenne pour un id de tuile.
        `None` couvre donc DEUX cas indiscernables ici : pas de teleport, et canal non capte --
        `neighbours_connectivity(tid) is None` les separe.

        Ferme la source qui manquait a deux residus nommes : `AddTeleportationTiles`
        (`base_pathfinder.py`) et le second critere de retention d'un waypoint de
        `IdunBattle.Entities.Pathfinding.FlyPathfinder$$FindPath` (`IsTeleportationTile`)."""
        v = (self.by_id.get(tid) or {}).get("teleportTwinTileId")
        if v is None:
            return None
        v = int(v)
        return v if v != 0 else None

    def neighbours_geometric(self, tid: int) -> list[int]:
        """Voisins GEOMETRIQUES de `tid` -- la couronne hex even-q recalculee depuis `(col, row)`,
        restreinte aux tuiles du board, INDEPENDAMMENT du mode d'adjacence de l'instance.

        C'est le substrat de `IdunBattle.Entities.Pathfinding.FlyPathfinder$$AddNeighbours`
        (`u003CAddNeighboursu003Ed__7$$MoveNext`), qui n'itere PAS la liste stockee sur la tuile mais
        interroge la requete de tuiles au rayon 1 (`IdunBattle.Core.Services.BattleQuery$$
        GetSurroundingTiles`) puis ecarte le centre (`while (lVar4 == this+0x30)`). L'override est
        REEL : `FlyPathfinder$$AddNeighbours` occupe le meme slot virtuel (`vslot 0x238`) que
        `IdunBattle.Entities.Pathfinding.BasePathfinder$$AddNeighbours` -- leurs seules XREFS sont
        des entrees de vtable, elles ne s'appellent pas.

        CONTRASTE avec `neighbours_native()` (le `ConnectivityComponent`, que lit la MARCHE) : sur
        `C1_74` les deux vues divergent sur **74 aretes dirigees**, toutes dans le sens
        geometrie \\ connectivity -- 70 par la porte d'elevation du capteur, 4 parce que le
        `ConnectivityComponent` ne relie pas les deux `Bridge` a leur voisin de niveau ((1,5)-(2,4)
        et (4,4)-(5,5)). Le mode du `Board` ne doit donc PAS arbitrer : chaque pathfinder lit SA
        source (#381-r3).

        ORDRE : trie par id. Le natif itere l'ordre de `GetSurroundingTiles` ; il n'est pas
        observable ici (le BFS accumule un `set`, et un voisin deja visite est ignore quel que soit
        l'ordre d'arrivee). Memoise sur l'instance (le board est STATIQUE)."""
        cached = getattr(self, "_geo_adj", None)
        if cached is None:
            idof = {(t["col"], t["row"]): t["id"] for t in self.by_id.values()}
            cached = {}
            for t in self.by_id.values():
                ds = EVENQ_EVEN if t["col"] % 2 == 0 else EVENQ_ODD
                cached[t["id"]] = sorted(
                    nid for nid in (idof.get((t["col"] + dc, t["row"] + dr)) for dc, dr in ds)
                    if nid is not None)
            self._geo_adj = cached
        return cached.get(tid, [])

    def tile_at(self, col: int, row: int) -> dict | None:
        return self.by_coord.get((col, row))

    def id_at(self, col: int, row: int) -> int | None:
        t = self.by_coord.get((col, row))
        return t["id"] if t else None

    def elevation(self, tid: int) -> int:
        return self.by_id[tid]["elevation"]

    def walkable(self, tid: int) -> bool:
        return bool(self.by_id[tid]["walkable"])

    def is_wall(self, tid: int) -> bool:
        """`TileComponent.IsWall` (`+0x41`) — le flag que lit `IdunBattle.Entities.Pathfinding
        .FlyPathfinder$$IsValidPathNode` (et que confirme `FlyPathfinder$$IsAnyAdjacentTileWall`,
        qui teste ce MEME offset). Publie par le `boardGraph` (`isWall`), distinct de `walkable` :
        une tuile `Block`/`Water` est `walkable=False` mais `isWall=False` — le vol la TRAVERSE.

        Repli sur `not walkable` quand le champ manque (board construit a la main dans un test
        unitaire) : c'est le comportement d'AVANT #403, donc jamais une regression silencieuse."""
        t = self.by_id.get(tid)
        if t is None:
            return True
        if "isWall" in t:
            return bool(t["isWall"])
        return not bool(t.get("walkable", True))

    def coord(self, tid: int) -> tuple[int, int]:
        t = self.by_id[tid]
        return (t["col"], t["row"])

    # --- terrain (tileDefId, capteur boardGraph #124) ---
    def tile_def_id(self, tid: int) -> str | None:
        """Terrain de la tuile (`TileId` de la BC : Grass/DryBush/Trench/FirstAid/...), ou None si non
        capte (boardGraph d'un build ANTERIEUR au capteur tileDefId). Base des effets de tuile
        (LightCover=DryBush, Trench, ...) — cf. docs/rl/terrain-effects.md."""
        return self.by_id.get(tid, {}).get("tileDefId")

    def terrain_at(self, col: int, row: int) -> str | None:
        t = self.by_coord.get((col, row))
        return t.get("tileDefId") if t else None

    def coords_with_terrain(self, tile_id: str) -> set[tuple[int, int]]:
        """Ensemble des (col,row) portant ce terrain (ex. 'DryBush' = tuiles cover LightCover ;
        'Trench'). Vide si le terrain n'est pas capte. Base des gates compute-time des effets de tuile."""
        return {(t["col"], t["row"]) for t in self.by_id.values()
                if t.get("tileDefId") == tile_id}

    # --- substrat PAR POSITION du WalkPathfinder (foyer unique des DEUX faces) ---
    def walk_maps_by_pos(self) -> tuple[dict, dict, dict]:
        """`(neigh_by_pos, walkable_by_pos, elev_by_pos)` — le substrat que
        `entities.pathfinding.walk_pathfinder.get_path_node_counts_by_pos` attend.

        FOYER UNIQUE : la face DECISION (`playbook/prediction/_shared.py::_walk_path_counts_from`)
        et la face COMBAT (`runner/operations/movement.py::_num_tiles_moved`) doivent voir le MEME
        graphe, sinon `TilesMovedThisTurn` diverge d'une face a l'autre alors que le natif n'a
        qu'un seul `IPathfinders`.

        ⚠ `neigh_by_pos` est le voisinage du PATHFINDING (`base_add_neighbours` : le
        `ConnectivityComponent`, repli sur le champ herite `neighbours` quand le canal n'est pas
        capte), ni trie ni symetrise -- PAS `self.neighbours()`, qui depend du `adjacency=` de
        l'instance donc du montage de l'appelant.

        Le rebranchement sur le canal (`#448-r1-r1-r1-r1-r2-r1`) est un NO-OP **prouve** sur cette
        route, et c'est pour ca qu'il est sur : les aretes que le canal ajoute au champ herite sont
        exactement celles de `|dElev| >= 2` (cf. `base_add_neighbours`), or l'arete de marche
        (`WalkPathfinder$$IsValidPathNode` -> `$$IsReachableElevationDifference`) exige
        `|dElev| <= 1` et les refuse toutes. Il ne change donc RIEN aujourd'hui ; il rend la route
        independante d'une porte qui appartient au CAPTEUR et non au natif mirrore. Memoise sur
        l'instance (le board est STATIQUE pour toute la bataille)."""
        cached = getattr(self, "_walk_maps", None)
        if cached is not None:
            return cached
        by_id = self.by_id
        pos_of = {tid: (t["col"], t["row"]) for tid, t in by_id.items()}
        neigh = {pos_of[tid]: [pos_of[n] for n in self.base_add_neighbours(tid) if n in pos_of]
                 for tid, t in by_id.items()}
        walk = {pos_of[tid]: bool(t.get("walkable")) for tid, t in by_id.items()}
        elev = {pos_of[tid]: int(t.get("elevation") or 0) for tid, t in by_id.items()}
        maps = (neigh, walk, elev)
        self._walk_maps = maps
        return maps

    # --- substrat PAR POSITION de la PORTE D'ELEVATION (foyer unique du canal) ------------------
    def elev_by_pos(self) -> dict:
        """`{(col,row): elevation}` -- le canal que consomme la porte d'elevation native.

        ⚠ CE N'EST PAS le 3e element de `walk_maps_by_pos()`, et les deux ne peuvent pas fusionner :
        celui-la rend `int(elevation or 0)` (le pathfinder a besoin d'une fonction TOTALE), celui-ci
        **OMET** toute tuile dont l'elevation n'est pas captee. La difference est decisive parce que
        les deux consommateurs n'ont pas le meme contrat sur l'INCONNU : coter `0` une elevation non
        mesuree FABRIQUE une donnee, et la porte deviendrait RESTRICTIVE (un voisin a 2 refuse a tort
        contre une tuile « 0 » inventee) -- un faux negatif d'adjacence SUPPRIME des actions legales,
        ce qui est pire que la degradation permissive qu'on ferme ici. Omettre laisse au foyer
        `battle_query.is_adjacent` son repli documente (« les DEUX elevations connues, sinon on
        retient »).

        Memoise sur l'instance (le board est STATIQUE pour toute la bataille)."""
        cached = getattr(self, "_elev_by_pos", None)
        if cached is None:
            cached = {(t["col"], t["row"]): int(t["elevation"])
                      for t in self.by_id.values()
                      if t.get("elevation") is not None
                      and t.get("col") is not None and t.get("row") is not None}
            self._elev_by_pos = cached
        return cached


def connectivity_neighbours(board, tile_id) -> "list[int] | None":
    """Le `ConnectivityComponent` de `tile_id` pour un board DUCK-TYPE, en TRI-ETAT --
    `None` = **pas de canal** (rien mesure), une liste = la liste STOCKEE.

    Meme role, et meme raison d'exister, que `elevations_by_pos` juste dessous : `board` est
    duck-type dans tout le DSL et dans `services/`, donc un lecteur hors `Board` a besoin d'une
    porte d'entree unique qui DISE « non mesure » au lieu de rendre un graphe vide.

    Le lecteur vise est `IdunBattle.Entities.Components.ConnectivityComponent$$IsNeighbour`
    (`return this[+0x10].Contains(<entity id de tile>)`), qu'appelle
    `IdunBattle.Core.Services.MovementUtil$$AreTilesAdjacent` -- **pas** `IterateAdjacentTiles`,
    donc pas le champ herite `neighbours` : la porte `|dElev| < 2` y est un terme SEPARE
    (`iVar7 < 2 & bVar3`), lisible dans le decompile, et non un filtre du voisinage."""
    if board is None or tile_id is None:
        return None
    getter = getattr(board, "neighbours_connectivity", None)
    if getter is None:
        return None
    return getter(int(tile_id))


def elevations_by_pos(board) -> dict | None:
    """Le canal d'elevation d'un board, en TRI-ETAT -- `None` = **pas de canal** (rien mesure),
    `{...}` = la carte des tuiles dont l'elevation EST captee.

    C'est la seule porte d'entree du port vers `tile->[0x20]->[0x18]`, l'entier que le natif lit
    dans les DEUX foyers de la porte d'elevation :

      * `IdunBattle.Core.Services.TileQuery.u003CIterateAdjacentTilesu003Ed__8$$MoveNext` -- apres
        les filtres terrain, `d = |elev(source) - elev(voisin)| ; if (d < 2) yield` (source lue une
        fois a l'init dans `d__8+0x48`, voisin relu par tuile) ;
      * `IdunBattle.Core.Services.MovementUtil$$AreTilesAdjacent(tile1, tile2)` --
        `return (|dElev| < 2) & (tile1 == tile2 || ConnectivityComponent.IsNeighbour(tile1, tile2))`.

    Le natif n'a PAS d'etat « elevation inconnue » : il deref le composant et LEVE s'il manque
    (`TileExtensions$$GetElevationDifference`). L'inconnu est donc une notion strictement PORT (un
    board construit a la main dans un test, un `boardGraph` anterieur au capteur) -- d'ou le
    tri-etat, et d'ou l'omission plutot qu'un `0` par defaut.

    `board` est DUCK-TYPE dans tout le DSL (`ctx.board` : `id_at`/`neighbours`/`walkable`), donc on
    accepte les deux formes portees : un `Board` (canal `by_id`) et tout objet exposant `by_coord`.
    Aucune des deux -> `None`, jamais une carte vide qui se ferait passer pour une mesure."""
    if board is None:
        return None
    if isinstance(board, Board):
        m = board.elev_by_pos()
        return m or None
    by_coord = getattr(board, "by_coord", None)
    if isinstance(by_coord, dict):
        m = {k: int(t["elevation"]) for k, t in by_coord.items()
             if isinstance(t, dict) and t.get("elevation") is not None}
        return m or None
    by_id = getattr(board, "by_id", None)
    if isinstance(by_id, dict):
        m = {(t["col"], t["row"]): int(t["elevation"]) for t in by_id.values()
             if isinstance(t, dict) and t.get("elevation") is not None
             and t.get("col") is not None and t.get("row") is not None}
        return m or None
    return None


def adjacent_neigh_by_pos(board) -> dict | None:
    """Le canal de VOISINAGE d'`IterateAdjacentTiles`, PAR POSITION, en TRI-ETAT -- `None` = **pas
    de canal** (rien mesure), jamais `{}`. Pendant exact d'`elevations_by_pos` ci-dessus, pour le
    PREMIER etage de la primitive (l'enumeration) la ou celui-la porte le SECOND (la porte).

    C'est le champ BRUT `neighbours` du `boardGraph` (`Board.neighbours_native`), resolu en
    positions : la liste STOCKEE du `ConnectivityComponent` telle que
    `IdunBattle.Core.Services.BattleQuery$$GetAdjacentTiles(t, 0, 0, 1)` la rend -- donc a travers
    `IdunBattle.Core.Services.TileQuery.u003CIterateAdjacentTilesu003Ed__8$$MoveNext`, exactement
    l'iterateur que `battle_query.is_adjacent` mirroir.

    ⚠ TROIS voisinages coexistent sur un `Board`, et ils ne sont PAS interchangeables (#381-r3) :
      * celui-ci (`neighbours_native`) -- la liste stockee AVEC la porte d'elevation du capteur.
        C'est le substrat des selecteurs `AdjacentTiles` et des comptages `GetAdjacent*` ;
      * `base_add_neighbours` (le `ConnectivityComponent` BRUT, SANS porte) -- celui du PATHFINDING,
        expose par `walk_maps_by_pos()[0]`. Le confondre avec celui-ci rendrait la primitive
        d'adjacence PERMISSIVE sur les aretes a `|dElev| >= 2` ;
      * `neighbours_geometric` (la couronne hex) -- celui du VOL, et l'ancien substrat de
        `is_adjacent`, qui sur-atteint la liste stockee de 4 aretes sur `C1_74` et 38 sur `C3_14`.

    `board` est DUCK-TYPE dans tout le DSL, d'ou les deux formes acceptees (un `Board`, ou tout
    objet exposant `by_id`). Une tuile dont le champ `neighbours` est ABSENT est OMISE de la carte
    -- `is_adjacent` retombe alors sur sa couronne hex POUR CETTE TUILE, ce qui est la degradation
    d'avant ; l'y coter `[]` la rendrait au contraire isolee, un faux negatif d'adjacence (le vice
    de `#381-r3`).

    MEMOISE sur l'instance de board (#433-r4-r1-r4-r2-r1), comme `Board.elev_by_pos` et
    `walk_maps_by_pos` : le graphe est STATIQUE pour toute la bataille -- c'est LU (les seuls
    ecrivains de `ConnectivityComponent` sont `InitializeConnectivityOperation$$Execute` pour
    `+0x10` et `$$ConnectTeleportTiles` pour `+0x18`, tous deux en passe unique) -- alors que les
    appelants COMBAT (`runner.components.update_charging`, un appel par pas de deplacement ;
    `runner.damage_model.battle_query_is_charging`, un appel par coup) sont sur des chemins chauds
    ou une reconstruction en O(tuiles) serait payee des milliers de fois. Le cache est pose par
    `setattr` protege : un board duck-type peut le refuser (`__slots__`, mapping fige), auquel cas
    on recalcule -- jamais on n'echoue."""
    if board is None:
        return None
    cached = getattr(board, "_adjacent_neigh_by_pos", "?")
    if cached != "?":
        return cached
    by_id = getattr(board, "by_id", None)
    if not isinstance(by_id, dict) or not by_id:
        return None
    pos_of = {tid: (t["col"], t["row"]) for tid, t in by_id.items()
              if isinstance(t, dict) and t.get("col") is not None and t.get("row") is not None}
    out = {}
    for tid, t in by_id.items():
        if tid not in pos_of or not isinstance(t, dict) or t.get("neighbours") is None:
            continue          # champ ABSENT != champ VIDE -- on OMET, on ne cote pas `[]`
        out[pos_of[tid]] = [pos_of[n] for n in t["neighbours"] if n in pos_of]
    res = out or None
    try:
        setattr(board, "_adjacent_neigh_by_pos", res)
    except (AttributeError, TypeError):
        pass                  # board fige -> on recalcule ; le resultat est le meme
    return res


def adjacency_channels(board) -> "tuple[dict | None, dict | None]":
    """`(elev_by_pos, neigh_by_pos)` -- les DEUX etages d'`IdunBattle.Core.Services.TileQuery
    .u003CIterateAdjacentTilesu003Ed__8$$MoveNext` derives d'un MEME board, en TRI-ETAT.

    FOYER UNIQUE de la derivation (#943-r7). Elle tient en deux appels, et c'est precisement ce qui
    la faisait recopier : cinq modules d'effets en portaient une copie privee, donc cinq endroits ou
    l'ordre du couple, le tri-etat ou le repli pouvaient diverger sans que rien ne le dise. Les
    consommateurs passent le resultat tel quel a `engine.battle_query.is_adjacent` /
    `.are_entities_adjacent`, dont les deux derniers parametres sont dans CET ordre.

    `board is None` -> `(None, None)`, jamais `({}, {})` : c'est le repli GEOMETRIQUE nomme du foyer
    d'adjacence, pas un voisinage vide (qui rendrait le predicat FAUX partout, vice #381-r3)."""
    return elevations_by_pos(board), adjacent_neigh_by_pos(board)
