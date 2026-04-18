// Phase 0 recorder: capture EVERY message applied to the live main runner
// and every AI sub-message emitted via AiControl.ApplyAiMessage /
// ApplyHumanAiMessage. Goal = complete log for later faithful replay on an
// isolated ReplayRunner.
//
// Why native ReplayRecorder is insufficient: it only records top-level
// IInputMessages that pass through runner.Apply. AI sub-messages (MoveUnit,
// ActiveAbility, ...) emitted internally via AiControl.ApplyAiMessage are
// NOT recorded — so a pure-native replay diverges after any CheatRunAI.
//
// This hook is observer-only for now (no state mutation, no gcRoot.add
// inside onEnter to avoid re-entering IL2CPP from interceptor callbacks).
// The gc-rooting of captured message pointers happens later when we move
// from observe to replay — in phase 0 we only count/classify.
//
// Identity filter: Interceptor.attach fires for ALL instances of the
// hooked class. We filter args[0] === realRunner (resp. realAiControl)
// so we never capture events from isolated sim runners we may spawn later.

send({ t: "hook_ready", name: "full-recorder", version: 1 });

// --- classes & methods ------------------------------------------------
var runnerClass = findClass("BattleLogicAssembly.dll", "IdunBattle.Runner", "IdunRunner");
var runnerApplyMi = runnerClass ? findMethod(runnerClass, "Apply") : null;
var runnerAiControlOff = runnerClass ? getFieldOffset(runnerClass, "_aiControl") : -1;
var runnerReplayRecorderOff = runnerClass ? getFieldOffset(runnerClass, "_replayRecorder") : -1;
var runnerStateOff = runnerClass ? getFieldOffset(runnerClass, "_state") : -1;
var runnerLoggerOff = runnerClass ? getFieldOffset(runnerClass, "_logger") : -1;
var runnerTimeSourceOff = runnerClass ? getFieldOffset(runnerClass, "_timeSource") : -1;
var runnerConfigOff = runnerClass ? getFieldOffset(runnerClass, "<Configuration>k__BackingField") : -1;
var runnerIsInitOff = runnerClass ? getFieldOffset(runnerClass, "_isInitialized") : -1;
var idunRunnerOptionsClass = findClass("BattleLogicAssembly.dll", "IdunBattle.Runner", "IdunRunnerOptions");
var idunRunnerOptionsCtor = idunRunnerOptionsClass ? findMethod(idunRunnerOptionsClass, ".ctor") : null;
var replayRunnerClass = findClass("BattleLogicAssembly.dll", "IdunBattle.Runner", "ReplayRunner");

// PRNG introspection
var runnerRngOff = runnerClass ? getFieldOffset(runnerClass, "_randomNumberGenerator") : -1;
var disallowablePrngClass = findClass("BattleLogicAssembly.dll", "IdunBattle.Utils.PRNG", "DisallowablePseudoRNG");
var disallowableRealRngOff = disallowablePrngClass ? getFieldOffset(disallowablePrngClass, "_realRNG") : 16;

// Newtonsoft.Json for MatchState serialization (reusing pattern from run-headless-battle.js)
var jsonConvertClass = findClass("Newtonsoft.Json.dll", "Newtonsoft.Json", "JsonConvert");
var serializeMi = null;
(function () {
    if (!jsonConvertClass) return;
    var it = Memory.alloc(Process.pointerSize); it.writePointer(ptr(0));
    var pcFn = new NativeFunction(il2cpp.findExportByName("il2cpp_method_get_param_count"), "uint32", ["pointer"]);
    var m;
    while (!(m = class_get_methods(jsonConvertClass, it)).isNull()) {
        if (s(method_get_name(m)) !== "SerializeObject") continue;
        if (pcFn(m) !== 1) continue;
        serializeMi = { info: m, ptr: m.readPointer() };
        break;
    }
})();
var _readIl2cppStringLarge = function (p) {
    if (p.isNull()) return null;
    var len = p.add(0x10).readS32();
    if (len <= 0 || len > 20000000) return null;
    return p.add(0x14).readUtf16String(len);
};

function findCtorByParamCount(klass, paramCount) {
    var it = Memory.alloc(Process.pointerSize); it.writePointer(ptr(0));
    var m;
    var pcFn = new NativeFunction(il2cpp.findExportByName("il2cpp_method_get_param_count"), "uint32", ["pointer"]);
    while (!(m = class_get_methods(klass, it)).isNull()) {
        if (s(method_get_name(m)) !== ".ctor") continue;
        try { if (pcFn(m) === paramCount) return { info: m, ptr: m.readPointer() }; } catch (e) {}
    }
    return null;
}

function findInitializeBySignature(wantInt32) {
    if (!runnerClass) return null;
    var it = Memory.alloc(Process.pointerSize); it.writePointer(ptr(0));
    var pcFn = new NativeFunction(il2cpp.findExportByName("il2cpp_method_get_param_count"), "uint32", ["pointer"]);
    var paramFn = new NativeFunction(il2cpp.findExportByName("il2cpp_method_get_param"), "pointer", ["pointer", "uint32"]);
    var nameFn = new NativeFunction(il2cpp.findExportByName("il2cpp_type_get_name"), "pointer", ["pointer"]);
    var m;
    while (!(m = class_get_methods(runnerClass, it)).isNull()) {
        if (s(method_get_name(m)) !== "Initialize") continue;
        if (pcFn(m) !== 6) continue;
        var p1 = s(nameFn(paramFn(m, 1)));
        if (wantInt32 && p1.indexOf("Int32") >= 0) return { info: m, ptr: m.readPointer() };
        if (!wantInt32 && p1.indexOf("IPseudoRNG") >= 0) return { info: m, ptr: m.readPointer() };
    }
    return null;
}

var replayRunnerCtor4 = replayRunnerClass ? findCtorByParamCount(replayRunnerClass, 4) : null;
var initializeSeedMi = findInitializeBySignature(true);

// MatchState._entities = List<IEntity> @ 48
var matchStateClass = findClass("BattleLogicAssembly.dll", "IdunBattle.Core", "MatchState");
var msEntitiesOff = matchStateClass ? getFieldOffset(matchStateClass, "_entities") : -1;

// Entity layout (base): Id@16 Int32, Type@20 Int32 (EntityType enum),
//   Components@24 array — but we use the concrete subclass direct-component refs.
// UnitEntity.Owner @ 32 (OwnerComponent)
// MatchEntity.Turn @ 56 (TurnComponent)
// OwnerComponent.PlayerEntityId @ 16, _overridingPlayerEntityId @ 20 (BEntityId = Int32)
// TurnComponent._currentPlayerId @ 36, TempPlayerId (Nullable) @ 40
//
// EntityType: 0=Tile 1=Unit 2=Match 3=Effect 4=Player 5=UnitFoot 6=Machine 7=MachinePlatform 8=EnvironmentAbility
var ENTITY_TYPE_UNIT = 1;
var ENTITY_TYPE_MATCH = 2;

// MT state helpers — snapshot/restore full PRNG state around each captured
// Apply. Lets the replay force inner's PRNG to the exact state live had
// before each message, so drift can't accumulate between steps.
function mtPtrFor(runnerPtr) {
    var mt = runnerPtr.add(runnerRngOff).readPointer();
    for (var hop = 0; hop < 4; hop++) {
        if (s(class_get_name(mt.readPointer())).indexOf("MersenneTwister") >= 0) return mt;
        var n = mt.add(16).readPointer();
        if (n.isNull() || n.equals(mt)) return null;
        mt = n;
    }
    return null;
}
function snapshotMt(runnerPtr) {
    var mt = mtPtrFor(runnerPtr);
    if (!mt) return null;
    var seed = mt.add(16).readS32();
    var count = mt.add(20).readS32();
    var mti = mt.add(40).readS32();
    var arr = mt.add(32).readPointer();
    if (arr.isNull()) return null;
    var len = arr.add(0x18).readS32();
    var bytes = arr.add(0x20).readByteArray(len * 4);
    return { seed: seed, count: count, mti: mti, mtBytes: bytes, mtLen: len };
}
// Only mti + mt[] affect PRNG behavior. seed and count are metadata —
// skipped on restore to reduce overhead and avoid cross-checks.
function restoreMt(runnerPtr, snap) {
    var mt = mtPtrFor(runnerPtr);
    if (!mt || !snap) return false;
    mt.add(40).writeS32(snap.mti);
    var arr = mt.add(32).readPointer();
    if (arr.isNull()) return false;
    arr.add(0x20).writeByteArray(snap.mtBytes);
    return true;
}

var aiControlClass = findClass("BattleLogicAssembly.dll", "IdunBattle.Core.Services", "AiControl");
var applyAiMsgMi = aiControlClass ? findMethod(aiControlClass, "ApplyAiMessage") : null;
var applyHumanAiMsgMi = aiControlClass ? findMethod(aiControlClass, "ApplyHumanAiMessage") : null;

// StreamDispatcher.Action / StartGroup — emitted for every state mutation
// (effect added, damage dealt, unit moved, turn started, …). We hook once
// globally (not identity-filtered) and correlate each event to the active
// runner.Apply / AiControl.ApplyAiMessage via applyStack.
var streamDispClass = findClass("BattleLogicAssembly.dll", "IdunBattle.Streams", "StreamDispatcher");
var streamActionMi = streamDispClass ? findMethod(streamDispClass, "Action") : null;
var streamGroupMi = streamDispClass ? findMethod(streamDispClass, "StartGroup") : null;

// Native replay for cross-check (probe 1)
var replayRecorderClass = findClass("BattleLogicAssembly.dll", "IdunBattleLogic.Replay", "ReplayRecorder");
var getReplayMi = replayRecorderClass ? findMethod(replayRecorderClass, "GetReplay") : null;
var replayClass = findClass("BattleLogicAssembly.dll", "IdunBattleLogic.Replay", "Replay");
var replayMessagesOff = replayClass ? getFieldOffset(replayClass, "Messages") : -1;
var replayRngSeedOff = replayClass ? getFieldOffset(replayClass, "RngSeed") : -1;

// CheatRunAI trigger (for probe 2)
var cheatRunAiClass = findClass("BattleLogicAssembly.dll", "IdunBattle.Messages", "CheatRunAIMessage");

// Runner capture via IdunGameViews.Update
var gameViewsClass = findClass("Assembly-CSharp.dll", "IdunBattle.View.Game", "IdunGameViews");
var gvRunnerOff = gameViewsClass ? getFieldOffset(gameViewsClass, "_runner") : -1;
var updateMi = gameViewsClass ? findMethod(gameViewsClass, "Update") : null;

// --- state ------------------------------------------------------------
var runnerInstance = null;
var realAiControl = null;
var installedListeners = [];
var log = [];              // { idx, src, cls, ptr, ts, runnerTurn, events }
var counter = 0;
var pending = [];

// applyStack: top-of-stack identifies the currently-running Apply context
// across both live and standalone/inner dispatches. Each entry:
//   { role: 'live'|'standalone', target: array to push events into }
// StreamDispatcher hooks peek the top to route their events.
var applyStack = [];
function pushApply(role, target) { applyStack.push({ role: role, target: target }); }
function popApply() { applyStack.pop(); }

function _readStepTags(dictPtr) {
    try { if (typeof readDict === 'function') return readDict(dictPtr, 0); }
    catch (e) {}
    return null;
}
// Attach once at script load — stream hooks fire for BOTH live's dispatcher
// and any standalone's dispatcher. No identity filter, we route via stack.
if (streamActionMi && !streamActionMi.ptr.isNull()) {
    Interceptor.attach(streamActionMi.ptr, {
        onEnter: function (args) {
            if (applyStack.length === 0) return;
            var top = applyStack[applyStack.length - 1];
            if (!top.target) return;
            try {
                top.target.push({
                    kind: 'action',
                    step: args[1].toInt32(),
                    entity: args[2].toInt32(),
                    tags: _readStepTags(args[3])
                });
            } catch (e) {}
        }
    });
}
if (streamGroupMi && !streamGroupMi.ptr.isNull()) {
    Interceptor.attach(streamGroupMi.ptr, {
        onEnter: function (args) {
            if (applyStack.length === 0) return;
            var top = applyStack[applyStack.length - 1];
            if (!top.target) return;
            try {
                var src = null;
                try { if (typeof readIl2cppString === 'function') src = readIl2cppString(args[3]); }
                catch (e) {}
                top.target.push({
                    kind: 'group',
                    group: args[1].toInt32(),
                    entity: args[2].toInt32(),
                    source: src
                });
            } catch (e) {}
        }
    });
}

