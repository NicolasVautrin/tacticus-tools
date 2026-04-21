// DOM helpers + status bar + view-mode toggle.
//
// `status()` writes to the header chrono line — thematic "last signal"
// display. `updateViewMode()` swaps between DEPLOY (config) and OBSERVE
// (runner) — the deployment section is hidden in OBSERVE since placements
// are overridden by authoritative matchState from the runner.

import { state } from "./state.js";

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

export function updateViewMode() {
    const inRunner = state.runnerId !== null && state.runnerId !== undefined;
    const deploy = $("deployment-section");
    if (deploy) deploy.classList.toggle("hidden", inRunner);
    const log = $("log-section");
    if (log) log.classList.toggle("hidden", !inRunner);
    const controls = $("controls-section");
    if (controls) controls.classList.toggle("hidden", !inRunner);
    const modeEl = $("view-mode");
    if (modeEl) {
        modeEl.textContent = inRunner ? "OBSERVE" : "DEPLOY";
        modeEl.dataset.mode = inRunner ? "observe" : "deploy";
    }
    const btn = $("launch-btn");
    if (btn) {
        btn.disabled = false;
        btn.textContent = "ENGAGE";
    }
}
