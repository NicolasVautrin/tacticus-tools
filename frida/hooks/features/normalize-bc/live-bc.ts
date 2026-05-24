// Minimal live BattleConfiguration helpers.
//
// Reduced to what's still consumed after the legacy in-memory BC
// normalization path was removed :
//   - `getLiveBC()` + `BC_OFF_PLAYER`  → debug RPCs (inspection only)
//   - `ARRAY_OFF_DATA`, `LIST_OFF_*`   → shared list-walk constants for
//                                        items-catalog
//
// Everything previously here (writeTemplateStats / writeTemplateProgression
// / iterTemplates / setBoard / readSpawnPointsForTwpi / findHumanPlayerId
// / buildAddUnitMsg / UC offsets / TWPI_HUMAN_DEFAULT / readUnitFaction)
// only served the legacy `_normalizeLiveTemplates` + `normalizeBcAndBuildRunner`
// path, which mutated the live `_currentBattle.Units` in place. The active
// RL pipeline uses `buildNormalizedBC` (json-build.ts), which mutates only
// the JSON-side object — no IL2CPP heap writes — so those helpers became
// dead code and were dropped.

import { getCampaignGameModeSourcePtr } from "../campaign-builder.js";

export const BC_OFF_PLAYER = 0x30;
export const CGMS_OFF_CURRENT_BATTLE = 0x80;
export const LIST_OFF_ITEMS = 0x10;
export const LIST_OFF_SIZE = 0x18;
export const ARRAY_OFF_DATA = 0x20;

export function getLiveBC(): NativePointer | null {
    const src = getCampaignGameModeSourcePtr();
    if (src === null) return null;
    try {
        const bc = src.add(CGMS_OFF_CURRENT_BATTLE).readPointer();
        return bc.isNull() ? null : bc;
    } catch { return null; }
}
