// AI utility access trace — observes which UtilityConfig keys are read
// during AI scoring decisions.
//
// Two hooks compose the trace:
//   1) UtilitiesDatabase.GetUtilityConfig(type, coll) → returns UtilityConfig
//      We register the returned instance pointer as "known" → key reads on
//      that instance are interesting.
//   2) Dictionary<string,int>.TryGetValue(key, out value) on UtilityConfig
//      instances → captures (configPtr, key, found, value).
//
// Cross-referencing: log entry from #1 carries (UtilityType, Collection)
// and the returned configPtr → we know which utility config a given dict
// access belongs to.
//
// Off by default — RPC `aiUtilityTraceEnable()` to start, `…Disable()` to
// stop, `…Dump(maxEntries)` to read the buffer.

import { Ctx } from "../controller.js";
import {
    class_get_methods, class_get_name,
    findClass, findClassAnywhere, findMethod,
    il2cppBase, il2cppSize,
    method_get_name, method_get_param_count, methodEntry, readIl2cppString,
    s,
} from "../il2cpp/helpers.js";
import { createManagedString, invokeMethod } from "../il2cpp/invoke.js";
import { queueOnMainThread } from "../runtime/queue.js";
import { state } from "../game/state.js";
import { aiControlClass } from "../game/ai-control.js";
import { getTraceOrigin, OriginBuffers } from "../game/trace-origin.js";

// Cache the System.String Il2CppClass* once at module load. The hook on
// Dictionary<string,int>.TryGetValue actually fires for ALL reference-typed
// generic instantiations of Dict<TKey,int> because IL2CPP uses "generic
// sharing" — the same compiled method body serves every Dict<refType,int>.
// Comparing args[1].readPointer() (= the key object's class ptr) against
// this cached System.String class lets us cleanly filter to genuine string
// keys without paying class_get_name's cost on every call.
//
// Source confirmed by Gemini: IL2CPP gshared (generic sharing for reference
// types) is the cause of the cross-instantiation hook fires we observed
// (~85% value-by-value, ~12% struct-by-ref, ~1.6% TileEntity, ~3% string).
const systemStringClass = findClassAnywhere("System", "String");

// Resolve il2cpp_type_get_name once — this gives us the qualified name of a
// closed generic class (e.g., "System.Collections.Generic.Dictionary`2[System.String,System.Int32]"),
// way more useful than class_get_name's unqualified "Dictionary`2".
const il2cppLib = Process.findModuleByName("GameAssembly.dll");
const _class_get_type_local = il2cppLib?.findExportByName("il2cpp_class_get_type")
    ? new NativeFunction(
        il2cppLib.findExportByName("il2cpp_class_get_type")!,
        "pointer", ["pointer"]) : null;
const _type_get_name = il2cppLib?.findExportByName("il2cpp_type_get_name")
    ? new NativeFunction(
        il2cppLib.findExportByName("il2cpp_type_get_name")!,
        "pointer", ["pointer"]) : null;

// Backup resolver that returns the assembly-qualified name. Used only if
// il2cpp_type_get_name returns something incomplete (we observed empty
// strings for some shared-generic cases).
const _type_get_aqname = il2cppLib?.findExportByName(
    "il2cpp_type_get_assembly_qualified_name")
    ? new NativeFunction(
        il2cppLib.findExportByName(
            "il2cpp_type_get_assembly_qualified_name")!,
        "pointer", ["pointer"]) : null;

/** Get the qualified type name of an Il2CppClass*, e.g. for the closed
 * generic `Dictionary<string,int>` returns its full instantiation name with
 * all type args expanded recursively (IL2CPP type API does this natively
 * since type args are baked into metadata for closed generics).
 *
 * Resolution order:
 *   1. il2cpp_type_get_name → "Namespace.Foo`1[Bar]" (preferred — concise)
 *   2. il2cpp_type_get_assembly_qualified_name → "Namespace.Foo`1[[…, Asm, …]], …"
 *      (verbose but always-complete fallback)
 *   3. class_get_name → "Foo`1" (last resort, no type args)
 */
function getClassQualifiedName(klass: NativePointer): string {
    if (klass.isNull()) return "";
    let il2Type: NativePointer | null = null;
    try {
        if (_class_get_type_local) {
            const t = _class_get_type_local(klass) as NativePointer;
            if (!t.isNull()) il2Type = t;
        }
    } catch { /* */ }
    if (il2Type && _type_get_name) {
        try {
            const namePtr = _type_get_name(il2Type) as NativePointer;
            if (!namePtr.isNull()) {
                const n = namePtr.readUtf8String();
                if (n && n.length > 0) return n;
            }
        } catch { /* */ }
    }
    if (il2Type && _type_get_aqname) {
        try {
            const namePtr = _type_get_aqname(il2Type) as NativePointer;
            if (!namePtr.isNull()) {
                const n = namePtr.readUtf8String();
                if (n && n.length > 0) return n;
            }
        } catch { /* */ }
    }
    try {
        return s(class_get_name(klass) as NativePointer);
    } catch { return "<?>"; }
}

// --- Resolve the classes we care about ---

const utilitiesDatabaseClass = findClass(
    "BattleLogicAssembly.dll",
    "IdunBattle.Core.Services", "UtilitiesDatabase");

const getUtilityConfigMi = utilitiesDatabaseClass
    ? findMethod(utilitiesDatabaseClass, "GetUtilityConfig") : null;

// We capture ONLY the mirror runner's UtilitiesDatabase, not the live one.
// `state.buildingMirror` is set by sim-engine.buildMirrorFromLive while
// it's calling buildRunner; the DefaultGroupOperator..ctor that fires
// during that window belongs to the mirror — that's the one we instrument.
//
// Two reasons for this scoping:
//   1) Avoid hook overhead on the live AI's hot path during normal play
//      (TryGetValue/get_Item are called thousands of times per turn).
//   2) Keep mirror-side experiments (weight tweaks, bypasses, …) from
//      touching live runner state — the mirror is the sandbox.
const groupOperatorClass = findClass(
    "BattleLogicAssembly.dll",
    "IdunBattle.AI.OperationalDeciders", "DefaultGroupOperator");

