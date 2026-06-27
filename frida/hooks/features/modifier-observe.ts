// Modifier-layer observation — ONE-SHOT diagnostic to crack the static-RE
// wall on the damage MODIFIER chain.
//
// Context: `DamageCalculations.CalculateAttackerModifiersForPrediction`,
// `CalculateDefenderModifiersForPrediction`, `ApplyCappedModifiers` and the
// per-effect `*_ExtraDamageEffect.CreateEffectDamageBonusForAttack` are all
// invoked PURELY via IL2CPP MethodInfo dispatch (interface/virtual). Literal
// code search finds zero by-name callers → the caller + the runtime origin of
// the builder's `param_5` (effect/ability source list) are invisible to static
// RE. The decompiled AI-prediction path (PredictAttackRaw + every wrapper:
// PredictAttack, the b__0 lambdas, GetNormalAttackPrediction,
// BattleQuery/DamagePredictionQuery.GetAttackPrediction) never calls the
// modifier builder by name.
//
// This hook attaches to those methods and CAPTURES THE BACKTRACE on the first
// few fires. The backtrace's IL2CPP frames are emitted as RVAs (`rva:0x...`,
// offset from GameAssembly.dll base) — add 0x180000000 to each to get the
// ghidra preferred-image address and look it up against the build dump. That
// reveals: (1) whether the modifier builder fires AT ALL during an AI
// prediction (→ tells us if the AI uses this path or a different one), and
// (2) the exact caller chain → where param_5 is built.
//
// This is OBSERVATION of an already-RE'd mechanism (who calls it, from where),
// not formula-fitting. Read-only; no code is replaced.
//
// Auto-arms best-effort at register (battle classes may not be resolved yet at
// script load → the install is retried via the modifierObserveInstall RPC,
// which is what the scenario driver calls after warmup).

import { Ctx } from "../controller.js";
import {
    class_get_name, findClassAnywhere, findMethod, il2cppBase, s,
} from "../il2cpp/helpers.js";
import { captureStack } from "../ai-toolkit/stack-capture.js";
import { log } from "../runtime/diag.js";
import { queueOnMainThread } from "../runtime/queue.js";

interface Target {
    ns: string;
    cls: string;
    method: string;
    /** short tag used as the capture key */
    tag: string;
}

const TARGETS: Target[] = [
    {
        ns: "IdunBattle.Core.Services", cls: "DamageCalculations",
        method: "CalculateAttackerModifiersForPrediction", tag: "attackerMods",
    },
    {
        ns: "IdunBattle.Core.Services", cls: "DamageCalculations",
        method: "CalculateDefenderModifiersForPrediction", tag: "defenderMods",
    },
    {
        ns: "IdunBattle.Core.Services", cls: "DamageCalculations",
        method: "ApplyCappedModifiers", tag: "applyCapped",
    },
    // Per-effect source of the +25% (RapidAssault). If THIS fires during the
    // AI prediction, the effect→DamageBonus path is live (vs UI-only).
    {
        ns: "IdunBattle.Entities.Effects.Loki",
        cls: "RapidAssault_ExtraDamageEffect",
        method: "CreateEffectDamageBonusForAttack", tag: "rapidAssaultBonus",
    },
    // The ACTUAL AI-prediction path (decisionView reads dmgMin/dmgMax from
    // DamagePredictionQuery.GetAllPredictions → ... → PredictAttackRaw).
    // PredictAttackRaw's backtrace = "d'où on vient" (the full caller chain
    // from the AI entry down to the core). If the builders above stay at 0
    // while these fire, the ×1.25 enters this chain without the builders.
    {
        ns: "IdunBattle.Core.Services", cls: "DamagePrediction",
        method: "PredictAttackRaw", tag: "predictRaw",
    },
    {
        ns: "IdunBattle.Core.Services", cls: "DamagePredictionQuery",
        method: "GetAllPredictions", tag: "getAllPred",
    },
    // The CACHED query is what decisionView actually calls (resolveDpq). It
    // returns cached predictions on a hit (no recompute → no downstream fire).
    // Hooking it confirms decisionView hits it; on a cache MISS (after a state
    // change) it calls the underlying chain → PredictAttackRaw fires.
    {
        ns: "IdunBattleLogic.Core.Services.Caches",
        cls: "CachedDamagePredictionQuery",
        method: "GetAllPredictions", tag: "cachedGetAll",
    },
];

