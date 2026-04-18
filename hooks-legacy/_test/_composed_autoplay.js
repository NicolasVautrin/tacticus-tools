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
var field_get_name = new NativeFunction(il2cpp.findExportByName("il2cpp_field_get_name"), "pointer", ["pointer"]);
var field_get_offset = new NativeFunction(il2cpp.findExportByName("il2cpp_field_get_offset"), "int32", ["pointer"]);

var fieldOffsetCache = {};
function getFieldOffset(klass, fieldName) {
    var key = klass.toString() + "." + fieldName;
    if (fieldOffsetCache[key] !== undefined) return fieldOffsetCache[key];
    var it = Memory.alloc(Process.pointerSize); it.writePointer(ptr(0));
    var f;
    while (!(f = class_get_fields(klass, it)).isNull()) {
        if (s(field_get_name(f)) === fieldName) {
            var off = field_get_offset(f);
            fieldOffsetCache[key] = off;
            return off;
        }
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
    var d = { msg: cls };
    try {
        if (cls === "MoveUnitMessage") {
            d.unitId = msg.add(0x10).readS32();
        } else if (cls === "ActiveAbilityMessage") {
            d.casterId = msg.add(0x10).readS32();
            d.targetId = msg.add(0x14).readS32();
            d.abilityType = msg.add(0x18).readS32();
        } else if (cls === "AiContainerMessage" || cls === "ExternalPlayerMessage") {
            var inner = msg.add(0x10).readPointer();
            if (!inner.isNull()) {
                d.inner = readMsgDetails(inner);
            }
        }
    } catch (e) {}
    return d;
}

console.log("[*] IL2CPP helpers loaded");
// util: IL2CPP Serializer — generic runtime object -> JSON serializer
// requires: _utils/il2cpp-helpers (for s(), findClass, il2cpp module)
// provides: serialize(objPtr, maxDepth) -> plain JS object

// --- Additional IL2CPP API for type introspection ---
var field_get_type = new NativeFunction(il2cpp.findExportByName("il2cpp_field_get_type"), "pointer", ["pointer"]);
var type_get_type = new NativeFunction(il2cpp.findExportByName("il2cpp_type_get_type"), "int32", ["pointer"]);
var type_get_name = new NativeFunction(il2cpp.findExportByName("il2cpp_type_get_name"), "pointer", ["pointer"]);
var class_from_type = new NativeFunction(il2cpp.findExportByName("il2cpp_class_from_type"), "pointer", ["pointer"]);
var class_is_enum = new NativeFunction(il2cpp.findExportByName("il2cpp_class_is_enum"), "int32", ["pointer"]);
var class_is_valuetype = new NativeFunction(il2cpp.findExportByName("il2cpp_class_is_valuetype"), "int32", ["pointer"]);
var class_get_parent = new NativeFunction(il2cpp.findExportByName("il2cpp_class_get_parent"), "pointer", ["pointer"]);
var class_get_element_class = new NativeFunction(il2cpp.findExportByName("il2cpp_class_get_element_class"), "pointer", ["pointer"]);
var class_instance_size = new NativeFunction(il2cpp.findExportByName("il2cpp_class_instance_size"), "uint32", ["pointer"]);

// IL2CPP type enum values
var TYPE_BOOLEAN = 2;
var TYPE_CHAR = 3;
var TYPE_I1 = 4;
var TYPE_U1 = 5;
var TYPE_I2 = 6;
var TYPE_U2 = 7;
var TYPE_I4 = 8;
var TYPE_U4 = 9;
var TYPE_I8 = 10;
var TYPE_U8 = 11;
var TYPE_R4 = 12;
var TYPE_R8 = 13;
var TYPE_STRING = 14;
var TYPE_PTR = 15;
var TYPE_VALUETYPE = 17;
var TYPE_CLASS = 18;
var TYPE_ARRAY = 20;
var TYPE_GENERICINST = 21;
var TYPE_I = 24;    // IntPtr
var TYPE_U = 25;    // UIntPtr
var TYPE_OBJECT = 28;
var TYPE_SZARRAY = 0x45;

// --- Circular reference guard ---
var _visiting = {};
var _visitId = 0;

// --- Skip fields that cause problems or are not useful ---
var SKIP_FIELDS = {
    "EntityTypeMapping": true,  // static dictionary, huge
    "_feetEnumerator": true,    // enumerator state, not useful
    "_caches": true,
    "_cacheInvalidator": true,
};

// --- Read a primitive value at a given address based on IL2CPP type ---
function readPrimitive(addr, typeEnum) {
    switch (typeEnum) {
        case TYPE_BOOLEAN: return addr.readU8() !== 0;
        case TYPE_CHAR:    return addr.readU16();
        case TYPE_I1:      return addr.readS8();
        case TYPE_U1:      return addr.readU8();
        case TYPE_I2:      return addr.readS16();
        case TYPE_U2:      return addr.readU16();
        case TYPE_I4:      return addr.readS32();
        case TYPE_U4:      return addr.readU32();
        case TYPE_I8:      return addr.readS64();
        case TYPE_U8:      return addr.readU64();
        case TYPE_R4:      return addr.readFloat();
        case TYPE_R8:      return addr.readDouble();
        default:           return null;
    }
}

// --- Read an IL2CPP array (szarray) ---
function readSzArray(arrPtr, depth) {
    if (arrPtr.isNull()) return null;
    try {
        var len = arrPtr.add(0x18).readS32();
        if (len <= 0 || len > 500) return { _array: true, length: len };
        // Get element class from array klass
        var arrKlass = arrPtr.readPointer();
        var elemKlass = class_get_element_class(arrKlass);
        var isValueType = class_is_valuetype(elemKlass) !== 0;
        var elemSize = isValueType ? class_instance_size(elemKlass) - (2 * Process.pointerSize) : Process.pointerSize;
        // Simple heuristic: if element is a reference type, read pointers
        var result = [];
        for (var i = 0; i < Math.min(len, 100); i++) {
            var elemAddr = arrPtr.add(0x20 + i * (isValueType ? elemSize : Process.pointerSize));
            if (isValueType) {
                // For value types in arrays, try reading as int
                result.push(elemAddr.readS32());
            } else {
                var elem = elemAddr.readPointer();
                if (elem.isNull()) {
                    result.push(null);
                } else {
                    result.push(serialize(elem, depth - 1));
                }
            }
        }
        if (len > 100) result.push("... (" + len + " total)");
        return result;
    } catch(e) {
        return { _error: "array read: " + e.message };
    }
}

// --- Read a List<T> ---
function readList(listPtr, depth) {
    if (listPtr.isNull()) return null;
    try {
        var items = listPtr.add(0x10).readPointer();
        var size = listPtr.add(0x18).readS32();
        if (items.isNull() || size < 0) return { _list: true, size: size };
        if (size === 0) return [];
        if (size > 500) return { _list: true, size: size, _truncated: true };
        // Read the underlying array
        var arrKlass = items.readPointer();
        var elemKlass = class_get_element_class(arrKlass);
        var isValueType = class_is_valuetype(elemKlass) !== 0;
        var result = [];
        for (var i = 0; i < Math.min(size, 100); i++) {
            if (isValueType) {
                var elemSize = class_instance_size(elemKlass) - (2 * Process.pointerSize);
                var elemAddr = items.add(0x20 + i * elemSize);
                result.push(elemAddr.readS32());
            } else {
                var elem = items.add(0x20 + i * Process.pointerSize).readPointer();
                if (elem.isNull()) {
                    result.push(null);
                } else {
                    result.push(serialize(elem, depth - 1));
                }
            }
        }
        if (size > 100) result.push("... (" + size + " total)");
        return result;
    } catch(e) {
        return { _error: "list read: " + e.message };
    }
}

// --- Read a Dictionary<K,V> — keys only for now ---
function readDictKeys(dictPtr, depth) {
    if (dictPtr.isNull()) return null;
    try {
        var count = dictPtr.add(0x20).readS32();
        if (count <= 0) return { _dict: true, count: count };
        if (count > 200) return { _dict: true, count: count, _truncated: true };
        // _entries is at 0x18
        var entries = dictPtr.add(0x18).readPointer();
        if (entries.isNull()) return { _dict: true, count: count, entries: "null" };
        // Each entry: hashCode(4) + next(4) + key(ptrSize) + value(ptrSize) = variable
        // But this depends on TKey/TValue being ref or value types. Skip deep parsing.
        return { _dict: true, count: count };
    } catch(e) {
        return { _error: "dict read: " + e.message };
    }
}

// --- Read a valuetype (struct or enum) at an inline address ---
function readValueType(addr, klass, depth) {
    // Check if it's an enum
    if (class_is_enum(klass) !== 0) {
        // Enums are backed by an integer
        return addr.readS32();
    }
    // For Nullable<T>, check hasValue
    var className = s(class_get_name(klass));
    if (className.indexOf("Nullable") === 0) {
        // Nullable<T> has: T value at offset 0, bool hasValue after T
        // But layout varies. Try: if first 4 bytes look like a value and next byte is 0/1
        try {
            // Simple heuristic: just return the int value or null
            return addr.readS32();
        } catch(e) { return null; }
    }
    // Generic struct: enumerate fields
    if (depth <= 0) return { _struct: className };
    var result = { _type: className };
    var it = Memory.alloc(Process.pointerSize); it.writePointer(ptr(0));
    var f;
    while (!(f = class_get_fields(klass, it)).isNull()) {
        var fname = s(field_get_name(f));
        var foff = field_get_offset(f);
        var ftype = field_get_type(f);
        var ftypeEnum = type_get_type(ftype);
        try {
            // For inline structs, offset is relative to the struct start, minus the object header
            // But for fields on a valuetype, offsets already include the header. Subtract it:
            var fieldAddr = addr.add(foff - (2 * Process.pointerSize));
            result[fname] = readFieldValue(fieldAddr, ftypeEnum, ftype, depth - 1);
        } catch(e) {
            result[fname] = { _error: e.message };
        }
    }
    return result;
}

// --- Read a single field value ---
function readFieldValue(addr, typeEnum, il2cppType, depth) {
    // Primitives
    if (typeEnum >= TYPE_BOOLEAN && typeEnum <= TYPE_R8) {
        return readPrimitive(addr, typeEnum);
    }
    // String
    if (typeEnum === TYPE_STRING) {
        var strPtr = addr.readPointer();
        if (strPtr.isNull()) return null;
        return readIl2cppString(strPtr);
    }
    // Value type (struct or enum)
    if (typeEnum === TYPE_VALUETYPE) {
        var vtKlass = class_from_type(il2cppType);
        return readValueType(addr, vtKlass, depth);
    }
    // Class / object reference
    if (typeEnum === TYPE_CLASS || typeEnum === TYPE_OBJECT) {
        var objPtr = addr.readPointer();
        if (objPtr.isNull()) return null;
        if (depth <= 0) {
            try { return { _ref: s(class_get_name(objPtr.readPointer())) }; } catch(e) { return { _ref: "?" }; }
        }
        return serialize(objPtr, depth - 1);
    }
    // Generic instance (List<T>, Dictionary<K,V>, etc.)
    if (typeEnum === TYPE_GENERICINST) {
        var objPtr = addr.readPointer();
        if (objPtr.isNull()) return null;
        // Detect List vs Dict by class name
        try {
            var objKlass = objPtr.readPointer();
            var objClassName = s(class_get_name(objKlass));
            if (objClassName === "List`1") {
                return readList(objPtr, depth);
            } else if (objClassName === "Dictionary`2") {
                return readDictKeys(objPtr, depth);
            } else if (objClassName.indexOf("OrderedSet") >= 0 || objClassName.indexOf("Set") >= 0) {
                return { _type: objClassName };
            }
            // Other generic: try serialize
            if (depth <= 0) return { _ref: objClassName };
            return serialize(objPtr, depth - 1);
        } catch(e) {
            return { _error: "generic: " + e.message };
        }
    }
    // SZArray (T[])
    if (typeEnum === TYPE_SZARRAY) {
        var arrPtr = addr.readPointer();
        if (arrPtr.isNull()) return null;
        return readSzArray(arrPtr, depth);
    }
    // IntPtr / UIntPtr
    if (typeEnum === TYPE_I || typeEnum === TYPE_U) {
        return addr.readPointer().toString();
    }
    // Fallback
    return { _unknownType: typeEnum };
}

// --- Main serialize function ---
function serialize(objPtr, maxDepth) {
    if (maxDepth === undefined) maxDepth = 3;
    if (objPtr.isNull()) return null;
    if (maxDepth <= 0) {
        try { return { _ref: s(class_get_name(objPtr.readPointer())) }; } catch(e) { return { _ref: "?" }; }
    }

    // Circular reference check
    var ptrKey = objPtr.toString();
    if (_visiting[ptrKey]) return { _circular: true };
    _visiting[ptrKey] = true;

    var result = {};
    try {
        var klass = objPtr.readPointer();
        var className = s(class_get_name(klass));
        var namespace = s(class_get_namespace(klass));
        result._class = className;

        // Special case: string
        if (className === "String") {
            delete _visiting[ptrKey];
            return readIl2cppString(objPtr);
        }

        // Walk the class hierarchy (current + parents)
        var current = klass;
        while (!current.isNull()) {
            var parentName = s(class_get_name(current));
            if (parentName === "Object" || parentName === "ValueType") break;

            var it = Memory.alloc(Process.pointerSize); it.writePointer(ptr(0));
            var f;
            while (!(f = class_get_fields(current, it)).isNull()) {
                var fname = s(field_get_name(f));
                // Clean up backing field names
                var displayName = fname.replace(/<(.+)>k__BackingField/, "$1");
                if (SKIP_FIELDS[fname] || SKIP_FIELDS[displayName]) continue;

                var foff = field_get_offset(f);
                if (foff <= 0) continue; // skip static fields (offset 0 or negative in some builds)

                var ftype = field_get_type(f);
                var ftypeEnum = type_get_type(ftype);

                try {
                    var fieldAddr = objPtr.add(foff);
                    result[displayName] = readFieldValue(fieldAddr, ftypeEnum, ftype, maxDepth - 1);
                } catch(e) {
                    result[displayName] = { _error: e.message };
                }
            }

            current = class_get_parent(current);
        }
    } catch(e) {
        result._error = e.message;
    }

    delete _visiting[ptrKey];
    return result;
}

console.log("[*] IL2CPP serializer loaded");
// hook: Auto-play — analyze game state, send options to Claude, receive commands, inject actions
// requires: _utils/il2cpp-helpers, _utils/il2cpp-serializer
// provides: recv("action") handler + turn analysis via game APIs
//
// Flow:
//   1. Hook IdunRunner.Apply to capture runner instance
//   2. When it's player turn, query game APIs (reachable tiles, valid targets, damage predictions)
//   3. send({t: "your_turn", ...}) with all options pre-computed
//   4. recv("action") to receive Claude's decision and inject it
//
// Commands (via POST /api/scripts/{id}/message):
//   {type: "action", payload: {action: "end_turn"}}
//   {type: "action", payload: {action: "ability", casterId: 90, targetId: 79, abilityType: 1123}}

// --- IL2CPP APIs ---
var il2cpp_object_new = new NativeFunction(
    il2cpp.findExportByName("il2cpp_object_new"), "pointer", ["pointer"]);
var il2cpp_runtime_invoke = new NativeFunction(
    il2cpp.findExportByName("il2cpp_runtime_invoke"), "pointer",
    ["pointer", "pointer", "pointer", "pointer"]);

// --- Message classes ---
var endTurnClass = findClass("BattleLogicAssembly.dll", "IdunBattle.Messages", "EndTurnMessage");
var abilityMsgClass = findClass("BattleLogicAssembly.dll", "IdunBattle.Messages", "ActiveAbilityMessage");

// --- Field offsets ---
var abCasterOff = abilityMsgClass ? getFieldOffset(abilityMsgClass, "CasterId") : -1;
var abTargetOff = abilityMsgClass ? getFieldOffset(abilityMsgClass, "TargetId") : -1;
var abTypeOff = abilityMsgClass ? getFieldOffset(abilityMsgClass, "ActiveAbilityType") : -1;
var abSkipFlagsOff = abilityMsgClass ? getFieldOffset(abilityMsgClass, "SkipFlags") : -1;

// --- Runner + services ---
var runnerClass = findClass("BattleLogicAssembly.dll", "IdunBattle.Runner", "IdunRunner");
var applyInfo = findMethod(runnerClass, "Apply");
// IL2CPP method signature on ARM64: fn(this, arg1, ..., MethodInfo*)
// Try both calling conventions
var applyFnWithMethodInfo = new NativeFunction(applyInfo.ptr, "void", ["pointer", "pointer", "pointer"]);
var applyFnSimple = new NativeFunction(applyInfo.ptr, "void", ["pointer", "pointer"]);

function callApply(runner, message) {
    // Try with MethodInfo* as last arg first (IL2CPP convention)
    try {
        applyFnWithMethodInfo(runner, message, applyInfo.info);
        return;
    } catch(e) {
        send({t: "debug", step: "applyFnWithMethodInfo failed", error: e.message});
    }
    // Fallback: try runtime_invoke
    invokeMethod(applyInfo.info, runner, [message]);
}

var runnerStateOff = getFieldOffset(runnerClass, "_state");
var runnerConfigOff = getFieldOffset(runnerClass, "<Configuration>k__BackingField");
var runnerBattleQueryOff = getFieldOffset(runnerClass, "<BattleQuery>k__BackingField");
var runnerDamagePredOff = getFieldOffset(runnerClass, "<DamagePrediction>k__BackingField");
var runnerPathfindersOff = getFieldOffset(runnerClass, "<Pathfinders>k__BackingField");
var runnerTargetingOff = getFieldOffset(runnerClass, "<TargetingQuery>k__BackingField");

// --- MatchState ---
var matchStateClass = findClass("BattleLogicAssembly.dll", "IdunBattle.Core", "MatchState");
var msEntitiesOff = getFieldOffset(matchStateClass, "_entities");

// --- Entity ---
var entityClass = findClass("BattleLogicAssembly.dll", "IdunBattle.Core", "Entity");
var entityIdOff = getFieldOffset(entityClass, "<Id>k__BackingField");
var entityTypeOff = getFieldOffset(entityClass, "<Type>k__BackingField");
var entityComponentsOff = getFieldOffset(entityClass, "Components");

// --- BaseUnitComponent ---
var bucClass = findClass("BattleLogicAssembly.dll", "IdunBattle.Entities.Components", "BaseUnitComponent");
var bucIdOff = getFieldOffset(bucClass, "Id");
var bucFactionOff = getFieldOffset(bucClass, "Faction");

// --- HealthComponent (fields inherited from FillUpStatComponent) ---
var fillUpClass = findClass("BattleLogicAssembly.dll", "IdunBattle.Entities.Components", "FillUpStatComponent");
var healthRemainingOff = fillUpClass ? getFieldOffset(fillUpClass, "RemainingValue") : -1;
var healthMaxOff = fillUpClass ? getFieldOffset(fillUpClass, "MaximumValue") : -1;

// --- ActiveAbilityComponent ---
var aaCompClass = findClass("BattleLogicAssembly.dll", "IdunBattle.Entities.Components", "ActiveAbilityComponent");
var aaNormalAttackOff = aaCompClass ? getFieldOffset(aaCompClass, "NormalAttackType") : -1;

// --- OwnerComponent ---
var ownerCompClass = findClass("BattleLogicAssembly.dll", "IdunBattle.Entities.Components", "OwnerComponent");
var ownerPlayerOff = ownerCompClass ? getFieldOffset(ownerCompClass, "PlayerEntityId") : -1;

// --- PlayerComponent ---
var playerCompClass = findClass("BattleLogicAssembly.dll", "IdunBattle.Entities.Components", "PlayerComponent");
var playerTypeOff = playerCompClass ? getFieldOffset(playerCompClass, "Type") : -1;
var playerUnitIdsOff = playerCompClass ? getFieldOffset(playerCompClass, "UnitIds") : -1;

// --- TurnComponent (on MatchEntity) ---
var turnCompClass = findClass("BattleLogicAssembly.dll", "IdunBattle.Entities.Components", "TurnComponent");
var turnCurrentPlayerOff = turnCompClass ? getFieldOffset(turnCompClass, "_currentPlayerId") : -1;

// --- Runner instance + pending actions ---
var runnerInstance = null;
var pendingActions = [];  // actions to execute on the next Apply call (main thread)

// --- List reading helper ---
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

function readListInts(listPtr) {
    if (listPtr.isNull()) return [];
    var items = listPtr.add(0x10).readPointer();
    var size = listPtr.add(0x18).readS32();
    if (items.isNull() || size <= 0 || size > 5000) return [];
    var result = [];
    for (var i = 0; i < size; i++) {
        result.push(items.add(0x20 + i * 4).readS32());
    }
    return result;
}

// --- Read component from entity by class name ---
function readComponent(entity, compClassName) {
    var componentsArr = entity.add(entityComponentsOff).readPointer();
    if (componentsArr.isNull()) return null;
    var arrLen = componentsArr.add(0x18).readS32();
    for (var j = 0; j < Math.min(arrLen, 50); j++) {
        var comp = componentsArr.add(0x20 + j * Process.pointerSize).readPointer();
        if (comp.isNull()) continue;
        try {
            if (s(class_get_name(comp.readPointer())) === compClassName) return comp;
        } catch(e) {}
    }
    return null;
}

// --- Build turn summary for Claude ---
function buildTurnSummary() {
    if (!runnerInstance) return null;

    try {
        var state = runnerInstance.add(runnerStateOff).readPointer();
        var entities = readListPtrs(state.add(msEntitiesOff).readPointer());

        // Find current player ID from MatchEntity's TurnComponent
        var currentPlayerId = -1;
        var humanPlayerEntityId = -1;
        var units = [];
        var unitEntities = {}; // entityId -> entity pointer

        for (var i = 0; i < entities.length; i++) {
            var e = entities[i];
            if (e.isNull()) continue;
            var eid = e.add(entityIdOff).readS32();
            var etype = e.add(entityTypeOff).readS32();

            // Match entity (type 2) — get current player turn
            if (etype === 2) {
                var turnComp = readComponent(e, "TurnComponent");
                if (turnComp && turnCurrentPlayerOff >= 0) {
                    currentPlayerId = turnComp.add(turnCurrentPlayerOff).readS32();
                }
            }

            // Player entity (type 4) — find human player
            if (etype === 4) {
                var playerComp = readComponent(e, "PlayerComponent");
                if (playerComp && playerTypeOff >= 0) {
                    var playerType = playerComp.add(playerTypeOff).readS32();
                    if (playerType === 0) { // 0 = human player
                        humanPlayerEntityId = eid;
                    }
                }
            }

            // Unit entity (type 1) — collect all units
            if (etype === 1) {
                unitEntities[eid] = e;
                var unitComp = readComponent(e, "UnitComponent");
                var ownerComp = readComponent(e, "OwnerComponent");
                var healthComp = readComponent(e, "HealthComponent");
                var aaComp = readComponent(e, "ActiveAbilityComponent");

                var unitInfo = {entityId: eid};

                if (unitComp && bucIdOff >= 0) {
                    try { unitInfo.name = readIl2cppString(unitComp.add(bucIdOff).readPointer()); } catch(ex) {}
                    try { unitInfo.faction = readIl2cppString(unitComp.add(bucFactionOff).readPointer()); } catch(ex) {}
                }
                if (ownerComp && ownerPlayerOff >= 0) {
                    unitInfo.owner = ownerComp.add(ownerPlayerOff).readS32();
                }
                if (healthComp) {
                    if (healthRemainingOff >= 0) unitInfo.hp = healthComp.add(healthRemainingOff).readS32();
                    if (healthMaxOff >= 0) unitInfo.maxHp = healthComp.add(healthMaxOff).readS32();
                }
                if (aaComp && aaNormalAttackOff >= 0) {
                    unitInfo.normalAttack = aaComp.add(aaNormalAttackOff).readS32();
                }
                unitInfo.alive = (unitInfo.hp || 0) > 0;

                units.push(unitInfo);
            }
        }

        // Separate player units vs enemy units
        var playerUnits = [];
        var enemyUnits = [];
        for (var u = 0; u < units.length; u++) {
            if (units[u].owner === humanPlayerEntityId) {
                playerUnits.push(units[u]);
            } else {
                enemyUnits.push(units[u]);
            }
        }

        return {
            currentPlayerId: currentPlayerId,
            humanPlayerEntityId: humanPlayerEntityId,
            isPlayerTurn: currentPlayerId === humanPlayerEntityId,
            playerUnits: playerUnits,
            enemyUnits: enemyUnits
        };
    } catch(e) {
        return {error: e.message};
    }
}

// --- Message creation ---

// --- Helper: invoke IL2CPP method via runtime_invoke ---
function invokeMethod(methodInfo, obj, args) {
    // il2cpp_runtime_invoke(MethodInfo* method, void* obj, void** params, Il2CppException** exc)
    // For reference type args: params[i] is the pointer to the object directly (NOT pointer-to-pointer)
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
        // Try to read exception message
        var excMsg = "IL2CPP exception";
        try {
            var excClass = s(class_get_name(excVal.readPointer()));
            excMsg += " (" + excClass + ")";
        } catch(e) {}
        throw new Error(excMsg);
    }
    return result;
}

