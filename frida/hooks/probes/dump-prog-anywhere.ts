import { class_get_fields, field_get_name, field_get_offset, s, domain_get, domain_get_assemblies, class_get_name, class_get_namespace, assembly_get_image, image_get_class_count, image_get_class } from "../il2cpp/helpers.js";

export function dumpUnitProgressionAnywhere() {
    const domain = domain_get() as NativePointer;
    const iter = Memory.alloc(Process.pointerSize).writePointer(ptr(0));
    let assembly: NativePointer;
    
    // il2cpp_domain_get_assemblies returns Assembly** (array) and sets a count.
    // Wait, the wrapper in helpers.ts is `domain_get_assemblies(domain, sizePtr)`.
    const sizePtr = Memory.alloc(4);
    const assemblies = domain_get_assemblies(domain, sizePtr) as NativePointer;
    const count = sizePtr.readU32();
    
    for (let i = 0; i < count; i++) {
        const assembly = assemblies.add(i * Process.pointerSize).readPointer();
        const image = assembly_get_image(assembly) as NativePointer;
        const classCount = image_get_class_count(image) as number;
        for (let j = 0; j < classCount; j++) {
            const klass = image_get_class(image, j) as NativePointer;
            if (klass.isNull()) continue;
            const kname = s(class_get_name(klass) as NativePointer);
            if (kname === "UnitProgression") {
                const knamespace = s(class_get_namespace(klass) as NativePointer);
                console.log(`[dump] Found UnitProgression in ${knamespace} @ ${klass}`);
                
                console.log(`[dump] Fields for ${knamespace}.UnitProgression:`);
                const f_iter = Memory.alloc(Process.pointerSize).writePointer(ptr(0));
                let f: NativePointer;
                while (!(f = class_get_fields(klass, f_iter) as NativePointer).isNull()) {
                    const fname = s(field_get_name(f) as NativePointer);
                    const off = field_get_offset(f) as number;
                    console.log(`  - ${fname} @ +0x${off.toString(16)}`);
                }
                return;
            }
        }
    }
    console.log("[dump] UnitProgression NOT found anywhere");
}
