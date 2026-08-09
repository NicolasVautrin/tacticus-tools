// Journal des EVENTS de la bataille VIVANTE — ce que le jeu emet de lui-meme.
//
// POURQUOI CE MODULE EXISTE
// -------------------------
// `apply-stack.ts` hooke deja `StreamDispatcher.Action` / `.StartGroup` / `.FinishGroup`,
// mais il ne COLLECTE que si une frame est ouverte (`applyStack.length > 0`) — et nos
// frames ne sont poussees qu'autour de NOS appels (`applyAction`, `initAndStart`...).
// Les events emis par le JEU lui-meme (tour de l'IA, fin de tour d'equipe, overwatch,
// summons) tombent donc dans le vide. Le module le savait deja et le COMPTAIT :
// `_actionFiresStackEmpty`. Ce compteur EST la mesure qui justifie ce fichier.
//
// CE QUE CA DEBLOQUE, CONCRETEMENT
// --------------------------------
// Sans events, on ne peut pas savoir QUAND l'equipe a fini son tour : on le devine par
// `decisionView.toActivate` et l'etat du FSM, et on se trompe. Mesure du 2026-08-09 :
// deux blocages de l'ecran dans `WaitingForPlayerTurnToEndVisuallyState` pour avoir
// termine le tour a la main alors que le jeu allait le faire — et, symetriquement, un
// tour qui ne passait pas parce que deux unites avaient bouge sans consommer leur action.
// L'un et l'autre se lisent dans le flux ; aucun des deux ne se lit dans l'etat projete.
//
// LA FRAME EST AU FOND DE LA PILE, ET C'EST LE POINT DE CONCEPTION
// ----------------------------------------------------------------
// `apply-stack` ecrit dans `applyStack[applyStack.length - 1]` — le SOMMET. En posant
// notre frame au FOND (au demarrage, pile vide), on recolte tout ce qui n'appartient a
// personne d'autre, SANS voler les events d'un `applyAction` en cours : le sien reste au
// sommet le temps de son appel. Les deux canaux coexistent, aucun ne masque l'autre.

import { applyStack, applyStackRoles, ensureStreamHooks, popApply, pushApply,
    streamHookStats } from "../game/apply-stack.js";
import type { StreamEvent } from "../game/apply-stack.js";
import { Ctx } from "../controller.js";

/** Plafond du tampon. Un tour d'IA emet des centaines d'events ; on garde une fenetre
 *  glissante plutot que de grossir sans borne dans un process de jeu. */
const PLAFOND = 6000;

const journal: StreamEvent[] = [];
let actif = false;
/** Events ECARTES par le plafond. Publie : un tampon qui deborde en silence se lit comme
 *  un flux complet, et on daterait a tort le debut d'un tour. */
let ecartes = 0;
let recus = 0;

/** Le tampon glissant. On coupe par la TETE : le recent prime, et on DIT combien on jette. */
function elaguer(): void {
    if (journal.length <= PLAFOND) return;
    const trop = journal.length - PLAFOND;
    journal.splice(0, trop);
    ecartes += trop;
}

/** Notre frame est-elle encore au fond de la pile ? Elle peut disparaitre si un appelant
 *  a `popApply()` en trop — on le DIT plutot que de rendre un journal muet qui passerait
 *  pour « rien ne s'est passe ». */
function frameEnPlace(): boolean {
    return applyStack.length > 0 && applyStack[0].target === journal;
}

export function register(ctx: Ctx): void {
    /** Le journal des events de la bataille vivante.
     *
     *  body: { start?, stop?, clear?, depuis?: number, max?: number }
     *    start   arme la capture (idempotent)
     *    stop    la desarme et retire la frame
     *    clear   vide le tampon SANS desarmer
     *    depuis  n'emet que les events d'index >= depuis (curseur d'appelant)
     *    max     borne le nombre d'events rendus (defaut 500)
     *
     *  `recus` est le compteur CUMULE depuis le `start` : `depuis = recus` du releve
     *  precedent donne exactement les nouveaux, sans trou ni doublon — a condition que
     *  `ecartes` n'ait pas bouge, ce que la reponse publie aussi. */
    ctx.rpc.battleEvents = (body?: {
        start?: boolean; stop?: boolean; clear?: boolean;
        depuis?: number; max?: number;
    }): unknown => {
        if (body?.stop) {
            if (frameEnPlace()) {
                // Notre frame est au FOND : on ne peut la retirer proprement que si elle
                // est aussi au sommet. Sinon on la neutralise en la vidant de son role.
                if (applyStack.length === 1) popApply();
            }
            actif = false;
            return { ok: true, actif, note: "capture desarmee" };
        }
        if (body?.start && !actif) {
            ensureStreamHooks();
            if (applyStack.length !== 0) {
                return { ok: false, error: "la pile d'apply n'est pas vide ("
                    + applyStack.length + " frame(s)) -- un appel est en cours, notre "
                    + "frame ne serait pas au FOND et volerait ses events. Reessayer." };
            }
            pushApply("live", journal);
            actif = true;
        }
        if (body?.clear) {
            journal.length = 0;
            ecartes = 0;
            recus = 0;
        }
        elaguer();
        recus = journal.length + ecartes;

        const depuis = Math.max(0, (body?.depuis ?? 0) - ecartes);
        const max = Math.max(1, Math.min(body?.max ?? 500, 2000));
        const tranche = journal.slice(depuis, depuis + max);
        const stats = streamHookStats();
        return {
            ok: true,
            actif,
            frameEnPlace: frameEnPlace(),
            // LA PILE, PAR RÔLE — pas seulement sa hauteur (#596-r1). Une frame ORPHELINE
            // désigne ainsi le module qui l'a poussée (`live` = recorder ou nous, `built` =
            // launch/message-trace, `mirror` = sim-engine). Sans ça, une fuite ne se lisait
            // que dans la CHAÎNE D'ERREUR du refus d'armement ci-dessus — un message qui
            // parle d'autre chose, et qu'il fallait interpréter.
            pile: applyStackRoles(),
            // ⚠ TRI-ETAT : hooks non installes = on n'a RIEN MESURE, ce n'est pas
            // « aucun event ». Le distinguer est tout l'interet du champ.
            hooksInstalles: stats.installed === 1,
            recus,
            ecartes,
            enTampon: journal.length,
            rendus: tranche.length,
            curseur: ecartes + depuis + tranche.length,
            // Le compteur qui a justifie ce module : combien d'events sont passes SANS
            // frame. Il doit cesser de monter une fois la capture armee.
            horsFrame: stats.actionFiresStackEmpty,
            totalAction: stats.actionFiresTotal,
            events: tranche,
        };
    };
}
