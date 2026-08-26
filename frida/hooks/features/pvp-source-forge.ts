// pvp-source-forge — FORGER une `PvpGameModeSource` et lui faire produire SA `BattleConfiguration`.
//
// POURQUOI, ET CE QUE CA REMPLACE
// --------------------------------
// Pour debuffer un duel d'Arene il faut NOMMER les unites adverses, donc connaitre la forme
// EXACTE de leurs `unitId` -- `UnitConfigId$$op_Equality` confronte PureId, Rarity, Level ET
// IsBorrowed, et une cible approximative n'apparie RIEN, sans lever, en laissant l'installation
// se declarer `ok`. On l'obtenait en montant un banc SANDBOX puis en relisant le JSON de la BC :
// trois etages de derivation la ou la source sait deja. Ce module DEMANDE A LA SOURCE.
//
// LA SURETE, LUE AU DECOMPILE (`t6dpr4k06g`)
// -------------------------------------------
// `PvpGameModeSource$$LoadBattleInternal` est de la CONSTRUCTION PURE :
//
//     BattleConfigGameConfigValues..ctor  ->  BattleConfigSettings$$FromFeatureToggles
//       -> BattleConfigBuilder..ctor
//       -> AProgressionGameModeSource$$GetEnvironmentAbilitiesFromProgression
//       -> BattleConfigBuilder$$GetPvpLevelConfig(...)   -> range en `_currentBattle`, rend la BC
//
// AUCUN `GenerateNewBattleId`, AUCUN evenement, AUCUN reseau. `isRestart` n'y est meme jamais LU.
//
// ⚠ L'ENREGISTREMENT DE LA TENTATIVE VIT DANS LA METHODE SOEUR, ET ON NE L'APPELLE JAMAIS :
// `PvpGameModeSource$$SendLoadBattleGameEventInternal` appelle `TempBattleData$$GenerateNewBattleId`
// puis dispatche sur `_pvpProgression`. Meme forme que le boss de guilde, ou une tentative
// enregistree puis non terminee est PERDUE sans qu'aucun compteur local ne bouge. Ce module
// n'appelle QUE `LoadBattleInternal` -- jamais `LoadBattle` (la publique de la base, qui peut
// router vers la chaine d'evenements), jamais `StartMatch`.
//
// ⛔ POURQUOI ON PASSE PAR LE CTOR, ET PAS PAR UNE POIGNEE DE CHAMPS — INCIDENT DU 2026-08-23
// -------------------------------------------------------------------------------------------
// Premiere version : on allouait l'objet et on ecrivait les **9 champs que `LoadBattleInternal`
// LIT**, inventaire tire du decompile de cette fonction. Resultat : `NullReferenceException` au
// milieu du graphe, puis **le process est mort**.
//
// La faute de raisonnement, et elle est generale : `LoadBattleInternal` **APPELLE**
// `AProgressionGameModeSource$$GetEnvironmentAbilitiesFromProgression(this, ...)` en lui repassant
// `this`. Ce que ce callee lit sur `this` n'apparait NULLE PART dans le corps qu'on avait lu.
// L'inventaire etait celui d'UNE fonction, pas celui du GRAPHE D'APPEL -- une liste blanche qui
// a l'air complete parce qu'on n'a pas regarde ou il fallait.
//
// ⇒ Le ctor est la seule construction qui rend l'objet coherent pour TOUT le graphe. C'est
//   exactement pour ca que `campaign-source-forge` appelle le sien (17 arguments) au lieu
//   d'ecrire des champs -- patron dont cette premiere version se reclamait sans le suivre.
//
// ⚠ ET L'ORDRE DES PARAMETRES NE SE RECOPIE PAS D'UN DUMP. `sources_win/` date d'un AUTRE build ;
// ses adresses sont 100 % perimees et rien ne garantit l'ordre d'une signature. On resout donc
// chaque argument par le TYPE DECLARE de son parametre, apparie aux champs de `ViewCommandExecutor`
// INDEXES PAR LEUR TYPE. Aucun ordre, aucun nom de champ en dur.

import {
    class_get_name, findClassAnywhere, findCtorByParamCount, findMethodByParamCount, getFieldInfo,
    getFieldOffset, field_get_type, type_get_class_or_element_class, methodParamClass, s as cstr,
} from "../il2cpp/helpers.js";
import { indexerAvecParents, nomDeClasse } from "../il2cpp/champs-par-type.js";
import { il2cpp_object_new, invokeMethod } from "../il2cpp/invoke.js";
import { serializeToJson } from "../il2cpp/serializer.js";
import { gcRoot } from "../il2cpp/gc-root.js";
import { queueOnMainThread } from "../runtime/queue.js";
import { executeurVivant } from "./view-command.js";
import { chargerBcDepuisSource } from "./battle-config.js";
import { lineupDeLaSource } from "../game/source-lineup.js";
import { propositionsChargees } from "./pvp-opponents.js";
import { champInt, champPointeur, champTexte, estRefus, refus } from "./lecture-champs.js";
import { Ctx } from "../controller.js";

