// Board rendering — load the PNG background + metadata + build the SVG
// hex overlay. All visual state lives in `state.*`, so callers just invoke
// `renderOverlay()` after mutations.

import { state } from "./state.js";
import { $, status } from "./dom.js";
import { hexLayout, tileCenter, hexPolygon } from "./hex.js";
import { configIdToPortrait, rankImageUrl } from "./images.js";
import { attachTileDnd } from "./dnd.js";
import { placeUnitImage } from "./placements.js";
import { getCalibration, syncPanelToCurrentBoard } from "./hex-calibration.js";

export function loadBoard() {
    const boardId = state.config?.Board?.Id?.toLowerCase();
    if (!boardId) { status("config has no Board.Id"); return; }

    state.boardVisual = state.manifest.boardVisuals[boardId] ?? null;
    const pngPath = state.manifest.boards[boardId];
    if (!pngPath) { status("no PNG for board " + boardId); return; }

    const img = $("board-bg");
    img.onload = () => {
        renderOverlay();
        // Refresh the calibration panel with this board's saved overrides
        // (or recomputed defaults) once the PNG is sized.
        syncPanelToCurrentBoard();
    };
    img.src = "/assets/" + pngPath;

    const meta = ["BOARD " + boardId.toUpperCase()];
    if (state.boardVisual) {
        meta.push(
            "DIM " + state.boardVisual.Width + "×" + state.boardVisual.Height);
        meta.push(
            "PLAY ["
            + state.boardVisual.PlayableMinCol + "-"
            + state.boardVisual.PlayableMaxCol + "] × ["
            + state.boardVisual.PlayableMinRow + "-"
            + state.boardVisual.PlayableMaxRow + "]");
    }
    $("board-meta").textContent = meta.join("  ·  ");

    state.spawnPointsByTile.clear();
    const setIdx = state.config.SpawnPointSetIndex ?? 0;
    const set = state.config.Board?.SpawnPointSets?.[setIdx];
    if (!set) return;

    // SpawnPointGroup.TeamWithPlayerIndex is an enum, NOT a raw TeamId.
    // Validated against native TeamPlayerIdExtensions.Unfold():
    //   0 → (team=1, playerIdx=0)    1 → (team=2, playerIdx=0)
    //   2 → (team=1, playerIdx=1)    3 → (team=2, playerIdx=1)
    //   4 → (team=3, playerIdx=0)    5 → (team=3, playerIdx=1)
    //   6 → (team=0, playerIdx=0)
    // playerIdx is 0-based despite the enum names saying "Player1" etc.
    const TWPI = {
        0: { teamId: 1, playerIdx: 0 },
        1: { teamId: 2, playerIdx: 0 },
        2: { teamId: 1, playerIdx: 1 },
        3: { teamId: 2, playerIdx: 1 },
        4: { teamId: 3, playerIdx: 0 },
        5: { teamId: 3, playerIdx: 1 },
        6: { teamId: 0, playerIdx: 0 },
    };

    const playersByTeam = new Map();
    const players = state.config.Player?.Players ?? {};
    for (const [pid, p] of Object.entries(players)) {
        const tid = p.TeamId ?? 0;
        if (!playersByTeam.has(tid)) playersByTeam.set(tid, []);
        playersByTeam.get(tid).push(Number(pid));
    }

    for (const group of set.SpawnPointGroups ?? []) {
        const twpiRaw = typeof group.TeamWithPlayerIndex === "number"
            ? group.TeamWithPlayerIndex
            : (group.TeamWithPlayerIndex?.value ?? 0);
        const dec = TWPI[twpiRaw] ?? { teamId: twpiRaw, playerIdx: 0 };
        const teamPlayers = playersByTeam.get(dec.teamId) ?? [];
        const playerId = teamPlayers[dec.playerIdx] ?? null;
        if (playerId == null) continue;
        for (const sp of group.SpawnPoints ?? []) {
            state.spawnPointsByTile.set(sp.Column + "," + sp.Row,
                { team: dec.teamId, playerId });
        }
    }
}

