// Campaign builder UI — renders the static catalog (CampaignType → Campaign
// → Node grid) and triggers on-demand BattleConfiguration generation.
//
// Catalog source: /meta/<version>/campaign-catalog.json (cached per game
// version, refreshed on inject + on the user's manual refresh click).
// Each click on a node POSTs /api/campaigns/build → fetches the generated
// JSON from /assets/<path> → hydrates the existing config view (board +
// placements + roster) via configs.hydrateConfig.
//
// Disabled state: the catalog requires a live CampaignGameModeSource on the
// agent side (the user must have opened the campaign view in-game at least
// once during the current session). We poll /api/campaigns/builder-status
// alongside admin status; while !hasInstance, the panel shows a hint.

import { state, saveLastConfigId } from "./state.js";
import { $, status, updateViewMode } from "./dom.js";
import { api } from "./api.js";
import { hydrateConfig } from "./configs.js";
import { renderRunnerList } from "./runners.js";
import { registerWsHandler } from "./ws.js";

let lastVersion = null;
let catalog = null;
let campaignTypeNames = null;  // { 0: "Standard", 1: "Mirror", ... }
let builtCache = new Map();    // "<type>/<id>/<idx>" → { path, generatedAt }

// I18N lookup: "Indomitus" / "Fall of Cadia" / etc. Populated lazily via
// the active version's i18n bundle (already synced in meta-sync).
let i18n = null;

async function loadI18n(version) {
    try {
        const r = await fetch("/meta/" + encodeURIComponent(version) + "/i18n/en.json");
        if (!r.ok) return null;
        return await r.json();
    } catch { return null; }
}

async function loadEnums() {
    try {
        const r = await fetch("/assets/enums.json");
        if (!r.ok) return null;
        const e = await r.json();
        return e?.CampaignType?.values ?? null;
    } catch { return null; }
}

function campaignDisplayName(typeName, campaignId) {
    // i18n keys observed:
    //   Campaigns/Standard_campaign1_name      → "Indomitus"
    //   Campaigns/Mirror_mirror1_name          → "..."
    //   Campaigns/Elite_elite1_name            → "..."
    //   Campaigns/EliteMirror_eliteMirror1_name → "..."
    if (!i18n) return campaignId;
    const candidates = [
        "Campaigns/" + typeName + "_" + campaignId + "_name",
        "Campaigns/" + campaignId + "_name",
        "Campaigns/" + campaignId,
    ];
    for (const k of candidates) {
        if (i18n[k]) return i18n[k];
    }
    return campaignId;
}

// Unit-id prefix → readable faction name. Used both to label events
// (which lack proper i18n names) and to colour the per-campaign chip.
const FACTION_PREFIXES = {
    astra: "Astra Militarum",
    tyran: "Tyranids",
    necro: "Necrons",
    aelda: "Aeldari",
    orks:  "Orks",
    chaos: "Chaos",
    tau:   "T'au",
    black: "Black Templars",
    blood: "Blood Angels",
    dark:  "Dark Angels",
    death: "Death Guard",
    space: "Space Marines",
    sons:  "Thousand Sons",
    sister:"Adepta Sororitas",
    sisters:"Adepta Sororitas",
    custodes:"Adeptus Custodes",
    mech:  "Mechanicus",
    ad:    "Mechanicus",
    eldar: "Aeldari",
    krieg: "Death Korps",
    nephilim:"Aeldari",
    drukhari:"Drukhari",
    genestealer:"Genestealers",
    nurgle:"Death Guard",
    slaanesh:"Slaanesh",
};

function inferEnemyFaction(units) {
    // units is List<List<string>> in the dump. First unit prefix gives a
    // good hint of the enemy faction (necro… aelda… orks… black… etc.).
    // Strip "Npc<N>" / digits / camelCase suffix to keep just the faction
    // root (astraNpc1Guardsman → astra; tyranNpc2Hormagaunt → tyran).
    if (!Array.isArray(units) || units.length === 0) return null;
    const first = Array.isArray(units[0]) ? units[0][0] : null;
    if (!first) return null;
    const m = first.match(/^([a-z]+?)(?:Npc|[A-Z0-9])/);
    return m ? m[1] : null;
}

