/** CANAL `weapons` (#419-r1-tr14-r5-r2-r1-r2-r1-r2) — les armes d'une unité TELLES QUE L'ECS
 *  les porte, et non telles que le catalogue les décrit.
 *
 *  POURQUOI CE MODULE EXISTE. Le port lit les armes dans le gameconfig
 *  (`GC.unit(visualId).weapons`, cf. `engine/playbook/adjacent_unit_preference.py::_unit_weapons`
 *  et le foyer `engine/services/battle_query.py::has_ranged_weapon`) ; le natif, lui, itère le
 *  `WeaponsComponent` de l'entité. En bataille standard les deux concordent — `BC.Units[].Weapons`
 *  dérive du catalogue — mais **rien ne le vérifie**, et un montage qui patcherait
 *  `BC.Units[].Weapons` seul les ferait diverger EN SILENCE. C'est ce qui interdisait de piloter
 *  par ce levier le discriminant de la règle dynamique d'attaque normale.
 *
 *  Comme tout hook, il n'est validable qu'en process : la résolution est donc paramétrée par un
 *  `WeaponsProbe`, exécutable hors Frida sur une disposition capturée par `classFields` et sur
 *  ses mutations adversariales. Même dispositif que `game/rarity.ts` (#1039).
 *
 *  CE QUE LE NATIF LIT — décompilé relu sur `t6dpr4k06g`, trois foyers concordants :
 *
 *      IdunBattle.Entities.Components.WeaponsComponent$$.ctor
 *          this->[+0x10] = new List<WeaponProfile>()          // UNIQUE champ du composant
 *      IdunBattle.Entities.Components.WeaponsComponent$$HasRangedWeapon(minRange)
 *          foreach (w in this->[+0x10])
 *              if (!w.IsMelee && (!minRange.HasValue || w.Range.Value >= minRange.Value))
 *                  return true;
 *          return false;
 *      IdunBattle.Core.Services.BattleQuery$$FindRangedWeapon(unit)
 *          if (!EntityExtensions.IsUnit(unit)) return null;
 *          foreach (w in TryGetComponent<WeaponsComponent>(unit)->[+0x10])
 *              if (!w.IsMelee) set.Add(w);
 *          return SelectMaxRangeWeapon(set);
 *
 *  ⚠ `WeaponsComponent$$Copy` confirme l'unicité du champ (`clone[2] = new List<T>(this->[+0x10])`,
 *  soit `+0x10` sur un `longlong*`), et `classFields` (session 93, lecture pure) le NOMME :
 *  **`<Weapons>k__BackingField`** — un backing field d'auto-property. Chercher `"Weapons"` ne
 *  résout RIEN : c'est le nom entre chevrons qu'il faut, et c'est pour ça qu'il est écrit ici
 *  une seule fois, en constante, plutôt que deviné au site.
 *
 *  LE PROFIL D'ARME — `IdunShared.Battle.WeaponProfile`, mesuré au RPC `classFields` :
 *      DamageProfileType @+0x10 (enum)  ·  DamageProfile @+0x18 (objet)
 *      Hits              @+0x20 (Int32) ·  Range         @+0x24 (Nullable<Int32>)
 *  et son `ToString` recoupe exactement ces trois-là (`+0x10`, `+0x20`, puis `+0x24` en
 *  `GetValueOrDefault` quand l'arme n'est pas melee).
 *
 *  ⚠ `IsMelee` N'EST PAS « l'arme a une portée ». `IdunShared.Battle.WeaponProfile$$get_IsMelee` :
 *
 *      if (!Range.HasValue) return true;
 *      return Range.Value < 2;
 *
 *  Le seuil est `>= 2`, donc une arme de portée **1 serait MELEE**. Les deux critères coïncident
 *  sur ce gameconfig (aucune arme à `Range == 1`), et c'est précisément pourquoi il faut le
 *  décompilé : la coïncidence ne se voit pas, et le port a déjà mirroré la bonne règle
 *  (`_weapon_is_melee`). Ce module publie les DEUX : le brut (`range`, `rangeHasValue`) et le
 *  dérivé (`isMelee`), pour que le consommateur puisse REFAIRE le calcul au lieu de le croire.
 *  `get_IsRanged` est littéralement `get_IsMelee() ^ 1` — il n'est donc pas publié séparément.
 *
 *  ⚠ LE `Nullable<Int32>` DE `Range` NE SE SUPPOSE PAS. `#347-r3` a mesuré, sur ce build même,
 *  que `Nullable<UnitPositionId>` vaut `{hasValue@+0, value@+8}` — ni la convention
 *  `{value; hasValue}` que le capteur de mouvement supposait, ni le `{hasValue@+0, value@+4}`
 *  que `game/match-state.ts` avait relevé pour un autre type : **l'offset de `value` suit
 *  l'alignement de `T`**. La disposition est donc DÉRIVÉE du champ, jamais écrite.
 *
 *  ⚠ AUCUNE INVOCATION. Ce module ne fait que lire de la mémoire — pas un `invokeMethod`.
 *  C'est délibéré : `#175` a mesuré qu'un SEUL appel natif mal choisi depuis `combatSnapshot`
 *  (`GetNormalAttackPrediction` contre une Machine) rend toute pose d'effet ultérieure sur le
 *  runner un no-op SILENCIEUX. Un capteur de configuration n'a aucune raison de prendre ce
 *  risque, et `HasRangedWeapon` se recalcule intégralement depuis ce qui est publié.
 */
