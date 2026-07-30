/** Oracle MakeDamagePredictions PARTAGÉ (#102/#103).
 *
 *  Invoque le `<Ability>Playbook.MakeDamagePredictions` NATIF — le dégât per-ability
 *  que l'IA SCORE réellement — au lieu de `GetAllPredictions` (le PREVIEW decisionView,
 *  Attack-based quel que soit l'abilityType, donc FAUX pour une spéciale config-based
 *  comme PlasmaCannon). Utilisé par le RPC `aiPlaybookPredict` (rpc-predict.ts) ET par
 *  l'affichage `decisionView.attackPlans`/`exposureView` (projection.ts). Read-only.
 *
 *  Chaîne native mirrorée (RE #102/#103) :
 *   1. `PlaybookDatabase.LoadPlaybook(ActiveAbilityType, bool fallbackToDefault)` @1810e0090
 *      (registry _playbookBuilders@+0x68 / _loadedPlaybooks@+0x70, fallback
 *      _defaultPlaybookBuilder@+0x80 = attaque normale + toute ability sans playbook
 *      bespoke). ⚠ 2 overloads homonymes à AUTRE key-space (Triggered@1810dfd10,
 *      UnitSpecificBehaviour@1810dfed0) → désambiguïser par TYPE de param. L'INSTANCE
 *      PlaybookDatabase est posée par `IdunRunner.Initialize @180e35400` → résolue par
 *      SCAN des champs pointeurs (runner→aiControl→services), match par nom de classe.
 *   2. `playbook.MakeDamagePredictions(caster, UnitPosition, target[, AbilityState*])` —
 *      slot vtable +0x358 (scorer `CalculateUtilityFromPredictions @181407890`). Le
 *      playbook monte son AbilityEntities en INTERNE (ability à playbook+0x68).
 *      `UnitPosition` d'une tuile candidate = `EntityExtensions.GetUnitPositionAtTile
 *      @180eb6dc0` (mono-tuile → UnitPosition..ctor([tile]) ; multi-tuile → footprint
 *      offset natif) — c'est ce que les movers natifs utilisent (ArmouredMight_MoveAbility).
 *      `AbilityState` {level@0, mult@4, 0@8} = l'entrée ActiveAbility (capteur #100).
 *   3. Retour `List<ProbableDamageEvent>` | `ProbableDamageEvent[]` | yield-machine
 *      `<MakeDamagePredictions>d__N`. Layout re-dérivé sur `rnca9r7q6c` (#276) depuis
 *      `IdunBattle.AI.Playbook.ProbableDamageEvent$$.ctor` : struct de **0xb8**,
 *      `IEntity Target`@+0x00, copie intégrale du `DamagePredictionResult`@+0x08,
 *      `Fix64 Probability`@+0xa8, `Fix64 Weight`@+0xb0. Le détail des champs et LA
 *      TABLE DES PREUVES vivent dans `game/damage-prediction.ts` — plus un seul
 *      offset de prédiction n'est écrit ici.
 *  #34 : décode AUSSI les Probable{Heal,Effect}Event (siblings du slot damage —
 *  `MakeHealPredictions` / `MakeEffectPredictions`, overrides bespoke ex. HealPlaybook)
 *  via le MÊME harnais (invocation par nom + List/array/yield). Layouts RE-VÉRIFIÉS sur
 *  `rnca9r7q6c` (#276) et **INCHANGÉS** — stride 0x18 (40 boxé − header) :
 *  `IEntity Target`@+0x00 ; HealEvent : `IdunBattle.Core.Services.HealPredictionResult`
 *  INLINE — c'est un ValueType de 8 o, donc passé PAR VALEUR en registre au ctor
 *  (`ProbableHealEvent$$.ctor` : `*(void**)(this+8) = healPrediction` écrit la VALEUR,
 *  pas un pointeur) : `{targetHpBefore@+0x08, healAmount@+0x0c}`. L'ordre vient du
 *  `return CONCAT44(iVar6, uVar14)` de `IdunBattle.Core.Services.DamagePrediction$$PredictHeal`,
 *  où `uVar14 = GetStat(target, 5)` (santé, mot BAS) et `iVar6` = le montant capé
 *  `FillUpStatComponent$$MaxFillUp` / `MaxReduce` (mot HAUT). EffectEvent :
 *  `int EffectType`@+0x08. `Fix64 Probability`@+0x10 dans les deux cas (Nullable → 1.0
 *  par défaut). Repair : PAS d'event — `MakeRepairPredictions` rend un Dictionary
 *  (décodage non porté, v2). */
