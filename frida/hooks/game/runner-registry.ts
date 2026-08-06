// Registry of IdunRunner instances we built ourselves (Phase 3 launches).
// Keyed by an auto-increment runnerId that the host uses to address subsequent
// actions (apply, startMatch, query, dispose) on a specific runner.
//
// Wording: "runner" by default means one of our managed runners in this
// registry. The game's own runner instance (created when the user enters a
// real battle) is explicitly called "liveRunner" (see game/state.ts).
//
// Pinned-refs tracking: every transient IL2CPP allocation we keep alive
// across an in-progress runner cycle (BC config, AddUnit/StartBattle/
// CheatRunAI messages, …) is registered against the owning runner via
// `pinForRunner`. `disposeRunner` then unpins all of them in one shot.
//
// L'en-tête annonçait ici « ~100 pins par bataille, `IdunRunner.Initialize`
// échoue au-delà de ~900 » — chiffre écrit le 2026-05-24, jamais re-mesuré.
// MESURÉ le 2026-07-26 (probe_132_gcroot_budget.py) : le coût réel est de
// **3 handles par bataille**, et un build réussit avec **5004 handles
// épinglés**. Le dépinglage groupé reste la bonne hygiène ; il ne protège
// simplement pas d'un mur qui n'existe pas. Voir MAX_RUNNERS ci-dessous.

import { RunnerHandle } from "./runner.js";
import { gcRoot } from "../il2cpp/gc-root.js";
import { purgeTracesForRunner } from "./trace-origin.js";
import { purgeArmedForRunner } from "./armed-runners.js";

interface Entry extends RunnerHandle {
    runnerId: number;
    started: boolean;
    /** When false, recorder.ts must NOT auto-evict this runner on its
     *  match-end heuristic — it is lifecycle-managed by its driver (explicit
     *  `disposeRunner`). Set for RL/isolated runners (initRunner / initAndStart
     *  / buildPatchedRunner) so a CONCURRENT build can't evict a sibling runner
     *  mid-use (TF06). UI / mirror-replay runners keep the default (true). */
    autoDispose: boolean;
    /** Étiquette libre du PROPRIÉTAIRE, fournie par le constructeur (chemin de
     *  state-file, nom d'agent, id de test…). Sert à la purge SÛRE des runners
     *  orphelins : sans elle, le registre ne dit pas à qui appartient un runner,
     *  et le seul critère disponible — l'âge — condamne un runner légitime d'un
     *  agent lent aussi vite qu'un orphelin. null quand l'appelant ne l'a pas
     *  renseignée (les anciens appelants restent valides). */
    owner: string | null;
    /** Horodatage de l'enregistrement (ms). Diagnostic — JAMAIS un critère de
     *  purge à lui seul, cf. `owner`. */
    createdAt: number;
    /** Pointers added via `pinForRunner` — all unpinned by `disposeRunner`. */
    pinnedRefs: NativePointer[];
}

// ⚠ INVARIANT — `counter` est STRICTEMENT MONOTONE : jamais remis à zéro, jamais
// décrémenté, et `disposeRunner` ne range l'id dans AUCUNE free-list. Un id disposé
// reste donc libre pour toujours (dans la session), et c'est ce qui rend IMPOSSIBLE
// le mode d'échec le plus coûteux du harnais : un agent qui pilote un id périmé se
// fait REFUSER par `getRunner` (`runner N not found`) au lieu d'atterrir en silence
// sur le runner d'un autre — lequel ne verrait ni erreur ni refus, seulement un état
// de bataille qui a avancé tout seul, et accuserait SON port.
// Ne pas « recycler les ids pour qu'ils ne gonflent pas ». Cliquet :
// `scripts/python/probe_377_runnerid_reuse.py` (I1..I5) — cf. docs/rl/case-377.
const byId = new Map<number, Entry>();
let counter = 0;

