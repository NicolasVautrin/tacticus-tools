// Effect recon — read the effects attached to each unit the SAME WAY the game
// renders them as status icons. Model (verified via dumpEntityComponents) :
//   - Every Unit (Type=1 squad) / Machine (Type=6) carries an
//     `EffectsOwnedComponent` whose `ActiveEffectIds` (List<BEntityId>) lists
//     the Effect entities it owns.
//   - Each effect is an `EffectEntity` (EntityType.Effect = 3) — a GENERIC
//     wrapper (its klass is always "EffectEntity"). Its identity + metadata
//     live on its `EffectComponent`:
//       SourceUnitId @0x10 · OwnerId @0x14 · AbilityVariant (String) @0x40
//       (= the descriptive name, e.g. "Ice", "RitesOfBattle_ExtraDmgImperial",
//        "Overwatch_AutoAttackEffect") · EffectType (enum) @0x58 ·
//       RemainingTurns @0x64 · Level @0x68 · ParentEffect @0x70.
//
// We read the game's own owned-effects list (no ad-hoc per-class scanning like
// overwatch-fix). All offsets resolved runtime via getFieldOffset — no RVA
// hardcoding (CLAUDE.md "Hash du build = identité du dump").

import {
    class_get_fields, class_get_name, field_get_name, field_get_offset,
    field_get_type, findClassAnywhere, getFieldOffset, s,
    type_get_class_or_element_class,
} from "../il2cpp/helpers.js";
import { EntityType, forEachComponent, forEachEntity } from "./match-state.js";
import { EFFECT_TYPE_NAMES } from "../data/effect-type-names.js";

const effectsOwnedComponentClass = findClassAnywhere(
    "IdunBattle.Entities.Components", "EffectsOwnedComponent");
const effectComponentClass = findClassAnywhere(
    "IdunBattle.Entities.Components", "EffectComponent");

// ActiveEffectIds : List<BEntityId> on EffectsOwnedComponent (dump: +0x10).
const activeEffectIdsOff = effectsOwnedComponentClass
    ? (getFieldOffset(effectsOwnedComponentClass, "ActiveEffectIds") || 0x10)
    : 0x10;

// EffectComponent field offsets (resolved by name; dump values as fallback).
const EC = {
    sourceUnitId: effectComponentClass
        ? (getFieldOffset(effectComponentClass, "SourceUnitId") || 0x10) : 0x10,
    effectType: effectComponentClass
        ? (getFieldOffset(effectComponentClass, "EffectType") || 0x58) : 0x58,
    isActive: effectComponentClass
        ? (getFieldOffset(effectComponentClass, "IsActive") || 0x5c) : 0x5c,
    removed: effectComponentClass
        ? (getFieldOffset(effectComponentClass, "Removed") || 0x5f) : 0x5f,
    remainingTurns: effectComponentClass
        ? (getFieldOffset(effectComponentClass, "RemainingTurns") || 0x64) : 0x64,
    level: effectComponentClass
        ? (getFieldOffset(effectComponentClass, "Level") || 0x68) : 0x68,
} as const;

// --- StatModifierComponent de l'entité-effet ---------------------------------
// La MAGNITUDE d'un effet stat-mod (le « +N Attack » qu'il porte) vivait jusqu'ici
// re-dérivée offline depuis le `StatsComponent` du porteur — avec une dépendance
// circulaire sur la famille EAGER (ActOfFaith lit `StatPart.INITIAL` du crit-damage,
// or l'attribution du seed précède la création du `UnitStats`). La lire À LA SOURCE
// supprime toute re-dérivation.
//
// Les NOMS DE CHAMPS ne sont PAS devinés : la classe fait 0x20 o (header
// BaseComponent 0x10 + le reste) et le dump ne porte pas sa table de champs. On
// énumère donc ses champs DÉCLARÉS au chargement (nom + offset + type) et on
// publie chaque valeur SOUS SON NOM NATIF. Si une MAJ renomme ou redispose, la
// charge utile change de forme au lieu de mentir sous un nom figé.
const statModifierComponentClass = findClassAnywhere(
    "IdunBattle.Entities.Components", "StatModifierComponent");

