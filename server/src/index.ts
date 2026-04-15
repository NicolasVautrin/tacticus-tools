/**
 * tacticus-tools server — minimal Frida bridge for WH40K Tacticus.
 */

import express from "express";
import { createServer } from "http";
import path from "path";
import { getResolver } from "./symbol-resolver.js";
import {
  listDevices,
  listProcesses,
  runScript,
  stopSession,
  getSession,
  listSessions,
  rpcCall,
  postMessage,
} from "./frida-manager.js";
import { attachWss } from "./ws-stream.js";

const PORT = parseInt(process.env.PORT ?? "8765", 10);
const DATA_DIR = path.resolve(__dirname, "../../data");

const app = express();
app.use(express.json({ limit: "10mb" }));

// ==================== Health ====================

app.get("/api/health", (_req, res) => {
  const resolver = getResolver();
  res.json({
    status: "ok",
    symbolsLoaded: resolver.isLoaded,
    methods: resolver.methodCount,
    enums: resolver.enumCount,
    abilityConfigs: resolver.abilityConfigCount,
  });
});

// ==================== Devices ====================

app.get("/api/devices", async (_req, res) => {
  try {
    res.json(await listDevices());
  } catch (e: any) {
    res.status(500).json({ error: e.message });
  }
});

app.get("/api/devices/:serial/processes", async (req, res) => {
  try {
    res.json(await listProcesses(req.params.serial));
  } catch (e: any) {
    res.status(500).json({ error: e.message });
  }
});

// ==================== Scripts ====================

app.post("/api/scripts/run", async (req, res) => {
  try {
    const { serial, mode, pid, target, source, log_dir, stop_previous } = req.body;
    if (!serial || !mode || !source) {
      return res.status(400).json({ error: "serial, mode, source required" });
    }

    // Stop previous running sessions for the same PID (default: true)
    if (stop_previous !== false && pid) {
      const running = listSessions().filter(
        (s) => s.pid === Number(pid) && s.status === "running",
      );
      for (const s of running) {
        try { await stopSession(s.id); } catch { /* ignore */ }
      }
      if (running.length > 0) {
        await new Promise((r) => setTimeout(r, 50));
      }
    }

    const session = await runScript({
      serial,
      mode,
      pid: pid ? Number(pid) : undefined,
      target,
      source,
      logDir: log_dir ?? path.resolve(__dirname, "../../logs"),
    });
    res.json({
      run_session_id: session.id,
      pid: session.pid,
      mode: session.mode,
      status: session.status,
    });
  } catch (e: any) {
    res.status(500).json({ error: e.message });
  }
});

app.post("/api/scripts/:id/stop", async (req, res) => {
  try {
    await stopSession(Number(req.params.id));
    res.json({ ok: true });
  } catch (e: any) {
    res.status(500).json({ error: e.message });
  }
});

app.post("/api/scripts/:id/rpc", async (req, res) => {
  try {
    const { method, args, timeout } = req.body;
    if (!method) return res.status(400).json({ error: "method required" });
    const result = await rpcCall(
      Number(req.params.id),
      method,
      args ?? {},
      timeout ?? 10000,
    );
    res.json({ result });
  } catch (e: any) {
    res.status(500).json({ error: e.message });
  }
});

app.post("/api/scripts/:id/message", (req, res) => {
  try {
    postMessage(Number(req.params.id), req.body);
    res.json({ ok: true });
  } catch (e: any) {
    res.status(500).json({ error: e.message });
  }
});

app.get("/api/scripts/:id", (req, res) => {
  const session = getSession(Number(req.params.id));
  if (!session) return res.status(404).json({ error: "Session not found" });
  res.json(session);
});

app.get("/api/sessions", (_req, res) => {
  res.json(listSessions());
});

// ==================== Dev ====================

app.post("/api/_dev/shutdown", async (_req, res) => {
  try {
    const { stopAll: stopAllSessions } = await import("./frida-manager.js");
    await stopAllSessions();
  } catch { /* ignore */ }
  res.json({ ok: true });
  setTimeout(() => process.exit(0), 300);
});

// ==================== Startup ====================

const server = createServer(app);
attachWss(server);

// Load symbols
const symbolsPath = path.join(DATA_DIR, "symbols.json");
const resolver = getResolver();
if (resolver.load(symbolsPath)) {
  console.log(
    `[startup] Loaded ${resolver.methodCount} methods + ${resolver.enumCount} enums + ${resolver.abilityConfigCount} ability configs`,
  );
} else {
  console.log(`[startup] No symbols.json at ${symbolsPath}`);
}

server.listen(PORT, "127.0.0.1", () => {
  console.log(`[startup] Server listening on http://127.0.0.1:${PORT}`);
});
