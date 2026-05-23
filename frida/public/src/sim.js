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
    /** Last `sim_auto_play_complete` payload — rendered below the
     * comparator until the next AI turn. */
    lastAutoPlay: null,
    /** True while a /api/sim/run-ai-turn round-trip is in flight, so the
     * button stays disabled and the UI can show a "running" hint. */
    aiTurnInFlight: false,
};

/** Auto-play loop control for build-source mirrors. Lives in the board
 * (Sim panel) — not on the runner row. The board owns the rendering of
 * the mirror, so the play/pause control is conceptually colocated there.
 * `target` = the build runnerId currently being auto-played; null when
 * no loop is running. `stopRequested` = soft-cancel signal the loop
 * checks each iteration. */
const autoPlay = { target: null, stopRequested: false };

/** Cancels any running auto-play loop. Called by runners.js when the
 * user picks a different mirror via 🪞. */
export function stopAutoPlay() {
    autoPlay.stopRequested = true;
    autoPlay.target = null;
    refreshAutoPlayButton();
}

/** Run ONE auto-play step on the mirror's source — dispatches a single
 * CheatRunAIMessage so the active team plays by AI, then stops. Same
 * behavior for live and build mirrors: AUTO-PLAY = one turn, period.
 * If the user wants the next turn played, they click again. */
async function startAutoPlayLoop(runnerId) {
    refreshAutoPlayButton();
    if (autoPlay.target !== runnerId || autoPlay.stopRequested) {
        refreshAutoPlayButton();
        return;
    }
    let r;
    try {
        r = await fetch("/api/sim/auto-play-step", { method: "POST" });
    } catch (e) {
        status("auto-play error: " + e.message);
        autoPlay.target = null;
        refreshAutoPlayButton();
        return;
    }
    const data = await r.json().catch(() => ({}));
    if (!data.ok) {
        status("auto-play failed: " + (data.reason ?? data.error ?? "?"));
    } else if (!data.advanced) {
        status("auto-play no-op · " + (data.reason ?? "stopped"));
    } else {
        status("auto-play · turn played on " + (data.target ?? "?"));
    }
    autoPlay.target = null;
    refreshAutoPlayButton();
}

async function clickEndTurn() {
    const ms = sim.status?.mirrorSource;
    if (!ms) { status("mirror something first"); return; }
    const btn = $("sim-end-turn-btn");
    if (btn) btn.disabled = true;
    try {
        const r = await fetch("/api/sim/end-turn", { method: "POST" });
        const data = await r.json();
        if (!data.ok) status("end-turn failed: " + (data.error ?? "?"));
        else status("turn ended on " + (data.target ?? "?")
            + " · player " + data.playerBefore + " → " + data.playerAfter);
    } catch (e) { status("end-turn error: " + e.message); }
    finally { refreshAutoPlayButton(); }
}

function clickAutoPlay() {
    const ms = sim.status?.mirrorSource;
    if (!ms) { status("mirror something first"); return; }
    if (autoPlay.target !== null && !autoPlay.stopRequested) {
        // Already running — UI is supposed to be disabled in that case;
        // ignore re-click defensively.
        return;
    }
    const targetKey = ms.kind === "build" ? ms.runnerId : "live";
    autoPlay.target = targetKey;
    autoPlay.stopRequested = false;
    status("auto-play started · " + (ms.kind === "build"
        ? "build#" + ms.runnerId : "live"));
    startAutoPlayLoop(targetKey);
}

/** AUTO-PLAY and END-TURN share the same enable rule:
 *
 *   - Build mirror → enabled when not currently auto-playing.
 *   - Live mirror → enabled when not auto-playing AND not in an AI turn.
 *   - No mirror → disabled.
 *
 * No manual STOP button — the auto-play loop ends naturally when the stage
 * leaves Running, when the source runner is gone, or when the user picks a
 * different mirror (which calls stopAutoPlay).
 */
