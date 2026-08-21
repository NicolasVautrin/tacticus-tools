// guild-war-config — LA BC D'UN MATCH DE GUILD WAR, FABRIQUEE PAR LE JEU, SANS UN OCTET RESEAU.
//
// POURQUOI CE MODULE EXISTE
// --------------------------
// Le guild war est le SEUL mode de bataille qui n'a AUCUNE voie sandbox native. Mesure du
// 2026-08-18 sur le build courant, TROIS sources concordantes :
//
//   1. il n'existe pas de `SandboxGuildWarBattleConfig` -- les 11 classes `Sandbox*BattleConfig`
//      sont Battle, Boosts, CampaignEvent, Draft, GuildBoss, Infested, Pvp, Survival,
//      Territories, TreasureBeach, Waves ;
//   2. il n'existe pas de `BattleConfigBuilder$$GetHotseatGuildWarsConfig` -- alors que les 10
//      autres modes ont chacun leur `GetHotseat*Config` ;
//   3. `BattleConfigBuilder$$GetHotSeatGameModeSpecificConfig` (le ROUTEUR par type) n'a pas de
//      branche GuildWars.
//
// `sandbox-mode.ts` est donc structurellement incapable de le monter, et ce n'est pas un trou de
// notre outillage : c'est une absence cote JEU.
//
// ⛔ ET LA VOIE NATIVE PARLE AU SERVEUR -- C'EST TOUT L'INTERET DE CE MODULE
// --------------------------------------------------------------------------
// `idun.shared.commands.ViewCommandExecutor$$StartGuildWarsMatch(battleData)` fonctionne, et on
// NE L'UTILISE PAS. Lu au decompile : elle alloue une `GuildWarsGameModeSource` puis appelle
// `StartMatch`. Or le squelette `AGameModeSource` appelle
// `GuildWarsGameModeSource$$SendLoadBattleGameEventInternal` PAR SLOT DE VTABLE -- ses deux
// seules xrefs sont des DATA, aucun appelant direct. Ce natif genere un battleId
// (`IdunMetaLogic.UserProgress.Util.TempBattleData$$GenerateNewBattleId`) et le pousse par un
// appel d'interface : la tentative est ENREGISTREE SERVEUR, AU CHARGEMENT.
//
// Le guild war a des tentatives limitees ET un debuff cumulatif par tentative
// (`GuildWarsAttemptDebuffWidget`, `attemptDebuffPercentage`). Monter par la voie native coute
// donc une vraie tentative sur le compte, irreversible. C'est exactement le verrou que #10020-r1
// avait deja documente pour le guild boss.
//
// CE QU'ON FAIT A LA PLACE : LA FABRIQUE, PAS LA SOURCE
// ------------------------------------------------------
// `Idun.Source.IdunBattle.View.BattleConfigBuilder$$GetGuildWarsConfig` est une fonction
// PUREMENT CONSTRUCTIVE : 14 donnees en entree, une `IdunBattle.Configuration.BattleConfiguration`
// en sortie. Elle est appelee par `GuildWarsGameModeSource$$LoadBattleInternal`, dont le corps ne
// porte AUCUN `Send*` -- `LoadBattleInternal` et `SendLoadBattleGameEventInternal` sont deux
// overrides virtuels INDEPENDANTS. On appelle donc la fabrique sans jamais instancier la source.
//
// La BC obtenue est celle du JEU, pas une reconstruction : c'est le point. Une BC de syncPvp
// re-etiquetee serait une approximation dont il faudrait prouver l'equivalence.
//
// CE QUE LA FABRIQUE ECRIT DE SPECIFIQUE, MESURE AU DECOMPILE
// ------------------------------------------------------------
//   - `BC.GameMode = idun.Shared.Battle.GameMode.GuildWars`
//   - deux `IdunBattle.Configuration.PlayerConfiguration`, PlayerIndex 1 (nous) et 2 (ennemi)
//   - `BC.Victory.VictoryConditions[VictoryConditionType.KillAllEnemyMainUnits] = 1`
//     (l'entree est ajoutee APRES `GetLevelConfigWithRealUnits`, c'est la signature du mode)
//
// ⚠ LE RANK LIMIT N'EST PAS UNE REGLE DE BATAILLE -- IL NE DESCEND PAS DANS LA BC.
// `GuildWarBattleData.RarityCap` (+0x44 du record) n'est lu QUE par
// `GuildWarsGameModeSource$$GetGameModeSpecificDeploymentHudOptionsInternal`, qui le recopie dans
// `idun.ui.GameModeSpecificUnitDeploymentHudOptions_GuildWars`. `LoadBattleInternal` ne le lit
// jamais, et `GetGuildWarsConfig` ne le prend meme pas en parametre. C'est une contrainte
// d'INTERFACE, appliquee a la SELECTION des unites. En sandbox on choisit soi-meme le roster,
// donc le cap ne s'applique pas -- et si on veut etre fidele, on filtre soi-meme la liste qu'on
// passe ici. Ne PAS aller chercher un gate de rarete dans la BC : il n'y en a pas.
//
// ⚠ LE CATALOGUE NE SE CHOISIT PAS -- IL SE LIT. C'ETAIT LE BLOCAGE #10038.
// `GuildWarsGameModeSource$$LoadBattleInternal` passe a la fabrique, VERIFIE AU DECOMPILE :
//   - `availableMainPlayerUnits` = `this+0xf0`, que le ctor remplit par
//     `GetUsableAndExhaustedUnits(includeMachinesOfWar: TRUE, (WarZoneId, SlotIndex))` ;
//   - `mainPlayerUnits` = **0**, litteralement -- la phase de deploiement choisit.
// Ce module passait la MEME liste choisie aux deux positions, et `includeMow = 0`. Consequences
// mesurees : `BC.Units` ne portait que ces ids, donc toute unite posee au deploiement devenait une
// entite SANS DEFINITION (elle se deplace au premier tour, puis la partie ne progresse plus), et
// aucune Machine of War n'entrait au catalogue. C'est mot pour mot le vice que
// `guild-boss-config.ts` documente en tete : « construire avec des arguments CHOISIS produit une BC
// dont le catalogue ne contient que ce qu'on a passe, alors que le HUD, lui, offre les unites
// deployables du mode ». La sandbox guild boss ne l'a jamais eu parce qu'elle appelle
// `LoadBattleInternal` sur une source FORGEE, qui fait ce remplissage elle-meme.
//
// ⚠ ET L'ADRESSE DU ROSTER EST (WarZoneId, SLOT), PAS (WarZoneId, ZonePart). Le record porte les
// deux (`+0x18` = ZonePartIndex, `+0x1c` = SlotIndex) et le ctor lit `+0x1c`. Le choix naturel est
// donc le mauvais.
//
// ⚠ CE MODULE NE MONTE RIEN. Il rend un JSON. Le montage reste le geste separe et confirme de
// `sandbox.ts` (`sandboxStartBattle`), qui ECRASE le match courant -- d'ou `confirmer` la-bas.

import {
    class_get_name, findClassAnywhere, findCtorByParamCount, findMethod,
    findMethodByParamClasses, findMethodByParamCount, getFieldOffset, methodParamClass,
    methodParamClassName, readIl2cppString, s as cstr,
} from "../il2cpp/helpers.js";
import { createManagedString, il2cpp_object_new, invokeMethod } from "../il2cpp/invoke.js";
import { deserializeFromJson, isDeserializerReady, isSerializerReady, serializeToJson }
    from "../il2cpp/serializer.js";
import { gcRoot } from "../il2cpp/gc-root.js";
import { queueOnMainThread } from "../runtime/queue.js";
import { executeurVivant, Refus as RefusVue } from "./view-command.js";
import { champPointeur, estRefus, refus } from "./lecture-champs.js";
import { getCapturedUniverse } from "./unit-visual-resolve.js";
// La comptabilite du JEU pour << une bataille tourne-t-elle ? >>. Le corps vit dans
// `retreat-capture.ts` -- deux lectures de `get_IsBattleActive` divergeraient en silence.
import { enBataille } from "./retreat-capture.js";
import { Ctx } from "../controller.js";

/** La source FORGEE, retenue entre appels -- et ENRACINEE, sinon le GC la ramasse.
 *  Exposee pour que la delegation du HUD puisse emprunter A LA SOURCE DU MODE plutot qu'a la
 *  campagne : `SandboxGameModeSource$$GetGameModeSpecificDeploymentHudOptions` rend un objet NU
 *  (`supportsMachinesOfWar` reste false), et emprunter a la campagne importerait SES restrictions
 *  -- meme vice que le roster imperial sur un montage PvP. */
let sourceForgeeGw: NativePointer | null = null;

/** Le `BattlefieldZoneTierConfigDto` retenu entre deux etapes de `guildWarEnvEtape` -- il faut
 *  qu'il SURVIVE a l'aller-retour RPC pour que l'etape 4 ne refasse pas l'appel de l'etape 3. */
let dtoZoneRetenu: NativePointer | null = null;

/** Le `GuildWarBattleData` forge, RETENU -- c'est LUI que `StartGuildWarsMatch` prend, pas la
 *  source. Garde a part de `sourceForgeeGw` parce que les deux ne servent pas au meme geste :
 *  la source sert a PREDIRE (forger la BC, preter au deploiement, tout cela gratuit), le record
 *  sert a ENGAGER. Et l'engagement coute une tentative de guilde, au CHARGEMENT. */
let recordForgeGw: NativePointer | null = null;
/** De quoi le record parle -- pour que le RPC d'engagement puisse le DIRE avant d'engager. */
let recordCible: { warZoneId: string; zonePartIndex: number; slotIndex: number } | null = null;

/** La `GuildWarsGameModeSource` forgee, pour les modules qui doivent lui DELEGUER un appel. */
export function sourceGuildWarForgee(): NativePointer | null {
    return sourceForgeeGw;
}

/** Le namespace de la fabrique et de ses satellites. */
const NS_VIEW = "Idun.Source.IdunBattle.View";
/** Celui de la configuration de bataille. */
const NS_CFG = "IdunBattle.Configuration";

/** Les dependances que la fabrique exige, toutes lues sur le `ViewCommandExecutor` VIVANT.
 *  Meme foyer que `sandbox-mode.ts` : leur ABSENCE est un refus NOMME, jamais un appel tente. */
interface Deps {
    prog: NativePointer;            // IUnitProgression
    gameConfig: NativePointer;      // GameConfigDto
    logger: NativePointer;          // IIdunLogger
    featureUnlocker: NativePointer; // IFeatureUnlocker
}

function lireDeps(): Deps | RefusVue {
    const exec = executeurVivant();
    if (estRefus(exec)) return exec;
    const lu: Record<string, NativePointer> = {};
    for (const nom of ["_unitProgression", "_gameConfigData", "_logger", "_featureUnlocker"]) {
        const p = champPointeur(exec as NativePointer, nom);
        if (estRefus(p)) return p;
        if ((p as NativePointer).isNull()) {
            return refus("`" + nom + "` est NUL sur le `ViewCommandExecutor` vivant "
                + "-- le meta n'est pas pleinement monte");
        }
        lu[nom] = p as NativePointer;
    }
    // `_gameConfigData` porte le DTO derriere `get_gameConfigDto` ; la fabrique veut le DTO.
    const kGcd = findClassAnywhere("IdunMetaLogic.Client.DTO.Config", "GameConfigData");
    let dto = lu["_gameConfigData"];
    if (kGcd) {
        const g = findMethod(kGcd, "get_gameConfigDto");
        if (g) {
            try {
                const r = invokeMethod(g.info, lu["_gameConfigData"], []);
                if (r && !r.isNull()) dto = r;
            } catch (e) {
                return refus("`GameConfigData$$get_gameConfigDto` a LEVE : " + (e as Error).message);
            }
        }
    }
    return {
        prog: lu["_unitProgression"], gameConfig: dto,
        logger: lu["_logger"], featureUnlocker: lu["_featureUnlocker"],
    };
}

/** Le `Func<String, IUnitModel>` que la fabrique appelle pour resoudre chaque unite ennemie.
 *
 *  ⚠ IL DOIT AGIR -- `il2cpp/delegate.ts` fabrique des delegues INERTES, ce qui ne convient pas
 *  ici : la fabrique s'en sert pour RESOUDRE, un stub muet rendrait une BC sans ennemis. On le
 *  construit donc sur une methode NATIVE existante, `UnitProgression$$GetUnit(String)`, dont la
 *  signature est exactement `String -> IUnitModel`.
 *
 *  ⚠ Et on passe par son CTOR a deux arguments (`object target, IntPtr method`), pas par une
 *  ecriture de champs : un delegue ne se re-cible pas par ecriture, et c'est le ctor qui
 *  renseigne `invoke_impl` correctement. Le piege n°1 de `delegate.ts` vise `createObject` (qui
 *  invoque le ctor avec `args = null`), pas un ctor correctement arme. */
/** Resolveur d'ennemi : quelle methode NATIVE le delegue enveloppe.
 *
 *  ⚠ LE CHOIX N'EST PAS COSMETIQUE, ET `hero` PERD LA PROGRESSION D'UN NPC.
 *  Mesure du 2026-08-19 : avec `GetUnit`, `necroNpc1Warrior:19` sort a Health 0 /
 *  Damage 0 / Level 1 / Rank 0 -- les 491 npc d'un catalogue forge etaient a zero.
 *  Le decompile dit pourquoi : `UnitProgression$$GetUnit(unitId)` interroge le cache
 *  des HEROS (`this+0x120`) et, sur echec, FABRIQUE un `CachedUnitModel` ; il ne
 *  teste jamais le dictionnaire npc. Le suffixe `:<ProgressionIndex>` n'est donc pas
 *  « ignore » -- il n'est jamais regarde.
 *
 *  CE QUE FAIT LE JEU, verbatim. `GuildWarsGameModeSource$$u003CLoadBattleInternalu003Eb__55_0`
 *  (la lambda que le jeu passe A CE MEME PARAMETRE) appelle son propre
 *  `GetUnitModel(unitId, isPvpEnemyUnit: true)` ; celui-ci cherche d'abord dans les
 *  donnees de la bataille, puis RETOMBE sur l'interface `IUnitProgression` slot 0x1a
 *  avec `(unitId, true)` -- c'est-a-dire `GetUnitOfAnyKind(unitId, stripLevel: true)`.
 *  Et `GetUnitOfAnyKind`, pour un id present au dictionnaire npc, route vers
 *  `GetNpcUnit(unitId)` EN LUI PASSANT L'ID COMPLET, suffixe compris.
 *
 *  POURQUOI ON NE LIE PAS `GetUnitOfAnyKind` DIRECTEMENT : elle a DEUX parametres,
 *  et un `Func<String,IUnitModel>` n'en porte qu'un. Le currying demanderait un
 *  `NativeCallback` -- que `delegate.ts` proscrit explicitement (Frida rentrerait
 *  dans QuickJS depuis un thread natif : gel). On expose donc le choix, plutot que
 *  de le deviner : `hero` (defaut, comportement historique) ou `npc`, qui vise
 *  `GetNpcUnit(String)` -- 1 parametre, exactement la branche ou `GetUnitOfAnyKind`
 *  aboutit pour un npc. Un lineup MIXTE hero+npc n'est donc pas servi par UN seul
 *  delegue ; c'est une limite REELLE, dite ici plutot que masquee. */
export type ResolveurEnnemi = "hero" | "npc";

const METHODE_RESOLVEUR: Record<ResolveurEnnemi, string> = {
    hero: "GetUnit",
    npc: "GetNpcUnit",
};

