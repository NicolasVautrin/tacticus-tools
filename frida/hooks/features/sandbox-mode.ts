// sandbox-mode — FABRIQUER une `BattleConfiguration` par mode de jeu, sans capture préalable.
//
// CE QUE ÇA RÉSOUT, ET EN QUOI C'EST L'INVERSE DE `sandbox.ts`
// ------------------------------------------------------------
// `sandbox.ts` CONSOMME une BC déjà écrite : il la désérialise et la donne à
// `TestSceneBattleModeSource`. Il fallait donc l'avoir capturée d'abord — au filet réseau,
// sur une vraie partie.
//
// Ici c'est l'autre sens, et c'est une MESURE, pas une intention :
//
//     IdunBattle.ViewLogic.BattleSource.SandboxGameModeSource$$LoadBattle(isRestart)
//         -> IdunBattle.Configuration.BattleConfiguration
//
// La source ne REÇOIT pas de BC : elle la CONSTRUIT depuis une `ISandboxBattleConfig`. On
// décrit donc une bataille par ses paramètres (unités, board, boss, vagues) et le jeu en
// dérive la BC par son propre code. Aucune capture, aucun replay à rejouer.
//
// ⇒ Deux gestes SÉPARÉS, et la séparation est le point :
//     `sandboxModeBuildBc`  — construit la config, la source, appelle `LoadBattle`, SÉRIALISE
//                             la BC et la rend. RIEN n'est monté à l'écran.
//     `sandboxModeStart`    — la même chose, PUIS `ViewCommandExecutor$$StartMatch`.
//
// POURQUOI CETTE SOURCE-LÀ, ET PAS `TestSceneBattleModeSource`
// -------------------------------------------------------------
// Mesuré : `TestSceneBattleModeSource` ne porte QUE `HandleStartMatch` et
// `HandleStartSpawningUnitsOfTurn`. `SandboxGameModeSource` porte les SIX —
// `HandleBattleException`, `HandleBattleRetryAfterPause`, `HandleBattleSurrender`,
// `HandleFinishBattle`, `HandleLoadBattle`, `HandleStartGame`. C'est la cause ÉTABLIE des
// trois pannes de sortie du 2026-08-16 (retraite sans effet / process tué / chargement
// suspendu) : personne ne recevait la fin de bataille.
//
// ✅ ÉPROUVÉ DE BOUT EN BOUT (2026-08-16, session 19, build `t6dpr4k06g`)
// -----------------------------------------------------------------------
// Onslaught tier 5 monté par `sandboxModeStart` : `IdunMainView` passe d'ABSENTE à vivante,
// 12 unités sur le plateau (5 en équipe 3 — les héros demandés — et 7 en équipe 4, la vague).
// **LA RETRAITE FONCTIONNE** : après elle, `IdunMainView` est de nouveau ABSENTE, aucun
// chargement suspendu, process vivant sur les DEUX critères (RPC queué revenu en 0,14 s,
// `Responding=True`, CPU qui progresse).
//
// C'est la CONFIRMATION de la cause, plus une hypothèse : sur `TestSceneBattleModeSource` la
// retraite ne faisait RIEN (carte figée à l'écran) parce que la source ne porte pas
// `HandleBattleSurrender`. Ici elle le porte, et ça marche.
//
// ⚠ CE QUI RESTE NON MESURÉ. Le ctor à 5 paramètres renseigne 5 des 9 champs : `_gameViews`
// (+0x38) et `_stateMachineActions` (+0x48) restent NULS. Le décompilé montre que ni
// `LoadBattle` ni `HandleLoadBattle` ne les lisent, et que `HandleStartGame` ne les touche que
// pour une config **Draft** — donc ils sont inertes ici, mais un sandbox Draft y buterait.
// `sandboxModeProbe` les RELIT après construction pour que ça se voie.
//
// CE QUE LE MONTAGE ÉCRIT SUR LE COMPTE — RIEN, ET C'EST VÉRIFIÉ AU DÉCOMPILÉ
// ---------------------------------------------------------------------------
// La surface complète de `SandboxGameModeSource` ne porte AUCUN `Send*GameEvent` (relevée
// méthode par méthode) — contrairement à `GuildBossGameModeSource`, dont le
// `SendLoadBattleGameEventInternal` enregistre une tentative AU CHARGEMENT.
// `HandleLoadBattle` fait UN appel d'interface sur `_unitProgression` (slot `0xd8`) avec `1` ;
// `HandleFinishBattle` refait le MÊME appel avec `0`. C'est un drapeau local, et il est
// restauré. Aucun jeton, aucune tentative, aucun loot.
//
// ⚠ ET IL FAIT COURIR LE MÊME RISQUE DE COMPTE QUE `sandbox.ts`
// --------------------------------------------------------------
// `StartMatch` ÉCRASE le match courant (champ statique) puis `thor.Loader$$LoadBattle`. Côté
// boss de guilde, la tentative est enregistrée AU CHARGEMENT — écraser un match enregistré et
// non terminé PERD la tentative, sans qu'aucun compteur local ne bouge. D'où
// `checkIfAlreadyRunning` à `true` par défaut, comme dans `sandbox.ts`.
//
// ⚠ La progression passée à la source est celle DU COMPTE, et c'est OBLIGÉ ici : les
// `IUnitModel` viennent de `UnitProgression$$GetUnit`, et une progression de test est VIDE —
// elle rendrait une BC sans unités. Le ctor déclare `IUnitProgression` (pas une classe de
// test), donc la substitution qui avait corrompu `_powerFormula` ne s'applique pas. Ce qui
// reste vrai : `SandboxGameModeSource` ne porte AUCUN `Send*GameEvent` (surface relevée
// méthode par méthode) — mais le corps de `LoadBattle` n'a pas été décompilé.
//
// COMMENT LES ARGUMENTS SONT LIÉS — PAR LA CLASSE DU PARAMÈTRE, JAMAIS PAR UN NOM ÉCRIT ICI
// -------------------------------------------------------------------------------------------
// Chaque `Sandbox<Mode>BattleConfig` a un ctor différent (5 paramètres pour Waves, 14 pour le
// boss de guilde). Plutôt que de recopier ces signatures — qui se périmeraient au prochain
// build, EN SILENCE —, le module lit la classe de CHAQUE paramètre au runtime
// (`methodParamClass`) et lie l'argument fourni contre elle. Un décalage d'arité est un REFUS
// NOMMÉ, pas un appel tenté.
//
// C'est aussi ce qui rend les collections constructibles sans rien inventer : `List<UnitModifier>`
// et `Dictionary<String, List<UnitModifier>>` sont des types INFLATÉS, introuvables par leur
// nom — mais parfaitement lisibles comme classe du paramètre 12 ou 14 du ctor. Une fois la
// classe en main, Newtonsoft les remplit depuis du JSON.
//
// ⚠ « WAVES » EST L'ONSLAUGHT, ET DEUX TYPES DE VAGUE PORTENT LE MÊME MOT
// -----------------------------------------------------------------------
// `BattleConfigBuilder$$GetHotSeatGameModeSpecificConfig` n'a PAS de branche « Waves » : il
// route `SandboxWavesBattleConfig` vers `GetOnslaughtConfig`, et les offsets concordent un à
// un (`+0x28` PlayerType, `+0x38` machine, `+0x40` AllUnits, `+0x48` DTO). Il n'a pas non plus
// de branche LEGENDARY EVENT — les dix types portés sont TreasureBeach, CampaignEvent,
// Waves(→Onslaught), Survival, GuildBoss, SyncPvp, Territories, Draft, Infested, Boosts.
//
// La forme attendue, MESURÉE (`classFields` + type de retour du convertisseur) :
//     WaveBattleConfigDto { spawnPointsSet:Int32, boardId:String, waves:List<WaveConfigDto> }
//     WaveConfigDto       { round:Int32, enemies:Dictionary<K,List<String>>, rewards:... }
// et `OnslaughtGameModeSource.<>c.<GetWaveBattleConfigDto>b__52_0` met TOUTES les `EnemyIds`
// sous UNE SEULE clé de ce dictionnaire.
//
// Le piège coûte un throw natif : une vague de legendary event est un `BattleSetWaveConfigDto`
// (`round`/`army`, AUCUN dictionnaire), donc `GetOnslaughtConfig` déréférence `vague+0x18` à
// null et part sur `FUN_1801f5460` (ne revient pas). Mesuré le 2026-08-16 — le jeu survit, mais
// l'erreur remonte en « system error » sans rien nommer. Les battleSets passent par les configs
// qui prennent un `BattleSetConfigDto` : survival et infested.

import {
    class_get_fields, class_get_methods, class_get_name, class_get_nested_types, class_get_parent,
    class_is_valuetype, field_get_name, field_get_offset, field_get_type, findClassAnywhere,
    findMethodByParamClasses, findMethodByParamCount, getFieldOffset, method_get_name,
    methodEntry, methodParamClass, readIl2cppString, readStaticObjectField, s,
    type_get_class_or_element_class,
} from "../il2cpp/helpers.js";
import { state } from "../game/state.js";
import { createManagedString, il2cpp_object_new, invokeMethod } from "../il2cpp/invoke.js";
// `battle-config` porte le FOYER UNIQUE d'application du patch : la sandbox
// SUBSTITUE une BC, elle ne mute pas celle du `LoadBattle` -- c'est donc a elle
// de faire passer SON objet par ce pipeline.
import * as battleConfig from "./battle-config.js";
import { deserializeFromJson, isDeserializerReady, isSerializerReady, serializeToJson }
    from "../il2cpp/serializer.js";
import { chargementEnCours } from "../game/loader.js";
import { gcRoot } from "../il2cpp/gc-root.js";
import { queueOnMainThread } from "../runtime/queue.js";
import { executeurVivant, premiereInstance } from "./view-command.js";
import { noterSourceMontee } from "./source-vivante.js";
// (!)FORME B (`import * as` puis appel attributaire), et c'est la doctrine du dépôt : une
// liaison de module n'est jamais gelée, donc elle reste substituable par un test. `deployment-
// draft` n'importe pas ce module -- pas de cycle.
import * as deploymentDraft from "./deployment-draft.js";
// (!)FORME B aussi, et le foyer est CHEZ LUI : `pvp-opponents` porte la marche
// `_pvpProgression -> _pvpProgressionData -> latestOpponents`, avec un refus nommé à chaque
// pas. La recopier ici aurait fait deux versions d'une garde. Pas de cycle : `pvp-opponents`
// n'importe pas ce module.
import * as pvpOpponents from "./pvp-opponents.js";
// (!)FORME B. Le FOYER du réceptacle `EnvironmentAbilities`, extrait de `guild-war-config.ts`
// le 2026-08-22 : les deux modules posent le même objet, dont le ctor natif ne crée AUCUN des
// trois membres. Deux copies auraient divergé -- et ce sont des ÉCRITURES en mémoire managée.
import * as envAbilities from "./environment-abilities.js";
// Le FOYER du forcage d'initialisation de classe (#982-r6). Il tient la discipline qui compte :
// lire l'etat AVANT, et distinguer une classe deja chaude d'une classe qu'on a chauffee soi-meme.
import { ClassInitState, classInitState, LIVE_CLASS_INIT_PROBE } from "../il2cpp/class-init.js";
import { Ctx } from "../controller.js";

interface Refus { ok: false; error: string }
function estRefus(x: unknown): x is Refus {
    return typeof x === "object" && x !== null && (x as { ok?: unknown }).ok === false;
}
function refus(msg: string): Refus { return { ok: false, error: msg }; }

const NS_CFG = "IdunBattle.ViewLogic.BattleSource.SandboxBattleConfig";
const NS_SRC = "IdunBattle.ViewLogic.BattleSource";
/** Le namespace de `BattleConfigBuilder` -- la FABRIQUE de BC, pas une source. */
const NS_VIEW = "Idun.Source.IdunBattle.View";

/** Les modes portés, et LEUR CLASSE — c'est la seule table écrite en dur, et elle ne contient
 *  que des NOMS (stables à 97,5 % inter-build), jamais une arité ni un ordre de paramètres.
 *  Ceux-là se lisent au runtime.
 *
 *  Les huit autres modes existent et sont atteignables par `classe` explicite : la table sert
 *  d'alias commode, pas de liste blanche. */
const MODES: Record<string, string> = {
    waves: "SandboxWavesBattleConfig",
    guildBoss: "SandboxGuildBossBattleConfig",
    survival: "SandboxSurvivalBattleConfig",
    treasureBeach: "SandboxTreasureBeachBattleConfig",
    pvp: "SandboxPvpBattleConfig",
    campaignEvent: "SandboxCampaignEventBattleConfig",
    boosts: "SandboxBoostsBattleConfig",
    draft: "SandboxDraftBattleConfig",
    infested: "SandboxInfestedBattleConfig",
    territories: "SandboxTerritoriesBattleConfig",
};

/** Un argument de ctor, décrit par son GENRE. Le genre dit COMMENT lier, la classe du
 *  paramètre dit CONTRE QUOI — les deux sont nécessaires, et aucun ne se déduit de l'autre. */
type Arg =
    | { genre: "entier"; valeur: number }        // int, enum (PlayerType, Rarity, ...)
    | { genre: "booleen"; valeur: boolean }
    | { genre: "texte"; valeur: string | null }
    | { genre: "unite"; id: string; voie?: "unit" | "npc" | "summon" }
    | { genre: "unites"; ids: string[]; voie?: "unit" | "npc" | "summon" }
    // ⚠ UN `List`1` NE DIT PAS SA PROFONDEUR. `SandboxPvpBattleConfig..ctor` déclare
    // `playerUnits : List<List<IUnitModel>>` (une liste PAR JOUEUR), et la classe inflatée
    // s'affiche `List`1` exactement comme un `List<IUnitModel>`. Or `il2cpp_runtime_invoke`
    // ne type-check pas : `unites` y ajouterait des `IUnitModel` sans rien lever, et la
    // corruption ne se verrait qu'à l'itération côté jeu. D'où un genre SÉPARÉ.
    | { genre: "unitesParJoueur"; joueurs: JoueurSpec[] }
    // L'équipe RÉELLE d'un adversaire d'Arène, matérialisée PAR LE JEU. Cf. `lineupAdverse`.
    | { genre: "machineAdverse"; adversaire: number }
    | { genre: "json"; valeur: unknown }         // DTO, List<String>, Dictionary<...>
    | { genre: "nul" };

