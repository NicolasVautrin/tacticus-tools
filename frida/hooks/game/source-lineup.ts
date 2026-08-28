// LA COMPOSITION DU JOUEUR, DEMANDÉE À LA SOURCE — foyer UNIQUE.
//
// ⛔ CE MODULE EXISTE PARCE QUE LA QUESTION A ÉTÉ REPOSÉE TROIS FOIS, ET MAL RÉPONDUE DEUX FOIS.
// « Quelles unités le joueur amène-t-il ? » n'a PAS de réponse dans la `BattleConfiguration` :
// mesuré le 2026-08-23 sur une BC PvP RÉELLE (forgée, sans consommer de tentative), le camp du
// joueur y est VIDE — `PredefinedUnits` ne porte que l'adversaire (groupe `Id 12`), et les unités
// du joueur n'entrent qu'au DÉPLOIEMENT, par `AddUnitMessage`, donc APRÈS la fenêtre
// `LoadBattle.onLeave`. Deux replis ont été tentés et sont tous deux FAUX :
//
//   * ÉPINGLER la composition à l'armement -> les 5 ids venaient d'une BC d'onslaught, la lineup
//     d'arène est autre : 0 appariement, aucun trait posé, et RIEN ne le signalait.
//   * DÉRIVER de la BC -> rend 0 unité en PvP, ce qui se lit comme « pas de camp » alors que c'est
//     « pas dans cet objet ».
//
// LA SOURCE, ELLE, CONNAÎT LA COMPOSITION — c'est elle qui la fournira au HUD. Toutes les sources
// de mode l'exposent par le même contrat (`GetBattleLineup` / `GetBattleMachineOfWarLineup`) :
// Campaign, CampaignEvent, Endless, GuildBoss, GuildWars, LegendaryEvent, MachinesOfWarEvent,
// Friendly, AutomaticBattles, AReplay, Sandbox, Pvp, SyncPvp. On la lui DEMANDE, une seule fois,
// ici, et plus personne n'a à se reposer la question.
//
// ⚠ THREAD. `invokeMethod` exécute du natif : l'appelant doit être SUR LE THREAD PRINCIPAL. Depuis
// un RPC, passer par `queueOnMainThread`. Depuis un `Interceptor` posé sur une méthode de la source
// (`LoadBattle.onLeave`), on Y EST DÉJÀ — c'est même la fenêtre idéale, l'objet est vivant et
// pleinement construit.
//
// ⚠ CE QUI PEUT INTERCEPTER LA RÉPONSE. `deployment-draft` (`deploymentHudArmer {armer:true}`)
// ancre lui aussi `GetBattleLineup` et peut LAISSER PASSER un tableau vide quand sa mémoire de
// poses porte plus frais que la sauvegarde du compte. Un vide obtenu pendant que ce relais est armé
// n'accuse donc PAS la source. Le champ `retour.classe` est là pour trancher.

import {
    class_get_name, findMethodByParamCount, s as cstr,
} from "../il2cpp/helpers.js";
import { invokeMethod } from "../il2cpp/invoke.js";

/** Un `Int32` boxé, tel que `runtime_invoke` l'attend pour un type valeur. */
function argInt(v: number): NativePointer {
    const p = Memory.alloc(8);
    p.writeS32(v | 0);
    return p;
}

/** Les bornes de composition que TOUTE source de mode expose. Le plafond est ce qu'on passe à
 *  `GetBattleLineup` : il se LIT sur la source, il ne s'écrit pas. Un `5` en dur ici deviendrait
 *  faux le jour où un mode change de plafond, en silence. */
const BORNES = [
    "MinUnitsNeededToStartBattle",
    "MaxUnitsPossibleToStartBattle",
    "AmountOfUnlockedUnits",
] as const;

