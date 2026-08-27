// LE PLATEAU — tout ce qui LIT l'etat du deploiement, l'acces au HUD par lequel on le lit, et le
// retrait d'une unite du runner.
//
// Extrait de `deployment-draft.ts` le 2026-08-26. Frontiere mesuree : 30 symboles, ZERO entree.
//
// ⚠ L'ACCES AU HUD EST DANS CE MODULE, ET C'EST LA MESURE QUI L'A IMPOSE. Une premiere frontiere
// ne prenait que les lecteurs : elle reclamait alors `hudInstance`, `assurerHud`, `compteDict`,
// `etatDuBouton` a l'autre module -- donc un cycle. On lit le plateau A TRAVERS le HUD ; les deux
// ne se separent pas.
//
// ⚠ ET IL SORT AVANT LA MEMOIRE. Tentee d'abord, l'extraction de la memoire reclamait NEUF
// symboles d'ici (`unitesDuPlateau`, `compteJoueur`, `assurerHud`, `marquerLesUnitesDuPlateau`...)
// : un pont a neuf entrees aurait ete pire que le monolithe. L'ordre des coupes ne se choisit
// pas, il se derive de ce que le compilateur reclame.
//
// ⚠ `vuesJeu` VIT ICI, PAS DANS LA MEMOIRE. C'est l'`IdunGameViews` captee au passage : une
// donnee de PLATEAU, que la memoire ne fait que consulter. La ranger avec la memoire etait une
// erreur de classement -- et c'est elle qui rendait la frontiere de la memoire infranchissable.

import { Ctx } from "../controller.js";
import {
    findClassAnywhere, findMethodByParamCount, findMethod, getFieldOffset, readIl2cppString,
    class_get_name, class_instance_size, class_get_element_class, class_is_valuetype, s,
} from "../il2cpp/helpers.js";
import { invokeMethod, createManagedString, il2cpp_object_new } from "../il2cpp/invoke.js";
import { gcRoot } from "../il2cpp/gc-root.js";
import { queueOnMainThread } from "../runtime/queue.js";
import { state } from "../game/state.js";
import { elementsDeListe, estRefus as estRefusLecture } from "./lecture-champs.js";
import { Refus, refus, ghidraVA, boolBoxe, NS_VIEWS, CLS_VIEWS } from "./deployment-socle.js";
import { NS_PREFAB, CLS_VIEWS_PREFAB, vuesDePose, dicoVivant } from "./deployment-prefab.js";
import { classeDerriere } from "./deployment-pool.js";
import { premiereInstance } from "./view-command.js";

/** LES TROIS ETATS QUE LES CAPTEURS DE `deployment-draft` ECRIVENT. Ils se LISENT directement
 *  (ESM lie les exports en vif) ; seule l'AFFECTATION passe par un accesseur nomme. */
export function definirHudInstance(p: NativePointer | null): void { hudInstance = p; }
export function definirHudSource(v: "Show" | "scene" | null): void { hudSource = v; }
export function definirVuesJeu(p: NativePointer | null): void { vuesJeu = p; }

// ─────────────────────────────────────────────────────────────────────────────
// LE PLAFOND : ON NE PEUT PLUS EMPILER, EN SANDBOX COMME EN PARTIE RÉELLE
// ─────────────────────────────────────────────────────────────────────────────
//
// ⚠ LA CAUSE STRUCTURELLE DE L'EMPILEMENT, ET ELLE EST DÉJÀ DOCUMENTÉE PLUS BAS DANS CE FICHIER :
// il y a DEUX comptabilités du déploiement -- les `PlaceholderUnitView` que le HUD tient, et les
// unités RÉELLES du runner -- et **aucune ne nourrit l'autre**. Chaque voie de pose ne consultait
// que la sienne, donc rien n'empêchait d'ajouter par l'une ce que l'autre tenait déjà.
//
// Mesuré le 2026-08-20 : le HUD tenait les 5 placeholders de l'équipe du JOUEUR ; notre rejeu a
// appliqué 5 `AddUnitMessage` de plus au runner ; le START a ensuite converti les placeholders
// PAR-DESSUS. Résultat : **10 unités pour un plafond de 5**, et un essai de boss de guilde perdu.
//
// LE CRAN, et il ne dépend d'aucune vigilance : avant toute pose, on ADDITIONNE les deux
// comptabilités et on les confronte au plafond que le HUD a lui-même reçu
// (`UnitDeploymentHud$$Show(units, minUnitsPossible, maxUnitsPossible, options)`).
//
// ⚠ TRI-ÉTAT, ENCORE : un plafond ou une comptabilité qu'on n'a PAS SU LIRE fait REFUSER. Un
// compteur illisible rendu comme un zéro est exactement ce qui autorise l'empilement -- c'est le
// même travers que le `duJoueur=0` lu pour « plateau vide » pendant l'incident.

export interface EtatDeploiement {
    reelles: number; nomsReels: Array<string | null>; cases: string[];
    placeholders: number; nomsPlaceholders: Array<string | null>;
    max: number; machines: boolean;
}

/**
 * Les `unitId` que le HUD tient en placeholders.
 *
 * ⚠ SANS EUX, LE CONTRÔLE DE DOUBLON EST AVEUGLE À LA MOITIÉ DU PLATEAU -- et c'est mesuré :
 * la re-pose d'une unité déjà présente n'a été refusée que parce que le PLAFOND était atteint.
 * Un plafond qui rattrape un doublon par accident n'est pas un contrôle de doublon.
 *
 * La taille d'élément est DÉRIVÉE (`class_instance_size` de la classe d'élément moins l'en-tête),
 * jamais recopiée — même exigence que `deploymentPlacees`. Non dérivable ⇒ `null`, qui fait
 * REFUSER en amont, jamais une liste vide qui se lirait « aucun doublon ».
 */
export function nomsDesPlaceholders(lst: NativePointer, taille: number): Array<string | null> | null {
    try {
        const kl = lst.readPointer();
        const offItems = getFieldOffset(kl, "_items");
        if (offItems < 0) return null;
        const items = lst.add(offItems).readPointer();
        if (items.isNull()) return null;
        const kElem = class_get_element_class ? class_get_element_class(items.readPointer()) : null;
        if (kElem === null || class_is_valuetype === null || class_instance_size === null) {
            return null;
        }
        const octets = (class_is_valuetype(kElem) as number) !== 0
            ? (class_instance_size(kElem) as number) - 2 * Process.pointerSize
            : Process.pointerSize;
        if (!(octets > 0 && octets <= 512)) return null;
        const base = items.add(4 * Process.pointerSize);
        const out: Array<string | null> = [];
        for (let i = 0; i < Math.min(taille, 32); i++) {
            // Les 8 premiers octets de l'entrée sont le `System.String` de l'`unitId` -- relevé
            // sur les entrées vivantes, pas supposé.
            const sp = base.add(i * octets).readPointer();
            out.push(sp.isNull() ? null : readIl2cppString(sp));
        }
        return out;
    } catch { return null; }
}

