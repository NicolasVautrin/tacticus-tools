// Sim engine — persistent "mirror" runner that follows the live runner
// message-by-message via log replay + per-message PRNG sync.
//
// The mirror is a fully isolated IdunRunner instance built from the same
// BattleConfiguration as live. We keep it caught up by re-applying every
// message captured by the live recorder onto the mirror (with PRNG state
// restored before each apply). The mirror never mutates the live game.
//
// Two control paths feed the mirror:
//   1. simMirror() — initial bring-up: build runner if needed, replay
//      state.log[lastSyncedLogIdx..] in one batch.
//   2. applyToMirror() — per-message hook: called by the recorder right
//      after a live apply. Catches up the single new message.
//
// Both paths set `state.replayingOnMirror = true` while invoking on the
// mirror, so the recorder's hook (which fires recursively from the mirror's
// own runner.Apply pipeline) skips its push and avoids re-entry.
//
// Notification model: the mirror emits `sim_state_changed` with just a
// monotonic revision and `syncedToLogIdx`. The host forwards via WS, the
// front fetches the projected state via GET /api/sim/state on demand.
// Keeps the WS channel small even during AI-message bursts.

import { Ctx } from "../controller.js";
import { invokeMethod } from "../il2cpp/invoke.js";
import { resolveMt, restoreMt } from "../il2cpp/mt.js";
import { gcRoot } from "../il2cpp/gc-root.js";
import { class_get_name, s } from "../il2cpp/helpers.js";
import { serializeToJson } from "../il2cpp/serializer.js";
import {
    applyAiMsgMi, applyHumanAiMsgMi,
} from "../game/ai-control.js";
import {
    pushApply, popApply, applyStack, StreamEvent,
} from "../game/apply-stack.js";
import {
    buildRunner, runnerApplyMi, runnerOff,
} from "../game/runner.js";
import {
    digestState, entityCensus, EntityType, forEachEntity, msEntitiesOff,
    projectMatchState, readBattleStatus, UnitProjection,
} from "../game/match-state.js";
import { state } from "../game/state.js";
import { queueOnMainThread } from "../runtime/queue.js";

interface MirrorHandle {
    runner: NativePointer;
    aiControl: NativePointer;
    seed: number;
    builtAt: number;
    /** Pointer of the live runner the mirror was built from. If
     * `state.runnerInstance` later differs from this, the mirror is stale
     * (a new battle was entered) and must be disposed before any further
     * applyToMirror — otherwise we'd replay new-battle messages on an
     * old-battle mirror. */
    builtFromLive: NativePointer;
}

interface SimEngineState {
    mirror: MirrorHandle | null;
    lastSyncedLogIdx: number;
    revision: number;
    diverged: boolean;
    divergedReason: string | null;
}

export const simState: SimEngineState = {
    mirror: null,
    lastSyncedLogIdx: 0,
    revision: 0,
    diverged: false,
    divergedReason: null,
};

interface ReplayStats {
    top: number; top_boot: number; ai: number; humanAi: number;
    skippedCheatRunAi: number;
    errors: Array<{ idx: number; src: string; cls: string; err: string }>;
    /** Per-message StreamEvent comparison live vs mirror — divergence here
     * means our replay is non-deterministic w.r.t. the live game even
     * though no exception was raised. */
    eventDivergences: Array<{
        idx: number; src: string; cls: string;
        liveCount: number; mirrorCount: number;
        firstDiff: string | null;
    }>;
}

function newReplayStats(): ReplayStats {
    return {
        top: 0, top_boot: 0, ai: 0, humanAi: 0,
        skippedCheatRunAi: 0, errors: [], eventDivergences: [],
    };
}

/** Replay a single live log entry on the mirror. Wraps in pushApply/popApply
 * so StreamDispatcher events get tagged "mirror". */
