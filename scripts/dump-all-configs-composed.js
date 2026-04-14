// util: IL2CPP Helpers — shared NativeFunction wrappers, class/method resolution, message parsing
// provides: il2cpp, il2cppBase, il2cppSize, s(), getStack(), findClass(), findMethod(),
//           hook(), readMsgClass(), readMsgDetails()

var il2cpp = Process.findModuleByName("libil2cpp.so");
var il2cppBase = il2cpp.base;
var il2cppSize = il2cpp.size;

// --- IL2CPP C API wrappers ---
var domain_get = new NativeFunction(il2cpp.findExportByName("il2cpp_domain_get"), "pointer", []);
var domain_get_assemblies = new NativeFunction(il2cpp.findExportByName("il2cpp_domain_get_assemblies"), "pointer", ["pointer", "pointer"]);
var assembly_get_image = new NativeFunction(il2cpp.findExportByName("il2cpp_assembly_get_image"), "pointer", ["pointer"]);
var image_get_class_count = new NativeFunction(il2cpp.findExportByName("il2cpp_image_get_class_count"), "uint32", ["pointer"]);
var image_get_class = new NativeFunction(il2cpp.findExportByName("il2cpp_image_get_class"), "pointer", ["pointer", "uint32"]);
var class_get_name = new NativeFunction(il2cpp.findExportByName("il2cpp_class_get_name"), "pointer", ["pointer"]);
var class_get_namespace = new NativeFunction(il2cpp.findExportByName("il2cpp_class_get_namespace"), "pointer", ["pointer"]);
var image_get_name = new NativeFunction(il2cpp.findExportByName("il2cpp_image_get_name"), "pointer", ["pointer"]);
var class_get_methods = new NativeFunction(il2cpp.findExportByName("il2cpp_class_get_methods"), "pointer", ["pointer", "pointer"]);
var method_get_name = new NativeFunction(il2cpp.findExportByName("il2cpp_method_get_name"), "pointer", ["pointer"]);

// --- Helpers ---

function s(p) {
    try { return p.readUtf8String() || ""; } catch (e) { return ""; }
}

// --- Stack trace (raw offsets — resolved by backend via symbols.json) ---

function getStack(ctx) {
    var bt = Thread.backtrace(ctx, Backtracer.ACCURATE);
    var frames = [];
    for (var i = 0; i < Math.min(bt.length, 15); i++) {
        var addr = bt[i];
        var off = addr.sub(il2cppBase);
        if (off.compare(0) >= 0 && off.compare(il2cppSize) < 0) {
            frames.push(off.toInt32());
        }
    }
    return frames;
}

// --- Class / method resolution (cached) ---

var classCache = {};
function findClass(asm, ns, cls) {
    var key = asm + "::" + ns + "." + cls;
    if (classCache[key]) return classCache[key];
    var domain = domain_get();
    var sizePtr = Memory.alloc(4);
    var assemblies = domain_get_assemblies(domain, sizePtr);
    var count = sizePtr.readU32();
    for (var i = 0; i < count; i++) {
        var assembly = assemblies.add(i * Process.pointerSize).readPointer();
        var image = assembly_get_image(assembly);
        if (s(image_get_name(image)) !== asm) continue;
        var cc = image_get_class_count(image);
        for (var j = 0; j < cc; j++) {
            var k = image_get_class(image, j);
            if (s(class_get_name(k)) === cls && s(class_get_namespace(k)) === ns) {
                classCache[key] = k;
                return k;
            }
        }
    }
    return null;
}

function findMethod(klass, name) {
    var it = Memory.alloc(Process.pointerSize);
    it.writePointer(ptr(0));
    var m;
    while (!(m = class_get_methods(klass, it)).isNull()) {
        if (s(method_get_name(m)) === name) return { info: m, ptr: m.readPointer() };
    }
    return null;
}

function hook(asm, ns, cls, mth, cb) {
    var k = findClass(asm, ns, cls);
    if (!k) { console.log("[-] " + cls + " not found"); return; }
    var m = findMethod(k, mth);
    if (!m || m.ptr.isNull()) { console.log("[-] " + cls + "." + mth + " not found"); return; }
    try {
        Interceptor.attach(m.ptr, cb);
        console.log("[+] " + cls + "." + mth);
    } catch (e) {
        console.log("[!] " + cls + "." + mth + " — cannot hook: " + e.message);
    }
}

// --- Field offset resolution (cached) ---

