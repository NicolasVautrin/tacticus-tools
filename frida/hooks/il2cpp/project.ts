// Path-based JSON projection for IL2CPP managed objects.
//
// Given a root object pointer and a list of dotted paths ("Position.Coordinate.Column"),
// walks each path through the field metadata, dereferencing reference-type
// hops and reading struct/value-type segments inline, and emits a
// JS-native record with the leaf values.
//
// Walks the IL2CPP type system at every hop, no caching of paths beyond
// (klass, fieldName) → FieldInfo* (already in helpers.getFieldOffset).
//
// Auto-detects value vs reference types via the IL2CppType.type byte
// (Mono/IL2CPP shared enum). Generic instantiations: Nullable<T> is
// recognized as a value-type wrapper (read value if hasValue=true);
// reference-type generics (List<T>, IList<T>) are dereferenced like
// normal heap classes.
//
// Index syntax for collections: `Field[i]` reads list/array element i.
// Example path: "Tiles[0].Position.Coordinate.Column".
//
// Leaf type can be hinted (`type: "fix64"`) or auto-inferred. When
// inference is ambiguous (e.g. enum vs int), hint takes precedence.

import {
    class_get_name, getFieldInfo, getFieldOffset,
    field_get_type, type_get_class_or_element_class,
    readIl2cppString, s,
} from "./helpers.js";

// C# auto-properties (`public Foo Bar { get; }`) compile to a private
// backing field named `<Bar>k__BackingField`. Path schemas use the
// public name `Bar`; we fall back to the backing-field name when the
// literal lookup fails so users don't have to spell out the mangled form.
//
// Everything we need to step through one field hop is memoized once per
// (klass, fieldName) into a `FieldMeta` record. Subsequent hops are pure
// memory reads — no IL2CPP reflection on the hot path.

interface FieldMeta {
    offset: number;
    info: NativePointer;
    fieldType: NativePointer;     // IL2CppType*
    tag: number;                  // IL2CppType.type byte
    classOfType: NativePointer;   // resolved once, used for VALUETYPE/GENERICINST
}

const fieldMetaCache: Map<string, FieldMeta | null> = new Map();

function resolveField(
    klass: NativePointer, name: string,
): FieldMeta | null {
    const key = klass.toString() + "::" + name;
    const cached = fieldMetaCache.get(key);
    if (cached !== undefined) return cached;

    let off = getFieldOffset(klass, name);
    let info = getFieldInfo(klass, name);
    if (off < 0 || !info) {
        const backing = `<${name}>k__BackingField`;
        off = getFieldOffset(klass, backing);
        info = getFieldInfo(klass, backing);
    }
    if (off < 0 || !info) {
        fieldMetaCache.set(key, null);
        return null;
    }
    const fieldType = field_get_type(info) as NativePointer;
    if (fieldType.isNull()) {
        fieldMetaCache.set(key, null);
        return null;
    }
    // Il2CppType layout (Unity 6 / IL2CPP 2020+):
    //   data: void* @ +0x00 (8 bytes)
    //   bitfield @ +0x08..+0x0c packed as:
    //     attrs:16 @ +0x08-0x09
    //     type:8   @ +0x0a   ← what we want
    //     num_mods:5, byref:1, pinned:1, valuetype:1 @ +0x0b (bits)
    const tag = fieldType.add(0x0a).readU8();
    const classOfType = type_get_class_or_element_class(
        fieldType) as NativePointer;
    const meta: FieldMeta = { offset: off, info, fieldType, tag, classOfType };
    fieldMetaCache.set(key, meta);
    return meta;
}

// Path parsing — memoize parsed segments since paths repeat heavily on
// the hot loop (each event projects the same anchors with the same paths).
const parsedPathCache: Map<string, PathSegment[]> = new Map();
function parsePathCached(path: string): PathSegment[] {
    const cached = parsedPathCache.get(path);
    if (cached) return cached;
    const out: PathSegment[] = [];
    for (const raw of path.split(".")) {
        const m = /^(\w+)(?:\[(\d+)\])?$/.exec(raw.trim());
        if (!m) {
            out.push({ name: raw });
            continue;
        }
        const seg: PathSegment = { name: m[1] };
        if (m[2] !== undefined) seg.index = parseInt(m[2], 10);
        out.push(seg);
    }
    parsedPathCache.set(path, out);
    return out;
}

// On x86-64 IL2CPP, every managed object instance starts with a 0x10-byte
// header (klass* at +0x0, monitor/sync at +0x8). Field offsets returned
// by `il2cpp_field_get_offset` are relative to this header. When we
// access fields of a value-type INLINE inside another struct/class,
// we have to subtract this header to reach the inline base.
const VALUETYPE_HEADER = 0x10;

