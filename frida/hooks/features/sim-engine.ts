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
import {
    buildRunnerAndReplay, ReplayMessage,
} from "./launch.js";
import { invokeMethod, il2cpp_object_new } from "../il2cpp/invoke.js";
import { resolveMt, restoreMt } from "../il2cpp/mt.js";
import { gcRoot } from "../il2cpp/gc-root.js";
import {
    class_get_name, findClass, findCtorByParamCount,
    readMsgIdentity, s,
} from "../il2cpp/helpers.js";
import { serializeToJson } from "../il2cpp/serializer.js";
import {
    applyAiMsgMi, applyHumanAiMsgMi, cheatRunAiClass,
} from "../game/ai-control.js";
import {
    pushApply, popApply, applyStack, StreamEvent,
} from "../game/apply-stack.js";
import {
    buildRunner, getReplayMi, replayOff, runnerApplyMi, runnerOff,
} from "../game/runner.js";
import {
    getRunner as getRegistryRunner, listRunners as listRegistryRunners,
} from "../game/runner-registry.js";
import {
    digestState, entityCensus, EntityType, forEachEntity, msEntitiesOff,
    projectMatchState, readBattleStatus, UnitProjection,
} from "../game/match-state.js";
import {
    state, clearMirrorQueueUnpinned, unpinEntries,
} from "../game/state.js";
import { queueOnMainThread } from "../runtime/queue.js";

/** Source of a mirror — either the in-game live runner or a build runner
 * registered via launch.initRunner. Drives which `state.log` entries
 * `applyToMirror` replays and which runner's PRNG/state is read at simMirror
 * time. The mirror exists in BOTH cases so the user can apply AI overrides
 * (weight tweaks, injected decisions) on the mirror while keeping the
 * source runner intact as a baseline for comparison. */
export type MirrorSource =
    | { kind: "live" }
    | { kind: "build"; runnerId: number };

