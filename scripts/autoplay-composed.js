// util: IL2CPP Helpers — shared NativeFunction wrappers, class/method resolution, message parsing
// provides: il2cpp, il2cppBase, il2cppSize, s(), getStack(), findClass(), findMethod(),
//           hook(), readMsgClass(), readMsgDetails()

var il2cpp = Process.findModuleByName("libil2cpp.so");
var il2cppBase = il2cpp.base;
var il2cppSize = il2cpp.size;

// --- IL2CPP C API wrappers ---
var domain_get = new NativeFunction(il2cpp.findExportByName("il2cpp_domain_get"), "pointer", []);
var domain_get_assemblies = new NativeFunction(il2cpp.findExportByName("il2cpp_domain_get_assemblies"), "pointer", ["pointer", "pointer"]);
var assembly_get_image = new NativeFunction(il2cpp.findExportByName("il2cpp_assembly_get_image"), "pointer", ["pointer"]);
var image_get_class_count = new NativeFunction(il2cpp.findExportByName("il2cpp_image_get_class_count"), "uint32", ["pointer"]);
var image_get_class = new NativeFunction(il2cpp.findExportByName("il2cpp_image_get_class"), "pointer", ["pointer", "uint32"]);
var class_get_name = new NativeFunction(il2cpp.findExportByName("il2cpp_class_get_name"), "pointer", ["pointer"]);
var class_get_namespace = new NativeFunction(il2cpp.findExportByName("il2cpp_class_get_namespace"), "pointer", ["pointer"]);
var image_get_name = new NativeFunction(il2cpp.findExportByName("il2cpp_image_get_name"), "pointer", ["pointer"]);
var class_get_methods = new NativeFunction(il2cpp.findExportByName("il2cpp_class_get_methods"), "pointer", ["pointer", "pointer"]);
var method_get_name = new NativeFunction(il2cpp.findExportByName("il2cpp_method_get_name"), "pointer", ["pointer"]);

// --- Helpers ---

function s(p) {
    try { return p.readUtf8String() || ""; } catch (e) { return ""; }
}

// --- Stack trace (raw offsets — resolved by backend via symbols.json) ---

function getStack(ctx) {
    var bt = Thread.backtrace(ctx, Backtracer.ACCURATE);
    var frames = [];
    for (var i = 0; i < Math.min(bt.length, 15); i++) {
        var addr = bt[i];
        var off = addr.sub(il2cppBase);
        if (off.compare(0) >= 0 && off.compare(il2cppSize) < 0) {
            frames.push(off.toInt32());
        }
    }
    return frames;
}

// --- Class / method resolution (cached) ---

var classCache = {};
function findClass(asm, ns, cls) {
    var key = asm + "::" + ns + "." + cls;
    if (classCache[key]) return classCache[key];
    var domain = domain_get();
    var sizePtr = Memory.alloc(4);
    var assemblies = domain_get_assemblies(domain, sizePtr);
    var count = sizePtr.readU32();
    for (var i = 0; i < count; i++) {
        var assembly = assemblies.add(i * Process.pointerSize).readPointer();
        var image = assembly_get_image(assembly);
        if (s(image_get_name(image)) !== asm) continue;
        var cc = image_get_class_count(image);
        for (var j = 0; j < cc; j++) {
            var k = image_get_class(image, j);
            if (s(class_get_name(k)) === cls && s(class_get_namespace(k)) === ns) {
                classCache[key] = k;
                return k;
            }
        }
    }
    return null;
}

function findMethod(klass, name) {
    var it = Memory.alloc(Process.pointerSize);
    it.writePointer(ptr(0));
    var m;
    while (!(m = class_get_methods(klass, it)).isNull()) {
        if (s(method_get_name(m)) === name) return { info: m, ptr: m.readPointer() };
    }
    return null;
}

function hook(asm, ns, cls, mth, cb) {
    var k = findClass(asm, ns, cls);
    if (!k) { console.log("[-] " + cls + " not found"); return; }
    var m = findMethod(k, mth);
    if (!m || m.ptr.isNull()) { console.log("[-] " + cls + "." + mth + " not found"); return; }
    try {
        Interceptor.attach(m.ptr, cb);
        console.log("[+] " + cls + "." + mth);
    } catch (e) {
        console.log("[!] " + cls + "." + mth + " — cannot hook: " + e.message);
    }
}

// --- Field offset resolution (cached) ---

var class_get_fields = new NativeFunction(il2cpp.findExportByName("il2cpp_class_get_fields"), "pointer", ["pointer", "pointer"]);
var class_get_parent = new NativeFunction(il2cpp.findExportByName("il2cpp_class_get_parent"), "pointer", ["pointer"]);
var field_get_name = new NativeFunction(il2cpp.findExportByName("il2cpp_field_get_name"), "pointer", ["pointer"]);
var field_get_offset = new NativeFunction(il2cpp.findExportByName("il2cpp_field_get_offset"), "int32", ["pointer"]);

var fieldOffsetCache = {};
function getFieldOffset(klass, fieldName) {
    var key = klass.toString() + "." + fieldName;
    if (fieldOffsetCache[key] !== undefined) return fieldOffsetCache[key];
    // Walk up the class hierarchy to find inherited fields
    var k = klass;
    while (!k.isNull()) {
        var it = Memory.alloc(Process.pointerSize); it.writePointer(ptr(0));
        var f;
        while (!(f = class_get_fields(k, it)).isNull()) {
            if (s(field_get_name(f)) === fieldName) {
                var off = field_get_offset(f);
                fieldOffsetCache[key] = off;
                return off;
            }
        }
        k = class_get_parent(k);
    }
    fieldOffsetCache[key] = -1;
    return -1;
}

// --- IL2CPP string reader ---

function readIl2cppString(objPtr) {
    if (objPtr.isNull()) return null;
    try {
        var len = objPtr.add(0x10).readS32();
        if (len <= 0 || len > 500) return null;
        return objPtr.add(0x14).readUtf16String(len);
    } catch (e) { return null; }
}

// --- Message parsing ---

function readMsgClass(msgPtr) {
    try { return s(class_get_name(msgPtr.readPointer())); } catch (e) { return "?"; }
}

function readMsgDetails(msg) {
    var cls = readMsgClass(msg);
    // Serialize the full message for comparison
    var d = serialize(msg, 3);
    d.msg = cls;
    return d;
}

console.log("[*] IL2CPP helpers loaded");
// util: IL2CPP Object creation & method invocation
// requires: _utils/il2cpp-helpers
// provides: il2cpp_object_new(), il2cpp_runtime_invoke(), invokeMethod(), createObject()

var il2cpp_object_new = new NativeFunction(
    il2cpp.findExportByName("il2cpp_object_new"), "pointer", ["pointer"]);
