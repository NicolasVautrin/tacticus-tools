// Live unit-visual resolver via `idun.IdunUniverse.TryGetUnitVisualConfig`.
//
// The game's own authoritative resolver: takes a "unitIdWithLevel" string
// (e.g. "eldarBossMauganRaCamp:2") and returns a UnitVisualConfig containing
// the assetNaming. Unlike IdunVisuals._unitConfigMap (which only lists
// 290 playable heroes), this resolver handles Boss/Camp/Event variants
// because the game uses it in its own UI (BaseSelectionState FSM).
//
// Strategy:
//   1. Interceptor.attach onEnter on TryGetUnitVisualConfig → capture the
//      first `this` observed. IdunUniverse is a ScriptableObject singleton
//      so the instance stays valid for the lifetime of the session.
//   2. RPC `resolveUnitVisual(id)` — call TryGet, read assetNaming.
//   3. RPC `dumpAllUnitVisuals()` — iterate get_ConfiguredUnitIds() and
//      resolve each. Returns the full visual map including Boss variants.

import {
    class_get_name, class_get_methods, findClassAnywhere, findMethod,
    getFieldOffset, IL2CPP_MODULE_NAME, method_get_name, readIl2cppString, s,
} from "../il2cpp/helpers.js";
import { createManagedString, invokeMethod } from "../il2cpp/invoke.js";
import { gcRoot } from "../il2cpp/gc-root.js";
import { queueOnMainThread } from "../runtime/queue.js";
import { log, traceEnter } from "../runtime/diag.js";
import { Ctx } from "../controller.js";

const universeClass = findClassAnywhere("idun", "IdunUniverse");
const tryGetMi = universeClass
    ? findMethod(universeClass, "TryGetUnitVisualConfig") : null;
const getConfiguredIdsMi = universeClass
    ? findMethod(universeClass, "get_ConfiguredUnitIds") : null;
const getUnitConfigMapMi = universeClass
    ? findMethod(universeClass, "get_UnitConfigMap") : null;

// Extra il2cpp exports for static field traversal — IdunVisuals has a
// static field pointing to IdunUniverse we can discover without relying on
// the game calling a hooked method first.
const _lib = Process.findModuleByName(IL2CPP_MODULE_NAME);
function _exp(n: string): NativePointer {
    if (!_lib) throw new Error(`${IL2CPP_MODULE_NAME} not loaded`);
    const p = _lib.findExportByName(n);
    if (!p) throw new Error("missing export: " + n);
    return p;
}
const _classGetFields = new NativeFunction(
    _exp("il2cpp_class_get_fields"), "pointer", ["pointer", "pointer"]);
const _fieldGetName = new NativeFunction(
    _exp("il2cpp_field_get_name"), "pointer", ["pointer"]);
const _fieldGetFlags = new NativeFunction(
    _exp("il2cpp_field_get_flags"), "uint32", ["pointer"]);
const _fieldGetType = new NativeFunction(
    _exp("il2cpp_field_get_type"), "pointer", ["pointer"]);
const _typeGetClass = new NativeFunction(
    _exp("il2cpp_type_get_class_or_element_class"), "pointer", ["pointer"]);
const _fieldStaticGetValue = new NativeFunction(
    _exp("il2cpp_field_static_get_value"), "void", ["pointer", "pointer"]);

const FIELD_ATTRIBUTE_STATIC = 0x0010;

let capturedUniverse: NativePointer | null = null;
let assetNamingOffset: number = -1;

export function getCapturedUniverse(): NativePointer | null {
    return capturedUniverse;
}

// Resolve UnitVisualConfig.assetNaming field offset lazily on first seen
// instance — the class isn't directly named in IL2CPP dump filters but we
// can inspect at runtime from the first returned object.
function ensureAssetNamingOffset(cfgPtr: NativePointer): void {
    if (assetNamingOffset >= 0) return;
    if (cfgPtr.isNull()) return;
    try {
        const klass = cfgPtr.readPointer();
        if (klass.isNull()) return;
        // Try common field names in priority order. Game uses `assetNaming`
        // per the IdunUnitType static map — UnitVisualConfig likely mirrors it.
        for (const name of ["assetNaming", "_assetNaming", "AssetNaming"]) {
            const off = getFieldOffset(klass, name);
            if (off >= 0) { assetNamingOffset = off; return; }
        }
    } catch { /* ignore */ }
}

