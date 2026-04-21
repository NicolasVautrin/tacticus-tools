// Resolve a config unit id (e.g. "adeptHospitaller", "eldarMauganRa") to a
// manifest portrait key ("adept_hospitaller_01" / "aelda_maugan_01").
//
// Primary source: state.assetMap dumped from IdunVisuals._unitConfigMap
// (game-authoritative). Falls back to camelCase→snake_case heuristic if
// the map is not loaded or the entry is missing.
//
// Note: campaign-specific variants like "eldarBossMauganRaCamp" are NOT in
// the asset map (the game embeds their VisualId inline in the
// BattleConfiguration — see renderConfigPredefinedUnits).

import { state } from "./state.js";

export function configIdToPortrait(configId) {
    if (!state.manifest || !configId) return null;
    const asset = state.assetMap?.[configId]?.assetNaming;
    if (asset) {
        if (state.manifest.units[asset]) return asset;
        for (const suffix of ["", "_01", "_01_premium"]) {
            const k = asset + suffix;
            if (state.manifest.units[k]) return k;
        }
    }
    const snake = configId.replace(/([a-z0-9])([A-Z])/g, "$1_$2").toLowerCase();
    for (const k of [snake + "_01", snake, snake + "_01_premium"]) {
        if (state.manifest.units[k]) return k;
    }
    return null;
}