export interface LineupDeSource {
    ok: boolean;
    /** Le nom de classe de l'instance interrogée. Publié : une réponse vide venue de la MAUVAISE
     *  classe et une source réellement sans composition se lisent autrement pareil. */
    classe: string | null;
    /** TRI-ÉTAT partout : `null` = PAS MESURÉ (méthode absente, levée, retour nul). JAMAIS un
     *  zéro de complaisance — un `[]` rendu pour une mesure ratée fait conclure « aucune unité »
     *  et corriger la mauvaise cause. */
    bornes: Record<string, number | null>;
    places: number | null;
    unites: string[] | null;
    unitesTaille: number | null;
    mow: string | null;
    /** Le pointeur ET la classe du `System.String[]` rendu. Sans la classe, une longueur de 0 ne
     *  distingue pas « aucune composition sauvegardée » d'« offset lu de travers ». */
    retour: { ptr: string; classe: string | null } | null;
    refus: string | null;
    mowRefus: string | null;
    /** Le POOL DÉPLOYABLE (`GetUnlockedUnits`), et ce n'est PAS la même question que `unites`.
     *  `null` = pas demandé ou pas mesuré. Voir `deployables` ci-dessous. */
    deployables: string[] | null;
    deployablesRefus: string | null;
    /** D'où viennent les ids utilisables : `"lineup"` (la composition sauvegardée) ou
     *  `"deployables"` (le repli). JAMAIS deviné par l'appelant. */
    voie: "lineup" | "deployables" | null;
    /** Le nombre de cases de spawn OFFERTES AU JOUEUR par le plateau, tel que l'appelant l'a
     *  dérivé de la BC. `null` = pas fourni / pas dérivable — et alors AUCUN pincement n'est
     *  appliqué, ce qui se lit sur `placesAvantPincement === places`. */
    casesDuPlateau: number | null;
    /** La borne AVANT pincement (celle de la source). Publiée pour que le pincement soit VISIBLE :
     *  sans elle, un `places` de 4 ne distingue pas « le mode dit 4 » de « le mode dit 5 et le
     *  plateau a pincé », alors que ça change la CLÉ de magasin lue. */
    placesAvantPincement: number | null;
}

function vide(refus: string, classe: string | null = null): LineupDeSource {
    return { ok: false, classe, bornes: {}, places: null, unites: null, unitesTaille: null,
             mow: null, retour: null, refus, mowRefus: null,
             deployables: null, deployablesRefus: null, voie: null,
             casesDuPlateau: null, placesAvantPincement: null };
}

/** Les éléments d'une `List<System.String>` gérée. `_items` (tableau) et `_size` (compte réel) --
 *  itérer sur la CAPACITÉ du tableau rendrait des nuls de fin de buffer pour des unités. */
function textesDeListe(liste: NativePointer): string[] | null {
    try {
        const items = liste.add(0x10).readPointer();
        const n = liste.add(0x18).readS32();
        if (items.isNull() || n < 0 || n > 512) return null;
        const out: string[] = [];
        for (let i = 0; i < n; i++) {
            out.push(chaineGeree(items.add(0x20 + i * Process.pointerSize).readPointer())
                ?? "<illisible>");
        }
        return out;
    } catch { return null; }
}

/**
 * LE POOL DÉPLOYABLE — la SECONDE question, et elle a une réponse quand la première n'en a pas.
 *
 * ⛔ `GetBattleLineup` rend la composition SAUVEGARDÉE. Sur un mode à run (l'événement Machines of
 * War / Incursion) elle vit dans l'ÉTAT DE RUN : tant qu'aucun run n'est démarré elle est VIDE, et
 * `ciblesAuto: "moi"` n'a alors RIEN à nommer. Mesure du 2026-08-24 : `places=5, unites=[]` alors
 * que `AmountOfUnlockedUnits` valait **24**. La source savait ; on ne lui demandait pas.
 *
 * `GetUnlockedUnits()` rend ces 24 -- les unités que le HUD proposera au déploiement, en ids NUS
 * (`blackTerminator`, `worldKharn`, ...), la même forme que le natif passe en `mainPlayerUnits`.
 *
 * ⚠ CE N'EST PAS LA MÊME QUESTION, ET LE CONFONDRE SERAIT FAUX POUR TOUT AUTRE USAGE : c'est le
 * POOL, pas l'ÉQUIPE. Pour un BUFF c'est sans risque (viser une unité qui ne descend jamais ne
 * coûte rien) ; pour compter une équipe ou prédire un placement, ce serait un mensonge. D'où
 * `voie`, qui DIT laquelle des deux a répondu.
 *
 * ⚠ ET ON PASSE PAR `GetUnlockedUnits`, JAMAIS PAR `GetUnitsForDeploymentHUD` : ce dernier rend un
 * `PooledList<String>` (type VALEUR, mis en pool), et enchaîner un `get_Item` sur le pointeur de
 * boxe passe l'en-tête comme `this` -- ça a TUÉ le process le 2026-08-21. `GetUnlockedUnits`
 * appelle `CloneAsListAndDispose` : ce qu'on reçoit est une `List<String>` normale.
 */
