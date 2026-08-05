import { findClassAnywhere, getFieldOffset, s, class_get_name } from "../il2cpp/helpers.js";

const il2cpp = Process.findModuleByName("GameAssembly.dll")!;
const _objectGetClass = new NativeFunction(il2cpp.findExportByName("il2cpp_object_get_class")!, "pointer", ["pointer"]);
const _classIsAssignableFrom = new NativeFunction(il2cpp.findExportByName("il2cpp_class_is_assignable_from")!, "uint8", ["pointer", "pointer"]);

function findInstanceByHeapScan(klass: NativePointer, validate?: (candidate: NativePointer) => boolean): NativePointer | null {
    const patternHex = (() => {
        const v = klass.toString(16).padStart(16, "0");
        const bytes: string[] = [];
        for (let i = 7; i >= 0; i--) bytes.push(v.substr(i * 2, 2));
        return bytes.join(" ");
    })();
    let match: NativePointer | null = null;
    const ranges = Process.enumerateRanges("rw-");
    for (const r of ranges) {
        if (match) break;
        if (r.size < 1024 * 1024) continue;
        try {
            Memory.scanSync(r.base, r.size, patternHex).forEach((m) => {
                if (match) return;
                const candidate = m.address;
                try {
                    if (!candidate.readPointer().equals(klass)) return;
                    if (validate && !validate(candidate)) return;
                    match = candidate;
                } catch { }
            });
        } catch { }
    }
    return match;
}

export function findProgressionSingletons() {
    const upCls = findClassAnywhere("IdunMetaLogic.UserProgress", "UnitProgression");
    if (!upCls) return { ok: false, msg: "UnitProgression class not found" };

    const instance = findInstanceByHeapScan(upCls, (cand) => {
        try {
            const candKlass = _objectGetClass(cand) as NativePointer;
            if (candKlass.isNull()) return false;
            if (!(_classIsAssignableFrom(upCls, candKlass) as number)) return false;
            // Check _unitsConfig @ 0x38
            const uc = cand.add(0x38).readPointer();
            return !uc.isNull();
        } catch { return false; }
    });

    if (instance) {
        console.log(`[dump] Found UnitProgression instance @ ${instance}`);
        const statsFormula = instance.add(0x80).readPointer();
        console.log(`[dump] StatsFormula @ ${statsFormula}`);
        return { ok: true, up: instance, sf: statsFormula };
    }

    return { ok: false, msg: "Instance not found" };
}
