// Phase: simulate a player turn on a cloned MatchState.
//
// Flow:
//   1. Clone runner._state via MatchState.Copy() and gc-root the clone.
//   2. Set InSimulationMode=true on the clone.
//   3. Swap runner._state pointer → clone.
//   4. Attach Interceptor on IdunRunner.Apply to capture sub-messages.
//   5. Invoke Apply(CheatRunAIMessage) — AI now plays on the clone.
//   6. Detach, restore runner._state, remove clone from gc-root.
//   7. Return captured messages.
//
// All native work happens on the Unity main thread via the IdunGameViews.Update queue.

send({ t: "hook_ready", name: "simulate-turn", version: 1 });

// --- classes / methods / offsets ---

var _gameViewsClass = findClass("Assembly-CSharp.dll", "IdunBattle.View.Game", "IdunGameViews");
var _gvRunnerOff = _gameViewsClass ? getFieldOffset(_gameViewsClass, "_runner") : -1;

var runnerClass = findClass("BattleLogicAssembly.dll", "IdunBattle.Runner", "IdunRunner");
var applyMi = runnerClass ? findMethod(runnerClass, "Apply") : null;
var runnerStateOff = runnerClass ? getFieldOffset(runnerClass, "_state") : -1;

var matchStateClass = findClass("BattleLogicAssembly.dll", "IdunBattle.Core", "MatchState");
var copyMi = matchStateClass ? findMethod(matchStateClass, "Copy") : null;
var setInSimMi = matchStateClass ? findMethod(matchStateClass, "set_InSimulationMode") : null;
var getInSimMi = matchStateClass ? findMethod(matchStateClass, "get_InSimulationMode") : null;

var cheatRunAiClass = findClass("BattleLogicAssembly.dll", "IdunBattle.Messages", "CheatRunAIMessage");

var aiControlClass = findClass("BattleLogicAssembly.dll", "IdunBattle.Core.Services", "AiControl");
var applyAiMi = aiControlClass ? findMethod(aiControlClass, "ApplyAiMessage") : null;
var applyHumanAiMi = aiControlClass ? findMethod(aiControlClass, "ApplyHumanAiMessage") : null;

// entity layout for post-mutation probe
var entityClass = findClass("BattleLogicAssembly.dll", "IdunBattle.Core", "Entity");
var entityIdOff = entityClass ? getFieldOffset(entityClass, "<Id>k__BackingField") : -1;
var msEntitiesOff = matchStateClass ? getFieldOffset(matchStateClass, "_entities") : -1;

// --- state ---

var runnerInstance = null;
var gameViewsInstance = null;
var pending = [];

// --- main-thread queue (via Update hook) ---