/** Les DEUX comptabilités + le plafond, ou un `Refus` dès qu'une lecture manque. */
export function etatDuDeploiement(): EtatDeploiement | Refus {
    const u = unitesDuPlateau();
    if (!Array.isArray(u)) {
        return refus("plateau NON LISIBLE (" + u + ") -- on ne pose pas à l'aveugle : une "
            + "comptabilité illisible rendue comme un zéro est ce qui autorise l'empilement");
    }
    const miennes = u.filter((x) => x.duJoueur);
    const hud = assurerHud();
    if (hud === null) {
        return refus("aucun `UnitDeploymentHud` -- ni capté à son `Show`, ni rendu par la scène. "
            + "Le plafond de déploiement est donc INCONNU. Ce n'est PAS « pas de plafond ».");
    }
    const k = findClassAnywhere(NS_HUD, CLS_HUD);
    if (!k) return refus(`\`${NS_HUD}.${CLS_HUD}\` INTROUVABLE sur ce build`);
    const offMax = getFieldOffset(k, "_maxUnitsPossible");
    const offMow = getFieldOffset(k, "_hasMachinesOfWar");
    const offPl = getFieldOffset(k, "_currentlyPlacedUnits");
    if (offMax < 0 || offPl < 0) {
        return refus(`champs ABSENTS de ce build : _maxUnitsPossible=${offMax} `
            + `_currentlyPlacedUnits=${offPl} -- chemin PÉRIMÉ, pas de repli sur un offset en dur`);
    }
    let placeholders: number;
    let nomsPh: Array<string | null> | null;
    try {
        const lst = hud.add(offPl).readPointer();
        if (lst.isNull()) return refus("`_currentlyPlacedUnits` est NULLE -- comptabilité du HUD "
            + "non mesurable");
        const offSize = getFieldOffset(lst.readPointer(), "_size");
        if (offSize < 0) return refus("`List._size` ABSENT -- comptabilité du HUD non mesurable");
        placeholders = lst.add(offSize).readS32();
        nomsPh = nomsDesPlaceholders(lst, placeholders);
    } catch (e) {
        return refus("`_currentlyPlacedUnits` ILLISIBLE : " + (e as Error).message);
    }
    if (nomsPh === null && placeholders > 0) {
        return refus(`les ${placeholders} placeholder(s) du HUD ne sont pas NOMMABLES -- le `
            + "contrôle de doublon serait aveugle à eux. Une liste illisible n'est pas une liste "
            + "vide.");
    }
    return {
        reelles: miennes.length,
        nomsReels: miennes.map((x) => x.unitId),
        cases: miennes.map((x) => `${x.col},${x.row}`),
        placeholders,
        nomsPlaceholders: nomsPh ?? [],
        max: hud.add(offMax).readS32(),
        machines: offMow >= 0 && hud.add(offMow).readU8() !== 0,
    };
}

/**
 * Le nombre d'unités DISTINCTES déployées, les deux comptabilités confondues.
 *
 * ⚠ NE PAS ADDITIONNER LES DEUX COMPTES -- c'est faux, et mesuré. En voie runner-directe une
 * même unité figurait DANS LES DEUX (la voie commit créait l'unité réelle, et l'entrée du HUD
 * survit) : relevé le 2026-08-20, 5 unités réelles pour 6 entrées de `_currentlyPlacedUnits`,
 * soit une somme de 11 pour un plafond de 6. Le plafond aurait refusé des poses LÉGITIMES.
 * L'invariant porte sur les unités DISTINCTES, donc sur l'UNION par `unitId`.
 */
export function unitesDistinctes(e: EtatDeploiement): string[] {
    const vus: string[] = [];
    for (const n of e.nomsReels.concat(e.nomsPlaceholders)) {
        if (typeof n === "string" && n !== "" && vus.indexOf(n) < 0) vus.push(n);
    }
    return vus;
}

/**
 * Rend un `Refus` quand la pose EMPILERAIT, ou `null` quand elle est légitime.
 *
 * `p === null` ⇒ on ne vérifie que le plafond (c'est le cas du START, qui ne pose rien lui-même
 * mais convertit tout ce qui traîne).
 *
 * ⚠ IL N'Y A PAS D'ÉCHAPPATOIRE ICI, ET C'EST DÉLIBÉRÉ. C'est même le SEUL garde qui reste
 * depuis le retrait de `refusHorsSandbox` (2026-08-21), et il tient parce qu'il porte sur le
 * FAIT -- combien d'unités le déploiement totalise -- et non sur l'IDENTITÉ de la source. Il ne
 * peut donc pas se tromper de bataille, ni refuser un geste légitime parce qu'il n'a pas su
 * reconnaître le mode. Aucun empilement n'est légitime : on vide d'abord
 * (`deploymentRetirer` / le clear du rejeu), on ne force pas.
 */
export function refusSiEmpilement(p: Pose | null, quoi: string): Refus | null {
    const e = etatDuDeploiement();
    if ("ok" in e) return refus(`REFUS (${quoi}) : ${e.error}`);
    const total = unitesDistinctes(e).length;
    // Le plafond porte sur les unités STANDARD ; une machine de guerre s'y ajoute quand le mode
    // en autorise une. On ne cherche pas à démêler laquelle est laquelle dans les deux listes :
    // la borne haute suffit à interdire l'empilement, et elle ne peut pas refuser à tort une
    // composition légitime.
    const borne = e.max + (e.machines ? 1 : 0);
    if (p !== null) {
        // ⚠ LES DEUX COMPTABILITÉS, pas seulement les unités réelles. Mesuré le 2026-08-20 : avec
        // le seul contrôle sur les réelles, une re-pose n'était refusée que parce que le PLAFOND
        // était atteint -- donc par accident, et donc pas du tout dès qu'il reste une place.
        if (e.nomsReels.indexOf(p.unitId) >= 0) {
            return refus(`REFUS (${quoi}) : \`${p.unitId}\` est DÉJÀ une unité réelle du plateau `
                + "-- la poser une seconde fois la dédoublerait.");
        }
        if (e.nomsPlaceholders.indexOf(p.unitId) >= 0) {
            return refus(`REFUS (${quoi}) : \`${p.unitId}\` est DÉJÀ un placeholder du HUD -- la `
                + "poser créerait le doublon HUD/runner qui a produit les 10 unités du "
                + "2026-08-20.");
        }
        if (e.cases.indexOf(`${p.col},${p.row}`) >= 0) {
            return refus(`REFUS (${quoi}) : la case (${p.col},${p.row}) est DÉJÀ occupée par une `
                + "unité réelle. Une pose sur case occupée échoue EN SILENCE côté natif.");
        }
        if (total >= borne) {
            return refus(`REFUS (${quoi}) : le déploiement est PLEIN -- ${total} unité(s) `
                + `DISTINCTE(S) (${e.reelles} réelle(s), ${e.placeholders} placeholder(s), `
                + `union par unitId), plafond ${borne} (max ${e.max}`
                + `${e.machines ? " + 1 machine" : ""}). Poser de plus EMPILERAIT : c'est ainsi `
                + "qu'un essai de boss de guilde s'est retrouvé à 10 unités pour 5. Vider "
                + "d'abord (`deploymentRetirer`) -- il n'y a pas d'échappatoire à ce refus-ci.");
        }
        return null;
    }
    if (total > borne) {
        return refus(`REFUS (${quoi}) : le plateau porte DÉJÀ ${total} unité(s) DISTINCTE(S) `
            + `(${e.reelles} réelle(s), ${e.placeholders} placeholder(s), union par unitId) pour `
            + `un plafond de ${borne}. Démarrer convertirait les placeholders PAR-DESSUS les `
            + "unités réelles -- exactement le doublement mesuré le 2026-08-20.");
    }
    return null;
}

// ============================================================================
// LE HUD LUI-MÊME — mesurer le REFUS DE POSE plutôt que le déduire.
//
// `idun.ui.UnitDeploymentHud$$Show(units, minUnitsPossible, maxUnitsPossible, options)`
// remplit DEUX dictionnaires : `_allUnitModels` pour tous, et `_allUnlockedUnitModels`
// **seulement si `IUnitModelExtensions$$IsUnlocked(u)`**. C'est le SECOND que
// `TryMarkUnitAsPlaced(unitId, isMachineOfWar)` interroge.
//
// ⇒ « je sélectionne mais je ne pose pas » est exactement la signature d'un premier
// dictionnaire plein et d'un second vide. On ne le DÉDUIT pas : on lit les deux comptes au
// moment du remplissage, et on capture le VERDICT de chaque clic.
//
// OBSERVATION PURE : aucun de ces deux ancrages n'écrit, et on n'invoque ni l'un ni l'autre.
export const NS_HUD = "idun.ui";

export const CLS_HUD = "UnitDeploymentHud";

/** L'instance du HUD, gardée pour pouvoir la relire APRÈS `Show` (l'état bouge à chaque pose). */
export let hudInstance: NativePointer | null = null;

/** Comment `hudInstance` a été obtenue — pour qu'un lecteur sache s'il lit la vraie ou un repli. */
export let hudSource: "Show" | "scene" | null = null;

