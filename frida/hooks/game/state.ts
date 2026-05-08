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

/** A single sub-message captured during the "AI plays on mirror" flow.
 * Snapshotted with the MIRROR's PRNG state pre-apply so we can restore the
 * live PRNG to that exact value before re-applying the same msg on live. */
export interface MirrorTurnMsg {
    src: "top" | "ai" | "humanAi";
    cls: string;
    ptr: string;
    unitId: number | null;
    /** Mirror PRNG snapshot taken right before this message was applied on
     * mirror — drives the live RNG restore in Phase 2. */
    prng: MtSnapshot | null;
    /** StreamEvents emitted by the mirror's apply, attached via the
     * apply-stack "mirror" frame the recorder pushes on capture. */
    events: StreamEvent[];
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

    /** Mirror runner pointer — set by sim-engine when the mirror is built,
     * cleared on dispose. Read by the recorder to filter captures during
     * the "AI plays on mirror" flow. */
    mirrorRunner: null as NativePointer | null,

    /** Mirror's inner AiControl pointer — companion to mirrorRunner. */
    mirrorAiControl: null as NativePointer | null,

    /** When true, the recorder enters a special mode for the "AI plays on
     * mirror" flow: it captures sub-messages dispatched on the mirror runner
     * (args[0] === mirrorRunner) into mirrorTurnQueue with a mirror-PRNG
     * snapshot, and skips ALL other recording (live messages during this
     * flow are applied manually in Phase 2 — see sim-engine.simRunAiTurn). */
    captureMirrorMessages: false,

    /** Sub-messages captured during Phase 1 of simRunAiTurn. Cleared at
     * Phase 1 start, drained at Phase 2 start. */
    mirrorTurnQueue: [] as MirrorTurnMsg[],

    /** Set by sim-engine.buildMirrorFromLive while it's calling buildRunner.
     * Used by ai-utility-trace's DefaultGroupOperator..ctor hook to identify
     * which UtilitiesDatabase belongs to the mirror (vs the live runner)
     * — we only want to inspect/tweak the mirror's. */
    buildingMirror: false,
};
