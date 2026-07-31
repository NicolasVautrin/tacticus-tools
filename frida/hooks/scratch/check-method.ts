import { findClassAnywhere, class_get_methods, method_get_name, method_get_param_count, s, methodEntry } from "../il2cpp/helpers.js";

export function checkGetMaxConfiguredRank() {
    const upCls = findClassAnywhere("IdunMetaLogic.UserProgress", "UnitProgression");
    if (!upCls) return;
    
    const it = Memory.alloc(Process.pointerSize).writePointer(ptr(0));
    let m: NativePointer;
    while (!(m = class_get_methods(upCls, it) as NativePointer).isNull()) {
        const name = s(method_get_name(m) as NativePointer);
        if (name === "GetMaxConfiguredRank") {
            const entry = methodEntry(m);
            console.log(`[dump] GetMaxConfiguredRank info=${m} entry=${entry}`);
        }
    }
}