/** Un joueur de `unitesParJoueur`. `ids` et `adversaire` sont EXCLUSIFS.
 *
 *  ⚠ `ids` résout sur NOTRE progression (`UnitProgression$$GetUnit`) — c'est ce qu'il faut pour
 *  notre camp, et c'est FAUX pour un camp adverse : ça rend NOS unités sous LEURS noms (mesuré
 *  le 2026-08-22 — un `darkaAzrael` qu'on ne possède pas sortait à rang 0 / puissance 562,
 *  et un `ultraTigurius` présent des deux côtés ne faisait QU'UNE entrée de catalogue). */
interface JoueurSpec {
    ids?: string[];
    voie?: "unit" | "npc" | "summon";
    /** INDEX d'une proposition d'Arène (`latestOpponents`). ⚠ Les propositions TOURNENT :
     *  un index mémorisé désignera quelqu'un d'autre au rafraîchissement suivant. */
    adversaire?: number;
}

// --- primitives génériques -------------------------------------------------------------

/** La classe d'un objet managé = le premier mot de son en-tête. C'est ce qui permet de partir
 *  d'un champ déclaré par une INTERFACE (`IUnitProgression`, `IGameConfigData`) et d'atteindre
 *  quand même les méthodes de son type CONCRET. */
function classeDeLObjet(obj: NativePointer): NativePointer | null {
    if (obj.isNull()) return null;
    try {
        const k = obj.readPointer();
        return k.isNull() ? null : k;
    } catch { return null; }
}

function nomDeClasse(k: NativePointer | null): string | null {
    if (!k || k.isNull()) return null;
    try { return s(class_get_name(k) as NativePointer); } catch { return null; }
}

/** Type valeur ? TRI-ÉTAT : `null` = PAS MESURÉ (l'export `il2cpp_class_is_valuetype` est
 *  résolu de façon tolérante et peut manquer), jamais rendu comme un `false`. */
function estTypeValeur(k: NativePointer | null): boolean | null {
    if (!k || k.isNull() || !class_is_valuetype) return null;
    try { return (class_is_valuetype(k) as number) !== 0; } catch { return null; }
}

/** Alloue + appelle le ctor SANS argument. Utilisé pour les `List<T>` inflatées, dont la
 *  classe vient d'un paramètre de ctor et non d'une recherche par nom (impossible : le nom
 *  d'un générique inflaté n'est pas indexé).
 *
 *  ⚠ PAS de `runtime_class_init` ici, et c'est délibéré : le dépôt le tient pour le seul
 *  wrapper de `helpers.ts` qui ait un EFFET, à n'appeler que sous un drapeau explicite. Il
 *  n'est pas nécessaire — `il2cpp_object_new` amorce la classe lui-même, et c'est déjà par
 *  cette voie que `sandbox.ts` construit `TestSceneBattleModeSource`. */
function collectionVide(klass: NativePointer): NativePointer | Refus {
    const ctor = findMethodByParamCount(klass, ".ctor", 0);
    if (!ctor) {
        return refus("`" + (nomDeClasse(klass) ?? "?") + "..ctor` sans argument INTROUVABLE "
            + "-- on ne sait pas fabriquer cette collection, et on ne se replie pas sur "
            + "un `new` nu (l'objet serait non initialisé)");
    }
    try {
        const p = il2cpp_object_new(klass) as NativePointer;
        if (p.isNull()) return refus("il2cpp_object_new -> NULL sur " + nomDeClasse(klass));
        gcRoot.add(p);
        invokeMethod(ctor.info, p, []);
        return p;
    } catch (e) {
        return refus("ctor de " + nomDeClasse(klass) + " a levé : " + (e as Error).message);
    }
}

/** `IUnitModel` depuis un `unitId`, par la voie DEMANDÉE.
 *
 *  Les trois voies sont DISTINCTES côté natif (`GetUnit` / `GetNpcUnit` / `GetSummonUnit`) et
 *  un id de npc passé à `GetUnit` rend `null` — donc un modèle nul silencieux dans la liste,
 *  et une BC amputée sans erreur. On refuse plutôt, en nommant la voie essayée. */
function modeleUnite(
    prog: NativePointer, id: string, voie: "unit" | "npc" | "summon",
): NativePointer | Refus {
    const kProg = classeDeLObjet(prog);
    if (!kProg) return refus("classe de l'IUnitProgression illisible");
    const nom = voie === "npc" ? "GetNpcUnit" : voie === "summon" ? "GetSummonUnit" : "GetUnit";
    const mi = findMethodByParamCount(kProg, nom, 1);
    if (!mi) {
        return refus("`" + (nomDeClasse(kProg) ?? "?") + "$$" + nom + "` à 1 paramètre "
            + "INTROUVABLE -- ne pas replier sur une autre voie : elles ne lisent pas le "
            + "même catalogue");
    }
    let r: NativePointer;
    try { r = invokeMethod(mi.info, prog, [createManagedString(id)]); }
    catch (e) { return refus(nom + "(" + id + ") a levé : " + (e as Error).message); }
    if (r.isNull()) {
        return refus(nom + "(\"" + id + "\") a rendu NULL -- id inconnu de cette voie "
            + "(un npc ou un summon ne se lit PAS par `GetUnit`)");
    }
    return r;
}

// --- l'équipe adverse RÉELLE ------------------------------------------------------------
//
// ⚠ ON NE FABRIQUE RIEN, ON DEMANDE AU JEU — et ce n'est pas un principe, c'est ce que le
// décompilé impose. `BattleConfigBuilder$$GetHotseatSyncPvpConfig` range `cfg.PlayerUnits[1]`
// dans le champ `+0x28` de son display class, et son résolveur
// `<>c__DisplayClass37_0$$<GetHotseatSyncPvpConfig>g__GetEnemy|0` finit sur
// `Enumerable.First(PlayerUnits[1], u => u.Id == unitId)`. La délégation EXISTE donc déjà et
// lit la liste qu'on fournit : il n'y a rien à ancrer, seulement à y mettre les BONS modèles.
//
// ⚠ ET C'EST L'OBJET ADVERSE QUI LES PORTE, PAS NOTRE PROGRESSION.
// `PvpOpponentProgressionData` garde la progression de l'adversaire unité par unité
// (`<units>k__BackingField`, remplie par `PvpServerResponseTranslator$$ApplyUnitInfo` depuis
// le DTO serveur : rank, xpLevel, upgrades, items). Ses deux accesseurs prennent NOTRE
// `IUnitProgression` / `IItemProgression` comme SERVICES de lecture du catalogue, mais les
// stats sortent de SES données :
//
//     GetPublicProfileLineup(unitProgression, itemProgression, logger, overrideLineup)
//         -> List<IUnitModel>          <- exactement le type de `PlayerUnits[1]`
//     GetPublicProfileMachineOfWarLineup(unitProgression, itemProgression, logger, overrideLineup)
//         -> IUnitModel
//
// `overrideLineup` reste NUL : sans lui le natif prend le lineup public de l'adversaire, qui
// est précisément ce qu'on veut affronter.

/** Les trois services que les deux accesseurs adverses réclament, ou un refus NOMMÉ. */
function servicesProfil(deps: Deps): NativePointer[] | Refus {
    if (deps.itemProg === null) {
        return refus("`ViewCommandExecutor._itemProgression` NON LU (champ absent ou nul) -- "
            + "c'est le 2e argument de `GetPublicProfileLineup`, et on ne le remplace pas par "
            + "un nul : le natif s'en sert pour lire les objets équipés de l'adversaire");
    }
    return [deps.prog, deps.itemProg, deps.logger, ptr(0)];
}

/** L'accesseur `nom` sur la `PvpOpponentProgressionData` de la proposition `index`. */
function invoquerSurAdversaire(
    deps: Deps, index: number, nom: string,
): NativePointer | Refus {
    const adv = pvpOpponents.adversaireParIndex(index);
    if (estRefus(adv)) return adv;
    const kAdv = classeDeLObjet(adv as NativePointer);
    if (!kAdv) return refus("classe de l'adversaire " + index + " illisible");
    const mi = findMethodByParamCount(kAdv, nom, 4);
    if (!mi) {
        return refus("`" + (nomDeClasse(kAdv) ?? "?") + "$$" + nom + "` à 4 paramètres "
            + "INTROUVABLE -- chemin PÉRIMÉ. Ne PAS se replier sur les ids du lineup : les "
            + "résoudre sur notre progression rendrait NOS unités sous LEURS noms, sans rien "
            + "lever, et c'est exactement le bug que ce genre existe pour fermer.");
    }
    const svc = servicesProfil(deps);
    if (estRefus(svc)) return svc;
    try { return invokeMethod(mi.info, adv as NativePointer, svc); }
    catch (e) { return refus(nom + "(adversaire " + index + ") a levé : " + (e as Error).message); }
}

/** `List<IUnitModel>` de l'équipe adverse RÉELLE. */
function lineupAdverse(deps: Deps, index: number): NativePointer | Refus {
    const l = invoquerSurAdversaire(deps, index, "GetPublicProfileLineup");
    if (estRefus(l)) return l;
    if (l.isNull()) {
        return refus("`GetPublicProfileLineup(adversaire " + index + ")` a rendu NULL -- "
            + "l'adversaire est chargé mais sans lineup public");
    }
    gcRoot.add(l);
    return l;
}

