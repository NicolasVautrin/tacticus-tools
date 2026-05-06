// Mirror panel — view onto the isolated mirror runner that follows live
// message-by-message. We render only the mirror's matchState (the live
// game itself is rendered by Tacticus); a compact comparison dashboard
// confirms the mirror stays aligned with live.
//
// Wiring:
//   - "MIRROR NOW" button: POST /api/sim/mirror → initial bring-up.
//   - "RESET" button: POST /api/sim/reset → drop the mirror.
//   - GET /api/sim/status polled every 2s → enable/disable button per
//     `canMirror` (live in Running stage AND no AI mid-execution).
//   - WS event `sim_state_changed` (light notification, 50 bytes) →
//     debounced `refreshSimState()` → GET /api/sim/state → re-render.
//   - WS event `sim_diverged` → switch to a divergent banner; user
//     clicks Reset to recover.

import { $, status } from "./dom.js";
import { state, saveLastConfigId } from "./state.js";
import { registerWsHandler } from "./ws.js";
import { hydrateConfig } from "./configs.js";

const POLL_INTERVAL_MS = 2000;
const REFRESH_DEBOUNCE_MS = 50;

const sim = {
    status: null,    // last /api/sim/status payload
    state: null,     // last /api/sim/state payload
    pendingRefresh: null,
    inFlightRefresh: false,
    pollTimer: null,
};

async function fetchJson(url, opts = {}) {
    const r = await fetch(url, opts);
    if (!r.ok) {
        const data = await r.json().catch(() => ({}));
        throw new Error(data.error ?? r.statusText);
    }
    return r.json();
}

async function clickMirror() {
    const btn = $("sim-mirror-btn");
    if (!btn || btn.disabled) return;
    btn.disabled = true;
    try {
        // Always pull the live BattleConfiguration first — it lets us load
        // the matching board PNG + hex layout if the user didn't pre-load
        // a config via the campaign builder.
        await loadLiveBattleConfig();

        const res = await fetchJson("/api/sim/mirror", { method: "POST" });
        if (!res.ok) {
            status("mirror failed: " + (res.error ?? "?"));
            return;
        }
        status("mirror rebuilt · synced to log idx " + res.syncedToLogIdx);
        await refreshSimState();
    } catch (e) {
        status("mirror error: " + e.message);
    } finally {
        await pollStatus();
    }
}

async function loadLiveBattleConfig() {
    // Always (re)load — MIRROR NOW must take precedence over any user-
    // selected archive capture, so we re-hydrate the live config on every
    // click. We also purge the persisted archive id so a future page reload
    // doesn't resurrect the stale selection.
    try {
        const r = await fetch("/api/sim/battle-config");
        if (!r.ok) return;
        const cfg = await r.json();
        // Stub meta so hydrateConfig doesn't crash on null lookups; the
        // board only needs cfg.Board.Id + Player.Players to render.
        const stubMeta = { id: "live-mirror", mode: "live",
            campaignId: null, locationIndex: null };
        hydrateConfig(stubMeta, cfg);
        saveLastConfigId(null);
    } catch (e) {
        console.warn("[sim] live battle config load failed", e);
    }
}


async function pollStatus() {
    try {
        sim.status = await fetchJson("/api/sim/status");
        applyStatusToButtons();
    } catch {
        // WS-down or transient — render with what we have
        applyStatusToButtons();
    }
}

function applyStatusToButtons() {
    const btn = $("sim-mirror-btn");
    const blockEl = $("sim-block-reason");
    const s = sim.status;
    if (!s) {
        if (btn) { btn.disabled = true; btn.title = "probing…"; }
        if (blockEl) blockEl.textContent = "— probing…";
        return;
    }
    if (btn) {
        btn.disabled = !s.canMirror;
        btn.title = s.canMirror
            ? "rebuild the mirror from live and replay the full log"
            : (s.blockReason ?? "not ready");
    }
    if (blockEl) {
        if (s.diverged) {
            blockEl.textContent = "DIVERGED · " + (s.divergedReason ?? "?")
                + " — click MIRROR NOW to rebuild.";
            blockEl.className = "sim-block-reason sim-block-reason--diverged";
        } else if (!s.canMirror) {
            blockEl.textContent = s.blockReason ?? "not ready";
            blockEl.className = "sim-block-reason";
        } else if (!s.built) {
            blockEl.textContent = "ready to mirror — click MIRROR NOW.";
            blockEl.className = "sim-block-reason";
        } else {
            blockEl.textContent = "live-mirroring · synced to log idx "
                + s.lastSyncedLogIdx + " / " + s.logSize;
            blockEl.className = "sim-block-reason sim-block-reason--ok";
        }
    }
}

