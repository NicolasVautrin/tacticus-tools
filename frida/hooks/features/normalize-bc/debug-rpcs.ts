// Debug RPCs for the normalize-bc pipeline. Kept separate from the main
// file because they're investigative tools, not the production wrapper.
//
//   - probeStatsViaFormula({ unitId, unitRank, progressionIndex })
//       Diagnostic call of `IStatsFormula.StatsUsingProgressionIndexFor`
//       with empty Lists + class-name dump of every method overload and
//       sidecar field. Used to diagnose silent crashes / sigil mismatches.
//   - probeFindHumanPlayer
//       Invokes `PlayersConfiguration.FindPlayerConfigByType(Human)` and
//       dumps the boxed Nullable<ValueTuple> result bytes — used to pin
//       down the actual offset of PlayerId inside the boxed return.
//   - installStatsFormulaTrap / getStatsFormulaCaptures
//       Passive `Interceptor.attach onEnter` on the formula entry, captures
//       the args the game itself passes when the natural cascade fires.
//       Compare with what we pass to identify divergence. The methodology
//       that unblocked the 5h crash investigation.
//   - dumpListItemsContents({ listPtrHex })
//       Walks a `List<IItemModel>` from a hex ptr and reads each ItemModel's
//       configId, initial/override/effective level, max level. Used to
//       inspect what the game stores for a player's equipped items.

import {
    findClass, findMethodByParamCount,
} from "../../il2cpp/helpers.js";
import { createManagedString, invokeMethod } from "../../il2cpp/invoke.js";
import { getLastUnitProgression } from "../campaign-builder.js";
import { queueOnMainThread } from "../../runtime/queue.js";
import { Ctx } from "../../controller.js";
import {
    resolveFormulaState, ensureEmptyLists, readUnitDynamicStats,
} from "./formula.js";
import { getLiveBC, BC_OFF_PLAYER } from "./live-bc.js";