/** Lie UN argument contre la classe RÉELLE de son paramètre. */
function lier(
    kParam: NativePointer | null, a: Arg, deps: Deps,
): NativePointer | Refus {
    const prog = deps.prog;
    switch (a.genre) {
        case "nul":
            return ptr(0);
        case "entier": {
            // Un type valeur se passe par ADRESSE de la valeur non boxée. `il2cpp_runtime_invoke`
            // ne type-check pas : un entier passé là où un objet est attendu ne lève rien, il
            // fabrique un pointeur. D'où le contrôle ci-dessous.
            // ⚠ TRI-ÉTAT : `class_is_valuetype` est résolu de façon TOLÉRANTE (null si
            // l'export manque). « pas mesurable » n'autorise pas à refuser — sinon un export
            // absent bloquerait tous les enums. On ne refuse que sur un `false` MESURÉ.
            const vt = estTypeValeur(kParam);
            if (vt === false) {
                return refus("argument `entier` sur un paramètre de type RÉFÉRENCE ("
                    + nomDeClasse(kParam) + ") -- refus : ce serait un pointeur fabriqué");
            }
            const b = Memory.alloc(4); b.writeS32(a.valeur); return b;
        }
        case "booleen": {
            const b = Memory.alloc(1); b.writeU8(a.valeur ? 1 : 0); return b;
        }
        case "texte":
            return a.valeur === null ? ptr(0) : createManagedString(a.valeur);
        case "unite":
            return modeleUnite(prog, a.id, a.voie ?? "unit");
        case "unites": {
            if (!kParam) return refus("classe du paramètre illisible -- liste non constructible");
            const l = collectionVide(kParam);
            if (estRefus(l)) return l;
            const add = findMethodByParamCount(kParam, "Add", 1);
            if (!add) return refus("`Add` à 1 paramètre absent de " + nomDeClasse(kParam));
            // GARDE : le paramètre attend-il des LISTES ? Le nom de classe ne le dit pas
            // (`List`1` des deux côtés) -- l'élément, lui, le dit. Sans ce refus on écrirait
            // des `IUnitModel` dans un `List<List<...>>` SANS que rien ne lève.
            const kElem = methodParamClass(add.info, 0);
            if (nomDeClasse(kElem) === "List`1") {
                return refus("ce paramètre est une LISTE DE LISTES (" + nomDeClasse(kParam)
                    + " d'éléments `List`1`) -- utilise `unitesParJoueur`, une entrée par "
                    + "joueur. `unites` y écrirait des modèles à plat, sans rien lever.");
            }
            for (const id of a.ids) {
                const m = modeleUnite(prog, id, a.voie ?? "unit");
                if (estRefus(m)) return m;
                try { invokeMethod(add.info, l, [m]); }
                catch (e) { return refus("Add(" + id + ") a levé : " + (e as Error).message); }
            }
            return l;
        }
        case "unitesParJoueur": {
            if (!kParam) return refus("classe du paramètre illisible -- liste non constructible");
            const ext = collectionVide(kParam);
            if (estRefus(ext)) return ext;
            const addExt = findMethodByParamCount(kParam, "Add", 1);
            if (!addExt) return refus("`Add` à 1 paramètre absent de " + nomDeClasse(kParam));
            // La classe de la liste INTERNE se lit sur le paramètre d'`Add`, jamais par nom :
            // le nom d'un générique inflaté n'est pas indexé, et `List`1` ne distingue pas
            // `List<IUnitModel>` de `List<List<IUnitModel>>`.
            const kInt = methodParamClass(addExt.info, 0);
            if (!kInt) return refus("classe de l'élément de " + nomDeClasse(kParam)
                + " illisible -- on ne devine pas le type de la liste interne");
            const addInt = findMethodByParamCount(kInt, "Add", 1);
            if (!addInt) {
                return refus("`Add` à 1 paramètre absent de l'élément `"
                    + (nomDeClasse(kInt) ?? "?") + "` -- ce paramètre n'est PAS une liste de "
                    + "listes ; c'est `unites` qu'il faut, pas `unitesParJoueur`");
            }
            for (let j = 0; j < a.joueurs.length; j++) {
                const spec = a.joueurs[j];
                const parIds = Array.isArray(spec.ids);
                const parAdv = typeof spec.adversaire === "number";
                // EXCLUSIFS, et les DEUX manques se nomment. « ni l'un ni l'autre » donnerait
                // une équipe VIDE sans rien lever ; « les deux » ferait taire silencieusement
                // l'une des deux intentions.
                if (parIds && parAdv) {
                    return refus("joueur " + j + " : `ids` ET `adversaire` fournis -- ils sont "
                        + "EXCLUSIFS (l'un résout sur NOTRE progression, l'autre sur la SIENNE)");
                }
                if (!parIds && !parAdv) {
                    return refus("joueur " + j + " : ni `ids` ni `adversaire` -- une équipe vide "
                        + "ne serait signalée par rien");
                }

                let interne: NativePointer;
                if (parAdv) {
                    // ⚠ LA LISTE VIENT DU JEU, ENTIÈRE : on ne la recopie pas élément par
                    // élément dans une `collectionVide`, ce qui n'apporterait rien et
                    // ajouterait un point de divergence.
                    const l = lineupAdverse(deps, spec.adversaire as number);
                    if (estRefus(l)) return refus("joueur " + j + " : " + l.error);
                    // GARDE DE TYPE : `List`1` ne distingue rien par son nom. On compare la
                    // classe RENDUE à celle que le paramètre attend -- un `List<String>` glissé
                    // là ne lèverait qu'à l'itération, côté jeu, loin d'ici.
                    const kRendu = classeDeLObjet(l);
                    if (kRendu === null || !kRendu.equals(kInt)) {
                        const nr = nomDeClasse(kRendu) ?? "?", ni = nomDeClasse(kInt) ?? "?";
                        // ⚠ Deux causes, et un message unique se lirait comme du charabia dans
                        // le second cas (« un `List`1` là où on attend un `List`1` »). IL2CPP
                        // INTERNE les instanciations génériques, donc deux pointeurs distincts
                        // pour un même nom veut dire que l'hypothèse d'internement est fausse
                        // sur ce build -- pas que les types diffèrent.
                        return refus("joueur " + j + " : " + (nr === ni
                            ? "`GetPublicProfileLineup` rend bien un `" + nr + "` mais d'une "
                                + "CLASSE INFLATÉE DIFFÉRENTE (" + kRendu + " vs " + kInt
                                + ") -- l'internement des génériques ne tient pas ici, la garde "
                                + "de type est à revoir avant de forcer"
                            : "`GetPublicProfileLineup` a rendu un `" + nr + "` là où le "
                                + "paramètre attend un `" + ni + "` -- types INCOMPATIBLES"));
                    }
                    interne = l;
                } else {
                    const vide = collectionVide(kInt);
                    if (estRefus(vide)) return vide;
                    interne = vide;
                    for (const id of spec.ids as string[]) {
                        const m = modeleUnite(prog, id, spec.voie ?? "unit");
                        if (estRefus(m)) return refus("joueur " + j + " : " + m.error);
                        try { invokeMethod(addInt.info, interne, [m]); }
                        catch (e) {
                            return refus("joueur " + j + " : Add(" + id + ") a levé : "
                                + (e as Error).message);
                        }
                    }
                }
                try { invokeMethod(addExt.info, ext, [interne]); }
                catch (e) {
                    return refus("Add(liste du joueur " + j + ") a levé : "
                        + (e as Error).message);
                }
            }
            return ext;
        }
        case "machineAdverse": {
            // ⚠ TRI-ÉTAT ASSUMÉ : un adversaire PEUT n'avoir aucune machine de guerre, et
            // `EnemyPlayerMachineOfWar` accepte un nul. On rend donc `ptr(0)` sur un NULL lu --
            // mais JAMAIS sur un échec d'appel, qui reste un refus nommé.
            const m = invoquerSurAdversaire(deps, a.adversaire,
                                            "GetPublicProfileMachineOfWarLineup");
            if (estRefus(m)) return m;
            if (!m.isNull()) gcRoot.add(m);
            return m;
        }
        case "json": {
            if (!kParam) return refus("classe du paramètre illisible -- JSON non liable");
            if (!isDeserializerReady()) return refus("JsonConvert.DeserializeObject non résolu");
            try { return deserializeFromJson(JSON.stringify(a.valeur), kParam); }
            catch (e) {
                return refus("désérialisation vers " + nomDeClasse(kParam) + " : "
                    + (e as Error).message);
            }
        }
    }
}

// --- dépendances vivantes --------------------------------------------------------------

interface Deps {
    exec: NativePointer; prog: NativePointer; gameConfig: NativePointer;
    logger: NativePointer; featureUnlocker: NativePointer;
    /** ⚠ OPTIONNEL, et le tri-état est le point : `null` = PAS LU, jamais « absent donc on
     *  s'en passe ». Le ctor de la source ne le demande PAS -- seul le genre `adversaire`
     *  en a besoin (2ᵉ argument de `GetPublicProfileLineup`). L'exiger dans la boucle
     *  ci-dessous ferait refuser les NEUF autres modes pour une dépendance qu'ils n'utilisent
     *  pas. Le refus est donc porté AU SITE qui le consomme, où il peut se nommer. */
    itemProg: NativePointer | null;
}

// --- LE POSTFIX D'IDS ADVERSES ----------------------------------------------------------
//
// CE QUE ÇA RÉPARE. Sans lui, une unité alignée par LES DEUX camps n'a qu'UNE entrée de
// catalogue, remplie par NOS statistiques : `b__0` termine par `cfg.Id = enemyTypeId`, donc les
// deux côtés écrivent la même ligne. Mesuré le 2026-08-22 (A/B contrôlé, proposition 2) --
// l'`ultraInceptorSgt` d'un joueur de niveau 13 sortait à 396 257 de puissance au lieu de 221.
// Facteur 1 800, EN SA FAVEUR, et en silence.
//
// ⚠ CE N'EST PAS UNE INVENTION — C'EST CE QUE FAIT LE NATIF, et les deux moitiés sont lues :
//
//     PvpGameModeSource$$LoadBattleInternal     passe `PVP_UNIT_POST_FIX` en 14ᵉ argument
//     PvpGameModeSource$$GetUnitModel           fait `String.Replace(unitId, <postfix>, "")`
//                                               avant de résoudre sur la progression adverse
//
// Le chemin sandbox, lui, passe un `0` LITTÉRAL compilé dans `GetHotseatSyncPvpConfig` : il n'y
// a ni argument de ctor ni champ de config à poser, d'où l'ancrage.
//
// ⚠ ON REPREND LA CHAÎNE DU JEU (`PvpGameModeSource.PVP_UNIT_POST_FIX`), pas une inventée : si
// un autre étage la retire lui aussi, une valeur à nous passerait au travers.

let postfixListeners: InvocationListener[] = [];
let postfixPose = 0;          // fois où le 14ᵉ argument a été écrit
let postfixRetire = 0;        // fois où le résolveur l'a vu et retiré
let postfixValeur: string | null = null;
/** Les chaînes managées qu'on fabrique doivent survivre à l'appel — bornées, sinon fuite. */
const postfixChaines: NativePointer[] = [];
function chaineManageeEnracinee(v: string): NativePointer {
    const p = createManagedString(v);
    gcRoot.add(p);
    postfixChaines.push(p);
    if (postfixChaines.length > 256) postfixChaines.shift();
    return p;
}

/** L'état d'initialisation de `PvpGameModeSource` au dernier appel -- PUBLIÉ, jamais supposé. */
let postfixInit: ClassInitState | null = null;

/** `PvpGameModeSource.PVP_UNIT_POST_FIX`, LU sur le jeu.
 *
 *  ⚠ IL FAUT FORCER L'INITIALISATION DE LA CLASSE, et ce n'est pas une liberté : IL2CPP ne
 *  remplit le bloc de statiques qu'à l'initialisation, et `PvpGameModeSource` n'est instanciée
 *  qu'en entrant dans un VRAI duel — donc froide dans toute session qui n'en a pas joué. Lue à
 *  froid, elle rend `null`, et c'est exactement ce qui est arrivé au premier essai (session 17).
 *
 *  **Le natif fait littéralement ce forçage au même endroit** : `GetUnitModel` porte
 *  `if (*(klass + 0xe4) == 0) il2cpp_runtime_class_init(klass);` juste avant de lire ce
 *  statique. On mirroite, on n'invente pas.
 *
 *  ⚠ L'ÉTAT SE LIT AVANT, et il est publié : une classe déjà chaude mesure le jeu, une classe
 *  qu'on vient de forcer mesure un état qu'on a créé soi-même. Le foyer `classInitState` tient
 *  cet ordre — c'est pour ça qu'on passe par lui plutôt que par `runtime_class_init` en direct. */
function postfixDuJeu(): string | Refus {
    const k = findClassAnywhere(NS_SRC, "PvpGameModeSource");
    if (!k) return refus("classe `PvpGameModeSource` introuvable -- chemin PÉRIMÉ");
    postfixInit = classInitState(LIVE_CLASS_INIT_PROBE, k, true);
    const p = readStaticObjectField(k, "PVP_UNIT_POST_FIX");
    if (p === null) {
        return refus("`PvpGameModeSource.PVP_UNIT_POST_FIX` NON LU (classe initialisée avant="
            + postfixInit.initializedBefore + ", forcée=" + postfixInit.forcedInit
            + ", après=" + postfixInit.initialized
            + (postfixInit.forceInitError ? ", " + postfixInit.forceInitError : "")
            + "). On ne rabat PAS sur une valeur par défaut : une chaîne inventée s'appliquerait "
            + "sans rien casser et fabriquerait un montage faux.");
    }
    const v = readIl2cppString(p);
    if (v === null || v === "") {
        return refus("`PVP_UNIT_POST_FIX` lu mais VIDE -- un postfix vide ne sépare rien");
    }
    return v;
}

/** Le résolveur du chemin sandbox, trouvé par sa partie STABLE.
 *
 *  ⚠ Sa classe est `<>c__DisplayClass37_0`, et le `37` est un index attribué par le COMPILATEUR :
 *  il bouge dès qu'une méthode est ajoutée à `BattleConfigBuilder`, SANS que rien ne le signale.
 *  On énumère donc les types imbriqués et on retient celui qui PORTE une méthode nommée
 *  `<GetHotseatSyncPvpConfig>g__GetEnemy|0` -- le nom de la méthode englobante, lui, est stable. */
function methodeResolveurSandbox(): { info: NativePointer; ptr: NativePointer } | Refus {
    const kB = findClassAnywhere(NS_VIEW, "BattleConfigBuilder");
    if (!kB) return refus("classe `" + NS_VIEW + ".BattleConfigBuilder` introuvable");
    const it = Memory.alloc(Process.pointerSize);
    it.writePointer(ptr(0));
    let n: NativePointer;
    const vus: string[] = [];
    while (!(n = class_get_nested_types(kB, it) as NativePointer).isNull()) {
        const nom = nomDeClasse(n) ?? "?";
        if (!nom.startsWith("<>c__DisplayClass")) continue;
        vus.push(nom);
        const mit = Memory.alloc(Process.pointerSize);
        mit.writePointer(ptr(0));
        let m: NativePointer;
        while (!(m = class_get_methods(n, mit) as NativePointer).isNull()) {
            const mn = s(method_get_name(m) as NativePointer);
            if (mn.includes("GetHotseatSyncPvpConfig") && mn.includes("g__GetEnemy")) {
                return { info: m, ptr: methodEntry(m) };
            }
        }
    }
    return refus("résolveur `<GetHotseatSyncPvpConfig>g__GetEnemy` INTROUVABLE parmi les "
        + vus.length + " display class de `BattleConfigBuilder` -- chemin PÉRIMÉ. Ne PAS se "
        + "replier sur un nom indexé (`<>c__DisplayClass37_0`) : l'index est attribué par le "
        + "compilateur et change sans bruit.");
}

/** L'état COURANT des deux ancrages — à relire APRÈS `LoadBattle`.
 *
 *  ⚠ POURQUOI CETTE FONCTION EXISTE. `armerPostfix` rend ses compteurs à l'ARMEMENT, donc à
 *  zéro : les deux ancrages ne tirent que pendant `LoadBattle`, qui vient plus tard. Publier
 *  l'objet d'armement dans la réponse affichait `pose=0 retire=0` sur un montage pourtant
 *  RÉUSSI -- un faux négatif qui aurait fait chercher une panne inexistante. Mesuré, corrigé. */
function etatPostfix(): Record<string, unknown> {
    return { arme: postfixListeners.length > 0, postfix: postfixValeur,
             pose: postfixPose, retire: postfixRetire, classeInit: postfixInit };
}

/** Arme (ou désarme) les DEUX ancrages. Ils vont ENSEMBLE : poser le postfix sans adapter le
 *  résolveur le fait LEVER -- il apparie par égalité exacte et finit sur `Enumerable.First`,
 *  qui n'a pas de variante `OrDefault`. */