var il2cpp_runtime_invoke = new NativeFunction(
    il2cpp.findExportByName("il2cpp_runtime_invoke"), "pointer",
    ["pointer", "pointer", "pointer", "pointer"]);

function invokeMethod(methodInfo, obj, args) {
    var exc = Memory.alloc(Process.pointerSize);
    exc.writePointer(ptr(0));
    var params = ptr(0);
    if (args && args.length > 0) {
        params = Memory.alloc(args.length * Process.pointerSize);
        for (var i = 0; i < args.length; i++) {
            params.add(i * Process.pointerSize).writePointer(args[i]);
        }
    }
    var result = il2cpp_runtime_invoke(methodInfo, obj, params, exc);
    var excVal = exc.readPointer();
    if (!excVal.isNull()) {
        var excMsg = "IL2CPP exception";
        try {
            excMsg += " (" + s(class_get_name(excVal.readPointer())) + ")";
        } catch(e) {}
        throw new Error(excMsg);
    }
    return result;
}

function createObject(klass) {
    var obj = il2cpp_object_new(klass);
    if (obj.isNull()) throw new Error("il2cpp_object_new returned null");
    var ctor = findMethod(klass, ".ctor");
    if (ctor) invokeMethod(ctor.info, obj, null);
    return obj;
}

console.log("[*] IL2CPP invoke loaded");
// util: IL2CPP Serializer — generic runtime object -> JSON serializer
// requires: _utils/il2cpp-helpers (for s(), findClass, il2cpp module)
// provides: serialize(objPtr, maxDepth) -> plain JS object

// --- Additional IL2CPP API for type introspection ---
var field_get_type = new NativeFunction(il2cpp.findExportByName("il2cpp_field_get_type"), "pointer", ["pointer"]);
var type_get_type = new NativeFunction(il2cpp.findExportByName("il2cpp_type_get_type"), "int32", ["pointer"]);
var type_get_name = new NativeFunction(il2cpp.findExportByName("il2cpp_type_get_name"), "pointer", ["pointer"]);
var class_from_type = new NativeFunction(il2cpp.findExportByName("il2cpp_class_from_type"), "pointer", ["pointer"]);
var class_is_enum = new NativeFunction(il2cpp.findExportByName("il2cpp_class_is_enum"), "int32", ["pointer"]);
var class_is_valuetype = new NativeFunction(il2cpp.findExportByName("il2cpp_class_is_valuetype"), "int32", ["pointer"]);
var class_get_parent = new NativeFunction(il2cpp.findExportByName("il2cpp_class_get_parent"), "pointer", ["pointer"]);
var class_get_element_class = new NativeFunction(il2cpp.findExportByName("il2cpp_class_get_element_class"), "pointer", ["pointer"]);
var class_instance_size = new NativeFunction(il2cpp.findExportByName("il2cpp_class_instance_size"), "uint32", ["pointer"]);

// IL2CPP type enum values
var TYPE_BOOLEAN = 2;
var TYPE_CHAR = 3;
var TYPE_I1 = 4;
var TYPE_U1 = 5;
var TYPE_I2 = 6;
var TYPE_U2 = 7;
var TYPE_I4 = 8;
var TYPE_U4 = 9;
var TYPE_I8 = 10;
var TYPE_U8 = 11;
var TYPE_R4 = 12;
var TYPE_R8 = 13;
var TYPE_STRING = 14;
var TYPE_PTR = 15;
var TYPE_VALUETYPE = 17;
var TYPE_CLASS = 18;
var TYPE_ARRAY = 20;
var TYPE_GENERICINST = 21;
var TYPE_I = 24;    // IntPtr
var TYPE_U = 25;    // UIntPtr
var TYPE_OBJECT = 28;
var TYPE_SZARRAY = 0x1D;  // 29 — IL2CPP_TYPE_SZARRAY

// --- Circular reference guard ---
var _visiting = {};
var _visitId = 0;

// --- Skip fields that cause problems or are not useful ---
var SKIP_FIELDS = {
    "EntityTypeMapping": true,  // static dictionary, huge
    "_feetEnumerator": true,    // enumerator state, not useful
    "_caches": true,
    "_cacheInvalidator": true,
};

// --- Read a primitive value at a given address based on IL2CPP type ---
function readPrimitive(addr, typeEnum) {
    switch (typeEnum) {
        case TYPE_BOOLEAN: return addr.readU8() !== 0;
        case TYPE_CHAR:    return addr.readU16();
        case TYPE_I1:      return addr.readS8();
        case TYPE_U1:      return addr.readU8();
        case TYPE_I2:      return addr.readS16();
        case TYPE_U2:      return addr.readU16();
        case TYPE_I4:      return addr.readS32();
        case TYPE_U4:      return addr.readU32();
        case TYPE_I8:      return addr.readS64();
        case TYPE_U8:      return addr.readU64();
        case TYPE_R4:      return addr.readFloat();
        case TYPE_R8:      return addr.readDouble();
        default:           return null;
    }
}

// --- Read an IL2CPP array (szarray) ---
function readSzArray(arrPtr, depth) {
    if (arrPtr.isNull()) return null;
    try {
        var len = arrPtr.add(0x18).readS32();
        if (len <= 0 || len > 500) return { _array: true, length: len };
        // Get element class from array klass
        var arrKlass = arrPtr.readPointer();
        var elemKlass = class_get_element_class(arrKlass);
        var isValueType = class_is_valuetype(elemKlass) !== 0;
        var elemSize = isValueType ? class_instance_size(elemKlass) - (2 * Process.pointerSize) : Process.pointerSize;
        // Simple heuristic: if element is a reference type, read pointers
        var result = [];
        for (var i = 0; i < Math.min(len, 100); i++) {
            var elemAddr = arrPtr.add(0x20 + i * (isValueType ? elemSize : Process.pointerSize));
            if (isValueType) {
                // For value types in arrays, try reading as int
                result.push(elemAddr.readS32());
            } else {
                var elem = elemAddr.readPointer();
                if (elem.isNull()) {
                    result.push(null);
                } else {
                    result.push(serialize(elem, depth - 1));
                }
            }
        }
        if (len > 100) result.push("... (" + len + " total)");
        return result;
    } catch(e) {
        return { _error: "array read: " + e.message };
    }
}

