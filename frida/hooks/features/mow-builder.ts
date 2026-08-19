// MachinesOfWar Event battle builder.
//
// Mirrors the campaign-builder pattern but targets MachinesOfWarEventGameModeSource.
//
// Capture: hook MachinesOfWarEventGameModeSource..ctor → stash lastMoWSource.
// The user has to navigate to the MoW event in-game once to publish the
// instance; subsequent builds work without further nav.
//
// Catalog: query the live IMachinesOfWarEventProgression on the source.
// `GetAllBattleConfigs(tierIndex)` returns the tier's static battle list
// (LinearBattleLevelConfigurationDto). Iterate tiers 0..N until null/empty.
//
// Build: mutate the backing fields of `_eventBattleData`
// (NodeOrBattleIndex, TierIndex, Enemies, MachineOfWarEnemy, BoardId,
// SpawnPointsSet, RarityCap, LightningVictoryTurns) on the live source,
// invoke LoadBattle(isRestart=true), capture _currentBattle, restore.
//
// Hot-path safety: every mutation is inside one queueOnMainThread invocation.
// No other code observes the swapped state. Originals are restored in the
// finally block even on serialize failure.

import {
    findClass, findClassAnywhere, findMethod, getFieldOffset,
    IL2CPP_MODULE_NAME, MethodRef, methodEntry, method_get_name,
    method_get_param_count, class_get_methods, class_get_name, s,
} from "../il2cpp/helpers.js";
import { invokeMethod, createManagedString } from "../il2cpp/invoke.js";
import { serializeToJson } from "../il2cpp/serializer.js";
import { queueOnMainThread } from "../runtime/queue.js";
import { log, traceEnter } from "../runtime/diag.js";
import { Ctx } from "../controller.js";
import { getLastGameConfig } from "./campaign-builder.js";

const ASM_BATTLE = "Assembly-CSharp.dll";
const NS_BATTLE_SOURCE = "IdunBattle.ViewLogic.BattleSource";
const NS_DATA_LIVE_EVENTS = "idun.Idun.Source.IdunMeta.Logic.UserProgress.Data.LiveEvents.Modules";

// Most-recent MachinesOfWarEventGameModeSource instance — captured by .ctor.
// Required only for the BUILD path (LoadBattle invocation).
let lastMoWSource: NativePointer | null = null;

// Live MachinesOfWarEventProgression — Zenject-bound singleton, available
// from boot. Captured via .ctor hook OR heap-scanned on first need. Used by
// the catalog dump so the user doesn't have to navigate to the MoW event
// just to enumerate available battles (mirrors how campaignBuilder uses
// the GameConfigDto singleton without requiring nav).
let lastMoWProgression: NativePointer | null = null;

// Resolved lazily on first use.
let mowSourceClass: NativePointer | null = null;
let loadBattleMi: MethodRef | null = null;
let offEventBattleData = -1;
let offMoWProgression = -1;
let offCurrentBattle = -1;

// MachinesOfWarEventBattleData backing-field offsets.
let ebdClass: NativePointer | null = null;
let offEbdLiveEventId = -1;
let offEbdNodeIndex = -1;
let offEbdTierIndex = -1;
let offEbdEnemies = -1;
let offEbdMoWEnemy = -1;
let offEbdBoardId = -1;
let offEbdSpawnSet = -1;
let offEbdRarityCap = -1;
let offEbdLVTurns = -1;

// IMachinesOfWarEventProgression methods.
let getAllBattleConfigsMi: MethodRef | null = null;
let getBattleConfigMi: MethodRef | null = null;
let getEnemyUnitsForBattleMi: MethodRef | null = null;
let getTierRarityMi: MethodRef | null = null;

// LinearBattleLevelConfigurationDto offsets (catalog row).
let linConfigClass: NativePointer | null = null;
let offLinBoardId = -1;
let offLinSpawnSet = -1;
let offLinBattleId = -1;
let offLinEnemies = -1;
let offLinEnemyMow = -1;
let offLinLightning = -1;

// List<T>._items / _size (resolved on first iteration of any list).
let listItemsOff = -1;
let listSizeOff = -1;

function ensureMoWClassResolved(): boolean {
    if (mowSourceClass && loadBattleMi) return true;
    mowSourceClass = findClass(ASM_BATTLE, NS_BATTLE_SOURCE,
        "MachinesOfWarEventGameModeSource");
    if (!mowSourceClass) {
        log("[mow-builder] MachinesOfWarEventGameModeSource class not found");
        return false;
    }
    // LoadBattleInternal (declared in MachinesOfWarEventGameModeSource —
    // override of the abstract AGameModeSource.LoadBattleInternal). The
    // public LoadBattle wrapper is on the parent class so findMethod (which
    // only enumerates DECLARED methods on this klass) won't see it; the
    // *Internal version is here, has the same signature, and produces the
    // BattleConfiguration directly.
    loadBattleMi = findMethod(mowSourceClass, "LoadBattleInternal");
    if (!loadBattleMi) {
        log("[mow-builder] LoadBattleInternal method not found");
        return false;
    }
    offEventBattleData = getFieldOffset(mowSourceClass, "_eventBattleData");
    offMoWProgression  = getFieldOffset(mowSourceClass,
        "_machinesOfWarEventProgression");
    offCurrentBattle   = getFieldOffset(mowSourceClass, "_currentBattle");
    if ([offEventBattleData, offMoWProgression, offCurrentBattle]
            .some((o) => o < 0)) {
        log("[mow-builder] missing source field offsets: "
            + JSON.stringify({offEventBattleData, offMoWProgression, offCurrentBattle}));
        return false;
    }
    return true;
}