function armerPostfix(actif: boolean): Record<string, unknown> | Refus {
    if (!actif) {
        for (const l of postfixListeners) { try { l.detach(); } catch { /* best effort */ } }
        postfixListeners = [];
        postfixValeur = null;
        return { ok: true, arme: false };
    }
    if (postfixListeners.length) {
        return { ok: true, arme: true, postfix: postfixValeur, deja: true,
                 pose: postfixPose, retire: postfixRetire };
    }
    const pf = postfixDuJeu();
    if (estRefus(pf)) return pf;
    const kB = findClassAnywhere(NS_VIEW, "BattleConfigBuilder");
    if (!kB) return refus("classe `BattleConfigBuilder` introuvable");
    const mBuild = findMethodByParamCount(kB, "GetPvpLevelConfig", 14);
    if (!mBuild) {
        return refus("`BattleConfigBuilder$$GetPvpLevelConfig` à 14 paramètres INTROUVABLE -- "
            + "chemin PÉRIMÉ (le 14ᵉ est `opponentUnitIdPostFix`)");
    }
    const mRes = methodeResolveurSandbox();
    if (estRefus(mRes)) return mRes;

    postfixValeur = pf;
    const chainePostfix = chaineManageeEnracinee(pf);

    // CRAN 1 -- poser le 14ᵉ argument.
    postfixListeners.push(Interceptor.attach(mBuild.ptr, {
        onEnter(args) {
            // ⛔ ON N'ÉCRIT QUE SUR UN NUL, et c'est la garde qui compte : le duel RÉEL passe
            // DÉJÀ son postfix (`PvpGameModeSource$$LoadBattleInternal`). L'écraser toucherait
            // une partie qui n'a rien demandé -- le vice exact du relais laissé armé qui a
            // coûté un jeton de boss de guilde le 2026-08-20.
            try {
                if (!args[14].isNull()) return;
                args[14] = chainePostfix;
                postfixPose++;
            } catch { /* un argument illisible fait RENONCER, jamais forcer */ }
        },
    }));

    // CRAN 2 -- le retirer à la résolution, COMME LE NATIF.
    postfixListeners.push(Interceptor.attach(mRes.ptr, {
        onEnter(args) {
            // args[0] = display class, args[1] = unitId, args[2] = isExtraEnemyUnit.
            try {
                const id = readIl2cppString(args[1]);
                if (id === null || postfixValeur === null) return;
                if (!id.includes(postfixValeur)) return;
                // `String.Replace` remplace TOUTES les occurrences -- on mirroite, y compris
                // son risque (un id qui contiendrait le motif serait mutilé chez le natif aussi).
                args[1] = chaineManageeEnracinee(id.split(postfixValeur).join(""));
                postfixRetire++;
            } catch { /* idem : renoncer */ }
        },
    }));

    return { ok: true, arme: true, postfix: pf,
             // L'état d'init est PUBLIÉ : « classe déjà chaude » et « classe que nous avons
             // forcée » ne sont pas la même mesure, et le lecteur doit pouvoir les séparer.
             classeInit: postfixInit,
             methodes: ["Idun.Source.IdunBattle.View.BattleConfigBuilder$$GetPvpLevelConfig",
                        "BattleConfigBuilder.<>c__DisplayClass*"
                            + "$$<GetHotseatSyncPvpConfig>g__GetEnemy|0"],
             note: "les deux ancrages vont ENSEMBLE. Le cran 1 n'écrit QUE sur un argument nul, "
                 + "donc un duel d'Arène RÉEL (qui passe déjà le sien) n'est pas touché." };
}

/** GREFFER L'ENVIRONNEMENT DU MODE sur une config sandbox déjà construite.
 *
 *  ⚠ CE N'EST PAS UN ARGUMENT DE CTOR — d'où une étape SÉPARÉE, après la construction.
 *  `SandboxPvpBattleConfig..ctor` ne pose que `BoardId` (+0x28) → `BossUnit` (+0x58) ;
 *  `EnvironmentAbilities` est une auto-propriété (+0x18) qu'il laisse NULLE. C'est exactement
 *  pour ça qu'un banc d'Arène se jouait sans limite de tour.
 *
 *  ⚠ « CONFIGURÉ » N'EST PAS « INSTALLÉ », et c'est le piège mesuré le 2026-08-22 : un grep de
 *  la BC trouve `EnvEndBombardment` TROIS fois (sa config d'ability dans
 *  `Abilities.EnvironmentAbilities`, son poids IA dans `Utilities.Default`) alors que la liste
 *  des installées est VIDE. Seul le compte des membres tranche — d'où le `resume` publié.
 *
 *  ⚠ ET LES CONSTANTES DU CATALOGUE NE SONT PAS CELLES DU MODE. La BC porte
 *  `nrOfRounds: 6` / `healthPct: 30` ; l'Arène tourne à **8 / 20**. Recopier le catalogue
 *  monterait une pression de fin FAUSSE, en silence. Les valeurs PAR MODE viennent de
 *  `PvpProgression$$GetEnvironmentAbilitiesConfig()`, et c'est elle qu'on demande. */
function grefferEnvironnement(cfg: NativePointer): Record<string, unknown> | Refus {
    const prog = pvpOpponents.progressionPvp();
    if (estRefus(prog)) return prog;
    const kProg = classeDeLObjet(prog as NativePointer);
    if (!kProg) return refus("classe de la `PvpProgression` illisible");

    const mCfg = findMethodByParamCount(kProg, "GetEnvironmentAbilitiesConfig", 0);
    if (!mCfg) {
        return refus("`" + (nomDeClasse(kProg) ?? "?") + "$$GetEnvironmentAbilitiesConfig()` "
            + "INTROUVABLE -- chemin PÉRIMÉ. Ne PAS se replier sur les constantes du catalogue "
            + "de la BC : elles valent 6/30, l'Arène tourne à 8/20.");
    }
    let extra: NativePointer;
    try { extra = invokeMethod(mCfg.info, prog as NativePointer, null); }
    catch (e) { return refus("`GetEnvironmentAbilitiesConfig` a levé : " + (e as Error).message); }
    if (extra.isNull()) {
        // Le décompilé passe par `GetCurrentSeason` : hors saison, il n'y a rien à greffer.
        // C'est un ÉTAT du compte, pas une panne — mais on ne le rend pas comme un succès.
        return refus("`GetEnvironmentAbilitiesConfig` a rendu NULL -- pas de saison PvP courante "
            + "(le natif passe par `GetCurrentSeason`). Rien à greffer, et ce n'est pas un "
            + "environnement vide : c'est un environnement NON MESURÉ.");
    }
    gcRoot.add(extra);

    const env = envAbilities.creerReceptacle();
    if (estRefus(env)) return env;
    const fus = envAbilities.fusionnerDepuisConfig(env as NativePointer, extra);
    if (estRefus(fus)) return fus;

    // La POSE sur la config : par le setter si le build l'expose, sinon par le champ de
    // backing -- et on DIT lequel, parce que les deux n'ont pas la même garantie.
    const kCfg = classeDeLObjet(cfg);
    if (!kCfg) return refus("classe de la config sandbox illisible");
    let voie: string;
    const setter = findMethodByParamCount(kCfg, "set_EnvironmentAbilities", 1);
    if (setter) {
        try { invokeMethod(setter.info, cfg, [env as NativePointer]); }
        catch (e) { return refus("`set_EnvironmentAbilities` a levé : " + (e as Error).message); }
        voie = "set_EnvironmentAbilities";
    } else {
        const off = getFieldOffset(kCfg, "<EnvironmentAbilities>k__BackingField");
        if (off < 0) {
            return refus("ni `set_EnvironmentAbilities` ni le champ de backing "
                + "`<EnvironmentAbilities>k__BackingField` sur `" + (nomDeClasse(kCfg) ?? "?")
                + "` -- chemin PÉRIMÉ");
        }
        cfg.add(off).writePointer(env as NativePointer);
        voie = "<EnvironmentAbilities>k__BackingField (+0x" + off.toString(16) + ")";
    }

    // Ce qui est RÉELLEMENT installé -- une mesure, pas la confiance dans l'appel.
    return { pose: true, voie, installe: envAbilities.resume(env as NativePointer) };
}

/** Les cinq dépendances du ctor, lues PAR NOM sur l'exécuteur vivant.
 *
 *  ⚠ Par nom, jamais par offset : un offset lu au mauvais endroit ne se signale pas, il rend
 *  un pointeur plausible. Les quatre champs sont mesurés présents sur ce build
 *  (`_unitProgression`, `_gameConfigData`, `_logger`, `_featureUnlocker`) ; leur ABSENCE est
 *  un refus nommé, pas un repli. */
function dependances(): Deps | Refus {
    const ex = executeurVivant();
    if (estRefus(ex)) return ex;
    const kExec = findClassAnywhere("idun.shared.commands", "ViewCommandExecutor");
    if (!kExec) return refus("classe `ViewCommandExecutor` introuvable");

    const lu: Record<string, NativePointer> = {};
    const manquants: string[] = [];
    const nuls: string[] = [];
    for (const nom of ["_unitProgression", "_gameConfigData", "_logger", "_featureUnlocker"]) {
        const off = getFieldOffset(kExec, nom);
        if (off < 0) { manquants.push(nom); continue; }
        const p = ex.add(off).readPointer();
        if (p.isNull()) { nuls.push(nom); continue; }
        lu[nom] = p;
    }
    if (manquants.length) {
        return refus("champ(s) absent(s) de `ViewCommandExecutor` sur ce build : "
            + manquants.join(", ") + " -- chemin PÉRIMÉ, pas de repli sur un offset");
    }
    if (nuls.length) {
        return refus("dépendance(s) NULLE(s) sur l'exécuteur : " + nuls.join(", ")
            + " -- l'exécuteur existe mais n'a pas reçu ses dépendances (jeu pas assez avancé)");
    }

    // Le ctor veut un `GameConfigDto`, l'exécuteur porte un `IGameConfigData`. L'accesseur
    // est ABSENT de `methods.tsv` -- ce qui ne prouve rien : IL2CPP déduplique les corps
    // triviaux, et `class_get_methods` le voit, lui.
    const kGcd = classeDeLObjet(lu["_gameConfigData"]);
    if (!kGcd) return refus("classe de `_gameConfigData` illisible");
    let mi = findMethodByParamCount(kGcd, "get_gameConfigDto", 0);
    if (!mi) mi = findMethodByParamCount(kGcd, "get_GameConfigDto", 0);
    if (!mi) {
        return refus("aucun accesseur sans paramètre `get_gameConfigDto` / `get_GameConfigDto` "
            + "sur `" + (nomDeClasse(kGcd) ?? "?") + "` -- le `GameConfigDto` du ctor est "
            + "inatteignable par cette voie");
    }
    let dto: NativePointer;
    try { dto = invokeMethod(mi.info, lu["_gameConfigData"], null); }
    catch (e) { return refus("get_gameConfigDto a levé : " + (e as Error).message); }
    if (dto.isNull()) return refus("get_gameConfigDto a rendu NULL");

    // `_itemProgression` est lu SÉPARÉMENT et sans refus : cf. le tri-état sur `Deps.itemProg`.
    // Mesuré le 2026-08-22 (`classFields`) : `IItemProgression` à +0x3c8, juste après
    // `_unitProgression`. Un `null` ici veut dire « champ absent ou non renseigné », et c'est
    // le genre `adversaire` qui le dira, pas cette fonction.
    let itemProg: NativePointer | null = null;
    const offItem = getFieldOffset(kExec, "_itemProgression");
    if (offItem >= 0) {
        const p = ex.add(offItem).readPointer();
        if (!p.isNull()) itemProg = p;
    }

    return {
        exec: ex, prog: lu["_unitProgression"], gameConfig: dto,
        logger: lu["_logger"], featureUnlocker: lu["_featureUnlocker"], itemProg,
    };
}

// --- construction ----------------------------------------------------------------------

/** Épingle tout ce qu'on construit : entre la construction et l'appel, un objet managé non
 *  enraciné peut être déplacé ou collecté. C'est la course déjà rencontrée sur `initRunner`,
 *  dont le symptôme est une bataille montée à moitié. */
const epingles: NativePointer[] = [];
function epingler(p: NativePointer): NativePointer {
    try { gcRoot.add(p); epingles.push(p); } catch { /* best effort */ }
    return p;
}

/** L'override de BC : la `BattleConfiguration` que `LoadBattle` rendra à la place de la
 *  sienne. `null` = transparent. Épinglée, sinon le GC la ramasse entre l'armement et le
 *  montage — le symptôme serait une bataille montée à moitié. */
let bcOverride: NativePointer | null = null;
let overrideListener: InvocationListener | null = null;
let overrideFires = 0;

function classeDuMode(mode?: string, classe?: string): NativePointer | Refus {
    const nom = classe ?? (mode ? MODES[mode] : undefined);
    if (!nom) {
        return refus("`mode` inconnu : " + JSON.stringify(mode ?? null) + ". Connus : "
            + Object.keys(MODES).join(", ") + ". Ou passer `classe` explicitement.");
    }
    const k = findClassAnywhere(NS_CFG, nom);
    if (!k) return refus("classe `" + NS_CFG + "." + nom + "` introuvable sur ce build");
    return k;
}

interface Montage {
    config: NativePointer; source: NativePointer; deps: Deps;
    /** `null` = pas demandé. Sinon le compte-rendu de la greffe, MESURÉ. */
    environnement: Record<string, unknown> | null;
    /** TOUJOURS renseigné -- le postfix est arme sans condition. */
    postfix: Record<string, unknown>;
}

