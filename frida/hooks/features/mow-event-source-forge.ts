// mow-event-source-forge — FORGER une `MachinesOfWarEventGameModeSource` (l'evenement INCURSION)
// et lui faire produire SA `BattleConfiguration`, sans jeton et sans naviguer.
//
// POURQUOI, ET CE QUE CA REMPLACE
// --------------------------------
// `mow-builder` CAPTURE la source, au vol, par un hook sur son ctor : il faut donc naviguer
// jusqu'a l'evenement ET avoir arme le hook avant que Zenject ne construise. Deux conditions
// qu'on ne peut pas tenir depuis un test. Ce module la CONSTRUIT, comme `pvp-source-forge` et
// `campaign-source-forge` le font pour leurs modes -- et c'est ce qui rend une battle de l'event
// montable a la demande, donc patchable (le patch d'env-ability s'ancre deja sur
// `MachinesOfWarEventGameModeSource$$LoadBattleInternal`, l'une des 17 sources).
//
// LA CHAINE, LUE AU DECOMPILE (`t6dpr4k06g`)
// -------------------------------------------
// Elle est celle que le jeu joue lui-meme, MOINS sa derniere marche :
//
//   ShowMachinesOfWarEventBattlePreviewPopupCommand$$OnPlayBattleTapped
//     -> ...$$CreateBattleData(tierIndex, nodeOrBattleIndex, isV2)   <- CE MODULE VA JUSQU'ICI
//     -> ViewCommandExecutor$$StartMachinesOfWarEventMatch(battleData)
//          -> MachinesOfWarEventGameModeSource..ctor(16 arguments)   <- ET IL LE REFAIT
//          -> ViewCommandExecutor$$StartMatch(...)                   <- JAMAIS APPELE ICI
//
// ⚠ LA FRONTIERE DU COUT EST `StartMatch`, PAS `CreateBattleData`. Le corps de `CreateBattleData`
// ne fait que LIRE la progression (getters d'interface), allouer un dictionnaire de PV et
// construire l'enregistrement : aucun `Send*`, aucun `StartBattle`, aucun `GenerateNewBattleId`,
// aucune depense. Ce qui engage le jeton vit dans `IMachinesOfWarEventProgression$$StartBattle`,
// atteint par `SendLoadBattleGameEventInternal` -- la methode SOEUR de celle qu'on appelle.
//
// `MachinesOfWarEventGameModeSource$$LoadBattleInternal` est de la CONSTRUCTION PURE, meme forme
// que le duel d'Arene :
//
//     BattleConfigGameConfigValues..ctor  ->  BattleConfigSettings$$FromFeatureToggles
//       -> BattleConfigBuilder..ctor
//       -> AProgressionGameModeSource$$GetEnvironmentAbilitiesFromProgression(this)
//       -> BattleConfigBuilder$$GetMachinesOfWarEventConfig(...)  -> range en `_currentBattle`
//
// ⚠ MAIS `isRestart` Y EST LU, CONTRAIREMENT AU DUEL D'ARENE : a `true` il rappelle
// `CreateOpponentLineup(this, battleData.Enemies)`. On passe `false` parce que **le ctor l'a deja
// appele** (mesure au decompile : `..ctor` fait `CreateOpponentLineup(this, eventBattleData+0x40)`
// avant de rendre la main). Un `true` ne serait pas faux, juste redondant.
//
// ⛔ POURQUOI LE CTOR, ET PAS UNE POIGNEE DE CHAMPS — L'INCIDENT DU 2026-08-23 VAUT ICI AUSSI.
// Ecrire « les champs que `LoadBattleInternal` lit » a tue le process une fois : cette fonction
// repasse `this` a `GetEnvironmentAbilitiesFromProgression`, dont les lectures n'apparaissent
// nulle part dans le corps qu'on avait inventorie. Le ctor est la seule construction coherente
// pour TOUT le graphe d'appel.
//
// ⚠ ET LES ARGUMENTS NE SE RECOPIENT PAS D'UN DUMP : chacun est resolu par le TYPE DECLARE de son
// parametre (`champs-par-type`). Deux cas que le seul NOM de type ne tranche pas, et qui sont
// traites nommement :
//   - `IMenu<UnitDeploymentHud>` et `IMenu<IdunGameHud>` portent le meme nom court et ne vivent
//     PAS sur l'executeur mais sur son `MenuSystems` -> le pool est l'union des deux, et
//     l'appariement passe par le POINTEUR DE CLASSE avant le nom.
//   - `GameConfigDto` n'est champ de personne : l'executeur porte un `IGameConfigData`, et le dto
//     s'obtient par son accesseur. `GlobalValuesDTO` est ensuite un champ DE CE DTO.

import {
    class_get_name, findClassAnywhere, findCtorByParamCount, findMethod, findMethodByParamCount,
    getFieldOffset, methodParamClass, readIl2cppString, s as cstr,
} from "../il2cpp/helpers.js";
import { indexerAvecParents, nomDeClasse } from "../il2cpp/champs-par-type.js";
import { il2cpp_object_new, invokeMethod } from "../il2cpp/invoke.js";
import { serializeToJson } from "../il2cpp/serializer.js";
import { gcRoot } from "../il2cpp/gc-root.js";
import { queueOnMainThread } from "../runtime/queue.js";
import { executeurVivant } from "./view-command.js";
import {
    champBool, champInt, champPointeur, champTexte, elementsDeListe, estRefus, refus,
} from "./lecture-champs.js";
import { Ctx } from "../controller.js";

