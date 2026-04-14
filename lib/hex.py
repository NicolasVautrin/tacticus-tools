"""Hex grid math for axial coordinates (offset rows).

Tacticus uses axial coordinates with offset rows (Layout=0).
Column = q, Row = r. Even rows are shifted right.
"""

from __future__ import annotations


def hex_distance(a: tuple[int, int], b: tuple[int, int]) -> int:
    """Manhattan distance between two hex tiles in axial offset coordinates.

    Converts offset coords to cube coords, then uses cube distance.
    """
    ax, ay, az = _offset_to_cube(a[0], a[1])
    bx, by, bz = _offset_to_cube(b[0], b[1])
    return max(abs(ax - bx), abs(ay - by), abs(az - bz))


def hex_neighbors(col: int, row: int) -> list[tuple[int, int]]:
    """Return the 6 hex neighbors of (col, row) in offset coordinates."""
    # Even rows: right-shifted
    if row % 2 == 0:
        directions = [
            (1, 0), (0, -1), (-1, -1),
            (-1, 0), (-1, 1), (0, 1),
        ]
    else:
        directions = [
            (1, 0), (1, -1), (0, -1),
            (-1, 0), (0, 1), (1, 1),
        ]
    return [(col + dc, row + dr) for dc, dr in directions]


def hex_direction(a: tuple[int, int], b: tuple[int, int]) -> tuple[int, int]:
    """Approximate direction vector from a to b (in cube coords, normalized to signs)."""
    ax, ay, az = _offset_to_cube(a[0], a[1])
    bx, by, bz = _offset_to_cube(b[0], b[1])
    return (_sign(bx - ax), _sign(by - ay))


def hex_ring(col: int, row: int, radius: int) -> list[tuple[int, int]]:
    """All tiles at exactly `radius` distance from (col, row)."""
    if radius == 0:
        return [(col, row)]
    results = []
    cx, cy, cz = _offset_to_cube(col, row)
    for x in range(-radius, radius + 1):
        for y in range(max(-radius, -x - radius), min(radius, -x + radius) + 1):
            z = -x - y
            if max(abs(x), abs(y), abs(z)) == radius:
                oc, or_ = _cube_to_offset(cx + x, cy + y, cz + z)
                results.append((oc, or_))
    return results


def tiles_in_range(col: int, row: int, radius: int) -> list[tuple[int, int]]:
    """All tiles within `radius` distance of (col, row), including center."""
    results = []
    cx, cy, cz = _offset_to_cube(col, row)
    for x in range(-radius, radius + 1):
        for y in range(max(-radius, -x - radius), min(radius, -x + radius) + 1):
            z = -x - y
            oc, or_ = _cube_to_offset(cx + x, cy + y, cz + z)
            results.append((oc, or_))
    return results


# -- Internal: offset <-> cube conversion --

def _offset_to_cube(col: int, row: int) -> tuple[int, int, int]:
    """Offset (even-r) to cube coordinates."""
    x = col - (row + (row & 1)) // 2
    z = row
    y = -x - z
    return x, y, z


def _cube_to_offset(x: int, y: int, z: int) -> tuple[int, int]:
    """Cube to offset (even-r) coordinates."""
    col = x + (z + (z & 1)) // 2
    row = z
    return col, row


def _sign(n: int) -> int:
    return (n > 0) - (n < 0)
