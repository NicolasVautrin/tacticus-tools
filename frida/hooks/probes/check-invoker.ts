import { IL2CPP_MODULE_NAME } from "../il2cpp/helpers.js";

export function checkInvokerExport() {
    const lib = Process.findModuleByName(IL2CPP_MODULE_NAME)!;
    const p = lib.findExportByName("il2cpp_method_get_invoker");
    console.log(`[dump] il2cpp_method_get_invoker: ${p}`);
}
