// Hook: Bucket<T>.AddAction / AddActionToBucket — gshared bodies.
//
// Each Playbook builds its `Bucket<UnitAction>` of candidate actions and
// registers them via these methods. By patching the `BucketAction.Utility`
// field (offset 0x18) BEFORE the bucket stores it, we make any in-range
// action appear with REJECT score → bucket selects it as Highest only when
// every alternative is also REJECT. This catches paths that bypass
// UtilityDecider.Decide and BasePlaybook.GenerateAction (notably
// ability-driven moves like SporeMine kamikaze, charge-into-enemy,
// summon spawn, etc.).
//
// Note: in the uu2fr8mv6c run this hook fires 0 times — Bucket<T> methods
// resolved via findClassAnywhere are returned but the AI's hot path may
// inline or call instantiation-specific bodies that the gshared resolution
// doesn't reach. Kept for completeness; the consumer-yield hook is the
// real diag entry point right now.

import { hexDistance } from "../../../ai-toolkit/hex.js";
import {
    BA_CONTENT, BA_UTILITY, LIST_ITEMS_BASE, LIST_ITEMS_PTR, UA_POSITION,
} from "../../../ai-toolkit/unit-action.js";
import { readTilePosition } from "../../../game/match-state.js";
import { log } from "../../../runtime/diag.js";
import {
    bucketAddActionPtr, bucketAddActionToBucketPtr,
} from "../resolve.js";
import { fix, utilityConsts } from "../state.js";

function makeAddActionHook() {
    return {
        onEnter(args: InvocationArguments) {
            fix.diag.bucketAddActionFires++;
            if (fix.overwatchers.size === 0) {
                fix.diag.bucketSkippedNoOverwatchers++;
                return;
            }
            // First arg is `this` (Bucket<T>). Second arg is the
            // BucketAction<T>. For AddActionToBucket the args are
            // (this, weight, bucketAction) — bucketAction is args[2].
            // We try args[1] then args[2] to be tolerant.
            let bucketAction: NativePointer = args[1];
            let content: NativePointer;
            try {
                content = bucketAction.add(BA_CONTENT).readPointer();
            } catch { return; }
            if (content.isNull()) {
                bucketAction = args[2];
                try {
                    content = bucketAction.add(BA_CONTENT).readPointer();
                } catch { return; }
                if (content.isNull()) return;
            }

            // Read dest tile from UnitAction.Position.Tiles[0].
            let destPos: { col: number; row: number } | null;
            try {
                const tileList = content.add(UA_POSITION).readPointer();
                if (tileList.isNull()) return;
                const items = tileList.add(LIST_ITEMS_PTR).readPointer();
                if (items.isNull()) return;
                const destTile = items.add(LIST_ITEMS_BASE).readPointer();
                if (destTile.isNull()) return;
                destPos = readTilePosition(destTile);
            } catch { return; }
            if (!destPos) return;

            // Check against tracked overwatchers.
            let inRange = false;
            for (const info of fix.overwatchers.values()) {
                const pos = info.cachedPos;
                if (!pos) continue;
                const d = hexDistance(
                    destPos.col, destPos.row, pos.col, pos.row);
                if (d <= info.range) { inRange = true; break; }
            }
            if (!inRange) {
                fix.diag.bucketSkippedNotInRange++;
                return;
            }

            // Patch BucketAction.Utility @ 0x18 with REJECT.
            try {
                const rejectVal = utilityConsts.REJECT ?? fix.penalty;
                bucketAction.add(BA_UTILITY).writeS64(rejectVal);
                fix.diag.bucketActionsPatched++;
            } catch {
                fix.diag.bucketWriteFailed++;
            }
        },
    };
}

export function installBucketHooks(): void {
    if (bucketAddActionPtr && !bucketAddActionPtr.isNull()) {
        try {
            fix.listeners.push(Interceptor.attach(
                bucketAddActionPtr, makeAddActionHook()));
        } catch (e) {
            log("[overwatch-fix] failed to hook Bucket.AddAction: "
                + (e as Error).message);
        }
    }
    if (bucketAddActionToBucketPtr && !bucketAddActionToBucketPtr.isNull()) {
        try {
            fix.listeners.push(Interceptor.attach(
                bucketAddActionToBucketPtr, makeAddActionHook()));
        } catch (e) {
            log("[overwatch-fix] failed to hook Bucket.AddActionToBucket: "
                + (e as Error).message);
        }
    }
}
