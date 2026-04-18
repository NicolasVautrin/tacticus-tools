// oneshot: For each enum in the domain, inspect its custom attributes and record
// whether [JsonConverter(StringEnumConverter)] is applied. Newtonsoft serializes
// those enums as their name() instead of their int value, which we need to
// reproduce for a faithful roundtrip.
//
// Sends:
//   {t: "enum_attrs", enums: {"Full.Name": {conv: true|false, converter: "..."}}}
//   "conv" = true if JsonConverterAttribute is applied
//   "converter" = fully-qualified class name of the converter (if readable),
//                 typically "Newtonsoft.Json.Converters.StringEnumConverter"

var il2cpp = Process.findModuleByName("libil2cpp.so");

function sym(n, ret, args) {
    var p = il2cpp.findExportByName(n);
    if (!p) return null;
    return new NativeFunction(p, ret, args);
}

var domain_get            = sym("il2cpp_domain_get", "pointer", []);
var domain_get_assemblies = sym("il2cpp_domain_get_assemblies", "pointer", ["pointer", "pointer"]);
var assembly_get_image    = sym("il2cpp_assembly_get_image", "pointer", ["pointer"]);
var image_get_class_count = sym("il2cpp_image_get_class_count", "uint32", ["pointer"]);
var image_get_class       = sym("il2cpp_image_get_class", "pointer", ["pointer", "uint32"]);
var image_get_name        = sym("il2cpp_image_get_name", "pointer", ["pointer"]);
var class_from_name       = sym("il2cpp_class_from_name", "pointer", ["pointer", "pointer", "pointer"]);

var class_get_name        = sym("il2cpp_class_get_name", "pointer", ["pointer"]);
var class_get_namespace   = sym("il2cpp_class_get_namespace", "pointer", ["pointer"]);
var class_get_declaring   = sym("il2cpp_class_get_declaring_type", "pointer", ["pointer"]);
var class_is_enum         = sym("il2cpp_class_is_enum", "int32", ["pointer"]);
var class_has_attribute   = sym("il2cpp_class_has_attribute", "int32", ["pointer", "pointer"]);

var custom_attrs_from_class = sym("il2cpp_custom_attrs_from_class", "pointer", ["pointer"]);
var custom_attrs_has_attr   = sym("il2cpp_custom_attrs_has_attr", "int32", ["pointer", "pointer"]);
var custom_attrs_get_attr   = sym("il2cpp_custom_attrs_get_attr", "pointer", ["pointer", "pointer"]);
var custom_attrs_free       = sym("il2cpp_custom_attrs_free", "void", ["pointer"]);

function s(p) { try { return p.readUtf8String() || ""; } catch(e) { return ""; } }

function classFullName(klass) {
    if (!klass || klass.isNull()) return null;
    var name = s(class_get_name(klass));
    var ns = s(class_get_namespace(klass));
    var decl = class_get_declaring(klass);
    if (decl && !decl.isNull()) {
        var parent = classFullName(decl);
        return parent ? (parent + "." + name) : (ns ? ns + "." + name : name);
    }
    return ns ? ns + "." + name : name;
}

// Locate Newtonsoft.Json assembly image + JsonConverterAttribute + StringEnumConverter classes
var domain = domain_get();
var sizePtr = Memory.alloc(4);
var assemblies = domain_get_assemblies(domain, sizePtr);
var asmCount = sizePtr.readU32();

