// Phase: simulate a turn via ReplayRunner (no field swap, isolated runner).
//
// Plan:
//   1. Read the LIVE runner's _replayRecorder → call GetReplay() to snapshot
//      everything since StartMatch.
//   2. (Future) Build a fresh ReplayRunner fed with that Replay, fast-forward,
//      run AI, read final state.
//
// For now this hook only does steps 1+2 (inspect the Replay) and times each step.
// We don't yet instantiate ReplayRunner until we confirm the Replay is non-empty
// and looks correct.

send({ t: "hook_ready", name: "replay-sim", version: 1 });

// --- classes ---
var _gameViewsClass = findClass("Assembly-CSharp.dll", "IdunBattle.View.Game", "IdunGameViews");
var _gvRunnerOff = _gameViewsClass ? getFieldOffset(_gameViewsClass, "_runner") : -1;

var runnerClass = findClass("BattleLogicAssembly.dll", "IdunBattle.Runner", "IdunRunner");
var runnerReplayRecorderOff = runnerClass ? getFieldOffset(runnerClass, "_replayRecorder") : -1;
var runnerLoggerOff = runnerClass ? getFieldOffset(runnerClass, "_logger") : -1;
var runnerTimeSourceOff = runnerClass ? getFieldOffset(runnerClass, "_timeSource") : -1;

var replayRecorderClass = findClass("BattleLogicAssembly.dll", "IdunBattleLogic.Replay", "ReplayRecorder");
var getReplayMi = replayRecorderClass ? findMethod(replayRecorderClass, "GetReplay") : null;

var replayClass = findClass("BattleLogicAssembly.dll", "IdunBattleLogic.Replay", "Replay");
var replayMessagesOff = replayClass ? getFieldOffset(replayClass, "Messages") : -1;
var replayRngSeedOff = replayClass ? getFieldOffset(replayClass, "RngSeed") : -1;
var replayBattleConfigOff = replayClass ? getFieldOffset(replayClass, "BattleConfiguration") : -1;
var replayRecordedPlayerIdsOff = replayClass ? getFieldOffset(replayClass, "RecordedPlayerIds") : -1;
var replayStartingTsOff = replayClass ? getFieldOffset(replayClass, "StartingTimestamp") : -1;

// --- state ---
var runnerInstance = null;
var gameViewsInstance = null;
var pending = [];

// --- main-thread queue ---
if (_gameViewsClass && _gvRunnerOff >= 0) {
    var updateMi = findMethod(_gameViewsClass, "Update");
    if (updateMi) {
        var _origUpdate = new NativeFunction(updateMi.ptr, "void", ["pointer", "pointer"]);
        Interceptor.replace(updateMi.ptr, new NativeCallback(function (self, methodInfo) {
            if (!gameViewsInstance) gameViewsInstance = self;
            // Re-capture on every tick so a new battle's runner replaces the stale one
            var r = self.add(_gvRunnerOff).readPointer();
            if (!r.isNull() && !r.equals(runnerInstance || ptr(0))) runnerInstance = r;
            while (pending.length > 0) {
                var req = pending.shift();
                try { req.resolve(req.fn()); }
                catch (e) { req.reject(e.message); }
            }
            _origUpdate(self, methodInfo);
        }, "void", ["pointer", "pointer"]));
    }
}

function queueOnMainThread(fn) {
    return new Promise(function (resolve, reject) {
        pending.push({ fn: fn, resolve: resolve, reject: function (m) { reject(new Error(m)); } });
    });
}

// High-resolution timing
var hrtime = function () {
    try { return Process.getCurrentThreadId() && performance.now(); } catch (e) { return Date.now(); }
};

// --- probe the replay ---
function doProbeReplay() {
    if (!runnerInstance) throw new Error("runner not captured");
    if (!getReplayMi || getReplayMi.ptr.isNull()) throw new Error("GetReplay not resolved");

    var timings = [];
    var t0 = Date.now();

    // Step 1: read recorder ptr
    var t = Date.now();
    var recorder = runnerInstance.add(runnerReplayRecorderOff).readPointer();
    timings.push({ step: "read _replayRecorder", ms: Date.now() - t, ptr: recorder.toString(), isNull: recorder.isNull() });
    if (recorder.isNull()) {
        return { ok: false, reason: "_replayRecorder is null", timings: timings };
    }
    var recorderKlassName = s(class_get_name(recorder.readPointer()));
    timings.push({ info: "recorder class", name: recorderKlassName });

    // Step 2: call GetReplay()
    t = Date.now();
    var replay = invokeMethod(getReplayMi.info, recorder, null);
    timings.push({ step: "GetReplay()", ms: Date.now() - t, ptr: replay.toString(), isNull: replay.isNull() });
    if (replay.isNull()) {
        return { ok: false, reason: "GetReplay returned null", timings: timings };
    }

    // Step 3: inspect Replay fields
    t = Date.now();
    var rngSeed = replay.add(replayRngSeedOff).readS32();
    var startingTs = replay.add(replayStartingTsOff).readS64();
    var battleConfig = replay.add(replayBattleConfigOff).readPointer();
    var msgsList = replay.add(replayMessagesOff).readPointer();
    var playerIdsList = replay.add(replayRecordedPlayerIdsOff).readPointer();

    var msgCount = -1;
    if (!msgsList.isNull()) msgCount = msgsList.add(0x18).readS32();
    var playerCount = -1;
    if (!playerIdsList.isNull()) playerCount = playerIdsList.add(0x18).readS32();

    timings.push({ step: "read Replay fields", ms: Date.now() - t });
    timings.push({
        info: "replay content",
        rngSeed: rngSeed,
        startingTs: startingTs.toString(),
        battleConfig: battleConfig.toString(),
        msgsListPtr: msgsList.toString(),
        msgCount: msgCount,
        playerIdsListPtr: playerIdsList.toString(),
        playerCount: playerCount
    });

    timings.push({ total_ms: Date.now() - t0 });

    return { ok: true, timings: timings };
}

