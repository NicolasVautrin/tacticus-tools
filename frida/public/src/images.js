// Resolve a config unit id (e.g. "adeptHospitaller", "eldarMauganRa") to a
// manifest portrait key ("adept_hospitaller_01" / "aelda_maugan_01").
//
// Primary source: state.assetMap dumped from IdunVisuals._unitConfigMap
// (game-authoritative). The map has known sloppy entries that don't
// match the actual extracted PNG names — we apply a chain of fuzzy
// transformations + a handful of hard aliases to bridge the gap.
//
// Note: campaign-specific variants like "eldarBossMauganRaCamp" are NOT in
// the asset map (the game embeds their VisualId inline in the
// BattleConfiguration — see renderConfigPredefinedUnits).

import { state } from "./state.js";

// Known assetNaming → real-PNG-key aliases for cases the auto-transform
// chain can't handle (semantic renames like Deathwing → Terminator).
const PORTRAIT_ALIASES = {
    "darka_deathwing_01": "darka_terminator_01",
    "necro_scarabswarm_01": "necro_scarab_01",
};

// Words that the game map sometimes glues to the previous segment without
// a separator (e.g. "podcommon" instead of "pod_common"). When detected
// at the tail of an asset name, we try splitting on them.
const SPLIT_TAIL_WORDS = [
    "uncommon", "common", "rare", "epic", "legendary", "mythic",
    "ability", "shield",
];

function buildCandidates(asset) {
    const out = new Set();
    if (!asset) return out;
    const clean = asset.trim();
    const lc = clean.toLowerCase();
    const versionSuffixes = ["", "_01", "_01_premium"];

    const enqueueWithSuffixes = (base) => {
        for (const s of versionSuffixes) out.add(base + s);
    };

    enqueueWithSuffixes(clean);
    enqueueWithSuffixes(lc);

    // Aliases (looked up post-trim, raw assetNaming).
    if (PORTRAIT_ALIASES[clean]) enqueueWithSuffixes(PORTRAIT_ALIASES[clean]);
    if (PORTRAIT_ALIASES[lc])    enqueueWithSuffixes(PORTRAIT_ALIASES[lc]);

    // Drop "s" before the (optional) version suffix — covers
    // "death_nurglings_01" ↔ "death_nurgling_01".
    const sing = clean.replace(/s(_\d+(?:_premium)?)?$/, "$1");
    if (sing !== clean) {
        enqueueWithSuffixes(sing);
        enqueueWithSuffixes(sing.toLowerCase());
    }

    // Insert "_" before glued tail words — covers
    // "loots_podcommon_01" ↔ "loots_pod_common_01".
    for (const w of SPLIT_TAIL_WORDS) {
        const re = new RegExp(`^(.+?)(${w})((?:_\\d+(?:_premium)?)?)$`, "i");
        const m = lc.match(re);
        if (!m) continue;
        const head = m[1].replace(/_$/, "");
        const split = `${head}_${m[2]}${m[3]}`;
        enqueueWithSuffixes(split);
    }

    return out;
}

// Resolve a unit Rank int (0-based, matches engine RankSprites[rank]) to
// the manifest rank icon URL (e.g. "ranks/gold_03.png"). The manifest's
// `ranks` array is ordered Stone1 → Mythic3 by IdunVisualConfiguration.
export function rankImageUrl(rank) {
    if (!state.manifest || rank == null) return null;
    const ranks = state.manifest.ranks;
    if (!Array.isArray(ranks)) return null;
    const path = ranks[rank];
    return path ? "/assets/" + path : null;
}

export function configIdToPortrait(configId) {
    if (!state.manifest || !configId) return null;
    const known = state.manifest.units;

    // 1) game's authoritative map → fuzzy candidate set
    const asset = state.assetMap?.[configId]?.assetNaming;
    if (asset) {
        for (const c of buildCandidates(asset)) {
            if (known[c]) return c;
        }
    }

    // 2) camelCase → snake_case heuristic on the configId itself
    const snake = configId.replace(/([a-z0-9])([A-Z])/g, "$1_$2").toLowerCase();
    for (const c of buildCandidates(snake)) {
        if (known[c]) return c;
    }
    return null;
}
