import { class_get_fields, field_get_name, field_get_offset, s, domain_get, domain_get_assemblies, class_get_name, class_get_namespace, assembly_get_image, image_get_class_count, image_get_class } from "../il2cpp/helpers.js";

export function findUnitProgressionInstance() {
    const domain = domain_get() as NativePointer;
    const sizePtr = Memory.alloc(4);
    const assemblies = domain_get_assemblies(domain, sizePtr) as NativePointer;
    const count = sizePtr.readU32();
    
    for (let i = 0; i < count; i++) {
        const assembly = assemblies.add(i * Process.pointerSize).readPointer();
        const image = assembly_get_image(assembly) as NativePointer;
        const classCount = image_get_class_count(image) as number;
        for (let j = 0; j < classCount; j++) {
            const klass = image_get_class(image, j) as NativePointer;
            const kname = s(class_get_name(klass) as NativePointer);
            if (kname === "UnitProgression") {
                const knamespace = s(class_get_namespace(klass) as NativePointer);
                if (knamespace === "IdunMetaLogic.UserProgress") {
                    console.log(`[dump] Found UnitProgression class @ ${klass}`);
                    // Check for static fields
                    // il2cpp doesn't differentiate static fields in class_get_fields if I recall correctly,
                    // but they have a different offset (usually 0 or special).
                    // Actually, il2cpp_class_get_fields returns all fields.
                }
            }
        }
    }
}
