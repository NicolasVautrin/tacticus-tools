// deployment-draft — RENDRE L'ÉCRAN DE DÉPLOIEMENT NATIF UTILISABLE SUR UNE BATAILLE SANDBOX.
//
// LE FAIT MESURÉ (build `t6dpr4k06g`, décompilé) — LE SANDBOX STUBBE SON ROSTER
// -----------------------------------------------------------------------------
// Les deux corps, côte à côte :
//
//   `IdunBattle.ViewLogic.BattleSource.CampaignGameModeSource$$GetUnitsForDeploymentHUD`
//       lit la progression (`this+0x20`), construit un `Nullable` depuis `this+0x70`, appelle
//       le slot d'interface `0x15` pour obtenir une liste poolée d'unités, la MAPPE, la rend.
//
//   `IdunBattle.ViewLogic.BattleSource.SandboxGameModeSource$$GetUnitsForDeploymentHUD`
//       rend un conteneur poolé FRAÎCHEMENT LOUÉ, **sans lire un seul champ de `this`**.
//
// ⇒ L'écran de déploiement s'afficherait, VIDE. Ce n'est pas un défaut de notre montage : la
// source sandbox déclare le contrat et ne fournit rien. C'est le seul étage qui manque.
//
// CE QUI N'EST **PAS** UN BLOQUEUR, et il fallait le vérifier
// ------------------------------------------------------------
// `idun.Idun.Source.IdunBattle.View.Hud.UnitDeployment.UnitDeploymentHudGameModeFactory$$Create`
// ne dispatche PAS sur un enum de mode de jeu : il teste la NON-NULLITÉ de champs successifs de
// l'objet d'options (`+0x50`, `+0x30`, `+0x68`, `+0x60`, `+0x20`, `+0x28`, `+0x58`, `+0x48`,
// `+0x40`) et retombe, tous nuls, sur `UnitDeploymentHudGameModeDefault`. Or
// `SandboxGameModeSource$$GetGameModeSpecificDeploymentHudOptions` construit un
// `idun.ui.GameModeSpecificUnitDeploymentHudOptions` par défaut (il n'écrit que `+0x86 = 0`) —
// tous les champs discriminants restent nuls. **Le sandbox tombe donc sur le HUD générique, et
// il n'y a aucune branche manquante à ajouter.**
//
// LE CONTRAT, ET POURQUOI ON OBSERVE AVANT DE REMPLIR
// ----------------------------------------------------
// La méthode rend `idun.shared.collections.pools.PooledList<System.String>` — une liste d'IDS
// d'unités. Mais `classes.tsv` dit `PooledList\`1  parent=System.ValueType  isValueType=1` :
// c'est un **TYPE VALEUR**, donc le retour est une STRUCT, pas une référence. Sa disposition
// n'est pas lisible statiquement (générique ouvert, taille 0 dans la table).
//
// On ne PARIE donc pas dessus. Le module a deux régimes, et le second refuse tant que le premier
// n'a pas parlé :
//
//   OBSERVER  (défaut)  -- `onLeave` LIT le retour et rapporte ce qu'il voit (valeur brute, et le
//                          nom de classe trouvé derrière si ça pointe sur un objet géré). Écrit
//                          RIEN. C'est « un natif qui écrit s'observe d'abord », appliqué.
//   REMPLIR             -- ajoute nos ids à la liste RENDUE PAR LE STUB. On ne construit aucun
//                          conteneur : celui du stub est déjà du bon type et correctement loué —
//                          il est juste vide. La méthode `Add` est résolue AU RUNTIME sur la
//                          classe RÉELLEMENT observée, jamais sur un offset écrit ici.
//
// TROIS GARDES, toutes tirées de fautes déjà payées dans ce dépôt
// ---------------------------------------------------------------
//   * `Interceptor.attach` + écriture dans le retour, JAMAIS `Interceptor.replace` : un stop de
//     session avec un `replace` actif crashe le jeu (cf. `Ne jamais` du CLAUDE.md).
//   * on n'invoque JAMAIS `GetUnitsForDeploymentHUD` nous-mêmes — ancrer ce qu'on invoque gèle
//     le jeu, et ça a déjà coûté un gel ici (cf. `sandboxModeBcOverride`).
//   * le régime REMPLIR exige `confirmer: true` ET une observation préalable réussie.

import {
    class_get_fields, class_get_name, class_instance_size, field_get_name, field_get_offset,
    field_get_type, findClassAnywhere, findMethodByParamCount, getFieldOffset, il2cppBase, s,
    type_get_class_or_element_class,
} from "../il2cpp/helpers.js";
import { createManagedString, il2cpp_object_new, invokeMethod } from "../il2cpp/invoke.js";
// ⚠ VOIE FROIDE, ET C'EST DÉLIBÉRÉ. La vue vivante s'obtient par `FindObjectsByType`, À LA
// DEMANDE. La version précédente la publiait depuis le pump (`IdunGameViews$$Update`), donc une
// écriture JS PAR FRAME dans le hot path le plus sensible du dépôt : un coût permanent payé par
// toutes les batailles pour un besoin qui n'existe que le temps d'un RPC.
import { premiereInstance } from "./view-command.js";
// Une valeur pré-empruntée doit SURVIVRE jusqu'à sa substitution : sans racine, le GC IL2CPP
// peut la ramasser entre l'emprunt et le `retval.replace`.
import { gcRoot } from "../il2cpp/gc-root.js";
// ⚠ `s()` convertit un `char*` NATIF. Un `System.String` MANAGÉ a sa propre disposition, et
// `readIl2cppString` est le lecteur du dépôt. Mesuré : `stringAt` rendait `null` sur les
// arguments de `TryMarkUnitAsPlaced` — le verdict était bon, le NOM manquait, et un capteur
// qui rend `null` sur ce qu'il est censé identifier ne sert qu'à moitié.
import { readIl2cppString } from "../il2cpp/helpers.js";
import { queueOnMainThread } from "../runtime/queue.js";
import { getCampaignGameModeSourcePtr } from "./campaign-builder.js";
import { Ctx } from "../controller.js";

const NS_SRC = "IdunBattle.ViewLogic.BattleSource";
const METHODE = "GetUnitsForDeploymentHUD";

interface Refus { ok: false; error: string }
function refus(error: string): Refus { return { ok: false, error }; }

/** Ce que `onLeave` a VU au dernier passage — la seule base sur laquelle REMPLIR est autorisé. */
interface Observation {
    brut: string;            // le retour, en hexa
    pointeur: boolean;       // ressemble-t-il à un pointeur exploitable ?
    classe: string | null;   // nom de classe lu derrière, si lisible
    erreur: string | null;   // ce qui a empêché de lire (jamais un silence)
}

let listener: InvocationListener | null = null;
let observations: Observation[] = [];
let fires = 0;

/** Les ids à injecter. `null` = TRANSPARENT (le hook observe et ne touche à rien). */
let unites: string[] | null = null;
let dernierRemplissage: { ajoutes: number; erreur: string | null } | null = null;

