/** CANAL `rarity` (#1039) — la RARETÉ EN BATAILLE d'une unité, telle que les gates la lisent.
 *
 *  POURQUOI CE MODULE EXISTE, et pourquoi il n'est pas trois lignes dans `rpc-snapshot.ts`.
 *  Un hook ne s'exécute que dans le process du jeu, donc le valider EXIGERAIT un reinject.
 *  La résolution est donc paramétrée par un `RarityProbe` — même dispositif que le
 *  `LayoutProbe` de `game/damage-prediction.ts` (#279) — ce qui rend `resolveRarityChannel`
 *  EXÉCUTABLE hors Frida, sur une disposition capturée par le RPC `classFields` et sur des
 *  MUTATIONS adversariales de cette disposition. `LIVE_PROBE` en est l'implémentation de
 *  production ; `frida/tools/probe-1039-rarity-canal.ts` en est le harnais.
 *
 *  CE QUE LE NATIF LIT — quatre foyers, tous le MÊME champ, décompilé relu sur `rnca9r7q6c` :
 *
 *      IdunBattle.Entities.UnitExtensions$$HasRarity
 *          GetBaseUnitComponent(unit)->[+0x74] == rarity
 *      IdunBattle.Entities.Formulas.UnitsWithRaritySelector$$Select
 *          GetBaseUnitComponent(entity)->[+0x74] == this->[+0x20]
 *      IdunBattle.Entities.Triggers.HasRarityTrigger$$ShouldTrigger
 *          GetBaseUnitComponent(entity)->[+0x74] == this->[+0x18]
 *      IdunBattle.Entities.Factories.UnitFactory$$InitBaseComponent
 *          GetBaseUnitComponent(entity)->[+0x74] = config->[+0x80]
 *
 *  Le quatrième est la SOURCE : la fabrique recopie `UnitConfiguration.Rarity` dans le
 *  composant. Les trois premiers sont les CONSOMMATEURS. Le canal publie donc les deux, et
 *  c'est le COMPOSANT qui fait foi — voir « pourquoi pas la configuration » ci-dessous.
 *
 *  ⚠ DEUX STRUCTS, LE MÊME `0x74`, ET C'EST LE PIÈGE CENTRAL DE CETTE TRANCHE.
 *  Mesuré au runtime (RPC `classFields`, build `rnca9r7q6c`, session 88) :
 *
 *      IdunBattle.Entities.Components.BaseUnitComponent.Rarity                    offset 116 (0x74)
 *      IdunBattle.Configuration.UnitConfiguration.AbilityVariablesMultiplierPercentage
 *                                                                                offset 116 (0x74)
 *      IdunBattle.Configuration.UnitConfiguration.Rarity                          offset 128 (0x80)
 *
 *  `rpc-snapshot.ts` lit DÉJÀ `UnitConfiguration+0x74` sous le nom `UCFG.mult`. Recopier
 *  « 0x74 » d'un struct vers l'autre rendrait donc `100` ou `180` là où on attend `0..5`,
 *  sans la moindre erreur. Aucun offset n'est écrit en dur ici : tout passe par
 *  `rawFieldOffset(<classe>, "Rarity")`, et les littéraux ci-dessus ne servent qu'à faire
 *  APPARAÎTRE une dérive (champ `drift`), jamais à lire.
 *
 *  ⚠ CINQ ENUMS DU BUILD PORTENT EXACTEMENT LES SIX MÊMES MEMBRES AUX MÊMES ORDINAUX —
 *  `idun.meta.Rarity`, `IdunMetaLogic.UserProgress.Model.UnitRarity`, `…ItemRarity`,
 *  `…UpgradeRarity`, `…XpBookRarity` (lus dans `data/symbols/<build>/frida/enums.tsv`). Une
 *  confusion d'appariement serait donc SILENCIEUSE EN ORDINAL. Celui que le COMBAT lit est
 *  `idun.meta.Rarity` — type DÉCLARÉ du paramètre `rarity` dans `frida/methods.tsv`, aux
 *  quatre foyers (`DSLSelectors.UnitsWithRarity`, `DSLTriggers.HasRarity`,
 *  `UnitExtensions.HasRarity`, `UnitsWithRaritySelector..ctor`). Le résolveur ne se contente
 *  donc pas de lire un ordinal : il DÉRIVE la classe de l'enum DU CHAMP LUI-MÊME et REFUSE
 *  le canal si son nom PLEIN n'est pas `idun.meta.Rarity`. C'est le seul cran qui rende la
 *  confusion visible.
 *
 *  POURQUOI LE COMPOSANT FAIT FOI, ET PAS LA CONFIGURATION. Trois raisons, toutes mesurées :
 *   1. c'est ce que les trois gates LISENT (le décompilé ci-dessus) ;
 *   2. `readUnitConfig` remonte à la configuration par `BattleQuery$$GetUnitConfig(visualId)`,
 *      une jointure N→1 : deux entités partageant une `VisualId` (même unité dans les deux
 *      camps) partagent la configuration rendue, alors qu'elles portent chacune LEUR
 *      composant ;
 *   3. et surtout `readUnitConfig` ne trouve sa `VisualId` qu'en filtrant sur la classe
 *      `IdunBattle.Entities.Components.UnitComponent` — une MACHINE OF WAR porte un
 *      `MachineComponent`, donc `readUnitConfig` lui rend `{error: "visualId introuvable"}`.
 *      Publier la rareté par cette seule voie l'aurait rendue AVEUGLE AUX MoW, c'est-à-dire
 *      aveugle aux porteurs mêmes des abilities mythiques qui motivent le capteur.
 *  `IdunBattle.Entities.UnitExtensions$$GetBaseUnitComponent`, elle, sert les deux : son
 *  chemin rapide rend `entity+0x28`, son repli passe par `TryGetComponent<BaseUnitComponent>`
 *  — et `MachineComponent` DÉRIVE de `BaseUnitComponent`.
 */
