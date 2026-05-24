// init-trace — narrow diagnostic for `IdunRunner.Initialize` crashes
// that propagate up as Frida "system error" (no managed exception
// reaches `il2cpp_runtime_invoke`'s out-param, so our `invokeMethod`
// can't decode them).
//
// Two layers :
//   - Hook `IdunRunner.Initialize` entry/leave → emit `init_enter`
//     / `init_leave` with gcRoot pinned-count + runner registry size,
//     so we can correlate "fail after N battles" with growth metrics.
//   - Hook `System.Exception..ctor` (all subclass ctors chain into it)
//     → emit `exception_ctor` with class name + message. Captures EVERY
//     managed exception created, even ones caught silently by the
//     engine. Once we see one fire inside an Initialize window, we
//     have the actual C# error that triggered the crash.
//
// Both emit to the shared ai-trace JSONL via the `emit` helper.
// `System.Exception..ctor` is **very** hot — fires thousands of times
// during normal play (try/catch in user code constructs ones that get
// caught immediately). We gate per-tick output by a flag set when we
// enter Initialize, and unset on leave, so the trace is bounded to the
// crash window.

import { emit } from "./ai-trace/state.js";
import { initializeSeedMi } from "../game/runner.js";
import {
    findClass, findClassAnywhere, class_get_name, s as cstr,
    methodEntry, findMethod,
} from "../il2cpp/helpers.js";
import { gcRoot } from "../il2cpp/gc-root.js";
import { listRunners } from "../game/runner-registry.js";
import { Ctx } from "../controller.js";

let installed = false;
let insideInitialize = 0; // re-entrant counter (Initialize can recurse)
let initEnterCount = 0;
let exceptionCount = 0;

// Lazy-resolved offsets for System.Exception._message (filled on first
// exception ctor hit).
let _excMessageOff = -1;
let _excFieldsResolved = false;

function _resolveExceptionFields(): void {
    if (_excFieldsResolved) return;
    _excFieldsResolved = true;
    try {
        // We don't have direct field-iter convenience here; reuse the
        // same field offsets as `invokeMethod`'s decoder. Cheap path:
        // try a few common offsets used by Unity 6 IL2CPP.
        // Real lookup happens on first decode attempt below.
    } catch { /* ignore */ }
}

function _readManagedString(strPtr: NativePointer): string | null {
    if (strPtr.isNull()) return null;
    try {
        const len = strPtr.add(0x10).readS32();
        if (len <= 0 || len > 100000) return null;
        return strPtr.add(0x14).readUtf16String(len);
    } catch { return null; }
}

function _safeKlassName(p: NativePointer): string {
    try {
        if (p.isNull()) return "?";
        return cstr(class_get_name(p) as NativePointer);
    } catch { return "?"; }
}

let exceptionCtorHookInstalled = false;

function installInitializeHook(): boolean {
    if (!initializeSeedMi) return false;
    Interceptor.attach(initializeSeedMi.ptr, {
        onEnter(args) {
            insideInitialize++;
            initEnterCount++;
            // Auto-arm the System.Exception..ctor hook the first time
            // we enter an Initialize, so any C# exception constructed
            // during the fail-#10 crash window is captured with class
            // name + message. Cheap: the hook itself is no-op outside
            // Initialize windows (gated by insideInitialize > 0). Wrap
            // in try/catch since nested Interceptor.attach from inside
            // an onEnter handler is delicate.
            if (!exceptionCtorHookInstalled) {
                try {
                    exceptionCtorHookInstalled = installExceptionCtorHook();
                } catch { /* keep retrying next enter */ }
            }
            try {
                emit({
                    evt: "init_enter",
                    initEnterCount,
                    insideDepth: insideInitialize,
                    runnerThis: args[0].toString(),
                    config: args[1].toString(),
                    seed: args[2].toInt32(),
                    gcRootCount: gcRoot.count(),
                    activeRunners: listRunners().length,
                });
            } catch { /* never throw */ }
        },
        onLeave(_retval) {
            insideInitialize--;
            try {
                emit({
                    evt: "init_leave",
                    initEnterCount,
                    insideDepth: insideInitialize,
                });
            } catch { /* never throw */ }
        },
    });
    return true;
}

function findExceptionCtor(): { info: NativePointer; ptr: NativePointer } | null {
    // .ctor variants: System.Exception has multiple ctors (parameterless,
    // (string), (string, Exception)). Hook the (string) overload — most
    // exception types call into it explicitly (e.g.,
    // KeyNotFoundException..ctor("…")).
    let klass = findClass("System.Private.CoreLib.dll", "System", "Exception");
    if (!klass) klass = findClass("mscorlib.dll", "System", "Exception");
    if (!klass) klass = findClassAnywhere("System", "Exception");
    if (!klass) return null;
    // Try the 1-arg (string) ctor; if not present, fall back to the
    // first .ctor we can find.
    return findMethod(klass, ".ctor");
}

function installExceptionCtorHook(): boolean {
    const ctor = findExceptionCtor();
    if (!ctor) return false;
    Interceptor.attach(ctor.ptr, {
        onEnter(args) {
            // Only log if we are inside an Initialize call — keeps the
            // trace bounded. The exception object's class lives at
            // *obj (rcx → arg0 = `this`). The (string) ctor's message
            // is arg1.
            if (insideInitialize === 0) return;
            exceptionCount++;
            try {
                const objPtr = args[0];
                const className = _safeKlassName(objPtr.readPointer());
                let message: string | null = null;
                try {
                    const msgArg = args[1];
                    if (!msgArg.isNull()) {
                        message = _readManagedString(msgArg);
                    }
                } catch { /* ignore */ }
                emit({
                    evt: "exception_ctor",
                    excNo: exceptionCount,
                    className,
                    message,
                    insideInitialize,
                });
            } catch { /* never throw */ }
        },
    });
    return true;
}

function install(): void {
    if (installed) return;
    installed = true;
    const hookedInit = installInitializeHook();
    // NOTE: the System.Exception..ctor hook is too hot to leave on at
    // startup — its Interceptor trampoline overhead × thousands of
    // caught-in-flight exceptions per second slows the heap scan 20×
    // (auto-boot timed out previously). We auto-arm it lazily on the
    // first Initialize entry instead, so the cost is paid only when
    // we actually need crash-window capture.
    try {
        emit({
            evt: "init_trace", op: "installed",
            initialize_hook: hookedInit,
            exception_ctor_hook: "lazy-on-first-init",
        });
    } catch { /* ignore */ }
}

export function register(ctx: Ctx): void {
    install();
    // Opt-in RPC to arm/disarm the very-hot System.Exception..ctor hook.
    // Set on right before triggering the failing battle, off afterwards.
    ctx.rpc.armExceptionCtorHook = () => {
        installExceptionCtorHook();
        return { ok: true };
    };
    // Touch unused-import linters
    void methodEntry;
    void _resolveExceptionFields;
    void _excMessageOff;
}
