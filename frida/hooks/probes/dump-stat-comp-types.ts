import { findClassAnywhere, class_get_fields, field_get_name, field_get_type, s } from "../il2cpp/helpers.js";

export function dumpStatComponentFieldTypes() {
    const name = "StatComponent";
    const klass = findClassAnywhere("IdunBattle.Entities.Components", name);
    if (!klass) return;
    
    console.log(`[dump] Field types for ${name}:`);
    const it = Memory.alloc(Process.pointerSize).writePointer(ptr(0));
    let f: NativePointer;
    while (!(f = class_get_fields(klass, it) as NativePointer).isNull()) {
        const fname = s(field_get_name(f) as NativePointer);
        const ftype = field_get_type(f) as NativePointer;
        // il2cpp_type_get_name
        const il2cpp = Process.findModuleByName("GameAssembly.dll")!;
        const _typeName = new NativeFunction(il2cpp.findExportByName("il2cpp_type_get_name")!, "pointer", ["pointer"]);
        console.log(`  - ${fname}: ${s(_typeName(ftype) as NativePointer)}`);
    }
}
