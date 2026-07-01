// Runtime introspection — RPCs the host calls to extract IL2CPP metadata
// (enums, class layouts, …) and persist them to disk so the front-end can
// load them via plain HTTP without a live Frida session.
//
// Pattern:
//   1. host POSTs /api/introspect/enums → calls `dumpEnums()` RPC
//   2. agent walks the requested classes' static-literal fields, builds
//      `{ EnumName: { intValue: name } }`
//   3. host writes the result to `frida/assets/public/enums.json`
//   4. front fetches `/assets/enums.json` at boot, caches in `state.enums`
//
// No background hook, no `send()` — the call returns synchronously and the
// host is in charge of where the data lands.

import { dumpEnum } from "../il2cpp/enum-dump.js";
import {
    findClass, findClassAnywhere, findMethod, readIl2cppString,
    method_get_name, cstr, il2cppBase,
} from "../il2cpp/helpers.js";
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
     * `{ values: { "0": "None", "1": "X", ... } }` or null if not found. */
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
     * args: { ns, cls, start?, end? } — offsets in bytes, default 0x2f8..0x3b8. */
    ctx.rpc.resolveVtableSlot = (args: {
        ns: string; cls: string; start?: number; end?: number;
    }) => {
        const klass = findClassAnywhere(args.ns, args.cls);
        if (!klass) return { ok: false, error: `class not found: ${args.ns}.${args.cls}` };
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
        return { ok: true, ns: args.ns, cls: args.cls, klass: klass.toString(), slots };
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