// IL2CPP type tags (Mono compatibility, see Il2CppType.h)
const TYPE_BOOLEAN     = 0x02;
const TYPE_CHAR        = 0x03;
const TYPE_I1          = 0x04;
const TYPE_U1          = 0x05;
const TYPE_I2          = 0x06;
const TYPE_U2          = 0x07;
const TYPE_I4          = 0x08;
const TYPE_U4          = 0x09;
const TYPE_I8          = 0x0a;
const TYPE_U8          = 0x0b;
const TYPE_R4          = 0x0c;
const TYPE_R8          = 0x0d;
const TYPE_STRING      = 0x0e;
const TYPE_VALUETYPE   = 0x11;
const TYPE_CLASS       = 0x12;
const TYPE_ARRAY       = 0x14;
const TYPE_GENERICINST = 0x15;
const TYPE_I           = 0x18;
const TYPE_U           = 0x19;
const TYPE_OBJECT      = 0x1c;
const TYPE_SZARRAY     = 0x1d;
const TYPE_ENUM        = 0x55;

// IL2CPP keeps a `valuetype: 1` bit for VALUETYPE/ENUM/Nullable<T>; the same
// flag is set on the Il2CppType bitfield byte at offset 0x11 (top bit).
// Practically, generic-inst layout: TYPE_GENERICINST always points to a
// Il2CppGenericClass — to know if it's a value-type, we check the bit
// in the Il2CppType.byval_arg `attrs` field. Easiest: re-read the
// `Il2CppType.type` byte and assume CLASS/OBJECT = ref, else value.

export type LeafKind =
    | "auto"     // infer from IL2CppType
    | "int" | "uint" | "long" | "ulong"
    | "byte" | "sbyte" | "short" | "ushort"
    | "float" | "double" | "bool" | "char"
    | "string"   // managed System.String → JS string
    | "fix64"    // FixedMath.NET Q31.32 → number
    | "ptr"      // raw pointer hex string
    | "cls"      // class name of the object pointed to
    | "enum"     // int32 value
    | "bentityid"; // BEntityId (int32 wrapper)

export interface PathSpec {
    /** Dotted path, e.g. "Position.Coordinate.Column" or "Tiles[0].Id".
     * `[i]` indexing supported on List<T> and arrays. */
    path: string;
    /** Output key (default: derived from path). */
    out?: string;
    /** Leaf read kind (default: auto-infer). */
    type?: LeafKind;
}

interface Hop {
    ptr: NativePointer;        // current address — for ref types it's the heap obj,
                               // for value types it's the inline base
    klass: NativePointer | null; // klass of the current ptr (null when leaf-only)
    isInline: boolean;         // true if currently at a value-type/struct base
}

function safeKlassName(klass: NativePointer): string {
    try {
        if (klass.isNull()) return "?";
        const n = s(class_get_name(klass) as NativePointer);
        return n || "?";
    } catch { return "?"; }
}

/** Read an arbitrary primitive leaf at `addr` based on the type tag. */
function readByTag(addr: NativePointer, tag: number): unknown {
    switch (tag) {
    case TYPE_BOOLEAN: return addr.readU8() !== 0;
    case TYPE_CHAR:    return String.fromCharCode(addr.readU16());
    case TYPE_I1:      return addr.readS8();
    case TYPE_U1:      return addr.readU8();
    case TYPE_I2:      return addr.readS16();
    case TYPE_U2:      return addr.readU16();
    case TYPE_I4:
    case TYPE_ENUM:    return addr.readS32();
    case TYPE_U4:      return addr.readU32();
    case TYPE_I8:      return addr.readS64().toString();
    case TYPE_U8:      return addr.readU64().toString();
    case TYPE_R4:      return addr.readFloat();
    case TYPE_R8:      return addr.readDouble();
    case TYPE_STRING:  return readIl2cppString(addr.readPointer());
    case TYPE_I:
    case TYPE_U:       return addr.readPointer().toString();
    default:           return null;
    }
}

/** Read leaf according to a user-supplied hint (overrides auto-infer). */
function readByHint(addr: NativePointer, kind: LeafKind): unknown {
    switch (kind) {
    case "int":
    case "enum":      return addr.readS32();
    case "uint":      return addr.readU32();
    case "long":      return addr.readS64().toString();
    case "ulong":     return addr.readU64().toString();
    case "byte":      return addr.readU8();
    case "sbyte":     return addr.readS8();
    case "short":     return addr.readS16();
    case "ushort":    return addr.readU16();
    case "float":     return addr.readFloat();
    case "double":    return addr.readDouble();
    case "bool":      return addr.readU8() !== 0;
    case "char":      return String.fromCharCode(addr.readU16());
    case "string":    return readIl2cppString(addr.readPointer());
    case "ptr":       return addr.readPointer().toString();
    case "cls": {
        const p = addr.readPointer();
        if (p.isNull()) return null;
        try {
            const klass = p.readPointer();
            return klass.isNull() ? null : safeKlassName(klass);
        } catch { return null; }
    }
    case "fix64": {
        // FixedMath.NET Q31.32 — single long m_rawValue at +0x0
        const lo = addr.readU32();
        const hi = addr.add(4).readS32();
        return hi + lo / 4294967296;
    }
    case "bentityid":
        // BEntityId is a single int32 wrapper struct
        return addr.readS32();
    }
    return null;
}

