// Passive capture of BattleConfiguration assembled by the game's own
// GameModeSource.LoadBattle(isRestart) → BattleConfiguration.
//
// Each concrete game mode (Campaign, Pvp, SyncPvp, GuildBoss, etc.) overrides
// or inherits LoadBattle to stitch a full BattleConfiguration from static
// bundles + user state.
//
// Coverage strategy:
//   - Auto-discover every class in `IdunBattle.ViewLogic.BattleSource`
//   - For each, walk the inheritance chain to find the LoadBattle method
//     (it may be declared on the base `AGameModeSource`, not on the concrete
//     class — `PvpGameModeSource` is a notable example)
//   - Collect the UNIQUE method pointers and Interceptor.attach each ONCE.
//     This catches both: direct calls when the derived overrides
//     (SyncPvp) and inherited dispatch when it doesn't (Pvp).
//   - In the hook callback, read `args[0]`'s class pointer and map back
//     to the CONCRETE class name — so a Pvp battle is logged as
//     "PvpGameModeSource", not "AGameModeSource".

import {
    class_get_fields, class_get_methods, class_get_name, class_get_namespace,
    class_get_parent, class_instance_size, cstr, field_get_name, field_get_offset,
    field_get_type, findClassAnywhere, findMethod, getFieldOffset,
    IL2CPP_MODULE_NAME, methodEntry, method_get_name,
    type_get_class_or_element_class,
} from "../il2cpp/helpers.js";
import { Ctx } from "../controller.js";
import { state } from "../game/state.js";
import { log } from "../runtime/diag.js";

const NS = "IdunBattle.ViewLogic.BattleSource";

// CampaignGameModeSource exposes the live `_currentCampaignId` (string ptr at
// offset 0x68) and `_currentLocationIndex` (int at 0x70). Capturing them at
// LoadBattle time gives the archive panel a much richer identity than the
// generic class name.
const CGMS_OFF_CAMPAIGN_ID = 0x68;
const CGMS_OFF_LOCATION_INDEX = 0x70;

function readManagedString(ptr_: NativePointer): string | null {
    // Il2CppString layout (Il2CppObject prefix is 0x10 bytes on x64):
    //   0x00: Il2CppClass* klass
    //   0x08: void*        monitor
    //   0x10: int32        length
    //   0x14: char16_t     chars[length]
    // Strict bounds — never fall through to an unbounded read because a
    // garbage `length` could otherwise make readUtf16String scan unmapped
    // memory and hang the calling thread.
    try {
        if (ptr_.isNull()) return null;
        const length = ptr_.add(0x10).readS32();
        if (length <= 0 || length > 1024) return null;
        return ptr_.add(0x14).readUtf16String(length);
    } catch { return null; }
}

interface DiscoveredSource {
    cls: string;
    klass: NativePointer;
    /** LoadBattle method ptr — own if declared, inherited from a parent
     * otherwise. Multiple discovered sources can share the same method ptr
     * when several classes inherit the same base implementation. */
    method: NativePointer;
    /** The IL2CPP MethodInfo* corresponding to `method`. We Interceptor.attach
     * on `method` (the entry pointer) but keep the MethodInfo* for diag. */
    methodInfo: NativePointer;
    /** Whether this class declared its own LoadBattle (true) or inherits it
     * (false). Diag-only — doesn't change hook behavior. */
    ownLoadBattle: boolean;
}

let discovered: DiscoveredSource[] = [];
/** Map klassPtr.toString() → concrete class name. Built at register time
 * for fast resolution of args[0]'s class in the hot path. */
const klassPtrToCls = new Map<string, string>();
/** Set of method pointers we've Interceptor.attach'd, to avoid double-hooking
 * the same inherited LoadBattle when multiple derived classes share it. */
const hookedMethodPtrs = new Set<string>();

function lib(): Module {
    const m = Process.findModuleByName(IL2CPP_MODULE_NAME);
    if (!m) throw new Error(`${IL2CPP_MODULE_NAME} not loaded`);
    return m;
}

function exp(name: string): NativePointer {
    const p = lib().findExportByName(name);
    if (!p) throw new Error("missing export: " + name);
    return p;
}

const _domain_get = new NativeFunction(
    exp("il2cpp_domain_get"), "pointer", []);
const _domain_get_assemblies = new NativeFunction(
    exp("il2cpp_domain_get_assemblies"), "pointer", ["pointer", "pointer"]);