var class_get_fields = new NativeFunction(il2cpp.findExportByName("il2cpp_class_get_fields"), "pointer", ["pointer", "pointer"]);
var class_get_parent = new NativeFunction(il2cpp.findExportByName("il2cpp_class_get_parent"), "pointer", ["pointer"]);
var field_get_name = new NativeFunction(il2cpp.findExportByName("il2cpp_field_get_name"), "pointer", ["pointer"]);
var field_get_offset = new NativeFunction(il2cpp.findExportByName("il2cpp_field_get_offset"), "int32", ["pointer"]);

var fieldOffsetCache = {};
function getFieldOffset(klass, fieldName) {
    var key = klass.toString() + "." + fieldName;
    if (fieldOffsetCache[key] !== undefined) return fieldOffsetCache[key];
    // Walk up the class hierarchy to find inherited fields
    var k = klass;
    while (!k.isNull()) {
        var it = Memory.alloc(Process.pointerSize); it.writePointer(ptr(0));
        var f;
        while (!(f = class_get_fields(k, it)).isNull()) {
            if (s(field_get_name(f)) === fieldName) {
                var off = field_get_offset(f);
                fieldOffsetCache[key] = off;
                return off;
            }
        }
        k = class_get_parent(k);
    }
    fieldOffsetCache[key] = -1;
    return -1;
}

// --- IL2CPP string reader ---

function readIl2cppString(objPtr) {
    if (objPtr.isNull()) return null;
    try {
        var len = objPtr.add(0x10).readS32();
        if (len <= 0 || len > 500) return null;
        return objPtr.add(0x14).readUtf16String(len);
    } catch (e) { return null; }
}

// --- Message parsing ---

function readMsgClass(msgPtr) {
    try { return s(class_get_name(msgPtr.readPointer())); } catch (e) { return "?"; }
}

function readMsgDetails(msg) {
    var cls = readMsgClass(msg);
    // Serialize the full message for comparison
    var d = serialize(msg, 3);
    d.msg = cls;
    return d;
}

console.log("[*] IL2CPP helpers loaded");
// util: IL2CPP Object creation & method invocation
// requires: _utils/il2cpp-helpers
// provides: il2cpp_object_new(), il2cpp_runtime_invoke(), invokeMethod(), createObject()

var il2cpp_object_new = new NativeFunction(
    il2cpp.findExportByName("il2cpp_object_new"), "pointer", ["pointer"]);
var il2cpp_runtime_invoke = new NativeFunction(
    il2cpp.findExportByName("il2cpp_runtime_invoke"), "pointer",
    ["pointer", "pointer", "pointer", "pointer"]);

function invokeMethod(methodInfo, obj, args) {
    var exc = Memory.alloc(Process.pointerSize);
    exc.writePointer(ptr(0));
    var params = ptr(0);
    if (args && args.length > 0) {
        params = Memory.alloc(args.length * Process.pointerSize);
        for (var i = 0; i < args.length; i++) {
            params.add(i * Process.pointerSize).writePointer(args[i]);
        }
    }
    var result = il2cpp_runtime_invoke(methodInfo, obj, params, exc);
    var excVal = exc.readPointer();
    if (!excVal.isNull()) {
        var excMsg = "IL2CPP exception";
        try {
            excMsg += " (" + s(class_get_name(excVal.readPointer())) + ")";
        } catch(e) {}
        throw new Error(excMsg);
    }
    return result;
}

function createObject(klass) {
    var obj = il2cpp_object_new(klass);
    if (obj.isNull()) throw new Error("il2cpp_object_new returned null");
    var ctor = findMethod(klass, ".ctor");
    if (ctor) invokeMethod(ctor.info, obj, null);
    return obj;
}

console.log("[*] IL2CPP invoke loaded");
// util: MatchState reader — runner access, turn detection, raw serialization, game queries
// requires: _utils/il2cpp-helpers, _utils/il2cpp-invoke, _utils/il2cpp-serializer
// provides: runnerInstance, isPlayerTurn(), getSerializedState(),
//           getEntityById(), getUnitTile(), queryReachableTiles(), queryDamagePrediction()

// --- Runner ---
var runnerClass = findClass("BattleLogicAssembly.dll", "IdunBattle.Runner", "IdunRunner");
var runnerApplyInfo = findMethod(runnerClass, "Apply");
var runnerStateOff = getFieldOffset(runnerClass, "_state");
var runnerPathfindersOff = getFieldOffset(runnerClass, "<Pathfinders>k__BackingField");
var runnerDamagePredOff = getFieldOffset(runnerClass, "<DamagePrediction>k__BackingField");
var runnerTargetingOff = getFieldOffset(runnerClass, "<TargetingQuery>k__BackingField");

