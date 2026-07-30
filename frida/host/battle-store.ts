// File-backed dump of battle_event payloads for debug exploration.
//
// Every `send({t:"battle_event", runnerId, msg, events, matchState})` from the
// hook is written to logs/runs/<runnerId>/<seq>-<msg>.json. The matchState
// string (potentially hundreds of KB) is stripped from the WS broadcast so
// the browser doesn't get flooded — it fetches via HTTP if needed.
//
// ---------------------------------------------------------------------------
// CE QUE `runners` EST, ET CE QU'IL N'EST PAS (#321).
//
// C'est un CACHE host des runners VIVANTS — metadonnees de presentation
// (configId, dernier message, chemin du dernier dump) pour le panneau du front
// et pour `/api/runners/:id/latest-state`. Ce N'EST PAS un journal d'audit :
// une entree qui reste apres la mort du runner est un BUG, pas un historique.
//
// L'AUTORITE est le registre des HOOKS (`frida/hooks/game/runner-registry.ts`,
// map `byId`), et c'est LUI SEUL que `MAX_RUNNERS` gate, aux deux points de
// creation (`initAndStart` dans `frida/hooks/features/launch.ts`,
// `buildPatchedRunner` dans `frida/hooks/features/battle-config.ts`). Ce cache
// ne gate RIEN, ne borne RIEN : le lire comme un compteur de capacite est une
// erreur de categorie.
//
// POURQUOI c'est ecrit noir sur blanc : le 2026-07-31, `GET /api/runners`
// rendait 306 entrees quand la RPC `listRunners` des hooks en rendait 0, et la
// lecture « 303 runners vivants pour un cap de 50 » a produit une fausse alerte
// capacite. Mesure de l'ecart quelques minutes plus tard : 318 cote host vs 0
// cote hooks, ids 1..318 SANS AUCUN TROU et tous `configId` absent — donc
// aucune entree n'avait JAMAIS ete retiree, et toutes venaient de
// l'auto-inference `battle_event` ci-dessous.
//
// CAUSE de la derive, corrigee ici : la comptabilite etait ASYMETRIQUE. La
// CREATION s'inferait toute seule (premier `battle_event` d'un runnerId
// inconnu), la MORT non — le chemin de dispose que TOUS les agents empruntent
// est la RPC `disposeRunner` via `POST /api/scripts/:id/rpc`, un passe-plat que
// le host ne relisait pas. Les seuls retraits cablés etaient
// `DELETE /api/runners/:id` (front), `POST /api/runners/sync` (front, manuel),
// `pruneRunnersBySession` (mort de session) et le `runner_disposed` emis par
// `recorder.ts` — qui ne concerne QUE les runners `autoDispose !== false`,
// c'est-a-dire jamais ceux des agents RL. La symetrie est retablie dans
// `rpcCall` (`host/sessions.ts`), au MEME point de passage unique que la porte
// de drain, et un reconciliateur periodique (`host/runner-reconcile.ts`) rattrape
// tout chemin de mort qui apparaitrait plus tard.
//
// COUT MESURE de la derive (2026-07-31), au cas ou elle serait relue comme
// cosmetique : 320 repertoires / 1147 fichiers / 455 Mo de dumps matchState
// sous `frida/logs/runs/`, que `removeRunner` aurait effaces au fil de l'eau.
// ---------------------------------------------------------------------------
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

/** Taille du cache host. Diagnostic UNIQUEMENT — ce n'est pas une jauge de
 *  capacite : le cap `MAX_RUNNERS` se lit cote hooks (cf. l'en-tete). */
export function countRunners(): number {
    return runners.size;
}

/** Le cache host connait-il cet id ? Utilise par `DELETE /api/runners/:id` pour
 *  rapporter honnetement ce qu'il a trouve, la purge nominale ayant desormais
 *  lieu en amont dans `rpcCall`. */
export function hasRunner(runnerId: number): boolean {
    return runners.has(runnerId);
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
 * host entries tied to vanished runnerIds are stale and their ids must go.
 *
 * `createdBefore` FERME LA COURSE, et ce n'est pas theorique : `keep` est une
 * PHOTO du registre des hooks prise a un instant T, mais un autre agent peut
 * creer un runner a T+e et le host en apprendre l'existence (via `battle_event`)
 * avant que la purge ne s'execute. Sans borne, ce runner tout neuf — absent de
 * la photo parce qu'il n'existait pas encore — serait purge, et ses dumps
 * effaces sous les pieds de son proprietaire. On ne purge donc QUE les entrees
 * enregistrees AVANT la photo. Appelants : passer l'horodatage pris juste avant
 * l'appel `listRunners` des hooks. */
export async function pruneRunners(
    keep: Set<number>, createdBefore = Number.POSITIVE_INFINITY,
): Promise<number[]> {
    const removed: number[] = [];
    for (const [id, meta] of [...runners.entries()]) {
        if (!keep.has(id) && meta.startedAt < createdBefore) {
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