let mirrorUtilitiesDb: NativePointer | null = null;
/** Live runner ptr captured at the most recent mirror build. Used as match
 * identity: re-mirroring the same battle leaves this unchanged → keep the
 * trace; mirroring a different battle changes it → wipe. */
let lastMirroredLiveRunner: string | null = null;
let utilitiesDbCtorHookInstalled = false;
function ensureUtilitiesDbCapture(): void {
    if (utilitiesDbCtorHookInstalled || !groupOperatorClass) return;
    const ctor = findMethod(groupOperatorClass, ".ctor");
    if (!ctor || ctor.ptr.isNull()) return;
    Interceptor.attach(ctor.ptr, {
        onEnter(args) {
            // Skip if this ctor is from the live runner (= !state.buildingMirror).
            // We only care about the mirror's UtilitiesDatabase.
            if (!state.buildingMirror) return;
            // Signature: ctor(state, aiQuery, logger, utilitiesDatabase, aiLogger)
            // Frida instance method: [this, state, aiQuery, logger, utilDb, aiLogger]
            const db = args[4];
            if (!db.isNull()) {
                mirrorUtilitiesDb = db;
                // Identify the match by the live runner ptr: same runner →
                // same battle, different runner → new battle. Re-mirroring
                // the same battle should preserve accumulated trace data so
                // the user can keep stacking observations (e.g., multiple AI
                // turns within one game). A new battle wipes everything.
                const liveRunnerPtr = state.liveRunner?.toString() ?? null;
                const sameMatch = liveRunnerPtr !== null
                    && liveRunnerPtr === lastMirroredLiveRunner;
                lastMirroredLiveRunner = liveRunnerPtr;
                // knownConfigs always re-populated — even within the same
                // match, the new mirror has fresh UtilityConfig instances
                // at different ptrs so the prior bindings are stale.
                knownConfigs.clear();
                if (!sameMatch) {
                    trace.buffer.clear();
                    trace.counters.clear();
                    trace.seq = 0;
                    trace.diag.tryGetValueFires = 0;
                    trace.diag.tryGetValueMatchedKnown = 0;
                    trace.diag.getItemFires = 0;
                    trace.diag.getItemMatchedKnown = 0;
                    trace.diag.liveAiFires = 0;
                    trace.diag.mirrorFires = 0;
                }
                const stats = prePopulateKnownConfigs();
                send({
                    t: "diag",
                    msg: "[ai-util-trace] captured mirror UtilitiesDatabase="
                        + db + " · liveRunner=" + liveRunnerPtr
                        + " · sameMatch=" + sameMatch
                        + " · auto-populated=" + stats.populated + " configs"
                        + (sameMatch ? " · trace kept" : " · trace reset"),
                });
            }
        },
    });
    Interceptor.flush();
    utilitiesDbCtorHookInstalled = true;
}

const utilityConfigClass = findClass(
    "BattleLogicAssembly.dll",
    "IdunBattle.Configuration", "UtilityConfig");

// `UtilityConfig` extends `Dictionary<string, int>`. The inherited methods
// (TryGetValue, get_Item) are owned by the closed generic Dictionary class,
// which is `il2cpp_class_get_parent(utilityConfigClass)`. Walk the chain
// + find the methods by name+param count.
const il2cppExp = (name: string): NativePointer => {
    const lib = Process.findModuleByName("GameAssembly.dll");
    if (!lib) throw new Error("GameAssembly.dll not loaded");
    const p = lib.findExportByName(name);
    if (!p) throw new Error("missing export: " + name);
    return p;
};
const class_get_parent = new NativeFunction(
    il2cppExp("il2cpp_class_get_parent"), "pointer", ["pointer"]);

function findInheritedMethod(
    cls: NativePointer, name: string, paramCount: number,
): { ptr: NativePointer; info: NativePointer; klass: NativePointer } | null {
    let k = cls;
    while (!k.isNull()) {
        const it = Memory.alloc(Process.pointerSize);
        it.writePointer(ptr(0));
        let m: NativePointer;
        while (!(m = class_get_methods(k, it) as NativePointer).isNull()) {
            if (s(method_get_name(m) as NativePointer) !== name) continue;
            try {
                if ((method_get_param_count(m) as number) === paramCount) {
                    return { ptr: methodEntry(m), info: m, klass: k };
                }
            } catch { /* skip */ }
        }
        k = class_get_parent(k) as NativePointer;
    }
    return null;
}

// TryGetValue(string key, out int value) → 2 params
// (the `out` parameter is a pointer to an int the method writes)
const tryGetValueRef = utilityConfigClass
    ? findInheritedMethod(utilityConfigClass, "TryGetValue", 2) : null;

// get_Item(string key) → 1 param, returns int
const getItemRef = utilityConfigClass
    ? findInheritedMethod(utilityConfigClass, "get_Item", 1) : null;

// set_Item(string key, int value) → 2 params, void return — used by the
// patcher RPC to mutate runtime UtilityConfig values.
const setItemRef = utilityConfigClass
    ? findInheritedMethod(utilityConfigClass, "set_Item", 2) : null;

// --- Trace state ---

interface UtilityConfigBinding {
    type: number;
    typeName: string;
    collection: number;
    collectionName: string;
}

const knownConfigs: Map<string, UtilityConfigBinding> = new Map();

