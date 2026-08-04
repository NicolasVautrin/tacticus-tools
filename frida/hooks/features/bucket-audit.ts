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
//   - Bucket<T>.AddAction(action)
//   - Bucket<T>.AddActionToBucket(weight, ...)
//   - Bucket<T>.IsValidAction(action) → bool
//   - Bucket<T>.ChooseAction() → action
//
// All four are IL2CPP gshared method bodies (single compiled body shared by
// every closed Bucket<T> instantiation — IL2CPP's "fully shared generic"
// optimization), so instrumenting one body covers every instantiation.
// Resolution is RUNTIME and goes through the INFLATED instance — see
// `findBucketMethod` for why the open definition is NOT usable here.
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
    class_get_name, cstr, findClassAnywhere, findMethod, il2cppBase,
    method_get_return_type, type_get_class_or_element_class,
} from "../il2cpp/helpers.js";
import { getTraceOrigin, OriginBuffers } from "../game/trace-origin.js";

// #475 : les quatre constantes `RVA` qui vivaient ici sont SUPPRIMÉES. Elles n'étaient plus
// utilisées pour attacher (`void RVA;`) et elles étaient 4/4 PÉRIMÉES — mesuré le 2026-08-04,
// sur `rnca9r7q6c` elles tombent en plein corps de `PlayerEventService$$SendPlayerEvent` et de
// `PointerEventsHelper$$SendEnterLeave`. Elles se présentaient comme de la documentation ; elles
// documentaient un autre build. Les corps se résolvent au RUNTIME (cf. `findBucketMethod`).

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

// LA DÉFINITION OUVERTE NE DONNE PAS LE CORPS — c'est ce qui rendait ce capteur MUET (#475).
//
// `findClassAnywhere("IdunBattle.AI.BucketSystem", "Bucket`1")` RÉUSSIT (mesuré live le
// 2026-08-04), et `findMethod` dessus rend bien un pointeur — mais c'est le THUNK d'invocation
// de la DÉFINITION générique, pas le corps pleinement partagé (#259 §3). Confronté à
// `data/symbols/rnca9r7q6c/ghidra/functions.tsv`, ce que l'ancienne résolution attachait était :
//   AddAction → `Unity.Services.Core.Device.IUserIdentifierProvider$$set_UserId`
//   IsValidAction → `UnityEngine.Purchasing.ITransactionLog$$HasRecordOf`
//   ChooseAction → `IActivationFactory$$ActivateInstance`
//   AddActionToBucket → `MinimumBinaryHeap\`1$$u003CMinHeapifyu003Eg__UpdateSmallestIfCandidateIsSmaller|21_1`
// — des corps triviaux DÉDUPLIQUÉS, sans rapport. Symptôme : `bucketAuditStatus` rendait
// `enabled: true, listeners: 5` et **0 fire** sur les cinq compteurs. C'est le coût mesuré : #597
// a dû lire `IsValidAction` au décompilé faute de capteur.
//
// LA VOIE QUI DONNE LE CORPS, et c'est la recette MESURÉE de #259-b : le `MethodInfo` d'une
// instance INFLATÉE porte le corps partagé. On atteint `Bucket<UnitAction>` par le TYPE DE RETOUR
// d'un playbook CONCRET (`EvaluateNonComparable` / `EvaluateInternal` rendent
// `IdunBattle.AI.BucketSystem.Bucket<IdunBattle.AI.ActionGenerators.UnitAction>`), puis
// `findMethod` sur cette classe-là.
//
// Plusieurs graines, délibérément : si l'une disparaît d'un build, les autres couvrent. Aucune
// n'est « meilleure » — la première qui résout gagne.
const BUCKET_SEEDS: Array<[string, string, string]> = [
    ["IdunBattle.AI.Playbook.Loki", "AberrantHypermorphPlaybook", "EvaluateNonComparable"],
    ["IdunBattle.AI.Playbook.Loki", "AetherStridePlaybook", "EvaluateNonComparable"],
    ["IdunBattle.AI.Playbook", "SolarAtomizerPlaybook", "EvaluateNonComparable"],
    ["IdunBattle.AI.Playbook", "BloodChalicePlaybook", "EvaluateInternal"],
];

/** `Il2CppClass*` de l'instance INFLATÉE `Bucket<UnitAction>`, ou null. Résolu une fois. */
let inflatedBucket: NativePointer | null | undefined;

