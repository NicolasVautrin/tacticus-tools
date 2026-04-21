// Active runner list + switch/delete. Polling every 3s picks up runners
// created outside the UI. Switching to a runner hides the deployment UI,
// loads the runner's config (if different), and overwrites eventUnits
// with the authoritative matchState snapshot.

import { state } from "./state.js";
import { $, status, updateViewMode } from "./dom.js";
import { api } from "./api.js";
import { renderOverlay } from "./board.js";
import { selectConfig, renderConfigList } from "./configs.js";
import { subscribeBattleEvents } from "./ws.js";

export async function refreshRunners() {
    try {
        state.runners = await api.runners();
        renderRunnerList();
    } catch { /* ignore */ }
}

export function renderRunnerList() {
    const ul = $("runner-list");
    if (!ul) return;
    ul.innerHTML = "";
    if (!state.runners?.length) {
        ul.innerHTML =
            '<li class="runners__empty">'
          + '<span>—</span> no active engagement'
          + '</li>';
        return;
    }
    for (const r of state.runners) {
        const li = document.createElement("li");
        li.className = "runner-row";
        if (r.runnerId === state.runnerId) li.classList.add("selected");
        const age = r.lastUpdatedAt
            ? Math.max(0, Math.round((Date.now() - r.lastUpdatedAt) / 1000))
              + "s"
            : "idle";
        const mode = (r.configId ?? "unknown")
            .replace(/GameModeSource.*/, "");
        const id = "R" + String(r.runnerId).padStart(2, "0");
        li.innerHTML =
            '<span class="runner-row__pulse"></span>'
          + '<div class="runner-row__body">'
          + '<div class="runner-row__line1">'
          +   '<span class="runner-row__id">' + id + '</span>'
          +   '<span class="runner-row__mode">' + mode + '</span>'
          +   '<button class="runner-row__del" title="dispose">×</button>'
          + '</div>'
          + '<div class="runner-row__line2">'
          +   '<span>seq ' + r.seq + '</span>'
          +   '<span>·</span>'
          +   '<span>' + (r.lastLabel ?? "-") + '</span>'
          +   '<span>·</span>'
          +   '<span>' + age + '</span>'
          + '</div>'
          + '</div>';
        li.addEventListener("click", () => switchToRunner(r.runnerId));
        li.querySelector(".runner-row__del")
          .addEventListener("click", async (ev) => {
            ev.stopPropagation();
            await deleteRunner(r.runnerId);
        });
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
    updateViewMode();
    await resumeRunnerState(runnerId);
    renderConfigList();
    renderRunnerList();
    status("runner " + runnerId + " · "
         + (r.configId?.replace(/GameModeSource.*/, "") ?? ""));
}

// Subscribe to the currently-running Frida session + resume the most recent
// runner (if any). Auto-selects its config + rebuilds eventUnits from the
// latest matchState dump so a page reload mid-battle doesn't lose the map.
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
        }
    } catch (e) { console.warn("runner resume failed", e); }

    try {
        const sessions = await api.sessions();
        const running = sessions.find((s) => s.status === "running");
        if (running) {
            console.log("auto-subscribing to session " + running.id);
            state.sessionId = running.id;
            subscribeBattleEvents(running.id);
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
