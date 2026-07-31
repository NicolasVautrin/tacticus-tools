import { findClassAnywhere } from "../il2cpp/helpers.js";
import { log } from "../runtime/diag.js";

export function findSingletonsViaGlobals() {
    log("[diag] Finding singletons via thor.Globals...");
    const globalsCls = findClassAnywhere("thor", "Globals");
    if (!globalsCls) { log("[diag] Globals class not found in NS=thor"); return; }
    
    const staticData = globalsCls.add(0xB8).readPointer();
    if (staticData.isNull()) { log("[diag] Globals static fields null"); return; }
    
    const globalsInstance = staticData.add(0x8).readPointer();
    log(`[diag] Globals instance @ ${globalsInstance}`);
    if (globalsInstance.isNull()) return;
    
    try {
        const userProg = globalsInstance.add(0x68).readPointer();
        log(`[diag] UserProgression @ ${userProg}`);
        if (!userProg.isNull()) {
            const statsFormula = userProg.add(0x1D0).readPointer();
            log(`[diag] StatsFormula @ ${statsFormula}`);
            
            const unitProg = userProg.add(0x20).readPointer();
            log(`[diag] UnitProgression @ ${unitProg}`);
            
            if (!unitProg.isNull()) {
                // UnitProgression._unitProgressionData @ 0x30
                const unitProgData = unitProg.add(0x30).readPointer();
                log(`[diag] IUnitProgressionData proxy @ ${unitProgData}`);
            }
        }
    } catch (e) {
        log("[diag] Error reading fields: " + (e as Error).message);
    }
}
