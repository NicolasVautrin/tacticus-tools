import { class_get_name, findMethod, s } from "../../il2cpp/helpers.js";
import { invokeMethod } from "../../il2cpp/invoke.js";
import { gcRoot } from "../../il2cpp/gc-root.js";
import { runnerApplyMi, runnerOff } from "../../game/runner.js";
import { getRunner } from "../../game/runner-registry.js";
import { setTraceOrigin } from "../../game/trace-origin.js";
import {
    projectMatchState, readBattleStatus,
} from "../../game/match-state.js";
import { applyAiMsgMi } from "../../game/ai-control.js";
import {
    ensureStreamHooks, popApply, pushApply, StreamEvent,
} from "../../game/apply-stack.js";
import { state } from "../../game/state.js";
import { queueOnMainThread } from "../../runtime/queue.js";
import { Ctx } from "../../controller.js";
import {
    applyEndTurn, captureStateForDemo, DecodedMsg, decodeMsgList, DryRunResult,
    hasActionLeftMi, invokeBool, isAliveMi, processMsgList,
    resolvePlayerEntity, resolveStrategy, summarize, sweepAllUnitProposals,
    turnFlagResetAvailable, turnFlagResetDiagnostic,
    UnitDemo, UnitProposal, validSquadsOrdered,
} from "./internals.js";


