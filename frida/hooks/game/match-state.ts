// MatchState reader — entity enumeration, turn state, digest.
//
// Entity layout (base):
//   Id     @ 16 (Int32)
//   Type   @ 20 (Int32, EntityType enum)
//   Components @ 24 (array)
// UnitEntity.Owner @ 32 (OwnerComponent)
// MatchEntity.Component @ 32, MatchEntity.Turn @ 56 (TurnComponent)
// TurnComponent._currentPlayerId @ 36
// OwnerComponent.PlayerEntityId @ 16, _overridingPlayerEntityId @ 20
//
// MatchComponent (offset 32 on MatchEntity):
//   CurrentId @ 16
//   WinnerId  @ 20
//   CheatFinished @ 32 (u8)
//   Stage @ 36 (Int32: 0=Setup, 1=Running, 2=Finished)

import {
    field_get_type, findClass, findClassAnywhere, findMethod,
    getFieldInfo, getFieldOffset, readIl2cppString,
    type_get_class_or_element_class,
} from "../il2cpp/helpers.js";
import { invokeMethod } from "../il2cpp/invoke.js";
import { serializeToJson } from "../il2cpp/serializer.js";

export const matchStateClass = findClass(
    "BattleLogicAssembly.dll", "IdunBattle.Core", "MatchState");
if (!matchStateClass) throw new Error("MatchState class not found");

export const msEntitiesOff = getFieldOffset(matchStateClass, "_entities");

// ---- Component classes for projection. Resolved once at module load. ----

export const positionComponentClass = findClassAnywhere(
    "IdunBattle.Entities.Components", "PositionComponent");
const healthComponentClass = findClassAnywhere(
    "IdunBattle.Entities.Components", "HealthComponent");
// ArmorComponent extends FillUpStatComponent (same Maximum@0x14 / Remaining@0x18
// layout as HealthComponent) — StatType.Armor=4, the DEPLETABLE armor pool that
// PredictRepair @181038280 fills (distinct from FixedArmorComponent=16). Read for
// the repair magnitude ARMOR term (#83). Absent on unarmored units → armor stays null.
const armorComponentClass = findClassAnywhere(
    "IdunBattle.Entities.Components", "ArmorComponent");
const movementComponentClass = findClassAnywhere(
    "IdunBattle.Entities.Components", "MovementComponent");
const ownerComponentClass = findClassAnywhere(
    "IdunBattle.Entities.Components", "OwnerComponent");
const unitComponentClass = findClassAnywhere(
    "IdunBattle.Entities.Components", "UnitComponent");
const tileComponentClass = findClassAnywhere(
    "IdunBattle.Entities.Components", "TileComponent");
const machineComponentClass = findClassAnywhere(
    "IdunBattle.Entities.Components", "MachineComponent");
const machinePlatformComponentClass = findClassAnywhere(
    "IdunBattle.Entities.Components", "MachinePlatformComponent");

/** Component field offsets, all relative to the component object base.
 * `PositionComponent.Coordinate` is an inline `AxialCoordinate` struct at
 * +0x10 → Column at +0x10, Row at +0x14. `HealthComponent` extends
 * `FillUpStatComponent` whose mutable values start at +0x10 (InitialValue),
 * +0x14 (MaximumValue), +0x18 (RemainingValue). `OwnerComponent.PlayerEntityId`
 * is at +0x10 (a 4B BEntityId).
 * `UnitComponent.VisualId` is a managed string at +0x20, `UnitComponent.Rank`
 * an Int32 at +0x1a4 (validated via runtime field-offset diag). */
const COMP_FIELD = {
    posCol: 0x10,
    posRow: 0x14,
    hpMax: 0x14,
    hpRemaining: 0x18,
    ownerPlayerId: 0x10,
    visualId: 0x20,
    rank: 0x1a4,
    // TileComponent layout (TypeDefIndex 11694) :
    //   Id (string) @0x10, Elevation @0x18, IsTemporary @0x2C,
    //   IsBossPlatform @0x2D, IsTerritoryTile @0x2E, IsInFogOfWar @0x40,
    //   IsWall @0x41, RoomTileType (int enum) @0x44
    tileId: 0x10,
    tileElevation: 0x18,
    tileIsTemporary: 0x2c,
    tileIsBossPlatform: 0x2d,
    tileIsTerritory: 0x2e,
    tileIsInFog: 0x40,
    tileIsWall: 0x41,
    tileRoomType: 0x44,
    // MachineComponent : Position (enum None/Top/Bottom) @0x78
    machinePosition: 0x78,
    // MachinePlatformComponent : Position (enum int) @0x10, Nullable<BEntityId>
    // MachineId @0x14. Mono Nullable<T> layout : hasValue @+0 (1B + padding),
    // value @+4. Confirme via Nullable<Level> dans normalize-bc/formula.ts.
    // Donc hasValue @0x14, value @0x18.
    platformPosition: 0x10,
    platformMachineIdHasValue: 0x14,
    platformMachineIdValue: 0x18,
} as const;

