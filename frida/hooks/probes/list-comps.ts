import { IL2CPP_MODULE_NAME, s } from "../il2cpp/helpers.js";

const lib = Process.findModuleByName(IL2CPP_MODULE_NAME)!;
const expFn = (n: string): NativePointer => lib.findExportByName(n)!;

const domain_get = new NativeFunction(expFn("il2cpp_domain_get"), "pointer", []);
const domain_get_assemblies = new NativeFunction(expFn("il2cpp_domain_get_assemblies"), "pointer", ["pointer", "pointer"]);
const assembly_get_image = new NativeFunction(expFn("il2cpp_assembly_get_image"), "pointer", ["pointer"]);
const image_get_class_count = new NativeFunction(expFn("il2cpp_image_get_class_count"), "size_t", ["pointer"]);
const image_get_class = new NativeFunction(expFn("il2cpp_image_get_class"), "pointer", ["pointer", "size_t"]);
const class_get_name = new NativeFunction(expFn("il2cpp_class_get_name"), "pointer", ["pointer"]);
const class_get_namespace = new NativeFunction(expFn("il2cpp_class_get_namespace"), "pointer", ["pointer"]);

export function dumpAllComponents() {
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
            const ns = s(class_get_namespace(klass) as NativePointer);
            if (ns === "IdunBattle.Entities.Components") {
                const name = s(class_get_name(klass) as NativePointer);
                if (name.endsWith("Component")) {
                    console.log(`[dump] Found Component: ${name}`);
                }
            }
        }
    }
}
