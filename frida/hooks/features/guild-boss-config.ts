// guild-boss-config — LE BOSS DE GUILDE COURANT, ET LES LIMITATIONS DE ROSTER QUI L'ACCOMPAGNENT.
//
// POURQUOI. Le gameconfig VERSIONNE ne porte PAS les encounters de guild boss : on y trouve
// ses coffres (`chest_guildboss_defeated_*`, `guildboss_season_end_reward_*`) mais ni
// `boardId`, ni `unitId`, ni PV, ni NPC. Ils viennent du SERVEUR et vivent dans la
// progression. Il n'existe donc AUCUNE voie « tout depuis le fichier » -- lire la progression
// est obligatoire, et c'est ce que ce module fait.
//
// LA CHAINE, meme forme que `pvp-opponents.ts` :
//
//     ViewCommandExecutor._guildBossProgression   ->  GuildBossProgression
//       GetGuildBossBattleConfiguration(idx)      ->  GuildBossConfiguration
//       GetDeployableUnits(idx, includeLocked)    ->  List<String>
//
// LA CONFIGURATION REMPLIT 11 DES 14 ARGUMENTS DU CTOR SANDBOX, un pour un :
//
//     BoardId -> boardId          BossUnitId -> bossUnitId
//     EggUnitId -> npc1UnitId     DragonlingUnitId -> npc2UnitId
//     BossHealth -> health        RemainingBossHealth -> remainingHealth
//     MaxRoundAmount -> rounds    SpawnPointSetIndex -> spawnPointIndex
//     BossModifiers / Enemies / UnitModifiers -> idem
//
// Les trois qui restent sont NOTRE camp (`playerType`, `playerUnits`,
// `playerMachineOfWarUnit`) -- exactement ce que la phase de deploiement doit choisir.
//
// ⚠ LA LIMITATION DE ROSTER EST `DisallowedFactions`, ET LA REGLE EST LUE AU DECOMPILE.
// `GuildBossProgression$$GetDeployableUnitsPooled` teste le champ `+0x60` de la configuration
// (soit `DisallowedFactions`) :
//
//     si IsNullOrEmpty(config + 0x60)                  -> l'unite est ACCEPTEE
//     sinon si !Contains(config + 0x60, <faction>)     -> l'unite est ACCEPTEE
//
// Autrement dit : liste vide => tout passe ; liste non vide => passe ce qui n'y est PAS.
//
// ⚠ ET LA SIGNATURE N'EST PAS CELLE QU'ON CROIT. `GetDeployableUnitsPooled` prend
// `(encounterIndex : EncounterIndex, includeLocked : Boolean)` -- PAS zero parametre. Le
// booleen choisit le slot d'interface `0xc` ou `0xe3` sur la progression d'unites, les deux
// memes slots que cote PvP. « Avec ou sans les unites verrouillees » est donc un CHOIX, pas un
// defaut : ce module le rend explicite et le publie.
//
// ⚠ CE QUE LES DEUX NATIFS INVOQUES FONT, VERIFIE AU DECOMPILE AVANT DE LES APPELER.
// `GetGuildBossBattleConfiguration` ALLOUE un objet et le remplit depuis les modeles ; il
// n'ecrit RIEN sur le compte. `GetDeployableUnitsPooled` lit et alloue depuis un pool. Aucun
// `Send*GameEvent`, aucun appel reseau. C'est ce qui autorise l'invocation.
//
// ⚠ ET IL NE FAUT PAS MONTER LE BOSS PAR SA PROPRE SOURCE. `GuildBossGameModeSource` porte un
// `SendLoadBattleGameEventInternal` qui enregistre une tentative AU CHARGEMENT ; la surface de
// `SandboxGameModeSource` n'en porte aucun. Le montage passe donc par la sandbox -- c'est ce
// qui rend l'operation gratuite.
//
// LECTURE SEULE : aucune ecriture, aucune tentative consommee.

