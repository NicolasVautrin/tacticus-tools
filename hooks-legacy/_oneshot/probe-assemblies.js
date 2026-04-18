// Probe: list all IL2CPP assemblies on the running app
// Emits: {t:"assemblies", names:[...]}

var il2cpp = Process.findModuleByName("libil2cpp.so");
var domain_get = new NativeFunction(il2cpp.findExportByName("il2cpp_domain_get"), "pointer", []);
var domain_get_assemblies = new NativeFunction(il2cpp.findExportByName("il2cpp_domain_get_assemblies"), "pointer", ["pointer", "pointer"]);
var assembly_get_image = new NativeFunction(il2cpp.findExportByName("il2cpp_assembly_get_image"), "pointer", ["pointer"]);
var image_get_name = new NativeFunction(il2cpp.findExportByName("il2cpp_image_get_name"), "pointer", ["pointer"]);
var image_get_class_count = new NativeFunction(il2cpp.findExportByName("il2cpp_image_get_class_count"), "uint32", ["pointer"]);
var image_get_class = new NativeFunction(il2cpp.findExportByName("il2cpp_image_get_class"), "pointer", ["pointer", "uint32"]);
var class_get_name = new NativeFunction(il2cpp.findExportByName("il2cpp_class_get_name"), "pointer", ["pointer"]);
var class_get_namespace = new NativeFunction(il2cpp.findExportByName("il2cpp_class_get_namespace"), "pointer", ["pointer"]);

function s(p) { try { return p.readUtf8String() || ""; } catch(e) { return ""; } }

var domain = domain_get();
var sizePtr = Memory.alloc(4);
var assemblies = domain_get_assemblies(domain, sizePtr);
var count = sizePtr.readU32();

var result = [];
var objectHits = [];    // assemblies containing a class named "System.Object"
var arrayListHits = []; // assemblies containing "ArrayList"

for (var i = 0; i < count; i++) {
    var asm = assemblies.add(i * Process.pointerSize).readPointer();
    var img = assembly_get_image(asm);
    var name = s(image_get_name(img));
    var cc = image_get_class_count(img);
    result.push({ name: name, classes: cc });

    // Scan for System.Object / ArrayList — useful to find the right assembly name
    for (var j = 0; j < cc; j++) {
        var k = image_get_class(img, j);
        var cn = s(class_get_name(k));
        var ns = s(class_get_namespace(k));
        if (cn === "Object" && ns === "System") objectHits.push(name);
        if (cn === "ArrayList" && ns === "System.Collections") arrayListHits.push(name);
    }
}

send({ t: "assemblies", count: count, list: result, objectIn: objectHits, arrayListIn: arrayListHits });
