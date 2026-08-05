/** Décodeur UNIQUE de `IdunBattle.Core.Services.DamagePredictionResult` et de son
 *  enveloppe `IdunBattle.AI.Playbook.ProbableDamageEvent` (#276), converti à la
 *  résolution de champs **PAR NOM** (#279).
 *
 *  ─────────────────────────────────────────────────────────────────────────────────
 *  POURQUOI CE MODULE EXISTE (case-268)
 *  ─────────────────────────────────────────────────────────────────────────────────
 *  Ces deux structs étaient relus À LA MAIN, avec des offsets copiés, dans SIX fichiers
 *  de hooks. À la migration `gqfc5mff6c` -> `rnca9r7q6c` ils ont TOUS dérivé en même
 *  temps, silencieusement : `aiPredict` rendait `[1,100]` pour un coup qui vaut 2375,
 *  `mightCrit` valait 25 sur un `bool`, `shieldBefore` -842041904. Ni erreur, ni crash —
 *  seulement des tests qui SKIPPENT en accusant leur propre montage.
 *
 *  #276 a centralisé le décodage ici. Restait le défaut de FOND : les offsets étaient
 *  des LITTÉRAUX, vrais pour un build et faux au suivant. C'est ce que #279 supprime.
 *
 *  ─────────────────────────────────────────────────────────────────────────────────
 *  #279 — LA RÉSOLUTION EST PAR NOM, ET ELLE ÉCHOUE FORT
 *  ─────────────────────────────────────────────────────────────────────────────────
 *  Les NOMS de champs vivent dans les métadonnées IL2CPP, en process : `class_get_fields`
 *  / `field_get_name` / `field_get_offset` les rendent au runtime, sans dump, sans
 *  fichier, sans Ghidra. Ce module ne fige donc plus AUCUN offset : il demande
 *  « où est `AccurateHealthDamage` ? » et le build répond. Une redisposition du struct
 *  n'a plus besoin d'une RE — seul un RENOMMAGE en exige une, et il se voit.
 *
 *  **Le point qui fait la différence, et il est central** : `getFieldOffset`
 *  (`il2cpp/helpers.ts`) rend **-1** quand le champ n'existe pas. Retomber sur `-1`
 *  (ou sur `0`) et lire quand même serait PIRE que l'offset figé : l'offset figé était
 *  faux mais STABLE, un `-1` lit une adresse voisine différente à chaque appel. Toute
 *  résolution manquante lève donc ici, et la lecture est refusée — cf. `POISON_OFFSET`
 *  et le `throw` en tête de `readDamagePredictionResult`.
 *
 *  ─────────────────────────────────────────────────────────────────────────────────
 *  DISPOSITION — MESURÉE en live sur `rnca9r7q6c` par le RPC `classFields`
 *  ─────────────────────────────────────────────────────────────────────────────────
 *  `classFields("IdunBattle.Core.Services", "DamagePredictionResult")` rend **18 champs**
 *  d'instance, taille boxée 176 (`0xB0`) donc `0xA0` de champs — ce que confirmaient déjà
 *  le `memset(dst, 0, 0xa0)` de `IdunBattle.Core.Services.DamagePrediction$$PredictAttackRaw`
 *  et de `unit_HUD_test$$CreateDamagePrediction`. Offsets ci-dessous en offsets de CHAMPS
 *  (le RPC les rend BOXÉS : header IL2CPP de `0x10` en plus).
 *
 *  | off  | nom du CHAMP (métadonnées)  | type                       | ce que le décodeur en fait |
 *  |------|-----------------------------|----------------------------|----------------------------|
 *  | 0x00 | `CurrentHealth`             | `Int32`                    | `hpBefore` |
 *  | 0x04 | `CurrentShield`             | `Int32`                    | `shieldBefore` |
 *  | 0x08 | `DamageProfile`             | `DamageProfile` (réf, 8 o) | non exposé — c'était le « 0x08 non identifié » de #276 |
 *  | 0x10 | `DefaultScenario`           | `DamagePredictionScenario` | conteneur des bornes RAW (`get_WillBeKill` / `get_MightBeKill`) |
 *  | 0x38 | `BlockScenarios`            | `List\`1`                  | `blockScenarioCount` / `blockKillDmg` / `blockMightDmg` / `blockProbability` (#372) |
 *  | 0x40 | `AccurateHealthDamage`      | `MinMaxDamage`             | `healthDmgMin/Max` — `IdunBattle.AI.Utilities.DamageUtility$$GetHealthDamage` = `MinMaxDamage$$Avg(pred + 0x40)` |
 *  | 0x50 | `AccurateShieldDamage`      | `MinMaxDamage`             | `shieldDmgMin/Max` — `DamageUtility$$GetShieldDamage` |
 *  | 0x60 | `TotalDamage`               | `MinMaxDamage`             | `totalDmgMin/Max` |
 *  | 0x70 | `Modifiers`                 | `List\`1`                  | non exposé — c'était le « List<?> non identifiée » de #276 |
 *  | 0x78 | `DeniedDamage`              | `Int32`                    | non exposé — retour d'`ApplyTraitDamageLimitsToDamage` |
 *  | 0x80 | `IndividualHitDamage`       | `List\`1` (`HitDamage`)    | non exposé — un élément par COUP |
 *  | 0x88 | `LimitedByMinHp`            | `Boolean`                  | `limitedByMinHp` |
 *  | 0x89 | `CannotBeGuaranteedKilled`  | `Boolean`                  | `cannotBeGuaranteedKilled` (#372) — gate de sortie anticipée de `get_WillBeKill` |
 *  | 0x8a | `MightCrit`                 | `Boolean`                  | `mightCrit` |
 *  | 0x8b | `ForceOverkill`             | `Boolean`                  | `forceOverkill` |
 *  | 0x8c | `PreventOverkill`           | `Boolean`                  | `preventOverkill` |
 *  | 0x90 | `OverkillDmgPctOfHealth`    | `Nullable\`1`              | non exposé — args 6/7 d'`IsOverkill` |
 *  | 0x98 | `AppliedHits`               | `Int32`                    | `appliedHits` |
 *
 *  **`CurrentArmor` N'EXISTE PAS.** #276 l'écrivait « aucun lecteur identifié » — une
 *  absence de PREUVE. Les 18 champs ci-dessus sont la liste EXHAUSTIVE rendue par les
 *  métadonnées : c'est désormais une preuve d'absence. `armorBefore` reste `null`.
 *  Le `0x9c` que #276 listait « dernier mot non identifié » n'est aucun champ : c'est du
 *  PADDING d'alignement entre `AppliedHits@0x98` et la fin du struct à `0xA0`.
 *
 *  Chaînes imbriquées (composées champ par champ, cf. `resolveFieldPath`) :
 *
 *  * `DamagePredictionScenario` (36 o de champs) = `{ Int32 Probability@0x00,
 *    DamagePredictionDamage Damage@0x04 }` ;
 *  * `DamagePredictionDamage` (32 o) = `{ MinMaxDamage HealthDamage@0x00,
 *    MinMaxDamage ShieldDamage@0x10 }` ;
 *  * `MinMaxDamage` (16 o) = `{ Nullable<int> _cap@0x00, Int32 Min@0x08, Int32 Max@0x0c }`
 *    — `IdunBattle.Core.Services.MinMaxDamage$$Avg` fait bien `(this[8] + this[0xc]) / 2`.
 *
 *  D'où `DefaultScenario.Damage.HealthDamage.Min` = `0x10 + 0x04 + 0x00 + 0x08` = `0x1c`,
 *  l'offset que lit `IdunBattle.Core.Services.DamagePredictionResult$$get_WillBeKill`, et
 *  `.Max` = `0x20`, celui de `get_MightBeKill`. Le décodeur ne les additionne plus à la
 *  main : il compose les quatre maillons NOMMÉS.
 *
 *  ─────────────────────────────────────────────────────────────────────────────────
 *  #372 — LES DEUX ENTRÉES DE `get_WillBeKill` QUI MANQUAIENT
 *  ─────────────────────────────────────────────────────────────────────────────────
 *  `IdunBattle.Core.Services.DamagePredictionResult$$get_WillBeKill`, VERBATIM :
 *
 *      if (CannotBeGuaranteedKilled@0x89) return false;
 *      m = (BlockScenarios@0x38 == null || BlockScenarios.Count < 1)
 *          ? DefaultScenario.Damage.HealthDamage.Min@0x1c
 *          : BlockScenarios[0] + 0x0c;              // .Damage.HealthDamage.Min
 *      return CurrentHealth@0x00 <= m;
 *
 *  Le canal n'exposait que la branche `else` (`willKillDmg`). Tout verdict sur une gate
 *  `WillBeKill` se prenait donc en AVEUGLE sur les deux autres entrées — c'est ce qui a
 *  bloqué `#353-r1` (volet b) et laissé `#344-r2` sans preuve. Ce module lit désormais
 *  les trois, et publie `willBeKill` DÉJÀ CALCULÉ : aucun consommateur ne doit
 *  ré-assembler la règle, sinon la divergence se rejoue à chaque site.
 *
 *  `BlockScenarios[0]` est un `DamagePredictionScenario`, MÊME type que `DefaultScenario`
 *  — c'est `DamagePredictionResult$$GetBlockScenarioOrDefault` qui le prouve (son fallback
 *  recopie les 36 octets de `DefaultScenario@0x10`), et
 *  `DamagePredictionResult$$get_HealthDamageWithBlock` le recoupe (mêmes deux branches,
 *  bornes `+0x0c`/`+0x10` du scénario). Le décodeur ne recopie donc AUCUN offset : il
 *  résout `Probability` / `Damage.HealthDamage.Min` / `.Max` PAR NOM sur la classe du
 *  champ `DefaultScenario` (`fieldTypeClass`), et la taille de l'élément par
 *  `resolveFieldsSize` — ni la classe du scénario ni son stride ne sont écrits ici.
 *
 *  **Deux constantes de FORME restent, et elles ne sont pas dérivables par nom** :
 *  `List<T>` porte `_items`/`_size` — ceux-là SONT des noms, donc résolus — mais un
 *  `Il2CppArray` place ses données à `+0x20` (header objet `0x10` + `bounds` + `max_length`).
 *  `ARRAY_FIRST` est de la même nature que `IL2CPP_BOX_HEADER` : une connaissance de forme,
 *  extérieure aux métadonnées. Elle est isolée et nommée pour cette raison.
 *
 *  **Où le flag peut VALOIR 1 — mesuré aux xrefs, pas supposé.**
 *  `CannotBeGuaranteedKilled@0x89` n'a qu'**UN SEUL écrivain** dans tout le binaire :
 *  `IdunBattle.Core.Services.DamagePrediction$$PredictNormalAttack`, dernière instruction
 *  avant son `return` (`*(char*)(this+0x89) = DamagePrediction$$CannotBeGuaranteedKilled(...)`),
 *  et `DamagePrediction$$CannotBeGuaranteedKilled` n'a lui-même que CE seul appelant.
 *  Conséquences, toutes lues :
 *  * `BattleQuery$$GetNormalAttackPrediction` invoque `IDamagePrediction` **slot 9** =
 *    `PredictNormalAttack` -> le flag est VIVANT ;
 *  * `BattleQuery$$GetAttackPrediction` invoque le **slot 0xb** (`PredictAttack`) et
 *    `BattleQuery$$GetMultiHitAttackPrediction` commence par `memset(result, 0, 0xa0)` puis
 *    délègue à `GetAttackPrediction` -> le flag y reste **structurellement 0** ;
 *  * `DamagePredictionResult$$Add` ne fusionne AUCUN des flags `@0x88..0x8c` (il ne somme
 *    que les bornes, `AppliedHits@0x98`, la liste `IndividualHitDamage@0x80` et fusionne
 *    `BlockScenarios@0x38` par index) -> le cumul multi-coups ne peut pas le rallumer.
 *  Donc : un `cannotBeGuaranteedKilled = 1` observé sur un event de playbook
 *  (`ComparablePlaybook<T>$$GenerateMultiHitAttackPredictions` -> slot 0x28 =
 *  `GetMultiHitAttackPrediction`) accuserait le DÉCODEUR, pas la bataille.
 *
 *  `ProbableDamageEvent` (184 = `0xB8` de champs, boxé 200) = `{ IEntity Target@0x00,
 *  DamagePredictionResult DamagePrediction@0x08, Fix64 Probability@0xA8, Fix64 Weight@0xB0 }`.
 *  `ProbableHealEvent` / `ProbableEffectEvent` = `0x18` de champs chacun :
 *  `{ IEntity Target@0x00, <charge utile>@0x08, Fix64 Probability@0x10 }`. La charge utile
 *  du heal est un `HealPredictionResult` **INLINE** — un ValueType de 8 octets
 *  (`Int32 CurrentHealth@0x00`, `Int32 TotalHeal@0x04`), PAS un pointeur : `Probability`
 *  étant à `0x10`, il ne reste que 8 octets pour lui, et `classFields` donne bien
 *  `boxedSize` 24 / `fieldsSize` 8 pour ce type.
 *
 *  ─────────────────────────────────────────────────────────────────────────────────
 *  OÙ CETTE VOIE S'ARRÊTE — mesuré, pas supposé (#279)
 *  ─────────────────────────────────────────────────────────────────────────────────
 *  1. **`class_get_fields` NE DESCEND PAS dans un ValueType imbriqué.** Mesuré :
 *     `DamagePredictionResult` rend 18 champs et `DefaultScenario` y figure comme UN
 *     champ de type `DamagePredictionScenario` ; ni `Probability` ni `Damage` n'y
 *     apparaissent. Il faut interroger `DamagePredictionScenario` séparément, puis
 *     `DamagePredictionDamage`, puis `MinMaxDamage`. Ce n'est PAS un mur : la classe du
 *     sous-type se déduit du champ lui-même (`field_get_type` ->
 *     `type_get_class_or_element_class`), donc la chaîne se compose sans jamais nommer
 *     une classe intermédiaire. C'est ce que fait `resolveFieldPath`. Le coût est un
 *     aller-retour de métadonnées par maillon, payé UNE fois au chargement.
 *  2. **Le header `0x10` n'est pas dans les noms.** `il2cpp_field_get_offset` rend un
 *     offset BOXÉ pour un ValueType ; savoir qu'il faut le retrancher est une
 *     connaissance de FORME, extérieure aux noms de champs. D'où l'appel à
 *     `class_is_valuetype` et le refus de composer un maillon qui n'en est pas un.
 *  3. **Ce qui n'a pas de nom reste indécodable par nom** : le padding `0x9c`, et le `T`
 *     d'un `List<T>` (le champ rend `List\`1`, pas l'élément). Le STRIDE d'un
 *     `List<ProbableDamageEvent>` se prend donc sur la classe de l'ÉLÉMENT
 *     (`PDE_STRIDE`), jamais sur le champ qui la contient.
 *  4. **Un RENOMMAGE inter-build reste une RE.** La conversion ne supprime pas ce coût,
 *     elle le rend BRUYANT : au lieu de rendre `[1,100]`, le canal dit quel chemin nommé
 *     n'existe plus.
 */