import {
    class_get_name, class_instance_size, field_get_type, findMethodByNameSuffix,
    findMethodByParamClasses, findMethodByParamCount, getFieldInfo, getFieldOffset, s,
    type_get_class_or_element_class,
} from "../../il2cpp/helpers.js";
import { invokeMethod } from "../../il2cpp/invoke.js";
import { runnerOff } from "../../game/runner.js";
import { entityExtClass, servicesOff } from "./internals.js";
import {
    DamagePredictionFields, PDE_PREDICTION_OFF, PDE_PROBABILITY_OFF, PDE_STRIDE,
    PDE_WEIGHT_OFF, readDamagePredictionResult, readFix64, SMALL_EVENT_STRIDE,
} from "../../game/damage-prediction.js";

/** sizeof(ProbableDamageEvent) = son stride dans un `List<T>`/tableau. Re-dérivé du
 *  ctor natif (#276) — cf. `game/damage-prediction.ts`. */
const EVENT_STRIDE = PDE_STRIDE;

/** Un `ProbableDamageEvent` décodé = la cible + tous les champs du
 *  `DamagePredictionResult` embarqué (cf. `game/damage-prediction.ts` pour la table
 *  des offsets et de leurs preuves) + les deux `Fix64` de l'enveloppe.
 *
 *  `willKillDmg`/`mightKillDmg` = les bornes du `DefaultBlockScenario` que lisent
 *  `get_WillBeKill` / `get_MightBeKill` ; `mightCrit`/`forceOverkill`/`preventOverkill`
 *  = les trois arguments booléens que `MightBeOverkill` / `WillBeOverkill` passent à
 *  `IdunBattle.Core.Services.DamagePrediction$$IsOverkill` — mais pas les mêmes :
 *  `MightBeOverkill` passe `MightCrit`, `WillBeOverkill` passe le littéral 0.
 *  L'asymétrie est NATIVE (borne optimiste vs garantie), cf. `case-r34`. */
export interface DamageEvent extends DamagePredictionFields {
    targetId: number | null;
    probability: number; probMult: number;
}

export function classNameAt(p: NativePointer): string | null {
    try {
        const k = p.readPointer();
        if (k.isNull()) return null;
        return s(class_get_name(k) as NativePointer);
    } catch { return null; }
}

/** Résout la PlaybookDatabase (singleton battle) par SCAN des champs pointeurs
 *  (runner→aiControl→services, 1-2 niveaux), match par nom de classe. Aucun RVA. */
export function resolvePlaybookDatabase(
    runner: NativePointer,
): { db: NativePointer; dbSrc: string } | null {
    const scanForClass = (
        obj: NativePointer, want: string, maxOff: number,
    ): { p: NativePointer; off: number } | null => {
        if (obj.isNull()) return null;
        for (let off = 0x10; off < maxOff; off += 8) {
            try {
                const p = obj.add(off).readPointer();
                if (p.isNull()) continue;
                if (classNameAt(p) === want) return { p, off };
            } catch { break; }
        }
        return null;
    };
    const aiControl = runner.add(runnerOff.aiControl).readPointer();
    const services = servicesOff >= 0 ? runner.add(servicesOff).readPointer() : ptr(0);
    const roots: Array<[string, NativePointer, number]> = [
        ["runner", runner, 0x300], ["aiControl", aiControl, 0x200],
        ["services", services, 0x200],
    ];
    for (const [name, obj, max] of roots) {
        const hit = scanForClass(obj, "PlaybookDatabase", max);
        if (hit) return { db: hit.p, dbSrc: name + "+0x" + hit.off.toString(16) };
    }
    // Fallback 2-niveaux : PlaybookDatabase peut vivre dans un objet intermédiaire.
    if (!aiControl.isNull()) {
        for (let off = 0x10; off < 0x150; off += 8) {
            try {
                const mid = aiControl.add(off).readPointer();
                if (mid.isNull() || classNameAt(mid) === null) continue;
                const hit = scanForClass(mid, "PlaybookDatabase", 0x150);
                if (hit) {
                    return { db: hit.p,
                        dbSrc: "aiControl+0x" + off.toString(16) + "->+0x" + hit.off.toString(16) };
                }
            } catch { /* */ }
        }
    }
    return null;
}