function replayEntryOnMirror(
    mirror: MirrorHandle, entry: typeof state.log[number],
    stats: ReplayStats,
): void {
    if ((entry.src === "top" || entry.src === "top_boot")
        && entry.cls === "CheatRunAIMessage") {
        // CheatRunAI's effects are already in the log as ai/humanAi
        // sub-messages — replaying it on the mirror would either re-trigger
        // AI execution there (double-counting), so skip.
        stats.skippedCheatRunAi++;
        return;
    }

    // Align mirror PRNG to the snapshot taken right before live applied this
    // message. With this, the mirror's stochastic decisions match live's
    // exactly.
    if (entry.prng) {
        try {
            const mtStart = mirror.runner.add(runnerOff.rng).readPointer();
            const mt = resolveMt(mtStart);
            if (mt) restoreMt(mt, entry.prng);
        } catch { /* best effort — proceed without PRNG sync */ }
    }

    const mirrorEvents: StreamEvent[] = [];
    pushApply("mirror", mirrorEvents);
    try {
        const msgPtr = ptr(entry.ptr);
        if (entry.src === "top" || entry.src === "top_boot") {
            invokeMethod(runnerApplyMi!.info, mirror.runner, [msgPtr]);
            stats[entry.src]++;
        } else if (entry.src === "ai" || entry.src === "humanAi") {
            // AI / HumanAI messages on live go through aiControl which
            // validates against AI services (BattleAiService etc.). Our
            // standalone mirror runner is built raw via `il2cpp_object_new`
            // — no Zenject bindings → those AI services are null → AV.
            // Bypass the validator and apply the message directly through
            // runner.Apply, which only touches the matchstate pipeline.
            invokeMethod(runnerApplyMi!.info, mirror.runner, [msgPtr]);
            if (entry.src === "ai") stats.ai++;
            else stats.humanAi++;
        }
    } catch (e) {
        stats.errors.push({
            idx: entry.idx, src: entry.src, cls: entry.cls,
            err: (e as Error).message,
        });
    } finally {
        popApply();
    }

    // Compare live↔mirror StreamEvents for this entry. Surfaces any
    // determinism breach (different damage tags, missing/extra events,
    // wrong entity targeted, …) message-by-message.
    const diff = diffEvents(entry.events, mirrorEvents);
    if (diff.divergent) {
        stats.eventDivergences.push({
            idx: entry.idx, src: entry.src, cls: entry.cls,
            liveCount: entry.events.length,
            mirrorCount: mirrorEvents.length,
            firstDiff: diff.firstDiff,
        });
        send({
            t: "diag",
            msg: "[sim] events DIVERGE · idx=" + entry.idx
                + " · src=" + entry.src + " · cls=" + entry.cls
                + " · live=" + entry.events.length
                + " mirror=" + mirrorEvents.length
                + " · first=" + diff.firstDiff,
        });
    }
}

interface EventDiff {
    divergent: boolean;
    /** Compact human-readable description of the first mismatch found. */
    firstDiff: string | null;
}

function diffEvents(
    live: StreamEvent[], mirror: StreamEvent[],
): EventDiff {
    if (live.length !== mirror.length) {
        return {
            divergent: true,
            firstDiff: "count: live=" + live.length
                + " mirror=" + mirror.length,
        };
    }
    for (let i = 0; i < live.length; i++) {
        const a = live[i], b = mirror[i];
        if (a.kind !== b.kind) {
            return {
                divergent: true,
                firstDiff: "[" + i + "] kind: live=" + a.kind
                    + " mirror=" + b.kind,
            };
        }
        if (a.step !== b.step || a.group !== b.group) {
            return {
                divergent: true,
                firstDiff: "[" + i + "] step/group: live="
                    + (a.step ?? a.group) + " mirror="
                    + (b.step ?? b.group),
            };
        }
        if (a.entity !== b.entity) {
            return {
                divergent: true,
                firstDiff: "[" + i + "] entity: live=" + a.entity
                    + " mirror=" + b.entity,
            };
        }
        if (a.tags !== b.tags) {
            // Scalar-level diff: parse both as JSON dicts and surface the
            // FIRST differing key with its numeric values. Cheap to read,
            // catches "same shape, off-by-one damage" cases.
            const tagDiff = diffTagsScalar(a.tags, b.tags);
            return {
                divergent: true,
                firstDiff: "[" + i + "] tag · " + tagDiff,
            };
        }
    }
    return { divergent: false, firstDiff: null };
}

/** Compare two `tags` JSON strings key-by-key. Returns a compact summary
 * of the first scalar mismatch, or "shape mismatch" if structure differs. */
