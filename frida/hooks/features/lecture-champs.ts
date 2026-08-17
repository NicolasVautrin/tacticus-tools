// lecture-champs — LIRE UN OBJET NATIF PAR LES NOMS DE SES CHAMPS, et NOMMER chaque echec.
//
// FOYER UNIQUE, extrait de `pvp-opponents.ts` quand le second lecteur de progression est
// arrive (`guild-boss-config.ts`). Ce ne sont pas des commodites : chacune de ces fonctions
// encode une faute deja payee sur ce depot.
//
//   * `getFieldOffset` rend -1 sur un nom absent, et -1 est *truthy* -- tester `< 0`, jamais
//     `||` ni `!`. C'est le piege qui fait lire le champ 0 (le slot de classe) a la place.
//   * la classe est lue A L'OFFSET 0 DE L'INSTANCE, pas cherchee par son nom de namespace :
//     l'objet derriere une interface est d'une classe qu'on n'a pas forcement nommee
//     (`IPvpProgression` -> `PvpProgression`, `IGuildBossProgression` -> `GuildBossProgression`).
//   * un echec de lecture rend un REFUS NOMME, jamais un `null` ni un tableau vide : « je n'ai
//     pas su lire » et « c'est vide » sont deux etats DIFFERENTS, et les confondre a deja fait
//     conclure a tort qu'un gisement etait mort.
//
// ⚠ AUCUNE de ces fonctions n'invoque de natif. Elles LISENT de la memoire.

import { getFieldOffset, readIl2cppString } from "../il2cpp/helpers.js";
import { Refus } from "./view-command.js";

/** Borne de garde sur la taille d'une liste native. Une `_size` aberrante (objet libere,
 *  offset perime) ferait boucler des millions de fois et figer le jeu ; on prefere tronquer
 *  EN LE DISANT plutot que de rendre une troncature muette. */
export const MAX_ELEMENTS = 4096;

export function estRefus(x: unknown): x is Refus {
    return typeof x === "object" && x !== null && (x as Refus).ok === false;
}

export function refus(error: string): Refus {
    return { ok: false, error };
}

/** Un champ POINTEUR, par son NOM, sur la classe REELLE de l'instance. */
export function champPointeur(obj: NativePointer, nom: string): NativePointer | Refus {
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

/** Un champ Int32, par son NOM. `null` = champ absent -- JAMAIS rabattu sur 0, qui se lirait
 *  comme une valeur mesuree. */
export function champInt(obj: NativePointer, nom: string): number | null {
    if (obj.isNull()) return null;
    try {
        const off = getFieldOffset(obj.readPointer(), nom);
        if (off < 0) return null;
        return obj.add(off).readS32();
    } catch { return null; }
}

/** Un champ `System.String`, par son NOM. */
export function champTexte(obj: NativePointer, nom: string): string | null {
    const p = champPointeur(obj, nom);
    if (estRefus(p) || p.isNull()) return null;
    try { return readIl2cppString(p); } catch { return null; }
}

/** Les elements d'une `List<T>` native, resolus PAR NOM (`_items`, `_size`). */
export function elementsDeListe(liste: NativePointer): NativePointer[] | Refus {
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
    return out;
}

/** Une `List<System.String>` -> tableau de chaines. Rend `null` si la liste est illisible --
 *  l'appelant DOIT distinguer ce cas d'une liste vide. */
export function listeDeTextes(liste: NativePointer): string[] | null {
    const els = elementsDeListe(liste);
    if (estRefus(els)) return null;
    return els.map((p) => (p.isNull() ? null : readIl2cppString(p)))
        .filter((x): x is string => typeof x === "string");
}