import {
    class_get_name, class_instance_size, class_is_valuetype,
    field_get_offset, field_get_type, findClassAnywhere, getFieldInfo, s,
    type_get_class_or_element_class,
} from "../il2cpp/helpers.js";

// ─── Résolution PAR NOM ───────────────────────────────────────────────────────────

/** Header IL2CPP porté par tout `System.ValueType` boxé. `il2cpp_field_get_offset` le
 *  compte dans l'offset qu'il rend ; les décodeurs, eux, travaillent en offsets de
 *  CHAMPS (base = premier octet utile). Confondre les deux est exactement ce qui avait
 *  mis `DamagePredictionResult` à `0xB0` au lieu de `0xA0` (#276). */
const IL2CPP_BOX_HEADER = 0x10;

/** Décalage des DONNÉES d'un `Il2CppArray` depuis le pointeur du tableau : header objet
 *  (`klass` + `monitor` = `0x10`) + `bounds` (`0x8`) + `max_length` (`0x8`). Même nature
 *  que `IL2CPP_BOX_HEADER` : une connaissance de FORME du runtime, PAS un nom de champ —
 *  aucune métadonnée ne la rend, donc elle est figée ici, isolée et nommée. (Le reste du
 *  codebase la porte déjà sous `ARRAY_FIRST` / `LIST_ITEMS_BASE`, cf.
 *  `features/ai-step/internals.ts` et `ai-toolkit/unit-action.ts`.) */