/** S'ASSURER qu'on a le HUD, même si `Show` n'a pas tiré.
 *
 * ⚠ MÊME CAUSE QUE `vueDeDeploiement`, MÊME SOIRÉE PERDUE. `hudInstance` n'est écrite QUE dans
 * le `onEnter` de `UnitDeploymentHud$$Show` -- ni `TryMarkUnitAsPlaced` ni aucune pose ne
 * l'écrivent. Sur une bataille dont l'écran de déploiement était DÉJÀ affiché quand on s'arme,
 * `Show` est passé, et le HUD reste introuvable pour toute la durée de la bataille. Mesuré le
 * 2026-08-20 : plafond INCONNU -> toute pose refusée -> START refusé, sur un jeton dépensé.
 *
 * Contrairement à `IdunGameViews`, `UnitDeploymentHud` est un `MonoBehaviour` : la scène peut
 * donc le rendre. On le note (`hudSource`) plutôt que de laisser croire qu'il vient de `Show`.
 *
 * ⚠ TRI-ÉTAT PRÉSERVÉ : si la scène ne le rend pas, on reste à `null` -- ce qui fait REFUSER en
 * amont. Un repli qui échoue ne doit jamais devenir un zéro.
 */
export function assurerHud(): NativePointer | null {
    if (hudInstance !== null && !hudInstance.isNull()) return hudInstance;
    const k = findClassAnywhere(NS_HUD, CLS_HUD);
    if (!k) return null;
    const r = premiereInstance(k);
    if (!(r instanceof NativePointer) || r.isNull()) return null;
    hudInstance = r;
    hudSource = "scene";
    return hudInstance;
}

/**
 * Les deux champs qui expliquent le bouton START.
 *
 * ⚠ MESURÉ : la comptabilité du HUD et la composition RÉELLE de la bataille sont DEUX choses
 * séparées, et en sandbox aucune ne nourrit l'autre. Unités déclarées dans `bc.Units` -> elles
 * apparaissent sur le plateau mais `_currentlyPlacedUnits` reste VIDE, donc START est grisé.
 * Unités posées par le HUD -> START s'active, mais le combat démarre sans unité joueur réelle
 * et se termine aussitôt. `HandleOnStartBattleTapped` relaie les posées à
 * `_callbacksDelegate` (`IDeploymentHudCallbacks`, slot 3) : c'est LÀ que se fait le raccord,
 * et savoir QUI l'implémente est le préalable.
 */
export function etatDuBouton(): Record<string, unknown> {
    const hud = assurerHud();
    if (hud === null) {
        return { mesure: false, raison: "aucune instance de HUD -- ni captée à son `Show`, ni "
            + "rendue par la scène" };
    }
    const out: Record<string, unknown> = { mesure: true, hud: hud.toString(),
                                           source: hudSource };
    try {
        const k = hud.readPointer();
        const offCb = getFieldOffset(k, "_callbacksDelegate");
        const offPl = getFieldOffset(k, "_currentlyPlacedUnits");
        if (offCb >= 0) {
            const cb = hud.add(offCb).readPointer();
            out.callbacks = cb.toString();
            out.classeCallbacks = cb.isNull() ? null : classeDerriere(cb).classe;
        } else { out.callbacks = "champ `_callbacksDelegate` ABSENT"; }
        if (offPl >= 0) {
            const lst = hud.add(offPl).readPointer();
            if (lst.isNull()) { out.placees = "liste NULLE"; }
            else {
                const kl = lst.readPointer();
                const offSize = getFieldOffset(kl, "_size");
                out.placees = offSize < 0 ? "champ `_size` ABSENT" : lst.add(offSize).readS32();
            }
        } else { out.placees = "champ `_currentlyPlacedUnits` ABSENT"; }
    } catch (e) { out.erreur = (e as Error).message; }
    return out;
}

/** Compte d'un `Dictionary<K,V>` : `_count - _freeCount`, les deux résolus PAR NOM. */
export function compteDict(dico: NativePointer): number | string {
    try {
        if (dico.isNull()) return "NUL";
        const k = dico.readPointer();
        const oc = getFieldOffset(k, "_count");
        const of = getFieldOffset(k, "_freeCount");
        if (oc < 0) return "champ `_count` absent de " + (s(class_get_name(k) as NativePointer));
        const c = dico.add(oc).readS32();
        const f = of < 0 ? 0 : dico.add(of).readS32();
        return c - f;
    } catch (e) { return "ILLISIBLE : " + (e as Error).message; }
}

/** L'entité du joueur humain, retenue au dernier parcours — publiée pour rendre un appariement
 *  raté LISIBLE (un compte à zéro ne dit pas s'il n'y a pas d'unité ou si l'appariement ment). */
export let dernierIdJoueurHumain: number | null = null;

/** Les couples `PlayerId/PlayerEntityId` observés — deux numérotations distinctes, et c'est la
 *  PREMIÈRE qu'attend `AddUnitMessage`. */
export let derniersCouples: string | null = null;

export function ordreDeConversion(): unknown {
    const v = vueDeLaMoW();
    if ("ok" in v) return { erreur: "aucune `IdunGameViews` joignable -- " + v.error };
    const kv = findClassAnywhere(NS_PREFAB, CLS_VIEWS_PREFAB);
    const mi = kv ? findMethodByParamCount(kv, "GetPlaceholderUnitViews", 0) : null;
    if (!mi) return { erreur: "`IdunGameViews$$GetPlaceholderUnitViews` INTROUVABLE (0 paramètre)" };
    let lst: NativePointer;
    try { lst = invokeMethod(mi.info, v.vues, []) as NativePointer; }
    catch (e) { return { erreur: "LEVÉ : " + (e as Error).message }; }
    if (lst === null || lst.isNull()) return { erreur: "la liste des vues est NULLE" };
    const els = elementsDeListe(lst);
    if (estRefusLecture(els)) return { erreur: "liste ILLISIBLE : " + JSON.stringify(els) };
    const out: Array<Record<string, unknown>> = [];
    for (const el of els) {
        if (el.isNull()) { out.push({ erreur: "vue NULLE" }); continue; }
        try {
            const k = el.readPointer();
            const oId = getFieldOffset(k, "<UnitId>k__BackingField");
            const oPl = getFieldOffset(k, "<PlayerId>k__BackingField");
            const oCo = getFieldOffset(k, "<CoordinatePosition>k__BackingField");
            const oMo = getFieldOffset(k, "<IsMachineOfWar>k__BackingField");
            if (oId < 0 || oPl < 0 || oCo < 0) {
                out.push({ erreur: `champs ABSENTS (UnitId=${oId} PlayerId=${oPl} `
                    + `CoordinatePosition=${oCo}) -- chemin PÉRIMÉ` });
                continue;
            }
            out.push({
                unitId: readIl2cppString(el.add(oId).readPointer()),
                playerId: el.add(oPl).readS32(),
                col: el.add(oCo).readS32(), row: el.add(oCo).add(4).readS32(),
                mow: oMo >= 0 ? el.add(oMo).readU8() !== 0 : null,
            });
        } catch (e) { out.push({ erreur: "vue ILLISIBLE : " + (e as Error).message }); }
    }
    return out;
}

/** Taille d'un `List\`1`, champ `_size` résolu PAR SON NOM. */
export function tailleListe(lst: NativePointer): number | string {
    try {
        if (lst.isNull()) return "NULLE";
        const o = getFieldOffset(lst.readPointer(), "_size");
        return o < 0 ? "champ `_size` ABSENT" : lst.add(o).readS32();
    } catch (e) { return "ILLISIBLE : " + (e as Error).message; }
}

/**
 * LE COMPTE DÉRIVÉ DU PLATEAU — les trois candidats, tous publiés.
 *
 * Forcer une CONSTANTE dans le relais du bouton ne contourne pas seulement la comptabilité
 * fausse du HUD : ça supprime la contrainte « assez d'unités posées ». En dérivant le compte des
 * unités RÉELLEMENT présentes, la contrainte est de nouveau ÉVALUÉE — c'est la comptabilité du
 * HUD qui est fausse (il ignore ce qui vient de `bc.Units`), pas la borne.
 *
 * Les trois sont rendus ensemble parce qu'un seul chiffre ne se vérifie pas : sur un montage à
 * 5 unités joueur et 3 adverses, seul le bon candidat vaut 5.
 */
