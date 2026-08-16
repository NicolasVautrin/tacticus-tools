// Capture-all recorder: hooks on live runner + bootstrap preamble from
// native ReplayRecorder. Drives the `state.log` array used by features.
//
// Three hooks, identity-filtered to the current live runner:
//   - runner.Apply(msg)                → src=top
//   - AiControl.ApplyAiMessage(msg)    → src=ai
//   - AiControl.ApplyHumanAiMessage    → src=humanAi
// Each onEnter pushes an `applyStack` frame so StreamDispatcher events
// fired during that Apply get attached to this entry's `events[]`.
//
// Bootstrap preamble: at install() time we pull the native Replay's
// top-level messages (StartBattle + AddUnits + earlier turns' triggers)
// and prepend them tagged src=top_boot, deduped by ptr.

import { readMsgClass } from "../il2cpp/helpers.js";
import { gcRoot } from "../il2cpp/gc-root.js";
import { invokeMethod } from "../il2cpp/invoke.js";
import { resolveMt, snapshotMt } from "../il2cpp/mt.js";
import {
    applyAiMsgMi, applyHumanAiMsgMi, dumpAiRngProbe,
} from "./ai-control.js";
import {
    pushApply, popApply, enterApply, leaveApply, StreamEvent,
    humanAiHookWanted, registerHumanAiListener,
} from "./apply-stack.js";
import {
    getReplayMi, replayOff, runnerApplyMi, runnerOff,
} from "./runner.js";
import { state, LogEntry, MirrorTurnMsg } from "./state.js";
import {
    applyToMirror, disposeMirrorIfFromBuild, purgeLogForOrigin,
} from "../features/sim-engine.js";
import {
    getRunner as getRegistryRunner, disposeRunner as disposeRegistryRunner,
} from "./runner-registry.js";
import { readBattleStatus, readTurnInfo } from "./match-state.js";
import { queueOnMainThread } from "../runtime/queue.js";

// Per-onEnter marker stored on `this` inside the interceptor callback
// so onLeave knows whether it pushed a frame and should pop.
// `_ours` = normal live recording path. `_mirrorCapture` = "AI plays on
// mirror" Phase 1 path: we pushed a frame, the message is in mirrorTurnQueue,
// onLeave should pop. The two are mutually exclusive.
type MarkerThis = InvocationContext & {
    _ours?: boolean;
    _mirrorCapture?: boolean;
    /** Cette invocation a ouvert la fenêtre `insideApply` (#596-r1) — donc c'est elle qui la
     *  referme. Distincte de `_recorderPushed`, qui ne vaut que pour `origin === "live"`. */
    _appliqueEnVol?: true;
    /** Set in onEnter for AI hooks — "live" or build runnerId; lets
     * onLeave know if live-only side-effects should fire. */
    _origin?: "live" | number;
    /** Stage of the watched runner BEFORE the apply — captured in onEnter
     * for the top-level (runner.Apply) hook so onLeave can detect a
     * Running → not-Running transition (= match-end) without firing on
     * pre-start applies. */
    _stagePre?: number | null;
};

// Throttle filter-mismatch logs — first 5 only, then summary every 100.
// Without this, a runner switch could spam thousands of messages/s.
const filterMismatchCounts: Record<string, number> = {};
function logFilterMismatch(
    where: string, gotPtr: string, expectedPtr: string,
): void {
    const key = where + ":" + gotPtr;
    const n = (filterMismatchCounts[key] ?? 0) + 1;
    filterMismatchCounts[key] = n;
    if (n <= 5 || n % 100 === 0) {
        send({
            t: "diag", msg: "[recorder] filter mismatch " + where
                + " · got=" + gotPtr + " expected=" + expectedPtr
                + " · n=" + n,
        });
    }
}

function detachAll(): void {
    for (const l of state.installedListeners) {
        try { l.detach(); } catch { /* ignore */ }
    }
    state.installedListeners = [];
}

