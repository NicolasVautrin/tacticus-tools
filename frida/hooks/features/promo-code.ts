// ---------------------------------------------------------------------------------------
// PROMO CODES -- reclamer un code sans passer par l'ecran des reglages.
//
// LA CHAINE NATIVE, du haut vers le bas :
//
//   idun.Meta.View.Hud.SettingsPopup$$HandleOnRedeemPromoCodePressed        <- l'UI
//     -> idun.shared.commands.ViewCommandExecutor$$RedeemPromoCode
//          (code:String, redeemButton:NullableRefUnity<OnlineOfflineButton>)
//     -> RedeemPromoCodeCommand$$Execute -> RedeemCode -> HandleRedeemCallback
//   thor.UserProgress.PromoCodeProgression$$Redeem                          <- LA LOGIQUE
//          (code:String, onFinish:IPromoCodeProgression.OnRedeemPromoCodeResult)
//     -> thor.Client.Services.GameEventService$$RedeemPromoCode             <- le reseau
//
// ON ENTRE PAR LA COUCHE LOGIQUE, ET C'EST MOTIVE. Les trois etages du dessus exigent un
// `NullableRefUnity<OnlineOfflineButton>` -- un BOUTON d'interface, qu'il faudrait fabriquer
// ou aller chercher a l'ecran. `Redeem` ne prend qu'une chaine et un delegue. C'est le meme
// choix que pour les Operations, ou l'on entre par `ExpeditionGameEvents` et non par le
// presenter.
//
// CE QUE `Redeem` FAIT (decompile, build t6dpr4k06g) : il capture `(this, onFinish)` dans une
// classe de fermeture, fabrique LUI-MEME le callback reseau, et appelle le slot 0x3a de
// `_gameEventService`. On n'a donc qu'UN delegue a fournir -- `onFinish` -- et aucune
// enveloppe de reponse a construire.
//
// ⚠ `onFinish` N'EST PAS NULLABLE. Dans `<Redeem>b__0`, les DEUX branches (succes et erreur)
// font `if (onFinish != 0) { invoke; return; }` et, sinon, tombent sur le lanceur de
// `NullReferenceException`. Passer `null` ne « saute » donc pas le rappel : ca leve, sur le
// thread de la reponse serveur. Il FAUT un delegue.
//
// LA REPONSE REVIENT PAR L'ARDOISE, SANS AUCUN `Interceptor`. `<Redeem>b__0` invoque ainsi :
//
//     (*(cb + 0x18))( *(cb + 0x40), dto->result, dto->inboxItem, *(cb + 0x28) )
//       invoke_impl     method_code                                  method
//
// soit, en ABI Win64 : rcx = method_code, rdx = LE RESULTAT, r8 = l'item d'inbox. Or le stub
// de `il2cpp/delegate.ts` enregistre exactement rcx/rdx/r8 dans son ardoise. Le delegue
// inerte n'est donc pas qu'un bouchon anti-crash : c'est NOTRE CAPTEUR.
// ⚠ Ca evite de resoudre `PromoCodeProgression.<>c__DisplayClass4_0$$<Redeem>b__0`, une classe
//   generee par le compilateur -- et surtout ca respecte « ne jamais ancrer la methode qu'on
//   invoque », puisqu'on n'ancre plus rien du tout.
// ⚠ L'ardoise de `delegate.ts` documente que `rdx` s'etait revele etre une ADRESSE DE PILE sur
//   le callback d'ENVOI d'Operation. Ici le decompile est explicite (`uVar5 = *(dto + 0x10)`,
//   un `undefined4` lu dans le DTO), donc on ATTEND une valeur. On ne le decrete pas : le RPC
//   rend `rdx` BRUT en plus du resultat interprete, pour que l'ecart se voie s'il existe.
//
// LE DTO (`RedeemPromoCodeResponseDto`, mesure par `classFields`) :
//     +0x10  result      thor.UserProgress.RedeemPromoCodeResult
//     +0x18  inboxItem   PromoCodeUserInboxItem      (non nul = des recompenses sont arrivees)
//
// ⚠⚠ `RedeemPromoCodeResult` CONTIENT `MaxFailsReached = 5` : le serveur COMPTE les echecs et
// finit par VERROUILLER. Des qu'il est observe, `promoRedeem` REFUSE tout envoi ulterieur
// jusqu'a `promoReset` explicite. Une consigne en prose n'arrete pas une boucle ; un refus, si.
//
// ⚠ CE QUE CE COMPTEUR COMPTE N'EST PAS ETABLISSABLE D'ICI, et la premiere version de ce
// module s'est trompee de lecture. Il vit cote SERVEUR -- le client ne recoit que le verdict,
// donc aucun decompile ne le dira. Deux lectures, aux consequences OPPOSEES :
//   * GLOBALE (echecs cumules du compte, quel que soit le code) -> enfiler une liste ramassee
//     sur Discord, majoritairement perimee, griderait le compteur pour les codes valables ;
//   * PAR CODE (echecs sur CE code) -> enfiler des codes DISTINCTS ne risque rien, et la
//     protection utile est de ne jamais REJOUER un code.
// L'utilisateur du jeu tranche pour la seconde (2026-08-16). On la suit, et on en tire la
// consequence : le garde n'est plus ici, il est dans le REGISTRE du pilote
// (`scripts/python/promo_run.py`), qui n'a jamais rejoue un code tente.
//
// D'OU LE PARTAGE DES ROLES, qui est le bon independamment de la reponse : ce module ne
// verrouille QUE sur un fait MESURE (`MaxFailsReached`, dit par le serveur). Le seuil d'echecs
// consecutifs etait une POLITIQUE deguisee en garde -- il a coute 90 codes non tentes sur sa
// premiere sortie. La politique appartient a l'appelant, qui la regle par `--echecs-max` ; le
// compteur reste publie ici pour qu'il puisse la fonder.
//
// ⚠ Les recompenses n'atterrissent PAS dans l'inventaire : elles vont dans la BOITE DE
// RECEPTION (`idun.ui.InboxScreen$$ShowPromoCodeRewards`, `IdunLocalization.PromoCode$$Inbox*`).
// Un `Success` sans item d'inbox visible n'est donc pas une contradiction -- c'est l'inbox
// qu'il faut regarder, pas le compte de ressources.
// ---------------------------------------------------------------------------------------

