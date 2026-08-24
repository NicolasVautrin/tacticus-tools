// sandbox-fenetre — LES RELAIS SANDBOX MEURENT AVEC LA BATAILLE QUI LES A OUVERTS.
//
// POURQUOI CE MODULE EXISTE
// --------------------------
// Un relais d'ecriture (`sandboxModeBcOverride`, `deploymentMemoire`, `deploymentClearArmer`...)
// n'attend pas qu'on le lui demande : il ECRIT TOUT SEUL a la prochaine bataille. Leur duree de
// vie etait celle de la SESSION, alors que leur raison d'etre est celle d'UNE bataille sandbox.
// Entre les deux, il n'y avait qu'un geste manuel — donc un geste OUBLIABLE, et il a deja coute
// un jeton de boss de guilde (l'ecran de deploiement d'une partie REELLE tombant sur des relais
// montes pour la sandbox).
//
// Mesure du 2026-08-24 : apres un montage `sandbox_boss.py`, la bataille finie, **14 relais
// d'ecriture etaient encore armes**, dont `sandboxModeBcOverride` — qui aurait substitue la BC
// de la premiere bataille reelle venue. Rien dans le systeme ne les eteignait.
//
// ⇒ On les arme A L'OUVERTURE de la fenetre (c'est le pilote qui le fait, il sait ce qu'il
//   monte) et on les eteint QUAND ELLE MEURT (c'est ici).
//
// OU EXACTEMENT, ET POURQUOI C'EST LE BON ENDROIT
// ------------------------------------------------
// Meme signal que `replay-fin-auto`, et pour la meme raison : la pompe lit
// `IdunGameViews._runner` a chaque frame. Une fermeture sondee de l'exterieur serait une COURSE,
// et la fenetre a fermer est precisement celle ou plus rien ne tourne pour sonder.
//
// QUATRE DECLENCHEURS, ET LE PRINCIPAL EST LE DERNIER
//   1. `stage -> Finished`       — la bataille va au bout ;
//   2. RUNNER MORT (`state` nul) — vu par la pompe, si elle vit encore assez longtemps ;
//   3. `_runner -> null`         — idem ;
//   4. POMPE DE BATAILLE ARRETEE — **c'est celui qui tire sur une retraite.**
// Le premier qui tire gagne ; les autres se taisent.
//
// ⛔ (1), (2) ET (3) SONT LUS DEPUIS `main-pump`, QUI REMPLACE `IdunGameViews.Update`. Quand la
// scene de bataille est demontee, `Update` cesse d'etre appele : l'observateur meurt avec ce
// qu'il devait observer. Mesure du 2026-08-24, retraite depuis la phase de deploiement -- la
// bataille est bien fermee (`IsBattleActive` FALSE) et nos appels sont GELES a 665. Ni
// `detachement`, ni un `state` nul, ni un `Finished` ne seront jamais vus : personne n'appelle
// plus.
//
// ⚠ ET C'EST `state.frameNo` QUI M'A FAIT ABANDONNER LE BON DIAGNOSTIC. Je l'ai regarde pour
// savoir si la pompe vivait : il avancait (+356 en 6 s), donc j'ai conclu qu'elle vivait, et
// j'ai bati un declencheur sur une autre theorie. Faux : `state.frameNo` est incremente par
// DEUX pompes, et c'est la pompe UI qui le faisait avancer. Le seul compteur qui repond a
// << la pompe qui M'APPELLE est-elle morte ? >> est celui que j'incremente MOI-MEME.
// ⇒ Pour mesurer qu'un appelant s'est arrete, compter SES appels -- jamais une horloge qu'il
//   partage avec quelqu'un d'autre.
//
// ⚠ ET LA FERMETURE N'A AUCUNE CONTRAINTE DE TIMING -- c'est ce qui rend un intervalle
// legitime ici alors qu'il serait faux pour une capture de replay. Le replay doit etre pris A LA
// FRAME (le runner disparait). Le desarmement, lui, doit seulement avoir lieu AVANT la prochaine
// bataille. Deux secondes de retard ne coutent rien ; ne jamais tirer coute un jeton.
//
// ⛔ LA LISTE DES RELAIS N'EST PAS ECRITE ICI, ET C'EST DELIBERE. Elle vit dans
// `scripts/python/relais_sandbox.py`, avec l'historique de chaque entree (dont deux RPC retires
// parce qu'ils n'existaient plus et faisaient rougir le garde a chaque passage). En tenir une
// SECONDE copie cote hook, c'est garantir qu'une des deux se perime en silence. Le pilote la
// PASSE a l'armement ; ce module ne fait qu'executer, au bon instant, ce qu'on lui a confie.
//
// ⚠ ET IL RELIT. Desarmer sans relire ne prouve rien : un RPC peut rendre `ok` sans avoir
// detache. Chaque relais est donc rappele en lecture apres coup, et son retour BRUT entre au
// bilan — c'est l'appelant qui juge, ce module ne rabat rien sur << desarme >>.