import {
    class_get_name, class_get_namespace, class_instance_size, field_get_offset,
    field_get_type, findClassAnywhere, getFieldInfo, s, type_get_class_or_element_class,
} from "../il2cpp/helpers.js";
import { dumpEnumClass } from "../il2cpp/enum-dump.js";

/** Le nom PLEIN, et le seul accepté. Cf. le bloc « CINQ ENUMS » ci-dessus. */
export const RARITY_ENUM_FULL_NAME = "idun.meta.Rarity";

export const RARITY_COMPONENT_NS = "IdunBattle.Entities.Components";
export const RARITY_COMPONENT_CLS = "BaseUnitComponent";
export const RARITY_CONFIG_NS = "IdunBattle.Configuration";
export const RARITY_CONFIG_CLS = "UnitConfiguration";
/** Le nom du champ, identique des deux côtés — c'est la CLASSE qui les sépare, pas le nom. */
export const RARITY_FIELD = "Rarity";

/** Header d'un objet IL2CPP (`Il2CppClass*` + monitor). `BaseUnitComponent` et
 *  `UnitConfiguration` sont des types RÉFÉRENCE : `il2cpp_field_get_offset` y rend déjà
 *  l'offset depuis le DÉBUT de l'objet, donc on n'y retranche RIEN (contrairement à un
 *  ValueType boxé). La constante ne sert qu'à borner par le bas la plage d'instance. */
const IL2CPP_OBJECT_HEADER = 0x10;

/** Offsets LUS au décompilé (`InitBaseComponent`) et re-mesurés au RPC `classFields` sur
 *  `rnca9r7q6c`. DIAGNOSTIC SEUL : ils n'entrent dans aucune lecture — leur unique rôle est
 *  de faire apparaître en `drift` un déplacement de champ au prochain build. Les écrire
 *  ailleurs qu'ici serait exactement la RVA en dur que la doctrine interdit. */
const DECOMPILED_COMPONENT_OFF = 0x74;
const DECOMPILED_CONFIG_OFF = 0x80;

/** Façade des métadonnées IL2CPP dont dépend la résolution. Elle existe pour rendre
 *  `resolveRarityChannel` exécutable HORS du process de jeu. */
