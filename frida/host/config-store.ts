// File-backed store of BattleConfiguration captures. Each capture is one JSON
// file under CONFIGS_DIR; an index.json catalogs metadata. Populated by
// onMessage in sessions.ts when it sees `send({t:"captured_config",...})`.
//
// Exposed to the browser:
//   GET  /api/configs           → listConfigs() (index)
//   GET  /api/configs/:id       → getConfig(id) (reads file)
//   POST /api/configs/clear     → clearConfigs()
//
// The same directory is served statically at /assets/configs/, so callers can
// also fetch files directly if they want to bypass the API.
//
// Rationale: writing to disk on capture survives host restart with no
// log-scraping rehydration.

import { promises as fs } from "fs";
import path from "path";
import { registerHandler } from "./router-messages.js";

const CONFIGS_DIR = path.resolve(process.cwd(), "assets", "public", "configs");

export interface CapturedConfigMeta {
    id: string;
    mode: string;
    ts: number;
    bytes: number;
    sessionId: number;
    path: string; // relative to /assets — "configs/<safe>.json"
}

let index: CapturedConfigMeta[] = [];
let ready = false;

function safeId(id: string): string {
    return id.replace(/[^A-Za-z0-9._-]/g, "_");
}

async function writeIndex(): Promise<void> {
    await fs.writeFile(
        path.join(CONFIGS_DIR, "index.json"),
        JSON.stringify(index, null, 2),
    );
}

export async function initConfigStore(): Promise<void> {
    await fs.mkdir(CONFIGS_DIR, { recursive: true });
    try {
        const raw = await fs.readFile(path.join(CONFIGS_DIR, "index.json"), "utf-8");
        index = JSON.parse(raw);
    } catch {
        index = [];
    }
    ready = true;
    console.log(`[config-store] ${index.length} captures indexed from ${CONFIGS_DIR}`);

    registerHandler("captured_config", ({ sessionId, payload, envelope }) => {
        if (typeof payload.id !== "string" || typeof payload.json !== "string") return;

        const id = payload.id;
        const fname = `${safeId(id)}.json`;
        const meta: CapturedConfigMeta = {
            id,
            mode: typeof payload.mode === "string" ? payload.mode : "?",
            ts: typeof payload.ts === "number" ? payload.ts : Date.now(),
            bytes: typeof payload.bytes === "number"
                ? payload.bytes : (payload.json as string).length,
            sessionId,
            path: `configs/${fname}`,
        };

        fs.writeFile(path.join(CONFIGS_DIR, fname), payload.json as string)
            .then(() => {
                const i = index.findIndex((e) => e.id === id);
                if (i >= 0) index[i] = meta;
                else index.push(meta);
                return writeIndex();
            })
            .catch((e) =>
                console.log(`[config-store] write failed for ${id}: ${e.message}`));

        // Strip the heavy `json` field from the broadcast envelope — the
        // browser fetches via /api/configs/:id on demand.
        const { json: _j, ...rest } = payload;
        envelope.payload = { type: "send", payload: { ...rest, t: "captured_config" } };
    });
}

export function listConfigs(): CapturedConfigMeta[] {
    return [...index];
}

export async function getConfig(id: string): Promise<string | undefined> {
    const meta = index.find((e) => e.id === id);
    if (!meta) return undefined;
    try {
        return await fs.readFile(
            path.join(CONFIGS_DIR, path.basename(meta.path)),
            "utf-8",
        );
    } catch {
        return undefined;
    }
}

export async function clearConfigs(): Promise<number> {
    const n = index.length;
    await Promise.all(index.map((m) =>
        fs.unlink(path.join(CONFIGS_DIR, path.basename(m.path))).catch(() => {})
    ));
    index = [];
    await writeIndex();
    return n;
}