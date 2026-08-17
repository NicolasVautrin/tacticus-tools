// pvp-opponents — LES PROPOSITIONS DE L'ARENE, LUES SANS RIEN DEPENSER.
//
// POURQUOI CE MODULE EXISTE. Monter une sandbox « comme un duel d'Arene » demandait jusqu'ici
// d'ENTRER dans le combat pour capturer sa `BattleConfiguration` -- or entrer CONSOMME la
// tentative, et abandonner ne la rend pas. Les propositions, elles, sont deja en memoire des
// que l'ecran d'Arene a charge : il n'y a rien a payer pour les LIRE.
//
// LA CHAINE, ET POURQUOI C'EST CELLE-LA.
//
//     ViewCommandExecutor._pvpProgression        -> PvpProgression
//       PvpProgression._pvpProgressionData       -> PvpProgressionData
//         PvpProgressionData.latestOpponents     -> List<PvpEncounterProgressionData>
//
// ⚠ On passe par le `ViewCommandExecutor`, PAS par `PvpScreen._pvpProgression` (qui existe
// aussi). L'ecran n'est instancie que si l'utilisateur l'a ouvert ; l'executeur, lui, est
// capte au warmup et porte les 44 progressions du compte. Mesure du 2026-08-17, build
// `t6dpr4k06g` : `_pvpProgression` y est declare `IPvpProgression`, aux cotes de 40 autres
// `*Progression` -- c'est le porteur canonique, et `view-command.ts` en est le foyer unique.
//
// ⚠ AUCUN NATIF DU JEU N'EST INVOQUE ICI, et ce n'est pas un scrupule de style : c'est ce que
// le decompile a rendu POSSIBLE. `PvpProgression$$GetLatestOpponents` s'ecrit en entier :
//
//     if (*(param_1 + 0x10) != 0) { return *(*(param_1 + 0x10) + 0x78); }
//     FUN_1801f5460();                              // levee si `_pvpProgressionData` est nul
//
// soit deux dereferencements et une garde. Les deux offsets sont EXACTEMENT ceux que les
// metadonnees nomment (`_pvpProgressionData` a +0x10, `latestOpponents` a +0x78), donc lire
// les champs PAR NOM rend la meme valeur que l'appel, sans passer par `runtime_invoke`.
//
// ⚠ NE PAS CONFONDRE avec `PvpProgression$$RefreshOpponentsAsync`, qui rend une
// `Task<FetchResult<PvpData>>` et part sur le RESEAU. Ce module ne l'appelle pas, et ne doit
// jamais le faire : la difference se lit dans le type de retour, pas dans le nom.
//
// LECTURE SEULE : aucune ecriture, aucun envoi, aucune tentative consommee.

import {
    findClassAnywhere, getFieldOffset, readIl2cppString,
} from "../il2cpp/helpers.js";
// Le FOYER de la resolution du `ViewCommandExecutor` -- importe, jamais re-marche.
import { executeurVivant, Refus as RefusVue } from "./view-command.js";
import { serializeToJson } from "../il2cpp/serializer.js";
import { queueOnMainThread } from "../runtime/queue.js";
import { Ctx } from "../controller.js";
import { log } from "../runtime/diag.js";

/** Borne de garde sur la taille d'une liste native. Une `_size` aberrante (objet libere,
 *  offset perime) ferait boucler des millions de fois et figer le jeu ; on prefere tronquer
 *  EN LE DISANT. L'Arene en propose une poignee. */
const MAX_ELEMENTS = 4096;

function estRefus(x: unknown): x is RefusVue {
    return typeof x === "object" && x !== null && (x as RefusVue).ok === false;
}

function refus(error: string): RefusVue {
    return { ok: false, error };
}

/**
 * Lit un champ POINTEUR par son NOM, sur la classe REELLE de l'instance.
 *
 * ⚠ La classe est lue a l'offset 0 de l'objet (slot `Il2CppClass*`), pas cherchee par son nom
 * de namespace : l'instance derriere une interface peut etre d'une classe qu'on n'a pas
 * nommee, et c'est precisement le cas ici (`IPvpProgression` -> `PvpProgression`).
 *
 * ⚠ `getFieldOffset` rend -1 sur un nom absent, et -1 est *truthy* : on teste `< 0`.
 */
