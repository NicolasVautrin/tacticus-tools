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

    ctx.rpc.autoPlayRunner = (args: {
        runnerId: number;
        maxTurns?: number;
    }) => queueOnMainThread(() => {
        if (!cheatRunAiClass) {
            throw new Error("CheatRunAIMessage class not found");
        }
        if (!runnerApplyMi) {
            throw new Error("IdunRunner.Apply not resolved");
        }
        const entry = getRunner(args.runnerId);
        const maxTurns = args.maxTurns ?? 200;
        const ctor = findCtorByParamCount(cheatRunAiClass, 0);

        const turns: Array<{
            turn: number; player: number | null; round: number | null;
            stageBefore: number; stageAfter: number;
        }> = [];
        let stage = -1;
        try {
            const sp0 = entry.runner.add(runnerOff.state).readPointer();
            if (!sp0.isNull()) stage = readBattleStatus(sp0).stage ?? -1;
        } catch { /* keep stage */ }

        if (stage !== STAGE_RUNNING) {
            return {
                ok: false, reason: `stage=${stage}, expected Running(1)`,
                stage, turns: 0,
            };
        }

        let turnIdx = 0;
        let finalStage = stage;
        while (turnIdx < maxTurns) {
            const sp = entry.runner.add(runnerOff.state).readPointer();
            const sBefore = sp.isNull() ? -1 : (readBattleStatus(sp).stage ?? -1);
            if (sBefore !== STAGE_RUNNING) {
                finalStage = sBefore;
                break;
            }
            const turn = readTurnInfo(sp);

            const msg = il2cpp_object_new(cheatRunAiClass) as NativePointer;
            if (msg.isNull()) {
                return {
                    ok: false, reason: "il2cpp_object_new returned null",
                    turns: turnIdx, stage: sBefore,
                };
            }
            gcRoot.add(msg);
            if (ctor) invokeMethod(ctor.info, msg, null);

            try {
                invokeMethod(runnerApplyMi.info, entry.runner, [msg]);
            } catch (e) {
                return {
                    ok: false,
                    reason: "Apply failed: " + (e as Error).message,
                    turns: turnIdx, stage: sBefore,
                };
            }

            const spAfter = entry.runner.add(runnerOff.state).readPointer();
            const sAfter = spAfter.isNull()
                ? -1 : (readBattleStatus(spAfter).stage ?? -1);
            turns.push({
                turn: turnIdx + 1,
                player: turn.player,
                round: turn.round,
                stageBefore: sBefore,
                stageAfter: sAfter,
            });
            turnIdx++;
            finalStage = sAfter;
            if (sAfter === STAGE_FINISHED) break;
            if (sAfter !== STAGE_RUNNING) break;
        }

        return {
            ok: true,
            turns: turnIdx,
            reachedFinished: finalStage === STAGE_FINISHED,
            finalStage,
            hitMaxTurns: turnIdx >= maxTurns && finalStage !== STAGE_FINISHED,
            history: turns,
        };
    });
}
