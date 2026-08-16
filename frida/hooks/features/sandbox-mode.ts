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
    class_get_name, class_is_valuetype, findClassAnywhere,
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
            for (const id of a.ids) {
                const m = modeleUnite(prog, id, a.voie ?? "unit");
                if (estRefus(m)) return m;
                try { invokeMethod(add.info, l, [m]); }
                catch (e) { return refus("Add(" + id + ") a levé : " + (e as Error).message); }
            }
            return l;
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

export function register(ctx: Ctx): void {

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

    /** FABRIQUE la BC **et la MONTE** dans le jeu, par le chemin natif.
     *
     *  ⚠ `confirmer: true` exigé : `StartMatch` écrase le match courant et déclenche un
     *  chargement de scène. Ce n'est pas un lecteur. */
    ctx.rpc.sandboxModeStart = (body?: {
        mode?: string; classe?: string; args?: Arg[];
        confirmer?: boolean; checkIfAlreadyRunning?: boolean;
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