function refreshAutoPlayButton() {
    const s = sim.status;
    const ms = s?.mirrorSource;
    const isBuildMirror = ms?.kind === "build";
    const isLiveMirror = ms?.kind === "live";
    const isAi = !!s?.isAiRunning;
    const hasMirror = ms != null;
    const running = autoPlay.target !== null && !autoPlay.stopRequested;
    // Source runner must be in Running stage (1). Anything else means
    // battle finished / pre-start / source disposed → buttons disabled.
    const sourceRunning = s?.mirrorSourceStage === 1;
    // Same rule for both buttons.
    const allowed = hasMirror && !running && sourceRunning
        && (isBuildMirror || (isLiveMirror && !isAi));

    const tipDisabled = !hasMirror
        ? "mirror something first (🪞 on a row)"
        : !sourceRunning
            ? "battle finished or source unloaded"
            : running
                ? "auto-play running"
                : (isLiveMirror && isAi)
                    ? "wait — AI turn in progress on live"
                    : "not ready";

    const btn = $("sim-auto-play-btn");
    if (btn) {
        btn.disabled = !allowed;
        btn.textContent = "▶ AUTO-PLAY";
        btn.classList.toggle("running", running);
        btn.title = allowed
            ? "auto-play (active team plays each step)"
            : tipDisabled;
    }
    const endBtn = $("sim-end-turn-btn");
    if (endBtn) {
        endBtn.disabled = !allowed;
        endBtn.title = allowed
            ? "end the active team's turn (source advances, mirror auto-syncs)"
            : tipDisabled;
    }
}

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
        // Trigger a replay-bundle download in the background — config + seed
        // + every captured message Newtonsoft-serialized with PRNG snapshots.
        // Lets the user reconstruct the same state offline via buildRunner.
        try {
            const a = document.createElement("a");
            a.href = "/api/sim/dump-replay";
            a.download = "";  // server sets Content-Disposition filename
            document.body.appendChild(a);
            a.click();
            a.remove();
        } catch (e) { /* download is best-effort */ }
    } catch (e) {
        status("mirror error: " + e.message);
    } finally {
        await pollStatus();
    }
}

async function clickRunAiTurn() {
    const btn = $("sim-run-ai-btn");
    if (!btn || btn.disabled) return;
    sim.aiTurnInFlight = true;
    btn.disabled = true;
    btn.textContent = "RUNNING…";
    status("AI turn via mirror — running");
    try {
        const res = await fetchJson("/api/sim/run-ai-turn", { method: "POST" });
        if (!res.ok) {
            status("AI turn failed: " + (res.error ?? "?"));
            sim.lastAutoPlay = { ok: false, error: res.error ?? "?" };
        } else {
            sim.lastAutoPlay = res;
            const div = (res.commits ?? []).filter((c) => c.divergent).length;
            status("AI turn done · " + (res.messages ?? 0) + " msgs · "
                + div + " event divergence(s)"
                + (res.phase1Err ? " · ph1=" + res.phase1Err : "")
                + (res.phase2Err ? " · ph2=" + res.phase2Err : ""));
        }
        renderAutoPlay();
        await refreshSimState();
    } catch (e) {
        status("AI turn error: " + e.message);
        sim.lastAutoPlay = { ok: false, error: e.message };
        renderAutoPlay();
    } finally {
        sim.aiTurnInFlight = false;
        btn.textContent = "AUTO-PLAY";
        await pollStatus();
    }
}

/** Pull the live runner's BattleConfiguration JSON from the agent and feed
 * it to the board renderer. Exported so runners.js can call it after a
 * 🪞 click on the Live row — without the config, the mini-board has no
 * tile/spawn data to render. */
export async function loadLiveBattleConfig() {
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
        // Mirror into shared state so the runners panel can render the
        // 🪞 highlights and the synthetic Live row.
        state.simStatus = sim.status;
        applyStatusToButtons();
        // Re-render the runners panel — cheap, just a list rebuild — so
        // the mirror highlight and the Live row reflect new sim status.
        try {
            const { renderRunnerList } = await import("./runners.js");
            renderRunnerList();
        } catch { /* runners module not loaded yet */ }
    } catch {
        // WS-down or transient — render with what we have
        applyStatusToButtons();
    }
}

