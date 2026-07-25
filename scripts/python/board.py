#!/usr/bin/env python
"""board — carte hex LOGIQUE du plateau depuis la BattleConfiguration.

Statique par board (la BC ne change pas en cours de battle). Donne terrain
(TileId), élévation, jouabilité, spawns — dans le repère hex (cf. hexgeo).
Le visuel (PNG+grille) reste au front (hex.js/hex-calibration.js).

Source : BC.Board.{Id,Width,Height,Tiles[col].Tile[row]={TileId,Elevation,
ForceUnplayable,...}, SpawnPointSets}. Décodage TeamWithPlayerIndex (TWPI)
aligné sur frida/public/src/board.js.

Usage :
    python scripts/python/board.py            # valide sur le seed BC (data/seed-bc.json)
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import hexgeo  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
# seed BC template (data/ gitignore, per-hash) — regenere par `dump_boards.py` (#159).
SEED_BC = ROOT / "data" / "seed-bc.json"

# TeamWithPlayerIndex -> (teamId, playerIdx). Cf. board.js / TeamPlayerIdExtensions.Unfold.
_TWPI = {
    0: (1, 0), 1: (2, 0), 2: (1, 1), 3: (2, 1),
    4: (3, 0), 5: (3, 1), 6: (0, 0),
}

# Glyphes terrain pour le rendu ASCII. TF20 : SYMBOLES uniquement (jamais de
# lettres) → disjoint des lettres d'unités (A-Z=moi / a-z=ennemi). Avant,
# Swamp='s'/DryBush='b' collisionnaient avec les lettres d'unités minuscules →
# glyphe ambigu sur une rangée (mis-lecture de position). Fallback non-lettre aussi.
_GLYPH = {
    "Grass": ".", "Water": "~", "Block": "#", "Bridge": "=",
    "Swamp": "%", "DryBush": "*",
}


def _effective_elevation(tile_id: str | None, bc_elevation) -> int:
    """Élévation EFFECTIVE d'une tuile = celle que le jeu expose (ElevationComponent,
    `IdunBattle.Entities.TileExtensions$$GetElevation`, capté par boardGraph/tileMeta), à partir du
    champ BC brut (`Board.Tiles[..].Elevation`).

    Règle mesurée (#195, LIVE vs BC sur 6 boards C2_16/17/18/19/20/32) : **Trench = terrain
    CREUSÉ → élévation effective = champ BC − 1** (uniforme, sans clamp) ; tous les autres
    TileId (Grass/Swamp/DryBush/Water/Bridge/Block) gardent leur champ BC à l'identique.
    Ex. Trench BC 0→-1, BC 1→0, BC 2→1. (Le composant ElevationComponent EXISTE et stocke
    déjà BC−1 : l'hypothèse « composant absent → -1 » est réfutée par C2_16 où Trench=1>0.)

    Le board ENGINE numérique (prédiction #182/#184, adjacence #187) lit boardGraph, qui
    baked déjà ce -1 → correct (bit-exact). Cette fonction n'aligne QUE le board dérivé du
    champ BC brut (ce module `board.py`, oracle-card) sur la vérité live."""
    e = int(bc_elevation or 0)
    return e - 1 if tile_id == "Trench" else e


class Board:
    def __init__(self, bc: dict):
        b = bc.get("Board") or {}
        self.board_id = b.get("Id")
        cols = b.get("Tiles") or []
        self.width = b.get("Width") or len(cols)
        self.height = b.get("Height") or 0
        self.tiles: dict[tuple[int, int], dict] = {}
        for c, col in enumerate(cols):
            rows = (col or {}).get("Tile") or []
            for r, t in enumerate(rows):
                if t is None:
                    continue
                self.tiles[(c, r)] = {
                    "tileId": t.get("TileId"),
                    "elevation": _effective_elevation(t.get("TileId"), t.get("Elevation", 0)),
                    "forceUnplayable": bool(t.get("ForceUnplayable")),
                }
        if not self.height and self.tiles:
            self.height = 1 + max(r for _c, r in self.tiles)
        self.spawns = self._decode_spawns(bc, b)
        for key, info in self.tiles.items():
            info["playable"] = not info["forceUnplayable"]
            info["spawn"] = self.spawns.get(key)

    def _decode_spawns(self, bc: dict, b: dict) -> dict:
        out: dict[tuple[int, int], dict] = {}
        idx = bc.get("SpawnPointSetIndex", 0) or 0
        sets = b.get("SpawnPointSets") or []
        if idx >= len(sets):
            return out
        s = sets[idx] or {}
        players = ((bc.get("Player") or {}).get("Players")) or {}
        by_team: dict[int, list[int]] = {}
        for pid, p in players.items():
            tid = (p or {}).get("TeamId", 0)
            by_team.setdefault(tid, []).append(int(pid))
        for g in (s.get("SpawnPointGroups") or []):
            raw = g.get("TeamWithPlayerIndex")
            if isinstance(raw, dict):
                raw = raw.get("value", 0)
            team, pidx = _TWPI.get(raw, (raw, 0))
            tps = by_team.get(team) or []
            pid = tps[pidx] if pidx is not None and pidx < len(tps) else None
            for sp in (g.get("SpawnPoints") or []):
                out[(sp.get("Column"), sp.get("Row"))] = {"team": team, "player": pid}
        return out

    # --- accès ---
    def tile(self, col: int, row: int) -> dict | None:
        return self.tiles.get((col, row))

    def is_playable(self, col: int, row: int) -> bool:
        t = self.tiles.get((col, row))
        return bool(t and t["playable"])

    def blocks_los(self, col: int, row: int) -> bool:
        """Tile qui coupe la ligne de vue (ranged) : terrain Block, tile
        non-jouable, ou trou hors-plateau. Approx (ignore l'élévation)."""
        t = self.tiles.get((col, row))
        if t is None:
            return True
        return (not t["playable"]) or t["tileId"] == "Block"

    def has_los(self, a, b) -> bool:
        """Ligne de vue de `a` à `b` : aucune tile INTERMÉDIAIRE ne bloque
        (endpoints exclus). Pour le ranged dans la danger zone."""
        ln = hexgeo.line(a, b)
        return not any(self.blocks_los(*t) for t in ln[1:-1])

    def playable_tiles(self) -> dict:
        return {k: v for k, v in self.tiles.items() if v["playable"]}

    def terrain_counts(self) -> Counter:
        return Counter(v["tileId"] for v in self.tiles.values())

    def distance(self, a, b) -> int:
        return hexgeo.distance(a, b)

    def neighbors(self, col: int, row: int) -> list:
        """Voisins hex EXISTANTS et jouables."""
        return [n for n in hexgeo.neighbors(col, row) if self.is_playable(*n)]

    def disk_playable(self, col: int, row: int, radius: int) -> list:
        return [t for t in hexgeo.disk(col, row, radius) if self.is_playable(*t)]

    # --- rendu ---
    def ascii(self) -> str:
        header = "     " + " ".join(f"{c % 10}" for c in range(self.width))
        lines = [header]
        for row in range(self.height - 1, -1, -1):  # top = row haut (cf. visualRow)
            cells = []
            for col in range(self.width):
                t = self.tiles.get((col, row))
                if t is None or not t["playable"]:
                    cells.append(" ")
                    continue
                sp = t.get("spawn")
                if sp:
                    cells.append(str(sp["team"]))
                    continue
                tid = t["tileId"] or "?"
                cells.append(_GLYPH.get(tid, "?"))
            lines.append(f"r{row:2d}  " + " ".join(cells))
        legend = ("legend: . grass  ~ water  # block  = bridge  % swamp  * drybush  "
                  "? autre  <chiffre>=spawn team   (col impaire décalée +1/2, odd-q)")
        return "\n".join(lines) + "\n" + legend


def from_seed() -> Board:
    return Board(json.loads(SEED_BC.read_text(encoding="utf-8")))


def _validate() -> int:
    if not SEED_BC.exists():
        print(f"[error] seed BC introuvable: {SEED_BC} — regenere via "
              f"`python dump_boards.py`.", file=sys.stderr)
        return 2
    bd = from_seed()
    print(f"[board] id={bd.board_id} dims={bd.width}x{bd.height} "
          f"tiles={len(bd.tiles)} jouables={len(bd.playable_tiles())}")
    print(f"[terrain] {dict(bd.terrain_counts())}")
    print(f"[spawns] {len(bd.spawns)} : "
          + ", ".join(f"({c},{r})->t{v['team']}/p{v['player']}"
                      for (c, r), v in list(bd.spawns.items())[:12]))
    # sanity distances : 2 spawns du même côté proches, côtés opposés loin.
    sp = list(bd.spawns.keys())
    if len(sp) >= 2:
        print(f"[dist] exemple {sp[0]}->{sp[-1]} = {bd.distance(sp[0], sp[-1])} hex")
    print("[ascii]")
    print(bd.ascii())
    return 0


if __name__ == "__main__":
    sys.exit(_validate())