const _assembly_get_image = new NativeFunction(
    exp("il2cpp_assembly_get_image"), "pointer", ["pointer"]);
const _image_get_class_count = new NativeFunction(
    exp("il2cpp_image_get_class_count"), "uint32", ["pointer"]);
const _image_get_class = new NativeFunction(
    exp("il2cpp_image_get_class"), "pointer", ["pointer", "uint32"]);
const _class_get_parent = new NativeFunction(
    exp("il2cpp_class_get_parent"), "pointer", ["pointer"]);

/** Walk the inheritance chain starting at `klass`, return the FIRST class
 * (including klass itself) whose own methods include `LoadBattle`, plus the
 * MethodRef. Returns null if neither klass nor any parent declares it. */
function resolveLoadBattle(klass: NativePointer): {
    method: NativePointer; methodInfo: NativePointer; declaredBy: NativePointer;
} | null {
    let k: NativePointer = klass;
    while (!k.isNull()) {
        const m = findMethod(k, "LoadBattle");
        if (m && !m.ptr.isNull()) {
            return { method: m.ptr, methodInfo: m.info, declaredBy: k };
        }
        try { k = _class_get_parent(k) as NativePointer; }
        catch { break; }
    }
    return null;
}

/** Walk every class in every loaded assembly, pick those whose namespace is
 * `IdunBattle.ViewLogic.BattleSource` AND that resolve a `LoadBattle` method
 * (own or inherited). Returns the resolved entries. */
function discoverModeSources(): DiscoveredSource[] {
    const out: DiscoveredSource[] = [];
    const seen = new Set<string>();

    const domain = _domain_get() as NativePointer;
    const sizePtr = Memory.alloc(4);
    const assemblies = _domain_get_assemblies(
        domain, sizePtr) as NativePointer;
    const count = sizePtr.readU32();
    for (let i = 0; i < count; i++) {
        const assembly = assemblies.add(
            i * Process.pointerSize).readPointer();
        const image = _assembly_get_image(assembly) as NativePointer;
        const cc = _image_get_class_count(image) as number;
        for (let j = 0; j < cc; j++) {
            const k = _image_get_class(image, j) as NativePointer;
            if (k.isNull()) continue;
            let ns: string;
            let clsName: string;
            try {
                ns = cstr(class_get_namespace(k) as NativePointer);
                if (ns !== NS) continue;
                clsName = cstr(class_get_name(k) as NativePointer);
            } catch { continue; }
            if (seen.has(clsName)) continue;

            const ownDecl = findMethod(k, "LoadBattle");
            const ownLoadBattle = !!(ownDecl && !ownDecl.ptr.isNull());
            const resolved = resolveLoadBattle(k);
            if (!resolved) continue;
            seen.add(clsName);
            out.push({
                cls: clsName, klass: k,
                method: resolved.method,
                methodInfo: resolved.methodInfo,
                ownLoadBattle,
            });
        }
    }
    return out;
}

function installHooks(sources: DiscoveredSource[]): void {
    klassPtrToCls.clear();
    for (const s of sources) {
        klassPtrToCls.set(s.klass.toString(), s.cls);
    }
    // De-duplicate by method pointer — multiple derived classes that inherit
    // the same parent's LoadBattle would otherwise install N redundant
    // listeners on the same function entry.
    hookedMethodPtrs.clear();
    let hooked = 0;
    for (const s of sources) {
        const key = s.method.toString();
        if (hookedMethodPtrs.has(key)) continue;
        hookedMethodPtrs.add(key);
        try {
            Interceptor.attach(s.method, {
                onEnter(args) {
                    (this as { sourcePtr?: NativePointer }).sourcePtr =
                        ptr(args[0].toString());
                },
                onLeave(retval) {
                    if (retval.isNull()) return;
                    const sp = (this as { sourcePtr?: NativePointer })
                        .sourcePtr;
                    if (!sp || sp.isNull()) return;

                    // Resolve the CONCRETE class from the instance pointer.
                    // CRITICAL: the method pointer we hook may be shared
                    // (IL2CPP generic sharing or simply a name-collision
                    // method on an unrelated base) — without this guard the
                    // hook fires for `DefaultContractResolver`, `MatchState`
                    // and other classes that have nothing to do with battle
                    // sources. Filter to ONLY the BattleSource classes we
                    // pre-discovered.
                    let concreteCls: string;
                    try {
                        const klass = sp.readPointer();
                        const mapped = klassPtrToCls.get(klass.toString());
                        if (!mapped) return;  // not a BattleSource class
                        concreteCls = mapped;
                    } catch { return; }

                    let campaignId: string | null = null;
                    let locationIndex: number | null = null;
                    if (concreteCls === "CampaignGameModeSource") {
                        try {
                            campaignId = readManagedString(
                                sp.add(CGMS_OFF_CAMPAIGN_ID).readPointer());
                            locationIndex = sp.add(
                                CGMS_OFF_LOCATION_INDEX).readS32();
                        } catch { /* keep nulls */ }
                    }
                    state.lastModeSourceMeta = {
                        mode: concreteCls,
                        campaignId,
                        locationIndex,
                        ts: Date.now(),
                    };
                    log(`[mode-source-capture] LoadBattle on ${concreteCls}`
                        + (campaignId !== null
                            ? ` campaignId=${campaignId} loc=${locationIndex}`
                            : ""));
                },
            });
            hooked++;
        } catch (e) {
            log(`[mode-source-capture] failed to hook LoadBattle for `
                + `${s.cls}: ${(e as Error).message}`);
        }
    }
    Interceptor.flush();
    log(`[mode-source-capture] hooked ${hooked} unique LoadBattle entries `
        + `for ${sources.length} mode classes`);
}