function construireGetEnemyUnit(m: NativePointer, index: number, prog: NativePointer,
                                resolveur: ResolveurEnnemi = "hero")
    : NativePointer | RefusVue {
    const kFunc = methodParamClass(m, index);
    if (!kFunc || kFunc.isNull()) {
        return refus("classe du parametre " + index + " (`getEnemyUnit`) illisible");
    }
    const kProg = findClassAnywhere("IdunMetaLogic.UserProgress", "UnitProgression");
    if (!kProg) return refus("classe `IdunMetaLogic.UserProgress.UnitProgression` introuvable");
    const nomMethode = METHODE_RESOLVEUR[resolveur];
    if (!nomMethode) {
        return refus("`enemyResolver` inconnu : " + String(resolveur)
            + " -- attendu 'hero' ou 'npc'");
    }
    // 1 parametre EXIGE : c'est ce qui rend la methode liable a `Func<String,IUnitModel>`.
    // Une surcharge a 2+ parametres passerait le controle d'arite du ctor puis lirait un
    // registre non initialise a l'invocation -- donc on lie par le COMPTE, jamais par le nom seul.
    const mGet = findMethodByParamCount(kProg, nomMethode, 1);
    if (!mGet) {
        return refus("`IdunMetaLogic.UserProgress.UnitProgression$$" + nomMethode
            + "(String)` INTROUVABLE sur ce build -- chemin PERIME");
    }
    const ctor = findCtorByParamCount(kFunc, 2);
    if (!ctor) {
        return refus("ctor a 2 parametres introuvable sur `"
            + cstr(class_get_name(kFunc) as NativePointer) + "`");
    }
    const d = il2cpp_object_new(kFunc);
    if (d.isNull()) return refus("allocation du `Func<String,IUnitModel>` a rendu NUL");
    gcRoot.add(d);                                  // cf. `delegate.ts` piege n°2
    // Le 2e argument du ctor est l'`IntPtr method` : c'est le `MethodInfo*`, donc `.info`.
    const argMethod = Memory.alloc(Process.pointerSize);
    argMethod.writePointer(mGet.info);
    invokeMethod(ctor.info, d, [prog, argMethod]);
    return d;
}

/** Construit une valeur managee a partir de JSON, en visant la classe du parametre `index`.
 *  C'est la technique de `sandbox-mode.ts` : on ne recopie AUCUNE signature ici -- la classe est
 *  lue au runtime, donc un renumerotage inter-build donne un refus nomme, pas un decalage muet. */
function depuisJson(m: NativePointer, index: number, json: string): NativePointer | RefusVue {
    const k = methodParamClass(m, index);
    if (!k || k.isNull()) return refus("classe du parametre " + index + " illisible");
    try {
        const v = deserializeFromJson(json, k);
        if (v.isNull()) {
            return refus("parametre " + index + " : la deserialisation a rendu NUL -- JSON "
                + "incompatible avec `" + cstr(class_get_name(k) as NativePointer) + "`");
        }
        return v;
    } catch (e) {
        return refus("parametre " + index + " : " + (e as Error).message);
    }
}

/** `List<IUnitModel>` : une interface ne se deserialise pas. On alloue la liste (classe du
 *  parametre, donc deja inflatee) et on y AJOUTE les modeles resolus par le jeu lui-meme. */
function listeDeModeles(m: NativePointer, index: number, prog: NativePointer, ids: string[])
    : NativePointer | RefusVue {
    const k = methodParamClass(m, index);
    if (!k || k.isNull()) return refus("classe du parametre " + index + " illisible");
    const kProg = findClassAnywhere("IdunMetaLogic.UserProgress", "UnitProgression");
    const mGet = kProg ? findMethodByParamCount(kProg, "GetUnit", 1) : null;
    if (!mGet) return refus("`UnitProgression$$GetUnit(String)` INTROUVABLE");
    const ctor = findCtorByParamCount(k, 0);
    if (!ctor) return refus("ctor sans parametre introuvable sur la liste du parametre " + index);
    const lst = il2cpp_object_new(k);
    if (lst.isNull()) return refus("allocation de la liste du parametre " + index + " a rendu NUL");
    gcRoot.add(lst);
    invokeMethod(ctor.info, lst, []);
    const add = findMethodByParamCount(k, "Add", 1);
    if (!add) return refus("`Add` introuvable sur la liste du parametre " + index);
    const absents: string[] = [];
    for (const id of ids) {
        const mdl = invokeMethod(mGet.info, prog, [createManagedString(id)]);
        if (!mdl || mdl.isNull()) { absents.push(id); continue; }
        invokeMethod(add.info, lst, [mdl]);
    }
    if (absents.length > 0) {
        return refus("unites INCONNUES de la progression du compte : " + absents.join(", ")
            + " -- une unite non possedee n'a pas de `IUnitModel`, elle ne peut pas entrer dans "
            + "`availableMainPlayerUnits`");
    }
    return lst;
}

/** La `GuildWarPhaseProgression` VIVANTE, par le champ nomme de l'executeur.
 *
 *  ⚠ NE PAS conclure de `_liveEventState == null` que la progression est VIDE. Mesure du
 *  2026-08-18 : les deux champs `_liveEvent` / `_liveEventState` de
 *  `SingleLiveEventBasedProgression` sont NULS alors que `GetAttemptsLeft()` rend 10 et
 *  `GetGuildWarIdEvenIfItHasntStartedYet()` un GUID valide. L'etat est resolu A LA DEMANDE par la
 *  cascade `ILiveEventsProgression`, pas mis en cache dans ces champs. Un lecteur qui teste le
 *  champ conclurait « pas de guerre en cours » a tort -- c'est exactement l'erreur que ce
 *  commentaire existe pour empecher. Le discriminant est un APPEL, pas un champ. */
function progressionPhase(): NativePointer | RefusVue {
    const exec = executeurVivant();
    if (estRefus(exec)) return exec;
    const p = champPointeur(exec as NativePointer, "_guildWarPhaseProgression");
    if (estRefus(p)) return p;
    if ((p as NativePointer).isNull()) {
        return refus("`_guildWarPhaseProgression` est NUL sur l'executeur vivant");
    }
    return p as NativePointer;
}

/**
 * L'ADRESSE DE BATAILLE que le jeu passe au roster : `Nullable<ValueTuple<String, Int32>>`.
 *
 * ⚠ RELEVEE AU DECOMPILE, PAS DEDUITE. `GuildWarsGameModeSource$$.ctor` construit un
 * `ValueTuple` a partir de `battleData+0x10` (WarZoneId) et `battleData+0x1c` (SlotIndex) --
 * donc (zone, SLOT), et surtout PAS `ZonePartIndex` (`+0x18`), qui serait le choix naturel et
 * serait FAUX. Il enveloppe ensuite le tuple dans un `Nullable` de 24 octets, dont il relit les
 * trois mots avant de le passer.
 *
 * ⚠ ET `hasValue` EST EN TETE, PAS EN QUEUE -- L'ADRESSE DE LA FAUTE L'A ETABLI.
 * La disposition « naturelle » (`{ value @0 ; hasValue @0x10 }`) fait lever
 * `access violation accessing 0x11`, mesure du 2026-08-18. Ce `0x11` n'est pas du bruit : c'est
 * `0x1 + 0x10`, soit le natif prenant le `slotIndex` (valeur 1, ecrite a `+8`) pour un `String*`
 * et lisant sa longueur au `+0x10` d'un `System.String`. Il lit donc `Item1` a `+8`, ce qui ne
 * laisse qu'une place pour le drapeau : la tete. C'est aussi ce que dit la source .NET, ou
 * `Nullable<T>` declare `private readonly bool hasValue;` AVANT `internal readonly T value;`.
 *
 * Disposition retenue : `{ hasValue @0 (bourre a 8), Item1 : String @8, Item2 : Int32 @0x10 }`.
 * Une zone a ZERO vaut « pas d'adresse » dans les DEUX lectures -- c'est pourquoi le buffer nul
 * que ce module passait jusqu'ici n'a jamais fauté, et n'a jamais rien prouve non plus.
 */
function adresseBataille(warZoneId?: string, slotIndex = 0): NativePointer {
    const p = Memory.alloc(24);
    p.writeByteArray(new Array(24).fill(0));
    if (warZoneId !== undefined) {
        const s = createManagedString(warZoneId);
        gcRoot.add(s);                       // la boite n'est PAS une racine GC : l'ancrer
        p.writeU8(1);                        // hasValue, EN TETE
        p.add(8).writePointer(s);            // ValueTuple.Item1 : String
        p.add(0x10).writeS32(slotIndex);     // ValueTuple.Item2 : Int32
    }
    return p;
}

/**
 * LE ROSTER DE GUERRE TEL QUE LA FABRIQUE LE RECOIT -- celui du JEU, jamais celui qu'on choisit.
 *
 * ⚠ C'EST LE FOYER DU BLOCAGE #10038, ET LE DECOMPILE LE NOMME. `LoadBattleInternal` passe en
 * `availableMainPlayerUnits` le champ `this+0xf0` de la source, que son ctor remplit par
 * `GetUsableAndExhaustedUnits(includeMachinesOfWar: TRUE, adresse)`. Ce module passait a la place
 * une `List<IUnitModel>` batie sur les ids CHOISIS par l'appelant, et `includeMow = 0`. Deux
 * consequences, toutes deux mesurees :
 *
 *   - `BC.Units` (le CATALOGUE) ne contenait que ces ids. Poser au deploiement une unite absente
 *     du catalogue cree une entite SANS DEFINITION : elle se deplace au premier tour et la partie
 *     ne progresse plus. C'est le vice que `guild-boss-config.ts` documente en tete -- meme cause,
 *     meme signature.
 *   - aucune Machine of War n'entrait dans le catalogue, d'ou le slot MoW vide.
 *
 * ⚠ Le retour est un `ValueTuple` a trois champs, donc un TYPE VALEUR : `il2cpp_runtime_invoke`
 * le rend BOXE, et les references vivent a `+0x10` (utilisables), `+0x18` (epuisees), `+0x20`.
 */
function rosterDeGuerre(k: NativePointer, sur: NativePointer, inclureMow: boolean,
                        warZoneId?: string, slotIndex = 0):
    { utilisables: NativePointer; epuisees: NativePointer } | RefusVue {
    const m = findMethodByParamCount(k, "GetUsableAndExhaustedUnits", 2);
    if (!m) {
        return refus("`GuildWarPhaseProgression$$GetUsableAndExhaustedUnits` a 2 parametres "
            + "INTROUVABLE -- chemin PERIME, on ne bricole pas un roster de remplacement");
    }
    const mow = Memory.alloc(1);
    mow.writeU8(inclureMow ? 1 : 0);
    let boite: NativePointer;
    try {
        boite = invokeMethod(m.info, sur, [mow, adresseBataille(warZoneId, slotIndex)]);
    } catch (e) {
        return refus("`GetUsableAndExhaustedUnits` a LEVE : " + (e as Error).message);
    }
    if (boite.isNull()) return refus("`GetUsableAndExhaustedUnits` a rendu NUL");
    gcRoot.add(boite);
    const utilisables = boite.add(0x10).readPointer();
    if (utilisables.isNull()) {
        return refus("`GetUsableAndExhaustedUnits` a rendu un tuple dont les UTILISABLES sont "
            + "NULS -- roster vide, la fabrique produirait un catalogue vide");
    }
    return { utilisables, epuisees: boite.add(0x18).readPointer() };
}

/** L'element `i` d'une `List<T>` managee. `+0x10` = tableau, `+0x18` = taille ; les elements
 *  commencent a `+0x20` du tableau. Rend un refus NOMME plutot que de lire hors bornes. */
function elementDeListe(lst: NativePointer, i: number): NativePointer | RefusVue {
    if (lst.isNull()) return refus("liste NULLE");
    const arr = lst.add(0x10).readPointer();
    const n = lst.add(0x18).readS32();
    if (arr.isNull()) return refus("liste sans tableau interne");
    if (i < 0 || i >= n) return refus(`index ${i} hors bornes (taille ${n})`);
    return arr.add(0x20 + i * Process.pointerSize).readPointer();
}

/** Le champ NOMME d'un objet manage, en refusant par son nom quand il n'existe pas. */
function champ(obj: NativePointer, nom: string): NativePointer | RefusVue {
    const p = champPointeur(obj, nom);
    if (estRefus(p)) return p;
    return p as NativePointer;
}

/** Appelle une methode `(warZoneType) -> Dto` de la progression, l'enum BOXEE.
 *
 *  ⚠ NI `il2cpp_runtime_invoke`, NI L'ORDINAL BRUT -- les deux ont ete mesures fautifs
 *  (cf. le pave de `guildWarProbe`) : le natif attend l'enum PAR VALEUR en registre, et la cle
 *  du dictionnaire gshared qu'il interroge est un OBJET. On appelle donc l'ENTRY POINT, avec la
 *  convention IL2CPP reelle `(this, args..., const MethodInfo*)`, sur une valeur BOXEE. */
function appelParTypeDeZone(
    m: { ptr: NativePointer; info: NativePointer }, sur: NativePointer,
    kWzt: NativePointer, ord: number,
): NativePointer | null {
    const boite = il2cpp_object_new(kWzt);
    if (boite.isNull()) return null;
    gcRoot.add(boite);
    boite.add(0x10).writeS32(ord);
    // `propagate` : appel MANAGE, cf. `il2cpp/invoke.ts`.
    const fn = new NativeFunction(m.ptr, "pointer", ["pointer", "pointer", "pointer"],
                                  { exceptions: "propagate" });
    try { return fn(sur, boite, m.info) as NativePointer; } catch { return null; }
}

/** LE CAP DE RARETE DU SLOT, et l'ordinal de type de zone qui l'a donne.
 *
 *  Trois sauts, tous natifs -- `battlefieldLevel` -> `zoneTiers[warZoneType]` -> `zoneTierId` ->
 *  `rarityCaps[slot]` -- et on n'en refait AUCUN a la main : `GetZoneConfig(warZoneType)` rend le
 *  `BattlefieldZoneTierConfigDto`, `BattlefieldZoneTierConfigDtoExtensions$$GetRarityCap(cfg,
 *  slotIndex)` en tire celui du slot. C'est le meme couple que la popup appelle.
 *
 *  ⚠ L'ORDINAL DE `WarZoneType` NE SE DEVINE PAS -- il est ABSENT de la table des enums
 *  (Newtonsoft le serialise par NOM), et le `Nullable` porte par la zone a rendu `1`, valeur qui
 *  fait LEVER les deux configs. On le DERIVE donc par CONFRONTATION : pour chaque ordinal,
 *  `GetWarZoneConfig(ord).boardId` est compare au board qu'on vise deja. Celui qui concorde EST
 *  le type de la zone. Zero concordance = refus NOMME, jamais un ordinal par defaut. */
function capDeRarete(
    kProg: NativePointer, prog: NativePointer, boardVoulu: string, slotIdx: number,
): { cap: number; ordinal: number } | RefusVue {
    const kWzt = findClassAnywhere("Idun.Source.IdunMeta.Logic.UserProgress.GuildWars",
                                   "WarZoneType");
    if (!kWzt) return refus("classe `WarZoneType` introuvable -- chemin PERIME");
    const mCfgZone = findMethodByParamCount(kProg, "GetWarZoneConfig", 1);
    if (!mCfgZone) return refus("`GetWarZoneConfig(1)` INTROUVABLE -- chemin PERIME");

    let ordinal = -1;
    const vus: string[] = [];
    // ⚠ BORNE 16, ET C'EST LA BORNE MESUREE -- pas un arrondi. `guildWarProbe` balaye `ord < 16`
    // depuis sa mise au point, et le gameconfig declare **15** types de zone. Je l'avais elargie
    // a 32 « pour etre sur » : le jeu a CRASHE (dump `Tacticus.exe.30620.dmp`, 2026-08-21
    // 14:19). Elargir un balayage d'ordinaux au-dela du domaine mesure, c'est appeler un natif
    // avec une valeur qu'aucune mesure n'autorise.
    for (let ord = 0; ord < 16; ord++) {
        const c = appelParTypeDeZone(mCfgZone, prog, kWzt, ord);
        if (c === null || c.isNull()) continue;
        let bid: string | null = null;
        try {
            const p = c.add(0x10).readPointer();
            bid = p.isNull() ? null : readIl2cppString(p);
        } catch { /* publie plus bas */ }
        if (bid !== null) vus.push(`${ord}:${bid}`);
        if (bid === boardVoulu) { ordinal = ord; break; }
    }
    if (ordinal < 0) {
        return refus(`aucun ordinal de \`WarZoneType\` ne rend le board \`${boardVoulu}\` `
            + `-- balaye 0..31, vus : ${vus.join(", ") || "aucun"}. On ne DEVINE pas un ordinal.`);
    }

    const mZoneCfg = findMethodByParamCount(kProg, "GetZoneConfig", 1);
    if (!mZoneCfg) return refus("`GetZoneConfig(1)` INTROUVABLE -- chemin PERIME");
    const dto = appelParTypeDeZone(mZoneCfg, prog, kWzt, ordinal);
    if (dto === null || dto.isNull()) {
        return refus(`\`GetZoneConfig(${ordinal})\` a rendu NUL pour \`${boardVoulu}\``);
    }
    gcRoot.add(dto);

    const kExtCap = findClassAnywhere("Idun.Source.IdunMeta.Logic.UserProgress.GuildWars",
                                      "BattlefieldZoneTierConfigDtoExtensions");
    if (!kExtCap) return refus("classe `BattlefieldZoneTierConfigDtoExtensions` introuvable");
    const mCap = findMethodByParamCount(kExtCap, "GetRarityCap", 2);
    if (!mCap) return refus("`GetRarityCap(2)` INTROUVABLE -- signature CHANGEE sur ce build");
    const pSlot = Memory.alloc(4); pSlot.writeS32(slotIdx);
    let cap: number;
    try {
        // ⚠ RETOUR BOXE : `il2cpp_runtime_invoke` rend un OBJET dont la valeur est a `+0x10`.
        // Lire le pointeur comme un entier rendrait une adresse tronquee (mesure #10038).
        const r = invokeMethod(mCap.info, null, [dto, pSlot]);
        if (r.isNull()) return refus("`GetRarityCap` a rendu NUL");
        cap = r.add(0x10).readS32();
    } catch (e) { return refus("`GetRarityCap` a LEVE : " + (e as Error).message); }
    return { cap, ordinal };
}

