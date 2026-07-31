import { findClassAnywhere, class_get_methods, method_get_name, method_get_param_count, s } from "../il2cpp/helpers.js";

export function dumpPathfinderMethods() {
    const klass = findClassAnywhere("IdunBattle.Entities.Pathfinding", "Pathfinders");
    if (!klass) {
        console.log("[dump] Pathfinders NOT found in IdunBattle.Entities.Pathfinding");
        return;
    }
    console.log(`[dump] Methods for Pathfinders:`);
    const it = Memory.alloc(Process.pointerSize);
    it.writePointer(ptr(0));
    let m: NativePointer;
    while (!(m = class_get_methods(klass, it) as NativePointer).isNull()) {
        const mname = s(method_get_name(m) as NativePointer);
        const pcount = method_get_param_count(m);
        console.log(`  - ${mname} (${pcount} params)`);
    }
}
