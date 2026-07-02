// Bucket-system audit — observability hooks on the AI's BucketSystem to
// understand WHY the AI picks suicidal actions despite negative utility.
//
// Background: ai-trace shows the AI computes utility=-9966 for "darkaCompanion
// attacks Re'vas (will die from overwatch first, dmg=0)" and STILL picks it.
// The decision must come from the bucket cascade — the AI partitions actions
// into priority buckets and tries them in order. Once any "valid" action
// exists in a high-priority bucket, that bucket wins regardless of utility
// magnitude.
//
// This module hooks:
//   - Bucket<T>.AddAction(action)               (RVA 0x1478820)
//   - Bucket<T>.AddActionToBucket(weight, ...)  (RVA 0x14786B0)
//   - Bucket<T>.IsValidAction(action) → bool    (RVA 0x1479290)
//   - Bucket<T>.ChooseAction() → action         (RVA 0x1478CC0)
//
// All four are IL2CPP gshared method bodies (single compiled body shared by
// every closed Bucket<T> instantiation — IL2CPP's "fully shared generic"
// optimization). Hooking the RVA directly instrument all instantiations.
//
// BucketAction<T> layout (gshared, T = ref type):
//   - Header @ 0x0  (Il2CppClass*)
//   - Monitor @ 0x8
//   - Content @ 0x10  (T pointer — usually a UnitAction*)
//   - Utility @ 0x18  (Fix64 raw int64)
//
// UnitAction layout (from sources_win):
//   - Position @ 0x10        (UnitPosition struct, Tiles ptr at +0x0)
//   - Target @ 0x18          (IEntity*)
//   - AbilityType @ 0x20     (ActiveAbilityType)
//   - DamagePrediction @ 0x28 (struct, complex)

import { Ctx } from "../controller.js";
import {
    class_get_methods, cstr, findClassAnywhere,
    il2cppBase, method_get_name, methodEntry,
} from "../il2cpp/helpers.js";
import { getTraceOrigin, OriginBuffers } from "../game/trace-origin.js";

// --- RVAs (offsets relative to GameAssembly.dll base) ---

// ⚠ RVA build-spécifiques (gshared -> non résolus par findMethod). Rafraîchis pour le build
// gqfc5mff6c depuis ghidra (VA - 0x180000000) : Bucket<__Il2CppFullySharedGenericType>.
//   AddAction @1813fbcc0 · AddActionToBucket @1813fbb60 · ChooseAction @1813fc0d0 · IsValidAction @1813fc660
// À REFAIRE à chaque changement de hash (cf. CLAUDE.md — RVA hardcodée = diagnostic-only).
const RVA = {
    addAction: 0x13fbcc0,
    addActionToBucket: 0x13fbb60,
    isValidAction: 0x13fc660,
    chooseAction: 0x13fc0d0,
};

// --- BucketAction layout ---
const BA = {
    content: 0x10,  // T = pointer to UnitAction
    utility: 0x18,  // Fix64 = int64 raw
};

const UA = {
    position: 0x10,    // UnitPosition.Tiles ptr at this offset
    target: 0x18,      // IEntity*
    abilityType: 0x20, // ActiveAbilityType (int)
};

// --- Fix64 helper (raw int64 → human number, scaled by 2^32) ---

function fix64ToNumber(raw: Int64): number {
    // Fix64 has 32 fractional bits. Convert raw int64 to a JS number,
    // dividing by 2^32. Precision is fine for log-display purposes.
    return Number(BigInt(raw.toString())) / 4294967296;
}

// --- State ---

interface AddedAction {
    seq: number;
    originRunnerId: number | null;   // runner du RPC déclencheur (null = IA live)
    ts: number;
    bucketPtr: string;
    weightBucket: number | null;  // for AddActionToBucket
    utility: number;
    actionPtr: string;
    targetName: string | null;
    targetPtr: string | null;
    abilityType: number | null;
    destTilePtr: string | null;
}

interface ChooseEvent {
    seq: number;
    originRunnerId: number | null;   // runner du RPC déclencheur (null = IA live)
    ts: number;
    bucketPtr: string;
    chosenActionPtr: string | null;
    chosenUtility: number | null;
}

