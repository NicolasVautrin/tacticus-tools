/**
 * Frida session management: attach, load scripts, RPC, message handling, cleanup.
 */

import frida from "frida";
import { getResolver } from "./symbol-resolver.js";
import { openLog, appendLog, closeLog } from "./jsonl-logger.js";
import { publish } from "./ws-stream.js";

// ---------- Types ----------

export interface RunSession {
  id: number;
  serial: string;
  pid: number;
  mode: "attach" | "spawn";
  status: "running" | "stopped" | "error";
  startedAt: string;
  endedAt?: string;
  errorMessage?: string;
  logDir?: string;
  fridaSession?: frida.Session;
  fridaScript?: frida.Script;
}

interface RpcPending {
  resolve: (result: unknown) => void;
  reject: (err: Error) => void;
  timer: ReturnType<typeof setTimeout>;
}

// ---------- State ----------

let nextSessionId = 1;
const sessions = new Map<number, RunSession>();
const rpcPending = new Map<string, RpcPending>();
let rpcCounter = 0;

// ---------- Public API ----------

export function listSessions(): RunSession[] {
  return [...sessions.values()].map(sanitize);
}

export function getSession(id: number): RunSession | undefined {
  const s = sessions.get(id);
  return s ? sanitize(s) : undefined;
}

export async function listDevices() {
  const mgr = frida.getDeviceManager();
  const devices = await mgr.enumerateDevices();
  return devices.map((d) => ({
    id: d.id,
    name: d.name,
    type: d.type,
  }));
}

export async function listProcesses(serial: string) {
  const device = await getDevice(serial);
  const processes = await device.enumerateProcesses();
  return processes.map((p) => ({ pid: p.pid, name: p.name }));
}

export async function runScript(opts: {
  serial: string;
  mode: "attach" | "spawn";
  pid?: number;
  target?: string;
  source: string;
  logDir?: string;
}): Promise<RunSession> {
  // Stop existing sessions to avoid orphan hooks
  await stopAll();

  const device = await getDevice(opts.serial);

  let pid: number;
  if (opts.mode === "spawn") {
    if (!opts.target) throw new Error("target required for spawn");
    pid = await device.spawn(opts.target);
  } else {
    if (!opts.pid) throw new Error("pid required for attach");
    pid = opts.pid;
  }

  const fridaSession = await device.attach(pid);
  const fridaScript = await fridaSession.createScript(opts.source);

  const sessionId = nextSessionId++;
  const session: RunSession = {
    id: sessionId,
    serial: opts.serial,
    pid,
    mode: opts.mode,
    status: "running",
    startedAt: new Date().toISOString(),
    logDir: opts.logDir,
    fridaSession,
    fridaScript,
  };
  sessions.set(sessionId, session);

  // Open JSONL log
  if (opts.logDir) {
    openLog(sessionId, opts.logDir, opts.target ?? "unknown");
  }

  // Message handler
  fridaScript.message.connect((message: frida.Message, data: Buffer | null) => {
    onMessage(sessionId, message, data);
  });

  fridaSession.detached.connect(() => {
    session.status = "stopped";
    session.endedAt = new Date().toISOString();
    closeLog(sessionId);
  });

  await fridaScript.load();

  if (opts.mode === "spawn") {
    await device.resume(pid);
  }

  return sanitize(session);
}

export async function stopSession(id: number): Promise<void> {
  const session = sessions.get(id);
  if (!session || session.status !== "running") return;

  try {
    // Graceful cleanup: ask script to revert hooks
    if (session.fridaScript) {
      session.fridaScript.post({ type: "cleanup" });
      // Wait up to 2s for cleanup_done
      await Promise.race([
        new Promise<void>((resolve) => {
          const check = (message: frida.Message) => {
            if (
              message.type === "send" &&
              (message as frida.SendMessage).payload?.t === "cleanup_done"
            ) {
              session.fridaScript?.message.disconnect(check);
              resolve();
            }
          };
          session.fridaScript?.message.connect(check);
        }),
        new Promise<void>((resolve) => setTimeout(resolve, 2000)),
      ]);
      await session.fridaScript.unload();
    }
    if (session.fridaSession) {
      await session.fridaSession.detach();
    }
  } catch {
    // Already detached
  }

  session.status = "stopped";
  session.endedAt = new Date().toISOString();
  closeLog(id);
}

export async function stopAll(): Promise<void> {
  for (const [id, session] of sessions) {
    if (session.status === "running") {
      await stopSession(id);
    }
  }
}

export async function rpcCall(
  id: number,
  method: string,
  args: Record<string, unknown>,
  timeout = 10000,
): Promise<unknown> {
  const session = sessions.get(id);
  if (!session?.fridaScript || session.status !== "running") {
    throw new Error(`Session ${id} not running`);
  }

  const rpcId = String(++rpcCounter);

  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => {
      rpcPending.delete(rpcId);
      reject(new Error(`RPC timeout after ${timeout}ms`));
    }, timeout);

    rpcPending.set(rpcId, { resolve, reject, timer });

    session.fridaScript!.post({
      type: "rpc",
      id: rpcId,
      method,
      args,
    });
  });
}

export function postMessage(id: number, message: unknown): void {
  const session = sessions.get(id);
  if (!session?.fridaScript || session.status !== "running") {
    throw new Error(`Session ${id} not running`);
  }
  session.fridaScript.post(message as frida.Message);
}

// ---------- Internal ----------

async function getDevice(serial: string): Promise<frida.Device> {
  const mgr = frida.getDeviceManager();
  const devices = await mgr.enumerateDevices();
  const device = devices.find((d) => d.id === serial);
  if (!device) throw new Error(`Device ${serial} not found`);
  return device;
}

function onMessage(sessionId: number, message: frida.Message, data: Buffer | null): void {
  const kind = message.type === "send" ? "send" : "error";

  // Intercept RPC responses
  if (kind === "send") {
    const payload = (message as frida.SendMessage).payload;
    if (payload && typeof payload === "object" && payload.t === "rpc_response") {
      const rpcId = String(payload.id ?? "");
      let result = payload.result;

      // Enrich RPC results
      const resolver = getResolver();
      if (resolver.isLoaded && result && typeof result === "object") {
        result = resolver.enrichPayload(result);
      }

      const pending = rpcPending.get(rpcId);
      if (pending) {
        clearTimeout(pending.timer);
        rpcPending.delete(rpcId);
        pending.resolve(result);
      }
      return; // Don't publish RPC plumbing
    }
  }

  // Enrich regular messages
  let enrichedMessage: unknown = message;
  const resolver = getResolver();
  if (resolver.isLoaded && kind === "send") {
    const payload = (message as frida.SendMessage).payload;
    if (payload && typeof payload === "object") {
      const enriched = resolver.enrichPayload(payload);
      enrichedMessage = { ...message, payload: enriched };
    }
  }

  const envelope: Record<string, unknown> = {
    type: kind,
    ts: new Date().toISOString(),
    payload: enrichedMessage,
  };
  if (data) {
    envelope.data_b64 = data.toString("base64");
  }

  // Publish to WS + JSONL
  publish(sessionId, envelope);
  appendLog(sessionId, envelope);
}

function sanitize(s: RunSession): RunSession {
  // Strip Frida objects from the returned session
  const { fridaSession, fridaScript, ...rest } = s;
  return rest as RunSession;
}