// --- ReplayRunner construction + execution probe ---
var replayRunnerClass = findClass("BattleLogicAssembly.dll", "IdunBattle.Runner", "ReplayRunner");
var idunRunnerOptionsClass = findClass("BattleLogicAssembly.dll", "IdunBattle.Runner", "IdunRunnerOptions");

// Find Initialize overloads. One takes (config, seed, ...) the other (config, prng, ...)
var initializePrngMi = null;
var initializeSeedMi = null;
if (runnerClass) {
    var it = Memory.alloc(Process.pointerSize); it.writePointer(ptr(0));
    var param_count_fn = new NativeFunction(il2cpp.findExportByName("il2cpp_method_get_param_count"), "uint32", ["pointer"]);
    var param_get_type_fn = new NativeFunction(il2cpp.findExportByName("il2cpp_method_get_param"), "pointer", ["pointer", "uint32"]);
    var type_name_fn = new NativeFunction(il2cpp.findExportByName("il2cpp_type_get_name"), "pointer", ["pointer"]);
    var m;
    while (!(m = class_get_methods(runnerClass, it)).isNull()) {
        if (s(method_get_name(m)) !== "Initialize") continue;
        if (param_count_fn(m) !== 6) continue;
        var p1Type = param_get_type_fn(m, 1);
        var p1Name = s(type_name_fn(p1Type));
        if (p1Name.indexOf("Int32") >= 0) initializeSeedMi = { info: m, ptr: m.readPointer() };
        else if (p1Name.indexOf("IPseudoRNG") >= 0) initializePrngMi = { info: m, ptr: m.readPointer() };
    }
}

var runnerRngOff = runnerClass ? getFieldOffset(runnerClass, "_randomNumberGenerator") : -1;
var runnerConfigOff = runnerClass ? getFieldOffset(runnerClass, "<Configuration>k__BackingField") : -1;
var runnerIsInitOff = runnerClass ? getFieldOffset(runnerClass, "_isInitialized") : -1;

// Find ReplayRunner 3-arg ctor (logger, runner, replay, timeSource)
function findCtorByParamTypes(klass, expectedTypes) {
    var it = Memory.alloc(Process.pointerSize); it.writePointer(ptr(0));
    var param_count_fn = new NativeFunction(il2cpp.findExportByName("il2cpp_method_get_param_count"), "uint32", ["pointer"]);
    var param_get_type_fn = new NativeFunction(il2cpp.findExportByName("il2cpp_method_get_param"), "pointer", ["pointer", "uint32"]);
    var type_name_fn = new NativeFunction(il2cpp.findExportByName("il2cpp_type_get_name"), "pointer", ["pointer"]);
    var m;
    while (!(m = class_get_methods(klass, it)).isNull()) {
        if (s(method_get_name(m)) !== ".ctor") continue;
        if (param_count_fn(m) !== expectedTypes.length) continue;
        var match = true;
        for (var i = 0; i < expectedTypes.length; i++) {
            var p = param_get_type_fn(m, i);
            var pn = s(type_name_fn(p));
            if (pn.indexOf(expectedTypes[i]) < 0) { match = false; break; }
        }
        if (match) return { info: m, ptr: m.readPointer() };
    }
    return null;
}

var replayRunnerCtor3_runner = replayRunnerClass
    ? findCtorByParamTypes(replayRunnerClass, ["IIdunLogger", "IdunRunner", "Replay", "ITimeSource"])
    : null;
var idunRunnerCtor = runnerClass ? findMethod(runnerClass, ".ctor") : null;
var idunRunnerOptionsCtor = idunRunnerOptionsClass ? findMethod(idunRunnerOptionsClass, ".ctor") : null;
var runnerApplyMi = runnerClass ? findMethod(runnerClass, "Apply") : null;
var cheatRunAiClass = findClass("BattleLogicAssembly.dll", "IdunBattle.Messages", "CheatRunAIMessage");

var aiControlClass = findClass("BattleLogicAssembly.dll", "IdunBattle.Core.Services", "AiControl");
var applyAiMsgMi = aiControlClass ? findMethod(aiControlClass, "ApplyAiMessage") : null;
var applyHumanAiMsgMi = aiControlClass ? findMethod(aiControlClass, "ApplyHumanAiMessage") : null;
var isPlayersTurnMi = aiControlClass ? findMethod(aiControlClass, "IsPlayersTurn") : null;
var runnerAiControlOff = runnerClass ? getFieldOffset(runnerClass, "_aiControl") : -1;