const NS_SRC = "IdunBattle.ViewLogic.BattleSource";
const CLS_SRC = "MachinesOfWarEventGameModeSource";
const CLS_DATA = "MachinesOfWarEventBattleData";
const NS_CMD = "idun.shared.commands";
const CLS_CMD = "ShowMachinesOfWarEventBattlePreviewPopupCommand";
const NB_ARGS_CMD = 8;
const NB_ARGS_SRC = 16;

let sourceForgee: NativePointer | null = null;
let derniereCle: { tier: number; node: number; isV2: boolean } | null = null;

/** La source d'evenement forgee, pour un module qui doit lui DELEGUER un appel (le roster de
 *  deploiement, la lineup -- cf. `game/source-lineup.ts`). `null` = rien de forge. */
export function sourceMowEventForgee(): NativePointer | null {
    return sourceForgee !== null && !sourceForgee.isNull() ? sourceForgee : null;
}

interface Candidat { nom: string; valeur: NativePointer; klass: NativePointer; source: string; }

/** Un entier passe a `runtime_invoke` : un pointeur VERS la valeur, jamais la valeur. */
function argInt(v: number): NativePointer {
    const p = Memory.alloc(8);
    p.writeS32(v);
    return p;
}

function argBool(v: boolean): NativePointer {
    const p = Memory.alloc(8);
    p.writeU8(v ? 1 : 0);
    return p;
}

/** La valeur d'un retour de type VALEUR.
 *
 *  ⚠ `runtime_invoke` BOXE les types valeur : le pointeur rendu designe l'en-tete de la boxe, et
 *  la valeur vit a `+0x10`. Lire le pointeur tel quel rendrait une adresse pour un booleen. */
function retourBool(p: NativePointer): boolean | null {
    if (p.isNull()) return null;
    try { return p.add(0x10).readU8() !== 0; } catch { return null; }
}

function retourInt(p: NativePointer): number | null {
    if (p.isNull()) return null;
    try { return p.add(0x10).readS32(); } catch { return null; }
}

/** Un champ d'un RECORD C#, par le nom de son PARAMETRE.
 *
 *  ⚠ Le nom du parametre positionnel N'EST PAS le nom du champ : le compilateur genere
 *  `<Nom>k__BackingField`. Mesure du 2026-08-24 -- lire `BoardId` sur le
 *  `MachinesOfWarEventBattleData` rendait `null`, ce qui se lit « pas de board » alors que
 *  c'etait « pas ce nom-la ». On essaie les deux formes, et `null` reste `null` : PAS MESURE. */
function champRecord(obj: NativePointer, nom: string): NativePointer | null {
    const direct = champPointeur(obj, nom);
    if (!estRefus(direct) && !(direct as NativePointer).isNull()) return direct as NativePointer;
    const back = champPointeur(obj, "<" + nom + ">k__BackingField");
    if (!estRefus(back) && !(back as NativePointer).isNull()) return back as NativePointer;
    return null;
}

function champRecordTexte(obj: NativePointer, nom: string): string | null {
    return champTexte(obj, nom) ?? champTexte(obj, "<" + nom + ">k__BackingField");
}

function champRecordInt(obj: NativePointer, nom: string): number | null {
    const v = champInt(obj, nom);
    return v !== null ? v : champInt(obj, "<" + nom + ">k__BackingField");
}

/** La taille d'une `List<T>` portee par un champ de record. `null` = PAS MESURE. */
function tailleListeRecord(obj: NativePointer, nom: string): number | null {
    const l = champRecord(obj, nom);
    return l === null ? null : champInt(l, "_size");
}

/** Le POOL de services : les champs de l'executeur, PLUS ceux de son `MenuSystems`.
 *
 *  ⚠ L'union n'est pas un confort : `deploymentHud` et `gameHud` ne sont PAS des champs de
 *  l'executeur -- `StartMachinesOfWarEventMatch` les lit sur l'objet `MenuSystems` qu'il porte.
 *  Un pool limite a l'executeur les rendrait NULS en silence. */
function poolDeServices(exec: NativePointer): { pool: Candidat[]; menuSystems: string | null } {
    const pool: Candidat[] = [];
    const kExec = findClassAnywhere(NS_CMD, "ViewCommandExecutor");
    let nomMenuSystems: string | null = null;
    if (kExec) {
        for (const [, liste] of indexerAvecParents(exec, kExec)) {
            for (const c of liste) pool.push({ ...c, source: "executeur" });
        }
    }
    const ms = pool.find((c) => cstr(class_get_name(c.klass) as NativePointer) === "MenuSystems"
        && !c.valeur.isNull());
    if (ms) {
        nomMenuSystems = ms.nom;
        const kMs = ms.valeur.readPointer();   // classe REELLE de l'instance, pas la declaree
        if (!kMs.isNull()) {
            for (const [, liste] of indexerAvecParents(ms.valeur, kMs)) {
                for (const c of liste) pool.push({ ...c, source: "menuSystems" });
            }
        }
    }
    return { pool, menuSystems: nomMenuSystems };
}

