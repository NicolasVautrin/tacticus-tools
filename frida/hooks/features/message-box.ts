/**
 * message-box — ouvrir une boite de dialogue DU JEU, avec un texte a nous (#10047).
 *
 * POURQUOI UN MODULE, ALORS QUE `viewInvoke` SAIT DEJA LE FAIRE
 * -------------------------------------------------------------
 * Il le sait, et c'est ainsi que la chose a ete etablie. Mais l'incantation est un pointeur
 * re-resolu a la main plus DIX arguments POSITIONNELS dont l'ordre ne se lit nulle part -- une
 * recette, pas une capacite. Et le premier consommateur ne sera pas un RPC : c'est le garde
 * << pas de lineup par defaut >> qui doit rendre son refus LISIBLE EN JEU plutot que dans un
 * journal que le joueur ne lit pas. Un garde qui appelle depuis du code a besoin d'une
 * FONCTION, pas d'un RPC.
 *
 * LES DEUX VOIES, ET CE QUI LES SEPARE VRAIMENT
 * ----------------------------------------------
 * Le travail est fait par `thor.Menu.MessagePopup$$Show`, qui prend DIX parametres :
 *
 *     Show(text, cancel, okCallback, cancelCallback, ok, okText, cancelText,
 *          immediately, titleText, blocking)
 *
 *   - VOIE `relais` -- `ViewCommandExecutor$$ShowMessagePopup(text, onConfirm, showCancel)`.
 *     C'est le chemin DU JEU. Lu au decompile, il n'en cable que trois et FORCE les sept
 *     autres a zero : `ok = 1`, et titre / libelles / `immediately` / `blocking` a 0. Donc
 *     **le relais ne peut pas porter de titre** -- ce n'est pas une limite de notre appel.
 *     Ce qu'il a en propre : il resout l'instance par `IMenu<MessagePopup>` (slot 0 = `Get()`)
 *     depuis le porte-menus de l'executeur, donc il PEUT la faire exister.
 *   - VOIE `directe` -- `Show` sur l'instance enumeree. Les dix parametres, donc le titre et
 *     les libelles de boutons. Elle ne sait que REUTILISER une instance existante.
 *
 * ⇒ `auto` (defaut) prend le relais quand aucune option riche n'est demandee, la voie directe
 * sinon. On ne choisit pas par gout : chacune est la seule a savoir faire une chose.
 *
 * ⚠ CE QUI N'EST PAS MESURE, ET QUI EST DIT PLUTOT QUE DEVINE. On ignore si la voie directe
 * laisse le `ScreenVisibilityManager` dans le meme etat que le relais. `ui-windows.ts` a mesure
 * qu'a l'ouverture de la confirmation de retraite, `MessagePopup` devient le seul ecran
 * `Rendering` -- il y a donc bien une comptabilite d'ecrans, et on ne sait pas si `Show` seule
 * la tient. Les deux voies ont ete jouees en live le 2026-08-26 (popup affichee, refermee par
 * le joueur, jeu intact) ; ca etablit qu'elles MARCHENT, pas qu'elles sont EQUIVALENTES.
 *
 * ⚠ AUCUN CALLBACK N'EST BRANCHE, ET C'EST DELIBERE. `okCallback`/`cancelCallback` partent a
 * NUL. Les trois handlers (`OnOk`, `OnCancel`, `OnClose`) testent le delegue avant de l'appeler
 * (`if (lVar1 != 0)`), donc un nul est SUR -- verifie au decompile puis en live. Fabriquer un
 * delegue qui rentrerait dans du JS est un autre sujet, et le depot rappelle deja qu'un delegue
 * ne se re-cible pas par champ.
 *
 * ⛔ CE MODULE N'INSTALLE AUCUN HOOK au register. Il n'ancre rien, ne remplace rien, et ne
 * touche pas au compte : il affiche du texte. C'est pour ca qu'il n'exige pas `confirmer` --
 * a la difference de `viewInvoke`, qui est un executeur de commandes generique et peut lancer
 * une bataille.
 *
 * ⛔ LE SEUL REFUS METIER : une popup qu'on ne peut plus fermer. `blocking` neutralise la croix
 * (`OnClose` sort immediatement quand il est arme) ; sans bouton OK ni bouton Annuler, il ne
 * resterait aucune sortie. La combinaison est refusee AVANT l'appel.
 */
