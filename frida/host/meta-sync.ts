// Per-version metadata sync.
//
// At inject-time we ask the agent for `Application.version` (the live
// Tacticus build) and fan out to extract every metadata flavour that's
// missing for that version. Files land under `data/meta/<version>/...`.
// Subsequent injects on the same version are no-ops (just confirm files
// exist), so reconnecting is cheap.
//
// Pieces synced:
//   - enums.json     — agent RPC `dumpEnums` (curated list, ~50 KB)
//   - i18n/<lang>.json — Python extractor (UnityPy reads bundles)
//
// Static PNGs (units, abilities, boards) live in `assets/public/` and
// aren't versioned because the asset key (assetNaming) is content-stable;
// extraction stays a one-shot manual `npm run sync:assets` step.

import { promises as fs } from "fs";
import { existsSync } from "fs";
import { spawn } from "child_process";
import path from "path";
import { rpcCall } from "./sessions.js";

const META_ROOT = path.resolve(process.cwd(), "data", "meta");

/** Most recently synced game version slug (matches a directory under
 * `data/meta/<v>/` with a `manifest.json`). Returns null if nothing has been
 * synced yet. Used by the front to know which `/meta/<v>/...` to fetch. */
export async function activeMetaVersion(): Promise<string | null> {
    try {
        const entries = await fs.readdir(META_ROOT, { withFileTypes: true });
        const dirs = entries.filter((e) => e.isDirectory());
        if (dirs.length === 0) return null;
        let best: { name: string; mtime: number } | null = null;
        for (const d of dirs) {
            const m = path.join(META_ROOT, d.name, "manifest.json");
            try {
                const st = await fs.stat(m);
                if (!best || st.mtimeMs > best.mtime) {
                    best = { name: d.name, mtime: st.mtimeMs };
                }
            } catch { /* manifest missing, skip */ }
        }
        return best?.name ?? null;
    } catch { return null; }
}

export interface SyncedItem {
    name: string;
    path: string;
    bytes: number;
    cached: boolean;
}

export interface MetaSyncResult {
    version: string;
    identifier: string | null;
    productName: string | null;
    unityVersion: string | null;
    metaDir: string;
    items: SyncedItem[];
    errors: Array<{ name: string; error: string }>;
}

/** Sanitize a version string into a directory-safe slug. Tacticus versions
 * look like "8.13.7" but we don't trust the input — strip anything outside
 * `[A-Za-z0-9._-]`. */
function safeVersion(v: string): string {
    return v.replace(/[^A-Za-z0-9._-]/g, "_");
}

/** Pull `Application.version`, `identifier`, `productName`, `unityVersion`
 * via the agent RPC. Throws if no live session or RPC unavailable. */
export async function fetchGameVersion(sessionId: number): Promise<{
    version: string;
    identifier: string | null;
    productName: string | null;
    unityVersion: string | null;
}> {
    const r = await rpcCall(sessionId, "getGameVersion", [], 5000) as {
        version: string | null;
        identifier: string | null;
        productName: string | null;
        unityVersion: string | null;
    };
    if (!r || !r.version) {
        throw new Error("agent returned no version (Application.version null)");
    }
    return r as {
        version: string;
        identifier: string | null;
        productName: string | null;
        unityVersion: string | null;
    };
}

/** Sync campaign-catalog.json for the active version. Always re-fetched from
 * the live agent (the catalog is small and may change as the game evolves
 * within the same version due to live event campaigns being added/removed).
 *
 * Called automatically in `fast` mode after inject AND exposed via
 * `/api/campaigns/catalog/refresh` for manual UI refresh.
 *
 * Throws if the agent has no live CampaignGameModeSource yet — caller
 * (router) translates this into 409 with a "open campaign view first"
 * message. */
export async function syncCampaignCatalog(sessionId: number, allowHeapScan = false): Promise<{
    version: string; bytes: number; path: string;
}> {
    const ver = await fetchGameVersion(sessionId);
    const slug = safeVersion(ver.version);
    const metaDir = path.join(META_ROOT, slug);
    await fs.mkdir(metaDir, { recursive: true });

    // `allowHeapScan` opt-in: when false, the agent will refuse to scan the
    // IL2CPP heap (which freezes Tacticus's main thread ~10 s) and instead
    // throws a clear "click any campaign battle to warm up" error. The /↻
    // refresh button explicitly passes true to force a scan if the amorce
    // capture failed.
    const r = await rpcCall(sessionId, "dumpCampaignCatalog",
        [{ allowHeapScan }],
        allowHeapScan ? 25000 : 5000) as {
        bytes: number; json: string;
    };
    const out = path.join(metaDir, "campaign-catalog.json");
    await fs.writeFile(out, r.json);
    return {
        version: ver.version,
        bytes: r.bytes,
        path: path.relative(process.cwd(), out).replace(/\\/g, "/"),
    };
}

