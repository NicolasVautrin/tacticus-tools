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
// Hook UI tooltip parameter resolution — v2 with SAC serialization
// requires: _utils/il2cpp-helpers (findClass, findMethod, hook, readIl2cppString, s, class_get_methods, method_get_name, getFieldOffset)
//
// Compose:
//   cat hooks/_utils/il2cpp-helpers.js scripts/hook-ui-tooltips.js > composed.js

var _method_get_param_count = new NativeFunction(
    il2cpp.findExportByName("il2cpp_method_get_param_count"), "uint32", ["pointer"]);

// --- AbilityConfiguration layout (discovered via probe) ---
// Offset 0x10: Variables (Dictionary<AbilityVariableType, int[]>)
// Offset 0x18: Constants (Dictionary<AbilityConstantType, String>)
// Offset 0x20: AttackRangeType (Nullable<AttackRangeType>)

// --- Dictionary reading helper ---
// IL2CPP Dictionary<K,V> internal layout:
// Generic Dict: _buckets at some offset, _entries at some offset, _count
// We discover offsets dynamically

var _dictClass = findClass("mscorlib.dll", "System.Collections.Generic", "Dictionary`2");
var _dictCountOff = _dictClass ? getFieldOffset(_dictClass, "_count") : -1;
var _dictEntriesOff = _dictClass ? getFieldOffset(_dictClass, "_entries") : -1;

send({t: "dict_layout", countOff: _dictCountOff, entriesOff: _dictEntriesOff});

function readDictIntString(dictPtr) {
    // Reads Dictionary<int_enum, String> -> {intKey: stringValue}
    var result = {};
    if (!dictPtr || dictPtr.isNull()) return result;
    try {
        var count = dictPtr.add(_dictCountOff).readS32();
        var entriesArr = dictPtr.add(_dictEntriesOff).readPointer();
        if (entriesArr.isNull() || count <= 0 || count > 500) return result;
        // Entry struct for Dict<int, String>:
        // hashCode (4) + next (4) + key (4) + padding (4) + value (8 = pointer)
        // Total = 24 bytes per entry
        var dataStart = entriesArr.add(0x20); // array header
        for (var i = 0; i < count; i++) {
            var base = dataStart.add(i * 24);
            var hash = base.readS32();
            if (hash < 0) continue;
            var key = base.add(8).readS32();
            var valPtr = base.add(16).readPointer();
            var valStr = readIl2cppString(valPtr);
            if (valStr !== null) result[key] = valStr;
        }
    } catch(e) { result._error = e.message; }
    return result;
}

function readDictIntIntArr(dictPtr) {
    // Reads Dictionary<int_enum, int[]> -> {intKey: [int values]}
    var result = {};
    if (!dictPtr || dictPtr.isNull()) return result;
    try {
        var count = dictPtr.add(_dictCountOff).readS32();
        var entriesArr = dictPtr.add(_dictEntriesOff).readPointer();
        if (entriesArr.isNull() || count <= 0 || count > 500) return result;
        // Entry struct for Dict<int, int[]>:
        // hashCode (4) + next (4) + key (4) + padding (4) + value (8 = pointer to array)
        var dataStart = entriesArr.add(0x20);
        for (var i = 0; i < count; i++) {
            var base = dataStart.add(i * 24);
            var hash = base.readS32();
            if (hash < 0) continue;
            var key = base.add(8).readS32();
            var arrPtr = base.add(16).readPointer();
            if (arrPtr.isNull()) continue;
            // IL2CPP Array: header=0x10, then max_length (4 bytes at 0x18), data starts at 0x20
            var arrLen = arrPtr.add(0x18).readS32();
            var vals = [];
            for (var j = 0; j < Math.min(arrLen, 100); j++) {
                vals.push(arrPtr.add(0x20 + j * 4).readS32());
            }
            result[key] = vals;
        }
    } catch(e) { result._error = e.message; }
    return result;
}

function readAbilityConfig(sacPtr) {
    // Read Variables + Constants from a StatefulAbilityConfiguration (or AbilityConfiguration)
    // SAC inherits from AbilityConfig, so offsets are same for the base fields
    if (!sacPtr || sacPtr.isNull()) return null;
    try {
        var varsDict = sacPtr.add(0x10).readPointer();  // Variables at offset 0x10
        var constsDict = sacPtr.add(0x18).readPointer(); // Constants at offset 0x18
        var vars = readDictIntIntArr(varsDict);
        var consts = readDictIntString(constsDict);
        return {Variables: vars, Constants: consts};
    } catch(e) {
        return {error: e.message};
    }
}

