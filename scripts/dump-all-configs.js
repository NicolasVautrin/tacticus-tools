// oneshot: Dump ALL ability configs with raw field reading (Variables + Constants)
// requires: _utils/il2cpp-helpers, _utils/il2cpp-invoke, _utils/matchstate-reader
//
// Uses discovered AbilityConfiguration offsets:
//   Variables (Dict<AbilityVariableType, int[]>) at 0x10
//   Constants (Dict<AbilityConstantType, String>) at 0x18
//   AttackRangeType at 0x20

var _method_get_param_count = new NativeFunction(
    il2cpp.findExportByName("il2cpp_method_get_param_count"), "uint32", ["pointer"]);

// --- Dict layout ---
// Concrete dict offsets (from probe — generic def returns 0 for all)
var _dictCountOff = 32;   // 0x20
var _dictEntriesOff = 24; // 0x18

function readDictIntString(dictPtr) {
    var result = {};
    if (!dictPtr || dictPtr.isNull()) return result;
    try {
        var count = dictPtr.add(_dictCountOff).readS32();
        var entriesArr = dictPtr.add(_dictEntriesOff).readPointer();
        if (entriesArr.isNull() || count <= 0 || count > 500) return result;
        var dataStart = entriesArr.add(0x20);
        for (var i = 0; i < count; i++) {
            var base = dataStart.add(i * 24);
            if (base.readS32() < 0) continue;
            var key = base.add(8).readS32();
            var valPtr = base.add(16).readPointer();
            var valStr = readIl2cppString(valPtr);
            if (valStr !== null) result[key] = valStr;
        }
    } catch(e) {}
    return result;
}

function readDictIntStringArr(dictPtr) {
    // Variables is Dict<AbilityVariableType, String[]> — elements are 8-byte string pointers
    var result = {};
    if (!dictPtr || dictPtr.isNull()) return result;
    try {
        var count = dictPtr.add(_dictCountOff).readS32();
        var entriesArr = dictPtr.add(_dictEntriesOff).readPointer();
        if (entriesArr.isNull() || count <= 0 || count > 500) return result;
        var dataStart = entriesArr.add(0x20);
        for (var i = 0; i < count; i++) {
            var base = dataStart.add(i * 24);
            if (base.readS32() < 0) continue;
            var key = base.add(8).readS32();
            var arrPtr = base.add(16).readPointer();
            if (arrPtr.isNull()) continue;
            var arrLen = arrPtr.add(0x18).readS32();
            var vals = [];
            for (var j = 0; j < Math.min(arrLen, 100); j++) {
                var strPtr = arrPtr.add(0x20 + j * 8).readPointer();
                vals.push(readIl2cppString(strPtr));
            }
            result[key] = vals;
        }
    } catch(e) {}
    return result;
}

function readConfig(configPtr) {
    if (!configPtr || configPtr.isNull()) return null;
    try {
        var varsDict = configPtr.add(0x10).readPointer();
        var constsDict = configPtr.add(0x18).readPointer();
        var vars = readDictIntStringArr(varsDict);
        var consts = readDictIntString(constsDict);
        // Skip truly empty configs (no vars AND no consts)
        if (Object.keys(vars).length === 0 && Object.keys(consts).length === 0) return null;
        var result = {};
        if (Object.keys(vars).length > 0) result.Variables = vars;
        if (Object.keys(consts).length > 0) result.Constants = consts;
        return result;
    } catch(e) { return null; }
}

// --- AbilitiesDatabase ---
var _abDbOff = getFieldOffset(runnerClass, "<AbilitiesDatabase>k__BackingField");
var _abDbClass = findClass("BattleLogicAssembly.dll", "IdunBattle.Core.Services", "AbilitiesDatabase");

// Collect all GetConfig overloads
var _getConfigMethods = [];
if (_abDbClass) {
    var it = Memory.alloc(Process.pointerSize);
    it.writePointer(ptr(0));
    var m;
    while (!(m = class_get_methods(_abDbClass, it)).isNull()) {
        if (s(method_get_name(m)) === "GetConfig") {
            _getConfigMethods.push({info: m, paramCount: _method_get_param_count(m)});
        }
    }
}

