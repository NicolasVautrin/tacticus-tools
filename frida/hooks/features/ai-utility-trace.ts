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
    method_get_name, method_get_param_count, methodEntry, readIl2cppString,
    s,
} from "../il2cpp/helpers.js";
import { invokeMethod } from "../il2cpp/invoke.js";
import { queueOnMainThread } from "../runtime/queue.js";
import { state } from "../game/state.js";

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
                // Each MIRROR NOW rebuilds the mirror with a fresh
                // UtilitiesDatabase, so pre-populated configs from a prior
                // mirror are stale — drop them.
                knownConfigs.clear();
                // Auto-populate the new mirror's configs so the trace is
                // ready to use without a manual enable step.
                const stats = prePopulateKnownConfigs();
                send({
                    t: "diag",
                    msg: "[ai-util-trace] captured mirror UtilitiesDatabase="
                        + db + " · auto-populated="
                        + stats.populated + " configs",
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
): { ptr: NativePointer; klass: NativePointer } | null {
    let k = cls;
    while (!k.isNull()) {
        const it = Memory.alloc(Process.pointerSize);
        it.writePointer(ptr(0));
        let m: NativePointer;
        while (!(m = class_get_methods(k, it) as NativePointer).isNull()) {
            if (s(method_get_name(m) as NativePointer) !== name) continue;
            try {
                if ((method_get_param_count(m) as number) === paramCount) {
                    return { ptr: methodEntry(m), klass: k };
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

interface AccessEntry {
    /** monotonic seq number — easier to correlate with ai-trace L3 events */
    seq: number;
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
}

interface TraceState {
    enabled: boolean;
    seq: number;
    /** Ring buffer — drops oldest when full. Sized for ~1 turn of AI scoring
     * (53 utilities × 100 candidate tiles × 2 dict accesses ≈ 10k entries). */
    buffer: AccessEntry[];
    bufferMax: number;
    /** Listeners installed by enable() — kept so disable() can detach. */
    listeners: InvocationListener[];
    /** Per-key read counters — useful summary view without dumping the
     * full buffer. Keyed as `${typeName}:${key}`. */
    counters: Map<string, number>;
    /** Lightweight diagnostic counters — fast-path tracks total hook fires
     * (incremented before the allowlist filter) so we can see how many calls
     * we're skipping. Slow-path counters increment only after the filter. */
    diag: {
        tryGetValueFires: number;
        tryGetValueMatchedKnown: number;
        getItemFires: number;
        getItemMatchedKnown: number;
    };
}

const trace: TraceState = {
    // Enabled by default — hooks are gated by trace.enabled but the install
    // is unconditional at boot, so any RUN AI TURN immediately captures
    // dict accesses without manual setup. Disable via aiUtilityTraceDisable
    // if the overhead becomes a problem.
    enabled: true,
    seq: 0,
    buffer: [],
    bufferMax: 20000,
    listeners: [],
    counters: new Map(),
    diag: {
        tryGetValueFires: 0,
        tryGetValueMatchedKnown: 0,
        getItemFires: 0,
        getItemMatchedKnown: 0,
    },
};

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
    if (trace.buffer.length >= trace.bufferMax) {
        trace.buffer.shift();
    }
    trace.buffer.push(entry);
    const ck = entry.ownerType + ":" + (entry.key ?? "<no-key>");
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
                if (!state.captureMirrorMessages) return;
                trace.diag.tryGetValueFires++;
                // Fast-path early exit: if args[0]'s class isn't in our
                // allowlist (UtilityConfig + 2 wrappers), bail out before
                // doing ANY string work. Saves the bulk of the cost on the
                // ~20k fires that aren't ours.
                const thisPtr = args[0];
                const ownerType = getOwnerType(thisPtr);
                if (ownerType === null) return;
                const cfgKey = thisPtr.toString();
                this._ucConfigPtr = cfgKey;
                this._ucOwnerType = ownerType;
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
                if (!state.captureMirrorMessages) return;
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
                });
            },
        }));
    }

    // Hook 3: get_Item on UtilityConfig instances (returns int directly)
    if (getItemRef && !getItemRef.ptr.isNull()) {
        trace.listeners.push(Interceptor.attach(getItemRef.ptr, {
            onEnter(this: CaptureMarker, args) {
                if (!trace.enabled) return;
                if (!state.captureMirrorMessages) return;
                trace.diag.getItemFires++;
                const thisPtr = args[0];
                const cfgKey = thisPtr.toString();
                const binding = knownConfigs.get(cfgKey);
                if (!binding) return;
                trace.diag.getItemMatchedKnown++;
                this._ucConfigPtr = cfgKey;
                this._ucOwnerType = getOwnerType(thisPtr) ?? undefined;
                this._ucBinding = binding;
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
                });
            },
        }));
    }

    Interceptor.flush();
    send({
        t: "diag",
        msg: "[ai-util-trace] hooks installed: GetUtilityConfig="
            + (!getUtilityConfigMi.ptr.isNull() ? "ok" : "FAIL")
            + " · TryGetValue=" + (tryGetValueRef ? "ok" : "missing")
            + " · get_Item=" + (getItemRef ? "ok" : "missing"),
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

    ctx.rpc.aiUtilityTraceClear = (): unknown => {
        trace.buffer = [];
        trace.counters.clear();
        trace.seq = 0;
        trace.diag.tryGetValueFires = 0;
        trace.diag.tryGetValueMatchedKnown = 0;
        trace.diag.getItemFires = 0;
        trace.diag.getItemMatchedKnown = 0;
        return { ok: true };
    };

    /** Dump the current buffer. Body: { since?: seq, max?: number }
     * - since: only entries with seq > since
     * - max: cap returned count (default 1000) */
    ctx.rpc.aiUtilityTraceDump = (
        body?: { since?: number; max?: number },
    ): unknown => {
        const since = body?.since ?? 0;
        const max = body?.max ?? 1000;
        const filtered = since > 0
            ? trace.buffer.filter((e) => e.seq > since)
            : trace.buffer;
        const slice = filtered.slice(-max);
        return {
            enabled: trace.enabled,
            totalSeq: trace.seq,
            bufferSize: trace.buffer.length,
            knownConfigs: knownConfigs.size,
            returned: slice.length,
            entries: slice,
        };
    };

    /** Aggregated counters: how many times each (ownerType, key) was read.
     * Lets us identify hot keys without scanning the full buffer.
     * `ownerType` is the qualified Dict<TKey,TValue> generic instantiation,
     * eg `Dictionary'2[BEntityId,Int32]` or
     * `IdunBattle.Configuration.UtilityConfig`. */
    ctx.rpc.aiUtilityTraceCounters = (): unknown => {
        const out: Array<{ ownerType: string; key: string; count: number }> =
            [];
        for (const [k, v] of trace.counters) {
            const idx = k.indexOf(":");
            out.push({
                ownerType: idx >= 0 ? k.slice(0, idx) : k,
                key: idx >= 0 ? k.slice(idx + 1) : "",
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

    void detachHooks; // exposed in case we add a "fully uninstall" RPC later
}