/** Allowlist of dict CLASS pointers (resolved once at module load) → friendly
 * name. The hook reads args[0].readPointer() (= the dict's Il2CppClass*)
 * and looks it up here for an O(1) decision: skip if not in the map.
 *
 * Avoids the per-call cost of `il2cpp_class_get_type` + `il2cpp_type_get_name`
 * we used to pay during the discovery phase. With this fast-path, every hook
 * fire on an irrelevant dict (UI dicts, ability registries, …) costs just
 * `args[0].readPointer()` + `Map.get()` + early return. */
const trackedClasses = new Map<string, string>();
function registerTrackedClass(
    klass: NativePointer | null, friendlyName: string,
): void {
    if (!klass || klass.isNull()) return;
    trackedClasses.set(klass.toString(), friendlyName);
}
registerTrackedClass(
    findClass("BattleLogicAssembly.dll",
        "IdunBattle.Configuration", "UtilityConfig"),
    "IdunBattle.Configuration.UtilityConfig");
registerTrackedClass(
    findClass("BattleLogicAssembly.dll",
        "IdunBattle.Configuration", "UtilitiesConfigCollection"),
    "IdunBattle.Configuration.UtilitiesConfigCollection");
registerTrackedClass(
    findClass("BattleLogicAssembly.dll",
        "IdunBattle.Configuration", "UtilitiesConfiguration"),
    "IdunBattle.Configuration.UtilitiesConfiguration");

/** Resolve owner type by class-ptr lookup in the allowlist. Returns null
 * (= skip this hook fire) for any class we don't track. */
function getOwnerType(dictPtr: NativePointer): string | null {
    let klass: NativePointer;
    try { klass = dictPtr.readPointer(); }
    catch { return null; }
    if (klass.isNull()) return null;
    return trackedClasses.get(klass.toString()) ?? null;
}

/** Diagnostic sampler — when enabled, captures the qualified type names of
 * dicts the AI consults during a live turn but that fall outside our tracked
 * classes. Used to spot when our allowlist drifts (e.g., agent class ptr ≠
 * runtime class ptr after a Tacticus restart) or when the AI uses a Dict
 * type we haven't catalogued yet. Capped at sampleCap to avoid log spam. */
const diagSampler = {
    enabled: false,
    sampleCap: 30,
    samples: new Map<string, { friendlyName: string; count: number }>(),
};
function sampleUntrackedDict(klass: NativePointer): void {
    if (!diagSampler.enabled) return;
    const k = klass.toString();
    const existing = diagSampler.samples.get(k);
    if (existing) {
        existing.count++;
        return;
    }
    if (diagSampler.samples.size >= diagSampler.sampleCap) return;
    let name = "<resolution-failed>";
    try { name = getClassQualifiedName(klass); } catch { /* keep default */ }
    diagSampler.samples.set(k, { friendlyName: name, count: 1 });
}

interface AccessEntry {
    /** monotonic seq number — easier to correlate with ai-trace L3 events */
    seq: number;
    /** runner du RPC déclencheur (null = IA live) — posé centralement par
     * pushAccess (cf. game/trace-origin.ts) */
    originRunnerId?: number | null;
    ts: number;
    configPtr: string;
    /** Qualified type name of the dict instance — tells us EXACTLY what
     * Dict<TKey,TValue> closed generic this is, eg
     * "System.Collections.Generic.Dictionary`2[BEntityId,Int32]". Resolved
     * via il2cpp_class_get_type → il2cpp_type_get_name. */
    ownerType: string;
    /** "TryGetValue" or "get_Item" */
    op: string;
    typeName: string;
    collectionName: string;
    key: string | null;
    /** TryGetValue: the int filled into `out`. get_Item: the return int. */
    value: number | null;
    /** TryGetValue: bool returned (was key found). get_Item: always true. */
    found: boolean | null;
    /** Which AI context fired the hook. "live" = a live AiControl.ApplyAiMessage
     * was on the stack (real game AI playing its turn); "mirror" = mirror replay
     * during simRunAiTurn Phase 1. */
    source: "live" | "mirror";
    /** Player id whose turn was active at fire time (sampled by the recorder
     * when the AI message hook entered). null until first AI msg. */
    turnPlayer: number | null;
    /** In-game "Turn N" — count of turns started by the current player
     * (matches the in-game UI's turn counter). null until first AI msg. */
    turnRound: number | null;
    /** Monotonic counter — bumps each time turnPlayer flips. Lets analysis
     * group all entries from a single contiguous turn window. */
    turnSegment: number;
}

interface TraceState {
    enabled: boolean;
    seq: number;
    /** Ring buffers PAR ORIGINE (cf. game/trace-origin.ts) — drop oldest when
     * full, cap PAR BUCKET. Sized for ~1 turn of AI scoring
     * (53 utilities × 100 candidate tiles × 2 dict accesses ≈ 10k entries). */
    buffer: OriginBuffers<AccessEntry>;
    /** Listeners installed by enable() — kept so disable() can detach. */
    listeners: InvocationListener[];
    /** Per-key read counters — useful summary view without dumping the
     * full buffer. Keyed as `${source}|${ownerType}:${key}`, so live + mirror
     * counts are separate (analysis usually wants one or the other, not the
     * sum — mirror replays of past turns shouldn't pollute the live AI signal). */
    counters: Map<string, number>;
    /** Multi-capture: collect up to N **distinct** callstacks (deduped by
     * top-frame RVA) at every tryGetValueRef fire and at every
     * AiControl.ExecuteMovementFor entry. Lets us see the actual AI scoring
     * path *and* the move-execution path side by side. */
    callstacksMax: number;
    callstacks: Array<{
        origin: "tryGetValue" | "executeMove" | "executeAbility";
        source: "live" | "mirror";
        topRva: number;
        frames: string[];
        ts: number;
    }>;
    /** Lightweight diagnostic counters — fast-path tracks total hook fires
     * (incremented before the allowlist filter) so we can see how many calls
     * we're skipping. Slow-path counters increment only after the filter. */
    diag: {
        tryGetValueFires: number;
        tryGetValueMatchedKnown: number;
        getItemFires: number;
        getItemMatchedKnown: number;
        /** Fires attributed to a live AI turn (state.liveAiRunning=true). */
        liveAiFires: number;
        /** Fires attributed to mirror replay (state.captureMirrorMessages=true). */
        mirrorFires: number;
    };
}

