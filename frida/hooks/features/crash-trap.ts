// crash-trap — diagnostic for IL2CPP failures that propagate up to Frida
// as "system error". Three layers of capture, each emitting its own event
// to the ai-trace JSONL stream:
//
//   1. Process.setExceptionHandler         → `native_crash` (SEH/access
//                                             violation level + backtrace)
//   2. Hook il2cpp_unhandled_exception     → `unhandled_exception`
//                                             (managed exception class /
//                                              message / stack — the most
//                                              informative event when the
//                                              crash is a C# throw)
//   3. Hook il2cpp_runtime_class_init      → `class_init` (last class the
//                                             runtime tried to initialize
//                                             before the crash — narrows
//                                             "which type crashed cctor")
//
// Always-on (no RPC arm step). Handlers must never throw, must always
// `emit()` best-effort; failure to log is preferable to amplifying the
// original issue.
//
// Output volume: SEH handler can fire many times per session (we saw
// 100+ "internally-handled" exceptions during a 10-battle batch). Each
// emitted record carries `crashNo` / `excNo` / `initNo` counters so the
// caller can correlate across the three streams.

import { emit } from "./ai-trace/state.js";
import { decodeManagedException } from "../il2cpp/invoke.js";
import {
    class_get_name, s as cstr, IL2CPP_MODULE_NAME,
} from "../il2cpp/helpers.js";
import { Ctx } from "../controller.js";
import { log } from "../runtime/diag.js";

function findIl2cppExport(name: string): NativePointer | null {
    const lib = Process.findModuleByName(IL2CPP_MODULE_NAME);
    if (!lib) return null;
    try {
        const p = lib.getExportByName(name);
        return p.isNull() ? null : p;
    } catch { return null; }
}

let installed = false;
let crashesSeen = 0;
let excSeen = 0;
let initSeen = 0;

// Console-log (host log) each UNIQUE native-fault site once, in RVA form so it
// can be symbolicated against data/all_game_targets_win.tsv (or ghidra-mcp) on
// the current build. The ai-trace `native_crash` emit only carries counters;
// this gives the actual fault location. Deduped by faulting RVA + capped so the
// 100+ recoverable AVs/session don't flood the log.
const _loggedFaultSites = new Set<string>();
let _faultLogCount = 0;
const FAULT_LOG_CAP = 40;
function rvaOf(addr: NativePointer, lib: { base: NativePointer; size: number } | null): string {
    try {
        if (lib && addr.compare(lib.base) >= 0
            && addr.compare(lib.base.add(lib.size)) < 0) {
            return "rva:0x" + addr.sub(lib.base).toString(16);
        }
    } catch { /* fall through */ }
    return addr.toString();
}

// Only log a small head of class_init calls per second to avoid drowning
// the trace — class init is hot (hundreds/sec under load).
const CLASS_INIT_LOG_HEAD = 8;
const CLASS_INIT_WINDOW_MS = 1000;
let _classInitBucketStart = 0;
let _classInitBucketCount = 0;

function describeBacktrace(ctx?: CpuContext): Array<{
    addr: string; mod: string | null; name: string | null;
}> {
    try {
        const bt = ctx
            ? Thread.backtrace(ctx, Backtracer.ACCURATE)
            : Thread.backtrace(undefined, Backtracer.FUZZY);
        return bt.slice(0, 24).map((addr) => {
            const ds = DebugSymbol.fromAddress(addr);
            return {
                addr: addr.toString(),
                mod: ds.moduleName ?? null,
                name: ds.name ?? null,
            };
        });
    } catch (e) {
        return [{ addr: "backtrace-failed: " + (e as Error).message,
                  mod: null, name: null }];
    }
}

function installSehHandler(): void {
    Process.setExceptionHandler((details) => {
        crashesSeen++;
        try {
            const ctx = (details as { context?: CpuContext }).context;
            const rec: Record<string, unknown> = {
                evt: "native_crash",
                kind: details.type,
                address: details.address.toString(),
                crashNo: crashesSeen,
            };
            if (details.memory) {
                rec.memory = {
                    operation: details.memory.operation,
                    address: details.memory.address.toString(),
                };
            }
            if (ctx) {
                rec.context = {
                    pc: ctx.pc?.toString() ?? null,
                    sp: ctx.sp?.toString() ?? null,
                };
            }
            rec.backtrace = describeBacktrace(ctx);
            emit(rec);
            // Console-log unique fault sites in RVA form for symbolication.
            try {
                const lib = Process.findModuleByName(IL2CPP_MODULE_NAME);
                const btRva = (ctx
                    ? Thread.backtrace(ctx, Backtracer.ACCURATE)
                    : Thread.backtrace(undefined, Backtracer.FUZZY))
                    .slice(0, 20).map((a) => rvaOf(a, lib));
                // Dedup by the first in-GameAssembly frame (the real il2cpp call
                // site), NOT the raw fault address — distinct call sites often
                // fault in the SAME shared system routine (e.g. a null-deref
                // helper), which a fault-address key would collapse into one.
                const siteKey = btRva.find((f) => f.startsWith("rva:"))
                    ?? rvaOf(details.address, lib);
                if (!_loggedFaultSites.has(siteKey)
                    && _faultLogCount < FAULT_LOG_CAP) {
                    _loggedFaultSites.add(siteKey);
                    _faultLogCount++;
                    const acc = details.memory
                        ? ` access=${details.memory.operation}@${details.memory.address}`
                        : "";
                    log(`[crash-trap] native_crash #${crashesSeen} kind=${details.type}`
                        + ` fault=${rvaOf(details.address, lib)}${acc} site=${siteKey}`
                        + ` bt=[ ${btRva.slice(0, 16).join(" ")} ]`);
                }
            } catch { /* never let the handler throw */ }
        } catch { /* never let the handler throw */ }
        // false = let it propagate. We do NOT want to swallow — the
        // upstream NativeFunction in invokeMethod must still throw so
        // autoPlayRunner can return ok:false and disposeRunner runs.
        return false;
    });
}

