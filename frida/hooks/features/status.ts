// Status/diagnostic RPCs — info, summary, dump, clear, battleStatus,
// forceInstall. Read-only except `clear` (wipes log) and `forceInstall`
// (re-attaches live hooks).

import { il2cppBase, il2cppSize } from "../il2cpp/helpers.js";
import { isSerializerReady } from "../il2cpp/serializer.js";
import { gcRoot } from "../il2cpp/gc-root.js";
import { state, LogEntry } from "../game/state.js";
import { runnerOff } from "../game/runner.js";
import { readBattleStatus } from "../game/match-state.js";
import { install, ensureInstalled } from "../game/recorder.js";
import { queueOnMainThread } from "../runtime/queue.js";
import { Ctx } from "../controller.js";

// Strip ArrayBuffer from prng snapshot for JSON-safe return.
function sanitizeEntry(e: LogEntry): Record<string, unknown> {
    const o: Record<string, unknown> = {
        idx: e.idx, src: e.src, cls: e.cls, ptr: e.ptr,
        unitId: e.unitId, ts: e.ts,
    };
    if (e.turn !== undefined) o.turn = e.turn;
    if (e.prng) {
        o.prng = {
            seed: e.prng.seed, count: e.prng.count,
            mti: e.prng.mti, mtLen: e.prng.mtLen,
        };
    }
    return o;
}

export function register(ctx: Ctx): void {
    ctx.rpc.ping = () => "pong";

    ctx.rpc.info = () => ({
        name: "frida",
        version: 1,
        runtime: Process.arch,
        platform: Process.platform,
        il2cppBase: il2cppBase.toString(),
        il2cppSize,
        serializerReady: isSerializerReady(),
        runner: state.runnerInstance?.toString() ?? null,
        realAiControl: state.realAiControl?.toString() ?? null,
        logSize: state.log.length,
        listeners: state.installedListeners.length,
        gcRootCount: gcRoot.listPtr() ? gcRoot.count() : null,
    });

    ctx.rpc.summary = () => queueOnMainThread(() => {
        const byKind: Record<string, number> = {
            top: 0, ai: 0, humanAi: 0, top_boot: 0,
        };
        const byCls: Record<string, number> = {};
        for (const e of state.log) {
            byKind[e.src] = (byKind[e.src] ?? 0) + 1;
            byCls[e.cls] = (byCls[e.cls] ?? 0) + 1;
        }
        return {
            total: state.log.length,
            byKind,
            byCls,
            head: state.log.slice(0, 15).map(sanitizeEntry),
            tail: state.log.slice(-10).map(sanitizeEntry),
        };
    });

    ctx.rpc.dump = () => queueOnMainThread(() => ({
        log: state.log.map(sanitizeEntry),
    }));

    ctx.rpc.clear = () => queueOnMainThread(() => {
        state.log = [];
        state.counter = 0;
        return { ok: true };
    });

    ctx.rpc.battleStatus = () => queueOnMainThread(() => {
        ensureInstalled();
        if (!state.runnerInstance) return { err: "no runner" };
        const statePtr = state.runnerInstance.add(runnerOff.state).readPointer();
        if (statePtr.isNull()) return { err: "state null" };
        return readBattleStatus(statePtr);
    });

    ctx.rpc.forceInstall = () => queueOnMainThread(() => {
        const before = state.installedListeners.length;
        const ok = install();
        return {
            ok,
            before,
            after: state.installedListeners.length,
            runner: state.runnerInstance?.toString() ?? null,
            aiControl: state.realAiControl?.toString() ?? null,
            logSize: state.log.length,
        };
    });
}