// Coalesce bursts of `sim_state_changed` (e.g. several AI sub-messages
// emitted within ms during an AI turn) into a single fetch.
function scheduleRefresh() {
    if (sim.pendingRefresh) return;
    sim.pendingRefresh = setTimeout(() => {
        sim.pendingRefresh = null;
        refreshSimState();
    }, REFRESH_DEBOUNCE_MS);
}

async function refreshSimState() {
    if (sim.inFlightRefresh) {
        // Another fetch is on the wire — skip; the one in flight will
        // catch the latest state when it returns.
        return;
    }
    sim.inFlightRefresh = true;
    try {
        const data = await fetchJson("/api/sim/state");
        if (!data.ok) {
            sim.state = null;
            state.simState = null;
        } else {
            sim.state = data;
            state.simState = data.mirror;
        }
        renderPanel();
        // Re-render the central board to reflect the new mirror units.
        const { renderOverlay } = await import("./board.js");
        renderOverlay();
    } catch (e) {
        console.warn("[sim] refresh failed", e);
    } finally {
        sim.inFlightRefresh = false;
    }
}

// ---- Render ----

function renderPanel() {
    renderStatusArea();
}

function renderStatusArea() {
    const el = $("sim-status-area");
    if (!el) return;
    if (!sim.state || !sim.state.ok) {
        el.classList.add("hidden");
        el.innerHTML = "";
        return;
    }
    el.classList.remove("hidden");
    const cmp = sim.state.compare;
    const equiv = cmp.equivalent;
    const head = `<div class="sim-status__head ${equiv ? "ok" : "bad"}">`
        + (equiv ? "ALIGNED ✓" : "DIVERGED ✗") + "</div>";

    const ann = (a, b) => a === b ? "" :
        ` <span class="sim-status__neq">≠ live ${b ?? "null"}</span>`;
    const m = sim.state.mirror;
    const lines = [
        `Lag: ${cmp.lag} message${cmp.lag === 1 ? "" : "s"}`,
        `Turn: ${m.turn ?? "—"}` + ann(m.turn, cmp.liveTurn)
            + ` · player: ${m.playerOnTurn ?? "—"}`
            + ann(m.playerOnTurn, cmp.liveCurrentPlayer),
        `Stage: ${m.stageName ?? "—"}`,
        `Digest: ${cmp.mirrorDigest ?? "—"}`
            + ann(cmp.mirrorDigest, cmp.liveDigest),
        `Units alive: ${cmp.mirrorUnitsAlive}`
            + ann(cmp.mirrorUnitsAlive, cmp.liveUnitsAlive),
        `AI running on live: ${cmp.isAiRunning ? "yes" : "no"}`,
    ].map((s) => `<div class="sim-status__line">${s}</div>`).join("");

    let divs = "";
    if (cmp.divergences.length > 0) {
        const rows = cmp.divergences.slice(0, 20).map((d) =>
            `<tr><td>${d.entityId}</td><td>${d.field}</td>`
            + `<td>${formatVal(d.liveValue)}</td>`
            + `<td>${formatVal(d.mirrorValue)}</td></tr>`).join("");
        const more = cmp.divergences.length > 20
            ? `<div class="sim-status__more">… +${cmp.divergences.length - 20} more</div>`
            : "";
        divs = `<table class="sim-status__divs"><thead><tr>`
            + `<th>entity</th><th>field</th><th>live</th><th>mirror</th>`
            + `</tr></thead><tbody>${rows}</tbody></table>${more}`;
    }

    el.innerHTML = head + lines + divs;
}

function formatVal(v) {
    if (v === null || v === undefined) return "—";
    if (typeof v === "object") {
        if (v.col !== undefined && v.row !== undefined) {
            return `${v.col},${v.row}`;
        }
        return JSON.stringify(v);
    }
    return String(v);
}

export function initSim() {
    const btn = $("sim-mirror-btn");
    if (btn) btn.addEventListener("click", clickMirror);

    // Listen for the agent's lightweight notifications.
    registerWsHandler("sim_state_changed", () => {
        scheduleRefresh();
    });
    registerWsHandler("sim_diverged", (msg) => {
        sim.status = sim.status ?? {};
        sim.status.diverged = true;
        sim.status.divergedReason = msg.reason ?? "?";
        applyStatusToButtons();
        // Also refresh state so the front sees the divergence flag in the
        // payload and re-renders the panel banner.
        scheduleRefresh();
    });

    pollStatus();
    sim.pollTimer = setInterval(pollStatus, POLL_INTERVAL_MS);
}