function ensureEbdResolved(ebdInstance: NativePointer): boolean {
    if (ebdClass && offEbdNodeIndex >= 0) return true;
    if (ebdInstance.isNull()) return false;
    ebdClass = ebdInstance.readPointer();
    // Backing fields use C# auto-property name format: <Name>k__BackingField.
    const f = (n: string) => getFieldOffset(ebdClass!, "<" + n + ">k__BackingField");
    offEbdLiveEventId = f("LiveEventId");
    offEbdNodeIndex   = f("NodeOrBattleIndex");
    offEbdTierIndex   = f("TierIndex");
    offEbdEnemies     = f("Enemies");
    offEbdMoWEnemy    = f("MachineOfWarEnemy");
    offEbdBoardId     = f("BoardId");
    offEbdSpawnSet    = f("SpawnPointsSet");
    offEbdRarityCap   = f("RarityCap");
    offEbdLVTurns     = f("LightningVictoryTurns");
    if ([offEbdNodeIndex, offEbdTierIndex, offEbdEnemies, offEbdMoWEnemy,
         offEbdBoardId, offEbdSpawnSet, offEbdRarityCap, offEbdLVTurns]
            .some((o) => o < 0)) {
        log("[mow-builder] missing EventBattleData backing offsets: "
            + JSON.stringify({offEbdLiveEventId, offEbdNodeIndex, offEbdTierIndex,
                              offEbdEnemies, offEbdMoWEnemy, offEbdBoardId,
                              offEbdSpawnSet, offEbdRarityCap, offEbdLVTurns}));
        return false;
    }
    return true;
}

function ensureProgressionMethodsResolved(progPtr: NativePointer): boolean {
    if (getAllBattleConfigsMi && getBattleConfigMi
        && getEnemyUnitsForBattleMi && getTierRarityMi) return true;
    if (progPtr.isNull()) return false;
    const klass = progPtr.readPointer();
    if (klass.isNull()) return false;
    // Walk methods to bind by name + param count (interfaces have multiple
    // overloads — pick the right arity).
    const it = Memory.alloc(Process.pointerSize);
    it.writePointer(ptr(0));
    let m: NativePointer;
    while (!(m = class_get_methods(klass, it) as NativePointer).isNull()) {
        const name = s(method_get_name(m) as NativePointer);
        const pc = method_get_param_count(m) as number;
        if (name === "GetAllBattleConfigs" && pc === 1 && !getAllBattleConfigsMi) {
            getAllBattleConfigsMi = { info: m, ptr: methodEntry(m) };
        } else if (name === "GetBattleConfig" && pc === 2 && !getBattleConfigMi) {
            getBattleConfigMi = { info: m, ptr: methodEntry(m) };
        } else if (name === "GetEnemyUnitsForBattle" && pc === 2
                   && !getEnemyUnitsForBattleMi) {
            getEnemyUnitsForBattleMi = { info: m, ptr: methodEntry(m) };
        } else if (name === "GetTierRarity" && pc === 1 && !getTierRarityMi) {
            getTierRarityMi = { info: m, ptr: methodEntry(m) };
        }
    }
    if (!getAllBattleConfigsMi || !getBattleConfigMi
        || !getEnemyUnitsForBattleMi || !getTierRarityMi) {
        log("[mow-builder] progression methods not all bound: "
            + JSON.stringify({
                GetAllBattleConfigs: !!getAllBattleConfigsMi,
                GetBattleConfig: !!getBattleConfigMi,
                GetEnemyUnitsForBattle: !!getEnemyUnitsForBattleMi,
                GetTierRarity: !!getTierRarityMi,
            }));
        return false;
    }
    return true;
}

function ensureLinConfigResolved(linInstance: NativePointer): boolean {
    if (linConfigClass && offLinBoardId >= 0) return true;
    if (linInstance.isNull()) return false;
    linConfigClass = linInstance.readPointer();
    offLinBoardId   = getFieldOffset(linConfigClass, "boardId");
    offLinSpawnSet  = getFieldOffset(linConfigClass, "spawnPointsSet");
    offLinBattleId  = getFieldOffset(linConfigClass, "battleId");
    offLinEnemies   = getFieldOffset(linConfigClass, "enemies");
    offLinEnemyMow  = getFieldOffset(linConfigClass, "enemyMow");
    offLinLightning = getFieldOffset(linConfigClass, "lightningVictory");
    return offLinBoardId >= 0 && offLinSpawnSet >= 0;
}

function ensureListOffsetsResolved(listPtr: NativePointer): boolean {
    if (listItemsOff >= 0 && listSizeOff >= 0) return true;
    if (listPtr.isNull()) return false;
    const klass = listPtr.readPointer();
    listItemsOff = getFieldOffset(klass, "_items");
    listSizeOff  = getFieldOffset(klass, "_size");
    return listItemsOff >= 0 && listSizeOff >= 0;
}

function listGet(listPtr: NativePointer, i: number): NativePointer {
    const items = listPtr.add(listItemsOff).readPointer();
    if (items.isNull()) return ptr(0);
    const size = listPtr.add(listSizeOff).readS32();
    if (i < 0 || i >= size) return ptr(0);
    return items.add(0x20 + i * Process.pointerSize).readPointer();
}

function listSize(listPtr: NativePointer): number {
    if (listPtr.isNull()) return 0;
    return listPtr.add(listSizeOff).readS32();
}

function readString(strPtr: NativePointer): string | null {
    try {
        if (strPtr.isNull()) return null;
        const len = strPtr.add(0x10).readS32();
        if (len < 0 || len > 4096) return null;
        return strPtr.add(0x14).readUtf16String(len);
    } catch { return null; }
}

/** Box an int as a System.Int32 boxed value pointer for IL2CPP invoke args. */
function boxInt32(v: number): NativePointer {
    const p = Memory.alloc(8);
    p.writeS64(int64(v));
    return p;
}

