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
import { purgeTracesForRunner } from "./trace-origin.js";

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

/** Hard cap on CONCURRENT managed runners. Replaces the old single-build
 *  dispose-all default of `initAndStart` (which silently nuked in-flight
 *  parallel runners — TF06) as the guard on the gcRoot handle budget
 *  (~100 pinned handles per battle; Initialize fails past ~900, see header).
 *  Past the cap, build RPCs REFUSE explicitly — callers own their runners
 *  and must dispose them at end of pass. */
export const MAX_RUNNERS = 10;

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
    // PAS de side effect trace-origin ici : getRunner est aussi appelé
    // depuis des callbacks de hooks (recorder) et des RPCs non-queués
    // (disposeRunner, thread RPC) — un set ambiant taignerait l'attribution.
    // L'origine est posée EXPLICITEMENT par les RPCs de pilotage
    // (cf. game/trace-origin.ts).
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
    // Drop les buckets de traces diagnostiques du runner mort (scorer /
    // aiUtilityTrace / bucketAudit) — même hygiène que purgeLogForOrigin
    // côté recorder. cf. game/trace-origin.ts.
    try { purgeTracesForRunner(runnerId); } catch { /* best effort */ }
    return byId.delete(runnerId);
}