/** Sync mow-catalog.json (MachinesOfWar event battles per tier).
 *
 * Requires the user to have navigated to the MoW event in-game once
 * (so the agent has captured a live MachinesOfWarEventGameModeSource).
 * Throws with a clear message otherwise — the router translates to 409. */
export async function syncMoWCatalog(sessionId: number): Promise<{
    version: string; bytes: number; tierCount: number; path: string;
}> {
    const ver = await fetchGameVersion(sessionId);
    const slug = safeVersion(ver.version);
    const metaDir = path.join(META_ROOT, slug);
    await fs.mkdir(metaDir, { recursive: true });

    const r = await rpcCall(sessionId, "dumpMachinesOfWarCatalog",
        [], 15000) as { bytes: number; json: string; tierCount: number };
    const out = path.join(metaDir, "mow-catalog.json");
    await fs.writeFile(out, r.json);
    return {
        version: ver.version,
        bytes: r.bytes,
        tierCount: r.tierCount,
        path: path.relative(process.cwd(), out).replace(/\\/g, "/"),
    };
}

async function syncCampaignCatalogAsItem(
    sessionId: number, metaDir: string,
): Promise<SyncedItem> {
    const out = path.join(metaDir, "campaign-catalog.json");
    // Only triggered by `syncMetadata("full")` = explicit /api/meta/sync.
    // Allow heap scan as fallback if natural capture isn't ready.
    const r = await rpcCall(sessionId, "dumpCampaignCatalog",
        [{ allowHeapScan: true }], 25000) as {
        bytes: number; json: string;
    };
    await fs.writeFile(out, r.json);
    return {
        name: "campaign-catalog", path: "campaign-catalog.json",
        bytes: r.bytes, cached: false,
    };
}

/** Sync enums.json for the active version. Always re-fetched — the curated
 * list of dumped enums (`introspect.ts:DEFAULT_ENUMS`) can grow as we add
 * features, and a stale cache silently breaks the consumers expecting newer
 * entries. The dumpEnums RPC is ~10 ms so the cost is negligible.
 *
 * Also mirrors to `assets/public/enums.json` so the front can fetch it via
 * the static mount (`/assets/enums.json`) without needing the version slug. */
async function syncEnums(sessionId: number, metaDir: string): Promise<SyncedItem> {
    const out = path.join(metaDir, "enums.json");
    const result = await rpcCall(sessionId, "dumpEnums", [], 15000) as Record<
        string, { asm: string; ns: string; count: number; values: Record<string, string> }>;
    const json = JSON.stringify(result, null, 2);
    await fs.mkdir(metaDir, { recursive: true });
    await fs.writeFile(out, json);
    // Mirror to the unversioned static path used by the front. We could
    // also have the front read the versioned path, but the static mount is
    // what the front already wires (api.adminStatus + /assets/enums.json).
    const publicOut = path.resolve(process.cwd(), "assets", "public", "enums.json");
    await fs.writeFile(publicOut, json);
    return { name: "enums", path: "enums.json", bytes: json.length, cached: false };
}

/** Sync i18n/<lang>.json by spawning the Python extractor. Cached if files
 * exist. The extractor writes to `assets/public/i18n/<lang>.json`; we copy
 * (move) into the versioned meta dir so subsequent injects don't re-run
 * the heavy UnityPy parse. */
async function syncI18n(metaDir: string): Promise<SyncedItem[]> {
    const langs = ["en", "fr"];
    const out: SyncedItem[] = [];
    const i18nDir = path.join(metaDir, "i18n");
    await fs.mkdir(i18nDir, { recursive: true });

    const allCached = langs.every((l) => existsSync(path.join(i18nDir, l + ".json")));
    if (allCached) {
        for (const l of langs) {
            const stat = await fs.stat(path.join(i18nDir, l + ".json"));
            out.push({ name: "i18n/" + l, path: "i18n/" + l + ".json",
                       bytes: stat.size, cached: true });
        }
        return out;
    }

    // Spawn the Python extractor with a sub-mode that only does i18n.
    // Re-using build_asset_manifest.py for now — it dumps to assets/public/
    // and we copy from there.
    await runPython(["scripts/python/build_asset_manifest.py"]);

    for (const l of langs) {
        const src = path.resolve(process.cwd(), "assets", "public", "i18n", l + ".json");
        const dst = path.join(i18nDir, l + ".json");
        if (!existsSync(src)) {
            out.push({ name: "i18n/" + l, path: "i18n/" + l + ".json", bytes: 0, cached: false });
            continue;
        }
        await fs.copyFile(src, dst);
        const stat = await fs.stat(dst);
        out.push({ name: "i18n/" + l, path: "i18n/" + l + ".json",
                   bytes: stat.size, cached: false });
    }
    return out;
}