export function registerDrive(ctx: Ctx): void {
    /** Étape 1 : pilote 1 MoveNext de CalculateNextActionForPlayer et décode
     *  l'action de la prochaine unité que l'IA jouerait — SANS commit. Sûr
     *  (ne mute pas le runner). Valide le pilotage manuel sur runner isolé.
     *  body: { runnerId?: number } — défaut = live runner. */
    ctx.rpc.aiStepDryRun = (
        body?: { runnerId?: number; maxPump?: number },
    ): Promise<DryRunResult> => queueOnMainThread((): DryRunResult => {
        const MAX_PUMP = (typeof body?.maxPump === "number" && body.maxPump > 0)
            ? body.maxPump : 2000;
        // 1. Runner cible.
        let runner: NativePointer;
        let label: string;
        if (typeof body?.runnerId === "number") {
            try { runner = getRunner(body.runnerId).runner; }
            catch (e) { return { ok: false, error: (e as Error).message }; }
            setTraceOrigin(body.runnerId);   // attribution des traces (cf. game/trace-origin.ts)
            label = "build#" + body.runnerId;
        } else if (state.liveRunner) {
            runner = state.liveRunner;
            label = "live";
        } else {
            return { ok: false, error: "no runner — pass runnerId or start a live battle" };
        }
        if (runner.isNull()) return { ok: false, error: label + " runner null" };

        // 2. État + garde stage Running + joueur courant.
        const statePtr = runner.add(runnerOff.state).readPointer();
        if (statePtr.isNull()) {
            return { ok: false, error: label + " _state null (not initialized)" };
        }
        const status = readBattleStatus(statePtr);
        if (status.stage !== 1) {
            return { ok: false, runner: label,
                error: label + " stage " + (status.stageName ?? status.stage)
                    + " (need Running)" };
        }
        const playerId = status.currentTurnPlayer;
        if (playerId === null) {
            return { ok: false, runner: label, error: "no currentTurnPlayer" };
        }

        // 3. AiControl + stratégie.
        const aiControl = runner.add(runnerOff.aiControl).readPointer();
        if (aiControl.isNull()) {
            return { ok: false, runner: label, error: "aiControl null" };
        }
        const { strategy, src: strategySrc, err: strategyErr } =
            resolveStrategy(aiControl, playerId);
        if (strategy.isNull()) {
            return { ok: false, runner: label, playerId, strategyErr,
                error: "strategy unresolved" };
        }

        // 4. Player IEntity = entité dont l'id == currentTurnPlayer.
        const playerEntity = resolvePlayerEntity(statePtr, playerId);
        if (playerEntity.isNull()) {
            return { ok: false, runner: label, playerId,
                error: "player entity (id=" + playerId + ") not found in state" };
        }

        // 5. Snapshot AVANT.
        const before = summarize(statePtr);

        // 6. CalculateNextActionForPlayer(player) → enumerator.
        const strategyClass = strategy.readPointer();
        const cnafpMi = findMethod(strategyClass, "CalculateNextActionForPlayer");
        if (!cnafpMi) {
            return { ok: false, runner: label, playerId, strategySrc,
                error: "CalculateNextActionForPlayer not found on "
                    + s(class_get_name(strategyClass) as NativePointer) };
        }
        let enumerator: NativePointer;
        try {
            enumerator = invokeMethod(cnafpMi.info, strategy, [playerEntity]);
        } catch (e) {
            return { ok: false, runner: label, playerId, strategySrc,
                error: "CalculateNextActionForPlayer threw: " + (e as Error).message };
        }
        if (enumerator.isNull()) {
            return { ok: false, runner: label, playerId, strategySrc,
                error: "enumerator null" };
        }

        // 7. UN MoveNext, lire <>2__current @0x18, décoder. Pin l'enumerator
        //    le temps de la séquence (les invoke peuvent déclencher un GC).
        gcRoot.add(enumerator);
        try {
            const enumClass = enumerator.readPointer();
            const moveNextMi = findMethod(enumClass, "MoveNext");
            if (!moveNextMi) {
                return { ok: false, runner: label, playerId, strategySrc,
                    error: "MoveNext not found on enumerator" };
            }
            // Pompe MoveNext jusqu'à une liste NON-VIDE (l'action d'une unité)
            // ou épuisement. La coroutine yield des listes vides pendant le
            // calcul multi-frame (decisionStopWatch / runAiCalculationsInMultipleFrames).
            let hasNext = false;
            let moveNextCalls = 0;
            let emptyYields = 0;
            let action: { count: number; messages: DecodedMsg[] } | null = null;
            let activatedUnitId: number | null = null;
            try {
                while (moveNextCalls < MAX_PUMP) {
                    const boxed = invokeMethod(moveNextMi.info, enumerator, null);
                    moveNextCalls++;
                    hasNext = !boxed.isNull() && boxed.add(0x10).readU8() !== 0;
                    if (!hasNext) break;  // tour épuisé, aucune action
                    // d__6 : <>2__current @0x18 = la List<IInputMessage> yieldée.
                    const list = enumerator.add(0x18).readPointer();
                    const decoded = decodeMsgList(list);
                    if (decoded.count > 0) {  // action d'une unité prête
                        action = decoded;
                        for (const m of decoded.messages) {
                            if (m.cls === "MoveUnitMessage" && m.unitId !== undefined) {
                                activatedUnitId = m.unitId; break;
                            }
                            if (m.cls === "FinishUnitTurnMessage"
                                && m.unitId !== undefined
                                && activatedUnitId === null) {
                                activatedUnitId = m.unitId;
                            }
                        }
                        break;
                    }
                    emptyYields++;  // yield vide = calcul en cours, on re-pompe
                }
            } catch (e) {
                return { ok: false, runner: label, playerId, strategySrc,
                    error: "MoveNext threw after " + moveNextCalls
                        + " calls: " + (e as Error).message,
                    moveNextCalls, emptyYields, before };
            }

            // Re-projection APRÈS pour confirmer que le dry-run n'a rien mué.
            const after = summarize(statePtr);
            return {
                ok: true, runner: label, playerId, strategySrc, strategyErr,
                hasNext, moveNextCalls, emptyYields, action, activatedUnitId,
                mutated: before.sig !== after.sig,
                before,
            };
        } finally {
            try { gcRoot.remove(enumerator); } catch { /* best effort */ }
        }
    });

    /** Driver per-unité COMPLET (sans CheatRunAIMessage) : pour chaque tour
     *  d'équipe, pilote CalculateNextActionForPlayer — pompe MoveNext jusqu'à
     *  un chunk non-vide, snapshot l'état AVANT chaque MoveUnitMessage, applique
     *  le chunk (runner.Apply), re-pompe ; à l'épuisement, EndTurn → équipe
     *  suivante. Capture 1 démo (état, unité, déplacement) par activation avec
     *  déplacement. L'IA choisit unité + position ; on ne contrôle que le grain.
     *  body: { runnerId, maxTurns?, maxActivations?, maxPump? } */
    ctx.rpc.aiPlayByUnit = (
        body?: {
            runnerId?: number; maxTurns?: number;
            maxActivations?: number; maxPump?: number;
            probeEachTurn?: boolean; captureEvents?: boolean;
            captureOverwatch?: boolean;
        },
    ): Promise<unknown> => queueOnMainThread(() => {
        // Runner cible.
        let runner: NativePointer; let label: string;
        if (typeof body?.runnerId === "number") {
            try { runner = getRunner(body.runnerId).runner; }
            catch (e) { return { ok: false, error: (e as Error).message }; }
            setTraceOrigin(body.runnerId);   // attribution des traces (cf. game/trace-origin.ts)
            label = "build#" + body.runnerId;
        } else if (state.liveRunner) {
            runner = state.liveRunner; label = "live";
        } else {
            return { ok: false, error: "no runner — pass runnerId" };
        }
        if (runner.isNull()) return { ok: false, error: label + " runner null" };
        if (!runnerApplyMi) return { ok: false, error: "runner.Apply not resolved" };

        const maxTurns = body?.maxTurns ?? 60;
        const maxActivations = body?.maxActivations ?? 400;
        const maxPump = (typeof body?.maxPump === "number" && body.maxPump > 0)
            ? body.maxPump : 30000;
        const probeEachTurn = body?.probeEachTurn === true;
        // Capture de TOUTE la cascade du tour, uniformément : chaque event
        // StreamDispatcher de chaque activation, annoté par l'activation qui l'a
        // produit (turn/player/unit/message). PAS de cas spécial overwatch —
        // l'overwatch est un event comme un autre (UnitDamaged Effect_Type=1009),
        // décodé côté Python (stream_events) au même titre que counter, aura, DoT,
        // kills. Alias rétro-compat : captureOverwatch.
        const captureEvents = body?.captureEvents === true
            || body?.captureOverwatch === true;
        const cascade: Array<StreamEvent & {
            turnIndex: number; player: number;
            activationUnitId: number | null; msgCls: string;
        }> = [];
        const t0 = Date.now();
        const demos: UnitDemo[] = [];
        const turnProbes: Array<{
            turnIndex: number; player: number; proposals: UnitProposal[];
        }> = [];
        let turnsPlayed = 0;
        let totalActivations = 0;
        let totalPumps = 0;
        let stopReason = "maxTurns";

        while (turnsPlayed < maxTurns) {
            const statePtr = runner.add(runnerOff.state).readPointer();
            if (statePtr.isNull()) { stopReason = "state null"; break; }
            const status = readBattleStatus(statePtr);
            if (status.stage !== 1) {
                stopReason = "stage " + (status.stageName ?? status.stage); break;
            }
            const playerId = status.currentTurnPlayer;
            if (playerId === null) { stopReason = "no currentTurnPlayer"; break; }
            const aiControl = runner.add(runnerOff.aiControl).readPointer();
            if (aiControl.isNull()) { stopReason = "aiControl null"; break; }
            const { strategy } = resolveStrategy(aiControl, playerId);
            if (strategy.isNull()) { stopReason = "strategy null"; break; }
            const playerEntity = resolvePlayerEntity(statePtr, playerId);
            if (playerEntity.isNull()) {
                stopReason = "player entity " + playerId + " not found"; break;
            }
            const cnafpMi = findMethod(
                strategy.readPointer(), "CalculateNextActionForPlayer");
            if (!cnafpMi) { stopReason = "CalculateNextActionForPlayer not found"; break; }

            // Probe READ-ONLY en début de tour : ce que chaque unité ferait,
            // contre l'état de DÉBUT de tour (avant que l'équipe ne joue).
            if (probeEachTurn) {
                const calcUnitMi = findMethod(
                    strategy.readPointer(), "CalculateNextActionForUnit");
                if (calcUnitMi) {
                    const sweep = sweepAllUnitProposals(
                        statePtr, strategy, calcUnitMi, maxPump, { mi: null });
                    totalPumps += sweep.pumps;
                    turnProbes.push({
                        turnIndex: turnsPlayed, player: playerId,
                        proposals: sweep.units,
                    });
                }
            }

            // Boucle de PAS du tour : CalculateNextActionForPlayer yield UN seul
            // pas (1 liste) puis se termine — comme le d__16, on RE-CRÉE
            // l'énumérateur à chaque pas, jusqu'à ce que le tour passe (la main
            // change) ou qu'aucune action ne soit produite (tour épuisé).
            let moveNextMi: { info: NativePointer; ptr: NativePointer } | null = null;
            let turnErr: string | null = null;
            let step = 0;
            const MAX_STEPS = 250;
            try {
                while (step < MAX_STEPS && totalActivations < maxActivations) {
                    step++;
                    // Énumérateur FRAIS pour ce pas.
                    const e = invokeMethod(cnafpMi.info, strategy, [playerEntity]);
                    if (e.isNull()) break;
                    gcRoot.add(e);
                    if (!moveNextMi) moveNextMi = findMethod(e.readPointer(), "MoveNext");
                    let chunk: Array<{ ptr: NativePointer; decoded: DecodedMsg }>
                        | null = null;
                    try {
                        let pumps = 0;
                        while (moveNextMi && pumps < maxPump) {
                            const boxed = invokeMethod(moveNextMi.info, e, null);
                            pumps++; totalPumps++;
                            if (boxed.isNull() || boxed.add(0x10).readU8() === 0) break;
                            const items = processMsgList(e.add(0x18).readPointer());
                            if (items.length > 0) { chunk = items; break; }
                        }
                    } finally {
                        try { gcRoot.remove(e); } catch { /* best effort */ }
                    }
                    if (!chunk) break;  // aucune action → tour épuisé

                    // Snapshot AVANT si le pas contient un déplacement.
                    const hasMove = chunk.some(
                        (it) => it.decoded.cls === "MoveUnitMessage");
                    const snap = hasMove ? captureStateForDemo(statePtr) : null;
                    for (const it of chunk) {
                        if (it.decoded.cls === "MoveUnitMessage" && snap
                            && it.decoded.unitId !== undefined) {
                            demos.push({
                                turnIndex: turnsPlayed,
                                player: playerId,
                                activatedUnitId: it.decoded.unitId,
                                move: {
                                    to: it.decoded.to ?? null,
                                    pathLen: it.decoded.pathLen ?? 0,
                                },
                                toActivate: snap.toActivate,
                                units: snap.units,
                            });
                            totalActivations++;
                        }
                        // Applique via ApplyAiMessage (→ _inputProcessor), PAS
                        // runner.Apply direct : sinon l'action n'est pas
                        // consommée côté AI/turn et l'unité reste « à jouer ».
                        if (captureEvents && applyAiMsgMi) {
                            // Wrap l'apply dans une frame → capture TOUTE la
                            // cascade de cette activation (applyAiMsgMi hooké
                            // NON-top → sans frame, events dans le vide). Aucun
                            // filtre : tout remonte, annoté ; décodage Python.
                            ensureStreamHooks();
                            const evs: StreamEvent[] = [];
                            pushApply("built", evs);
                            try { invokeMethod(applyAiMsgMi.info, aiControl, [it.ptr]); }
                            finally { try { popApply(); } catch { /* */ } }
                            for (const ev of evs) {
                                cascade.push({
                                    ...ev, turnIndex: turnsPlayed, player: playerId,
                                    activationUnitId: it.decoded.unitId ?? null,
                                    msgCls: it.decoded.cls,
                                });
                            }
                        } else if (applyAiMsgMi) {
                            invokeMethod(applyAiMsgMi.info, aiControl, [it.ptr]);
                        } else {
                            invokeMethod(runnerApplyMi.info, runner, [it.ptr]);
                        }
                    }

                    // La main a-t-elle changé (tour passé) ?
                    const sp = runner.add(runnerOff.state).readPointer();
                    if (!sp.isNull()
                        && readBattleStatus(sp).currentTurnPlayer !== playerId) {
                        break;
                    }
                }
            } catch (e) {
                turnErr = (e as Error).message;
            }
            if (turnErr) { stopReason = "turn err: " + turnErr; break; }
            turnsPlayed++;

            // Force le passage de tour si toujours le même joueur (et battle pas finie).
            const sp2 = runner.add(runnerOff.state).readPointer();
            if (!sp2.isNull()) {
                const st2 = readBattleStatus(sp2);
                if (st2.stage === 1 && st2.currentTurnPlayer === playerId) {
                    try {
                        // Capture aussi les effets de FRONTIÈRE de tour (ticks
                        // d'AoE/DoT résolus à l'EndTurn) dans la cascade.
                        if (captureEvents) {
                            const evs: StreamEvent[] = [];
                            applyEndTurn(runner, evs);
                            for (const ev of evs) {
                                cascade.push({
                                    ...ev, turnIndex: turnsPlayed, player: playerId,
                                    activationUnitId: null, msgCls: "EndTurnMessage",
                                });
                            }
                        } else {
                            applyEndTurn(runner);
                        }
                    } catch (e) {
                        stopReason = "endturn threw: " + (e as Error).message; break;
                    }
                }
            }
            if (totalActivations >= maxActivations) {
                stopReason = "maxActivations"; break;
            }
        }

        const spEnd = runner.add(runnerOff.state).readPointer();
        const endStatus = spEnd.isNull() ? null : readBattleStatus(spEnd);
        return {
            ok: true, runner: label,
            turnsPlayed, totalActivations, totalPumps,
            ms: Date.now() - t0, stopReason,
            finalStage: endStatus?.stage ?? null,
            finalStageName: endStatus?.stageName ?? null,
            finalPlayer: endStatus?.currentTurnPlayer ?? null,
            demoCount: demos.length, demos,
            probeCount: turnProbes.length, turnProbes,
            cascadeCount: cascade.length, cascade,
        };
    });

    /** INTERVENTION étape 1 : FORCER l'ordre d'activation. Au lieu de laisser
     *  PickNextUnit choisir, on désigne nous-mêmes l'unité et on pilote
     *  `CalculateNextActionForUnit(unit)` (l'IA décide quoi fait l'unité, nous
     *  décidons QUI joue et dans quel ordre).
     *  body: { runnerId, order?: "asc"|"desc"|number[], maxTurns?,
     *          maxActivations?, maxPump? } — order défaut "desc". */
    ctx.rpc.aiPlayOrdered = (
        body?: {
            runnerId?: number; order?: "asc" | "desc" | number[];
            maxTurns?: number; maxActivations?: number; maxPump?: number;
        },
    ): Promise<unknown> => queueOnMainThread(() => {
        let runner: NativePointer; let label: string;
        if (typeof body?.runnerId === "number") {
            try { runner = getRunner(body.runnerId).runner; }
            catch (e) { return { ok: false, error: (e as Error).message }; }
            setTraceOrigin(body.runnerId);   // attribution des traces (cf. game/trace-origin.ts)
            label = "build#" + body.runnerId;
        } else if (state.liveRunner) {
            runner = state.liveRunner; label = "live";
        } else {
            return { ok: false, error: "no runner — pass runnerId" };
        }
        if (runner.isNull()) return { ok: false, error: label + " runner null" };
        if (!applyAiMsgMi && !runnerApplyMi) {
            return { ok: false, error: "no apply method resolved" };
        }

        const order = body?.order ?? "desc";
        const maxTurns = body?.maxTurns ?? 60;
        const maxActivations = body?.maxActivations ?? 400;
        const maxPump = (typeof body?.maxPump === "number" && body.maxPump > 0)
            ? body.maxPump : 30000;
        const MAX_STEPS_PER_UNIT = 40;
        const t0 = Date.now();
        const demos: UnitDemo[] = [];
        const turnOrders: Array<{ turnIndex: number; player: number; order: number[] }> = [];
        let turnsPlayed = 0;
        let totalActivations = 0;
        let totalPumps = 0;
        let stopReason = "maxTurns";
        let moveNextMi: { info: NativePointer; ptr: NativePointer } | null = null;

        while (turnsPlayed < maxTurns) {
            const statePtr = runner.add(runnerOff.state).readPointer();
            if (statePtr.isNull()) { stopReason = "state null"; break; }
            const status = readBattleStatus(statePtr);
            if (status.stage !== 1) {
                stopReason = "stage " + (status.stageName ?? status.stage); break;
            }
            const playerId = status.currentTurnPlayer;
            if (playerId === null) { stopReason = "no currentTurnPlayer"; break; }
            const aiControl = runner.add(runnerOff.aiControl).readPointer();
            if (aiControl.isNull()) { stopReason = "aiControl null"; break; }
            const { strategy } = resolveStrategy(aiControl, playerId);
            if (strategy.isNull()) { stopReason = "strategy null"; break; }
            const calcUnitMi = findMethod(
                strategy.readPointer(), "CalculateNextActionForUnit");
            if (!calcUnitMi) { stopReason = "CalculateNextActionForUnit not found"; break; }

            // NOTRE ordre d'activation imposé.
            const myUnits = validSquadsOrdered(statePtr, order);
            const playedThisTurn: number[] = [];
            let turnErr: string | null = null;

            try {
                for (const u of myUnits) {
                    if (totalActivations >= maxActivations) break;
                    // Re-vérifie : l'unité peut avoir été tuée / avoir agi via
                    // une réaction pendant l'activation d'une autre.
                    if (!invokeBool(isAliveMi, [u.ptr, statePtr])) continue;
                    if (!invokeBool(hasActionLeftMi, [u.ptr])) continue;
                    playedThisTurn.push(u.id);

                    // Force-joue cette unité jusqu'à épuisement de ses actions.
                    let g = 0;
                    while (g < MAX_STEPS_PER_UNIT
                        && invokeBool(hasActionLeftMi, [u.ptr])
                        && invokeBool(isAliveMi, [u.ptr, statePtr])) {
                        g++;
                        const e = invokeMethod(calcUnitMi.info, strategy, [u.ptr]);
                        if (e.isNull()) break;
                        gcRoot.add(e);
                        if (!moveNextMi) {
                            moveNextMi = findMethod(e.readPointer(), "MoveNext");
                        }
                        let chunk: Array<{ ptr: NativePointer; decoded: DecodedMsg }>
                            | null = null;
                        try {
                            let pumps = 0;
                            while (moveNextMi && pumps < maxPump) {
                                const boxed = invokeMethod(moveNextMi.info, e, null);
                                pumps++; totalPumps++;
                                if (boxed.isNull() || boxed.add(0x10).readU8() === 0) break;
                                const items = processMsgList(e.add(0x18).readPointer());
                                if (items.length > 0) { chunk = items; break; }
                            }
                        } finally {
                            try { gcRoot.remove(e); } catch { /* best effort */ }
                        }
                        if (!chunk) break;  // plus d'action pour cette unité

                        const hasMove = chunk.some(
                            (it) => it.decoded.cls === "MoveUnitMessage");
                        const snap = hasMove ? captureStateForDemo(statePtr) : null;
                        for (const it of chunk) {
                            if (it.decoded.cls === "MoveUnitMessage" && snap
                                && it.decoded.unitId !== undefined) {
                                demos.push({
                                    turnIndex: turnsPlayed, player: playerId,
                                    activatedUnitId: it.decoded.unitId,
                                    move: {
                                        to: it.decoded.to ?? null,
                                        pathLen: it.decoded.pathLen ?? 0,
                                    },
                                    toActivate: snap.toActivate, units: snap.units,
                                });
                                totalActivations++;
                            }
                            if (applyAiMsgMi) {
                                invokeMethod(applyAiMsgMi.info, aiControl, [it.ptr]);
                            } else {
                                invokeMethod(runnerApplyMi!.info, runner, [it.ptr]);
                            }
                        }
                        const sp = runner.add(runnerOff.state).readPointer();
                        if (!sp.isNull()
                            && readBattleStatus(sp).currentTurnPlayer !== playerId) {
                            break;
                        }
                    }
                }
            } catch (e) {
                turnErr = (e as Error).message;
            }
            turnOrders.push({ turnIndex: turnsPlayed, player: playerId, order: playedThisTurn });
            if (turnErr) { stopReason = "turn err: " + turnErr; break; }
            turnsPlayed++;

            const sp2 = runner.add(runnerOff.state).readPointer();
            if (!sp2.isNull()) {
                const st2 = readBattleStatus(sp2);
                if (st2.stage === 1 && st2.currentTurnPlayer === playerId) {
                    try { applyEndTurn(runner); }
                    catch (e) {
                        stopReason = "endturn threw: " + (e as Error).message; break;
                    }
                }
            }
            if (totalActivations >= maxActivations) { stopReason = "maxActivations"; break; }
        }

        return {
            ok: true, runner: label, orderMode: order,
            turnsPlayed, totalActivations, totalPumps,
            ms: Date.now() - t0, stopReason,
            turnOrders, demoCount: demos.length, demos,
        };
    });

    /** DRY-RUN sur TOUTES les units du joueur courant : pour chaque squad
     *  contrôlé + vivant, pompe `CalculateNextActionForUnit(unit)` pour lire
     *  l'action proposée par l'IA — SANS appliquer. Read-only (vérifie
     *  mutated=false). Donne, contre le MÊME état courant, ce que ferait
     *  chaque unité « si elle jouait en premier ». body: { runnerId, maxPump? } */
    ctx.rpc.aiDryRunAllUnits = (
        body?: { runnerId?: number; maxPump?: number; resetTurnFlags?: boolean },
    ): Promise<unknown> => queueOnMainThread(() => {
        let runner: NativePointer; let label: string;
        if (typeof body?.runnerId === "number") {
            try { runner = getRunner(body.runnerId).runner; }
            catch (e) { return { ok: false, error: (e as Error).message }; }
            setTraceOrigin(body.runnerId);   // attribution des traces (cf. game/trace-origin.ts)
            label = "build#" + body.runnerId;
        } else if (state.liveRunner) {
            runner = state.liveRunner; label = "live";
        } else {
            return { ok: false, error: "no runner — pass runnerId" };
        }
        if (runner.isNull()) return { ok: false, error: label + " runner null" };
        const maxPump = (typeof body?.maxPump === "number" && body.maxPump > 0)
            ? body.maxPump : 30000;

        const statePtr = runner.add(runnerOff.state).readPointer();
        if (statePtr.isNull()) return { ok: false, error: "state null" };
        const status = readBattleStatus(statePtr);
        if (status.stage !== 1) {
            return { ok: false, runner: label,
                error: "stage " + (status.stageName ?? status.stage) };
        }
        const playerId = status.currentTurnPlayer;
        if (playerId === null) return { ok: false, error: "no currentTurnPlayer" };
        const aiControl = runner.add(runnerOff.aiControl).readPointer();
        if (aiControl.isNull()) return { ok: false, error: "aiControl null" };
        const { strategy } = resolveStrategy(aiControl, playerId);
        if (strategy.isNull()) return { ok: false, error: "strategy null" };
        const calcUnitMi = findMethod(
            strategy.readPointer(), "CalculateNextActionForUnit");
        if (!calcUnitMi) {
            return { ok: false, error: "CalculateNextActionForUnit not found" };
        }

        // Map squadId → (visualId, pos) pour identifier les unités (ex.
        // Terminators) et mesurer la distance du déplacement proposé.
        const proj = projectMatchState(statePtr);
        const visById = new Map<number, string | null>();
        const posById = new Map<number, { col: number; row: number } | null>();
        for (const u of proj.units) {
            visById.set(u.squadId, u.visualId);
            posById.set(u.squadId, u.pos);
        }

        const before = summarize(statePtr);
        const t0 = Date.now();

        // #296 — OPT-IN. Sans lui, rien ne change : le défaut reste la mesure « à l'état
        // courant », qui est la bonne pour un tour frais. Avec lui, on répond à l'autre
        // question : « que proposerait chaque unité si son tour n'était PAS entamé ? » —
        // seule façon d'obtenir un oracle de DÉCISION per-unité pour un SUMMON, dont le
        // natif termine le tour dès l'apparition (`SpawnUnitBehaviour$$
        // TriggerSpawnedUnitBehaviours` -> `FinishUnitTurn(spawned, isTerminated: true)`).
        const wantReset = body?.resetTurnFlags === true;
        if (wantReset && !turnFlagResetAvailable()) {
            // On REFUSE plutôt que de balayer sans reset : rendre un résultat
            // silencieusement identique au défaut ferait passer un capteur MORT pour une
            // mesure (même discipline de tri-état que `unitFlags`).
            return { ok: false, runner: label,
                error: "resetTurnFlags demandé mais non résolu : "
                    + turnFlagResetDiagnostic() };
        }
        const { units, pumps, turnFlagsReset } = sweepAllUnitProposals(
            statePtr, strategy, calcUnitMi, maxPump, { mi: null },
            { resetTurnFlags: wantReset });
        const after = summarize(statePtr);
        const unitsWithVis = units.map((u) => ({
            ...u,
            visualId: visById.get(u.unitId) ?? null,
            pos: posById.get(u.unitId) ?? null,
        }));
        const resets = turnFlagsReset ?? [];
        return {
            ok: true, runner: label, playerId,
            // ⚠ Avec `resetTurnFlags`, `mutated` est LA garde : il doit rester `false`.
            // `true` = la restauration a échoué et la mesure est à jeter.
            mutated: before.sig !== after.sig,
            totalPumps: pumps, ms: Date.now() - t0,
            unitCount: unitsWithVis.length, units: unitsWithVis,
            // `null` = non demandé ; `[]` = demandé et aucune unité n'avait de flag de tour.
            turnFlagsReset: wantReset
                ? resets.map((r) => ({ unitId: r.unitId, cleared: r.cleared,
                    notRestored: r.notRestored, error: r.error ?? null }))
                : null,
            turnFlagsRestoreFailed: wantReset
                ? resets.filter((r) => r.notRestored.length > 0).length : null,
            turnFlagsError: wantReset
                ? (resets.find((r) => r.error)?.error ?? null) : null,
        };
    });
}