// --- install/reinstall interceptors filtered by identity --------------
function detachAll() {
    for (var i = 0; i < installedListeners.length; i++) {
        try { installedListeners[i].detach(); } catch (e) {}
    }
    installedListeners = [];
}

function install() {
    detachAll();
    if (!runnerInstance || !runnerApplyMi) return false;
    realAiControl = runnerInstance.add(runnerAiControlOff).readPointer();
    if (realAiControl.isNull()) return false;
    gcRoot.init();

    var runnerSnapshot = runnerInstance;
    var aiSnapshot = realAiControl;

    installedListeners.push(Interceptor.attach(runnerApplyMi.ptr, {
        onEnter: function (args) {
            if (!args[0].equals(runnerSnapshot)) { this._ours = false; return; }
            this._ours = true;
            try {
                var msg = args[1];
                gcRoot.add(msg);
                var entry = {
                    idx: counter++,
                    src: 'top',
                    cls: readMsgClass(msg),
                    ptr: msg.toString(),
                    unitId: null,
                    prng: snapshotMt(runnerSnapshot),
                    ts: Date.now(),
                    events: []
                };
                log.push(entry);
                pushApply('live', entry.events);
            } catch (e) {}
        },
        onLeave: function () {
            if (this._ours) { try { popApply(); } catch (e) {} }
        }
    }));

    // MoveUnitMessage.UnitId @16 (BEntityId = Int32) and
    // ActiveAbilityMessage.CasterId @16 share the same offset — read unconditionally.
    function attachAi(mi, tag) {
        if (!mi || mi.ptr.isNull()) return;
        installedListeners.push(Interceptor.attach(mi.ptr, {
            onEnter: function (args) {
                if (!args[0].equals(aiSnapshot)) { this._ours = false; return; }
                this._ours = true;
                try {
                    var msg = args[1];
                    gcRoot.add(msg);
                    var uid = null;
                    try { uid = msg.add(16).readS32(); } catch (e) {}
                    var entry = {
                        idx: counter++,
                        src: tag,
                        cls: readMsgClass(msg),
                        ptr: msg.toString(),
                        unitId: uid,
                        prng: snapshotMt(runnerSnapshot),
                        ts: Date.now(),
                        events: []
                    };
                    log.push(entry);
                    pushApply('live', entry.events);
                } catch (e) {}
            },
            onLeave: function () {
                if (this._ours) { try { popApply(); } catch (e) {} }
            }
        }));
    }
    attachAi(applyAiMsgMi, 'ai');
    attachAi(applyHumanAiMsgMi, 'humanAi');

    Interceptor.flush();

    // Bootstrap preamble: read native ReplayRecorder._replay.Messages and
    // prepend its entries to our log tagged src='top_boot'. Covers messages
    // that happened before injection (StartMatch, AddUnits, earlier turns).
    // Dedupe by ptr in case live hooks already captured the same message in
    // the tiny window between Interceptor.flush() and GetReplay().
    var bootCount = 0, bootSkipped = 0;
    try {
        var recorder = runnerSnapshot.add(runnerReplayRecorderOff).readPointer();
        if (!recorder.isNull() && getReplayMi && !getReplayMi.ptr.isNull()) {
            var replay = invokeMethod(getReplayMi.info, recorder, null);
            if (!replay.isNull()) {
                var msgsList = replay.add(replayMessagesOff).readPointer();
                if (!msgsList.isNull()) {
                    var size = msgsList.add(0x18).readS32();
                    var items = msgsList.add(0x10).readPointer();
                    var seenPtrs = {};
                    for (var li = 0; li < log.length; li++) seenPtrs[log[li].ptr] = true;
                    var boot = [];
                    for (var i = 0; i < size; i++) {
                        var step = items.add(0x20 + i * 8).readPointer();
                        if (step.isNull()) continue;
                        var turn = step.add(20).readS32();
                        var inputMsg = step.add(32).readPointer();
                        if (inputMsg.isNull()) continue;
                        var pstr = inputMsg.toString();
                        if (seenPtrs[pstr]) { bootSkipped++; continue; }
                        boot.push({
                            idx: boot.length,
                            src: 'top_boot',
                            cls: readMsgClass(inputMsg),
                            ptr: pstr,
                            unitId: null,
                            turn: turn,
                            ts: 0,
                            events: []
                        });
                    }
                    // prepend boot, then renumber live entries so idx stays sequential
                    var liveOffset = boot.length;
                    for (var j = 0; j < log.length; j++) log[j].idx = liveOffset + j;
                    log = boot.concat(log);
                    counter = log.length;
                    bootCount = boot.length;
                }
            }
        }
    } catch (e) {
        send({ t: 'boot_error', err: e.message });
    }

    send({
        t: 'recorder_armed',
        runner: runnerSnapshot.toString(),
        aiControl: aiSnapshot.toString(),
        listeners: installedListeners.length,
        bootstrapped: bootCount,
        bootSkipped: bootSkipped
    });
    return true;
}

// --- main-thread pump via IdunGameViews.Update ------------------------
// Install() from INSIDE an Interceptor.replace callback fails silently
// (Interceptor.attach cannot complete from within another interceptor
// handler). We flag the need and defer via setTimeout(0) so it runs on
// the Frida main JS thread outside any interceptor context.
var installNeeded = false;
if (updateMi && !updateMi.ptr.isNull()) {
    var _origUpdate = new NativeFunction(updateMi.ptr, "void", ["pointer", "pointer"]);
    Interceptor.replace(updateMi.ptr, new NativeCallback(function (self, methodInfo) {
        var r = self.add(gvRunnerOff).readPointer();
        if (!r.isNull() && !r.equals(runnerInstance || ptr(0))) {
            runnerInstance = r;
            counter = 0;
            log = [];
            installNeeded = true;
            // Defer install so we escape this Interceptor callback. setTimeout
            // runs callbacks on Frida's JS thread when nothing else is running,
            // which is outside the scope of any current interceptor.
            setTimeout(function () {
                if (installNeeded) {
                    installNeeded = false;
                    try { install(); }
                    catch (e) { send({ t: "install_error", err: e.message }); }
                }
            }, 0);
        }
        while (pending.length > 0) {
            var req = pending.shift();
            try { req.resolve(req.fn()); }
            catch (e) { req.reject(e.message); }
        }
        _origUpdate(self, methodInfo);
    }, "void", ["pointer", "pointer"]));
}

// Safety net: every RPC that needs a ready recorder can call this first.
function ensureInstalled() {
    if (runnerInstance && installedListeners.length === 0) {
        try { install(); } catch (e) {}
    }
    return installedListeners.length > 0;
}

function queueOnMainThread(fn) {
    return new Promise(function (resolve, reject) {
        pending.push({
            fn: fn, resolve: resolve,
            reject: function (m) { reject(new Error(m)); }
        });
    });
}

// Serializable view of a log entry — strips the raw mt[] ArrayBuffer so
// RPC replies stay JSON-friendly.
function sanitizeEntry(e) {
    var o = {};
    for (var k in e) if (k !== 'prng') o[k] = e[k];
    if (e.prng) {
        o.prng = { seed: e.prng.seed, count: e.prng.count, mti: e.prng.mti,
                   mtLen: e.prng.mtLen };
    }
    return o;
}

// --- aggregate helpers ------------------------------------------------
function summarize() {
    var byKind = { top: 0, ai: 0, humanAi: 0 };
    var byCls = {};
    for (var i = 0; i < log.length; i++) {
        var e = log[i];
        byKind[e.src] = (byKind[e.src] || 0) + 1;
        byCls[e.cls] = (byCls[e.cls] || 0) + 1;
    }
    return {
        total: log.length,
        byKind: byKind,
        byCls: byCls
    };
}

// --- sim cache: simId -> { captured, ts } ----------------------------
// Captures from `sim` are stashed here so a subsequent `commit` RPC can
// find them. All message pointers are in gcRoot, so they stay alive
// across the gap between sim and commit.
var simCache = {};
var simIdSeq = 1;

// --- inner runner construction (centralized) --------------------------
// Builds an isolated IdunRunner that mirrors the live runner at time 0
// (pre-StartBattle). Used by every RPC that needs a sandbox runner to
// replay messages on, compare states against live, or explore alternate
// decisions without mutating the real runner.
//
// Standalone (fresh `IdunRunner`) is preferred over `ReplayRunner`:
// - ReplayRunner wraps an internal runner + a SimRequestRunner; its
//   ctor touches ReplayRecorder state that has been observed to crash
//   (access violation 0x4) on a second build in the same session.
// - Standalone is a plain runner, no replay machinery — fully isolated.
//
// Steals live's sidecars (logger, timeSource, config, battleDataReporter)
// so the standalone has the same binding context. Initializes with the
// seed from live's Replay so PRNG state matches.
//
// Callers typically: (1) dispatch captured log entries via runner.Apply
// and AiControl.Apply(Human)AiMessage, (2) snapshot state/PRNG, (3) diff
// against the live runner.
//
// Returns { standalone, innerAiControl, seed, replay, realLogger,
//           realTimeSource, realConfig, realReporter } — all pointers
// already added to gcRoot.
function buildStandaloneRunner() {
    if (!runnerInstance) throw new Error("no live runner");
    if (!runnerClass) throw new Error("IdunRunner class not resolved");
    if (!initializeSeedMi) throw new Error("Initialize(seed) overload not resolved");
    if (!idunRunnerOptionsClass || !idunRunnerOptionsCtor) {
        throw new Error("IdunRunnerOptions not resolved");
    }
    gcRoot.init();

    // Read live sidecars
    var realLogger = runnerInstance.add(runnerLoggerOff).readPointer();
    var realTimeSource = runnerInstance.add(runnerTimeSourceOff).readPointer();
    var realConfig = runnerInstance.add(runnerConfigOff).readPointer();
    var opProc = runnerInstance.add(192).readPointer();
    if (opProc.isNull()) throw new Error("opProc null on live runner");
    var startMatchOp = opProc.add(528).readPointer();
    if (startMatchOp.isNull()) throw new Error("startMatchOp null on live runner");
    // NullBattleDataReporter — safe to reuse across standalones
    var realReporter = startMatchOp.add(48).readPointer();

    // Seed from live's ReplayRecorder
    var recorder = runnerInstance.add(runnerReplayRecorderOff).readPointer();
    if (recorder.isNull()) throw new Error("recorder null on live runner");
    var replay = invokeMethod(getReplayMi.info, recorder, null);
    if (replay.isNull()) throw new Error("GetReplay returned null");
    gcRoot.add(replay);
    var seed = replay.add(replayRngSeedOff).readS32();

    // Fresh IdunRunner via 2-arg ctor: (BattleConfiguration, recordQuerySimRequests:bool)
    // Use findCtorByParamCount (not findMethod) — findMethod returns the first
    // ctor by iteration order, which isn't guaranteed to be the 2-arg one.
    var ctor = findCtorByParamCount(runnerClass, 2);
    if (!ctor) throw new Error("IdunRunner 2-arg ctor not found");
    var standalone = il2cpp_object_new(runnerClass);
    gcRoot.add(standalone);
    var boolFalseArg = Memory.alloc(1); boolFalseArg.writeU8(0);
    invokeMethod(ctor.info, standalone, [realConfig, boolFalseArg]);

    // Options: RecordReplay=false so the standalone doesn't fight the live
    // recorder for state (both write to the same field layout inside
    // IdunRunner, but their recorder instances are per-runner so they
    // wouldn't collide; still, disabling keeps the sandbox cheap).
    var options = il2cpp_object_new(idunRunnerOptionsClass);
    gcRoot.add(options);
    invokeMethod(idunRunnerOptionsCtor.info, options, null);
    options.add(16).writeU8(0);

    // Initialize(BattleConfiguration, int seed, ITimeSource, IdunRunnerOptions,
    //            IIdunLogger, IBattleDataReporter)
    var seedArg = Memory.alloc(4); seedArg.writeS32(seed);
    invokeMethod(initializeSeedMi.info, standalone,
        [realConfig, seedArg, realTimeSource, options, realLogger, realReporter]);

    var innerAiControl = standalone.add(runnerAiControlOff).readPointer();
    if (innerAiControl.isNull()) throw new Error("inner AiControl null after Initialize");

    return {
        standalone: standalone,
        innerAiControl: innerAiControl,
        seed: seed,
        replay: replay,
        realLogger: realLogger,
        realTimeSource: realTimeSource,
        realConfig: realConfig,
        realReporter: realReporter
    };
}

