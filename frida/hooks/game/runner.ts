// IdunRunner class + offsets + runner builder.
//
// The IdunRunner is the main game engine. A live runner is created by the
// game on battle start. We can also build an *isolated* runner
// via its 2-arg ctor with fresh null-object sidecars, and use it as a
// sandbox to explore decisions without mutating the live state.

import {
    class_get_methods, findClass, findClassAnywhere,
    findCtorByParamCount, findMethod, getFieldOffset, IL2CPP_MODULE_NAME,
    MethodRef, method_get_name, method_get_param_count, methodEntry, s,
} from "../il2cpp/helpers.js";
import { il2cpp_object_new, invokeMethod } from "../il2cpp/invoke.js";
import { gcRoot } from "../il2cpp/gc-root.js";

// --- IdunRunner class + offsets ---

export const runnerClass = findClass(
    "BattleLogicAssembly.dll", "IdunBattle.Runner", "IdunRunner");
if (!runnerClass) throw new Error("IdunRunner class not found");

export const runnerApplyMi = findMethod(runnerClass, "Apply");
export const runnerStartMatchMi = findMethod(runnerClass, "StartMatch");

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

// --- Null-object stub classes for sidecar services.
// All three have parameterless ctors and implement the required interfaces,
// so we can instantiate fresh sidecars per runner without having
// to capture them from a live battle.

const nullLoggerClass = findClassAnywhere("idun.Idun.Source.Shared", "NullLogger");
if (!nullLoggerClass) throw new Error("NullLogger class not found");
const nullLoggerCtor = findCtorByParamCount(nullLoggerClass, 0);
if (!nullLoggerCtor) throw new Error("NullLogger parameterless ctor not found");

const timeSourceClass = findClassAnywhere(
    "idun.Idun.Source.Shared.Time", "TimeSource");
if (!timeSourceClass) throw new Error("TimeSource class not found");
const timeSourceCtor = findCtorByParamCount(timeSourceClass, 0);
if (!timeSourceCtor) throw new Error("TimeSource parameterless ctor not found");

const nullReporterClass = findClassAnywhere(
    "idun.Shared.Battle.BattleDataReporters", "NullBattleDataReporter");
if (!nullReporterClass) throw new Error("NullBattleDataReporter class not found");
const nullReporterCtor = findCtorByParamCount(nullReporterClass, 0);
if (!nullReporterCtor) throw new Error("NullBattleDataReporter parameterless ctor not found");

function instantiate(klass: NativePointer, ctor: MethodRef): NativePointer {
    const obj = il2cpp_object_new(klass) as NativePointer;
    if (obj.isNull()) throw new Error("il2cpp_object_new returned null");
    invokeMethod(ctor.info, obj, null);
    return obj;
    // NOTE: no gcRoot.add here. Callers that hand these to the runner via
    // Initialize() rely on the runner's own managed fields (`_logger`,
    // `_timeSource`, etc.) to keep them alive. Only the runner itself is pinned.
}

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
    const lib = Process.findModuleByName(IL2CPP_MODULE_NAME);
    if (!lib) return null;
    const expFn = (n: string): NativePointer => {
        const p = lib.findExportByName(n);
        if (p === null) {
            throw new Error(`${IL2CPP_MODULE_NAME} export not found: ${n}`);
        }
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
        if (p1.indexOf("Int32") >= 0) return { info: m, ptr: methodEntry(m) };
    }
    return null;
}

export const initializeSeedMi = findInitializeSeedOverload();

// --- Runner builder ---

export interface RunnerHandle {
    runner: NativePointer;  // IdunRunner instance — the only object pinned in gcRoot
    innerAiControl: NativePointer;
    seed: number;
}

/**
 * Build an isolated IdunRunner from a BattleConfiguration, using fresh
 * null-object sidecars (NullLogger, TimeSource, NullBattleDataReporter).
 *
 * Fresh IdunRunner via 2-arg ctor is preferred over ReplayRunner:
 * ReplayRunner's ctor touches ReplayRecorder state that has been observed to
 * crash (`access violation 0x4`) on a second build in the same session.
 *
 * Stream events are captured out-of-band via Interceptor hooks on
 * StreamDispatcher.Action / StartGroup (see game/apply-stack.ts).
 */
export function buildRunner(config: NativePointer): RunnerHandle {
    if (!runnerApplyMi) throw new Error("IdunRunner.Apply not found");
    if (!initializeSeedMi) throw new Error("Initialize(seed) overload not resolved");
    if (!idunRunnerOptionsCtor) throw new Error("IdunRunnerOptions ctor not resolved");
    gcRoot.init();

    const logger = instantiate(nullLoggerClass!, nullLoggerCtor!);
    const timeSource = instantiate(timeSourceClass!, timeSourceCtor!);
    const reporter = instantiate(nullReporterClass!, nullReporterCtor!);
    const seed = (Math.random() * 0x7fffffff) | 0;

    // Fresh IdunRunner via 2-arg ctor: (BattleConfiguration, bool recordQuerySimRequests)
    const ctor = findCtorByParamCount(runnerClass!, 2);
    if (!ctor) throw new Error("IdunRunner 2-arg ctor not found");
    const runner = il2cpp_object_new(runnerClass!) as NativePointer;
    gcRoot.add(runner);
    const boolFalseArg = Memory.alloc(1); boolFalseArg.writeU8(0);
    invokeMethod(ctor.info, runner, [config, boolFalseArg]);

    // Options: RecordReplay=false — lightweight. Not pinned: either stored
    // in a runner field, or its settings are copied during Initialize().
    const options = il2cpp_object_new(idunRunnerOptionsClass!) as NativePointer;
    invokeMethod(idunRunnerOptionsCtor.info, options, null);
    options.add(16).writeU8(0);

    // Initialize(config, seed, timeSource, options, logger, reporter)
    const seedArg = Memory.alloc(4); seedArg.writeS32(seed);
    invokeMethod(initializeSeedMi.info, runner,
        [config, seedArg, timeSource, options, logger, reporter]);

    const innerAiControl = runner.add(runnerOff.aiControl).readPointer();
    if (innerAiControl.isNull()) throw new Error("inner AiControl null after Initialize");

    return { runner, innerAiControl, seed };
}