/** Read a System.Nullable<int>: layout = { bool hasValue @ 0; int value @ 4 }. */
function readNullableInt(p: NativePointer): number | null {
    if (p.isNull()) return null;
    const has = p.readU8();
    if (!has) return null;
    return p.add(4).readS32();
}

// IL2CPP runtime helpers for heap scan + type validation.
const _libIl2cpp = Process.findModuleByName(IL2CPP_MODULE_NAME);
const _objectGetClass = (() => {
    if (!_libIl2cpp) return null;
    const p = _libIl2cpp.findExportByName("il2cpp_object_get_class");
    return p ? new NativeFunction(p, "pointer", ["pointer"]) : null;
})();
const _classIsAssignableFrom = (() => {
    if (!_libIl2cpp) return null;
    const p = _libIl2cpp.findExportByName("il2cpp_class_is_assignable_from");
    return p ? new NativeFunction(p, "uint8", ["pointer", "pointer"]) : null;
})();

/** Heap-scan for an instance whose klass pointer matches `klass`. Same
 * mechanism as campaign-builder's findInstanceByHeapScan but local to keep
 * dependencies minimal. Validator filters DI placeholders. */
function findInstanceByHeapScan(
    klass: NativePointer,
    validate?: (cand: NativePointer) => boolean,
): NativePointer | null {
    const patternHex = (() => {
        const v = klass.toString(16).padStart(16, "0");
        const bytes: string[] = [];
        for (let i = 7; i >= 0; i--) bytes.push(v.substr(i * 2, 2));
        return bytes.join(" ");
    })();
    let match: NativePointer | null = null;
    const ranges = Process.enumerateRanges("rw-");
    for (const r of ranges) {
        if (match) break;
        if (r.size < 1024 * 1024) continue;
        if (r.size > 2 * 1024 * 1024 * 1024) continue;
        try {
            Memory.scanSync(r.base, r.size, patternHex).forEach((m) => {
                if (match) return;
                const cand = m.address;
                try {
                    if (!cand.readPointer().equals(klass)) return;
                    if (validate && !validate(cand)) return;
                    match = cand;
                } catch { /* unmapped */ }
            });
        } catch { /* range went away */ }
    }
    return match;
}

const MOW_PROG_NS = "Idun.Source.IdunMeta.Logic.UserProgress.MachinesOfWarEvent";

function findMoWProgressionViaHeap(): NativePointer | null {
    let klass = findClassAnywhere(MOW_PROG_NS, "MachinesOfWarEventProgression");
    if (!klass) {
        log("[mow-builder] MachinesOfWarEventProgression class not found");
        return null;
    }
    const start = Date.now();
    const found = findInstanceByHeapScan(klass, (cand) => {
        try {
            if (!_objectGetClass || !_classIsAssignableFrom) return false;
            const candKlass = _objectGetClass(cand) as NativePointer;
            if (candKlass.isNull()) return false;
            const ok = _classIsAssignableFrom(klass, candKlass) as number;
            if (!ok) return false;
            // Strict validator: every injected service field (0x50…0xC8)
            // must be a non-null pointer above the heap-base watermark.
            // Zenject placeholders show 0 / 1 / sub-page integers — ALL of
            // these would fail this check, while a fully DI-resolved
            // instance has real heap pointers at every slot.
            const min = ptr(0x10000);
            const offs = [
                0x50, 0x58, 0x60, 0x68, 0x70, 0x78, 0x80, 0x88,
                0x90, 0x98, 0xA0, 0xA8, 0xB0, 0xC8,
            ];
            for (const off of offs) {
                const v = cand.add(off).readPointer();
                if (v.compare(min) < 0) return false;
                // Each candidate's klass pointer at offset 0 must be a real
                // class pointer (sanity defense against pointer chains
                // landing in random heap data).
                try {
                    const k = v.readPointer();
                    if (k.compare(min) < 0) return false;
                } catch { return false; }
            }
            return true;
        } catch { return false; }
    });
    log("[mow-builder] heap-scan progression: "
        + (found ? found.toString() : "none")
        + " (" + (Date.now() - start) + " ms)");
    return found;
}

function findMoWSourceViaHeap(): NativePointer | null {
    const klass = findClass(ASM_BATTLE, NS_BATTLE_SOURCE,
        "MachinesOfWarEventGameModeSource");
    if (!klass) return null;
    if (!ensureMoWClassResolved()) return null;
    const start = Date.now();
    const found = findInstanceByHeapScan(klass, (cand) => {
        try {
            if (!_objectGetClass || !_classIsAssignableFrom) return false;
            const candKlass = _objectGetClass(cand) as NativePointer;
            if (candKlass.isNull()) return false;
            const ok = _classIsAssignableFrom(klass, candKlass) as number;
            if (!ok) return false;
            // Source must have non-null progression + eventBattleData
            // (DI-resolved fields). Filters Zenject placeholders.
            const min = ptr(0x10000);
            const ebd = cand.add(offEventBattleData).readPointer();
            const prog = cand.add(offMoWProgression).readPointer();
            return ebd.compare(min) >= 0 && prog.compare(min) >= 0;
        } catch { return false; }
    });
    log("[mow-builder] heap-scan source: "
        + (found ? found.toString() : "none")
        + " (" + (Date.now() - start) + " ms)");
    return found;
}