function applyStatusToButtons() {
    refreshAutoPlayButton();
    // Show the Sim panel based on viewerSelection (set by runners.js).
    // Hidden when nothing is selected. Live → must have a live mirror;
    // build → must have a build runner; mirror → must have a mirror.
    const panel = $("sim-panel");
    if (panel) {
        const sel = state.viewerSelection;
        const s = sim.status;
        // Visible only when the selected runner is engaged (Running stage).
        const liveMirrorEngaged = s?.mirrorSource?.kind === "live"
            && s?.mirrorSourceStage === 1;
        const buildEngaged = s?.buildStage === 1;
        const mirrorEngaged = !!s?.built && s?.mirrorSourceStage === 1;
        const visible =
            (sel === "live" && liveMirrorEngaged)
            || (sel === "build" && buildEngaged)
            || (sel === "mirror" && mirrorEngaged);
        panel.classList.toggle("hidden", !visible);
    }
    const blockEl = $("sim-block-reason");
    const s = sim.status;
    if (!s) {
        if (blockEl) blockEl.textContent = "— probing…";
        return;
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
    renderAutoPlay();
}

function renderAutoPlay() {
    const el = $("sim-autoplay-area");
    if (!el) return;
    const a = sim.lastAutoPlay;
    if (!a) {
        el.classList.add("hidden");
        el.innerHTML = "";
        return;
    }
    el.classList.remove("hidden");
    if (a.ok === false) {
        el.innerHTML = `<div class="sim-autoplay__head bad">AI TURN FAILED</div>`
            + `<div class="sim-autoplay__line">${escapeHtml(a.error ?? "?")}</div>`;
        return;
    }
    const commits = a.commits ?? [];
    const div = commits.filter((c) => c.divergent).length;
    const head = `<div class="sim-autoplay__head ${div === 0 ? "ok" : "bad"}">`
        + `AI TURN · ${a.messages ?? 0} msgs · ${div} divergence${div === 1 ? "" : "s"}`
        + `</div>`;
    const meta = `<div class="sim-autoplay__line">`
        + `phase1: ${a.phase1Ms ?? "?"} ms · phase2: ${a.phase2Ms ?? "?"} ms`
        + (a.phase1Err ? ` · ph1Err: ${escapeHtml(a.phase1Err)}` : "")
        + (a.phase2Err ? ` · ph2Err: ${escapeHtml(a.phase2Err)}` : "")
        + `</div>`;
    const rows = commits.slice(0, 30).map((c) => {
        const cls = c.divergent ? "sim-autoplay__row bad" : "sim-autoplay__row ok";
        const tag = c.src + " · " + c.cls + (c.unitId != null ? " #" + c.unitId : "");
        const counts = `live=${c.liveEventsCount} mirror=${c.mirrorEventsCount}`;
        const diff = c.divergent
            ? ` <span class="sim-autoplay__diff">${escapeHtml(c.firstDiff ?? "?")}</span>`
            : "";
        return `<tr class="${cls}"><td>${c.idx}</td><td>${escapeHtml(tag)}</td>`
            + `<td>${counts}</td><td>${diff}</td></tr>`;
    }).join("");
    const tbl = `<table class="sim-autoplay__tbl"><thead><tr>`
        + `<th>#</th><th>msg</th><th>events</th><th>diff</th>`
        + `</tr></thead><tbody>${rows}</tbody></table>`;
    const more = commits.length > 30
        ? `<div class="sim-autoplay__more">… +${commits.length - 30} more</div>`
        : "";
    el.innerHTML = head + meta + tbl + more;
}

function escapeHtml(s) {
    return String(s)
        .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
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
    const autoBtn = $("sim-auto-play-btn");
    if (autoBtn) autoBtn.addEventListener("click", clickAutoPlay);
    const endBtn = $("sim-end-turn-btn");
    if (endBtn) endBtn.addEventListener("click", clickEndTurn);

    // React to viewer selection changes (runners.js click handlers fire
    // a custom event after updating state.viewerSelection).
    document.addEventListener("viewer-changed", () => {
        applyStatusToButtons();
        scheduleRefresh();
    });

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
    registerWsHandler("sim_auto_play_complete", (msg) => {
        // Lightweight notification — the round-trip POST already returned
        // the full payload as `sim.lastAutoPlay`. Just nudge the status.
        status("AI turn complete · " + (msg.messages ?? "?")
            + " msgs · " + (msg.divergences ?? 0) + " divergence(s)");
    });

    pollStatus();
    sim.pollTimer = setInterval(pollStatus, POLL_INTERVAL_MS);
}