function construire(
    mode: string | undefined, classe: string | undefined, args: Arg[],
    environnement?: string | null,
): Montage | Refus {
    const kCfg = classeDuMode(mode, classe);
    if (estRefus(kCfg)) return kCfg;

    const ctorCfg = findMethodByParamCount(kCfg, ".ctor", args.length);
    if (!ctorCfg) {
        // ⚠ Le nombre attendu est LISIBLE : on le dit, plutôt que de laisser l'appelant
        // deviner. Un « ctor introuvable » nu enverrait chercher un problème de build.
        const arites: number[] = [];
        for (let n = 0; n <= 20; n++) {
            if (findMethodByParamCount(kCfg, ".ctor", n)) arites.push(n);
        }
        return refus("`" + (nomDeClasse(kCfg) ?? "?") + "..ctor` à " + args.length
            + " paramètre(s) INTROUVABLE. Arité(s) réellement portée(s) : "
            + (arites.length ? arites.join(", ") : "aucune") + ".");
    }

    // --- LE POSTFIX, ARMÉ SANS CONDITION ----------------------------------------------
    //
    // ⛔ PAS D'OPTION, ET C'EST LE POINT. Un drapeau qu'on oublie de passer rend un banc qui
    // MENT -- l'unité alignée des deux côtés sort avec NOS statistiques, sans erreur, sans
    // trace. Le duel réel pose ce postfix systématiquement ; on fait pareil.
    //
    // ⚠ AVANT le ctor, et pas après : le cran 1 ancre `GetPvpLevelConfig`, que `LoadBattle`
    // appellera plus tard. Armé trop tard, il ne tirerait pas -- et son absence ne se verrait
    // que par des statistiques adverses fausses, c'est-à-dire pas du tout.
    //
    // ⚠ L'ÉCHEC N'EST FATAL QUE POUR LE PVP. Les deux ancrages ne peuvent tirer que sur le
    // chemin PvP (`GetPvpLevelConfig` et le résolveur de `GetHotseatSyncPvpConfig`) : bloquer
    // un montage `waves` parce que `PVP_UNIT_POST_FIX` n'est pas lisible serait une panne
    // fabriquée. On PUBLIE le refus dans les deux cas -- il n'est jamais tu.
    const estPvp = nomDeClasse(kCfg) === MODES.pvp;
    let postfixRapport: Record<string, unknown> = armerPostfix(true) as Record<string, unknown>;
    if (estRefus(postfixRapport)) {
        if (estPvp) {
            return refus("postfix NON ARMÉ, et c'est un montage PvP -- une unité alignée par "
                + "les deux camps sortirait avec NOS statistiques, en silence. "
                + (postfixRapport as unknown as Refus).error);
        }
        postfixRapport = { arme: false, sansEffetIci: true,
                           raison: (postfixRapport as unknown as Refus).error };
    }

    const deps = dependances();
    if (estRefus(deps)) return deps;

    // Liaison argument par argument, contre la classe RÉELLE du paramètre.
    const lies: NativePointer[] = [];
    for (let i = 0; i < args.length; i++) {
        const kParam = methodParamClass(ctorCfg.info, i);
        const v = lier(kParam, args[i], deps);
        if (estRefus(v)) {
            return refus("paramètre " + i + " (attendu : " + (nomDeClasse(kParam) ?? "?")
                + ") -- " + v.error);
        }
        lies.push(v);
    }

    let cfg: NativePointer;
    try {
        cfg = il2cpp_object_new(kCfg) as NativePointer;
        if (cfg.isNull()) return refus("il2cpp_object_new(config) -> NULL");
        epingler(cfg);
        invokeMethod(ctorCfg.info, cfg, lies);
    } catch (e) {
        return refus("ctor de " + nomDeClasse(kCfg) + " a levé : " + (e as Error).message);
    }

    // --- LA GREFFE D'ENVIRONNEMENT, APRÈS le ctor et AVANT la source ---------------------
    //
    // ⚠ Le refus est DUR, pas un avertissement. Un banc d'Arène qu'on croit sous pression de
    // fin et qui n'y est pas se joue tout entier sur une prémisse fausse -- exactement ce que
    // le montage du 2026-08-22 a fait, sans que rien ne le dise.
    let envRapport: Record<string, unknown> | null = null;
    if (environnement != null && environnement !== "") {
        if (environnement !== "arene") {
            return refus("`environnement` inconnu : " + JSON.stringify(environnement)
                + ". Porté : `arene` (la config de la saison PvP courante). Les autres modes "
                + "ont leur propre getter et ne sont PAS interchangeables : les constantes "
                + "sont PAR MODE.");
        }
        const g = grefferEnvironnement(cfg);
        if (estRefus(g)) return refus("greffe de l'environnement : " + g.error);
        envRapport = g;
    }

    const kSrc = findClassAnywhere(NS_SRC, "SandboxGameModeSource");
    if (!kSrc) return refus("classe `SandboxGameModeSource` introuvable sur ce build");
    const ctorSrc = findMethodByParamCount(kSrc, ".ctor", 5);
    if (!ctorSrc) {
        return refus("`SandboxGameModeSource..ctor` à 5 paramètres INTROUVABLE -- la "
            + "signature attendue est (ISandboxBattleConfig, IUnitProgression, GameConfigDto, "
            + "IIdunLogger, IFeatureUnlocker)");
    }
    let src: NativePointer;
    try {
        src = il2cpp_object_new(kSrc) as NativePointer;
        if (src.isNull()) return refus("il2cpp_object_new(source) -> NULL");
        epingler(src);
        invokeMethod(ctorSrc.info, src,
                     [cfg, deps.prog, deps.gameConfig, deps.logger, deps.featureUnlocker]);
    } catch (e) {
        return refus("SandboxGameModeSource..ctor a levé : " + (e as Error).message);
    }
    return { config: cfg, source: src, deps,
             environnement: envRapport, postfix: postfixRapport };
}

/** Relit les champs de la source APRÈS construction. Le ctor n'en renseigne que 5 sur 9 —
 *  publier ce qui reste nul est la seule façon que ça se VOIE, plutôt que de le supposer. */
function champsDeLaSource(src: NativePointer): Record<string, string | null> {
    const k = findClassAnywhere(NS_SRC, "SandboxGameModeSource");
    const out: Record<string, string | null> = {};
    if (!k) return out;
    for (const nom of ["_currentBattle", "sandboxConfig", "_unitProgression", "_gameConfig",
                       "_logger", "_gameViews", "_featureUnlocker", "_stateMachineActions"]) {
        const off = getFieldOffset(k, nom);
        out[nom] = off < 0 ? null : src.add(off).readPointer().toString();
    }
    return out;
}

// --- le SEED, pour rendre une bataille REJOUABLE ----------------------------------------
//
// CHAINE MESURÉE (décompilé) :
//
//     idun.IdunMainView$$ShowBattle
//         seed = 0
//         cs = gameModeSource.CustomSeed                 // Nullable<Int32>, slot 6 de
//                                                        // IGameModeSource
//         si cs.HasValue        -> seed = cs.Value       // SyncPvp est le SEUL à l'imposer
//         sinon si !BC.DisableRandomness (+0xe7)
//                               -> seed = (Int32)DateTime.Now.Ticks
//         IdunBattle.Runner.IdunRunner$$Initialize(runner, BC, seed, ...)
//             -> new IdunBattle.Utils.PRNG.MersenneTwister(seed)
//
// ⇒ hors PvP synchrone, le seed d'une bataille est L'HORLOGE. Rien n'est rejouable.
//
// POURQUOI ON N'ANCRE PAS `get_CustomSeed`, QUI SERAIT L'ENDROIT « LOGIQUE »
// --------------------------------------------------------------------------
// Il n'a QU'UNE implémentation dans la table, sur `SyncPvpGameModeSource` — ce qui ne veut PAS
// dire que les autres sources n'en ont pas : le `return null` de la base est un corps TRIVIAL,
// et IL2CPP déduplique ces corps-là. S'attacher dessus ferait donc feu sur tous les getters
// qui partagent le même `return null`, c'est-à-dire potentiellement des centaines, sur des
// chemins chauds. C'est le contraire de ce qu'on veut.
//
// On ancre le CONSOMMATEUR, qui est un corps bien à lui et tire UNE FOIS PAR BATAILLE.
//
// ⚠ LES DEUX SURCHARGES D'`Initialize` ONT LA MÊME ARITÉ (6). L'une prend un `IPseudoRNG`
// déjà construit, l'autre l'`Int32` qui nous intéresse — `findMethodByParamCount` rendrait
// donc l'une OU l'autre, sans le dire. On désambiguïse par la CLASSE du paramètre 1.
// ⚠ LE PARAGRAPHE CI-DESSUS EST UN RE — DONC IL SE CONFRONTE, IL NE SE CITE PAS.
// « le seed est l'horloge » et « rien n'est rejouable » sont des conclusions LUES au décompilé.
// Elles peuvent avoir été justes et ne plus l'être (un build change), ou avoir toujours porté
// sur une autre source que celle qu'on monte.
//
// ⚠ LE MODE OBSERVATION QUI LES RENDAIT VÉRIFIABLES A ÉTÉ RETIRÉ le 2026-08-22 (cf. le bloc
// `seedJournal` plus bas). Re-confronter demande donc de le réécrire — une dizaine de lignes :
// journaliser `args[2]` sans le remplacer, sur deux montages consécutifs.
//
// ✅ CONFRONTÉ LE 2026-08-19 SUR `t6dpr4k06g`, ET LE RE EST JUSTE — deux voies indépendantes,
// sur deux montages guild war consécutifs (mode observation, aucune écriture) :
//     seed 1 = 0xd322c8a0   seed 2 = 0xeb76f760
//     seed2 - seed1                 = 408 170 176 ticks = 40,8 s  (l'écart RÉEL entre les deux)
//     (Int32)DateTime.Now.Ticks - seed2 = 753 546 443 ticks = 75,4 s  (le temps depuis, réel)
// À 10^7 ticks/s les deux collent : le seed EST l'horloge locale tronquée en Int32.
//
// CE QUE ÇA TRANCHE, ET QUI N'EST PAS ÉVIDENT : le seed est LOCAL — aucun contact serveur, ni
// en sandbox ni en bataille réelle. Il est donc IMPRÉVISIBLE (résolution 100 ns) mais
// IMPOSABLE, et l'ancrage porte sur `IdunRunner$$Initialize`, consommateur commun à TOUTES les
// batailles. La limite au rejeu n'est donc pas le seed : c'est que le PRNG se consomme dans
// l'ORDRE DES ÉVÉNEMENTS — même seed + une action différente, et tout diverge à partir de là.
let seedImpose: number | null = null;
let seedUnCoup = true;
let seedListener: InvocationListener | null = null;
// ⛔ IL Y AVAIT ICI UN `seedJournal` -- RETIRÉ LE 2026-08-22, NE PAS LE REMETTRE.
//
// Il gardait ce qui avait été remplacé, par quoi, et sous quel mode, pour qu'un lecteur Python
// puisse attester après coup que le seed avait bien mordu. C'était un tableau À NOUS, borné à 32
// en interne et rendu TRONQUÉ à ses 8 dernières entrées.
//
// Son unique lecteur, le cran 11 des chaînes de rejeu, prenait la LONGUEUR de cette vue pour un
// compteur : passé la 8ᵉ bataille d'une session elle saturait, et le cran refusait
// « `Initialize` n'a RIEN journalisé » sur des batailles qui avaient parfaitement monté. Quatre
// sessions de farming ont buté à 8, 8, 7, 8 — la taille de notre propre fenêtre, prise pour un
// plafond du JEU, qu'un redémarrage « réparait » parce qu'il la vidait.
//
// Le cran a été supprimé plutôt que réparé : il n'arbitrait rien, la morsure du seed se
// constatant de toute façon en aval quand chaque coup est confronté à la référence. Le journal
// n'ayant plus aucun lecteur, il part avec lui — ainsi que le mode OBSERVATION, dont il était le
// seul débouché (observer sans journaliser ne rend rien).
//
// ⚠ CE QUI EST PERDU, ET QUI EST ASSUMÉ : la capacité de LIRE le seed du jeu sans le remplacer.
// Elle a servi une fois, le 2026-08-19, pour établir que le seed est l'horloge locale tronquée
// en Int32 — RE confronté et écrit plus haut dans ce fichier. Si elle redevient nécessaire, elle
// se réécrit en une dizaine de lignes ; la garder armée « au cas où » est ce qui a produit le
// piège ci-dessus.

function methodeInitializeSeed(): { info: NativePointer; ptr: NativePointer } | Refus {
    const k = findClassAnywhere("IdunBattle.Runner", "IdunRunner");
    if (!k) return refus("classe `IdunBattle.Runner.IdunRunner` introuvable sur ce build");
    const mr = findMethodByParamClasses(k, "Initialize",
                                        ["BattleConfiguration", "Int32", null, null, null, null]);
    if (!mr) {
        return refus("`IdunRunner$$Initialize` à 6 paramètres dont un `Int32` en position 1 "
            + "INTROUVABLE -- ne PAS se replier sur l'arité seule : l'autre surcharge prend un "
            + "`IPseudoRNG` et l'ancrer n'imposerait aucun seed, en silence");
    }
    return mr;
}

/** Arme (ou désarme) l'imposition du seed. `null` = désarmer.
 *
 *  ⚠ Ce n'est PAS un `replace` : on laisse le natif s'exécuter, on ne fait que réécrire
 *  l'argument 2 à l'entrée. Le journal garde ce qui a été remplacé, pour que « la bataille
 *  a bien pris mon seed » soit une MESURE et pas une croyance. */
/**
 * L'identité EXIGÉE de la bataille, ou `null` = pas de condition.
 *
 * ⚠ POURQUOI CETTE CONDITION EXISTE. Imposer un seed « à la prochaine bataille » ne sait pas
 * DE QUELLE bataille il s'agit : si le joueur entre dans une arène, une campagne ou un autre
 * boss, le seed de la référence lui est écrit dessus -- un effet réel sur une partie qui n'a
 * rien demandé. C'est le même vice que le relais laissé armé qui a coûté un jeton de boss de
 * guilde le 2026-08-20 : un déclenchement qui ne vérifie pas SUR QUOI il tire.
 *
 * `IdunRunner$$Initialize(configuration, rngSeed, ...)` reçoit la `BattleConfiguration` en
 * premier argument : elle porte son `Id` et son `GameMode`. Deux lectures de CHAMP, aucune
 * invocation -- donc sans danger dans le callback.
 */
let seedSiConfigId: string | null = null;

/** Lit `BattleConfiguration.Id`. `null` = PAS LU -- ce qui fait RENONCER à imposer. */
function idDeLaConfig(cfg: NativePointer): string | null {
    try {
        if (cfg.isNull()) return null;
        const k = cfg.readPointer();
        let off = getFieldOffset(k, "<Id>k__BackingField");
        if (off < 0) off = getFieldOffset(k, "Id");
        if (off < 0) return null;
        return readIl2cppString(cfg.add(off).readPointer());
    } catch { return null; }
}

