// Shared mutable state — runner instance, log, installed listeners, etc.
//
// Modules import `state` and read/mutate its fields. The recorder populates
// runnerInstance + log; features read them. Using an exported object (not
// plain `export let`) so mutations are visible across imports.

import { StreamEvent } from "./apply-stack.js";
import { MtSnapshot } from "../il2cpp/mt.js";
import { gcRoot } from "../il2cpp/gc-root.js";

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
    /** Tag identifying which watched runner emitted this entry — "live" for
     * the in-game live runner, numeric for build (launch-registered) runners.
     * Lets analysis filter the log by origin (mirror a single build's stream
     * even when multiple builds are running concurrently). Defaults to "live". */
    originRunnerId?: "live" | number;
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
    /** The in-game live runner captured by main-pump from IdunGameViews.
     * Update — single source of truth for "the live battle". Set ONLY by
     * main-pump (on runner switch detection), never by feature RPCs.
     * Gating sentinel for "Live always required": every mirror operation
     * (including on BUILD launch runners) requires this to be non-null. */
    liveRunner: null as NativePointer | null,

    /** L'`IdunGameViews` dont la pompe draine l'`Update`, et LA FRAME où elle l'a vue.
     *
     * ⚠ `liveRunner` SE PÉRIME, et ces deux champs sont ce qui permet de le SAVOIR. La pompe ne
     * remet `liveRunner` à nul qu'en VOYANT la transition `_runner -> null` ; si la vue est
     * détruite, son `Update` cesse de tirer et le verrou garde à jamais le dernier runner.
     * Mesuré le 2026-08-20 : +12 s après une retraite confirmée, `liveRunner` pointait encore
     * sur le runner mort. Un lecteur qui veut la VÉRITÉ relit `_runner` sur `gameViews`, et
     * compare `gameViewsFrame` à `frameNo` pour savoir si la pompe tourne encore. */
    gameViews: null as NativePointer | null,
    gameViewsFrame: 0,

    /** Legacy alias for `liveRunner` — kept while we migrate callers. New
     * code should read `state.liveRunner` directly. The recorder no longer
     * uses this for filtering (see watchedRunners). */
    runnerInstance: null as NativePointer | null,

    /** Set of runners the recorder watches. Each entry maps the runner's
     * pointer (stringified) to its origin tag — "live" for the in-game
     * live runner, or a numeric build runnerId for launch-built runners.
     * Populated by main-pump (live) and launch.initRunner (build); cleared
     * on runner switch / disposeRunner. The recorder filters in onEnter via
     * `watchedRunners.get(args[0].toString())` — capture if present, ignore
     * otherwise — and stamps the resulting LogEntry with `originRunnerId`. */
    watchedRunners: new Map<string, "live" | number>(),

    /** Parallel set for AiControl pointers — same shape, used by the
     * recorder's AI hooks (`ApplyAiMessage` / `ApplyHumanAiMessage`).
     * Without this, AI sub-messages dispatched on a build runner's inner
     * AiControl during e.g. CheatRunAIMessage execution would be invisible
     * to the recorder, so the build's mirror catchUp would find nothing
     * to replay and stay frozen at the build's pre-AI state. Populated
     * alongside watchedRunners (main-pump for live, launch for build),
     * cleared on the same lifecycle events. */
    watchedAiControls: new Map<string, "live" | number>(),

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

    /** Monotonic frame counter incremented by IdunGameViews.Update hook
     *  (game-mode pump) and UnityFreezeDetector.Update (menu pump).
     *  Used to confirm empirically that frames elapse between successive
     *  queueOnMainThread calls — if the counter goes up between two
     *  consecutive turns of `autoPlayRunner`, Unity ticked at least one
     *  frame in between. Stays constant inside a single pump cycle. */
    frameNo: 0,

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

    /** Preview runner — built when the user clicks a saved-config tile in
     * the archive panel. Distinct from build runners: NOT registered in
     * runner-registry, NOT in watchedRunners (so the recorder ignores any
     * Apply on it, and state.log isn't polluted), NOT shown in the runners
     * panel. Used purely to project the saved matchstate so the front can
     * render it on the central board. Replaced/disposed on every preview
     * rebuild — only one preview lives at a time. */
    previewRunner: null as NativePointer | null,

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

    /** True while the recorder is inside an `ApplyAiMessage` call on the LIVE
     * AiControl. Lets ai-utility-trace observe AI scoring during normal live
     * play (not just during simRunAiTurn replay on mirror). Set/cleared in
     * recorder.ts around the "_ours" branch of the AI hook so it stays scoped
     * to genuine live AI activity. */
    liveAiRunning: false,

    /** Player whose turn it is right now, sampled from the live MatchState's
     * TurnComponent. Updated by the recorder on each AI message hook (not on
     * every trace fire — too hot). null until first read. */
    currentTurnPlayer: null as number | null,

    /** Round number — count of turns started by the current player, read via
     * TurnComponent.GetAmountOfTurnsStartedByCurrentPlayer. Stable within a
     * single contiguous turn (matches the in-game "Turn N" UI). */
    currentTurnRound: null as number | null,

    /** Monotonic segment counter — increments every time currentTurnPlayer
     * flips. Lets the trace tag entries with a turn-segment id so analysis
     * can group all the AI scoring done within a single contiguous turn
     * (player A's first turn = 1, player B's first turn = 2, player A's
     * second turn = 3, ...). */
    turnSegment: 0,

    /** Origin tag of the runner currently inside a watched `runner.Apply`
     * call. "live" for the in-game live runner, numeric for a build runner
     * registered via launch.initRunner. null when no watched Apply is on
     * the stack. Set in `recorder.runnerApplyMi.onEnter` after filtering,
     * cleared in `onLeave`. Used by feature hooks (move-options, …) that
     * fire DURING the Apply window (e.g. AI scoring inside
     * CheatRunAIMessage) to attribute each fire to the right runner —
     * critical because `liveAiRunning` covers only live, not build
     * autoPlay scoring. */
    scoringRunnerId: null as "live" | number | null,

    /** Monotonic counter — incremented in `recorder.runnerApplyMi.onEnter`
     * for every watched Apply. Lets hooks that fire DURING the Apply
     * window stamp their events with the same `applySeq` so analysis
     * can group all fires belonging to a single Apply.
     *
     * Crucial for the future Mode A → Mode B transition:
     *  - **Mode A (current)** : one `Apply(CheatRunAIMessage)` per turn
     *    runs the AI for ALL units. Many move-options fires share the
     *    same applySeq → grouping by (applySeq, unitEntityId) recovers
     *    per-unit scoring batches.
     *  - **Mode B (RL engine drives)** : we'll dispatch one
     *    per-unit move/ability message at a time. Each Apply gets its
     *    own applySeq, so (applySeq, unitEntityId) naturally pairs to
     *    a single decision. Same join key works in both modes. */
    applySeq: 0,

    /** Last GameModeSource.LoadBattle observation — set by mode-source-capture
     * when a battle loads. Captured passively (no auto-save anymore) so the
     * user-driven `simSaveLiveConfig` can enrich the saved config with mode +
     * campaignId + locationIndex without requerying the source instance. */
    lastModeSourceMeta: null as null | {
        mode: string;
        campaignId: string | null;
        locationIndex: number | null;
        ts: number;
    },
};