interface FieldRef { name: string; off: number; type: string }

/** Champs DÉCLARÉS d'une classe (sans remonter les parents — le header
 *  BaseComponent ne porte rien d'exploitable ici). */
function declaredFields(klass: NativePointer | null): FieldRef[] {
    if (!klass) return [];
    const out: FieldRef[] = [];
    try {
        const iter = Memory.alloc(Process.pointerSize);
        iter.writePointer(ptr(0));
        for (;;) {
            const f = class_get_fields(klass, iter) as NativePointer;
            if (f.isNull()) break;
            let type = "?";
            try {
                const tc = type_get_class_or_element_class(
                    field_get_type(f) as NativePointer) as NativePointer;
                if (!tc.isNull()) type = s(class_get_name(tc) as NativePointer);
            } catch { /* type best-effort */ }
            out.push({
                name: s(field_get_name(f) as NativePointer),
                off: field_get_offset(f) as number, type,
            });
        }
    } catch { /* classe non énumérable → aucun champ publié */ }
    return out;
}

const STAT_MODIFIER_FIELDS = declaredFields(statModifierComponentClass);

/** Lit le `StatModifierComponent` d'une entité-effet → {champ natif: valeur}.
 *  null si l'effet n'en porte pas (la grande majorité).
 *
 *  La LARGEUR de lecture suit le TYPE déclaré du champ : `Boolean` fait 1 octet,
 *  le lire en s32 ramasse les octets voisins et publie un nombre absurde
 *  (mesuré : `IsHidden: 1946157056` au lieu de 0/1). Enums et entiers restent en
 *  s32. C'est la raison d'être de l'énumération des champs : elle donne le type,
 *  pas seulement l'offset. */
function readStatModifier(
    effEntityPtr: NativePointer,
): Record<string, number> | null {
    if (!statModifierComponentClass || STAT_MODIFIER_FIELDS.length === 0) return null;
    let comp: NativePointer | null = null;
    forEachComponent(effEntityPtr, (c, klass) => {
        if (comp === null && klass.equals(statModifierComponentClass)) comp = c;
    });
    if (comp === null) return null;
    const c = comp as NativePointer;
    const out: Record<string, number> = {};
    for (const f of STAT_MODIFIER_FIELDS) {
        try {
            out[f.name] = (f.type === "Boolean" || f.type === "Byte"
                || f.type === "SByte")
                ? c.add(f.off).readU8()
                : c.add(f.off).readS32();
        } catch { /* champ illisible */ }
    }
    return out;
}

export interface EffectInfo {
    /** Effect entity id (EntityType.Effect). */
    effectId: number;
    /** AbilityVariant — descriptive effect name ("Ice", "RitesOfBattle_…"). */
    name: string | null;
    /** EffectType enum value (category). */
    effectType: number | null;
    /** RemainingTurns (null if HasTurns is false → permanent/aura). */
    remaining: number | null;
    level: number | null;
    /** SourceUnitId — entity that applied the effect. */
    source: number | null;
    /** `EffectComponent.IsActive` — l'effet est POSÉ mais son ActiveCondition
     *  n'est pas forcément satisfaite. Toujours `true` sauf si l'appelant a
     *  demandé `includeInactive` (les inactifs sont filtrés par défaut). */
    active: boolean;
    /** `EffectComponent.Removed`. */
    removed: boolean;
    /** Champs natifs du `StatModifierComponent` porté par l'entité-effet
     *  (magnitude À LA SOURCE), ou null s'il n'en porte pas. */
    statMod: Record<string, number> | null;
}

/** Decoded effect + liveness flags (IsActive/Removed) used to drop effects
 * owned but not currently applying (e.g. an aura whose target left its range). */
type Decoded = Omit<EffectInfo, "effectId">;