/** IL2CPP EntityType enum. */
export const EntityType = {
    Tile: 0,
    Unit: 1,
    Match: 2,
    Effect: 3,
    Player: 4,
    UnitFoot: 5,
    Machine: 6,
    MachinePlatform: 7,
    EnvironmentAbility: 8,
} as const;

export const STAGE_NAMES: Record<number, string> = {
    0: "Setup",
    1: "Running",
    2: "Finished",
};

/** Iterate over entities in a MatchState. Yields [entityPtr, id, type]. */
export function forEachEntity(
    statePtr: NativePointer,
    cb: (entityPtr: NativePointer, id: number, type: number) => void,
): void {
    const list = statePtr.add(msEntitiesOff).readPointer();
    if (list.isNull()) return;
    const size = list.add(0x18).readS32();
    const items = list.add(0x10).readPointer();
    for (let k = 0; k < size; k++) {
        const e = items.add(0x20 + k * 8).readPointer();
        if (e.isNull()) continue;
        cb(e, e.add(16).readS32(), e.add(20).readS32());
    }
}

/** Current player taking a turn, from TurnComponent on MatchEntity. */
export function readTurnPlayer(statePtr: NativePointer): number | null {
    let result: number | null = null;
    forEachEntity(statePtr, (e, _id, ty) => {
        if (result !== null) return;
        if (ty === EntityType.Match) {
            const tc = e.add(56).readPointer();
            if (!tc.isNull()) result = tc.add(36).readS32();
        }
    });
    return result;
}

const turnComponentClass = findClassAnywhere(
    "IdunBattle.Entities.Components", "TurnComponent");
const getTurnsStartedByCurrentPlayerMi = turnComponentClass
    ? findMethod(turnComponentClass, "GetAmountOfTurnsStartedByCurrentPlayer")
    : null;

/** Combined `{ player, round }` read in a single MatchState scan. `round` =
 * the count returned by `TurnComponent.GetAmountOfTurnsStartedByCurrentPlayer`,
 * i.e. the Nth turn for the player currently on turn. In a 1v1 match where
 * both players have started 3 turns, `round = 3` regardless of who's
 * currently active. */
export function readTurnInfo(
    statePtr: NativePointer,
): { player: number | null; round: number | null } {
    const out: { player: number | null; round: number | null } =
        { player: null, round: null };
    forEachEntity(statePtr, (e, _id, ty) => {
        if (out.player !== null) return;
        if (ty !== EntityType.Match) return;
        const tc = e.add(56).readPointer();
        if (tc.isNull()) return;
        out.player = tc.add(36).readS32();
        if (getTurnsStartedByCurrentPlayerMi
            && !getTurnsStartedByCurrentPlayerMi.ptr.isNull()) {
            try {
                // il2cpp_runtime_invoke boxes value-type returns. The actual
                // int sits at offset 0x10 of the boxed System.Int32 object
                // (header @ 0x0/0x8, then the unboxed value).
                const r = invokeMethod(
                    getTurnsStartedByCurrentPlayerMi.info, tc, null);
                if (!r.isNull()) out.round = r.add(0x10).readS32();
            } catch { /* leave round null */ }
        }
    });
    return out;
}

export interface BattleStatus {
    stage: number | null;
    stageName: string | null;
    winner: number | null;
    currentTurnPlayer: number | null;
    cheatFinished: boolean | null;
    unitsAlive: number;
}

/** Read battle top-level status — Stage, winner, currentPlayer, unitsAlive. */
export function readBattleStatus(statePtr: NativePointer): BattleStatus {
    const out: BattleStatus = {
        stage: null, stageName: null, winner: null,
        currentTurnPlayer: null, cheatFinished: null, unitsAlive: 0,
    };
    forEachEntity(statePtr, (e, _id, ty) => {
        if (ty === EntityType.Match) {
            const mc = e.add(32).readPointer();
            if (!mc.isNull()) {
                out.stage = mc.add(36).readS32();
                out.stageName = STAGE_NAMES[out.stage] ?? ("?" + out.stage);
                out.winner = mc.add(20).readS32();
                out.cheatFinished = mc.add(32).readU8() !== 0;
            }
            const tc = e.add(56).readPointer();
            if (!tc.isNull()) out.currentTurnPlayer = tc.add(36).readS32();
        } else if (ty === EntityType.Unit) {
            out.unitsAlive++;
        }
    });
    return out;
}

