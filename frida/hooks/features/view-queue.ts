// view-queue — CE QUE LA VUE RECOIT QUAND ON JOUE, lu DANS LE MEME JOB que l'`Apply`.
//
// LE CANAL, ET SON SENS. `IdunBattle.Runner.IdunRunner$$Apply` a trois etages, tous
// synchrones : pre-listeners, processeur, post-listeners. L'un de ces listeners appelle
// `IdunBattle.ViewLogic.BattleStream.MessageExecutionQueue$$Enqueue` -- jamais appelee en
// direct (que des references DATA : c'est un delegue). C'est donc `Apply` qui NOURRIT la
// vue. Nos commandes n'entrent PAS par elle, contrairement au tour de l'IA.
//
// `Enqueue` empile dans `_messages` (la `Queue`, ce qui reste a JOUER), journalise dans
// `_messageArchive` (la `List`, jamais purgee), puis appelle `ProcessNextMessage` -- qui
// resout la vue de l'entite et ANIME. `ProcessNextMessage` ne rappelle JAMAIS `Apply` :
// la file est PRESENTATIONNELLE, elle n'applique rien.
//
// (!)POURQUOI LIRE DANS LE JOB, ET PAS PAR UN RPC SEPARE.
//
// Notre travail est draine par `IdunGameViews$$Update` AVANT le relais vers l'original, et
// `QueueComputerActions` est a la FIN de cet original. Tant qu'on est dans le job, la vue
// n'a donc pas eu sa frame et `IdunGameViews.<RunComputerActionsForCurrentPlayerInMultiple
// Frames>` n'a pas demarre : ce qu'on lit est le produit de NOTRE coup, et de lui seul.
// Ce n'est pas une chance de timing, c'est l'ordre des etages.
//
// Apres un `EndTurnMessage` l'IA part des la frame suivante. Un RPC separe arriverait donc
// TROP TARD sur exactement le coup qu'on veut observer -- le dernier avant qu'elle joue.
//
// (!)TOUS LES CHAMPS SONT RESOLUS PAR LEUR NOM. Les offsets du decompile n'ont servi qu'a
// CONFIRMER l'appariement contre `classFields` sur les classes VIVANTES : 6/6 concordants
// sur `MessageExecutionQueue` (`_messages` +0x38, `_messageArchive` +0x40,
// `_currentlyProcessingMessage` +0x48, `_disableTimeouts` +0x68, `_isStopped` +0x69), et
// `_messageExecutionQueue` +0x140 / `_queuedComputerActions` +0x1f8 sur `IdunGameViews`.
//
// ⚠ AUCUNE INVOCATION NATIVE ICI. On LIT de la memoire -- y compris le predicat `ralenti`,
// qui re-derive `MessageExecutionQueue$$IsIdle` (file vide ET rien en cours) au lieu de
// l'appeler. Invoquer dans le job d'un `Apply` fait courir un risque pour zero gain.

import { Ctx } from "../controller.js";
import { state } from "../game/state.js";
import { queueOnMainThread } from "../runtime/queue.js";
import { readMsgIdentity } from "../il2cpp/helpers.js";
import {
    champPointeur, champInt, champBool, champTexte, elementsDeListe, estRefus,
} from "./lecture-champs.js";

/** Combien d'entrees d'archive on rend quand l'appelant ne donne pas de repere. L'archive
 *  n'est jamais purgee de toute la bataille : la rendre entiere noierait la reponse. */
const DERNIERES_PAR_DEFAUT = 40;

export interface MessageDeVue {
    /** Indice dans `_messageArchive` — comparable d'un appel a l'autre. */
    i: number;
    ns: string;
    cls: string;
}

export interface FileDeVue {
    ok: boolean;
    error?: string;
    /** Frame de la derniere publication de la vue par la pompe. Un ecart avec
     *  `state.frameNo` dit que la pompe ne tourne plus -- donc que ce qui suit est VIEUX. */
    frame: number | null;
    frameCourante: number;
    /** `_messages.Count` : ce qui reste a JOUER. */
    enAttente: number | null;
    /** `_currentlyProcessingMessage` : un message est en cours d'animation. */
    enCours: boolean | null;
    /** `_isStopped`. */
    arretee: boolean | null;
    /** Le predicat du jeu (`MessageExecutionQueue$$IsIdle`), re-derive : rien en file ET
     *  rien en cours. `null` = pas mesure. */
    ralenti: boolean | null;
    /** Longueur totale de `_messageArchive` — le repere a repasser au prochain appel. */
    archive: number | null;
    /** `_lastActivity` / `_lastActivityStep` : ce que la vue dit avoir fait en dernier. */
    derniereActivite: string | null;
    dernierPas: string | null;
    /** `IdunGameViews._queuedComputerActions` non nul = la coroutine d'IA est EN VOL. */
    iaEnVol: boolean | null;
    /** La logique est-elle en pause ? `_isLogicPausedFromException` est le verrou SANS clef
     *  d'une exception avalee : la vue cesse alors de pomper, et rien ne le signale. */
    pauseUI: boolean | null;
    pauseVisuels: boolean | null;
    pauseException: boolean | null;
    /** Les entrees d'archive depuis le repere. `null` = pas mesure (jamais `[]`). */
    nouveaux: MessageDeVue[] | null;
    /** Vrai si `nouveaux` a ete tronque — un compte filtre DIT ce qu'il filtre. */
    tronque: boolean;
}

