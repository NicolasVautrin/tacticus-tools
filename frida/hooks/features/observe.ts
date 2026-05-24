// Comprehensive observation RPC over a runner's MatchState.
//
// Thin wrapper around `projectMatchState` (game/match-state.ts) which is
// the canonical projector: it uses IL2CPP component class reflection
// (`forEachComponent`) instead of hardcoded offsets, walks UnitFoot →
// Tile to resolve visible piece positions correctly, and resolves
// Player → TeamId so the `teamId` is the logical team (1/2/3).
//
// Output shape preserves the historic observeBattle contract used by
// diag scripts: { stage, stageName, units: [{entityId, visualId,
// playerId, col, row, hp, hpMax, ...}], counts, byType }.
// Per-foot entries (= one row per visible tile occupied by a unit).

import { state } from "../game/state.js";
import { runnerOff } from "../game/runner.js";
import {
    forEachEntity, projectMatchState, EntityType,
} from "../game/match-state.js";
import { getRunner as getRegistryRunner } from "../game/runner-registry.js";
import { queueOnMainThread } from "../runtime/queue.js";
import { Ctx } from "../controller.js";

interface UnitObservation {
    entityId: number;
    squadId: number;
    visualId: string | null;
    /** Logical team id (1=player, 2=AI, 3=env). Use this for friend/foe. */
    teamId: number | null;
    /** Owner's PlayerEntityId (BEntityId in MatchState — not the logical
     * 11/12 PlayerId of the BC config). Kept for traceability. */
    playerId: number | null;
    col: number | null;
    row: number | null;
    hp: number | null;
    hpMax: number | null;
    rank: number | null;
    isDead: boolean;
}

interface BattleObservation {
    ok: boolean;
    runner: string | null;
    matchState: string | null;
    stage: number | null;
    stageName: string | null;
    currentPlayer: number | null;
    counts: { total: number; tiles: number; units: number; match: number;
              effects: number; player: number; other: number };
    byType: Record<number, number>;
    units: UnitObservation[];
    err?: string;
}

function observeBattle(opts?: { runnerId?: number }): BattleObservation {
    const obs: BattleObservation = {
        ok: false, runner: null, matchState: null,
        stage: null, stageName: null, currentPlayer: null,
        counts: { total: 0, tiles: 0, units: 0, match: 0,
                  effects: 0, player: 0, other: 0 },
        byType: {}, units: [],
    };

    let runner: NativePointer | null = null;
    if (opts?.runnerId !== undefined) {
        try {
            runner = getRegistryRunner(opts.runnerId).runner;
        } catch (e) {
            obs.err = (e as Error).message; return obs;
        }
    } else {
        runner = state.liveRunner ?? null;
    }
    if (!runner) { obs.err = "no runner (live or by id)"; return obs; }
    obs.runner = runner.toString();

    const statePtr = runner.add(runnerOff.state).readPointer();
    if (statePtr.isNull()) { obs.err = "matchState is null"; return obs; }
    obs.matchState = statePtr.toString();

    // Counts per EntityType: fast scan (no component decoding).
    forEachEntity(statePtr, (_e, _id, type) => {
        obs.counts.total++;
        obs.byType[type] = (obs.byType[type] ?? 0) + 1;
        switch (type) {
            case EntityType.Tile: obs.counts.tiles++; break;
            case EntityType.Unit: obs.counts.units++; break;
            case EntityType.Match: obs.counts.match++; break;
            case EntityType.Effect: obs.counts.effects++; break;
            case EntityType.Player: obs.counts.player++; break;
            default: obs.counts.other++; break;
        }
    });

    // Reuse the canonical projector — robust to layout changes (uses
    // component class reflection), and resolves UnitFoot → Tile positions
    // + Player → TeamId mapping correctly.
    const proj = projectMatchState(statePtr);
    obs.stage = proj.stage;
    obs.stageName = proj.stageName;
    obs.currentPlayer = proj.playerOnTurn;

    for (const u of proj.units) {
        obs.units.push({
            entityId: u.id,
            squadId: u.squadId,
            visualId: u.visualId,
            teamId: u.teamId,
            playerId: u.ownerId,
            col: u.pos?.col ?? null,
            row: u.pos?.row ?? null,
            hp: u.hp,
            hpMax: u.maxHp,
            rank: u.rank,
            isDead: u.isDead,
        });
    }

    obs.ok = true;
    return obs;
}

export function register(ctx: Ctx): void {
    ctx.rpc.observeBattle = (opts?: { runnerId?: number }) =>
        queueOnMainThread(() => observeBattle(opts));
}