export interface RarityProbe {
    findClass(ns: string, cls: string): NativePointer | null;
    className(klass: NativePointer): string;
    classNamespace(klass: NativePointer): string;
    /** `il2cpp_class_instance_size` — taille d'instance, ou -1 si indisponible. */
    instanceSize(klass: NativePointer): number;
    /** Offset BRUT de `il2cpp_field_get_offset` ; **-1 si le champ n'existe pas**. */
    rawFieldOffset(klass: NativePointer, name: string): number;
    /** Classe du TYPE du champ, ou null si le champ ou son type ne se résout pas. */
    fieldTypeClass(klass: NativePointer, name: string): NativePointer | null;
    /** `{nom: ordinal}` de l'enum, ou null si illisible. */
    enumMembers(klass: NativePointer): Record<string, number> | null;
    sameClass(a: NativePointer, b: NativePointer): boolean;
}

export const LIVE_PROBE: RarityProbe = {
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
    sameClass: (a, b) => a.equals(b),
};

export interface RarityChannel {
    /** Offset de `BaseUnitComponent.Rarity` DANS L'INSTANCE du composant (header compris —
     *  type référence, on ne déboxe pas). C'est le `+0x74` des trois gates. */
    componentOffset: number;
    /** Offset de `UnitConfiguration.Rarity`, ou **-1** = pas résolu. TÉMOIN seul : la valeur
     *  que la fabrique COPIE, publiée pour qu'un désaccord config↔composant se VOIE. */
    configOffset: number;
    /** Nom PLEIN de l'enum, DÉRIVÉ du champ. Toujours `idun.meta.Rarity` — sinon le canal
     *  est refusé (`channel === null`). */
    enumFullName: string;
    /** `{nom: ordinal}` de CET enum-là, pour que le consommateur nomme sans recopier. */
    members: Record<string, number>;
}

export interface RarityResolution {
    /** `null` = canal REFUSÉ. Aucun repli, jamais d'offset deviné. */
    channel: RarityChannel | null;
    /** Ce qui a fait refuser. Vide quand `channel !== null`. */
    errors: string[];
    /** Ce qui a bougé sans empêcher de lire (champ déplacé, témoin de config perdu). */
    drift: string[];
}

/** Résout le canal, ou REFUSE en disant pourquoi.
 *
 *  Aucun chemin ne rend d'offset de repli : `rawFieldOffset` rend **-1** sur un nom absent,
 *  et `comp.add(-1).readS32()` lirait du garbage sans lever — c'est la panne exacte que
 *  `fieldOffsetOr` documente dans `il2cpp/helpers.ts` (le `-1` est *truthy* en JavaScript).
 *  Ici, un champ introuvable rend `channel = null`, et le RPC publie `rarity: null`
 *  = PAS MESURÉ, jamais `0` (= `Rarity.Common`, une valeur parfaitement plausible : c'est
 *  ce qui rendrait la panne indiscernable d'une mesure). */