export interface Census {
    total: number;
    byType: Record<number, number[]>;
}

/** Count + enumerate entity IDs grouped by EntityType — for state diff. */
export function entityCensus(statePtr: NativePointer): Census {
    const list = statePtr.add(msEntitiesOff).readPointer();
    if (list.isNull()) return { total: 0, byType: {} };
    const size = list.add(0x18).readS32();
    const items = list.add(0x10).readPointer();
    const byType: Record<number, number[]> = {};
    for (let k = 0; k < size; k++) {
        const e = items.add(0x20 + k * 8).readPointer();
        if (e.isNull()) continue;
        const id = e.add(16).readS32();
        const ty = e.add(20).readS32();
        (byType[ty] ??= []).push(id);
    }
    for (const t in byType) byType[t].sort((a, b) => a - b);
    return { total: size, byType };
}

export interface StateDigest {
    bytes: number;
    digest: string;  // "0xNNNNNNNN" — fnv-1a of the JSON bytes
}

/** Serialize via Newtonsoft + fnv-1a digest, for cheap state comparison. */
export function digestState(statePtr: NativePointer): StateDigest | null {
    const str = serializeToJson(statePtr);
    if (!str) return null;
    let h = 2166136261 >>> 0;
    for (let i = 0; i < str.length; i++) {
        h = Math.imul(h ^ (str.charCodeAt(i) & 0xff), 16777619) >>> 0;
    }
    return { bytes: str.length, digest: "0x" + h.toString(16) };
}

// ---- State projection (for the front-end mirror panel) ----

export interface UnitProjection {
    id: number;
    /** Parent squad entity ID (Type=1). Carried for traceability — the
     * actual visual identity (visualId/rank) is denormalized onto each
     * UnitFoot below so the front renders without extra lookups. */
    squadId: number;
    entityType: number;
    pos: { col: number; row: number } | null;
    hp: number | null;
    maxHp: number | null;
    /** Depletable armor pool (ArmorComponent, StatType.Armor=4). null if
     * unarmored. Feeds the repair ARMOR term (#83). */
    armor: number | null;
    armorMax: number | null;
    ownerId: number | null;
    /** TeamId enum value (1, 2, 3) read from the player's PlayerComponent.
     * Lets the front color units by team without a config-side mapping. */
    teamId: number | null;
    /** Squad's `UnitComponent.VisualId` — drives portrait lookup on the
     * front via `configIdToPortrait` + `manifest.units`. */
    visualId: string | null;
    /** Squad's `UnitComponent.Rank` — drives the rank-badge overlay. */
    rank: number | null;
    isDead: boolean;
}

export interface MowProjection {
    /** MachinePlatform entityId — analog of UnitFoot.id. */
    id: number;
    /** Parent Machine entityId — analog of UnitFoot.squadId. Carries HP/Owner. */
    machineId: number;
    /** ALIAS de `machineId` : l'entite qui CASTE. Existe parce que le piege s'est
     *  referme (2026-07-27) -- prendre `id` comme casterId fait refuser TOUT cast par
     *  `TargetIsEnemy`, et le symptome (« faux refus » du gate de ciblage) ne designe
     *  pas sa cause. `id` est la PLATEFORME d'ancrage, jamais l'acteur. */
    casterId: number;
    entityType: number;
    /** Position of THIS platform on the grid. A MoW spans multiple
     * platforms (each on its own tile). */
    pos: { col: number; row: number } | null;
    hp: number | null;
    maxHp: number | null;
    ownerId: number | null;
    teamId: number | null;
    visualId: string | null;
    rank: number | null;
    isDead: boolean;
    /** Initial deployment slot from MachineComponent.Position enum
     * (0=None, 1=Top, 2=Bottom). NB: dynamic spawns can have None. */
    initialSlot: number | null;
    /** #287-r14-r2 — TOUTES les entités `MachinePlatform` (Type=7) liées à cette machine,
     *  triées, pas seulement l'ancre publiée sous `id`. C'est le SEUL substrat de
     *  `IdunBattle.Entities.TileExtensions$$GetMachinePlatformContent`, la branche
     *  `EntityType == 7` d'`IdunBattle.Entities.UnitExtensions$$GetMachine` : le port ne peut
     *  résoudre `plateforme -> machine` que s'il connaît la liste ENTIÈRE.
     *
     *  MESURE qui l'impose (2026-08-14, runner `orksRukkatrukk` sur `MC1_67`,
     *  `dumpEntityComponents` sur les ids 60..99) : la MoW porte **DEUX** plateformes (75, 76),
     *  `id` n'en publiait qu'UNE (76). Porter la moitié du mapping ferait réussir la résolution
     *  sur une plateforme et échouer sur l'autre, en silence.
     *
     *  ⚠ Ces entités ne portent QU'UN `MachinePlatformComponent` — ni `PositionComponent` ni
     *  `TileComponent` (mesuré) : c'est pourquoi `pos` est `null` et pourquoi il n'existe PAS de
     *  voie « tuile -> machine ». `null` = pas mesuré, `[]` = mesuré et aucune plateforme liée. */
    platformIds: number[] | null;
}

