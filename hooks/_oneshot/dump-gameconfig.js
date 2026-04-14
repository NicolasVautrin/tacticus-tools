// oneshot: Dump units lineup from GameConfig (activeAbilities, passiveAbilities, traits, etc.)
// requires: _utils/il2cpp-helpers, _utils/il2cpp-invoke, _utils/il2cpp-serializer
//
// Does NOT require combat — reads from thor.Globals.gameConfigData (static).
//
// Compose:
//   cat _utils/il2cpp-helpers.js _utils/il2cpp-invoke.js _utils/il2cpp-serializer.js \
//       _oneshot/dump-gameconfig.js > /tmp/dump-gameconfig-composed.js

// --- Locate thor.Globals.gameConfigData ---
var _globalsClass = findClass("Assembly-CSharp.dll", "thor", "Globals");
var _gameConfigDataOff = _globalsClass ? getFieldOffset(_globalsClass, "gameConfigData") : -1;

// GameConfigData -> gameConfigDto
var _gcdClass = findClass("MetaLogicAssembly.dll", "IdunMetaLogic.Client.DTO.Config", "GameConfigData");
var _gcdDtoOff = _gcdClass ? getFieldOffset(_gcdClass, "<gameConfigDto>k__BackingField") : -1;

// GameConfigDto -> units
var _gcdtoClass = findClass("MetaLogicAssembly.dll", "IdunMetaLogic.Client.DTO.Config", "GameConfigDto");
var _unitsOff = _gcdtoClass ? getFieldOffset(_gcdtoClass, "units") : -1;

// UnitsConfigDto -> lineup, abilities
var _unitsClass = findClass("MetaLogicAssembly.dll", "IdunMetaLogic.Client.DTO.Config", "UnitsConfigDto");
var _lineupOff = _unitsClass ? getFieldOffset(_unitsClass, "lineup") : -1;
var _abilitiesDictOff = _unitsClass ? getFieldOffset(_unitsClass, "abilities") : -1;

// BaseUnitConfigDto fields
var _baseUnitClass = findClass("MetaLogicAssembly.dll", "IdunMetaLogic.Client.DTO.Config", "BaseUnitConfigDto");
var _activeAbilitiesOff = _baseUnitClass ? getFieldOffset(_baseUnitClass, "activeAbilities") : -1;
var _passiveAbilitiesOff = _baseUnitClass ? getFieldOffset(_baseUnitClass, "passiveAbilities") : -1;
var _mythicAbilitiesOff = _baseUnitClass ? getFieldOffset(_baseUnitClass, "mythicAbilities") : -1;
var _traitsOff = _baseUnitClass ? getFieldOffset(_baseUnitClass, "traits") : -1;
var _factionOff = _baseUnitClass ? getFieldOffset(_baseUnitClass, "FactionId") : -1;
var _classOff = _baseUnitClass ? getFieldOffset(_baseUnitClass, "Class") : -1;
var _dmgTypeOff = _baseUnitClass ? getFieldOffset(_baseUnitClass, "DamageType") : -1;
var _rangeOff = _baseUnitClass ? getFieldOffset(_baseUnitClass, "Range") : -1;
var _movementOff = _baseUnitClass ? getFieldOffset(_baseUnitClass, "Movement") : -1;

function readStringList(listPtr) {
    if (listPtr.isNull()) return [];
    var items = listPtr.add(0x10).readPointer();
    var size = listPtr.add(0x18).readS32();
    if (items.isNull() || size <= 0 || size > 100) return [];
    var r = [];
    for (var i = 0; i < size; i++) {
        var sp = items.add(0x20 + i * Process.pointerSize).readPointer();
        r.push(sp.isNull() ? null : readIl2cppString(sp));
    }
    return r;
}

function readIntList(listPtr) {
    if (listPtr.isNull()) return [];
    var items = listPtr.add(0x10).readPointer();
    var size = listPtr.add(0x18).readS32();
    if (items.isNull() || size <= 0 || size > 100) return [];
    var r = [];
    for (var i = 0; i < size; i++) {
        r.push(items.add(0x20 + i * 4).readS32());
    }
    return r;
}

var _runtime_class_init = new NativeFunction(
    il2cpp.findExportByName("il2cpp_runtime_class_init"), "void", ["pointer"]);
var _class_get_static_field_data = new NativeFunction(
    il2cpp.findExportByName("il2cpp_class_get_static_field_data"), "pointer", ["pointer"]);

