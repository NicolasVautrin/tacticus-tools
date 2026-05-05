// Shared module state, projection schemas, and low-level helpers used
// by every ai-trace submodule (predictions, playbooks, generators,
// utilities, ai-control). All mutable state lives in `traceState` so
// submodules can read/write across module boundaries via reference.

import {
    class_get_methods, class_get_name,
    method_get_name, methodEntry,
    s,
} from "../../il2cpp/helpers.js";
import { abilityName } from "../../data/ability-names.js";
import { triggeredAbilityName } from "../../data/triggered-ability-names.js";
import { projectPaths, type PathSpec } from "../../il2cpp/project.js";

// ---- Public types -------------------------------------------------------

export interface Levels { L1: boolean; L2: boolean; L3: boolean }

export interface EvalCtx {
    caster: unknown;
    casterTile: unknown;
    abilityType: number;
    playbookCls: string;
    startedAt: number;
}

export interface MutableTraceState {
    enabled: Levels;
    seq: number;
    currentEval: EvalCtx | null;
    installed: boolean;
}

export const traceState: MutableTraceState = {
    enabled: { L1: true, L2: true, L3: true },
    seq: 0,
    currentEval: null,
    installed: false,
};

export const installStatus: Record<string, string> = {};

// ---- Projection schema --------------------------------------------------

// Defaults are kept terse to keep the on-disk JSONL light:
//   - Unit anchors → just `name` (= `Component.Id`, e.g. "loki_PlagueMarine")
//   - Tile anchors → `col`, `row`, `elevation`
// Use aiTraceSetProjection RPC to enrich on demand.
const ENTITY_PROJECTION: PathSpec[] = [
    { path: "Component.Id", out: "name", type: "string" },
];
const TILE_PROJECTION: PathSpec[] = [
    { path: "Position.Coordinate.Column", out: "col",       type: "int" },
    { path: "Position.Coordinate.Row",    out: "row",       type: "int" },
    { path: "Component.Elevation",        out: "elevation", type: "int" },
];

export const projections: Record<string, PathSpec[]> = {
    caster:       ENTITY_PROJECTION,
    target:       ENTITY_PROJECTION,
    closestEnemy: ENTITY_PROJECTION,
    unit:         ENTITY_PROJECTION,
    casterTile:   TILE_PROJECTION,
    actionTile:   TILE_PROJECTION,
    caseTile:     TILE_PROJECTION,
};

export const ANCHORS = Object.keys(projections);

// ---- BEntityId → name cache --------------------------------------------
// Populated lazily by every `projectEntity` call (we always have a fresh
// IEntity pointer there, plus `Entity.<Id>k__BackingField` at +0x10).
// The cache lets `ai_action_applied` events resolve unit/caster/target
// IDs back to human-readable names without keeping live IEntity pointers.

const entityNameById: Map<number, string> = new Map();

export function readEntityId(entPtr: NativePointer): number {
    try { return entPtr.add(0x10).readS32(); } catch { return -1; }
}

export function entityNameOrId(id: number): string {
    if (id < 0) return "id:?";
    return entityNameById.get(id) ?? "id:" + id;
}

// ---- Projection helpers -------------------------------------------------

export function projectEntity(
    p: NativePointer, anchor: string,
): Record<string, unknown> | null {
    if (p.isNull()) return null;
    const spec = projections[anchor];
    const proj = spec ? projectPaths(p, spec) : { _ptr: p.toString() };
    const id = readEntityId(p);
    if (id >= 0 && proj && typeof proj === "object") {
        const n = (proj as Record<string, unknown>).name;
        if (typeof n === "string") entityNameById.set(id, n);
    }
    return proj;
}

/** Project the first tile of a UnitPosition struct (passed by value as
 * the IList<IEntity>* of its Tiles field). Returns null when empty. */
export function projectFirstTile(
    posArg: NativePointer, anchor: string,
): { count: number; tile: Record<string, unknown> | null } {
    if (posArg.isNull()) return { count: 0, tile: null };
    try {
        const items = posArg.add(0x10).readPointer();
        const count = posArg.add(0x18).readS32();
        if (items.isNull() || count <= 0 || count > 1000) {
            return { count: 0, tile: null };
        }
        const firstTile = items.add(0x20).readPointer();
        const tile = projectEntity(firstTile, anchor);
        return { count, tile };
    } catch { return { count: 0, tile: null }; }
}

// ---- Emit + low-level helpers ------------------------------------------

export function emit(record: Record<string, unknown>): void {
    try {
        send({ t: "ai_trace", seq: traceState.seq++,
            ts: Date.now(), ...record });
    } catch { /* best effort */ }
}

export function safeKlassName(klass: NativePointer): string {
    try {
        if (klass.isNull()) return "?";
        return s(class_get_name(klass) as NativePointer);
    } catch { return "?"; }
}