/** Read an EffectEntity's EffectComponent → identity + metadata + liveness. */
function readEffect(effEntityPtr: NativePointer): Decoded | null {
    if (!effectComponentClass) return null;
    let ec: NativePointer | null = null;
    forEachComponent(effEntityPtr, (comp, klass) => {
        if (klass.equals(effectComponentClass)) ec = comp;
    });
    if (!ec) return null;
    const c = ec as NativePointer;
    let effectType: number | null = null;
    let remaining: number | null = null;
    let level: number | null = null;
    let source: number | null = null;
    let active = true;     // default true: never drop on a read failure
    let removed = false;
    try { effectType = c.add(EC.effectType).readS32(); } catch { /* */ }
    try { remaining = c.add(EC.remainingTurns).readS32(); } catch { /* */ }
    try { level = c.add(EC.level).readS32(); } catch { /* */ }
    try { source = c.add(EC.sourceUnitId).readS32(); } catch { /* */ }
    try { active = c.add(EC.isActive).readU8() !== 0; } catch { /* */ }
    try { removed = c.add(EC.removed).readU8() !== 0; } catch { /* */ }
    // EffectType id → descriptive name via the generated enum table (= the
    // names the cascade/UI show: "Ice", "HeavyRailRifle_PendingTarget", …).
    const name = (effectType !== null)
        ? (EFFECT_TYPE_NAMES[effectType] ?? null) : null;
    return { name, effectType, remaining, level, source, active, removed,
             statMod: readStatModifier(effEntityPtr) };
}

// AbilityStateReference (struct inline, EffectComponent.AbilityState @0x18, dump gqfc5mff6c
// TypeDefIndex 24412) : Owner(BEntityId)@+0x00 · Ability(AbilityType, 0x10 o)@+0x04 ·
// Nullable<AbilityState>@+0x14 où AbilityState = {Level(int)@0, VariableMultiplierPercentage@4,
// TempData.Counter@8} (TypeDefIndex 24402). C'est le state BAKÉ à la création de l'effet que
// `BaseEffect.GetAbilityState @180f11780` (via `DSLFactory.AbilityStateFromEffect @180de5e60`,
// sélecteur <Effect>@factory+0x150) expose aux nœuds ConfigVar — la source du multiplier COMBAT
// d'un additif d'effet (#68/#75 : SmashaEad combat=300 vs prédiction 599). On dumpe la zone en
// ints BRUTS (le layout Nullable<T> il2cpp hasValue-first/value-first se décode côté client).
const abilityStateOff = effectComponentClass
    ? (getFieldOffset(effectComponentClass, "AbilityState") || 0x18) : 0x18;

/** Raw dump of an EffectEntity's AbilityStateReference (10 ints from comp+abilityStateOff)
 * + identity fields (EffectType/source/owner) resolved by name like readEffect. */
export function readEffectAbilityStateRaw(effEntityPtr: NativePointer): {
    stateRaw: number[]; effectType: number | null; name: string | null;
    source: number | null; active: boolean;
} | null {
    if (!effectComponentClass) return null;
    let ec: NativePointer | null = null;
    forEachComponent(effEntityPtr, (comp, klass) => {
        if (klass.equals(effectComponentClass)) ec = comp;
    });
    if (!ec) return null;
    const c = ec as NativePointer;
    const base = c.add(abilityStateOff);
    const stateRaw: number[] = [];
    for (let i = 0; i < 10; i++) {
        try { stateRaw.push(base.add(i * 4).readS32()); } catch { break; }
    }
    let effectType: number | null = null;
    let source: number | null = null;
    let active = true;
    try { effectType = c.add(EC.effectType).readS32(); } catch { /* */ }
    try { source = c.add(EC.sourceUnitId).readS32(); } catch { /* */ }
    try { active = c.add(EC.isActive).readU8() !== 0; } catch { /* */ }
    const name = (effectType !== null)
        ? (EFFECT_TYPE_NAMES[effectType] ?? null) : null;
    return { stateRaw, effectType, name, source, active };
}