function resolveInflatedBucket(): NativePointer | null {
    if (inflatedBucket !== undefined) return inflatedBucket;
    inflatedBucket = null;
    if (method_get_return_type === null || type_get_class_or_element_class === null) {
        return inflatedBucket;
    }
    for (const [ns, cls, method] of BUCKET_SEEDS) {
        try {
            const k = findClassAnywhere(ns, cls);
            if (!k) continue;
            const mi = findMethod(k, method);
            if (!mi) continue;
            const t = method_get_return_type(mi.info) as NativePointer;
            if (t.isNull()) continue;
            const bk = type_get_class_or_element_class(t) as NativePointer;
            if (bk.isNull()) continue;
            if (cstr(class_get_name(bk) as NativePointer) !== "Bucket`1") continue;
            inflatedBucket = bk;
            return inflatedBucket;
        } catch { /* graine suivante */ }
    }
    return inflatedBucket;
}

/** Entrée du corps gshared d'une méthode de `Bucket<T>`, ou null — jamais le thunk.
 *
 * Le GARDE est structurel : on résout AUSSI sur la définition ouverte, et si les deux rendent la
 * MÊME adresse, c'est qu'on est retombé sur le thunk → on REFUSE. Sans ce test, une régression
 * silencieuse redeviendrait indiscernable d'un capteur qui marche. */
function findBucketMethod(name: string): NativePointer | null {
    const inflated = resolveInflatedBucket();
    if (inflated === null) return null;
    const m = findMethod(inflated, name);
    if (!m || m.ptr.isNull()) return null;
    const open = findClassAnywhere("IdunBattle.AI.BucketSystem", "Bucket`1");
    if (open) {
        const def = findMethod(open, name);
        if (def && !def.ptr.isNull() && def.ptr.equals(m.ptr)) {
            send({
                t: "diag",
                msg: "[bucket-audit] REFUS " + name + " : l'instance inflatée rend la MÊME"
                    + " adresse que la définition ouverte (" + m.ptr + ") — c'est le thunk"
                    + " d'invocation, pas le corps gshared. Aucun attachement.",
            });
            return null;
        }
    }
    return m.ptr;
}

function installHooks(): boolean {
    if (audit.listeners.length > 0) return true;

    // Résolution 100 % RUNTIME, via l'instance INFLATÉE (cf. `findBucketMethod`). Aucune adresse
    // en dur : `Interceptor.attach` réussit SILENCIEUSEMENT sur du code arbitraire, donc une RVA
    // périmée ne se voit ni à l'erreur ni au crash — seulement à un capteur muet.
    const addActionPtr = findBucketMethod("AddAction");
    const addActionToBucketPtr = findBucketMethod("AddActionToBucket");
    const isValidActionPtr = findBucketMethod("IsValidAction");
    const chooseActionPtr = findBucketMethod("ChooseAction");
    const ctorPtr = findBucketMethod(".ctor");
    if (!addActionPtr || !addActionToBucketPtr
        || !isValidActionPtr || !chooseActionPtr) {
        send({
            t: "diag",
            msg: "[bucket-audit] DISABLED: au moins une méthode de Bucket<T> n'a pas pu être"
                + " résolue sur l'instance INFLATÉE. On n'attache PAS : ni sur le thunk de la"
                + " définition ouverte (0 fire, mesuré #475), ni sur une adresse en dur."
                + " AddAction=" + addActionPtr
                + " AddActionToBucket=" + addActionToBucketPtr
                + " IsValidAction=" + isValidActionPtr
                + " ChooseAction=" + chooseActionPtr,
        });
        return false;
    }

    // La VA ghidra est imprimée pour être CONFRONTÉE à `data/symbols/<build>/ghidra/functions.tsv`
    // (attendu sur `rnca9r7q6c` : AddAction @1814eff60, AddActionToBucket @1814efe00,
    // IsValidAction @1814f0900, ChooseAction @1814f0370). C'est le contrôle qu'un lecteur peut
    // faire sans rien instrumenter.
    const ghidra = (p: NativePointer | null): string =>
        p === null ? "<null>" : "0x" + (0x180000000 + p.sub(il2cppBase).toInt32()).toString(16);
    send({
        t: "diag",
        msg: "[bucket-audit] entry pts (ghidra VA): AddAction=" + ghidra(addActionPtr)
            + " AddActionToBucket=" + ghidra(addActionToBucketPtr)
            + " IsValidAction=" + ghidra(isValidActionPtr)
            + " ChooseAction=" + ghidra(chooseActionPtr)
            + " ctor=" + ghidra(ctorPtr),
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
