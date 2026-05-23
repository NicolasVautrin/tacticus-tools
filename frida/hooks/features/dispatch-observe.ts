// Dispatch observation — hook BaseTriggeredAbility.ShouldTrigger to map
// who calls the trigger evaluator at runtime, with what context, and what
// retval comes back. Independent of overwatch-fix; built to answer the
// curiosity question "who upstream invokes this method, and could we
// invoke it ourselves for what-if scenarios?".
//
// Each fire records:
//   - this->klass FQN  (TriggeredAbility subtype)
//   - retval (true/false), with per-class true/false counters
//   - top-N stack RVAs, deduped per (class, topRva) pair so we get one
//     specimen per upstream caller per class
//   - eventTriggerType (4-byte enum, args[2])
//   - one memcpy snapshot of args[1] (AbilityEntities, 0x120 bytes) per
//     class — kept as a hex string so it can be replayed/mutated later
//
// Volume guard: stacks capped via StackBucket; templates capped to 5
// per-class entries; fireLog ring capped to 50 entries.
//
// Default OFF — enabled via POST /api/dispatch-observe/enable.

import { Ctx } from "../controller.js";
import {
    class_get_name, class_get_namespace, cstr, findClassAnywhere,
    IL2CPP_MODULE_NAME, methodEntry,
} from "../il2cpp/helpers.js";
import { StackBucket } from "../ai-toolkit/stack-capture.js";
import { log } from "../runtime/diag.js";
import { queueOnMainThread } from "../runtime/queue.js";

const _il2cppLib = Process.findModuleByName(IL2CPP_MODULE_NAME);
const _classGetMethodFromName = (() => {
    if (!_il2cppLib) return null;
    const p = _il2cppLib.findExportByName(
        "il2cpp_class_get_method_from_name");
    return p ? new NativeFunction(
        p, "pointer", ["pointer", "pointer", "int"]) : null;
})();

/** AbilityEntities is a struct; size taken from dump.cs offsets table:
 * last field at 0x11C (Nullable<int> MovementSteps, payload at 0x120 — the
 * struct is 0x120 bytes including alignment). */
const ABILITY_ENTITIES_SIZE = 0x120;
const TEMPLATES_PER_CLASS_MAX = 1;
const FIRE_LOG_MAX = 50;
const STACK_BUCKET_CAP = 30;

interface ClassFireStats {
    fires: number;
    trueCount: number;
    falseCount: number;
}

const observe = {
    enabled: false,
    listeners: [] as InvocationListener[],
    /** Stacks deduped per (class, topRva). Each unique class+caller pair
     * yields one stack specimen. */
    stackBucket: new StackBucket<string>(STACK_BUCKET_CAP),
    /** Per-class stats — every fire counts here, no cap. */
    firesByClass: {} as Record<string, ClassFireStats>,
    /** AbilityEntities templates, one per class (first-seen wins). The hex
     * dump can be replayed in a what-if invocation by allocating fresh
     * memory and writing the bytes back. */
    templates: [] as Array<{
        cls: string; entitiesAddr: string; hexDump: string; ts: number;
    }>,
    /** Recent fire log — bounded ring. */
    fireLog: [] as Array<{
        cls: string; thisPtr: string; retval: boolean;
        eventTriggerType: number; ts: number;
    }>,
};

function readClassFqn(klass: NativePointer): string {
    if (klass.isNull()) return "<null>";
    try {
        const ns = cstr(class_get_namespace(klass) as NativePointer);
        const name = cstr(class_get_name(klass) as NativePointer);
        return ns ? ns + "." + name : name;
    } catch { return "<read-failed>"; }
}

function snapshotEntitiesHex(p: NativePointer): string {
    try {
        const out: string[] = [];
        for (let i = 0; i < ABILITY_ENTITIES_SIZE; i++) {
            const b = p.add(i).readU8();
            out.push((b < 16 ? "0" : "") + b.toString(16));
        }
        return out.join("");
    } catch (e) {
        return "<read-failed: " + (e as Error).message + ">";
    }
}

function bumpStats(cls: string, retval: boolean): void {
    let s = observe.firesByClass[cls];
    if (!s) {
        s = { fires: 0, trueCount: 0, falseCount: 0 };
        observe.firesByClass[cls] = s;
    }
    s.fires++;
    if (retval) s.trueCount++; else s.falseCount++;
}

