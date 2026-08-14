/** CANAL `tertiary` (#1036-r8) — l'ABILITY TERTIAIRE (relique / mythique de MoW) et SON NIVEAU,
 *  lus sur la `UnitConfiguration` par une voie qui SERT AUSSI LES MACHINES OF WAR.
 *
 *  POURQUOI CE MODULE EXISTE, et pourquoi il n'est pas trois lignes dans `rpc-snapshot.ts`.
 *  Un hook ne s'exécute que dans le process du jeu, donc le valider EXIGERAIT un reinject.
 *  La résolution est donc paramétrée par un `TertiaryProbe` — même dispositif que le
 *  `RarityProbe` de `game/rarity.ts` (#1039) et le `LayoutProbe` de `game/damage-prediction.ts`
 *  (#279) — ce qui rend `resolveTertiaryChannel` EXÉCUTABLE hors Frida, sur une disposition
 *  capturée par le RPC `classFields` et sur des MUTATIONS adversariales de cette disposition.
 *  `LIVE_PROBE` en est l'implémentation de production ; `frida/tools/probe-1072-capteurs-fenetre.ts`
 *  en est le harnais.
 *
 *  LE TROU QUE CE CANAL FERME (#1036-r8, mesuré session 89). `necroReanimator` monté à
 *  `--equip-mythic …:4` porte `TertiaryAbilityLevel = 4` ÉCRIT dans la BC, et AUCUN canal live ne
 *  le publiait : `combatSnapshot.units[].unitConfig` rend `{"error": "visualId introuvable"}` pour
 *  toute Machine, `units[].abilityStates` et `decisionView.mows[].abilities` ne listent que ses
 *  ACTIVES. Côté port, `UnitContext.tertiary_ability` restait `None` et
 *  `tertiary_ability_level` `0` — donc toute magnitude d'aura de MoW était structurellement nulle.
 *
 *  CE QUE LE NATIF LIT — décompilé relu sur `rnca9r7q6c` :
 *
 *      IdunBattle.Entities.Factories.UnitFactory$$AddConfiguredAbilities
 *          Nullable<TriggeredAbilityType>.get_HasValue(config+0xb0)
 *          -> Nullable<…>.get_Value(config+0xb0) -> TriggeredAbilityConfigId.op_Implicit
 *          -> TriggeredAbilityComponent$$TryAdd(comp, id, tertiaryAbilityState, group = 3)
 *      IdunBattle.Entities.Factories.UnitFactory$$InitBaseComponent
 *          baseUnitComponent.<Id @+0x10> = config.<Id @+0x10>
 *
 *  Le second est LA JOINTURE, et c'est lui qui rend la voie MoW-compatible : la clé est
 *  `BaseUnitComponent.Id`, obtenu par la fonction NOMMÉE
 *  `IdunBattle.Entities.UnitExtensions$$GetBaseUnitComponent` — celle-là même que la fabrique
 *  appelle, et qui sert les DEUX familles (`MachineComponent` DÉRIVE de `BaseUnitComponent`).
 *  C'est exactement le contournement que #1039 a dû faire pour la rareté : `readUnitConfig`
 *  cherche sa `VisualId` en filtrant sur la classe `IdunBattle.Entities.Components.UnitComponent`,
 *  qu'une MoW ne porte pas.
 *
 *  ⚠ TROIS PIÈGES, ET AUCUN N'EST DEVINABLE DU DÉCOMPILÉ.
 *
 *  1. **Le layout de `Nullable<T>` n'est LU NULLE PART.** Le natif passe par `get_HasValue` /
 *     `get_Value` : le décompilé ne montre donc jamais où sont `hasValue` et `value` dans les
 *     8 octets. `readShields` (`rpc-snapshot.ts`) documente cette incertitude et publie les mots
 *     bruts faute de mieux. Ici on fait un cran de plus : les deux offsets sont **DÉRIVÉS DES
 *     MÉTADONNÉES** (`class_get_fields` de l'instance inflatée `Nullable<TriggeredAbilityType>`).
 *     Les mots bruts restent publiés pour diagnostic, jamais pour lire.
 *
 *     ⚠ **ET CE MAILLON PEUT ÉCHOUER SANS QUE LE NIVEAU SOIT PERDU — mesuré, pas redouté.** Le
 *     RPC `classFields` rend, pour la DÉFINITION OUVERTE `System.Nullable\`1` du build en vol
 *     (`rnca9r7q6c`, session 89, lecture pure) : `boxedSize: 0`, `hasValue` à l'offset `0`,
 *     `value` à l'offset `0` — exactement le piège que `game/damage-prediction.ts` documente sur
 *     `List\`1`. Si `type_get_class_or_element_class` rendait cette définition plutôt que
 *     l'instance INFLATÉE, dériver donnerait deux offsets identiques et faux. D'où la
 *     RÉPARTITION des rôles ci-dessous : le `Nullable` et son enum sont des **TÉMOINS**
 *     (dégradation bornée, `drift`), le NIVEAU est **BLOQUANT**. C'est le niveau que #1036-r8
 *     demande ; faire tomber tout le canal avec le `Nullable` rendrait le résidu ouvert pour une
 *     donnée qu'il ne réclamait pas.
 *
 *  2. **L'ENUM. `TertiaryAbility` est un `TriggeredAbilityType`, PAS un `ActiveAbilityType`** —
 *     et une confusion serait SILENCIEUSE EN ORDINAL : `TriggeredAbilityType` partage **233**
 *     ordinaux avec `ActiveAbilityType` et **458** avec `EffectType` (CLAUDE.md, #270-c). La
 *     `UnitConfiguration` porte littéralement les deux voisins (`ActiveAbilities` @+0xa0 =
 *     `List<ActiveAbilityType>`, `PassiveAbilities` @+0xa8 = `List<TriggeredAbilityType>`), donc
 *     l'erreur est à portée d'une ligne. Le résolveur DÉRIVE l'enum du champ `value` du `Nullable`
 *     et REFUSE si son nom PLEIN n'est pas `IdunBattle.Entities.Enum.TriggeredAbilityType`.
 *
 *  3. **`0` EST UNE MESURE, PAS UNE PANNE.** `TertiaryAbilityLevel` est un `Idun.Shared.Level`
 *     (struct à un seul champ `val`), et `0` y signifie « VERROUILLÉ » — c'est ce que porte toute
 *     entrée sans relique (`Idun.Shared.Level$$CreateValidOrLockedLevel`), et c'est exactement la
 *     valeur sur laquelle `TryGetVariableArrayForLevel` LÈVE. Un capteur qui replierait sa panne
 *     sur `0` rendrait donc l'absence de mesure indiscernable d'un verrou réel. `null` = PAS
 *     MESURÉ, sans aucune exception.
 *
 *  ⚠ AUCUN OFFSET N'EST ÉCRIT EN DUR POUR LIRE. Tout passe par `rawFieldOffset(<classe>, <nom>)` ;
 *  les littéraux `DECOMPILED_*` ci-dessous ne servent qu'à faire APPARAÎTRE une dérive (`drift`).
 */
