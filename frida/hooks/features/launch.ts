// Phase 3 launch — build an isolated IdunRunner from a JSON config, apply
// AddUnitMessages for each player placement, then StartMatch and stream events.
//
// RPCs:
//   initRunner({configJson})                      → {runnerId, seed}
//   applyAddUnit({runnerId, unitId, playerId, col, row}) → {events: N}
//   startBattle({runnerId})                       → {events: N}
//   snapshotState({runnerId})                     → { ok }
//   listRunners()                                 → [{runnerId, started, seed}]
//   disposeRunner({runnerId})                     → { removed }
//
// Each RPC emits `send({t:"battle_event", runnerId, msg, events})` with the
// StreamDispatcher events fired during the Apply/StartMatch call. The host
// forwards these to subscribed WebSocket clients.

import {
    findClass, findCtorByParamCount,
} from "../il2cpp/helpers.js";
import {
    createManagedString, createObject, il2cpp_object_new, invokeMethod,
} from "../il2cpp/invoke.js";
import { gcRoot } from "../il2cpp/gc-root.js";
import {
    deserializeFromJson, isDeserializerReady,
} from "../il2cpp/serializer.js";
import {
    buildRunner, runnerApplyMi, runnerStartMatchMi, runnerOff,
} from "../game/runner.js";
import { cheatRunAiClass } from "../game/ai-control.js";
import {
    registerRunner, getRunner, listRunners, disposeRunner,
} from "../game/runner-registry.js";
import {
    pushApply, popApply, ensureStreamHooks, StreamEvent,
} from "../game/apply-stack.js";
import { serializeToJson } from "../il2cpp/serializer.js";
import { queueOnMainThread } from "../runtime/queue.js";
import { Ctx } from "../controller.js";

const battleConfigClass = findClass(
    "BattleLogicAssembly.dll",
    "IdunBattle.Configuration",
    "BattleConfiguration",
);

const addUnitMsgClass = findClass(
    "BattleLogicAssembly.dll",
    "IdunBattle.Messages",
    "AddUnitMessage",
);
const addUnitMsgCtor4 = addUnitMsgClass
    ? findCtorByParamCount(addUnitMsgClass, 4) : null;

function buildAddUnitMessage(
    unitId: string, playerId: number, col: number, row: number,
): NativePointer {
    if (!addUnitMsgClass) throw new Error("AddUnitMessage class not found");
    if (!addUnitMsgCtor4) throw new Error("AddUnitMessage 4-arg ctor not found");
    const msg = il2cpp_object_new(addUnitMsgClass) as NativePointer;
    if (msg.isNull()) throw new Error("il2cpp_object_new(AddUnitMessage) returned null");
    gcRoot.add(msg);

    const unitIdStr = createManagedString(unitId);
    // PlayerId is a struct wrapping an int32 — passed as pointer to 4 raw bytes.
    const pidBuf = Memory.alloc(4); pidBuf.writeS32(playerId);
    const colBuf = Memory.alloc(4); colBuf.writeS32(col);
    const rowBuf = Memory.alloc(4); rowBuf.writeS32(row);

    invokeMethod(addUnitMsgCtor4.info, msg, [unitIdStr, pidBuf, colBuf, rowBuf]);
    // The 4-arg ctor leaves SpawnSource at its default (Unknown=0). The live
    // game writes Deployment=5 for user pre-battle placements — without it,
    // InputMessageProcessor routes the unit to the wrong player (env instead
    // of the intended owner), leaving the human side empty.
    msg.add(0x28).writeS32(5);
    return msg;
}

function captureEvents(
    runnerId: number, runnerPtr: NativePointer, label: string,
    body: () => void,
): StreamEvent[] {
    ensureStreamHooks();
    const events: StreamEvent[] = [];
    pushApply("built", events);
    try {
        body();
    } finally {
        popApply();
    }
    // Snapshot MatchState AFTER the apply so the host sees the post-state.
    let matchState: string | null = null;
    try {
        const statePtr = runnerPtr.add(runnerOff.state).readPointer();
        if (!statePtr.isNull()) matchState = serializeToJson(statePtr);
    } catch { /* best effort */ }
    try {
        send({ t: "battle_event", runnerId, msg: label, events, matchState });
    } catch { /* best effort */ }
    return events;
}

export function register(ctx: Ctx): void {

    ctx.rpc.initRunner = (args: { configJson: string }) => {
        if (!isDeserializerReady()) {
            throw new Error("Newtonsoft DeserializeObject not resolved");
        }
        if (!battleConfigClass) {
            throw new Error("BattleConfiguration class not found");
        }
        return queueOnMainThread(() => {
            gcRoot.init();
            const configPtr = deserializeFromJson(args.configJson, battleConfigClass);
            gcRoot.add(configPtr);
            const r = buildRunner(configPtr);
            const entry = registerRunner(r);
            return { runnerId: entry.runnerId, seed: entry.seed };
        });
    };

    ctx.rpc.applyAddUnit = (args: {
        runnerId: number; unitId: string; playerId: number; col: number; row: number;
    }) => {
        const applyMi = runnerApplyMi;
        if (!applyMi) throw new Error("IdunRunner.Apply not resolved");
        return queueOnMainThread(() => {
            const entry = getRunner(args.runnerId);
            const msg = buildAddUnitMessage(args.unitId, args.playerId, args.col, args.row);
            const events = captureEvents(args.runnerId, entry.runner,
                "AddUnitMessage", () => {
                    invokeMethod(applyMi.info, entry.runner, [msg]);
                });
            return { ok: true, eventCount: events.length };
        });
    };

    ctx.rpc.startBattle = (args: { runnerId: number }) => {
        const startMi = runnerStartMatchMi;
        if (!startMi) throw new Error("IdunRunner.StartMatch not resolved");
        return queueOnMainThread(() => {
            const entry = getRunner(args.runnerId);
            if (entry.started) throw new Error("battle already started");
            const events = captureEvents(args.runnerId, entry.runner,
                "StartMatch", () => {
                    invokeMethod(startMi.info, entry.runner, null);
                });
            entry.started = true;
            return { ok: true, eventCount: events.length };
        });
    };

    ctx.rpc.listRunners = () => listRunners();

    ctx.rpc.disposeRunner = (args: { runnerId: number }) => {
        const removed = disposeRunner(args.runnerId);
        return { removed };
    };

    // Fire CheatRunAIMessage on a registry runner. Delegates turn-play to
    // the game's own AI. Whoever's turn is currently active on that runner
    // gets played. Events stream out via the same `battle_event` path as
    // applyAddUnit / startBattle.
    ctx.rpc.playTurn = (args: { runnerId: number }) => {
        if (!cheatRunAiClass) throw new Error("CheatRunAIMessage class not found");
        const applyMi = runnerApplyMi;
        if (!applyMi) throw new Error("IdunRunner.Apply not resolved");
        const klass = cheatRunAiClass;
        return queueOnMainThread(() => {
            const entry = getRunner(args.runnerId);
            const msg = createObject(klass);
            gcRoot.add(msg);
            const events = captureEvents(args.runnerId, entry.runner,
                "PlayTurn", () => {
                    invokeMethod(applyMi.info, entry.runner, [msg]);
                });
            return { ok: true, eventCount: events.length };
        });
    };
}
