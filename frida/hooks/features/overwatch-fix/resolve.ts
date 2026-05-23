// IL2CPP class + method refs resolved once at module load.
//
// Centralised here so every hook module imports a typed `OverwatchClasses`
// bundle instead of re-resolving classes themselves. Resolution is purely
// runtime via `findClassAnywhere` + `findMethod` — no RVA hardcoding (see
// CLAUDE.md "Hash du build = identité du dump"). The bundle is null-tolerant:
// individual hooks must check that the methods they need are non-null before
// installing.

import {
    class_get_methods, cstr,
    findClassAnywhere, findMethod, methodEntry,
    method_get_name,
} from "../../il2cpp/helpers.js";
import { findIteratorStateMachine } from "../../ai-toolkit/coroutine.js";

// Overwatch effect itself — fires when an enemy enters an Overwatcher's
// range. We hook `BaseEffect.Apply` and filter at runtime to track which
// units are actively Overwatching.
export const overwatchEffectClass = findClassAnywhere(
    "IdunBattle.Entities.Effects.Loki", "Overwatch_AutoAttackEffect");

// Infiltrate_UnitEffect — applied to units with the Infiltrate trait, makes
// them invisible to Overwatch triggers (= they enter an OW zone without
// being shot). When this effect's `Apply(owner, target, effect)` fires we
// remember the `target` unit ptr so the should-execute hook can skip
// veto for those units. Also resolves their persistent state via
// scanStateForInfiltrated so units with Infiltrate at save-load time
// are pre-registered.
export const infiltrateUnitEffectClass = findClassAnywhere(
    "IdunBattle.Entities.Effects.Loki", "Infiltrate_UnitEffect");

export const baseEffectClass = findClassAnywhere(
    "IdunBattle.Entities.Effects", "BaseEffect");
export const baseEffectApplyMi = baseEffectClass
    ? findMethod(baseEffectClass, "Apply") : null;

// Active ability classes that "arm" an overwatch state on a unit. These are
// the persistent representations we look for in the matchstate post-replay
// (since `Overwatch_AutoAttackEffect.Apply` only fires when the overwatch
// actually triggers — too late for pre-arm). When Re'vas activates her
// overwatch ability, she gets one of these armed; another enemy entering
// range causes the corresponding effect to fire.
export const overwatchAbilityClasses: NativePointer[] = (() => {
    const candidates = [
        { ns: "IdunBattleLogic.Entities.Abilities.Active.Loki",
          cls: "OverwatchAutoAttackAbility" },
        { ns: "IdunBattleLogic.Entities.Abilities.Triggered.Loki",
          cls: "PurgeResponse_ActiveOverwatchAbility" },
    ];
    const out: NativePointer[] = [];
    for (const c of candidates) {
        const k = findClassAnywhere(c.ns, c.cls);
        if (k && !k.isNull()) out.push(k);
    }
    return out;
})();

export const triggeredAbilitiesNonOwnerUtilityClass = findClassAnywhere(
    "IdunBattle.AI.Utilities", "TriggeredAbilitiesNonOwnerUtility");

// `UtilityDecider.CalculateUtility<TCase>` — the AI's score AGGREGATOR.
// Iterates every utility in a UtilityBucket, sums their per-yield Fix64
// contributions for the given `case` (TCase = UtilityMovementCase for
// movement candidates, TCase = IEntity for attack targets), and returns
// the consolidated score the ranker uses to pick the best candidate.
export const utilityDeciderClass = findClassAnywhere(
    "IdunBattleLogic.AI.Utilities", "UtilityDecider");
export const calculateUtilityMi = utilityDeciderClass
    ? findMethod(utilityDeciderClass, "CalculateUtility") : null;

export const utilityMovementCaseClass = findClassAnywhere(
    "IdunBattle.AI.Utilities", "UtilityMovementCase");

/** Resolve the `Decide(...)` overloads — there are 2 (UtilityMovementCase
 * and IEntity element types) with the same arity. We collect both and let
 * each hook filter at runtime by element-type class. */