import { state } from "../game/state.js";
import { readBattleStatus } from "../game/match-state.js";
import { runnerOff } from "../game/runner.js";
import { Ctx } from "../controller.js";

/** Une frame sur 15 (~0,25 s a 60 fps) — meme cadence que `replay-fin-auto`. */
const PERIODE_FRAMES = 15;

interface Relais {
    /** Le nom du RPC, tel qu'il est enregistre dans `ctx.rpc`. */
    rpc: string;
    /** Le corps de DESARMEMENT. Toutes les formes ne sont pas `{armer:false}` :
     *  `sandboxModeBcOverride` veut `{configJson:null}`, `sandboxModeSeed` veut `{seed:null}`. */
    corps?: Record<string, unknown> | null;
}

interface LigneBilan {
    rpc: string;
    /** `null` = PAS MESURE (RPC absent, ou appel leve) — jamais lu comme un succes. */
    appele: boolean | null;
    err: string | null;
    /** Le retour BRUT de la relecture. C'est l'appelant qui en tire un verdict. */
    relu: unknown;
}

interface Bilan {
    raison: string;
    frameNo: number;
    lignes: LigneBilan[];
    /** Combien de RPC n'existaient pas — un relais renomme se lit ICI, pas dans un silence. */
    absents: number;
}

let arme = false;
let relais: Relais[] = [];
let ctxRef: Ctx | null = null;
/** La fenetre s'est-elle OUVERTE ? Sans ce garde, un armement pose hors bataille se fermerait
 *  sur le premier detachement venu — c'est-a-dire immediatement, et sur rien. */
let vuVivant = false;
let ferme = false;
let dernierStage: string | null = null;
let dernierBilan: Bilan | null = null;
/** Distingue « rien vu » de « jamais appele » — sans compteur, les deux se lisent pareil. */
let appelsSurveillance = 0;
let appelsDetachement = 0;
let dernierRefus: string | null = null;

// --- DECLENCHEUR 3 : LA POMPE S'ARRETE ---------------------------------------------------
/** Toutes les 2 s, hors frame du jeu. Le thread JS de Frida vit meme quand la scene est morte. */
const PERIODE_VEILLE_MS = 2000;
/** Deux tours SANS progression avant de conclure, pas un : une frame peut manquer (chargement,
 *  fenetre minimisee) sans que la scene soit morte. Fermer trop tot desarmerait une fenetre
 *  VIVANTE, ce qui est la panne symetrique et bien pire. */
const TOURS_SANS_FRAME_AVANT_FERMETURE = 2;
// `setInterval` ne rend PAS un `number` sous le typage Frida -- on prend le type qu'il rend.
let veille: ReturnType<typeof setInterval> | null = null;
/** ⛔ ON SURVEILLE `appelsSurveillance`, PAS `state.frameNo` -- ET C'EST TOUT LE SUJET.
 *
 *  `state.frameNo` est incremente par DEUX pompes : la principale (`IdunGameViews.Update`, qui
 *  seule nous appelle) et la pompe UI. Quand la scene de bataille meurt, la principale s'arrete
 *  et la seconde continue -- donc `frameNo` avance encore, et une veille batie dessus ne
 *  conclut JAMAIS. Mesure du 2026-08-24, apres retraite : nos appels GELES a 665, `frameNo`
 *  +356 en 6 s. Le seul compteur qui dit << la pompe qui m'appelle est morte >> est celui que
 *  J'INCREMENTE MOI-MEME. */
let derniereSurveillanceVue = -1;
let toursSansFrame = 0;

function arreterVeille(): void {
    if (veille !== null) { clearInterval(veille); veille = null; }
}

