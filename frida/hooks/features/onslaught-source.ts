// onslaught-source — FORGER une `OnslaughtGameModeSource`, pour lui DÉLÉGUER le roster.
//
// POURQUOI CE MODULE EXISTE
// --------------------------
// Un onslaught monté en sandbox affiche un ROSTER VIDE, et l'écran de déploiement est
// inutilisable. Mesuré le 2026-08-23, tier 18 voie Chaos, banc monté par `sandbox_mode.py start
// --mode waves` : `stage = Setup` (la phase s'ouvre bien), mais le HUD rend
// `minUnitsPossible: 0  maxUnitsPossible: 0  allUnitModels: 0  allUnlockedUnitModels: 0` et
// `_units.taille = 0`. C'est le stub : `SandboxGameModeSource$$GetUnitsForDeploymentHUD` rend un
// conteneur poolé fraîchement loué SANS lire un seul champ de `this`.
//
// `deployment-draft` sait déjà DÉLÉGUER ces méthodes à la source du MODE — c'est ainsi que la
// campagne, le boss de guilde et la guerre de guilde remplissent leur écran. Il manquait le
// prêteur du mode onslaught, donc l'instance à qui déléguer. Ce module la fabrique.
//
// ⚠ LA CLASSE N'EST PAS DANS `IdunBattle.ViewLogic.BattleSource`, ET LE CHERCHER LÀ REND ZÉRO.
// Les 23 autres sources de mode y vivent ; celle-ci est rangée sous
// `idun.Idun.Source.IdunMeta.View.Features.Onslaught.Battle`. Un balayage limité au namespace des
// autres conclut « pas de source onslaught sur ce build » — conclusion FAUSSE, tirée d'une
// recherche trop étroite, et c'est exactement ce qui a été fait avant d'écrire ce fichier.
//
// LA CHAÎNE
// ---------
//     OnslaughtGameModeSource..ctor(17 args)   <- 15 services + alliance + tier
//       -> GetUnitsForDeploymentHUD()          -> PooledList<System.String>   (le ROSTER)
//       -> GetBattleLineup(lineupIndex)        -> System.String[]             (la COMPOSITION)
//       -> GetGameModeSpecificDeploymentHudOptions() / Min|MaxUnitsPossibleToStartBattle()
//
// `alliance` et `tier` sont des paramètres EN CLAIR du ctor : la voie et le palier se choisissent
// donc sans naviguer, et sans dépendre de ce que le joueur a ouvert à l'écran.
//
// ⛔ CE QU'ON N'APPELLE JAMAIS : `LoadBattle`. Ce module ne sert qu'à PRÊTER un roster. Produire
// une BC d'onslaught a déjà sa voie (`sandbox_mode.py --mode waves`, qui passe par
// `SandboxWavesBattleConfig` -> `GetOnslaughtConfig`), et rien ici ne démarre de bataille ni
// n'engage de jeton.

import {
    class_get_name, findClassAnywhere, findMethodByParamCount, getFieldOffset, s as cstr,
} from "../il2cpp/helpers.js";
import { il2cpp_object_new, invokeMethod } from "../il2cpp/invoke.js";
import { gcRoot } from "../il2cpp/gc-root.js";
import { queueOnMainThread } from "../runtime/queue.js";
import { executeurVivant } from "./view-command.js";
import { Ctx } from "../controller.js";

interface Refus { ok: false; error: string }
const refus = (m: string): Refus => ({ ok: false, error: m });
const estRefus = (x: unknown): x is Refus =>
    typeof x === "object" && x !== null && (x as { ok?: unknown }).ok === false;

const NS_SRC = "idun.Idun.Source.IdunMeta.View.Features.Onslaught.Battle";
const CLS_SRC = "OnslaughtGameModeSource";

/** `Idun.Source.IdunMeta.Logic.UserProgress.Units.GrandAllianceType`, lu dans `enums.tsv`.
 *
 * ⚠ ON ÉCRIT LE MEMBRE, JAMAIS L'ORDINAL AU SITE D'APPEL. Un ordinal juste aujourd'hui devient
 * faux au renumérotage suivant, EN SILENCE — et le porteur ici est un simple `Int32` que le natif
 * ne validera pas. Le nom est le seul canal où la faute se voit. */
const ALLIANCE: Record<string, number> = { Imperial: 0, Xenos: 1, Chaos: 2 };

