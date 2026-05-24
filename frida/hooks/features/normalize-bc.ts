// RPC wiring for the BC normalization feature family.
//
// Active RPCs registered here :
//   - buildNormalizedBC(args)  — JSON in, JSON out, no IL2CPP mutation
//                                except read-only formula invoke
//   - dumpItemsCatalog(args?)  — items catalog inspection
//   - previewBis(args)         — Best-In-Slot preview without runner build
//
// Plus debug RPCs registered via `registerDebugRpcs(ctx)`.
//
// The legacy `normalizeBcAndBuildRunner` / `_normalizeLiveTemplates` path
// (which mutated `_currentBattle.Units` in place via writeTemplateStats)
// was removed — RL pipeline uses only the JSON-isolated flow.
//
// Sibling modules:
//   ./normalize-bc/formula.ts        — IStatsFormula direct call + synthetic ItemModel
//   ./normalize-bc/live-bc.ts        — minimal BC offsets + getLiveBC for debug
//   ./normalize-bc/items-catalog.ts  — gameConfig.items walker + BiS picker
//   ./normalize-bc/json-build.ts     — buildNormalizedBC (JSON-only flow)
//   ./normalize-bc/debug-rpcs.ts     — probe / passive trap / inspection RPCs

import { queueOnMainThread } from "../runtime/queue.js";
import { Ctx } from "../controller.js";

import {
    buildItemCatalog, getCachedCatalog, buildBisItemSpecs,
    ITEM_TYPE_NAMES, ITEM_RARITY_NAMES,
} from "./normalize-bc/items-catalog.js";
import {
    buildNormalizedBC, NormalizeBcArgs,
} from "./normalize-bc/json-build.js";
import { registerDebugRpcs } from "./normalize-bc/debug-rpcs.js";

export function register(ctx: Ctx): void {
    ctx.rpc.buildNormalizedBC = (args: NormalizeBcArgs) =>
        queueOnMainThread(() => buildNormalizedBC(args));

    registerDebugRpcs(ctx);

    /** Build and return the items catalog (one-shot, then cached). Useful
     *  for inspection / debugging the BiS picker. */
    ctx.rpc.dumpItemsCatalog = (args?: { sample?: number }) =>
        queueOnMainThread(() => {
            const res = buildItemCatalog();
            const cat = getCachedCatalog();
            if (!res.ok || !cat) return res;
            const sample = args?.sample ?? 10;
            return {
                ok: true, count: cat.length,
                byItemType: cat.reduce<Record<string, number>>(
                    (acc, it) => {
                        const k = ITEM_TYPE_NAMES[it.itemType] ?? String(it.itemType);
                        acc[k] = (acc[k] ?? 0) + 1; return acc;
                    }, {}),
                byRarity: cat.reduce<Record<string, number>>(
                    (acc, it) => {
                        const k = ITEM_RARITY_NAMES[it.rarity] ?? String(it.rarity);
                        acc[k] = (acc[k] ?? 0) + 1; return acc;
                    }, {}),
                sample: cat.slice(0, sample),
            };
        });

    /** Compute BiS itemSpecs for a list of units without building a runner. */
    ctx.rpc.previewBis = (args: {
        units: Array<{ unitId: string; faction: string }>;
        rarityCap?: number;
        excludeRelics?: boolean;
    }) => queueOnMainThread(() => buildBisItemSpecs(args));
}
