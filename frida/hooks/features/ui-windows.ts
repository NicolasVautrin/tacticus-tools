// QUELLE VUE EST DEVANT — lu dans le gestionnaire de fenêtres DU JEU, pas déduit de l'arbre.
//
// POURQUOI CE MODULE EXISTE
// -------------------------
// `uiList` énumère les `Button` par `Object.FindObjectsByType` : une liste PLATE, sans aucun
// ordre de rendu (`FindObjectsByType` ne garantit même pas son ordre d'énumération). Côté
// Python, `gamenav/vue.py` en déduit les popups par le NOM du prefab — ça dit LESQUELS sont
// montés, jamais LEQUEL est devant. Mesure du 2026-08-09 : avec un `InterstitialPopup`
// d'offres en travers de tout l'écran, `identifier()` rendait `TRANSITOIRE`, et un appelant
// a conclu « le bouton de campagne a disparu ».
//
// Or le jeu tient son PROPRE gestionnaire de fenêtres, et il a déjà fait le calcul :
//
//     thor.Menu.MenuSystems                      ~230 slots `IMenu<T>` NOMMÉS, un par vue
//       <VisibilityManager>k__BackingField    -> idun.ui.ScreenVisibilityManager
//            _screenVisibilities                 la PILE (List<idun.ui.ScreenVisibility>)
//            _lastScreenRendered                 le dernier écran RENDU, en String
//       _hideableMenus                           ce qui peut être masqué
//       _blurredBackgroundManager                le fond flouté = signal MODAL
//
// ⚠ ET POURTANT `MenuSystems` N'EST PAS LE POINT D'ENTRÉE. Première version de ce module :
// « il porte un `Update()`, donc c'est un MonoBehaviour, donc `FindObjectsByType` le trouve ».
// Mesure au premier appel live : `instances: 0`. La réfutation était déjà dans le relevé de
// `classFields` — le dump de `MenuSystems` ne montre AUCUN `m_CachedPtr`, là où celui de
// `ScreenVisibility` le montre. `MenuSystems` est une classe C# ORDINAIRE ; son `Update()` est
// appelé à la main par un pilote. Un `Update()` ne prouve pas l'héritage : `m_CachedPtr`, si.
//
// LE POINT D'ENTRÉE EST DONC `idun.ui.ScreenVisibility`, qui EST un MonoBehaviour (mesuré :
// il hérite `m_CachedPtr`) et qui porte tout ce qui compte — sa clé, son état, son statut de
// rendu et son `Canvas`.
//
// ⚠ LE Z-ORDER UNITY NE DISCRIMINE RIEN ICI, ET LE STATUT DE RENDU SUFFIT. Ce module a
// d'abord été écrit sur l'idée « `Canvas.sortingOrder` décide qui est peint par-dessus qui ».
// Confronté le 2026-08-09 : `sortingOrder == 0` sur les SEPT écrans chargés, popups compris —
// le tri est donc inopérant. Le vrai signal est `RenderStatus`, parce que le jeu applique
// `ScreenVisibilityManager$$DisableRenderingOfEverythingBehind` : il n'y a JAMAIS deux écrans
// `Rendering` en même temps. Mesure sur l'empilement Pause + confirmation de retraite — le
// cas que `vue.py` ne sait pas départager : à l'ouverture de la confirmation, `PauseMenu`
// passe `Rendering -> NotRendering` et `MessagePopup` devient le seul rendu. `devant` est donc
// non ambigu par construction, pas par notre tri.
// Le tri par `tri` est CONSERVÉ (il coûte deux appels et deviendrait le discriminant si un
// build cessait de désactiver le rendu du dessous), mais il ne doit pas être présenté comme
// ce qui fonde la réponse.
//
// ⚠ CE QUE ÇA NE COUVRE PAS, MESURÉ : en bataille, `visibles == 0` et `devant == null`. Le HUD
// de combat n'est pas un écran rendu par cette couche. Ne pas lire ce `null` comme « rien à
// l'écran » — c'est « aucune fenêtre GÉRÉE n'est devant ».
//
// ⚠ UNE DIVERGENCE AVEC `vue.py` ACCUSE `vue.py`, PAS CE MODULE — vérifié le 2026-08-09.
// Après fermeture de l'aperçu de bataille, `devant == ShopPopup` tandis que `vue.py` rendait
// `Idun_CampaignScreen`. J'ai d'abord écrit ici que le sondage avait tort. FAUX : l'arbre
// porte bien `ShopPopup(Clone)` (avec `UI_PromotionalAsset_Layout_BattlePassExtraPremium_Full`
// — l'offre Battle Pass était réellement devant). `vue.py` COLLECTAIT le popup et le TAISAIT,
// parce que son `identifier()` donnait la priorité à l'écran monté. Corrigé côté Python.
// La leçon vaut au-delà : ce module lit l'état que le JEU tient, `vue.py` déduit d'un arbre
// d'objets. Quand les deux divergent, c'est le déduit qu'on soupçonne en premier.
//
// Ce qui reste HORS de portée par cette voie, et qu'on ne prétend pas rendre :
// `_lastScreenRendered` et `_hideableMenus` vivent sur les deux classes ORDINAIRES
// (`MenuSystems`, `ScreenVisibilityManager`) — aucune n'est énumérable, et aucun
// `ScreenVisibility` ne porte de lien retour vers son manager. Les atteindre demanderait un
// détenteur MonoBehaviour (`IdunGameHud._menuSystems`, qui n'existe qu'en bataille). Non fait,
// et dit plutôt que contourné.
//
// LA CLÉ EST UN ENUM, ET C'EST CE QUI REND LA SORTIE LISIBLE
// -----------------------------------------------------------
// Chaque `ScreenVisibility` porte `<GuiId>k__BackingField` : un `idun.tracking.GuiId`, ~250
// membres qui nomment CHAQUE vue du jeu — `34=PauseMenu`, `70=InterstitialPopup`,
// `46=GenericMessagePopup`, `25=BattlePreviewPopup`, `21=UnitDeploymentHud`, `13=GameHud`.
// Publier l'ordinal nu serait la faute que le dépôt documente partout : juste aujourd'hui,
// faux en silence au prochain build. On publie donc le MEMBRE.
//
// ⚠ ET LES NOMS DE MEMBRES SE RÉSOLVENT DEPUIS LA CLASSE DU CHAMP, JAMAIS PAR SON NOM.
// `_state` est de type `idun.ui.ScreenVisibility.State` — pour IL2CPP il s'appelle juste
// `State`, dans le namespace `idun.ui`. Un `findClassAnywhere("idun.ui", "State")`
// attraperait n'importe quel `State` du namespace et publierait des membres FAUX sans lever.
// D'où `dumpEnumClass(klass)` : on part du champ, sa classe de type EST la réponse.
//
// ⚠ CE QUE `_lastScreenRendered` DIT, ET CE QU'IL NE DIT PAS. C'est le dernier écran RENDU
// (`ScreenVisibilityManager$$SetLastScreenRendered`, appelé par `RenderScreenIfNotObstructed`)
// — l'axe du RENDU, pas celui du RAYCAST. Tant qu'il n'a pas été confronté à un empilement
// connu (Pause + confirmation de retraite), le lire comme « ce que mon clic va toucher »
// serait une extrapolation. On le publie brut et on ne conclut rien.
//
// ⚠ LES SLOTS DE MENU SONT LISTÉS, JAMAIS APPELÉS. `IMenu<T>.Get()` est un GET-OR-CREATE
// (`MenuSystems$$CreateMenu<T>`, `$$InitialiseMenu<T>`, `$$UnloadLeastRecentlyOpenedMenus`) :
// l'appeler sur 230 slots chargerait toutes les fenêtres du jeu. C'est le même piège que
// `UnitDeployment_TryPlaceUnitOnBoard`, le « getter » qui MARQUE. Ce module rend les NOMS de
// slots et la nullité du pointeur ; ouvrir un menu reste un geste explicite de l'appelant.

