// Main-thread pumps.
//
//   1. IdunGameViews.Update — fires during battle view. Handles runner switch
//      (new battle detected → install live-runner hooks) + drains pending RPC.
//   2. UnityFreezeDetector.Update — fires EVERY frame (menu + battle).
//      Drains pending RPC too so Phase 3 launch works without an active battle.
//
// Both pumps share `state.pending`. The queue is shift()-based so fn's run at
// most once; having two pumps guarantees main-thread work proceeds regardless
// of game state.
//
// Both pumps use `Interceptor.replace` (not `attach`): Frida's `attach`
// applies a per-thread recursion guard that silently suppresses any nested
// hook callback fired from inside an `attach` onEnter. Because `drainPending`
// invokes IL2CPP methods synchronously (on the main thread, as required by
// the runtime), any listener we've installed on those invoked methods would
// be dead under an `attach`-pump. `replace` has no recursion guard and
// preserves the main-thread context, so hooks downstream of `drainPending`
// fire correctly.

import { findClass, findMethod, getFieldOffset } from "../il2cpp/helpers.js";
import { state } from "../game/state.js";
import { install } from "../game/recorder.js";
import { log, traceEnter } from "./diag.js";

function drainPending(): void {
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
}

const gameViewsClass = findClass(
    "Assembly-CSharp.dll", "IdunBattle.View.Game", "IdunGameViews");
const gvRunnerOff = gameViewsClass
    ? getFieldOffset(gameViewsClass, "_runner") : -1;
const updateMi = gameViewsClass ? findMethod(gameViewsClass, "Update") : null;

export function installMainPump(): void {
    if (!updateMi || updateMi.ptr.isNull()) {
        log("[main-pump] IdunGameViews.Update not found");
        return;
    }

    const origUpdate = new NativeFunction(
        updateMi.ptr, "void", ["pointer", "pointer"]);

    Interceptor.replace(updateMi.ptr, new NativeCallback(function (self, methodInfo) {
        traceEnter("IdunGameViews.Update", 60);
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

        drainPending();

        origUpdate(selfPtr, methodInfo as NativePointer);
    }, "void", ["pointer", "pointer"]));
}

export function installMenuPump(): void {
    const cls = findClass(
        "Assembly-CSharp.dll", "idun.unity.utils", "UnityFreezeDetector");
    if (!cls) { log("[menu-pump] UnityFreezeDetector not found"); return; }
    const mi = findMethod(cls, "Update");
    if (!mi || mi.ptr.isNull()) {
        log("[menu-pump] UnityFreezeDetector.Update not found");
        return;
    }

    const origUpdate = new NativeFunction(
        mi.ptr, "void", ["pointer", "pointer"]);

    Interceptor.replace(mi.ptr, new NativeCallback(function (self, methodInfo) {
        traceEnter("UnityFreezeDetector.Update", 60);
        drainPending();
        origUpdate(self as NativePointer, methodInfo as NativePointer);
    }, "void", ["pointer", "pointer"]));
    log("[menu-pump] attached (via replace) to UnityFreezeDetector.Update");
}
