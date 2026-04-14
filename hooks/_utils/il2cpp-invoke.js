// util: IL2CPP Object creation & method invocation
// requires: _utils/il2cpp-helpers
// provides: il2cpp_object_new(), il2cpp_runtime_invoke(), invokeMethod(), createObject()

var il2cpp_object_new = new NativeFunction(
    il2cpp.findExportByName("il2cpp_object_new"), "pointer", ["pointer"]);
var il2cpp_runtime_invoke = new NativeFunction(
    il2cpp.findExportByName("il2cpp_runtime_invoke"), "pointer",
    ["pointer", "pointer", "pointer", "pointer"]);

function invokeMethod(methodInfo, obj, args) {
    var exc = Memory.alloc(Process.pointerSize);
    exc.writePointer(ptr(0));
    var params = ptr(0);
    if (args && args.length > 0) {
        params = Memory.alloc(args.length * Process.pointerSize);
        for (var i = 0; i < args.length; i++) {
            params.add(i * Process.pointerSize).writePointer(args[i]);
        }
    }
    var result = il2cpp_runtime_invoke(methodInfo, obj, params, exc);
    var excVal = exc.readPointer();
    if (!excVal.isNull()) {
        var excMsg = "IL2CPP exception";
        try {
            excMsg += " (" + s(class_get_name(excVal.readPointer())) + ")";
        } catch(e) {}
        throw new Error(excMsg);
    }
    return result;
}

function createObject(klass) {
    var obj = il2cpp_object_new(klass);
    if (obj.isNull()) throw new Error("il2cpp_object_new returned null");
    var ctor = findMethod(klass, ".ctor");
    if (ctor) invokeMethod(ctor.info, obj, null);
    return obj;
}

console.log("[*] IL2CPP invoke loaded");
