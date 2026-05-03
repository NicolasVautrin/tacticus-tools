// Live hex-grid calibration panel.
//
// One calibration per board (cellSize X/Y, originX/Y, oddOffsetSign). The
// per-elevation Y shift falls out of the X/Y ratio (cosine of the camera
// tilt) — see hex.js — so we don't store it; just render each tile at its
// own (col, row, tile.Elevation).
//
// Per-board overrides live in `state.calibrations[boardId]` (keyed
// lowercase). Persisted to localStorage so reloads keep the in-progress
// tuning.

import { state } from "./state.js";
import { $ } from "./dom.js";
import { computeEngineDefaults } from "./hex.js";

const LS_KEY = "tacticus.hexCalibrations.v3";
const LEGACY_KEYS = ["tacticus.hexCalibrations.v2", "tacticus.hexCalibrations.v1"];

function loadFromStorage() {
    try {
        const raw = JSON.parse(localStorage.getItem(LS_KEY) ?? "null");
        if (raw && typeof raw === "object") return raw;
    } catch { /* fall through */ }
    // Migrate from older shapes if present, then upgrade the storage key.
    for (const k of LEGACY_KEYS) {
        try {
            const old = JSON.parse(localStorage.getItem(k) ?? "null");
            if (!old || typeof old !== "object") continue;
            const out = {};
            for (const [boardId, entry] of Object.entries(old)) {
                // v2 had { byElevation: { "0": cal, ... } } — keep elev 0 only.
                if (entry?.byElevation?.["0"]) out[boardId] = entry.byElevation["0"];
                // v1 was a flat cal directly.
                else if (entry?.cellSize !== undefined) out[boardId] = entry;
            }
            return out;
        } catch { /* keep trying */ }
    }
    return {};
}

function persistToStorage() {
    try { localStorage.setItem(LS_KEY, JSON.stringify(state.calibrations)); }
    catch (e) { console.warn("[hex-cal] persist failed", e); }
}

state.calibrations = loadFromStorage();

let renderOverlayFn = null;

function currentBoardId() {
    return state.config?.Board?.Id?.toLowerCase() ?? null;
}

function defaultsFor(boardId) {
    // Engine-aligned defaults — same path as hex.js's no-override branch.
    // Pre-fills the panel after a RESET so the user lands on values that
    // already match the engine projection (just refine from there).
    const v = state.boardVisual;
    const img = $("board-bg");
    if (!v || !img || !img.naturalWidth) return null;
    return computeEngineDefaults(v, img.naturalWidth, img.naturalHeight);
}

export function getCalibration(boardId) {
    if (!boardId) return null;
    return state.calibrations[boardId.toLowerCase()] ?? null;
}

function setCalibration(boardId, cal) {
    state.calibrations[boardId.toLowerCase()] = cal;
    persistToStorage();
}

function clearCalibration(boardId) {
    delete state.calibrations[boardId.toLowerCase()];
    persistToStorage();
}

function readPanel() {
    const cellSize = parseFloat($("hexcal-size").value);
    const cellSizeY = parseFloat($("hexcal-sizey").value);
    const originX = parseFloat($("hexcal-x").value);
    const originY = parseFloat($("hexcal-y").value);
    const oddOffsetSign = parseInt($("hexcal-odd").value, 10);
    return {
        cellSize,
        cellSizeY: Number.isFinite(cellSizeY) ? cellSizeY : cellSize,
        originX, originY, oddOffsetSign,
    };
}

function writePanel(cal) {
    const setVal = (id, v, decimals = 2) => {
        const inp = $(id);
        if (inp) inp.value = Number(v).toFixed(decimals);
    };
    setVal("hexcal-size", cal.cellSize, 2);
    setVal("hexcal-sizey", cal.cellSizeY ?? cal.cellSize, 2);
    setVal("hexcal-x", cal.originX, 0);
    setVal("hexcal-y", cal.originY, 0);
    const odd = $("hexcal-odd");
    if (odd) odd.value = String(cal.oddOffsetSign);
    refreshDerived();
}

/** Show the camera-tilt + elevation-lift derived from cellSize X/Y so the
 *  user can sanity-check the geometry is sensible. */
function refreshDerived() {
    const out = $("hexcal-derived");
    if (!out) return;
    const Rx = parseFloat($("hexcal-size").value);
    const Ry = parseFloat($("hexcal-sizey").value);
    if (!Number.isFinite(Rx) || !Number.isFinite(Ry) || Rx <= 0) {
        out.textContent = "—";
        return;
    }
    const ratio = Math.min(1, Ry / Rx);
    const sinT = Math.sqrt(Math.max(0, 1 - ratio * ratio));
    const thetaDeg = Math.acos(ratio) * 180 / Math.PI;
    const elevLift = (Rx / 2) * sinT;
    out.textContent =
        `tilt ${thetaDeg.toFixed(1)}°  ·  elev lift ${elevLift.toFixed(1)} px/lvl`;
}