export interface TileProjection {
    id: number;
    col: number;
    row: number;
    /** TileComponent.Id (string) — terrain prototype identifier
     * (e.g., "RoomTile_Normal_01", "RoomTile_Wall_02"). */
    tileDefId: string | null;
    elevation: number;
    isWall: boolean;
    isTemporary: boolean;
    isBossPlatform: boolean;
    isTerritory: boolean;
    isInFog: boolean;
    /** RoomTileType enum: 0=Floor, 1=Wall, 2=Door. */
    roomTileType: number;
}

export interface MatchStateProjection {
    turn: number | null;
    playerOnTurn: number | null;
    stage: number | null;
    stageName: string | null;
    units: UnitProjection[];
    /** MoW projection — 1 row per MachinePlatform (analog of UnitFoot).
     * Always projected (cheap, important for RL state). */
    mows?: MowProjection[];
    /** Tile snapshot — only populated when `includeTiles` is passed. */
    tiles?: TileProjection[];
}

export const unitFootComponentClass = findClassAnywhere(
    "IdunBattle.Entities.Components", "UnitFootComponent");
const tileContentComponentClass = findClassAnywhere(
    "IdunBattle.Entities.Components", "TileContentComponent");
/** Exportée (#311) : `rpc-board` lit `PlayerComponent.TeamId` pour étiqueter les
 *  positions de machine de guerre rendues par `BattleQuery$$GetPositionMachineForPlayer`. */
export const playerComponentClass = findClassAnywhere(
    "IdunBattle.Entities.Components", "PlayerComponent");

/** UnitFootComponent layout — UnitId @ +0x10, TileId @ +0x14 (both 4B). */
const UNITFOOT_UNIT_ID_OFF = 0x10;
const UNITFOOT_TILE_ID_OFF = 0x14;
/** PlayerComponent.TeamId @ +0x24 (Int32 TeamId enum: 0=None, 1, 2, 3). */
const PLAYER_TEAM_ID_OFF = 0x24;

/** Walk an entity's `Components` IComponent[] (offset 0x18) and yield each
 * `(componentPtr, klassPtr)` pair. Defensive against malformed arrays. */
export function forEachComponent(
    entityPtr: NativePointer,
    cb: (componentPtr: NativePointer, klassPtr: NativePointer) => void,
): void {
    let arr: NativePointer;
    try { arr = entityPtr.add(0x18).readPointer(); }
    catch { return; }
    if (arr.isNull()) return;
    let length: number;
    try { length = arr.add(0x18).readS32(); }
    catch { return; }
    if (length <= 0 || length > 200) return;
    for (let i = 0; i < length; i++) {
        let comp: NativePointer;
        try { comp = arr.add(0x20 + i * Process.pointerSize).readPointer(); }
        catch { continue; }
        if (comp.isNull()) continue;
        let klass: NativePointer;
        try { klass = comp.readPointer(); }
        catch { continue; }
        if (klass.isNull()) continue;
        cb(comp, klass);
    }
}

// ---- Death metadata (#185 BlessingsOfKhorne) ----
// `UnitComponent.DefeatedByMeleeAttack` (bool) = LE byte que le sélecteur natif
// `UnitsDefeatedByMeleeAttackSelector.IsValidUnit @180f00b40` lit en gate primaire
// (comp+0x178 sur gqfc5mff6c, confirmé par dumpUnitComp live) ; écrit par
// `KillUnitOperation.Execute @180e76470` (param wasMelee). `UnitComponent.DeathReason`
// = Nullable<DamageSource> (comp+0x108 live) ; killer = `DamageSource.get_KillerId
// @180e65a10` (override Nullable<int>@+0xc si non-zéro, sinon id@+0 — on INVOQUE le
// getter natif plutôt que transcrire ses offsets internes). Offsets composant RÉSOLUS
// PAR NOM au chargement (getFieldOffset) — zéro hardcode. Nullable<T> layout
// (convention build validée, cf. COMP_FIELD platformMachineId) : hasValue @+0,
// value aligné (@+8 pour DamageSource, align 8).
const ucDefeatedByMeleeOff = unitComponentClass
    ? getFieldOffset(unitComponentClass, "DefeatedByMeleeAttack") : -1;