/** Le `GameConfigDto` vivant. Il n'est champ de personne : l'executeur porte l'INTERFACE
 *  `IGameConfigData`, et le dto s'obtient par son accesseur -- exactement ce que fait
 *  `StartMachinesOfWarEventMatch` au decompile.
 *
 *  ⚠ On l'INVOQUE une fois ; on ne l'ANCRE jamais. `GameConfigData$$get_gameConfigDto` est appele
 *  ~27 000 fois/s par les serialisations Newtonsoft du jeu, et un hook permanent dessus met la
 *  frame au-dessus de 960 ms -- crash. */
function gameConfigDto(pool: Candidat[]): NativePointer | ReturnType<typeof refus> {
    const direct = pool.find((c) =>
        cstr(class_get_name(c.klass) as NativePointer) === "GameConfigDto" && !c.valeur.isNull());
    if (direct) return direct.valeur;

    const porteurs = pool.filter((c) => {
        const t = cstr(class_get_name(c.klass) as NativePointer);
        return (t === "IGameConfigData" || t === "GameConfigData") && !c.valeur.isNull();
    });
    if (porteurs.length === 0) {
        return refus("aucun champ `IGameConfigData` sur l'executeur -- le `GameConfigDto` du ctor "
            + "resterait NUL, et le graphe leverait au milieu");
    }
    for (const p of porteurs) {
        const kReel = p.valeur.readPointer();
        if (kReel.isNull()) continue;
        const m = findMethod(kReel, "get_gameConfigDto");
        if (!m) continue;
        try {
            const dto = invokeMethod(m.info, p.valeur, null);
            if (!dto.isNull()) return dto;
        } catch { /* porteur suivant */ }
    }
    return refus("`get_gameConfigDto` introuvable ou en echec sur les " + porteurs.length
        + " porteur(s) `IGameConfigData` -- chemin PERIME, on ne devine pas un offset");
}

/** L'EXECUTEUR PRIME SUR SON `MenuSystems` -- et ce n'est pas un depart au hasard, c'est ce que
 *  fait le natif. `StartMachinesOfWarEventMatch` lit ses SEIZE arguments sur l'executeur, a DEUX
 *  exceptions qu'il indirecte explicitement par `MenuSystems` : les deux huds. Le `MenuSystems`
 *  n'est donc pas une seconde source d'egale valeur, c'est un COMPLEMENT.
 *
 *  ⚠ Mesure du 2026-08-24 : sans cette priorite, `IIdunLogger` sort ambigu
 *  (`executeur._logger` / `menuSystems._logger`) et la forge REFUSE -- alors que le decompile
 *  designe le premier sans hesiter (`logger = *(exec + 0x5b8)`). L'ambiguite reste un refus
 *  A L'INTERIEUR d'une meme source : deux champs du meme type sur l'executeur, ca se tranche
 *  par lecture, pas par ordre de declaration. */
function prioriser(cands: Candidat[]): Candidat[] {
    const surExecuteur = cands.filter((c) => c.source === "executeur");
    return surExecuteur.length > 0 ? surExecuteur : cands;
}

/** APPARIER les parametres d'un ctor au pool, PAR TYPE.
 *
 *  L'ordre de resolution : cas nomme -> POINTEUR de classe -> NOM de type. Le pointeur passe en
 *  premier parce que c'est le seul qui separe deux instanciations d'un meme generique. Une
 *  ambiguite qui survit aux deux est un REFUS : deux champs du meme type, c'est une question a
 *  trancher par lecture, pas par ordre de declaration. */
function apparier(
    ctor: NativePointer, nbArgs: number, pool: Candidat[],
    nommes: Map<string, { valeur: NativePointer; via: string }>,
): {
    args: NativePointer[];
    appariement: Array<Record<string, unknown>>;
    nuls: string[];
    ambigus: string[];
} {
    const args: NativePointer[] = [];
    const appariement: Array<Record<string, unknown>> = [];
    const nuls: string[] = [];
    const ambigus: string[] = [];

    for (let i = 0; i < nbArgs; i++) {
        const kp = methodParamClass(ctor, i);
        const t = kp ? cstr(class_get_name(kp) as NativePointer) : "?";
        const nomme = nommes.get(t);
        if (nomme) {
            args.push(nomme.valeur);
            appariement.push({ i, type: t, via: nomme.via, source: "nomme" });
            if (nomme.valeur.isNull()) nuls.push(t);
            continue;
        }
        let cands: Candidat[] = [];
        if (kp) {
            cands = prioriser(pool.filter((c) => c.klass.equals(kp) && !c.valeur.isNull()));
        }
        let par = "pointeur de classe";
        if (cands.length === 0) {
            cands = prioriser(pool.filter((c) =>
                cstr(class_get_name(c.klass) as NativePointer) === t && !c.valeur.isNull()));
            par = "nom de type";
        }
        if (cands.length === 1) {
            args.push(cands[0].valeur);
            appariement.push({ i, type: t, via: cands[0].nom, source: cands[0].source, par });
        } else if (cands.length > 1) {
            ambigus.push(t + " {" + cands.map((c) => c.source + "." + c.nom).join(", ") + "}");
            args.push(ptr(0));
            appariement.push({ i, type: t, via: "AMBIGU", source: null, par });
        } else {
            nuls.push(t);
            args.push(ptr(0));
            appariement.push({ i, type: t, via: "NUL", source: null, par: null });
        }
    }
    return { args, appariement, nuls, ambigus };
}