import {
    class_get_fields, class_get_methods, class_get_name, field_get_name, field_get_offset,
    field_get_type, findClassAnywhere, findMethod, findMethodByParamCount, getSystemType,
    method_get_name, method_get_param_count, methodEntry, s as cstr,
    type_get_class_or_element_class,
} from "../il2cpp/helpers.js";
import { dumpEnumClass } from "../il2cpp/enum-dump.js";
import { invokeMethod } from "../il2cpp/invoke.js";
import { queueOnMainThread } from "../runtime/queue.js";
import { ensureRefs } from "./ui-nav.js";
import { Ctx } from "../controller.js";

interface Champ { nom: string; offset: number; typeKlass: NativePointer | null }

/** Le champ NOMMÉ d'une classe : son offset ET la classe de son type. Rend `null` quand le
 *  champ n'existe pas dans CE build — l'appelant doit le DIRE, pas lire à l'offset 0. */
function champ(klass: NativePointer, nom: string): Champ | null {
    let k = klass;
    while (!k.isNull()) {
        const it = Memory.alloc(Process.pointerSize);
        it.writePointer(ptr(0));
        let f: NativePointer;
        while (!(f = class_get_fields(k, it) as NativePointer).isNull()) {
            if (cstr(field_get_name(f) as NativePointer) !== nom) continue;
            let tk: NativePointer | null = null;
            try {
                tk = type_get_class_or_element_class(
                    field_get_type(f) as NativePointer) as NativePointer;
                if (tk.isNull()) tk = null;
            } catch { tk = null; }
            return { nom, offset: field_get_offset(f) as number, typeKlass: tk };
        }
        // `class_get_parent` n'est pas importé ici : les champs visés sont tous DÉCLARÉS par
        // la classe elle-même (mesuré par `classFields`). Remonter la hiérarchie ferait
        // porter au module une dette qu'il n'a pas.
        break;
    }
    return null;
}

