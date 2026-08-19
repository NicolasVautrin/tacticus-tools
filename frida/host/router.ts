// HTTP API routes.
//
//   GET  /api/health
//   GET  /api/admin/status                  → consolidated Tacticus + session state
//   GET  /api/admin/candidates              → debug: all Tacticus-named procs
//   POST /api/admin/inject                  body: { pid? }
//   POST /api/scripts/run                   body: { mode, pid?, target?, source, log_dir?, stop_previous? }
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
import { promises as fs, readFileSync, existsSync } from "fs";
import path from "path";
import {
    getSession, listProcesses, listSessions, postMessage, pickLiveSessionId,
    rpcCall, runScript, stopAllPreservingState, stopSession,
} from "./sessions.js";
import { aiTraceStoreStatus } from "./ai-trace-store.js";
import {
    listConfigs, getConfig, getReplayBundle, clearConfigs,
    deleteConfig, saveConfig, updateConfigDescription,
} from "./config-store.js";
import {
    listRunners, latestDumpPath, registerRunner, removeRunner, pruneRunners,
    hasRunner,
} from "./battle-store.js";
import { listGateStats, setCap, setTimeoutScale, resetStats } from "./rpc-queue.js";
import {
    getDrainState, setDrain, resetDrainCounters, isDrainRefusal,
    listCreationMethods,
} from "./drain.js";
import {
    findTacticusCandidates, injectBundle, TacticusCandidate,
} from "./admin.js";
import { syncMetadata, syncCampaignCatalog, syncMoWCatalog, activeMetaVersion } from "./meta-sync.js";

/** RVA → "Class.method" map, lazy-loaded from data/all_game_targets_win.tsv.
 * Used to symbolicate IL2CPP backtraces (DebugSymbol on Windows IL2CPP only
 * resolves native exports, so every IL2CPP method lands on "mono_type_size"). */
let il2cppRvaMap: Map<number, string> | null = null;
function loadIl2cppRvaMap(): Map<number, string> {
    if (il2cppRvaMap !== null) return il2cppRvaMap;
    const tsv = path.resolve(
        process.cwd(), "..", "data", "all_game_targets_win.tsv");
    const m = new Map<number, string>();
    if (!existsSync(tsv)) {
        console.warn("[router] symbol map missing: " + tsv);
        il2cppRvaMap = m; return m;
    }
    const data = readFileSync(tsv, "utf8");
    let lines = 0, parsed = 0;
    for (const line of data.split("\n")) {
        lines++;
        if (!line) continue;
        const parts = line.split("\t");
        if (parts.length < 3) continue;
        const rva = parseInt(parts[2].trim(), 16);
        if (isNaN(rva)) continue;
        // For collisions (different overloads at the same RVA — shouldn't
        // happen but defensive), keep the FIRST entry (most specific name).
        if (!m.has(rva)) m.set(rva, parts[1]);  // method FQN
        parsed++;
    }
    console.log("[router] symbol map loaded · lines=" + lines
        + " · entries=" + parsed);
    il2cppRvaMap = m;
    return m;
}

/** Resolve a single RVA → "Class.method @ rva". Falls back to "?".  */
function symbolicate(rva: number): string {
    const map = loadIl2cppRvaMap();
    const exact = map.get(rva);
    if (exact) return exact + " @ 0x" + rva.toString(16);
    // Walk-back search: methods aren't 1-byte. Try up to 64KiB back.
    for (let off = 1; off < 0x10000; off++) {
        const hit = map.get(rva - off);
        if (hit) return hit + "+0x" + off.toString(16)
            + " @ 0x" + rva.toString(16);
    }
    return "<unknown> @ 0x" + rva.toString(16);
}

/** Rend une erreur d'RPC en HTTP.
 *
 * Un refus de DRAIN (#285) sort en **503 + `Retry-After`** et non en 500 : c'est
 * une indisponibilite TEMPORAIRE et ATTENDUE, pas une panne. Le CORPS garde la
 * forme `{ error: <message> }` de toujours — c'est ce que lisent tous les
 * appelants Python (`resp.get("error")`), et c'est ce qui fait remonter le
 * message jusqu'a l'agent sans toucher a un seul d'entre eux. */
function sendRpcError(res: Response, e: unknown): void {
    const message = (e as Error).message;
    if (isDrainRefusal(e)) {
        res.setHeader("Retry-After", String(e.retryAfterSec));
        res.status(503).json({ error: message, drain: true,
                               retryAfterSec: e.retryAfterSec });
        return;
    }
    res.status(500).json({ error: message });
}

