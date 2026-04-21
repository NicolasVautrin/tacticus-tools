// RPC dispatcher: aggregates feature modules.
//
// Each feature exports `register(ctx)` that attaches its handlers to
// `ctx.rpc`. Adding a feature = create hooks/features/foo.ts +
// import here. No changes to existing features needed.

import * as status from "./features/status.js";
import * as sim from "./features/sim.js";
import * as compare from "./features/compare.js";
import * as cheat from "./features/cheat.js";
import * as adBypass from "./features/ad-bypass.js";
import * as configIo from "./features/config-io.js";
import * as modeSourceCapture from "./features/mode-source-capture.js";
import * as launch from "./features/launch.js";
import * as unitAssetMap from "./features/unit-asset-map.js";
import * as movementTrace from "./features/movement-trace.js";
import * as unitVisualResolve from "./features/unit-visual-resolve.js";

export interface Ctx {
    rpc: Record<string, (...args: any[]) => unknown>;
}

export function wireRpc(ctx: Ctx): void {
    [status, sim, compare, cheat, adBypass, configIo, modeSourceCapture, launch,
     unitAssetMap, movementTrace, unitVisualResolve].forEach((f) => f.register(ctx));
}
