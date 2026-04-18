// oneshot: Scan libil2cpp.so .data/.rodata sections for 8-byte slots that hold runtime-
// resolved Il2CppClass* or MethodInfo* pointers, and build a mapping:
//   {addr_rva_hex -> {kind: "class"|"method", name: "..."}}
//
// Used to resolve PTR_DAT_XXXXXXXX references in Ghidra's decompile output.
// At runtime, each PTR_DAT cell holds a pointer to a heap-allocated Il2CppClass or MethodInfo
// (populated by IL2CPP init). We dereference every aligned pointer cell in the writable/read
// data sections and match its value against a set of known pointers built from il2cpp_full.
//
// Prerequisite: data/il2cpp_full.json must be up-to-date (contains kp/mp fields).
//
// Sends:
//   {t: "ptr_dat_map", entries: {rva_hex: {k: "class"|"method", n: "..."}}}

var il2cpp = Process.findModuleByName("libil2cpp.so");
var il2cppBase = il2cpp.base;
var il2cppEnd  = il2cppBase.add(il2cpp.size);

send({t: "progress", msg: "Module: " + il2cppBase + " .. " + il2cppEnd + " (" + il2cpp.size + " bytes)"});

// --- Load known pointers from il2cpp_full.json (pre-baked on host, sent via rpc if needed) ---
// Since we can't easily read host files from Frida, we build the registry from a fresh
// enumeration of classes/methods — same approach as dump-il2cpp-full.js but keeping only
// pointer -> name (no metadata). Fast enough (~5-10s).

function sym(n, ret, args) {
    var p = il2cpp.findExportByName(n);
    if (!p) return null;
    return new NativeFunction(p, ret, args);
}

var domain_get = sym("il2cpp_domain_get", "pointer", []);
var domain_get_assemblies = sym("il2cpp_domain_get_assemblies", "pointer", ["pointer", "pointer"]);
var assembly_get_image = sym("il2cpp_assembly_get_image", "pointer", ["pointer"]);
var image_get_class_count = sym("il2cpp_image_get_class_count", "uint32", ["pointer"]);
var image_get_class = sym("il2cpp_image_get_class", "pointer", ["pointer", "uint32"]);
var class_get_name = sym("il2cpp_class_get_name", "pointer", ["pointer"]);
var class_get_namespace = sym("il2cpp_class_get_namespace", "pointer", ["pointer"]);
var class_get_methods = sym("il2cpp_class_get_methods", "pointer", ["pointer", "pointer"]);
var class_get_declaring_type = sym("il2cpp_class_get_declaring_type", "pointer", ["pointer"]);
var class_get_type = sym("il2cpp_class_get_type", "pointer", ["pointer"]);
var method_get_name = sym("il2cpp_method_get_name", "pointer", ["pointer"]);

function s(p) { try { return p.readUtf8String() || ""; } catch(e) { return ""; } }

var classFullNameCache = {};
function classFullName(klass) {
    if (!klass || klass.isNull()) return null;
    var key = klass.toString();
    if (classFullNameCache[key] !== undefined) return classFullNameCache[key];
    var name = s(class_get_name(klass));
    var ns = s(class_get_namespace(klass));
    var decl = class_get_declaring_type ? class_get_declaring_type(klass) : null;
    var full;
    if (decl && !decl.isNull()) {
        var parentFull = classFullName(decl);
        full = parentFull ? (parentFull + "." + name) : (ns ? ns + "." + name : name);
    } else {
        full = ns ? ns + "." + name : name;
    }
    classFullNameCache[key] = full;
    return full;
}

send({t: "progress", msg: "Building class/method/type pointer registry..."});

// ptr_string -> {k: "class"|"method"|"type", n: fullName}
var registry = {};
var regStats = {classes: 0, methods: 0, types: 0};

var domain = domain_get();
var sizePtr = Memory.alloc(4);
var assemblies = domain_get_assemblies(domain, sizePtr);
var asmCount = sizePtr.readU32();

for (var i = 0; i < asmCount; i++) {
    var assembly = assemblies.add(i * Process.pointerSize).readPointer();
    var image = assembly_get_image(assembly);
    var classCount = image_get_class_count(image);
    for (var j = 0; j < classCount; j++) {
        var klass = image_get_class(image, j);
        if (!klass || klass.isNull()) continue;
        var fullName = classFullName(klass);
        if (!fullName) continue;
        registry[klass.toString()] = {k: "class", n: fullName};
        regStats.classes++;

        // Il2CppType* — the runtime type descriptor (distinct pointer from Il2CppClass*)
        if (class_get_type) {
            try {
                var typePtr = class_get_type(klass);
                if (typePtr && !typePtr.isNull()) {
                    registry[typePtr.toString()] = {k: "type", n: fullName};
                    regStats.types++;
                }
            } catch(e) {}
        }

        // Methods
        var it = Memory.alloc(Process.pointerSize);
        it.writePointer(ptr(0));
        var m;
        while (!(m = class_get_methods(klass, it)).isNull()) {
            var mname = s(method_get_name(m));
            registry[m.toString()] = {k: "method", n: fullName + "." + mname};
            regStats.methods++;
        }
    }
}

send({t: "progress", msg: "Registry: " + regStats.classes + " classes, " + regStats.methods + " methods, " + regStats.types + " types"});

// --- Enumerate ranges from the module itself (covers all ELF segments) ---
// Module.enumerateRanges returns ranges *belonging to* the module regardless of protection;
// this is the cleanest way to capture .text+.rodata+.data.rel.ro+.data+.bss.
var ranges = il2cpp.enumerateRanges('r--')
    .concat(il2cpp.enumerateRanges('rw-'))
    .concat(il2cpp.enumerateRanges('r-x'));

// Deduplicate ranges (Module.enumerateRanges may report the same region under multiple
// protection queries) and skip x-only code where we'd just waste time on false positives.
var seenKey = {};
var modRanges = [];
for (var r = 0; r < ranges.length; r++) {
    var rg = ranges[r];
    // Skip pure-executable pages (.text) — any pointer-matching there is coincidence.
    if (rg.protection === 'r-x') continue;
    var key = rg.base.toString() + ":" + rg.size;
    if (seenKey[key]) continue;
    seenKey[key] = 1;
    modRanges.push({base: rg.base, size: rg.size, prot: rg.protection});
}
var totalBytes = 0;
for (var ri = 0; ri < modRanges.length; ri++) totalBytes += modRanges[ri].size;
send({t: "progress", msg: "Scanning " + modRanges.length + " ranges in libil2cpp.so, " + totalBytes + " bytes"});

var entries = {};
var matches = 0;
var slots = 0;

for (var k = 0; k < modRanges.length; k++) {
    var mr = modRanges[k];
    var baseAddr = mr.base;
    var sz = mr.size;
    // Iterate 8 bytes at a time
    for (var off = 0; off + 8 <= sz; off += 8) {
        var cellAddr = baseAddr.add(off);
        var val;
        try { val = cellAddr.readPointer(); } catch(e) { continue; }
        slots++;
        if (val.isNull()) continue;
        var hit = registry[val.toString()];
        if (!hit) continue;
        var rva = cellAddr.sub(il2cppBase).toString(16);
        entries[rva] = {k: hit.k, n: hit.n};
        matches++;
    }
    if (k % 4 === 0) send({t: "progress", msg: "range " + (k+1) + "/" + modRanges.length + " — matches so far: " + matches});
}

send({t: "progress", msg: "Scan done. Slots examined: " + slots + ", matches: " + matches});
send({t: "ptr_dat_map", entries: entries});
send({t: "progress", msg: "Done. You can stop this script."});