// --- Entity offsets (for lookup + turn detection) ---
var _entityClass = findClass("BattleLogicAssembly.dll", "IdunBattle.Core", "Entity");
var _entityIdOff = getFieldOffset(_entityClass, "<Id>k__BackingField");
var _entityTypeOff = getFieldOffset(_entityClass, "<Type>k__BackingField");
var _entityComponentsOff = getFieldOffset(_entityClass, "Components");
var _msEntitiesOff = getFieldOffset(
    findClass("BattleLogicAssembly.dll", "IdunBattle.Core", "MatchState"), "_entities");

// --- Turn detection offsets ---
var _turnCompClass = findClass("BattleLogicAssembly.dll", "IdunBattle.Entities.Components", "TurnComponent");
var _turnCurrentPlayerOff = _turnCompClass ? getFieldOffset(_turnCompClass, "_currentPlayerId") : -1;
var _playerCompClass = findClass("BattleLogicAssembly.dll", "IdunBattle.Entities.Components", "PlayerComponent");
var _playerTypeOff = _playerCompClass ? getFieldOffset(_playerCompClass, "Type") : -1;

// --- Foot component offsets (for unit -> tile lookup) ---
var _footCompClass = findClass("BattleLogicAssembly.dll", "IdunBattle.Entities.Components", "UnitFootComponent");
var _footUnitIdOff = _footCompClass ? getFieldOffset(_footCompClass, "UnitId") : -1;
var _footTileIdOff = _footCompClass ? getFieldOffset(_footCompClass, "TileId") : -1;

// --- Movement component (for reachable tiles depth) ---
var _moveCompClass = findClass("BattleLogicAssembly.dll", "IdunBattle.Entities.Components", "MovementComponent");
var _moveInitialOff = _moveCompClass ? getFieldOffset(_moveCompClass, "InitialValue") : -1;

// --- Game service classes + methods ---
var _pathfindersClass = findClass("BattleLogicAssembly.dll", "IdunBattle.Entities.Pathfinding", "Pathfinders");
var _findReachableInfo = _pathfindersClass ? findMethod(_pathfindersClass, "FindReachableTiles") : null;

var _damagePredClass = findClass("BattleLogicAssembly.dll", "IdunBattle.Core.Services", "DamagePrediction");
var _predictNormalInfo = _damagePredClass ? findMethod(_damagePredClass, "PredictNormalAttack") : null;

var runnerInstance = null;
var matchStateRef = null; // fallback: captured from FSM tap before runner is available

// --- Internal helpers ---

function _readListPtrs(listPtr) {
    if (listPtr.isNull()) return [];
    var items = listPtr.add(0x10).readPointer();
    var size = listPtr.add(0x18).readS32();
    if (items.isNull() || size <= 0 || size > 5000) return [];
    var r = [];
    for (var i = 0; i < size; i++)
        r.push(items.add(0x20 + i * Process.pointerSize).readPointer());
    return r;
}

function _findComp(entity, name) {
    var arr = entity.add(_entityComponentsOff).readPointer();
    if (arr.isNull()) return null;
    var len = arr.add(0x18).readS32();
    for (var j = 0; j < Math.min(len, 50); j++) {
        var c = arr.add(0x20 + j * Process.pointerSize).readPointer();
        if (c.isNull()) continue;
        try { if (s(class_get_name(c.readPointer())) === name) return c; } catch(e) {}
    }
    return null;
}

function _getEntities() {
    var state = runnerInstance.add(runnerStateOff).readPointer();
    return _readListPtrs(state.add(_msEntitiesOff).readPointer());
}

// --- Public: entity lookup ---

function getEntityById(entityId) {
    if (!runnerInstance) return null;
    var entities = _getEntities();
    for (var i = 0; i < entities.length; i++) {
        var e = entities[i];
        if (!e.isNull() && e.add(_entityIdOff).readS32() === entityId) return e;
    }
    return null;
}