export function resolveRarityChannel(probe: RarityProbe): RarityResolution {
    const errors: string[] = [];
    const drift: string[] = [];

    const comp = probe.findClass(RARITY_COMPONENT_NS, RARITY_COMPONENT_CLS);
    if (comp === null) {
        errors.push("CLASSE INTROUVABLE (#1039) : " + RARITY_COMPONENT_NS + "."
            + RARITY_COMPONENT_CLS + " -- aucun canal de rarete");
        return { channel: null, errors, drift };
    }
    const off = probe.rawFieldOffset(comp, RARITY_FIELD);
    if (off < 0) {
        errors.push("CHAMP INTROUVABLE (#1039) : " + RARITY_COMPONENT_CLS + "."
            + RARITY_FIELD + " -- absent des metadonnees IL2CPP de ce build. Le capteur"
            + " REFUSE de lire plutot que de retomber sur un offset de repli.");
        return { channel: null, errors, drift };
    }
    const size = probe.instanceSize(comp);
    if (size > 0 && (off < IL2CPP_OBJECT_HEADER || off >= size)) {
        errors.push("OFFSET HORS INSTANCE (#1039) : " + RARITY_COMPONENT_CLS + "."
            + RARITY_FIELD + " -- offset " + off + " hors [" + IL2CPP_OBJECT_HEADER + ","
            + size + "[ ; champ STATIQUE ou litteral, pas un champ d'instance");
        return { channel: null, errors, drift };
    }
    const enumClass = probe.fieldTypeClass(comp, RARITY_FIELD);
    if (enumClass === null) {
        errors.push("TYPE DE CHAMP NON RESOLU (#1039) : " + RARITY_COMPONENT_CLS + "."
            + RARITY_FIELD + " -- l'enum ne peut pas etre nomme, donc l'ordinal ne peut pas"
            + " etre qualifie");
        return { channel: null, errors, drift };
    }
    const ns = probe.classNamespace(enumClass);
    const full = (ns ? ns + "." : "") + probe.className(enumClass);
    if (full !== RARITY_ENUM_FULL_NAME) {
        errors.push("ENUM MAL APPARIE (#1039) : " + RARITY_COMPONENT_CLS + "."
            + RARITY_FIELD + " a pour type `" + full + "`, attendu `"
            + RARITY_ENUM_FULL_NAME + "`. CINQ enums du build portent EXACTEMENT les six"
            + " memes membres aux memes ordinaux : la confusion serait SILENCIEUSE EN"
            + " ORDINAL, seul le nom PLEIN la rend visible.");
        return { channel: null, errors, drift };
    }
    const members = probe.enumMembers(enumClass);
    if (members === null || Object.keys(members).length === 0) {
        errors.push("ENUM VIDE (#1039) : " + full + " n'expose aucun membre lisible --"
            + " l'ordinal publie ne serait nommable par personne");
        return { channel: null, errors, drift };
    }
    if (off !== DECOMPILED_COMPONENT_OFF) {
        drift.push(RARITY_COMPONENT_CLS + "." + RARITY_FIELD + " : offset " + off
            + " (0x" + off.toString(16) + "), lu 0x"
            + DECOMPILED_COMPONENT_OFF.toString(16) + " au decompile -- la lecture SUIT,"
            + " la doc est ce qui devient faux");
    }

    // --- TÉMOIN : `UnitConfiguration.Rarity`, la source que la fabrique copie -------------
    // Sa perte ne peut PAS bloquer le canal (le composant fait foi) : elle part en `drift`.
    let configOffset = -1;
    const cfg = probe.findClass(RARITY_CONFIG_NS, RARITY_CONFIG_CLS);
    if (cfg === null) {
        drift.push("temoin perdu : classe " + RARITY_CONFIG_NS + "." + RARITY_CONFIG_CLS
            + " introuvable");
    } else {
        const coff = probe.rawFieldOffset(cfg, RARITY_FIELD);
        const csize = probe.instanceSize(cfg);
        const ctype = probe.fieldTypeClass(cfg, RARITY_FIELD);
        if (coff < 0) {
            drift.push("temoin perdu : " + RARITY_CONFIG_CLS + "." + RARITY_FIELD
                + " absent des metadonnees");
        } else if (csize > 0 && (coff < IL2CPP_OBJECT_HEADER || coff >= csize)) {
            drift.push("temoin perdu : " + RARITY_CONFIG_CLS + "." + RARITY_FIELD
                + " a l'offset " + coff + ", hors [" + IL2CPP_OBJECT_HEADER + "," + csize
                + "[");
        } else if (ctype === null || !probe.sameClass(ctype, enumClass)) {
            // Identité de POINTEUR de classe, pas égalité de nom : c'est ce qui distingue
            // `idun.meta.Rarity` de ses quatre homonymes d'ordinaux.
            drift.push("temoin perdu : " + RARITY_CONFIG_CLS + "." + RARITY_FIELD
                + " n'a pas le meme type d'enum que " + RARITY_COMPONENT_CLS + "."
                + RARITY_FIELD);
        } else {
            configOffset = coff;
            if (coff !== DECOMPILED_CONFIG_OFF) {
                drift.push(RARITY_CONFIG_CLS + "." + RARITY_FIELD + " : offset " + coff
                    + " (0x" + coff.toString(16) + "), lu 0x"
                    + DECOMPILED_CONFIG_OFF.toString(16) + " au decompile");
            }
        }
    }

    return {
        channel: { componentOffset: off, configOffset, enumFullName: full, members },
        errors, drift,
    };
}
