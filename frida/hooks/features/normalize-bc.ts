// `normalizeBcAndBuildRunner` — all-in-one RL entry point.
//
// Captures the live BattleConfiguration (warmed up via mode-source-capture)
// and produces a runner ready for `startBattle` / `playTurn` with:
//   1. every `BC.Units[]` template normalized to (rank/rarity/level/star)
//      via `IStatsFormula.StatsUsingProgressionIndexFor` (cf. ./formula.ts)
//   2. optional Best-In-Slot items from `gameConfig.items` per slot/faction
//      (cf. ./items-catalog.ts) — `autoBis: true`
//   3. a fresh isolated `IdunRunner` (no live UI involvement)
//   4. one `AddUnitMessage` per player unit at auto-picked spawn points
//      (TWPI=0 = single-player human team) — caller can pass strings or
//      explicit `{unitId, playerId, col, row}` overrides
//
// Sibling modules:
//   ./formula.ts        — IStatsFormula direct call + synthetic ItemModel
//   ./live-bc.ts        — BC offsets, spawn points, Human PlayerId, AddUnit
//   ./items-catalog.ts  — gameConfig.items walker + BiS picker
//   ./json-build.ts     — `buildNormalizedBC(...)` offline JSON workflow
//   ./debug-rpcs.ts     — probe / passive trap / inspection RPCs

import { createManagedString, invokeMethod } from "../il2cpp/invoke.js";
import { readIl2cppString } from "../il2cpp/helpers.js";
import { getLastUnitProgression } from "./campaign-builder.js";
import { buildRunner, runnerApplyMi } from "../game/runner.js";
import { registerRunner } from "../game/runner-registry.js";
import { queueOnMainThread } from "../runtime/queue.js";
import { log } from "../runtime/diag.js";
import { Ctx } from "../controller.js";

import {
    resolveFormulaState, ensureEmptyLists, resolveItemModelState,
    createEmptyList, createItemModel, addItemToList,
} from "./normalize-bc/formula.js";
import {
    UC, TWPI_HUMAN_DEFAULT, NormalizedTemplateStats,
    getLiveBC, iterTemplates, writeTemplateStats, writeTemplateProgression,
    readSpawnPointsForTwpi, findHumanPlayerId, buildAddUnitMsg,
} from "./normalize-bc/live-bc.js";
import {
    buildItemCatalog, getCachedCatalog, buildBisItemSpecs,
    ITEM_TYPE_NAMES, ITEM_RARITY_NAMES,
} from "./normalize-bc/items-catalog.js";
import {
    buildNormalizedBC, NormalizeBcArgs,
} from "./normalize-bc/json-build.js";
import { registerDebugRpcs } from "./normalize-bc/debug-rpcs.js";

interface NormalizeAndBuildArgs {
    /** Target Rank tier (1-17). Also used as progressionIndex in the formula. */
    targetRank: number;
    /** 0-5 (Stone..Mythic) — written to template Rarity. */
    targetRarity?: number;
    /** 1-50 — written to template Level. */
    targetLevel?: number;
    /** Written to template StarLevel. */
    targetStarLevel?: number;
    /** Written to Active/Passive/TertiaryAbilityLevel. */
    targetAbilityLevel?: number;
    /** Per-unit synthetic items spec — key = unitId, value = list of
     *  { configId, level? }. Units not in the map use empty list. */
    itemSpecs?: Record<string, Array<{ configId: string; level?: number | null }>>;
    /** Whitelist of unitIds to normalize. If absent, normalize all templates.
     *  Useful to skip MoW/special units that may fail the formula. */
    unitsFilter?: string[];
    /** Player units to spawn after building the runner. Each entry is either:
     *   - a string `"unitId"` → auto-pick playerId + next free spawn point
     *   - an object `{ unitId, [playerId], [col], [row] }` → missing fields
     *     are auto-filled (playerId from FindPlayerConfigByType(Human) or
     *     `humanPlayerId` arg; col/row from the next free spot in the active
     *     SpawnPointSet group with `playerSpawnTwpi`). */
    playerUnits: Array<string | {
        unitId: string; playerId?: number; col?: number; row?: number;
    }>;
    /** Override the human PlayerId resolution. Default: try
     *  PlayersConfiguration.FindPlayerConfigByType(Human), then fall back to 11. */
    humanPlayerId?: number;
    /** Which SpawnPointGroup serves the human (by TeamWithPlayerIndex enum).
     *  Default 0 = (team 1, playerIdx 0) — the single-player human player. */
    playerSpawnTwpi?: number;
    /** When true, auto-pick BiS items per unit from gameConfig.items catalog.
     *  Applied to ALL normalized units (those touched by `unitsFilter`/all
     *  templates). Filter: itemType matches one of unit's lineup itemSlots,
     *  rarity ≤ `targetRarity` (or 5), faction match, unit match, non-relic. */
    autoBis?: boolean;
}