/** LoadPlaybook(ActiveAbilityType, fallbackToDefault=true) — désambiguïse les 3
 *  overloads homonymes par TYPE du 1er param (un findMethodByParamCount(1) aveugle
 *  matche l'overload UnitSpecificBehaviour @1810dfed0 → mauvais playbook). Retourne
 *  le playbook (null si aucun / non résolu). */
export function loadPlaybook(db: NativePointer, abilityType: number): NativePointer {
    const loadMi = findMethodByParamClasses(
        db.readPointer(), "LoadPlaybook", ["ActiveAbilityType", null]);
    if (!loadMi) return ptr(0);
    const abilBuf = Memory.alloc(4); abilBuf.writeS32(abilityType | 0);
    const fallbackBuf = Memory.alloc(1); fallbackBuf.writeU8(1);   // fallbackToDefault = true
    try { return invokeMethod(loadMi.info, db, [abilBuf, fallbackBuf]); }
    catch { return ptr(0); }
}

/** UnitPosition d'une tuile candidate : `EntityExtensions.GetUnitPositionAtTile(unit,
 *  tile, state)` @180eb6dc0 (mono-tuile → [tile] ; multi-tuile → footprint offset natif),
 *  unbox à +0x10 (retour value-type boxé par l'invoke). Null si non résolu. */
export function unitPositionAtTile(
    unit: NativePointer, tile: NativePointer, statePtr: NativePointer,
): NativePointer | null {
    if (!entityExtClass) return null;
    const mi = findMethodByParamCount(entityExtClass, "GetUnitPositionAtTile", 3);
    if (!mi) return null;
    try {
        const pos = invokeMethod(mi.info, null, [unit, tile, statePtr]);
        if (pos.isNull()) return null;
        return pos.add(0x10);
    } catch { return null; }
}

/** UnitPosition COURANTE : `EntityExtensions.GetUnitPosition(unit, state)` @180eb72f0,
 *  unbox à +0x10. Null si non résolu. */
export function unitPositionCurrent(
    unit: NativePointer, statePtr: NativePointer,
): NativePointer | null {
    if (!entityExtClass) return null;
    const mi = findMethodByParamCount(entityExtClass, "GetUnitPosition", 2);
    if (!mi) return null;
    try {
        const pos = invokeMethod(mi.info, null, [unit, statePtr]);
        if (pos.isNull()) return null;
        return pos.add(0x10);
    } catch { return null; }
}

/** Invoque `Make<X>Predictions(caster, UnitPosition, target[, AbilityState{level,mult,0}])`
 *  sur le playbook (override résolu sur la classe CONCRÈTE). Arité 4 (avec AbilityState)
 *  d'abord — signature du slot +0x358 — 3 en secours. `methodName` défaut =
 *  "MakeDamagePredictions" ; #34 : mêmes args pour les siblings "MakeHealPredictions" /
 *  "MakeEffectPredictions" (base @18140a970/@18140a930 rend un enumerable VIDE quand le
 *  playbook n'override pas). Retourne {list, retClass, makeArity} (list null si non
 *  résolu / throw). */
export function makeDamagePredictions(
    playbook: NativePointer, unit: NativePointer, posPtr: NativePointer,
    target: NativePointer, level: number, mult: number,
    methodName: string = "MakeDamagePredictions",
): { list: NativePointer; retClass: string | null; makeArity: number } {
    const stateBuf = Memory.alloc(12);
    stateBuf.writeS32(level | 0);
    stateBuf.add(4).writeS32((mult ?? 100) | 0);
    stateBuf.add(8).writeS32(0);
    const pbCls = playbook.readPointer();
    let makeMi = findMethodByParamCount(pbCls, methodName, 4);
    let makeArgs: NativePointer[] = [unit, posPtr, target, stateBuf];
    if (!makeMi) {
        makeMi = findMethodByParamCount(pbCls, methodName, 3);
        makeArgs = [unit, posPtr, target];
    }
    if (!makeMi) return { list: ptr(0), retClass: null, makeArity: 0 };
    try {
        const list = invokeMethod(makeMi.info, playbook, makeArgs);
        return { list, retClass: list.isNull() ? null : classNameAt(list),
            makeArity: makeArgs.length };
    } catch { return { list: ptr(0), retClass: null, makeArity: makeArgs.length }; }
}

