// Generic UI navigation engine — walks every live UnityEngine.UI.Button via
// Object.FindObjectsByType, exposes them by full hierarchy path, and clicks
// via Button.onClick.Invoke() (the same UnityEvent the game fires on a real
// pointer click). All work runs on Unity's main thread via queueOnMainThread.
//
// Scope (v1): UnityEngine.UI.Button only. Filtered to interactable & active.
// Path matching: full strict — uiClick("Canvas/Menu/PlayButton") must match
// the assembled path exactly (case-sensitive).

import {
    findClassAnywhere, findMethod, methodEntry,
    class_get_methods, method_get_name, method_get_param_count,
    s as cstr, readIl2cppString, getSystemType, MethodRef,
    IL2CPP_MODULE_NAME,
} from "../il2cpp/helpers.js";
import { invokeMethod } from "../il2cpp/invoke.js";
import { queueOnMainThread } from "../runtime/queue.js";
import { log } from "../runtime/diag.js";
import { Ctx } from "../controller.js";

// --- Resolved IL2CPP refs, populated lazily on first RPC call ---

interface UiRefs {
    objectK: NativePointer;
    componentK: NativePointer;
    transformK: NativePointer;
    behaviourK: NativePointer;
    selectableK: NativePointer;
    buttonK: NativePointer;
    unityEventK: NativePointer;

    findObjectsByType: MethodRef;
    objectGetName: MethodRef;
    componentGetGameObject: MethodRef;
    componentGetTransform: MethodRef;
    transformGetParent: MethodRef;
    behaviourGetActiveAndEnabled: MethodRef;
    selectableGetInteractable: MethodRef;
    buttonGetOnClick: MethodRef;
    unityEventInvoke: MethodRef;
    buttonSystemType: NativePointer; // typeof(UnityEngine.UI.Button)
}

let _refs: UiRefs | null = null;

export type { UiRefs };

function findMethodByParamCount(
    klass: NativePointer, name: string, paramCount: number,
): MethodRef | null {
    const it = Memory.alloc(Process.pointerSize);
    it.writePointer(ptr(0));
    let m: NativePointer;
    while (!(m = class_get_methods(klass, it) as NativePointer).isNull()) {
        if (cstr(method_get_name(m) as NativePointer) !== name) continue;
        try {
            if ((method_get_param_count(m) as number) === paramCount) {
                return { info: m, ptr: methodEntry(m) };
            }
        } catch { /* skip */ }
    }
    return null;
}

function need<T>(v: T | null, what: string): T {
    if (v === null) {
        throw new Error(`ui-nav: ${what} not found in IL2CPP image`);
    }
    return v;
}

export function ensureRefs(): UiRefs {
    if (_refs) return _refs;

    const objectK = need(findClassAnywhere("UnityEngine", "Object"),
                         "UnityEngine.Object");
    const componentK = need(findClassAnywhere("UnityEngine", "Component"),
                            "UnityEngine.Component");
    const transformK = need(findClassAnywhere("UnityEngine", "Transform"),
                            "UnityEngine.Transform");
    const behaviourK = need(findClassAnywhere("UnityEngine", "Behaviour"),
                            "UnityEngine.Behaviour");
    const selectableK = need(findClassAnywhere("UnityEngine.UI", "Selectable"),
                             "UnityEngine.UI.Selectable");
    const buttonK = need(findClassAnywhere("UnityEngine.UI", "Button"),
                         "UnityEngine.UI.Button");
    const unityEventK = need(
        findClassAnywhere("UnityEngine.Events", "UnityEvent"),
        "UnityEngine.Events.UnityEvent");

    // FindObjectsByType has multiple overloads. We want the non-generic
    // 2-param form: (Type, FindObjectsSortMode). Walk all 2-param matches
    // and pick the one whose first param is System.Type.
    const findObjectsByType = need(
        pickFindObjectsByType(objectK),
        "Object.FindObjectsByType(Type, FindObjectsSortMode)");

    const objectGetName = need(findMethod(objectK, "get_name"),
                               "Object.get_name");
    const componentGetGameObject = need(
        findMethod(componentK, "get_gameObject"), "Component.get_gameObject");
    const componentGetTransform = need(
        findMethod(componentK, "get_transform"), "Component.get_transform");
    const transformGetParent = need(findMethod(transformK, "get_parent"),
                                    "Transform.get_parent");
    const behaviourGetActiveAndEnabled = need(
        findMethod(behaviourK, "get_isActiveAndEnabled"),
        "Behaviour.get_isActiveAndEnabled");
    const selectableGetInteractable = need(
        findMethod(selectableK, "get_interactable"),
        "Selectable.get_interactable");
    const buttonGetOnClick = need(findMethod(buttonK, "get_onClick"),
                                  "Button.get_onClick");
    const unityEventInvoke = need(
        findMethodByParamCount(unityEventK, "Invoke", 0),
        "UnityEvent.Invoke()");

    // Build typeof(Button) for FindObjectsByType.
    const buttonSystemType = getSystemType(buttonK);

    _refs = {
        objectK, componentK, transformK, behaviourK,
        selectableK, buttonK, unityEventK,
        findObjectsByType, objectGetName,
        componentGetGameObject, componentGetTransform,
        transformGetParent, behaviourGetActiveAndEnabled,
        selectableGetInteractable, buttonGetOnClick, unityEventInvoke,
        buttonSystemType,
    };
    log("[ui-nav] refs resolved");
    return _refs;
}