// --- Read a List<T> ---
function readList(listPtr, depth) {
    if (listPtr.isNull()) return null;
    try {
        var items = listPtr.add(0x10).readPointer();
        var size = listPtr.add(0x18).readS32();
        if (items.isNull() || size < 0) return { _list: true, size: size };
        if (size === 0) return [];
        if (size > 500) return { _list: true, size: size, _truncated: true };
        // Read the underlying array
        var arrKlass = items.readPointer();
        var elemKlass = class_get_element_class(arrKlass);
        var isValueType = class_is_valuetype(elemKlass) !== 0;
        var result = [];
        var limit = Math.min(size, 200);
        for (var i = 0; i < limit; i++) {
            if (isValueType) {
                var elemSize = class_instance_size(elemKlass) - (2 * Process.pointerSize);
                var elemAddr = items.add(0x20 + i * elemSize);
                result.push(elemAddr.readS32());
            } else {
                var elem = items.add(0x20 + i * Process.pointerSize).readPointer();
                if (elem.isNull()) {
                    result.push(null);
                } else {
                    result.push(serialize(elem, depth - 1));
                }
            }
        }
        if (size > limit) result.push("... (" + size + " total)");
        return result;
    } catch(e) {
        return { _error: "list read: " + e.message };
    }
}

// --- Read a Dictionary<K,V> ---
// Layout: [klass:8][monitor:8][_buckets:8][_entries:8][_count:4][_freeList:4][_freeCount:4][_version:4]...
// _entries is an array of Entry structs. Entry fields are introspected from the array element class.
function readDict(dictPtr, depth) {
    if (dictPtr.isNull()) return null;
    try {
        var count = dictPtr.add(0x20).readS32();
        if (count <= 0) return {};
        if (count > 200) return { _dict: true, count: count, _truncated: true };

        var entries = dictPtr.add(0x18).readPointer();
        if (entries.isNull()) return { _dict: true, count: count, entries: "null" };

        // Introspect Entry struct from the entries array element class
        var entriesKlass = entries.readPointer(); // array klass
        var entryKlass = class_get_element_class(entriesKlass); // Entry struct class
        var entrySize = class_instance_size(entryKlass);
        // Entry has fields: hashCode, next, key, value — find key and value offsets + types
        var keyOff = -1, valOff = -1;
        var keyEnumType = null, valEnumType = null;
        var keyTypeEnum = -1, valTypeEnum = -1;
        var keyIl2cppType = null, valIl2cppType = null;
        var it = Memory.alloc(Process.pointerSize); it.writePointer(ptr(0));
        var f;
        while (!(f = class_get_fields(entryKlass, it)).isNull()) {
            var fname = s(field_get_name(f));
            var foff = field_get_offset(f);
            if (fname === "key") {
                keyOff = foff;
                var ft = field_get_type(f);
                keyTypeEnum = type_get_type(ft);
                keyIl2cppType = ft;
                var fk = class_from_type(ft);
                if (class_is_enum(fk)) {
                    keyEnumType = s(class_get_namespace(fk)) + "." + s(class_get_name(fk));
                }
            } else if (fname === "value") {
                valOff = foff;
                var ft2 = field_get_type(f);
                valTypeEnum = type_get_type(ft2);
                valIl2cppType = ft2;
                var fk2 = class_from_type(ft2);
                if (class_is_enum(fk2)) {
                    valEnumType = s(class_get_namespace(fk2)) + "." + s(class_get_name(fk2));
                }
            }
        }
        if (keyOff < 0 || valOff < 0) return { _dict: true, count: count, _error: "no key/value fields" };

        // entrySize from instance_size includes object header (16 bytes) for value types
        // Actual struct size = instance_size - 16 (no object header in array elements)
        var structSize = entrySize - 16;
        if (structSize <= 0) structSize = 16; // fallback

        var result = {};
        for (var i = 0; i < count; i++) {
            var entryBase = entries.add(0x20 + i * structSize);
            var hashCode = entryBase.readS32();
            if (hashCode < 0) continue; // deleted entry
            // offsets within Entry include the 16-byte "header" from instance_size calculation
            // but in an array, entries are packed without headers, so subtract 16
            var keyAddr = entryBase.add(keyOff - 16);
            var valAddr = entryBase.add(valOff - 16);

            // Read key
            var keyStr;
            if (keyEnumType) {
                keyStr = JSON.stringify({_enum: keyEnumType, _value: keyAddr.readS32()});
            } else if (keyTypeEnum === TYPE_STRING) {
                var kp = keyAddr.readPointer();
                keyStr = kp.isNull() ? "null" : readIl2cppString(kp);
            } else {
                keyStr = keyAddr.readS32().toString();
            }

            // Read value — cap depth at 1 to avoid recursive explosion
            var value;
            if (valEnumType) {
                value = {_enum: valEnumType, _value: valAddr.readS32()};
            } else {
                try {
                    value = readFieldValue(valAddr, valTypeEnum, valIl2cppType, Math.min(depth, 2));
                } catch(e) {
                    value = valAddr.readS32();
                }
            }

            result[keyStr] = value;
        }
        return result;
    } catch(e) {
        return { _error: "dict read: " + e.message };
    }
}

// --- Read a valuetype (struct or enum) at an inline address ---
function readValueType(addr, klass, depth) {
    // Check if it's an enum
    if (class_is_enum(klass) !== 0) {
        // Enums are backed by an integer
        return addr.readS32();
    }
    // For Nullable<T>, check hasValue
    var className = s(class_get_name(klass));
    if (className.indexOf("Nullable") === 0) {
        // Nullable<T> has: T value at offset 0, bool hasValue after T
        // But layout varies. Try: if first 4 bytes look like a value and next byte is 0/1
        try {
            // Simple heuristic: just return the int value or null
            return addr.readS32();
        } catch(e) { return null; }
    }
    // Generic struct: enumerate fields
    if (depth <= 0) return { _struct: className };
    var result = { _type: className };
    var it = Memory.alloc(Process.pointerSize); it.writePointer(ptr(0));
    var f;
    while (!(f = class_get_fields(klass, it)).isNull()) {
        var fname = s(field_get_name(f));
        var foff = field_get_offset(f);
        var ftype = field_get_type(f);
        var ftypeEnum = type_get_type(ftype);
        try {
            // For inline structs, offset is relative to the struct start, minus the object header
            // But for fields on a valuetype, offsets already include the header. Subtract it:
            var fieldAddr = addr.add(foff - (2 * Process.pointerSize));
            result[fname] = readFieldValue(fieldAddr, ftypeEnum, ftype, depth - 1);
        } catch(e) {
            result[fname] = { _error: e.message };
        }
    }
    return result;
}