// Enumerate all .ctor overloads and pick by parameter signature
function findCtorByParamCount(klass, paramCount) {
    var it = Memory.alloc(Process.pointerSize); it.writePointer(ptr(0));
    var m;
    var param_count_fn = new NativeFunction(il2cpp.findExportByName("il2cpp_method_get_param_count"), "uint32", ["pointer"]);
    while (!(m = class_get_methods(klass, it)).isNull()) {
        if (s(method_get_name(m)) !== ".ctor") continue;
        try {
            var pc = param_count_fn(m);
            if (pc === paramCount) return { info: m, ptr: m.readPointer(), paramCount: pc };
        } catch (e) { }
    }
    return null;
}

var replayRunnerCtor4 = replayRunnerClass ? findCtorByParamCount(replayRunnerClass, 4) : null;
var initBattleMi = replayRunnerClass ? findMethod(replayRunnerClass, "InitializeBattle") : null;
var runAllStepsMi = replayRunnerClass ? findMethod(replayRunnerClass, "RunAllSteps") : null;
var runAiMi = replayRunnerClass ? findMethod(replayRunnerClass, "RunAi") : null;
var getStateMi = replayRunnerClass ? findMethod(replayRunnerClass, "GetState") : null;
var getRemainingStepsMi = replayRunnerClass ? findMethod(replayRunnerClass, "get_RemainingSteps") : null;

function doCreateReplayRunner() {
    if (!runnerInstance) throw new Error("runner not captured");
    if (!gcRoot.init()) throw new Error("gcRoot init failed");
    if (!replayRunnerClass) throw new Error("ReplayRunner class not found");
    if (!replayRunnerCtor4) throw new Error("4-arg ctor not found");

    var timings = [];
    var grandT0 = Date.now();

    // 1) Get Replay
    var t = Date.now();
    var recorder = runnerInstance.add(runnerReplayRecorderOff).readPointer();
    var replay = invokeMethod(getReplayMi.info, recorder, null);
    gcRoot.add(replay);
    timings.push({ step: "GetReplay + root", ms: Date.now() - t });

    // 2) Grab logger + timeSource from real runner
    var logger = runnerInstance.add(runnerLoggerOff).readPointer();
    var timeSource = runnerInstance.add(runnerTimeSourceOff).readPointer();

    // 3) Build Nullable<Int32> = null (hasValue=false)
    var maxAiSteps = Memory.alloc(8); maxAiSteps.writeU64(0);

    // 4) Instantiate ReplayRunner + call 4-arg ctor
    t = Date.now();
    var rr = il2cpp_object_new(replayRunnerClass);
    gcRoot.add(rr);
    invokeMethod(replayRunnerCtor4.info, rr, [logger, replay, timeSource, maxAiSteps]);
    timings.push({ step: "new ReplayRunner + ctor", ms: Date.now() - t, rr: rr.toString() });

    // 5) Inspect RR fields to see if ctor populated them
    var rrRunnerOff = getFieldOffset(replayRunnerClass, "_runner");
    var rrSeedOff = getFieldOffset(replayRunnerClass, "_seed");
    var rrInputMessagesOff = getFieldOffset(replayRunnerClass, "_inputMessages");
    var rrReplayMetaDataOff = getFieldOffset(replayRunnerClass, "_replayMetaData");
    var rrRunner = rr.add(rrRunnerOff).readPointer();
    var rrSeed = rr.add(rrSeedOff).readS32();
    var rrInputMsgs = rr.add(rrInputMessagesOff).readPointer();
    var rrMeta = rr.add(rrReplayMetaDataOff).readPointer();
    var rrBattleConfigOff = getFieldOffset(replayRunnerClass, "_battleConfig");
    var rrBattleConfig = rr.add(rrBattleConfigOff).readPointer();
    var populated = {
        _runner: rrRunner.toString(),
        _runner_isNull: rrRunner.isNull(),
        _seed: rrSeed,
        _battleConfig: rrBattleConfig.toString(),
        _battleConfig_isNull: rrBattleConfig.isNull(),
        _inputMessages: rrInputMsgs.toString(),
        _replayMetaData: rrMeta.toString()
    };

    // Inspect the inner IdunRunner's fields — is it Initialize'd?
    if (!rrRunner.isNull()) {
        var innerRunnerClass = runnerClass;
        var innerStateOff = getFieldOffset(innerRunnerClass, "_state");
        var innerConfigOff = getFieldOffset(innerRunnerClass, "<Configuration>k__BackingField");
        var innerAiControlOff = getFieldOffset(innerRunnerClass, "_aiControl");
        var innerOpProcOff = getFieldOffset(innerRunnerClass, "<OperationProcessor>k__BackingField");
        var innerIsInitOff = getFieldOffset(innerRunnerClass, "_isInitialized");
        populated.innerRunner = {
            _state: rrRunner.add(innerStateOff).readPointer().toString(),
            _isInitialized: rrRunner.add(innerIsInitOff).readU8(),
            Configuration: rrRunner.add(innerConfigOff).readPointer().toString(),
            _aiControl: rrRunner.add(innerAiControlOff).readPointer().toString(),
            OperationProcessor: rrRunner.add(innerOpProcOff).readPointer().toString()
        };
    }

    timings.push({ info: "fields after ctor", populated: populated });
    timings.push({ grand_total_ms: Date.now() - grandT0 });
    return { ok: true, timings: timings };
}