function factionDisplay(prefix) {
    if (!prefix) return null;
    return FACTION_PREFIXES[prefix.toLowerCase()] ?? prefix;
}

// Derive a readable display name for an Event campaign (catalog id like
// "eventStandard1" / "eventExtremis3"). Result e.g.:
//   "Event 1 — Astra Militarum (Standard)"
function eventDisplayName(campaignId, faction) {
    const m = /^event(Standard|Extremis)(\d+)$/i.exec(campaignId);
    if (!m) return null;
    const variant = m[1];   // Standard | Extremis
    const idx = m[2];
    const fac = factionDisplay(faction);
    return `Event ${idx} — ${fac ?? "?"} (${variant})`;
}

function nodeStateClass(key) {
    if (builtCache.has(key)) return "node--built";
    return "node--pending";
}

// The data-key on each node-button serializes the (campaignType, campaignId,
// locationIndex) triple. Pipe-delimited (campaignId is a regex-safe slug).
function renderNodeBadge(campaignTypeInt, campaignId, locationIndex) {
    const key = campaignTypeInt + "|" + campaignId + "|" + locationIndex;
    const cls = nodeStateClass(key);
    const label = String(locationIndex + 1);  // 1-based for humans
    return `<button class="cb-node ${cls}" data-key="${key}">${label}</button>`;
}

function renderCampaign(campaignTypeInt, typeName, campaignId, campaign) {
    const battles = Array.isArray(campaign?.battles) ? campaign.battles : [];
    const lastPlayable = campaign?.lastPlayableLevel ?? battles.length;
    const enemyFactionRaw = battles.length
        ? inferEnemyFaction(battles[0]?.units) : null;
    // Events lack proper i18n names — derive a readable one from the id +
    // first-battle faction. Other campaign types get their normal name.
    const dispName = (typeName === "Event"
        ? eventDisplayName(campaignId, enemyFactionRaw)
        : null)
        ?? campaignDisplayName(typeName, campaignId);
    const factionLabel = factionDisplay(enemyFactionRaw);
    const cells = battles.map((_, i) =>
        renderNodeBadge(campaignTypeInt, campaignId, i)).join("");

    return `
      <div class="cb-campaign" data-type="${campaignTypeInt}" data-id="${campaignId}">
        <div class="cb-campaign__head">
          <span class="cb-campaign__name">${dispName}</span>
          ${factionLabel && typeName !== "Event"
            ? `<span class="cb-campaign__faction">${factionLabel}</span>` : ""}
          <span class="cb-campaign__count">${battles.length} nodes${
              lastPlayable < battles.length ? ` · playable up to ${lastPlayable}` : ""
          }</span>
        </div>
        <div class="cb-campaign__grid">${cells}</div>
      </div>
    `;
}

let lastBuilderStatus = null;  // { session, hasGameConfig, hasInstance }

