// LE REGISTRE DES COMPOSITIONS — une décision, DEUX consommateurs qui lisent la même chose.
//
// LE PROBLÈME QUE ÇA RÉSOUT, ET IL EST SILENCIEUX
// ------------------------------------------------
// La composition et les buffs se posent à DEUX moments différents, et c'est structurel :
//
//   `LoadBattle.onLeave`   -- la BC vient d'être fabriquée, pas encore remise au runner. C'est la
//                             SEULE fenêtre où l'environnement soit mutable (mesuré : le runner lit
//                             `BC.EnvironmentAbilities` à son `Initialize` et personne ne relit
//                             ensuite).
//   `GetBattleLineup`      -- le FSM de déploiement demande QUI le joueur amène. Mesuré par pile :
//                             `StateMachineActions$$DeployBattleLineup` ->
//                             `VisualBattleQuery$$GetBattleLineupToDeploy` -> ici. La BC est DÉJÀ
//                             passée au runner à ce moment (on est dans `IdunMainView$$StartBattle`).
//
// Si ces deux moments lisent des sources DIFFÉRENTES, on buffe des unités qui ne se déploient pas.
// L'écart ne lève aucune erreur : les buffs s'installent, sur les mauvaises cibles, et le résultat
// se lit comme « les buffs ne marchent pas ». D'où ce registre : UN endroit, LU deux fois.
//
// LA CLÉ EST LE MODE, ET C'EST LE SEUL DÉNOMINATEUR COMMUN
// ---------------------------------------------------------
// Au `LoadBattle.onLeave` on tient la BC et la source ; à `GetBattleLineup` on ne tient que la
// source. La classe de source (`CampaignGameModeSource`, ...) est donc la seule identité
// disponible AUX DEUX endroits. Corollaire assumé et DIT : une composition retenue par mode, pas
// par nœud. Deux nœuds du même mode partagent l'entrée -- si ça devient faux pour ton usage, c'est
// la clé qu'il faut enrichir, pas un contournement à ajouter.
//
// CE QUI EST ÉCRIT, ET CE QUI NE L'EST PAS
// -----------------------------------------
// Rien n'est persisté côté jeu. Le natif reconstruit son `String[]` depuis sa propre sauvegarde à
// CHAQUE appel -- mesuré, les deux observations rendent le même `avant`. On réécrit donc pour
// l'appel en cours, et le compte reste intact dès qu'on désarme. Muter la configuration serait
// l'idéal ; ce registre est le repli honnête, et il ne prétend pas être autre chose.
//
// ⛔ MUTUELLEMENT EXCLUSIF AVEC `lineupSource`. Ce module ANCRE `GetBattleLineup` ; `lineup-lire`
// l'INVOQUE. Invoquer une méthode qu'on ancre fait retomber l'appel natif dans notre propre
// trampoline pendant que Frida veut y exécuter du JS sur un thread qui tient déjà le runtime --
// gel mesuré trois fois sur trois dans ce dépôt. `estArme()` est exporté pour que la lecture
// REFUSE au lieu de geler.
//
// ⚠ OBSERVER D'ABORD. Tant qu'aucun passage n'a établi que le retour est un tableau de chaînes ET
// sa longueur, on n'écrit RIEN -- une longueur lue de travers ferait écrire dans le tas du jeu.
// ⚠ ON N'ÉCRIT QUE DANS LES CASES QUI EXISTENT (`min(n, ids)`), et le rapport DIT la troncature.
// ⚠ ENRACINER AVANT D'ÉCRIRE : entre `il2cpp_string_new` et l'écriture, la chaîne n'est référencée
// par rien de managé et une collecte la libérerait.

import { Ctx } from "../controller.js";
import { queueOnMainThread } from "../runtime/queue.js";
import {
    class_get_name, findClassAnywhere, findMethodByParamCount, s as cstr,
} from "../il2cpp/helpers.js";
import { createManagedArray, createManagedString } from "../il2cpp/invoke.js";
import { gcRoot } from "../il2cpp/gc-root.js";
// LE FOYER de `IdunNavigation._unitProgression`, capté par l'amorce. C'est la SECONDE source du
// magasin, et la seule qui n'exige NI bataille NI capteur -- cf. `magasinUtilisable()`.
import { getUnitProgressionPtr } from "./campaign-builder.js";
// La projection de l'état de match -- c'est elle qui donne la composition RÉELLEMENT en jeu au
// moment de la retraite, plutôt qu'une intention qu'on aurait notée avant.
import { projectMatchState, readBattleStatus } from "../game/match-state.js";

const NS_SRC = "IdunBattle.ViewLogic.BattleSource";

/** Les sources dont on sait qu'elles DÉCLARENT `GetBattleLineup(1)`. Une source absente d'ici
 *  n'est pas « sans composition » : elle n'est pas couverte par CE module, et le refus le dit. */
const CLASSES: Readonly<Record<string, string>> = {
    campagne: "CampaignGameModeSource",
    pvp: "PvpGameModeSource",
    mow: "MachinesOfWarEventGameModeSource",
    guildBoss: "GuildBossGameModeSource",
    // ⚠ CELLES-CI RENDENT UN TABLEAU VIDE, donc elles passent par `remplacerRetour`, jamais par
    // `poser` -- il n'y a aucune case à écrire. C'est la SEULE voie de substitution qu'elles
    // admettent : ni l'une ni l'autre ne lit de magasin (talon constant au décompilé), donc
    // `lineupSubstituer` ne peut rien pour elles.
    guildWar: "GuildWarsGameModeSource",
    sandbox: "SandboxGameModeSource",
};

/** `System.String[]` : longueur en `+0x18`, éléments dès `+0x20`. Relevé sur le lecteur de
 *  `game/source-lineup.ts` -- un seul endroit connaît cette disposition à l'origine. */
const OFF_LONGUEUR = 0x18;
const OFF_ELEMENTS = 0x20;
/** Une longueur lue de travers rendrait un nombre énorme. Aucun mode n'approche 64 places. */
const PLAFOND_PLACES = 64;

interface Observation {
    classeRetour: string | null;
    longueur: number | null;
    avant: string[] | null;
    /** QUI a appelé. Adresses BRUTES, jamais nommées ici : `DebugSymbol.fromAddress` ignore les
     *  méthodes IL2CPP. La table qui donne les symboles vit HORS du process. `null` = pas mesurée. */
    pile: string[] | null;
    base: string | null;
}

/** Une composition retenue, et D'OÙ elle vient. `origine` n'est pas décoratif : au moment de
 *  buffer, savoir si la composition a été décidée en sandbox ou posée à la main change la
 *  confiance qu'on lui accorde. */
export interface CompositionRetenue {
    ids: string[];
    confirme: boolean;
    origine: string;
}

/** Clé = NOM DE CLASSE de la source (pas le libellé de mode) : c'est ce que les deux
 *  consommateurs peuvent lire chacun de leur côté. */
const registre = new Map<string, CompositionRetenue>();

let listener: InvocationListener | null = null;
let classeArmee: string | null = null;
let fires = 0;
const observations: Observation[] = [];
let dernierePose: Record<string, unknown> | null = null;

/** Vrai tant qu'un `Interceptor` est posé. `lineup-lire` le consulte pour refuser d'INVOQUER la
 *  méthode qu'on ancre. */
export function estArme(): boolean {
    return listener !== null;
}

/**
 * L'ACCESSEUR DU SECOND CONSOMMATEUR — pour le chemin des BUFFS, au `LoadBattle.onLeave`.
 *
 * `classeSource` est le nom de classe de la source (celui que `class_get_name` rend sur
 * l'instance). Rend `null` quand aucune composition n'est retenue pour ce mode : l'appelant doit
 * alors DEMANDER À LA SOURCE, pas supposer une liste vide.
 */
export function compositionRetenue(classeSource: string | null): CompositionRetenue | null {
    if (classeSource === null) return null;
    const c = registre.get(classeSource);
    return c !== undefined && c.confirme ? c : null;
}

/** Lit un `System.String` géré. Même convention que `game/source-lineup.ts`. */
function chaineGeree(p: NativePointer): string | null {
    if (p.isNull()) return null;
    try { return p.add(0x14).readUtf16String(); } catch { return null; }
}

let baseModule: string | null = null;
function baseGameAssembly(): string | null {
    if (baseModule !== null) return baseModule;
    try {
        const m = Process.findModuleByName("GameAssembly.dll");
        baseModule = m ? m.base.toString() : null;
    } catch { baseModule = null; }
    return baseModule;
}