const audit = {
    enabled: false,
    seq: 0,
    listeners: [] as InvocationListener[],
    // Buffers PAR ORIGINE (cf. game/trace-origin.ts) — ring, cap PAR BUCKET.
    added: new OriginBuffers<AddedAction>(5000, "ring"),
    chosen: new OriginBuffers<ChooseEvent>(200, "ring"),
    diag: {
        addActionFires: 0,
        addActionToBucketFires: 0,
        isValidActionFires: 0,
        chooseActionFires: 0,
        ctorFires: 0,
        readErrors: 0,
    },
    /** First-fire backtraces — one captured per hook the very first time it
     * fires, then frozen. Surfaces the actual call-site that uses Bucket<T>. */
    backtraces: {} as Record<string, string[]>,
};

// --- Helpers ---

function readUnitActionFields(actionPtr: NativePointer): {
    targetPtr: string | null;
    abilityType: number | null;
} {
    const out: ReturnType<typeof readUnitActionFields> = {
        targetPtr: null, abilityType: null,
    };
    try {
        const target = actionPtr.add(UA.target).readPointer();
        if (!target.isNull()) out.targetPtr = target.toString();
        out.abilityType = actionPtr.add(UA.abilityType).readS32();
    } catch { /* keep nulls */ }
    return out;
}

/** Best-effort name read on a target IEntity. Reads VisualId at +0x20 of the
 * UnitComponent component if available. For diag purposes — we don't iterate
 * the entire components array here, just try the most common offset. */
function readTargetName(targetPtr: NativePointer): string | null {
    if (targetPtr.isNull()) return null;
    try {
        // Entity.Id @ 16 — we just dump the id as a fallback identifier.
        const id = targetPtr.add(16).readS32();
        return "id=" + id;
    } catch { return null; }
}

/** Capture an IL2CPP-symbolicated backtrace once per `tag`. After the first
 * call for a given tag, subsequent calls are no-ops (cheap counter check).
 * Output goes both into `audit.backtraces[tag]` and a diag send. */
function captureBacktraceOnce(ctx: CpuContext, tag: string): void {
    if (audit.backtraces[tag] !== undefined) return;
    try {
        const frames = Thread.backtrace(ctx, Backtracer.ACCURATE)
            .map((p) => DebugSymbol.fromAddress(p).toString());
        audit.backtraces[tag] = frames;
        send({
            t: "diag",
            msg: "[bucket-audit] BACKTRACE " + tag + "\n  "
                + frames.slice(0, 16).join("\n  "),
        });
    } catch (e) {
        audit.backtraces[tag] = ["<failed: " + (e as Error).message + ">"];
    }
}

// --- Hook installation ---

/** Find Bucket<T>'s methods via IL2CPP class lookup. The class name is
 * `Bucket\`1` for the open generic. We resolve via findClassAnywhere and
 * iterate its methods. The returned method entry is the gshared body — same
 * as the dump RVA but resolved through the runtime's actual MethodInfo so
 * we don't depend on RVA accuracy. */
function findBucketMethod(name: string): NativePointer | null {
    const klass = findClassAnywhere(
        "IdunBattle.AI.BucketSystem", "Bucket`1");
    if (!klass) return null;
    const it = Memory.alloc(Process.pointerSize);
    it.writePointer(ptr(0));
    let m: NativePointer;
    while (!(m = class_get_methods(klass, it) as NativePointer).isNull()) {
        if (cstr(method_get_name(m) as NativePointer) !== name) continue;
        return methodEntry(m);
    }
    return null;
}

