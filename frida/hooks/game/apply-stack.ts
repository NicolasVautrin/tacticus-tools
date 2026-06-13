// applyStack + StreamDispatcher hooks — event trace correlated to triggers.
//
// We hook directly on `IdunBattle.Streams.StreamDispatcher.Action` and
// `.StartGroup` — the dispatcher methods the game calls to emit events.
// Every event passes through here before any listener filtering, so we
// see the full unfiltered stream.
//
// Prereq: the main-thread pumps must use `Interceptor.replace` (not `attach`).
// Frida's `attach` applies a per-thread recursion guard that silently
// suppresses nested hook callbacks fired from inside another `attach`
// onEnter — so if the pump used `attach` and drained pending IL2CPP work
// synchronously in its callback, any hook on those methods would be dead.
// `replace` has no recursion guard. See runtime/main-pump.ts.

import { findClassAnywhere, findMethod } from "../il2cpp/helpers.js";
import { serializeToJson } from "../il2cpp/serializer.js";

export interface StreamEvent {
    kind: "action" | "group" | "finish";
    step?: number;    // action: StepType
    group?: number;   // group: GroupType (StartGroup ouvre ce scope)
    entity: number;   // finish: non significatif (FinishGroup ferme le dernier groupe ouvert)
    // JSON-serialized Dict<TagKey,int>. Host parses + gets enum names for free
    // via the game's Newtonsoft settings (StringEnumConverter registered globally).
    tags?: string | null;
    source?: string | null;
}

export interface ApplyFrame {
    role: "live" | "built" | "mirror";
    target: StreamEvent[];
}

export const applyStack: ApplyFrame[] = [];

export function pushApply(
    role: "live" | "built" | "mirror", target: StreamEvent[],
): void {
    applyStack.push({ role, target });
}

export function popApply(): void {
    applyStack.pop();
}

let streamHooksInstalled = false;
let _actionFiresTotal = 0;
let _actionFiresStackEmpty = 0;

export function streamHookStats(): Record<string, number> {
    return {
        actionFiresTotal: _actionFiresTotal,
        actionFiresStackEmpty: _actionFiresStackEmpty,
        applyStackDepth: applyStack.length,
        installed: streamHooksInstalled ? 1 : 0,
    };
}

function readManagedString(sp: NativePointer): string | null {
    if (sp.isNull()) return null;
    try {
        const len = sp.add(0x10).readS32();
        if (len > 0 && len < 500) return sp.add(0x14).readUtf16String(len);
    } catch { /* */ }
    return null;
}


export function ensureStreamHooks(): void {
    if (streamHooksInstalled) return;

    const cls = findClassAnywhere("IdunBattle.Streams", "StreamDispatcher");
    if (!cls) {
        send({ t: "stream_hooks_err", reason: "class-missing" });
        try { send({ t: "diag", msg: "[apply-stack] StreamDispatcher class not found — retry later" }); } catch { /* */ }
        // Pas de set installed=true → retry au prochain appel.
        return;
    }
    streamHooksInstalled = true;

    const actionMi = findMethod(cls, "Action");
    const groupMi = findMethod(cls, "StartGroup");
    const finishMi = findMethod(cls, "FinishGroup");

    if (actionMi && !actionMi.ptr.isNull()) {
        // Action(StepType stepType, BEntityId entityId, Dictionary<TagKey,int> tags)
        // ARM64 method entry: (this, stepType, entityId, tags, methodInfo)
        Interceptor.attach(actionMi.ptr, {
            onEnter(args) {
                _actionFiresTotal++;
                if (applyStack.length === 0) {
                    _actionFiresStackEmpty++;
                    return;
                }
                try {
                    applyStack[applyStack.length - 1].target.push({
                        kind: "action",
                        step: args[1].toInt32(),
                        entity: args[2].toInt32(),
                        tags: serializeToJson(args[3]),
                    });
                } catch { /* */ }
            },
        });
    }

    if (groupMi && !groupMi.ptr.isNull()) {
        // StartGroup(GroupType, BEntityId, string, Nullable<BEntityId>)
        Interceptor.attach(groupMi.ptr, {
            onEnter(args) {
                if (applyStack.length === 0) return;
                try {
                    applyStack[applyStack.length - 1].target.push({
                        kind: "group",
                        group: args[1].toInt32(),
                        entity: args[2].toInt32(),
                        source: readManagedString(args[3]),
                    });
                } catch { /* */ }
            },
        });
    }

    if (finishMi && !finishMi.ptr.isNull()) {
        // FinishGroup(this) — paramétrless : ferme le DERNIER groupe ouvert
        // (discipline de pile). On pousse un marqueur de fermeture pour que
        // l'ingest puisse reconstruire le nesting des scopes (chaque action
        // connaît son groupe englobant = ex. User_UseAbility/NormalAttack →
        // entité acteur, qui encadre le Info arme + ses UnitDamaged).
        Interceptor.attach(finishMi.ptr, {
            onEnter() {
                if (applyStack.length === 0) return;
                try {
                    applyStack[applyStack.length - 1].target.push({
                        kind: "finish",
                        entity: 0,
                    });
                } catch { /* */ }
            },
        });
    }

    Interceptor.flush();
    send({ t: "stream_hooks_installed",
        actionPtr: actionMi?.ptr.toString() ?? null,
        groupPtr: groupMi?.ptr.toString() ?? null,
        finishPtr: finishMi?.ptr.toString() ?? null,
    });
    try {
        send({ t: "diag", msg: "[apply-stack] stream hooks installed: "
            + "Action=" + (actionMi?.ptr.toString() ?? "missing")
            + " StartGroup=" + (groupMi?.ptr.toString() ?? "missing")
            + " FinishGroup=" + (finishMi?.ptr.toString() ?? "missing") });
    } catch { /* */ }
}