function vide(error: string): FileDeVue {
    return {
        ok: false, error,
        frame: null, frameCourante: state.frameNo,
        enAttente: null, enCours: null, arretee: null, ralenti: null,
        archive: null, derniereActivite: null, dernierPas: null,
        iaEnVol: null, pauseUI: null, pauseVisuels: null, pauseException: null,
        nouveaux: null, tronque: false,
    };
}

/**
 * L'etat du canal vue, et ce qui y est entre depuis `depuis`.
 *
 * `depuis` est un indice dans `_messageArchive` : passer la valeur `archive` rendue par un
 * appel precedent donne exactement le delta. Omis, on rend les dernieres entrees.
 */
export function dumpFileDeVue(depuis?: number | null): FileDeVue {
    const vues = state.gameViews;
    if (!vues || vues.isNull()) {
        return vide("aucune `IdunGameViews` publiee par la pompe -- pas de bataille a "
            + "l'ecran, ce qui n'est PAS « file vide »");
    }

    const out = vide("");
    out.ok = true;
    delete out.error;
    out.frame = state.gameViewsFrame ?? null;

    // Le jeton d'IA et les trois pauses se lisent sur la VUE, pas sur la file.
    out.iaEnVol = (() => {
        const p = champPointeur(vues, "_queuedComputerActions");
        return estRefus(p) ? null : !p.isNull();
    })();
    out.pauseUI = champBool(vues, "_isLogicPausedFromUI");
    out.pauseVisuels = champBool(vues, "_isLogicPausedFromVisuals");
    out.pauseException = champBool(vues, "_isLogicPausedFromException");

    const file = champPointeur(vues, "_messageExecutionQueue");
    if (estRefus(file)) { out.ok = false; out.error = file.error; return out; }
    if (file.isNull()) {
        out.ok = false;
        out.error = "`_messageExecutionQueue` NUL sur la vue";
        return out;
    }

    out.enCours = champBool(file, "_currentlyProcessingMessage");
    out.arretee = champBool(file, "_isStopped");
    out.derniereActivite = champTexte(file, "_lastActivity");
    out.dernierPas = champTexte(file, "_lastActivityStep");

    const messages = champPointeur(file, "_messages");
    out.enAttente = estRefus(messages) || messages.isNull()
        ? null : champInt(messages, "_size");

    // `IsIdle` re-derive. Les deux facteurs doivent etre MESURES : si l'un manque, le
    // predicat n'est pas `false`, il est INCONNU.
    out.ralenti = (out.enAttente === null || out.enCours === null)
        ? null : (out.enAttente === 0 && out.enCours === false);

    const archive = champPointeur(file, "_messageArchive");
    if (estRefus(archive) || archive.isNull()) return out;
    const els = elementsDeListe(archive);
    if (estRefus(els)) { out.error = els.error; return out; }
    out.archive = els.length;

    const debut = typeof depuis === "number" && depuis >= 0
        ? Math.min(depuis, els.length)
        : Math.max(0, els.length - DERNIERES_PAR_DEFAUT);
    out.tronque = debut > 0 && (typeof depuis !== "number" || depuis < 0);
    out.nouveaux = els.slice(debut).map((p, k) => ({
        i: debut + k,
        ...(p.isNull() ? { ns: "", cls: "<null>" } : readMsgIdentity(p)),
    }));
    return out;
}

export function register(ctx: Ctx): void {
    /**
     * L'etat du canal RUNNER -> VUE, a la demande. Lecture PURE : n'arme rien, n'invoque
     * rien, ne modifie rien.
     *
     * ⚠ HORS DU JOB D'UN `Apply`, CE DUMP EST PRIS APRES LA FRAME. Sur un `EndTurnMessage`
     * l'IA a alors deja pu demarrer, et l'archive melange notre coup au sien. Pour
     * attribuer a UN coup, lire `fileDeVue` dans la reponse de `replayMessages` : celle-la
     * est prise dans le job, avant que la vue ait sa frame.
     */
    ctx.rpc.viewQueueDump = (args?: { depuis?: number }) =>
        queueOnMainThread(() => dumpFileDeVue(
            typeof args?.depuis === "number" ? args.depuis : null));
}

/** La longueur d'archive SEULE, pour prendre un repere avant un `Apply` sans payer la
 *  lecture des identites. `null` = pas mesure. */
export function repereArchive(): number | null {
    const vues = state.gameViews;
    if (!vues || vues.isNull()) return null;
    const file = champPointeur(vues, "_messageExecutionQueue");
    if (estRefus(file) || file.isNull()) return null;
    const archive = champPointeur(file, "_messageArchive");
    if (estRefus(archive) || archive.isNull()) return null;
    return champInt(archive, "_size");
}