/** Capture at most this many backtraces per target (one-shot — we only need a
 * specimen of the caller chain, and the methods may be moderately hot during
 * an AI turn). After the cap the onEnter still counts fires but stops
 * capturing, keeping overhead negligible. */
const MAX_CAPTURES_PER_TARGET = 6;

// ── VALUE DUMP — per-bout armour/pierce inputs+output ───────────────────────
// To find the axis that explains u90 (oracle per-hit ≫ offline), dump the REAL
// values the native feeds to the per-bout core `GetBaseDamageWithFixedPiercedArmor`
// (@181030d10) : base bout (param_2), pierce-extras (param_3/param_4), armour
// penetration (param_10), and the returned per-bout damage. base bout ≈ 1850 /
// 2774 identifies u90's lo/hi; result vs offline [370,766] + penetration reveals
// whether armour/pierce is being modified. CONFIRMATION of an RE'd chain (which
// input differs), not fitting. Read-only.
const DUMP_TARGET: Target = {
    ns: "IdunBattle.Core.Services", cls: "DamagePrediction",
    method: "GetBaseDamageWithFixedPiercedArmor", tag: "baseDmgPierced",
};
const MAX_VALUE_DUMPS = 40;

/** FixMath.NET Fix64 = Q31.32 (64-bit, 32 fractional bits) → integer part = raw >> 32.
 * Damage values are positive so the logical shift is fine. Returns the int part
 * and the raw hex (for format sanity-checks). */
function fix64(p: NativePointer): { i: number; raw: string } {
    let i = NaN;
    try { i = p.shr(32).toInt32(); } catch { /* */ }
    return { i, raw: p.toString() };
}

interface ValueDump {
    idx: number;
    baseIn: { i: number; raw: string };
    pierceA: { i: number; raw: string };
    pierceB: { i: number; raw: string };
    penetration: { i: number; raw: string };
    result: { i: number; raw: string };
    ts: number;
}

// ── MODS DUMP — DamageModifiers struct fields per builder (attacker vs defender) ──────────────
// To SOURCE the 499 penetration: each builder fills its output DamageModifiers (args[0]) — field
// @0x10=additive(Fix64), @0x20=pierce-extra(Fix64), @0x28=penetration(Fix64). Reading both builders'
// @0x28 separately tells which SIDE (attacker u90 / defender u86) contributes the 499. Read-only.
const MODS_DUMP_TARGETS: Target[] = [
    {
        ns: "IdunBattle.Core.Services", cls: "DamageCalculations",
        method: "CalculateAttackerModifiersForPrediction", tag: "attModsDump",
    },
    {
        ns: "IdunBattle.Core.Services", cls: "DamageCalculations",
        method: "CalculateDefenderModifiersForPrediction", tag: "defModsDump",
    },
];
const MAX_MODS_DUMPS = 80;

interface ModsDump {
    idx: number;
    side: string;            // "attacker" | "defender"
    additive: { i: number; raw: string };
    pierce: { i: number; raw: string };       // @0x20
    penetration: { i: number; raw: string };  // @0x28
    ts: number;
}

