// Tacticus admin: auto-discover the running game process on the local
// machine and inject the bundled hooks into it. Wired to the front-end
// status banner + INJECT button via router.ts.
//
// Heuristic for game vs. launcher disambiguation: the actual Tacticus.exe
// (Unity IL2CPP build) is always shipped with a sibling `<basename>_Data`
// folder per Unity convention. The launcher (Electron / native wrapper)
// has no such folder.

import { existsSync } from "fs";
import { promises as fs } from "fs";
import path from "path";
import frida from "frida";
import { runScript, RunSession } from "./sessions.js";

const PROCESS_NAME_RE = /tacticus/i;

export interface TacticusCandidate {
    pid: number;
    name: string;
    path: string | null;
    isGame: boolean;
}

export async function findTacticusCandidates(): Promise<TacticusCandidate[]> {
    const device = await frida.getLocalDevice();
    // scope: 'metadata' returns parameters.path (absolute exe path) so we
    // can locate the sibling `<basename>_Data\` folder.
    const procs = await device.enumerateProcesses({ scope: frida.Scope.Metadata });
    return procs
        .filter((p) => PROCESS_NAME_RE.test(p.name))
        .map((p): TacticusCandidate => {
            const params = (p as unknown as { parameters?: { path?: string } }).parameters;
            const exePath = params?.path ?? null;
            const isGame = exePath !== null && hasUnityDataFolder(exePath);
            return { pid: p.pid, name: p.name, path: exePath, isGame };
        });
}

function hasUnityDataFolder(exePath: string): boolean {
    try {
        const dir = path.dirname(exePath);
        const base = path.basename(exePath, path.extname(exePath));
        return existsSync(path.join(dir, base + "_Data"));
    } catch {
        return false;
    }
}

/** Return the PID of the game process, throwing on absence/ambiguity.
 * Throws with `(err as any).candidates` populated when ambiguous. */
export async function findTacticusGamePid(): Promise<{ pid: number; exePath: string | null }> {
    const cands = await findTacticusCandidates();
    const games = cands.filter((c) => c.isGame);
    if (games.length === 0) {
        const summary = cands.length
            ? `candidates: ${cands.map((c) => `${c.pid}=${c.name}`).join(", ")}`
            : "none";
        throw new Error(`no Tacticus game process found (${summary})`);
    }
    if (games.length > 1) {
        const err = new Error(
            `multiple game candidates: ${games.map((g) => `${g.pid}@${g.path}`).join(", ")}`,
        );
        (err as { candidates?: TacticusCandidate[] }).candidates = games;
        throw err;
    }
    return { pid: games[0].pid, exePath: games[0].path };
}

/** Locate a candidate by exact exe path — used by sessionManager.restoreSessions
 * to recover after a Tacticus close+restart cycle (PID changes, path stable). */
export async function findPidByExePath(exePath: string): Promise<number | null> {
    const cands = await findTacticusCandidates();
    const match = cands.find((c) => c.path === exePath && c.isGame);
    return match ? match.pid : null;
}

/** Read dist/hooks.js + spawn a Frida session against the given PID, or
 * auto-discover the game PID when not specified. */
export async function injectBundle(opts: {
    pid?: number;
    bundlePath?: string;
    logDir?: string;
} = {}): Promise<{ session: RunSession; bundleBytes: number }> {
    const bundlePath = opts.bundlePath
        ?? path.resolve(process.cwd(), "dist", "hooks.js");

    const source = await fs.readFile(bundlePath, "utf-8");

    let pid: number;
    let exePath: string | null = null;
    if (opts.pid !== undefined) {
        pid = opts.pid;
        // Best-effort enrichment so persistence has the exePath even when
        // the user forced a PID manually.
        const cands = await findTacticusCandidates();
        const match = cands.find((c) => c.pid === pid);
        exePath = match?.path ?? null;
    } else {
        const found = await findTacticusGamePid();
        pid = found.pid;
        exePath = found.exePath;
    }

    const session = await runScript({
        mode: "attach",
        pid,
        target: "tacticus",
        source,
        // ⚠ PAS de défaut ici, et c'est VOULU (cf. `index.ts` : le défaut a été retiré le
        // 2026-07-26 après avoir accumulé 3 663 Mo / 828 fichiers `run-*.jsonl` — un par
        // session, contenant CHAQUE message de l'agent — sans qu'aucun lecteur existe
        // dans le dépôt). Le journal reste une CAPACITÉ, demandée explicitement par
        // `log_dir` dans le corps de l'inject. Les timings de stop, eux, passent par le
        // `console.log` de `stopSession` : ils n'ont pas besoin du flux complet.
        logDir: opts.logDir,
        exePath: exePath ?? undefined,
        bundlePath,
    });
    return { session, bundleBytes: source.length };
}