function getUnitTile(unitEntityId) {
    // FootEntity (type 5) links unit -> tile
    if (!runnerInstance) return null;
    var entities = _getEntities();
    for (var i = 0; i < entities.length; i++) {
        var e = entities[i];
        if (e.isNull() || e.add(_entityTypeOff).readS32() !== 5) continue;
        var fc = _findComp(e, "UnitFootComponent");
        if (fc && fc.add(_footUnitIdOff).readS32() === unitEntityId) {
            var tileId = fc.add(_footTileIdOff).readS32();
            return getEntityById(tileId);
        }
    }
    return null;
}

// --- Turn detection ---

function isPlayerTurn() {
    if (!runnerInstance) return false;
    try {
        var entities = _getEntities();
        var cur = -1, human = -1;
        for (var i = 0; i < entities.length; i++) {
            var e = entities[i];
            if (e.isNull()) continue;
            var t = e.add(_entityTypeOff).readS32();
            if (t === 2) {
                var tc = _findComp(e, "TurnComponent");
                if (tc) cur = tc.add(_turnCurrentPlayerOff).readS32();
            }
            if (t === 4) {
                var pc = _findComp(e, "PlayerComponent");
                if (pc && pc.add(_playerTypeOff).readS32() === 0)
                    human = e.add(_entityIdOff).readS32();
            }
        }
        return cur === human && cur !== -1;
    } catch(e) { return false; }
}

// --- Full state serialization ---

function getSerializedState(depth) {
    if (!runnerInstance) return null;
    try {
        var state = runnerInstance.add(runnerStateOff).readPointer();
        return serialize(state, depth || 4);
    } catch(e) { return {error: e.message}; }
}

// --- Game queries (called on main thread via RPC) ---

// Helper: allocate a value-type arg for il2cpp_runtime_invoke
function _valArg(value) {
    var p = Memory.alloc(8);
    p.writeS32(value);
    return p;
}

function queryReachableTiles(unitId) {
    if (!runnerInstance || !_findReachableInfo) return {error: "not ready"};
    var unit = getEntityById(unitId);
    if (!unit) return {error: "unit not found: " + unitId};
    var tile = getUnitTile(unitId);
    if (!tile) return {error: "tile not found for unit: " + unitId};

    // Read movement value from MovementComponent
    var moveComp = _findComp(unit, "MovementComponent");
    var depth = 3;
    if (moveComp && _moveInitialOff >= 0) {
        depth = moveComp.add(_moveInitialOff).readS32();
    }

    var pathfinders = runnerInstance.add(runnerPathfindersOff).readPointer();

    // Direct NativeFunction call (ARM64 IL2CPP convention):
    // this, PathfinderType(int), IEntity start, int depth, IEntity unit, MethodInfo*
    var findReachableFn = new NativeFunction(_findReachableInfo.ptr, "pointer",
        ["pointer", "int", "pointer", "int", "pointer", "pointer"]);
    var result = findReachableFn(pathfinders, 0, tile, depth, unit, _findReachableInfo.info);

    if (result.isNull()) return {error: "FindReachableTiles returned null"};

    // DisposableList<TileEntity> — read items before they get pooled
    // Read _size and iterate _items array
    var size = result.add(0x18).readS32();
    var items = result.add(0x10).readPointer();
    var tiles = [];
    for (var i = 0; i < Math.min(size, 200); i++) {
        var t = items.add(0x20 + i * Process.pointerSize).readPointer();
        if (t.isNull()) continue;
        var tid = t.add(_entityIdOff).readS32();
        tiles.push(tid);
    }
    return {unitId: unitId, depth: depth, tileIds: tiles, count: size};
}

function queryDamagePrediction(attackerId, defenderId) {
    if (!runnerInstance || !_predictNormalInfo) return {error: "not ready"};
    var attacker = getEntityById(attackerId);
    var defender = getEntityById(defenderId);
    if (!attacker) return {error: "attacker not found: " + attackerId};
    if (!defender) return {error: "defender not found: " + defenderId};

    var damagePred = runnerInstance.add(runnerDamagePredOff).readPointer();
    // PredictNormalAttack(attacker, attackerPosition, defender)
    // attackerPosition is UnitPosition — we need to construct it
    // For now, pass null and see if it works with just the attacker tile
    // TODO: construct UnitPosition properly
    return {error: "not yet implemented — needs UnitPosition construction"};
}

// Note: LocalizationQuery RPC was attempted but returns null for all abilities.
// Ability descriptions are resolved statically by the backend using I2 templates + abilities.json configs.


// queryAbilitiesInfo removed — LocalizationQuery RPC returns null.
// Descriptions are resolved by the backend via I2 templates + abilities.json.

console.log("[*] MatchState reader loaded");
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