// Attach — capture universe ref on first call to ANY instance method.
// ScriptableObject singletons have no static accessor, so we catch them
// as `this` of any managed call. TryGet is rare; IsUnitInUniverse / GetBoard
// / get_ConfiguredUnitIds are hit often and on many screens.
const captureOnEnter = (args: InvocationArguments): void => {
    if (capturedUniverse !== null) return;
    if (args[0].isNull()) return;
    capturedUniverse = args[0];
    try { gcRoot.add(args[0]); } catch { /* ok if gc not ready */ }
    log("[unit-visual-resolve] captured IdunUniverse @ " + args[0]);
};

if (universeClass) {
    const captureMethods = [
        "TryGetUnitVisualConfig",
        "IsUnitInUniverse",
        "IsUnitReleasable",
        "GetBoard",
        "GetTileConfigurations",
        "GetTutorials",
        "get_ConfiguredUnitIds",
        "get_UnitConfigMap",
    ];
    for (const name of captureMethods) {
        const m = findMethod(universeClass, name);
        if (!m || m.ptr.isNull()) continue;
        try {
            const traceName = "IdunUniverse." + name;
            Interceptor.attach(m.ptr, {
                onEnter(args) {
                    traceEnter(traceName, 50);
                    captureOnEnter(args);
                },
            });
        } catch { /* best effort */ }
    }
    Interceptor.flush();
}

// Enumerate all static fields of `klass` and return the first one whose type
// is assignable to `targetClass`. For singletons held as public/private
// static in another service class.
function findStaticFieldOfType(
    klass: NativePointer, targetClass: NativePointer,
): { name: string; ptr: NativePointer } | null {
    const it = Memory.alloc(Process.pointerSize);
    it.writePointer(ptr(0));
    let f: NativePointer;
    while (!(f = _classGetFields(klass, it) as NativePointer).isNull()) {
        const flags = _fieldGetFlags(f) as number;
        if ((flags & FIELD_ATTRIBUTE_STATIC) === 0) continue;
        const typePtr = _fieldGetType(f) as NativePointer;
        if (typePtr.isNull()) continue;
        const fieldClass = _typeGetClass(typePtr) as NativePointer;
        if (fieldClass.isNull()) continue;
        if (!fieldClass.equals(targetClass)) continue;
        const storage = Memory.alloc(Process.pointerSize);
        storage.writePointer(ptr(0));
        try {
            _fieldStaticGetValue(f, storage);
            const val = storage.readPointer();
            if (val.isNull()) continue;
            const name = s(_fieldGetName(f) as NativePointer);
            return { name, ptr: val };
        } catch { /* continue */ }
    }
    return null;
}

// Try to capture IdunUniverse by walking static fields of known holders.
function tryStaticCapture(): string | null {
    if (capturedUniverse !== null) return "already captured";
    if (!universeClass) return "universe class not found";

    const candidates: Array<{ ns: string; cls: string }> = [
        { ns: "idun.ui", cls: "IdunVisuals" },
        { ns: "idun", cls: "IdunUniverse" },
        { ns: "idun", cls: "IdunGame" },
        { ns: "idun.ui", cls: "IdunUi" },
        { ns: "idun", cls: "IdunDatabase" },
    ];
    for (const c of candidates) {
        const k = findClassAnywhere(c.ns, c.cls);
        if (!k) continue;
        const found = findStaticFieldOfType(k, universeClass);
        if (found) {
            capturedUniverse = found.ptr;
            try { gcRoot.add(found.ptr); } catch { /* */ }
            log("[unit-visual-resolve] captured IdunUniverse via "
                + c.cls + "." + found.name + " @ " + found.ptr);
            return c.cls + "." + found.name;
        }
    }
    return null;
}

// Capture via the thor.Globals singleton. Globals is a MonoBehaviour kept
// alive across scenes; its instance field `currentIdunUniverse` holds the
// active IdunUniverse.
export function tryGlobalsCapture(): string | null {
    if (capturedUniverse !== null) return "already captured";
    const globalsClass = findClassAnywhere("thor", "Globals");
    if (!globalsClass) return "Globals class not found";

    // Use GetDontCreate to avoid constructing if not yet bootstrapped.
    const getDontCreate = findMethod(globalsClass, "GetDontCreate")
        ?? findMethod(globalsClass, "Get");
    if (!getDontCreate) return "Globals.Get(DontCreate) not found";

    let instance: NativePointer;
    try {
        instance = invokeMethod(getDontCreate.info, null, null);
    } catch (e) {
        return "Globals.Get() threw: " + (e as Error).message;
    }
    if (instance.isNull()) return "Globals instance is null (not bootstrapped)";

    const off = getFieldOffset(globalsClass, "currentIdunUniverse");
    if (off < 0) return "currentIdunUniverse field not found on Globals";
    const u = instance.add(off).readPointer();
    if (u.isNull()) return "currentIdunUniverse is null";

    capturedUniverse = u;
    try { gcRoot.add(u); } catch { /* */ }
    log("[unit-visual-resolve] captured IdunUniverse via "
        + "Globals.currentIdunUniverse @ " + u);
    return "Globals.currentIdunUniverse";
}

