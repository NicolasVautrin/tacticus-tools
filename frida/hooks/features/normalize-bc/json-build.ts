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
import { getLastUnitProgression } from "../campaign-builder.js";
import {
    resolveFormulaState, ensureEmptyLists, resolveItemModelState,
    createEmptyList, createItemModel, addItemToList,
} from "./formula.js";

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
}

export interface NormalizeBcResult {
    ok: boolean;
    configJson?: string;
    normalized: string[];
    skipped: Array<{ unitId: string; reason: string }>;
    swappedBoard: string | null;
    err?: string;
}

export function buildNormalizedBC(args: NormalizeBcArgs): NormalizeBcResult {
    const result: NormalizeBcResult = {
        ok: false, normalized: [], skipped: [], swappedBoard: null,
    };

    const unitProg = getLastUnitProgression();
    if (!unitProg) {
        result.err = "lastUnitProgression not captured — warmup required";
        return result;
    }
    const state = resolveFormulaState(unitProg);
    if (typeof state === "string") { result.err = state; return result; }
    const listsErr = ensureEmptyLists(state, unitProg, "ultraTigurius");
    if (listsErr) { result.err = listsErr; return result; }
    const ismErr = resolveItemModelState(state, unitProg);
    if (ismErr) { result.err = ismErr; return result; }

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
    const listClass = state.emptyListItems!.readPointer();
    const fn = new NativeFunction(state.statsForMi.ptr, "void", [
        "pointer", "pointer", "pointer", "uchar", "int", "int",
        "pointer", "pointer",
    ]);

    for (const u of units) {
        const unitId = u.Id as string | undefined;
        if (!unitId) {
            result.skipped.push({ unitId: "<no Id>", reason: "no Id field" });
            continue;
        }
        if (filter && !filter.has(unitId)) continue;

        try {
            const idStr = createManagedString(unitId);

            // isMOW
            let isMow = 0;
            try {
                const idTmp = createManagedString(unitId);
                const r = invokeMethod(state.isMowMi.info, ptr(0),
                    [state.unitsConfig, idTmp]) as NativePointer;
                isMow = r.toInt32() & 1;
            } catch (e) {
                result.skipped.push({ unitId, reason: "IsMOW: " + (e as Error).message });
                continue;
            }

            // Build items list (fresh per unit to isolate)
            const itemsList = createEmptyList(listClass);
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
               state.emptyListInt!, itemsList);

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
        } catch (e) {
            result.skipped.push({
                unitId, reason: "v2 patch: " + (e as Error).message,
            });
        }
    }

    result.configJson = JSON.stringify(bc);
    result.ok = true;
    return result;
}
