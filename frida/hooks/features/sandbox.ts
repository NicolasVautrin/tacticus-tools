// sandbox — jouer une `BattleConfiguration` ARBITRAIRE dans le JEU, à l'écran.
//
// CE QUE ÇA RÉSOUT
// ----------------
// On sait déjà monter n'importe quelle bataille sur un runner HEADLESS (`initRunner` +
// `applyAddUnit` + `startBattle`) : c'est ainsi qu'on rejoue un replay au bit près. Ce qui
// manquait, c'est de VOIR cette même configuration — la jouer à la main, avec l'UI.
//
// LA VOIE EST NATIVE, ET C'EST LE POINT
// --------------------------------------
//   `idun.IdunMainView$$StartBattle(battleConfig, skipUnitDeployment)`
// prend une `BattleConfiguration` toute faite. Aucun `Interceptor.replace`, aucun détournement
// du démarrage de bataille : on APPELLE ce que le jeu appelle déjà.
//
// ⚠ NE PAS CONFONDRE AVEC LE CAMPAIGN-BUILDER, qui va dans l'AUTRE SENS. Lui PRODUIT une BC
// (progression-swap sur `CampaignProgression`, puis `LoadBattle`) ; ici on en CONSOMME une.
// La famille `IdunBattle.ViewLogic.BattleSource.Sandbox*` (un `Sandbox<Mode>BattleConfig` par
// mode de jeu, dont `SandboxGuildBossBattleConfig`) est elle aussi un PRODUCTEUR : elle
// fabrique la BC depuis des paramètres. Quand on a déjà la BC, elle est inutile — et la
// construire coûterait de fabriquer des `IUnitModel`, des `List<>` et des `Dictionary<>`
// managés pour rien.
//
// CE QUE CE MODULE REFUSE, ET POURQUOI
// -------------------------------------
//   - tout démarrage sans `confirmer: true`. `StartBattle` LANCE une vraie bataille dans le
//     jeu de l'utilisateur : ce n'est pas un lecteur.
//   - un appel quand `IdunMainView` n'a aucune instance. Le refus est NOMMÉ (la scène de
//     bataille n'est pas montée) plutôt que rendu comme un échec générique : c'est la
//     condition normale hors bataille, pas une panne.
//   - un appel pendant un chargement de scène. `thor.Loader` REFUSE EN SILENCE dans cette
//     fenêtre — un `ok: true` y serait un mensonge.
//
// ⚠ ET IL NE DISPENSE PAS D'OBSERVER D'ABORD. `sandboxProbe` est là pour ça, et il ne mute
// RIEN : le dépôt a déjà rendu `ok: true` puis trouvé le jeu MORT en invoquant un natif qui
// écrit sans l'avoir observé.
//
// ⚠⚠ LA SORTIE DE BATAILLE FAIT CRASHER LE JEU — LE CYCLE DE VIE N'EST PAS BOUCLÉ
// ------------------------------------------------------------------------------
// Mesuré le 2026-08-16 : le MONTAGE marche (boss de guilde à 22 200 785 PV, ses adds, sans
// campagne ni warmup), mais `IdunMainView$$EndBattleAndGoToMeta` sur une bataille montée
// ainsi rend `IsBattleActive = false` PUIS `loader = 0` — les deux lectures RÉUSSISSENT —
// et le process MEURT ensuite, pendant le chargement du meta (`Tacticus.exe.80832.dmp`,
// 38 Mo). Les mesures d'après-coup étaient VERTES : le crash arrive après elles.
//
// Cause probable, à confirmer : `TestSceneBattleModeSource` ne porte NI `HandleFinishBattle`
// NI `HandleBattleSurrender` — `SandboxGameModeSource`, si. Le retour au meta réclame
// score / loot / métadonnées de replay à la source, qui ne les fournit pas.
//
// ⇒ Ne pas traiter ce montage comme acquis tant que la sortie n'est pas résolue. Pistes NON
// essayées : construire un `SandboxGameModeSource` (il porte les deux `Handle*`) au lieu
// d'un `TestSceneBattleModeSource` ; ou ne jamais sortir, et relancer par-dessus.
//
// ⚠⚠⚠ ET IL A COÛTÉ DEUX JETONS DE BOSS DE GUILDE SUR LE COMPTE RÉEL — MESURÉ
// ---------------------------------------------------------------------------
// Le ctor déclare `unitProgression: idun.tests.TestUnitProgression`. On lui passait le VRAI
// `IUnitProgression` du compte, lu sur l'exécuteur vivant ; `il2cpp_runtime_invoke` ne
// type-check pas, donc ça montait sans broncher.
//
// ⚠ LE DANGER N'EST PAS LE TYPE — LE CHAMP EST DÉCLARÉ `IUnitProgression` (RPC `classFields` :
// `TestSceneBattleModeSource` = `_battleConfiguration@0x10`, `_unitProgression@0x18`
// (IUnitProgression), `_gameViews@0x20`, `_menuSystems@0x28`, `_battleFinished@0x30`).
// C'EST UNE HYPOTHÈSE DE **DISPOSITION**. Le ctor construit un délégué et l'écrit à
// `*(unitProgression + 0x88)`, un offset qui n'a de sens que dans la classe de TEST :
//
//     idun.tests.TestUnitProgression        +0x88 = _GetAbilityConfig  (Func`3)  <- slot prévu
//     IdunMetaLogic.UserProgress.UnitProgression  +0x88 = _powerFormula (IPowerFormula)
//
// Passer la vraie progression ÉCRASE donc `_powerFormula` du compte par un délégué. Tout
// calcul de puissance ultérieur (`GetPowerForUnit`, `GetPowerForNpcUnit`,
// `GetAccumulatedPowerOfAllPlayerUnits`, ...) dispatche sur le mauvais vtable — ce qui
// explique le CRASH au retour au meta, qui recalcule la puissance partout.
// (`_guildBossProgression` est ailleurs, à +0xc0, et n'est pas touché.)
//
// ⚠ CE N'EST PAS PAR LÀ QUE LES JETONS SONT PARTIS — voir le bloc suivant. Le correctif reste
// juste (le type déclaré est une classe de test, et le ctor ÉCRIT dans l'objet reçu), mais il
// ne faut pas lui attribuer la perte : le RE l'a réfuté.
//
// CE QUI FAIT PERDRE UNE TENTATIVE DE BOSS DE GUILDE — ÉTABLI PAR RE
// -------------------------------------------------------------------
// `ViewCommandExecutor$$StartMatch` ne dépense RIEN et ne touche AUCUNE progression :
//
//     if (checkIfAlreadyRunning) { ... refuse + LogError si un match tourne déjà ... }
//     holder = new <MatchHolder>; *(holder + 0x20) = gameModeSource;
//     **(statique + 0xb8) = holder;          // ÉCRASE LE MATCH COURANT
//     thor.Loader$$LoadBattle(0);
//
// Côté boss de guilde, la tentative est enregistrée AU CHARGEMENT, avant qu'on joue :
// `GuildBossGameModeSource$$SendLoadBattleGameEventInternal` appelle
// `TempBattleData$$GenerateNewBattleId` puis poste un game-event au serveur. D'où
// `GuildBossProgression$$WasLastLoadedBattleAcknowledgedByServer`,
// `IBattleReconciliationProgression`, et le `battle_reconciliation.json` du disque.
// Une tentative enregistrée puis JAMAIS TERMINÉE est perdue — et aucun compteur local n'est
// décrémenté, donc la perte ne laisse AUCUNE trace côté client.
//
// ⇒ La garde est le booléen `checkIfAlreadyRunning`, et ce module passait `false`. Il est
// désormais à `true` par défaut. S'y ajoute : ne pas monter depuis un écran de bataille ou
// une prévisualisation de combat, et ne PAS revenir au meta avec cette source (elle n'a pas
// de `HandleFinishBattle`, donc le meta hérite d'une bataille jamais close).
//
// ⚠ CE QUE LE RE A RÉFUTÉ, ET QU'IL NE FAUT PAS RÉÉCRIRE : « le compte à rebours de
// `guildBoss.battleTokens.countdownStartedAt` ne démarre que sur une dépense ». FAUX.
// `GuildBossProgressionData$$ApplyBattleTokens` lit une quantité et une date DANS LE DTO
// SERVEUR et les recopie par `AbstractStaminaProgressionData$$SetEnergyAtServerTime` : cet
// horodatage marque une SYNCHRONISATION, pas une dépense, et n'accuse personne.

