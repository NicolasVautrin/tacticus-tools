// DOM helpers + status bar + view-mode toggle.
//
// `status()` writes to the header chrono line — thematic "last signal"
// display.
//
// View mode is a user-explicit toggle (BUILD ↔ MIRROR), persisted in
// localStorage:
//   - BUILD   : config-archive exploration + roster + ENGAGE.
//   - MIRROR  : live mirroring + AI-on-mirror auto-play. The Mirror panel
//               docks into the right aside; deployment section is hidden;
//               builders/archive panels are hidden from left aside (they're
//               not useful while observing a live battle).
// The hook live runs in BOTH modes (the hook is heavy and conditions
// catalog amorce, recorder, etc. — see project memory). Toggle just
// re-arranges visibility, never re-attaches Frida.

import { state, saveViewMode } from "./state.js";

export const $ = (id) => document.getElementById(id);

let statusTimer = null;

export function status(msg) {
    const el = $("status");
    if (!el) return;
    el.textContent = msg;
    el.classList.add("status--flash");
    if (statusTimer) clearTimeout(statusTimer);
    statusTimer = setTimeout(() => el.classList.remove("status--flash"), 420);
    const timestampEl = $("status-timestamp");
    if (timestampEl) {
        const d = new Date();
        const pad = (n) => String(n).padStart(2, "0");
        timestampEl.textContent =
            pad(d.getHours()) + ":" + pad(d.getMinutes())
            + ":" + pad(d.getSeconds());
    }
}

/** Apply the current `state.viewMode` to the DOM: header chip text + mode,
 * `body[data-mode]`, panel reparenting (Mirror panel docks into the right
 * aside in MIRROR mode), and runner-derived show/hide for log + controls.
 * Idempotent — safe to call from boot, on toggle, and on runner change. */
export function updateViewMode() {
    const mode = state.viewMode === "mirror" ? "mirror" : "build";
    document.body.dataset.mode = mode;

    // Header chip.
    const modeEl = $("view-mode");
    if (modeEl) {
        modeEl.textContent = mode === "mirror" ? "MIRROR" : "BUILD";
        modeEl.dataset.mode = mode;
    }

    // Sim panel placement: anchored statically into #roster-panel (right
    // aside). Visibility is gated by viewerSelection + engagement state in
    // sim.js (applyStatusToButtons), independent of the BUILD/MIRROR mode.
    const sim = $("sim-panel");
    const roster = $("roster-panel");
    if (sim && roster && sim.parentElement !== roster) {
        roster.prepend(sim);
    }

    // Runner-derived inner state of the right aside (independent of mode).
    const inRunner = state.runnerId !== null && state.runnerId !== undefined;
    const deploy = $("deployment-section");
    if (deploy) deploy.classList.toggle("hidden", inRunner);
    const log = $("log-section");
    if (log) log.classList.toggle("hidden", !inRunner);
    const controls = $("controls-section");
    if (controls) controls.classList.toggle("hidden", !inRunner);

    const btn = $("launch-btn");
    if (btn) {
        btn.disabled = false;
        btn.textContent = "ENGAGE";
    }
}

/** Toggle BUILD ↔ MIRROR. Persists + re-applies layout. */
export function toggleViewMode() {
    state.viewMode = state.viewMode === "mirror" ? "build" : "mirror";
    saveViewMode(state.viewMode);
    updateViewMode();
}

/** Wire the `#view-mode` chip click → toggle. Called once at boot. */
export function initViewModeToggle() {
    const el = $("view-mode");
    if (!el) return;
    el.style.cursor = "pointer";
    el.title = "click to toggle BUILD ↔ MIRROR";
    el.addEventListener("click", toggleViewMode);
}
