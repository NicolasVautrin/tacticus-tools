import { findClassAnywhere, class_get_fields, field_get_name, field_get_offset, s } from "../il2cpp/helpers.js";
import { log } from "../runtime/diag.js";

export function checkStatsFields() {
    const classes = [
        { ns: "IdunMetaLogic.UserProgress.Model", name: "UnitStats" },
        { ns: "IdunMetaLogic.UserProgress.Model", name: "CalculatedStatsUnitModel" }
    ];
    for (const c of classes) {
        const klass = findClassAnywhere(c.ns, c.name);
        if (!klass) {
            log(`[diag] ${c.ns}.${c.name} not found`);
            continue;
        }
        log(`[diag] Fields for ${c.ns}.${c.name}:`);
        const it = Memory.alloc(Process.pointerSize);
        it.writePointer(ptr(0));
        let f: NativePointer;
        while (!(f = class_get_fields(klass, it) as NativePointer).isNull()) {
            const fname = s(field_get_name(f) as NativePointer);
            const off = field_get_offset(f) as number;
            log(`[diag]   - ${fname} @ +0x${off.toString(16)}`);
        }
    }
}
