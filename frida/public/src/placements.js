// User placements (pre-launch) — deploy, move, remove, render list +
// SVG portrait placement. Each mutation persists to localStorage and
// triggers a re-render of the board overlay.

import { state, savePlacements } from "./state.js";
import { $, status } from "./dom.js";
import { tileCenter } from "./hex.js";
import { configIdToPortrait } from "./images.js";
import { renderOverlay } from "./board.js";

export function deployUnitAt(unitId, col, row) {
    const sp = state.spawnPointsByTile.get(col + "," + row);
    if (!sp) { status("(" + col + "," + row + ") is not a spawn point"); return; }
    state.placements = state.placements.filter(
        (p) => !(p.col === col && p.row === row));
    state.placements.push({
        unitId, playerId: sp.playerId ?? sp.team, col, row,
    });
    savePlacements();
    renderOverlay();
    renderPlacements();
    status("deployed " + unitId + " at (" + col + "," + row + ")");
}

export function moveUnitTo(fromCol, fromRow, toCol, toRow) {
    if (fromCol === toCol && fromRow === toRow) return;
    const p = state.placements.find(
        (x) => x.col === fromCol && x.row === fromRow);
    if (!p) return;
    state.placements = state.placements.filter(
        (x) => !(x.col === toCol && x.row === toRow));
    p.col = toCol; p.row = toRow;
    savePlacements();
    renderOverlay();
    renderPlacements();
    status("moved " + p.unitId + " → (" + toCol + "," + toRow + ")");
}

export function removePlacement(p) {
    state.placements = state.placements.filter((x) => x !== p);
    savePlacements();
    renderOverlay();
    renderPlacements();
    status("removed " + p.unitId);
}

// Render a placement portrait as an SVG <foreignObject> so native HTML drag
// works on the inner <img>.
export function placeUnitImage(svg, layout, p, minC, minR, elevation = 0) {
    const [cx, cy] = tileCenter(layout, p.col + minC, p.row + minR, elevation);
    const portraitKey = configIdToPortrait(p.unitId);
    const pngPath = portraitKey ? state.manifest.units[portraitKey] : null;
    if (!pngPath) return;
    const w = layout.size * 1.5;
    const fo = document.createElementNS(
        "http://www.w3.org/2000/svg", "foreignObject");
    fo.setAttribute("x", cx - w / 2);
    fo.setAttribute("y", cy - w / 2);
    fo.setAttribute("width", w);
    fo.setAttribute("height", w);
    fo.classList.add("unit-fo");
    fo.classList.add("unit-fo--placement");
    const img = document.createElement("img");
    img.src = "/assets/" + pngPath;
    img.draggable = true;
    img.dataset.col = p.col;
    img.dataset.row = p.row;
    img.addEventListener("dragstart", (ev) => {
        ev.dataTransfer.setData("text/plain", JSON.stringify({
            kind: "move", col: p.col, row: p.row,
        }));
        ev.dataTransfer.effectAllowed = "move";
    });
    fo.appendChild(img);
    svg.appendChild(fo);
}

export function renderPlacements() {
    const ol = $("placements-list");
    if (!ol) return;
    ol.innerHTML = "";
    if (state.placements.length === 0) {
        const li = document.createElement("li");
        li.className = "placements__empty";
        li.textContent = "∅ no units queued";
        ol.appendChild(li);
        return;
    }
    for (let i = 0; i < state.placements.length; i++) {
        const p = state.placements[i];
        const li = document.createElement("li");
        li.className = "placement-row";
        const idx = String(i + 1).padStart(2, "0");
        li.innerHTML =
            '<span class="placement-row__idx">[' + idx + ']</span>'
          + '<span class="placement-row__name">' + p.unitId + '</span>'
          + '<span class="placement-row__coord">'
          + p.col + '·' + p.row + '</span>'
          + '<button class="placement-row__remove" title="remove">×</button>';
        li.querySelector(".placement-row__remove")
          .addEventListener("click", () => {
            state.placements = state.placements.filter((x) => x !== p);
            savePlacements();
            renderOverlay();
            renderPlacements();
        });
        ol.appendChild(li);
    }
}
