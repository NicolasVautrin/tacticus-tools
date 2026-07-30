// Reconciliation PERIODIQUE du cache host des runners contre le registre des
// hooks — le FILET de #321, pas le correctif principal.
//
// Le correctif principal est dans `sessions.ts` (`rpcCall` purge le cache quand
// un `disposeRunner` reussit). Il couvre le chemin de mort que tout le monde
// emprunte aujourd'hui. Ce module couvre les AUTRES, y compris ceux qui
// n'existent pas encore : c'est exactement la fragilite que `drain.ts` documente
// pour sa liste noire (« si une methode apparait un jour sans etre ajoutee ici,
// le drain FUIT »). Une liste de chemins de mort a maintenir a la main
// re-ouvrirait la meme derive silencieuse ; une convergence periodique vers
// l'AUTORITE, non.
//
// L'AUTORITE est le registre des hooks (`frida/hooks/game/runner-registry.ts`),
// interroge par la RPC `listRunners`. Elle est bon marche : cote hooks c'est une
// lecture de Map en JS, NON queuee sur le main thread Unity (cf.
// `ctx.rpc.listRunners` dans `frida/hooks/features/launch.ts`) — elle ne dispute
// pas le debit de la pompe aux agents en vol.
//
// TRI-ETAT ASSUME, meme discipline que `host_inputs.py` (#273) et que la jauge
// de drain (#285) : « je n'ai pas pu compter » n'est JAMAIS « il n'y a rien ».
//   - aucune session vivante          -> on ne purge RIEN (on ne sait pas)
//   - RPC en echec / reponse inattendue -> on ne purge RIEN
//   - reponse valide                  -> on purge, borne par l'horodatage de la
//                                        photo (cf. `pruneRunners`)
// Le contre-exemple a ne pas reproduire est `POST /api/runners/sync`, qui purge
// TOUT quand il n'y a pas de session : correct pour un geste MANUEL du front
// (l'utilisateur sait ce qu'il fait), faux pour un timer qui pourrait tomber
// pendant une fenetre de reattache.

import { pruneRunners, countRunners } from "./battle-store.js";
import { pickLiveSessionId, rpcCall } from "./sessions.js";

/** Periode de reconciliation. Volontairement lache : le chemin nominal est deja
 *  ferme par `rpcCall`, ce timer ne rattrape qu'un chemin de mort inconnu. */
const RECONCILE_INTERVAL_MS = 60_000;

/** Au-dela de ce nombre d'entrees en cache, on le DIT a chaque passe meme si
 *  rien n'est purgeable. Un cache qui gonfle alors que la reconciliation tourne
 *  signale un runner reellement vivant en surnombre (la ce serait une vraie
 *  alerte capacite) ou une purge empechee — dans les deux cas, il faut le voir.
 *  Reference : `MAX_RUNNERS` vaut 50 cote hooks ; on laisse une marge large pour
 *  ne pas bruiter les passes normales. */
const LOUD_ABOVE = 120;

let timer: ReturnType<typeof setInterval> | null = null;
let lastErrorLogged: string | null = null;

/** Une passe. Exportee pour etre declenchable / testable hors du timer.
 *  Ne leve jamais : c'est de l'hygiene de fond, pas un chemin fonctionnel. */
export async function reconcileOnce(): Promise<{
    /** null = PAS MESURE (pas de session, ou RPC KO) — jamais 0 par defaut. */
    hooksCount: number | null;
    hostCount: number;
    removed: number[];
    error: string | null;
}> {
    const hostCount = countRunners();
    const sid = pickLiveSessionId();
    if (sid == null) {
        return { hooksCount: null, hostCount, removed: [], error: "aucune session Frida vivante" };
    }
    // Photo PRISE AVANT l'appel : tout runner enregistre cote host apres cet
    // instant est hors du champ de la purge (cf. `pruneRunners`).
    const snapshotAt = Date.now();
    let live: Array<{ runnerId: number }>;
    try {
        live = await rpcCall(sid, "listRunners", [], 5000) as Array<{ runnerId: number }>;
    } catch (e) {
        const error = (e as Error).message;
        if (error !== lastErrorLogged) {
            console.log(`[runner-reconcile] listRunners KO — AUCUNE purge: ${error}`);
            lastErrorLogged = error;
        }
        return { hooksCount: null, hostCount, removed: [], error };
    }
    if (!Array.isArray(live)) {
        return {
            hooksCount: null, hostCount, removed: [],
            error: "reponse listRunners inattendue",
        };
    }
    lastErrorLogged = null;
    const keep = new Set(live.map((r) => r.runnerId));
    const removed = await pruneRunners(keep, snapshotAt);
    if (removed.length > 0) {
        console.log(
            `[runner-reconcile] ${removed.length} entree(s) host orpheline(s) purgee(s) `
            + `(hooks=${keep.size}, host=${hostCount} -> ${countRunners()}). `
            + "Un chemin de mort de runner n'a pas prevenu le host — cf. #321, "
            + "noteRunnerDeath dans host/sessions.ts. ids: "
            + removed.slice(0, 20).join(", ")
            + (removed.length > 20 ? ", ..." : ""));
    } else if (countRunners() > LOUD_ABOVE) {
        console.log(
            `[runner-reconcile] cache host = ${countRunners()} entrees, hooks = ${keep.size}, `
            + "rien a purger. Ce sont donc des runners VIVANTS cote hooks : "
            + "verifier que les agents disposent bien les leurs.");
    }
    return { hooksCount: keep.size, hostCount, removed, error: null };
}

export function startRunnerReconciler(intervalMs = RECONCILE_INTERVAL_MS): void {
    if (timer) return;
    timer = setInterval(() => { void reconcileOnce(); }, intervalMs);
    // Ne retient pas la boucle d'evenements : le host doit pouvoir sortir.
    timer.unref?.();
    console.log(`[runner-reconcile] actif (toutes les ${Math.round(intervalMs / 1000)} s)`);
}

export function stopRunnerReconciler(): void {
    if (!timer) return;
    clearInterval(timer);
    timer = null;
}
