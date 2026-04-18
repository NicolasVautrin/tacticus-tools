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

import { findClass, getFieldOffset } from "../il2cpp/helpers.js";
import { serializeToJson } from "../il2cpp/serializer.js";

export const matchStateClass = findClass(
    "BattleLogicAssembly.dll", "IdunBattle.Core", "MatchState");
if (!matchStateClass) throw new Error("MatchState class not found");

export const msEntitiesOff = getFieldOffset(matchStateClass, "_entities");

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