function readStaticField(klass, fieldName) {
    _runtime_class_init(klass);
    var staticData = _class_get_static_field_data(klass);
    if (staticData.isNull()) return ptr(0);
    var it = Memory.alloc(Process.pointerSize); it.writePointer(ptr(0));
    var f;
    while (!(f = class_get_fields(klass, it)).isNull()) {
        if (s(field_get_name(f)) === fieldName) {
            var off = field_get_offset(f);
            var val = staticData.add(off).readPointer();
            return val;
        }
    }
    return ptr(0);
}

function dumpGameConfig() {
    // Read the Globals singleton instance, then read gameConfigData as instance field
    _runtime_class_init(_globalsClass);
    var staticData = _class_get_static_field_data(_globalsClass);
    // globals singleton is at offset 8 in static data
    var globalsOff = getFieldOffset(_globalsClass, "globals");
    var globals = staticData.add(globalsOff).readPointer();
    if (globals.isNull()) {
        send({t: "error", msg: "Globals singleton is null"});
        return;
    }
    // gameConfigData is also a static field — but the static data has wrong value
    // Try reading it as if it were stored on the singleton instance via serialize
    // Actually: gameConfigData IS a static field, not an instance field
    // The static data at offset 160 has the wrong object — let's try iterating
    // all pointer-sized values in a range around the singleton to find GameConfigData
    var gcd = ptr(0);
    // Alternative: search static data for an object with class GameConfigData
    for (var probe = 0; probe < 800; probe += Process.pointerSize) {
        try {
            var candidate = staticData.add(probe).readPointer();
            if (!candidate.isNull()) {
                var cn = s(class_get_name(candidate.readPointer()));
                if (cn === "GameConfigData") {
                    gcd = candidate;
                    send({t: "debug", msg: "Found GameConfigData at static offset " + probe});
                    break;
                }
            }
        } catch(e) {}
    }
    if (gcd.isNull()) {
        // Try on the singleton instance instead
        send({t: "debug", msg: "Not in static data, trying on globals instance..."});
        for (var probe2 = 16; probe2 < 800; probe2 += Process.pointerSize) {
            try {
                var candidate = globals.add(probe2).readPointer();
                if (!candidate.isNull()) {
                    var cn = s(class_get_name(candidate.readPointer()));
                    if (cn === "GameConfigData") {
                        gcd = candidate;
                        send({t: "debug", msg: "Found GameConfigData on instance at offset " + probe2});
                        break;
                    }
                }
            } catch(e) {}
        }
    }
    if (gcd.isNull()) {
        send({t: "error", msg: "GameConfigData not found anywhere"});
        return;
    }
    // Debug: show GCD structure
    try {
        var gcdKeys = serialize(gcd, 1);
        send({t: "debug_gcd_keys", data: Object.keys(gcdKeys)});
    } catch(e) { send({t: "debug", msg: "serialize gcd failed: " + e.message}); }

    var dto = gcd.add(_gcdDtoOff).readPointer();
    if (dto.isNull()) {
        send({t: "error", msg: "gameConfigDto is null at offset " + _gcdDtoOff + ", trying serialize to find it"});
        return;
    }

    var unitsConfig = dto.add(_unitsOff).readPointer();
    if (unitsConfig.isNull()) {
        send({t: "error", msg: "UnitsConfigDto is null"});
        return;
    }

    // --- Read lineup dict: Dictionary<string, LineupUnitConfigDto> ---
    var lineupDict = unitsConfig.add(_lineupOff).readPointer();
    if (lineupDict.isNull()) {
        send({t: "error", msg: "lineup dict is null"});
        return;
    }

    // Read dict entries
    var count = lineupDict.add(0x20).readS32();
    send({t: "progress", msg: "Reading " + count + " units from lineup..."});

    var entries = lineupDict.add(0x18).readPointer();
    if (entries.isNull()) {
        send({t: "error", msg: "lineup entries null"});
        return;
    }

    // Introspect Entry struct size
    var entriesKlass = entries.readPointer();
    var entryKlass = class_get_element_class(entriesKlass);
    var entrySize = class_instance_size(entryKlass) - 16;

    var result = {};
    for (var i = 0; i < count; i++) {
        var entryBase = entries.add(0x20 + i * entrySize);
        var hashCode = entryBase.readS32();
        if (hashCode < 0) continue;

        // Entry struct: hashCode(4), next(4), key(ptr), value(ptr)
        var keyPtr = entryBase.add(8).readPointer();
        var valPtr = entryBase.add(8 + Process.pointerSize).readPointer();
        if (keyPtr.isNull() || valPtr.isNull()) continue;

        var unitId = readIl2cppString(keyPtr);
        try {
            var unit = {
                activeAbilities: readStringList(valPtr.add(_activeAbilitiesOff).readPointer()),
                passiveAbilities: readStringList(valPtr.add(_passiveAbilitiesOff).readPointer()),
                mythicAbilities: readStringList(valPtr.add(_mythicAbilitiesOff).readPointer()),
                traits: readIntList(valPtr.add(_traitsOff).readPointer()),
                faction: (function() { var p = valPtr.add(_factionOff).readPointer(); return p.isNull() ? null : readIl2cppString(p); })(),
                class: valPtr.add(_classOff).readS32(),
                damageType: valPtr.add(_dmgTypeOff).readS32(),
                range: valPtr.add(_rangeOff).readS32(),
                movement: valPtr.add(_movementOff).readS32(),
            };
            result[unitId] = unit;
        } catch(e) {
            result[unitId] = {_error: e.message};
        }
    }

    send({t: "gameconfig_dump", units: result, count: Object.keys(result).length});

    // --- Dump abilities dict: Dictionary<string, AbilityConfigDto> ---
    var abilitiesDict = unitsConfig.add(_abilitiesDictOff).readPointer();
    if (!abilitiesDict.isNull()) {
        var abCount = abilitiesDict.add(0x20).readS32();
        send({t: "progress", msg: "Reading " + abCount + " abilities from config..."});
        var abEntries = abilitiesDict.add(0x18).readPointer();
        if (!abEntries.isNull()) {
            var abEntriesKlass = abEntries.readPointer();
            var abEntryKlass = class_get_element_class(abEntriesKlass);
            var abEntrySize = class_instance_size(abEntryKlass) - 16;
            var abilities = {};
            for (var ai = 0; ai < abCount; ai++) {
                var abBase = abEntries.add(0x20 + ai * abEntrySize);
                if (abBase.readS32() < 0) continue;
                var abKeyPtr = abBase.add(8).readPointer();
                var abValPtr = abBase.add(8 + Process.pointerSize).readPointer();
                if (abKeyPtr.isNull() || abValPtr.isNull()) continue;
                var abId = readIl2cppString(abKeyPtr);
                try {
                    abilities[abId] = serialize(abValPtr, 4);
                } catch(e) {
                    abilities[abId] = {_error: e.message};
                }
            }
            send({t: "gameconfig_abilities", abilities: abilities, count: Object.keys(abilities).length});
        }
    }

    // --- Dump summons ---
    var summonsOff = getFieldOffset(_unitsClass, "summons");
    var summonsDict = unitsConfig.add(summonsOff).readPointer();
    if (!summonsDict.isNull()) {
        var smCount = summonsDict.add(0x20).readS32();
        send({t: "progress", msg: "Reading " + smCount + " summons..."});
        var smEntries = summonsDict.add(0x18).readPointer();
        if (!smEntries.isNull()) {
            var smEntriesKlass = smEntries.readPointer();
            var smEntryKlass = class_get_element_class(smEntriesKlass);
            var smEntrySize = class_instance_size(smEntryKlass) - 16;
            var summons = {};
            for (var si = 0; si < smCount; si++) {
                var smBase = smEntries.add(0x20 + si * smEntrySize);
                if (smBase.readS32() < 0) continue;
                var smKeyPtr = smBase.add(8).readPointer();
                var smValPtr = smBase.add(8 + Process.pointerSize).readPointer();
                if (smKeyPtr.isNull() || smValPtr.isNull()) continue;
                var smId = readIl2cppString(smKeyPtr);
                try {
                    summons[smId] = {
                        activeAbilities: readStringList(smValPtr.add(_activeAbilitiesOff).readPointer()),
                        passiveAbilities: readStringList(smValPtr.add(_passiveAbilitiesOff).readPointer()),
                        faction: (function() { var p = smValPtr.add(_factionOff).readPointer(); return p.isNull() ? null : readIl2cppString(p); })(),
                        range: smValPtr.add(_rangeOff).readS32(),
                        movement: smValPtr.add(_movementOff).readS32(),
                    };
                } catch(e) {
                    summons[smId] = {_error: e.message};
                }
            }
            send({t: "gameconfig_summons", summons: summons, count: Object.keys(summons).length});
        }
    }
}

// Execute after a short delay to let the script settle
setTimeout(dumpGameConfig, 500);