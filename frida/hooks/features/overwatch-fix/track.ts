// Overwatcher tracking — registry of currently-Overwatching unit ptrs +
// helpers to resolve their tile position from the live matchstate, plus
// the BaseEffect.Apply hook that catches in-game Overwatch firings.
//
// Two complementary tracking paths feed `fix.overwatchers`:
//   1) Hook BaseEffect.Apply, filter to Overwatch_AutoAttackEffect — fires
//      when an enemy actually triggers an Overwatch shot. Late, but
//      authoritative.
//   2) Proactive scan (see scan.ts) — walks the matchstate after save load
//      to find any persistent OverwatchAutoAttackAbility instance armed
//      on a unit. Pre-arms the tracker so the very first AI move is gated.

import {
    EntityType, forEachComponent, forEachEntity, readTilePosition,
    unitFootComponentClass,
} from "../../game/match-state.js";
import { UF_TILE_ID, UF_UNIT_ID } from "../../ai-toolkit/unit-action.js";
import {
    baseEffectApplyMi, infiltrateUnitEffectClass, overwatchEffectClass,
} from "./resolve.js";
import { fix } from "./state.js";

/** Find the overwatcher's tile position by walking state entities for a
 * UnitFoot whose unitId matches the squad's id. Returns null if the squad
 * has no UnitFoot on the board (= dead/removed). */
export function resolveOverwatcherPos(
    state: NativePointer, ownerPtr: NativePointer,
): { col: number; row: number } | null {
    let ownerId: number;
    try { ownerId = ownerPtr.add(16).readS32(); }
    catch { return null; }

    // First pass: find the UnitFoot whose UnitFootComponent.unitId === ownerId
    // and read its tileId.
    let footTileId: number | null = null;
    forEachEntity(state, (e, _id, ty) => {
        if (footTileId !== null) return;
        if (ty !== EntityType.UnitFoot) return;
        forEachComponent(e, (comp, klass) => {
            if (footTileId !== null) return;
            if (!unitFootComponentClass) return;
            if (!klass.equals(unitFootComponentClass)) return;
            try {
                const uid = comp.add(UF_UNIT_ID).readS32();
                if (uid === ownerId) {
                    footTileId = comp.add(UF_TILE_ID).readS32();
                }
            } catch { /* skip */ }
        });
    });
    if (footTileId === null) return null;

    // Second pass: find the Tile entity with id === footTileId and read pos.
    let pos: { col: number; row: number } | null = null;
    forEachEntity(state, (e, id, ty) => {
        if (pos !== null) return;
        if (ty !== EntityType.Tile) return;
        if (id !== footTileId) return;
        pos = readTilePosition(e);
    });
    return pos;
}

/** Install the BaseEffect.Apply hook that catches dynamic Overwatch firings
 * AND Infiltrate effect applications. The same hook handles both — filtered
 * at runtime by the effect's class. No-op if the BaseEffect class/method
 * couldn't be resolved at module load. */
export function installTrackingHook(): void {
    if (!baseEffectApplyMi || baseEffectApplyMi.ptr.isNull()) return;
    fix.listeners.push(Interceptor.attach(baseEffectApplyMi.ptr, {
        onEnter(args) {
            fix.diag.applyHookFires++;
            const thisPtr = args[0];
            let klass: NativePointer;
            try { klass = thisPtr.readPointer(); }
            catch { return; }

            // Overwatch_AutoAttackEffect — track the OWNER (= unit doing
            // the overwatch). args[1] is the owner.
            if (overwatchEffectClass
                && klass.equals(overwatchEffectClass)) {
                const owner = args[1];
                if (owner.isNull()) return;
                const key = owner.toString();
                if (!fix.overwatchers.has(key)) {
                    fix.overwatchers.set(key, {
                        ownerPtr: key,
                        sinceTs: Date.now(),
                        cachedPos: null,
                        range: fix.threatRange,
                    });
                    fix.diag.overwatchersTracked++;
                }
                return;
            }

            // Infiltrate_UnitEffect — track the TARGET (= unit gaining the
            // Infiltrate trait). The signature for ApplyInternal in the
            // sources is `Apply(owner, target, effect)` and the wrapper's
            // Apply forwards through; on the BaseEffect.Apply slot the
            // first user arg is `owner` (args[1]) and the second is
            // `target` (args[2]). We track args[2].
            if (infiltrateUnitEffectClass
                && klass.equals(infiltrateUnitEffectClass)) {
                fix.diag.infiltrateApplyFires++;
                const target = args[2];
                if (target.isNull()) return;
                const key = target.toString();
                if (!fix.infiltratedUnits.has(key)) {
                    fix.infiltratedUnits.add(key);
                    fix.diag.infiltrateUnitsTracked++;
                }
            }
        },
    }));
}
