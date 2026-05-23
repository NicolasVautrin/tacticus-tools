// Phase 3 launch — build an isolated IdunRunner from a JSON config, apply
// AddUnitMessages for each player placement, then StartMatch and stream events.
//
// RPCs:
//   initRunner({configJson})                      → {runnerId, seed}
//   applyAddUnit({runnerId, unitId, playerId, col, row}) → {events: N}
//   startBattle({runnerId})                       → {events: N}
//   snapshotState({runnerId})                     → { ok }
//   listRunners()                                 → [{runnerId, started, seed}]
//   disposeRunner({runnerId})                     → { removed }
//
// Each RPC emits `send({t:"battle_event", runnerId, msg, events})` with the
// StreamDispatcher events fired during the Apply/StartMatch call. The host
// forwards these to subscribed WebSocket clients.

import {
    findClass, findClassAnywhere, findCtorByParamCount,
} from "../il2cpp/helpers.js";
import {
    createManagedString, createObject, il2cpp_object_new, invokeMethod,
} from "../il2cpp/invoke.js";
import { gcRoot } from "../il2cpp/gc-root.js";
import {
    deserializeFromJson, isDeserializerReady,
} from "../il2cpp/serializer.js";
import { resolveMt, restoreMt, MtSnapshot } from "../il2cpp/mt.js";
import {
    buildRunner, runnerApplyMi, runnerStartMatchMi, runnerOff,
} from "../game/runner.js";
import { readBattleStatus } from "../game/match-state.js";
import { state } from "../game/state.js";
import { cheatRunAiClass } from "../game/ai-control.js";
import { purgeLogForOrigin } from "./sim-engine.js";
import {
    registerRunner, getRunner, listRunners, disposeRunner,
} from "../game/runner-registry.js";
import {
    pushApply, popApply, ensureStreamHooks, StreamEvent,
} from "../game/apply-stack.js";
import { serializeToJson } from "../il2cpp/serializer.js";
import { queueOnMainThread } from "../runtime/queue.js";
import { log } from "../runtime/diag.js";
import { Ctx } from "../controller.js";

const battleConfigClass = findClass(
    "BattleLogicAssembly.dll",
    "IdunBattle.Configuration",
    "BattleConfiguration",
);

const addUnitMsgClass = findClass(
    "BattleLogicAssembly.dll",
    "IdunBattle.Messages",
    "AddUnitMessage",
);
const addUnitMsgCtor4 = addUnitMsgClass
    ? findCtorByParamCount(addUnitMsgClass, 4) : null;

function buildAddUnitMessage(
    unitId: string, playerId: number, col: number, row: number,
): NativePointer {
    if (!addUnitMsgClass) throw new Error("AddUnitMessage class not found");
    if (!addUnitMsgCtor4) throw new Error("AddUnitMessage 4-arg ctor not found");
    const msg = il2cpp_object_new(addUnitMsgClass) as NativePointer;
    if (msg.isNull()) throw new Error("il2cpp_object_new(AddUnitMessage) returned null");
    gcRoot.add(msg);

    const unitIdStr = createManagedString(unitId);
    // PlayerId is a struct wrapping an int32 — passed as pointer to 4 raw bytes.
    const pidBuf = Memory.alloc(4); pidBuf.writeS32(playerId);
    const colBuf = Memory.alloc(4); colBuf.writeS32(col);
    const rowBuf = Memory.alloc(4); rowBuf.writeS32(row);

    invokeMethod(addUnitMsgCtor4.info, msg, [unitIdStr, pidBuf, colBuf, rowBuf]);
    // The 4-arg ctor leaves SpawnSource at its default (Unknown=0). The live
    // game writes Deployment=5 for user pre-battle placements — without it,
    // InputMessageProcessor routes the unit to the wrong player (env instead
    // of the intended owner), leaving the human side empty.
    msg.add(0x28).writeS32(5);
    return msg;
}