/** Lit UN `ProbableDamageEvent` (struct 0xb8) à l'adresse `ev`. La référence `IEntity`
 *  cible est un pointeur 8 o @+0x00 (un readS32 y lit du garbage) → résolue en unitId
 *  via `idByPtr`. Le `DamagePredictionResult` est copié INLINE dès +0x08 par
 *  `IdunBattle.AI.Playbook.ProbableDamageEvent$$.ctor`, d'où la délégation au décodeur
 *  unique : aucun offset de prédiction n'est écrit ici (#276). */
export function readDamageEvent(
    ev: NativePointer, idByPtr: Map<string, number>,
): DamageEvent {
    return {
        targetId: idByPtr.get(ev.readPointer().toString()) ?? null,
        ...readDamagePredictionResult(ev.add(PDE_PREDICTION_OFF)),
        probability: readFix64(ev.add(PDE_PROBABILITY_OFF)),
        probMult: readFix64(ev.add(PDE_WEIGHT_OFF)),
    };
}

/** #34 — `ProbableHealEvent` (`ProbableHealEvent$$.ctor`, stride 0x18) : target@+0x00 +
 *  `HealPredictionResult` INLINE (ValueType de 8 o = retour par VALEUR de
 *  `IdunBattle.Core.Services.DamagePrediction$$PredictHeal`, `CONCAT44(amount,
 *  currentHealth)`) : targetHpBefore@+0x08, healAmount@+0x0c (capé MaxFillUp
 *  maxHP−curHP / boss / group-limit) + probability@+0x10. RE-VÉRIFIÉ sur `rnca9r7q6c`
 *  (#276) : inchangé. */
export interface HealEvent {
    targetId: number | null;
    targetHpBefore: number; healAmount: number;
    probability: number;
}

/** #34 — `ProbableEffectEvent` (`ProbableEffectEvent$$.ctor`, stride 0x18) :
 *  target@+0x00, effectType(int)@+0x08, probability@+0x10. RE-VÉRIFIÉ (#276) :
 *  inchangé. */
export interface EffectEvent {
    targetId: number | null;
    effectType: number;
    probability: number;
}

export function readHealEvent(
    ev: NativePointer, idByPtr: Map<string, number>,
): HealEvent {
    return {
        targetId: idByPtr.get(ev.readPointer().toString()) ?? null,
        targetHpBefore: ev.add(0x08).readS32(),
        healAmount: ev.add(0x0c).readS32(),
        probability: readFix64(ev.add(0x10)),
    };
}

export function readEffectEvent(
    ev: NativePointer, idByPtr: Map<string, number>,
): EffectEvent {
    return {
        targetId: idByPtr.get(ev.readPointer().toString()) ?? null,
        effectType: ev.add(0x08).readS32(),
        probability: readFix64(ev.add(0x10)),
    };
}

/** Décode le retour d'un Make<X>Predictions en events (générique #34 : le READER et le
 *  STRIDE varient par famille, le harnais est identique). Gère les 3 formes :
 *  `List`1` (items@+0x10/count@+0x18, structs INLINE dès +0x20), array managé
 *  `Probable<X>Event[]` (max_length@+0x18, éléments dès +0x20), et yield-machine
 *  `<Make<X>Predictions>d__N` (IEnumerable ET IEnumerator : `<>1__state`=0 puis
 *  MoveNext + lecture du struct INLINE `<>2__current`). */
