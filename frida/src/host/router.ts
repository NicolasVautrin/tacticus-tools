// HTTP API routes.
//
//   GET  /api/health
//   GET  /api/devices
//   GET  /api/devices/:serial/processes
//   POST /api/scripts/run                   body: { serial, mode, pid?, target?, source, log_dir?, stop_previous? }
//   POST /api/scripts/:id/stop
//   POST /api/scripts/:id/rpc               body: { method, args?, timeout? }
//   POST /api/scripts/:id/message           body: arbitrary
//   GET  /api/scripts/:id
//   GET  /api/sessions
//   POST /api/_dev/shutdown

import express, { Router, Request, Response } from "express";
import path from "path";
import {
    getSession, listDevices, listProcesses, listSessions, postMessage,
    rpcCall, runScript, stopAll, stopSession,
} from "./sessions.js";

export function buildRouter(defaultLogDir: string): Router {
    const router = express.Router();

    router.get("/api/health", (_req: Request, res: Response) => {
        res.json({ status: "ok" });
    });

    router.get("/api/devices", async (_req: Request, res: Response) => {
        try { res.json(await listDevices()); }
        catch (e) { res.status(500).json({ error: (e as Error).message }); }
    });

    router.get("/api/devices/:serial/processes",
        async (req: Request, res: Response) => {
            try { res.json(await listProcesses(req.params.serial)); }
            catch (e) { res.status(500).json({ error: (e as Error).message }); }
        });

    router.post("/api/scripts/run", async (req: Request, res: Response) => {
        try {
            const { serial, mode, pid, target, source, log_dir, stop_previous } = req.body;
            if (!serial || !mode || !source) {
                res.status(400).json({ error: "serial, mode, source required" });
                return;
            }

            // Stop previously-running sessions for the same PID (default: true)
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
                logDir: log_dir ?? defaultLogDir,
            });
            res.json({
                run_session_id: session.id,
                pid: session.pid,
                mode: session.mode,
                status: session.status,
            });
        } catch (e) {
            res.status(500).json({ error: (e as Error).message });
        }
    });

    router.post("/api/scripts/:id/stop", async (req: Request, res: Response) => {
        try {
            await stopSession(Number(req.params.id));
            res.json({ ok: true });
        } catch (e) {
            res.status(500).json({ error: (e as Error).message });
        }
    });

    router.post("/api/scripts/:id/rpc", async (req: Request, res: Response) => {
        try {
            const { method, args, timeout } = req.body;
            if (!method) {
                res.status(400).json({ error: "method required" });
                return;
            }
            const result = await rpcCall(
                Number(req.params.id),
                method,
                args ?? [],
                timeout ?? 10000,
            );
            res.json({ result });
        } catch (e) {
            res.status(500).json({ error: (e as Error).message });
        }
    });

    router.post("/api/scripts/:id/message", (req: Request, res: Response) => {
        try {
            postMessage(Number(req.params.id), req.body);
            res.json({ ok: true });
        } catch (e) {
            res.status(500).json({ error: (e as Error).message });
        }
    });

    router.get("/api/scripts/:id", (req: Request, res: Response) => {
        const session = getSession(Number(req.params.id));
        if (!session) { res.status(404).json({ error: "Session not found" }); return; }
        res.json(session);
    });

    router.get("/api/sessions", (_req: Request, res: Response) => {
        res.json(listSessions());
    });

    router.post("/api/_dev/shutdown", async (_req: Request, res: Response) => {
        try { await stopAll(); } catch { /* ignore */ }
        res.json({ ok: true });
        setTimeout(() => process.exit(0), 300);
    });

    return router;
}
