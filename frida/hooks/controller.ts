// RPC dispatcher: aggregates feature modules.
//
// Each feature exports `register(ctx)` that attaches its handlers to
// `ctx.rpc`. Adding a feature = create hooks/features/foo.ts +
// import here. No changes to existing features needed.

import * as status from "./features/status.js";
import * as sim from "./features/sim.js";
import * as compare from "./features/compare.js";
import * as cheat from "./features/cheat.js";
import * as configIo from "./features/config-io.js";
import * as modeSourceCapture from "./features/mode-source-capture.js";
import * as launch from "./features/launch.js";
import * as unitAssetMap from "./features/unit-asset-map.js";
import * as movementTrace from "./features/movement-trace.js";
import * as unitVisualResolve from "./features/unit-visual-resolve.js";
import * as introspect from "./features/introspect.js";
import * as campaignBuilder from "./features/campaign-builder.js";
import * as mowBuilder from "./features/mow-builder.js";
import * as aiTrace from "./features/ai-trace.js";
import * as simEngine from "./features/sim-engine.js";

export interface Ctx {
    rpc: Record<string, (...args: any[]) => unknown>;
}

export function wireRpc(ctx: Ctx): void {
    // movement-trace stays opt-in — its 39 Interceptor.attach hooks on
    // EvaluateMovementInSteps utilities each call 3× class_get_name and
    // produced visible navigation lag. Re-enable explicitly when AI movement
    // debugging is the active task. ai-trace L3 covers the same surface but
    // streams to disk instead of an in-memory ring; default L3=off so this
    // path stays cheap unless the user explicitly enables it.
    void movementTrace;
    [status, sim, compare, cheat, configIo, modeSourceCapture, launch,
     unitAssetMap, /* movementTrace, */ unitVisualResolve, introspect,
     campaignBuilder, mowBuilder, aiTrace, simEngine]
        .forEach((f) => f.register(ctx));
}
