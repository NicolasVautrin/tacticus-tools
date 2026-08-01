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
  - 'native'     : voisins natifs dirigés tels quels (peuvent être asymétriques —
                   ~18 arêtes one-way observées, quirks de capture aux bords).
  - 'native_sym' : union des deux sens (corrige l'asymétrie). DÉFAUT.
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

        ⚠ `neigh_by_pos` est bati sur le champ BRUT `neighbours` du `boardGraph` (ni trie ni
        symetrise), PAS sur `self.neighbours()` : c'est la liste d'adjacence STOCKEE sur la tuile,
        celle qu'itere `IdunBattle.Core.Services.TileQuery$$IterateAdjacentTiles`. Memoise sur
        l'instance (le board est STATIQUE pour toute la bataille)."""
        cached = getattr(self, "_walk_maps", None)
        if cached is not None:
            return cached
        by_id = self.by_id
        pos_of = {tid: (t["col"], t["row"]) for tid, t in by_id.items()}
        neigh = {pos_of[tid]: [pos_of[n] for n in (t.get("neighbours") or []) if n in pos_of]
                 for tid, t in by_id.items()}
        walk = {pos_of[tid]: bool(t.get("walkable")) for tid, t in by_id.items()}
        elev = {pos_of[tid]: int(t.get("elevation") or 0) for tid, t in by_id.items()}
        maps = (neigh, walk, elev)
        self._walk_maps = maps
        return maps
