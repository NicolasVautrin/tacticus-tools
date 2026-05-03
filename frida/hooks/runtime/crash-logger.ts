// Global native-exception handler.
//
// Installs `Process.setExceptionHandler` to catch access violations that
// bubble up from managed code (e.g. a stale pointer deref inside an IL2CPP
// method). The handler logs CPU context + a GameAssembly-rooted backtrace,
// then returns `false` so the OS proceeds to terminate the process
// normally — we just want diagnostic info in the host log before the crash.

import { il2cppBase, il2cppSize } from "../il2cpp/helpers.js";
import { log } from "./diag.js";

let installed = false;

/** Up to 20 return addresses resolved to GameAssembly offsets (hex). */
function backtraceOffsets(ctx: CpuContext): string[] {
    try {
        const bt = Thread.backtrace(ctx, Backtracer.ACCURATE);
        const out: string[] = [];
        for (let i = 0; i < Math.min(bt.length, 20); i++) {
            const addr = bt[i];
            const off = addr.sub(il2cppBase);
            const inLib = off.compare(0) >= 0 && off.compare(il2cppSize) < 0;
            if (inLib) {
                out.push("GameAssembly+0x" + off.toString(16));
            } else {
                // Resolve via Frida's native symbol table (libc, linker, etc.)
                let label = addr.toString();
                try {
                    const sym = DebugSymbol.fromAddress(addr);
                    if (sym.name) label = sym.moduleName + "!" + sym.name;
                    else if (sym.moduleName) label = sym.moduleName + "+" + addr.toString();
                } catch { /* best effort */ }
                out.push(label);
            }
        }
        return out;
    } catch (e) {
        return ["<backtrace failed: " + (e as Error).message + ">"];
    }
}

/** x86-64 snapshot: general-purpose regs + frame/stack/instruction pointers. */
function regDump(ctx: CpuContext): Record<string, string> {
    const a = ctx as any;  // Ia32/X64CpuContext fields are string-indexable
    const out: Record<string, string> = {};
    const keys = ["rax", "rbx", "rcx", "rdx", "rsi", "rdi", "rbp", "rsp", "rip",
                  "r8", "r9", "r10", "r11", "r12", "r13", "r14", "r15"];
    for (const k of keys) {
        try {
            const v = a[k];
            if (v) out[k] = (v as NativePointer).toString();
        } catch { /* skip */ }
    }
    return out;
}

export function installCrashLogger(): void {
    if (installed) return;
    installed = true;
    Process.setExceptionHandler((details) => {
        const ctx = details.context;
        const pc = (ctx as any).rip as NativePointer | undefined;
        const pcOff = pc ? pc.sub(il2cppBase) : null;
        const pcInLib = pcOff && pcOff.compare(0) >= 0 && pcOff.compare(il2cppSize) < 0;

        const payload = {
            t: "native_exception",
            type: details.type,
            address: details.address.toString(),
            memory: details.memory
                ? { op: details.memory.operation, addr: details.memory.address.toString() }
                : null,
            pc: pc ? pc.toString() : null,
            pcOffset: pcInLib ? "GameAssembly+0x" + pcOff!.toString(16) : null,
            regs: regDump(ctx),
            stack: backtraceOffsets(ctx),
        };
        try { send(payload); } catch { /* best effort */ }
        try {
            log("[!] native_exception " + details.type
                + " at " + details.address
                + (payload.pcOffset ? " pc=" + payload.pcOffset : "")
                + (payload.memory ? " op=" + payload.memory.op
                    + " fault=" + payload.memory.addr : ""));
            for (const f of payload.stack) log("    " + f);
        } catch { /* best effort */ }
        // Let the OS kill the process — we just wanted a diagnostic log.
        return false;
    });
    log("[*] crash-logger installed");
}