function poolDeployable(
    klass: NativePointer, src: NativePointer,
): { ids: string[] | null; refus: string | null } {
    const mi = findMethodByParamCount(klass, "GetUnlockedUnits", 0);
    if (!mi) return { ids: null, refus: "`GetUnlockedUnits(0)` INTROUVABLE sur cette source" };
    let l: NativePointer;
    try { l = invokeMethod(mi.info, src, []); }
    catch (e) { return { ids: null, refus: "`GetUnlockedUnits` a levé : " + (e as Error).message }; }
    if (l.isNull()) return { ids: null, refus: "`GetUnlockedUnits` a rendu NUL" };
    const ids = textesDeListe(l);
    return ids === null
        ? { ids: null, refus: "`List<String>` illisible (offsets `_items`/`_size`)" }
        : { ids, refus: null };
}

/** Lit un `System.String` géré : longueur en `+0x10`, caractères UTF-16 à partir de `+0x14`. */
function chaineGeree(p: NativePointer): string | null {
    if (p.isNull()) return null;
    try { return p.add(0x14).readUtf16String(); } catch { return null; }
}

/**
 * DEMANDER à une source de mode la composition que le joueur amène.
 *
 * `src` est l'instance de la source (le `this` d'une de ses méthodes — au `LoadBattle.onLeave`,
 * c'est `args[0]` capturé à l'`onEnter`). On ne suppose RIEN de sa classe concrète : le contrat est
 * porté par la base, donc `findMethodByParamCount` remonte la hiérarchie et trouve l'override.
 *
 * ⚠ LE PARAMÈTRE DE `GetBattleLineup` EST UNE TAILLE, PAS UN INDEX — son nom dans le dump
 * (`lineupIndex`) dit le contraire, et le croire fait lire un vide pour une absence. Mesuré le
 * 2026-08-23 sur la voie Chaos : `0 -> []`, `1 -> 1 élément`, `2 -> 2`, `18 -> 18`. Le natif rend la
 * composition sauvegardée AJUSTÉE au nombre de places demandé. D'où le défaut :
 * `MaxUnitsPossibleToStartBattle`, LU sur la source.
 *
 * ⛔ MAIS LA BORNE DE LA SOURCE N'EST PAS CELLE QUE LE JEU PASSE — LE PLATEAU PINCE, ET C'EST LA
 * MÊME VALEUR QUI NOMME LA CLÉ DE MAGASIN. `GetBattleLineupToDeploy` fait
 * `GetBattleLineup(VisualBattleQuery$$MaxUnitsPossibleToStartBattle())`, et cette méthode-là rend
 * un `idun.shared.SPMath$$Min` À TROIS TERMES :
 *     min( source.AmountOfUnlockedUnits(),
 *          GetSpawnPointCoordinatedForHumanPlayer().Count,   <- LE PLATEAU
 *          source.MaxUnitsPossibleToStartBattle() )
 * Côté source, `CampaignGameModeSource$$Min/MaxUnitsNeededToStartBattle` lisent `+0x7c` / `+0x80`
 * du même objet de configuration : ce sont des GLOBALES DU MODE (3 et 5), identiques sur TOUS les
 * nœuds — elles ne disent rien de la carte.
 *
 * (!)MESURE DU 2026-08-28, `mirror3` nœud 38 (board `C3_37`, 4 cases joueur) : la source rend 5,
 * donc on lisait `mirror3_5` = `[admecRuststalker, ultraEliminatorSgt, spaceHound,
 * ultraInceptorSgt, ultraTigurius]` pendant que la bataille jouait `mirror3_4`. Conséquence
 * mesurée : `ciblesAuto: "moi"` posait le buff sur CINQ unités dont AUCUNE n'était déployée, et le
 * symptôme à l'écran était « le buff ne s'applique pas ». Aucune erreur, aucun avertissement — le
 * patch rapportait fidèlement « 5 Target(s) ÉCRITE(S) ».
 *
 * ⇒ `casesDuPlateau` est donc le 2e terme du `Min`, à DÉRIVER DE LA BC par l'appelant (elle est la
 * seule à l'avoir à cette fenêtre). On ne modélise pas `AmountOfUnlockedUnits` : il compte les
 * unités débloquées du compte (mesuré 49) et ne pince jamais en campagne — notre `places` est donc
 * un MAJORANT du `Min` natif, il ne peut viser une clé PLUS GRANDE que celle que le jeu relit.
 * ⚠ Tri-état : `casesDuPlateau` NON DÉRIVÉ ne se rabat PAS sur la borne du mode en silence — il
 * laisse `places` intact ET le publie, pour que « pas pincé » se distingue de « pincé à la même
 * valeur ».
 */
