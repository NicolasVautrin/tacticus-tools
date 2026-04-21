// Pure hex math — no DOM, no state. Flat-top odd-q offset coordinates
// (rotated 30° from pointy-top). Vertices are left/right; flat edges top
// and bottom. All coords are in PNG pixel space; the SVG is sized to match
// the image via viewBox.
//
//   hexWidth  = 2       * size    (horizontal corner-to-corner)
//   hexHeight = sqrt(3) * size    (vertical flat-to-flat)
//   colHoriz  = 1.5     * size    (horizontal center-to-center between cols)

export const SQRT3 = Math.sqrt(3);

export function hexLayout(visual, imgW, imgH) {
    // The visual MonoBehaviour's Width × Height describes the FULL grid baked
    // into the PNG (ex: 13 × 14 for a 7 × 9 playable board — 3 cols padding
    // left/right, 2 top / 3 bottom). We fit that visual grid into the PNG, so
    // tiles land exactly where the background was rendered.
    const W = visual.Width, H = visual.Height;
    const sizeW = imgW / (W * 1.5 + 0.5);
    const sizeH = imgH / ((H + 0.5) * SQRT3);
    const size = Math.min(sizeW, sizeH);
    const hexH = SQRT3 * size;
    const colH = 1.5 * size;
    const gridW = (W * 1.5 + 0.5) * size;
    const gridH = (H + 0.5) * hexH;
    return {
        size, hexH, colH, H,
        // Center the grid within the PNG; first hex center is offset by its
        // own half-dimensions. Empirical: the baked grid sits half a hex
        // west of the math-centered position.
        originX: (imgW - gridW) / 2,
        originY: (imgH - gridH) / 2 + hexH / 2,
    };
}

export function tileCenter(layout, col, row) {
    // Y-flip: game row 0 → visual bottom. Logical even cols shifted up by
    // one hex-half to match the staggered pattern baked into the PNG.
    const visualRow = (layout.H - 1) - row;
    const offset = (col % 2 === 1) ? -layout.hexH / 2 : 0;
    return [
        layout.originX + col * layout.colH,
        layout.originY + visualRow * layout.hexH + offset,
    ];
}

export function hexPolygon(cx, cy, size) {
    // Flat-top: vertex at right, offsets 0/60/120/180/240/300 degrees.
    const pts = [];
    for (let i = 0; i < 6; i++) {
        const a = Math.PI / 180 * (60 * i);
        pts.push((cx + size * Math.cos(a)) + "," + (cy + size * Math.sin(a)));
    }
    return pts.join(" ");
}