/** LA PILE, EN ADRESSES BRUTES. `FUZZY` comme `stack-sample` : `ACCURATE` s'appuie sur des
 *  prologues que le code IL2CPP optimisé ne présente pas toujours. */
function pileBrute(contexte: CpuContext): string[] | null {
    try {
        return Thread.backtrace(contexte, Backtracer.FUZZY).slice(0, 12).map((p) => p.toString());
    } catch { return null; }
}

function lireTableau(arr: NativePointer, contexte?: CpuContext): Observation {
    let classeRetour: string | null = null;
    try { classeRetour = cstr(class_get_name(arr.readPointer()) as NativePointer); } catch { /* nul */ }
    let longueur: number | null = null;
    try { longueur = arr.add(OFF_LONGUEUR).readS32(); } catch { /* nul */ }
    const pile = contexte ? pileBrute(contexte) : null;
    const base = baseGameAssembly();
    if (longueur === null || longueur < 0 || longueur > PLAFOND_PLACES) {
        return { classeRetour, longueur, avant: null, pile, base };
    }
    const avant: string[] = [];
    for (let i = 0; i < longueur; i++) {
        try {
            avant.push(chaineGeree(arr.add(OFF_ELEMENTS + i * Process.pointerSize).readPointer())
                ?? "<illisible>");
        } catch { avant.push("<illisible>"); }
    }
    return { classeRetour, longueur, avant, pile, base };
}

/** L'ÉCRITURE. N'est appelée qu'après une observation qui a établi classe ET longueur. */
function poser(arr: NativePointer, obs: Observation, ids: string[]): Record<string, unknown> {
    const n = obs.longueur as number;
    const combien = Math.min(n, ids.length);
    const ecrits: string[] = [];
    for (let i = 0; i < combien; i++) {
        const s = createManagedString(ids[i]);
        // ENRACINER D'ABORD : entre la fabrication et l'écriture, la chaîne n'est référencée par
        // rien de managé.
        gcRoot.add(s);
        arr.add(OFF_ELEMENTS + i * Process.pointerSize).writePointer(s);
        ecrits.push(ids[i]);
    }
    return {
        ecrits, combien, placesDuTableau: n, idsFournis: ids.length,
        tronque: ids.length > n,
        // Les cases NON réécrites gardent l'id d'origine : on le DIT, sinon une composition
        // partielle se lirait comme une composition complète.
        restantesInchangees: n > combien ? (obs.avant ?? []).slice(combien) : [],
    };
}

function armer(mode: string): Record<string, unknown> {
    const nomClasse = CLASSES[mode];
    if (nomClasse === undefined) {
        return { ok: false, refus: `mode inconnu \`${mode}\` -- connus : ${Object.keys(CLASSES).join(", ")}` };
    }
    const k = findClassAnywhere(NS_SRC, nomClasse);
    if (!k) return { ok: false, refus: `${NS_SRC}.${nomClasse} INTROUVABLE sur ce build` };
    const mi = findMethodByParamCount(k, "GetBattleLineup", 1);
    if (!mi) return { ok: false, refus: `\`${nomClasse}$$GetBattleLineup(1 param)\` INTROUVABLE` };

    listener = Interceptor.attach(mi.ptr, {
        onLeave(retval: InvocationReturnValue) {
            fires++;
            const arr = retval as unknown as NativePointer;
            if (arr.isNull()) return;
            const obs = lireTableau(arr, this.context);
            if (observations.length < 12) observations.push(obs);
            const retenue = compositionRetenue(classeArmee);
            if (retenue === null) return;
            if (obs.classeRetour === null || obs.longueur === null) return;
            if (obs.longueur > PLAFOND_PLACES) return;
            try {
                // DEUX VOIES, et c'est la LONGUEUR RENDUE qui tranche -- pas le mode. Un retour
                // vide n'a aucune case (cf. `remplacerRetour` : en guild war c'est le singleton
                // `Array.Empty<string>()`), donc l'écriture en place n'a rien à écrire ; un retour
                // pourvu, lui, est un objet que l'appelant tient déjà, et on le préserve.
                dernierePose = obs.longueur <= 0
                    ? { ...remplacerRetour(retval, retenue.ids), voie: "remplacement",
                        fire: fires, origine: retenue.origine }
                    : { ...poser(arr, obs, retenue.ids), voie: "ecriture-en-place",
                        fire: fires, origine: retenue.origine };
            } catch (e) {
                dernierePose = { erreur: (e as Error).message, fire: fires };
            }
        },
    });
    Interceptor.flush();
    classeArmee = nomClasse;
    return { ok: true };
}

/**
 * REMPLACER LE RETOUR, quand il n'y a AUCUNE case où écrire.
 *
 * ⛔ LA VOIE « ÉCRIRE DANS LES CASES » EST STRUCTURELLEMENT IMPOSSIBLE POUR CES MODES-LÀ, et s'y
 * essayer serait un désastre silencieux. Mesuré au décompilé :
 * `GuildWarsGameModeSource$$GetBattleLineup` rend `System.Array$$Empty<string>()` -- un SINGLETON
 * PARTAGÉ PAR TOUT LE PROCESS. Il a zéro case (donc rien à remplir), et le corrompre casserait
 * tout appelant de `Array.Empty<string>()` dans le jeu, très loin d'ici. On alloue donc un tableau
 * NEUF et on substitue le retour.
 *
 * POURQUOI ÇA SUFFIT, et c'est le décompilé qui le dit --
 * `IdunBattle.View.FSM.VisualBattleQuery$$GetBattleLineupToDeploy` :
 *
 *   lineup = GetBattleLineup(MaxUnitsPossibleToStartBattle)        <- appel 1, INCONDITIONNEL
 *   if (lineup.Length < MinUnitsNeededToStartBattle) {             <- 0 < min ⇒ toujours vrai en GW
 *       n = Max; do { n--; if (n < 1) break;
 *                     lineup = GetBattleLineup(n); } while (lineup.Length == 0);
 *       ... puis COMPLÈTE depuis le pool déployable (`AddIfNotExisting`) ...
 *   }
 *
 * ⇒ répondre au PREMIER appel avec un tableau de la taille demandée fait que la branche de
 * complétion n'est JAMAIS prise, et notre composition sort verbatim. C'est aussi ce qui explique
 * l'auto-déploiement qu'on voit en jeu : ce n'est pas un défaut, c'est cette complétion.
 *
 * ⚠ ON NE REMPLACE QUE SUR UN RETOUR VIDE. Un retour non vide a des cases : `poser` y écrit, ce qui
 * préserve l'objet que l'appelant tient déjà. Remplacer dans ce cas serait un changement de
 * comportement gratuit, et on perdrait la trace de ce que le jeu voulait rendre.
 *
 * ⛔ CE CHEMIN N'A AUCUN DÉCLENCHEUR EN SANDBOX — mesuré le 2026-08-25, et c'est ce qui empêche de
 * le confronter à bon marché. Sur un montage guerre de guilde (`sandbox_mode.py start`, prêteur
 * `guildWar`, zone `Trenches1`), l'ancrage a rendu **`fires: 0`** SUR LES DEUX classes, chacune sur
 * son propre montage : `GuildWarsGameModeSource$$GetBattleLineup` d'abord, puis
 * `SandboxGameModeSource$$GetBattleLineup`. Personne ne demande de composition.
 *
 * Deux causes, toutes deux lisibles dans la recette :
 *   - la délégation du montage (`deploymentPoolArmer { source: "guildWar", only: [...] }`) ne porte
 *     que `GetUnitModel` / `GetGameModeSpecificDeploymentHudOptions` / `GetUnitsForDeploymentHUD`
 *     -- `GetBattleLineup` n'y est PAS ;
 *   - et la phase de déploiement y est FORCÉE par le lanceur (`deploymentPhaseArmer { forcer }`),
 *     donc `VisualBattleQuery$$GetBattleLineupToDeploy` -- le seul appelant qui nous intéresse --
 *     ne tourne pas.
 *
 * Conséquence mesurée du même montage : `posees = 0` et `deploymentStartInvoquer` est un NO-OP, la
 * bataille restant en `Setup`. C'est le manque même que ce chemin vise, observé en vrai.
 *
 * ⇒ CONFRONTER CE CHEMIN EXIGE UNE VRAIE BATAILLE DE GUERRE DE GUILDE (donc une tentative). Tant
 * que ce n'est pas fait, ce code est COMPILÉ et RELU, pas éprouvé -- ne pas l'écrire autrement.
 */
