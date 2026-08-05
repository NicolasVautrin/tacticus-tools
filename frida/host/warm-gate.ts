// PORTE DE WARMUP — aucun runner ne se cree sur une session qui n'a pas ete
// warmee DEPUIS SON INJECTION.
//
// POURQUOI (#285-r1). Le `CLAUDE.md` porte depuis longtemps une REGLE
// INCONDITIONNELLE : « warmup apres CHAQUE (re)inject, AVANT tout RPC/probe,
// sans exception ». Elle n'etait ecrite NULLE PART en code. Le 2026-08-05 elle a
// ete violee par le harnais lui-meme, pas par un humain distrait :
//
//   1. fenetre de maintenance -> drain ARME, `liveRunners` tombe a 0 ;
//   2. restart du host — et le drain vit EN MEMOIRE, donc il repart a `false` ;
//   3. l'auto-restore (`restoreSessions`) re-attache et REINJECTE, mais ne warme
//      PAS (seul `POST /api/admin/inject` enchaine le warmup) ;
//   4. entre 3. et le warmup manuel, la creation de runners etait ROUVERTE sur
//      une session FROIDE. Trois `initAndStart` d'un agent y sont passes.
//
// Ils ont rendu `started: true`. C'est exactement le piege que la regle vise :
// « un probe qui MARCHE sans warmup ne prouve rien » — il marche quand le jeu est
// chaud par chance, et au prochain demarrage froid c'est le crash `0x2c`
// (metadata IL2CPP non initialisee). Le cout reel a ete de jeter trois runners
// et les mesures qu'ils portaient.
//
// ---------------------------------------------------------------------------
// LA PORTE WARME, ELLE NE REFUSE PAS. C'est le choix central de ce module.
//
// Refuser aurait rendu l'invariant VISIBLE, pas TENU : un agent qui recoit un
// refus doit warmer lui-meme, ce que le `CLAUDE.md` lui INTERDIT (invariant 4 —
// le harnais appartient a l'orchestrateur). On aurait remplace une mesure
// silencieusement fausse par un blocage franc de toute la flotte, en attendant
// un geste humain. Warmer a la demande supprime le mode d'erreur au lieu de le
// signaler : la premiere creation qui arrive sur une session froide DECLENCHE le
// warmup, l'attend, puis passe. Dans l'incident ci-dessus, les trois runners
// auraient ete construits chauds sans que personne n'intervienne.
//
// On ne REFUSE que si le warmup lui-meme ECHOUE — la, il n'y a plus de bon
// resultat possible, et le refus NOMME sa cause.
//
// ---------------------------------------------------------------------------
// TROIS PROPRIETES QUI COMPTENT, ET POURQUOI.
//
// * COUP UNIQUE PAR SESSION. Le warmup pilote l'UI du jeu (campagne -> node ->
//   play -> capture -> retour campagne, ~12 s). Le rejouer devant chaque
//   creation perturberait les runners deja en place. L'etat est donc memorise
//   PAR sessionId, et un id ne se recycle pas (`nextSessionId++`).
//
// * FILE UNIQUE (single-flight). Quatre agents qui buildent en parallele sur une
//   session froide ne doivent declencher QU'UN warmup : les trois autres
//   attendent la MEME promesse. Sans cela on lancerait quatre navigations UI
//   concurrentes dans le meme process — de quoi casser le jeu, pas le sauver.
//
// * LE REFUS N'EMPRUNTE PAS LE MARQUEUR DU DRAIN. `DRAIN_MARKER` a un contrat
//   cote Python (`rl_collect_batch._rpc`, `tests/conftest.py`) : il veut dire
//   « temporaire, ATTENDS ». Une session froide, elle, ne se rechauffe pas toute
//   seule pendant qu'on patiente : reutiliser ce marqueur ferait boucler le
//   client jusqu'a son plafond sur une cause qui ne bouge pas. Le message porte
//   donc son propre marqueur, et il dit quoi faire.