import {
    class_get_name, findClassAnywhere, findMethodByParamCount, getFieldOffset, MethodRef, s as cstr,
} from "../il2cpp/helpers.js";
import { executeurVivant, Refus as RefusVue } from "./view-command.js";
// Le FOYER des captures de `*GameModeSource` (campagne, MoW, Pvp, et desormais guild boss).
import { getGuildBossGameModeSourcePtr } from "./campaign-builder.js";
import { serializeToJson } from "../il2cpp/serializer.js";
import {
    champInt, champPointeur, champTexte, estRefus, listeDeTextes, refus,
} from "./lecture-champs.js";
import { il2cpp_object_new, invokeMethod } from "../il2cpp/invoke.js";

/** Le namespace des sources de mode. */
const NS_SRC_GB = "IdunBattle.ViewLogic.BattleSource";
import { gcRoot } from "../il2cpp/gc-root.js";
import { queueOnMainThread } from "../runtime/queue.js";
import { Ctx } from "../controller.js";

/** `EncounterIndex` est un TYPE VALEUR d'un seul `Int32` (`boxedSize` = 20 = 0x10 + 4).
 *  `il2cpp_runtime_invoke` attend un pointeur vers la VALEUR, pas vers une boite. */
function argIndex(i: number): NativePointer {
    const p = Memory.alloc(4);
    p.writeS32(i);
    return p;
}

function argBool(b: boolean): NativePointer {
    const p = Memory.alloc(1);
    p.writeU8(b ? 1 : 0);
    return p;
}

/** La `GuildBossProgression` vivante, via le foyer `executeurVivant`. */
export function progressionGuildBoss(): NativePointer | RefusVue {
    const exec = executeurVivant();
    if (estRefus(exec)) return exec;
    const kExec = findClassAnywhere("idun.shared.commands", "ViewCommandExecutor");
    if (!kExec) return refus("classe `idun.shared.commands.ViewCommandExecutor` introuvable");
    const off = getFieldOffset(kExec, "_guildBossProgression");
    if (off < 0) {
        return refus("`_guildBossProgression` ABSENT de `ViewCommandExecutor` sur ce build "
            + "-- chemin PERIME");
    }
    const p = (exec as NativePointer).add(off).readPointer();
    if (p.isNull()) {
        return refus("`ViewCommandExecutor._guildBossProgression` est NUL -- le mode guild boss "
            + "n'est PAS cable. C'est un defaut de CABLAGE, pas une absence de guilde.");
    }
    return p;
}

/** Resout une methode sur la classe REELLE de la progression (jamais par un nom de namespace :
 *  l'objet derriere `IGuildBossProgression` est une `GuildBossProgression`). */
function methodeDe(prog: NativePointer, nom: string, arite: number): MethodRef | RefusVue {
    let k: NativePointer;
    try { k = prog.readPointer(); } catch { return refus("classe de la progression illisible"); }
    if (k.isNull()) return refus("slot de classe NUL sur la progression");
    const mi = findMethodByParamCount(k, nom, arite);
    if (!mi || mi.ptr.isNull()) {
        return refus(`\`${nom}\` (${arite} parametre(s)) INTROUVABLE sur ce build -- signature `
            + "CHANGEE, on ne devine pas une arite de remplacement");
    }
    return mi;
}

/**
 * La `GuildBossConfiguration` d'un encounter.
 *
 * ⚠ Le natif rend **0** (et non une levee) quand ses `Contract.Require` echouent -- mesure au
 * decompile : il exige `this+0xc0` et `this+0x98` non nuls. Ce zero SIGNIFIE « la progression
 * existe mais n'a pas ses donnees » (pas de guilde, pas de saison en cours, pas encore
 * synchronise), et c'est un etat parfaitement legitime qu'il faut NOMMER plutot que de rendre
 * comme une panne.
 */
function configuration(prog: NativePointer, idx: number): NativePointer | RefusVue {
    const mi = methodeDe(prog, "GetGuildBossBattleConfiguration", 1);
    if (estRefus(mi)) return mi;
    let r: NativePointer;
    try { r = invokeMethod(mi.info, prog, [argIndex(idx)]); }
    catch (e) { return refus("`GetGuildBossBattleConfiguration` a leve : " + (e as Error).message); }
    if (r.isNull()) {
        return refus(`\`GetGuildBossBattleConfiguration(${idx})\` a rendu NUL. Au decompile, ce `
            + "retour signifie que les `Contract.Require` de la progression ont echoue : elle "
            + "vit, mais SANS DONNEES (pas de guilde, pas de saison active, ou pas encore "
            + "synchronisee). Ce n'est pas une panne de lecture.");
    }
    gcRoot.add(r);
    return r;
}