/** Les racines du remplacement de retour — SÉPARÉES de celles de `lineupSubstituer`, et ce n'est
 *  pas de la symétrie : les deux durées de vie n'ont rien à voir. `lineupSubstituer` libère les
 *  siennes au début de chaque substitution ; partager la liste ferait désépingler, depuis un RPC,
 *  le tableau qu'un `onLeave` vient de rendre au jeu. On libère celles du tour PRÉCÉDENT : l'appel
 *  qui les portait est retourné, et `GetBattleLineupToDeploy` écrase `lineup` à chaque tour de sa
 *  boucle décroissante -- l'ancien tableau n'est donc plus joignable. */
const racinesRetour: NativePointer[] = [];
function libererRacinesRetour(): void {
    while (racinesRetour.length > 0) {
        const p = racinesRetour.pop() as NativePointer;
        try { gcRoot.remove(p); } catch { /* handle deja parti */ }
    }
}

function remplacerRetour(
    retval: InvocationReturnValue, ids: string[],
): Record<string, unknown> {
    const kStr = findClassAnywhere("System", "String");
    if (!kStr) return { erreur: "`System.String` INTROUVABLE -- aucun remplacement" };
    const n = Math.min(ids.length, PLAFOND_PLACES);
    libererRacinesRetour();
    const arr = createManagedArray(kStr, n);
    // ENRACINER D'ABORD : le tableau n'est référencé par rien de managé tant que l'appelant ne
    // l'a pas rangé, et on le lui rend au milieu de sa propre pile.
    gcRoot.add(arr); racinesRetour.push(arr);
    for (let i = 0; i < n; i++) {
        const s = createManagedString(ids[i]);
        gcRoot.add(s); racinesRetour.push(s);
        arr.add(OFF_ELEMENTS + i * Process.pointerSize).writePointer(s);
    }
    retval.replace(arr);
    return { remplace: true, ids: ids.slice(0, n), longueurRendue: n,
             tronque: ids.length > n };
}

function etatRegistre(): Array<Record<string, unknown>> {
    return Array.from(registre.entries()).map(([classe, c]) => ({
        classe, ids: c.ids, confirme: c.confirme, origine: c.origine,
    }));
}

// --- LE CAPTEUR DE CLÉS ---------------------------------------------------------------------
//
// `UnitProgression.GetBattleLineup(lineupKey: String) -> String[]` est UN magasin à clé chaîne, et
// son écriture est `UnitProgression.SetBattleLineupLocally(lineupKey, unitIds)`. Les deux sont des
// RELAIS MINCES : ils résolvent une interface sur `this+0x30` et dispatchent son slot 7 (lire) /
// slot 5 (écrire). Le `Set` fait EN PLUS un appel sur `this+0x90` quand il est non nul -- une
// notification, non identifiée ici.
//
// ⇒ LA CLÉ ARRIVE EN ARGUMENT. On n'a donc RIEN à reconstruire ni à associer à la main : on la LIT.
// C'est ce qui rend l'écriture adressable pour un mode dont on ne connaît pas le fabricant de clé.
//
// ⚠ MAIS CE MAGASIN N'EST PAS UNIVERSEL, ET LA VERSION PRÉCÉDENTE DE CE COMMENTAIRE LE PRÉTENDAIT.
// Elle annonçait « un seul magasin, TOUS MODES CONFONDUS » et des clés « auto-descriptives
// (`<campagne>_<index>`) ». Mesuré au décompilé le 2026-08-25 (build `t6dpr4k06g`) : les deux sont
// faux. Il y a TROIS familles, et la troisième interdit ce qu'on projetait d'en faire.
//
//   (a) DÉLÈGUENT au magasin, par le slot d'interface 0x5e -- et chacune fabrique sa clé
//       AUTREMENT, donc aucune forme de clé n'est généralisable :
//         `IdunBattle.ViewLogic.BattleSource.CampaignGameModeSource$$GetBattleLineup`
//             clé = Concat(<préfixe lu sur `this+0x20`>, <littéral>, lineupIndex.ToString())
//         `IdunBattle.ViewLogic.BattleSource.PvpGameModeSource$$GetBattleLineup`
//             clé = un LITTÉRAL constant, avec repli sur un SECOND littéral si le retour est vide
//         `IdunBattle.ViewLogic.BattleSource.GuildBossGameModeSource$$GetBattleLineup`
//             clé = `thor.Client.DTO.Common.UnitsDto$$CreateGuildBossLineupKeyByFaction`, deux replis
//       Le dernier repli de PvP et celui de guild boss sont LE MÊME littéral -- il y a donc une
//       composition « par défaut » partagée. Le repli se déclenche sur `longueur == 0` lue en
//       `+0x18`, la même que `OFF_LONGUEUR` ci-dessus.
//
//   (b) A SA PROPRE SOURCE, sans clé ni magasin :
//         `IdunBattle.ViewLogic.BattleSource.MachinesOfWarEventGameModeSource$$GetBattleLineup`
//             lit un `List<string>` par le slot d'interface 0x2b, puis `ToArray()`.
//       ⇒ le capteur ne verra JAMAIS passer de clé pour la MoW. Son silence n'est pas une panne.
//
//   (c) N'ONT RIEN DU TOUT -- le corps natif est un talon constant :
//         `IdunBattle.ViewLogic.BattleSource.GuildWarsGameModeSource$$GetBattleLineup` -> `Array.Empty<string>()`
//         `IdunBattle.ViewLogic.BattleSource.SandboxGameModeSource$$GetBattleLineup`   -> `new string[0]`
//       ⇒ pour la GUILD WAR et la SANDBOX, il n'existe AUCUNE clé sous laquelle écrire. Le registre
//       en mémoire + l'ancrage de ce module ne sont pas un repli faute de mieux : ils sont la SEULE
//       voie. C'était la question ouverte (« les modes qui n'ont pas la feature, comment faire ? ») ;
//       la réponse est qu'il n'y a rien à trouver côté jeu.
//       ⚠ Et la « délégation » de la sandbox vers la source réelle est LA NÔTRE (`deployment-draft`),
//       pas celle du jeu : le natif, seul, rend un tableau vide.
//
// ⚠ ET LE PARAMÈTRE DE LA VOIE CAMPAGNE SERT DEUX FOIS -- ce qui dissout l'« ambiguïté index vs
// taille » au lieu de la trancher. Le même entier est (1) concaténé dans la clé, et (2) passé en
// `amountOfUnitsToBring` à
// `IdunBattle.ViewLogic.BattleSource.LineupHelper$$GetCampaignBattleLineupUsingRequiredUnits`, qui
// s'en sert comme seuil puis comme `Take(n)`. Les deux lectures étaient JUSTES. Conséquence à ne
// pas rater : demander `n` places lit la clé `<préfixe><sép><n>` -- il y a donc une composition
// sauvegardée PAR TAILLE, et écrire sous la mauvaise taille n'écrase rien de visible.
//
// ⚠ RÉ-ENTRANCE, ET ELLE EST ASSUMÉE PLUTÔT QUE TUE. `lineupSource` invoque
// `<Source>$$GetBattleLineup`, qui appelle CETTE méthode : notre handler se déclenche donc au
// milieu de notre propre invoke. Ce n'est PAS le cas interdit (« ancrer la méthode qu'on
// invoque ») -- c'est un cran en dessous -- et la contre-épreuve #10041 a vu 12 ancrages armés,
// dont la méthode invoquée elle-même, revenir 6/6 sans geler. On l'autorise donc, mais le corps
// du handler est réduit au strict minimum : lire une chaîne, ranger. AUCUN invoke dedans.

const NS_PROG = "IdunMetaLogic.UserProgress";
const CLS_PROG = "UnitProgression";

