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
    // Light-weight identity: extracted from the BattleConfiguration JSON at
    // capture time. Cheaper than re-reading the file every list-render and
    // displayed in the archive panel for at-a-glance identification.
    board?: string | null;     // Board.Id, e.g. "C1_75", "C5_01", "C1_t_01"
    campaignId?: string | null;     // e.g. "campaign1", "eventStandard1"
    locationIndex?: number | null;  // 0-based battle index in the campaign
    /** When the live runner had a captured message log at save time, we
     * persist it as a separate <id>.bundle.json file. Lets preview-from-
     * saved replay messages on a fresh build runner so it reaches the
     * exact saved state. Null on legacy (config-only) saves. */
    messageCount?: number | null;
    bundlePath?: string | null;  // relative path "configs/<safe>.bundle.json"
    /** Free-form user description — set/edited via PATCH /api/configs/:id.
     * Displayed under the save tile heading so the user can label saves
     * ("interesting overwatch case", "round 5 turn point", ...). */
    description?: string | null;
}

export interface ReplayBundleMessage {
    idx: number;
    src: string;
    cls: string;
    ns: string;
    unitId: number | null;
    prng: unknown;  // MtSnapshot — opaque to host, the agent owns the schema
    json: string | null;
}

export interface ReplayBundle {
    configJson: string;
    messages: ReplayBundleMessage[];
    capturedAt: number;
}

/** Cheap Board.Id extraction from the JSON string. The serializer puts
 * the `Board` object near the top with `"Id": "..."` as one of its first
 * fields. Avoids parsing 500+ KB of JSON just to read one string. */
function extractBoardId(json: string): string | null {
    // Look for the Board object opening, then its Id.
    const m = /"Board"\s*:\s*\{[^}]{0,200}?"Id"\s*:\s*"([^"]+)"/i.exec(
        json.slice(0, 4096));
    return m ? m[1] : null;
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
    // Backfill `board` for legacy captures missing it. Read each file once,
    // extract Board.Id, persist back. One-shot on boot so subsequent renders
    // are cheap.
    let backfilled = 0;
    for (const m of index) {
        if (m.board !== undefined) continue;
        try {
            // Read just the head — Board comes near the top of the JSON.
            const fh = await fs.open(
                path.join(CONFIGS_DIR, path.basename(m.path)), "r");
            const buf = Buffer.alloc(4096);
            await fh.read(buf, 0, 4096, 0);
            await fh.close();
            m.board = extractBoardId(buf.toString("utf-8"));
            backfilled += 1;
        } catch {
            m.board = null;
        }
    }
    if (backfilled) {
        await writeIndex();
        console.log(`[config-store] backfilled board ids on ${backfilled} captures`);
    }
    ready = true;
    console.log(`[config-store] ${index.length} captures indexed from ${CONFIGS_DIR}`);

    registerHandler("captured_config", ({ sessionId, payload, envelope }) => {
        if (typeof payload.id !== "string" || typeof payload.json !== "string") return;

        const id = payload.id;
        const fname = `${safeId(id)}.json`;
        const bundleFname = `${safeId(id)}.bundle.json`;
        const jsonStr = payload.json as string;
        const messages = Array.isArray(payload.messages) ? payload.messages : null;
        const meta: CapturedConfigMeta = {
            id,
            mode: typeof payload.mode === "string" ? payload.mode : "?",
            ts: typeof payload.ts === "number" ? payload.ts : Date.now(),
            bytes: typeof payload.bytes === "number"
                ? payload.bytes : jsonStr.length,
            sessionId,
            path: `configs/${fname}`,
            board: extractBoardId(jsonStr),
            campaignId: typeof payload.campaignId === "string"
                ? payload.campaignId : null,
            locationIndex: typeof payload.locationIndex === "number"
                ? payload.locationIndex : null,
            messageCount: messages ? messages.length : null,
            bundlePath: messages ? `configs/${bundleFname}` : null,
        };

        const writeAll = async (): Promise<void> => {
            await fs.writeFile(path.join(CONFIGS_DIR, fname), jsonStr);
            if (messages) {
                // Persist messages as a separate file alongside the config.
                // Keeps the existing config file format byte-for-byte
                // (consumers like /api/configs/:id are unchanged) and only
                // load-from-bundle paths know about the extra file.
                const bundle = JSON.stringify({
                    version: 1,
                    capturedAt: meta.ts,
                    messageCount: messages.length,
                    messages,
                });
                await fs.writeFile(
                    path.join(CONFIGS_DIR, bundleFname), bundle);
            }
            const i = index.findIndex((e) => e.id === id);
            if (i >= 0) index[i] = meta;
            else index.push(meta);
            await writeIndex();
        };
        writeAll().catch((e) =>
            console.log(`[config-store] write failed for ${id}: ${e.message}`));

        // Strip the heavy `json` AND `messages` fields from the broadcast
        // envelope — the browser fetches via /api/configs/:id on demand and
        // the bundle is only relevant at preview-from-saved time.
        const { json: _j, messages: _m, ...rest } = payload;
        envelope.payload = { type: "send", payload: { ...rest, t: "captured_config" } };
    });
}

