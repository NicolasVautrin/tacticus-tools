// Runtime introspection — RPCs the host calls to extract IL2CPP metadata
// (enums, class layouts, …) and persist them to disk so the front-end can
// load them via plain HTTP without a live Frida session.
//
// Pattern:
//   1. host POSTs /api/introspect/enums → calls `dumpEnums()` RPC
//   2. agent walks the requested classes' static-literal fields, builds
//      `{ EnumName: { memberName: value } }` (valeur en decimal exact, chaine)
//   3. host writes the result to `frida/assets/public/enums.json`
//   4. front fetches `/assets/enums.json` at boot, caches in `state.enums`
//
// No background hook, no `send()` — the call returns synchronously and the
// host is in charge of where the data lands.

import { dumpEnum } from "../il2cpp/enum-dump.js";
import {
    findClass, findClassAnywhere, findMethod, readIl2cppString,
    method_get_name, cstr, il2cppBase, methodEntry,
    class_get_methods, class_get_name, class_get_namespace, class_get_parent,
    method_get_param_count,
} from "../il2cpp/helpers.js";
import { classInitState, LIVE_CLASS_INIT_PROBE } from "../il2cpp/class-init.js";
import { invokeMethod } from "../il2cpp/invoke.js";
import { Ctx } from "../controller.js";

interface EnumSpec { asm: string; ns: string; cls: string; }

// Curated list — these are the enums we actually need to resolve event tags
// (Effect_Id, UnitStats_AddTrait, DamageProfile, …). Add to this array as
// new tag-keyed enums surface.
const DEFAULT_ENUMS: EnumSpec[] = [
    { asm: "IdunSharedAssembly.dll", ns: "IdunBattle.Entities.Enum",   cls: "EffectType" },
    { asm: "IdunSharedAssembly.dll", ns: "IdunBattle.Entities.Enum",   cls: "UnitTrait" },
    { asm: "IdunSharedAssembly.dll", ns: "IdunBattle.Entities.Enum",   cls: "DamageProfileType" },
    { asm: "BattleLogicAssembly.dll", ns: "IdunBattle.Streams",         cls: "StepType" },
    { asm: "BattleLogicAssembly.dll", ns: "IdunBattle.Streams",         cls: "GroupType" },
    { asm: "BattleLogicAssembly.dll", ns: "IdunBattle.Streams",         cls: "TagKey" },
    // CampaignType lives in Idun.Shared namespace (assembly resolved via
    // findClassAnywhere fallback in dumpEnum). Used by /api/campaigns/* to
    // translate the catalog Dictionary<CampaignType, ...> int keys to names
    // (Standard / Mirror / Elite / EliteMirror).
    { asm: "IdunSharedAssembly.dll",  ns: "Idun.Shared",                cls: "CampaignType" },
];

/** Invoke a parameterless static UnityEngine.Application getter that returns
 * a managed System.String (e.g. `get_version`, `get_identifier`). */
function callStaticStringGetter(name: string): string | null {
    const cls = findClass("UnityEngine.CoreModule.dll", "UnityEngine", "Application");
    if (!cls) return null;
    const m = findMethod(cls, name);
    if (!m) return null;
    try {
        const sp = invokeMethod(m.info, null, null);
        return readIl2cppString(sp);
    } catch {
        return null;
    }
}

