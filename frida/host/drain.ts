// Mode DRAIN — refuser la CREATION de runner, laisser vivre ceux DEJA EN PLACE.
//
// POURQUOI (#285). Ouvrir une fenetre de reinject/restart-host exige zero runner
// en vol. Sans drain, la seule voie etait de REVEILLER chaque agent pour lui
// demander d'arreter — 300-600 K tokens de rejeu de contexte par agent, pour une
// fenetre de deux minutes. Le drain inverse la charge : on refuse les CREATIONS,
// les runners existants finissent leur passe et se disposent au fil de l'eau, et
// le compte tombe a zero tout seul. Personne n'est reveille.
//
// ---------------------------------------------------------------------------
// PORTEE VOLONTAIREMENT ETROITE : liste NOIRE de la creation, jamais liste
// BLANCHE du monitoring.
//
// Tout ce qui PILOTE ou OBSERVE un runner deja en place continue de passer :
// `battleStatus`, `decisionView`, `observeBattle`, `combatSnapshot`,
// `applyAction`, `aiDryRunAllUnits`, `dumpRng`, `listRunners`, `playTurn`...
// et surtout `disposeRunner`, SANS QUOI LE DRAIN NE CONVERGERAIT JAMAIS vers
// zero — c'est la dispose des agents qui fait descendre le compte.
//
// Le choix liste-noire est deliberé et il a un cout assume : si une methode de
// creation apparait un jour sans etre ajoutee ici, le drain FUIT (elle passe).
// L'echec symetrique d'une liste blanche serait de CASSER LE MONITORING au
// moindre RPC oublie — c'est-a-dire de casser le travail des agents en vol, ce
// que le drain est precisement cense eviter. Entre fuir et casser, on fuit.
//
// ---------------------------------------------------------------------------
// LA LISTE, DERIVEE DU CODE ET NON DEVINEE.
//
// Cote hooks, UN SEUL point cree une entree de runner : `registerRunner`
// (frida/hooks/game/runner-registry.ts). Ses quatre appelants sont exactement :
//
//   initRunner           frida/hooks/features/launch.ts
//   initAndStart         frida/hooks/features/launch.ts
//   loadFromSavedBundle  frida/hooks/features/launch.ts
//   buildPatchedRunner   frida/hooks/features/battle-config.ts
//
// `simBuildPreview` est le CINQUIEME, a part : il construit un runner natif de
// preview qui n'entre PAS au registre (slot unique `state.previewRunner`, rendu
// par `simDisposePreview`). Il est refuse lui aussi — c'est une creation, et un
// reinject le detruirait pareil — mais il ne pese pas sur `listRunners`, donc il
// ne compte pas dans la convergence vers zero.
//
// Pour re-deriver cette liste apres une evolution des hooks :
//   grep -n "registerRunner(" frida/hooks
// puis remonter au `ctx.rpc.<nom>` englobant.

/** Sous-chaine STABLE presente dans tout refus de drain.
 *
 * C'est le contrat avec le client Python : `scripts/python/tests/conftest.py`
 * la cherche pour (a) ATTENDRE qu'un slot se libere au lieu d'abandonner, et
 * (b) convertir en ECHEC ROUGE un `pytest.skip` qui l'invoquerait — un skip vert
 * sur harnais indisponible est le faux negatif le plus couteux du projet.
 * La changer ici SANS la changer la-bas casse silencieusement les deux
 * comportements : c'est une constante partagee, pas un libelle cosmetique. */
export const DRAIN_MARKER = "runner creation paused";

/** Methodes RPC qui CREENT un runner. Cf. l'en-tete pour la derivation. */
const CREATION_METHODS = new Set([
    "initRunner",
    "initAndStart",
    "loadFromSavedBundle",
    "buildPatchedRunner",
    "simBuildPreview",
]);

export interface DrainRefusal {
    at: string;
    method: string;
}

export interface DrainState {
    enabled: boolean;
    message: string;
    retryAfterSec: number;
    since: string | null;
    /** Compteurs de refus — l'INSTRUMENT qui prouve que le message est bien
     * parti vers un appelant, au lieu de le supposer. Un drain arme qui
     * n'affiche aucun refus alors que des agents buildent signale un gate
     * contourne (chemin de creation hors liste), pas un calme plat. */
    refusedTotal: number;
    refusedByMethod: Record<string, number>;
    lastRefusals: DrainRefusal[];
}

const DEFAULT_RETRY_AFTER_SEC = 60;
const LAST_REFUSALS_KEPT = 20;

const state: DrainState = {
    enabled: false,
    message: "",
    retryAfterSec: DEFAULT_RETRY_AFTER_SEC,
    since: null,
    refusedTotal: 0,
    refusedByMethod: {},
    lastRefusals: [],
};

