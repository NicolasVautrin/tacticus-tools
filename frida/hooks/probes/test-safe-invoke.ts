import { findClassAnywhere, s } from "../il2cpp/helpers.js";
import { invokeMethod, createManagedString } from "../il2cpp/invoke.js";
import { log } from "../runtime/diag.js";

export function testSafeInvoke() {
    log("[diag] Testing UnitProgression.GetStats in-battle...");
    
    const upCls = findClassAnywhere("IdunMetaLogic.UserProgress", "UnitProgression");
    if (!upCls) { log("[diag] UnitProgression class not found"); return; }
    
    // Let's resolve the UnitProgression instance via Globals
    const globalsCls = findClassAnywhere("thor", "Globals");
    if (!globalsCls) { log("[diag] Globals class not found"); return; }
    
    const staticData = globalsCls.add(0xB8).readPointer();
    if (staticData.isNull()) { log("[diag] Globals static fields null"); return; }
    
    const globalsInstance = staticData.add(0x8).readPointer();
    if (globalsInstance.isNull()) { log("[diag] Globals instance null"); return; }
    
    const userProg = globalsInstance.add(0x68).readPointer();
    if (userProg.isNull()) { log("[diag] UserProgression null"); return; }
    
    const unitProg = userProg.add(0x20).readPointer();
    if (unitProg.isNull()) { log("[diag] UnitProgression null"); return; }
    
    log(`[diag] UnitProgression instance @ ${unitProg}`);
    
    // Find the GetStats method with 3 parameters
    let getStatsMethod: NativePointer | null = null;
    const it = Memory.alloc(Process.pointerSize);
    let m: NativePointer;
    const class_get_methods_fn = new NativeFunction(
        Process.findModuleByName("GameAssembly.dll")!.findExportByName("il2cpp_class_get_methods")!,
        "pointer", ["pointer", "pointer"]
    );
    const method_get_name_fn = new NativeFunction(
        Process.findModuleByName("GameAssembly.dll")!.findExportByName("il2cpp_method_get_name")!,
        "pointer", ["pointer"]
    );
    const method_get_param_count_fn = new NativeFunction(
        Process.findModuleByName("GameAssembly.dll")!.findExportByName("il2cpp_method_get_param_count")!,
        "uint32", ["pointer"]
    );
    
    it.writePointer(ptr(0));
    while (!(m = class_get_methods_fn(upCls, it) as NativePointer).isNull()) {
        const mname = s(method_get_name_fn(m) as NativePointer);
        if (mname === "GetStats") {
            const pcount = method_get_param_count_fn(m) as number;
            if (pcount === 3) {
                getStatsMethod = m;
                break;
            }
        }
    }
    
    if (!getStatsMethod) {
        log("[diag] GetStats(3 params) method not found");
        return;
    }
    
    log(`[diag] Found GetStats method @ ${getStatsMethod}`);
    
    const unitId = "ultraTigurius";
    const managedUnitId = createManagedString(unitId);
    
    try {
        const pIdx = Memory.alloc(4);
        pIdx.writeS32(17); // D3
        
        const pLvl = Memory.alloc(4);
        pLvl.writeS32(50); // Lvl 50
        
        log("[diag] Calling UnitProgression.GetStats...");
        const statsObj = invokeMethod(getStatsMethod, unitProg, [managedUnitId, pIdx, pLvl]);
        if (!statsObj.isNull()) {
            const health = statsObj.add(0x10).readS32();
            const damage = statsObj.add(0x14).readS32();
            const armor = statsObj.add(0x1C).readS32();
            log(`[diag] Success! D3 Stats for ${unitId}: Health=${health}, Damage=${damage}, Armor=${armor}`);
        } else {
            log("[diag] Returned statsObj is null!");
        }
    } catch (e) {
        log("[diag] Exception calling GetStats: " + (e as Error).message);
    }
}