/** Le roster deployable, filtres du mode APPLIQUES par le natif lui-meme. */
function deployables(prog: NativePointer, idx: number, includeLocked: boolean):
    string[] | RefusVue {
    const mi = methodeDe(prog, "GetDeployableUnits", 2);
    if (estRefus(mi)) return mi;
    let r: NativePointer;
    try { r = invokeMethod(mi.info, prog, [argIndex(idx), argBool(includeLocked)]); }
    catch (e) { return refus("`GetDeployableUnits` a leve : " + (e as Error).message); }
    if (r.isNull()) return refus("`GetDeployableUnits` a rendu NUL");
    gcRoot.add(r);
    const l = listeDeTextes(r);
    if (l === null) return refus("liste deployable ILLISIBLE -- ce n'est pas une `List<String>`");
    return l;
}

/**
 * LE ROSTER GUILD BOSS, sous la forme que la substitution du HUD attend : la BOITE rendue par
 * `GetDeployableUnitsPooled`.
 *
 * ⚠ ON N'EMPRUNTE PAS A UNE `GuildBossGameModeSource`, ET C'EST DELIBERE. Elle n'est captee
 * par aucun de nos ancrages, et surtout son `IsUnitDeployable` ne fait que DELEGUER a la
 * progression (slot d'interface `0x36`, avec son index d'encounter). La progression est donc
 * le FOYER de la regle, pas un contournement : on s'y adresse directement, avec une dependance
 * de moins.
 *
 * ⚠ Rend la BOITE, pas la valeur : `PooledList<T>` est un TYPE VALEUR, donc
 * `il2cpp_runtime_invoke` la boxe, et c'est a l'appelant de deboxer (+0x10) comme il le fait
 * deja pour les deux autres preteurs. Rendre la boite la ou l'appelant attend la valeur lui
 * ferait lire l'en-tete d'objet comme si c'etait le conteneur.
 */
export function rosterPooledGuildBoss(idx: number, includeLocked: boolean):
    NativePointer | RefusVue {
    const prog = progressionGuildBoss();
    if (estRefus(prog)) return prog;
    const mi = methodeDe(prog as NativePointer, "GetDeployableUnitsPooled", 2);
    if (estRefus(mi)) return mi;
    let r: NativePointer;
    try { r = invokeMethod(mi.info, prog as NativePointer, [argIndex(idx), argBool(includeLocked)]); }
    catch (e) { return refus("`GetDeployableUnitsPooled` a leve : " + (e as Error).message); }
    if (r.isNull()) return refus("`GetDeployableUnitsPooled` a rendu NUL");
    gcRoot.add(r);
    return r;
}

/** Les champs que `LoadBattleInternal` LIT, releves au decompile -- resolus PAR NOM ici.
 *
 *  Six pour `LoadBattleInternal` lui-meme (`_guildBossConfig`, `_unitProgression`,
 *  `_gameConfig`, `_logger`, `_resourceProgression`, `_featureUnlocker`), plus DEUX que son
 *  appel a `ApprogressionGameModeSource$$ApplyEnvironmentAbilitiesFromProgression` exige
 *  (`ModifierProgression`, `Logger`). Les deux derniers ne se voyaient PAS dans le corps de
 *  `LoadBattleInternal` : c'est le callee qui les lit. */
const CHAMPS_REQUIS = [
    "_guildBossConfig", "_unitProgression", "_gameConfig", "_logger",
    "_resourceProgression", "_featureUnlocker", "ModifierProgression", "Logger",
] as const;

/**
 * L'etat des dependances d'une source, champ par champ.
 *
 * ⚠ TROIS ETATS, ET LES CONFONDRE A DEJA MENTI. La premiere version rendait le refus comme une
 * CHAINE (`"REFUS: ..."`), et l'appelant comptait les manquants par `=== null` -- donc un champ
 * ILLISIBLE etait compte comme PRESENT. Mesure le 2026-08-17 : `pret: true` sur une instance
 * dont AUCUN des huit champs n'etait lisible, parce que la classe derriere le pointeur n'etait
 * pas la bonne. Invoquer sur cette base aurait appele un natif sur un objet du mauvais type.
 *
 *   `{ valeur }`   -> lu, non nul
 *   `{ nul: true }` -> lu, NUL (dependance a cabler)
 *   `{ refus }`    -> PAS LU (champ absent de ce build, objet illisible)
 */
