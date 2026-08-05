// Inspect idun.UI.IdunNavigation: list methods + params, try to locate a
// live instance via UnityEngine.Object.FindFirstObjectByType.
// Returns everything via RPC payload (no console.log → not lost to stdout).

import {
    findClassAnywhere, class_get_methods, method_get_name,
    method_get_param_count, s as cstr, getSystemType, IL2CPP_MODULE_NAME,
    MethodRef, methodEntry,
} from "../il2cpp/helpers.js";
import { invokeMethod } from "../il2cpp/invoke.js";
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
    ctx.rpc.dumpIdunNavInfo = () => queueOnMainThread(() => {
        const klass = findClassAnywhere("idun.UI", "IdunNavigation");
        if (!klass) return { ok: false, err: "IdunNavigation class not found" };

        // List methods + param counts
        const methods: { name: string; params: number }[] = [];
        const it = Memory.alloc(Process.pointerSize);
        it.writePointer(ptr(0));
        let m: NativePointer;
        while (!(m = class_get_methods(klass, it) as NativePointer).isNull()) {
            const name = cstr(method_get_name(m) as NativePointer);
            const params = method_get_param_count(m) as number;
            methods.push({ name, params });
        }

        // Detail params for nav-relevant methods
        const lib = Process.findModuleByName(IL2CPP_MODULE_NAME)!;
        const getParamPtr = lib.findExportByName("il2cpp_method_get_param");
        const typeNamePtr = lib.findExportByName("il2cpp_type_get_name");
        const detailed: Record<string, string[]> = {};
        if (getParamPtr && typeNamePtr) {
            const getParam = new NativeFunction(
                getParamPtr, "pointer", ["pointer", "uint32"]);
            const typeGetName = new NativeFunction(
                typeNamePtr, "pointer", ["pointer"]);

            const it2 = Memory.alloc(Process.pointerSize);
            it2.writePointer(ptr(0));
            let m2: NativePointer;
            while (!(m2 = class_get_methods(klass, it2) as NativePointer).isNull()) {
                const name = cstr(method_get_name(m2) as NativePointer);
                if (!name.startsWith("To") && name !== "ShowScreenAndHideOthers") {
                    continue;
                }
                const pc = method_get_param_count(m2) as number;
                const types: string[] = [];
                for (let i = 0; i < pc; i++) {
                    const p = getParam(m2, i) as NativePointer;
                    types.push(cstr(typeGetName(p) as NativePointer));
                }
                detailed[`${name}/${pc}`] = types;
            }
        }

        // Try locating a live instance via FindFirstObjectByType(Type)
        let liveInstance: string | null = null;
        const objK = findClassAnywhere("UnityEngine", "Object");
        if (objK) {
            const findFirst = findMethodByParamCount(
                objK, "FindFirstObjectByType", 1);
            if (findFirst) {
                try {
                    const navType = getSystemType(klass);
                    const inst = invokeMethod(findFirst.info, null, [navType]);
                    liveInstance = inst.isNull() ? null : inst.toString();
                } catch (e) {
                    liveInstance = `error: ${(e as Error).message}`;
                }
            }
        }

        return {
            ok: true,
            klass: klass.toString(),
            methodCount: methods.length,
            navMethods: methods.filter(
                (mm) => mm.name.startsWith("To") ||
                       mm.name === "ShowScreenAndHideOthers"),
            detailedParams: detailed,
            liveInstance,
        };
    });
}
