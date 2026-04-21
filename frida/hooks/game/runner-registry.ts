// Registry of IdunRunner instances we built ourselves (Phase 3 launches).
// Keyed by an auto-increment runnerId that the host uses to address subsequent
// actions (apply, startMatch, query, dispose) on a specific runner.
//
// Wording: "runner" by default means one of our managed runners in this
// registry. The game's own runner instance (created when the user enters a
// real battle) is explicitly called "liveRunner" (see game/state.ts).

import { RunnerHandle } from "./runner.js";
import { gcRoot } from "../il2cpp/gc-root.js";

interface Entry extends RunnerHandle {
    runnerId: number;
    started: boolean;
}

const byId = new Map<number, Entry>();
let counter = 0;

export function registerRunner(h: RunnerHandle): Entry {
    const e: Entry = { ...h, runnerId: ++counter, started: false };
    byId.set(e.runnerId, e);
    return e;
}

export function getRunner(runnerId: number): Entry {
    const e = byId.get(runnerId);
    if (!e) throw new Error(`runner ${runnerId} not found`);
    return e;
}

export function listRunners(): Array<{
    runnerId: number; started: boolean; seed: number;
}> {
    return [...byId.values()].map((e) => ({
        runnerId: e.runnerId,
        started: e.started,
        seed: e.seed,
    }));
}

/** Un-pin the runner from the GC root ArrayList + remove from registry.
 * Only the runner itself is pinned — its logger/timeSource/reporter/config/
 * options/matchState/etc are all transitively reachable through the runner's
 * managed fields and die naturally once the runner is unreachable. */
export function disposeRunner(runnerId: number): boolean {
    const e = byId.get(runnerId);
    if (!e) return false;
    try { gcRoot.remove(e.runner); } catch { /* best effort */ }
    return byId.delete(runnerId);
}