interface EtatChamp { valeur?: string; nul?: boolean; refus?: string }

function etatDesChamps(src: NativePointer): Record<string, EtatChamp> {
    const out: Record<string, EtatChamp> = {};
    for (const nom of CHAMPS_REQUIS) {
        const p = champPointeur(src, nom);
        if (estRefus(p)) out[nom] = { refus: p.error };
        else if (p.isNull()) out[nom] = { nul: true };
        else out[nom] = { valeur: p.toString() };
    }
    return out;
}

/** Les champs NULS (a cabler) et les champs ILLISIBLES (chemin perime / mauvais type). */
function ventiler(champs: Record<string, EtatChamp>): { nuls: string[]; illisibles: string[] } {
    return {
        nuls: Object.keys(champs).filter((k) => champs[k].nul === true),
        illisibles: Object.keys(champs).filter((k) => champs[k].refus !== undefined),
    };
}

/**
 * La classe REELLE derriere un pointeur.
 *
 * ⚠ C'est le controle qui manquait a la capture. Les portes passives visaient des getters
 * HERITES (`get_BattleGameMode`, `get_Name`...) : IL2CPP partage UN SEUL corps entre toutes
 * les sources, donc le hook attrape le `this` de n'importe laquelle. Sans confronter la
 * classe, on retient une `CampaignGameModeSource` en croyant tenir la guild boss.
 */
function nomDeClasseDe(p: NativePointer): string | null {
    try {
        if (p.isNull()) return null;
        const k = p.readPointer();
        if (k.isNull()) return null;
        return cstr(class_get_name(k) as NativePointer);
    } catch { return null; }
}

/**
 * LES 18 ARGUMENTS DU CTOR, dans l'ordre, tels que `ViewCommandExecutor$$StartGuildBossMatch`
 * les passe -- releves au decompile puis NOMMES par `classFields`, jamais devines.
 *
 * `champ` = le nom du champ a lire sur le `ViewCommandExecutor`.
 * `special` = une valeur qui ne vient pas directement de l'executeur.
 */
const ARGS_CTOR: Array<{ nom: string; champ?: string; special?: string }> = [
    { nom: "guildBossProgression", champ: "_guildBossProgression" },
    { nom: "guildProgression", champ: "_guildProgression" },
    { nom: "unitProgression", champ: "_unitProgression" },
    { nom: "modifierProgression", champ: "_modifierProgression" },
    { nom: "battleReconciliationProgression", champ: "_battleReconciliationProgression" },
    { nom: "gameConfig", champ: "_gameConfigData" },
    { nom: "viewCommandExecutor", special: "executeur" },
    { nom: "menuSystems", champ: "_menuSystems" },
    { nom: "logger", champ: "_logger" },
    { nom: "tutorialStatus", special: "tutorialStatusTool" },
    { nom: "heroReleaseEventProgression", champ: "_heroReleaseEventProgression" },
    { nom: "soundSetup", champ: "_soundSetup" },
    { nom: "onlineFeatureDecider", champ: "_onlineFeatureDecider" },
    { nom: "deploymentHud", special: "menuSystems.unitDeploymentHud" },
    { nom: "encounterIndex", special: "index" },
    { nom: "featureUnlocker", champ: "_featureUnlocker" },
    { nom: "resourceProgression", champ: "_resourceProgression" },
    { nom: "questEventHandler", champ: "_questEventHandler" },
];

/** La source forgee, retenue entre appels (et enracinee -- sinon le GC la ramasse). */
let sourceForgee: NativePointer | null = null;

/**
 * La `GuildBossGameModeSource` FORGEE, pour les modules qui doivent lui DELEGUER un appel.
 *
 * ⚠ EXPOSEE parce que la delegation du HUD (`deployment-draft`) doit emprunter a LA SOURCE DU
 * MODE, pas a la campagne : `SandboxGameModeSource$$GetGameModeSpecificDeploymentHudOptions`
 * rend un objet NU (elle ne pose que `isOnlineOnly`, laissant `supportsMachinesOfWar` a false),
 * et emprunter a la campagne importerait SES restrictions -- le meme vice que le roster
 * imperial sur un montage PvP.
 */