/**
 * LES CLÉS LITTÉRALES, RÉSOLUES HORS LIGNE — pas devinées, et c'est la différence qui compte.
 *
 * Chacune est le CONTENU du slot de cache de littéral cité au décompilé, lu dans
 * `data/symbols/<build>/metadata/string_literals.tsv` (format `index \t rva_du_slot \t "texte"`,
 * `image_base=0x180000000`, donc `DAT_1833a5af0` -> rva `0x33a5af0`).
 *
 * ⚠ LA MÉTHODE SE VÉRIFIE PAR UN TÉMOIN, sinon on apparie deux tables au hasard : le slot
 * `0x3388910`, que le décompilé de
 * `IdunBattle.ViewLogic.BattleSource.LineupHelper$$GetCampaignBattleLineupUsingRequiredUnits`
 * charge comme littéral, rend `""` dans la table. L'appariement `DAT_` <-> table tient.
 *
 * ⚠ VRAIES POUR CE BUILD SEULEMENT. Un contenu de métadonnées n'est pas un symbole : les noms
 * survivent au changement de hash, pas les littéraux ni leur emplacement. Les RE-DÉRIVER.
 */
const CLES_LITTERALES: Readonly<Record<string, string>> = {
    // `PvpGameModeSource$$GetBattleLineup` -- clé principale.
    pvp: "pvp",
    // `GuildBossGameModeSource$$GetBattleLineup` -- PREMIER repli (le second est `defautPartage`).
    guildBossRepli: "gb",
    // DERNIER repli de PvP *ET* de guild boss : la composition « par défaut » du compte.
    defautPartage: "5",
};

/** Le séparateur de la clé campagne : `<campaignId>` + ceci + `<nombre de places>`. Concaténé par
 *  `CampaignGameModeSource$$GetBattleLineup` via `System.String$$Concat`. */
const SEP_CAMPAGNE = "_";

interface VueDeCle {
    vues: number;
    derniereLongueur: number | null;
    dernierContenu: string[] | null;
}

let ecouteCles: InvocationListener | null = null;
const catalogue = new Map<string, VueDeCle>();
let firesCles = 0;

/** La clé du dernier combat vu passer. `null` = aucune observée -- JAMAIS une chaîne vide. */
let derniereCle: string | null = null;

/**
 * L'INSTANCE DU MAGASIN, cueillie sur `args[0]` du même passage que la clé.
 *
 * ⚠ ELLE VIENT DE LÀ, ET PAS D'UN CHAMP DE SOURCE, PARCE QUE L'OFFSET N'EST PAS LE MÊME D'UN MODE
 * À L'AUTRE : campagne `+0x28`, PvP `+0x88`, guild boss `+0x98`. Trois offsets pour un seul objet
 * -- les coder en dur ferait trois occasions de lire à côté. Le `this` de l'appel, lui, EST
 * l'instance, quel que soit le mode qui l'a atteinte.
 *
 * ⚠ ÉPINGLÉE (`gcRoot`) et REMPLAÇANTE : on désépingle la précédente. Sans l'épingle on garderait
 * un pointeur vers un objet potentiellement recyclé, et le relire pour le valider serait déjà
 * l'utiliser. Une seule épingle à la fois -- pas de fuite de handles.
 */
let magasin: NativePointer | null = null;

function retenirMagasin(p: NativePointer): void {
    if (p.isNull()) return;
    if (magasin !== null && magasin.equals(p)) return;
    try { if (magasin !== null) gcRoot.remove(magasin); } catch { /* handle deja parti */ }
    try { gcRoot.add(p); magasin = p; } catch { magasin = null; }
}

/** Les objets managés fabriqués pour la DERNIÈRE substitution, épinglés le temps de l'appel natif
 *  et libérés au début de la suivante. Bornées par construction : une substitution à la fois. */
const racines: NativePointer[] = [];
function libererRacines(): void {
    while (racines.length > 0) {
        const p = racines.pop() as NativePointer;
        try { gcRoot.remove(p); } catch { /* handle deja parti */ }
    }
}

/** Ce qu'on a écrit en dernier, pour que la relecture puisse se confronter à une INTENTION.
 *  `null` = aucune substitution -- donc une relecture ne prouve rien sur nous. */
let derniereSubstitution: { cle: string; unites: string[]; origine: string } | null = null;

/** Exporté pour le RPC de substitution : sans clé observée, on n'écrit nulle part. */
export function cleObservee(): string | null {
    return derniereCle;
}

/** `null` = le magasin n'a JAMAIS été vu passer -- pas « absent du jeu ». */
export function magasinObserve(): NativePointer | null {
    return magasin;
}

/**
 * LE MAGASIN UTILISABLE, et D'OÙ il vient — deux sources, par ordre d'autorité DÉCROISSANTE.
 *
 * 1. `capteur` — le `this` de l'appel lui-même. Rien ne peut être plus juste : c'est l'objet sur
 *    lequel le jeu VIENT d'appeler la méthode.
 * 2. `amorce` — `IdunNavigation._unitProgression`, capté par `autoBootExtraire` au moment de
 *    l'inject.
 *
 * ⚠ LA SECONDE EXISTE PARCE QUE LA PREMIÈRE EXIGE UNE BATAILLE, et c'est ce qui bloquait tout :
 * mesuré le 2026-08-25, le capteur armé sur une session montée APRÈS le chargement d'une bataille
 * rend `fires: 0` indéfiniment -- la source du mode n'ayant pas été captée non plus, il n'existait
 * AUCUN chemin vers le magasin. L'amorce, elle, le publie à chaque inject, sans bataille et sans
 * navigation. Ce n'est pas un repli dégradé : c'est la voie NORMALE.
 *
 * ⚠ LA SOURCE EST RENDUE AVEC LE POINTEUR, jamais tue. Les deux ne sont pas interchangeables si le
 * jeu venait à porter plusieurs instances -- et un lecteur qui ne sait pas d'où vient l'objet ne
 * peut pas juger ce qu'il lit.
 */
function magasinUtilisable(): { ptr: NativePointer; source: string } | null {
    if (magasin !== null && !magasin.isNull()) return { ptr: magasin, source: "capteur" };
    let p: NativePointer | null = null;
    try { p = getUnitProgressionPtr(); } catch { p = null; }
    if (p !== null && !p.isNull()) return { ptr: p, source: "amorce" };
    return null;
}

/**
 * ÉCRIRE AU MAGASIN — LE FOYER UNIQUE. Deux appelants : le RPC `lineupSubstituer` et le commit de
 * retraite. Un second chemin d'écriture serait un second endroit où oublier d'enraciner.
 *
 * ⛔ NE S'ENVELOPPE PAS DANS `queueOnMainThread` — c'est l'APPELANT qui décide. Le RPC arrive sur
 * un autre thread et doit passer par la file ; le commit de retraite, lui, tourne DÉJÀ sur le
 * thread principal (il est dans un `Interceptor`), et l'y remettre le ferait exécuter par une
 * pompe qui vit dans `IdunGameViews$$Update` -- donc APRÈS le démontage de la scène de bataille,
 * c'est-à-dire peut-être jamais.
 */
function ecrireAuMagasin(
    cle: string, unites: string[], origine: string,
): Record<string, unknown> {
    const mag = magasinUtilisable();
    if (mag === null) {
        return { ok: false,
            refus: "aucune instance de magasin -- NI vue passer par le capteur, NI publiée par "
                + "l'amorce (`IdunNavigation._unitProgression`). Ce n'est pas « absent du jeu » : "
                + "rejouer `POST /api/admin/amorce`, qui la capte sans bataille." };
    }
    const commun = { cle, unites: unites.slice(),
                     magasin: mag.ptr.toString(), magasinSource: mag.source };
    const k = findClassAnywhere(NS_PROG, CLS_PROG);
    if (!k) return { ok: false, ...commun, refus: `${NS_PROG}.${CLS_PROG} INTROUVABLE` };
    const mi = findMethodByParamCount(k, "SetBattleLineupLocally", 2);
    if (!mi) {
        return { ok: false, ...commun,
                 refus: "`SetBattleLineupLocally(2 params)` INTROUVABLE sur ce build" };
    }
    const kStr = findClassAnywhere("System", "String");
    if (!kStr) return { ok: false, ...commun, refus: "`System.String` INTROUVABLE" };

    // Les racines du tour PRÉCÉDENT se libèrent MAINTENANT, pas après l'appel : une fois la
    // composition rangée par le natif, c'est du managé qui la référence. Garder nos épingles
    // ferait fuir un handle par substitution.
    libererRacines();
    let arr: NativePointer;
    try {
        arr = createManagedArray(kStr, unites.length);
        gcRoot.add(arr); racines.push(arr);
        for (let i = 0; i < unites.length; i++) {
            const s = createManagedString(unites[i]);
            gcRoot.add(s); racines.push(s);   // ENRACINER D'ABORD, écrire ensuite
            arr.add(OFF_ELEMENTS + i * Process.pointerSize).writePointer(s);
        }
    } catch (e) {
        return { ok: false, ...commun,
                 refus: `fabrication du String[] : ${(e as Error).message}` };
    }
    try {
        const cleGeree = createManagedString(cle);
        gcRoot.add(cleGeree); racines.push(cleGeree);
        // `propagate` : appel MANAGÉ, cf. `il2cpp/invoke.ts`. Sans lui Frida confisque
        // l'exception C++ par laquelle IL2CPP la transporte.
        const fn = new NativeFunction(
            mi.ptr, "void", ["pointer", "pointer", "pointer", "pointer"],
            { exceptions: "propagate" });
        fn(mag.ptr, cleGeree, arr, mi.info);
    } catch (e) {
        return { ok: false, ...commun,
                 refus: `\`SetBattleLineupLocally\` a levé : ${(e as Error).message}` };
    }
    derniereSubstitution = { cle, unites: unites.slice(), origine };
    return { ok: true, ecrit: true, ...commun };
}

