// oneshot: Dump IL2CPP symbols (methods + enums + fields) for backend resolution
// Run once per APK version. Sends {t: "symbols", methods: {...}, enums: {...}, fields: {...}}
// The backend saves this as symbols.json in the workdir.
//
// Usage: inject via POST /api/scripts/run, wait for the "symbols" message, then stop.
// Takes ~5-15 seconds depending on device speed.

var il2cpp = Process.findModuleByName("libil2cpp.so");
var il2cppBase = il2cpp.base;

var domain_get = new NativeFunction(il2cpp.findExportByName("il2cpp_domain_get"), "pointer", []);
var domain_get_assemblies = new NativeFunction(il2cpp.findExportByName("il2cpp_domain_get_assemblies"), "pointer", ["pointer", "pointer"]);
var assembly_get_image = new NativeFunction(il2cpp.findExportByName("il2cpp_assembly_get_image"), "pointer", ["pointer"]);
var image_get_class_count = new NativeFunction(il2cpp.findExportByName("il2cpp_image_get_class_count"), "uint32", ["pointer"]);
var image_get_class = new NativeFunction(il2cpp.findExportByName("il2cpp_image_get_class"), "pointer", ["pointer", "uint32"]);
var image_get_name = new NativeFunction(il2cpp.findExportByName("il2cpp_image_get_name"), "pointer", ["pointer"]);
var class_get_name = new NativeFunction(il2cpp.findExportByName("il2cpp_class_get_name"), "pointer", ["pointer"]);
var class_get_namespace = new NativeFunction(il2cpp.findExportByName("il2cpp_class_get_namespace"), "pointer", ["pointer"]);
var class_get_methods = new NativeFunction(il2cpp.findExportByName("il2cpp_class_get_methods"), "pointer", ["pointer", "pointer"]);
var method_get_name = new NativeFunction(il2cpp.findExportByName("il2cpp_method_get_name"), "pointer", ["pointer"]);
var class_get_fields = new NativeFunction(il2cpp.findExportByName("il2cpp_class_get_fields"), "pointer", ["pointer", "pointer"]);
var field_get_name = new NativeFunction(il2cpp.findExportByName("il2cpp_field_get_name"), "pointer", ["pointer"]);
var class_is_enum = new NativeFunction(il2cpp.findExportByName("il2cpp_class_is_enum"), "int32", ["pointer"]);
var field_is_literal = new NativeFunction(il2cpp.findExportByName("il2cpp_field_is_literal"), "int32", ["pointer"]);
var field_static_get_value = new NativeFunction(il2cpp.findExportByName("il2cpp_field_static_get_value"), "void", ["pointer", "pointer"]);
var field_get_offset = new NativeFunction(il2cpp.findExportByName("il2cpp_field_get_offset"), "int32", ["pointer"]);
var field_get_type = new NativeFunction(il2cpp.findExportByName("il2cpp_field_get_type"), "pointer", ["pointer"]);
var type_get_name = new NativeFunction(il2cpp.findExportByName("il2cpp_type_get_name"), "pointer", ["pointer"]);

function s(p) { try { return p.readUtf8String() || ""; } catch(e) { return ""; } }

send({t: "progress", msg: "Starting symbol dump..."});

var methods = {};   // hex offset string → "Namespace.Class.Method"
var enums = {};     // "Namespace.ClassName" → {value_int_string: "FieldName", ...}
var fields = {};    // "Namespace.ClassName" → [{n: "fieldName", t: "TypeName", o: offset}, ...]
var methodCount = 0;
var enumCount = 0;
var fieldClassCount = 0;

var domain = domain_get();
var sizePtr = Memory.alloc(4);
var assemblies = domain_get_assemblies(domain, sizePtr);
var asmCount = sizePtr.readU32();

// Buffer for reading static enum values
var valueBuf = Memory.alloc(8);

for (var i = 0; i < asmCount; i++) {
    var assembly = assemblies.add(i * Process.pointerSize).readPointer();
    var image = assembly_get_image(assembly);
    var asmName = s(image_get_name(image));
    var classCount = image_get_class_count(image);

    send({t: "progress", msg: "Assembly " + asmName + ": " + classCount + " classes"});

    for (var j = 0; j < classCount; j++) {
        var klass = image_get_class(image, j);
        var className = s(class_get_name(klass));
        var ns = s(class_get_namespace(klass));
        var fullName = ns ? (ns + "." + className) : className;

        // --- Methods ---
        var it = Memory.alloc(Process.pointerSize);
        it.writePointer(ptr(0));
        var m;
        while (!(m = class_get_methods(klass, it)).isNull()) {
            var mptr = m.readPointer();
            if (!mptr.isNull() && mptr.compare(il2cppBase) >= 0) {
                var offset = mptr.sub(il2cppBase).toString(16);
                var mname = s(method_get_name(m));
                methods[offset] = fullName + "." + mname;
                methodCount++;
            }
        }

        // --- Enums ---
        if (class_is_enum(klass)) {
            var enumValues = {};
            var hasValues = false;
            var fit = Memory.alloc(Process.pointerSize);
            fit.writePointer(ptr(0));
            var f;
            while (!(f = class_get_fields(klass, fit)).isNull()) {
                var fname = s(field_get_name(f));
                if (fname === "value__") continue; // skip the backing field
                if (field_is_literal(f)) {
                    try {
                        valueBuf.writeS64(0);
                        field_static_get_value(f, valueBuf);
                        var val = valueBuf.readS32();
                        enumValues[val.toString()] = fname;
                        hasValues = true;
                    } catch(e) {
                        // Some literal fields can't be read statically, skip
                    }
                }
            }
            if (hasValues) {
                enums[fullName] = enumValues;
                enumCount++;
            }
        }

        // --- Fields (non-enum classes) ---
        if (!class_is_enum(klass)) {
            var classFields = [];
            var fit2 = Memory.alloc(Process.pointerSize);
            fit2.writePointer(ptr(0));
            var f2;
            while (!(f2 = class_get_fields(klass, fit2)).isNull()) {
                if (field_is_literal(f2)) continue; // skip constants
                var fname2 = s(field_get_name(f2));
                var foffset = field_get_offset(f2);
                var ftypeName = "";
                try {
                    var ftype = field_get_type(f2);
                    if (!ftype.isNull()) ftypeName = s(type_get_name(ftype));
                } catch(e) {}
                classFields.push({n: fname2, t: ftypeName, o: foffset});
            }
            if (classFields.length > 0) {
                fields[fullName] = classFields;
                fieldClassCount++;
            }
        }
    }
}

send({t: "progress", msg: "Done: " + methodCount + " methods, " + enumCount + " enums, " + fieldClassCount + " classes with fields"});

// Send in chunks if too large — Frida message size limit is ~128MB so should be fine
send({t: "symbols", methods: methods, enums: enums, fields: fields});

send({t: "progress", msg: "Symbol dump complete. You can stop this script now."});
