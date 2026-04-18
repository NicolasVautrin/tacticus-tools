// RPC dispatcher: aggregates feature modules.
//
// Each feature exports `register(ctx)` that attaches its handlers to
// `ctx.rpc`. Adding a feature = create src/hooks/features/foo.ts +
// import here. No changes to existing features needed.

import * as status from "./features/status.js";
import * as sim from "./features/sim.js";
import * as compare from "./features/compare.js";
import * as cheat from "./features/cheat.js";

export interface Ctx {
    rpc: Record<string, (...args: any[]) => unknown>;
}

export function wireRpc(ctx: Ctx): void {
    [status, sim, compare, cheat].forEach((f) => f.register(ctx));
}
