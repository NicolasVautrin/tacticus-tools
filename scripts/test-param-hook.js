// Test: GetConfig(UnitTrait) + StatefulAbilityConfiguration.GetVariableForLevel
// for traits with empty configs — do they return computed values?

var _abDbOff = getFieldOffset(runnerClass, "<AbilitiesDatabase>k__BackingField");
var _abDbClass = findClass("BattleLogicAssembly.dll", "IdunBattle.Core.Services", "AbilitiesDatabase");
var _sacClass = findClass("MetaLogicAssembly.dll", "idun.meta", "StatefulAbilityConfiguration");
var _getAllVars = _sacClass ? findMethod(_sacClass, "GetAllVariablesForLevel") : null;
var _getVarForLevel = _sacClass ? findMethod(_sacClass, "GetVariableForLevel") : null;

var _method_get_param_count = new NativeFunction(
    il2cpp.findExportByName("il2cpp_method_get_param_count"), "uint32", ["pointer"]);
var _object_new = new NativeFunction(
    il2cpp.findExportByName("il2cpp_object_new"), "pointer", ["pointer"]);

// GetConfig overloads
var _getConfigMethods = [];
if (_abDbClass) {
    var it = Memory.alloc(Process.pointerSize);
    it.writePointer(ptr(0));
    var m;
    while (!(m = class_get_methods(_abDbClass, it)).isNull()) {
        if (s(method_get_name(m)) === "GetConfig") _getConfigMethods.push(m);
    }
}

// SAC 3-param ctor
var _sacCtor3 = null;
if (_sacClass) {
    var it2 = Memory.alloc(Process.pointerSize);
    it2.writePointer(ptr(0));
    var m2;
    while (!(m2 = class_get_methods(_sacClass, it2)).isNull()) {
        if (s(method_get_name(m2)) === ".ctor" && _method_get_param_count(m2) === 3) {
            _sacCtor3 = m2;
            break;
        }
    }
}

// AbilityVariableType enum — find all values
var _avtClass = findClass("BattleLogicAssembly.dll", "IdunBattle.Configuration", "AbilityVariableType");

send({t: "test_setup", configs: _getConfigMethods.length, sac: !!_sacClass, ctor3: !!_sacCtor3,
      getAllVars: !!_getAllVars, getVarForLevel: !!_getVarForLevel});

var _testRun = 0;
var _origGS = getSerializedState;
getSerializedState = function(depth) {
    if (_testRun < 1 && runnerInstance) {
        _testRun++;
        var abDb = runnerInstance.add(_abDbOff).readPointer();

        // Test traits: GetConfig(UnitTrait) → SAC → GetVariableForLevel
        var traitTests = [
            {name: "LetTheGalaxyBurn", id: 1058, stateIdx: 40},
            {name: "TerminatorArmour", id: 1039, stateIdx: 40},
            {name: "CrushingStrike", id: 1044, stateIdx: 40},
            {name: "Parry", id: 1031, stateIdx: 40},
            {name: "RapidAssault", id: 1043, stateIdx: 40},
            {name: "Terrifying", id: 34, stateIdx: 40},
        ];

        for (var ti = 0; ti < traitTests.length; ti++) {
            var tt = traitTests[ti];
            try {
                // 1. GetConfig(UnitTrait)
                var typeArg = Memory.alloc(4);
                typeArg.writeS32(tt.id);
                var config = invokeMethod(_getConfigMethods[3], abDb, [typeArg]);
                var configNull = !config || config.isNull();

                // 2. Serialize raw config
                var rawConfig = configNull ? null : serialize(config, 4);

                // 3. Create SAC + GetAllVariablesForLevel
                var sacVars = null;
                if (!configNull && _sacCtor3) {
                    var stateArg = Memory.alloc(8);
                    stateArg.writeS32(tt.stateIdx);
                    var sac = _object_new(_sacClass);
                    invokeMethod(_sacCtor3, sac, [stateArg, config, ptr(0)]);
                    var vars = invokeMethod(_getAllVars.info, sac, []);
                    if (vars && !vars.isNull()) {
                        sacVars = serialize(vars, 3);
                    }

                    // 4. Try GetVariableForLevel for specific known types (0..20)
                    // Returns boxed Int32 — value at ptr+0x10
                    var varValues = {};
                    if (_getVarForLevel) {
                        for (var vi = 0; vi < 20; vi++) {
                            try {
                                var vtArg = Memory.alloc(4);
                                vtArg.writeS32(vi);
                                var fbArg = Memory.alloc(4);
                                fbArg.writeS32(1); // fallbackToDefault = true
                                var boxed = invokeMethod(_getVarForLevel.info, sac, [vtArg, fbArg]);
                                if (boxed && !boxed.isNull()) {
                                    var intVal = boxed.add(0x10).readS32();
                                    if (intVal !== 0) {
                                        varValues[vi] = intVal;
                                    }
                                }
                            } catch(e) {}
                        }
                    }
                }

                send({t: "trait_test", name: tt.name, id: tt.id, state: tt.stateIdx,
                      configNull: configNull,
                      rawConstants: rawConfig ? (rawConfig.Constants || null) : null,
                      rawVariables: rawConfig ? Object.keys(rawConfig.Variables || {}) : null,
                      sacVarsCount: sacVars ? sacVars._count : null,
                      varValues: varValues || null});
            } catch(e) {
                send({t: "trait_test", name: tt.name, error: e.message});
            }
        }
    }
    return _origGS(depth);
};
console.log("[*] Trait SAC test ready — call get_state");