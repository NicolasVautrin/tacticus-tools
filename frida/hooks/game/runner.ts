// IdunRunner class + offsets + runner builder.
//
// The IdunRunner is the main game engine. A live runner is created by the
// game on battle start. We can also build an *isolated* runner
// via its 2-arg ctor with fresh null-object sidecars, and use it as a
// sandbox to explore decisions without mutating the live state.

import {
    class_get_methods, class_get_name, findClass, findClassAnywhere,
    findCtorByParamCount, findMethod, getFieldOffset, IL2CPP_MODULE_NAME,
    MethodRef, method_get_name, method_get_param_count, methodEntry, s,
} from "../il2cpp/helpers.js";
import { il2cpp_object_new, invokeMethod } from "../il2cpp/invoke.js";
import { gcRoot } from "../il2cpp/gc-root.js";
import { emit } from "../features/ai-trace/state.js";

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
    // NOTE: no gcRoot.add here — buildRunner pins each sidecar at the call
    // site (right after creation) and unpins once Initialize() has stored
    // them in the runner's managed fields. See buildRunner.
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
    /** Le `ReplayRecorder` de CE runner est-il ARME ? (cf. OPT_RECORD_REPLAY_OFF)
     *  Faux => `IdunBattle.Runner.IdunRunner$$SetupReplayRecorder` n'a JAMAIS
     *  tourne sur lui : le recorder existe (le ctor du runner le cree) mais il
     *  n'est ni `Init`-ialise, ni inscrit dans `_messageListeners`, ni abonne au
     *  `StreamCache` / au PRNG. Son `Replay` reste donc VIDE, en silence. */
    recordReplay: boolean;
}

/** `IdunBattle.Runner.IdunRunnerOptions.RecordReplay` — le booleen qui ARME
 *  l'enregistrement de replay. RESOLU PAR NOM au runtime, jamais en dur.
 *
 *  MESURE (#477-r1, build `rnca9r7q6c`) — trois lectures concordantes :
 *   - `IdunBattle.Runner.IdunRunnerOptions$$.ctor` ecrit `1` a cet offset (et
 *     `1` dans `AddInputInterceptor`) : le DEFAUT du jeu est « on enregistre » ;
 *   - `IdunBattle.Runner.IdunRunner$$Initialize` teste ce meme champ et n'appelle
 *     `IdunBattle.Runner.IdunRunner$$SetupReplayRecorder` QUE s'il est non nul.
 *     Le champ suivant (`ReplayBugFinderModes`) gouverne
 *     `IdunBattle.Runner.IdunRunner$$AddReplayBugFinder`, celui d'apres
 *     (`AddInputInterceptor`) une troisieme branche — on ne touche ni l'un ni
 *     l'autre ;
 *   - RPC `classFields("IdunBattle.Runner", "IdunRunnerOptions")` : 4 champs,
 *     `RecordReplay:Boolean` en tete.
 *
 *  L'appel n'est donc PAS inconditionnel, contrairement a ce qu'affirmait la
 *  docstring de `features/replay-output-stream.ts` : c'est l'ecriture d'un `0`
 *  ici qui desarmait le flux natif sur TOUS nos runners. */
