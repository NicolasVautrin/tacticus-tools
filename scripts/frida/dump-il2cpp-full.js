// oneshot: Dump COMPLETE IL2CPP metadata (methods with signatures, classes with layouts, enums)
// for Ghidra pre-processing. Output format designed to drive GhidraApplyIl2CppSymbols.java.
//
// Sends:
//   {t: "il2cpp_full", methods: {...}, classes: {...}, enums: {...}}
//
// Methods:  rva_hex -> {n, d, r, p: [{n,t}], s: 1|0, mp: methodinfo_ptr_hex}
//   n  = full name "Namespace.Class.Method" (with parent chain for nested classes)
//   d  = declaring class full name
//   r  = return type full name
//   p  = array of params {n: paramName, t: paramType}
//   s  = 1 if static (no `this` param), 0 otherwise
//   mp = MethodInfo* runtime address (hex, offset from libil2cpp.so base) — used to resolve
//        PTR_DAT_xxx data cells that point to this MethodInfo
//
// Classes:  fullName -> {ns, n, decl, parent, size, vtype, kp, flags, iface, abs, gen, infl, interfaces, fields: [{n,t,o}]}
//   ns    = namespace
//   n     = short class name
//   decl  = declaring class full name (for nested/coroutines) or null
//   parent= parent class full name (inheritance) or null
//   size  = instance size in bytes
//   vtype = 1 if value type
//   kp    = Il2CppClass* runtime address (hex, offset from libil2cpp.so base) — used to resolve
//           PTR_DAT_xxx data cells that point to this class
//   flags = raw uint32 TypeAttributes (0x20=interface, 0x80=abstract, 0x100=sealed, 0x18 mask=layout)
//   iface = 1 if interface
//   abs   = 1 if abstract
//   gen   = 1 if generic definition (`<T>`, pre-instantiation)
//   infl  = 1 if generic instantiation (concrete `Foo<SomeT>`)
//   interfaces = array of interface fullNames implemented (present only when non-empty)
//   fields= [{n: fieldName, t: typeName, o: offset}]
//
// Enums:    fullName -> {"Name": "value"}   valeur en DECIMAL EXACT (chaine), largeur reelle
//           de l'enum (jusqu'a 64 bits). Keye par NOM : deux membres de meme valeur coexistent.
//
// Takes ~30-60s for a large game.

var il2cpp = Process.findModuleByName("GameAssembly.dll") || Process.findModuleByName("libil2cpp.so");
if (!il2cpp) {
    throw new Error("Could not find GameAssembly.dll or libil2cpp.so");
}
var il2cppBase = il2cpp.base;

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
var image_get_name = sym("il2cpp_image_get_name", "pointer", ["pointer"]);

var class_get_name = sym("il2cpp_class_get_name", "pointer", ["pointer"]);
var class_get_namespace = sym("il2cpp_class_get_namespace", "pointer", ["pointer"]);
var class_get_methods = sym("il2cpp_class_get_methods", "pointer", ["pointer", "pointer"]);
var class_get_fields = sym("il2cpp_class_get_fields", "pointer", ["pointer", "pointer"]);
var class_is_enum = sym("il2cpp_class_is_enum", "int32", ["pointer"]);
var class_is_valuetype = sym("il2cpp_class_is_valuetype", "int32", ["pointer"]);
var class_get_parent = sym("il2cpp_class_get_parent", "pointer", ["pointer"]);
var class_get_declaring_type = sym("il2cpp_class_get_declaring_type", "pointer", ["pointer"]);
var class_instance_size = sym("il2cpp_class_instance_size", "int32", ["pointer"]);
var class_get_type = sym("il2cpp_class_get_type", "pointer", ["pointer"]);
var class_get_flags = sym("il2cpp_class_get_flags", "uint32", ["pointer"]);
var class_is_interface = sym("il2cpp_class_is_interface", "int32", ["pointer"]);
var class_is_abstract = sym("il2cpp_class_is_abstract", "int32", ["pointer"]);
var class_is_generic = sym("il2cpp_class_is_generic", "int32", ["pointer"]);
var class_is_inflated = sym("il2cpp_class_is_inflated", "int32", ["pointer"]);
var class_get_interfaces = sym("il2cpp_class_get_interfaces", "pointer", ["pointer", "pointer"]);

var method_get_name = sym("il2cpp_method_get_name", "pointer", ["pointer"]);
var method_get_return_type = sym("il2cpp_method_get_return_type", "pointer", ["pointer"]);
var method_get_param_count = sym("il2cpp_method_get_param_count", "uint32", ["pointer"]);
var method_get_param = sym("il2cpp_method_get_param", "pointer", ["pointer", "uint32"]);
var method_get_param_name = sym("il2cpp_method_get_param_name", "pointer", ["pointer", "uint32"]);
var method_get_flags = sym("il2cpp_method_get_flags", "uint32", ["pointer", "pointer"]);