export function buildRouter(defaultLogDir: string): Router {
    const router = express.Router();

    // Static mounts: browser view + extracted assets (PNGs + manifest.json).
    // `public/` is the frontend bundle-free source; `assets/public/` is built
    // by scripts/python/build_asset_manifest.py.
    const frida_root = path.resolve(process.cwd());
    router.use("/view", express.static(path.join(frida_root, "public")));
    router.use("/assets", express.static(path.join(frida_root, "assets", "public")));
    // Per-version metadata (enums, i18n, …) generated by /api/meta/sync.
    router.use("/meta", express.static(path.join(frida_root, "data", "meta")));

    router.get("/api/health", (_req: Request, res: Response) => {
        res.json({ status: "ok" });
    });

    router.get("/api/processes", async (_req: Request, res: Response) => {
        try { res.json(await listProcesses()); }
        catch (e) { res.status(500).json({ error: (e as Error).message }); }
    });

    router.post("/api/scripts/run", async (req: Request, res: Response) => {
        try {
            const { mode, pid, target, source, log_dir, stop_previous } = req.body;
            if (!mode || !source) {
                res.status(400).json({ error: "mode, source required" });
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
                mode,
                pid: pid ? Number(pid) : undefined,
                target,
                source,
                // OPT-IN : sans `log_dir` explicite, on n'ecrit PAS de run-log.
                // Le defaut etait `?? defaultLogDir` -> chaque message de l'agent
                // (donc chaque reponse RPC) partait sur disque, sans lecteur.
                logDir: log_dir,
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
            sendRpcError(res, e);
        }
    });

    // SELF-PLAY turn hand-off (cf. docs/rl/design.md §Self-play). Long-poll : bloque
    // CÔTÉ HOST jusqu'à ce que ce soit le tour du joueur `player` (= currentPlayer du
    // runner), OU que la battle soit finie (stage != Running), OU timeout. L'agent
    // player émet UN seul GET par tour (pas de boucle sleep côté client — le foreground
    // sleep est bloqué par le harness). Poll léger via la RPC `battleStatus` (PAS
    // decisionView, qui peut overrun une frame).
    //   GET /api/selfplay/:id/await?runnerId=R&player=P[&timeoutMs=90000][&pollMs=400]
    //   -> { ok, yourTurn, gameOver, currentPlayer, stage, stageName, timedOut? }
    router.get("/api/selfplay/:id/await", async (req: Request, res: Response) => {
        const id = Number(req.params.id);
        const runnerId = Number(req.query.runnerId);
        const player = Number(req.query.player);
        const timeoutMs = Math.min(300000, Number(req.query.timeoutMs) || 90000);
        const pollMs = Math.max(100, Number(req.query.pollMs) || 400);
        if (!Number.isFinite(runnerId) || !Number.isFinite(player)) {
            res.status(400).json({ error: "runnerId and player (query params) required" });
            return;
        }
        const deadline = Date.now() + timeoutMs;
        const sleep = (ms: number): Promise<void> =>
            new Promise((r) => setTimeout(r, ms));
        // TF19 : un timeout/erreur TRANSITOIRE du poll interne `battleStatus` (queue RPC
        // saturée pendant le pump Unity du tour adverse) NE DOIT PAS remonter comme un
        // échec — un raw 500 « RPC timeout 15000ms » se lit comme un vrai fail. On l'AVALE
        // et on continue à long-poller jusqu'à la deadline, puis on renvoie un `timedOut`
        // UNIFORME (+ `transientError` pour la visibilité). Le caller ré-émet l'await.
        type BS = { ok?: boolean; error?: string; stage?: number;
                    stageName?: string; currentPlayer?: number };
        let transientError: string | null = null;
        try {
            for (;;) {
                let r: BS | null = null;
                try {
                    r = (await rpcCall(id, "battleStatus", [{ runnerId }], 15000)) as BS;
                } catch (e) {
                    transientError = (e as Error).message;  // transitoire -> on re-poll
                }
                if (r && r.ok === false) {
                    // échec DÉFINITIF (ex. runner introuvable = nuke concurrent) -> surfacer.
                    res.status(502).json({ error: r.error || "battleStatus failed" });
                    return;
                }
                const stage = r?.stage;
                const currentPlayer = r?.currentPlayer;
                // stage 1 = Running ; tout autre = battle terminée (plus de tours).
                if (stage !== undefined && stage !== 1) {
                    res.json({ ok: true, gameOver: true, yourTurn: false,
                        currentPlayer, stage, stageName: r?.stageName });
                    return;
                }
                if (currentPlayer === player) {
                    res.json({ ok: true, yourTurn: true, gameOver: false,
                        currentPlayer, stage, stageName: r?.stageName });
                    return;
                }
                if (Date.now() >= deadline) {
                    res.json({ ok: true, yourTurn: false, gameOver: false,
                        timedOut: true, currentPlayer, stage, stageName: r?.stageName,
                        ...(transientError ? { transientError } : {}) });
                    return;
                }
                await sleep(pollMs);
            }
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

    // ---------- Admin: Tacticus auto-discovery + injection ----------

    router.get("/api/admin/candidates", async (_req: Request, res: Response) => {
        try { res.json({ candidates: await findTacticusCandidates() }); }
        catch (e) { res.status(500).json({ error: (e as Error).message }); }
    });

    /** Consolidated state used by the front-end status banner. */
    router.get("/api/admin/status", async (_req: Request, res: Response) => {
        try {
            const candidates = await findTacticusCandidates();
            const game = candidates.find((c) => c.isGame) ?? null;
            const launcherOnly = candidates.length > 0 && !game;
            const sid = pickRunningSession();
            const session = sid != null ? getSession(sid) ?? null : null;
            const metaVersion = await activeMetaVersion();
            res.json({
                tacticus: {
                    running: !!game,
                    launcherOnly,
                    gamePid: game?.pid ?? null,
                    gamePath: game?.path ?? null,
                    candidates,
                },
                session: session ? {
                    id: session.id,
                    pid: session.pid,
                    status: session.status,
                    startedAt: session.startedAt,
                    errorMessage: session.errorMessage,
                } : null,
                version: metaVersion,
            });
        } catch (e) {
            res.status(500).json({ error: (e as Error).message });
        }
    });

    router.post("/api/admin/inject", async (req: Request, res: Response) => {
        try {
            const { pid } = req.body ?? {};
            const targetPid = pid !== undefined ? Number(pid) : undefined;

            // Stop any running session(s) on the same target BEFORE injecting.
            // stopSession() runs the cleanup protocol (post {type:"cleanup"} +
            // wait for {t:"cleanup_done"}) so Interceptor.replace callbacks
            // wind down cleanly before unload — without this we'd just stack
            // multiple Frida agents in the same process, all firing.
            const running = listSessions().filter((s) => s.status === "running");
            // If a target PID was provided, only stop sessions for THAT pid;
            // otherwise stop all running sessions (auto-discovery flow).
            const toStop = targetPid !== undefined
                ? running.filter((s) => s.pid === targetPid)
                : running;
            for (const s of toStop) {
                try { await stopSession(s.id); }
                catch (e) { console.log(`[inject] stopSession(${s.id}) failed: ${(e as Error).message}`); }
            }
            // Brief pause so Frida fully releases the previous attach before
            // we re-attach (helps avoid "session already attached" races).
            if (toStop.length > 0) await new Promise((r) => setTimeout(r, 100));

            const { session, bundleBytes } = await injectBundle({
                pid: targetPid,
                // Pas de run-log par defaut (cf. `logDir` de /api/run ci-dessus).
                // C'est CE chemin qui produisait les 3 663 Mo de frida/logs/ :
                // l'inject est la voie normale, et il journalisait tout.
                logDir: req.body?.log_dir,
            });

            // Fast meta sync — RPC-only (enums). Heavy bits (i18n via
            // Python/UnityPy) are deferred to an explicit /api/meta/sync
            // call. Non-fatal: injection succeeded regardless.
            let meta: unknown = null;
            let metaError: string | null = null;
            try {
                meta = await syncMetadata(session.id, "fast");
            } catch (e) {
                metaError = (e as Error).message;
            }

            // AMORCE ENCHAINEE — une LECTURE de deux champs sur `IdunNavigation`
            // (`_gameConfig`, `_unitProgression`), rien d'autre. Elle ne pilote AUCUNE
            // UI et n'entre dans AUCUNE bataille.
            //
            // ⚠ CE QU'ELLE REMPLACE, ET POURQUOI. L'inject enchainait un cycle qui
            // ENTRAIT EN BATAILLE puis se retirait (~14 s), au motif que sans lui les
            // caches `MethodInfo*` seraient vides et l'init IL2CPP non amorcee -> crash
            // `0x2c`. Mesure du 2026-08-19 sur un process FROID (jeu relance, aucune
            // bataille jamais entree) : le runner se monte en 8,1 s et se JOUE
            // (`aiturn`, 156 events, stage `Running`), sans aucun crash. Le seul
            // manquant reel etait `lastGameConfig` -- sans lui `previewBis` refuse et
            // crit/block valent 0 sur toutes les unites (#419-r5). Et ce pointeur se
            // lit sur un ECRAN META, pas dans une bataille.
            //
            // Elle n'est pas non plus une porte : un echec est RAPPORTE, il ne refuse
            // rien. `amorce: false` pour l'eviter explicitement.
            let amorce: unknown = null;
            let amorceError: string | null = null;
            if (req.body?.amorce === false) {
                amorceError = "sautee sur demande explicite (amorce: false)";
            } else {
                try {
                    amorce = await rpcCall(session.id, "autoBootExtraire", [{}], 30000);
                } catch (e) {
                    amorceError = (e as Error).message;
                }
            }

            res.json({
                ok: true,
                sessionId: session.id,
                pid: session.pid,
                status: session.status,
                bundleBytes,
                meta,
                metaError,
                amorce,
                amorceError,
            });
        } catch (e) {
            const msg = (e as Error).message;
            const candidates = (e as { candidates?: TacticusCandidate[] }).candidates;
            // Multiple game candidates → 409 with the list; UI can prompt.
            if (candidates && candidates.length > 1) {
                res.status(409).json({ error: msg, candidates });
                return;
            }
            // No game running → 404; banner will already say so.
            if (msg.startsWith("no Tacticus game process found")) {
                res.status(404).json({ error: msg });
                return;
            }
            res.status(500).json({ error: humanizeFridaError(msg) });
        }
    });

    // AMORCE — point d'entree unique cote host, pour les cas ou la session existe
    // deja. `/api/admin/inject` l'enchaine tout seul ; celle-ci sert a la rejouer
    // (elle est idempotente : elle relit les memes deux champs).
    router.post("/api/admin/amorce", async (_req: Request, res: Response) => {
        try {
            const sid = pickRunningSession();
            if (sid === null) {
                res.status(409).json({
                    error: "aucune session Frida vivante — injecter d'abord "
                        + "(POST /api/admin/inject, qui enchaine deja l'amorce)",
                });
                return;
            }
            const result = await rpcCall(sid, "autoBootExtraire", [{}], 30000);
            const ok = (result as { ok?: boolean } | null)?.ok === true;
            res.status(ok ? 200 : 500).json({ sessionId: sid, ...(result as object) });
        } catch (e) {
            res.status(500).json({ error: (e as Error).message });
        }
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

    router.delete("/api/configs/:id", async (req: Request, res: Response) => {
        const ok = await deleteConfig(req.params.id);
        if (!ok) { res.status(404).json({ error: "not found" }); return; }
        res.json({ ok: true });
    });

    /** Set/update the user-facing description on a saved capture. Body:
     *   { description: string }  — empty/whitespace clears it.
     * Returns the updated meta. */
    router.patch("/api/configs/:id", async (req: Request, res: Response) => {
        const { description } = req.body ?? {};
        if (typeof description !== "string" && description !== null) {
            res.status(400).json({ error: "description (string|null) required" });
            return;
        }
        const meta = await updateConfigDescription(req.params.id, description);
        if (!meta) { res.status(404).json({ error: "not found" }); return; }
        res.json({ ok: true, meta });
    });

    // Phase 3: orchestrate initRunner + applyAddUnit×N + startBattle
    // body: { configId, placements, sessionId?, inlineConfig?, inlineMeta? }
    //   - inlineConfig: when set (campaign-builder generated config that
    //     was held in memory only), the JSON is persisted to the
    //     archive at engage time so the setup can be reloaded later.
    router.post("/api/launch", async (req: Request, res: Response) => {
        try {
            const { configId, placements, sessionId, inlineConfig, inlineMeta } =
                req.body as {
                    configId: string;
                    placements: Array<{ unitId: string; playerId: number; col: number; row: number }>;
                    sessionId?: number;
                    inlineConfig?: string;
                    inlineMeta?: {
                        mode?: string;
                        campaignId?: string | null;
                        locationIndex?: number | null;
                    };
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
            // Resolve the BattleConfiguration JSON. Two paths:
            //   1. inlineConfig provided → save to archive then use it.
            //   2. otherwise → look it up in the existing archive.
            let json: string | undefined;
            if (typeof inlineConfig === "string" && inlineConfig.length > 0) {
                await saveConfig({
                    id: configId,
                    mode: inlineMeta?.mode ?? "engaged",
                    sessionId: sid,
                    campaignId: inlineMeta?.campaignId ?? null,
                    locationIndex: inlineMeta?.locationIndex ?? null,
                }, inlineConfig);
                json = inlineConfig;
            } else {
                json = await getConfig(configId);
            }
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
            // Route CREATRICE de runner : un drain la refuse, et le refus doit
            // ressortir en 503 comme sur la voie RPC generique (meme corps
            // `{ error }`, meme marqueur).
            sendRpcError(res, e);
        }
    });

    // Runners VIVANTS connus du host — CACHE de presentation, PAS un historique
    // et PAS une jauge de capacite (#321). Alimente par `/api/launch` et par
    // auto-inference sur les `battle_event`; purge a la mort du runner
    // (`rpcCall` relit `disposeRunner`, cf. host/sessions.ts) et rattrape par
    // `host/runner-reconcile.ts`. Plus recent d'abord.
    //
    // CE COMPTEUR NE GATE RIEN. Le plafond `MAX_RUNNERS` (= 50) vit et
    // s'applique COTE HOOKS, dans `frida/hooks/game/runner-registry.ts`, compare
    // a `listRunners()` du MEME module, aux deux seuls points de creation :
    // `initAndStart` (`frida/hooks/features/launch.ts`) et `buildPatchedRunner`
    // (`frida/hooks/features/battle-config.ts`). Le nombre rendu ici n'entre
    // dans aucune de ces deux comparaisons.
    //
    // Le 2026-07-31 cette route rendait 306 entrees quand la RPC `listRunners`
    // des hooks en rendait 0, et l'ecart s'est lu « 303 runners vivants pour un
    // cap de 50 » — une alerte capacite qui ne pouvait pas etre vraie, puisque
    // les builds continuaient de passer. Pour compter des runners VIVANTS, la
    // seule source est la RPC `listRunners` (ou `GET /api/admin/drain`, champ
    // `liveRunners`, qui l'interroge avec le tri-etat qui va bien).
    router.get("/api/runners", (_req: Request, res: Response) => {
        res.json(listRunners());
    });

    // RPC concurrency gate — capacity instrument for parallel runners.
    //   GET  /api/rpc-queue                      → per-session telemetry
    //   POST /api/rpc-queue { cap?, id?, reset? } → set cap (≤0/null=uncapped)
    //                                               and/or reset counters
    // Measures how many concurrent callers (≈ sub-agents) the single Frida pump
    // absorbs before avgInFlight→N / avgRpcMs climbs (i.e. it stops "breathing").
    // MODE DRAIN (#285) — suspendre la CREATION de runner sans toucher aux
    // runners en place, pour laisser une fenetre de reinject/restart s'ouvrir
    // d'elle-meme au lieu de reveiller les agents.
    //
    //   GET  /api/admin/drain  -> { enabled, message, retryAfterSec, since,
    //                               refusedTotal, refusedByMethod, lastRefusals,
    //                               creationMethods, liveRunners }
    //   POST /api/admin/drain  body: { enabled, message?, retryAfterSec?,
    //                                  resetCounters? }
    //
    // `liveRunners` est LA jauge de convergence : le drain est « atteint » quand
    // elle tombe a 0, et c'est ce qui autorise le reinject.
    //
    // ELLE LIT LE REGISTRE DES HOOKS, PAS CELUI DU HOST — et la nuance n'est pas
    // theorique : MESUREE le 2026-07-30, juste apres une dispose reussie, le
    // registre du host annoncait 2 runners quand celui des hooks etait VIDE. Le
    // registre host est un cache, il derive (d'ou l'existence de
    // `/api/runners/sync`). Une jauge de convergence bATie dessus ne serait jamais
    // tombee a zero : on aurait attendu sans fin, ou -- pire -- conclu l'inverse
    // un jour ou il sous-compte, et reinjecte sur des runners bien vivants.
    //
    // Tri-etat ASSUME, meme discipline que `host_inputs.py` (#273) :
    //   nombre -> mesure cote hooks (`liveRunnersSource: "hooks"`)
    //   null   -> PAS mesure (aucune session, ou RPC en echec) + `liveRunnersError`
    // Jamais de 0 par defaut : « je n'ai pas pu compter » ne doit pas se lire
    // « il n'y a rien », sinon la jauge autorise le reinject au pire moment.
    router.get("/api/admin/drain", async (_req: Request, res: Response) => {
        let liveRunners: number | null = null;
        let liveRunnersError: string | null = null;
        const sid = pickLiveSessionId();
        if (sid == null) {
            liveRunnersError = "aucune session Frida vivante";
        } else {
            try {
                const live = await rpcCall(sid, "listRunners", [], 5000) as
                    Array<{ runnerId: number }>;
                liveRunners = Array.isArray(live) ? live.length : null;
                if (liveRunners === null) liveRunnersError = "reponse listRunners inattendue";
            } catch (e) {
                liveRunnersError = (e as Error).message;
            }
        }
        res.json({
            ok: true,
            ...getDrainState(),
            creationMethods: listCreationMethods(),
            liveRunners,
            liveRunnersSource: liveRunners === null ? null : "hooks",
            liveRunnersError,
            // Le cache host, expose SEULEMENT pour rendre la derive visible.
            // Ne JAMAIS s'en servir comme jauge : cf. le bloc ci-dessus.
            hostRegistryRunners: listRunners().length,
        });
    });

    router.post("/api/admin/drain", (req: Request, res: Response) => {
        const body = (req.body ?? {}) as {
            enabled?: boolean; message?: string;
            retryAfterSec?: number; resetCounters?: boolean;
        };
        if (typeof body.enabled !== "boolean") {
            res.status(400).json({
                error: "body.enabled (boolean) requis — "
                     + "{ enabled: true } arme le drain, { enabled: false } le leve",
            });
            return;
        }
        if (body.resetCounters) resetDrainCounters();
        const state = setDrain({
            enabled: body.enabled,
            message: body.message,
            retryAfterSec: body.retryAfterSec,
        });
        // Pas de comptage ici : le POST ARME/LEVE, il ne mesure pas. La jauge de
        // convergence se lit par GET (qui, lui, interroge les hooks).
        res.json({ ok: true, ...state, creationMethods: listCreationMethods() });
    });

    router.get("/api/rpc-queue", (_req: Request, res: Response) => {
        res.json({ ok: true, ...listGateStats() });
    });
    router.post("/api/rpc-queue", (req: Request, res: Response) => {
        const body = (req.body ?? {}) as
            { cap?: number; timeoutScale?: number; id?: number; reset?: boolean };
        const id = typeof body.id === "number" ? body.id : undefined;
        if (body.reset) resetStats(id);
        if (typeof body.cap === "number") setCap(body.cap, id);
        if (typeof body.timeoutScale === "number") setTimeoutScale(body.timeoutScale, id);
        res.json({ ok: true, ...listGateStats() });
    });

    // Reconcile host-side runner registry against the hook's in-memory runner
    // registry. Frida script reloads clear the hook registry; without this,
    // the front keeps showing dead runnerIds whose RPCs fail with
    // `runner N not found`. Called on front hard-reload.
    //
    // Geste MANUEL, d'ou l'asymetrie assumee avec `host/runner-reconcile.ts`
    // (le filet AUTOMATIQUE) : ici, PAS de session vivante => on purge TOUT,
    // parce que l'utilisateur declenche la reconciliation en connaissance de
    // cause et que le registre des hooks est alors vide par definition. Un timer
    // n'a pas ce droit : il pourrait tomber pendant une fenetre de reattache.
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
            // Horodatage PRIS AVANT la photo : un runner cree par un autre
            // appelant pendant l'aller-retour RPC est absent de `keep` sans etre
            // mort. `pruneRunners` ne touche donc qu'aux entrees anterieures.
            const snapshotAt = Date.now();
            const live = await rpcCall(sid, "listRunners", [], 5000) as Array<{
                runnerId: number;
            }>;
            const keep = new Set(live.map((r) => r.runnerId));
            const removed = await pruneRunners(keep, snapshotAt);
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
        // `removed` se lit AVANT la RPC : depuis #321 un `disposeRunner` reussi
        // purge deja le cache host depuis `rpcCall` (point de passage unique),
        // donc le `removeRunner` ci-dessous rendrait `false` sur le chemin
        // NOMINAL et la reponse mentirait. Ce qu'on rapporte, c'est « le host
        // avait-il une entree pour cet id », pas « qui l'a retiree ».
        const removed = hasRunner(id);
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
        // Filet : pas de session vivante, ou RPC en echec -> la purge de
        // `rpcCall` n'a pas eu lieu. Idempotent quand elle a eu lieu.
        await removeRunner(id);
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

    /** Sync per-version metadata (enums + i18n) for the active game build.
     *
     * Idempotent — only generates files that are missing under
     * `data/meta/<version>/`. The `summary` returned tells the caller what
     * was generated vs cached. Called automatically after a successful
     * inject (see /api/admin/inject), but exposed standalone for manual
     * refresh from the UI. */
    router.post("/api/meta/sync", async (_req: Request, res: Response) => {
        try {
            const sid = pickRunningSession();
            if (sid == null) { res.status(409).json({ error: "no running Frida session" }); return; }
            const result = await syncMetadata(sid);
            res.json(result);
        } catch (e) {
            res.status(500).json({ error: (e as Error).message });
        }
    });

    /** Refresh the static enum catalog from the live agent.
     *
     * Calls the agent's `dumpEnums()` RPC, persists the result to
     * `assets/public/enums.json`, and returns it. The front fetches that
     * file at boot via `/assets/enums.json` so it can resolve numeric event
     * tags (Effect_Id, …) to names without needing a live session. */
    router.post("/api/introspect/enums", async (_req: Request, res: Response) => {
        try {
            const sid = pickRunningSession();
            if (sid == null) { res.status(409).json({ error: "no running Frida session" }); return; }
            const result = await rpcCall(sid, "dumpEnums", [], 10000) as Record<
                string, { asm: string; ns: string; count: number; values: Record<string, string> }>;
            const out = path.join(process.cwd(), "assets", "public", "enums.json");
            await fs.mkdir(path.dirname(out), { recursive: true });
            await fs.writeFile(out, JSON.stringify(result, null, 2));
            const summary = Object.fromEntries(
                Object.entries(result).map(([k, v]) => [k, v.count]),
            );
            res.json({ ok: true, path: "enums.json", summary });
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

    /** Refresh the campaign catalog from the live agent.
     *
     * Calls `dumpCampaignCatalog`, stores the result under
     * `data/meta/<version>/campaign-catalog.json` so the front can fetch it
     * via `/meta/<version>/campaign-catalog.json` without needing a session.
     * Returns `{ version, bytes, path }`. */
    router.post("/api/campaigns/catalog/refresh", async (_req: Request, res: Response) => {
        try {
            const sid = pickRunningSession();
            if (sid == null) { res.status(409).json({ error: "no running Frida session" }); return; }
            // Explicit user-initiated refresh: allow the agent to fall back
            // to a heap scan (~10 s game freeze) if no live capture is
            // available. The push-based auto-refresh that runs on
            // builder_ready will normally satisfy the request without ever
            // needing the scan.
            const result = await syncCampaignCatalog(sid, true);
            res.json(result);
        } catch (e) {
            res.status(500).json({ error: (e as Error).message });
        }
    });

    /** Build a BattleConfiguration for one campaign node on demand.
     *
     * Body: `{ campaignType: number, campaignId: string, locationIndex: number }`.
     * Returns the JSON inline (no disk save). Promotion to the capture
     * archive happens later via /api/launch when the user actually
     * engages the setup — keeps "I clicked around to explore" out of
     * the archive list. */
    router.post("/api/campaigns/build", async (req: Request, res: Response) => {
        try {
            const sid = pickRunningSession();
            if (sid == null) { res.status(409).json({ error: "no running Frida session" }); return; }
            const { campaignType, campaignId, locationIndex } = req.body ?? {};
            if (typeof campaignType !== "number" || typeof campaignId !== "string"
                || typeof locationIndex !== "number") {
                res.status(400).json({
                    error: "body must be { campaignType:int, campaignId:string, locationIndex:int }",
                });
                return;
            }
            const r = await rpcCall(sid, "buildCampaignConfig",
                [{ campaignType, campaignId, locationIndex }], 120000) as {
                    campaignType: number; campaignId: string; locationIndex: number;
                    bytes: number; json: string;
                };

            res.json({
                id: `Campaign${campaignType}_${campaignId}_${locationIndex}`,
                campaignType, campaignId, locationIndex,
                bytes: r.bytes,
                json: r.json,           // inline — front parses directly
                source: "generated",
                generatedAt: new Date().toISOString(),
            });
        } catch (e) {
            res.status(500).json({ error: (e as Error).message });
        }
    });

    router.get("/api/mow/diag/runtime", async (_req: Request, res: Response) => {
        try {
            const sid = pickRunningSession();
            if (sid == null) { res.status(409).json({ error: "no running Frida session" }); return; }
            const r = await rpcCall(sid, "dumpLiveEventsRuntimeData",
                [], 60000) as { bytes: number; json: string };
            res.type("application/json").send(r.json);
        } catch (e) {
            res.status(500).json({ error: (e as Error).message });
        }
    });

    router.get("/api/mow/diag/live-event/:name", async (req: Request, res: Response) => {
        try {
            const sid = pickRunningSession();
            if (sid == null) { res.status(409).json({ error: "no running Frida session" }); return; }
            const r = await rpcCall(sid, "dumpLiveEventConfigByName",
                [{ eventName: req.params.name }], 30000) as
                { index: number; klassPtr: string; ptr: string;
                  bytes: number; json: string };
            res.type("application/json").send(JSON.stringify(r, null, 2));
        } catch (e) {
            res.status(500).json({ error: (e as Error).message });
        }
    });

    router.get("/api/mow/diag/live-events-config", async (_req: Request, res: Response) => {
        try {
            const sid = pickRunningSession();
            if (sid == null) { res.status(409).json({ error: "no running Frida session" }); return; }
            const r = await rpcCall(sid, "dumpLiveEventsConfig",
                [], 60000) as { bytes: number; json: string; instance: string };
            res.type("application/json").send(r.json);
        } catch (e) {
            res.status(500).json({ error: (e as Error).message });
        }
    });

    /** Diagnostic: dump the internal state of the live
     * IMachinesOfWarEventProgression as JSON. Used to investigate
     * whether future-event configs are already in memory. */
    router.get("/api/mow/diag/progression", async (_req: Request, res: Response) => {
        try {
            const sid = pickRunningSession();
            if (sid == null) { res.status(409).json({ error: "no running Frida session" }); return; }
            const r = await rpcCall(sid, "dumpMoWProgressionState",
                [], 30000) as { bytes: number; json: string };
            res.type("application/json").send(r.json);
        } catch (e) {
            res.status(500).json({ error: (e as Error).message });
        }
    });

    /** MachinesOfWar event builder — diagnostic. */
    router.get("/api/mow/builder-status", async (_req: Request, res: Response) => {
        try {
            const sid = pickRunningSession();
            if (sid == null) { res.json({ session: false, hasInstance: false }); return; }
            const r = await rpcCall(sid, "machinesOfWarBuilderStatus", [], 5000) as {
                hasInstance: boolean; instance: string | null;
            };
            res.json({ session: true, ...r });
        } catch (e) {
            res.status(500).json({ error: (e as Error).message });
        }
    });

    /** Refresh the MoW catalog from the live agent → data/meta/<v>/mow-catalog.json. */
    router.post("/api/mow/catalog/refresh", async (_req: Request, res: Response) => {
        try {
            const sid = pickRunningSession();
            if (sid == null) { res.status(409).json({ error: "no running Frida session" }); return; }
            const result = await syncMoWCatalog(sid);
            res.json(result);
        } catch (e) {
            res.status(500).json({ error: (e as Error).message });
        }
    });

    /** Build a BattleConfiguration for one MoW (tier, battle) combo.
     * Body: `{ tier: number, battle: number }`. Returns inline JSON. */
    router.post("/api/mow/build", async (req: Request, res: Response) => {
        try {
            const sid = pickRunningSession();
            if (sid == null) { res.status(409).json({ error: "no running Frida session" }); return; }
            const { tier, battle } = req.body ?? {};
            if (typeof tier !== "number" || typeof battle !== "number") {
                res.status(400).json({
                    error: "body must be { tier:int, battle:int }",
                });
                return;
            }
            const r = await rpcCall(sid, "buildMachinesOfWarConfig",
                [{ tier, battle }], 120000) as {
                    tier: number; battle: number; bytes: number; json: string;
                };
            res.json({
                id: `MoW_T${tier}_B${battle}`,
                tier, battle,
                bytes: r.bytes,
                json: r.json,
                source: "generated",
                generatedAt: new Date().toISOString(),
            });
        } catch (e) {
            res.status(500).json({ error: (e as Error).message });
        }
    });

    // ---------- AI trace toggle endpoints ----------
    // ai-trace is OFF by default to keep idle Tacticus runs cheap. The
    // front exposes three toggles (L1/L2/L3) that flip per-level capture
    // on demand. Status is cheap (just reads in-memory flags).

    router.get("/api/ai-trace/status", async (_req: Request, res: Response) => {
        try {
            // `store` = état des WRITERS côté host (répertoire ABSOLU où les traces
            // atterrissent, fichiers ouverts, lignes écrites). Il est mesurable SANS
            // session — d'où sa présence dans les deux branches. Jusqu'ici aucun
            // consommateur ne pouvait DEMANDER au host où il écrit : il l'INFÉRAIT
            // (#273-r(c)), et `aiTraceStoreStatus()` portait la réponse sans être
            // exposée par aucune route (#480-r7).
            const store = aiTraceStoreStatus();
            const sid = pickRunningSession();
            if (sid == null) { res.json({ session: false, store }); return; }
            const result = await rpcCall(sid, "aiTraceStatus", [], 5000);
            res.json({ session: true, store, ...result as Record<string, unknown> });
        } catch (e) {
            res.status(500).json({ error: (e as Error).message });
        }
    });

    router.post("/api/ai-trace/enable", async (req: Request, res: Response) => {
        try {
            const sid = pickRunningSession();
            if (sid == null) { res.status(409).json({ error: "no running session" }); return; }
            const { level } = req.body ?? {};
            if (typeof level !== "string") {
                res.status(400).json({ error: "body must be { level: string }" });
                return;
            }
            const result = await rpcCall(sid, "aiTraceEnable", [level], 5000);
            res.json(result);
        } catch (e) {
            res.status(500).json({ error: (e as Error).message });
        }
    });

    router.post("/api/ai-trace/disable", async (req: Request, res: Response) => {
        try {
            const sid = pickRunningSession();
            if (sid == null) { res.status(409).json({ error: "no running session" }); return; }
            const { level } = req.body ?? {};
            if (typeof level !== "string") {
                res.status(400).json({ error: "body must be { level: string }" });
                return;
            }
            const result = await rpcCall(sid, "aiTraceDisable", [level], 5000);
            res.json(result);
        } catch (e) {
            res.status(500).json({ error: (e as Error).message });
        }
    });

    // ---------- AI utility trace endpoints ----------
    // Phase 1 of the "tune AI movement scoring" workflow: capture every read
    // of UtilityConfig keys during AI decisions. Off by default — keep the
    // hook installation cheap when not investigating.

    router.post("/api/ai-utility-trace/enable", async (_req: Request, res: Response) => {
        try {
            const sid = pickRunningSession();
            if (sid == null) { res.status(409).json({ error: "no running session" }); return; }
            const result = await rpcCall(sid, "aiUtilityTraceEnable", [], 5000);
            res.json(result);
        } catch (e) {
            res.status(500).json({ error: (e as Error).message });
        }
    });

    router.post("/api/ai-utility-trace/disable", async (_req: Request, res: Response) => {
        try {
            const sid = pickRunningSession();
            if (sid == null) { res.status(409).json({ error: "no running session" }); return; }
            const result = await rpcCall(sid, "aiUtilityTraceDisable", [], 5000);
            res.json(result);
        } catch (e) {
            res.status(500).json({ error: (e as Error).message });
        }
    });

    router.post("/api/ai-utility-trace/clear", async (_req: Request, res: Response) => {
        try {
            const sid = pickRunningSession();
            if (sid == null) { res.status(409).json({ error: "no running session" }); return; }
            const result = await rpcCall(sid, "aiUtilityTraceClear", [], 5000);
            res.json(result);
        } catch (e) {
            res.status(500).json({ error: (e as Error).message });
        }
    });

    /** Dump the buffer. Query: ?since=<seq>&max=<n> */
    router.get("/api/ai-utility-trace/dump", async (req: Request, res: Response) => {
        try {
            const sid = pickRunningSession();
            if (sid == null) { res.status(409).json({ error: "no running session" }); return; }
            const since = req.query.since !== undefined
                ? Number(req.query.since) : 0;
            const max = req.query.max !== undefined
                ? Number(req.query.max) : 1000;
            const result = await rpcCall(sid, "aiUtilityTraceDump",
                [{ since, max }], 10000);
            res.json(result);
        } catch (e) {
            res.status(500).json({ error: (e as Error).message });
        }
    });

    /** Aggregated counters — sorted by hottest key. */
    router.get("/api/ai-utility-trace/counters", async (_req: Request, res: Response) => {
        try {
            const sid = pickRunningSession();
            if (sid == null) { res.status(409).json({ error: "no running session" }); return; }
            const result = await rpcCall(sid, "aiUtilityTraceCounters", [], 5000);
            res.json(result);
        } catch (e) {
            res.status(500).json({ error: (e as Error).message });
        }
    });

    /** Multi-capture call-stacks: every tryGetValueRef fire (during live AI
     * coroutine OR mirror replay) and every AiControl.ExecuteMovementFor
     * entry, deduped by top-frame RVA. Resolves RVAs via the IL2CPP method
     * table dump (DebugSymbol on Windows IL2CPP only resolves native exports). */
    router.get("/api/ai-utility-trace/callstacks", async (_req: Request, res: Response) => {
        try {
            const sid = pickRunningSession();
            if (sid == null) { res.status(409).json({ error: "no running session" }); return; }
            const result = await rpcCall(sid, "aiUtilityTraceCallstacks", [], 5000) as {
                max: number; count: number;
                callstacks: Array<{
                    origin: string; source: string; topRva: number;
                    frames: string[]; ts: number;
                }>;
            };
            const enriched = result.callstacks.map((c) => ({
                ...c,
                top: symbolicate(c.topRva),
                symbolicated: c.frames.map((f) => f.startsWith("rva:0x")
                    ? symbolicate(parseInt(f.slice(6), 16)) : f),
            }));
            res.json({ ...result, callstacks: enriched });
        } catch (e) { res.status(500).json({ error: (e as Error).message }); }
    });
    router.post("/api/ai-utility-trace/callstacks/reset", async (_req: Request, res: Response) => {
        try {
            const sid = pickRunningSession();
            if (sid == null) { res.status(409).json({ error: "no running session" }); return; }
            const result = await rpcCall(sid, "aiUtilityTraceCallstacksReset", [], 5000);
            res.json(result);
        } catch (e) { res.status(500).json({ error: (e as Error).message }); }
    });

    /** Enable the diag sampler (records untracked-dict classes seen during live AI). */
    router.post("/api/ai-utility-trace/diag-sampler/enable", async (req: Request, res: Response) => {
        try {
            const sid = pickRunningSession();
            if (sid == null) { res.status(409).json({ error: "no running session" }); return; }
            const sampleCap = typeof req.body?.sampleCap === "number"
                ? req.body.sampleCap : undefined;
            const result = await rpcCall(
                sid, "aiUtilityTraceDiagSamplerEnable",
                sampleCap !== undefined ? [{ sampleCap }] : [], 5000);
            res.json(result);
        } catch (e) {
            res.status(500).json({ error: (e as Error).message });
        }
    });
    router.post("/api/ai-utility-trace/diag-sampler/disable", async (_req: Request, res: Response) => {
        try {
            const sid = pickRunningSession();
            if (sid == null) { res.status(409).json({ error: "no running session" }); return; }
            const result = await rpcCall(sid, "aiUtilityTraceDiagSamplerDisable", [], 5000);
            res.json(result);
        } catch (e) {
            res.status(500).json({ error: (e as Error).message });
        }
    });
    router.get("/api/ai-utility-trace/diag-sampler/dump", async (_req: Request, res: Response) => {
        try {
            const sid = pickRunningSession();
            if (sid == null) { res.status(409).json({ error: "no running session" }); return; }
            const result = await rpcCall(sid, "aiUtilityTraceDiagSamplerDump", [], 5000);
            res.json(result);
        } catch (e) {
            res.status(500).json({ error: (e as Error).message });
        }
    });

    /** Patch a UtilityConfig key on a runtime instance.
     * Body: { configPtr: "0x...", key: "PerUnitWithAbilityInRange", value: -50 } */
    router.post("/api/ai-utility-trace/patch", async (req: Request, res: Response) => {
        try {
            const sid = pickRunningSession();
            if (sid == null) { res.status(409).json({ error: "no running session" }); return; }
            const { configPtr, key, value } = req.body ?? {};
            if (typeof configPtr !== "string" || typeof key !== "string"
                || typeof value !== "number") {
                res.status(400).json({
                    error: "expected { configPtr: string, key: string, value: number }",
                });
                return;
            }
            const result = await rpcCall(
                sid, "aiUtilityTracePatch", [{ configPtr, key, value }], 5000);
            res.json(result);
        } catch (e) {
            res.status(500).json({ error: (e as Error).message });
        }
    });

    // ---------- Mode-source diag ----------
    // Dump the auto-discovered list of GameModeSource classes (whose
    // LoadBattle is hooked). Lets us verify that newly added modes —
    // e.g. an Arena class not previously enumerated — are picked up
    // after a hooks rebuild.
    router.get("/api/mode-sources", async (_req: Request, res: Response) => {
        try {
            const sid = pickRunningSession();
            if (sid == null) { res.status(409).json({ error: "no running session" }); return; }
            const result = await rpcCall(sid, "dumpModeSources", [], 5000);
            res.json(result);
        } catch (e) {
            res.status(500).json({ error: (e as Error).message });
        }
    });
    router.get("/api/find-class/:needle", async (req: Request, res: Response) => {
        try {
            const sid = pickRunningSession();
            if (sid == null) { res.status(409).json({ error: "no running session" }); return; }
            const result = await rpcCall(sid, "findClassesNamed",
                [req.params.needle], 30000);
            res.json(result);
        } catch (e) {
            res.status(500).json({ error: (e as Error).message });
        }
    });

    // ---------- Overwatch fix endpoints ----------
    // AI-aware injection of overwatch threat into movement scoring. See
    // hooks/features/overwatch-fix.ts for the rationale.

    router.get("/api/overwatch-fix/status", async (_req: Request, res: Response) => {
        try {
            const sid = pickRunningSession();
            if (sid == null) { res.status(409).json({ error: "no running session" }); return; }
            const result = await rpcCall(sid, "overwatchFixStatus", [], 5000);
            res.json(result);
        } catch (e) {
            res.status(500).json({ error: (e as Error).message });
        }
    });

    router.post("/api/overwatch-fix/enable", async (_req: Request, res: Response) => {
        try {
            const sid = pickRunningSession();
            if (sid == null) { res.status(409).json({ error: "no running session" }); return; }
            const result = await rpcCall(sid, "overwatchFixEnable", [], 5000);
            res.json(result);
        } catch (e) {
            res.status(500).json({ error: (e as Error).message });
        }
    });

    router.post("/api/overwatch-fix/disable", async (_req: Request, res: Response) => {
        try {
            const sid = pickRunningSession();
            if (sid == null) { res.status(409).json({ error: "no running session" }); return; }
            const result = await rpcCall(sid, "overwatchFixDisable", [], 5000);
            res.json(result);
        } catch (e) {
            res.status(500).json({ error: (e as Error).message });
        }
    });

    router.post("/api/overwatch-fix/set-veto-enabled",
        async (req: Request, res: Response) => {
        try {
            const sid = pickRunningSession();
            if (sid == null) {
                res.status(409).json({ error: "no running session" }); return;
            }
            const enabled = req.body?.enabled === true
                || req.body?.enabled === "true";
            const result = await rpcCall(sid, "overwatchFixSetVetoEnabled",
                [{ enabled }], 5000);
            res.json(result);
        } catch (e) {
            res.status(500).json({ error: (e as Error).message });
        }
    });

    router.post("/api/overwatch-fix/reset-diag", async (_req: Request, res: Response) => {
        try {
            const sid = pickRunningSession();
            if (sid == null) { res.status(409).json({ error: "no running session" }); return; }
            const result = await rpcCall(sid, "overwatchFixResetDiag", [], 5000);
            res.json(result);
        } catch (e) {
            res.status(500).json({ error: (e as Error).message });
        }
    });

    // ---------- Bucket audit endpoints ----------
    router.get("/api/bucket-audit/status", async (_req: Request, res: Response) => {
        try {
            const sid = pickRunningSession();
            if (sid == null) { res.status(409).json({ error: "no running session" }); return; }
            const result = await rpcCall(sid, "bucketAuditStatus", [], 5000);
            res.json(result);
        } catch (e) { res.status(500).json({ error: (e as Error).message }); }
    });
    router.post("/api/bucket-audit/enable", async (_req: Request, res: Response) => {
        try {
            const sid = pickRunningSession();
            if (sid == null) { res.status(409).json({ error: "no running session" }); return; }
            const result = await rpcCall(sid, "bucketAuditEnable", [], 5000);
            res.json(result);
        } catch (e) { res.status(500).json({ error: (e as Error).message }); }
    });
    router.post("/api/bucket-audit/disable", async (_req: Request, res: Response) => {
        try {
            const sid = pickRunningSession();
            if (sid == null) { res.status(409).json({ error: "no running session" }); return; }
            const result = await rpcCall(sid, "bucketAuditDisable", [], 5000);
            res.json(result);
        } catch (e) { res.status(500).json({ error: (e as Error).message }); }
    });
    router.post("/api/bucket-audit/reset", async (_req: Request, res: Response) => {
        try {
            const sid = pickRunningSession();
            if (sid == null) { res.status(409).json({ error: "no running session" }); return; }
            const result = await rpcCall(sid, "bucketAuditReset", [], 5000);
            res.json(result);
        } catch (e) { res.status(500).json({ error: (e as Error).message }); }
    });
    router.get("/api/bucket-audit/added", async (req: Request, res: Response) => {
        try {
            const sid = pickRunningSession();
            if (sid == null) { res.status(409).json({ error: "no running session" }); return; }
            const max = req.query.max ? parseInt(String(req.query.max), 10) : undefined;
            const targetPtr = req.query.targetPtr as string | undefined;
            const result = await rpcCall(sid, "bucketAuditDumpAdded",
                [{ max, targetPtr }], 5000);
            res.json(result);
        } catch (e) { res.status(500).json({ error: (e as Error).message }); }
    });
    router.get("/api/bucket-audit/chosen", async (req: Request, res: Response) => {
        try {
            const sid = pickRunningSession();
            if (sid == null) { res.status(409).json({ error: "no running session" }); return; }
            const max = req.query.max ? parseInt(String(req.query.max), 10) : undefined;
            const result = await rpcCall(sid, "bucketAuditDumpChosen",
                [{ max }], 5000);
            res.json(result);
        } catch (e) { res.status(500).json({ error: (e as Error).message }); }
    });
    router.get("/api/bucket-audit/backtraces", async (_req: Request, res: Response) => {
        try {
            const sid = pickRunningSession();
            if (sid == null) { res.status(409).json({ error: "no running session" }); return; }
            const result = await rpcCall(sid, "bucketAuditBacktraces", [], 5000);
            res.json(result);
        } catch (e) { res.status(500).json({ error: (e as Error).message }); }
    });
    router.get("/api/bucket-audit/by-bucket", async (req: Request, res: Response) => {
        try {
            const sid = pickRunningSession();
            if (sid == null) { res.status(409).json({ error: "no running session" }); return; }
            const bucketPtr = req.query.bucketPtr as string;
            if (!bucketPtr) { res.status(400).json({ error: "bucketPtr required" }); return; }
            const result = await rpcCall(sid, "bucketAuditByBucket",
                [{ bucketPtr }], 5000);
            res.json(result);
        } catch (e) { res.status(500).json({ error: (e as Error).message }); }
    });

    router.post("/api/overwatch-fix/scan-state", async (req: Request, res: Response) => {
        try {
            const sid = pickRunningSession();
            if (sid == null) { res.status(409).json({ error: "no running session" }); return; }
            const result = await rpcCall(sid, "overwatchScanState",
                [req.body ?? {}], 30000);
            res.json(result);
        } catch (e) {
            res.status(500).json({ error: (e as Error).message });
        }
    });
    router.post("/api/overwatch-fix/auto-arm", async (req: Request, res: Response) => {
        try {
            const sid = pickRunningSession();
            if (sid == null) { res.status(409).json({ error: "no running session" }); return; }
            const result = await rpcCall(sid, "overwatchAutoArm",
                [req.body ?? {}], 30000);
            res.json(result);
        } catch (e) {
            res.status(500).json({ error: (e as Error).message });
        }
    });
    router.post("/api/overwatch-fix/clear-tracking", async (_req: Request, res: Response) => {
        try {
            const sid = pickRunningSession();
            if (sid == null) { res.status(409).json({ error: "no running session" }); return; }
            const result = await rpcCall(sid, "overwatchFixClearTracking", [], 5000);
            res.json(result);
        } catch (e) {
            res.status(500).json({ error: (e as Error).message });
        }
    });

    // ---------- Dispatch observe endpoints ----------
    // Hook BaseTriggeredAbility.ShouldTrigger to map upstream callers + retval
    // distribution by class. Default OFF — opt-in via /enable.
    router.get("/api/dispatch-observe/status", async (_req: Request, res: Response) => {
        try {
            const sid = pickRunningSession();
            if (sid == null) { res.status(409).json({ error: "no running session" }); return; }
            const result = await rpcCall(sid, "dispatchObserveStatus", [], 5000);
            res.json(result);
        } catch (e) { res.status(500).json({ error: (e as Error).message }); }
    });
    router.post("/api/dispatch-observe/enable", async (_req: Request, res: Response) => {
        try {
            const sid = pickRunningSession();
            if (sid == null) { res.status(409).json({ error: "no running session" }); return; }
            const result = await rpcCall(sid, "dispatchObserveEnable", [], 5000);
            res.json(result);
        } catch (e) { res.status(500).json({ error: (e as Error).message }); }
    });
    router.post("/api/dispatch-observe/disable", async (_req: Request, res: Response) => {
        try {
            const sid = pickRunningSession();
            if (sid == null) { res.status(409).json({ error: "no running session" }); return; }
            const result = await rpcCall(sid, "dispatchObserveDisable", [], 5000);
            res.json(result);
        } catch (e) { res.status(500).json({ error: (e as Error).message }); }
    });
    router.post("/api/dispatch-observe/reset", async (_req: Request, res: Response) => {
        try {
            const sid = pickRunningSession();
            if (sid == null) { res.status(409).json({ error: "no running session" }); return; }
            const result = await rpcCall(sid, "dispatchObserveReset", [], 5000);
            res.json(result);
        } catch (e) { res.status(500).json({ error: (e as Error).message }); }
    });

    // ---------- What-if trigger endpoints ----------
    // Capture AbilityEntities templates from BaseTriggeredAbility.ShouldTrigger
    // fires; clone + mutate + invoke EvaluateTriggerOperation.ExecuteSimulation
    // on the mirror runner for what-if scenarios.
    router.get("/api/whatif-trigger/status", async (_req: Request, res: Response) => {
        try {
            const sid = pickRunningSession();
            if (sid == null) { res.status(409).json({ error: "no running session" }); return; }
            const result = await rpcCall(sid, "whatifTriggerStatus", [], 5000);
            res.json(result);
        } catch (e) { res.status(500).json({ error: (e as Error).message }); }
    });
    router.post("/api/whatif-trigger/enable", async (_req: Request, res: Response) => {
        try {
            const sid = pickRunningSession();
            if (sid == null) { res.status(409).json({ error: "no running session" }); return; }
            const result = await rpcCall(sid, "whatifTriggerEnable", [], 5000);
            res.json(result);
        } catch (e) { res.status(500).json({ error: (e as Error).message }); }
    });
    router.post("/api/whatif-trigger/disable", async (_req: Request, res: Response) => {
        try {
            const sid = pickRunningSession();
            if (sid == null) { res.status(409).json({ error: "no running session" }); return; }
            const result = await rpcCall(sid, "whatifTriggerDisable", [], 5000);
            res.json(result);
        } catch (e) { res.status(500).json({ error: (e as Error).message }); }
    });
    router.post("/api/whatif-trigger/clear", async (_req: Request, res: Response) => {
        try {
            const sid = pickRunningSession();
            if (sid == null) { res.status(409).json({ error: "no running session" }); return; }
            const result = await rpcCall(sid, "whatifTriggerClearTemplates", [], 5000);
            res.json(result);
        } catch (e) { res.status(500).json({ error: (e as Error).message }); }
    });
    router.get("/api/whatif-trigger/template", async (req: Request, res: Response) => {
        try {
            const sid = pickRunningSession();
            if (sid == null) { res.status(409).json({ error: "no running session" }); return; }
            const cls = req.query.cls as string;
            if (!cls) { res.status(400).json({ error: "cls required" }); return; }
            const result = await rpcCall(sid, "whatifTriggerGetTemplate",
                [{ cls }], 5000);
            res.json(result);
        } catch (e) { res.status(500).json({ error: (e as Error).message }); }
    });
    router.post("/api/whatif-trigger/invoke", async (req: Request, res: Response) => {
        try {
            const sid = pickRunningSession();
            if (sid == null) { res.status(409).json({ error: "no running session" }); return; }
            const result = await rpcCall(sid, "whatifTriggerInvoke",
                [req.body ?? {}], 10000);
            res.json(result);
        } catch (e) { res.status(500).json({ error: (e as Error).message }); }
    });
    router.post("/api/whatif-trigger/set-trace", async (req: Request, res: Response) => {
        try {
            const sid = pickRunningSession();
            if (sid == null) { res.status(409).json({ error: "no running session" }); return; }
            const result = await rpcCall(sid, "whatifTriggerSetTraceFilter",
                [req.body ?? {}], 5000);
            res.json(result);
        } catch (e) { res.status(500).json({ error: (e as Error).message }); }
    });
    router.get("/api/whatif-trigger/trace", async (req: Request, res: Response) => {
        try {
            const sid = pickRunningSession();
            if (sid == null) { res.status(409).json({ error: "no running session" }); return; }
            const clear = req.query.clear === "1";
            const max = req.query.max ? parseInt(String(req.query.max), 10) : undefined;
            const result = await rpcCall(sid, "whatifTriggerGetTrace",
                [{ clear, max }], 5000);
            res.json(result);
        } catch (e) { res.status(500).json({ error: (e as Error).message }); }
    });

    // ---------- Sim mirror endpoints ----------
    // The mirror is an isolated IdunRunner that follows live message-by-
    // message via log replay + per-message PRNG sync. It exposes the
    // matchState to the front for rendering, and is foundational for future
    // AI variant exploration. See docs/plans for design rationale.

    /** Build a transient PREVIEW runner from a saved bundle (config +
     * messages). The runner is NOT registered as a build — it doesn't
     * appear in the runners panel and the recorder doesn't tag its applies.
     * Used solely so the front can render the saved matchstate on the
     * central board before the user commits via LOAD. */
    router.post("/api/sim/preview-build", async (req: Request, res: Response) => {
        try {
            const { configId } = req.body ?? {};
            if (typeof configId !== "string" || !configId) {
                res.status(400).json({ error: "configId required" });
                return;
            }
            const sid = pickRunningSession();
            if (sid == null) { res.status(409).json({ error: "no running Frida session" }); return; }
            const bundle = await getReplayBundle(configId);
            if (!bundle) { res.status(404).json({ error: "config not found" }); return; }
            const result = await rpcCall(sid, "simBuildPreview", [{
                configJson: bundle.configJson,
                messages: bundle.messages,
            }], 60000);
            res.json(result);
        } catch (e) {
            res.status(500).json({ error: (e as Error).message });
        }
    });

    /** Re-project the current preview's matchstate. */
    router.get("/api/sim/preview-state", async (_req: Request, res: Response) => {
        try {
            const sid = pickRunningSession();
            if (sid == null) { res.status(409).json({ error: "no running Frida session" }); return; }
            const result = await rpcCall(sid, "simGetPreviewState", [], 5000);
            res.json(result);
        } catch (e) {
            res.status(500).json({ error: (e as Error).message });
        }
    });

    /** Drop the preview slot. */
    router.post("/api/sim/preview-dispose", async (_req: Request, res: Response) => {
        try {
            const sid = pickRunningSession();
            if (sid == null) { res.status(409).json({ error: "no running Frida session" }); return; }
            const result = await rpcCall(sid, "simDisposePreview", [], 5000);
            res.json(result);
        } catch (e) {
            res.status(500).json({ error: (e as Error).message });
        }
    });

    /** LOAD a saved bundle into a fresh BUILD runner (single-build policy
     * disposes any prior build + preview). Recorder watches the new build
     * so subsequent applies (manual end-turn, auto-play, mirror catchUp)
     * are captured normally. Falls back to legacy initRunner+startBattle
     * for old config-only saves with no message bundle. */
    router.post("/api/sim/load-from-saved", async (req: Request, res: Response) => {
        try {
            const { configId } = req.body ?? {};
            if (typeof configId !== "string" || !configId) {
                res.status(400).json({ error: "configId required" });
                return;
            }
            const sid = pickRunningSession();
            if (sid == null) { res.status(409).json({ error: "no running Frida session" }); return; }
            const bundle = await getReplayBundle(configId);
            if (!bundle) { res.status(404).json({ error: "config not found" }); return; }
            if (bundle.messages.length > 0) {
                // Bundle path — replay every saved message.
                const r = await rpcCall(sid, "loadFromSavedBundle", [{
                    configJson: bundle.configJson,
                    messages: bundle.messages,
                }], 120000) as { ok: boolean; runnerId: number; seed: number };
                registerRunner(r.runnerId, sid, configId);
                res.json(r);
            } else {
                // Legacy path — config-only save (pre-bundle): build runner
                // + start match. The matchstate will reflect the
                // PredefinedUnits but won't include any post-deployment
                // gameplay messages.
                const init = await rpcCall(sid, "initRunner",
                    [{ configJson: bundle.configJson }], 30000) as
                    { runnerId: number; seed: number };
                registerRunner(init.runnerId, sid, configId);
                await rpcCall(sid, "startBattle",
                    [{ runnerId: init.runnerId }], 30000);
                res.json({ ok: true, runnerId: init.runnerId, seed: init.seed,
                    legacy: true });
            }
        } catch (e) {
            res.status(500).json({ error: (e as Error).message });
        }
    });

    /** Build-or-catchup the mirror. Body: { source?: "live"|"build", runnerId? }.
     * Defaults to source="live" for back-compat with the existing button. */
    router.post("/api/sim/mirror", async (req: Request, res: Response) => {
        try {
            const sid = pickRunningSession();
            if (sid == null) { res.status(409).json({ error: "no running Frida session" }); return; }
            const body = (req.body && typeof req.body === "object")
                ? { source: req.body.source, runnerId: req.body.runnerId }
                : {};
            const result = await rpcCall(sid, "simMirror", [body], 60000);
            res.json(result);
        } catch (e) {
            res.status(500).json({ error: (e as Error).message });
        }
    });

    /** Read the mirror's current matchState + a live↔mirror compare. */
    router.get("/api/sim/state", async (_req: Request, res: Response) => {
        try {
            const sid = pickRunningSession();
            if (sid == null) { res.status(409).json({ error: "no running Frida session" }); return; }
            const result = await rpcCall(sid, "simGetState", [], 10000);
            res.json(result);
        } catch (e) {
            res.status(500).json({ error: (e as Error).message });
        }
    });

    /** Full replay-able battle dump: config + seed + every captured message
     * (boot preamble + live + AI sub-messages) Newtonsoft-serialized with
     * per-message PRNG snapshots. The bundle is sufficient to reconstruct
     * the current state offline via buildRunner(cfg, seed) + per-message
     * deserialize+restoreMt+Apply. Returned as a downloadable JSON file. */
    router.get("/api/sim/dump-replay", async (_req: Request, res: Response) => {
        try {
            const sid = pickRunningSession();
            if (sid == null) { res.status(409).json({ error: "no running Frida session" }); return; }
            const r = await rpcCall(sid, "simDumpReplay", [], 60000) as {
                ok: boolean; error?: string;
                capturedAt?: number; runnerPtr?: string;
                seed?: number | null;
                config?: { bytes: number; json: string };
                messages?: unknown[];
                stats?: Record<string, number>;
            };
            if (!r.ok) {
                res.status(404).json({ error: r.error ?? "unavailable" });
                return;
            }
            const filename = "replay-"
                + new Date().toISOString().replace(/[:.]/g, "-")
                + "-msgs" + (r.messages?.length ?? 0) + ".json";
            res.setHeader("Content-Disposition",
                `attachment; filename="${filename}"`);
            res.type("application/json").send(JSON.stringify(r));
        } catch (e) {
            res.status(500).json({ error: (e as Error).message });
        }
    });

    /** User-driven save of the live runner's BattleConfiguration to the
     * configs store. Live-only; build runners can't be saved (they came
     * from a stored config). Returns { ok, id } on success. */
    router.post("/api/sim/save-live-config", async (_req: Request, res: Response) => {
        try {
            const sid = pickRunningSession();
            if (sid == null) { res.status(409).json({ error: "no running Frida session" }); return; }
            const result = await rpcCall(sid, "simSaveLiveConfig", [], 30000);
            res.json(result);
        } catch (e) {
            res.status(500).json({ error: (e as Error).message });
        }
    });

    /** Live runner's BattleConfiguration as JSON — front uses it to load
     * the right board PNG + hex layout for the active battle. */
    router.get("/api/sim/battle-config", async (_req: Request, res: Response) => {
        try {
            const sid = pickRunningSession();
            if (sid == null) { res.status(409).json({ error: "no running Frida session" }); return; }
            const r = await rpcCall(sid, "simGetBattleConfig", [], 30000) as
                { ok: boolean; bytes?: number; json?: string; error?: string };
            if (!r.ok || !r.json) {
                res.status(404).json({ error: r.error ?? "unavailable" });
                return;
            }
            res.type("application/json").send(r.json);
        } catch (e) {
            res.status(500).json({ error: (e as Error).message });
        }
    });

    /** Per-entry log dump — diagnostic for live↔mirror divergence. */
    router.get("/api/sim/dump-log", async (_req: Request, res: Response) => {
        try {
            const sid = pickRunningSession();
            if (sid == null) { res.status(409).json({ error: "no running Frida session" }); return; }
            const result = await rpcCall(sid, "simDumpLog", [], 10000);
            res.json(result);
        } catch (e) {
            res.status(500).json({ error: (e as Error).message });
        }
    });

    /** Lightweight status — used by the front to enable/disable buttons. */
    router.get("/api/sim/status", async (_req: Request, res: Response) => {
        try {
            const sid = pickRunningSession();
            if (sid == null) {
                res.json({
                    built: false, canMirror: false,
                    blockReason: "no running Frida session",
                });
                return;
            }
            const result = await rpcCall(sid, "simStatus", [], 5000);
            res.json(result);
        } catch (e) {
            res.status(500).json({ error: (e as Error).message });
        }
    });

    /** Dispatch one EndTurnMessage on the current mirror's build source —
     * passes the turn to the next team without auto-playing. Refused on a
     * live mirror. */
    router.post("/api/sim/end-turn", async (_req: Request, res: Response) => {
        try {
            const sid = pickRunningSession();
            if (sid == null) { res.status(409).json({ error: "no running Frida session" }); return; }
            const result = await rpcCall(sid, "simEndTurn", [], 10000);
            res.json(result);
        } catch (e) {
            res.status(500).json({ error: (e as Error).message });
        }
    });

    /** One auto-play step for a build-source mirror — dispatches a single
     * CheatRunAIMessage on the build runner (active team plays). Front calls
     * this in a loop until {advanced:false}. */
    router.post("/api/sim/auto-play-step", async (_req: Request, res: Response) => {
        try {
            const sid = pickRunningSession();
            if (sid == null) { res.status(409).json({ error: "no running Frida session" }); return; }
            const result = await rpcCall(sid, "simAutoPlayStep", [], 30000);
            res.json(result);
        } catch (e) {
            res.status(500).json({ error: (e as Error).message });
        }
    });

    /** Drop the mirror — next mirror call rebuilds from scratch. */
    router.post("/api/sim/reset", async (_req: Request, res: Response) => {
        try {
            const sid = pickRunningSession();
            if (sid == null) { res.status(409).json({ error: "no running Frida session" }); return; }
            const result = await rpcCall(sid, "simReset", [], 5000);
            res.json(result);
        } catch (e) {
            res.status(500).json({ error: (e as Error).message });
        }
    });

    /** "AI plays on mirror, then commits to live" — single-shot turn driver.
     * No body. Returns Phase1/Phase2 timings + per-msg event divergences. */
    router.post("/api/sim/run-ai-turn", async (_req: Request, res: Response) => {
        try {
            const sid = pickRunningSession();
            if (sid == null) { res.status(409).json({ error: "no running Frida session" }); return; }
            // Generous timeout: a full AI turn can be 10-30 messages; each
            // commit invokes runner.Apply on live (~10-30ms) and we may also
            // hit slow heap allocations during Phase 1 dispatch.
            const result = await rpcCall(sid, "simRunAiTurn", [], 60000);
            res.json(result);
        } catch (e) {
            res.status(500).json({ error: (e as Error).message });
        }
    });

    /** Rebuild + replay log[0..logIdx) — primitive de rollback. */
    router.post("/api/sim/rebuild-to", async (req: Request, res: Response) => {
        try {
            const sid = pickRunningSession();
            if (sid == null) { res.status(409).json({ error: "no running Frida session" }); return; }
            const { logIdx } = req.body ?? {};
            if (typeof logIdx !== "number") {
                res.status(400).json({ error: "body must be { logIdx: number }" });
                return;
            }
            const result = await rpcCall(sid, "simRebuildAndCatchUpTo",
                [{ logIdx }], 60000);
            res.json(result);
        } catch (e) {
            res.status(500).json({ error: (e as Error).message });
        }
    });

    /** Diagnostic — does the agent have a live CampaignGameModeSource?
     * The build/catalog endpoints fail with a clear message when this is
     * false (user needs to open the campaign view in-game first). */
    router.get("/api/campaigns/builder-status", async (_req: Request, res: Response) => {
        try {
            const sid = pickRunningSession();
            if (sid == null) { res.json({ session: false, hasInstance: false }); return; }
            const r = await rpcCall(sid, "campaignBuilderStatus", [], 5000) as {
                hasInstance: boolean; instance: string | null;
            };
            res.json({ session: true, ...r });
        } catch (e) {
            res.status(500).json({ error: (e as Error).message });
        }
    });

    // Liveness-aware: skips zombies (status "running" but script destroyed).
    // Delegates to sessions.ts because script liveness isn't visible here
    // (listSessions() returns sanitized views without fridaScript).
    function pickRunningSession(): number | null {
        return pickLiveSessionId();
    }

    router.post("/api/_dev/shutdown", async (_req: Request, res: Response) => {
        try { await stopAllPreservingState(); } catch { /* ignore */ }
        res.json({ ok: true });
        setTimeout(() => process.exit(0), 300);
    });

    return router;
}

/** Map common Frida error strings to user-friendly hints. */
function humanizeFridaError(msg: string): string {
    if (/unable to find process with pid/i.test(msg)) {
        return `${msg} — the game closed between selection and attach. Relaunch Tacticus and retry.`;
    }
    if (/unable to (inject|access) /i.test(msg)) {
        return `${msg} — Frida couldn't inject. Try running the host as Administrator.`;
    }
    if (/script\.load.*timeout/i.test(msg)) {
        return `${msg} — the IL2CPP runtime didn't respond in time; the game may still be loading.`;
    }
    return msg;
}