const ARRAY_FIRST = 0x20;

/** `System.Collections.Generic.List<T>` : `_items` (le tableau) puis `_size` (le Count).
 *
 *  **Pourquoi ces deux-là ÉCHAPPENT à la résolution par nom, et c'est MESURÉ, pas supposé.**
 *  `findClassAnywhere("System.Collections.Generic", "List\`1")` rend la DÉFINITION
 *  générique, jamais une instanciation. Le RPC `classFields` sur elle (build `rnca9r7q6c`,
 *  2026-07-31) rend `boxedSize: 0`, `fieldsSize: -16`, `instanceFieldCount: 0` et les
 *  **cinq** champs à `offset: 0` — une classe jamais initialisée n'a pas de disposition
 *  (même piège que `reference_il2cpp_methodptr_uninit_class`). Composer sur ces zéros
 *  lirait le pointeur de classe au lieu du tableau.
 *
 *  Ce sont donc des constantes de FORME, exactement comme `IL2CPP_BOX_HEADER` et
 *  `ARRAY_FIRST`, et le reste du codebase les porte déjà ainsi en production
 *  (`features/ai-step/internals.ts` `LIST_ITEMS`/`LIST_SIZE`, `ai-toolkit/unit-action.ts`).
 *  `checkListShape` ci-dessous les CONFRONTE quand même aux métadonnées, au cas où une
 *  instanciation concrète serait résolvable : une divergence part en `drift`, pas en
 *  erreur — le décodeur suit la forme, la doc est ce qui devient faux. */
const LIST_ITEMS = 0x10;
const LIST_SIZE = 0x18;

/** Sentinelle d'offset NON RÉSOLU. Volontairement énorme : si un appelant l'utilisait
 *  malgré tout, `base.add(POISON_OFFSET).readS32()` LÈVERAIT (accès mémoire invalide)
 *  au lieu de rendre une valeur plausible lue dans le tas voisin. `0` et `-1` sont
 *  proscrits pour cette raison : ce sont des offsets LISIBLES. */
const POISON_OFFSET = 0x40000000;

/** Façade des métadonnées IL2CPP dont dépend la résolution. Elle existe pour une seule
 *  raison : rendre la résolution EXÉCUTABLE hors du process de jeu, sur une disposition
 *  capturée par le RPC `classFields`. Sans elle, la seule façon de voir la garde rougir
 *  serait de réinjecter. `LIVE_PROBE` en est l'implémentation de production. */
export interface LayoutProbe {
    findClass(ns: string, cls: string): NativePointer | null;
    className(klass: NativePointer): string;
    /** true / false / null = « l'export manque, je ne sais pas » (on refuse de deviner). */
    isValueType(klass: NativePointer): boolean | null;
    /** `il2cpp_class_instance_size` — taille BOXÉE, ou -1 si indisponible. */
    instanceSize(klass: NativePointer): number;
    /** Offset BRUT de `il2cpp_field_get_offset` (donc BOXÉ pour un ValueType) ;
     *  **-1 si le champ n'existe pas**. */
    rawFieldOffset(klass: NativePointer, name: string): number;
    /** Classe du TYPE du champ, ou null si le champ ou son type ne se résout pas. */
    fieldTypeClass(klass: NativePointer, name: string): NativePointer | null;
}

export const LIVE_PROBE: LayoutProbe = {
    findClass: (ns, cls) => {
        const k = findClassAnywhere(ns, cls);
        return k === null || k.isNull() ? null : k;
    },
    className: (klass) => s(class_get_name(klass) as NativePointer),
    isValueType: (klass) => (class_is_valuetype === null
        ? null : (class_is_valuetype(klass) as number) !== 0),
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
};

/** Compose un CHEMIN de champs nommés en un offset de CHAMPS, en descendant dans les
 *  ValueTypes imbriqués. LÈVE au premier maillon qui ne se résout pas — jamais de
 *  retour dégradé.
 *
 *  Chaque maillon est vérifié sur trois points, et chacun a déjà coûté :
 *  * le champ EXISTE (sinon `-1`, qui lirait une adresse voisine) ;
 *  * son conteneur est un ValueType (sinon le `-0x10` serait faux, et un champ de type
 *    référence devrait être DÉRÉFÉRENCÉ, pas additionné) ;
 *  * l'offset tombe dans la plage d'instance `[0x10, instanceSize[` — un champ STATIQUE
 *    porte un offset hors de cette plage et ne doit jamais être composé. */
export function resolveFieldPath(
    probe: LayoutProbe, klass: NativePointer, label: string,
    path: readonly string[],
): number {
    let k = klass;
    let acc = 0;
    for (let i = 0; i < path.length; i++) {
        const where = label + "." + path.slice(0, i + 1).join(".");
        const isVt = probe.isValueType(k);
        if (isVt === null) {
            throw new Error("RESOLUTION PAR NOM IMPOSSIBLE (#279) : " + where
                + " -- il2cpp_class_is_valuetype non exporte, le decalage de header"
                + " (0x10) n'est pas derivable");
        }
        if (!isVt) {
            throw new Error("RESOLUTION PAR NOM IMPOSSIBLE (#279) : " + where
                + " -- le conteneur " + probe.className(k) + " n'est PAS un ValueType,"
                + " ses champs ne sont pas INLINE (il faudrait dereferencer)");
        }
        const raw = probe.rawFieldOffset(k, path[i]);
        if (raw < 0) {
            throw new Error("CHAMP INTROUVABLE (#279) : " + where
                + " -- absent des metadonnees IL2CPP de ce build. Le decodeur REFUSE"
                + " de lire plutot que de retomber sur un offset de repli.");
        }
        const size = probe.instanceSize(k);
        if (size > 0 && (raw < IL2CPP_BOX_HEADER || raw >= size)) {
            throw new Error("OFFSET HORS INSTANCE (#279) : " + where + " -- offset boxe "
                + raw + " hors [" + IL2CPP_BOX_HEADER + "," + size + "[ ; champ STATIQUE"
                + " ou litteral, pas un champ d'instance");
        }
        acc += raw - IL2CPP_BOX_HEADER;
        if (i + 1 < path.length) {
            const next = probe.fieldTypeClass(k, path[i]);
            if (next === null) {
                throw new Error("TYPE DE CHAMP NON RESOLU (#279) : " + where
                    + " -- impossible de descendre dans le sous-struct");
            }
            k = next;
        }
    }
    return acc;
}