function armerCles(): Record<string, unknown> {
    const k = findClassAnywhere(NS_PROG, CLS_PROG);
    if (!k) return { ok: false, refus: `${NS_PROG}.${CLS_PROG} INTROUVABLE sur ce build` };
    const mi = findMethodByParamCount(k, "GetBattleLineup", 1);
    if (!mi) return { ok: false, refus: `\`${CLS_PROG}$$GetBattleLineup(1 param)\` INTROUVABLE` };
    ecouteCles = Interceptor.attach(mi.ptr, {
        onEnter(args: InvocationArguments) {
            firesCles++;
            try {
                retenirMagasin(args[0] as NativePointer);   // `this` = l'instance du magasin
            } catch { /* pas d'epingle ne doit pas faire tomber le jeu */ }
            try {
                const p = args[1] as NativePointer;   // args[0] = `this`
                const cle = p.isNull() ? null : p.add(0x14).readUtf16String();
                if (cle !== null && cle.length > 0) {
                    derniereCle = cle;
                    (this as unknown as { _cle: string })._cle = cle;
                }
            } catch { /* une clé illisible ne doit pas faire tomber le jeu */ }
        },
        onLeave(retval: InvocationReturnValue) {
            let cle: string | null = null;
            try { cle = (this as unknown as { _cle?: string })._cle ?? null; } catch { /* nul */ }
            if (cle === null) return;
            let longueur: number | null = null;
            let contenu: string[] | null = null;
            try {
                const arr = retval as unknown as NativePointer;
                if (!arr.isNull()) {
                    longueur = arr.add(OFF_LONGUEUR).readS32();
                    if (longueur !== null && longueur >= 0 && longueur <= PLAFOND_PLACES) {
                        contenu = [];
                        for (let i = 0; i < longueur; i++) {
                            contenu.push(chaineGeree(
                                arr.add(OFF_ELEMENTS + i * Process.pointerSize).readPointer())
                                ?? "<illisible>");
                        }
                    }
                }
            } catch { /* un retour illisible se DIT par `null`, il ne s'invente pas */ }
            const v = catalogue.get(cle);
            catalogue.set(cle, {
                vues: (v?.vues ?? 0) + 1,
                derniereLongueur: longueur,
                dernierContenu: contenu,
            });
        },
    });
    Interceptor.flush();
    return { ok: true };
}

// --- LE COMMIT PAR LA RETRAITE ----------------------------------------------------------------
//
// LE GESTE : en sandbox, on sort par la retraite. « J'ai fini d'arranger cette équipe, garde-la »
// se pose donc dessus, sans rien créer ni rien confisquer.
//
// ⛔ POURQUOI PAS UN VRAI BOUTON UNITY. Ce dépôt n'a jamais créé d'UI, et `il2cpp/delegate.ts`
// REFUSE délibérément les callbacks JS (« y mettre un `NativeCallback` ferait entrer Frida dans
// QuickJS ») : il ne fabrique que des délégués INERTES, qu'il faut ensuite sonder. Un `onClick`
// qui rappelle notre code est donc précisément ce qu'on s'interdit ici.
//
// L'ANCRE : `IdunBattle.ViewLogic.BattleSource.SandboxGameModeSource$$HandleBattleSurrender`.
//
// ⚠ ET ELLE A ÉTÉ CHOISIE APRÈS LE CONTRÔLE DE DÉDUPLICATION, pas avant. Son corps est un relais
// trivial (un seul appel de slot), donc exactement le profil qu'IL2CPP fusionne entre classes --
// et un corps partagé ferait tirer cet ancrage sur des batailles RÉELLES. Mesuré sur
// `frida/methods.tsv` : `HandleBattleSurrender` occupe **12 adresses DISTINCTES**, une par mode.
// Aucune fusion, l'ancrage est bien propre à la sandbox.
//
// ⚠ `onEnter` SEUL, ET C'EST UN LISTENER NEUF. Ajouter un `onEnter` à un listener qui n'a qu'un
// `onLeave` fait CESSER son tir, en silence -- mesuré deux fois dans ce dépôt, sur deux listeners
// indépendants. Ici il n'y a pas d'`onLeave` à préserver : on attache un listener à nous.
//
// ⚠ ON ÉCRIT DANS LE HANDLER, ON NE DIFFÈRE PAS. `queueOnMainThread` fait exécuter par la pompe de
// `IdunGameViews$$Update` -- qui MEURT avec la scène de bataille. Différer depuis une retraite,
// c'est risquer que la substitution ne s'exécute jamais. À l'ENTRÉE de ce natif, rien n'est encore
// démonté (son corps ne fait que relayer), et l'écriture ne touche que le magasin de progression.
//
// ⚠ `retreat-capture` N'ANCRE PAS cette méthode (il prend `OnBattleSurrender` / `ContinueSurrender`
// / `ProcessFinishSurrender` / `ProcessFinishBattle` / `OnFinishBattle` sur `IdunMainView`, et
// `PauseSurrender` sur `AGameModeSource` / `CampaignGameModeSource`). Pas de double attache.
//
// CONFRONTÉ EN LIVE le 2026-08-25, sandbox guild boss (`GuildBoss1Boss1TyranTervigonLeviathan`),
// bataille DÉMARRÉE puis quittée par `retreatInvoke OnBattleSurrender` :
//
//     equipesVues   ["1","2"]        equipeRetenue "1"
//     parEquipe     1 -> admecRuststalker, admecDominus, tauMarksman, admecManipulus, admecMarshall
//                   2 -> GuildBoss1Boss1TyranTervigonLeviathan
//     registre      GuildBossGameModeSource <- les 5, origine "retraite sandbox"
//
// La composition du joueur est retenue, l'adversaire écarté, et la sortie est propre
// (`sandboxProbe.instance` vide, jeu vivant).
//
// ⛔ ET IL FAUT SORTIR D'UNE BATAILLE **DÉMARRÉE**, PAS DE LA PHASE DE DÉPLOIEMENT. Deux crashs du
// jeu, le même jour, sur des retraites depuis `Setup` (une en sandbox, une en campagne réelle) ;
// la même retraite depuis `Running` -- la sortie que `tacticus-sandbox` documente -- passe sans
// incident. La cause exacte n'est PAS établie : le refus posé plus bas vise le contenu retenu
// (l'état ne porte que l'adversaire en `Setup`), et il se trouve qu'il écarte aussi la géométrie
// où l'on a crashé. Ne pas lire ce refus comme une parade au crash : il n'a pas été éprouvé comme
// telle.

const CLS_SANDBOX = "SandboxGameModeSource";
const METHODE_RETRAITE = "HandleBattleSurrender";

interface CibleCommit { cle: string | null; mode: string | null; equipe: number | null; }

let ecouteRetraite: InvocationListener | null = null;
let cibleCommit: CibleCommit | null = null;
let firesRetraite = 0;
let commitDejaTire = false;
let dernierCommit: Record<string, unknown> | null = null;

/** Les compositions LUES sur l'état de match, par équipe. En sandbox le jeu est en HOTSEAT : les
 *  DEUX camps sont jouables, donc « la composition du joueur » n'a pas de sens tout seul -- on rend
 *  les deux et on DIT laquelle a été retenue. */