function lirePointeur(obj: NativePointer, c: Champ | null): NativePointer | null {
    if (c === null || obj.isNull()) return null;
    try {
        const p = obj.add(c.offset).readPointer();
        return p.isNull() ? null : p;
    } catch { return null; }
}

function lireInt(obj: NativePointer, c: Champ | null): number | null {
    if (c === null || obj.isNull()) return null;
    try { return obj.add(c.offset).readS32(); } catch { return null; }
}

/** ordinal -> membre, construit UNE fois par classe d'enum. `null` = enum non dumpable :
 *  l'appelant publie alors l'ordinal SEUL, il ne fabrique pas un nom. */
function tableEnum(k: NativePointer | null): Record<number, string> | null {
    if (k === null) return null;
    const brut = dumpEnumClass(k);
    if (!brut) return null;
    const out: Record<number, string> = {};
    for (const [nom, val] of Object.entries(brut)) {
        const n = parseInt(val, 10);
        if (!Number.isNaN(n) && out[n] === undefined) out[n] = nom;
    }
    return out;
}

/** L'ordinal ET son membre. Le membre vaut `null` quand la table manque — jamais une
 *  invention, jamais l'ordinal déguisé en nom. */
function membre(
    v: number | null, t: Record<number, string> | null,
): { v: number | null; nom: string | null } {
    if (v === null) return { v: null, nom: null };
    return { v, nom: t ? (t[v] ?? null) : null };
}

