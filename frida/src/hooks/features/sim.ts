// Simulation RPCs: sim → commit (or simAndCommit as a single step).
//
// `sim`:
//   1. Build standalone runner via buildStandaloneRunner() — fresh isolated
//      IdunRunner with same config + seed as live.
//   2. Catch up standalone by dispatching our captured log via runner.Apply
//      (skips CheatRunAIMessage — its sub-messages are already in the log).
//   3. Install temp capture interceptors on inner AiControl, fire CheatRunAI
//      on standalone. Its AI emits MoveUnit/ActiveAbility/... sub-messages
//      we capture. The live runner is NOT touched.
//   4. Stash captured messages under `simId` in state.simCache — their
//      pointers are in gcRoot so they stay alive.
//
// `commit(simId)`:
//   Apply each stashed message on the real AiControl via ApplyAiMessage /
//   ApplyHumanAiMessage — live runner moves for real.
//
// Decoupling sim from commit enables later: multiple sims with different
// params → compare → commit the best.

import { invokeMethod, createObject } from "../il2cpp/invoke.js";
import { gcRoot } from "../il2cpp/gc-root.js";
import { readMsgClass } from "../il2cpp/helpers.js";
import {
    buildStandaloneRunner, runnerApplyMi, runnerOff,
} from "../game/runner.js";
import {
    applyAiMsgMi, applyHumanAiMsgMi, cheatRunAiClass,
} from "../game/ai-control.js";
import { EntityType, msEntitiesOff } from "../game/match-state.js";
import { state } from "../game/state.js";
import { ensureInstalled } from "../game/recorder.js";
import { queueOnMainThread } from "../runtime/queue.js";
import { Ctx } from "../controller.js";

interface Timing {
    step?: string;
    ms?: number;
    [k: string]: unknown;
}

function readStage(liveRunner: NativePointer): number | null {
    const mstate = liveRunner.add(runnerOff.state).readPointer();
    if (mstate.isNull()) return null;
    const list = mstate.add(msEntitiesOff).readPointer();
    const size = list.add(0x18).readS32();
    const items = list.add(0x10).readPointer();
    for (let i = 0; i < size; i++) {
        const e = items.add(0x20 + i * 8).readPointer();
        if (e.isNull()) continue;
        if (e.add(20).readS32() === EntityType.Match) {
            const mc = e.add(32).readPointer();
            if (!mc.isNull()) return mc.add(36).readS32();
            return null;
        }
    }
    return null;
}

