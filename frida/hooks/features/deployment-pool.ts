// L'ETAGE POOL — la DELEGATION : faire repondre la source du MODE la ou la sandbox rend un stub.
//
// Extrait de `deployment-draft.ts` le 2026-08-26. Il emporte SES RPC, et ce n'est pas un detail :
// neuf de ses etats sont MUTES par eux (`preteurDelegation`, `sansFiltreArme`, `preEmprunt`...).
// Les laisser ailleurs aurait exige neuf accesseurs -- un couplage bavard a la place d'un
// couplage invisible. Un module possede son etat ET ce qui l'ecrit.
//
// ⚠ LA FRONTIERE A ETE ELARGIE DEUX FOIS, ET C'EST LA MESURE QUI L'A DIT : la premiere coupe
// laissait dehors les caches de roster (`idsCampagne`, `cacheRoster`...) et les noms natifs
// partages, que le pool cite vingt fois. Les importer aurait ferme un cycle. Les caches sont
// donc ICI, et les noms natifs sont montes au SOCLE.
//
// ⚠ `memoirePoses` reste dehors et nous est INJECTE : la memoire de deploiement est le prochain
// module a sortir, et lui non plus ne doit pas nous importer en retour.

import { Ctx } from "../controller.js";
import {
    findClassAnywhere, findMethodByParamCount, getFieldOffset, readIl2cppString,
    class_get_name, s,
} from "../il2cpp/helpers.js";
import { invokeMethod, createManagedString } from "../il2cpp/invoke.js";
import { gcRoot } from "../il2cpp/gc-root.js";
import { queueOnMainThread } from "../runtime/queue.js";
import { elementsDeListe, estRefus as estRefusLecture, listeDeTextes } from "./lecture-champs.js";
import {
    Refus, refus, Tete, lireTete, teteTriviale, ghidraVA,
    NS_SRC, METHODE, CLS_SANDBOX, NS_VBQ, CLS_VBQ, METH_VBQ, NS_VIEWS, CLS_VIEWS,
} from "./deployment-socle.js";
import { rosterPooledGuildBoss, sourceGuildBossForgee } from "./guild-boss-config.js";
import { sourceCampagneForgee } from "./campaign-source-forge.js";
import { sourceGuildWarForgee } from "./guild-war-config.js";
import { sourceOnslaughtForgee } from "./onslaught-source.js";
import { sourceMowEventForgee } from "./mow-event-source-forge.js";
import { sourcePvpForgee } from "./pvp-source-forge.js";
import { substituerRetourLineup } from "./lineup-poser.js";
import { getCampaignGameModeSourcePtr, getPvpGameModeSourcePtr } from "./campaign-builder.js";

/** Le LECTEUR de la memoire de deploiement, pose par `deployment-draft` -- cf. l'en-tete.
 *  Non injecte, il se comporte comme une memoire VIDE : la delegation delegue, ce qui est le
 *  comportement d'origine. Une injection oubliee ne fabrique donc pas un blocage silencieux. */
/** Les unites que `deploymentDraftUnites` a posees -- etat de l'etage DRAFT, pas du notre.
 *  `remplir` s'en sert comme SOURCE PAR DEFAUT quand l'appelant n'en fournit pas. Injecte pour
 *  la meme raison que la memoire : draft nous importe, on ne l'importe pas en retour. */
let lireUnitesDraft: (() => string[] | null) | null = null;
export function enregistrerLecteurUnitesDraft(fn: () => string[] | null): void {
    lireUnitesDraft = fn;
}

let lireMemoirePoses: (() => { length: number }) | null = null;
export function enregistrerLecteurMemoirePoses(fn: () => { length: number }): void {
    lireMemoirePoses = fn;
}
const memoirePoses = {
    get length(): number { return lireMemoirePoses ? lireMemoirePoses().length : 0; },
};

/** OUBLIER le pre-emprunt d'une bataille morte. ESM interdit d'assigner un import, et c'est tant
 *  mieux : la dependance est NOMMEE au lieu d'etre une affectation invisible entre deux modules. */
export function oublierPreEmprunt(): boolean {
    if (preEmprunt === null) return false;
    preEmprunt = null;
    preEmpruntInfo = null;
    return true;
}

/** Le roster guild war, en CHAÎNES JS. Lu une seule fois, puis re-posé à chaque tir.
 *
 *  ⚠ C'est ce cache qui empêche un objet mis en pool de traverser la frontière : on emprunte
 *  UNE fois pour lire, jamais pour substituer (cf. la branche `guildWar` de la délégation, et
 *  l'exception `BeforeReturnToPoolAttempt` qu'elle a coûtée). Remis à `null` à chaque
 *  (dés)armement du prêteur, pour qu'un remontage relise plutôt que de servir un roster périmé. */
export let idsGuildWar: string[] | null = null;

/** Le roster ONSLAUGHT, même forme et pour les mêmes raisons.
 *
 *  ⚠ IL LUI FAUT SA PROPRE CASE, et pas seulement une branche : le cache est ce qui garde
 *  l'emprunt à UN SEUL par montage. Le partager avec la guerre de guilde ferait servir le roster
 *  de l'autre mode après un changement de prêteur -- silencieusement, et avec un roster qui a
 *  l'air parfaitement valide. */
export let idsOnslaught: string[] | null = null;

/** Le roster CAMPAGNE, même forme et pour les mêmes raisons — cf. la branche `campagne`. */
export let idsCampagne: string[] | null = null;

/** Le roster de l'ÉVÉNEMENT Machines of War (Incursion), même forme et même raison de cache.
 *
 *  ⚠ IL NE SE LIT PAS PAR LA MÉTHODE DÉLÉGUÉE, et c'est ce qui le distingue des quatre autres.
 *  `GetUnitsForDeploymentHUD` rend un `PooledList<String>` — un objet MIS EN POOL, dont la
 *  traversée de frontière fait lever `BeforeReturnToPoolAttempt` au `Dispose` de l'appelant.
 *  La même source expose `GetUnlockedUnits()`, qui appelle `CloneAsListAndDispose` : ce qu'on
 *  reçoit est une `List<String>` NORMALE. On lit donc par là, et on ne fait que REMPLIR le
 *  retour du jeu — rien ne traverse. */
export let idsMowEvent: string[] | null = null;

/** Le roster PvP -- MEME lecteur que l'evenement (`GetUnlockedUnits`), sa PROPRE case.
 *
 *  ⚠ La case separee n'est pas du zele : le cache est ce qui garde l'emprunt a UN par montage, et
 *  le partager ferait servir le roster de l'autre mode apres un changement de preteur -- avec un
 *  contenu parfaitement plausible. C'est exactement la raison ecrite pour `idsOnslaught`. */
export let idsPvp: string[] | null = null;

/** Les prêteurs dont le roster se lit par `GetUnlockedUnits()` -- un seul foyer pour les deux.
 *
 *  ⚠ `PvpGameModeSource` ET `MachinesOfWarEventGameModeSource` exposent TOUS DEUX cette méthode
 *  (vérifié dans `methods.tsv` du build courant). Elle appelle `CloneAsListAndDispose` et rend une
 *  `List<String>` NORMALE, là où `GetUnitsForDeploymentHUD` rend un `PooledList<String>` dont la
 *  traversée de frontière fait lever `BeforeReturnToPoolAttempt`. À contrat égal, on prend le
 *  lecteur qui n'a pas ce mode de panne — et on n'écrit pas deux fois la même branche. */
export function lisParUnlockedUnits(nom: Preteur): boolean {
    return nom === "mowEvent" || nom === "pvp";
}

export function cacheUnlocked(nom: Preteur): string[] | null {
    return nom === "pvp" ? idsPvp : idsMowEvent;
}

export function poserCacheUnlocked(nom: Preteur, v: string[] | null): void {
    if (nom === "pvp") { idsPvp = v; } else { idsMowEvent = v; }
}

/** Les ancrages sur les DEUX bornes de `VisualBattleQuery` (cf. `deploymentBornesArmer`). */
export const listenerBornes: InvocationListener[] = [];

/** Ce que chaque borne a rendu NATIVEMENT et ce qu'on a substitué. Les deux, toujours : sans le
 *  natif à côté, on ne peut pas dire si la substitution a changé quoi que ce soit. */
export const derniersBornes: Record<string,
    { natif: number; substitue: number | null; detail: string }> = {};

/** Le cache du prêteur `nom`, en LECTURE et en ÉCRITURE — un seul foyer pour les deux modes
 *  dont le roster est un `PooledList` à 0 paramètre (`guildWar`, `onslaught`). */
export function cacheRoster(nom: Preteur): string[] | null {
    return nom === "onslaught" ? idsOnslaught : idsGuildWar;
}

export function poserCacheRoster(nom: Preteur, v: string[] | null): void {
    if (nom === "onslaught") { idsOnslaught = v; } else { idsGuildWar = v; }
}

/**
 * D'un `PooledListElement<T>` aux CHAÎNES qu'il porte. LÈVE si la forme n'est pas celle attendue —
 * un roster illisible doit se DIRE, jamais se rabattre sur une liste vide qui se lirait comme
 * « ce mode n'a pas d'unités ».
 *
 * ⚠ `_object` est résolu PAR SON NOM (`getFieldOffset` remonte la chaîne de parents : le champ est
 * déclaré par `PooledElement\`1`), jamais par un offset écrit ici.
 */
export function idsDePooledElement(el: NativePointer): string[] {
    if (el.isNull()) throw new Error("`_listWithStatus` NUL");
    const off = getFieldOffset(el.readPointer(), "_object");
    if (off <= 0) throw new Error("`_object` non résolu sur le wrapper de pool");
    const interne = el.add(off).readPointer();
    if (interne.isNull()) throw new Error("`_object` NUL");
    const ids = listeDeTextes(interne);
    if (ids === null) throw new Error("`List<String>` illisible");
    return ids;
}

/** Lit prudemment le nom de classe derrière un pointeur candidat. Ne lève jamais. */
export function classeDerriere(p: NativePointer): { classe: string | null; erreur: string | null } {
    try {
        if (p.isNull()) return { classe: null, erreur: "retour NUL" };
        const klass = p.readPointer();
        if (klass.isNull()) return { classe: null, erreur: "slot de classe NUL" };
        // `il2cpp_class_get_name` rend un `char*`, JAMAIS une chaîne JS -- `s()` est le
        // convertisseur du dépôt. L'oublier rend un `[object Object]` qui se lit comme un nom.
        const nom = s(class_get_name(klass) as NativePointer);
        return { classe: nom || null, erreur: nom ? null : "class_get_name muet" };
    } catch (e) {
        return { classe: null, erreur: "lecture refusée : " + (e as Error).message };
    }
}

/**
 * Ajoute nos ids à la liste rendue par le stub. `Add` résolu au RUNTIME sur la classe vue.
 *
 * ⚠ LE RETOUR EST UN **WRAPPER DE POOL**, PAS LA LISTE — mesuré le 2026-08-17, et c'est le
 * refus de la première version qui l'a établi : `Add` (1 param) est INTROUVABLE sur
 * `PooledListElement\`1`. `classFields` sur la classe VIVANTE donne la forme réelle :
 *
 *     Empty                       PooledListElement`1   (statique)
 *     _object                     List`1                <- LE CONTENEUR, hérité de `PooledElement\`1`
 *     <IsPooled>k__BackingField   Boolean
 *
 * On descend donc d'un cran quand `Add` manque au premier niveau — et le champ est résolu
 * **PAR SON NOM** (`getFieldOffset`, qui remonte la chaîne de parents : `_object` est déclaré
 * par le parent), jamais par un offset écrit ici. La voie empruntée est PUBLIÉE : « ça a marché »
 * ne doit pas cacher « par où ».
 */
export function remplir(retour: NativePointer, source?: string[] | null): {
    ajoutes: number; erreur: string | null; voie?: string;
} {
    const { classe, erreur } = classeDerriere(retour);
    if (classe === null) {
        return { ajoutes: 0, erreur: erreur ?? "classe du retour non identifiée" };
    }

    // Niveau 0 : le retour lui-même porte-t-il `Add` ?
    let cible = retour;
    let voie = classe;
    let miAdd = findMethodByParamCount(retour.readPointer(), "Add", 1);

    // Niveau 1 : sinon, descendre dans `_object` (le conteneur du wrapper de pool).
    if (!miAdd) {
        let off: number;
        try {
            off = getFieldOffset(retour.readPointer(), "_object");
        } catch (e) {
            return { ajoutes: 0, erreur: `\`Add\` absent de \`${classe}\` et champ \`_object\` `
                + "non résolu : " + (e as Error).message };
        }
        if (off <= 0) {
            return { ajoutes: 0, erreur: `\`Add\` absent de \`${classe}\`, et \`_object\` n'a pas `
                + "d'offset exploitable -- NE RIEN ÉCRIRE" };
        }
        const interne = retour.add(off).readPointer();
        if (interne.isNull()) {
            return { ajoutes: 0, erreur: `\`${classe}._object\` est NUL -- le wrapper de pool ne `
                + "porte aucune liste ; NE RIEN ÉCRIRE" };
        }
        const nomInterne = classeDerriere(interne).classe;
        miAdd = findMethodByParamCount(interne.readPointer(), "Add", 1);
        if (!miAdd) {
            return { ajoutes: 0, erreur: `\`Add\` (1 param) introuvable sur \`${classe}\` NI sur `
                + `son \`_object\` (\`${nomInterne ?? "?"}\`) -- NE RIEN ÉCRIRE` };
        }
        cible = interne;
        voie = `${classe}._object -> ${nomInterne ?? "?"}`;
    }

    let n = 0;
    for (const id of (source ?? (lireUnitesDraft ? lireUnitesDraft() : null)) ?? []) {
        try {
            invokeMethod(miAdd.info, cible, [createManagedString(id)]);
            n++;
        } catch (e) {
            return { ajoutes: n, voie, erreur: `\`Add("${id}")\` a levé : ` + (e as Error).message };
        }
    }
    return { ajoutes: n, erreur: null, voie };
}