import { findClassAnywhere, findMethodByParamCount, getFieldOffset } from "../il2cpp/helpers.js";
import { createManagedString, invokeMethod } from "../il2cpp/invoke.js";
import { queueOnMainThread } from "../runtime/queue.js";
// `Refus` vient de `view-command` (qui l'EXPORTE) et les deux helpers de `lecture-champs` : les
// deux formes sont le meme `{ ok: false; error: string }`, et c'est la convention deja suivie
// par `expedition-board` / `promo-code` / `shop`.
import { executeurVivant, premiereInstance, Refus } from "./view-command.js";
import { estRefus, refus } from "./lecture-champs.js";
import { Ctx } from "../controller.js";

const NS_POPUP = "thor.Menu";
const CLS_POPUP = "MessagePopup";
const METH_SHOW = "Show";
const METH_RELAIS = "ShowMessagePopup";

export interface OptionsMessage {
    texte?: string;
    titre?: string;
    okTexte?: string;
    annulerTexte?: string;
    avecAnnuler?: boolean;
    bloquant?: boolean;
    immediat?: boolean;
    voie?: "auto" | "relais" | "directe";
}

/** Un booleen pour `il2cpp_runtime_invoke` : un POINTEUR vers l'octet, jamais un boxe. */
function bool(v: boolean): NativePointer {
    const p = Memory.alloc(1);
    p.writeU8(v ? 1 : 0);
    return p;
}

/** Une chaine manage, ou NUL -- et le NUL a un SENS pour le natif : sur `okText`/`cancelText`
 *  il declenche le libelle localise par defaut (`UI_Message_Popup_Button_Okay` / `_Cancel`),
 *  et sur `titleText` il MASQUE la barre de titre. On ne remplace donc pas `undefined` par une
 *  chaine vide : ce ne sont pas les memes effets. */
function chaineOuNul(v: string | undefined): NativePointer {
    return typeof v === "string" && v.length > 0 ? createManagedString(v) : ptr(0);
}

/** L'instance de popup, VIVANTE.
 *
 *  ⚠ `premiereInstance` rend la PREMIERE, et le depot a mesure (2026-08-19) qu'apres une
 *  retraite suivie d'un remontage `FindObjectsByType` peut rendre une instance MORTE. On ne
 *  duplique pas l'enumeration pour compter : on interroge le discriminant que le depot nomme
 *  deja, `m_CachedPtr` -- le pointeur natif Unity, remis a zero quand l'objet est detruit.
 *  Mesure du 2026-08-26 : offset 16 sur `MessagePopup` comme sur le temoin `IdunNavigation`,
 *  non nul dans les deux cas. */
function popupVivante(): NativePointer | Refus {
    const k = findClassAnywhere(NS_POPUP, CLS_POPUP);
    if (!k) return refus(`classe ${NS_POPUP}.${CLS_POPUP} introuvable -- chemin PERIME`);
    const inst = premiereInstance(k);
    if (estRefus(inst)) {
        return refus("aucune MessagePopup enumerable -- " + (inst as Refus).error
            + ". La voie `relais` peut, elle, la faire exister (IMenu<T>.Get()).");
    }
    const p = inst as NativePointer;
    const off = getFieldOffset(k, "m_CachedPtr");
    if (off < 0) {
        return refus("`m_CachedPtr` absent de MessagePopup ni de ses parents -- la classe ne "
            + "derive plus d'`UnityEngine.Object` sur ce build, le chemin est PERIME");
    }
    let natif: NativePointer;
    try { natif = p.add(off).readPointer(); }
    catch (e) { return refus("`m_CachedPtr` illisible : " + (e as Error).message); }
    if (natif.isNull()) {
        return refus("l'instance enumeree est DETRUITE (`m_CachedPtr` nul) -- c'est le cas "
            + "mesure du remontage, ou `FindObjectsByType` rend d'abord la morte. Reessayer "
            + "apres la transition d'ecran, ou passer par la voie `relais`.");
    }
    return p;
}

