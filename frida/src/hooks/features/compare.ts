// compareStandalone — build standalone, replay full log, compare to live.
//
// Sends full state dumps + per-trigger event traces to the host via
// send() (written to logs/run-N.jsonl) for offline diffing.
//
// Reports PRNG digest, state digest, bytes delta, turn match, and
// entity census for both runners.

import { invokeMethod } from "../il2cpp/invoke.js";
import { class_get_name, s } from "../il2cpp/helpers.js";
import { serializeToJson } from "../il2cpp/serializer.js";
import {
    buildStandaloneRunner, runnerApplyMi, runnerOff,
} from "../game/runner.js";
import {
    digestState, entityCensus, EntityType, msEntitiesOff,
    readTurnPlayer, StateDigest,
} from "../game/match-state.js";
import { applyStack, pushApply, popApply, StreamEvent } from "../game/apply-stack.js";
import { state } from "../game/state.js";
import { queueOnMainThread } from "../runtime/queue.js";
import { Ctx } from "../controller.js";

interface PrngSnap {
    seed: number;
    count: number;
    mti: number;
    digest: string;
}

/** FNV-1a digest of a pointer's MT state — walks wrappers up to 4 hops. */
function snapshotPrng(runnerPtr: NativePointer): PrngSnap {
    let mt = runnerPtr.add(runnerOff.rng).readPointer();
    for (let hop = 0; hop < 4; hop++) {
        if (s(class_get_name(mt.readPointer()) as NativePointer)
            .indexOf("MersenneTwister") >= 0) break;
        const n = mt.add(16).readPointer();
        if (n.isNull() || n.equals(mt)) break;
        mt = n;
    }
    const arr = mt.add(32).readPointer();
    const len = arr.isNull() ? 0 : arr.add(0x18).readS32();
    let h = 2166136261 >>> 0;
    for (let i = 0; i < len; i++) {
        const w = arr.add(0x20 + i * 4).readU32() >>> 0;
        h = Math.imul(h ^ (w & 0xff), 16777619) >>> 0;
        h = Math.imul(h ^ ((w >>> 8) & 0xff), 16777619) >>> 0;
        h = Math.imul(h ^ ((w >>> 16) & 0xff), 16777619) >>> 0;
        h = Math.imul(h ^ ((w >>> 24) & 0xff), 16777619) >>> 0;
    }
    return {
        seed: mt.add(16).readS32(),
        count: mt.add(20).readS32(),
        mti: mt.add(40).readS32(),
        digest: "0x" + h.toString(16),
    };
}

/** Dump serialized state to the host via send(). Returns size on success. */
function sendStateDump(runner: "live" | "standalone", statePtr: NativePointer): {
    bytes?: number; err?: string;
} {
    if (statePtr.isNull()) return { err: "state null" };
    const str = serializeToJson(statePtr);
    if (!str) return { err: "serialize failed" };
    send({ t: "state_dump", runner, bytes: str.length, json: str });
    return { bytes: str.length };
}

interface TraceEntry {
    logIdx: number;
    src: string;
    cls: string;
    unitId: number | null;
    events: StreamEvent[];
    turnBefore?: number | null;
    turnAfter?: number | null;
}