// ============================================================================
// MIRROR DE `GetUnlockedUnitsPooled` (#10020-r1) — LE SECOND STUB, celui qui bloque LA POSE.
//
// LES SIX MÉTHODES DE LA SOURCE ONT **DEUX RÔLES**, et les confondre coûte cher (mesuré) :
//
//   GetUnitsForDeploymentHUD   -> l'AFFICHAGE   (rempli plus haut ; le roster apparaît)
//   GetUnlockedUnitsPooled     -> le MODÈLE     (`UnitDeploymentHud._allUnlockedUnitModels`)
//
// C'est le SECOND que consulte le garde `TryGetValue` de
// `idun.ui.UnitDeploymentHud$$TryMarkUnitAsPlaced`. Sur la sandbox il rend un dictionnaire
// **fraîchement loué** (`DictionaryPooler<K,V>.Get()`, aucun champ de `this` lu), donc vide, donc
// **toute pose est refusée quel que soit l'affichage**. Remplir le premier ne peut pas débloquer
// le second — deux heures de sondage du HUD ne l'auraient pas dit, il fallait lire le corps.
//
// POURQUOI ON N'A PAS RÉIMPLÉMENTÉ LE CORPS CAMPAGNE, ET C'EST UNE MESURE, PAS UN CONFORT
// ----------------------------------------------------------------------------------------
//   `CampaignGameModeSource$$GetUnlockedUnitsPooled(this)` lit `this+0x20` (unitProgression) ET
//   `this+0x70`, puis `<slot 0x15>(Nullable(this+0x70), 1)` suivi d'un `.Map(converter)`.
//   Or `SandboxGameModeSource` fait **0x58 octets** (`classes.tsv`) : il **N'A PAS de `+0x70`**.
//   Rejouer ce corps sur un `this` sandbox lirait HORS DES BORNES de l'objet.
//
// ⇒ On EMPRUNTE le résultat à la source CAMPAGNE VIVANTE, capturée par l'amorce
// (`getCampaignGameModeSourcePtr`). Même compte, même progression, et c'est SA méthode qui
// construit le dictionnaire — on n'en fabrique aucun. Le mirror est un emprunt, pas une copie.
//
// ⚠ CE QUE CET EMPRUNT NE GARANTIT PAS, et il faut le dire : le `+0x70` de la campagne participe
// à la requête (vraisemblablement un type/palier de campagne). Le dictionnaire obtenu est donc
// « les unités débloquées SELON LA CAMPAGNE », pas « selon la sandbox ». Tant qu'aucune mesure ne
// compare les deux, ce module ne prétend pas à l'équivalence — il rend un dictionnaire NON VIDE
// et publie sa provenance.
//
// GARDES — les mêmes que pour la phase, et pour la même raison :
//   * refus si le corps résolu est TRIVIAL (`ret` dans les 8 premiers octets) ⇒ corps dédupliqué,
//     donc adresse PARTAGÉE (cf. les 745 xrefs du §8) ;
//   * refus si aucune source campagne n'est capturée — on ne fabrique pas un dictionnaire vide
//     pour faire joli, on DIT qu'on ne peut pas ;
//   * `Interceptor.attach` + substitution du retour, JAMAIS `replace`.

export const CLS_CAMP = "CampaignGameModeSource";

/**
 * LA TABLE DE DÉLÉGATION — ce que la sandbox n'est pas capable de répondre, et qu'on va lui faire
 * demander à une VRAIE source.
 *
 * Chaque entrée est une méthode d'`IGameModeSource` que la couche déploiement interroge et que
 * `SandboxGameModeSource` STUBBE. `params` est vérifié à la résolution (arité), jamais supposé.
 *
 * ⚠ L'ORDRE N'EST PAS ARBITRAIRE : `GetUnitModel` est celui qui commande la POSE (il décide si le
 * modèle est un `HotseatUnitModel` ou un modèle de compte, donc si `IsUnlocked` passe) ;
 * `GetGameModeSpecificDeploymentHudOptions` est celui qui apporte les RESTRICTIONS (faction,
 * unité obligatoire, objectifs) — sans lui le déploiement reste permissif, ce qui n'est PAS le
 * déploiement du jeu.
 */
/**
 * ⚠ `valeurs` — QUELS PARAMÈTRES SONT DES TYPES VALEUR, et pourquoi ça ne s'improvise pas.
 *
 * `il2cpp_runtime_invoke` attend, pour un type VALEUR, un POINTEUR vers la valeur. Les
 * arguments interceptés, eux, arrivent bruts : un `System.Boolean` `false` est le mot `0`.
 * Le retransmettre tel quel revient à passer `0x0` comme adresse.
 *
 * MESURÉ le 2026-08-17 : `GetUnitModel(unitId, isPvpEnemyUnit)` -- seule entrée de cette table
 * à porter un paramètre -- a levé « access violation accessing 0x0 » sur ses 101 appels, soit
 * exactement l'adresse `false`. Les trois autres n'ont AUCUN paramètre : elles fonctionnaient
 * par chance de forme, pas parce que le transfert était correct.
 */
/** Les méthodes dont le RETOUR est un `System.Int32` — donc un TYPE VALEUR, donc une BOÎTE au
 *  sortir de `runtime_invoke`. Le chemin générique poserait la boîte telle quelle dans `retval`
 *  et le HUD lirait une adresse comme un compte. Elles ont leur branche, qui DÉBALLE (`+0x10`). */
export const DELEGUEES_ENTIERES = new Set(["MinUnitsNeededToStartBattle",
                                    "MaxUnitsPossibleToStartBattle",
                                    "AmountOfUnlockedUnits"]);

/** Les méthodes dont le corps SANDBOX est TRIVIAL — donc partagé par déduplication — et qu'on
 *  ancrerait malgré tout, en filtrant sur la classe de `this`.
 *
 *  ⚠ VIDE, ET CE N'EST PAS UNE PRUDENCE : C'EST UNE IMPOSSIBILITÉ MESURÉE.
 *  `SandboxGameModeSource$$AmountOfUnlockedUnits` fait TROIS octets — `33 c0 c3`, soit
 *  `xor eax,eax ; ret`. Frida refuse net : « unable to intercept function at 00007FFC4B7245B0 »
 *  (mesuré le 2026-08-23). Un trampoline inline a besoin de plus de place que ça, et les octets
 *  qui suivent sont le remplissage `cc` d'une AUTRE fonction. Le filtre par classe était donc la
 *  bonne idée pour le mauvais obstacle : ce n'est pas le partage qui bloque, c'est la TAILLE.
 *  Le mécanisme reste câblé (il servira à un corps partagé mais assez long) ; la liste, elle,
 *  reste vide tant qu'aucun cas ne le justifie. */
export const DELEGUEES_TRIVIALES_FILTREES = new Set<string>();

export const DELEGUEES: Array<{ nom: string; params: number; role: string; valeurs?: boolean[] }> = [
    { nom: "GetUnitModel", params: 2, valeurs: [false, true],
      role: "commande la POSE -- sandbox rend un `HotseatUnitModel`, qui échoue à `IsUnlocked`" },
    { nom: "GetGameModeSpecificDeploymentHudOptions", params: 0,
      role: "apporte les RESTRICTIONS -- sandbox rend des options par défaut, donc AUCUNE règle" },
    { nom: "GetUnitsForDeploymentHUD", params: 0,
      role: "apporte le ROSTER réel -- sandbox rend une liste vide" },
    // LE DERNIER DÉPLOIEMENT UTILISÉ — le jeu le PERSISTE, la sandbox rend un tableau VIDE.
    //
    // `CampaignGameModeSource$$GetBattleLineup(lineupIndex)` fabrique une clé
    // (`<campagne>_<lineupIndex>`), la passe au slot d'interface `0x5e` de `this+0x28` qui rend le
    // lineup SAUVEGARDÉ, puis appelle
    // `LineupHelper$$GetCampaignBattleLineupUsingRequiredUnits(lineupIndex, sauvegardé,
    // déployables, restrictions)`. `SandboxGameModeSource$$GetBattleLineup`, lui, s'écrit en
    // entier : `return <tableau vide>`.
    //
    // ⚠ C'EST LA COMPOSITION, PAS LES CASES. Le type déclaré est `System.String[]` (des `unitId`) :
    // aucune position n'y transite. Les cases restent l'affaire de `deploymentMemoire`, qui les
    // rejoue par l'étage FSM. Les deux sont complémentaires, pas redondants.
    //
    // ⚠ `lineupIndex` est un `System.Int32`, donc un TYPE VALEUR : il doit être RÉ-EMPAQUETÉ
    // (cf. le bloc `valeurs` ci-dessous), sans quoi `0` partirait comme pointeur nul.
    { nom: "GetBattleLineup", params: 1, valeurs: [true],
      role: "le DERNIER DÉPLOIEMENT du joueur sur ce noeud -- sandbox rend un tableau VIDE" },
    { nom: "GetUnlockedUnitsPooled", params: 0,
      role: "dictionnaire des débloqués -- MESURÉ jamais appelé sur ce chemin (cf. §13)" },
    // LES DEUX BORNES DU HUD. Mesuré le 2026-08-23 sur un onslaught Chaos tier 18 : une fois le
    // roster délégué (`allUnitModels` 0 -> 29), `minUnitsPossible` et `maxUnitsPossible`
    // restaient à `0` -- le HUD les lit sur la SANDBOX, qui rend zéro. Avec `min = 0` il n'y a
    // aucun plancher à franchir, et avec `max = 0` aucune place : l'écran a un roster mais reste
    // inutilisable. La source du mode, elle, rend 3 et 5.
    { nom: "MinUnitsNeededToStartBattle", params: 0,
      role: "le PLANCHER de pose -- sandbox rend 0, donc aucune règle de démarrage" },
    { nom: "MaxUnitsPossibleToStartBattle", params: 0,
      role: "le PLAFOND de pose -- sandbox rend 0, donc AUCUNE place déployable" },
    // ⚠ LE TERME QUI ÉCRASE LES DEUX AUTRES, ET QUI N'EST PAS DANS LA FORMULE QU'ON CROYAIT.
    // Le HUD ne demande PAS ses bornes à la source : il les demande à
    // `IdunBattle.View.FSM.VisualBattleQuery`, qui les CALCULE (décompilé, 2026-08-23) --
    //
    //     Max = SPMath.Min( <slot 0x31 de la source>,
    //                       GetSpawnPointCoordinatedForHumanPlayer(this).Count,
    //                       <slot 0x33 de la source> )
    //     Min = SPMath.Min( <slot 0x31>, <même Count>, <slot 0x32> )
    //
    // Déléguer `Min|MaxUnitsPossibleToStartBattle` (les slots 0x32/0x33) ne suffit donc PAS :
    // un `Min` à trois termes est écrasé par le plus petit. Mesuré sur l'onslaught Chaos tier
    // 18 : source déléguée à 3 et 5, points d'apparition du joueur = 3, et le HUD affichait
    // quand même `0/0`. Le terme coupable est le premier.
    { nom: "AmountOfUnlockedUnits", params: 0,
      role: "le 1er terme du `SPMath.Min` de `VisualBattleQuery` -- il ÉCRASE les deux bornes" },
];

export interface Delegation {
    nom: string; role: string;
    listener: InvocationListener | null;
    miCampagne: { ptr: NativePointer; info: NativePointer } | null;
    ancrage: { sandbox: string; campagne: string; tete: Tete } | null;
    /** LE PRÊTEUR SUR LEQUEL LA MÉTHODE A ÉTÉ RÉSOLUE — pas celui qui est demandé aujourd'hui.
     *  `null` = jamais armée. Cf. `armerUneDelegation` : sans ce témoin, un ré-armement avec un
     *  AUTRE prêteur laissait la méthode de l'ancien en place, en silence. */
    preteurArme: Preteur | null;
    fires: number; emprunts: number;
    /** Appels qui ont PASSÉ le filtre de classe (corps partagé). Égal à `fires` pour une
     *  méthode à corps propre. L'écart avec `fires` dit combien d'appels ÉTRANGERS traversent
     *  l'ancrage — c'est ce qui rend un filtre trop étroit visible au lieu d'inerte. */
    passesFiltre: number;
    /** Dernier incident RÉEL — jamais avalé, jamais résumé en booléen. */
    dernier: { ok: boolean; detail: string } | null;
}

export const delegations: Delegation[] = DELEGUEES.map((d) => ({
    nom: d.nom, role: d.role, listener: null, miCampagne: null, ancrage: null,
    preteurArme: null, fires: 0, emprunts: 0, passesFiltre: 0, dernier: null,
}));

/**
 * QUI PRÊTE À LA DÉLÉGATION — et ce n'est pas toujours la campagne.
 *
 * ⚠ MESURÉ le 2026-08-17, et c'est la cause d'un défaut que l'écran montrait depuis longtemps :
 * l'emplacement Machine of War ne proposait RIEN, ni en guild boss ni en PvP.
 * `SandboxGameModeSource$$GetGameModeSpecificDeploymentHudOptions` s'écrit en entier :
 *
 *     options = new GameModeSpecificUnitDeploymentHudOptions()   // ctor NU
 *     options[0x86] = 0                                          // isOnlineOnly = false
 *     return options
 *
 * Elle ne touche JAMAIS `+0x85 supportsMachinesOfWar`, qui reste donc au zéro de l'allocation.
 * Et elle ne consulte même pas `GameModeExtensions$$SupportsMachinesOfWar`, la règle qui dit
 * quels modes acceptent les MoW. Le défaut est donc dans la SANDBOX, pas dans le mode — d'où
 * son universalité.
 *
 * ⚠ EMPRUNTER À LA CAMPAGNE SUFFIRAIT À RALLUMER LES MoW, ET SERAIT FAUX : le même objet porte
 * les restrictions, la quantité déployable et les objectifs du mode. On prendrait les règles de
 * la campagne pour une bataille de guild boss — exactement le vice déjà payé sur le roster
 * (impérial sur un montage PvP). Le prêteur DOIT être la source du mode monté.
 */
