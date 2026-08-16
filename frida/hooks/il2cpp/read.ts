// ---------------------------------------------------------------------------------------
// LIRE DES OBJETS MANAGES -- champs, chaines, listes, structures inline.
//
// POURQUOI CE FICHIER EXISTE. Ces fonctions sont nees dans `features/inbox.ts`, ou elles
// n'avaient rien d'une boite de reception : << lire un champ par son nom sur la classe
// concrete d'un objet >> et << parcourir un `List<T>` sans supposer sa foulee >> sont des
// besoins de TOUTE la couche IL2CPP. C'est la meme lecon que `il2cpp/delegate.ts`, sorti de
// `features/expedition-dispatch.ts` pour la meme raison, et dont l'en-tete dit deja : les
// laisser dans un module metier, c'est garantir qu'on les repaye ailleurs.
//
// Et on les payait deja : `il2cpp/project.ts` porte sa propre lecture de `List<T>` a
// `+0x10 / +0x18`, avec la foulee de 8 octets EN DUR -- donc juste pour les references et
// FAUSSE pour les types valeur, silencieusement.
//
// LES DEUX PIEGES QUE CE MODULE EXISTE POUR FERMER :
//
// 1. LA FOULEE D'UNE LISTE SE DERIVE. `List<T>$$get_Item` lit a
//    `items + 0x20 + element_size * i` : `8` pour une reference, mais LA TAILLE DE LA STRUCT
//    pour un type valeur. Mesure : `PromoCodeUserInboxItem.<rewards>` est un
//    `List<thor.UserProgress.Data.RewardDto>` et `RewardDto` est une STRUCT -- une lecture a
//    foulee 8 y rend un COMPTE JUSTE (la taille, elle, se lit bien) et des CHAMPS NULS. Le
//    compte juste est precisement ce qui rend la panne credible.
//
// 2. LES OFFSETS D'UN TYPE VALEUR SONT BOXES. `il2cpp_field_get_offset` inclut le header
//    IL2CPP de `0x10` meme pour un `System.ValueType`. Les appliquer a une structure inline
//    decale de 16 octets par maillon. Mesure : `InboxItemGUID` est une struct a un seul
//    champ `_value:String` -- la dereferencer comme un objet rendait `null`, et un envoi sans
//    identite se lit simplement comme << non reclamable >>, donc la faute etait MUETTE.
//
// PRINCIPE : quand un accesseur IL2CPP manque ou qu'une forme est inattendue, ces fonctions
// REFUSENT de lire et le DISENT (`err`), au lieu de rendre des nombres faux.
//
// NOMMAGE : identifiants en ANGLAIS. Mesure du 2026-08-16 sur `frida/hooks/il2cpp/` : 84
// exports, dont 73 anglais -- `delegate.ts` en etait l'unique exception. Un module que toute
// la couche importe ne doit pas etre la seconde. Les COMMENTAIRES restent francais, la aussi
// par convention du depot.
// ---------------------------------------------------------------------------------------

import {
    getFieldOffset, readIl2cppString,
    class_get_element_class, class_is_valuetype, class_instance_size,
} from "./helpers.js";

export interface ListElements {
    /** Type REFERENCE : les pointeurs d'objet. Type VALEUR : les ADRESSES des structures
     *  inline. Dans les deux cas, ce sur quoi lire les champs. */
    addrs: NativePointer[];
    /** `true` = elements INLINE. Commande la lecture : offsets a DEBOXER, pas de
     *  dereferencement. */
    inline: boolean;
    /** La classe de l'element -- necessaire pour deboxer ses offsets de champ. */
    klass: NativePointer | null;
    /** Renseigne quand on a REFUSE de lire. `addrs` est alors vide, et ce n'est PAS
     *  << la liste est vide >>. */
    err?: string;
}

/** Elements d'un `List<T>` IL2CPP : tableau a +0x10, taille a +0x18, elements a +0x20.
 *  La foulee est DERIVEE de la classe d'element, jamais supposee (cf. piege n°1 en tete). */
export function listElements(list: NativePointer, max = 256): ListElements {
    if (list.isNull()) return { addrs: [], inline: false, klass: null };
    let count: number;
    let array: NativePointer;
    try {
        count = list.add(0x18).readS32();
        array = list.add(0x10).readPointer();
    } catch {
        return { addrs: [], inline: false, klass: null, err: "liste ILLISIBLE" };
    }
    if (array.isNull() || count <= 0) return { addrs: [], inline: false, klass: null };

    if (!class_get_element_class || !class_is_valuetype) {
        return { addrs: [], inline: false, klass: null,
                 err: "`il2cpp_class_get_element_class` / `_is_valuetype` absents -- foulee "
                    + "non etablissable, on REFUSE de lire" };
    }

    let klass: NativePointer | null = null;
    let inline = false;
    let stride = Process.pointerSize;
    try {
        const arrayKlass = array.readPointer();          // `Il2CppClass*` du TABLEAU
        const elemKlass = class_get_element_class(arrayKlass) as NativePointer;
        if (elemKlass && !elemKlass.isNull()) {
            klass = elemKlass;
            inline = (class_is_valuetype(elemKlass) as number) !== 0;
            if (inline) {
                if (!class_instance_size) {
                    return { addrs: [], inline, klass,
                             err: "elements de type VALEUR mais `il2cpp_class_instance_size` "
                                + "absent -- foulee inconnue, on REFUSE de lire" };
                }
                // taille BOXEE - header IL2CPP = taille des champs = la foulee inline.
                stride = (class_instance_size(elemKlass) as number) - 0x10;
                if (!(stride > 0)) {
                    return { addrs: [], inline, klass,
                             err: "foulee calculee <= 0 -- on REFUSE de lire" };
                }
            }
        }
    } catch {
        return { addrs: [], inline: false, klass: null,
                 err: "classe d'element NON RESOLUE -- on REFUSE de lire" };
    }

    const addrs: NativePointer[] = [];
    for (let i = 0; i < Math.min(count, max); i++) {
        const a = array.add(0x20 + i * stride);
        try { addrs.push(inline ? a : a.readPointer()); } catch { break; }
    }
    return { addrs, inline, klass };
}

