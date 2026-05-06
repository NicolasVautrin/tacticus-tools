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
    findClass, findClassAnywhere, getFieldOffset, readIl2cppString,
} from "../il2cpp/helpers.js";
import { serializeToJson } from "../il2cpp/serializer.js";

export const matchStateClass = findClass(
    "BattleLogicAssembly.dll", "IdunBattle.Core", "MatchState");
if (!matchStateClass) throw new Error("MatchState class not found");

export const msEntitiesOff = getFieldOffset(matchStateClass, "_entities");

// ---- Component classes for projection. Resolved once at module load. ----

const positionComponentClass = findClassAnywhere(
    "IdunBattle.Entities.Components", "PositionComponent");
const healthComponentClass = findClassAnywhere(
    "IdunBattle.Entities.Components", "HealthComponent");
const movementComponentClass = findClassAnywhere(
    "IdunBattle.Entities.Components", "MovementComponent");
const ownerComponentClass = findClassAnywhere(
    "IdunBattle.Entities.Components", "OwnerComponent");
const unitComponentClass = findClassAnywhere(
    "IdunBattle.Entities.Components", "UnitComponent");

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

export interface MatchStateProjection {
    turn: number | null;
    playerOnTurn: number | null;
    stage: number | null;
    stageName: string | null;
    units: UnitProjection[];
}

const unitFootComponentClass = findClassAnywhere(
    "IdunBattle.Entities.Components", "UnitFootComponent");
const tileContentComponentClass = findClassAnywhere(
    "IdunBattle.Entities.Components", "TileContentComponent");
const playerComponentClass = findClassAnywhere(
    "IdunBattle.Entities.Components", "PlayerComponent");

/** UnitFootComponent layout — UnitId @ +0x10, TileId @ +0x14 (both 4B). */
const UNITFOOT_UNIT_ID_OFF = 0x10;
const UNITFOOT_TILE_ID_OFF = 0x14;
/** PlayerComponent.TeamId @ +0x24 (Int32 TeamId enum: 0=None, 1, 2, 3). */
const PLAYER_TEAM_ID_OFF = 0x24;

/** Walk an entity's `Components` IComponent[] (offset 0x18) and yield each
 * `(componentPtr, klassPtr)` pair. Defensive against malformed arrays. */
function forEachComponent(
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

interface SquadStats {
    hp: number | null;
    maxHp: number | null;
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
        hp: null, maxHp: null, ownerId: null,
        visualId: null, rank: null, isDead: false,
    };
    try {
        forEachComponent(entityPtr, (comp, klass) => {
            if (healthComponentClass && klass.equals(healthComponentClass)) {
                out.hp = comp.add(COMP_FIELD.hpRemaining).readS32();
                out.maxHp = comp.add(COMP_FIELD.hpMax).readS32();
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
            }
            void movementComponentClass;
        });
        if (out.hp !== null && out.hp <= 0) out.isDead = true;
    } catch { /* return defaults */ }
    return out;
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

/** Read PositionComponent on a Tile entity → (col, row). */
function readTilePosition(
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
export function projectMatchState(statePtr: NativePointer): MatchStateProjection {
    const status = readBattleStatus(statePtr);

    // Single pass — build entityById index, squad stats, player→team map.
    const entityById = new Map<number, NativePointer>();
    const squads = new Map<number, SquadStats>();
    const playerTeams = new Map<number, number>();
    forEachEntity(statePtr, (e, id, ty) => {
        entityById.set(id, e);
        if (ty === EntityType.Unit) {
            squads.set(id, projectSquadStats(e));
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
            ownerId: parent?.ownerId ?? null,
            teamId,
            visualId: parent?.visualId ?? null,
            rank: parent?.rank ?? null,
            isDead: parent?.isDead ?? false,
        });
    });
    units.sort((a, b) => a.id - b.id);

    return {
        turn: status.currentTurnPlayer,
        playerOnTurn: status.currentTurnPlayer,
        stage: status.stage,
        stageName: status.stageName,
        units,
    };
}