/**
 * ⚠ `guildWar` REND LES DEUX DEFAUTS D'UN SEUL COUP, ET C'EST MESURE (2026-08-19).
 * Sur un montage guild war, l'écran de déploiement montrait un roster VIDE **et** aucun
 * emplacement MoW. Les deux tombent sur la même délégation :
 *
 *   - `GetUnitModel` — la sandbox rend un `HotseatUnitModel`, qui échoue à `IsUnlocked`. La HUD
 *     recevait bien les 98 unités (`dernierRemplissage.ajoutes = 98`, aucune erreur) puis les
 *     rejetait UNE PAR UNE. Le vide était donc EN AVAL du remplissage, pas dedans — et
 *     `deploymentStartArmer` le confirmait par `tailleUnits: 0` au START.
 *   - `GetGameModeSpecificDeploymentHudOptions` — le défaut sandbox décrit ci-dessus.
 *     `GuildWarsGameModeSource$$GetGameModeSpecificDeploymentHudOptionsInternal` est la SEULE
 *     lectrice de `GuildWarBattleData.RarityCap` (+0x44) : c'est elle qui pose le cap de rareté
 *     du mode en même temps que le support MoW.
 *
 * La source vient de `guildWarSourceForger` — donc du MODE MONTÉ, comme cette section l'exige.
 */
/**
 * ⚠ `onslaught` A LE MÊME DÉFAUT, ET SA CLASSE N'EST PAS LÀ OÙ ON LA CHERCHE.
 * Mesuré le 2026-08-23, tier 18 voie Chaos monté par `sandbox_mode.py start --mode waves` :
 * `stage = Setup` (la phase s'ouvre), mais le HUD rend `minUnitsPossible: 0
 * maxUnitsPossible: 0  allUnitModels: 0  allUnlockedUnitModels: 0` et `_units.taille = 0`.
 * Même stub sandbox, même remède : déléguer à la source du mode.
 *
 * ⚠ Et le piège est en amont du câblage : `OnslaughtGameModeSource` ne vit PAS dans
 * `IdunBattle.ViewLogic.BattleSource` — où sont les 23 autres sources de mode — mais sous
 * `idun.Idun.Source.IdunMeta.View.Features.Onslaught.Battle`. Un balayage limité au namespace
 * des autres rend ZÉRO et fait conclure « pas de source onslaught sur ce build ». Conclusion
 * FAUSSE, tirée d'une recherche trop étroite — elle a été faite avant ce commit.
 *
 * La source vient de `onslaughtSourceForger {alliance, tier}` — donc du MODE, et paramétrée par
 * la voie et le palier, qui sont des arguments EN CLAIR de son ctor.
 */
export type Preteur = "campagne" | "guildBoss" | "guildWar" | "onslaught" | "mowEvent" | "pvp";

export let preteurDelegation: Preteur = "campagne";

/** La source qui prête, son NAMESPACE et la CLASSE sur lesquels résoudre la méthode déléguée.
 *
 * ⚠ LE NAMESPACE FAIT PARTIE DU PRÊTEUR. Il était supposé valoir `NS_SRC` pour tout le monde —
 * vrai pour trois prêteurs sur quatre, faux pour l'onslaught, et l'échec était SILENCIEUX. */
export function sourcePreteuse(): { ptr: NativePointer | null; ns: string; cls: string; nom: Preteur } {
    if (preteurDelegation === "guildBoss") {
        return { ptr: sourceGuildBossForgee(), ns: NS_SRC,
                 cls: "GuildBossGameModeSource", nom: "guildBoss" };
    }
    if (preteurDelegation === "guildWar") {
        return { ptr: sourceGuildWarForgee(), ns: NS_SRC,
                 cls: "GuildWarsGameModeSource", nom: "guildWar" };
    }
    if (preteurDelegation === "onslaught") {
        return { ptr: sourceOnslaughtForgee(),
                 ns: "idun.Idun.Source.IdunMeta.View.Features.Onslaught.Battle",
                 cls: "OnslaughtGameModeSource", nom: "onslaught" };
    }
    // L'EVENEMENT Machines of War (Incursion). Son roster deployable n'est PAS celui de la
    // campagne : `GetUnlockedUnits` y rend les unites eligibles de l'evenement (24 mesurees,
    // toutes de l'alliance imposee par le palier). Emprunter a la campagne offrirait le roster
    // du noeud ou pointe la source captee -- un ecran plausible, et faux.
    if (preteurDelegation === "mowEvent") {
        return { ptr: sourceMowEventForgee(), ns: NS_SRC,
                 cls: "MachinesOfWarEventGameModeSource", nom: "mowEvent" };
    }
    // L'ARENE. Son roster deployable est celui du COMPTE, borne par ce que le mode autorise --
    // ni le noeud de campagne ou pointe la source captee, ni l'alliance d'un palier d'evenement.
    // La source se FORGE (`pvpSourceForger`), donc sans consommer de tentative : seul un combat
    // en consomme, et `LoadBattleInternal` n'en est pas un.
    if (preteurDelegation === "pvp") {
        return { ptr: sourcePvpForgee(), ns: NS_SRC, cls: "PvpGameModeSource", nom: "pvp" };
    }
    // ⚠ LA CAPTÉE D'ABORD, LA FORGÉE ENSUITE -- et le repli n'est pas un confort.
    // La source captée l'est par un ancrage sur le ctor, qui ne tire QU'À LA NAVIGATION : après
    // un reinject, ou sur un nœud monté en sandbox sans passer par l'écran, elle est NULLE. Le
    // prêteur rendait alors `null`, la délégation ne se faisait pas, et l'écran de déploiement
    // affichait un ROSTER VIDE (mesuré le 2026-08-20 sur `elite4` nœud 31) -- BC juste, écran
    // inutilisable. `campaignSourceForger` construit la même classe sans naviguer : on l'accepte
    // exactement comme le prêteur guild boss accepte la sienne.
    const captee = getCampaignGameModeSourcePtr();
    if (captee !== null && !captee.isNull()) {
        return { ptr: captee, ns: NS_SRC, cls: CLS_CAMP, nom: "campagne" };
    }
    return { ptr: sourceCampagneForgee(), ns: NS_SRC, cls: CLS_CAMP, nom: "campagne" };
}

/** Le contexte du prêteur guild boss, retenu pour pouvoir RÉ-EMPRUNTER à l'identique. */
export let gbEncounterIndex = 0;

export let gbIncludeLocked = false;

/**
 * ⚠ UNE `PooledList` NE SE SUBSTITUE QU'UNE FOIS -- et c'est le RETRY qui l'a révélé.
 *
 * Le pré-emprunt fige UNE valeur, calculée avant le montage, puis la re-pose à chaque appel.
 * Ça tient tant qu'il n'y a qu'un seul `Show`. Mesuré le 2026-08-17 : au RETRY, l'écran revient
 * bien en phase de déploiement mais le roster est VIDE -- le premier `Show` a consommé la
 * liste, qui est retournée au pool, et le second reçoit un pointeur recyclé. Le nom du type le
 * disait déjà.
 *
 * Le prêteur guild boss n'a AUCUN besoin du pré-emprunt : celui-ci n'existe que pour laisser le
 * masque `sansFiltre` agir hors hook (cf. §24), or `GetDeployableUnitsPooled` applique déjà
 * `DisallowedFactions`. On ré-emprunte donc FRAIS à chaque appel.
 */
export function rosterFraisGuildBoss(): NativePointer | null {
    const boite = rosterPooledGuildBoss(gbEncounterIndex, gbIncludeLocked);
    if (typeof boite === "object" && boite !== null
        && (boite as { ok?: boolean }).ok === false) return null;
    const b = boite as NativePointer;
    if (b.isNull()) return null;
    gcRoot.add(b);
    try {
        // `PooledList<T>` est un TYPE VALEUR : `runtime_invoke` le boxe, la valeur est à +0x10.
        const deboxe = b.add(0x10).readPointer();
        if (deboxe.isNull()) return null;
        gcRoot.add(deboxe);
        return deboxe;
    } catch { return null; }
}

// ============================================================================
// ROSTER NON FILTRÉ — lever le filtre de NŒUD, sans toucher au nœud.
//
// `CampaignProgression$$GetDeployableUnits(locationIndex: Nullable<Int32>, onlyUnlocked)`
// charge TA collection puis la filtre :
//
//     info = null
//     si locationIndex.HasValue :                       <-- TOUT le filtrage est sous ce test
//         info = (this->_battles[idx], GetStarsOfLocation(idx))
//     unites = this->_unitProgression.GetUnits(flags, null)
//     return CampaignBattleInfo.GetDeployableUnits(info, ..., unites, ...)
//
// Un `Nullable` SANS valeur rend donc la collection non filtrée. Mais
// `CampaignGameModeSource$$GetUnitsForDeploymentHUD` en construit toujours un AVEC valeur
// (depuis `_currentLocationIndex`, un `Int32`) : ce chemin est inatteignable sans intervenir.
//
// ⚠ DEUX RÉGIMES, ET L'OBSERVATION EST LE DÉFAUT. On ne sait pas d'avance si un
// `Nullable<Int32>` (8 octets) arrive PAR VALEUR dans un registre — auquel cas `args[1]` porte
// `valeur | hasValue<<32` — ou PAR POINTEUR. Masquer un POINTEUR le corromprait, et une faute
// native sur le thread principal fige le jeu (deux fois le 2026-08-17). On LIT donc d'abord :
// `74` + `hasValue 1` donnerait `0x10000004a`, une adresse de tas ne ressemble à rien de tel.
//
// ⚠ Et l'effet est BORNÉ À L'APPEL EMPRUNTÉ (`dansEmprunt`) : `GetDeployableUnits` sert aussi
// aux écrans méta, où lever le filtre mentirait à l'interface du jeu.
export let sansFiltreArme = false;

export let sansFiltreEcrit = false;

export let dansEmprunt = false;

export let listenerDeployable: InvocationListener | null = null;

// ⚠ COMPTER TOUS LES PASSAGES, PAS SEULEMENT CEUX DE LA FENÊTRE. Un compteur conditionné par
// `dansEmprunt` ne sait pas distinguer « la méthode n'est jamais appelée » (donc la classe
// ancrée est la mauvaise) de « elle est appelée hors fenêtre » (donc c'est ma fenêtre qui est
// fausse). Les deux rendent zéro observation, et ce zéro-là ne désigne rien.
export let firesDeployable = 0;

// La valeur PRÉ-EMPRUNTÉE, déjà déboxée, prête à être substituée par la délégation.
export let preEmprunt: NativePointer | null = null;

export let preEmpruntInfo: Record<string, unknown> | null = null;

export const observationsNullable: Array<{
    brut: string; basse: string; haute: string; dansEmprunt: boolean; ecrit: boolean;
}> = [];

export function armerSansFiltre(ecrire: boolean): true | Refus {
    sansFiltreArme = true;
    sansFiltreEcrit = ecrire;
    if (listenerDeployable) return true;
    const k = findClassAnywhere("IdunMetaLogic.UserProgress", "CampaignProgression");
    if (!k) return refus("`CampaignProgression` INTROUVABLE sur ce build");
    const mi = findMethodByParamCount(k, "GetDeployableUnits", 2);
    if (!mi) {
        return refus("`CampaignProgression$$GetDeployableUnits` INTROUVABLE (2 paramètres)");
    }
    const tete = lireTete(mi.ptr);
    if (tete.erreur !== null) return refus(`tête ILLISIBLE (${tete.erreur})`);
    if (teteTriviale(tete)) {
        return refus("REFUS : `GetDeployableUnits` résout sur un corps TRIVIAL "
            + `(ret à l'octet ${tete.retA} ; tête = ${tete.hex}) -- adresse probablement `
            + "PARTAGÉE par déduplication IL2CPP. Cf. case-10020 §8.");
    }
    listenerDeployable = Interceptor.attach(mi.ptr, {
        onEnter(args) {
            firesDeployable++;
            const brut = args[1];
            let ecrit = false;
            if (sansFiltreArme && dansEmprunt && sansFiltreEcrit) {
                // ⚠ DISPOSITION **MESURÉE**, ET ELLE EST L'INVERSE DE CELLE QU'ON SUPPOSE.
                // Observation d'un appel NATUREL du jeu : `0x4a00000001` pour
                // `_currentLocationIndex = 74`. Donc 32 bits BAS = `hasValue` (1), 32 bits
                // HAUTS = la valeur (0x4a). Le `Nullable<Int32>` est rangé
                // `{ bool hasValue; int value; }`, pas `{ int value; bool hasValue; }`.
                //
                // Masquer les bits BAS (ce que faisait la version d'avant) aurait gardé
                // `hasValue = 1` et mis l'index à 0 : un AUTRE nœud, pas l'absence de filtre.
                // Ça aurait « marché » en faisant tout autre chose -- et c'est exactement ce
                // que le régime observation-d'abord existe pour attraper.
                args[1] = brut.and(ptr("0xffffffff00000000"));
                ecrit = true;
            }
            if (observationsNullable.length < 24) {
                observationsNullable.push({
                    brut: brut.toString(),
                    basse: brut.and(ptr("0xffffffff")).toString(),
                    haute: brut.shr(32).toString(),
                    dansEmprunt, ecrit,
                });
            }
        },
    });
    Interceptor.flush();
    return true;
}

// ============================================================================
// LE PLAFOND DE POSE — pourquoi « je sélectionne mais je ne pose pas ».
//
// Mesuré sur le HUD vivant : `allUnitModels = 55`, `allUnlockedUnitModels = 49`,
// `disabledInput = false`, mais **`maxUnitsPossible = 0`**. Le verrou n'est donc PAS
// `IsUnlocked` (49 unités sont posables) : le HUD a reçu l'autorisation de poser ZÉRO unité.
//
// `IdunBattle.View.FSM.VisualBattleQuery$$MaxUnitsPossibleToStartBattle` calcule :
//
//     min( source.AmountOfUnlockedUnits(),
//          GetSpawnPointCoordinatedForHumanPlayer(this).Count,
//          source.MaxUnitsPossibleToStartBattle() )
//
// (slots d'interface 0x31 et 0x33, NOMMÉS par `classInterfaceSlots` — lus, pas dérivés.)
//
// Et `SandboxGameModeSource$$AmountOfUnlockedUnits` résout sur un corps `return 0;`
// **DÉDUPLIQUÉ, 1233 xrefs**, que Ghidra nomme `UnityAdsIdentifier$$get_UserId`. D'où
// `min(0, ...) = 0`.
//
// ⛔ ON N'ANCRE PAS CE CORPS. 1233 consommateurs basculeraient — c'est exactement le piège du
// §8. On ancre le RELAIS, qui est un vrai corps, et on remplace SON retour. Même forme que le
// forçage de phase, qui marche par la même raison.
// ⚠ LES DEUX BORNES, PAS SEULEMENT LE PLAFOND. `Show(units, min, max, options)` en reçoit
// DEUX, et `VisualBattleQuery` porte un relais pour chacune
// (`MaxUnitsPossibleToStartBattle`, `MinUnitsNeededToStartBattle`). Ne forcer que le max
// laisserait le HUD sur un intervalle décidé à moitié par la sandbox — et un `min` qui vaut
// autre chose que ce qu'on croit se lirait comme un refus de poser, exactement le symptôme
// qu'on vient de passer une heure à attribuer.
export interface Borne {
    methode: string;
    listener: InvocationListener | null;
    impose: number | null;
    fires: number;
    obs: Array<{ rendu: number; impose: number | null }>;
}