export function register(ctx: Ctx): void {
    /** Cheap version probe — used as cache key for per-version metadata
     * (enums, i18n) so the host knows when to re-extract. Bundles the
     * Tacticus app version (`Application.version`), the bundle identifier
     * (e.g. `com.snowprintstudios.tacticus`), the product name, and the
     * Unity engine version — handy for debug. */
    ctx.rpc.getGameVersion = () => ({
        version: callStaticStringGetter("get_version"),
        identifier: callStaticStringGetter("get_identifier"),
        productName: callStaticStringGetter("get_productName"),
        unityVersion: callStaticStringGetter("get_unityVersion"),
    });

    /** Dump one enum class — useful for ad-hoc debugging. Returns
     * `{ values: { "None": "0", "X": "1", ... } }` or null if not found. */
    ctx.rpc.dumpEnum = (args: { asm: string; ns: string; cls: string }) => {
        const values = dumpEnum(args.asm, args.ns, args.cls);
        return { asm: args.asm, ns: args.ns, cls: args.cls, values };
    };

    /** Resolve IL2CPP vtable slots of a class by reading the runtime
     * Il2CppClass. Each virtual slot is a VirtualInvokeData { methodPtr(8),
     * MethodInfo*(8) } — for slot at byte offset `off`, methodPtr = klass+off,
     * MethodInfo* = klass+off+8. We read the MethodInfo* and name it via
     * il2cpp_method_get_name. Purely reads pointers (no invoke). Used to
     * resolve which method sits at a decompiled vtable offset (e.g. +0x398).
     * args: { ns, cls, start?, end?, forceInit? } — offsets in bytes, default 0x2f8..0x3b8.
     *
     * #982-r6 — `forceInit` (défaut FAUX). **IL2CPP ne remplit la vtable d'une classe qu'à son
     * INITIALISATION** : une classe jamais instanciée dans la session rend des slots à ZÉRO, et
     * un zéro se lit comme « aucun override ». C'est la cause MESURÉE du recensement partiel de
     * `probe_916r1_effect_slots.py` — 244 classes d'effet mesurées sur 465, les 221 autres
     * rangées en `NON MESUREE` faute de pouvoir les réveiller.
     *
     * Le drapeau appelle `il2cpp_runtime_class_init`, c'est-à-dire exactement ce que le jeu fait
     * lui-même au premier accès. Il reste EXPLICITE, et le RPC publie `initializedBefore` /
     * `forcedInit` / `forceInitError` : un lecteur qui voit `initialized: false` ne tient pas une
     * mesure, et un lecteur qui voit `forcedInit: true` sait que l'état vient du capteur et non
     * du jeu. Foyer unique de cette discipline : `il2cpp/class-init.ts`, partagé avec
     * `probes/static-field-probe.ts` — les deux ne peuvent donc pas diverger. */
    /**
     * LES BLOCS D'INTERFACE D'UNE CLASSE — `interfaceOffsets`, LU, pas dérivé.
     *
     * Un appel d'interface compilé par IL2CPP porte un index RELATIF au bloc de son interface
     * (`InterfaceFuncInvoker<N>(index, itfClass, obj, ...)`). Pour le nommer, il faut le
     * DÉCALAGE du bloc dans la vtable de la classe concrète. Ce décalage se lit ici :
     *
     *     klass+0xb0   -> tableau de paires 16 o { Il2CppClass* itf, int32 offset }
     *     klass+0x12e  -> u16, nombre de paires
     *     klass+0x138  -> vtable, entrées 16 o { codePtr, MethodInfo* }
     *
     * ⚠ POURQUOI CE RPC EXISTE — UNE HEURISTIQUE A MENTI, ET ELLE MENTAIT BIEN. On dérivait le
     * décalage en supposant « bloc à partir du slot 4 » (après les 4 slots de `System.Object`).
     * Sur `CampaignProgression` ça donnait `GetBattleRestrictions` / `GetDeployableUnits` /
     * `IsDeploymentUnlocked` en 0x14/0x15/0x16 — un groupe sémantique parfait pour un roster de
     * déploiement — et le corps ainsi nommé avait EXACTEMENT la forme du site d'appel. Deux
     * concordances indépendantes, et un compteur de passages les a démenties : la méthode
     * ancrée n'est JAMAIS entrée (`fires: 0`), ancrage pourtant vérifié à l'adresse près.
     * Une concordance de FORME n'est pas une mesure. Cf. case-10020.
     */
    ctx.rpc.classInterfaceSlots = (args: {
        ns: string; cls: string; itf?: string; indices?: number[]; forceInit?: boolean;
    }) => {
        const klass = findClassAnywhere(args.ns, args.cls);
        if (!klass) return { ok: false, error: `class not found: ${args.ns}.${args.cls}` };
        // Même cran que `resolveVtableSlot` : une classe FROIDE rend des slots nuls, ce qui se
        // lirait « pas d'implémentation » au lieu de « pas mesurée ».
        const init = classInitState(LIVE_CLASS_INIT_PROBE, klass, args.forceInit === true);
        let n = 0;
        try { n = klass.add(0x12e).readU16(); }
        catch (e) { return { ok: false, error: "count d'interfaces illisible : "
            + (e as Error).message }; }
        let pairs: NativePointer;
        try { pairs = klass.add(0xb0).readPointer(); }
        catch (e) { return { ok: false, error: "`interfaceOffsets` illisible : "
            + (e as Error).message }; }
        const indices = args.indices ?? [];
        const interfaces: Array<Record<string, unknown>> = [];
        for (let i = 0; i < n; i++) {
            let nom: string | null = null; let off = -1;
            try {
                const itf = pairs.add(i * 0x10).readPointer();
                off = pairs.add(i * 0x10 + 8).readS32();
                if (!itf.isNull()) nom = cstr(class_get_name(itf) as NativePointer);
            } catch { /* paire illisible — publiée telle quelle plutôt que sautée */ }
            const garde = args.itf === undefined
                || (nom !== null && nom.indexOf(args.itf) >= 0);
            const slots: Array<Record<string, unknown>> = [];
            if (garde && off >= 0) {
                for (const k of indices) {
                    let methode: string | null = null; let erreur: string | null = null;
                    try {
                        const mi = klass.add(0x138 + (off + k) * 0x10 + 8).readPointer();
                        if (mi.isNull()) erreur = "slot VIDE";
                        else methode = cstr(method_get_name(mi) as NativePointer);
                    } catch (e) { erreur = (e as Error).message; }
                    slots.push({ index: "0x" + k.toString(16), slot: off + k, methode, erreur });
                }
            }
            interfaces.push({ i, itf: nom, offset: off, retenue: garde, slots });
        }
        return { ok: true, ns: args.ns, cls: args.cls, klass: klass.toString(),
                 initialized: init.initialized, initializedBefore: init.initializedBefore,
                 forcedInit: init.forcedInit, nbInterfaces: n,
                 interfaces: args.itf === undefined
                     ? interfaces : interfaces.filter((x) => x.retenue) };
    };

    ctx.rpc.resolveVtableSlot = (args: {
        ns: string; cls: string; start?: number; end?: number; forceInit?: boolean;
    }) => {
        const klass = findClassAnywhere(args.ns, args.cls);
        if (!klass) return { ok: false, error: `class not found: ${args.ns}.${args.cls}` };
        // AVANT toute lecture de slot : l'ordre est le cran (cf. `class-init.ts`).
        const init = classInitState(LIVE_CLASS_INIT_PROBE, klass, args.forceInit === true);
        const start = args.start ?? 0x2f8;
        const end = args.end ?? 0x3b8;
        const base = il2cppBase;
        const slots: Array<{
            off: string; funcVA: string; funcRVA: string;
            ghidraVA: string; method: string | null;
        }> = [];
        for (let off = start; off <= end; off += 0x10) {
            let funcVA = "", funcRVA = "", ghidraVA = "", method: string | null = null;
            try {
                const fp = klass.add(off).readPointer();
                const mi = klass.add(off + 8).readPointer();
                funcVA = fp.toString();
                if (!fp.isNull()) {
                    const rva = fp.sub(base);
                    funcRVA = rva.toString();
                    // Ghidra image base for this binary = 0x180000000.
                    ghidraVA = ptr("0x180000000").add(rva).toString();
                }
                if (!mi.isNull()) {
                    const nm = method_get_name(mi) as NativePointer;
                    method = nm.isNull() ? null : cstr(nm);
                }
            } catch { /* garbage slot outside vtable — leave blanks */ }
            slots.push({ off: "0x" + off.toString(16), funcVA, funcRVA, ghidraVA, method });
        }
        // #982-r6 — le contexte SANS lequel les slots ne sont pas interprétables. `nonNullSlots`
        // est le témoin le plus direct : une classe froide en rend 0, et c'est le seul chiffre
        // qui distingue « lue et sans override » de « jamais réveillée ».
        const nonNullSlots = slots.filter((x) => x.method !== null).length;
        return { ok: true, ns: args.ns, cls: args.cls, klass: klass.toString(),
            initialized: init.initialized, initializedBefore: init.initializedBefore,
            forcedInit: init.forcedInit, forceInitError: init.forceInitError,
            runtimeClassInitAvailable: init.runtimeClassInitAvailable,
            slotCount: slots.length, nonNullSlots, slots };
    };

    /** Résout le POINTEUR D'ENTRÉE d'une méthode, en remontant la chaîne de
     * parents — le seul RPC du bundle qui RETOURNE une adresse de méthode.
     *
     * Motif (#259-b) : la chaîne Frida ne nomme aucun corps générique PLEINEMENT
     * PARTAGÉ (`__Il2CppFullySharedGeneric*`), parce que le dump énumère les
     * DÉFINITIONS génériques, dont le `methodPointer` est un thunk d'invocation
     * (établi au décompilé sur
     * `IdunBattle.AI.Playbook.TriggeredAbilityPlaybook`1$$Init`). Reste la question
     * ouverte : le `MethodInfo` d'une instance INFLATÉE porte-t-il, lui, le corps
     * partagé ? Si oui, un hook peut résoudre sa cible au RUNTIME au lieu de porter
     * une adresse en dur.
     *
     * On rend, PAR NIVEAU de la chaîne de parents et pour CHAQUE surcharge du nom :
     *   - `entry`   : `methodEntry(mi)` — ce que `findMethod` rendrait, donc ce
     *                 qu'un hook attacherait
     *   - `raw`     : le champ `methodPointer` lu directement (`mi+0`)
     *   - `invoker` : `MethodInfo.invoker_method` (`mi+0x10`)
     * `entry` et `raw` peuvent DIFFÉRER (`methodEntry` passe par
     * `il2cpp_method_get_pointer` quand l'export existe) — on montre les deux
     * plutôt que d'en choisir un.
     *
     * Lecture pure : aucun invoke, aucun hook posé.
     * args: { targets: [{ns, cls, method}], maxDepth? } */
    ctx.rpc.resolveMethodPtr = (args: {
        targets: Array<{ ns: string; cls: string; method: string }>;
        maxDepth?: number;
    }) => {
        const GHIDRA_BASE = ptr("0x180000000");
        const maxDepth = args.maxDepth ?? 6;
        const fmt = (p: NativePointer) => {
            if (p.isNull()) return { va: "0", rva: "0", ghidraVA: "0" };
            const rva = p.sub(il2cppBase);
            return {
                va: p.toString(), rva: rva.toString(),
                ghidraVA: GHIDRA_BASE.add(rva).toString(),
            };
        };
        const out = (args.targets ?? []).map((t) => {
            const klass = findClassAnywhere(t.ns, t.cls);
            if (!klass) {
                return { ns: t.ns, cls: t.cls, method: t.method,
                    ok: false, error: `class not found: ${t.ns}.${t.cls}` };
            }
            const levels: Array<{
                depth: number; klass: string; name: string;
                methods: Array<{
                    paramCount: number | null; mi: string;
                    entry: ReturnType<typeof fmt>;
                    raw: ReturnType<typeof fmt>;
                    invoker: ReturnType<typeof fmt>;
                }>;
            }> = [];
            let k = klass;
            for (let depth = 0; depth < maxDepth && !k.isNull(); depth++) {
                const nsName = cstr(class_get_namespace(k) as NativePointer);
                const clsName = cstr(class_get_name(k) as NativePointer);
                const methods: (typeof levels)[0]["methods"] = [];
                const it = Memory.alloc(Process.pointerSize);
                it.writePointer(ptr(0));
                let m: NativePointer;
                while (!(m = class_get_methods(k, it) as NativePointer).isNull()) {
                    if (cstr(method_get_name(m) as NativePointer) !== t.method) continue;
                    let pc: number | null = null;
                    try { pc = method_get_param_count(m) as number; } catch { /* */ }
                    let entry = ptr(0); let raw = ptr(0); let invoker = ptr(0);
                    try { entry = methodEntry(m); } catch { /* */ }
                    try { raw = m.readPointer(); } catch { /* */ }
                    try { invoker = m.add(0x10).readPointer(); } catch { /* */ }
                    methods.push({ paramCount: pc, mi: m.toString(),
                        entry: fmt(entry), raw: fmt(raw), invoker: fmt(invoker) });
                }
                levels.push({ depth, klass: k.toString(),
                    name: (nsName ? nsName + "." : "") + clsName, methods });
                k = class_get_parent(k) as NativePointer;
            }
            return { ns: t.ns, cls: t.cls, method: t.method, ok: true, levels };
        });
        return { ok: true, il2cppBase: il2cppBase.toString(), targets: out };
    };

    /** Dump every enum from DEFAULT_ENUMS in one call. Returns
     * `{ <ClassName>: { values, asm, ns, count }, ... }`. */
    ctx.rpc.dumpEnums = () => {
        const out: Record<string, {
            asm: string; ns: string; count: number; values: Record<string, string>;
        }> = {};
        for (const spec of DEFAULT_ENUMS) {
            const values = dumpEnum(spec.asm, spec.ns, spec.cls) ?? {};
            out[spec.cls] = {
                asm: spec.asm, ns: spec.ns,
                count: Object.keys(values).length,
                values,
            };
        }
        return out;
    };
}