function probeStatsViaFormula(args: {
    unitId: string;
    unitRank: number;
    progressionIndex: number;
}): unknown {
    const unitProg = getLastUnitProgression();
    if (!unitProg) return { err: "lastUnitProgression not captured" };

    const state = resolveFormulaState(unitProg);
    if (typeof state === "string") return { err: state };

    const listsErr = ensureEmptyLists(state, unitProg, args.unitId);
    if (listsErr) return { err: listsErr };

    const idStr = createManagedString(args.unitId);

    // IsMachineOfWar(UnitsConfigDto, string) -> bool (returned as boxed int)
    let isMow = 0;
    try {
        const ret = invokeMethod(state.isMowMi.info, ptr(0),
            [state.unitsConfig, idStr]) as NativePointer;
        isMow = ret.toInt32() & 1;
    } catch (e) {
        return { err: "IsMachineOfWar failed: " + (e as Error).message };
    }

    // bool param: try 1-byte first (matches Ghidra `char param_4` signature).
    const isMowBuf = Memory.alloc(1); isMowBuf.writeU8(isMow);
    const rankBuf = Memory.alloc(4); rankBuf.writeS32(args.unitRank);
    const progIdxBuf = Memory.alloc(4); progIdxBuf.writeS32(args.progressionIndex);

    // Resolve class names for diagnosis
    const _Helpers = require("../../il2cpp/helpers.js");
    const _cgn = _Helpers.class_get_name;
    const _cst = _Helpers.cstr;
    function _clsName(klass: NativePointer): string {
        try { return _cst(_cgn(klass) as NativePointer); }
        catch { return "?"; }
    }
    const formulaClass = state.statsFormula.readPointer();
    const gaBase = Process.findModuleByName("GameAssembly.dll")?.base ?? ptr(0);
    // StatsFormula fields: _gameConfig @ 0x10, _itemStatsFormula @ 0x18
    const fGameConfig = state.statsFormula.add(0x10).readPointer();
    const fItemStatsFormula = state.statsFormula.add(0x18).readPointer();
    const dbg: Record<string, unknown> = {
        isMow,
        statsFormulaPtr: state.statsFormula.toString(),
        formulaClassName: _clsName(formulaClass),
        statsForRva: "0x" + state.statsForMi.ptr.sub(gaBase).toString(16),
        f_gameConfigPtr: fGameConfig.toString(),
        f_gameConfigClassName: fGameConfig.isNull() ? "<null>" : _clsName(fGameConfig.readPointer()),
        f_itemStatsFormulaPtr: fItemStatsFormula.toString(),
        f_itemStatsFormulaClassName: fItemStatsFormula.isNull() ? "<null>" : _clsName(fItemStatsFormula.readPointer()),
        emptyListIntClassName: _clsName(state.emptyListInt!.readPointer()),
        emptyListItemsClassName: _clsName(state.emptyListItems!.readPointer()),
    };

    // Enumerate ALL methods named StatsUsingProgressionIndexFor on the class
    // to detect if we're picking the wrong one.
    {
        const cm = _Helpers.class_get_methods;
        const mn = _Helpers.method_get_name;
        const mpc = _Helpers.method_get_param_count;
        const me = _Helpers.methodEntry;
        const cp = _Helpers.class_get_parent;
        const matches: Array<{ paramCount: number; rva: string; className: string }> = [];
        let k = formulaClass;
        while (!k.isNull()) {
            const it = Memory.alloc(Process.pointerSize); it.writePointer(ptr(0));
            let m: NativePointer;
            const kn = _clsName(k);
            while (!(m = cm(k, it) as NativePointer).isNull()) {
                if (_cst(mn(m) as NativePointer) === "StatsUsingProgressionIndexFor") {
                    matches.push({
                        paramCount: mpc(m) as number,
                        rva: "0x" + (me(m) as NativePointer).sub(gaBase).toString(16),
                        className: kn,
                    });
                }
            }
            k = cp(k) as NativePointer;
        }
        dbg.allStatsUsingProgressionIndexFor = matches;
    }

    // Sanity probe: call UnitStatMultiplierForProgressionIndex(progIdx, isMOW)
    // (2 args, returns int) — validates the StatsFormula instance is callable.
    try {
        const multMi = findMethodByParamCount(
            formulaClass, "UnitStatMultiplierForProgressionIndex", 2);
        if (multMi) {
            const progBuf = Memory.alloc(4); progBuf.writeS32(args.progressionIndex);
            const mowB = Memory.alloc(1); mowB.writeU8(isMow);
            const r = invokeMethod(multMi.info, state.statsFormula,
                [progBuf, mowB]) as NativePointer;
            dbg.unitStatMultiplier = r.toInt32();
        } else {
            dbg.unitStatMultiplier = "method not found";
        }
    } catch (e) {
        dbg.unitStatMultiplierErr = (e as Error).message;
    }

    try {
        const boxed = invokeMethod(state.statsForMi.info, state.statsFormula,
            [idStr, isMowBuf, rankBuf, progIdxBuf,
             state.emptyListInt!, state.emptyListItems!]) as NativePointer;
        if (!boxed || boxed.isNull()) {
            return { ...dbg, err: "StatsUsingProgressionIndexFor returned null" };
        }
        return { ...dbg, stats: readUnitDynamicStats(boxed) };
    } catch (e) {
        return { ...dbg, err: "formula invoke failed: " + (e as Error).message };
    }
}