// --- Dépinglage des conteneurs de messages -----------------------------------
// Le recorder ÉPINGLE chaque message managé appliqué à un runner surveillé
// (`gcRoot.add(msg)`) : sans ça, un GC déclenché PENDANT l'Apply collecterait un
// objet dont seule notre JS tient la référence -> AV. Le pin doit donc vivre
// aussi longtemps que le conteneur qui garde le pointeur.
//
// Corollaire, longtemps manqué : **vider le conteneur sans dépingler transforme
// chaque pin en handle ORPHELIN définitif** — plus aucun code ne connaît le
// pointeur, et rien ne le relâchera jamais. `purgeLogForOrigin` (sim-engine)
// faisait déjà le bon geste au dispose d'un runner ; trois autres sites vidaient
// à cru : la bascule de bataille live (main-pump), le RPC `clear` (status) et la
// file miroir (sim-engine). Ces helpers sont le geste correct, en un seul
// endroit. C'est exactement le budget de handles que le protocole #132 mesure.

/** Dépingle les messages de `entries` (best effort). Rend le nombre traité. */
export function unpinEntries(entries: Array<{ ptr?: string }>): number {
    let n = 0;
    for (const e of entries) {
        if (!e.ptr) continue;
        try { gcRoot.remove(ptr(e.ptr)); n++; } catch { /* best effort */ }
    }
    return n;
}

/** Vide `state.log` EN DÉPINGLANT ses messages. Rend le nombre dépinglé. */
export function clearLogUnpinned(): number {
    const n = unpinEntries(state.log);
    state.log = [];
    return n;
}

/** Vide `state.mirrorTurnQueue` EN DÉPINGLANT ses messages (épinglés par
 *  `recorder.captureMirrorMsg`). Rend le nombre dépinglé. */
export function clearMirrorQueueUnpinned(): number {
    const n = unpinEntries(state.mirrorTurnQueue);
    state.mirrorTurnQueue = [];
    return n;
}
