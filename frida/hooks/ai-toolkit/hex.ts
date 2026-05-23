// Hex grid distance — same axial-coordinate formula Tacticus uses internally
// (PositionComponent.Distance). Two tiles at (col, row) coordinates have:
//   dist = (|c1-c2| + |c1+r1 - c2-r2| + |r1-r2|) / 2
//
// Pure, no IL2CPP dependency. Generic for any AI fix reasoning over the
// battle grid (range checks, threat zones, danger zones, line-of-sight
// approximations, etc.).

export function hexDistance(
    c1: number, r1: number, c2: number, r2: number,
): number {
    return (Math.abs(c1 - c2)
        + Math.abs(c1 + r1 - c2 - r2)
        + Math.abs(r1 - r2)) / 2;
}
