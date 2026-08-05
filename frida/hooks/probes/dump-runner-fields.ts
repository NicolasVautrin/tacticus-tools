import { runnerClass } from "../game/runner.js";
import { class_get_fields, field_get_name, field_get_offset, s } from "../il2cpp/helpers.js";

export function dumpRunnerFields() {
    console.log(`[dump] Fields for IdunRunner:`);
    const it = Memory.alloc(Process.pointerSize);
    it.writePointer(ptr(0));
    let f: NativePointer;
    while (!(f = class_get_fields(runnerClass!, it) as NativePointer).isNull()) {
        const fname = s(field_get_name(f) as NativePointer);
        const off = field_get_offset(f) as number;
        console.log(`  - ${fname} @ +0x${off.toString(16)}`);
    }
}