// --- Read a single field value ---
function readFieldValue(addr, typeEnum, il2cppType, depth) {
    // Primitives
    if (typeEnum >= TYPE_BOOLEAN && typeEnum <= TYPE_R8) {
        return readPrimitive(addr, typeEnum);
    }
    // String
    if (typeEnum === TYPE_STRING) {
        var strPtr = addr.readPointer();
        if (strPtr.isNull()) return null;
        return readIl2cppString(strPtr);
    }
    // Value type (struct or enum)
    if (typeEnum === TYPE_VALUETYPE) {
        var vtKlass = class_from_type(il2cppType);
        return readValueType(addr, vtKlass, depth);
    }
    // Class / object reference
    if (typeEnum === TYPE_CLASS || typeEnum === TYPE_OBJECT) {
        var objPtr = addr.readPointer();
        if (objPtr.isNull()) return null;
        if (depth <= 0) {
            try { return { _ref: s(class_get_name(objPtr.readPointer())) }; } catch(e) { return { _ref: "?" }; }
        }
        return serialize(objPtr, depth - 1);
    }
    // Generic instance (List<T>, Dictionary<K,V>, etc.)
    if (typeEnum === TYPE_GENERICINST) {
        var objPtr = addr.readPointer();
        if (objPtr.isNull()) return null;
        // Detect List vs Dict by class name
        try {
            var objKlass = objPtr.readPointer();
            var objClassName = s(class_get_name(objKlass));
            if (objClassName === "List`1") {
                return readList(objPtr, depth);
            } else if (objClassName === "Dictionary`2") {
                return readDict(objPtr, depth);
            } else if (objClassName.indexOf("KeyedCollection") >= 0 || objClassName.indexOf("OrderedSet") >= 0 || objClassName.indexOf("Set") >= 0) {
                return { _type: objClassName };
            }
            // Other generic: try serialize
            if (depth <= 0) return { _ref: objClassName };
            return serialize(objPtr, depth - 1);
        } catch(e) {
            return { _error: "generic: " + e.message };
        }
    }
    // SZArray (T[])
    if (typeEnum === TYPE_SZARRAY) {
        var arrPtr = addr.readPointer();
        if (arrPtr.isNull()) return null;
        return readSzArray(arrPtr, depth);
    }
    // IntPtr / UIntPtr
    if (typeEnum === TYPE_I || typeEnum === TYPE_U) {
        return addr.readPointer().toString();
    }
    // Fallback
    return { _unknownType: typeEnum };
}

// --- Lightweight reader for ability collections ---

// Read only primitive fields (int, bool, enum) from an object — skip references.
// Fast and safe: no recursion, no depth, no circular refs.
function serializeFlat(objPtr) {
    if (objPtr.isNull()) return null;
    try {
        var klass = objPtr.readPointer();
        var result = {_class: s(class_get_name(klass))};
        var cur = klass;
        while (!cur.isNull()) {
            var cn = s(class_get_name(cur));
            if (cn === "Object" || cn === "ValueType") break;
            var it = Memory.alloc(Process.pointerSize); it.writePointer(ptr(0));
            var f;
            while (!(f = class_get_fields(cur, it)).isNull()) {
                var fn = s(field_get_name(f));
                var foff = field_get_offset(f);
                if (foff <= 0) continue;
                var ft = field_get_type(f);
                var te = type_get_type(ft);
                var displayName = fn.replace(/<(.+)>k__BackingField/, "$1");
                try {
                    if (te >= TYPE_BOOLEAN && te <= TYPE_R8) {
                        result[displayName] = readPrimitive(objPtr.add(foff), te);
                    } else if (te === TYPE_VALUETYPE) {
                        // Enums and small structs (wrappers like ConfigId) — read as int
                        result[displayName] = objPtr.add(foff).readS32();
                    } else if (te === TYPE_GENERICINST) {
                        // Handle Nullable<T> — value at +0, hasValue at +sizeof(T)
                        var vtKlass = class_from_type(ft);
                        var vtName = s(class_get_name(vtKlass));
                        if (vtName.indexOf("Nullable") === 0) {
                            var hasValue = objPtr.add(foff + 4).readU8() !== 0;
                            result[displayName] = hasValue ? objPtr.add(foff).readS32() : null;
                        }
                    } else if (te === TYPE_STRING) {
                        var sp = objPtr.add(foff).readPointer();
                        if (!sp.isNull()) result[displayName] = readIl2cppString(sp);
                    }
                    // skip references, arrays — that's the point
                } catch(e) {}
            }
            cur = class_get_parent(cur);
        }
        return result;
    } catch(e) { return {_error: e.message}; }
}

// Read a KeyedCollection for AbilityComponent — uses serializeFlat on each item
function readAbilitiesCollection(objPtr) {
    if (objPtr.isNull()) return [];
    try {
        var items = objPtr.add(0x10).readPointer(); // Collection<T>.items at 0x10
        if (items.isNull()) return [];
        var size = items.add(0x18).readS32();
        if (size <= 0 || size > 50) return [];
        var arr = items.add(0x10).readPointer();
        if (arr.isNull()) return [];
        var result = [];
        for (var i = 0; i < size; i++) {
            var elem = arr.add(0x20 + i * Process.pointerSize).readPointer();
            result.push(elem.isNull() ? null : serializeFlat(elem));
        }
        return result;
    } catch(e) { return {_error: e.message}; }
}

var ABILITY_COLLECTION_FIELDS = {"Abilities": true};

// --- Main serialize function ---
function serialize(objPtr, maxDepth) {
    if (maxDepth === undefined) maxDepth = 3;
    if (objPtr.isNull()) return null;
    if (maxDepth <= 0) {
        try { return { _ref: s(class_get_name(objPtr.readPointer())) }; } catch(e) { return { _ref: "?" }; }
    }

    // Circular reference check
    var ptrKey = objPtr.toString();
    if (_visiting[ptrKey]) return { _circular: true };
    _visiting[ptrKey] = true;

    var result = {};
    try {
        var klass = objPtr.readPointer();
        var className = s(class_get_name(klass));
        var namespace = s(class_get_namespace(klass));
        result._class = className;

        // Special case: string
        if (className === "String") {
            delete _visiting[ptrKey];
            return readIl2cppString(objPtr);
        }

        // Walk the class hierarchy (current + parents)
        var current = klass;
        while (!current.isNull()) {
            var parentName = s(class_get_name(current));
            if (parentName === "Object" || parentName === "ValueType") break;

            var it = Memory.alloc(Process.pointerSize); it.writePointer(ptr(0));
            var f;
            while (!(f = class_get_fields(current, it)).isNull()) {
                var fname = s(field_get_name(f));
                // Clean up backing field names
                var displayName = fname.replace(/<(.+)>k__BackingField/, "$1");
                if (SKIP_FIELDS[fname] || SKIP_FIELDS[displayName]) continue;

                var foff = field_get_offset(f);
                if (foff <= 0) continue; // skip static fields (offset 0 or negative in some builds)

                var ftype = field_get_type(f);
                var ftypeEnum = type_get_type(ftype);

                try {
                    var fieldAddr = objPtr.add(foff);
                    // Intercept Abilities field on AbilityComponents — use flat reader
                    if (displayName === "Abilities"
                        && (className === "ActiveAbilityComponent" || className === "TriggeredAbilityComponent")) {
                        var kcPtr = fieldAddr.readPointer();
                        result[displayName] = kcPtr.isNull() ? [] : readAbilitiesCollection(kcPtr);
                    } else {
                        result[displayName] = readFieldValue(fieldAddr, ftypeEnum, ftype, maxDepth - 1);
                    }
                } catch(e) {
                    result[displayName] = { _error: e.message };
                }
            }

            current = class_get_parent(current);
        }
    } catch(e) {
        result._error = e.message;
    }

    delete _visiting[ptrKey];
    return result;
}

