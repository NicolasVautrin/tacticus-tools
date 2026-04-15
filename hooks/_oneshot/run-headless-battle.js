// Oneshot: deserialize BattleConfiguration + run via AutomaticBattleRunner
// requires: _utils/il2cpp-helpers, _utils/il2cpp-invoke

function log(msg) { send({t: "log", msg: msg}); }

var method_get_param_count = new NativeFunction(
    il2cpp.findExportByName("il2cpp_method_get_param_count"), "uint32", ["pointer"]);
var il2cpp_string_new = new NativeFunction(
    il2cpp.findExportByName("il2cpp_string_new"), "pointer", ["pointer"]);
var il2cpp_class_get_type = new NativeFunction(
    il2cpp.findExportByName("il2cpp_class_get_type"), "pointer", ["pointer"]);
var il2cpp_type_get_object = new NativeFunction(
    il2cpp.findExportByName("il2cpp_type_get_object"), "pointer", ["pointer"]);
var il2cpp_thread_attach = new NativeFunction(
    il2cpp.findExportByName("il2cpp_thread_attach"), "pointer", ["pointer"]);
var il2cpp_domain_get = new NativeFunction(
    il2cpp.findExportByName("il2cpp_domain_get"), "pointer", []);

var _readLarge = function(p) {
    if (p.isNull()) return null;
    var len = p.add(0x10).readS32();
    if (len <= 0 || len > 5000000) return null;
    return p.add(0x14).readUtf16String(len);
};

// --- Classes ---
var bcClass = findClass("BattleLogicAssembly.dll", "IdunBattle.Configuration", "BattleConfiguration");
var abrClass = findClass("Assembly-CSharp.dll", "Runner", "AutomaticBattleRunner");
var abrCtor = findMethod(abrClass, ".ctor");
var abrRun = findMethod(abrClass, "Run");
var jsonConvertClass = findClass("Newtonsoft.Json.dll", "Newtonsoft.Json", "JsonConvert");

// Find DeserializeObject and SerializeObject — enumerate all overloads
var deserializeMethods = [];
var serializeMethod = null;
var method_get_param = new NativeFunction(
    il2cpp.findExportByName("il2cpp_method_get_param"), "pointer", ["pointer", "uint32"]);
var type_get_name_full = new NativeFunction(
    il2cpp.findExportByName("il2cpp_type_get_name"), "pointer", ["pointer"]);

(function() {
    var it = Memory.alloc(Process.pointerSize);
    it.writePointer(ptr(0));
    var m;
    while (!(m = class_get_methods(jsonConvertClass, it)).isNull()) {
        var name = s(method_get_name(m));
        var pc = method_get_param_count(m);
        if (name === "DeserializeObject") {
            var paramTypes = [];
            for (var i = 0; i < pc; i++) {
                var pt = method_get_param(m, i);
                paramTypes.push(s(type_get_name_full(pt)));
            }
            log("DeserializeObject(" + paramTypes.join(", ") + ") — " + pc + " params");
            deserializeMethods.push({info: m, params: paramTypes, count: pc});
        }
        if (name === "SerializeObject" && pc === 1 && !serializeMethod) {
            serializeMethod = m;
        }
    }
})();

// Pick the right overload: DeserializeObject(string, Type)
var deserializeMethod = null;
for (var i = 0; i < deserializeMethods.length; i++) {
    var dm = deserializeMethods[i];
    if (dm.count === 2 && dm.params[0] === "System.String" && dm.params[1] === "System.Type") {
        deserializeMethod = dm.info;
        log("Selected: DeserializeObject(String, Type)");
        break;
    }
}
if (!deserializeMethod && deserializeMethods.length > 0) {
    // Try 3-param with Type
    for (var i = 0; i < deserializeMethods.length; i++) {
        var dm = deserializeMethods[i];
        if (dm.count === 3 && dm.params[1] === "System.Type") {
            deserializeMethod = dm.info;
            log("Selected: DeserializeObject(" + dm.params.join(", ") + ")");
            break;
        }
    }
}
log("DeserializeObject: " + (deserializeMethod ? "found" : "NOT FOUND"));
log("SerializeObject: " + (serializeMethod ? "found" : "NOT FOUND"));

// --- Runner fields ---
var runnerClass = findClass("BattleLogicAssembly.dll", "IdunBattle.Runner", "IdunRunner");
var loggerOff = getFieldOffset(runnerClass, "_logger");
var timeSourceOff = getFieldOffset(runnerClass, "_timeSource");