// ---------------------------------------------------------------------------------------
// LE JOURNAL DES TRANSITIONS — ce qu'un SONDAGE ne peut pas voir
// ---------------------------------------------------------------------------------------
// `uiWindows` répond « qui est devant MAINTENANT ». Entre deux appels il ne voit rien : un
// popup qui s'ouvre et se referme seul est invisible, et l'ordre de deux bascules dans la
// même frame est perdu. C'est le même écart qu'entre `observeBattle` et `battleEvents`.
//
// Les points de transition sont NOMMÉS et portés par UNE seule classe, non générique — donc
// `findMethod` mord directement, sans le piège gshared qui a laissé `bucket-audit` `enabled`
// avec 0 fire :
//
//     ScreenVisibilityManager$$HandleOnScreenStartedShowing (this, screen)
//     ScreenVisibilityManager$$HandleOnScreenFinishedShowing(this, screen)
//     ScreenVisibilityManager$$HandleOnScreenStartedHiding  (this, screen)
//     ScreenVisibilityManager$$Register / $$Unregister      (this, screen)
//
// `Register`/`Unregister` expliquent ce que le sondage a mesuré sans pouvoir l'expliquer : la
// liste passe de 7 à 8 écrans quand `PauseMenu` se charge (`UnloadLeastRecentlyOpenedMenus`).
//
// ⚠ `Register` PORTE DEUX SURCHARGES de même nom ET même arité (deux adresses distinctes au
// décompilé). `findMethod` en rendrait UNE, au hasard, et le journal raterait la moitié des
// inscriptions sans jamais le dire. On s'attache donc à TOUTES les méthodes portant le nom, et
// on publie le compte (`ancrages`) pour que « 0 fire » se distingue de « pas accroché ».
//
// ⚠ ET LES DEUX SURCHARGES NE PRENNENT PAS LE MÊME TYPE — mesuré dans `frida/methods.tsv` :
//     idun.ui.ScreenVisibilityManager.Register    screen:idun.ui.IScreenVisibility
//     idun.ui.ScreenVisibilityManager.Register    screen:idun.ui.ITemporarilyHideable
//     idun.ui.ScreenVisibilityManager.Unregister  screen:idun.ui.ITemporarilyHideable
// Ce sont des INTERFACES : rien ne garantit que l'objet reçu soit un `idun.ui.ScreenVisibility`,
// et lire `<GuiId>k__BackingField` à SON offset sur un objet d'une autre classe rend un entier
// arbitraire. C'est mesuré, pas redouté : le journal publiait `ordinal -1988785488` sur deux
// transitions de chaque cycle de warmup (#390-r2, deux runs identiques à 28/28 transitions).
// D'où `classe` ci-dessous — le nom IL2CPP de la classe RÉELLE de l'objet. L'ordinal reste
// publié tel quel (le rabattre sur `null` masquerait la mesure) ; `classe` est ce qui le rend
// LISIBLE : `idun.ui.BlurredBackgroundScreen` n'est pas un écran, c'est le wrapper de fond
// flouté que `BlurredBackgroundScreenVisibilityManagerProxy$$CreateBlurredBackgroundWrapper`
// inscrit EN PLUS du vrai écran — ce qui explique aussi pourquoi les transitions vont par
// PAIRES (`montre-debut <wrapper>` puis `montre-debut PauseMenu`).

/** LES LIBELLÉS DE TRANSITION — foyer unique. Ils sont publiés dans `uiWindowEvents` ET
 *  consommés comme SIGNAL par `warmup-retreat-signal.ts` (#390-r2), qui ne peut pas importer
 *  ce module (il est pur, donc exécutable hors Frida) et redéclare donc les siens. C'est
 *  `frida/tools/probe-390-r2-signal-retraite.ts` étage 2 qui garde les deux appariés — une
 *  divergence rendrait le signal muet sans rien casser d'autre. */
export const TRANSITION = {
    /** `ScreenVisibilityManager$$HandleOnScreenStartedShowing` */
    montreDebut: "montre-debut",
    /** `ScreenVisibilityManager$$HandleOnScreenFinishedShowing` */
    montreFin: "montre-fin",
    /** `ScreenVisibilityManager$$HandleOnScreenStartedHiding` */
    cacheDebut: "cache-debut",
    /** `ScreenVisibilityManager$$Register` (les DEUX surcharges) */
    inscrit: "inscrit",
    /** `ScreenVisibilityManager$$Unregister` */
    retire: "retire",
} as const;

export interface TransitionVue {
    quoi: string;
    gui: { v: number | null; nom: string | null };
    /** Nom IL2CPP de la classe réelle de l'objet reçu. `null` = illisible. */
    classe: string | null;
}
interface Transition extends TransitionVue { n: number }

const journal: Transition[] = [];
/** Tampon glissant. Publier `ecartes` : un débordement muet ferait dater à tort une séquence. */
let ecartes = 0;
let recus = 0;
let actif = false;
let ancrages: number | null = null;   // null = hooks JAMAIS posés (≠ posés et 0 fire)
const PLAFOND_JOURNAL = 2000;

/** Les abonnés PUSH (cf. `ecouterTransitions`). Volontairement SÉPARÉS du drapeau `actif` et
 *  du tampon : ceux-là sont l'état de l'OPÉRATEUR. */