console.log("[*] IL2CPP serializer loaded");
// util: MatchState reader — runner access, turn detection, raw serialization, game queries
// requires: _utils/il2cpp-helpers, _utils/il2cpp-invoke, _utils/il2cpp-serializer
// provides: runnerInstance, isPlayerTurn(), getSerializedState(),
//           getEntityById(), getUnitTile(), queryReachableTiles(), queryDamagePrediction()

// --- Runner ---
var runnerClass = findClass("BattleLogicAssembly.dll", "IdunBattle.Runner", "IdunRunner");
var runnerApplyInfo = findMethod(runnerClass, "Apply");
var runnerStateOff = getFieldOffset(runnerClass, "_state");
var runnerPathfindersOff = getFieldOffset(runnerClass, "<Pathfinders>k__BackingField");
var runnerDamagePredOff = getFieldOffset(runnerClass, "<DamagePrediction>k__BackingField");
var runnerTargetingOff = getFieldOffset(runnerClass, "<TargetingQuery>k__BackingField");

// --- Entity offsets (for lookup + turn detection) ---
var _entityClass = findClass("BattleLogicAssembly.dll", "IdunBattle.Core", "Entity");
var _entityIdOff = getFieldOffset(_entityClass, "<Id>k__BackingField");
var _entityTypeOff = getFieldOffset(_entityClass, "<Type>k__BackingField");
var _entityComponentsOff = getFieldOffset(_entityClass, "Components");
var _msEntitiesOff = getFieldOffset(
    findClass("BattleLogicAssembly.dll", "IdunBattle.Core", "MatchState"), "_entities");

// --- Turn detection offsets ---
var _turnCompClass = findClass("BattleLogicAssembly.dll", "IdunBattle.Entities.Components", "TurnComponent");
var _turnCurrentPlayerOff = _turnCompClass ? getFieldOffset(_turnCompClass, "_currentPlayerId") : -1;
var _playerCompClass = findClass("BattleLogicAssembly.dll", "IdunBattle.Entities.Components", "PlayerComponent");
var _playerTypeOff = _playerCompClass ? getFieldOffset(_playerCompClass, "Type") : -1;

// --- Foot component offsets (for unit -> tile lookup) ---
var _footCompClass = findClass("BattleLogicAssembly.dll", "IdunBattle.Entities.Components", "UnitFootComponent");
var _footUnitIdOff = _footCompClass ? getFieldOffset(_footCompClass, "UnitId") : -1;
var _footTileIdOff = _footCompClass ? getFieldOffset(_footCompClass, "TileId") : -1;

// --- Movement component (for reachable tiles depth) ---
var _moveCompClass = findClass("BattleLogicAssembly.dll", "IdunBattle.Entities.Components", "MovementComponent");
var _moveInitialOff = _moveCompClass ? getFieldOffset(_moveCompClass, "InitialValue") : -1;

// --- Game service classes + methods ---
var _pathfindersClass = findClass("BattleLogicAssembly.dll", "IdunBattle.Entities.Pathfinding", "Pathfinders");
var _findReachableInfo = _pathfindersClass ? findMethod(_pathfindersClass, "FindReachableTiles") : null;

var _damagePredClass = findClass("BattleLogicAssembly.dll", "IdunBattle.Core.Services", "DamagePrediction");
var _predictNormalInfo = _damagePredClass ? findMethod(_damagePredClass, "PredictNormalAttack") : null;

var runnerInstance = null;
var matchStateRef = null; // fallback: captured from FSM tap before runner is available

// --- Internal helpers ---

function _readListPtrs(listPtr) {
    if (listPtr.isNull()) return [];
    var items = listPtr.add(0x10).readPointer();
    var size = listPtr.add(0x18).readS32();
    if (items.isNull() || size <= 0 || size > 5000) return [];
    var r = [];
    for (var i = 0; i < size; i++)
        r.push(items.add(0x20 + i * Process.pointerSize).readPointer());
    return r;
}

function _findComp(entity, name) {
    var arr = entity.add(_entityComponentsOff).readPointer();
    if (arr.isNull()) return null;
    var len = arr.add(0x18).readS32();
    for (var j = 0; j < Math.min(len, 50); j++) {
        var c = arr.add(0x20 + j * Process.pointerSize).readPointer();
        if (c.isNull()) continue;
        try { if (s(class_get_name(c.readPointer())) === name) return c; } catch(e) {}
    }
    return null;
}

function _getEntities() {
    var state = runnerInstance.add(runnerStateOff).readPointer();
    return _readListPtrs(state.add(_msEntitiesOff).readPointer());
}

// --- Public: entity lookup ---

function getEntityById(entityId) {
    if (!runnerInstance) return null;
    var entities = _getEntities();
    for (var i = 0; i < entities.length; i++) {
        var e = entities[i];
        if (!e.isNull() && e.add(_entityIdOff).readS32() === entityId) return e;
    }
    return null;
}

function getUnitTile(unitEntityId) {
    // FootEntity (type 5) links unit -> tile
    if (!runnerInstance) return null;
    var entities = _getEntities();
    for (var i = 0; i < entities.length; i++) {
        var e = entities[i];
        if (e.isNull() || e.add(_entityTypeOff).readS32() !== 5) continue;
        var fc = _findComp(e, "UnitFootComponent");
        if (fc && fc.add(_footUnitIdOff).readS32() === unitEntityId) {
            var tileId = fc.add(_footTileIdOff).readS32();
            return getEntityById(tileId);
        }
    }
    return null;
}

// --- Turn detection ---

function isPlayerTurn() {
    if (!runnerInstance) return false;
    try {
        var entities = _getEntities();
        var cur = -1, human = -1;
        for (var i = 0; i < entities.length; i++) {
            var e = entities[i];
            if (e.isNull()) continue;
            var t = e.add(_entityTypeOff).readS32();
            if (t === 2) {
                var tc = _findComp(e, "TurnComponent");
                if (tc) cur = tc.add(_turnCurrentPlayerOff).readS32();
            }
            if (t === 4) {
                var pc = _findComp(e, "PlayerComponent");
                if (pc && pc.add(_playerTypeOff).readS32() === 0)
                    human = e.add(_entityIdOff).readS32();
            }
        }
        return cur === human && cur !== -1;
    } catch(e) { return false; }
}

