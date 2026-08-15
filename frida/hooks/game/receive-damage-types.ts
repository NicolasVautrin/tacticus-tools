/** CANAL `receiveDamageTypeThisTurn` (#487-r2) — les PROFILS DE DÉGÂT reçus par une unité
 *  depuis le début du tour, tels que les triggers les lisent.
 *
 *  POURQUOI CE MODULE EXISTE, et pourquoi il n'est pas trois lignes dans `rpc-snapshot.ts`.
 *  Un hook ne s'exécute que dans le process du jeu, donc le valider EXIGERAIT un reinject.
 *  La résolution est donc paramétrée par un `DictProbe` — même dispositif que le `RarityProbe`
 *  de `game/rarity.ts` (#1039) et le `LayoutProbe` de `game/damage-prediction.ts` (#279) — ce
 *  qui rend `resolveReceiveDamageChannel` EXÉCUTABLE hors Frida, sur une disposition capturée
 *  par le RPC `classFields` et sur des MUTATIONS adversariales de cette disposition.
 *  `LIVE_PROBE` en est l'implémentation de production ;
 *  `frida/tools/probe-10008-canaux-du-foyer.ts` en est le harnais.
 *
 *  CE QUE LE NATIF ÉCRIT ET LIT — décompilé relu sur `t6dpr4k06g` :
 *
 *      IdunBattle.Entities.Components.ActorStatisticsComponent$$RegisterReceivedDamage
 *          d = this->[+0x80]                                   // Dictionary<K,int>
 *          if (!d.TryAdd(damageProfileType, 1))                // 1re instance de ce profil
 *              d[damageProfileType] = d[damageProfileType] + 1; // sinon incrément
 *      IdunBattle.Entities.Components.ActorStatisticsComponent$$ResetReceivedDamageThisTurn
 *          this->[+0x80].Clear()
 *
 *  ⚠ CE N'EST PAS UN SCALAIRE, et la fiche #487-r2 le nommait comme tel
 *  (« `receivedDamageThisTurn` (`ActorStatisticsComponent + 0x80`) »). L'OFFSET est juste ;
 *  la NATURE ne l'est pas. `+0x80` est un `Dictionary<DamageProfileType, int>` qui compte le
 *  NOMBRE D'INSTANCES de dégât par PROFIL — jamais une somme de dégâts. Un capteur écrit sur
 *  la foi du nom aurait publié `readS32(+0x80)`, c'est-à-dire les 4 octets bas d'un POINTEUR
 *  de dictionnaire : un entier énorme, non nul, parfaitement plausible pour « des dégâts ont
 *  été reçus ». Le port, lui, a toujours porté la bonne forme
 *  (`UnitComponent.received_damage_this_turn` = `{profil: nb}`, case-202).
 *
 *  ⚠ LE NOM DU CHAMP N'EST PAS CELUI DE LA MÉTHODE QUI LE REMET À ZÉRO. Mesuré au RPC
 *  `classFields` (session 93, lecture pure) : le champ s'appelle **`ReceiveDamageTypeThisTurn`**,
 *  pas `ReceivedDamageThisTurn`. Un `fieldOffsetOr(asClass, "ReceivedDamageThisTurn", 0x80)`
 *  se serait donc REPLIÉ EN SILENCE sur le littéral décompilé — il aurait « marché » sur ce
 *  build par coïncidence d'offset, et serait devenu faux au premier déplacement de champ, sans
 *  que rien ne le dise. D'où la résolution PAR NOM SANS REPLI de ce module.
 *
 *  ⚠ LA DÉFINITION OUVERTE D'UN GÉNÉRIQUE NE PORTE AUCUN LAYOUT — c'est mesuré, et c'est le
 *  cran de garde central ici. RPC `classFields("System.Collections.Generic", "Dictionary`2")`
 *  sur la session 93 rend `boxedSize: 0` et ses **DIX champs à l'offset 0** (idem
 *  `System.Nullable`1`, cf. #1072). Résoudre le layout depuis un nom de classe générique
 *  rendrait donc `_entries@0` et `_count@0` — deux offsets qui ne sont pas négatifs, donc
 *  qu'une garde `< 0` LAISSE PASSER. Le layout est ici dérivé de l'INSTANCE INFLATÉE, obtenue
 *  du TYPE DU CHAMP lui-même, et une garde de PLAGE (offsets dans l'instance, distincts)
 *  refuse explicitement la disposition ouverte.
 *
 *  ⚠ L'ENUM DES CLÉS EST DÉRIVÉ DE `Entry.key`, ET SON NOM PLEIN EST ASSERTÉ. `DamageProfileType`
 *  porte 26 membres ; le confondre avec un autre enum d'ordinaux voisins serait SILENCIEUX EN
 *  ORDINAL (même forme que les cinq `Rarity` de #1039). Le canal REFUSE si le nom ne
 *  correspond pas.
 */
