import { findClassAnywhere, class_get_fields, field_get_name, field_get_type, type_get_class_or_element_class, class_get_name, class_get_namespace, s } from "../il2cpp/helpers.js";

export function debugFlagsType() {
    const name = "UnitFlagsComponent";
    const klass = findClassAnywhere("IdunBattle.Entities.Components", name);
    if (!klass) return;
    const it = Memory.alloc(Process.pointerSize);
    it.writePointer(ptr(0));
    let f: NativePointer;
    while (!(f = class_get_fields(klass, it) as NativePointer).isNull()) {
        const fname = s(field_get_name(f) as NativePointer);
        if (fname === "Flags") {
            const ft = field_get_type(f) as NativePointer;
            const fcls = type_get_class_or_element_class(ft) as NativePointer;
            if (!fcls.isNull()) {
                const ns = s(class_get_namespace(fcls) as NativePointer);
                const n = s(class_get_name(fcls) as NativePointer);
                console.log(`[dump] Flags field type: ${ns}.${n}`);
            } else {
                console.log(`[dump] Flags field type: null class`);
            }
        }
    }
}