interface NormalizeAndBuildResult {
    ok: boolean;
    err?: string;
    runnerId?: number;
    runner?: string;
    seed?: number;
    bcPtr?: string;
    normalized: Array<{
        unitId: string;
        before: { health: number; damage: number };
        after: NormalizedTemplateStats;
    }>;
    skipped: Array<{ unitId: string; reason: string }>;
    spawned: Array<{
        unitId: string; playerId: number; col: number; row: number;
        ok: boolean; err?: string;
    }>;
    autoBis?: Record<string, Array<{ configId: string; level: number }>>;
}

function _normalizeLiveTemplates(args: NormalizeAndBuildArgs): {
    bc: NativePointer;
    normalized: NormalizeAndBuildResult["normalized"];
    skipped: NormalizeAndBuildResult["skipped"];
    autoBisApplied?: Record<string, Array<{ configId: string; level: number }>>;
} | string {
    const bc = getLiveBC();
    if (!bc) return "no live BattleConfiguration (warmup required)";

    const unitProg = getLastUnitProgression();
    if (!unitProg) return "lastUnitProgression not captured (warmup required)";

    const state = resolveFormulaState(unitProg);
    if (typeof state === "string") return state;
    const listsErr = ensureEmptyLists(state, unitProg, "ultraTigurius");
    if (listsErr) return listsErr;
    const ismErr = resolveItemModelState(state, unitProg);
    if (ismErr) return ismErr;

    const listClass = state.emptyListItems!.readPointer();
    const fn = new NativeFunction(state.statsForMi.ptr, "void", [
        "pointer", "pointer", "pointer", "uchar", "int", "int",
        "pointer", "pointer",
    ]);

    const templates = iterTemplates(bc);
    const filter = args.unitsFilter ? new Set(args.unitsFilter) : null;
    const normalized: NormalizeAndBuildResult["normalized"] = [];
    const skipped: NormalizeAndBuildResult["skipped"] = [];

    // Auto-BiS: build item specs once for the targeted units. Merges with
    // any caller-provided itemSpecs (caller's specs take precedence per-unit).
    let mergedSpecs = args.itemSpecs ?? {};
    let autoBisApplied:
        Record<string, Array<{ configId: string; level: number }>> | undefined;
    if (args.autoBis) {
        const targetUnits: Array<{ unitId: string; faction: string }> = [];
        for (const uc of templates) {
            const id = readIl2cppString(uc.add(UC.ID).readPointer());
            if (!id) continue;
            if (filter && !filter.has(id)) continue;
            const faction = readIl2cppString(uc.add(0x28).readPointer()) ?? "";
            targetUnits.push({ unitId: id, faction });
        }
        const bis = buildBisItemSpecs({
            units: targetUnits,
            rarityCap: args.targetRarity ?? 5,
            excludeRelics: true,
        });
        if (bis.ok) {
            autoBisApplied = {};
            const merged: typeof mergedSpecs = { ...bis.itemSpecs };
            // Caller-provided specs override per-unit.
            for (const [uid, spec] of Object.entries(mergedSpecs)) {
                merged[uid] = spec.map(it => ({
                    configId: it.configId,
                    level: (typeof it.level === "number" && it.level > 0
                        ? it.level : 1) as number,
                }));
            }
            for (const [uid, spec] of Object.entries(bis.itemSpecs)) {
                if (!(uid in (args.itemSpecs ?? {}))) {
                    autoBisApplied[uid] = spec;
                }
            }
            mergedSpecs = merged as typeof mergedSpecs;
            log(`[normalize-bc] autoBis: catalog=${bis.catalogCount}` +
                ` units=${Object.keys(bis.itemSpecs).length}`);
        } else {
            log(`[normalize-bc] autoBis failed: ${bis.err}`);
        }
    }

    for (const uc of templates) {
        const unitId = readIl2cppString(uc.add(UC.ID).readPointer());
        if (!unitId) {
            skipped.push({ unitId: "<no id>", reason: "Id null" });
            continue;
        }
        if (filter && !filter.has(unitId)) continue;

        try {
            // isMOW check
            let isMow = 0;
            const idTmp = createManagedString(unitId);
            const r = invokeMethod(state.isMowMi.info, ptr(0),
                [state.unitsConfig, idTmp]) as NativePointer;
            isMow = r.toInt32() & 1;

            // Items list (fresh per unit). Use merged specs (autoBis ∪ caller).
            const itemsList = createEmptyList(listClass);
            const spec = mergedSpecs[unitId] ?? [];
            for (const it of spec) {
                const item = createItemModel(it.configId, it.level ?? null);
                addItemToList(itemsList, item);
            }

            // Stats output (UnitDynamicStats, 48 bytes)
            const outBuf = Memory.alloc(48);
            for (let i = 0; i < 48; i += 4) outBuf.add(i).writeS32(0);
            const idStr = createManagedString(unitId);
            fn(outBuf, state.statsFormula, idStr, isMow,
               args.targetRank, args.targetRank /* progIdx = rank */,
               state.emptyListInt!, itemsList);

            const before = {
                health: uc.add(UC.HEALTH).readS32(),
                damage: uc.add(UC.DAMAGE).readS32(),
            };
            const after: NormalizedTemplateStats = {
                health: outBuf.add(0x00).readS32(),
                damage: outBuf.add(0x04).readS32(),
                armor: outBuf.add(0x08).readS32(),
                fixedArmor: outBuf.add(0x0c).readS32(),
                critChance: outBuf.add(0x10).readS32(),
                critDamage: outBuf.add(0x14).readS32(),
                blockChance: outBuf.add(0x18).readS32(),
                blockDamage: outBuf.add(0x1c).readS32(),
            };
            writeTemplateStats(uc, after);
            writeTemplateProgression(uc, {
                rank: args.targetRank, rarity: args.targetRarity,
                level: args.targetLevel, starLevel: args.targetStarLevel,
                abilityLevel: args.targetAbilityLevel,
            });
            normalized.push({ unitId, before, after });
        } catch (e) {
            skipped.push({ unitId, reason: (e as Error).message });
        }
    }

    return { bc, normalized, skipped, autoBisApplied };
}