const trace: TraceState = {
    // Enabled by default — hooks are gated by trace.enabled but the install
    // is unconditional at boot, so any RUN AI TURN immediately captures
    // dict accesses without manual setup. Disable via aiUtilityTraceDisable
    // if the overhead becomes a problem.
    enabled: true,
    seq: 0,
    buffer: new OriginBuffers<AccessEntry>(20000, "ring"),
    listeners: [],
    counters: new Map(),
    diag: {
        tryGetValueFires: 0,
        tryGetValueMatchedKnown: 0,
        getItemFires: 0,
        getItemMatchedKnown: 0,
        liveAiFires: 0,
        mirrorFires: 0,
    },
    callstacksMax: 20,
    callstacks: [],
};

/** Read MatchState.IsAiRunning (offset 0x58) on the live runner. Defensive —
 * returns false if pointers are stale or the read fails. Used as a broad
 * gating signal: the live AI's scoring runs in a coroutine that's NOT inside
 * an ApplyAiMessage call, so `state.liveAiRunning` (set per-message) misses
 * the entire scoring window. IsAiRunning stays true across the whole turn. */
function liveIsAiRunning(): boolean {
    const live = state.liveRunner;
    if (!live) return false;
    try {
        // runnerOff.state is the IdunRunner._state field offset.
        // Hardcoded here to avoid an extra import — cheap u8 read.
        const liveState = live.add(0x40).readPointer();
        if (liveState.isNull()) return false;
        return liveState.add(0x58).readU8() !== 0;
    } catch { return false; }
}

/** Capture a backtrace as RVAs and store it deduped by top-frame. Caps at
 * `trace.callstacksMax` distinct stacks. Cheap: hot-path reads ≈ 32 frames,
 * dedup by `topRva` is O(1) Set lookup. */
function captureStack(
    ctx: CpuContext,
    origin: "tryGetValue" | "executeMove" | "executeAbility",
    source: "live" | "mirror",
): void {
    if (trace.callstacks.length >= trace.callstacksMax) return;
    let topRva = -1;
    const frames: string[] = [];
    try {
        const bt = Thread.backtrace(ctx, Backtracer.ACCURATE);
        for (let i = 0; i < Math.min(bt.length, 32); i++) {
            const off = bt[i].sub(il2cppBase);
            const inIl2cpp = off.compare(0) >= 0
                && off.compare(il2cppSize) < 0;
            if (i === 0 && inIl2cpp) topRva = off.toInt32();
            frames.push(inIl2cpp
                ? "rva:0x" + off.toString(16)
                : "abs:" + bt[i].toString());
        }
    } catch (e) {
        frames.push("<failed: " + (e as Error).message + ">");
    }
    // Dedup by (origin, topRva): same hot loop fires thousands of times,
    // we only want one specimen per unique entry point.
    for (const c of trace.callstacks) {
        if (c.origin === origin && c.topRva === topRva) return;
    }
    trace.callstacks.push({ origin, source, topRva, frames, ts: Date.now() });
}

// --- Enum name lookup (from sources_win UtilityType.cs / UtilityConfigCollectionType.cs) ---

const UTILITY_TYPE_NAMES: Record<number, string> = {
    0: "Spawn", 1: "SingleAdjacency", 2: "TriggeredAbilities",
    3: "UnitSpecificBehaviours", 4: "TriggeredAbilitiesNonOwner",
    5: "UnitMovementFromTemporary", 6: "UnitMovement", 7: "Tile",
    8: "Elevation", 9: "TileEffects", 10: "UnitEffectsAdjacent",
    11: "UnitEffectsSurrounding", 12: "UnitEffectsRanged",
    13: "TemporaryTile", 14: "TilePendingBlockableSummon",
    15: "RangedAdjacentEnemy", 16: "MinDistanceToClosestEnemy",
    17: "MaxDistanceToUnitTile", 18: "MaxDistanceToEnemies",
    19: "SteppableUnit", 20: "KustomForceField",
    21: "DefenderOfTheGreaterGood", 22: "SaviorProtocols",
    23: "MoltenForm", 24: "CapturePoint", 25: "AdjacentToadstool",
    26: "TreeAncientHeal", 27: "Contaminated", 28: "PowerUp",
    29: "DislikeStartingTilesUtility", 30: "DespoiledGround",
    31: "SummonDislikeDoorOpening", 32: "HeroLikeDoorOpening",
    33: "EnvEndBombardment", 34: "MovementSuggestion",
    35: "TileDistance", 36: "Damage", 37: "DamageDealt",
    38: "KillUnit", 39: "OverkillUnit", 40: "DislikeObjects",
    41: "DislikeEnvironmentUnits", 42: "OnlyImperviousUnitIfCanBeDamaged",
    43: "EnemyOnTerritoryTile", 44: "AttackTargetWithEffect",
    45: "Heal", 46: "AddedTileEffects", 47: "Repair",
    48: "RepairedAmount", 49: "DanceOfDaggers",
    50: "AdjacentQuickSlash", 51: "RoyalGuard_AvoidAdjacentEnemies",
    52: "SwornProtector_AvoidAdjacentEnemies",
    53: "DevoutPush_AdjacentRangedEnemies",
    54: "RammingSpeed_MostAdjacentEnemies",
    55: "WireweaveNet_FirstAttack",
    56: "MV71SniperDroneSquad_ClosestToParent",
    57: "EarlyWarningOverride_SpawnSummon",
    58: "DoctrinaImperatives_AttractMechanicals",
    59: "EchoesFromTheWarp_FriendliesAvoidGhost",
    60: "OptimizedGait_AdjacentFriends",
    61: "Phantasm_AvoidFriendlyPhantasm",
    62: "BioMinefield_MoveTowardsTarget",
    63: "MasterOfTheTutelaries_MoveTowardsTarget",
    64: "HypersensoryAbilities_BonusForFirstAttack",
    65: "DecoysAndMisdirection_AttractToDecoys",
    66: "TheArdentBlade_Geminae", 67: "LeadingTheCharge_ChargeTile",
    68: "ActiveAbilities", 69: "PreferNonBoss",
    70: "PreferFreshlySpawned", 71: "MinPossibleNormalAttackTarget",
    72: "UnitWithShortestPathToEnemy", 73: "Remaining",
    74: "PreferAbilities", 75: "PreferSummons",
    76: "LastAbilities", 77: "UnitOrder", 78: "Random",
    79: "AdjacentHarmonizedFriend", 80: "PsychicFortress",
    81: "NoMovementToTileWithAdjacentEnemies",
};

