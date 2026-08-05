import { findClass, findMethod, s, class_get_name, class_get_methods, method_get_name, method_get_param_count, methodEntry, findClassAnywhere, getSystemType } from "../il2cpp/helpers.js";
import { invokeMethod, createManagedString } from "../il2cpp/invoke.js";
import { queueOnMainThread } from "../runtime/queue.js";
import { log } from "../runtime/diag.js";
import { Ctx } from "../controller.js";

export function registerTestScene(ctx: Ctx): void {
    ctx.rpc.testScene = () => {
        return queueOnMainThread(() => {
            log("[test-scene] Starting scene hierarchy inspection...");

            const smKlass = findClass("UnityEngine.CoreModule.dll", "UnityEngine.SceneManagement", "SceneManager");
            if (!smKlass) {
                log("[test-scene] SceneManager class not found!");
                return { error: "SceneManager not found" };
            }

            const sceneKlass = findClass("UnityEngine.CoreModule.dll", "UnityEngine.SceneManagement", "Scene");
            if (!sceneKlass) {
                log("[test-scene] Scene class not found!");
                return { error: "Scene not found" };
            }

            const goKlass = findClass("UnityEngine.CoreModule.dll", "UnityEngine", "GameObject");
            if (!goKlass) {
                log("[test-scene] GameObject class not found!");
                return { error: "GameObject not found" };
            }

            const uoKlass = findClass("UnityEngine.CoreModule.dll", "UnityEngine", "Object");
            if (!uoKlass) {
                log("[test-scene] UnityEngine.Object class not found!");
                return { error: "UnityEngine.Object not found" };
            }

            const transKlass = findClass("UnityEngine.CoreModule.dll", "UnityEngine", "Transform");
            if (!transKlass) {
                log("[test-scene] Transform class not found!");
                return { error: "Transform not found" };
            }

            const compKlass = findClass("UnityEngine.CoreModule.dll", "UnityEngine", "Component");
            if (!compKlass) {
                log("[test-scene] Component class not found!");
                return { error: "Component not found" };
            }

            // Methods
            const getSceneCountMi = findMethod(smKlass, "get_sceneCount");
            const getSceneAtMi = findMethod(smKlass, "GetSceneAt");
            const getRootGameObjectsMi = findMethod(sceneKlass, "GetRootGameObjects");
            const sceneGetNameMi = findMethod(sceneKlass, "get_name");

            const uoGetNameMi = findMethod(uoKlass, "get_name");
            const goGetTransformMi = findMethod(goKlass, "get_transform");
            const transGetChildCountMi = findMethod(transKlass, "get_childCount");
            const transGetChildMi = findMethod(transKlass, "GetChild");
            const transGetGameObjectMi = findMethod(compKlass, "get_gameObject");

            // Look up all GetComponent(Type) and GetComponent(string) on GameObject (which take 1 parameter)
            function findAllMethodsByParamCount(klass: NativePointer, name: string, paramCount: number) {
                const it = Memory.alloc(Process.pointerSize);
                it.writePointer(ptr(0));
                let m: NativePointer;
                const results: any[] = [];
                while (!(m = class_get_methods(klass, it) as NativePointer).isNull()) {
                    const mName = s(method_get_name(m) as NativePointer);
                    if (mName === name) {
                        try {
                            const pCount = method_get_param_count(m) as number;
                            log(`[test-scene] Found overload: ${name} with ${pCount} parameters (methodInfo: ${m})`);
                            if (pCount === paramCount) {
                                results.push({ info: m, ptr: methodEntry(m) });
                            }
                        } catch (e) {
                            log(`[test-scene] Error inspecting overload: ${(e as Error).message}`);
                        }
                    }
                }
                return results;
            }

            const goGetComponentMis = findAllMethodsByParamCount(goKlass, "GetComponent", 1);
            log(`[test-scene] GameObject.GetComponent overloads found: ${goGetComponentMis.length}`);

            log(`[test-scene] Listing Find methods on UnityEngine.Object...`);
            const uoMethodsIt = Memory.alloc(Process.pointerSize);
            uoMethodsIt.writePointer(ptr(0));
            let uoM: NativePointer;
            while (!(uoM = class_get_methods(uoKlass, uoMethodsIt) as NativePointer).isNull()) {
                const uoMName = s(method_get_name(uoM) as NativePointer);
                if (uoMName.includes("Find")) {
                    log(`[test-scene]   Found UnityEngine.Object method: ${uoMName} (param count: ${method_get_param_count(uoM)}) (methodInfo: ${uoM})`);
                }
            }

            log(`[test-scene] getSceneCountMi: ${getSceneCountMi ? "OK" : "MISSING"}`);
            log(`[test-scene] getSceneAtMi: ${getSceneAtMi ? "OK" : "MISSING"}`);
            log(`[test-scene] getRootGameObjectsMi: ${getRootGameObjectsMi ? "OK" : "MISSING"}`);
            log(`[test-scene] sceneGetNameMi: ${sceneGetNameMi ? "OK" : "MISSING"}`);
            log(`[test-scene] uoGetNameMi: ${uoGetNameMi ? "OK" : "MISSING"}`);
            log(`[test-scene] goGetTransformMi: ${goGetTransformMi ? "OK" : "MISSING"}`);
            log(`[test-scene] transGetChildCountMi: ${transGetChildCountMi ? "OK" : "MISSING"}`);
            log(`[test-scene] transGetChildMi: ${transGetChildMi ? "OK" : "MISSING"}`);
            log(`[test-scene] transGetGameObjectMi: ${transGetGameObjectMi ? "OK" : "MISSING"}`);

            if (!getSceneCountMi || !getSceneAtMi || !getRootGameObjectsMi || !sceneGetNameMi || !uoGetNameMi ||
                !goGetTransformMi || !transGetChildCountMi || !transGetChildMi || !transGetGameObjectMi) {
                log("[test-scene] Required Unity methods not found!");
                return { error: "Unity methods not found" };
            }

            // Direct Type-based Lookup of IdunNavigation using Unity engine FindFirstObjectByType
            const navKlass = findClassAnywhere("idun.UI", "IdunNavigation");
            if (navKlass) {
                log(`[test-scene] IdunNavigation class found @ ${navKlass}`);
                try {
                    const navType = getSystemType(navKlass);
                    log(`[test-scene] IdunNavigation System.Type: ${navType}`);

                    const findFirstObjectByTypeOverloads = findAllMethodsByParamCount(uoKlass, "FindFirstObjectByType", 1);
                    log(`[test-scene] FindFirstObjectByType overloads with 1 param found: ${findFirstObjectByTypeOverloads.length}`);
                    
                    for (let idx = 0; idx < findFirstObjectByTypeOverloads.length; idx++) {
                        const mi = findFirstObjectByTypeOverloads[idx];
                        try {
                            log(`[test-scene] Attempting FindFirstObjectByType overload [${idx}] (methodInfo: ${mi.info})...`);
                            const inst = invokeMethod(mi.info, null, [navType]);
                            log(`[test-scene] FindFirstObjectByType overload [${idx}] result: ${inst}`);
                            if (!inst.isNull()) {
                                log(`[test-scene] SUCCESS! Discovered active IdunNavigation instance: ${inst}`);
                            }
                        } catch (e) {
                            log(`[test-scene] FindFirstObjectByType overload [${idx}] failed: ${(e as Error).message}`);
                        }
                    }
                } catch (e) {
                    log(`[test-scene] Direct IdunNavigation lookup failed: ${(e as Error).message}`);
                }
            }

            function getObjectName(objPtr: NativePointer): string {
                try {
                    const nameStr = invokeMethod(uoGetNameMi!.info, objPtr, []);
                    if (!nameStr.isNull()) {
                        const len = nameStr.add(0x10).readS32();
                        return nameStr.add(0x14).readUtf16String(len) || "empty_name";
                    }
                } catch (e) {
                    // Ignore
                }
                return "unknown";
            }

            function traverseTransform(transPtr: NativePointer, depth: number, prefix: string): void {
                if (transPtr.isNull()) return;

                const goPtr = invokeMethod(transGetGameObjectMi!.info, transPtr, []);
                if (goPtr.isNull()) return;

                const name = getObjectName(goPtr);
                const classPtr = goPtr.readPointer();
                let className = "GameObject";
                try {
                    className = s(class_get_name(classPtr) as NativePointer);
                } catch {}

                log(`[test-scene] ${prefix}- GO: "${name}" @ ${goPtr} (class: ${className})`);

                // Check for Navigation component or interesting name
                if (name.toLowerCase().includes("navigation") || name.toLowerCase().includes("idun")) {
                    log(`[test-scene]   *** MATCH: Found interesting GameObject: "${name}" @ ${goPtr}`);
                    
                    const componentNameStr = createManagedString("IdunNavigation");
                    for (let idx = 0; idx < goGetComponentMis.length; idx++) {
                        const mi = goGetComponentMis[idx];
                        try {
                            log(`[test-scene]   Attempting GetComponent overload [${idx}] (methodInfo: ${mi.info}) on ${goPtr}...`);
                            const compPtr = invokeMethod(mi.info, goPtr, [componentNameStr]);
                            log(`[test-scene]   GetComponent overload [${idx}] result: ${compPtr}`);
                            if (!compPtr.isNull()) {
                                const compKlassPtr = compPtr.readPointer();
                                const compKlassName = s(class_get_name(compKlassPtr) as NativePointer);
                                log(`[test-scene]   Successfully found component of type: ${compKlassName} @ ${compPtr}!`);
                            }
                        } catch (e) {
                            log(`[test-scene]   GetComponent overload [${idx}] failed: ${(e as Error).message}`);
                        }
                    }
                }

                try {
                    const childCountPtr = invokeMethod(transGetChildCountMi!.info, transPtr, []);
                    if (!childCountPtr.isNull()) {
                        log(`[test-scene]   childCountPtr: ${childCountPtr}`);
                        // Dump memory if it looks like a valid pointer
                        if (childCountPtr.compare(ptr("0x10000")) > 0) {
                            try {
                                log(`[test-scene]   childCountPtr MemDump:\n${hexdump(childCountPtr, { length: 32 })}`);
                            } catch (he) {
                                log(`[test-scene]   Failed to hexdump childCountPtr: ${(he as Error).message}`);
                            }
                        }
                        
                        const childCount = childCountPtr.add(0x10).readS32();
                        log(`[test-scene]   childCount (offset 0x10): ${childCount}`);
                        
                        // Also try to read it as a raw integer if it's a tiny pointer value
                        let rawVal: number = -1;
                        if (childCountPtr.compare(ptr("0x10000")) < 0) {
                            rawVal = childCountPtr.toInt32();
                            log(`[test-scene]   childCountPtr looks like raw value: ${rawVal}`);
                        }

                        const effectiveChildCount = rawVal !== -1 ? rawVal : childCount;
                        if (effectiveChildCount > 0 && effectiveChildCount < 1000) { // Safety guard
                            for (let i = 0; i < effectiveChildCount; i++) {
                                const indexVal = Memory.alloc(4).writeS32(i);
                                const childTransPtr = invokeMethod(transGetChildMi!.info, transPtr, [indexVal]);
                                traverseTransform(childTransPtr, depth + 1, prefix + "  ");
                            }
                        }
                    }
                } catch (e) {
                    log(`[test-scene] Error traversing children: ${(e as Error).message}`);
                }
            }

            try {
                const sceneCountPtr = invokeMethod(getSceneCountMi.info, null, []);
                if (sceneCountPtr.isNull()) {
                    log("[test-scene] sceneCountPtr is NULL");
                    return { error: "sceneCount is null" };
                }
                const sceneCount = sceneCountPtr.add(0x10).readS32();
                log(`[test-scene] Total loaded scenes: ${sceneCount}`);

                if (sceneCount < 0 || sceneCount > 100) {
                    log("[test-scene] Invalid scene count");
                    return { error: "Invalid scene count" };
                }

                for (let i = 0; i < sceneCount; i++) {
                    const indexVal = Memory.alloc(4).writeS32(i);
                    const sceneStruct = invokeMethod(getSceneAtMi.info, null, [indexVal]);
                    if (sceneStruct.isNull()) continue;

                    // Get scene name
                    let sceneName = "unknown";
                    try {
                        const nameStr = invokeMethod(sceneGetNameMi.info, sceneStruct.add(0x10), []);
                        if (!nameStr.isNull()) {
                            const len = nameStr.add(0x10).readS32();
                            sceneName = nameStr.add(0x14).readUtf16String(len) || "";
                        }
                    } catch (e) {
                        log(`[test-scene] Error reading scene name for index ${i}: ${(e as Error).message}`);
                    }

                    log(`[test-scene] Scene [${i}]: "${sceneName}"`);

                    // Get root game objects
                    let rootArray: NativePointer = ptr(0);
                    try {
                        rootArray = invokeMethod(getRootGameObjectsMi.info, sceneStruct.add(0x10), []);
                    } catch (e) {
                        log(`[test-scene] GetRootGameObjects failed for scene "${sceneName}": ${(e as Error).message}`);
                    }

                    if (!rootArray.isNull()) {
                        const len = rootArray.add(0x18).readS32();
                        log(`[test-scene]   Root GameObjects count: ${len}`);
                        for (let r = 0; r < len; r++) {
                            const goPtr = rootArray.add(0x20 + r * Process.pointerSize).readPointer();
                            if (goPtr.isNull()) continue;

                            const transPtr = invokeMethod(goGetTransformMi.info, goPtr, []);
                            traverseTransform(transPtr, 0, "    ");
                        }
                    }
                }

            } catch (e) {
                log(`[test-scene] Error during traversal: ${(e as Error).message}`);
            }

            return { ok: true };
        });
    };
}
