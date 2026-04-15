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