export function compterSurLePlateau(): Record<string, number | string> {
    const out: Record<string, number | string> = {};
    const vues = vuesDePose;
    if (vues === null || vues.isNull()) {
        return { erreur: "aucune `IdunGameViews` observée -- rien n'est compté" };
    }
    // LE COMPTE JUSTE : les vues d'unité dont le joueur EST le joueur humain.
    // ⚠ `_humanPlayerEntityIds` compte les JOUEURS (mesuré : 1) et `_unitViews` compte LES DEUX
    // CAMPS (mesuré : 8 pour 5+3). Ni l'un ni l'autre ne repond a la question ; c'est en les
    // publiant tous les deux qu'on l'a vu, plutot qu'en en elisant un.
    const ids = idsDesUnitesDuJoueur();
    out.unitesDuJoueurHumain = Array.isArray(ids) ? ids.length : ids;
    if (Array.isArray(ids)) out.idsSurLePlateau = ids.join(",");
    if (dernierIdJoueurHumain !== null) out.idJoueurHumain = dernierIdJoueurHumain;
    if (derniersCouples !== null) out.couplesPlayerIdSurEntityId = derniersCouples;
    try {
        const k = vues.readPointer();
        for (const [cle, champ, genre] of [
            ["unitesDuJoueur", "_humanPlayerEntityIds", "liste"],
            ["toutesLesVues", "_unitViews", "dico"],
            ["placeholders", "_placeholderUnitViews", "dico"],
        ] as const) {
            const o = getFieldOffset(k, champ);
            if (o < 0) { out[cle] = `champ \`${champ}\` ABSENT`; continue; }
            const p = vues.add(o).readPointer();
            out[cle] = genre === "liste" ? tailleListe(p) : compteDict(p);
        }
    } catch (e) { out.erreur = (e as Error).message; }
    return out;
}

/** Une unité RÉELLE du plateau, telle que sa vue la déclare. */
export interface UniteDuPlateau {
    unitId: string | null;
    /** `AUnitView.<Id>` — l'entité DE L'UNITÉ. C'est ce qu'attend `RemoveUnitMessage`. */
    entityId: number;
    /** `AUnitView.<PlayerId>` — ce qu'attend `AddUnitMessage`. */
    playerId: number | null;
    /** `AUnitView.<PlayerEntityId>` — l'entité DU JOUEUR, ce qui apparie l'unité à son camp. */
    playerEntityId: number;
    /** `AUnitView$$get_LogicalPosition` — la tuile RÉELLEMENT occupée. `null` = non lue.
     *  ⚠ Sans elle on ne peut pas dire si une pose échoue par la TUILE ou par le CATALOGUE :
     *  mesuré, `ultraApothecary` (dans la BC ET dans le lineup) n'apparaît pas en (0,0), tandis
     *  qu'`admecMarshall` (hors BC native) apparaît en (4,1) et (4,2). */
    col: number | null;
    row: number | null;
    duJoueur: boolean;
}

/** L'`IdunGameViews` du déploiement — captée par nos hooks, SINON celle que la pompe draine.
 *
 * ⚠ LE REPLI N'EST PAS UN CONFORT, C'EST LA CAUSE D'UNE SOIRÉE PERDUE (2026-08-20). Nos capteurs
 * (`Initialize`/`AddUnit`/`Continue`/`Enable`) ne tirent qu'à la CRÉATION de la bataille. En
 * sandbox on monte soi-même, hooks déjà en place, donc ils tirent toujours -- et le défaut est
 * resté invisible. Sur une bataille RÉELLE créée avant l'armement, ils ne tirent JAMAIS :
 * `vuesDePose` reste nul pour toute la durée de cette bataille, et TOUT ce qui suit devient
 * aveugle (plateau illisible, poses refusées, START refusé).
 *
 * Or la pompe, elle, tient cette vue depuis toujours : elle lit `IdunGameViews._runner` à chaque
 * frame, donc son `this` EST l'objet qu'on cherche -- même classe, même instance.
 *
 * ⛔ `premiereInstance` NE MARCHE PAS ICI : `IdunGameViews` n'est pas un `UnityEngine.Object`,
 * `FindObjectsByType` rend NULL même en pleine bataille. Mesuré. Le repli (3) de `dicoVivant`
 * repose sur cette voie et ne peut donc pas sauver ce cas-là.
 */
export function vueDeDeploiement(): NativePointer | null {
    if (vuesDePose !== null && !vuesDePose.isNull()) return vuesDePose;
    const p = state.gameViews;
    return p !== null && !p.isNull() ? p : null;
}