function doFullSim() {
    send({ t: "sim_step", step: "enter doFullSim" });
    if (!runnerInstance) throw new Error("runner not captured");
    if (!gcRoot.init()) throw new Error("gcRoot init failed");

    var timings = [];
    var grandT0 = Date.now();

    // 1. GetReplay + root
    send({ t: "sim_step", step: "before GetReplay" });
    var t = Date.now();
    var recorder = runnerInstance.add(runnerReplayRecorderOff).readPointer();
    var replay = invokeMethod(getReplayMi.info, recorder, null);
    gcRoot.add(replay);
    timings.push({ step: "GetReplay", ms: Date.now() - t });
    send({ t: "sim_step", step: "after GetReplay", replay: replay.toString() });

    // 2. Build ReplayRunner
    send({ t: "sim_step", step: "before new ReplayRunner" });
    t = Date.now();
    var logger = runnerInstance.add(runnerLoggerOff).readPointer();
    var timeSource = runnerInstance.add(runnerTimeSourceOff).readPointer();
    var maxAiSteps = Memory.alloc(8); maxAiSteps.writeU64(0);
    var rr = il2cpp_object_new(replayRunnerClass);
    gcRoot.add(rr);
    invokeMethod(replayRunnerCtor4.info, rr, [logger, replay, timeSource, maxAiSteps]);
    timings.push({ step: "new ReplayRunner", ms: Date.now() - t });
    send({ t: "sim_step", step: "after new ReplayRunner", rr: rr.toString() });

    // 3. InitializeBattle
    send({ t: "sim_step", step: "before InitializeBattle", rr: rr.toString() });
    t = Date.now();
    var initErr = null;
    try { invokeMethod(initBattleMi.info, rr, null); }
    catch (e) { initErr = e.message; }
    timings.push({ step: "InitializeBattle", ms: Date.now() - t, err: initErr });
    send({ t: "sim_step", step: "after InitializeBattle", err: initErr, ms: Date.now() - t });
    if (initErr) return { ok: false, timings: timings };

    // 4. RunAllSteps(runSim=false, runAi=false) — fast-forward recorded messages
    send({ t: "sim_step", step: "before RunAllSteps" });
    t = Date.now();
    var boolFalse = Memory.alloc(1); boolFalse.writeU8(0);
    var runAllErr = null;
    try { invokeMethod(runAllStepsMi.info, rr, [boolFalse, boolFalse]); }
    catch (e) { runAllErr = e.message; }
    timings.push({ step: "RunAllSteps", ms: Date.now() - t, err: runAllErr });
    send({ t: "sim_step", step: "after RunAllSteps", err: runAllErr, ms: Date.now() - t });

    // 5. Query remaining steps
    t = Date.now();
    var boxedRemaining = invokeMethod(getRemainingStepsMi.info, rr, null);
    var remaining = boxedRemaining.isNull() ? -1 : boxedRemaining.add(0x10).readS32();
    timings.push({ step: "get_RemainingSteps", ms: Date.now() - t, remaining: remaining });

    // 6. RunAi — our simulation
    t = Date.now();
    var runAiErr = null;
    try { invokeMethod(runAiMi.info, rr, null); }
    catch (e) { runAiErr = e.message; }
    timings.push({ step: "RunAi", ms: Date.now() - t, err: runAiErr });

    // 7. GetState
    t = Date.now();
    var simState = invokeMethod(getStateMi.info, rr, null);
    timings.push({ step: "GetState", ms: Date.now() - t, simState: simState.toString() });

    timings.push({ grand_total_ms: Date.now() - grandT0 });

    // Cleanup: release rr and replay
    gcRoot.remove(rr);
    gcRoot.remove(replay);

    return { ok: true, timings: timings };
}

// Build a fully isolated ReplayRunner and return {rr, innerRunner, replay}
function buildIsolatedReplayRunner() {
    var recorder = runnerInstance.add(runnerReplayRecorderOff).readPointer();
    var replay = invokeMethod(getReplayMi.info, recorder, null);
    gcRoot.add(replay);

    var realConfig = runnerInstance.add(runnerConfigOff).readPointer();
    var realTimeSource = runnerInstance.add(runnerTimeSourceOff).readPointer();
    var realLogger = runnerInstance.add(runnerLoggerOff).readPointer();
    var opProc = runnerInstance.add(192).readPointer();
    var startMatchOp = opProc.add(528).readPointer();
    var realReporter = startMatchOp.add(48).readPointer();

    var options = il2cpp_object_new(idunRunnerOptionsClass);
    gcRoot.add(options);
    invokeMethod(idunRunnerOptionsCtor.info, options, null);
    options.add(16).writeU8(0); // RecordReplay=false (sim runner doesn't need to record)

    var maxAiSteps = Memory.alloc(8); maxAiSteps.writeU64(0);
    var rr = il2cpp_object_new(replayRunnerClass);
    gcRoot.add(rr);
    invokeMethod(replayRunnerCtor4.info, rr, [realLogger, replay, realTimeSource, maxAiSteps]);
    var innerRunner = rr.add(getFieldOffset(replayRunnerClass, "_runner")).readPointer();

    var replaySeed = replay.add(replayRngSeedOff).readS32();
    var seedArg = Memory.alloc(4); seedArg.writeS32(replaySeed);
    invokeMethod(initializeSeedMi.info, innerRunner,
        [realConfig, seedArg, realTimeSource, options, realLogger, realReporter]);

    // Try InitializeBattle now that inner runner is Initialize'd
    var ibErr = null;
    try { invokeMethod(initBattleMi.info, rr, null); }
    catch (e) { ibErr = e.message; }
    // If InitializeBattle succeeded we don't need to set _didInitBattle manually
    if (ibErr) {
        rr.add(getFieldOffset(replayRunnerClass, "_didInitBattle")).writeU8(1);
    }

    return { rr: rr, innerRunner: innerRunner, replay: replay };
}

