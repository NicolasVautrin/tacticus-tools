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
import { findClass, findMethod, readIl2cppString } from "../il2cpp/helpers.js";
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
