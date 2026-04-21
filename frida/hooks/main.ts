// Entry point for the injected Frida script.

import { il2cppBase, il2cppSize } from "./il2cpp/helpers.js";
import "./game/runner.js";
import "./game/match-state.js";
import "./game/ai-control.js";
import { installMainPump, installMenuPump } from "./runtime/main-pump.js";
import { wireRpc } from "./controller.js";

send({ t: "hook_ready", name: "frida", version: 1 });
console.log("[*] il2cpp base=" + il2cppBase + " size=" + il2cppSize);

installMainPump();
installMenuPump();

const rpcHandlers: Record<string, (...args: any[]) => unknown> = {};
wireRpc({ rpc: rpcHandlers });
rpc.exports = rpcHandlers;
