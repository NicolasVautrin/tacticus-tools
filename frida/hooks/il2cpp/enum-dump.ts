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
        return true;
    } catch {
        _fieldStaticGetValue = null;
        return false;
    }
}

const FIELD_ATTRIBUTE_LITERAL = 0x40;
const FIELD_ATTRIBUTE_STATIC = 0x10;

/** Walk every static literal field of `klass` and read its int32 value.
 * Returns `{ "0": "None", "1": "StartMatch", ... }` (string keys for JSON
 * roundtrip — the front coerces back to int when looking up). */
export function dumpEnum(
    asm: string, ns: string, cls: string,
): Record<string, string> | null {
    if (!ensure()) return null;
    const klass = findClass(asm, ns, cls) ?? findClassAnywhere(ns, cls);
    if (!klass) return null;

    const out: Record<string, string> = {};
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
            valBuf.writeS32(0);
            _fieldStaticGetValue!(f, valBuf);
            const value = valBuf.readS32();
            out[String(value)] = name;
        } catch { /* skip unreadable */ }
    }
    return out;
}
