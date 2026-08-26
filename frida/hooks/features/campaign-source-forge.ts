// campaign-source-forge — FORGER une `CampaignGameModeSource` et en tirer SA `BattleConfiguration`.
//
// POURQUOI, ET EN QUOI C'EST L'HOMOLOGUE DE `guild-boss-config`
// --------------------------------------------------------------
// `campaign-builder` sait déjà produire une BC de campagne, mais il EXIGE une
// `CampaignGameModeSource` VIVANTE, captée au vol par un ancrage sur son ctor. Cet ancrage ne
// tire qu'à la navigation : après un reinject, ou si l'utilisateur est déjà en bataille, il n'y
// a rien à capter et tout le builder est mort -- il faut alors demander un clic humain.
//
// Côté boss de guilde, `guildBossSourceForger` a résolu ce problème depuis longtemps : on
// CONSTRUIT la source à partir des services que porte le `ViewCommandExecutor`, sans naviguer et
// sans démarrer. Ce module est le MÊME geste, pour la campagne.
//
// LA CHAÎNE
// ---------
//     CampaignGameModeSource..ctor(17 args)   <- 14 services + campaignId/index/enemyIsAiControlled
//       -> LoadBattle(isRestart: true)        -> IdunBattle.Configuration.BattleConfiguration
//
// ⚠ `isRestart: true` N'EST PAS UN DÉTAIL, C'EST LA SÛRETÉ, ET LE DÉCOMPILÉ LE DIT.
// `CampaignGameModeSource$$LoadBattle` construit la BC par
// `BattleConfigBuilder$$GetCampaignLevelConfig`, la range en `this+0x80`, PUIS :
//
//     if ((char)isRestart != '\0') { return this+0x80; }      <- SORTIE ANTICIPÉE
//     ... appel d'interface sur `this+0x30` avec l'index de lieu ...
//
// Autrement dit `LoadBattle(true)` rend la BC AVANT l'appel supplémentaire ; c'est `false` qui
// le déclenche. C'est l'équivalent exact du `LoadBattleInternal` du boss de guilde -- lequel
// n'existe PAS ici, d'où la nécessité de lire le corps plutôt que de se fier au nom.
//
// ⚠ L'EN-TÊTE DE `campaign-builder` DIT L'INVERSE (« LoadBattle(true) may emit funnel/analytics
// events »). Mesuré au décompilé le 2026-08-20 : c'est `false` qui atteint l'appel. On garde la
// prudence -- on n'appelle QUE `true` -- mais on ne recopie pas l'avertissement à l'envers.
//
// ⚠ CE QU'ON NE FAIT JAMAIS : `ViewCommandExecutor$$StartCampaignMatch`. C'est LUI qui démarre
// et engage l'énergie. On reproduit le geste QUI CONSTRUIT, jamais celui qui lance.

import {
    class_get_name, findClassAnywhere, findMethodByParamCount, getFieldOffset, s as cstr,
} from "../il2cpp/helpers.js";
import { createManagedString, il2cpp_object_new, invokeMethod } from "../il2cpp/invoke.js";
import { serializeToJson } from "../il2cpp/serializer.js";
import { gcRoot } from "../il2cpp/gc-root.js";
import { queueOnMainThread } from "../runtime/queue.js";
import { executeurVivant } from "./view-command.js";
import { chargerBcDepuisSource } from "./battle-config.js";
import { Ctx } from "../controller.js";

interface Refus { ok: false; error: string }
const refus = (m: string): Refus => ({ ok: false, error: m });
const estRefus = (x: unknown): x is Refus =>
    typeof x === "object" && x !== null && (x as { ok?: unknown }).ok === false;

const NS_SRC = "IdunBattle.ViewLogic.BattleSource";
const CLS_SRC = "CampaignGameModeSource";

