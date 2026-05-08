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
import { pushApply, popApply, StreamEvent } from "./apply-stack.js";
import {
    getReplayMi, replayOff, runnerApplyMi, runnerOff,
} from "./runner.js";
import { state, LogEntry, MirrorTurnMsg } from "./state.js";
import { applyToMirror } from "../features/sim-engine.js";

// Per-onEnter marker stored on `this` inside the interceptor callback
// so onLeave knows whether it pushed a frame and should pop.
// `_ours` = normal live recording path. `_mirrorCapture` = "AI plays on
// mirror" Phase 1 path: we pushed a frame, the message is in mirrorTurnQueue,
// onLeave should pop. The two are mutually exclusive.
type MarkerThis = InvocationContext & {
    _ours?: boolean;
    _mirrorCapture?: boolean;
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
    if (!state.runnerInstance || !runnerApplyMi) return false;
    const liveRunner = state.runnerInstance;
    state.realAiControl = liveRunner.add(runnerOff.aiControl).readPointer();
    if (state.realAiControl.isNull()) return false;
    gcRoot.init();

    const runnerSnapshot = liveRunner;
    const aiSnapshot = state.realAiControl;

    // Resolve MT once from the live runner to seed our snapshot per entry
    const mtStart = runnerSnapshot.add(runnerOff.rng).readPointer();
    const mt = resolveMt(mtStart);

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
            if (!args[0].equals(runnerSnapshot)) {
                this._ours = false;
                logFilterMismatch("runner.Apply",
                    args[0].toString(), runnerSnapshot.toString());
                return;
            }
            this._ours = true;
            try {
                const msg = args[1];
                gcRoot.add(msg);
                const entry: LogEntry = {
                    idx: state.counter++,
                    src: "top",
                    cls: readMsgClass(msg),
                    ptr: msg.toString(),
                    unitId: null,
                    prng: mt ? snapshotMt(mt) : null,
                    ts: Date.now(),
                    events: [],
                    runner: "live",
                };
                state.log.push(entry);
                pushApply("live", entry.events);
            } catch { /* best effort */ }
        },
        onLeave(this: MarkerThis) {
            if (this._mirrorCapture) {
                try { popApply(); } catch { /* ignore */ }
                return;
            }
            if (!this._ours) return;
            try { popApply(); } catch { /* ignore */ }
            // Auto-mirror: replay any new live entries on the mirror.
            try { applyToMirror(); } catch { /* best effort */ }
        },
    }));

    function attachAi(mi: { ptr: NativePointer } | null, tag: "ai" | "humanAi"): void {
        if (!mi || mi.ptr.isNull()) return;
        state.installedListeners.push(Interceptor.attach(mi.ptr, {
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
                if (!args[0].equals(aiSnapshot)) {
                    this._ours = false;
                    logFilterMismatch("aiControl." + tag,
                        args[0].toString(), aiSnapshot.toString());
                    return;
                }
                this._ours = true;
                try {
                    const msg = args[1];
                    gcRoot.add(msg);
                    let uid: number | null = null;
                    // MoveUnitMessage.UnitId @16 and ActiveAbilityMessage.CasterId @16 match
                    try { uid = msg.add(16).readS32(); } catch { /* ignore */ }
                    const entry: LogEntry = {
                        idx: state.counter++,
                        src: tag,
                        cls: readMsgClass(msg),
                        ptr: msg.toString(),
                        unitId: uid,
                        prng: mt ? snapshotMt(mt) : null,
                        ts: Date.now(),
                        events: [],
                        runner: "live",
                    };
                    state.log.push(entry);
                    pushApply("live", entry.events);
                } catch { /* best effort */ }
            },
            onLeave(this: MarkerThis) {
                if (this._mirrorCapture) {
                    try { popApply(); } catch { /* ignore */ }
                    return;
                }
                if (!this._ours) return;
                try { popApply(); } catch { /* ignore */ }
                try { applyToMirror(); } catch { /* best effort */ }
            },
        }));
    }
    attachAi(applyAiMsgMi, "ai");
    attachAi(applyHumanAiMsgMi, "humanAi");
    Interceptor.flush();

    // Bootstrap preamble from native ReplayRecorder._replay.Messages
    let bootCount = 0, bootSkipped = 0;
    try {
        const recorder = runnerSnapshot.add(runnerOff.replayRecorder).readPointer();
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
        runner: runnerSnapshot.toString(),
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
    if (state.runnerInstance && state.installedListeners.length === 0) {
        try { install(); } catch { /* best effort */ }
    }
    return state.installedListeners.length > 0;
}

export { detachAll };
