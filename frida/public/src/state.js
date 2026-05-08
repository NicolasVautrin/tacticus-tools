// Global mutable state singleton + placement persistence.
//
// Kept as a plain object (not a class) because modules read and mutate
// fields directly — no ceremony. Mutations are synchronous, followed by an
// explicit `renderX()` call from the caller. Future migration to a reactive
// model (Preact signals) would replace direct mutation with signal writes.

const LS_KEY = "tacticus.placementsByConfig.v1";
const LS_LAST_CONFIG = "tacticus.lastConfigId.v1";
const LS_VIEW_MODE = "tacticus.viewMode.v1";

function loadViewMode() {
    try {
        const v = localStorage.getItem(LS_VIEW_MODE);
        return v === "mirror" ? "mirror" : "build";
    } catch { return "build"; }
}

function loadPlacementsByConfig() {
    try { return JSON.parse(localStorage.getItem(LS_KEY) ?? "{}"); }
    catch { return {}; }
}

export const state = {
    manifest: null,             // { units, boards, boardVisuals } from /assets
    configs: [],                // captured BattleConfiguration metadata
    selected: null,             // selected capture metadata
    config: null,               // parsed full BattleConfiguration
    boardVisual: null,          // { Width, Height, PlayableMinCol, ... }
    spawnPointsByTile: new Map(),   // `${col},${row}` → { team, playerId }
    placements: [],             // [{ unitId, playerId, col, row }]
    placementsByConfig: loadPlacementsByConfig(),
    selectedUnit: null,         // unitId for next placement
    configUnits: [],            // filtered playable heroes from config.Units
    assetMap: null,             // configId → { unitId, assetNaming }
    tileIdToCoord: new Map(),   // tileId → { col, row }
    eventUnits: new Map(),      // entityId|preN → { col, row, playerId, visualId }
    runners: [],
    runnerId: null,
    sessionId: null,
    ws: null,
    // Deployment constraints (when the loaded config is a campaign battle):
    //   { allowedFactions: ["Sisterhood",...], requiredUnits: [...] }
    // Null when the source isn't a campaign or the catalog isn't loaded.
    constraints: null,
    // { runnerId, winner, stageName, finishedAt } once a battle ends
    // (FinishMatch event observed or stage flipped non-Running). Cleared on
    // resetRunnerSession so re-engage starts fresh.
    battleEnded: null,
    // Mirror state — projected matchState from the isolated mirror runner.
    // When non-null, the central board renders these units (priority over
    // placements / eventUnits). Shape: { turn, playerOnTurn, units: [...] }.
    simState: null,
    // UI mode toggle — explicit user choice, persisted to localStorage.
    // "build" : layout for config-archive exploration + ENGAGE flow.
    // "mirror": layout for live mirroring + AI-on-mirror auto-play.
    // The hook live runs in both modes; mode only changes which panels are
    // visible / where the Mirror panel docks.
    viewMode: loadViewMode(),
};

export function saveViewMode(mode) {
    try { localStorage.setItem(LS_VIEW_MODE, mode); }
    catch (e) { console.warn("saveViewMode", e); }
}

export function savePlacements() {
    if (!state.selected?.id) return;
    state.placementsByConfig[state.selected.id] = state.placements;
    try { localStorage.setItem(LS_KEY, JSON.stringify(state.placementsByConfig)); }
    catch (e) { console.warn("savePlacements", e); }
}

export function saveLastConfigId(id) {
    try { localStorage.setItem(LS_LAST_CONFIG, id ?? ""); }
    catch (e) { console.warn("saveLastConfigId", e); }
}

export function loadLastConfigId() {
    try { return localStorage.getItem(LS_LAST_CONFIG) || null; }
    catch { return null; }
}