/** CLONER la liste d'ennemis en leur POSANT des PV — pour un banc, et rien d'autre.
 *
 * ⚠ HARDCODE (test) ASSUME ET SIGNALE : les PV adverses reels vivent dans l'etat de RUN, et sans
 * run demarre ils valent 0 (`MaxHealth` comme `RemainingHealth`). Or `CreateOpponentLineup`
 * FILTRE tout ennemi a 0 PV, donc la BC sort sans adversaire. La valeur posee ici est INVENTEE :
 * elle rend la bataille montable pour eprouver un patch, elle ne reproduit PAS le combat reel.
 * Ne jamais s'en servir pour comparer des degats a une partie jouee.
 *
 * ⚠ ON CLONE, ON NE MUTE PAS. Les `UnitModelWithHealth` rendus par la progression peuvent etre
 * ses propres objets : y ecrire des PV changerait ce que l'ecran de l'evenement affiche. Le
 * record, lui, est a NOUS -- on lui donne une liste neuve. Aucune ecriture hors de nos objets.
 */
function clonerEnnemisAvecPv(
    data: NativePointer, pv: number,
): { poses: number } | ReturnType<typeof refus> {
    const liste = champRecord(data, "Enemies");
    if (liste === null) return refus("`Enemies` illisible sur l'enregistrement de bataille");
    const kListe = liste.readPointer();
    if (kListe.isNull()) return refus("classe de la liste `Enemies` illisible");
    const els = elementsDeListe(liste);
    if (estRefus(els)) return els;

    const ctor0 = findCtorByParamCount(kListe, 0);
    const mAdd = findMethodByParamCount(kListe, "Add", 1);
    if (!ctor0 || !mAdd) {
        return refus("`List<UnitModelWithHealth>` sans `.ctor(0)` ou sans `Add(1)` sur ce build "
            + "-- chemin PERIME, on ne fabrique pas une liste a la main");
    }
    const neuve = il2cpp_object_new(kListe) as NativePointer;
    if (neuve.isNull()) return refus("allocation de la liste d'ennemis a rendu NUL");
    gcRoot.add(neuve);
    try { invokeMethod(ctor0.info, neuve, null); }
    catch (e) { return refus("`List..ctor()` a LEVE : " + (e as Error).message); }

    const CHAMPS = ["UnitModel", "IsNpc", "MaxHealth", "RemainingHealth", "Power"];
    let poses = 0;
    for (const e of els) {
        const kE = e.readPointer();
        if (kE.isNull()) continue;
        const copie = il2cpp_object_new(kE) as NativePointer;
        if (copie.isNull()) continue;
        gcRoot.add(copie);
        for (const nom of CHAMPS) {
            const off = getFieldOffset(kE, nom);
            if (off < 0) {
                return refus("`UnitModelWithHealth." + nom + "` ABSENT sur ce build -- on ne "
                    + "recopie pas a un offset devine");
            }
            if (nom === "UnitModel") copie.add(off).writePointer(e.add(off).readPointer());
            else if (nom === "IsNpc") copie.add(off).writeU8(e.add(off).readU8());
            else copie.add(off).writeS32(e.add(off).readS32());
        }
        for (const nom of ["MaxHealth", "RemainingHealth"]) {
            copie.add(getFieldOffset(kE, nom)).writeS32(pv);
        }
        try { invokeMethod(mAdd.info, neuve, [copie]); }
        catch (er) { return refus("`List.Add` a LEVE : " + (er as Error).message); }
        poses++;
    }

    // Le champ du RECORD, ecrit sur NOTRE objet. Nom de parametre puis nom de champ genere.
    const kData = data.readPointer();
    let off = getFieldOffset(kData, "<Enemies>k__BackingField");
    if (off < 0) off = getFieldOffset(kData, "Enemies");
    if (off < 0) {
        return refus("champ `Enemies` introuvable sur l'enregistrement -- chemin PERIME");
    }
    data.add(off).writePointer(neuve);
    return { poses };
}

/** La progression de l'evenement, prise dans le pool. */
function progression(pool: Candidat[]): NativePointer | ReturnType<typeof refus> {
    const c = pool.find((x) => {
        const t = cstr(class_get_name(x.klass) as NativePointer);
        return (t === "IMachinesOfWarEventProgression" || t === "MachinesOfWarEventProgression")
            && !x.valeur.isNull();
    });
    if (!c) {
        return refus("aucun champ `IMachinesOfWarEventProgression` sur l'executeur -- ce build "
            + "n'expose pas l'evenement Machines of War par cette voie");
    }
    return c.valeur;
}

/** `IsV2()` lu sur la progression -- le seul discriminant entre les deux barèmes de noeuds.
 *  `false` par defaut est ASSUME et DIT : un `IsV2` illisible fait retomber sur la voie V1, qui
 *  est celle des builds anterieurs ; l'appelant voit `isV2` dans la reponse. */
function isV2Ici(prog: NativePointer): boolean {
    const k = prog.readPointer();
    if (k.isNull()) return false;
    const m = findMethodByParamCount(k, "IsV2", 0);
    if (!m) return false;
    try {
        const r = invokeMethod(m.info, prog, null);
        return retourBool(r) === true;
    } catch { return false; }
}