// --- QUELLE BATAILLE EST MONTÉE, LÀ, MAINTENANT ------------------------------------------------
//
// CE QUE ÇA REMPLACE, ET POURQUOI L'ANCIEN ÉTAIT FRAGILE
// ------------------------------------------------------
// `bataille_reference.py` identifiait la bataille en cherchant l'`Id` du replay PARMI LES NOMS
// D'UNITÉS ADVERSES du plateau. Ça ne marchait que par coïncidence : dans la BC du replay
// Belisarius, `Id` et `BossUnit.UnitId` valent la MÊME chaîne. Rien ne le garantit ailleurs, et
// les PNJ de cette même BC portent un suffixe de rang (`...AdmecTechpriest:22`) -- si la vue du
// boss en porte un aussi, la comparaison échoue sur une bataille LÉGITIME. On refuserait alors
// un jeton déjà dépensé, pour un défaut d'outil.
//
// On lit donc l'`Id` LÀ OÙ IL EST : sur la `BattleConfiguration` que porte le runner vivant.
//
// ⛔ AUCUNE INVOCATION. Le champ se trouve par un balayage de MÉTADONNÉES (`class_get_fields` +
// `field_get_type`), puis se lit à son offset. Rien de managé ne s'exécute -- c'est ce qui rend
// l'appel sûr y compris depuis un callback.
//
// ⚠ TRI-ÉTAT PARTOUT : `null` = PAS LU. Ni « pas de bataille », ni un feu vert. C'est le travers
// qui a produit l'incident du 2026-08-20 (`duJoueur=0` lu comme « plateau vide »).

/** Ce qu'on a vu passer à `IdunRunner$$Initialize`, ÉPINGLÉ AU RUNNER qui l'a reçu.
 *
 *  ⚠ L'ÉPINGLAGE EST LE POINT : sans le pointeur du runner, une mémoire dirait « la dernière
 *  bataille créée », pas « la bataille montée ». Deux choses différentes dès qu'on est sorti
 *  d'une bataille pour en monter une autre. */
let bcMemorisee: { runner: string; id: string | null } | null = null;

/** L'offset du PREMIER champ de type `BattleConfiguration` sur `klass` ou l'un de ses parents.
 *  `-1` = pas trouvé. Jamais un `0` : un offset nul est un offset VALIDE. */
function offsetDuChampBc(klass: NativePointer): number {
    const iter = Memory.alloc(Process.pointerSize);
    for (let k = klass; !k.isNull(); k = class_get_parent(k) as NativePointer) {
        iter.writePointer(ptr(0));
        let f: NativePointer;
        while (!(f = class_get_fields(k, iter) as NativePointer).isNull()) {
            try {
                const t = field_get_type(f) as NativePointer;
                if (t.isNull()) continue;
                const kc = type_get_class_or_element_class(t) as NativePointer;
                if (kc.isNull()) continue;
                if (s(class_get_name(kc) as NativePointer) !== "BattleConfiguration") continue;
                return field_get_offset(f) as number;
            } catch { /* un champ illisible n'est pas une raison d'abandonner les suivants */ }
        }
    }
    return -1;
}

/** Le nom du champ trouvé — pour que le retour DISE d'où vient la lecture, pas seulement quoi. */
function nomDuChampBc(klass: NativePointer): string | null {
    const iter = Memory.alloc(Process.pointerSize);
    for (let k = klass; !k.isNull(); k = class_get_parent(k) as NativePointer) {
        iter.writePointer(ptr(0));
        let f: NativePointer;
        while (!(f = class_get_fields(k, iter) as NativePointer).isNull()) {
            try {
                const t = field_get_type(f) as NativePointer;
                if (t.isNull()) continue;
                const kc = type_get_class_or_element_class(t) as NativePointer;
                if (kc.isNull() || s(class_get_name(kc) as NativePointer) !== "BattleConfiguration") {
                    continue;
                }
                return s(class_get_name(k) as NativePointer) + "."
                    + s(field_get_name(f) as NativePointer);
            } catch { /* idem */ }
        }
    }
    return null;
}

interface IdentiteBataille {
    ok: true; lecture: true;
    /** L'`Id` de la BC MONTÉE. `null` = PAS LU -- lire `diagnostic`. */
    id: string | null;
    champ: string | null;
    runner: string | null;
    /** La lecture faite à la création, et si elle porte sur CE runner-ci. */
    memorise: { id: string | null; runner: string; concorde: boolean } | null;
    /** L'état de la pompe. `concorde: false` = son verrou `liveRunner` est PÉRIMÉ ;
     *  `framesDepuisLaVue > 0` = elle ne draine plus la vue de bataille. */
    pompe: { runner: string | null; concorde: boolean | null;
             vue: string | null; frame: number; framesDepuisLaVue: number | null };
    diagnostic: string;
}

// ⛔ ON NE SE FIE PAS À `state.liveRunner`, ET C'EST MESURÉ (2026-08-20).
//
// La pompe ne remet `liveRunner` à nul qu'en VOYANT la transition `_runner -> null` dans
// `IdunGameViews$$Update`. Après une retraite, cette vue est détruite : son `Update` ne tire
// plus, la transition n'est jamais vue, et le verrou GARDE le dernier runner. Mesuré : à +12 s
// d'une retraite confirmée (`sandboxProbe.instance == null`), `state.liveRunner` pointait encore
// sur `0x23ff324c500` et la première version de ce lecteur affirmait « `GuildBoss10Boss1...` ».
// C'est LA faute que ce module existe pour empêcher -- affirmer une bataille qui n'est plus là.
//
// (Le RPC répondait quand même parce que la pompe UI, armée par le montage, draine dans
// `EventSystem$$Update` : le harnais vivait, la vue de bataille non.)
//
// On repart donc de la SCÈNE : l'instance vivante d'`IdunGameViews`, puis son `_runner`. La
// valeur de la pompe reste publiée comme RECOUPEMENT -- un désaccord nomme son verrou périmé.
function identiteDeLaBatailleVivante(): IdentiteBataille {
    const cache = state.liveRunner;
    const etatPompe = (concorde: boolean | null) => ({
        runner: cache === null ? null : cache.toString(), concorde,
        vue: state.gameViews === null ? null : state.gameViews.toString(),
        frame: state.frameNo,
        framesDepuisLaVue: state.gameViews === null ? null
            : state.frameNo - state.gameViewsFrame,
    });
    const sansRunner = (diagnostic: string): IdentiteBataille => ({
        ok: true, lecture: true, id: null, champ: null, runner: null,
        memorise: bcMemorisee === null ? null
            : { id: bcMemorisee.id, runner: bcMemorisee.runner, concorde: false },
        pompe: etatPompe(null),
        diagnostic,
    });

    const kGv = findClassAnywhere("IdunBattle.View.Game", "IdunGameViews");
    if (!kGv) return sansRunner("classe `IdunBattle.View.Game.IdunGameViews` INTROUVABLE sur ce "
        + "build -- NON MESURÉ.");
    const offRunner = getFieldOffset(kGv, "_runner");
    if (offRunner < 0) return sansRunner("champ `IdunGameViews._runner` INTROUVABLE -- la "
        + "structure a changé. NON MESURÉ, pas « pas de bataille ».");
    // ⛔ LA SCÈNE D'ABORD, ET C'EST LE SEUL CRAN QUI TIENNE.
    //
    // Trois voies ont été essayées, deux MESURÉES FAUSSES :
    //   1. `state.liveRunner` seul -> garde le runner mort (la pompe ne voit pas la transition) ;
    //   2. relire `_runner` sur l'`IdunGameViews` de la pompe -> l'objet mort reste MAPPÉ et
    //      rend encore le runner, qui rend encore son `Id`. Mesuré : +582 frames après une
    //      retraite confirmée, cette voie affirmait toujours `GuildBoss10Boss1AdmecBelisarius`.
    //      Lire un objet ne prouve PAS qu'il vive ;
    //   3. `premiereInstance(IdunGameViews)` -> rend NULL même en pleine bataille :
    //      `IdunGameViews` n'est pas un `UnityEngine.Object`, `FindObjectsByType` ne le voit pas.
    //
    // `IdunMainView`, lui, EST un `UnityEngine.Object`, et il s'est montré juste dans les DEUX
    // régimes (instance en bataille, absent après retraite). C'est donc lui qui atteste que la
    // scène de bataille est montée ; la pompe ne fournit plus que le POINTEUR de la vue.
    const kMain = findClassAnywhere("idun", "IdunMainView");
    if (!kMain) return sansRunner("classe `idun.IdunMainView` INTROUVABLE sur ce build -- "
        + "NON MESURÉ.");
    const scene = premiereInstance(kMain);
    if (estRefus(scene)) {
        return sansRunner("aucune `IdunMainView` vivante (" + scene.error + ") -- la scène de "
            + "bataille n'est pas montée. Ce n'est PAS « identité fausse ».");
    }
    const vue = state.gameViews;
    if (vue === null || vue.isNull()) {
        return sansRunner("la pompe n'a jamais vu d'`IdunGameViews` (aucune frame de bataille "
            + "drainée depuis l'injection) -- NON MESURÉ, pas « pas de bataille ».");
    }
    let r: NativePointer;
    try { r = vue.add(offRunner).readPointer(); }
    catch (e) { return sansRunner("`_runner` ILLISIBLE : " + (e as Error).message); }
    if (r.isNull()) {
        return sansRunner("`IdunGameViews` vivante mais son `_runner` est NUL -- la scène est là, "
            + "la bataille non.");
    }

    const mem = bcMemorisee === null ? null : {
        id: bcMemorisee.id, runner: bcMemorisee.runner,
        concorde: bcMemorisee.runner === r.toString(),
    };
    const pompe = etatPompe(cache !== null && cache.equals(r));
    let off = -1, champ: string | null = null;
    try {
        const k = r.readPointer();
        off = offsetDuChampBc(k);
        champ = off < 0 ? null : nomDuChampBc(k);
    } catch { /* traité ci-dessous */ }
    if (off < 0) {
        return { ok: true, lecture: true, id: null, champ: null, runner: r.toString(),
                 memorise: mem, pompe,
                 diagnostic: "aucun champ de type `BattleConfiguration` sur la classe du runner "
                     + "vivant -- la structure a changé. NON MESURÉ, pas « pas la bonne "
                     + "bataille »." };
    }
    let id: string | null = null;
    try { id = idDeLaConfig(r.add(off).readPointer()); } catch { id = null; }
    return {
        ok: true, lecture: true, id, champ, runner: r.toString(), memorise: mem, pompe,
        diagnostic: id === null
            ? "champ trouvé (" + String(champ) + ") mais `Id` ILLISIBLE -- NON MESURÉ."
            : "lu sur la `BattleConfiguration` du runner porté par l'`IdunGameViews` vivante.",
    };
}

function armerSeed(seed: number | null, unCoup: boolean): Record<string, unknown> | Refus {
    if (seed === null) {
        if (seedListener) { try { seedListener.detach(); } catch { /* best effort */ } }
        seedListener = null;
        seedImpose = null;
        return { ok: true, arme: false };
    }
    const mr = methodeInitializeSeed();
    if (estRefus(mr)) return mr;
    seedImpose = seed | 0;
    seedUnCoup = unCoup;
    if (!seedListener) {
        seedListener = Interceptor.attach(mr.ptr, {
            onEnter(args) {
                // `this`=args[0], `configuration`=args[1], `rngSeed`=args[2].
                // ON MÉMORISE L'IDENTITÉ, ÉPINGLÉE AU RUNNER -- inconditionnellement, et pas
                // seulement quand une condition est posée : c'est ce qui permet de RECOUPER, plus
                // tard, la lecture faite sur le runner vivant. Deux lectures de champ, aucune
                // invocation.
                //
                // ⚠ C'EST LE SEUL TÉMOIN QUI RESTE de ce hook, et il suffit : `batailleIdentite`
                // le publie avec le pointeur du runner vivant, donc « la bataille montée est bien
                // celle dont j'ai vu passer l'`Initialize` » reste une MESURE.
                try {
                    bcMemorisee = { runner: args[0].toString(), id: idDeLaConfig(args[1]) };
                } catch { /* une mémoire manquante fait dire NON MESURÉ, jamais conclure */ }
                if (seedImpose === null) return;
                // ⚠ LA CONDITION D'IDENTITÉ D'ABORD, ET ELLE RENONCE SUR NON-MESURE.
                // `args[1]` = `configuration`. Un `Id` qu'on n'a pas su lire n'est PAS un `Id`
                // qui concorde : on n'écrit pas sur une bataille qu'on n'a pas identifiée.
                if (seedSiConfigId !== null && idDeLaConfig(args[1]) !== seedSiConfigId) return;
                args[2] = ptr(seedImpose >>> 0);
                if (seedUnCoup) seedImpose = null;       // un seul coup : la bataille SUIVANTE
            },
        });
    }
    return { ok: true, arme: true, seed: seedImpose, unCoup,
             methode: "IdunBattle.Runner.IdunRunner$$Initialize (surcharge Int32)",
             note: "IMPOSITION : l'argument `rngSeed` sera reecrit a l'entree." };
}

