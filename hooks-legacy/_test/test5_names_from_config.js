var il2cpp = Process.findModuleByName("libil2cpp.so");
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
var class_get_fields = new NativeFunction(il2cpp.findExportByName("il2cpp_class_get_fields"), "pointer", ["pointer", "pointer"]);
var field_get_name = new NativeFunction(il2cpp.findExportByName("il2cpp_field_get_name"), "pointer", ["pointer"]);
var field_get_offset = new NativeFunction(il2cpp.findExportByName("il2cpp_field_get_offset"), "int32", ["pointer"]);

function s(p) { try { return p.readUtf8String() || ""; } catch(e) { return ""; } }

function readIl2cppString(objPtr) {
    if (objPtr.isNull()) return null;
    try {
        var len = objPtr.add(0x10).readS32();
        if (len <= 0 || len > 500) return null;
        return objPtr.add(0x14).readUtf16String(len);
    } catch(e) { return null; }
}

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
                classCache[key] = k; return k;
            }
        }
    }
    return null;
}

function findMethod(klass, name) {
    var it = Memory.alloc(Process.pointerSize); it.writePointer(ptr(0));
    var m;
    while (!(m = class_get_methods(klass, it)).isNull()) {
        if (s(method_get_name(m)) === name) return { info: m, ptr: m.readPointer() };
    }
    return null;
}

function hook(asm, ns, cls, mth, cb) {
    var k = findClass(asm, ns, cls);
    if (!k) { send({t: "hook_fail", msg: cls + " not found"}); return; }
    var m = findMethod(k, mth);
    if (!m || m.ptr.isNull()) { send({t: "hook_fail", msg: cls + "." + mth + " not found"}); return; }
    try {
        Interceptor.attach(m.ptr, cb);
        send({t: "hook_ok", msg: cls + "." + mth});
    } catch(e) {
        send({t: "hook_fail", msg: cls + "." + mth + " -- " + e.message});
    }
}

var fieldCache = {};
function getFieldOffset(klass, fieldName) {
    var key = klass.toString() + "." + fieldName;
    if (fieldCache[key] !== undefined) return fieldCache[key];
    var it = Memory.alloc(Process.pointerSize); it.writePointer(ptr(0));
    var f;
    while (!(f = class_get_fields(klass, it)).isNull()) {
        if (s(field_get_name(f)) === fieldName) {
            var off = field_get_offset(f);
            fieldCache[key] = off;
            return off;
        }
    }
    fieldCache[key] = -1;
    return -1;
}

// --- Resolve all needed class/field offsets ---
var runnerClass = findClass("BattleLogicAssembly.dll", "IdunBattle.Runner", "IdunRunner");
var runnerConfigOff = runnerClass ? getFieldOffset(runnerClass, "<Configuration>k__BackingField") : -1;

var battleConfigClass = findClass("BattleLogicAssembly.dll", "IdunBattle.Configuration", "BattleConfiguration");
var bcUnitsOff = battleConfigClass ? getFieldOffset(battleConfigClass, "Units") : -1;

var unitConfigClass = findClass("BattleLogicAssembly.dll", "IdunBattle.Configuration", "UnitConfiguration");
var ucIdOff = unitConfigClass ? getFieldOffset(unitConfigClass, "Id") : -1;
var ucFactionOff = unitConfigClass ? getFieldOffset(unitConfigClass, "Faction") : -1;

var moveMsg = findClass("BattleLogicAssembly.dll", "IdunBattle.Messages", "MoveUnitMessage");
var moveUnitId = moveMsg ? getFieldOffset(moveMsg, "UnitId") : -1;

var abilityMsg = findClass("BattleLogicAssembly.dll", "IdunBattle.Messages", "ActiveAbilityMessage");
var abCasterId = abilityMsg ? getFieldOffset(abilityMsg, "CasterId") : -1;
var abTargetId = abilityMsg ? getFieldOffset(abilityMsg, "TargetId") : -1;
var abType = abilityMsg ? getFieldOffset(abilityMsg, "ActiveAbilityType") : -1;

send({t: "offsets", runner_config: runnerConfigOff, bc_units: bcUnitsOff, uc_id: ucIdOff, uc_faction: ucFactionOff});

// --- Registries ---
var unitNames = {};      // entityId (int) -> {id, faction}
var configDumped = false;

// Read a List<T> — IL2CPP List has: [klass, monitor, _items (array ptr), _size (int)]
// _items is at offset 0x10, _size is at offset 0x18
// The array itself: [klass, monitor, max_length (at 0x18), then elements starting at 0x20]
function readList(listPtr) {
    if (listPtr.isNull()) return [];
    var items = listPtr.add(0x10).readPointer();
    var size = listPtr.add(0x18).readS32();
    if (items.isNull() || size <= 0 || size > 1000) return [];
    var result = [];
    for (var i = 0; i < size; i++) {
        var elem = items.add(0x20 + i * Process.pointerSize).readPointer();
        result.push(elem);
    }
    return result;
}

