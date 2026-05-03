// ENGAGE — POST /api/launch then switch to the newly-created runner.

import { state } from "./state.js";
import { $, status } from "./dom.js";
import { api } from "./api.js";
import { subscribeBattleEvents } from "./ws.js";
import { refreshRunners, switchToRunner } from "./runners.js";

export async function launchBattle() {
    if (!state.selected || !state.config) {
        status("pick a config first");
        return;
    }
    if (state.placements.length === 0) {
        status("queue at least one unit before engagement");
        return;
    }
    const btn = $("launch-btn");
    btn.disabled = true;
    btn.textContent = "ENGAGING…";
    try {
        // Resolve playerId from the current spawn map at engage time. The
        // value stored on the placement may be stale (from a pre-fix save)
        // or the tile's ownership may have been recomputed — take the spawn
        // map as source of truth, fall back to the placement's playerId.
        // For builder-generated configs the JSON is held in memory only —
        // ship it back to the host so it can persist the setup as a
        // capture at engage time.
        const opts = state.selected.kind === "generated" && state.selected.inlineJson
            ? {
                inlineConfig: state.selected.inlineJson,
                inlineMeta: {
                    mode: state.selected.mode,
                    campaignId: state.selected.campaignId ?? null,
                    locationIndex: state.selected.locationIndex ?? null,
                },
            }
            : undefined;
        const data = await api.launch(
            state.selected.id,
            state.placements.map((p) => {
                const sp = state.spawnPointsByTile.get(p.col + "," + p.row);
                return {
                    unitId: p.unitId,
                    playerId: sp?.playerId ?? p.playerId,
                    col: p.col,
                    row: p.row,
                };
            }),
            opts);
        state.sessionId = data.sessionId;
        status("runner " + data.runnerId
             + " started on session " + data.sessionId);
        // Order matters: switchToRunner sets state.runnerId — must happen
        // BEFORE subscribeBattleEvents. Otherwise the WS replays initRunner/
        // applyAddUnit/startBattle events from the ring buffer while
        // state.runnerId is still null, and ws.onmessage filters them out.
        await refreshRunners();
        await switchToRunner(data.runnerId);
        subscribeBattleEvents(data.sessionId);
    } catch (e) {
        status("launch failed: " + e.message);
        btn.disabled = false;
        btn.textContent = "ENGAGE";
    }
}