function decodeEventsGeneric<T>(
    list: NativePointer, idByPtr: Map<string, number>,
    reader: (ev: NativePointer, m: Map<string, number>) => T, stride: number,
): { events: T[]; count: number; retClass: string | null; error?: string } {
    const events: T[] = [];
    if (list.isNull()) return { events, count: -1, retClass: null };
    const retClass = classNameAt(list);
    try {
        if (retClass === "List`1") {
            const items = list.add(0x10).readPointer();
            const count = list.add(0x18).readS32();
            if (!items.isNull() && count > 0 && count < 64) {
                for (let i = 0; i < count; i++) {
                    events.push(reader(items.add(0x20 + i * stride), idByPtr));
                }
            }
            return { events, count, retClass };
        }
        if (retClass !== null && retClass.endsWith("[]")) {
            const count = list.add(0x18).readS32();
            if (count > 0 && count < 64) {
                for (let i = 0; i < count; i++) {
                    events.push(reader(list.add(0x20 + i * stride), idByPtr));
                }
            }
            return { events, count, retClass };
        }
        // Retour YIELD : machine d'état `<Make<X>Predictions>d__N` (IEnumerable
        // ET IEnumerator de Probable<X>Event). On CALL le GetEnumerator NATIF au
        // lieu de forcer `<>1__state`=0 à la main : GetEnumerator (state -2 → 0)
        // COPIE aussi les paramètres capturés `<>3__caster/target/pos/state` vers les
        // champs de TRAVAIL que MoveNext lit (RE @18117d570 : bloc LAB `this+0x118 =
        // this+0x120` …). Sans cette copie, MoveNext déréférence des champs nuls →
        // il2cpp "system error". GetEnumerator est une impl EXPLICITE d'interface
        // (nom qualifié `…IEnumerable<Probable<X>Event>.GetEnumerator`) → résolue
        // par suffixe. Retourne `this` (même thread, fast-path) ou un clone initialisé.
        const getEnumMi = findMethodByNameSuffix(list.readPointer(), "GetEnumerator", 0);
        if (!getEnumMi) {
            return { events, count: -1, retClass,
                error: "yield-machine sans GetEnumerator(0) (" + retClass + ")" };
        }
        let en: NativePointer;
        try { en = invokeMethod(getEnumMi.info, list, null); }
        catch (e) {
            return { events, count: -1, retClass,
                error: "GetEnumerator threw: " + (e as Error).message };
        }
        if (en.isNull()) return { events, count: -1, retClass, error: "GetEnumerator null" };
        const enCls = en.readPointer();
        const curOff = getFieldOffset(enCls, "<>2__current");
        const moveMi = findMethodByParamCount(enCls, "MoveNext", 0);
        if (curOff < 0 || !moveMi) {
            return { events, count: -1, retClass,
                error: "yield-machine: <>2__current/MoveNext non résolus (" + retClass + ")" };
        }
        let count = 0;
        for (let i = 0; i < 64; i++) {
            const more = invokeMethod(moveMi.info, en, null);   // bool boxé → valeur @+0x10
            if (more.isNull() || more.add(0x10).readU8() === 0) break;
            events.push(reader(en.add(curOff), idByPtr));
            count++;
        }
        return { events, count, retClass };
    } catch (e) {
        return { events, count: -1, retClass, error: "lecture events: " + (e as Error).message };
    }
}

export function decodeDamageEvents(
    list: NativePointer, idByPtr: Map<string, number>,
): { events: DamageEvent[]; count: number; retClass: string | null; error?: string } {
    return decodeEventsGeneric(list, idByPtr, readDamageEvent, EVENT_STRIDE);
}

export function decodeHealEvents(
    list: NativePointer, idByPtr: Map<string, number>,
): { events: HealEvent[]; count: number; retClass: string | null; error?: string } {
    return decodeEventsGeneric(list, idByPtr, readHealEvent, SMALL_EVENT_STRIDE);
}

export function decodeEffectEvents(
    list: NativePointer, idByPtr: Map<string, number>,
): { events: EffectEvent[]; count: number; retClass: string | null; error?: string } {
    return decodeEventsGeneric(list, idByPtr, readEffectEvent, SMALL_EVENT_STRIDE);
}