import { findClassAnywhere, findMethodByParamCount, methodParamClass, getFieldOffset }
    from "../il2cpp/helpers.js";
import { invokeMethod, createManagedString } from "../il2cpp/invoke.js";
import { delegateInerte, lireArdoise } from "../il2cpp/delegate.js";
import { queueOnMainThread } from "../runtime/queue.js";
import { Ctx } from "../controller.js";
import { log } from "../runtime/diag.js";
import { executeurVivant, Refus as RefusVue } from "./view-command.js";

const NS = "thor.UserProgress";

/** `executeurVivant` rend un REFUS NOMME plutot qu'un `null` -- on le reconnait a sa forme. */
function estRefusVue(x: NativePointer | RefusVue): x is RefusVue {
    return typeof x === "object" && x !== null && (x as RefusVue).ok === false;
}

/** L'ordinal de `MaxFailsReached`. ⚠ C'est un MIROIR, mesure sur `t6dpr4k06g` par le RPC
 *  `dumpEnum` ET par le dump Il2CppDumper de mai (concordants). Il ne sert QU'AU VERROU :
 *  tout le reste de l'interpretation se fait cote appelant, qui redemande les noms au jeu
 *  (`dumpEnum thor.UserProgress RedeemPromoCodeResult`) plutot que de recopier une table. */
const MAX_FAILS_REACHED = 5;
const SUCCESS = 0;

interface Reclamation {
    n: number;
    ts: number;
    code: string;
    /** Le compteur de l'ardoise AVANT l'appel. La reponse est asynchrone : c'est l'increment
     *  de ce compteur qui atteste qu'elle est arrivee, pas le retour de `promoRedeem`. */
    appelsAvant: number;
    /** Renseigne par `promoLire` quand la reponse est revenue. */
    resultat?: number;
    inboxItem?: string;
    rdxBrut?: string;
    err?: string;
}

const journal: Reclamation[] = [];
/** Le verrou. Arme UNIQUEMENT sur `MaxFailsReached` -- un fait DIT PAR LE SERVEUR, pas une
 *  extrapolation de notre part. Se leve par `promoReset`, jamais tout seul. */
let verrou: string | null = null;
/** Publie, jamais agi : c'est a l'appelant d'en faire une politique (`--echecs-max`). Un
 *  seuil applique ici serait une politique deguisee en garde -- cf. l'en-tete. */
let echecsConsecutifs = 0;

/** La `PromoCodeProgression` vivante, lue sur le `ViewCommandExecutor`.
 *
 *  ⚠ Champ resolu PAR NOM (`_promoCodeProgression`) a chaque appel, jamais par le +0x4c0
 *  mesure : un offset en dur se perime au build suivant, EN SILENCE. Meme regle que
 *  `_expeditionProgression` dans `expedition-dispatch.ts`.
 *  ⚠ Lecture PURE -- aucune commande de vue jouee, donc rien ne bouge a l'ecran du joueur. */