import {
    class_get_name, class_get_namespace, class_instance_size, field_get_offset,
    field_get_type, findClassAnywhere, getFieldInfo, s, type_get_class_or_element_class,
} from "../il2cpp/helpers.js";
import { dumpEnumClass } from "../il2cpp/enum-dump.js";

export const WEAPONS_COMPONENT_NS = "IdunBattle.Entities.Components";
export const WEAPONS_COMPONENT_CLS = "WeaponsComponent";
/** Backing field d'auto-property : `"Weapons"` seul ne résout RIEN. Nom MESURÉ. */
export const WEAPONS_FIELD = "<Weapons>k__BackingField";
export const WEAPON_PROFILE_NS = "IdunShared.Battle";
export const WEAPON_PROFILE_CLS = "WeaponProfile";
export const WP_DAMAGE_PROFILE_TYPE_FIELD = "DamageProfileType";
export const WP_HITS_FIELD = "Hits";
export const WP_RANGE_FIELD = "Range";
/** Le nom PLEIN de l'enum de profil, et le seul accepté. */
export const WEAPON_PROFILE_ENUM_FULL_NAME = "IdunBattle.Entities.Enum.DamageProfileType";

/** Seuil de `get_IsMelee`, LU au décompilé (`Range.Value < 2`). Ce n'est pas un réglage :
 *  c'est le littéral du natif, cité ici pour que le mirror soit relisable d'un coup d'oeil. */
const MELEE_RANGE_MAX_EXCLUSIVE = 2;

const IL2CPP_OBJECT_HEADER = 0x10;

/** Offsets LUS au décompilé / mesurés au RPC `classFields` sur `t6dpr4k06g`. DIAGNOSTIC SEUL :
 *  ils n'entrent dans AUCUNE lecture — leur unique rôle est de faire apparaître un déplacement
 *  de champ en `drift` au prochain build. */
const DECOMPILED_WEAPONS_OFF = 0x10;
const DECOMPILED_WP_TYPE_OFF = 0x10;
const DECOMPILED_WP_HITS_OFF = 0x20;
const DECOMPILED_WP_RANGE_OFF = 0x24;

export interface WeaponsProbe {
    findClass(ns: string, cls: string): NativePointer | null;
    className(klass: NativePointer): string;
    classNamespace(klass: NativePointer): string;
    instanceSize(klass: NativePointer): number;
    /** Offset BRUT ; **-1 si le champ n'existe pas**. */
    rawFieldOffset(klass: NativePointer, name: string): number;
    fieldTypeClass(klass: NativePointer, name: string): NativePointer | null;
    enumMembers(klass: NativePointer): Record<string, number> | null;
}

