// stack-sample — NOMMER une boucle native en échantillonnant les piles, sans rien muter.
//
// CE QUE ÇA RÉSOUT
// -----------------
// Un jeu qui « ne répond plus » se diagnostique par le CPU : delta NUL = thread bloqué,
// delta PLEIN = thread qui TOURNE EN ROND. Le second cas est le plus frustrant, parce qu'on
// sait qu'il boucle sans savoir OÙ. Mesuré le 2026-08-16 : l'IA d'une bataille montée en
// sandbox consommait ~150 % d'un cœur pendant 15 s sans qu'aucun indicateur d'état ne bouge,
// et il a fallu deviner entre trois candidats (`PickNextUnit`, l'évaluation d'une ability, un
// compteur de passif). Ce module remplace la devinette par une mesure.
//
// ⚠⚠ CE RPC NE PASSE **PAS** PAR `queueOnMainThread`, ET C'EST TOUT LE POINT
// ---------------------------------------------------------------------------
// La règle habituelle du dépôt est d'exécuter sur le thread principal. Ici c'est l'inverse :
// on veut mesurer un thread principal QUI NE REND PAS LA MAIN. Une exécution queued
// n'arriverait jamais — c'est exactement le piège inverse de celui de `loaderStatus`, où lire
// une réponse non queued avait été pris à tort pour une preuve de vie. Le non-queued est ici
// la SEULE voie qui fonctionne, et il est donc DÉLIBÉRÉ.
//
// ⚠ ON NE NOMME RIEN ICI, ET C'EST VOULU. `DebugSymbol.fromAddress` ne connaît pas les
// méthodes IL2CPP : il rendrait `GameAssembly.dll+0x53cf70`, ce qui n'apprend rien. Le module
// rend donc des ADRESSES BRUTES + la base du module, et c'est l'appelant Python qui les
// résout contre `data/symbols/<build>/ghidra/functions.tsv`. C'est la doctrine du dépôt : on
// cite un SYMBOLE, et la table qui le donne vit hors du process.
//
// ⚠ `Process.enumerateThreads()` suspend brièvement les threads. C'est incomparablement plus
// léger qu'un `Memory.scan` (le geste explicitement proscrit), et `UnityFreezeDetector` est
// désarmé sur ce build — mais on borne quand même : peu d'échantillons, intervalle court.

import { Ctx } from "../controller.js";

const MODULE_IL2CPP = "GameAssembly.dll";

interface Trame { adresse: string; module: string | null; decalage: number | null }
interface Echantillon { thread: number; etat: string; trames: Trame[] }

/** Une pile, en adresses. `FUZZY` parce que le code IL2CPP n'a pas de frame pointer fiable :
 *  `ACCURATE` rend le plus souvent une pile d'une seule trame. */
function pile(contexte: CpuContext, profondeur: number): Trame[] {
    let brut: NativePointer[];
    try { brut = Thread.backtrace(contexte, Backtracer.FUZZY).slice(0, profondeur); }
    catch { return []; }
    return brut.map((a) => {
        let mod: string | null = null;
        let dec: number | null = null;
        try {
            const m = Process.findModuleByAddress(a);
            if (m) { mod = m.name; dec = a.sub(m.base).toInt32(); }
        } catch { /* best effort */ }
        return { adresse: a.toString(), module: mod, decalage: dec };
    });
}

export function register(ctx: Ctx): void {

    /** Échantillonne les piles de TOUS les threads, N fois.
     *
     *  body: { echantillons?: number (defaut 6), profondeur?: number (defaut 24),
     *          seulementActifs?: boolean (defaut true) }
     *
     *  Retour : un lot par échantillon + la base des modules, pour que l'appelant resolve.
     *  Rien n'est nomme ici (cf. l'en-tete). LECTURE PURE : aucune ecriture, aucun hook. */
    ctx.rpc.stackSample = (body?: {
        echantillons?: number; profondeur?: number; seulementActifs?: boolean;
    }): unknown => {
        const n = Math.max(1, Math.min(20, body?.echantillons ?? 6));
        const prof = Math.max(4, Math.min(64, body?.profondeur ?? 24));
        const actifsSeuls = body?.seulementActifs !== false;

        let base: string | null = null;
        let taille: number | null = null;
        try {
            const m = Process.findModuleByName(MODULE_IL2CPP);
            if (m) { base = m.base.toString(); taille = m.size; }
        } catch { /* best effort */ }

        const lots: Echantillon[][] = [];
        for (let i = 0; i < n; i++) {
            const lot: Echantillon[] = [];
            let threads: ThreadDetails[];
            try { threads = Process.enumerateThreads(); }
            catch (e) {
                return { ok: false, error: "enumerateThreads a levé : " + (e as Error).message };
            }
            for (const t of threads) {
                if (actifsSeuls && t.state !== "running") continue;
                lot.push({ thread: t.id, etat: t.state, trames: pile(t.context, prof) });
            }
            lots.push(lot);
        }

        // Quels threads reviennent, et avec quelles trames RÉCURRENTES ? Une boucle se
        // reconnaît à une adresse qui revient dans tous les échantillons du même thread.
        const parThread: Record<number, { etats: string[]; compte: Record<string, number> }> = {};
        for (const lot of lots) {
            for (const e of lot) {
                const p = parThread[e.thread] ?? { etats: [], compte: {} };
                p.etats.push(e.etat);
                for (const t of e.trames) {
                    p.compte[t.adresse] = (p.compte[t.adresse] ?? 0) + 1;
                }
                parThread[e.thread] = p;
            }
        }
        const recurrents = Object.entries(parThread).map(([id, p]) => ({
            thread: Number(id),
            vuFois: p.etats.length,
            etats: Array.from(new Set(p.etats)),
            // les adresses vues dans AU MOINS la moitié des échantillons de ce thread
            adressesRecurrentes: Object.entries(p.compte)
                .filter(([, c]) => c >= Math.ceil(p.etats.length / 2))
                .sort((a, b) => b[1] - a[1])
                .slice(0, 24)
                .map(([a, c]) => ({ adresse: a, fois: c })),
        })).sort((a, b) => b.vuFois - a.vuFois);

        return {
            ok: true,
            moduleIl2cpp: MODULE_IL2CPP,
            base, taille,
            echantillons: n, profondeur: prof, seulementActifs: actifsSeuls,
            threadsVus: Object.keys(parThread).length,
            recurrents,
            lots,
            note: "adresses BRUTES -- les resoudre contre data/symbols/<build>/ghidra/"
                + "functions.tsv (VA = 0x180000000 + (adresse - base))",
        };
    };
}
