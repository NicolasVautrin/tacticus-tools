// util: IL2CPP Object creation & method invocation
// requires: _utils/il2cpp-helpers
// provides: il2cpp_object_new(), il2cpp_runtime_invoke(), invokeMethod(), createObject()

var il2cpp_object_new = new NativeFunction(
    il2cpp.findExportByName("il2cpp_object_new"), "pointer", ["pointer"]);
var il2cpp_runtime_invoke = new NativeFunction(
    il2cpp.findExportByName("il2cpp_runtime_invoke"), "pointer",
    ["pointer", "pointer", "pointer", "pointer"]);

// Resolved once on first invocation that throws — lets us retrieve the
// managed Message + StackTrace from any caught IL2CPP exception.
var _exceptionGetMessageMi = null;
var _exceptionGetStackMi = null;
function _ensureExceptionAccessors() {
    if (_exceptionGetMessageMi && _exceptionGetStackMi) return;
    var excClass = findClass("mscorlib.dll", "System", "Exception");
    if (!excClass) return;
    _exceptionGetMessageMi = findMethod(excClass, "get_Message");
    _exceptionGetStackMi = findMethod(excClass, "get_StackTrace");
}
function _readManagedString(strPtr) {
    if (strPtr.isNull()) return null;
    try {
        var len = strPtr.add(0x10).readS32();
        if (len <= 0 || len > 100000) return null;
        return strPtr.add(0x14).readUtf16String(len);
    } catch (e) { return null; }
}

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
        var klassName = "?";
        try { klassName = s(class_get_name(excVal.readPointer())); } catch (e) {}
        var excMsg = "IL2CPP exception (" + klassName + ")";
        // Retrieve managed Message + StackTrace from the Exception object
        try {
            _ensureExceptionAccessors();
            if (_exceptionGetMessageMi) {
                var mp = il2cpp_runtime_invoke(_exceptionGetMessageMi.info, excVal,
                                               ptr(0), Memory.alloc(Process.pointerSize));
                var m = _readManagedString(mp);
                if (m) excMsg += ": " + m;
            }
            if (_exceptionGetStackMi) {
                var sp = il2cpp_runtime_invoke(_exceptionGetStackMi.info, excVal,
                                               ptr(0), Memory.alloc(Process.pointerSize));
                var st = _readManagedString(sp);
                if (st) excMsg += "\n" + st;
            }
        } catch (e) {}
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
