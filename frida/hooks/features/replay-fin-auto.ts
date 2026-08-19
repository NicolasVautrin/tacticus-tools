// replay-fin-auto — LE REPLAY PRIS A LA FRAME OU LA BATAILLE SE TERMINE.
//
// POURQUOI CE MODULE EXISTE, ET CE QU'IL REMPLACE
// ------------------------------------------------
// La premiere tentative interrogeait `replayOutputStream` depuis un script EXTERIEUR, en
// sondant `battleStatus` toutes les 3 s. C'est une COURSE, et elle a ete perdue deux fois :
// le runner disparait a la fin de la bataille, et un sondage qui tombe apres ne rend plus
// que `runner has no ReplayRecorder` -- un message qui accuse le mecanisme alors que seul le
// TIMING etait en cause. Un replay a ainsi ete perdu apres une bataille entiere.
//
// Le sondage ne se repare pas en le rendant plus rapide : il n'existe aucune periode qui
// garantisse de tomber dans la fenetre. Le signal doit etre pris LA OU IL SE PRODUIT.
//
// OU EXACTEMENT, ET POURQUOI C'EST LE BON ENDROIT
// ------------------------------------------------
// `main-pump` lit `IdunGameViews._runner` A CHAQUE FRAME et detecte deja la transition
// `runner -> null` (c'est elle qui vide `state.liveRunner`). A cet instant precis, le runner
// est ENCORE dans `state.liveRunner` : c'est la derniere frame ou le replay est atteignable.
// On capture donc AVANT le nettoyage, dans la meme frame. Aucune course possible.
//
// DEUX DECLENCHEURS, PARCE QU'UNE BATAILLE PEUT FINIR DE DEUX FACONS
//   1. `stage -> Finished` alors que le runner est encore attache (fin normale, ecran de
//      resultat) -- vu par le balayage periodique ci-dessous ;
//   2. `_runner -> null` sans passer par (1) (retraite, changement de scene) -- vu par la
//      pompe, qui appelle `capturerFin("runner detache")`.
// Le premier qui tire gagne ; le second se tait (`dejaCapture`).
//
// COUT : le balayage lit l'etat du match, ce qui parcourt les entites. Il ne tourne donc
// QU'ARME, et seulement une frame sur `PERIODE_FRAMES`. Desarme, ce module coute un test de
// booleen par frame.

import { state } from "../game/state.js";
import { readBattleStatus } from "../game/match-state.js";
import { replayOutputStream } from "./replay-output-stream.js";
import { runnerOff } from "../game/runner.js";
import { Ctx } from "../controller.js";

/** Assez large pour un replay entier : la troncature est le defaut qu'on cherche a eviter,
 *  et le champ `tronque` de la capture le signale s'il reste atteint. */
const MAX_CHARS = 40_000_000;
/** Une frame sur 15 (~0,25 s a 60 fps) : assez fin pour attraper `Finished` avant que la
 *  scene change, assez rare pour ne rien couter. */
const PERIODE_FRAMES = 15;

export interface CaptureFin {
    raison: string;
    stageName: string | null;
    winner: number | null;
    frameNo: number;
    /** Le replay serialise. `null` = la capture a echoue, et `err` dit pourquoi. */
    replay: string | null;
    longueur: number;
    tronque: boolean;
    stepCount: number | null;
    recorderArmed: boolean | null;
    err: string | null;
}

let arme = false;
let dejaCapture = false;
let derniereCapture: CaptureFin | null = null;

// ⚠ COMPTEURS D'APPEL — parce qu'un capteur MUET a deux causes indiscernables sans eux :
// « il n'a rien vu » et « il n'a jamais ete appele ». Mesure du 2026-08-19 : premiere mise en
// service, `dejaCapture` est reste FAUX apres un detachement de runner AVERE (le RPC
// `battleStatus` etant passe de `Running` a `no runner`), sans aucune faute de pompe. Le code
// etait dans le bundle, l'armement etait vrai -- et il n'existait aucun moyen de savoir si la
// branche avait tire. Ces compteurs repondent a ca, et rien d'autre.
let appelsSurveillance = 0;
let appelsDetachement = 0;
let balayagesEffectifs = 0;
/** Le dernier motif de non-capture, pour que le refus se lise au lieu de se deviner. */
let dernierRefus: string | null = null;
/** Toutes les captures de la session, pour qu'une seconde bataille n'efface pas la premiere. */
const captures: CaptureFin[] = [];
const CAPTURES_MAX = 8;
/** Le dernier stage vu, pour ne declencher que sur une TRANSITION. */
let dernierStage: string | null = null;

