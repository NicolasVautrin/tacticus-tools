// Drag-and-drop wiring for board tiles.
// Each hex polygon accepts drops of two kinds:
//   - {kind: "deploy", unitId}  — from the roster, spawn tiles only
//   - {kind: "move", col, row}  — from an existing placement, any tile
// Click-to-remove on tiles that already hold a placement.

import { state } from "./state.js";
import { status } from "./dom.js";
import { deployUnitAt, moveUnitTo, removePlacement } from "./placements.js";

export function attachTileDnd(poly, col, row) {
    const isSpawn = state.spawnPointsByTile.has(col + "," + row);
    const hasPlacement = () =>
        state.placements.some((p) => p.col === col && p.row === row);

    poly.addEventListener("dragenter", (ev) => {
        ev.preventDefault();
        if (isSpawn) poly.classList.add("drop-hover");
        else poly.classList.add("drop-hover-maybe");
    });
    poly.addEventListener("dragover", (ev) => { ev.preventDefault(); });
    poly.addEventListener("dragleave", () => {
        poly.classList.remove("drop-hover", "drop-hover-maybe");
    });
    poly.addEventListener("drop", (ev) => {
        ev.preventDefault();
        ev.stopPropagation();
        poly.classList.remove("drop-hover", "drop-hover-maybe");
        let data;
        try { data = JSON.parse(ev.dataTransfer.getData("text/plain")); }
        catch (e) { console.warn("drop: bad payload", e); return; }
        if (data.kind === "deploy") {
            if (!isSpawn) {
                status("(" + col + "," + row + ") is not a deployment zone");
                return;
            }
            deployUnitAt(data.unitId, col, row);
        } else if (data.kind === "move") {
            moveUnitTo(data.col, data.row, col, row);
        }
    });
    poly.addEventListener("click", () => {
        if (hasPlacement()) {
            const p = state.placements.find(
                (x) => x.col === col && x.row === row);
            if (p) removePlacement(p);
        }
    });
}