export const BORNES: Record<"max" | "min", Borne> = {
    max: { methode: "MaxUnitsPossibleToStartBattle",
           listener: null, impose: null, fires: 0, obs: [] },
    min: { methode: "MinUnitsNeededToStartBattle",
           listener: null, impose: null, fires: 0, obs: [] },
};

export function armerBorne(b: Borne): true | Refus {
    if (b.listener) return true;
    const k = findClassAnywhere(NS_VBQ, CLS_VBQ);
    if (!k) return refus(`\`${NS_VBQ}.${CLS_VBQ}\` INTROUVABLE sur ce build`);
    const mi = findMethodByParamCount(k, b.methode, 0);
    if (!mi) return refus(`\`${CLS_VBQ}$$${b.methode}\` INTROUVABLE (0 paramètre)`);
    const t = lireTete(mi.ptr);
    if (t.erreur !== null) return refus(`tête de \`${b.methode}\` ILLISIBLE (${t.erreur})`);
    if (teteTriviale(t)) {
        return refus(`REFUS : \`${CLS_VBQ}$$${b.methode}\` résout sur un corps TRIVIAL `
            + `(ret à l'octet ${t.retA} ; tête = ${t.hex}) -- adresse PARTAGÉE par `
            + "déduplication. C'est précisément ce qu'on évite en visant le relais plutôt "
            + "que `AmountOfUnlockedUnits`. Cf. §8.");
    }
    b.listener = Interceptor.attach(mi.ptr, {
        onLeave(retval) {
            b.fires++;
            const rendu = retval.toInt32();
            if (b.impose !== null) retval.replace(ptr(b.impose));
            if (b.obs.length < 32) b.obs.push({ rendu, impose: b.impose });
        },
    });
    Interceptor.flush();
    return true;
}