/** Les 17 arguments du ctor, DANS L'ORDRE, et d'où vient chacun.
 *
 * ⚠ RÉSOLUS PAR NOM sur `ViewCommandExecutor`, jamais par offset — même règle que
 * `campaign-source-forge`. Mesuré le 2026-08-23 sur `t6dpr4k06g` : les 15 dépendances sont
 * TOUTES présentes telles quelles sur l'exécuteur (273 champs), aucune à dériver. C'est plus
 * simple que la campagne, dont `_campaignProgression` (singulier) manque et se dérive.
 *
 * Les offsets mesurés ne sont PAS écrits ici : ils ne servent qu'à dire que la mesure a eu lieu,
 * et `getFieldOffset` les re-résout à chaque appel. */
const ARGS: Array<{ nom: string; champ?: string; special?: string }> = [
    { nom: "gameConfig", champ: "_gameConfigData" },
    { nom: "menuSystems", champ: "_menuSystems" },
    { nom: "universe", champ: "_universe" },
    { nom: "unitProgression", champ: "_unitProgression" },
    { nom: "resourceProgression", champ: "_resourceProgression" },
    { nom: "modifierProgression", champ: "_modifierProgression" },
    { nom: "onslaughtProgression", champ: "_onslaughtProgression" },
    { nom: "battleReconciliationProgression", champ: "_battleReconciliationProgression" },
    { nom: "viewCommandExecutor", special: "executeur" },
    { nom: "tooltipManager", champ: "_tooltipManager" },
    { nom: "logger", champ: "_logger" },
    { nom: "alliance", special: "alliance" },
    { nom: "tier", special: "tier" },
    { nom: "featureUnlocker", champ: "_featureUnlocker" },
    { nom: "questEventHandler", champ: "_questEventHandler" },
    { nom: "onlineFeatureDecider", champ: "_onlineFeatureDecider" },
    { nom: "showOnslaughtScreenViewCommand", champ: "_showOnslaughtScreenViewCommand" },
];

/** La source forgée, RETENUE et ENRACINÉE -- sans `gcRoot` le ramasse-miettes l'emporte. */
let sourceForgee: NativePointer | null = null;
let cibleForgee: { alliance: string; allianceOrdinal: number; tier: number } | null = null;

/**
 * La `OnslaughtGameModeSource` FORGÉE, pour `deployment-draft` qui doit lui DÉLÉGUER le roster.
 *
 * Rend `null` tant que `onslaughtSourceForger {confirmer:true}` n'a pas été joué — jamais un
 * pointeur douteux. Le prêteur doit DIRE qu'il n'a rien, pas prêter du vide.
 */
export function sourceOnslaughtForgee(): NativePointer | null {
    return sourceForgee !== null && !sourceForgee.isNull() ? sourceForgee : null;
}

/** Ce que la source forgée DÉCRIT — publié pour qu'une cible discordante se VOIE. */
export function cibleOnslaughtForgee(): typeof cibleForgee {
    return cibleForgee;
}

/** Un `Int32` boxé, tel que `runtime_invoke` l'attend pour un type valeur. */
function argInt(v: number): NativePointer {
    const p = Memory.alloc(8);
    p.writeS32(v | 0);
    return p;
}