import {
    class_get_name, findClassAnywhere, findMethodByParamCount, getFieldOffset, s,
} from "../il2cpp/helpers.js";
import { chargementEnCours } from "../game/loader.js";
import { il2cpp_object_new } from "../il2cpp/invoke.js";
import { invokeMethod } from "../il2cpp/invoke.js";
import { deserializeFromJson, isDeserializerReady } from "../il2cpp/serializer.js";
import { gcRoot } from "../il2cpp/gc-root.js";
import { queueOnMainThread } from "../runtime/queue.js";
// ⚠ IMPORTÉE, PAS RECOPIÉE. `premiereInstance` porte une mesure qu'une copie perdrait : la
// surcharge de `FindObjectsByType` à 3 arguments (`FindObjectsInactive.Include`), sans
// laquelle un objet désactivé rend « 0 instance » sur une classe qui résout parfaitement.
import { premiereInstance, executeurVivant } from "./view-command.js";
import { Ctx } from "../controller.js";

interface Refus { ok: false; error: string }
function estRefus(x: unknown): x is Refus {
    return typeof x === "object" && x !== null && (x as { ok?: unknown }).ok === false;
}

/** La BC désérialisée est ÉPINGLÉE jusqu'au prochain montage. Sans `gcRoot.add`, l'objet
 *  managé peut être déplacé ou libéré entre la désérialisation et l'appel — c'est la course
 *  « BC injoignable entre deserialize et Initialize » déjà rencontrée dans `initRunner`, dont
 *  le symptôme est une bataille qui démarre à moitié construite. */