export function register(ctx: Ctx): void {
    // .ctor capture — fires once per nav into the MoW event.
    const klass = findClass(ASM_BATTLE, NS_BATTLE_SOURCE,
        "MachinesOfWarEventGameModeSource");
    if (klass) {
        const ctor = findMethod(klass, ".ctor");
        if (ctor && !ctor.ptr.isNull()) {
            try {
                Interceptor.attach(ctor.ptr, {
                    onEnter(args) {
                        traceEnter("MachinesOfWarEventGameModeSource..ctor");
                        this.selfPtr = ptr(args[0].toString());
                    },
                    onLeave() {
                        const self = this.selfPtr as NativePointer;
                        if (!self || self.isNull()) return;
                        const wasNull = lastMoWSource === null;
                        lastMoWSource = self;
                        log("[mow-builder] captured (ctor) @ " + self);
                        if (wasNull) {
                            try { send({ t: "mow_builder_ready", via: "ctor" }); }
                            catch { /* */ }
                        }
                    },
                });
                log("[+] MachinesOfWarEventGameModeSource..ctor (instance capture)");
            } catch (e) {
                log("[mow-builder] ctor hook failed: " + (e as Error).message);
            }
        }
        // Also catch via LoadBattleInternal.onEnter — covers instances
        // created BEFORE inject (rare for MoW but mirrors campaign-builder's
        // safety net). LoadBattleInternal is the override declared on the
        // class itself; the public LoadBattle is on the parent.
        const lb = findMethod(klass, "LoadBattleInternal");
        if (lb && !lb.ptr.isNull()) {
            try {
                Interceptor.attach(lb.ptr, {
                    onEnter(args) {
                        traceEnter("MachinesOfWarEventGameModeSource.LoadBattleInternal");
                        const self = ptr(args[0].toString());
                        if (self.isNull()) return;
                        if (!lastMoWSource || !lastMoWSource.equals(self)) {
                            const wasNull = lastMoWSource === null;
                            lastMoWSource = self;
                            log("[mow-builder] captured (LoadBattleInternal) @ " + self);
                            if (wasNull) {
                                try { send({ t: "mow_builder_ready", via: "LoadBattleInternal" }); }
                                catch { /* */ }
                            }
                        }
                    },
                });
                log("[+] MachinesOfWarEventGameModeSource.LoadBattleInternal (capture)");
            } catch (e) {
                log("[mow-builder] LoadBattle hook failed: " + (e as Error).message);
            }
        }
    } else {
        log("[mow-builder] MachinesOfWarEventGameModeSource class not found");
    }

    // Hook the MachinesOfWarEventProgression ctor — this is the Zenject
    // singleton that owns GetAllBattleConfigs / GetEnemyUnitsForBattle /
    // GetTierRarity. Capture once during boot's DI resolution, never need
    // user nav for the catalog.
    {
        const progKlass = findClassAnywhere(MOW_PROG_NS,
            "MachinesOfWarEventProgression");
        if (progKlass) {
            const ctor = findMethod(progKlass, ".ctor");
            if (ctor && !ctor.ptr.isNull()) {
                try {
                    Interceptor.attach(ctor.ptr, {
                        onEnter(args) {
                            traceEnter("MachinesOfWarEventProgression..ctor");
                            this.selfPtr = ptr(args[0].toString());
                        },
                        onLeave() {
                            const self = this.selfPtr as NativePointer;
                            if (!self || self.isNull()) return;
                            if (lastMoWProgression === null) {
                                lastMoWProgression = self;
                                log("[mow-builder] captured progression (ctor) @ "
                                    + self);
                            }
                        },
                    });
                    log("[+] MachinesOfWarEventProgression..ctor (capture)");
                } catch (e) {
                    log("[mow-builder] progression ctor hook failed: "
                        + (e as Error).message);
                }
            }

            // Late-capture hook: if the user injected AFTER Zenject built
            // the progression (boot singleton, .ctor fires once), the
            // ctor hook never sees it. Hook routine instance methods
            // that fire on player-state sync / config update — these
            // happen periodically and capture `this` post-construction.
            const capturePostCtor = (mname: string): void => {
                const m = findMethod(progKlass, mname);
                if (!m || m.ptr.isNull()) return;
                try {
                    Interceptor.attach(m.ptr, {
                        onEnter(args) {
                            traceEnter("MachinesOfWarEventProgression."
                                + mname, 100);
                            if (lastMoWProgression !== null) return;
                            const self = ptr(args[0].toString());
                            if (self.isNull()) return;
                            lastMoWProgression = self;
                            log("[mow-builder] captured progression (via "
                                + mname + ") @ " + self);
                            try { send({ t: "mow_builder_ready",
                                         via: mname }); } catch { /* */ }
                        },
                    });
                    log("[+] MachinesOfWarEventProgression." + mname
                        + " (late-capture)");
                } catch (e) {
                    log("[mow-builder] " + mname + " hook failed: "
                        + (e as Error).message);
                }
            };
            // OnSyncedPlayerState fires on every server player-state sync —
            // routine, no MoW-specific UI required. UpdateConfig fires
            // on game config refresh.
            for (const m of ["OnSyncedPlayerState",
                             "OnPostGameConfigUpdate",
                             "OnLiveEventOrOfferModuleAdded",
                             "OnLiveEventRemoved",
                             "GetTimeLeft",
                             "IsUnlocked"]) {
                capturePostCtor(m);
            }
        } else {
            log("[mow-builder] MachinesOfWarEventProgression class not found "
                + "in ns " + MOW_PROG_NS);
        }
    }

    /** Diagnostic — three flags so the caller can show a precise amorce
     *  banner:
     *    hasProgression : catalog dump works (no nav needed)
     *    hasInstance    : build path works (source captured)
     *    instance       : raw pointer for debug (when available) */
    ctx.rpc.machinesOfWarBuilderStatus = () => ({
        hasProgression: lastMoWProgression !== null,
        hasInstance: lastMoWSource !== null,
        instance: lastMoWSource ? lastMoWSource.toString() : null,
        progression: lastMoWProgression ? lastMoWProgression.toString() : null,
    });

    /** Diagnostic: dump GameConfigDto.liveEvents.idunLiveEventConfigs[]
     * — the STATIC array of all event configs loaded at boot from the
     * server payload, including future events (gated only by timestamp on
     * client-side activation). Concrete subclasses like
     * MachineOfWarEventConfigDataDto live here.
     *
     * Resolution: lastGameConfig (captured by campaign-builder via natural
     * UnitProgression.GetUnit firing — a few seconds post-inject, no nav
     * required). NO heap-scan, NO MoW-progression capture required. */
    /** Diagnostic: dump LiveEventsProgressionData.liveEvents and
     * .liveEventPreviews — runtime data with timestamps and components.
     * Reaches the singleton via the captured MoW progression's parent
     * field _liveEventsProgression → LiveEventsProgression
     * → _liveEventsProgressionData. */
    ctx.rpc.dumpLiveEventsRuntimeData = () => queueOnMainThread(() => {
        if (!lastMoWProgression) {
            throw new Error("MoW progression not captured — restart Tacticus + early inject, OR open the events screen so OnSyncedPlayerState/IsUnlocked fires");
        }
        const progKlass = lastMoWProgression.readPointer();
        const offLEP = getFieldOffset(progKlass, "_liveEventsProgression");
        if (offLEP < 0) throw new Error("_liveEventsProgression offset not found");
        const lepPtr = lastMoWProgression.add(offLEP).readPointer();
        if (lepPtr.isNull()) throw new Error("LiveEventsProgression null");
        const lepKlass = lepPtr.readPointer();
        const offLEPD = getFieldOffset(lepKlass, "_liveEventsProgressionData");
        if (offLEPD < 0) throw new Error("_liveEventsProgressionData offset not found");
        const lepdPtr = lepPtr.add(offLEPD).readPointer();
        if (lepdPtr.isNull()) throw new Error("LiveEventsProgressionData null");
        const lepdKlass = lepdPtr.readPointer();
        const offLE = getFieldOffset(lepdKlass, "liveEvents");
        const offLEPv = getFieldOffset(lepdKlass, "liveEventPreviews");
        if (offLE < 0 || offLEPv < 0) {
            throw new Error("liveEvents/liveEventPreviews offsets unresolved");
        }

        const dumpList = (listPtr: NativePointer, label: string): any => {
            if (listPtr.isNull()) return { count: 0, items: [] };
            if (!ensureListOffsetsResolved(listPtr)) {
                return { count: 0, items: [], note: "list offsets unresolved" };
            }
            const n = listSize(listPtr);
            const items: any[] = [];
            for (let i = 0; i < n; i++) {
                const e = listGet(listPtr, i);
                if (e.isNull()) { items.push(null); continue; }
                try {
                    const j = serializeToJson(e);
                    items.push(j ? JSON.parse(j) : null);
                } catch (err) {
                    items.push("<error: " + (err as Error).message + ">");
                }
            }
            return { count: n, items };
        };

        const liveEvents = lepdPtr.add(offLE).readPointer();
        const liveEventPreviews = lepdPtr.add(offLEPv).readPointer();

        const out = JSON.stringify({
            instance: lepdPtr.toString(),
            liveEvents: dumpList(liveEvents, "liveEvents"),
            liveEventPreviews: dumpList(liveEventPreviews, "liveEventPreviews"),
        });
        return { bytes: out.length, json: out };
    });

    /** Target diag: find LiveEventConfigDataDto entry by eventName, then
     * Newtonsoft-serialize the concrete instance. Shows all fields the
     * runtime exposes for that subtype (dump.cs may strip them). */
    ctx.rpc.dumpLiveEventConfigByName = (args: { eventName: string }) => queueOnMainThread(() => {
        const gc = getLastGameConfig();
        if (!gc) throw new Error("GameConfigDto not captured");
        const gcKlass = gc.readPointer();
        const offLiveEv = getFieldOffset(gcKlass, "liveEvents");
        if (offLiveEv < 0) throw new Error("liveEvents offset not found");
        const lePtr = gc.add(offLiveEv).readPointer();
        if (lePtr.isNull()) throw new Error("liveEvents null");
        const leKlass = lePtr.readPointer();
        const offArr = getFieldOffset(leKlass, "idunLiveEventConfigs");
        const arrPtr = lePtr.add(offArr).readPointer();
        if (arrPtr.isNull()) throw new Error("array null");
        const arrLen = arrPtr.add(0x18).readU32();
        const baseKlass = findClassAnywhere(
            "idun.Idun.Source.IdunMeta.Logic.UserProgress.Data.LiveEvents",
            "LiveEventConfigDataDto");
        const offEventName = baseKlass
            ? getFieldOffset(baseKlass, "eventName") : -1;
        if (offEventName < 0) throw new Error("eventName offset not found");
        for (let i = 0; i < arrLen; i++) {
            const elem = arrPtr.add(0x20 + i * Process.pointerSize).readPointer();
            if (elem.isNull()) continue;
            const sp = elem.add(offEventName).readPointer();
            const name = readString(sp);
            if (name !== args.eventName) continue;
            // Found it. Newtonsoft-serialize the concrete instance.
            const j = serializeToJson(elem);
            return {
                index: i,
                klassPtr: elem.readPointer().toString(),
                ptr: elem.toString(),
                bytes: j ? j.length : 0,
                json: j ?? "<null>",
            };
        }
        throw new Error("eventName '" + args.eventName + "' not found in idunLiveEventConfigs");
    });

    ctx.rpc.dumpLiveEventsConfig = () => queueOnMainThread(() => {
        const gc = getLastGameConfig();
        if (!gc) {
            throw new Error("GameConfigDto not captured — wait a few seconds for natural capture (UnitProgression.GetUnit fires on any unit render)");
        }
        const gcKlass = gc.readPointer();
        const offLiveEv = getFieldOffset(gcKlass, "liveEvents");
        if (offLiveEv < 0) throw new Error("GameConfigDto.liveEvents offset not found");
        const lePtr = gc.add(offLiveEv).readPointer();
        if (lePtr.isNull()) throw new Error("GameConfigDto.liveEvents is null");
        const leKlass = lePtr.readPointer();
        const offArr = getFieldOffset(leKlass, "idunLiveEventConfigs");
        if (offArr < 0) {
            throw new Error("LiveEventConfigDto.idunLiveEventConfigs offset not found");
        }
        const arrPtr = lePtr.add(offArr).readPointer();
        if (arrPtr.isNull()) {
            return { bytes: 14, json: '{"items":[]}' };
        }
        // Il2CppArray header: klass(0x0) + monitor(0x8) + bounds(0x10) +
        // max_length(0x18) + vector(0x20). Pointer-sized elements.
        const arrLen = arrPtr.add(0x18).readU32();
        // Two-phase: phase 1 = fast metadata-only walk of all 1356+ items
        // (klass name + eventName, no Newtonsoft); phase 2 = Newtonsoft
        // serialize only items matching the optional `prefix` filter.
        // Avoids the cost of serializing thousands of unrelated offer
        // configs while still letting the caller drill into specifics.
        const baseKlass = findClassAnywhere(
            "idun.Idun.Source.IdunMeta.Logic.UserProgress.Data.LiveEvents",
            "LiveEventConfigDataDto");
        let offEventName = -1;
        let offEventType = -1;
        if (baseKlass) {
            offEventName = getFieldOffset(baseKlass, "eventName");
            offEventType = getFieldOffset(baseKlass, "eventType_webStore");
        }
        const phase1: any[] = [];
        for (let i = 0; i < arrLen; i++) {
            const elem = arrPtr.add(0x20 + i * Process.pointerSize).readPointer();
            if (elem.isNull()) { phase1.push(null); continue; }
            const elemKlass = elem.readPointer();
            let klassName = "?";
            try {
                const np = class_get_name(elemKlass) as NativePointer;
                klassName = np.isNull() ? "?" : s(np);
            } catch { /* */ }
            // LiveEventConfigId is a struct with one string field at 0x0,
            // so read the string ptr at offEventName + 0.
            let eventName: string | null = null;
            if (offEventName >= 0) {
                try {
                    const sp = elem.add(offEventName).readPointer();
                    eventName = readString(sp);
                } catch { /* */ }
            }
            let eventType: string | null = null;
            if (offEventType >= 0) {
                try {
                    eventType = readString(elem.add(offEventType).readPointer());
                } catch { /* */ }
            }
            phase1.push({ klass: klassName, eventName, eventType });
        }
        const out = JSON.stringify({ count: arrLen, items: phase1 });
        return { bytes: out.length, json: out };
    });

    /** Diagnostic: dump the live MachinesOfWarEventProgression's internal
     * state. The parent SingleLiveEventBasedProgression<T> has private
     * fields (`_liveEvent`, `_liveEventState`, `_liveEventsWithComponentType`)
     * that Newtonsoft skips by default — we read them directly from memory
     * and Newtonsoft-serialize each pointed-to instance individually so the
     * caller can see what's in memory without a public accessor. */
    ctx.rpc.dumpMoWProgressionState = () => queueOnMainThread(() => {
        // No heap-scan here either — relies on .ctor capture. If the user
        // missed the boot-time capture window, they need to relaunch
        // Tacticus and re-inject early.
        let progPtr: NativePointer | null = lastMoWProgression;
        if (progPtr === null && lastMoWSource !== null
            && ensureMoWClassResolved()) {
            const p = lastMoWSource.add(offMoWProgression).readPointer();
            if (!p.isNull()) progPtr = p;
        }
        if (progPtr === null) {
            throw new Error("MachinesOfWarEventProgression not captured — relaunch Tacticus and re-inject during the splash screen so the .ctor hook fires before Zenject DI completes");
        }
        const klass = progPtr.readPointer();
        const offLiveEvent       = getFieldOffset(klass, "_liveEvent");
        const offLiveEventState  = getFieldOffset(klass, "_liveEventState");
        const offEventsWithComp  = getFieldOffset(klass,
            "_liveEventsWithComponentType");

        const out: any = {
            instance: progPtr.toString(),
            offsets: { offLiveEvent, offLiveEventState, offEventsWithComp },
        };

        const safeSerialize = (label: string, p: NativePointer) => {
            if (p.isNull()) return { [label]: null };
            try {
                const json = serializeToJson(p);
                return { [label]: json ? JSON.parse(json) : "<serialize null>" };
            } catch (e) {
                return { [label]: "<error: " + (e as Error).message + ">" };
            }
        };

        if (offLiveEvent >= 0) {
            const p = progPtr.add(offLiveEvent).readPointer();
            Object.assign(out, safeSerialize("liveEvent", p));
        }
        if (offLiveEventState >= 0) {
            const p = progPtr.add(offLiveEventState).readPointer();
            Object.assign(out, safeSerialize("liveEventState", p));
        }
        if (offEventsWithComp >= 0) {
            const listPtr = progPtr.add(offEventsWithComp).readPointer();
            if (!listPtr.isNull() && ensureListOffsetsResolved(listPtr)) {
                const n = listSize(listPtr);
                const items: any[] = [];
                for (let i = 0; i < Math.min(n, 50); i++) {
                    const e = listGet(listPtr, i);
                    if (e.isNull()) { items.push(null); continue; }
                    try {
                        const s = serializeToJson(e);
                        items.push(s ? JSON.parse(s) : null);
                    } catch (err) {
                        items.push("<error: " + (err as Error).message + ">");
                    }
                }
                out.liveEventsWithComponentType = { count: n, items };
            } else {
                out.liveEventsWithComponentType = { count: 0, items: [] };
            }
        }

        const json = JSON.stringify(out);
        return { bytes: json.length, json };
    });

    /** Dump the static MoW battle catalog by walking
     * IMachinesOfWarEventProgression.GetAllBattleConfigs(tier) for each tier
     * until empty/null. Each tier returns a List<LinearBattleLevelConfigurationDto>.
     * We emit a flat JSON of { tiers: [{tier, rarity, battles: [...]}] }.
     *
     * Resolution order for the progression instance:
     *   1. lastMoWProgression — captured from the .ctor hook at game boot
     *   2. lastMoWSource._machinesOfWarEventProgression — if we have a source
     *   3. heap-scan for MachinesOfWarEventProgression klass
     * The catalog does NOT require the user to navigate to the MoW event —
     * the progression is a Zenject singleton resolved during boot DI. */
    ctx.rpc.dumpMachinesOfWarCatalog = (opts?: { allowHeapScan?: boolean }) => queueOnMainThread(() => {
        let progPtr: NativePointer | null = lastMoWProgression;
        if (progPtr === null && lastMoWSource !== null
            && ensureMoWClassResolved()) {
            const p = lastMoWSource.add(offMoWProgression).readPointer();
            if (!p.isNull()) {
                progPtr = p;
                lastMoWProgression = p;
            }
        }
        if (progPtr === null && opts?.allowHeapScan !== false) {
            const scanned = findMoWProgressionViaHeap();
            if (scanned !== null) {
                lastMoWProgression = scanned;
                progPtr = scanned;
            }
        }
        if (progPtr === null) {
            throw new Error("no IMachinesOfWarEventProgression captured — wait for game boot DI to settle (a few seconds post-inject) or click ↻ to force a heap scan");
        }
        if (!ensureProgressionMethodsResolved(progPtr)) {
            throw new Error("MoW progression methods resolution failed");
        }

        const tiers: any[] = [];
        const MAX_TIERS = 50;
        // First call to GetAllBattleConfigs(0) is special: if it throws on
        // tier 0, the progression's _moduleData is null (no live MoW event).
        // Distinguish that case from "candidate was a placeholder" by
        // returning a structured "noActiveEvent" flag and clearing the
        // candidate so a future call can heap-scan again.
        let noActiveEvent = false;
        for (let tier = 0; tier < MAX_TIERS; tier++) {
            const arg = boxInt32(tier);
            let listPtr: NativePointer;
            try {
                listPtr = invokeMethod(getAllBattleConfigsMi!.info, progPtr, [arg]);
            } catch (e) {
                if (tier === 0) {
                    log("[mow-builder] GetAllBattleConfigs(0) threw — likely no active MoW event ("
                        + (e as Error).message + ")");
                    noActiveEvent = true;
                } else {
                    log("[mow-builder] GetAllBattleConfigs(" + tier + ") threw, stopping: "
                        + (e as Error).message);
                }
                break;
            }
            if (listPtr.isNull()) break;
            if (!ensureListOffsetsResolved(listPtr)) break;
            const n = listSize(listPtr);
            if (n === 0) break;

            // Tier rarity (best-effort).
            let rarity = -1;
            try {
                const rArg = boxInt32(tier);
                const rPtr = invokeMethod(getTierRarityMi!.info, progPtr, [rArg]);
                rarity = rPtr.toInt32();
            } catch { /* enum returned by-value through invoke wrapper */ }

            const battles: any[] = [];
            for (let i = 0; i < n; i++) {
                const lin = listGet(listPtr, i);
                if (lin.isNull()) continue;
                if (!ensureLinConfigResolved(lin)) continue;
                const enemiesList = lin.add(offLinEnemies).readPointer();
                const enemies: string[] = [];
                if (!enemiesList.isNull()) {
                    if (ensureListOffsetsResolved(enemiesList)) {
                        const en = listSize(enemiesList);
                        for (let j = 0; j < en; j++) {
                            const sp = listGet(enemiesList, j);
                            const ss = readString(sp);
                            if (ss) enemies.push(ss);
                        }
                    }
                }
                battles.push({
                    battleIndex: i,
                    boardId: readString(lin.add(offLinBoardId).readPointer()),
                    spawnPointsSet: lin.add(offLinSpawnSet).readS32(),
                    battleId: readString(lin.add(offLinBattleId).readPointer()),
                    enemies,
                    enemyMow: readString(lin.add(offLinEnemyMow).readPointer()),
                    lightningVictory: offLinLightning >= 0
                        ? readNullableInt(lin.add(offLinLightning))
                        : null,
                });
            }
            tiers.push({ tier, rarity, battles });
        }
        const json = JSON.stringify({ tiers, noActiveEvent });
        return { bytes: json.length, json, tierCount: tiers.length, noActiveEvent };
    });

    /** Build a BattleConfiguration for an arbitrary (tier, battle) combo by
     * mutating the live source's _eventBattleData backing fields, invoking
     * LoadBattle(true), capturing _currentBattle, then restoring originals.
     *
     * The lists/dicts for AvailableUnits/EligibleUnits/UncappedAvailableUnits/
     * RegeneratedUnitsRemainingHealthAfterBattleStart are PRESERVED from the
     * live data — they're player-side state and don't depend on (tier, battle).
     */
    ctx.rpc.buildMachinesOfWarConfig = (args: {
        tier: number;
        battle: number;
    }) => queueOnMainThread(() => {
        // Source needed to invoke LoadBattle. Heap-scan is the fallback
        // mirror of campaign-builder — works as long as Tacticus DI has
        // instantiated the source at least once (typically yes after boot,
        // even without UI nav).
        if (!ensureMoWClassResolved()) {
            throw new Error("MoW source class resolution failed");
        }
        if (!lastMoWSource) {
            const scanned = findMoWSourceViaHeap();
            if (scanned !== null) lastMoWSource = scanned;
        }
        if (!lastMoWSource) {
            throw new Error("no live MachinesOfWarEventGameModeSource — open the MoW event UI in-game once. (DI doesn't always pre-instantiate this source.)");
        }
        const ebd = lastMoWSource.add(offEventBattleData).readPointer();
        if (ebd.isNull()) throw new Error("source._eventBattleData is null");
        if (!ensureEbdResolved(ebd)) {
            throw new Error("EventBattleData offsets resolution failed");
        }
        const progPtr = lastMoWSource.add(offMoWProgression).readPointer();
        if (progPtr.isNull()) throw new Error("source._machinesOfWarEventProgression is null");
        if (!ensureProgressionMethodsResolved(progPtr)) {
            throw new Error("MoW progression methods resolution failed");
        }

        // Resolve target battle's static config (board/spawnSet/lightning).
        const tArg = boxInt32(args.tier);
        const bArg = boxInt32(args.battle);
        const lin = invokeMethod(getBattleConfigMi!.info, progPtr, [tArg, bArg]);
        if (lin.isNull()) {
            throw new Error(`GetBattleConfig(${args.tier}, ${args.battle}) returned null`);
        }
        if (!ensureLinConfigResolved(lin)) {
            throw new Error("LinearBattleLevelConfigurationDto offsets unresolved");
        }
        const newBoardIdPtr = lin.add(offLinBoardId).readPointer();
        const newSpawnSet   = lin.add(offLinSpawnSet).readS32();
        const newLightning  = offLinLightning >= 0
            ? (readNullableInt(lin.add(offLinLightning)) ?? 0)
            : 0;

        // Resolve target battle's enemies (List<UnitModelWithHealth>) + MoW.
        // GetEnemyUnitsForBattle returns ValueTuple<List<UnitModelWithHealth>,
        // UnitModelWithHealth>. ValueTuple<T1,T2> layout = { T1 Item1; T2 Item2; }
        // — both are pointer-sized references for managed ref types.
        // The invoke wrapper returns the boxed tuple for us to read fields off.
        // (For value-type tuples Frida's invokeMethod still returns a pointer
        // to the unboxed result on the eval stack.)
        const eu = invokeMethod(getEnemyUnitsForBattleMi!.info, progPtr, [tArg, bArg]);
        if (eu.isNull()) {
            throw new Error(`GetEnemyUnitsForBattle(${args.tier}, ${args.battle}) returned null`);
        }
        // Box layout: skip the box header (klass+monitor = 0x10) for object box,
        // then ValueTuple fields. invokeMethod for value types returns the
        // boxed object — Item1/Item2 at +0x10/+0x18.
        const newEnemies = eu.add(0x10).readPointer();
        const newMoW     = eu.add(0x10 + Process.pointerSize).readPointer();

        // Tier rarity → write into RarityCap.
        let newRarity = ebd.add(offEbdRarityCap).readS32();
        try {
            const rArg = boxInt32(args.tier);
            const r = invokeMethod(getTierRarityMi!.info, progPtr, [rArg]);
            newRarity = r.toInt32();
        } catch { /* keep existing */ }

        // Save originals for restore.
        const origNode    = ebd.add(offEbdNodeIndex).readS32();
        const origTier    = ebd.add(offEbdTierIndex).readS32();
        const origEnemies = ebd.add(offEbdEnemies).readPointer();
        const origMoW     = ebd.add(offEbdMoWEnemy).readPointer();
        const origBoardId = ebd.add(offEbdBoardId).readPointer();
        const origSpawn   = ebd.add(offEbdSpawnSet).readS32();
        const origRarity  = ebd.add(offEbdRarityCap).readS32();
        const origLV      = ebd.add(offEbdLVTurns).readS32();

        log(`[mow-builder] mutating ebd: node ${origNode}→${args.battle}, `
            + `tier ${origTier}→${args.tier}, board ${origBoardId}→${newBoardIdPtr}, `
            + `spawn ${origSpawn}→${newSpawnSet}, rarity ${origRarity}→${newRarity}, `
            + `lv ${origLV}→${newLightning}`);

        let json: string | null = null;
        try {
            ebd.add(offEbdNodeIndex).writeS32(args.battle);
            ebd.add(offEbdTierIndex).writeS32(args.tier);
            ebd.add(offEbdEnemies).writePointer(newEnemies);
            ebd.add(offEbdMoWEnemy).writePointer(newMoW);
            ebd.add(offEbdBoardId).writePointer(newBoardIdPtr);
            ebd.add(offEbdSpawnSet).writeS32(newSpawnSet);
            ebd.add(offEbdRarityCap).writeS32(newRarity);
            ebd.add(offEbdLVTurns).writeS32(newLightning);

            const isRestartArg = Memory.alloc(8);
            isRestartArg.writeU64(uint64(1));
            const t0 = Date.now();
            const battleConfig = invokeMethod(loadBattleMi!.info, lastMoWSource,
                [isRestartArg]);
            log("[mow-builder] LoadBattle returned " + battleConfig
                + " (took " + (Date.now() - t0) + " ms)");
            if (battleConfig.isNull()) throw new Error("LoadBattle returned null");
            json = serializeToJson(battleConfig);
            if (!json) throw new Error("SerializeObject(BattleConfiguration) returned null");
            log("[mow-builder] serialized to " + json.length + " bytes");
        } finally {
            // Restore originals.
            ebd.add(offEbdNodeIndex).writeS32(origNode);
            ebd.add(offEbdTierIndex).writeS32(origTier);
            ebd.add(offEbdEnemies).writePointer(origEnemies);
            ebd.add(offEbdMoWEnemy).writePointer(origMoW);
            ebd.add(offEbdBoardId).writePointer(origBoardId);
            ebd.add(offEbdSpawnSet).writeS32(origSpawn);
            ebd.add(offEbdRarityCap).writeS32(origRarity);
            ebd.add(offEbdLVTurns).writeS32(origLV);
            log("[mow-builder] ebd restored");
        }
        return { tier: args.tier, battle: args.battle,
                 bytes: json!.length, json: json! };
    });
}