/** #45/#300 — décodage REPAIR. Le repair n'a PAS d'event :
 *  `IdunBattle.AI.Playbook.RepairPlaybook$$MakeRepairPredictions` rend un
 *  `Dictionary<IEntity, RepairPredictionResult>` {cible: PredictRepair(...)} — la base
 *  `NonComparablePlaybook<T>$$MakeRepairPredictions` rend un dict VIDE quand le playbook
 *  n'override pas.
 *
 *  ⚠ CE DÉCODEUR A ÉTÉ FAUX SUR DEUX AXES (#276-r1, corrigé le 2026-07-30). L'en-tête
 *  affirmait « RepairPrediction … 16 o = 4 ints : currentHealth, currentArmor, hpFill,
 *  armorFill », et le corps appliquait `ENTRY_SIZE = 32`. Les DEUX sont faux, mesuré :
 *
 *   1. **Le type de valeur n'a que DEUX champs.** RPC `classFields` sur la session live :
 *      `IdunBattle.Core.Services.RepairPredictionResult` -> `boxedSize 24, fieldsSize 8,
 *      fieldCount 2` = `Int32 CurrentHealth@+0x00`, `Int32 TotalHeal@+0x04`. La table
 *      versionnée concorde (`data/symbols/<build>/frida/classes.tsv` : `24 System.ValueType`).
 *      Il n'y a **aucun** champ d'armure — `CurrentArmor` a été établi ABSENT par #279, et
 *      `PredictArmorRestore` n'existe plus dans ce build. Les champs 3 et 4 lisaient donc
 *      des octets VOISINS. C'est le pendant exact de `HealPredictionResult` (même forme,
 *      même taille), et le miroir du correctif `33292bc4` sur `PredictRepair` lui-même.
 *   2. **Le stride était faux**, et c'est le plus grave : `Dictionary<K,V>.Entry` =
 *      `{int hashCode; int next; TKey key; TValue value}`. Avec une clé RÉFÉRENCE (8 o,
 *      alignée 8) et une valeur de 8 o, l'entrée fait **24 o**, pas 32. Dès `i = 1` on
 *      lisait à côté — y compris le `keyPtr`, donc l'identifiant de CIBLE lui-même.
 *      Un montage à une seule cible ne l'aurait jamais montré.
 *
 *  D'où ce décodage entièrement RÉSOLU PAR NOM, sans un seul littéral de layout : la
 *  classe `Entry` se déduit du TYPE du champ `_entries` (donc du dictionnaire réel qu'on
 *  décode, pas d'un nom qu'on suppose), sa taille et les offsets de `key`/`value` viennent
 *  du runtime, et le type de valeur se déduit à son tour du champ `value`. Un renommage
 *  inter-build ne rend plus des nombres faux : il rend une ERREUR NOMMÉE (mirror de la
 *  discipline posée par #279 dans `game/damage-prediction.ts`).
 *
 *  ⚠ Les offsets rendus par `il2cpp_field_get_offset` et la taille rendue par
 *  `il2cpp_class_instance_size` sont BOXÉS pour un ValueType : on retranche l'en-tête de
 *  `0x10` (même piège que `classes.tsv`, cf. la note de `reference_symbol_table_versioned`). */
export interface RepairEntry {
    targetId: number | null;
    /** `GetStat(target, Health)` — mot BAS du retour de `PredictRepair`. */
    targetHpBefore: number;
    /** `FillUpStatComponent$$MaxFillUp(HealthComponent(target), eff)` — mot HAUT. */
    hpFill: number;
}

const BOX_HEADER = 0x10;

/** Layout du `Dictionary<IEntity, RepairPredictionResult>`, résolu une fois par classe
 *  de dictionnaire rencontrée. `null` = un maillon n'a pas résolu -> on refuse de décoder
 *  plutôt que de deviner. */
interface RepairDictLayout {
    entriesOff: number; countOff: number;
    entryStride: number; keyOff: number; valOff: number;
    currentHealthOff: number; totalHealOff: number;
}
const repairLayoutCache: Record<string, RepairDictLayout | string> = {};