function installHooks(): boolean {
    if (audit.listeners.length > 0) return true;

    // Resolve via the live IL2CPP class table only. The hardcoded RVAs
    // below are kept as documentation of where these methods USED to live
    // in the `nb3o9lmt6c` build, but are NOT used as a fallback anymore —
    // when the game binary updates (new hash under `tacticus/games/<HASH>`)
    // those RVAs point at random code, and Interceptor.attach silently
    // succeeds while hooking the wrong instructions. Symptoms: hooks fire
    // 0 times even when the AI is active, or worse, fire on hot paths and
    // crash. See CLAUDE.md "Hash du build = identité du dump" for context.
    void RVA;
    const addActionPtr = findBucketMethod("AddAction");
    const addActionToBucketPtr = findBucketMethod("AddActionToBucket");
    const isValidActionPtr = findBucketMethod("IsValidAction");
    const chooseActionPtr = findBucketMethod("ChooseAction");
    const ctorPtr = findBucketMethod(".ctor");
    if (!addActionPtr || !addActionToBucketPtr
        || !isValidActionPtr || !chooseActionPtr) {
        send({
            t: "diag",
            msg: "[bucket-audit] DISABLED: at least one Bucket<T> method "
                + "couldn't be resolved via findClassAnywhere. The previous "
                + "RVA fallback was removed because it would post-hash-change "
                + "hook random code. Skipping installation."
                + " AddAction=" + addActionPtr
                + " AddActionToBucket=" + addActionToBucketPtr
                + " IsValidAction=" + isValidActionPtr
                + " ChooseAction=" + chooseActionPtr,
        });
        return false;
    }

    send({
        t: "diag",
        msg: "[bucket-audit] entry pts: AddAction=" + addActionPtr
            + " AddActionToBucket=" + addActionToBucketPtr
            + " IsValidAction=" + isValidActionPtr
            + " ChooseAction=" + chooseActionPtr
            + " ctor=" + (ctorPtr ?? "<not found>"),
    });

    // Hook 0: .ctor — confirms the class is instantiated at all during AI eval
    if (ctorPtr) {
        audit.listeners.push(Interceptor.attach(ctorPtr, {
            onEnter(args) {
                audit.diag.ctorFires++;
                captureBacktraceOnce(this.context, "ctor");
            },
        }));
    }

    // Hook 1: AddAction(this=Bucket<T>, action=BucketAction<T>)
    audit.listeners.push(Interceptor.attach(addActionPtr, {
        onEnter(args) {
            audit.diag.addActionFires++;
            captureBacktraceOnce(this.context, "AddAction");
            try {
                const bucket = args[0];
                const action = args[1];
                if (bucket.isNull() || action.isNull()) return;
                const utility = fix64ToNumber(action.add(BA.utility).readS64());
                const content = action.add(BA.content).readPointer();
                const fields = content.isNull()
                    ? { targetPtr: null, abilityType: null }
                    : readUnitActionFields(content);
                const targetName = fields.targetPtr
                    ? readTargetName(ptr(fields.targetPtr)) : null;
                audit.added.push({
                    seq: ++audit.seq,
                    originRunnerId: getTraceOrigin(),
                    ts: Date.now(),
                    bucketPtr: bucket.toString(),
                    weightBucket: null,
                    utility,
                    actionPtr: action.toString(),
                    targetName,
                    targetPtr: fields.targetPtr,
                    abilityType: fields.abilityType,
                    destTilePtr: null,
                });
            } catch { audit.diag.readErrors++; }
        },
    }));

    // Hook 2: AddActionToBucket(this=Bucket<T>, weight=int, action=BucketAction<T>)
    audit.listeners.push(Interceptor.attach(addActionToBucketPtr, {
        onEnter(args) {
            audit.diag.addActionToBucketFires++;
            captureBacktraceOnce(this.context, "AddActionToBucket");
            try {
                const bucket = args[0];
                const weight = args[1].toInt32();
                const action = args[2];
                if (bucket.isNull() || action.isNull()) return;
                const utility = fix64ToNumber(action.add(BA.utility).readS64());
                const content = action.add(BA.content).readPointer();
                const fields = content.isNull()
                    ? { targetPtr: null, abilityType: null }
                    : readUnitActionFields(content);
                const targetName = fields.targetPtr
                    ? readTargetName(ptr(fields.targetPtr)) : null;
                audit.added.push({
                    seq: ++audit.seq,
                    originRunnerId: getTraceOrigin(),
                    ts: Date.now(),
                    bucketPtr: bucket.toString(),
                    weightBucket: weight,
                    utility,
                    actionPtr: action.toString(),
                    targetName,
                    targetPtr: fields.targetPtr,
                    abilityType: fields.abilityType,
                    destTilePtr: null,
                });
            } catch { audit.diag.readErrors++; }
        },
    }));

    // Hook 3: IsValidAction — log the validity decision per action
    audit.listeners.push(Interceptor.attach(isValidActionPtr, {
        onEnter(args) {
            audit.diag.isValidActionFires++;
            captureBacktraceOnce(this.context, "IsValidAction");
            (this as { _bucketPtr?: string; _actionPtr?: string })._bucketPtr
                = args[0].toString();
            (this as { _bucketPtr?: string; _actionPtr?: string })._actionPtr
                = args[1].toString();
        },
        // We don't push to a buffer — too noisy. Counter only.
    }));

    // Hook 4: ChooseAction — log which action gets picked
    audit.listeners.push(Interceptor.attach(chooseActionPtr, {
        onEnter(args) {
            audit.diag.chooseActionFires++;
            captureBacktraceOnce(this.context, "ChooseAction");
            (this as { _bucketPtr?: string })._bucketPtr = args[0].toString();
        },
        onLeave(retval) {
            const bucketPtr = (this as { _bucketPtr?: string })._bucketPtr
                ?? "?";
            try {
                const action = retval as NativePointer;
                if (action.isNull()) {
                    audit.chosen.push({
                        seq: ++audit.seq,
                        originRunnerId: getTraceOrigin(),
                        ts: Date.now(),
                        bucketPtr,
                        chosenActionPtr: null,
                        chosenUtility: null,
                    });
                    return;
                }
                const utility = fix64ToNumber(
                    action.add(BA.utility).readS64());
                audit.chosen.push({
                    seq: ++audit.seq,
                    originRunnerId: getTraceOrigin(),
                    ts: Date.now(),
                    bucketPtr,
                    chosenActionPtr: action.toString(),
                    chosenUtility: utility,
                });
            } catch { audit.diag.readErrors++; }
        },
    }));

    Interceptor.flush();
    return true;
}