export function sourceGuildBossForgee(): NativePointer | null {
    return sourceForgee;
}

export function register(ctx: Ctx): void {
    /**
     * FORGE une `GuildBossGameModeSource` EXACTEMENT comme le jeu la forge.
     *
     * ⚠ POURQUOI FORGER, ET POURQUOI CE N'EST PAS DE LA CUISINE. Le seul appelant du ctor est
     * `ViewCommandExecutor$$StartGuildBossMatch`, qui fait DEUX choses : construire la source
     * avec 18 arguments lus sur l'executeur, PUIS appeler `StartMatch` -- et c'est ce second
     * appel, lui seul, qui demarre la bataille et engage la tentative. On reproduit le PREMIER
     * geste, verbatim, et on n'appelle JAMAIS le second.
     *
     * Les 18 arguments viennent tous de l'executeur (ou en derivent), resolus PAR NOM. Rien
     * n'est invente : c'est la meme source, cablee par les memes services que ceux dont le jeu
     * se sert. C'est ce qui permet ensuite a `LoadBattleInternal` de produire SA BC -- avec son
     * catalogue, ses modificateurs et ses environment abilities.
     *
     * ⚠ `StartMatch` N'EST PAS APPELE ICI, et ne doit jamais l'etre par ce module : il ECRASE
     * le match courant et enregistre la tentative AU CHARGEMENT.
     */
    ctx.rpc.guildBossSourceForger = (body?: {
        confirmer?: boolean; encounterIndex?: number;
    }): Promise<unknown> => queueOnMainThread(() => {
        const idx = body?.encounterIndex ?? 0;
        const exec = executeurVivant();
        if (estRefus(exec)) return exec;
        const kExec = findClassAnywhere("idun.shared.commands", "ViewCommandExecutor");
        if (!kExec) return refus("classe `ViewCommandExecutor` introuvable");

        // 1. Les champs de l'executeur, PAR NOM. Un seul absent => on s'arrete en le nommant.
        const depuisExec: Record<string, NativePointer> = {};
        const absents: string[] = [];
        const nuls: string[] = [];
        for (const a of ARGS_CTOR) {
            if (!a.champ) continue;
            const off = getFieldOffset(kExec, a.champ);
            if (off < 0) { absents.push(a.champ); continue; }
            const p = (exec as NativePointer).add(off).readPointer();
            if (p.isNull()) nuls.push(a.champ);
            depuisExec[a.champ] = p;
        }
        if (absents.length > 0) {
            return refus("champs ABSENTS de `ViewCommandExecutor` sur ce build : "
                + absents.join(", ") + " -- chemin PERIME");
        }

        // 2. `deploymentHud` = `_menuSystems.unitDeploymentHud` (nom releve sur MenuSystems).
        const menuSystems = depuisExec["_menuSystems"];
        const hud = champPointeur(menuSystems, "unitDeploymentHud");
        if (estRefus(hud)) return hud;

        // 3. `tutorialStatus` = `TutorialStatusTool..ctor(featureUnlocker)` -- c'est ce que
        //    `StartGuildBossMatch` construit, avec le MEME argument.
        const kTuto = findClassAnywhere("idun.shared", "TutorialStatusTool");
        if (!kTuto) return refus("classe `idun.shared.TutorialStatusTool` introuvable");
        const miTuto = findMethodByParamCount(kTuto, ".ctor", 1);
        if (!miTuto) return refus("`TutorialStatusTool..ctor(1)` INTROUVABLE");

        if (body?.confirmer !== true) {
            return { ok: true, lecture: true, encounterIndex: idx,
                     executeur: (exec as NativePointer).toString(),
                     champsNuls: nuls,
                     note: "`confirmer: true` exige : ce RPC ALLOUE et CONSTRUIT une "
                         + "`GuildBossGameModeSource`. Il n'appelle PAS `StartMatch`, donc il ne "
                         + "demarre aucune bataille et ne consomme aucune tentative." };
        }
        if (nuls.length > 0) {
            return refus("dependances NULLES sur l'executeur : " + nuls.join(", ")
                + " -- la source serait construite incomplete, et le natif leverait plus tard "
                + "sans rien nommer");
        }

        const kSrc = findClassAnywhere(NS_SRC_GB, "GuildBossGameModeSource");
        if (!kSrc) return refus("classe `GuildBossGameModeSource` introuvable");
        const miCtor = findMethodByParamCount(kSrc, ".ctor", 18);
        if (!miCtor) {
            return refus("`GuildBossGameModeSource..ctor(18)` INTROUVABLE -- la signature a "
                + "CHANGE sur ce build ; on ne devine pas une arite de remplacement");
        }

        let tuto: NativePointer;
        try {
            tuto = il2cpp_object_new(kTuto) as NativePointer;
            gcRoot.add(tuto);
            invokeMethod(miTuto.info, tuto, [depuisExec["_featureUnlocker"]]);
        } catch (e) { return refus("`TutorialStatusTool..ctor` a leve : " + (e as Error).message); }

        let src: NativePointer;
        try { src = il2cpp_object_new(kSrc) as NativePointer; }
        catch (e) { return refus("allocation de la source a leve : " + (e as Error).message); }
        gcRoot.add(src);

        const args: NativePointer[] = ARGS_CTOR.map((a) => {
            if (a.champ) return depuisExec[a.champ];
            if (a.special === "executeur") return exec as NativePointer;
            if (a.special === "tutorialStatusTool") return tuto;
            if (a.special === "menuSystems.unitDeploymentHud") return hud as NativePointer;
            return argIndex(idx);          // `encounterIndex` : type VALEUR de 4 octets
        });

        try { invokeMethod(miCtor.info, src, args); }
        catch (e) { return refus("`GuildBossGameModeSource..ctor` a leve : " + (e as Error).message); }

        sourceForgee = src;
        const champs = etatDesChamps(src);
        const v = ventiler(champs);
        return {
            ok: true, action: "FORGEE", instance: src.toString(),
            classe: nomDeClasseDe(src), encounterIndex: idx,
            champs, nuls: v.nuls, illisibles: v.illisibles,
            pret: v.nuls.length === 0 && v.illisibles.length === 0,
            note: "`StartMatch` n'a PAS ete appele -- aucune bataille demarree, aucune "
                + "tentative consommee.",
        };
    });

    /**
     * L'instance vivante de `GuildBossGameModeSource` et l'etat de ses dependances.
     *
     * Lecture PURE : aucune invocation. Sert a savoir si `guildBossSourceBc` peut travailler,
     * et SI NON, lequel des huit champs manque -- plutot qu'un echec generique en aval.
     */
    ctx.rpc.guildBossSourceProbe = (): Promise<unknown> => queueOnMainThread(() => {
        const src = getGuildBossGameModeSourcePtr();
        if (src === null || src.isNull()) {
            return { ok: true, captee: false, instance: null,
                     note: "aucune `GuildBossGameModeSource` captee. Les portes passives sont "
                         + "armees (ctor + 6 getters) : ouvrir l'ecran Guild Boss suffit "
                         + "normalement a en faire naitre une. OUVRIR ne consomme AUCUNE "
                         + "tentative -- seul un combat en consomme." };
        }
        const classe = nomDeClasseDe(src);
        const champs = etatDesChamps(src);
        const { nuls, illisibles } = ventiler(champs);
        // La CLASSE d'abord : des champs tous illisibles ne veulent pas dire « build perime »,
        // ils veulent dire « ce n'est pas l'objet qu'on croit ».
        const bonType = classe === "GuildBossGameModeSource";
        return {
            ok: true, captee: true, instance: src.toString(), classe, bonType,
            champs, nuls, illisibles,
            pret: bonType && nuls.length === 0 && illisibles.length === 0,
            note: bonType ? null
                : `classe REELLE = ${classe} -- ce n'est PAS une GuildBossGameModeSource. Une `
                    + "porte passive a capte le `this` d'une AUTRE source (les getters herites "
                    + "partagent UN SEUL corps entre toutes les sources).",
        };
    });

    /**
     * LA `BattleConfiguration` DU BOSS, PRODUITE PAR LA SOURCE DU MODE ELLE-MEME.
     *
     * ⚠ C'EST LA SEULE VOIE LEGITIME, et elle remplace la fabrication a la main. Construire
     * une `SandboxGuildBossBattleConfig` avec des arguments CHOISIS produit une BC dont le
     * CATALOGUE (`BC.Units`) ne contient que ce qu'on a passe -- alors que le HUD, lui, offre
     * les 101 unites deployables du mode. Poser une de ces 100 autres cree une entite dont la
     * definition manque. Ici la source produit SON catalogue, ses modificateurs et ses
     * environment abilities : rien n'est invente, rien n'est fusionne.
     *
     * ⚠ AUCUNE TENTATIVE CONSOMMEE, et c'est le decompile qui l'etablit, pas le nom de la
     * methode : `LoadBattleInternal` construit la BC et la rend, sans appeler
     * `SendLoadBattleGameEventInternal` -- l'envoi de l'evenement est une methode SEPAREE
     * (`void`), qu'on n'appelle jamais. C'est exactement ce qui distingue cette voie de
     * `LoadBattle`.
     *
     * ⚠ On INVOQUE `LoadBattleInternal`, donc on ne l'ANCRE nulle part (ce serait le gel). Les
     * portes de capture de `campaign-builder` visent des getters et des relais d'UI.
     */
    ctx.rpc.guildBossSourceBc = (body?: {
        confirmer?: boolean; isRestart?: boolean;
    }): Promise<unknown> => queueOnMainThread(() => {
        // La source FORGEE d'abord (c'est la voie normale : le jeu n'en cree une que pour
        // demarrer une bataille, ce qui couterait une tentative), sinon celle que les portes
        // passives auraient captee si une vraie bataille guild boss avait tourne.
        const src = sourceForgee ?? getGuildBossGameModeSourcePtr();
        if (src === null || src.isNull()) {
            return refus("aucune `GuildBossGameModeSource` -- appeler `guildBossSourceForger "
                + "{confirmer:true}` d'abord (il construit la source SANS demarrer de bataille)");
        }
        const classe = nomDeClasseDe(src);
        const champs = etatDesChamps(src);
        const { nuls, illisibles } = ventiler(champs);
        // ⛔ LE TYPE AVANT TOUT. Invoquer `LoadBattleInternal` sur un objet qui n'est pas une
        // `GuildBossGameModeSource` execute du code natif sur une disposition memoire etrangere.
        if (classe !== "GuildBossGameModeSource") {
            return refus(`l'instance captee est une \`${classe}\`, PAS une `
                + "`GuildBossGameModeSource`. Invoquer dessus executerait du natif sur une "
                + "disposition memoire etrangere. Cause connue : une porte passive a capte le "
                + "`this` d'une autre source par un getter HERITE (corps partage).");
        }
        if (illisibles.length > 0) {
            return refus("champs ILLISIBLES sur ce build : " + illisibles.join(", ")
                + " -- chemin PERIME, on n'invoque pas a l'aveugle");
        }
        if (body?.confirmer !== true) {
            return { ok: true, lecture: true, instance: src.toString(), classe, champs,
                     nuls, illisibles, pret: nuls.length === 0,
                     note: "`confirmer: true` exige : ce RPC INVOQUE "
                         + "`GuildBossGameModeSource$$LoadBattleInternal` sur la source vivante. "
                         + "Il ne depense RIEN (l'envoi d'evenement est une methode separee, "
                         + "jamais appelee), mais il ECRIT `_currentBattle` sur cette source." };
        }
        if (nuls.length > 0) {
            // On REFUSE en NOMMANT les champs, plutot que de laisser le natif lever : deux de
            // ces champs sont des gardes explicites (`_gameConfig`, `_resourceProgression`).
            return refus("dependances NON CABLEES : " + nuls.join(", ")
                + " -- invoquer maintenant ferait lever le natif sans rien nommer");
        }
        const mi = methodeDe(src, "LoadBattleInternal", 1);
        if (estRefus(mi)) return mi;
        let bc: NativePointer;
        try { bc = invokeMethod(mi.info, src, [argBool(body?.isRestart === true)]); }
        catch (e) { return refus("`LoadBattleInternal` a leve : " + (e as Error).message); }
        if (bc.isNull()) return refus("`LoadBattleInternal` a rendu NUL");
        gcRoot.add(bc);
        const json = serializeToJson(bc);
        return {
            ok: true, instance: src.toString(), bc: bc.toString(),
            json,
            jsonRefus: json === null
                ? "serialisation Newtonsoft en echec -- la BC existe (pointeur ci-dessus) mais "
                    + "n'a pas pu etre rendue en texte"
                : null,
            octets: json === null ? null : json.length,
        };
    });

    /**
     * Le boss courant et ses limitations de roster.
     *
     * `{ encounterIndex }` choisit l'encounter (defaut 0) ; `{ includeLocked }` decide si les
     * unites verrouillees comptent (defaut `false` -- ce que l'ecran montre).
     *
     * ⚠ Publie TOUJOURS `cable` et `donnees` separement : une progression CABLEE mais SANS
     * DONNEES est un etat distinct d'une progression absente, et les confondre ferait chercher
     * un bug de harnais la ou il n'y a qu'une saison inactive.
     */
    ctx.rpc.guildBossConfig = (body?: {
        encounterIndex?: number; includeLocked?: boolean;
    }): Promise<unknown> => queueOnMainThread(() => {
        const idx = body?.encounterIndex ?? 0;
        const includeLocked = body?.includeLocked === true;

        const prog = progressionGuildBoss();
        if (estRefus(prog)) return { ...prog, cable: false, donnees: false };

        const cfg = configuration(prog as NativePointer, idx);
        if (estRefus(cfg)) {
            // CABLE (on tient la progression) mais SANS DONNEES -- la distinction est le point.
            return { ...cfg, cable: true, donnees: false,
                     progression: (prog as NativePointer).toString(), encounterIndex: idx };
        }

        const interdites = (() => {
            const l = champPointeur(cfg as NativePointer, "DisallowedFactions");
            if (estRefus(l)) return null;
            return l.isNull() ? [] : listeDeTextes(l);
        })();
        const ennemis = (() => {
            const l = champPointeur(cfg as NativePointer, "Enemies");
            if (estRefus(l)) return null;
            return l.isNull() ? [] : listeDeTextes(l);
        })();

        const dep = deployables(prog as NativePointer, idx, includeLocked);

        return {
            ok: true, cable: true, donnees: true,
            encounterIndex: idx, includeLocked,
            progression: (prog as NativePointer).toString(),
            // Les 11 champs qui remplissent le ctor `SandboxGuildBossBattleConfig`.
            boss: {
                boardId: champTexte(cfg as NativePointer, "BoardId"),
                bossUnitId: champTexte(cfg as NativePointer, "BossUnitId"),
                npc1UnitId: champTexte(cfg as NativePointer, "EggUnitId"),
                npc2UnitId: champTexte(cfg as NativePointer, "DragonlingUnitId"),
                spawnPointIndex: champInt(cfg as NativePointer, "SpawnPointSetIndex"),
                health: champInt(cfg as NativePointer, "BossHealth"),
                remainingHealth: champInt(cfg as NativePointer, "RemainingBossHealth"),
                rounds: champInt(cfg as NativePointer, "MaxRoundAmount"),
                bossRarity: champInt(cfg as NativePointer, "BossRarity"),
                unitSet: champTexte(cfg as NativePointer, "UnitSet"),
                enemies: ennemis,
            },
            // LES LIMITATIONS. `null` = pas lu ; `[]` = lu et VIDE, ce qui d'apres le decompile
            // signifie « aucune faction interdite, tout le roster passe ».
            limitations: {
                disallowedFactions: interdites,
                regle: interdites === null
                    ? "NON LUE"
                    : (interdites.length === 0
                        ? "aucune faction interdite -- tout le roster deployable passe"
                        : "une unite passe si sa faction n'est PAS dans `disallowedFactions`"),
                deployables: estRefus(dep) ? null : dep,
                nbDeployables: estRefus(dep) ? null : dep.length,
                refusDeployables: estRefus(dep) ? dep.error : null,
            },
            // Ces trois-la ne viennent PAS du boss : c'est le camp du joueur, donc le draft.
            aChoisir: ["playerType", "playerUnits", "playerMachineOfWarUnit"],
        };
    });
}
