/** Décodeur UNIQUE de `IdunBattle.Core.Services.DamagePredictionResult` et de son
 *  enveloppe `IdunBattle.AI.Playbook.ProbableDamageEvent` (#276).
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
 *  Un seul décodeur, donc, et une GARDE DE LAYOUT (`predictionLayoutStatus`) qui
 *  confronte la taille de classe LIVE aux tailles RE de ce build. Au prochain
 *  changement de build, le canal dira « layout périmé » au lieu de rendre du garbage.
 *
 *  ─────────────────────────────────────────────────────────────────────────────────
 *  LAYOUT — re-dérivé au décompilé de `rnca9r7q6c`, une preuve par ligne
 *  ─────────────────────────────────────────────────────────────────────────────────
 *  `DamagePredictionResult` est un `System.ValueType` : `classes.tsv` annonce **176**
 *  (taille BOXÉE), les champs occupent donc **0xA0**. Confirmé trois fois par du code :
 *  `unit_HUD_test$$CreateDamagePrediction` et
 *  `IdunBattle.Core.Services.DamagePrediction$$PredictAttackRaw` font tous deux un
 *  `memset(dst, 0, 0xa0)`, et
 *  `IdunBattleLogic.Entities.Abilities.Triggered.Loki.HarlequinsPanoplyAbility$$SurvivesByDiscardingHits`
 *  en recopie exactement `+0x00 .. +0x9f`.
 *
 *  `MinMaxDamage` (16 o de champs) = `{ Nullable<int> Cap@+0x00 (value@+0, hasValue@+4),
 *  int Min@+0x08, int Max@+0x0c }` — lu dans `IdunBattle.Core.Services.MinMaxDamage$$Avg`
 *  (`(this[8] + this[0xc]) / 2`) et `IdunBattle.Core.Services.MinMaxDamage$$ApplyCap`.
 *  Ce motif `Min@+8 / Max@+0xc` a SURVÉCU à la migration ; ce qui a bougé, c'est la
 *  position des `MinMaxDamage` dans le struct englobant.
 *
 *  | off  | champ                                   | fonction native qui le PROUVE |
 *  |------|-----------------------------------------|-------------------------------|
 *  | 0x00 | `CurrentHealth` (int)                   | `DamagePredictionResult$$get_MightBeKill` (`*this <= *(this+0x20)`), 1er arg d'`IsOverkill` dans `MightBeOverkill` |
 *  | 0x04 | `CurrentShield` (int)                   | `DamagePredictionResult$$CalculateProbabilisticDamagePart` : `Math.Min(this[4], scenario.ShieldDamage)` ; `CalculateProbabilisticDamage` : cap `this[0] + this[4]`. Recoupé par `unit_HUD_test$$CreateDamagePrediction` (l'arg `currentShield` y atterrit à +0x04) |
 *  | 0x08 | **non identifié** (8 o)                 | aucun lecteur trouvé — l'ancien décodeur lisait `Armor@0x04 / Shield@0x08`, ce qui est FAUX ici |
 *  | 0x10 | `DefaultBlockScenario` (`DamagePredictionScenario`, 36 o) | `DamagePredictionResult$$get_DefaultBlockScenario` recopie `+0x10 .. +0x33` ; `PredictAttackRaw` y écrit le retour de `DamagePrediction$$CalculateDamagePredictionScenario` |
 *  | 0x10 |  · `Probability` (int, en %)            | `CalculateProbabilisticDamagePart` : `Fix64(scenario[0]) / 100`, clampé [0,1] |
 *  | 0x14 |  · `HealthDamage` (MinMaxDamage) -> **Min@0x1c / Max@0x20** | `get_HealthDamageWithBlock` (copie `+0x14..+0x23`), `get_WillBeKill` (0x1c), `get_MightBeKill` (0x20) |
 *  | 0x24 |  · `ShieldDamage` (MinMaxDamage) -> Min@0x2c / Max@0x30 | `get_ShieldDamage`, `get_ShieldDamageWithBlock` |
 *  | 0x38 | `List<DamagePredictionScenario>` (scénarios de BLOCAGE) | `get_*WithBlock` / `GetBlockScenarioOrDefault` lisent `list[0]` quand la liste est non vide |
 *  | 0x40 | `HealthDamage` (MinMaxDamage) -> **Min@0x48 / Max@0x4c** | `IdunBattle.AI.Utilities.DamageUtility$$GetHealthDamage` = `MinMaxDamage$$Avg(pred + 0x40)` |
 *  | 0x50 | `ShieldDamage` (MinMaxDamage) -> **Min@0x58 / Max@0x5c** | `IdunBattle.AI.Utilities.DamageUtility$$GetShieldDamage` = `MinMaxDamage$$Avg(pred + 0x50)` |
 *  | 0x60 | `TotalDamage` (MinMaxDamage) -> **Min@0x68 / Max@0x6c** | `unit_HUD_test$$CreateDamagePrediction` y écrit `minArmor + minHealth` / `maxArmor + maxHealth` ; `PredictAttackRaw` y pose le retour de `MinMaxDamage$$Add` |
 *  | 0x70 | `List<?>` (non identifiée)              | `unit_HUD_test$$CreateDamagePrediction` |
 *  | 0x78 | int — retour de `DamagePrediction$$ApplyTraitDamageLimitsToDamage` | `PredictAttackRaw` |
 *  | 0x80 | `List<IdunBattle.Core.HitDamage>` (un élément par COUP) | `PredictAttackRaw` (ctor `HitDamage` -> `List.Add`) ; `HarlequinsPanoplyAbility$$SurvivesByDiscardingHits` (`list[0].Damage`) |
 *  | 0x88 | `LimitedByMinHp` (bool)                 | `PredictAttackRaw` y écrit le `out wasReducedByMinHp` de `CalculateDamagePredictionScenario` ; `DamageUtility$$GetHealthDamage` renvoie `CurrentHealth` quand il est vrai |
 *  | 0x89 | bool — gate de `get_WillBeKill` / `WillBeOverkill` (sortie anticipée `false`) | `DamagePredictionResult$$get_WillBeKill` — **non nommé** |
 *  | 0x8a | `MightCrit` (bool)                      | `DamagePredictionResult$$MightBeOverkill` -> 3e arg (`isCritical`) de `DamagePrediction$$IsOverkill` |
 *  | 0x8b | `ForceOverkill` (bool)                  | `MightBeOverkill` / `WillBeOverkill` -> 4e arg |
 *  | 0x8c | `PreventOverkill` (bool)                | `MightBeOverkill` / `WillBeOverkill` -> 5e arg |
 *  | 0x90 | `Nullable<int>` (value@0x90, hasValue@0x94) -> args 6/7 d'`IsOverkill` | `MightBeOverkill` / `WillBeOverkill` |
 *  | 0x98 | `AppliedHits` (int)                     | `PredictAttackRaw` le pose à **1** au moment exact où UN `HitDamage` est ajouté à la liste `@0x80` ; `DamagePredictionResult$$Add` le SOMME (seul `int` agrégé du struct) |
 *  | 0x9c | int — **non identifié**                 | dernier mot du struct |
 *
 *  `ProbableDamageEvent` = **200** boxé -> **0xB8** de champs, monté par
 *  `IdunBattle.AI.Playbook.ProbableDamageEvent$$.ctor(this, target, damagePrediction,
 *  probability, weight)` : `IEntity Target@0x00` (POINTEUR, pas un id), la copie
 *  intégrale de `DamagePredictionResult` à **+0x08** (le ctor recopie `dp+0x00..0x9f`
 *  vers `this+0x08..0xa7`, décalage constant), `Fix64 Probability@0xA8`,
 *  `Fix64 Weight@0xB0`. Les deux `Fix64` arrivent en `Nullable<Fix64>` : absent -> 1.0.
 *
 *  `ProbableHealEvent` / `ProbableEffectEvent` = **40** boxés -> **0x18** de champs,
 *  ctors `ProbableHealEvent$$.ctor` / `ProbableEffectEvent$$.ctor` :
 *  `IEntity Target@0x00` ; puis, pour le heal, un **POINTEUR** de prédiction @0x08
 *  (`*(void**)(this+8) = healPrediction`) — surtout PAS deux `int` — et pour l'effect
 *  un `int EffectType@0x08` ; `Fix64 Probability@0x10` dans les deux cas.
 */