import {
    class_get_name, class_get_namespace, class_instance_size, field_get_offset,
    field_get_type, findClassAnywhere, getFieldInfo, s, type_get_class_or_element_class,
} from "../il2cpp/helpers.js";
import { dumpEnumClass } from "../il2cpp/enum-dump.js";

export const RDT_COMPONENT_NS = "IdunBattle.Entities.Components";
export const RDT_COMPONENT_CLS = "ActorStatisticsComponent";
/** MESURÉ au RPC `classFields`, PAS déduit du nom de `ResetReceivedDamageThisTurn`. */
export const RDT_FIELD = "ReceiveDamageTypeThisTurn";
/** Le nom PLEIN de l'enum de clé, et le seul accepté. */
export const RDT_KEY_ENUM_FULL_NAME = "IdunBattle.Entities.Enum.DamageProfileType";

/** Header d'un objet IL2CPP (`Il2CppClass*` + monitor). `ActorStatisticsComponent` et
 *  `Dictionary<K,V>` sont des types RÉFÉRENCE : `il2cpp_field_get_offset` y rend déjà l'offset
 *  depuis le DÉBUT de l'objet, donc on n'y retranche RIEN. `Entry`, lui, est un ValueType :
 *  son offset et sa taille sont BOXÉS, on en retranche l'en-tête. */
const IL2CPP_OBJECT_HEADER = 0x10;

/** Offset LU au décompilé (`RegisterReceivedDamage`, `ResetReceivedDamageThisTurn`).
 *  DIAGNOSTIC SEUL : il n'entre dans aucune lecture — son unique rôle est de faire apparaître
 *  en `drift` un déplacement de champ au prochain build. */
const DECOMPILED_FIELD_OFF = 0x80;

/** En .NET Core, un slot d'`Entry` LIBÉRÉ porte `next = StartOfFreeList - _freeList`, avec
 *  `StartOfFreeList = -3` : tout `next <= -3` est un trou. Une entrée OCCUPÉE a `next >= -1`.
 *  Le natif n'appelle jamais `Remove` sur ce dictionnaire (seulement `TryAdd`, `set_Item` et
 *  `Clear`), donc `freeCount` doit valoir 0 — c'est publié pour être VÉRIFIABLE, pas supposé. */
const FREE_SLOT_NEXT_MAX = -3;

/** Façade des métadonnées IL2CPP dont dépend la résolution. Elle existe pour rendre
 *  `resolveReceiveDamageChannel` exécutable HORS du process de jeu. */
export interface DictProbe {
    findClass(ns: string, cls: string): NativePointer | null;
    className(klass: NativePointer): string;
    classNamespace(klass: NativePointer): string;
    /** `il2cpp_class_instance_size` — taille d'instance, ou -1 si indisponible. */
    instanceSize(klass: NativePointer): number;
    /** Offset BRUT de `il2cpp_field_get_offset` ; **-1 si le champ n'existe pas**. */
    rawFieldOffset(klass: NativePointer, name: string): number;
    /** Classe du TYPE du champ (élément, si c'est un tableau), ou null. */
    fieldTypeClass(klass: NativePointer, name: string): NativePointer | null;
    /** `{nom: ordinal}` de l'enum, ou null si illisible. */
    enumMembers(klass: NativePointer): Record<string, number> | null;
}