function demarrerVeille(): void {
    arreterVeille();
    derniereSurveillanceVue = -1;
    toursSansFrame = 0;
    veille = setInterval(() => {
        if (!arme || ferme) { arreterVeille(); return; }
        // Tant qu'aucune fenetre ne s'est OUVERTE, il n'y a rien a fermer -- et surtout, une
        // pompe a l'arret est alors l'etat NORMAL (hors bataille).
        if (!vuVivant) { derniereSurveillanceVue = appelsSurveillance; return; }
        if (appelsSurveillance !== derniereSurveillanceVue) {
            derniereSurveillanceVue = appelsSurveillance;
            toursSansFrame = 0;
            return;
        }
        toursSansFrame++;
        if (toursSansFrame >= TOURS_SANS_FRAME_AVANT_FERMETURE) {
            fermer("pompe de bataille ARRETEE (" + (toursSansFrame * PERIODE_VEILLE_MS / 1000)
                   + " s sans un seul appel) -- la scene de bataille a disparu");
        }
    }, PERIODE_VEILLE_MS);
}

function fermer(raison: string): void {
    if (!arme || ferme) return;
    ferme = true;
    arme = false;                      // plus rien ne doit re-declencher
    arreterVeille();
    const instantane = relais.slice();
    const frameNo = state.frameNo;
    // ⛔ JAMAIS DANS LA FRAME. Les deux pompes REMPLACENT `Update` : tout ce qu'on fait ici
    // retarde ou supprime une frame de la vue de bataille. On differe donc a `setTimeout(0)`,
    // exactement comme la pompe le fait pour `install()`. Le contexte y est le meme que celui
    // d'un RPC venu de Python — donc rien de neuf pour les relais qu'on va appeler.
    setTimeout(() => {
        const lignes: LigneBilan[] = [];
        let absents = 0;
        for (const r of instantane) {
            const fn = ctxRef === null
                ? undefined
                : (ctxRef.rpc as Record<string, unknown>)[r.rpc];
            if (typeof fn !== "function") {
                absents++;
                lignes.push({ rpc: r.rpc, appele: null,
                              err: "RPC ABSENT du bundle (renomme ou retire ?)", relu: null });
                continue;
            }
            const appel = fn as (body?: unknown) => unknown;
            let err: string | null = null;
            let appele: boolean | null = null;
            try { appel(r.corps ?? {}); appele = true; }
            catch (e) { err = (e as Error).message; }
            let relu: unknown = null;
            try { relu = appel({}); }
            catch (e) { relu = { ok: false, error: (e as Error).message }; }
            lignes.push({ rpc: r.rpc, appele, err, relu });
        }
        dernierBilan = { raison, frameNo, lignes, absents };
        const echecs = lignes.filter((l) => l.appele !== true).length;
        send({ t: "diag", msg: "[sandbox-fenetre] fenetre fermee (" + raison + ") -- "
            + (lignes.length - echecs) + "/" + lignes.length + " relais desarmes"
            + (absents > 0 ? ", " + absents + " RPC ABSENT(S)" : "")
            + (echecs - absents > 0 ? ", " + (echecs - absents) + " en ECHEC" : "")
            + ". `sandboxFenetre {}` pour le bilan relu." });
    }, 0);
}

/** Appele par la pompe A CHAQUE FRAME. Un test de booleen tant que le module est desarme. */
export function surveillerFinDeFenetre(): void {
    appelsSurveillance++;
    if (!arme) return;
    if (state.liveRunner) vuVivant = true;
    if (state.frameNo % PERIODE_FRAMES !== 0) return;
    const runner = state.liveRunner;
    if (!runner) { dernierRefus = "balayage : `state.liveRunner` NUL"; return; }
    try {
        const statePtr = runner.add(runnerOff.state).readPointer();
        if (statePtr.isNull()) {
            // ⛔ LE SIGNAL EST ICI, ET C'EST CE `return` QUI LE MANQUAIT.
            //
            // Un `state` nul sur un runner qu'on a DEJA lu, c'est un runner MORT : la bataille
            // est demontee, seule la reference survit. Mesure du 2026-08-24, retraite depuis la
            // phase de deploiement -- `battleStatus` rendait `runner: "live"` ET `stage: null`,
            // ce qui dit exactement ca. La pompe, elle, TICQUAIT ENCORE (frameNo 2521 -> 3784
            // en 21 s) et `IdunGameViews._runner` ne passait JAMAIS a null : les declencheurs
            // (2) et (3) ne pouvaient donc pas tirer, et celui-ci sortait en silence.
            //
            // J'avais diagnostique << la pompe s'arrete >> et bati un declencheur dessus. C'etait
            // FAUX, et la mesure l'a dit tout de suite. Ce qui meurt, c'est le RUNNER, pas la
            // pompe.
            //
            // ⚠ LE GARDE EST `dernierStage !== null` : sans lui, une frame ou le runner n'est pas
            // encore initialise fermerait la fenetre avant qu'elle ait servi. On ne conclut a la
            // mort que de ce qu'on a vu VIVRE.
            if (dernierStage !== null) {
                fermer("runner MORT (`state` nul) -- retraite ou demontage de la bataille");
            }
            return;
        }
        const bs = readBattleStatus(statePtr);
        // Sur la TRANSITION, pas sur la presence : une fenetre qui naitrait deja `Finished`
        // ne doit pas se fermer avant d'avoir servi.
        if (bs.stageName === "Finished" && dernierStage !== null && dernierStage !== "Finished") {
            fermer("stage -> Finished");
        }
        dernierStage = bs.stageName;
    } catch { /* un capteur ne doit JAMAIS peser sur la frame */ }
}

