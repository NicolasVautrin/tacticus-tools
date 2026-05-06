// Shared mutable state — runner instance, log, installed listeners, etc.
//
// Modules import `state` and read/mutate its fields. The recorder populates
// runnerInstance + log; features read them. Using an exported object (not
// plain `export let`) so mutations are visible across imports.

import { StreamEvent } from "./apply-stack.js";
import { MtSnapshot } from "../il2cpp/mt.js";

export interface LogEntry {
    idx: number;
    src: "top" | "ai" | "humanAi" | "top_boot";
    cls: string;
    ptr: string;
    unitId: number | null;
    prng: MtSnapshot | null;
    ts: number;
    events: StreamEvent[];
    turn?: number;   // set for top_boot entries from native Replay
    /** Origin runner. "live" by default; set to "mirror" if the entry was
     * observed on the mirror runner (recorder filters those out — they
     * are kept as a sentinel for re-entrancy guards only, not pushed
     * into state.log). Reserved for diagnostics, not used yet. */
    runner?: "live" | "mirror";
}

export interface SimCacheEntry {
    captured: Array<{ src: "ai" | "humanAi"; cls: string; ptr: string }>;
    ts: number;
}

export interface PendingRpc {
    fn: () => unknown;
    resolve: (value: unknown) => void;
    reject: (msg: string) => void;
}

export const state = {
    /** Live runner pointer — captured by main-pump from IdunGameViews.Update. */
    runnerInstance: null as NativePointer | null,

    /** Live AiControl pointer — cached by install(), re-read on each use
     * (runner may switch across battles). */
    realAiControl: null as NativePointer | null,

    /** All captured IInputMessages: top-level (runner.Apply) + AI sub-messages
     * (AiControl.Apply*AiMessage) + bootstrap preamble from native Replay. */
    log: [] as LogEntry[],
    counter: 0,

    /** Interceptor listeners installed by recorder.install(); detached on
     * runner switch. */
    installedListeners: [] as InvocationListener[],

    /** Queued main-thread work — drained by main-pump on each Update. */
    pending: [] as PendingRpc[],

    /** sim results stashed for later commit. */
    simCache: {} as Record<number, SimCacheEntry>,
    simIdSeq: 1,

    /** install() is deferred from the Update callback via setTimeout(0) to
     * avoid "cannot Interceptor.attach from within Interceptor.replace". */
    installNeeded: false,

    /** Set to true while sim-engine is replaying messages on the mirror
     * runner (initial catchup OR per-message auto-mirror). The recorder
     * skips its push when this is true so we don't double-record nor
     * trigger re-entrant applyToMirror calls. */
    replayingOnMirror: false,
};