let bcEpinglee: NativePointer | null = null;

function epinglerBc(p: NativePointer): void {
    if (bcEpinglee) { try { gcRoot.remove(bcEpinglee); } catch { /* best effort */ } }
    try { gcRoot.add(p); bcEpinglee = p; } catch { /* best effort */ }
}

// ⚠ `chargementEnCours` est IMPORTÉE de `game/loader.ts`, et cette ligne remplace une
// réimplémentation FAUSSE, mesurée : `thor.Loader.__loadingStep` est un champ **STATIQUE**,
// que j'avais lu comme un champ d'instance sur une instance quelconque -- il rendait `true`
// en permanence là où le foyer rend `0 / false`. Un garde qui se trompe dans ce sens bloque
// tout ; dans l'autre, il autoriserait le geste exactement au pire moment.
// Le foyer passe par `il2cpp_field_static_get_value` (voie NOMMÉE) et porte le tri-état.

/** La progression JETABLE que le ctor de `TestSceneBattleModeSource` déclare vraiment.
 *
 *  `idun.tests.TestUnitProgression..ctor` ne prend AUCUN paramètre — donc rien n'oblige à
 *  emprunter celle du compte, et c'est ce qui rend le refus tenable plutôt que théorique.
 *
 *  ⚠ La raison est une DISPOSITION, pas un type (mesurée au RPC `classFields`) : le ctor
 *  écrit un délégué à `+0x88`, qui vaut `_GetAbilityConfig` (`Func`3`) sur la classe de test
 *  et `_powerFormula` (`IPowerFormula`) sur la vraie `UnitProgression`. Lui passer celle du
 *  compte CORROMPT donc le calcul de puissance — cf. l'en-tête du module.
 *
 *  Mémoïsée + `gcRoot` : réinstancier à chaque montage ferait un objet managé de plus à
 *  garder en vie pour rien, et un objet non enraciné peut être déplacé entre sa création et
 *  l'appel du ctor. */
let progTest: NativePointer | null = null;

function progressionDeTest(): NativePointer | Refus {
    if (progTest && !progTest.isNull()) return progTest;
    const k = findClassAnywhere("idun.tests", "TestUnitProgression");
    if (!k) {
        return { ok: false, error: "`idun.tests.TestUnitProgression` INTROUVABLE sur ce build "
            + "-- REFUS. Pas de repli sur la progression du compte : c'est elle qui porte "
            + "`IGuildBossProgression`, et ce repli a déjà coûté 2 jetons de boss de guilde." };
    }
    const ctor = findMethodByParamCount(k, ".ctor", 0);
    if (!ctor) {
        return { ok: false, error: "`TestUnitProgression..ctor` à 0 paramètre INTROUVABLE "
            + "-- REFUS (le ctor sans argument est ce qui rend la progression jetable "
            + "constructible ; sans lui, on ne sait pas en fabriquer une)" };
    }
    try {
        const p = il2cpp_object_new(k) as NativePointer;
        if (p.isNull()) return { ok: false, error: "il2cpp_object_new(TestUnitProgression) -> NULL" };
        gcRoot.add(p);
        invokeMethod(ctor.info, p, []);
        progTest = p;
        return p;
    } catch (e) {
        return { ok: false, error: "TestUnitProgression..ctor a levé : " + (e as Error).message };
    }
}

