// Active runner list + switch/delete. Polling every 3s picks up runners
// created outside the UI. Switching to a runner hides the deployment UI,
// loads the runner's config (if different), and overwrites eventUnits
// with the authoritative matchState snapshot.

import { state, saveViewMode } from "./state.js";
import { $, status, updateViewMode } from "./dom.js";
import { api } from "./api.js";
import { renderOverlay } from "./board.js";
import { selectConfig, renderConfigList } from "./configs.js";
import { subscribeBattleEvents } from "./ws.js";
import { onBattleEndedRender } from "./actions.js";

export async function refreshRunners() {
    try {
        state.runners = await api.runners();
        renderRunnerList();
    } catch { /* ignore */ }
}

/** Clear every runner-tied piece of UI state. Called when the active Frida
 * session changes (re-inject, host restart) — the previous session's runner
 * lived in the now-dead script's heap, so anything we still display is stale.
 *
 * Persistent UI bits like the deployment queue (state.placements) and saved
 * configs are deliberately preserved so the user just hits ENGAGE again. */
export function resetRunnerSession() {
    state.runnerId = null;
    state.runners = [];
    state.eventUnits.clear();
    state.tileIdToCoord.clear();
    state.sessionId = null;
    state.battleEnded = null;
    updateViewMode();
    renderOverlay();
    renderRunnerList();
    // Hide the active battle UI bits.
    const log = $("battle-log");
    if (log) log.innerHTML = "";
}

import { stopAutoPlay as simStopAutoPlay, loadLiveBattleConfig } from "./sim.js";

/** Click handler for the 🪞 button. Just builds the mirror — does NOT
 * auto-start a play loop (the user controls that from the Sim panel's
 * board controls). Exported so configs.js can chain it after building a
 * preview build runner (LOAD button on archive rows). */
export async function clickMirror(source, runnerId) {
    // A new mirror invalidates any running auto-play loop on the previous
    // build target — auto-play lives in sim.js but we cancel from here so
    // the prior loop doesn't keep dispatching on a now-unmirrored build.
    try { simStopAutoPlay(); } catch { /* sim module not loaded */ }
    try {
        // Hydrate the board's hex layout + spawn data BEFORE building the
        // mirror so the panel can render the result as soon as state arrives.
        if (source === "live") {
            try { await loadLiveBattleConfig(); }
            catch (e) { console.warn("[runners] live config load failed", e); }
        }
        const body = source === "live" ? { source: "live" }
            : { source: "build", runnerId };
        const r = await fetch("/api/sim/mirror", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(body),
        });
        const data = await r.json();
        if (!data.ok) {
            status("mirror failed: " + (data.error ?? "?"));
            return;
        }
        status("mirror built · " + (source === "live"
            ? "live" : "build#" + runnerId));
        // Auto-select the new mirror in the viewer + switch to MIRROR layout.
        // For source=live → select "live" (mirror live is rendered via Live tile).
        // For source=build → select "mirror" (the new MIRROR tile is what renders it).
        state.viewerSelection = source === "live" ? "live" : "mirror";
        if (state.viewMode !== "mirror") {
            state.viewMode = "mirror";
            saveViewMode("mirror");
            updateViewMode();
        }
        renderRunnerList();  // re-render so the MIRROR tile appears
    } catch (e) { status("mirror error: " + e.message); }
}

/** Set the viewer to a specific runner kind. The Sim panel observes this
 * to render the appropriate state (or hides itself if null). */
function setViewer(kind) {
    state.viewerSelection = kind;
    renderRunnerList();
    // Sim panel visibility/content is driven by sim.js's pollStatus +
    // applyStatusToButtons; trigger a refresh so it updates immediately.
    try {
        document.dispatchEvent(new CustomEvent("viewer-changed"));
    } catch { /* no-op */ }
}


function isCurrentMirrorSource(simStatus, kind) {
    return simStatus?.mirrorSource?.kind === kind;
}

