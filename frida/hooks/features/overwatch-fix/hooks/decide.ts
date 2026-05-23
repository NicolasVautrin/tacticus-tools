// Hook: UtilityDecider.Decide(...) — input filter on the aggregator entry.
//
// The AI calls Decide with a List<UtilityMovementCase> (or IEntity for the
// other overload) and gets back an IEnumerator ranked by score. Rather than
// fight the iterator's internal scoring (we couldn't reach it via
// <>2__current/<>5__2 writes — the aggregator sums utility yields and a
// REJECT in one yield is still summed away by positive contributions in
// other yields), we FILTER THE INPUT LIST in onEnter before Decide runs:
// remove every case whose destination tile is within range of a tracked
// overwatcher. Decide can't yield what isn't in its input → AI can't pick
// a suicide move.
//
// List<T> in IL2CPP: `_items: T[]` @ 0x10, `_size: int` @ 0x18.
// We compact the array in place (non-suicide cases moved to the front) and
// decrement _size. The full _items[] backing array stays — older slots may
// still hold pointers but Decide reads via _size and never sees them.

import {
    class_get_name, cstr,
} from "../../../il2cpp/helpers.js";
import { hexDistance } from "../../../ai-toolkit/hex.js";
import {
    LIST_ITEMS_BASE, LIST_ITEMS_PTR, UMC,
} from "../../../ai-toolkit/unit-action.js";
import { readTilePosition } from "../../../game/match-state.js";
import {
    decideMethods, utilityMovementCaseClass,
} from "../resolve.js";
import { fix } from "../state.js";

export function installDecideHooks(): void {
    for (const decide of decideMethods) {
        fix.listeners.push(Interceptor.attach(decide.ptr, {
            onEnter(args) {
                fix.diag.calcUtilityFires++;
                if (fix.overwatchers.size === 0) {
                    fix.diag.calcUtilitySkippedNoOverwatchers++;
                    return;
                }
                const listPtr = args[1];
                if (listPtr.isNull()) return;
                // Determine collection shape from its IL2CPP class name:
                //   "<X>[]"   = managed array — items inline at +0x20,
                //               length at +0x18; the listPtr ITSELF is the
                //               items base.
                //   "List`1"  = List<T>      — `_items: T[]` @ +0x10 wraps a
                //               managed array; `_size: int` @ +0x18.
                let listClsName = "?";
                try {
                    const klass = listPtr.readPointer();
                    listClsName = cstr(
                        class_get_name(klass) as NativePointer);
                } catch { /* keep ? */ }
                const isArray = listClsName.endsWith("[]");
                let items: NativePointer;
                let size: number;
                try {
                    if (isArray) {
                        items = listPtr;
                        size = listPtr.add(0x18).readS32();
                    } else {
                        items = listPtr.add(0x10).readPointer();
                        size = listPtr.add(0x18).readS32();
                    }
                } catch { return; }
                let elemClsName = "?";
                if (size > 0 && !items.isNull()) {
                    try {
                        const first = items.add(0x20).readPointer();
                        if (!first.isNull()) {
                            elemClsName = cstr(
                                class_get_name(first.readPointer()) as
                                NativePointer);
                        }
                    } catch { /* keep ? */ }
                }
                fix.decideListSizes.push({
                    size, listCls: listClsName, elemCls: elemClsName,
                    itemsNull: items.isNull(),
                });
                if (fix.decideListSizes.length > 50) {
                    fix.decideListSizes.shift();
                }
                if (items.isNull() || size <= 0 || size > 1000) return;
                // Check if any overwatcher has cachedPos — if all null, the
                // filter will be a no-op. Track to surface diagnostically.
                let haveCachedPos = false;
                for (const info of fix.overwatchers.values()) {
                    if (info.cachedPos) { haveCachedPos = true; break; }
                }
                if (!haveCachedPos) {
                    fix.diag.calcUtilitySkippedNoCachedPos++;
                }

                // Iterate cases. Compact in place: write index `dst` advances
                // only when we keep a case. Suicide cases are skipped (= not
                // copied forward), effectively removing them from the
                // visible portion of the list.
                let dst = 0;
                let removed = 0;
                for (let src = 0; src < size; src++) {
                    fix.diag.calcUtilityCasesScanned++;
                    let casePtr: NativePointer;
                    try {
                        casePtr = items.add(0x20 + src * 8).readPointer();
                    } catch { continue; }
                    if (casePtr.isNull()) continue;
                    fix.diag.calcUtilityCasesIdentified++;

                    // Only filter UtilityMovementCase elements (the other
                    // Decide overload takes IEntity — we leave those alone).
                    let isMoveCase = true;
                    try {
                        const klass = casePtr.readPointer();
                        if (utilityMovementCaseClass
                            && !klass.equals(utilityMovementCaseClass)) {
                            isMoveCase = false;
                        }
                    } catch { isMoveCase = false; }

                    let suicide = false;
                    if (isMoveCase) {
                        try {
                            const tileList = casePtr.add(UMC.movementPosition)
                                .readPointer();
                            if (!tileList.isNull()) {
                                const tItems = tileList.add(LIST_ITEMS_PTR)
                                    .readPointer();
                                if (!tItems.isNull()) {
                                    const destTile = tItems.add(
                                        LIST_ITEMS_BASE).readPointer();
                                    if (!destTile.isNull()) {
                                        const destPos =
                                            readTilePosition(destTile);
                                        if (destPos) {
                                            for (const info of fix.overwatchers
                                                .values()) {
                                                const pos = info.cachedPos;
                                                if (!pos) continue;
                                                const d = hexDistance(
                                                    destPos.col, destPos.row,
                                                    pos.col, pos.row);
                                                if (d <= info.range) {
                                                    suicide = true;
                                                    break;
                                                }
                                            }
                                        }
                                    }
                                }
                            }
                        } catch { /* keep suicide=false */ }
                    }

                    if (suicide) {
                        removed++;
                        continue;
                    }
                    if (dst !== src) {
                        try {
                            items.add(0x20 + dst * 8).writePointer(casePtr);
                        } catch { /* skip */ }
                    }
                    dst++;
                }

                if (removed > 0) {
                    try {
                        // Both List<T> (`_size`) and managed array
                        // (max_length) store their visible length at +0x18,
                        // so the same write shrinks the visible portion in
                        // either layout. Items beyond `dst` may still hold
                        // pointers in the backing buffer but Decide reads
                        // via length and never sees them.
                        listPtr.add(0x18).writeS32(dst);
                        fix.diag.calcUtilityRejected += removed;
                    } catch { /* */ }
                }
            },
        }));
    }
}