/** Index every Effect entity (Type=3) → its decoded EffectComponent. One pass. */
function indexEffects(statePtr: NativePointer): Map<number, Decoded> {
    const m = new Map<number, Decoded>();
    forEachEntity(statePtr, (e, id, ty) => {
        if (ty !== EntityType.Effect) return;
        const info = readEffect(e);
        if (info) m.set(id, info);
    });
    return m;
}

/** Read a unit's owned-effect ids from EffectsOwnedComponent.ActiveEffectIds.
 * List<BEntityId> — value type, 4B inline elements; _items @0x10, _size @0x18,
 * backing array length @0x18, elements from @0x20 (stride 4). */
function readOwnedEffectIds(unitPtr: NativePointer): number[] {
    if (!effectsOwnedComponentClass) return [];
    let eoc: NativePointer | null = null;
    forEachComponent(unitPtr, (comp, klass) => {
        if (klass.equals(effectsOwnedComponentClass)) eoc = comp;
    });
    if (!eoc) return [];
    let list: NativePointer;
    try { list = (eoc as NativePointer).add(activeEffectIdsOff).readPointer(); }
    catch { return []; }
    if (list.isNull()) return [];
    let size: number;
    try { size = list.add(0x18).readS32(); } catch { return []; }
    if (size <= 0 || size > 128) return [];
    let items: NativePointer;
    try { items = list.add(0x10).readPointer(); } catch { return []; }
    if (items.isNull()) return [];
    const out: number[] = [];
    for (let i = 0; i < size; i++) {
        try { out.push(items.add(0x20 + i * 4).readS32()); } catch { break; }
    }
    return out;
}

/** Matérialise une entrée de charge utile depuis un effet décodé. */
function toInfo(eid: number, info: Decoded | undefined): EffectInfo {
    return {
        effectId: eid,
        name: info?.name ?? null,
        effectType: info?.effectType ?? null,
        remaining: info?.remaining ?? null,
        level: info?.level ?? null,
        source: info?.source ?? null,
        active: info?.active ?? true,
        removed: info?.removed ?? false,
        statMod: info?.statMod ?? null,
    };
}

export interface ReadEffectsOpts {
    /** Publier AUSSI les effets POSÉS mais dont l'`ActiveCondition` n'est pas
     *  satisfaite (`EffectComponent.IsActive == false`). Par défaut FAUX —
     *  comportement historique, que tous les consommateurs actuels supposent.
     *
     *  Sans ce drapeau, l'absence d'un effet dans la charge utile est AMBIGUË :
     *  non-posé ou posé-inactif ? C'est ce qui a forcé #127 à replier le gate
     *  d'activation de l'overwatch dans le `matches` du tir, faute de pouvoir
     *  distinguer les deux. Avec `includeInactive`, la distinction est LUE, et
     *  le repli peut se déplier à son vrai étage. Les effets RETIRÉS (`Removed`)
     *  restent filtrés dans les deux cas — ils ne sont plus là, point. */
    includeInactive?: boolean;
}

/** Map owner entityId (Type=1 squad / Type=6 machine — = decisionView unit/mow
 * id) → its effects (name + metadata + liveness + magnitude stat-mod). Reads the
 * game's own owned-effect list, mirroring exactly what the in-game UI renders as
 * status icons. */
export function readEffectsByUnit(
    statePtr: NativePointer, opts?: ReadEffectsOpts,
): Map<number, EffectInfo[]> {
    const includeInactive = opts?.includeInactive === true;
    const byId = indexEffects(statePtr);
    const out = new Map<number, EffectInfo[]>();
    forEachEntity(statePtr, (e, id, ty) => {
        if (ty !== EntityType.Unit && ty !== EntityType.Machine) return;
        const ids = readOwnedEffectIds(e);
        if (!ids.length) return;
        const effs: EffectInfo[] = [];
        for (const eid of ids) {
            const info = byId.get(eid);
            // Drop effects owned but NOT applying (inactive / removed) — e.g. an
            // aura whose target is currently out of range. Default-keep on a
            // read failure (active=true) so we never silently hide a real effect.
            if (info && info.removed) continue;
            if (info && !info.active && !includeInactive) continue;
            effs.push(toInfo(eid, info));
        }
        if (effs.length) out.set(id, effs);
    });
    return out;
}