// --- Saved-bundle replay primitive (shared between LOAD = launch a fresh
//     BUILD runner, and PREVIEW = render the saved state without exposing
//     the runner as a build). Both paths build the same kind of runner and
//     replay the same kind of messages — they only differ in registration:
//     LOAD adds to runner-registry + watchedRunners; PREVIEW pins the
//     runner privately in sim-engine. ---

export interface ReplayMessage {
    idx: number; src: string; cls: string; ns: string;
    unitId: number | null;
    prng: MtSnapshot | null;
    json: string | null;
}

export interface ReplayStats {
    replayed: number; skipped: number;
    deserializeFailed: number; applyFailed: number; classNotFound: number;
    errors: Array<{ idx: number; cls: string; err: string }>;
}

function newReplayStats(): ReplayStats {
    return {
        replayed: 0, skipped: 0,
        deserializeFailed: 0, applyFailed: 0, classNotFound: 0,
        errors: [],
    };
}

/** Build a fresh IdunRunner from a JSON BattleConfiguration. Pinned by
 * gcRoot. No replay yet — caller can hook into the runner (register +
 * watch for the LOAD path; private slot for the PREVIEW path) before
 * calling `replayOnRunner` so the recorder either captures or ignores
 * subsequent applies as appropriate. */
export function buildEmptyRunner(configJson: string): {
    runner: NativePointer; innerAiControl: NativePointer; seed: number;
} {
    if (!isDeserializerReady()) {
        throw new Error("Newtonsoft DeserializeObject not resolved");
    }
    if (!battleConfigClass) {
        throw new Error("BattleConfiguration class not found");
    }
    gcRoot.init();
    const configPtr = deserializeFromJson(configJson, battleConfigClass);
    gcRoot.add(configPtr);
    return buildRunner(configPtr);
}

/** Replay persisted messages on an existing runner. Whether the recorder
 * captures these applies depends on what the caller wired up before
 * calling this — adding to watchedRunners before replay → recorder
 * captures (LOAD); leaving the runner unwatched → recorder skips
 * (PREVIEW). */
