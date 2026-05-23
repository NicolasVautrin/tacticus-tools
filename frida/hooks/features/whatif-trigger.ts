// What-if trigger evaluation: clone a captured AbilityEntities template,
// optionally mutate fields by offset, and invoke
// `EvaluateTriggerOperation.ExecuteSimulation(EventTriggerType, AbilityEntities)`
// against either the live or the mirror runner.
//
// Pipeline:
//   1. Hook BaseTriggeredAbility.ShouldTrigger (already known viable from
//      dispatch-observe). On each fire, memcpy the 0x120 byte AbilityEntities
//      into a Frida-owned persistent buffer, indexed by `args[0]->klass FQN`.
//      First-seen wins per class.
//   2. Resolve the EvaluateTriggerOperation pointer for a given scope
//      ("live" | "mirror") via `runner.<OperationProcessor>k__BackingField
//      → OperationProcessor._evaluateAbilities`.
//   3. RPC `whatifTriggerInvoke({templateClass, scope, mutations,
//      eventTriggerType})` clones the template, applies mutations
//      (write a raw NativePointer at a struct offset), and calls
//      ExecuteSimulation via `il2cpp_runtime_invoke`.
//
// Side effects of ExecuteSimulation are NOT directly captured here — they
// land on the EvaluateTriggerOperation's `_events: IStreamDispatcher`
// which is the live or mirror's apply-stack. Callers should observe the
// apply-stack of the chosen scope to see emitted Actions.
//
// Default OFF — enabled via POST /api/whatif-trigger/enable.

import { Ctx } from "../controller.js";
import {
    class_get_name, class_get_namespace, cstr, findClassAnywhere, findMethod,
    getFieldOffset, IL2CPP_MODULE_NAME, methodEntry,
} from "../il2cpp/helpers.js";
import { invokeMethod } from "../il2cpp/invoke.js";
import { runnerClass } from "../game/runner.js";
import { state } from "../game/state.js";
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

const ABILITY_ENTITIES_SIZE = 0x120;

// --- Late-resolved class/method/offset refs ---
// `findClassAnywhere` calls walk every loaded image; defer until enable time
// to avoid running unconditionally on agent boot.

let opProcessorClass: NativePointer | null = null;
let evalTriggerOpClass: NativePointer | null = null;
let baseTriggeredAbilityClass: NativePointer | null = null;
let executeSimMi: { info: NativePointer; ptr: NativePointer } | null = null;
let runnerOpProcOff = -1;
let opProcEvalAbilitiesOff = -1;
let resolved = false;

function tryResolve(): boolean {
    if (resolved) return true;
    opProcessorClass = findClassAnywhere(
        "Core.Services", "OperationProcessor");
    if (!opProcessorClass) {
        log("[whatif] OperationProcessor class not resolved"); return false;
    }
    evalTriggerOpClass = findClassAnywhere(
        "IdunBattle.Operations", "EvaluateTriggerOperation");
    if (!evalTriggerOpClass) {
        log("[whatif] EvaluateTriggerOperation class not resolved");
        return false;
    }
    baseTriggeredAbilityClass = findClassAnywhere(
        "IdunBattle.Entities.Abilities", "BaseTriggeredAbility");
    if (!baseTriggeredAbilityClass) {
        log("[whatif] BaseTriggeredAbility class not resolved"); return false;
    }
    executeSimMi = findMethod(evalTriggerOpClass, "ExecuteSimulation");
    if (!executeSimMi || executeSimMi.ptr.isNull()) {
        log("[whatif] ExecuteSimulation not resolved"); return false;
    }
    runnerOpProcOff = getFieldOffset(
        runnerClass!, "<OperationProcessor>k__BackingField");
    if (runnerOpProcOff < 0) {
        log("[whatif] runner OperationProcessor field not found");
        return false;
    }
    opProcEvalAbilitiesOff = getFieldOffset(
        opProcessorClass, "_evaluateAbilities");
    if (opProcEvalAbilitiesOff < 0) {
        log("[whatif] _evaluateAbilities field not found"); return false;
    }
    resolved = true;
    log("[whatif] resolved: runnerOpProcOff=0x"
        + runnerOpProcOff.toString(16)
        + " opProcEvalAbilitiesOff=0x" + opProcEvalAbilitiesOff.toString(16)
        + " ExecuteSimulation=" + executeSimMi.ptr.toString());
    return true;
}