const ucDeathReasonOff = unitComponentClass
    ? getFieldOffset(unitComponentClass, "DeathReason") : -1;
const damageSourceClass = findClassAnywhere("IdunBattle.Operations", "DamageSource");
const getKillerIdMi = damageSourceClass
    ? findMethod(damageSourceClass, "get_KillerId") : null;
// Layout INTERNE du Nullable<DamageSource> résolu PAR RÉFLEXION (pas de convention
// supposée) : field DeathReason → type → classe Nullable`1 → offsets hasValue/value.
// ⚠ il2cpp_field_get_offset sur un VALUE TYPE renvoie l'offset BOXÉ (header 0x10
// inclus, cf. il2cpp/project.ts) → soustraire 0x10 pour l'offset inline.
const drNullableClass = (() => {
    if (!unitComponentClass) return null;
    const f = getFieldInfo(unitComponentClass, "DeathReason");
    if (!f) return null;
    try {
        const t = field_get_type(f) as NativePointer;
        const k = type_get_class_or_element_class(t) as NativePointer;
        return k.isNull() ? null : k;
    } catch { return null; }
})();
const drHasValueOff = drNullableClass
    ? getFieldOffset(drNullableClass, "hasValue") - 0x10 : -1;
const drValueOff = drNullableClass
    ? getFieldOffset(drNullableClass, "value") - 0x10 : -1;
// get_KillerId : appel DIRECT de l'entry native (ABI : DamageSource* this,
// MethodInfo* = 0 — mirror exact du call-site natif `get_KillerId(&local_2b8, 0)`
// dans UnitKillerSelector.Select @180eff680). PAS runtime_invoke : il UNBOXE
// (+0x10) l'instance des value-types → un ptr brut serait décalé.
// `propagate` : appel MANAGE, cf. `il2cpp/invoke.ts`.
const getKillerIdFn = getKillerIdMi
    ? new NativeFunction(getKillerIdMi.ptr, "int32", ["pointer", "pointer"],
                         { exceptions: "propagate" })
    : null;

export interface UnitDeathMeta {
    /** Tué par une attaque de MÊLÉE — source du multiplicateur BlessingsOfKhorne
     * (`GetMultiplierBasedOnDefeatedInMelee @180f34ea0`). */
    defeatedByMelee: boolean;
    /** EntityId du tueur (`DamageSource.KillerId`), null si pas mort / inconnu.
     * Consommé par la branche TalismanOfRage (1460) du multiplicateur. */
    killerId: number | null;
}

/** Lit le death-meta du SQUAD (EntityType.Unit) — fiable aussi sur les CORPSES
 * (le squad garde son UnitComponent après la mort, contrairement au UnitFoot). */
export function readUnitDeathMeta(entityPtr: NativePointer): UnitDeathMeta {
    const out: UnitDeathMeta = { defeatedByMelee: false, killerId: null };
    if (!unitComponentClass) return out;
    try {
        forEachComponent(entityPtr, (comp, klass) => {
            if (!klass.equals(unitComponentClass)) return;
            if (ucDefeatedByMeleeOff > 0) {
                out.defeatedByMelee =
                    comp.add(ucDefeatedByMeleeOff).readU8() !== 0;
            }
            if (ucDeathReasonOff > 0 && getKillerIdFn
                && drHasValueOff >= 0 && drValueOff >= 0
                && comp.add(ucDeathReasonOff + drHasValueOff).readU8() !== 0) {
                try {
                    const kid = getKillerIdFn(
                        comp.add(ucDeathReasonOff + drValueOff), NULL) as number;
                    out.killerId = kid > 0 ? kid : null;
                } catch { /* killerId stays null */ }
            }
        });
    } catch { /* defaults */ }
    return out;
}

interface SquadStats {
    hp: number | null;
    maxHp: number | null;
    /** ArmorComponent RemainingValue/MaximumValue (StatType.Armor=4). null on
     * unarmored units (no ArmorComponent). Feeds the repair ARMOR term (#83). */
    armor: number | null;
    armorMax: number | null;
    ownerId: number | null;
    visualId: string | null;
    rank: number | null;
    isDead: boolean;
}

