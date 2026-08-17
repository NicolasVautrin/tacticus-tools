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
    class_get_name, class_is_valuetype, findClassAnywhere, findMethodByParamClasses,
    findMethodByParamCount, getFieldOffset, methodParamClass, s,
} from "../il2cpp/helpers.js";
import { createManagedString, il2cpp_object_new, invokeMethod } from "../il2cpp/invoke.js";
import { deserializeFromJson, isDeserializerReady, isSerializerReady, serializeToJson }
    from "../il2cpp/serializer.js";
import { chargementEnCours } from "../game/loader.js";
import { gcRoot } from "../il2cpp/gc-root.js";
import { queueOnMainThread } from "../runtime/queue.js";
import { executeurVivant } from "./view-command.js";
import { Ctx } from "../controller.js";

interface Refus { ok: false; error: string }
function estRefus(x: unknown): x is Refus {
    return typeof x === "object" && x !== null && (x as { ok?: unknown }).ok === false;
}
function refus(msg: string): Refus { return { ok: false, error: msg }; }

const NS_CFG = "IdunBattle.ViewLogic.BattleSource.SandboxBattleConfig";
const NS_SRC = "IdunBattle.ViewLogic.BattleSource";

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
    | { genre: "unitesParJoueur";
        joueurs: Array<{ ids: string[]; voie?: "unit" | "npc" | "summon" }> }
    | { genre: "json"; valeur: unknown }         // DTO, List<String>, Dictionary<...>
    | { genre: "nul" };

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

/** Lie UN argument contre la classe RÉELLE de son paramètre. */
function lier(
    kParam: NativePointer | null, a: Arg, prog: NativePointer,
): NativePointer | Refus {
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
                const interne = collectionVide(kInt);
                if (estRefus(interne)) return interne;
                for (const id of a.joueurs[j].ids) {
                    const m = modeleUnite(prog, id, a.joueurs[j].voie ?? "unit");
                    if (estRefus(m)) return refus("joueur " + j + " : " + m.error);
                    try { invokeMethod(addInt.info, interne, [m]); }
                    catch (e) {
                        return refus("joueur " + j + " : Add(" + id + ") a levé : "
                            + (e as Error).message);
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

    return {
        exec: ex, prog: lu["_unitProgression"], gameConfig: dto,
        logger: lu["_logger"], featureUnlocker: lu["_featureUnlocker"],
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

interface Montage { config: NativePointer; source: NativePointer; deps: Deps }

function construire(mode: string | undefined, classe: string | undefined, args: Arg[])
    : Montage | Refus {
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

    const deps = dependances();
    if (estRefus(deps)) return deps;

    // Liaison argument par argument, contre la classe RÉELLE du paramètre.
    const lies: NativePointer[] = [];
    for (let i = 0; i < args.length; i++) {
        const kParam = methodParamClass(ctorCfg.info, i);
        const v = lier(kParam, args[i], deps.prog);
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
    return { config: cfg, source: src, deps };
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
let seedImpose: number | null = null;
let seedUnCoup = true;
let seedListener: InvocationListener | null = null;
const seedJournal: Array<{ remplace: string; par: number }> = [];

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
function armerSeed(seed: number | null, unCoup: boolean): Record<string, unknown> | Refus {
    if (seed === null) {
        if (seedListener) { try { seedListener.detach(); } catch { /* best effort */ } }
        seedListener = null;
        seedImpose = null;
        return { ok: true, arme: false, journal: seedJournal.slice(-8) };
    }
    const mr = methodeInitializeSeed();
    if (estRefus(mr)) return mr;
    seedImpose = seed | 0;
    seedUnCoup = unCoup;
    if (!seedListener) {
        seedListener = Interceptor.attach(mr.ptr, {
            onEnter(args) {
                if (seedImpose === null) return;
                // `this`=args[0], `configuration`=args[1], `rngSeed`=args[2].
                let avant = "?";
                try { avant = args[2].toString(); } catch { /* best effort */ }
                args[2] = ptr(seedImpose >>> 0);
                seedJournal.push({ remplace: avant, par: seedImpose });
                if (seedJournal.length > 32) seedJournal.shift();
                if (seedUnCoup) seedImpose = null;   // un seul coup : la bataille SUIVANTE
            },
        });
    }
    return { ok: true, arme: true, seed: seedImpose, unCoup,
             methode: "IdunBattle.Runner.IdunRunner$$Initialize (surcharge Int32)" };
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
     *  Le retour porte le JOURNAL : ce qui a ete remplace, et par quoi. Un seed « impose »
     *  qui n'a jamais tire se verrait donc, au lieu de passer pour applique. */
    ctx.rpc.sandboxModeSeed = (body?: { seed?: number | null; unCoup?: boolean }): unknown => {
        // ⚠ `body == null` et NON `=== undefined` : un RPC appelé sans argument arrive à
        // `null`, pas à `undefined`, et le test strict laissait passer jusqu'au déréférencement
        // (« cannot read property 'seed' of null »). Mesuré à la première lecture.
        if (body == null || body.seed === undefined) {
            return { ok: true, arme: seedListener !== null, seedCourant: seedImpose,
                     unCoup: seedUnCoup, journal: seedJournal.slice(-8),
                     note: "lecture seule -- passer `seed` pour armer, `seed: null` pour desarmer" };
        }
        return armerSeed(body.seed === null ? null : (body.seed | 0), body.unCoup !== false);
    };

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
                // le seed : arme ou non, et ce qu'il a REELLEMENT remplace
                seedResolu: !estRefus(methodeInitializeSeed()),
                seedArme: seedListener !== null,
                seedCourant: seedImpose,
                seedJournal: seedJournal.slice(-8),
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
            const m = construire(body?.mode, body?.classe, body?.args as Arg[]);
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

            if (!overrideListener) {
                const kSrc = findClassAnywhere(NS_SRC, "SandboxGameModeSource");
                const mi = kSrc ? findMethodByParamCount(kSrc, "LoadBattle", 1) : null;
                if (!mi) return refus("`SandboxGameModeSource$$LoadBattle` INTROUVABLE -- "
                    + "override désarmé");
                overrideListener = Interceptor.attach(mi.ptr, {
                    onLeave(retval) {
                        if (bcOverride === null) return;   // transparent quand non armé
                        overrideFires++;
                        retval.replace(bcOverride);
                    },
                });
                Interceptor.flush();
            }
            return { ok: true, arme: true, bc: bc.toString(),
                     taille: (body.configJson as string).length,
                     ancrage: "IdunBattle.ViewLogic.BattleSource.SandboxGameModeSource$$LoadBattle",
                     fires: overrideFires,
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
            const m = construire(body?.mode, body?.classe, body?.args as Arg[]);
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
            return {
                ok: true,
                source: m.source.toString(),
                config: m.config.toString(),
                champsSource: champsDeLaSource(m.source),
                avertissement: "l'APPEL est passé -- ça ne dit RIEN du montage. Le vérifier "
                    + "par `sandboxProbe` / l'écran. Et la SORTIE reste non éprouvée sur cette "
                    + "source : elle porte les six `Handle*`, ce qui est la cause identifiée "
                    + "des pannes précédentes, mais aucune sortie n'a encore été JOUÉE.",
            };
        });
    };
}
