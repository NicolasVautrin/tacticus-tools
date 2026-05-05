// AI evaluation trace store — receives ai_trace messages from the agent
// and appends them to a per-session NDJSON file under data/ai-traces/.
//
// File naming: <sessionId>-<startIso>.jsonl. One file per Frida session.
// The first event of a session opens the writable stream lazily; the
// stream stays open for the session's lifetime and is closed when the
// session detaches (we listen for "diag" messages mentioning a session
// shutdown? simpler: we close on process exit).
//
// Format: one JSON object per line, fields:
//   { sessionId, t:"ai_trace", seq, ts, evt, ... }
// where `evt` is one of:
//   playbook_eval_begin / playbook_eval_end / playbook_action  (L1)
//   candidates                                                  (L2)
//   utility_case                                                (L3)
//   control                                                     (toggle log)
//
// Keep this lean — no in-memory aggregation, just write-through.

import { promises as fsp, createWriteStream, WriteStream } from "fs";
import path from "path";
import { registerHandler } from "./router-messages.js";

const TRACES_DIR = path.resolve(process.cwd(), "data", "ai-traces");

interface Writer {
    sessionId: number;
    path: string;
    stream: WriteStream;
    lineCount: number;
    openedAt: number;
}

const writers = new Map<number, Writer>();

function safeIso(iso: string): string {
    return iso.replace(/[:.]/g, "-");
}

function getOrOpen(sessionId: number): Writer {
    const existing = writers.get(sessionId);
    if (existing) return existing;
    const startedAt = new Date().toISOString();
    const fname = `${sessionId}-${safeIso(startedAt)}.jsonl`;
    const fpath = path.join(TRACES_DIR, fname);
    const stream = createWriteStream(fpath, {
        flags: "a", encoding: "utf-8",
    });
    const w: Writer = {
        sessionId, path: fpath, stream, lineCount: 0,
        openedAt: Date.now(),
    };
    writers.set(sessionId, w);
    console.log(`[ai-trace] session ${sessionId} → ${fpath}`);
    return w;
}

export async function initAiTraceStore(): Promise<void> {
    await fsp.mkdir(TRACES_DIR, { recursive: true });
    console.log(`[ai-trace] persisting AI evaluation traces to ${TRACES_DIR}`);

    registerHandler("ai_trace", ({ sessionId, payload, envelope }) => {
        const w = getOrOpen(sessionId);
        // Strip routing/redundant fields before write:
        //   - sessionId : already in the filename
        //   - t : always "ai_trace" (routing discriminator, no value on disk)
        //   - ts : agent-side wall-clock — redundant with seq for ordering;
        //          the host-side `openedAt` of the writer gives session start.
        // Keep seq (cross-referenced by playbookSeq inside utility_score).
        const { t: _t, ts: _ts, ...record } = payload;
        try {
            w.stream.write(JSON.stringify(record) + "\n");
            w.lineCount++;
        } catch (e) {
            console.log(`[ai-trace] write failed (s${sessionId}): `
                + (e as Error).message);
        }

        // Drop the per-line payload from the WS broadcast — the front
        // doesn't render AI traces (user explicitly opted for disk-only).
        // Keep the envelope minimal so the dev can still see "ai_trace"
        // markers in logs without flooding the browser.
        envelope.payload = { t: "ai_trace", seq: payload.seq, evt: payload.evt };
    });
}

/** Close all open writers — call from graceful shutdown. */
export async function closeAiTraceStore(): Promise<void> {
    const all = [...writers.values()];
    writers.clear();
    await Promise.all(all.map((w) => new Promise<void>((resolve) => {
        w.stream.end(() => {
            console.log(`[ai-trace] closed s${w.sessionId} (${w.lineCount} lines)`);
            resolve();
        });
    })));
}

/** For diagnostics — return the current writer state. */
export function aiTraceStoreStatus(): {
    dir: string;
    sessions: Array<{ sessionId: number; path: string;
        lineCount: number; openedAt: number }>;
} {
    return {
        dir: TRACES_DIR,
        sessions: [...writers.values()].map((w) => ({
            sessionId: w.sessionId,
            path: w.path,
            lineCount: w.lineCount,
            openedAt: w.openedAt,
        })),
    };
}