/** Appele par la pompe quand `IdunGameViews._runner` passe a `null` — fin de scene ou RETRAITE
 *  (on peut se retirer d'une sandbox, et c'est un mode de mort a part entiere). */
export function fermerAvantDetachement(): void {
    appelsDetachement++;
    if (!arme) { dernierRefus = "detachement vu, mais module DESARME"; return; }
    if (!vuVivant) {
        // Un armement pose hors bataille ne doit pas se consommer sur un detachement qui ne
        // concerne pas SA fenetre.
        dernierRefus = "detachement vu, mais aucune fenetre ne s'etait OUVERTE";
        return;
    }
    fermer("runner detache (retraite ou fin de scene)");
}

export function register(ctx: Ctx): void {
    ctxRef = ctx;

    /** ARMER la fermeture automatique, a l'OUVERTURE de la fenetre sandbox.
     *
     *  ⚠ SANS ARGUMENT, C'EST UNE LECTURE. Un RPC dont la forme neutre ECRIT est un piege pour
     *  tout appelant — `replayFinAuto` s'est fait prendre exactement la (la sonde qui verifiait
     *  le desarmement REARMAIT ce qu'elle mesurait, puis accusait le desarmement d'avoir echoue). */
    ctx.rpc.sandboxFenetre = (body?: {
        armer?: boolean; relais?: Relais[];
    }): unknown => {
        if (body == null || body.armer === undefined) {
            return {
                ok: true, lecture: true, arme, ferme, vuVivant,
                relais: relais.map((r) => r.rpc),
                appels: { surveillance: appelsSurveillance, detachement: appelsDetachement,
                          dernierStageVu: dernierStage, dernierRefus,
                          veilleActive: veille !== null, toursSansFrame,
                          derniereSurveillanceVue,
                          // `frameNo` est publie POUR LE CONTRASTE : il avance meme quand la
                          // pompe de bataille est morte (l'autre pompe l'incremente). Les voir
                          // cote a cote est ce qui a fait trouver la panne.
                          frameNo: state.frameNo },
                dernierBilan,
                note: "lecture seule -- `{armer:true, relais:[{rpc,corps}]}` pour armer a "
                    + "l'ouverture, `{armer:false}` pour renoncer sans rien desarmer.",
            };
        }
        if (body.armer === false) {
            arme = false;
            arreterVeille();
            return { ok: true, arme: false, note: "renonce -- AUCUN relais n'a ete desarme ici. "
                + "Pour desarmer maintenant : `desarmer_relais.py`." };
        }
        const liste = Array.isArray(body.relais) ? body.relais : [];
        if (liste.length === 0) {
            // Armer sans liste produirait une fermeture qui ne ferme RIEN, et le diag dirait
            // « 0/0 relais desarmes » -- un vert parfait sur une garde vide.
            return { ok: false, error: "REFUS : `relais` vide. Armer sans liste rendrait une "
                + "fermeture qui ne ferme rien, et son bilan se lirait comme un succes." };
        }
        relais = liste.filter((r) => r && typeof r.rpc === "string");
        arme = true;
        ferme = false;
        vuVivant = state.liveRunner !== null;
        dernierStage = null;
        dernierRefus = null;
        demarrerVeille();
        return {
            ok: true, arme, vuVivant, relais: relais.map((r) => r.rpc),
            note: "les relais seront desarmes a la MORT de la fenetre : `stage -> Finished`, "
                + "`_runner -> null`, ou POMPE ARRETEE (la scene demontee -- c'est le cas le "
                + "plus courant). Bilan relu dans `sandboxFenetre {}`.",
        };
    };
}