function applyAndRender() {
    const boardId = currentBoardId();
    if (!boardId) return;
    setCalibration(boardId, readPanel());
    refreshDerived();
    if (typeof renderOverlayFn === "function") renderOverlayFn();
}

function attachInputBinding(inputId, decimals) {
    const inp = $(inputId);
    if (!inp) return;
    inp.addEventListener("input", () => {
        const v = parseFloat(inp.value);
        if (Number.isFinite(v)) applyAndRender();
    });
    const row = document.querySelector(`.hexcal-row[data-target="${inputId}"]`);
    if (!row) return;
    for (const btn of row.querySelectorAll(".hexcal-step")) {
        btn.addEventListener("click", () => {
            const delta = parseFloat(btn.dataset.delta);
            if (!Number.isFinite(delta)) return;
            const cur = parseFloat(inp.value) || 0;
            inp.value = (cur + delta).toFixed(decimals);
            applyAndRender();
        });
    }
}

function logCalibration() {
    const boardId = currentBoardId();
    if (!boardId) {
        console.warn("[hex-cal] no board loaded");
        return;
    }
    const v = state.boardVisual ?? {};
    const img = $("board-bg");
    const cal = readPanel();
    setCalibration(boardId, cal);
    const pngRel = state.manifest?.boards?.[boardId] ?? null;
    // Same derived metrics shown in the panel — useful for the assistant
    // to sanity-check the geometry across boards.
    const Rx = cal.cellSize, Ry = cal.cellSizeY ?? cal.cellSize;
    const ratio = Math.min(1, Ry / Rx);
    const sinT = Math.sqrt(Math.max(0, 1 - ratio * ratio));
    const dump = {
        boardId,
        visual: {
            Width: v.Width, Height: v.Height,
            PlayableMinCol: v.PlayableMinCol, PlayableMaxCol: v.PlayableMaxCol,
            PlayableMinRow: v.PlayableMinRow, PlayableMaxRow: v.PlayableMaxRow,
        },
        png: {
            w: img?.naturalWidth ?? null,
            h: img?.naturalHeight ?? null,
            relPath: pngRel,
            absPath: pngRel
                ? "C:/Users/nicolasv/tacticus-tools/frida/assets/public/" + pngRel
                : null,
        },
        calibration: cal,
        derived: {
            tiltDeg: Math.acos(ratio) * 180 / Math.PI,
            elevLiftPx: (Rx / 2) * sinT,
            scale: Rx / 2,
        },
    };
    const text = JSON.stringify(dump, null, 2);
    console.log("[HEX-CAL]\n" + text);
    const out = $("hexcal-output");
    if (out) {
        out.value = text;
        out.classList.remove("hidden");
        try { out.select(); } catch { /* noop */ }
    }
}

function resetCalibration() {
    const boardId = currentBoardId();
    if (!boardId) return;
    clearCalibration(boardId);
    const def = defaultsFor(boardId);
    if (def) writePanel(def);
    if (typeof renderOverlayFn === "function") renderOverlayFn();
}

function resetAllCalibrations() {
    const n = Object.keys(state.calibrations).length;
    if (n === 0) return;
    if (!confirm(`Reset all calibrations for ${n} board(s)?`)) return;
    state.calibrations = {};
    persistToStorage();
    const def = defaultsFor(currentBoardId());
    if (def) writePanel(def);
    if (typeof renderOverlayFn === "function") renderOverlayFn();
}

export function syncPanelToCurrentBoard() {
    const boardId = currentBoardId();
    if (!boardId) return;
    const cal = getCalibration(boardId) ?? defaultsFor(boardId);
    if (cal) writePanel(cal);
}

export function initCalibration(rerender) {
    renderOverlayFn = rerender;
    attachInputBinding("hexcal-size", 2);
    attachInputBinding("hexcal-sizey", 2);
    attachInputBinding("hexcal-x", 0);
    attachInputBinding("hexcal-y", 0);
    const log = $("hexcal-log");
    if (log) log.addEventListener("click", logCalibration);
    const reset = $("hexcal-reset");
    if (reset) reset.addEventListener("click", resetCalibration);
    const resetAll = $("hexcal-reset-all");
    if (resetAll) resetAll.addEventListener("click", resetAllCalibrations);
    const odd = $("hexcal-odd");
    if (odd) odd.addEventListener("change", applyAndRender);
}
