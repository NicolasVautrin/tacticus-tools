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
var class_get_parent = new NativeFunction(il2cpp.findExportByName("il2cpp_class_get_parent"), "pointer", ["pointer"]);

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

// Dump all fields of a class (including parent classes)
function dumpAllFields(klass) {
    var fields = {};
    var current = klass;
    while (!current.isNull()) {
        var it = Memory.alloc(Process.pointerSize); it.writePointer(ptr(0));
        var f;
        while (!(f = class_get_fields(current, it)).isNull()) {
            fields[s(field_get_name(f))] = field_get_offset(f);
        }
        current = class_get_parent(current);
        // stop at System.Object
        if (!current.isNull() && s(class_get_name(current)) === "Object") break;
    }
    return fields;
}

// --- Resolve key offsets ---
var runnerClass = findClass("BattleLogicAssembly.dll", "IdunBattle.Runner", "IdunRunner");
var runnerStateOff = runnerClass ? getFieldOffset(runnerClass, "_state") : -1;

var matchStateClass = findClass("BattleLogicAssembly.dll", "IdunBattle.Core", "MatchState");
var msEntitiesOff = matchStateClass ? getFieldOffset(matchStateClass, "_entities") : -1;

var entityClass = findClass("BattleLogicAssembly.dll", "IdunBattle.Core", "Entity");
var entityIdOff = entityClass ? getFieldOffset(entityClass, "<Id>k__BackingField") : -1;
var entityTypeOff = entityClass ? getFieldOffset(entityClass, "<Type>k__BackingField") : -1;
var entityComponentsOff = entityClass ? getFieldOffset(entityClass, "Components") : -1;

send({t: "offsets", runner_state: runnerStateOff, ms_entities: msEntitiesOff,
      entity_id: entityIdOff, entity_type: entityTypeOff, entity_components: entityComponentsOff});

// --- Read a List<T> ---
function readListPtrs(listPtr) {
    if (listPtr.isNull()) return [];
    var items = listPtr.add(0x10).readPointer();
    var size = listPtr.add(0x18).readS32();
    if (items.isNull() || size <= 0 || size > 5000) return [];
    var result = [];
    for (var i = 0; i < size; i++) {
        result.push(items.add(0x20 + i * Process.pointerSize).readPointer());
    }
    return result;
}

// --- Read an IComponent[] (native array) ---
function readArray(arrPtr) {
    if (arrPtr.isNull()) return [];
    // IL2CPP array: [klass(8), monitor(8), max_length(8 on 64bit), elements...]
    var len = arrPtr.add(0x18).readS32();
    if (len <= 0 || len > 200) return [];
    var result = [];
    for (var i = 0; i < len; i++) {
        var elem = arrPtr.add(0x20 + i * Process.pointerSize).readPointer();
        result.push(elem);
    }
    return result;
}

// --- Read BaseUnitComponent fields from an entity's component ---
var baseUnitCompClass = findClass("BattleLogicAssembly.dll", "IdunBattle.Entities.Components", "BaseUnitComponent");
var bucIdOff = baseUnitCompClass ? getFieldOffset(baseUnitCompClass, "Id") : -1;
var bucFactionOff = baseUnitCompClass ? getFieldOffset(baseUnitCompClass, "Faction") : -1;

// --- Dump MatchState on demand ---
var stateDumped = false;
var unitNames = {};  // entityId -> {id, faction}