function normalizeBcAndBuildRunner(
    args: NormalizeAndBuildArgs,
): NormalizeAndBuildResult {
    const result: NormalizeAndBuildResult = {
        ok: false, normalized: [], skipped: [], spawned: [],
    };

    if (!Array.isArray(args.playerUnits) || args.playerUnits.length === 0) {
        result.err = "playerUnits required (non-empty array)";
        return result;
    }

    const norm = _normalizeLiveTemplates(args);
    if (typeof norm === "string") { result.err = norm; return result; }
    result.normalized = norm.normalized;
    result.skipped = norm.skipped;
    result.bcPtr = norm.bc.toString();
    if (norm.autoBisApplied) result.autoBis = norm.autoBisApplied;

    // Resolve human playerId + spawn points BEFORE building the runner.
    // playerId precedence per-unit:  unit.playerId > args.humanPlayerId
    //                              > FindPlayerConfigByType(Human) > 11
    // col/row precedence per-unit: unit.col/row > nextSpawnPoint(twpi).
    const twpi = args.playerSpawnTwpi ?? TWPI_HUMAN_DEFAULT;
    const autoSpawnPoints = readSpawnPointsForTwpi(norm.bc, twpi);
    const resolvedHumanPlayerId =
        args.humanPlayerId ?? findHumanPlayerId(norm.bc) ?? 11;

    // Build isolated runner from the (now-mutated) live BC.
    let handle: ReturnType<typeof buildRunner>;
    try {
        handle = buildRunner(norm.bc);
    } catch (e) {
        result.err = "buildRunner failed: " + (e as Error).message;
        return result;
    }
    const entry = registerRunner(handle);
    result.runnerId = entry.runnerId;
    result.runner = handle.runner.toString();
    result.seed = handle.seed;
    log(`[normalize-bc] normalizeBcAndBuildRunner: runnerId=${entry.runnerId}` +
        ` normalized=${result.normalized.length}` +
        ` skipped=${result.skipped.length}` +
        ` humanPlayerId=${resolvedHumanPlayerId}` +
        ` autoSpawnPoints=${autoSpawnPoints.length}`);

    // Spawn player units via AddUnitMessage. Errors per unit don't abort
    // the whole call — the caller can inspect `spawned[i].ok` to decide.
    if (!runnerApplyMi) {
        result.err = "runner.Apply not resolved";
        return result;
    }
    let autoIdx = 0;
    for (const raw of args.playerUnits) {
        const u: { unitId: string; playerId?: number; col?: number; row?: number } =
            typeof raw === "string" ? { unitId: raw } : raw;

        const playerId = u.playerId ?? resolvedHumanPlayerId;
        let col = u.col;
        let row = u.row;
        if (typeof col !== "number" || typeof row !== "number") {
            const sp = autoSpawnPoints[autoIdx++];
            if (!sp) {
                result.spawned.push({
                    unitId: u.unitId, playerId,
                    col: col ?? -1, row: row ?? -1, ok: false,
                    err: `no free spawn point (group TWPI=${twpi} exhausted ` +
                         `after ${autoSpawnPoints.length} slots)`,
                });
                continue;
            }
            col = sp.col;
            row = sp.row;
        }

        const sp: NormalizeAndBuildResult["spawned"][number] = {
            unitId: u.unitId, playerId, col, row, ok: false,
        };
        try {
            const msg = buildAddUnitMsg(u.unitId, playerId, col, row);
            invokeMethod(runnerApplyMi.info, handle.runner, [msg]);
            sp.ok = true;
        } catch (e) {
            sp.err = (e as Error).message;
        }
        result.spawned.push(sp);
    }

    result.ok = result.spawned.every((s) => s.ok);
    return result;
}

// -----------------------------------------------------------------------------

export function register(ctx: Ctx): void {
    ctx.rpc.buildNormalizedBC = (args: NormalizeBcArgs) =>
        queueOnMainThread(() => buildNormalizedBC(args));
    ctx.rpc.normalizeBcAndBuildRunner = (args: NormalizeAndBuildArgs) =>
        queueOnMainThread(() => normalizeBcAndBuildRunner(args));

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