export function* enumerateMethodsByName(
    klass: NativePointer, name: string,
): Generator<{ info: NativePointer; ptr: NativePointer }> {
    const it = Memory.alloc(Process.pointerSize);
    it.writePointer(ptr(0));
    let m: NativePointer;
    while (!(m = class_get_methods(klass, it) as NativePointer).isNull()) {
        const n = s(method_get_name(m) as NativePointer);
        if (n === name) {
            const p = methodEntry(m);
            if (!p.isNull()) yield { info: m, ptr: p };
        }
    }
}

// ---- Fix64 reading -----------------------------------------------------
// FixedMath.NET Q31.32: a 64-bit raw value where the high 32 bits are
// the integer part and the low 32 bits are the fractional part.

/** Read Fix64 passed as a register-by-value argument. */
export function readFix64FromArg(arg: NativePointer): number {
    try {
        const v = BigInt(arg.toString());
        const sign = v >= 0x8000000000000000n
            ? v - 0x10000000000000000n : v;
        return Number(sign) / 4294967296;
    } catch { return NaN; }
}

/** Read a Fix64 value at a memory address (e.g., a state machine field). */
export function readFix64Raw(addr: NativePointer): number {
    try {
        const lo = addr.readU32();
        const hi = addr.add(4).readS32();
        return hi + lo / 4294967296;
    } catch { return NaN; }
}

/** Split RAX-returned 8-byte struct into its two int32 halves.
 * Used by PredictHeal / PredictArmorRestore (no-sret returns). */
export function splitU64(p: NativePointer): { lo: number; hi: number } {
    const u = BigInt(p.toString());
    const lo = Number(u & 0xffffffffn);
    const hi = Number((u >> 32n) & 0xffffffffn);
    return {
        lo: lo > 0x7fffffff ? lo - 0x100000000 : lo,
        hi: hi > 0x7fffffff ? hi - 0x100000000 : hi,
    };
}

// ---- Damage prediction reading -----------------------------------------

/** Read a DamagePredictionResult struct given its base address.
 * Layout (from dump.cs):
 *   +0x00  CurrentHealth: int       — target HP before this hit
 *   +0x04  CurrentArmor: int        — target armor before this hit
 *   +0x08  CurrentShield: int       — target shield before this hit
 *   +0x90  TotalDamage: MinMaxDamage  ({_cap @0, Min @8, Max @0xC})
 *   +0xB9  MightCrit: bool
 *   +0xBA  ForceOverkill: bool
 *   +0xBB  PreventOverkill: bool
 *   +0xC4  AppliedHits: int */
export function readDamagePredictionAt(
    dpBase: NativePointer,
): Record<string, unknown> | null {
    if (dpBase.isNull()) return null;
    try {
        return {
            currentHealth: dpBase.readS32(),
            currentArmor:  dpBase.add(0x4).readS32(),
            currentShield: dpBase.add(0x8).readS32(),
            dmgMin:        dpBase.add(0x98).readS32(),
            dmgMax:        dpBase.add(0x9C).readS32(),
            mightCrit:     dpBase.add(0xB9).readU8() !== 0,
            forceOverkill: dpBase.add(0xBA).readU8() !== 0,
            appliedHits:   dpBase.add(0xC4).readS32(),
        };
    } catch { return null; }
}

/** Read DamagePrediction inline at UnitAction.DamagePrediction (offset 0x28). */
export function readDamagePrediction(
    unitActionPtr: NativePointer,
): Record<string, unknown> | null {
    if (unitActionPtr.isNull()) return null;
    return readDamagePredictionAt(unitActionPtr.add(0x28));
}

/** Read AbilityOrEffect inline at `base`. .NET Nullable<int> layout:
 *   +0x0 hasValue (1B)  +0x4 value (int).
 * AbilityOrEffect inline:
 *   +0x00 _activeAbility   (Nullable<ActiveAbilityType>)
 *   +0x08 _triggeredAbility(Nullable<TriggeredAbilityType>)
 *   +0x10 _effect          (Nullable<EffectType>)
 * Returns first non-null discriminant. */
export function readAbilityOrEffect(
    base: NativePointer,
): Record<string, unknown> | null {
    try {
        if (base.readU8() !== 0) {
            return {
                kind: "active",
                name: abilityName(base.add(0x4).readS32()),
            };
        }
        if (base.add(0x8).readU8() !== 0) {
            return {
                kind: "triggered",
                name: triggeredAbilityName(base.add(0xC).readS32()),
            };
        }
        if (base.add(0x10).readU8() !== 0) {
            return { kind: "effect", id: base.add(0x14).readS32() };
        }
    } catch { /* fall through */ }
    return null;
}