function createEndTurnMessage() {
    var msg = il2cpp_object_new(endTurnClass);
    if (msg.isNull()) throw new Error("il2cpp_object_new returned null for EndTurnMessage");
    // Call .ctor() via runtime_invoke
    var ctor = findMethod(endTurnClass, ".ctor");
    if (ctor) {
        invokeMethod(ctor.info, msg, null);
    }
    return msg;
}

function createAbilityMessage(casterId, targetId, abilityType) {
    var msg = il2cpp_object_new(abilityMsgClass);
    if (msg.isNull()) throw new Error("il2cpp_object_new returned null for ActiveAbilityMessage");
    // Call parameterless .ctor first to initialize
    var ctor = findMethod(abilityMsgClass, ".ctor");
    if (ctor) {
        invokeMethod(ctor.info, msg, null);
    }
    // Then set fields
    msg.add(abCasterOff).writeS32(casterId);
    msg.add(abTargetOff).writeS32(targetId);
    msg.add(abTypeOff).writeS32(abilityType);
    msg.add(abSkipFlagsOff).writeU8(0);
    return msg;
}

function createMessage(cmd) {
    if (cmd.action === "end_turn") {
        return createEndTurnMessage();
    }
    if (cmd.action === "ability") {
        return createAbilityMessage(cmd.casterId, cmd.targetId, cmd.abilityType);
    }
    throw new Error("Unknown action: " + cmd.action);
}