// Full-assembly scan fallback: walk every class in every loaded assembly,
// look for a static field whose type is IdunUniverse. Costly (~seconds)
// but runs once, and only if the fast path missed. Skips mscorlib/system
// assemblies — the singleton won't live there.
function fullAssemblyScan(): string | null {
    if (!universeClass) return null;
    const lib = Process.findModuleByName(IL2CPP_MODULE_NAME);
    if (!lib) return null;
    const domainGet = new NativeFunction(
        _exp("il2cpp_domain_get"), "pointer", []);
    const domainGetAssemblies = new NativeFunction(
        _exp("il2cpp_domain_get_assemblies"), "pointer", ["pointer", "pointer"]);
    const assemblyGetImage = new NativeFunction(
        _exp("il2cpp_assembly_get_image"), "pointer", ["pointer"]);
    const imageGetClassCount = new NativeFunction(
        _exp("il2cpp_image_get_class_count"), "uint32", ["pointer"]);
    const imageGetClass = new NativeFunction(
        _exp("il2cpp_image_get_class"), "pointer", ["pointer", "uint32"]);
    const imageGetName = new NativeFunction(
        _exp("il2cpp_image_get_name"), "pointer", ["pointer"]);

    const domain = domainGet() as NativePointer;
    const sizePtr = Memory.alloc(4);
    const assemblies = domainGetAssemblies(
        domain, sizePtr) as NativePointer;
    const count = sizePtr.readU32();

    const skip = new Set([
        "mscorlib.dll", "System.dll", "System.Core.dll",
        "UnityEngine.dll", "UnityEngine.CoreModule.dll",
        "UnityEngine.TextRenderingModule.dll",
        "UnityEngine.UI.dll", "netstandard.dll",
    ]);

    for (let i = 0; i < count; i++) {
        const assembly = assemblies.add(
            i * Process.pointerSize).readPointer();
        const image = assemblyGetImage(assembly) as NativePointer;
        const imgName = s(imageGetName(image) as NativePointer);
        if (skip.has(imgName)) continue;
        const cc = imageGetClassCount(image) as number;
        for (let j = 0; j < cc; j++) {
            const k = imageGetClass(image, j) as NativePointer;
            const found = findStaticFieldOfType(k, universeClass);
            if (found) {
                capturedUniverse = found.ptr;
                try { gcRoot.add(found.ptr); } catch { /* */ }
                const holder = s(
                    class_get_name(k) as NativePointer);
                const tag = imgName + "/" + holder + "." + found.name;
                log("[unit-visual-resolve] captured IdunUniverse "
                    + "via full-scan: " + tag + " @ " + found.ptr);
                return tag;
            }
        }
    }
    return null;
}

