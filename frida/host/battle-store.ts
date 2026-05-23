// File-backed dump of battle_event payloads for debug exploration.
//
// Every `send({t:"battle_event", runnerId, msg, events, matchState})` from the
// hook is written to logs/runs/<runnerId>/<seq>-<msg>.json. The matchState
// string (potentially hundreds of KB) is stripped from the WS broadcast so
// the browser doesn't get flooded — it fetches via HTTP if needed.
//
// The next iteration will parse matchState on receipt and forward only a
// compact renderState (unit positions, HP, owner) alongside the events.

import { promises as fs } from "fs";
import path from "path";
import { registerHandler } from "./router-messages.js";

const RUNS_DIR = path.resolve(process.cwd(), "logs", "runs");

interface RunnerMeta {
    runnerId: number;
    configId?: string;
    sessionId: number;
    startedAt: number;
    seq: number;
    lastLabel?: string;
    lastUpdatedAt?: number;
}

const runners = new Map<number, RunnerMeta>();

function nextSeq(runnerId: number): number {
    const e = runners.get(runnerId);
    if (!e) return 1;
    e.seq += 1;
    return e.seq;
}

/** Called by /api/launch before RPCs so we track (runnerId → configId). */
export function registerRunner(
    runnerId: number, sessionId: number, configId: string,
): void {
    runners.set(runnerId, {
        runnerId, sessionId, configId,
        startedAt: Date.now(), seq: 0,
    });
}

export function listRunners(): RunnerMeta[] {
    return [...runners.values()].sort((a, b) => b.startedAt - a.startedAt);
}

export async function removeRunner(runnerId: number): Promise<boolean> {
    if (!runners.has(runnerId)) return false;
    runners.delete(runnerId);
    seqByRunnerDelete(runnerId);
    // Best-effort disk cleanup.
    try {
        await fs.rm(path.join(RUNS_DIR, String(runnerId)), {
            recursive: true, force: true,
        });
    } catch { /* ignore */ }
    return true;
}

/** Drop any host-side runner whose id isn't in `keep`. Used by /api/runners/sync
 * after Frida is relaunched: the hook's in-memory runner registry resets, so
 * host entries tied to vanished runnerIds are stale and their ids must go. */
export async function pruneRunners(keep: Set<number>): Promise<number[]> {
    const removed: number[] = [];
    for (const id of [...runners.keys()]) {
        if (!keep.has(id)) {
            await removeRunner(id);
            removed.push(id);
        }
    }
    return removed;
}

/** Drop every runner tied to a specific session. Called when a Frida session
 * stops — its runners live inside the script's heap, so they are dead as soon
 * as the script unloads. */
export async function pruneRunnersBySession(sessionId: number): Promise<number[]> {
    const removed: number[] = [];
    for (const [id, meta] of [...runners.entries()]) {
        if (meta.sessionId === sessionId) {
            await removeRunner(id);
            removed.push(id);
        }
    }
    return removed;
}

function seqByRunnerDelete(_id: number): void { /* no-op — seq lives on meta */ }

export function latestDumpPath(runnerId: number): string | null {
    const e = runners.get(runnerId);
    if (!e || !e.lastLabel || e.seq < 1) return null;
    const fname = `${String(e.seq).padStart(4, "0")}-${safe(e.lastLabel)}.json`;
    return path.join(RUNS_DIR, String(runnerId), fname);
}

function safe(s: string): string {
    return s.replace(/[^A-Za-z0-9._-]/g, "_");
}