type Abonne = (t: TransitionVue) => void;
const abonnes = new Set<Abonne>();

/** Résolu une fois : le champ `GuiId` de `ScreenVisibility` et sa table de membres. */
let cGuiCache: Champ | null | undefined;
let tGuiCache: Record<number, string> | null = null;

function guiDeLEcran(screen: NativePointer): { v: number | null; nom: string | null } {
    if (cGuiCache === undefined) {
        const k = findClassAnywhere("idun.ui", "ScreenVisibility");
        cGuiCache = k ? champ(k, "<GuiId>k__BackingField") : null;
        tGuiCache = tableEnum(cGuiCache?.typeKlass ?? null);
    }
    return membre(lireInt(screen, cGuiCache ?? null), tGuiCache);
}

/** Le nom de la classe RÉELLE d'un objet IL2CPP : son premier slot est son `Il2CppClass*`.
 *  Rend `null` plutôt que d'inventer — un nom faux serait pire que pas de nom. */
function classeDe(obj: NativePointer): string | null {
    try {
        if (obj.isNull()) return null;
        const k = obj.readPointer();
        if (k.isNull()) return null;
        return cstr(class_get_name(k) as NativePointer);
    } catch { return null; }
}

function noter(quoi: string, screen: NativePointer): void {
    // Sortie immédiate quand personne n'écoute : le drapeau `actif` gate le JOURNAL, les
    // abonnés sont indépendants — mais aucun des deux ne doit faire payer les lectures
    // quand il n'y a rien à alimenter.
    if (!actif && abonnes.size === 0) return;
    try {
        const vue: TransitionVue = {
            quoi, gui: guiDeLEcran(screen), classe: classeDe(screen),
        };
        // Diffusion AVANT le gate : un abonné n'a pas à dépendre de l'état du journal de
        // l'opérateur, et le warmup ne doit pas avoir à l'armer (donc à l'éteindre après,
        // ce qui écraserait une observation en cours).
        for (const cb of abonnes) {
            try { cb(vue); } catch { /* un abonné qui jette n'emporte pas les autres */ }
        }
        if (!actif) return;
        recus++;
        journal.push({ n: recus, ...vue });
        if (journal.length > PLAFOND_JOURNAL) {
            ecartes += journal.length - PLAFOND_JOURNAL;
            journal.splice(0, journal.length - PLAFOND_JOURNAL);
        }
    } catch { /* un capteur ne jette jamais */ }
}

/** Attache TOUTES les méthodes portant ce nom — cf. l'avertissement sur les surcharges. */
function ancrer(klass: NativePointer, nom: string, quoi: string): number {
    let poses = 0;
    const it = Memory.alloc(Process.pointerSize);
    it.writePointer(ptr(0));
    let mi: NativePointer;
    while (!(mi = class_get_methods(klass, it) as NativePointer).isNull()) {
        if (cstr(method_get_name(mi) as NativePointer) !== nom) continue;
        if ((method_get_param_count(mi) as number) !== 1) continue;
        try {
            const p = methodEntry(mi);
            if (p === null || p.isNull()) continue;
            Interceptor.attach(p, {
                onEnter(args) { noter(quoi, args[1]); },
            });
            poses++;
        } catch { /* une ancre qui echoue ne doit pas emporter les autres */ }
    }
    return poses;
}

/** UNE ÉCOUTE PUSH DES TRANSITIONS — ce qu'un consommateur INTERNE au bundle peut attendre
 *  sans sonder. Ajouté par #390-r2 pour `retreatToCampaign` (`warmup-singletons.ts`), qui
 *  détectait la sortie de bataille en interrogeant l'UI toutes les 250 ms.
 *
 *  ⚠ POURQUOI CE N'EST **PAS** UN `uiWindowEvents({start:true})` SUIVI D'UN `{stop:true}`.
 *  Le drapeau `actif`, le tampon et `recus` sont l'état de l'OPÉRATEUR : un `start` du warmup
 *  puis son `stop` ÉTEINDRAIT un journal qu'un humain venait d'armer, et un `clear` effacerait
 *  ses transitions. L'abonnement est purement ADDITIF — il ne lit ni n'écrit `actif`, ne touche
 *  pas au tampon, et se retire à `fermer()`.
 *
 *  ⚠ `ancrages === null` = LE SIGNAL N'EXISTE PAS (classe introuvable). Tri-état : l'appelant
 *  doit le DIRE et retomber sur son filet, jamais le lire comme « rien ne s'est passé ».
 *
 *  COÛT MESURÉ (#390-r2, build rnca9r7q6c) : un cycle de warmup complet — entrée en bataille,
 *  pause, retraite, retour campagne — produit **28** transitions, dont 6 après le clic de
 *  confirmation. Ces points sont FROIDS ; ils ne sont pas dans le régime de `ui-mutations.ts`
 *  (`GameObject$$SetActive`), qui lui n'est jamais auto-armé. */