function maybeStashTemplate(
    cls: string, entitiesPtr: NativePointer,
): void {
    const existing = observe.templates.filter((t) => t.cls === cls).length;
    if (existing >= TEMPLATES_PER_CLASS_MAX) return;
    observe.templates.push({
        cls,
        entitiesAddr: entitiesPtr.toString(),
        hexDump: snapshotEntitiesHex(entitiesPtr),
        ts: Date.now(),
    });
}

function installShouldTriggerHook(): boolean {
    if (!_classGetMethodFromName) {
        log("[dispatch-observe] il2cpp_class_get_method_from_name not exported");
        return false;
    }
    const klass = findClassAnywhere(
        "IdunBattle.Entities.Abilities", "BaseTriggeredAbility");
    if (!klass) {
        log("[dispatch-observe] BaseTriggeredAbility class not resolved");
        return false;
    }
    const nameBuf = Memory.allocUtf8String("ShouldTrigger");
    const mi = _classGetMethodFromName(klass, nameBuf, 2) as NativePointer;
    if (mi.isNull()) {
        log("[dispatch-observe] ShouldTrigger(2) not found on "
            + "BaseTriggeredAbility");
        return false;
    }
    let entry = methodEntry(mi);
    if (entry.isNull()) {
        try { entry = mi.readPointer(); } catch { return false; }
    }
    if (entry.isNull()) {
        log("[dispatch-observe] ShouldTrigger entry is null");
        return false;
    }
    log("[dispatch-observe] hooking BaseTriggeredAbility.ShouldTrigger @ "
        + entry.toString());

    try {
        observe.listeners.push(Interceptor.attach(entry, {
            onEnter(args) {
                const thisPtr = args[0];
                let cls = "<unknown>";
                try {
                    const klassPtr = thisPtr.readPointer();
                    cls = readClassFqn(klassPtr);
                } catch { /* keep unknown */ }
                const ictx = (this as Record<string, unknown>);
                ictx.__do_cls = cls;
                ictx.__do_this = thisPtr.toString();
                // args[2] is EventTriggerType — passed in a register slot
                // (8 bytes on x64); read as int32 since the enum's storage
                // class is int.
                ictx.__do_evt = args[2].toInt32();
                ictx.__do_entities = args[1];
                // Capture stack: dedup per (class, topRva). Annotation
                // includes this pointer so multiple instances of same
                // class with same caller still produce one entry.
                observe.stackBucket.record(
                    this.context, cls, "this=" + thisPtr.toString());
                maybeStashTemplate(cls, args[1]);
            },
            onLeave(retval) {
                const ictx = (this as Record<string, unknown>);
                const cls = ictx.__do_cls as string | undefined;
                if (!cls) return;
                const result = retval.toInt32() !== 0;
                bumpStats(cls, result);
                if (observe.fireLog.length < FIRE_LOG_MAX) {
                    observe.fireLog.push({
                        cls,
                        thisPtr: ictx.__do_this as string,
                        retval: result,
                        eventTriggerType: ictx.__do_evt as number,
                        ts: Date.now(),
                    });
                }
            },
        }));
        Interceptor.flush();
        return true;
    } catch (e) {
        log("[dispatch-observe] Interceptor.attach FAILED: "
            + (e as Error).message);
        return false;
    }
}

function detachAll(): void {
    for (const l of observe.listeners) {
        try { l.detach(); } catch { /* */ }
    }
    observe.listeners = [];
}

export function register(ctx: Ctx): void {
    ctx.rpc.dispatchObserveEnable = (): Promise<unknown> =>
        queueOnMainThread(() => {
            if (observe.enabled) {
                return { ok: true, alreadyEnabled: true,
                    listeners: observe.listeners.length };
            }
            const ok = installShouldTriggerHook();
            observe.enabled = ok;
            return { ok, listeners: observe.listeners.length };
        });

    ctx.rpc.dispatchObserveDisable = (): unknown => {
        detachAll();
        observe.enabled = false;
        return { ok: true };
    };

    ctx.rpc.dispatchObserveStatus = (): unknown => ({
        enabled: observe.enabled,
        listeners: observe.listeners.length,
        firesByClass: { ...observe.firesByClass },
        stacks: [...observe.stackBucket.stacks],
        stackCounts: { ...observe.stackBucket.categoryCounts },
        templates: observe.templates.map((t) => ({
            cls: t.cls,
            entitiesAddr: t.entitiesAddr,
            hexDump: t.hexDump,
            ts: t.ts,
        })),
        fireLog: observe.fireLog.slice(-30),
    });

    ctx.rpc.dispatchObserveReset = (): unknown => {
        observe.firesByClass = {};
        observe.stackBucket.reset();
        observe.templates = [];
        observe.fireLog = [];
        return { ok: true };
    };
}