function diffTagsScalar(
    aRaw: string | null | undefined, bRaw: string | null | undefined,
): string {
    if (aRaw === bRaw) return "(equal)";
    if (!aRaw || !bRaw) {
        return "presence: live=" + (aRaw ?? "null")
            + " mirror=" + (bRaw ?? "null");
    }
    let aDict: Record<string, unknown>, bDict: Record<string, unknown>;
    try { aDict = JSON.parse(aRaw); }
    catch { return "live tags unparseable"; }
    try { bDict = JSON.parse(bRaw); }
    catch { return "mirror tags unparseable"; }
    const keys = new Set<string>([
        ...Object.keys(aDict), ...Object.keys(bDict),
    ]);
    for (const k of keys) {
        const av = aDict[k], bv = bDict[k];
        if (av !== bv) {
            return k + " · live=" + JSON.stringify(av)
                + " mirror=" + JSON.stringify(bv);
        }
    }
    return "(equal-by-key but raw differs — ordering?)";
}

/** Catch the mirror up by replaying state.log[from..to). */
function catchUp(
    mirror: MirrorHandle, fromIdx: number, toIdx: number,
): ReplayStats {
    const stats = newReplayStats();
    state.replayingOnMirror = true;
    try {
        for (let i = fromIdx; i < toIdx; i++) {
            replayEntryOnMirror(mirror, state.log[i], stats);
        }
    } finally {
        state.replayingOnMirror = false;
    }
    simState.lastSyncedLogIdx = toIdx;
    return stats;
}

/** Compute the live↔mirror compare payload returned by simGetState. */
interface CompareReport {
    equivalent: boolean;
    divergences: Array<{
        entityId: number; field: string;
        liveValue: unknown; mirrorValue: unknown;
    }>;
    liveLogIdx: number;
    mirrorLogIdx: number;
    lag: number;
    liveDigest: string | null;
    mirrorDigest: string | null;
    liveTurn: number | null;
    mirrorTurn: number | null;
    liveCurrentPlayer: number | null;
    mirrorCurrentPlayer: number | null;
    isAiRunning: boolean;
    liveStage: number | null;
    liveStageName: string | null;
    liveUnitsAlive: number;
    mirrorUnitsAlive: number;
}

function unitField(
    units: UnitProjection[],
): Map<number, UnitProjection> {
    const m = new Map<number, UnitProjection>();
    for (const u of units) m.set(u.id, u);
    return m;
}

function computeCompare(
    liveStatePtr: NativePointer, mirrorStatePtr: NativePointer,
): CompareReport {
    const liveProj = projectMatchState(liveStatePtr);
    const mirrorProj = projectMatchState(mirrorStatePtr);
    const liveDigest = digestState(liveStatePtr);
    const mirrorDigest = digestState(mirrorStatePtr);
    const liveStatus = readBattleStatus(liveStatePtr);
    const liveCensus = entityCensus(liveStatePtr);
    const mirrorCensus = entityCensus(mirrorStatePtr);

    const isAiRunning = (() => {
        try { return liveStatePtr.add(0x58).readU8() !== 0; }
        catch { return false; }
    })();

    const liveById = unitField(liveProj.units);
    const mirrorById = unitField(mirrorProj.units);
    const divergences: CompareReport["divergences"] = [];
    const allIds = new Set<number>([...liveById.keys(), ...mirrorById.keys()]);
    for (const id of allIds) {
        const lu = liveById.get(id);
        const mu = mirrorById.get(id);
        if (!lu) {
            divergences.push({
                entityId: id, field: "exists",
                liveValue: false, mirrorValue: true,
            });
            continue;
        }
        if (!mu) {
            divergences.push({
                entityId: id, field: "exists",
                liveValue: true, mirrorValue: false,
            });
            continue;
        }
        const fields: Array<keyof UnitProjection> = [
            "hp", "maxHp", "ownerId", "isDead",
        ];
        for (const f of fields) {
            if (lu[f] !== mu[f]) {
                divergences.push({
                    entityId: id, field: f,
                    liveValue: lu[f] as unknown, mirrorValue: mu[f] as unknown,
                });
            }
        }
        const lp = lu.pos ? `${lu.pos.col},${lu.pos.row}` : "null";
        const mp = mu.pos ? `${mu.pos.col},${mu.pos.row}` : "null";
        if (lp !== mp) {
            divergences.push({
                entityId: id, field: "pos",
                liveValue: lu.pos, mirrorValue: mu.pos,
            });
        }
    }

    return {
        equivalent: divergences.length === 0
            && liveDigest?.digest === mirrorDigest?.digest,
        divergences,
        liveLogIdx: state.log.length,
        mirrorLogIdx: simState.lastSyncedLogIdx,
        lag: state.log.length - simState.lastSyncedLogIdx,
        liveDigest: liveDigest?.digest ?? null,
        mirrorDigest: mirrorDigest?.digest ?? null,
        liveTurn: liveStatus.currentTurnPlayer,
        mirrorTurn: mirrorProj.turn,
        liveCurrentPlayer: liveStatus.currentTurnPlayer,
        mirrorCurrentPlayer: mirrorProj.playerOnTurn,
        isAiRunning,
        liveStage: liveStatus.stage,
        liveStageName: liveStatus.stageName,
        liveUnitsAlive: liveCensus.byType[1]?.length ?? 0,
        mirrorUnitsAlive: mirrorCensus.byType[1]?.length ?? 0,
    };
}