// Simulate + capture messages the AI emits on the inner runner, then replay on the real runner.
function doSimAndCommit() {
    if (!runnerInstance) throw new Error("runner not captured");
    if (!gcRoot.init()) throw new Error("gcRoot init failed");

    var timings = [];
    var T0 = Date.now();
    try {
        var t = Date.now();
        var built = buildIsolatedReplayRunner();
        timings.push({ step: "build isolated RR", ms: Date.now() - t,
                       innerRunner: built.innerRunner.toString() });

        // RunAllSteps(runSimReqs=true, runRemainingAi=false)
        // — only replay recorded messages, don't run AI for remaining turns
        // (we'll run AI ourselves with the capture interceptor installed)
        t = Date.now();
        var boolTrue = Memory.alloc(1); boolTrue.writeU8(1);
        var boolFalse = Memory.alloc(1); boolFalse.writeU8(0);
        var rasErr0 = null;
        try { invokeMethod(runAllStepsMi.info, built.rr, [boolTrue, boolFalse]); }
        catch (e) { rasErr0 = e.message; }
        timings.push({ step: "RunAllSteps(simReqs=true, ai=false)", ms: Date.now() - t, err: rasErr0 });

        // (no probe — will crash if innerAiControl is briefly null; not critical)
        if (rasErr0) {
            // Try to read _nextStepIndex to see how far it got
            var nsiOff = getFieldOffset(replayRunnerClass, "_nextStepIndex");
            var nsi = built.rr.add(nsiOff).readS32();
            timings.push({ info: "progress before crash", nextStepIndex: nsi });
            return { ok: false, timings: timings };
        }

        // Install AiControl.ApplyAiMessage + ApplyHumanAiMessage interceptors
        // filtered on the INNER runner's aiControl (avoids capturing real game events)
        var innerAiControl = built.innerRunner.add(runnerAiControlOff).readPointer();
        var captured = [];
        var listeners = [];
        function attachAi(mi, tag) {
            if (!mi || mi.ptr.isNull()) return;
            listeners.push(Interceptor.attach(mi.ptr, {
                onEnter: function (args) {
                    if (!args[0].equals(innerAiControl)) return;
                    try {
                        var msg = args[1];
                        captured.push({ src: tag, cls: readMsgClass(msg), ptr: msg.toString() });
                        gcRoot.add(msg);
                    } catch (e) { captured.push({ src: tag, err: e.message }); }
                }
            }));
        }
        attachAi(applyAiMsgMi, "ApplyAiMessage");
        attachAi(applyHumanAiMsgMi, "ApplyHumanAiMessage");
        Interceptor.flush();

        // Trigger AI via CheatRunAIMessage on inner runner — more reliable than RunAi
        t = Date.now();
        var raErr = null;
        try {
            var cheatMsg = createObject(cheatRunAiClass);
            gcRoot.add(cheatMsg);
            invokeMethod(runnerApplyMi.info, built.innerRunner, [cheatMsg]);
        } catch (e) { raErr = e.message; }
        for (var li = 0; li < listeners.length; li++) listeners[li].detach();
        timings.push({ step: "CheatRunAI on inner", ms: Date.now() - t, err: raErr, capturedCount: captured.length });

        if (raErr) return { ok: false, timings: timings, captured: captured };

        // Apply captured messages on the REAL runner's AiControl (not IdunRunner.Apply —
        // MoveUnitMessage/AiMessage is rejected by the InputProcessor validator).
        t = Date.now();
        var realAiControl = runnerInstance.add(runnerAiControlOff).readPointer();
        var applyErrors = [];
        var appliedOk = 0;
        for (var i = 0; i < captured.length; i++) {
            if (captured[i].err) { applyErrors.push({ i: i, err: "skipped — capture error" }); continue; }
            var applyTargetMi = (captured[i].src === "ApplyHumanAiMessage") ? applyHumanAiMsgMi : applyAiMsgMi;
            try {
                invokeMethod(applyTargetMi.info, realAiControl, [ptr(captured[i].ptr)]);
                appliedOk++;
            } catch (e) {
                applyErrors.push({ i: i, cls: captured[i].cls, err: e.message });
            }
        }
        timings.push({ step: "replay on real AiControl", ms: Date.now() - t,
                       applied: appliedOk, errors: applyErrors.length });

        timings.push({ grand_total_ms: Date.now() - T0 });
        return {
            ok: applyErrors.length === 0,
            timings: timings,
            captured: captured,
            applyErrors: applyErrors
        };
    } catch (e) {
        timings.push({ step: "UNCAUGHT", err: e.message });
        return { ok: false, timings: timings };
    }
}

