import { findClassAnywhere, class_get_fields, field_get_name, field_get_offset, field_get_type, IL2CPP_MODULE_NAME, s } from "../il2cpp/helpers.js";

const lib = Process.findModuleByName(IL2CPP_MODULE_NAME)!;
const expFn = (n: string): NativePointer => lib.findExportByName(n)!;
const type_get_name = new NativeFunction(expFn("il2cpp_type_get_name"), "pointer", ["pointer"]);

export function dumpUnitEntityFields() {
    const name = "UnitEntity";
    const klass = findClassAnywhere("IdunBattle.Core", name);
    if (!klass) {
        console.log(`[dump] ${name} NOT found`);
        return;
    }
    console.log(`[dump] Fields for ${klass} (${name}):`);
    const it = Memory.alloc(Process.pointerSize);
    it.writePointer(ptr(0));
    let f: NativePointer;
    while (!(f = class_get_fields(klass, it) as NativePointer).isNull()) {
        const fname = s(field_get_name(f) as NativePointer);
        const off = field_get_offset(f) as number;
        const t = field_get_type(f);
        const tname = s(type_get_name(t) as NativePointer);
        console.log(`  - ${fname} @ +0x${off.toString(16)} (type: ${tname})`);
    }
}