export function renderRunnerList() {
    const ul = $("runner-list");
    if (!ul) return;
    ul.innerHTML = "";
    const sim = state.simStatus ?? null;
    const hasLive = !!sim?.hasLive;
    const builds = state.runners ?? [];
    const build = builds[0] ?? null;
    const hasMirror = !!sim?.mirrorSource;
    const sel = state.viewerSelection;

    if (!hasLive && !build) {
        ul.innerHTML =
            '<li class="runners__empty">'
          + '<span>—</span> no active engagement'
          + '</li>';
        return;
    }

    // ----- LIVE row -----
    if (hasLive) {
        const li = document.createElement("li");
        li.className = "runner-row runner-row--live";
        if (sel === "live") li.classList.add("selected");
        if (isCurrentMirrorSource(sim, "live")) li.classList.add("mirrored");
        const stage = sim.liveStageName ?? "Running";
        li.innerHTML =
            '<span class="runner-row__pulse runner-row__pulse--live"></span>'
          + '<div class="runner-row__body">'
          + '<div class="runner-row__line1">'
          +   '<span class="runner-row__id">LIVE</span>'
          +   '<span class="runner-row__mode">in-game</span>'
          +   '<button class="runner-row__save" title="save config">💾</button>'
          +   '<button class="runner-row__mirror" title="mirror this">🪞</button>'
          + '</div>'
          + '<div class="runner-row__line2">'
          +   '<span>' + stage + '</span>'
          +   '<span>·</span>'
          +   '<span>' + (sim.isAiRunning ? "AI playing" : "human turn") + '</span>'
          + '</div>'
          + '</div>';
        li.addEventListener("click", () => setViewer("live"));
        li.querySelector(".runner-row__mirror")
          .addEventListener("click", (ev) => {
            ev.stopPropagation();
            clickMirror("live");
        });
        li.querySelector(".runner-row__save")
          .addEventListener("click", async (ev) => {
            ev.stopPropagation();
            try {
                const r = await fetch("/api/sim/save-live-config",
                    { method: "POST" });
                const data = await r.json();
                if (!data.ok) status("save failed: " + (data.error ?? "?"));
                else status("config saved · " + data.id);
            } catch (e) { status("save error: " + e.message); }
        });
        ul.appendChild(li);
    }

    // ----- BUILD row (single-build policy) -----
    if (build) {
        const li = document.createElement("li");
        li.className = "runner-row";
        if (sel === "build") li.classList.add("selected");
        const age = build.lastUpdatedAt
            ? Math.max(0, Math.round((Date.now() - build.lastUpdatedAt) / 1000))
              + "s"
            : "idle";
        const mode = (build.configId ?? "unknown")
            .replace(/GameModeSource.*/, "");
        const id = "BUILD";
        li.innerHTML =
            '<span class="runner-row__pulse"></span>'
          + '<div class="runner-row__body">'
          + '<div class="runner-row__line1">'
          +   '<span class="runner-row__id">' + id + '</span>'
          +   '<span class="runner-row__mode">' + mode + '</span>'
          +   '<button class="runner-row__mirror" title="mirror this">🪞</button>'
          +   '<button class="runner-row__del" title="dispose">×</button>'
          + '</div>'
          + '<div class="runner-row__line2">'
          +   '<span>seq ' + build.seq + '</span>'
          +   '<span>·</span>'
          +   '<span>' + (build.lastLabel ?? "-") + '</span>'
          +   '<span>·</span>'
          +   '<span>' + age + '</span>'
          + '</div>'
          + '</div>';
        li.addEventListener("click", () => {
            switchToRunner(build.runnerId);
            setViewer("build");
        });
        li.querySelector(".runner-row__mirror")
          .addEventListener("click", (ev) => {
            ev.stopPropagation();
            clickMirror("build", build.runnerId);
        });
        li.querySelector(".runner-row__del")
          .addEventListener("click", async (ev) => {
            ev.stopPropagation();
            await deleteRunner(build.runnerId);
        });
        ul.appendChild(li);
    }

    // ----- MIRROR row (visible whenever a mirror exists, regardless of source) -----
    if (hasMirror) {
        const li = document.createElement("li");
        li.className = "runner-row runner-row--mirror";
        if (sel === "mirror") li.classList.add("selected");
        const sourceLabel = sim.mirrorSource.kind === "live"
            ? "sandbox of LIVE"
            : "sandbox of BUILD";
        li.innerHTML =
            '<span class="runner-row__pulse runner-row__pulse--mirror"></span>'
          + '<div class="runner-row__body">'
          + '<div class="runner-row__line1">'
          +   '<span class="runner-row__id">MIRROR</span>'
          +   '<span class="runner-row__mode">' + sourceLabel + '</span>'
          + '</div>'
          + '<div class="runner-row__line2">'
          +   '<span>' + (sim.mirrorSourceStage === 1 ? "Running" : "—") + '</span>'
          + '</div>'
          + '</div>';
        li.addEventListener("click", () => setViewer("mirror"));
        ul.appendChild(li);
    }
}

export async function deleteRunner(runnerId) {
    try {
        await api.deleteRunner(runnerId);
        if (state.runnerId === runnerId) {
            state.runnerId = null;
            state.eventUnits.clear();
            state.tileIdToCoord.clear();
            updateViewMode();
            renderOverlay();
            status("runner " + runnerId + " disposed");
        }
        await refreshRunners();
    } catch (e) {
        status("delete failed: " + e.message);
    }
}