function dumpMatchState(runnerThis) {
    if (stateDumped) return;
    try {
        var state = runnerThis.add(runnerStateOff).readPointer();
        if (state.isNull()) { send({t: "error", msg: "state is null"}); return; }

        var entitiesList = state.add(msEntitiesOff).readPointer();
        if (entitiesList.isNull()) { send({t: "error", msg: "entities list is null"}); return; }

        var entities = readListPtrs(entitiesList);
        send({t: "info", msg: "MatchState has " + entities.length + " entities"});

        var unitCount = 0;
        for (var i = 0; i < entities.length; i++) {
            var entity = entities[i];
            if (entity.isNull()) continue;

            var eid = entity.add(entityIdOff).readS32();
            var etype = entity.add(entityTypeOff).readS32();

            // Read Components array
            var componentsArr = entity.add(entityComponentsOff).readPointer();
            if (componentsArr.isNull()) continue;

            var components = readArray(componentsArr);
            var compNames = [];
            var unitId = null;
            var unitFaction = null;

            for (var j = 0; j < components.length; j++) {
                var comp = components[j];
                if (comp.isNull()) continue;

                // Read component class name
                var compClassName = "?";
                try { compClassName = s(class_get_name(comp.readPointer())); } catch(e) {}
                compNames.push(compClassName);

                // If it's a BaseUnitComponent or subclass, read Id and Faction
                if (compClassName === "UnitComponent" || compClassName === "BaseUnitComponent") {
                    if (bucIdOff >= 0) {
                        try {
                            var idPtr = comp.add(bucIdOff).readPointer();
                            unitId = readIl2cppString(idPtr);
                        } catch(e) {}
                    }
                    if (bucFactionOff >= 0) {
                        try {
                            var fPtr = comp.add(bucFactionOff).readPointer();
                            unitFaction = readIl2cppString(fPtr);
                        } catch(e) {}
                    }
                }
            }

            if (unitId) {
                unitNames[eid] = {id: unitId, faction: unitFaction};
                unitCount++;
                send({t: "entity", entityId: eid, entityType: etype, unit: unitId,
                      faction: unitFaction, components: compNames});
            }
        }
        send({t: "info", msg: "Found " + unitCount + " units with names out of " + entities.length + " entities"});
        stateDumped = true;
    } catch(e) {
        send({t: "error", msg: "dumpMatchState: " + e.message});
    }
}

// --- Message reading with unit names ---
var moveMsg = findClass("BattleLogicAssembly.dll", "IdunBattle.Messages", "MoveUnitMessage");
var moveUnitId = moveMsg ? getFieldOffset(moveMsg, "UnitId") : -1;
var abilityMsg = findClass("BattleLogicAssembly.dll", "IdunBattle.Messages", "ActiveAbilityMessage");
var abCasterId = abilityMsg ? getFieldOffset(abilityMsg, "CasterId") : -1;
var abTargetId = abilityMsg ? getFieldOffset(abilityMsg, "TargetId") : -1;
var abType = abilityMsg ? getFieldOffset(abilityMsg, "ActiveAbilityType") : -1;

function resolveUnit(entityId) {
    var u = unitNames[entityId];
    return u ? u.id : ("unit_" + entityId);
}

function readMsgDetails(msg) {
    var cls = "?";
    try { cls = s(class_get_name(msg.readPointer())); } catch(e) {}
    var d = { msg: cls };
    try {
        if (cls === "MoveUnitMessage" && moveUnitId >= 0) {
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
            if (!inner.isNull()) d.inner = readMsgDetails(inner);
        }
    } catch(e) {}
    return d;
}

// === HOOKS ===

hook("BattleLogicAssembly.dll", "IdunBattle.Runner", "IdunRunner", "Apply", {
    onEnter: function(args) {
        try {
            dumpMatchState(args[0]);
            send({t: "action", detail: readMsgDetails(args[1])});
        } catch(e) {}
    }
});

var lastAiLog = 0;
hook("BattleLogicAssembly.dll", "IdunBattle.Core.Services", "AiControl", "RunComputerActionsForPlayer", {
    onEnter: function(args) {
        var now = Date.now();
        if (now - lastAiLog < 2000) return;
        lastAiLog = now;
        send({t: "ai_turn"});
    }
});

hook("BattleLogicAssembly.dll", "IdunBattle.Core.Services", "AiControl", "ApplyAiMessage", {
    onEnter: function(args) {
        try { send({t: "ai_action", detail: readMsgDetails(args[1])}); } catch(e) {}
    }
});