const COLLECTION_NAMES: Record<number, string> = {
    0: "Default", 1: "SummonIceElemental", 2: "MovementSuggestion",
};

// --- Hook installation ---

type CaptureMarker = InvocationContext & {
    _ucKey?: string;
    _ucConfigPtr?: string;
    _ucOwnerType?: string;
    _ucBinding?: UtilityConfigBinding;
    _ucOutPtr?: NativePointer;
    /** Snapshot of which AI context fired this hook (live vs mirror) — taken
     * at onEnter so the onLeave dispatch sees the same source even if the
     * flags flipped between the two callbacks (extremely rare but possible
     * if the AI window closed mid-call). */
    _ucSource?: "live" | "mirror";
    _gciCall?: { type: number; collection: number };
};

// Owner-type allowlist. Only push entries from these dict types — drops
// the firehose of ability/effect/pool registry lookups that share our
// gshared hook but don't carry AI weight tuning info.
//
// We keep `UtilityConfig` (where the actual key→int reads happen) AND its
// two wrappers because Phase 1 of GetUtilityConfig traverses them en route
// to the leaf, and the wrapper traversals are useful breadcrumbs.
const TRACE_OWNER_ALLOWLIST = new Set([
    "IdunBattle.Configuration.UtilityConfig",
    "IdunBattle.Configuration.UtilitiesConfigCollection",
    "IdunBattle.Configuration.UtilitiesConfiguration",
]);

function pushAccess(entry: AccessEntry): void {
    if (!TRACE_OWNER_ALLOWLIST.has(entry.ownerType)) return;
    entry.originRunnerId = getTraceOrigin();   // chokepoint central — attribution runner
    trace.buffer.push(entry);
    const ck = entry.source + "|" + entry.ownerType
        + ":" + (entry.key ?? "<no-key>");
    trace.counters.set(ck, (trace.counters.get(ck) ?? 0) + 1);
}

