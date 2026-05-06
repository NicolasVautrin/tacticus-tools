// Thin wrappers around Newtonsoft.Json:
//   - JsonConvert.SerializeObject(object) → json string     — dump RPCs
//   - JsonConvert.DeserializeObject(string, Type, settings) — Phase 3 launch
//     The 3-arg variant is the only DeserializeObject that survives IL2CPP
//     AOT stripping; `PopulateObject` is stripped entirely. Type is obtained
//     via il2cpp_type_get_object(il2cpp_class_get_type(klass)).

import {
    class_get_methods, findClassAnywhere, getSystemType, method_get_name,
    method_get_param_count, s,
} from "./helpers.js";
import { createManagedString, invokeMethod } from "./invoke.js";

function findStaticMethod(
    cls: NativePointer, name: string, paramCount: number,
): NativePointer | null {
    const it = Memory.alloc(Process.pointerSize);
    it.writePointer(ptr(0));
    let m: NativePointer;
    while (!(m = class_get_methods(cls, it) as NativePointer).isNull()) {
        if (s(method_get_name(m) as NativePointer) !== name) continue;
        if ((method_get_param_count(m) as number) !== paramCount) continue;
        return m;
    }
    return null;
}

const jsonConvertClass = findClassAnywhere("Newtonsoft.Json", "JsonConvert");
const serializeMi = jsonConvertClass
    ? findStaticMethod(jsonConvertClass, "SerializeObject", 1) : null;
const deserializeMi = jsonConvertClass
    ? findStaticMethod(jsonConvertClass, "DeserializeObject", 3) : null;

export function isSerializerReady(): boolean {
    return serializeMi !== null;
}

export function isDeserializerReady(): boolean {
    return deserializeMi !== null;
}

/** Read a potentially large (up to 20 MB) managed System.String. */
function readLargeString(p: NativePointer): string | null {
    if (p.isNull()) return null;
    const len = p.add(0x10).readS32();
    if (len <= 0 || len > 20_000_000) return null;
    return p.add(0x14).readUtf16String(len);
}

/** Newtonsoft-serialize an IL2CPP object to a JSON string. null on failure. */
export function serializeToJson(objPtr: NativePointer): string | null {
    if (!serializeMi || objPtr.isNull()) return null;
    let jp: NativePointer;
    try { jp = invokeMethod(serializeMi, ptr(0), [objPtr]); }
    catch { return null; }
    if (jp.isNull()) return null;
    return readLargeString(jp);
}

/** Deserialize a JSON string into an IL2CPP object of type `klass` via
 * JsonConvert.DeserializeObject(string value, Type type, JsonSerializerSettings settings). */
export function deserializeFromJson(
    json: string, klass: NativePointer,
): NativePointer {
    if (!deserializeMi) throw new Error("JsonConvert.DeserializeObject not found");
    const jsonStr = createManagedString(json);
    const typeObj = getSystemType(klass);
    const result = invokeMethod(deserializeMi, ptr(0), [jsonStr, typeObj, ptr(0)]);
    if (result.isNull()) throw new Error("DeserializeObject returned null");
    return result;
}
