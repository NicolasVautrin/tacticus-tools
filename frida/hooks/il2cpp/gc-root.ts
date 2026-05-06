// IL2CPP GC rooting via native `il2cpp_gchandle_new` handles.
//
// Earlier we used a managed `System.Collections.ArrayList` to pin objects
// against the IL2CPP managed GC. That worked most of the time but the
// ArrayList itself sometimes got invalidated mid-run (signature: Add throws
// "system error"), breaking pins on every previously-pinned object — every
// recovery from that point would dereference dangling msg pointers and AV.
//
// `il2cpp_gchandle_new(obj, pinned)` is the canonical IL2CPP API to keep an
// object alive across GC. It returns a uint32 handle the script holds; calls
// to `il2cpp_gchandle_free` release it. No managed wrapper involved → no
// "ArrayList got invalidated" failure mode.
//
// `pinned=true` additionally prevents the GC from moving the object. Tacticus
// IL2CPP doesn't appear to compact (no movement observed) but pinning keeps
// us safe across future builds.

import { IL2CPP_MODULE_NAME } from "./helpers.js";
import { log } from "../runtime/diag.js";

const _lib = Process.findModuleByName(IL2CPP_MODULE_NAME);
function _exp(n: string): NativePointer {
    if (!_lib) throw new Error(`${IL2CPP_MODULE_NAME} not loaded`);
    const p = _lib.findExportByName(n);
    if (!p) throw new Error("missing export: " + n);
    return p;
}

const _gchandleNew = new NativeFunction(
    _exp("il2cpp_gchandle_new"), "uint32", ["pointer", "uint8"]);
const _gchandleFree = new NativeFunction(
    _exp("il2cpp_gchandle_free"), "void", ["uint32"]);

// Map<ptr-string, handle> so `remove(ptr)` can locate the gchandle to free.
// Use string keys because NativePointer instances aren't structurally compared
// by JS Map.
const handles = new Map<string, number>();
let initialized = false;

function init(): boolean {
    if (initialized) return true;
    initialized = true;
    log("[gcRoot] initialized (gchandle-based)");
    return true;
}

function add(objPtr: NativePointer | null): void {
    if (!initialized) init();
    if (objPtr === null || objPtr.isNull()) return;
    const key = objPtr.toString();
    if (handles.has(key)) return;  // already pinned
    try {
        const h = _gchandleNew(objPtr, 1) as number;  // pinned=true
        if (h === 0) {
            // IL2CPP returns 0 to mean "failed". Rare — usually only when the
            // object is not in the managed heap.
            log("[gcRoot] gchandle_new returned 0 for " + objPtr);
            return;
        }
        handles.set(key, h);
    } catch (e) {
        // Native call should never throw, but defend anyway.
        log("[gcRoot] gchandle_new threw: " + (e as Error).message);
    }
}

function remove(objPtr: NativePointer | null): void {
    if (objPtr === null || objPtr.isNull()) return;
    const key = objPtr.toString();
    const h = handles.get(key);
    if (h === undefined) return;
    try { _gchandleFree(h); } catch { /* best effort */ }
    handles.delete(key);
}

function clear(): void {
    for (const h of handles.values()) {
        try { _gchandleFree(h); } catch { /* best effort */ }
    }
    handles.clear();
}

function count(): number {
    return handles.size;
}

/** Legacy export kept for callers that wanted the ArrayList pointer. With
 * gchandles there's no list — return null. Callers should not rely on it. */
function listPtr(): NativePointer | null { return null; }

export const gcRoot = { init, add, remove, clear, count, listPtr };
