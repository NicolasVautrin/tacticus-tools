// Main-thread pump via Interceptor.replace on IdunGameViews.Update.
//
// Two jobs per frame:
//   1. Detect runner switch (new battle, or reinject across battles):
//      if the GameViews._runner pointer changed, flag for install(),
//      reset log/counter. Install is deferred via setTimeout(0) because
//      Interceptor.attach cannot complete from within Interceptor.replace.
//   2. Drain `state.pending` — RPC work waiting for main-thread execution.
//
// Calls the original Update at the end to keep the game ticking normally.

import { findClass, findMethod, getFieldOffset } from "../il2cpp/helpers.js";
import { state } from "../game/state.js";
import { install } from "../game/recorder.js";

const gameViewsClass = findClass(
    "Assembly-CSharp.dll", "IdunBattle.View.Game", "IdunGameViews");
const gvRunnerOff = gameViewsClass
    ? getFieldOffset(gameViewsClass, "_runner") : -1;
const updateMi = gameViewsClass ? findMethod(gameViewsClass, "Update") : null;

export function installMainPump(): void {
    if (!updateMi || updateMi.ptr.isNull()) {
        console.log("[main-pump] IdunGameViews.Update not found");
        return;
    }

    const origUpdate = new NativeFunction(
        updateMi.ptr, "void", ["pointer", "pointer"]);

    Interceptor.replace(updateMi.ptr, new NativeCallback(function (self, methodInfo) {
        const selfPtr = self as NativePointer;

        // Runner switch detection
        const r = selfPtr.add(gvRunnerOff).readPointer();
        if (!r.isNull() && !r.equals(state.runnerInstance ?? ptr(0))) {
            state.runnerInstance = r;
            state.counter = 0;
            state.log = [];
            state.installNeeded = true;
            setTimeout(() => {
                if (state.installNeeded) {
                    state.installNeeded = false;
                    try { install(); }
                    catch (e) { send({ t: "install_error", err: (e as Error).message }); }
                }
            }, 0);
        }

        // Drain pending RPC work
        while (state.pending.length > 0) {
            const req = state.pending.shift()!;
            try {
                const result = req.fn();
                if (result instanceof Promise) {
                    result.then(req.resolve, (e) => req.reject((e as Error).message));
                } else {
                    req.resolve(result);
                }
            } catch (e) {
                req.reject((e as Error).message);
            }
        }

        origUpdate(selfPtr, methodInfo as NativePointer);
    }, "void", ["pointer", "pointer"]));
}
