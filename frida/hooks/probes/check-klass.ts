import { findClassAnywhere } from "../il2cpp/helpers.js";

export function checkKlass() {
    const upCls = findClassAnywhere("IdunMetaLogic.UserProgress", "UnitProgression");
    console.log(`[dump] UnitProgression klass: ${upCls}`);
}