// List every class that has ANY field (static or instance) typed
// IdunUniverse. Helps identify singleton holders when the static scan
// comes up empty.
function scanUniverseReferences(): Array<{
    assembly: string;
    klass: string;
    field: string;
    isStatic: boolean;
    populatedIfStatic: string | null;
}> {
    if (!universeClass) return [];
    const lib = Process.findModuleByName(IL2CPP_MODULE_NAME);
    if (!lib) return [];
    const domainGet = new NativeFunction(
        _exp("il2cpp_domain_get"), "pointer", []);
    const domainGetAssemblies = new NativeFunction(
        _exp("il2cpp_domain_get_assemblies"), "pointer", ["pointer", "pointer"]);
    const assemblyGetImage = new NativeFunction(
        _exp("il2cpp_assembly_get_image"), "pointer", ["pointer"]);
    const imageGetClassCount = new NativeFunction(
        _exp("il2cpp_image_get_class_count"), "uint32", ["pointer"]);
    const imageGetClass = new NativeFunction(
        _exp("il2cpp_image_get_class"), "pointer", ["pointer", "uint32"]);
    const imageGetName = new NativeFunction(
        _exp("il2cpp_image_get_name"), "pointer", ["pointer"]);

    const domain = domainGet() as NativePointer;
    const sizePtr = Memory.alloc(4);
    const assemblies = domainGetAssemblies(domain, sizePtr) as NativePointer;
    const count = sizePtr.readU32();

    const skip = new Set([
        "mscorlib.dll", "System.dll", "System.Core.dll",
        "UnityEngine.dll", "UnityEngine.CoreModule.dll",
        "UnityEngine.TextRenderingModule.dll",
        "UnityEngine.UI.dll", "netstandard.dll",
    ]);

    const results: Array<{
        assembly: string;
        klass: string;
        field: string;
        isStatic: boolean;
        populatedIfStatic: string | null;
    }> = [];
    for (let i = 0; i < count; i++) {
        const assembly = assemblies.add(
            i * Process.pointerSize).readPointer();
        const image = assemblyGetImage(assembly) as NativePointer;
        const imgName = s(imageGetName(image) as NativePointer);
        if (skip.has(imgName)) continue;
        const cc = imageGetClassCount(image) as number;
        for (let j = 0; j < cc; j++) {
            const k = imageGetClass(image, j) as NativePointer;
            const it = Memory.alloc(Process.pointerSize);
            it.writePointer(ptr(0));
            let f: NativePointer;
            while (!(f = _classGetFields(k, it) as NativePointer).isNull()) {
                const typePtr = _fieldGetType(f) as NativePointer;
                if (typePtr.isNull()) continue;
                const fc = _typeGetClass(typePtr) as NativePointer;
                if (fc.isNull() || !fc.equals(universeClass)) continue;
                const flags = _fieldGetFlags(f) as number;
                const isStatic = (flags & FIELD_ATTRIBUTE_STATIC) !== 0;
                const fname = s(_fieldGetName(f) as NativePointer);
                let populated: string | null = null;
                if (isStatic) {
                    const storage = Memory.alloc(Process.pointerSize);
                    storage.writePointer(ptr(0));
                    try {
                        _fieldStaticGetValue(f, storage);
                        const v = storage.readPointer();
                        populated = v.isNull() ? "null" : v.toString();
                    } catch { populated = "err"; }
                }
                results.push({
                    assembly: imgName,
                    klass: s(class_get_name(k) as NativePointer),
                    field: fname,
                    isStatic,
                    populatedIfStatic: populated,
                });
            }
        }
    }
    return results;
}

tryStaticCapture();
// Globals.Get() involves a managed invoke — needs the main thread. Only
// callable via RPC (see tryGlobalsCapture RPC), not at hook-setup time.

function callTryGet(unitId: string): {
    found: boolean;
    assetNaming: string | null;
    cfgClass: string | null;
} {
    if (!capturedUniverse) {
        throw new Error(
            "IdunUniverse not captured yet — navigate a unit in-game to trigger "
            + "a portrait lookup, then retry");
    }
    if (!tryGetMi) throw new Error("TryGetUnitVisualConfig method not resolved");

    const idStr = createManagedString(unitId);
    const outSlot = Memory.alloc(Process.pointerSize);
    outSlot.writePointer(ptr(0));
    const flagArg = Memory.alloc(4);
    flagArg.writeS32(0);

    // Invoke TryGetUnitVisualConfig(this, idStr, out cfg, flag)
    invokeMethod(tryGetMi.info, capturedUniverse, [idStr, outSlot, flagArg]);

    const cfgPtr = outSlot.readPointer();
    if (cfgPtr.isNull()) {
        return { found: false, assetNaming: null, cfgClass: null };
    }

    let cfgClass: string | null = null;
    try {
        const klass = cfgPtr.readPointer();
        cfgClass = s(class_get_name(klass) as NativePointer);
    } catch { /* ignore */ }

    ensureAssetNamingOffset(cfgPtr);
    let assetNaming: string | null = null;
    if (assetNamingOffset >= 0) {
        try {
            const strPtr = cfgPtr.add(assetNamingOffset).readPointer();
            assetNaming = readIl2cppString(strPtr);
        } catch { /* ignore */ }
    }
    return { found: true, assetNaming, cfgClass };
}