export const LIVE_PROBE: WeaponsProbe = {
    findClass: (ns, cls) => {
        const k = findClassAnywhere(ns, cls);
        return k === null || k.isNull() ? null : k;
    },
    className: (klass) => s(class_get_name(klass) as NativePointer),
    classNamespace: (klass) => s(class_get_namespace(klass) as NativePointer),
    instanceSize: (klass) => (class_instance_size === null
        ? -1 : (class_instance_size(klass) as number)),
    rawFieldOffset: (klass, name) => {
        const f = getFieldInfo(klass, name);
        return f === null ? -1 : (field_get_offset(f) as number);
    },
    fieldTypeClass: (klass, name) => {
        const f = getFieldInfo(klass, name);
        if (f === null) return null;
        const tc = type_get_class_or_element_class(
            field_get_type(f) as NativePointer) as NativePointer;
        return tc.isNull() ? null : tc;
    },
    enumMembers: (klass) => {
        const raw = dumpEnumClass(klass);
        if (raw === null) return null;
        const out: Record<string, number> = {};
        for (const k of Object.keys(raw)) {
            const v = parseInt(raw[k], 10);
            if (Number.isFinite(v)) out[k] = v;
        }
        return out;
    },
};

export interface WeaponsChannel {
    /** Offset de `WeaponsComponent.<Weapons>k__BackingField` DANS L'INSTANCE. */
    listOffset: number;
    /** Offsets de `WeaponProfile` (type RÉFÉRENCE : header compris, on ne déboxe pas). */
    typeOffset: number;
    hitsOffset: number;
    rangeOffset: number;
    /** Disposition INTERNE du `Nullable<Int32>` de `Range`, DÉRIVÉE. */
    rangeHasValueOff: number;
    rangeValueOff: number;
    /** Nom PLEIN de l'enum de profil, DÉRIVÉ du champ. */
    profileEnumFullName: string;
    profileEnumMembers: Record<string, number>;
}

export interface WeaponsResolution {
    channel: WeaponsChannel | null;
    errors: string[];
    drift: string[];
}