const NS_SRC = "IdunBattle.ViewLogic.BattleSource";
const CLS_SRC = "PvpGameModeSource";
const NS_OPP = "IdunMetaLogic.UserProgress.Data.PvP";
const CLS_OPP = "PvpOpponentProgressionData";
/** ⚠ PAS le type que porte `latestOpponents` -- cf. `constuireEncounter`. */
const NS_ENC = "thor.Content";
const CLS_ENC = "PvpEncounter";
const NB_ARGS_CTOR = 15;

let sourceForgee: NativePointer | null = null;
let indexForge: number | null = null;

/** La `PvpGameModeSource` forgee, pour un module qui doit lui DELEGUER un appel (meme raison que
 *  `sourceCampagneForgee` : la sandbox ne fournit pas de roster de deploiement). */
export function sourcePvpForgee(): NativePointer | null {
    return sourceForgee !== null && !sourceForgee.isNull() ? sourceForgee : null;
}

function typeDeclare(klass: NativePointer, nom: string): string | null {
    try {
        const fi = getFieldInfo(klass, nom);
        if (!fi || fi.isNull()) return null;
        const tc = type_get_class_or_element_class(
            field_get_type(fi) as NativePointer) as NativePointer;
        return tc.isNull() ? null : cstr(class_get_name(tc) as NativePointer);
    } catch { return null; }
}

function ecrireChamp(
    obj: NativePointer, klass: NativePointer, cls: string, nom: string, valeur: NativePointer,
): true | ReturnType<typeof refus> {
    const off = getFieldOffset(klass, nom);
    if (off < 0) {
        return refus("`" + cls + "." + nom + "` ABSENT sur ce build -- chemin PERIME, on n'ecrit "
            + "pas a un offset devine");
    }
    try { obj.add(off).writePointer(valeur); }
    catch (e) { return refus("ecriture de `" + nom + "` : " + (e as Error).message); }
    return true;
}

/** L'ENCOUNTER attendu par la source -- ET C'EST UN AUTRE TYPE QUE CE QUE PORTE `latestOpponents`.
 *
 *  ⚠ MESURE (`classFields`, build charge) :
 *    `latestOpponents[]`                   = `PvpEncounterProgressionData` (7 champs, fin a `+0x40`)
 *    `PvpGameModeSource._currentEncounter` = `thor.Content.PvpEncounter`   (18 champs)
 *
 *  Or `LoadBattleInternal` lit `encounter+0x68` (boardId) et `+0x70` (spawnPointsSet) : des offsets
 *  qui tombent HORS de l'objet progression. Y ecrire l'element de `latestOpponents` lirait du
 *  garbage, ou crasherait. La relation est l'INVERSE de l'intuition -- c'est `PvpEncounter` qui
 *  ENVELOPPE la progression (`+0x80 encounterProgressionData`). Un type-guard a attrape ca avant
 *  tout degat ; on FABRIQUE donc le type declare au lieu de forcer l'autre. */
function construireEncounter(
    kSrc: NativePointer, encData: NativePointer, adv: NativePointer,
): { enc: NativePointer } | ReturnType<typeof refus> {
    const kEnc = findClassAnywhere(NS_ENC, CLS_ENC);
    if (!kEnc) return refus("classe `" + NS_ENC + "." + CLS_ENC + "` introuvable");
    const attendu = typeDeclare(kSrc, "_currentEncounter");
    if (attendu !== null && attendu !== CLS_ENC) {
        return refus("`_currentEncounter` est declare `" + attendu + "` et non `" + CLS_ENC
            + "` -- la forme a change sur ce build, on ne fabrique pas un type au hasard");
    }
    const enc = il2cpp_object_new(kEnc) as NativePointer;
    if (enc.isNull()) return refus("allocation de `" + CLS_ENC + "` a rendu NUL");
    gcRoot.add(enc);

    const board = champPointeur(encData, "boardId");
    if (estRefus(board)) return board;
    const sps = champInt(encData, "spawnPointsSet");
    if (sps === null) {
        return refus("`spawnPointsSet` illisible sur la proposition -- on ne pose pas un 0 par "
            + "defaut, il choisirait un autre placement");
    }
    for (const [nom, val] of [
        ["boardId", board as NativePointer],
        ["opponentProgressionData", adv],
        ["encounterProgressionData", encData],
    ] as Array<[string, NativePointer]>) {
        const r = ecrireChamp(enc, kEnc, CLS_ENC, nom, val);
        if (estRefus(r)) return r;
    }
    const offSps = getFieldOffset(kEnc, "spawnPointsSet");
    if (offSps < 0) {
        return refus("`" + CLS_ENC + ".spawnPointsSet` ABSENT sur ce build -- chemin PERIME");
    }
    enc.add(offSps).writeS32(sps);
    return { enc };
}

