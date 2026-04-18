// Phase 1: make our human team play via the game's own AI.
// Chain: runner → _aiControl(+104) → _humanAiStrategy(+40) → DefaultPlayerStrategy
// Call CalculateNextActionForPlayer(humanPlayerEntity) → IEnumerator<List<IInputMessage>>
// Drain: MoveNext → get_Current → Apply each message via runner.Apply(msg).
//
// Execution runs on the Unity main thread via IdunGameViews.Update hook queue.

send({ t: "hook_ready", name: "ai-plays-me", version: 1 });

// --- Resolve classes and methods ---

var _gameViewsClass = findClass("Assembly-CSharp.dll", "IdunBattle.View.Game", "IdunGameViews");
var _gvRunnerOff = _gameViewsClass ? getFieldOffset(_gameViewsClass, "_runner") : -1;

var runnerClass = findClass("BattleLogicAssembly.dll", "IdunBattle.Runner", "IdunRunner");
var applyMi = runnerClass ? findMethod(runnerClass, "Apply") : null;

var aiControlClass = findClass("BattleLogicAssembly.dll", "IdunBattle.Core.Services", "AiControl");

var defaultPlayerStrategyClass = findClass("BattleLogicAssembly.dll", "IdunBattle.AI", "DefaultPlayerStrategy");
var calcNextMi = defaultPlayerStrategyClass ? findMethod(defaultPlayerStrategyClass, "CalculateNextActionForPlayer") : null;

var opProcClass = findClass("BattleLogicAssembly.dll", "Core.Services", "OperationProcessor");
var finishAllMi = opProcClass ? findMethod(opProcClass, "FinishAllCurrentPlayerUnitTurns") : null;

var endTurnClass = findClass("BattleLogicAssembly.dll", "IdunBattle.Messages", "EndTurnMessage");
var cheatRunAiClass = findClass("BattleLogicAssembly.dll", "IdunBattle.Messages", "CheatRunAIMessage");

var matchStateClass = findClass("BattleLogicAssembly.dll", "IdunBattle.Core", "MatchState");
var msEntitiesOff = matchStateClass ? getFieldOffset(matchStateClass, "_entities") : -1;
var msRunnerStateOff = runnerClass ? getFieldOffset(runnerClass, "_state") : -1;

var entityClass = findClass("BattleLogicAssembly.dll", "IdunBattle.Core", "Entity");
var entityIdOff = entityClass ? getFieldOffset(entityClass, "<Id>k__BackingField") : -1;
var entityTypeOff = entityClass ? getFieldOffset(entityClass, "<Type>k__BackingField") : -1;
var entityComponentsOff = entityClass ? getFieldOffset(entityClass, "Components") : -1;

var playerCompClass = findClass("BattleLogicAssembly.dll", "IdunBattle.Entities.Components", "PlayerComponent");
var playerTypeOff = playerCompClass ? getFieldOffset(playerCompClass, "Type") : -1;

// --- State ---

var runnerInstance = null;
var gameViewsInstance = null;
var pending = [];           // queue of actions to run on main thread
var lastResult = null;

// --- Helpers ---

function readListPtrs(listPtr) {
    if (listPtr.isNull()) return [];
    var items = listPtr.add(0x10).readPointer();
    var size = listPtr.add(0x18).readS32();
    if (items.isNull() || size <= 0 || size > 5000) return [];
    var out = [];
    for (var i = 0; i < size; i++) {
        out.push(items.add(0x20 + i * Process.pointerSize).readPointer());
    }
    return out;
}

function readComponent(entity, compName) {
    var compArr = entity.add(entityComponentsOff).readPointer();
    if (compArr.isNull()) return null;
    var len = compArr.add(0x18).readS32();
    for (var j = 0; j < Math.min(len, 50); j++) {
        var c = compArr.add(0x20 + j * Process.pointerSize).readPointer();
        if (c.isNull()) continue;
        try { if (s(class_get_name(c.readPointer())) === compName) return c; } catch (e) { }
    }
    return null;
}

function findHumanPlayerEntity(state) {
    var ents = readListPtrs(state.add(msEntitiesOff).readPointer());
    for (var i = 0; i < ents.length; i++) {
        var e = ents[i];
        if (e.isNull()) continue;
        if (e.add(entityTypeOff).readS32() !== 4) continue;  // Player
        var pc = readComponent(e, "PlayerComponent");
        if (pc && playerTypeOff >= 0 && pc.add(playerTypeOff).readS32() === 0) return e;  // 0 = human
    }
    return null;
}

// Find MoveNext + get_Current on an enumerator instance.
// Explicit interface impls have names like
// "System.Collections.Generic.IEnumerator<...>.get_Current" —
// we match by suffix so both short names and interface-qualified names work.
function findMethodBySuffix(klass, suffix) {
    var it = Memory.alloc(Process.pointerSize); it.writePointer(ptr(0));
    var m;
    while (!(m = class_get_methods(klass, it)).isNull()) {
        var name = s(method_get_name(m));
        if (name === suffix || (name.length >= suffix.length && name.slice(name.length - suffix.length) === suffix)) {
            return { info: m, ptr: m.readPointer(), name: name };
        }
    }
    return null;
}

function getEnumeratorMethods(enumPtr) {
    var klass = enumPtr.readPointer();
    return {
        klassName: s(class_get_name(klass)),
        moveNext: findMethodBySuffix(klass, "MoveNext"),
        getCurrent: findMethodBySuffix(klass, "get_Current"),
        dispose: findMethodBySuffix(klass, "Dispose")
    };
}

// --- Core action ---