/** Résout le canal, ou REFUSE en disant pourquoi. Aucun offset de repli, jamais. */
export function resolveWeaponsChannel(probe: WeaponsProbe): WeaponsResolution {
    const errors: string[] = [];
    const drift: string[] = [];

    const comp = probe.findClass(WEAPONS_COMPONENT_NS, WEAPONS_COMPONENT_CLS);
    if (comp === null) {
        errors.push("CLASSE INTROUVABLE (#419) : " + WEAPONS_COMPONENT_NS + "."
            + WEAPONS_COMPONENT_CLS + " -- aucun canal d'armes par entite");
        return { channel: null, errors, drift };
    }
    const listOffset = probe.rawFieldOffset(comp, WEAPONS_FIELD);
    if (listOffset < 0) {
        errors.push("CHAMP INTROUVABLE (#419) : " + WEAPONS_COMPONENT_CLS + "."
            + WEAPONS_FIELD + " -- absent des metadonnees. C'est un BACKING FIELD"
            + " d'auto-property : chercher `Weapons` sans les chevrons ne resout rien.");
        return { channel: null, errors, drift };
    }
    const compSize = probe.instanceSize(comp);
    if (compSize > 0 && (listOffset < IL2CPP_OBJECT_HEADER || listOffset >= compSize)) {
        errors.push("OFFSET HORS INSTANCE (#419) : " + WEAPONS_COMPONENT_CLS + "."
            + WEAPONS_FIELD + " -- offset " + listOffset + " hors ["
            + IL2CPP_OBJECT_HEADER + "," + compSize + "[");
        return { channel: null, errors, drift };
    }
    if (listOffset !== DECOMPILED_WEAPONS_OFF) {
        drift.push(WEAPONS_COMPONENT_CLS + "." + WEAPONS_FIELD + " : offset " + listOffset
            + ", lu 0x" + DECOMPILED_WEAPONS_OFF.toString(16) + " au decompile");
    }

    const wp = probe.findClass(WEAPON_PROFILE_NS, WEAPON_PROFILE_CLS);
    if (wp === null) {
        errors.push("CLASSE INTROUVABLE (#419) : " + WEAPON_PROFILE_NS + "."
            + WEAPON_PROFILE_CLS + " -- les elements de la liste seraient illisibles");
        return { channel: null, errors, drift };
    }
    const wpSize = probe.instanceSize(wp);
    const off = (name: string, decompiled: number): number => {
        const o = probe.rawFieldOffset(wp, name);
        if (o < 0) {
            errors.push("CHAMP INTROUVABLE (#419) : " + WEAPON_PROFILE_CLS + "." + name);
            return -1;
        }
        if (wpSize > 0 && (o < IL2CPP_OBJECT_HEADER || o >= wpSize)) {
            errors.push("OFFSET HORS INSTANCE (#419) : " + WEAPON_PROFILE_CLS + "." + name
                + " -- offset " + o + " hors [" + IL2CPP_OBJECT_HEADER + "," + wpSize + "[");
            return -1;
        }
        if (o !== decompiled) {
            drift.push(WEAPON_PROFILE_CLS + "." + name + " : offset " + o + ", lu 0x"
                + decompiled.toString(16) + " au decompile");
        }
        return o;
    };
    const typeOffset = off(WP_DAMAGE_PROFILE_TYPE_FIELD, DECOMPILED_WP_TYPE_OFF);
    const hitsOffset = off(WP_HITS_FIELD, DECOMPILED_WP_HITS_OFF);
    const rangeOffset = off(WP_RANGE_FIELD, DECOMPILED_WP_RANGE_OFF);
    if (typeOffset < 0 || hitsOffset < 0 || rangeOffset < 0) {
        return { channel: null, errors, drift };
    }

    // --- La disposition du `Nullable<Int32>`, DÉRIVÉE (cf. #347-r3 / #579-r1) --------------
    // On NE re-dérive pas à la main : la classe INFLATÉE du Nullable vient du TYPE du champ,
    // et ses deux membres donnent leurs offsets. La définition OUVERTE, elle, rend `hasValue`
    // ET `value` à 0 (mesure session 93) : c'est cet état-là que la garde d'égalité refuse.
    const nullableClass = probe.fieldTypeClass(wp, WP_RANGE_FIELD);
    if (nullableClass === null) {
        errors.push("TYPE DE CHAMP NON RESOLU (#419) : " + WEAPON_PROFILE_CLS + "."
            + WP_RANGE_FIELD + " -- disposition du Nullable non derivable");
        return { channel: null, errors, drift };
    }
    const rawHv = probe.rawFieldOffset(nullableClass, "hasValue");
    const rawV = probe.rawFieldOffset(nullableClass, "value");
    if (rawHv < 0 || rawV < 0) {
        errors.push("NULLABLE NON RESOLU (#419) : membres `hasValue`/`value` absents ("
            + rawHv + "/" + rawV + ")");
        return { channel: null, errors, drift };
    }
    const rangeHasValueOff = rawHv - IL2CPP_OBJECT_HEADER;
    const rangeValueOff = rawV - IL2CPP_OBJECT_HEADER;
    if (rangeHasValueOff < 0 || rangeValueOff < 0 || rangeHasValueOff === rangeValueOff) {
        errors.push("NULLABLE NON INFLATE (#419) : hasValue@" + rangeHasValueOff
            + " value@" + rangeValueOff + " -- une definition GENERIQUE ouverte rend ses DEUX"
            + " membres a l'offset 0 (mesure session 93). Lire dans cet etat rendrait le bit"
            + " hasValue a la place de la portee -- exactement la faute #579-r1.");
        return { channel: null, errors, drift };
    }

    const enumClass = probe.fieldTypeClass(wp, WP_DAMAGE_PROFILE_TYPE_FIELD);
    if (enumClass === null) {
        errors.push("ENUM NON RESOLU (#419) : type de " + WEAPON_PROFILE_CLS + "."
            + WP_DAMAGE_PROFILE_TYPE_FIELD + " illisible");
        return { channel: null, errors, drift };
    }
    const ns = probe.classNamespace(enumClass);
    const full = (ns ? ns + "." : "") + probe.className(enumClass);
    if (full !== WEAPON_PROFILE_ENUM_FULL_NAME) {
        errors.push("ENUM MAL APPARIE (#419) : " + WEAPON_PROFILE_CLS + "."
            + WP_DAMAGE_PROFILE_TYPE_FIELD + " a pour type `" + full + "`, attendu `"
            + WEAPON_PROFILE_ENUM_FULL_NAME + "`. Une confusion serait SILENCIEUSE EN ORDINAL.");
        return { channel: null, errors, drift };
    }
    const members = probe.enumMembers(enumClass);
    if (members === null || Object.keys(members).length === 0) {
        errors.push("ENUM VIDE (#419) : " + full + " n'expose aucun membre lisible");
        return { channel: null, errors, drift };
    }

    return {
        channel: {
            listOffset, typeOffset, hitsOffset, rangeOffset,
            rangeHasValueOff, rangeValueOff,
            profileEnumFullName: full, profileEnumMembers: members,
        },
        errors, drift,
    };
}

