// IdunRunner class + offsets + standalone runner builder.
//
// The IdunRunner is the main game engine. A live runner is created by the
// game on battle start. We can also build an *isolated* standalone runner
// via its 2-arg ctor, catch it up to live by replaying messages, and use
// it as a sandbox to explore decisions without mutating the live state.

import {
    class_get_methods, findClass, findCtorByParamCount, findMethod,
    getFieldOffset, MethodRef, method_get_name, method_get_param_count, s,
} from "../il2cpp/helpers.js";
import { il2cpp_object_new, invokeMethod } from "../il2cpp/invoke.js";
import { gcRoot } from "../il2cpp/gc-root.js";

// --- IdunRunner class + offsets ---

export const runnerClass = findClass(
    "BattleLogicAssembly.dll", "IdunBattle.Runner", "IdunRunner");
if (!runnerClass) throw new Error("IdunRunner class not found");

export const runnerApplyMi = findMethod(runnerClass, "Apply");

/** Offsets inside an IdunRunner instance. */
export const runnerOff = {
    aiControl: getFieldOffset(runnerClass, "_aiControl"),
    replayRecorder: getFieldOffset(runnerClass, "_replayRecorder"),
    state: getFieldOffset(runnerClass, "_state"),
    logger: getFieldOffset(runnerClass, "_logger"),
    timeSource: getFieldOffset(runnerClass, "_timeSource"),
    config: getFieldOffset(runnerClass, "<Configuration>k__BackingField"),
    isInit: getFieldOffset(runnerClass, "_isInitialized"),
    rng: getFieldOffset(runnerClass, "_randomNumberGenerator"),
};

// Hardcoded offsets for service accessors used to steal the reporter from
// a live runner. Reporter is a NullBattleDataReporter shared by convention.
//   runner[192]           — OperationProcessor*
//   opProc[528]           — StartMatchOperation*
//   startMatchOp[48]      — IBattleDataReporter (null-object)
const RUNNER_OPPROC_OFF = 192;
const OPPROC_STARTMATCH_OFF = 528;
const STARTMATCH_REPORTER_OFF = 48;

// --- IdunRunnerOptions ---

export const idunRunnerOptionsClass = findClass(
    "BattleLogicAssembly.dll", "IdunBattle.Runner", "IdunRunnerOptions");
if (!idunRunnerOptionsClass) throw new Error("IdunRunnerOptions class not found");

export const idunRunnerOptionsCtor = findMethod(idunRunnerOptionsClass, ".ctor");

// --- Replay class (for seed) ---

export const replayClass = findClass(
    "BattleLogicAssembly.dll", "IdunBattleLogic.Replay", "Replay");
export const replayOff = replayClass ? {
    messages: getFieldOffset(replayClass, "Messages"),
    rngSeed: getFieldOffset(replayClass, "RngSeed"),
} : { messages: -1, rngSeed: -1 };

// --- ReplayRecorder.GetReplay — used to get the seed ---

const replayRecorderClass = findClass(
    "BattleLogicAssembly.dll", "IdunBattleLogic.Replay", "ReplayRecorder");
export const getReplayMi = replayRecorderClass
    ? findMethod(replayRecorderClass, "GetReplay") : null;

// --- IdunRunner Initialize overload with seed:int32 ---
// Signature: Initialize(BattleConfiguration, Int32 seed, ITimeSource,
//                       IdunRunnerOptions, IIdunLogger, IBattleDataReporter)

function findInitializeSeedOverload(): MethodRef | null {
    const lib = Process.findModuleByName("libil2cpp.so");
    if (!lib) return null;
    const expFn = (n: string): NativePointer => {
        const p = lib.findExportByName(n);
        if (p === null) throw new Error("libil2cpp export not found: " + n);
        return p;
    };
    const paramFn = new NativeFunction(
        expFn("il2cpp_method_get_param"), "pointer", ["pointer", "uint32"]);
    const nameFn = new NativeFunction(
        expFn("il2cpp_type_get_name"), "pointer", ["pointer"]);

    const it = Memory.alloc(Process.pointerSize);
    it.writePointer(ptr(0));
    let m: NativePointer;
    while (!(m = class_get_methods(runnerClass!, it) as NativePointer).isNull()) {
        if (s(method_get_name(m) as NativePointer) !== "Initialize") continue;
        if ((method_get_param_count(m) as number) !== 6) continue;
        const p1 = s(nameFn(paramFn(m, 1)) as NativePointer);
        if (p1.indexOf("Int32") >= 0) return { info: m, ptr: m.readPointer() };
    }
    return null;
}

