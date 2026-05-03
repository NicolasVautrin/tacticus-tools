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

// Map game-internal campaign ids to readable labels for the archive panel.
// Standard campaigns get their proper name (Indomitus, Octarius, ...) when
// known. Events fall back to a derived label using the id parts.
const CAMPAIGN_PRETTY = {
    campaign1:  "Indomitus",
    campaign2:  "Octarius",
    campaign3:  "Saim-Hann",
    campaign4:  "Fall of Cadia",
    campaign5:  "Tyranid Hive Wars",
    mirror1:    "Indomitus · Mirror",
    mirror2:    "Octarius · Mirror",
    mirror3:    "Saim-Hann · Mirror",
    mirror4:    "Fall of Cadia · Mirror",
    elite1:     "Indomitus · Elite",
    elite2:     "Octarius · Elite",
    elite3:     "Saim-Hann · Elite",
    elite4:     "Fall of Cadia · Elite",
};

function prettyCampaignLabel(campaignId, locationIndex) {
    if (!campaignId) return null;
    let name = CAMPAIGN_PRETTY[campaignId];
    if (!name) {
        // Event ids: eventStandardN / eventExtremisN
        const m = /^event(Standard|Extremis)(\d+)$/i.exec(campaignId);
        if (m) name = `Event ${m[2]} (${m[1]})`;
        else name = campaignId;
    }
    if (typeof locationIndex === "number" && locationIndex >= 0) {
        return name + " · Battle " + (locationIndex + 1);
    }
    return name;
}

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
        // Heading: pretty-print campaignId when available, else fall back to
        // mode + board id. campaignId+locationIndex give precise identity.
        const pretty = prettyCampaignLabel(cfg.campaignId, cfg.locationIndex);
        const headLeft = pretty
            ? pretty + (cfg.board
                ? ' <span class="archive-row__board">' + cfg.board + '</span>'
                : "")
            : (cfg.board
                ? mode + ' · <span class="archive-row__board">' + cfg.board + '</span>'
                : mode);
        li.innerHTML =
            '<span class="archive-row__marker"></span>'
          + '<div class="archive-row__body">'
          + '<div class="archive-row__mode">' + headLeft + '</div>'
          + '<div class="archive-row__meta">'
          +   '<span>' + t + '</span>'
          +   '<span>·</span>'
          +   '<span>' + kb + ' KB</span>'
          + '</div>'
          + '</div>'
          + '<button class="archive-row__delete" title="delete capture"'
          +   ' data-id="' + cfg.id + '">✕</button>';
        // Click on the row body → select. Click on ✕ → delete.
        li.addEventListener("click", (e) => {
            if (e.target instanceof Element
                && e.target.closest(".archive-row__delete")) return;
            selectConfig(cfg);
        });
        const delBtn = li.querySelector(".archive-row__delete");
        delBtn?.addEventListener("click", async (e) => {
            e.stopPropagation();
            if (!confirm("Delete capture " + cfg.id + " ?")) return;
            try {
                await api.deleteConfig(cfg.id);
                if (state.selected?.id === cfg.id) {
                    state.selected = null;
                    state.config = null;
                    saveLastConfigId(null);
                }
                await refreshConfigs();
                status("deleted " + cfg.id);
            } catch (err) {
                status("delete failed: " + err.message);
            }
        });
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
        const config = await api.config(meta.id);
        hydrateConfig(meta, config);
    } catch (e) {
        status("config fetch failed: " + e.message);
    }
}

// Common post-fetch pipeline shared between captures (selectConfig) and
// generated configs (campaign builder). Mutates state, repaints the board /
// placements / roster. Caller is responsible for `state.selected`,
// `saveLastConfigId`, and the runner/tile/eventUnits reset — that part
// differs between flows (e.g. the builder may want a different status text).
export function hydrateConfig(meta, config) {
    state.config = config;
    const seen = new Set();
    state.configUnits = [];
    for (const u of config.Units ?? []) {
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
    status("ready: " + (meta.mode ?? meta.kind ?? "config")
         + " — " + state.configUnits.length + " units in pool");
}