// Pick the FindObjectsByType overload that takes (Type, FindObjectsSortMode).
// We do a lightweight type-name check on param 0 to filter out
// (FindObjectsInactive, FindObjectsSortMode).
function pickFindObjectsByType(objectK: NativePointer): MethodRef | null {
    const lib = Process.findModuleByName(IL2CPP_MODULE_NAME)!;
    const getParamPtr = lib.findExportByName("il2cpp_method_get_param");
    const typeNamePtr = lib.findExportByName("il2cpp_type_get_name");
    if (!getParamPtr || !typeNamePtr) {
        // Fall back: first 2-param overload (best effort).
        return findMethodByParamCount(objectK, "FindObjectsByType", 2);
    }
    const getParam = new NativeFunction(
        getParamPtr, "pointer", ["pointer", "uint32"]);
    const typeGetName = new NativeFunction(
        typeNamePtr, "pointer", ["pointer"]);

    const it = Memory.alloc(Process.pointerSize);
    it.writePointer(ptr(0));
    let m: NativePointer;
    let fallback: MethodRef | null = null;
    while (!(m = class_get_methods(objectK, it) as NativePointer).isNull()) {
        if (cstr(method_get_name(m) as NativePointer) !== "FindObjectsByType") {
            continue;
        }
        try {
            if ((method_get_param_count(m) as number) !== 2) continue;
            const p0 = getParam(m, 0) as NativePointer;
            const tn = cstr(typeGetName(p0) as NativePointer);
            const candidate: MethodRef = { info: m, ptr: methodEntry(m) };
            if (tn === "System.Type") return candidate;
            if (!fallback) fallback = candidate;
        } catch { /* skip */ }
    }
    return fallback;
}

// Read boxed primitive returned by il2cpp_runtime_invoke. Value-type
// returns are auto-boxed into Il2CppObject* — value at +0x10.
function readBoxedBool(p: NativePointer): boolean {
    if (p.isNull()) return false;
    return p.add(0x10).readU8() !== 0;
}

function getName(r: UiRefs, obj: NativePointer): string {
    if (obj.isNull()) return "";
    try {
        const sp = invokeMethod(r.objectGetName.info, obj, []);
        return readIl2cppString(sp) ?? "";
    } catch { return ""; }
}

/** Build the full hierarchy path from a Button up to its scene root.
 * Example: "Canvas (Environment)/MenuRoot/Top/CampaignButton". */
function getPath(r: UiRefs, button: NativePointer): string {
    let t: NativePointer;
    try {
        t = invokeMethod(r.componentGetTransform.info, button, []);
    } catch { return ""; }
    if (t.isNull()) return "";
    const parts: string[] = [];
    let depth = 0;
    while (!t.isNull() && depth < 50) {
        let go: NativePointer;
        try {
            go = invokeMethod(r.componentGetGameObject.info, t, []);
        } catch { break; }
        parts.unshift(getName(r, go));
        try {
            t = invokeMethod(r.transformGetParent.info, t, []);
        } catch { break; }
        depth++;
    }
    return parts.join("/");
}

