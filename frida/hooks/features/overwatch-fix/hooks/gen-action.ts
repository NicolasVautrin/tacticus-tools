// Hook: BasePlaybook.GenerateAction (3 overloads).
//
// Every Playbook emits its scored UnitActions through one of three
// overloads of GenerateAction, all returning a `BucketAction<UnitAction>`
// with layout:
//   Content @ 0x10 = UnitAction*
//   Utility @ 0x18 = Fix64
//
// onEnter: read the destination tile from args[1] (UnitPosition, IEntity,
// or IList<IEntity> depending on overload — we currently parse only the
// IList/UnitPosition shape; the IEntity shape returns "no_dest"). If the
// tile is in OW range, replace args[3] (the input utility Fix64) with
// REJECT.
//
// onLeave: re-read the returned BucketAction.Utility and verify our REJECT
// survived round-trip. Diagnostic only — we already proved survives at
// 16/16 in the uu2fr8mv6c run; the consumer ignores Utility and that's
// being investigated by the consumer-yield hook + the upcoming
// should-execute hook on Loki_NormalAttackPlaybook.

import {
    class_get_methods, cstr, findClassAnywhere, methodEntry,
    method_get_name,
} from "../../../il2cpp/helpers.js";
import { hexDistance } from "../../../ai-toolkit/hex.js";
import { captureStack } from "../../../ai-toolkit/stack-capture.js";
import {
    BA_UTILITY, LIST_ITEMS_BASE, LIST_ITEMS_PTR,
} from "../../../ai-toolkit/unit-action.js";
import { readTilePosition } from "../../../game/match-state.js";
import { log } from "../../../runtime/diag.js";
import { fix, utilityConsts } from "../state.js";

/** Cap on total stacks captured (across all categories). After this, the
 * recordStack helper becomes a no-op for new entries (counters still tick).
 * Prevents unbounded growth of the diag JSON. */
const GEN_ACTION_STACKS_MAX = 30;

/** Push a backtrace into `fix.genActionStacks` for the given category, with
 * dedup by (category, topRva). Always increments the per-category counter,
 * even when the stack is suppressed for dedup or cap. */
function recordGenActionStack(
    ctx: CpuContext,
    category: "patched" | "out_of_range" | "no_dest",
    destPos: { col: number; row: number } | null,
): void {
    fix.genActionCategoryCounts[category] =
        (fix.genActionCategoryCounts[category] ?? 0) + 1;
    if (fix.genActionStacks.length >= GEN_ACTION_STACKS_MAX) return;
    const { topRva, frames } = captureStack(ctx);
    for (const s of fix.genActionStacks) {
        if (s.category === category && s.topRva === topRva) return;
    }
    const annotated = destPos !== null
        ? [...frames, "dest=(" + destPos.col + "," + destPos.row + ")"]
        : frames;
    fix.genActionStacks.push({
        category, topRva, frames: annotated, ts: Date.now(),
    });
}

export function installGenActionHooks(): void {
    const basePlaybookClass = findClassAnywhere(
        "IdunBattle.AI.Playbook", "BasePlaybook");
    if (!basePlaybookClass) return;
    const it = Memory.alloc(Process.pointerSize);
    it.writePointer(ptr(0));
    let m: NativePointer;
    while (true) {
        m = class_get_methods(basePlaybookClass, it) as NativePointer;
        if (m.isNull()) break;
        const name = cstr(method_get_name(m) as NativePointer);
        if (name !== "GenerateAction") continue;
        const mptr = methodEntry(m);
        if (mptr.isNull()) continue;
        try {
            fix.listeners.push(Interceptor.attach(mptr, {
                onEnter(args) {
                    fix.diag.genActionFires++;
                    // Track whether this call was patched, for onLeave to
                    // verify the score round-trips into the BucketAction.
                    (this as unknown as Record<string, boolean>)
                        .__owFixPatched = false;
                    if (fix.overwatchers.size === 0) return;
                    // GenerateAction signature:
                    //   args[0] = this (BasePlaybook)
                    //   args[1] = UnitPosition position (struct passed by
                    //     value; its single field `Tiles: IList<IEntity>`
                    //     at offset 0 means args[1] IS the Tiles list
                    //     pointer directly), OR IEntity tile, OR
                    //     IList<IEntity> unitFeetTiles
                    //   args[2] = target IEntity
                    //   args[3] = utility Fix64 (raw int64)
                    let destPos: { col: number; row: number } | null;
                    try {
                        const list = args[1];
                        if (list.isNull()) {
                            recordGenActionStack(
                                this.context, "no_dest", null);
                            return;
                        }
                        const items = list.add(LIST_ITEMS_PTR).readPointer();
                        if (items.isNull()) {
                            recordGenActionStack(
                                this.context, "no_dest", null);
                            return;
                        }
                        const destTile =
                            items.add(LIST_ITEMS_BASE).readPointer();
                        if (destTile.isNull()) {
                            recordGenActionStack(
                                this.context, "no_dest", null);
                            return;
                        }
                        destPos = readTilePosition(destTile);
                    } catch {
                        recordGenActionStack(
                            this.context, "no_dest", null);
                        return;
                    }
                    if (!destPos) {
                        recordGenActionStack(
                            this.context, "no_dest", null);
                        return;
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
                        fix.diag.genActionSkippedNotInRange++;
                        recordGenActionStack(
                            this.context, "out_of_range", destPos);
                        return;
                    }

                    // Replace args[3] (the input utility) with REJECT.
                    // x86-64 ABI: args 0-3 in RCX/RDX/R8/R9; assigning
                    // args[3] writes to R9, which the function reads as
                    // Fix64 raw int64. The constructed BucketAction will
                    // hold our magic value as its Utility.
                    try {
                        const rejectVal =
                            utilityConsts.REJECT ?? fix.penalty;
                        const buf = Memory.alloc(8);
                        buf.writeS64(rejectVal);
                        args[3] = buf.readPointer();
                        fix.diag.genActionPatched++;
                        (this as unknown as Record<string, boolean>)
                            .__owFixPatched = true;
                        if (fix.patchedSamples.length < 30) {
                            fix.patchedSamples.push({
                                col: destPos.col, row: destPos.row,
                                ts: Date.now(),
                            });
                        }
                        recordGenActionStack(
                            this.context, "patched", destPos);
                    } catch {
                        fix.diag.genActionWriteFailed++;
                    }
                },
                onLeave(retval) {
                    const wasPatched = (this as unknown as Record<
                        string, boolean>).__owFixPatched;
                    if (!wasPatched) return;
                    try {
                        if (retval.isNull()) {
                            fix.diag.genActionLeaveNullRet++;
                            return;
                        }
                        const utilityRaw = retval.add(BA_UTILITY).readS64();
                        const expectedReject = utilityConsts.REJECT
                            ?? fix.penalty;
                        if (utilityRaw.compare(expectedReject) === 0) {
                            fix.diag.genActionLeaveSurvived++;
                        } else {
                            fix.diag.genActionLeaveOverwritten++;
                        }
                        if (fix.genActionLeaveUtilSamples.length < 20) {
                            fix.genActionLeaveUtilSamples.push({
                                utility: utilityRaw.toString(),
                                expectedReject:
                                    utilityRaw.compare(expectedReject)
                                        === 0,
                                ts: Date.now(),
                            });
                        }
                    } catch {
                        fix.diag.genActionLeaveReadFailed++;
                    }
                },
            }));
        } catch (e) {
            log("[overwatch-fix] failed to hook GenerateAction: "
                + (e as Error).message);
        }
    }
}
