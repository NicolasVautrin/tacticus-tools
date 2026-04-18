// Oneshot: capture BattleConfiguration from active battle
// requires: _utils/il2cpp-helpers, _utils/il2cpp-invoke, _utils/il2cpp-serializer
//
// Grabs runner from GameViews.Update, then serializes
// BattleConfiguration via Newtonsoft JsonConvert.SerializeObject

function log(msg) { send({t: "log", msg: msg}); }

var method_get_param_count = new NativeFunction(
    il2cpp.findExportByName("il2cpp_method_get_param_count"), "uint32", ["pointer"]);

// Override readIl2cppString with a version that handles large strings
var _readIl2cppStringLarge = function(objPtr) {
    if (objPtr.isNull()) return null;
    try {
        var len = objPtr.add(0x10).readS32();
        if (len <= 0 || len > 2000000) return null;
        return objPtr.add(0x14).readUtf16String(len);
    } catch (e) { return null; }
};

// --- Find runner via GameViews ---
var gameViewsClass = findClass("Assembly-CSharp.dll", "IdunBattle.View.Game", "IdunGameViews");
var gvRunnerOff = getFieldOffset(gameViewsClass, "_runner");
var updateMethod = findMethod(gameViewsClass, "Update");

// --- Runner config offset ---
var runnerClass = findClass("BattleLogicAssembly.dll", "IdunBattle.Runner", "IdunRunner");
var configOff = getFieldOffset(runnerClass, "<Configuration>k__BackingField");

// --- Find JsonConvert.SerializeObject via IL2CPP ---
// Try common DLL names for Newtonsoft
var jsonConvertClass = null;
var dllNames = ["Newtonsoft.Json.dll", "Assembly-CSharp.dll", "netstandard.dll"];
for (var i = 0; i < dllNames.length; i++) {
    jsonConvertClass = findClass(dllNames[i], "Newtonsoft.Json", "JsonConvert");
    if (jsonConvertClass) {
        log("Found JsonConvert in " + dllNames[i]);
        break;
    }
}

var serializeMethodInfo = null;
if (jsonConvertClass) {
    // Enumerate methods to find SerializeObject(object)
    var it = Memory.alloc(Process.pointerSize);
    it.writePointer(ptr(0));
    var m;
    while (!(m = class_get_methods(jsonConvertClass, it)).isNull()) {
        var mName = s(method_get_name(m));
        if (mName === "SerializeObject") {
            // Check param count — we want the simplest (1 param)
            var paramCount = method_get_param_count(m);
            log("Found SerializeObject with " + paramCount + " params");
            if (paramCount === 1) {
                serializeMethodInfo = m;
                log("Using SerializeObject(object) — 1 param");
                break;
            }
            if (paramCount === 2 && !serializeMethodInfo) {
                serializeMethodInfo = m;  // keep as fallback
            }
        }
    }
}

if (!serializeMethodInfo) {
    log("WARN: JsonConvert.SerializeObject not found, will use fallback");
}

function sendJson(jsonStr, source) {
    var CHUNK = 8000;
    var chunks = Math.ceil(jsonStr.length / CHUNK);
    for (var i = 0; i < chunks; i++) {
        send({
            t: "battle_config_json",
            source: source,
            chunk: i,
            total: chunks,
            data: jsonStr.substring(i * CHUNK, (i + 1) * CHUNK)
        });
    }
    log("Sent " + chunks + " chunks (" + source + ", " + jsonStr.length + " chars)");
}

var originalUpdate = new NativeFunction(updateMethod.ptr, "void", ["pointer", "pointer"]);
var captured = false;

Interceptor.replace(updateMethod.ptr, new NativeCallback(function(self, methodInfo) {
    originalUpdate(self, methodInfo);

    if (captured) return;

    var runner = self.add(gvRunnerOff).readPointer();
    if (runner.isNull()) return;

    captured = true;
    log("Runner captured");

    var battleConfig = runner.add(configOff).readPointer();
    if (battleConfig.isNull()) {
        log("BattleConfiguration is null");
        return;
    }

    var idPtr = battleConfig.add(0x10).readPointer();
    log("Config.Id: " + (idPtr.isNull() ? "null" : readIl2cppString(idPtr)));

    // --- Serialize via invokeMethod ---
    if (serializeMethodInfo) {
        try {
            log("Calling JsonConvert.SerializeObject via runtime_invoke...");
            var result = invokeMethod(serializeMethodInfo, ptr(0), [battleConfig]);
            if (!result.isNull()) {
                var strLen = result.add(0x10).readS32();
                log("JsonConvert returned string of length " + strLen);
                var jsonStr = _readIl2cppStringLarge(result);
                if (jsonStr && jsonStr.length > 0) {
                    log("JsonConvert SUCCESS — " + jsonStr.length + " chars");
                    sendJson(jsonStr, "newtonsoft");
                    return;
                }
                log("readIl2cppString returned null for len=" + strLen);
            }
            log("JsonConvert returned null");
        } catch(e) {
            log("JsonConvert exception: " + e.message);
        }
    }
}, "void", ["pointer", "pointer"]));

log("capture-battle-config: hooked Update, enter a battle...");
