import { findClassAnywhere, class_get_parent, s, class_get_name } from "../il2cpp/helpers.js";

export function checkParent() {
    const upCls = findClassAnywhere("IdunMetaLogic.UserProgress", "UnitProgression");
    if (!upCls) return;
    
    let k = upCls;
    while (!k.isNull()) {
        console.log(`[dump] Class: ${s(class_get_name(k) as NativePointer)}`);
        k = class_get_parent(k) as NativePointer;
    }
}
