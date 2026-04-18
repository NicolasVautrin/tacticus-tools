// Append-only JSONL logger for Frida session events.
// One file per session: logs/run-{id}_{timestamp}_{target}.jsonl

import fs from "fs";
import path from "path";

const openStreams = new Map<number, fs.WriteStream>();

function pad2(n: number): string {
    return n.toString().padStart(2, "0");
}

function sessionFileName(sessionId: number, target: string): string {
    const d = new Date();
    const ts = `${pad2(d.getHours())}${pad2(d.getMinutes())}${pad2(d.getSeconds())}`;
    return `run-${sessionId}_${ts}_${target || "unknown"}.jsonl`;
}

export function openLog(sessionId: number, logDir: string, target: string): void {
    if (openStreams.has(sessionId)) return;
    fs.mkdirSync(logDir, { recursive: true });
    const filePath = path.join(logDir, sessionFileName(sessionId, target));
    const stream = fs.createWriteStream(filePath, { flags: "a", encoding: "utf-8" });
    openStreams.set(sessionId, stream);
}

export function appendLog(sessionId: number, envelope: unknown): void {
    const stream = openStreams.get(sessionId);
    if (!stream) return;
    stream.write(JSON.stringify(envelope) + "\n");
}

export function closeLog(sessionId: number): void {
    const stream = openStreams.get(sessionId);
    if (stream) {
        stream.end();
        openStreams.delete(sessionId);
    }
}