// --- Template store ---

interface Template {
    cls: string;
    /** Frida-allocated persistent buffer holding a 0x120 byte snapshot. The
     * Memory.alloc result lives until the agent unloads or we drop the
     * reference; storing it in `wt.templates` is enough to keep it alive. */
    buf: NativePointer;
    capturedAt: number;
    ownerPtr: string | null;
    targetPtr: string | null;
    casterTilePtr: string | null;
    /** EventTriggerType enum value at the moment the template was captured. */
    eventTriggerType: number;
}

const wt = {
    enabled: false,
    listeners: [] as InvocationListener[],
    /** Per-class templates, first-seen wins. Cap at ~80 templates max so the
     * memory footprint stays bounded (each template = 0x120 bytes ≈ negligible
     * but we don't want runaway growth in pathological scenarios). */
    templates: new Map<string, Template>(),
    fires: 0,
    /** Flag flipped by invokeWhatIf around the il2cpp_runtime_invoke call.
     * The ShouldTrigger hook reads it in onLeave to decide whether to push
     * a sample. queueOnMainThread guarantees we run on the same thread the
     * predicate fires on, so no race. */
    invokeRecording: false,
    /** Per-invocation log of ShouldTrigger retvals. Reset at each invokeWhatIf
     * call so the result is the trace of the most recent simulation. */
    invokeShouldTriggerLog: [] as Array<{
        cls: string; retval: boolean; eventTriggerType: number;
    }>,
    /** Substring filter — every fire whose class FQN includes this string
     * is appended to traceLog with retval, owner/target/casterTile ptrs and
     * top-N stack frames. Useful to observe the AI utility loop calling
     * ShouldTrigger thousands of times per turn during decision. Null = no
     * trace, fires never recorded. */
    traceClassFilter: null as string | null,
    /** Cap on trace log entries — beyond this, fires are silently dropped
     * to avoid runaway growth during long AI turns. */
    traceCap: 300,
    /** Trace log — appended on every ShouldTrigger fire whose class FQN
     * matches `traceClassFilter`. */
    traceLog: [] as Array<{
        cls: string; thisPtr: string; retval: boolean;
        eventTriggerType: number;
        ownerPtr: string | null; targetPtr: string | null;
        casterTilePtr: string | null;
        topRva: number; frames: string[];
        ts: number;
    }>,
    lastInvokeResult: null as null | Record<string, unknown>,
};

const TEMPLATES_MAX = 80;

function readClassFqn(klass: NativePointer): string {
    if (klass.isNull()) return "<null>";
    try {
        const ns = cstr(class_get_namespace(klass) as NativePointer);
        const name = cstr(class_get_name(klass) as NativePointer);
        return ns ? ns + "." + name : name;
    } catch { return "<read-failed>"; }
}

function captureTemplate(
    klass: NativePointer, entitiesPtr: NativePointer, evt: number,
): void {
    const cls = readClassFqn(klass);
    if (wt.templates.has(cls)) return;
    if (wt.templates.size >= TEMPLATES_MAX) return;
    let buf: NativePointer;
    try {
        buf = Memory.alloc(ABILITY_ENTITIES_SIZE);
        Memory.copy(buf, entitiesPtr, ABILITY_ENTITIES_SIZE);
    } catch (e) {
        log("[whatif] template alloc/copy failed for " + cls + ": "
            + (e as Error).message);
        return;
    }
    let ownerPtr: string | null = null;
    let targetPtr: string | null = null;
    let casterTilePtr: string | null = null;
    try {
        const o = entitiesPtr.add(0x18).readPointer();
        if (!o.isNull()) ownerPtr = o.toString();
        const t = entitiesPtr.add(0x10).readPointer();
        if (!t.isNull()) targetPtr = t.toString();
        const ct = entitiesPtr.add(0x40).readPointer();
        if (!ct.isNull()) casterTilePtr = ct.toString();
    } catch { /* keep nulls */ }
    wt.templates.set(cls, {
        cls, buf, capturedAt: Date.now(),
        ownerPtr, targetPtr, casterTilePtr, eventTriggerType: evt,
    });
}

