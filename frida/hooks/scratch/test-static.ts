import { findClassAnywhere, findMethod, s } from "../il2cpp/helpers.js";
import { invokeMethod } from "../il2cpp/invoke.js";

export function testStatic() {
    const cls = findClassAnywhere("UnityEngine", "Debug");
    if (!cls) return;
    const mi = findMethod(cls, "Log"); // Removed paramCount to test
    if (!mi) return;
    
    console.log(`[dump] Testing static Debug.Log...`);
    try {
        const msg = Memory.allocUtf8String("Hello from Frida!");
        const il2cpp = Process.findModuleByName("GameAssembly.dll")!;
        const _stringNew = new NativeFunction(il2cpp.findExportByName("il2cpp_string_new")!, "pointer", ["pointer"]);
        const sObj = _stringNew(msg) as NativePointer;
        
        invokeMethod(mi.info, ptr(0), [sObj]);
        console.log(`[dump] Success!`);
    } catch (e) {
        console.log("[dump] Error: " + (e as Error).message);
    }
}
