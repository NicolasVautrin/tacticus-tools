// champs-par-type — INDEXER les champs d'une instance PAR LE TYPE de leur declaration.
//
// POURQUOI CE FOYER EXISTE
// -------------------------
// Forger un objet de jeu (une `*GameModeSource`, une commande de vue) veut dire APPELER SON CTOR,
// et donc retrouver chacun de ses arguments parmi les services que l'executeur porte deja. Or
// l'ORDRE d'une signature NE SE RECOPIE PAS D'UN DUMP : `sources_win/` date d'un autre build, et
// rien ne garantit qu'un parametre soit reste a sa place. On resout donc chaque argument par le
// TYPE DECLARE de son parametre, apparie a des champs indexes PAR LEUR TYPE -- aucun ordre,
// aucun nom de champ en dur.
//
// Ce module est la version PARTAGEE de ce que `pvp-source-forge` portait en prive. Il a ete sorti
// quand `mow-event-source-forge` a eu besoin du meme geste : deux copies d'un helper subtil
// derivent, et celui-ci porte deja deux mesures qu'un lecteur ne redecouvrirait pas seul (la
// double declaration d'un meme nom de champ, et l'ambiguite des generiques).

import {
    class_get_fields, class_get_name, class_get_parent, field_get_name, field_get_offset,
    field_get_type, type_get_class_or_element_class, s as cstr,
} from "./helpers.js";

/** Un champ retrouve sur une instance.
 *
 *  `klass` est la classe du TYPE DECLARE, pas celle de la valeur : c'est elle qu'on confronte a
 *  `methodParamClass`, et c'est le seul discriminant qui separe deux instanciations d'un meme
 *  generique -- `IMenu<UnitDeploymentHud>` et `IMenu<IdunGameHud>` portent le MEME nom court
 *  (`IMenu\`1`) et des POINTEURS DE CLASSE differents. */
export interface ChampIndexe {
    nom: string;
    valeur: NativePointer;
    klass: NativePointer;
}

/** Les champs d'une instance, INDEXES PAR LE NOM DE LEUR TYPE DECLARE.
 *
 *  ⚠ On remonte la hierarchie, et on garde la declaration la PLUS DERIVEE en tete -- un nom de
 *  champ peut etre declare deux fois (mesure : `_featureUnlocker` l'est, sur `PvpGameModeSource`
 *  ET sur un parent). Un type peut aussi etre porte par PLUSIEURS champs : on les garde TOUS,
 *  et c'est a l'appariement de REFUSER l'ambiguite au lieu d'en choisir un. */
export function indexerAvecParents(
    obj: NativePointer, klass: NativePointer,
): Map<string, ChampIndexe[]> {
    const index = new Map<string, ChampIndexe[]>();
    let k = klass;
    let profondeur = 0;
    // `class_get_fields` ne rend que les champs DECLARES sur la classe -- d'ou la remontee.
    // Borne dure : une hierarchie qui ne remonte pas a `null` ferait boucler le thread principal.
    while (!k.isNull() && profondeur < 8) {
        const it = Memory.alloc(Process.pointerSize);
        it.writePointer(ptr(0));
        let f: NativePointer;
        while (!(f = class_get_fields(k, it) as NativePointer).isNull()) {
            try {
                const tc = type_get_class_or_element_class(
                    field_get_type(f) as NativePointer) as NativePointer;
                if (tc.isNull()) continue;
                const type = cstr(class_get_name(tc) as NativePointer);
                const nom = cstr(field_get_name(f) as NativePointer);
                const off = field_get_offset(f) as number;
                if (off < 0) continue;
                const valeur = obj.add(off).readPointer();
                const liste = index.get(type);
                // La classe la plus DERIVEE est visitee en premier : on APPEND, donc son
                // candidat reste en tete, et un appariement qui lit `[0]` prend le bon.
                if (liste === undefined) index.set(type, [{ nom, valeur, klass: tc }]);
                else liste.push({ nom, valeur, klass: tc });
            } catch { /* champ illisible : on passe, on ne devine pas */ }
        }
        try { k = class_get_parent(k) as NativePointer; } catch { break; }
        profondeur++;
    }
    return index;
}

/** Le nom de classe d'un objet gere, ou `null`.
 *
 *  ⚠ C'est le TYPE-GUARD des forges : un objet d'un autre type est PARFAITEMENT lisible, et une
 *  BC perimee comme un `RectTransform` se rendent tous deux sans lever. Confronter le nom est ce
 *  qui separe « construit » de « plausible ». */
export function nomDeClasse(obj: NativePointer): string | null {
    try {
        if (obj.isNull()) return null;
        const k = obj.readPointer();
        if (k.isNull()) return null;
        return cstr(class_get_name(k) as NativePointer);
    } catch { return null; }
}