// --- Full state serialization ---

function getSerializedState(depth) {
    if (!runnerInstance) return null;
    try {
        var state = runnerInstance.add(runnerStateOff).readPointer();
        return serialize(state, depth || 4);
    } catch(e) { return {error: e.message}; }
}

// --- Game queries (called on main thread via RPC) ---

// Helper: allocate a value-type arg for il2cpp_runtime_invoke
function _valArg(value) {
    var p = Memory.alloc(8);
    p.writeS32(value);
    return p;
}

function queryReachableTiles(unitId) {
    if (!runnerInstance || !_findReachableInfo) return {error: "not ready"};
    var unit = getEntityById(unitId);
    if (!unit) return {error: "unit not found: " + unitId};
    var tile = getUnitTile(unitId);
    if (!tile) return {error: "tile not found for unit: " + unitId};

    // Read movement value from MovementComponent
    var moveComp = _findComp(unit, "MovementComponent");
    var depth = 3;
    if (moveComp && _moveInitialOff >= 0) {
        depth = moveComp.add(_moveInitialOff).readS32();
    }

    var pathfinders = runnerInstance.add(runnerPathfindersOff).readPointer();

    // Direct NativeFunction call (ARM64 IL2CPP convention):
    // this, PathfinderType(int), IEntity start, int depth, IEntity unit, MethodInfo*
    var findReachableFn = new NativeFunction(_findReachableInfo.ptr, "pointer",
        ["pointer", "int", "pointer", "int", "pointer", "pointer"]);
    var result = findReachableFn(pathfinders, 0, tile, depth, unit, _findReachableInfo.info);

    if (result.isNull()) return {error: "FindReachableTiles returned null"};

    // DisposableList<TileEntity> — read items before they get pooled
    // Read _size and iterate _items array
    var size = result.add(0x18).readS32();
    var items = result.add(0x10).readPointer();
    var tiles = [];
    for (var i = 0; i < Math.min(size, 200); i++) {
        var t = items.add(0x20 + i * Process.pointerSize).readPointer();
        if (t.isNull()) continue;
        var tid = t.add(_entityIdOff).readS32();
        tiles.push(tid);
    }
    return {unitId: unitId, depth: depth, tileIds: tiles, count: size};
}

function queryDamagePrediction(attackerId, defenderId) {
    if (!runnerInstance || !_predictNormalInfo) return {error: "not ready"};
    var attacker = getEntityById(attackerId);
    var defender = getEntityById(defenderId);
    if (!attacker) return {error: "attacker not found: " + attackerId};
    if (!defender) return {error: "defender not found: " + defenderId};

    var damagePred = runnerInstance.add(runnerDamagePredOff).readPointer();
    // PredictNormalAttack(attacker, attackerPosition, defender)
    // attackerPosition is UnitPosition — we need to construct it
    // For now, pass null and see if it works with just the attacker tile
    // TODO: construct UnitPosition properly
    return {error: "not yet implemented — needs UnitPosition construction"};
}

// Note: LocalizationQuery RPC was attempted but returns null for all abilities.
// Ability descriptions are resolved statically by the backend using I2 templates + abilities.json configs.


// queryAbilitiesInfo removed — LocalizationQuery RPC returns null.
// Descriptions are resolved by the backend via I2 templates + abilities.json.

console.log("[*] MatchState reader loaded");
// hook: Message factory — create IL2CPP battle messages
// requires: _utils/il2cpp-helpers, _utils/il2cpp-invoke, _utils/matchstate-reader
// provides: createMessage(cmd)

// --- Message classes ---
var endTurnClass = findClass("BattleLogicAssembly.dll", "IdunBattle.Messages", "EndTurnMessage");
var abilityMsgClass = findClass("BattleLogicAssembly.dll", "IdunBattle.Messages", "ActiveAbilityMessage");
var moveMsgClass = findClass("BattleLogicAssembly.dll", "IdunBattle.Messages", "MoveUnitMessage");
var positionClass = findClass("BattleLogicAssembly.dll", "IdunBattle.Messages", "Position");
var _posIsValueType = positionClass ? class_is_valuetype(positionClass) : -1;
var _posInstanceSize = positionClass ? class_instance_size(positionClass) : -1;
send({t: "debug", positionClass: !!positionClass, isValueType: _posIsValueType, instanceSize: _posInstanceSize});

// --- ActiveAbilityMessage field offsets ---
var abCasterOff = abilityMsgClass ? getFieldOffset(abilityMsgClass, "CasterId") : -1;
var abTargetOff = abilityMsgClass ? getFieldOffset(abilityMsgClass, "TargetId") : -1;
var abTypeOff = abilityMsgClass ? getFieldOffset(abilityMsgClass, "ActiveAbilityType") : -1;
var abSkipFlagsOff = abilityMsgClass ? getFieldOffset(abilityMsgClass, "SkipFlags") : -1;

// --- MoveUnitMessage field offsets ---
var mvUnitIdOff = moveMsgClass ? getFieldOffset(moveMsgClass, "UnitId") : -1;
var mvPositionsOff = moveMsgClass ? getFieldOffset(moveMsgClass, "UnitFeetPositions") : -1;
var mvSkipFlagsOff = moveMsgClass ? getFieldOffset(moveMsgClass, "SkipFlags") : -1;

// --- Position field offsets ---
var posColumnOff = positionClass ? getFieldOffset(positionClass, "Column") : -1;
var posRowOff = positionClass ? getFieldOffset(positionClass, "Row") : -1;

function createEndTurnMessage() {
    return createObject(endTurnClass);
}

function createAbilityMessage(casterId, targetId, abilityType) {
    var msg = createObject(abilityMsgClass);
    msg.add(abCasterOff).writeS32(casterId);
    msg.add(abTargetOff).writeS32(targetId);
    msg.add(abTypeOff).writeS32(abilityType);
    msg.add(abSkipFlagsOff).writeU8(0);
    return msg;
}

function createPosition(col, row) {
    // Position is a VALUE TYPE (struct) — for List<Position>.Add we need a boxed object
    // but the data pointer for runtime_invoke is at object+0x10
    var pos = il2cpp_object_new(positionClass);
    pos.add(posColumnOff).writeS32(col);
    pos.add(posRowOff).writeS32(row);
    return pos;
}

// For il2cpp_runtime_invoke, value type args need pointer to unboxed data
function createPositionUnboxed(col, row) {
    // Allocate raw struct: just Column (4 bytes) + Row (4 bytes)
    var buf = Memory.alloc(8);
    buf.writeS32(col);
    buf.add(4).writeS32(row);
    return buf;
}

