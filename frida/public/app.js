// Entry point. Boots the module graph, wires DOM events, starts polling.
//
// Module graph:
//   state  dom  hex  api
//    │     │    │    │
//    ├─────┼────┼────┼───→ images
//    ├─────┼────┼────┼───→ placements ─┐
//    │     │    │    │                 ├─→ board ─→ battle-log ─→ ws
//    │     │    │    │                 │                            │
//    │     │    │    └───→ dnd ────────┘                            │
//    │     │    │                                                    │
//    │     │    └───→ roster                                         │
//    │     │                                                          │
//    │     └───→ configs ──→ runners ←──────────────────────────────┘
//    │                          │
//    │                          └───→ launch
//    │
//    └───→ used everywhere (singleton state object)

import { state } from "./src/state.js";
import { $, status } from "./src/dom.js";
import { api } from "./src/api.js";
import { refreshConfigs, restoreLastConfig } from "./src/configs.js";
import {
    refreshRunners, autoSubscribeSession, resetRunnerSession,
} from "./src/runners.js";
import { renderUnitRoster } from "./src/roster.js";
import { launchBattle } from "./src/launch.js";
import { playTurn } from "./src/actions.js";
import { wireAdmin } from "./src/admin.js";
import { initCampaignBuilder } from "./src/campaign-builder.js";
import { initCollapsiblePanels } from "./src/collapsible.js";

(async function boot() {
    try {
        state.manifest = await api.manifest();
        status("manifest loaded · "
             + Object.keys(state.manifest.units).length + " portraits · "
             + Object.keys(state.manifest.boards).length + " boards");
        renderUnitRoster();
    } catch (e) {
        status("manifest load failed: " + e.message);
    }

    try {
        state.assetMap = await api.assetMap();
        if (state.assetMap) {
            console.log("unit-asset-map: "
                + Object.keys(state.assetMap).length + " entries");
        }
    } catch { /* fallback to heuristic */ }

    $("refresh-configs").addEventListener("click", refreshConfigs);
    $("unit-filter").addEventListener("input", renderUnitRoster);
    $("launch-btn").addEventListener("click", launchBattle);
    $("play-turn-btn").addEventListener("click", playTurn);
    wireAdmin();

    await refreshConfigs();
    await autoSubscribeSession();
    // Restore after autoSubscribeSession so an active runner takes priority.
    await restoreLastConfig();

    refreshRunners();
    setInterval(refreshRunners, 3000);

    // Boot the campaign builder panel. The version slug comes from
    // /api/admin/status (added when meta-sync has run at least once);
    // if it's null at boot, the builder polls until a session arrives.
    try {
        const adm = await api.adminStatus();
        await initCampaignBuilder(adm?.version ?? null);
    } catch (e) {
        console.warn("[app] campaign-builder init failed", e);
    }

    // Wire collapsible behaviour on every .panel-block. Persists per-panel
    // state to localStorage so the user's layout survives reloads.
    initCollapsiblePanels();

    // When admin.js detects a new session (host restored after reboot, or a
    // fresh INJECT just landed), wipe runner-tied UI and re-run the subscribe
    // pipeline so the WS rebinds — without a manual page reload.
    //
    // The previous session's runner died with its agent's heap. Anything
    // we still display (board overlay, runner list, log) is stale.
    window.addEventListener("tacticus:session-changed", (ev) => {
        const sid = ev.detail?.sessionId ?? null;
        const prev = ev.detail?.previousSessionId ?? null;
        if (sid !== prev && prev !== null) {
            // Session swap or session loss — reset UI before any rebind.
            console.log(`[app] session changed ${prev} → ${sid ?? "none"}, resetting`);
            resetRunnerSession();
        }
        // Only re-subscribe when the session id actually differs from what
        // we're already on. boot() already performed the initial subscribe;
        // admin.js's first poll (prev=null → sid=N) would otherwise trigger
        // a redundant subscribe that piles a second WS on the same session.
        if (sid !== null && sid !== state.sessionId) {
            autoSubscribeSession().catch((e) =>
                console.warn("re-subscribe failed", e));
        }
    });

    // Tick the status timestamp every second so the HUD stays alive even
    // when no event fires.
    const tsEl = $("status-timestamp");
    if (tsEl) {
        const pad = (n) => String(n).padStart(2, "0");
        const tick = () => {
            const d = new Date();
            tsEl.textContent =
                pad(d.getHours()) + ":" + pad(d.getMinutes())
                + ":" + pad(d.getSeconds());
        };
        tick();
        setInterval(tick, 1000);
    }
})();
