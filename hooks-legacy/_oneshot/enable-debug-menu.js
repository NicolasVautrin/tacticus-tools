// oneshot: Enable debug menu and battle cheats
// requires: _utils/il2cpp-helpers
//
// Patches BuildSettings flags in memory and replaces SettingsPopup.OnVersionClicked
// to bypass password entry. Must be injected after game has loaded.
//
// Compose:
//   cat _utils/il2cpp-helpers.js _oneshot/enable-debug-menu.js > scripts/enable-debug-composed.js

// --- Extra IL2CPP imports not in il2cpp-helpers ---
var field_static_get_value = new NativeFunction(
    il2cpp.findExportByName("il2cpp_field_static_get_value"), "void", ["pointer", "pointer"]);

// ============================================================
// Step 1: Patch BuildSettings flags in memory
// ============================================================

var globalsClass = findClass("Assembly-CSharp.dll", "thor", "Globals");
if (!globalsClass) {
    console.log("[-] thor.Globals not found");
} else {
    var it = Memory.alloc(Process.pointerSize);
    it.writePointer(ptr(0));
    var globalsField = null;
    var f;
    while (!(f = class_get_fields(globalsClass, it)).isNull()) {
        if (s(field_get_name(f)) === "globals") { globalsField = f; break; }
    }

    if (!globalsField) {
        console.log("[-] thor.Globals.globals field not found");
    } else {
        var globalsPtr = Memory.alloc(Process.pointerSize);
        field_static_get_value(globalsField, globalsPtr);
        var globalsInstance = globalsPtr.readPointer();

        if (globalsInstance.isNull()) {
            console.log("[-] thor.Globals singleton is null");
        } else {
            console.log("[+] thor.Globals at " + globalsInstance);

            var bsOff = getFieldOffset(globalsClass, "_buildSettings");
            if (bsOff >= 0) {
                var buildSettings = globalsInstance.add(bsOff).readPointer();
                if (!buildSettings.isNull()) {
                    console.log("[+] BuildSettings at " + buildSettings);
                    var bsClass = findClass("Assembly-CSharp.dll", "thor.Scripts", "BuildSettings");
                    if (bsClass) {
                        var flags = [
                            "allowCheatMode",       // 0x5C
                            "allowOpeningDebugMenu", // 0x5D
                            "allowBattleCheats",     // 0x5E
                            "showDebugSettings",     // 0x29
                            "ShowFullDebugMenu",     // 0x2D
                            "debugSettingsUnlocked"  // 0xC8
                        ];
                        var patched = 0;
                        flags.forEach(function(name) {
                            var off = getFieldOffset(bsClass, name);
                            if (off >= 0) {
                                var prev = buildSettings.add(off).readU8();
                                buildSettings.add(off).writeU8(1);
                                console.log("[+] " + name + ": " + prev + " -> 1");
                                patched++;
                            }
                        });
                        console.log("[+] Patched " + patched + "/" + flags.length + " flags");
                    }
                }
            }
        }
    }
}

// ============================================================
// Step 2: Replace SettingsPopup.OnVersionClicked
//         to call the unlock lambda directly (skip password)
// ============================================================
// SettingsPopup.OnVersionClicked  — RVA: 0x2348528
// <OnVersionClicked>b__67_0       — RVA: 0x2348A48 (the unlock callback lambda)
// SettingsPopup._debugSettingsMenuLock — offset 0x1C0

var _onVersionClickedPtr = il2cppBase.add(0x2348528);
var _lambdaPtr = il2cppBase.add(0x2348A48);
var _origOnVersionClicked = new NativeFunction(_onVersionClickedPtr, 'void', ['pointer', 'pointer']);
var _lambdaFn = new NativeFunction(_lambdaPtr, 'void', ['pointer', 'pointer']);

Interceptor.replace(_onVersionClickedPtr, new NativeCallback(function(self, methodInfo) {
    console.log("[*] OnVersionClicked — calling unlock lambda directly");
    try {
        _lambdaFn(self, ptr(0));
        console.log("[+] Debug menu should be opening!");
    } catch (e) {
        console.log("[!] Lambda call failed: " + e.message);
    }
}, 'void', ['pointer', 'pointer']));
console.log("[+] SettingsPopup.OnVersionClicked replaced");

// ============================================================
// Step 3: Hook IsDebugSettingsEnabled to return true
// ============================================================

hook("Assembly-CSharp.dll", "thor.Scripts", "BuildSettings", "IsDebugSettingsEnabled", {
    onLeave: function(retval) {
        retval.replace(ptr(1));
    }
});

console.log("[*] Debug menu enabler loaded — tap version number in Settings");