// getGameConfig — dump the live runner's BattleConfiguration as JSON.
//
// The config is owned by the game's IdunRunner at a known offset; it's a
// managed .NET object serializable by Newtonsoft.Json. Consumers (e.g. the
// browser view) use this to lay out the board, units, spawn points, etc.

import { serializeToJson, isSerializerReady } from "../il2cpp/serializer.js";
import { runnerOff } from "../game/runner.js";
import { state } from "../game/state.js";
import { queueOnMainThread } from "../runtime/queue.js";
import { Ctx } from "../controller.js";

export function register(ctx: Ctx): void {
    ctx.rpc.getGameConfig = () => queueOnMainThread(() => {
        if (!state.liveRunner) throw new Error("no runner");
        if (!isSerializerReady()) throw new Error("Newtonsoft serializer not available");
        const configPtr = state.liveRunner.add(runnerOff.config).readPointer();
        if (configPtr.isNull()) throw new Error("config pointer null on live runner");
        const json = serializeToJson(configPtr);
        if (json === null) throw new Error("serializeToJson returned null");
        return json;
    });

    ctx.rpc.getMatchState = () => queueOnMainThread(() => {
        if (!state.liveRunner) throw new Error("no runner");
        if (!isSerializerReady()) throw new Error("Newtonsoft serializer not available");
        const statePtr = state.liveRunner.add(runnerOff.state).readPointer();
        if (statePtr.isNull()) return null;
        const json = serializeToJson(statePtr);
        return json;
    });
}