// ── BONUS DUMP — per-source attribution via the BASE dispatchers + stacktrace ────────────────
// User's idea: hook the modifier *construction* point with a backtrace so every bonus is
// attributed to its SOURCE (which effect / which path created it). The two prediction-time
// dispatchers read the per-effect cached bonus:
//   • BaseEffect.HitsBonusForAttack  @180f12a30 → hits axis (PowerTrip_FullHealthEffect +1, …)
//   • BaseEffect.DamageBonusForAttack@180f0f5e0 → dmg/pierce/penetration axis (RapidAssault %, ignore-armour)
// `this` (the effect instance) = args[1] (after the hidden struct-return ptr) → its class name
// IS the source. The execution-time triggered-hits behaviour is a SEPARATE path:
//   • AddBonusHitsToCurrentHitGroupBehaviour.Execute @180f93410 → GetStuckIn's per-odd-hit bonus.
// If THIS fires during a decisionView-only window (no real attack), the PREDICTION simulates
// GetStuckIn (→ the 6 hits include it); if only the dispatchers fire, the prediction is
// base+effects only. Deduped by (tag, srcClass) so it stays bounded on hot paths. Read-only.
interface BonusTarget extends Target {
    /** arg index of the effect/source `this` (after the hidden struct-return ptr). */
    thisArgIdx: number;
}
const BONUS_TARGETS: BonusTarget[] = [
    {
        ns: "IdunBattle.Entities.Effects", cls: "BaseEffect",
        method: "HitsBonusForAttack", tag: "hitsBonus", thisArgIdx: 1,
    },
    {
        ns: "IdunBattle.Entities.Effects", cls: "BaseEffect",
        method: "DamageBonusForAttack", tag: "dmgBonus", thisArgIdx: 1,
    },
    {
        ns: "IdunBattle.Entities.Behaviours",
        cls: "AddBonusHitsToCurrentHitGroupBehaviour",
        method: "Execute", tag: "addBonusHitsExec", thisArgIdx: 1,
    },
];
const MAX_BONUS_DUMPS = 120;

interface BonusDump {
    idx: number;
    tag: string;
    srcClass: string | null;   // effect/source class name (read from `this`)
    topRva: number;
    /** frames as `rva:0x...` / `abs:0x...` — add 0x180000000 to each rva for ghidra. */
    frames: string[];
    ts: number;
}

interface Capture {
    tag: string;
    fireIdx: number;
    topRva: number;
    /** frames as `rva:0x...` (IL2CPP) / `abs:0x...` (outside). Add
     * 0x180000000 to each rva to get the ghidra address. */
    frames: string[];
    ts: number;
}

const state = {
    installed: false,
    listeners: [] as InvocationListener[],
    fires: {} as Record<string, number>,
    resolved: {} as Record<string, string>,
    missing: [] as string[],
    captures: [] as Capture[],
    valueDumps: [] as ValueDump[],
    modsDumps: [] as ModsDump[],
    bonusDumps: [] as BonusDump[],
    bonusSeen: new Set<string>(),
};

