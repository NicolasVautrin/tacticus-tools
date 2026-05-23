// Comprehensive observation RPC over the live MatchState.
//
// Reports every entity present in the runner's MatchState — tiles, units,
// match meta, effects — with the fields most useful for RL state input AND
// debugging (did the AI squad patch actually spawn the units we asked for?).
//
// At Setup stage, the entities list may be empty or contain only tiles;
// units typically materialize at the Running transition. The observation
// reports whatever IS there so the caller can distinguish "battle not yet
// initialized" from "battle initialized but no enemy units" — a key signal
// for diagnosing patch failures.

import { readIl2cppString } from "../il2cpp/helpers.js";
import { state } from "../game/state.js";
import { runnerOff } from "../game/runner.js";
import {
    forEachEntity, readBattleStatus, readTurnInfo, EntityType, STAGE_NAMES,
} from "../game/match-state.js";
import { getRunner as getRegistryRunner }
    from "../game/runner-registry.js";
import { queueOnMainThread } from "../runtime/queue.js";
import { Ctx } from "../controller.js";

// --- Entity component offsets ---
// Per normalizer.ts (already in the project) and match-state.ts comments:
//   UnitEntity layout:
//     +0x10  Id (int32)
//     +0x14  Type (int32, EntityType enum)
//     +0x28  UnitComponent
//     +0x38  Attack/Damage StatComponent
//     +0x40  OwnerComponent (PlayerEntityId at +0x10 inside)
//     +0x58  HealthComponent (FillUpStat: Initial/Max/Remaining at +0x10/14/18)
//     +0x60  Armor StatComponent
//     +0x68  PositionComponent (Coordinate.Column at +0x10, Row at +0x14)
//
// (these were tuned against the dump and validated by the existing
// normalizer code which writes HP/dmg/armor through them)

const UE_OFF_UNIT_COMP = 0x28;
const UE_OFF_ATTACK_COMP = 0x38;
const UE_OFF_OWNER_COMP = 0x40;
const UE_OFF_HEALTH_COMP = 0x58;
const UE_OFF_ARMOR_COMP = 0x60;
const UE_OFF_POSITION_COMP = 0x68;

const UNITCOMP_OFF_VISUAL_ID = 0x20;
const HEALTH_OFF_MAX = 0x14;
const HEALTH_OFF_REMAINING = 0x18;
const STAT_OFF_INITIAL = 0x48;  // StatComponent.InitialValue (damage/armor)
const POS_OFF_COL = 0x10;
const POS_OFF_ROW = 0x14;
const OWNER_OFF_PLAYER_ID = 0x10;

const TILE_OFF_POSITION_COMP = 0x28;  // tiles use position at a different offset
const TILE_OFF_TILE_COMP = 0x30;

interface UnitObservation {
    entityId: number;
    visualId: string | null;
    playerId: number | null;
    col: number | null;
    row: number | null;
    hp: number | null;
    hpMax: number | null;
    damage: number | null;
    armor: number | null;
}

interface TileObservation {
    entityId: number;
    col: number | null;
    row: number | null;
}

interface BattleObservation {
    ok: boolean;
    runner: string | null;
    matchState: string | null;
    stage: number | null;
    stageName: string | null;
    currentPlayer: number | null;
    round: number | null;
    counts: {
        total: number;
        tiles: number;
        units: number;
        match: number;
        effects: number;
        other: number;
    };
    byType: Record<number, number>;  // EntityType (0..8) → count
    units: UnitObservation[];
    tiles?: TileObservation[];     // omitted by default (verbose)
    err?: string;
}