send({t: "dump_setup", overloads: _getConfigMethods.length, dictCountOff: _dictCountOff, dictEntriesOff: _dictEntriesOff});

function dumpAllConfigs() {
    if (!runnerInstance) {
        send({t: "error", msg: "No runner — must be in combat"});
        return;
    }
    var abDb = runnerInstance.add(_abDbOff).readPointer();
    if (abDb.isNull()) {
        send({t: "error", msg: "AbilitiesDatabase is null"});
        return;
    }

    // overloads: [0]=ActiveAbilityType, [1]=TriggeredAbilityType, [2]=ConfigId, [3]=UnitTrait
    var results = {active: {}, triggered: {}, traits: {}};
    var stats = {active: 0, triggered: 0, traits: 0, errors: 0};

    // --- Active abilities (0..1600) ---
    send({t: "progress", msg: "Dumping active abilities..."});
    if (_getConfigMethods.length >= 1) {
        for (var i = 0; i <= 1600; i++) {
            try {
                var arg = Memory.alloc(4); arg.writeS32(i);
                var cfg = invokeMethod(_getConfigMethods[0].info, abDb, [arg]);
                if (cfg && !cfg.isNull()) {
                    var data = readConfig(cfg);
                    if (data) { results.active[i] = data; stats.active++; }
                }
            } catch(e) { stats.errors++; }
        }
    }

    // --- Triggered abilities (0..1600) ---
    send({t: "progress", msg: "Dumping triggered abilities..."});
    if (_getConfigMethods.length >= 2) {
        for (var i = 0; i <= 1600; i++) {
            try {
                var arg = Memory.alloc(4); arg.writeS32(i);
                var cfg = invokeMethod(_getConfigMethods[1].info, abDb, [arg]);
                if (cfg && !cfg.isNull()) {
                    var data = readConfig(cfg);
                    if (data) { results.triggered[i] = data; stats.triggered++; }
                }
            } catch(e) { stats.errors++; }
        }
    }

    // --- Traits (0..1200) ---
    send({t: "progress", msg: "Dumping trait configs..."});
    if (_getConfigMethods.length >= 4) {
        for (var i = 0; i <= 1200; i++) {
            try {
                var arg = Memory.alloc(4); arg.writeS32(i);
                var cfg = invokeMethod(_getConfigMethods[3].info, abDb, [arg]);
                if (cfg && !cfg.isNull()) {
                    var data = readConfig(cfg);
                    if (data) { results.traits[i] = data; stats.traits++; }
                }
            } catch(e) { stats.errors++; }
        }
    }

    send({t: "all_configs_dump", results: results, stats: stats});
    console.log("[*] Dump done: " + stats.active + " active, " + stats.triggered + " triggered, " + stats.traits + " traits, " + stats.errors + " errors");
}

// Run on first Update frame (needs runner)
var _dumpDone = false;
var _origUpdate = null;
var _updateMethod = findMethod(
    findClass("Assembly-CSharp.dll", "IdunBattle.View.Game", "IdunGameViews"), "Update");

if (_updateMethod) {
    _origUpdate = new NativeFunction(_updateMethod.ptr, "void", ["pointer", "pointer"]);
    Interceptor.replace(_updateMethod.ptr, new NativeCallback(function(self, methodInfo) {
        if (!_dumpDone) {
            var _gvRunnerOff = getFieldOffset(
                findClass("Assembly-CSharp.dll", "IdunBattle.View.Game", "IdunGameViews"), "_runner");
            if (!runnerInstance && _gvRunnerOff >= 0) {
                var r = self.add(_gvRunnerOff).readPointer();
                if (!r.isNull()) runnerInstance = r;
            }
            if (runnerInstance) {
                _dumpDone = true;
                try { dumpAllConfigs(); } catch(e) {
                    send({t: "error", msg: "dump failed: " + e.message});
                }
            }
        }
        _origUpdate(self, methodInfo);
    }, "void", ["pointer", "pointer"]));
    console.log("[+] Waiting for first Update frame to dump configs...");
} else {
    console.log("[-] IdunGameViews.Update not found — not in combat?");
}