export async function switchToRunner(runnerId) {
    const r = state.runners.find((x) => x.runnerId === runnerId);
    if (!r) return;
    if (r.configId && state.selected?.id !== r.configId) {
        const cfg = state.configs.find((c) => c.id === r.configId);
        if (cfg) await selectConfig(cfg);
    }
    state.runnerId = runnerId;
    // Wipe stale battleEnded from a previous runner so the new battle's
    // PLAY TURN button isn't stuck on "BATTLE ENDED" until the next event.
    if (state.battleEnded && state.battleEnded.runnerId !== runnerId) {
        state.battleEnded = null;
    }
    updateViewMode();
    await resumeRunnerState(runnerId);
    renderConfigList();
    renderRunnerList();
    onBattleEndedRender();
    status("runner " + runnerId + " · "
         + (r.configId?.replace(/GameModeSource.*/, "") ?? ""));
}

// Subscribe to the currently-running Frida session + resume the most recent
// runner (if any). Auto-selects its config + rebuilds eventUnits from the
// latest matchState dump so a page reload mid-battle doesn't lose the map.
//
// Idempotent: on repeated calls (e.g. after re-inject), it first wipes any
// stale runner-tied UI before re-subscribing. So the caller doesn't need to
// reset manually.
export async function autoSubscribeSession() {
    // Reconcile first: if Frida was relaunched, its runner registry is empty
    // and host-side entries for those ids are stale. Without this, PLAY TURN
    // on a resumed runner fails with `runner N not found`.
    try {
        const sync = await api.syncRunners();
        if (sync.removed?.length) {
            console.log("pruned stale runners: " + sync.removed.join(", "));
        }
    } catch (e) { console.warn("runner sync failed", e); }

    // Resolve active runner + set state.runnerId BEFORE opening the WS.
    // Otherwise ring-buffered events from older runners fire first and the
    // null-guard in ws.onmessage adopts the wrong runner as "current".
    try {
        await refreshRunners();
        if (state.runners?.length) {
            await switchToRunner(state.runners[0].runnerId);
        } else if (state.runnerId !== null || state.eventUnits.size) {
            // No runner alive on the host side — sweep any UI from a previous
            // (now-dead) session.
            resetRunnerSession();
        }
    } catch (e) { console.warn("runner resume failed", e); }

    try {
        const sessions = await api.sessions();
        const running = sessions.find((s) => s.status === "running");
        if (running) {
            console.log("auto-subscribing to session " + running.id);
            state.sessionId = running.id;
            subscribeBattleEvents(running.id);
        } else {
            state.sessionId = null;
        }
    } catch (e) { console.warn("session probe failed", e); }
}

// Rebuild eventUnits from the runner's latest matchState. Unit position
// chain: Unit(Type=1).Components → Feet[0] → Foot(Type=5).Components →
// TileId → Board lookup.
export async function resumeRunnerState(runnerId) {
    const dump = await api.latestState(runnerId);
    if (!dump) return;
    const ms = dump.matchState;
    if (!ms) return;
    const ents = ms._entities || [];

    // TileId → (col, row) from the Match entity's Tiles component.
    for (const e of ents) {
        if (!e) continue;
        for (const c of e.Components ?? []) {
            if (!c || !Array.isArray(c.Tiles) || !Array.isArray(c.Tiles[0])) continue;
            if (typeof c.Tiles[0][0] !== "number") continue;
            state.tileIdToCoord.clear();
            for (let col = 0; col < c.Tiles.length; col++) {
                for (let row = 0; row < c.Tiles[col].length; row++) {
                    state.tileIdToCoord.set(c.Tiles[col][row], { col, row });
                }
            }
            break;
        }
        if (state.tileIdToCoord.size) break;
    }

    state.eventUnits.clear();
    for (const e of ents) {
        if (!e || e.Type !== 1) continue;
        let feet = null, ownerEntId = 0, visualId = null;
        for (const c of e.Components ?? []) {
            if (!c) continue;
            if (Array.isArray(c.Feet) && feet === null) feet = c.Feet;
            if (c.PlayerEntityId != null && !ownerEntId) {
                ownerEntId = c.CurrentPlayerEntityId ?? c.PlayerEntityId;
            }
            if (typeof c.VisualId === "string" && !visualId) visualId = c.VisualId;
        }
        if (!feet || !feet.length) continue;
        const foot = ents[feet[0]];
        if (!foot) continue;
        let tileId = null;
        for (const c of foot.Components ?? []) {
            if (c && c.TileId != null) { tileId = c.TileId; break; }
        }
        if (tileId == null) continue;
        const coord = state.tileIdToCoord.get(tileId);
        if (!coord) continue;
        const ownerEnt = ents[ownerEntId];
        const playerId = ownerEnt?.Component?.PlayerId ?? ownerEntId;
        state.eventUnits.set(e.Id, {
            col: coord.col, row: coord.row,
            playerId, kind: "unit", visualId,
        });
    }
    console.log("resumed runner " + runnerId + ": "
        + state.eventUnits.size + " units on map");
    renderOverlay();
}