/** Erreur dediee : le routeur la distingue pour repondre 503 + `Retry-After`
 * plutot que le 500 generique. Le CORPS reste `{ error: <message> }`, forme que
 * tous les appelants Python savent deja lire (`resp.get("error")`). */
export class DrainRefusedError extends Error {
    readonly retryAfterSec: number;
    constructor(message: string, retryAfterSec: number) {
        super(message);
        this.name = "DrainRefusedError";
        this.retryAfterSec = retryAfterSec;
    }
}

export function isDrainRefusal(e: unknown): e is DrainRefusedError {
    return e instanceof DrainRefusedError;
}

/** ASCII STRICT — ce texte finit dans un `print`/`stderr` Python sur une console
 * Windows cp1252, ou tout non-ASCII leve `UnicodeEncodeError` et fait CRASHER le
 * script appelant. Un message de refus qui plante son lecteur est pire que pas
 * de message : il transforme un refus lisible en trace illisible. */
function buildMessage(retryAfterSec: number, custom?: string): string {
    if (custom && custom.trim()) return custom.trim();
    return (
        `${DRAIN_MARKER} (host en DRAIN) -- serveur momentanement indisponible, `
        + `reessayer dans ~${retryAfterSec} s. `
        + "Les runners DEJA EN PLACE restent pilotables et observables "
        + "(view / act / aiturn / decisionView / dispose) : seule la CREATION "
        + "est refusee, le temps d'une fenetre de maintenance. "
        + "Ne PAS relancer le host ni reinjecter -- attendre la levee."
    );
}

export function getDrainState(): DrainState {
    return {
        ...state,
        refusedByMethod: { ...state.refusedByMethod },
        lastRefusals: [...state.lastRefusals],
    };
}

export function setDrain(opts: {
    enabled: boolean;
    message?: string;
    retryAfterSec?: number;
}): DrainState {
    const retryAfterSec = typeof opts.retryAfterSec === "number"
        && Number.isFinite(opts.retryAfterSec) && opts.retryAfterSec > 0
        ? Math.round(opts.retryAfterSec)
        : DEFAULT_RETRY_AFTER_SEC;

    if (opts.enabled) {
        // Ré-armer un drain déjà armé ne remet pas `since` à zéro : on veut
        // savoir depuis quand la fenêtre dure, pas depuis le dernier POST.
        state.since = state.since ?? new Date().toISOString();
        state.enabled = true;
        state.retryAfterSec = retryAfterSec;
        state.message = buildMessage(retryAfterSec, opts.message);
    } else {
        state.enabled = false;
        state.since = null;
        state.message = "";
        state.retryAfterSec = retryAfterSec;
    }
    console.log(`[drain] ${state.enabled ? "ARME" : "leve"}`
        + (state.enabled ? ` (retryAfter=${state.retryAfterSec}s)` : "")
        + ` — refus cumules: ${state.refusedTotal}`);
    return getDrainState();
}

/** Remet les compteurs à zéro sans toucher à l'état armé/levé. */
export function resetDrainCounters(): DrainState {
    state.refusedTotal = 0;
    state.refusedByMethod = {};
    state.lastRefusals = [];
    return getDrainState();
}

/** Vrai si `method` cree un runner. Exporte pour que la garde puisse verifier
 * la liste sans la redupliquer. */
export function isCreationMethod(method: string): boolean {
    return CREATION_METHODS.has(method);
}

export function listCreationMethods(): string[] {
    return [...CREATION_METHODS].sort();
}

/**
 * Porte du drain, appelee par `rpcCall` — LE point de passage unique.
 *
 * Elle est posee dans `rpcCall` et non dans la route HTTP `/api/scripts/:id/rpc`
 * parce que plusieurs routes du host (`/api/launch`, la route de replay sim)
 * appellent `rpcCall` EN INTERNE sans repasser par HTTP : garder la porte au
 * niveau de la route les laisserait toutes passer. Durcir le point de passage,
 * pas les appelants.
 */
export function assertCreationAllowed(method: string): void {
    if (!state.enabled || !isCreationMethod(method)) return;
    state.refusedTotal += 1;
    state.refusedByMethod[method] = (state.refusedByMethod[method] ?? 0) + 1;
    state.lastRefusals.unshift({ at: new Date().toISOString(), method });
    if (state.lastRefusals.length > LAST_REFUSALS_KEPT) {
        state.lastRefusals.length = LAST_REFUSALS_KEPT;
    }
    console.log(`[drain] REFUS ${method} (total=${state.refusedTotal})`);
    throw new DrainRefusedError(state.message, state.retryAfterSec);
}