// --- `_gameViews` : le champ SANS LEQUEL UN MODE À VAGUES NE TOURNE PAS -------------------
//
// CE QUE ÇA RÉPARE, ET COMMENT ON L'A TROUVÉ
// -------------------------------------------
// Une bataille montée par ce module SE MONTE mais NE TOURNE PAS : mesuré deux fois, elle se
// fige sur le tour de l'équipe ennemie, l'état ne bouge plus pendant 15 s alors que le CPU
// consomme, et l'équipe bloquée porte des unités VIVANTES à `inPlay: false` — des unités de
// vague dont l'apparition ne s'est jamais terminée.
//
// Le blocage est INDÉPENDANT du seed (deux seeds, même point d'arrêt) et INDÉPENDANT du draft
// (mesuré : seul le joueur du HÉROS a `DraftAfterUnitDeath`, le blocage est sur l'AUTRE camp,
// et une des deux captures a ZÉRO mort côté héros).
//
// Cause : **six** sources implémentent `HandleStartSpawningUnitsOfTurn`, et ce sont exactement
// les modes à vagues (Onslaught, LegendaryEvent, SurvivalEvent, TreasureBeach, LinearHeroEvent,
// TestScene). `SandboxGameModeSource` n'en fait PAS partie. L'implémentation de référence est
// minuscule et dit tout :
//
//     TestSceneBattleModeSource$$HandleStartSpawningUnitsOfTurn(this, playerId, group, continue)
//         if (this->_gameViews != 0)  return _gameViews.<slot 0x2b>(group, continue);
//
// Elle RELAIE LA CONTINUATION à `_gameViews`. Et le ctor à 5 paramètres de
// `SandboxGameModeSource` laisse `_gameViews` (+0x38) NUL.
//
// ⛔⛔ CE DIAGNOSTIC EST **RÉFUTÉ** — NE PAS LE RÉÉCRIRE, ET NE PAS ARMER CE RPC EN CROYANT
// QU'IL RÉPARE LA BOUCLE.
//
// L'utilisateur a corrigé l'observation : la bataille NE se bloque PAS à la première vague,
// elle tourne **quatre vagues** avant de se figer. L'apparition FONCTIONNE donc, et
// `_gameViews` n'est pas la cause. Re-mesuré sur les deux captures : les `entityId` du camp
// bloqué s'étalent sur 113..330 avec 4 sauts — plusieurs lots étaient bien passés.
//
// L'INVARIANT RÉEL, lui, est net et tient sur les deux blocages (seeds ET positions
// différents) : le camp bloqué n'a plus qu'**UNE** unité jouable, c'est un
// `tyranNpc4Warrior`, à PV PLEINS (4919/4919) — jamais touché, jamais joué. Son kit :
// `BigTarget` (« cannot be displaced »), `Synapse`, `ShadowInTheWarp`, l'active mêlée
// `ScythingTalons` (1065), et le passif `ReinforcedHiveNode` dont la condition dépend du round
// où l'unité est ENTRÉE EN JEU — donc sensible à une arrivée par vague tardive.
//
// ⇒ La suite se mesure avec `stack-sample.ts` (échantillonnage de piles), qui NOMME la boucle
// au lieu de la deviner. Ce RPC-ci reste livré parce qu'il est inoffensif (opt-in, n'écrit que
// sur une `SandboxGameModeSource` dont le champ est nul) et que le champ nul est un fait — mais
// il ne répare PAS ce qu'on cherchait, et c'est mesuré.
//
// Ce qui reste vrai et mesuré : les six sources qui portent le handler, le corps de la version
// TestScene, et `_gameViews` nul après notre ctor.
//
// POURQUOI UN HOOK ET PAS UNE ÉCRITURE À LA CONSTRUCTION
// -------------------------------------------------------
// Au moment de `StartMatch`, `IdunMainView` N'EXISTE PAS (mesuré : aucune instance hors
// bataille). C'est `ShowBattle` qui la peuple, via `LoadGameViews`, au tout début. On s'accroche
// donc à `ShowBattle` et on écrit à la SORTIE, quand `gameViews` (+0xb0) est renseigné.
//
// ⚠ Le hook ne touche QUE ce qu'il doit : il lit la source réellement active
// (`IdunMainView._activeGameSource`, +0xd0), n'agit que si sa classe EST
// `SandboxGameModeSource`, et n'écrit que si le champ est ENCORE NUL. Une bataille normale du
// jeu passe donc dessous sans être modifiée.
let gvListener: InvocationListener | null = null;
const gvJournal: Array<{ source: string; gameViews: string }> = [];
let gvRefus: string | null = null;

function armerInjectionGameViews(): Record<string, unknown> | Refus {
    if (gvListener) return { ok: true, arme: true, deja: true, journal: gvJournal.slice(-6) };
    const kVue = findClassAnywhere("idun", "IdunMainView");
    const kSrc = findClassAnywhere(NS_SRC, "SandboxGameModeSource");
    if (!kVue || !kSrc) {
        return refus("classe manquante : IdunMainView=" + (kVue !== null)
            + " SandboxGameModeSource=" + (kSrc !== null));
    }
    const mi = findMethodByParamCount(kVue, "ShowBattle", 2);
    if (!mi) return refus("`IdunMainView$$ShowBattle` à 2 paramètres INTROUVABLE");
    // PAR NOM, jamais par offset : un offset faux écrirait un pointeur plausible dans un
    // champ voisin, et rien ne le signalerait.
    const offVueGv = getFieldOffset(kVue, "gameViews");
    const offVueSrc = getFieldOffset(kVue, "_activeGameSource");
    const offSrcGv = getFieldOffset(kSrc, "_gameViews");
    if (offVueGv < 0 || offVueSrc < 0 || offSrcGv < 0) {
        return refus("champ absent sur ce build : IdunMainView.gameViews=" + offVueGv
            + " IdunMainView._activeGameSource=" + offVueSrc
            + " SandboxGameModeSource._gameViews=" + offSrcGv
            + " -- chemin PÉRIMÉ, pas de repli sur un offset en dur");
    }
    gvListener = Interceptor.attach(mi.ptr, {
        onEnter(args) { (this as unknown as { vue: NativePointer }).vue = args[0]; },
        onLeave() {
            try {
                const vue = (this as unknown as { vue: NativePointer }).vue;
                if (!vue || vue.isNull()) return;
                const src = vue.add(offVueSrc).readPointer();
                if (src.isNull()) return;
                const kObj = classeDeLObjet(src);
                if (!kObj || !kObj.equals(kSrc)) return;      // pas NOTRE source : on ne touche pas
                if (!src.add(offSrcGv).readPointer().isNull()) return;   // déjà renseigné
                const gv = vue.add(offVueGv).readPointer();
                if (gv.isNull()) { gvRefus = "IdunMainView.gameViews encore NUL à la sortie de "
                    + "ShowBattle -- rien écrit"; return; }
                src.add(offSrcGv).writePointer(gv);
                gvJournal.push({ source: src.toString(), gameViews: gv.toString() });
                if (gvJournal.length > 16) gvJournal.shift();
            } catch (e) { gvRefus = "injection a levé : " + (e as Error).message; }
        },
    });
    return { ok: true, arme: true,
             note: "injection armée sur IdunMainView$$ShowBattle -- n'agit que sur une "
                 + "SandboxGameModeSource dont `_gameViews` est encore nul" };
}