function champPointeur(obj: NativePointer, nom: string): NativePointer | RefusVue {
    if (obj.isNull()) return refus(`objet NUL -- \`${nom}\` illisible`);
    let k: NativePointer;
    try { k = obj.readPointer(); } catch (e) {
        return refus(`classe illisible sur l'objet (${(e as Error).message})`);
    }
    if (k.isNull()) return refus("slot de classe NUL -- ce n'est pas un objet IL2CPP vivant");
    const off = getFieldOffset(k, nom);
    if (off < 0) {
        return refus(`champ \`${nom}\` ABSENT de ce build -- chemin PERIME, pas de repli `
            + "sur un offset mesure");
    }
    try { return obj.add(off).readPointer(); }
    catch (e) { return refus(`lecture de \`${nom}\` : ${(e as Error).message}`); }
}

/** Lit un champ Int32 par son NOM. Rend `null` quand le champ n'existe pas -- l'appelant
 *  publie alors `null`, JAMAIS un zero (un zero se lirait comme une valeur mesuree). */
function champInt(obj: NativePointer, nom: string): number | null {
    if (obj.isNull()) return null;
    try {
        const off = getFieldOffset(obj.readPointer(), nom);
        if (off < 0) return null;
        return obj.add(off).readS32();
    } catch { return null; }
}

/** Lit un champ `System.String` par son NOM. */
function champTexte(obj: NativePointer, nom: string): string | null {
    const p = champPointeur(obj, nom);
    if (estRefus(p) || p.isNull()) return null;
    try { return readIl2cppString(p); } catch { return null; }
}

/**
 * Les elements d'une `List<T>` native, resolus PAR NOM (`_items`, `_size`).
 *
 * Rend un REFUS NOMME plutot qu'un tableau vide quand la liste est illisible : « pas de
 * proposition » et « je n'ai pas su lire » ne doivent pas se confondre -- c'est exactement le
 * genre de zero muet qui a deja fait conclure a tort qu'un gisement etait vide.
 */
function elementsDeListe(liste: NativePointer): NativePointer[] | RefusVue {
    if (liste.isNull()) return refus("liste NULLE");
    let k: NativePointer;
    try { k = liste.readPointer(); } catch { return refus("classe de la liste illisible"); }
    const offItems = getFieldOffset(k, "_items");
    const offSize = getFieldOffset(k, "_size");
    if (offItems < 0 || offSize < 0) {
        return refus("`_items`/`_size` absents -- ce n'est pas une `List<T>` de ce build");
    }
    const n = liste.add(offSize).readS32();
    if (n < 0) return refus(`\`_size\` = ${n} : negatif, l'objet n'est pas une liste vivante`);
    const arr = liste.add(offItems).readPointer();
    if (arr.isNull()) return [];
    const pris = Math.min(n, MAX_ELEMENTS);
    const out: NativePointer[] = [];
    for (let i = 0; i < pris; i += 1) {
        // Tableau IL2CPP : en-tete de 0x20, puis les elements (pointeurs).
        out.push(arr.add(0x20 + i * Process.pointerSize).readPointer());
    }
    if (pris < n) log(`[pvp-opponents] liste TRONQUEE : ${pris}/${n} (borne ${MAX_ELEMENTS})`);
    return out;
}

/** Une liste de `System.String` -> tableau de chaines. */
function listeDeTextes(liste: NativePointer): string[] | null {
    const els = elementsDeListe(liste);
    if (estRefus(els)) return null;
    return els.map((p) => (p.isNull() ? null : readIl2cppString(p)))
        .filter((x): x is string => typeof x === "string");
}

/** La `PvpProgression` vivante, via le foyer `executeurVivant`. */
function progressionPvp(): NativePointer | RefusVue {
    const exec = executeurVivant();
    if (estRefus(exec)) return exec;
    const kExec = findClassAnywhere("idun.shared.commands", "ViewCommandExecutor");
    if (!kExec) return refus("classe `idun.shared.commands.ViewCommandExecutor` introuvable");
    const off = getFieldOffset(kExec, "_pvpProgression");
    if (off < 0) {
        return refus("`_pvpProgression` ABSENT de `ViewCommandExecutor` sur ce build "
            + "-- chemin PERIME");
    }
    const p = (exec as NativePointer).add(off).readPointer();
    if (p.isNull()) {
        return refus("`ViewCommandExecutor._pvpProgression` est NUL -- l'executeur vit mais "
            + "n'a pas recu cette dependance");
    }
    return p;
}