interface Cible { klass: NativePointer; inst: NativePointer; mi: { info: NativePointer } }

/** Résout `IdunMainView` + son `StartBattle` à 2 paramètres. Chaque échec porte SA cause :
 *  « classe absente » (build changé) et « aucune instance » (hors bataille) demandent des
 *  gestes opposés, les confondre ferait chercher au mauvais endroit. */
function cibleStartBattle(): Cible | Refus {
    const klass = findClassAnywhere("idun", "IdunMainView");
    if (!klass) {
        return { ok: false, error: "classe idun.IdunMainView introuvable sur ce build" };
    }
    const mi = findMethodByParamCount(klass, "StartBattle", 2);
    if (!mi) {
        return { ok: false, error: "IdunMainView$$StartBattle à 2 paramètres non résolue "
            + "-- la signature attendue est (BattleConfiguration, Boolean)" };
    }
    const inst = premiereInstance(klass);
    if (estRefus(inst)) {
        return { ok: false, error: "aucune IdunMainView vivante : la scène de bataille n'est "
            + "pas montée. C'est l'état NORMAL hors bataille, pas une panne -- il faut que le "
            + "jeu soit dans une bataille pour que cette vue existe. (" + inst.error + ")" };
    }
    return { klass, inst, mi };
}

/** La voie SANS CAMPAGNE, et c'est la bonne.
 *
 *  `IdunMainView$$StartBattle` (plus bas) est appelée par le jeu PENDANT le montage de la
 *  scène : l'invoquer sur une scène déjà montée ne recharge RIEN -- mesuré, l'instance ne
 *  bouge pas et aucun chargement ne démarre. Il fallait donc entrer en bataille d'abord,
 *  c'est-à-dire lancer une node de CAMPAGNE dont on ne veut pas.
 *
 *  En amont, le jeu passe par :
 *      `ViewCommandExecutor$$StartMatch(gameModeSource, checkIfAlreadyRunning)`
 *  qui accepte un `IGameModeSource` ARBITRAIRE. Et `TestSceneBattleModeSource..ctor` prend
 *  une `BattleConfiguration` toute faite. Donc : notre BC -> une source -> `StartMatch`, et
 *  le jeu monte NOTRE bataille par son propre chemin.
 *
 *  ⚠ Le ctor déclare `unitProgression: idun.tests.TestUnitProgression` -- une classe de
 *  TEST. `il2cpp_runtime_invoke` ne vérifie pas les types, donc passer le vrai
 *  `IUnitProgression` du compte PEUT marcher ; ce probe le DIT au lieu de le supposer, et
 *  nomme ce qui manque. Rien n'est construit ici. */
function sonderVoieStartMatch(): Record<string, unknown> {
    const kSrc = findClassAnywhere("IdunBattle.ViewLogic.BattleSource",
                                   "TestSceneBattleModeSource");
    const kProg = findClassAnywhere("idun.tests", "TestUnitProgression");
    const kMenu = findClassAnywhere("thor.Menu", "MenuSystems");
    const kExec = findClassAnywhere("idun.shared.commands", "ViewCommandExecutor");
    const ctorSrc = kSrc ? findMethodByParamCount(kSrc, ".ctor", 3) : null;
    const miStart = kExec ? findMethodByParamCount(kExec, "StartMatch", 2) : null;

    // Instances : `MenuSystems` porte un `Update()` mais `FindObjectsByType` rend 0 dessus
    // (mesure de `view-command.ts`) -- on publie donc le refus, pas un zéro nu.
    let menuInst: string | null = null;
    let menuRefus: string | null = null;
    if (kMenu) {
        const r = premiereInstance(kMenu);
        if (estRefus(r)) menuRefus = r.error; else menuInst = r.toString();
    }
    return {
        testSceneSourceResolue: kSrc !== null,
        ctor3ParamsResolu: ctorSrc !== null,
        testUnitProgressionResolue: kProg !== null,
        menuSystemsResolue: kMenu !== null,
        menuSystemsInstance: menuInst,
        menuSystemsRefus: menuRefus,
        startMatchResolu: miStart !== null,
    };
}

