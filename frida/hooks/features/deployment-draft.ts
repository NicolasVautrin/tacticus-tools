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
    class_get_name, findClassAnywhere, findMethodByParamCount, getFieldOffset, il2cppBase, s,
} from "../il2cpp/helpers.js";
import { createManagedString, invokeMethod } from "../il2cpp/invoke.js";
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
            try {
                const argv = (this as unknown as { argv: NativePointer[] }).argv ?? [];
                const r = invokeMethod(mc.info, src, argv) as NativePointer;
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

    /** ÉTAT du mirror de `GetUnlockedUnitsPooled`. Lecture pure. */
    ctx.rpc.deploymentPoolStatus = (): unknown => ({ ok: true, lecture: true, ...etatPool() });

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
        locationIndex?: number; confirmer?: boolean;
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
            return {
                source: src.toString(), locationIndex: idx,
                campaignProgression: progBrut.isNull() ? null : progBrut.toString(),
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