interface MirrorHandle {
    runner: NativePointer;
    aiControl: NativePointer;
    seed: number;
    builtAt: number;
    source: MirrorSource;
    /** Pointer of the source runner at build time. If the live runner
     * switches (new battle) or the build is disposed, this no longer
     * resolves to a valid runner → mirror is stale. */
    builtFromRunner: NativePointer;
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

/** Catch the mirror up by replaying state.log[from..to). Only entries
 * whose originRunnerId matches the mirror's source are replayed —
 * without this filter, a live mirror built after a LOAD would re-execute
 * the build's saved-bundle messages on top of the live config, mixing
 * states (3 heroes at deployment from the build + whatever live had).
 * Symmetric with the per-message filter in `applyToMirror`. */
function catchUp(
    mirror: MirrorHandle, fromIdx: number, toIdx: number,
): ReplayStats {
    const stats = newReplayStats();
    const targetOrigin: "live" | number = mirror.source.kind === "live"
        ? "live" : mirror.source.runnerId;
    state.replayingOnMirror = true;
    try {
        for (let i = fromIdx; i < toIdx; i++) {
            const entry = state.log[i];
            if ((entry.originRunnerId ?? "live") !== targetOrigin) continue;
            replayEntryOnMirror(mirror, entry, stats);
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

/** Purge state.log entries whose originRunnerId matches the given build
 * runnerId. Called from the recorder's match-end cleanup so the buffers
 * don't accumulate across consecutive build/load cycles. Also adjusts
 * simState.lastSyncedLogIdx so the still-active mirror (if any) keeps
 * correct positional bookkeeping after the array shrinks. */
export function purgeLogForOrigin(buildId: number): number {
    const before = state.log.length;
    if (before === 0) return 0;
    // Separate kept vs removed so we can unpin the removed entries'
    // message ptrs from gcRoot — the recorder pins every Apply'd
    // message so its `ptr` field can be used as a stable lookup key;
    // once purged, the message can no longer be looked up and pinning
    // it is pure leak. Empirically this was the dominant gcRoot
    // accumulation source (~100 entries/battle), eventually making
    // IdunRunner.Initialize fail past ~900 pinned handles.
    const kept: typeof state.log = [];
    const removedEntries: typeof state.log = [];
    for (const e of state.log) {
        if ((e.originRunnerId ?? "live") === buildId) {
            removedEntries.push(e);
        } else {
            kept.push(e);
        }
    }
    state.log = kept;
    for (const e of removedEntries) {
        if (!e.ptr) continue;
        try { gcRoot.remove(ptr(e.ptr)); } catch { /* best effort */ }
    }
    const removed = removedEntries.length;
    if (removed > 0) {
        simState.lastSyncedLogIdx = Math.min(
            simState.lastSyncedLogIdx, state.log.length);
    }
    return removed;
}

/** Dispose the mirror if its source matches the given build runnerId.
 * Used by the recorder when a build runner's match ends so we don't
 * leave a stale mirror tied to a runner that's about to be disposed.
 * Idempotent. */
export function disposeMirrorIfFromBuild(buildId: number): boolean {
    if (!simState.mirror) return false;
    if (simState.mirror.source.kind !== "build") return false;
    if (simState.mirror.source.runnerId !== buildId) return false;
    while (applyStack.length > 0
        && applyStack[applyStack.length - 1].role === "mirror") {
        popApply();
    }
    disposeMirror();
    simState.revision++;
    send({
        t: "sim_state_changed",
        revision: simState.revision,
        syncedToLogIdx: simState.lastSyncedLogIdx,
        liveLogIdx: state.log.length,
    });
    return true;
}

/** Apply a single live log entry to the mirror. Called by recorder onLeave.
 * No-op if no mirror or if mirror has diverged. */
export function applyToMirror(): void {
    if (simState.mirror === null || simState.diverged) return;
    // If the live runner switched (new battle) since we built the mirror,
    // drop it cleanly — the new battle's messages would be incoherent on
    // the old config's runner. The user can rebuild on demand.
    syncMirrorWithSource();
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

    // Only replay entries whose origin matches our mirror's source —
    // a mirror of build #3 mustn't replay live messages, and vice versa.
    const targetOrigin: "live" | number = mirror.source.kind === "live"
        ? "live" : mirror.source.runnerId;
    let hadError = false;
    state.replayingOnMirror = true;
    let lastIdx = -1;
    let lastCls = "?";
    let lastSrc = "?";
    try {
        for (let i = fromIdx; i < toIdx; i++) {
            const entry = state.log[i];
            if ((entry.originRunnerId ?? "live") !== targetOrigin) continue;
            lastIdx = i;
            lastCls = entry.cls;
            lastSrc = entry.src;
            const stats = newReplayStats();
            replayEntryOnMirror(mirror, entry, stats);
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
    /** Source the current mirror was built from — null when no mirror.
     * Lets the runners panel highlight the row currently being mirrored. */
    mirrorSource: MirrorSource | null;
    /** Stage of the mirror's SOURCE runner (live or build) — null when no
     * mirror. Lets the front gate AUTO-PLAY/END-TURN: anything ≠ 1 (Running)
     * means the source runner is finished or pre-start, so dispatching on
     * it makes no sense. */
    mirrorSourceStage: number | null;
    /** Stage of the (single) build runner — null when no build registered.
     * Lets the front gate "is the build engaged?" for the BUILD viewer tile. */
    buildStage: number | null;
    /** True when an in-game live battle is engaged. Lets the front render a
     * synthetic "Live battle" row in the runners panel. */
    hasLive: boolean;
}

function readStatus(): StatusReport {
    const mirrorSource = simState.mirror?.source ?? null;
    // Resolve the mirror's source runner and read its stage so the front
    // can gate AUTO-PLAY/END-TURN even when the source is finished
    // (e.g. live battle ended while a mirror still exists).
    let mirrorSourceStage: number | null = null;
    if (simState.mirror) {
        const { runner: source } = resolveSource(simState.mirror.source);
        if (source) {
            try {
                const sp = source.add(runnerOff.state).readPointer();
                if (!sp.isNull()) {
                    mirrorSourceStage = readBattleStatus(sp).stage ?? null;
                }
            } catch { /* leave null */ }
        }
    }
    // hasLive default = "we have a runner pointer". We narrow this below to
    // "we have a runner AND its stage is Running" — covers the case where
    // Tacticus keeps the runner reference alive after the battle has ended
    // (stage went Finished). Without this narrowing the LIVE row would
    // linger in the runners panel forever.
    let hasLive = state.liveRunner !== null;
    // Build stage — single-build policy means at most one in the registry.
    let buildStage: number | null = null;
    try {
        const builds = listRegistryRunners();
        if (builds.length > 0) {
            const buildEntry = getRegistryRunner(builds[0].runnerId);
            const sp = buildEntry.runner.add(runnerOff.state).readPointer();
            if (!sp.isNull()) {
                buildStage = readBattleStatus(sp).stage ?? null;
            }
        }
    } catch { /* leave null */ }
    const base = {
        built: simState.mirror !== null,
        lastSyncedLogIdx: simState.lastSyncedLogIdx,
        logSize: state.log.length,
        diverged: simState.diverged,
        divergedReason: simState.divergedReason,
        revision: simState.revision,
        mirrorSource, mirrorSourceStage, buildStage, hasLive,
    };
    const live = state.liveRunner;
    if (!live) {
        return {
            ...base,
            liveStage: null, liveStageName: null,
            liveCurrentPlayer: null,
            isAiRunning: false,
            canMirror: false,
            blockReason: "no live runner",
        };
    }
    let liveStatePtr: NativePointer;
    try { liveStatePtr = live.add(runnerOff.state).readPointer(); }
    catch {
        return {
            ...base,
            liveStage: null, liveStageName: null,
            liveCurrentPlayer: null, isAiRunning: false,
            canMirror: false,
            blockReason: "live runner _state unreadable",
        };
    }
    if (liveStatePtr.isNull()) {
        return {
            ...base,
            liveStage: null, liveStageName: null,
            liveCurrentPlayer: null, isAiRunning: false,
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

    // Narrow hasLive to "actually engaged in a battle" — Tacticus may keep
    // the runner pointer alive after the battle ends (stage = Finished),
    // and we don't want the LIVE row to linger.
    hasLive = status.stage === 1;
    return {
        ...base,
        hasLive,
        liveStage: status.stage,
        liveStageName: status.stageName,
        liveCurrentPlayer: status.currentTurnPlayer,
        isAiRunning,
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
    state.mirrorRunner = null;
    state.mirrorAiControl = null;
}

/** Resolve a MirrorSource to its current runner pointer + readable name. */
function resolveSource(src: MirrorSource): {
    runner: NativePointer | null; label: string;
} {
    if (src.kind === "live") {
        return { runner: state.liveRunner, label: "live" };
    }
    try {
        const entry = getRegistryRunner(src.runnerId);
        return { runner: entry.runner, label: "build#" + src.runnerId };
    } catch { return { runner: null, label: "build#" + src.runnerId }; }
}

function buildMirrorFromSource(src: MirrorSource): MirrorHandle {
    const { runner: source, label } = resolveSource(src);
    if (!source) {
        throw new Error("source runner not available: " + label);
    }
    const cfg = source.add(runnerOff.config).readPointer();
    if (cfg.isNull()) throw new Error(label + " runner config null");
    // Set the flag so ai-utility-trace can identify which DefaultGroupOperator
    // ctor (and thus UtilitiesDatabase) belongs to the mirror — we only want
    // to instrument the mirror's, not the source runner's.
    state.buildingMirror = true;
    let handle;
    try {
        handle = buildRunner(cfg);
    } finally {
        state.buildingMirror = false;
    }
    state.mirrorRunner = handle.runner;
    state.mirrorAiControl = handle.innerAiControl;
    return {
        runner: handle.runner,
        aiControl: handle.innerAiControl,
        seed: handle.seed,
        builtAt: Date.now(),
        source: src,
        builtFromRunner: source,
    };
}

/** Detect a stale mirror — the source runner has switched (new live battle)
 * or been disposed (build dropped) — and tear it down. The recorder already
 * clears state.log on a live runner switch (main-pump.ts); for a build switch
 * the log persists but stays tagged with the old originRunnerId. */
function syncMirrorWithSource(): void {
    if (simState.mirror === null) return;
    const { runner: current } = resolveSource(simState.mirror.source);
    if (!current) {
        send({
            t: "sim_diverged",
            reason: "mirror source runner gone (live ended or build disposed)",
            atLogIdx: simState.lastSyncedLogIdx,
        });
        disposeMirror();
        return;
    }
    if (!simState.mirror.builtFromRunner.equals(current)) {
        send({
            t: "sim_diverged",
            reason: "mirror source runner switched — auto-reset",
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
    ctx.rpc.simMirror = (
        body?: { source?: "live" | "build"; runnerId?: number },
    ): Promise<unknown> => queueOnMainThread(() => {
        // Default source = live (back-compat with the existing "MIRROR NOW"
        // button which sent no body).
        const sourceKind = body?.source ?? "live";
        const src: MirrorSource = sourceKind === "build"
            ? { kind: "build", runnerId: Number(body?.runnerId ?? -1) }
            : { kind: "live" };
        if (src.kind === "build" && (src.runnerId < 0
            || !Number.isFinite(src.runnerId))) {
            return { ok: false, error: "build source needs a numeric runnerId" };
        }
        // Garde 1: "Live always required" — even mirroring a build needs an
        // in-game live to provide the host services / hooks context.
        if (!state.liveRunner) {
            return { ok: false, error: "no in-game live battle engaged — start one in Tacticus first" };
        }
        // Garde 2: source runner must be engaged (stage Running).
        const { runner: sourceRunner, label } = resolveSource(src);
        if (!sourceRunner) {
            return { ok: false, error: "source runner not available: " + label };
        }
        try {
            const stagePtr = sourceRunner.add(runnerOff.state).readPointer();
            if (stagePtr.isNull()) {
                return { ok: false,
                    error: label + " runner has no MatchState — not engaged" };
            }
            const stage = readBattleStatus(stagePtr).stage;
            if (stage !== 1) {
                return { ok: false,
                    error: label + " runner stage is "
                        + (readBattleStatus(stagePtr).stageName ?? stage)
                        + " — must be Running" };
            }
        } catch (e) {
            return { ok: false,
                error: "failed to read " + label + " stage: "
                    + (e as Error).message };
        }
        // Drop any prior mirror (whether stale, diverged, or fine — we
        // always rebuild for predictability).
        while (applyStack.length > 0
            && applyStack[applyStack.length - 1].role === "mirror") {
            popApply();
        }
        disposeMirror();

        const t0 = Date.now();
        try {
            simState.mirror = buildMirrorFromSource(src);
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
            const live = state.liveRunner;
            if (!live) return { ok: false, error: "no live runner" };
            const cfg = live.add(runnerOff.config).readPointer();
            if (cfg.isNull()) return { ok: false, error: "config null" };
            const json = serializeToJson(cfg);
            if (!json) return { ok: false, error: "serialize failed" };
            return { ok: true, bytes: json.length, json };
        });

    /** User-driven save of the live runner's BattleConfiguration into the
     * configs store. Only available on the live (in-game) runner — build
     * runners are NOT saveable through this path (they were created from a
     * stored config in the first place). Enriches the saved entry with the
     * last GameModeSource.LoadBattle observation (mode, campaignId,
     * locationIndex) cached by mode-source-capture. */
    ctx.rpc.simSaveLiveConfig = (): Promise<unknown> => queueOnMainThread(() => {
        const live = state.liveRunner;
        if (!live) return { ok: false, error: "no live runner" };
        const cfg = live.add(runnerOff.config).readPointer();
        if (cfg.isNull()) return { ok: false, error: "live config null" };
        const json = serializeToJson(cfg);
        if (!json) return { ok: false, error: "serialize failed" };
        const meta = state.lastModeSourceMeta;
        const id = meta
            ? `${meta.mode}:${meta.campaignId ?? ""}:${meta.locationIndex ?? ""}:${meta.ts}`
            : `LiveRunner:${Date.now()}`;

        // Bundle every captured message — required to reconstruct the runner
        // at the saved state via deserialize+Apply at load time. Each entry
        // carries (ns, cls) so we can resolve the class via findClassAnywhere
        // without owning-assembly knowledge, plus the PRNG snapshot taken
        // pre-apply on live (lets us restore the build runner's MT to the
        // same value before each Apply → deterministic re-run). top_boot
        // entries lack PRNG (the native Replay store doesn't snapshot) —
        // we still serialize them; replay determinism for those is best-
        // effort but matches the existing simDumpReplay behaviour.
        const messages: Array<{
            idx: number; src: string; cls: string; ns: string;
            unitId: number | null;
            prng: typeof state.log[number]["prng"];
            json: string | null;
        }> = [];
        let serializeErrors = 0, totalBytes = 0;
        for (const e of state.log) {
            const id = readMsgIdentity(ptr(e.ptr));
            let mjson: string | null = null;
            try { mjson = serializeToJson(ptr(e.ptr)); }
            catch { /* leave null */ }
            if (mjson === null) serializeErrors++;
            else totalBytes += mjson.length;
            messages.push({
                idx: e.idx, src: e.src, cls: id.cls, ns: id.ns,
                unitId: e.unitId, prng: e.prng, json: mjson,
            });
        }

        send({
            t: "captured_config",
            id,
            mode: meta?.mode ?? "LiveRunner",
            ts: Date.now(),
            bytes: json.length,
            campaignId: meta?.campaignId ?? null,
            locationIndex: meta?.locationIndex ?? null,
            json,
            messages,
            messageStats: {
                count: messages.length,
                serializeErrors,
                totalMessageBytes: totalBytes,
            },
        });
        return {
            ok: true, id,
            bytes: json.length,
            mode: meta?.mode ?? "LiveRunner",
            messageCount: messages.length,
            serializeErrors,
        };
    });

    /** Dump a fully replay-able snapshot of the current battle: config + seed
     * + every captured message (boot preamble + live + AI sub-messages) with
     * Newtonsoft serialization and per-message PRNG snapshot. The bundle is
     * sufficient to re-build a runner and replay deterministically up to the
     * current state, without needing the live game running. Heavy (config
     * alone ≈ 540 KB) but ran on demand at MIRROR NOW click. */
    ctx.rpc.simDumpReplay = (): Promise<unknown> => queueOnMainThread(() => {
        const live = state.liveRunner;
        if (!live) return { ok: false, error: "no live runner" };
        const cfg = live.add(runnerOff.config).readPointer();
        if (cfg.isNull()) return { ok: false, error: "config null" };
        const cfgJson = serializeToJson(cfg);
        if (!cfgJson) return { ok: false, error: "config serialize failed" };

        // Read the live runner's RngSeed from its native Replay object —
        // needed so a rebuild with this seed reproduces the same PRNG starting
        // point as the original battle. If we can't reach it (replay or
        // recorder missing), surface a warning but return seed=null and let
        // the caller fall back to per-message restoreMt.
        let seed: number | null = null;
        try {
            const recorder = live.add(runnerOff.replayRecorder).readPointer();
            if (!recorder.isNull() && getReplayMi
                && !getReplayMi.ptr.isNull()) {
                const replay = invokeMethod(
                    getReplayMi.info, recorder, null);
                if (!replay.isNull() && replayOff.rngSeed >= 0) {
                    seed = replay.add(replayOff.rngSeed).readS32();
                }
            }
        } catch { /* leave seed null */ }

        // Serialize each captured message via Newtonsoft. Skip on failure but
        // keep the entry with json=null so the caller sees the gap.
        const messages: Array<{
            idx: number; src: string; cls: string; ptr: string;
            unitId: number | null; ts: number;
            prng: typeof state.log[number]["prng"];
            json: string | null;
            jsonBytes: number;
        }> = [];
        let serializeErrors = 0, totalBytes = 0;
        for (const e of state.log) {
            let json: string | null = null;
            try { json = serializeToJson(ptr(e.ptr)); }
            catch { /* leave null */ }
            if (json === null) serializeErrors++;
            else totalBytes += json.length;
            messages.push({
                idx: e.idx, src: e.src, cls: e.cls, ptr: e.ptr,
                unitId: e.unitId, ts: e.ts,
                prng: e.prng, json,
                jsonBytes: json?.length ?? 0,
            });
        }
        return {
            ok: true,
            capturedAt: Date.now(),
            runnerPtr: live.toString(),
            seed,
            config: { bytes: cfgJson.length, json: cfgJson },
            messages,
            stats: {
                messageCount: messages.length,
                serializeErrors,
                totalMessageBytes: totalBytes,
                configBytes: cfgJson.length,
            },
        };
    });

    /** Lightweight status — used by the front to enable/disable buttons. */
    ctx.rpc.simStatus = (): Promise<unknown> =>
        queueOnMainThread(() => {
            // Detect runner switch on every status poll so the front sees
            // the auto-reset state without waiting for the next live message.
            syncMirrorWithSource();
            return readStatus();
        });

    /** Read the current mirror matchState + a live↔mirror compare summary.
     * Returns 404-shaped {ok:false} if no mirror exists. */
    ctx.rpc.simGetState = (): Promise<unknown> => queueOnMainThread(() => {
        if (simState.mirror === null) {
            return { ok: false, error: "no mirror" };
        }
        // Compare against the mirror's actual SOURCE — for a build mirror
        // we'd otherwise compare against the live runner and report a
        // permanent divergence. resolveSource → live or build runner.
        const { runner: source, label } = resolveSource(simState.mirror.source);
        if (!source) return { ok: false, error: "source gone: " + label };
        const sourceStatePtr = source.add(runnerOff.state).readPointer();
        const mirrorStatePtr = simState.mirror.runner
            .add(runnerOff.state).readPointer();
        if (sourceStatePtr.isNull() || mirrorStatePtr.isNull()) {
            return { ok: false, error: "state pointer null" };
        }
        const mirrorProjection = projectMatchState(mirrorStatePtr);
        const compare = computeCompare(sourceStatePtr, mirrorStatePtr);
        return {
            ok: true,
            mirror: mirrorProjection,
            source: simState.mirror.source,
            sourceLabel: label,
            compare,
            diverged: simState.diverged,
            divergedReason: simState.divergedReason,
            revision: simState.revision,
        };
    });

    /** Dump per-entry log summary (no payload — just shape/type/prng-presence)
     * to debug live↔mirror divergence: lets us see if `top_boot` entries lack
     * PRNG snapshots, if `ai`/`humanAi` are present at all, if a long boot
     * preamble is followed by very few live messages, etc. */
    ctx.rpc.simDumpLog = (): Promise<unknown> => queueOnMainThread(() => {
        const counts: Record<string, number> = {};
        const prngMissing: Record<string, number> = {};
        const entries = state.log.map((e) => {
            counts[e.src] = (counts[e.src] ?? 0) + 1;
            if (!e.prng) prngMissing[e.src] = (prngMissing[e.src] ?? 0) + 1;
            return {
                idx: e.idx, src: e.src, cls: e.cls, unitId: e.unitId,
                hasPrng: e.prng !== null,
                turn: e.turn ?? null,
                events: e.events.length,
                originRunnerId: e.originRunnerId ?? null,
            };
        });
        return {
            ok: true,
            total: state.log.length,
            counts,
            prngMissing,
            entries,
        };
    });

    /** Dispatch a single EndTurnMessage on the SOURCE runner of the current
     * mirror. The recorder captures it and the mirror auto-syncs.
     * Symmetric for live and build:
     *
     *   - build source → source build advances, mirror follows.
     *   - live source → live runner advances, mirror follows. Tacticus' UI
     *     (turn-transition animations) doesn't play because we skipped the
     *     UI input chain, but no crash — only cosmetic.
     */
    ctx.rpc.simEndTurn = (): Promise<unknown> => queueOnMainThread(() => {
        if (!simState.mirror || simState.diverged) {
            return { ok: false, error: "no mirror or diverged" };
        }
        const klass = findClass("BattleLogicAssembly.dll",
            "IdunBattle.Messages", "EndTurnMessage");
        if (!klass) {
            return { ok: false, error: "EndTurnMessage class not found" };
        }
        if (!runnerApplyMi) {
            return { ok: false, error: "runner.Apply not resolved" };
        }
        let targetRunner: NativePointer;
        let targetLabel: string;
        if (simState.mirror.source.kind === "build") {
            const runnerId = simState.mirror.source.runnerId;
            try {
                const entry = getRegistryRunner(runnerId);
                targetRunner = entry.runner;
            } catch (e) {
                return { ok: false,
                    error: "build runner gone: " + (e as Error).message };
            }
            targetLabel = "build#" + runnerId;
        } else {
            if (!state.liveRunner) {
                return { ok: false, error: "live runner gone" };
            }
            targetRunner = state.liveRunner;
            targetLabel = "live";
        }
        if (targetRunner.isNull()) {
            return { ok: false, error: "target runner null" };
        }
        // Diag — capture state before and after so we can confirm the
        // dispatch actually advanced the runner (and that the recorder
        // captured the apply).
        const readPlayer = (r: NativePointer): number => {
            try {
                const sp = r.add(runnerOff.state).readPointer();
                if (sp.isNull()) return -1;
                return readBattleStatus(sp).currentTurnPlayer ?? -1;
            } catch { return -1; }
        };
        const playerBefore = readPlayer(targetRunner);
        const logSizeBefore = state.log.length;
        try {
            const msg = il2cpp_object_new(klass) as NativePointer;
            if (msg.isNull()) {
                return { ok: false, error: "il2cpp_object_new returned null" };
            }
            gcRoot.add(msg);
            const ctor = findCtorByParamCount(klass, 0);
            if (ctor) invokeMethod(ctor.info, msg, null);
            invokeMethod(runnerApplyMi.info, targetRunner, [msg]);
        } catch (e) {
            return { ok: false,
                error: "dispatch failed: " + (e as Error).message };
        }
        const playerAfter = readPlayer(targetRunner);
        const logSizeAfter = state.log.length;
        send({
            t: "diag",
            msg: "[sim] simEndTurn · target=" + targetLabel
                + " · player " + playerBefore + " → " + playerAfter
                + " · logSize " + logSizeBefore + " → " + logSizeAfter,
        });
        return {
            ok: true, target: targetLabel,
            playerBefore, playerAfter,
            logSizeBefore, logSizeAfter,
            captured: logSizeAfter > logSizeBefore,
            advanced: playerAfter !== playerBefore,
        };
    });

    /** One auto-play step on a build-source mirror: dispatches a single
     * CheatRunAIMessage on the build runner. The active team (whoever's
     * turn it is) gets played by the game's own AI. Returns `advanced=false`
     * when the loop should stop (mirror source isn't a build, build is no
     * longer Running, or anything went wrong). The front calls this in a
     * loop, debouncing with a small delay so the recorder + auto-mirror
     * have time to apply each batch of messages onto the mirror. */
    ctx.rpc.simAutoPlayStep = (): Promise<unknown> => queueOnMainThread(() => {
        if (!simState.mirror || simState.diverged) {
            return { ok: true, advanced: false, reason: "no mirror or diverged" };
        }
        // Determine target runner — symmetric for live and build.
        let buildRunner: NativePointer;
        let label: string;
        if (simState.mirror.source.kind === "build") {
            const runnerId = simState.mirror.source.runnerId;
            try {
                const entry = getRegistryRunner(runnerId);
                buildRunner = entry.runner;
            } catch (e) {
                return { ok: true, advanced: false,
                    reason: "build runner gone: " + (e as Error).message };
            }
            label = "build#" + runnerId;
        } else {
            if (!state.liveRunner) {
                return { ok: true, advanced: false, reason: "live runner gone" };
            }
            buildRunner = state.liveRunner;
            label = "live";
        }
        if (buildRunner.isNull()) {
            return { ok: true, advanced: false, reason: label + " runner null" };
        }
        // Stage gate — don't dispatch on a finished or pre-start runner.
        let stage = -1;
        try {
            const sp = buildRunner.add(runnerOff.state).readPointer();
            if (!sp.isNull()) stage = readBattleStatus(sp).stage ?? -1;
        } catch { /* leave -1 */ }
        if (stage !== 1) {
            return { ok: true, advanced: false,
                reason: "build stage " + stage + " (not Running)",
                stage };
        }
        // Dispatch one CheatRunAIMessage — plays the active team.
        if (!cheatRunAiClass) {
            return { ok: false, advanced: false,
                reason: "CheatRunAIMessage class not resolved" };
        }
        if (!runnerApplyMi) {
            return { ok: false, advanced: false,
                reason: "runner.Apply not resolved" };
        }
        let stageAfter = stage;
        try {
            const msg = il2cpp_object_new(cheatRunAiClass) as NativePointer;
            if (msg.isNull()) {
                return { ok: false, advanced: false,
                    reason: "il2cpp_object_new returned null" };
            }
            gcRoot.add(msg);
            const ctor = findCtorByParamCount(cheatRunAiClass, 0);
            if (ctor) invokeMethod(ctor.info, msg, null);
            invokeMethod(runnerApplyMi.info, buildRunner, [msg]);
            try {
                const sp = buildRunner.add(runnerOff.state).readPointer();
                if (!sp.isNull()) stageAfter = readBattleStatus(sp).stage ?? -1;
            } catch { /* keep stage */ }
        } catch (e) {
            return { ok: false, advanced: false,
                reason: "dispatch failed: " + (e as Error).message,
                stage };
        }
        return {
            ok: true, advanced: stageAfter === 1,
            stage, stageAfter, target: label,
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
        const priorSource = simState.mirror?.source ?? { kind: "live" } as MirrorSource;
        disposeMirror();
        let m: MirrorHandle;
        try {
            m = buildMirrorFromSource(priorSource);
        } catch (e) {
            return { ok: false, error: "build failed: " + (e as Error).message };
        }
        simState.mirror = m;
        const stats = catchUp(m, 0, target);
        simState.revision++;
        send({
            t: "sim_state_changed",
            revision: simState.revision,
            syncedToLogIdx: simState.lastSyncedLogIdx,
            liveLogIdx: state.log.length,
        });
        return {
            ok: true, builtAt: m.builtAt, seed: m.seed,
            syncedToLogIdx: simState.lastSyncedLogIdx,
            replayStats: stats,
            revision: simState.revision,
        };
    });

    /** "AI plays on mirror, then commits to live" flow.
     *
     * Phase 0 — gates: mirror built, live in Running stage, no AI running on
     * live, mirror sync (lag === 0), live current player == human (we don't
     * preempt an ongoing AI turn).
     *
     * Phase 1 — capture: instantiate a CheatRunAIMessage, set
     * captureMirrorMessages=true so the recorder routes any apply on the
     * mirror runner into mirrorTurnQueue with a mirror-PRNG snapshot per msg.
     * Apply CheatRunAIMessage on the mirror — if its inner AI succeeds, it
     * dispatches a sequence of MoveUnitMessage / ActiveAbilityMessage etc.
     * which we capture.
     *
     * Phase 2 — commit: for each captured msg, restore live PRNG to the
     * mirror snapshot taken pre-apply, push a "live" apply frame manually,
     * invoke runner.Apply on live, pop the frame, diff events live↔mirror.
     *
     * Returns counts + per-msg event divergences. The live runner is now
     * advanced as if the AI played the human turn; the recorder's auto-mirror
     * will re-sync any subsequent live activity. */
    ctx.rpc.simRunAiTurn = (): Promise<unknown> => queueOnMainThread(() => {
        // Gates
        if (!simState.mirror) {
            return { ok: false, error: "no mirror — click MIRROR NOW first" };
        }
        if (simState.diverged) {
            return { ok: false, error: "mirror diverged — reset first" };
        }
        // simRunAiTurn commits AI moves back onto the LIVE in-game runner —
        // doesn't make sense for a build mirror (Étape 3 will add a build-
        // local auto-play that dispatches CheatRunAIMessage on the build
        // runner directly).
        if (simState.mirror.source.kind !== "live") {
            return { ok: false,
                error: "simRunAiTurn only works on a live-source mirror" };
        }
        const live = state.liveRunner;
        if (!live) return { ok: false, error: "no live runner" };
        const liveStatePtr = live.add(runnerOff.state).readPointer();
        if (liveStatePtr.isNull()) {
            return { ok: false, error: "live state null" };
        }
        const liveStatus = readBattleStatus(liveStatePtr);
        if (liveStatus.stage !== 1) {
            return { ok: false, error: "live not Running (stage="
                + (liveStatus.stageName ?? liveStatus.stage) + ")" };
        }
        let isAiRunning = false;
        try { isAiRunning = liveStatePtr.add(0x58).readU8() !== 0; }
        catch { /* keep false */ }
        if (isAiRunning) {
            return { ok: false, error: "AI is running on live — wait" };
        }
        if (state.log.length !== simState.lastSyncedLogIdx) {
            return { ok: false, error: "mirror lagging behind live — sync first" };
        }

        // Pre-build CheatRunAIMessage instance (parameterless).
        if (!cheatRunAiClass) {
            return { ok: false, error: "CheatRunAIMessage class not resolved" };
        }
        let cheatMsg: NativePointer;
        try {
            cheatMsg = il2cpp_object_new(cheatRunAiClass) as NativePointer;
            if (cheatMsg.isNull()) throw new Error("il2cpp_object_new returned null");
            const ctor = findCtorByParamCount(cheatRunAiClass, 0);
            if (ctor) invokeMethod(ctor.info, cheatMsg, null);
            // Pin until end of flow; gcRoot.add is idempotent.
            gcRoot.add(cheatMsg);
        } catch (e) {
            return { ok: false,
                error: "build CheatRunAIMessage failed: " + (e as Error).message };
        }

        const mirror = simState.mirror;
        const liveMtStart = live.add(runnerOff.rng).readPointer();
        const liveMt = resolveMt(liveMtStart);

        // Phase 1: capture
        send({ t: "diag", msg: "[sim] simRunAiTurn · Phase 1 enter" });
        // Résidu d'un run précédent : dépingle avant de vider (cf. game/state.ts).
        clearMirrorQueueUnpinned();
        state.captureMirrorMessages = true;
        const t0 = Date.now();
        let phase1Err: string | null = null;
        while (applyStack.length > 0
            && applyStack[applyStack.length - 1].role === "mirror") {
            popApply();
        }
        try {
            invokeMethod(runnerApplyMi!.info, mirror.runner, [cheatMsg]);
        } catch (e) {
            phase1Err = (e as Error).message;
            send({
                t: "diag",
                msg: "[sim] simRunAiTurn · Phase 1 failed: " + phase1Err,
            });
        } finally {
            state.captureMirrorMessages = false;
            while (applyStack.length > 0
                && applyStack[applyStack.length - 1].role === "mirror") {
                popApply();
            }
        }
        const phase1Ms = Date.now() - t0;
        const captured = state.mirrorTurnQueue;
        state.mirrorTurnQueue = [];
        send({
            t: "diag",
            msg: "[sim] simRunAiTurn · Phase 1 exit · captured="
                + captured.length + " · ms=" + phase1Ms
                + (phase1Err ? " · err=" + phase1Err : ""),
        });

        if (phase1Err && captured.length === 0) {
            return {
                ok: false,
                error: "AI on mirror failed: " + phase1Err,
                phase1Ms,
            };
        }

        // Phase 2: commit each captured msg on live, diff events.
        // The recorder's live hooks fire on these manual applies (args[0] ===
        // liveRunner). Set replayingOnMirror=true so they skip — we don't
        // want a duplicate state.log entry, and we don't want auto-mirror
        // to recurse (the mirror already advanced during Phase 1).
        send({
            t: "diag",
            msg: "[sim] simRunAiTurn · Phase 2 enter · "
                + captured.length + " msgs to commit on live",
        });
        const t1 = Date.now();
        const liveCommits: Array<{
            idx: number; src: string; cls: string;
            unitId: number | null;
            liveEventsCount: number; mirrorEventsCount: number;
            divergent: boolean; firstDiff: string | null;
            err: string | null;
            /** Raw events for both sides — kept compact (kind, step/group,
             * entity, tags). Front can render side-by-side for inspection. */
            liveEvents: StreamEvent[];
            mirrorEvents: StreamEvent[];
        }> = [];
        let phase2Err: string | null = null;
        state.replayingOnMirror = true;
        try {
            for (let i = 0; i < captured.length; i++) {
                const m = captured[i];
                const liveEvents: StreamEvent[] = [];
                let err: string | null = null;
                try {
                    if (m.prng && liveMt) restoreMt(liveMt, m.prng);
                    pushApply("live", liveEvents);
                    try {
                        invokeMethod(runnerApplyMi!.info, live, [ptr(m.ptr)]);
                    } finally {
                        popApply();
                    }
                } catch (e) {
                    err = (e as Error).message;
                    phase2Err = phase2Err ?? err;
                    while (applyStack.length > 0
                        && applyStack[applyStack.length - 1].role === "live") {
                        popApply();
                    }
                }
                const diff = err
                    ? { divergent: true, firstDiff: "live AV: " + err }
                    : diffEvents(liveEvents, m.events);
                liveCommits.push({
                    idx: i, src: m.src, cls: m.cls, unitId: m.unitId,
                    liveEventsCount: liveEvents.length,
                    mirrorEventsCount: m.events.length,
                    divergent: diff.divergent,
                    firstDiff: diff.firstDiff,
                    err,
                    liveEvents,
                    mirrorEvents: m.events,
                });
            }
        } finally {
            state.replayingOnMirror = false;
            // Les messages capturés ont fini leur office (rejoués sur live) et
            // plus personne ne détient leur pointeur — le pin de
            // `captureMirrorMsg` deviendrait un handle orphelin. Même geste que
            // le dépinglage équilibré après chaque Apply (launch.ts).
            unpinEntries(captured);
        }
        const phase2Ms = Date.now() - t1;
        const phase2Divergent = liveCommits.filter((c) => c.divergent).length;
        send({
            t: "diag",
            msg: "[sim] simRunAiTurn · Phase 2 exit · committed="
                + liveCommits.length + " · divergent=" + phase2Divergent
                + " · ms=" + phase2Ms
                + (phase2Err ? " · err=" + phase2Err : ""),
        });

        // Realign mirror to live's new logSize. Each Phase-2 live apply was
        // applied OUTSIDE the recorder (captureMirrorMessages was false but
        // we routed via our own pushApply, not via the live recorder hook),
        // so state.log was NOT extended by these messages. The mirror's
        // matchstate already advanced through Phase 1. So:
        //   - lastSyncedLogIdx stays === log.length (still in sync)
        //   - mirror state == live state (modulo divergences in liveCommits)
        // No catchUp needed.
        simState.revision++;
        send({
            t: "sim_auto_play_complete",
            revision: simState.revision,
            messages: captured.length,
            divergences: liveCommits.filter((c) => c.divergent).length,
            phase1Ms, phase2Ms,
            phase1Err, phase2Err,
        });
        send({
            t: "sim_state_changed",
            revision: simState.revision,
            syncedToLogIdx: simState.lastSyncedLogIdx,
            liveLogIdx: state.log.length,
        });

        return {
            ok: true,
            phase1Ms, phase2Ms,
            messages: captured.length,
            phase1Err, phase2Err,
            commits: liveCommits,
        };
    });

    // ---------- Preview slot ----------
    // Distinct from build: NOT registered in runner-registry, NOT in
    // watchedRunners, NOT shown as a tile in the runners panel. Built
    // when the user clicks a saved-config row in the archive — used solely
    // to render the saved matchstate on the central board so the user can
    // inspect the saved state before committing to LOAD it as a BUILD.
    // Single slot — replaced/disposed on each rebuild.

    function disposePreview(): void {
        if (state.previewRunner) {
            try { gcRoot.remove(state.previewRunner); } catch { /* ignore */ }
            state.previewRunner = null;
        }
    }

    /** Build a preview runner from a saved bundle and project its
     * matchstate. The runner is NOT registered nor watched — only kept
     * alive via gcRoot so the matchstate stays readable until the next
     * rebuild or dispose. */
    ctx.rpc.simBuildPreview = (args: {
        configJson: string; messages: ReplayMessage[];
    }): Promise<unknown> => queueOnMainThread(() => {
        disposePreview();
        let result;
        try {
            result = buildRunnerAndReplay(args.configJson, args.messages);
        } catch (e) {
            return { ok: false, error: "build failed: " + (e as Error).message };
        }
        state.previewRunner = result.runner;
        let matchState = null;
        try {
            const sp = result.runner.add(runnerOff.state).readPointer();
            if (!sp.isNull()) matchState = projectMatchState(sp);
        } catch (e) {
            return { ok: false,
                error: "project failed: " + (e as Error).message };
        }
        return {
            ok: true,
            stage: result.stage,
            stats: result.stats,
            firstErrors: result.stats.errors.slice(0, 10),
            matchState,
        };
    });

    /** Re-project the existing preview's matchstate. Lets the front
     * refresh its render without rebuilding. */
    ctx.rpc.simGetPreviewState = (): Promise<unknown> => queueOnMainThread(() => {
        if (!state.previewRunner) return { ok: false, error: "no preview" };
        try {
            const sp = state.previewRunner.add(runnerOff.state).readPointer();
            if (sp.isNull()) return { ok: false, error: "preview state null" };
            return { ok: true, matchState: projectMatchState(sp) };
        } catch (e) {
            return { ok: false,
                error: "project failed: " + (e as Error).message };
        }
    });

    /** Drop the preview slot. Called when the user navigates away from
     * the saved-config tile or clicks LOAD (the BUILD path takes over). */
    ctx.rpc.simDisposePreview = (): Promise<unknown> => queueOnMainThread(() => {
        const had = state.previewRunner !== null;
        disposePreview();
        return { ok: true, disposed: had };
    });
}