/** Arme UNE délégation. Rend un refus NOMMÉ plutôt qu'un silence. */
export function armerUneDelegation(
    d: Delegation, spec: { nom: string; params: number; valeurs?: boolean[] },
): true | Refus {
    // ⚠ DÉJÀ ARMÉE ≠ ARMÉE SUR LE BON PRÊTEUR, ET LES CONFONDRE PRODUIT UNE CONFUSION DE TYPE.
    //
    // Ce test était `if (d.listener) return true;` — un ré-armement demandant un AUTRE prêteur
    // ressortait donc VERT sans rien re-résoudre, et `d.miCampagne` restait la méthode de
    // l'ancien. Mesure du 2026-08-21, montage guild war après trois montages de campagne :
    // `preteurDelegation` valait bien `guildWar` et l'OBJET prêté était la source GW, mais la
    // MÉTHODE invoquée était `CampaignGameModeSource$$GetUnitsForDeploymentHUD` (`+0x511fe0`)
    // au lieu de `GuildWarsGameModeSource$$GetUnitsForDeploymentHUD` (`+0x520300`). On exécutait
    // donc du natif de campagne sur une disposition mémoire de guerre de guilde : le champ de
    // progression lu à l'offset de la campagne tombait sur l'`_onlineFeatureDecider` de l'objet
    // GW, d'où `MethodAccessException: ICampaignProgression.GetDeployableUnits on type
    // OnlineFeatureDecider` — et un écran de déploiement au roster VIDE.
    //
    // C'est exactement ce que `guildWarSourceBc` refuse par ailleurs (« invoquer dessus
    // exécuterait du natif sur une disposition mémoire étrangère ») : ici on le faisait.
    if (d.listener) {
        const voulu = sourcePreteuse().nom;
        if (d.preteurArme === voulu) return true;
        // Le prêteur a changé : on DÉPOSE et on re-résout. Un `detach` ici est sûr — on n'est
        // pas dans l'appel qu'on ancre, on arme.
        d.listener.detach();
        d.listener = null;
        d.miCampagne = null;
        d.ancrage = null;
    }

    const ks = findClassAnywhere(NS_SRC, CLS_SANDBOX);
    if (!ks) return refus(`${NS_SRC}.${CLS_SANDBOX} INTROUVABLE`);
    const ms = findMethodByParamCount(ks, spec.nom, spec.params);
    if (!ms) return refus(`\`${CLS_SANDBOX}$$${spec.nom}\` INTROUVABLE (${spec.params} param)`);

    // MÊME GARDE QUE PARTOUT AILLEURS DANS CE MODULE : un corps trivial est probablement
    // DÉDUPLIQUÉ, donc son adresse est PARTAGÉE, et s'y attacher basculerait N méthodes. Cf. §8.
    const tete = lireTete(ms.ptr);
    if (tete.erreur !== null) {
        return refus(`tête du corps de \`${spec.nom}\` ILLISIBLE (${tete.erreur})`);
    }
    // ⚠ L'EXCEPTION À CETTE GARDE, ET POURQUOI ELLE EST SÛRE.
    // `SandboxGameModeSource$$AmountOfUnlockedUnits` EST un corps trivial : `33 c0 c3`, soit
    // `xor eax,eax ; ret` -- il rend 0, et son adresse est partagée par toutes les méthodes du
    // binaire qui rendent 0. Refuser tout net rendait ce terme INATTEIGNABLE, et il est
    // précisément celui qui écrase les deux bornes du HUD (`SPMath.Min(0, 3, 5) = 0`).
    //
    // Ce qui rend l'ancrage dangereux, ce n'est pas le PARTAGE de l'adresse : c'est de répondre
    // à TOUS ceux qui y passent. On garde donc l'ancrage et on FILTRE SUR LA CLASSE DE `this` --
    // on ne substitue que quand l'appel vient bien d'une `SandboxGameModeSource`, et on laisse
    // le `0` natif à tous les autres. Le compteur `passesFiltre` publie la part réellement
    // substituée : si elle reste à 0 alors que `fires` monte, le filtre est trop étroit et ça
    // se VOIT, au lieu de se lire comme « la délégation ne sert à rien ».
    if (teteTriviale(tete) && !DELEGUEES_TRIVIALES_FILTREES.has(spec.nom)) {
        return refus(`REFUS : \`${CLS_SANDBOX}$$${spec.nom}\` résout sur un corps TRIVIAL `
            + `(ret à l'octet ${tete.retA} ; tête = ${tete.hex}) -- adresse probablement PARTAGÉE `
            + "par déduplication IL2CPP. Cf. case-10020 §8.");
    }
    const corpsPartage = teteTriviale(tete);

    // La méthode est résolue sur la classe du PRÊTEUR retenu, pas sur la campagne par défaut.
    //
    // ⚠ ET SUR SON NAMESPACE À LUI. `NS_SRC` était écrit en dur ici : trois prêteurs sur quatre
    // vivent bien dans `IdunBattle.ViewLogic.BattleSource`, mais pas `OnslaughtGameModeSource`
    // (cf. le pavé de `Preteur`). Mesuré le 2026-08-23 : les 4 délégations rendaient
    // `IdunBattle.ViewLogic.BattleSource.OnslaughtGameModeSource INTROUVABLE` — et
    // `deploymentPoolArmer` répondait pourtant `{ok: true, action: "arme"}`, parce que le détail
    // par méthode vit dans `rapport`, que l'appelant ne lit pas forcément. Un armement qui rend
    // `ok` sans rien avoir armé se lit comme un succès : c'est l'écran vide qui l'a démenti.
    const preteur = sourcePreteuse();
    const kc = findClassAnywhere(preteur.ns, preteur.cls);
    if (!kc) return refus(`${preteur.ns}.${preteur.cls} INTROUVABLE`);
    const mc = findMethodByParamCount(kc, spec.nom, spec.params);
    if (!mc) {
        return refus(`\`${preteur.cls}$$${spec.nom}\` INTROUVABLE (${spec.params} param) -- ce `
            + "prêteur ne porte pas cette méthode, donc il n'y a rien à quoi déléguer");
    }
    d.miCampagne = mc;
    d.preteurArme = preteur.nom;

    const nParams = spec.params;
    d.listener = Interceptor.attach(ms.ptr, {
        // Les arguments sont capturés à l'ENTRÉE : au `onLeave` ils ne sont plus lisibles.
        // `args[0]` est le `this` sandbox — on ne le transmet PAS, c'est tout l'objet de la
        // délégation : la vraie source répond avec SON état.
        onEnter(args) {
            // CORPS PARTAGÉ : on n'a le droit de répondre que pour la sandbox. La classe de
            // `this` est le seul discriminant disponible ici — l'adresse, elle, est commune à
            // toutes les méthodes déduplicées.
            (this as unknown as { pourNous: boolean }).pourNous = !corpsPartage || (() => {
                try {
                    const o = args[0];
                    if (o.isNull()) return false;
                    return s(class_get_name(o.readPointer()) as NativePointer) === CLS_SANDBOX;
                } catch { return false; }
            })();
            // Un paramètre de type VALEUR doit être RÉ-EMPAQUETÉ : on alloue et on écrit la
            // valeur, puis on transmet SON ADRESSE. Sans ça, `false` (le mot 0) part comme
            // pointeur nul -- cf. le bloc `valeurs` sur `DELEGUEES`.
            const bruts = nParams >= 1 ? [args[1], args[2]].slice(0, nParams) : [];
            (this as unknown as { argv: NativePointer[] }).argv = bruts.map((a, i) => {
                if (!spec.valeurs || !spec.valeurs[i]) return a;
                const cell = Memory.alloc(8);
                cell.writePointer(a);          // conserve les 8 octets tels quels
                return cell;
            });
        },
        onLeave(retval) {
            d.fires++;
            // Sur un corps partagé, tout ce qui n'est pas la sandbox repart avec sa valeur
            // native. `fires` compte quand même : l'écart `fires - passesFiltre` DIT combien
            // d'appels étrangers traversent, donc si le filtre est au bon endroit.
            if (!(this as unknown as { pourNous: boolean }).pourNous) return;
            d.passesFiltre++;
            const p = sourcePreteuse();
            const src = p.ptr;
            if (src === null || src.isNull()) {
                d.dernier = { ok: false, detail: `aucune source \`${p.cls}\` (prêteur `
                    + `${p.nom}) -- pour la campagne : amorce non joué ou session froide ; pour `
                    + "le guild boss : `guildBossSourceForger` n'a pas été appelé ; pour le "
                    + "guild war : `guildWarSourceForger` n'a pas été appelé. "
                    + "RIEN SUBSTITUÉ." };
                return;
            }
            // PRÉ-EMPRUNT : la valeur a été calculée HORS de tout hook, donc l'ancrage sur
            // `GetDeployableUnits` a pu la voir — et le masque `sansFiltre` a pu agir. Ici on
            // ne fait plus que la poser. C'est la seule forme qui permette de modifier
            // l'appel emprunté (cf. §24 : un `Interceptor` est aveugle aux appels imbriqués).
            // GUILD BOSS : on ré-emprunte FRAIS, jamais la valeur figée -- une `PooledList`
            // consommée par un premier `Show` revient VIDE au retry (cf. `rosterFraisGuildBoss`).
            if (spec.nom === METHODE && p.nom === "guildBoss") {
                const frais = rosterFraisGuildBoss();
                if (frais === null) {
                    d.dernier = { ok: false, detail: "ré-emprunt guild boss ÉCHOUÉ -- rien "
                        + "substitué (mieux vaut le roster natif qu'une liste recyclée)" };
                    return;
                }
                retval.replace(frais);
                d.emprunts++;
                d.dernier = { ok: true, detail: `ré-emprunt FRAIS -> ${frais}` };
                return;
            }
            // GUILD WAR : ON NE SUBSTITUE PLUS LE RETOUR — ON REMPLIT CELUI DU JEU.
            //
            // ⚠ POURQUOI, ET CE QUE LA SUBSTITUTION COÛTAIT. `GetUnitsForDeploymentHUD` rend un
            // `PooledList<System.String>`, TYPE VALEUR d'UN SEUL champ
            // (`_listWithStatus : PooledListElement<T>`, mesuré par `classFields`). La version
            // précédente déboxait le retour de `runtime_invoke` (`+0x10`) et le posait dans
            // `retval` — le roster S'AFFICHAIT (0 -> 125 modèles), donc ça passait pour juste.
            // Ça ne l'était pas : la liste que la source SANDBOX venait de louer
            // (`DictionaryPooler.Get`) n'était jamais rendue, et l'appelant disposait la NÔTRE,
            // louée dans un autre pool par le `ConvertAll` de
            // `GuildWarsGameModeSource$$GetUnitsForDeploymentHUD`. La comptabilité du pool
            // (`PooledElement.IsPooled`) partait de travers, et le `Dispose` de l'appelant levait
            //
            //     MethodAccessException: 'IPoolableObject.BeforeReturnToPoolAttempt'
            //                            on type 'PooledList<System.String>'
            //
            // ⚠ ET CETTE EXCEPTION TUAIT LA BATAILLE EN SILENCE. Capturée le 2026-08-19 dans
            // `IdunBattle.View.Game.IdunGameViews$$Enable+0xf1` (pile :
            // `IdunMainView$$Start` -> `BattleAndEditorFlowController$$LoadBattle` ->
            // `IdunMainView$$StartBattle`), donc AU CHARGEMENT, avant le premier clic.
            // `IdunGameViews$$HandleException` pose alors `_isLogicPausedFromException`, qu'AUCUN
            // `ContinueLogicFromException` ne retire, et `QueueComputerActions` exige ce drapeau à
            // zéro : l'IA adverse n'était plus JAMAIS lancée. Ni popup, ni log (`_errorListeners`
            // est vide). Contre-épreuve : même montage sans cette délégation -> aucune exception,
            // aucun verrou. Sonde : `vueExceptionArmer`. Détail : `docs/rl/case-10038-*.md`.
            //
            // CE QU'ON FAIT À LA PLACE : on emprunte UNE SEULE FOIS pour LIRE les ids (chaînes
            // JS, mises en cache), puis on remplit la liste que le jeu a déjà louée. Plus aucun
            // objet mis en pool ne traverse la frontière, et le cycle de location reste au jeu.
            //
            // ⚠ CETTE BRANCHE SERT DEUX PRÊTEURS, ET C'EST UNE MESURE, PAS UNE COMMODITÉ.
            // `GuildWarsGameModeSource$$GetUnitsForDeploymentHUD` et
            // `OnslaughtGameModeSource$$GetUnitsForDeploymentHUD` ont la MÊME signature (0
            // paramètre) et le MÊME retour (`PooledList<System.String>`, un type valeur). Le
            // traitement est donc identique — mais chacun garde SON cache : partager la case
            // ferait servir le roster de l'autre mode après un changement de prêteur, avec un
            // contenu parfaitement plausible et faux.
            if (spec.nom === METHODE && (p.nom === "guildWar" || p.nom === "onslaught")) {
                const quoi = p.nom === "onslaught" ? "onslaught" : "guild war";
                if (cacheRoster(p.nom) === null) {
                    let b: NativePointer;
                    try { b = invokeMethod(mc.info, src, []) as NativePointer; }
                    catch (e) {
                        d.dernier = { ok: false,
                            detail: `lecture du roster ${quoi} a levé : ` + (e as Error).message };
                        return;
                    }
                    if (b === null || b.isNull()) {
                        d.dernier = { ok: false, detail: `la source ${quoi} a rendu NUL` };
                        return;
                    }
                    gcRoot.add(b);
                    try {
                        // La boîte porte la structure à `+0x10` ; son unique champ est le wrapper
                        // de pool, dont `_object` (résolu PAR NOM) est la `List<String>`.
                        poserCacheRoster(p.nom, idsDePooledElement(b.add(0x10).readPointer()));
                    } catch (e) {
                        d.dernier = { ok: false,
                            detail: `roster ${quoi} illisible : ` + (e as Error).message };
                        return;
                    }
                }
                const ids = cacheRoster(p.nom);
                if (ids === null || ids.length === 0) {
                    // « je n'ai pas su lire » et « c'est vide » se disent, ils ne se rabattent pas
                    // sur un roster natif silencieusement faux.
                    d.dernier = { ok: false, detail: `roster ${quoi} `
                        + (ids === null ? "ILLISIBLE" : "VIDE")
                        + " -- rien écrit, le retour natif est laissé INTACT" };
                    poserCacheRoster(p.nom, null);  // relire au prochain tir, ne pas figer l'échec
                    return;
                }
                const r = remplir(retval, ids);
                d.emprunts++;
                d.dernier = { ok: r.erreur === null,
                    detail: r.erreur === null
                        ? `${quoi} REMPLI ${r.ajoutes}/${ids.length} (${r.voie})`
                        : `remplissage ${quoi} : ${r.erreur}` };
                return;   // ⚠ `retval` INTACT — c'est tout l'objet du correctif.
            }
            // CAMPAGNE : MÊME REMÈDE QUE LE GUILD WAR — on REMPLIT la liste du jeu.
            //
            // ⚠ DEUX DÉFAUTS TOMBAIENT ICI, ET LE PREMIER SUFFISAIT À VIDER L'ÉCRAN.
            // Mesuré le 2026-08-20 sur `elite4` nœud 31 : la délégation TIRAIT et EMPRUNTAIT
            // (`fires=1 emprunts=1`, `dernier.ok` VRAI) et le roster restait VIDE. Sans
            // pré-emprunt, le chemin GÉNÉRIQUE d'en dessous posait dans `retval` le retour BRUT
            // de `runtime_invoke` — or `PooledList<System.String>` est un TYPE VALEUR, donc ce
            // retour est une BOÎTE. Le HUD lisait `_listWithStatus` sur un en-tête d'objet.
            // C'est le prix du chemin générique : il est juste pour un type RÉFÉRENCE (les
            // trois autres déléguées) et faux pour celui-ci, sans que rien ne le signale.
            //
            // Second défaut, celui du PRÉ-EMPRUNT lui-même : une `PooledList` NE SE SUBSTITUE
            // QU'UNE FOIS (cf. `rosterFraisGuildBoss`), et un objet mis en pool qui traverse la
            // frontière fait lever `BeforeReturnToPoolAttempt` au `Dispose` de l'appelant — ce
            // qui TUE la bataille EN SILENCE (cf. la branche `guildWar`). Le remplissage règle
            // les deux d'un coup : rien ne traverse, et la liste remplie est celle du jeu.
            if (spec.nom === METHODE && p.nom === "campagne") {
                if (idsCampagne === null) {
                    // LE PRÉ-EMPRUNT RESTE PRIORITAIRE, MAIS ON LE **LIT** AU LIEU DE LE POSER :
                    // c'est la seule valeur empruntée HORS hook, donc la seule sur laquelle le
                    // masque `sansFiltre` a pu agir (cf. §24 — un `Interceptor` est aveugle aux
                    // appels imbriqués). Le lever de filtre de nœud survit donc au correctif.
                    if (preEmprunt !== null) {
                        try { idsCampagne = idsDePooledElement(preEmprunt); }
                        catch (e) {
                            d.dernier = { ok: false, detail: "pré-emprunt campagne ILLISIBLE : "
                                + (e as Error).message + " -- rien écrit" };
                            return;
                        }
                    } else {
                        let b: NativePointer;
                        try { b = invokeMethod(mc.info, src, []) as NativePointer; }
                        catch (e) {
                            d.dernier = { ok: false, detail: "lecture du roster campagne a levé : "
                                + (e as Error).message };
                            return;
                        }
                        if (b === null || b.isNull()) {
                            d.dernier = { ok: false, detail: "la source campagne a rendu NUL" };
                            return;
                        }
                        gcRoot.add(b);
                        try { idsCampagne = idsDePooledElement(b.add(0x10).readPointer()); }
                        catch (e) {
                            d.dernier = { ok: false, detail: "roster campagne illisible : "
                                + (e as Error).message };
                            return;
                        }
                    }
                }
                if (idsCampagne === null || idsCampagne.length === 0) {
                    d.dernier = { ok: false, detail: "roster campagne "
                        + (idsCampagne === null ? "ILLISIBLE" : "VIDE")
                        + " -- rien écrit, le retour natif est laissé INTACT" };
                    idsCampagne = null;   // relire au prochain tir plutôt que figer un échec
                    return;
                }
                const r = remplir(retval, idsCampagne);
                d.emprunts++;
                d.dernier = { ok: r.erreur === null,
                    detail: r.erreur === null
                        ? `campagne REMPLI ${r.ajoutes}/${idsCampagne.length} (${r.voie})`
                        : `remplissage campagne : ${r.erreur}` };
                return;   // ⚠ `retval` INTACT.
            }
            // L'ÉVÉNEMENT MACHINES OF WAR : MÊME REMÈDE, AUTRE LECTEUR.
            //
            // ⚠ ON NE LIT PAS PAR LA MÉTHODE DÉLÉGUÉE. `GetUnitsForDeploymentHUD` rend un
            // `PooledList<String>` ; les branches `guildWar`/`onslaught` s'en tirent en déballant
            // la boîte à `+0x10` puis le wrapper de pool, mais la source de l'événement expose
            // `GetUnlockedUnits()`, qui appelle `CloneAsListAndDispose` et rend une `List<String>`
            // NORMALE. Un objet non poolé ne peut pas faire lever `BeforeReturnToPoolAttempt` :
            // à contrat égal, on prend le lecteur qui n'a pas ce mode de panne.
            //
            // ⚠ ET LE ROSTER DE L'ÉVÉNEMENT N'EST PAS CELUI DE LA CAMPAGNE : il est borné par
            // l'alliance du palier (24 unités Chaos mesurées au tier 11). Emprunter à la campagne
            // afficherait le roster du nœud où pointe la source captée — plausible, et faux.
            if (spec.nom === METHODE && lisParUnlockedUnits(p.nom)) {
                if (cacheUnlocked(p.nom) === null) {
                    // La classe se lit sur L'INSTANCE : c'est la classe RÉELLE, pas celle qu'on
                    // aurait re-résolue par son nom.
                    const mi = findMethodByParamCount(src.readPointer(), "GetUnlockedUnits", 0);
                    if (!mi) {
                        d.dernier = { ok: false, detail: "`GetUnlockedUnits(0)` INTROUVABLE sur "
                            + `\`${p.cls}\` -- chemin PERIME, rien écrit` };
                        return;
                    }
                    let l: NativePointer;
                    try { l = invokeMethod(mi.info, src, []) as NativePointer; }
                    catch (e) {
                        d.dernier = { ok: false, detail: `lecture du roster ${p.nom} a levé : `
                            + (e as Error).message };
                        return;
                    }
                    if (l === null || l.isNull()) {
                        d.dernier = { ok: false, detail: "`GetUnlockedUnits` a rendu NUL" };
                        return;
                    }
                    gcRoot.add(l);
                    poserCacheUnlocked(p.nom, listeDeTextes(l));
                }
                const ids = cacheUnlocked(p.nom);
                if (ids === null || ids.length === 0) {
                    d.dernier = { ok: false, detail: `roster ${p.nom} `
                        + (ids === null ? "ILLISIBLE" : "VIDE")
                        + " -- rien écrit, le retour natif est laissé INTACT" };
                    // relire au prochain tir plutôt que figer un échec
                    poserCacheUnlocked(p.nom, null);
                    return;
                }
                const r = remplir(retval, ids);
                d.emprunts++;
                d.dernier = { ok: r.erreur === null,
                    detail: r.erreur === null
                        ? `${p.nom} REMPLI ${r.ajoutes}/${ids.length} (${r.voie})`
                        : `remplissage ${p.nom} : ${r.erreur}` };
                return;   // ⚠ `retval` INTACT.
            }
            // LE LINEUP DE LA SOURCE EST UNE SAUVEGARDE — donc PÉRIMÉ dès que le joueur a touché
            // à son déploiement dans cette session.
            //
            // ⚠ MESURÉ le 2026-08-20 : au retry, l'écran revenait à la composition du dernier
            // essai RÉEL, pas à celle qu'on venait de poser. La cause n'est pas la délégation :
            // c'est que le jeu PERSISTE le lineup au démarrage d'une vraie partie
            // (`UnitProgressionData$$SetLineup`), et que la sandbox ne le fait jamais. La clé
            // `<campagne>_<index>` pointe donc toujours sur l'avant-dernier état.
            //
            // ⛔ ET ON N'ÉCRIRA PAS CETTE SAUVEGARDE. `SetLineup` touche les données du COMPTE
            // pour un essai qui n'en est pas un ; c'est exactement le genre d'écriture qui a
            // coûté un jeton. On règle le conflit dans l'autre sens : dès que notre mémoire
            // porte plus frais, on ne substitue RIEN et le tableau VIDE de la sandbox passe.
            // L'écran reste nu une fraction de seconde, puis `rejouerMemoire` y repose la
            // composition ET les cases, par l'étage FSM.
            //
            // ⚠ LA SOURCE RESTE LE FOURNISSEUR AU PREMIER MONTAGE, quand la mémoire est vide --
            // c'est là qu'elle a la seule vérité disponible.
            if (spec.nom === "GetBattleLineup" && memoirePoses.length > 0) {
                d.dernier = { ok: true, detail: "laissé au JEU (tableau vide) -- la mémoire porte "
                    + `${memoirePoses.length} pose(s), plus fraîches que la sauvegarde du compte` };
                return;
            }
            // NOTRE COMPOSITION RETENUE, QUAND IL Y EN A UNE -- ET C'EST NOUS QUI SUBSTITUONS.
            //
            // ⛔ ANCRER LA MÉTHODE DU PRÊTEUR NE MARCHE PAS DEPUIS ICI, et ce n'est pas un défaut
            // d'ancrage. Mesuré le 2026-08-25 (session 140, guerre de guilde) : MÊME méthode, MÊME
            // `invokeMethod`, le compteur `fires` de `lineup-poser` monte quand l'appel vient d'un
            // RPC et reste INCHANGÉ quand il vient d'ici — donc son callback ne tourne pas du tout.
            // Le mécanisme (garde de réentrance de `gum`) est une EXPLICATION, pas une mesure : la
            // discussion et l'hypothèse LEVÉE du partage d'adresse vivent sur
            // `substituerRetourLineup`. Le correctif ci-dessous vaut sous l'un ou l'autre.
            //
            // ⚠ APRÈS la mémoire, pas avant. Quand des poses attendent, elles sont plus fraîches
            // que toute sauvegarde (cf. le pavé précédent) et l'étage FSM les rejoue : doubler ce
            // chemin ferait deux autorités pour un seul écran.
            if (spec.nom === "GetBattleLineup") {
                const sub = substituerRetourLineup(retval, p.cls);
                if (sub !== null) {
                    const ids = sub.ids as string[] | undefined;
                    d.emprunts++;
                    d.dernier = sub.erreur === undefined
                        ? { ok: true, detail: `composition RETENUE substituée sur \`${p.cls}\` `
                            + `(${ids?.length ?? "?"}) : ${ids?.join(", ") ?? "?"} -- le prêteur `
                            + "n'a PAS été interrogé" }
                        : { ok: false, detail: "substitution de la composition retenue : "
                            + String(sub.erreur) };
                    return;
                }
            }
            // LES BORNES : un `System.Int32` revient BOXÉ de `runtime_invoke`, et le générique
            // poserait la boîte. On DÉBALLE à `+0x10` et on remplace par la valeur elle-même.
            //
            // ⚠ ET ON VÉRIFIE QUE LE COMPTE EST PLAUSIBLE. Une adresse lue comme un entier donne
            // un nombre ÉNORME ou NÉGATIF ; un plafond absurde ferait un écran encore plus cassé
            // qu'un plafond nul, et sans rien dire. Hors bornes, on ne substitue pas.
            if (DELEGUEES_ENTIERES.has(spec.nom)) {
                let boite: NativePointer;
                try { boite = invokeMethod(mc.info, src, []) as NativePointer; }
                catch (e) {
                    d.dernier = { ok: false,
                        detail: `\`${spec.nom}\` a levé : ` + (e as Error).message };
                    return;
                }
                if (boite === null || boite.isNull()) {
                    d.dernier = { ok: false, detail: `\`${spec.nom}\` a rendu NUL` };
                    return;
                }
                const v = boite.add(0x10).readS32();
                if (v < 0 || v > 64) {
                    d.dernier = { ok: false, detail: `\`${spec.nom}\` = ${v} : hors de toute `
                        + "borne plausible (0..64) -- le déballage est probablement faux, RIEN "
                        + "SUBSTITUÉ plutôt qu'un plafond absurde" };
                    return;
                }
                retval.replace(ptr(v));
                d.emprunts++;
                d.dernier = { ok: true, detail: `${spec.nom} = ${v} (déballé de la boîte)` };
                return;
            }
            // ⚠ LE CHEMIN GÉNÉRIQUE NE DOIT PLUS VOIR `METHODE`. Les quatre prêteurs ont leur
            // branche ; s'il en apparaît un cinquième, il tomberait ici et re-poserait une BOÎTE
            // dans `retval` — le défaut qu'on vient de corriger. On REFUSE plutôt que de le
            // rejouer en silence.
            if (spec.nom === METHODE) {
                d.dernier = { ok: false, detail: `prêteur \`${p.nom}\` sans branche pour `
                    + `\`${METHODE}\` : le retour est un TYPE VALEUR, le chemin générique `
                    + "poserait une BOÎTE. RIEN SUBSTITUÉ." };
                return;
            }
            try {
                const argv = (this as unknown as { argv: NativePointer[] }).argv ?? [];
                // Fenêtre de l'emprunt : c'est la SEULE pendant laquelle `sansFiltre` agit.
                // Hors d'elle, `GetDeployableUnits` sert les écrans méta du jeu.
                dansEmprunt = true;
                let r: NativePointer;
                try { r = invokeMethod(mc.info, src, argv) as NativePointer; }
                finally { dansEmprunt = false; }
                if (r === null || r.isNull()) {
                    d.dernier = { ok: false,
                        detail: "la vraie source a rendu NUL -- rien substitué" };
                    return;
                }
                retval.replace(r);
                d.emprunts++;
                d.dernier = { ok: true, detail: `délégué à ${src} -> ${r}` };
            } catch (e) {
                d.dernier = { ok: false, detail: "la délégation a levé : " + (e as Error).message };
            }
        },
    });
    d.ancrage = { sandbox: ghidraVA(ms.ptr), campagne: ghidraVA(mc.ptr), tete };
    return true;
}