function observeBattle(opts?: {
    includeTiles?: boolean;
    runnerId?: number;
}): BattleObservation {
    const obs: BattleObservation = {
        ok: false,
        runner: null, matchState: null,
        stage: null, stageName: null, currentPlayer: null, round: null,
        counts: { total: 0, tiles: 0, units: 0, match: 0, effects: 0, other: 0 },
        byType: {},
        units: [],
    };
    if (opts?.includeTiles) obs.tiles = [];

    // Pick the runner: explicit runnerId from registry, else state.liveRunner.
    let runner: NativePointer | null = null;
    if (opts?.runnerId !== undefined) {
        try {
            runner = getRegistryRunner(opts.runnerId).runner;
        } catch (e) {
            obs.err = (e as Error).message;
            return obs;
        }
    } else {
        runner = state.liveRunner ?? null;
    }
    if (!runner) { obs.err = "no runner (live or by id)"; return obs; }
    obs.runner = runner.toString();

    const statePtr = runner.add(runnerOff.state).readPointer();
    if (statePtr.isNull()) { obs.err = "matchState is null"; return obs; }
    obs.matchState = statePtr.toString();

    const status = readBattleStatus(statePtr);
    obs.stage = status.stage;
    obs.stageName = status.stageName;
    const turn = readTurnInfo(statePtr);
    obs.currentPlayer = turn.player;
    obs.round = turn.round;

    forEachEntity(statePtr, (ePtr, id, type) => {
        obs.counts.total++;
        obs.byType[type] = (obs.byType[type] ?? 0) + 1;
        if (type === EntityType.Tile) {
            obs.counts.tiles++;
            if (obs.tiles) {
                try {
                    const pc = ePtr.add(TILE_OFF_POSITION_COMP).readPointer();
                    if (!pc.isNull()) {
                        obs.tiles.push({
                            entityId: id,
                            col: pc.add(POS_OFF_COL).readS32(),
                            row: pc.add(POS_OFF_ROW).readS32(),
                        });
                    } else {
                        obs.tiles.push({ entityId: id, col: null, row: null });
                    }
                } catch {
                    obs.tiles.push({ entityId: id, col: null, row: null });
                }
            }
        } else if (type === EntityType.Unit) {
            obs.counts.units++;
            const u: UnitObservation = {
                entityId: id,
                visualId: null,
                playerId: null,
                col: null, row: null,
                hp: null, hpMax: null,
                damage: null, armor: null,
            };
            try {
                const uc = ePtr.add(UE_OFF_UNIT_COMP).readPointer();
                if (!uc.isNull()) {
                    u.visualId = readIl2cppString(
                        uc.add(UNITCOMP_OFF_VISUAL_ID).readPointer());
                }
            } catch { /* */ }
            try {
                const oc = ePtr.add(UE_OFF_OWNER_COMP).readPointer();
                if (!oc.isNull()) {
                    u.playerId = oc.add(OWNER_OFF_PLAYER_ID).readS32();
                }
            } catch { /* */ }
            try {
                const pc = ePtr.add(UE_OFF_POSITION_COMP).readPointer();
                if (!pc.isNull()) {
                    u.col = pc.add(POS_OFF_COL).readS32();
                    u.row = pc.add(POS_OFF_ROW).readS32();
                }
            } catch { /* */ }
            try {
                const hc = ePtr.add(UE_OFF_HEALTH_COMP).readPointer();
                if (!hc.isNull()) {
                    u.hpMax = hc.add(HEALTH_OFF_MAX).readS32();
                    u.hp = hc.add(HEALTH_OFF_REMAINING).readS32();
                }
            } catch { /* */ }
            try {
                const ac = ePtr.add(UE_OFF_ATTACK_COMP).readPointer();
                if (!ac.isNull()) {
                    u.damage = ac.add(STAT_OFF_INITIAL).readS32();
                }
                const armorComp = ePtr.add(UE_OFF_ARMOR_COMP).readPointer();
                if (!armorComp.isNull()) {
                    u.armor = armorComp.add(STAT_OFF_INITIAL).readS32();
                }
            } catch { /* */ }
            obs.units.push(u);
        } else if (type === EntityType.Match) {
            obs.counts.match++;
        } else if (type === EntityType.Effect) {
            obs.counts.effects++;
        } else {
            obs.counts.other++;
        }
    });

    obs.ok = true;
    return obs;
}

export function register(ctx: Ctx): void {
    ctx.rpc.observeBattle = (
        opts?: { includeTiles?: boolean; runnerId?: number },
    ) => queueOnMainThread(() => observeBattle(opts));
}