if (_gameViewsClass && _gvRunnerOff >= 0) {
    var updateMi = findMethod(_gameViewsClass, "Update");
    if (updateMi) {
        var _origUpdate = new NativeFunction(updateMi.ptr, "void", ["pointer", "pointer"]);
        Interceptor.replace(updateMi.ptr, new NativeCallback(function (self, methodInfo) {
            if (!gameViewsInstance) gameViewsInstance = self;
            if (!runnerInstance) {
                var r = self.add(_gvRunnerOff).readPointer();
                if (!r.isNull()) runnerInstance = r;
            }
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

// --- snapshot helpers (to verify real state is unchanged) ---

function _readListPtrs(listPtr) {
    if (listPtr.isNull()) return [];
    var items = listPtr.add(0x10).readPointer();
    var size = listPtr.add(0x18).readS32();
    if (items.isNull() || size <= 0 || size > 5000) return [];
    var out = [];
    for (var i = 0; i < size; i++) out.push(items.add(0x20 + i * Process.pointerSize).readPointer());
    return out;
}

function snapshotEntityPtrs(state) {
    var arr = state.add(msEntitiesOff).readPointer();
    var ents = _readListPtrs(arr);
    return { count: ents.length, firstId: ents.length ? ents[0].add(entityIdOff).readS32() : -1 };
}

// --- core ---

function doSimulate() {
    if (!runnerInstance) throw new Error("runner not captured yet");
    if (!copyMi || copyMi.ptr.isNull()) throw new Error("MatchState.Copy not resolved");
    if (!setInSimMi || setInSimMi.ptr.isNull()) throw new Error("set_InSimulationMode not resolved");
    if (!applyMi || applyMi.ptr.isNull()) throw new Error("IdunRunner.Apply not resolved");
    if (!cheatRunAiClass) throw new Error("CheatRunAIMessage class not found");
    if (!gcRoot.init()) throw new Error("gcRoot init failed");

    var log = [];
    var origState = runnerInstance.add(runnerStateOff).readPointer();
    if (origState.isNull()) throw new Error("runner._state is null");
    log.push("origState=" + origState);

    var preSnapshot = snapshotEntityPtrs(origState);
    log.push("preSnapshot=" + JSON.stringify(preSnapshot));

    // 1. Clone
    var cloneState = invokeMethod(copyMi.info, origState, null);
    if (cloneState.isNull()) throw new Error("MatchState.Copy returned null");
    gcRoot.add(cloneState);
    log.push("cloneState=" + cloneState + " (rooted)");

    // 2. Set InSimulationMode=true on clone
    var boolTrue = Memory.alloc(1); boolTrue.writeU8(1);
    invokeMethod(setInSimMi.info, cloneState, [boolTrue]);
    var boxed = invokeMethod(getInSimMi.info, cloneState, null);
    log.push("clone.InSimulationMode=" + (boxed.isNull() ? "?" : boxed.add(0x10).readU8()));

    // 3. Swap runner._state → clone
    runnerInstance.add(runnerStateOff).writePointer(cloneState);
    log.push("swapped runner._state → clone");

    // 4. Attach AI message capture hooks
    var captured = [];
    var listeners = attachCaptureHooks(captured);

    // 5. Invoke Apply(CheatRunAIMessage)
    var simError = null;
    try {
        var msg = createObject(cheatRunAiClass);
        invokeMethod(applyMi.info, runnerInstance, [msg]);
    } catch (e) {
        simError = e.message;
    }

    // 6. Detach + restore
    detachAll(listeners);
    runnerInstance.add(runnerStateOff).writePointer(origState);
    gcRoot.remove(cloneState);
    log.push("restored runner._state=" + runnerInstance.add(runnerStateOff).readPointer());

    var postSnapshot = snapshotEntityPtrs(origState);
    log.push("postSnapshot=" + JSON.stringify(postSnapshot));

    return {
        ok: simError === null,
        simError: simError,
        capturedCount: captured.length,
        captured: captured,
        preSnapshot: preSnapshot,
        postSnapshot: postSnapshot,
        log: log
    };
}

function doTestClone() {
    if (!runnerInstance) throw new Error("runner not captured yet");
    if (!gcRoot.init()) throw new Error("gcRoot init failed");
    var log = [];
    var origState = runnerInstance.add(runnerStateOff).readPointer();
    log.push("runnerState=" + origState);
    if (origState.isNull()) throw new Error("runner._state is null");
    var cloneState = invokeMethod(copyMi.info, origState, null);
    log.push("cloneState=" + cloneState);
    if (cloneState.isNull()) throw new Error("Copy returned null");
    var cloneKlass = cloneState.readPointer();
    log.push("cloneKlass=" + cloneKlass + " name=" + s(class_get_name(cloneKlass)));
    gcRoot.add(cloneState);
    log.push("rooted, count=" + gcRoot.count());
    return { ok: true, origState: origState.toString(), cloneState: cloneState.toString(), log: log };
}

function doTestSetSimMode(cloneHexPtr) {
    var clone = ptr(cloneHexPtr);
    var log = [];
    var boolTrue = Memory.alloc(1); boolTrue.writeU8(1);
    invokeMethod(setInSimMi.info, clone, [boolTrue]);
    log.push("set_InSimulationMode(true) called");
    var boxed = invokeMethod(getInSimMi.info, clone, null);
    log.push("get boxed=" + boxed);
    if (!boxed.isNull()) log.push("value=" + boxed.add(0x10).readU8());
    return { ok: true, log: log };
}

function attachCaptureHooks(captured) {
    var listeners = [];
    function attachOn(mi, tag) {
        if (!mi || mi.ptr.isNull()) return;
        listeners.push(Interceptor.attach(mi.ptr, {
            onEnter: function (args) {
                try {
                    captured.push({ src: tag, cls: readMsgClass(args[1]), ptr: args[1].toString() });
                } catch (e) { captured.push({ src: tag, err: e.message }); }
            }
        }));
    }
    attachOn(applyAiMi, "ApplyAiMessage");
    attachOn(applyHumanAiMi, "ApplyHumanAiMessage");
    Interceptor.flush();
    return listeners;
}

function detachAll(listeners) {
    for (var i = 0; i < listeners.length; i++) listeners[i].detach();
}

function doProbeCloneDeep() {
    if (!gcRoot.init()) throw new Error("gcRoot init failed");
    var log = [];
    var orig = runnerInstance.add(runnerStateOff).readPointer();
    var clone = invokeMethod(copyMi.info, orig, null);
    gcRoot.add(clone);

    var origList = orig.add(msEntitiesOff).readPointer();
    var cloneList = clone.add(msEntitiesOff).readPointer();
    var origItems = origList.add(0x10).readPointer();
    var cloneItems = cloneList.add(0x10).readPointer();
    var origSize = origList.add(0x18).readS32();
    var cloneSize = cloneList.add(0x18).readS32();
    log.push("origSize=" + origSize + " cloneSize=" + cloneSize);

    // Sample first 10 entity ptrs — compare orig vs clone
    var aliasedCount = 0, distinctCount = 0, nullInClone = 0, nullInOrig = 0;
    var sample = [];
    for (var i = 0; i < Math.min(origSize, cloneSize, 150); i++) {
        var op = origItems.add(0x20 + i * 8).readPointer();
        var cp = cloneItems.add(0x20 + i * 8).readPointer();
        if (op.isNull()) nullInOrig++;
        if (cp.isNull()) nullInClone++;
        if (!op.isNull() && !cp.isNull()) {
            if (op.equals(cp)) aliasedCount++; else distinctCount++;
        }
        if (i < 10) sample.push({ i: i, orig: op.toString(), clone: cp.toString(), aliased: !op.isNull() && !cp.isNull() && op.equals(cp) });
    }
    log.push("aliased=" + aliasedCount + " distinct=" + distinctCount + " nullOrig=" + nullInOrig + " nullClone=" + nullInClone);

    gcRoot.remove(clone);
    return { ok: true, log: log, sample: sample };
}

function doProbeClone() {
    if (!gcRoot.init()) throw new Error("gcRoot init failed");
    var log = [];
    var orig = runnerInstance.add(runnerStateOff).readPointer();
    log.push("msEntitiesOff=" + msEntitiesOff);

    var origEntListPtr = orig.add(msEntitiesOff).readPointer();
    log.push("orig._entities list ptr=" + origEntListPtr + " isNull=" + origEntListPtr.isNull());
    if (!origEntListPtr.isNull()) {
        log.push("orig list items=" + origEntListPtr.add(0x10).readPointer() + " size=" + origEntListPtr.add(0x18).readS32());
    }

    var clone = invokeMethod(copyMi.info, orig, null);
    gcRoot.add(clone);
    log.push("clone=" + clone + " klass=" + s(class_get_name(clone.readPointer())));

    // Same offset, different object
    var cloneEntListPtr = clone.add(msEntitiesOff).readPointer();
    log.push("clone._entities list ptr=" + cloneEntListPtr + " isNull=" + cloneEntListPtr.isNull());
    if (!cloneEntListPtr.isNull()) {
        var cloneItems = cloneEntListPtr.add(0x10).readPointer();
        var cloneSize = cloneEntListPtr.add(0x18).readS32();
        log.push("clone list items=" + cloneItems + " size=" + cloneSize);
    }

    gcRoot.remove(clone);
    return { ok: true, log: log };
}

function doCompareStates() {
    if (!gcRoot.init()) throw new Error("gcRoot init failed");
    var log = [];
    var orig = runnerInstance.add(runnerStateOff).readPointer();

    var origEnts = _readListPtrs(orig.add(msEntitiesOff).readPointer());
    log.push("orig entities count=" + origEnts.length + " firstPtr=" + (origEnts[0] || "n/a") + " firstId=" + (origEnts[0] ? origEnts[0].add(entityIdOff).readS32() : -1));

    var clone = invokeMethod(copyMi.info, orig, null);
    gcRoot.add(clone);

    var cloneEnts = _readListPtrs(clone.add(msEntitiesOff).readPointer());
    log.push("clone entities count=" + cloneEnts.length + " firstPtr=" + (cloneEnts[0] || "n/a") + " firstId=" + (cloneEnts[0] ? cloneEnts[0].add(entityIdOff).readS32() : -1));

    // Compare: same count? same ids? distinct pointers (deep copy)?
    var sameCount = origEnts.length === cloneEnts.length;
    var sameIds = true;
    var distinctPtrs = true;
    for (var i = 0; i < Math.min(origEnts.length, cloneEnts.length); i++) {
        if (origEnts[i].add(entityIdOff).readS32() !== cloneEnts[i].add(entityIdOff).readS32()) sameIds = false;
        if (origEnts[i].equals(cloneEnts[i])) distinctPtrs = false;
    }

    log.push("sameCount=" + sameCount + " sameIds=" + sameIds + " distinctPtrs=" + distinctPtrs);

    // Sample first 5 entity ptrs to see which are aliased vs cloned
    var sample = [];
    for (var i = 0; i < Math.min(5, origEnts.length); i++) {
        sample.push({
            i: i,
            id: origEnts[i].add(entityIdOff).readS32(),
            type: origEnts[i].add(entityTypeOff).readS32(),
            origPtr: origEnts[i].toString(),
            clonePtr: cloneEnts[i].toString(),
            aliased: origEnts[i].equals(cloneEnts[i])
        });
    }

    gcRoot.remove(clone);
    return { ok: true, log: log, sameCount: sameCount, sameIds: sameIds, distinctPtrs: distinctPtrs, sample: sample };
}

function doCaptureAiMessages() {
    // No swap — run cheat on real state + capture messages the AI emits via AiControl.
    var log = [];
    var captured = [];
    var listeners = attachCaptureHooks(captured);
    log.push("listeners attached: ApplyAiMessage=" + !!(applyAiMi) + " ApplyHumanAiMessage=" + !!(applyHumanAiMi));
    var err = null;
    try {
        var msg = createObject(cheatRunAiClass);
        invokeMethod(applyMi.info, runnerInstance, [msg]);
    } catch (e) { err = e.message; }
    detachAll(listeners);
    return { ok: err === null, err: err, capturedCount: captured.length, captured: captured, log: log };
}

function doTestSwapCheat() {
    if (!gcRoot.init()) throw new Error("gcRoot init failed");
    var log = [];
    var origState = runnerInstance.add(runnerStateOff).readPointer();
    log.push("orig=" + origState);

    var cloneState = invokeMethod(copyMi.info, origState, null);
    if (cloneState.isNull()) throw new Error("Copy returned null");
    gcRoot.add(cloneState);
    log.push("clone=" + cloneState);

    var boolTrue = Memory.alloc(1); boolTrue.writeU8(1);
    invokeMethod(setInSimMi.info, cloneState, [boolTrue]);
    log.push("set InSim on clone");

    runnerInstance.add(runnerStateOff).writePointer(cloneState);
    log.push("swapped");

    var err = null;
    try {
        var msg = createObject(cheatRunAiClass);
        invokeMethod(applyMi.info, runnerInstance, [msg]);
        log.push("cheat applied on clone");
    } catch (e) { err = e.message; log.push("cheat threw: " + err); }

    runnerInstance.add(runnerStateOff).writePointer(origState);
    log.push("restored");
    gcRoot.remove(cloneState);
    return { ok: err === null, err: err, log: log };
}

function doTestSwap(cloneHexPtr) {
    var clone = ptr(cloneHexPtr);
    var log = [];
    var orig = runnerInstance.add(runnerStateOff).readPointer();
    log.push("orig=" + orig);
    runnerInstance.add(runnerStateOff).writePointer(clone);
    log.push("swapped → " + runnerInstance.add(runnerStateOff).readPointer());
    // immediately restore
    runnerInstance.add(runnerStateOff).writePointer(orig);
    log.push("restored → " + runnerInstance.add(runnerStateOff).readPointer());
    return { ok: true, log: log };
}

rpc.exports = {
    info: function () {
        return {
            runnerCaptured: !!runnerInstance,
            gameViewsCaptured: !!gameViewsInstance,
            applyResolved: !!(applyMi && !applyMi.ptr.isNull()),
            copyResolved: !!(copyMi && !copyMi.ptr.isNull()),
            setInSimResolved: !!(setInSimMi && !setInSimMi.ptr.isNull()),
            cheatClassFound: !!cheatRunAiClass
        };
    },
    testClone: function () { return queueOnMainThread(doTestClone); },
    testSetSimMode: function (cloneHexPtr) { return queueOnMainThread(function () { return doTestSetSimMode(cloneHexPtr); }); },
    testSwap: function (cloneHexPtr) { return queueOnMainThread(function () { return doTestSwap(cloneHexPtr); }); },
    testAttachOnly: function () { return queueOnMainThread(doTestAttachOnly); },
    testSwapCheat: function () { return queueOnMainThread(doTestSwapCheat); },
    captureAiMessages: function () { return queueOnMainThread(doCaptureAiMessages); },
    compareStates: function () { return queueOnMainThread(doCompareStates); },
    probeClone: function () { return queueOnMainThread(doProbeClone); },
    probeCloneDeep: function () { return queueOnMainThread(doProbeCloneDeep); },
    simulate: function () { return queueOnMainThread(doSimulate); }
};