export function etatPool(): Record<string, unknown> {
    const src = getCampaignGameModeSourcePtr();
    const p = sourcePreteuse();
    return {
        // ⚠ LE PRÊTEUR DEMANDÉ, ET LE PRÊTEUR RÉELLEMENT ARMÉ -- publier le premier seul serait
        // pire que rien. Mesure du 2026-08-21 : `preteurDelegation` disait `guildWar` alors que
        // les quatre délégations restaient armées sur la CAMPAGNE (cf. `armerUneDelegation`), et
        // ce statut n'exposait NI l'un NI l'autre. Il ne publiait que `sourceCampagne`, qu'on lit
        // alors naturellement comme « le prêteur » -- ça m'a fait diagnostiquer à côté deux fois.
        preteur: p.nom,
        preteurPtr: p.ptr && !p.ptr.isNull() ? p.ptr.toString() : null,
        // TRI-ÉTAT : `null` = pas de source capturée, ce qui n'est PAS « rien à déléguer ».
        // (!)CE N'EST PAS LE PRÊTEUR -- c'est la source de campagne captée par l'amorce, qui ne
        // sert que si `preteur === "campagne"`.
        sourceCampagne: src && !src.isNull() ? src.toString() : null,
        // LE ROSTER EMPRUNTÉ, EN CLAIR. Il était lu, mis en cache et versé dans la liste du jeu
        // sans jamais être publié : impossible de savoir CE QUE le HUD a reçu, ni de s'en servir
        // ailleurs (ex. peupler `BC.Units` pour que ces unités aient un prefab). `null` = pas
        // encore emprunté, ce qui n'est PAS « roster vide ».
        rosterEmprunte: cacheRoster(p.nom),
        delegations: delegations.map((d) => ({
            nom: d.nom, role: d.role, arme: d.listener !== null,
            // `null` = jamais armée. Un écart avec `preteur` ci-dessus signale une résolution
            // PÉRIMÉE -- c'est le symptôme qui n'avait aucun capteur.
            preteurArme: d.preteurArme,
            fires: d.fires, emprunts: d.emprunts, passesFiltre: d.passesFiltre,
            dernier: d.dernier, ancrage: d.ancrage,
        })),
    };
}

