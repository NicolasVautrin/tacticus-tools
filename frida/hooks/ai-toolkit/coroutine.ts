// C# compiler-generated coroutine helpers.
//
// Async/iterator methods compile to nested classes named `<MethodName>d__N`,
// implementing IEnumerator. Their fields are stable across the codebase:
//   <>1__state @ 0x10  (int — current step in the state machine)
//   <>2__current @ 0x18 (T — value yielded last)
//   <>4__this @ varies  (the outer 'this' captured at coroutine entry)
//   public params @ 0x20+
//   <localVar>5__N @ later offsets (captured locals)
//
// Generic for any AI fix that hooks a coroutine MoveNext to read or mutate
// the yielded value, or to capture the outer-this for context.

import {
    class_get_name, class_get_nested_types, cstr,
} from "../il2cpp/helpers.js";

/** Common state-machine field offsets — applies to every C# iterator
 * compiler-generated class. */
export const SM_STATE = 0x10;     // <>1__state (int)
export const SM_CURRENT = 0x18;   // <>2__current (T — yielded value)

/** Find the compiler-generated state-machine nested class for an iterator
 * method on `parentClass`. The naming convention is `<MethodName>d__N` where
 * N is a compiler-assigned index — matches by prefix. Returns the first
 * match (there's only ever one per method). */
export function findIteratorStateMachine(
    parentClass: NativePointer, methodName: string,
): NativePointer | null {
    const it = Memory.alloc(Process.pointerSize);
    it.writePointer(ptr(0));
    let nested: NativePointer;
    while (!(nested = class_get_nested_types(parentClass, it) as NativePointer)
        .isNull()) {
        const name = cstr(class_get_name(nested) as NativePointer);
        if (name.startsWith("<" + methodName + ">d__")) return nested;
    }
    return null;
}