export interface ButtonRow {
    path: string;
    name: string;
    active: boolean;
    interactable: boolean;
    ptr: string;
}

/** Enumerate every live Button. Filter applied per caller. */
export function enumerateButtons(r: UiRefs, includeAll: boolean): ButtonRow[] {
    // FindObjectsByType(Type, FindObjectsSortMode.None=0).
    const sortMode = Memory.alloc(4).writeS32(0);
    const arrayPtr = invokeMethod(
        r.findObjectsByType.info, null, [r.buttonSystemType, sortMode]);
    if (arrayPtr.isNull()) return [];

    // Il2CppArray layout: length at +0x18, elements at +0x20.
    const len = arrayPtr.add(0x18).readS32();
    if (len <= 0 || len > 100000) return [];

    const out: ButtonRow[] = [];
    for (let i = 0; i < len; i++) {
        const btn = arrayPtr.add(0x20 + i * Process.pointerSize).readPointer();
        if (btn.isNull()) continue;

        let active = false;
        let interactable = false;
        try {
            active = readBoxedBool(
                invokeMethod(r.behaviourGetActiveAndEnabled.info, btn, []));
        } catch { /* */ }
        try {
            interactable = readBoxedBool(
                invokeMethod(r.selectableGetInteractable.info, btn, []));
        } catch { /* */ }

        if (!includeAll && (!active || !interactable)) continue;

        const path = getPath(r, btn);
        const segs = path.split("/");
        const name = segs[segs.length - 1] ?? "";
        out.push({ path, name, active, interactable, ptr: btn.toString() });
    }
    return out;
}

/** Click a button by exact path match. */
export function clickByPath(r: UiRefs, path: string): {
    ok: boolean; clicked?: string; err?: string;
} {
    const rows = enumerateButtons(r, true);
    const match = rows.find((b) => b.path === path);
    if (!match) {
        return { ok: false, err: `no button at path: ${path}` };
    }
    if (!match.active || !match.interactable) {
        return {
            ok: false,
            err: `button ${path} found but not clickable ` +
                `(active=${match.active}, interactable=${match.interactable})`,
        };
    }

    const btn = ptr(match.ptr);
    let onClick: NativePointer;
    try {
        onClick = invokeMethod(r.buttonGetOnClick.info, btn, []);
    } catch (e) {
        return { ok: false, err: `get_onClick failed: ${(e as Error).message}` };
    }
    if (onClick.isNull()) {
        return { ok: false, err: "Button.onClick is null" };
    }
    try {
        invokeMethod(r.unityEventInvoke.info, onClick, []);
    } catch (e) {
        return {
            ok: false,
            err: `onClick.Invoke threw: ${(e as Error).message}`,
        };
    }
    return { ok: true, clicked: path };
}

export function register(ctx: Ctx): void {
    ctx.rpc.uiList = () => queueOnMainThread(() => {
        try {
            const r = ensureRefs();
            return { ok: true, buttons: enumerateButtons(r, false) };
        } catch (e) {
            return { ok: false, err: (e as Error).message };
        }
    });

    /** Same as uiList but includes inactive/non-interactable buttons. Useful
     * for debugging when a target button isn't appearing in uiList. */
    ctx.rpc.uiListAll = () => queueOnMainThread(() => {
        try {
            const r = ensureRefs();
            return { ok: true, buttons: enumerateButtons(r, true) };
        } catch (e) {
            return { ok: false, err: (e as Error).message };
        }
    });

    ctx.rpc.uiClick = (path: string) => queueOnMainThread(() => {
        if (typeof path !== "string" || path.length === 0) {
            return { ok: false, err: "uiClick: path must be a non-empty string" };
        }
        try {
            const r = ensureRefs();
            return clickByPath(r, path);
        } catch (e) {
            return { ok: false, err: (e as Error).message };
        }
    });
}