function installOnce(): {
    ok: boolean; hooked: string[]; missing: string[];
} {
    if (state.installed) {
        return {
            ok: true, hooked: Object.values(state.resolved),
            missing: state.missing,
        };
    }
    const hooked: string[] = [];
    const missing: string[] = [];
    for (const t of TARGETS) {
        const klass = findClassAnywhere(t.ns, t.cls);
        if (!klass) { missing.push(`${t.cls} (class not resolved)`); continue; }
        const m = findMethod(klass, t.method);
        if (!m || m.ptr.isNull()) {
            missing.push(`${t.cls}.${t.method} (method not found)`);
            continue;
        }
        state.fires[t.tag] = 0;
        const tag = t.tag;
        try {
            state.listeners.push(Interceptor.attach(m.ptr, {
                onEnter(this: InvocationContext) {
                    const n = (state.fires[tag] = (state.fires[tag] ?? 0) + 1);
                    if (n > MAX_CAPTURES_PER_TARGET) return;
                    const { topRva, frames } = captureStack(this.context);
                    state.captures.push({
                        tag, fireIdx: n, topRva, frames, ts: Date.now(),
                    });
                    log(`[modifier-observe] ${tag} fire#${n} top=rva:0x`
                        + topRva.toString(16) + " (ghidra 0x"
                        + (0x180000000 + topRva).toString(16) + ")");
                },
            }));
            const ghidra = 0x180000000 + m.ptr.sub(il2cppBase).toInt32();
            state.resolved[t.tag] = `${t.cls}.${t.method} @ ${m.ptr} `
                + `(ghidra 0x${ghidra.toString(16)})`;
            hooked.push(state.resolved[t.tag]);
        } catch (e) {
            missing.push(`${t.cls}.${t.method} (attach: `
                + (e as Error).message + ")");
        }
    }
    // Value-dump hook on the per-bout core (onEnter args + onLeave result).
    try {
        const dk = findClassAnywhere(DUMP_TARGET.ns, DUMP_TARGET.cls);
        const dm = dk ? findMethod(dk, DUMP_TARGET.method) : null;
        if (!dm || dm.ptr.isNull()) {
            missing.push(`${DUMP_TARGET.cls}.${DUMP_TARGET.method} (value-dump method not found)`);
        } else {
            state.fires[DUMP_TARGET.tag] = 0;
            state.listeners.push(Interceptor.attach(dm.ptr, {
                // args: [0]=this/param_1, [1]=base bout, [2]=pierceA, [3]=pierceB,
                // [4]=attacker, [5]=target, [6]=profile, [7]=p8, [8]=p9, [9]=penetration.
                onEnter(this: InvocationContext & { _vd?: ValueDump },
                        args: InvocationArguments) {
                    state.fires[DUMP_TARGET.tag] =
                        (state.fires[DUMP_TARGET.tag] ?? 0) + 1;
                    if (state.valueDumps.length >= MAX_VALUE_DUMPS) return;
                    this._vd = {
                        idx: state.valueDumps.length,
                        baseIn: fix64(args[1]),
                        pierceA: fix64(args[2]),
                        pierceB: fix64(args[3]),
                        penetration: fix64(args[9]),
                        result: { i: NaN, raw: "" }, ts: Date.now(),
                    };
                },
                onLeave(this: InvocationContext & { _vd?: ValueDump }, retval) {
                    if (!this._vd) return;
                    this._vd.result = fix64(retval);
                    state.valueDumps.push(this._vd);
                },
            }));
            const ghidra = 0x180000000 + dm.ptr.sub(il2cppBase).toInt32();
            state.resolved[DUMP_TARGET.tag] =
                `${DUMP_TARGET.cls}.${DUMP_TARGET.method} @ ${dm.ptr} `
                + `(ghidra 0x${ghidra.toString(16)}) [value-dump]`;
            hooked.push(state.resolved[DUMP_TARGET.tag]);
        }
    } catch (e) {
        missing.push(`${DUMP_TARGET.cls}.${DUMP_TARGET.method} (value-dump attach: `
            + (e as Error).message + ")");
    }

    // Per-builder DamageModifiers struct dump (attacker vs defender → source the penetration).
    for (const mt of MODS_DUMP_TARGETS) {
        try {
            const mk = findClassAnywhere(mt.ns, mt.cls);
            const mm = mk ? findMethod(mk, mt.method) : null;
            if (!mm || mm.ptr.isNull()) {
                missing.push(`${mt.cls}.${mt.method} (mods-dump method not found)`);
                continue;
            }
            const side = mt.tag === "attModsDump" ? "attacker" : "defender";
            state.listeners.push(Interceptor.attach(mm.ptr, {
                onEnter(this: InvocationContext & { _p1?: NativePointer },
                        args: InvocationArguments) {
                    this._p1 = args[0];   // output DamageModifiers struct ptr
                },
                onLeave(this: InvocationContext & { _p1?: NativePointer }) {
                    if (!this._p1 || this._p1.isNull()) return;
                    if (state.modsDumps.length >= MAX_MODS_DUMPS) return;
                    const p1 = this._p1;
                    try {
                        state.modsDumps.push({
                            idx: state.modsDumps.length, side,
                            additive: fix64(p1.add(0x10).readPointer()),
                            pierce: fix64(p1.add(0x20).readPointer()),
                            penetration: fix64(p1.add(0x28).readPointer()),
                            ts: Date.now(),
                        });
                    } catch { /* */ }
                },
            }));
            hooked.push(`${mt.cls}.${mt.method} @ ${mm.ptr} [mods-dump ${side}]`);
        } catch (e) {
            missing.push(`${mt.cls}.${mt.method} (mods-dump attach: `
                + (e as Error).message + ")");
        }
    }

    // Per-source bonus attribution (base dispatchers + execution behaviour) + backtrace.
    for (const bt of BONUS_TARGETS) {
        try {
            const bk = findClassAnywhere(bt.ns, bt.cls);
            const bm = bk ? findMethod(bk, bt.method) : null;
            if (!bm || bm.ptr.isNull()) {
                missing.push(`${bt.cls}.${bt.method} (bonus-dump method not found)`);
                continue;
            }
            state.fires[bt.tag] = 0;
            const tag = bt.tag;
            const thisIdx = bt.thisArgIdx;
            state.listeners.push(Interceptor.attach(bm.ptr, {
                onEnter(this: InvocationContext, args: InvocationArguments) {
                    state.fires[tag] = (state.fires[tag] ?? 0) + 1;
                    if (state.bonusDumps.length >= MAX_BONUS_DUMPS) return;
                    let srcClass: string | null = null;
                    try {
                        const self = args[thisIdx];
                        if (self && !self.isNull()) {
                            srcClass = s(
                                class_get_name(self.readPointer()) as NativePointer);
                        }
                    } catch { /* unreadable this → leave null */ }
                    // Dedup by (tag, srcClass): one specimen per source keeps the
                    // capture bounded even when the dispatcher is hot.
                    const key = `${tag}|${srcClass ?? "?"}`;
                    if (state.bonusSeen.has(key)) return;
                    state.bonusSeen.add(key);
                    const { topRva, frames } = captureStack(this.context);
                    state.bonusDumps.push({
                        idx: state.bonusDumps.length, tag, srcClass,
                        topRva, frames, ts: Date.now(),
                    });
                    log(`[modifier-observe] ${tag} src=${srcClass ?? "?"} `
                        + `top=rva:0x${topRva.toString(16)} (ghidra 0x`
                        + (0x180000000 + topRva).toString(16) + ")");
                },
            }));
            hooked.push(`${bt.cls}.${bt.method} @ ${bm.ptr} [bonus-dump ${tag}]`);
        } catch (e) {
            missing.push(`${bt.cls}.${bt.method} (bonus-dump attach: `
                + (e as Error).message + ")");
        }
    }

    try { Interceptor.flush(); } catch { /* */ }
    state.missing = missing;
    state.installed = hooked.length > 0;
    log(`[modifier-observe] install: ${hooked.length} hooked, `
        + `${missing.length} missing`);
    return { ok: state.installed, hooked, missing };
}