import {
    class_get_name, class_get_namespace, class_instance_size, class_is_valuetype,
    field_get_offset, field_get_type, findClassAnywhere, getFieldInfo, s,
    type_get_class_or_element_class,
} from "../il2cpp/helpers.js";

/** Le nom PLEIN de l'enum de l'ability tertiaire, et le seul accepté. Cf. le piège 2. */
export const TERTIARY_ENUM_FULL_NAME = "IdunBattle.Entities.Enum.TriggeredAbilityType";
/** Le nom PLEIN du type du NIVEAU. `Idun.Shared.Level` est un struct `{ int val; }`. */
export const LEVEL_TYPE_FULL_NAME = "Idun.Shared.Level";

export const CONFIG_NS = "IdunBattle.Configuration";
export const CONFIG_CLS = "UnitConfiguration";
export const COMPONENT_NS = "IdunBattle.Entities.Components";
export const COMPONENT_CLS = "BaseUnitComponent";
export const BATTLE_CONFIG_CLS = "BattleConfiguration";

/** Les champs LUS, par leur nom. `Id` est LA clé de jointure (`InitBaseComponent`). */
export const F_ID = "Id";
export const F_TERTIARY = "TertiaryAbility";
export const F_TERTIARY_LEVEL = "TertiaryAbilityLevel";
export const F_TERTIARY_MULT = "TertiaryAbilityVariablesMultiplierPercentage";
export const F_UNITS = "Units";
/** Champs INTERNES de `System.Nullable<T>` — dérivés, jamais supposés (piège 1). */
export const F_NULLABLE_HAS = "hasValue";
export const F_NULLABLE_VALUE = "value";
/** Champ interne d'`Idun.Shared.Level`. */
export const F_LEVEL_VAL = "val";