// Alternate flow: use 4-arg ReplayRunner ctor (which populates SimulationRequestRunner etc.),
// THEN manually Initialize the inner runner via IdunRunner.Initialize.
function doHybridSim() {
    var timings = [];
    try {
        if (!gcRoot.init()) throw new Error("gcRoot init failed");

        var t = Date.now();
        var recorder = runnerInstance.add(runnerReplayRecorderOff).readPointer();
        var replay = invokeMethod(getReplayMi.info, recorder, null);
        gcRoot.add(replay);
        timings.push({ step: "GetReplay", ms: Date.now() - t });

        var realConfig = runnerInstance.add(runnerConfigOff).readPointer();
        var realPrng = runnerInstance.add(runnerRngOff).readPointer();
        var realTimeSource = runnerInstance.add(runnerTimeSourceOff).readPointer();
        var realLogger = runnerInstance.add(runnerLoggerOff).readPointer();
        var opProc = runnerInstance.add(192).readPointer();
        var startMatchOp = opProc.add(528).readPointer();
        var realReporter = startMatchOp.add(48).readPointer();

        // 4-arg ctor — creates and populates inner runner (non-init) + simReqRunner
        t = Date.now();
        var options = il2cpp_object_new(idunRunnerOptionsClass);
        gcRoot.add(options);
        invokeMethod(idunRunnerOptionsCtor.info, options, null);
        options.add(16).writeU8(1);  // RecordReplay=true

        var maxAiSteps = Memory.alloc(8); maxAiSteps.writeU64(0);
        var rr = il2cpp_object_new(replayRunnerClass);
        gcRoot.add(rr);
        invokeMethod(replayRunnerCtor4.info, rr, [realLogger, replay, realTimeSource, maxAiSteps]);
        var innerRunner = rr.add(getFieldOffset(replayRunnerClass, "_runner")).readPointer();
        timings.push({ step: "new ReplayRunner(4-arg)", ms: Date.now() - t, rr: rr.toString(), innerRunner: innerRunner.toString() });

        // Initialize the inner runner — use SEED overload (fresh PRNG, isolates from real game)
        t = Date.now();
        var replaySeed = replay.add(replayRngSeedOff).readS32();
        var seedArg = Memory.alloc(4); seedArg.writeS32(replaySeed);
        invokeMethod(initializeSeedMi.info, innerRunner,
            [realConfig, seedArg, realTimeSource, options, realLogger, realReporter]);
        var isInit = innerRunner.add(runnerIsInitOff).readU8();
        timings.push({ step: "inner Initialize (seed=" + replaySeed + ")", ms: Date.now() - t, isInit: isInit });

        // Skip InitializeBattle — set _didInitBattle=true manually
        rr.add(getFieldOffset(replayRunnerClass, "_didInitBattle")).writeU8(1);
        timings.push({ step: "skipped InitializeBattle, set _didInitBattle=true" });

        // RunAllSteps(false, false) — fast-forward recorded messages
        t = Date.now();
        var boolFalse = Memory.alloc(1); boolFalse.writeU8(0);
        var rasErr = null;
        try { invokeMethod(runAllStepsMi.info, rr, [boolFalse, boolFalse]); }
        catch (e) { rasErr = e.message; }
        timings.push({ step: "RunAllSteps(false,false)", ms: Date.now() - t, err: rasErr });
        if (rasErr) return { ok: false, timings: timings };

        // RunAi — make the AI play its turn on the cloned runner
        t = Date.now();
        var raErr = null;
        try { invokeMethod(runAiMi.info, rr, null); }
        catch (e) { raErr = e.message; }
        timings.push({ step: "RunAi", ms: Date.now() - t, err: raErr });

        // GetState
        t = Date.now();
        var simState = invokeMethod(getStateMi.info, rr, null);
        timings.push({ step: "GetState", ms: Date.now() - t, simState: simState.toString() });

        return { ok: rasErr === null, timings: timings };
    } catch (e) {
        timings.push({ step: "UNCAUGHT", err: e.message, stack: e.stack });
        return { ok: false, timings: timings };
    }
}