export const initializeSeedMi = findInitializeSeedOverload();

// --- Standalone runner builder ---

export interface StandaloneRunner {
    standalone: NativePointer;
    innerAiControl: NativePointer;
    seed: number;
    replay: NativePointer;
    realLogger: NativePointer;
    realTimeSource: NativePointer;
    realConfig: NativePointer;
    realReporter: NativePointer;
}

/**
 * Build an isolated IdunRunner mirroring the live runner at time 0.
 *
 * Standalone (fresh IdunRunner via 2-arg ctor) is preferred over ReplayRunner:
 * ReplayRunner's ctor touches ReplayRecorder state that has been observed to
 * crash (`access violation 0x4`) on a second build in the same session.
 *
 * The live runner's sidecars (logger, timeSource, config, battleDataReporter)
 * are reused so standalone binds to the same context. Seed is taken from the
 * live Replay so PRNG state matches after Initialize.
 *
 * Caller is expected to catch the standalone up via `runner.Apply(msg)` for
 * each IInputMessage of interest, then use it as a sandbox.
 */
export function buildStandaloneRunner(
    liveRunner: NativePointer,
): StandaloneRunner {
    if (!runnerApplyMi) throw new Error("IdunRunner.Apply not found");
    if (!initializeSeedMi) throw new Error("Initialize(seed) overload not resolved");
    if (!idunRunnerOptionsCtor) throw new Error("IdunRunnerOptions ctor not resolved");
    if (!getReplayMi) throw new Error("ReplayRecorder.GetReplay not resolved");
    gcRoot.init();

    // Steal sidecars from live
    const realLogger = liveRunner.add(runnerOff.logger).readPointer();
    const realTimeSource = liveRunner.add(runnerOff.timeSource).readPointer();
    const realConfig = liveRunner.add(runnerOff.config).readPointer();
    const opProc = liveRunner.add(RUNNER_OPPROC_OFF).readPointer();
    if (opProc.isNull()) throw new Error("opProc null on live runner");
    const startMatchOp = opProc.add(OPPROC_STARTMATCH_OFF).readPointer();
    if (startMatchOp.isNull()) throw new Error("startMatchOp null on live runner");
    const realReporter = startMatchOp.add(STARTMATCH_REPORTER_OFF).readPointer();

    // Seed from live ReplayRecorder
    const recorder = liveRunner.add(runnerOff.replayRecorder).readPointer();
    if (recorder.isNull()) throw new Error("recorder null on live runner");
    const replay = invokeMethod(getReplayMi.info, recorder, null);
    if (replay.isNull()) throw new Error("GetReplay returned null");
    gcRoot.add(replay);
    const seed = replay.add(replayOff.rngSeed).readS32();

    // Fresh IdunRunner via 2-arg ctor: (BattleConfiguration, bool recordQuerySimRequests)
    // Use findCtorByParamCount(2) — findMethod(".ctor") returns the first
    // ctor by iteration order, which isn't guaranteed to be the 2-arg one.
    const ctor = findCtorByParamCount(runnerClass!, 2);
    if (!ctor) throw new Error("IdunRunner 2-arg ctor not found");
    const standalone = il2cpp_object_new(runnerClass!) as NativePointer;
    gcRoot.add(standalone);
    const boolFalseArg = Memory.alloc(1); boolFalseArg.writeU8(0);
    invokeMethod(ctor.info, standalone, [realConfig, boolFalseArg]);

    // Options: RecordReplay=false — lightweight, won't fight live's recorder
    const options = il2cpp_object_new(idunRunnerOptionsClass!) as NativePointer;
    gcRoot.add(options);
    invokeMethod(idunRunnerOptionsCtor.info, options, null);
    options.add(16).writeU8(0);

    // Initialize(config, seed, timeSource, options, logger, reporter)
    const seedArg = Memory.alloc(4); seedArg.writeS32(seed);
    invokeMethod(initializeSeedMi.info, standalone,
        [realConfig, seedArg, realTimeSource, options, realLogger, realReporter]);

    const innerAiControl = standalone.add(runnerOff.aiControl).readPointer();
    if (innerAiControl.isNull()) throw new Error("inner AiControl null after Initialize");

    return {
        standalone, innerAiControl, seed, replay,
        realLogger, realTimeSource, realConfig, realReporter,
    };
}
