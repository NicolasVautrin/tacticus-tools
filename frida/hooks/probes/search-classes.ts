import { IL2CPP_MODULE_NAME, s } from "../il2cpp/helpers.js";

const lib = Process.findModuleByName(IL2CPP_MODULE_NAME)!;
const expFn = (n: string): NativePointer => {
    const p = lib.findExportByName(n);
    if (!p) {
        console.log(`[warning] Export not found: ${n}`);
    }
    return p || ptr(0);
};

const domain_get_ptr = expFn("il2cpp_domain_get");
const domain_get = domain_get_ptr.isNull() ? null : new NativeFunction(domain_get_ptr, "pointer", []);

const domain_get_assemblies_ptr = expFn("il2cpp_domain_get_assemblies");
const domain_get_assemblies = domain_get_assemblies_ptr.isNull() ? null : new NativeFunction(domain_get_assemblies_ptr, "pointer", ["pointer", "pointer"]);

const assembly_get_image_ptr = expFn("il2cpp_assembly_get_image");
const assembly_get_image = assembly_get_image_ptr.isNull() ? null : new NativeFunction(assembly_get_image_ptr, "pointer", ["pointer"]);

const image_get_class_count_ptr = expFn("il2cpp_image_get_class_count");
const image_get_class_count = image_get_class_count_ptr.isNull() ? null : new NativeFunction(image_get_class_count_ptr, "size_t", ["pointer"]);

const image_get_class_ptr = expFn("il2cpp_image_get_class");
const image_get_class = image_get_class_ptr.isNull() ? null : new NativeFunction(image_get_class_ptr, "pointer", ["pointer", "size_t"]);

const class_get_name_ptr = expFn("il2cpp_class_get_name");
const class_get_name = class_get_name_ptr.isNull() ? null : new NativeFunction(class_get_name_ptr, "pointer", ["pointer"]);

const class_get_namespace_ptr = expFn("il2cpp_class_get_namespace");
const class_get_namespace = class_get_namespace_ptr.isNull() ? null : new NativeFunction(class_get_namespace_ptr, "pointer", ["pointer"]);

const class_get_instance_size_ptr = expFn("il2cpp_class_get_instance_size");
const class_get_instance_size = class_get_instance_size_ptr.isNull() ? null : new NativeFunction(class_get_instance_size_ptr, "int32", ["pointer"]);

const class_is_valuetype_ptr = expFn("il2cpp_class_is_valuetype");
const class_is_valuetype = class_is_valuetype_ptr.isNull() ? null : new NativeFunction(class_is_valuetype_ptr, "bool", ["pointer"]);

const class_get_fields_ptr = expFn("il2cpp_class_get_fields");
const class_get_fields = class_get_fields_ptr.isNull() ? null : new NativeFunction(class_get_fields_ptr, "pointer", ["pointer", "pointer"]);

const field_get_name_ptr = expFn("il2cpp_field_get_name");
const field_get_name = field_get_name_ptr.isNull() ? null : new NativeFunction(field_get_name_ptr, "pointer", ["pointer"]);

const field_get_offset_ptr = expFn("il2cpp_field_get_offset");
const field_get_offset = field_get_offset_ptr.isNull() ? null : new NativeFunction(field_get_offset_ptr, "int32", ["pointer"]);

export function searchAllClasses(query: string) {
    if (!domain_get || !domain_get_assemblies || !assembly_get_image || !image_get_class_count || !image_get_class || !class_get_name || !class_get_namespace || !class_get_fields || !field_get_name || !field_get_offset) {
        console.log("[error] Required IL2CPP exports not found.");
        return;
    }

    const domain = domain_get();
    const sizePtr = Memory.alloc(Process.pointerSize);
    const assemblies = domain_get_assemblies(domain, sizePtr);
    const count = sizePtr.readPointer().toUInt32();

    for (let i = 0; i < count; i++) {
        const asm = assemblies.add(i * Process.pointerSize).readPointer();
        const img = assembly_get_image(asm);
        const classCount = (image_get_class_count(img) as any) as number;
        
        for (let j = 0; j < classCount; j++) {
            const klass = image_get_class(img, j);
            if (klass.isNull()) continue;
            const name = s(class_get_name(klass) as NativePointer);
            if (name.indexOf(query) >= 0) {
                const ns = s(class_get_namespace(klass) as NativePointer);
                const isVal = class_is_valuetype ? class_is_valuetype(klass) : "unknown";
                const size = class_get_instance_size ? class_get_instance_size(klass) as number : "unknown";
                console.log(`[dump] Match: ${ns}.${name} (isValType=${isVal}, size=${size})`);
                
                // Dump all fields
                const it = Memory.alloc(Process.pointerSize);
                it.writePointer(ptr(0));
                let f: NativePointer;
                while (!(f = class_get_fields(klass, it) as NativePointer).isNull()) {
                    const fname = s(field_get_name(f) as NativePointer);
                    const off = field_get_offset(f) as number;
                    console.log(`  - Field: ${fname} @ +0x${off.toString(16)} (${off})`);
                }
            }
        }
    }
}
