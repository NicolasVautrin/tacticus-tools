// Hook: UtilityDecider.CalculateUtility — synchronous Fix64 return.
//
// Kept for backward compat. Not invoked by the live AI in this match
// (0 fires observed against uu2fr8mv6c) but listed in IUtilityDecider so
// callers MAY use it directly in some paths. Returns REJECT when the
// case is a UtilityMovementCase whose destination is in OW range.

import { hexDistance } from "../../../ai-toolkit/hex.js";
import {
    LIST_ITEMS_BASE, LIST_ITEMS_PTR, UMC,
} from "../../../ai-toolkit/unit-action.js";
import { readTilePosition } from "../../../game/match-state.js";
import {
    calculateUtilityMi, utilityMovementCaseClass,
} from "../resolve.js";
import { fix, utilityConsts } from "../state.js";

export function installCalcUtilityHook(): void {
    if (!calculateUtilityMi || calculateUtilityMi.ptr.isNull()) return;
    fix.listeners.push(Interceptor.attach(calculateUtilityMi.ptr, {
        onEnter(args) {
            // CalculateUtility<TCase>(TCase case, UtilityBucket bucket,
            //                         Func<...> utilCalc)
            // Instance method: args[0]=this, args[1]=case.
            (this as { _case?: NativePointer })._case = args[1];
        },
        onLeave(retval) {
            fix.diag.calcUtilityFires++;
            const casePtr = (this as { _case?: NativePointer })._case;
            if (!casePtr || casePtr.isNull()) return;

            let caseKlass: NativePointer;
            try { caseKlass = casePtr.readPointer(); }
            catch { return; }
            if (utilityMovementCaseClass
                && !caseKlass.equals(utilityMovementCaseClass)) {
                fix.diag.calcUtilitySkippedNotMoveCase++;
                return;
            }
            if (fix.overwatchers.size === 0) {
                fix.diag.calcUtilitySkippedNoOverwatchers++;
                return;
            }

            let destPos: { col: number; row: number } | null;
            try {
                const tileList = casePtr.add(UMC.movementPosition)
                    .readPointer();
                if (tileList.isNull()) {
                    fix.diag.calcUtilityReadFailed++; return;
                }
                const items = tileList.add(LIST_ITEMS_PTR).readPointer();
                if (items.isNull()) {
                    fix.diag.calcUtilityReadFailed++; return;
                }
                const destTile = items.add(LIST_ITEMS_BASE).readPointer();
                if (destTile.isNull()) {
                    fix.diag.calcUtilityReadFailed++; return;
                }
                destPos = readTilePosition(destTile);
            } catch {
                fix.diag.calcUtilityReadFailed++; return;
            }
            if (!destPos) {
                fix.diag.calcUtilityReadFailed++; return;
            }

            let inRange = false;
            for (const info of fix.overwatchers.values()) {
                const pos = info.cachedPos;
                if (!pos) continue;
                const d = hexDistance(
                    destPos.col, destPos.row, pos.col, pos.row);
                if (d <= info.range) { inRange = true; break; }
            }
            if (!inRange) {
                fix.diag.calcUtilitySkippedNotInRange++;
                return;
            }

            // OVERRIDE the return value with REJECT. Fix64 is an 8-byte
            // struct returned in a register on x64; Frida's retval.replace
            // takes a NativePointer with the raw 64-bit pattern.
            try {
                const rejectVal = utilityConsts.REJECT ?? fix.penalty;
                const buf = Memory.alloc(8);
                buf.writeS64(rejectVal);
                retval.replace(buf.readPointer());
                fix.diag.calcUtilityRejected++;
            } catch { /* ignore */ }
        },
    }));
}
