// Dump IL2CPP enum classes — iterate static-literal fields, read their value via
// `il2cpp_field_static_get_value` A LA LARGEUR REELLE de l'enum. Returns a `{ name: value }`
// map (valeur en decimal exact, chaine).
//
// Sert a resoudre les ids numeriques des tags d'evenement (Effect_Id, AbilityType, …) vers
// leur nom, et a GENERER les tables `hooks/data/*-names.ts`.

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
 * Returns `{ "None": "0", "StartMatch": "1", ... }` — keye par NOM, valeur en DECIMAL EXACT
 * (chaine : un flag 64 bits depasse 2^53, ou un Number JSON perdrait des bits de poids faible).
 *
 * Le keyage etait PAR VALEUR, pour le front, qui resolvait un id numerique vers un nom. Le front
 * n'est plus utilise (2026-07-27), et ce contrat coutait deux choses : deux membres de meme valeur
 * — alias, composite de flags — s'y ecrasaient, et il DIVERGEAIT du dump one-shot
 * `scripts/frida/dump-il2cpp-full.js`. Un seul contrat pour la meme notion, desormais. */
export function dumpEnum(
    asm: string, ns: string, cls: string,
): Record<string, string> | null {
    if (!ensure()) return null;
    const klass = findClass(asm, ns, cls) ?? findClassAnywhere(ns, cls);
    if (!klass) return null;
    return dumpEnumClass(klass);
}

/** LE MÊME dump, mais à partir de la CLASSE déjà résolue.
 *
 *  Pourquoi cette entrée existe : un enum IMBRIQUÉ ne se retrouve pas par son nom.
 *  `idun.ui.ScreenVisibility.State` s'appelle juste `State` pour IL2CPP, dans le namespace
 *  `idun.ui` — un `findClassAnywhere("idun.ui", "State")` attraperait n'importe quel `State`
 *  du namespace et publierait des noms de membres FAUX, sans lever. Quand on tient déjà le
 *  champ, sa classe de type est la réponse EXACTE : on la passe directement.
 *
 *  Un seul corps, deux entrées — la duplication serait exactement la divergence que la
 *  doctrine « un service natif = UNE fonction » interdit. */
export function dumpEnumClass(klass: NativePointer): Record<string, string> | null {
    if (!ensure()) return null;
    if (klass.isNull()) return null;

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
            out[name] = readLiteral(valBuf, underlying);
        } catch { /* skip unreadable */ }
    }
    return out;
}