/** Map TILE entityId (EntityType.Tile) → its active tile-status-effects
 * (name + metadata). A tile carries the SAME `EffectsOwnedComponent`
 * (ActiveEffectIds @0x10) as a unit — the AI's `TileEffectsUtility` reads
 * exactly this list (native leaf @1810fbe50: GetComponent(tile, EffectsOwned)
 * → List@+0x10 → resolve each to its Effect entity → EffectComponent.EffectType).
 * The effect NAME = EffectType enum ToString = the `Default.TileEffects.<Name>`
 * weight key (Fire/Ice/SpiderWeb/Thorns_DefenseReduction…). `source` is the
 * effect's owner (needed for GetStatusEffectMultiplier's friend/foe branch). */
export function readEffectsByTile(
    statePtr: NativePointer, opts?: ReadEffectsOpts,
): Map<number, EffectInfo[]> {
    const includeInactive = opts?.includeInactive === true;
    const byId = indexEffects(statePtr);
    const out = new Map<number, EffectInfo[]>();
    forEachEntity(statePtr, (e, id, ty) => {
        if (ty !== EntityType.Tile) return;
        const ids = readOwnedEffectIds(e);
        if (!ids.length) return;
        const effs: EffectInfo[] = [];
        for (const eid of ids) {
            const info = byId.get(eid);
            if (info && info.removed) continue;
            if (info && !info.active && !includeInactive) continue;
            effs.push(toInfo(eid, info));
        }
        if (effs.length) out.set(id, effs);
    });
    return out;
}

/** EffectType ids of the board-wide end-of-battle round-cap bombardment.
 * 1359 = EnvEndBombardment_Incoming (countdown telegraph) · 1360 =
 * EnvEndBombardment (the AoE nuke itself). These are NOT attached to any unit's
 * ActiveEffectIds (board/environment-owned), so readEffectsByUnit misses them —
 * the live cascade shows them, decisionView did not. cf. hypotheses.md H58. */
const ROUND_CAP_EFFECT_TYPES: ReadonlySet<number> = new Set([1359, 1360]);

export interface RoundCapClock {
    /** Effect name driving the soonest countdown (e.g. "EnvEndBombardment_Incoming"). */
    name: string | null;
    effectType: number;
    /** Soonest RemainingTurns across active round-cap effects (0 = firing this
     *  turn · null = present but turn count unreadable). */
    remaining: number | null;
    /** Active round-cap effect entities on the board (telegraph spread). */
    count: number;
}

/** Scan every Effect entity (Type=3) for the round-cap bombardment telegraph and
 * report the SOONEST RemainingTurns. Owner-agnostic (the board effect is not in
 * any unit's owned list) — the only reliable in-view round-cap clock. Returns
 * null when no round-cap effect is active. */
export function readRoundCapClock(statePtr: NativePointer): RoundCapClock | null {
    let name: string | null = null;
    let effectType = -1;
    let remaining: number | null = null;
    let found = false;
    let count = 0;
    forEachEntity(statePtr, (e, _id, ty) => {
        if (ty !== EntityType.Effect) return;
        const info = readEffect(e);
        if (!info || info.effectType === null) return;
        if (!ROUND_CAP_EFFECT_TYPES.has(info.effectType)) return;
        if (!info.active || info.removed) return;
        count++;
        // Keep the soonest concrete countdown (min remaining). A null remaining
        // never overrides a concrete one but seeds the result if it's the only signal.
        const isSooner = info.remaining !== null
            && (remaining === null || info.remaining < remaining);
        if (!found || isSooner) {
            found = true;
            name = info.name;
            effectType = info.effectType;
            if (info.remaining !== null) remaining = info.remaining;
        }
    });
    if (!found) return null;
    return { name, effectType, remaining, count };
}