/** Invoquer une methode SANS argument de la progression, resolue PAR NOM sur sa classe REELLE.
 *  Jamais par indice de slot : un slot est un ordinal, il glisse d'un build a l'autre en silence. */
function surProgression(
    prog: NativePointer, nom: string, args: NativePointer[] | null, nbArgs: number,
): NativePointer | null {
    const k = prog.readPointer();
    if (k.isNull()) return null;
    const m = findMethodByParamCount(k, nom, nbArgs);
    if (!m) return null;
    try { return invokeMethod(m.info, prog, args); } catch { return null; }
}

export function register(ctx: Ctx): void {
    /**
     * L'ETAT de l'evenement Machines of War (Incursion) -- LECTURE PURE, rien n'est invoque
     * d'autre que des accesseurs.
     *
     * Il existe pour repondre a « quels (tier, node) sont montables ? », question dont la forge
     * a besoin et que rien d'autre ne publie. Tri-etat partout : `null` = PAS MESURE, jamais un
     * zero -- un `0` de complaisance sur `tiers` se lirait « aucun evenement » alors qu'il ne
     * dirait que l'echec de la lecture.
     */
    ctx.rpc.mowEventEtat = (body?: { tier?: number }): Promise<unknown> =>
        queueOnMainThread(() => {
            const exec = executeurVivant();
            if (estRefus(exec)) return exec;
            const { pool, menuSystems } = poolDeServices(exec as NativePointer);
            const prog = progression(pool);
            if (estRefus(prog)) return prog;

            const tiers = surProgression(prog as NativePointer, "GetTiers", null, 0);
            const tier = body?.tier;
            const profondeur = tier === undefined ? null
                : retourInt(surProgression(prog as NativePointer, "GetMaxNodeDepth",
                                           [argInt(tier), argBool(false)], 2) ?? ptr(0));
            const chosen = surProgression(prog as NativePointer, "GetChosenUnit", null, 0);

            // LES NOEUDS DU TIER, ET LEQUEL EST UN COMBAT. Sans ca, choisir un `node` est un
            // tirage : un noeud d'amelioration ou de coffre fait sortir une BC complete mais
            // SANS ADVERSAIRE, et rien ne le signale. `GetBattleConfigV2` rend NUL sur un noeud
            // qui n'est pas une bataille -- c'est le discriminant, et il est LU, pas devine.
            let noeuds: Array<Record<string, unknown>> | null = null;
            if (tier !== undefined && profondeur !== null) {
                const nomConf = isV2Ici(prog as NativePointer)
                    ? "GetBattleConfigV2" : "GetBattleConfig";
                noeuds = [];
                for (let n = 0; n <= profondeur; n++) {
                    const c = surProgression(prog as NativePointer, nomConf,
                                             [argInt(tier), argInt(n)], 2);
                    noeuds.push({ node: n, bataille: c !== null && !c.isNull() });
                }
            }

            return {
                ok: true,
                menuSystems,
                deverrouille: retourBool(
                    surProgression(prog as NativePointer, "IsUnlocked", null, 0) ?? ptr(0)),
                isV2: retourBool(
                    surProgression(prog as NativePointer, "IsV2", null, 0) ?? ptr(0)),
                uniteChoisie: chosen && !chosen.isNull() ? readIl2cppString(chosen) : null,
                tierMaxAtteint: retourInt(
                    surProgression(prog as NativePointer,
                                   "GetHighestReachedTierForChosenUnit", null, 0) ?? ptr(0)),
                tiers: tiers && !tiers.isNull() ? champInt(tiers, "_size") : null,
                tierInterroge: tier ?? null,
                profondeurMaxDuTier: profondeur,
                runDemarre: tier === undefined ? null : retourBool(
                    surProgression(prog as NativePointer, "IsRunStarted",
                                   [argInt(tier)], 1) ?? ptr(0)),
                noeuds,
                noeudsDeCombat: noeuds === null ? null
                    : noeuds.filter((n) => n.bataille === true).map((n) => n.node),
                note: "`tiers` et `profondeurMaxDuTier` bornent les (tier, node) que `CreateBattleData` "
                    + "sait construire. Une valeur `null` est une lecture MANQUEE, pas un zero.",
            };
        });

    /**
     * FORGER la source de l'evenement pour le couple (tier, node) et en tirer SA
     * `BattleConfiguration`.
     *
     * ⚠ SANS `confirmer`, RIEN N'EST INVOQUE : on rend l'APPARIEMENT des arguments des DEUX ctors
     * (type du parametre -> champ retenu, et d'ou il vient) plus la liste de ceux qui resteraient
     * NULS. C'est le mode a jouer en premier -- une `NullReferenceException` dans ce graphe a
     * deja tue le process une fois.
     *
     * `isV2` n'est PAS a fournir : il se lit sur la progression (`IsV2()`), parce que c'est ce
     * que fait `OnPlayBattleTapped`, et parce qu'un mauvais choix fait prendre a
     * `CreateBattleData` l'autre bras de lecture des tiers -- silencieusement.
     */
    ctx.rpc.mowEventSourceForger = (body?: {
        tier?: number; node?: number; isV2?: boolean; pvEnnemis?: number;
        confirmer?: boolean; json?: boolean;
    }): Promise<unknown> => queueOnMainThread(() => {
        const tier = body?.tier ?? 0;
        const node = body?.node ?? 0;

        const kSrc = findClassAnywhere(NS_SRC, CLS_SRC);
        if (!kSrc) return refus("classe `" + NS_SRC + "." + CLS_SRC + "` introuvable");
        const kCmd = findClassAnywhere(NS_CMD, CLS_CMD);
        if (!kCmd) return refus("classe `" + NS_CMD + "." + CLS_CMD + "` introuvable");

        const ctorSrc = findCtorByParamCount(kSrc, NB_ARGS_SRC);
        if (!ctorSrc) {
            return refus("`" + CLS_SRC + "..ctor(" + NB_ARGS_SRC + " parametres)` INTROUVABLE sur "
                + "ce build -- la signature a change ; on ne devine pas une arite de remplacement");
        }
        const ctorCmd = findCtorByParamCount(kCmd, NB_ARGS_CMD);
        if (!ctorCmd) {
            return refus("`" + CLS_CMD + "..ctor(" + NB_ARGS_CMD + " parametres)` INTROUVABLE sur "
                + "ce build -- chemin PERIME");
        }
        const mCreate = findMethodByParamCount(kCmd, "CreateBattleData", 3);
        if (!mCreate) {
            return refus("`" + CLS_CMD + "$$CreateBattleData(3)` INTROUVABLE -- c'est LUI qui "
                + "construit l'enregistrement de bataille ; sans lui on ne forge rien");
        }
        const mLoad = findMethodByParamCount(kSrc, "LoadBattleInternal", 1);
        if (!mLoad) {
            return refus("`" + CLS_SRC + "$$LoadBattleInternal(1)` INTROUVABLE -- chemin PERIME");
        }

        const exec = executeurVivant();
        if (estRefus(exec)) return exec;
        const { pool, menuSystems } = poolDeServices(exec as NativePointer);
        const prog = progression(pool);
        if (estRefus(prog)) return prog;

        const dto = gameConfigDto(pool);
        if (estRefus(dto)) return dto;
        // `GlobalValuesDTO` est un champ DU DTO, pas de l'executeur -- meme geste, autre instance.
        const kDto = (dto as NativePointer).readPointer();
        const champsDto = kDto.isNull()
            ? new Map<string, Array<{ nom: string; valeur: NativePointer; klass: NativePointer }>>()
            : indexerAvecParents(dto as NativePointer, kDto);
        const gv = (champsDto.get("GlobalValuesDTO") ?? []).find((c) => !c.valeur.isNull());

        const nommesCmd = new Map<string, { valeur: NativePointer; via: string }>([
            ["IViewCommandExecutor", { valeur: exec as NativePointer, via: "l'executeur lui-meme" }],
            ["ViewCommandExecutor", { valeur: exec as NativePointer, via: "l'executeur lui-meme" }],
            ["GlobalValuesDTO", {
                valeur: gv ? gv.valeur : ptr(0),
                via: gv ? "gameConfigDto." + gv.nom : "NUL (absent du GameConfigDto)",
            }],
        ]);
        const apCmd = apparier(ctorCmd.info, NB_ARGS_CMD, pool, nommesCmd);

        // L'`isV2` se LIT ; il n'est demande que pour pouvoir forcer une contre-mesure.
        const isV2Lu = retourBool(
            surProgression(prog as NativePointer, "IsV2", null, 0) ?? ptr(0));
        if (isV2Lu === null && body?.isV2 === undefined) {
            return refus("`IMachinesOfWarEventProgression$$IsV2()` illisible et aucun `isV2` "
                + "fourni -- les deux bras de `CreateBattleData` lisent des tiers DIFFERENTS, "
                + "on ne joue pas a pile ou face");
        }
        const isV2 = body?.isV2 ?? (isV2Lu as boolean);

        const resume: Record<string, unknown> = {
            ok: true, tier, node, isV2, isV2Lu, isV2Force: body?.isV2 !== undefined,
            confirme: body?.confirmer === true,
            menuSystems,
            appariementCommande: apCmd.appariement,
            argsNulsCommande: apCmd.nuls,
            arite: { commande: NB_ARGS_CMD, source: NB_ARGS_SRC },
        };
        if (apCmd.ambigus.length > 0) {
            return refus("plusieurs champs portent le meme type pour le ctor de `" + CLS_CMD
                + "`, on ne CHOISIT pas : " + apCmd.ambigus.join(" | "));
        }

        // L'APPARIEMENT DE LA SOURCE se rend DES le mode a blanc -- mais le `battleData` n'existe
        // pas encore, donc son emplacement est annonce sans valeur. C'est la seule case qui
        // differe entre le blanc et le confirme.
        const nommesSrc = new Map<string, { valeur: NativePointer; via: string }>([
            ["IViewCommandExecutor", { valeur: exec as NativePointer, via: "l'executeur lui-meme" }],
            ["ViewCommandExecutor", { valeur: exec as NativePointer, via: "l'executeur lui-meme" }],
            ["GameConfigDto", { valeur: dto as NativePointer, via: "get_gameConfigDto()" }],
            [CLS_DATA, { valeur: ptr(0), via: "battleData (construit a la confirmation)" }],
        ]);
        const apSrcBlanc = apparier(ctorSrc.info, NB_ARGS_SRC, pool, nommesSrc);
        resume.appariementSource = apSrcBlanc.appariement;
        resume.argsNulsSource = apSrcBlanc.nuls.filter((t) => t !== CLS_DATA);
        if (apSrcBlanc.ambigus.length > 0) {
            return refus("plusieurs champs portent le meme type pour le ctor de `" + CLS_SRC
                + "`, on ne CHOISIT pas : " + apSrcBlanc.ambigus.join(" | "));
        }

        if (body?.confirmer !== true) {
            resume.note = "MODE A BLANC : rien n'a ete invoque. Relire `argsNulsSource` et "
                + "`argsNulsCommande` avant de confirmer -- une NullReferenceException dans ce "
                + "graphe a deja tue le process. Aucun jeton n'est engage meme en confirmant : "
                + "on s'arrete avant `StartMatch`.";
            return resume;
        }

        // 1. LA COMMANDE DE PREVIEW -- on ne l'utilise QUE pour son `CreateBattleData`. Son
        //    `Execute` ouvre un popup et masque l'ecran courant : jamais appele.
        const cmd = il2cpp_object_new(kCmd) as NativePointer;
        if (cmd.isNull()) return refus("allocation de `" + CLS_CMD + "` a rendu NUL");
        gcRoot.add(cmd);
        try { invokeMethod(ctorCmd.info, cmd, apCmd.args); }
        catch (e) { return refus("`" + CLS_CMD + "..ctor` a LEVE : " + (e as Error).message); }

        // 2. L'ENREGISTREMENT DE BATAILLE.
        let data: NativePointer;
        try {
            data = invokeMethod(mCreate.info, cmd, [argInt(tier), argInt(node), argBool(isV2)]);
        } catch (e) { return refus("`CreateBattleData` a LEVE : " + (e as Error).message); }
        if (data.isNull()) {
            return refus("`CreateBattleData(" + tier + ", " + node + ", isV2=" + isV2 + ")` a rendu "
                + "NUL. Les trois causes, au decompile : aucun evenement Machines of War ACTIF "
                + "(le `LiveEventId` courant n'a pas de valeur), le couple (tier, node) hors du "
                + "bareme, ou -- en V2 -- aucune configuration de bataille a ce noeud. Lire "
                + "`mowEventEtat {tier}` pour les bornes.");
        }
        // ⚠ TYPE-GUARD. Un corps trivial deduplique rend un objet d'un AUTRE type sans lever, et
        // il est parfaitement lisible : le nom de classe est ce qui separe « construit » de
        // « plausible ».
        const nomData = nomDeClasse(data);
        if (nomData !== CLS_DATA) {
            return refus("`CreateBattleData` a rendu un `" + (nomData ?? "?") + "`, pas un `"
                + CLS_DATA + "` -- on ne le rend pas comme un succes");
        }
        gcRoot.add(data);

        // 2bis. LES PV DES ENNEMIS -- LUS D'ABORD, ce qui est la seule facon de dire si le
        //       remplissage a servi ou masque quelque chose.
        const pvAvant: Array<Record<string, unknown>> = [];
        let vivantsAvant: number | null = null;
        const listeAvant = champRecord(data, "Enemies");
        if (listeAvant !== null) {
            const els = elementsDeListe(listeAvant);
            if (!estRefus(els)) {
                vivantsAvant = 0;
                for (const e of els) {
                    const restant = champInt(e, "RemainingHealth");
                    pvAvant.push({
                        max: champInt(e, "MaxHealth"), restant,
                        npc: champBool(e, "IsNpc"), puissance: champInt(e, "Power"),
                    });
                    if (restant !== null && restant > 0) vivantsAvant++;
                }
            }
        }
        resume.ennemisVivantsAvant = vivantsAvant;
        resume.ennemisPvAvant = pvAvant;

        // ⚠ LE REMPLISSAGE EST OPT-IN, ET IL FABRIQUE. Il doit passer AVANT le ctor : c'est LUI
        // qui appelle `CreateOpponentLineup`, donc apres il serait trop tard et rien ne le dirait.
        if (typeof body?.pvEnnemis === "number" && body.pvEnnemis > 0) {
            const r = clonerEnnemisAvecPv(data, body.pvEnnemis);
            if (estRefus(r)) return r;
            resume.pvFabriques = body.pvEnnemis;
            resume.ennemisRemplis = r.poses;
            resume.pvFabriquesNote = "PV INVENTES pour rendre la bataille montable : les vrais "
                + "viennent de l'etat de RUN. Ce banc eprouve un patch, il ne reproduit PAS le "
                + "combat reel -- ne pas en tirer de comparaison de degats.";
        }

        // 3. LA SOURCE, PAR SON CTOR. Il appelle lui-meme `CreateOpponentLineup(battleData.Enemies)`.
        nommesSrc.set(CLS_DATA, { valeur: data, via: "battleData construit" });
        const apSrc = apparier(ctorSrc.info, NB_ARGS_SRC, pool, nommesSrc);
        resume.appariementSource = apSrc.appariement;
        resume.argsNulsSource = apSrc.nuls;
        const src = il2cpp_object_new(kSrc) as NativePointer;
        if (src.isNull()) return refus("allocation de `" + CLS_SRC + "` a rendu NUL");
        gcRoot.add(src);
        try { invokeMethod(ctorSrc.info, src, apSrc.args); }
        catch (e) { return refus("`" + CLS_SRC + "..ctor` a LEVE : " + (e as Error).message); }

        // 4. LA BC. `isRestart: false` -- le ctor a DEJA bati la lineup adverse (decompile).
        let bc: NativePointer;
        try { bc = invokeMethod(mLoad.info, src, [argBool(false)]); }
        catch (e) { return refus("`LoadBattleInternal` a LEVE : " + (e as Error).message); }
        if (bc.isNull()) return refus("`LoadBattleInternal` a rendu une BC NULLE");
        const nomBc = nomDeClasse(bc);
        if (nomBc !== "BattleConfiguration") {
            return refus("`LoadBattleInternal` a rendu un `" + (nomBc ?? "?") + "`, pas une "
                + "`BattleConfiguration` -- on ne le rend pas comme un succes");
        }
        gcRoot.add(bc);
        sourceForgee = src;
        derniereCle = { tier, node, isV2 };

        resume.srcPtr = src.toString();
        resume.bcPtr = bc.toString();
        resume.dataPtr = data.toString();
        resume.boardId = champRecordTexte(data, "BoardId");
        resume.spawnPointsSet = champRecordInt(data, "SpawnPointsSet");
        resume.lightningVictoryTurns = champRecordInt(data, "LightningVictoryTurns");
        // ⚠ CE QUI DIT SI LE NOEUD EST UNE BATAILLE. Un noeud d'amelioration ou de coffre rend un
        // enregistrement PARFAITEMENT valide, avec `Enemies` VIDE -- la BC sort alors complete et
        // SANS ADVERSAIRE, ce qui se lit comme une forge ratee alors que c'est le noeud qui n'est
        // pas un combat. Mesure du 2026-08-24 sur (tier 9, node 1).
        const ennemis = tailleListeRecord(data, "Enemies");
        const mowEnnemi = champRecord(data, "MachineOfWarEnemy");
        resume.ennemis = ennemis;
        resume.mowEnnemi = mowEnnemi !== null;
        resume.uniteesDisponibles = tailleListeRecord(data, "AvailableUnits");
        resume.uniteesEligibles = tailleListeRecord(data, "EligibleUnits");

        // ⚠ CE QUI ARRIVE VRAIMENT DANS LA BC, ET CE N'EST PAS `Enemies`.
        // `..ctor` -> `CreateOpponentLineup` -> `ListExtensions$$FilterMap(Enemies, b__43_0)`, et
        // ce mappeur commence par `if (unit.RemainingHealth == 0) return null` -- `FilterMap`
        // jette les nuls. Un ennemi a 0 PV n'entre donc PAS dans `PredefinedUnits`, en silence.
        // Mesure du 2026-08-24 : run NON demarre => les 9 ennemis du (tier 9, node 3) sont tous a
        // 0 PV, la BC sort avec `PredefinedUnits: []` et le seul `PredefinedMachines` -- qui, lui,
        // passe par `PredefinedMachineOfWar$$op_Implicit` et ne subit aucun filtre.
        let vivants: number | null = null;
        const pv: Array<Record<string, unknown>> = [];
        const liste = champRecord(data, "Enemies");
        if (liste !== null) {
            const els = elementsDeListe(liste);
            if (!estRefus(els)) {
                vivants = 0;
                for (const e of els) {
                    const restant = champInt(e, "RemainingHealth");
                    pv.push({
                        max: champInt(e, "MaxHealth"), restant,
                        npc: champBool(e, "IsNpc"), puissance: champInt(e, "Power"),
                    });
                    if (restant !== null && restant > 0) vivants++;
                }
            }
        }
        resume.ennemisVivants = vivants;
        resume.ennemisPv = pv;
        if (ennemis === 0 && mowEnnemi === null) {
            resume.avertissement = "NOEUD SANS COMBAT : `Enemies` est vide et il n'y a pas de "
                + "machine adverse. La BC est structurellement complete mais SANS ADVERSAIRE.";
        } else if (vivants === 0 && ennemis !== null && ennemis > 0) {
            resume.avertissement = "LES " + ennemis + " ENNEMIS SONT TOUS A 0 PV, donc AUCUN "
                + "n'entre dans la BC : `CreateOpponentLineup` les filtre (`FilterMap` + "
                + "`RemainingHealth == 0`). Les PV adverses viennent de l'etat de RUN -- lire "
                + "`runDemarre` dans `mowEventEtat {tier}`. Sans run demarre la BC sort avec "
                + "`PredefinedUnits: []`, et seule la machine adverse survit (elle ne passe pas "
                + "par ce filtre).";
        }
        resume.note = "BC construite par la SOURCE. Aucun jeton engage : on s'est arrete avant "
            + "`StartMatch`, et `SendLoadBattleGameEventInternal` -- qui appelle "
            + "`IMachinesOfWarEventProgression$$StartBattle` -- n'a jamais ete appelee.";
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
    ctx.rpc.mowEventSourceForgeEtat = (): unknown => ({
        ok: true,
        forgee: sourceForgee !== null && !sourceForgee.isNull() ? sourceForgee.toString() : null,
        cle: derniereCle,
    });
}