export async function initBattleStore(): Promise<void> {
    await fs.mkdir(RUNS_DIR, { recursive: true });
    console.log(`[battle-store] dumping battle events to ${RUNS_DIR}`);

    // Agent-side auto-dispose notification — emitted by recorder.ts when a
    // build runner's match ends so its registry entry shouldn't linger on
    // the front. Without this handler the host registry would still list
    // the dead runnerId until a manual /api/runners/sync.
    registerHandler("runner_disposed", ({ payload, envelope }) => {
        const id = typeof payload.runnerId === "number" ? payload.runnerId : null;
        if (id !== null) {
            removeRunner(id).then((removed) =>
                console.log(`[battle-store] runner ${id} auto-disposed (${payload.reason ?? "?"}) · removed=${removed}`),
            ).catch((e) =>
                console.log(`[battle-store] runner ${id} auto-dispose failed: ${e.message}`));
        }
        // Forward as a lightweight WS notification — the front uses it to
        // refresh its runners panel immediately rather than waiting for
        // the next 3s poll.
        envelope.payload = {
            type: "send",
            payload: { t: "runner_disposed", runnerId: id, reason: payload.reason ?? null },
        };
    });

    registerHandler("battle_event", ({ sessionId, payload, envelope }) => {
        const runnerId = typeof payload.runnerId === "number" ? payload.runnerId : 0;
        const msg = typeof payload.msg === "string" ? payload.msg : "unknown";
        // Ensure a RunnerMeta exists even for RPC calls that bypassed /api/launch
        // (e.g. curl tests) — configId will be undefined in that case.
        if (!runners.has(runnerId)) {
            runners.set(runnerId, {
                runnerId, sessionId, startedAt: Date.now(), seq: 0,
            });
        }
        const seq = nextSeq(runnerId);
        const runner = runners.get(runnerId)!;
        runner.lastLabel = msg;
        runner.lastUpdatedAt = Date.now();
        const dir = path.join(RUNS_DIR, String(runnerId));

        const parsedMs = typeof payload.matchState === "string"
            ? safeParse(payload.matchState) : null;
        const dump = {
            runnerId,
            msg,
            seq,
            ts: Date.now(),
            events: payload.events ?? null,
            matchState: parsedMs,
        };
        const fname = `${String(seq).padStart(4, "0")}-${safe(msg)}.json`;

        fs.mkdir(dir, { recursive: true })
            .then(() => fs.writeFile(
                path.join(dir, fname), JSON.stringify(dump, null, 2)))
            .catch((e) =>
                console.log(`[battle-store] write failed (r${runnerId}/${fname}): ${e.message}`));

        // Extract {entityId: visualId} for Type=1 units — small enough to ship
        // in every WS broadcast so the front can render portraits per unit.
        const unitVisuals = extractUnitVisuals(parsedMs);

        // Strip matchState from WS broadcast — browser would choke on repeated
        // multi-MB payloads. Events kept (small, drive animations).
        const { matchState: _ms, ...rest } = payload;
        envelope.payload = {
            type: "send",
            payload: { ...rest, t: "battle_event", unitVisuals, matchStateBytes:
                typeof payload.matchState === "string" ? payload.matchState.length : 0 },
        };
    });
}

function safeParse(s: string): unknown {
    try { return JSON.parse(s); }
    catch { return { _rawPreview: s.slice(0, 500), _parseFailed: true }; }
}

/** Walk parsed matchState._entities → Type=1 units → pick up VisualId from
 * any component that carries one. Returns {} if the shape doesn't match. */
function extractUnitVisuals(ms: unknown): Record<number, string> {
    const out: Record<number, string> = {};
    if (!ms || typeof ms !== "object") return out;
    const ents = (ms as { _entities?: unknown })._entities;
    if (!Array.isArray(ents)) return out;
    for (const e of ents) {
        if (!e || typeof e !== "object") continue;
        const ent = e as { Id?: number; Type?: number; Components?: unknown[] };
        if (ent.Type !== 1 || typeof ent.Id !== "number") continue;
        const comps = Array.isArray(ent.Components) ? ent.Components : [];
        for (const c of comps) {
            if (!c || typeof c !== "object") continue;
            const v = (c as { VisualId?: unknown }).VisualId;
            if (typeof v === "string" && v.length) { out[ent.Id] = v; break; }
        }
    }
    return out;
}