function capturer(raison: string, stageName: string | null, winner: number | null): void {
    if (!arme || dejaCapture) return;
    dejaCapture = true;
    let c: CaptureFin;
    try {
        const r = replayOutputStream({ maxChars: MAX_CHARS });
        c = {
            raison, stageName, winner, frameNo: state.frameNo,
            replay: r.outputStream,
            longueur: r.outputStreamLength ?? 0,
            tronque: r.truncated === true,
            stepCount: r.stepCount,
            recorderArmed: r.recorderArmed,
            err: r.err,
        };
    } catch (e) {
        c = {
            raison, stageName, winner, frameNo: state.frameNo,
            replay: null, longueur: 0, tronque: false, stepCount: null,
            recorderArmed: null, err: (e as Error).message,
        };
    }
    derniereCapture = c;
    captures.push(c);
    if (captures.length > CAPTURES_MAX) captures.shift();
    send({ t: "diag", msg: "[replay-fin-auto] " + raison + " -- "
        + (c.replay === null ? "CAPTURE ECHOUEE : " + c.err
                             : c.longueur + " caracteres" + (c.tronque ? " (TRONQUE)" : "")) });
}

/** Appele par la pompe A CHAQUE FRAME. Ne fait rien tant que le module n'est pas arme. */
export function surveillerFinDeBataille(): void {
    appelsSurveillance++;
    if (!arme || dejaCapture) return;
    if (state.frameNo % PERIODE_FRAMES !== 0) return;
    const runner = state.liveRunner;
    if (!runner) { dernierRefus = "balayage : `state.liveRunner` NUL"; return; }
    balayagesEffectifs++;
    try {
        const statePtr = runner.add(runnerOff.state).readPointer();
        if (statePtr.isNull()) return;
        const bs = readBattleStatus(statePtr);
        // On declenche sur la TRANSITION vers un stage terminal, pas sur sa presence : un
        // montage qui naitrait deja `Finished` ne doit pas capturer un flux vide.
        if (bs.stageName === "Finished" && dernierStage !== null && dernierStage !== "Finished") {
            capturer("stage -> Finished", bs.stageName, bs.winner);
        }
        dernierStage = bs.stageName;
    } catch { /* un capteur ne doit JAMAIS peser sur la frame */ }
}

/** Appele par la pompe quand `IdunGameViews._runner` passe a `null`, AVANT le nettoyage de
 *  `state.liveRunner` -- c'est la derniere frame ou le replay est atteignable. */
export function capturerAvantDetachement(): void {
    appelsDetachement++;
    if (!arme) { dernierRefus = "detachement vu, mais module DESARME"; return; }
    if (dejaCapture) { dernierRefus = "detachement vu, mais deja capture"; return; }
    capturer("runner detache (fin de scene ou retraite)", dernierStage, null);
}

export function register(ctx: Ctx): void {
    /** ARMER la capture automatique. `armer: true` REARME aussi pour une nouvelle bataille
     *  (remet `dejaCapture` a faux) -- sinon la deuxieme bataille d'une session ne serait
     *  jamais capturee, et le silence se lirait comme « rien a capturer ». */
    ctx.rpc.replayFinAuto = (body?: { armer?: boolean }): unknown => {
        const veut = body?.armer !== false;
        arme = veut;
        if (veut) { dejaCapture = false; dernierStage = null; }
        return {
            ok: true, arme, dejaCapture, capturesGardees: captures.length,
            periodeFrames: PERIODE_FRAMES, maxChars: MAX_CHARS,
            note: "capture PRISE DANS LA POMPE, a la frame de la transition -- pas de sondage "
                + "externe, donc pas de course. `armer: true` REARME pour la bataille suivante.",
        };
    };

    /** Le replay capture. Rendu SANS le contenu par defaut : une reponse de plusieurs Mo
     *  n'a pas a partir a chaque coup d'oeil. `avecReplay: true` pour le contenu. */
    ctx.rpc.replayFinEtat = (body?: { avecReplay?: boolean; index?: number }): unknown => {
        const avec = body?.avecReplay === true;
        const resume = (c: CaptureFin): Record<string, unknown> => ({
            raison: c.raison, stageName: c.stageName, winner: c.winner, frameNo: c.frameNo,
            longueur: c.longueur, tronque: c.tronque, stepCount: c.stepCount,
            recorderArmed: c.recorderArmed, err: c.err,
            replay: avec ? c.replay : null,
        });
        const i = body?.index;
        if (typeof i === "number") {
            const c = captures[i];
            return c ? { ok: true, index: i, capture: resume(c) }
                     : { ok: false, error: "index " + i + " hors des " + captures.length
                         + " captures gardees" };
        }
        return {
            ok: true, arme, dejaCapture, total: captures.length,
            // Ce bloc distingue « rien a capturer » de « jamais appele » — sans lui, les deux
            // se lisent pareil (capteur muet) et on accuse le mauvais etage.
            appels: {
                surveillance: appelsSurveillance,
                balayagesEffectifs,
                detachement: appelsDetachement,
                dernierStageVu: dernierStage,
                dernierRefus,
            },
            derniere: derniereCapture === null ? null : resume(derniereCapture),
            toutes: captures.map((c) => ({ raison: c.raison, longueur: c.longueur,
                                           frameNo: c.frameNo, err: c.err })),
        };
    };
}