export function renderOverlay() {
    const svg = $("board-overlay");
    const img = $("board-bg");
    if (!svg || !img) return;
    const W = img.naturalWidth, H = img.naturalHeight;
    svg.setAttribute("viewBox", "0 0 " + W + " " + H);
    svg.setAttribute("preserveAspectRatio", "none");
    svg.innerHTML = "";

    const visual = state.boardVisual;
    if (!visual) return;

    const boardId = state.config?.Board?.Id?.toLowerCase();
    const override = boardId ? getCalibration(boardId) : null;
    const layout = hexLayout(visual, W, H, override);
    const { PlayableMinCol: minC, PlayableMinRow: minR } = visual;
    const logicalW = state.config.Board.Width;
    const logicalH = state.config.Board.Height;

    // Tile elevation lookup: Board.Tiles[col].Tile[row].Elevation. Falls
    // back to 0 when the tile slot is missing or the structure differs
    // (older captures).
    const tilesCols = state.config.Board.Tiles ?? [];
    const elevAt = (lc, lr) => {
        const col = tilesCols[lc];
        const inner = Array.isArray(col?.Tile) ? col.Tile : null;
        const t = inner ? inner[lr] : null;
        return Number.isFinite(t?.Elevation) ? t.Elevation : 0;
    };

    // Tiles layer — each hex drawn at its own (col, row, elevation) so
    // raised platforms align with the perspective baked into the PNG.
    // Iterate rows BACK-TO-FRONT (top of image → bottom) so the painter's
    // algorithm lets closer tiles occlude the parts of higher-elevation
    // tiles that bleed into their row.
    for (let lr = logicalH - 1; lr >= 0; lr--) {
        for (let lc = 0; lc < logicalW; lc++) {
            const elev = elevAt(lc, lr);
            const [cx, cy] = tileCenter(layout, lc + minC, lr + minR, elev);
            const poly = document.createElementNS(
                "http://www.w3.org/2000/svg", "polygon");
            poly.setAttribute("points",
                hexPolygon(cx, cy, {
                    Rx: layout.Rx * 0.92,
                    Ry: layout.Ry * 0.92,
                }));
            poly.classList.add("hex");
            if (elev > 0) poly.classList.add("hex--elev-" + elev);
            const sp = state.spawnPointsByTile.get(lc + "," + lr);
            if (sp) poly.classList.add("spawn", "team-" + sp.team);
            poly.dataset.col = lc;
            poly.dataset.row = lr;
            poly.dataset.elev = String(elev);
            const title = document.createElementNS(
                "http://www.w3.org/2000/svg", "title");
            title.textContent = "(" + lc + ", " + lr + ") elev " + elev;
            poly.appendChild(title);
            poly.addEventListener("mouseenter", () => {
                const lbl = $("hex-coord");
                if (lbl) lbl.textContent =
                    "COL " + String(lc).padStart(2, "0")
                  + "  ROW " + String(lr).padStart(2, "0")
                  + "  E " + elev;
            });
            attachTileDnd(poly, lc, lr);
            svg.appendChild(poly);
        }
    }

    // Mirror mode wins over both pre-launch placements and live event
    // units: the front renders ONLY the mirror state when one exists.
    const playerTeams = new Map();
    for (const [pid, p] of Object.entries(state.config?.Player?.Players ?? {})) {
        playerTeams.set(Number(pid), p.TeamId ?? 0);
    }
    if (state.simState?.units?.length) {
        for (const u of state.simState.units) {
            if (!u.pos || u.isDead) continue;
            // Mirror coords are 0-based-relative to the Tiles array (same
            // convention as state.eventUnits) — convert to absolute by
            // adding minC/minR before passing to tileCenter.
            const [cx, cy] = tileCenter(layout,
                u.pos.col + minC, u.pos.row + minR,
                elevAt(u.pos.col, u.pos.row));
            const ringCls = u.teamId === 1 ? "ring-team-1"
                         : u.teamId === 2 ? "ring-team-2"
                         : "ring-team-n";
            // visualId comes from the projection (squad's UnitComponent),
            // no live state dependency.
            const portraitKey = u.visualId ? configIdToPortrait(u.visualId)
                : null;
            const pngPath = portraitKey ? state.manifest?.units?.[portraitKey]
                : null;
            const g = document.createElementNS(
                "http://www.w3.org/2000/svg", "g");
            g.classList.add("event-unit");
            if (pngPath) {
                const r = layout.size * 0.6;
                const ring = document.createElementNS(
                    "http://www.w3.org/2000/svg", "circle");
                ring.setAttribute("cx", cx);
                ring.setAttribute("cy", cy);
                ring.setAttribute("r", r);
                ring.classList.add("unit-ring", ringCls);
                g.appendChild(ring);
                const fo = document.createElementNS(
                    "http://www.w3.org/2000/svg", "foreignObject");
                const w = r * 1.8;
                fo.setAttribute("x", cx - w / 2);
                fo.setAttribute("y", cy - w / 2);
                fo.setAttribute("width", w);
                fo.setAttribute("height", w);
                fo.classList.add("unit-fo");
                const imgEl = document.createElement("img");
                imgEl.src = "/assets/" + pngPath;
                imgEl.style.pointerEvents = "none";
                fo.appendChild(imgEl);
                g.appendChild(fo);
                const rankUrl = u.rank ? rankImageUrl(u.rank) : null;
                if (rankUrl) {
                    const minR = Math.min(layout.Rx, layout.Ry);
                    const badgeSize = minR * 0.825;
                    const badge = document.createElementNS(
                        "http://www.w3.org/2000/svg", "image");
                    badge.setAttributeNS(
                        "http://www.w3.org/1999/xlink", "href", rankUrl);
                    badge.setAttribute("href", rankUrl);
                    badge.setAttribute("x", cx - layout.Rx * 0.75);
                    badge.setAttribute("y", cy + layout.Ry * 0.20);
                    badge.setAttribute("width", badgeSize);
                    badge.setAttribute("height", badgeSize);
                    badge.classList.add("unit-rank-badge");
                    g.appendChild(badge);
                }
            } else {
                const r = layout.size * 0.55;
                const ring = document.createElementNS(
                    "http://www.w3.org/2000/svg", "circle");
                ring.setAttribute("cx", cx);
                ring.setAttribute("cy", cy);
                ring.setAttribute("r", r);
                ring.classList.add("unit-fallback", ringCls);
                g.appendChild(ring);
            }
            svg.appendChild(g);
        }
        return;
    }

    // Pre-launch placements — only in DEPLOY mode (no runner active).
    if (!state.runnerId) {
        for (const p of state.placements) {
            placeUnitImage(svg, layout, p, minC, minR, elevAt(p.col, p.row));
        }
    }

    // Live units from battle_event StreamEvents.
    for (const [entity, u] of state.eventUnits) {
        const [cx, cy] = tileCenter(layout, u.col + minC, u.row + minR,
            elevAt(u.col, u.row));
        const team = playerTeams.get(u.playerId);
        const ringCls = team === 1 ? "ring-team-1"
                     : team === 2 ? "ring-team-2" : "ring-team-n";
        const portraitKey = u.visualId ? configIdToPortrait(u.visualId) : null;
        const pngPath = portraitKey ? state.manifest.units[portraitKey] : null;
        const g = document.createElementNS("http://www.w3.org/2000/svg", "g");
        g.classList.add("event-unit");
        if (pngPath) {
            const r = layout.size * 0.6;
            const ring = document.createElementNS(
                "http://www.w3.org/2000/svg", "circle");
            ring.setAttribute("cx", cx);
            ring.setAttribute("cy", cy);
            ring.setAttribute("r", r);
            ring.classList.add("unit-ring");
            ring.classList.add(ringCls);
            g.appendChild(ring);
            const fo = document.createElementNS(
                "http://www.w3.org/2000/svg", "foreignObject");
            const w = r * 1.8;
            fo.setAttribute("x", cx - w / 2);
            fo.setAttribute("y", cy - w / 2);
            fo.setAttribute("width", w);
            fo.setAttribute("height", w);
            fo.classList.add("unit-fo");
            const imgEl = document.createElement("img");
            imgEl.src = "/assets/" + pngPath;
            imgEl.style.pointerEvents = "none";
            fo.appendChild(imgEl);
            g.appendChild(fo);

            const rankUrl = rankImageUrl(u.rank);
            if (rankUrl) {
                const minR = Math.min(layout.Rx, layout.Ry);
                const badgeSize = minR * 0.825;
                const badge = document.createElementNS(
                    "http://www.w3.org/2000/svg", "image");
                badge.setAttributeNS(
                    "http://www.w3.org/1999/xlink", "href", rankUrl);
                badge.setAttribute("href", rankUrl);
                badge.setAttribute("x", cx - layout.Rx * 0.75);
                badge.setAttribute("y", cy + layout.Ry * 0.20);
                badge.setAttribute("width", badgeSize);
                badge.setAttribute("height", badgeSize);
                badge.classList.add("unit-rank-badge");
                g.appendChild(badge);
            }
        } else {
            const circle = document.createElementNS(
                "http://www.w3.org/2000/svg", "circle");
            circle.setAttribute("cx", cx);
            circle.setAttribute("cy", cy);
            circle.setAttribute("r", layout.size * 0.55);
            circle.classList.add("unit-fallback", ringCls);
            const text = document.createElementNS(
                "http://www.w3.org/2000/svg", "text");
            text.setAttribute("x", cx);
            text.setAttribute("y", cy + 5);
            text.setAttribute("text-anchor", "middle");
            text.setAttribute("font-size", layout.size * 0.55);
            text.classList.add("unit-fallback-label");
            text.textContent = String(entity);
            g.appendChild(circle);
            g.appendChild(text);
        }
        svg.appendChild(g);
    }
}
