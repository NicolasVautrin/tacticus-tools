// Dump IL2CPP enum classes — iterate static-literal fields, read their
// int value via `il2cpp_field_static_get_value`. Returns a `{ value: name }`
// map suitable for `send({ t:"enum-dump", name, values })` to the front.
//
// Used to resolve numeric IDs in event tags (Effect_Id, AbilityType, …) to
// their string name, which the front then maps to the i18n catalog
// (`UnitEffects/<name>_Name`, etc.).

import { IL2CPP_MODULE_NAME, findClass, findClassAnywhere, s } from "./helpers.js";

const lib = Process.findModuleByName(IL2CPP_MODULE_NAME);

function exp(n: string): NativePointer {
    if (!lib) throw new Error(`${IL2CPP_MODULE_NAME} not loaded`);
    const p = lib.findExportByName(n);
    if (!p) throw new Error(`missing export: ${n}`);
    return p;
}

// Resolved lazily — some IL2CPP builds strip a few of these.
let _ready = false;
let _classGetFields: NativeFunction<NativePointer, [NativePointer, NativePointer]>;
let _fieldGetName: NativeFunction<NativePointer, [NativePointer]>;
let _fieldGetFlags: NativeFunction<number, [NativePointer]>;
let _fieldStaticGetValue: NativeFunction<void, [NativePointer, NativePointer]> | null = null;
// Optionnels : servent a lire la LARGEUR reelle de l'enum. Leur absence fait retomber sur
// l'ancien comportement (int32) plutot que d'invalider tout le dump.
let _fieldGetType: NativeFunction<NativePointer, [NativePointer]> | null = null;
let _typeGetName: NativeFunction<NativePointer, [NativePointer]> | null = null;

function ensure(): boolean {
    if (_ready) return _fieldStaticGetValue !== null;
    _ready = true;
    try {
        _classGetFields = new NativeFunction(
            exp("il2cpp_class_get_fields"), "pointer", ["pointer", "pointer"]);
        _fieldGetName = new NativeFunction(
            exp("il2cpp_field_get_name"), "pointer", ["pointer"]);
        _fieldGetFlags = new NativeFunction(
            exp("il2cpp_field_get_flags"), "uint32", ["pointer"]);
        _fieldStaticGetValue = new NativeFunction(
            exp("il2cpp_field_static_get_value"), "void",
            ["pointer", "pointer"]);
    } catch {
        _fieldStaticGetValue = null;
        return false;
    }
    // Resolution SEPAREE : ces deux-la sont un confort de precision, pas une dependance
    // dure — s'ils manquent on lit en int32 comme avant.
    try {
        _fieldGetType = new NativeFunction(
            exp("il2cpp_field_get_type"), "pointer", ["pointer"]);
        _typeGetName = new NativeFunction(
            exp("il2cpp_type_get_name"), "pointer", ["pointer"]);
    } catch {
        _fieldGetType = null;
        _typeGetName = null;
    }
    return true;
}

/** Type SOUS-JACENT de l'enum, porte par son champ implicite `value__`. */
function underlyingOf(klass: NativePointer): string {
    if (!_fieldGetType || !_typeGetName) return "";
    const it = Memory.alloc(Process.pointerSize);
    it.writePointer(ptr(0));
    let f: NativePointer;
    while (!(f = _classGetFields(klass, it) as NativePointer).isNull()) {
        if (s(_fieldGetName(f) as NativePointer) !== "value__") continue;
        try {
            return s(_typeGetName(_fieldGetType(f) as NativePointer) as NativePointer);
        } catch { return ""; }
    }
    return "";
}

/** Valeur d'un literal, en DECIMAL EXACT, a la largeur reelle de l'enum.
 *
 * Ce site lisait `readS32()` inconditionnellement. Sur un enum adosse a `long` — les enums de
 * FLAGS un peu fournis — tout membre au-dessus du bit 31 a ses 32 bits de poids faible NULS :
 * il tronquait vers 0, et comme la map est keyee PAR VALEUR, les membres hauts s'ecrasaient
 * entre eux. Mesure sur `IdunBattle.Core.Services.TargetingRule` (build gqfc5mff6c) : douze
 * membres reduits a UN. Perte silencieuse. */
function readLiteral(buf: NativePointer, underlying: string): string {
    switch (underlying) {
        case "System.SByte":  return String(buf.readS8());
        case "System.Byte":   return String(buf.readU8());
        case "System.Int16":  return String(buf.readS16());
        case "System.UInt16": return String(buf.readU16());
        case "System.UInt32": return String(buf.readU32());
        case "System.Int64":  return buf.readS64().toString();
        case "System.UInt64": return buf.readU64().toString();
        default:              return String(buf.readS32());   // System.Int32 = defaut C#
    }
}

const FIELD_ATTRIBUTE_LITERAL = 0x40;
const FIELD_ATTRIBUTE_STATIC = 0x10;

/** Walk every static literal field of `klass` and read its value at the enum's real width.
 * Returns `{ "0": "None", "1": "StartMatch", ... }` (string keys for JSON
 * roundtrip — the front coerces back to int when looking up).
 *
 * La map reste keyee PAR VALEUR : c'est le contrat de ses consommateurs (le front resout un
 * id numerique vers un nom). Deux membres de MEME valeur — alias, composite de flags — s'y
 * ecrasent donc encore ; c'est une limite assumee de cette forme, distincte du bug de largeur
 * corrige ci-dessus. Le dump one-shot `scripts/frida/dump-il2cpp-full.js`, lui, keye par NOM. */
export function dumpEnum(
    asm: string, ns: string, cls: string,
): Record<string, string> | null {
    if (!ensure()) return null;
    const klass = findClass(asm, ns, cls) ?? findClassAnywhere(ns, cls);
    if (!klass) return null;

    const out: Record<string, string> = {};
    const underlying = underlyingOf(klass);
    const it = Memory.alloc(Process.pointerSize);
    it.writePointer(ptr(0));
    const valBuf = Memory.alloc(8);

    let f: NativePointer;
    while (!(f = _classGetFields(klass, it) as NativePointer).isNull()) {
        const flags = _fieldGetFlags(f) as number;
        if ((flags & FIELD_ATTRIBUTE_LITERAL) === 0) continue;
        if ((flags & FIELD_ATTRIBUTE_STATIC) === 0) continue;
        const name = s(_fieldGetName(f) as NativePointer);
        if (!name || name === "value__") continue;   // synthetic
        try {
            valBuf.writeS64(0);
            _fieldStaticGetValue!(f, valBuf);
            out[readLiteral(valBuf, underlying)] = name;
        } catch { /* skip unreadable */ }
    }
    return out;
}