function installManagedExceptionHook(): boolean {
    const sym = findIl2cppExport("il2cpp_unhandled_exception");
    if (!sym || sym.isNull()) return false;
    Interceptor.attach(sym, {
        onEnter(args) {
            excSeen++;
            const excPtr = args[0];
            try {
                const decoded = decodeManagedException(excPtr);
                emit({
                    evt: "unhandled_exception",
                    excNo: excSeen,
                    className: decoded.className,
                    message: decoded.message,
                    // Stacks are huge — keep first 2KB so the JSONL stays
                    // browsable but enough frames survive for diagnosis.
                    stack: decoded.stack
                        ? decoded.stack.slice(0, 2000) : null,
                });
            } catch { /* never throw */ }
        },
    });
    return true;
}

function installClassInitHook(): boolean {
    const sym = findIl2cppExport("il2cpp_runtime_class_init");
    if (!sym || sym.isNull()) return false;
    Interceptor.attach(sym, {
        onEnter(args) {
            initSeen++;
            // Rate-limit: only emit first N per 1s window to keep volume
            // manageable. Otherwise this hook alone drowns the JSONL.
            const now = Date.now();
            if (now - _classInitBucketStart > CLASS_INIT_WINDOW_MS) {
                _classInitBucketStart = now;
                _classInitBucketCount = 0;
            }
            _classInitBucketCount++;
            if (_classInitBucketCount > CLASS_INIT_LOG_HEAD) return;
            const klass = args[0];
            let name: string | null = null;
            try {
                if (!klass.isNull()) {
                    name = cstr(class_get_name(klass) as NativePointer);
                }
            } catch { /* keep null */ }
            try {
                emit({
                    evt: "class_init",
                    initNo: initSeen,
                    klass: name,
                });
            } catch { /* never throw */ }
        },
    });
    return true;
}

// Hook kernelbase.dll!RaiseException — Windows native dispatcher used
// by the MSVC C++ runtime to throw exceptions (code 0xE06D7363 = 'msc').
// Frida's VEH intentionally ignores this code (would otherwise spam on
// every normal try/throw in C++ code), so SEH-handler hooks miss them.
//
// Volume hazard: IL2CPP uses 0xE06D7363 internally for EVERY managed
// exception propagation (NullRef, IndexOutOfRange, NotImplemented, ...).
// During amorce we saw 113 throws in 36s — Thread.backtrace overhead
// (32 frames * DebugSymbol.fromAddress) destabilised the cible.
//
// Strategy:
//   - 0xC0000005 / 0xC00000FD = always fatal, always emit + backtrace
//   - 0xE06D7363              = noisy IL2CPP managed propagation. Emit
//                               only when armed via `armCxxThrowTrap`,
//                               with strict rate limit and skip if the
//                               caller looks like il2cpp_unhandled_*.
// ⚠ Le hook qui LIT `cxxTrapArmed` (`installRaiseExceptionHook`) n'est PAS câblé —
// cf. la note de `install()`. `armCxxThrowTrap` / `disarmCxxThrowTrap` sont donc
// l'interface d'un bloc conservé pour référence, et NON une API du module : ils ont
// perdu leur `export` (#480-r7). Aucun RPC ne les expose, et il ne faut pas en poser
// un : armer un flag que personne ne lit ferait croire le piège actif.
let cxxTrapArmed = false;
const CXX_THROTTLE_HEAD = 4;
const CXX_THROTTLE_WINDOW_MS = 1000;
let _cxxBucketStart = 0;
let _cxxBucketCount = 0;
function installRaiseExceptionHook(): boolean {
    let sym: NativePointer | null = null;
    try {
        const k = Process.findModuleByName("kernelbase.dll")
            ?? Process.findModuleByName("KERNELBASE.dll");
        if (k) {
            const p = k.findExportByName("RaiseException");
            sym = p === null ? null : p;
        }
    } catch { /* ignore */ }
    if (!sym || sym.isNull()) return false;
    let throwSeen = 0;
    Interceptor.attach(sym, {
        onEnter(args) {
            const code = args[0].toUInt32() >>> 0;
            const fatal = (code === 0xC00000FD || code === 0xC0000005);
            const msvcCxx = (code === 0xE06D7363);
            if (!fatal && !msvcCxx) return;
            if (msvcCxx && !cxxTrapArmed) return;
            // Rate-limit msvc C++ even when armed.
            if (msvcCxx) {
                const now = Date.now();
                if (now - _cxxBucketStart > CXX_THROTTLE_WINDOW_MS) {
                    _cxxBucketStart = now;
                    _cxxBucketCount = 0;
                }
                _cxxBucketCount++;
                if (_cxxBucketCount > CXX_THROTTLE_HEAD) return;
            }
            throwSeen++;
            try {
                const ctx = this.context;
                const bt = Thread.backtrace(ctx, Backtracer.ACCURATE)
                    .slice(0, 32)
                    .map((addr) => {
                        const ds = DebugSymbol.fromAddress(addr);
                        return {
                            addr: addr.toString(),
                            mod: ds.moduleName ?? null,
                            name: ds.name ?? null,
                        };
                    });
                // Skip msvc throws that originate inside the IL2CPP
                // unhandled-exception path — that's the normal managed
                // exception machinery and not a useful signal.
                if (msvcCxx) {
                    const top = bt[0]?.name ?? "";
                    const sec = bt[1]?.name ?? "";
                    if (top.includes("il2cpp_unhandled_exception") ||
                        sec.includes("il2cpp_unhandled_exception")) {
                        return;
                    }
                }
                emit({
                    evt: "raise_exception",
                    code: "0x" + code.toString(16).toUpperCase(),
                    throwNo: throwSeen,
                    backtrace: bt,
                });
            } catch { /* never throw from a hook handler */ }
        },
    });
    return true;
}

