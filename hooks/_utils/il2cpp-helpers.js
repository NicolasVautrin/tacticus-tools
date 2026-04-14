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