/** Offset d'un champ d'un type RÉFÉRENCE (donc BRUT, header objet COMPRIS — un objet ne
 *  se « déboxe » pas). Pendant strict de `resolveFieldPath` pour les cas où le conteneur
 *  n'est PAS un ValueType : `List<T>._items` / `._size`. Mêmes refus (champ absent,
 *  offset hors plage d'instance), même politique — LÈVE plutôt que rendre un repli.
 *
 *  ⚠ Ne JAMAIS router un ValueType par ici : le `-0x10` manquerait et l'offset serait
 *  faux de 16 octets, silencieusement. La garde `isValueType === true` refuse. */
export function resolveRefFieldOffset(
    probe: LayoutProbe, klass: NativePointer, label: string, name: string,
): number {
    const where = label + "." + name;
    const isVt = probe.isValueType(klass);
    if (isVt === null) {
        throw new Error("RESOLUTION PAR NOM IMPOSSIBLE (#372) : " + where
            + " -- il2cpp_class_is_valuetype non exporte, impossible de verifier que le"
            + " conteneur est bien un type REFERENCE");
    }
    if (isVt) {
        throw new Error("RESOLUTION PAR NOM IMPOSSIBLE (#372) : " + where + " -- "
            + probe.className(klass) + " est un ValueType ; utiliser resolveFieldPath"
            + " (qui retranche le header de boxing), pas resolveRefFieldOffset");
    }
    const raw = probe.rawFieldOffset(klass, name);
    if (raw < 0) {
        throw new Error("CHAMP INTROUVABLE (#372) : " + where
            + " -- absent des metadonnees IL2CPP de ce build.");
    }
    const size = probe.instanceSize(klass);
    if (size > 0 && (raw < IL2CPP_BOX_HEADER || raw >= size)) {
        throw new Error("OFFSET HORS INSTANCE (#372) : " + where + " -- offset " + raw
            + " hors [" + IL2CPP_BOX_HEADER + "," + size + "[ ; champ STATIQUE, pas un"
            + " champ d'instance");
    }
    return raw;
}

/** Taille des CHAMPS d'un ValueType = taille boxée - header. LÈVE si la classe n'est pas
 *  un ValueType ou si `il2cpp_class_instance_size` manque : c'est un STRIDE d'itération
 *  de `List<T>`, et un stride faux de 16 octets rend du garbage sur tout élément après
 *  le premier (#276). */
export function resolveFieldsSize(
    probe: LayoutProbe, klass: NativePointer, label: string,
): number {
    const isVt = probe.isValueType(klass);
    if (isVt !== true) {
        throw new Error("TAILLE DE CHAMPS INDETERMINEE (#279) : " + label
            + " -- " + (isVt === null ? "il2cpp_class_is_valuetype non exporte"
                : "n'est pas un ValueType"));
    }
    const size = probe.instanceSize(klass);
    if (size <= IL2CPP_BOX_HEADER) {
        throw new Error("TAILLE DE CHAMPS INDETERMINEE (#279) : " + label
            + " -- il2cpp_class_instance_size rend " + size);
    }
    return size - IL2CPP_BOX_HEADER;
}

// ─── Chemins NOMMÉS (la seule chose que ce module fige désormais) ─────────────────

const NS_SERVICES = "IdunBattle.Core.Services";
const NS_PLAYBOOK = "IdunBattle.AI.Playbook";

/** Chemins de `DamagePredictionResult` -> champs exposés par `DamagePredictionFields`.
 *  Un chemin à plusieurs maillons descend dans des ValueTypes imbriqués. */
const DPR_PATHS = {
    currentHealth: ["CurrentHealth"],
    currentShield: ["CurrentShield"],
    /** `DefaultScenario.Probability`, en pourcents entiers. Le CHAMP s'appelle
     *  `DefaultScenario` ; c'est l'ACCESSEUR qui s'appelle
     *  `DamagePredictionResult$$get_DefaultBlockScenario`. */
    scenarioProbability: ["DefaultScenario", "Probability"],
    /** Bornes RAW que lisent `get_WillBeKill` (Min) et `get_MightBeKill` (Max). */
    scenarioHealthDamage: ["DefaultScenario", "Damage", "HealthDamage"],
    scenarioShieldDamage: ["DefaultScenario", "Damage", "ShieldDamage"],
    blockScenarios: ["BlockScenarios"],
    /** `MinMaxDamage$$Avg` sur ce champ = `DamageUtility$$GetHealthDamage`. */
    healthDamage: ["AccurateHealthDamage"],
    /** `MinMaxDamage$$Avg` sur ce champ = `DamageUtility$$GetShieldDamage`. */
    shieldDamage: ["AccurateShieldDamage"],
    totalDamage: ["TotalDamage"],
    hitDamages: ["IndividualHitDamage"],
    limitedByMinHp: ["LimitedByMinHp"],
    /** #372 — gate de sortie anticipée de `get_WillBeKill`. Unique écrivain natif :
     *  `DamagePrediction$$PredictNormalAttack` (cf. l'en-tête de ce fichier). */
    cannotBeGuaranteedKilled: ["CannotBeGuaranteedKilled"],
    mightCrit: ["MightCrit"],
    forceOverkill: ["ForceOverkill"],
    preventOverkill: ["PreventOverkill"],
    appliedHits: ["AppliedHits"],
} as const;

type DprKey = keyof typeof DPR_PATHS;

const PDE_PATHS = {
    prediction: ["DamagePrediction"],
    probability: ["Probability"],
    weight: ["Weight"],
} as const;

/** Disposition RE de `rnca9r7q6c`, conservée UNIQUEMENT comme témoin de dérive.
 *
 *  Ce n'est plus ce que le décodeur utilise — il lit les métadonnées. Un écart entre
 *  cette table et la résolution live ne signifie donc PAS « canal mort » : il signifie
 *  « le struct a été redisposé, le décodeur suit, la documentation de ce fichier est à
 *  refaire ». C'est l'inversion apportée par #279 : la dérive devient une information,
 *  elle n'est plus une panne. Cf. `predictionLayoutDrift`. */
const RE_OFFSETS_RNCA9R7Q6C: Record<string, number> = {
    "DamagePredictionResult.currentHealth": 0x00,
    "DamagePredictionResult.currentShield": 0x04,
    "DamagePredictionResult.scenarioProbability": 0x10,
    "DamagePredictionResult.scenarioHealthDamage": 0x14,
    "DamagePredictionResult.scenarioShieldDamage": 0x24,
    "DamagePredictionResult.blockScenarios": 0x38,
    "DamagePredictionResult.healthDamage": 0x40,
    "DamagePredictionResult.shieldDamage": 0x50,
    "DamagePredictionResult.totalDamage": 0x60,
    "DamagePredictionResult.hitDamages": 0x80,
    "DamagePredictionResult.limitedByMinHp": 0x88,
    "DamagePredictionResult.cannotBeGuaranteedKilled": 0x89,
    "DamagePredictionScenario.probability": 0x00,
    "DamagePredictionScenario.healthDamageMin": 0x0c,
    "DamagePredictionScenario.healthDamageMax": 0x10,
    "DamagePredictionScenario.fieldsSize": 0x24,
    "DamagePredictionResult.mightCrit": 0x8a,
    "DamagePredictionResult.forceOverkill": 0x8b,
    "DamagePredictionResult.preventOverkill": 0x8c,
    "DamagePredictionResult.appliedHits": 0x98,
    "MinMaxDamage.Min": 0x08,
    "MinMaxDamage.Max": 0x0c,
    "DamagePredictionResult.fieldsSize": 0xa0,
    "ProbableDamageEvent.prediction": 0x08,
    "ProbableDamageEvent.probability": 0xa8,
    "ProbableDamageEvent.weight": 0xb0,
    "ProbableDamageEvent.fieldsSize": 0xb8,
    "ProbableHealEvent.fieldsSize": 0x18,
    "ProbableEffectEvent.fieldsSize": 0x18,
};