/** L'offset d'un champ, DEBOXE quand la classe est un type valeur (cf. piege n°2 en tete).
 *  Rend `-1` si le champ n'existe pas -- ⚠ `-1` est *truthy* en JS, tester `< 0`. */
export function unboxedFieldOffset(klass: NativePointer, name: string): number {
    const o = getFieldOffset(klass, name);
    if (o < 0) return -1;
    try {
        if (class_is_valuetype && (class_is_valuetype(klass) as number) !== 0) return o - 0x10;
    } catch { /* on rend l'offset tel quel */ }
    return o;
}

/** L'adresse d'un champ, la classe etant DONNEE -- cas d'une structure inline, qui ne porte
 *  pas d'en-tete et donc pas de `Il2CppClass*` a lire. */
export function fieldIn(base: NativePointer, klass: NativePointer,
                        name: string): NativePointer | null {
    const off = unboxedFieldOffset(klass, name);
    if (off < 0) return null;
    try { return base.add(off); } catch { return null; }
}

/** L'adresse d'un champ sur la classe CONCRETE de l'objet. `null` = le champ n'existe pas sur
 *  cette classe, au sens NON MESURE -- jamais un zero.
 *  ⚠ Reserve aux types REFERENCE : le `Il2CppClass*` est lu dans l'en-tete de l'objet. */
export function field(obj: NativePointer, name: string): NativePointer | null {
    try {
        const klass = obj.readPointer();          // `Il2CppClass*`, premier mot de tout objet
        if (klass.isNull()) return null;
        return fieldIn(obj, klass, name);
    } catch { return null; }
}

/** Le PREMIER nom qui resout, parmi plusieurs candidats.
 *
 *  ⚠ Ce n'est PAS un filet defensif du genre proscrit par le depot (un `getattr` a rallonge
 *  sur des noms esperes). L'usage legitime est celui ou DEUX types NOMMES coexistent
 *  reellement et ou le conteneur decide lequel on tient -- p. ex.
 *  `thor.UserProgress.Data.RewardDto` (struct : `id`/`amount`/`type`) et
 *  `IdunMetaLogic.Loot.Reward` (classe : `Id`/`<Amount>k__BackingField`/`Type`). Passer des
 *  noms qu'on n'a pas verifies au dump transformerait cet outil en devinette. */
export function fieldAny(base: NativePointer, klass: NativePointer,
                         names: string[]): NativePointer | null {
    for (const n of names) {
        const a = fieldIn(base, klass, n);
        if (a) return a;
    }
    return null;
}

/** La chaine managee a une adresse de champ deja resolue. */
export function stringAt(a: NativePointer | null): string | null {
    if (!a) return null;
    try {
        const p = a.readPointer();
        return p.isNull() ? null : readIl2cppString(p);
    } catch { return null; }
}

/** Raccourci : champ par nom sur un objet, lu comme chaine managee. */
export function stringField(obj: NativePointer, name: string): string | null {
    return stringAt(field(obj, name));
}

/** Raccourci : champ par nom sur un objet, lu comme booleen. `null` = champ absent. */
export function boolField(obj: NativePointer, name: string): boolean | null {
    const a = field(obj, name);
    if (!a) return null;
    try { return a.readU8() !== 0; } catch { return null; }
}

/** Raccourci : champ par nom sur un objet, lu comme `Int32`. `null` = champ absent. */
export function intField(obj: NativePointer, name: string): number | null {
    const a = field(obj, name);
    if (!a) return null;
    try { return a.readS32(); } catch { return null; }
}

/** Le nom COURT de la classe d'un objet (`Il2CppClass->name`, a +0x10).
 *
 *  ⚠ Nom COURT, donc potentiellement AMBIGU : `class_get_declaring_type` (helpers) existe
 *  pour lever l'ambiguite des classes imbriquees, ou le nom court collisionne massivement.
 *  Ici on rend ce qu'on lit -- a l'appelant de qualifier s'il en a besoin. */
export function className(obj: NativePointer): string | null {
    try {
        const klass = obj.readPointer();
        if (klass.isNull()) return null;
        const p = klass.add(0x10).readPointer();
        return p.isNull() ? null : p.readUtf8String();
    } catch { return null; }
}
