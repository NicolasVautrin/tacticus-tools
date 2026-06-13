// message-trace — capture messages (runner.Apply + AI sub-messages) +
// leurs StreamDispatcher events (StepType: UnitDamaged, ReceiveEffect,
// LoseEffect, ChangePosition, etc.) en flush JSONL par apply window.
//
// Pourquoi exister :
//   - Le recorder (game/recorder.ts) fait ce travail mais dort si
//     state.liveRunner === null. Les RL batches en build runners isolés
//     ne déclenchent jamais l'install.
//   - launch.captureEvents wrap seulement init/start, pas autoPlayRunner.
//   - Conséquence : avant ce module, les StreamDispatcher events tombent
//     dans le vide pendant les RL batches (apply-stack vide → push
//     nowhere).
//
// Stratégie :
//   - Hook runnerApplyMi onEnter/onLeave + applyAiMsgMi + applyHumanAiMsgMi
//   - Filter via watchedRunners / watchedAiControls : seulement les
//     runners enregistrés (live OR build)
//   - Pour origin === "live" : SKIP — le recorder fait déjà le job
//   - Pour origin === build id : pushApply + emit message au onEnter,
//     popApply + emit events au onLeave
//   - Maintient aussi state.scoringRunnerId + state.applySeq (déplace
//     ce travail depuis move-options.ts)

import { readMsgClass } from "../il2cpp/helpers.js";
import { state } from "../game/state.js";
import { runnerApplyMi, runnerOff } from "../game/runner.js";
import { applyAiMsgMi, applyHumanAiMsgMi } from "../game/ai-control.js";
import { projectMatchState } from "../game/match-state.js";
import { getRunner as getRegistryRunner } from "../game/runner-registry.js";
import {
    pushApply, popApply, ensureStreamHooks, StreamEvent,
    streamHookStats,
} from "../game/apply-stack.js";
import { emit } from "./ai-trace/state.js";
import { Ctx } from "../controller.js";

/** Resolve runner ptr from origin tag, then snapshot MatchState.
 * `includeTiles=true` ajoute la liste des Tile entities (col/row + props
 * statiques) — à n'utiliser qu'au 1er message de chaque battle pour
 * eviter le bloat. */
function snapshotMatchStateFor(
    origin: "live" | number, includeTiles = false,
): Record<string, unknown> | null {
    let runner: NativePointer | null = null;
    if (origin === "live") {
        runner = state.liveRunner;
    } else {
        try { runner = getRegistryRunner(origin).runner; }
        catch { return null; }
    }
    if (!runner) return null;
    try {
        const sp = runner.add(runnerOff.state).readPointer();
        if (sp.isNull()) return null;
        const proj = projectMatchState(sp, { includeTiles });
        return proj as unknown as Record<string, unknown>;
    } catch { return null; }
}

/** Set des runners pour lesquels on a deja envoye le snapshot tiles.
 * Reset au reinject (module reload). */
const tilesSnappedRunners = new Set<number>();

let installed = false;
let msgSeqCounter = 0;

type MsgCtx = InvocationContext & {
    _mtPushed?: boolean;
    _mtMsgIdx?: number;
    _mtEvents?: StreamEvent[];
    _mtOrigin?: "live" | number;
};

/** Hook commun pour runner.Apply / AiControl.Apply*Message. Push une
 * frame, set le contexte, emit le message au onEnter. Au onLeave, pop la
 * frame et emit `message_events` avec tous les StreamDispatcher events
 * capturés pendant l'apply. */
function attachApply(
    mi: { ptr: NativePointer } | null,
    src: "top" | "ai" | "humanAi",
    watchMap: Map<string, "live" | number>,
    isTopLevel: boolean,
): void {
    if (!mi || mi.ptr.isNull()) return;
    Interceptor.attach(mi.ptr, {
        onEnter(args) {
            const callee = args[0];
            const origin = watchMap.get(callee.toString());
            if (origin === undefined) return;
            // Pour live, le recorder s'occupe de tout — on évite la
            // double-capture.
            if (origin === "live") return;
            // Tentative lazy d'install des stream hooks. À ce point IL2CPP
            // est complètement chargé. Idempotent — coût d'1 if.
            ensureStreamHooks();

            const ctx = this as MsgCtx;
            ctx._mtOrigin = origin;
            ctx._mtMsgIdx = ++msgSeqCounter;

            // SEUL le top-level apply pushApply : le recursion guard de
            // Frida suppress les onLeave des sub-messages quand fired
            // depuis un autre attach onEnter → si on push pour sub-msgs
            // on accumule des frames jamais popées (leak). En ne pushant
            // qu'au top, tous les sub-events qui fire pendant Apply
            // tombent dans NOTRE seule frame.
            if (isTopLevel) {
                ctx._mtEvents = [];
                pushApply("built", ctx._mtEvents);
                ctx._mtPushed = true;
                state.scoringRunnerId = origin;
                state.applySeq += 1;
            } else {
                // Sub-message : pas de push, on emit juste le message
                // pour avoir la trace de l'action (move/ability/end).
                ctx._mtPushed = false;
                ctx._mtEvents = undefined;
            }

            const msg = args[1];
            let msgClass = "?";
            try { msgClass = readMsgClass(msg); } catch { /* keep ? */ }
            let unitId: number | null = null;
            try { unitId = msg.add(0x10).readS32(); } catch { /* null */ }

            // Snapshot MatchState avant l'apply = état `s_t` pour IL/RL.
            // Capturé ICI dans onEnter pour avoir la photo PRE-action.
            // Inclure tiles UNIQUEMENT au 1er msg de chaque runner (cad
            // 1 fois par battle) — la grille est statique sur la duree
            // de la battle, les tiles dynamiques (Fire, Swamp temp) sont
            // tracees via stream_event step_code 16/17 (ReceiveEffect).
            const isFirstForRunner = typeof origin === "number"
                && !tilesSnappedRunners.has(origin);
            const matchState = snapshotMatchStateFor(origin, isFirstForRunner);
            if (isFirstForRunner && typeof origin === "number") {
                tilesSnappedRunners.add(origin);
            }

            emit({
                evt: "message",
                msgIdx: ctx._mtMsgIdx,
                applySeq: state.applySeq,
                runnerId: origin,
                src,
                msgClass,
                unitId,
                matchState,
            });
        },
        onLeave() {
            const ctx = this as MsgCtx;
            if (!ctx._mtPushed) return;  // sub-message → rien à pop
            try { popApply(); } catch { /* ignore */ }
            state.scoringRunnerId = null;
            // Emit les events capturés pendant tout le top-level apply
            // (inclut les events fired par les sub-messages internes).
            const events = ctx._mtEvents ?? [];
            emit({
                evt: "message_events",
                msgIdx: ctx._mtMsgIdx,
                count: events.length,
                events,
            });
        },
    });
}

function install(): { ok: boolean; err?: string } {
    if (installed) return { ok: true };
    ensureStreamHooks();
    attachApply(runnerApplyMi, "top", state.watchedRunners, true);
    attachApply(applyAiMsgMi, "ai", state.watchedAiControls, false);
    attachApply(applyHumanAiMsgMi, "humanAi", state.watchedAiControls, false);
    Interceptor.flush();
    installed = true;
    emit({ evt: "message_trace_installed" });
    return { ok: true };
}

export function register(ctx: Ctx): void {
    install();

    ctx.rpc.messageTraceStatus = () => ({
        installed,
        msgSeqCounter,
        streamHook: streamHookStats(),
    });
}