interface PathSegment {
    name: string;
    index?: number;   // [i] suffix
}


/** Walk a single path and return its leaf value, or null on failure. */
function walkPath(
    rootPtr: NativePointer, segments: PathSegment[], hint?: LeafKind,
): unknown {
    if (rootPtr.isNull()) return null;
    let cur: Hop = {
        ptr: rootPtr,
        klass: rootPtr.readPointer(),  // first qword of any heap obj is its klass*
        isInline: false,
    };

    for (let i = 0; i < segments.length; i++) {
        const seg = segments[i];
        const isLeaf = i === segments.length - 1;

        if (cur.klass === null || cur.klass.isNull()) return null;

        const meta = resolveField(cur.klass, seg.name);
        if (!meta) return null;
        const fieldType = meta.fieldType;
        const tag = meta.tag;

        // IL2CPP convention: il2cpp_field_get_offset returns the BOXED
        // offset (= inline offset + 0x10 header). For class-instance access
        // it lines up directly. For inline-struct field access (we just
        // stepped into a VALUETYPE), we must subtract the header. Without
        // this every nested struct read pulls from offset+0x10 of garbage.
        const adjOffset = cur.isInline
            ? meta.offset - VALUETYPE_HEADER
            : meta.offset;
        const fieldAddr = cur.ptr.add(adjOffset);

        // Leaf? Read directly.
        if (isLeaf) {
            // Index into List/SZArray field at the LEAF position is unusual
            // but supported (returns the i-th element ref/value as ptr/cls).
            if (seg.index !== undefined) {
                const itemAddr = readListIndexed(
                    fieldType, fieldAddr, seg.index, tag);
                if (itemAddr === null) return null;
                if (hint && hint !== "auto") {
                    return readByHint(itemAddr, hint);
                }
                return readByTag(itemAddr, TYPE_OBJECT) ?? itemAddr.toString();
            }
            if (hint && hint !== "auto") {
                return readByHint(fieldAddr, hint);
            }
            return readLeafAuto(fieldType, fieldAddr, tag);
        }

        // Non-leaf: advance to the next hop.
        const next = stepInto(fieldType, fieldAddr, tag, seg.index);
        if (!next) return null;
        cur = next;
    }
    return null;
}

/** Read a List<T>/Array element. fieldAddr points to the field slot. */
function readListIndexed(
    fieldType: NativePointer, fieldAddr: NativePointer,
    index: number, tag: number,
): NativePointer | null {
    // Array type (T[]): heap ptr at fieldAddr, then payload at +0x20
    if (tag === TYPE_SZARRAY || tag === TYPE_ARRAY) {
        const arr = fieldAddr.readPointer();
        if (arr.isNull()) return null;
        const len = arr.add(0x18).readS32();
        if (index < 0 || index >= len) return null;
        // Element size depends on T — for ref-types it's 8 (pointer)
        // For value-types it depends; we only handle ref arrays in v1
        // (tile lists are IList<IEntity> = ref).
        return arr.add(0x20 + index * Process.pointerSize);
    }
    // List<T>: heap ptr at fieldAddr → has _items: T[] at 0x10, _size: int @ 0x18
    if (tag === TYPE_CLASS || tag === TYPE_GENERICINST) {
        const list = fieldAddr.readPointer();
        if (list.isNull()) return null;
        const size = list.add(0x18).readS32();
        if (index < 0 || index >= size) return null;
        const items = list.add(0x10).readPointer();
        if (items.isNull()) return null;
        return items.add(0x20 + index * Process.pointerSize);
    }
    return null;
}

/** Compute the next hop after a field that's not the leaf. Returns null
 * if the segment can't be traversed (ref is null, type is unsupported). */