export function register(ctx: Ctx): void {
    discovered = discoverModeSources();
    installHooks(discovered);

    // Validate the campaign field offsets at load time — if `_currentCampaignId`
    // moves in a future build we want to know early via diag.
    try {
        const cgms = discovered.find(d => d.cls === "CampaignGameModeSource");
        if (cgms) {
            const off1 = getFieldOffset(cgms.klass, "_currentCampaignId");
            const off2 = getFieldOffset(cgms.klass, "_currentLocationIndex");
            if (off1 >= 0 && off1 !== CGMS_OFF_CAMPAIGN_ID) {
                log(`[mode-source-capture] WARN: _currentCampaignId offset `
                    + `drifted from 0x${CGMS_OFF_CAMPAIGN_ID.toString(16)} `
                    + `to 0x${off1.toString(16)}`);
            }
            if (off2 >= 0 && off2 !== CGMS_OFF_LOCATION_INDEX) {
                log(`[mode-source-capture] WARN: _currentLocationIndex offset `
                    + `drifted from 0x${CGMS_OFF_LOCATION_INDEX.toString(16)} `
                    + `to 0x${off2.toString(16)}`);
            }
        }
    } catch { /* best-effort */ }

    void class_get_methods; void method_get_name; void methodEntry;

    /** RPC: scan every loaded assembly's classes whose name CONTAINS the
     * given substring (case-insensitive). Returns ns + cls + ownLoadBattle.
     * Useful for ad-hoc inspection when a known mode doesn't show up where
     * expected. */
    ctx.rpc.findClassesNamed = (needle: string): unknown => {
        const wanted = (needle || "").toLowerCase();
        const out: Array<{ ns: string; cls: string; ownLoadBattle: boolean }> = [];
        const domain = _domain_get() as NativePointer;
        const sizePtr = Memory.alloc(4);
        const assemblies = _domain_get_assemblies(
            domain, sizePtr) as NativePointer;
        const count = sizePtr.readU32();
        for (let i = 0; i < count; i++) {
            const assembly = assemblies.add(
                i * Process.pointerSize).readPointer();
            const image = _assembly_get_image(assembly) as NativePointer;
            const cc = _image_get_class_count(image) as number;
            for (let j = 0; j < cc; j++) {
                const k = _image_get_class(image, j) as NativePointer;
                if (k.isNull()) continue;
                let clsName = "";
                let ns = "";
                try {
                    clsName = cstr(class_get_name(k) as NativePointer);
                    if (!clsName.toLowerCase().includes(wanted)) continue;
                    ns = cstr(class_get_namespace(k) as NativePointer);
                } catch { continue; }
                let ownLB = false;
                try {
                    const m = findMethod(k, "LoadBattle");
                    ownLB = !!(m && !m.ptr.isNull());
                } catch { /* ignore */ }
                out.push({ ns, cls: clsName, ownLoadBattle: ownLB });
            }
        }
        return { count: out.length, results: out };
    };

    /**
     * RPC: disposition COMPLETE d'une classe — nom, offset et type de chaque champ,
     * remontee de la chaine d'heritage, plus la taille BOXEE.
     *
     * POURQUOI CE RPC EXISTE (#279). Les decodeurs de struct du harnais figent des
     * offsets en dur (`sretPtr.add(0x8).readS32()`). A chaque migration de build ils
     * se mettent a lire du tas voisin — des valeurs plausibles, jamais nulles, jamais
     * signalees (#276 : `aiPredict` rendait [1,100] pour TOUT couple ; #278 :
     * `RepairPredictionResult` lu sur 16 octets alors qu'il n'en fait que 8). Chaque
     * fois, la reparation coutait une RE complete au decompile, champ par champ.
     *
     * Or les noms de champs sont dans les METADONNEES IL2CPP, donc lisibles EN LIVE :
     * `getFieldOffset(klass, "HealthDamage")` resout deja par nom et survit a une
     * redisposition sans une ligne de code. Ce qui manquait n'etait pas la resolution,
     * c'etait de pouvoir LISTER les champs pour savoir quels noms demander — le dump
     * `data/il2cpp_full.json` n'est pas sur disque, et un agent en worktree ne l'a pas
     * non plus. Ce RPC comble ce trou : il rend la disposition reelle du build COURANT,
     * sans dump, sans Ghidra, sans supposer un ordre de declaration.
     *
     * ⚠ `size` est la taille BOXEE (`il2cpp_class_instance_size`) : pour un ValueType
     * elle inclut le header IL2CPP de 0x10. La confondre avec la taille des CHAMPS est
     * exactement l'erreur qui a mis `DamagePredictionResult` a 0xB0 au lieu de 0xA0, et
     * par ricochet fausse le stride d'iteration d'un `List<T>`. `fieldsSize` ci-dessous
     * donne la taille des champs seuls, deja corrigee.
     */
    ctx.rpc.classFields = (ns: string, cls: string): unknown => {
        if (typeof ns !== "string" || typeof cls !== "string" || !cls) {
            return { ok: false, err: "classFields(ns, cls) — ns et cls requis" };
        }
        const klass = findClassAnywhere(ns, cls);
        if (!klass) return { ok: false, err: `classe introuvable: ${ns}.${cls}` };

        const fields: Array<{
            name: string; offset: number; type: string; declaredBy: string;
        }> = [];
        let k: NativePointer = klass;
        let depth = 0;
        while (!k.isNull() && depth < 6) {
            const owner = (() => {
                try { return cstr(class_get_name(k) as NativePointer); }
                catch { return "?"; }
            })();
            try {
                const iter = Memory.alloc(Process.pointerSize);
                iter.writePointer(ptr(0));
                for (;;) {
                    const f = class_get_fields(k, iter) as NativePointer;
                    if (f.isNull()) break;
                    let type = "?";
                    try {
                        const tc = type_get_class_or_element_class(
                            field_get_type(f) as NativePointer) as NativePointer;
                        if (!tc.isNull()) {
                            type = cstr(class_get_name(tc) as NativePointer);
                        }
                    } catch { /* type non resolu : le nom+offset suffisent */ }
                    fields.push({
                        name: cstr(field_get_name(f) as NativePointer),
                        offset: field_get_offset(f) as number,
                        type, declaredBy: owner,
                    });
                }
            } catch { /* classe sans champs iterables */ }
            k = class_get_parent(k) as NativePointer;
            depth++;
        }

        const boxedSize = class_instance_size
            ? (class_instance_size(klass) as number) : null;
        // Un champ d'INSTANCE d'un ValueType est offset >= 0x10 (apres le header) ;
        // les statiques/litteraux sortent de cette plage et ne comptent pas dans la
        // taille des champs.
        const instanceFields = fields.filter(
            (f) => f.offset >= 0x10 && f.offset < (boxedSize ?? Number.MAX_SAFE_INTEGER));
        return {
            ok: true, ns, cls,
            klass: klass.toString(),
            boxedSize,
            fieldsSize: boxedSize === null ? null : boxedSize - 0x10,
            fieldCount: fields.length,
            instanceFieldCount: instanceFields.length,
            fields,
        };
    };

    /** RPC: list every discovered class so the user can verify the new
     * arena / event / mode classes are picked up after a hooks rebuild. */
    ctx.rpc.dumpModeSources = (): unknown => ({
        count: discovered.length,
        uniqueMethods: hookedMethodPtrs.size,
        classes: discovered.map(d => ({
            cls: d.cls,
            klass: d.klass.toString(),
            method: d.method.toString(),
            ownLoadBattle: d.ownLoadBattle,
        })),
        currentMeta: state.lastModeSourceMeta,
    });
}