// --- Capture runner ---
var gameViewsClass = findClass("Assembly-CSharp.dll", "IdunBattle.View.Game", "IdunGameViews");
var gvRunnerOff = getFieldOffset(gameViewsClass, "_runner");
var updateMethod = findMethod(gameViewsClass, "Update");
var originalUpdate = new NativeFunction(updateMethod.ptr, "void", ["pointer", "pointer"]);

var _logger = null;
var _timeSource = null;
var _captured = false;

Interceptor.replace(updateMethod.ptr, new NativeCallback(function(self, mi) {
    originalUpdate(self, mi);
    if (_captured) return;
    var runner = self.add(gvRunnerOff).readPointer();
    if (runner.isNull()) return;
    _captured = true;
    _logger = runner.add(loggerOff).readPointer();
    _timeSource = runner.add(timeSourceOff).readPointer();
    log("Runner captured — logger:" + _logger + " timeSource:" + _timeSource);
    send({t: "ready_for_json"});
}, "void", ["pointer", "pointer"]));

// --- Receive JSON and run battle ---
recv("inject_json", function(message) {
    var jsonStr = message.payload;
    log("Received JSON: " + jsonStr.length + " chars");

    // Attach this thread to IL2CPP
    var domain = il2cpp_domain_get();
    il2cpp_thread_attach(domain);

    try {
        // 1. Create IL2CPP string
        var il2str = il2cpp_string_new(Memory.allocUtf8String(jsonStr));
        log("IL2CPP string created");

        // 2. Get Type object for BattleConfiguration
        var bcType = il2cpp_class_get_type(bcClass);
        var bcTypeObj = il2cpp_type_get_object(bcType);
        log("Type object: " + bcTypeObj);

        // 3. Deserialize
        log("Deserializing...");
        var config = invokeMethod(deserializeMethod, ptr(0), [il2str, bcTypeObj, ptr(0)]);
        if (config.isNull()) { log("ERROR: Deserialize returned null"); return; }

        var idPtr = config.add(0x10).readPointer();
        log("Deserialized config Id: " + (idPtr.isNull() ? "null" : readIl2cppString(idPtr)));

        var unitsList = config.add(0x78).readPointer();
        var unitsCount = unitsList.isNull() ? 0 : unitsList.add(0x18).readS32();
        log("Units: " + unitsCount);

        // 4. Create AutomaticBattleRunner via runtime_invoke
        log("Creating AutomaticBattleRunner...");
        var abr = il2cpp_object_new(abrClass);

        // .ctor(logger, config, maxTurns, findReplayBugs, validate, timeSource)
        // runtime_invoke boxes primitives automatically
        var maxTurns = il2cpp_object_new(findClass("mscorlib.dll", "System", "Int32"));
        maxTurns.add(0x10).writeS32(200);
        var boolFalse = il2cpp_object_new(findClass("mscorlib.dll", "System", "Boolean"));
        boolFalse.add(0x10).writeU8(0);

        invokeMethod(abrCtor.info, abr, [_logger, config, maxTurns, boolFalse, boolFalse, _timeSource]);
        log("AutomaticBattleRunner created, running...");

        // 5. Run
        var t0 = Date.now();
        var result = invokeMethod(abrRun.info, abr, null);
        var elapsed = Date.now() - t0;
        log("Battle completed in " + elapsed + "ms");

        if (!result.isNull()) {
            // Read RunTimeInMs at offset 0x30
            var runTime = result.add(0x30).readS64();
            log("Result.RunTimeInMs: " + runTime);

            // Check exception at 0x38
            var exc = result.add(0x38).readPointer();
            log("Result.Exception: " + (exc.isNull() ? "none" : "HAS EXCEPTION"));

            // Serialize result with JsonConvert and send full result
            try {
                var resultJsonPtr = invokeMethod(serializeMethod, ptr(0), [result]);
                if (!resultJsonPtr.isNull()) {
                    var resultJson = _readLarge(resultJsonPtr);
                    if (resultJson) {
                        log("Result serialized: " + resultJson.length + " chars, sending...");
                        var CHUNK = 8000;
                        var chunks = Math.ceil(resultJson.length / CHUNK);
                        for (var ci = 0; ci < chunks; ci++) {
                            send({t: "battle_result_chunk", chunk: ci, total: chunks,
                                  data: resultJson.substring(ci * CHUNK, (ci + 1) * CHUNK)});
                        }
                        log("Sent " + chunks + " result chunks");
                    }
                }
            } catch(e) {
                log("Result serialization failed: " + e.message);
            }
        }
    } catch(e) {
        log("ERROR: " + e.message);
    }
});

log("run-headless-battle: loaded. Enter a battle to capture runner.");