// Hook OutputDebugStringW — Unity often emits its last-words error
// message via this just before a C++ throw aborts the process. Filter
// for messages that look error-related to keep volume manageable.
const ODS_KEYWORDS = ["Error", "Exception", "Assert", "Fatal",
    "throw", "crash", "abort"];
function installOutputDebugStringHook(): boolean {
    let sym: NativePointer | null = null;
    try {
        const k = Process.findModuleByName("kernelbase.dll")
            ?? Process.findModuleByName("KERNELBASE.dll");
        if (k) {
            const w = k.findExportByName("OutputDebugStringW");
            sym = w === null ? null : w;
        }
    } catch { /* ignore */ }
    if (!sym || sym.isNull()) return false;
    Interceptor.attach(sym, {
        onEnter(args) {
            try {
                const msg = args[0].readUtf16String();
                if (!msg) return;
                let match = false;
                for (const kw of ODS_KEYWORDS) {
                    if (msg.includes(kw)) { match = true; break; }
                }
                if (!match) return;
                emit({ evt: "debug_string", msg: msg.slice(0, 1024) });
            } catch { /* never throw */ }
        },
    });
    return true;
}

function armCxxThrowTrap(): void { cxxTrapArmed = true; }
function disarmCxxThrowTrap(): void { cxxTrapArmed = false; }

function install(): void {
    if (installed) return;
    installed = true;
    installSehHandler();
    const hookedExc = installManagedExceptionHook();
    // NOTE: class_init hook (installClassInitHook) N'EST PLUS auto-armé —
    // Interceptor.attach sur il2cpp_runtime_class_init = trampoline JS sur un
    // chemin ULTRA-hot au boot frais (mesuré 2026-07-20 session 50 :
    // initNo=734k en ~6 min, soit des milliers d'appels/s pendant les loads)
    // → main thread saturé → UnityFreezeDetector TUE le process. Même loi que
    // l'interdit « hook permanent sur getters hot » (CLAUDE.md) et que le
    // RaiseException hook ci-dessous. Sur un jeu chaud depuis longtemps le
    // rythme est supportable, d'où la latence du symptôme (3 morts de jeu sur
    // boots frais avant diagnostic). Ré-armable à la demande via le RPC
    // `armClassInitTrace` (diagnostic « quelle classe crashe son cctor »).
    // NOTE: RaiseException hook (installRaiseExceptionHook) was REMOVED
    // because Interceptor.attach on kernelbase!RaiseException — called
    // by EVERY IL2CPP managed exception propagation (hundreds per second
    // baseline) — destabilises Tacticus on attach, even when the onEnter
    // handler returns immediately. Function is kept in this file for
    // reference but never wired in.
    const hookedODS = installOutputDebugStringHook();
    try {
        emit({
            evt: "crash_trap", op: "installed",
            seh: true,
            unhandled_exception_hook: hookedExc,
            class_init_hook: false,
            output_debug_string_hook: hookedODS,
        });
    } catch { /* ignore */ }
}

export function register(ctx: Ctx): void {
    // Auto-arm at module register, per "debug features on by default"
    // convention — diagnostic must be active from the first hook of the
    // session, no manual RPC arm step. (Exception : class_init, cf. install()
    // — tue le jeu sur boot frais, opt-in via RPC ci-dessous.)
    install();
    ctx.rpc.armClassInitTrace = () => ({ ok: true, armed: installClassInitHook() });
}