function compositionsParEquipe(
    statePtr: NativePointer,
): { parEquipe: Record<string, string[]>; stage?: string | null; refus: string | null } {
    let nomClasse: string | null = null;
    try { nomClasse = cstr(class_get_name(statePtr.readPointer()) as NativePointer); }
    catch { nomClasse = null; }
    // Les offsets de `projectMatchState` sont ceux de `MatchState`. Sur un autre objet ils
    // liraient du bruit -- et un bruit plausible est pire qu'un refus.
    if (nomClasse === null || !nomClasse.includes("MatchState")) {
        return { parEquipe: {},
                 refus: `l'argument d'état n'est pas un \`MatchState\` (lu : ${nomClasse ?? "illisible"})` };
    }
    // ⛔ LE REFUS SUR `Setup`, ET IL EST MESURÉ -- pas prudentiel. Confronté le 2026-08-25 sur une
    // sandbox guild boss : retraiter depuis la phase de déploiement a fait retenir
    // `["GuildBoss1Boss1TyranTervigonLeviathan"]` comme composition du joueur, et RIEN ne l'a
    // arrêté. La cause : en `Setup` les unités du joueur sont encore des `PlaceholderUnitView`,
    // que le START natif convertit -- elles n'existent PAS comme entités, donc `projectMatchState`
    // ne voit que l'adversaire. Sur une cible `cle`, ce tir aurait rangé l'id du BOSS dans le
    // magasin du joueur, sans lever quoi que ce soit.
    // (La voie `deploymentCommit`, qui posait des unités RÉELLES en `Setup`, a été supprimée le
    // 2026-08-21 : toute pose passe désormais par l'étage FSM. Il n'y a donc plus aucun régime où
    // lire l'état en `Setup` rendrait la composition du joueur.)
    const statut = readBattleStatus(statePtr);
    if (statut.stage === null) {
        return { parEquipe: {}, stage: null,
                 refus: "stage de bataille NON LU -- on ne retient rien sur un état qu'on ne "
                      + "sait pas qualifier" };
    }
    if (statut.stage <= 0) {
        return { parEquipe: {}, stage: statut.stageName,
                 refus: `bataille en \`${statut.stageName}\` : les unités du joueur sont encore `
                      + "des placeholders, l'état ne porte que l'adversaire. Démarrer la bataille "
                      + "AVANT de retraiter -- sinon on retiendrait la composition ENNEMIE." };
    }
    const parEquipe: Record<string, string[]> = {};
    const proj = projectMatchState(statePtr);
    for (const u of proj.units) {
        if (u.visualId === null || u.isDead) continue;
        const k = String(u.teamId);
        if (parEquipe[k] === undefined) parEquipe[k] = [];
        if (!parEquipe[k].includes(u.visualId)) parEquipe[k].push(u.visualId);
    }
    return { parEquipe, stage: statut.stageName, refus: null };
}

function armerRetraite(): Record<string, unknown> {
    const k = findClassAnywhere(NS_SRC, CLS_SANDBOX);
    if (!k) return { ok: false, refus: `${NS_SRC}.${CLS_SANDBOX} INTROUVABLE sur ce build` };
    const mi = findMethodByParamCount(k, METHODE_RETRAITE, 9);
    if (!mi) {
        return { ok: false,
                 refus: `\`${CLS_SANDBOX}$$${METHODE_RETRAITE}(9 params)\` INTROUVABLE` };
    }
    ecouteRetraite = Interceptor.attach(mi.ptr, {
        onEnter(args: InvocationArguments) {
            firesRetraite++;
            const cible = cibleCommit;
            if (cible === null || commitDejaTire) return;
            try {
                // args[0] = `this`, args[1] = `state: IMatchState`.
                const lu = compositionsParEquipe(args[1] as NativePointer);
                if (lu.refus !== null) {
                    // ⚠ ON NE VERROUILLE PAS SUR UN REFUS : le tir suivant (une retraite depuis
                    // une bataille DÉMARRÉE, cette fois) doit encore pouvoir commiter.
                    dernierCommit = { ok: false, refus: lu.refus,
                                      stage: lu.stage ?? null, fire: firesRetraite };
                    return;
                }
                const equipes = Object.keys(lu.parEquipe).sort();
                if (equipes.length === 0) {
                    dernierCommit = { ok: false, fire: firesRetraite,
                        refus: "aucune unité vivante lue sur l'état -- rien à retenir" };
                    return;
                }
                const choisie = cible.equipe !== null ? String(cible.equipe) : equipes[0];
                const ids = lu.parEquipe[choisie];
                if (ids === undefined || ids.length === 0) {
                    dernierCommit = { ok: false, fire: firesRetraite,
                        equipesVues: equipes, parEquipe: lu.parEquipe,
                        refus: `aucune unité pour l'équipe ${choisie}` };
                    return;
                }
                // UN SEUL TIR : on ne détache pas depuis le handler (retirer un `Interceptor`
                // pendant qu'il s'exécute est un geste qu'on ne veut pas parier), on VERROUILLE.
                commitDejaTire = true;
                const commun = { fire: firesRetraite, equipeRetenue: choisie,
                                 equipesVues: equipes, parEquipe: lu.parEquipe };
                if (cible.cle !== null) {
                    dernierCommit = { ...commun, voie: "magasin",
                                      ...ecrireAuMagasin(cible.cle, ids, "retraite sandbox") };
                } else {
                    const nomClasse = CLASSES[cible.mode as string];
                    registre.set(nomClasse, {
                        ids: ids.slice(), confirme: true, origine: "retraite sandbox",
                    });
                    dernierCommit = { ...commun, ok: true, voie: "registre",
                                      classe: nomClasse, ids: ids.slice() };
                }
            } catch (e) {
                dernierCommit = { ok: false, fire: firesRetraite,
                                  erreur: (e as Error).message };
            }
        },
    });
    Interceptor.flush();
    return { ok: true };
}