export function findDecideMethods(): Array<{
    info: NativePointer; ptr: NativePointer;
}> {
    const out: Array<{ info: NativePointer; ptr: NativePointer }> = [];
    if (!utilityDeciderClass) return out;
    const it = Memory.alloc(Process.pointerSize);
    it.writePointer(ptr(0));
    let m: NativePointer;
    while (true) {
        m = class_get_methods(utilityDeciderClass, it) as NativePointer;
        if (m.isNull()) break;
        const name = cstr(method_get_name(m) as NativePointer);
        if (name === "Decide") {
            const p = methodEntry(m);
            if (!p.isNull()) out.push({ info: m, ptr: p });
        }
    }
    return out;
}
export const decideMethods = findDecideMethods();

// Bucket<T>.AddAction / AddActionToBucket — gshared bodies. Resolved live;
// no RVA fallback (see CLAUDE.md "Règle de code: résolution runtime, pas
// de RVA hardcodées").
const bucketClass = findClassAnywhere(
    "IdunBattle.AI.BucketSystem", "Bucket`1");

function findBucketMethod(name: string): NativePointer | null {
    if (!bucketClass) return null;
    const it = Memory.alloc(Process.pointerSize);
    it.writePointer(ptr(0));
    let m: NativePointer;
    while (true) {
        m = class_get_methods(bucketClass, it) as NativePointer;
        if (m.isNull()) break;
        if (cstr(method_get_name(m) as NativePointer) === name) {
            return methodEntry(m);
        }
    }
    return null;
}
export const bucketAddActionPtr = findBucketMethod("AddAction");
export const bucketAddActionToBucketPtr = findBucketMethod("AddActionToBucket");

// State machine for the iterator we hook in `hooks/move-next.ts`.
export const moveStateMachineClass = triggeredAbilitiesNonOwnerUtilityClass
    ? findIteratorStateMachine(
        triggeredAbilitiesNonOwnerUtilityClass, "EvaluateMovementInSteps")
    : null;
export const moveNextMi = moveStateMachineClass
    ? findMethod(moveStateMachineClass, "MoveNext") : null;

/** Human-readable summary of which classes/methods got resolved. Surfaced
 * via the status RPC so the operator sees what's missing. */
export function reportResolution(): string {
    const checks: Array<[string, boolean]> = [
        ["Overwatch_AutoAttackEffect class", !!overwatchEffectClass],
        ["BaseEffect class", !!baseEffectClass],
        ["BaseEffect.Apply method",
            !!(baseEffectApplyMi && !baseEffectApplyMi.ptr.isNull())],
        ["TriggeredAbilitiesNonOwnerUtility class",
            !!triggeredAbilitiesNonOwnerUtilityClass],
        ["MoveNext state machine class", !!moveStateMachineClass],
        ["MoveNext method",
            !!(moveNextMi && !moveNextMi.ptr.isNull())],
        ["UtilityDecider class", !!utilityDeciderClass],
        ["CalculateUtility method",
            !!(calculateUtilityMi && !calculateUtilityMi.ptr.isNull())],
        ["UtilityMovementCase class", !!utilityMovementCaseClass],
    ];
    return checks.map(([n, ok]) => (ok ? "+" : "-") + " " + n).join(" · ");
}

/** Quick gate — returns true iff every essential class/method is resolved
 * (excludes the optional Bucket / Decide stuff which is best-effort). */
export function classesReady(): boolean {
    return !!(overwatchEffectClass && baseEffectClass && baseEffectApplyMi
        && triggeredAbilitiesNonOwnerUtilityClass && moveStateMachineClass
        && moveNextMi);
}

/** State-machine field offsets specific to TriggeredAbilitiesNonOwnerUtility
 * .EvaluateMovementInSteps (the iterator we hook for movement scoring).
 * Generic `<>1__state` and `<>2__current` live in ai-toolkit/coroutine.ts;
 * the rest are closure-captured locals specific to this iterator. */
export const SM = {
    state: 0x10,        // <>1__state (int) — same as SM_STATE
    current: 0x18,      // <>2__current (Fix64 = int64) — same as SM_CURRENT
    moveCase: 0x20,     // moveCase (UtilityMovementCase*)
    thisRef: 0x28,      // <>4__this (TriggeredAbilitiesNonOwnerUtility*)
    evaluation: 0x30,   // <evaluation>5__2 (Fix64 accumulator)
};