function progressionPromo(): NativePointer | null {
    try {
        const exec = executeurVivant();
        if (estRefusVue(exec)) return null;
        const kExec = findClassAnywhere("idun.shared.commands", "ViewCommandExecutor");
        if (!kExec) return null;
        const off = getFieldOffset(kExec, "_promoCodeProgression");
        if (off < 0) return null;              // ⚠ -1 est *truthy* : tester `< 0`, jamais `||`
        const p = (exec as NativePointer).add(off).readPointer();
        return p.isNull() ? null : p;
    } catch { return null; }
}

/** Le delegue PARTAGE qui sert de capteur. Un seul, reutilise : `neuf: true` epinglerait un
 *  objet de plus a chaque code, et on en joue des dizaines. Comme on serialise (un code, puis
 *  on attend sa reponse), une ardoise unique suffit -- c'est l'INCREMENT de son compteur qui
 *  apparie la reponse a la demande. */
let capteur: ReturnType<typeof delegateInerte>["d"] | null = null;

function obtenirCapteur(mi: { info: NativePointer }): { d?: NonNullable<typeof capteur>;
                                                       err?: string } {
    if (capteur) return { d: capteur };
    const kCb = methodParamClass(mi.info, 1);   // `onFinish`, parametre 1 de `Redeem`
    const r = delegateInerte(kCb);
    if (!r.d) return { err: r.err ?? "classe du delegue NON RESOLUE" };
    capteur = r.d;
    return { d: r.d };
}