function detachAll(): void {
    for (const l of audit.listeners) {
        try { l.detach(); } catch { /* */ }
    }
    audit.listeners = [];
}

// --- RPCs ---

export function register(ctx: Ctx): void {
    // Auto-install at boot — observability is on by default.
    audit.enabled = installHooks();

    ctx.rpc.bucketAuditStatus = (): unknown => ({
        enabled: audit.enabled,
        listeners: audit.listeners.length,
        added: audit.added.size(),
        chosen: audit.chosen.size(),
        diag: { ...audit.diag },
        backtraceTags: Object.keys(audit.backtraces),
    });

    /** Return the captured first-fire backtraces (one per hook tag). */
    ctx.rpc.bucketAuditBacktraces = (): unknown => {
        return { backtraces: { ...audit.backtraces } };
    };

    ctx.rpc.bucketAuditEnable = (): unknown => {
        audit.enabled = installHooks();
        return { ok: audit.enabled, listeners: audit.listeners.length };
    };

    ctx.rpc.bucketAuditDisable = (): unknown => {
        audit.enabled = false;
        detachAll();
        return { ok: true };
    };

    ctx.rpc.bucketAuditReset = (body?: { runnerId?: number }): unknown => {
        if (typeof body?.runnerId === "number") {
            // Reset SCOPÉ multi-acteur : drop les buckets de CE runner
            // (compteurs diag + backtraces restent globaux).
            audit.added.clear(body.runnerId);
            audit.chosen.clear(body.runnerId);
            return { ok: true, added: audit.added.size(),
                     chosen: audit.chosen.size() };
        }
        audit.added.clear();
        audit.chosen.clear();
        audit.seq = 0;
        Object.keys(audit.diag).forEach((k) => {
            (audit.diag as Record<string, number>)[k] = 0;
        });
        audit.backtraces = {};
        return { ok: true };
    };

    /** Dump recent additions (most recent first). */
    ctx.rpc.bucketAuditDumpAdded = (
        body?: { max?: number; targetPtr?: string; runnerId?: number },
    ): unknown => {
        const max = body?.max ?? 200;
        let entries = audit.added.entries(body?.runnerId);
        if (body?.targetPtr) {
            entries = entries.filter((e) => e.targetPtr === body.targetPtr);
        }
        return {
            total: entries.length, returned: Math.min(max, entries.length),
            entries: entries.slice(-max),
        };
    };

    ctx.rpc.bucketAuditDumpChosen = (
        body?: { max?: number; runnerId?: number },
    ): unknown => {
        const max = body?.max ?? 50;
        const entries = audit.chosen.entries(body?.runnerId);
        return {
            total: entries.length,
            returned: Math.min(max, entries.length),
            entries: entries.slice(-max),
        };
    };

    /** Cross-correlate — for a given bucket ptr, list all added actions
     * and the chosen action. Reveals the decision logic at that bucket. */
    ctx.rpc.bucketAuditByBucket = (body?: { bucketPtr?: string }): unknown => {
        if (!body?.bucketPtr) return { error: "bucketPtr required" };
        const added = audit.added.entries()
            .filter((e) => e.bucketPtr === body.bucketPtr);
        const chosen = audit.chosen.entries()
            .filter((e) => e.bucketPtr === body.bucketPtr);
        return { bucketPtr: body.bucketPtr, added, chosen };
    };
}
