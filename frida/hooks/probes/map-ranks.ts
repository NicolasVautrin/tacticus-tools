import { findClassAnywhere, findMethod, s, methodEntry, methodInvoker } from "../il2cpp/helpers.js";
import { findProgressionSingletons } from "./find-prog-instances.js";

export function findD3Index() {
    const res = findProgressionSingletons();
    if (!res.ok || !res.up) return;
    const upInstance = res.up as NativePointer;

    const upCls = findClassAnywhere("IdunMetaLogic.UserProgress", "UnitProgression");
    if (!upCls) return;

    const getMaxRankMi = findMethod(upCls, "GetMaxConfiguredRank");
    if (!getMaxRankMi) return;

    console.log(`[dump] Calling GetMaxConfiguredRank via invoker...`);
    try {
        const invokerPtr = methodInvoker(getMaxRankMi.info);
        const entryPtr = methodEntry(getMaxRankMi.info);
        
        // `propagate` : l'invoker EXECUTE du managE, cf. `il2cpp/invoke.ts`.
        const invoker = new NativeFunction(invokerPtr, "pointer",
                                           ["pointer", "pointer", "pointer", "pointer"],
                                           { exceptions: "propagate" });
        // Il2CppObject* invoker(Il2CppMethodPointer method, MethodInfo* method, void* obj, void** params)
        const ret = invoker(entryPtr, getMaxRankMi.info, upInstance, ptr(0)) as NativePointer;
        
        console.log(`[dump] Result ptr: ${ret}`);
        if (!ret.isNull()) {
            const val = ret.add(0x10).readS32();
            console.log(`[dump] Max Rank: ${val}`);
        }
    } catch (e) {
        console.log("[dump] Error: " + (e as Error).message);
    }
}