// --- RPCs -------------------------------------------------------------
rpc.exports = {
    forceInstall: function () {
        return queueOnMainThread(function () {
            var before = installedListeners.length;
            var ok = install();
            return { ok: ok, before: before, after: installedListeners.length,
                     runner: runnerInstance ? runnerInstance.toString() : null,
                     aiControl: realAiControl ? realAiControl.toString() : null,
                     logSize: log.length };
        });
    },
    info: function () {
        return {
            classesResolved: {
                runnerClass: !!runnerClass,
                aiControlClass: !!aiControlClass,
                replayClass: !!replayClass
            },
            methodsResolved: {
                runnerApplyMi: !!(runnerApplyMi && !runnerApplyMi.ptr.isNull()),
                applyAiMsgMi: !!(applyAiMsgMi && !applyAiMsgMi.ptr.isNull()),
                applyHumanAiMsgMi: !!(applyHumanAiMsgMi && !applyHumanAiMsgMi.ptr.isNull()),
                getReplayMi: !!(getReplayMi && !getReplayMi.ptr.isNull()),
                updateMi: !!(updateMi && !updateMi.ptr.isNull())
            },
            runner: runnerInstance ? runnerInstance.toString() : null,
            aiControl: realAiControl ? realAiControl.toString() : null,
            listeners: installedListeners.length,
            logSize: log.length
        };
    },
    summary: function () {
        return queueOnMainThread(function () {
            ensureInstalled();
            var s = summarize();
            s.head = log.slice(0, 15).map(sanitizeEntry);
            s.tail = log.slice(Math.max(0, log.length - 15)).map(sanitizeEntry);
            return s;
        });
    },
    dump: function () {
        return queueOnMainThread(function () { return { log: log.map(sanitizeEntry) }; });
    },
    clear: function () {
        return queueOnMainThread(function () {
            log = []; counter = 0; return { ok: true };
        });
    },
    // Engine-only lookup: from an IMatchState, iterate _entities and build
    // {ownerByUnit: {uid -> playerId}, currentTurnPlayer, allUnits}.
    // Works on the live runner AND on any inner ReplayRunner's state.
    resolveContext: function (entityIds) {
        return queueOnMainThread(function () {
            if (!runnerInstance) throw new Error("no runner");
            var state = runnerInstance.add(runnerStateOff).readPointer();
            if (state.isNull()) throw new Error("state null");
            var list = state.add(msEntitiesOff).readPointer();
            if (list.isNull()) throw new Error("_entities null");
            var size = list.add(0x18).readS32();
            var items = list.add(0x10).readPointer();

            var wanted = null;
            if (entityIds && entityIds.length) {
                wanted = {};
                for (var k = 0; k < entityIds.length; k++) wanted[entityIds[k]] = true;
            }

            var ownerByUnit = {};
            var currentTurnPlayer = null;
            var prevTurnPlayer = null;
            var tempTurnPlayer = null;
            var unitsSeen = 0;

            for (var i = 0; i < size; i++) {
                var e = items.add(0x20 + i * 8).readPointer();
                if (e.isNull()) continue;
                var eId = e.add(16).readS32();
                var eType = e.add(20).readS32();
                if (eType === ENTITY_TYPE_UNIT) {
                    unitsSeen++;
                    if (wanted && !wanted[eId]) continue;
                    var owner = e.add(32).readPointer();   // UnitEntity.Owner
                    if (owner.isNull()) continue;
                    var pid = owner.add(16).readS32();        // PlayerEntityId
                    var over = owner.add(20).readS32();       // _overridingPlayerEntityId
                    ownerByUnit[eId] = (over !== 0) ? over : pid;
                } else if (eType === ENTITY_TYPE_MATCH) {
                    var turn = e.add(56).readPointer();        // MatchEntity.Turn
                    if (!turn.isNull()) {
                        prevTurnPlayer = turn.add(24).readS32();
                        currentTurnPlayer = turn.add(36).readS32();
                        // TempPlayerId is Nullable<BEntityId>: [value:4B][hasValue:1B]
                        // layout = value@40 + hasValue@44 (needs verification)
                        var hasTemp = turn.add(44).readU8();
                        tempTurnPlayer = hasTemp ? turn.add(40).readS32() : null;
                    }
                }
            }
            return {
                ownerByUnit: ownerByUnit,
                currentTurnPlayer: currentTurnPlayer,
                prevTurnPlayer: prevTurnPlayer,
                tempTurnPlayer: tempTurnPlayer,
                unitsSeen: unitsSeen
            };
        });
    },
    // Probe simulation/atomic flags on MatchState after Init to see if inner is
    // in a passive "no-side-effect" mode.
    probeStateFlags: function (which) {
        return queueOnMainThread(function () {
            if (!runnerInstance) throw new Error("no runner");
            var src = runnerInstance.add(runnerStateOff).readPointer();
            if (src.isNull()) return { err: "state null" };
            // MatchState tsv line 12475: interesting flags offsets (relative to MatchState base)
            // need to resolve through getFieldOffset
            var names = ["InSimulationMode", "InSimulationCleanupPhase",
                         "IsSimulationDisallowed", "DidSimulationRefreshEffects",
                         "InAtomicMode", "AtomicModeCounter",
                         "PauseAutomaticEffectUpdates",
                         "AutomaticEffectUpdatesPausedCounter"];
            var result = {};
            for (var i = 0; i < names.length; i++) {
                var off = getFieldOffset(matchStateClass, names[i]);
                if (off < 0) { result[names[i]] = "offset not found"; continue; }
                // read as Int32 or byte depending on name; try both
                try { result[names[i]] = { offset: off, u8: src.add(off).readU8(),
                                           s32: src.add(off).readS32() }; }
                catch (e) { result[names[i]] = "read error: " + e.message; }
            }
            return result;
        });
    },

    // Read _combatLogger.Actions from live runner — live-growing list of
    // every combat action (attacks, abilities, summons, etc.) persisted
    // internally regardless of our hooks.
    dumpCombatLog: function () {
        return queueOnMainThread(function () {
            if (!runnerInstance) throw new Error("no runner");
            var runnerCombatLoggerOff = getFieldOffset(runnerClass, "_combatLogger");
            var combatLogger = runnerInstance.add(runnerCombatLoggerOff).readPointer();
            if (combatLogger.isNull()) return { err: "combat logger null" };
            var klassName = s(class_get_name(combatLogger.readPointer()));
            var combatLoggerClass = findClass("BattleLogicAssembly.dll",
                "IdunBattleLogic.CombatLog", "BattleCombatLogger");
            if (!combatLoggerClass) return { err: "BattleCombatLogger class not found",
                                             actualKlass: klassName };
            var actionsOff = getFieldOffset(combatLoggerClass, "Actions");
            var actionsList = combatLogger.add(actionsOff).readPointer();
            if (actionsList.isNull()) return { err: "Actions list null" };
            var size = actionsList.add(0x18).readS32();
            var items = actionsList.add(0x10).readPointer();
            // CombatAction (72B): GroupType@16, Caster@24, Target@32, SourceId@40,
            //   CombatEntries@48, ReceivedTime@56, Team@64
            var out = [];
            for (var i = 0; i < size; i++) {
                var act = items.add(0x20 + i * 8).readPointer();
                if (act.isNull()) continue;
                var groupType = act.add(16).readS32();
                var caster = act.add(24).readPointer();
                var target = act.add(32).readPointer();
                var sourceIdPtr = act.add(40).readPointer();
                var entriesList = act.add(48).readPointer();
                var team = act.add(64).readS32();
                var casterId = caster.isNull() ? null : caster.add(16).readS32();
                var targetId = target.isNull() ? null : target.add(16).readS32();
                var entriesCount = entriesList.isNull() ? 0 : entriesList.add(0x18).readS32();
                var sourceId = sourceIdPtr.isNull() ? null : readIl2cppString(sourceIdPtr);
                out.push({ i: i, groupType: groupType, casterId: casterId,
                           targetId: targetId, team: team, sourceId: sourceId,
                           entriesCount: entriesCount });
            }
            return { klass: klassName, count: size, actions: out };
        });
    },

    // Probe SkipFlags on messages stored in native Replay.
    probeMessageFlags: function () {
        return queueOnMainThread(function () {
            if (!runnerInstance) throw new Error("no runner");
            var recorder = runnerInstance.add(runnerReplayRecorderOff).readPointer();
            var replay = invokeMethod(getReplayMi.info, recorder, null);
            var msgsList = replay.add(replayMessagesOff).readPointer();
            var size = msgsList.add(0x18).readS32();
            var items = msgsList.add(0x10).readPointer();
            var out = [];
            for (var i = 0; i < size; i++) {
                var step = items.add(0x20 + i * 8).readPointer();
                if (step.isNull()) continue;
                var msg = step.add(32).readPointer();
                if (msg.isNull()) continue;
                var cls = readMsgClass(msg);
                var entry = { i: i, cls: cls };
                // MoveUnitMessage.SkipFlags @ 32 (bool)
                // ActiveAbilityMessage.SkipFlags @ 28, SkipAtomicCheck @ 29, SkipTurnFinishedCheck @ 30
                if (cls === "MoveUnitMessage") {
                    entry.unitId = msg.add(16).readS32();
                    entry.skipFlags = msg.add(32).readU8();
                } else if (cls === "ActiveAbilityMessage") {
                    entry.casterId = msg.add(16).readS32();
                    entry.targetId = msg.add(20).readS32();
                    entry.abilityType = msg.add(24).readS32();
                    entry.skipFlags = msg.add(28).readU8();
                    entry.skipAtomicCheck = msg.add(29).readU8();
                    entry.skipTurnFinishedCheck = msg.add(30).readU8();
                }
                out.push(entry);
            }
            return { count: size, entries: out };
        });
    },

    // Standalone IdunRunner — no ReplayRunner wrapping. Dispatch native Replay
    // messages directly via runner.Apply. See if state & PRNG match live.
    standaloneReplay: function () {
        return queueOnMainThread(function () {
            if (!runnerInstance) throw new Error("no runner");
            gcRoot.init();
            var result = { phases: [] };

            function snapshotPrng(runnerPtr) {
                var mt = runnerPtr.add(runnerRngOff).readPointer();
                for (var hop = 0; hop < 4; hop++) {
                    if (s(class_get_name(mt.readPointer())).indexOf("MersenneTwister") >= 0) break;
                    var n = mt.add(16).readPointer();
                    if (n.isNull() || n.equals(mt)) break;
                    mt = n;
                }
                var arr = mt.add(32).readPointer();
                var len = arr.isNull() ? 0 : arr.add(0x18).readS32();
                var h = 2166136261 >>> 0;
                for (var i = 0; i < len; i++) {
                    var w32 = arr.add(0x20 + i * 4).readU32() >>> 0;
                    h = Math.imul(h ^ (w32 & 0xff), 16777619) >>> 0;
                    h = Math.imul(h ^ ((w32 >>> 8) & 0xff), 16777619) >>> 0;
                    h = Math.imul(h ^ ((w32 >>> 16) & 0xff), 16777619) >>> 0;
                    h = Math.imul(h ^ ((w32 >>> 24) & 0xff), 16777619) >>> 0;
                }
                return { count: mt.add(20).readS32(), mti: mt.add(40).readS32(),
                         digest: "0x" + h.toString(16) };
            }
            function ctxOf(statePtr) {
                var list = statePtr.add(msEntitiesOff).readPointer();
                if (list.isNull()) return null;
                var size = list.add(0x18).readS32();
                var items = list.add(0x10).readPointer();
                var nUnits = 0, nEffects = 0;
                for (var i = 0; i < size; i++) {
                    var e = items.add(0x20 + i * 8).readPointer();
                    if (e.isNull()) continue;
                    var ty = e.add(20).readS32();
                    if (ty === 1) nUnits++;
                    else if (ty === 3) nEffects++;
                }
                return { nEntities: size, nUnits: nUnits, nEffects: nEffects };
            }

            // Live snapshot
            var livePrng = snapshotPrng(runnerInstance);
            var liveCtx = ctxOf(runnerInstance.add(runnerStateOff).readPointer());
            result.phases.push({ step: "live", prng: livePrng, ctx: liveCtx });

            // Get native Replay from live recorder (source of messages)
            var recorder = runnerInstance.add(runnerReplayRecorderOff).readPointer();
            var replay = invokeMethod(getReplayMi.info, recorder, null);
            gcRoot.add(replay);
            var seed = replay.add(replayRngSeedOff).readS32();
            var msgsList = replay.add(replayMessagesOff).readPointer();
            var size = msgsList.add(0x18).readS32();
            var items = msgsList.add(0x10).readPointer();

            // Deps from live runner
            var realLogger = runnerInstance.add(runnerLoggerOff).readPointer();
            var realTimeSource = runnerInstance.add(runnerTimeSourceOff).readPointer();
            var realConfig = runnerInstance.add(runnerConfigOff).readPointer();
            var opProc = runnerInstance.add(192).readPointer();
            var startMatchOp = opProc.add(528).readPointer();
            var realReporter = startMatchOp.add(48).readPointer();

            // Build standalone IdunRunner (2-arg ctor: config + recordQuerySimRequests:bool)
            var t = Date.now();
            var idunRunnerCtor = findMethod(runnerClass, ".ctor");
            var standalone = il2cpp_object_new(runnerClass);
            gcRoot.add(standalone);
            var boolFalseArg = Memory.alloc(1); boolFalseArg.writeU8(0);
            try { invokeMethod(idunRunnerCtor.info, standalone, [realConfig, boolFalseArg]); }
            catch (ex) { return { phases: result.phases,
                                  error: "ctor failed: " + ex.message }; }
            result.phases.push({ step: "new standalone IdunRunner", ms: Date.now() - t });

            // Options
            var options = il2cpp_object_new(idunRunnerOptionsClass);
            gcRoot.add(options);
            invokeMethod(idunRunnerOptionsCtor.info, options, null);
            options.add(16).writeU8(1); // RecordReplay=true so its own recorder tracks

            // Initialize with seed from native Replay
            t = Date.now();
            var seedArg = Memory.alloc(4); seedArg.writeS32(seed);
            try {
                invokeMethod(initializeSeedMi.info, standalone,
                    [realConfig, seedArg, realTimeSource, options, realLogger, realReporter]);
            } catch (ex) { return { phases: result.phases,
                                    error: "Initialize failed: " + ex.message }; }
            result.phases.push({ step: "Initialize(seed=" + seed + ")",
                                 ms: Date.now() - t,
                                 isInit: standalone.add(runnerIsInitOff).readU8() });

            // Dispatch every native Replay message via runner.Apply — trace per-message
            var ctxAfterInit = ctxOf(standalone.add(runnerStateOff).readPointer());
            result.phases.push({ step: "standalone after Initialize (before dispatch)",
                                 prng: snapshotPrng(standalone), ctx: ctxAfterInit });
            t = Date.now();
            var stats = { dispatched: 0, perMsg: [], errors: [] };
            for (var i = 0; i < size; i++) {
                var step = items.add(0x20 + i * 8).readPointer();
                if (step.isNull()) continue;
                var inputMsg = step.add(32).readPointer();
                if (inputMsg.isNull()) continue;
                var cls = readMsgClass(inputMsg);
                var pBefore = snapshotPrng(standalone);
                var cBefore = ctxOf(standalone.add(runnerStateOff).readPointer());
                // read currentTurnPlayer on standalone before message
                function readTurn(ptr) {
                    var list = ptr.add(runnerStateOff).readPointer().add(msEntitiesOff).readPointer();
                    var sz = list.add(0x18).readS32();
                    var it = list.add(0x10).readPointer();
                    for (var k = 0; k < sz; k++) {
                        var e = it.add(0x20 + k * 8).readPointer();
                        if (e.isNull()) continue;
                        if (e.add(20).readS32() === ENTITY_TYPE_MATCH) {
                            var tc = e.add(56).readPointer();
                            if (!tc.isNull()) return tc.add(36).readS32();
                        }
                    }
                    return null;
                }
                var turnBefore = readTurn(standalone);
                try {
                    invokeMethod(runnerApplyMi.info, standalone, [inputMsg]);
                    stats.dispatched++;
                } catch (ex) {
                    stats.errors.push({ i: i, cls: cls, err: ex.message });
                    if (stats.errors.length >= 3) break;
                }
                var pAfter = snapshotPrng(standalone);
                var cAfter = ctxOf(standalone.add(runnerStateOff).readPointer());
                var turnAfter = readTurn(standalone);
                stats.perMsg.push({ i: i, cls: cls, turnBefore: turnBefore, turnAfter: turnAfter,
                    prngDelta: pAfter.count - pBefore.count,
                    unitsDelta: cAfter.nUnits - cBefore.nUnits,
                    effectsDelta: cAfter.nEffects - cBefore.nEffects });
            }
            result.phases.push({ step: "dispatch " + size + " native messages",
                                 ms: Date.now() - t, stats: stats });

            // Standalone snapshot
            var sPrng = snapshotPrng(standalone);
            var sCtx = ctxOf(standalone.add(runnerStateOff).readPointer());
            result.phases.push({ step: "standalone", prng: sPrng, ctx: sCtx });

            result.diff = {
                prngCountDelta: sPrng.count - livePrng.count,
                prngMtiDelta: sPrng.mti - livePrng.mti,
                prngDigestMatch: sPrng.digest === livePrng.digest,
                nUnitsDelta: sCtx.nUnits - liveCtx.nUnits,
                nEffectsDelta: sCtx.nEffects - liveCtx.nEffects,
                nEntitiesDelta: sCtx.nEntities - liveCtx.nEntities
            };

            // Extra probe: dispatch a FRESH CheatRunAIMessage (ours, not from
            // the native replay stream). Does that consume randoms?
            try {
                var prngBefore = snapshotPrng(standalone);
                var freshCheat = createObject(cheatRunAiClass);
                gcRoot.add(freshCheat);
                var freshErr = null;
                try { invokeMethod(runnerApplyMi.info, standalone, [freshCheat]); }
                catch (ex) { freshErr = ex.message; }
                var prngAfter = snapshotPrng(standalone);
                var ctxAfter = ctxOf(standalone.add(runnerStateOff).readPointer());
                result.freshCheatProbe = {
                    err: freshErr,
                    prngBefore: prngBefore, prngAfter: prngAfter,
                    prngCountDelta: prngAfter.count - prngBefore.count,
                    ctxAfter: ctxAfter,
                    nUnitsDelta: ctxAfter.nUnits - sCtx.nUnits
                };
            } catch (e) {
                result.freshCheatProbe = { err: e.message };
            }
            return result;
        });
    },

    // Dump native Replay.Messages to see what top-level runner.Apply has recorded.
    dumpNativeReplay: function () {
        return queueOnMainThread(function () {
            if (!runnerInstance) throw new Error("no runner");
            var recorder = runnerInstance.add(runnerReplayRecorderOff).readPointer();
            if (recorder.isNull()) return { err: "recorder null" };
            var replay = invokeMethod(getReplayMi.info, recorder, null);
            if (replay.isNull()) return { err: "replay null" };
            var msgsList = replay.add(replayMessagesOff).readPointer();
            if (msgsList.isNull()) return { err: "messages list null" };
            var size = msgsList.add(0x18).readS32();
            var items = msgsList.add(0x10).readPointer();
            var entries = [];
            for (var i = 0; i < size; i++) {
                var step = items.add(0x20 + i * 8).readPointer();
                if (step.isNull()) continue;
                var idx = step.add(16).readS32();
                var turn = step.add(20).readS32();
                var inputMsg = step.add(32).readPointer();
                var srList = step.add(64).readPointer();
                var srCount = srList.isNull() ? 0 : srList.add(0x18).readS32();
                entries.push({
                    i: i, idx: idx, turn: turn,
                    cls: inputMsg.isNull() ? null : readMsgClass(inputMsg),
                    simReqCount: srCount
                });
            }
            return { count: size, entries: entries };
        });
    },

    // Snapshot the live runner's PRNG — seed, count, mti, and digest of mt[].
    prngSnapshot: function () {
        return queueOnMainThread(function () {
            if (!runnerInstance) throw new Error("no runner");
            var wrapper = runnerInstance.add(runnerRngOff).readPointer();
            if (wrapper.isNull()) return { err: "no wrapper" };
            var wrapperKlass = s(class_get_name(wrapper.readPointer()));
            // The PRNG may be wrapped 0..N times (Disallowable → IntBasedMT).
            // Walk the chain by following `_realRNG` (offset 16) until we
            // reach something that looks like a MersenneTwister (has the
            // Seed/Count/mt fields at the documented offsets).
            var chain = [ { klass: wrapperKlass, ptr: wrapper.toString() } ];
            var mt = wrapper;
            for (var hop = 0; hop < 4 && !mt.isNull(); hop++) {
                var kname = s(class_get_name(mt.readPointer()));
                if (kname.indexOf("MersenneTwister") >= 0) break;
                // try to follow `_realRNG` @16 if present
                var next = mt.add(16).readPointer();
                if (next.isNull() || next.equals(mt)) break;
                chain.push({ klass: s(class_get_name(next.readPointer())), ptr: next.toString() });
                mt = next;
            }
            if (mt.isNull() || s(class_get_name(mt.readPointer())).indexOf("MersenneTwister") < 0) {
                return { err: "MT not found", chain: chain };
            }
            var seed = mt.add(16).readS32();
            var count = mt.add(20).readS32();
            var mti = mt.add(40).readS32();
            // mt[] is a UInt32[] object at offset 32; array contents start at +0x20, length at +0x18
            var arr = mt.add(32).readPointer();
            var digest = null;
            if (!arr.isNull()) {
                var len = arr.add(0x18).readS32();
                if (len > 0 && len <= 2048) {
                    // cheap fnv-1a over all uint32 words
                    var h = 2166136261 >>> 0;
                    for (var i = 0; i < len; i++) {
                        var w = arr.add(0x20 + i * 4).readU32() >>> 0;
                        h = Math.imul(h ^ (w & 0xff), 16777619) >>> 0;
                        h = Math.imul(h ^ ((w >>> 8) & 0xff), 16777619) >>> 0;
                        h = Math.imul(h ^ ((w >>> 16) & 0xff), 16777619) >>> 0;
                        h = Math.imul(h ^ ((w >>> 24) & 0xff), 16777619) >>> 0;
                    }
                    digest = "0x" + h.toString(16);
                }
            }
            return {
                chain: chain,
                mtKlass: s(class_get_name(mt.readPointer())),
                seed: seed, count: count, mti: mti,
                mtDigest: digest
            };
        });
    },

    // Same as proveAlignment but uses our full-recorder log (top_boot +
    // top + ai + humanAi) instead of native RunAllSteps. Correct for
    // post-turn-1 states since it replays captured sub-messages.
    proveAlignmentViaLog: function () {
        return queueOnMainThread(function () {
            if (!runnerInstance) throw new Error("no runner");
            gcRoot.init();
            var result = { phases: [], stats: { top: 0, top_boot: 0, ai: 0, humanAi: 0,
                                                skippedCheatRunAi: 0, errors: [] } };

            function snapshotPrng(runnerPtr) {
                var mt = runnerPtr.add(runnerRngOff).readPointer();
                for (var hop = 0; hop < 4; hop++) {
                    if (s(class_get_name(mt.readPointer())).indexOf("MersenneTwister") >= 0) break;
                    var n = mt.add(16).readPointer();
                    if (n.isNull() || n.equals(mt)) break;
                    mt = n;
                }
                var arr = mt.add(32).readPointer();
                var len = arr.isNull() ? 0 : arr.add(0x18).readS32();
                var h = 2166136261 >>> 0;
                for (var i = 0; i < len; i++) {
                    var w32 = arr.add(0x20 + i * 4).readU32() >>> 0;
                    h = Math.imul(h ^ (w32 & 0xff), 16777619) >>> 0;
                    h = Math.imul(h ^ ((w32 >>> 8) & 0xff), 16777619) >>> 0;
                    h = Math.imul(h ^ ((w32 >>> 16) & 0xff), 16777619) >>> 0;
                    h = Math.imul(h ^ ((w32 >>> 24) & 0xff), 16777619) >>> 0;
                }
                return { seed: mt.add(16).readS32(), count: mt.add(20).readS32(),
                         mti: mt.add(40).readS32(), digest: "0x" + h.toString(16) };
            }
            function digestState(statePtr) {
                if (!serializeMi) return null;
                var jp = invokeMethod(serializeMi.info, ptr(0), [statePtr]);
                if (jp.isNull()) return null;
                var str = _readIl2cppStringLarge(jp);
                if (!str) return null;
                var h = 2166136261 >>> 0;
                for (var i = 0; i < str.length; i++) {
                    h = Math.imul(h ^ (str.charCodeAt(i) & 0xff), 16777619) >>> 0;
                }
                return { bytes: str.length, digest: "0x" + h.toString(16) };
            }

            // Live snapshot first
            var livePrng = snapshotPrng(runnerInstance);
            var liveState = digestState(runnerInstance.add(runnerStateOff).readPointer());
            result.phases.push({ step: "live", prng: livePrng, state: liveState });

            // Build inner — Initialize only, don't RunAllSteps
            var recorder = runnerInstance.add(runnerReplayRecorderOff).readPointer();
            var replay = invokeMethod(getReplayMi.info, recorder, null);
            gcRoot.add(replay);
            var seed = replay.add(replayRngSeedOff).readS32();
            var realLogger = runnerInstance.add(runnerLoggerOff).readPointer();
            var realTimeSource = runnerInstance.add(runnerTimeSourceOff).readPointer();
            var realConfig = runnerInstance.add(runnerConfigOff).readPointer();
            var opProc = runnerInstance.add(192).readPointer();
            var startMatchOp = opProc.add(528).readPointer();
            var realReporter = startMatchOp.add(48).readPointer();
            var options = il2cpp_object_new(idunRunnerOptionsClass);
            gcRoot.add(options);
            invokeMethod(idunRunnerOptionsCtor.info, options, null);
            options.add(16).writeU8(0);
            var maxAiSteps = Memory.alloc(8); maxAiSteps.writeU64(0);
            var rr = il2cpp_object_new(replayRunnerClass);
            gcRoot.add(rr);
            invokeMethod(replayRunnerCtor4.info, rr, [realLogger, replay, realTimeSource, maxAiSteps]);
            var innerRunner = rr.add(getFieldOffset(replayRunnerClass, "_runner")).readPointer();

            // Let InitializeBattle do the full setup (it calls IdunRunner.Initialize internally).
            // No manual Initialize — avoids double-init NPE on SetupReplayRecorder.
            var t0 = Date.now();
            var initBattleMi = findMethod(replayRunnerClass, "InitializeBattle");
            var ibErr = null;
            try { invokeMethod(initBattleMi.info, rr, null); }
            catch (ex) { ibErr = ex.message; }
            // Probe: remaining steps and next-step index after init
            var getRemainingMi = findMethod(replayRunnerClass, "get_RemainingSteps");
            var nextStepIdxOff = getFieldOffset(replayRunnerClass, "_nextStepIndex");
            var remainingAfterInit = null, nextIdxAfterInit = null;
            try {
                var boxed = invokeMethod(getRemainingMi.info, rr, null);
                if (!boxed.isNull()) remainingAfterInit = boxed.add(0x10).readS32();
                nextIdxAfterInit = rr.add(nextStepIdxOff).readS32();
            } catch (e) {}
            result.phases.push({ step: "InitializeBattle",
                                 ms: Date.now() - t0, err: ibErr,
                                 remainingSteps: remainingAfterInit,
                                 nextStepIndex: nextIdxAfterInit });
            var innerAiControl = innerRunner.add(runnerAiControlOff).readPointer();

            // Replay native top-level via RunAllSteps(false, false) — we want
            // actual re-execution with PRNG consumption, not deterministic
            // sim-request lookup that skips random draws.
            t0 = Date.now();
            var runAllStepsMi = findMethod(replayRunnerClass, "RunAllSteps");
            var boolFalse = Memory.alloc(1); boolFalse.writeU8(0);
            var rasErr = null;
            try { invokeMethod(runAllStepsMi.info, rr, [boolFalse, boolFalse]); }
            catch (ex) { rasErr = ex.message; }
            var remainingAfterRas = null, nextIdxAfterRas = null;
            try {
                var b2 = invokeMethod(getRemainingMi.info, rr, null);
                if (!b2.isNull()) remainingAfterRas = b2.add(0x10).readS32();
                nextIdxAfterRas = rr.add(nextStepIdxOff).readS32();
            } catch (e) {}
            result.phases.push({ step: "RunAllSteps(false, false)",
                                 ms: Date.now() - t0, err: rasErr,
                                 remainingSteps: remainingAfterRas,
                                 nextStepIndex: nextIdxAfterRas });
            if (rasErr) return result;

            // Now manually dispatch only the ai/humanAi entries of our log
            t0 = Date.now();
            var prngRestored = 0;
            for (var i = 0; i < log.length; i++) {
                var e = log[i];
                if (e.src !== 'ai' && e.src !== 'humanAi') continue;
                var msgPtr = ptr(e.ptr);
                if (e.prng) { if (restoreMt(innerRunner, e.prng)) prngRestored++; }
                try {
                    var target = (e.src === 'humanAi') ? applyHumanAiMsgMi : applyAiMsgMi;
                    invokeMethod(target.info, innerAiControl, [msgPtr]);
                    result.stats[e.src]++;
                } catch (ex) {
                    result.stats.errors.push({ i: i, src: e.src, cls: e.cls,
                                               unitId: e.unitId, err: ex.message });
                    if (result.stats.errors.length >= 3) break;
                }
            }
            result.phases.push({ step: "ai/humanAi dispatch", ms: Date.now() - t0,
                                 prngRestored: prngRestored });

            // Inner snapshot after replay
            var innerPrng = snapshotPrng(innerRunner);
            var innerStatePtr = innerRunner.add(runnerStateOff).readPointer();
            var innerState = digestState(innerStatePtr);
            result.phases.push({ step: "inner", prng: innerPrng, state: innerState });

            // Structural comparison — entity count + current turn for both
            function ctxOf(statePtr) {
                var list = statePtr.add(msEntitiesOff).readPointer();
                if (list.isNull()) return null;
                var size = list.add(0x18).readS32();
                var items = list.add(0x10).readPointer();
                var nEnt = size, nTiles = 0, nUnits = 0, nEffects = 0,
                    nPlayers = 0, nMatch = 0, currentTurnPlayer = null;
                var unitIds = [], effectIds = [], ownerByUnit = {};
                for (var i = 0; i < size; i++) {
                    var e = items.add(0x20 + i * 8).readPointer();
                    if (e.isNull()) continue;
                    var id = e.add(16).readS32();
                    var ty = e.add(20).readS32();
                    if (ty === 0) nTiles++;
                    else if (ty === 1) {
                        nUnits++;
                        unitIds.push(id);
                        var o = e.add(32).readPointer();
                        if (!o.isNull()) {
                            var pid = o.add(16).readS32(), ov = o.add(20).readS32();
                            ownerByUnit[id] = (ov !== 0) ? ov : pid;
                        }
                    }
                    else if (ty === 2) {
                        nMatch++;
                        var tc = e.add(56).readPointer();
                        if (!tc.isNull()) currentTurnPlayer = tc.add(36).readS32();
                    }
                    else if (ty === 3) { nEffects++; effectIds.push(id); }
                    else if (ty === 4) nPlayers++;
                }
                return { nEntities: nEnt, nTiles: nTiles, nUnits: nUnits,
                         nEffects: nEffects, nPlayers: nPlayers, nMatch: nMatch,
                         currentTurnPlayer: currentTurnPlayer,
                         unitIds: unitIds.sort(function(a,b){return a-b;}),
                         effectIds: effectIds.sort(function(a,b){return a-b;}),
                         ownerByUnit: ownerByUnit };
            }
            result.liveCtx = ctxOf(runnerInstance.add(runnerStateOff).readPointer());
            result.innerCtx = ctxOf(innerStatePtr);
            // Compute unit delta: what's in live but not in inner (and vice-versa)
            var innerSet = {};
            result.innerCtx.unitIds.forEach(function(x){ innerSet[x] = true; });
            var liveSet = {};
            result.liveCtx.unitIds.forEach(function(x){ liveSet[x] = true; });
            result.unitsOnlyLive = result.liveCtx.unitIds.filter(function(x){ return !innerSet[x]; });
            result.unitsOnlyInner = result.innerCtx.unitIds.filter(function(x){ return !liveSet[x]; });
            result.unitsOnlyLiveOwners = result.unitsOnlyLive.map(function(id) {
                return { id: id, owner: result.liveCtx.ownerByUnit[id] };
            });

            result.diff = {
                prngSeedMatch: livePrng.seed === innerPrng.seed,
                prngCountMatch: livePrng.count === innerPrng.count,
                prngCountDelta: innerPrng.count - livePrng.count,
                prngMtiMatch: livePrng.mti === innerPrng.mti,
                prngDigestMatch: livePrng.digest === innerPrng.digest,
                stateDigestMatch: liveState && innerState &&
                                  liveState.digest === innerState.digest,
                stateBytesDelta: innerState && liveState ?
                                 innerState.bytes - liveState.bytes : null
            };
            return result;
        });
    },

    // Build inner, replay native top-level, then compare PRNG + MatchState
    // digest with live. Proves (or disproves) alignment at turn 1.
    proveAlignment: function () {
        return queueOnMainThread(function () {
            if (!runnerInstance) throw new Error("no runner");
            if (!replayRunnerCtor4) throw new Error("ReplayRunner ctor not resolved");
            gcRoot.init();
            var result = { phases: [] };

            function snapshotPrng(runnerPtr) {
                var w = runnerPtr.add(runnerRngOff).readPointer();
                var mt = w;
                for (var hop = 0; hop < 4; hop++) {
                    if (s(class_get_name(mt.readPointer())).indexOf("MersenneTwister") >= 0) break;
                    var n = mt.add(16).readPointer();
                    if (n.isNull() || n.equals(mt)) break;
                    mt = n;
                }
                var arr = mt.add(32).readPointer();
                var len = arr.isNull() ? 0 : arr.add(0x18).readS32();
                var h = 2166136261 >>> 0;
                for (var i = 0; i < len; i++) {
                    var w32 = arr.add(0x20 + i * 4).readU32() >>> 0;
                    h = Math.imul(h ^ (w32 & 0xff), 16777619) >>> 0;
                    h = Math.imul(h ^ ((w32 >>> 8) & 0xff), 16777619) >>> 0;
                    h = Math.imul(h ^ ((w32 >>> 16) & 0xff), 16777619) >>> 0;
                    h = Math.imul(h ^ ((w32 >>> 24) & 0xff), 16777619) >>> 0;
                }
                return {
                    seed: mt.add(16).readS32(),
                    count: mt.add(20).readS32(),
                    mti: mt.add(40).readS32(),
                    digest: "0x" + h.toString(16)
                };
            }
            function digestState(statePtr) {
                if (!serializeMi) return null;
                var jp = invokeMethod(serializeMi.info, ptr(0), [statePtr]);
                if (jp.isNull()) return null;
                var str = _readIl2cppStringLarge(jp);
                if (!str) return null;
                var h = 2166136261 >>> 0;
                for (var i = 0; i < str.length; i++) {
                    h = Math.imul(h ^ (str.charCodeAt(i) & 0xff), 16777619) >>> 0;
                }
                return { bytes: str.length, digest: "0x" + h.toString(16) };
            }

            // 1. Snapshot live pre-sim
            var livePrngBefore = snapshotPrng(runnerInstance);
            var liveStateBefore = digestState(runnerInstance.add(runnerStateOff).readPointer());
            result.phases.push({ step: "live snapshot (before)",
                                 prng: livePrngBefore, state: liveStateBefore });

            // 2. Build inner + Initialize + RunAllSteps
            var recorder = runnerInstance.add(runnerReplayRecorderOff).readPointer();
            var replay = invokeMethod(getReplayMi.info, recorder, null);
            gcRoot.add(replay);
            var seed = replay.add(replayRngSeedOff).readS32();
            var realLogger = runnerInstance.add(runnerLoggerOff).readPointer();
            var realTimeSource = runnerInstance.add(runnerTimeSourceOff).readPointer();
            var realConfig = runnerInstance.add(runnerConfigOff).readPointer();
            var opProc = runnerInstance.add(192).readPointer();
            var startMatchOp = opProc.add(528).readPointer();
            var realReporter = startMatchOp.add(48).readPointer();
            var options = il2cpp_object_new(idunRunnerOptionsClass);
            gcRoot.add(options);
            invokeMethod(idunRunnerOptionsCtor.info, options, null);
            options.add(16).writeU8(0);
            var maxAiSteps = Memory.alloc(8); maxAiSteps.writeU64(0);
            var rr = il2cpp_object_new(replayRunnerClass);
            gcRoot.add(rr);
            invokeMethod(replayRunnerCtor4.info, rr, [realLogger, replay, realTimeSource, maxAiSteps]);
            var innerRunner = rr.add(getFieldOffset(replayRunnerClass, "_runner")).readPointer();
            var seedArg = Memory.alloc(4); seedArg.writeS32(seed);
            invokeMethod(initializeSeedMi.info, innerRunner,
                [realConfig, seedArg, realTimeSource, options, realLogger, realReporter]);
            rr.add(getFieldOffset(replayRunnerClass, "_didInitBattle")).writeU8(1);
            var boolFalse = Memory.alloc(1); boolFalse.writeU8(0);
            var rasErr = null;
            try {
                var runAllStepsMi = findMethod(replayRunnerClass, "RunAllSteps");
                invokeMethod(runAllStepsMi.info, rr, [boolFalse, boolFalse]);
            } catch (e) { rasErr = e.message; }
            result.phases.push({ step: "inner ready", rasErr: rasErr });
            if (rasErr) return result;

            // 3. Snapshot inner post-RunAllSteps (should equal live snapshot)
            var innerPrngAfter = snapshotPrng(innerRunner);
            var innerStateAfter = digestState(innerRunner.add(runnerStateOff).readPointer());
            result.phases.push({ step: "inner snapshot (after RunAllSteps)",
                                 prng: innerPrngAfter, state: innerStateAfter });

            // 4. Diff
            result.diff = {
                prngSeedMatch: livePrngBefore.seed === innerPrngAfter.seed,
                prngCountMatch: livePrngBefore.count === innerPrngAfter.count,
                prngMtiMatch: livePrngBefore.mti === innerPrngAfter.mti,
                prngDigestMatch: livePrngBefore.digest === innerPrngAfter.digest,
                stateDigestMatch: liveStateBefore && innerStateAfter &&
                                  liveStateBefore.digest === innerStateAfter.digest,
                liveBytes: liveStateBefore ? liveStateBefore.bytes : null,
                innerBytes: innerStateAfter ? innerStateAfter.bytes : null
            };
            return result;
        });
    },

    // Try to serialize the live MatchState via Newtonsoft JsonConvert.
    // Streams chunks back because the JSON may be multi-MB.
    serializeLiveState: function () {
        return queueOnMainThread(function () {
            if (!runnerInstance) throw new Error("no runner");
            if (!serializeMi) return { err: "SerializeObject(1arg) not resolved" };
            var state = runnerInstance.add(runnerStateOff).readPointer();
            if (state.isNull()) return { err: "state null" };
            var t0 = Date.now();
            var jsonPtr = null, errMsg = null;
            try { jsonPtr = invokeMethod(serializeMi.info, ptr(0), [state]); }
            catch (e) { errMsg = e.message; }
            if (errMsg || jsonPtr.isNull()) {
                return { err: errMsg || "null result", ms: Date.now() - t0 };
            }
            var str = _readIl2cppStringLarge(jsonPtr);
            var ms = Date.now() - t0;
            if (!str) return { err: "string read failed", ms: ms };
            // fnv-1a digest of the string so we can compare without shipping full JSON
            var h = 2166136261 >>> 0;
            for (var i = 0; i < str.length; i++) {
                h = Math.imul(h ^ (str.charCodeAt(i) & 0xff), 16777619) >>> 0;
            }
            return {
                bytes: str.length,
                ms: ms,
                digest: "0x" + h.toString(16),
                head: str.substring(0, 300),
                tail: str.substring(Math.max(0, str.length - 200))
            };
        });
    },

    // Build a standalone runner, catch it up to live via our log, run
    // CheatRunAI on it to capture the isolated AI's decisions, and stash
    // them under a simId. Does NOT touch the live runner.
    //
    // Returns { simId, captured: [{src, cls}], timings } on success.
    // Pair with `commit(simId)` to apply on live.
    sim: function () {
        return queueOnMainThread(function () {
            ensureInstalled();
            if (!runnerInstance) throw new Error("no runner");
            var timings = [];
            var T0 = Date.now();

            // 1. Battle must be Running
            var mstate = runnerInstance.add(runnerStateOff).readPointer();
            if (mstate.isNull()) throw new Error("state null");
            var stageCheck = null;
            (function () {
                var list = mstate.add(msEntitiesOff).readPointer();
                var size = list.add(0x18).readS32();
                var items = list.add(0x10).readPointer();
                for (var i = 0; i < size; i++) {
                    var e = items.add(0x20 + i * 8).readPointer();
                    if (e.isNull()) continue;
                    if (e.add(20).readS32() === ENTITY_TYPE_MATCH) {
                        var mc = e.add(32).readPointer();
                        if (!mc.isNull()) stageCheck = mc.add(36).readS32();
                        break;
                    }
                }
            })();
            if (stageCheck !== 1) return { error: "battle not Running", stage: stageCheck };

            // 2. Build standalone
            var t = Date.now();
            var built;
            try { built = buildStandaloneRunner(); }
            catch (e) { return { error: "buildStandaloneRunner failed", detail: e.message }; }
            timings.push({ step: "buildStandaloneRunner", ms: Date.now() - t, seed: built.seed });

            // 3. Catch up via our log. Skip CheatRunAIMessage (trigger only;
            //    its ai/humanAi sub-messages are already in our log).
            t = Date.now();
            var catchUp = { top: 0, top_boot: 0, ai: 0, humanAi: 0,
                            skippedCheatRunAi: 0, errors: [] };
            for (var i = 0; i < log.length; i++) {
                var e = log[i];
                var msgPtr = ptr(e.ptr);
                if ((e.src === 'top' || e.src === 'top_boot') && e.cls === 'CheatRunAIMessage') {
                    catchUp.skippedCheatRunAi++;
                    continue;
                }
                try {
                    invokeMethod(runnerApplyMi.info, built.standalone, [msgPtr]);
                    catchUp[e.src]++;
                } catch (ex) {
                    catchUp.errors.push({ i: i, src: e.src, cls: e.cls, err: ex.message });
                    if (catchUp.errors.length >= 3) break;
                }
            }
            timings.push({ step: "catch up via log", ms: Date.now() - t, catchUp: catchUp });
            if (catchUp.errors.length > 0) {
                return { error: "catch up failed", timings: timings };
            }

            // 4. Install temp capture on inner AiControl, fire CheatRunAI,
            //    collect decisions into `captured[]`.
            var captured = [];
            var captureListeners = [];
            function attachCap(mi, tag) {
                if (!mi || mi.ptr.isNull()) return;
                captureListeners.push(Interceptor.attach(mi.ptr, {
                    onEnter: function (args) {
                        if (!args[0].equals(built.innerAiControl)) return;
                        try {
                            var m = args[1];
                            gcRoot.add(m);
                            captured.push({ src: tag, cls: readMsgClass(m), ptr: m.toString() });
                        } catch (e) {}
                    }
                }));
            }
            attachCap(applyAiMsgMi, 'ai');
            attachCap(applyHumanAiMsgMi, 'humanAi');
            Interceptor.flush();

            t = Date.now();
            var cheatMsg = createObject(cheatRunAiClass);
            gcRoot.add(cheatMsg);
            var cheatErr = null;
            try { invokeMethod(runnerApplyMi.info, built.standalone, [cheatMsg]); }
            catch (e) { cheatErr = e.message; }
            for (var li = 0; li < captureListeners.length; li++) captureListeners[li].detach();
            timings.push({ step: "CheatRunAI(standalone)", ms: Date.now() - t,
                           err: cheatErr, capturedCount: captured.length });
            if (cheatErr) return { error: "standalone CheatRunAI failed", detail: cheatErr, timings: timings };

            // 5. Stash under a simId — ptrs stay alive via gcRoot
            var simId = simIdSeq++;
            simCache[simId] = { captured: captured, ts: Date.now() };
            timings.push({ total_ms: Date.now() - T0 });

            return {
                ok: true,
                simId: simId,
                captured: captured.map(function (c) { return { src: c.src, cls: c.cls }; }),
                timings: timings
            };
        });
    },

    // Apply a previously-stashed sim on the live AiControl.
    // Frees the sim from the cache (pointers remain in gcRoot; caller can
    // re-invoke live's AI to produce new rooted messages if needed).
    commit: function (simId) {
        return queueOnMainThread(function () {
            if (!runnerInstance) throw new Error("no runner");
            var entry = simCache[simId];
            if (!entry) return { error: "simId not found", simId: simId };
            var captured = entry.captured;
            var realAiControl = runnerInstance.add(runnerAiControlOff).readPointer();
            var t = Date.now();
            var applied = 0, errors = [];
            for (var ci = 0; ci < captured.length; ci++) {
                var c = captured[ci];
                var target = (c.src === 'humanAi') ? applyHumanAiMsgMi : applyAiMsgMi;
                try {
                    invokeMethod(target.info, realAiControl, [ptr(c.ptr)]);
                    applied++;
                } catch (e) {
                    errors.push({ i: ci, cls: c.cls, err: e.message });
                }
            }
            delete simCache[simId];
            return {
                ok: errors.length === 0,
                simId: simId,
                applied: applied,
                errors: errors,
                ms: Date.now() - t
            };
        });
    },

    // Convenience: sim + commit in one round-trip.
    simAndCommit: function () {
        var self = this;
        return self.sim().then(function (simRes) {
            if (!simRes.ok) return simRes;
            return self.commit(simRes.simId).then(function (commitRes) {
                return {
                    ok: commitRes.ok,
                    simId: simRes.simId,
                    captured: simRes.captured,
                    applied: commitRes.applied,
                    errors: commitRes.errors,
                    timings: simRes.timings.concat([{
                        step: "commit on live",
                        ms: commitRes.ms,
                        applied: commitRes.applied,
                        errors: commitRes.errors.length
                    }])
                };
            });
        });
    },



    // Battle status from the engine — reads MatchComponent.Stage etc.
    // so we don't try to reconstruct on a finished battle.
    battleStatus: function () {
        return queueOnMainThread(function () {
            ensureInstalled();
            if (!runnerInstance) return { err: "no runner" };
            var state = runnerInstance.add(runnerStateOff).readPointer();
            if (state.isNull()) return { err: "state null" };
            var list = state.add(msEntitiesOff).readPointer();
            if (list.isNull()) return { err: "entities null" };
            var size = list.add(0x18).readS32();
            var items = list.add(0x10).readPointer();
            var out = { stage: null, stageName: null, winner: null,
                        currentTurnPlayer: null, cheatFinished: null,
                        unitsAlive: 0 };
            var STAGES = { 0: "Setup", 1: "Running", 2: "Finished" };
            for (var i = 0; i < size; i++) {
                var e = items.add(0x20 + i * 8).readPointer();
                if (e.isNull()) continue;
                var ty = e.add(20).readS32();
                if (ty === ENTITY_TYPE_MATCH) {
                    var mc = e.add(32).readPointer();     // MatchEntity.Component
                    if (!mc.isNull()) {
                        out.stage = mc.add(36).readS32();
                        out.stageName = STAGES[out.stage] || ("?"+out.stage);
                        out.winner = mc.add(20).readS32();
                        out.cheatFinished = !!mc.add(32).readU8();
                    }
                    var tc = e.add(56).readPointer();     // MatchEntity.Turn
                    if (!tc.isNull()) out.currentTurnPlayer = tc.add(36).readS32();
                } else if (ty === ENTITY_TYPE_UNIT) {
                    out.unitsAlive++;
                }
            }
            return out;
        });
    },
    // Safety probe: verify every log entry's ptr still points to a valid
    // IL2CPP object with the expected class name.
    probeLogPointers: function () {
        return queueOnMainThread(function () {
            var out = [];
            var bad = 0;
            for (var i = 0; i < log.length; i++) {
                var e = log[i];
                var p = ptr(e.ptr);
                var cls = null, err = null;
                try { cls = s(class_get_name(p.readPointer())); }
                catch (ex) { err = ex.message; bad++; }
                out.push({ i: i, src: e.src, expected: e.cls,
                           actual: cls, match: cls === e.cls, err: err });
                if (bad >= 3) break;
            }
            return { logSize: log.length, badCount: bad, entries: out };
        });
    },

    // Diagnostic: trace each step of reconstruction with owner + currentTurnPlayer
    // before/after. Goal = validate hypothesis that aborts happen when
    // unit's owner != inner currentTurnPlayer.
    reconstructTrace: function () {
        return queueOnMainThread(function () {
            if (!runnerInstance) throw new Error("no runner");
            if (!replayRunnerCtor4) throw new Error("ReplayRunner ctor not resolved");
            gcRoot.init();

            // 1. Pre-resolve owners from LIVE state (stable during the sim)
            var liveState = runnerInstance.add(runnerStateOff).readPointer();
            var ownerLookup = {};
            (function () {
                var list = liveState.add(msEntitiesOff).readPointer();
                var size = list.add(0x18).readS32();
                var items = list.add(0x10).readPointer();
                for (var i = 0; i < size; i++) {
                    var e = items.add(0x20 + i * 8).readPointer();
                    if (e.isNull()) continue;
                    if (e.add(20).readS32() !== ENTITY_TYPE_UNIT) continue;
                    var id = e.add(16).readS32();
                    var o = e.add(32).readPointer();
                    if (o.isNull()) continue;
                    var p = o.add(16).readS32(), ov = o.add(20).readS32();
                    ownerLookup[id] = (ov !== 0) ? ov : p;
                }
            })();

            // 2. Build inner runner (same as reconstruct)
            var recorder = runnerInstance.add(runnerReplayRecorderOff).readPointer();
            var replay = invokeMethod(getReplayMi.info, recorder, null);
            gcRoot.add(replay);
            var seed = replay.add(replayRngSeedOff).readS32();
            var realLogger = runnerInstance.add(runnerLoggerOff).readPointer();
            var realTimeSource = runnerInstance.add(runnerTimeSourceOff).readPointer();
            var realConfig = runnerInstance.add(runnerConfigOff).readPointer();
            var opProc = runnerInstance.add(192).readPointer();
            var startMatchOp = opProc.add(528).readPointer();
            var realReporter = startMatchOp.add(48).readPointer();
            var options = il2cpp_object_new(idunRunnerOptionsClass);
            gcRoot.add(options);
            invokeMethod(idunRunnerOptionsCtor.info, options, null);
            options.add(16).writeU8(0);
            var maxAiSteps = Memory.alloc(8); maxAiSteps.writeU64(0);
            var rr = il2cpp_object_new(replayRunnerClass);
            gcRoot.add(rr);
            invokeMethod(replayRunnerCtor4.info, rr, [realLogger, replay, realTimeSource, maxAiSteps]);
            var innerRunner = rr.add(getFieldOffset(replayRunnerClass, "_runner")).readPointer();
            var seedArg = Memory.alloc(4); seedArg.writeS32(seed);
            invokeMethod(initializeSeedMi.info, innerRunner,
                [realConfig, seedArg, realTimeSource, options, realLogger, realReporter]);
            var innerAiControl = innerRunner.add(runnerAiControlOff).readPointer();
            var innerState = innerRunner.add(runnerStateOff).readPointer();
            if (innerAiControl.isNull() || innerState.isNull()) {
                return { error: "inner init incomplete",
                         innerAiControl: innerAiControl.toString(),
                         innerState: innerState.toString(),
                         isInit: innerRunner.add(runnerIsInitOff).readU8() };
            }

            // Helper: read inner currentTurnPlayer from TurnComponent on MatchEntity
            function innerTurnPlayer() {
                var list = innerState.add(msEntitiesOff).readPointer();
                if (list.isNull()) return null;
                var size = list.add(0x18).readS32();
                var items = list.add(0x10).readPointer();
                for (var i = 0; i < size; i++) {
                    var e = items.add(0x20 + i * 8).readPointer();
                    if (e.isNull()) continue;
                    if (e.add(20).readS32() === ENTITY_TYPE_MATCH) {
                        var tc = e.add(56).readPointer();
                        if (!tc.isNull()) return tc.add(36).readS32();
                    }
                }
                return null;
            }

            // 3. Replay with per-step trace
            var trace = [];
            for (var i = 0; i < log.length; i++) {
                var e = log[i];
                var msgPtr = ptr(e.ptr);
                var before = innerTurnPlayer();
                var owner = (e.unitId != null) ? (ownerLookup[e.unitId] || null) : null;
                var entry = {
                    step: i,
                    src: e.src,
                    cls: e.cls,
                    unitId: e.unitId,
                    owner: owner,
                    turnBefore: before,
                    skipped: false,
                    err: null
                };
                try {
                    if (e.src === 'top' || e.src === 'top_boot') {
                        if (e.cls === 'CheatRunAIMessage') { entry.skipped = true; trace.push(entry); continue; }
                        invokeMethod(runnerApplyMi.info, innerRunner, [msgPtr]);
                    } else if (e.src === 'ai') {
                        invokeMethod(applyAiMsgMi.info, innerAiControl, [msgPtr]);
                    } else if (e.src === 'humanAi') {
                        invokeMethod(applyHumanAiMsgMi.info, innerAiControl, [msgPtr]);
                    }
                } catch (ex) {
                    entry.err = ex.message;
                }
                entry.turnAfter = innerTurnPlayer();
                trace.push(entry);
                if (trace.filter(function(x){return x.err;}).length >= 5) break;
            }
            return { trace: trace, ownerLookup: ownerLookup };
        });
    },

    // Build an isolated inner IdunRunner, replay captured log on it with
    // correct dispatch per src, compare resulting state vs live.
    reconstruct: function () {
        return queueOnMainThread(function () {
            if (!runnerInstance) throw new Error("no runner");
            if (!replayRunnerCtor4) throw new Error("ReplayRunner 4-arg ctor not resolved");
            if (!initializeSeedMi) throw new Error("Initialize(seed) overload not resolved");
            if (!idunRunnerOptionsCtor) throw new Error("IdunRunnerOptions ctor not resolved");
            gcRoot.init();

            var timings = [];
            var T0 = Date.now();

            // 1. Get native Replay (for seed + as 2nd arg of ReplayRunner ctor)
            var t = Date.now();
            var recorder = runnerInstance.add(runnerReplayRecorderOff).readPointer();
            var replay = invokeMethod(getReplayMi.info, recorder, null);
            gcRoot.add(replay);
            var seed = replay.add(replayRngSeedOff).readS32();
            timings.push({ step: "GetReplay + seed", ms: Date.now() - t, seed: seed });

            // 2. Steal deps from live runner
            var realLogger = runnerInstance.add(runnerLoggerOff).readPointer();
            var realTimeSource = runnerInstance.add(runnerTimeSourceOff).readPointer();
            var realConfig = runnerInstance.add(runnerConfigOff).readPointer();
            var opProc = runnerInstance.add(192).readPointer();
            var startMatchOp = opProc.add(528).readPointer();
            var realReporter = startMatchOp.add(48).readPointer();

            // 3. Build options (RecordReplay=false on sim)
            var options = il2cpp_object_new(idunRunnerOptionsClass);
            gcRoot.add(options);
            invokeMethod(idunRunnerOptionsCtor.info, options, null);
            options.add(16).writeU8(0);

            // 4. Build ReplayRunner(4-arg) — creates empty inner IdunRunner + SimReqRunner
            t = Date.now();
            var maxAiSteps = Memory.alloc(8); maxAiSteps.writeU64(0);
            var rr = il2cpp_object_new(replayRunnerClass);
            gcRoot.add(rr);
            invokeMethod(replayRunnerCtor4.info, rr, [realLogger, replay, realTimeSource, maxAiSteps]);
            var innerRunner = rr.add(getFieldOffset(replayRunnerClass, "_runner")).readPointer();
            timings.push({ step: "new ReplayRunner", ms: Date.now() - t,
                           innerRunner: innerRunner.toString() });

            // 5. Initialize inner runner with seed overload (PRNG isolation)
            t = Date.now();
            var seedArg = Memory.alloc(4); seedArg.writeS32(seed);
            invokeMethod(initializeSeedMi.info, innerRunner,
                [realConfig, seedArg, realTimeSource, options, realLogger, realReporter]);
            var isInit = innerRunner.add(runnerIsInitOff).readU8();
            timings.push({ step: "inner.Initialize(seed)", ms: Date.now() - t, isInit: isInit });
            if (!isInit) return { ok: false, reason: "inner not initialized", timings: timings };

            var innerAiControl = innerRunner.add(runnerAiControlOff).readPointer();

            // 6. Manual replay loop over our captured log
            t = Date.now();
            var stats = { top: 0, top_boot: 0, ai: 0, humanAi: 0,
                          skippedCheatRunAi: 0, errors: [] };
            for (var i = 0; i < log.length; i++) {
                var e = log[i];
                var msgPtr = ptr(e.ptr);
                try {
                    if (e.src === 'top' || e.src === 'top_boot') {
                        // CheatRunAI's side-effects are the captured 'ai' sub-messages
                        // that follow it — replaying it would re-trigger the AI and
                        // double-apply. Skip and let captured sub-messages drive state.
                        if (e.cls === 'CheatRunAIMessage') { stats.skippedCheatRunAi++; continue; }
                        invokeMethod(runnerApplyMi.info, innerRunner, [msgPtr]);
                        stats[e.src]++;
                    } else if (e.src === 'ai') {
                        invokeMethod(applyAiMsgMi.info, innerAiControl, [msgPtr]);
                        stats.ai++;
                    } else if (e.src === 'humanAi') {
                        invokeMethod(applyHumanAiMsgMi.info, innerAiControl, [msgPtr]);
                        stats.humanAi++;
                    }
                } catch (ex) {
                    stats.errors.push({ i: i, src: e.src, cls: e.cls, err: ex.message });
                    if (stats.errors.length >= 5) break;
                }
            }
            timings.push({ step: "replay loop", ms: Date.now() - t, stats: stats });

            // 7. Read inner state + compare with live via engine-only lookups
            t = Date.now();
            function extractCtx(state) {
                var list = state.add(msEntitiesOff).readPointer();
                var size = list.add(0x18).readS32();
                var items = list.add(0x10).readPointer();
                var owners = {}, currentTurnPlayer = null, nUnits = 0, nEntities = size;
                for (var i = 0; i < size; i++) {
                    var en = items.add(0x20 + i * 8).readPointer();
                    if (en.isNull()) continue;
                    var id = en.add(16).readS32();
                    var ty = en.add(20).readS32();
                    if (ty === ENTITY_TYPE_UNIT) {
                        nUnits++;
                        var o = en.add(32).readPointer();
                        if (!o.isNull()) {
                            var pid = o.add(16).readS32(), ov = o.add(20).readS32();
                            owners[id] = (ov !== 0) ? ov : pid;
                        }
                    } else if (ty === ENTITY_TYPE_MATCH) {
                        var tc = en.add(56).readPointer();
                        if (!tc.isNull()) currentTurnPlayer = tc.add(36).readS32();
                    }
                }
                return { owners: owners, currentTurnPlayer: currentTurnPlayer,
                         nUnits: nUnits, nEntities: nEntities };
            }
            var innerState = innerRunner.add(runnerStateOff).readPointer();
            var liveState = runnerInstance.add(runnerStateOff).readPointer();
            var innerCtx = extractCtx(innerState);
            var liveCtx = extractCtx(liveState);

            var ownerDiff = 0;
            var allIds = {};
            Object.keys(innerCtx.owners).forEach(function (k) { allIds[k] = true; });
            Object.keys(liveCtx.owners).forEach(function (k) { allIds[k] = true; });
            Object.keys(allIds).forEach(function (k) {
                if (innerCtx.owners[k] !== liveCtx.owners[k]) ownerDiff++;
            });
            timings.push({ step: "state extract + diff", ms: Date.now() - t });
            timings.push({ grand_total_ms: Date.now() - T0 });

            return {
                ok: stats.errors.length === 0,
                stats: stats,
                inner: innerCtx,
                live: liveCtx,
                diff: {
                    nEntitiesEqual: innerCtx.nEntities === liveCtx.nEntities,
                    nUnitsEqual: innerCtx.nUnits === liveCtx.nUnits,
                    currentTurnPlayerEqual: innerCtx.currentTurnPlayer === liveCtx.currentTurnPlayer,
                    ownerMismatches: ownerDiff
                },
                timings: timings,
                rr: rr.toString(),
                innerRunner: innerRunner.toString()
            };
        });
    },
    cheatRunAi: function () {
        return queueOnMainThread(function () {
            if (!runnerInstance) throw new Error("no runner");
            if (!cheatRunAiClass) throw new Error("CheatRunAIMessage class not found");
            var msg = createObject(cheatRunAiClass);
            var before = log.length;
            invokeMethod(runnerApplyMi.info, runnerInstance, [msg]);
            return { ok: true, before: before, after: log.length, delta: log.length - before };
        });
    },
    // Probe 1: our 'top' entries should match the native ReplayRecorder
    compareNative: function () {
        return queueOnMainThread(function () {
            if (!runnerInstance) throw new Error("no runner");
            var recorder = runnerInstance.add(runnerReplayRecorderOff).readPointer();
            if (recorder.isNull()) return { err: "recorder null" };
            var replay = invokeMethod(getReplayMi.info, recorder, null);
            if (replay.isNull()) return { err: "replay null" };
            var msgsList = replay.add(replayMessagesOff).readPointer();
            var size = msgsList.isNull() ? 0 : msgsList.add(0x18).readS32();
            var items = msgsList.isNull() ? null : msgsList.add(0x10).readPointer();
            var native = [];
            for (var i = 0; i < size; i++) {
                var step = items.add(0x20 + i * 8).readPointer();
                if (step.isNull()) continue;
                var turn = step.add(20).readS32();
                var inputMsg = step.add(32).readPointer();
                native.push({
                    i: i,
                    turn: turn,
                    cls: inputMsg.isNull() ? null : readMsgClass(inputMsg)
                });
            }
            var ourTop = log.filter(function (e) {
                return e.src === 'top' || e.src === 'top_boot';
            });
            var mismatches = [];
            var minLen = Math.min(native.length, ourTop.length);
            for (var j = 0; j < minLen; j++) {
                if (native[j].cls !== ourTop[j].cls) {
                    mismatches.push({ i: j, native: native[j].cls, ours: ourTop[j].cls });
                }
            }
            return {
                nativeCount: native.length,
                ourTopCount: ourTop.length,
                ourAiCount: log.filter(function(e){return e.src==='ai';}).length,
                ourHumanAiCount: log.filter(function(e){return e.src==='humanAi';}).length,
                sameSize: native.length === ourTop.length,
                mismatches: mismatches,
                nativeHead: native.slice(0, 10),
                ourTopHead: ourTop.slice(0, 10)
            };
        });
    },

    // Standalone path (no ReplayRunner):
    //   1. build fresh standalone IdunRunner via buildStandaloneRunner(),
    //   2. dispatch ALL our log entries (top + top_boot + ai + humanAi),
    //      skipping CheatRunAIMessage (trigger, not a state mutation),
    //   3. compare state digest + PRNG with live.
    compareStandalone: function () {
        return queueOnMainThread(function () {
            var result = { phases: [] };
            var step = "start";
            function tryStep(name, fn) {
                step = name;
                try { var r = fn() || {}; result.phases.push(Object.assign({ step: name }, r)); return r; }
                catch (e) { result.phases.push({ step: name, err: e.message }); throw e; }
            }

            function snapshotPrng(runnerPtr) {
                var mt = runnerPtr.add(runnerRngOff).readPointer();
                for (var hop = 0; hop < 4; hop++) {
                    if (s(class_get_name(mt.readPointer())).indexOf("MersenneTwister") >= 0) break;
                    var n = mt.add(16).readPointer();
                    if (n.isNull() || n.equals(mt)) break;
                    mt = n;
                }
                var arr = mt.add(32).readPointer();
                var len = arr.isNull() ? 0 : arr.add(0x18).readS32();
                var h = 2166136261 >>> 0;
                for (var i = 0; i < len; i++) {
                    var w32 = arr.add(0x20 + i * 4).readU32() >>> 0;
                    h = Math.imul(h ^ (w32 & 0xff), 16777619) >>> 0;
                    h = Math.imul(h ^ ((w32 >>> 8) & 0xff), 16777619) >>> 0;
                    h = Math.imul(h ^ ((w32 >>> 16) & 0xff), 16777619) >>> 0;
                    h = Math.imul(h ^ ((w32 >>> 24) & 0xff), 16777619) >>> 0;
                }
                return { seed: mt.add(16).readS32(), count: mt.add(20).readS32(),
                         mti: mt.add(40).readS32(), digest: "0x" + h.toString(16) };
            }
            function digestState(statePtr) {
                if (!serializeMi) return null;
                var jp = invokeMethod(serializeMi.info, ptr(0), [statePtr]);
                if (jp.isNull()) return null;
                var str = _readIl2cppStringLarge(jp);
                if (!str) return null;
                var h = 2166136261 >>> 0;
                for (var i = 0; i < str.length; i++) {
                    h = Math.imul(h ^ (str.charCodeAt(i) & 0xff), 16777619) >>> 0;
                }
                return { bytes: str.length, digest: "0x" + h.toString(16) };
            }
            function readTurn(runnerPtr) {
                var list = runnerPtr.add(runnerStateOff).readPointer().add(msEntitiesOff).readPointer();
                var sz = list.add(0x18).readS32();
                var it = list.add(0x10).readPointer();
                for (var k = 0; k < sz; k++) {
                    var e = it.add(0x20 + k * 8).readPointer();
                    if (e.isNull()) continue;
                    if (e.add(20).readS32() === ENTITY_TYPE_MATCH) {
                        var tc = e.add(56).readPointer();
                        if (!tc.isNull()) return tc.add(36).readS32();
                    }
                }
                return null;
            }
            function entityCensus(statePtr) {
                var list = statePtr.add(msEntitiesOff).readPointer();
                if (list.isNull()) return null;
                var sz = list.add(0x18).readS32();
                var it = list.add(0x10).readPointer();
                var byType = {};
                for (var k = 0; k < sz; k++) {
                    var e = it.add(0x20 + k * 8).readPointer();
                    if (e.isNull()) continue;
                    var id = e.add(16).readS32();
                    var ty = e.add(20).readS32();
                    if (!byType[ty]) byType[ty] = [];
                    byType[ty].push(id);
                }
                for (var t in byType) byType[t].sort(function (a, b) { return a - b; });
                return { total: sz, byType: byType };
            }
            // Serialize state to full Newtonsoft JSON and push it to the PC
            // via send(). The server writes each send() as a line in
            // logs/run-<session>.jsonl, so dumps are cheap to grep / jq.
            function dumpState(runnerName, statePtr) {
                if (!serializeMi || statePtr.isNull()) return null;
                var jp = null;
                try { jp = invokeMethod(serializeMi.info, ptr(0), [statePtr]); }
                catch (ex) { return { err: ex.message }; }
                if (!jp || jp.isNull()) return { err: "serialize null" };
                var str = _readIl2cppStringLarge(jp);
                if (!str) return { err: "string read failed" };
                send({ t: "state_dump", runner: runnerName, bytes: str.length, json: str });
                return { bytes: str.length };
            }

            var livePrng, liveState, liveTurn, built;
            var standaloneTrace = [];

            try {
                tryStep("live snapshot", function () {
                    livePrng = snapshotPrng(runnerInstance);
                    liveState = digestState(runnerInstance.add(runnerStateOff).readPointer());
                    liveTurn = readTurn(runnerInstance);
                    return { prng: livePrng, state: liveState, turn: liveTurn };
                });
                tryStep("build standalone", function () {
                    built = buildStandaloneRunner();
                    return { seed: built.seed,
                             isInit: built.standalone.add(runnerIsInitOff).readU8() };
                });
                tryStep("dispatch log on standalone", function () {
                    var stats = { top: 0, top_boot: 0, ai: 0, humanAi: 0,
                                  skippedCheatRunAi: 0, errors: [] };
                    for (var i = 0; i < log.length; i++) {
                        var e = log[i];
                        var msgPtr = ptr(e.ptr);
                        if ((e.src === 'top' || e.src === 'top_boot') && e.cls === 'CheatRunAIMessage') {
                            stats.skippedCheatRunAi++;
                            continue;
                        }
                        var evts = [];
                        var traceEntry = { logIdx: i, src: e.src, cls: e.cls,
                                           unitId: e.unitId, events: evts };
                        traceEntry.turnBefore = readTurn(built.standalone);
                        standaloneTrace.push(traceEntry);
                        pushApply('standalone', evts);
                        try {
                            invokeMethod(runnerApplyMi.info, built.standalone, [msgPtr]);
                            stats[e.src]++;
                        } catch (ex) {
                            stats.errors.push({ i: i, src: e.src, cls: e.cls,
                                                unitId: e.unitId,
                                                turnBefore: traceEntry.turnBefore,
                                                err: ex.message });
                            if (stats.errors.length >= 3) { popApply(); break; }
                        }
                        popApply();
                        traceEntry.turnAfter = readTurn(built.standalone);
                    }
                    return stats;
                });
                var standalonePrng, standaloneState, standaloneTurn;
                tryStep("standalone snapshot", function () {
                    standalonePrng = snapshotPrng(built.standalone);
                    standaloneState = digestState(built.standalone.add(runnerStateOff).readPointer());
                    standaloneTurn = readTurn(built.standalone);
                    return { prng: standalonePrng, state: standaloneState, turn: standaloneTurn };
                });
                tryStep("entity census", function () {
                    result.liveCensus = entityCensus(runnerInstance.add(runnerStateOff).readPointer());
                    result.standaloneCensus = entityCensus(built.standalone.add(runnerStateOff).readPointer());
                    return { live: result.liveCensus, standalone: result.standaloneCensus };
                });
                tryStep("push state dumps + event traces via send()", function () {
                    var liveDump = dumpState("live", runnerInstance.add(runnerStateOff).readPointer());
                    var saDump = dumpState("standalone", built.standalone.add(runnerStateOff).readPointer());
                    // Live events: copy from log[*].events into a compact array
                    var liveTrace = log.map(function (e) {
                        return { logIdx: e.idx, src: e.src, cls: e.cls,
                                 unitId: e.unitId || null, events: e.events || [] };
                    });
                    send({ t: "event_trace", runner: "live", trace: liveTrace });
                    send({ t: "event_trace", runner: "standalone", trace: standaloneTrace });
                    return { liveDump: liveDump, standaloneDump: saDump,
                             liveTraceEntries: liveTrace.length,
                             standaloneTraceEntries: standaloneTrace.length };
                });
                result.diff = {
                    turnMatch: liveTurn === standaloneTurn,
                    prngCountMatch: livePrng.count === standalonePrng.count,
                    prngCountDelta: standalonePrng.count - livePrng.count,
                    prngMtiMatch: livePrng.mti === standalonePrng.mti,
                    prngDigestMatch: livePrng.digest === standalonePrng.digest,
                    stateDigestMatch: liveState && standaloneState &&
                                      liveState.digest === standaloneState.digest,
                    liveBytes: liveState ? liveState.bytes : null,
                    standaloneBytes: standaloneState ? standaloneState.bytes : null,
                    bytesDelta: liveState && standaloneState ?
                                standaloneState.bytes - liveState.bytes : null
                };
            } catch (e) {
                result.crashAt = step;
                result.err = e.message;
                // Make sure we don't leave a dangling stack entry
                while (applyStack.length > 0 && applyStack[applyStack.length - 1].role === 'standalone') popApply();
            }
            return result;
        });
    }
};

console.log("[*] full-recorder loaded");