// --- Resolve List<Position> class from the field type ---
var _listPositionClass = (function() {
    var it = Memory.alloc(Process.pointerSize);
    it.writePointer(ptr(0));
    var f;
    while (!(f = class_get_fields(moveMsgClass, it)).isNull()) {
        if (s(field_get_name(f)) === "UnitFeetPositions") {
            var ft = field_get_type(f);
            return class_from_type(ft);
        }
    }
    return null;
})();
var _listAddInfo = _listPositionClass ? findMethod(_listPositionClass, "Add") : null;

function createMoveMessage(unitId, positions) {
    // positions = [{col, row}] — 1 element for standard units
    var msg = il2cpp_object_new(moveMsgClass);
    msg.add(mvUnitIdOff).writeS32(unitId);
    msg.add(mvSkipFlagsOff).writeU8(0);

    // Create List<Position> — Position is a value type (8 bytes: Column + Row)
    // Write directly into List internals instead of using Add()
    var list = createObject(_listPositionClass);
    // List<T> layout: [klass:8][monitor:8][_items:8][_size:4][_version:4]
    // _items is a T[] (szarray): [klass:8][monitor:8][bounds:8][max_length:4][padding:4][data...]
    // For value type T, data is inline: items[0] at offset 0x20, size = sizeof(T) = 8

    var count = positions.length;
    // Ensure _items array is big enough — the .ctor creates a default empty array
    // We need to create a new T[] with enough capacity
    // Find the array class for Position[]
    var itemsArray = list.add(0x10).readPointer();
    var maxLen = itemsArray.isNull() ? 0 : itemsArray.add(0x18).readS32();

    if (maxLen < count) {
        // Value type param for runtime_invoke = pointer to raw struct data
        for (var i = 0; i < count; i++) {
            var unboxed = createPositionUnboxed(positions[i].col, positions[i].row);
            invokeMethod(_listAddInfo.info, list, [unboxed]);
        }
    } else {
        // Write directly
        for (var i = 0; i < count; i++) {
            itemsArray.add(0x20 + i * 8).writeS32(positions[i].col);
            itemsArray.add(0x20 + i * 8 + 4).writeS32(positions[i].row);
        }
        list.add(0x18).writeS32(count); // _size
    }

    msg.add(mvPositionsOff).writePointer(list);
    return msg;
}

function createMessage(cmd) {
    if (cmd.action === "end_turn") return createEndTurnMessage();
    if (cmd.action === "ability") return createAbilityMessage(cmd.casterId, cmd.targetId, cmd.abilityType);
    if (cmd.action === "move") return createMoveMessage(cmd.unitId, cmd.positions);
    throw new Error("Unknown action: " + cmd.action);
}

console.log("[*] Message factory loaded");
// hook: Action queue — execute actions + RPC on the main thread via Update
// requires: _utils/il2cpp-helpers, _utils/il2cpp-invoke, _utils/matchstate-reader, autoplay/message-factory
// provides: pendingActions, pendingRpc, pendingPlay, events
//
// Uses Interceptor.replace (not attach) so that nested Interceptor hooks
// on methods called during Apply (StreamDispatcher, MoveUnitOperation, etc.)
// fire correctly — Frida suppresses nested hooks inside attach callbacks
// (same-thread suppression) but not inside replace functions.

var pendingActions = [];
var pendingRpc = [];
var pendingPlay = null; // {id, args, executed}
var events = [];

var _gameViewsClass = findClass("Assembly-CSharp.dll", "IdunBattle.View.Game", "IdunGameViews");
var _gvRunnerOff = _gameViewsClass ? getFieldOffset(_gameViewsClass, "_runner") : -1;
var _updateMethod = _gameViewsClass ? findMethod(_gameViewsClass, "Update") : null;

if (_updateMethod) {
    var _originalUpdate = new NativeFunction(_updateMethod.ptr, "void", ["pointer", "pointer"]);

    Interceptor.replace(_updateMethod.ptr, new NativeCallback(function(self, methodInfo) {
        // --- Capture runner from GameViews._runner ---
        if (!runnerInstance && _gvRunnerOff >= 0) {
            var r = self.add(_gvRunnerOff).readPointer();
            if (!r.isNull()) {
                runnerInstance = r;
                console.log("[+] Runner captured from GameViews");
            }
        }

        // --- Instant RPCs — always process, even without runner ---
        if (pendingRpc.length > 0) {
            var req = pendingRpc.shift();
            try {
                var result = null;
                if (req.method === "get_state") {
                    result = getSerializedState(req.args.depth);
                } else if (req.method === "get_reachable_tiles") {
                    result = queryReachableTiles(req.args.unitId);
                } else if (req.method === "get_damage_prediction") {
                    result = queryDamagePrediction(req.args.attackerId, req.args.defenderId);
                } else {
                    result = {error: "unknown RPC method: " + req.method};
                }
                send({t: "rpc_response", id: req.id, result: result});
            } catch(e) {
                send({t: "rpc_response", id: req.id, result: {error: e.message}});
            }
        }

        if (runnerInstance) {
            // --- Blocking play: execute then wait for player turn ---
            if (pendingPlay) {
                if (!pendingPlay.executed) {
                    events = [];
                    pendingPlay.executed = true;
                    try {
                        var message = createMessage(pendingPlay.args);
                        invokeMethod(runnerApplyInfo.info, runnerInstance, [message]);
                    } catch(e) {
                        send({t: "rpc_response", id: pendingPlay.id, result: {error: "play failed: " + e.message}});
                        pendingPlay = null;
                    }
                } else {
                    if (isPlayerTurn()) {
                        try {
                            var state = getSerializedState();
                            if (state) state._events = events;
                            send({t: "rpc_response", id: pendingPlay.id, result: state});
                        } catch(e) {
                            send({t: "rpc_response", id: pendingPlay.id, result: {error: e.message}});
                        }
                        pendingPlay = null;
                        events = [];
                    }
                }
            }
            // --- Fire-and-forget actions (via POST /message) ---
            else if (pendingActions.length > 0) {
                var cmd = pendingActions.shift();
                try {
                    var msg = createMessage(cmd);
                    invokeMethod(runnerApplyInfo.info, runnerInstance, [msg]);
                    send({t: "played", cmd: cmd});
                } catch(e) {
                    send({t: "error", msg: "play failed: " + e.message});
                }
            }
        }

        // Call original Update
        _originalUpdate(self, methodInfo);
    }, "void", ["pointer", "pointer"]));

    console.log("[+] IdunGameViews.Update (replaced)");
} else {
    console.log("[-] IdunGameViews.Update not found");
}

console.log("[*] Action queue loaded");// hook: Turn observer — capture runner, Apply messages, StreamDispatcher mutations, player turn
// requires: _utils/il2cpp-helpers, _utils/il2cpp-invoke, _utils/matchstate-reader, autoplay/action-queue