const optRecordReplayOff = getFieldOffset(idunRunnerOptionsClass, "RecordReplay");

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
export function buildRunner(
    config: NativePointer, opts?: { seed?: number; recordReplay?: boolean },
): RunnerHandle {
    if (!runnerApplyMi) throw new Error("IdunRunner.Apply not found");
    if (!initializeSeedMi) throw new Error("Initialize(seed) overload not resolved");
    if (!idunRunnerOptionsCtor) throw new Error("IdunRunnerOptions ctor not resolved");
    gcRoot.init();

    // Pin each sidecar immediately. They're referenced only by these JS-held
    // pointers until Initialize() stores them in the runner's managed fields;
    // the conservative IL2CPP GC doesn't scan our JS stack, so an
    // il2cpp_object_new below (reporter / options / runner) can trigger a GC
    // that collects them → access violation deep in Initialize. Released once
    // Initialize() has rooted them via the (pinned) runner.
    const pinnedTransients: NativePointer[] = [];
    const logger = instantiate(nullLoggerClass!, nullLoggerCtor!);
    gcRoot.add(logger); pinnedTransients.push(logger);
    const timeSource = instantiate(timeSourceClass!, timeSourceCtor!);
    gcRoot.add(timeSource); pinnedTransients.push(timeSource);
    const reporter = instantiate(nullReporterClass!, nullReporterCtor!);
    gcRoot.add(reporter); pinnedTransients.push(reporter);
    // Use caller-provided seed for reproducible runs; otherwise a fresh
    // random one. Engine RNG drives in-battle randomness (damage rolls,
    // AI tie-breaks, crits) so pinning the seed makes the same roster
    // play out identically across runs.
    const seed = (typeof opts?.seed === "number")
        ? (opts.seed | 0)
        : ((Math.random() * 0x7fffffff) | 0);

    // Fresh IdunRunner via 2-arg ctor: (BattleConfiguration, bool recordQuerySimRequests)
    const ctor = findCtorByParamCount(runnerClass!, 2);
    if (!ctor) throw new Error("IdunRunner 2-arg ctor not found");
    const runner = il2cpp_object_new(runnerClass!) as NativePointer;
    gcRoot.add(runner);

    // Track which step is in flight so the diagnostic event tells us
    // whether the crash is ctor / Initialize / post-init read.
    let step = "alloc";
    try {
        const boolFalseArg = Memory.alloc(1); boolFalseArg.writeU8(0);
        step = "ctor";
        invokeMethod(ctor.info, runner, [config, boolFalseArg]);

        // Options. Pinned like the sidecars (same GC-collection race) until
        // Initialize() has consumed it.
        //
        // Le flag de replay est DESARME PAR DEFAUT (le ctor natif le pose a 1) :
        // armer coute la retention, pour toute la duree de la bataille, du texte
        // de chaque groupe racine de stream (`ReplayStep.OutputStream`) ET d'un
        // objet par tirage PRNG. C'est un cout de MEMOIRE proportionnel a la
        // longueur de la bataille, inutile en collecte de batch.
        // `recordReplay: true` le laisse a la valeur du ctor => le flux natif
        // (`ctx.rpc.replayOutputStream`) devient non vide.
        step = "options";
        const options = il2cpp_object_new(idunRunnerOptionsClass!) as NativePointer;
        gcRoot.add(options); pinnedTransients.push(options);
        invokeMethod(idunRunnerOptionsCtor.info, options, null);
        // Le desarmement est une OPTIMISATION, pas une exigence : si le nom du
        // champ a disparu du build, `getFieldOffset` rend -1 et
        // `options.add(-1).writeU8(0)` ecraserait l'en-tete de l'objet. On ne
        // touche alors a RIEN — le ctor natif laisse `RecordReplay = true`, donc
        // le runner ENREGISTRE, et `recordReplay` le dit (jamais un `false` qui
        // mentirait sur l'etat reel du recorder).
        let recordReplay = opts?.recordReplay === true;
        if (!recordReplay && optRecordReplayOff >= 0) {
            options.add(optRecordReplayOff).writeU8(0);
        } else if (!recordReplay) {
            recordReplay = true;
        }

        // Initialize(config, seed, timeSource, options, logger, reporter)
        const seedArg = Memory.alloc(4); seedArg.writeS32(seed);
        step = "initialize";
        invokeMethod(initializeSeedMi.info, runner,
            [config, seedArg, timeSource, options, logger, reporter]);

        step = "post-init";
        const innerAiControl = runner.add(runnerOff.aiControl).readPointer();
        if (innerAiControl.isNull()) {
            throw new Error("inner AiControl null after Initialize");
        }

        // Sidecars + options are now reachable from the runner's managed
        // fields (the runner is a pinned GC root) → release the transient
        // pins so they don't accumulate across builds.
        for (const p of pinnedTransients) {
            try { gcRoot.remove(p); } catch { /* best effort */ }
        }
        return { runner, innerAiControl, seed, recordReplay };
    } catch (e) {
        // Emit a rich diagnostic before cleanup so we always know which
        // build step blew up and what state the runner was in. The
        // upstream catch in invokeMethod already emits invoke_native_error
        // but lacks the buildRunner-level context (step, runner ptr,
        // config klass) that lets us correlate across battles.
        try {
            const msg = (e as Error).message ?? String(e);
            const runnerKlass = (() => {
                try { return runner.readPointer(); } catch { return null; }
            })();
            const configKlass = (() => {
                try { return config.readPointer(); } catch { return null; }
            })();
            function kname(k: NativePointer | null): string | null {
                if (!k || k.isNull()) return null;
                try { return s(class_get_name(k) as NativePointer); }
                catch { return null; }
            }
            // Sample first few field slots so we can spot half-built
            // state (e.g. _state at offset state still null, etc.).
            const slot = (off: number) => {
                try { return runner.add(off).readPointer().toString(); }
                catch { return null; }
            };
            emit({
                evt: "runner_init_threw",
                step,
                message: msg,
                seed,
                runnerPtr: runner.toString(),
                runnerKlass: kname(runnerKlass),
                configPtr: config.toString(),
                configKlass: kname(configKlass),
                runnerSlots: {
                    state: slot(runnerOff.state),
                    aiControl: slot(runnerOff.aiControl),
                },
            });
        } catch { /* diagnostic must never throw */ }
        // Release the runner pin + any transient pins so they can be
        // collected — otherwise every failed build leaks gcRoot entries
        // (we observed gcRootCount climbing +2 per fail in 50-battle batches).
        for (const p of pinnedTransients) {
            try { gcRoot.remove(p); } catch { /* best effort */ }
        }
        try { gcRoot.remove(runner); } catch { /* best effort */ }
        throw e;
    }
}
