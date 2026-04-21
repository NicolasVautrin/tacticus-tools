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
import { refreshRunners, autoSubscribeSession } from "./src/runners.js";
import { renderUnitRoster } from "./src/roster.js";
import { launchBattle } from "./src/launch.js";
import { playTurn } from "./src/actions.js";

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

    await refreshConfigs();
    await autoSubscribeSession();
    // Restore after autoSubscribeSession so an active runner takes priority.
    await restoreLastConfig();

    refreshRunners();
    setInterval(refreshRunners, 3000);

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