function resolveRepairDictLayout(cls: NativePointer): RepairDictLayout | string {
    const key = cls.toString();
    const hit = repairLayoutCache[key];
    if (hit !== undefined) return hit;
    const fail = (why: string): string => {
        repairLayoutCache[key] = why;
        return why;
    };

    const entriesOff = getFieldOffset(cls, "_entries");
    const countOff = getFieldOffset(cls, "_count");
    if (entriesOff < 0 || countOff < 0) {
        return fail("Dictionary : champs `_entries`/`_count` non résolus");
    }
    if (!class_instance_size) {
        return fail("`il2cpp_class_instance_size` indisponible — stride d'Entry non mesurable");
    }
    // `Entry` se déduit du TYPE du champ `_entries` (un `Entry[]`), donc du dictionnaire
    // RÉEL — jamais d'un nom de classe supposé.
    const entriesField = getFieldInfo(cls, "_entries");
    if (!entriesField) return fail("FieldInfo `_entries` non résolu");
    const entryArrType = field_get_type(entriesField) as NativePointer;
    if (entryArrType.isNull()) return fail("type de `_entries` non résolu");
    const entryClass = type_get_class_or_element_class(entryArrType) as NativePointer;
    if (entryClass.isNull()) return fail("classe élément de `_entries` (Entry) non résolue");

    const entryStride = (class_instance_size(entryClass) as number) - BOX_HEADER;
    const keyOff = getFieldOffset(entryClass, "key") - BOX_HEADER;
    const valOff = getFieldOffset(entryClass, "value") - BOX_HEADER;
    if (entryStride <= 0 || keyOff < 0 || valOff < 0) {
        return fail(`Entry : stride/key/value non résolus (stride=${entryStride}, `
            + `key=${keyOff}, value=${valOff})`);
    }

    const valueField = getFieldInfo(entryClass, "value");
    if (!valueField) return fail("FieldInfo `Entry.value` non résolu");
    const valueType = field_get_type(valueField) as NativePointer;
    if (valueType.isNull()) return fail("type de `Entry.value` non résolu");
    const valueClass = type_get_class_or_element_class(valueType) as NativePointer;
    if (valueClass.isNull()) return fail("classe de `Entry.value` non résolue");

    const currentHealthOff = getFieldOffset(valueClass, "CurrentHealth") - BOX_HEADER;
    const totalHealOff = getFieldOffset(valueClass, "TotalHeal") - BOX_HEADER;
    if (currentHealthOff < 0 || totalHealOff < 0) {
        // Renommage inter-build : on NOMME le champ manquant au lieu de publier des nombres.
        return fail(`${class_get_name(valueClass)} : champs `
            + `CurrentHealth/TotalHeal non résolus (${currentHealthOff}/${totalHealOff})`);
    }
    // Garde de bornes : les deux champs doivent tenir DANS la valeur de l'entrée. Sans elle,
    // un renommage qui ferait résoudre un homonyme d'une autre classe relirait des voisins —
    // exactement la faute que ce correctif supprime.
    const valueSize = entryStride - valOff;
    if (currentHealthOff + 4 > valueSize || totalHealOff + 4 > valueSize) {
        return fail(`${class_get_name(valueClass)} : champs HORS BORNES de la valeur `
            + `(valueSize=${valueSize}, ch=${currentHealthOff}, th=${totalHealOff})`);
    }

    const layout: RepairDictLayout = {
        entriesOff, countOff, entryStride, keyOff, valOff,
        currentHealthOff, totalHealOff,
    };
    repairLayoutCache[key] = layout;
    return layout;
}

export function decodeRepairDict(
    dict: NativePointer, idByPtr: Map<string, number>,
): { events: RepairEntry[]; count: number; retClass: string | null; error?: string } {
    if (dict.isNull()) return { events: [], count: 0, retClass: null };
    const retClass = classNameAt(dict);
    try {
        const cls = dict.readPointer();
        const layout = resolveRepairDictLayout(cls);
        if (typeof layout === "string") {
            return { events: [], count: -1, retClass, error: layout };
        }
        const entries = dict.add(layout.entriesOff).readPointer();
        const count = dict.add(layout.countOff).readS32();
        if (entries.isNull() || count <= 0 || count > 4096) {
            return { events: [], count: 0, retClass };
        }
        // Données d'un Il2CppArray dès +0x20 ; `hashCode == 0` = slot libéré
        // (même pattern que `normalize-bc/items-catalog.ts`).
        const ARR_DATA = 0x20;
        const out: RepairEntry[] = [];
        for (let i = 0; i < count; i++) {
            const e = entries.add(ARR_DATA + i * layout.entryStride);
            if (e.readS32() === 0) continue;
            const keyPtr = e.add(layout.keyOff).readPointer();
            if (keyPtr.isNull()) continue;
            const v = e.add(layout.valOff);
            out.push({
                targetId: idByPtr.get(keyPtr.toString()) ?? null,
                targetHpBefore: v.add(layout.currentHealthOff).readS32(),
                hpFill: v.add(layout.totalHealOff).readS32(),
            });
        }
        return { events: out, count: out.length, retClass };
    } catch (e) {
        return { events: [], count: -1, retClass,
            error: "lecture repair dict: " + (e as Error).message };
    }
}
