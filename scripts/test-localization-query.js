// Test: call LocalizationQuery methods from the main thread (via Update)
// Append after autoplay hooks (needs runnerInstance, il2cpp helpers, pendingRpc)

var _lqClass = findClass("BattleLogicAssembly.dll", "IdunBattle.Core.Services", "LocalizationQuery");
var _runnerLqOff = _lqClass ? getFieldOffset(runnerClass, "<LocalizationQuery>k__BackingField") : -1;
var _getEffectLocData = _lqClass ? findMethod(_lqClass, "GetEffectLocalizationData") : null;
var _getActiveLocData = _lqClass ? findMethod(_lqClass, "GetActiveAbilityLocalizationData") : null;

send({t: "lq_setup", classFound: !!_lqClass, offset: _runnerLqOff,
      getEffect: !!_getEffectLocData, getActive: !!_getActiveLocData});

function queryLocalization(unitId, typeId, methodInfo) {
    if (!runnerInstance || _runnerLqOff < 0 || !methodInfo) return {error: "not ready"};
    var lq = runnerInstance.add(_runnerLqOff).readPointer();
    if (lq.isNull()) return {error: "LQ instance null"};

    var unitArg = Memory.alloc(4);
    unitArg.writeS32(unitId);
    var typeArg = Memory.alloc(4);
    typeArg.writeS32(typeId);

    var result = invokeMethod(methodInfo.info, lq, [unitArg, typeArg]);
    if (!result || result.isNull()) return null;
    return serialize(result, 3);
}

// Hook into the RPC handler: add "lq_test" method
// This runs inside the Update callback on the main thread
var _origRpcBlock = pendingRpc;

// Queue a test — will be picked up by action-queue's RPC handler
// But action-queue doesn't know "lq_test", so we intercept here
// Instead: override get_state to also run our test once

var _lqTestDone = false;
var _origGetState = getSerializedState;
getSerializedState = function(depth) {
    if (!_lqTestDone) {
        _lqTestDone = true;
        try {
            // Test effect localization
            var r1 = queryLocalization(79, 1008, _getEffectLocData);
            send({t: "lq_result", method: "GetEffectLocData", unitId: 79, typeId: 1008, result: r1});

            var r2 = queryLocalization(87, 1226, _getEffectLocData);
            send({t: "lq_result", method: "GetEffectLocData", unitId: 87, typeId: 1226, result: r2});

            // Test active ability localization
            var r3 = queryLocalization(79, 1063, _getActiveLocData);
            send({t: "lq_result", method: "GetActiveLocData", unitId: 79, typeId: 1063, result: r3});

            // Test a working ability for comparison
            var r4 = queryLocalization(90, 1122, _getActiveLocData);
            send({t: "lq_result", method: "GetActiveLocData", unitId: 90, typeId: 1122, result: r4});
        } catch(e) {
            send({t: "lq_error", msg: e.message});
        }
    }
    return _origGetState(depth);
};

console.log("[*] LQ test: will run on next get_state RPC call");