/** ARMER l'environnement depuis les BUFFS ACTIFS de la zone -- mirror de la boucle de
 *  `ShowGuildWarsBattlePreviewPopupCommand$$OnStartBattleButtonClicked`.
 *
 *  Pour chaque `WarZoneBuffData` :
 *    - `buffAbilityConfig[<cap de rarete>]` donne l'`AbilityConfiguration` du buff. LA CLE EST LE
 *      CAP : c'est pour ca que le cap et l'environnement ne peuvent pas etre traites separement ;
 *    - `triggeredAbilityType` donne le `TriggeredAbilityConfigId` ;
 *    - `buffAmount` donne le NIVEAU -- c'est lui qui choisit dans les tableaux de variables du
 *      gameconfig. Pour `EnvArtillerySupport`, `nrOfProjectiles: ["1","2","3","4","5"]` : niveau 3
 *      = TROIS salves. Un niveau nul n'arme rien, comme dans le natif.
 *
 *  ⚠ LE CLAMP EXPLICITE DE LA POPUP N'EST PAS REPRIS, ET C'EST DELIBERE. Elle borne le niveau au
 *  plus court tableau de variables de la config ; or `AbilityConfiguration$$TryGetVariableArrayForLevel`
 *  -- foyer UNIQUE des quatre accesseurs -- clampe DEJA en aval (`idx >= len` -> `len - 1`). Le
 *  reimplementer ici serait un second comptage a maintenir, du genre qui finit par diverger.
 *
 *  ⚠ Les deux structs sont ecrites PAR CHAMP NOMME plutot que par leurs ctors : `Level` n'a qu'un
 *  `val:Int32` et `TriggeredAbilityConfigId` qu'un `AbilityType` + un `VariantId` nul. Les offsets
 *  sont RESOLUS par `getFieldOffset`, jamais ecrits en dur. */
function armerBuffsDeZone(
    kProg: NativePointer, prog: NativePointer, warZoneId: string,
    rarityCap: number, env: NativePointer, detail: Array<Record<string, unknown>>,
): true | RefusVue {
    const mBuffs = findMethodByParamCount(kProg, "GetActiveBuffs", 1);
    if (!mBuffs) return refus("`GetActiveBuffs(1)` INTROUVABLE -- chemin PERIME");
    let buffs: NativePointer;
    try { buffs = invokeMethod(mBuffs.info, prog, [createManagedString(warZoneId)]); }
    catch (e) { return refus("`GetActiveBuffs` a LEVE : " + (e as Error).message); }
    if (buffs.isNull()) return refus("`GetActiveBuffs` a rendu NUL -- pas de liste a parcourir");
    gcRoot.add(buffs);

    const kEac = findClassAnywhere(NS_CFG, "EnvironmentAbilityConfiguration");
    const kTid = findClassAnywhere("IdunShared", "TriggeredAbilityConfigId");
    if (!kEac) return refus("classe `EnvironmentAbilityConfiguration` introuvable");
    if (!kTid) return refus("classe `TriggeredAbilityConfigId` introuvable");
    const offCfgId = getFieldOffset(kEac, "ConfigId");
    const offLevel = getFieldOffset(kEac, "Level");
    const offType = getFieldOffset(kTid, "AbilityType");
    const offVariant = getFieldOffset(kTid, "VariantId");
    if (offCfgId < 0 || offLevel < 0 || offType < 0 || offVariant < 0) {
        return refus("champ(s) absent(s) sur ce build : "
            + `ConfigId=${offCfgId} Level=${offLevel} AbilityType=${offType} `
            + `VariantId=${offVariant} -- chemin PERIME, pas de repli sur un offset`);
    }
    // Le receptacle que le ctor d'`EnvironmentAbilities` a cree pour nous.
    const listeAb = champ(env, "Abilities");
    if (estRefus(listeAb)) return listeAb as RefusVue;

    const n = buffs.add(0x18).readS32();
    for (let i = 0; i < n; i++) {
        const b = elementDeListe(buffs, i);
        if (estRefus(b)) return b as RefusVue;
        const buff = b as NativePointer;
        if (buff.isNull()) continue;

        // LECTURE PURE des deux scalaires du buff, par offset RESOLU sur sa classe reelle.
        const kBuff = buff.readPointer();
        const offType2 = getFieldOffset(kBuff, "<triggeredAbilityType>k__BackingField");
        const offAmount = getFieldOffset(kBuff, "<buffAmount>k__BackingField");
        if (offType2 < 0 || offAmount < 0) {
            return refus("`WarZoneBuffData` : `triggeredAbilityType`/`buffAmount` non resolus "
                + `(${offType2}/${offAmount}) -- chemin PERIME`);
        }
        const abilityType = buff.add(offType2).readS32();
        const niveau = buff.add(offAmount).readS32();

        // ⛔ `AbilitiesConfigurations` N'EST PAS PEUPLE ICI, ET C'EST UN CHOIX MOTIVE.
        //
        // La popup y range la config du buff, tiree de `buffAbilityConfig[<cap de rarete>]` --
        // un `Dictionary` dont la cle est un TYPE VALEUR. L'appeler exige de trancher entre
        // « pointeur vers la valeur » et « valeur BOXEE », et se tromper ne leve pas : le natif
        // DEREFERENCE l'ordinal. C'est ce qui a fait CRASHER le jeu le 2026-08-21 (dump
        // `Tacticus.exe.30620.dmp`, 14:19) -- j'avais passe une cle NON boxee, exactement ce que
        // le pave de `guildWarProbe` interdit en capitales.
        //
        // On s'en passe parce que la BC porte DEJA le catalogue : mesure sur le replay d'un
        // montage DogAlpha, `BC.Abilities.EnvironmentAbilities` = **166 definitions**, dont
        // `EnvArtillerySupport` avec ses variables (`nrOfProjectiles`, `hpPct`). La config du
        // buff y est donc deja resolvable par son id ; ce que l'accumulateur doit apporter, c'est
        // l'ABILITY et son NIVEAU.
        //
        // ⚠ CE N'EST PAS ETABLI, C'EST UNE HYPOTHESE A EPROUVER -- et son oracle est net : trois
        // salves d'artillerie au debut de la partie (`nrOfProjectiles[3]`). Si elles ne tirent
        // pas, c'est que le dictionnaire est necessaire, et il faudra alors trancher la
        // convention de cle par une mesure, pas par un essai sur la partie de l'utilisateur.

        if (niveau === 0) {
            detail.push({ abilityType, niveau, arme: false,
                          raison: "niveau 0 -- le natif n'arme pas non plus" });
            continue;
        }
        // `Abilities += EnvironmentAbilityConfiguration { ConfigId, Level }`
        //
        // Les deux structs sont ECRITES INLINE plutot que construites par leurs ctors : `Level`
        // n'a qu'un `val:Int32` et `TriggeredAbilityConfigId` qu'un `AbilityType` + un
        // `VariantId` (nul ici). Les offsets INTERNES se retranchent de `0x10`, l'en-tete que
        // porte la version BOXEE de la struct mais pas sa version INLINE.
        const eac = il2cpp_object_new(kEac);
        if (eac.isNull()) return refus("allocation d'`EnvironmentAbilityConfiguration` a rendu NUL");
        gcRoot.add(eac);
        eac.add(offCfgId + (offType - 0x10)).writeS32(abilityType);
        eac.add(offCfgId + (offVariant - 0x10)).writePointer(NULL);
        eac.add(offLevel).writeS32(niveau);
        const la = listeAb as NativePointer;
        const mAddL = findMethodByParamCount(la.readPointer(), "Add", 1);
        if (!mAddL) return refus("`List.Add(1)` INTROUVABLE sur `Abilities`");
        try { invokeMethod(mAddL.info, la, [eac]); }
        catch (e) { return refus("`Abilities.Add` a LEVE : " + (e as Error).message); }
        detail.push({ abilityType, niveau, rarityCap, arme: true });
    }
    return true;
}

/** BORNE HAUTE d'exploration des indices de zone.
 *
 *  ⚠ CE N'EST PAS LE NOMBRE DE ZONES, et la version precedente confondait les deux : elle
 *  bouclait `idx < 12` en dur. Mesure du 2026-08-19 (`t6dpr4k06g`) : `GetWarZone(aff, idx)` rend
 *  un objet jusqu'a l'indice **14**, et `GetBattlefieldConfig().battlefieldLevels[].zoneTiers`
 *  declare **15** types de zone -- `Trenches1/2/3`, `HQ`, `ArtilleryPosition1/2`, `LandingPad1/2`,
 *  `Armoury`, `Bunker1/2`, `SupplyDepot`, `MedicaeStation1/2`, `AntiAirBattery`. Le `12` jetait
 *  donc `HQ`, `MedicaeStation1` et `MedicaeStation2` -- UN CINQUIEME DE LA CARTE -- et il le
 *  faisait EN SILENCE : le RPC publiait `total: 36` (3 x 12), un compte parfaitement coherent
 *  avec lui-meme et faux. Un occupant reel (`Drakar69`, `MedicaeStation1`) etait donc introuvable,
 *  et le lecteur en concluait « il ne defend rien » -- exactement le vice que le depot nomme
 *  « une liste TRONQUEE fait conclure a une ABSENCE ».
 *
 *  On explore donc LARGE et on CONFRONTE au compte declare par le jeu (`nbTypesDeZone`). */
const PLAFOND_INDEX_ZONE = 64;

/** Le nombre de types de zone que le JEU declare, ou `null` si non mesurable.
 *
 *  Source : `GuildWarPhaseProgression$$GetBattlefieldConfig()` ->
 *  `GuildWarBattlefieldConfigDto.battlefieldLevels[].zoneTiers`. Tous les niveaux portent la meme
 *  liste ; on prend le maximum, pour qu'un niveau tronque ne rabaisse pas l'attendu. */
function nbTypesDeZone(k: NativePointer, sur: NativePointer): number | null {
    const r = appeler(k, sur, "GetBattlefieldConfig", 0, []);
    if (estRefus(r)) return null;
    const j = enJson(r as NativePointer) as Record<string, unknown> | null;
    if (j === null || typeof j !== "object") return null;
    const niveaux = j.battlefieldLevels;
    if (!Array.isArray(niveaux)) return null;
    let max = 0;
    for (const n of niveaux) {
        const t = (n as Record<string, unknown>)?.zoneTiers;
        if (Array.isArray(t) && t.length > max) max = t.length;
    }
    return max > 0 ? max : null;
}

/** Invoque une methode d'instance NOMMEE et rend son retour, ou un refus NOMME. */
function appeler(k: NativePointer, sur: NativePointer, nom: string, nbArgs: number,
                 args: NativePointer[]): NativePointer | RefusVue {
    const m = findMethodByParamCount(k, nom, nbArgs);
    if (!m) return refus("`GuildWarPhaseProgression$$" + nom + "` a " + nbArgs
        + " parametre(s) INTROUVABLE -- chemin PERIME sur ce build");
    try {
        return invokeMethod(m.info, sur, args);
    } catch (e) {
        return refus("`" + nom + "` a LEVE : " + (e as Error).message);
    }
}

/** Serialise un objet manage, ou dit pourquoi il ne l'est pas. */
function enJson(p: NativePointer | RefusVue): unknown {
    if (estRefus(p)) return { erreur: (p as RefusVue).error };
    if ((p as NativePointer).isNull()) return null;
    try {
        const j = serializeToJson(p as NativePointer);
        return j === null ? { erreur: "serialisation NULLE" } : JSON.parse(j);
    } catch (e) {
        return { erreur: (e as Error).message };
    }
}