/** Header d'un objet IL2CPP (`Il2CppClass*` + monitor). Pour un type RÉFÉRENCE
 *  (`UnitConfiguration`, `BaseUnitComponent`, `BattleConfiguration`) `il2cpp_field_get_offset`
 *  rend déjà l'offset depuis le DÉBUT de l'objet — on n'y retranche RIEN. Pour un ValueType
 *  (`Nullable<T>`, `Level`) il rend l'offset BOXÉ : le header EST inclus et doit être retranché,
 *  faute de quoi chaque maillon décale de 16 octets (cf. `class_is_valuetype` dans
 *  `il2cpp/helpers.ts`). Le résolveur ne SUPPOSE pas laquelle des deux formes s'applique : il
 *  interroge `isValueType`. */
const IL2CPP_OBJECT_HEADER = 0x10;

/** Offsets LUS au décompilé (`AddConfiguredAbilities`, `InitBaseComponent`) et re-mesurés au RPC
 *  `classFields`. DIAGNOSTIC SEUL : ils n'entrent dans aucune lecture. */
const DECOMPILED_TERTIARY_OFF = 0xb0;
const DECOMPILED_TERTIARY_LEVEL_OFF = 0xc0;
const DECOMPILED_TERTIARY_MULT_OFF = 0x78;
const DECOMPILED_CONFIG_ID_OFF = 0x10;
const DECOMPILED_COMPONENT_ID_OFF = 0x10;

/** Façade des métadonnées IL2CPP dont dépend la résolution. Elle existe pour rendre
 *  `resolveTertiaryChannel` exécutable HORS du process de jeu. */
export interface TertiaryProbe {
    findClass(ns: string, cls: string): NativePointer | null;
    className(klass: NativePointer): string;
    classNamespace(klass: NativePointer): string;
    /** `il2cpp_class_instance_size` — taille d'instance (header compris), ou -1. */
    instanceSize(klass: NativePointer): number;
    /** `il2cpp_class_is_valuetype` — décide si les offsets de champ sont BOXÉS.
     *  `null` = indéterminable ; le résolveur REFUSE plutôt que de choisir. */
    isValueType(klass: NativePointer): boolean | null;
    /** Offset BRUT de `il2cpp_field_get_offset` ; **-1 si le champ n'existe pas**. */
    rawFieldOffset(klass: NativePointer, name: string): number;
    /** Classe du TYPE du champ, ou null si le champ ou son type ne se résout pas. */
    fieldTypeClass(klass: NativePointer, name: string): NativePointer | null;
}

