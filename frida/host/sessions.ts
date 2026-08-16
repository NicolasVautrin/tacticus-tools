// Frida session management: attach, load scripts, RPC, message handling,
// graceful cleanup, on-disk persistence so sessions survive a host reboot.
//
// Persistence pattern (intent-only): we record { pid, exePath, bundlePath }
// per active session in `data/sessions.json`. On boot, restoreSessions()
// re-attaches by PID (or, if the PID is dead, rediscovers by exePath via
// admin.findTacticusCandidates) and re-injects the bundle. The agent itself
// does NOT survive — it is re-installed at every host start.
import frida from "frida";
import {
    promises as fsp, existsSync, mkdirSync, readFileSync, writeFileSync,
} from "fs";
import path from "path";
import { openLog, appendLog, closeLog } from "./logger.js";
import { cleanupSession, publish } from "./ws.js";
import { routeMessage } from "./router-messages.js";
import { pruneRunnersBySession, removeRunner } from "./battle-store.js";
import {
    acquireSlot, releaseSlot, noteDispatch, noteSettle, concurrencyFactor,
} from "./rpc-queue.js";
import { assertCreationAllowed, isCreationMethod } from "./drain.js";
import {
    ensureWarmForCreation, forgetSession as forgetWarmState,
    noteRpcResult as noteWarmupResult, WARMUP_METHOD,
} from "./warm-gate.js";

export interface RunSession {
    id: number;
    pid: number;
    mode: "attach" | "spawn";
    status: "running" | "stopped" | "error";
    startedAt: string;
    endedAt?: string;
    errorMessage?: string;
    logDir?: string;
    exePath?: string;
    bundlePath?: string;
    fridaSession?: frida.Session;
    fridaScript?: frida.Script;
}

let nextSessionId = 1;
const sessions = new Map<number, RunSession>();

const STATE_PATH = path.resolve(process.cwd(), "data", "sessions.json");
let suspendPersist = false;

export function listSessions(): RunSession[] {
    return [...sessions.values()].map(sanitize);
}

export function getSession(id: number): RunSession | undefined {
    const s = sessions.get(id);
    return s ? sanitize(s) : undefined;
}

/** Most-recently-started session that is running AND whose script is still
 * alive. Callers outside this module can't check script liveness themselves
 * (sanitize() strips fridaScript), so they must go through here rather than
 * filtering listSessions() on status — otherwise a zombie (status "running",
 * script destroyed, signal not yet propagated) gets advertised as active. */
export function pickLiveSessionId(): number | null {
    const live = [...sessions.values()].filter(
        (s) => s.status === "running" && !!s.fridaScript && !isScriptDestroyed(s.fridaScript),
    );
    if (live.length === 0) return null;
    return live[live.length - 1].id;
}

export async function listProcesses(): Promise<Array<{
    pid: number; name: string;
}>> {
    const device = await getDevice();
    const processes = await device.enumerateProcesses();
    return processes.map((p) => ({ pid: p.pid, name: p.name }));
}

export interface RunScriptOpts {
    mode: "attach" | "spawn";
    pid?: number;
    target?: string;
    source: string;
    logDir?: string;
    exePath?: string;
    bundlePath?: string;
}