/** Read squad-level HP + Owner + Visual identity. Squads (EntityType.Unit)
 * carry HP/Owner/VisualId/Rank but no position — the visible position comes
 * from each squad member (UnitFoot/Machine), each with its own
 * PositionComponent. */
function projectSquadStats(entityPtr: NativePointer): SquadStats {
    const out: SquadStats = {
        hp: null, maxHp: null, armor: null, armorMax: null, ownerId: null,
        visualId: null, rank: null, isDead: false,
    };
    try {
        forEachComponent(entityPtr, (comp, klass) => {
            if (healthComponentClass && klass.equals(healthComponentClass)) {
                out.hp = comp.add(COMP_FIELD.hpRemaining).readS32();
                out.maxHp = comp.add(COMP_FIELD.hpMax).readS32();
            } else if (armorComponentClass && klass.equals(armorComponentClass)) {
                // Same FillUpStatComponent layout: Remaining@0x18, Maximum@0x14.
                out.armor = comp.add(COMP_FIELD.hpRemaining).readS32();
                out.armorMax = comp.add(COMP_FIELD.hpMax).readS32();
            } else if (ownerComponentClass && klass.equals(ownerComponentClass)) {
                out.ownerId = comp.add(COMP_FIELD.ownerPlayerId).readS32();
            } else if (unitComponentClass && klass.equals(unitComponentClass)) {
                try {
                    const strPtr = comp.add(COMP_FIELD.visualId).readPointer();
                    out.visualId = readIl2cppString(strPtr);
                } catch { /* visualId stays null */ }
                try {
                    out.rank = comp.add(COMP_FIELD.rank).readS32();
                } catch { /* rank stays null */ }
            } else if (machineComponentClass
                && klass.equals(machineComponentClass)) {
                // MoW entities (Type=6) carry MachineComponent, NOT
                // UnitComponent — but both extend BaseUnitComponent, so
                // VisualId@0x20 is valid. Rank (0x1A4) is UnitComponent-only,
                // so we don't read it here (would be OOB on MachineComponent).
                // NB: a MoW machine has no HealthComponent / PositionComponent
                // (verified via dumpEntityComponents) — hp/pos stay null by
                // design; its board position is config-derived from the slot
                // (MachineComponent.Position, exposed as `initialSlot`).
                try {
                    const strPtr = comp.add(COMP_FIELD.visualId).readPointer();
                    out.visualId = readIl2cppString(strPtr);
                } catch { /* visualId stays null */ }
            }
            void movementComponentClass;
        });
        if (out.hp !== null && out.hp <= 0) out.isDead = true;
    } catch { /* return defaults */ }
    return out;
}

/** Read MachineComponent on a Machine entity → initial slot (Top/Bottom/None). */
function readMachineSlot(entityPtr: NativePointer): number | null {
    let slot: number | null = null;
    try {
        forEachComponent(entityPtr, (comp, klass) => {
            if (machineComponentClass && klass.equals(machineComponentClass)) {
                slot = comp.add(COMP_FIELD.machinePosition).readS32();
            }
        });
    } catch { return null; }
    return slot;
}

/** Read MachinePlatformComponent → linked Machine entityId (Nullable). */
function readMachinePlatformLink(entityPtr: NativePointer): {
    machineId: number;
} | null {
    let machineId: number | null = null;
    try {
        forEachComponent(entityPtr, (comp, klass) => {
            if (machinePlatformComponentClass
                && klass.equals(machinePlatformComponentClass)) {
                const hasValue = comp.add(COMP_FIELD.platformMachineIdHasValue)
                    .readU8() !== 0;
                if (hasValue) {
                    machineId = comp.add(COMP_FIELD.platformMachineIdValue)
                        .readS32();
                }
            }
        });
    } catch { return null; }
    if (machineId === null) return null;
    return { machineId };
}

/** Read UnitFootComponent on a UnitFoot entity → (unitId, tileId). */
function readUnitFootLink(entityPtr: NativePointer): {
    unitId: number; tileId: number;
} | null {
    let unitId: number | null = null;
    let tileId: number | null = null;
    try {
        forEachComponent(entityPtr, (comp, klass) => {
            if (unitFootComponentClass
                && klass.equals(unitFootComponentClass)) {
                unitId = comp.add(UNITFOOT_UNIT_ID_OFF).readS32();
                tileId = comp.add(UNITFOOT_TILE_ID_OFF).readS32();
            }
        });
    } catch { return null; }
    if (unitId === null || tileId === null) return null;
    return { unitId, tileId };
}

/** Project a Tile entity → static terrain attributes for tile_ref table.
 * Combines TileComponent (terrain props) + PositionComponent (col/row). */