export function register(ctx: Ctx): void {
    /** Le CATALOGUE des clés du magasin de compositions. Lecture pure, aucun invoke. */
    ctx.rpc.lineupClesArmer = (body?: { armer?: boolean }): Promise<unknown> | unknown => {
        const etat = (): Record<string, unknown> => ({
            arme: ecouteCles !== null, fires: firesCles, derniereCle,
            magasin: magasin === null ? null : magasin.toString(),
            magasinSource: magasinUtilisable()?.source ?? null,
            // Publiées ici pour qu'un appelant n'ait RIEN à deviner : ce sont les clés que le
            // natif utilise, résolues hors ligne. Cf. `CLES_LITTERALES`.
            clesLitterales: CLES_LITTERALES, sepCampagne: SEP_CAMPAGNE,
            catalogue: Array.from(catalogue.entries()).map(([cle, v]) => ({
                cle, vues: v.vues, longueur: v.derniereLongueur, contenu: v.dernierContenu,
            })),
        });
        if (!body || body.armer === undefined) {
            return { ok: true, lecture: true, ...etat(),
                     note: "`{ armer: true }` pour capturer les clés du magasin "
                         + "`UnitProgression$$GetBattleLineup` -- lecture pure" };
        }
        return queueOnMainThread(() => {
            if (body.armer === false) {
                if (ecouteCles) { ecouteCles.detach(); Interceptor.flush(); ecouteCles = null; }
                return { ok: true, arme: false, action: "retire", fires: firesCles };
            }
            if (ecouteCles !== null) return { ok: true, ...etat(), note: "déjà armé" };
            const r = armerCles();
            if (r.ok !== true) return r;
            return { ok: true, ...etat(),
                     ancrage: `${NS_PROG}.${CLS_PROG}$$GetBattleLineup`,
                     note: "armé -- ouvrir une bataille (ou une sandbox à délégation armée) "
                         + "pour voir passer les clés" };
        });
    };

    /**
     * `lineupSubstituer { cle?, unites, confirmer?, origine? }` — L'ÉCRITURE DANS LE MAGASIN.
     *
     * ⚠ CELLE-CI EST PERSISTANTE, contrairement à `lineupPoserUnites`. On n'écrit plus dans le
     * `String[]` d'un appel en cours -- on appelle
     * `IdunMetaLogic.UserProgress.UnitProgression$$SetBattleLineupLocally`, qui range la
     * composition dans le magasin du joueur. Elle DEVIENT donc la composition par défaut du jeu
     * pour cette clé, y compris après désarmement et hors de nos hooks. C'est ce qui était demandé,
     * mais ça ne s'annule pas tout seul : le dry-run est le défaut, `confirmer: true` est explicite.
     *
     * ⚠ NE COUVRE PAS guild war ni sandbox : leur natif ne lit AUCUN magasin (talon constant, cf.
     * l'en-tête du capteur). Pour ces deux-là c'est `lineupPoserUnites` -- registre + ancrage.
     */
    ctx.rpc.lineupSubstituer = (body?: {
        cle?: string; unites?: string[]; confirmer?: boolean; origine?: string;
    }): Promise<unknown> | unknown => {
        const unites = body?.unites;
        if (!Array.isArray(unites) || unites.length === 0
            || unites.some((u) => typeof u !== "string" || u.length === 0)) {
            return { ok: false, refus: "`unites` doit être un tableau NON VIDE de chaînes non vides" };
        }
        if (unites.length > PLAFOND_PLACES) {
            return { ok: false,
                refus: `${unites.length} unités demandées, plafond ${PLAFOND_PLACES}` };
        }
        const cle = body?.cle ?? derniereCle;
        if (cle === null || cle === undefined || cle.length === 0) {
            return { ok: false,
                refus: "aucune clé -- ni fournie, ni OBSERVÉE. Ce n'est PAS « ce mode n'en a pas » : "
                    + "armer `lineupClesArmer { armer: true }`, puis ouvrir l'écran du mode pour la "
                    + "voir passer. Guild war et sandbox, eux, n'ont AUCUNE clé par construction "
                    + "-- pour ceux-là, `lineupPoserUnites`." };
        }
        const mag = magasinUtilisable();
        const store = mag === null ? null : mag.ptr;
        const vue = catalogue.get(cle) ?? null;
        const apercu: Record<string, unknown> = {
            cle, unites, placesDemandees: unites.length,
            magasin: store === null ? null : store.toString(),
            magasinSource: mag === null ? null : mag.source,
            connuAuCatalogue: vue !== null,
            // Ce que le magasin rendait la DERNIÈRE fois qu'on l'a vu passer. `null` = jamais vu
            // pour CETTE clé -- pas « composition vide ».
            contenuObserve: vue?.dernierContenu ?? null,
            longueurObservee: vue?.derniereLongueur ?? null,
        };
        if (store === null) {
            return { ok: false, ...apercu,
                refus: "aucune instance de magasin -- NI vue passer par le capteur, NI publiée par "
                    + "l'amorce (`IdunNavigation._unitProgression`). Ce n'est pas « absent du "
                    + "jeu » : rejouer `POST /api/admin/amorce`, qui la capte sans bataille." };
        }
        if (body?.confirmer !== true) {
            return { ok: true, ecrit: false, dryRun: true, ...apercu,
                note: "RIEN n'a été écrit. Rejouer avec `{ confirmer: true }`. ⚠ l'écriture est "
                    + "PERSISTANTE : la composition devient celle du jeu pour cette clé." };
        }
        // Le RPC arrive sur un AUTRE thread que celui d'Unity : c'est LUI qui doit passer par la
        // file. Le foyer, lui, n'en sait rien -- l'autre appelant (le commit de retraite) y est
        // déjà.
        return queueOnMainThread(() => {
            const r = ecrireAuMagasin(cle, unites, body?.origine ?? "lineupSubstituer");
            if (r.ok !== true) return { ...apercu, ...r };
            return { ...apercu, ...r,
                // ⚠ TRI-ÉTAT : on n'a PAS relu. Relire invoquerait `GetBattleLineup`, que le
                // capteur ANCRE -- exactement le cas interdit. `lineupMagasinLire` le fait, une
                // fois le capteur désarmé.
                verification: null,
                note: "écrit. NON RELU : relire invoquerait la méthode que le capteur ancre. "
                    + "Pour vérifier -- `lineupClesArmer { armer: false }` puis "
                    + "`lineupMagasinLire { cle }`." };
        });
    };

    /**
     * `lineupMagasinLire { cle? }` — RELECTURE du magasin, pour vérifier une substitution.
     *
     * ⛔ REFUSE tant que le capteur est armé : ce RPC INVOQUE
     * `IdunMetaLogic.UserProgress.UnitProgression$$GetBattleLineup`, que le capteur ANCRE. C'est le
     * cas interdit du dépôt (« ne pas ancrer ce qu'on invoque »), pas le cran en dessous qui, lui,
     * est assumé plus haut. Même idiome de verrou que `lineup-lire` face à `estArme()`.
     */
    ctx.rpc.lineupMagasinLire = (body?: { cle?: string }): Promise<unknown> | unknown => {
        if (ecouteCles !== null) {
            return { ok: false,
                refus: "le capteur de clés est ARMÉ sur `GetBattleLineup` -- lire l'invoquerait, "
                    + "donc on retomberait dans notre propre trampoline (gel). Désarmer d'abord : "
                    + "`lineupClesArmer { armer: false }`." };
        }
        const cle = body?.cle ?? derniereCle;
        if (cle === null || cle === undefined || cle.length === 0) {
            return { ok: false, refus: "aucune clé -- ni fournie, ni observée." };
        }
        const mag = magasinUtilisable();
        if (mag === null) {
            return { ok: false, cle,
                refus: "aucune instance de magasin -- NI capteur, NI amorce. Rejouer "
                    + "`POST /api/admin/amorce`, qui la capte sans bataille." };
        }
        const store = mag.ptr;
        return queueOnMainThread(() => {
            const k = findClassAnywhere(NS_PROG, CLS_PROG);
            if (!k) return { ok: false, cle, refus: `${NS_PROG}.${CLS_PROG} INTROUVABLE` };
            const mi = findMethodByParamCount(k, "GetBattleLineup", 1);
            if (!mi) return { ok: false, cle, refus: "`GetBattleLineup(1 param)` INTROUVABLE" };
            try {
                const cleGeree = createManagedString(cle);
                gcRoot.add(cleGeree);
                try {
                    const fn = new NativeFunction(
                        mi.ptr, "pointer", ["pointer", "pointer", "pointer"],
                        { exceptions: "propagate" });
                    const arr = fn(store, cleGeree, mi.info) as NativePointer;
                    if (arr.isNull()) {
                        return { ok: true, cle, longueur: null, contenu: null,
                                 note: "le magasin a rendu NUL pour cette clé" };
                    }
                    const obs = lireTableau(arr);
                    return { ok: true, cle, longueur: obs.longueur, contenu: obs.avant,
                             classeRetour: obs.classeRetour,
                             magasin: store.toString(), magasinSource: mag.source,
                             derniereSubstitution };
                } finally { try { gcRoot.remove(cleGeree); } catch { /* deja parti */ } }
            } catch (e) {
                return { ok: false, cle, refus: `\`GetBattleLineup\` a levé : ${(e as Error).message}` };
            }
        });
    };

    /**
     * `lineupRetraiteCommit { armer?, cle?, mode?, equipe?, confirmer? }` — LE « BOUTON ».
     *
     * Armé, il attend que tu SORTES de la sandbox par la retraite. À cet instant il lit la
     * composition réellement en jeu et la pose sur la cible désignée -- magasin (`cle`) ou
     * registre (`mode`).
     *
     * ⚠ LA CIBLE SE DÉSIGNE À L'ARMEMENT, elle ne se devine pas. La sandbox ne sait pas quel mode
     * elle imite : c'est NOUS qui l'avons montée. Deviner écrirait la composition sous une clé qui
     * n'est pas la bonne, et une clé fausse ne lève rien -- elle range à côté, en silence.
     *
     * ⚠ UN SEUL TIR PAR ARMEMENT (`commitDejaTire`). Une sandbox peut faire tirer la retraite
     * plusieurs fois ; sans verrou, la deuxième écraserait la première avec l'état d'après.
     */
    ctx.rpc.lineupRetraiteCommit = (body?: {
        armer?: boolean; cle?: string; mode?: string; equipe?: number; confirmer?: boolean;
    }): Promise<unknown> | unknown => {
        const etat = (): Record<string, unknown> => ({
            arme: ecouteRetraite !== null, cible: cibleCommit,
            fires: firesRetraite, dejaTire: commitDejaTire, dernierCommit,
            ancrage: `${NS_SRC}.${CLS_SANDBOX}$$${METHODE_RETRAITE}`,
        });
        if (!body || body.armer === undefined) {
            return { ok: true, lecture: true, ...etat(),
                note: "`{ armer: true, cle | mode, confirmer: true }`. Sortir ensuite de la "
                    + "sandbox par la retraite : la composition en jeu sera posée sur la cible." };
        }
        return queueOnMainThread(() => {
            if (body.armer === false) {
                if (ecouteRetraite) {
                    ecouteRetraite.detach(); Interceptor.flush(); ecouteRetraite = null;
                }
                cibleCommit = null; commitDejaTire = false;
                return { ok: true, arme: false, action: "retire", fires: firesRetraite,
                         dernierCommit };
            }
            const aCle = typeof body.cle === "string" && body.cle.length > 0;
            const aMode = typeof body.mode === "string" && body.mode.length > 0;
            if (aCle === aMode) {
                return { ok: false,
                    refus: "il faut EXACTEMENT une cible : `cle` (magasin -- campagne, pvp, guild "
                        + "boss) OU `mode` (registre -- guild war, sandbox, qui n'ont AUCUN "
                        + "magasin). Les deux, ou aucune, ne désigne rien." };
            }
            if (aMode && CLASSES[body.mode as string] === undefined) {
                return { ok: false,
                    refus: `mode inconnu \`${body.mode}\` -- connus : ${Object.keys(CLASSES).join(", ")}` };
            }
            if (body.confirmer !== true) {
                return { ok: false,
                    refus: "`confirmer: true` exigé. Ce n'est pas un observateur : à la prochaine "
                        + "retraite de sandbox il ÉCRIT" + (aCle
                            ? " dans le magasin du joueur, de façon PERSISTANTE." : " au registre.") };
            }
            if (ecouteRetraite !== null) {
                return { ok: true, ...etat(), note: "déjà armé -- désarmer pour changer de cible" };
            }
            const r = armerRetraite();
            if (r.ok !== true) return r;
            cibleCommit = {
                cle: aCle ? (body.cle as string) : null,
                mode: aMode ? (body.mode as string) : null,
                // `null` = on prendra la PLUS PETITE équipe présente, et on dira laquelle.
                equipe: typeof body.equipe === "number" ? body.equipe : null,
            };
            commitDejaTire = false;
            return { ok: true, ...etat(),
                note: "armé. Sortir de la sandbox PAR LA RETRAITE pour déclencher le commit." };
        });
    };

    /**
     * AUTO-TEST DE LA LIAISON `il2cpp_array_new` — alloue, relit, jette.
     *
     * Il existe parce que la liaison est PARESSEUSE : un export absent ne se verrait ni à la
     * compilation ni au chargement, seulement au premier usage réel -- c'est-à-dire au pire
     * moment, en pleine substitution. Ce RPC déplace cette découverte AVANT.
     *
     * Il vérifie DEUX choses d'un coup, et la seconde compte autant : que l'allocation répond, et
     * que la disposition qu'on croit connaître (`longueur` en `+0x18`, classe au pointeur de tête)
     * se relit bien sur un tableau qu'on a fabriqué NOUS-MÊMES. Un `String[]` relu comme tel sur
     * notre propre allocation est la preuve que les offsets de LECTURE valent pour l'ÉCRITURE.
     *
     * N'écrit rien dans le jeu : le tableau reste vide et n'est confié à personne.
     */
    ctx.rpc.lineupArrayAutotest = (body?: { longueur?: number }): Promise<unknown> | unknown => {
        const n = body?.longueur ?? 5;
        return queueOnMainThread(() => {
            const kStr = findClassAnywhere("System", "String");
            if (!kStr) return { ok: false, refus: "classe `System.String` INTROUVABLE" };
            let arr: NativePointer;
            try { arr = createManagedArray(kStr, n); }
            catch (e) { return { ok: false, refus: (e as Error).message }; }
            // ENRACINER tout de suite : rien de managé ne le référence.
            gcRoot.add(arr);
            let classe: string | null = null;
            try { classe = cstr(class_get_name(arr.readPointer()) as NativePointer); } catch { /* nul */ }
            let relue: number | null = null;
            try { relue = arr.add(OFF_LONGUEUR).readS32(); } catch { /* nul */ }
            // Un tableau NEUF doit avoir toutes ses cases à NUL -- si ce n'est pas le cas, c'est
            // l'offset des éléments qui est faux, pas l'allocation.
            let premieresNulles: boolean | null = null;
            try {
                premieresNulles = true;
                for (let i = 0; i < Math.min(n, 4); i++) {
                    if (!arr.add(OFF_ELEMENTS + i * Process.pointerSize).readPointer().isNull()) {
                        premieresNulles = false;
                    }
                }
            } catch { premieresNulles = null; }
            gcRoot.remove(arr);
            return {
                ok: classe !== null && relue === n,
                demandee: n, longueurRelue: relue, classe, premieresCasesNulles: premieresNulles,
                note: "le tableau est LIBERE a la sortie : rien n'est confie au jeu",
            };
        });
    };

    ctx.rpc.lineupPoserArmer = (body?: {
        armer?: boolean; mode?: string;
    }): Promise<unknown> | unknown => {
        if (!body || body.armer === undefined) {
            return {
                ok: true, lecture: true, arme: listener !== null, classeArmee, fires,
                observations, registre: etatRegistre(), dernierePose,
                note: "`{ armer: true, mode? }` pour ancrer (OBSERVER). Retenir une composition "
                    + "avec `lineupPoserUnites`. ⚠ tant que c'est armé, `lineupSource` REFUSE.",
            };
        }
        return queueOnMainThread(() => {
            if (body.armer === false) {
                if (listener) { listener.detach(); Interceptor.flush(); listener = null; }
                classeArmee = null;
                return { ok: true, arme: false, action: "retire", fires };
            }
            if (listener !== null) {
                return { ok: true, arme: true, classeArmee, fires, note: "déjà armé" };
            }
            const r = armer(body.mode ?? "campagne");
            if (r.ok !== true) return r;
            return {
                ok: true, arme: true, classeArmee, fires, registre: etatRegistre(),
                note: "régime OBSERVER -- rien n'est écrit tant qu'aucune composition CONFIRMÉE "
                    + "n'est retenue pour ce mode",
            };
        });
    };

    /** RETENIR une composition pour un mode. C'est l'entrée du registre : ce que `GetBattleLineup`
     *  posera, ET ce que le chemin des buffs devra lire pour viser les mêmes unités. */
    ctx.rpc.lineupPoserUnites = (body?: {
        mode?: string; unites?: string[] | null; confirmer?: boolean; origine?: string;
    }): unknown => {
        const mode = body?.mode ?? "campagne";
        const nomClasse = CLASSES[mode];
        if (nomClasse === undefined) {
            return { ok: false, refus: `mode inconnu \`${mode}\` -- connus : ${Object.keys(CLASSES).join(", ")}` };
        }
        if (!body || body.unites === undefined) {
            return { ok: true, lecture: true, registre: etatRegistre(), fires, observations, dernierePose };
        }
        if (body.unites === null) {
            registre.delete(nomClasse);
            return { ok: true, action: "efface", mode, classe: nomClasse, registre: etatRegistre() };
        }
        if (!Array.isArray(body.unites) || body.unites.length === 0) {
            return { ok: false, refus: "`unites` doit être un tableau NON VIDE d'ids d'unité" };
        }
        if (body.unites.some((u) => typeof u !== "string" || u.length === 0)) {
            return { ok: false, refus: "chaque id doit être une chaîne non vide" };
        }
        // Le cran qui rend ce module honnête : on ne remplit pas un tableau qu'on n'a jamais vu.
        const vue = observations.find((o) => o.classeRetour !== null && o.longueur !== null);
        if (body.confirmer === true && !vue) {
            return {
                ok: false,
                refus: `AUCUNE observation n'a lu le tableau (${observations.length} passage(s), `
                    + `${fires} fire(s)). Armer, ouvrir une bataille pour OBSERVER, puis confirmer.`,
            };
        }
        registre.set(nomClasse, {
            ids: body.unites.slice(),
            confirme: body.confirmer === true,
            origine: body.origine ?? "pose manuelle",
        });
        return {
            ok: true, mode, classe: nomClasse, registre: etatRegistre(), fires,
            placesObservees: vue ? vue.longueur : null,
            note: body.confirmer === true
                ? "RETENUE ET CONFIRMÉE -- sera posée au prochain `GetBattleLineup`, et lisible "
                    + "par le chemin des buffs via `compositionRetenue()`"
                : "retenue mais NON confirmée -- ni écrite, ni visible du chemin des buffs",
        };
    };
}
