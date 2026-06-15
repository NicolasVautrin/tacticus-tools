#!/usr/bin/env python
"""hexgeo — géométrie hexagonale du plateau Tacticus (repère MOTEUR).

Dérivé de la formule moteur (cf. frida/public/src/hex.js,
`HexUtils.GetTileWorldPosition`) :
    world.x = col * 3
    world.z = row * 2*sqrt(3) + (col impair ? sqrt(3) : 0)
→ hexagones **flat-top**, **colonnes décalées odd-q** (colonnes impaires
  décalées de +1/2 ligne). 6 voisins.

Coordonnées de jeu = (col, row) "offset". Pour distance/portée on convertit en
cube (x, y, z), x+y+z=0 :
    x = col ; z = row - (col - (col & 1)) // 2 ; y = -x - z
distance(a, b) = (|dx| + |dy| + |dz|) / 2

Voisins dérivés directement de la géométrie monde (donc fidèles au moteur ;
chaque voisin est à distance cube 1 — vérifié par _selftest) :
    col pair   : (0,+1)(0,-1)(+1,0)(+1,-1)(-1,0)(-1,-1)
    col impair : (0,+1)(0,-1)(+1,+1)(+1,0)(-1,+1)(-1,0)

Le visuel (PNG↔pixel) reste au front (hex.js/hex-calibration.js). Ici = LOGIQUE
pure pour le raisonnement de l'oracle.
"""
from __future__ import annotations

Coord = tuple  # (col, row)

_NEIGHBORS_EVEN = [(0, 1), (0, -1), (1, 0), (1, -1), (-1, 0), (-1, -1)]
_NEIGHBORS_ODD = [(0, 1), (0, -1), (1, 1), (1, 0), (-1, 1), (-1, 0)]


def to_cube(col: int, row: int) -> tuple[int, int, int]:
    x = col
    z = row - (col - (col & 1)) // 2
    return (x, -x - z, z)


def from_cube(x: int, z: int) -> tuple[int, int]:
    col = x
    row = z + (col - (col & 1)) // 2
    return (col, row)


def distance(a: Coord, b: Coord) -> int:
    ax, ay, az = to_cube(a[0], a[1])
    bx, by, bz = to_cube(b[0], b[1])
    return (abs(ax - bx) + abs(ay - by) + abs(az - bz)) // 2


def neighbors(col: int, row: int) -> list[Coord]:
    deltas = _NEIGHBORS_ODD if (col & 1) else _NEIGHBORS_EVEN
    return [(col + dc, row + dr) for dc, dr in deltas]


def disk(col: int, row: int, radius: int) -> list[Coord]:
    """Toutes les tiles à distance hex <= radius (centre inclus). NON clippé
    aux bords du plateau — le caller filtre avec la Board."""
    cx, _cy, cz = to_cube(col, row)
    out: list[Coord] = []
    for dx in range(-radius, radius + 1):
        lo = max(-radius, -dx - radius)
        hi = min(radius, -dx + radius)
        for dy in range(lo, hi + 1):
            dz = -dx - dy
            out.append(from_cube(cx + dx, cz + dz))
    return out


def ring(col: int, row: int, radius: int) -> list[Coord]:
    """Tiles exactement à distance hex == radius."""
    if radius < 0:
        return []
    if radius == 0:
        return [(col, row)]
    return [t for t in disk(col, row, radius) if distance((col, row), t) == radius]


def _cube_round(x: float, y: float, z: float) -> tuple[int, int, int]:
    rx, ry, rz = round(x), round(y), round(z)
    dx, dy, dz = abs(rx - x), abs(ry - y), abs(rz - z)
    if dx > dy and dx > dz:
        rx = -ry - rz
    elif dy > dz:
        ry = -rx - rz
    else:
        rz = -rx - ry
    return int(rx), int(ry), int(rz)


def line(a: Coord, b: Coord) -> list[Coord]:
    """Tracé de la ligne hex de `a` à `b` (inclus), via lerp cube + arrondi
    (algo Red Blob). Base de la ligne de vue (LoS) : le caller teste si une tile
    intermédiaire bloque. Endpoints inclus, ordonnés de a vers b."""
    n = distance(a, b)
    if n == 0:
        return [a]
    ax, ay, az = to_cube(a[0], a[1])
    bx, by, bz = to_cube(b[0], b[1])
    out: list[Coord] = []
    for i in range(n + 1):
        t = i / n
        cx = ax + (bx - ax) * t
        cy = ay + (by - ay) * t
        cz = az + (bz - az) * t
        rx, _ry, rz = _cube_round(cx, cy, cz)
        out.append(from_cube(rx, rz))
    return out


def _selftest() -> None:
    # 1) chaque voisin est à distance 1 (cols paire ET impaire, + bords).
    for (c, r) in [(0, 0), (1, 0), (4, 4), (5, 3), (2, 7), (3, 0), (6, 9)]:
        for n in neighbors(c, r):
            d = distance((c, r), n)
            assert d == 1, f"neighbor {n} of {(c, r)} dist={d} != 1"
    # 2) disk(R) = 1 + 3R(R+1) tiles (avant clip de bord).
    for R in range(0, 6):
        n = len(set(disk(3, 4, R)))
        assert n == 1 + 3 * R * (R + 1), f"disk R={R} -> {n} != {1 + 3 * R * (R + 1)}"
    # 3) round-trip cube <-> offset.
    for (c, r) in [(0, 0), (1, 5), (6, 2), (7, 9), (4, 0)]:
        x, _y, z = to_cube(c, r)
        assert from_cube(x, z) == (c, r), f"roundtrip {(c, r)}"
    # 4) ring(R) = 6R tiles.
    for R in range(1, 6):
        assert len(ring(3, 4, R)) == 6 * R, f"ring R={R}"
    # 5) symétrie + exemples concrets.
    assert distance((0, 0), (0, 0)) == 0
    assert distance((1, 7), (6, 5)) == distance((6, 5), (1, 7))
    # 6) line: endpoints inclus, longueur dist+1, tiles consécutives = voisines.
    for a, b in [((0, 0), (0, 0)), ((1, 1), (5, 6)), ((6, 2), (0, 8)), ((3, 0), (3, 9))]:
        ln = line(a, b)
        assert ln[0] == a and ln[-1] == b, f"line endpoints {a}->{b}: {ln}"
        assert len(ln) == distance(a, b) + 1, f"line len {a}->{b}: {len(ln)}"
        for i in range(1, len(ln)):
            assert distance(ln[i - 1], ln[i]) == 1, f"line gap {a}->{b} at {i}"
    print("hexgeo selftest OK — voisins@dist1, disk=1+3R(R+1), ring=6R, "
          "cube round-trip, symétrie, line")


if __name__ == "__main__":
    _selftest()