// Iterate the managed object returned by get_ConfiguredUnitIds. Likely a
// List<string> / HashSet<string> / IReadOnlyCollection<string>. Strategy:
// probe for common field offsets, fall back to calling GetEnumerator.
function enumerateConfiguredIds(universe: NativePointer): string[] {
    if (!getConfiguredIdsMi) throw new Error("get_ConfiguredUnitIds not found");
    const collPtr = invokeMethod(getConfiguredIdsMi.info, universe, null);
    if (collPtr.isNull()) return [];

    // Read class name to determine container shape.
    let collCls = "";
    try {
        collCls = s(class_get_name(collPtr.readPointer()) as NativePointer);
    } catch { /* */ }

    const ids: string[] = [];

    // Try List<string> layout: _items @ 0x10 (T[]), _size @ 0x18 (int).
    // Il2CppArray.items @ 0x20. This works for List<> concrete type.
    try {
        const items = collPtr.add(0x10).readPointer();
        const size = collPtr.add(0x18).readS32();
        if (!items.isNull() && size > 0 && size < 100000) {
            for (let i = 0; i < size; i++) {
                const sp = items.add(0x20 + i * 8).readPointer();
                const v = readIl2cppString(sp);
                if (v) ids.push(v);
            }
            if (ids.length > 0) return ids;
        }
    } catch { /* fallthrough */ }

    // If the List probe didn't yield entries, try HashSet<string> layout:
    // _buckets @ 0x10, _slots @ 0x18 (Slot[]), _count @ 0x30.
    // HashSet<T>.Slot: hashCode(4), next(4), value(ref 8) = 16B.
    try {
        const slots = collPtr.add(0x18).readPointer();
        const count = collPtr.add(0x30).readS32();
        if (!slots.isNull() && count > 0 && count < 100000) {
            for (let i = 0; i < count; i++) {
                const base = slots.add(0x20 + i * 16);
                const hash = base.readS32();
                if (hash < -1) continue;
                const sp = base.add(8).readPointer();
                const v = readIl2cppString(sp);
                if (v) ids.push(v);
            }
            if (ids.length > 0) return ids;
        }
    } catch { /* fallthrough */ }

    throw new Error(
        "could not enumerate ConfiguredUnitIds (class=" + collCls
        + ") — need a manual probe");
}

