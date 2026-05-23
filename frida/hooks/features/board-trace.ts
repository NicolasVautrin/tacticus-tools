// boardTrace — hook BoardConfiguration..ctor to capture each board
// instantiation + call stack. Reveals where boards are loaded from and
// who stores them in memory (which we need to enumerate the catalog).
//
// RPCs:
//   boardTraceStart()  → arm the hook, returns {ok}
//   boardTraceStop()   → disarm + return collected entries
//   boardTraceStatus() → entries collected so far

import {
    findClassAnywhere, findCtorByParamCount, readIl2cppString,
} from "../il2cpp/helpers.js";
import { queueOnMainThread } from "../runtime/queue.js";
import { Ctx } from "../controller.js";

interface CtorEntry {
    ptr: string;
    idAfter: string | null;   // read 100ms after ctor — null if not set
    stack: string;            // backtrace
    ts: number;
}

let entries: CtorEntry[] = [];
let listener: InvocationListener | null = null;

const BOARD_OFF_ID = 0x18;

function startTrace(): { ok: boolean; err?: string } {
    if (listener) return { ok: false, err: "already armed" };

    const boardClass = findClassAnywhere(
        "IdunBattle.Configuration", "BoardConfiguration");
    if (!boardClass) return { ok: false, err: "BoardConfiguration class not found" };

    // BoardConfiguration is a ScriptableObject — it gets parameterless ctor.
    const ctor = findCtorByParamCount(boardClass, 0);
    if (!ctor) return { ok: false, err: "BoardConfiguration 0-arg ctor not found" };

    entries = [];
    listener = Interceptor.attach(ctor.ptr, {
        onEnter(args) {
            this.self = args[0];
        },
        onLeave() {
            const self = this.self as NativePointer;
            const stack = Thread.backtrace(this.context, Backtracer.ACCURATE)
                .map((p) => p.toString())
                .slice(0, 20)
                .join(" | ");
            entries.push({
                ptr: self.toString(),
                idAfter: null,  // read later via getter
                stack,
                ts: Date.now(),
            });
        },
    });
    return { ok: true };
}

function stopTrace(): { ok: boolean; entries: CtorEntry[] } {
    if (listener) {
        listener.detach();
        listener = null;
    }
    // Resolve ids now — they're usually set after Awake/Init
    for (const e of entries) {
        try {
            const p = ptr(e.ptr).add(BOARD_OFF_ID).readPointer();
            e.idAfter = readIl2cppString(p);
        } catch { /* leave null */ }
    }
    return { ok: true, entries };
}

function statusTrace(): { armed: boolean; count: number } {
    return { armed: listener !== null, count: entries.length };
}

export function register(ctx: Ctx): void {
    ctx.rpc.boardTraceStart = () => queueOnMainThread(startTrace);
    ctx.rpc.boardTraceStop = () => queueOnMainThread(stopTrace);
    ctx.rpc.boardTraceStatus = () => queueOnMainThread(statusTrace);
}