/** LE FOYER. Rend un refus NOMME -- jamais un `null`, qui se lirait << rien a montrer >>. */
export function afficherMessage(o?: OptionsMessage): Record<string, unknown> | Refus {
    const texte = o?.texte;
    if (typeof texte !== "string" || texte.length === 0) {
        return refus("`texte` manquant -- une boite de dialogue sans message n'a pas d'objet");
    }
    const avecAnnuler = o?.avecAnnuler === true;
    const bloquant = o?.bloquant === true;
    // Le bouton OK est toujours affiche : c'est ce que force le relais, et c'est la seule
    // sortie garantie. Le rendre optionnel n'apporterait qu'une facon de se verrouiller.
    const avecOk = true;
    if (bloquant && !avecOk && !avecAnnuler) {
        return refus("REFUS : `bloquant` sans aucun bouton rendrait la popup INFERMABLE "
            + "(`OnClose` sort immediatement quand `blocking` est arme).");
    }

    const riche = typeof o?.titre === "string" && o.titre.length > 0
        || typeof o?.okTexte === "string" && o.okTexte.length > 0
        || typeof o?.annulerTexte === "string" && o.annulerTexte.length > 0
        || bloquant || o?.immediat === true;
    const voie = o?.voie && o.voie !== "auto" ? o.voie : (riche ? "directe" : "relais");

    if (voie === "relais") {
        if (riche) {
            return refus("la voie `relais` NE PEUT PAS porter titre, libelles, `immediat` ni "
                + "`bloquant` : `ViewCommandExecutor$$ShowMessagePopup` force ces sept "
                + "parametres a zero. Utiliser `voie: \"directe\"`.");
        }
        const exec = executeurVivant();
        if (estRefus(exec)) return exec as Refus;
        const kExec = (exec as NativePointer).readPointer();
        const mi = findMethodByParamCount(kExec, METH_RELAIS, 3);
        if (!mi) {
            return refus(`\`${METH_RELAIS}\` a 3 parametres introuvable sur l'executeur `
                + "-- chemin PERIME");
        }
        try {
            invokeMethod(mi.info, exec as NativePointer,
                         [createManagedString(texte), ptr(0), bool(avecAnnuler)]);
        } catch (e) {
            return refus("`ShowMessagePopup` a leve : " + (e as Error).message);
        }
        return { ok: true, voie: "relais", avecAnnuler, titre: null,
                 note: "chemin du jeu (`IMenu<MessagePopup>.Get()`), sans titre par construction" };
    }

    const p = popupVivante();
    if (estRefus(p)) return p as Refus;
    const inst = p as NativePointer;
    const mi = findMethodByParamCount(inst.readPointer(), METH_SHOW, 10);
    if (!mi) {
        return refus("`MessagePopup$$Show` a 10 parametres introuvable -- la signature a change "
            + "sur ce build, le chemin est PERIME (ne pas replier sur une autre arite : "
            + "l'ordre des parametres ne serait plus etabli)");
    }
    try {
        invokeMethod(mi.info, inst, [
            createManagedString(texte),      // text
            bool(avecAnnuler),               // cancel
            ptr(0),                          // okCallback     -- nul, cf. l'en-tete
            ptr(0),                          // cancelCallback -- nul, cf. l'en-tete
            bool(avecOk),                    // ok
            chaineOuNul(o?.okTexte),         // okText     (nul -> libelle localise par defaut)
            chaineOuNul(o?.annulerTexte),    // cancelText (nul -> libelle localise par defaut)
            bool(o?.immediat === true),      // immediately
            chaineOuNul(o?.titre),           // titleText  (nul -> barre de titre MASQUEE)
            bool(bloquant),                  // blocking
        ]);
    } catch (e) {
        return refus("`MessagePopup$$Show` a leve : " + (e as Error).message);
    }
    return { ok: true, voie: "directe", instance: inst.toString(),
             titre: o?.titre ?? null, avecAnnuler, bloquant, immediat: o?.immediat === true };
}

export function register(ctx: Ctx): void {
    /** Ouvrir une boite de dialogue avec NOTRE texte.
     *
     *  body: { texte, titre?, okTexte?, annulerTexte?, avecAnnuler?, bloquant?, immediat?, voie? }
     *
     *  Pas de `confirmer` : ce RPC n'ecrit pas sur le compte, il affiche du texte. Le seul refus
     *  metier est la popup infermable (cf. l'en-tete).
     *
     *  `queueOnMainThread` est OBLIGATOIRE : `Show` touche des `GameObject` (SetActive) et une
     *  animation. Toucher l'UI Unity depuis un autre fil est un plantage, pas un risque. */
    ctx.rpc.messageBox = (body?: OptionsMessage): Promise<unknown> =>
        queueOnMainThread(() => afficherMessage(body));
}