function renderCatalog() {
    const root = $("campaign-builder-list");
    if (!root) return;
    if (!catalog) {
        const s = lastBuilderStatus;
        let hint;
        if (!s || !s.session) {
            hint = "host has no live Frida session · inject hooks first";
        } else if (!s.hasGameConfig) {
            hint = "waiting for game to load (UserProgression ctor) — should be ready in seconds…";
        } else {
            hint = "no catalog yet · click ↻ to refresh";
        }
        root.innerHTML = '<div class="cb-empty">— ' + hint + "</div>";
        return;
    }
    const typeKeys = Object.keys(catalog);
    if (typeKeys.length === 0) {
        root.innerHTML = '<div class="cb-empty">— catalog is empty</div>';
        return;
    }
    // Game serialises CampaignsConfigDto as { CampaignTypeName: [CampaignBattlesConfig...] }.
    // The outer key is the CampaignType *name* (Standard/Mirror/Elite/EliteMirror/Event).
    // The inner is an Array — each element has .id (campaign id like "campaign1"),
    // .lastPlayableLevel, .battles (List<CampaignConfigDto>).
    // The CampaignType *int* (used in the build RPC) is reverse-looked-up
    // from `enums.json` (CampaignType.values is { "0": "Standard", ... }).
    const nameToInt = {};
    if (campaignTypeNames) {
        for (const [n, name] of Object.entries(campaignTypeNames)) {
            nameToInt[name] = Number(n);
        }
    }
    const sections = typeKeys.map((typeName) => {
        const list = Array.isArray(catalog[typeName]) ? catalog[typeName] : [];
        const typeInt = nameToInt[typeName];
        if (typeInt === undefined) {
            return `<div class="cb-type">
                <h3 class="cb-type__head">${typeName.toUpperCase()}</h3>
                <div class="cb-empty">— unknown CampaignType "${typeName}" (enums.json out of date?)</div>
            </div>`;
        }
        const campaigns = list
            .map((c) => renderCampaign(typeInt, typeName, c?.id ?? "?", c))
            .join("");
        return `
          <div class="cb-type">
            <h3 class="cb-type__head">${typeName.toUpperCase()}</h3>
            ${campaigns || '<div class="cb-empty">— no campaigns</div>'}
          </div>
        `;
    });
    root.innerHTML = sections.join("");

    root.querySelectorAll(".cb-node").forEach((btn) => {
        btn.addEventListener("click", () => onNodeClick(btn.dataset.key));
    });

    // Wire collapse on per-type (STANDARD/EVENT/...) and per-campaign
    // (INDOMITUS/...) headers. Persisted to localStorage so the user's
    // layout survives reloads + catalog refreshes.
    wireCollapsibleSections(root);
}

const COLLAPSE_PREFIX = "cb-collapsed:";
function wireCollapsibleSections(root) {
    // Per-type sections (STANDARD, EVENT, MIRROR, ...).
    root.querySelectorAll(".cb-type").forEach((section) => {
        const head = section.querySelector(".cb-type__head");
        if (!head) return;
        const name = head.textContent.trim();
        const key = COLLAPSE_PREFIX + "type:" + name;
        if (localStorage.getItem(key) === "1") {
            section.classList.add("cb-type--collapsed");
        }
        head.addEventListener("click", () => {
            const collapsed = !section.classList.contains("cb-type--collapsed");
            section.classList.toggle("cb-type--collapsed", collapsed);
            try {
                if (collapsed) localStorage.setItem(key, "1");
                else localStorage.removeItem(key);
            } catch { /* private mode */ }
        });
    });
    // Per-campaign sections (INDOMITUS, EVENTSTANDARD1, ...).
    root.querySelectorAll(".cb-campaign").forEach((section) => {
        const head = section.querySelector(".cb-campaign__head");
        if (!head) return;
        const id = section.dataset.id ?? "?";
        const type = section.dataset.type ?? "?";
        const key = COLLAPSE_PREFIX + "campaign:" + type + ":" + id;
        if (localStorage.getItem(key) === "1") {
            section.classList.add("cb-campaign--collapsed");
        }
        head.addEventListener("click", () => {
            const collapsed = !section.classList.contains("cb-campaign--collapsed");
            section.classList.toggle("cb-campaign--collapsed", collapsed);
            try {
                if (collapsed) localStorage.setItem(key, "1");
                else localStorage.removeItem(key);
            } catch { /* private mode */ }
        });
    });
}