export function unitesDuPlateau(): UniteDuPlateau[] | string {
    const vues = vueDeDeploiement();
    if (vues === null || vues.isNull()) {
        return "aucune `IdunGameViews` -- ni captée par nos hooks, ni vue par la pompe";
    }
    return (() => {
        try {
            const k = vues.readPointer();
            // ⚠ `get_CurrentPlayerEntityId` designe le joueur DU TOUR COURANT, pas le proprietaire
            // de l'appareil : pendant le deploiement il peut ne designer personne de pertinent.
            // `FirstPlayerEntityIdOfHumanOnThisDevice` est la question qu'on pose vraiment.
            const mAll = findMethodByParamCount(k, "GetAllUnitViews", 0);
            const mHum = findMethodByParamCount(k, "FirstPlayerEntityIdOfHumanOnThisDevice", 0)
                ?? findMethodByParamCount(k, "get_CurrentPlayerEntityId", 0);
            if (!mAll || !mHum) return "`GetAllUnitViews`/joueur humain INTROUVABLES";
            // ⚠ `BEntityId` est un TYPE VALEUR : `runtime_invoke` le BOXE, la valeur est a +0x10.
            const boite = invokeMethod(mHum.info, vues, null);
            if (boite.isNull()) return "joueur humain NUL";
            const idCourant = boite.add(0x10).readS32();
            dernierIdJoueurHumain = idCourant;
            // ⚠ `GetAllUnitViews` rend une `ValueCollection` (mesuré), pas une `List` : elle n'a
            // ni `_items` ni `_size`. On parcourt donc les ENTRÉES du dictionnaire, avec la
            // taille d'élément DÉRIVÉE de la classe du tableau -- jamais supposée.
            const offVues = getFieldOffset(k, "_unitViews");
            if (offVues < 0) return "champ `_unitViews` ABSENT";
            const dico = vues.add(offVues).readPointer();
            if (dico.isNull()) return "`_unitViews` est NUL";
            const kd = dico.readPointer();
            const offEntries = getFieldOffset(kd, "_entries");
            const offCount = getFieldOffset(kd, "_count");
            if (offEntries < 0 || offCount < 0) return "`_entries`/`_count` absents du dictionnaire";
            const entries = dico.add(offEntries).readPointer();
            const nEntries = dico.add(offCount).readS32();
            // ⛔ `_entries` NUL AVEC `_count == 0` N'EST PAS UNE PANNE DE LECTURE : C'EST UN
            // DICTIONNAIRE VIDE, et c'est le SEUL cas que le rejeu de mémoire doit servir.
            //
            // Un `Dictionary<K,V>` .NET construit et jamais alimenté laisse `_buckets` ET
            // `_entries` à NUL -- le tableau de secours n'est alloué qu'à la première insertion.
            // Rendre un refus dessus faisait passer « le plateau est VIDE » pour « je ne sais pas
            // lire le plateau », et les deux ne mènent pas au même geste :
            //
            //     compteJoueur() -> null  -> rejouerMemoire : « plateau non lisible -- rejeu ANNULÉ »
            //     compteJoueur() -> 0     -> rejouerMemoire : REJOUE les poses mémorisées
            //
            // Mesuré le 2026-08-26 sur un retry d'onslaught : la mémoire portait bien les 5 poses
            // (`necroSpyder`, `necroDestroyer`, `tauMarksman`, `tauCrisis`, `tauDarkstrider`),
            // `armé: true`, `capteurStartArmé: true` -- et `rejeux: 0`, `dernier: "plateau non
            // lisible -- rejeu ANNULÉ"`. La composition n'était pas reprise, et rien n'accusait
            // la vraie cause : la garde tombait pile sur l'état qu'elle devait laisser passer.
            //
            // ⚠ On ne relâche QUE le couple (`_entries` nul ET `_count` nul). Un `_entries` nul
            // avec un `_count` non nul reste une incohérence -- là, on ne sait vraiment pas lire,
            // et on refuse.
            if (entries.isNull()) {
                return nEntries === 0 ? [] : "`_entries` est NUL alors que `_count` vaut "
                    + nEntries + " -- dictionnaire INCOHÉRENT, on ne devine pas";
            }
            if (nEntries < 0 || nEntries > 4096) return `_count invraisemblable (${nEntries})`;
            if (class_get_element_class === null || class_instance_size === null) {
                return "`class_get_element_class`/`class_instance_size` absents -- taille "
                    + "d'element NON DERIVABLE, on ne devine pas";
            }
            const kElem = class_get_element_class(entries.readPointer()) as NativePointer;
            // Type valeur : `instance_size` inclut l'en-tete d'objet (2 pointeurs).
            const tailleElem = (class_instance_size(kElem) as number) - Process.pointerSize * 2;
            if (tailleElem <= 0 || tailleElem > 128) {
                return `taille d'element derivee invraisemblable (${tailleElem})`;
            }
            const trouves: UniteDuPlateau[] = [];
            let offJoueur = -1;
            let offUnitId = -1;
            let offPlayerId = -1;
            let offId = -1;
            // `undefined` = pas encore cherché ; `null` = cherché et ABSENT. Les distinguer évite
            // de relancer la résolution à chaque vue.
            let mPos: ReturnType<typeof findMethodByParamCount> | undefined;
            let lus = 0;
            const vus: number[] = [];
            const couples: string[] = [];
            for (let i = 0; i < nEntries; i++) {
                // `{ hashCode, next, cle, valeur }` : la valeur est une REFERENCE, donc en fin
                // d'entree apres alignement.
                const uv = entries.add(0x20 + i * tailleElem + tailleElem - Process.pointerSize)
                    .readPointer();
                if (uv.isNull()) continue;
                if (offJoueur < 0) {
                    offJoueur = getFieldOffset(uv.readPointer(),
                                               "<PlayerEntityId>k__BackingField");
                    offPlayerId = getFieldOffset(uv.readPointer(), "<PlayerId>k__BackingField");
                    offUnitId = getFieldOffset(uv.readPointer(), "<UnitId>k__BackingField");
                    // `AUnitView.<Id>` : l'entité de l'UNITÉ, distincte des deux ids de JOUEUR
                    // lus juste au-dessus. Sans elle, aucun retrait n'est adressable.
                    offId = getFieldOffset(uv.readPointer(), "<Id>k__BackingField");
                    if (offJoueur < 0) return "champ `<PlayerEntityId>k__BackingField` ABSENT";
                    if (offUnitId < 0) return "champ `<UnitId>k__BackingField` ABSENT";
                    if (offId < 0) return "champ `<Id>k__BackingField` ABSENT";
                }
                lus++;
                const idVue = uv.add(offJoueur).readS32();
                // Les ids OBSERVES sont publies : un compte a zero ne dit pas s'il n'y a pas
                // d'unite du joueur ou si c'est l'appariement qui est faux.
                if (vus.indexOf(idVue) < 0 && vus.length < 12) vus.push(idVue);
                // ⚠ `PlayerId` et `PlayerEntityId` sont DEUX numerotations distinctes. Celle
                // qu'attend `AddUnitMessage` est `PlayerId` -- la lire sur une unite REELLE est
                // le seul moyen de ne pas la deviner.
                if (offPlayerId >= 0 && couples.length < 12) {
                    const c = `${uv.add(offPlayerId).readS32()}/${idVue}`;
                    if (couples.indexOf(c) < 0) couples.push(c);
                }
                // On enregistre les DEUX camps : c'est le seul moyen de dire « 0 unité du joueur
                // sur 8 vues lues » plutôt qu'un zéro muet qui ne distingue pas le plateau vide
                // de l'appariement faux.
                let nom: string | null = null;
                try { nom = readIl2cppString(uv.add(offUnitId).readPointer()); } catch { nom = null; }
                // La TUILE. `get_LogicalPosition` rend un `AxialCoordinate` — un TYPE VALEUR,
                // donc `runtime_invoke` le BOXE : `Column` est à +0x10, `Row` à +0x14. Lire le
                // pointeur lui-même rendrait n'importe quoi (même piège que `boolBoxe`).
                let col: number | null = null;
                let row: number | null = null;
                try {
                    if (mPos === undefined) {
                        mPos = findMethodByParamCount(uv.readPointer(), "get_LogicalPosition", 0);
                    }
                    if (mPos) {
                        const boite = invokeMethod(mPos.info, uv, null);
                        if (!boite.isNull()) {
                            col = boite.add(0x10).readS32();
                            row = boite.add(0x14).readS32();
                        }
                    }
                } catch { col = null; row = null; }
                trouves.push({
                    unitId: nom === "" ? null : nom,
                    entityId: uv.add(offId).readS32(),
                    playerId: offPlayerId >= 0 ? uv.add(offPlayerId).readS32() : null,
                    playerEntityId: idVue,
                    col, row,
                    duJoueur: idVue === idCourant,
                });
            }
            // Le parcours se CONTROLE : si on n'a pas lu autant de vues que le dictionnaire en
            // annonce, la disposition supposee est fausse et le compte ne vaut RIEN.
            derniersCouples = couples.join(" ");
            const attendu = compteDict(dico);
            if (typeof attendu === "number" && lus !== attendu) {
                return `parcours INCOHERENT : ${lus} vues lues pour ${attendu} annoncees `
                    + `(taille d'element ${tailleElem}) -- on ne rend RIEN plutot qu'un faux`;
            }
            return trouves;
        } catch (e) { return "LEVÉ : " + (e as Error).message; }
    })();
}

/** Les `unitId` des unités du JOUEUR HUMAIN sur le plateau — la vue « noms » de l'inventaire.
 *  UN SEUL parcours existe (`unitesDuPlateau`), avec UN SEUL contrôle de cohérence : deux
 *  lecteurs indépendants du même dictionnaire finiraient par diverger en silence. */
export function idsDesUnitesDuJoueur(): string[] | string {
    const u = unitesDuPlateau();
    if (!Array.isArray(u)) return u;
    return u.filter((x) => x.duJoueur && x.unitId !== null).map((x) => x.unitId as string);
}

// ---------------------------------------------------------------------------------------------
// LE RETRAIT — le symétrique exact de la pose.
//
// Le déploiement natif ne sait ôter que des `PlaceholderUnitView` : quand les unités viennent de
// `bc.Units`, le runner les a créées AU MONTAGE, elles sont RÉELLES, et le clear du HUD n'a
// aucune prise sur elles. Il vide sa liste (donc grise START) et laisse le plateau intact.
//
// Le chemin qui les ôte pour de vrai est le même que pour la pose : un message d'entrée appliqué
// au runner VIVANT. `IdunBattle.Messages.InputMessageProcessor$$Visit` en a une surcharge dédiée.
// ---------------------------------------------------------------------------------------------

export const NS_MESSAGES = "IdunBattle.Messages";

/**
 * Le message que le jeu emploie lui-même pour ôter une unité — construit, jamais deviné.
 *
 * `RemoveUnitMessage` porte UN SEUL champ (`UnitId : BEntityId`), et
 * `IdunBattle.Messages.InputMessageProcessor$$Visit` ne lit que celui-là (4 octets) avant de
 * résoudre l'entité et d'appeler `IdunBattle.Operations.RemoveUnitOperation$$Execute` avec
 * `removeEffects: true, keepActive: false` — les deux littéraux sont dans le décompilé.
 *
 * ⚠ AUCUN `.ctor` n'est invoqué, et c'est un choix MESURÉ, pas une facilité : la classe n'en
 * publie pas dans `frida/methods.tsv` — ce qui ne prouve rien (IL2CPP déduplique les corps
 * triviaux) — mais son unique champ est un entier et le lecteur natif ne lit que lui. L'écrire
 * EST donc la construction complète.
 *
 * ⚠ L'offset est DÉRIVÉ par `getFieldOffset`, jamais le `+0x10` qu'on a mesuré : un offset
 * recopié devient faux au prochain build, en silence.
 *
 * ⚠ Rendu PINNÉ, comme `buildAddUnitMessage` : l'appelant DOIT `gcRoot.remove(msg)` après
 * l'`Apply`, sinon la racine GC s'accumule à chaque retrait.
 */
