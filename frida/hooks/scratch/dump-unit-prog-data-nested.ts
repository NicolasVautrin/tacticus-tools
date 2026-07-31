import { findClassAnywhere, class_get_nested_types, s, class_get_name } from "../il2cpp/helpers.js";

export function dumpUnitProgDataNested() {
    const name = "UnitProgressionData";
    const klass = findClassAnywhere("IdunMetaLogic.UserProgress.Data", name);
    if (!klass) return;
    
    console.log(`[dump] Nested types for ${name}:`);
    const it = Memory.alloc(Process.pointerSize).writePointer(ptr(0));
    let n: NativePointer;
    while (!(n = class_get_nested_types(klass, it) as NativePointer).isNull()) {
        console.log(`  - ${s(class_get_name(n) as NativePointer)}`);
    }
}
