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

// --- Resolve message field offsets ---
var moveMsg = findClass("BattleLogicAssembly.dll", "IdunBattle.Messages", "MoveUnitMessage");
var moveUnitId = moveMsg ? getFieldOffset(moveMsg, "UnitId") : -1;

var abilityMsg = findClass("BattleLogicAssembly.dll", "IdunBattle.Messages", "ActiveAbilityMessage");
var abCasterId = abilityMsg ? getFieldOffset(abilityMsg, "CasterId") : -1;
var abTargetId = abilityMsg ? getFieldOffset(abilityMsg, "TargetId") : -1;
var abType = abilityMsg ? getFieldOffset(abilityMsg, "ActiveAbilityType") : -1;

// --- ActiveAbility field offset for enum value ---
var activeAbilityClass = findClass("BattleLogicAssembly.dll", "IdunBattle.Entities.Components", "ActiveAbility");
var abNameOff = activeAbilityClass ? getFieldOffset(activeAbilityClass, "AbilityName") : -1;

// --- Registries ---
var unitNames = {};      // entityId (int) -> configId (string)
var abilityNames = {};   // abilityType (int) -> name (string)

function resolveUnit(entityId) {
    return unitNames[entityId] || ("unit_" + entityId);
}

function resolveAbility(abilityTypeInt) {
    return abilityNames[abilityTypeInt] || ("ability_" + abilityTypeInt);
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
            d.ability = resolveAbility(atype);
        } else if (cls === "AiContainerMessage" || cls === "ExternalPlayerMessage") {
            var inner = msg.add(16).readPointer();
            if (!inner.isNull()) d.inner = readMsgDetails(inner);
        }
    } catch(e) {}
    return d;
}

// === HOOK: UnitFactory.Build — capture entityId -> configId mapping ===
hook("BattleLogicAssembly.dll", "IdunBattle.Entities.Factories", "UnitFactory", "Build", {
    onEnter: function(args) {
        try {
            // args[0] = this, args[1] = BEntityId (struct, int), args[2] = configId (IL2CPP string)
            var entityId = args[1].toInt32();
            var configId = readIl2cppString(args[2]);
            if (configId) {
                unitNames[entityId] = configId;
                send({t: "unit_registered", entityId: entityId, configId: configId});
            }
        } catch(e) {}
    }
});

// === HOOK: ActiveAbility.ToString — capture abilityType -> name mapping ===
hook("BattleLogicAssembly.dll", "IdunBattle.Entities.Components", "ActiveAbility", "ToString", {
    onEnter: function(args) {
        try {
            if (abNameOff >= 0) {
                this._abilityType = args[0].add(abNameOff).readS32();
            }
        } catch(e) {}
    },
    onLeave: function(retval) {
        try {
            var name = readIl2cppString(retval);
            if (name && this._abilityType !== undefined && !abilityNames[this._abilityType]) {
                abilityNames[this._abilityType] = name;
                send({t: "ability_registered", type: this._abilityType, name: name});
            }
        } catch(e) {}
    }
});

// === HOOK: IdunRunner.Apply — all actions ===
hook("BattleLogicAssembly.dll", "IdunBattle.Runner", "IdunRunner", "Apply", {
    onEnter: function(args) {
        try {
            send({t: "action", detail: readMsgDetails(args[1])});
        } catch(e) {}
    }
});

// === HOOK: AiControl.RunComputerActionsForPlayer — AI turn ===
var lastAiLog = 0;
hook("BattleLogicAssembly.dll", "IdunBattle.Core.Services", "AiControl", "RunComputerActionsForPlayer", {
    onEnter: function(args) {
        var now = Date.now();
        if (now - lastAiLog < 2000) return;
        lastAiLog = now;
        send({t: "ai_turn"});
    }
});

// === HOOK: AiControl.ApplyAiMessage — AI actions ===
hook("BattleLogicAssembly.dll", "IdunBattle.Core.Services", "AiControl", "ApplyAiMessage", {
    onEnter: function(args) {
        try {
            send({t: "ai_action", detail: readMsgDetails(args[1])});
        } catch(e) {}
    }
});
