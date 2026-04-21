// Host entrypoint — Express + WebSocket server.
// Manages Frida sessions, routes HTTP RPC, persists `send()` to JSONL logs.

import express from "express";
import { createServer } from "http";
import path from "path";
import { buildRouter } from "./router.js";
import { attachWss } from "./ws.js";
import { initConfigStore } from "./config-store.js";
import { initBattleStore } from "./battle-store.js";

const PORT = parseInt(process.env.PORT ?? "8765", 10);

// npm scripts run from frida/ so logs/ sits at cwd. Robust to the
// hooks/host move (removing src/) because it no longer relies on the
// compiled-file depth.
const DEFAULT_LOG_DIR = path.resolve(process.cwd(), "logs");

const app = express();
app.use(express.json({ limit: "10mb" }));
app.use(buildRouter(DEFAULT_LOG_DIR));

const server = createServer(app);
attachWss(server);

await initConfigStore();
await initBattleStore();

server.listen(PORT, "127.0.0.1", () => {
    console.log(`[host] listening on http://127.0.0.1:${PORT}`);
    console.log(`[host] default log dir: ${DEFAULT_LOG_DIR}`);
});