function projectTile(
    entityPtr: NativePointer, id: number,
): TileProjection | null {
    let col: number | null = null;
    let row: number | null = null;
    let tileDefId: string | null = null;
    let elevation = 0;
    let isWall = false;
    let isTemporary = false;
    let isBossPlatform = false;
    let isTerritory = false;
    let isInFog = false;
    let roomTileType = 0;
    try {
        forEachComponent(entityPtr, (comp, klass) => {
            if (positionComponentClass && klass.equals(positionComponentClass)) {
                col = comp.add(COMP_FIELD.posCol).readS32();
                row = comp.add(COMP_FIELD.posRow).readS32();
            } else if (tileComponentClass && klass.equals(tileComponentClass)) {
                try {
                    const strPtr = comp.add(COMP_FIELD.tileId).readPointer();
                    tileDefId = readIl2cppString(strPtr);
                } catch { /* leave null */ }
                elevation = comp.add(COMP_FIELD.tileElevation).readS32();
                isTemporary = comp.add(COMP_FIELD.tileIsTemporary).readU8() !== 0;
                isBossPlatform = comp.add(COMP_FIELD.tileIsBossPlatform).readU8() !== 0;
                isTerritory = comp.add(COMP_FIELD.tileIsTerritory).readU8() !== 0;
                isInFog = comp.add(COMP_FIELD.tileIsInFog).readU8() !== 0;
                isWall = comp.add(COMP_FIELD.tileIsWall).readU8() !== 0;
                roomTileType = comp.add(COMP_FIELD.tileRoomType).readS32();
            }
        });
    } catch { return null; }
    if (col === null || row === null) return null;
    return {
        id, col, row, tileDefId, elevation, isWall, isTemporary,
        isBossPlatform, isTerritory, isInFog, roomTileType,
    };
}

/** Read PositionComponent on a Tile entity → (col, row). */
export function readTilePosition(
    entityPtr: NativePointer,
): { col: number; row: number } | null {
    let pos: { col: number; row: number } | null = null;
    try {
        forEachComponent(entityPtr, (comp, klass) => {
            if (positionComponentClass && klass.equals(positionComponentClass)) {
                pos = {
                    col: comp.add(COMP_FIELD.posCol).readS32(),
                    row: comp.add(COMP_FIELD.posRow).readS32(),
                };
            }
        });
    } catch { return null; }
    return pos;
}

/** Project a MatchState into a JSON-friendly snapshot for rendering.
 * Tacticus model:
 *   - EntityType.Unit (squad) carries HP/Owner but no position
 *   - EntityType.UnitFoot is each visible piece on the board. Its
 *     UnitFootComponent holds (unitId, tileId). Position lives on the Tile.
 *   - EntityType.Tile carries PositionComponent (col/row).
 * We project one entry per visible piece, walking UnitFoot → Tile for
 * pos and UnitFoot → Unit for HP/Owner. */
