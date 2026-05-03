// Per-tile hex math, NOT a uniform grid. Pulled directly from the game
// engine — `Idun.Source.IdunBattle.Logic.Utils.Hex.HexUtils.GetTileWorldPosition`:
//
//   world.x = col * 3.0
//   world.y = elevation                              ← lifts the tile up
//   world.z = row * 2*sqrt(3) + (col odd ? sqrt(3) : 0)
//
// The PNG render is an orthographic projection of that world tilted by an
// angle θ around the X axis (slight perspective baked into the asset).
// Projecting (x, y, z) at world scale `scale` (px / world unit) gives:
//
//   pixelX = originX + col * (1.5 * cellSizeX)
//   pixelY = originY + visualRow * (sqrt(3) * cellSizeY)
//          + (col odd ? sign * sqrt(3) * cellSizeY / 2 : 0)
//          + elevation * elevLiftPx
//
// where `elevLiftPx = scale * sin(θ)` and `cos(θ) = cellSizeY / cellSizeX`
// (so the tilt is fully encoded by the X/Y cell-size ratio — no extra
// per-elevation calibration needed).

export const SQRT3 = Math.sqrt(3);

// Hand-tuned calibrations from real boards, keyed by `H × pMinC-pMaxC ×
// pMinR-pMaxR` (board "shape signature"). The PNG render uses a constant
// camera tilt; only the ortho zoom may vary by shape, so cellSizeX/Y
// might or might not differ between sizes — TBD as more shapes get
// calibrated. Each entry holds the FULL absolute values the user dialed
// in, so any board with the same shape gets identical defaults without
// re-derivation.
const SHAPE_CALIBRATIONS = {
    // c1_01 / c1_06 / c1_t_07 / etc. — Tacticus 1.38.94 (avg of 2 calibs
    // 2026-05-03). Per-board residual ±20 px on origin: each art asset
    // has its own small offset; for pixel-perfect on a specific board,
    // calibrate it individually (per-boardId override wins).
    "12|3-7|2-8": {
        cellSize: 111.29,   // avg(111.79, 110.79)
        cellSizeY: 101.65,  // avg(101.7,  101.6)
        originX: 183,       // avg(173, 193)
        originY: 71,        // avg(78,  65)
        oddOffsetSign: -1,
    },
    // 13×14 — c1_03 + c1_13 (avg of 2 calibs 2026-05-03). cellSizeY was
    // pixel-identical between samples → camera tilt truly constant.
    "14|3-9|2-10": {
        cellSize: 103.44,   // avg(103.79, 103.09)
        cellSizeY: 90.73,   // identical
        originX: 95,        // avg(88, 102)
        originY: 78,        // avg(79, 77)
        oddOffsetSign: -1,
    },
    // 13×15 — c1_09 (1 calib 2026-05-03).
    "15|3-9|2-11": {
        cellSize: 91.09,
        cellSizeY: 83.03,
        originX: 202,
        originY: 47,
        oddOffsetSign: -1,
    },
};
// Average tilt cosine across known calibrations — used as the fallback
// when no shape match is found, so we can still render a sensible grid.
const FALLBACK_TILT_COS = 0.910;
const FALLBACK_CELL_X_BY_HEIGHT = {
    12: 111.29,
    14: 103.44,
    15: 91.09,
};

function shapeKey(visual) {
    return `${visual.Height}|${visual.PlayableMinCol}-${visual.PlayableMaxCol}`
        + `|${visual.PlayableMinRow}-${visual.PlayableMaxRow}`;
}

/** Engine-aligned defaults. Tries an exact shape match first (gives the
 *  exact dialed-in values). Falls back to "anchor playable center at PNG
 *  center" with a per-height cellSize. Used both by hexLayout's
 *  no-override branch AND by the calibration panel's RESET target. */
