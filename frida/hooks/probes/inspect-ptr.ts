import { class_get_name, class_get_namespace, s } from "../il2cpp/helpers.js";
import { log } from "../runtime/diag.js";

export function inspectPtr(pStr: string) {
    const p = ptr(pStr);
    log(`[diag] Inspecting ${p}...`);
    try {
        const klass = p.readPointer();
        log(`[diag] Klass pointer: ${klass}`);
        const name = s(class_get_name(klass) as NativePointer);
        const ns = s(class_get_namespace(klass) as NativePointer);
        log(`[diag] Class: ${ns}.${name}`);
    } catch (e) {
        log(`[diag] Failed to inspect ${p}: ` + (e as Error).message);
    }
}
