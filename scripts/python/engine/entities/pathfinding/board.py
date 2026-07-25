"""Board — graphe de tuiles STATIQUE pour le pathfinding fidèle.

Source = RPC `boardGraph` (capture LIVE, approche A). Par tuile :
    {id, col, row, elevation, walkable, isWall, neighbours:[id...]}
où `neighbours` = voisins NATIFS via `BattleQuery.GetAdjacentTiles(tile,
false,false,true)` = graphe géométrique COMPLET (#148 : param3=requireEmptyOrSteppable=0
inclut les occupées, param4=requireWalkable=0 inclut les murs, param5=allowTemporary=1 ;
mapping via les CTORs des itérateurs IdunBattle.Core.Services.BattleQuery$$IterateAdjacentTiles/IdunBattle.Core.Services.TileQuery$$IterateAdjacentTiles). L'ANCIEN `(true,true,true)` —
flags de `IdunBattle.Core.Services.BattleQuery$$GetFreeAdjacentTiles` (tuiles LIBRES) — EXCLUAIT les occupées + murs
(bug #148 : graphe amputé). Le board est capté une seule fois par bataille (statique).

Trois modes d'adjacence (la vérité-terrain `aiMovableTiles` tranche lequel est
fidèle) :
  - 'native'     : voisins natifs dirigés tels quels (peuvent être asymétriques —
                   ~18 arêtes one-way observées, quirks de capture aux bords).
  - 'native_sym' : union des deux sens (corrige l'asymétrie). DÉFAUT.
  - 'evenq'      : géométrie hex even-q (parité par COLONNE) recalculée depuis
                   (col,row). Convention VÉRIFIÉE sur les tuiles natives à 6
                   voisins (gqfc5mff6c) :
                     col pair  → (-1,0)(-1,1)(0,-1)(0,1)(1,0)(1,1)
                     col impair→ (-1,-1)(-1,0)(0,-1)(0,1)(1,-1)(1,0)

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

    def tile_at(self, col: int, row: int) -> dict | None:
        return self.by_coord.get((col, row))

    def id_at(self, col: int, row: int) -> int | None:
        t = self.by_coord.get((col, row))
        return t["id"] if t else None

    def elevation(self, tid: int) -> int:
        return self.by_id[tid]["elevation"]

    def walkable(self, tid: int) -> bool:
        return bool(self.by_id[tid]["walkable"])

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
