// IL2CPP object creation & managed method invocation.
// Exceptions thrown from managed code are re-thrown as JS Error with
// the managed Message + StackTrace included (resolved lazily).

import {
    class_get_name, class_get_fields, field_get_name, field_get_offset,
    findClass, findClassAnywhere, findMethod,
    IL2CPP_MODULE_NAME, MethodRef, s,
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

// Resolved lazily on the first throw — direct field reads instead of
// recursive get_Message/get_StackTrace invokes, which themselves can throw
// and silently swallow the actual error.
//
// System.Exception layout (Unity 6 / IL2CPP v39, x64):
//   header     : 0x10
//   _message   : Il2CppString*  (offset resolved at runtime, typically 0x18)
//   _stackTraceString : Il2CppString*  (offset resolved at runtime)
let _excFieldsResolved = false;
let _excMessageOff = -1;
let _excStackOff = -1;

function _ensureExceptionFields(): void {
    if (_excFieldsResolved) return;
    _excFieldsResolved = true;
    let excClass = findClass("System.Private.CoreLib.dll", "System", "Exception");
    if (!excClass) excClass = findClass("mscorlib.dll", "System", "Exception");
    if (!excClass) excClass = findClassAnywhere("System", "Exception");
    if (!excClass) return;
    const it = Memory.alloc(Process.pointerSize); it.writePointer(ptr(0));
    let f: NativePointer;
    while (!(f = class_get_fields(excClass, it) as NativePointer).isNull()) {
        const name = s(field_get_name(f) as NativePointer);
        const off = field_get_offset(f) as number;
        if (name === "_message") _excMessageOff = off;
        else if (name === "_stackTraceString") _excStackOff = off;
        if (_excMessageOff >= 0 && _excStackOff >= 0) break;
    }
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
            _ensureExceptionFields();
            if (_excMessageOff >= 0) {
                const msgPtr = excVal.add(_excMessageOff).readPointer();
                const m = _readManagedString(msgPtr);
                if (m) excMsg += ": " + m;
            }
            if (_excStackOff >= 0) {
                const stPtr = excVal.add(_excStackOff).readPointer();
                const st = _readManagedString(stPtr);
                if (st) excMsg += "\n" + st;
            }
        } catch { /* best effort, never let diagnostics crash */ }
        throw new Error(excMsg);
    }
    return result;
}

/** Invoke a managed method using the direct invoker pointer. Slower to set up but
 * avoids some overhead and can be more stable for complex signatures. */
export function invokeMethodDirect(
    methodInfo: NativePointer,
    obj: NativePointer | null,
    params: NativePointer, // void**
): NativePointer {
    const invokerPtr = methodInfo.add(8).readPointer(); // MethodInfo->invoker_method
    const methodPtr = methodInfo.readPointer();        // MethodInfo->methodPointer
    
    const invoker = new NativeFunction(invokerPtr, "pointer", ["pointer", "pointer", "pointer", "pointer"]);
    return invoker(methodPtr, methodInfo, obj ?? ptr(0), params) as NativePointer;
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