export function projectMatchState(
    statePtr: NativePointer,
    opts: { includeTiles?: boolean } = {},
): MatchStateProjection {
    const status = readBattleStatus(statePtr);

    // Single pass — build entityById index, squad stats, player→team map.
    // If includeTiles is set, also project all Tile entities up-front.
    const entityById = new Map<number, NativePointer>();
    const squads = new Map<number, SquadStats>();
    // Machine entities use the same BaseUnitComponent layout as Squad —
    // we reuse projectSquadStats() and key by machine entityId.
    const machines = new Map<number,
        SquadStats & { initialSlot: number | null }>();
    const playerTeams = new Map<number, number>();
    const tiles: TileProjection[] = [];
    forEachEntity(statePtr, (e, id, ty) => {
        entityById.set(id, e);
        if (ty === EntityType.Unit) {
            squads.set(id, projectSquadStats(e));
        } else if (ty === EntityType.Machine) {
            machines.set(id, {
                ...projectSquadStats(e),
                initialSlot: readMachineSlot(e),
            });
        } else if (ty === EntityType.Player) {
            try {
                forEachComponent(e, (comp, klass) => {
                    if (playerComponentClass
                        && klass.equals(playerComponentClass)) {
                        playerTeams.set(id,
                            comp.add(PLAYER_TEAM_ID_OFF).readS32());
                    }
                });
            } catch { /* skip */ }
        } else if (ty === EntityType.Tile && opts.includeTiles) {
            const t = projectTile(e, id);
            if (t) tiles.push(t);
        }
    });

    // For each UnitFoot — read (unitId, tileId), look up tile for pos,
    // squad for HP/Owner.
    const units: UnitProjection[] = [];
    forEachEntity(statePtr, (e, id, ty) => {
        if (ty !== EntityType.UnitFoot) return;
        const link = readUnitFootLink(e);
        if (!link) return;
        const tilePtr = entityById.get(link.tileId);
        const pos = tilePtr ? readTilePosition(tilePtr) : null;
        if (!pos) return;
        const parent = squads.get(link.unitId);
        const teamId = parent?.ownerId !== null && parent?.ownerId !== undefined
            ? (playerTeams.get(parent.ownerId) ?? null) : null;
        units.push({
            id, squadId: link.unitId, entityType: ty,
            pos,
            hp: parent?.hp ?? null,
            maxHp: parent?.maxHp ?? null,
            armor: parent?.armor ?? null,
            armorMax: parent?.armorMax ?? null,
            ownerId: parent?.ownerId ?? null,
            teamId,
            visualId: parent?.visualId ?? null,
            rank: parent?.rank ?? null,
            isDead: parent?.isDead ?? false,
        });
    });
    units.sort((a, b) => a.id - b.id);

    // MoW projection. Source of truth = Machine entities (Type=6), which
    // carry HP/Owner/Visual via the same BaseUnitComponent layout as squads.
    // A Machine's board position lives on its linked MachinePlatform (Type=7),
    // bound by AddMachineOperation.Execute through
    // MachinePlatformComponent.MachineId (Nullable<BEntityId> @+0x14 hasValue,
    // +0x18 value — confirmed in Ghidra). We build the reverse map
    // platform→machine, then emit ONE row PER MACHINE so a deployed MoW is
    // always visible — even if its platform's PositionComponent can't be read.
    // (Deployment correctness is `machines.size`, not platform linkage: the
    // old code dropped the whole row on a null platform position, hiding MoWs
    // that were in fact deployed. See AddMachineOperation$$Execute RE.)
    const platformByMachine = new Map<number,
        { platformId: number; pos: { col: number; row: number } | null }>();
    // #287-r14-r2 — la liste ENTIÈRE des plateformes par machine, à côté de l'ancre.
    // L'ancre seule ne suffit pas à porter `GetMachinePlatformContent` : mesuré, une MoW en
    // porte DEUX et `id` n'en publiait qu'une (cf. le commentaire de `platformIds`).
    const allPlatformsByMachine = new Map<number, number[]>();
    forEachEntity(statePtr, (e, id, ty) => {
        if (ty !== EntityType.MachinePlatform) return;
        const link = readMachinePlatformLink(e);
        if (!link) return;
        // A MoW spans several platforms — keep the first as anchor position.
        if (!platformByMachine.has(link.machineId)) {
            platformByMachine.set(link.machineId, {
                platformId: id, pos: readTilePosition(e),
            });
        }
        const lst = allPlatformsByMachine.get(link.machineId) ?? [];
        lst.push(id);
        allPlatformsByMachine.set(link.machineId, lst);
    });
    const mows: MowProjection[] = [];
    for (const [machineId, m] of machines) {
        const plat = platformByMachine.get(machineId);
        const teamId = m.ownerId !== null && m.ownerId !== undefined
            ? (playerTeams.get(m.ownerId) ?? null) : null;
        mows.push({
            // `id` = anchor platform entityId when linked, else the machine
            // entityId (keeps rows distinct + traceable either way).
            id: plat?.platformId ?? machineId,
            machineId,
            casterId: machineId,
            entityType: EntityType.Machine,
            pos: plat?.pos ?? null,
            hp: m.hp,
            maxHp: m.maxHp,
            ownerId: m.ownerId,
            teamId,
            visualId: m.visualId,
            rank: m.rank,
            isDead: m.isDead,
            initialSlot: m.initialSlot,
            // #287-r14-r2 — `[]` (mesuré, aucune plateforme liée) et non `null` : la passe
            // ci-dessus a bien tourné sur TOUTES les entités. `null` resterait réservé à une
            // non-mesure, qui n'existe pas ici.
            platformIds: (allPlatformsByMachine.get(machineId) ?? []).slice().sort((a, b) => a - b),
        });
    }
    mows.sort((a, b) => a.id - b.id);

    const out: MatchStateProjection = {
        turn: status.currentTurnPlayer,
        playerOnTurn: status.currentTurnPlayer,
        stage: status.stage,
        stageName: status.stageName,
        units,
    };
    if (mows.length > 0) {
        out.mows = mows;
    }
    if (opts.includeTiles) {
        tiles.sort((a, b) => a.id - b.id);
        out.tiles = tiles;
    }
    return out;
}

