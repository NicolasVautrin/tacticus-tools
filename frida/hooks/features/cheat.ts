// cheatRunAi — fire CheatRunAIMessage directly on the live runner.
//
// Fallback path when you want to let the game's own AI play the current
// turn on live (e.g. to finish a battle quickly, or to debug). Normal
// workflow is `simAndCommit` which isolates the AI decision in a
// runner first.
//
// autoPlayRunner — loop CheatRunAIMessage on a *registered* runner (from
// runner-registry, e.g. one built via buildPatchedRunner) until the match
// reaches Finished or maxTurns is hit. The full auto-play loop for
// AI-vs-AI on an isolated runner — no live state touched.

import { createObject, il2cpp_object_new, invokeMethod } from "../il2cpp/invoke.js";
import { findCtorByParamCount } from "../il2cpp/helpers.js";
import { gcRoot } from "../il2cpp/gc-root.js";
import { cheatRunAiClass } from "../game/ai-control.js";
import { runnerApplyMi, runnerOff } from "../game/runner.js";
import { readBattleStatus, readTurnInfo } from "../game/match-state.js";
import { state } from "../game/state.js";
import { getRunner } from "../game/runner-registry.js";
import { queueOnMainThread } from "../runtime/queue.js";
import { Ctx } from "../controller.js";

const STAGE_RUNNING = 1;
const STAGE_FINISHED = 2;

export function register(ctx: Ctx): void {
    ctx.rpc.cheatRunAi = () => queueOnMainThread(() => {
        if (!state.liveRunner) throw new Error("no runner");
        if (!cheatRunAiClass) throw new Error("CheatRunAIMessage class not found");
        const msg = createObject(cheatRunAiClass);
        gcRoot.add(msg);
        const before = state.log.length;
        invokeMethod(runnerApplyMi!.info, state.liveRunner, [msg]);
        return {
            ok: true,
            before,
            after: state.log.length,
            delta: state.log.length - before,
        };
    });

    ctx.rpc.autoPlayRunner = async (args: {
        runnerId: number;
        maxTurns?: number;
    }) => {
        if (!cheatRunAiClass) {
            throw new Error("CheatRunAIMessage class not found");
        }
        if (!runnerApplyMi) {
            throw new Error("IdunRunner.Apply not resolved");
        }
        const maxTurns = args.maxTurns ?? 200;
        const ctor = findCtorByParamCount(cheatRunAiClass, 0);

        const turns: Array<{
            turn: number; player: number | null; round: number | null;
            stageBefore: number; stageAfter: number;
        }> = [];

        // Stage check (initial). One short queueOnMainThread for the
        // peek so we resolve `entry` + read battle status atomically.
        type PeekRes = { stage: number; abort?: { ok: false;
            reason: string; stage: number; turns: number } };
        const peek = await queueOnMainThread<PeekRes>(() => {
            const entry = getRunner(args.runnerId);
            let stage = -1;
            try {
                const sp0 = entry.runner.add(runnerOff.state).readPointer();
                if (!sp0.isNull()) stage = readBattleStatus(sp0).stage ?? -1;
            } catch { /* keep stage */ }
            if (stage !== STAGE_RUNNING) {
                return {
                    stage, abort: {
                        ok: false as const,
                        reason: `stage=${stage}, expected Running(1)`,
                        stage, turns: 0,
                    },
                };
            }
            return { stage };
        });
        if (peek.abort) return peek.abort;

        // One queueOnMainThread per turn — between turns the pump
        // returns from Update(), Unity ticks a frame, deferred native
        // destruction queues get drained. Empirically this fixes the
        // ~10th-Initialize failure (Microsoft C++ exception 0xE06D7363)
        // caused by Unity main-thread starvation when the whole battle
        // runs in one pump cycle.
        let turnIdx = 0;
        let finalStage = peek.stage;
        while (turnIdx < maxTurns) {
            type TurnRes = {
                done?: true;
                fail?: { ok: false; reason: string;
                    turns: number; stage: number };
                stageBefore?: number; stageAfter?: number;
                player?: number | null; round?: number | null;
                frameNo?: number;
            };
            const r = await queueOnMainThread<TurnRes>(() => {
                const entry = getRunner(args.runnerId);
                const frameNo = state.frameNo;
                const sp = entry.runner.add(runnerOff.state).readPointer();
                const sBefore = sp.isNull() ? -1
                    : (readBattleStatus(sp).stage ?? -1);
                if (sBefore !== STAGE_RUNNING) {
                    return { done: true, stageAfter: sBefore, frameNo };
                }
                const turn = readTurnInfo(sp);
                const msg = il2cpp_object_new(cheatRunAiClass!) as NativePointer;
                if (msg.isNull()) {
                    return {
                        fail: {
                            ok: false as const,
                            reason: "il2cpp_object_new returned null",
                            turns: turnIdx, stage: sBefore,
                        },
                    };
                }
                if (ctor) invokeMethod(ctor.info, msg, null);
                try {
                    invokeMethod(runnerApplyMi!.info, entry.runner, [msg]);
                } catch (e) {
                    return {
                        fail: {
                            ok: false as const,
                            reason: "Apply failed: " + (e as Error).message,
                            turns: turnIdx, stage: sBefore,
                        },
                    };
                }
                const spAfter = entry.runner.add(runnerOff.state)
                    .readPointer();
                const sAfter = spAfter.isNull() ? -1
                    : (readBattleStatus(spAfter).stage ?? -1);
                return {
                    stageBefore: sBefore, stageAfter: sAfter,
                    player: turn.player, round: turn.round,
                    frameNo,
                };
            });
            if (r.fail) return r.fail;
            if (r.done) { finalStage = r.stageAfter ?? finalStage; break; }
            turns.push({
                turn: turnIdx + 1,
                player: r.player ?? null,
                round: r.round ?? null,
                stageBefore: r.stageBefore!,
                stageAfter: r.stageAfter!,
                frameNo: r.frameNo,
            } as never);
            turnIdx++;
            finalStage = r.stageAfter!;
            if (finalStage === STAGE_FINISHED) break;
            if (finalStage !== STAGE_RUNNING) break;
        }

        return {
            ok: true,
            turns: turnIdx,
            reachedFinished: finalStage === STAGE_FINISHED,
            finalStage,
            hitMaxTurns: turnIdx >= maxTurns && finalStage !== STAGE_FINISHED,
            history: turns,
        };
    };
}