export function buildRemoveUnitMessage(entityId: number): NativePointer {
    const k = findClassAnywhere(NS_MESSAGES, "RemoveUnitMessage");
    if (!k) throw new Error("`IdunBattle.Messages.RemoveUnitMessage` INTROUVABLE sur ce build");
    const off = getFieldOffset(k, "UnitId");
    if (off < 0) throw new Error("champ `UnitId` ABSENT de `RemoveUnitMessage` -- chemin PÉRIMÉ");
    const msg = il2cpp_object_new(k) as NativePointer;
    if (msg.isNull()) throw new Error("`il2cpp_object_new(RemoveUnitMessage)` a rendu NUL");
    gcRoot.add(msg);
    msg.add(off).writeS32(entityId);
    return msg;
}

/** Applique un `RemoveUnitMessage` par cible. `cibles === null` ⇒ toutes les unités du joueur.
 *  ⚠ À APPELER DEPUIS LA FILE DU THREAD PRINCIPAL, jamais d'un callback d'interception. */
export function retirerDuRunner(cibles: number[] | null): Record<string, unknown> | Refus {
    const avant = unitesDuPlateau();
    if (!Array.isArray(avant)) return refus("plateau non lisible : " + avant);
    const ids = cibles ?? avant.filter((u) => u.duJoueur).map((u) => u.entityId);
    if (ids.length === 0) {
        // ⚠ Un zéro DÉSIGNE SON SUSPECT. Ce refus a déjà menti une fois : le plateau portait
        // bien ses unités, c'est `vuesDePose` qui pointait sur la vue d'une bataille morte.
        return refus("aucune unité du joueur sur le plateau -- rien à retirer. Vue interrogée : "
            + `${vuesDePose === null ? "AUCUNE" : vuesDePose.toString()}, ${avant.length} vue(s) `
            + "lue(s) tous camps confondus. Si la bataille est bien montée, c'est cette "
            + "vue-là qui est PÉRIMÉE, pas le plateau qui est vide.");
    }
    const runner = state.liveRunner;
    if (runner === null || runner.isNull()) {
        return refus("aucun runner vivant publié par le pump -- `state.liveRunner` est NUL, "
            + "ce qui n'est PAS « zéro unité »");
    }
    const kr = findClassAnywhere("IdunBattle.Runner", "IdunRunner");
    const mApply = kr ? findMethodByParamCount(kr, "Apply", 1) : null;
    if (!mApply) return refus("`IdunBattle.Runner.IdunRunner$$Apply` INTROUVABLE");
    const nomDe = new Map<number, string | null>(avant.map((u) => [u.entityId, u.unitId]));
    const faits: Array<{ entityId: number; unitId: string | null;
                         ok: boolean; detail: string }> = [];
    for (const id of ids) {
        let msg: NativePointer | null = null;
        try {
            msg = buildRemoveUnitMessage(id);
            invokeMethod(mApply.info, runner, [msg]);
            faits.push({ entityId: id, unitId: nomDe.get(id) ?? null, ok: true,
                         detail: "`Apply` passé" });
        } catch (e) {
            faits.push({ entityId: id, unitId: nomDe.get(id) ?? null, ok: false,
                         detail: "LEVÉ : " + (e as Error).message });
        } finally {
            if (msg !== null) { try { gcRoot.remove(msg); } catch { /* best effort */ } }
        }
    }
    // ⚠ ON NE TOUCHE PAS À LA MÉMOIRE ICI, ET C'EST UN CHOIX. Tenir `memoirePoses` à jour geste
    // par geste, c'est maintenir un DOUBLE du plateau : deux états qui doivent rester égaux,
    // donc qui divergent. La mémoire se prend en UNE FOIS, au START, sur le plateau RÉEL
    // (`instantanerAuStart`) -- ce qui rend cette synchronisation-ci inutile ET plus sûre.
    // ⚠ READ-AFTER-WRITE. Une observation prise AVANT la mutation ne dit rien de ce qu'elle a
    // fait, et « `Apply` n'a pas levé » n'est PAS « l'unité a disparu » : mesuré sur
    // `AddUnitMessage`, l'appel passe sans erreur et rien n'apparaît quand la configuration
    // manque à la BC. On relit donc, et on publie les deux comptes.
    const apres = unitesDuPlateau();
    return {
        // ⚠ `ok` DIT ICI << les appels sont partis >>, PAS << les unités sont parties >>, et cette
        // nuance a coûté cher : le 2026-08-20, ce RPC a rendu `ok: true` sur ses 5 cibles alors
        // que les 5 entités étaient TOUJOURS VIVANTES ; le START a ensuite empilé par-dessus,
        // 10 unités pour 5. La note le disait déjà -- une note ne suffit pas quand le champ
        // qu'on lit d'abord affirme le contraire. Le VERDICT est produit par `deploymentRetirer`,
        // qui attend l'effet et REND `ok: false` si une cible survit.
        ok: true, faits, verifie: false,
        cibles: ids,
        retirees: faits.filter((f) => f.ok).length, visees: ids.length,
        surPlateauAvant: avant.filter((u) => u.duJoueur).length,
        surPlateauApres: Array.isArray(apres)
            ? apres.filter((u) => u.duJoueur).length : apres,
        note: "`ok` = les `Apply` sont partis. Le retrait de la VUE passe par le flux de bataille "
            + "(`IdunBattle.View.BattleStream.StepHandlers.RemoveUnitStepHandler`) et traîne "
            + "d'une frame ou deux : `surPlateauApres` est un INSTANTANÉ, pas un verdict.",
    };
}

/** Rejoue `f` après `n` images de pump. ⛔ On repasse par la FILE, on ne dort jamais. */
export function apresImages<T>(n: number, f: () => T): Promise<T> {
    if (n <= 0) return queueOnMainThread(f) as Promise<T>;
    return (queueOnMainThread(() => null) as Promise<null>)
        .then(() => apresImages(n - 1, f));
}

/** Déclare au HUD les unités DÉJÀ présentes sur le plateau, puis provoque le rafraîchissement
 *  du bouton. C'est ce qui rend START actif quand les unités viennent de `bc.Units` : le HUD ne
 *  compte que ce que LUI a posé, or sur une BC pré-remplie il n'a rien posé.
 *  ⚠ À APPELER DEPUIS LA FILE DU THREAD PRINCIPAL. */
export function marquerLesUnitesDuPlateau(): Record<string, unknown> | Refus {
    const ids = idsDesUnitesDuJoueur();
    if (!Array.isArray(ids)) return refus("plateau non lisible : " + ids);
    if (ids.length === 0) return refus("aucune unité du joueur sur le plateau");
    if (hudInstance === null || hudInstance.isNull()) {
        return refus("aucune instance de HUD captée");
    }
    const c = classeDerriere(hudInstance);
    if (c.classe !== CLS_HUD) {
        return refus(`le pointeur de HUD ne porte plus \`${CLS_HUD}\` mais `
            + `\`${c.classe ?? c.erreur}\` -- PÉRIMÉ`);
    }
    const kh = findClassAnywhere(NS_HUD, CLS_HUD);
    const mMark = kh ? findMethodByParamCount(kh, "TryMarkUnitAsPlaced", 2) : null;
    const mUp = kh ? findMethodByParamCount(kh, "UpdateButtons", 0) : null;
    if (!mMark) return refus("`TryMarkUnitAsPlaced` INTROUVABLE (2 paramètres)");
    const faits: Array<{ unitId: string; accepte: boolean | string }> = [];
    const faux = Memory.alloc(1); faux.writeU8(0);   // `isMachineOfWar: false`
    for (const id of ids) {
        try {
            const r = invokeMethod(mMark.info, hudInstance, [createManagedString(id), faux]);
            // ⚠ retour BOXÉ : le booléen est à +0x10, pas dans le pointeur.
            faits.push({ unitId: id, accepte: boolBoxe(r) });
        } catch (e) {
            faits.push({ unitId: id, accepte: "LEVÉ : " + (e as Error).message });
        }
    }
    if (mUp) { try { invokeMethod(mUp.info, hudInstance, null); } catch { /* best effort */ } }
    const b = etatDuBouton();
    return { ok: true, faits, marquees: faits.filter((f) => f.accepte === true).length,
             placeesApres: typeof b.placees !== "undefined" ? b.placees : "non relu" };
}

