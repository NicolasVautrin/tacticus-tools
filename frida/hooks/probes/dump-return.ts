import { findClassAnywhere, class_get_methods, method_get_name, s, IL2CPP_MODULE_NAME } from "../il2cpp/helpers.js";

const lib = Process.findModuleByName(IL2CPP_MODULE_NAME)!;
const expFn = (n: string): NativePointer => lib.findExportByName(n)!;
const method_get_return_type = new NativeFunction(expFn("il2cpp_method_get_return_type"), "pointer", ["pointer"]);
const type_get_name = new NativeFunction(expFn("il2cpp_type_get_name"), "pointer", ["pointer"]);

export function dumpPathfinderReturn() {
    const klass = findClassAnywhere("IdunBattle.Entities.Pathfinding", "Pathfinders");
    if (!klass) return;
    const it = Memory.alloc(Process.pointerSize);
    it.writePointer(ptr(0));
    let m: NativePointer;
    while (!(m = class_get_methods(klass, it) as NativePointer).isNull()) {
        const mname = s(method_get_name(m) as NativePointer);
        if (mname === "FindReachableTiles") {
            const rt = method_get_return_type(m) as NativePointer;
            const rname = s(type_get_name(rt) as NativePointer);
            console.log(`[dump] Method ${mname} return type: ${rname}`);
        }
    }
}
