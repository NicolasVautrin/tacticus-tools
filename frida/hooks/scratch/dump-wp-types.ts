import { findClassAnywhere, class_get_fields, field_get_name, field_get_type, IL2CPP_MODULE_NAME, s } from "../il2cpp/helpers.js";

const lib = Process.findModuleByName(IL2CPP_MODULE_NAME)!;
const expFn = (n: string): NativePointer => lib.findExportByName(n)!;
const type_get_name = new NativeFunction(expFn("il2cpp_type_get_name"), "pointer", ["pointer"]);

export function dumpWeaponProfileTypes() {
    const klass = findClassAnywhere("IdunShared.Battle", "WeaponProfile");
    if (!klass) return;
    const it = Memory.alloc(Process.pointerSize);
    it.writePointer(ptr(0));
    let f: NativePointer;
    while (!(f = class_get_fields(klass, it) as NativePointer).isNull()) {
        const fname = s(field_get_name(f) as NativePointer);
        const t = field_get_type(f);
        const tname = s(type_get_name(t) as NativePointer);
        console.log(`[dump] Field ${fname} type: ${tname}`);
    }
}
