// IL2CPP object creation & managed method invocation.
// Exceptions thrown from managed code are re-thrown as JS Error with
// the managed Message + StackTrace included (resolved lazily).

import {
    class_get_name, findClass, findMethod, IL2CPP_MODULE_NAME, MethodRef, s,
} from "./helpers.js";

function exp(name: string): NativePointer {
    const lib = Process.findModuleByName(IL2CPP_MODULE_NAME);
    if (!lib) throw new Error(`${IL2CPP_MODULE_NAME} not loaded`);
    const p = lib.findExportByName(name);
    if (p === null) {
        throw new Error(`${IL2CPP_MODULE_NAME} export not found: ${name}`);
    }
    return p;
}

export const il2cpp_object_new = new NativeFunction(
    exp("il2cpp_object_new"), "pointer", ["pointer"]);

export const il2cpp_runtime_invoke = new NativeFunction(
    exp("il2cpp_runtime_invoke"), "pointer",
    ["pointer", "pointer", "pointer", "pointer"]);

const il2cpp_string_new = new NativeFunction(
    exp("il2cpp_string_new"), "pointer", ["pointer"]);

/** Build a managed System.String from a JS string (UTF-8 roundtrip). */
export function createManagedString(str: string): NativePointer {
    const buf = Memory.allocUtf8String(str);
    const p = il2cpp_string_new(buf) as NativePointer;
    if (p.isNull()) throw new Error("il2cpp_string_new returned null");
    return p;
}

// Resolved lazily on the first throw — avoids paying the lookup cost when
// no managed exception ever fires.
let _exceptionGetMessageMi: MethodRef | null = null;
let _exceptionGetStackMi: MethodRef | null = null;

function _ensureExceptionAccessors(): void {
    if (_exceptionGetMessageMi && _exceptionGetStackMi) return;
    const excClass = findClass("mscorlib.dll", "System", "Exception");
    if (!excClass) return;
    _exceptionGetMessageMi = findMethod(excClass, "get_Message");
    _exceptionGetStackMi = findMethod(excClass, "get_StackTrace");
}

function _readManagedString(strPtr: NativePointer): string | null {
    if (strPtr.isNull()) return null;
    try {
        const len = strPtr.add(0x10).readS32();
        if (len <= 0 || len > 100000) return null;
        return strPtr.add(0x14).readUtf16String(len);
    } catch { return null; }
}

/** Invoke a managed method. Throws with managed exception details on failure. */
export function invokeMethod(
    methodInfo: NativePointer,
    obj: NativePointer | null,
    args: NativePointer[] | null,
): NativePointer {
    const exc = Memory.alloc(Process.pointerSize);
    exc.writePointer(ptr(0));
    let params: NativePointer = ptr(0);
    if (args && args.length > 0) {
        params = Memory.alloc(args.length * Process.pointerSize);
        for (let i = 0; i < args.length; i++) {
            params.add(i * Process.pointerSize).writePointer(args[i]);
        }
    }
    const result = il2cpp_runtime_invoke(
        methodInfo, obj ?? ptr(0), params, exc) as NativePointer;
    const excVal = exc.readPointer();
    if (!excVal.isNull()) {
        let klassName = "?";
        try { klassName = s(class_get_name(excVal.readPointer()) as NativePointer); } catch { /* ignore */ }
        let excMsg = `IL2CPP exception (${klassName})`;
        try {
            _ensureExceptionAccessors();
            if (_exceptionGetMessageMi) {
                const mp = il2cpp_runtime_invoke(
                    _exceptionGetMessageMi.info, excVal, ptr(0),
                    Memory.alloc(Process.pointerSize)) as NativePointer;
                const m = _readManagedString(mp);
                if (m) excMsg += ": " + m;
            }
            if (_exceptionGetStackMi) {
                const sp = il2cpp_runtime_invoke(
                    _exceptionGetStackMi.info, excVal, ptr(0),
                    Memory.alloc(Process.pointerSize)) as NativePointer;
                const st = _readManagedString(sp);
                if (st) excMsg += "\n" + st;
            }
        } catch { /* best effort */ }
        throw new Error(excMsg);
    }
    return result;
}

/** Allocate + invoke the first parameterless ctor. For multi-ctor classes use
 * `findCtorByParamCount` + manual `invokeMethod`. */
export function createObject(klass: NativePointer): NativePointer {
    const obj = il2cpp_object_new(klass) as NativePointer;
    if (obj.isNull()) throw new Error("il2cpp_object_new returned null");
    const ctor = findMethod(klass, ".ctor");
    if (ctor) invokeMethod(ctor.info, obj, null);
    return obj;
}