/** Sous-chaine STABLE presente dans tout refus de warmup. Distincte de
 *  `DRAIN_MARKER` A DESSEIN (cf. l'en-tete) : celui-ci veut dire « attends », le
 *  notre veut dire « le warmup a echoue, va le lire ». */
export const WARM_GATE_MARKER = "warmup required";

/** ASCII STRICT — ce texte finit dans un `print`/`stderr` Python sur une console
 *  Windows cp1252, ou tout non-ASCII leve `UnicodeEncodeError` et fait CRASHER
 *  le script appelant. Meme contrainte que `drain.ts`, meme raison. */
function refusalMessage(method: string, cause: string): string {
    return (
        `${WARM_GATE_MARKER} -- creation '${method}' refusee : la session n'a pas `
        + "ete warmee depuis son injection, et le warmup automatique a ECHOUE "
        + `(${cause}). Un runner monte sur une session froide ne prouve rien `
        + "(caches MethodInfo* vides, init IL2CPP non amorcee -> crash 0x2c au "
        + "prochain demarrage froid). Diagnostiquer par POST /api/admin/warmup, "
        + "qui rend le detail etape par etape. Echappatoire consciente : "
        + "TACTICUS_ALLOW_COLD_RUNNER=1 cote host."
    );
}

export class ColdSessionError extends Error {
    constructor(message: string) {
        super(message);
        this.name = "ColdSessionError";
    }
}

export function isColdSessionRefusal(e: unknown): e is ColdSessionError {
    return e instanceof ColdSessionError;
}

interface WarmRecord {
    at: string;
    /** Comment la session a ete declaree chaude — `auto` (par cette porte),
     *  `observed` (un warmup a reussi par une autre voie : /api/admin/inject,
     *  /api/admin/warmup, ou un appelant direct du RPC). Sert au diagnostic :
     *  un parc entierement `auto` signifierait que plus personne ne warme
     *  explicitement, donc que la porte est devenue le seul filet. */
    how: "auto" | "observed";
}

const warmed = new Map<number, WarmRecord>();
const inFlight = new Map<number, Promise<void>>();

let autoWarmups = 0;
let autoWarmupFailures = 0;

/** Nom du RPC de warmup, cote hooks. Un seul point de verite ici : la porte le
 *  DECLENCHE et le RECONNAIT, les deux doivent parler du meme. */
export const WARMUP_METHOD = "warmupGameSingletons";

export function isWarmed(sessionId: number): boolean {
    return warmed.has(sessionId);
}

/** Appelee quand un warmup a REUSSI, d'ou qu'il vienne. */
export function markWarmed(sessionId: number, how: "auto" | "observed"): void {
    if (warmed.has(sessionId)) return;
    warmed.set(sessionId, { at: new Date().toISOString(), how });
    console.log(`[warm-gate] session ${sessionId} declaree CHAUDE (${how})`);
}

/** Une session qui meurt oublie son etat. Sans cela un id recycle (aucun
 *  aujourd'hui, `nextSessionId` ne recule pas — mais c'est une invariante de
 *  code, pas une loi) heriterait d'un « chaud » qui ne lui appartient pas. */
export function forgetSession(sessionId: number): void {
    warmed.delete(sessionId);
    inFlight.delete(sessionId);
}

export function getWarmState(): {
    warmed: Array<{ sessionId: number; at: string; how: string }>;
    pending: number[];
    autoWarmups: number;
    autoWarmupFailures: number;
    escapeHatch: boolean;
} {
    return {
        warmed: [...warmed.entries()].map(([sessionId, r]) => ({
            sessionId, at: r.at, how: r.how,
        })),
        pending: [...inFlight.keys()],
        autoWarmups,
        autoWarmupFailures,
        escapeHatch: process.env.TACTICUS_ALLOW_COLD_RUNNER === "1",
    };
}

