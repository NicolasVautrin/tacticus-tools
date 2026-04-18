// oneshot: probe which IL2CPP class-flag APIs are available, and sample a known class
// to verify the bit layout. Answers:
//   - can we detect `abstract` / `interface` / `sealed` / `generic` ?
//   - what's the raw flags value for TriggeredAbilityPlaybook`1 (should be abstract+generic)
//   - what's the raw flags value for IAbilitiesDatabase (should be interface)
//
// Sends: {t: "probe_result", available: [...], samples: {...}}

var il2cpp = Process.findModuleByName("libil2cpp.so");

function sym(n, ret, args) {
    var p = il2cpp.findExportByName(n);
    if (!p) return null;
    return new NativeFunction(p, ret, args);
}

function s(p) { try { return p.readUtf8String() || ""; } catch(e) { return ""; } }

// Candidate APIs to probe
var candidates = [
    "il2cpp_class_get_flags",
    "il2cpp_class_is_interface",
    "il2cpp_class_is_abstract",
    "il2cpp_class_is_generic",
    "il2cpp_class_is_inflated",
    "il2cpp_class_is_sealed",
    "il2cpp_class_has_attribute",
    "il2cpp_class_get_type_token",
    "il2cpp_class_get_image",
    "il2cpp_class_get_assemblyname",
    "il2cpp_class_get_rank",
    "il2cpp_class_is_subclass_of",
    "il2cpp_class_get_interfaces",
    "il2cpp_class_get_property_from_name",
    "il2cpp_class_get_properties",
    "il2cpp_method_get_class",
    "il2cpp_type_is_reference",
    "il2cpp_type_is_byref",
];

var available = {};
candidates.forEach(function(name) {
    var p = il2cpp.findExportByName(name);
    available[name] = p ? p.toString() : null;
});
send({t: "probe_available", exports: available});

// Resolve a few classes and read flags
var domain_get = sym("il2cpp_domain_get", "pointer", []);
var domain_get_assemblies = sym("il2cpp_domain_get_assemblies", "pointer", ["pointer", "pointer"]);
var assembly_get_image = sym("il2cpp_assembly_get_image", "pointer", ["pointer"]);
var image_get_class_count = sym("il2cpp_image_get_class_count", "uint32", ["pointer"]);
var image_get_class = sym("il2cpp_image_get_class", "pointer", ["pointer", "uint32"]);
var image_get_name = sym("il2cpp_image_get_name", "pointer", ["pointer"]);
var class_get_name = sym("il2cpp_class_get_name", "pointer", ["pointer"]);
var class_get_namespace = sym("il2cpp_class_get_namespace", "pointer", ["pointer"]);

var class_get_flags = sym("il2cpp_class_get_flags", "uint32", ["pointer"]);
var class_is_interface = sym("il2cpp_class_is_interface", "int32", ["pointer"]);
var class_is_abstract = sym("il2cpp_class_is_abstract", "int32", ["pointer"]);
var class_is_generic = sym("il2cpp_class_is_generic", "int32", ["pointer"]);
var class_is_inflated = sym("il2cpp_class_is_inflated", "int32", ["pointer"]);

// Targets of interest
var targets = {
    "IdunBattle.AI.Playbook.TriggeredAbilityPlaybook": null,  // should be abstract + generic
    "IdunBattle.Core.Services.IAbilitiesDatabase": null,        // should be interface
    "IdunBattle.Core.Services.AbilitiesDatabase": null,         // should be normal class
    "IdunBattle.Entities.Components.HealthComponent": null,     // normal concrete
    "IdunBattle.Utils.Hex.AxialCoordinate": null,               // struct (valuetype)
};

var domain = domain_get();
var sizePtr = Memory.alloc(4);
var assemblies = domain_get_assemblies(domain, sizePtr);
var asmCount = sizePtr.readU32();
var samples = {};

for (var i = 0; i < asmCount && Object.keys(samples).length < 8; i++) {
    var assembly = assemblies.add(i * Process.pointerSize).readPointer();
    var image = assembly_get_image(assembly);
    var cc = image_get_class_count(image);
    for (var j = 0; j < cc; j++) {
        var klass = image_get_class(image, j);
        if (!klass || klass.isNull()) continue;
        var ns = s(class_get_namespace(klass));
        var n = s(class_get_name(klass));
        var full = ns ? ns + "." + n : n;
        // Strip backtick suffix for matching
        var full_clean = full.replace(/`\d+$/, '');
        if (targets.hasOwnProperty(full_clean) && !samples[full_clean]) {
            var sample = {full: full};
            if (class_get_flags) {
                try { sample.flags = class_get_flags(klass) >>> 0; } catch(e) { sample.flags_err = String(e); }
            }
            if (class_is_interface) {
                try { sample.is_interface = class_is_interface(klass); } catch(e) {}
            }
            if (class_is_abstract) {
                try { sample.is_abstract = class_is_abstract(klass); } catch(e) {}
            }
            if (class_is_generic) {
                try { sample.is_generic = class_is_generic(klass); } catch(e) {}
            }
            if (class_is_inflated) {
                try { sample.is_inflated = class_is_inflated(klass); } catch(e) {}
            }
            samples[full_clean] = sample;
        }
    }
}

send({t: "probe_samples", samples: samples});
send({t: "probe_done"});
