// hook: AI Services observer — capture calls to AttackQuery, DamagePrediction, TargetingQuery
// requires: _utils/il2cpp-helpers, _utils/matchstate-reader
//
// Phase 2: entity IDs + stack in onEnter. Bool/int retvals in onLeave.
// No serialization of complex return values.

function _safeEntityId(ptr) {
    try {
        if (ptr.isNull()) return null;
        return ptr.add(_entityIdOff).readS32();
    } catch(e) { return null; }
}

var _attackQueryClass = findClass("BattleLogicAssembly.dll", "IdunBattle.Core.Services", "AttackQuery");
var _dmgPredClass = findClass("BattleLogicAssembly.dll", "IdunBattle.Core.Services", "DamagePredictionQuery");
var _targetingClass = findClass("BattleLogicAssembly.dll", "IdunBattle.Core.Services", "TargetingQuery");

// =====================================================================
// AttackQuery.GetValidTargets
// =====================================================================
if (_attackQueryClass) {
    var _aqGetValid = findMethod(_attackQueryClass, "GetValidTargets");
    if (_aqGetValid) {
        try {
            Interceptor.attach(_aqGetValid.ptr, {
                onEnter: function(args) {
                    try {
                        this._unitId = _safeEntityId(args[1]);
                        this._stack = getStack(this.context);
                    } catch(e) {}
                },
                onLeave: function(retval) {
                    try {
                        send({t: "ai_service", call: "AttackQuery.GetValidTargets",
                              unitId: this._unitId, stack: this._stack});
                    } catch(e) {}
                }
            });
            console.log("[+] AttackQuery.GetValidTargets");
        } catch(e) { console.log("[!] AttackQuery.GetValidTargets: " + e.message); }
    }

    // AttackQuery.HasValidTargets
    var _aqHasValid = findMethod(_attackQueryClass, "HasValidTargets");
    if (_aqHasValid) {
        try {
            Interceptor.attach(_aqHasValid.ptr, {
                onEnter: function(args) {
                    try {
                        this._unitId = _safeEntityId(args[1]);
                        this._stack = getStack(this.context);
                    } catch(e) {}
                },
                onLeave: function(retval) {
                    try {
                        send({t: "ai_service", call: "AttackQuery.HasValidTargets",
                              unitId: this._unitId, result: retval.toInt32() !== 0,
                              stack: this._stack});
                    } catch(e) {}
                }
            });
            console.log("[+] AttackQuery.HasValidTargets");
        } catch(e) { console.log("[!] AttackQuery.HasValidTargets: " + e.message); }
    }
}

// =====================================================================
// DamagePredictionQuery.GetAllPredictions
// =====================================================================
if (_dmgPredClass) {
    var _dpGetAll = findMethod(_dmgPredClass, "GetAllPredictions");
    if (_dpGetAll) {
        try {
            Interceptor.attach(_dpGetAll.ptr, {
                onEnter: function(args) {
                    try {
                        this._attackerId = _safeEntityId(args[1]);
                        this._stack = getStack(this.context);
                    } catch(e) {}
                },
                onLeave: function(retval) {
                    try {
                        send({t: "ai_service", call: "DamagePredictionQuery.GetAllPredictions",
                              attackerId: this._attackerId, stack: this._stack});
                    } catch(e) {}
                }
            });
            console.log("[+] DamagePredictionQuery.GetAllPredictions");
        } catch(e) { console.log("[!] DamagePredictionQuery.GetAllPredictions: " + e.message); }
    }
}

// =====================================================================
// TargetingQuery.GetRangeValue
// =====================================================================
if (_targetingClass) {
    var _tqGetRange = findMethod(_targetingClass, "GetRangeValue");
    if (_tqGetRange) {
        try {
            Interceptor.attach(_tqGetRange.ptr, {
                onEnter: function(args) {
                    try {
                        this._casterId = _safeEntityId(args[1]);
                        this._stack = getStack(this.context);
                    } catch(e) {}
                },
                onLeave: function(retval) {
                    try {
                        send({t: "ai_service", call: "TargetingQuery.GetRangeValue",
                              casterId: this._casterId, result: retval.toInt32(),
                              stack: this._stack});
                    } catch(e) {}
                }
            });
            console.log("[+] TargetingQuery.GetRangeValue");
        } catch(e) { console.log("[!] TargetingQuery.GetRangeValue: " + e.message); }
    }
}

console.log("[*] AI services observer loaded");