/** Les 17 arguments du ctor, DANS L'ORDRE, et d'où vient chacun.
 *
 * ⚠ RÉSOLUS PAR NOM sur `ViewCommandExecutor`, jamais par offset : un offset copié devient faux
 * au prochain build, en silence. Un champ absent fait REFUSER en le NOMMANT.
 *
 * Mesuré le 2026-08-20 sur `t6dpr4k06g` : 11 des 12 champs attendus existent tels quels ; seul
 * `_campaignProgression` (SINGULIER) est absent de l'exécuteur -- il se DÉRIVE du pluriel par
 * `CampaignProgressions$$GetCampaign(campaignType, campaignId)`, qui est une lecture pure. */
const ARGS: Array<{ nom: string; champ?: string; special?: string }> = [
    { nom: "campaignProgression", special: "getCampaign" },
    { nom: "campaignProgressions", champ: "_campaignProgressions" },
    { nom: "userFunnelProgression", champ: "_userFunnelProgression" },
    { nom: "unitProgression", champ: "_unitProgression" },
    { nom: "modifierProgression", champ: "_modifierProgression" },
    { nom: "questProgression", champ: "_questProgression" },
    { nom: "gameConfig", champ: "_gameConfigData" },
    { nom: "viewCommandExecutor", special: "executeur" },
    { nom: "tutorialStatus", special: "tutorialStatusTool" },
    { nom: "logger", champ: "_logger" },
    { nom: "campaignId", special: "campaignId" },
    { nom: "initialLocationIndex", special: "locationIndex" },
    { nom: "enemyIsAiControlled", special: "enemyIsAiControlled" },
    { nom: "featureUnlocker", champ: "_featureUnlocker" },
    { nom: "heroReleaseEventProgression", champ: "_heroReleaseEventProgression" },
    { nom: "battleReconciliationProgression", champ: "_battleReconciliationProgression" },
    { nom: "questEventHandler", champ: "_questEventHandler" },
];

/** La source forgée, RETENUE et ENRACINÉE -- sans `gcRoot` le ramasse-miettes l'emporte. */
let sourceForgee: NativePointer | null = null;
let cibleForgee: { campaignType: number; campaignId: string; locationIndex: number } | null = null;

/**
 * La `CampaignGameModeSource` FORGÉE, pour les modules qui doivent lui DÉLÉGUER un appel.
 *
 * ⚠ EXPOSÉE POUR LA MÊME RAISON QUE CÔTÉ BOSS, ET LE SYMPTÔME EST LE MÊME : mesuré le
 * 2026-08-20, un nœud de campagne monté en sandbox affiche un ROSTER VIDE. La sandbox ne fournit
 * pas de roster -- `SandboxGameModeSource$$GetUnitsForDeploymentHUD` ne rend rien d'utile -- et
 * `deployment-draft` délègue donc ces méthodes à LA SOURCE DU MODE. Or son prêteur « campagne »
 * ne connaissait que la source CAPTÉE au vol par le ctor, laquelle est nulle dès qu'on n'a pas
 * navigué. Sans ce repli, forger la source ne sert à rien : la BC est juste, l'écran est vide.
 */
export function sourceCampagneForgee(): NativePointer | null {
    return sourceForgee !== null && !sourceForgee.isNull() ? sourceForgee : null;
}

/** Un `Int32` boxé, tel que `runtime_invoke` l'attend pour un type valeur. */
function argInt(v: number): NativePointer {
    const p = Memory.alloc(8);
    p.writeS32(v | 0);
    return p;
}

function argBool(v: boolean): NativePointer {
    const p = Memory.alloc(8);
    p.writeU8(v ? 1 : 0);
    return p;
}