export function register(ctx: Ctx): void {

    /**
     * FORGER la source d'une voie d'onslaught. Ne démarre RIEN, ne dépense RIEN.
     *
     * `alliance` : `"Imperial"` | `"Xenos"` | `"Chaos"` — le NOM, pas l'ordinal.
     * `tier`     : le palier tel que le jeu l'affiche (1..21).
     */
    ctx.rpc.onslaughtSourceForger = (body?: {
        alliance?: string; tier?: number; confirmer?: boolean;
    }): Promise<unknown> => queueOnMainThread(() => {
        const nomAlliance = body?.alliance;
        const tier = body?.tier;
        if (typeof nomAlliance !== "string" || !(nomAlliance in ALLIANCE)) {
            return refus("`alliance` manquante ou inconnue -- attendu l'un de "
                + Object.keys(ALLIANCE).join(", ") + ` (reçu ${JSON.stringify(nomAlliance)})`);
        }
        if (typeof tier !== "number" || !Number.isInteger(tier) || tier < 1) {
            return refus("`tier` manquant -- un entier >= 1, tel que le jeu l'affiche");
        }
        const ordinal = ALLIANCE[nomAlliance];

        const exec = executeurVivant();
        if (estRefus(exec)) return exec;
        const kExec = findClassAnywhere("idun.shared.commands", "ViewCommandExecutor");
        if (!kExec) return refus("classe `ViewCommandExecutor` introuvable");

        // 1. Les champs de l'exécuteur, PAR NOM. Un seul absent => on s'arrête en le NOMMANT.
        const depuis: Record<string, NativePointer> = {};
        const absents: string[] = [];
        const nuls: string[] = [];
        for (const a of ARGS) {
            if (!a.champ) continue;
            const off = getFieldOffset(kExec, a.champ);
            if (off < 0) { absents.push(a.champ); continue; }
            const p = (exec as NativePointer).add(off).readPointer();
            if (p.isNull()) nuls.push(a.champ);
            depuis[a.champ] = p;
        }
        if (absents.length > 0) {
            return refus("champs ABSENTS de `ViewCommandExecutor` sur ce build : "
                + absents.join(", ") + " -- chemin PÉRIMÉ, on ne devine pas un offset");
        }

        const kSrc = findClassAnywhere(NS_SRC, CLS_SRC);
        if (!kSrc) {
            return refus(`classe \`${NS_SRC}.${CLS_SRC}\` introuvable -- ⚠ elle n'est PAS dans `
                + "`IdunBattle.ViewLogic.BattleSource` comme les 23 autres sources de mode");
        }
        const miCtor = findMethodByParamCount(kSrc, ".ctor", ARGS.length);
        if (!miCtor) {
            return refus(`\`${CLS_SRC}..ctor(${ARGS.length})\` INTROUVABLE -- la signature a `
                + "CHANGÉ sur ce build ; on ne devine pas une arité de remplacement");
        }

        if (body?.confirmer !== true) {
            return { ok: true, lecture: true,
                     cible: { alliance: nomAlliance, allianceOrdinal: ordinal, tier },
                     executeur: (exec as NativePointer).toString(),
                     dependances: ARGS.filter((a) => a.champ).length,
                     champsNuls: nuls,
                     note: "`confirmer: true` exigé : ce RPC ALLOUE et CONSTRUIT une "
                         + "`OnslaughtGameModeSource`. Il n'appelle NI `LoadBattle` NI aucun "
                         + "démarrage -- aucune bataille montée, aucun jeton engagé." };
        }
        if (nuls.length > 0) {
            return refus("dépendances NULLES sur l'exécuteur : " + nuls.join(", ")
                + " -- la source serait construite incomplète, et le natif lèverait plus tard "
                + "sans rien nommer");
        }

        const valeurs: NativePointer[] = ARGS.map((a) => {
            if (a.champ) return depuis[a.champ];
            switch (a.special) {
                case "executeur": return exec as NativePointer;
                case "alliance": return argInt(ordinal);
                case "tier": return argInt(tier);
                default: return ptr(0);
            }
        });

        let src: NativePointer;
        try {
            src = il2cpp_object_new(kSrc);
            invokeMethod(miCtor.info, src, valeurs);
        } catch (e) {
            return refus("le ctor a levé : " + (e as Error).message);
        }
        if (src.isNull()) return refus("l'allocation a rendu NUL");
        gcRoot.add(src);
        sourceForgee = src;
        cibleForgee = { alliance: nomAlliance, allianceOrdinal: ordinal, tier };
        return { ok: true, instance: src.toString(),
                 classe: cstr(class_get_name(src.readPointer()) as NativePointer),
                 cible: { ...cibleForgee },
                 note: "source FORGÉE. Rien n'est monté, rien n'est dépensé. Elle sert de "
                     + "PRÊTEUR à `deploymentPoolArmer {source: \"onslaught\"}`." };
    });

    /**
     * CE QUE LA SOURCE FORGÉE RÉPOND — sans rien monter, et sans passer par le HUD.
     *
     * C'est le témoin de la délégation : si `GetBattleLineup` rend déjà la bonne composition ici,
     * un écran resté vide accuse le CÂBLAGE, pas la source. Sans ce cran, les deux causes sont
     * indiscernables et on va corriger la mauvaise.
     *
     * ⚠ `GetUnitsForDeploymentHUD` rend un `PooledList<System.String>` — un TYPE VALEUR, dont la
     * disposition n'est pas lisible statiquement. On ne le déréférence donc PAS ici : c'est
     * `deployment-draft` qui sait l'observer, sur la classe RÉELLEMENT vue. On ne rend que
     * `GetBattleLineup` (un `System.String[]`, lui parfaitement typé) et les deux bornes.
     *
     * ⚠ LE PARAMÈTRE DE `GetBattleLineup` EST UNE TAILLE, PAS UN INDEX — son nom dans le dump
     * (`lineupIndex`) dit le contraire, et le croire fait lire un vide pour une absence. Mesuré
     * le 2026-08-23 sur la voie Chaos : `0 -> []`, `1 -> 1 élément`, `2 -> 2`, `18 -> 18`. Le
     * natif rend la composition sauvegardée AJUSTÉE au nombre de places demandé. D'où le défaut
     * ci-dessous : `MaxUnitsPossibleToStartBattle`, lu sur la source, jamais un `5` écrit ici.
     */
    ctx.rpc.onslaughtSourceRoster = (body?: { places?: number }): Promise<unknown> =>
        queueOnMainThread(() => {
            const src = sourceForgee;
            if (src === null || src.isNull()) {
                return refus("aucune source forgée -- appeler `onslaughtSourceForger "
                    + "{alliance, tier, confirmer:true}` d'abord");
            }
            // ⛔ LE TYPE AVANT TOUT : invoquer sur une disposition mémoire étrangère exécute du
            // natif à l'aveugle.
            const klass = src.readPointer();
            const classe = cstr(class_get_name(klass) as NativePointer);
            if (classe !== CLS_SRC) {
                return refus(`l'instance retenue est une \`${classe}\`, PAS une \`${CLS_SRC}\``);
            }

            // ⚠ `runtime_invoke` BOXE les types valeur : un `Int32` revient dans un OBJET géré,
            // et sa valeur est à `+0x10` — pas dans le pointeur lui-même. Mesuré ici le
            // 2026-08-23 : lire le pointeur avec `.toInt32()` a rendu -165316864 / -165316896 /
            // -165316928, trois « bornes » espacées de 32 octets, c'est-à-dire trois ADRESSES
            // consécutives. Un nombre absurde se voit ; un nombre PLAUSIBLE ne se verrait pas.
            const bornes: Record<string, number | null> = {};
            for (const nom of ["MinUnitsNeededToStartBattle", "MaxUnitsPossibleToStartBattle",
                               "AmountOfUnlockedUnits"]) {
                const mi = findMethodByParamCount(klass, nom, 0);
                // TRI-ÉTAT : `null` = PAS MESURÉ (méthode absente ou levée), jamais un zéro.
                if (!mi) { bornes[nom] = null; continue; }
                try {
                    const boite = invokeMethod(mi.info, src, []);
                    bornes[nom] = boite.isNull() ? null : boite.add(0x10).readS32();
                } catch { bornes[nom] = null; }
            }

            const miLineup = findMethodByParamCount(klass, "GetBattleLineup", 1);
            if (!miLineup) {
                return { ok: true, cible: cibleForgee, bornes,
                         lineup: null,
                         lineupRefus: "`GetBattleLineup(1)` INTROUVABLE sur ce build" };
            }
            // Le défaut se LIT sur la source (le plafond du mode), il ne s'écrit pas : un `5` en
            // dur ici deviendrait faux le jour où le mode change de plafond, en silence.
            const places = body?.places ?? bornes["MaxUnitsPossibleToStartBattle"] ?? 0;
            let arr: NativePointer;
            try { arr = invokeMethod(miLineup.info, src, [argInt(places)]); }
            catch (e) {
                return { ok: true, cible: cibleForgee, bornes, lineup: null,
                         lineupRefus: "`GetBattleLineup` a levé : " + (e as Error).message };
            }
            if (arr.isNull()) {
                return { ok: true, cible: cibleForgee, bornes, lineup: null,
                         lineupRefus: "`GetBattleLineup` a rendu NUL -- aucune composition "
                             + "sauvegardée pour cette voie (PAS « roster vide »)" };
            }
            // `System.String[]` : longueur en +0x18, éléments à partir de +0x20.
            //
            // ⚠ ON PUBLIE LA CLASSE ET LE POINTEUR. Une longueur de 0 ne distingue pas « aucune
            // composition sauvegardée » d'« offset lu de travers » : sans le nom de classe du
            // retour, les deux rendent le même zéro, et on irait corriger la mauvaise cause.
            const classeArr = (() => {
                try { return cstr(class_get_name(arr.readPointer()) as NativePointer); }
                catch { return null; }
            })();
            const n = arr.add(0x18).readS32();
            const lineup: string[] = [];
            for (let i = 0; i < n && i < 64; i++) {
                const s = arr.add(0x20 + i * Process.pointerSize).readPointer();
                lineup.push(s.isNull() ? "<null>" : s.add(0x14).readUtf16String() ?? "<illisible>");
            }
            return { ok: true, cible: cibleForgee, bornes, lineup, lineupTaille: n, places,
                     retour: { ptr: arr.toString(), classe: classeArr },
                     lineupRefus: n === 0
                         ? "tableau de longueur 0 -- si `retour.classe` n'est pas un tableau de "
                             + "chaînes, c'est l'OFFSET qui est faux, pas la composition qui est "
                             + "vide"
                         : null,
                     instance: src.toString() };
        });
}
