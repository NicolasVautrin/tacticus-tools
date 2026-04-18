// Host entrypoint — Express + WebSocket server.
// Manages Frida sessions, routes HTTP RPC, persists `send()` to JSONL logs.

import express from "express";
import { createServer } from "http";
import path from "path";
import { fileURLToPath } from "url";
import { buildRouter } from "./router.js";
import { attachWss } from "./ws.js";

const PORT = parseInt(process.env.PORT ?? "8765", 10);

const __dirname = path.dirname(fileURLToPath(import.meta.url));
// logs/ lives at the repo root (../../../logs from src/host/ in dev via tsx,
// or from dist/host/ in prod — same depth).
const DEFAULT_LOG_DIR = path.resolve(__dirname, "../../../logs");

const app = express();
app.use(express.json({ limit: "10mb" }));
app.use(buildRouter(DEFAULT_LOG_DIR));

const server = createServer(app);
attachWss(server);

server.listen(PORT, "127.0.0.1", () => {
    console.log(`[host] listening on http://127.0.0.1:${PORT}`);
    console.log(`[host] default log dir: ${DEFAULT_LOG_DIR}`);
});
