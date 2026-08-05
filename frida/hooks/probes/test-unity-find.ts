import { findClass, findMethod, s, methodEntry, getSystemType } from "../il2cpp/helpers.js";
import { invokeMethod, createManagedString } from "../il2cpp/invoke.js";
import { queueOnMainThread } from "../runtime/queue.js";
import { log } from "../runtime/diag.js";
import { Ctx } from "../controller.js";

export function registerTestFind(ctx: Ctx): void {
    ctx.rpc.testUnityFind = () => {
        return queueOnMainThread(() => {
            log("[test-find] Starting Unity find tests...");
            
            const goKlass = findClass("UnityEngine.CoreModule.dll", "UnityEngine", "GameObject");
            if (!goKlass) {
                log("[test-find] GameObject class not found!");
                return { error: "GameObject class not found" };
            }
            log(`[test-find] GameObject klass: ${goKlass}`);

            const findMi = findMethod(goKlass, "Find");
            if (!findMi) {
                log("[test-find] GameObject.Find method not found!");
                return { error: "GameObject.Find not found" };
            }
            log(`[test-find] GameObject.Find: info=${findMi.info}, ptr=${findMi.ptr}`);

            try {
                // Try to find a common GameObject name like "IdunNavigation"
                const nameStr = createManagedString("IdunNavigation");
                log("[test-find] Invoking GameObject.Find('IdunNavigation')...");
                const goInst = invokeMethod(findMi.info, null, [nameStr]);
                log(`[test-find] GameObject.Find result: ${goInst}`);
                if (!goInst.isNull()) {
                    log("[test-find] Successfully found IdunNavigation GameObject!");
                    return { ok: true, go: goInst.toString() };
                }
            } catch (e) {
                log(`[test-find] Error during GameObject.Find: ${(e as Error).message}`);
            }

            return { ok: false, msg: "GameObject not found" };
        });
    };
}