function installCaptureHook(): boolean {
    if (!_classGetMethodFromName || !baseTriggeredAbilityClass) return false;
    const nameBuf = Memory.allocUtf8String("ShouldTrigger");
    const mi = _classGetMethodFromName(
        baseTriggeredAbilityClass, nameBuf, 2) as NativePointer;
    if (mi.isNull()) {
        log("[whatif] ShouldTrigger(2) not resolved"); return false;
    }
    let entry = methodEntry(mi);
    if (entry.isNull()) {
        try { entry = mi.readPointer(); } catch { return false; }
    }
    if (entry.isNull()) {
        log("[whatif] ShouldTrigger entry null"); return false;
    }
    log("[whatif] hooking BaseTriggeredAbility.ShouldTrigger @ "
        + entry.toString());
    try {
        wt.listeners.push(Interceptor.attach(entry, {
            onEnter(args) {
                wt.fires++;
                try {
                    const klass = args[0].readPointer();
                    const cls = readClassFqn(klass);
                    captureTemplate(klass, args[1], args[2].toInt32());
                    const ictx = this as Record<string, unknown>;
                    if (wt.invokeRecording) {
                        ictx.__wt_rec = true;
                        ictx.__wt_cls = cls;
                        ictx.__wt_evt = args[2].toInt32();
                    }
                    // trace mode: capture naturally-firing fires that match
                    // the substring filter. Stash everything we'll need in
                    // onLeave (entities ptrs are valid only during onEnter
                    // because args[1] points into the caller's stack frame).
                    if (wt.traceClassFilter
                        && cls.indexOf(wt.traceClassFilter) >= 0
                        && wt.traceLog.length < wt.traceCap) {
                        const e = args[1];
                        let owner: string | null = null;
                        let target: string | null = null;
                        let ct: string | null = null;
                        try {
                            const o = e.add(0x18).readPointer();
                            if (!o.isNull()) owner = o.toString();
                            const t = e.add(0x10).readPointer();
                            if (!t.isNull()) target = t.toString();
                            const c = e.add(0x40).readPointer();
                            if (!c.isNull()) ct = c.toString();
                        } catch { /* keep nulls */ }
                        ictx.__wt_trace = {
                            cls, thisPtr: args[0].toString(),
                            eventTriggerType: args[2].toInt32(),
                            ownerPtr: owner, targetPtr: target,
                            casterTilePtr: ct,
                        };
                    }
                } catch { /* swallow per-fire to avoid log spam */ }
            },
            onLeave(retval) {
                const ictx = this as Record<string, unknown>;
                if (ictx.__wt_rec) {
                    wt.invokeShouldTriggerLog.push({
                        cls: ictx.__wt_cls as string,
                        retval: retval.toInt32() !== 0,
                        eventTriggerType: ictx.__wt_evt as number,
                    });
                }
                const tr = ictx.__wt_trace as Record<string, unknown> | undefined;
                if (tr && wt.traceLog.length < wt.traceCap) {
                    let topRva = -1;
                    const frames: string[] = [];
                    try {
                        const bt = Thread.backtrace(this.context, Backtracer.ACCURATE);
                        for (let i = 0; i < Math.min(bt.length, 12); i++) {
                            const off = bt[i].sub(_il2cppLib!.base);
                            const inIl = off.compare(0) >= 0
                                && off.compare(_il2cppLib!.size) < 0;
                            if (i === 0 && inIl) topRva = off.toInt32();
                            frames.push(inIl ? "rva:0x" + off.toString(16)
                                : "abs:" + bt[i].toString());
                        }
                    } catch { /* */ }
                    wt.traceLog.push({
                        cls: tr.cls as string,
                        thisPtr: tr.thisPtr as string,
                        retval: retval.toInt32() !== 0,
                        eventTriggerType: tr.eventTriggerType as number,
                        ownerPtr: tr.ownerPtr as string | null,
                        targetPtr: tr.targetPtr as string | null,
                        casterTilePtr: tr.casterTilePtr as string | null,
                        topRva, frames, ts: Date.now(),
                    });
                }
            },
        }));
        Interceptor.flush();
        return true;
    } catch (e) {
        log("[whatif] capture attach failed: " + (e as Error).message);
        return false;
    }
}

function detachAll(): void {
    for (const l of wt.listeners) {
        try { l.detach(); } catch { /* */ }
    }
    wt.listeners = [];
}

// --- Invocation ---

interface Mutation {
    /** Byte offset into the AbilityEntities struct (0..0x11F). */
    offset: number;
    /** Hex string representation of a NativePointer (e.g. an IEntity*). */
    ptrHex: string;
}

