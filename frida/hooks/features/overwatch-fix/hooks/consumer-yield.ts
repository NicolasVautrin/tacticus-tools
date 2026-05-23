// Hook: ActiveAbilityActionGenerator.<GenerateActions>d__6.MoveNext.
//
// CONSUMER-side observation hook. Stack analysis (in
// data/dumps/uu2fr8mv6c/all_game_targets_win.tsv) showed the suicide moves
// for this match come from this generator on `DefaultAiUnitTactic` units.
// We confirmed via gen-action's onLeave that REJECT survives into the
// returned BucketAction.Utility, yet the AI still suicides — meaning the
// consumer ignores Utility. This hook lets us:
//   - log every (col, row) the coroutine yields
//   - identify which IPlaybook subclass is producing in-range yields by
//     reading <playbook>5__5 @ 0x58 and <activeAbilityType>5__4 @ 0x50
//   - capture the upstream caller chain (deduped by topRva)
//
// State machine layout
// (sources_win/_NoNamespace/ActiveAbilityActionGenerator..cs):
//   <>1__state          @ 0x10 (int)
//   <>2__current        @ 0x18 (UnitAction*)        ← yielded action
//   unit                @ 0x20 (IEntity)
//   <>4__this           @ 0x28 (ActiveAbilityActionGenerator)
//   positions           @ 0x30 (IList<UnitPosition>)
//   overrideUtility     @ 0x38 (UtilityDefinition)
//   <actionsBucket>5__2 @ 0x40 (Bucket<UnitAction>)  ← live bucket
//   <>7__wrap2          @ 0x48
//   <activeAbilityType>5__4 @ 0x50 (ActiveAbilityType int)
//   <playbook>5__5      @ 0x58 (IPlaybook)
//   <>7__wrap5          @ 0x60
//   <position>5__7      @ 0x68 (UnitPosition struct)

import {
    class_get_methods, class_get_name, class_get_namespace,
    cstr, findClassAnywhere, methodEntry,
    method_get_name,
} from "../../../il2cpp/helpers.js";
import { findIteratorStateMachine } from "../../../ai-toolkit/coroutine.js";
import { hexDistance } from "../../../ai-toolkit/hex.js";
import { captureStack } from "../../../ai-toolkit/stack-capture.js";
import {
    LIST_ITEMS_BASE, LIST_ITEMS_PTR, UA_POSITION,
} from "../../../ai-toolkit/unit-action.js";
import { readTilePosition } from "../../../game/match-state.js";
import { log } from "../../../runtime/diag.js";
import { fix } from "../state.js";

export function installConsumerYieldHook(): void {
    const activeAbilityGenClass = findClassAnywhere(
        "IdunBattle.AI.ActionGenerators",
        "ActiveAbilityActionGenerator");
    if (!activeAbilityGenClass) {
        log("[overwatch-fix] ActiveAbilityActionGenerator class not found");
        return;
    }
    const smClass = findIteratorStateMachine(
        activeAbilityGenClass, "GenerateActions");
    if (!smClass) {
        log("[overwatch-fix] ActiveAbilityActionGenerator.GenerateActions "
            + "state machine not found");
        return;
    }
    let entry: NativePointer | null = null;
    const it = Memory.alloc(Process.pointerSize);
    it.writePointer(ptr(0));
    let mm: NativePointer;
    while (true) {
        mm = class_get_methods(smClass, it) as NativePointer;
        if (mm.isNull()) break;
        const mname = cstr(method_get_name(mm) as NativePointer);
        if (mname === "MoveNext" && entry === null) {
            entry = methodEntry(mm);
        }
    }
    if (!entry || entry.isNull()) {
        log("[overwatch-fix] ActiveAbilityActionGenerator.MoveNext not "
            + "resolved");
        return;
    }

    try {
        fix.listeners.push(Interceptor.attach(entry, {
            onEnter(args) {
                (this as unknown as Record<string, NativePointer>).__sm =
                    args[0];
            },
            onLeave(retval) {
                fix.diag.consumerYieldFires++;
                if (retval.toInt32() === 0) return;  // end-of-iter
                fix.diag.consumerYields++;
                const sm = (this as unknown as Record<
                    string, NativePointer>).__sm;
                if (!sm || sm.isNull()) return;
                let pos: { col: number; row: number } | null = null;
                try {
                    const action = sm.add(0x18).readPointer();
                    if (action.isNull()) {
                        fix.diag.consumerYieldReadFailed++; return;
                    }
                    const tiles = action.add(UA_POSITION).readPointer();
                    if (tiles.isNull()) {
                        fix.diag.consumerYieldReadFailed++; return;
                    }
                    const items = tiles.add(LIST_ITEMS_PTR).readPointer();
                    if (items.isNull()) {
                        fix.diag.consumerYieldReadFailed++; return;
                    }
                    const tile = items.add(LIST_ITEMS_BASE).readPointer();
                    if (tile.isNull()) {
                        fix.diag.consumerYieldReadFailed++; return;
                    }
                    pos = readTilePosition(tile);
                } catch {
                    fix.diag.consumerYieldReadFailed++; return;
                }
                if (!pos) {
                    fix.diag.consumerYieldReadFailed++; return;
                }
                let inRange = false;
                for (const info of fix.overwatchers.values()) {
                    const cp = info.cachedPos;
                    if (!cp) continue;
                    const d = hexDistance(
                        pos.col, pos.row, cp.col, cp.row);
                    if (d <= info.range) { inRange = true; break; }
                }
                if (fix.consumerYieldSamples.length < 30) {
                    fix.consumerYieldSamples.push({
                        col: pos.col, row: pos.row, inRange,
                        ts: Date.now(),
                    });
                }
                if (!inRange) return;
                fix.diag.consumerYieldedInRange++;
                // Identify the producing playbook + ability type.
                let playbookCls: string | null = null;
                let playbookNs: string | null = null;
                let abilityType: number | null = null;
                try {
                    abilityType = sm.add(0x50).readS32();
                    const pb = sm.add(0x58).readPointer();
                    if (!pb.isNull()) {
                        const klass = pb.readPointer();
                        if (!klass.isNull()) {
                            const namePtr = class_get_name(klass) as NativePointer;
                            const nsPtr = class_get_namespace(klass) as NativePointer;
                            playbookCls = cstr(namePtr);
                            playbookNs = cstr(nsPtr);
                        }
                    }
                } catch { /* best-effort */ }
                const prodKey = (playbookNs ?? "?") + "."
                    + (playbookCls ?? "?") + ":"
                    + (abilityType ?? -1);
                if (!fix._consumerYieldProducerKeys.has(prodKey)
                    && fix.consumerYieldProducers.length < 30) {
                    fix._consumerYieldProducerKeys.add(prodKey);
                    fix.consumerYieldProducers.push({
                        pos, playbookClass: playbookCls,
                        playbookNs, activeAbilityType: abilityType,
                        ts: Date.now(),
                    });
                }
                if (fix.consumerYieldStacks.length < 10) {
                    const { topRva, frames } = captureStack(this.context);
                    const dup = fix.consumerYieldStacks.find(
                        (s) => s.topRva === topRva);
                    if (!dup) {
                        fix.consumerYieldStacks.push({
                            topRva, frames, pos, ts: Date.now(),
                        });
                    }
                }
            },
        }));
    } catch (e) {
        log("[overwatch-fix] failed to hook "
            + "ActiveAbilityActionGenerator.MoveNext: "
            + (e as Error).message);
    }
}
