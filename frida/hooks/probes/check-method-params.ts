import { findClassAnywhere, class_get_methods, method_get_name, method_get_param_count, s, IL2CPP_MODULE_NAME } from "../il2cpp/helpers.js";
import { log } from "../runtime/diag.js";

const lib = Process.findModuleByName(IL2CPP_MODULE_NAME)!;
const expFn = (n: string): NativePointer => lib.findExportByName(n)!;
const paramFn = new NativeFunction(expFn("il2cpp_method_get_param"), "pointer", ["pointer", "uint32"]);
const type_get_name = new NativeFunction(expFn("il2cpp_type_get_name"), "pointer", ["pointer"]);

export function checkMethodParams() {
    log("[diag] Checking IdunNavigation.ToCampaign and ShowScreenAndHideOthers parameters...");
    const klass = findClassAnywhere("idun.UI", "IdunNavigation");
    if (!klass) {
        log("[diag] IdunNavigation class not found");
        return;
    }
    
    const it = Memory.alloc(Process.pointerSize);
    it.writePointer(ptr(0));
    let m: NativePointer;
    while (!(m = class_get_methods(klass, it) as NativePointer).isNull()) {
        const mname = s(method_get_name(m) as NativePointer);
        if (mname === "ToCampaign" || mname === "ShowScreenAndHideOthers" || mname === "ToHome") {
            const pcount = method_get_param_count(m) as number;
            log(`[diag] Method: ${mname} (${pcount} params)`);
            for (let i = 0; i < pcount; i++) {
                const p = paramFn(m, i);
                const pname = s(type_get_name(p) as NativePointer);
                log(`[diag]   - Param ${i}: ${pname}`);
            }
        }
    }
}