function resolveEvaluateTriggerOp(
    scope: "live" | "mirror",
): NativePointer | null {
    const runner = scope === "live"
        ? state.runnerInstance : state.mirrorRunner;
    if (!runner || runner.isNull()) return null;
    try {
        const op = runner.add(runnerOpProcOff).readPointer();
        if (op.isNull()) return null;
        const eta = op.add(opProcEvalAbilitiesOff).readPointer();
        return eta.isNull() ? null : eta;
    } catch { return null; }
}

function invokeWhatIf(opts: {
    templateClass: string;
    scope: "live" | "mirror";
    mutations?: Mutation[];
    eventTriggerType?: number;
}): unknown {
    if (!resolved) return { ok: false, error: "not resolved" };
    const tmpl = wt.templates.get(opts.templateClass);
    if (!tmpl) {
        return { ok: false,
            error: "no template for class " + opts.templateClass,
            availableClasses: [...wt.templates.keys()] };
    }
    const opPtr = resolveEvaluateTriggerOp(opts.scope);
    if (!opPtr) {
        return { ok: false,
            error: "no EvaluateTriggerOperation for scope " + opts.scope };
    }
    let clone: NativePointer;
    try {
        clone = Memory.alloc(ABILITY_ENTITIES_SIZE);
        Memory.copy(clone, tmpl.buf, ABILITY_ENTITIES_SIZE);
    } catch (e) {
        return { ok: false, error: "clone alloc failed: "
            + (e as Error).message };
    }
    const applied: Mutation[] = [];
    for (const m of (opts.mutations ?? [])) {
        if (m.offset < 0 || m.offset > ABILITY_ENTITIES_SIZE - 8) {
            return { ok: false,
                error: "mutation offset out of bounds: " + m.offset };
        }
        try {
            clone.add(m.offset).writePointer(ptr(m.ptrHex));
            applied.push(m);
        } catch (e) {
            return { ok: false,
                error: "mutation failed at offset " + m.offset
                    + ": " + (e as Error).message };
        }
    }
    const evt = opts.eventTriggerType ?? tmpl.eventTriggerType;
    const evtBuf = Memory.alloc(4);
    evtBuf.writeS32(evt);
    // Snapshot pre-invoke for byte-level diff. ExecuteSimulation might
    // populate the result fields of AbilityEntities (TotalDamage, WasCrit,
    // IndividualHitDamage, …) — passing by hidden ref means writes on the
    // callee side could be visible in our clone. If the byte diff is
    // empty we know the simulator returns its results through other
    // channels (likely _events: IStreamDispatcher).
    const snapPre = hexOf(clone, ABILITY_ENTITIES_SIZE);
    wt.invokeShouldTriggerLog = [];
    wt.invokeRecording = true;
    try {
        const ret = invokeMethod(executeSimMi!.info, opPtr, [evtBuf, clone]);
        wt.invokeRecording = false;
        const snapPost = hexOf(clone, ABILITY_ENTITIES_SIZE);
        const byteDiff = diffHex(snapPre, snapPost);
        wt.lastInvokeResult = {
            ok: true, scope: opts.scope, opPtr: opPtr.toString(),
            templateClass: opts.templateClass, eventTriggerType: evt,
            mutationsApplied: applied,
            retval: ret.isNull() ? null : ret.toString(),
            byteDiffCount: byteDiff.length,
            byteDiff: byteDiff.slice(0, 60),
            cloneAddr: clone.toString(),
            shouldTriggerLog: [...wt.invokeShouldTriggerLog],
            ts: Date.now(),
        };
    } catch (e) {
        wt.invokeRecording = false;
        wt.lastInvokeResult = {
            ok: false, scope: opts.scope, opPtr: opPtr.toString(),
            templateClass: opts.templateClass, eventTriggerType: evt,
            mutationsApplied: applied,
            error: (e as Error).message, ts: Date.now(),
        };
    }
    return wt.lastInvokeResult;
}

function hexOf(p: NativePointer, len: number): string {
    const out: string[] = [];
    for (let i = 0; i < len; i++) {
        const b = p.add(i).readU8();
        out.push((b < 16 ? "0" : "") + b.toString(16));
    }
    return out.join("");
}

/** Diff two hex strings of equal length (each char = 1 nibble = 0.5 byte).
 * Returns a list of {offset, before, after} for each modified byte. */