function installHooks(): boolean {
    if (trace.listeners.length > 0) return true;

    if (!getUtilityConfigMi || getUtilityConfigMi.ptr.isNull()) {
        send({ t: "diag", msg: "[ai-util-trace] GetUtilityConfig not resolved" });
        return false;
    }

    // We deliberately don't hook GetUtilityConfig here. Registration of
    // UtilityConfig pointers is done manually by prePopulateKnownConfigs()
    // using the mirror's captured UtilitiesDatabase only — that scopes the
    // trace to the mirror and avoids picking up live-runner configs.

    // Hook 2: TryGetValue on UtilityConfig instances
    if (tryGetValueRef && !tryGetValueRef.ptr.isNull()) {
        trace.listeners.push(Interceptor.attach(tryGetValueRef.ptr, {
            onEnter(this: CaptureMarker, args) {
                if (!trace.enabled) return;
                // Fire during mirror replay (Phase 1 simRunAiTurn), during
                // a live ApplyAiMessage window, OR anywhere in the broader
                // live-AI coroutine (IsAiRunning=true). The third case is
                // critical for the *scoring* phase, which runs OUTSIDE
                // ApplyAiMessage and was previously invisible to us.
                const inLiveAi = state.liveAiRunning || liveIsAiRunning();
                if (!state.captureMirrorMessages && !inLiveAi) return;
                trace.diag.tryGetValueFires++;
                const source: "live" | "mirror" =
                    inLiveAi ? "live" : "mirror";
                if (source === "live") trace.diag.liveAiFires++;
                else trace.diag.mirrorFires++;
                // Multi-capture: dedup by top-frame RVA so we collect every
                // distinct call-site that hits TryGetValue, up to the cap.
                captureStack(this.context, "tryGetValue", source);
                // Fast-path early exit: if args[0]'s class isn't in our
                // allowlist (UtilityConfig + 2 wrappers), bail out before
                // doing ANY string work. Saves the bulk of the cost on the
                // ~20k fires that aren't ours.
                const thisPtr = args[0];
                const ownerType = getOwnerType(thisPtr);
                if (ownerType === null) {
                    // Diagnostic: sample the dict's class for offline inspection
                    // (only when sampler is enabled and we're in a live AI
                    // window — avoids overhead during regular play).
                    if (diagSampler.enabled && source === "live") {
                        try { sampleUntrackedDict(thisPtr.readPointer()); }
                        catch { /* ignore */ }
                    }
                    return;
                }
                const cfgKey = thisPtr.toString();
                this._ucConfigPtr = cfgKey;
                this._ucOwnerType = ownerType;
                this._ucSource = source;
                this._ucBinding = knownConfigs.get(cfgKey) ?? {
                    type: -1, typeName: "<unknown>",
                    collection: -1, collectionName: "<unknown>",
                };
                // Key parsing — args[1] is either:
                //   - System.String for UtilityConfig (the leaf reads)
                //   - Enum value-type by-ref for the wrappers
                //     (UtilityType / UtilityConfigCollectionType)
                // Filter at args[1].class equality vs cached String class
                // for the leaf; for the wrappers we don't need the key
                // (just record the traversal).
                const keyArg = args[1];
                if (keyArg.compare(ptr("0x10000")) <= 0) {
                    this._ucKey = "<primitive>";
                } else {
                    try {
                        const klass = keyArg.readPointer();
                        if (klass.isNull()) {
                            this._ucKey = "<klass-null>";
                        } else if (systemStringClass
                            && klass.equals(systemStringClass)) {
                            const k = readIl2cppString(keyArg);
                            this._ucKey = k ?? "<empty-string>";
                        } else {
                            this._ucKey = "<enum-by-ref>";
                        }
                    } catch {
                        this._ucKey = "<av>";
                    }
                }
                this._ucOutPtr = args[2];
            },
            onLeave(this: CaptureMarker, retval) {
                if (!this._ucBinding) return;
                if (!state.captureMirrorMessages
                    && !state.liveAiRunning) return;
                // Keep noise entries in the buffer/counters so we can dig
                // into the struct-by-ref layouts further (separate "samples"
                // captures details per noise category — see capture logic
                // in onEnter and the noiseSamples map below).
                let value: number | null = null;
                try { value = this._ucOutPtr?.readS32() ?? null; }
                catch { /* ignore */ }
                pushAccess({
                    seq: ++trace.seq,
                    ts: Date.now(),
                    configPtr: this._ucConfigPtr ?? "?",
                    ownerType: this._ucOwnerType ?? "?",
                    op: "TryGetValue",
                    typeName: this._ucBinding.typeName,
                    collectionName: this._ucBinding.collectionName,
                    key: this._ucKey ?? null,
                    value,
                    found: retval.toInt32() !== 0,
                    source: this._ucSource ?? "live",
                    turnPlayer: state.currentTurnPlayer,
                    turnRound: state.currentTurnRound,
                    turnSegment: state.turnSegment,
                });
            },
        }));
    }

    // Hook 3: get_Item on UtilityConfig instances (returns int directly)
    if (getItemRef && !getItemRef.ptr.isNull()) {
        trace.listeners.push(Interceptor.attach(getItemRef.ptr, {
            onEnter(this: CaptureMarker, args) {
                if (!trace.enabled) return;
                if (!state.captureMirrorMessages
                    && !state.liveAiRunning) return;
                trace.diag.getItemFires++;
                const thisPtr = args[0];
                const cfgKey = thisPtr.toString();
                const binding = knownConfigs.get(cfgKey);
                if (!binding) return;
                trace.diag.getItemMatchedKnown++;
                this._ucConfigPtr = cfgKey;
                this._ucOwnerType = getOwnerType(thisPtr) ?? undefined;
                this._ucBinding = binding;
                this._ucSource = state.liveAiRunning ? "live" : "mirror";
                try {
                    this._ucKey = readIl2cppString(args[1]) ?? "<unreadable>";
                } catch { this._ucKey = "<exception>"; }
            },
            onLeave(this: CaptureMarker, retval) {
                if (!this._ucBinding) return;
                pushAccess({
                    seq: ++trace.seq,
                    ts: Date.now(),
                    configPtr: this._ucConfigPtr ?? "?",
                    ownerType: this._ucOwnerType ?? "?",
                    op: "get_Item",
                    typeName: this._ucBinding.typeName,
                    collectionName: this._ucBinding.collectionName,
                    key: this._ucKey ?? null,
                    value: retval.toInt32(),
                    found: true,
                    source: this._ucSource ?? "live",
                    turnPlayer: state.currentTurnPlayer,
                    turnRound: state.currentTurnRound,
                    turnSegment: state.turnSegment,
                });
            },
        }));
    }

    // Hook 4: AiControl.ExecuteMovementFor — captures the call-stack at the
    // *moment of move execution*. The frame above us is the AI tactic that
    // chose this destination, so the backtrace exposes the decision pipeline.
    if (aiControlClass) {
        const execMoveMi = findMethod(aiControlClass, "ExecuteMovementFor");
        if (execMoveMi && !execMoveMi.ptr.isNull()) {
            trace.listeners.push(Interceptor.attach(execMoveMi.ptr, {
                onEnter() {
                    captureStack(this.context, "executeMove",
                        liveIsAiRunning() ? "live" : "mirror");
                },
            }));
        }
        const execAbilityMi = findMethod(aiControlClass, "ExecuteAbilityFor")
            ?? findMethod(aiControlClass, "ExecuteAbilityActionFor");
        if (execAbilityMi && !execAbilityMi.ptr.isNull()) {
            trace.listeners.push(Interceptor.attach(execAbilityMi.ptr, {
                onEnter() {
                    captureStack(this.context, "executeAbility",
                        liveIsAiRunning() ? "live" : "mirror");
                },
            }));
        }
    }

    Interceptor.flush();
    send({
        t: "diag",
        msg: "[ai-util-trace] hooks installed: GetUtilityConfig="
            + (!getUtilityConfigMi.ptr.isNull() ? "ok" : "FAIL")
            + " · TryGetValue=" + (tryGetValueRef ? "ok" : "missing")
            + " · get_Item=" + (getItemRef ? "ok" : "missing")
            + " · ExecuteMove="
            + (aiControlClass ? "scanning" : "<no AiControl class>")
            + " · listeners=" + trace.listeners.length,
    });
    return true;
}

function detachHooks(): void {
    for (const l of trace.listeners) {
        try { l.detach(); } catch { /* ignore */ }
    }
    trace.listeners = [];
}

// --- Pre-populate knownConfigs: iterate every (UtilityType × Collection)
//     and call GetUtilityConfig via invokeMethod, registering the returned
//     config ptr. Counts on the live UtilitiesDatabase being captured. ---