export function register(ctx: Ctx): void {
    /**
     * FORGER la source du duel d'Arene `n` et en tirer SA `BattleConfiguration`.
     *
     * ⚠ SANS `confirmer`, RIEN N'EST INVOQUE : on rend l'APPARIEMENT des 15 arguments du ctor
     * (type de chaque parametre -> champ de l'executeur retenu), et la liste de ceux qui
     * resteraient NULS. C'est le mode a jouer en premier -- une `NullReferenceException` dans ce
     * graphe a deja tue le process une fois.
     */
    ctx.rpc.pvpSourceForger = (body?: {
        n?: number; confirmer?: boolean; json?: boolean;
    }): Promise<unknown> => queueOnMainThread(() => {
        const n = body?.n ?? 0;

        const kSrc = findClassAnywhere(NS_SRC, CLS_SRC);
        if (!kSrc) return refus("classe `" + NS_SRC + "." + CLS_SRC + "` introuvable");

        // 1. LA PROPOSITION -- foyer PARTAGE avec `pvp-opponents`, jamais une seconde marche.
        const props = propositionsChargees();
        if (estRefus(props)) return props;
        if (props.listeNulle || props.elements.length === 0) {
            return refus("aucune proposition chargee -- ouvrir l'ecran d'Arene (ouvrir ne consomme "
                + "AUCUNE tentative ; seul un combat en consomme)");
        }
        if (n < 0 || n >= props.elements.length) {
            return refus("indice " + n + " hors des " + props.elements.length + " proposition(s)");
        }
        const encData = props.elements[n];
        const adv = champPointeur(encData, "opponent");
        if (estRefus(adv)) return adv;
        if ((adv as NativePointer).isNull()) {
            return refus("proposition " + n + " : son champ `opponent` est NUL");
        }

        // 2. LE CTOR, RESOLU PAR SON ARITE -- et ses parametres lus PAR TYPE.
        const ctor = findCtorByParamCount(kSrc, NB_ARGS_CTOR);
        if (!ctor) {
            return refus("`" + CLS_SRC + "..ctor(" + NB_ARGS_CTOR + " parametres)` INTROUVABLE sur "
                + "ce build -- la signature a change ; on ne devine pas une arite de remplacement");
        }
        const typesAttendus: string[] = [];
        for (let i = 0; i < NB_ARGS_CTOR; i++) {
            const kp = methodParamClass(ctor.info ?? ctor, i);
            typesAttendus.push(kp ? cstr(class_get_name(kp) as NativePointer) : "?");
        }

        // 3. LES SERVICES, INDEXES PAR TYPE sur l'executeur. Aucun nom de champ en dur.
        const exec = executeurVivant();
        if (estRefus(exec)) return exec;
        const kExec = findClassAnywhere("idun.shared.commands", "ViewCommandExecutor");
        if (!kExec) return refus("classe `ViewCommandExecutor` introuvable");
        const parType = indexerAvecParents(exec as NativePointer, kExec);

        // 4. L'ENCOUNTER (type FABRIQUE, cf. le pave de `construireEncounter`).
        const bati = construireEncounter(kSrc, encData, adv as NativePointer);
        if (estRefus(bati)) return bati;
        const enc = bati.enc;

        // 5. L'APPARIEMENT. Type du parametre -> champ de l'executeur. Les cas speciaux sont
        //    NOMMES : l'encounter qu'on vient de batir, et l'executeur lui-meme.
        const args: NativePointer[] = [];
        const appariement: Array<Record<string, unknown>> = [];
        const nuls: string[] = [];
        const ambigus: string[] = [];
        for (let i = 0; i < NB_ARGS_CTOR; i++) {
            const t = typesAttendus[i];
            let val: NativePointer = ptr(0);
            let via = "NUL";
            if (t === CLS_ENC) { val = enc; via = "encounter FABRIQUE"; }
            else if (t === "IViewCommandExecutor" || t === "ViewCommandExecutor") {
                val = exec as NativePointer; via = "l'executeur lui-meme";
            } else {
                const cands = (parType.get(t) ?? []).filter((c) => !c.valeur.isNull());
                if (cands.length === 1) { val = cands[0].valeur; via = cands[0].nom; }
                else if (cands.length > 1) {
                    // ⚠ ON NE CHOISIT PAS. Deux champs du meme type sur l'executeur, c'est une
                    // question a trancher par lecture, pas par ordre de declaration.
                    ambigus.push(t + " {" + cands.map((c) => c.nom).join(", ") + "}");
                    via = "AMBIGU";
                } else nuls.push(t);
            }
            args.push(val);
            appariement.push({ i, type: t, via });
        }
        if (ambigus.length > 0) {
            return refus("plusieurs champs de l'executeur portent le meme type, on ne CHOISIT pas : "
                + ambigus.join(" | "));
        }

        const resume: Record<string, unknown> = {
            ok: true, n, confirme: body?.confirmer === true,
            adversaire: champTexte(adv as NativePointer, "displayName"),
            boardId: champTexte(encData, "boardId"),
            spawnPointsSet: champInt(encData, "spawnPointsSet"),
            appariement, argsNuls: nuls,
        };
        if (body?.confirmer !== true) {
            resume.note = "MODE A BLANC : rien n'a ete invoque. Relire `argsNuls` avant de "
                + "confirmer -- une NullReferenceException dans ce graphe a deja tue le process.";
            return resume;
        }

        // 6. LA CONSTRUCTION PAR LE CTOR.
        const src = il2cpp_object_new(kSrc) as NativePointer;
        if (src.isNull()) return refus("allocation de `" + CLS_SRC + "` a rendu NUL");
        gcRoot.add(src);
        try { invokeMethod(ctor.info ?? ctor, src, args); }
        catch (e) { return refus("`" + CLS_SRC + "..ctor` a LEVE : " + (e as Error).message); }

        // 7. L'EQUIPE ADVERSE. `_opponentLineup` / `_opponentMachineOfWarLineup` ne sont PAS des
        //    arguments du ctor : c'est `PvpOpponentProgressionData$$GetPublicProfileLineup` qui les
        //    materialise depuis le profil public de l'adversaire (rank, xpLevel, upgrades, items
        //    ecrits par le serveur). Passer par NOS identifiants donnerait notre roster portant
        //    leurs noms -- mesure du 2026-08-22, facteur 1 800 sur la puissance, en SA faveur.
        const kOpp = findClassAnywhere(NS_OPP, CLS_OPP);
        if (!kOpp) return refus("classe `" + NS_OPP + "." + CLS_OPP + "` introuvable");
        const mLineup = findMethodByParamCount(kOpp, "GetPublicProfileLineup", 4);
        if (!mLineup) {
            return refus("`" + CLS_OPP + "$$GetPublicProfileLineup(4)` INTROUVABLE -- la signature "
                + "a change ; on ne devine pas une arite de remplacement");
        }
        const mMow = findMethodByParamCount(kOpp, "GetPublicProfileMachineOfWarLineup", 4);
        const unitProg = (parType.get("IUnitProgression") ?? [])[0]?.valeur ?? ptr(0);
        const itemProg = (parType.get("IItemProgression") ?? [])[0]?.valeur ?? ptr(0);
        const logger = (parType.get("IIdunLogger") ?? [])[0]?.valeur ?? ptr(0);

        let lineup: NativePointer;
        try {
            lineup = invokeMethod(mLineup.info, adv as NativePointer,
                                  [unitProg, itemProg, logger, ptr(0)]);
        } catch (e) { return refus("`GetPublicProfileLineup` a LEVE : " + (e as Error).message); }
        if (lineup.isNull()) {
            return refus("`GetPublicProfileLineup` a rendu NUL -- la BC sortirait sans adversaire, "
                + "et rien ne le signalerait");
        }
        gcRoot.add(lineup);

        let mow: NativePointer = ptr(0);
        if (mMow) {
            try {
                mow = invokeMethod(mMow.info, adv as NativePointer,
                                   [unitProg, itemProg, logger, ptr(0)]);
            } catch { mow = ptr(0); }
            if (!mow.isNull()) gcRoot.add(mow);
        }
        for (const [nom, val] of [
            ["_opponentLineup", lineup], ["_opponentMachineOfWarLineup", mow],
        ] as Array<[string, NativePointer]>) {
            const r = ecrireChamp(src, kSrc, CLS_SRC, nom, val);
            if (estRefus(r)) return r;
        }

        // 8. LA CONSTRUCTION DE LA BC. `LoadBattleInternal` est PROTEGEE -- resolue par nom et
        //    arite, jamais par une adresse. Ni `LoadBattle`, ni `StartMatch`.
        const mLoad = findMethodByParamCount(kSrc, "LoadBattleInternal", 1);
        if (!mLoad) {
            return refus("`" + CLS_SRC + "$$LoadBattleInternal(1)` INTROUVABLE -- chemin PERIME");
        }
        const argIsRestart = Memory.alloc(8);
        argIsRestart.writeU8(0);          // jamais LU par ce corps (decompile) -- pose a false.

        // ⛔ LA SOURCE SE DECLARE, SINON LE CIBLAGE `auto=moi` REND ZERO -- EN SILENCE.
        // Le patch d'env-abilities mord dans l'`onLeave` de `LoadBattleInternal`, mais il ne
        // CAPTURE pas l'instance (un `onEnter` sur ce listener le tuerait) : c'est l'appelant qui
        // la DECLARE. Sans ca, `lineupDeLaSource` n'a personne a interroger, `ciblesAuto` rend
        // `0 cible (voie=aucune)` et l'avertissement accuse -- a juste titre -- << la SOURCE n'a
        // pas ete transmise >>. Mesure du 2026-08-24 : les trois enhancements s'installaient avec
        // ZERO cible sur une source PvP forgee, alors que la meme chaine rend 29 cibles sur
        // l'evenement, dont la forge (`mow-event-source-forge`) declare, elle.
        // ⚠ LE `finally` N'EST PAS DECORATIF : une declaration qui survit a l'appel ferait
        // attribuer la PROCHAINE `LoadBattle` -- une vraie, celle du jeu -- a notre source forgee.
        let bc: NativePointer;
        try { bc = chargerBcDepuisSource(mLoad.info, src, [argIsRestart]); }
        catch (e) { return refus("`LoadBattleInternal` a LEVE : " + (e as Error).message); }
        if (bc.isNull()) return refus("`LoadBattleInternal` a rendu une BC NULLE");

        // ⚠ ON VERIFIE CE QU'ON A RECU. Une BC perimee ou un objet d'un autre type est
        // PARFAITEMENT lisible : le type-guard par NOM DE CLASSE separe « construit » de
        // « plausible ».
        const nomBc = nomDeClasse(bc);
        if (nomBc !== "BattleConfiguration") {
            return refus("`LoadBattleInternal` a rendu un `" + (nomBc ?? "?") + "`, pas une "
                + "`BattleConfiguration` -- on ne le rend pas comme un succes");
        }
        gcRoot.add(bc);
        sourceForgee = src;
        indexForge = n;

        resume.srcPtr = src.toString();
        resume.bcPtr = bc.toString();
        resume.mowResolue = !mow.isNull();
        // LA COMPOSITION DU JOUEUR, DEMANDEE A LA SOURCE -- elle n'est PAS dans la BC, qui ne
        // porte que l'adversaire. C'est ce que `ciblesAuto: "moi"` visera, et c'est aussi ce
        // qu'un pilote doit PRE-POSER a l'ecran de deploiement : sans elle il ne peut que
        // demander au lecteur de nommer ses unites a la main.
        //
        // ⚠ EN PvP CETTE VOIE REPOND, et c'est ce qui distingue ce mode de l'evenement Machines
        // of War : la-bas `GetBattleLineup` lit l'etat de RUN et rend `[]` tant qu'aucun run
        // n'est demarre, donc le ciblage retombe TOUJOURS sur le POOL (`voie=deployables`). Ici
        // on obtient la lineup REELLE, MoW comprise -- deux chemins distincts, et le second
        // n'avait jamais ete confronte.
        const lu = lineupDeLaSource(src);
        resume.lineup = {
            classe: lu.classe, places: lu.places, unites: lu.unites, mow: lu.mow,
            voie: lu.voie, refus: lu.refus,
        };
        resume.note = "BC construite par la SOURCE. Aucune tentative enregistree : "
            + "`SendLoadBattleGameEventInternal` (qui appelle `GenerateNewBattleId`) n'a pas ete "
            + "appelee.";
        if (body?.json === true) {
            const j = serializeToJson(bc);
            resume.json = j;
            resume.jsonRefus = j === null
                ? "serialisation Newtonsoft en echec -- le resume reste valable, il ne depend "
                    + "pas d'elle"
                : null;
        }
        return resume;
    });

    /** L'etat de la forge -- `null` = rien de forge, jamais a lire comme « echec ». */
    ctx.rpc.pvpSourceForgeEtat = (): unknown => ({
        ok: true,
        forgee: sourceForgee !== null && !sourceForgee.isNull() ? sourceForgee.toString() : null,
        n: indexForge,
    });
}
