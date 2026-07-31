import { domain_get, domain_get_assemblies, assembly_get_image, image_get_class_count, image_get_class, class_get_name, class_get_namespace } from "../il2cpp/helpers.js";
import { log } from "../runtime/diag.js";

export function searchForGlobals() {
    log("[diag] Searching for Globals class in all assemblies...");
    const domain = domain_get();
    const sizePtr = Memory.alloc(Process.pointerSize);
    const assembliesPtr = domain_get_assemblies(domain, sizePtr) as NativePointer;
    const count = sizePtr.readPointer().toInt32(); // il2cpp_domain_get_assemblies uses size_t*
    
    log(`[diag] Found ${count} assemblies`);
    
    for (let i = 0; i < count; i++) {
        const assembly = assembliesPtr.add(i * Process.pointerSize).readPointer();
        const image = assembly_get_image(assembly);
        const classCount = image_get_class_count(image);
        for (let j = 0; j < classCount; j++) {
            const klass = image_get_class(image, j);
            const name = class_get_name(klass).readUtf8String();
            if (name === "Globals") {
                const ns = class_get_namespace(klass).readUtf8String();
                log(`[diag] Found Globals at NS="${ns}", klass=${klass}`);
            }
        }
    }
}