function stepInto(
    fieldType: NativePointer, fieldAddr: NativePointer,
    tag: number, index: number | undefined,
): Hop | null {
    // Index → List/Array indexing into a ref hop
    if (index !== undefined) {
        const itemAddr = readListIndexed(fieldType, fieldAddr, index, tag);
        if (itemAddr === null) return null;
        // For ref-typed list elements, itemAddr holds a heap pointer
        const itemPtr = itemAddr.readPointer();
        if (itemPtr.isNull()) return null;
        return {
            ptr: itemPtr,
            klass: itemPtr.readPointer(),
            isInline: false,
        };
    }

    switch (tag) {
    case TYPE_VALUETYPE:
    case TYPE_ENUM: {
        // Inline struct — keep ptr, switch klass to struct's class
        const klass = type_get_class_or_element_class(fieldType) as NativePointer;
        return { ptr: fieldAddr, klass, isInline: true };
    }
    case TYPE_GENERICINST: {
        // Could be value-type (Nullable<T>) or reference-type (List<T>).
        // Heuristic: try treating as ref (read pointer); if invalid (null
        // or unreadable), fall back to inline.
        const klass = type_get_class_or_element_class(fieldType) as NativePointer;
        // Probe: ref-types have their klass with refcount > 0 and reading
        // (fieldAddr).readPointer() yields a valid heap obj. We choose
        // based on the *class*'s value-type bit. Fallback path: treat all
        // GENERICINST that we see in this codebase (Nullable<T>) as inline
        // when the class is a known value-type wrapper. Simpler: try ref
        // first (most common: List<T>, IList<T>, Dictionary), inline second.
        const refPtr = fieldAddr.readPointer();
        if (!refPtr.isNull()) {
            try {
                const probedKlass = refPtr.readPointer();
                if (!probedKlass.isNull()) {
                    return { ptr: refPtr, klass: probedKlass, isInline: false };
                }
            } catch { /* try inline path */ }
        }
        // Inline fallback — treat as struct
        return { ptr: fieldAddr, klass, isInline: true };
    }
    case TYPE_CLASS:
    case TYPE_OBJECT:
    case TYPE_STRING:
    case TYPE_SZARRAY:
    case TYPE_ARRAY: {
        const refPtr = fieldAddr.readPointer();
        if (refPtr.isNull()) return null;
        let klass: NativePointer;
        try {
            klass = refPtr.readPointer();
            if (klass.isNull()) return null;
        } catch { return null; }
        return { ptr: refPtr, klass, isInline: false };
    }
    default:
        // Primitive types can't be a non-leaf — dead end
        return null;
    }
}

/** Auto-infer leaf value from IL2CppType byte. */
function readLeafAuto(
    fieldType: NativePointer, fieldAddr: NativePointer, tag: number,
): unknown {
    if (tag === TYPE_VALUETYPE || tag === TYPE_ENUM) {
        // For most game enums, treat as int32. For Fix64, special-case:
        // it's TYPE_VALUETYPE wrapping `long m_rawValue`. Without runtime
        // type-name introspection we can't tell — so default to enum/int32.
        // Callers should hint "fix64" when the leaf is a Fix64 field.
        const klass = type_get_class_or_element_class(fieldType) as NativePointer;
        const klassName = safeKlassName(klass);
        if (klassName === "Fix64") {
            const lo = fieldAddr.readU32();
            const hi = fieldAddr.add(4).readS32();
            return hi + lo / 4294967296;
        }
        if (klassName === "BEntityId") {
            return fieldAddr.readS32();
        }
        return readByTag(fieldAddr, TYPE_I4);
    }
    if (tag === TYPE_GENERICINST) {
        // Likely a Nullable<T> if value-type generic. Read hasValue at
        // sizeof(T)... but without resolving T we can't. Return null
        // marker to signal "unread generic" — caller should hint.
        return null;
    }
    if (tag === TYPE_CLASS || tag === TYPE_OBJECT) {
        // Default for ref-type leaf: return ptr hex. To get class name,
        // user should hint "cls".
        const p = fieldAddr.readPointer();
        return p.isNull() ? null : p.toString();
    }
    return readByTag(fieldAddr, tag);
}

/** Project an IL2CPP managed object to a JSON-serializable record by walking
 * a list of paths. Returns one entry per path; missing paths produce null
 * silently (resilient to schema drift across game patches). */
export function projectPaths(
    rootPtr: NativePointer, paths: PathSpec[],
): Record<string, unknown> {
    const out: Record<string, unknown> = {};
    if (rootPtr.isNull()) return out;
    for (const spec of paths) {
        const segments = parsePathCached(spec.path);
        const key = spec.out ?? spec.path;
        try {
            out[key] = walkPath(rootPtr, segments, spec.type ?? "auto");
        } catch {
            out[key] = null;
        }
    }
    return out;
}

// RETIRE (#480-r7) : `projectFromBase` (63 lignes) et son unique appelee `continueInline`
// (46 lignes) n'avaient AUCUN appelant. `projectFromBase` etait une variante de
// `projectPaths` pour un base-pointer de struct INLINE, ecrite pour `UnitPosition` ; ce
// chemin est couvert par `projectPaths` + `stepInto`, qui traitent l'inline via
// `next.isInline`. Le retrait est en CASCADE et c'est voulu : garder `continueInline`
// apres avoir retire son seul appelant aurait converti un mort EXPORTE (mesurable) en
// mort PRIVE (invisible au recensement).