function diffHex(pre: string, post: string): Array<{
    offset: number; pre: string; post: string;
}> {
    const out: Array<{ offset: number; pre: string; post: string }> = [];
    if (pre.length !== post.length) return out;
    // 2 hex chars = 1 byte
    for (let i = 0; i < pre.length; i += 2) {
        const a = pre.substr(i, 2);
        const b = post.substr(i, 2);
        if (a !== b) {
            out.push({ offset: i / 2, pre: a, post: b });
        }
    }
    return out;
}

export function register(ctx: Ctx): void {
    ctx.rpc.whatifTriggerStatus = (): unknown => ({
        enabled: wt.enabled,
        resolved,
        fires: wt.fires,
        templateClasses: [...wt.templates.keys()],
        templates: [...wt.templates.values()].map((t) => ({
            cls: t.cls,
            ownerPtr: t.ownerPtr,
            targetPtr: t.targetPtr,
            casterTilePtr: t.casterTilePtr,
            eventTriggerType: t.eventTriggerType,
            capturedAt: t.capturedAt,
            // hex dump bounded to avoid huge JSON; full template can be
            // fetched via /template/<cls>.
        })),
        lastInvokeResult: wt.lastInvokeResult,
    });

    ctx.rpc.whatifTriggerEnable = (): Promise<unknown> => queueOnMainThread(() => {
        if (!tryResolve()) {
            return { ok: false, error: "resolve failed" };
        }
        if (!wt.enabled) {
            const ok = installCaptureHook();
            wt.enabled = ok;
        }
        return { ok: wt.enabled, resolved };
    });

    ctx.rpc.whatifTriggerDisable = (): unknown => {
        detachAll();
        wt.enabled = false;
        return { ok: true };
    };

    ctx.rpc.whatifTriggerClearTemplates = (): unknown => {
        const before = wt.templates.size;
        wt.templates.clear();
        return { ok: true, cleared: before };
    };

    /** Set the substring filter for trace mode. Pass `cls: null` (or omit)
     * to disable tracing. The trace log is cleared when the filter changes. */
    ctx.rpc.whatifTriggerSetTraceFilter = (
        body?: { cls?: string | null; cap?: number },
    ): unknown => {
        const prevFilter = wt.traceClassFilter;
        const next = body?.cls ?? null;
        wt.traceClassFilter = next;
        if (typeof body?.cap === "number" && body.cap > 0) {
            wt.traceCap = Math.min(body.cap, 5000);
        }
        if (prevFilter !== next) {
            wt.traceLog = [];
        }
        return { ok: true, traceClassFilter: wt.traceClassFilter,
            traceCap: wt.traceCap };
    };

    /** Read the current trace log without clearing. Pass `clear: true` to
     * drain the buffer atomically. */
    ctx.rpc.whatifTriggerGetTrace = (
        body?: { clear?: boolean; max?: number },
    ): unknown => {
        const max = body?.max && body.max > 0 ? body.max : wt.traceLog.length;
        const slice = wt.traceLog.slice(0, max);
        if (body?.clear) wt.traceLog = [];
        return {
            ok: true,
            filter: wt.traceClassFilter,
            cap: wt.traceCap,
            count: wt.traceLog.length,
            entries: slice,
        };
    };

    ctx.rpc.whatifTriggerGetTemplate = (
        body?: { cls?: string },
    ): unknown => {
        const cls = body?.cls;
        if (!cls) return { ok: false, error: "cls required" };
        const t = wt.templates.get(cls);
        if (!t) {
            return { ok: false, error: "no template for " + cls,
                available: [...wt.templates.keys()] };
        }
        return {
            ok: true,
            cls: t.cls,
            ownerPtr: t.ownerPtr, targetPtr: t.targetPtr,
            casterTilePtr: t.casterTilePtr,
            eventTriggerType: t.eventTriggerType,
            hexDump: hexOf(t.buf, ABILITY_ENTITIES_SIZE),
        };
    };

    ctx.rpc.whatifTriggerInvoke = (
        body?: {
            templateClass?: string;
            scope?: "live" | "mirror";
            mutations?: Mutation[];
            eventTriggerType?: number;
        },
    ): Promise<unknown> => queueOnMainThread(() => {
        if (!body?.templateClass) {
            return { ok: false, error: "templateClass required" };
        }
        return invokeWhatIf({
            templateClass: body.templateClass,
            scope: body.scope ?? "mirror",
            mutations: body.mutations,
            eventTriggerType: body.eventTriggerType,
        });
    });
}
