// Entry point for the injected Frida script.

import { il2cppBase, il2cppSize } from "./il2cpp/helpers.js";
import "./game/runner.js";
import "./game/match-state.js";
import "./game/ai-control.js";
import { installMainPump, installMenuPump } from "./runtime/main-pump.js";
import { installFreezeDetectorNeutralizer } from "./runtime/freeze-detector.js";
import { installCrashLogger } from "./runtime/crash-logger.js";
import { installExceptionTracer } from "./runtime/exception-tracer.js";
import { log } from "./runtime/diag.js";
import { wireRpc } from "./controller.js";

send({ t: "hook_ready", name: "frida", version: 1 });
log("[*] il2cpp base=" + il2cppBase + " size=" + il2cppSize);

// installCrashLogger();  // disabled — Process.setExceptionHandler intercepts
//                       // every SIGSEGV including IL2CPP soft null-checks and
//                       // GC write barriers, freezing the main thread.
// EN PREMIER : desarmer le UnityFreezeDetector avant toute autre pose de hook. C'est lui
// qui appelle `ForceCrash` quand la boucle Unity bloque trop longtemps — donc lui qui tuait
// le jeu sur une amorce un peu long ou un heap scan. Tout ce qui suit devient survivable.
installFreezeDetectorNeutralizer();

installMainPump();
installMenuPump();
installExceptionTracer();

const rpcHandlers: Record<string, (...args: any[]) => unknown> = {};
wireRpc({ rpc: rpcHandlers });
rpc.exports = rpcHandlers;

// Graceful cleanup protocol — host posts `{type:"cleanup"}` before unload.
// We acknowledge with `{t:"cleanup_done"}` so the host doesn't need to wait
// the full 2s timeout. Frida auto-detaches Interceptor.attach + reverts
// Interceptor.replace on script unload, so no manual teardown is needed
// here — this is purely a sync handshake.
recv("cleanup", () => {
    try { send({ t: "cleanup_done" }); }
    catch { /* host already gone — unload will follow */ }
});

// Boot completion signal — host's runScript awaits this before resolving
// so the first RPC after inject doesn't sit pending while the agent's
// top-level (lots of findClass + Interceptor.attach) is still running.
// Must be the very last statement in this module.
send({ t: "agent_ready", name: "frida" });