export function register(ctx: Ctx): void {

    /** Arme/lit l'injection de `_gameViews` (cf. le bloc ci-dessus). Le journal dit ce qui a
     *  ETE ECRIT : une injection « armee » qui n'a jamais tire se voit, au lieu de passer pour
     *  appliquee. */
    ctx.rpc.sandboxModeGameViews = (body?: { armer?: boolean }): unknown => {
        if (body == null || body.armer === undefined) {
            return { ok: true, arme: gvListener !== null, journal: gvJournal.slice(-6),
                     refus: gvRefus,
                     note: "lecture seule -- passer `armer: true` pour armer" };
        }
        if (body.armer === false) {
            if (gvListener) { try { gvListener.detach(); } catch { /* best effort */ } }
            gvListener = null;
            return { ok: true, arme: false, journal: gvJournal.slice(-6) };
        }
        return armerInjectionGameViews();
    };

    /** Imposer le seed de la PROCHAINE bataille, pour la rendre REJOUABLE.
     *
     *  body: { seed: <Int32> | null, unCoup?: boolean }
     *    - `seed: null`   -> desarme
     *    - `unCoup: true` (defaut) -> n'agit que sur la bataille suivante, puis se desarme
     *
     *  ⚠ CE RPC NE REND PLUS DE JOURNAL, et le mode `observer` a disparu avec lui (2026-08-22) :
     *  cf. le bloc du haut de fichier. Pour savoir si le seed a mordu, la reponse est en AVAL --
     *  un rejeu dont le seed n'a pas mordu diverge des le premier jet de des, et la confrontation
     *  coup par coup le dit au caractere pres. `batailleIdentite` reste disponible pour savoir
     *  QUELLE bataille a ete montee. */
    ctx.rpc.sandboxModeSeed = (body?: {
        seed?: number | null; unCoup?: boolean;
        /** N'imposer QUE si `BattleConfiguration.Id` vaut ceci. Sans lui, le seed part sur la
         *  prochaine bataille QUELLE QU'ELLE SOIT -- y compris une arène du joueur. */
        siConfigId?: string | null;
    }): unknown => {
        if (body?.siConfigId !== undefined) {
            seedSiConfigId = typeof body.siConfigId === "string" && body.siConfigId !== ""
                ? body.siConfigId : null;
        }
        // ⚠ `body == null` et NON `=== undefined` : un RPC appelé sans argument arrive à
        // `null`, pas à `undefined`, et le test strict laissait passer jusqu'au déréférencement
        // (« cannot read property 'seed' of null »). Mesuré à la première lecture.
        if (body == null || body.seed === undefined) {
            return { ok: true, arme: seedListener !== null, seedCourant: seedImpose,
                     unCoup: seedUnCoup,
                     note: "lecture seule -- `seed` pour armer ; `seed: null` pour desarmer" };
        }
        return armerSeed(body.seed === null ? null : (body.seed | 0), body.unCoup !== false);
    };

    /**
     * QUELLE BATAILLE EST MONTÉE — l'`Id` de sa `BattleConfiguration`. LECTURE PURE.
     *
     * C'est la réponse à « suis-je bien dans la bataille que je crois ? », et elle se prend là où
     * l'information EST : sur la BC que porte le runner vivant. La voie précédente déduisait
     * l'identité des NOMS D'UNITÉS adverses du plateau -- une coïncidence de chaînes qui n'est
     * garantie par rien (cf. le commentaire d'`offsetDuChampBc`).
     *
     * ⚠ `id: null` = NON MESURÉ. Ni « pas la bonne bataille », ni un feu vert. `diagnostic` dit
     * laquelle des trois causes s'applique (pas de runner / champ introuvable / `Id` illisible).
     *
     * `memorise` recoupe avec ce qu'on a vu passer à `IdunRunner$$Initialize` -- présent
     * seulement si le capteur de seed était armé à la création, et `concorde` dit s'il porte
     * bien sur CE runner-ci.
     */
    ctx.rpc.batailleIdentite = (): Promise<unknown> =>
        queueOnMainThread(() => identiteDeLaBatailleVivante());

    /** OBSERVATION PURE — ne construit rien, n'invoque rien qui écrive. */
    ctx.rpc.sandboxModeProbe = (body?: { mode?: string; classe?: string }): Promise<unknown> =>
        queueOnMainThread(() => {
            const kSrc = findClassAnywhere(NS_SRC, "SandboxGameModeSource");
            const modes: Record<string, unknown> = {};
            for (const [alias, nom] of Object.entries(MODES)) {
                const k = findClassAnywhere(NS_CFG, nom);
                if (!k) { modes[alias] = { classe: nom, resolue: false }; continue; }
                const arites: number[] = [];
                for (let n = 0; n <= 20; n++) {
                    if (findMethodByParamCount(k, ".ctor", n)) arites.push(n);
                }
                modes[alias] = { classe: nom, resolue: true, arites };
            }
            // Les classes des paramètres du mode demandé : c'est ce qu'il faut pour écrire
            // les `args`, et ça ne se devine pas.
            let signature: unknown = null;
            const kCfg = classeDuMode(body?.mode, body?.classe);
            if (!estRefus(kCfg)) {
                for (let n = 0; n <= 20; n++) {
                    const c = findMethodByParamCount(kCfg, ".ctor", n);
                    if (!c || n === 0) continue;
                    signature = Array.from({ length: n }, (_, i) => {
                        const kp = methodParamClass(c.info, i);
                        return { index: i, classe: nomDeClasse(kp), valueType: estTypeValeur(kp) };
                    });
                    break;
                }
            }
            const deps = dependances();
            return {
                ok: true,
                sourceResolue: kSrc !== null,
                ctorSource5: kSrc ? findMethodByParamCount(kSrc, ".ctor", 5) !== null : false,
                modes,
                signature,
                dependances: estRefus(deps) ? null : {
                    unitProgression: deps.prog.toString(),
                    gameConfigDto: deps.gameConfig.toString(),
                    logger: deps.logger.toString(),
                    featureUnlocker: deps.featureUnlocker.toString(),
                },
                dependancesRefus: estRefus(deps) ? deps.error : null,
                serialiseurPret: isSerializerReady(),
                deserialiseurPret: isDeserializerReady(),
                chargementEnCours: chargementEnCours(),
                // le seed : resolu, arme ou non, et lequel
                seedResolu: !estRefus(methodeInitializeSeed()),
                seedArme: seedListener !== null,
                seedCourant: seedImpose,
            };
        });

    /** FABRIQUE une BC et la rend en JSON. NE MONTE RIEN.
     *
     *  C'est la réponse à « construire une BC sans devoir la capturer » : la source appelle
     *  `LoadBattle`, qui est le code du jeu, et on sérialise le résultat.
     *
     *  ⚠ Pas de `confirmer` ici, et c'est délibéré : rien n'est monté, aucun match n'est
     *  écrasé. Ce qui reste vrai, c'est que `LoadBattle` est un natif dont on n'a pas lu le
     *  corps — s'il écrivait quelque part, on ne le saurait pas. Il est appelé UNE fois. */
    ctx.rpc.sandboxModeBuildBc = (body?: {
        mode?: string; classe?: string; args?: Arg[]; isRestart?: boolean;
        /** `"arene"` greffe la config d'environnement de la saison PvP (8 rounds / 20 %).
         *  Absent = champ laissé NUL, donc AUCUNE ability d'environnement installée. */
        environnement?: string | null;
    }): Promise<unknown> | unknown => {
        if (!Array.isArray(body?.args)) {
            return refus("`args` manquant (tableau, un descripteur par paramètre du ctor). "
                + "`sandboxModeProbe {mode}` donne la signature attendue.");
        }
        return queueOnMainThread(() => {
            if (bcOverride !== null) {
                return refus("REFUS : un override de BC est ARMÉ, donc `LoadBattle` est "
                    + "ancré -- l'invoquer ici GÈLE le jeu (ancrer ce qu'on invoque). "
                    + "Retirer l'override par `sandboxModeBcOverride { configJson: null }`, "
                    + "ou utiliser `sandboxModeStart`, où c'est le JEU qui appelle LoadBattle.");
            }
            const m = construire(body?.mode, body?.classe, body?.args as Arg[],
                                 body?.environnement);
            if (estRefus(m)) return m;
            const kSrc = findClassAnywhere(NS_SRC, "SandboxGameModeSource");
            const mi = kSrc ? findMethodByParamCount(kSrc, "LoadBattle", 1) : null;
            if (!mi) {
                return refus("`SandboxGameModeSource$$LoadBattle` à 1 paramètre INTROUVABLE");
            }
            const restart = Memory.alloc(1);
            restart.writeU8(body?.isRestart === true ? 1 : 0);
            let bc: NativePointer;
            try { bc = invokeMethod(mi.info, m.source, [restart]); }
            catch (e) {
                return refus("LoadBattle a levé : " + (e as Error).message
                    + " -- champs de la source : " + JSON.stringify(champsDeLaSource(m.source)));
            }
            if (bc.isNull()) {
                return refus("LoadBattle a rendu NULL -- la config est acceptée par le ctor "
                    + "mais ne produit pas de bataille (paramètres incohérents entre eux)");
            }
            epingler(bc);
            if (!isSerializerReady()) {
                return { ok: true, bc: bc.toString(), configJson: null,
                         avertissement: "BC construite mais `JsonConvert.SerializeObject` non "
                             + "résolu -- elle est en mémoire, pas lisible ici" };
            }
            const json = serializeToJson(bc);
            return {
                ok: true,
                bc: bc.toString(),
                source: m.source.toString(),
                config: m.config.toString(),
                taille: json ? json.length : null,
                configJson: json,
                champsSource: champsDeLaSource(m.source),
                // TRI-ÉTAT : `null` = greffe PAS DEMANDÉE (donc environnement VIDE), jamais
                // à lire comme « rien à installer ». Sinon, le compte des INSTALLÉES.
                environnement: m.environnement,
                postfix: etatPostfix(),   // RELU ici : les ancrages ne tirent que pendant LoadBattle
            };
        });
    };

    /** SUBSTITUER la BC que `LoadBattle` rend — pour faire tourner une BC **CAPTURÉE** dans
     *  la sandbox, au lieu d'une qu'on fabrique.
     *
     *  body: { configJson: string }  pose l'override · `{ configJson: null }` le retire ·
     *         rien : lit l'état.
     *
     *  À QUOI ÇA SERT, ET POURQUOI C'EST LA BONNE MANCHE. Quand un montage se fige, deux
     *  causes restent : notre BC est infidèle, ou le régime lui-même (l'IA qui joue le
     *  joueur) ne tient pas. Une BC **capturée sur une partie réelle jouée jusqu'au bout**
     *  est un témoin connu-bon : si elle se fige ici, notre BC est hors de cause ; si elle va
     *  au bout, c'est la nôtre. Une manche répond, là où un diff de formes cherche une
     *  aiguille.
     *
     *  POURQUOI ON N'UTILISE PAS `sandboxStartMatch({configJson})`, QUI PREND DÉJÀ UNE BC :
     *  il passe par `TestSceneBattleModeSource`, qui ne porte QUE `HandleStartMatch` et
     *  `HandleStartSpawningUnitsOfTurn` — pas `HandleBattleSurrender`. On monterait la BC et
     *  on ne pourrait plus SORTIR sans relancer le jeu (geste utilisateur). Ici on garde
     *  `SandboxGameModeSource` et ses six `Handle*`, dont la retraite est ÉPROUVÉE.
     *
     *  ⚠ ANCRER CE QU'ON INVOQUE = GEL. `sandboxModeBuildBc` appelle `LoadBattle` lui-même ;
     *  avec ce hook armé, ça a déjà coûté un gel dans ce dépôt. On REFUSE donc `buildBc` tant
     *  qu'un override est posé, plutôt que de laisser la faute se rejouer. */
    ctx.rpc.sandboxModeBcOverride = (body?: {
        configJson?: string | null;
    }): Promise<unknown> | unknown => {
        if (!body || body.configJson === undefined) {
            return { ok: true, lecture: true, arme: bcOverride !== null,
                     ancrage: overrideListener !== null,
                     note: "passer { configJson } pour armer, { configJson: null } pour retirer" };
        }
        return queueOnMainThread(() => {
            if (body.configJson === null) {
                bcOverride = null;
                battleConfig.declarerOverrideDeBc(null);
                return { ok: true, arme: false, action: "retire",
                         note: "l'ancrage reste posé mais devient transparent" };
            }
            if (!isDeserializerReady()) {
                return refus("`JsonConvert.DeserializeObject` non résolu -- on ne peut pas "
                    + "relire une BC");
            }
            const kBc = findClassAnywhere("IdunBattle.Configuration", "BattleConfiguration");
            if (!kBc) return refus("classe `BattleConfiguration` INTROUVABLE");
            let bc: NativePointer;
            try { bc = deserializeFromJson(body.configJson as string, kBc); }
            catch (e) { return refus("désérialisation refusée : " + (e as Error).message); }
            if (bc.isNull()) {
                return refus("désérialisation rendue NULLE -- le JSON n'est pas une "
                    + "`BattleConfiguration` (vérifier que c'est bien la BC, pas un replay)");
            }
            epingler(bc);
            bcOverride = bc;
            // Le hook de `battle-config` doit S'EFFACER sur cette source : sinon il
            // mute l'objet qu'on jette ET consomme `consumeOnce`, privant du patch
            // l'objet reellement monte.
            battleConfig.declarerOverrideDeBc("SandboxGameModeSource");

            // ⛔ LE MONTAGE DÉCLARE SA BATAILLE À LA MÉMOIRE DE POSE -- c'est ICI, et nulle part
            // ailleurs, qu'on sait qu'une bataille est LA NÔTRE. Deux dégâts mesurés le
            // 2026-08-22 quand ce lien n'existait pas : la composition d'une sandbox rejouée sur
            // la SUIVANTE (géométrie différente), et -- bien pire -- sur un combat officiel
            // contre le boss, où notre hook écrivait dans la partie du joueur.
            //
            // (!)L'ID SE LIT DANS LE JSON, PAS SUR L'OBJET NATIF. On vient de le désérialiser :
            // le relire par un champ natif demanderait un offset, donc une adresse à tenir à
            // jour. `JSON.parse` sur ~550 Ko coûte quelques millisecondes, une fois par montage.
            let idBc: string | null = null;
            try {
                const d = JSON.parse(body.configJson as string) as { Id?: unknown };
                if (typeof d.Id === "string") idBc = d.Id;
            } catch { /* `idBc` reste nul -- la mémoire sera vidée, ce qui est le côté sûr */ }
            const mem = deploymentDraft.memoireBatailleMontee(idBc);

            if (!overrideListener) {
                const kSrc = findClassAnywhere(NS_SRC, "SandboxGameModeSource");
                const mi = kSrc ? findMethodByParamCount(kSrc, "LoadBattle", 1) : null;
                if (!mi) return refus("`SandboxGameModeSource$$LoadBattle` INTROUVABLE -- "
                    + "override désarmé");
                overrideListener = Interceptor.attach(mi.ptr, {
                    onLeave(retval) {
                        if (bcOverride === null) return;   // transparent quand non armé
                        overrideFires++;
                        // ⛔ LE PATCH S'APPLIQUE A NOTRE OBJET, PAS A CELUI QU'ON JETTE.
                        // La sandbox ne MUTE pas la BC produite : elle en SUBSTITUE une autre,
                        // désérialisée à l'armement. Le hook de `battle-config` mutait donc le
                        // retour d'origine -- que ce `replace` rend aussitôt inaccessible.
                        // Mesuré le 2026-08-23 : patch écrit sur `0x22c13b0e200`, BC vivante
                        // `0x22c1021c600`, `ok: true` et `relu: true` des deux côtés, AUCUN signal.
                        //
                        // ⚠ Et c'est la sandbox qui perdait le plus à ce silence : son objet est
                        // d'éprouver ce que le patch FAIT. Un banc où le patch est le seul à ne pas
                        // s'appliquer valide un chemin que la vraie bataille ne suit pas. L'override
                        // reste le TRANSPORT ; le patch passe par le même pipeline des deux côtés.
                        // `declarerOverrideDeBc` empêche la double application (cf. là-bas).
                        battleConfig.appliquerPatchEnAttenteSur(
                            bcOverride, "SandboxGameModeSource (BC substituée)");
                        retval.replace(bcOverride);
                        // ⛔ LE JETON DE REJEU SE REPOSE ICI, ET C'EST LE RETRY QUI L'EXIGE.
                        // Ce point tire à CHAQUE chargement de la bataille sandbox -- montage
                        // initial ET retry -- alors que le RPC de montage, lui, ne passe qu'une
                        // fois. Un jeton posé au seul RPC était consommé par le premier écran de
                        // déploiement, et le retry rouvrait la phase SANS composition : la
                        // mémoire perdait exactement ce pour quoi elle existe.
                        //
                        // Et le refus reste entier là où il compte : une bataille RÉELLE a sa
                        // propre `GameModeSource` et ne passe JAMAIS par ici, donc elle ne pose
                        // aucun jeton. On n'écrit rien d'autre qu'un booléen -- pas d'invocation
                        // depuis un callback d'interception.
                        deploymentDraft.memoireRejeuAutoriser();
                    },
                });
                Interceptor.flush();
            }
            return { ok: true, arme: true, bc: bc.toString(),
                     taille: (body.configJson as string).length,
                     ancrage: "IdunBattle.ViewLogic.BattleSource.SandboxGameModeSource$$LoadBattle",
                     fires: overrideFires,
                     // Ce que le montage a fait à la mémoire de pose -- publié, parce qu'un
                     // vidage silencieux se lirait comme « rien ne s'est passé ».
                     memoireDePose: mem,
                     avertissement: "ARMÉ. `sandboxModeBuildBc` est REFUSÉ tant que ça dure "
                         + "(ancrer ce qu'on invoque gèle le jeu). Retirer avec "
                         + "`{ configJson: null }` avant de refabriquer une BC." };
        });
    };

    /** FABRIQUE la BC **et la MONTE** dans le jeu, par le chemin natif.
     *
     *  ⚠ `confirmer: true` exigé : `StartMatch` écrase le match courant et déclenche un
     *  chargement de scène. Ce n'est pas un lecteur. */
    ctx.rpc.sandboxModeStart = (body?: {
        mode?: string; classe?: string; args?: Arg[];
        confirmer?: boolean; checkIfAlreadyRunning?: boolean; injecterGameViews?: boolean;
        /** Cf. `sandboxModeBuildBc`. Le compte-rendu de la greffe est publié en retour --
         *  « l'appel est passé » ne dit rien de ce qui est INSTALLÉ. */
        environnement?: string | null;
    }): Promise<unknown> | unknown => {
        if (!Array.isArray(body?.args)) return refus("`args` manquant");
        if (body?.confirmer !== true) {
            return refus("REFUS : `confirmer: true` exigé. Ce RPC MONTE une bataille dans le "
                + "jeu. `sandboxModeBuildBc` fabrique la même BC SANS rien monter -- si c'est "
                + "la BC que tu veux, c'est lui qu'il faut appeler.");
        }
        return queueOnMainThread(() => {
            if (chargementEnCours() === true) {
                return refus("chargement de scène EN COURS -- `thor.Loader` refuserait EN "
                    + "SILENCE, l'appel est bloqué ici pour que ça se voie");
            }
            const m = construire(body?.mode, body?.classe, body?.args as Arg[],
                                 body?.environnement);
            if (estRefus(m)) return m;
            const kExec = findClassAnywhere("idun.shared.commands", "ViewCommandExecutor");
            const miStart = kExec ? findMethodByParamCount(kExec, "StartMatch", 2) : null;
            if (!miStart) return refus("`ViewCommandExecutor$$StartMatch` à 2 paramètres "
                + "INTROUVABLE");
            // Défaut `true` : la garde native contre l'écrasement d'un match déjà enregistré
            // côté serveur. La désarmer a déjà coûté 2 jetons de boss de guilde.
            const chk = Memory.alloc(1);
            chk.writeU8(body?.checkIfAlreadyRunning === false ? 0 : 1);
            try { invokeMethod(miStart.info, m.deps.exec, [m.source, chk]); }
            catch (e) {
                return refus("StartMatch a levé : " + (e as Error).message);
            }
            // ⚠ NOTER LA SOURCE, SINON LES LECTEURS DE BC REGARDENT UNE SOURCE MORTE. Sans ce
            // cran, `getLiveBattleConfig` retombe sur les sources CAPTURÉES et rend la BC d'une
            // bataille qui ne joue plus -- avec un `Id` plausible, donc sans rien signaler.
            noterSourceMontee(m.source);
            return {
                ok: true,
                source: m.source.toString(),
                config: m.config.toString(),
                champsSource: champsDeLaSource(m.source),
                // TRI-ÉTAT : `null` = greffe PAS DEMANDÉE (environnement VIDE).
                environnement: m.environnement,
                postfix: etatPostfix(),   // RELU ici : les ancrages ne tirent que pendant LoadBattle
                avertissement: "l'APPEL est passé -- ça ne dit RIEN du montage. Le vérifier "
                    + "par `sandboxProbe` / l'écran. Et la SORTIE reste non éprouvée sur cette "
                    + "source : elle porte les six `Handle*`, ce qui est la cause identifiée "
                    + "des pannes précédentes, mais aucune sortie n'a encore été JOUÉE.",
            };
        });
    };
}