var newtonsoftImage = null;
for (var i = 0; i < asmCount; i++) {
    var asm = assemblies.add(i * Process.pointerSize).readPointer();
    var img = assembly_get_image(asm);
    var name = s(image_get_name(img));
    if (name === "Newtonsoft.Json.dll" || name === "Newtonsoft.Json") {
        newtonsoftImage = img;
        break;
    }
}
if (!newtonsoftImage) {
    send({t: "progress", msg: "Newtonsoft.Json image not found — listing all assemblies for reference:"});
    for (var i = 0; i < asmCount; i++) {
        var asm = assemblies.add(i * Process.pointerSize).readPointer();
        var img = assembly_get_image(asm);
        send({t: "progress", msg: "  " + s(image_get_name(img))});
    }
    send({t: "enum_attrs", error: "no newtonsoft image", enums: {}});
} else {
    send({t: "progress", msg: "Found Newtonsoft.Json image"});

    var ns1 = Memory.allocUtf8String("Newtonsoft.Json");
    var cn1 = Memory.allocUtf8String("JsonConverterAttribute");
    var jsonConvAttr = class_from_name(newtonsoftImage, ns1, cn1);
    send({t: "progress", msg: "JsonConverterAttribute: " + (jsonConvAttr && !jsonConvAttr.isNull() ? "OK" : "NOT FOUND")});

    var ns2 = Memory.allocUtf8String("Newtonsoft.Json.Converters");
    var cn2 = Memory.allocUtf8String("StringEnumConverter");
    var strEnumConv = class_from_name(newtonsoftImage, ns2, cn2);
    send({t: "progress", msg: "StringEnumConverter: " + (strEnumConv && !strEnumConv.isNull() ? "OK" : "NOT FOUND")});

    // Iterate all enums in all assemblies
    var result = {};
    var stats = {enumsSeen: 0, withConverter: 0, errors: 0};

    for (var i = 0; i < asmCount; i++) {
        var asm = assemblies.add(i * Process.pointerSize).readPointer();
        var img = assembly_get_image(asm);
        var n = image_get_class_count(img);
        for (var j = 0; j < n; j++) {
            var klass = image_get_class(img, j);
            if (!klass || klass.isNull()) continue;
            var isEnum = 0;
            try { isEnum = class_is_enum(klass); } catch(e) {}
            if (!isEnum) continue;

            var fullName = classFullName(klass);
            if (!fullName) continue;
            stats.enumsSeen++;

            // Fast path: class_has_attribute
            var hasConv = 0;
            try {
                if (jsonConvAttr && !jsonConvAttr.isNull()) {
                    hasConv = class_has_attribute(klass, jsonConvAttr);
                }
            } catch (e) { stats.errors++; }

            if (!hasConv) continue;  // skip most enums (majority have no converter)

            // Also test the specific StringEnumConverter attribute class
            var isStringEnum = 0;
            try {
                if (strEnumConv && !strEnumConv.isNull()) {
                    isStringEnum = class_has_attribute(klass, strEnumConv);
                }
            } catch (e) {}

            // Read the attribute instance to confirm converter class
            var converterName = null;
            try {
                var info = custom_attrs_from_class(klass);
                if (info && !info.isNull()) {
                    if (jsonConvAttr && custom_attrs_has_attr(info, jsonConvAttr)) {
                        var attrObj = custom_attrs_get_attr(info, jsonConvAttr);
                        if (attrObj && !attrObj.isNull()) {
                            // Il2CppObject layout:
                            //   0x00: Il2CppClass* klass
                            //   0x08: Il2CppObject* monitor
                            //   0x10+: fields
                            // JsonConverterAttribute has:
                            //   _converterType : System.Type
                            //   ConverterParameters : object[]
                            // System.Type objects encapsulate an Il2CppClass*. We try to
                            // read the first field as a System.Type reference and walk it.
                            var typeRef = attrObj.add(0x10).readPointer();
                            if (typeRef && !typeRef.isNull()) {
                                // System.RuntimeType inherits from System.Type; first field
                                // (after object header) is `m_handle` (IntPtr to Il2CppClass)
                                // or similar. Try common offsets.
                                for (var off = 0x10; off <= 0x28; off += 0x8) {
                                    try {
                                        var klassPtr = typeRef.add(off).readPointer();
                                        if (klassPtr && !klassPtr.isNull()) {
                                            var maybeName = classFullName(klassPtr);
                                            if (maybeName && maybeName.indexOf("Converter") >= 0) {
                                                converterName = maybeName;
                                                break;
                                            }
                                        }
                                    } catch (e) {}
                                }
                            }
                        }
                    }
                    custom_attrs_free(info);
                }
            } catch (e) { stats.errors++; }

            result[fullName] = {
                conv: 1,
                strEnum: isStringEnum ? 1 : 0,
                converter: converterName
            };
            stats.withConverter++;
        }
    }

    send({t: "progress", msg: "Scanned " + stats.enumsSeen + " enums, " + stats.withConverter + " with JsonConverter, " + stats.errors + " errors"});
    send({t: "enum_attrs", enums: result});
}
