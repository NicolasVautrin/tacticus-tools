// Frida session management: attach, load scripts, RPC, message handling,
// graceful cleanup.
//
// Trimmed from the legacy server: no stack/enum/i2 enrichment (the hook
// bundle now emits structured data directly).
import frida from "frida";
import { openLog, appendLog, closeLog } from "./logger.js";
import { publish } from "./ws.js";
import { routeMessage } from "./router-messages.js";

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

let nextSessionId = 1;
const sessions = new Map<number, RunSession>();

export function listSessions(): RunSession[] {
    return [...sessions.values()].map(sanitize);
}

export function getSession(id: number): RunSession | undefined {
    const s = sessions.get(id);
    return s ? sanitize(s) : undefined;
}

export async function listDevices(): Promise<Array<{
    id: string; name: string; type: string;
}>> {
    const mgr = frida.getDeviceManager();
    const devices = await mgr.enumerateDevices();
    return devices.map((d) => ({ id: d.id, name: d.name, type: d.type }));
}

export async function listProcesses(serial: string): Promise<Array<{
    pid: number; name: string;
}>> {
    const device = await getDevice(serial);
    const processes = await device.enumerateProcesses();
    return processes.map((p) => ({ pid: p.pid, name: p.name }));
}

export interface RunScriptOpts {
    serial: string;
    mode: "attach" | "spawn";
    pid?: number;
    target?: string;
    source: string;
    logDir?: string;
}

export async function runScript(opts: RunScriptOpts): Promise<RunSession> {
    // Stop all existing sessions to avoid orphan hooks on the same process.
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

    if (opts.logDir) {
        openLog(sessionId, opts.logDir, opts.target ?? "unknown");
    }

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

/**
 * Graceful unload: post `{type:"cleanup"}` and wait up to 2s for the
 * hook to emit `{t:"cleanup_done"}`, then unload. Avoids detaching while
 * Interceptor.replace callbacks are mid-flight (can crash the game).
 */
export async function stopSession(id: number): Promise<void> {
    const session = sessions.get(id);
    if (!session || session.status !== "running") return;

    try {
        if (session.fridaScript) {
            session.fridaScript.post({ type: "cleanup" });
            await Promise.race([
                new Promise<void>((resolve) => {
                    const check = (message: frida.Message): void => {
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

/**
 * Invoke an rpc.exports method declared by the injected Frida script.
 * `args` may be positional (array) or a single object argument.
 */
export async function rpcCall(
    id: number,
    method: string,
    args: unknown[] | Record<string, unknown>,
    timeout = 10000,
): Promise<unknown> {
    const session = sessions.get(id);
    if (!session?.fridaScript || session.status !== "running") {
        throw new Error(`Session ${id} not running`);
    }

    // Frida exposes rpc.exports as an object of async functions under
    // script.exports — we awaited it once to get the map.
    const exports = (await (session.fridaScript as unknown as {
        exports: Promise<Record<string, (...a: unknown[]) => Promise<unknown>>>;
    }).exports);
    const fn = exports[method];
    if (typeof fn !== "function") {
        throw new Error(`Script does not export method '${method}'`);
    }

    const callArgs = Array.isArray(args) ? args : [args];
    const call = fn.apply(null, callArgs);

    const timeoutP = new Promise<never>((_, reject) => {
        setTimeout(() => reject(new Error(`RPC timeout after ${timeout}ms`)), timeout);
    });

    return Promise.race([call, timeoutP]);
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
    const envelope: Record<string, unknown> = {
        type: kind,
        ts: new Date().toISOString(),
        payload: message,
    };
    if (data) {
        envelope.data_b64 = data.toString("base64");
    }

    // Dispatch to a typed handler (if any) registered for payload.t. Handlers
    // can redact heavy fields from `envelope.payload` before broadcast/log.
    if (message.type === "send") {
        const p = (message as frida.SendMessage).payload;
        if (p && typeof p === "object") {
            routeMessage({
                sessionId,
                payload: p as Record<string, unknown>,
                envelope,
            });
        }
    }

    publish(sessionId, envelope);
    appendLog(sessionId, envelope);
}

function sanitize(s: RunSession): RunSession {
    // Strip internal Frida refs from the exposed session view.
    const { fridaSession: _fs, fridaScript: _fsc, ...rest } = s;
    return rest as RunSession;
}
