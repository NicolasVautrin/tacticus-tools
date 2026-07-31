import { findClassAnywhere, class_get_fields, field_get_name, field_get_offset, s } from "../il2cpp/helpers.js";

export function dumpCritBlockComps() {
    const components = ["CritChanceComponent", "CritDamageComponent", "BlockChanceComponent", "BlockDamageComponent"];
    for (const name of components) {
        const klass = findClassAnywhere("IdunBattle.Entities.Components", name);
        if (!klass) {
            console.log(`[dump] ${name} NOT found`);
            continue;
        }
        console.log(`[dump] Fields for ${name}:`);
        const it = Memory.alloc(Process.pointerSize);
        it.writePointer(ptr(0));
        let f: NativePointer;
        while (!(f = class_get_fields(klass, it) as NativePointer).isNull()) {
            const fname = s(field_get_name(f) as NativePointer);
            const off = field_get_offset(f) as number;
            console.log(`  - ${fname} @ +0x${off.toString(16)}`);
        }
    }
}
