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