// Full manual flow: create inner IdunRunner, Initialize it, wrap in ReplayRunner via 3-arg ctor.
function doManualInitSim() {
    var timings = [];
    timings.push({ step: "enter", t: Date.now() });
    try {
        if (!runnerInstance) throw new Error("runner not captured");
        if (!gcRoot.init()) throw new Error("gcRoot init failed");
        if (!initializePrngMi) throw new Error("Initialize(PRNG,...) overload not resolved");
        if (!replayRunnerCtor3_runner) throw new Error("ReplayRunner 3-arg ctor not resolved");
        timings.push({ step: "preconditions OK" });
    } catch (e) { timings.push({ step: "preconditions FAIL", err: e.message }); return { ok: false, timings: timings }; }
    var T0 = Date.now();

    // 1. GetReplay — wrapped in try/catch to capture exact failure step
    try {
        var t = Date.now();
        var recorder = runnerInstance.add(runnerReplayRecorderOff).readPointer();
        timings.push({ step: "read recorder", ptr: recorder.toString() });
        var replay = invokeMethod(getReplayMi.info, recorder, null);
        timings.push({ step: "GetReplay done", ms: Date.now() - t, replay: replay.toString() });
        gcRoot.add(replay);
    } catch (e) { timings.push({ step: "GetReplay FAIL", err: e.message }); return { ok: false, timings: timings }; }

    // 2. Grab deps from the real runner
    var realConfig, realPrng, realTimeSource, realLogger, realReporter;
    try {
        realConfig = runnerInstance.add(runnerConfigOff).readPointer();
        realPrng = runnerInstance.add(runnerRngOff).readPointer();
        realTimeSource = runnerInstance.add(runnerTimeSourceOff).readPointer();
        realLogger = runnerInstance.add(runnerLoggerOff).readPointer();
        // Steal reporter from real runner's OperationProcessor._startMatch._battleDataReporter
        var opProc = runnerInstance.add(192).readPointer();
        var startMatchOp = opProc.add(528).readPointer();
        realReporter = startMatchOp.add(48).readPointer();
        timings.push({ step: "deps", config: realConfig.toString(), prng: realPrng.toString(), timeSource: realTimeSource.toString(), logger: realLogger.toString(), reporter: realReporter.toString(), reporterKlass: s(class_get_name(realReporter.readPointer())) });
        if (realConfig.isNull() || realPrng.isNull() || realTimeSource.isNull() || realLogger.isNull()) {
            return { ok: false, reason: "a dep is null", timings: timings };
        }
    } catch (e) { timings.push({ step: "deps FAIL", err: e.message }); return { ok: false, timings: timings }; }

    // 3. Build default IdunRunnerOptions + set RecordReplay=true
    var options, innerRunner;
    try {
        t = Date.now();
        options = il2cpp_object_new(idunRunnerOptionsClass);
        gcRoot.add(options);
        invokeMethod(idunRunnerOptionsCtor.info, options, null);
        // RecordReplay=true (offset 16), ReplayBugFinderModes=0 (offset 17), AddInputInterceptor=false (18)
        options.add(16).writeU8(1);
        timings.push({ step: "new IdunRunnerOptions + RecordReplay=true", ms: Date.now() - t, ptr: options.toString() });
    } catch (e) { timings.push({ step: "IdunRunnerOptions FAIL", err: e.message }); return { ok: false, timings: timings }; }

    // 4. Create empty inner IdunRunner — ctor takes (battleConfig, recordQuerySimRequests: bool)
    try {
        t = Date.now();
        innerRunner = il2cpp_object_new(runnerClass);
        gcRoot.add(innerRunner);
        var boolFalseArg = Memory.alloc(1); boolFalseArg.writeU8(0);
        invokeMethod(idunRunnerCtor.info, innerRunner, [realConfig, boolFalseArg]);
        timings.push({ step: "new IdunRunner + ctor(config, false)", ms: Date.now() - t, ptr: innerRunner.toString() });
    } catch (e) { timings.push({ step: "IdunRunner ctor FAIL", err: e.message }); return { ok: false, timings: timings }; }

    // 5. Initialize inner runner — use PRNG overload so we share RNG with real runner
    //    IdunRunner.Initialize(config, prng, timeSource, options, logger, reporter)
    t = Date.now();
    var initErr = null;
    try {
        invokeMethod(initializePrngMi.info, innerRunner,
            [realConfig, realPrng, realTimeSource, options, realLogger, realReporter]);
    } catch (e) { initErr = e.message; }
    var isInitialized = 0;
    try { isInitialized = innerRunner.add(runnerIsInitOff).readU8(); } catch (e) {}
    timings.push({ step: "Initialize (PRNG, reporter=stolen)", ms: Date.now() - t, err: initErr, isInitialized: isInitialized });
    if (initErr || isInitialized !== 1) {
        return { ok: false, reason: "Initialize failed", timings: timings };
    }

    // 6. Wrap in ReplayRunner via 3-arg ctor
    t = Date.now();
    var rr = il2cpp_object_new(replayRunnerClass);
    gcRoot.add(rr);
    invokeMethod(replayRunnerCtor3_runner.info, rr, [realLogger, innerRunner, replay, realTimeSource]);
    timings.push({ step: "new ReplayRunner(3-arg)", ms: Date.now() - t, rr: rr.toString() });

    // Manually populate _simulationRequestRunner (3-arg ctor leaves it null)
    try {
        t = Date.now();
        var simReqRunnerClass = findClass("BattleLogicAssembly.dll", "Idun.Source.IdunBattle.Logic.Replay", "SimulationRequestRunner");
        var simReqRunnerCtor = findMethod(simReqRunnerClass, ".ctor");
        var innerBattleQueryOff = getFieldOffset(runnerClass, "<BattleQuery>k__BackingField");
        var innerStateOff = getFieldOffset(runnerClass, "_state");
        var innerQuery = innerRunner.add(innerBattleQueryOff).readPointer();
        var innerState = innerRunner.add(innerStateOff).readPointer();
        var simReqRunner = il2cpp_object_new(simReqRunnerClass);
        gcRoot.add(simReqRunner);
        invokeMethod(simReqRunnerCtor.info, simReqRunner, [innerQuery, innerState]);
        rr.add(getFieldOffset(replayRunnerClass, "_simulationRequestRunner")).writePointer(simReqRunner);
        timings.push({ step: "populate _simulationRequestRunner", ms: Date.now() - t, ptr: simReqRunner.toString(), innerQuery: innerQuery.toString(), innerState: innerState.toString() });
    } catch (e) { timings.push({ step: "SimReqRunner FAIL", err: e.message }); return { ok: false, timings: timings }; }

    // 7. InitializeBattle
    send({ t: "sim_step", step: "before InitializeBattle" });
    t = Date.now();
    var ibErr = null;
    try { invokeMethod(initBattleMi.info, rr, null); }
    catch (e) { ibErr = e.message; }
    timings.push({ step: "InitializeBattle", ms: Date.now() - t, err: ibErr });
    if (ibErr) {
        gcRoot.remove(rr); gcRoot.remove(innerRunner); gcRoot.remove(options); gcRoot.remove(replay);
        return { ok: false, reason: "InitializeBattle failed", timings: timings };
    }

    // 8. RunAllSteps(false, false) — fast-forward
    t = Date.now();
    var boolFalse = Memory.alloc(1); boolFalse.writeU8(0);
    var rasErr = null;
    try { invokeMethod(runAllStepsMi.info, rr, [boolFalse, boolFalse]); }
    catch (e) { rasErr = e.message; }
    timings.push({ step: "RunAllSteps(false,false)", ms: Date.now() - t, err: rasErr });

    // 9. GetState
    t = Date.now();
    var simState = invokeMethod(getStateMi.info, rr, null);
    timings.push({ step: "GetState", ms: Date.now() - t, simState: simState.toString() });

    timings.push({ grand_total_ms: Date.now() - T0 });
    return { ok: true, timings: timings };
}