export function register(ctx: Ctx): void {
    ctx.rpc.compareStandalone = () => queueOnMainThread(() => {
        if (!state.runnerInstance) throw new Error("no runner");
        const liveRunner = state.runnerInstance;
        const result: Record<string, unknown> & { phases: unknown[]; diff?: unknown } = {
            phases: [],
        };
        let step = "start";
        const tryStep = <T>(name: string, fn: () => T): T => {
            step = name;
            try {
                const r = fn();
                result.phases.push({ step: name, ...((r as object) ?? {}) });
                return r;
            } catch (e) {
                result.phases.push({ step: name, err: (e as Error).message });
                throw e;
            }
        };

        let livePrng: PrngSnap | undefined;
        let liveState: StateDigest | null = null;
        let liveTurn: number | null = null;
        let built: ReturnType<typeof buildStandaloneRunner> | undefined;
        const standaloneTrace: TraceEntry[] = [];

        try {
            tryStep("live snapshot", () => {
                livePrng = snapshotPrng(liveRunner);
                liveState = digestState(
                    liveRunner.add(runnerOff.state).readPointer());
                liveTurn = readTurnPlayer(
                    liveRunner.add(runnerOff.state).readPointer());
                return { prng: livePrng, state: liveState, turn: liveTurn };
            });

            tryStep("build standalone", () => {
                built = buildStandaloneRunner(liveRunner);
                return {
                    seed: built.seed,
                    isInit: built.standalone.add(runnerOff.isInit).readU8(),
                };
            });

            tryStep("dispatch log on standalone", () => {
                const stats = {
                    top: 0, top_boot: 0, ai: 0, humanAi: 0,
                    skippedCheatRunAi: 0, errors: [] as unknown[],
                };
                for (let i = 0; i < state.log.length; i++) {
                    const e = state.log[i];
                    const msgPtr = ptr(e.ptr);
                    if ((e.src === "top" || e.src === "top_boot") &&
                        e.cls === "CheatRunAIMessage") {
                        stats.skippedCheatRunAi++;
                        continue;
                    }
                    const evts: StreamEvent[] = [];
                    const traceEntry: TraceEntry = {
                        logIdx: i, src: e.src, cls: e.cls,
                        unitId: e.unitId, events: evts,
                        turnBefore: readTurnPlayer(
                            built!.standalone.add(runnerOff.state).readPointer()),
                    };
                    standaloneTrace.push(traceEntry);
                    pushApply("standalone", evts);
                    try {
                        invokeMethod(
                            runnerApplyMi!.info, built!.standalone, [msgPtr]);
                        stats[e.src]++;
                    } catch (ex) {
                        stats.errors.push({
                            i, src: e.src, cls: e.cls,
                            unitId: e.unitId,
                            turnBefore: traceEntry.turnBefore,
                            err: (ex as Error).message,
                        });
                        if (stats.errors.length >= 3) { popApply(); break; }
                    }
                    popApply();
                    traceEntry.turnAfter = readTurnPlayer(
                        built!.standalone.add(runnerOff.state).readPointer());
                }
                return stats;
            });

            let standalonePrng: PrngSnap | undefined;
            let standaloneState: StateDigest | null = null;
            let standaloneTurn: number | null = null;
            tryStep("standalone snapshot", () => {
                standalonePrng = snapshotPrng(built!.standalone);
                standaloneState = digestState(
                    built!.standalone.add(runnerOff.state).readPointer());
                standaloneTurn = readTurnPlayer(
                    built!.standalone.add(runnerOff.state).readPointer());
                return {
                    prng: standalonePrng,
                    state: standaloneState,
                    turn: standaloneTurn,
                };
            });

            tryStep("entity census", () => {
                const liveCensus = entityCensus(
                    liveRunner.add(runnerOff.state).readPointer());
                const standaloneCensus = entityCensus(
                    built!.standalone.add(runnerOff.state).readPointer());
                result.liveCensus = liveCensus;
                result.standaloneCensus = standaloneCensus;
                return { live: liveCensus, standalone: standaloneCensus };
            });

            tryStep("push state dumps + event traces via send()", () => {
                const liveDump = sendStateDump(
                    "live", liveRunner.add(runnerOff.state).readPointer());
                const saDump = sendStateDump(
                    "standalone", built!.standalone.add(runnerOff.state).readPointer());
                const liveTrace = state.log.map((e) => ({
                    logIdx: e.idx, src: e.src, cls: e.cls,
                    unitId: e.unitId ?? null,
                    events: e.events ?? [],
                }));
                send({ t: "event_trace", runner: "live", trace: liveTrace });
                send({ t: "event_trace", runner: "standalone", trace: standaloneTrace });
                return {
                    liveDump, standaloneDump: saDump,
                    liveTraceEntries: liveTrace.length,
                    standaloneTraceEntries: standaloneTrace.length,
                };
            });

            result.diff = {
                turnMatch: liveTurn === standaloneTurn,
                prngCountMatch: livePrng!.count === standalonePrng!.count,
                prngCountDelta: standalonePrng!.count - livePrng!.count,
                prngMtiMatch: livePrng!.mti === standalonePrng!.mti,
                prngDigestMatch: livePrng!.digest === standalonePrng!.digest,
                stateDigestMatch:
                    liveState !== null && standaloneState !== null &&
                    (liveState as StateDigest).digest === (standaloneState as StateDigest).digest,
                liveBytes: liveState !== null ? (liveState as StateDigest).bytes : null,
                standaloneBytes:
                    standaloneState !== null ? (standaloneState as StateDigest).bytes : null,
                bytesDelta:
                    liveState !== null && standaloneState !== null
                        ? (standaloneState as StateDigest).bytes - (liveState as StateDigest).bytes
                        : null,
            };
        } catch (e) {
            result.crashAt = step;
            result.err = (e as Error).message;
            // Clear any dangling standalone frame
            while (
                applyStack.length > 0 &&
                applyStack[applyStack.length - 1].role === "standalone"
            ) popApply();
        }
        return result;
    });
}

// Suppress unused import warnings — msEntitiesOff + EntityType used via
// match-state helpers, but keeping them here for clarity in compare.
void msEntitiesOff; void EntityType;