/** Lit prudemment le nom de classe derrière un pointeur candidat. Ne lève jamais. */
function classeDerriere(p: NativePointer): { classe: string | null; erreur: string | null } {
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
function remplir(retour: NativePointer): {
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
    for (const id of unites ?? []) {
        try {
            invokeMethod(miAdd.info, cible, [createManagedString(id)]);
            n++;
        } catch (e) {
            return { ajoutes: n, voie, erreur: `\`Add("${id}")\` a levé : ` + (e as Error).message };
        }
    }
    return { ajoutes: n, erreur: null, voie };
}

function armer(): true | Refus {
    if (listener) return true;
    const k = findClassAnywhere(NS_SRC, "SandboxGameModeSource");
    if (!k) return refus(`${NS_SRC}.SandboxGameModeSource INTROUVABLE sur ce build`);
    const mi = findMethodByParamCount(k, METHODE, 0);
    if (!mi) return refus(`\`SandboxGameModeSource$$${METHODE}\` INTROUVABLE (0 param)`);
    listener = Interceptor.attach(mi.ptr, {
        onLeave(retval) {
            fires++;
            const p = retval as unknown as NativePointer;
            const { classe, erreur } = classeDerriere(p);
            if (observations.length < 8) {
                observations.push({ brut: p.toString(), pointeur: !p.isNull(), classe, erreur });
            }
            // TRANSPARENT tant qu'aucun id n'est posé : le régime par défaut n'écrit RIEN.
            if (unites && unites.length) dernierRemplissage = remplir(p);
        },
    });
    Interceptor.flush();
    return true;
}

// ============================================================================
// PHASE DE DÉPLOIEMENT (#10020-r1) — forcer une sandbox à passer par l'écran de
// déploiement au lieu de sauter directement en `Running`.
//
// LA CHAÎNE, mesurée le 2026-08-17 (`t6dpr4k06g`), décompilée puis confrontée sur les objets
// VIVANTS (cf. `docs/rl/case-10020-lien-vue-source-sens-unique.md` §7-§8) :
//
//   IdunBattle.View.Game.IdunGameViews$$Enable(this, skipUnitDeployment)
//       si skipUnitDeployment == 0 ET <slot 0x34>(this+0x138 = _visualBattleQuery) :
//              -> IdunBattle.View.FSM.UnitSelectionFsm$$UnitDeployment       (PHASE DE DEPLOIEMENT)
//       sinon  -> IdunBattle.View.FSM.UnitSelectionFsm$$StartMatch           (direct en jeu)
//
//   IdunBattle.View.FSM.VisualBattleQuery$$ShouldShowUnitDeploymentHud  =  relais PUR vers
//       <slot 0x29>(this+0x80 = _gameModeSource : IGameModeSource)
//
// Sur une sandbox les DEUX rendent `false` (invoqués sur les objets vivants), et le corps de
// `SandboxGameModeSource$$ShouldShowUnitDeployment` est un `return 0` **CONSTANT** : aucun réglage
// de BC ni de gameconfig ne le fera basculer. D'où ce hook.
//
// ⛔ POURQUOI ON N'ANCRE PAS LA SOURCE, ET POURQUOI C'EST LE POINT CENTRAL DE CE MODULE
// -------------------------------------------------------------------------------------
// `SandboxGameModeSource$$ShouldShowUnitDeployment` résout au runtime sur un corps que **~745
// `MethodInfo` PARTAGENT** (745 xrefs DATA + 122 appels directs ; Ghidra le nomme d'après une
// classe sans rapport, `Stash.Native.StashNative$$get_IsPurchaseProcessing`). IL2CPP déduplique les
// corps triviaux : `return 0` n'a pas d'identité. S'y attacher basculerait à `true` TOUT ce qui rend
// « faux constant » dans le jeu — sans erreur, sans symptôme qui désigne la cause.
//
// Le dépôt portait déjà « l'absence dans la table ne prouve RIEN » : c'était le versant LECTURE.
// Ici c'est le versant ÉCRITURE, et il ne rate pas une conclusion — il fait un dégât.
//
// ⇒ On ancre le RELAIS, un étage au-dessus : il a un VRAI corps, donc une adresse propre
// (2 xrefs DATA : son `MethodInfo` + son entrée de vtable).
//
// ET LE GARDE EST EXÉCUTABLE, PAS ÉCRIT — une prose n'arrête pas un comportement. `teteTriviale()`
// lit les premiers octets du corps résolu et REFUSE l'attache si un `ret` (0xC3) tombe dans les 8
// premiers : un corps qui rend une constante rette en 1 à 4 octets, un relais réel commence par sa
// garde de cctor et son test de nullité. Le refus PUBLIE les octets, pour qu'on juge sur pièce et
// pas sur un verdict.
//
// RÉGIMES — `forcer` est FAUX par défaut, donc armer n'écrit RIEN.
//   OBSERVER : on lit le `skipUnitDeployment` que le jeu passe à `Enable`, et ce que le relais rend.
//              C'est la seule base sur laquelle on saura si forcer a un sens.
//   FORCER   : `onLeave` remplace le retour du relais par `true`. `Interceptor.attach`, JAMAIS
//              `replace` (un stop de session avec un `replace` actif crashe le jeu).
//
// ⚠ `VisualBattleQuery` sert TOUS les modes, pas seulement la sandbox : forcer sans désarmer ferait
// apparaître une phase de déploiement là où le jeu n'en veut pas. D'où l'armement explicite.

const NS_VBQ = "IdunBattle.View.FSM";
const CLS_VBQ = "VisualBattleQuery";
const METH_VBQ = "ShouldShowUnitDeploymentHud";
const NS_VIEWS = "IdunBattle.View.Game";
const CLS_VIEWS = "IdunGameViews";

/** Octets lus en tête de corps pour le garde de trivialité. */
const OCTETS_TETE = 8;

interface Tete {
    hex: string | null;
    /** Index du premier `ret` (0xC3) dans la tête, ou `null` s'il n'y en a pas. */
    retA: number | null;
    erreur: string | null;
}

/** Lit la tête du corps. Ne lève jamais — un refus de lecture est un refus, pas un silence. */
function lireTete(p: NativePointer): Tete {
    try {
        const buf = p.readByteArray(OCTETS_TETE);
        if (!buf) return { hex: null, retA: null, erreur: "lecture vide" };
        const o = new Uint8Array(buf);
        let retA: number | null = null;
        for (let i = 0; i < o.length; i++) {
            if (o[i] === 0xc3) { retA = i; break; }
        }
        const hex = Array.from(o).map((b) => b.toString(16).padStart(2, "0")).join(" ");
        return { hex, retA, erreur: null };
    } catch (e) {
        return { hex: null, retA: null, erreur: "lecture refusée : " + (e as Error).message };
    }
}

/** Le corps ressemble-t-il à une constante dédupliquée ? Voir l'en-tête. */
function teteTriviale(t: Tete): boolean {
    return t.retA !== null;
}

let relaisListener: InvocationListener | null = null;
let enableListener: InvocationListener | null = null;

/** `false` = OBSERVER (aucune écriture). `true` = le relais rendra `true`. */
let forcerPhase = false;

let relaisFires = 0;
let relaisForces = 0;
/** Ce que le relais a rendu AVANT toute substitution — la mesure, pas notre effet. */
const relaisRetours: number[] = [];
/** Le `skipUnitDeployment` que le jeu passe à `Enable`, tel quel. */
const enableObservations: Array<{ skip: number }> = [];

/** Ce que l'armement a établi sur les deux corps — publié, jamais résumé en booléen. */
let ancrage: {
    relais: { ghidraVA: string; tete: Tete } | null;
    enable: { ghidraVA: string; tete: Tete } | null;
} = { relais: null, enable: null };

function ghidraVA(p: NativePointer): string {
    return ptr("0x180000000").add(p.sub(il2cppBase)).toString();
}

function armerPhase(): true | Refus {
    if (relaisListener) return true;

    const kv = findClassAnywhere(NS_VBQ, CLS_VBQ);
    if (!kv) return refus(`${NS_VBQ}.${CLS_VBQ} INTROUVABLE sur ce build`);
    const mv = findMethodByParamCount(kv, METH_VBQ, 0);
    if (!mv) return refus(`\`${CLS_VBQ}$$${METH_VBQ}\` INTROUVABLE (0 param)`);

    // LE GARDE. Il vaut pour le relais comme pour n'importe quelle cible future : si le corps
    // résolu rend une constante, il est probablement PARTAGÉ, et s'y attacher est un dégât de
    // masse. On refuse en publiant les octets.
    const teteV = lireTete(mv.ptr);
    if (teteV.erreur !== null) {
        return refus(`tête du corps de \`${METH_VBQ}\` ILLISIBLE (${teteV.erreur}) -- `
            + "on ne s'attache pas à un corps qu'on n'a pas pu qualifier");
    }
    if (teteTriviale(teteV)) {
        return refus(`REFUS : \`${CLS_VBQ}$$${METH_VBQ}\` résout sur un corps TRIVIAL `
            + `(ret à l'octet ${teteV.retA} ; tête = ${teteV.hex}). IL2CPP déduplique ces corps, `
            + "donc l'adresse est PARTAGÉE par N méthodes et s'y attacher les basculerait TOUTES. "
            + "Ancrer un appelant qui a un vrai corps. Cf. case-10020 §8.");
    }

    const kg = findClassAnywhere(NS_VIEWS, CLS_VIEWS);
    const mg = kg ? findMethodByParamCount(kg, "Enable", 1) : null;
    const teteG = mg ? lireTete(mg.ptr) : null;

    relaisListener = Interceptor.attach(mv.ptr, {
        onLeave(retval) {
            relaisFires++;
            // Le retour est un Boolean IL2CPP : la valeur utile est dans AL, d'où le masque.
            const brut = retval.toInt32() & 0xff;
            if (relaisRetours.length < 32) relaisRetours.push(brut);
            if (forcerPhase && brut === 0) {
                retval.replace(ptr(1));
                relaisForces++;
            }
        },
    });

    // `Enable` reste en OBSERVATION PURE, toujours : c'est lui qui dit si le drapeau
    // `skipUnitDeployment` court-circuite le prédicat, auquel cas forcer le relais ne servirait
    // à rien. Sans cette lecture, un forçage sans effet serait indiscernable d'un forçage raté.
    if (mg && teteG && teteG.erreur === null && !teteTriviale(teteG)) {
        enableListener = Interceptor.attach(mg.ptr, {
            onEnter(args) {
                if (enableObservations.length < 32) {
                    enableObservations.push({ skip: args[1].toInt32() & 0xff });
                }
            },
        });
    }

    Interceptor.flush();
    ancrage = {
        relais: { ghidraVA: ghidraVA(mv.ptr), tete: teteV },
        enable: mg && teteG ? { ghidraVA: ghidraVA(mg.ptr), tete: teteG } : null,
    };
    return true;
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
// ⇒ On EMPRUNTE le résultat à la source CAMPAGNE VIVANTE, capturée par le warmup
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

const CLS_CAMP = "CampaignGameModeSource";
const CLS_SANDBOX = "SandboxGameModeSource";

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
const DELEGUEES: Array<{ nom: string; params: number; role: string }> = [
    { nom: "GetUnitModel", params: 2,
      role: "commande la POSE -- sandbox rend un `HotseatUnitModel`, qui échoue à `IsUnlocked`" },
    { nom: "GetGameModeSpecificDeploymentHudOptions", params: 0,
      role: "apporte les RESTRICTIONS -- sandbox rend des options par défaut, donc AUCUNE règle" },
    { nom: "GetUnitsForDeploymentHUD", params: 0,
      role: "apporte le ROSTER réel -- sandbox rend une liste vide" },
    { nom: "GetUnlockedUnitsPooled", params: 0,
      role: "dictionnaire des débloqués -- MESURÉ jamais appelé sur ce chemin (cf. §13)" },
];

interface Delegation {
    nom: string; role: string;
    listener: InvocationListener | null;
    miCampagne: { ptr: NativePointer; info: NativePointer } | null;
    ancrage: { sandbox: string; campagne: string; tete: Tete } | null;
    fires: number; emprunts: number;
    /** Dernier incident RÉEL — jamais avalé, jamais résumé en booléen. */
    dernier: { ok: boolean; detail: string } | null;
}

const delegations: Delegation[] = DELEGUEES.map((d) => ({
    nom: d.nom, role: d.role, listener: null, miCampagne: null, ancrage: null,
    fires: 0, emprunts: 0, dernier: null,
}));

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
let sansFiltreArme = false;
let sansFiltreEcrit = false;
let dansEmprunt = false;
let listenerDeployable: InvocationListener | null = null;
// ⚠ COMPTER TOUS LES PASSAGES, PAS SEULEMENT CEUX DE LA FENÊTRE. Un compteur conditionné par
// `dansEmprunt` ne sait pas distinguer « la méthode n'est jamais appelée » (donc la classe
// ancrée est la mauvaise) de « elle est appelée hors fenêtre » (donc c'est ma fenêtre qui est
// fausse). Les deux rendent zéro observation, et ce zéro-là ne désigne rien.
let firesDeployable = 0;
// La valeur PRÉ-EMPRUNTÉE, déjà déboxée, prête à être substituée par la délégation.
let preEmprunt: NativePointer | null = null;
let preEmpruntInfo: Record<string, unknown> | null = null;
const observationsNullable: Array<{
    brut: string; basse: string; haute: string; dansEmprunt: boolean; ecrit: boolean;
}> = [];

function armerSansFiltre(ecrire: boolean): true | Refus {
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
const NS_HUD = "idun.ui";
const CLS_HUD = "UnitDeploymentHud";
let listenerShow: InvocationListener | null = null;
let listenerPose: InvocationListener | null = null;
let listenerBoard: InvocationListener | null = null;
let hudEtat: Record<string, unknown> | null = null;
const hudPoses: Array<{ unitId: string | null; mow: boolean; accepte: boolean }> = [];
// ⚠ L'ÉTAGE QUI POSE VRAIMENT. `TryMarkUnitAsPlaced` n'est que la comptabilité du roster —
// mesuré : il rend `true` (l'unité se grise) alors que le plateau ne bouge pas.
// `StateMachineActions$$UnitDeployment_PlaceUnitOnBoard` interroge le HUD puis délègue à un
// SECOND étage ; c'est celui-là qu'il faut voir.
const hudBoard: Array<{
    unitId: string | null; col: number; row: number; manuel: boolean; playerId: number;
    retour: number;
}> = [];

/** Compte d'un `Dictionary<K,V>` : `_count - _freeCount`, les deux résolus PAR NOM. */
function compteDict(dico: NativePointer): number | string {
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

function armerHud(): true | Refus {
    if (listenerShow && listenerPose) return true;
    const k = findClassAnywhere(NS_HUD, CLS_HUD);
    if (!k) return refus(`\`${NS_HUD}.${CLS_HUD}\` INTROUVABLE sur ce build`);
    const miShow = findMethodByParamCount(k, "Show", 4);
    const miPose = findMethodByParamCount(k, "TryMarkUnitAsPlaced", 2);
    if (!miShow) return refus("`UnitDeploymentHud$$Show` INTROUVABLE (4 paramètres)");
    if (!miPose) {
        return refus("`UnitDeploymentHud$$TryMarkUnitAsPlaced` INTROUVABLE (2 paramètres)");
    }
    for (const [nom, mi] of [["Show", miShow], ["TryMarkUnitAsPlaced", miPose]] as const) {
        const t = lireTete(mi.ptr);
        if (t.erreur !== null) return refus(`tête de \`${nom}\` ILLISIBLE (${t.erreur})`);
        if (teteTriviale(t)) {
            return refus(`REFUS : \`${CLS_HUD}$$${nom}\` résout sur un corps TRIVIAL `
                + `(ret à l'octet ${t.retA}) -- adresse probablement PARTAGÉE. Cf. §8.`);
        }
    }
    const offTous = getFieldOffset(k, "_allUnitModels");
    const offDebl = getFieldOffset(k, "_allUnlockedUnitModels");
    const offInput = getFieldOffset(k, "_disabledInput");
    if (offTous < 0 || offDebl < 0) {
        return refus("champ(s) absent(s) de `UnitDeploymentHud` sur ce build : "
            + `_allUnitModels=${offTous} _allUnlockedUnitModels=${offDebl} `
            + "-- chemin PÉRIMÉ, pas de repli sur un offset");
    }
    if (!listenerShow) {
        listenerShow = Interceptor.attach(miShow.ptr, {
            onEnter(args) {
                // `Show` remplit les dictionnaires : on lit APRÈS, pas avant.
                (this as unknown as { hud: NativePointer; mn: number; mx: number }).hud = args[0];
                (this as unknown as { mn: number }).mn = args[2].toInt32();
                (this as unknown as { mx: number }).mx = args[3].toInt32();
            },
            onLeave() {
                const self = this as unknown as { hud: NativePointer; mn: number; mx: number };
                try {
                    hudEtat = {
                        hud: self.hud.toString(),
                        minUnitsPossible: self.mn, maxUnitsPossible: self.mx,
                        allUnitModels: compteDict(self.hud.add(offTous).readPointer()),
                        allUnlockedUnitModels: compteDict(self.hud.add(offDebl).readPointer()),
                        disabledInput: offInput < 0
                            ? null : self.hud.add(offInput).readU8() !== 0,
                    };
                } catch (e) { hudEtat = { erreur: (e as Error).message }; }
            },
        });
    }
    if (!listenerPose) {
        listenerPose = Interceptor.attach(miPose.ptr, {
            onEnter(args) {
                const self = this as unknown as { uid: string | null; mow: boolean };
                self.uid = null;
                try { self.uid = readIl2cppString(args[1]); } catch { /* best effort */ }
                self.mow = args[2].toInt32() !== 0;
            },
            onLeave(retval) {
                const self = this as unknown as { uid: string | null; mow: boolean };
                if (hudPoses.length < 32) {
                    hudPoses.push({ unitId: self.uid, mow: self.mow,
                                    accepte: (retval.toInt32() & 0xff) !== 0 });
                }
            },
        });
    }
    if (!listenerBoard) {
        const ka = findClassAnywhere("IdunBattle.View.FSM", "StateMachineActions");
        if (!ka) return refus("`IdunBattle.View.FSM.StateMachineActions` INTROUVABLE");
        const mb = findMethodByParamCount(ka, "UnitDeployment_PlaceUnitOnBoard", 5);
        if (!mb) {
            return refus("`StateMachineActions$$UnitDeployment_PlaceUnitOnBoard` INTROUVABLE "
                + "(5 paramètres)");
        }
        const tb = lireTete(mb.ptr);
        if (tb.erreur !== null) return refus(`tête de \`PlaceUnitOnBoard\` ILLISIBLE`);
        if (teteTriviale(tb)) {
            return refus("REFUS : `UnitDeployment_PlaceUnitOnBoard` résout sur un corps "
                + `TRIVIAL (ret à l'octet ${tb.retA}) -- adresse PARTAGÉE. Cf. §8.`);
        }
        listenerBoard = Interceptor.attach(mb.ptr, {
            onEnter(args) {
                const self = this as unknown as {
                    uid: string | null; c: number; r: number; m: boolean; p: number;
                };
                self.uid = null;
                try { self.uid = readIl2cppString(args[1]); } catch { /* best effort */ }
                self.c = args[2].toInt32();
                self.r = args[3].toInt32();
                self.m = (args[4].toInt32() & 0xff) !== 0;
                self.p = args[5].toInt32();
            },
            onLeave(retval) {
                const self = this as unknown as {
                    uid: string | null; c: number; r: number; m: boolean; p: number;
                };
                if (hudBoard.length < 32) {
                    hudBoard.push({ unitId: self.uid, col: self.c, row: self.r,
                                    manuel: self.m, playerId: self.p,
                                    retour: retval.toInt32() & 0xff });
                }
            },
        });
    }
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
interface Borne {
    methode: string;
    listener: InvocationListener | null;
    impose: number | null;
    fires: number;
    obs: Array<{ rendu: number; impose: number | null }>;
}
const BORNES: Record<"max" | "min", Borne> = {
    max: { methode: "MaxUnitsPossibleToStartBattle",
           listener: null, impose: null, fires: 0, obs: [] },
    min: { methode: "MinUnitsNeededToStartBattle",
           listener: null, impose: null, fires: 0, obs: [] },
};

function armerBorne(b: Borne): true | Refus {
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
function armerUneDelegation(d: Delegation, spec: { nom: string; params: number }): true | Refus {
    if (d.listener) return true;

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
    if (teteTriviale(tete)) {
        return refus(`REFUS : \`${CLS_SANDBOX}$$${spec.nom}\` résout sur un corps TRIVIAL `
            + `(ret à l'octet ${tete.retA} ; tête = ${tete.hex}) -- adresse probablement PARTAGÉE `
            + "par déduplication IL2CPP. Cf. case-10020 §8.");
    }

    const kc = findClassAnywhere(NS_SRC, CLS_CAMP);
    if (!kc) return refus(`${NS_SRC}.${CLS_CAMP} INTROUVABLE`);
    const mc = findMethodByParamCount(kc, spec.nom, spec.params);
    if (!mc) {
        return refus(`\`${CLS_CAMP}$$${spec.nom}\` INTROUVABLE (${spec.params} param) -- la vraie `
            + "source ne porte pas cette méthode, donc il n'y a rien à quoi déléguer");
    }
    d.miCampagne = mc;

    const nParams = spec.params;
    d.listener = Interceptor.attach(ms.ptr, {
        // Les arguments sont capturés à l'ENTRÉE : au `onLeave` ils ne sont plus lisibles.
        // `args[0]` est le `this` sandbox — on ne le transmet PAS, c'est tout l'objet de la
        // délégation : la vraie source répond avec SON état.
        onEnter(args) {
            (this as unknown as { argv: NativePointer[] }).argv =
                nParams >= 1 ? [args[1], args[2]].slice(0, nParams) : [];
        },
        onLeave(retval) {
            d.fires++;
            const src = getCampaignGameModeSourcePtr();
            if (src === null || src.isNull()) {
                d.dernier = { ok: false, detail: "aucune CampaignGameModeSource capturée -- le "
                    + "warmup ne l'a pas prise, ou la session est froide. RIEN SUBSTITUÉ." };
                return;
            }
            // PRÉ-EMPRUNT : la valeur a été calculée HORS de tout hook, donc l'ancrage sur
            // `GetDeployableUnits` a pu la voir — et le masque `sansFiltre` a pu agir. Ici on
            // ne fait plus que la poser. C'est la seule forme qui permette de modifier
            // l'appel emprunté (cf. §24 : un `Interceptor` est aveugle aux appels imbriqués).
            if (preEmprunt !== null && spec.nom === METHODE) {
                retval.replace(preEmprunt);
                d.emprunts++;
                d.dernier = { ok: true, detail: `PRÉ-EMPRUNT substitué -> ${preEmprunt}` };
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

// ============================================================================
// L'ÉTAGE PREFAB — ET LE CHARGEMENT « À LA DEMANDE » EXISTE DÉJÀ DANS LE JEU.
//
// Symptôme : on sélectionne une unité du roster, elle se GRISE (`TryMarkUnitAsPlaced` rend
// `true`), et le plateau ne bouge pas. `IdunGameViews$$AddPlaceholderUnit` sort en `false` sur
// `UnitIdToPrefabDictionary$$Get` -> `NullableRefExtensions$$TryGet` -> `false`.
//
// CE QUE `Get` FAIT VRAIMENT, et c'est le fait qui commande tout ce bloc :
//
//     ref = dico[GetUnitIdForUniverse(unitId)]      // AssetBundleBattleReference
//     si ref.prefab == null :                       // <-- LE CHARGEMENT PARESSEUX
//         ref.prefab = ref.loader.Invoke()          //     EST DÉJÀ LÀ, dans le jeu
//     return NullableRefUnity(ref.prefab)
//
// ⇒ Il n'y a donc RIEN à charger : il y a une ENTRÉE à créer. Le prefab sera tiré par le jeu
// lui-même, au premier `Get`, exactement là où il le tire pour les unités de `bc.Units`. On
// ne déclenche aucun chargement de bundle depuis un thread Frida — ce qui écarte au passage
// le profil de gel qu'on redoutait.
//
// POURQUOI L'ENTRÉE MANQUE. `UnitIdToPrefabDictionary$$Add` n'a qu'UN SEUL appelant :
// `idun.IdunMainView$$StartBattle`, qui itère `BattleConfiguration.Units`. Notre roster est
// EMPRUNTÉ à la campagne et n'est dans aucune BC — il ne pouvait donc pas avoir de prefab.
//
// LA SÉQUENCE NATIVE, mirroir 1:1 de `StartBattle` :
//
//     holder = new <classe porteuse>()                    // { visualConfig, effectPool }
//     holder.effectPool = thor.Game.Board.EffectPool$$GetInstance()
//     IdunUniverse$$TryGetUnitVisualConfig(univers, visualId, &holder.visualConfig)
//     del = new WidgetPoolReuseHelper.CreateWidget<T>(holder, <méthode du holder>)
//     ref = new AssetBundleBattleReference(del)
//     dico.Add(unitId, ref)
//
// ⚠ AUCUNE de ces classes n'est nommée ici, et c'est le cœur du dispositif. Ghidra ne les
// nomme pas non plus : le ctor d'`AssetBundleBattleReference` s'y appelle
// `UnityEngine.EventSystems.BaseEventData$$.ctor` (corps DÉDUPLIQUÉ — son absence de
// `methods.tsv` ne prouvait rien, cf. le CLAUDE.md), et la classe porteuse n'est qu'un `DAT_`.
// On CAPTURE donc un exemplaire VIVANT : `sandboxModeStart` fait tourner `StartBattle`, donc
// `Add` tire pour chaque unité de la BC. Le patron ainsi capturé porte les trois classes, le
// `m_target` du délégué et l'`EffectPool` — sans une seule adresse en dur, et re-capturé à
// chaque montage, donc insensible au changement de build.
//
// ⚠ ON CLONE, ON NE RECONSTRUIT PAS. Copier l'instance capturée puis n'écraser que le champ
// qui change préserve tout ce que le runtime a calculé (l'`invoke_impl` et le `method_code` du
// délégué, notamment) et évite d'invoquer trois ctors dont un prend un `IntPtr`. Le seul piège
// est en face : le `ref` capturé a SON prefab déjà résolu, donc le clone doit REMETTRE CE SLOT
// À NUL — sans quoi chaque unité ajoutée afficherait le modèle de l'unité capturée, et ça se
// verrait comme un bug de jeu, pas comme un bug de patron.
//
// ⚠ Les slots sont résolus PAR LE TYPE du champ (même doctrine que `bucket-decode`), jamais par
// un offset écrit ici, et le diagnostic PUBLIE le nom réellement trouvé pour que la péremption
// se voie.

const NS_PREFAB = "IdunBattle.View.Game";
const CLS_DICO = "UnitIdToPrefabDictionary";
const CLS_VIEWS_PREFAB = "IdunGameViews";

interface Champ { nom: string; off: number; type: string }

/** Champs d'instance d'une classe, avec le NOM DE TYPE — la clé de la résolution par type. */
function champsDe(klass: NativePointer): Champ[] {
    const out: Champ[] = [];
    const it = Memory.alloc(Process.pointerSize);
    it.writePointer(ptr(0));
    let f: NativePointer;
    while (!(f = class_get_fields(klass, it) as NativePointer).isNull()) {
        let type = "?";
        try {
            const t = field_get_type(f) as NativePointer;
            const k = type_get_class_or_element_class(t) as NativePointer;
            if (!k.isNull()) type = s(class_get_name(k) as NativePointer);
        } catch { /* type illisible : le champ reste listé, avec `?` */ }
        try {
            out.push({ nom: s(field_get_name(f) as NativePointer),
                       off: field_get_offset(f) as number, type });
        } catch { /* champ illisible : on continue plutôt que de tout perdre */ }
    }
    return out;
}

/** Le premier champ dont le type porte `type`. Rend `-1` si absent — jamais un offset deviné. */
function offsetParType(champs: Champ[], type: string): number {
    const c = champs.find((x) => x.type === type);
    return c ? c.off : -1;
}

/** Ce qu'un `Add` VIVANT nous a appris. Tout est capturé, rien n'est écrit en dur. */
interface Patron {
    dico: string;
    refClasse: NativePointer; refClasseNom: string;
    offPrefab: number; nomPrefab: string;
    offLoader: number; nomLoader: string;
    delClasse: NativePointer; delClasseNom: string;
    offTarget: number;
    /** ⚠ LE SLOT QUE `Get` LIT VRAIMENT. Le décompilé invoque le loader par
     *  `invoke_impl(delegue->method_code, &retour, delegue->method)` — donc `method_code`,
     *  PAS `m_target`. Ne réécrire que `m_target` laisse le délégué cloné pointer sur la
     *  fermeture DU PATRON : mesuré, deux unités distinctes se sont affichées avec le modèle du
     *  patron, sans la moindre erreur. Les deux champs sont donc écrits, et relus. */
    offMethodCode: number;
    holderClasse: NativePointer; holderClasseNom: string;
    offConfig: number; nomConfig: string;
    /** TOUS les champs du porteur. Publiés : c'est en choisissant le champ « par élimination »
     *  qu'on a écrit la config dans le mauvais slot, et que deux unités distinctes se sont
     *  affichées avec le modèle du patron. Le slot se choisit désormais par le TYPE RÉEL de la
     *  config, à l'écriture — pas par une devinette à la capture. */
    champsHolder: Champ[];
    /** Le corps que le délégué appelle : c'est LUI qui fabrique le prefab. Lu sur le délégué
     *  capturé (`method_ptr`, champ NOMMÉ de `System.Delegate`), donc jamais une adresse écrite. */
    loaderPtr: NativePointer | null;
    /** ⚠ CE QUE `Delegate..ctor` ATTEND, et ce n'est PAS `method_ptr`. En IL2CPP, `ldftn` rend un
     *  `MethodInfo*` déguisé en `IntPtr` : le second argument du ctor est donc le champ `method`
     *  (+0x28), pas le pointeur de code (+0x10). Lui passer le code construit un délégué dont
     *  l'invocateur part sur une sentinelle — mesuré : « access violation accessing
     *  0xffffffffffffffff ». */
    loaderMethodInfo: NativePointer | null;
    tailleRef: number; tailleDel: number; tailleHolder: number;
    exemplaireRef: NativePointer; exemplaireDel: NativePointer; exemplaireHolder: NativePointer;
    unitIdVu: string | null;
}

let patron: Patron | null = null;
let patronRefus: string | null = null;
let listenerAdd: InvocationListener | null = null;
let addFires = 0;
const prefabCharges: Array<{ unitId: string; ok: boolean; detail: string }> = [];

// ⚠ LES POINTEURS QUE LE JEU UTILISE VRAIMENT — la seule autorité.
//
// Mesuré session 52 : `HasPrefabForUnitId` rend `true` pour `spaceBlackmane` alors que le `Get`
// du jeu rend NUL pour la même unité. Or les deux corps font le MÊME `ContainsKey`, sur le MÊME
// champ, avec la MÊME clé — sur une seule et même instance ils ne PEUVENT pas diverger. Donc ils
// portent sur DEUX objets différents, et c'est ma lecture qui visait le mauvais.
//
// La cause est la voie d'accès : aller CHERCHER la vue (`FindObjectsByType`, ou le dernier `this`
// vu par le pump) rend *une* vue, pas *celle que le déploiement utilise*. On enregistre donc les
// pointeurs tels qu'ils passent dans les appels du jeu, et tout le reste s'y adosse.
const dicosVusParAdd = new Map<string, number>();
/** Les unitIds que `Add` a inscrits — donc ceux dont le prefab EXISTE, sans rien fabriquer. */
const idsAvecPrefab: string[] = [];
let dicoDeGet: NativePointer | null = null;     // le `this` du dernier `Get` -- l'AUTORITÉ
let vuesDePose: NativePointer | null = null;    // le `this` d'`Enable` / `AddPlaceholderUnit`
let listenerVue: InvocationListener | null = null;
/** Ce qu'a donné chaque tentative de capture de la vue. Publié — jamais avalé. */
const captureVue: string[] = [];

/**
 * Le dictionnaire ET la vue que LE JEU utilise pour le déploiement.
 *
 * ⚠ ORDRE DE PRÉFÉRENCE, et il n'est pas cosmétique : on prend d'abord ce qu'on a VU PASSER dans
 * les appels du jeu (`Get`, `AddPlaceholderUnit`), puis seulement à défaut une vue qu'on va
 * chercher. C'est exactement l'erreur qui a produit la contradiction `HasPrefabForUnitId=true` /
 * `Get=NUL` : une vue trouvée n'est pas la vue employée. La SOURCE est publiée à chaque appel,
 * pour qu'un résultat obtenu par le repli ne se lise jamais comme un résultat autoritaire.
 */
function dicoVivant(): { dico: NativePointer; vues: NativePointer; source: string } | Refus {
    const kv = findClassAnywhere(NS_PREFAB, CLS_VIEWS_PREFAB);
    if (!kv) return refus(`\`${NS_PREFAB}.${CLS_VIEWS_PREFAB}\` INTROUVABLE`);
    const off = offsetParType(champsDe(kv), CLS_DICO);
    if (off < 0) {
        return refus(`aucun champ de type \`${CLS_DICO}\` sur \`${CLS_VIEWS_PREFAB}\` -- `
            + "chemin PÉRIMÉ, pas de repli sur un offset");
    }
    // (1) L'AUTORITÉ : la vue sur laquelle le jeu vient d'appeler `AddPlaceholderUnit`.
    if (vuesDePose !== null && !vuesDePose.isNull()) {
        const dico = vuesDePose.add(off).readPointer();
        if (!dico.isNull()) {
            return { dico, vues: vuesDePose, source: "vue OBSERVÉE dans `AddPlaceholderUnit`" };
        }
    }
    // (2) Le dictionnaire vu dans `Get` : autoritaire lui aussi, mais il ne donne pas la vue,
    // donc il ne suffit pas pour `GetUnitVisualConfig`.
    if (dicoDeGet !== null && !dicoDeGet.isNull() && vuesDePose === null) {
        return refus("le dictionnaire du jeu est connu (" + dicoDeGet
            + ") mais AUCUNE vue n'a encore été observée : `GetUnitVisualConfig` a besoin de la "
            + "vue. Tenter une pose d'abord (elle échouera, et elle publiera la vue).");
    }
    // (3) Repli : une vue qu'on va chercher. Peut viser à côté -- on le DIT.
    const trouve = premiereInstance(kv);
    if (!(trouve instanceof NativePointer)) return refus(trouve.error + " (repli)");
    if (trouve.isNull()) return refus("`FindObjectsByType` a rendu un pointeur NUL (repli)");
    const dico = trouve.add(off).readPointer();
    if (dico.isNull()) return refus("le champ dictionnaire est NUL sur la vue trouvée (repli)");
    return { dico, vues: trouve,
             source: "REPLI `FindObjectsByType` -- PAS forcément la vue du déploiement" };
}

/** Arme la CAPTURE du patron sur `Add`. Observation pure : n'écrit rien, ne remplace rien. */
function armerPrefab(): true | Refus {
    if (listenerAdd) return true;
    const kd = findClassAnywhere(NS_PREFAB, CLS_DICO);
    if (!kd) return refus(`\`${NS_PREFAB}.${CLS_DICO}\` INTROUVABLE sur ce build`);
    const mi = findMethodByParamCount(kd, "Add", 2);
    if (!mi) return refus(`\`${CLS_DICO}$$Add\` INTROUVABLE (2 paramètres)`);
    const t = lireTete(mi.ptr);
    if (t.erreur !== null) return refus(`tête de \`Add\` ILLISIBLE (${t.erreur})`);
    if (teteTriviale(t)) {
        return refus(`REFUS : \`${CLS_DICO}$$Add\` résout sur un corps TRIVIAL `
            + `(ret à l'octet ${t.retA}) -- adresse PARTAGÉE par déduplication. Cf. §8.`);
    }
    // La VUE, captée au montage plutôt qu'à la première pose. Le `this` de ces méthodes EST la
    // vue employée — donc autoritaire, au même titre que celui d'`AddPlaceholderUnit`, mais
    // disponible sans attendre un clic de l'utilisateur.
    //
    // ⚠ DEUX candidates, et le RÉSULTAT DE CHACUNE EST PUBLIÉ. La version précédente n'en tentait
    // qu'une et AVALAIT l'échec : le hook n'a pas tiré, `vuesDePose` est resté nul, et il a fallu
    // un aller-retour avec l'utilisateur pour découvrir que le capteur n'était pas armé. Un
    // capteur qui échoue en silence coûte plus cher que pas de capteur du tout.
    const kv = findClassAnywhere(NS_PREFAB, CLS_VIEWS_PREFAB);
    if (!listenerVue && kv) {
        for (const [nom, np] of [["Enable", 1], ["Continue", 0], ["Clear", 0]] as const) {
            const mv = findMethodByParamCount(kv, nom, np);
            if (!mv) { captureVue.push(`${nom}(${np}) : INTROUVABLE`); continue; }
            const tv = lireTete(mv.ptr);
            if (tv.erreur !== null) { captureVue.push(`${nom} : tête ILLISIBLE`); continue; }
            if (teteTriviale(tv)) { captureVue.push(`${nom} : corps TRIVIAL, refusé`); continue; }
            listenerVue = Interceptor.attach(mv.ptr, {
                onEnter(args) { if (vuesDePose === null) vuesDePose = args[0]; },
            });
            captureVue.push(`${nom} : ARMÉ`);
            break;
        }
    }
    listenerAdd = Interceptor.attach(mi.ptr, {
        onEnter(args) {
            addFires++;
            // QUEL dictionnaire a été rempli, et combien de fois chacun. C'est ce comptage qui
            // distingue « 68 prefabs chargés » de « 68 prefabs chargés AILLEURS ».
            const cle = args[0].toString();
            dicosVusParAdd.set(cle, (dicosVusParAdd.get(cle) ?? 0) + 1);
            // LES IDS QUI ONT UN PREFAB, par construction : ce sont ceux que le jeu vient de
            // charger. C'est la bonne source pour le roster -- inutile d'en fabriquer d'autres.
            try {
                const nom = readIl2cppString(args[1]);
                if (nom !== null && nom !== "" && idsAvecPrefab.indexOf(nom) < 0) {
                    idsAvecPrefab.push(nom);
                }
            } catch { /* best effort */ }
            if (patron !== null) return;          // un seul patron suffit
            try { patronRefus = capturerPatron(args[0], args[1], args[2]); }
            catch (e) { patronRefus = "capture levée : " + (e as Error).message; }
        },
    });
    Interceptor.flush();
    return true;
}

/**
 * Booléen rendu par `invokeMethod`. **À N'OUBLIER SOUS AUCUN PRÉTEXTE.**
 *
 * `il2cpp_runtime_invoke` BOXE les retours de type valeur : le pointeur rendu désigne une boîte
 * managée, et le `Boolean` vit à `+0x10`. Lire `retour.toInt32()` lit les 32 bits BAS DU
 * POINTEUR — quasi jamais nuls — donc rend **`true` inconditionnellement**.
 *
 * Ce n'est pas une précaution théorique : c'est exactement la faute qui a fait répondre
 * `HasPrefabForUnitId = true` sur des unités ABSENTES du dictionnaire, réfuter à tort la bonne
 * cause, et faire dire à `deploymentPrefabCharger` « déjà présent -- rien fait » alors qu'il
 * n'avait rien créé. Un capteur qui ne peut rendre que `true` ne mesure rien.
 */
function boolBoxe(p: NativePointer): boolean {
    if (p.isNull()) return false;
    return p.add(0x10).readU8() !== 0;
}

/** Taille d'instance. `il2cpp_class_instance_size` peut manquer de l'export : on LÈVE avec le
 *  nom plutôt que de cloner sur une taille devinée — un clone tronqué laisserait des champs à
 *  zéro sans la moindre erreur. */
function taille(klass: NativePointer): number {
    if (class_instance_size === null) {
        throw new Error("`il2cpp_class_instance_size` absent de ce build : clonage IMPOSSIBLE");
    }
    return class_instance_size(klass) as number;
}

/** Décortique un `Add` réel. Rend `null` si le patron est complet, sinon la RAISON du refus. */
function capturerPatron(dico: NativePointer, unitId: NativePointer,
                        ref: NativePointer): string | null {
    if (ref.isNull()) return "la référence passée à `Add` est NULLE";
    const kRef = ref.readPointer();
    const nomRef = s(class_get_name(kRef) as NativePointer);
    const champsRef = champsDe(kRef);
    // Le prefab est le champ `GameObject` ; le loader est le SEUL autre champ référence.
    const offPrefab = offsetParType(champsRef, "GameObject");
    if (offPrefab < 0) {
        return `aucun champ de type \`GameObject\` sur \`${nomRef}\` -- champs vus : `
            + champsRef.map((c) => `${c.nom}:${c.type}`).join(", ");
    }
    const cLoader = champsRef.find((c) => c.off !== offPrefab && c.type !== "?");
    if (!cLoader) return `aucun champ loader identifiable sur \`${nomRef}\``;
    const del = ref.add(cLoader.off).readPointer();
    if (del.isNull()) return "le champ loader est NUL sur l'exemplaire capturé";
    const kDel = del.readPointer();
    const nomDel = s(class_get_name(kDel) as NativePointer);
    // `m_target` est un champ NOMMÉ de `System.Delegate` : on le résout par son nom, pas par
    // la disposition supposée d'`Il2CppDelegate`.
    const offTarget = getFieldOffset(kDel, "m_target");
    if (offTarget < 0) return `\`m_target\` absent de \`${nomDel}\``;
    const holder = del.add(offTarget).readPointer();
    if (holder.isNull()) return "le `m_target` du délégué capturé est NUL";
    const kHolder = holder.readPointer();
    const nomHolder = s(class_get_name(kHolder) as NativePointer);
    const champsHolder = champsDe(kHolder);
    // La config visuelle est ce que `TryGetUnitVisualConfig` écrit ; on la repère par le champ
    // dont le type n'est PAS le pool d'effets.
    const cConfig = champsHolder.find((c) => c.type.indexOf("EffectPool") < 0 && c.type !== "?");
    if (!cConfig) {
        return `aucun champ de config visuelle sur \`${nomHolder}\` -- champs vus : `
            + champsHolder.map((c) => `${c.nom}:${c.type}`).join(", ");
    }
    patron = {
        dico: dico.toString(),
        refClasse: kRef, refClasseNom: nomRef,
        offPrefab, nomPrefab: champsRef.find((c) => c.off === offPrefab)?.nom ?? "?",
        offLoader: cLoader.off, nomLoader: cLoader.nom,
        delClasse: kDel, delClasseNom: nomDel, offTarget,
        offMethodCode: getFieldOffset(kDel, "method_code"),
        holderClasse: kHolder, holderClasseNom: nomHolder,
        offConfig: cConfig.off, nomConfig: cConfig.nom, champsHolder,
        loaderPtr: (() => {
            const o = getFieldOffset(kDel, "method_ptr");
            if (o < 0) return null;
            const p = del.add(o).readPointer();
            return p.isNull() ? null : p;
        })(),
        loaderMethodInfo: (() => {
            const o = getFieldOffset(kDel, "method");
            if (o < 0) return null;
            const p = del.add(o).readPointer();
            return p.isNull() ? null : p;
        })(),
        tailleRef: taille(kRef), tailleDel: taille(kDel), tailleHolder: taille(kHolder),
        exemplaireRef: ref, exemplaireDel: del, exemplaireHolder: holder,
        unitIdVu: (() => { try { return readIl2cppString(unitId); } catch { return null; } })(),
    };
    // Le patron sert de gabarit BIEN APRÈS le `Add` qui l'a fourni : sans racine, le GC peut
    // ramasser les trois exemplaires entre la capture et la première fabrication.
    gcRoot.add(ref); gcRoot.add(del); gcRoot.add(holder);
    return null;
}

/** Clone une instance managée : même classe, mêmes octets, en-tête neuf. */
function cloner(source: NativePointer, klass: NativePointer, taille: number): NativePointer {
    const copie = il2cpp_object_new(klass) as NativePointer;
    if (copie.isNull()) throw new Error("`il2cpp_object_new` a rendu NUL");
    // L'en-tête (klass + monitor, 2 pointeurs) vient de l'allocation ; on ne copie QUE le corps.
    const debut = Process.pointerSize * 2;
    Memory.copy(copie.add(debut), source.add(debut), Math.max(0, taille - debut));
    return copie;
}

/**
 * Les ids du roster, lus dans la liste PRÉ-EMPRUNTÉE à la campagne.
 *
 * ⚠ POURQUOI C'EST NÉCESSAIRE, ET PAS UN CONFORT. Charger « les unités qu'on croit utiles »
 * fait porter à l'utilisateur la traduction portrait -> identifiant : il a cliqué
 * `admecMarshall` en pensant désigner un héros de la liste que j'avais chargée, et l'essai n'a
 * rien mesuré du tout. Un écran est utilisable quand TOUT ce qu'il montre est posable.
 *
 * La liste est un `PooledListElement\`1` : on descend dans `_object` (le `List\`1` réel), puis on
 * lit `_size` et `_items` PAR LEUR NOM. Aucun offset écrit ici.
 */
function listeDuRoster(): string[] | Refus {
    if (preEmprunt === null || preEmprunt.isNull()) {
        return refus("aucun pré-emprunt en main -- jouer `deploymentPoolPreEmprunt` d'abord");
    }
    try {
        const kWrap = preEmprunt.readPointer();
        let liste = preEmprunt;
        const offObj = getFieldOffset(kWrap, "_object");
        if (offObj > 0) {
            const interne = preEmprunt.add(offObj).readPointer();
            if (interne.isNull()) return refus("`_object` du wrapper de pool est NUL");
            liste = interne;
        }
        const kListe = liste.readPointer();
        const offItems = getFieldOffset(kListe, "_items");
        const offSize = getFieldOffset(kListe, "_size");
        if (offItems < 0 || offSize < 0) {
            return refus(`\`_items\`/\`_size\` absents de \`${s(class_get_name(kListe) as
                NativePointer)}\` -- chemin PÉRIMÉ`);
        }
        const n = liste.add(offSize).readS32();
        const items = liste.add(offItems).readPointer();
        if (items.isNull()) return refus("`_items` est NUL");
        if (n < 0 || n > 4096) return refus(`taille invraisemblable (${n}) -- on ne lit RIEN`);
        const out: string[] = [];
        // ⚠ LES ÉLÉMENTS NE SONT PAS FORCÉMENT DES CHAÎNES. `GetUnitsForDeploymentHUD` MAPPE la
        // liste : ses éléments sont des MODÈLES d'unité. `readIl2cppString` dessus ne rend rien,
        // et la première version rendait donc une liste VIDE -- que l'appelant a rapportée comme
        // « `tout` non demandé ». Un vide silencieux vaut pire qu'une erreur.
        let classeElement: string | null = null;
        let offId = -1;
        for (let i = 0; i < n; i++) {
            // Tableau managé : longueur à +0x18, premier élément à +0x20.
            const el = items.add(0x20 + i * Process.pointerSize).readPointer();
            if (el.isNull()) continue;
            const ke = el.readPointer();
            if (classeElement === null) {
                classeElement = s(class_get_name(ke) as NativePointer);
                if (classeElement !== "String") {
                    // L'id se trouve sur le modèle : champ String nommé, résolu PAR SON NOM.
                    for (const nom of ["unitId", "UnitId", "id", "Id",
                                       "<UnitId>k__BackingField", "<unitId>k__BackingField"]) {
                        const o = getFieldOffset(ke, nom);
                        if (o >= 0) { offId = o; break; }
                    }
                    if (offId < 0) {
                        return refus(`les éléments sont des \`${classeElement}\`, et aucun champ `
                            + "d'id n'y est reconnu -- champs : "
                            + champsDe(ke).map((c) => `${c.nom}:${c.type}`).join(", "));
                    }
                }
            }
            const v = classeElement === "String"
                ? readIl2cppString(el)
                : readIl2cppString(el.add(offId).readPointer());
            if (v !== null && v !== "") out.push(v);
        }
        if (out.length === 0) {
            return refus(`liste lue (taille ${n}, éléments \`${classeElement ?? "?"}\`) mais AUCUN `
                + "id extrait -- on refuse plutôt que de rendre un vide qui se lirait comme "
                + "« rien à charger »");
        }
        return out;
    } catch (e) { return refus("lecture du roster levée : " + (e as Error).message); }
}

/**
 * Fabrique l'entrée manquante d'UNE unité, sur le patron capturé. Rend le détail — jamais un
 * booléen nu : chaque refus doit se lire.
 *
 * ⚠ N'appelle AUCUN chargement d'asset. Elle pose un triplet PARESSEUX (`_prefab` à nul) ;
 * c'est le corps natif de `Get` qui invoquera le loader ensuite, exactement comme il le fait
 * pour les unités de la BC. Le coût reste donc proportionnel à ce qui est RÉELLEMENT posé.
 */
function fabriquerEntree(
    p: Patron, dico: NativePointer, vues: NativePointer, id: string,
    mHas: MethodRefLike, mAdd: MethodRefLike, mCfg: MethodRefLike,
): { ok: boolean; detail: string; ref?: NativePointer } {
    try {
        const sid = createManagedString(id);
        // `Add` LÈVE sur clé dupliquée : on ne tente que ce qui manque vraiment.
        if (boolBoxe(invokeMethod(mHas.info, dico, [sid]))) {
            return { ok: true, detail: "déjà présent -- rien fait" };
        }
        // Lecture pure (`UnitConfigMap.TryGetValue`), aucun asset touché.
        const cfg = invokeMethod(mCfg.info, vues, [sid]);
        if (cfg.isNull()) {
            return { ok: false, detail: "`GetUnitVisualConfig` rend NUL -- pas de config visuelle "
                + "dans l'univers chargé ; on n'invente rien" };
        }
        // LE SLOT SE CHOISIT PAR LE TYPE RÉEL DE `cfg`, pas par élimination. Mesuré : le choix
        // « le premier champ qui n'est pas l'EffectPool » visait un autre membre de la fermeture,
        // la config du patron restait en place, et DEUX unités s'affichaient avec SON modèle.
        const nomCfg = s(class_get_name(cfg.readPointer()) as NativePointer);
        const cible = p.champsHolder.find((c) => c.type === nomCfg);
        if (!cible) {
            return { ok: false, detail: `aucun champ de type \`${nomCfg}\` sur `
                + `\`${p.holderClasseNom}\` -- champs : `
                + p.champsHolder.map((c) => `${c.nom}:${c.type}`).join(", ")
                + " ; on n'écrit RIEN plutôt qu'à côté" };
        }
        if (p.loaderMethodInfo === null) {
            return { ok: false, detail: "`method` (le `MethodInfo*`) du délégué capturé "
                + "ILLISIBLE -- on ne construit pas de délégué sans lui" };
        }
        const ctorDel = findMethodByParamCount(p.delClasse, ".ctor", 2);
        if (!ctorDel) {
            return { ok: false, detail: `\`${p.delClasseNom}..ctor\` (2 paramètres) INTROUVABLE` };
        }
        const holder = cloner(p.exemplaireHolder, p.holderClasse, p.tailleHolder);
        holder.add(cible.off).writePointer(cfg);
        // RELECTURE : une écriture non vérifiée est ce qui a produit deux modèles identiques
        // sans la moindre erreur.
        if (!holder.add(cible.off).readPointer().equals(cfg)) {
            return { ok: false, detail: `écriture NON CONFIRMÉE dans \`${cible.nom}\`` };
        }
        // ⚠ ON CONSTRUIT LE DÉLÉGUÉ, ON NE LE CLONE PAS — et les deux tentatives précédentes
        // établissent pourquoi. `method_code` (+0x40), que `Get` passe à l'invocateur, n'est pas
        // la CIBLE mais un pointeur de CODE, vers un trampoline où la cible est déjà scellée :
        //   * ne réécrire que `m_target` -> pas de crash, mais le trampoline appelle toujours la
        //     fermeture du PATRON (mesuré : deux unités affichées avec SON modèle) ;
        //   * écrire le porteur dans `method_code` -> l'invocateur saute sur des données
        //     (mesuré : « access violation accessing 0x... » levée par `Get`).
        // Un délégué ne se re-cible donc pas par écriture de champ. `StartBattle` l'instancie par
        // `.ctor(cible, pointeur_de_méthode)` — on fait pareil, et le runtime bâtit le trampoline.
        const del = il2cpp_object_new(p.delClasse) as NativePointer;
        if (del.isNull()) return { ok: false, detail: "`il2cpp_object_new` (délégué) a rendu NUL" };
        // Un `IntPtr` est un TYPE VALEUR : `runtime_invoke` en attend l'ADRESSE, pas la valeur.
        const boiteFn = Memory.alloc(Process.pointerSize);
        boiteFn.writePointer(p.loaderMethodInfo);
        invokeMethod(ctorDel.info, del, [holder, boiteFn]);
        const cibleRelue = del.add(p.offTarget).readPointer();
        if (!cibleRelue.equals(holder)) {
            return { ok: false, detail: `délégué construit mais \`m_target\` vaut ${cibleRelue} `
                + `au lieu de ${holder} -- on n'inscrit RIEN` };
        }
        const ref = cloner(p.exemplaireRef, p.refClasse, p.tailleRef);
        // ⚠ LE SLOT QUI DOIT REPARTIR À NUL : le patron a son prefab déjà résolu ; le laisser
        // afficherait le modèle de l'unité capturée.
        ref.add(p.offPrefab).writePointer(ptr(0));
        ref.add(p.offLoader).writePointer(del);
        gcRoot.add(holder); gcRoot.add(del); gcRoot.add(ref);
        invokeMethod(mAdd.info, dico, [sid, ref]);
        return { ok: true, ref, detail: `entrée créée -- config ${nomCfg} @ \`${cible.nom}\`` };
    } catch (e) { return { ok: false, detail: "LEVÉ : " + (e as Error).message }; }
}

/** Ce dont `fabriquerEntree` a besoin d'une méthode : son `MethodInfo*`. */
interface MethodRefLike { info: NativePointer }

function etatPrefab(): Record<string, unknown> {
    return {
        arme: listenerAdd !== null,
        addFires,
        patron: patron === null ? null : {
            reference: patron.refClasseNom,
            champPrefab: `${patron.nomPrefab}@+0x${patron.offPrefab.toString(16)}`,
            champLoader: `${patron.nomLoader}@+0x${patron.offLoader.toString(16)}`,
            delegue: patron.delClasseNom,
            porteur: patron.holderClasseNom,
            champConfig: `${patron.nomConfig}@+0x${patron.offConfig.toString(16)}`,
            champsDuPorteur: patron.champsHolder.map((c) => `${c.nom}:${c.type}`),
            unitIdVu: patron.unitIdVu,
        },
        // LE COMPTAGE QUI TRANCHE : si `Add` a rempli un dictionnaire et que `Get` en lit un
        // AUTRE, « N prefabs chargés » ne dit rien sur ce que le déploiement voit.
        dicosRemplisParAdd: Array.from(dicosVusParAdd, ([p, n]) => ({ dico: p, adds: n })),
        dicoLuParGet: dicoDeGet === null ? null : dicoDeGet.toString(),
        idsAvecPrefab,
        vueDePose: vuesDePose === null ? null : vuesDePose.toString(),
        captureVue,
        dicoDuPatron: patron === null ? null : patron.dico,
        // TRI-ÉTAT : `null` = aucun refus ENREGISTRÉ, ce qui n'est pas « tout va bien » tant
        // qu'`addFires` vaut 0.
        refusDeCapture: patronRefus,
        charges: prefabCharges.slice(-24),
    };
}

// ============================================================================
// POURQUOI LA POSE ÉCHOUE — ET LA PREMIÈRE CAUSE ÉCRITE ICI ÉTAIT FAUSSE.
//
// Mesuré sur la session 50, sur les DEUX unités réellement refusées
// (`spaceBlackmane`, `admecRuststalker`) : `HasPrefabForUnitId` rend **true** pour chacune.
// Le montage `useAccountUnits` charge **68** prefabs (compté sur `Add`, hook armé APRÈS le
// warmup, donc tous les fires viennent de NOTRE montage). ⇒ **La cause « prefab manquant »
// est RÉFUTÉE** ; elle avait été déduite du décompilé sans jamais être mesurée.
//
// L'étage supérieur est tranché, lui aussi par mesure. `StateMachineActions` porte
// `_hud : IIdunGameHud` en `+0x48` et `_views : IIdunGameViews` en `+0x18` (`classFields`), donc :
//
//     UnitDeployment_PlaceUnitOnBoard(unitId, col, row, isManual, playerId) :
//         si _hud != null et <garde> :
//             si !_hud.<slot 0x11>(unitId) : return false      <- c'est `TryMarkUnitAsPlaced`,
//                                                                 MESURÉ à `true` (le grisement)
//         return _views.AddPlaceholderUnit(unitId, col, row, isManual, playerId)
//
// ⇒ On entre donc BIEN dans `AddPlaceholderUnit`, et c'est LUI qui rend `false`. Il lui reste
// exactement trois sorties, et ce bloc les départage AU LIEU d'en élire une :
//
//   (A) `UnitIdToPrefabDictionary$$Get` -> `TryGet` faux        -- déjà réfutée, on la RE-MESURE
//                                                                  au runtime plutôt que de s'en
//                                                                  remettre à `HasPrefabForUnitId`
//   (B) `IdunBoardView$$GetLogicalTileAt(col, row)` rend NUL    -- la tuile cliquée n'existe pas
//   (C) `_placeholderUnitViews` contient déjà `unitId`          -- unité déjà posée
//
// ⚠ Aucun de ces trois hooks n'écrit quoi que ce soit. On observe, on nomme, ET ENSUITE on
// décide — c'est le régime qui a déjà rattrapé deux fausses causes dans ce dossier.

const NS_BOARD = "idun";
const CLS_BOARD = "IdunBoardView";
let listenerAdd2: InvocationListener | null = null;
let listenerTuile: InvocationListener | null = null;
let listenerGet: InvocationListener | null = null;
const poseTrace: Array<Record<string, unknown>> = [];
const tuileTrace: Array<{ col: number; row: number; trouvee: boolean }> = [];
const getTrace: Array<{
    unitId: string | null; rendu: string; nul: boolean; dico: string;
    loaderAppele: number; lecture: string;
}> = [];
let listenerLoader: InvocationListener | null = null;
let listenerCle: InvocationListener | null = null;
let listenerDemande: InvocationListener | null = null;
/** Le régime À LA DEMANDE. Faux par défaut : il ÉCRIT dans le dictionnaire du jeu. */
let aLaDemande = false;
let demandesFaites = 0;
const demandeTrace: Array<{ unitId: string | null; detail: string }> = [];
let loaderFires = 0;
const loaderTrace: Array<{ rendu: string; nul: boolean }> = [];
const cleTrace: Array<{ entree: string | null; sortie: string | null }> = [];

function armerPoseDiag(): true | Refus {
    const kv = findClassAnywhere(NS_PREFAB, CLS_VIEWS_PREFAB);
    if (!kv) return refus(`\`${CLS_VIEWS_PREFAB}\` INTROUVABLE`);
    const mAdd = findMethodByParamCount(kv, "AddPlaceholderUnit", 5);
    if (!mAdd) return refus("`IdunGameViews$$AddPlaceholderUnit` INTROUVABLE (5 paramètres)");
    const kb = findClassAnywhere(NS_BOARD, CLS_BOARD);
    if (!kb) return refus(`\`${NS_BOARD}.${CLS_BOARD}\` INTROUVABLE`);
    const mTuile = findMethodByParamCount(kb, "GetLogicalTileAt", 2);
    if (!mTuile) return refus("`IdunBoardView$$GetLogicalTileAt` INTROUVABLE (2 paramètres)");
    const kd = findClassAnywhere(NS_PREFAB, CLS_DICO);
    if (!kd) return refus(`\`${CLS_DICO}\` INTROUVABLE`);
    const mGet = findMethodByParamCount(kd, "Get", 1);
    if (!mGet) return refus("`UnitIdToPrefabDictionary$$Get` INTROUVABLE (1 paramètre)");
    for (const [nom, mi] of
        [["AddPlaceholderUnit", mAdd], ["GetLogicalTileAt", mTuile], ["Get", mGet]] as const) {
        const t = lireTete(mi.ptr);
        if (t.erreur !== null) return refus(`tête de \`${nom}\` ILLISIBLE (${t.erreur})`);
        if (teteTriviale(t)) {
            return refus(`REFUS : \`${nom}\` résout sur un corps TRIVIAL (ret à l'octet `
                + `${t.retA}) -- adresse PARTAGÉE par déduplication. Cf. §8.`);
        }
    }
    if (!listenerAdd2) {
        listenerAdd2 = Interceptor.attach(mAdd.ptr, {
            onEnter(args) {
                const self = this as unknown as {
                    uid: string | null; c: number; r: number; vues: NativePointer;
                    tAvant: number; gAvant: number;
                };
                self.uid = null;
                try { self.uid = readIl2cppString(args[1]); } catch { /* best effort */ }
                self.c = args[2].toInt32();
                self.r = args[3].toInt32();
                self.vues = args[0];
                vuesDePose = args[0];      // l'AUTORITÉ sur « quelle vue déploie »
                // Les deux compteurs encadrent l'appel : ils disent quels sous-étages ont été
                // TRAVERSÉS, donc où la sortie s'est produite. Un `false` sans delta de tuile
                // désigne (A) ou (C) ; avec delta et tuile non trouvée, c'est (B).
                self.tAvant = tuileTrace.length;
                self.gAvant = getTrace.length;
            },
            onLeave(retval) {
                const self = this as unknown as {
                    uid: string | null; c: number; r: number; vues: NativePointer;
                    tAvant: number; gAvant: number;
                };
                if (poseTrace.length >= 32) return;
                const rendu = (retval.toInt32() & 0xff) !== 0;
                let dejaPosee: boolean | string = "non lu";
                let nbPosees: number | string = "non lu";
                try {
                    const kv2 = findClassAnywhere(NS_PREFAB, CLS_VIEWS_PREFAB);
                    const off = kv2 ? getFieldOffset(kv2, "_placeholderUnitViews") : -1;
                    if (off >= 0) {
                        const dico = self.vues.add(off).readPointer();
                        nbPosees = compteDict(dico);
                    } else { nbPosees = "champ `_placeholderUnitViews` ABSENT"; }
                } catch (e) { nbPosees = "ILLISIBLE : " + (e as Error).message; }
                const tuiles = tuileTrace.slice(self.tAvant);
                const gets = getTrace.slice(self.gAvant);
                if (gets.length > 0) dejaPosee = false;   // on a dépassé le test (C)
                poseTrace.push({
                    unitId: self.uid, col: self.c, row: self.r, rendu,
                    // Le VERDICT est dérivé des étages traversés, jamais deviné.
                    etage: rendu ? "POSÉE"
                        : gets.length === 0 ? "(A?) sorti AVANT `Get` -- prefab ou garde amont"
                        : gets.some((g) => g.nul) ? "(A) `Get` a rendu NUL"
                        : tuiles.length === 0 ? "(C) sorti APRÈS `Get`, SANS chercher de tuile "
                            + "-- `_placeholderUnitViews` contient déjà cet unitId"
                        : tuiles.some((t) => !t.trouvee) ? "(B) `GetLogicalTileAt` a rendu NUL"
                        : "sorti APRÈS une tuile TROUVÉE -- aucune des trois causes connues",
                    getsVus: gets, tuilesVues: tuiles, placeholders: nbPosees, dejaPosee,
                });
            },
        });
    }
    if (!listenerTuile) {
        listenerTuile = Interceptor.attach(mTuile.ptr, {
            onEnter(args) {
                const self = this as unknown as { c: number; r: number };
                self.c = args[1].toInt32();
                self.r = args[2].toInt32();
            },
            onLeave(retval) {
                const self = this as unknown as { c: number; r: number };
                if (tuileTrace.length < 64) {
                    tuileTrace.push({ col: self.c, row: self.r, trouvee: !retval.isNull() });
                }
            },
        });
    }
    // LE LOADER. S'il tire pendant un `Get` qui rend nul, l'entrée EXISTE et c'est la fabrication
    // du prefab qui échoue. S'il ne tire pas, `Get` est sorti par « clé absente » -- donc la clé
    // qu'il calcule DIFFÈRE de celle de `HasPrefabForUnitId`, seule autre explication possible.
    if (!listenerLoader && patron !== null && patron.loaderPtr !== null) {
        listenerLoader = Interceptor.attach(patron.loaderPtr, {
            onLeave(retval) {
                loaderFires++;
                if (loaderTrace.length < 32) {
                    loaderTrace.push({ rendu: retval.toString(), nul: retval.isNull() });
                }
            },
        });
    }
    // LA CLÉ. Les deux appels de `GetUnitIdForUniverse` dans `Get` passent par des blocs d'init
    // distincts : si leurs sorties diffèrent, la contradiction s'explique sans mystère.
    if (!listenerCle) {
        const kn = findClassAnywhere("idun.shared", "UnitNamingConventions")
            ?? findClassAnywhere("shared", "UnitNamingConventions");
        const mn = kn ? findMethodByParamCount(kn, "GetUnitIdForUniverse", 1) : null;
        if (mn) {
            listenerCle = Interceptor.attach(mn.ptr, {
                onEnter(args) {
                    const self = this as unknown as { e: string | null };
                    self.e = null;
                    try { self.e = readIl2cppString(args[0]); } catch { /* best effort */ }
                },
                onLeave(retval) {
                    const self = this as unknown as { e: string | null };
                    if (cleTrace.length >= 48) return;
                    let sortie: string | null = null;
                    try { sortie = readIl2cppString(retval); } catch { /* best effort */ }
                    cleTrace.push({ entree: self.e, sortie });
                },
            });
        }
    }
    // ============================================================================
    // LE CHARGEMENT À LA DEMANDE, DANS SA FORME DÉFINITIVE.
    //
    // On ancre `Get` et, si la clé MANQUE, on fabrique l'entrée DANS LE `onEnter` — puis on
    // laisse le corps natif s'exécuter normalement : il trouve alors la clé et déclenche son
    // propre chargement paresseux. Aucun `replace`, aucun retour fabriqué, et c'est le JEU qui
    // charge, au moment où il l'aurait fait.
    //
    // ⚠ POURQUOI PAS UN PRÉCHARGEMENT DU ROSTER. Créer les 55 entrées d'avance « pour tester »
    // valide un mécanisme qui n'est PAS celui qu'on livre : le régime d'épreuve doit être le
    // régime réel, sinon le vert ne prouve rien. Une entrée par unité RÉELLEMENT posée.
    //
    // ⚠ Les appels faits ici (`HasPrefabForUnitId`, `GetUnitVisualConfig`, `Add`) ne seront PAS
    // vus par nos propres ancrages : un `Interceptor` ne ré-observe pas un appel émis depuis un
    // autre callback sur le même thread. `addFires` ne bougera donc pas — ce n'est pas une panne.
    if (!listenerDemande) {
        const kdd = findClassAnywhere(NS_PREFAB, CLS_DICO);
        const kvv = findClassAnywhere(NS_PREFAB, CLS_VIEWS_PREFAB);
        const mHas = kdd ? findMethodByParamCount(kdd, "HasPrefabForUnitId", 1) : null;
        const mAddD = kdd ? findMethodByParamCount(kdd, "Add", 2) : null;
        const mCfg = kvv ? findMethodByParamCount(kvv, "GetUnitVisualConfig", 1) : null;
        if (!mHas || !mAddD || !mCfg) {
            return refus("chargement à la demande IMPOSSIBLE : "
                + `HasPrefabForUnitId=${mHas !== null} Add=${mAddD !== null} `
                + `GetUnitVisualConfig=${mCfg !== null}`);
        }
        listenerDemande = Interceptor.attach(mGet.ptr, {
            onEnter(args) {
                if (!aLaDemande || patron === null) return;
                const vues = vuesDePose;
                if (vues === null || vues.isNull()) {
                    if (demandeTrace.length < 32) {
                        demandeTrace.push({ unitId: null,
                            detail: "aucune vue captée -- rien tenté" });
                    }
                    return;
                }
                let id: string | null = null;
                try { id = readIl2cppString(args[1]); } catch { /* best effort */ }
                if (id === null || id === "") return;
                const r = fabriquerEntree(patron, args[0], vues, id, mHas, mAddD, mCfg);
                if (r.detail === "déjà présent -- rien fait") return;   // le cas courant
                demandesFaites++;
                if (demandeTrace.length < 32) demandeTrace.push({ unitId: id, detail: r.detail });
            },
        });
    }
    if (!listenerGet) {
        listenerGet = Interceptor.attach(mGet.ptr, {
            onEnter(args) {
                const self = this as unknown as {
                    uid: string | null; dico: NativePointer; lAvant: number;
                };
                self.uid = null;
                try { self.uid = readIl2cppString(args[1]); } catch { /* best effort */ }
                self.dico = args[0];
                self.lAvant = loaderFires;
                dicoDeGet = args[0];       // l'AUTORITÉ sur « quel dictionnaire est lu »
            },
            onLeave(retval) {
                const self = this as unknown as {
                    uid: string | null; dico: NativePointer; lAvant: number;
                };
                if (getTrace.length < 64) {
                    const dl = loaderFires - self.lAvant;
                    getTrace.push({
                        unitId: self.uid, rendu: retval.toString(), nul: retval.isNull(),
                        dico: self.dico.toString(), loaderAppele: dl,
                        // LE VERDICT, dérivé -- pas choisi.
                        lecture: !retval.isNull() ? "prefab rendu"
                            : dl > 0 ? "le loader A TIRÉ et n'a rien produit -- entrée présente, "
                                + "fabrication du prefab EN ÉCHEC"
                            : "le loader N'A PAS tiré -- `Get` est sorti par « clé absente », "
                                + "donc sa clé DIFFÈRE de celle de `HasPrefabForUnitId`",
                    });
                }
            },
        });
    }
    Interceptor.flush();
    return true;
}

function etatPool(): Record<string, unknown> {
    const src = getCampaignGameModeSourcePtr();
    return {
        // TRI-ÉTAT : `null` = pas de source capturée, ce qui n'est PAS « rien à déléguer ».
        sourceCampagne: src && !src.isNull() ? src.toString() : null,
        delegations: delegations.map((d) => ({
            nom: d.nom, role: d.role, arme: d.listener !== null,
            fires: d.fires, emprunts: d.emprunts, dernier: d.dernier, ancrage: d.ancrage,
        })),
    };
}

function etatPhase(): Record<string, unknown> {
    return {
        arme: relaisListener !== null,
        enableArme: enableListener !== null,
        forcer: forcerPhase,
        relaisFires, relaisForces,
        relaisRetours, enableObservations,
        ancrage,
    };
}

export function register(ctx: Ctx): void {
    /** OBSERVER / DÉSARMER. `{ armer: true }` pose le hook en régime transparent. */
    ctx.rpc.deploymentDraftArmer = (body?: { armer?: boolean }): Promise<unknown> | unknown => {
        if (!body || body.armer === undefined) {
            return { ok: true, lecture: true, arme: listener !== null, fires,
                     unitesPosees: unites ? unites.length : null, observations,
                     dernierRemplissage,
                     note: "passer { armer: true } pour observer, { armer: false } pour retirer" };
        }
        return queueOnMainThread(() => {
            if (body.armer === false) {
                if (listener) { listener.detach(); Interceptor.flush(); listener = null; }
                unites = null;
                return { ok: true, arme: false, action: "retire", fires };
            }
            const r = armer();
            if (r !== true) return r;
            return { ok: true, arme: true, fires, observations,
                     ancrage: `IdunBattle.ViewLogic.BattleSource.SandboxGameModeSource$$${METHODE}`,
                     note: "régime OBSERVER -- rien n'est écrit tant que `deploymentDraftUnites` "
                         + "n'a pas posé d'ids" };
        });
    };

    /** REMPLIR. Exige une observation préalable QUI A IDENTIFIÉ la classe du retour. */
    ctx.rpc.deploymentDraftUnites = (body?: {
        unites?: string[] | null; confirmer?: boolean;
    }): Promise<unknown> | unknown => {
        if (!body || body.unites === undefined) {
            return { ok: true, lecture: true, unitesPosees: unites, fires,
                     observations, dernierRemplissage };
        }
        return queueOnMainThread(() => {
            if (body.unites === null) {
                unites = null;
                return { ok: true, action: "retire", note: "hook redevenu TRANSPARENT" };
            }
            if (!Array.isArray(body.unites) || body.unites.some((u) => typeof u !== "string")) {
                return refus("`unites` doit être un tableau de chaînes (ids d'unité), ou null");
            }
            if (listener === null) {
                return refus("hook NON ARMÉ -- jouer `deploymentDraftArmer { armer: true }` "
                    + "d'abord, puis ouvrir l'écran de déploiement pour OBSERVER");
            }
            // Le cran qui rend ce module honnête : on ne remplit pas un conteneur qu'on n'a
            // jamais vu. Une observation qui n'a identifié AUCUNE classe = on refuse, en le
            // disant, plutôt que d'écrire dans un pointeur supposé.
            const vue = observations.find((o) => o.classe !== null);
            if (!vue) {
                return refus("AUCUNE observation n'a identifié la classe du retour ("
                    + `${observations.length} passage(s), ${fires} fire(s)). \`PooledList\` est un `
                    + "TYPE VALEUR : sa disposition doit être MESURÉE avant qu'on y écrive. "
                    + "Ouvrir l'écran de déploiement d'une sandbox, relire `deploymentDraftArmer`.");
            }
            if (body.confirmer !== true) {
                return refus("`confirmer: true` exigé : au prochain affichage de l'écran de "
                    + `déploiement, ce hook ÉCRIRA dans le conteneur rendu (\`${vue.classe}\`).`);
            }
            unites = body.unites.slice();
            return { ok: true, unitesPosees: unites.length, classeVue: vue.classe,
                     note: "posé -- l'écriture aura lieu au PROCHAIN appel de "
                         + `\`SandboxGameModeSource$$${METHODE}\`` };
        });
    };

    /** ÉTAT du hook de phase de déploiement. Lecture pure. */
    ctx.rpc.deploymentPhaseStatus = (): unknown => ({ ok: true, lecture: true, ...etatPhase() });

    /** Arme la CAPTURE du patron sur `UnitIdToPrefabDictionary$$Add`. Observation PURE.
     *  À armer AVANT `sandboxModeStart` : c'est `StartBattle` qui fait tirer `Add`. */
    ctx.rpc.deploymentPrefabArmer = (body?: { armer?: boolean }): unknown => {
        if (body == null || body.armer === undefined) {
            return { ok: true, lecture: true, ...etatPrefab(),
                     note: "lecture seule -- `armer: true` pose la capture (elle n'écrit rien)" };
        }
        if (body.armer === false) {
            if (listenerAdd) { try { listenerAdd.detach(); } catch { /* best effort */ } }
            listenerAdd = null;
            return { ok: true, arme: false };
        }
        const r = armerPrefab();
        if (r !== true) return r;
        return { ok: true, ...etatPrefab() };
    };

    /** Départage les trois sorties d'échec d'`AddPlaceholderUnit`. Observation PURE. */
    ctx.rpc.deploymentPoseDiag = (body?: {
        armer?: boolean; aLaDemande?: boolean; confirmer?: boolean;
    }): unknown => {
        // Le régime À LA DEMANDE se règle ici : il ÉCRIT dans le dictionnaire du jeu, donc il
        // exige `confirmer`, et son état est publié à chaque lecture.
        if (body?.aLaDemande !== undefined) {
            if (body.aLaDemande === true && body.confirmer !== true) {
                return refus("`confirmer: true` exigé : le régime à la demande ÉCRIT dans le "
                    + "dictionnaire de prefabs du jeu, sur défaut de clé");
            }
            aLaDemande = body.aLaDemande;
        }
        if (body == null || body.armer === undefined) {
            return { ok: true, lecture: true,
                     arme: listenerAdd2 !== null && listenerTuile !== null,
                     poses: poseTrace.slice(-12),
                     tuiles: tuileTrace.slice(-16), gets: getTrace.slice(-16),
                     // TRI-ÉTAT : `loaderArme: false` veut dire NON MESURÉ, pas « n'a pas tiré ».
                     loaderArme: listenerLoader !== null, loaderFires,
                     loaderRetours: loaderTrace.slice(-12),
                     aLaDemande, demandesFaites, demandes: demandeTrace.slice(-12),
                     clesArme: listenerCle !== null, cles: cleTrace.slice(-16) };
        }
        if (body.armer === false) {
            for (const l of [listenerAdd2, listenerTuile, listenerGet]) {
                if (l) { try { l.detach(); } catch { /* best effort */ } }
            }
            listenerAdd2 = null; listenerTuile = null; listenerGet = null;
            return { ok: true, arme: false };
        }
        const r = armerPoseDiag();
        if (r !== true) return r;
        return { ok: true, arme: true,
                 note: "poser une unité, puis relire ce RPC sans argument" };
    };

    /**
     * POURQUOI `Get` REND NUL ALORS QUE LA CLÉ EST LÀ. Lectures pures, aucune écriture.
     *
     * Mesuré session 53, MÊME dictionnaire et MÊME instant : `HasPrefabForUnitId` rend `true`
     * pour `spaceBlackmane` quand le `Get` du jeu rend `0x0`. `ContainsKey` étant donc vrai,
     * `Get` ne sort PAS par la branche « clé absente » — la seule autre issue à `0x0` est que
     * le loader rende un prefab NUL. Or `StartBattle` teste `IdunAssets$$IsAssetBundleAvailable`,
     * ÉCRIT UN AVERTISSEMENT, **et ajoute l'entrée quand même** : une entrée présente ne promet
     * donc rien sur la disponibilité de l'asset.
     *
     * Ce RPC lit, pour chaque unité : la config visuelle, sa référence d'asset (champ résolu PAR
     * TYPE), et la réponse de `IsAssetBundleAvailable`. Il n'invoque AUCUN chargement.
     */
    ctx.rpc.deploymentPrefabInspecter = (body?: { ids?: string[] }):
        Promise<unknown> | unknown => {
        const ids = body?.ids ?? [];
        if (ids.length === 0) return refus("`ids` exigé");
        return queueOnMainThread(() => {
            const d = dicoVivant();
            if ("ok" in d) return d;
            const kv = findClassAnywhere(NS_PREFAB, CLS_VIEWS_PREFAB);
            if (!kv) return refus(`\`${CLS_VIEWS_PREFAB}\` INTROUVABLE`);
            const mCfg = findMethodByParamCount(kv, "GetUnitVisualConfig", 1);
            if (!mCfg) return refus("`GetUnitVisualConfig` INTROUVABLE (1 paramètre)");
            const kAssets = findClassAnywhere("Idun.Source.Scripts", "IdunAssets")
                ?? findClassAnywhere("idun.Idun.Source.Scripts", "IdunAssets");
            const mDispo = kAssets
                ? findMethodByParamCount(kAssets, "IsAssetBundleAvailable", 1) : null;
            const out: Array<Record<string, unknown>> = [];
            for (const id of ids) {
                const ligne: Record<string, unknown> = { unitId: id };
                try {
                    const cfg = invokeMethod(mCfg.info, d.vues, [createManagedString(id)]);
                    ligne.config = cfg.toString();
                    if (cfg.isNull()) { ligne.verdict = "config visuelle NULLE"; out.push(ligne);
                                        continue; }
                    const kc = cfg.readPointer();
                    ligne.classeConfig = s(class_get_name(kc) as NativePointer);
                    const champs = champsDe(kc);
                    ligne.champs = champs.map((c) => `${c.nom}:${c.type}`);
                    const cRef = champs.find((c) => c.type.indexOf("AssetReference") >= 0);
                    if (!cRef) {
                        ligne.verdict = "aucun champ `AssetReference*` -- chemin PÉRIMÉ";
                        out.push(ligne); continue;
                    }
                    const aref = cfg.add(cRef.off).readPointer();
                    ligne.assetRef = `${cRef.nom}@+0x${cRef.off.toString(16)} = ${aref}`;
                    if (mDispo === null) {
                        ligne.verdict = "`IdunAssets$$IsAssetBundleAvailable` INTROUVABLE "
                            + "-- NON MESURÉ (ce n'est pas un `false`)";
                    } else if (aref.isNull()) {
                        ligne.verdict = "référence d'asset NULLE";
                    } else {
                        const dispo = boolBoxe(invokeMethod(mDispo.info, null, [aref]));
                        ligne.bundleDisponible = dispo;
                        ligne.verdict = dispo
                            ? "bundle DISPONIBLE -- la cause est ailleurs"
                            : "bundle INDISPONIBLE -- le loader ne peut RIEN produire, `Get` "
                                + "rendra nul quoi qu'on écrive dans le dictionnaire";
                    }
                } catch (e) { ligne.verdict = "LEVÉ : " + (e as Error).message; }
                out.push(ligne);
            }
            return { ok: true, dico: d.dico.toString(), source: d.source, unites: out };
        });
    };

    /**
     * L'ÉPREUVE CONTRÔLÉE : fabriquer l'entrée d'UNE unité, puis appeler `Get` NOUS-MÊMES et
     * DÉCODER ce qui en sort — retour, ou exception managée avec sa classe et son message.
     *
     * Pourquoi elle existe : `listenerDemande` a vu **5** appels de `Get` là où `listenerGet`
     * n'en a enregistré que **3**, et les deux manquants sont exactement les unités posées. Or
     * `listenerGet` écrit dans son `onLeave` — un `onLeave` qui ne tire pas signifie que l'appel
     * N'EST PAS REVENU. `Get` lève donc dans notre entrée fabriquée, silencieusement : rien sur
     * le plateau, aucune trace de pose, aucune erreur à l'écran. Seul un appel encadré peut lire
     * ce message.
     *
     * ⛔ ON DÉPOSE LES ANCRAGES SUR `Get` PENDANT L'APPEL. Ancrer la méthode qu'on invoque est
     * le motif qui gèle le jeu (`retreatInvoke` applique déjà cette précaution). Ils sont
     * ré-armés ensuite.
     */
    ctx.rpc.deploymentPrefabEprouver = (body?: { id?: string; confirmer?: boolean }):
        Promise<unknown> | unknown => {
        const id = body?.id;
        if (!id) return refus("`id` exigé (une seule unité)");
        if (body?.confirmer !== true) {
            return refus("`confirmer: true` exigé : cette épreuve ÉCRIT une entrée puis INVOQUE "
                + "`Get`, donc elle peut déclencher un chargement d'asset");
        }
        if (patron === null) return refus("aucun PATRON capturé -- monter une bataille d'abord");
        return queueOnMainThread(() => {
            const p = patron;
            if (p === null) return refus("patron perdu");
            const d = dicoVivant();
            if ("ok" in d) return d;
            const kd = findClassAnywhere(NS_PREFAB, CLS_DICO);
            const kv = findClassAnywhere(NS_PREFAB, CLS_VIEWS_PREFAB);
            if (!kd || !kv) return refus("classes INTROUVABLES");
            const mHas = findMethodByParamCount(kd, "HasPrefabForUnitId", 1);
            const mAdd = findMethodByParamCount(kd, "Add", 2);
            const mCfg = findMethodByParamCount(kv, "GetUnitVisualConfig", 1);
            const mGet = findMethodByParamCount(kd, "Get", 1);
            if (!mHas || !mAdd || !mCfg || !mGet) return refus("méthodes INTROUVABLES");

            const fab = fabriquerEntree(p, d.dico, d.vues, id, mHas, mAdd, mCfg);
            const sortie: Record<string, unknown> = { unitId: id, fabrication: fab.detail };

            // ⛔ dépose des ancrages sur `Get` -- on invoque ce qu'on ancrait.
            const gardeDemande = aLaDemande;
            aLaDemande = false;
            for (const l of [listenerDemande, listenerGet]) {
                if (l) { try { l.detach(); } catch { /* best effort */ } }
            }
            listenerDemande = null; listenerGet = null;
            Interceptor.flush();
            try {
                const r = invokeMethod(mGet.info, d.dico, [createManagedString(id)]);
                sortie.getRetour = r.toString();
                sortie.getNul = r.isNull();
                sortie.verdict = r.isNull()
                    ? "`Get` rend NUL sans lever -- l'entrée est là mais ne produit pas de prefab"
                    : "`Get` a RENDU quelque chose -- le prefab existe";
            } catch (e) {
                // C'EST LE MESSAGE QU'ON CHERCHAIT : `invokeMethod` décode la classe, le message
                // et la pile de l'exception managée.
                sortie.verdict = "`Get` a LEVÉ";
                sortie.exception = (e as Error).message;
            }
            // L'état de l'entrée APRÈS l'appel : le loader a-t-il rempli `_prefab` ?
            if (fab.ref !== undefined) {
                try {
                    const pr = fab.ref.add(p.offPrefab).readPointer();
                    sortie.prefabApres = pr.toString();
                    sortie.prefabRempli = !pr.isNull();
                } catch (e) { sortie.prefabApres = "ILLISIBLE : " + (e as Error).message; }
            }
            aLaDemande = gardeDemande;
            const re = armerPoseDiag();
            sortie.ancragesReArmes = re === true ? true : (re as Refus).error;
            return { ok: true, ...sortie };
        });
    };

    /** Diagnostic PUR : le patron, et pour chaque id demandé si le jeu a déjà son prefab.
     *  `HasPrefabForUnitId` est une lecture (`ContainsKey`), elle n'écrit rien. */
    ctx.rpc.deploymentPrefabStatus = (body?: { ids?: string[] }): Promise<unknown> | unknown => {
        const ids = body?.ids ?? [];
        if (ids.length === 0) return { ok: true, lecture: true, ...etatPrefab() };
        return queueOnMainThread(() => {
            const d = dicoVivant();
            if ("ok" in d) return d;
            const kd = findClassAnywhere(NS_PREFAB, CLS_DICO);
            if (!kd) return refus(`\`${CLS_DICO}\` INTROUVABLE`);
            const mh = findMethodByParamCount(kd, "HasPrefabForUnitId", 1);
            if (!mh) return refus("`HasPrefabForUnitId` INTROUVABLE (1 paramètre)");
            const vus: Array<{ unitId: string; aSonPrefab: boolean | string }> = [];
            for (const id of ids) {
                try {
                    const r = invokeMethod(mh.info, d.dico, [createManagedString(id)]);
                    vus.push({ unitId: id, aSonPrefab: boolBoxe(r) });
                } catch (e) { vus.push({ unitId: id, aSonPrefab: "LEVÉ : " + (e as Error).message }); }
            }
            return { ok: true, dico: d.dico.toString(), vus, ...etatPrefab() };
        });
    };

    /** LE CHARGEMENT À LA DEMANDE. Fabrique l'entrée manquante pour chaque id, sur le patron
     *  capturé. N'appelle AUCUN chargement d'asset : c'est le jeu qui tirera le prefab à son
     *  premier `Get`, comme il le fait pour les unités de la BC. */
    ctx.rpc.deploymentPrefabCharger = (body?: {
        ids?: string[]; confirmer?: boolean; tout?: boolean;
    }):
        Promise<unknown> | unknown => {
        let ids = body?.ids ?? [];
        if (!body || body.confirmer === undefined) {
            return { ok: true, lecture: true, ...etatPrefab(),
                     note: "`confirmer: true` exigé, plus `ids` OU `tout: true` : ce RPC ÉCRIT "
                         + "dans le dictionnaire de prefabs de la vue vivante" };
        }
        if (body.confirmer !== true) return refus("`confirmer: true` exigé");
        // `tout` = tout ce que le HUD affiche. C'est le seul régime qui rende l'écran
        // réellement utilisable : l'utilisateur clique un portrait, pas un identifiant.
        if (body.tout === true) {
            const r = listeDuRoster();
            if (!Array.isArray(r)) return r;
            ids = r;
        }
        if (ids.length === 0) return refus("`ids` vide et `tout` non demandé : rien à faire");
        if (patron === null) {
            return refus("aucun PATRON capturé -- armer `deploymentPrefabArmer` AVANT le montage, "
                + `puis remonter la bataille (addFires=${addFires}, refus=${patronRefus})`);
        }
        return queueOnMainThread(() => {
            const p = patron;
            if (p === null) return refus("patron perdu entre-temps");
            const d = dicoVivant();
            if ("ok" in d) return d;
            const kd = findClassAnywhere(NS_PREFAB, CLS_DICO);
            const kv = findClassAnywhere(NS_PREFAB, CLS_VIEWS_PREFAB);
            if (!kd || !kv) return refus("classes du dictionnaire/vue INTROUVABLES");
            const mHas = findMethodByParamCount(kd, "HasPrefabForUnitId", 1);
            const mAdd = findMethodByParamCount(kd, "Add", 2);
            const mCfg = findMethodByParamCount(kv, "GetUnitVisualConfig", 1);
            if (!mHas || !mAdd) return refus("`HasPrefabForUnitId`/`Add` INTROUVABLES");
            if (!mCfg) return refus("`IdunGameViews$$GetUnitVisualConfig` INTROUVABLE (1 param)");
            const faits: Array<{ unitId: string; ok: boolean; detail: string }> = [];
            for (const id of ids) {
                let detail = "";
                let ok = false;
                try {
                    const sid = createManagedString(id);
                    // `Add` LÈVE sur clé dupliquée : on ne tente que ce qui manque vraiment.
                    if (boolBoxe(invokeMethod(mHas.info, d.dico, [sid]))) {
                        detail = "déjà présent -- rien fait";
                        ok = true;
                    } else {
                        // Lecture pure (`UnitConfigMap.TryGetValue`), aucun asset touché.
                        const cfg = invokeMethod(mCfg.info, d.vues, [sid]);
                        if (cfg.isNull()) {
                            detail = "`GetUnitVisualConfig` rend NUL -- cette unité n'a pas de "
                                + "config visuelle dans l'univers chargé ; on n'invente rien";
                        } else {
                            // LE SLOT SE CHOISIT PAR LE TYPE RÉEL DE `cfg`, pas par élimination.
                            // Mesuré : le choix « le premier champ qui n'est pas l'EffectPool »
                            // visait un autre membre de la fermeture ; la config du patron restait
                            // en place et DEUX unités distinctes s'affichaient avec SON modèle.
                            const nomCfg = s(class_get_name(cfg.readPointer()) as NativePointer);
                            const cible = p.champsHolder.find((c) => c.type === nomCfg);
                            if (!cible) {
                                detail = `aucun champ de type \`${nomCfg}\` sur `
                                    + `\`${p.holderClasseNom}\` -- champs : `
                                    + p.champsHolder.map((c) => `${c.nom}:${c.type}`).join(", ")
                                    + " ; on n'écrit RIEN plutôt qu'à côté";
                                faits.push({ unitId: id, ok: false, detail });
                                continue;
                            }
                            const holder = cloner(p.exemplaireHolder, p.holderClasse,
                                                  p.tailleHolder);
                            holder.add(cible.off).writePointer(cfg);
                            // RELECTURE : une écriture non vérifiée est ce qui a produit deux
                            // modèles identiques sans la moindre erreur.
                            const relu = holder.add(cible.off).readPointer();
                            if (!relu.equals(cfg)) {
                                detail = `écriture NON CONFIRMÉE dans \`${cible.nom}\` `
                                    + `(relu ${relu}, attendu ${cfg})`;
                                faits.push({ unitId: id, ok: false, detail });
                                continue;
                            }
                            const del = cloner(p.exemplaireDel, p.delClasse, p.tailleDel);
                            del.add(p.offTarget).writePointer(holder);
                            // `method_code` est le slot que `Get` passe à l'invocateur.
                            if (p.offMethodCode < 0) {
                                detail = "`method_code` ABSENT de `" + p.delClasseNom
                                    + "` : le délégué cloné appellerait la fermeture du PATRON. "
                                    + "On refuse plutôt que d'afficher un modèle d'emprunt.";
                                faits.push({ unitId: id, ok: false, detail });
                                continue;
                            }
                            del.add(p.offMethodCode).writePointer(holder);
                            const reluCode = del.add(p.offMethodCode).readPointer();
                            if (!reluCode.equals(holder)) {
                                detail = `\`method_code\` NON CONFIRMÉ (relu ${reluCode})`;
                                faits.push({ unitId: id, ok: false, detail });
                                continue;
                            }
                            const ref = cloner(p.exemplaireRef, p.refClasse, p.tailleRef);
                            // ⚠ LE SLOT QUI DOIT REPARTIR À NUL : le patron a son prefab déjà
                            // résolu ; le laisser afficherait le modèle de l'unité capturée.
                            ref.add(p.offPrefab).writePointer(ptr(0));
                            ref.add(p.offLoader).writePointer(del);
                            gcRoot.add(holder); gcRoot.add(del); gcRoot.add(ref);
                            invokeMethod(mAdd.info, d.dico, [sid, ref]);
                            detail = `entrée créée -- config ${nomCfg} @ \`${cible.nom}\``
                                + `+0x${cible.off.toString(16)} = ${cfg} (relue OK)`;
                            ok = true;
                        }
                    }
                } catch (e) { detail = "LEVÉ : " + (e as Error).message; }
                faits.push({ unitId: id, ok, detail });
                if (prefabCharges.length < 128) prefabCharges.push({ unitId: id, ok, detail });
            }
            return { ok: true, faits, poses: faits.filter((f) => f.ok).length,
                     total: ids.length };
        });
    };

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
     * LE HUD — les DEUX dictionnaires, et le VERDICT de chaque clic. Observation pure.
     *
     * `{ armer: true }` ancre `Show` (lit les comptes après remplissage) et
     * `TryMarkUnitAsPlaced` (capture unitId + retour). Sans corps : lecture.
     */
    ctx.rpc.deploymentHudArmer = (body?: { armer?: boolean }): unknown => {
        if (!body || body.armer === undefined) {
            return { ok: true, lecture: true,
                     arme: listenerShow !== null && listenerPose !== null,
                     etat: hudEtat, poses: hudPoses, plateau: hudBoard };
        }
        if (body.armer === false) {
            if (listenerShow) { listenerShow.detach(); listenerShow = null; }
            if (listenerPose) { listenerPose.detach(); listenerPose = null; } if (listenerBoard) { listenerBoard.detach(); listenerBoard = null; }
            Interceptor.flush();
            return { ok: true, arme: false, action: "retire" };
        }
        const r = armerHud();
        if (r !== true) return r;
        return { ok: true, arme: true, etat: hudEtat, poses: hudPoses, plateau: hudBoard,
                 note: "`Show` publie les deux comptes ; `TryMarkUnitAsPlaced` publie le "
                     + "verdict de chaque clic. Un premier dictionnaire plein et un second "
                     + "vide EST la signature de « je sélectionne mais je ne pose pas »." };
    };

    /**
     * EMPRUNT ISOLÉ — invoque la méthode campagne HORS de tout callback d'interception.
     *
     * ⚠ C'EST UN DISCRIMINANT, PAS UNE COMMODITÉ. Mesuré : l'ancrage sur
     * `CampaignProgression$$GetDeployableUnits` attrape les appels NATURELS du jeu (2 fires
     * pendant une navigation de campagne, `dansEmprunt: false`) mais JAMAIS ceux de nos
     * emprunts. Deux lectures restent :
     *
     *   (a) le corps emprunté ne s'exécute pas -- `invokeMethod` rendrait un pointeur sans
     *       rien faire, et toutes nos substitutions seraient des illusions ;
     *   (b) il s'exécute, mais un appel déclenché DEPUIS un callback d'interception n'est pas
     *       re-observé par l'`Interceptor` sur le même thread.
     *
     * Ce RPC tranche : il fait le MÊME appel, depuis la file du thread principal, sans être
     * dans aucun hook. Si le compteur bouge, c'est (b) — nos emprunts marchent, c'est notre
     * OBSERVATION qui est aveugle. S'il ne bouge pas, c'est (a), et c'est bien plus grave.
     *
     * ⚠ La règle « ne jamais ancrer la méthode qu'on invoque » est RESPECTÉE : on invoque
     * `GetUnitsForDeploymentHUD`, on ancre `GetDeployableUnits`. Deux méthodes distinctes.
     * Et c'est un appel que le JEU fait lui-même — pas un natif jamais observé.
     */
    /**
     * PRÉ-EMPRUNT — calcule la valeur empruntée HORS de tout hook, la déboxe, la garde.
     *
     * C'est la forme imposée par le §24 : pendant la délégation, l'`Interceptor` est aveugle,
     * donc `sansFiltre` ne peut pas y agir. En pré-empruntant ici, l'appel est visible, le
     * masque s'applique, et il ne reste au `onLeave` de la délégation qu'un `retval.replace`.
     *
     * ⚠ DEUX CRANS QUE LA VERSION NAÏVE N'AVAIT PAS :
     *
     *   1. **DÉBOXAGE.** `il2cpp_runtime_invoke` BOXE les types valeur, et
     *      `PooledList<System.String>` en est un (`classes.tsv` : `isValueType=1`). Rendre la
     *      BOÎTE là où l'appelant attend la valeur lui fait lire l'en-tête d'objet comme si
     *      c'était le conteneur. La valeur utile est à `+0x10`. Les deux classes sont
     *      PUBLIÉES : c'est le seul moyen de voir qu'on a bien déboxé, plutôt que de
     *      supposer.
     *   2. **RACINE GC.** Entre l'emprunt et la substitution il peut s'écouler un montage
     *      entier. Sans `gcRoot`, la valeur est ramassable.
     */
    ctx.rpc.deploymentPoolPreEmprunt = (body?: { confirmer?: boolean; oublier?: boolean }):
        Promise<unknown> | unknown => {
        if (body?.oublier === true) {
            preEmprunt = null; preEmpruntInfo = null;
            return { ok: true, action: "oublie" };
        }
        if (!body || body.confirmer === undefined) {
            return { ok: true, lecture: true, pret: preEmprunt !== null, info: preEmpruntInfo };
        }
        if (body.confirmer !== true) {
            return { ok: false, error: "`confirmer: true` exigé : ce RPC INVOQUE la méthode de "
                + "la source campagne vivante." };
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
                boite: boite.toString(), classeBoite: cBoite.classe, erreurBoite: cBoite.erreur,
                deboxe: deboxe.toString(), classeDeboxee: cDeboxe.classe,
                erreurDeboxee: cDeboxe.erreur,
                // Le témoin que l'appel a VRAIMENT traversé `GetDeployableUnits`, et que le
                // masque a pu agir : sans lui, « ok » ne dirait rien.
                deltaGetDeployableUnits: firesDeployable - avant,
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
            return { ok: false, error: "aucune `CampaignGameModeSource` captée -- le warmup ne "
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
            // appelé -- les trois appartiennent au cycle inject/warmup (résidu #10021).
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
     * warmup a ouvert — et **pas** des règles « génériques » ni celles d'un nœud choisi.
     * Dire « la sandbox devient fidèle » serait faux : elle IMPERSONNE UN NŒUD PARTICULIER.
     * Choisir ce nœud voudrait dire écrire `_currentCampaignId`/`_currentLocationIndex` et
     * re-résoudre `_currentMatch` — NON MESURÉ, et un DTO déjà résolu deviendrait périmé.
     */
    ctx.rpc.deploymentPoolArmer = (body?: {
        armer?: boolean; confirmer?: boolean; only?: string[];
    }): Promise<unknown> | unknown => {
        if (!body || body.armer === undefined) {
            return { ok: true, lecture: true, ...etatPool(),
                     note: "{ armer: true, confirmer: true } pour déléguer à la source campagne ; "
                         + "`only: [\"GetUnitModel\"]` pour n'en déléguer qu'une" };
        }
        return queueOnMainThread(() => {
            if (body.armer === false) {
                for (const d of delegations) {
                    if (d.listener) { d.listener.detach(); d.listener = null; }
                }
                Interceptor.flush();
                return { ok: true, action: "retire", ...etatPool() };
            }
            if (body.confirmer !== true) {
                return refus("`confirmer: true` exigé : chaque délégation SUBSTITUE le retour dès "
                    + "l'armement. Et le wrapper fait répondre la sandbox comme LE NŒUD DE CAMPAGNE "
                    + "où pointe la source capturée -- pas comme une source générique.");
            }
            const src = getCampaignGameModeSourcePtr();
            if (src === null || src.isNull()) {
                return refus("aucune `CampaignGameModeSource` capturée : le warmup ne l'a pas prise, "
                    + "ou la session est froide. On ne délègue PAS à rien -- rejouer le warmup.");
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
            return { ok: true, action: "arme", rapport, ...etatPool() };
        });
    };

    /**
     * ARMER / FORCER / DÉSARMER la phase de déploiement.
     *
     *   { armer: true }                      -> OBSERVER : pose les deux ancrages, n'écrit RIEN
     *   { forcer: true, confirmer: true }    -> le relais rendra `true` au prochain `Enable`
     *   { forcer: false }                    -> redevient transparent, ancrages en place
     *   { armer: false }                     -> retire tout
     *
     * `confirmer: true` est exigé pour FORCER, parce que c'est le seul geste qui écrit — et il
     * écrit dans la décision d'un objet (`VisualBattleQuery`) que TOUS les modes partagent.
     */
    ctx.rpc.deploymentPhaseArmer = (body?: {
        armer?: boolean; forcer?: boolean; confirmer?: boolean;
    }): Promise<unknown> | unknown => {
        if (!body || (body.armer === undefined && body.forcer === undefined)) {
            return { ok: true, lecture: true, ...etatPhase(),
                     note: "{ armer: true } pour OBSERVER ; puis { forcer: true, confirmer: true }" };
        }
        return queueOnMainThread(() => {
            if (body.armer === false) {
                if (relaisListener) { relaisListener.detach(); relaisListener = null; }
                if (enableListener) { enableListener.detach(); enableListener = null; }
                Interceptor.flush();
                forcerPhase = false;
                return { ok: true, action: "retire", ...etatPhase() };
            }
            if (body.armer === true) {
                const r = armerPhase();
                if (r !== true) return r;
            }
            if (body.forcer !== undefined) {
                if (relaisListener === null) {
                    return refus("hook NON ARMÉ -- jouer `{ armer: true }` d'abord. Forcer sans "
                        + "avoir observé ne dirait pas si le drapeau `skipUnitDeployment` "
                        + "court-circuite déjà le prédicat.");
                }
                if (body.forcer === true && body.confirmer !== true) {
                    return refus("`confirmer: true` exigé : forcer écrit dans la décision de "
                        + "`VisualBattleQuery`, que TOUS les modes de jeu partagent -- une phase "
                        + "de déploiement apparaîtrait là où le jeu n'en veut pas.");
                }
                forcerPhase = body.forcer === true;
            }
            return { ok: true, action: body.armer === true ? "arme" : "regime", ...etatPhase() };
        });
    };
}