var field_get_name = sym("il2cpp_field_get_name", "pointer", ["pointer"]);
var field_is_literal = sym("il2cpp_field_is_literal", "int32", ["pointer"]);
var field_static_get_value = sym("il2cpp_field_static_get_value", "void", ["pointer", "pointer"]);
var field_get_offset = sym("il2cpp_field_get_offset", "int32", ["pointer"]);
var field_get_type = sym("il2cpp_field_get_type", "pointer", ["pointer"]);

var type_get_name = sym("il2cpp_type_get_name", "pointer", ["pointer"]);

function s(p) { try { return p.readUtf8String() || ""; } catch(e) { return ""; } }

// Cache class full names (ns.className with parent chain resolved)
var classFullNameCache = {};

function classFullName(klass) {
    if (!klass || klass.isNull()) return null;
    var key = klass.toString();
    if (classFullNameCache[key] !== undefined) return classFullNameCache[key];

    var name = s(class_get_name(klass));
    var ns = s(class_get_namespace(klass));

    // If nested, prepend declaring class chain
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

function typeName(type) {
    if (!type || type.isNull()) return "";
    try { return s(type_get_name(type)); } catch(e) { return ""; }
}

// Type SOUS-JACENT d'un enum : porte par son champ implicite `value__`.
// Le lire est OBLIGATOIRE, pas un raffinement — cf. `readEnumLiteral`.
function enumUnderlying(klass) {
    var it = Memory.alloc(Process.pointerSize);
    it.writePointer(ptr(0));
    var f;
    while (!(f = class_get_fields(klass, it)).isNull()) {
        if (s(field_get_name(f)) !== "value__") continue;
        try { return typeName(field_get_type(f)); } catch(e) { return ""; }
    }
    return "";
}

// Valeur d'un literal d'enum, rendue en DECIMAL EXACT (chaine), selon la largeur reelle.
//
// POURQUOI la largeur : ce site lisait `readS32()` inconditionnellement. Sur un enum adosse a
// `long` — tous les enums de FLAGS un peu fournis du jeu — chaque membre au-dessus du bit 31 a
// ses 32 bits de poids faible NULS, donc tronquait vers 0 ; et comme le dictionnaire etait keye
// PAR VALEUR, ils s'ecrasaient l'un l'autre. Mesure sur `IdunBattle.Core.Services.TargetingRule`
// (build gqfc5mff6c) : douze membres reduits a UN SEUL, `TargetIsCasterOrEnemy`, range sous la
// cle "0" parce qu'il etait le dernier ecrit. Perte SILENCIEUSE — d'ou les masques de ciblage
// dont il a fallu renommer les bits a la main au decompile.
//
// POURQUOI une chaine : un flag 64 bits depasse 2^53, ou un Number JSON perd des bits de poids
// faible. Le decimal exact traverse le JSON puis le TSV sans arrondi.
function readEnumLiteral(buf, underlying) {
    switch (underlying) {
        case "System.SByte":  return buf.readS8().toString();
        case "System.Byte":   return buf.readU8().toString();
        case "System.Int16":  return buf.readS16().toString();
        case "System.UInt16": return buf.readU16().toString();
        case "System.UInt32": return buf.readU32().toString();
        case "System.Int64":  return buf.readS64().toString();
        case "System.UInt64": return buf.readU64().toString();
        default:              return buf.readS32().toString();   // System.Int32 = defaut C#
    }
}

// -- Probe which exports are available
var missing = [];
var required = {
    class_get_declaring_type: class_get_declaring_type,
    class_get_parent: class_get_parent,
    class_instance_size: class_instance_size,
    class_is_valuetype: class_is_valuetype,
    method_get_return_type: method_get_return_type,
    method_get_param_count: method_get_param_count,
    method_get_param: method_get_param,
    method_get_param_name: method_get_param_name,
};
for (var k in required) if (!required[k]) missing.push(k);
send({t: "progress", msg: "Missing exports: " + (missing.length ? missing.join(", ") : "none")});

send({t: "progress", msg: "Starting full metadata dump..."});

var methods = {};
var classes = {};
var enums = {};
var stats = {methods: 0, classes: 0, enums: 0, fields: 0};

var domain = domain_get();
var sizePtr = Memory.alloc(4);
var assemblies = domain_get_assemblies(domain, sizePtr);
var asmCount = sizePtr.readU32();

var valueBuf = Memory.alloc(8);

for (var i = 0; i < asmCount; i++) {
    var assembly = assemblies.add(i * Process.pointerSize).readPointer();
    var image = assembly_get_image(assembly);
    var asmName = s(image_get_name(image));
    var classCount = image_get_class_count(image);
    send({t: "progress", msg: "Assembly " + asmName + ": " + classCount + " classes"});

    for (var j = 0; j < classCount; j++) {
        var klass = image_get_class(image, j);
        if (!klass || klass.isNull()) continue;
        var fullName = classFullName(klass);
        if (!fullName) continue;

        // --- Class metadata ---
        var classEntry = {
            ns: s(class_get_namespace(klass)),
            n: s(class_get_name(klass)),
            decl: null,
            parent: null,
            size: 0,
            vtype: 0,
            kp: null,
            fields: []
        };
        // Il2CppClass* raw address (typically on the heap, not in libil2cpp.so).
        // Used to resolve PTR_DAT_xxx by reading the data cell value and matching it here.
        try { classEntry.kp = klass.toString(); } catch(e) {}
        if (class_get_declaring_type) {
            var decl = class_get_declaring_type(klass);
            if (decl && !decl.isNull()) classEntry.decl = classFullName(decl);
        }
        if (class_get_parent) {
            var par = class_get_parent(klass);
            if (par && !par.isNull()) classEntry.parent = classFullName(par);
        }
        if (class_instance_size) {
            try { classEntry.size = class_instance_size(klass); } catch(e) {}
        }
        if (class_is_valuetype) {
            try { classEntry.vtype = class_is_valuetype(klass) ? 1 : 0; } catch(e) {}
        }
        if (class_get_flags) {
            try { classEntry.flags = class_get_flags(klass) >>> 0; } catch(e) {}
        }
        if (class_is_interface) {
            try { classEntry.iface = class_is_interface(klass) ? 1 : 0; } catch(e) {}
        }
        if (class_is_abstract) {
            try { classEntry.abs = class_is_abstract(klass) ? 1 : 0; } catch(e) {}
        }
        if (class_is_generic) {
            try { classEntry.gen = class_is_generic(klass) ? 1 : 0; } catch(e) {}
        }
        if (class_is_inflated) {
            try { classEntry.infl = class_is_inflated(klass) ? 1 : 0; } catch(e) {}
        }
        if (class_get_interfaces) {
            try {
                var iit = Memory.alloc(Process.pointerSize);
                iit.writePointer(ptr(0));
                var ifaces = [];
                var ic;
                while (!(ic = class_get_interfaces(klass, iit)).isNull()) {
                    var ifn = classFullName(ic);
                    if (ifn) ifaces.push(ifn);
                }
                if (ifaces.length) classEntry.interfaces = ifaces;
            } catch(e) {}
        }

        // --- Methods ---
        var it = Memory.alloc(Process.pointerSize);
        it.writePointer(ptr(0));
        var m;
        while (!(m = class_get_methods(klass, it)).isNull()) {
            var mptr = m.readPointer();
            if (mptr.isNull() || mptr.compare(il2cppBase) < 0) continue;
            var offset = mptr.sub(il2cppBase).toString(16);
            var mname = s(method_get_name(m));
            var entry = {
                n: fullName + "." + mname,
                d: fullName,
                // MethodInfo* raw absolute address (typically on heap).
                // Used to resolve PTR_DAT_xxx that hold MethodInfo pointers.
                mp: m.toString()
            };
            if (method_get_flags) {
                try {
                    // IL2CPP method flags: bit 0x10 = static (matches .NET MethodAttributes.Static)
                    var flags = method_get_flags(m, ptr(0));
                    entry.s = (flags & 0x10) ? 1 : 0;
                } catch(e) { entry.s = 0; }
            }
            if (method_get_return_type) {
                try { entry.r = typeName(method_get_return_type(m)); } catch(e) {}
            }
            if (method_get_param_count && method_get_param) {
                try {
                    var pc = method_get_param_count(m);
                    var params = [];
                    for (var pi = 0; pi < pc; pi++) {
                        var pt = method_get_param(m, pi);
                        var pn = method_get_param_name ? s(method_get_param_name(m, pi)) : "p" + pi;
                        params.push({n: pn, t: typeName(pt)});
                    }
                    entry.p = params;
                } catch(e) {}
            }
            methods[offset] = entry;
            stats.methods++;
        }

        // --- Enums ---
        if (class_is_enum(klass)) {
            var enumValues = {};
            var hasValues = false;
            var underlying = enumUnderlying(klass);
            var fit = Memory.alloc(Process.pointerSize);
            fit.writePointer(ptr(0));
            var f;
            while (!(f = class_get_fields(klass, fit)).isNull()) {
                var fname = s(field_get_name(f));
                if (fname === "value__") continue;
                if (field_is_literal(f)) {
                    try {
                        valueBuf.writeS64(0);
                        field_static_get_value(f, valueBuf);
                        // Keye par NOM (unique en C#), pas par valeur : deux membres de meme
                        // valeur — un alias, un composite — sont tous deux CONSERVES au lieu
                        // que le second efface le premier.
                        enumValues[fname] = readEnumLiteral(valueBuf, underlying);
                        hasValues = true;
                    } catch(e) {}
                }
            }
            if (hasValues) {
                enums[fullName] = enumValues;
                stats.enums++;
            }
        } else {
            // --- Instance fields (non-enum) ---
            var fit2 = Memory.alloc(Process.pointerSize);
            fit2.writePointer(ptr(0));
            var f2;
            while (!(f2 = class_get_fields(klass, fit2)).isNull()) {
                if (field_is_literal(f2)) continue;
                var fname2 = s(field_get_name(f2));
                var foffset = field_get_offset(f2);
                var ftypeName = "";
                try {
                    var ftype = field_get_type(f2);
                    if (!ftype.isNull()) ftypeName = typeName(ftype);
                } catch(e) {}
                classEntry.fields.push({n: fname2, t: ftypeName, o: foffset});
                stats.fields++;
            }
        }

        classes[fullName] = classEntry;
        stats.classes++;
    }
}

// === Second pass: walk parent chains to dump INFLATED generics ===
// `image_get_class` only returns generic DEFINITIONS (TriggeredAbilityPlaybook`1) and
// concrete classes, not inflated instances (TriggeredAbilityPlaybook<SomeT>) which the
// runtime creates lazily. But each concrete subclass of a generic base has an inflated
// parent — we can walk parent chains and capture those instances. Their layout has the
// REAL field offsets (vs 0 for generic defs).
var inflatedSeen = {};   // klass.toString() -> 1
var inflatedDumped = {}; // fullName -> true
function dumpInflated(klass) {
    if (!klass || klass.isNull()) return;
    var key = klass.toString();
    if (inflatedSeen[key]) return;
    inflatedSeen[key] = 1;
    if (!class_is_inflated || !class_is_inflated(klass)) return;
    // Name for inflated: use class_get_type + type_get_name to get `Foo<Bar>`
    var name = null;
    try {
        var ty = class_get_type(klass);
        name = ty && !ty.isNull() ? s(type_get_name(ty)) : null;
    } catch(e) {}
    if (!name) {
        name = classFullName(klass);
        if (!name) return;
        name = name + '<inflated@' + key + '>';
    }
    // Only dump once per logical name (multiple klass pointers may share the same inflation)
    if (inflatedDumped[name]) return;
    inflatedDumped[name] = true;
    var entry = {
        ns: s(class_get_namespace(klass)),
        n: s(class_get_name(klass)),
        decl: null,
        parent: null,
        size: 0,
        vtype: 0,
        kp: key,
        fields: [],
        iface: 0, abs: 0, gen: 0, infl: 1
    };
    try {
        var par = class_get_parent(klass);
        if (par && !par.isNull()) entry.parent = classFullName(par);
    } catch(e) {}
    try { entry.size = class_instance_size(klass); } catch(e) {}
    try { entry.vtype = class_is_valuetype(klass) ? 1 : 0; } catch(e) {}
    try { entry.abs = class_is_abstract(klass) ? 1 : 0; } catch(e) {}
    try { entry.flags = class_get_flags(klass) >>> 0; } catch(e) {}
    var fit = Memory.alloc(Process.pointerSize);
    fit.writePointer(ptr(0));
    var f;
    while (!(f = class_get_fields(klass, fit)).isNull()) {
        if (field_is_literal(f)) continue;
        var fname = s(field_get_name(f));
        var foffset = field_get_offset(f);
        var ftype = '';
        try {
            var ft = field_get_type(f);
            if (!ft.isNull()) ftype = typeName(ft);
        } catch(e) {}
        entry.fields.push({n: fname, t: ftype, o: foffset});
    }
    classes[name] = entry;
    stats.classes++;
}

send({t: "progress", msg: "Second pass: walking parent chains for inflated generics..."});
for (var cname in classes) {
    var c = classes[cname];
    if (!c.kp) continue;
    // Walk parent chain (need to re-resolve klass pointer from kp string — we stored it)
    try {
        var klass = ptr(c.kp);
        var parent = class_get_parent(klass);
        while (parent && !parent.isNull()) {
            dumpInflated(parent);
            parent = class_get_parent(parent);
        }
    } catch(e) {}
}

send({t: "progress", msg: "Done: " + stats.methods + " methods, " + stats.classes + " classes, " + stats.enums + " enums, " + stats.fields + " fields"});
send({t: "il2cpp_full", methods: methods, classes: classes, enums: enums});
send({t: "progress", msg: "Dump complete. You can stop this script now."});