function runSim(): unknown {
    ensureInstalled();
    if (!state.runnerInstance) throw new Error("no runner");
    const liveRunner = state.runnerInstance;
    const timings: Timing[] = [];
    const T0 = Date.now();

    // Battle must be Running
    const stage = readStage(liveRunner);
    if (stage !== 1) return { error: "battle not Running", stage };

    // Build standalone
    let built;
    let t = Date.now();
    try { built = buildStandaloneRunner(liveRunner); }
    catch (e) { return { error: "buildStandaloneRunner failed",
                         detail: (e as Error).message }; }
    timings.push({ step: "buildStandaloneRunner", ms: Date.now() - t,
                   seed: built.seed });

    // Catch up via log — skip CheatRunAIMessage (trigger only)
    t = Date.now();
    const catchUp = {
        top: 0, top_boot: 0, ai: 0, humanAi: 0,
        skippedCheatRunAi: 0, errors: [] as unknown[],
    };
    for (let i = 0; i < state.log.length; i++) {
        const e = state.log[i];
        const msgPtr = ptr(e.ptr);
        if ((e.src === "top" || e.src === "top_boot") && e.cls === "CheatRunAIMessage") {
            catchUp.skippedCheatRunAi++;
            continue;
        }
        try {
            invokeMethod(runnerApplyMi!.info, built.standalone, [msgPtr]);
            catchUp[e.src]++;
        } catch (ex) {
            catchUp.errors.push({
                i, src: e.src, cls: e.cls,
                err: (ex as Error).message,
            });
            if (catchUp.errors.length >= 3) break;
        }
    }
    timings.push({ step: "catch up via log", ms: Date.now() - t, catchUp });
    if (catchUp.errors.length > 0) {
        return { error: "catch up failed", timings };
    }

    // Capture inner AiControl decisions
    const captured: Array<{ src: "ai" | "humanAi"; cls: string; ptr: string }> = [];
    const listeners: InvocationListener[] = [];
    function attachCap(mi: { ptr: NativePointer } | null, tag: "ai" | "humanAi"): void {
        if (!mi || mi.ptr.isNull()) return;
        listeners.push(Interceptor.attach(mi.ptr, {
            onEnter(args) {
                if (!args[0].equals(built!.innerAiControl)) return;
                try {
                    const m = args[1];
                    gcRoot.add(m);
                    captured.push({
                        src: tag, cls: readMsgClass(m), ptr: m.toString(),
                    });
                } catch { /* best effort */ }
            },
        }));
    }
    attachCap(applyAiMsgMi, "ai");
    attachCap(applyHumanAiMsgMi, "humanAi");
    Interceptor.flush();

    // Fire CheatRunAI on standalone
    t = Date.now();
    const cheatMsg = createObject(cheatRunAiClass!);
    gcRoot.add(cheatMsg);
    let cheatErr: string | null = null;
    try { invokeMethod(runnerApplyMi!.info, built.standalone, [cheatMsg]); }
    catch (e) { cheatErr = (e as Error).message; }
    for (const l of listeners) l.detach();
    timings.push({
        step: "CheatRunAI(standalone)", ms: Date.now() - t,
        err: cheatErr, capturedCount: captured.length,
    });
    if (cheatErr) return {
        error: "standalone CheatRunAI failed", detail: cheatErr, timings,
    };

    // Stash under simId
    const simId = state.simIdSeq++;
    state.simCache[simId] = { captured, ts: Date.now() };
    timings.push({ total_ms: Date.now() - T0 });

    return {
        ok: true,
        simId,
        captured: captured.map((c) => ({ src: c.src, cls: c.cls })),
        timings,
    };
}

function runCommit(simId: number): unknown {
    if (!state.runnerInstance) throw new Error("no runner");
    const entry = state.simCache[simId];
    if (!entry) return { error: "simId not found", simId };
    const captured = entry.captured;
    const realAiControl = state.runnerInstance.add(runnerOff.aiControl).readPointer();
    const t = Date.now();
    let applied = 0;
    const errors: unknown[] = [];
    for (let ci = 0; ci < captured.length; ci++) {
        const c = captured[ci];
        const target = c.src === "humanAi" ? applyHumanAiMsgMi : applyAiMsgMi;
        try {
            invokeMethod(target!.info, realAiControl, [ptr(c.ptr)]);
            applied++;
        } catch (e) {
            errors.push({ i: ci, cls: c.cls, err: (e as Error).message });
        }
    }
    delete state.simCache[simId];
    return {
        ok: errors.length === 0,
        simId, applied, errors, ms: Date.now() - t,
    };
}

export function register(ctx: Ctx): void {
    ctx.rpc.sim = () => queueOnMainThread(runSim);
    ctx.rpc.commit = (simId: number) => queueOnMainThread(() => runCommit(simId));
    ctx.rpc.simAndCommit = () => queueOnMainThread(() => {
        const simRes = runSim() as { ok?: boolean; simId?: number;
                                      captured?: unknown; timings?: Timing[] };
        if (!simRes.ok || simRes.simId === undefined) return simRes;
        const commitRes = runCommit(simRes.simId) as {
            ok?: boolean; applied?: number; errors?: unknown[]; ms?: number;
        };
        return {
            ok: commitRes.ok,
            simId: simRes.simId,
            captured: simRes.captured,
            applied: commitRes.applied,
            errors: commitRes.errors,
            timings: [...(simRes.timings ?? []), {
                step: "commit on live",
                ms: commitRes.ms,
                applied: commitRes.applied,
                errors: (commitRes.errors ?? []).length,
            }],
        };
    });
}
