// winner-capture — détermine le vainqueur d'une battle en hookant
// `IdunBattle.Operations.VerifyMatchEndOperation.HasWon` (par-player) et
// `DidEveryoneLose` (cas draw).
//
// Pourquoi pas attendre la transition Running → Finished + lire le state :
// le `WinnerInfo` retourné par HasWon est transitoire (objet temporaire,
// non persisté sur PlayerComponent). Le hook capture l'info DIRECTEMENT
// au moment où le moteur la détermine, AVANT le dispose du runner.
//
// Static analysis (data/dumps/rmvdp0v56c/dump.cs:376298) :
//   VerifyMatchEndOperation.HasWon(IEntity player) → WinnerInfo
//     - WinnerInfo.<Winner>k__BackingField : IEntity  @ 0x10
//     - WinnerInfo.<Reason>k__BackingField : BattleWinnerReason (int) @ 0x18
//   VerifyMatchEndOperation.DidEveryoneLose(IReadOnlyList<IEntity>) → bool
//
// BattleWinnerReason enum :
//   0 WonMatch · 1 EnemySurrendered · 2 OutOfRounds · 3 EveryoneLost

import {
    findClass, findClassAnywhere, findMethod, findMethodByParamCount,
} from "../il2cpp/helpers.js";
import { emit } from "./ai-trace/state.js";
import { state } from "../game/state.js";
import { forEachComponent } from "../game/match-state.js";
import { Ctx } from "../controller.js";

const REASON_NAMES = ["WonMatch", "EnemySurrendered", "OutOfRounds", "EveryoneLost"];

// PlayerComponent layout (dump.cs:386577) :
//   PlayerId      @ 0x10 (struct wrapping int — int32 read OK)
//   TeamId        @ 0x24
//   Surrendered   @ 0x28
const PC_PLAYER_ID_OFF = 0x10;
const PC_TEAM_ID_OFF = 0x24;

const playerComponentClass = findClassAnywhere(
    "IdunBattle.Entities.Components", "PlayerComponent");

interface WinnerResolved {
    playerId: number | null;
    teamId: number | null;
    entityId: number;
}

function resolveWinnerFromEntity(entity: NativePointer): WinnerResolved {
    const out: WinnerResolved = {
        playerId: null, teamId: null, entityId: -1,
    };
    try { out.entityId = entity.add(0x10).readS32(); } catch { /* keep -1 */ }
    if (!playerComponentClass) return out;
    forEachComponent(entity, (comp, klass) => {
        if (!klass.equals(playerComponentClass)) return;
        try { out.playerId = comp.add(PC_PLAYER_ID_OFF).readS32(); }
        catch { /* leave null */ }
        try { out.teamId = comp.add(PC_TEAM_ID_OFF).readS32(); }
        catch { /* leave null */ }
    });
    return out;
}

let installed = false;
let hasWonFires = 0;
let hasWonNonNull = 0;     // Winner ≠ null
let didEveryoneLoseFires = 0;
let didEveryoneLoseTrue = 0;

interface ResolveResult {
    klass: NativePointer | null;
    hasWonMethod: { ptr: NativePointer; info: NativePointer } | null;
    didEveryoneLoseMethod: { ptr: NativePointer; info: NativePointer } | null;
    err: string | null;
}

function resolveTargets(): ResolveResult {
    const klass = findClass("BattleLogicAssembly.dll",
        "IdunBattle.Operations", "VerifyMatchEndOperation");
    if (!klass) {
        return {
            klass: null, hasWonMethod: null, didEveryoneLoseMethod: null,
            err: "VerifyMatchEndOperation class not found",
        };
    }
    const hasWon = findMethodByParamCount(klass, "HasWon", 1);
    const everyone = findMethod(klass, "DidEveryoneLose");
    return {
        klass,
        hasWonMethod: hasWon,
        didEveryoneLoseMethod: everyone,
        err: null,
    };
}

let resolved: ResolveResult | null = null;
let listeners: InvocationListener[] = [];

function install(): { ok: boolean; err?: string } {
    if (installed) return { ok: true };
    resolved = resolveTargets();
    if (resolved.err) return { ok: false, err: resolved.err };

    if (resolved.hasWonMethod && !resolved.hasWonMethod.ptr.isNull()) {
        listeners.push(Interceptor.attach(resolved.hasWonMethod.ptr, {
            onLeave(retval) {
                hasWonFires++;
                // Most calls return null (winner pas encore décidé).
                // Cheap early exit.
                if (retval.isNull()) return;
                let winnerEntity: NativePointer;
                try { winnerEntity = retval.add(0x10).readPointer(); }
                catch { return; }
                if (winnerEntity.isNull()) return;
                hasWonNonNull++;
                let reason = -1;
                try { reason = retval.add(0x18).readS32(); } catch { /* keep -1 */ }
                const w = resolveWinnerFromEntity(winnerEntity);
                emit({
                    evt: "battle_winner",
                    runnerId: state.scoringRunnerId,
                    applySeq: state.applySeq,
                    outcome: "won",
                    winnerPlayerId: w.playerId,
                    winnerTeamId: w.teamId,
                    winnerEntityId: w.entityId,
                    reasonCode: reason,
                    reasonName: REASON_NAMES[reason] ?? "?",
                });
            },
        }));
    }

    if (resolved.didEveryoneLoseMethod
        && !resolved.didEveryoneLoseMethod.ptr.isNull()) {
        listeners.push(Interceptor.attach(
            resolved.didEveryoneLoseMethod.ptr, {
            onLeave(retval) {
                didEveryoneLoseFires++;
                // bool retval : 0 = false, 1 = true. Most calls return
                // false. Filter cheaply.
                const r = retval.toInt32() & 1;
                if (r === 0) return;
                didEveryoneLoseTrue++;
                emit({
                    evt: "battle_winner",
                    runnerId: state.scoringRunnerId,
                    applySeq: state.applySeq,
                    outcome: "draw",
                    winnerPlayerId: null,
                    winnerTeamId: null,
                    winnerEntityId: null,
                    reasonCode: 3,  // EveryoneLost
                    reasonName: "EveryoneLost",
                });
            },
        }));
    }

    Interceptor.flush();
    installed = true;
    return { ok: true };
}

function counters(): Record<string, unknown> {
    return {
        installed,
        hasWonFires, hasWonNonNull,
        didEveryoneLoseFires, didEveryoneLoseTrue,
        klass: resolved?.klass ? "VerifyMatchEndOperation" : null,
        hasWonResolved:
            !!resolved?.hasWonMethod && !resolved.hasWonMethod.ptr.isNull(),
        didEveryoneLoseResolved: !!resolved?.didEveryoneLoseMethod
            && !resolved.didEveryoneLoseMethod.ptr.isNull(),
        err: resolved?.err ?? null,
    };
}

export function register(ctx: Ctx): void {
    // Auto-install au register : capture du winner toujours active, pas
    // d'arm/disarm RPC. Coût négligeable (filter retval.isNull() cheap).
    const r = install();
    if (!r.ok) {
        try {
            emit({ evt: "winner_capture_install_failed", err: r.err });
        } catch { /* ignore */ }
    }

    ctx.rpc.winnerCaptureStatus = () => counters();
}