function dumpBattleConfig(runnerThis) {
    if (configDumped) return;
    try {
        if (runnerConfigOff < 0 || bcUnitsOff < 0 || ucIdOff < 0) {
            send({t: "error", msg: "missing offsets"});
            return;
        }
        var config = runnerThis.add(runnerConfigOff).readPointer();
        if (config.isNull()) { send({t: "error", msg: "config is null"}); return; }

        var unitsList = config.add(bcUnitsOff).readPointer();
        if (unitsList.isNull()) { send({t: "error", msg: "units list is null"}); return; }

        var units = readList(unitsList);
        send({t: "info", msg: "Found " + units.length + " units in BattleConfiguration"});

        for (var i = 0; i < units.length; i++) {
            var uc = units[i];
            if (uc.isNull()) continue;
            var id = readIl2cppString(uc.add(ucIdOff).readPointer());
            var faction = ucFactionOff >= 0 ? readIl2cppString(uc.add(ucFactionOff).readPointer()) : null;
            if (id) {
                // The entityId for units is assigned sequentially starting from some base.
                // We'll map them when we see AddUnitMessage.
                send({t: "unit_config", index: i, id: id, faction: faction});
            }
        }
        configDumped = true;
    } catch(e) {
        send({t: "error", msg: "dumpBattleConfig: " + e.message});
    }
}

// We also need to map entityId -> configId. We do this by hooking AddUnitMessage
// through IdunRunner.Apply. When we see AddUnitMessage, we read its UnitId field
// (which is a BEntityId). We also need the configId — but AddUnitMessage doesn't have it.
// So we correlate: the order of AddUnitMessage matches the order in BattleConfiguration.Units.
var unitConfigList = [];  // populated from dumpBattleConfig
var addUnitIndex = 0;

function dumpBattleConfigWithMapping(runnerThis) {
    if (configDumped) return;
    try {
        if (runnerConfigOff < 0 || bcUnitsOff < 0 || ucIdOff < 0) return;
        var config = runnerThis.add(runnerConfigOff).readPointer();
        if (config.isNull()) return;
        var unitsList = config.add(bcUnitsOff).readPointer();
        if (unitsList.isNull()) return;
        var units = readList(unitsList);
        for (var i = 0; i < units.length; i++) {
            var uc = units[i];
            if (uc.isNull()) continue;
            var id = readIl2cppString(uc.add(ucIdOff).readPointer());
            var faction = ucFactionOff >= 0 ? readIl2cppString(uc.add(ucFactionOff).readPointer()) : null;
            unitConfigList.push({id: id, faction: faction});
        }
        send({t: "info", msg: "Loaded " + unitConfigList.length + " unit configs"});
        configDumped = true;
    } catch(e) {
        send({t: "error", msg: "dumpBattleConfig: " + e.message});
    }
}

function resolveUnit(entityId) {
    var u = unitNames[entityId];
    return u ? u.id : ("unit_" + entityId);
}

function readMsgDetails(msg, runnerThis) {
    var cls = "?";
    try { cls = s(class_get_name(msg.readPointer())); } catch(e) {}
    var d = { msg: cls };
    try {
        if (cls === "AddUnitMessage") {
            var uid = msg.add(moveUnitId).readS32(); // UnitId is at same offset (16) in AddUnitMessage
            // Map entityId to config by order
            if (addUnitIndex < unitConfigList.length) {
                var cfg = unitConfigList[addUnitIndex];
                unitNames[uid] = cfg;
                d.entityId = uid;
                d.unit = cfg.id;
                d.faction = cfg.faction;
                send({t: "unit_mapped", entityId: uid, unit: cfg.id, faction: cfg.faction});
            } else {
                d.entityId = uid;
                d.unit = "unknown_" + uid;
            }
            addUnitIndex++;
        } else if (cls === "MoveUnitMessage" && moveUnitId >= 0) {
            var uid = msg.add(moveUnitId).readS32();
            d.unitId = uid;
            d.unit = resolveUnit(uid);
        } else if (cls === "ActiveAbilityMessage" && abCasterId >= 0) {
            var cid = msg.add(abCasterId).readS32();
            var tid = msg.add(abTargetId).readS32();
            var atype = msg.add(abType).readS32();
            d.casterId = cid;
            d.caster = resolveUnit(cid);
            d.targetId = tid;
            d.target = resolveUnit(tid);
            d.abilityType = atype;
        } else if (cls === "AiContainerMessage" || cls === "ExternalPlayerMessage") {
            var inner = msg.add(16).readPointer();
            if (!inner.isNull()) d.inner = readMsgDetails(inner, runnerThis);
        }
    } catch(e) {}
    return d;
}

// === HOOK: IdunRunner.Apply ===
hook("BattleLogicAssembly.dll", "IdunBattle.Runner", "IdunRunner", "Apply", {
    onEnter: function(args) {
        try {
            // First call: dump the battle config to get unit names
            dumpBattleConfigWithMapping(args[0]);
            var d = readMsgDetails(args[1], args[0]);
            send({t: "action", detail: d});
        } catch(e) {}
    }
});

// === HOOK: AiControl.RunComputerActionsForPlayer ===
var lastAiLog = 0;
hook("BattleLogicAssembly.dll", "IdunBattle.Core.Services", "AiControl", "RunComputerActionsForPlayer", {
    onEnter: function(args) {
        var now = Date.now();
        if (now - lastAiLog < 2000) return;
        lastAiLog = now;
        send({t: "ai_turn"});
    }
});

// === HOOK: AiControl.ApplyAiMessage ===
hook("BattleLogicAssembly.dll", "IdunBattle.Core.Services", "AiControl", "ApplyAiMessage", {
    onEnter: function(args) {
        try {
            send({t: "ai_action", detail: readMsgDetails(args[1], null)});
        } catch(e) {}
    }
});