export const LIVE_PROBE: DictProbe = {
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

export interface ReceiveDamageChannel {
    /** Offset de `ActorStatisticsComponent.ReceiveDamageTypeThisTurn` DANS L'INSTANCE. */
    fieldOffset: number;
    /** Offsets DANS L'INSTANCE du dictionnaire (type référence : header compris). */
    entriesOff: number;
    countOff: number;
    /** -1 = `_freeCount` non résolu : la vérification « aucun trou » ne pourra pas être faite. */
    freeCountOff: number;
    /** Taille d'une `Entry` DÉBOXÉE, et offsets de ses champs, tous déboxés. */
    entryStride: number;
    keyOff: number;
    valueOff: number;
    /** -1 = `next` non résolu -> pas de filtrage des slots libérés (dit au consommateur). */
    nextOff: number;
    /** Nom PLEIN de l'enum de clé, DÉRIVÉ de `Entry.key`. */
    keyEnumFullName: string;
    /** `{nom: ordinal}` de CET enum-là, pour que le consommateur nomme sans recopier. */
    keyEnumMembers: Record<string, number>;
}

export interface ReceiveDamageResolution {
    /** `null` = canal REFUSÉ. Aucun repli, jamais d'offset deviné. */
    channel: ReceiveDamageChannel | null;
    errors: string[];
    drift: string[];
}

/** Résout le canal, ou REFUSE en disant pourquoi.
 *
 *  Aucun chemin ne rend d'offset de repli. Le RPC publie alors
 *  `receiveDamageTypeThisTurn: null` = PAS MESURÉ — jamais `{}`, qui est la mesure « cette
 *  unité n'a reçu aucun dégât ce tour », c'est-à-dire l'état MAJORITAIRE : le rabattre ferait
 *  une panne indiscernable du cas normal, exactement le vice qu'`#969-r4` documente pour
 *  `currentOwnerIsEnvironment`. */
export function resolveReceiveDamageChannel(probe: DictProbe): ReceiveDamageResolution {
    const errors: string[] = [];
    const drift: string[] = [];

    const comp = probe.findClass(RDT_COMPONENT_NS, RDT_COMPONENT_CLS);
    if (comp === null) {
        errors.push("CLASSE INTROUVABLE (#487-r2) : " + RDT_COMPONENT_NS + "."
            + RDT_COMPONENT_CLS + " -- aucun canal de profils recus");
        return { channel: null, errors, drift };
    }
    const off = probe.rawFieldOffset(comp, RDT_FIELD);
    if (off < 0) {
        errors.push("CHAMP INTROUVABLE (#487-r2) : " + RDT_COMPONENT_CLS + "." + RDT_FIELD
            + " -- absent des metadonnees IL2CPP de ce build. Le capteur REFUSE de lire"
            + " plutot que de retomber sur l'offset decompile 0x"
            + DECOMPILED_FIELD_OFF.toString(16) + ".");
        return { channel: null, errors, drift };
    }
    const compSize = probe.instanceSize(comp);
    if (compSize > 0 && (off < IL2CPP_OBJECT_HEADER || off >= compSize)) {
        errors.push("OFFSET HORS INSTANCE (#487-r2) : " + RDT_COMPONENT_CLS + "." + RDT_FIELD
            + " -- offset " + off + " hors [" + IL2CPP_OBJECT_HEADER + "," + compSize
            + "[ ; champ STATIQUE ou litteral, pas un champ d'instance");
        return { channel: null, errors, drift };
    }
    if (off !== DECOMPILED_FIELD_OFF) {
        drift.push(RDT_COMPONENT_CLS + "." + RDT_FIELD + " : offset " + off + " (0x"
            + off.toString(16) + "), lu 0x" + DECOMPILED_FIELD_OFF.toString(16)
            + " au decompile -- la lecture SUIT, la doc est ce qui devient faux");
    }

    // --- Le dictionnaire, par son INSTANCE INFLATÉE (jamais par le nom générique) ----------
    const dictClass = probe.fieldTypeClass(comp, RDT_FIELD);
    if (dictClass === null) {
        errors.push("TYPE DE CHAMP NON RESOLU (#487-r2) : " + RDT_COMPONENT_CLS + "."
            + RDT_FIELD + " -- sans la classe INFLATEE du dictionnaire, aucun layout n'est"
            + " derivable (la definition OUVERTE rend tous ses offsets a 0, mesure session 93)");
        return { channel: null, errors, drift };
    }
    const entriesOff = probe.rawFieldOffset(dictClass, "_entries");
    const countOff = probe.rawFieldOffset(dictClass, "_count");
    if (entriesOff < 0 || countOff < 0) {
        errors.push("DICTIONNAIRE NON RESOLU (#487-r2) : champs `_entries`/`_count` absents ("
            + entriesOff + "/" + countOff + ")");
        return { channel: null, errors, drift };
    }
    // GARDE DE DÉFINITION OUVERTE. Mesurée : `Dictionary`2` ouvert rend TOUS ses champs a 0,
    // et `0` n'est pas negatif -- la garde `< 0` ci-dessus le laisse passer. Deux champs
    // DISTINCTS ne peuvent pas partager un offset, et aucun champ d'instance ne vit sous le
    // header. C'est cette garde-la, et elle seule, qui separe « inflate » d'« ouvert ».
    const dictSize = probe.instanceSize(dictClass);
    if (entriesOff < IL2CPP_OBJECT_HEADER || countOff < IL2CPP_OBJECT_HEADER
        || entriesOff === countOff) {
        errors.push("DISPOSITION OUVERTE REFUSEE (#487-r2) : `_entries`@" + entriesOff
            + " / `_count`@" + countOff + " -- une definition GENERIQUE NON INFLATEE rend tous"
            + " ses champs a l'offset 0 (mesure session 93 : `Dictionary`2` -> 10 champs a 0)."
            + " Lire a ces offsets rendrait le pointeur de classe pour un compteur.");
        return { channel: null, errors, drift };
    }
    if (dictSize > 0 && (entriesOff >= dictSize || countOff >= dictSize)) {
        errors.push("DISPOSITION HORS INSTANCE (#487-r2) : `_entries`@" + entriesOff
            + " / `_count`@" + countOff + " hors instance de taille " + dictSize);
        return { channel: null, errors, drift };
    }
    let freeCountOff = probe.rawFieldOffset(dictClass, "_freeCount");
    if (freeCountOff < IL2CPP_OBJECT_HEADER) {
        drift.push("temoin perdu : `_freeCount` non resolu (" + freeCountOff + ") -- le"
            + " controle << aucun slot libere >> ne pourra pas etre fait");
        freeCountOff = -1;
    }

    // --- `Entry`, DÉDUITE DU TYPE DE `_entries` (donc du dictionnaire RÉEL) ---------------
    // Le stride ne se suppose pas : c'est exactement la faute #276-r1 (`ENTRY_SIZE = 32` sur
    // une entree de 24) qui faisait lire a cote des la 2e cle.
    const entryClass = probe.fieldTypeClass(dictClass, "_entries");
    if (entryClass === null) {
        errors.push("ENTRY NON RESOLUE (#487-r2) : classe element de `_entries` illisible");
        return { channel: null, errors, drift };
    }
    const entryBoxed = probe.instanceSize(entryClass);
    const entryStride = entryBoxed - IL2CPP_OBJECT_HEADER;
    const keyOff = probe.rawFieldOffset(entryClass, "key") - IL2CPP_OBJECT_HEADER;
    const valueOff = probe.rawFieldOffset(entryClass, "value") - IL2CPP_OBJECT_HEADER;
    if (entryStride <= 0 || keyOff < 0 || valueOff < 0) {
        errors.push("ENTRY NON MESURABLE (#487-r2) : stride=" + entryStride + " key=" + keyOff
            + " value=" + valueOff + " -- un stride suppose ferait lire a cote des la 2e cle"
            + " (faute #276-r1)");
        return { channel: null, errors, drift };
    }
    if (keyOff + 4 > entryStride || valueOff + 4 > entryStride) {
        errors.push("ENTRY HORS BORNES (#487-r2) : key@" + keyOff + " value@" + valueOff
            + " ne tiennent pas dans un stride de " + entryStride);
        return { channel: null, errors, drift };
    }
    const rawNext = probe.rawFieldOffset(entryClass, "next");
    let nextOff = rawNext < 0 ? -1 : rawNext - IL2CPP_OBJECT_HEADER;
    if (nextOff < 0 || nextOff + 4 > entryStride) {
        drift.push("temoin perdu : `Entry.next` non resolu (" + rawNext + ") -- les slots"
            + " LIBERES ne pourront pas etre filtres ; sans Remove natif il ne doit pas y en"
            + " avoir, mais le capteur ne pourra plus le verifier");
        nextOff = -1;
    }

    // --- L'ENUM DE CLÉ, dérivé de `Entry.key`, nom PLEIN asserté --------------------------
    const keyEnumClass = probe.fieldTypeClass(entryClass, "key");
    if (keyEnumClass === null) {
        errors.push("ENUM DE CLE NON RESOLU (#487-r2) : type de `Entry.key` illisible --"
            + " l'ordinal publie ne serait qualifiable par personne");
        return { channel: null, errors, drift };
    }
    const ns = probe.classNamespace(keyEnumClass);
    const full = (ns ? ns + "." : "") + probe.className(keyEnumClass);
    if (full !== RDT_KEY_ENUM_FULL_NAME) {
        errors.push("ENUM MAL APPARIE (#487-r2) : `Entry.key` a pour type `" + full
            + "`, attendu `" + RDT_KEY_ENUM_FULL_NAME + "`. Une confusion d'enum serait"
            + " SILENCIEUSE EN ORDINAL : seul le nom PLEIN la rend visible.");
        return { channel: null, errors, drift };
    }
    const members = probe.enumMembers(keyEnumClass);
    if (members === null || Object.keys(members).length === 0) {
        errors.push("ENUM VIDE (#487-r2) : " + full + " n'expose aucun membre lisible");
        return { channel: null, errors, drift };
    }

    return {
        channel: {
            fieldOffset: off, entriesOff, countOff, freeCountOff,
            entryStride, keyOff, valueOff, nextOff,
            keyEnumFullName: full, keyEnumMembers: members,
        },
        errors, drift,
    };
}

/** Ce que le capteur publie PAR UNITÉ. `profiles === null` = PAS MESURÉ. */
export interface ReceiveDamageReading {
    /** `{ "<ordinal DamageProfileType>": nombre d'instances }`. `{}` = mesuré, rien reçu. */
    profiles: Record<string, number> | null;
    /** `_count` brut du dictionnaire (entrées occupées + trous). `null` = pas mesuré. */
    count: number | null;
    /** `_freeCount` : DOIT valoir 0 (le natif n'appelle jamais `Remove`). `null` = pas lu. */
    freeCount: number | null;
    /** Nombre de slots LIBÉRÉS sautés. `null` = `Entry.next` non résolu, donc pas de filtre. */
    freeSlotsSkipped: number | null;
    /** Cause NOMMÉE quand `profiles === null`. */
    error?: string;
}

const NOT_MEASURED: ReceiveDamageReading = {
    profiles: null, count: null, freeCount: null, freeSlotsSkipped: null,
};

/** Lit le dictionnaire sur UN `ActorStatisticsComponent`.
 *
 *  ⚠ Chaque `null` porte sa CAUSE (`error`). La version naïve de ce capteur aurait rendu
 *  `null` pour quatre causes distinctes — canal refusé, composant nul, dictionnaire nul,
 *  taille aberrante — et la mesure aurait dit « muet » sans dire de quoi : c'est exactement
 *  ce qui a coûté une fenêtre à `#347-r3`. */
export function readReceiveDamageTypes(
    comp: NativePointer | null, ch: ReceiveDamageChannel | null, cap = 4096,
): ReceiveDamageReading {
    if (ch === null) return { ...NOT_MEASURED, error: "canal non resolu" };
    if (comp === null || comp.isNull()) {
        return { ...NOT_MEASURED, error: "ActorStatisticsComponent nul" };
    }
    try {
        const dict = comp.add(ch.fieldOffset).readPointer();
        // Le natif lui-même teste `if (this->[+0x80] != 0)` avant d'y toucher, et LÈVE sinon
        // (`FUN_1801f5460`). Un dictionnaire nul est donc un état que le natif ne tolère pas :
        // on le NOMME au lieu de rendre `{}`.
        if (dict.isNull()) return { ...NOT_MEASURED, error: "dictionnaire nul" };
        const count = dict.add(ch.countOff).readS32();
        const freeCount = ch.freeCountOff >= 0 ? dict.add(ch.freeCountOff).readS32() : null;
        if (count < 0 || count > cap) {
            return { ...NOT_MEASURED, count, freeCount, error: "_count aberrant : " + count };
        }
        if (count === 0) {
            // MESURE, pas panne : l'unité n'a reçu aucun dégât ce tour. C'est le cas
            // MAJORITAIRE, et le distinguer d'un `null` est tout l'objet du tri-état.
            return { profiles: {}, count, freeCount, freeSlotsSkipped: 0 };
        }
        const entries = dict.add(ch.entriesOff).readPointer();
        if (entries.isNull()) {
            return { ...NOT_MEASURED, count, freeCount, error: "_entries nul" };
        }
        // Il2CppArray : longueur @+0x18, données dès +0x20. On BORNE par la longueur réelle
        // du tableau : `_count` seul suffirait dans un dictionnaire sain, mais un `_count`
        // corrompu ferait lire hors du tableau.
        const arrayLen = entries.add(0x18).readS32();
        if (arrayLen < 0 || arrayLen > cap) {
            return { ...NOT_MEASURED, count, freeCount,
                error: "longueur de `_entries` aberrante : " + arrayLen };
        }
        const n = Math.min(count, arrayLen);
        const profiles: Record<string, number> = {};
        let skipped = 0;
        for (let i = 0; i < n; i++) {
            const e = entries.add(0x20 + i * ch.entryStride);
            if (ch.nextOff >= 0 && e.add(ch.nextOff).readS32() <= FREE_SLOT_NEXT_MAX) {
                skipped++;
                continue;
            }
            profiles[String(e.add(ch.keyOff).readS32())] = e.add(ch.valueOff).readS32();
        }
        return { profiles, count, freeCount,
            freeSlotsSkipped: ch.nextOff >= 0 ? skipped : null };
    } catch (err) {
        return { ...NOT_MEASURED, error: "lecture en faute : " + (err as Error).message };
    }
}