/** Le compte d'unités RÉELLES du joueur, ou `null` si le plateau n'est pas lisible.
 *  ⚠ `null` = PAS MESURÉ, jamais à lire comme un zéro. */
export function compteJoueur(): number | null {
    const u = unitesDuPlateau();
    return Array.isArray(u) ? u.filter((x) => x.duJoueur).length : null;
}

export interface Pose { unitId: string; playerId: number; col: number; row: number }

export let vuesJeu: NativePointer | null = null;   // l'`IdunGameViews` vivante, captée au passage

/**
 * L'`IdunGameViews` sur laquelle reposer la MoW — par ORDRE D'AUTORITÉ, jamais par une source
 * unique.
 *
 * ⚠ C'EST LA CAUSE MESURÉE DU « LA MoW N'EST PAS RÉCUPÉRÉE AU RETRY » (2026-08-19).
 * `vuesJeu` n'est rempli que par le hook `IdunGameViews$$Enable` d'`armerPhase`, et ce hook
 * était REFUSÉ par le faux positif du garde de trivialité (cf. `teteTriviale`). Pendant ce
 * temps, le MÊME fichier tenait une vue VIVANTE dans `vuesDePose` — captée par
 * `AddPlaceholderUnit`, armée sans encombre. Relevé en séance : `deploymentMemoire` publiait
 * `vuesJeu: null` et `dernier: "... | MoW: aucune IdunGameViews captée"` alors que
 * `deploymentPrefabStatus` publiait `vueDePose: 0x1c716011000` et `Enable : ARMÉ`.
 * Le rejeu lisait la variable VIDE des deux. Deux sources pour une même chose, et on
 * interrogeait la mauvaise.
 *
 * ⇒ On passe par l'échelle `dicoVivant()` que le reste du fichier emploie déjà, et on PUBLIE la
 * source : une MoW reposée par le repli `FindObjectsByType` ne doit pas se lire comme une MoW
 * reposée sur la vue observée.
 *
 * ⇒ `dicoVivant()` D'ABORD, `vuesJeu` en dernier recours. Sa tête est `vuesDePose`, captée sur
 * l'`AddPlaceholderUnit` de la pose EN COURS — strictement plus fraîche que `Enable`, dont on a
 * mesuré (2026-08-21, `sonde_vue_perimee`) qu'il tire PENDANT LE DÉMONTAGE :
 *     AVANT montage    vuesJeu=None
 *     APRÈS montage    vuesJeu=None          <- `Enable` n'a pas encore tiré
 *     APRÈS retraite   vuesJeu=0x270feb0c900 <- il est rempli PAR LA SORTIE
 *
 * ⚠ CET ORDRE NE SUFFIT PAS, ET C'EST MESURÉ : l'inverser SEUL n'a rien réparé — le jeu est mort
 * au montage suivant exactement comme avant, parce que `vuesDePose` est périmée de la MÊME façon.
 * La réparation est `oublierLesPointeursDeLaBatailleMorte()`, qui les remet TOUS à nul avant
 * chaque montage. Ce qu'on gagne ici est plus modeste et reste vrai : à fraîcheur égale, la vue
 * de la pose en cours est la bonne, et la source publiée dit toujours laquelle a servi.
 */
export function vueDeLaMoW(): { vues: NativePointer; source: string } | Refus {
    const d = dicoVivant();
    if (!("ok" in d)) return { vues: d.vues, source: d.source };
    if (vuesJeu !== null && !vuesJeu.isNull()) {
        return { vues: vuesJeu,
                 source: "DERNIER RECOURS `IdunGameViews$$Enable` -- l'échelle vivante a refusé ("
                     + d.error + "). Ce pointeur peut dater d'une bataille PRÉCÉDENTE." };
    }
    return d;
}