// --- Hook Apply to capture runner + execute pending actions + send turn summary ---
var lastTurnSent = 0;

hook("BattleLogicAssembly.dll", "IdunBattle.Runner", "IdunRunner", "Apply", {
    onEnter: function(args) {
        runnerInstance = args[0];
    },
    onLeave: function(retval) {
        // Execute any pending actions (we're on the main thread here)
        while (pendingActions.length > 0) {
            var cmd = pendingActions.shift();
            try {
                var message = createMessage(cmd);
                // Call Apply directly — we're on the correct thread
                var applyDirect = new NativeFunction(applyInfo.ptr, "void", ["pointer", "pointer", "pointer"]);
                applyDirect(runnerInstance, message, applyInfo.info);
                send({t: "played", cmd: cmd});
            } catch(e) {
                send({t: "error", msg: "play failed: " + e.message});
                break; // stop processing on error
            }
        }

        // After each action, check if it's now the player's turn and send summary
        var now = Date.now();
        if (now - lastTurnSent < 500) return; // debounce
        try {
            var summary = buildTurnSummary();
            if (summary && summary.isPlayerTurn) {
                lastTurnSent = now;
                send({t: "your_turn", state: summary});
            }
        } catch(e) {}
    }
});

// --- recv handler for commands ---
// Actions are queued and executed on the next Apply call (main thread)
recv("action", function onAction(msg) {
    if (!runnerInstance) {
        send({t: "error", msg: "No runner instance yet"});
        recv("action", onAction);
        return;
    }
    var cmd = msg.payload;
    pendingActions.push(cmd);
    send({t: "queued", cmd: cmd, pending: pendingActions.length});
    recv("action", onAction);
});

// --- recv handler for state query on demand ---
recv("query_state", function onQuery(msg) {
    try {
        var summary = buildTurnSummary();
        send({t: "state", state: summary});
    } catch(e) {
        send({t: "error", msg: "query failed: " + e.message});
    }
    recv("query_state", onQuery);
});

// --- Hook Update to process pending actions on main thread ---
hook("Assembly-CSharp.dll", "IdunBattle.View.Game", "IdunGameViews", "Update", {
    onEnter: function(args) {
        if (pendingActions.length === 0 || !runnerInstance) return;
        while (pendingActions.length > 0) {
            var cmd = pendingActions.shift();
            try {
                var message = createMessage(cmd);
                var applyDirect = new NativeFunction(applyInfo.ptr, "void", ["pointer", "pointer", "pointer"]);
                applyDirect(runnerInstance, message, applyInfo.info);
                send({t: "played", cmd: cmd});
            } catch(e) {
                send({t: "error", msg: "play failed: " + e.message});
                break;
            }
        }
    }
});

send({t: "autoplay_ready", msg: "Hooks installed. Play a turn to capture runner, then auto-play begins."});
