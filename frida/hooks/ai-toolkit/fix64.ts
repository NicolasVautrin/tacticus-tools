// Fix64 helpers + BaseUtility sentinel value reader.
//
// Tacticus AI scoring uses `Fix64` (a Q32.32 fixed-point int64 wrapping a
// raw scaled integer). The score aggregator interprets certain magic
// values as DIRECTIVES rather than numbers:
//   OK                     = 0
//   BONUS                  = small positive
//   TAKE                   = int64.MaxValue (unconditionally pick)
//   SKIP                   = (rare)
//   REJECT                 = int64.MinValue (discard candidate entirely)
//   REJECT_IF_VALID_EXISTS = reject only if any non-rejected alt exists
//   YIELD_NULL             = (rare)
// These are static fields on `IdunBattle.AI.Utilities.BaseUtility` —
// reading them at runtime gives us the exact raw int64 the game compares
// against, so our patches use the same value the AI checks for.
//
// Generic — used by any fix that wants to write Fix64 values into a
// Bucket, score field, or args slot.

import {
    class_get_fields, cstr, field_get_name, findClassAnywhere,
    IL2CPP_MODULE_NAME,
} from "../il2cpp/helpers.js";

/** Build a Fix64 raw int64 from a plain integer. The Fix64 representation
 * has 32 fractional bits, so `n * 2^32` is the raw value. */
export function fix64FromInt(n: number): Int64 {
    const positive = Math.abs(n);
    const raw = (BigInt(positive) << 32n).toString();
    return n < 0 ? new Int64("-" + raw) : new Int64(raw);
}

export interface UtilityConsts {
    OK: Int64 | null;
    BONUS: Int64 | null;
    TAKE: Int64 | null;
    SKIP: Int64 | null;
    REJECT: Int64 | null;
    REJECT_IF_VALID_EXISTS: Int64 | null;
    YIELD_NULL: Int64 | null;
}

const FIELD_ATTRIBUTE_STATIC = 0x0010;

const _il2cppLib = Process.findModuleByName(IL2CPP_MODULE_NAME);
function _exp(n: string): NativePointer {
    if (!_il2cppLib) throw new Error(`${IL2CPP_MODULE_NAME} not loaded`);
    const p = _il2cppLib.findExportByName(n);
    if (!p) throw new Error("missing export: " + n);
    return p;
}
const _fieldStaticGetValue = (() => {
    try {
        return new NativeFunction(
            _exp("il2cpp_field_static_get_value"),
            "void", ["pointer", "pointer"]);
    } catch { return null; }
})();
const _fieldGetFlags = (() => {
    try {
        return new NativeFunction(
            _exp("il2cpp_field_get_flags"), "uint32", ["pointer"]);
    } catch { return null; }
})();

/** Read every static Fix64 sentinel on `BaseUtility` at module load. The
 * class lives in `IdunBattle.AI.Utilities.BaseUtility`. Returns nulls
 * for any field we can't resolve — callers must check before relying on
 * a value (e.g. fall back to a numeric penalty). */
export function readUtilityConstants(): UtilityConsts {
    const out: UtilityConsts = {
        OK: null, BONUS: null, TAKE: null, SKIP: null,
        REJECT: null, REJECT_IF_VALID_EXISTS: null, YIELD_NULL: null,
    };
    const klass = findClassAnywhere("IdunBattle.AI.Utilities", "BaseUtility");
    if (!klass || !_fieldStaticGetValue || !_fieldGetFlags) return out;
    const wantedNames = new Set(Object.keys(out));
    const it = Memory.alloc(Process.pointerSize);
    it.writePointer(ptr(0));
    let f: NativePointer;
    while (!(f = class_get_fields(klass, it) as NativePointer).isNull()) {
        const flags = _fieldGetFlags(f) as number;
        if ((flags & FIELD_ATTRIBUTE_STATIC) === 0) continue;
        const name = cstr(field_get_name(f) as NativePointer);
        if (!wantedNames.has(name)) continue;
        const buf = Memory.alloc(8);
        try {
            _fieldStaticGetValue(f, buf);
            out[name as keyof UtilityConsts] = buf.readS64();
        } catch { /* leave null */ }
    }
    return out;
}
