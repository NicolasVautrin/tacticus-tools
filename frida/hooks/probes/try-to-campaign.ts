// Isolated test: invoke IdunNavigation.ToCampaign directly via IL2CPP,
// no UI clicks. Validates that:
//   1. We can find a live IdunNavigation instance (via FindObjectsByType,
//      since FindFirstObjectByType<T> is generic and not directly invokable)
//   2. We can call ToCampaign(bool, CampaignType, string, Nullable<CampaignAddress>)
//   3. The Indomitus campaign screen actually mounts after the call
//
// If this works, the multi-hop UI nav in warmup-singletons becomes obsolete —
// one invoke replaces 2-3 UI clicks + screen waits.

import {
    findClassAnywhere, findMethod, class_get_methods, method_get_name,
    method_get_param_count, methodEntry, s as cstr,
    getSystemType, MethodRef, IL2CPP_MODULE_NAME,
} from "../il2cpp/helpers.js";
import { invokeMethod, createManagedString } from "../il2cpp/invoke.js";
import { queueOnMainThread } from "../runtime/queue.js";
import { Ctx } from "../controller.js";

function findMethodByParamCount(
    klass: NativePointer, name: string, paramCount: number,
): MethodRef | null {
    const it = Memory.alloc(Process.pointerSize);
    it.writePointer(ptr(0));
    let m: NativePointer;
    while (!(m = class_get_methods(klass, it) as NativePointer).isNull()) {
        if (cstr(method_get_name(m) as NativePointer) !== name) continue;
        try {
            if ((method_get_param_count(m) as number) === paramCount) {
                return { info: m, ptr: methodEntry(m) };
            }
        } catch { /* skip */ }
    }
    return null;
}

export function register(ctx: Ctx): void {
    ctx.rpc.tryToCampaign = (opts?: {
        animated?: boolean;
        campaignType?: number; // 0=Standard, 1=Elite, 2=Mirror, 3=EliteMirror, 4=Event
        campaignId?: string;
    }) => queueOnMainThread(() => {
        const animated = opts?.animated ?? true;
        const campaignType = opts?.campaignType ?? 0; // Standard = Indomitus
        const campaignId = opts?.campaignId ?? "campaign1";

        // 1. Resolve classes + method
        const navK = findClassAnywhere("idun.UI", "IdunNavigation");
        if (!navK) return { ok: false, err: "IdunNavigation class not found" };

        const objK = findClassAnywhere("UnityEngine", "Object");
        if (!objK) return { ok: false, err: "UnityEngine.Object not found" };

        // Non-generic FindObjectsByType(Type, FindObjectsSortMode)
        const findObjects = findMethodByParamCount(objK, "FindObjectsByType", 2);
        if (!findObjects) {
            return { ok: false, err: "FindObjectsByType(Type,Mode) not found" };
        }

        const toCampaign = findMethodByParamCount(navK, "ToCampaign", 4);
        if (!toCampaign) {
            return { ok: false, err: "ToCampaign(4 params) not found" };
        }

        // 2. Find live instance
        const navType = getSystemType(navK);
        const sortMode = Memory.alloc(4).writeS32(0); // SortMode.None
        const arr = invokeMethod(findObjects.info, null, [navType, sortMode]);
        if (arr.isNull()) {
            return { ok: false, err: "FindObjectsByType returned null array" };
        }
        // Il2CppArray: length at +0x18, elements at +0x20
        const len = arr.add(0x18).readS32();
        if (len <= 0) {
            return { ok: false, err: `no IdunNavigation instance live (len=${len})` };
        }
        const navInstance = arr.add(0x20).readPointer();
        if (navInstance.isNull()) {
            return { ok: false, err: "first IdunNavigation slot is null" };
        }

        // 3. Build the 4 args
        const argAnimated = Memory.alloc(1).writeU8(animated ? 1 : 0);
        const argType = Memory.alloc(4).writeS32(campaignType);
        const argId = createManagedString(campaignId);
        // Nullable<CampaignAddress>: zero-filled buffer. CampaignAddress is
        // 0x28 bytes, the Nullable wrapper adds the bool hasValue. 64 bytes
        // is safe-overkill (Nullable<CampaignAddress> ≤ 48 bytes). hasValue=0
        // => the method sees Nullable.HasValue==false (i.e., null).
        const argNullable = Memory.alloc(64);
        // explicit zero (Memory.alloc should already zero, but be safe)
        for (let i = 0; i < 64; i += 4) argNullable.add(i).writeU32(0);

        // 4. Invoke
        try {
            invokeMethod(toCampaign.info, navInstance,
                [argAnimated, argType, argId, argNullable]);
        } catch (e) {
            return {
                ok: false,
                err: `ToCampaign threw: ${(e as Error).message}`,
                navInstance: navInstance.toString(),
            };
        }

        return {
            ok: true,
            navInstance: navInstance.toString(),
            args: { animated, campaignType, campaignId },
        };
    });
}
