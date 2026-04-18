// cheatRunAi — fire CheatRunAIMessage directly on the live runner.
//
// Fallback path when you want to let the game's own AI play the current
// turn on live (e.g. to finish a battle quickly, or to debug). Normal
// workflow is `simAndCommit` which isolates the AI decision in a
// standalone runner first.

import { createObject, invokeMethod } from "../il2cpp/invoke.js";
import { gcRoot } from "../il2cpp/gc-root.js";
import { cheatRunAiClass } from "../game/ai-control.js";
import { runnerApplyMi } from "../game/runner.js";
import { state } from "../game/state.js";
import { queueOnMainThread } from "../runtime/queue.js";
import { Ctx } from "../controller.js";

export function register(ctx: Ctx): void {
    ctx.rpc.cheatRunAi = () => queueOnMainThread(() => {
        if (!state.runnerInstance) throw new Error("no runner");
        if (!cheatRunAiClass) throw new Error("CheatRunAIMessage class not found");
        const msg = createObject(cheatRunAiClass);
        gcRoot.add(msg);
        const before = state.log.length;
        invokeMethod(runnerApplyMi!.info, state.runnerInstance, [msg]);
        return {
            ok: true,
            before,
            after: state.log.length,
            delta: state.log.length - before,
        };
    });
}
