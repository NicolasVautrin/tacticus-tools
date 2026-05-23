// compareBuilt — build built, replay full log, compare to live.
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
    buildRunner, runnerApplyMi, runnerOff,
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
function sendStateDump(runner: "live" | "built", statePtr: NativePointer): {
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
    ctx.rpc.compareBuilt = () => queueOnMainThread(() => {
        if (!state.liveRunner) throw new Error("no runner");
        const liveRunner = state.liveRunner;
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
        let built: ReturnType<typeof buildRunner> | undefined;
        const builtTrace: TraceEntry[] = [];

        try {
            tryStep("live snapshot", () => {
                livePrng = snapshotPrng(liveRunner);
                liveState = digestState(
                    liveRunner.add(runnerOff.state).readPointer());
                liveTurn = readTurnPlayer(
                    liveRunner.add(runnerOff.state).readPointer());
                return { prng: livePrng, state: liveState, turn: liveTurn };
            });

            tryStep("build built", () => {
                const cfg = liveRunner.add(runnerOff.config).readPointer();
                built = buildRunner(cfg);
                return {
                    seed: built.seed,
                    isInit: built.runner.add(runnerOff.isInit).readU8(),
                };
            });

            tryStep("dispatch log on built", () => {
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
                            built!.runner.add(runnerOff.state).readPointer()),
                    };
                    builtTrace.push(traceEntry);
                    pushApply("built", evts);
                    try {
                        invokeMethod(
                            runnerApplyMi!.info, built!.runner, [msgPtr]);
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
                        built!.runner.add(runnerOff.state).readPointer());
                }
                return stats;
            });

            let builtPrng: PrngSnap | undefined;
            let builtState: StateDigest | null = null;
            let builtTurn: number | null = null;
            tryStep("built snapshot", () => {
                builtPrng = snapshotPrng(built!.runner);
                builtState = digestState(
                    built!.runner.add(runnerOff.state).readPointer());
                builtTurn = readTurnPlayer(
                    built!.runner.add(runnerOff.state).readPointer());
                return {
                    prng: builtPrng,
                    state: builtState,
                    turn: builtTurn,
                };
            });

            tryStep("entity census", () => {
                const liveCensus = entityCensus(
                    liveRunner.add(runnerOff.state).readPointer());
                const builtCensus = entityCensus(
                    built!.runner.add(runnerOff.state).readPointer());
                result.liveCensus = liveCensus;
                result.builtCensus = builtCensus;
                return { live: liveCensus, built: builtCensus };
            });

            tryStep("push state dumps + event traces via send()", () => {
                const liveDump = sendStateDump(
                    "live", liveRunner.add(runnerOff.state).readPointer());
                const saDump = sendStateDump(
                    "built", built!.runner.add(runnerOff.state).readPointer());
                const liveTrace = state.log.map((e) => ({
                    logIdx: e.idx, src: e.src, cls: e.cls,
                    unitId: e.unitId ?? null,
                    events: e.events ?? [],
                }));
                send({ t: "event_trace", runner: "live", trace: liveTrace });
                send({ t: "event_trace", runner: "built", trace: builtTrace });
                return {
                    liveDump, builtDump: saDump,
                    liveTraceEntries: liveTrace.length,
                    builtTraceEntries: builtTrace.length,
                };
            });

            result.diff = {
                turnMatch: liveTurn === builtTurn,
                prngCountMatch: livePrng!.count === builtPrng!.count,
                prngCountDelta: builtPrng!.count - livePrng!.count,
                prngMtiMatch: livePrng!.mti === builtPrng!.mti,
                prngDigestMatch: livePrng!.digest === builtPrng!.digest,
                stateDigestMatch:
                    liveState !== null && builtState !== null &&
                    (liveState as StateDigest).digest === (builtState as StateDigest).digest,
                liveBytes: liveState !== null ? (liveState as StateDigest).bytes : null,
                builtBytes:
                    builtState !== null ? (builtState as StateDigest).bytes : null,
                bytesDelta:
                    liveState !== null && builtState !== null
                        ? (builtState as StateDigest).bytes - (liveState as StateDigest).bytes
                        : null,
            };
        } catch (e) {
            result.crashAt = step;
            result.err = (e as Error).message;
            // Clear any dangling built frame
            while (
                applyStack.length > 0 &&
                applyStack[applyStack.length - 1].role === "built"
            ) popApply();
        }
        return result;
    });
}

// Suppress unused import warnings — msEntitiesOff + EntityType used via
// match-state helpers, but keeping them here for clarity in compare.
void msEntitiesOff; void EntityType;