// ─── Résolution effective (une fois, au chargement du module) ─────────────────────

/** #372 — offsets INTERNES à un `DamagePredictionScenario` (l'élément de `BlockScenarios`,
 *  MÊME type que `DefaultScenario`). Résolus sur la classe du champ `DefaultScenario`, donc
 *  sans jamais nommer `DamagePredictionScenario` ici. */
export interface ScenarioLayout {
    probability: number;
    healthDamageMin: number;
    healthDamageMax: number;
    /** Stride d'un élément dans le tableau interne de `List<DamagePredictionScenario>`. */
    stride: number;
}

export interface PredictionLayout {
    dpr: Record<DprKey, number>;
    minMaxMin: number;
    minMaxMax: number;
    /** null = la chaîne `BlockScenarios[0]` ne s'est pas résolue ; la lecture rend alors
     *  `null` (tri-état) au lieu d'un zéro qui se lirait « pas de scénario de blocage ». */
    scenario: ScenarioLayout | null;
    dprFieldsSize: number;
    pdePrediction: number;
    pdeProbability: number;
    pdeWeight: number;
    pdeStride: number;
    smallEventStride: number;
    // RETIRE (#480-r7) : `dprBoxedSize` / `pdeBoxedSize` / `smallEventBoxedSize`. Ces trois
    // champs etaient `<taille de champs> + IL2CPP_BOX_HEADER`, et leurs SEULS lecteurs
    // etaient les trois exports `*_BOXED_SIZE` ci-dessous, eux-memes sans aucun appelant.
    // Un consommateur qui aurait besoin de la taille BOXEE l'obtient en ajoutant le header
    // `0x10` au stride ; `IL2CPP_BOX_HEADER` est PRIVE a ce module, l'exporter est le geste
    // a faire quand un appelant existera -- pas avant.
}

export interface LayoutResolution {
    layout: PredictionLayout | null;
    /** Une entrée par échec, message ASCII prêt à remonter dans un payload. */
    errors: string[];
    /** `chemin: live=<x> re=<y>` pour chaque offset qui s'écarte de la table RE. */
    drift: string[];
}

/** Résout TOUTE la disposition par nom. Ne lève jamais : c'est appelé au chargement du
 *  module, et un throw y empêcherait le bundle entier de se charger. Les échecs sont
 *  CAPTURÉS et rendus — c'est la LECTURE qui refusera ensuite (cf.
 *  `readDamagePredictionResult`). */
export function resolvePredictionLayout(probe: LayoutProbe): LayoutResolution {
    const errors: string[] = [];
    const drift: string[] = [];
    const noteDrift = (key: string, live: number): void => {
        const re = RE_OFFSETS_RNCA9R7Q6C[key];
        if (re !== undefined && re !== live) {
            drift.push(key + ": live=" + live + " re(rnca9r7q6c)=" + re);
        }
    };
    const cls = (ns: string, name: string): NativePointer | null => {
        let k: NativePointer | null = null;
        try { k = probe.findClass(ns, name); } catch { k = null; }
        if (k === null) {
            errors.push("CLASSE INTROUVABLE (#279) : " + ns + "." + name);
        }
        return k;
    };

    const dprK = cls(NS_SERVICES, "DamagePredictionResult");
    const mmK = cls(NS_SERVICES, "MinMaxDamage");
    const pdeK = cls(NS_PLAYBOOK, "ProbableDamageEvent");
    const pheK = cls(NS_PLAYBOOK, "ProbableHealEvent");
    const peeK = cls(NS_PLAYBOOK, "ProbableEffectEvent");
    if (dprK === null || mmK === null || pdeK === null
        || pheK === null || peeK === null) {
        return { layout: null, errors, drift };
    }

    const take = (fn: () => number, onOk: (v: number) => void): void => {
        try { onOk(fn()); }
        catch (e) { errors.push((e as Error).message); }
    };

    const dpr = {} as Record<DprKey, number>;
    for (const key of Object.keys(DPR_PATHS) as DprKey[]) {
        take(() => resolveFieldPath(probe, dprK, "DamagePredictionResult",
            DPR_PATHS[key]), (v) => {
            dpr[key] = v;
            noteDrift("DamagePredictionResult." + key, v);
        });
    }

    // #372 — la chaîne `BlockScenarios[0].Damage.HealthDamage.Min` : trois maillons, tous
    // NOMMÉS. La classe de l'élément se prend sur le CHAMP `DefaultScenario` (même type,
    // établi par `DamagePredictionResult$$GetBlockScenarioOrDefault`), et celle de la liste
    // sur le champ `BlockScenarios` — aucune des deux n'est écrite ici.
    let scenario: ScenarioLayout | null = null;
    {
        const scnK = ((): NativePointer | null => {
            try { return probe.fieldTypeClass(dprK, "DefaultScenario"); } catch { return null; }
        })();
        if (scnK === null) {
            errors.push("TYPE DE CHAMP NON RESOLU (#372) :"
                + " DamagePredictionResult.DefaultScenario -- impossible de composer"
                + " BlockScenarios[0], qui est du MEME type");
        } else {
            const parts: Partial<ScenarioLayout> = {};
            take(() => resolveFieldPath(probe, scnK, "DamagePredictionScenario",
                ["Probability"]), (v) => {
                parts.probability = v; noteDrift("DamagePredictionScenario.probability", v);
            });
            take(() => resolveFieldPath(probe, scnK, "DamagePredictionScenario",
                ["Damage", "HealthDamage", "Min"]), (v) => {
                parts.healthDamageMin = v;
                noteDrift("DamagePredictionScenario.healthDamageMin", v);
            });
            take(() => resolveFieldPath(probe, scnK, "DamagePredictionScenario",
                ["Damage", "HealthDamage", "Max"]), (v) => {
                parts.healthDamageMax = v;
                noteDrift("DamagePredictionScenario.healthDamageMax", v);
            });
            take(() => resolveFieldsSize(probe, scnK, "DamagePredictionScenario"), (v) => {
                parts.stride = v; noteDrift("DamagePredictionScenario.fieldsSize", v);
            });
            if (parts.probability !== undefined && parts.healthDamageMin !== undefined
                && parts.healthDamageMax !== undefined && parts.stride !== undefined) {
                scenario = parts as ScenarioLayout;
            }
        }
        // Contrôle OPPORTUNISTE de la forme de `List<T>` : si — et seulement si — une
        // instanciation résolvable existe, on confronte `_items`/`_size` aux constantes de
        // forme. Un échec est ATTENDU (définition générique non initialisée, mesuré) et ne
        // dit rien ; une divergence, elle, part en `drift`.
        for (const [name, want] of [["_items", LIST_ITEMS], ["_size", LIST_SIZE]] as const) {
            try {
                const lstK = probe.fieldTypeClass(dprK, "BlockScenarios");
                if (lstK === null) break;
                const got = resolveRefFieldOffset(probe, lstK, "List", name);
                if (got !== want) drift.push("List." + name + ": live=" + got + " forme=" + want);
            } catch { /* non résolvable : la forme fait foi, cf. LIST_ITEMS */ }
        }
    }

    let minMaxMin = -1; let minMaxMax = -1;
    take(() => resolveFieldPath(probe, mmK, "MinMaxDamage", ["Min"]), (v) => {
        minMaxMin = v; noteDrift("MinMaxDamage.Min", v);
    });
    take(() => resolveFieldPath(probe, mmK, "MinMaxDamage", ["Max"]), (v) => {
        minMaxMax = v; noteDrift("MinMaxDamage.Max", v);
    });

    let dprFieldsSize = -1;
    take(() => resolveFieldsSize(probe, dprK, "DamagePredictionResult"), (v) => {
        dprFieldsSize = v; noteDrift("DamagePredictionResult.fieldsSize", v);
    });

    let pdePrediction = -1; let pdeProbability = -1; let pdeWeight = -1;
    take(() => resolveFieldPath(probe, pdeK, "ProbableDamageEvent",
        PDE_PATHS.prediction), (v) => {
        pdePrediction = v; noteDrift("ProbableDamageEvent.prediction", v);
    });
    take(() => resolveFieldPath(probe, pdeK, "ProbableDamageEvent",
        PDE_PATHS.probability), (v) => {
        pdeProbability = v; noteDrift("ProbableDamageEvent.probability", v);
    });
    take(() => resolveFieldPath(probe, pdeK, "ProbableDamageEvent",
        PDE_PATHS.weight), (v) => {
        pdeWeight = v; noteDrift("ProbableDamageEvent.weight", v);
    });

    let pdeStride = -1;
    take(() => resolveFieldsSize(probe, pdeK, "ProbableDamageEvent"), (v) => {
        pdeStride = v; noteDrift("ProbableDamageEvent.fieldsSize", v);
    });

    // `SMALL_EVENT_STRIDE` est partagé par les DEUX petits events. Ce partage est une
    // HYPOTHÈSE de l'ancien code : on la VÉRIFIE au lieu de la reconduire.
    let healStride = -1; let effectStride = -1;
    take(() => resolveFieldsSize(probe, pheK, "ProbableHealEvent"), (v) => {
        healStride = v; noteDrift("ProbableHealEvent.fieldsSize", v);
    });
    take(() => resolveFieldsSize(probe, peeK, "ProbableEffectEvent"), (v) => {
        effectStride = v; noteDrift("ProbableEffectEvent.fieldsSize", v);
    });
    if (healStride > 0 && effectStride > 0 && healStride !== effectStride) {
        errors.push("STRIDE PARTAGE INVALIDE (#279) : ProbableHealEvent=" + healStride
            + " != ProbableEffectEvent=" + effectStride
            + " -- SMALL_EVENT_STRIDE ne peut plus etre unique");
    }

    if (errors.length > 0) return { layout: null, errors, drift };

    return {
        layout: {
            dpr, minMaxMin, minMaxMax, scenario,
            dprFieldsSize,
            pdePrediction, pdeProbability, pdeWeight,
            pdeStride,
            smallEventStride: healStride,
        },
        errors, drift,
    };
}

