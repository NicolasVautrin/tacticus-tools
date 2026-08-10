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

// --- Instrumentation du tas managé (protocole de mesure #132) ---
// Variante SOUPLE de `_exp` : un export absent rend null au lieu de throw. Le
// module est chargé à l'inject — un throw ici tuerait tout le script pour une
// sonde optionnelle.
function _expSoft(n: string): NativePointer | null {
    try { return _lib ? _lib.findExportByName(n) : null; } catch { return null; }
}
function _fnSoft(
    n: string, ret: string, args: string[],
): NativeFunction<any, any> | null {
    const p = _expSoft(n);
    return p ? new NativeFunction(p, ret as never, args as never) : null;
}
// il2cpp_gc_get_{used,heap}_size rendent un int64 (API Unity). `il2cpp_gc_collect`
// prend le nombre max de générations. `il2cpp_string_new` alloue une chaîne
// managée — le seul allocateur trivial exporté, utilisé comme LEST par `pinBallast`.
const _gcUsedSize = _fnSoft("il2cpp_gc_get_used_size", "int64", []);
const _gcHeapSize = _fnSoft("il2cpp_gc_get_heap_size", "int64", []);
const _gcCollect = _fnSoft("il2cpp_gc_collect", "void", ["int"]);
const _stringNew = _fnSoft("il2cpp_string_new", "pointer", ["pointer"]);

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
 * gchandles there's no list — return null. Callers should not rely on it.
 * PIÈGE HISTORIQUE : `status.ts` en faisait une GARDE (`listPtr() ? count() : null`),
 * ce qui a rendu `info.gcRootCount` muet du 2026-05-07 au 2026-07-26. */
function listPtr(): NativePointer | null { return null; }

/** Taille utilisée / réservée du tas managé IL2CPP, en octets (null si l'export
 * manque). CONTRÔLE OBLIGATOIRE du protocole #132 : si `Initialize` échoue alors
 * que le tas est aussi au plus haut, les handles ne sont pas prouvés coupables —
 * la mémoire est co-variable. */
function usedSize(): number | null {
    if (!_gcUsedSize) return null;
    try { return (_gcUsedSize() as Int64).toNumber(); } catch { return null; }
}
function heapSize(): number | null {
    if (!_gcHeapSize) return null;
    try { return (_gcHeapSize() as Int64).toNumber(); } catch { return null; }
}

/** ⛔ FORCER UN GC GÈLE LE JEU. Mesuré, pas redouté — et ce refus remplace une prose qui
 *  disait « à n'appeler QUE sur demande explicite », laquelle n'a arrêté personne.
 *
 *  MESURE DU 2026-08-10 (#600, build `rnca9r7q6c`) : un `il2cpp_gc_collect(2)` appelé depuis
 *  le thread RPC de Frida — **sans** aucun envoi, delegate, ni `runtime_invoke` — a figé le
 *  process. Lecture du process figé (`OpenThread` + `GetThreadContext`) : **145 threads dans
 *  `ntdll.dll`** + 1 dans `win32u`, aucun dans `GameAssembly.dll`, main thread parqué avec
 *  ZÉRO cadre `GameAssembly` (suspendu à un safepoint). Le RPC n'est jamais revenu (60 s),
 *  et `Get-Process().Responding` est passé à `False`.
 *
 *  C'est le stop-the-world du GC qui ne repart pas : il attend qu'un thread atteigne un
 *  safepoint, et sous instrumentation Frida ce thread n'y arrive pas. Même famille que
 *  l'avertissement déjà porté par `CLAUDE.md` sur les scans de tas.
 *
 *  ⚠ CE GEL EST CELUI QUI A ÉTÉ ATTRIBUÉ À TORT au callback du dispatch d'Operation (#600,
 *  tentatives #4 et #5). Deux pannes distinctes étaient traitées comme une seule.
 *
 *  ⚠ ET IL NE SE SIGNALE PAS : process vivant, session Frida `running`, `/api/admin/status`
 *  serein. Seul un RPC qui ne revient pas le révèle.
 *
 *  La dérive mémoire mesurée le 2026-07-26 (6,9 Go après ~1900 batailles en 16 h) reste
 *  réelle — mais forcer une collecte n'est PAS le remède disponible : le remède coûterait
 *  une relance du jeu à chaque appel. Cette voie est fermée, pas oubliée (résidu #132).
 *
 *  `autoriserLeGel` est l'échappatoire consciente, pour qui veut REMESURER ce gel (c'est ce
 *  que fait `probes/gc-rendezvous.ts`). Rend `false` sans rien tenter dans tous les autres
 *  cas — et `false` veut dire « RIEN N'A ÉTÉ TENTÉ », jamais « la collecte a échoué ». */
function collect(maxGenerations = 2, autoriserLeGel = false): boolean {
    if (!autoriserLeGel) {
        log("[gcRoot] collect() REFUSE : forcer un GC gele le jeu (145 threads parques "
            + "dans ntdll, cf. docs/rl/case-600-gel-du-dispatch-natif.md). Passe "
            + "`autoriserLeGel` si tu veux justement remesurer ce gel.");
        return false;
    }
    if (!_gcCollect) return false;
    try { _gcCollect(maxGenerations); return true; } catch { return false; }
}

// --- LEST de handles (manip B du protocole #132) -----------------------------
// L'observation de mai (« Initialize échoue au-delà de ~900 pins ») ne POUVAIT
// PAS distinguer sa cause : le nombre de handles et le nombre de batailles
// vivantes montaient toujours ENSEMBLE. Le lest les découple — on monte le
// compteur de handles à K avec UNE SEULE bataille vivante, puis on tente un
// build. Chaînes managées allouées via `il2cpp_string_new` (allocateur trivial),
// épinglées par le même chemin que le reste, et tracées à part pour être
// relâchées d'un bloc sans toucher aux pins réels.
const ballast: NativePointer[] = [];

function pinBallast(n: number): { pinned: number; total: number } {
    if (!_stringNew) return { pinned: 0, total: ballast.length };
    if (!initialized) init();
    const buf = Memory.allocUtf8String("gcRoot-ballast");
    let pinned = 0;
    for (let i = 0; i < n; i++) {
        let sp: NativePointer;
        try { sp = _stringNew(buf) as NativePointer; } catch { break; }
        if (sp.isNull()) break;
        const before = handles.size;
        add(sp);
        // `add` est idempotent par pointeur : si l'allocateur rend deux fois la
        // même adresse (chaîne internée), le handle n'augmente pas — on ne
        // compterait alors PAS un vrai handle de plus.
        if (handles.size === before) continue;
        ballast.push(sp);
        pinned++;
    }
    return { pinned, total: ballast.length };
}

function releaseBallast(): number {
    const n = ballast.length;
    for (const p of ballast) remove(p);
    ballast.length = 0;
    return n;
}

function ballastCount(): number { return ballast.length; }

export const gcRoot = {
    init, add, remove, clear, count, listPtr,
    usedSize, heapSize, collect, pinBallast, releaseBallast, ballastCount,
};