export function register(ctx: Ctx): void {
    // Best-effort auto-arm at register. Battle classes are usually NOT yet
    // resolvable at script load, so this typically no-ops with everything in
    // `missing`; the scenario driver re-arms via modifierObserveInstall after
    // warmup. Wrapped so a failure never breaks module load.
    try { installOnce(); } catch (e) {
        log("[modifier-observe] auto-arm skipped: " + (e as Error).message);
    }

    ctx.rpc.modifierObserveInstall = (): Promise<unknown> =>
        queueOnMainThread(() => installOnce());

    ctx.rpc.modifierObserveStatus = (): unknown => ({
        installed: state.installed,
        listeners: state.listeners.length,
        resolved: { ...state.resolved },
        missing: [...state.missing],
        fires: { ...state.fires },
        captures: state.captures.map((c) => ({ ...c })),
        valueDumps: state.valueDumps.map((v) => ({ ...v })),
        modsDumps: state.modsDumps.map((v) => ({ ...v })),
        bonusDumps: state.bonusDumps.map((v) => ({ ...v })),
    });

    ctx.rpc.modifierObserveReset = (): unknown => {
        for (const k of Object.keys(state.fires)) state.fires[k] = 0;
        state.captures = [];
        state.valueDumps = [];
        state.modsDumps = [];
        state.bonusDumps = [];
        state.bonusSeen.clear();
        return { ok: true };
    };
}