/** Résolution de PRODUCTION, faite une fois au chargement. Le `try` extérieur est une
 *  ceinture : `resolvePredictionLayout` capture déjà tout, mais un module de hooks qui
 *  lève au chargement empêche le script ENTIER de s'installer. */
const RESOLUTION: LayoutResolution = (() => {
    try { return resolvePredictionLayout(LIVE_PROBE); }
    catch (e) {
        return {
            layout: null,
            errors: ["RESOLUTION DE LAYOUT EN ECHEC (#279) : " + (e as Error).message],
            drift: [],
        };
    }
})();

const L = RESOLUTION.layout;

// ─── Offsets exposés (résolus PAR NOM, empoisonnés si la résolution a échoué) ──────

// RETIRE (#480-r7) : `DPR_BOXED_SIZE`, `PDE_BOXED_SIZE`, `SMALL_EVENT_BOXED_SIZE` --
// derives triviaux (stride + header `0x10`) sans aucun lecteur, dans aucune des
// trois langues du depot. Et `DPR_SIZE` avec eux : le recensement le classait
// « sur-exporte, utilise chez lui », mais sa seule autre occurrence etait le COMMENTAIRE
// de `DPR_BOXED_SIZE` ci-dessus -- il etait mort lui aussi. La taille des champs de
// `DamagePredictionResult` reste disponible dans le layout (`dprFieldsSize`), lu par le
// harnais `tools/probe-279-layout-by-name.ts`.

/** Champs de `ProbableDamageEvent` = son STRIDE dans un `List<T>` / un tableau. */
export const PDE_STRIDE = L ? L.pdeStride : POISON_OFFSET;
/** `Probable{Heal,Effect}Event` : 3 slots de 8 o (égalité VÉRIFIÉE, pas supposée). */
export const SMALL_EVENT_STRIDE = L ? L.smallEventStride : POISON_OFFSET;

/** Décalage du `DamagePredictionResult` embarqué dans un `ProbableDamageEvent`
 *  (champ `DamagePrediction`, ValueType INLINE). */
export const PDE_PREDICTION_OFF = L ? L.pdePrediction : POISON_OFFSET;
/** `Fix64 Probability` puis `Fix64 Weight`. Les deux arrivent en `Nullable<Fix64>` à
 *  `IdunBattle.AI.Playbook.ProbableDamageEvent$$.ctor`, qui substitue `Fix64(1)` quand
 *  `HasValue` est faux — donc une probabilité NULLE ne peut pas venir du natif, c'est
 *  une sentinelle de décodage. */
export const PDE_PROBABILITY_OFF = L ? L.pdeProbability : POISON_OFFSET;
export const PDE_WEIGHT_OFF = L ? L.pdeWeight : POISON_OFFSET;

const POISONED_DPR = ((): Record<DprKey, number> => {
    const out = {} as Record<DprKey, number>;
    for (const k of Object.keys(DPR_PATHS) as DprKey[]) out[k] = POISON_OFFSET;
    return out;
})();

/** Offsets `DamagePredictionResult` (champs nus, base = début du struct). */
export const DPR: Readonly<Record<DprKey, number>> = L ? L.dpr : POISONED_DPR;

/** `MinMaxDamage` : `Min` et `Max`, résolus par nom sur la classe elle-même. */
export const MINMAX_MIN = L ? L.minMaxMin : POISON_OFFSET;
export const MINMAX_MAX = L ? L.minMaxMax : POISON_OFFSET;

// ─── Garde de layout ──────────────────────────────────────────────────────────────

export interface LayoutStatus {
    /** true = tous les chemins NOMMÉS se sont résolus ; la lecture est autorisée. */
    ok: boolean;
    /** Détail des échecs de résolution, vide si `ok`. */
    mismatches: string[];
    /** Classes que `findClassAnywhere` n'a pas résolues (garde non concluante). */
    unresolved: string[];
    /** true si une primitive de métadonnées manque (garde inopérante). */
    unavailable: boolean;
    /** Offsets qui s'écartent de la table RE `rnca9r7q6c`. N'INVALIDE PAS la lecture :
     *  le décodeur suit le build, c'est la DOC de ce fichier qui est à refaire. */
    drift: string[];
}

let layoutStatus: LayoutStatus | null = null;

/** État de la résolution PAR NOM, calculé une fois puis en cache.
 *
 *  Avant #279 cette garde confrontait la taille de classe LIVE à une taille RE figée :
 *  elle disait « le build a changé, ce décodeur est périmé ». Elle dit maintenant
 *  quelque chose de plus fort et de plus étroit : « tel chemin NOMMÉ n'existe plus ».
 *  Un simple déplacement de champ ne la déclenche plus — il n'a plus à la déclencher,
 *  puisque le décodeur le suit.
 *
 *  Ne LÈVE jamais (on est dans des hooks) : le statut se propage aux payloads. */
export function predictionLayoutStatus(): LayoutStatus {
    if (layoutStatus !== null) return layoutStatus;
    const unresolved = RESOLUTION.errors
        .filter((e) => e.indexOf("CLASSE INTROUVABLE") === 0);
    const unavailable = RESOLUTION.errors.some(
        (e) => e.indexOf("non exporte") >= 0);
    layoutStatus = {
        ok: RESOLUTION.layout !== null,
        mismatches: RESOLUTION.errors.filter((e) => unresolved.indexOf(e) < 0),
        unresolved,
        unavailable,
        drift: RESOLUTION.drift,
    };
    return layoutStatus;
}