export function install(): boolean {
    detachAll();
    if (!state.liveRunner || !runnerApplyMi) return false;
    const liveRunner = state.liveRunner;
    state.realAiControl = liveRunner.add(runnerOff.aiControl).readPointer();
    if (state.realAiControl.isNull()) return false;
    gcRoot.init();

    const aiSnapshot = state.realAiControl;
    // Mark the live AiControl as watched. Build runners' inner AiControls
    // are added by launch.ts; the recorder filter for AI hooks consults
    // watchedAiControls so build-source mirrors can also catch up on AI
    // sub-messages dispatched during CheatRunAIMessage / similar. Clear
    // any prior "live" entry first — handles a live runner switch where
    // the previous live's AiControl would otherwise linger.
    for (const [k, v] of [...state.watchedAiControls.entries()]) {
        if (v === "live") state.watchedAiControls.delete(k);
    }
    state.watchedAiControls.set(aiSnapshot.toString(), "live");

    // Resolve MT lazily, cached per watched runner ptr. With multi-watch
    // (live + N builds), each runner has its own internal `_randomNumberGenerator`
    // — we must snapshot/restore the right one or PRNG sync breaks per-source.
    const mtCache = new Map<string, ReturnType<typeof resolveMt> | null>();
    function getMt(runnerPtr: NativePointer): ReturnType<typeof resolveMt> | null {
        const key = runnerPtr.toString();
        const hit = mtCache.get(key);
        if (hit !== undefined) return hit;
        let mt: ReturnType<typeof resolveMt> | null = null;
        try {
            const start = runnerPtr.add(runnerOff.rng).readPointer();
            mt = resolveMt(start);
        } catch { /* leave null */ }
        mtCache.set(key, mt);
        return mt;
    }
    // Pre-resolved live MT — used by the AI hooks (which filter on the live
    // AiControl, so they always run with the live PRNG).
    const liveMt = getMt(liveRunner);

    /** Resolve the mirror runner's PRNG for snapshotting during Phase 1 of
     * simRunAiTurn. Resolved per-call because the mirror runner can be
     * rebuilt mid-session (its MT pointer changes). */
    function resolveMirrorMt(): ReturnType<typeof resolveMt> | null {
        if (!state.mirrorRunner) return null;
        try {
            const start = state.mirrorRunner.add(runnerOff.rng).readPointer();
            return resolveMt(start);
        } catch { return null; }
    }

    /** Capture an apply on the mirror runner during simRunAiTurn Phase 1.
     * Pushes a "mirror" apply frame so StreamDispatcher events get attached
     * to the captured msg, snapshots the mirror PRNG so we can drive live
     * RNG to the same value in Phase 2. Returns true on success. */
    function captureMirrorMsg(
        msg: NativePointer, src: "top" | "ai" | "humanAi",
    ): boolean {
        try {
            gcRoot.add(msg);
            let uid: number | null = null;
            try { uid = msg.add(16).readS32(); } catch { /* ignore */ }
            const mirrorMt = resolveMirrorMt();
            const events: StreamEvent[] = [];
            const captured: MirrorTurnMsg = {
                src,
                cls: readMsgClass(msg),
                ptr: msg.toString(),
                unitId: uid,
                prng: mirrorMt ? snapshotMt(mirrorMt) : null,
                events,
            };
            state.mirrorTurnQueue.push(captured);
            pushApply("mirror", events);
            return true;
        } catch { return false; }
    }

    state.installedListeners.push(Interceptor.attach(runnerApplyMi.ptr, {
        onEnter(this: MarkerThis, args) {
            // "AI plays on mirror" Phase 1: capture sub-messages dispatched
            // on the mirror runner; ignore any live applies we triggered
            // manually in Phase 2.
            if (state.captureMirrorMessages) {
                if (state.mirrorRunner
                    && args[0].equals(state.mirrorRunner)) {
                    this._mirrorCapture = captureMirrorMsg(args[1], "top");
                }
                this._ours = false;
                return;
            }
            // Skip if this Apply was triggered by our own mirror replay loop
            // (sim-engine.ts sets the flag while invoking on the mirror runner).
            if (state.replayingOnMirror) { this._ours = false; return; }
            // Multi-watch: capture if args[0] is a known watched runner
            // (live OR a build registered via launch.initRunner).
            const callee = args[0];
            const origin = state.watchedRunners.get(callee.toString());
            if (origin === undefined) {
                this._ours = false;
                return;
            }
            this._ours = true;
            this._origin = origin;
            // Fenêtre « un Apply est EN VOL » (#596-r1) — lue par le capteur
            // `System.Exception..ctor`, trop chaud pour tourner en permanence. Volontairement
            // découplée de `_recorderPushed` : celle-ci ne s'ouvre que pour `origin === "live"`,
            // alors qu'un message de BUILD peut lever tout autant.
            enterApply();
            this._appliqueEnVol = true;
            // Snapshot stage BEFORE the apply so onLeave can detect a
            // Running → not-Running transition (= match just ended).
            // Without this we'd fire on every apply whose stage isn't
            // Running — including AddUnits during the LOAD bundle replay
            // where stage stays at PreStart (0) until StartBattle.
            try {
                const sp = callee.add(runnerOff.state).readPointer();
                this._stagePre = !sp.isNull()
                    ? (readBattleStatus(sp).stage ?? null) : null;
            } catch { this._stagePre = null; }
            const callerMt = getMt(callee);
            try {
                const msg = args[1];
                gcRoot.add(msg);
                const entry: LogEntry = {
                    idx: state.counter++,
                    src: "top",
                    cls: readMsgClass(msg),
                    ptr: msg.toString(),
                    unitId: null,
                    prng: callerMt ? snapshotMt(callerMt) : null,
                    ts: Date.now(),
                    events: [],
                    runner: "live",
                    originRunnerId: origin,
                };
                state.log.push(entry);
                // pushApply UNIQUEMENT pour live — pour les build runners,
                // message-trace gère le push/pop avec sa propre logique
                // (au top-level seulement, évite le leak dû au recursion
                // guard Frida sur les sub-messages).
                if (origin === "live") {
                    pushApply("live", entry.events);
                    (this as MarkerThis & { _recorderPushed?: true })
                        ._recorderPushed = true;
                }
            } catch { /* best effort */ }
        },
        onLeave(this: MarkerThis) {
            if (this._mirrorCapture) {
                try { popApply(); } catch { /* ignore */ }
                return;
            }
            if (!this._ours) return;
            if ((this as MarkerThis & { _appliqueEnVol?: true })._appliqueEnVol) leaveApply();
            // Clear the scoring tag (companion to the set in onEnter).
            // NOTE: we don't push/pop a stack here — re-entrant Apply on
            // a *different* runner during scoring is unexpected; if it
            // happens we'd lose the outer tag, but that's a flag to
            // investigate, not silently mask.
            // Note : on ne touche plus scoringRunnerId ici — c'est
            // message-trace qui gère ce tag.
            // popApply seulement si on avait pushé (live origin).
            if ((this as MarkerThis & { _recorderPushed?: true })._recorderPushed) {
                try { popApply(); } catch { /* ignore */ }
            }
            // Auto-mirror: replay any new live entries on the mirror.
            try { applyToMirror(); } catch { /* best effort */ }
            // Match-end auto-cleanup for build runners. Only fires on the
            // exact Running → not-Running transition (caught via the
            // stagePre snapshot in onEnter), so the LOAD-bundle replay's
            // PreStart applies don't trigger a premature dispose.
            if (this._origin !== undefined && this._origin !== "live"
                && this._stagePre === 1) {
                const buildId = this._origin;
                try {
                    const entry = getRegistryRunner(buildId);
                    const sp = entry.runner.add(runnerOff.state).readPointer();
                    const stagePost = !sp.isNull()
                        ? (readBattleStatus(sp).stage ?? 1) : 1;
                    if (stagePost !== 1 && entry.autoDispose === false) {
                        // TF06 — persistent (RL/isolated) runner: NEVER auto-evict
                        // on the match-end heuristic. Lifecycle is driver-managed
                        // (explicit disposeRunner). Under CONCURRENT builds this
                        // fragile stagePre→stagePost transition evicted a sibling
                        // runner mid-use — exactly the failure this flag prevents.
                        send({ t: "diag",
                            msg: "[recorder] build#" + buildId + " match ended (1→"
                                + stagePost + ") — auto-dispose SKIPPED (persistent)" });
                    } else if (stagePost !== 1) {
                        send({ t: "diag",
                            msg: "[recorder] build#" + buildId
                                + " match ended (1→" + stagePost
                                + ") → schedule cleanup" });
                        queueOnMainThread(() => {
                            try { disposeMirrorIfFromBuild(buildId); }
                            catch { /* ignore */ }
                            try {
                                state.watchedRunners.delete(
                                    entry.runner.toString());
                                state.watchedAiControls.delete(
                                    entry.innerAiControl.toString());
                            } catch { /* ignore */ }
                            try { disposeRegistryRunner(buildId); }
                            catch { /* ignore */ }
                            // Drop log entries originating from this build
                            // so the buffers don't accumulate across
                            // consecutive build/load cycles. Adjusts the
                            // mirror's lastSyncedLogIdx to the new array
                            // length so positional bookkeeping stays sane.
                            let purged = 0;
                            try { purged = purgeLogForOrigin(buildId); }
                            catch { /* ignore */ }
                            send({ t: "runner_disposed", runnerId: buildId,
                                reason: "match_ended" });
                            send({ t: "diag",
                                msg: "[recorder] build#" + buildId
                                    + " disposed · log entries purged="
                                    + purged });
                            return null;
                        });
                    }
                } catch { /* registry entry already gone */ }
            }
        },
    }));

    function attachAi(
        mi: { ptr: NativePointer } | null, tag: "ai" | "humanAi",
    ): InvocationListener | null {
        if (!mi || mi.ptr.isNull()) return null;
        const listener = Interceptor.attach(mi.ptr, {
            onEnter(this: MarkerThis, args) {
                // Phase 1 of simRunAiTurn: AI sub-messages dispatched on
                // the mirror's aiControl get captured into mirrorTurnQueue.
                if (state.captureMirrorMessages) {
                    if (state.mirrorAiControl
                        && args[0].equals(state.mirrorAiControl)) {
                        this._mirrorCapture =
                            captureMirrorMsg(args[1], tag);
                    }
                    this._ours = false;
                    return;
                }
                if (state.replayingOnMirror) { this._ours = false; return; }
                // Multi-AI-control watch: capture if args[0] matches any
                // registered AiControl (live's or a build's inner one).
                // Without this, AI sub-messages dispatched on a build during
                // CheatRunAIMessage execution would be invisible — its mirror
                // would have no AI activity to replay.
                const callee = args[0];
                const origin = state.watchedAiControls.get(callee.toString());
                if (origin === undefined) {
                    this._ours = false;
                    logFilterMismatch("aiControl." + tag,
                        callee.toString(), aiSnapshot.toString());
                    return;
                }
                this._ours = true;
                this._origin = origin;
                // Flag the live-AI window for ai-utility-trace. Only the
                // pure "ai" tag — humanAi is player-assisted and doesn't
                // run the AI scoring pipeline. Live-only — build AI runs
                // shouldn't toggle the live-AI flag.
                if (tag === "ai" && origin === "live") {
                    state.liveAiRunning = true;
                    // Sample turn info from the live MatchState so the trace
                    // can tag entries with (player, round, segment). Cheap
                    // (one MatchState scan + one il2cpp invoke per AI message
                    // ≈ 10/turn). If the current player flipped vs. last
                    // sample, bump the segment counter — analysis can group
                    // all entries within a single contiguous turn window.
                    try {
                        const liveState = liveRunner
                            .add(runnerOff.state).readPointer();
                        const ti = readTurnInfo(liveState);
                        if (ti.player !== null
                            && ti.player !== state.currentTurnPlayer) {
                            state.currentTurnPlayer = ti.player;
                            state.turnSegment += 1;
                        }
                        if (ti.round !== null) state.currentTurnRound = ti.round;
                    } catch { /* best effort */ }
                }
                try {
                    const msg = args[1];
                    gcRoot.add(msg);
                    let uid: number | null = null;
                    // MoveUnitMessage.UnitId @16 and ActiveAbilityMessage.CasterId @16 match
                    try { uid = msg.add(16).readS32(); } catch { /* ignore */ }
                    // Snapshot PRNG from the runner that owns this AiControl
                    // so per-message determinism replays correctly: live
                    // origin → liveMt; build origin → its own MT (resolved
                    // via getMt on the build runner's pointer).
                    let prngMt = liveMt;
                    if (this._origin !== undefined && this._origin !== "live") {
                        // Find the build runner whose ptr matches this AiControl's owner.
                        for (const [rPtr, rOrigin]
                            of state.watchedRunners.entries()) {
                            if (rOrigin === this._origin) {
                                prngMt = getMt(ptr(rPtr));
                                break;
                            }
                        }
                    }
                    const entry: LogEntry = {
                        idx: state.counter++,
                        src: tag,
                        cls: readMsgClass(msg),
                        ptr: msg.toString(),
                        unitId: uid,
                        prng: prngMt ? snapshotMt(prngMt) : null,
                        ts: Date.now(),
                        events: [],
                        runner: "live",
                        originRunnerId: this._origin ?? "live",
                    };
                    state.log.push(entry);
                    // Live only — voir commentaire identique sur l'autre
                    // hook plus haut. Pour builds, message-trace fait le
                    // push au top-level seulement (évite leak sub-msgs).
                    if (this._origin === "live") {
                        pushApply("live", entry.events);
                        (this as MarkerThis & { _recorderPushed?: true })
                            ._recorderPushed = true;
                    }
                } catch { /* best effort */ }
            },
            onLeave(this: MarkerThis) {
                if (this._mirrorCapture) {
                    try { popApply(); } catch { /* ignore */ }
                    return;
                }
                if (!this._ours) return;
                if (tag === "ai" && this._origin === "live") {
                    state.liveAiRunning = false;
                }
                if ((this as MarkerThis & { _recorderPushed?: true })._recorderPushed) {
                    try { popApply(); } catch { /* ignore */ }
                }
                try { applyToMirror(); } catch { /* best effort */ }
            },
        });
        state.installedListeners.push(listener);
        return listener;
    }
    attachAi(applyAiMsgMi, "ai");
    // `humanAi` est DÉBRANCHABLE — contre-épreuve #596-r1, cf. l'en-tête de `apply-stack.ts`.
    // Le choix survit à un `install()` : sans ça, un changement de runner rearmerait la sonde
    // au milieu de la mesure, et on lirait le résultat de l'autre régime.
    registerHumanAiListener(
        humanAiHookWanted() ? attachAi(applyHumanAiMsgMi, "humanAi") : null);
    Interceptor.flush();

    // Bootstrap preamble from native ReplayRecorder._replay.Messages
    let bootCount = 0, bootSkipped = 0;
    try {
        const recorder = liveRunner.add(runnerOff.replayRecorder).readPointer();
        if (!recorder.isNull() && getReplayMi && !getReplayMi.ptr.isNull()) {
            const replay = invokeMethod(getReplayMi.info, recorder, null);
            if (!replay.isNull()) {
                const msgsList = replay.add(replayOff.messages).readPointer();
                if (!msgsList.isNull()) {
                    const size = msgsList.add(0x18).readS32();
                    const items = msgsList.add(0x10).readPointer();
                    const seenPtrs: Record<string, boolean> = {};
                    for (const e of state.log) seenPtrs[e.ptr] = true;
                    const boot: LogEntry[] = [];
                    for (let i = 0; i < size; i++) {
                        const step = items.add(0x20 + i * 8).readPointer();
                        if (step.isNull()) continue;
                        const turn = step.add(20).readS32();
                        const inputMsg = step.add(32).readPointer();
                        if (inputMsg.isNull()) continue;
                        const pstr = inputMsg.toString();
                        if (seenPtrs[pstr]) { bootSkipped++; continue; }
                        boot.push({
                            idx: boot.length,
                            src: "top_boot",
                            cls: readMsgClass(inputMsg),
                            ptr: pstr,
                            unitId: null,
                            prng: null,
                            ts: 0,
                            events: [],
                            turn,
                        });
                    }
                    // prepend boot, renumber live entries so idx stays sequential
                    const liveOffset = boot.length;
                    for (let j = 0; j < state.log.length; j++) {
                        state.log[j].idx = liveOffset + j;
                    }
                    state.log = boot.concat(state.log);
                    state.counter = state.log.length;
                    bootCount = boot.length;
                }
            }
        }
    } catch (e) {
        send({ t: "boot_error", err: (e as Error).message });
    }

    send({
        t: "recorder_armed",
        runner: liveRunner.toString(),
        aiControl: aiSnapshot.toString(),
        listeners: state.installedListeners.length,
        bootstrapped: bootCount,
        bootSkipped,
    });
    // One-shot RNG-field probe — runs the first time the recorder arms.
    try { dumpAiRngProbe(aiSnapshot); } catch (e) {
        send({ t: "diag", msg: "[probe] dumpAiRngProbe threw: " + (e as Error).message });
    }
    return true;
}

/** Safety net for RPCs that need a ready recorder. */
export function ensureInstalled(): boolean {
    if (state.liveRunner && state.installedListeners.length === 0) {
        try { install(); } catch { /* best effort */ }
    }
    return state.installedListeners.length > 0;
}

export { detachAll };