function runPython(args: string[]): Promise<void> {
    return new Promise((resolve, reject) => {
        // Run from the repo root so the script's `..` lookups resolve.
        const cwd = path.resolve(process.cwd(), "..");
        const proc = spawn("python", args, {
            cwd,
            stdio: ["ignore", "inherit", "inherit"],
            env: { ...process.env, PYTHONIOENCODING: "utf-8" },
        });
        proc.on("error", reject);
        proc.on("exit", (code) => {
            if (code === 0) resolve();
            else reject(new Error(`python exited with code ${code}`));
        });
    });
}

/** Top-level orchestrator. Idempotent — only generates what's missing.
 *
 * `mode: "fast"` runs only the cheap pieces (RPC-only, ~10ms total). Used
 * after every inject so the front always has the active version's enum
 * map without waiting on Python.
 *
 * `mode: "full"` adds the heavy bits (i18n via UnityPy, ~25s on first run).
 * Triggered explicitly via `/api/meta/sync`. */
export async function syncMetadata(
    sessionId: number, mode: "fast" | "full" = "full",
): Promise<MetaSyncResult> {
    const ver = await fetchGameVersion(sessionId);
    const slug = safeVersion(ver.version);
    const metaDir = path.join(META_ROOT, slug);
    await fs.mkdir(metaDir, { recursive: true });

    const items: SyncedItem[] = [];
    const errors: Array<{ name: string; error: string }> = [];

    try {
        items.push(await syncEnums(sessionId, metaDir));
    } catch (e) {
        errors.push({ name: "enums", error: (e as Error).message });
    }

    // Catalog sync moved out of "fast" path: pre-amorce it falls back to a
    // 10 s `findGameConfigDtoViaHeap` heap scan that suspends the game's main
    // thread, tripping Tacticus's UnityFreezeDetector and crashing the
    // process. Triggered explicitly by /api/campaigns/catalog/refresh after
    // the user warms up (opens any campaign view + clicks BATTLE).
    if (mode === "full") {
        try {
            items.push(await syncCampaignCatalogAsItem(sessionId, metaDir));
        } catch (e) {
            errors.push({ name: "campaign-catalog", error: (e as Error).message });
        }
    }

    if (mode === "full") {
        try {
            items.push(...await syncI18n(metaDir));
        } catch (e) {
            errors.push({ name: "i18n", error: (e as Error).message });
        }
    }

    // Drop a manifest so the front knows the contract is satisfied for this
    // version. Used as the "is this version known?" check on next inject.
    // Merge with any pre-existing manifest so a `fast` run doesn't blow
    // away records of `full` items synced earlier.
    let prev: Record<string, unknown> = {};
    const manifestPath = path.join(metaDir, "manifest.json");
    if (existsSync(manifestPath)) {
        try { prev = JSON.parse(await fs.readFile(manifestPath, "utf-8")); }
        catch { /* corrupt — overwrite */ }
    }
    const prevItems = Array.isArray(prev.items)
        ? (prev.items as Array<{ name: string }>) : [];
    const mergedItems = mergeItems(prevItems, items.map((i) => ({
        name: i.name, path: i.path, bytes: i.bytes,
    })));
    const manifest = {
        version: ver.version,
        identifier: ver.identifier,
        productName: ver.productName,
        unityVersion: ver.unityVersion,
        generatedAt: new Date().toISOString(),
        items: mergedItems,
    };
    await fs.writeFile(manifestPath, JSON.stringify(manifest, null, 2));

    return {
        version: ver.version,
        identifier: ver.identifier,
        productName: ver.productName,
        unityVersion: ver.unityVersion,
        metaDir: path.relative(process.cwd(), metaDir).replace(/\\/g, "/"),
        items,
        errors,
    };
}

/** Merge two item arrays by `name` — the latter wins on collision. */
function mergeItems<T extends { name: string }>(prev: T[], next: T[]): T[] {
    const map = new Map<string, T>();
    for (const i of prev) map.set(i.name, i);
    for (const i of next) map.set(i.name, i);
    return [...map.values()];
}
