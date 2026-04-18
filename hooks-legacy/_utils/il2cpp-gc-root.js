// util: IL2CPP GC rooting via System.Collections.ArrayList
// requires: _utils/il2cpp-helpers, _utils/il2cpp-invoke
// provides: gcRoot.init(), gcRoot.add(obj), gcRoot.remove(obj), gcRoot.clear(),
//           gcRoot.count(), gcRoot.listPtr()
//
// Purpose: Unity/IL2CPP uses a managed GC. Any object we clone (via MatchState.Copy,
// etc.) and hold from the native side must be referenced from a live managed object,
// otherwise the GC collects it within seconds.
//
// Strategy: create one ArrayList at script start, keep it alive through our script's
// closure, and add each object we want to preserve to it. Calling gcRoot.remove() or
// gcRoot.clear() drops our reference, and the GC reclaims memory on the next cycle.
//
// We use `System.Collections.ArrayList` (non-generic) rather than `List<T>` because
// the generic version requires finding an inflated generic instance, which is more
// complex via raw Frida. ArrayList stores `System.Object` so it accepts anything.

var gcRoot = (function () {
    var arrayList = null;        // IL2CPP ArrayList* (live root)
    var addMi = null;            // ArrayList.Add MethodInfo*
    var removeMi = null;         // ArrayList.Remove MethodInfo*
    var clearMi = null;          // ArrayList.Clear MethodInfo*
    var countGetMi = null;       // ArrayList.get_Count MethodInfo*

    function init() {
        if (arrayList !== null) return true;

        var klass = findClass("mscorlib.dll", "System.Collections", "ArrayList");
        if (!klass) {
            console.log("[gcRoot] ERROR: ArrayList class not found");
            return false;
        }

        var ctor = findMethod(klass, ".ctor");
        if (!ctor || ctor.ptr.isNull()) {
            console.log("[gcRoot] ERROR: ArrayList..ctor not found");
            return false;
        }
        addMi = findMethod(klass, "Add");
        removeMi = findMethod(klass, "Remove");
        clearMi = findMethod(klass, "Clear");
        countGetMi = findMethod(klass, "get_Count");
        if (!addMi || !removeMi || !clearMi || !countGetMi) {
            console.log("[gcRoot] ERROR: missing Add/Remove/Clear/get_Count on ArrayList");
            return false;
        }

        // Create the instance. The ctor in ArrayList (parameterless) can only be
        // the default one; there are overloads but findMethod returns the first.
        arrayList = il2cpp_object_new(klass);
        if (arrayList.isNull()) {
            console.log("[gcRoot] ERROR: il2cpp_object_new returned null");
            return false;
        }
        invokeMethod(ctor.info, arrayList, null);

        console.log("[gcRoot] ArrayList created at " + arrayList);
        return true;
    }

    function add(objPtr) {
        if (!arrayList) throw new Error("gcRoot not initialized");
        if (objPtr === null || objPtr.isNull()) return;
        try {
            invokeMethod(addMi.info, arrayList, [objPtr]);
        } catch (e) {
            // If the ArrayList was reclaimed/invalidated, build a new one
            // and retry once.
            if (/ArrayTypeMismatch|exception/i.test(e.message)) {
                arrayList = null;
                init();
                invokeMethod(addMi.info, arrayList, [objPtr]);
                return;
            }
            throw e;
        }
    }

    function remove(objPtr) {
        if (!arrayList) throw new Error("gcRoot not initialized");
        if (objPtr === null || objPtr.isNull()) return;
        invokeMethod(removeMi.info, arrayList, [objPtr]);
    }

    function clear() {
        if (!arrayList) throw new Error("gcRoot not initialized");
        invokeMethod(clearMi.info, arrayList, null);
    }

    function count() {
        if (!arrayList) return 0;
        // get_Count returns int32 (value type). il2cpp_runtime_invoke returns a
        // *boxed* Int32 object: pointer to an Il2CppObject whose payload starts
        // at offset 0x10 (after klass* + monitor*).
        var boxed = invokeMethod(countGetMi.info, arrayList, null);
        if (boxed.isNull()) return 0;
        return boxed.add(0x10).readS32();
    }

    function listPtr() { return arrayList; }

    return { init: init, add: add, remove: remove, clear: clear, count: count, listPtr: listPtr };
})();

console.log("[*] IL2CPP gc-root loaded");