// --- Public API exposed to the recorder for auto-mirror ---

/** Apply a single live log entry to the mirror. Called by recorder onLeave.
 * No-op if no mirror or if mirror has diverged. */
export function applyToMirror(): void {
    if (simState.mirror === null || simState.diverged) return;
    // If the live runner switched (new battle) since we built the mirror,
    // drop it cleanly — the new battle's messages would be incoherent on
    // the old config's runner. The user can rebuild on demand.
    syncMirrorWithLiveRunner();
    if (simState.mirror === null) return;
    if (state.log.length <= simState.lastSyncedLogIdx) return;

    const mirror = simState.mirror;
    const fromIdx = simState.lastSyncedLogIdx;
    const toIdx = state.log.length;
    const t0 = Date.now();
    send({
        t: "diag", msg: "[sim] applyToMirror enter · range="
            + fromIdx + ".." + toIdx + " · " + (toIdx - fromIdx) + " entries",
    });

    let hadError = false;
    state.replayingOnMirror = true;
    let lastIdx = -1;
    let lastCls = "?";
    let lastSrc = "?";
    try {
        for (let i = fromIdx; i < toIdx; i++) {
            lastIdx = i;
            lastCls = state.log[i].cls;
            lastSrc = state.log[i].src;
            const stats = newReplayStats();
            replayEntryOnMirror(mirror, state.log[i], stats);
            if (stats.errors.length > 0) {
                hadError = true;
                simState.diverged = true;
                simState.divergedReason =
                    `${stats.errors[0].cls}: ${stats.errors[0].err}`;
                send({
                    t: "sim_diverged", reason: simState.divergedReason,
                    atLogIdx: i,
                });
                break;
            }
        }
    } finally {
        state.replayingOnMirror = false;
    }
    send({
        t: "diag", msg: "[sim] applyToMirror exit · ms=" + (Date.now() - t0)
            + " · lastIdx=" + lastIdx + " · lastSrc=" + lastSrc
            + " · lastCls=" + lastCls + " · hadError=" + hadError,
    });
    if (!hadError) simState.lastSyncedLogIdx = toIdx;

    simState.revision++;
    send({
        t: "sim_state_changed",
        revision: simState.revision,
        syncedToLogIdx: simState.lastSyncedLogIdx,
        liveLogIdx: state.log.length,
    });
}

// --- RPCs ---

interface StatusReport {
    built: boolean;
    lastSyncedLogIdx: number;
    logSize: number;
    liveStage: number | null;
    liveStageName: string | null;
    liveCurrentPlayer: number | null;
    isAiRunning: boolean;
    diverged: boolean;
    divergedReason: string | null;
    revision: number;
    canMirror: boolean;
    blockReason: string | null;
}

