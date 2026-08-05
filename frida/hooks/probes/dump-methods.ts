import { findClassAnywhere, class_get_methods, method_get_name, s } from "../il2cpp/helpers.js";

export function dumpComponentMethods() {
    const components = ["MovementComponent", "AttackComponent", "UnitComponent"];
    for (const name of components) {
        const klass = findClassAnywhere("IdunBattle.Entities.Components", name);
        if (!klass) continue;
        console.log(`[dump] Methods for ${name}:`);
        const it = Memory.alloc(Process.pointerSize);
        it.writePointer(ptr(0));
        let m: NativePointer;
        while (!(m = class_get_methods(klass, it) as NativePointer).isNull()) {
            const mname = s(method_get_name(m) as NativePointer);
            console.log(`  - ${mname}`);
        }
    }
}