export function register(ctx: Ctx): void {
    ctx.rpc.unitVisualResolveStatus = (): unknown => ({
        universeClassFound: universeClass !== null,
        tryGetMiFound: tryGetMi !== null && !tryGetMi.ptr.isNull(),
        getConfiguredIdsMiFound:
            getConfiguredIdsMi !== null && !getConfiguredIdsMi.ptr.isNull(),
        universeCaptured: capturedUniverse !== null,
        universePtr: capturedUniverse?.toString() ?? null,
        assetNamingOffset,
    });

    ctx.rpc.tryStaticCapture = (): unknown => {
        const r = tryStaticCapture();
        return {
            ok: capturedUniverse !== null,
            capturedVia: r,
            universePtr: capturedUniverse?.toString() ?? null,
        };
    };

    ctx.rpc.fullAssemblyScan = (): unknown => {
        const t0 = Date.now();
        const r = fullAssemblyScan();
        return {
            ok: capturedUniverse !== null,
            capturedVia: r,
            universePtr: capturedUniverse?.toString() ?? null,
            ms: Date.now() - t0,
        };
    };

    ctx.rpc.listUniverseRefs = (): unknown => {
        const t0 = Date.now();
        const refs = scanUniverseReferences();
        return {
            ms: Date.now() - t0,
            count: refs.length,
            static: refs.filter(r => r.isStatic),
            instance: refs.filter(r => !r.isStatic),
        };
    };

    ctx.rpc.tryGlobalsCapture = (): unknown => queueOnMainThread(() => {
        const r = tryGlobalsCapture();
        return {
            ok: capturedUniverse !== null,
            capturedVia: r,
            universePtr: capturedUniverse?.toString() ?? null,
        };
    });

    ctx.rpc.listUniverseInstanceFields = (): unknown => {
        if (!universeClass) return { err: "no universe class" };
        const fields: Array<{ name: string; offset: number; typeCls: string }> = [];
        const typeGetName = new NativeFunction(
            _exp("il2cpp_type_get_name"), "pointer", ["pointer"]);
        const fieldGetOffset = new NativeFunction(
            _exp("il2cpp_field_get_offset"), "int32", ["pointer"]);
        const it = Memory.alloc(Process.pointerSize);
        it.writePointer(ptr(0));
        let f: NativePointer;
        while (!(f = _classGetFields(universeClass, it) as NativePointer).isNull()) {
            const flags = _fieldGetFlags(f) as number;
            if ((flags & FIELD_ATTRIBUTE_STATIC) !== 0) continue;
            const typePtr = _fieldGetType(f) as NativePointer;
            const name = s(_fieldGetName(f) as NativePointer);
            const off = fieldGetOffset(f) as number;
            let typeCls = "?";
            try { typeCls = s(typeGetName(typePtr) as NativePointer); } catch { /* */ }
            fields.push({ name, offset: off, typeCls });
        }
        return { fields };
    };

    ctx.rpc.resolveUnitVisual = (unitId: string): unknown =>
        queueOnMainThread(() => {
            if (typeof unitId !== "string" || !unitId) {
                throw new Error("unitId must be a non-empty string");
            }
            return callTryGet(unitId);
        });

    // Pure-memory dump — no main-thread invoke needed. Reads:
    //   1. IdunUniverse._unitConfigMap (Dictionary<string, IdunUnitType>) @ 0x40
    //   2. IdunUniverse.Units (List<IdunUnitType>) @ 0x18 (may contain extras
    //      not keyed in the dict — Boss/Camp variants)
    // IdunUnitType layout:  unitId @ 0x20,  assetNaming @ 0x30
    ctx.rpc.dumpAllUnitVisuals = (): unknown => {
        if (!capturedUniverse) {
            return { error: "IdunUniverse not captured — call tryGlobalsCapture first" };
        }

        const fromDict: Record<string, { unitId: string | null; assetNaming: string | null }> = {};
        try {
            const dict = capturedUniverse.add(0x40).readPointer();
            if (!dict.isNull()) {
                const count = dict.add(0x20).readS32();
                const entries = dict.add(0x18).readPointer();
                if (!entries.isNull() && count > 0 && count < 100000) {
                    for (let i = 0; i < count; i++) {
                        const base = entries.add(0x20 + i * 24);
                        const next = base.add(4).readS32();
                        if (next < -1) continue;
                        const keyPtr = base.add(8).readPointer();
                        const valPtr = base.add(16).readPointer();
                        if (keyPtr.isNull() || valPtr.isNull()) continue;
                        const key = readIl2cppString(keyPtr);
                        if (!key) continue;
                        const unitIdPtr = valPtr.add(0x20).readPointer();
                        const assetPtr = valPtr.add(0x30).readPointer();
                        fromDict[key] = {
                            unitId: readIl2cppString(unitIdPtr),
                            assetNaming: readIl2cppString(assetPtr),
                        };
                    }
                }
            }
        } catch (e) {
            return { error: "dict read failed: " + (e as Error).message };
        }

        // List<IdunUnitType>: _items @ 0x10, _size @ 0x18; Array.items @ 0x20
        const fromList: Record<string, { unitId: string | null; assetNaming: string | null }> = {};
        try {
            const listSize = capturedUniverse.add(0x18).readS32()
                + (capturedUniverse.add(0x18 + 8).readU32() === 0 ? 0 : 0);
            // Actually read directly: field offset 24 → that IS the List<T>
            // ref, we need _size and _items. Re-do properly.
            const listRef = capturedUniverse.add(0x18).readPointer();
            if (!listRef.isNull()) {
                const itemsArr = listRef.add(0x10).readPointer();
                const size = listRef.add(0x18).readS32();
                if (!itemsArr.isNull() && size > 0 && size < 100000) {
                    for (let i = 0; i < size; i++) {
                        const cfgPtr = itemsArr.add(0x20 + i * 8).readPointer();
                        if (cfgPtr.isNull()) continue;
                        const unitIdPtr = cfgPtr.add(0x20).readPointer();
                        const assetPtr = cfgPtr.add(0x30).readPointer();
                        const uid = readIl2cppString(unitIdPtr);
                        const asset = readIl2cppString(assetPtr);
                        if (uid) {
                            fromList[uid] = { unitId: uid, assetNaming: asset };
                        }
                    }
                }
            }
            void listSize;
        } catch (e) {
            return { error: "list read failed: " + (e as Error).message };
        }

        // Diff: keys present only in one source.
        const dictKeys = new Set(Object.keys(fromDict));
        const listKeys = new Set(Object.keys(fromList));
        const onlyInDict = [...dictKeys].filter(k => !listKeys.has(k));
        const onlyInList = [...listKeys].filter(k => !dictKeys.has(k));

        return {
            dictCount: Object.keys(fromDict).length,
            listCount: Object.keys(fromList).length,
            onlyInDictCount: onlyInDict.length,
            onlyInListCount: onlyInList.length,
            onlyInList: onlyInList.slice(0, 50),
            onlyInDict: onlyInDict.slice(0, 50),
            fromDict,
            fromList,
        };
    };
}
