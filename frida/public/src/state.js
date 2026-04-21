// Global mutable state singleton + placement persistence.
//
// Kept as a plain object (not a class) because modules read and mutate
// fields directly — no ceremony. Mutations are synchronous, followed by an
// explicit `renderX()` call from the caller. Future migration to a reactive
// model (Preact signals) would replace direct mutation with signal writes.

const LS_KEY = "tacticus.placementsByConfig.v1";
const LS_LAST_CONFIG = "tacticus.lastConfigId.v1";

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
};

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
