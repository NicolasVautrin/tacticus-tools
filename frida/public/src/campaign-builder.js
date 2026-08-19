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
    mech:  "Adeptus Mechanicus",
    ad:    "Adeptus Mechanicus",
    admec: "Adeptus Mechanicus",
    adept: "Adepta Sororitas",
    eldar: "Aeldari",
    krieg: "Death Korps",
    nephilim:"Aeldari",
    drukhari:"Drukhari",
    genes: "Genestealers",
    genestealer:"Genestealers",
    nurgle:"Death Guard",
    slaanesh:"Slaanesh",
    ultra: "Ultramarines",
    world: "World Eaters",
    templ: "Black Templars",
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

/** Resolve a campaignId (e.g. "eventStandard2") to its display faction
 *  via the loaded catalog. Returns the localized faction name (e.g.
 *  "Tyranids") or null when the catalog isn't loaded yet / unknown id.
 *  Used by the archive list to surface the faction instead of the raw
 *  event index. */
export function getCampaignFactionLabel(campaignId) {
    if (!catalog || !campaignId) return null;
    for (const tier of Object.values(catalog)) {
        if (!Array.isArray(tier)) continue;
        const c = tier.find((x) => x?.id === campaignId);
        if (c) return eventDominantFaction(c);
    }
    return null;
}

/** Deployment constraints for a (campaignId, locationIndex) pair, sourced
 *  from the campaign catalog:
 *    - allowedFactions : factions the player may deploy from (campaign-
 *      level — set in `unlockConditions.requiredUnits.allowedFactions`)
 *    - requiredUnits   : unit ids the player MUST include in this battle
 *      (battle-level — `battles[].requiredUnits`)
 *  Returns null when the catalog is not loaded or the campaign is unknown.
 *  An empty `allowedFactions` array means "no faction restriction" — the
 *  caller should treat that as "any faction allowed". */
export function getCampaignConstraints(campaignId, locationIndex) {
    if (!catalog || !campaignId) return null;
    for (const tier of Object.values(catalog)) {
        if (!Array.isArray(tier)) continue;
        const c = tier.find((x) => x?.id === campaignId);
        if (!c) continue;
        const allowedFactions = c.unlockConditions?.requiredUnits
            ?.allowedFactions ?? [];
        const battles = Array.isArray(c.battles) ? c.battles : [];
        const battle = (typeof locationIndex === "number")
            ? (battles[locationIndex] ?? null)
            : null;
        const requiredUnits = Array.isArray(battle?.requiredUnits)
            ? battle.requiredUnits : [];
        return { allowedFactions, requiredUnits };
    }
    return null;
}

function factionDisplay(prefix) {
    if (!prefix) return null;
    return FACTION_PREFIXES[prefix.toLowerCase()] ?? prefix;
}

/** Dominant enemy faction across an event's battles. Each battle
 *  contributes its first unit's faction prefix; we tally and pick the
 *  most-frequent. Tacticus events typically have 1 main enemy (~25-33/33
 *  battles) plus a few "guest" battles with other factions — the user
 *  thinks of the event by the dominant faction, not the minority guests. */
function eventDominantFaction(campaign) {
    const battles = Array.isArray(campaign?.battles) ? campaign.battles : [];
    const counts = new Map();
    for (const b of battles) {
        const units = Array.isArray(b?.units) ? b.units : [];
        const first = Array.isArray(units[0]) ? units[0][0] : null;
        if (!first) continue;
        const m = first.match(/^([a-z]+?)(?:Npc|[A-Z0-9])/);
        if (!m) continue;
        counts.set(m[1], (counts.get(m[1]) ?? 0) + 1);
    }
    let bestPrefix = null, bestN = 0;
    for (const [pfx, n] of counts) {
        if (n > bestN) { bestPrefix = pfx; bestN = n; }
    }
    return bestPrefix ? factionDisplay(bestPrefix) : null;
}

// Derive a readable display name for an Event campaign (catalog id like
// "eventStandard1" / "eventExtremis3"). Result e.g.:
//   "Tyranids (Standard)" / "T'au (Extremis)"
function eventDisplayName(campaign) {
    const id = campaign?.id ?? "";
    const m = /^event(Standard|Extremis)\d+$/i.exec(id);
    if (!m) return null;
    const faction = eventDominantFaction(campaign);
    return `${faction ?? "?"} (${m[1]})`;
}

// The data-key on each node-button serializes the (campaignType, campaignId,
// locationIndex) triple. Pipe-delimited (campaignId is a regex-safe slug).
function renderNodeBadge(campaignTypeInt, campaignId, locationIndex) {
    const key = campaignTypeInt + "|" + campaignId + "|" + locationIndex;
    const label = String(locationIndex + 1);  // 1-based for humans
    return `<button class="cb-node node--pending" data-key="${key}">${label}</button>`;
}

function renderCampaign(campaignTypeInt, typeName, campaignId, campaign) {
    const battles = Array.isArray(campaign?.battles) ? campaign.battles : [];
    const lastPlayable = campaign?.lastPlayableLevel ?? battles.length;
    const enemyFactionRaw = battles.length
        ? inferEnemyFaction(battles[0]?.units) : null;
    // Events lack proper i18n names — derive a readable one from the id +
    // first-battle faction. Other campaign types get their normal name.
    const dispName = (typeName === "Event"
        ? eventDisplayName(campaign)
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
    // Single-selection: clear the highlight on whichever node was last
    // active so only the just-clicked one stays lit.
    root?.querySelectorAll(".cb-node.node--selected")
        .forEach((el) => el.classList.remove("node--selected"));
    const btn = root?.querySelector('.cb-node[data-key="' + key + '"]');
    if (btn) {
        btn.disabled = true;
        btn.classList.remove("node--pending", "node--error");
        btn.classList.add("node--building", "node--selected");
    }
    status("building " + campaignId + " · node " + (locationIndex + 1) + "…");
    try {
        const r = await api.campaigns.build(campaignType, campaignId, locationIndex);
        // Inline JSON — host doesn't persist on build anymore. We hold
        // it in state so the engage flow can ship it back at launch
        // time (which is when the archive entry actually gets created).
        const config = JSON.parse(r.json);

        // Reset runner-tied state (same prelude as selectConfig in configs.js).
        const meta = {
            id: r.id,
            mode: "Campaign" + campaignType,
            kind: "generated",
            campaignType, campaignId, locationIndex,
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
        // Other panels (archive list) derive their labels from this
        // catalog. Fire a custom event so they re-render once it lands —
        // avoids a circular import on configs.js.
        if (catalog) {
            window.dispatchEvent(new CustomEvent("tacticus:catalog-loaded"));
        }
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

    // Push-based amorce signal: agent emits `builder_ready` once
    // CampaignGameModeSource is captured (user clicked a battle in-game).
    // No more polling for hasInstance — the front reacts instantly and
    // triggers a single agent-side refreshCatalog (cheap now: lastSource
    // is captured, no heap scan needed).
    let builderReadyConsumed = false;
    registerWsHandler("builder_ready", async (payload) => {
        if (builderReadyConsumed) return;
        builderReadyConsumed = true;
        status("amorce detected (" + (payload?.via ?? "?")
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