export function computeEngineDefaults(visual, imgW, imgH) {
    const exact = SHAPE_CALIBRATIONS[shapeKey(visual)];
    if (exact) return { ...exact };

    const cellSizeX = FALLBACK_CELL_X_BY_HEIGHT[visual.Height] ?? 95;
    const cellSizeY = cellSizeX * FALLBACK_TILT_COS;
    const colH = 1.5 * cellSizeX;
    const hexH = SQRT3 * cellSizeY;
    const playableCenterCol = (visual.PlayableMinCol + visual.PlayableMaxCol) / 2;
    const playableCenterRow = (visual.PlayableMinRow + visual.PlayableMaxRow) / 2;
    const visualCenterRow = (visual.Height - 1) - playableCenterRow;
    const oddSign = -1;
    const parityFrac = ((playableCenterCol % 2) + 2) % 2;
    const parityOffset = oddSign * hexH / 2 * Math.min(1, parityFrac);
    return {
        cellSize: cellSizeX,
        cellSizeY,
        originX: imgW / 2 - playableCenterCol * colH,
        originY: imgH / 2 - visualCenterRow * hexH - parityOffset,
        oddOffsetSign: oddSign,
    };
}

/** Build a layout. If `override` is provided (from the calibration panel)
 *  it wins outright. Otherwise we use `computeEngineDefaults` so even
 *  uncalibrated boards render with the engine-aligned formula. */
export function hexLayout(visual, imgW, imgH, override = null) {
    const cal = override
        && Number.isFinite(override.cellSize)
        && Number.isFinite(override.originX)
        && Number.isFinite(override.originY)
        ? override
        : computeEngineDefaults(visual, imgW, imgH);
    const Rx = cal.cellSize;
    const Ry = Number.isFinite(cal.cellSizeY) ? cal.cellSizeY : Rx;
    return finalize(Rx, Ry, cal.originX, cal.originY,
        cal.oddOffsetSign === 0 ? 0
        : (cal.oddOffsetSign === 1 ? 1 : -1),
        visual.Height);
}

function finalize(Rx, Ry, originX, originY, oddOffsetSign, H) {
    const hexH = SQRT3 * Ry;
    const colH = 1.5 * Rx;
    // Recover the camera tilt from the X/Y size ratio: cos(θ) = Ry / Rx.
    // World scale (px per world unit) = colH / 3 = Rx / 2. Vertical lift
    // per elevation step = scale * sin(θ).
    const ratio = Math.min(1, Ry / Rx);
    const sinTheta = Math.sqrt(Math.max(0, 1 - ratio * ratio));
    const elevLiftPx = (Rx / 2) * sinTheta;
    return {
        Rx, Ry, size: Rx, hexH, colH, H, originX, originY,
        oddOffsetSign, elevLiftPx,
    };
}

/** Pixel center of one tile. `elevation` shifts the tile UP in image space
 *  (smaller pixel-Y) by `elevation * elevLiftPx`. */
export function tileCenter(layout, col, row, elevation = 0) {
    const visualRow = (layout.H - 1) - row;
    const sign = (layout.oddOffsetSign ?? -1);
    const oddOffset = (col % 2 === 1) ? sign * layout.hexH / 2 : 0;
    const elev = Number.isFinite(elevation) ? elevation : 0;
    return [
        layout.originX + col * layout.colH,
        layout.originY + visualRow * layout.hexH + oddOffset
            - elev * (layout.elevLiftPx ?? 0),
    ];
}

/** Flat-top hex polygon. `Rx`/`Ry` allow non-regular shapes; falls back to
 *  legacy single-`size` callers. */
export function hexPolygon(cx, cy, sizeOrLayout) {
    const Rx = (typeof sizeOrLayout === "object")
        ? (sizeOrLayout.Rx ?? sizeOrLayout.size)
        : sizeOrLayout;
    const Ry = (typeof sizeOrLayout === "object")
        ? (sizeOrLayout.Ry ?? sizeOrLayout.size)
        : sizeOrLayout;
    const pts = [];
    for (let i = 0; i < 6; i++) {
        const a = Math.PI / 180 * (60 * i);
        pts.push((cx + Rx * Math.cos(a)) + "," + (cy + Ry * Math.sin(a)));
    }
    return pts.join(" ");
}
