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
 *      `<MakeDamagePredictions>d__N` (struct 0xd8, ctor @181135500) : target(BEntityId)@+0x00,
 *      AttackHitPrediction copiée @+0x08 (donc chaque champ DamagePredictionResult @X →
 *      event @+0x08+X : hp@+0x08, armor@+0x0c, shield@+0x10, willKill@+0x2c=struct+0x24,
 *      mightKill@+0x30=struct+0x28, healthDmg@+0x68/+0x6c=struct+0x60/+0x64, totalDmg@+0x98/
 *      +0x9c, mightCrit@+0xb9, appliedHits@+0xc4), probability(Fix64)@+0xc8, probMult@+0xd0.
 *  ⚠ Certains playbooks (heal/repair) rendent des Probable{Heal,Effect}Event : ce module
 *  ne décode que les DamageEvent (l'appelant passe une ability d'ATTAQUE). */
import {
    class_get_name, findMethodByNameSuffix, findMethodByParamClasses,
    findMethodByParamCount, getFieldOffset, s,
} from "../../il2cpp/helpers.js";
import { invokeMethod } from "../../il2cpp/invoke.js";
import { runnerOff } from "../../game/runner.js";
import { entityExtClass, servicesOff } from "./internals.js";

/** sizeof(ProbableDamageEvent) — RE ctor @181135500 (copie AttackHitPrediction 0xc0 o
 *  à +0x08, puis probability@+0xc8 + probMult@+0xd0). */
const EVENT_STRIDE = 0xd8;

export interface DamageEvent {
    targetId: number | null;
    hpBefore: number; armorBefore: number; shieldBefore: number;
    healthDmgMin: number; healthDmgMax: number;
    totalDmgMin: number; totalDmgMax: number;
    /** Seuils de mort EFFECTIFS (post floor-Resilient + overkill) : hp<=willKillDmg =
     *  mort garantie (get_WillBeKill@struct+0x24) ; hp<=mightKillDmg = possible (@+0x28). */
    willKillDmg: number; mightKillDmg: number;
    mightCrit: number; appliedHits: number;
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

/** Invoque `MakeDamagePredictions(caster, UnitPosition, target[, AbilityState{level,mult,0}])`
 *  sur le playbook (override résolu sur la classe CONCRÈTE). Arité 4 (avec AbilityState)
 *  d'abord — signature du slot +0x358 — 3 en secours. Retourne {list, retClass, makeArity}
 *  (list null si non résolu / throw). */
export function makeDamagePredictions(
    playbook: NativePointer, unit: NativePointer, posPtr: NativePointer,
    target: NativePointer, level: number, mult: number,
): { list: NativePointer; retClass: string | null; makeArity: number } {
    const stateBuf = Memory.alloc(12);
    stateBuf.writeS32(level | 0);
    stateBuf.add(4).writeS32((mult ?? 100) | 0);
    stateBuf.add(8).writeS32(0);
    const pbCls = playbook.readPointer();
    let makeMi = findMethodByParamCount(pbCls, "MakeDamagePredictions", 4);
    let makeArgs: NativePointer[] = [unit, posPtr, target, stateBuf];
    if (!makeMi) {
        makeMi = findMethodByParamCount(pbCls, "MakeDamagePredictions", 3);
        makeArgs = [unit, posPtr, target];
    }
    if (!makeMi) return { list: ptr(0), retClass: null, makeArity: 0 };
    try {
        const list = invokeMethod(makeMi.info, playbook, makeArgs);
        return { list, retClass: list.isNull() ? null : classNameAt(list),
            makeArity: makeArgs.length };
    } catch { return { list: ptr(0), retClass: null, makeArity: makeArgs.length }; }
}

/** Lit UN ProbableDamageEvent (struct 0xd8) à l'adresse `ev`. La référence IEntity
 *  cible est un pointeur 8 o @+0x00 (un readS32 y lit du garbage) → résolue en unitId
 *  via `idByPtr`. AttackHitPrediction copiée dès +0x08 (RE ctor @181135500). */
export function readDamageEvent(
    ev: NativePointer, idByPtr: Map<string, number>,
): DamageEvent {
    const fx = (off: number): number =>
        ev.add(off).readS64().toNumber() / 4294967296;   // Fix64 Q32.32
    return {
        targetId: idByPtr.get(ev.readPointer().toString()) ?? null,
        hpBefore: ev.add(0x08).readS32(),
        armorBefore: ev.add(0x0c).readS32(),
        shieldBefore: ev.add(0x10).readS32(),
        willKillDmg: ev.add(0x2c).readS32(),
        mightKillDmg: ev.add(0x30).readS32(),
        healthDmgMin: ev.add(0x68).readS32(),
        healthDmgMax: ev.add(0x6c).readS32(),
        totalDmgMin: ev.add(0x98).readS32(),
        totalDmgMax: ev.add(0x9c).readS32(),
        mightCrit: ev.add(0xb9).readU8(),
        appliedHits: ev.add(0xc4).readS32(),
        probability: fx(0xc8), probMult: fx(0xd0),
    };
}

/** Décode le retour de MakeDamagePredictions en events. Gère les 3 formes :
 *  `List`1` (items@+0x10/count@+0x18, structs INLINE dès +0x20), array managé
 *  `ProbableDamageEvent[]` (max_length@+0x18, éléments dès +0x20), et yield-machine
 *  `<MakeDamagePredictions>d__N` (IEnumerable ET IEnumerator : `<>1__state`=0 puis
 *  MoveNext + lecture du struct INLINE `<>2__current`). */
export function decodeDamageEvents(
    list: NativePointer, idByPtr: Map<string, number>,
): { events: DamageEvent[]; count: number; retClass: string | null; error?: string } {
    const events: DamageEvent[] = [];
    if (list.isNull()) return { events, count: -1, retClass: null };
    const retClass = classNameAt(list);
    try {
        if (retClass === "List`1") {
            const items = list.add(0x10).readPointer();
            const count = list.add(0x18).readS32();
            if (!items.isNull() && count > 0 && count < 64) {
                for (let i = 0; i < count; i++) {
                    events.push(readDamageEvent(items.add(0x20 + i * EVENT_STRIDE), idByPtr));
                }
            }
            return { events, count, retClass };
        }
        if (retClass !== null && retClass.endsWith("[]")) {
            const count = list.add(0x18).readS32();
            if (count > 0 && count < 64) {
                for (let i = 0; i < count; i++) {
                    events.push(readDamageEvent(list.add(0x20 + i * EVENT_STRIDE), idByPtr));
                }
            }
            return { events, count, retClass };
        }
        // Retour YIELD : machine d'état `<MakeDamagePredictions>d__N` (IEnumerable
        // ET IEnumerator de ProbableDamageEvent). On CALL le GetEnumerator NATIF au
        // lieu de forcer `<>1__state`=0 à la main : GetEnumerator (state -2 → 0)
        // COPIE aussi les paramètres capturés `<>3__caster/target/pos/state` vers les
        // champs de TRAVAIL que MoveNext lit (RE @18117d570 : bloc LAB `this+0x118 =
        // this+0x120` …). Sans cette copie, MoveNext déréférence des champs nuls →
        // il2cpp "system error". GetEnumerator est une impl EXPLICITE d'interface
        // (nom qualifié `…IEnumerable<ProbableDamageEvent>.GetEnumerator`) → résolue
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
            events.push(readDamageEvent(en.add(curOff), idByPtr));
            count++;
        }
        return { events, count, retClass };
    } catch (e) {
        return { events, count: -1, retClass, error: "lecture events: " + (e as Error).message };
    }
}