function prePopulateKnownConfigs(): {
    populated: number; skipped: number; reason?: string;
} {
    if (!mirrorUtilitiesDb) {
        return {
            populated: 0, skipped: 0,
            reason: "no mirror UtilitiesDatabase captured yet — click MIRROR NOW first",
        };
    }
    if (!getUtilityConfigMi || getUtilityConfigMi.ptr.isNull()) {
        return { populated: 0, skipped: 0,
            reason: "GetUtilityConfig method not resolved" };
    }
    const enumArg = Memory.alloc(4);
    const collArg = Memory.alloc(4);
    let populated = 0, skipped = 0;
    for (const [typeStr, typeName] of Object.entries(UTILITY_TYPE_NAMES)) {
        const typeVal = Number(typeStr);
        for (const [collStr, collName] of Object.entries(COLLECTION_NAMES)) {
            const collVal = Number(collStr);
            enumArg.writeS32(typeVal);
            collArg.writeS32(collVal);
            try {
                const cfg = invokeMethod(
                    getUtilityConfigMi.info, mirrorUtilitiesDb,
                    [enumArg, collArg]);
                if (!cfg.isNull()) {
                    knownConfigs.set(cfg.toString(), {
                        type: typeVal, typeName,
                        collection: collVal, collectionName: collName,
                    });
                    populated++;
                } else { skipped++; }
            } catch { skipped++; }
        }
    }
    return { populated, skipped };
}

// --- RPCs ---