export function replayOnRunner(
    runner: NativePointer, messages: ReplayMessage[],
): { stats: ReplayStats; stage: number | null } {
    if (!runnerApplyMi) {
        throw new Error("IdunRunner.Apply not resolved");
    }
    send({ t: "diag", msg: "[replay] runner=" + runner
        + " · messages=" + messages.length });

    // Cache MT once — restoreMt is per-message before each Apply.
    let mt: ReturnType<typeof resolveMt> | null = null;
    try {
        const mtStart = runner.add(runnerOff.rng).readPointer();
        mt = resolveMt(mtStart);
    } catch { /* leave null — replay still works, just non-deterministic */ }

    const stats = newReplayStats();
    for (const m of messages) {
        if (!m.json) { stats.skipped++; continue; }
        if (!m.cls) {
            stats.classNotFound++;
            stats.errors.push({ idx: m.idx, cls: m.cls,
                err: "missing cls" });
            continue;
        }
        if (m.cls === "CheatRunAIMessage") {
            // Wrapper unrolled into ai/humanAi sub-messages — those are
            // already in the saved log, so applying the wrapper again
            // would double-execute the turn.
            stats.skipped++;
            continue;
        }
        // ns may legitimately be "" for root-namespace classes.
        const klass = findClassAnywhere(m.ns ?? "", m.cls);
        if (!klass) {
            stats.classNotFound++;
            stats.errors.push({ idx: m.idx, cls: m.cls,
                err: "class not found: " + m.ns + "." + m.cls });
            send({ t: "diag", msg: "[replay#" + m.idx + "] class NOT FOUND "
                + m.ns + "." + m.cls });
            continue;
        }
        let msgPtr: NativePointer;
        try { msgPtr = deserializeFromJson(m.json, klass); }
        catch (e) {
            stats.deserializeFailed++;
            stats.errors.push({ idx: m.idx, cls: m.cls,
                err: "deserialize: " + (e as Error).message });
            send({ t: "diag", msg: "[replay#" + m.idx + "] deserialize FAILED "
                + m.cls + ": " + (e as Error).message });
            continue;
        }
        gcRoot.add(msgPtr);
        if (m.prng && mt) {
            try { restoreMt(mt, m.prng); } catch { /* best effort */ }
        }
        // Pre-apply stage probe — lets us see if a particular Apply
        // transitioned from PreStart→Running (StartBattle) etc.
        let stagePre = -1;
        try {
            const sp = runner.add(runnerOff.state).readPointer();
            if (!sp.isNull()) stagePre = readBattleStatus(sp).stage ?? -1;
        } catch { /* leave -1 */ }
        try {
            invokeMethod(runnerApplyMi.info, runner, [msgPtr]);
            stats.replayed++;
        } catch (e) {
            stats.applyFailed++;
            stats.errors.push({ idx: m.idx, cls: m.cls,
                err: "apply: " + (e as Error).message });
            send({ t: "diag", msg: "[replay#" + m.idx + "] APPLY FAILED "
                + m.cls + ": " + (e as Error).message });
            // Continue — partial replay is more useful than abort.
            continue;
        }
        let stagePost = -1;
        try {
            const sp = runner.add(runnerOff.state).readPointer();
            if (!sp.isNull()) stagePost = readBattleStatus(sp).stage ?? -1;
        } catch { /* leave -1 */ }
        send({ t: "diag", msg: "[replay#" + m.idx + "] " + m.cls
            + " applied · stage " + stagePre + "→" + stagePost });
    }
    let stage: number | null = null;
    try {
        const sp = runner.add(runnerOff.state).readPointer();
        if (!sp.isNull()) stage = readBattleStatus(sp).stage ?? null;
    } catch { /* leave null */ }
    send({ t: "diag", msg: "[replay] DONE · replayed=" + stats.replayed
        + " · skipped=" + stats.skipped
        + " · applyFailed=" + stats.applyFailed
        + " · deserializeFailed=" + stats.deserializeFailed
        + " · classNotFound=" + stats.classNotFound
        + " · finalStage=" + stage });
    return { stats, stage };
}

/** Convenience wrapper — build + immediately replay (no register/watch
 * hook). Used by PREVIEW (sim-engine.simBuildPreview); LOAD calls the
 * underlying primitives separately so it can register+watch the runner
 * BEFORE replay (recorder must capture replay applies into state.log
 * for the future mirror catchUp to find them). */
export function buildRunnerAndReplay(
    configJson: string, messages: ReplayMessage[],
): { runner: NativePointer; innerAiControl: NativePointer; seed: number;
     stats: ReplayStats; stage: number | null } {
    const handle = buildEmptyRunner(configJson);
    const r = replayOnRunner(handle.runner, messages);
    return { ...handle, ...r };
}

function captureEvents(
    runnerId: number, runnerPtr: NativePointer, label: string,
    body: () => void,
): StreamEvent[] {
    ensureStreamHooks();
    const events: StreamEvent[] = [];
    pushApply("built", events);
    try {
        body();
    } finally {
        popApply();
    }
    // Snapshot MatchState AFTER the apply so the host sees the post-state.
    let matchState: string | null = null;
    try {
        const statePtr = runnerPtr.add(runnerOff.state).readPointer();
        if (!statePtr.isNull()) matchState = serializeToJson(statePtr);
    } catch { /* best effort */ }
    try {
        send({ t: "battle_event", runnerId, msg: label, events, matchState });
    } catch { /* best effort */ }
    return events;
}