export function register(ctx: Ctx): void {

    /**
     * FORGER la source d'un nœud de campagne. Ne démarre RIEN, ne dépense RIEN.
     *
     * `campaignType` : 0=Standard 1=Elite 2=Mirror 3=EliteMirror 4=Event (`Idun.Shared.CampaignType`).
     * `locationIndex` : l'index 0-BASÉ dans `battles`. Le `battleId` affiché par le jeu est
     * 1-basé -- le nœud « 31 » est donc l'index 30. On PUBLIE les deux pour que la confusion
     * se voie au lieu de se jouer.
     */
    ctx.rpc.campaignSourceForger = (body?: {
        campaignType?: number; campaignId?: string; locationIndex?: number;
        enemyIsAiControlled?: boolean; confirmer?: boolean;
    }): Promise<unknown> => queueOnMainThread(() => {
        const type = body?.campaignType ?? 0;
        const id = body?.campaignId;
        const idx = body?.locationIndex;
        if (typeof id !== "string" || id === "") return refus("`campaignId` manquant (ex. `elite4`)");
        if (typeof idx !== "number") return refus("`locationIndex` manquant (0-BASÉ : le nœud 31 "
            + "est l'index 30)");

        const exec = executeurVivant();
        if (estRefus(exec)) return exec;
        const kExec = findClassAnywhere("idun.shared.commands", "ViewCommandExecutor");
        if (!kExec) return refus("classe `ViewCommandExecutor` introuvable");

        // 1. Les champs de l'exécuteur, PAR NOM. Un seul absent => on s'arrête en le nommant.
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

        // 2. `campaignProgression` (SINGULIER) se DÉRIVE du pluriel. Lecture pure.
        const progs = depuis["_campaignProgressions"];
        if (progs === undefined || progs.isNull()) {
            return refus("`_campaignProgressions` NUL -- la progression de campagne n'est pas "
                + "câblée (pas encore synchronisé ?)");
        }
        const kProgs = progs.readPointer();
        const miGet = findMethodByParamCount(kProgs, "GetCampaign", 2);
        if (!miGet) {
            return refus("`CampaignProgressions$$GetCampaign(2)` INTROUVABLE -- la signature a "
                + "changé ; on ne devine pas une arité de remplacement");
        }

        // 3. `tutorialStatus` = `TutorialStatusTool..ctor(featureUnlocker)`, comme côté boss.
        const kTuto = findClassAnywhere("idun.shared", "TutorialStatusTool");
        if (!kTuto) return refus("classe `idun.shared.TutorialStatusTool` introuvable");
        const miTuto = findMethodByParamCount(kTuto, ".ctor", 1);
        if (!miTuto) return refus("`TutorialStatusTool..ctor(1)` INTROUVABLE");

        const kSrc = findClassAnywhere(NS_SRC, CLS_SRC);
        if (!kSrc) return refus(`classe \`${NS_SRC}.${CLS_SRC}\` introuvable`);
        const miCtor = findMethodByParamCount(kSrc, ".ctor", ARGS.length);
        if (!miCtor) {
            return refus(`\`${CLS_SRC}..ctor(${ARGS.length})\` INTROUVABLE -- la signature a `
                + "CHANGÉ sur ce build ; on ne devine pas une arité de remplacement");
        }

        if (body?.confirmer !== true) {
            return { ok: true, lecture: true,
                     cible: { campaignType: type, campaignId: id, locationIndex: idx,
                              battleIdAffiche: idx + 1 },
                     executeur: (exec as NativePointer).toString(),
                     champsNuls: nuls,
                     note: "`confirmer: true` exigé : ce RPC ALLOUE et CONSTRUIT une "
                         + "`CampaignGameModeSource`. Il n'appelle PAS `StartCampaignMatch`, donc "
                         + "il ne démarre aucune bataille et ne dépense aucune énergie." };
        }
        if (nuls.length > 0) {
            return refus("dépendances NULLES sur l'exécuteur : " + nuls.join(", ")
                + " -- la source serait construite incomplète, et le natif lèverait plus tard "
                + "sans rien nommer");
        }

        // La progression du nœud visé.
        let prog: NativePointer;
        try {
            prog = invokeMethod(miGet.info, progs, [argInt(type), createManagedString(id)]);
        } catch (e) {
            return refus("`GetCampaign` a levé : " + (e as Error).message);
        }
        if (prog.isNull()) {
            return refus(`\`GetCampaign(${type}, "${id}")\` a rendu NUL -- ce couple `
                + "type/campagne n'existe pas, ou n'est pas débloqué sur ce compte");
        }

        let tuto: NativePointer;
        try {
            tuto = il2cpp_object_new(kTuto);
            invokeMethod(miTuto.info, tuto, [depuis["_featureUnlocker"]]);
        } catch (e) {
            return refus("`TutorialStatusTool..ctor` a levé : " + (e as Error).message);
        }

        const valeurs: NativePointer[] = ARGS.map((a) => {
            if (a.champ) return depuis[a.champ];
            switch (a.special) {
                case "getCampaign": return prog;
                case "executeur": return exec as NativePointer;
                case "tutorialStatusTool": return tuto;
                case "campaignId": return createManagedString(id);
                case "locationIndex": return argInt(idx);
                case "enemyIsAiControlled": return argBool(body?.enemyIsAiControlled !== false);
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
        cibleForgee = { campaignType: type, campaignId: id, locationIndex: idx };
        return { ok: true, instance: src.toString(),
                 classe: cstr(class_get_name(src.readPointer()) as NativePointer),
                 cible: { ...cibleForgee, battleIdAffiche: idx + 1 },
                 note: "source FORGÉE. Aucune bataille démarrée, aucune énergie dépensée." };
    });

    /**
     * LA `BattleConfiguration` DU NŒUD, produite par la source elle-même.
     *
     * ⚠ `LoadBattle(isRestart: TRUE)`, et le décompilé est la raison (cf. l'en-tête) : ce bras
     * rend la BC par une SORTIE ANTICIPÉE, avant l'appel d'interface que le bras `false`
     * atteint. On ne choisit pas `true` par prudence vague -- on le choisit parce qu'on a lu où
     * le corps se sépare.
     */
    ctx.rpc.campaignSourceBc = (body?: { confirmer?: boolean }): Promise<unknown> =>
        queueOnMainThread(() => {
            const src = sourceForgee;
            if (src === null || src.isNull()) {
                return refus("aucune source forgée -- appeler `campaignSourceForger "
                    + "{campaignType, campaignId, locationIndex, confirmer:true}` d'abord");
            }
            // ⛔ LE TYPE AVANT TOUT : invoquer sur une disposition mémoire étrangère exécute du
            // natif à l'aveugle.
            const classe = cstr(class_get_name(src.readPointer()) as NativePointer);
            if (classe !== CLS_SRC) {
                return refus(`l'instance retenue est une \`${classe}\`, PAS une \`${CLS_SRC}\``);
            }
            const mi = findMethodByParamCount(src.readPointer(), "LoadBattle", 1);
            if (!mi) return refus("`CampaignGameModeSource$$LoadBattle(1)` INTROUVABLE");
            if (body?.confirmer !== true) {
                return { ok: true, lecture: true, instance: src.toString(), cible: cibleForgee,
                         note: "`confirmer: true` exigé : ce RPC INVOQUE `LoadBattle(true)` sur "
                             + "la source forgée. Il ne démarre pas de bataille et ne dépense "
                             + "pas d'énergie, mais il ÉCRIT `_currentBattle` sur CETTE source." };
            }
            // ⛔ PAR LE POINT DE PASSAGE UNIQUE : il DECLARE la source pendant l'appel. Le patch
            // d'env-ability s'applique dans l'`onLeave` de CE `LoadBattle`, et `ciblesAuto: "moi"`
            // a besoin de l'instance pour demander la composition du joueur -- absente de la BC.
            // Cette forge ne declarait PAS : mesure du 2026-08-26, `elite1 40` monte en sandbox
            // rendait `voie=aucune` et `0 cible`, alors que `lineupSource` sur la MEME instance
            // rendait 5 unites.
            let bc: NativePointer;
            try { bc = chargerBcDepuisSource(mi.info, src, [argBool(true)]); }
            catch (e) { return refus("`LoadBattle` a levé : " + (e as Error).message); }
            if (bc.isNull()) return refus("`LoadBattle` a rendu NUL");
            gcRoot.add(bc);
            const json = serializeToJson(bc);
            return {
                ok: true, instance: src.toString(), bc: bc.toString(), cible: cibleForgee,
                json,
                jsonRefus: json === null
                    ? "sérialisation Newtonsoft en échec -- la BC existe (pointeur ci-dessus) "
                        + "mais n'a pas pu être rendue en texte. NON MESURÉ, pas « BC vide »."
                    : null,
                octets: json === null ? null : json.length,
            };
        });
}