/** Message ASCII prêt à remonter dans un payload d'erreur (les sondes Python
 *  l'impriment sur une console cp1252). Vide si la garde passe.
 *
 *  ⚠ La DÉRIVE vis-à-vis de la table RE n'apparaît PAS ici, et c'est délibéré : elle
 *  ne disqualifie aucune mesure. Cf. `predictionLayoutDrift`. */
export function predictionLayoutError(): string | null {
    const st = predictionLayoutStatus();
    if (st.ok) return null;
    const parts: string[] = [];
    if (st.mismatches.length) parts.push("echecs: " + st.mismatches.join(" ; "));
    if (st.unresolved.length) parts.push(st.unresolved.join(", "));
    if (st.unavailable) parts.push("primitive de metadonnees indisponible");
    return "LAYOUT DE PREDICTION NON RESOLU (#279/#276/#268) -- " + parts.join(" | ")
        + ". Le decodeur resout ses champs PAR NOM dans les metadonnees IL2CPP ;"
        + " un nom absent veut dire que le struct a ete RENOMME, pas deplace."
        + " Refaire le RE avant de croire une seule valeur de degat.";
}

/** Dérive entre la disposition LIVE et la table RE de `rnca9r7q6c`. Non nul = la doc de
 *  ce fichier est périmée (le décodeur, lui, reste juste). */
export function predictionLayoutDrift(): string | null {
    const st = predictionLayoutStatus();
    if (st.drift.length === 0) return null;
    return "DISPOSITION DE PREDICTION DEPLACEE depuis rnca9r7q6c -- "
        + st.drift.join(" ; ")
        + ". Le decodeur SUIT (resolution par nom) ; c'est la table documentee en tete"
        + " de frida/hooks/game/damage-prediction.ts qui est a refaire.";
}

// ─── Lecture ──────────────────────────────────────────────────────────────────────

export interface MinMax { min: number; max: number; }

/** `IdunBattle.Core.Services.MinMaxDamage` — `Min` / `Max` résolus par nom. */
export function readMinMaxDamage(base: NativePointer): MinMax {
    return {
        min: base.add(MINMAX_MIN).readS32(),
        max: base.add(MINMAX_MAX).readS32(),
    };
}

export interface DamagePredictionFields {
    hpBefore: number;
    /** `CurrentArmor` n'existe PAS dans `DamagePredictionResult` : les métadonnées
     *  IL2CPP en rendent la liste EXHAUSTIVE (18 champs, mesurés par `classFields`) et
     *  aucun ne porte ce nom. L'ancien décodeur appelait « armor » le `+0x04`, qui est
     *  `CurrentShield`. On rend `null` — une absence PROUVÉE, pas un offset deviné. */
    armorBefore: number | null;
    shieldBefore: number;
    /** Bornes du `DefaultScenario`. ⚠ `willKillDmg` n'est que la branche `else` de
     *  `get_WillBeKill` : la borne EFFECTIVE est `willKillDmgEffective`, et le verdict
     *  est `willBeKill`. `mightKillDmg`, lui, EST la borne complète de `get_MightBeKill`
     *  (aucun gate natif de ce côté — l'asymétrie est native). */
    willKillDmg: number;
    mightKillDmg: number;
    /** #372 — `CannotBeGuaranteedKilled@0x89`. `1` => `get_WillBeKill` rend `false`
     *  QUELLES QUE SOIENT les bornes. Unique écrivain : `PredictNormalAttack`. */
    cannotBeGuaranteedKilled: number;
    /** #372 — `BlockScenarios@0x38` : `Count`, puis les champs de `[0]` quand `Count >= 1`.
     *  `null` = TRI-ÉTAT « non mesuré » (liste illisible / chaîne non résolue), JAMAIS
     *  « zéro scénario » — un `0` de `blockScenarioCount` est, lui, une mesure. */
    blockScenarioCount: number | null;
    blockProbability: number | null;
    /** `BlockScenarios[0].Damage.HealthDamage.Min` = le `+0x0c` que lit `get_WillBeKill`. */
    blockKillDmg: number | null;
    /** `BlockScenarios[0].Damage.HealthDamage.Max` — lu par `get_HealthDamageWithBlock`,
     *  PAS par `get_MightBeKill`. Exposé pour recouper la paire. */
    blockMightDmg: number | null;
    /** #372 — la borne EFFECTIVEMENT comparée par `get_WillBeKill` :
     *  `blockKillDmg` si `blockScenarioCount >= 1`, sinon `willKillDmg`. */
    willKillDmgEffective: number | null;
    /** #372 — `get_WillBeKill` mirroré ENTIER (gate + choix de borne + comparaison).
     *  `null` = indécidable (une entrée non mesurée). Les consommateurs lisent CE champ ;
     *  ré-assembler la règle chez soi est exactement ce qui a produit les verdicts en
     *  aveugle de `#353-r1` et `#344-r2`. */
    willBeKill: boolean | null;
    /** #372 — `get_MightBeKill` mirroré : `CurrentHealth <= mightKillDmg`, sans gate. */
    mightBeKill: boolean;
    healthDmgMin: number;
    healthDmgMax: number;
    shieldDmgMin: number;
    shieldDmgMax: number;
    totalDmgMin: number;
    totalDmgMax: number;
    limitedByMinHp: number;
    mightCrit: number;
    forceOverkill: number;
    preventOverkill: number;
    appliedHits: number;
    /** Violations de FORME détectées à la lecture (vide = rien d'anormal). Non vide
     *  ne veut pas dire « le natif a tort » : ça veut dire « ce décodeur ne décode
     *  plus ce struct ». Cf. `damagePredictionShapeErrors`. */
    shapeErrors?: string[];
}

/** Sentinelles de FORME : des propriétés que le natif ne peut PAS violer, donc dont
 *  la violation accuse le décodeur et non la bataille.
 *
 *  C'est la seconde moitié de la garde : la résolution par nom attrape un champ disparu,
 *  ces sentinelles attrapent une base fausse (mauvais `+0x10` de boxing, mauvais stride
 *  dans un `List<T>`, pointeur d'event mal calculé) — c'est-à-dire les cas où le struct
 *  est intact mais où l'on lit à côté. `mightCrit = 25` était exactement ça. */
export function damagePredictionShapeErrors(v: DamagePredictionFields): string[] {
    const errs: string[] = [];
    const bools: Array<[string, number]> = [
        ["mightCrit", v.mightCrit], ["forceOverkill", v.forceOverkill],
        ["preventOverkill", v.preventOverkill], ["limitedByMinHp", v.limitedByMinHp],
        ["cannotBeGuaranteedKilled", v.cannotBeGuaranteedKilled],
    ];
    for (const [name, b] of bools) {
        if (b !== 0 && b !== 1) errs.push(name + "=" + b + " hors {0,1}");
    }
    if (v.hpBefore < 0) errs.push("hpBefore=" + v.hpBefore + " negatif");
    if (v.shieldBefore < 0) errs.push("shieldBefore=" + v.shieldBefore + " negatif");
    if (v.appliedHits < 0 || v.appliedHits > 256) {
        errs.push("appliedHits=" + v.appliedHits + " hors [0,256]");
    }
    const pairs: Array<[string, number, number]> = [
        ["healthDmg", v.healthDmgMin, v.healthDmgMax],
        ["shieldDmg", v.shieldDmgMin, v.shieldDmgMax],
        ["totalDmg", v.totalDmgMin, v.totalDmgMax],
        ["killDmg", v.willKillDmg, v.mightKillDmg],
    ];
    for (const [name, mn, mx] of pairs) {
        if (mn > mx) errs.push(name + " min=" + mn + " > max=" + mx);
        if (mn < 0) errs.push(name + "Min=" + mn + " negatif");
    }
    // #372 — `BlockScenarios` : le natif y met UN scénario par source de blocage du
    // défenseur. Un compte négatif ou délirant n'accuse pas la bataille mais la base de
    // lecture (mauvais stride d'event, `+0x10` de boxing oublié) — même famille que le
    // `mightCrit = 25` de #276. Le seuil est LARGE à dessein : il attrape le garbage, pas
    // un cas de jeu inhabituel.
    if (v.blockScenarioCount !== null
        && (v.blockScenarioCount < 0 || v.blockScenarioCount > 1024)) {
        errs.push("blockScenarioCount=" + v.blockScenarioCount + " hors [0,1024]");
    }
    if (v.blockKillDmg !== null && v.blockMightDmg !== null
        && v.blockKillDmg > v.blockMightDmg) {
        errs.push("blockKillDmg=" + v.blockKillDmg + " > blockMightDmg=" + v.blockMightDmg);
    }
    return errs;
}

