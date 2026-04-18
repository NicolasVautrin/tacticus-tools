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
    applyAiMsgMi, applyHumanAiMsgMi,
} from "./ai-control.js";
import { pushApply, popApply } from "./apply-stack.js";
import {
    getReplayMi, replayOff, runnerApplyMi, runnerOff,
} from "./runner.js";
import { state, LogEntry } from "./state.js";

// Per-onEnter marker stored on `this` inside the interceptor callback
// so onLeave knows whether it pushed a frame and should pop.
type MarkerThis = InvocationContext & { _ours?: boolean };

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

    state.installedListeners.push(Interceptor.attach(runnerApplyMi.ptr, {
        onEnter(this: MarkerThis, args) {
            if (!args[0].equals(runnerSnapshot)) { this._ours = false; return; }
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
                };
                state.log.push(entry);
                pushApply("live", entry.events);
            } catch { /* best effort */ }
        },
        onLeave(this: MarkerThis) {
            if (this._ours) { try { popApply(); } catch { /* ignore */ } }
        },
    }));

    function attachAi(mi: { ptr: NativePointer } | null, tag: "ai" | "humanAi"): void {
        if (!mi || mi.ptr.isNull()) return;
        state.installedListeners.push(Interceptor.attach(mi.ptr, {
            onEnter(this: MarkerThis, args) {
                if (!args[0].equals(aiSnapshot)) { this._ours = false; return; }
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
                    };
                    state.log.push(entry);
                    pushApply("live", entry.events);
                } catch { /* best effort */ }
            },
            onLeave(this: MarkerThis) {
                if (this._ours) { try { popApply(); } catch { /* ignore */ } }
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