export function register(ctx: Ctx): void {
    // Install everything proactively at register time so the trace is
    // ready as soon as the user clicks MIRROR NOW + RUN AI TURN — no manual
    // enable step required:
    //   1. UtilitiesDatabase capture (DefaultGroupOperator..ctor hook)
    //   2. Dictionary access hooks (TryGetValue / get_Item) — gated by
    //      trace.enabled (true by default)
    //   3. Auto-populate triggers from #1's onEnter when state.buildingMirror
    //      flips true during sim-engine.buildMirrorFromLive
    ensureUtilitiesDbCapture();
    installHooks();

    /** Install hooks (idempotent) and start collecting. Returns method
     * resolution diagnostics so the front knows what's hooked. */
    ctx.rpc.aiUtilityTraceEnable = (): Promise<unknown> =>
        queueOnMainThread(() => {
            const ok = installHooks();
            // Pre-populate knownConfigs by iterating GetUtilityConfig over
            // every (type × coll). Without this, the TryGetValue/get_Item
            // hooks would skip every call (their filter requires the dict
            // ptr to be in knownConfigs).
            const populate = prePopulateKnownConfigs();
            trace.enabled = ok;
            return {
                ok, enabled: trace.enabled,
                getUtilityConfigResolved:
                    !!getUtilityConfigMi && !getUtilityConfigMi.ptr.isNull(),
                tryGetValueResolved:
                    !!tryGetValueRef && !tryGetValueRef.ptr.isNull(),
                getItemResolved:
                    !!getItemRef && !getItemRef.ptr.isNull(),
                tryGetValueOnClass: tryGetValueRef
                    ? s(class_get_name(tryGetValueRef.klass) as NativePointer)
                    : null,
                getItemOnClass: getItemRef
                    ? s(class_get_name(getItemRef.klass) as NativePointer)
                    : null,
                mirrorUtilitiesDb: mirrorUtilitiesDb?.toString() ?? null,
                knownConfigs: knownConfigs.size,
                populate,
            };
        });

    ctx.rpc.aiUtilityTraceDisable = (): unknown => {
        trace.enabled = false;
        return { ok: true, listeners: trace.listeners.length };
    };

    ctx.rpc.aiUtilityTraceClear = (body?: { runnerId?: number }): unknown => {
        if (typeof body?.runnerId === "number") {
            // Clear SCOPÉ multi-acteur : drop le bucket de CE runner (les
            // compteurs agrégés restent globaux — granularité assumée, ils
            // ne sont pas rejouables par-runner).
            trace.buffer.clear(body.runnerId);
            return { ok: true, remaining: trace.buffer.size() };
        }
        trace.buffer.clear();
        trace.counters.clear();
        trace.seq = 0;
        trace.diag.tryGetValueFires = 0;
        trace.diag.tryGetValueMatchedKnown = 0;
        trace.diag.getItemFires = 0;
        trace.diag.getItemMatchedKnown = 0;
        trace.diag.liveAiFires = 0;
        trace.diag.mirrorFires = 0;
        return { ok: true };
    };

    /** Dump the current buffer. Body: { since?: seq, max?: number }
     * - since: only entries with seq > since
     * - max: cap returned count (default 1000) */
    ctx.rpc.aiUtilityTraceDump = (
        body?: { since?: number; max?: number; runnerId?: number },
    ): unknown => {
        const since = body?.since ?? 0;
        const max = body?.max ?? 1000;
        let filtered = trace.buffer.entries(body?.runnerId);
        if (since > 0) filtered = filtered.filter((e) => e.seq > since);
        const slice = filtered.slice(-max);
        return {
            enabled: trace.enabled,
            totalSeq: trace.seq,
            bufferSize: trace.buffer.size(),
            knownConfigs: knownConfigs.size,
            returned: slice.length,
            entries: slice,
        };
    };

    /** Aggregated counters: how many times each (source, ownerType, key) was
     * read. Lets us identify hot keys without scanning the full buffer.
     * `ownerType` is the qualified Dict<TKey,TValue> generic instantiation,
     * eg `IdunBattle.Configuration.UtilityConfig`. `source` is "live" (live
     * AI turn) or "mirror" (simRunAiTurn replay) — separated so analysis
     * can focus on one without the other contaminating the signal. */
    ctx.rpc.aiUtilityTraceCounters = (): unknown => {
        const out: Array<{
            source: "live" | "mirror";
            ownerType: string; key: string; count: number;
        }> = [];
        for (const [k, v] of trace.counters) {
            const pipe = k.indexOf("|");
            const source = pipe >= 0 ? k.slice(0, pipe) : "live";
            const rest = pipe >= 0 ? k.slice(pipe + 1) : k;
            const colon = rest.indexOf(":");
            out.push({
                source: source as "live" | "mirror",
                ownerType: colon >= 0 ? rest.slice(0, colon) : rest,
                key: colon >= 0 ? rest.slice(colon + 1) : "",
                count: v,
            });
        }
        out.sort((a, b) => b.count - a.count);
        return {
            enabled: trace.enabled,
            uniqueKeys: out.length,
            counters: out,
            hookDiag: trace.diag,
            knownConfigs: knownConfigs.size,
            mirrorUtilitiesDb: mirrorUtilitiesDb?.toString() ?? null,
            trackedClasses: [...trackedClasses.values()],
        };
    };

    /** Read the multi-capture buffer of distinct call-stacks. Captured at
     * EVERY tryGetValueRef fire (during live-AI coroutine OR mirror replay)
     * and at every AiControl.ExecuteMovementFor entry, deduped by top-frame
     * RVA, capped at trace.callstacksMax. */
    ctx.rpc.aiUtilityTraceCallstacks = (): unknown => ({
        max: trace.callstacksMax,
        count: trace.callstacks.length,
        callstacks: trace.callstacks,
    });
    /** Wipe the callstack buffer so the next AI turn re-collects fresh. */
    ctx.rpc.aiUtilityTraceCallstacksReset = (): unknown => {
        trace.callstacks = [];
        return { ok: true };
    };

    void detachHooks; // exposed in case we add a "fully uninstall" RPC later

    /** Enable the untracked-dict diag sampler. While enabled, every TryGetValue
     * fire that misses the trackedClasses allowlist samples its class qualified
     * name (capped at sampleCap to bound log spam). Call …DiagDump to read. */
    ctx.rpc.aiUtilityTraceDiagSamplerEnable = (
        body?: { sampleCap?: number },
    ): unknown => {
        diagSampler.enabled = true;
        if (body?.sampleCap) diagSampler.sampleCap = body.sampleCap;
        diagSampler.samples.clear();
        return { ok: true, sampleCap: diagSampler.sampleCap };
    };

    ctx.rpc.aiUtilityTraceDiagSamplerDisable = (): unknown => {
        diagSampler.enabled = false;
        return { ok: true };
    };

    /** Dump the diag sampler's collected (classPtr → friendlyName, count). */
    ctx.rpc.aiUtilityTraceDiagSamplerDump = (): unknown => {
        const out = [...diagSampler.samples.entries()].map(([k, v]) => ({
            classPtr: k, friendlyName: v.friendlyName, count: v.count,
        }));
        out.sort((a, b) => b.count - a.count);
        return {
            enabled: diagSampler.enabled,
            sampleCap: diagSampler.sampleCap,
            distinctClasses: out.length,
            trackedClasses: [...trackedClasses.entries()].map(([ptr, name]) => ({
                classPtr: ptr, friendlyName: name,
            })),
            samples: out,
        };
    };

    /** Patch a UtilityConfig key on a specific runtime config instance.
     *
     * Body: { configPtr: string, key: string, value: number }
     *   - configPtr: pointer string ("0x...") visible in trace entries
     *     (`entry.configPtr`). Must be a live UtilityConfig instance.
     *   - key: string key (e.g. "PerUnitWithAbilityInRange")
     *   - value: new int value to set
     *
     * Invokes Dictionary<string,int>.set_Item via il2cpp on the main thread.
     * Returns the previous value (read via TryGetValue) for verification —
     * if the key didn't exist, prevFound=false and prevValue=0. */
    ctx.rpc.aiUtilityTracePatch = (
        body: { configPtr: string; key: string; value: number },
    ): Promise<unknown> => queueOnMainThread(() => {
        if (!setItemRef || setItemRef.ptr.isNull()) {
            return { ok: false, error: "set_Item not resolved" };
        }
        if (!tryGetValueRef || tryGetValueRef.ptr.isNull()) {
            return { ok: false, error: "TryGetValue not resolved" };
        }
        const cfg = ptr(body.configPtr);
        if (cfg.isNull()) {
            return { ok: false, error: "configPtr is null" };
        }
        // Read the previous value before patching (best-effort).
        let prevValue = 0; let prevFound = false;
        try {
            const outBuf = Memory.alloc(4);
            outBuf.writeS32(0);
            const keyStr = createManagedString(body.key);
            const r = invokeMethod(
                tryGetValueRef.info, cfg, [keyStr, outBuf]);
            // Boxed bool → byte at 0x10 of the boxed object.
            prevFound = !r.isNull() && r.add(0x10).readU8() !== 0;
            prevValue = outBuf.readS32();
        } catch (e) {
            // Read failed — proceed with patch anyway, prev info is just
            // diagnostic.
            send({
                t: "diag", msg: "[ai-util-trace] patch prev-read failed: "
                    + (e as Error).message,
            });
        }
        // Patch via set_Item(string, int). The int is passed as a pointer to
        // a stack-allocated 4-byte buffer (IL2CPP value-type by-ref ABI).
        try {
            const keyStr = createManagedString(body.key);
            const valBuf = Memory.alloc(4);
            valBuf.writeS32(body.value);
            invokeMethod(setItemRef.info, cfg, [keyStr, valBuf]);
        } catch (e) {
            return {
                ok: false, error: "set_Item threw: " + (e as Error).message,
                prevFound, prevValue,
            };
        }
        return {
            ok: true, configPtr: body.configPtr, key: body.key,
            newValue: body.value, prevFound, prevValue,
        };
    });
}