function readStatus(): StatusReport {
    const live = state.runnerInstance;
    if (!live) {
        return {
            built: simState.mirror !== null,
            lastSyncedLogIdx: simState.lastSyncedLogIdx,
            logSize: state.log.length,
            liveStage: null, liveStageName: null,
            liveCurrentPlayer: null,
            isAiRunning: false,
            diverged: simState.diverged,
            divergedReason: simState.divergedReason,
            revision: simState.revision,
            canMirror: false,
            blockReason: "no live runner",
        };
    }
    let liveStatePtr: NativePointer;
    try { liveStatePtr = live.add(runnerOff.state).readPointer(); }
    catch {
        return {
            built: simState.mirror !== null,
            lastSyncedLogIdx: simState.lastSyncedLogIdx,
            logSize: state.log.length,
            liveStage: null, liveStageName: null,
            liveCurrentPlayer: null, isAiRunning: false,
            diverged: simState.diverged,
            divergedReason: simState.divergedReason,
            revision: simState.revision,
            canMirror: false,
            blockReason: "live runner _state unreadable",
        };
    }
    if (liveStatePtr.isNull()) {
        return {
            built: simState.mirror !== null,
            lastSyncedLogIdx: simState.lastSyncedLogIdx,
            logSize: state.log.length,
            liveStage: null, liveStageName: null,
            liveCurrentPlayer: null, isAiRunning: false,
            diverged: simState.diverged,
            divergedReason: simState.divergedReason,
            revision: simState.revision,
            canMirror: false,
            blockReason: "live runner _state null",
        };
    }
    const status = readBattleStatus(liveStatePtr);
    let isAiRunning = false;
    try { isAiRunning = liveStatePtr.add(0x58).readU8() !== 0; }
    catch { /* keep false */ }

    let block: string | null = null;
    if (status.stage !== 1) block = `live stage ${status.stageName ?? status.stage}`;
    else if (isAiRunning) block = "AI is running on live — wait for human turn";

    return {
        built: simState.mirror !== null,
        lastSyncedLogIdx: simState.lastSyncedLogIdx,
        logSize: state.log.length,
        liveStage: status.stage,
        liveStageName: status.stageName,
        liveCurrentPlayer: status.currentTurnPlayer,
        isAiRunning,
        diverged: simState.diverged,
        divergedReason: simState.divergedReason,
        revision: simState.revision,
        canMirror: block === null,
        blockReason: block,
    };
}

function disposeMirror(): void {
    if (simState.mirror) {
        const ptr = simState.mirror.runner.toString();
        try { gcRoot.remove(simState.mirror.runner); } catch { /* ignore */ }
        try {
            send({
                t: "diag", msg: "[sim] disposeMirror · runner=" + ptr
                    + " · gcRoot.count=" + gcRoot.count(),
            });
        } catch { /* gcRoot may be uninit */ }
    }
    simState.mirror = null;
    simState.lastSyncedLogIdx = 0;
    simState.diverged = false;
    simState.divergedReason = null;
}

function buildMirrorFromLive(): MirrorHandle {
    const live = state.runnerInstance;
    if (!live) throw new Error("no live runner");
    const cfg = live.add(runnerOff.config).readPointer();
    if (cfg.isNull()) throw new Error("live runner config null");
    const handle = buildRunner(cfg);
    return {
        runner: handle.runner,
        aiControl: handle.innerAiControl,
        seed: handle.seed,
        builtAt: Date.now(),
        builtFromLive: live,
    };
}

/** Detect a live runner switch (new battle started) and discard the
 * previous mirror. The recorder already clears state.log on this event
 * (main-pump.ts), so we just need to drop the now-stale mirror — the
 * user can rebuild on demand. */
function syncMirrorWithLiveRunner(): void {
    if (simState.mirror === null) return;
    const live = state.runnerInstance;
    if (!live) {
        // Live runner gone (battle ended/crashed) — keep mirror so the
        // user can still inspect the last state, but flag it so applyToMirror
        // stops trying to replay further messages.
        return;
    }
    if (!simState.mirror.builtFromLive.equals(live)) {
        send({
            t: "sim_diverged",
            reason: "live runner switched (new battle?) — mirror auto-reset",
            atLogIdx: simState.lastSyncedLogIdx,
        });
        disposeMirror();
    }
}