import {
    class_instance_size, findClassAnywhere,
} from "../il2cpp/helpers.js";

// ─── Tailles RE (build rnca9r7q6c) ────────────────────────────────────────────────

/** Champs de `DamagePredictionResult`, header exclu. `memset(.., 0, 0xa0)` dans
 *  `PredictAttackRaw` ET `unit_HUD_test$$CreateDamagePrediction`. */
export const DPR_SIZE = 0xa0;
/** Taille BOXÉE (= `il2cpp_class_instance_size`) : header 0x10 + `DPR_SIZE`. */
export const DPR_BOXED_SIZE = 0xb0;
/** Champs de `ProbableDamageEvent` = son STRIDE dans un `List<T>` / un tableau. */
export const PDE_STRIDE = 0xb8;
export const PDE_BOXED_SIZE = 0xc8;
/** `Probable{Heal,Effect}Event` : 3 slots de 8 o. */
export const SMALL_EVENT_STRIDE = 0x18;
export const SMALL_EVENT_BOXED_SIZE = 0x28;

/** Décalage du `DamagePredictionResult` embarqué dans un `ProbableDamageEvent`
 *  (`ProbableDamageEvent$$.ctor` : `dp+X` -> `event+0x08+X`). */
export const PDE_PREDICTION_OFF = 0x08;
/** `Fix64 Probability` puis `Fix64 Weight`, écrits en fin de `ProbableDamageEvent$$.ctor`
 *  (`this+0xa8` / `this+0xb0`). Les deux arrivent en `Nullable<Fix64>` : le ctor
 *  substitue `Fix64(1)` quand `HasValue` est faux — donc une probabilité NULLE ne peut
 *  pas venir du natif, c'est une sentinelle de décodage. */