/** UNE arme, telle que le natif la porte. */
export interface WeaponReading {
    /** Ordinal `DamageProfileType`. */
    damageProfileType: number;
    hits: number;
    /** `Range.Value`, ou `null` si le `Nullable` est VIDE — une MESURE, pas une panne. */
    range: number | null;
    rangeHasValue: boolean;
    /** `IdunShared.Battle.WeaponProfile$$get_IsMelee` = `!Range.HasValue || Range.Value < 2`.
     *  CALCULÉ ici (mirror 1:1), jamais invoqué — le brut au-dessus permet de le refaire. */
    isMelee: boolean;
}

/** Ce que le capteur publie PAR UNITÉ. `weapons === null` = PAS MESURÉ. */
export interface WeaponsReading {
    /** `[]` = mesuré, l'unité ne porte aucune arme (état réel : les objets de décor). */
    weapons: WeaponReading[] | null;
    /** `IdunBattle.Entities.Components.WeaponsComponent$$HasRangedWeapon(minRange = null)`,
     *  recalculé depuis la liste : `true` dès qu'UNE arme n'est pas `IsMelee`. `null` = pas
     *  mesuré — et le tri-état compte ici, parce que `false` est la réponse MAJORITAIRE. */
    hasRangedWeapon: boolean | null;
    /** Cause NOMMÉE quand `weapons === null`. */
    error?: string;
}

const NOT_MEASURED: WeaponsReading = { weapons: null, hasRangedWeapon: null };

/** Lit les armes sur UN `WeaponsComponent`.
 *
 *  ⚠ `listClassFields` dérive le layout de `List<T>` de la CLASSE RUNTIME de la liste — pas
 *  du type DÉCLARÉ du champ, qui est l'interface `IReadOnlyList<T>` et ne porte aucun champ.
 *  Le `.ctor` du composant instancie bien une `List<WeaponProfile>`, mais c'est l'objet qui
 *  fait foi, pas le contrat. */
export function readWeapons(
    comp: NativePointer | null, ch: WeaponsChannel | null,
    listLayout: { itemsOff: number; sizeOff: number } | null, cap = 64,
): WeaponsReading {
    if (ch === null) return { ...NOT_MEASURED, error: "canal non resolu" };
    if (comp === null || comp.isNull()) {
        // MESURE : toutes les entités ne portent pas de `WeaponsComponent`. Le natif le teste
        // (`TryGetComponent`) et rend `null` sans lever — on le NOMME au lieu de rendre `[]`,
        // qui voudrait dire « l'unité porte le composant, et il est vide ».
        return { ...NOT_MEASURED, error: "WeaponsComponent absent" };
    }
    if (listLayout === null) {
        return { ...NOT_MEASURED, error: "layout de List<T> non resolu" };
    }
    try {
        const list = comp.add(ch.listOffset).readPointer();
        if (list.isNull()) return { ...NOT_MEASURED, error: "liste nulle" };
        const items = list.add(listLayout.itemsOff).readPointer();
        const size = list.add(listLayout.sizeOff).readS32();
        if (items.isNull()) return { ...NOT_MEASURED, error: "_items nul" };
        if (size < 0 || size > cap) {
            return { ...NOT_MEASURED, error: "_size aberrant : " + size };
        }
        const weapons: WeaponReading[] = [];
        for (let i = 0; i < size; i++) {
            const w = items.add(0x20 + i * Process.pointerSize).readPointer();
            if (w.isNull()) continue;
            const hasValue = w.add(ch.rangeOffset + ch.rangeHasValueOff).readU8() !== 0;
            const range = hasValue
                ? w.add(ch.rangeOffset + ch.rangeValueOff).readS32() : null;
            weapons.push({
                damageProfileType: w.add(ch.typeOffset).readS32(),
                hits: w.add(ch.hitsOffset).readS32(),
                range, rangeHasValue: hasValue,
                // `get_IsMelee` VERBATIM : pas de `Range` -> melee ; sinon `Range < 2`.
                isMelee: !hasValue || (range as number) < MELEE_RANGE_MAX_EXCLUSIVE,
            });
        }
        return { weapons, hasRangedWeapon: weapons.some((w) => !w.isMelee) };
    } catch (err) {
        return { ...NOT_MEASURED, error: "lecture en faute : " + (err as Error).message };
    }
}