export interface EcouteTransitions {
    /** Les transitions vues DEPUIS l'abonnement, dans l'ordre d'arrivée. */
    vues: () => readonly TransitionVue[];
    /** Résout sur la PREMIÈRE transition d'index `>= depuis` satisfaisant `pred` — déjà
     *  arrivée (balayage du tampon local) ou à venir (push). `null` au plafond.
     *
     *  Le balayage préalable n'est pas un sondage : il ferme la fenêtre entre le geste qui
     *  déclenche la transition et l'appel — sans lui, la transition la plus rapide serait
     *  perdue, et c'est exactement celle qui compte. */
    attendre: (
        pred: (t: TransitionVue) => boolean, plafondMs: number, depuis?: number,
    ) => Promise<TransitionVue | null>;
    /** Nombre d'`Interceptor` posés. `null` = aucun, donc AUCUN signal possible. */
    ancrages: number | null;
    fermer: () => void;
}

export function ecouterTransitions(): EcouteTransitions {
    if (ancrages === null) ancrages = installerAncrages();
    const vues: TransitionVue[] = [];
    const reveils = new Set<() => void>();
    const cb: Abonne = (t) => {
        vues.push(t);
        for (const r of [...reveils]) r();
    };
    abonnes.add(cb);
    return {
        ancrages,
        vues: () => vues,
        fermer: () => { abonnes.delete(cb); reveils.clear(); },
        attendre: (pred, plafondMs, depuis = 0) => new Promise<TransitionVue | null>(
            (resolve) => {
                let i = Math.max(0, depuis);
                let fini = false;
                let minuteur: ReturnType<typeof setTimeout> | null = null;
                const terminer = (v: TransitionVue | null): void => {
                    if (fini) return;
                    fini = true;
                    reveils.delete(examiner);
                    if (minuteur !== null) clearTimeout(minuteur);
                    resolve(v);
                };
                function examiner(): void {
                    for (; i < vues.length; i++) {
                        const t = vues[i] as TransitionVue;
                        if (pred(t)) { terminer(t); return; }
                    }
                }
                reveils.add(examiner);
                examiner();                       // ce qui est DÉJÀ arrivé
                if (fini) return;
                minuteur = setTimeout(() => terminer(null), plafondMs);
            }),
    };
}

function installerAncrages(): number | null {
    const klass = findClassAnywhere("idun.ui", "ScreenVisibilityManager");
    if (!klass) return null;
    let total = 0;
    total += ancrer(klass, "HandleOnScreenStartedShowing", TRANSITION.montreDebut);
    total += ancrer(klass, "HandleOnScreenFinishedShowing", TRANSITION.montreFin);
    total += ancrer(klass, "HandleOnScreenStartedHiding", TRANSITION.cacheDebut);
    total += ancrer(klass, "Register", TRANSITION.inscrit);
    total += ancrer(klass, "Unregister", TRANSITION.retire);
    Interceptor.flush();
    return total;
}