export const PDE_PROBABILITY_OFF = 0xa8;
export const PDE_WEIGHT_OFF = 0xb0;

// ─── Offsets `DamagePredictionResult` (champs nus, base = début du struct) ─────────

export const DPR = {
    currentHealth: 0x00,
    currentShield: 0x04,
    /** `DefaultBlockScenario.Probability`, en pourcents entiers. */
    scenarioProbability: 0x10,
    /** `DefaultBlockScenario.HealthDamage` — les bornes que lisent `get_WillBeKill`
     *  (Min) et `get_MightBeKill` (Max). C'est la paire « RAW » des sondes overkill. */
    scenarioHealthDamage: 0x14,
    scenarioShieldDamage: 0x24,
    blockScenarios: 0x38,
    /** `MinMaxDamage$$Avg(pred+0x40)` = `DamageUtility$$GetHealthDamage`. */
    healthDamage: 0x40,
    /** `MinMaxDamage$$Avg(pred+0x50)` = `DamageUtility$$GetShieldDamage`. */
    shieldDamage: 0x50,
    totalDamage: 0x60,
    hitDamages: 0x80,
    limitedByMinHp: 0x88,
    mightCrit: 0x8a,
    forceOverkill: 0x8b,
    preventOverkill: 0x8c,
    appliedHits: 0x98,
} as const;

/** `MinMaxDamage` : `Min` à `+0x08`, `Max` à `+0x0c` (cf. `MinMaxDamage$$Avg`). */
export const MINMAX_MIN = 0x08;
export const MINMAX_MAX = 0x0c;

// ─── Garde de layout ──────────────────────────────────────────────────────────────

export interface LayoutStatus {
    /** true = toutes les tailles LIVE correspondent aux tailles RE de ce build. */
    ok: boolean;
    /** Détail des divergences, vide si `ok`. Une entrée par classe fautive. */
    mismatches: string[];
    /** Classes que `findClassAnywhere` n'a pas résolues (garde non concluante). */
    unresolved: string[];
    /** true si `il2cpp_class_instance_size` n'est pas exporté (garde inopérante). */
    unavailable: boolean;
}

let layoutStatus: LayoutStatus | null = null;

/** Confronte, UNE FOIS puis en cache, la taille de classe LIVE aux tailles RE.
 *
 *  C'est la garde qui manquait : les offsets de ce module sont vrais pour un build
 *  donné et deviennent faux SILENCIEUSEMENT au suivant. Une taille de classe qui
 *  change est le signal le plus précoce et le moins cher qu'on ait — il n'exige ni
 *  bataille, ni cible, ni valeur de référence.
 *
 *  Ne LÈVE jamais (on est dans des hooks) : le statut se propage aux payloads. */
export function predictionLayoutStatus(): LayoutStatus {
    if (layoutStatus !== null) return layoutStatus;
    const st: LayoutStatus = {
        ok: true, mismatches: [], unresolved: [], unavailable: false,
    };
    const sizeOf = class_instance_size;
    if (sizeOf === null) {
        st.unavailable = true;
        st.ok = false;
        layoutStatus = st;
        return st;
    }
    const expect: Array<[string, string, number]> = [
        ["IdunBattle.Core.Services", "DamagePredictionResult", DPR_BOXED_SIZE],
        ["IdunBattle.AI.Playbook", "ProbableDamageEvent", PDE_BOXED_SIZE],
        ["IdunBattle.AI.Playbook", "ProbableHealEvent", SMALL_EVENT_BOXED_SIZE],
        ["IdunBattle.AI.Playbook", "ProbableEffectEvent", SMALL_EVENT_BOXED_SIZE],
    ];
    for (const [ns, cls, want] of expect) {
        let klass: NativePointer | null = null;
        try { klass = findClassAnywhere(ns, cls); } catch { klass = null; }
        if (klass === null || klass.isNull()) {
            st.unresolved.push(ns + "." + cls);
            continue;
        }
        let got = -1;
        try { got = sizeOf(klass) as number; } catch { got = -1; }
        if (got !== want) {
            st.ok = false;
            st.mismatches.push(
                ns + "." + cls + ": live=" + got + " attendu=" + want
                + " (offsets RE du build rnca9r7q6c)");
        }
    }
    if (st.unresolved.length > 0) st.ok = false;
    layoutStatus = st;
    return st;
}