/** Plafond dur de runners CONCURRENTS. Remplace l'ancien défaut « un seul build,
 *  dispose-all » d'`initAndStart` (qui nukait silencieusement les runners
 *  parallèles en vol — TF06). Au-delà, les RPC de build REFUSENT explicitement :
 *  chaque appelant possède ses runners et les dispose en fin de passe.
 *
 *  VALEUR MESURÉE, pas héritée (2026-07-26, probe_132_gcroot_budget.py) :
 *  ce plafond a longtemps valu 10 parce qu'il était dérivé du budget de handles
 *  annoncé en en-tête (« ~100 pins par bataille, échec au-delà de ~900 »). Les
 *  trois manips ont réfuté cette dérivation :
 *    - coût RÉEL = **3 handles par bataille**, dérive nulle sur 12 cycles ;
 *    - un build RÉUSSIT avec **5004 handles épinglés** et une seule bataille
 *      vivante (lest `gcPin`, qui découple enfin handles et batailles) ;
 *    - la latence d'un `decisionView` est PLATE de 1 à 10 runners vivants
 *      (0,173 s → 0,120 s) : un runner vivant NON PILOTÉ ne coûte pas de temps.
 *  La seule grandeur qui borne vraiment est la MÉMOIRE : ~3,6 Mo de tas managé
 *  par runner vivant. À 50, cela fait ~180 Mo — négligeable devant les ~290 Mo
 *  de tas managé déjà en place. La ressource partagée qui reste est le DÉBIT de
 *  la pompe Unity, mais elle se consomme en PILOTANT, pas en existant. */
export const MAX_RUNNERS = 50;

export function registerRunner(
    h: RunnerHandle, opts?: { autoDispose?: boolean; owner?: string },
): Entry {
    const e: Entry = { ...h, runnerId: ++counter, started: false,
                       autoDispose: opts?.autoDispose !== false,
                       owner: typeof opts?.owner === "string" && opts.owner
                           ? opts.owner : null,
                       createdAt: Date.now(),
                       pinnedRefs: [] };
    byId.set(e.runnerId, e);
    return e;
}

export function getRunner(runnerId: number): Entry {
    const e = byId.get(runnerId);
    if (!e) throw new Error(`runner ${runnerId} not found`);
    // PAS de side effect trace-origin ici : getRunner est aussi appelé
    // depuis des callbacks de hooks (recorder) et des RPCs non-queués
    // (disposeRunner, thread RPC) — un set ambiant taignerait l'attribution.
    // L'origine est posée EXPLICITEMENT par les RPCs de pilotage
    // (cf. game/trace-origin.ts).
    return e;
}

export function listRunners(): Array<{
    runnerId: number; started: boolean; seed: number;
    owner: string | null; createdAt: number; recordReplay: boolean;
}> {
    return [...byId.values()].map((e) => ({
        runnerId: e.runnerId,
        started: e.started,
        seed: e.seed,
        owner: e.owner,
        createdAt: e.createdAt,
        // #477-r1 : sans lui, un `replayOutputStream` vide ne se distingue pas
        // d'une bataille qui n'aurait rien produit.
        recordReplay: e.recordReplay === true,
    }));
}

/** Pin a transient managed object against IL2CPP GC and register it as
 *  owned by `runnerId`. `disposeRunner(runnerId)` will unpin it. Caller
 *  must not pass the runner pointer itself — that's pinned + unpinned
 *  separately via the registry life-cycle. */
export function pinForRunner(runnerId: number, ptr: NativePointer): void {
    if (ptr.isNull()) return;
    const e = byId.get(runnerId);
    if (!e) {
        // Runner gone — pin globally (won't leak much since no further
        // resources will be attached). Better than swallowing silently.
        gcRoot.add(ptr);
        return;
    }
    gcRoot.add(ptr);
    e.pinnedRefs.push(ptr);
}

/** Un-pin the runner + every transient managed object registered against
 *  it, then remove from registry. */
export function disposeRunner(runnerId: number): boolean {
    const e = byId.get(runnerId);
    if (!e) return false;
    try { gcRoot.remove(e.runner); } catch { /* best effort */ }
    for (const p of e.pinnedRefs) {
        try { gcRoot.remove(p); } catch { /* best effort */ }
    }
    e.pinnedRefs.length = 0;
    // Drop les buckets de traces diagnostiques du runner mort (scorer /
    // aiUtilityTrace / bucketAudit) — même hygiène que purgeLogForOrigin
    // côté recorder. cf. game/trace-origin.ts.
    try { purgeTracesForRunner(runnerId); } catch { /* best effort */ }
    // ... et son ARMEMENT (#483). Sans ça, un runner mort laisserait sa porte
    // ouverte pour toujours : `anyArmed()` resterait vrai et les Interceptor des
    // features à détachement paresseux (hit-trace, bucket-audit) ne se
    // détacheraient jamais. cf. game/armed-runners.ts.
    try { purgeArmedForRunner(runnerId); } catch { /* best effort */ }
    return byId.delete(runnerId);
}
