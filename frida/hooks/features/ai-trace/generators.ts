// L2 — Action generator inputs.
// Hooks MovementActionGenerator.GenerateActions and
// ActiveAbilityActionGenerator.GenerateActions onEnter — captures the
// raw inputs (unit, start tile, candidate position count, owned ability
// set for the active-ability generator) BEFORE per-tile/per-ability
// scoring kicks in.

import { findClass, findMethod, getFieldOffset } from "../../il2cpp/helpers.js";
import { abilityName } from "../../data/ability-names.js";
import {
    traceState, installStatus,
    emit, projectEntity, projectFirstTile,
} from "./state.js";

let aaagAbilityTypesOffset = -1;

/** Read up to N `int` entries from an OrderedSet<int>/List<int> at slotPtr.
 * The set's `_items: int[]` is at +0x10, `_size: int` at +0x18. Array
 * payload starts at +0x20 with 4 bytes per element. */
function readIntSet(slotPtr: NativePointer, max = 16): number[] {
    try {
        if (slotPtr.isNull()) return [];
        const items = slotPtr.add(0x10).readPointer();
        const size = slotPtr.add(0x18).readS32();
        if (items.isNull() || size <= 0 || size > 1000) return [];
        const out: number[] = [];
        const n = Math.min(size, max);
        for (let i = 0; i < n; i++) {
            out.push(items.add(0x20 + i * 4).readS32());
        }
        return out;
    } catch { return []; }
}

export function installL2(): void {
    for (const cls of [
        "MovementActionGenerator",
        "ActiveAbilityActionGenerator",
    ]) {
        const k = findClass(
            "BattleLogicAssembly.dll",
            "IdunBattle.AI.ActionGenerators", cls);
        if (!k) {
            installStatus["L2_" + cls] = "class not found";
            continue;
        }
        const m = findMethod(k, "GenerateActions");
        if (!m || m.ptr.isNull()) {
            installStatus["L2_" + cls] = "GenerateActions not found";
            continue;
        }
        // ActiveAbilityActionGenerator carries an _abilityTypes IOrderedSet
        // identifying which abilities this generator instance is responsible
        // for. Same generator class may be instantiated multiple times with
        // different ability sets per unit — without this discriminator, two
        // candidates events with same unit/startTile/count look identical.
        if (cls === "ActiveAbilityActionGenerator") {
            aaagAbilityTypesOffset = getFieldOffset(k, "_abilityTypes");
        }
        try {
            const generatorCls = cls;
            const isActiveAbility = cls === "ActiveAbilityActionGenerator";
            Interceptor.attach(m.ptr, {
                onEnter(args): void {
                    if (!traceState.enabled.L2) return;
                    const generator = args[0];
                    const unit = args[1];
                    const startTile = projectFirstTile(args[2], "casterTile");
                    let possibleCount = -1;
                    try {
                        const list = args[3];
                        if (!list.isNull()) {
                            possibleCount = list.add(0x18).readS32();
                        }
                    } catch { /* keep -1 */ }

                    let abilities: number[] | undefined = undefined;
                    if (isActiveAbility && aaagAbilityTypesOffset >= 0
                        && !generator.isNull()) {
                        try {
                            const setPtr = generator.add(
                                aaagAbilityTypesOffset).readPointer();
                            abilities = readIntSet(setPtr);
                        } catch { /* keep undefined */ }
                    }

                    emit({
                        evt: "candidates",
                        generator: generatorCls,
                        unit: projectEntity(unit, "unit"),
                        startTile: startTile.tile,
                        possibleCount,
                        abilities: abilities?.map((a) => abilityName(a)),
                    });
                },
            });
            installStatus["L2_" + cls] = "ok";
        } catch (e) {
            installStatus["L2_" + cls] = "attach_failed: "
                + (e as Error).message;
        }
    }
}