export function register(ctx: Ctx): void {
    /** Le gestionnaire de fenêtres DU JEU, tel quel. Read-only, n'ouvre et ne clique rien.
     *
     *  body: { menus?: true }  -> inclut la liste des ~230 slots (verbeux, hors défaut)
     *
     *  TRI-ÉTAT partout : `null` = PAS MESURÉ (champ absent de ce build, liste illisible),
     *  jamais rabattu sur vide/0/faux. `champsAbsents` dit LESQUELS, pour qu'un `null` se
     *  lise comme une péremption et non comme un état du jeu.
     */
    ctx.rpc.uiWindows = (): Promise<unknown> =>
        queueOnMainThread(() => {
            const kSv = findClassAnywhere("idun.ui", "ScreenVisibility");
            if (!kSv) {
                return { ok: false, error: "classe idun.ui.ScreenVisibility introuvable -- "
                    + "la couche UI a ete renommee, ou le build a change" };
            }

            // ⚠ IL FAUT LA SURCHARGE QUI INCLUT LES INACTIFS, ET C'EST UNE MESURE.
            // `uiList` utilise `FindObjectsByType(Type, FindObjectsSortMode)` — cette
            // surcharge-là EXCLUT les objets inactifs. Sur les `Button` ça tombe juste (on ne
            // veut que le cliquable) ; ici ça a rendu **0 écran** alors que la classe résout
            // et hérite bien de MonoBehaviour (chaîne mesurée :
            // `ScreenVisibility <- MonoBehaviour <- Object`). Un écran MASQUÉ est exactement
            // ce qu'on veut voir — c'est la moitié de la réponse à « qui est devant ».
            // D'où la surcharge à 3 arguments, `FindObjectsInactive.Include = 1`.
            const kObj = findClassAnywhere("UnityEngine", "Object");
            const mi3 = kObj ? findMethodByParamCount(kObj, "FindObjectsByType", 3) : null;
            const sortMode = Memory.alloc(4).writeS32(0);
            const inclureInactifs = Memory.alloc(4).writeS32(1);
            let arr: NativePointer;
            let voieInactifs: boolean;
            if (mi3 !== null) {
                voieInactifs = true;
                arr = invokeMethod(mi3.info, null,
                                   [getSystemType(kSv), inclureInactifs, sortMode]);
            } else {
                // Repli sur la surcharge de `uiList`. On le DIT (`voieInactifs: false`) :
                // sans ça, une liste amputée des écrans masqués se lirait comme complète.
                voieInactifs = false;
                arr = invokeMethod(ensureRefs().findObjectsByType.info, null,
                                   [getSystemType(kSv), sortMode]);
            }
            const n = arr.isNull() ? 0 : arr.add(0x18).readS32();
            if (n <= 0) {
                return { ok: false, ecrans: 0, voieInactifs,
                    error: "aucun ScreenVisibility vivant -- l'UI n'est pas montee "
                        + "(jeu en cours de chargement ?)" };
            }

            const absents: string[] = [];
            const exige = (k: NativePointer, nom: string): Champ | null => {
                const c = champ(k, nom);
                if (c === null) absents.push(nom);
                return c;
            };
            const cGui = exige(kSv, "<GuiId>k__BackingField");
            const cEtat = exige(kSv, "_state");
            const cRendu = exige(kSv, "<RenderStatus>k__BackingField");
            const cOverlay = exige(kSv, "OverlayType");
            const cCanvas = exige(kSv, "Canvas");
            const cRay = exige(kSv, "Raycaster");

            const tGui = tableEnum(cGui?.typeKlass ?? null);
            const tEtat = tableEnum(cEtat?.typeKlass ?? null);
            const tRendu = tableEnum(cRendu?.typeKlass ?? null);
            const tOverlay = tableEnum(cOverlay?.typeKlass ?? null);

            // Le z-order UNITY. `null` = non résolu (méthode absente) — jamais 0, qui est un
            // ordre de tri parfaitement légitime.
            const kCanvas = findClassAnywhere("UnityEngine", "Canvas");
            const miTri = kCanvas ? findMethod(kCanvas, "get_sortingOrder") : null;
            const miSurcharge = kCanvas ? findMethod(kCanvas, "get_overrideSorting") : null;
            if (kCanvas === null) absents.push("UnityEngine.Canvas");

            const lireTri = (cv: NativePointer | null): number | null => {
                if (cv === null || miTri === null) return null;
                try { return invokeMethod(miTri.info, cv, []).add(0x10).readS32(); }
                catch { return null; }
            };
            const lireSurcharge = (cv: NativePointer | null): boolean | null => {
                if (cv === null || miSurcharge === null) return null;
                try {
                    return invokeMethod(
                        miSurcharge.info, cv, []).add(0x10).readU8() !== 0;
                } catch { return null; }
            };

            const ecrans = [];
            for (let i = 0; i < n; i++) {
                const e = arr.add(0x20 + i * Process.pointerSize).readPointer();
                if (e.isNull()) continue;
                const cv = lirePointeur(e, cCanvas);
                ecrans.push({
                    gui: membre(lireInt(e, cGui), tGui),
                    etat: membre(lireInt(e, cEtat), tEtat),
                    rendu: membre(lireInt(e, cRendu), tRendu),
                    overlay: membre(lireInt(e, cOverlay), tOverlay),
                    tri: lireTri(cv),
                    triSurcharge: lireSurcharge(cv),
                    aRaycaster: cRay === null ? null : lirePointeur(e, cRay) !== null,
                });
            }

            // Tri par z-order — SANS EFFET aujourd'hui (`tri == 0` partout, mesuré), gardé
            // comme filet si un build cessait de désactiver le rendu du dessous. L'ordre
            // d'énumération de `FindObjectsByType` n'est PAS une pile : le publier tel quel
            // se lirait comme un ordre alors que c'est un ordre de tas.
            ecrans.sort((a, b) => (b.tri ?? -1e9) - (a.tri ?? -1e9));

            // « DEVANT » = celui QUI REND ENCORE, et c'est le vrai discriminant : le jeu
            // n'en laisse qu'UN (`DisableRenderingOfEverythingBehind`). Confronté sur
            // l'empilement Pause + confirmation — `PauseMenu` bascule en `NotRendering` dès
            // que `MessagePopup` s'ouvre. Compter un `NotRendering` désignerait comme premier
            // plan quelque chose que le joueur ne voit pas.
            const visible = ecrans.filter((x) => x.rendu.nom === "Rendering");
            return {
                ok: true,
                ecrans: n,
                voieInactifs,
                devant: visible.length ? visible[0].gui.nom : null,
                visibles: visible.length,
                pile: ecrans,
                champsAbsents: absents,
            };
        });

    /** Le JOURNAL des transitions d'UI — ce qu'un sondage ne peut pas voir.
     *
     *  body: { start?, stop?, clear?, depuis?: number, max?: number }
     *
     *  `depuis = recus` du relevé précédent rend exactement les nouvelles, sans trou ni
     *  doublon — à condition qu'`ecartes` n'ait pas bougé, ce que la réponse publie aussi.
     *
     *  ⚠ `stop` ARRÊTE D'ENREGISTRER, il ne DÉTACHE PAS. Retirer des `Interceptor` posés sur
     *  cinq points chauds pour les reposer ensuite coûte plus cher que le drapeau, et un
     *  détachement partiel laisserait un journal muet qui se lirait comme « rien ne s'est
     *  passé ». Le dire vaut mieux que le maquiller.
     *
     *  ⚠ `ancrages: null` = hooks JAMAIS POSÉS. À ne pas confondre avec `ancrages: 5` et zéro
     *  transition : le premier est une panne, le second une mesure. */
    ctx.rpc.uiWindowEvents = (body?: {
        start?: boolean; stop?: boolean; clear?: boolean;
        depuis?: number; max?: number;
    }): unknown => {
        if (body?.stop) { actif = false; }
        if (body?.start) {
            if (ancrages === null) ancrages = installerAncrages();
            if (ancrages === null) {
                return { ok: false, error: "classe idun.ui.ScreenVisibilityManager "
                    + "introuvable -- aucun ancrage pose" };
            }
            actif = true;
        }
        if (body?.clear) { journal.length = 0; ecartes = 0; recus = 0; }

        const depuis = Math.max(0, (body?.depuis ?? 0) - ecartes);
        const max = Math.max(1, Math.min(body?.max ?? 200, 2000));
        const tranche = journal.slice(depuis, depuis + max);
        return {
            ok: true,
            actif,
            ancrages,
            recus,
            ecartes,
            enTampon: journal.length,
            rendus: tranche.length,
            curseur: ecartes + depuis + tranche.length,
            transitions: tranche,
        };
    };
}