function doPlayTurnWithAi(strategyField) {
    // strategyField: "default" (offset 32, enemy's strategy) or "human" (offset 40, default).
    var log = [];
    if (!runnerInstance) throw new Error("runner not captured yet");
    if (!calcNextMi || calcNextMi.ptr.isNull()) throw new Error("CalculateNextActionForPlayer not resolved");
    if (!applyMi || applyMi.ptr.isNull()) throw new Error("IdunRunner.Apply not resolved");

    var aiControl = runnerInstance.add(104).readPointer();
    if (aiControl.isNull()) throw new Error("_aiControl is null");
    var offset = (strategyField === "default") ? 32 : 40;
    var humanStrategy = aiControl.add(offset).readPointer();
    if (humanStrategy.isNull()) throw new Error("strategy at offset " + offset + " is null");
    log.push("usingStrategy=" + strategyField + " (offset " + offset + ") ptr=" + humanStrategy);

    var state = runnerInstance.add(msRunnerStateOff).readPointer();
    var humanEntity = findHumanPlayerEntity(state);
    if (!humanEntity || humanEntity.isNull()) throw new Error("human player entity not found");

    log.push("aiControl=" + aiControl + " humanStrategy=" + humanStrategy + " humanEntity=" + humanEntity);

    // enumerator = humanStrategy.CalculateNextActionForPlayer(humanEntity)
    var enumerator = invokeMethod(calcNextMi.info, humanStrategy, [humanEntity]);
    if (enumerator.isNull()) throw new Error("enumerator is null");

    var em = getEnumeratorMethods(enumerator);
    log.push("enumerator klass=" + em.klassName);
    if (!em.moveNext || !em.getCurrent) throw new Error("enumerator methods not found");

    var unitsPlayed = 0;
    var totalMessages = 0;
    var yieldLog = [];

    var moveNextFn = new NativeFunction(em.moveNext.ptr, "int", ["pointer", "pointer"]);

    // Capture initial state machine snapshot
    log.push("d6.player=" + enumerator.add(32).readPointer() + " d6.this4=" + enumerator.add(40).readPointer() + " d6.innerEnum=" + enumerator.add(48).readPointer());

    for (var safety = 0; safety < 10; safety++) {
        var stateBefore = enumerator.add(16).readS32();
        var innerBefore = enumerator.add(48).readPointer();
        var hasNext = moveNextFn(enumerator, em.moveNext.info);
        var stateAfter = enumerator.add(16).readS32();
        var current = enumerator.add(24).readPointer();
        var innerAfter = enumerator.add(48).readPointer();
        var innerState = innerAfter.isNull() ? "null" : innerAfter.add(16).readS32().toString();
        var innerCurrent = innerAfter.isNull() ? "null" : innerAfter.add(24).readPointer().toString();
        yieldLog.push("ret=" + hasNext + " state:" + stateBefore + "->" + stateAfter +
                      " current=" + current +
                      " inner=" + innerAfter + " innerState=" + innerState + " innerCur=" + innerCurrent);
        if (hasNext === 0) break;
        if (current.isNull()) continue;
        var msgs = readListPtrs(current);
        for (var i = 0; i < msgs.length; i++) {
            invokeMethod(applyMi.info, runnerInstance, [msgs[i]]);
            totalMessages++;
        }
        unitsPlayed++;
    }

    // Cleanup enumerator
    if (em.dispose && !em.dispose.ptr.isNull()) {
        try { invokeMethod(em.dispose.info, enumerator, null); } catch (e) { /* ignore */ }
    }

    return { unitsPlayed: unitsPlayed, totalMessages: totalMessages, log: log, yieldLog: yieldLog };
}

// --- Hook Update on main thread to run queued actions ---

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
                try {
                    var res = req.fn();
                    req.resolve(res);
                } catch (e) {
                    req.reject(e.message);
                }
            }
            _origUpdate(self, methodInfo);
        }, "void", ["pointer", "pointer"]));
    }
}

function queueOnMainThread(fn) {
    return new Promise(function (resolve, reject) {
        pending.push({
            fn: fn,
            resolve: resolve,
            reject: function (m) { reject(new Error(m)); }
        });
    });
}

function doFinishAllViaProcessor() {
    // NOTE: FinishAllCurrentPlayerUnitTurns is SKIP, not "let AI play".
    // Keep this around only for reference.
    if (!runnerInstance) throw new Error("runner not captured");
    var opProc = runnerInstance.add(192).readPointer();
    invokeMethod(finishAllMi.info, opProc, null);
    return { ok: true };
}

rpc.exports = {
    info: function () {
        return {
            runnerCaptured: !!runnerInstance,
            gameViewsCaptured: !!gameViewsInstance,
            applyResolved: !!(applyMi && !applyMi.ptr.isNull()),
            calcResolved: !!(calcNextMi && !calcNextMi.ptr.isNull()),
            finishAllResolved: !!(finishAllMi && !finishAllMi.ptr.isNull())
        };
    },
    playTurnWithAi: function (strategy) {
        var s = strategy || "human";
        return queueOnMainThread(function () { return doPlayTurnWithAi(s); });
    },
    finishAll: function () {
        return queueOnMainThread(doFinishAllViaProcessor);
    },
    runAiCheat: function () {
        return queueOnMainThread(function () {
            if (!runnerInstance) throw new Error("runner not captured");
            if (!cheatRunAiClass) throw new Error("CheatRunAIMessage class not found");
            var msg = createObject(cheatRunAiClass);
            invokeMethod(applyMi.info, runnerInstance, [msg]);
            return { ok: true, msg: msg.toString() };
        });
    }
};