export function register(ctx: Ctx): void {

    ctx.rpc.initRunner = (args: { configJson: string }) => {
        if (!isDeserializerReady()) {
            throw new Error("Newtonsoft DeserializeObject not resolved");
        }
        if (!battleConfigClass) {
            throw new Error("BattleConfiguration class not found");
        }
        return queueOnMainThread(() => {
            gcRoot.init();
            // Single-build policy: dispose any prior build before creating
            // a new one. Rebuild = replace, never accumulate.
            for (const old of listRunners()) {
                try {
                    const oldEntry = getRunner(old.runnerId);
                    state.watchedRunners.delete(oldEntry.runner.toString());
                    state.watchedAiControls.delete(
                        oldEntry.innerAiControl.toString());
                } catch { /* runner already gone */ }
                disposeRunner(old.runnerId);
                // Purge any state.log entries from the disposed build so
                // they don't leak across consecutive build/load cycles.
                try { purgeLogForOrigin(old.runnerId); } catch { /* ignore */ }
            }
            const configPtr = deserializeFromJson(args.configJson, battleConfigClass);
            gcRoot.add(configPtr);
            const r = buildRunner(configPtr);
            const entry = registerRunner(r);
            // Register this build runner so the recorder captures its
            // runner.Apply calls into state.log with originRunnerId=<id>.
            // Lets the auto-mirror follow a build runner the same way it
            // follows the live one. Also watch the build's inner AiControl
            // — without it, AI sub-messages dispatched by CheatRunAIMessage
            // on this runner would be invisible to the recorder, and the
            // build's mirror catchUp would have nothing to replay.
            state.watchedRunners.set(r.runner.toString(), entry.runnerId);
            state.watchedAiControls.set(
                r.innerAiControl.toString(), entry.runnerId);
            return { runnerId: entry.runnerId, seed: entry.seed };
        });
    };

    ctx.rpc.applyAddUnit = (args: {
        runnerId: number; unitId: string; playerId: number; col: number; row: number;
    }) => {
        const applyMi = runnerApplyMi;
        if (!applyMi) throw new Error("IdunRunner.Apply not resolved");
        return queueOnMainThread(() => {
            const entry = getRunner(args.runnerId);
            const msg = buildAddUnitMessage(args.unitId, args.playerId, args.col, args.row);
            const events = captureEvents(args.runnerId, entry.runner,
                "AddUnitMessage", () => {
                    invokeMethod(applyMi.info, entry.runner, [msg]);
                });
            return { ok: true, eventCount: events.length };
        });
    };

    ctx.rpc.startBattle = (args: { runnerId: number }) => {
        const startMi = runnerStartMatchMi;
        if (!startMi) throw new Error("IdunRunner.StartMatch not resolved");
        return queueOnMainThread(() => {
            const entry = getRunner(args.runnerId);
            if (entry.started) throw new Error("battle already started");
            const events = captureEvents(args.runnerId, entry.runner,
                "StartMatch", () => {
                    invokeMethod(startMi.info, entry.runner, null);
                });
            entry.started = true;
            return { ok: true, eventCount: events.length };
        });
    };

    ctx.rpc.listRunners = () => listRunners();

    ctx.rpc.disposeRunner = (args: { runnerId: number }) => {
        // Drop watch entries first so the recorder stops tagging messages
        // with this runnerId (and stops capturing once the runner is freed).
        try {
            const entry = getRunner(args.runnerId);
            state.watchedRunners.delete(entry.runner.toString());
            state.watchedAiControls.delete(entry.innerAiControl.toString());
        } catch { /* runner already gone */ }
        const removed = disposeRunner(args.runnerId);
        // Purge state.log entries originating from this runner so the
        // buffers stay bounded.
        try { purgeLogForOrigin(args.runnerId); } catch { /* ignore */ }
        return { removed };
    };

    /** LOAD from a saved bundle — builds a fresh BUILD runner from the
     * saved BattleConfiguration and replays every captured message so the
     * runner ends up in the saved state. The recorder naturally captures
     * each replayed Apply into state.log with originRunnerId = the new
     * build's id — which is exactly what the mirror needs later (clicking
     * 🪞 on this BUILD tile builds a mirror + catchUp replays those entries
     * → mirror reaches the saved state too).
     *
     * Each saved msg carries (ns, cls) → resolve via findClassAnywhere,
     * (json) → deserialize via Newtonsoft, (prng) → restoreMt on the new
     * runner's MT before Apply so determinism matches the original run.
     *
     * Top-of-the-log boot messages (`top_boot`) lack a PRNG snapshot — we
     * apply them without restore. Same fidelity as the live recorder
     * provides; gameplay is bootstrapped from these so they're idempotent
     * w.r.t. random draws in practice. */
    ctx.rpc.loadFromSavedBundle = (args: {
        configJson: string;
        messages: ReplayMessage[];
    }) => queueOnMainThread(() => {
        // Single-build policy — drop any prior build before this one.
        for (const old of listRunners()) {
            try {
                const oldEntry = getRunner(old.runnerId);
                state.watchedRunners.delete(oldEntry.runner.toString());
            } catch { /* runner already gone */ }
            disposeRunner(old.runnerId);
        }
        // LOAD takes over — drop any preview held by sim-engine.
        if (state.previewRunner) {
            try { gcRoot.remove(state.previewRunner); } catch { /* ignore */ }
            state.previewRunner = null;
        }
        // Build first, then register+watch, then replay. The watch must
        // be in place BEFORE replay so the recorder captures each replayed
        // Apply into state.log with originRunnerId = entry.runnerId — the
        // future mirror catchUp filters state.log by originRunnerId, so
        // missing entries → mirror reaches initial config state, not the
        // replayed state, and renders nothing.
        const handle = buildEmptyRunner(args.configJson);
        const entry = registerRunner(handle);
        state.watchedRunners.set(handle.runner.toString(), entry.runnerId);
        state.watchedAiControls.set(
            handle.innerAiControl.toString(), entry.runnerId);
        const replay = replayOnRunner(handle.runner, args.messages);
        // Emit a battle_event with the final matchstate so the host's
        // battle-store writes a disk dump for this runner — switchToRunner
        // on the front reads from /api/runners/:id/latest-state to populate
        // its tile/board.
        try {
            const sp = handle.runner.add(runnerOff.state).readPointer();
            if (!sp.isNull()) {
                const ms = serializeToJson(sp);
                if (ms) {
                    send({
                        t: "battle_event",
                        runnerId: entry.runnerId,
                        msg: "LoadedFromBundle",
                        events: [],
                        matchState: ms,
                    });
                }
            }
        } catch { /* best effort */ }
        return {
            ok: true,
            runnerId: entry.runnerId,
            seed: handle.seed,
            stage: replay.stage,
            stats: replay.stats,
            firstErrors: replay.stats.errors.slice(0, 10),
        };
    });

    // Fire CheatRunAIMessage on a registry runner. Delegates turn-play to
    // the game's own AI. Whoever's turn is currently active on that runner
    // gets played. Events stream out via the same `battle_event` path as
    // applyAddUnit / startBattle.
    let playTurnSeq = 0;
    ctx.rpc.playTurn = (args: { runnerId: number }) => {
        if (!cheatRunAiClass) throw new Error("CheatRunAIMessage class not found");
        const applyMi = runnerApplyMi;
        if (!applyMi) throw new Error("IdunRunner.Apply not resolved");
        const klass = cheatRunAiClass;
        return queueOnMainThread(() => {
            const entry = getRunner(args.runnerId);
            const seq = ++playTurnSeq;

            // Pre-apply snapshot — if the following invoke crashes, this is
            // the last line visible in the host log before the exception handler fires.
            let preStatus: any = null;
            try {
                const statePtr = entry.runner.add(runnerOff.state).readPointer();
                if (!statePtr.isNull()) preStatus = readBattleStatus(statePtr);
            } catch (e) { preStatus = { err: (e as Error).message }; }
            log("[playTurn #" + seq + "] runner=" + args.runnerId
                + " pre=" + JSON.stringify(preStatus));

            // Each step is logged so a native fault leaves a precise breadcrumb
            // (Frida swallows SEH on Windows and just throws "system error").
            let msg: NativePointer;
            try {
                log("[playTurn #" + seq + "] step=createObject(CheatRunAIMessage)");
                msg = createObject(klass);
                log("[playTurn #" + seq + "] msg=" + msg);
            } catch (e) {
                log("[playTurn #" + seq + "] FAILED at createObject: " + (e as Error).message);
                throw e;
            }
            try {
                log("[playTurn #" + seq + "] step=gcRoot.add count=" + gcRoot.count());
                gcRoot.add(msg);
                log("[playTurn #" + seq + "] gcRoot.add ok newCount=" + gcRoot.count());
            } catch (e) {
                log("[playTurn #" + seq + "] FAILED at gcRoot.add: " + (e as Error).message);
                throw e;
            }

            // Apply with one retry-after-frame on transient access violations.
            //
            // Observed: on a freshly-built standalone runner the first
            // Apply(CheatRunAIMessage) can fault deep in the AI dispatch path
            // (`access violation accessing 0x135`) — non-deterministic, likely
            // a downstream subscription / AiControl entry not yet wired up.
            // Retrying on the next pump tick (= next frame) consistently
            // works. queueOnMainThread re-parks us and the menu/main pump
            // drains it on its next Update.
            const isTransientFault = (err: Error): boolean =>
                /access violation|system error/i.test(err.message);

            const applyOnce = (label: string): StreamEvent[] => {
                log("[playTurn #" + seq + "] step=invokeMethod(runner.Apply) " + label
                    + " runner=" + entry.runner);
                return captureEvents(args.runnerId, entry.runner, "PlayTurn",
                    () => { invokeMethod(applyMi.info, entry.runner, [msg]); });
            };

            const result = (() => {
                try {
                    const events = applyOnce("first");
                    log("[playTurn #" + seq + "] invokeMethod returned, events=" + events.length);
                    return Promise.resolve(events);
                } catch (e) {
                    const err = e as Error;
                    if (!isTransientFault(err)) {
                        log("[playTurn #" + seq + "] FAILED at invokeMethod (fatal): " + err.message);
                        throw e;
                    }
                    log("[playTurn #" + seq + "] transient fault: " + err.message
                        + " — retrying next frame");
                    // Re-queue: drainPending awaits this Promise; the inner
                    // queueOnMainThread parks a fresh task that the pump
                    // drains on its next Update tick.
                    return queueOnMainThread(() => {
                        // Rebuild the message — the previous one may have
                        // been left in an inconsistent state by the fault.
                        msg = createObject(klass);
                        gcRoot.add(msg);
                        log("[playTurn #" + seq + "] retry: new msg=" + msg);
                        const events = applyOnce("retry");
                        log("[playTurn #" + seq + "] retry succeeded, events=" + events.length);
                        return events;
                    });
                }
            })();

            // Note: from here on we operate on a Promise so the postStatus
            // snapshot must also chain. drainPending unwraps the outer Promise.
            return result.then((events: StreamEvent[]) => {
                let postStatus: any = null;
                try {
                    const statePtr = entry.runner.add(runnerOff.state).readPointer();
                    if (!statePtr.isNull()) postStatus = readBattleStatus(statePtr);
                } catch (e) { postStatus = { err: (e as Error).message }; }
                log("[playTurn #" + seq + "] runner=" + args.runnerId
                    + " post=" + JSON.stringify(postStatus)
                    + " events=" + events.length);
                return { ok: true, eventCount: events.length, seq, preStatus, postStatus };
            });
        });
    };
}
