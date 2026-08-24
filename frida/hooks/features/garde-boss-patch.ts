// garde-boss-patch — UNE TENTATIVE DE BOSS NE PART JAMAIS SUR UNE BC PATCHEE.
//
// LE PROBLEME
// -----------
// Un patch de BC (`env_ability_patch.py --poser`) reste `pending` jusqu'a ce qu'on le retire, et
// il mord au PROCHAIN `LoadBattle` -- **quel qu'il soit**. On l'arme pour l'onslaught et le PvP ;
// rien n'empeche qu'il tombe sur la tentative de boss de guilde lancee dix minutes plus tard.
// Cette tentative-la est une ressource RARE et NON RENOUVELABLE, et son replay part au serveur.
//
// OU, ET POURQUOI CE POINT-LA
// ----------------------------
// `idun.shared.commands.ViewCommandExecutor$$StartGuildBossMatch(encounterModel)` -- le point
// d'entree UNIQUE du lancement, en amont de tout :
//
//     StartGuildBossMatch                 <- ICI. Rien n'est encore engage.
//       -> AGameModeSource$$LoadBattle
//            -> GuildBossGameModeSource$$LoadBattleInternal   <- la BC est CONSTRUITE (et notre
//                                                                patch s'appliquerait a l'onLeave)
//            -> BattleLoadStateMachine.BattleLoadedAndSendingGameEventState
//                 -> SendLoadBattleGameEventInternal          <- LE JETON PART ICI
//
// ⛔ LES DEUX POINTS PLUS BAS SONT TROP TARD, ET C'EST MESURE AU DECOMPILE.
//   * `SendLoadBattleGameEventInternal` : le nom de l'etat le dit -- << BattleLOADEDAndSending >>.
//     La BC est deja construite, donc deja patchee. Desarmer la n'annule pas la mutation.
//   * l'entree de `LoadBattleInternal` : `GuildBossGameModeSource$$LoadBattleInternal` construit
//     la BC et la rend, il n'envoie rien -- mais surtout, LUI AJOUTER UN `onEnter` EST INTERDIT.
//     Mesure du 2026-08-23 : un `onEnter` ajoute a ces ancrages fait CESSER le tir de leur
//     `onLeave` -- les 17 ancrages muets d'un coup, en silence, pendant une bataille. Le garde
//     aurait desarme le mecanisme qu'il devait proteger.
//
// CE QU'IL FAIT : il DESARME, il ne refuse pas.
// ---------------------------------------------
// Faire echouer le lancement demanderait de detourner un `LoadBattle` natif, ce qui laisse le jeu
// dans un etat que personne n'a mesure. Retirer le patch, en revanche, est total et sans risque :
// la tentative part PROPRE, le jeton n'est pas gaspille, et le retrait est CRIE (`diag` + memoire
// relisible) pour que personne ne croie son debuff encore actif.
//
// ⚠ IL NE VISE QUE LE BOSS. L'onslaught et le PvP sont precisement les modes ou l'on VEUT le
// patch : les garder ici serait desarmer ce qu'on vient d'armer.
//
// ARME AU REGISTER, sans RPC d'armement -- un garde de securite qu'il faut penser a armer est un
// garde qui ne sera pas la le jour ou il sert. Cout : un `Interceptor.attach` sur un chemin
// FROID (un lancement de boss), aucun `replace`.

import { findClassAnywhere, findMethod } from "../il2cpp/helpers.js";
import { patchEnAttente, retirerPatchEnAttente } from "./battle-config.js";
import { log } from "../runtime/diag.js";
import { Ctx } from "../controller.js";

const NS = "idun.shared.commands";
const CLS = "ViewCommandExecutor";
const METHODE = "StartGuildBossMatch";
const PLEIN = NS + "." + CLS + "$$" + METHODE;

interface Retrait {
    quand: string;
    /** Ce qui a ete retire, tel quel -- pour qu'on puisse le REARMER en connaissance de cause. */
    retire: unknown;
}

let ancre: string | null = null;
let ancreErreur: string | null = null;
/** Combien de lancements de boss ont traverse le garde -- distingue « rien a retirer » de
 *  « jamais appele », qui se lisent pareil sans compteur. */
let lancements = 0;
let retraits: Retrait[] = [];

export function register(ctx: Ctx): void {
    ctx.rpc.gardeBossPatch = (): unknown => ({
        ok: true, ancre, ancreErreur, lancements,
        patchEnAttente: patchEnAttente() !== null,
        retraits,
        note: "ARME EN PERMANENCE. A chaque `ViewCommandExecutor$$StartGuildBossMatch`, un patch "
            + "de BC en attente est RETIRE -- avant que la BC soit construite, donc bien avant "
            + "que le jeton parte. Le boss ne joue jamais patche.",
    });

    try {
        const klass = findClassAnywhere(NS, CLS);
        if (klass === null) { ancreErreur = "classe introuvable : " + NS + "." + CLS; return; }
        const mi = findMethod(klass, METHODE);
        if (mi === null) { ancreErreur = "methode introuvable : " + PLEIN; return; }
        Interceptor.attach(mi.ptr, {
            onEnter() {
                lancements++;
                const p = patchEnAttente();
                if (p === null) return;
                retirerPatchEnAttente();
                const r: Retrait = { quand: new Date().toISOString(), retire: p };
                retraits.push(r);
                if (retraits.length > 8) retraits = retraits.slice(-8);
                // ⚠ ON LE CRIE. Un desarmement silencieux ferait jouer la tentative en croyant
                // le debuff actif -- ou, pire, ferait rearmer << puisqu'il n'a pas marche >>.
                send({ t: "diag", msg: "[garde-boss-patch] LANCEMENT DE BOSS -- patch de BC "
                    + "RETIRE avant construction de la BC (donc avant la depense du jeton). "
                    + "La tentative part PROPRE. Rearmer explicitement apres, si voulu." });
            },
        });
        ancre = PLEIN;
        log("[garde-boss-patch] arme sur " + ancre);
    } catch (e) {
        ancreErreur = (e as Error).message;
    }
}