export function registerPlateau(ctx: Ctx): void {
    /**
     * LES ENTRÉES DE `_currentlyPlacedUnits`, ET LE PRÉDICAT DE START ÉPROUVÉ SUR CHACUNE.
     *
     * ⚠ POURQUOI ENTRÉE PAR ENTRÉE, ET PAS UN VERDICT GLOBAL. `HandleOnStartBattleTapped` fait
     * `_currentlyPlacedUnits.FindAll(<HandleOnStartBattleTapped>b__150_0)` : UNE entrée qui lève
     * fait tomber tout le START, et le message natif ne dit PAS laquelle. Tant qu'on ne les
     * éprouve pas une par une, « ça lève » ne désigne personne — c'est exactement ce qui a fait
     * accuser tour à tour le prefab, la munition, le placeholder, le contexte de vidange.
     *
     * Le prédicat est un LECTEUR : il cherche la clé de l'entrée dans `_allUnitModels` et rend
     * `!IsMachineOfWar` (slot 0x37) -- donc `FindAll` EXCLUT les machines. Aucune écriture.
     *
     * ⚠ La taille d'élément est DÉRIVÉE (`class_instance_size` de la classe d'élément moins
     * l'en-tête d'objet), jamais recopiée du décompilé : elle est PUBLIÉE pour être confrontée
     * aux 32 octets que `b__150_0` copie, pas pour être crue.
     */
    ctx.rpc.deploymentPlacees = (body?: {
        tronquer?: number; confirmer?: boolean;
    }): Promise<unknown> | unknown => {
        const tronquer = typeof body?.tronquer === "number" ? body.tronquer : null;
        if (tronquer !== null && body?.confirmer !== true) {
            return refus("ECRITURE -- `tronquer` exige `confirmer: true`. Il RÉÉCRIT le `_size` "
                + "de `_currentlyPlacedUnits` : les éléments au-delà deviennent invisibles du "
                + "HUD sans être détruits.");
        }
        return queueOnMainThread((): Record<string, unknown> => {
            if (hudInstance === null || hudInstance.isNull()) {
                return { ok: false, error: "aucun `UnitDeploymentHud` capturé" };
            }
            const k = findClassAnywhere(NS_HUD, CLS_HUD);
            if (!k) return { ok: false, error: `\`${NS_HUD}.${CLS_HUD}\` INTROUVABLE` };
            const offPl = getFieldOffset(k, "_currentlyPlacedUnits");
            if (offPl < 0) return { ok: false, error: "champ `_currentlyPlacedUnits` ABSENT" };
            const lst = hudInstance.add(offPl).readPointer();
            if (lst.isNull()) return { ok: false, error: "`_currentlyPlacedUnits` est NULLE" };
            const kl = lst.readPointer();
            const offItems = getFieldOffset(kl, "_items");
            const offSize = getFieldOffset(kl, "_size");
            if (offItems < 0 || offSize < 0) {
                return { ok: false, error: `champs de \`List\` absents : _items=${offItems} `
                    + `_size=${offSize}` };
            }
            const taille = lst.add(offSize).readS32();
            if (tronquer !== null) {
                if (tronquer < 0 || tronquer > taille) {
                    return { ok: false, error: `\`tronquer\` HORS BORNES : ${tronquer} pour une `
                        + `liste de ${taille}` };
                }
                lst.add(offSize).writeS32(tronquer);
                return { ok: true, action: "tronque", avant: taille,
                         apres: lst.add(offSize).readS32() };
            }
            const items = lst.add(offItems).readPointer();
            if (items.isNull()) return { ok: false, error: "`_items` est NUL", taille };
            // Taille d'élément DÉRIVÉE de la classe d'élément du tableau, jamais supposée.
            // ⚠ Les trois helpers sont résolus PARESSEUSEMENT et peuvent valoir `null` sur un
            // build où l'export manque : on le DIT (`octetsParEntree: null`) au lieu de retomber
            // sur les 32 du décompilé, qui feraient lire des entrées décalées en silence.
            const kArr = items.readPointer();
            const kElem = class_get_element_class ? class_get_element_class(kArr) : null;
            const estVal = kElem !== null && class_is_valuetype !== null
                ? (class_is_valuetype(kElem) as number) !== 0 : null;
            let octets: number | null = null;
            if (estVal === true && class_instance_size !== null) {
                octets = (class_instance_size(kElem as NativePointer) as number)
                    - 2 * Process.pointerSize;
            } else if (estVal === false) { octets = Process.pointerSize; }
            if (octets === null || octets <= 0 || octets > 512) {
                return { ok: false, taille, octetsParEntree: octets, elementValeur: estVal,
                         error: "taille d'élément NON DÉRIVABLE -- pas de repli sur une "
                             + "constante, la lecture serait décalée sans le dire" };
            }
            const maxLength = items.add(3 * Process.pointerSize).readS32();
            const base = items.add(4 * Process.pointerSize);
            // Le prédicat, résolu PAR NOM. C'est un lecteur -- il ne mute rien.
            const mPred = findMethod(k, "<HandleOnStartBattleTapped>b__150_0");
            const entrees: Array<Record<string, unknown>> = [];
            for (let i = 0; i < Math.min(taille, 32); i++) {
                const p = base.add(i * octets);
                const e: Record<string, unknown> = { i, adresse: p.toString() };
                try {
                    const u8 = new Uint8Array(p.readByteArray(octets) as ArrayBuffer);
                    e.hex = Array.from(u8).map((b) => b.toString(16).padStart(2, "0")).join(" ");
                    e.nul = Array.from(u8).every((b) => b === 0);
                } catch (err) { e.hex = "ILLISIBLE : " + (err as Error).message; }
                if (mPred) {
                    try {
                        const r = invokeMethod(mPred.info, hudInstance!, [p]);
                        // Retour `bool` BOXÉ : la valeur vit à +0x10, pas sur le pointeur.
                        e.predicat = r !== null && !r.isNull()
                            ? (r.add(0x10).readU8() !== 0) : null;
                    } catch (err) { e.predicat = "LEVÉ : " + (err as Error).message; }
                } else { e.predicat = "`b__150_0` INTROUVABLE"; }
                entrees.push(e);
            }
            return { ok: true, taille, maxLength, octetsParEntree: octets,
                     elementValeur: estVal, predicatResolu: mPred !== null,
                     predicatVA: mPred ? ghidraVA(mPred.ptr) : null, entrees,
                     note: "`predicat: false` = machine of war (EXCLUE du relais, c'est normal) ; "
                         + "`predicat: LEVÉ` = clé ABSENTE d'`_allUnitModels` -- CELLE-LÀ fait "
                         + "tomber tout le START." };
        });
    };

    /** L'inventaire du plateau, les DEUX camps — lecture pure, aucune écriture. */
    ctx.rpc.deploymentPlateau = (): Promise<unknown> | unknown =>
        queueOnMainThread(() => {
            const u = unitesDuPlateau();
            if (!Array.isArray(u)) return refus("plateau non lisible : " + u);
            return { ok: true, lecture: true, unites: u,
                     duJoueur: u.filter((x) => x.duJoueur).length, total: u.length };
        });

    /** LE CLEAR QUI ÔTE POUR DE VRAI. Applique un `RemoveUnitMessage` par unité au runner
     *  VIVANT — le seul chemin qui atteigne une unité RÉELLE, celle que le clear natif ne sait
     *  pas voir parce qu'il ne connaît que les `PlaceholderUnitView`. */
    ctx.rpc.deploymentRetirer = (body?: {
        confirmer?: boolean; entityIds?: number[];
    }): Promise<unknown> | unknown => {
        if (body?.confirmer !== true) {
            return queueOnMainThread(() => {
                const u = unitesDuPlateau();
                if (!Array.isArray(u)) return refus("plateau non lisible : " + u);
                const cibles = body?.entityIds ?? u.filter((x) => x.duJoueur)
                    .map((x) => x.entityId);
                return { ok: true, lecture: true, aRetirer: cibles,
                         unites: u.filter((x) => cibles.indexOf(x.entityId) >= 0),
                         note: "`confirmer: true` exigé : ce RPC APPLIQUE des "
                             + "`RemoveUnitMessage` au runner VIVANT -- il modifie la bataille "
                             + "en cours" };
            });
        }
        // ⚠ ON ATTEND L'EFFET, ET LE VERDICT EN DÉPEND. `Apply` qui passe n'est pas « l'unité est
        // partie » -- mesuré le 2026-08-20, 5 `Apply` verts pour 5 entités TOUJOURS VIVANTES.
        // ~90 images de pump, soit environ une seconde à 60 images/s (même délai que
        // `verifierPuisNettoyer`).
        return (queueOnMainThread(
            () => retirerDuRunner(body.entityIds ?? null)) as
                Promise<Record<string, unknown>>)
            .then((r) => {
                if (r.ok !== true) return r;
                const cibles = (r.cibles as number[]) ?? [];
                return apresImages(90, (): Record<string, unknown> => {
                    const u = unitesDuPlateau();
                    if (!Array.isArray(u)) {
                        return { ...r, verifie: false, ok: false,
                                 verdict: "plateau NON RELISIBLE (" + u + ") -- le retrait n'est "
                                     + "ni confirmé ni infirmé. On ne le compte pas comme fait." };
                    }
                    const restants = u.filter((x) => cibles.indexOf(x.entityId) >= 0);
                    if (restants.length > 0) {
                        return { ...r, verifie: true, ok: false,
                                 survivantes: restants.map((x) => ({ entityId: x.entityId,
                                                                     unitId: x.unitId })),
                                 verdict: `RETRAIT INCOMPLET : ${restants.length} cible(s) sur `
                                     + `${cibles.length} sont TOUJOURS sur le plateau après 90 `
                                     + "images. Ne rien poser par-dessus : c'est exactement ce "
                                     + "qui a produit 10 unités pour 5 le 2026-08-20." };
                    }
                    return { ...r, verifie: true, ok: true,
                             verdict: `les ${cibles.length} cible(s) ont bien QUITTÉ le plateau` };
                });
            });
    };

    /**
     * L'ÉTAT DU DÉPLOIEMENT, ORDRE COMPRIS — lecture pure, et le seul observable AVANT le START.
     *
     * ⚠ POURQUOI IL EXISTE. Le replay adresse ses coups PAR ENTITÉ, et l'entité n'est attribuée
     * qu'au START : mesuré le 2026-08-20, en phase de déploiement `observeBattle` ne voit que les
     * unités ADVERSES -- les nôtres sont des `PlaceholderUnitView`, sans entité. Tout contrôle
     * d'appariement arrivait donc APRÈS le START, c'est-à-dire après le coût d'entrée.
     *
     * Ce que le HUD tient, lui, est lisible tout de suite : `_currentlyPlacedUnits`, DANS SON
     * ORDRE. C'est cet ordre que le START parcourt pour convertir. L'exposer, c'est se donner
     * l'unique chance de refuser AVANT de dépenser.
     *
     * ⚠ CE QUE ÇA NE PROUVE PAS ENCORE. Que l'allocation se DÉDUISE de cet ordre reste une
     * corrélation à deux mesures (poses en ordre du replay -> allocation inverse ; poses en ordre
     * inverse -> allocation du replay), sans mécanisme lu au décompilé. On PUBLIE donc l'ordre,
     * on n'en tire aucune loi ici : c'est l'appelant qui confronte, et le cran d'après-START
     * (`controler_appariement`) reste le juge.
     */
    ctx.rpc.deploymentEtat = (): Promise<unknown> | unknown => queueOnMainThread(() => {
        const e = etatDuDeploiement();
        const base = "ok" in e ? { hudRefus: e.error }
            : { placeholders: e.placeholders, ordreHud: e.nomsPlaceholders,
                reelles: e.reelles, nomsReels: e.nomsReels, cases: e.cases,
                max: e.max, machines: e.machines };
        return { ok: true, lecture: true, ...base, ordreConversion: ordreDeConversion(),
                 note: "`ordreConversion` est la liste que le START PARCOURT ; `ordreHud` est une "
                     + "AUTRE collection, qui ne commande rien. Les entités n'existent qu'APRÈS "
                     + "le START, dans l'ordre d'`ordreConversion`." };
    });
}