/** Le resume d'UNE proposition : ce dont un montage sandbox a besoin, et rien de plus. */
function resumeProposition(enc: NativePointer): Record<string, unknown> {
    const adv = champPointeur(enc, "opponent");
    const advOk = !estRefus(adv) && !adv.isNull();
    return {
        // Le couple que `sandboxModeBuildBc` reclame.
        boardId: champTexte(enc, "boardId"),
        spawnPointsSet: champInt(enc, "spawnPointsSet"),
        ratingGain: champInt(enc, "ratingGain"),
        ratingLoss: champInt(enc, "ratingLoss"),
        adversaire: advOk ? {
            displayName: champTexte(adv as NativePointer, "displayName"),
            rating: champInt(adv as NativePointer, "rating"),
            level: champInt(adv as NativePointer, "level"),
            trophies: champInt(adv as NativePointer, "trophies"),
            machineOfWarLineup: champTexte(adv as NativePointer, "machineOfWarLineup"),
            lineup: (() => {
                const l = champPointeur(adv as NativePointer, "lineup");
                return estRefus(l) || l.isNull() ? null : listeDeTextes(l);
            })(),
        } : null,
        // Pourquoi l'adversaire manque, le cas echeant -- jamais un `null` muet.
        refusAdversaire: estRefus(adv) ? adv.error : (advOk ? null : "`opponent` NUL"),
    };
}

export function register(ctx: Ctx): void {
    /**
     * Les propositions d'Arene actuellement chargees.
     *
     * `{ json: true }` ajoute la serialisation complete (Newtonsoft) -- utile pour rejouer
     * hors ligne, mais lourde et faillible sur les types exotiques ; le RESUME, lui, est lu
     * champ par champ et ne depend d'aucun serialiseur.
     *
     * ⚠ TRI-ETAT sur le compte : `null` = PAS mesure (chaine rompue, et la raison est dite),
     * `0` = mesure et vide (l'Arene n'a rien charge). Les rabattre l'un sur l'autre ferait
     * lire « aucun adversaire » la ou il faut lire « ouvre l'ecran d'Arene ».
     */
    ctx.rpc.pvpOpponents = (body?: { json?: boolean }): Promise<unknown> =>
        queueOnMainThread(() => {
            const prog = progressionPvp();
            if (estRefus(prog)) return { ...prog, nombre: null };

            const data = champPointeur(prog as NativePointer, "_pvpProgressionData");
            if (estRefus(data)) return { ...data, nombre: null };
            if (data.isNull()) {
                return { ok: false, nombre: null,
                         error: "`_pvpProgressionData` est NUL -- c'est la garde meme que le "
                             + "natif teste avant de lever. Les donnees PvP ne sont pas "
                             + "chargees : ouvrir l'ecran d'Arene suffit (ouvrir ne consomme "
                             + "AUCUNE tentative ; seul un combat en consomme)." };
            }

            const liste = champPointeur(data, "latestOpponents");
            if (estRefus(liste)) return { ...liste, nombre: null };
            if (liste.isNull()) {
                return { ok: true, nombre: 0, propositions: [],
                         note: "`latestOpponents` est NUL : la progression PvP est chargee mais "
                             + "aucune proposition ne l'accompagne -- ouvrir l'ecran d'Arene." };
            }

            const els = elementsDeListe(liste);
            if (estRefus(els)) return { ...els, nombre: null };

            const propositions = els
                .filter((p) => !p.isNull())
                .map((p) => resumeProposition(p));

            const sortie: Record<string, unknown> = {
                ok: true,
                nombre: propositions.length,
                progression: (prog as NativePointer).toString(),
                propositions,
            };
            if (body?.json === true) {
                // Best-effort : `serializeToJson` rend `null` si Newtonsoft refuse le graphe.
                // On PUBLIE l'echec plutot que de le taire -- le resume reste valable.
                const j = serializeToJson(liste);
                sortie.json = j;
                sortie.jsonRefus = j === null
                    ? "serialisation Newtonsoft en echec -- le resume ci-dessus reste lu "
                        + "champ par champ, il ne depend pas d'elle"
                    : null;
            }
            return sortie;
        });
}