export function register(ctx: Ctx): void {
    /** Always: drop any existing mirror, rebuild from current live config,
     * replay the full log up to live's latest entry. The user's contract
     * is "MIRROR NOW = give me a fresh-and-current mirror" — no
     * incremental-catchup, no preconditions beyond a live runner with
     * a config we can copy. */
    ctx.rpc.simMirror = (): Promise<unknown> => queueOnMainThread(() => {
        if (!state.runnerInstance) {
            return { ok: false, error: "no live runner" };
        }
        // Drop any prior mirror (whether stale, diverged, or fine — we
        // always rebuild for predictability).
        // Clean any dangling mirror frame on the apply-stack from a prior
        // crashed replay, then dispose.
        while (applyStack.length > 0
            && applyStack[applyStack.length - 1].role === "mirror") {
            popApply();
        }
        disposeMirror();

        const t0 = Date.now();
        try {
            simState.mirror = buildMirrorFromLive();
        } catch (e) {
            return { ok: false, error: "build failed: " + (e as Error).message };
        }

        const replayCount = state.log.length;
        const stats = catchUp(simState.mirror, 0, replayCount);
        const totalMs = Date.now() - t0;
        send({
            t: "diag",
            msg: "[sim] rebuild · messages=" + replayCount
                + " · totalMs=" + totalMs,
        });

        simState.revision++;
        send({
            t: "sim_state_changed",
            revision: simState.revision,
            syncedToLogIdx: simState.lastSyncedLogIdx,
            liveLogIdx: state.log.length,
        });

        return {
            ok: true,
            builtAt: simState.mirror.builtAt,
            seed: simState.mirror.seed,
            syncedToLogIdx: simState.lastSyncedLogIdx,
            replayStats: stats,
            revision: simState.revision,
        };
    });

    /** Serialize the live runner's BattleConfiguration as JSON — lets the
     * front load the matching board PNG + hex layout for the running
     * battle, even if the user never went through the campaign-builder
     * archive flow. */
    ctx.rpc.simGetBattleConfig = (): Promise<unknown> =>
        queueOnMainThread(() => {
            const live = state.runnerInstance;
            if (!live) return { ok: false, error: "no live runner" };
            const cfg = live.add(runnerOff.config).readPointer();
            if (cfg.isNull()) return { ok: false, error: "config null" };
            const json = serializeToJson(cfg);
            if (!json) return { ok: false, error: "serialize failed" };
            return { ok: true, bytes: json.length, json };
        });

    /** Lightweight status — used by the front to enable/disable buttons. */
    ctx.rpc.simStatus = (): Promise<unknown> =>
        queueOnMainThread(() => {
            // Detect runner switch on every status poll so the front sees
            // the auto-reset state without waiting for the next live message.
            syncMirrorWithLiveRunner();
            return readStatus();
        });

    /** Read the current mirror matchState + a live↔mirror compare summary.
     * Returns 404-shaped {ok:false} if no mirror exists. */
    ctx.rpc.simGetState = (): Promise<unknown> => queueOnMainThread(() => {
        if (simState.mirror === null) {
            return { ok: false, error: "no mirror" };
        }
        const live = state.runnerInstance;
        if (!live) return { ok: false, error: "no live runner" };
        const liveStatePtr = live.add(runnerOff.state).readPointer();
        const mirrorStatePtr = simState.mirror.runner
            .add(runnerOff.state).readPointer();
        if (liveStatePtr.isNull() || mirrorStatePtr.isNull()) {
            return { ok: false, error: "state pointer null" };
        }
        const mirrorProjection = projectMatchState(mirrorStatePtr);
        const compare = computeCompare(liveStatePtr, mirrorStatePtr);
        return {
            ok: true,
            mirror: mirrorProjection,
            compare,
            diverged: simState.diverged,
            divergedReason: simState.divergedReason,
            revision: simState.revision,
        };
    });

    /** Drop the mirror — next simMirror() rebuilds from scratch. */
    ctx.rpc.simReset = (): Promise<unknown> => queueOnMainThread(() => {
        const had = simState.mirror !== null;
        // If we had a frame on the apply-stack from a previous mirror replay
        // that crashed mid-flight, clean up.
        while (applyStack.length > 0
            && applyStack[applyStack.length - 1].role === "mirror") {
            popApply();
        }
        disposeMirror();
        simState.revision++;
        send({
            t: "sim_state_changed",
            revision: simState.revision,
            syncedToLogIdx: 0,
            liveLogIdx: state.log.length,
        });
        return { ok: true, hadMirror: had };
    });

    void EntityType; void forEachEntity; void msEntitiesOff;
    void class_get_name; void s;

    /** Drop the mirror, rebuild, and replay log[0..logIdx). Lets the user
     * "rewind" to any point in the live history. logIdx is exclusive. */
    ctx.rpc.simRebuildAndCatchUpTo = (
        body: { logIdx: number },
    ): Promise<unknown> => queueOnMainThread(() => {
        if (typeof body?.logIdx !== "number") {
            return { ok: false, error: "body must be { logIdx: number }" };
        }
        const target = Math.max(0, Math.min(body.logIdx, state.log.length));
        disposeMirror();
        simState.mirror = buildMirrorFromLive();
        const stats = catchUp(simState.mirror, 0, target);
        simState.revision++;
        send({
            t: "sim_state_changed",
            revision: simState.revision,
            syncedToLogIdx: simState.lastSyncedLogIdx,
            liveLogIdx: state.log.length,
        });
        return {
            ok: true, builtAt: simState.mirror.builtAt,
            seed: simState.mirror.seed,
            syncedToLogIdx: simState.lastSyncedLogIdx,
            replayStats: stats,
            revision: simState.revision,
        };
    });
}
