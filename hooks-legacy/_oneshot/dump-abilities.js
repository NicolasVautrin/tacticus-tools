// oneshot: Dump ability configs from AbilitiesDatabase
// requires: _utils/il2cpp-helpers, _utils/il2cpp-invoke, _utils/il2cpp-serializer, _utils/matchstate-reader
//
// Must be injected IN COMBAT (runner must exist).
// Iterates over all known ActiveAbilityType values, calls GetConfig() on each,
// and serializes the result. Sends {t: "abilities_dump", abilities: {...}}.
//
// Compose:
//   cat _utils/il2cpp-helpers.js _utils/il2cpp-invoke.js _utils/il2cpp-serializer.js \
//       _utils/matchstate-reader.js _oneshot/dump-abilities.js > /tmp/dump-abilities-composed.js

// --- Locate AbilitiesDatabase on the runner ---
var _abDbOff = getFieldOffset(runnerClass, "<AbilitiesDatabase>k__BackingField");
var _abDbClass = findClass("BattleLogicAssembly.dll", "IdunBattle.Core.Services", "AbilitiesDatabase");
var _getConfigActive = _abDbClass ? findMethod(_abDbClass, "GetConfig") : null;

// --- ActiveAbilityType enum values from symbols.json are ints 0..~1500 ---
// We probe a range and skip nulls.

send({t: "progress", msg: "Waiting for runner..."});

function dumpAbilities() {
    if (!runnerInstance) {
        send({t: "error", msg: "No runner — must be in combat"});
        return;
    }

    var abDb = runnerInstance.add(_abDbOff).readPointer();
    if (abDb.isNull()) {
        send({t: "error", msg: "AbilitiesDatabase is null"});
        return;
    }

    if (!_getConfigActive) {
        send({t: "error", msg: "GetConfig method not found"});
        return;
    }

    send({t: "progress", msg: "Dumping abilities..."});

    var abilities = {};
    var count = 0;
    var errors = 0;

    // Probe ability types 0..1600 (covers all known ActiveAbilityType values)
    for (var i = 0; i <= 1600; i++) {
        try {
            var typeArg = Memory.alloc(4);
            typeArg.writeS32(i);
            var config = invokeMethod(_getConfigActive.info, abDb, [typeArg]);
            if (config && !config.isNull()) {
                var serialized = serialize(config, 8);
                if (serialized && typeof serialized === "object") {
                    abilities[i] = serialized;
                    count++;
                }
            }
        } catch(e) {
            errors++;
        }
    }

    send({t: "progress", msg: "Dumping triggered abilities..."});

    // Triggered abilities
    var _getConfigTriggered = null;
    // GetConfig has overloads — find the one for TriggeredAbilityType
    // We already got the first overload (ActiveAbilityType). Try finding others.
    var _trigAbTypeClass = findClass("BattleLogicAssembly.dll", "IdunBattle.Entities.Enum", "TriggeredAbilityType");

    var triggered = {};
    var trigCount = 0;

    // Use the second GetConfig overload (TriggeredAbilityType)
    // findMethod returns first match — we need to iterate
    if (_abDbClass) {
        var it = Memory.alloc(Process.pointerSize);
        it.writePointer(ptr(0));
        var m;
        var getConfigMethods = [];
        while (!(m = class_get_methods(_abDbClass, it)).isNull()) {
            var name = s(method_get_name(m));
            if (name === "GetConfig") {
                getConfigMethods.push(m);
            }
        }
        // getConfigMethods[0] = ActiveAbilityType, [1] = TriggeredAbilityType, [2] = ConfigId, [3] = UnitTrait
        if (getConfigMethods.length >= 2) {
            _getConfigTriggered = {ptr: getConfigMethods[1], info: getConfigMethods[1]};
        }
    }

    if (_getConfigTriggered) {
        for (var i = 0; i <= 1600; i++) {
            try {
                var typeArg = Memory.alloc(4);
                typeArg.writeS32(i);
                var config = invokeMethod(_getConfigTriggered.info, abDb, [typeArg]);
                if (config && !config.isNull()) {
                    var serialized = serialize(config, 8);
                    if (serialized && typeof serialized === "object") {
                        triggered[i] = serialized;
                        trigCount++;
                    }
                }
            } catch(e) {
                errors++;
            }
        }
    }

    send({t: "abilities_dump", abilities: abilities, triggered: triggered,
          stats: {active: count, triggered: trigCount, errors: errors}});
    console.log("[*] Abilities dump: " + count + " active, " + trigCount + " triggered, " + errors + " errors");

    // --- Trait configs via GetConfig(UnitTrait) ---
    if (getConfigMethods.length >= 4) {
        send({t: "progress", msg: "Dumping trait configs..."});
        var traits = {};
        var traitCount = 0;
        for (var ti = 0; ti <= 1100; ti++) {
            try {
                var traitArg = Memory.alloc(4);
                traitArg.writeS32(ti);
                var traitConfig = invokeMethod(getConfigMethods[3], abDb, [traitArg]);
                if (traitConfig && !traitConfig.isNull()) {
                    var traitSerialized = serialize(traitConfig, 8);
                    if (traitSerialized && typeof traitSerialized === "object") {
                        traits[ti] = traitSerialized;
                        traitCount++;
                    }
                }
            } catch(e) {
                errors++;
            }
        }
        send({t: "traits_dump", traits: traits, count: traitCount});
        console.log("[*] Traits dump: " + traitCount + " configs");
    }
}

// Run on next Update frame (needs runner)
var _dumpDone = false;
var _origDumpUpdate = null;
var _dumpUpdateMethod = findMethod(
    findClass("Assembly-CSharp.dll", "IdunBattle.View.Game", "IdunGameViews"), "Update");

if (_dumpUpdateMethod) {
    _origDumpUpdate = new NativeFunction(_dumpUpdateMethod.ptr, "void", ["pointer", "pointer"]);
    Interceptor.replace(_dumpUpdateMethod.ptr, new NativeCallback(function(self, methodInfo) {
        if (!_dumpDone) {
            // Capture runner from GameViews._runner
            var _gvRunnerOff2 = getFieldOffset(
                findClass("Assembly-CSharp.dll", "IdunBattle.View.Game", "IdunGameViews"), "_runner");
            if (!runnerInstance && _gvRunnerOff2 >= 0) {
                var r = self.add(_gvRunnerOff2).readPointer();
                if (!r.isNull()) runnerInstance = r;
            }
            if (runnerInstance) {
                _dumpDone = true;
                try {
                    dumpAbilities();
                } catch(e) {
                    send({t: "error", msg: "dump failed: " + e.message});
                }
            }
        }
        _origDumpUpdate(self, methodInfo);
    }, "void", ["pointer", "pointer"]));
    console.log("[+] Dump-abilities: waiting for first Update frame");
} else {
    console.log("[-] IdunGameViews.Update not found — not in combat?");
}