export function registerDebugRpcs(ctx: Ctx): void {
    /** Debug: invoke FindPlayerConfigByType(Human) and dump 64 bytes of the
     *  boxed Nullable<ValueTuple<PlayerId, PlayerConfiguration>> result, so
     *  we can find the actual offset of the PlayerId int inside it. */
    ctx.rpc.probeFindHumanPlayer = () => queueOnMainThread(() => {
        const bc = getLiveBC();
        if (!bc) return { err: "no live BC" };
        const playersConfig = bc.add(BC_OFF_PLAYER).readPointer();
        if (playersConfig.isNull()) return { err: "PlayersConfiguration null" };

        const klass = findClass(
            "BattleLogicAssembly.dll", "IdunBattle.Configuration",
            "PlayersConfiguration");
        if (!klass) return { err: "PlayersConfiguration class not found" };
        const m = findMethodByParamCount(klass, "FindPlayerConfigByType", 1);
        if (!m) return { err: "FindPlayerConfigByType not found" };

        const out: Record<string, unknown> = {};
        for (const [name, type] of Object.entries({ Human: 0, AI: 1 })) {
            try {
                const buf = Memory.alloc(4); buf.writeS32(type);
                const boxed = invokeMethod(m.info, playersConfig, [buf]) as NativePointer;
                if (!boxed || boxed.isNull()) {
                    out[name] = { boxed: "null" };
                    continue;
                }
                const dump: number[] = [];
                for (let i = 0; i < 48; i++) {
                    dump.push(boxed.add(i).readU8());
                }
                out[name] = {
                    boxed: boxed.toString(),
                    bytes: dump.map(b => b.toString(16).padStart(2, "0")).join(" "),
                    s32At10: boxed.add(0x10).readS32(),
                    s32At14: boxed.add(0x14).readS32(),
                    s32At18: boxed.add(0x18).readS32(),
                    s32At1C: boxed.add(0x1C).readS32(),
                    s32At20: boxed.add(0x20).readS32(),
                    u8At10: boxed.add(0x10).readU8(),
                };
            } catch (e) {
                out[name] = { err: (e as Error).message };
            }
        }
        return out;
    });

    ctx.rpc.probeStatsViaFormula = (args: {
        unitId: string; unitRank: number; progressionIndex: number;
    }) => queueOnMainThread(() => probeStatsViaFormula(args));

    // Passive trap on StatsFormula.StatsUsingProgressionIndexFor: capture
    // the args the game itself passes when the 1-arg GetStats cascade fires.
    // Compares with what we attempt to pass to identify divergence.
    let _statsTrapInstalled = false;
    const _statsTrapCaptures: Array<Record<string, unknown>> = [];
    ctx.rpc.installStatsFormulaTrap = () => queueOnMainThread(() => {
        if (_statsTrapInstalled) return { ok: true, alreadyInstalled: true };
        const unitProg = getLastUnitProgression();
        if (!unitProg) return { err: "no lastUnitProgression" };
        const state = resolveFormulaState(unitProg);
        if (typeof state === "string") return { err: state };
        const _H = require("../../il2cpp/helpers.js");
        const cgn = _H.class_get_name;
        const cst = _H.cstr;
        const _readMS = (p: NativePointer): string | null => {
            if (!p || p.isNull()) return null;
            try {
                const len = p.add(0x10).readS32();
                if (len < 0 || len > 1000) return null;
                return p.add(0x14).readUtf16String(len);
            } catch { return null; }
        };
        Interceptor.attach(state.statsForMi.ptr, {
            onEnter(args) {
                // 8 args at the native level:
                //   args[0] = out UnitDynamicStats*
                //   args[1] = StatsFormula* (this)
                //   args[2] = string unitId
                //   args[3] = bool isMOW (in low byte)
                //   args[4] = int unitRank
                //   args[5] = int progressionIndex
                //   args[6] = List<int>*
                //   args[7] = List<IItemModel>*
                if (_statsTrapCaptures.length >= 10) return; // cap log volume
                try {
                    const idPtr = args[2] as NativePointer;
                    const list4 = args[6] as NativePointer;
                    const list5 = args[7] as NativePointer;
                    const sz4 = list4.isNull() ? -1 :
                        list4.add(0x18).readS32(); // List<T>._size at +0x18
                    const sz5 = list5.isNull() ? -1 :
                        list5.add(0x18).readS32();
                    _statsTrapCaptures.push({
                        ts: Date.now(),
                        outBuf: (args[0] as NativePointer).toString(),
                        thisPtr: (args[1] as NativePointer).toString(),
                        unitId: _readMS(idPtr),
                        isMOW: (args[3] as NativePointer).toInt32() & 0xFF,
                        unitRank: (args[4] as NativePointer).toInt32(),
                        progIdx: (args[5] as NativePointer).toInt32(),
                        listIntPtr: list4.toString(),
                        listIntClass: list4.isNull() ? null
                            : cst(cgn(list4.readPointer()) as NativePointer),
                        listIntSize: sz4,
                        listItemsPtr: list5.toString(),
                        listItemsClass: list5.isNull() ? null
                            : cst(cgn(list5.readPointer()) as NativePointer),
                        listItemsSize: sz5,
                    });
                } catch (e) {
                    _statsTrapCaptures.push({ err: (e as Error).message });
                }
            },
        });
        _statsTrapInstalled = true;
        return { ok: true };
    });
    ctx.rpc.getStatsFormulaCaptures = () =>
        ({ captures: _statsTrapCaptures });

    /** Read all configIds + levels from a `List<IItemModel>` pointer. */
    ctx.rpc.dumpListItemsContents = (args: { listPtrHex: string }) =>
        queueOnMainThread(() => {
            const _readMS = (p: NativePointer): string | null => {
                if (!p || p.isNull()) return null;
                try {
                    const len = p.add(0x10).readS32();
                    if (len < 0 || len > 1000) return null;
                    return p.add(0x14).readUtf16String(len);
                } catch { return null; }
            };
            const list = ptr(args.listPtrHex);
            if (list.isNull()) return { err: "list null" };
            const itemsArr = list.add(0x10).readPointer();
            const size = list.add(0x18).readS32();
            if (itemsArr.isNull() || size <= 0) return { size, items: [] };

            // Lazy-resolve ItemModel.Level() and Stats() to call them per-item.
            const _H = require("../../il2cpp/helpers.js");
            const itemModelClass = _H.findClassAnywhere(
                "IdunMetaLogic.UserProgress.Model", "ItemModel");
            const levelMi = itemModelClass
                ? _H.findMethod(itemModelClass, "Level") : null;
            const maxLevelMi = itemModelClass
                ? _H.findMethod(itemModelClass, "MaxLevel") : null;

            const out: Array<Record<string, unknown>> = [];
            for (let i = 0; i < size; i++) {
                const itemPtr = itemsArr.add(0x20 + i * 8).readPointer();
                if (itemPtr.isNull()) { out.push({ idx: i, ptr: "0x0" }); continue; }
                // ItemModel layout: 0x10 ItemId, 0x18 ConfigId(strPtr),
                // 0x20 Amount, 0x28 BoundToUnit, 0x30 _itemProgression,
                // 0x38 _initialItemLevel(int), 0x3C Nullable<Level>(8B = hasV+int)
                const cfgIdStrPtr = itemPtr.add(0x18).readPointer();
                const cfgIdStr = _readMS(cfgIdStrPtr);
                const boundTo = _readMS(itemPtr.add(0x28).readPointer());
                const initialLvl = itemPtr.add(0x38).readS32();
                const overrideHas = itemPtr.add(0x3C).readU8();
                const overrideLvl = itemPtr.add(0x40).readS32();

                let effectiveLvl: number | string = "n/a";
                try {
                    if (levelMi) {
                        const r = invokeMethod(levelMi.info, itemPtr, null) as NativePointer;
                        // Level is a 4-byte int struct; runtime_invoke returns
                        // it boxed -> read at +0x10
                        effectiveLvl = r.add(0x10).readS32();
                    }
                } catch (e) { effectiveLvl = "err: " + (e as Error).message; }

                let maxLvl: number | string = "n/a";
                try {
                    if (maxLevelMi) {
                        const r = invokeMethod(maxLevelMi.info, itemPtr, null) as NativePointer;
                        maxLvl = r.add(0x10).readS32();
                    }
                } catch (e) { maxLvl = "err: " + (e as Error).message; }

                out.push({
                    idx: i, ptr: itemPtr.toString(),
                    configId: cfgIdStr, boundTo,
                    initialLevel: initialLvl,
                    levelOverride: overrideHas ? overrideLvl : null,
                    effectiveLevel: effectiveLvl,
                    maxLevel: maxLvl,
                });
            }
            return { size, items: out };
        });
}
