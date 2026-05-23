// Hook: ALoki_NormalAttackPlaybook<T>.ShouldExecute — last-mile veto on
// Loki normal-attack actions whose caster ends up in an OW range.
//
// Why this hook exists: gen-action's onLeave verification proved REJECT
// survives into the BucketAction.Utility for moves we patch (16/16 in
// uu2fr8mv6c). Yet the AI still suicides with Loki normal attacks
// (activeAbilityType=69) because the consumer ignores Utility — the
// scoring is one of several inputs and ShouldExecute is the final gate
// before the action is added to the bucket. A `false` return here
// rejects the action entirely, regardless of any prior score.
//
// Class hierarchy (from sources_win):
//   Loki_NormalAttackPlaybook : ALoki_NormalAttackPlaybook<Loki_NormalAttackAbility>
//   ALoki_NormalAttackPlaybook<TAbility> : ComparablePlaybook<TAbility>
//   protected override bool ShouldExecute(IEntity caster, IEntity casterTile,
//                                         IEntity target, Fix64 attackHealUtility)
//
// One hook on the gshared body covers every closed instantiation (every
// concrete `Loki_*NormalAttackPlaybook` derives via the same generic).
//
// Args (x86-64 Windows): args[0]=this, args[1]=caster, args[2]=casterTile,
// args[3]=target, args[4]=attackHealUtility (Fix64). We read casterTile
// in onEnter, then in onLeave: if it falls within an overwatcher's
// range, replace retval with 0 (= false) so the playbook drops the action.

import {
    findClassAnywhere, IL2CPP_MODULE_NAME, methodEntry,
} from "../../../il2cpp/helpers.js";
import { hexDistance } from "../../../ai-toolkit/hex.js";
import { readTilePosition } from "../../../game/match-state.js";
import { log } from "../../../runtime/diag.js";
import { fix } from "../state.js";

// `il2cpp_class_get_method_from_name(klass, name, paramCount)` walks the
// inheritance chain — useful for resolving methods declared on an abstract
// gshared base where `class_get_methods` returns the methodInfo with a null
// methodPointer. Resolving from a concrete subclass returns the closed
// instantiation's MethodInfo, whose methodPointer is the gshared body.
const _il2cppLib = Process.findModuleByName(IL2CPP_MODULE_NAME);
const _classGetMethodFromName = (() => {
    if (!_il2cppLib) return null;
    const p = _il2cppLib.findExportByName(
        "il2cpp_class_get_method_from_name");
    return p ? new NativeFunction(
        p, "pointer", ["pointer", "pointer", "int"]) : null;
})();

export function installShouldExecuteHook(): void {
    if (!_classGetMethodFromName) {
        log("[overwatch-fix] should-execute: il2cpp_class_get_method_from_name "
            + "not exported — cannot resolve abstract gshared method");
        return;
    }
    // Resolve from a CONCRETE subclass. ALoki_NormalAttackPlaybook<T> is
    // an abstract open generic — its methods don't carry a methodPointer
    // since IL2CPP only emits code for closed instantiations. Pick the
    // canonical concrete: Loki_NormalAttackPlaybook : ALoki_NormalAttackPlaybook<
    // Loki_NormalAttackAbility>. il2cpp_class_get_method_from_name walks the
    // inheritance chain and returns the closest MethodInfo for ShouldExecute,
    // whose methodPointer is the gshared body shared by every subclass.
    const klass = findClassAnywhere(
        "IdunBattle.AI.Playbook.Loki", "Loki_NormalAttackPlaybook");
    if (!klass) {
        log("[overwatch-fix] should-execute: class "
            + "Loki_NormalAttackPlaybook not resolved");
        return;
    }
    const nameBuf = Memory.allocUtf8String("ShouldExecute");
    const methodInfo = _classGetMethodFromName(
        klass, nameBuf, 4) as NativePointer;
    if (methodInfo.isNull()) {
        log("[overwatch-fix] should-execute: ShouldExecute(4 args) not "
            + "found on Loki_NormalAttackPlaybook hierarchy");
        return;
    }
    let entry = methodEntry(methodInfo);
    if (entry.isNull()) {
        try { entry = methodInfo.readPointer(); } catch { entry = NULL; }
    }
    if (entry.isNull()) {
        log("[overwatch-fix] should-execute: methodPointer is null on "
            + "the resolved MethodInfo (gshared body unbound?)");
        return;
    }
    log("[overwatch-fix] should-execute: hooking ShouldExecute @ "
        + entry.toString());

    try {
        fix.listeners.push(Interceptor.attach(entry, {
            onEnter(args) {
                fix.diag.shouldExecuteFires++;
                if (fix.overwatchers.size === 0) {
                    fix.diag.shouldExecuteSkippedNoOverwatchers++;
                    return;
                }
                // Infiltrate caster — the Infiltrate trait makes the unit
                // invisible to Overwatch triggers, so we must NOT veto its
                // NormalAttack even if its casterTile is in OW range.
                // args[1] is `IEntity caster`.
                const caster = args[1];
                if (!caster.isNull()
                    && fix.infiltratedUnits.has(caster.toString())) {
                    fix.diag.shouldExecuteSkippedInfiltrate++;
                    return;
                }
                // args[2] = IEntity casterTile (the tile the unit would
                // attack from after moving). Stash for onLeave.
                (this as { _casterTile?: NativePointer })._casterTile =
                    args[2];
            },
            onLeave(retval) {
                // Master gate — when the operator turns off the veto for
                // observation purposes, let the AI suicide as normal so we
                // can capture the runtime predicate firings.
                if (!fix.vetoEnabled) return;
                // If the playbook is already returning false, no override
                // needed — preserves the original AI logic.
                if (retval.toInt32() === 0) return;
                const casterTile =
                    (this as { _casterTile?: NativePointer })._casterTile;
                if (!casterTile || casterTile.isNull()) return;
                let pos: { col: number; row: number } | null;
                try { pos = readTilePosition(casterTile); }
                catch {
                    fix.diag.shouldExecuteReadFailed++; return;
                }
                if (!pos) {
                    fix.diag.shouldExecuteReadFailed++; return;
                }
                let inRange = false;
                for (const info of fix.overwatchers.values()) {
                    const cp = info.cachedPos;
                    if (!cp) continue;
                    const d = hexDistance(
                        pos.col, pos.row, cp.col, cp.row);
                    if (d <= info.range) { inRange = true; break; }
                }
                if (!inRange) {
                    fix.diag.shouldExecuteSkippedNotInRange++;
                    return;
                }
                // Force false: replace return value with 0. On x86-64 a
                // bool returns in AL (low byte of RAX); writing the slot
                // to 0 makes the caller see false.
                try {
                    retval.replace(ptr(0));
                    fix.diag.shouldExecuteVetoed++;
                    if (fix.shouldExecuteVetoSamples.length < 30) {
                        fix.shouldExecuteVetoSamples.push({
                            col: pos.col, row: pos.row, ts: Date.now(),
                        });
                    }
                } catch {
                    fix.diag.shouldExecuteWriteFailed++;
                }
            },
        }));
    } catch (e) {
        log("[overwatch-fix] should-execute: failed to attach: "
            + (e as Error).message);
    }
}
