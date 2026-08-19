// MachinesOfWar event builder — UI counterpart of mow-builder.ts (agent).
//
// Catalog source: /meta/<version>/mow-catalog.json (cached per game version,
// refreshed manually via the ↻ button — same pattern as the campaign
// builder). Each click on a (tier, battle) cell POSTs /api/mow/build →
// hydrateConfig with the inline JSON.
//
// Disabled state: build path needs a live MachinesOfWarEventGameModeSource
// on the agent. Catalog only needs the IMachinesOfWarEventProgression
// singleton (Zenject-bound, available from boot).

import { state, saveLastConfigId } from "./state.js";
import { $, status, updateViewMode } from "./dom.js";
import { api } from "./api.js";
import { hydrateConfig } from "./configs.js";
import { renderRunnerList } from "./runners.js";
import { registerWsHandler } from "./ws.js";

let lastVersion = null;
let catalog = null;       // { tiers: [{tier, rarity, battles: [...]}] }
let lastStatus = null;    // { session, hasProgression, hasInstance }

// Tacticus rarity → display label. Best-effort; falls back to raw int.
const RARITY_NAMES = {
    0: "Common",
    1: "Uncommon",
    2: "Rare",
    3: "Epic",
    4: "Legendary",
    5: "Mythic",
};

function renderCatalog() {
    const root = $("mow-builder-list");
    if (!root) return;
    if (!catalog) {
        const s = lastStatus;
        let hint;
        if (!s || !s.session) {
            hint = "host has no live Frida session · inject hooks first";
        } else if (!s.hasProgression) {
            hint = "waiting for MachinesOfWarEventProgression (boot DI) — should be ready in seconds…";
        } else {
            hint = "no catalog yet · click ↻ to refresh";
        }
        root.innerHTML = '<div class="cb-empty">— ' + hint + "</div>";
        return;
    }
    const tiers = Array.isArray(catalog.tiers) ? catalog.tiers : [];
    if (tiers.length === 0) {
        const msg = catalog.noActiveEvent
            ? "no active Machines of War event in Tacticus right now · catalog will populate when an event becomes live"
            : "no tiers in catalog";
        root.innerHTML = '<div class="cb-empty">— ' + msg + "</div>";
        return;
    }
    const sections = tiers.map((t) => {
        const rarityLbl = RARITY_NAMES[t.rarity] ?? ("R" + t.rarity);
        const battles = Array.isArray(t.battles) ? t.battles : [];
        const cells = battles.map((b) => {
            const key = t.tier + "|" + b.battleIndex;
            const label = String(b.battleIndex + 1);
            const tip = `${b.boardId ?? "?"} · enemies: ${
                Array.isArray(b.enemies) ? b.enemies.length : "?"
            }${b.enemyMow ? " + MoW " + b.enemyMow : ""}`;
            return `<button class="cb-node node--pending" data-key="${key}" `
                + `title="${tip}">${label}</button>`;
        }).join("");
        return `
          <div class="cb-campaign" data-tier="${t.tier}">
            <div class="cb-campaign__head">
              <span class="cb-campaign__name">Tier ${t.tier + 1}</span>
              <span class="cb-campaign__faction">${rarityLbl}</span>
              <span class="cb-campaign__count">${battles.length} battles</span>
            </div>
            <div class="cb-campaign__grid">${cells}</div>
          </div>
        `;
    });
    root.innerHTML = `
      <div class="cb-type">
        <h3 class="cb-type__head">MACHINES OF WAR</h3>
        ${sections.join("")}
      </div>
    `;

    root.querySelectorAll(".cb-node").forEach((btn) => {
        btn.addEventListener("click", () => onNodeClick(btn.dataset.key));
    });
}

async function onNodeClick(key) {
    const [tierStr, battleStr] = key.split("|");
    const tier = Number(tierStr);
    const battle = Number(battleStr);
    if (!Number.isFinite(tier) || !Number.isFinite(battle)) return;

    const root = $("mow-builder-list");
    root?.querySelectorAll(".cb-node.node--selected")
        .forEach((el) => el.classList.remove("node--selected"));
    const btn = root?.querySelector('.cb-node[data-key="' + key + '"]');
    if (btn) {
        btn.disabled = true;
        btn.classList.remove("node--pending", "node--error");
        btn.classList.add("node--building", "node--selected");
    }
    status("building MoW T" + (tier + 1) + " · battle " + (battle + 1) + "…");
    try {
        const r = await api.mow.build(tier, battle);
        const config = JSON.parse(r.json);
        const meta = {
            id: r.id,
            mode: "MachinesOfWarEvent",
            kind: "generated",
            tier, battle,
            inlineJson: r.json,
        };
        state.selected = meta;
        saveLastConfigId(meta.id);
        state.placements = state.placementsByConfig[meta.id] ?? [];
        state.runnerId = null;
        state.tileIdToCoord.clear();
        state.eventUnits.clear();
        updateViewMode();
        renderRunnerList();
        hydrateConfig(meta, config);
    } catch (e) {
        status("build failed: " + e.message);
        if (btn) btn.classList.add("node--error");
    } finally {
        if (btn) btn.disabled = false;
        if (btn) btn.classList.remove("node--building");
    }
}

async function refresh(forceAgentRefresh = false) {
    const refreshBtn = $("mow-builder-refresh");
    if (refreshBtn) refreshBtn.disabled = true;
    try {
        if (forceAgentRefresh) {
            try {
                await api.mow.refreshCatalog();
            } catch (e) {
                console.warn("[mow] refresh failed: " + e.message);
                status("MoW catalog refresh failed: " + e.message);
            }
        }
        if (!lastVersion) {
            const adm = await api.adminStatus();
            lastVersion = adm?.version ?? adm?.session?.version ?? null;
        }
        if (lastVersion) {
            catalog = await api.mow.fetchCatalog(lastVersion);
        }
        renderCatalog();
    } finally {
        if (refreshBtn) refreshBtn.disabled = false;
    }
}

export async function initMoWBuilder(activeVersion) {
    lastVersion = activeVersion ?? null;
    const refreshBtn = $("mow-builder-refresh");
    if (refreshBtn) refreshBtn.addEventListener("click", () => refresh(true));
    // First load: cached catalog only, no agent call.
    await refresh(false);

    // Push-based readiness signal: agent emits `mow_builder_ready` when it
    // captures either the source or the progression for the first time.
    let readyConsumed = false;
    registerWsHandler("mow_builder_ready", async (payload) => {
        if (readyConsumed) return;
        readyConsumed = true;
        status("MoW amorce detected (" + (payload?.via ?? "?")
            + ") — refreshing catalog…");
        try {
            await refresh(true);
            status("MoW builder ready");
        } catch (e) {
            status("MoW catalog refresh failed: " + e.message);
            readyConsumed = false;
        }
    });

    // Light polling (10s) — picks up the rising edge of hasProgression
    // when boot DI settles, and triggers the first auto-refresh.
    let prev = null;
    setInterval(async () => {
        try {
            const s = await api.mow.builderStatus();
            lastStatus = s;
            const justGotProg = s.hasProgression
                && (!prev || !prev.hasProgression);
            if (justGotProg || (s.hasProgression && !catalog)) {
                refresh(true).catch(() => {});
            }
            if (!catalog) renderCatalog();
            prev = s;
        } catch { /* network/host blip — silent */ }
    }, 10000);
}
