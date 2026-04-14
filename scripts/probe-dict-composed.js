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
// Probe Dictionary field offsets at runtime
// requires: _utils/il2cpp-helpers

// Try multiple assembly names for mscorlib/System
var asmNames = ["mscorlib.dll", "System.dll", "System.Collections.dll",
                "System.Private.CoreLib.dll", "netstandard.dll"];
var ns = "System.Collections.Generic";

for (var ai = 0; ai < asmNames.length; ai++) {
    var cls = findClass(asmNames[ai], ns, "Dictionary`2");
    if (cls) {
        send({t: "dict_class_found", asm: asmNames[ai]});
        // enumerate fields
        var k = cls;
        while (!k.isNull()) {
            var cname = s(class_get_name(k));
            var it = Memory.alloc(Process.pointerSize);
            it.writePointer(ptr(0));
            var f;
            while (!(f = class_get_fields(k, it)).isNull()) {
                var fn = s(field_get_name(f));
                var off = field_get_offset(f);
                send({t: "dict_field", class: cname, name: fn, offset: off});
            }
            k = class_get_parent(k);
            if (cname === "Object") break;
        }
    }
}

// Alternative: find a CONCRETE dict type from a known class
// StatefulAbilityConfiguration.GetAllVariablesForLevel returns Dictionary<AbilityVariableType, int[]>
// Let's use AbilityConfigDto which has concrete fields
var dtoClass = findClass("MetaLogicAssembly.dll", "IdunMetaLogic.Client.DTO.Config", "AbilityConfigDto");
if (dtoClass) {
    send({t: "dto_found"});
    var it2 = Memory.alloc(Process.pointerSize);
    it2.writePointer(ptr(0));
    var f2;
    while (!(f2 = class_get_fields(dtoClass, it2)).isNull()) {
        var fn2 = s(field_get_name(f2));
        send({t: "dto_field", name: fn2, offset: field_get_offset(f2)});
    }
}

// Try to get the class from a field type
var field_get_type = new NativeFunction(il2cpp.findExportByName("il2cpp_field_get_type"), "pointer", ["pointer"]);
var class_from_type = new NativeFunction(il2cpp.findExportByName("il2cpp_class_from_type"), "pointer", ["pointer"]);

// Get the Variables field on AbilityConfiguration via SAC parent
var sacClass = findClass("MetaLogicAssembly.dll", "idun.meta", "StatefulAbilityConfiguration");
if (sacClass) {
    // Walk to parent (AbilityConfiguration)
    var acClass = class_get_parent(sacClass);
    if (acClass && !acClass.isNull()) {
        send({t: "ac_class", name: s(class_get_name(acClass))});
        // Find Variables field
        var it3 = Memory.alloc(Process.pointerSize);
        it3.writePointer(ptr(0));
        var f3;
        while (!(f3 = class_get_fields(acClass, it3)).isNull()) {
            var fn3 = s(field_get_name(f3));
            if (fn3 === "Variables" || fn3 === "Constants") {
                var ftype = field_get_type(f3);
                var ftypeClass = class_from_type(ftype);
                if (!ftypeClass.isNull()) {
                    var typeName = s(class_get_name(ftypeClass));
                    var typeNs = s(class_get_namespace(ftypeClass));
                    send({t: "field_type", fieldName: fn3, typeName: typeName, typeNs: typeNs});
                    // Enumerate fields of this CONCRETE dict class
                    var it4 = Memory.alloc(Process.pointerSize);
                    it4.writePointer(ptr(0));
                    var f4;
                    while (!(f4 = class_get_fields(ftypeClass, it4)).isNull()) {
                        send({t: "concrete_dict_field", dictFor: fn3,
                              name: s(field_get_name(f4)), offset: field_get_offset(f4)});
                    }
                }
            }
        }
    }
}

console.log("[*] Dict probe done");