export function register(ctx: Ctx): void {
    /** LE `GuildWarConfigDto` COMPLET -- donc `zoneTypeConfigs`, donc LES CARTES.
     *
     *  POURQUOI PAR CETTE VOIE, ET PAS PAR `GetWarZoneConfig`
     *  ------------------------------------------------------
     *  `GuildWarPhaseProgression$$GetWarZoneConfig(warZoneType)` fait un lookup dans
     *  `cfg.zoneTypeConfigs` via `CollectionExtensions$$GetValueOrDefault`, un generique
     *  PLEINEMENT PARTAGE (`__Il2CppFullySharedGenericType`). Ce lookup DEREFERENCE sa cle, et
     *  aucune des trois formes d'appel ne passe la barriere du thunk -- mesure du 2026-08-18,
     *  16 ordinaux balayes a chaque fois :
     *    - `il2cpp_runtime_invoke` + valeur  -> `access violation accessing 0x219_0000000<ord>`
     *      (l'ordinal RECOLLE a un fragment de pointeur de tas) ;
     *    - entry point + valeur en registre  -> `access violation accessing 0x<ord>` ;
     *    - entry point + cle BOXEE           -> `0x<ord>` encore.
     *  Le temoin qui tranche est `ord = 0` : il NE PLANTE PAS et rend `null`, parce que 0 est
     *  le seul ordinal dont le dereferencement est benin. Le natif lit donc bien la cle comme
     *  une ADRESSE.
     *
     *  Plutot que de forcer ce thunk, on prend l'objet EN AMONT : `cfg` est passe en argument a
     *  `GuildWarsScoreCalculator$$GetAllPossibleScores`, qui est STATIQUE et NON generique. On
     *  l'ancre, on declenche `GuildWarPhaseProgression$$GetAllPossibleScores()` (0 argument,
     *  donc invocable sans piege de convention), on recupere `cfg`, on DETACHE, puis on
     *  serialise. Newtonsoft rend alors `zoneTypeConfigs` clefs PAR NOM -- ce qui supprime du
     *  meme coup le besoin de connaitre l'ordinal de `WarZoneType`, absent du dump.
     *
     *  ⚠ Le handler d'ancrage ne fait QUE deposer un pointeur : aucun appel natif, aucun travail
     *  JS. C'est la seule forme sure quand on ancre une methode situee dans la chaine de celle
     *  qu'on invoque -- « le natif depose, le pump ramasse ». Et il DETACHE avant tout usage. */
    ctx.rpc.guildWarZoneConfigs = (): Promise<unknown> => queueOnMainThread(() => {
        const prog = progressionPhase();
        if (estRefus(prog)) return { ok: false, error: (prog as RefusVue).error };
        const kProg = findClassAnywhere("Idun.Source.IdunMeta.Logic.UserProgress.GuildWars",
                                        "GuildWarPhaseProgression");
        const kCalc = findClassAnywhere("Idun.Source.IdunMeta.Logic.UserProgress.GuildWars",
                                        "GuildWarsScoreCalculator");
        if (!kProg || !kCalc) {
            return { ok: false, error: "classe manquante : "
                + `progression=${kProg !== null} calculateur=${kCalc !== null}` };
        }
        const mCalc = findMethodByParamCount(kCalc, "GetAllPossibleScores", 1);
        const mProg = findMethodByParamCount(kProg, "GetAllPossibleScores", 0);
        if (!mCalc || !mProg) {
            return { ok: false, error: "`GetAllPossibleScores` INTROUVABLE : "
                + `calculateur(1)=${mCalc !== null} progression(0)=${mProg !== null}` };
        }

        let cfg: NativePointer | null = null;
        const ancre = Interceptor.attach(mCalc.ptr, {
            onEnter(args) { cfg = args[0]; },      // DEPOSE, rien d'autre
        });
        let leve: string | null = null;
        try {
            invokeMethod(mProg.info, prog as NativePointer, []);
        } catch (e) {
            leve = (e as Error).message;
        }
        ancre.detach();                            // DETACHER avant tout usage
        Interceptor.flush();

        if (cfg === null || (cfg as NativePointer).isNull()) {
            return { ok: false,
                error: "`cfg` NON CAPTURE -- `GetAllPossibleScores` n'a pas atteint le "
                    + "calculateur (guerre non demarree ?)",
                leve };
        }
        const c = cfg as NativePointer;
        const dico = c.add(0x40).readPointer();     // `zoneTypeConfigs`, offset MESURE
        return {
            ok: true,
            cfg: c.toString(),
            zoneTypeConfigsNul: dico.isNull(),
            config: enJson(c),
            leve,
        };
    });

    /** LIT la guerre de guilde EN COURS : cibles, zone, slot defensif, buffs.
     *
     *  Aucune ecriture, aucun appel reseau -- ces methodes lisent la progression deja resolue
     *  cote client. C'est la MEME forme que `guild-boss-config.ts`, et c'est ce qui evite
     *  d'INVENTER une carte ou une equipe adverse. */
    ctx.rpc.guildWarBoardRead = (body?: {
        warZoneId?: string; zonePartIndex?: number; slotIndex?: number;
    }): Promise<unknown> => queueOnMainThread(() => {
        const prog = progressionPhase();
        if (estRefus(prog)) return { ok: false, error: (prog as RefusVue).error };
        const sur = prog as NativePointer;
        const k = findClassAnywhere("Idun.Source.IdunMeta.Logic.UserProgress.GuildWars",
                                    "GuildWarPhaseProgression");
        if (!k) return { ok: false, error: "classe `GuildWarPhaseProgression` introuvable" };

        const i32 = (v: number) => { const p = Memory.alloc(4); p.writeS32(v); return p; };
        /** ⚠ `il2cpp_runtime_invoke` BOXE les types valeur : il rend un OBJET dont la valeur est
         *  a `+0x10`, pas un entier. Caster le pointeur avec `.toInt32()` rend l'adresse tronquee
         *  -- mesure du 2026-08-18 : `GetAttemptsLeft` a rendu `1176113984` la ou `viewInvoke`,
         *  qui deboxe correctement, rendait `10`. Toujours lire A TRAVERS la boite. */
        const lireInt = (nom: string): number | string => {
            const m = findMethodByParamCount(k, nom, 0);
            if (!m) return "INTROUVABLE";
            try {
                const r = invokeMethod(m.info, sur, []);
                return r.isNull() ? "NUL" : r.add(0x10).readS32();
            } catch (e) {
                return "LEVE: " + (e as Error).message;
            }
        };

        const res: Record<string, unknown> = {
            ok: true,
            guildWarId: enJson(appeler(k, sur, "GetGuildWarIdEvenIfItHasntStartedYet", 0, [])),
            attemptsLeft: lireInt("GetAttemptsLeft"),
            targets: enJson(appeler(k, sur, "GetTargets", 0, [])),
            battlefieldConfig: enJson(appeler(k, sur, "GetBattlefieldConfig", 0, [])),
            // LE ROSTER D'UNE GUERRE N'EST PAS LE ROSTER DU COMPTE : une unite ENGAGEE dans un
            // combat de guerre est EPUISEE et ne peut plus repartir. C'est le jeu qui tient cette
            // liste (`ExhaustUnits` l'alimente a chaque envoi), donc on la LIT au lieu de la
            // deviner -- un ecran de deploiement rempli du roster complet proposerait des unites
            // que le jeu refuse.
            exhaustedUnits: enJson(appeler(k, sur, "GetExhaustedUnits", 0, [])),
        };

        // LE ROSTER QUE L'ECRAN DOIT AFFICHER, tel que l'UI le calcule elle-meme.
        //
        // `GetExhaustedUnits()` ci-dessus rend la liste des unites DEJA ENGAGEES dans la guerre.
        // ⚠ Une liste VIDE y est une reponse LEGITIME (aucune bataille jouee dans cette guerre),
        // pas le signe d'un accesseur muet -- verifie aupres de l'utilisateur le 2026-08-18, apres
        // que je l'aie soupconnee a tort par analogie avec `GetWarZoneSlot`. Ne pas re-suspecter
        // cette methode sans avoir d'abord etabli qu'une unite A ete engagee.
        //
        // `GetUsableAndExhaustedUnits` donne les DEUX faces d'un coup, et c'est elle qui fait foi
        // pour remplir l'ecran : `utilisables` = roster du compte MOINS les epuisees. Elle prend
        // une adresse de bataille (`Nullable<ValueTuple<String,Int32>>`) -- on la passe VIDE, donc
        // « pas de zone particuliere ».
        //
        // Le retour est un `ValueTuple<List<IUnitModel>, List<IUnitModel>, Dictionary<...>>`, donc
        // un TYPE VALEUR : `il2cpp_runtime_invoke` le rend BOXE, et les trois references vivent
        // a `+0x10`, `+0x18`, `+0x20` de la boite.
        const mUse = findMethodByParamCount(k, "GetUsableAndExhaustedUnits", 2);
        if (mUse) {
            const inclureMow = Memory.alloc(1); inclureMow.writeU8(0);
            const adresse = Memory.alloc(24); adresse.writeByteArray(new Array(24).fill(0));
            try {
                const boite = invokeMethod(mUse.info, sur, [inclureMow, adresse]);
                if (boite.isNull()) {
                    res.usableEtEpuisees = { erreur: "retour NUL" };
                } else {
                    res.usableEtEpuisees = {
                        utilisables: enJson(boite.add(0x10).readPointer()),
                        epuisees: enJson(boite.add(0x18).readPointer()),
                    };
                }
            } catch (e) {
                res.usableEtEpuisees = { erreur: (e as Error).message.slice(0, 120) };
            }
        } else {
            res.usableEtEpuisees = { erreur: "`GetUsableAndExhaustedUnits` a 2 parametres INTROUVABLE" };
        }

        // ENUMERER les zones : `GetTargets()` ne rend que les cibles MARQUEES par la guilde (elle
        // rend `[]` quand personne n'a marque), donc elle ne peut pas servir d'inventaire. La voie
        // qui inventorie est `GetWarZone(affiliation, index)` -- on balaye les deux fronts.
        const zones: unknown[] = [];
        const mZone2 = findMethodByParamClasses(k, "GetWarZone", ["FrontLineAffiliation", "Int32"]);
        if (mZone2) {
            for (let aff = 0; aff < 3; aff++) {
                // MEME BORNE que `guildWarZones` -- le `12` en dur jetait 3 des 15 types de zone.
                for (let idx = 0; idx < PLAFOND_INDEX_ZONE; idx++) {
                    let z: NativePointer;
                    try { z = invokeMethod(mZone2.info, sur, [i32(aff), i32(idx)]); } catch { break; }
                    if (!z || z.isNull()) continue;
                    const j = enJson(z);
                    if (j) zones.push({ affiliation: aff, index: idx, zone: j });
                }
            }
        }
        res.zones = zones;
        res.zonesRefus = mZone2 ? null
            : "`GetWarZone(FrontLineAffiliation, Int32)` INTROUVABLE -- chemin PERIME";

        // Une adresse de bataille (zone, part, slot) => la ZONE et le SLOT DEFENSIF reels.
        if (body?.warZoneId) {
            const id = createManagedString(body.warZoneId);
            const zp = i32(body.zonePartIndex ?? 0);
            const sl = i32(body.slotIndex ?? 0);
            const mZone1 = findMethodByParamClasses(k, "GetWarZone", ["String"]);
            const zone = mZone1 ? invokeMethod(mZone1.info, sur, [id]) : NULL;
            res.warZone = enJson(zone);
            res.warZoneSlot = enJson(appeler(k, sur, "GetWarZoneSlot", 3, [id, zp, sl]));
            res.activeBuffs = enJson(appeler(k, sur, "GetActiveBuffs", 1, [id]));
            res.occupant = enJson(appeler(k, sur, "GetOccupyingGuildMember", 2, [id, zp]));

            // LA CARTE. Mirror de `ShowGuildWarsBattlePreviewPopupCommand$$OnStartBattleButtonClicked` :
            // le `warZoneType` de la zone (champ `Nullable` a `+0x20`) alimente DEUX configs --
            // `GetWarZoneConfig` porte le BoardId (`+0x10`) et le SpawnPointsSet (`+0x18`),
            // `GetZoneConfig` porte les caps de rarete, dont `GetRarityCap(cfg, slotIndex)` tire
            // celui du slot. Rien n'est devine ici : ce sont les memes appels, dans le meme ordre.
            if (!zone.isNull()) {
                // ⚠ L'ORDINAL NE SE DEVINE PAS. `WarZoneType` est ABSENT de la table des enums
                // (Newtonsoft le serialise par NOM : "AntiAirBattery"), et lire le `Nullable` a
                // `+0x20` a rendu `1` -- valeur qui fait LEVER les deux configs. On ne suppose
                // donc rien : on BALAYE les ordinaux et on publie ce que CHACUN rend. Le mapping
                // ordinal -> board se DERIVE de la mesure, il ne se recopie pas.
                res.octetsWarZoneType = [zone.add(0x20).readS32(), zone.add(0x24).readS32()];
                const mCfg = findMethodByParamCount(k, "GetWarZoneConfig", 1);
                const balayage: unknown[] = [];
                if (mCfg) {
                    // ⚠ PAS `il2cpp_runtime_invoke` ICI, ET C'EST MESURE. Le corps de
                    // `GuildWarPhaseProgression$$GetWarZoneConfig` fait `local = param_2` puis
                    // passe `&local` a `CollectionExtensions$$GetValueOrDefault` : il attend donc
                    // l'enum PAR VALEUR, en registre. `runtime_invoke`, lui, passe un POINTEUR
                    // vers la valeur -- le natif recolle alors mon ordinal a un fragment de
                    // pointeur de tas et dereference. Signature du crash, sur les 16 ordinaux :
                    // `access violation accessing 0x219_0000000<ord>`, ou `0x219` est le prefixe
                    // du tas IL2CPP et `<ord>` exactement la valeur passee.
                    // On appelle donc l'ENTRY POINT, avec la convention IL2CPP reelle :
                    // `(this, args..., const MethodInfo*)`.
                    // ⚠ ET LA CLE DOIT ETRE BOXEE. Passer l'ordinal BRUT fait planter sur
                    // `access violation accessing 0x<ord>` -- l'adresse fautive EST la valeur,
                    // donc le natif la DEREFERENCE. C'est la signature d'un dictionnaire gshared
                    // (`__Il2CppFullySharedGenericType`) : sa cle est un OBJET, pas une valeur.
                    // Une boite IL2CPP, c'est un objet dont la valeur vit a `+0x10`.
                    const kWzt = findClassAnywhere(
                        "Idun.Source.IdunMeta.Logic.UserProgress.GuildWars", "WarZoneType");
                    res.classeWarZoneType = kWzt !== null;
                    // `propagate` : appel MANAGE, cf. `il2cpp/invoke.ts`.
                    const fn = new NativeFunction(mCfg.ptr, "pointer",
                                                  ["pointer", "pointer", "pointer"],
                                                  { exceptions: "propagate" });
                    for (let ord = 0; ord < 16; ord++) {
                        if (!kWzt) break;
                        const boite = il2cpp_object_new(kWzt);
                        if (boite.isNull()) continue;
                        gcRoot.add(boite);
                        boite.add(0x10).writeS32(ord);
                        let c: NativePointer;
                        try { c = fn(sur, boite, mCfg.info) as NativePointer; } catch (e) {
                            balayage.push({ ord, erreur: (e as Error).message.slice(0, 60) });
                            continue;
                        }
                        if (!c || c.isNull()) { balayage.push({ ord, config: null }); continue; }
                        let bid: string | null = null;
                        let sps: number | null = null;
                        try {
                            const p = c.add(0x10).readPointer();
                            bid = p.isNull() ? null : readIl2cppString(p);
                            sps = c.add(0x18).readS32();
                        } catch { /* offsets a confirmer */ }
                        balayage.push({ ord, boardId: bid, spawnPointsSet: sps, brut: enJson(c) });
                    }
                }
                res.warZoneConfigParOrdinal = balayage;
                res.warZoneConfigRefus = mCfg ? null : "`GetWarZoneConfig` INTROUVABLE";
            }
        }
        return res;
    });

    /** L'INVENTAIRE LISIBLE DES ZONES -- celui qui rend un `warZoneId` trouvable par un HUMAIN.
     *
     *  body: { filtre?: string, avecUnites?: boolean }
     *    - `filtre` : sous-chaine insensible a la casse, comparee au PSEUDO de l'occupant, au
     *      type de zone et au `zoneId`. C'est la forme utile : « donne-moi la zone de nicodsf ».
     *    - `avecUnites: true` ajoute l'apercu des ids d'unites defendantes par slot.
     *
     *  ⚠ POURQUOI CE RPC EXISTE. `guildWarBoardRead` rend l'etat COMPLET -- 637 Ko sur le plateau
     *  du 2026-08-19, et les zones n'y sont designees que par des GUID (`zoneId`,
     *  `occupiedByUserId`). Aucun humain ne peut y retrouver « la zone d'Untel », alors que
     *  `guildWarSourceForger` EXIGE justement un `warZoneId`. Le chainon manquant est
     *  `GuildWarPhaseProgression$$GetOccupyingGuildMember(warZoneId, zonePartIndex)`, qui rend le
     *  MEMBRE -- donc le pseudo. Ce RPC ne fait que boucler dessus et rendre du compact.
     *
     *  ⚠ LECTURE PURE : `GetWarZone` et `GetOccupyingGuildMember` lisent la progression deja
     *  synchronisee cote client. Aucune ecriture, aucun octet reseau, aucune tentative consommee.
     *
     *  ⚠ UN FILTRE QUI NE REND RIEN DIT COMBIEN IL A ECARTE (`total` vs `rendues`) : un zero
     *  filtre ne doit pas se lire comme « pas de zones ». */
    ctx.rpc.guildWarZones = (body?: {
        filtre?: string; avecUnites?: boolean;
    }): Promise<unknown> => queueOnMainThread(() => {
        const prog = progressionPhase();
        if (estRefus(prog)) return { ok: false, error: (prog as RefusVue).error };
        const sur = prog as NativePointer;
        const k = findClassAnywhere("Idun.Source.IdunMeta.Logic.UserProgress.GuildWars",
                                    "GuildWarPhaseProgression");
        if (!k) return { ok: false, error: "classe `GuildWarPhaseProgression` introuvable" };
        const mZone2 = findMethodByParamClasses(k, "GetWarZone", ["FrontLineAffiliation", "Int32"]);
        if (!mZone2) {
            return { ok: false,
                     error: "`GetWarZone(FrontLineAffiliation, Int32)` INTROUVABLE -- chemin PERIME" };
        }
        const i32 = (v: number) => { const p = Memory.alloc(4); p.writeS32(v); return p; };

        /** Le pseudo, cherche PAR NOM DE CHAMP dans le membre serialise. On essaie plusieurs
         *  noms parce qu'aucun n'est garanti par le build ; ce qui n'est PAS negociable, c'est
         *  qu'un echec rende `null` ET publie le brut, jamais une chaine inventee. */
        const CLES_NOM = ["playerName", "userName", "displayName", "nickname", "name"];
        const nomDeMembre = (o: unknown): string | null => {
            if (o === null || typeof o !== "object") return null;
            const d = o as Record<string, unknown>;
            for (const c of CLES_NOM) {
                const v = d[c];
                if (typeof v === "string" && v.length > 0) return v;
            }
            for (const v of Object.values(d)) {
                if (v !== null && typeof v === "object") {
                    const r = nomDeMembre(v);
                    if (r !== null) return r;
                }
            }
            return null;
        };

        const zones: Array<Record<string, unknown>> = [];
        const attendu = nbTypesDeZone(k, sur);
        for (let aff = 0; aff < 3; aff += 1) {
            for (let idx = 0; idx < PLAFOND_INDEX_ZONE; idx += 1) {
                let z: NativePointer;
                try { z = invokeMethod(mZone2.info, sur, [i32(aff), i32(idx)]); } catch { break; }
                if (!z || z.isNull()) continue;
                const j = enJson(z) as Record<string, unknown> | null;
                if (j === null || typeof j !== "object") continue;
                const zoneId = typeof j.zoneId === "string" ? j.zoneId : null;
                const parts: Array<Record<string, unknown>> = [];
                for (const [champ, pi] of [["zonePart1", 0], ["zonePart2", 1]] as const) {
                    const zp = j[champ] as Record<string, unknown> | undefined;
                    if (zp === undefined || zp === null) continue;
                    let occupant: string | null = null;
                    let occupantBrut: unknown = null;
                    let occupantRefus: string | null = null;
                    if (zoneId !== null) {
                        const o = appeler(k, sur, "GetOccupyingGuildMember", 2,
                                          [createManagedString(zoneId), i32(pi)]);
                        if (estRefus(o)) { occupantRefus = (o as RefusVue).error; }
                        else {
                            const oj = enJson(o);
                            occupant = nomDeMembre(oj);
                            if (occupant === null) occupantBrut = oj;
                        }
                    } else {
                        occupantRefus = "`zoneId` absent de la zone -- occupant NON MESURE";
                    }
                    const brutSlots = Array.isArray(zp.warZoneSlots) ? zp.warZoneSlots : [];
                    const slots = brutSlots.map((s: Record<string, unknown>, i: number) => {
                        const du = Array.isArray(s?.defendingUnits) ? s.defendingUnits : [];
                        const l: Record<string, unknown> = {
                            slot: i,
                            unites: du.length,
                            tentatives: s?.attemptNumber ?? null,
                            perdues: s?.unitsLost ?? null,
                            // `defeatedByUserId` non nul = slot DEJA BATTU. Le publier tel quel :
                            // c'est la seule facon de distinguer « intact » de « rase ».
                            battu: s?.defeatedByUserId != null,
                            mow: s?.defendingMachineOfWar != null,
                        };
                        if (body?.avecUnites === true) {
                            l.apercu = du.map((u: Record<string, unknown>) => {
                                const ui = u?.unitInfo as Record<string, unknown> | undefined;
                                return ui?.id ?? null;
                            });
                        }
                        return l;
                    });
                    parts.push({ zonePartIndex: pi, occupiedByUserId: zp.occupiedByUserId ?? null,
                                 occupant, occupantRefus, occupantBrut, slots });
                }
                zones.push({ affiliation: aff, index: idx, zoneId,
                             type: j.warZoneType ?? null, revealed: j.revealed ?? null, parts });
            }
        }

        const f = (body?.filtre ?? "").toLowerCase();
        const retenues = f === "" ? zones : zones.filter((z) => {
            const champs: string[] = [String(z.type ?? ""), String(z.zoneId ?? "")];
            for (const p of z.parts as Array<Record<string, unknown>>) {
                champs.push(String(p.occupant ?? ""), String(p.occupiedByUserId ?? ""));
            }
            return champs.some((c) => c.toLowerCase().includes(f));
        });
        // COUVERTURE : le compte trouve, confronte a celui que le JEU declare. Sans ce cran, une
        // enumeration tronquee publie un total coherent avec lui-meme et FAUX -- c'est ce qui a
        // fait conclure « Drakar69 ne defend rien » alors qu'il tenait `MedicaeStation1` (#10038).
        const parFront = new Map<number, number>();
        for (const z of zones) {
            const a = Number(z.affiliation);
            parFront.set(a, (parFront.get(a) ?? 0) + 1);
        }
        const maxParFront = parFront.size ? Math.max(...parFront.values()) : 0;
        const couverture = {
            typesDeZoneDeclares: attendu,
            zonesParFront: Object.fromEntries(parFront),
            plafondExplore: PLAFOND_INDEX_ZONE,
            // `null` = PAS mesurable (config illisible), jamais rabattu sur « complet ».
            complete: attendu === null ? null : maxParFront >= attendu,
            manque: attendu === null ? null : Math.max(0, attendu - maxParFront),
        };
        return { ok: true, total: zones.length, rendues: retenues.length,
                 filtre: body?.filtre ?? null, couverture, zones: retenues,
                 note: "`zoneId` est le `warZoneId` attendu par `guildWarSourceForger` ; "
                     + "`zonePartIndex` et le `slot` d'un slot sont ses deux autres coordonnees." };
    });

    /** Resout TOUTE la chaine et rend ce qui manque. N'INVOQUE RIEN -- a jouer avant
     *  `guildWarBuildBc`, pour lire un refus AVANT de tenter plutot qu'apres coup. */
    ctx.rpc.guildWarProbe = (): Promise<unknown> => queueOnMainThread(() => {
        const kB = findClassAnywhere(NS_VIEW, "BattleConfigBuilder");
        const m = kB ? findMethodByParamCount(kB, "GetGuildWarsConfig", 14) : null;
        const kVals = findClassAnywhere(NS_VIEW, "BattleConfigGameConfigValues");
        // Le ctor VISE, celui qui prend l'univers -- pas l'autre surcharge a 2 parametres.
        const ctorVals = kVals
            ? findMethodByParamClasses(kVals, ".ctor", [null, "ITileConfigurationSource"]) : null;
        // Et la liste des surcharges, pour que le refus soit LISIBLE quand la visee echoue.
        const ctorsVals: string[] = [];
        if (kVals) {
            for (let n = 0; n <= 3; n++) {
                const c = findCtorByParamCount(kVals, n);
                if (!c) continue;
                const cls: string[] = [];
                for (let i = 0; i < n; i++) cls.push(methodParamClassName(c.info, i) ?? "?");
                ctorsVals.push("(" + cls.join(", ") + ")");
            }
        }
        const kSet = findClassAnywhere(NS_VIEW, "BattleConfigSettings");
        const mFrom = kSet ? findMethodByParamCount(kSet, "FromFeatureToggles", 1) : null;
        const deps = lireDeps();
        const univers = getCapturedUniverse();
        const params: Array<{ index: number; classe: string | null }> = [];
        if (m) {
            for (let i = 0; i < 14; i++) {
                const k = methodParamClass(m.info, i);
                params.push({
                    index: i,
                    classe: k && !k.isNull() ? cstr(class_get_name(k) as NativePointer) : null,
                });
            }
        }
        return {
            ok: true,
            fabrique: {
                classe: kB ? cstr(class_get_name(kB) as NativePointer) : null,
                getGuildWarsConfigResolue: m !== null,
                params,
            },
            gameConfigValues: kVals !== null,
            gameConfigValuesCtorVise: ctorVals !== null,
            gameConfigValuesCtors: ctorsVals,
            battleConfigSettings: mFrom !== null,
            dependances: estRefus(deps) ? null : {
                unitProgression: (deps as Deps).prog.toString(),
                gameConfigDto: (deps as Deps).gameConfig.toString(),
                logger: (deps as Deps).logger.toString(),
                featureUnlocker: (deps as Deps).featureUnlocker.toString(),
            },
            dependancesRefus: estRefus(deps) ? (deps as RefusVue).error : null,
            univers: univers ? univers.toString() : null,
            universRefus: univers ? null
                : "`IdunUniverse` NON CAPTURE -- l'amorce ne l'a pas pose (rejouer "
                  + "`POST /api/admin/amorce`)",
            serialiseurPret: isSerializerReady(),
            deserialiseurPret: isDeserializerReady(),
            // Ce que `guildWarBuildBc` exigera, pour que l'appelant sache CE QUI manque.
            pret: kB !== null && m !== null && ctorVals !== null && mFrom !== null
                && !estRefus(deps) && univers !== null && isSerializerReady(),
        };
    });

    /**
     * FORGE une `GuildWarsGameModeSource` -- ET C'EST LA VOIE QUI NE PASSE PLUS PAR NOS INGREDIENTS.
     *
     * ⚠ POURQUOI FORGER PLUTOT QU'APPELER LA FABRIQUE. `guildWarBuildBc` appelle
     * `GetGuildWarsConfig` en lui passant NOS 14 arguments : le catalogue, les environment
     * abilities, l'ammo, la carte. Chacun est une occasion de se tromper, et plusieurs l'etaient.
     * Une source FORGEE, elle, va chercher les 14 toute seule dans `LoadBattleInternal` -- c'est
     * exactement ce que fait `guild-boss-config.ts`, et c'est pourquoi cette sandbox-la marche.
     *
     * ⚠ LE CTOR DE LA SOURCE EXIGE LE RECORD ET LE DEREFERENCE. Il lit `battleData+0x28`
     * (Enemies), `+0x30` (MoW adverse, dont le `+0x10` doit etre non nul), `+0x10` (WarZoneId) et
     * `+0x1c` (SlotIndex), et il LEVE si le pointeur est nul. On construit donc d'abord le record
     * par SON ctor a 12 arguments.
     *
     * ⚠ LES ENNEMIS NE SONT PAS RECONSTRUITS -- ce sont les OBJETS VIVANTS de la zone, ceux-la
     * memes que le jeu passerait. On les atteint par `GetWarZone(String)` puis par champs NOMMES.
     *
     * ⚠ TROIS CHAMPS RESTENT NULS, ET C'EST MESURE, PAS NEGLIGE. `Buffs` (+0x50), `EnemyPlayer`
     * (+0x58) et, si l'appelant ne le donne pas, `RarityCap` (+0x44) ne sont lus NI par le ctor de
     * la source NI par `LoadBattleInternal` : le premier sert au HUD, le second aux metadonnees de
     * replay, le troisieme au seul
     * `GetGameModeSpecificDeploymentHudOptionsInternal`. Les remplir a l'aveugle serait inventer.
     *
     * ⚠ AUCUN CONTACT SERVEUR. `StartMatch` n'est PAS appele -- et c'est lui, et lui seul, qui
     * conduit a `SendLoadBattleGameEventInternal`. Le ctor n'envoie rien.
     */
    ctx.rpc.guildWarSourceForger = (body?: {
        warZoneId?: string; zonePartIndex?: number; slotIndex?: number;
        boardId?: string; spawnPointsSet?: number; rarityCap?: number; confirmer?: boolean;
        avecEnvironnement?: boolean;
    }): Promise<unknown> => queueOnMainThread(() => {
        if (!body?.warZoneId) return refus("`warZoneId` manquant");
        if (!body?.boardId) return refus("`boardId` manquant -- le derive de `guildWarZoneConfigs`");
        const part = body.zonePartIndex ?? 0;
        const slotIdx = body.slotIndex ?? 0;

        const exec = executeurVivant();
        if (estRefus(exec)) return exec;
        const kExec = findClassAnywhere("idun.shared.commands", "ViewCommandExecutor");
        if (!kExec) return refus("classe `ViewCommandExecutor` introuvable");
        const prog = progressionPhase();
        if (estRefus(prog)) return prog;
        const kProg = findClassAnywhere("Idun.Source.IdunMeta.Logic.UserProgress.GuildWars",
                                        "GuildWarPhaseProgression");
        if (!kProg) return refus("classe `GuildWarPhaseProgression` introuvable");

        // --- les ennemis VIVANTS, pris dans la zone -----------------------------------------
        const mZone = findMethodByParamClasses(kProg, "GetWarZone", ["String"]);
        if (!mZone) return refus("`GetWarZone(String)` INTROUVABLE -- chemin PERIME");
        let zone: NativePointer;
        try { zone = invokeMethod(mZone.info, prog as NativePointer,
                                  [createManagedString(body.warZoneId)]); }
        catch (e) { return refus("`GetWarZone` a LEVE : " + (e as Error).message); }
        if (zone.isNull()) return refus(`zone \`${body.warZoneId}\` INCONNUE de la progression`);
        gcRoot.add(zone);

        const nomPart = part === 0 ? "zonePart1" : "zonePart2";
        const pPart = champ(zone, nomPart);
        if (estRefus(pPart)) return pPart;
        if ((pPart as NativePointer).isNull()) return refus(`\`${nomPart}\` est NUL sur la zone`);
        const pSlots = champ(pPart as NativePointer, "warZoneSlots");
        if (estRefus(pSlots)) return pSlots;
        const pSlot = elementDeListe(pSlots as NativePointer, slotIdx);
        if (estRefus(pSlot)) return refus(`slot ${slotIdx} : ` + (pSlot as RefusVue).error);
        // ⚠ `Enemies` N'EST PAS LA LISTE BRUTE DU SLOT, et l'y mettre fait LEVER le ctor de la
        // source (« system error », mesure du 2026-08-19). La popup passe
        // `WarZoneSlotDtoExtensions$$GetLineUpModels(slot, unitProgression, out totalPower)`, qui
        // rend un `List<UnitModelWithHealth>` : pour chaque `defendingUnits[i]`, elle construit un
        // `CalculatedStatsUnitModel(unitDto, xp, unitProgression, initStaticStats: true, isNpc)`
        // puis l'enveloppe avec maxHp/remainingHp/power lus a `+0x18`/`+0x1c`/`+0x20`. C'est cette
        // liste-la que le ctor de la source passe a `ListExtensions$$FilterMap`.
        //
        // ⚠ ET ON LA CALCULE SUR LE SLOT DE `GetWarZone`, PAS SUR CELUI DE `GetWarZoneSlot`.
        // `GetLineUpModels` lit les PV dans les elements de `slot+0x18` ; or `GetWarZoneSlot` rend
        // un slot dont `remainingHp` vaut 0 la ou `GetWarZone` le peuple (mesure anterieure : 0
        // contre 3204, meme unite). Prendre la voie de la popup a la lettre monterait des ennemis
        // MORTS -- on garde donc SA fonction, mais sur NOTRE slot.
        const kExt = findClassAnywhere("Idun.Source.IdunMeta.Logic.UserProgress.GuildWars",
                                       "WarZoneSlotDtoExtensions");
        if (!kExt) return refus("classe `WarZoneSlotDtoExtensions` introuvable");
        const mLineup = findMethodByParamCount(kExt, "GetLineUpModels", 3);
        if (!mLineup) {
            return refus("`WarZoneSlotDtoExtensions$$GetLineUpModels(3)` INTROUVABLE -- signature "
                + "CHANGEE sur ce build");
        }
        const pUnitProg = champ(exec as NativePointer, "_unitProgression");
        if (estRefus(pUnitProg)) return pUnitProg;
        const outPower = Memory.alloc(4);
        outPower.writeS32(0);
        let enemies: NativePointer;
        try {
            enemies = invokeMethod(mLineup.info, NULL,
                                   [pSlot as NativePointer, pUnitProg as NativePointer, outPower]);
        } catch (e) { return refus("`GetLineUpModels` a LEVE : " + (e as Error).message); }
        if (enemies.isNull()) return refus("`GetLineUpModels` a rendu NUL");
        gcRoot.add(enemies);
        const nbEnnemis = enemies.add(0x18).readS32();
        const puissanceLineup = outPower.readS32();

        // LA MoW ADVERSE -- LE FRERE JUMEAU DE L'APPEL CI-DESSUS (2026-08-21).
        //
        // (!)ELLE RESTAIT NULLE FAUTE DE SAVOIR OU LA PRENDRE, et le symptome se voyait a l'ecran :
        // BC juste, defense complete, `PredefinedMachines: [{Id: 12, MachineOfWar: {UnitId: null}}]`
        // -- l'emplacement existe, la machine non, alors que `guildWarZones` annonce `mow: true`.
        //
        // Le decompile de la popup tranche : elle appelle DEUX extensions, sur le MEME slot et avec
        // le MEME `unitProgression`, et n'en garde que le premier element du tuple --
        //   `ShowGuildWarsBattlePreviewPopupCommand$$GetUnits`
        //       -> `WarZoneSlotDtoExtensions$$GetLineUpModels(slot, unitProgression, out puissance)`
        //   `ShowGuildWarsBattlePreviewPopupCommand$$GetMachineOfWarUnits`
        //       -> `WarZoneSlotDtoExtensions$$GetMachineOfWarLineUpModel(slot, unitProgression,
        //                                                                out rarete)`
        // puis `GuildWarBattleData$$.ctor(..., Enemies, MachineOfWarEnemy, ...)`. La machine n'est
        // donc PAS dans la liste des ennemis : c'est un appel SEPARE, qu'on ne faisait pas.
        //
        // (!)MEME SLOT QUE LES ENNEMIS, ET POUR LA MEME RAISON. On reste sur `pSlot` (celui de
        // `GetWarZone`), pas sur `GetWarZoneSlot` dont les PV restants valent 0 -- cf. la mesure
        // citee plus haut.
        //
        // (!)LE NUL RESTE TOLERE, LE MI-CUIT NON. Le ctor de la source saute son bloc si le
        // pointeur est nul, mais il LEVE si le pointeur est non nul et que son `+0x10` l'est
        // (`if (*(battleData+0x30 + 0x10) == 0) goto <throw>`). Un slot sans MoW doit donc partir
        // en NUL FRANC, jamais en modele vide -- d'ou `mowUtilisable`, qui juge le `+0x10`.
        const mMow = findMethodByParamCount(kExt, "GetMachineOfWarLineUpModel", 3);
        if (!mMow) {
            return refus("`WarZoneSlotDtoExtensions$$GetMachineOfWarLineUpModel(3)` INTROUVABLE "
                + "-- signature CHANGEE sur ce build");
        }
        const outRarete = Memory.alloc(4);
        outRarete.writeS32(0);
        let mowPtr: NativePointer = NULL;
        try {
            mowPtr = invokeMethod(mMow.info, NULL,
                                  [pSlot as NativePointer, pUnitProg as NativePointer, outRarete]);
        } catch (e) {
            return refus("`GetMachineOfWarLineUpModel` a LEVE : " + (e as Error).message);
        }
        let mowUtilisable = false;
        if (!mowPtr.isNull()) {
            gcRoot.add(mowPtr);
            // Le champ que le ctor de la source DEREFERENCE. On le lit AVANT de passer le
            // pointeur, pour ne jamais lui donner de quoi lever.
            try { mowUtilisable = !mowPtr.add(0x10).readPointer().isNull(); } catch { /* faux */ }
        }
        const mowRarete = outRarete.readS32();

        // --- l'identifiant de guerre ----------------------------------------------------------
        const gwId = appeler(kProg, prog as NativePointer,
                             "GetGuildWarIdEvenIfItHasntStartedYet", 0, []);
        if (estRefus(gwId)) return gwId;

        // --- un `EnvironmentAbilities` REELLEMENT INITIALISE ----------------------------------
        // ⚠ Un objet nu ne suffit PAS : `ApplyEnvironmentAbilitiesFromProgression` le passe en
        // ACCUMULATEUR a `BattleEnvironmentAbilityExtensions$$Apply`, qui ECRIT dedans. Ses trois
        // membres (`Abilities`, `EnhancementAbilities`, `AbilitiesConfigurations`) doivent donc
        // exister. Le ctor natif ne les cree pas -- c'est l'appelant qui le fait, verifie au
        // decompile de la popup. On les fait creer par Newtonsoft, qui connait leurs generiques.
        const kEnv = findClassAnywhere(NS_CFG, "EnvironmentAbilities");
        if (!kEnv) return refus("classe `IdunBattle.Configuration.EnvironmentAbilities` introuvable");
        let env: NativePointer;
        try {
            env = deserializeFromJson(
                '{"Abilities":[],"EnhancementAbilities":[],"AbilitiesConfigurations":{}}', kEnv);
        } catch (e) { return refus("`EnvironmentAbilities` : " + (e as Error).message); }
        if (env.isNull()) return refus("`EnvironmentAbilities` deserialise en NUL");
        gcRoot.add(env);

        // --- ET ON LE REMPLIT : LES BUFFS DE ZONE ---------------------------------------------
        //
        // ⚠ CREER L'ACCUMULATEUR NE SUFFIT PAS, et le laisser vide se voyait a l'ecran :
        // AUCUNE ability d'environnement ne jouait sur un montage sandbox de guerre de guilde.
        // Mesure du 2026-08-21 sur le replay d'un montage DogAlpha : le CATALOGUE etait bien la
        // (`BC.Abilities.EnvironmentAbilities` = 166 definitions) mais la LISTE ACTIVE valait
        // `0` -- et le buff de la zone (`EnvArtillerySupport_Regional`) avait **0 occurrence**
        // dans tout le fichier. Effet concret : les trois salves d'artillerie du debut de partie
        // n'avaient pas lieu.
        //
        // Ce qui les arme, c'est cette boucle-ci, mirror de
        // `ShowGuildWarsBattlePreviewPopupCommand$$OnStartBattleButtonClicked` -- la popup qu'on
        // court-circuite. Elle porte a la fois l'environnement ET le cap de rarete, parce que le
        // cap est la CLE d'indexation de la config de chaque buff.
        // ⛔ OPT-IN, ET ETEINT PAR DEFAUT -- `avecEnvironnement: true` pour l'allumer.
        //
        // ⚠ CE CHEMIN A FAIT CRASHER LE JEU DEUX FOIS le 2026-08-21 (dumps
        // `Tacticus.exe.30620.dmp` 14:19 et le suivant). La seconde fois, SEULE la partie
        // LECTURE avait tourne (`guildWarEnvProbe`) : la faute est donc dans `capDeRarete` ou
        // `GetActiveBuffs`, PAS dans l'armement -- c'est ce que l'isolement des etages a permis
        // de dire. La cause exacte n'est pas etablie.
        //
        // Tant qu'elle ne l'est pas, un montage guild war ne doit pas l'emprunter : il monte
        // sans environnement (donc sans les salves d'artillerie), ce qui est un ECART CONNU
        // et ANNONCE -- pas un crash. Residu ouvert.
        // ⚠ LE CAP DE RARETE N'ENTRE PAS DANS CE CHEMIN, ET C'EST UNE MESURE QUI L'A RETIRE.
        //
        // La popup indexe la config de chaque buff par le cap (`buffAbilityConfig[rarityCap]`), ce
        // qui m'a fait croire que cap et environnement etaient indissociables -- et m'a fait
        // appeler `GetWarZoneConfig`/`GetZoneConfig`/`GetRarityCap`, dont l'un a CRASHE le jeu
        // deux fois (dumps `Tacticus.exe.30620.dmp` et `.40696.dmp`, 2026-08-21).
        //
        // Or `GetActiveBuffs` rend la config POUR LES SIX RARETES, et sur cette zone elles sont
        // IDENTIQUES -- mesure : `Common`..`Mythic` portent le meme `nrOfProjectiles`
        // (`["3","6","9",...]`) et le meme `hpPct`. Le cap ne discrimine donc RIEN ici, et
        // l'indexer n'apportait que le risque. On ne lit plus que `GetActiveBuffs`, appel deja
        // eprouve sans crash (et deja utilise par `guildWarProbe`).
        //
        // ⚠ CE QUI RESTE VRAI : le cap SERT AILLEURS -- c'est l'argument 9 du record, qui borne
        // la rarete deployable a l'ecran. Il vaut toujours `?? 0` faute d'avoir pu appeler
        // `GetRarityCap` sans tuer le jeu. Residu #10041-r3.
        const detailEnv: Array<Record<string, unknown>> = [];
        const rarityCap = body.rarityCap ?? 0;
        if (body.avecEnvironnement !== false) {
            const rBuffs = armerBuffsDeZone(kProg, prog as NativePointer, body.warZoneId,
                                            rarityCap, env, detailEnv);
            if (estRefus(rBuffs)) return rBuffs;
        }

        // --- les 17 dependances de la source, resolues PAR NOM --------------------------------
        const NOMS_EXEC = ["_unitProgression", "_itemProgression", "_modifierProgression",
                           "_gameConfigData", "_logger", "_featureUnlocker", "_onlineFeatureDecider",
                           "_coroutineStarter", "_resourceProgression",
                           "_battleReconciliationProgression", "_questEventHandler",
                           "_menuSystems"] as const;
        const dep: Record<string, NativePointer> = {};
        const absents: string[] = [];
        const nuls: string[] = [];
        for (const n of NOMS_EXEC) {
            const off = getFieldOffset(kExec, n);
            if (off < 0) { absents.push(n); continue; }
            const p = (exec as NativePointer).add(off).readPointer();
            if (p.isNull()) nuls.push(n);
            dep[n] = p;
        }
        if (absents.length > 0) {
            return refus("champs ABSENTS de `ViewCommandExecutor` sur ce build : "
                + absents.join(", ") + " -- chemin PERIME");
        }
        // Les trois HUD vivent sur `MenuSystems`. On les prend PAR NOM et on PUBLIE leur offset :
        // le decompile de `StartGuildWarsMatch` lit `+0x188`, `+0x3c8` et `+0xf8`, donc un ecart
        // signale un renommage ou un renumerotage AU LIEU de le subir en silence.
        const HUDS: Array<{ arg: string; nom: string; attendu: number }> = [
            { arg: "deploymentHud", nom: "unitDeploymentHud",    attendu: 0x188 },
            { arg: "hud",           nom: "GuildWarInBattleHud",  attendu: 0x3c8 },
            { arg: "gameHud",       nom: "idunGameHud",          attendu: 0xf8 },
        ];
        const menus = dep["_menuSystems"];
        let kMenus: NativePointer = NULL;
        try { kMenus = menus.readPointer(); } catch { /* publie plus bas */ }
        const hudRes: Record<string, { offset: number; attendu: number; concorde: boolean }> = {};
        const hudPtr: Record<string, NativePointer> = {};
        for (const h of HUDS) {
            const off = kMenus.isNull() ? -1 : getFieldOffset(kMenus, h.nom);
            hudRes[h.arg] = { offset: off, attendu: h.attendu, concorde: off === h.attendu };
            hudPtr[h.arg] = off < 0 ? NULL : menus.add(off).readPointer();
        }
        const hudManquants = HUDS.filter((h) => hudRes[h.arg].offset < 0).map((h) => h.nom);

        if (body.confirmer !== true) {
            return { ok: true, lecture: true,
                     zone: zone.toString(), zonePart: nomPart, slotIndex: slotIdx,
                     enemies: enemies.toString(), nbEnnemis, puissanceLineup,
                     machineOfWarEnemy: mowPtr.toString(), mowUtilisable, mowRarete,
                     guildWarId: (gwId as NativePointer).toString(),
                     champsNuls: nuls, hud: hudRes, hudManquants,
                     note: "`confirmer: true` exige : ce RPC ALLOUE un `GuildWarBattleData` puis "
                         + "une `GuildWarsGameModeSource`. `StartMatch` n'est PAS appele, donc "
                         + "aucune tentative n'est consommee et rien ne part au serveur." };
        }
        if (hudManquants.length > 0) {
            return refus("HUD INTROUVABLES sur `MenuSystems` : " + hudManquants.join(", ")
                + " -- les noms ont change sur ce build, on ne devine pas un remplacant");
        }
        if (nuls.length > 0) {
            return refus("dependances NULLES sur l'executeur : " + nuls.join(", ")
                + " -- la source serait construite incomplete et le natif leverait plus tard "
                + "sans rien nommer");
        }

        // --- le RECORD, par son ctor a 12 arguments -------------------------------------------
        // ⚠ SA CLASSE NE SE CHERCHE PAS PAR NOM. `GuildWarBattleData` est IMBRIQUEE dans
        // `GuildWarsGameModeSource` : `findClassAnywhere` passe par `image_get_class`, qui
        // n'indexe pas les classes imbriquees -- mesure du 2026-08-19, refus « introuvable » sur
        // les deux formes de namespace essayees. On la prend donc la ou elle est DECLAREE : c'est
        // le PARAMETRE 0 du ctor de la source. Zero nom devine, et un renommage inter-build se
        // resout tout seul.
        const kSrcPourRec = findClassAnywhere("IdunBattle.ViewLogic.BattleSource",
                                              "GuildWarsGameModeSource");
        if (!kSrcPourRec) return refus("classe `GuildWarsGameModeSource` introuvable");
        const ctorSrcPourRec = findCtorByParamCount(kSrcPourRec, 17);
        if (!ctorSrcPourRec) {
            return refus("`GuildWarsGameModeSource..ctor(17)` INTROUVABLE -- signature CHANGEE");
        }
        const kRec = methodParamClass(ctorSrcPourRec.info, 0);
        if (!kRec || kRec.isNull()) {
            return refus("classe du parametre 0 de `GuildWarsGameModeSource..ctor` illisible "
                + "-- c'est elle qui porte `GuildWarBattleData`");
        }
        const ctorRec = findCtorByParamCount(kRec, 12);
        if (!ctorRec) {
            return refus("`GuildWarBattleData..ctor(12)` INTROUVABLE -- la signature a CHANGE ; "
                + "on ne devine pas une arite de remplacement");
        }
        const i32 = (v: number) => { const p = Memory.alloc(4); p.writeS32(v); return p; };
        const rec = il2cpp_object_new(kRec);
        if (rec.isNull()) return refus("allocation du `GuildWarBattleData` a rendu NUL");
        gcRoot.add(rec);
        try {
            invokeMethod(ctorRec.info, rec, [
                createManagedString(body.warZoneId),      // WarZoneId
                i32(part),                                // ZonePartIndex
                i32(slotIdx),                             // SlotIndex
                gwId as NativePointer,                    // GuildWarId
                enemies,                                  // Enemies -- modeles, voie de la popup
                mowUtilisable ? mowPtr : NULL,            // MachineOfWarEnemy -- modele, voie de la popup
                createManagedString(body.boardId),        // BoardId
                i32(body.spawnPointsSet ?? 0),            // SpawnPointsSet
                // ⚠ LE CAP EST DERIVE DU NATIF, PLUS UN `?? 0`. Il valait 0 -- donc << Common
                // seulement >> -- sur tous nos montages, alors que `GetRarityCap` rend celui du
                // slot. Et il ne sert pas qu'ici : c'est la CLE d'indexation de la config de
                // chaque buff de zone (cf. `armerBuffsDeZone`). `body.rarityCap` reste une
                // echappatoire EXPLICITE, jamais le defaut.
                i32(rarityCap),                           // RarityCap
                env,                                      // EnvironmentAbilities
                NULL,                                     // Buffs        -- HUD seul
                NULL,                                     // EnemyPlayer  -- replay seul
            ]);
        } catch (e) { return refus("`GuildWarBattleData..ctor` a LEVE : " + (e as Error).message); }

        // --- LA SOURCE, par son ctor a 17 arguments -------------------------------------------
        const kSrc = kSrcPourRec;
        const ctorSrc = ctorSrcPourRec;
        const src = il2cpp_object_new(kSrc);
        if (src.isNull()) return refus("allocation de la source a rendu NUL");
        gcRoot.add(src);
        try {
            invokeMethod(ctorSrc.info, src, [
                rec,                                      // guildWarsBattleData
                dep["_unitProgression"],                  // unitProgression
                dep["_itemProgression"],                  // itemProgression
                prog as NativePointer,                    // guildWarPhaseProgression
                dep["_modifierProgression"],              // modifierProgression
                exec as NativePointer,                    // viewCommandExecutor
                dep["_gameConfigData"],                   // gameConfig
                dep["_logger"],                           // logger
                dep["_featureUnlocker"],                  // featureUnlocker
                dep["_onlineFeatureDecider"],             // onlineFeatureDecider
                hudPtr["deploymentHud"],                  // deploymentHud
                dep["_coroutineStarter"],                 // coroutineStarter
                dep["_resourceProgression"],              // resourceProgression
                dep["_battleReconciliationProgression"],  // battleReconciliationProgression
                hudPtr["hud"],                            // hud
                hudPtr["gameHud"],                        // gameHud
                dep["_questEventHandler"],                // questEventHandler
            ]);
        } catch (e) {
            return refus("`GuildWarsGameModeSource..ctor` a LEVE : " + (e as Error).message);
        }
        sourceForgeeGw = src;
        recordForgeGw = rec;
        recordCible = { warZoneId: body.warZoneId, zonePartIndex: part, slotIndex: slotIdx };
        return {
            ok: true, action: "FORGEE", record: rec.toString(), instance: src.toString(),
            // L'ENVIRONNEMENT, buff par buff -- `arme: true` = une ability posee avec son niveau.
            // Un `ecarte` non nul n'est PAS un detail : c'est un ecart mesure avec le natif.
            rarityCap,
            environnement: detailEnv,
            environnementArmees: detailEnv.filter((d) => d.arme === true).length,
            classe: (() => { try { return cstr(class_get_name(src.readPointer()) as NativePointer); }
                             catch { return null; } })(),
            hud: hudRes, mowUtilisable,
            // Ce que le ctor a lui-meme rempli : le lineup mappe et le roster ADRESSE.
            opponentLineup: src.add(0xe0).readPointer().toString(),
            availableMainPlayerUnits: src.add(0xf0).readPointer().toString(),
            note: "`StartMatch` n'a PAS ete appele -- aucune bataille demarree, aucune tentative "
                + "consommee, rien envoye au serveur.",
        };
    });

    /**
     * LA BC DU JEU, PRODUITE PAR LA SOURCE ELLE-MEME.
     *
     * ⚠ AUCUNE TENTATIVE CONSOMMEE, et c'est le decompile qui l'etablit : `LoadBattleInternal`
     * construit la BC et la rend ; `SendLoadBattleGameEventInternal` est un override virtuel
     * SEPARE, appele par le squelette `AGameModeSource` -- jamais par celui-ci.
     *
     * ⚠ On INVOQUE `LoadBattleInternal`, donc on ne l'ANCRE nulle part : ancrer ce qu'on invoque
     * gele le jeu.
     */
    /** ⛔ ENGAGER LA VRAIE BATAILLE DE GUERRE DE GUILDE -- LE SEUL GESTE IRREVERSIBLE DU MODULE.
     *
     *  `idun.shared.commands.ViewCommandExecutor$$StartGuildWarsMatch(battleData)` alloue une
     *  `GuildWarsGameModeSource` et appelle `StartMatch`. Le squelette `AGameModeSource` appelle
     *  alors `GuildWarsGameModeSource$$SendLoadBattleGameEventInternal` PAR SLOT DE VTABLE, qui
     *  genere un battleId (`TempBattleData$$GenerateNewBattleId`) et le POUSSE au serveur.
     *
     *  ⚠ LA TENTATIVE EST DONC PRISE AU CHARGEMENT, PAS AU START. C'est l'inverse de la campagne,
     *  ou seul le START engage l'energie -- et ca supprime la fenetre << monter, verifier, puis
     *  decider >>. Tout ce qui peut etre verifie doit l'etre AVANT cet appel, sur la source
     *  FORGEE, qui elle ne coute rien. Une fois ici, c'est parti.
     *
     *  ⚠ ET CA TOUCHE LA GUILDE, pas seulement le compte : les tentatives d'un slot sont
     *  partagees. Un appel par inadvertance en prend une a tout le monde.
     *
     *  body: { confirmer: true, warZoneId, zonePartIndex, slotIndex }
     *  Les trois derniers ne sont pas decoratifs : ils sont CONFRONTES au record retenu. Engager
     *  sur une cible qu'on croit connaitre est exactement la faute qu'on ne peut pas rattraper. */
    ctx.rpc.guildWarEngagerReel = (body?: {
        confirmer?: boolean; warZoneId?: string; zonePartIndex?: number; slotIndex?: number;
    }): Promise<unknown> => queueOnMainThread(() => {
        if (recordForgeGw === null || recordForgeGw.isNull() || recordCible === null) {
            return { ok: false, error: "aucun `GuildWarBattleData` forge -- appeler "
                + "`guildWarSourceForger {confirmer:true}` d'abord. On n'engage QUE ce qu'on a "
                + "deja construit et diffe." };
        }
        // La cible ANNONCEE doit etre la cible FORGEE. Trois champs, trois comparaisons.
        const c = recordCible;
        const ecarts: string[] = [];
        if (body?.warZoneId !== c.warZoneId) {
            ecarts.push(`warZoneId annonce=${body?.warZoneId} forge=${c.warZoneId}`);
        }
        if ((body?.zonePartIndex ?? -1) !== c.zonePartIndex) {
            ecarts.push(`zonePartIndex annonce=${body?.zonePartIndex} forge=${c.zonePartIndex}`);
        }
        if ((body?.slotIndex ?? -1) !== c.slotIndex) {
            ecarts.push(`slotIndex annonce=${body?.slotIndex} forge=${c.slotIndex}`);
        }
        if (ecarts.length > 0) {
            return { ok: false, cible: c, error: "REFUS : la cible ANNONCEE n'est pas la cible "
                + "FORGEE -- " + ecarts.join(" ; ") + ". On n'engage pas une tentative de guilde "
                + "sur un malentendu." };
        }
        if (body?.confirmer !== true) {
            return { ok: false, lecture: true, cible: c, record: recordForgeGw.toString(),
                     error: "REFUS : `confirmer: true` exige. Cet appel PREND UNE TENTATIVE DE "
                         + "GUILDE, au chargement, et l'envoie au serveur. Il n'est pas annulable." };
        }
        // Une bataille deja montee ? `StartMatch` l'ECRASERAIT -- et ici l'ecraser coute une
        // tentative pour rien. Le predicat est la comptabilite du jeu (cf. #10041).
        const enCours = enBataille();
        if (enCours !== false) {
            return { ok: false, cible: c, error: enCours === true
                ? "REFUS : une bataille est ACTIVE. Sortir d'abord."
                : "REFUS : etat de bataille NON MESURE (`get_IsBattleActive` introuvable) -- on "
                  + "n'engage pas une tentative a l'aveugle." };
        }
        const exec = executeurVivant();
        if (estRefus(exec)) return exec;
        const kExec = findClassAnywhere("idun.shared.commands", "ViewCommandExecutor");
        if (!kExec) return refus("classe `ViewCommandExecutor` introuvable");
        const m = findMethodByParamCount(kExec, "StartGuildWarsMatch", 1);
        if (!m) {
            return refus("`ViewCommandExecutor$$StartGuildWarsMatch(1)` INTROUVABLE -- signature "
                + "CHANGEE sur ce build. On n'invente pas un point d'entree pour engager.");
        }
        try {
            invokeMethod(m.info, exec as NativePointer, [recordForgeGw]);
        } catch (e) {
            return { ok: false, cible: c, engage: "INCERTAIN",
                     error: "`StartGuildWarsMatch` a LEVE : " + (e as Error).message
                         + " -- (!)L'EXCEPTION NE PROUVE PAS QUE RIEN N'EST PARTI : le battleId "
                         + "peut avoir ete pousse avant. Relire `attemptsLeft` avant de retenter." };
        }
        return {
            ok: true, cible: c, methode: "ViewCommandExecutor$$StartGuildWarsMatch",
            note: "l'appel est PASSE -- ca ne dit rien du montage, et ca ne dit pas non plus que "
                + "la tentative a ete comptee. Verifier les DEUX : `sandboxProbe` / "
                + "`retreatStatus.batailleActive` pour la scene, et `guildWarBoardRead."
                + "attemptsLeft` pour la tentative.",
        };
    });

    /** UN SEUL APPEL NATIF PAR ALLER-RETOUR RPC -- la sonde qui SURVIT a un crash.
     *
     *  ⚠ POURQUOI CE GRAIN-LA, ET PAS CELUI DE `guildWarEnvProbe`. Un crash tue la session
     *  Frida : on ne recupere RIEN, ni valeur de retour, ni champ `etage`, ni log. Grouper
     *  quatre appels natifs dans UN rpc, c'est donc n'apprendre que << c'etait dans les
     *  quatre >>. Mesure du 2026-08-21 : deux crashs du jeu, et apres le second je ne pouvais
     *  toujours pas nommer l'appel fautif.
     *  Ici chaque invocation ne fait QU'UN appel et rend la main : la reponse precedente est
     *  DEJA partie sur le fil quand la suivante part, donc la transcription elle-meme dit
     *  jusqu'ou on est alle. C'est le seul regime ou un crash INFORME au lieu d'effacer.
     *
     *  body: { etape: 1..4, ord?, warZoneId?, slotIndex? }
     *    1 = `GetActiveBuffs(warZoneId)`     -- deja appele sans crash par `guildWarProbe`
     *    2 = `GetWarZoneConfig(ord)`         -- UN ordinal, pas un balayage
     *    3 = `GetZoneConfig(ord)`            -- UN ordinal ; retient le dto pour l'etape 4
     *    4 = `GetRarityCap(<dto retenu>, slotIndex)`
     */
    ctx.rpc.guildWarEnvEtape = (body?: {
        etape?: number; ord?: number; warZoneId?: string; slotIndex?: number;
    }): Promise<unknown> => queueOnMainThread(() => {
        const prog = progressionPhase();
        if (estRefus(prog)) return { ok: false, error: (prog as RefusVue).error };
        const sur = prog as NativePointer;
        const kProg = findClassAnywhere("Idun.Source.IdunMeta.Logic.UserProgress.GuildWars",
                                        "GuildWarPhaseProgression");
        if (!kProg) return { ok: false, error: "classe `GuildWarPhaseProgression` introuvable" };
        const etape = body?.etape ?? 0;

        if (etape === 1) {
            if (!body?.warZoneId) return { ok: false, error: "`warZoneId` requis" };
            const m = findMethodByParamCount(kProg, "GetActiveBuffs", 1);
            if (!m) return { ok: false, error: "`GetActiveBuffs(1)` INTROUVABLE" };
            let l: NativePointer;
            try { l = invokeMethod(m.info, sur, [createManagedString(body.warZoneId)]); }
            catch (e) { return { ok: false, etape, error: (e as Error).message }; }
            if (l.isNull()) return { ok: true, etape, buffs: null, n: null };
            gcRoot.add(l);
            return { ok: true, etape, n: l.add(0x18).readS32(), buffs: enJson(l) };
        }

        if (etape === 2 || etape === 3) {
            const nom = etape === 2 ? "GetWarZoneConfig" : "GetZoneConfig";
            const ord = body?.ord ?? 0;
            const kWzt = findClassAnywhere("Idun.Source.IdunMeta.Logic.UserProgress.GuildWars",
                                           "WarZoneType");
            if (!kWzt) return { ok: false, error: "classe `WarZoneType` introuvable" };
            const m = findMethodByParamCount(kProg, nom, 1);
            if (!m) return { ok: false, error: `\`${nom}(1)\` INTROUVABLE` };
            const c = appelParTypeDeZone(m, sur, kWzt, ord);
            if (c === null) return { ok: false, etape, ord, error: `\`${nom}(${ord})\` a LEVE` };
            if (c.isNull()) return { ok: true, etape, ord, config: null };
            gcRoot.add(c);
            if (etape === 3) { dtoZoneRetenu = c; return { ok: true, etape, ord, dto: c.toString() }; }
            let bid: string | null = null;
            try {
                const p = c.add(0x10).readPointer();
                bid = p.isNull() ? null : readIl2cppString(p);
            } catch { /* publie tel quel */ }
            return { ok: true, etape, ord, boardId: bid, spawnPointsSet: c.add(0x18).readS32() };
        }

        if (etape === 4) {
            if (dtoZoneRetenu === null) {
                return { ok: false, error: "aucun dto retenu -- jouer l'etape 3 d'abord" };
            }
            const kExt2 = findClassAnywhere("Idun.Source.IdunMeta.Logic.UserProgress.GuildWars",
                                            "BattlefieldZoneTierConfigDtoExtensions");
            if (!kExt2) return { ok: false, error: "classe `...DtoExtensions` introuvable" };
            const m = findMethodByParamCount(kExt2, "GetRarityCap", 2);
            if (!m) return { ok: false, error: "`GetRarityCap(2)` INTROUVABLE" };
            const pSlot = Memory.alloc(4); pSlot.writeS32(body?.slotIndex ?? 0);
            try {
                const r = invokeMethod(m.info, null, [dtoZoneRetenu, pSlot]);
                // Retour BOXE : la valeur est a `+0x10`.
                return { ok: true, etape, rarityCap: r.isNull() ? null : r.add(0x10).readS32() };
            } catch (e) { return { ok: false, etape, error: (e as Error).message }; }
        }
        return { ok: false, error: "`etape` attendue dans 1..4" };
    });

    /** LES DEUX ETAGES DE L'ENVIRONNEMENT, EN LECTURE SEULE -- le cap de rarete et les buffs
     *  actifs, SANS rien allouer ni armer.
     *
     *  ⚠ CETTE SONDE EXISTE PARCE QUE LE CHEMIN COMPLET A FAIT CRASHER LE JEU (2026-08-21,
     *  `Tacticus.exe.30620.dmp`). Isoler les etages est ce qui permet de dire LEQUEL est fautif
     *  au lieu de retenter le tout et d'esperer. Elle ne fait que LIRE : `GetWarZoneConfig`,
     *  `GetZoneConfig`, `GetRarityCap`, `GetActiveBuffs` -- aucune ecriture, aucun octet reseau.
     *
     *  body: { warZoneId, boardId, slotIndex } */
    ctx.rpc.guildWarEnvProbe = (body?: {
        warZoneId?: string; boardId?: string; slotIndex?: number;
    }): Promise<unknown> => queueOnMainThread(() => {
        if (!body?.warZoneId || !body?.boardId) {
            return { ok: false, error: "`warZoneId` et `boardId` requis" };
        }
        const prog = progressionPhase();
        if (estRefus(prog)) return { ok: false, error: (prog as RefusVue).error };
        const kProg = findClassAnywhere("Idun.Source.IdunMeta.Logic.UserProgress.GuildWars",
                                        "GuildWarPhaseProgression");
        if (!kProg) return { ok: false, error: "classe `GuildWarPhaseProgression` introuvable" };

        const rar = capDeRarete(kProg, prog as NativePointer, body.boardId, body.slotIndex ?? 0);
        if (estRefus(rar)) return { ok: false, etage: "capDeRarete", error: (rar as RefusVue).error };
        const { cap, ordinal } = rar as { cap: number; ordinal: number };

        const mBuffs = findMethodByParamCount(kProg, "GetActiveBuffs", 1);
        if (!mBuffs) return { ok: false, etage: "GetActiveBuffs", error: "INTROUVABLE" };
        let buffs: NativePointer;
        try {
            buffs = invokeMethod(mBuffs.info, prog as NativePointer,
                                 [createManagedString(body.warZoneId)]);
        } catch (e) {
            return { ok: false, etage: "GetActiveBuffs", error: (e as Error).message };
        }
        return {
            ok: true, lecture: true, rarityCap: cap, ordinalTypeDeZone: ordinal,
            nbBuffs: buffs.isNull() ? null : buffs.add(0x18).readS32(),
            // Le brut SERIALISE : c'est la voie sure pour voir `buffAmount` (le NIVEAU, donc le
            // nombre de salves) et `buffAbilityConfig` sans toucher au dictionnaire natif.
            buffs: enJson(buffs),
            note: "LECTURE SEULE -- rien n'a ete alloue ni arme.",
        };
    });

    ctx.rpc.guildWarSourceBc = (body?: {
        confirmer?: boolean; isRestart?: boolean;
    }): Promise<unknown> => queueOnMainThread(() => {
        const src = sourceForgeeGw;
        if (src === null || src.isNull()) {
            return refus("aucune `GuildWarsGameModeSource` forgee -- appeler "
                + "`guildWarSourceForger {confirmer:true}` d'abord");
        }
        let classe: string | null = null;
        try { classe = cstr(class_get_name(src.readPointer()) as NativePointer); } catch { /* nomme */ }
        if (classe !== "GuildWarsGameModeSource") {
            return refus(`l'instance retenue est une \`${classe}\`, PAS une `
                + "`GuildWarsGameModeSource` -- invoquer dessus executerait du natif sur une "
                + "disposition memoire etrangere");
        }
        if (body?.confirmer !== true) {
            return { ok: true, lecture: true, instance: src.toString(), classe,
                     note: "`confirmer: true` exige : ce RPC INVOQUE "
                         + "`GuildWarsGameModeSource$$LoadBattleInternal`. Il ne depense RIEN, "
                         + "mais il ECRIT `_currentBattle` sur la source forgee." };
        }
        const m = findMethodByParamCount(
            findClassAnywhere("IdunBattle.ViewLogic.BattleSource",
                              "GuildWarsGameModeSource") as NativePointer,
            "LoadBattleInternal", 1);
        if (!m) return refus("`LoadBattleInternal(1)` INTROUVABLE -- chemin PERIME");
        const b8 = Memory.alloc(1);
        b8.writeU8(body?.isRestart === true ? 1 : 0);
        let bc: NativePointer;
        try { bc = invokeMethod(m.info, src, [b8]); }
        catch (e) { return refus("`LoadBattleInternal` a LEVE : " + (e as Error).message); }
        if (bc.isNull()) return refus("`LoadBattleInternal` a rendu NUL");
        gcRoot.add(bc);
        if (!isSerializerReady()) {
            return refus("serialiseur Newtonsoft non resolu -- la BC existe (" + bc.toString()
                + ") mais reste illisible");
        }
        let json: string | null;
        try { json = serializeToJson(bc); }
        catch (e) { return refus("serialisation de la BC : " + (e as Error).message); }
        if (json === null) {
            return refus("serialisation NULLE -- la BC EXISTE (" + bc.toString()
                + ") mais Newtonsoft ne l'a pas rendue");
        }
        return { ok: true, instance: src.toString(), bc: bc.toString(),
                 configJson: json, bytes: json.length };
    });

    /** Fabrique la BC d'un match de guild war et la rend en JSON. AUCUN montage, AUCUN reseau.
     *
     *  DEUX REGIMES, ET LE DEFAUT EST CELUI DU JEU
     *  --------------------------------------------
     *  - `warZoneId` fourni (VOIE NORMALE) : le CATALOGUE vient de
     *    `GetUsableAndExhaustedUnits(true, (warZoneId, slotIndex))`, exactement comme
     *    `GuildWarsGameModeSource$$.ctor` le remplit, et `mainPlayerUnits` reste NUL -- donc la
     *    phase de deploiement choisit, comme en jeu.
     *  - `playerUnits` fourni SANS `warZoneId` (voie DEGRADEE, conservee pour les montages
     *    deterministes) : le catalogue se limite a ces ids. ⚠ Toute unite posee hors de cette
     *    liste sera une entite SANS DEFINITION -- c'est le blocage #10038. */
    ctx.rpc.guildWarBuildBc = (body?: {
        id?: string; boardId?: string; spawnPointsSet?: number;
        warZoneId?: string; slotIndex?: number;
        playerUnits?: string[]; preDeployedUnits?: string[]; enemyLineupJson?: string;
        playerAmmo?: number; randomizeAiInput?: boolean;
        environmentAbilitiesJson?: string; enemyMachineJson?: string;
        enemyResolver?: ResolveurEnnemi;
    }): Promise<unknown> | unknown => {
        if (!body?.boardId) return { ok: false, error: "`boardId` manquant" };
        if (!body?.enemyLineupJson) {
            return { ok: false, error: "`enemyLineupJson` manquant -- c'est la liste des "
                + "`PredefinedUnit` du camp adverse, celle qu'un guild war oppose" };
        }
        const joueurs = body.playerUnits ?? [];
        if (!body.warZoneId && joueurs.length === 0) {
            return { ok: false, error: "il faut `warZoneId` (le catalogue vient alors du JEU, "
                + "MoW comprises -- voie normale) OU `playerUnits` (catalogue restreint a ces "
                + "ids -- voie degradee, cf. #10038)" };
        }

        return queueOnMainThread(() => {
            const kB = findClassAnywhere(NS_VIEW, "BattleConfigBuilder");
            if (!kB) return { ok: false, error: "`BattleConfigBuilder` introuvable" };
            const m = findMethodByParamCount(kB, "GetGuildWarsConfig", 14);
            if (!m) {
                return { ok: false, error: "`BattleConfigBuilder$$GetGuildWarsConfig` a 14 "
                    + "parametres INTROUVABLE -- signature changee, chemin PERIME" };
            }
            const deps = lireDeps();
            if (estRefus(deps)) return { ok: false, error: (deps as RefusVue).error };
            const d = deps as Deps;
            const univers = getCapturedUniverse();
            if (!univers) {
                return { ok: false, error: "`IdunUniverse` NON CAPTURE -- rejouer l'amorce" };
            }

            // --- le builder, monte comme `LoadBattleInternal` le monte -------------------------
            const kVals = findClassAnywhere(NS_VIEW, "BattleConfigGameConfigValues");
            // ⚠ DEUX ctors a 2 parametres existent : `(GameConfigDto, List<TileConfiguration>)` et
            // `(GameConfigDto, ITileConfigurationSource)`. `findCtorByParamCount` rendrait le
            // PREMIER, donc potentiellement celui qui attend une liste de tuiles -- on lui
            // passerait l'univers, et le natif fauterait plus loin sans dire pourquoi. On lie donc
            // par la CLASSE du parametre, jamais par son compte.
            const ctorVals = kVals
                ? findMethodByParamClasses(kVals, ".ctor", [null, "ITileConfigurationSource"])
                : null;
            if (!kVals || !ctorVals) {
                return { ok: false, error: "`BattleConfigGameConfigValues..ctor(GameConfigDto, "
                    + "ITileConfigurationSource)` INTROUVABLE -- l'autre surcharge attend une "
                    + "`List<TileConfiguration>` et ne convient pas ; signature changee ?" };
            }
            const vals = il2cpp_object_new(kVals);
            gcRoot.add(vals);
            invokeMethod(ctorVals.info, vals, [d.gameConfig, univers]);

            const kSet = findClassAnywhere(NS_VIEW, "BattleConfigSettings");
            const mFrom = kSet ? findMethodByParamCount(kSet, "FromFeatureToggles", 1) : null;
            if (!mFrom) {
                return { ok: false, error: "`BattleConfigSettings$$FromFeatureToggles` introuvable" };
            }
            const settings = invokeMethod(mFrom.info, NULL, [d.featureUnlocker]);

            const ctorB = findCtorByParamCount(kB, 5);
            if (!ctorB) return { ok: false, error: "`BattleConfigBuilder` ctor(5) introuvable" };
            const builder = il2cpp_object_new(kB);
            gcRoot.add(builder);
            // ⚠ `releasableUnitsSource` N'EST PAS NUL, et le supposer a coute un aller-retour.
            // `GuildWarsGameModeSource$$LoadBattleInternal` monte le builder avec
            // `(unitProgression, values, uVar9, logger, settings)` ou `uVar9 = thor.Globals+0x1e0`
            // -- LE MEME objet qu'il vient de passer comme `universe` a
            // `BattleConfigGameConfigValues..ctor`. L'`IdunUniverse` implemente donc les DEUX
            // interfaces (`ITileConfigurationSource` ET `IReleasableUnitsSource`). `GetGuildWarsConfig`
            // ne le lit peut-etre pas lui-meme, mais `GetLevelConfigWithRealUnits`, qu'elle appelle,
            // si. On passe l'univers, comme le jeu.
            invokeMethod(ctorB.info, builder, [d.prog, vals, univers, d.logger, settings]);

            // --- les 14 arguments, chacun lie contre la CLASSE de son parametre ----------------
            const mi = m.info;
            const lineup = depuisJson(mi, 3, body.enemyLineupJson as string);
            if (estRefus(lineup)) return { ok: false, error: (lineup as RefusVue).error };

            const resolveur: ResolveurEnnemi = body.enemyResolver ?? "hero";
            const getEnemy = construireGetEnemyUnit(mi, 4, d.prog, resolveur);
            if (estRefus(getEnemy)) return { ok: false, error: (getEnemy as RefusVue).error };

            let envAb: NativePointer = NULL;
            if (body.environmentAbilitiesJson) {
                const e = depuisJson(mi, 5, body.environmentAbilitiesJson);
                if (estRefus(e)) return { ok: false, error: (e as RefusVue).error };
                envAb = e as NativePointer;
            }

            // --- arg 6 : LE CATALOGUE. Du JEU quand on a l'adresse de la zone. ----------------
            let dispo: NativePointer;
            let catalogueSource: string;
            let nbEpuisees: number | null = null;
            if (body.warZoneId) {
                const prog = progressionPhase();
                if (estRefus(prog)) return { ok: false, error: (prog as RefusVue).error };
                const kProg = findClassAnywhere("Idun.Source.IdunMeta.Logic.UserProgress.GuildWars",
                                                "GuildWarPhaseProgression");
                if (!kProg) {
                    return { ok: false, error: "classe `GuildWarPhaseProgression` introuvable" };
                }
                const r = rosterDeGuerre(kProg, prog as NativePointer, true,
                                         body.warZoneId, body.slotIndex ?? 0);
                if (estRefus(r)) return { ok: false, error: (r as RefusVue).error };
                dispo = r.utilisables;
                catalogueSource = "GetUsableAndExhaustedUnits(includeMachinesOfWar: true, "
                    + `("${body.warZoneId}", ${body.slotIndex ?? 0}))`;
                try { nbEpuisees = r.epuisees.isNull() ? 0 : r.epuisees.add(0x18).readS32(); }
                catch { nbEpuisees = null; }
            } else {
                const l = listeDeModeles(mi, 6, d.prog, joueurs);
                if (estRefus(l)) return { ok: false, error: (l as RefusVue).error };
                dispo = l as NativePointer;
                catalogueSource = "playerUnits (voie DEGRADEE -- catalogue restreint, cf. #10038)";
            }

            // --- arg 8 : `mainPlayerUnits`. NUL par defaut, COMME LE JEU. ---------------------
            // ⚠ `LoadBattleInternal` passe `0` a cette position -- verifie au decompile. Y mettre
            // une liste PRE-PLACE les unites et court-circuite la phase de deploiement ; c'est ce
            // que faisait ce module, et c'est la seconde moitie du blocage #10038.
            let mainIds: NativePointer = NULL;
            if (body.preDeployedUnits && body.preDeployedUnits.length > 0) {
                const p = depuisJson(mi, 8, JSON.stringify(body.preDeployedUnits));
                if (estRefus(p)) return { ok: false, error: (p as RefusVue).error };
                mainIds = p as NativePointer;
            }

            let enemyMachine: NativePointer = NULL;
            if (body.enemyMachineJson) {
                const em = depuisJson(mi, 12, body.enemyMachineJson);
                if (estRefus(em)) return { ok: false, error: (em as RefusVue).error };
                enemyMachine = em as NativePointer;
            }

            const i32 = (v: number) => { const p = Memory.alloc(4); p.writeS32(v); return p; };
            const b8 = (v: boolean) => { const p = Memory.alloc(1); p.writeU8(v ? 1 : 0); return p; };
            /** `Nullable<T>` est un TYPE VALEUR : `il2cpp_runtime_invoke` attend un pointeur vers
             *  LA VALEUR, jamais `NULL`. Mesure du 2026-08-18 : passer `NULL` pour
             *  `mainPlayerType` / `enemyPlayerType` fait lever `GetGuildWarsConfig` en
             *  « access violation accessing 0x0 » -- le natif lit `&param` puis dereference.
             *  Une zone a ZERO vaut `hasValue = false`, donc « pas de valeur » : c'est exactement
             *  le defaut que `LoadBattleInternal` passe (il met `0` a ces positions). */
            const nullableVide = () => {
                const p = Memory.alloc(8);
                p.writeU64(0);
                return p;
            };

            let bc: NativePointer;
            try {
                bc = invokeMethod(mi, builder, [
                    createManagedString(body.id ?? "GuildWarsSandbox"),   // 0  id
                    createManagedString(body.boardId as string),          // 1  boardId
                    i32(body.spawnPointsSet ?? 0),                        // 2  spawnPointsSet
                    lineup as NativePointer,                              // 3  opponentLineup
                    getEnemy as NativePointer,                            // 4  getEnemyUnit
                    envAb,                                                // 5  environmentAbilities
                    dispo as NativePointer,                               // 6  availableMainPlayerUnits
                    i32(body.playerAmmo ?? 0),                            // 7  playerAmmo
                    mainIds as NativePointer,                             // 8  mainPlayerUnits
                    nullableVide(),                                       // 9  mainPlayerType (defaut)
                    nullableVide(),                                       // 10 enemyPlayerType (defaut)
                    NULL,                                                 // 11 overrideMainPlayerMachine
                    enemyMachine,                                         // 12 overrideOpponentPlayerMachine
                    b8(body.randomizeAiInput === true),                   // 13 randomizeAiInput
                ]);
            } catch (e) {
                return { ok: false, error: "`GetGuildWarsConfig` a LEVE : " + (e as Error).message };
            }
            if (!bc || bc.isNull()) {
                return { ok: false, error: "`GetGuildWarsConfig` a rendu NUL" };
            }
            if (!isSerializerReady()) {
                return { ok: false, error: "serialiseur Newtonsoft non resolu -- BC construite "
                    + "mais illisible", bc: bc.toString() };
            }
            // ⚠ `serializeToJson` rend `null` quand Newtonsoft refuse -- le distinguer d'une
            // chaine vide, sinon « a refuse » et « a rendu un JSON vide » seraient indiscernables.
            let json: string | null;
            try {
                json = serializeToJson(bc);
            } catch (e) {
                return { ok: false, error: "serialisation de la BC : " + (e as Error).message };
            }
            if (json === null) {
                return { ok: false, error: "la serialisation a rendu NUL -- la BC EXISTE mais "
                    + "Newtonsoft ne l'a pas rendue", bc: bc.toString() };
            }
            return {
                ok: true, bc: bc.toString(), configJson: json, bytes: json.length,
                // CE QUI A REELLEMENT ALIMENTE LE CATALOGUE -- publie parce que c'est le seul
                // discriminant entre une BC jouable et la BC tronquee du blocage #10038.
                catalogue: catalogueSource,
                // PUBLIE : `hero` sur un lineup npc rend des entrees a Health/Damage 0 sans
                // la moindre erreur. Un catalogue muet sur son resolveur se lit comme complet.
                enemyResolver: resolveur,
                epuiseesEcartees: nbEpuisees,
                mainPlayerUnits: mainIds.isNull()
                    ? "NUL -- la phase de deploiement choisit, comme en jeu"
                    : "PRE-PLACEES (" + (body.preDeployedUnits ?? []).length + ")",
            };
        });
    };

    /** L'ETAT DE LA GUERRE, LISIBLE MEME AVANT QU'ELLE COMMENCE.
     *
     *  POURQUOI CE RPC EXISTE. En phase de PREPARATION, `guildWarZones` rend `total: 0` et
     *  `guildWarZoneConfigs` refuse (« `GetAllPossibleScores` n'a pas atteint le calculateur »).
     *  Les deux sont CORRECTS -- les zones ne sont attribuees qu'au demarrage -- mais ils ne
     *  distinguent pas « guerre pas encore commencee » de « cette guilde ne fait pas de GW »
     *  ni de « le client n'a pas rafraichi ». Trois causes, un seul zero : indecidable.
     *
     *  `GetGuildWarIdEvenIfItHasntStartedYet` tranche, et son nom dit qu'il est ECRIT POUR CA :
     *  un identifiant non nul = une guerre est bien programmee pour cette guilde.
     *
     *  LECTURE PURE : que des getters sans argument, invoques sur la progression VIVANTE. Aucune
     *  ecriture, et surtout AUCUN `Fetch*` -- ceux-la (`FetchSeasonLeaderboard`,
     *  `FetchLeagueLeaderboard`) partent au serveur, et ce module n'en appelle aucun. */
    ctx.rpc.guildWarEtat = (): Promise<unknown> => queueOnMainThread(() => {
        const prog = progressionPhase();
        if (estRefus(prog)) return { ok: false, error: (prog as RefusVue).error };
        const sur = prog as NativePointer;
        const k = findClassAnywhere("Idun.Source.IdunMeta.Logic.UserProgress.GuildWars",
                                    "GuildWarPhaseProgression");
        if (!k) return { ok: false, error: "classe `GuildWarPhaseProgression` introuvable" };

        /** Un entier rendu par un getter sans argument. `null` = NON MESURE (methode absente ou
         *  levee), jamais rabattu sur 0 -- « zero tentative » et « pas lisible » sont deux
         *  reponses differentes. */
        const entier = (nom: string): number | null => {
            const r = appeler(k, sur, nom, 0, []);
            if (estRefus(r)) return null;
            try { return (r as NativePointer).toInt32(); } catch { return null; }
        };
        const texte = (nom: string): string | null => {
            const r = appeler(k, sur, nom, 0, []);
            if (estRefus(r)) return null;
            const p = r as NativePointer;
            if (p.isNull()) return null;
            try { return readIl2cppString(p); } catch { return null; }
        };
        const objet = (nom: string): unknown => {
            const r = appeler(k, sur, nom, 0, []);
            if (estRefus(r)) return { erreur: (r as RefusVue).error };
            return enJson(r);
        };

        // L'identifiant de guerre, MEME non demarree -- le discriminant de ce RPC.
        const guerreId = texte("GetGuildWarIdEvenIfItHasntStartedYet");
        const membres = objet("GetBothTeamsGuildMembers");

        return {
            ok: true,
            // `null` ici = aucune guerre programmee pour cette guilde (ou methode peremee) ;
            // une chaine = une guerre EXISTE, meme si la phase de combat n'a pas commence.
            guerreId,
            guerreProgrammee: guerreId !== null,
            tentativesRestantes: entier("GetAttemptsLeft"),
            trophesSiVictoire: entier("GetTrophiesOnWin"),
            trophesSiDefaite: entier("GetTrophiesOnLoss"),
            creditsParUniteVaincue: entier("GetGuildWarCurrencyPerUnitDefeat"),
            nbMembresDesDeuxGuildes: Array.isArray(membres) ? membres.length : null,
            unitesEpuisees: objet("GetExhaustedUnits"),
            cibles: objet("GetTargets"),
            note: "phase de PREPARATION : `guildWarZones` rend 0 et c'est NORMAL -- les zones ne "
                + "sont attribuees qu'au demarrage de la phase de guerre. `guerreProgrammee` "
                + "repond a « y a-t-il une guerre » independamment de ca.",
        };
    });
}
