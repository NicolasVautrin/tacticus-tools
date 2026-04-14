// Probe AbilityConfiguration class structure at runtime
// requires: _utils/il2cpp-helpers

// Find AbilityConfiguration class
var assemblies = ["BattleLogicAssembly.dll", "MetaLogicAssembly.dll", "Assembly-CSharp.dll"];
var namespaces = ["IdunBattle.Configuration", "idun.meta", ""];
var found = null;

for (var ai = 0; ai < assemblies.length && !found; ai++) {
    for (var ni = 0; ni < namespaces.length && !found; ni++) {
        var cls = findClass(assemblies[ai], namespaces[ni], "AbilityConfiguration");
        if (cls) {
            found = {asm: assemblies[ai], ns: namespaces[ni], ptr: cls};
        }
    }
}

if (found) {
    send({t: "probe_class", name: "AbilityConfiguration", asm: found.asm, ns: found.ns});

    // Enumerate ALL fields (including inherited)
    var fields = [];
    var k = found.ptr;
    var depth = 0;
    while (!k.isNull() && depth < 5) {
        var it = Memory.alloc(Process.pointerSize);
        it.writePointer(ptr(0));
        var f;
        while (!(f = class_get_fields(k, it)).isNull()) {
            var fname = s(field_get_name(f));
            var foff = field_get_offset(f);
            fields.push({name: fname, offset: foff, depth: depth});
        }
        k = class_get_parent(k);
        depth++;
    }
    send({t: "probe_fields", className: "AbilityConfiguration", fields: fields});
} else {
    send({t: "probe_class", name: "AbilityConfiguration", found: false});
}

// Also probe StatefulAbilityConfiguration fields
var sacClass = findClass("MetaLogicAssembly.dll", "idun.meta", "StatefulAbilityConfiguration");
if (sacClass) {
    var sacFields = [];
    var k2 = sacClass;
    var depth2 = 0;
    while (!k2.isNull() && depth2 < 5) {
        var cname = s(class_get_name(k2));
        var it2 = Memory.alloc(Process.pointerSize);
        it2.writePointer(ptr(0));
        var f2;
        while (!(f2 = class_get_fields(k2, it2)).isNull()) {
            sacFields.push({name: s(field_get_name(f2)), offset: field_get_offset(f2),
                           class: cname, depth: depth2});
        }
        k2 = class_get_parent(k2);
        depth2++;
    }
    send({t: "probe_fields", className: "StatefulAbilityConfiguration", fields: sacFields});
}

// Also try to find AbilitiesConfiguration (the container)
var abcfg = findClass("BattleLogicAssembly.dll", "IdunBattle.Configuration", "AbilitiesConfiguration");
if (!abcfg) abcfg = findClass("MetaLogicAssembly.dll", "IdunBattle.Configuration", "AbilitiesConfiguration");
if (abcfg) {
    var abcfgFields = [];
    var k3 = abcfg;
    var it3 = Memory.alloc(Process.pointerSize);
    it3.writePointer(ptr(0));
    var f3;
    while (!(f3 = class_get_fields(k3, it3)).isNull()) {
        abcfgFields.push({name: s(field_get_name(f3)), offset: field_get_offset(f3)});
    }
    send({t: "probe_fields", className: "AbilitiesConfiguration", fields: abcfgFields});
} else {
    send({t: "probe_class", name: "AbilitiesConfiguration", found: false});
}

console.log("[*] Probe done");