/** Message ASCII prêt à remonter dans un payload d'erreur (les sondes Python
 *  l'impriment sur une console cp1252). Vide si la garde passe. */
export function predictionLayoutError(): string | null {
    const st = predictionLayoutStatus();
    if (st.ok) return null;
    if (st.unavailable) {
        return "garde de layout INOPERANTE : il2cpp_class_instance_size non exporte";
    }
    const parts: string[] = [];
    if (st.mismatches.length) parts.push("tailles: " + st.mismatches.join(" ; "));
    if (st.unresolved.length) parts.push("classes non resolues: " + st.unresolved.join(", "));
    return "LAYOUT DE PREDICTION PERIME (#276/#268) -- " + parts.join(" | ")
        + ". Le decodeur des hooks a ete re-derive sur le build rnca9r7q6c ;"
        + " re-faire le RE avant de croire une seule valeur de degat.";
}

// ─── Lecture ──────────────────────────────────────────────────────────────────────

export interface MinMax { min: number; max: number; }

/** `IdunBattle.Core.Services.MinMaxDamage` — `Min@+0x08`, `Max@+0x0c`. */
export function readMinMaxDamage(base: NativePointer): MinMax {
    return {
        min: base.add(MINMAX_MIN).readS32(),
        max: base.add(MINMAX_MAX).readS32(),
    };
}

export interface DamagePredictionFields {
    hpBefore: number;
    /** `CurrentArmor` n'a **aucun lecteur identifié** dans le décompilé de ce build :
     *  le `+0x04` que l'ancien décodeur appelait « armor » est `CurrentShield`, et
     *  `+0x08` n'est lu nulle part. On rend `null` plutôt qu'un offset deviné — c'est
     *  exactement le défaut que #276 répare. */
    armorBefore: number | null;
    shieldBefore: number;
    /** Bornes du `DefaultBlockScenario` : `hp <= willKillDmg` => mort GARANTIE
     *  (`get_WillBeKill`), `hp <= mightKillDmg` => mort POSSIBLE (`get_MightBeKill`). */
    willKillDmg: number;
    mightKillDmg: number;
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
 *  C'est la seconde moitié de la garde : la taille de classe attrape un changement de
 *  layout, ces sentinelles attrapent une base fausse (mauvais `+0x10` de boxing,
 *  mauvais stride dans un `List<T>`, pointeur d'event mal calculé) — c'est-à-dire les
 *  cas où la classe est intacte mais où l'on lit à côté. `mightCrit = 25` sur un
 *  `bool` était exactement ça. */
export function damagePredictionShapeErrors(v: DamagePredictionFields): string[] {
    const errs: string[] = [];
    const bools: Array<[string, number]> = [
        ["mightCrit", v.mightCrit], ["forceOverkill", v.forceOverkill],
        ["preventOverkill", v.preventOverkill], ["limitedByMinHp", v.limitedByMinHp],
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
    return errs;
}

/** Décode un `DamagePredictionResult` dont `base` est le PREMIER OCTET DES CHAMPS
 *  (donc `boxed + 0x10` pour un struct boxé, `event + 0x08` dans un
 *  `ProbableDamageEvent`, ou le `sret` tel quel dans un hook de `PredictAttack*`). */
export function readDamagePredictionResult(
    base: NativePointer,
): DamagePredictionFields {
    const health = readMinMaxDamage(base.add(DPR.healthDamage));
    const shield = readMinMaxDamage(base.add(DPR.shieldDamage));
    const total = readMinMaxDamage(base.add(DPR.totalDamage));
    const scenario = readMinMaxDamage(base.add(DPR.scenarioHealthDamage));
    const v: DamagePredictionFields = {
        hpBefore: base.add(DPR.currentHealth).readS32(),
        armorBefore: null,
        shieldBefore: base.add(DPR.currentShield).readS32(),
        willKillDmg: scenario.min,
        mightKillDmg: scenario.max,
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
    const errs = damagePredictionShapeErrors(v);
    if (errs.length) v.shapeErrors = errs;
    return v;
}

/** Fix64 (Q32.32) lu en mémoire. */
export function readFix64(p: NativePointer): number {
    return p.readS64().toNumber() / 4294967296;
}