rpc.exports = {
    info: function () {
        return {
            runnerCaptured: !!runnerInstance,
            gameViewsCaptured: !!gameViewsInstance,
            replayRecorderOff: runnerReplayRecorderOff,
            replayClassFound: !!replayClass,
            replayRecorderClassFound: !!replayRecorderClass,
            getReplayResolved: !!(getReplayMi && !getReplayMi.ptr.isNull()),
            offsets: {
                RngSeed: replayRngSeedOff,
                Messages: replayMessagesOff,
                BattleConfiguration: replayBattleConfigOff,
                RecordedPlayerIds: replayRecordedPlayerIdsOff,
                StartingTimestamp: replayStartingTsOff
            }
        };
    },
    probeReplay: function () { return queueOnMainThread(doProbeReplay); },
    createReplayRunner: function () { return queueOnMainThread(doCreateReplayRunner); },
    fullSim: function () { return queueOnMainThread(doFullSim); },
    manualInitSim: function () { return queueOnMainThread(doManualInitSim); },
    hybridSim: function () { return queueOnMainThread(doHybridSim); },
    simAndCommit: function () { return queueOnMainThread(doSimAndCommit); },
    dumpReplayMessages: function () {
        return queueOnMainThread(function () {
            var recorder = runnerInstance.add(runnerReplayRecorderOff).readPointer();
            var replay = invokeMethod(getReplayMi.info, recorder, null);
            var msgsList = replay.add(replayMessagesOff).readPointer();
            var items = msgsList.add(0x10).readPointer();
            var size = msgsList.add(0x18).readS32();
            var out = [];
            for (var i = 0; i < size; i++) {
                var step = items.add(0x20 + i * 8).readPointer();
                if (step.isNull()) continue;
                var turn = step.add(20).readS32();
                var inputMsg = step.add(32).readPointer();
                out.push({ i: i, turn: turn, msg: inputMsg.isNull() ? "null" : readMsgClass(inputMsg) });
            }
            return { count: size, messages: out };
        });
    },
    cheatOnReal: function () {
        return queueOnMainThread(function () {
            if (!runnerInstance) throw new Error("no runner");
            var msg = createObject(cheatRunAiClass);
            invokeMethod(runnerApplyMi.info, runnerInstance, [msg]);
            return { ok: true, msg: msg.toString() };
        });
    },
    misFound: function () {
        return {
            isPlayersTurnMi: !!(isPlayersTurnMi && !isPlayersTurnMi.ptr.isNull()),
            applyAiMsgMi: !!(applyAiMsgMi && !applyAiMsgMi.ptr.isNull()),
            getRemainingStepsMi: !!(getRemainingStepsMi && !getRemainingStepsMi.ptr.isNull()),
            runAiMi: !!(runAiMi && !runAiMi.ptr.isNull()),
            runAllStepsMi: !!(runAllStepsMi && !runAllStepsMi.ptr.isNull())
        };
    },
    forceRecaptureRunner: function () {
        return queueOnMainThread(function () {
            if (!gameViewsInstance) return { err: "gameViews not captured" };
            var r = gameViewsInstance.add(_gvRunnerOff).readPointer();
            var old = runnerInstance ? runnerInstance.toString() : "null";
            runnerInstance = r.isNull() ? null : r;
            return { old: old, new: r.toString(), isNull: r.isNull() };
        });
    },
    ctorsFound: function () {
        return {
            initializePrngMi: !!(initializePrngMi && !initializePrngMi.ptr.isNull()),
            initializeSeedMi: !!(initializeSeedMi && !initializeSeedMi.ptr.isNull()),
            replayRunnerCtor3_runner: !!(replayRunnerCtor3_runner && !replayRunnerCtor3_runner.ptr.isNull()),
            idunRunnerCtor: !!(idunRunnerCtor && !idunRunnerCtor.ptr.isNull()),
            idunRunnerOptionsClass: !!idunRunnerOptionsClass,
            idunRunnerOptionsCtor: !!(idunRunnerOptionsCtor && !idunRunnerOptionsCtor.ptr.isNull()),
            offsets: {
                runnerRng: runnerRngOff, runnerConfig: runnerConfigOff, runnerIsInit: runnerIsInitOff
            }
        };
    }
};
