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
//   GET  /api/configs                       → list captured BattleConfiguration metadata
//   GET  /api/configs/:id                   → full JSON of one capture
//   POST /api/configs/clear                 → wipe store
//   POST /api/_dev/shutdown

import express, { Router, Request, Response } from "express";
import { promises as fs } from "fs";
import path from "path";
import {
    getSession, listDevices, listProcesses, listSessions, postMessage,
    rpcCall, runScript, stopAll, stopSession,
} from "./sessions.js";
import { listConfigs, getConfig, clearConfigs } from "./config-store.js";
import {
    listRunners, latestDumpPath, registerRunner, removeRunner, pruneRunners,
} from "./battle-store.js";

export function buildRouter(defaultLogDir: string): Router {
    const router = express.Router();

    // Static mounts: browser view + extracted assets (PNGs + manifest.json).
    // `public/` is the frontend bundle-free source; `assets/public/` is built
    // by scripts/python/build_asset_manifest.py.
    const frida_root = path.resolve(process.cwd());
    router.use("/view", express.static(path.join(frida_root, "public")));
    router.use("/assets", express.static(path.join(frida_root, "assets", "public")));

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

    router.get("/api/configs", (_req: Request, res: Response) => {
        res.json(listConfigs());
    });

    router.get("/api/configs/:id", async (req: Request, res: Response) => {
        const json = await getConfig(req.params.id);
        if (!json) { res.status(404).json({ error: "config not found" }); return; }
        res.type("application/json").send(json);
    });

    router.post("/api/configs/clear", async (_req: Request, res: Response) => {
        res.json({ cleared: await clearConfigs() });
    });

    // Phase 3: orchestrate initRunner + applyAddUnit×N + startBattle
    // body: { configId, placements: [{unitId, playerId, col, row}], sessionId? }
    router.post("/api/launch", async (req: Request, res: Response) => {
        try {
            const { configId, placements, sessionId } = req.body as {
                configId: string;
                placements: Array<{ unitId: string; playerId: number; col: number; row: number }>;
                sessionId?: number;
            };
            if (!configId || !Array.isArray(placements)) {
                res.status(400).json({ error: "configId + placements[] required" });
                return;
            }
            const sid = sessionId ?? pickRunningSession();
            if (sid == null) {
                res.status(409).json({ error: "no running Frida session" });
                return;
            }
            const json = await getConfig(configId);
            if (!json) { res.status(404).json({ error: "config not found" }); return; }

            const init = await rpcCall(sid, "initRunner",
                [{ configJson: json }], 30000) as { runnerId: number; seed: number };
            const runnerId = init.runnerId;
            // Track (runnerId → configId) so the front can resume the session
            // and rebuild its map from the latest matchState dump.
            registerRunner(runnerId, sid, configId);

            for (const p of placements) {
                await rpcCall(sid, "applyAddUnit", [{
                    runnerId, unitId: p.unitId, playerId: p.playerId,
                    col: p.col, row: p.row,
                }], 10000);
            }

            await rpcCall(sid, "startBattle", [{ runnerId }], 30000);

            res.json({ ok: true, sessionId: sid, runnerId, seed: init.seed });
        } catch (e) {
            res.status(500).json({ error: (e as Error).message });
        }
    });

    // List known runners (registered via /api/launch or auto-inferred from
    // battle_event messages). Most recent first.
    router.get("/api/runners", (_req: Request, res: Response) => {
        res.json(listRunners());
    });

    // Reconcile host-side runner registry against the hook's in-memory runner
    // registry. Frida script reloads clear the hook registry; without this,
    // the front keeps showing dead runnerIds whose RPCs fail with
    // `runner N not found`. Called on front hard-reload.
    router.post("/api/runners/sync", async (_req: Request, res: Response) => {
        const sid = pickRunningSession();
        if (sid == null) {
            // No live session — can't verify. Prune everything to match
            // reality (the hook's registry is definitionally empty).
            const removed = await pruneRunners(new Set());
            res.json({ ok: true, sessionId: null, kept: [], removed });
            return;
        }
        try {
            const live = await rpcCall(sid, "listRunners", [], 5000) as Array<{
                runnerId: number;
            }>;
            const keep = new Set(live.map((r) => r.runnerId));
            const removed = await pruneRunners(keep);
            res.json({
                ok: true, sessionId: sid,
                kept: [...keep], removed,
            });
        } catch (e) {
            res.status(500).json({ error: (e as Error).message });
        }
    });

    // Dispose a runner: tells the hook to release GC roots, purges the host
    // registry entry, and wipes its on-disk event dumps.
    router.delete("/api/runners/:id", async (req: Request, res: Response) => {
        const id = parseInt(req.params.id, 10);
        if (!Number.isFinite(id)) { res.status(400).json({ error: "bad id" }); return; }
        const sid = pickRunningSession();
        if (sid != null) {
            try {
                await rpcCall(sid, "disposeRunner", [{ runnerId: id }], 5000);
            } catch (e) {
                // Hook may have lost the runner (restart, etc.) — proceed with
                // host-side cleanup regardless.
                console.log(`[router] disposeRunner(${id}) failed: ${(e as Error).message}`);
            }
        }
        const removed = await removeRunner(id);
        res.json({ ok: true, removed });
    });

    // Returns the latest matchState + events dump for a runner. The front uses
    // this to resume/restore a running battle after a page reload.
    router.get("/api/runners/:id/latest-state", async (req: Request, res: Response) => {
        const id = parseInt(req.params.id, 10);
        if (!Number.isFinite(id)) { res.status(400).json({ error: "bad id" }); return; }
        const p = latestDumpPath(id);
        if (!p) { res.status(404).json({ error: "no dump yet" }); return; }
        try {
            const content = await fs.readFile(p, "utf-8");
            res.type("application/json").send(content);
        } catch (e) {
            res.status(500).json({ error: (e as Error).message });
        }
    });

    // Dump unitId → assetNaming mapping from `IdunVisuals._unitConfigMap`
    // (authoritative game data, replaces the front-end heuristic). Caches to
    // disk so the front can load without needing an active Frida session.
    router.post("/api/unit-asset-map/refresh", async (_req: Request, res: Response) => {
        try {
            const sid = pickRunningSession();
            if (sid == null) { res.status(409).json({ error: "no running Frida session" }); return; }
            const result = await rpcCall(sid, "getUnitAssetMap", [], 10000) as {
                count: number; map: Record<string, { unitId: string; assetNaming: string }>;
            };
            const out = path.join(process.cwd(), "assets", "public", "unit-asset-map.json");
            await fs.writeFile(out, JSON.stringify(result.map, null, 2));
            res.json({ ok: true, count: result.count, path: "unit-asset-map.json" });
        } catch (e) {
            res.status(500).json({ error: (e as Error).message });
        }
    });

    function pickRunningSession(): number | null {
        const running = listSessions().filter((s) => s.status === "running");
        if (running.length === 0) return null;
        // Most recently started.
        return running[running.length - 1].id;
    }

    router.post("/api/_dev/shutdown", async (_req: Request, res: Response) => {
        try { await stopAll(); } catch { /* ignore */ }
        res.json({ ok: true });
        setTimeout(() => process.exit(0), 300);
    });

    return router;
}