export function lineupDeLaSource(
    src: NativePointer | null,
    opts?: { places?: number; avecMow?: boolean; casesDuPlateau?: number | null },
): LineupDeSource {
    if (src === null || src.isNull()) return vide("instance de source NULLE");

    // ⛔ LE TYPE AVANT TOUT : invoquer sur une disposition mémoire étrangère exécute du natif à
    // l'aveugle. On ne CONTRAINT pas la classe (toute source de mode est légitime), on la PUBLIE.
    let klass: NativePointer;
    let classe: string | null;
    try {
        klass = src.readPointer();
        classe = cstr(class_get_name(klass) as NativePointer);
    } catch (e) {
        return vide("classe de l'instance ILLISIBLE : " + (e as Error).message);
    }

    // ⚠ `runtime_invoke` BOXE les types valeur : un `Int32` revient dans un OBJET géré, et sa
    // valeur est à `+0x10` — pas dans le pointeur lui-même. Lire le pointeur avec `.toInt32()`
    // rend des ADRESSES consécutives, c'est-à-dire des nombres PLAUSIBLES : la faute ne se voit
    // pas. Mesuré le 2026-08-23 (-165316864 / -165316896 / -165316928, espacés de 32 octets).
    const bornes: Record<string, number | null> = {};
    for (const nom of BORNES) {
        const mi = findMethodByParamCount(klass, nom, 0);
        if (!mi) { bornes[nom] = null; continue; }
        try {
            const boite = invokeMethod(mi.info, src, []);
            bornes[nom] = boite.isNull() ? null : boite.add(0x10).readS32();
        } catch { bornes[nom] = null; }
    }

    const placesAvantPincement = opts?.places ?? bornes["MaxUnitsPossibleToStartBattle"];
    if (placesAvantPincement === null || placesAvantPincement === undefined) {
        return { ...vide("`MaxUnitsPossibleToStartBattle` NON MESURÉ et aucune `places` fournie -- "
                    + "on ne devine pas un plafond, un `5` en dur deviendrait faux en silence",
                    classe),
                 bornes };
    }
    // LE PINCEMENT PAR LE PLATEAU — 2e terme du `Min` natif (cf. l'en-tête). Un `casesDuPlateau`
    // absent laisse la borne du mode telle quelle : on ne fabrique pas un pincement qu'on n'a pas
    // mesuré, et `placesAvantPincement` rend l'écart lisible dans les deux sens.
    const cases = opts?.casesDuPlateau ?? null;
    const places = cases === null ? placesAvantPincement
        : Math.min(placesAvantPincement, cases);

    const miLineup = findMethodByParamCount(klass, "GetBattleLineup", 1);
    if (!miLineup) {
        return { ...vide("`GetBattleLineup(1 param)` INTROUVABLE sur `" + classe + "`", classe),
                 bornes, places, casesDuPlateau: cases, placesAvantPincement };
    }
    let arr: NativePointer;
    try { arr = invokeMethod(miLineup.info, src, [argInt(places)]); }
    catch (e) {
        return { ...vide("`GetBattleLineup` a levé : " + (e as Error).message, classe),
                 bornes, places, casesDuPlateau: cases, placesAvantPincement };
    }
    if (arr.isNull()) {
        return { ...vide("`GetBattleLineup` a rendu NUL -- aucune composition sauvegardée pour "
                    + "cette source (ce n'est PAS « roster vide »)", classe),
                 bornes, places, casesDuPlateau: cases, placesAvantPincement };
    }

    // `System.String[]` : longueur en +0x18, éléments à partir de +0x20.
    const classeArr = (() => {
        try { return cstr(class_get_name(arr.readPointer()) as NativePointer); }
        catch { return null; }
    })();
    const n = arr.add(0x18).readS32();
    const unites: string[] = [];
    // Borne de sûreté : une longueur lue de travers rendrait un nombre énorme et on itérerait sur
    // de la mémoire quelconque. Le plafond d'un mode n'approche jamais 64.
    for (let i = 0; i < n && i < 64; i++) {
        const s = arr.add(0x20 + i * Process.pointerSize).readPointer();
        unites.push(chaineGeree(s) ?? "<illisible>");
    }

    let mow: string | null = null;
    let mowRefus: string | null = null;
    if (opts?.avecMow !== false) {
        const miMow = findMethodByParamCount(klass, "GetBattleMachineOfWarLineup", 0);
        if (!miMow) {
            mowRefus = "`GetBattleMachineOfWarLineup` INTROUVABLE sur `" + classe + "`";
        } else {
            try {
                const p = invokeMethod(miMow.info, src, []);
                // Une MoW absente est une réponse LÉGITIME (`null` géré), pas une panne : on la
                // distingue de « pas mesuré » par `mowRefus`, qui reste nul dans ce cas.
                mow = p.isNull() ? null : chaineGeree(p);
            } catch (e) {
                mowRefus = "`GetBattleMachineOfWarLineup` a levé : " + (e as Error).message;
            }
        }
    }

    // LE REPLI, et il ne se déclenche QUE sur un vide : tant que la composition sauvegardée
    // répond, c'est elle qui fait foi -- le pool est plus large, donc moins précis.
    const pool = n === 0 ? poolDeployable(klass, src) : { ids: null, refus: null };

    return {
        ok: true, classe, bornes, places, casesDuPlateau: cases, placesAvantPincement,
        unites, unitesTaille: n, mow, mowRefus,
        retour: { ptr: arr.toString(), classe: classeArr },
        deployables: pool.ids,
        deployablesRefus: pool.refus,
        voie: n > 0 ? "lineup" : (pool.ids !== null && pool.ids.length > 0 ? "deployables" : null),
        refus: n === 0 && (pool.ids === null || pool.ids.length === 0)
            ? "tableau de longueur 0, et le POOL déployable ne répond pas non plus ("
                + (pool.refus ?? "vide") + ") -- si `retour.classe` n'est pas un tableau de "
                + "chaînes, c'est l'OFFSET qui est faux, pas la composition qui est vide ; et si "
                + "`deploymentHudArmer` est armé, c'est peut-être LUI qui a laissé passer un vide"
            : (n === 0
                ? "composition sauvegardée VIDE (mode à run non démarré, typiquement) -- repli sur "
                    + "le POOL déployable de `GetUnlockedUnits` : " + (pool.ids as string[]).length
                    + " unité(s). C'est le POOL, pas l'ÉQUIPE ; sans risque pour un buff, faux "
                    + "pour compter une équipe."
                : null),
    };
}
