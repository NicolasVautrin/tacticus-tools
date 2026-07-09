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
    forEachEntity, forEachComponent, projectMatchState, EntityType,
} from "../game/match-state.js";
import { getRunner as getRegistryRunner } from "../game/runner-registry.js";
import { class_get_name, class_get_namespace, cstr } from "../il2cpp/helpers.js";
import { queueOnMainThread } from "../runtime/queue.js";
import { Ctx } from "../controller.js";

/** DIAG (scratch): dump component class names for entities of given types,
 * to discover where a Machine's HP/position actually live. One entity per
 * type by default. Reads a few candidate int fields raw for inspection. */
function dumpEntityComponents(opts: {
    runnerId?: number; types?: number[]; perType?: number;
}): unknown {
    let runner: NativePointer | null = null;
    if (opts?.runnerId !== undefined) {
        try { runner = getRegistryRunner(opts.runnerId).runner; }
        catch (e) { return { err: (e as Error).message }; }
    } else { runner = state.liveRunner ?? null; }
    if (!runner) return { err: "no runner" };
    const statePtr = runner.add(runnerOff.state).readPointer();
    if (statePtr.isNull()) return { err: "matchState null" };

    const types = opts.types ?? [1, 6, 7];
    const perType = opts.perType ?? 1;
    const seen: Record<number, number> = {};
    const out: Array<Record<string, unknown>> = [];
    forEachEntity(statePtr, (e, id, ty) => {
        if (!types.includes(ty)) return;
        seen[ty] = (seen[ty] ?? 0) + 1;
        if (seen[ty] > perType) return;
        const comps: Array<Record<string, unknown>> = [];
        forEachComponent(e, (comp, klass) => {
            let name = "?", ns = "?";
            try { name = cstr(class_get_name(klass) as NativePointer); }
            catch { /* keep */ }
            try { ns = cstr(class_get_namespace(klass) as NativePointer); }
            catch { /* keep */ }
            // Raw ints at the offsets the projector cares about, so we can
            // eyeball where HP (Max@0x14/Rem@0x18) and pos (@0x10/0x14) sit.
            const peek: Record<string, number> = {};
            for (const off of [0x10, 0x14, 0x18, 0x20, 0x78]) {
                try { peek[`0x${off.toString(16)}`] = comp.add(off).readS32(); }
                catch { /* skip */ }
            }
            comps.push({ name, ns, comp: comp.toString(), peek });
        });
        out.push({ entityId: id, entityType: ty, components: comps });
    });
    return { ok: true, counts: seen, entities: out };
}

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
    /** Depletable armor pool (ArmorComponent, StatType.Armor=4). null if the
     * unit has no ArmorComponent (unarmored). Feeds the repair ARMOR term (#83). */
    armor: number | null;
    armorMax: number | null;
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
    /** MoW projection (1 row per MachinePlatform → linked Machine). Empty
     * unless the battle has deployed Machines of War. Exposes pos/hp/owner so
     * we can verify a MoW is actually on the board and being played. */
    mows: unknown[];
    err?: string;
}

function observeBattle(opts?: { runnerId?: number }): BattleObservation {
    const obs: BattleObservation = {
        ok: false, runner: null, matchState: null,
        stage: null, stageName: null, currentPlayer: null,
        counts: { total: 0, tiles: 0, units: 0, match: 0,
                  effects: 0, player: 0, other: 0 },
        byType: {}, units: [], mows: [],
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
            armor: u.armor,
            armorMax: u.armorMax,
            rank: u.rank,
            isDead: u.isDead,
        });
    }

    // Expose the MoW projection the projector already computed (units-only
    // copy above drops it). Lets callers verify a Machine of War is deployed
    // on the board (pos set) and being played (pos/hp change across turns).
    obs.mows = (proj.mows ?? []) as unknown[];

    obs.ok = true;
    return obs;
}

export function register(ctx: Ctx): void {
    ctx.rpc.observeBattle = (opts?: { runnerId?: number }) =>
        queueOnMainThread(() => observeBattle(opts));
    ctx.rpc.dumpEntityComponents = (opts?: {
        runnerId?: number; types?: number[]; perType?: number;
    }) => queueOnMainThread(() => dumpEntityComponents(opts ?? {}));
}
