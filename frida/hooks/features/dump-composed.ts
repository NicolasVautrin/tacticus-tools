// dump-composed — lecture RUNTIME du `_composedUtilityLookup` de la
// `UtilitiesDatabase` (Dictionary<UtilityType, UtilityType[]>).
//
// Pourquoi : l'assemblage des composites (Damage(35)=[13 feuilles], Tile(7)=[29],
// MovementSuggestion(33), …) est construit dans `UtilitiesDatabase.InitializeUtilities`
// depuis des arrays STATIQUES du binaire (RuntimeHelpers.InitializeArray) — illisibles
// via `read_bytes(DAT)` (rend un token de métadonnée). On les lit donc à l'exécution,
// sur l'instance déjà initialisée (lecture d'une STRUCTURE de config, pas d'une utilité).
//
// Capture : hook `DefaultGroupOperator..ctor(state, aiQuery, logger, utilitiesDatabase,
// aiLogger)` → arg[4]. Le dict est identique pour toute instance (composition hardcodée),
// donc on capture la PREMIÈRE venue (live ou mirror, peu importe), une seule fois.
//
// RPC `dumpComposedUtility()` → { ok, dbPtr, fieldOffset, count, entries:[{key, values:[…]}] }.

import { Ctx } from "../controller.js";
import { findClass, findMethod, getFieldOffset, class_get_name, s } from "../il2cpp/helpers.js";

const groupOperatorClass = findClass(
    "BattleLogicAssembly.dll",
    "IdunBattle.AI.OperationalDeciders", "DefaultGroupOperator");

const utilitiesDatabaseClass = findClass(
    "BattleLogicAssembly.dll",
    "IdunBattle.Core.Services", "UtilitiesDatabase");

// Offset de `_composedUtilityLookup` (Dictionary<UtilityType, UtilityType[]>) — résolu
// par nom (robuste au changement de build), pas hardcodé (dump.cs disait 0x58).
const composedOff = utilitiesDatabaseClass
    ? getFieldOffset(utilitiesDatabaseClass, "_composedUtilityLookup") : -1;

let capturedDb: NativePointer | null = null;
let ctorHookInstalled = false;

function ensureCapture(): void {
    if (ctorHookInstalled || !groupOperatorClass) return;
    const ctor = findMethod(groupOperatorClass, ".ctor");
    if (!ctor || ctor.ptr.isNull()) return;
    Interceptor.attach(ctor.ptr, {
        onEnter(args) {
            if (capturedDb) return;              // une seule capture suffit
            // Frida instance method args : [this, state, aiQuery, logger, utilDb, aiLogger]
            const db = args[4];
            if (db && !db.isNull()) capturedDb = db;
        },
    });
    Interceptor.flush();
    ctorHookInstalled = true;
}

/** Lit un Il2CppArray<int32> → number[] (length @0x18, data @0x20). */
function readInt32Array(arr: NativePointer): number[] {
    if (!arr || arr.isNull()) return [];
    const len = arr.add(0x18).readS32();
    const out: number[] = [];
    if (len < 0 || len > 256) return out;        // garde-fou
    const data = arr.add(0x20);
    for (let i = 0; i < len; i++) out.push(data.add(i * 4).readS32());
    return out;
}

/** Walk d'un Dictionary<int, int[]> il2cpp. Entry<int,ref> = {hashCode@0,next@4,key@8,value@0x10},
 *  stride 0x18 ; entries Il2CppArray (len @0x18, data @0x20). _count/_entries résolus par nom. */
function dumpDict(dict: NativePointer): { count: number; entries: { key: number; values: number[] }[] } {
    const klass = dict.readPointer();            // Il2CppObject.klass = champ 0
    let entriesOff = -1, countOff = -1;
    for (const n of ["_entries", "entries"]) {
        const o = getFieldOffset(klass, n);
        if (o >= 0) { entriesOff = o; break; }
    }
    for (const n of ["_count", "count"]) {
        const o = getFieldOffset(klass, n);
        if (o >= 0) { countOff = o; break; }
    }
    if (entriesOff < 0 || countOff < 0) return { count: -1, entries: [] };
    const count = dict.add(countOff).readS32();
    const entriesArr = dict.add(entriesOff).readPointer();
    const out: { key: number; values: number[] }[] = [];
    if (entriesArr.isNull() || count < 0 || count > 1024) return { count, entries: out };
    const base = entriesArr.add(0x20);
    for (let i = 0; i < count; i++) {
        const e = base.add(i * 0x18);
        const key = e.add(8).readS32();
        if (key < 0 || key > 200) continue;      // hashCode<0 = slot libre → skip
        const valPtr = e.add(0x10).readPointer();
        out.push({ key, values: readInt32Array(valPtr) });
    }
    return { count, entries: out };
}

export function register(ctx: Ctx): void {
    ensureCapture();

    ctx.rpc.dumpComposedUtility = (): unknown => {
        ensureCapture();
        if (!utilitiesDatabaseClass) return { ok: false, error: "UtilitiesDatabase class introuvable" };
        if (composedOff < 0) return { ok: false, error: "_composedUtilityLookup offset introuvable" };
        if (!capturedDb) {
            return {
                ok: false,
                error: "aucune UtilitiesDatabase capturée — construire un runner (DefaultGroupOperator..ctor) d'abord",
                composedOff,
            };
        }
        try {
            const dict = capturedDb.add(composedOff).readPointer();
            if (dict.isNull()) return { ok: false, error: "_composedUtilityLookup == null", composedOff };
            const r = dumpDict(dict);
            return {
                ok: true,
                dbPtr: capturedDb.toString(),
                klass: s(class_get_name(utilitiesDatabaseClass) as NativePointer),
                fieldOffset: composedOff,
                count: r.count,
                entries: r.entries,
            };
        } catch (e) {
            return { ok: false, error: "walk threw: " + (e as Error).message, composedOff };
        }
    };

    ctx.rpc.dumpComposedUtilityStatus = (): unknown => ({
        ok: true,
        captured: !!capturedDb,
        composedOff,
        hasClass: !!utilitiesDatabaseClass,
        hasGroupOp: !!groupOperatorClass,
    });
}
