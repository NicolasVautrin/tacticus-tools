import { findProgressionSingletons } from "./find-prog-instances.js";

export function inspectInstance() {
    const res = findProgressionSingletons();
    if (!res.ok || !res.up) return;
    const upInstance = res.up as NativePointer;
    
    console.log(`[dump] Inspecting UnitProgression @ ${upInstance}:`);
    console.log(hexdump(upInstance, { length: 64 }));
}
