// Trace every managed exception raised in the IL2CPP runtime.
//
// Hooks `il2cpp_raise_exception` (called by the runtime at every managed
// `throw` before any try/catch handler runs). For each raised exception:
//   - read its type name, Message, and StackTrace (C# stack)
//   - log it via send() + diag log
//
// This is the most reliable way to diagnose "system error" crashes from
// `il2cpp_runtime_invoke`: Frida packages such errors generically, but the
// exception itself passes through `il2cpp_raise_exception` first — so we
// see the real cause (type + message + C# stack).
//
// Side effects: enabling this hook adds a few microseconds per managed
// throw. Tacticus throws very few exceptions per second on the happy
// path, so cost is negligible.

import {
    class_get_name, findMethod, findClass, cstr, IL2CPP_MODULE_NAME,
} from "../il2cpp/helpers.js";
import { il2cpp_runtime_invoke } from "../il2cpp/invoke.js";
import { log } from "./diag.js";

let _installed = false;

function _exp(name: string): NativePointer | null {
    const lib = Process.findModuleByName(IL2CPP_MODULE_NAME);
    if (!lib) return null;
    return lib.findExportByName(name);
}

// Read managed System.String robustly (returns null on any failure).
function _readMS(strPtr: NativePointer): string | null {
    if (!strPtr || strPtr.isNull()) return null;
    try {
        const len = strPtr.add(0x10).readS32();
        if (len < 0 || len > 100000) return null;
        return strPtr.add(0x14).readUtf16String(len);
    } catch { return null; }
}

// Lazy-resolved accessors for Exception.get_Message / get_StackTrace.
let _excGetMessage: NativePointer | null = null;
let _excGetStackTrace: NativePointer | null = null;
let _excResolved = false;

function _resolveExcAccessors(): void {
    if (_excResolved) return;
    const klass = findClass("mscorlib.dll", "System", "Exception");
    if (!klass) return;
    const m = findMethod(klass, "get_Message");
    const s = findMethod(klass, "get_StackTrace");
    if (m) _excGetMessage = m.info;
    if (s) _excGetStackTrace = s.info;
    _excResolved = true;
}

function _invokeGetter(mi: NativePointer | null, obj: NativePointer): string | null {
    if (!mi) return null;
    try {
        const exc = Memory.alloc(Process.pointerSize); exc.writePointer(ptr(0));
        const ret = il2cpp_runtime_invoke(mi, obj, ptr(0), exc) as NativePointer;
        // ignore inner exception, best-effort
        return _readMS(ret);
    } catch { return null; }
}

export function installExceptionTracer(): void {
    if (_installed) return;
    const raiseExp = _exp("il2cpp_raise_exception");
    if (!raiseExp) {
        log("[exception-tracer] il2cpp_raise_exception not exported — skipped");
        return;
    }
    Interceptor.attach(raiseExp, {
        onEnter(args) {
            const excObj = args[0] as NativePointer;
            if (!excObj || excObj.isNull()) return;
            let type = "?";
            try {
                const klass = excObj.readPointer();
                type = cstr(class_get_name(klass) as NativePointer);
            } catch { /* swallow */ }

            _resolveExcAccessors();
            const message = _invokeGetter(_excGetMessage, excObj);
            const stack = _invokeGetter(_excGetStackTrace, excObj);

            const payload = {
                t: "managed_exception",
                type, message,
                stack: stack ? stack.split("\n").slice(0, 30) : null,
            };
            try { send(payload); } catch { /* best effort */ }
            try {
                log(`[!] managed_exception ${type}` +
                    (message ? ": " + message : "") +
                    (stack ? "\n" + stack.split("\n").slice(0, 10).join("\n") : ""));
            } catch { /* best effort */ }
        },
    });
    // Hook _CxxThrowException — entry point of all native C++ throws on
    // Windows. Under modern Windows (UCRT), this lives in ucrtbase.dll, not
    // vcruntime140.dll/msvcrt.dll. IL2CPP uses this for marshalling errors
    // that don't surface as managed exceptions nor SEH.
    const vcruntime = Process.findModuleByName("ucrtbase.dll")
        ?? Process.findModuleByName("vcruntime140.dll")
        ?? Process.findModuleByName("msvcrt.dll");
    if (vcruntime) {
        const cxxThrow = vcruntime.findExportByName("_CxxThrowException");
        if (cxxThrow) {
            Interceptor.attach(cxxThrow, {
                onEnter(args) {
                    const excObj = args[0] as NativePointer;
                    const throwInfo = args[1] as NativePointer;
                    let ra = this.returnAddress;
                    const il2cppMod = Process.findModuleByName(IL2CPP_MODULE_NAME);
                    const base = il2cppMod?.base ?? ptr(0);
                    const raOff = ra.sub(base);
                    const inIl2cpp = !il2cppMod ? false :
                        raOff.compare(0) >= 0 && raOff.compare(il2cppMod.size) < 0;
                    const payload = {
                        t: "cxx_throw",
                        excObj: excObj.toString(),
                        throwInfo: throwInfo.toString(),
                        returnAddress: ra.toString(),
                        returnOffset: inIl2cpp
                            ? "GameAssembly+0x" + raOff.toString(16) : null,
                    };
                    try { send(payload); } catch { /* ignore */ }
                    try {
                        log(`[!] cxx_throw ra=${ra}` +
                            (payload.returnOffset ? " " + payload.returnOffset : ""));
                    } catch { /* ignore */ }
                },
            });
            log("[*] exception-tracer: _CxxThrowException hooked");
        } else {
            log("[exception-tracer] _CxxThrowException not exported from " + vcruntime.name);
        }
    } else {
        log("[exception-tracer] vcruntime/msvcrt not found — no native C++ hook");
    }

    // NOTE: KiUserExceptionDispatcher hook tentative was buggy (reading RCX
    // as EXCEPTION_RECORD* via this.context isn't reliable — Frida's
    // trampoline alters register state at attach time). Re-implement with
    // proper x64 ABI handling (read from [rsp] for the dispatcher's actual
    // args) if needed. Removed for now to prevent crashing Tacticus.

    _installed = true;
    log("[*] exception-tracer installed (il2cpp_raise_exception hooked)");
}
