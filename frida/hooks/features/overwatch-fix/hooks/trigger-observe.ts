// Hook: observe the runtime IAbilityTrigger.ShouldTrigger predicate of
// `Overwatch_AutoAttackEffect`.
//
// The game encodes when an Overwatch should fire as a composable AST of
// `AbilityTrigger` predicates (with `& | !` operators). The root node is
// returned by `RangedAutoAttackEffect.CreateActiveCondition()` (slot 61
// virtual, override-able). Each call to that root's `ShouldTrigger
// (AbilityEntities entities, EventTriggerType triggerType)` answers
// "should this overwatch fire right now, given this context?".
//
// Hooking those firings tells us **the actual game rule** for OW
// activation — engaged, stunned, out-of-ammo, etc. — without guessing.
//
// We pair two hooks:
//   1. CreateActiveCondition.onLeave  → capture every Overwatch effect's
//      trigger root pointer.
//   2. For each unique captured root, dynamically resolve and hook its
//      ShouldTrigger via `il2cpp_class_get_method_from_name(klass,
//      "ShouldTrigger", 2)`. Filter at runtime to fires whose `this` is
//      one of our captured roots (so we don't drown in unrelated
//      AbilityTrigger fires from elsewhere in the game).
//
// onEnter: `args[0]` is `this` (the trigger). `args[1]` is the
// `AbilityEntities` struct passed by hidden pointer (Win64 ABI, structs
// > 8 bytes go by ref). Read entities.{Owner@0x18, Target@0x10,
// CasterTile@0x40} for context.

import {
    class_get_name, class_get_namespace, cstr, il2cppBase,
    IL2CPP_MODULE_NAME, methodEntry,
} from "../../../il2cpp/helpers.js";
import { log } from "../../../runtime/diag.js";
import { overwatchEffectClass } from "../resolve.js";
import { fix } from "../state.js";

function readClassFqn(klass: NativePointer): string {
    if (klass.isNull()) return "<null>";
    try {
        const ns = cstr(class_get_namespace(klass) as NativePointer);
        const name = cstr(class_get_name(klass) as NativePointer);
        return ns ? ns + "." + name : name;
    } catch {
        return "<read-failed>";
    }
}

function rvaOf(p: NativePointer): string {
    try {
        const off = p.sub(il2cppBase);
        return "0x" + off.toString(16);
    } catch {
        return "?";
    }
}

const _il2cppLib = Process.findModuleByName(IL2CPP_MODULE_NAME);
const _classGetMethodFromName = (() => {
    if (!_il2cppLib) return null;
    const p = _il2cppLib.findExportByName(
        "il2cpp_class_get_method_from_name");
    return p ? new NativeFunction(
        p, "pointer", ["pointer", "pointer", "int"]) : null;
})();

const TRIGGER_LOG_MAX = 100;

/** Track which trigger CLASSES we've already attached to ShouldTrigger,
 * so multiple overwatcher instances of the same trigger class share one
 * listener instead of stacking redundant hooks. */
const _hookedTriggerClasses = new Set<string>();

function resolveCreateActiveCondition(): NativePointer | null {
    if (!overwatchEffectClass || !_classGetMethodFromName) return null;
    const nameBuf = Memory.allocUtf8String("CreateActiveCondition");
    const mi = _classGetMethodFromName(
        overwatchEffectClass, nameBuf, 0) as NativePointer;
    if (mi.isNull()) return null;
    let entry = methodEntry(mi);
    if (entry.isNull()) {
        try { entry = mi.readPointer(); } catch { return null; }
    }
    return entry.isNull() ? null : entry;
}

function attachShouldTriggerHookForKlass(klass: NativePointer): void {
    if (!_classGetMethodFromName) return;
    const klassKey = klass.toString();
    if (_hookedTriggerClasses.has(klassKey)) return;
    _hookedTriggerClasses.add(klassKey);
    const fqn = readClassFqn(klass);

    const nameBuf = Memory.allocUtf8String("ShouldTrigger");
    const mi = _classGetMethodFromName(klass, nameBuf, 2) as NativePointer;
    if (mi.isNull()) {
        log("[overwatch-fix] trigger-observe: ShouldTrigger(2) not "
            + "resolved on trigger class " + fqn + " (" + klassKey + ")");
        return;
    }
    let entry = methodEntry(mi);
    if (entry.isNull()) {
        try { entry = mi.readPointer(); } catch { return; }
    }
    if (entry.isNull()) {
        log("[overwatch-fix] trigger-observe: ShouldTrigger entry null on "
            + fqn);
        return;
    }
    log("[overwatch-fix] trigger-observe: hooking ShouldTrigger on " + fqn
        + " (klass " + klassKey + ") @ " + entry.toString()
        + " RVA=" + rvaOf(entry));

    let attached = false;
    try {
        fix.listeners.push(Interceptor.attach(entry, mkShouldTriggerCb()));
        attached = true;
    } catch (e) {
        log("[overwatch-fix] trigger-observe: Interceptor.attach FAILED on "
            + fqn + " RVA=" + rvaOf(entry) + " — " + (e as Error).message);
    }
    if (!attached) return;
}