export function register(ctx: Ctx): void {

    /** OBSERVATION PURE de la voie `StartMatch` — ne construit rien, n'invoque rien. */
    ctx.rpc.sandboxVoieProbe = (): Promise<unknown> =>
        queueOnMainThread(() => {
            const base = sonderVoieStartMatch();
            const ex = executeurVivant();
            if (estRefus(ex)) return { ok: true, ...base, executeur: null, executeurRefus: ex.error };
            const kExec = findClassAnywhere("idun.shared.commands", "ViewCommandExecutor");
            const dep: Record<string, unknown> = { executeur: ex.toString() };
            for (const nom of ["_menuSystems", "_unitProgression"]) {
                const off = kExec ? getFieldOffset(kExec, nom) : -1;
                dep[nom] = off < 0 ? null : ex.add(off).readPointer().toString();
            }
            return { ok: true, ...base, ...dep };
        });

    /** Monte NOTRE BC dans le jeu SANS passer par une node de campagne.
     *
     *  Chaîne, toute native :
     *      JSON -> `BattleConfiguration`
     *      -> `new TestSceneBattleModeSource(bc, unitProgression, menuSystems)`
     *      -> `ViewCommandExecutor$$StartMatch(source, checkIfAlreadyRunning: true)`
     *
     *  ⚠ `_menuSystems` se prend PAR NOM sur l'exécuteur vivant, jamais par offset : les
     *  offsets bougent d'un build à l'autre, et une valeur lue au mauvais offset ne se
     *  signale pas -- elle fabrique un pointeur plausible.
     *
     *  ⚠⚠ La progression, elle, est FABRIQUÉE (`idun.tests.TestUnitProgression`, ctor sans
     *  argument) et non empruntée à l'exécuteur. `progressionDuCompte: true` rebranche celle
     *  du compte, et alors la bataille court POUR DE VRAI : elle débite jetons et tentatives.
     *  Mesuré le 2026-08-16 -- 2 jetons de boss de guilde, cf. l'en-tête du module. */
    ctx.rpc.sandboxStartMatch = (body?: {
        configJson?: string; confirmer?: boolean; checkIfAlreadyRunning?: boolean;
        progressionDuCompte?: boolean;
    }): Promise<unknown> | unknown => {
        if (!body?.configJson) return { ok: false, error: "`configJson` manquant" };
        if (body.confirmer !== true) {
            return { ok: false, error: "REFUS : `confirmer: true` exigé. Ce RPC MONTE une "
                + "bataille dans le jeu -- `sandboxVoieProbe` observe d'abord." };
        }
        return queueOnMainThread(() => {
            if (chargementEnCours() === true) {
                return { ok: false, error: "chargement de scène EN COURS -- un changement de "
                    + "scène serait refusé EN SILENCE" };
            }
            const ex = executeurVivant();
            if (estRefus(ex)) return ex;
            const kExec = findClassAnywhere("idun.shared.commands", "ViewCommandExecutor");
            const kSrc = findClassAnywhere("IdunBattle.ViewLogic.BattleSource",
                                           "TestSceneBattleModeSource");
            const kBc = findClassAnywhere("IdunBattle.Configuration", "BattleConfiguration");
            if (!kExec || !kSrc || !kBc) {
                return { ok: false, error: "classe manquante : "
                    + `exec=${kExec !== null} src=${kSrc !== null} bc=${kBc !== null}` };
            }
            const ctor = findMethodByParamCount(kSrc, ".ctor", 3);
            const miStart = findMethodByParamCount(kExec, "StartMatch", 2);
            if (!ctor || !miStart) {
                return { ok: false, error: "méthode manquante : "
                    + `ctor3=${ctor !== null} StartMatch2=${miStart !== null}` };
            }
            const offProg = getFieldOffset(kExec, "_unitProgression");
            const offMenu = getFieldOffset(kExec, "_menuSystems");
            if (offProg < 0 || offMenu < 0) {
                return { ok: false, error: "champ absent de ViewCommandExecutor sur ce build : "
                    + `_unitProgression=${offProg} _menuSystems=${offMenu} `
                    + "-- chemin PÉRIMÉ, ne pas replier sur un offset" };
            }
            const progCompte = ex.add(offProg).readPointer();
            const menu = ex.add(offMenu).readPointer();
            if (progCompte.isNull() || menu.isNull()) {
                return { ok: false, error: "dépendance NULLE sur l'exécuteur : "
                    + `_unitProgression=${progCompte} _menuSystems=${menu} `
                    + "-- l'exécuteur existe mais n'a pas reçu ses dépendances" };
            }

            // ⚠ LA PROGRESSION EST LE POINT DE DÉBIT DU COMPTE, PAS UN DÉTAIL DE CÂBLAGE.
            // Défaut = la jetable ; celle du compte n'est atteignable que sur demande
            // NOMMÉE. Ce n'est pas de la prudence de principe : le repli silencieux a
            // débité 2 jetons de boss de guilde le 2026-08-16 (cf. l'en-tête).
            let prog: NativePointer;
            if (body.progressionDuCompte === true) {
                prog = progCompte;
            } else {
                const pt = progressionDeTest();
                if (estRefus(pt)) return pt;
                prog = pt;
            }
            if (!isDeserializerReady()) {
                return { ok: false, error: "JsonConvert.DeserializeObject non résolu" };
            }
            let bc: NativePointer;
            try { bc = deserializeFromJson(body.configJson as string, kBc); }
            catch (e) { return { ok: false, error: "désérialisation : " + (e as Error).message }; }
            if (bc.isNull()) return { ok: false, error: "désérialisation -> NULL" };
            epinglerBc(bc);

            // ⚠ `il2cpp_object_new` NU puis `.ctor` explicite : `createObject` enchaînerait
            // un ctor SANS paramètre, qui n'existe pas ici.
            let src: NativePointer;
            try {
                src = il2cpp_object_new(kSrc) as NativePointer;
                if (src.isNull()) return { ok: false, error: "il2cpp_object_new -> NULL" };
                gcRoot.add(src);
                // `prog` est la progression JETABLE, du type que le ctor déclare -- sauf
                // `progressionDuCompte: true`, où c'est celle du compte et où le débit est
                // ASSUMÉ par l'appelant.
                invokeMethod(ctor.info, src, [bc, prog, menu]);
            } catch (e) {
                return { ok: false, error: "TestSceneBattleModeSource..ctor a levé : "
                    + (e as Error).message
                    + (body.progressionDuCompte === true
                        ? " -- la substitution d'`IUnitProgression` au `TestUnitProgression`"
                          + " déclaré est la cause la plus probable"
                        : "") };
            }
            // ⚠⚠ LE DÉFAUT EST `true`, ET C'EST LA GARDE PRINCIPALE DE CE MODULE.
            //
            // `ViewCommandExecutor$$StartMatch` ne dépense rien et ne touche aucune
            // progression : elle ÉCRASE le match courant dans un champ statique, puis
            // appelle `thor.Loader$$LoadBattle`. Avec `checkIfAlreadyRunning`, elle REFUSE
            // (et journalise) quand un match tourne déjà ; sans lui, elle écrase.
            //
            // Or côté boss de guilde la tentative est enregistrée AU CHARGEMENT, avant
            // qu'on joue : `GuildBossGameModeSource$$SendLoadBattleGameEventInternal`
            // appelle `TempBattleData$$GenerateNewBattleId` puis poste un game-event.
            // D'où `WasLastLoadedBattleAcknowledgedByServer`, `IBattleReconciliationProgression`
            // et le `battle_reconciliation.json` du disque. Écraser un match enregistré mais
            // non terminé PERD la tentative -- sans qu'aucun compteur local ne soit décrémenté,
            // donc sans trace côté client.
            //
            // Ce module passait `false`. C'était la valeur exactement inverse de celle qu'il
            // fallait, et elle désarmait la seule garde native disponible.
            const chk = Memory.alloc(1);
            chk.writeU8(body.checkIfAlreadyRunning === false ? 0 : 1);
            try {
                invokeMethod(miStart.info, ex, [src, chk]);
            } catch (e) {
                return { ok: false, error: "StartMatch a levé : " + (e as Error).message,
                         source: src.toString(), bc: bc.toString() };
            }
            return {
                ok: true, source: src.toString(), bc: bc.toString(),
                progression: body.progressionDuCompte === true ? "DU COMPTE" : "de test",
                avertissement: "appel passé -- le montage se MESURE (sandboxProbe : "
                    + "`chargementEnCours` puis `instance`), un retour d'appel ne le prouve pas"
                    + (body.progressionDuCompte === true
                        ? " ; et cette bataille court SUR LE COMPTE RÉEL -- elle peut en "
                          + "débiter jetons et tentatives"
                        : ""),
            };
        });
    };


    /** OBSERVATION PURE — ne construit rien, n'invoque rien, ne mute rien. */
    ctx.rpc.sandboxProbe = (): Promise<unknown> => queueOnMainThread(() => {
        const klass = findClassAnywhere("idun", "IdunMainView");
        const mi = klass ? findMethodByParamCount(klass, "StartBattle", 2) : null;
        let instance: string | null = null;
        let refusInstance: string | null = null;
        if (klass) {
            const r = premiereInstance(klass);
            if (estRefus(r)) refusInstance = r.error;
            else instance = r.toString();
        }
        return {
            ok: true,
            classe: klass ? s(class_get_name(klass) as NativePointer) : null,
            startBattleResolue: mi !== null,
            instance,
            refusInstance,
            deserialiseurPret: isDeserializerReady(),
            chargementEnCours: chargementEnCours(),
            bcEpinglee: bcEpinglee ? bcEpinglee.toString() : null,
            // Ce que `sandboxStartBattle` exigera, pour que l'appelant sache CE QUI manque
            // avant de tenter -- plutôt que de lire un refus après coup.
            pret: klass !== null && mi !== null && instance !== null
                && isDeserializerReady() && chargementEnCours() === false,
        };
    });

    /** Lance une bataille VISIBLE depuis un JSON de `BattleConfiguration`.
     *
     *  `skipUnitDeployment: true` (défaut) garde les unités et positions PORTÉES PAR LA BC ;
     *  à `false`, le jeu ouvre son écran de déploiement et l'utilisateur place lui-même. */
    ctx.rpc.sandboxStartBattle = (body?: {
        configJson?: string; skipUnitDeployment?: boolean; confirmer?: boolean;
    }): Promise<unknown> | unknown => {
        if (!body?.configJson) {
            return { ok: false, error: "`configJson` manquant" };
        }
        if (body.confirmer !== true) {
            return { ok: false, error: "REFUS : `confirmer: true` exigé. Ce RPC LANCE une "
                + "vraie bataille dans le jeu -- utilise `sandboxProbe` pour observer d'abord." };
        }
        return queueOnMainThread(() => {
            const charge = chargementEnCours();
            if (charge === true) {
                return { ok: false, error: "un chargement de scène est EN COURS -- `thor.Loader` "
                    + "refuserait en silence, l'appel est bloqué ici pour que ça se voie" };
            }
            const c = cibleStartBattle();
            if (estRefus(c)) return c;
            if (!isDeserializerReady()) {
                return { ok: false, error: "JsonConvert.DeserializeObject non résolu" };
            }
            const kBc = findClassAnywhere("IdunBattle.Configuration", "BattleConfiguration");
            if (!kBc) {
                return { ok: false, error: "classe BattleConfiguration introuvable" };
            }
            let bc: NativePointer;
            try {
                bc = deserializeFromJson(body.configJson as string, kBc);
            } catch (e) {
                return { ok: false, error: "désérialisation de la BC : " + (e as Error).message };
            }
            if (bc.isNull()) {
                return { ok: false, error: "la désérialisation a rendu NULL -- JSON invalide "
                    + "ou incompatible avec `BattleConfiguration` de ce build" };
            }
            epinglerBc(bc);

            const skip = Memory.alloc(1);
            skip.writeU8(body.skipUnitDeployment === false ? 0 : 1);
            try {
                invokeMethod(c.mi.info, c.inst, [bc, skip]);
            } catch (e) {
                return { ok: false, error: "StartBattle a levé : " + (e as Error).message,
                         bc: bc.toString() };
            }
            return {
                ok: true,
                bc: bc.toString(),
                skipUnitDeployment: body.skipUnitDeployment !== false,
                // ⚠ `ok: true` dit que l'APPEL est passé, PAS que la bataille est montée :
                // c'est `observeBattle` / l'écran qui l'établissent. Le dépôt a déjà lu un
                // retour d'appel comme une preuve d'effet -- ne pas recommencer.
                avertissement: "appel passé -- vérifier l'état réel du jeu, un retour d'appel "
                    + "ne prouve pas que la bataille est montée",
            };
        });
    };
}
