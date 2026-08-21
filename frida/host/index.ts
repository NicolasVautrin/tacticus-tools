// Host entrypoint — Express + WebSocket server.
// Manages Frida sessions, routes HTTP RPC, persists `send()` to JSONL logs.

import express from "express";
import { createServer } from "http";
import path from "path";
import { buildRouter } from "./router.js";
import { attachWss } from "./ws.js";
import { initConfigStore } from "./config-store.js";
import { initBattleStore } from "./battle-store.js";
import { initReplayStore } from "./replay-store.js";
import { initAiTraceStore, closeAiTraceStore } from "./ai-trace-store.js";
import { postMessage, restoreSessions, stopAllPreservingState } from "./sessions.js";
import { startRunnerReconciler, stopRunnerReconciler } from "./runner-reconcile.js";
import { findPidByExePath } from "./admin.js";
import { registerHandler } from "./router-messages.js";

const PORT = parseInt(process.env.PORT ?? "8765", 10);

// Les SORTIES du host vont sous `logs/` A LA RACINE DU DEPOT, pas sous
// `frida/`. Les npm scripts tournent depuis `frida/`, d'ou le `..`.
//
// Ce repertoire n'est utilise QUE si l'appelant demande explicitement un
// journal (`log_dir` dans le corps de l'inject). Il n'est PLUS le defaut :
// mesure du 2026-07-26, `frida/logs/` avait accumule 3 663 Mo / 828 fichiers
// -- un `run-*.jsonl` par session, contenant CHAQUE message de l'agent -- et
// le depot ne contient AUCUN lecteur (grep : seul `logger.ts` y touche, et il
// ne fait qu'ecrire). On garde la capacite, on retire le defaut.
const DEFAULT_LOG_DIR = path.resolve(process.cwd(), "..", "logs", "sessions");

const app = express();
app.use(express.json({ limit: "10mb" }));
app.use(buildRouter(DEFAULT_LOG_DIR));

const server = createServer(app);
attachWss(server);

await initConfigStore();
await initBattleStore();
await initAiTraceStore();
initReplayStore();

// Mirror agent-side `log()` calls to the host stdout so `npm run dev` stays
// readable. The full payload is also persisted to logs/run-*_<target>.jsonl
// via appendLog (handlers don't suppress that), so off-process tail still works.
registerHandler("diag", ({ sessionId, payload }) => {
    const msg = typeof payload.msg === "string" ? payload.msg : JSON.stringify(payload);
    console.log(`[s${sessionId}] ${msg}`);
});

// Pretty-print crash snapshots so they're impossible to miss in the dev
// terminal. Full payload still goes to the JSONL log + WS broadcast.
// Both crash_diag and crash_backtrace expect an immediate ack so the
// agent's recv("crash_diag_ack").wait() unblocks before unwind kills the
// process. Same handler shape for both.
registerHandler("crash_backtrace", ({ sessionId, payload }) => {
    try {
        postMessage(sessionId, { type: "crash_diag_ack" });
    } catch { /* session may be gone */ }
    const bt = (payload.backtrace ?? []) as Array<{
        addr: string; rva: string | null; label: string }>;
    if (!bt.length) return;
    console.log(`\n[s${sessionId}] === CRASH BACKTRACE (${bt.length} frames) ===`);
    for (const f of bt) {
        console.log(`  ${f.addr}  rva=${f.rva ?? "?"}  ${f.label}`);
    }
    console.log("  ============================\n");
});

registerHandler("crash_diag", ({ sessionId, payload }) => {
    // Send ack IMMEDIATELY so the agent's recv("crash_diag_ack").wait()
    // unblocks before the OS continues unwinding (and kills the process).
    try {
        postMessage(sessionId, { type: "crash_diag_ack" });
    } catch { /* session may be gone */ }
    const regs = (payload.registers ?? {}) as Record<string, string>;
    console.log(`\n[s${sessionId}] === CRASH SNAPSHOT ===`);
    console.log(`  type:   ${payload.exception_type}`);
    console.log(`  rip:    ${payload.rip}`);
    console.log(`  module: ${payload.module_name} @ ${payload.module_base}`
        + `  (rva ${payload.module_rva})`);
    console.log(`  GA-rva: ${payload.rva}   (GameAssembly.dll @ ${payload.il2cpp_base})`);
    console.log(`  instr:  ${payload.instruction}`);
    console.log(`  fault:  ${payload.fault_op} @ ${payload.fault_address}`);
    const prior = (payload.prior_instructions ?? []) as string[];
    if (prior.length) {
        console.log(`  prior instructions:`);
        for (const p of prior) console.log(`    ${p}`);
    }
    const order = ["rax", "rbx", "rcx", "rdx", "rsi", "rdi", "rbp", "rsp",
        "r8", "r9", "r10", "r11", "r12", "r13", "r14", "r15"];
    for (const k of order) {
        if (regs[k]) console.log(`  ${k.padEnd(4)} ${regs[k]}`);
    }
    const bt = (payload.backtrace ?? []) as Array<{
        addr: string; rva: string | null; label: string }>;
    if (bt.length) {
        console.log(`  backtrace:`);
        for (const f of bt) {
            console.log(`    ${f.addr}  rva=${f.rva ?? "?"}  ${f.label}`);
        }
    }
    console.log("  ======================\n");
});

// Filet #321 : converge le cache host des runners vers le registre des hooks
// (l'AUTORITE). Le chemin nominal est deja ferme dans `rpcCall` ; ce timer ne
// rattrape qu'un chemin de mort non cable. Ne purge JAMAIS sur mesure absente.
startRunnerReconciler();

server.listen(PORT, "127.0.0.1", async () => {
    console.log(`[host] listening on http://127.0.0.1:${PORT}`);
    console.log(`[host] default log dir: ${DEFAULT_LOG_DIR}`);

    if (process.env.TACTICUS_NO_RESTORE === "1") {
        console.log("[host] TACTICUS_NO_RESTORE=1 — skipping session restore");
        return;
    }
    try {
        const r = await restoreSessions({
            findPidByPath: findPidByExePath,
            defaultLogDir: DEFAULT_LOG_DIR,
        });
        if (r.found > 0) {
            console.log(`[host] restored ${r.restored}/${r.found} session(s)`
                + (r.failed.length ? `, ${r.failed.length} failed` : ""));
            for (const f of r.failed) {
                console.log(`[host]   ✗ pid ${f.pid}: ${f.error}`);
            }
        }
    } catch (e) {
        console.log(`[host] restore failed: ${(e as Error).message}`);
    }
});

// Graceful shutdown: detach Frida sessions WITHOUT clearing the persisted
// state file, so the next boot can restore them. Catches SIGINT (Ctrl+C in
// the terminal) and SIGTERM (process manager / Docker stop).
let shuttingDown = false;
async function shutdown(signal: string): Promise<void> {
    if (shuttingDown) return;
    shuttingDown = true;
    console.log(`[host] ${signal} received — detaching sessions (state preserved)`);
    // AVANT de détacher : le réconciliateur purge le cache host des runners d'après le
    // registre des hooks. Le laisser tourner pendant qu'on détache le ferait mesurer un
    // registre en train de disparaître et conclure « ces runners sont morts » sur une
    // session qu'on veut justement RESTAURER au prochain boot (#480-r7).
    stopRunnerReconciler();
    try { await stopAllPreservingState(); } catch { /* ignore */ }
    try { await closeAiTraceStore(); } catch { /* ignore */ }
    process.exit(0);
}
process.on("SIGINT", () => { void shutdown("SIGINT"); });
process.on("SIGTERM", () => { void shutdown("SIGTERM"); });