var _lastTurnSent = 0;

// --- Hook Apply: capture runner + log every message ---
hook("BattleLogicAssembly.dll", "IdunBattle.Runner", "IdunRunner", "Apply", {
    onEnter: function(args) {
        runnerInstance = args[0];

        try {
            var details = readMsgDetails(args[1]);

            if (details.msg === "CheatMoveUnitMessage") {
                details.stack = getStack(this.context);
            }

            send({t: "apply", msg: details});
        } catch(e) {}
    },
    onLeave: function(retval) {
        if (pendingPlay) return;
        var now = Date.now();
        if (now - _lastTurnSent < 500) return;
        if (isPlayerTurn()) {
            _lastTurnSent = now;
            send({t: "your_turn"});
        }
    }
});

// --- Hook ApplyAiMessage: capture AI-specific actions ---
hook("BattleLogicAssembly.dll", "IdunBattle.Core.Services", "AiControl", "ApplyAiMessage", {
    onEnter: function(args) {
        try {
            var details = readMsgDetails(args[1]);
            details._src = "AI";
            send({t: "apply", msg: details});
        } catch(e) {}
    }
});

// --- Hook StreamDispatcher: capture ALL mutations ---
// Action(StepType actionType, BEntityId entityId, Dictionary<TagKey, int> tags)
// StepType and BEntityId are value types (ints), tags is a reference type
hook("BattleLogicAssembly.dll", "IdunBattle.Streams", "StreamDispatcher", "Action", {
    onEnter: function(args) {
        try {
            // args[0] = this, args[1] = StepType (int), args[2] = BEntityId (int),
            // args[3] = Dictionary<TagKey, int> (pointer)
            var stepType = args[1].toInt32();
            var entityId = args[2].toInt32();

            var tags = null;
            try { tags = readDict(args[3], 0); } catch(e) {}

            var evt = {
                step: {_enum: "IdunBattle.Streams.StepType", _value: stepType},
                entity: entityId,
                tags: tags
            };
            send({t: "stream", evt: evt});

            if (pendingPlay && pendingPlay.executed) {
                events.push(evt);
            }
        } catch(e) {}
    }
});

// StartGroup(GroupType, BEntityId, string sourceId, BEntityId? initialTarget)
hook("BattleLogicAssembly.dll", "IdunBattle.Streams", "StreamDispatcher", "StartGroup", {
    onEnter: function(args) {
        try {
            var groupType = args[1].toInt32();
            var entityId = args[2].toInt32();
            var sourceId = readIl2cppString(args[3]);

            var evt = {
                group: {_enum: "IdunBattle.Streams.GroupType", _value: groupType},
                entity: entityId,
                source: sourceId
            };
            send({t: "stream_group", evt: evt});

            if (pendingPlay && pendingPlay.executed) {
                events.push(evt);
            }
        } catch(e) {}
    }
});

// --- Diagnostic hooks: log validation failures ---
var _moveOpClass = findClass("BattleLogicAssembly.dll", "IdunBattle.Operations", "MoveUnitOperation");

if (_moveOpClass) {
    var _validationMethods = ["IsAllowedToMove", "TilesAreWalkable", "TilesAreEmpty", "TilesMatchUnitFeetCount"];
    for (var vi = 0; vi < _validationMethods.length; vi++) {
        (function(name) {
            var info = findMethod(_moveOpClass, name);
            if (info) {
                Interceptor.attach(info.ptr, {
                    onLeave: function(retval) {
                        if (retval.toInt32() === 0) {
                            var evt = {_validation: name, passed: false};
                            send({t: "validation_failed", evt: evt});
                            if (pendingPlay && pendingPlay.executed) events.push(evt);
                        }
                    }
                });
                console.log("[+] MoveUnitOperation." + name);
            }
        })(_validationMethods[vi]);
    }
}

console.log("[*] Turn observer loaded");// hook: Input capture — tap-to-select units/tiles on the board
// requires: _utils/il2cpp-helpers, _utils/il2cpp-serializer, _utils/matchstate-reader

// --- Hook HandleMouseButtonUpThisFrame ---
// ARM64 ABI: Vector3 (HFA, 3 floats) goes in float regs, not integer regs.
// So: args[0]=this, args[1]=entityHit, args[2]=tileHit, args[3]=MethodInfo*
hook("Assembly-CSharp.dll", "IdunBattle.View.FSM", "UnitSelectionFsm", "HandleMouseButtonUpThisFrame", {
    onEnter: function(args) {
        try {
            var entityHit = args[1];
            var tileHit = args[2];

            var tap = {};
            if (!entityHit.isNull()) tap.entity = serialize(entityHit, 4);
            if (!tileHit.isNull()) tap.tile = serialize(tileHit, 4);

            send({t: "tap", tap: tap});
        } catch(e) {
            send({t: "tap", error: e.message});
        }
    }
});

console.log("[*] Input capture loaded");// hook: Recv handlers — bridge between backend POST and script queues
// requires: autoplay/action-queue, _utils/matchstate-reader
// provides: recv("action"), recv("rpc"), recv("query_state")

// --- Action commands (fire-and-forget via POST /api/scripts/{id}/message) ---
recv("action", function onAction(msg) {
    if (!runnerInstance) {
        send({t: "error", msg: "No runner instance yet"});
        recv("action", onAction);
        return;
    }
    pendingActions.push(msg.payload);
    send({t: "queued", cmd: msg.payload, pending: pendingActions.length});
    recv("action", onAction);
});

// --- RPC queries (POST /api/scripts/{id}/rpc) ---
recv("rpc", function onRpc(msg) {
    if (msg.method === "play") {
        // Blocking play: execute action, wait for isPlayerTurn
        if (pendingPlay) {
            // Already a play in flight — reject
            send({t: "rpc_response", id: msg.id, result: {error: "play already in progress"}});
        } else {
            pendingPlay = {id: msg.id, args: msg.args, executed: false};
        }
    } else {
        // Instant RPC (get_state, etc.)
        pendingRpc.push({id: msg.id, method: msg.method, args: msg.args || {}});
    }
    recv("rpc", onRpc);
});

// --- Legacy state query (kept for compatibility) ---
recv("query_state", function onQuery(msg) {
    try {
        send({t: "state", state: buildTurnSummary()});
    } catch(e) {
        send({t: "error", msg: "query failed: " + e.message});
    }
    recv("query_state", onQuery);
});

// --- Cleanup: signal ready for unload ---
// The backend waits for this ack + a short sleep before script.unload(),
// ensuring we're not in the middle of a NativeCallback (Interceptor.replace).
recv("cleanup", function(msg) {
    send({t: "cleanup_done"});
});

send({t: "autoplay_ready", msg: "Hooks installed. Play a turn to capture runner, then auto-play begins."});