export const LIVE_PROBE: TertiaryProbe = {
    findClass: (ns, cls) => {
        const k = findClassAnywhere(ns, cls);
        return k === null || k.isNull() ? null : k;
    },
    className: (klass) => s(class_get_name(klass) as NativePointer),
    classNamespace: (klass) => s(class_get_namespace(klass) as NativePointer),
    instanceSize: (klass) => (class_instance_size === null
        ? -1 : (class_instance_size(klass) as number)),
    isValueType: (klass) => (class_is_valuetype === null
        ? null : (class_is_valuetype(klass) as number) !== 0),
    rawFieldOffset: (klass, name) => {
        // `getFieldInfo` REMONTE la chaîne de parents — c'est ce qu'on veut pour
        // `BaseUnitComponent.Id`, que `MachineComponent` HÉRITE (c'est tout l'objet de la voie
        // MoW). Pour les champs internes d'un ValueType (`Nullable<T>`, `Level`) la chaîne est
        // triviale, et `class_get_fields` fonctionne aussi bien sur une instance INFLATÉE.
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
};

export interface TertiaryChannel {
    /** Offset de `BattleConfiguration.Units` — la liste des `UnitConfiguration`. */
    unitsOffset: number;
    /** Offset de `UnitConfiguration.Id` — la clé de jointure côté CONFIGURATION. */
    configIdOffset: number;
    /** Offset de `BaseUnitComponent.Id` — la même clé, côté ENTITÉ. */
    componentIdOffset: number;
    /** Offset du `Nullable<TriggeredAbilityType> TertiaryAbility`. **-1 = TÉMOIN perdu** :
     *  l'ability n'est pas lisible, le NIVEAU l'est toujours (cf. piège 1). */
    tertiaryOffset: number;
    /** Offsets INTERNES du `Nullable`, DÉBOXÉS (relatifs au début de la struct).
     *  **-1 = non dérivable** — l'ability n'est alors PAS publiée, jamais devinée. */
    nullableHasValueOffset: number;
    nullableValueOffset: number;
    /** Offset du `Level TertiaryAbilityLevel`, plus l'offset interne de son `val` (déboxé —
     *  vaut 0 sur ce build, mais il est DÉRIVÉ, pas supposé). */
    levelOffset: number;
    levelValOffset: number;
    /** Offset du multiplicateur de variables de l'ability tertiaire. -1 = TÉMOIN perdu :
     *  sa disparition ne bloque PAS le canal (le niveau seul ferme #1036-r8). */
    multiplierOffset: number;
    /** Nom PLEIN de l'enum, DÉRIVÉ du champ `value` du `Nullable`. Vaut
     *  `IdunBattle.Entities.Enum.TriggeredAbilityType` ou **`null`** — et `null` INTERDIT de
     *  publier l'ability : un ordinal que personne ne peut qualifier n'a pas à sortir (233
     *  ordinaux communs avec `ActiveAbilityType`, 458 avec `EffectType`). */
    abilityEnumFullName: string | null;
    /** Vrai SSI les trois conditions de lecture de l'ability sont réunies (offset du champ,
     *  layout du `Nullable`, enum nommé). Un seul booléen à tester, côté lecture. */
    abilityReadable: boolean;
}

export interface TertiaryResolution {
    /** `null` = canal REFUSÉ. Aucun repli, jamais d'offset deviné. */
    channel: TertiaryChannel | null;
    /** Ce qui a fait refuser. Vide quand `channel !== null`. */
    errors: string[];
    /** Ce qui a bougé sans empêcher de lire (champ déplacé, témoin perdu). */
    drift: string[];
}

/** Offset d'un champ, RAMENÉ au début de la struct quand la classe est un ValueType.
 *  Rend `-1` si le champ manque, et `null` si on ne SAIT PAS si la classe est un ValueType —
 *  cas où lire serait un pari à 16 octets près. */
function unboxedOffset(
    probe: TertiaryProbe, klass: NativePointer, name: string,
): number | null {
    const raw = probe.rawFieldOffset(klass, name);
    if (raw < 0) return -1;
    const vt = probe.isValueType(klass);
    if (vt === null) return null;
    return vt ? raw - IL2CPP_OBJECT_HEADER : raw;
}

/** Résout le canal, ou REFUSE en disant pourquoi.
 *
 *  Aucun chemin ne rend d'offset de repli : `rawFieldOffset` rend **-1** sur un nom absent, et
 *  `cfg.add(-1).readS32()` lirait du garbage sans lever — la panne exacte que `fieldOffsetOr`
 *  documente dans `il2cpp/helpers.ts` (le `-1` est *truthy* en JavaScript). Ici, un champ
 *  introuvable rend `channel = null`, et le RPC publie `tertiary: null` = PAS MESURÉ. */
export function resolveTertiaryChannel(probe: TertiaryProbe): TertiaryResolution {
    const errors: string[] = [];
    const drift: string[] = [];
    const refus = (): TertiaryResolution => ({ channel: null, errors, drift });

    const cfg = probe.findClass(CONFIG_NS, CONFIG_CLS);
    if (cfg === null) {
        errors.push("CLASSE INTROUVABLE (#1036-r8) : " + CONFIG_NS + "." + CONFIG_CLS
            + " -- aucun canal d'ability tertiaire");
        return refus();
    }
    const comp = probe.findClass(COMPONENT_NS, COMPONENT_CLS);
    if (comp === null) {
        errors.push("CLASSE INTROUVABLE (#1036-r8) : " + COMPONENT_NS + "." + COMPONENT_CLS
            + " -- la CLE DE JOINTURE entite->configuration n'est pas lisible, et c'est"
            + " precisement elle qui rend la voie compatible avec les MACHINES OF WAR");
        return refus();
    }
    const bc = probe.findClass(CONFIG_NS, BATTLE_CONFIG_CLS);
    if (bc === null) {
        errors.push("CLASSE INTROUVABLE (#1036-r8) : " + CONFIG_NS + "." + BATTLE_CONFIG_CLS
            + " -- la liste des UnitConfiguration n'est pas atteignable");
        return refus();
    }

    // --- les trois offsets de STRUCTURE (types REFERENCE : rien a deboxer) ---------------
    const unitsOffset = probe.rawFieldOffset(bc, F_UNITS);
    if (unitsOffset < 0) {
        errors.push("CHAMP INTROUVABLE (#1036-r8) : " + BATTLE_CONFIG_CLS + "." + F_UNITS);
        return refus();
    }
    const configIdOffset = probe.rawFieldOffset(cfg, F_ID);
    if (configIdOffset < 0) {
        errors.push("CHAMP INTROUVABLE (#1036-r8) : " + CONFIG_CLS + "." + F_ID
            + " -- sans la cle, la jointure entite->configuration est impossible");
        return refus();
    }
    const componentIdOffset = probe.rawFieldOffset(comp, F_ID);
    if (componentIdOffset < 0) {
        errors.push("CHAMP INTROUVABLE (#1036-r8) : " + COMPONENT_CLS + "." + F_ID
            + " -- sans la cle, la jointure entite->configuration est impossible");
        return refus();
    }

    // --- le NIVEAU (Idun.Shared.Level) — SEUL ETAGE BLOQUANT ------------------------------
    // C'est LUI que #1036-r8 reclame : sans le niveau, toute magnitude d'aura de MoW reste
    // structurellement nulle. Le `Nullable` et l'enum, plus bas, sont des TEMOINS.
    const cfgSize = probe.instanceSize(cfg);
    const levelOffset = probe.rawFieldOffset(cfg, F_TERTIARY_LEVEL);
    if (levelOffset < 0) {
        errors.push("CHAMP INTROUVABLE (#1036-r8) : " + CONFIG_CLS + "." + F_TERTIARY_LEVEL
            + " -- c'est LE champ que #1036-r8 demande ; sans lui la magnitude d'une aura"
            + " de MoW reste structurellement nulle");
        return refus();
    }
    if (cfgSize > 0 && (levelOffset < IL2CPP_OBJECT_HEADER || levelOffset >= cfgSize)) {
        errors.push("OFFSET HORS INSTANCE (#1036-r8) : " + CONFIG_CLS + "."
            + F_TERTIARY_LEVEL + " -- offset " + levelOffset + " hors ["
            + IL2CPP_OBJECT_HEADER + "," + cfgSize + "[");
        return refus();
    }
    const levelClass = probe.fieldTypeClass(cfg, F_TERTIARY_LEVEL);
    if (levelClass === null) {
        errors.push("TYPE DE CHAMP NON RESOLU (#1036-r8) : " + CONFIG_CLS + "."
            + F_TERTIARY_LEVEL);
        return refus();
    }
    const lns = probe.classNamespace(levelClass);
    const lfull = (lns ? lns + "." : "") + probe.className(levelClass);
    if (lfull !== LEVEL_TYPE_FULL_NAME) {
        errors.push("TYPE DE NIVEAU MAL APPARIE (#1036-r8) : " + CONFIG_CLS + "."
            + F_TERTIARY_LEVEL + " a pour type `" + lfull + "`, attendu `"
            + LEVEL_TYPE_FULL_NAME + "`. C'est ce type qui donne son sens au ZERO"
            + " (= VERROUILLE, cf. Idun.Shared.Level$$CreateValidOrLockedLevel) ; le lire"
            + " comme un entier nu ferait passer un verrou pour un niveau.");
        return refus();
    }
    const levelValOffset = unboxedOffset(probe, levelClass, F_LEVEL_VAL);
    if (levelValOffset === null || levelValOffset < 0) {
        errors.push("CHAMP INTERNE DU NIVEAU NON DERIVABLE (#1036-r8) : `" + F_LEVEL_VAL
            + "` sur `" + lfull + "` -> " + levelValOffset);
        return refus();
    }

    // --- TEMOIN : le Nullable<TriggeredAbilityType> ----------------------------------------
    // DEGRADATION BORNEE, jamais un refus (cf. piege 1 de l'en-tete : la definition OUVERTE
    // `Nullable`1` rend boxedSize 0 et deux offsets nuls -- mesure du build en vol). Chaque
    // sortie de cet etage laisse `abilityReadable = false` et le niveau intact.
    let tertiaryOffset = probe.rawFieldOffset(cfg, F_TERTIARY);
    let hasOff = -1;
    let valOff = -1;
    let abilityEnumFullName: string | null = null;
    if (tertiaryOffset < 0) {
        drift.push("temoin perdu : " + CONFIG_CLS + "." + F_TERTIARY
            + " absent des metadonnees -- le NIVEAU reste lisible, l'ability non");
    } else if (cfgSize > 0
        && (tertiaryOffset < IL2CPP_OBJECT_HEADER || tertiaryOffset >= cfgSize)) {
        drift.push("temoin perdu : " + CONFIG_CLS + "." + F_TERTIARY + " a l'offset "
            + tertiaryOffset + ", hors [" + IL2CPP_OBJECT_HEADER + "," + cfgSize + "[");
        tertiaryOffset = -1;
    } else {
        if (tertiaryOffset !== DECOMPILED_TERTIARY_OFF) {
            drift.push(CONFIG_CLS + "." + F_TERTIARY + " : offset " + tertiaryOffset
                + " (0x" + tertiaryOffset.toString(16) + "), lu 0x"
                + DECOMPILED_TERTIARY_OFF.toString(16) + " au decompile -- la lecture SUIT,"
                + " la doc est ce qui devient faux");
        }
        const nullableClass = probe.fieldTypeClass(cfg, F_TERTIARY);
        if (nullableClass === null) {
            drift.push("temoin perdu : le type de " + CONFIG_CLS + "." + F_TERTIARY + " ne se"
                + " resout pas -- le layout du Nullable ne peut pas etre DERIVE, et le"
                + " decompile ne le montre nulle part (le natif passe par"
                + " get_HasValue/get_Value)");
        } else {
            const h = unboxedOffset(probe, nullableClass, F_NULLABLE_HAS);
            const v = unboxedOffset(probe, nullableClass, F_NULLABLE_VALUE);
            const nullableSize = probe.instanceSize(nullableClass);
            const utile = nullableSize - IL2CPP_OBJECT_HEADER;
            if (h === null || v === null) {
                drift.push("temoin perdu : impossible de savoir si les offsets de `"
                    + probe.className(nullableClass) + "` sont BOXES -- lire l'ability serait"
                    + " un pari a 16 octets pres");
            } else if (h < 0 || v < 0 || h === v) {
                // `h === v` est LE symptome de la definition OUVERTE (les deux champs y sont
                // annonces a l'offset 0). Le distinguer d'un champ absent evite de faire
                // chercher un renommage la ou le probleme est l'INFLATION du generique.
                drift.push("temoin perdu : layout du Nullable non derivable (`"
                    + F_NULLABLE_HAS + "`=" + h + " `" + F_NULLABLE_VALUE + "`=" + v
                    + " sur `" + probe.className(nullableClass) + "`, taille " + nullableSize
                    + ")" + (h === v && h >= 0
                        ? " -- deux offsets EGAUX : c'est la signature de la DEFINITION"
                          + " OUVERTE `Nullable`1`, pas de l'instance inflatee"
                        : ""));
            } else if (nullableSize > 0 && (h >= utile || v + 4 > utile)) {
                drift.push("temoin perdu : layout du Nullable incoherent (has=" + h + " val="
                    + v + " hors des " + utile + " octets utiles)");
            } else {
                const enumClass = probe.fieldTypeClass(nullableClass, F_NULLABLE_VALUE);
                if (enumClass === null) {
                    drift.push("temoin perdu : le champ `" + F_NULLABLE_VALUE + "` du Nullable"
                        + " n'expose pas son type -- l'ordinal ne serait qualifie par personne,"
                        + " donc il ne sera PAS publie");
                } else {
                    const ns = probe.classNamespace(enumClass);
                    const full = (ns ? ns + "." : "") + probe.className(enumClass);
                    if (full !== TERTIARY_ENUM_FULL_NAME) {
                        drift.push("temoin perdu : ENUM MAL APPARIE -- " + CONFIG_CLS + "."
                            + F_TERTIARY + " porte des `" + full + "`, attendu `"
                            + TERTIARY_ENUM_FULL_NAME + "`. TriggeredAbilityType partage 233"
                            + " ordinaux avec ActiveAbilityType et 458 avec EffectType : la"
                            + " confusion serait SILENCIEUSE EN ORDINAL, et la meme classe"
                            + " porte litteralement le voisin `ActiveAbilities`"
                            + " (List<ActiveAbilityType>). L'ability ne sera PAS publiee.");
                    } else {
                        hasOff = h; valOff = v; abilityEnumFullName = full;
                    }
                }
            }
        }
    }
    const abilityReadable = tertiaryOffset >= 0 && hasOff >= 0 && valOff >= 0
        && abilityEnumFullName !== null;

    // --- TEMOIN : le multiplicateur de variables tertiaires -------------------------------
    // Sa perte ne peut PAS bloquer le canal : #1036-r8 demande le NIVEAU. Elle part en `drift`.
    let multiplierOffset = probe.rawFieldOffset(cfg, F_TERTIARY_MULT);
    if (multiplierOffset < 0) {
        drift.push("temoin perdu : " + CONFIG_CLS + "." + F_TERTIARY_MULT
            + " absent des metadonnees");
        multiplierOffset = -1;
    } else if (cfgSize > 0
        && (multiplierOffset < IL2CPP_OBJECT_HEADER || multiplierOffset >= cfgSize)) {
        drift.push("temoin perdu : " + CONFIG_CLS + "." + F_TERTIARY_MULT + " a l'offset "
            + multiplierOffset + ", hors [" + IL2CPP_OBJECT_HEADER + "," + cfgSize + "[");
        multiplierOffset = -1;
    } else if (multiplierOffset !== DECOMPILED_TERTIARY_MULT_OFF) {
        drift.push(CONFIG_CLS + "." + F_TERTIARY_MULT + " : offset " + multiplierOffset
            + " (0x" + multiplierOffset.toString(16) + "), lu 0x"
            + DECOMPILED_TERTIARY_MULT_OFF.toString(16) + " au decompile");
    }

    // --- DERIVES sur les offsets LUS au decompile : la lecture SUIT, la doc est ce qui
    //     devient faux.
    const cite = (label: string, got: number, want: number): void => {
        if (got !== want) {
            drift.push(label + " : offset " + got + " (0x" + got.toString(16) + "), lu 0x"
                + want.toString(16) + " au decompile -- la lecture SUIT, la doc est ce qui"
                + " devient faux");
        }
    };
    cite(CONFIG_CLS + "." + F_TERTIARY_LEVEL, levelOffset, DECOMPILED_TERTIARY_LEVEL_OFF);
    cite(CONFIG_CLS + "." + F_ID, configIdOffset, DECOMPILED_CONFIG_ID_OFF);
    cite(COMPONENT_CLS + "." + F_ID, componentIdOffset, DECOMPILED_COMPONENT_ID_OFF);

    return {
        channel: {
            unitsOffset, configIdOffset, componentIdOffset, tertiaryOffset,
            nullableHasValueOffset: hasOff, nullableValueOffset: valOff,
            levelOffset, levelValOffset, multiplierOffset,
            abilityEnumFullName, abilityReadable,
        },
        errors, drift,
    };
}