// --- Context tracking ---
var _currentAbilityId = null;
var _currentUnitId = null;

// ==========================================
// 1. IdunLocalization.SetAbilityParameters — capture SAC config
// ==========================================
hook("Assembly-CSharp.dll", "idun.shared.utils", "IdunLocalization", "SetAbilityParameters", {
    onEnter: function(args) {
        // static: args[0]=Localize, args[1]=abilityId(String), args[2]=SAC, args[3]=unitId(String), args[4]=override(String)
        var abilityId = readIl2cppString(args[1]);
        var unitId = readIl2cppString(args[3]);
        _currentAbilityId = abilityId;
        _currentUnitId = unitId;

        // Read the SAC's config data directly
        var sacPtr = args[2];
        var config = readAbilityConfig(sacPtr);

        send({t: "ui_ability", abilityId: abilityId, unitId: unitId, config: config});
    }
});

// ==========================================
// 2. SetAbilityParameter overloads — individual param capture
// ==========================================
var _locaClass = findClass("Assembly-CSharp.dll", "idun.shared.utils", "IdunLocalization");
if (_locaClass) {
    var it = Memory.alloc(Process.pointerSize);
    it.writePointer(ptr(0));
    var m;
    var setParamMethods = [];
    while (!(m = class_get_methods(_locaClass, it)).isNull()) {
        if (s(method_get_name(m)) === "SetAbilityParameter") {
            setParamMethods.push({info: m, ptr: m.readPointer(), paramCount: _method_get_param_count(m)});
        }
    }
    for (var i = 0; i < setParamMethods.length; i++) {
        var mInfo = setParamMethods[i];
        if (mInfo.paramCount === 4) {
            try {
                Interceptor.attach(mInfo.ptr, {
                    onEnter: function(args) {
                        send({t: "ui_var", varType: args[1].toInt32(), value: args[2].toInt32(),
                              override: readIl2cppString(args[3]),
                              abilityId: _currentAbilityId, unitId: _currentUnitId});
                    }
                });
                console.log("[+] SetAbilityParameter (variable, 4p)");
            } catch(e) { console.log("[!] " + e.message); }
        } else if (mInfo.paramCount === 3) {
            try {
                Interceptor.attach(mInfo.ptr, {
                    onEnter: function(args) {
                        send({t: "ui_const", constType: args[1].toInt32(), value: readIl2cppString(args[2]),
                              abilityId: _currentAbilityId, unitId: _currentUnitId});
                    }
                });
                console.log("[+] SetAbilityParameter (constant, 3p)");
            } catch(e) { console.log("[!] " + e.message); }
        }
    }
}

// ==========================================
// 3. Entry point hooks (lightweight)
// ==========================================
hook("Assembly-CSharp.dll", "idun.Ui", "IdunUnitInfoBarHud", "HandleUnitEffectTapped", {
    onEnter: function(args) {
        send({t: "ui_effect_tapped"});
    }
});

hook("Assembly-CSharp.dll", "idun.Ui", "IdunUnitInfoBarHud", "GetEffectRealtimeData", {
    onEnter: function(args) {
        this._effectType = args[1].toInt32();
    },
    onLeave: function(retval) {
        var entries = {};
        if (retval && !retval.isNull()) {
            try {
                var count = retval.add(_dictCountOff).readS32();
                var entriesArr = retval.add(_dictEntriesOff).readPointer();
                if (!entriesArr.isNull() && count > 0 && count < 100) {
                    var dataStart = entriesArr.add(0x20);
                    for (var i = 0; i < count; i++) {
                        var base = dataStart.add(i * 16);
                        var hash = base.readS32();
                        if (hash < 0) continue;
                        entries[base.add(8).readS32()] = base.add(12).readS32();
                    }
                }
            } catch(e) {}
        }
        send({t: "ui_effect_rt", effectType: this._effectType, entries: entries});
    }
});

// ==========================================
// 4. GetEffectAbilityConfig — capture the config for each effect
// ==========================================
hook("Assembly-CSharp.dll", "idun.Ui", "IdunUnitInfoBarHud", "GetEffectAbilityConfig", {
    onEnter: function(args) {
        // args[0]=this, args[1]=EffectType(int), args[2]=BEntityId (value type, 8 bytes)
        this._effectType = args[1].toInt32();
    },
    onLeave: function(retval) {
        // retval = StatefulAbilityConfiguration or null
        var config = null;
        if (retval && !retval.isNull()) {
            config = readAbilityConfig(retval);
        }
        send({t: "ui_effect_config", effectType: this._effectType, config: config});
    }
});

console.log("[*] UI tooltip hooks v2 ready — tap abilities/effects");