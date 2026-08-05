import { findClassAnywhere, class_get_methods, method_get_name, method_get_param_count, s } from "../il2cpp/helpers.js";

export function dumpProgressionExtensions() {
    const name = "IUnitProgressionExtensions";
    const klass = findClassAnywhere("idun.meta.extensions", name);
    if (!klass) {
        console.log(`[dump] ${name} NOT found`);
        return;
    }
    console.log(`[dump] Methods for ${name}:`);
    const it = Memory.alloc(Process.pointerSize);
    it.writePointer(ptr(0));
    let m: NativePointer;
    while (!(m = class_get_methods(klass, it) as NativePointer).isNull()) {
        const mname = s(method_get_name(m) as NativePointer);
        const pcount = method_get_param_count(m) as number;
        console.log(`  - ${mname} (${pcount} params)`);
    }
}
