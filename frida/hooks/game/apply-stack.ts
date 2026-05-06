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
    kind: "action" | "group";
    step?: number;    // action: StepType
    group?: number;   // group: GroupType
    entity: number;
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
    streamHooksInstalled = true;

    const cls = findClassAnywhere("IdunBattle.Streams", "StreamDispatcher");
    if (!cls) { send({ t: "stream_hooks_err", reason: "class-missing" }); return; }

    const actionMi = findMethod(cls, "Action");
    const groupMi = findMethod(cls, "StartGroup");

    if (actionMi && !actionMi.ptr.isNull()) {
        // Action(StepType stepType, BEntityId entityId, Dictionary<TagKey,int> tags)
        // ARM64 method entry: (this, stepType, entityId, tags, methodInfo)
        Interceptor.attach(actionMi.ptr, {
            onEnter(args) {
                if (applyStack.length === 0) return;
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

    Interceptor.flush();
    send({ t: "stream_hooks_installed" });
}