export async function runScript(opts: RunScriptOpts): Promise<RunSession> {
    // Stop all existing sessions to avoid orphan hooks on the same process.
    await stopAll();

    const device = await getDevice();

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
        pid,
        mode: opts.mode,
        status: "running",
        startedAt: new Date().toISOString(),
        logDir: opts.logDir,
        exePath: opts.exePath,
        bundlePath: opts.bundlePath,
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

    // Mark the session dead exactly once, whichever teardown signal fires
    // first. The SESSION emits `detached` (process gone / explicit detach);
    // the SCRIPT emits `destroyed` (unload, runtime teardown, or the agent
    // dying without the whole session detaching). Historically only
    // `detached` was wired, so a script that died on its own left a zombie
    // session stuck at status "running" — every subsequent RPC then threw a
    // raw "Script is destroyed" from Frida. Wiring `destroyed` too closes
    // that gap; the `finalized` guard keeps side-effects single-shot when
    // both signals fire (they do during a normal stopSession unload+detach).
    let finalized = false;
    const finalize = (reason: string): void => {
        if (finalized) return;
        finalized = true;
        if (session.status === "running") session.status = "stopped";
        session.endedAt = new Date().toISOString();
        closeLog(sessionId);
        // Runners are dead once the script is gone, so their host metadata
        // must disappear too (same rationale as stopSession).
        pruneRunnersBySession(sessionId).catch((e) => {
            console.log(`[sessions] prune (${reason}) failed for ${sessionId}: ${e.message}`);
        });
        // Une session morte n'est plus chaude (#285-r1) : son script est parti,
        // donc les caches Frida-side qu'un warmup avait remplis aussi.
        forgetWarmState(sessionId);
        persist();
    };
    fridaSession.detached.connect(() => finalize("detached"));
    fridaScript.destroyed.connect(() => finalize("script-destroyed"));

    // Wait for the agent to finish its top-level init (lots of
    // findClass + Interceptor.attach) before returning, so the first
    // RPC after inject doesn't sit pending during boot. The agent
    // signals completion via send({t:"agent_ready"}) at the very end
    // of main.ts. Falls back to a safety timeout in case an
    // unrelated send precedes ours and the listener races.
    // The fallback is generous (the bundle keeps growing — ~890 KB / dozens of
    // Interceptor.attach at boot — and can take >15s to emit agent_ready); a
    // premature fallback marks the session "ready" before the agent truly is,
    // making the first RPCs race the boot. Prefer waiting for the real signal.
    const AGENT_READY_TIMEOUT_MS = 45000;
    const readyPromise = new Promise<void>((resolve) => {
        const onReady = (msg: frida.Message): void => {
            if (msg.type === "send" &&
                (msg as frida.SendMessage).payload?.t === "agent_ready") {
                fridaScript.message.disconnect(onReady);
                resolve();
            }
        };
        fridaScript.message.connect(onReady);
    });
    await fridaScript.load();
    await Promise.race([
        readyPromise,
        new Promise<void>((resolve) => setTimeout(resolve, AGENT_READY_TIMEOUT_MS)),
    ]);

    // Liveness gate: re-attaching to a PID left wedged by a prior agent can
    // load the script only for the runtime to tear it straight back down.
    // Without this check runScript would still hand back a session marked
    // "running" — a phantom that fails every RPC with "Script is destroyed".
    // `isDestroyed` is the one unambiguous failure signal at this point: a
    // mere ready-timeout is expected (the race above is a deliberate
    // fallback), so we must NOT fail on that alone.
    if (isScriptDestroyed(fridaScript)) {
        session.status = "error";
        session.errorMessage =
            "script was destroyed right after load — the target PID is likely " +
            "wedged; relaunch Tacticus, then reinject";
        session.endedAt = new Date().toISOString();
        closeLog(sessionId);
        persist();
        throw new Error(`inject failed on pid ${pid}: ${session.errorMessage}`);
    }

    if (opts.mode === "spawn") {
        await device.resume(pid);
    }

    persist();
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

    // CHRONOMÉTRAGE DES TROIS ÉTAGES DU STOP (#10016-r1).
    //
    // Mesuré le 2026-08-16 : un `POST /api/admin/inject` a mis 400 s puis échoué, et le
    // suivant — stop désormais terminé — a rendu la main en 9 s. Tout le coût est donc
    // dans le stop, jamais dans l'attach. Mais PERSONNE NE SAIT LEQUEL des trois appels
    // le porte : le handshake est plafonné à 2 s, tandis qu'`unload()` et `detach()`
    // n'ont NI mesure NI timeout. Le seul témoin disponible était le temps de bout en
    // bout de la requête HTTP, qui mélange stop + attach — donc inutilisable pour
    // décider quoi que ce soit.
    //
    // ⚠ TRI-ÉTAT, et il n'est pas décoratif : `-1` = l'appel N'A PAS TERMINÉ (exception,
    // ou étage jamais atteint parce que le précédent a levé). Un `0` s'y lirait comme
    // « instantané », c'est-à-dire comme une MESURE — exactement le rabattement qui
    // ferait innocenter l'étage fautif.
    const chrono = { handshakeMs: -1, unloadMs: -1, detachMs: -1 };
    const t0 = Date.now();

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
            chrono.handshakeMs = Date.now() - t0;
            const tUnload = Date.now();
            await session.fridaScript.unload();
            chrono.unloadMs = Date.now() - tUnload;
        }
        if (session.fridaSession) {
            const tDetach = Date.now();
            await session.fridaSession.detach();
            chrono.detachMs = Date.now() - tDetach;
        }
    } catch {
        // Already detached
    }

    // Émis MÊME quand un étage a levé : c'est précisément le cas où l'on veut savoir
    // lequel, et les `-1` le disent. Le total de bout en bout est repris à côté des
    // trois étages pour que la somme manquante saute aux yeux.
    session.status = "stopped";
    session.endedAt = new Date().toISOString();

    // ⚠ LIBÉRER LES OBJETS FRIDA — la Map `sessions` n'est JAMAIS purgée (`sessions.set`
    // ligne 119, aucun `sessions.delete` dans le fichier), donc chaque session stoppée
    // gardait son `frida.Session` ET son `frida.Script` référencés pour toute la vie du
    // process host. Ce ne sont pas de simples objets JS : ce sont des poignées vers des
    // ressources natives du binding frida-node.
    //
    // COÛT MESURÉ (#10016-r1, 2026-08-16). Sur un host lancé le 2026-08-07 — neuf jours
    // et une longue série de sessions — un stop mettait des MINUTES et faisait échouer
    // l'inject qui le suivait (400 s, puis `session: null`). Host redémarré, MÊME jeu
    // (PID 80832 inchangé, donc ni son tas managé ni ses hooks ne sont en cause) :
    //     [sessions] stop 1 -- handshake=2ms unload=24ms detach=2ms (total=28ms)
    // La dégradation suit donc le NOMBRE de sessions accumulées dans le process node,
    // pas la durée d'une session — ce qui explique que de très longues sessions
    // passaient sans problème auparavant.
    //
    // On garde l'ENTRÉE (métadonnées d'historique : status, dates, pid — `sanitize` les
    // publie et les retire déjà de la sortie) et on lâche les POIGNÉES.
    session.fridaScript = undefined;
    session.fridaSession = undefined;

    // ⚠ COMPTÉ APRÈS LA LIBÉRATION, sinon l'observable s'accuse LUI-MÊME : le signal
    // `fridaScript.destroyed` de l'unload passe la session à `stopped` via `finalize()`
    // AVANT qu'on arrive ici, donc elle entrait dans son propre filtre et le compteur
    // affichait 1 en permanence. Mesuré sur trois stops enchaînés : `en memoire` montait
    // 1 → 2 → 3 tandis que `RETENUES` restait figé à 1 — c'est ce plafond qui prouvait
    // que la libération marchait, et c'est exactement ce qu'un cliquet à 0 doit dire
    // sans qu'on ait à l'interpréter.
    //
    // `retenues` DOIT rester à 0 : c'est le cliquet de la libération ci-dessous. S'il
    // remonte, une voie de stop a été ajoutée sans lâcher les poignées, et la
    // dégradation reviendra — silencieusement, sur plusieurs jours. La RSS du host est
    // imprimée à côté parce que c'est l'autre face de la même fuite.
    const retenues = [...sessions.values()]
        .filter((s) => s.status !== "running" && (s.fridaScript || s.fridaSession)).length;
    console.log(
        `[sessions] stop ${id} — handshake=${chrono.handshakeMs}ms `
        + `unload=${chrono.unloadMs}ms detach=${chrono.detachMs}ms `
        + `(total=${Date.now() - t0}ms ; -1 = n'a pas termine) `
        + `— sessions en memoire=${sessions.size} dont RETENUES=${retenues} `
        + `(doit valoir 0) ; rss=${Math.round(process.memoryUsage().rss / 1048576)}Mo`,
    );
    try {
        appendLog(id, { t: "stop_timings", ...chrono, totalMs: Date.now() - t0 });
    } catch { /* journal non ouvert (aucun logDir a l'inject) — le console.log suffit */ }

    closeLog(id);

    // Runners live inside the Frida script's heap — stopping the session
    // kills them. Prune host-side metadata so stale runnerIds don't leak
    // to the UI as "existing" runners.
    try {
        const removed = await pruneRunnersBySession(id);
        if (removed.length > 0) {
            console.log(`[sessions] pruned runners for session ${id}: ${removed.join(", ")}`);
        }
    } catch (e) {
        console.log(`[sessions] prune failed for session ${id}: ${(e as Error).message}`);
    }

    // Le script est unloadé : plus aucun `publish` ne viendra pour cet id. Sans cet appel,
    // le ring WS (jusqu'à RING_SIZE = 10 000 événements) et le Set d'abonnés restaient en
    // mémoire pour la durée de vie du host, une session stoppée après l'autre —
    // `cleanupSession` existait pour ça et n'avait AUCUN appelant (#480-r7).
    // Rien d'observable n'est perdu : le front ne se réabonne qu'à une session
    // `status === "running"` (`public/src/runners.js`), donc ce ring n'était plus relu.
    cleanupSession(id);

    persist();
}