export function listConfigs(): CapturedConfigMeta[] {
    return [...index];
}

/** Persist a config explicitly (vs the implicit `captured_config` agent
 *  flow). Used by /api/launch when the engaged config came from the
 *  campaign builder's inline build — promoting it to the archive only
 *  after the user committed to engage. Returns the stored metadata. */
export async function saveConfig(
    meta: Omit<CapturedConfigMeta, "path" | "bytes" | "ts"> & {
        path?: string; bytes?: number; ts?: number;
    },
    jsonStr: string,
): Promise<CapturedConfigMeta> {
    const fname = `${safeId(meta.id)}.json`;
    const full: CapturedConfigMeta = {
        id: meta.id,
        mode: meta.mode,
        sessionId: meta.sessionId,
        ts: meta.ts ?? Date.now(),
        bytes: meta.bytes ?? jsonStr.length,
        path: meta.path ?? `configs/${fname}`,
        board: meta.board ?? extractBoardId(jsonStr),
        campaignId: meta.campaignId ?? null,
        locationIndex: meta.locationIndex ?? null,
    };
    await fs.mkdir(CONFIGS_DIR, { recursive: true });
    await fs.writeFile(path.join(CONFIGS_DIR, fname), jsonStr);
    const i = index.findIndex((e) => e.id === full.id);
    if (i >= 0) index[i] = full;
    else index.push(full);
    await writeIndex();
    return full;
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

/** Read both the config JSON and the messages bundle (if any) for a saved
 * capture. Used by preview-from-saved to fully reconstruct a runner via
 * initRunner + replay each message. Returns undefined when the config is
 * missing; returns `{configJson, messages: []}` when only the legacy
 * config file exists (no bundle was persisted at save time). */
export async function getReplayBundle(
    id: string,
): Promise<ReplayBundle | undefined> {
    const meta = index.find((e) => e.id === id);
    if (!meta) return undefined;
    let configJson: string;
    try {
        configJson = await fs.readFile(
            path.join(CONFIGS_DIR, path.basename(meta.path)),
            "utf-8",
        );
    } catch {
        return undefined;
    }
    let messages: ReplayBundleMessage[] = [];
    let capturedAt = meta.ts;
    if (meta.bundlePath) {
        try {
            const raw = await fs.readFile(
                path.join(CONFIGS_DIR, path.basename(meta.bundlePath)),
                "utf-8",
            );
            const parsed = JSON.parse(raw) as {
                capturedAt?: number;
                messages?: ReplayBundleMessage[];
            };
            if (Array.isArray(parsed.messages)) messages = parsed.messages;
            if (typeof parsed.capturedAt === "number") capturedAt = parsed.capturedAt;
        } catch (e) {
            console.log(`[config-store] bundle read failed for ${id}: ${(e as Error).message}`);
        }
    }
    return { configJson, messages, capturedAt };
}

export async function clearConfigs(): Promise<number> {
    const n = index.length;
    await Promise.all(index.flatMap((m) => {
        const tasks = [fs.unlink(path.join(CONFIGS_DIR, path.basename(m.path))).catch(() => {})];
        if (m.bundlePath) {
            tasks.push(fs.unlink(path.join(CONFIGS_DIR, path.basename(m.bundlePath))).catch(() => {}));
        }
        return tasks;
    }));
    index = [];
    await writeIndex();
    return n;
}

/** Set/update the user-facing description on a saved capture. Trims
 * whitespace; an empty string clears the description (stored as null).
 * Returns the updated meta or undefined if the id doesn't exist. */
export async function updateConfigDescription(
    id: string, description: string | null,
): Promise<CapturedConfigMeta | undefined> {
    const i = index.findIndex((e) => e.id === id);
    if (i < 0) return undefined;
    const trimmed = typeof description === "string"
        ? description.trim() : null;
    index[i] = { ...index[i], description: trimmed && trimmed.length > 0 ? trimmed : null };
    await writeIndex();
    return index[i];
}

/** Remove one capture by id. Returns true if found+removed. */
export async function deleteConfig(id: string): Promise<boolean> {
    const i = index.findIndex((e) => e.id === id);
    if (i < 0) return false;
    const [meta] = index.splice(i, 1);
    try {
        await fs.unlink(path.join(CONFIGS_DIR, path.basename(meta.path)));
    } catch { /* file may already be gone */ }
    if (meta.bundlePath) {
        try {
            await fs.unlink(path.join(CONFIGS_DIR, path.basename(meta.bundlePath)));
        } catch { /* file may already be gone */ }
    }
    await writeIndex();
    return true;
}