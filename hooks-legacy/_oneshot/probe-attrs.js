// Probe: what custom-attribute related exports exist on libil2cpp.so
// Emits: {t: "probe_attrs", exports: {name: present_bool}, sample: "..."}

var il2cpp = Process.findModuleByName("libil2cpp.so");

var names = [
    // Get info object
    "il2cpp_custom_attrs_from_class",
    "il2cpp_custom_attrs_from_method",
    "il2cpp_custom_attrs_from_field",
    "il2cpp_custom_attrs_from_param",
    "il2cpp_custom_attrs_from_assembly",
    // Check presence of a specific attribute class
    "il2cpp_custom_attrs_has_attr",
    "il2cpp_custom_attrs_get_attr",
    "il2cpp_custom_attrs_free",
    // Direct test
    "il2cpp_class_has_attribute",
    "il2cpp_class_has_custom_attribute",
    "il2cpp_class_get_custom_attribute_type",
    // Cache form
    "il2cpp_class_get_custom_attributes_info",
    "il2cpp_class_get_custom_attribute_info",
    // Reflection-level
    "MonoCustomAttrInfo",
    "il2cpp_reflection_get_custom_attrs_info",
    // Utilities to get classes by name
    "il2cpp_class_from_name",
    "il2cpp_image_get_name",
    "il2cpp_domain_get",
    "il2cpp_domain_get_assemblies",
    // Cache
    "il2cpp_custom_attrs_cache_from_class",
    // Via Type
    "il2cpp_type_get_object",
    // Low level resolver
    "CustomAttributeDataReader",
    "il2cpp_custom_attribute_reader"
];

var result = {};
for (var i = 0; i < names.length; i++) {
    var p = il2cpp.findExportByName(names[i]);
    result[names[i]] = p ? ("0x" + p.sub(il2cpp.base).toString(16)) : null;
}

send({t: "probe_attrs", exports: result});
