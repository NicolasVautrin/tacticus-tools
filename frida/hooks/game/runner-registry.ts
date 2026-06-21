// Registry of IdunRunner instances we built ourselves (Phase 3 launches).
// Keyed by an auto-increment runnerId that the host uses to address subsequent
// actions (apply, startMatch, query, dispose) on a specific runner.
//
// Wording: "runner" by default means one of our managed runners in this
// registry. The game's own runner instance (created when the user enters a
// real battle) is explicitly called "liveRunner" (see game/state.ts).
//
// Pinned-refs tracking: every transient IL2CPP allocation we keep alive
// across an in-progress runner cycle (BC config, AddUnit/StartBattle/
// CheatRunAI messages, …) is registered against the owning runner via
// `pinForRunner`. `disposeRunner` then unpins all of them in one shot,
// preventing gcRoot from accumulating ~100 pinned handles per battle
// (which has been empirically shown to make `IdunRunner.Initialize`
// fail with a native "system error" past ~900 pinned entries).

import { RunnerHandle } from "./runner.js";
import { gcRoot } from "../il2cpp/gc-root.js";

interface Entry extends RunnerHandle {
    runnerId: number;
    started: boolean;
    /** When false, recorder.ts must NOT auto-evict this runner on its
     *  match-end heuristic — it is lifecycle-managed by its driver (explicit
     *  `disposeRunner`). Set for RL/isolated runners (initRunner / initAndStart
     *  / buildPatchedRunner) so a CONCURRENT build can't evict a sibling runner
     *  mid-use (TF06). UI / mirror-replay runners keep the default (true). */
    autoDispose: boolean;
    /** Pointers added via `pinForRunner` — all unpinned by `disposeRunner`. */
    pinnedRefs: NativePointer[];
}

const byId = new Map<number, Entry>();
let counter = 0;

export function registerRunner(
    h: RunnerHandle, opts?: { autoDispose?: boolean },
): Entry {
    const e: Entry = { ...h, runnerId: ++counter, started: false,
                       autoDispose: opts?.autoDispose !== false, pinnedRefs: [] };
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

/** Pin a transient managed object against IL2CPP GC and register it as
 *  owned by `runnerId`. `disposeRunner(runnerId)` will unpin it. Caller
 *  must not pass the runner pointer itself — that's pinned + unpinned
 *  separately via the registry life-cycle. */
export function pinForRunner(runnerId: number, ptr: NativePointer): void {
    if (ptr.isNull()) return;
    const e = byId.get(runnerId);
    if (!e) {
        // Runner gone — pin globally (won't leak much since no further
        // resources will be attached). Better than swallowing silently.
        gcRoot.add(ptr);
        return;
    }
    gcRoot.add(ptr);
    e.pinnedRefs.push(ptr);
}

/** Un-pin the runner + every transient managed object registered against
 *  it, then remove from registry. */
export function disposeRunner(runnerId: number): boolean {
    const e = byId.get(runnerId);
    if (!e) return false;
    try { gcRoot.remove(e.runner); } catch { /* best effort */ }
    for (const p of e.pinnedRefs) {
        try { gcRoot.remove(p); } catch { /* best effort */ }
    }
    e.pinnedRefs.length = 0;
    return byId.delete(runnerId);
}
