// Proactive scan: walk a matchstate and find every Overwatch_AutoAttackEffect
// or armed OverwatchAutoAttackAbility instance.
//
// The dynamic `BaseEffect.Apply` hook only fires when the overwatch
// auto-attack physically TRIGGERS (i.e., an enemy enters range and gets
// shot). It does NOT fire when the effect is registered (= when Re'vas
// activates her overwatch ability). So at save-load time, the effect is
// present in the matchstate but the dynamic tracker has never been
// notified. This scan walks the full entity list and registers every
// owner pre-emptively into `fix.overwatchers`.

import {
    forEachComponent, forEachEntity,
} from "../../game/match-state.js";
import { state as agentState } from "../../game/state.js";
import { runnerOff } from "../../game/runner.js";
import { getRunner } from "../../game/runner-registry.js";
import { log } from "../../runtime/diag.js";
import {
    infiltrateUnitEffectClass, overwatchAbilityClasses,
    overwatchEffectClass,
} from "./resolve.js";
import { fix } from "./state.js";
import { resolveOverwatcherPos } from "./track.js";

export interface ScanHit {
    foundOnEntityId: number;
    foundOnEntityType: number;
    /** "entity-class" if the entity itself IS the effect (klass match),
     *  "component" if the effect lives as a component on a unit. */
    location: "entity-class" | "component";
    /** Pointer of the effect object — passed to gcRoot tracking key. */
    effectPtr: string;
    /** Resolved owner ptr — for component case: the entity holding the
     *  component. For entity-class case: needs further work to find owner. */
    ownerEntityId: number | null;
    ownerPtr: string | null;
    ownerPos: { col: number; row: number } | null;
}

/** Scan a matchstate for Overwatch ability/effect instances. We check both:
 *   - Overwatch_AutoAttackEffect (the trigger payload — present only after
 *     the effect has actually fired, so unlikely to find at pre-arm)
 *   - OverwatchAutoAttackAbility / PurgeResponse_ActiveOverwatchAbility
 *     (the persistent ARMED state on the unit — what we actually need
 *     to detect at save load)
 *
 * Sightings can be in two locations: as the entity's own klass (= the
 * entity itself IS the ability/effect), or as a component on a unit.
 * Returns one hit per sighting. */
export function scanStateForOverwatchers(stateP: NativePointer): ScanHit[] {
    const hits: ScanHit[] = [];
    const targets: NativePointer[] = [...overwatchAbilityClasses];
    if (overwatchEffectClass) targets.push(overwatchEffectClass);
    if (targets.length === 0) return hits;

    forEachEntity(stateP, (e, id, ty) => {
        // Hypothesis A: the entity itself is an overwatch ability/effect
        // (its klass matches one of our targets).
        try {
            const klass = e.readPointer();
            if (!klass.isNull()) {
                for (const t of targets) {
                    if (klass.equals(t)) {
                        hits.push({
                            foundOnEntityId: id,
                            foundOnEntityType: ty,
                            location: "entity-class",
                            effectPtr: e.toString(),
                            ownerEntityId: null,
                            ownerPtr: null,
                            ownerPos: null,
                        });
                        break;
                    }
                }
            }
        } catch { /* skip */ }

        // Hypothesis B: the ability/effect is a component on a unit (or any
        // other entity). Walk components and check klass against every
        // target class.
        try {
            forEachComponent(e, (comp, klass) => {
                for (const t of targets) {
                    if (klass.equals(t)) {
                        hits.push({
                            foundOnEntityId: id,
                            foundOnEntityType: ty,
                            location: "component",
                            effectPtr: comp.toString(),
                            ownerEntityId: id,
                            ownerPtr: e.toString(),
                            ownerPos: null,
                        });
                        break;
                    }
                }
            });
        } catch { /* skip */ }
    });

    // Resolve ownerPos for component-located effects (their owner is the
    // hosting entity, which for Unit entities has no PositionComponent —
    // position lives on the UnitFoot). Reuse `resolveOverwatcherPos`.
    for (const hit of hits) {
        if (!hit.ownerPtr) continue;
        try {
            hit.ownerPos = resolveOverwatcherPos(
                stateP, ptr(hit.ownerPtr));
        } catch { /* leave null */ }
    }
    return hits;
}

/** Pick the matchstate of a runner — live (`scope === "live"`) or build by
 * runnerId. Returns null if not available. */
export function pickRunnerState(
    scope: "live" | number,
): NativePointer | null {
    if (scope === "live") {
        const lr = agentState.liveRunner;
        if (!lr) return null;
        const st = lr.add(runnerOff.state).readPointer();
        return st.isNull() ? null : st;
    }
    try {
        const e = getRunner(scope);
        const st = e.runner.add(runnerOff.state).readPointer();
        return st.isNull() ? null : st;
    } catch { return null; }
}

/** Walk a matchstate and register every unit currently carrying an
 * `Infiltrate_UnitEffect` component into `fix.infiltratedUnits`. Mirror of
 * scanStateForOverwatchers but for the Infiltrate trait — needed because
 * `BaseEffect.Apply` only fires when the trait is freshly applied; on save
 * load the unit is already-infiltrated and Apply doesn't re-run. Returns
 * the count of units found. */
export function scanStateForInfiltrated(stateP: NativePointer): number {
    if (!infiltrateUnitEffectClass) return 0;
    const target = infiltrateUnitEffectClass;
    let added = 0;
    forEachEntity(stateP, (e, _id, _ty) => {
        try {
            forEachComponent(e, (_comp, klass) => {
                if (!klass.equals(target)) return;
                const key = e.toString();
                if (!fix.infiltratedUnits.has(key)) {
                    fix.infiltratedUnits.add(key);
                    fix.diag.infiltrateUnitsTracked++;
                    added++;
                }
            });
        } catch { /* skip */ }
    });
    return added;
}

/** Run the scan + register every found owner into the overwatcher tracker.
 * Called proactively after save load and at end-turn so the tracker is
 * armed BEFORE the AI's first move evaluation. Returns diag info. */
export function autoArm(scope: "live" | number): {
    ok: boolean; reason?: string;
    hits: number; addedOverwatchers: number;
    addedInfiltrated: number;
    sample: ScanHit[];
} {
    const stateP = pickRunnerState(scope);
    if (!stateP) {
        return { ok: false, reason: "no matchstate", hits: 0,
            addedOverwatchers: 0, addedInfiltrated: 0, sample: [] };
    }
    const hits = scanStateForOverwatchers(stateP);
    let added = 0;
    for (const h of hits) {
        if (!h.ownerPtr) continue;
        if (fix.overwatchers.has(h.ownerPtr)) continue;
        fix.overwatchers.set(h.ownerPtr, {
            ownerPtr: h.ownerPtr,
            sinceTs: Date.now(),
            cachedPos: h.ownerPos,
            range: fix.threatRange,
        });
        fix.diag.overwatchersTracked++;
        added++;
    }
    const addedInfiltrated = scanStateForInfiltrated(stateP);
    if (added > 0 || addedInfiltrated > 0) {
        log(`[overwatch-fix] auto-armed ${added} overwatcher(s) + `
            + `${addedInfiltrated} infiltrated unit(s) from matchstate `
            + `scan (${hits.length} OW hits)`);
    }
    return {
        ok: true, hits: hits.length, addedOverwatchers: added,
        addedInfiltrated,
        sample: hits.slice(0, 10),
    };
}