/** `IdunBattle.Core.Services.DamagePredictionResult$$get_WillBeKill` mirroré, à partir des
 *  champs DÉJÀ décodés. Isolé pour être testable hors process (`resolvePredictionLayout`
 *  a sa façade `LayoutProbe` ; ceci n'a même pas besoin de mémoire).
 *
 *      if (CannotBeGuaranteedKilled) return false;
 *      m = (BlockScenarios != null && BlockScenarios.Count >= 1)
 *          ? BlockScenarios[0].Damage.HealthDamage.Min
 *          : DefaultScenario.Damage.HealthDamage.Min;
 *      return CurrentHealth <= m;
 *
 *  Rend `null` quand une entrée n'a PAS été mesurée : mieux vaut un canal qui dit « je ne
 *  sais pas » qu'un `false` indiscernable d'un vrai « pas de kill garanti ». */
export function computeWillBeKill(
    v: Pick<DamagePredictionFields,
        "hpBefore" | "willKillDmg" | "cannotBeGuaranteedKilled"
        | "blockScenarioCount" | "blockKillDmg">,
): { willBeKill: boolean | null; effective: number | null } {
    if (v.cannotBeGuaranteedKilled !== 0) return { willBeKill: false, effective: null };
    if (v.blockScenarioCount === null) return { willBeKill: null, effective: null };
    let m: number;
    if (v.blockScenarioCount >= 1) {
        if (v.blockKillDmg === null) return { willBeKill: null, effective: null };
        m = v.blockKillDmg;
    } else {
        m = v.willKillDmg;
    }
    return { willBeKill: v.hpBefore <= m, effective: m };
}

/** Décode un `DamagePredictionResult` dont `base` est le PREMIER OCTET DES CHAMPS
 *  (donc `boxed + 0x10` pour un struct boxé, `event + PDE_PREDICTION_OFF` dans un
 *  `ProbableDamageEvent`, ou le `sret` tel quel dans un hook de `PredictAttack*`).
 *
 *  **LÈVE** si la résolution par nom a échoué. C'est le point de la conversion : rendre
 *  des zéros, ou lire à `-1`, produirait des valeurs plausibles et indétectables — le
 *  défaut même que #268 a mis des jours à identifier. Tous les appelants de hook sont
 *  déjà sous `try` (`ai-trace/state.ts`, `scorer-damage-trace.ts`, `rpc-predict.ts`) ;
 *  ceux qui ne le sont pas doivent faire remonter l'erreur, pas la lisser. */
export function readDamagePredictionResult(
    base: NativePointer,
): DamagePredictionFields {
    if (L === null) {
        throw new Error(predictionLayoutError()
            ?? "LAYOUT DE PREDICTION NON RESOLU (#279)");
    }
    const health = readMinMaxDamage(base.add(DPR.healthDamage));
    const shield = readMinMaxDamage(base.add(DPR.shieldDamage));
    const total = readMinMaxDamage(base.add(DPR.totalDamage));
    const scenario = readMinMaxDamage(base.add(DPR.scenarioHealthDamage));
    // #372 — `BlockScenarios@0x38`. Une DÉRÉFÉRENCE de pointeur, pas une lecture de champ :
    // c'est une classe de risque distincte du reste du décodeur (le pointeur peut être nul,
    // et une base fausse le rend arbitraire). D'où le tri-état `null` = « non mesuré », et
    // le `catch` LOCAL : perdre ce champ ne doit pas faire perdre les vingt autres — mais
    // il laisse une trace dans `shapeErrors`, jamais un zéro silencieux.
    const blockErrs: string[] = [];
    let blockScenarioCount: number | null = null;
    let blockProbability: number | null = null;
    let blockKillDmg: number | null = null;
    let blockMightDmg: number | null = null;
    const SCN = L.scenario;
    if (SCN === null) {
        blockErrs.push("BlockScenarios NON LU : chaine DamagePredictionScenario non resolue");
    } else {
        try {
            const list = base.add(DPR.blockScenarios).readPointer();
            if (list.isNull()) {
                blockScenarioCount = 0;          // MESURE : `BlockScenarios == null`
            } else {
                blockScenarioCount = list.add(LIST_SIZE).readS32();
                if (blockScenarioCount >= 1 && blockScenarioCount <= 1024) {
                    const items = list.add(LIST_ITEMS).readPointer();
                    if (items.isNull()) {
                        blockErrs.push("BlockScenarios._items NUL avec Count="
                            + blockScenarioCount);
                    } else {
                        const s0 = items.add(ARRAY_FIRST);      // index 0, stride SCN.stride
                        blockProbability = s0.add(SCN.probability).readS32();
                        blockKillDmg = s0.add(SCN.healthDamageMin).readS32();
                        blockMightDmg = s0.add(SCN.healthDamageMax).readS32();
                    }
                }
            }
        } catch (e) {
            blockScenarioCount = null;
            blockErrs.push("BlockScenarios ILLISIBLE : " + (e as Error).message);
        }
    }
    const hpBefore = base.add(DPR.currentHealth).readS32();
    const cannotBeGuaranteedKilled = base.add(DPR.cannotBeGuaranteedKilled).readU8();
    const kill = computeWillBeKill({
        hpBefore, willKillDmg: scenario.min, cannotBeGuaranteedKilled,
        blockScenarioCount, blockKillDmg,
    });
    const v: DamagePredictionFields = {
        hpBefore,
        armorBefore: null,
        shieldBefore: base.add(DPR.currentShield).readS32(),
        willKillDmg: scenario.min,
        mightKillDmg: scenario.max,
        cannotBeGuaranteedKilled,
        blockScenarioCount, blockProbability, blockKillDmg, blockMightDmg,
        willKillDmgEffective: kill.effective,
        willBeKill: kill.willBeKill,
        mightBeKill: hpBefore <= scenario.max,
        healthDmgMin: health.min,
        healthDmgMax: health.max,
        shieldDmgMin: shield.min,
        shieldDmgMax: shield.max,
        totalDmgMin: total.min,
        totalDmgMax: total.max,
        limitedByMinHp: base.add(DPR.limitedByMinHp).readU8(),
        mightCrit: base.add(DPR.mightCrit).readU8(),
        forceOverkill: base.add(DPR.forceOverkill).readU8(),
        preventOverkill: base.add(DPR.preventOverkill).readU8(),
        appliedHits: base.add(DPR.appliedHits).readS32(),
    };
    const errs = blockErrs.concat(damagePredictionShapeErrors(v));
    if (errs.length) v.shapeErrors = errs;
    return v;
}

/** Fix64 (Q32.32) lu en mémoire. */
export function readFix64(p: NativePointer): number {
    return p.readS64().toNumber() / 4294967296;
}