export function register(ctx: Ctx): void {

    /** RECLAMER un code promotionnel.
     *
     *  ⚠ CE RPC ECRIT sur le compte -- d'ou `confirmer: true`, comme les portes d'Operations.
     *  Il n'y a en revanche RIEN a depenser : un code est un gain ou un refus serveur.
     *
     *  IL NE REND PAS LE RESULTAT. La reponse est asynchrone (aller-retour serveur) : ce RPC
     *  rend `appelsAvant`, et c'est `promoLire` qui atteste quand le compteur de l'ardoise a
     *  bouge. Rendre un verdict ici serait un mensonge de forme -- on aurait « ok: true » pour
     *  un code que le serveur va refuser une seconde plus tard. */
    ctx.rpc.promoRedeem = (body?: { code?: string; confirmer?: boolean; }):
        Promise<unknown> | unknown => {
        const code = typeof body?.code === "string" ? body.code.trim() : "";
        if (!code) {
            return { ok: false, error: "`code` manquant -- ce RPC n'ENUMERE PAS les codes, il "
                + "en joue un. Les codes viennent du canal Discord, pas du jeu." };
        }
        if (code.length > 64) {
            return { ok: false, error: "`code` de plus de 64 caracteres -- refuse, c'est une "
                + "borne de surete, pas une regle du jeu" };
        }
        if (body?.confirmer !== true) {
            return { ok: false, error: "REFUS : `confirmer: true` exige. Ce RPC ECRIT sur le "
                + "compte et consomme une TENTATIVE cote serveur." };
        }
        if (verrou) {
            return { ok: false, verrou, error: "VERROU ARME : " + verrou + ". Le serveur compte "
                + "les echecs (`MaxFailsReached`) et finit par bloquer la fonction. Lever par "
                + "`promoReset` seulement si tu sais pourquoi tu le fais." };
        }
        return queueOnMainThread(() => {
            const prog = progressionPromo();
            if (prog === null) {
                return { ok: false, error: "`PromoCodeProgression` introuvable sur "
                    + "`ViewCommandExecutor._promoCodeProgression` -- l'executeur n'est peut-etre "
                    + "pas encore capte" };
            }
            const kProg = findClassAnywhere(NS, "PromoCodeProgression");
            if (!kProg) {
                return { ok: false, error: "classe `PromoCodeProgression` absente de ce build" };
            }
            const mi = findMethodByParamCount(kProg, "Redeem", 2);
            if (!mi) {
                return { ok: false, error: "`Redeem` a 2 parametres INTROUVABLE -- chemin PERIME "
                    + "sur ce build, ne pas replier sur une autre arite" };
            }
            const c = obtenirCapteur(mi);
            if (!c.d) {
                return { ok: false, error: "delegue `onFinish` non fabricable : " + (c.err ?? "?")
                    + " -- on n'appelle PAS avec null : les deux branches de `<Redeem>b__0` "
                    + "levent une NullReferenceException sur le thread de la reponse" };
            }
            const avant = lireArdoise(c.d.ardoise);
            const e: Reclamation = {
                n: journal.length + 1, ts: Date.now(), code,
                appelsAvant: avant ? avant.appels : -1,
            };
            log("[promo-code] reclamation `" + code + "`, ardoise a " + e.appelsAvant
                + " -- si le jeu gele, cette ligne est la derniere sortie");
            try {
                invokeMethod(mi.info, prog, [createManagedString(code), c.d.ptr]);
            } catch (ex) {
                e.err = String((ex as Error).message || ex).slice(0, 200);
            }
            if (journal.length >= 128) journal.shift();
            journal.push(e);
            return {
                ok: !e.err, reclamation: e,
                note: "L'appel est parti. Le VERDICT n'est pas ici : sonder `promoLire` "
                    + "jusqu'a ce que `appels` depasse `appelsAvant`. Et la tentative est "
                    + "consommee cote serveur MEME si le jeu gele ensuite -- ne pas rejouer "
                    + "un code a l'aveugle, ca brule une tentative de plus.",
            };
        });
    };

    /** LIRE l'ardoise du capteur : la reponse serveur est-elle revenue, et que dit-elle ?
     *
     *  Lecture PURE, sans aucun appel natif -- on relit une page memoire que le stub a
     *  ecrite. Peut donc etre sondee sans risque, aussi souvent qu'on veut.
     *
     *  ⚠ Rend l'ORDINAL, pas un nom. Le nom se redemande au jeu
     *  (`dumpEnum thor.UserProgress RedeemPromoCodeResult`) : un miroir recopie ici se
     *  perimerait en silence, et c'est exactement ce que le depot proscrit. */
    ctx.rpc.promoLire = (): unknown => {
        if (!capteur) {
            return { ok: false, error: "aucun capteur fabrique -- aucune reclamation n'a encore "
                + "ete jouee. C'est `null` au sens NON MESURE, pas `0 appel`." };
        }
        const ar = lireArdoise(capteur.ardoise);
        if (!ar) {
            return { ok: false, error: "ardoise ILLISIBLE -- NON MESURE" };
        }
        const derniere = journal.length ? journal[journal.length - 1] : null;
        const repondu = derniere !== null && ar.appels > derniere.appelsAvant;
        // rdx porte le resultat (cf. l'en-tete). On garde le BRUT a cote de l'entier : si un
        // jour rdx redevenait une adresse de pile, l'ecart doit se VOIR, pas se deviner.
        let resultat: number | null = null;
        try { resultat = parseInt(ar.rdx, 16) & 0xffffffff; } catch { resultat = null; }
        if (repondu && derniere) {
            derniere.resultat = resultat ?? undefined;
            derniere.rdxBrut = ar.rdx;
            derniere.inboxItem = ar.r8;
            // LE VERROU, arme sur le SEUL fait mesure : le serveur dit `MaxFailsReached`.
            // Le compteur d'echecs, lui, est tenu et PUBLIE -- jamais agi ici.
            if (resultat === MAX_FAILS_REACHED) {
                verrou = "`MaxFailsReached` observe sur le code `" + derniere.code + "`";
            }
            echecsConsecutifs = (resultat === SUCCESS) ? 0 : echecsConsecutifs + 1;
        }
        return {
            ok: true, repondu, appels: ar.appels,
            appelsAvant: derniere ? derniere.appelsAvant : null,
            code: derniere ? derniere.code : null,
            resultat: repondu ? resultat : null,
            inboxItemNonNul: repondu ? (ar.r8 !== "0x0") : null,
            rdxBrut: ar.rdx, r8Brut: ar.r8,
            verrou, echecsConsecutifs,
            note: "`resultat` est un ORDINAL de `thor.UserProgress.RedeemPromoCodeResult` : "
                + "le nommer par `dumpEnum`, jamais par une table recopiee. `inboxItemNonNul` "
                + "dit que des recompenses sont arrivees -- elles vont dans la BOITE DE "
                + "RECEPTION, pas dans l'inventaire.",
        };
    };

    /** Le journal des reclamations jouees dans cette session. */
    ctx.rpc.promoJournal = (): unknown => ({
        ok: true, n: journal.length, verrou, echecsConsecutifs,
        reclamations: journal.slice(-64),
    });

    /** LEVER le verrou. Geste DELIBERE : le verrou existe parce que le serveur compte les
     *  echecs. Le lever pour « reessayer voir » est exactement ce contre quoi il protege. */
    ctx.rpc.promoReset = (body?: { confirmer?: boolean }): unknown => {
        if (body?.confirmer !== true) {
            return { ok: false, verrou, error: "REFUS : `confirmer: true` exige. Le verrou "
                + "protege d'un blocage SERVEUR de la fonction promo -- ne pas le lever par "
                + "reflexe." };
        }
        const ancien = verrou;
        verrou = null;
        echecsConsecutifs = 0;
        return { ok: true, leve: ancien, note: "verrou leve ; le compteur d'echecs du SERVEUR, "
            + "lui, n'est pas remis a zero par ce geste -- il ne se voit pas d'ici." };
    };
}
