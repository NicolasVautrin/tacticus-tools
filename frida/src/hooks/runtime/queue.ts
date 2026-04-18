// Main-thread RPC queue.
//
// IL2CPP methods (invokeMethod, new object, etc.) must run on Unity's main
// thread — Frida RPCs arrive on a different thread. queueOnMainThread()
// wraps a function in a Promise, parks it in `state.pending`, and waits
// for the main-pump (in IdunGameViews.Update hook) to drain and execute.

import { state } from "../game/state.js";

export function queueOnMainThread<T>(fn: () => T | Promise<T>): Promise<T> {
    return new Promise<T>((resolve, reject) => {
        state.pending.push({
            fn: fn as () => unknown,
            resolve: resolve as (v: unknown) => void,
            reject: (m: string) => reject(new Error(m)),
        });
    });
}