function mkShouldTriggerCb(): InvocationListenerCallbacks {
    return {
        onEnter(args) {
            const thisPtr = args[0];
            const key = thisPtr.toString();
            // Skip if this isn't one of our captured Overwatch trigger
            // roots — same shared body fires for every other AbilityTrigger
            // in the game so we'd drown in unrelated calls otherwise.
            if (!fix.capturedTriggerPtrs.has(key)) return;
            (this as Record<string, unknown>).__owt_active = true;
            (this as Record<string, unknown>).__owt_this = key;
            (this as Record<string, unknown>).__owt_ctx = args[1];
        },
        onLeave(retval) {
            const active = (this as Record<string, unknown>)
                .__owt_active as boolean | undefined;
            if (!active) return;
            fix.diag.triggerShouldTriggerFires++;
            const result = retval.toInt32() !== 0;
            if (result) fix.diag.triggerShouldTriggerTrue++;
            else fix.diag.triggerShouldTriggerFalse++;

            let ownerPtr: string | null = null;
            let targetPtr: string | null = null;
            let casterTilePtr: string | null = null;
            const entities = (this as Record<string, unknown>)
                .__owt_ctx as NativePointer | undefined;
            if (entities && !entities.isNull()) {
                try {
                    const o = entities.add(0x18).readPointer();
                    if (!o.isNull()) ownerPtr = o.toString();
                    const t = entities.add(0x10).readPointer();
                    if (!t.isNull()) targetPtr = t.toString();
                    const ct = entities.add(0x40).readPointer();
                    if (!ct.isNull()) casterTilePtr = ct.toString();
                } catch { /* keep nulls */ }
            }
            if (fix.triggerShouldTriggerLog.length < TRIGGER_LOG_MAX) {
                fix.triggerShouldTriggerLog.push({
                    triggerPtr: (this as Record<string, unknown>)
                        .__owt_this as string,
                    retval: result, ownerPtr, targetPtr, casterTilePtr,
                    ts: Date.now(),
                });
            }
        },
    };
}

export function installTriggerObserveHook(): void {
    if (!overwatchEffectClass) {
        log("[overwatch-fix] trigger-observe: Overwatch_AutoAttackEffect "
            + "class not resolved, skipping");
        return;
    }
    if (!_classGetMethodFromName) {
        log("[overwatch-fix] trigger-observe: il2cpp_class_get_method_"
            + "from_name not exported, skipping");
        return;
    }
    const createMi = resolveCreateActiveCondition();
    if (!createMi) {
        log("[overwatch-fix] trigger-observe: CreateActiveCondition not "
            + "resolved on Overwatch_AutoAttackEffect");
        return;
    }
    log("[overwatch-fix] trigger-observe: hooking CreateActiveCondition @ "
        + createMi.toString());

    fix.listeners.push(Interceptor.attach(createMi, {
        onEnter(args) {
            // Filter: only catch the Overwatch_AutoAttackEffect override.
            // The slot is on RangedAutoAttackEffect parent; many other
            // RangedAutoAttackEffect-derived effects share the slot and
            // we don't want to capture their triggers.
            try {
                const klass = args[0].readPointer();
                (this as Record<string, unknown>).__owt_isOw =
                    klass.equals(overwatchEffectClass!);
            } catch {
                (this as Record<string, unknown>).__owt_isOw = false;
            }
        },
        onLeave(retval) {
            const isOw = (this as Record<string, unknown>)
                .__owt_isOw as boolean | undefined;
            if (!isOw) return;
            fix.diag.triggerCreateFires++;
            if (retval.isNull()) return;
            const key = retval.toString();
            if (fix.capturedTriggerPtrs.has(key)) return;
            fix.capturedTriggerPtrs.add(key);
            fix.diag.triggerCaptured++;
            try {
                const klass = retval.readPointer();
                const fqn = readClassFqn(klass);
                log("[overwatch-fix] trigger-observe: captured trigger root @ "
                    + key + " class=" + fqn);
                if (!klass.isNull()) {
                    attachShouldTriggerHookForKlass(klass);
                }
            } catch (e) {
                log("[overwatch-fix] trigger-observe: failed to attach "
                    + "ShouldTrigger: " + (e as Error).message);
            }
        },
    }));
}
