// Captured BattleConfiguration list + selection. Selecting a config loads
// its JSON, derives the playable unit pool, and hands off to the board
// module. Also renders PredefinedUnits as a preview (no runner needed).

import { state, saveLastConfigId, loadLastConfigId } from "./state.js";
import { $, status, updateViewMode } from "./dom.js";
import { api } from "./api.js";
import { configIdToPortrait } from "./images.js";
import { loadBoard } from "./board.js";
import { renderPlacements } from "./placements.js";
import { renderUnitRoster } from "./roster.js";
import { renderRunnerList } from "./runners.js";

// Populate eventUnits with PredefinedUnits[0].Units mapped onto the active
// SpawnPointSet's enemy spawn points (Team 1). Used for config-only view
// (no runner). Cleared when a runner is opened — matchState becomes
// authoritative.
function renderConfigPredefinedUnits() {
    state.eventUnits.clear();
    const cfg = state.config;
    if (!cfg) return;
    const idx = cfg.SpawnPointSetIndex ?? 0;
    const set = cfg.Board?.SpawnPointSets?.[idx];
    if (!set) return;
    const enemyGroup = set.SpawnPointGroups?.find(
        (g) => g.TeamWithPlayerIndex === 1);
    const units = cfg.PredefinedUnits?.[0]?.Units ?? [];
    if (!enemyGroup || !units.length) return;
    const points = enemyGroup.SpawnPoints ?? [];
    units.forEach((u, i) => {
        const p = points[i];
        if (!p) return;
        // The config embeds its own UnitId → VisualId mapping in Units[].
        // Required for campaign variants like "eldarBossMauganRaCamp:2"
        // whose VisualId is "eldarMauganRa".
        const entry = cfg.Units?.find((x) => x.Id === u.UnitId);
        const visualId = entry?.VisualId ?? String(u.UnitId).split(":")[0];
        state.eventUnits.set("pre" + i, {
            col: p.Column, row: p.Row, playerId: null,
            kind: "unit", visualId,
        });
    });
}

export async function refreshConfigs() {
    try {
        const list = await api.configs();
        state.configs = list.sort((a, b) => b.ts - a.ts);
        renderConfigList();
    } catch (e) {
        status("fetch /api/configs failed: " + e.message);
    }
}

// Auto-restore last-selected config on boot. Skipped if a runner has already
// been resumed (runner view is authoritative — overwriting its config mid-flow
// would wipe the placed-unit overlay).
export async function restoreLastConfig() {
    if (state.runnerId != null) return;
    const id = loadLastConfigId();
    if (!id) return;
    const meta = state.configs.find((c) => c.id === id);
    if (!meta) return;
    await selectConfig(meta);
}

export function renderConfigList() {
    const ul = $("config-list");
    if (!ul) return;
    ul.innerHTML = "";
    if (state.configs.length === 0) {
        ul.innerHTML =
            '<li class="archive__empty">'
          + '<span>—</span> no captures yet · launch a battle in Tacticus'
          + '</li>';
        return;
    }
    for (const cfg of state.configs) {
        const li = document.createElement("li");
        li.className = "archive-row";
        if (state.selected?.id === cfg.id) li.classList.add("selected");
        const mode = cfg.mode.replace("GameModeSource", "");
        const d = new Date(cfg.ts);
        const pad = (n) => String(n).padStart(2, "0");
        const t = pad(d.getHours()) + ":" + pad(d.getMinutes())
                + ":" + pad(d.getSeconds());
        const kb = (cfg.bytes / 1024).toFixed(1);
        li.innerHTML =
            '<span class="archive-row__marker"></span>'
          + '<div class="archive-row__body">'
          + '<div class="archive-row__mode">' + mode + '</div>'
          + '<div class="archive-row__meta">'
          +   '<span>' + t + '</span>'
          +   '<span>·</span>'
          +   '<span>' + kb + ' KB</span>'
          + '</div>'
          + '</div>';
        li.addEventListener("click", () => selectConfig(cfg));
        ul.appendChild(li);
    }
}

export async function selectConfig(meta) {
    state.selected = meta;
    saveLastConfigId(meta.id);
    state.placements = state.placementsByConfig[meta.id] ?? [];
    state.runnerId = null;
    state.tileIdToCoord.clear();
    state.eventUnits.clear();
    updateViewMode();
    renderConfigList();
    renderRunnerList();
    status("loading " + meta.id + "…");
    try {
        state.config = await api.config(meta.id);
        const seen = new Set();
        state.configUnits = [];
        for (const u of state.config.Units ?? []) {
            if (!u?.Id || seen.has(u.Id)) continue;
            seen.add(u.Id);
            const portraitKey = configIdToPortrait(u.Id);
            if (!portraitKey) continue;
            state.configUnits.push({
                id: u.Id,
                faction: u.Faction ?? null,
                level: u.Level ?? null,
                rarity: u.Rarity ?? null,
                portraitKey,
            });
        }
        renderConfigPredefinedUnits();
        loadBoard();
        renderPlacements();
        renderUnitRoster();
        status("ready: " + meta.mode
             + " — " + state.configUnits.length + " units in pool");
    } catch (e) {
        status("config fetch failed: " + e.message);
    }
}
