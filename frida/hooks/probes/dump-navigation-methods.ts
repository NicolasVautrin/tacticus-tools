import { findClassAnywhere, class_get_methods, method_get_name, method_get_param_count, s } from "../il2cpp/helpers.js";
import { Ctx } from "../controller.js";

export function dumpNavigationMethods() {
    const navKlass = findClassAnywhere("idun.UI", "IdunNavigation");
    if (!navKlass) {
        console.log("[dump-nav] IdunNavigation NOT found");
        return;
    }
    console.log("[dump-nav] Methods for IdunNavigation:");
    const it = Memory.alloc(Process.pointerSize);
    it.writePointer(ptr(0));
    let m: NativePointer;
    while (!(m = class_get_methods(navKlass, it) as NativePointer).isNull()) {
        const mname = s(method_get_name(m) as NativePointer);
        const pcount = method_get_param_count(m) as number;
        console.log(`  - ${mname} (params: ${pcount})`);
    }
}

export function register(ctx: Ctx) {
    ctx.rpc.dumpNavMethods = () => {
        dumpNavigationMethods();
        return { ok: true };
    };
}
