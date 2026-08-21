// JSON workflow — `buildNormalizedBC` ("V2") takes a serialized
// `BattleConfiguration` JSON, recomputes per-unit stats via the validated
// `IStatsFormula.StatsUsingProgressionIndexFor` direct call, and returns a
// new JSON. Used for offline build flows (save → reload a normalized
// config) where the live `_currentBattle` is not the right target.
//
// (V1 — the older `UnitProgression.GetStats(string,int,int)` path — was
// dropped: its "level" parameter was actually a Rarity enum and the helpers
// it called filtered items by player rarity-cap, which made stats depend
// on player state.)

import { createManagedString, invokeMethod } from "../../il2cpp/invoke.js";
import { getUnitProgressionPtr } from "../campaign-builder.js";
import {
    resolveFormulaState, ensureEmptyListClasses, resolveItemModelState,
    createEmptyList, createFreshEmptyLists, createItemModel, addItemToList,
} from "./formula.js";
import { emit } from "../ai-trace/state.js";

let _normalizeCallCount = 0;

export interface NormalizeBcArgs {
    baseBcJson: string;
    boardJson?: string;
    spawnPointSetIndex?: number;
    targetRank: number;             // e.g., 14 (Diamond3)
    targetProgressionIndex: number; // e.g., 14
    targetRarity?: number;          // 0-5 (writes to BC.Units[i].Rarity if set)
    targetLevel?: number;           // 1-50 (writes to BC.Units[i].Level if set)
    targetStarLevel?: number;       // writes to BC.Units[i].StarLevel
    targetAbilityLevel?: number;    // writes to Active/Passive AbilityLevel
    unitsFilter?: string[];
    // Per-unit item specs. Key = unitId. If absent, that unit uses empty list.
    itemSpecs?: Record<string, Array<{ configId: string; level?: number | null }>>;
    /** EXPLICIT stats path — NPC and SUMMON carriers (#419-r1-tr12-r2).
     *
     *  WHY IT EXISTS. Everything below goes through ONE formula,
     *  `IStatsFormula.StatsUsingProgressionIndexFor`, which is the HERO
     *  progression formula. A unit that has no hero progression table
     *  throws inside it, lands in `skipped` ("v2 patch: system error")
     *  and therefore never reaches the `--p-units` pool. That is what
     *  made every npc-only / summon-only carrier unconfrontable except
     *  by GRAFTING its ability onto a pool hero — a graft that covers
     *  neither the stats, nor the traits, nor the weapons of the real
     *  carrier (case-92 §5bis).
     *
     *  The game itself has two OTHER named paths for those carriers:
     *    - npc    `IdunMetaLogic.UserProgress.UnitProgression$$GetNpcStats`
     *             -> `idun.meta.extensions.UnitConfigExtensions$$GetStatsForLevel`,
     *             reading `units.npc[id].stats[]` from the game config;
     *    - summon `IdunMetaLogic.UserProgress.UnitProgression$$GetSummonStats`,
     *             reading the `summon*` variables of the summoning ability.
     *  Both are mirrored offline in `scripts/python/catalog_inject.py`
     *  (`npc_stats` / `summon_stats`) and CONFRONTED there against the
     *  seed BC the game itself produced. So the value written here is
     *  computed by the caller, and this RPC only has to HONOUR it
     *  instead of overwriting or skipping it.
     *
     *  Key = unitId (exact `BC.Units[].Id`, suffix included). Value =
     *  the `UnitConfiguration` fields to write verbatim — the caller
     *  supplies the progression fields too (`Rank`, `StarLevel`,
     *  `Level`, `Active/PassiveAbilityLevel`, …) because for an npc they
     *  come from its own `stats[]` row, NOT from `targetRank` &co. None
     *  of the `target*` arguments is applied to these units: forcing a
     *  hero's rank 17 onto an npc whose row says rank 6 would silently
     *  contradict the very table we just read.
     *
     *  Unknown unitIds are reported in `explicitUnmatched` rather than
     *  ignored: a typo would otherwise degrade into "the formula ran",
     *  i.e. exactly the failure mode this path exists to remove. */
    explicitStats?: Record<string, Record<string, number | null>>;
}