export async function stopAll(): Promise<void> {
    for (const [id, session] of sessions) {
        if (session.status === "running") {
            await stopSession(id);
        }
    }
}

/** Used by graceful shutdown: detach without rewriting state, so the next
 * boot's restore can replay what was live. */
export async function stopAllPreservingState(): Promise<void> {
    suspendPersist = true;
    try { await stopAll(); }
    finally { suspendPersist = false; }
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
    // Porte du DRAIN (#285) — AVANT toute autre verification. Refuse les seules
    // methodes qui CREENT un runner ; tout le pilotage/monitoring des runners
    // deja en place passe intact, `disposeRunner` compris (sans lui le drain ne
    // convergerait jamais vers zero). Pose ICI et non dans la route HTTP parce
    // que `/api/launch` et la route de replay sim appellent `rpcCall` en
    // INTERNE : une porte au niveau des routes les laisserait passer.
    assertCreationAllowed(method);
    const session = requireLiveSession(id);

    // Porte de WARMUP (#285-r1) — APRES le drain, et pour les memes methodes.
    // L'ordre importe : pendant une fenetre de maintenance on veut refuser la
    // creation TOUT DE SUITE, pas payer 12 s de warmup avant de la refuser.
    // La porte WARME au lieu de refuser (cf. l'en-tete de warm-gate.ts) ; elle
    // ne leve que si le warmup lui-meme echoue.
    if (isCreationMethod(method)) {
        await ensureWarmForCreation(id, method,
            (sid) => rpcCall(sid, WARMUP_METHOD, [{ force: true }], 240000));
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

    // Concurrency gate (cap=∞ by default → pure pass-through + telemetry). The
    // slot is acquired BEFORE the timeout clock starts, so a caller queued
    // behind a finite cap never times out while merely waiting for a slot
    // (timeout-at-dispatch). See host/rpc-queue.ts.
    const queuedMs = await acquireSlot(id);
    noteDispatch(id, queuedMs);
    // Timeout scales with parallelism: the single Frida pump runs RPCs one at a
    // time, so under C concurrent callers a call may serialize behind ~C others
    // → effective = base × concurrencyFactor (cap when set, else in-flight).
    // Keeps a per-call base (single-agent worst case) correct as N grows, and
    // avoids false timeouts on MUTATING RPCs (zombie/corruption) under load.
    const factor = concurrencyFactor(id);
    const effTimeout = timeout * factor;
    const dispatchedAt = Date.now();
    let timer: ReturnType<typeof setTimeout> | undefined;
    let timedOut = false;
    try {
        const call = fn.apply(null, callArgs);
        const timeoutP = new Promise<never>((_, reject) => {
            timer = setTimeout(() => {
                timedOut = true;
                reject(new Error(
                    `RPC timeout after ${effTimeout}ms (base ${timeout}×${factor})`));
            }, effTimeout);
        });
        const out = await Promise.race([call, timeoutP]);
        noteRunnerDeath(method, callArgs);
        // Symetrique de `noteRunnerDeath` : le host apprend qu'une session est
        // CHAUDE en relisant le warmup qui vient de reussir, quelle que soit la
        // route qui l'a lance (#285-r1).
        noteWarmupResult(id, method, out);
        return out;
    } finally {
        if (timer) clearTimeout(timer);
        noteSettle(id, Date.now() - dispatchedAt, timedOut);
        releaseSlot(id);
    }
}

/**
 * SYMETRIQUE de la porte de drain (#321) : le host apprend la MORT d'un runner
 * en relisant la RPC qui vient de reussir.
 *
 * Pose ICI, dans `rpcCall`, pour la MEME raison que `assertCreationAllowed` :
 * c'est le point de passage unique. Les agents disposent par
 * `POST /api/scripts/:id/rpc` (passe-plat generique), le front par
 * `DELETE /api/runners/:id`, et certaines routes appellent `rpcCall` en interne
 * — une regle posee au niveau des routes en manquerait la majorite. C'est
 * exactement ce qui manquait : la CREATION s'inferait toute seule (premier
 * `battle_event`), la MORT n'etait cablee nulle part sur ce chemin, et le cache
 * host derivait sans borne (mesure : 318 entrees pour 0 runner vivant, ids
 * 1..318 sans aucun trou). Cf. l'en-tete de `battle-store.ts`.
 *
 * On purge que la RPC ait rendu `{removed:true}` ou `{removed:false}` : un
 * `false` signifie que les hooks n'avaient DEJA plus ce runner, donc l'entree
 * host est stale a plus forte raison. Best-effort et silencieux en cas d'echec :
 * une comptabilite de presentation ne doit jamais faire echouer une RPC reussie.
 */
function noteRunnerDeath(method: string, callArgs: unknown[]): void {
    if (method !== "disposeRunner") return;
    const a0 = callArgs[0];
    const rid = a0 && typeof a0 === "object"
        ? (a0 as { runnerId?: unknown }).runnerId
        : a0;
    if (typeof rid !== "number" || !Number.isFinite(rid)) return;
    removeRunner(rid).catch((e) => {
        console.log(`[sessions] host registry purge failed for runner ${rid}: ${(e as Error).message}`);
    });
}

export function postMessage(id: number, message: unknown): void {
    const session = requireLiveSession(id);
    session.fridaScript!.post(message as frida.Message);
}

// ---------- Persistence ----------

interface PersistedSession {
    pid: number;
    exePath?: string;
    bundlePath: string;
}

interface StateFile {
    version: number;
    savedAt: string;
    sessions: PersistedSession[];
}

function persist(): void {
    if (suspendPersist) return;
    try {
        const persistable: PersistedSession[] = [...sessions.values()]
            .filter((s) => s.status === "running" && s.bundlePath)
            .map((s) => ({
                pid: s.pid,
                exePath: s.exePath,
                bundlePath: s.bundlePath as string,
            }));
        const state: StateFile = {
            version: 1,
            savedAt: new Date().toISOString(),
            sessions: persistable,
        };
        const dir = path.dirname(STATE_PATH);
        if (!existsSync(dir)) {
            // frida/data exists in a normal checkout but not in a fresh
            // clone — mkdir on the rare miss instead of crashing persist().
            mkdirSync(dir, { recursive: true });
        }
        writeFileSync(STATE_PATH, JSON.stringify(state, null, 2));
    } catch (e) {
        console.log(`[sessions] persist failed: ${(e as Error).message}`);
    }
}

/** Read the saved state and re-attach + re-inject for each saved session.
 * Falls back to rediscovery-by-exePath when the saved PID is dead.
 *
 * Returns a summary suitable for logging from the host entrypoint. */
export async function restoreSessions(opts: {
    findPidByPath?: (exePath: string) => Promise<number | null>;
    defaultLogDir?: string;
} = {}): Promise<{ found: number; restored: number; failed: Array<{ pid: number; error: string }> }> {
    if (!existsSync(STATE_PATH)) return { found: 0, restored: 0, failed: [] };
    let state: StateFile;
    try {
        state = JSON.parse(readFileSync(STATE_PATH, "utf-8")) as StateFile;
    } catch (e) {
        console.log(`[restore] cannot parse state file: ${(e as Error).message}`);
        return { found: 0, restored: 0, failed: [] };
    }
    const list = state.sessions ?? [];
    if (list.length === 0) return { found: 0, restored: 0, failed: [] };

    suspendPersist = true;
    let restored = 0;
    const failed: Array<{ pid: number; error: string }> = [];
    try {
        for (const saved of list) {
            const result = await tryRestoreOne(saved, opts);
            if (result.ok) restored++;
            else failed.push({ pid: saved.pid, error: result.error });
        }
    } finally {
        suspendPersist = false;
    }
    persist();    // rewrite to reflect what's actually live now
    return { found: list.length, restored, failed };
}

async function tryRestoreOne(
    saved: PersistedSession,
    opts: { findPidByPath?: (exePath: string) => Promise<number | null>; defaultLogDir?: string },
): Promise<{ ok: true } | { ok: false; error: string }> {
    let bundle: string;
    try {
        bundle = await fsp.readFile(saved.bundlePath, "utf-8");
    } catch (e) {
        return { ok: false, error: `bundle read failed: ${(e as Error).message}` };
    }

    // Try the saved PID first.
    try {
        await runScript({
            mode: "attach",
            pid: saved.pid,
            source: bundle,
            // Pas de run-log sur l'auto-restore : personne ne le lit, et c'est
            // le chemin le plus frequent (chaque restart du host).
            exePath: saved.exePath,
            bundlePath: saved.bundlePath,
        });
        console.log(`[restore]   ✓ pid ${saved.pid}`);
        return { ok: true };
    } catch (e) {
        const err = (e as Error).message;
        // PID dead / recycled — try rediscovery by exePath if available.
        if (saved.exePath && opts.findPidByPath) {
            try {
                const newPid = await opts.findPidByPath(saved.exePath);
                if (newPid && newPid !== saved.pid) {
                    await runScript({
                        mode: "attach",
                        pid: newPid,
                        source: bundle,
                        exePath: saved.exePath,
                        bundlePath: saved.bundlePath,
                    });
                    console.log(`[restore]   ✓ pid ${saved.pid} → ${newPid} (rediscovered by exePath)`);
                    return { ok: true };
                }
            } catch (e2) {
                return { ok: false, error: `rediscovery failed: ${(e2 as Error).message}` };
            }
        }
        return { ok: false, error: err };
    }
}

// ---------- Internal ----------

async function getDevice(): Promise<frida.Device> {
    return frida.getLocalDevice();
}

/** Safe read of Frida's `Script.isDestroyed` getter. A live script never
 * throws here; treat a throw (native handle gone) as destroyed. */
function isScriptDestroyed(script: frida.Script): boolean {
    try {
        return (script as unknown as { isDestroyed: boolean }).isDestroyed === true;
    } catch {
        return true;
    }
}

/** Resolve a session that is BOTH marked running AND whose script is still
 * alive. Self-heals a zombie (status "running" but the script was destroyed
 * without the session detaching) by finalizing it, and throws an actionable
 * error instead of leaking Frida's raw "Script is destroyed". */
function requireLiveSession(id: number): RunSession {
    const session = sessions.get(id);
    if (!session?.fridaScript || session.status !== "running") {
        throw new Error(`Session ${id} not running`);
    }
    if (isScriptDestroyed(session.fridaScript)) {
        // Zombie: the destroyed signal may not have propagated yet (or fired
        // before this session's handler was wired). Mark it dead now so
        // pickRunningSession / admin status stop advertising it.
        session.status = "stopped";
        session.endedAt = new Date().toISOString();
        closeLog(session.id);
        pruneRunnersBySession(session.id).catch(() => { /* best effort */ });
        persist();
        throw new Error(
            `Session ${id} script is destroyed — reinject (POST /api/admin/inject); ` +
            "if inject wedges on the same PID, relaunch Tacticus first",
        );
    }
    return session;
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