export function registerPool(ctx: Ctx): void {
    /** ÉTAT du mirror de `GetUnlockedUnitsPooled`. Lecture pure. */
    ctx.rpc.deploymentPoolStatus = (): unknown => ({ ok: true, lecture: true, ...etatPool() });

    /**
     * LE PLAFOND DE POSE — observe, et sur demande IMPOSE.
     *
     *   { armer: true }                                  -> observe ce que le relais rend
     *   { armer: true, valeur: N, confirmer: true }       -> impose N
     *
     * ⚠ On agit sur le RELAIS `VisualBattleQuery`, jamais sur
     * `SandboxGameModeSource$$AmountOfUnlockedUnits` : ce dernier résout sur un `return 0;`
     * DÉDUPLIQUÉ à 1233 xrefs. L'ancrer basculerait un millier de prédicats sans rapport.
     */
    ctx.rpc.deploymentPlafondArmer = (body?: {
        armer?: boolean; max?: number; min?: number; confirmer?: boolean;
    }): unknown => {
        const etat = () => ({
            max: { arme: BORNES.max.listener !== null, impose: BORNES.max.impose,
                   fires: BORNES.max.fires, observations: BORNES.max.obs },
            min: { arme: BORNES.min.listener !== null, impose: BORNES.min.impose,
                   fires: BORNES.min.fires, observations: BORNES.min.obs },
        });
        if (!body || body.armer === undefined) {
            return { ok: true, lecture: true, ...etat() };
        }
        if (body.armer === false) {
            for (const b of [BORNES.max, BORNES.min]) {
                if (b.listener) b.listener.detach();
                b.listener = null; b.impose = null;
            }
            Interceptor.flush();
            return { ok: true, action: "retire", ...etat() };
        }
        if ((body.max !== undefined || body.min !== undefined) && body.confirmer !== true) {
            return { ok: false, error: "`confirmer: true` exigé pour IMPOSER une borne : on "
                + "écrit dans la décision de `VisualBattleQuery`, que TOUS les modes de jeu "
                + "partagent. Observer d'abord (`{ armer: true }`)." };
        }
        // On arme les DEUX relais même si une seule valeur est imposée : observer la borne
        // qu'on ne force pas est ce qui dit si elle valait déjà ce qu'on croit.
        for (const b of [BORNES.max, BORNES.min]) {
            const r = armerBorne(b);
            if (r !== true) return r;
        }
        if (body.max !== undefined) BORNES.max.impose = body.max | 0;
        if (body.min !== undefined) BORNES.min.impose = body.min | 0;
        return { ok: true, ...etat() };
    };

    /**
     * ⚠ `source` — LE PRÊTEUR EST CELUI DU MODE, ET C'EST UNE RÈGLE, PAS UNE OPTION.
     *
     * Le roster affiché doit venir de la source du mode qu'on monte, sinon on importe les
     * PERMISSIONS d'un autre mode. Mesuré le 2026-08-17 : emprunté à la campagne sur un
     * montage PvP, l'écran n'offrait que les Impériaux — parce que
     * `CampaignGameModeSource$$GetUnitsForDeploymentHUD` rend
     * `_campaignProgression.GetDeployableUnits(locationIndex, onlyUnlocked: false)`, soit la
     * liste déployable de CETTE campagne.
     *
     * `PvpGameModeSource$$GetUnitsForDeploymentHUD` est, lui, une LECTURE PURE d'un champ déjà
     * rempli (`this+0x88`, converti en liste poolée) — vérifié au décompilé : aucun appel
     * serveur, aucun matchmaking.
     *
     * ⚠ Le défaut reste `campagne` et la source RETENUE est publiée : un choix implicite entre
     * deux prêteurs se lirait comme « ça marche » alors qu'on offrirait le mauvais roster.
     */
    ctx.rpc.deploymentPoolPreEmprunt = (body?: {
        confirmer?: boolean; oublier?: boolean; source?: "campagne" | "pvp" | "guildBoss";
        encounterIndex?: number; includeLocked?: boolean;
    }): Promise<unknown> | unknown => {
        if (body?.oublier === true) {
            preEmprunt = null; preEmpruntInfo = null;
            return { ok: true, action: "oublie" };
        }
        if (!body || body.confirmer === undefined) {
            return { ok: true, lecture: true, pret: preEmprunt !== null, info: preEmpruntInfo,
                     sources: {
                         campagne: getCampaignGameModeSourcePtr()?.toString() ?? null,
                         pvp: getPvpGameModeSourcePtr()?.toString() ?? null,
                         guildBoss: "via la PROGRESSION, pas une GameModeSource",
                     },
                     note: "`source: \"pvp\"` emprunte le roster à la source PvP -- c'est ce "
                         + "qu'il faut pour un montage PvP ; la campagne n'offrirait que sa "
                         + "propre liste déployable. `source: \"guildBoss\"` passe par "
                         + "`GuildBossProgression$$GetDeployableUnitsPooled`, qui APPLIQUE "
                         + "`DisallowedFactions` -- le filtre du mode, pas une liste brute." };
        }
        if (body.confirmer !== true) {
            return { ok: false, error: "`confirmer: true` exigé : ce RPC INVOQUE la méthode de "
                + "la source de mode vivante." };
        }
        const quelle = body.source ?? "campagne";

        // GUILD BOSS — le prêteur n'est PAS une `GameModeSource` mais la PROGRESSION.
        //
        // ⚠ Ce n'est pas un contournement faute d'instance : au décompilé,
        // `GuildBossGameModeSource$$IsUnitDeployable` ne fait que DÉLÉGUER à la progression
        // (slot d'interface `0x36`, avec son index d'encounter). La règle vit donc là, et
        // `GetDeployableUnitsPooled` APPLIQUE déjà `DisallowedFactions` -- ce qu'on emprunte
        // est le roster FILTRÉ par le mode, pas une liste brute qu'il faudrait re-filtrer.
        if (quelle === "guildBoss") {
            const idx = body.encounterIndex ?? 0;
            const incl = body.includeLocked === true;
            // Retenu pour que le RÉ-EMPRUNT de la délégation reparte du MÊME contexte : un
            // roster frais qui viserait un autre encounter serait pire qu'une liste vide.
            gbEncounterIndex = idx;
            gbIncludeLocked = incl;
            return queueOnMainThread(() => {
                const boite = rosterPooledGuildBoss(idx, incl);
                if (typeof boite === "object" && boite !== null
                    && (boite as { ok?: boolean }).ok === false) {
                    return { ok: false, source: quelle, ...(boite as object) };
                }
                const b = boite as NativePointer;
                gcRoot.add(b);
                const cBoite = classeDerriere(b);
                let deboxe: NativePointer;
                try { deboxe = b.add(0x10).readPointer(); }
                catch (e) {
                    return { ok: false, source: quelle,
                             error: "déboxage impossible : " + (e as Error).message };
                }
                if (deboxe.isNull()) {
                    return { ok: false, source: quelle,
                             error: "déboxage -> NUL : on ne substitue RIEN plutôt que de poser "
                                 + "un pointeur douteux",
                             boite: b.toString(), classeBoite: cBoite.classe };
                }
                gcRoot.add(deboxe);
                const cDeboxe = classeDerriere(deboxe);
                preEmprunt = deboxe;
                preEmpruntInfo = {
                    source: quelle, instance: "progression", encounterIndex: idx,
                    includeLocked: incl,
                    boite: b.toString(), classeBoite: cBoite.classe, erreurBoite: cBoite.erreur,
                    deboxe: deboxe.toString(), classeDeboxee: cDeboxe.classe,
                    erreurDeboxee: cDeboxe.erreur,
                    // Le témoin de `GetDeployableUnits` ne vaut QUE pour la campagne : ni la
                    // source PvP ni la progression guild boss ne passent par elle.
                    deltaGetDeployableUnits: null,
                    masqueArme: sansFiltreArme && sansFiltreEcrit,
                };
                return { ok: true, ...preEmpruntInfo };
            });
        }

        return queueOnMainThread(() => {
            const pvp = quelle === "pvp";
            const nomClasse = pvp ? "PvpGameModeSource" : "CampaignGameModeSource";
            const src = pvp ? getPvpGameModeSourcePtr() : getCampaignGameModeSourcePtr();
            if (!src || src.isNull()) {
                return { ok: false, source: quelle,
                         error: `aucune \`${nomClasse}\` captée -- pour le PvP, `
                             + "`discoverSources` la trouve si le jeu en a une vivante" };
            }
            const kc = findClassAnywhere(NS_SRC, nomClasse);
            if (!kc) return { ok: false, source: quelle,
                              error: `\`${nomClasse}\` INTROUVABLE` };
            const mc = findMethodByParamCount(kc, METHODE, 0);
            if (!mc) return { ok: false, source: quelle,
                              error: `\`${nomClasse}$$${METHODE}\` INTROUVABLE (0 paramètre)` };
            const avant = firesDeployable;
            let boite: NativePointer;
            // Même fenêtre que la délégation, mais ICI elle est observable : c'est tout
            // l'intérêt du pré-emprunt.
            dansEmprunt = true;
            try { boite = invokeMethod(mc.info, src, null); }
            catch (e) {
                dansEmprunt = false;
                return { ok: false, error: "l'emprunt a levé : " + (e as Error).message };
            }
            dansEmprunt = false;
            if (boite.isNull()) return { ok: false, error: "l'emprunt a rendu NUL" };
            gcRoot.add(boite);
            const cBoite = classeDerriere(boite);
            let deboxe: NativePointer | null = null;
            let cDeboxe: { classe: string | null; erreur: string | null } =
                { classe: null, erreur: "non lu" };
            try {
                deboxe = boite.add(0x10).readPointer();
                cDeboxe = classeDerriere(deboxe);
            } catch (e) { cDeboxe = { classe: null, erreur: (e as Error).message }; }
            if (deboxe === null || deboxe.isNull()) {
                return { ok: false, error: "déboxage -> NUL : la valeur à +0x10 est vide, on ne "
                    + "substitue RIEN plutôt que de poser un pointeur douteux",
                         boite: boite.toString(), classeBoite: cBoite.classe };
            }
            gcRoot.add(deboxe);
            preEmprunt = deboxe;
            preEmpruntInfo = {
                // QUI a prêté. Sans ce champ, un roster impérial sur un montage PvP est
                // indiscernable d'un roster correct -- c'est exactement ce qui s'est produit.
                source: quelle, instance: src.toString(),
                boite: boite.toString(), classeBoite: cBoite.classe, erreurBoite: cBoite.erreur,
                deboxe: deboxe.toString(), classeDeboxee: cDeboxe.classe,
                erreurDeboxee: cDeboxe.erreur,
                // Le témoin que l'appel a VRAIMENT traversé `GetDeployableUnits`, et que le
                // masque a pu agir : sans lui, « ok » ne dirait rien.
                // ⚠ Ce témoin ne vaut QUE pour le prêteur campagne : la source PvP ne passe
                // pas par `GetDeployableUnits`, donc un delta nul y est NORMAL, pas un échec.
                deltaGetDeployableUnits: pvp ? null : firesDeployable - avant,
                masqueArme: sansFiltreArme && sansFiltreEcrit,
            };
            return { ok: true, ...preEmpruntInfo };
        });
    };

    ctx.rpc.deploymentPoolEmprunterUneFois = (body?: { confirmer?: boolean }):
        Promise<unknown> | unknown => {
        if (body?.confirmer !== true) {
            return { ok: false, error: "`confirmer: true` exigé : ce RPC INVOQUE une méthode "
                + "native sur la source campagne vivante. C'est une mesure, pas un lecteur." };
        }
        return queueOnMainThread(() => {
            const src = getCampaignGameModeSourcePtr();
            if (!src || src.isNull()) {
                return { ok: false, error: "aucune `CampaignGameModeSource` captée" };
            }
            const kc = findClassAnywhere(NS_SRC, "CampaignGameModeSource");
            if (!kc) return { ok: false, error: "`CampaignGameModeSource` INTROUVABLE" };
            const mc = findMethodByParamCount(kc, METHODE, 0);
            if (!mc) return { ok: false, error: `\`${METHODE}\` INTROUVABLE (0 paramètre)` };
            const avant = firesDeployable;
            let r: NativePointer | null = null;
            let erreur: string | null = null;
            // Cet emprunt-ci est HORS hook, donc l'ancrage le VOIT : c'est le seul endroit où
            // `sansFiltre` peut réellement agir. On ouvre donc la même fenêtre que la
            // délégation -- sans quoi le masque resterait inerte ici aussi.
            dansEmprunt = true;
            try { r = invokeMethod(mc.info, src, null); }
            catch (e) { erreur = (e as Error).message; }
            finally { dansEmprunt = false; }
            return {
                ok: erreur === null,
                erreur,
                retour: r === null || r.isNull() ? null : r.toString(),
                // LE chiffre : combien de fois `GetDeployableUnits` a été vu PENDANT cet appel.
                firesAvant: avant, firesApres: firesDeployable,
                delta: firesDeployable - avant,
                lecture: firesDeployable > avant
                    ? "(b) le corps S'EXÉCUTE -- c'est notre observation depuis un hook qui est "
                      + "aveugle aux appels imbriqués"
                    : "(a) le corps NE s'exécute PAS -- toutes nos substitutions sont des "
                      + "illusions, à re-mesurer avant d'en tirer quoi que ce soit",
            };
        });
    };

    /**
     * LÈVE LE FILTRE DE NŒUD sur le roster emprunté — deux régimes, observation par défaut.
     *
     *   { armer: true }                          -> OBSERVE `args[1]` sans rien écrire
     *   { armer: true, ecrire: true, confirmer: true } -> efface `hasValue`
     *
     * L'observation est le défaut parce qu'on ne sait pas d'avance si le `Nullable<Int32>`
     * arrive par VALEUR (registre) ou par POINTEUR : masquer un pointeur le corromprait, et
     * une faute native sur le thread principal fige le jeu. Lire d'abord coûte un aller-retour.
     */
    ctx.rpc.deploymentPoolSansFiltre = (body?: {
        armer?: boolean; ecrire?: boolean; confirmer?: boolean;
    }): unknown => {
        if (!body || body.armer === undefined) {
            return { ok: true, lecture: true, arme: sansFiltreArme, ecrit: sansFiltreEcrit, fires: firesDeployable,
                     observations: observationsNullable,
                     note: "`{ armer: true }` observe ; `{ armer: true, ecrire: true, "
                         + "confirmer: true }` écrit. Lire les observations AVANT d'écrire : "
                         + "un `Nullable<Int32>` par valeur donne `basse`=index et `haute`=1." };
        }
        if (body.armer === false) {
            sansFiltreArme = false; sansFiltreEcrit = false;
            return { ok: true, arme: false, action: "desarme" };
        }
        if (body.ecrire === true && body.confirmer !== true) {
            return { ok: false, error: "`confirmer: true` exigé pour ÉCRIRE : on modifie un "
                + "argument natif en vol. Observer d'abord (`{ armer: true }`)." };
        }
        const r = armerSansFiltre(body.ecrire === true);
        if (r !== true) return r;
        return { ok: true, arme: true, ecrit: sansFiltreEcrit,
                 observations: observationsNullable };
    };

    /**
     * LE PRÊTEUR, LU ET POSITIONNÉ — sans bataille, sans `StartMatch`, sans swap.
     *
     * Sans corps : LECTURE PURE. Avec `{ locationIndex, confirmer: true }` : écrit le seul
     * entier dont dépende le roster.
     *
     * ⚠ POURQUOI CET ENTIER SUFFIT, ET POURQUOI CE N'EST PAS LA MÊME CHOSE QUE POSITIONNER
     * UNE SOURCE. Le décompilé de `CampaignGameModeSource$$GetUnitsForDeploymentHUD` ne lit
     * QUE deux champs :
     *
     *     _campaignProgression.GetDeployableUnits(
     *         locationIndex: Nullable<Int32>(this->_currentLocationIndex),
     *         onlyUnlocked : false)
     *
     * Ni `_currentMatch`, ni `_currentCampaignId`, ni la progression de compte. La crainte
     * écrite plus haut (« un DTO déjà résolu deviendrait périmé ») vaut pour `LoadBattle`,
     * PAS pour le roster : il n'y a aucun DTO dans ce chemin. Et l'identité de la campagne
     * est portée par l'INSTANCE de `_campaignProgression` (`get_CampaignType` est son premier
     * slot d'interface), donc elle ne se règle pas ici.
     *
     * ⚠ `_currentLocationIndex` est restauré par personne : ce qu'on écrit reste écrit. On le
     * publie donc AVANT et APRÈS, pour que l'appelant puisse le remettre.
     */
    ctx.rpc.deploymentPoolPreteur = (body?: {
        locationIndex?: number; confirmer?: boolean; classe?: boolean;
    }): Promise<unknown> | unknown => queueOnMainThread(() => {
        const src = getCampaignGameModeSourcePtr();
        if (!src || src.isNull()) {
            return { ok: false, error: "aucune `CampaignGameModeSource` captée -- l'amorce ne "
                + "l'a pas posée, ou la session a été réinjectée depuis" };
        }
        const kSrc = findClassAnywhere("IdunBattle.ViewLogic.BattleSource",
                                       "CampaignGameModeSource");
        if (!kSrc) return { ok: false, error: "classe `CampaignGameModeSource` introuvable" };
        // PAR NOM, jamais par les +0x68/+0x70 mesurés : `getFieldOffset` rend -1 sur un nom
        // absent, et -1 est *truthy* -- tester `< 0`, jamais `||`.
        const offId = getFieldOffset(kSrc, "_currentCampaignId");
        const offIdx = getFieldOffset(kSrc, "_currentLocationIndex");
        const offProg = getFieldOffset(kSrc, "_campaignProgression");
        if (offId < 0 || offIdx < 0 || offProg < 0) {
            return { ok: false, error: "champ(s) absent(s) de `CampaignGameModeSource` sur ce "
                + `build : _currentCampaignId=${offId} _currentLocationIndex=${offIdx} `
                + `_campaignProgression=${offProg} -- chemin PÉRIMÉ, pas de repli sur un offset` };
        }

        const lire = (): Record<string, unknown> => {
            const idx = src.add(offIdx).readS32();
            // ⛔ ON NE DÉRÉFÉRENCE RIEN DE CE QUE CES CHAMPS CONTIENNENT. Deux gels du jeu
            // le 2026-08-17 (sessions 35 et 36, `Responding=False`, delta CPU nul,
            // `__loadingStep = 12`) : la première version lisait la CLASSE de
            // `_campaignProgression` et le CONTENU de `_currentCampaignId`. `isNull()` ne
            // protège que du zéro -- un pointeur STALE le passe, et `class_get_name` /
            // la lecture d'un `System.String` partent alors dans le vide, sur le thread
            // principal, où un `try/catch` JS n'attrape pas une faute native.
            //
            // Ce lecteur ne rend donc que des SCALAIRES et des ADRESSES, sans jamais suivre
            // un pointeur. C'est assez pour le diagnostic visé (`_currentLocationIndex`), et
            // c'est le seul régime qui ne puisse pas figer.
            const progBrut = src.add(offProg).readPointer();
            const idBrut = src.add(offId).readPointer();
            // ⛔ CE LECTEUR N'INVOQUE RIEN, ET C'EST UNE CICATRICE, PAS UN PRINCIPE.
            //
            // La première version appelait `CampaignProgression$$IsDeploymentUnlocked(idx)`
            // « pour avoir un tri-état » distinguant « mauvais index » de « index bon, roster
            // vide ». Mesuré le 2026-08-17 (session 35) : l'appel n'est JAMAIS revenu, et le
            // jeu a GELÉ -- `Responding=False`, delta CPU 0,03 s sur 8 s,
            // `thor.Loader.__loadingStep = 12`. Relance manuelle exigée.
            //
            // Le natif n'avait jamais été OBSERVÉ : on ne savait pas ce qu'il touche, s'il
            // charge quoi que ce soit, ni s'il est appelable hors de son contexte d'écran.
            // Une commodité de diagnostic ne justifie pas d'invoquer à l'aveugle sur le
            // thread principal. Si ce tri-état est voulu, il se prend par un `Interceptor`
            // sur l'appel que le JEU fait lui-même -- jamais en le provoquant.
            // ⚠ OPT-IN, ET C'EST UNE HISTOIRE D'ACCUSATION PUIS D'ACQUITTEMENT. Ce
            // déréférencement a été RETIRÉ le 2026-08-17 comme cause présumée de deux gels du
            // jeu. Il a ensuite été DISCULPÉ : un troisième gel, même signature
            // (`__loadingStep = 12`), s'est produit sur un inject NU, sans qu'aucun RPC ne soit
            // appelé -- les trois appartiennent au cycle inject (résidu #10021).
            // Il revient donc, mais sur demande explicite : suivre un pointeur de champ reste
            // le geste le plus risqué de ce module, et rien ne prouve qu'il soit TOUJOURS sain.
            let classeProgression: string | null = null;
            if (body?.classe === true && !progBrut.isNull()) {
                try {
                    classeProgression = s(class_get_name(progBrut.readPointer()) as NativePointer);
                } catch (e) { classeProgression = "ILLISIBLE : " + (e as Error).message; }
            }
            return {
                source: src.toString(), locationIndex: idx,
                campaignProgression: progBrut.isNull() ? null : progBrut.toString(),
                classeProgression,
                currentCampaignIdPtr: idBrut.isNull() ? null : idBrut.toString(),
                note: "SCALAIRES ET ADRESSES SEULEMENT -- aucun pointeur n'est suivi, aucun "
                    + "natif invoqué (deux gels du jeu le 2026-08-17). Le NOM de la campagne "
                    + "et la CLASSE de la progression exigeraient de déréférencer : les "
                    + "prendre en OBSERVANT un appel du jeu, jamais en le provoquant.",
            };
        };

        const avant = lire();
        if (body?.locationIndex === undefined) {
            return { ok: true, lecture: true, ...avant,
                     note: "passer { locationIndex, confirmer: true } pour positionner le "
                         + "prêteur. Rien d'autre n'est écrit, et rien ne le restaure." };
        }
        if (body.confirmer !== true) {
            return { ok: false, error: "`confirmer: true` exigé : on écrit dans une source "
                + "VIVANTE du jeu, et personne ne la restaure.", ...avant };
        }
        src.add(offIdx).writeS32(body.locationIndex | 0);
        return { ok: true, action: "positionne", avant, apres: lire() };
    });

    /**
     * LES DEUX BORNES DU HUD, MIRÉES LÀ OÙ ELLES SONT CALCULÉES.
     *
     * ⚠ LE HUD NE DEMANDE PAS SES BORNES À LA SOURCE — il les demande à `VisualBattleQuery`, qui
     * les CALCULE. Décompilé le 2026-08-23 :
     *
     *     IdunBattle.View.FSM.VisualBattleQuery$$MaxUnitsPossibleToStartBattle
     *         = idun.shared.SPMath$$Min( <slot 0x31 de la source>,
     *                                    GetSpawnPointCoordinatedForHumanPlayer(this).Count,
     *                                    <slot 0x33 de la source> )
     *     ...$$MinUnitsNeededToStartBattle : idem, avec <slot 0x32> en 3e terme.
     *
     * puis `idun.Ui.IdunGameHud$$UnitDeployment_ShowHud` passe les deux à
     * `idun.ui.UnitDeploymentHud$$Show(units, min, max, options)`.
     *
     * ⇒ DÉLÉGUER `Min|MaxUnitsPossibleToStartBattle` NE SUFFIT PAS, et c'est le piège : un `Min`
     * à trois termes est écrasé par le plus petit. Mesuré sur l'onslaught Chaos tier 18 — source
     * déléguée à 3 et 5, points d'apparition du joueur = 3 — le HUD affichait quand même `0/0`.
     * Le terme coupable est le PREMIER : `SandboxGameModeSource$$AmountOfUnlockedUnits` rend 0.
     *
     * ⚠ ET IL EST INANCRABLE. Son corps fait TROIS octets (`33 c0 c3` = `xor eax,eax ; ret`) :
     * Frida répond « unable to intercept function ». Ce n'est pas le partage par déduplication
     * qui bloque — c'est la TAILLE. On ne peut donc pas corriger le terme ; on mire la FORMULE.
     *
     * Ce qu'on fait ici : on rejoue `SPMath.Min` des trois MÊMES termes, en lisant les deux qui
     * viennent de la source sur le PRÊTEUR (la vraie source du mode) au lieu du stub. Le terme
     * des points d'apparition, lui, est relu du natif — on ne le devine pas.
     */
    ctx.rpc.deploymentBornesArmer = (body?: {
        armer?: boolean; confirmer?: boolean;
    }): Promise<unknown> | unknown => {
        const etat = () => ({
            arme: listenerBornes.length > 0,
            derniers: derniersBornes,
        });
        if (!body || body.armer === undefined) {
            return { ok: true, lecture: true, ...etat(),
                     note: "{ armer: true, confirmer: true } pour mirer `SPMath.Min` avec les "
                         + "termes du PRÊTEUR. `deploymentPoolArmer {source}` doit avoir été "
                         + "joué d'abord : c'est lui qui désigne la source à interroger." };
        }
        return queueOnMainThread(() => {
            if (body.armer === false) {
                for (const l of listenerBornes) l.detach();
                listenerBornes.length = 0;
                Interceptor.flush();
                return { ok: true, action: "retire", ...etat() };
            }
            if (body.confirmer !== true) {
                return refus("`confirmer: true` exigé : on SUBSTITUE le retour de deux méthodes "
                    + "de `VisualBattleQuery`, que TOUS les modes partagent.");
            }
            if (listenerBornes.length > 0) return { ok: true, action: "deja arme", ...etat() };

            const kQ = findClassAnywhere("IdunBattle.View.FSM", "VisualBattleQuery");
            if (!kQ) return refus("`IdunBattle.View.FSM.VisualBattleQuery` INTROUVABLE");
            const miSpawn = findMethodByParamCount(kQ, "GetSpawnPointCoordinatedForHumanPlayer", 0);
            if (!miSpawn) {
                return refus("`VisualBattleQuery$$GetSpawnPointCoordinatedForHumanPlayer(0)` "
                    + "INTROUVABLE -- sans ce terme on ne peut pas rejouer le `Min` sans le "
                    + "DEVINER, et on ne devine pas");
            }
            const rapport: Array<{ nom: string; ok: boolean; detail: string | null }> = [];
            for (const [nom, surSource] of [
                ["MinUnitsNeededToStartBattle", "MinUnitsNeededToStartBattle"],
                ["MaxUnitsPossibleToStartBattle", "MaxUnitsPossibleToStartBattle"],
            ] as Array<[string, string]>) {
                const mq = findMethodByParamCount(kQ, nom, 0);
                if (!mq) {
                    rapport.push({ nom, ok: false,
                                   detail: `\`VisualBattleQuery$$${nom}(0)\` INTROUVABLE` });
                    continue;
                }
                const t = lireTete(mq.ptr);
                if (t.erreur === null && teteTriviale(t)) {
                    rapport.push({ nom, ok: false,
                                   detail: `corps TRIVIAL (${t.hex}) -- adresse PARTAGÉE` });
                    continue;
                }
                listenerBornes.push(Interceptor.attach(mq.ptr, {
                    onEnter(args) {
                        (this as unknown as { q: NativePointer }).q = args[0];
                    },
                    onLeave(retval) {
                        const q = (this as unknown as { q: NativePointer }).q;
                        const natif = retval.toInt32();
                        const p = sourcePreteuse();
                        if (p.ptr === null || p.ptr.isNull()) {
                            derniersBornes[nom] = { natif, substitue: null,
                                detail: `aucune source \`${p.cls}\` (prêteur ${p.nom})` };
                            return;
                        }
                        try {
                            const klass = p.ptr.readPointer();
                            // ⚠ CHAQUE `Int32` revient BOXÉ : la valeur est à `+0x10`.
                            const entier = (m: string): number | null => {
                                const mi = findMethodByParamCount(klass, m, 0);
                                if (!mi) return null;
                                const b = invokeMethod(mi.info, p.ptr as NativePointer, []);
                                return b.isNull() ? null : b.add(0x10).readS32();
                            };
                            const debloquees = entier("AmountOfUnlockedUnits");
                            const borne = entier(surSource);
                            // Le terme des points d'apparition se RELIT du natif -- c'est une
                            // propriété du PLATEAU, pas de la source : l'emprunter serait faux.
                            const liste = invokeMethod(miSpawn.info, q, []);
                            const places = liste.isNull() ? null : liste.add(0x18).readS32();
                            if (debloquees === null || borne === null || places === null) {
                                derniersBornes[nom] = { natif, substitue: null,
                                    detail: `terme NON MESURÉ (debloquees=${debloquees} `
                                        + `borne=${borne} places=${places}) -- RIEN SUBSTITUÉ` };
                                return;
                            }
                            const v = Math.min(debloquees, places, borne);
                            if (v < 0 || v > 64) {
                                derniersBornes[nom] = { natif, substitue: null,
                                    detail: `résultat ${v} hors borne plausible -- RIEN SUBSTITUÉ` };
                                return;
                            }
                            retval.replace(ptr(v));
                            derniersBornes[nom] = { natif, substitue: v,
                                detail: `Min(debloquees=${debloquees}, places=${places}, `
                                    + `${surSource}=${borne}) = ${v}` };
                        } catch (e) {
                            derniersBornes[nom] = { natif, substitue: null,
                                detail: "a levé : " + (e as Error).message };
                        }
                    },
                }));
                rapport.push({ nom, ok: true, detail: null });
            }
            Interceptor.flush();
            const reussies = rapport.filter((x) => x.ok).length;
            if (reussies === 0) {
                return refus("AUCUNE borne ancrée -- "
                    + rapport.map((x) => `${x.nom} : ${x.detail}`).join(" | "));
            }
            return { ok: true, action: "arme", ancrees: reussies, rapport, ...etat() };
        });
    };

    /**
     * LA SANDBOX EN **WRAPPER** D'UNE VRAIE SOURCE — on ne patche plus stub par stub, on DÉLÈGUE.
     *
     *   { armer: true, confirmer: true }            -> délègue TOUTE la table
     *   { armer: true, confirmer: true, only: [...] } -> délègue seulement ces méthodes
     *   { armer: false }                            -> retire tout
     *
     * `confirmer` est exigé : chaque délégation SUBSTITUE un retour dès l'armement, il n'y a pas
     * de régime transparent (contrairement à la phase). L'observer d'abord n'apprendrait rien —
     * le décompilé dit déjà ce que la sandbox rend.
     *
     * ⚠ CE QUE CE WRAPPER EST, ET CE QU'IL N'EST PAS — mesuré, pas supposé.
     * `CampaignGameModeSource` ne STOCKE pas les règles d'un nœud : elle porte son IDENTITÉ
     * (`_currentCampaignId` `+0x68`, `_currentLocationIndex` `+0x70`) et RÉSOUT sa config
     * (`_currentMatch : CampaignConfigDto` `+0x78`). C'est un RÉSOLVEUR lié à une sélection
     * courante. Déléguer lui importe donc **les règles du nœud où elle pointe** — celui que le
     * amorce a ouvert — et **pas** des règles « génériques » ni celles d'un nœud choisi.
     * Dire « la sandbox devient fidèle » serait faux : elle IMPERSONNE UN NŒUD PARTICULIER.
     * Choisir ce nœud voudrait dire écrire `_currentCampaignId`/`_currentLocationIndex` et
     * re-résoudre `_currentMatch` — NON MESURÉ, et un DTO déjà résolu deviendrait périmé.
     */
    ctx.rpc.deploymentPoolArmer = (body?: {
        armer?: boolean; confirmer?: boolean; only?: string[]; source?: Preteur;
    }): Promise<unknown> | unknown => {
        if (!body || body.armer === undefined) {
            return { ok: true, lecture: true, ...etatPool(), preteur: preteurDelegation,
                     note: "{ armer: true, confirmer: true } pour déléguer ; `only` restreint la "
                         + "liste ; `source: \"guildBoss\"` emprunte à la source du MODE plutôt "
                         + "qu'à la campagne -- indispensable pour "
                         + "`GetGameModeSpecificDeploymentHudOptions`, qui porte "
                         + "`supportsMachinesOfWar` ET les restrictions du mode." };
        }
        // Le prêteur est fixé AVANT l'armement : `armerUneDelegation` résout la méthode sur SA
        // classe, donc en changer après coup laisserait des ancrages incohérents.
        if (body.source !== undefined) preteurDelegation = body.source;
        // Les rosters empruntés sont relus au prochain tir : un remontage change de source forgée,
        // et servir le cache d'une bataille précédente donnerait un roster PÉRIMÉ sans le dire.
        idsGuildWar = null;
        idsOnslaught = null;
        idsCampagne = null;
        idsMowEvent = null;
        idsPvp = null;
        return queueOnMainThread(() => {
            if (body.armer === false) {
                for (const d of delegations) {
                    if (d.listener) { d.listener.detach(); d.listener = null; }
                    // Le témoin de prêteur suit le listener : le garder après un désarmement
                    // ferait croire à un ré-armement inutile au prochain tour.
                    d.preteurArme = null; d.miCampagne = null; d.ancrage = null;
                }
                Interceptor.flush();
                return { ok: true, action: "retire", ...etatPool() };
            }
            if (body.confirmer !== true) {
                return refus("`confirmer: true` exigé : chaque délégation SUBSTITUE le retour dès "
                    + "l'armement. Et le wrapper fait répondre la sandbox comme LE NŒUD DE CAMPAGNE "
                    + "où pointe la source capturée -- pas comme une source générique.");
            }
            // ⚠ LA GARDE PORTE SUR LE PRÊTEUR RETENU, PAS SUR LA CAMPAGNE. Elle testait
            // `getCampaignGameModeSourcePtr()` quel que soit `source` — un reste de l'époque où
            // la campagne était le seul prêteur. Mesuré le 2026-08-19 : un montage guild boss
            // ENTIÈREMENT gréé (source forgée, BC de la source, override posé) était refusé au
            // motif « rejouer l'amorce », alors qu'`armerUneDelegation` résout sur
            // `sourcePreteuse()` et n'aurait pas lu la campagne une seule fois. Une garde qui
            // accuse une dépendance dont le chemin ne se sert pas fait réparer la mauvaise cause.
            const p = sourcePreteuse();
            if (p.ptr === null || p.ptr.isNull()) {
                return refus(`aucune source \`${p.cls}\` (prêteur ${p.nom}) -- on ne délègue PAS `
                    + "à rien. Campagne : l'amorce ne l'a pas prise (session froide, ou la "
                    + "navigation auto est éteinte) ; guild boss : `guildBossSourceForger "
                    + "{confirmer:true}` n'a pas été appelé ; guild war : "
                    + "`guildWarSourceForger` n'a pas été appelé ; onslaught : "
                    + "`onslaughtSourceForger {alliance, tier, confirmer:true}` n'a pas été "
                    + "appelé.");
            }
            if (body.only !== undefined) {
                const connus = DELEGUEES.map((x) => x.nom);
                const inconnus = body.only.filter((n) => !connus.includes(n));
                if (inconnus.length) {
                    return refus(`méthode(s) hors table : ${inconnus.join(", ")}. Table = `
                        + connus.join(", "));
                }
            }
            const rapport: Array<{ nom: string; ok: boolean; detail: string | null }> = [];
            for (let i = 0; i < delegations.length; i++) {
                const spec = DELEGUEES[i];
                if (body.only && !body.only.includes(spec.nom)) continue;
                const r = armerUneDelegation(delegations[i], spec);
                rapport.push(r === true
                    ? { nom: spec.nom, ok: true, detail: null }
                    : { nom: spec.nom, ok: false, detail: r.error });
            }
            Interceptor.flush();
            // ⚠ UN ARMEMENT QUI N'ARME RIEN N'EST PAS UN SUCCÈS. Ce retour valait `ok: true,
            // action: "arme"` quel que soit le contenu de `rapport` : le détail par méthode y
            // était bien écrit, mais un appelant qui ne le lit pas -- et il n'y a aucune raison
            // de le lire quand `ok` est vrai -- monte sa bataille en croyant l'écran gréé.
            // Mesuré le 2026-08-23 : 4 délégations sur 4 en échec (mauvais namespace du prêteur),
            // `ok: true` rendu, et c'est l'ÉCRAN VIDE qui a fini par le démentir -- après un
            // montage, un armement de relais et un patch d'environnement posés pour rien.
            const reussies = rapport.filter((x) => x.ok).length;
            if (rapport.length > 0 && reussies === 0) {
                return refus(`AUCUNE délégation armée (${rapport.length} tentée(s), prêteur `
                    + `\`${p.nom}\`) -- l'écran resterait VIDE. Détail : `
                    + rapport.map((x) => `${x.nom} : ${x.detail}`).join(" | "));
            }
            return { ok: true, action: "arme", armees: reussies, tentees: rapport.length,
                     rapport, ...etatPool() };
        });
    };
}