async function onNodeClick(key) {
    const [typeKeyStr, campaignId, idxStr] = key.split("|");
    const campaignType = Number(typeKeyStr);
    const locationIndex = Number(idxStr);
    if (!Number.isFinite(campaignType) || !Number.isFinite(locationIndex)) return;

    const root = $("campaign-builder-list");
    const btn = root?.querySelector('.cb-node[data-key="' + key + '"]');
    if (btn) {
        btn.disabled = true;
        btn.classList.remove("node--pending", "node--built", "node--error");
        btn.classList.add("node--building");
    }
    status("building " + campaignId + " · node " + (locationIndex + 1) + "…");
    try {
        let built = builtCache.get(key);
        if (!built) {
            const r = await api.campaigns.build(campaignType, campaignId, locationIndex);
            built = { path: r.path, generatedAt: r.generatedAt, id: r.id };
            builtCache.set(key, built);
        }
        const config = await api.campaigns.fetchBuilt(built.path);

        // Reset runner-tied state (same prelude as selectConfig in configs.js).
        const meta = {
            id: built.id,
            mode: "Campaign" + campaignType,
            kind: "generated",
            campaignType, campaignId, locationIndex,
            path: built.path,
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
        if (btn) btn.classList.add("node--built");
    } catch (e) {
        status("build failed: " + e.message);
        if (btn) btn.classList.add("node--error");
    } finally {
        if (btn) btn.disabled = false;
        if (btn) btn.classList.remove("node--building");
    }
}

// Auto-refresh on page load is `false` by default — calling refreshCatalog()
// triggers an agent-side findGameConfigDtoViaHeap heap scan (~10 s) that
// suspends the game's main thread. Tacticus's UnityFreezeDetector then kills
// the process. We use the on-disk catalog cache instead. The user can force
// a full refresh by clicking the ↻ button (which calls refresh(true)).
async function refresh(forceAgentRefresh = false) {
    const refreshBtn = $("campaign-builder-refresh");
    if (refreshBtn) refreshBtn.disabled = true;
    try {
        if (forceAgentRefresh) {
            try {
                await api.campaigns.refreshCatalog();
            } catch (e) {
                console.warn("[cb] refresh failed: " + e.message);
            }
        }
        if (!lastVersion) {
            const adm = await api.adminStatus();
            lastVersion = adm?.version ?? adm?.session?.version ?? null;
        }
        if (lastVersion) {
            catalog = await api.campaigns.fetchCatalog(lastVersion);
        }
        if (!campaignTypeNames) campaignTypeNames = await loadEnums();
        if (!i18n && lastVersion) i18n = await loadI18n(lastVersion);
        renderCatalog();
    } finally {
        if (refreshBtn) refreshBtn.disabled = false;
    }
}

export async function initCampaignBuilder(activeVersion) {
    lastVersion = activeVersion ?? null;
    const refreshBtn = $("campaign-builder-refresh");
    // ↻ button: explicit user action triggers an agent-side dump (heap scan).
    if (refreshBtn) refreshBtn.addEventListener("click", () => refresh(true));
    // First load: cached catalog only, no scan.
    await refresh(false);

    // Push-based warmup signal: agent emits `builder_ready` once
    // CampaignGameModeSource is captured (user clicked a battle in-game).
    // No more polling for hasInstance — the front reacts instantly and
    // triggers a single agent-side refreshCatalog (cheap now: lastSource
    // is captured, no heap scan needed).
    let builderReadyConsumed = false;
    registerWsHandler("builder_ready", async (payload) => {
        if (builderReadyConsumed) return;
        builderReadyConsumed = true;
        status("warmup detected (" + (payload?.via ?? "?")
            + ") — refreshing catalog…");
        try {
            await refresh(true);
            status("builder ready");
        } catch (e) {
            status("catalog refresh failed: " + e.message);
            builderReadyConsumed = false; // allow retry on next signal
        }
    });

    // Keep the panel snappy: when the agent reports GameConfigDto became
    // available (was null, now non-null), re-trigger a catalog refresh
    // automatically. The two readiness flags are independent:
    //   - hasGameConfig → catalog can be dumped (browse works)
    //   - hasInstance   → build can run on a node (click works)
    let prev = null;
    setInterval(async () => {
        try {
            const s = await api.campaigns.builderStatus();
            lastBuilderStatus = s;
            // Trigger refresh on the rising edge of hasGameConfig OR when the
            // catalog is still empty and we just gained the prerequisite.
            const justGotConfig = s.hasGameConfig
                && (!prev || !prev.hasGameConfig);
            if (justGotConfig || (s.hasGameConfig && !catalog)) {
                refresh().catch(() => {});
            }
            // If the panel is in its empty state, refresh the hint to track
            // session/hasGameConfig changes without waiting for a manual click.
            if (!catalog) renderCatalog();
            prev = s;
        } catch { /* network/host blip — silent */ }
    }, 5000);
}