/**
 * LECTURE DU RESULTAT D'UN WARMUP — symetrique de `noteRunnerDeath` : le host
 * apprend l'etat en RELISANT la RPC qui vient de reussir, au lieu de le deduire
 * de la route empruntee.
 *
 * Pose au point de passage unique (`rpcCall`), donc les TROIS voies de warmup
 * marquent la session sans une ligne de code chez elles : le warmup enchaine par
 * `POST /api/admin/inject`, `POST /api/admin/warmup`, et l'appel direct au RPC
 * (ce que font les probes Python). Une regle posee route par route en aurait
 * manque au moins une — c'est precisement comment ce trou est ne.
 *
 * `{ ok: true, skipped: "already-ready" }` COMPTE comme un warmup reussi : c'est
 * la reponse du RPC quand les singletons sont deja captures, pas un echec.
 */
export function noteRpcResult(sessionId: number, method: string, out: unknown): void {
    if (method !== WARMUP_METHOD) return;
    // Le warmup DECLENCHE PAR LA PORTE passe aussi par ici (il emprunte `rpcCall`
    // pour heriter du timeout et de la file). Le laisser marquer « observed »
    // ferait mentir le diagnostic : un parc entierement `auto` doit rester
    // lisible comme tel. La porte marque elle-meme son propre warmup.
    if (inFlight.has(sessionId)) return;
    const ok = !!(out && typeof out === "object"
        && (out as { ok?: unknown }).ok === true);
    if (ok) markWarmed(sessionId, "observed");
}

/**
 * LA PORTE. Appelee par `rpcCall` pour les seules methodes de CREATION.
 *
 * `runWarmup` est injecte par l'appelant plutot qu'importe ici : `sessions.ts`
 * importe ce module, donc l'inverse ferait un cycle. C'est aussi ce qui rend la
 * porte testable sans Frida.
 */
export async function ensureWarmForCreation(
    sessionId: number,
    method: string,
    runWarmup: (sessionId: number) => Promise<unknown>,
): Promise<void> {
    if (warmed.has(sessionId)) return;

    if (process.env.TACTICUS_ALLOW_COLD_RUNNER === "1") {
        // Echappatoire CONSCIENTE, et bruyante : elle ne doit jamais devenir le
        // regime normal sans que quelqu'un le lise dans les logs.
        console.log(`[warm-gate] session ${sessionId} FROIDE mais `
            + `TACTICUS_ALLOW_COLD_RUNNER=1 -- '${method}' passe SANS warmup`);
        return;
    }

    const already = inFlight.get(sessionId);
    if (already) {
        // File unique : on attend LE warmup en cours, on n'en lance pas un second.
        await already;
        if (!warmed.has(sessionId)) {
            throw new ColdSessionError(refusalMessage(
                method, "un warmup concurrent a echoue"));
        }
        return;
    }

    console.log(`[warm-gate] session ${sessionId} FROIDE -- warmup automatique `
        + `declenche par '${method}'`);
    autoWarmups += 1;
    const p = (async () => {
        const out = await runWarmup(sessionId);
        const ok = !!(out && typeof out === "object"
            && (out as { ok?: unknown }).ok === true);
        if (ok) markWarmed(sessionId, "auto");
        else {
            throw new Error(`le RPC ${WARMUP_METHOD} a rendu ok=false: `
                + `${JSON.stringify(out).slice(0, 200)}`);
        }
    })();
    inFlight.set(sessionId, p.catch(() => { /* relaye ci-dessous */ }));
    try {
        await p;
    } catch (e) {
        autoWarmupFailures += 1;
        const cause = (e as Error).message || String(e);
        console.log(`[warm-gate] warmup automatique ECHOUE (session ${sessionId}): `
            + cause);
        throw new ColdSessionError(refusalMessage(method, cause));
    } finally {
        inFlight.delete(sessionId);
    }
}