export interface NormalizeBcResult {
    ok: boolean;
    configJson?: string;
    normalized: string[];
    /** Subset of `normalized` whose IsMachineOfWar(UnitsConfigDto, id)
     *  returned true. These units have a separate spawn mechanic
     *  (BC.PredefinedMachines instead of PredefinedUnits) and obey
     *  GameModeSource.SupportsMachinesOfWar. Some modes reject MoW. */
    mow: string[];
    skipped: Array<{ unitId: string; reason: string }>;
    /** Subset of `normalized` whose stats came from `args.explicitStats`
     *  (npc / summon carriers) instead of the hero formula. Callers use
     *  it to assert WHICH path produced a unit's stats — the two regimes
     *  must never be confused for one another. */
    explicit: string[];
    /** Keys of `args.explicitStats` that matched no `BC.Units[].Id`.
     *  Non-empty means the caller asked for a unit that is not in the
     *  catalogue (inject it first) or misspelled its id. */
    explicitUnmatched: string[];
    swappedBoard: string | null;
    err?: string;
}

export function buildNormalizedBC(args: NormalizeBcArgs): NormalizeBcResult {
    const result: NormalizeBcResult = {
        ok: false, normalized: [], mow: [], skipped: [],
        explicit: [], explicitUnmatched: [], swappedBoard: null,
    };

    const unitProg = getUnitProgressionPtr();
    if (!unitProg) {
        result.err = "unitProgressionPtr not captured — amorce required";
        return result;
    }
    const state = resolveFormulaState(unitProg);
    if (typeof state === "string") { result.err = state; return result; }
    const classesErr = ensureEmptyListClasses(state);
    if (classesErr) { result.err = classesErr; return result; }
    const ismErr = resolveItemModelState(state, unitProg);
    if (ismErr) { result.err = ismErr; return result; }

    // Allocate fresh empty Lists for THIS RPC call. We deliberately
    // do NOT cache list instances across calls — Boehm GC collects
    // them silently (no gcRoot) and the recycled heap slot gets used
    // for unrelated allocations, which makes the formula throw a
    // generic "system error" for most units (pool 106→8).
    let freshInt: NativePointer;
    let freshItems: NativePointer;
    try {
        const fresh = createFreshEmptyLists(state);
        freshInt = fresh.listInt;
        freshItems = fresh.listItems;
    } catch (e) {
        result.err = "createFreshEmptyLists: " + (e as Error).message;
        return result;
    }
    _normalizeCallCount++;
    try {
        emit({
            evt: "normalize_bc_call",
            callNo: _normalizeCallCount,
            emptyListInt: freshInt.toString(),
            emptyListItems: freshItems.toString(),
        });
    } catch { /* diagnostic must never throw */ }

    let bc: Record<string, unknown>;
    try {
        bc = JSON.parse(args.baseBcJson) as Record<string, unknown>;
    } catch (e) {
        result.err = "baseBcJson parse: " + (e as Error).message;
        return result;
    }

    // Board swap + SpawnPointSetIndex
    if (args.boardJson) {
        try {
            const board = JSON.parse(args.boardJson);
            bc.Board = board;
            result.swappedBoard = (board as { Id?: string })?.Id ?? "?";
        } catch (e) {
            result.err = "boardJson parse: " + (e as Error).message;
            return result;
        }
    }
    if (typeof args.spawnPointSetIndex === "number") {
        bc.SpawnPointSetIndex = args.spawnPointSetIndex;
    }

    const units = bc.Units as Array<Record<string, unknown>> | undefined;
    if (!Array.isArray(units)) {
        result.err = "BC.Units is not an array";
        return result;
    }

    const filter = args.unitsFilter ? new Set(args.unitsFilter) : null;
    const listItemsKlass = state.emptyListItemsKlass!;
    // `exceptions: "propagate"` -- appel MANAGE, et celui-ci tourne dans la FABRIQUE DE BC,
    // donc a chaque montage. Sans lui, une levee de ce natif serait confisquee et le
    // `try/catch` du jeu ne jouerait pas. Le pourquoi complet est au foyer,
    // `il2cpp/invoke.ts`.
    const fn = new NativeFunction(state.statsForMi.ptr, "void", [
        "pointer", "pointer", "pointer", "uchar", "int", "int",
        "pointer", "pointer",
    ], { exceptions: "propagate" });

    // Diagnostic counters: IsMOW=true detection rate, irrespective of
    // formula success. If `mowAttempted` stays 0 we know IsMOW itself
    // is the issue (wrong _unitsConfig, wrong method, etc.). If it's
    // non-zero but `result.mow` is empty, the formula is rejecting MoW.
    let mowAttempted = 0;
    const mowAttemptedSample: string[] = [];
    const mowSkipped: Array<{ unitId: string; reason: string }> = [];

    for (const u of units) {
        const unitId = u.Id as string | undefined;
        if (!unitId) {
            result.skipped.push({ unitId: "<no Id>", reason: "no Id field" });
            continue;
        }
        if (filter && !filter.has(unitId)) continue;

        // MoW detection: trust the unit's Traits[] (already deserialised
        // by Newtonsoft into JS). The native UnitConfigUtil.IsMachineOfWar
        // method requires the unitId to be a key in _unitsConfig.lineup
        // or .npc — :pvp variants aren't there, so it returns false even
        // for actual MoW. The JSON Traits is the authoritative signal
        // (we verified 9 MoW in the seed BC vs 0 from native IsMOW).
        const traits = (u.Traits as unknown[] | undefined) ?? [];
        const isMow = traits.some((t) => t === "MachineOfWar") ? 1 : 0;
        if (isMow) {
            mowAttempted++;
            if (mowAttemptedSample.length < 10) {
                mowAttemptedSample.push(unitId);
            }
        }

        // EXPLICIT stats path (#419-r1-tr12-r2) — taken BEFORE the hero
        // formula, because for these carriers the formula does not merely
        // return a wrong number, it THROWS. The caller already computed
        // the values by mirroring the game's own npc/summon paths, so all
        // that is left here is to write them and count the unit as
        // normalized. Deliberately no `target*` patching: an npc's rank,
        // star level and ability level are dictated by the `stats[]` row
        // it was read from. The MoW flag is still honoured above — a MoW
        // routed through this path must keep spawning via
        // BC.PredefinedMachines, and silently demoting it to a regular
        // unit would fail at spawn time, not here.
        const explicitFields = args.explicitStats?.[unitId];
        if (explicitFields) {
            for (const k of Object.keys(explicitFields)) {
                u[k] = explicitFields[k];
            }
            if ("RemainingHealth" in u && typeof u.Health === "number") {
                u.RemainingHealth = u.Health;
            }
            result.normalized.push(unitId);
            result.explicit.push(unitId);
            if (isMow) result.mow.push(unitId);
            continue;
        }

        try {
            const idStr = createManagedString(unitId);

            // Build items list (fresh per unit to isolate; not pinned
            // — survives within this synchronous call frame).
            const itemsList = createEmptyList(listItemsKlass);
            const spec = args.itemSpecs?.[unitId] ?? [];
            for (const it of spec) {
                const item = createItemModel(it.configId, it.level ?? null);
                addItemToList(itemsList, item);
            }

            // Call formula
            const outBuf = Memory.alloc(48);
            for (let i = 0; i < 48; i += 4) outBuf.add(i).writeS32(0);
            fn(outBuf, state.statsFormula, idStr, isMow,
               args.targetRank, args.targetProgressionIndex,
               freshInt, itemsList);

            // Overwrite numeric stats
            const b = outBuf;
            u.Health = b.add(0x00).readS32();
            u.Damage = b.add(0x04).readS32();
            u.Armor = b.add(0x08).readS32();
            u.FixedArmor = b.add(0x0c).readS32();
            u.CritChance = b.add(0x10).readS32();
            u.CritDamage = b.add(0x14).readS32();
            u.BlockChance = b.add(0x18).readS32();
            u.BlockDamage = b.add(0x1c).readS32();
            // Reset RemainingHealth so spawned unit starts at full HP
            if ("RemainingHealth" in u) u.RemainingHealth = u.Health;

            // Patch progression metadata if provided
            if (typeof args.targetRarity === "number") u.Rarity = args.targetRarity;
            if (typeof args.targetLevel === "number") u.Level = args.targetLevel;
            u.Rank = args.targetRank;
            if (typeof args.targetStarLevel === "number") u.StarLevel = args.targetStarLevel;
            if (typeof args.targetAbilityLevel === "number") {
                // ActiveAbilityLevel/PassiveAbilityLevel apply to the unit's
                // native abilities (defined in gameConfig.units.lineup[id]),
                // not to the override IDs in `ActiveAbilities[]`. So we patch
                // unconditionally — empty IDs list just means no override,
                // but the unit still has its native abilities at this level.
                const lvl = args.targetAbilityLevel;
                u.ActiveAbilityLevel = lvl;
                u.PassiveAbilityLevel = lvl;
                if (u.TertiaryAbility != null) u.TertiaryAbilityLevel = lvl;
            }

            result.normalized.push(unitId);
            if (isMow) result.mow.push(unitId);
        } catch (e) {
            const reason = "v2 patch: " + (e as Error).message;
            result.skipped.push({ unitId, reason });
            // Track MoW that the formula refused so we can tell apart
            // "no MoW in BC" from "MoW present but unsupported by the
            // formula" (likely the case for `:pvp` MoW variants whose
            // stats aren't computed via StatsUsingProgressionIndexFor).
            if (isMow) mowSkipped.push({ unitId, reason });
        }
    }
    // An explicit-stats key that matched nothing is REPORTED, never
    // swallowed. Swallowing it would degrade back into "the hero formula
    // ran for that unit" — the exact silent failure this path removes.
    // Note it is computed against the WHOLE catalogue, not the filtered
    // pass, so `unitsFilter` cannot turn a real entry into a false alarm.
    if (args.explicitStats) {
        const known = new Set(units.map((x) => x.Id as string));
        for (const k of Object.keys(args.explicitStats)) {
            if (!known.has(k)) result.explicitUnmatched.push(k);
        }
    }

    try {
        emit({
            evt: "normalize_bc_mow_diag",
            callNo: _normalizeCallCount,
            mowAttempted,
            mowAttemptedSample,
            mowNormalized: result.mow.length,
            mowSkipped: mowSkipped.length,
            mowSkippedSample: mowSkipped.slice(0, 5),
        });
    } catch { /* diagnostic must never throw */ }

    // Diagnostic summary at the end: aggregate skip reasons so we
    // can correlate pool degradation with specific failure modes
    // (e.g. "IsMOW: ..." vs "v2 patch: ..." vs catch internal).
    try {
        const reasonCounts: Record<string, number> = {};
        const reasonSamples: Record<string, string[]> = {};
        for (const s of result.skipped) {
            const r = s.reason || "<unknown>";
            // Truncate to first 60 chars so error variants collapse.
            const key = r.length > 60 ? r.slice(0, 60) + "…" : r;
            reasonCounts[key] = (reasonCounts[key] ?? 0) + 1;
            if (!reasonSamples[key]) reasonSamples[key] = [];
            if (reasonSamples[key].length < 3) reasonSamples[key].push(s.unitId);
        }
        emit({
            evt: "normalize_bc_summary",
            callNo: _normalizeCallCount,
            normalizedCount: result.normalized.length,
            skippedCount: result.skipped.length,
            reasonCounts,
            reasonSamples,
        });
    } catch { /* diagnostic must never throw */ }

    result.configJson = JSON.stringify(bc);
    result.ok = true;
    return result;
}
