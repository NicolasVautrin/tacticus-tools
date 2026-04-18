// applyStack + StreamDispatcher hooks — event trace correlated to triggers.
//
// Every call to runner.Apply / AiControl.Apply*AiMessage pushes a frame on
// applyStack (with a target array for events). StreamDispatcher.Action and
// StartGroup fire many times during each Apply; the hook reads the top of
// applyStack and appends events to its target array.
//
// With this, we can build a log like:
//   [{ src: "ai", cls: "MoveUnitMessage", unitId: 101,
//      events: [{kind:"action", step:3, entity:101, tags:{...}}, ...] }, ...]
//
// Frames for standalone dispatches are pushed/popped manually by the
// feature calling `runner.Apply` on the standalone runner.

import { findClass, findMethod } from "../il2cpp/helpers.js";

export interface StreamEvent {
    kind: "action" | "group";
    step?: number;    // action: StepType
    group?: number;   // group: GroupType
    entity: number;
    tags?: Record<string, unknown> | null;
    source?: string | null;
}

export interface ApplyFrame {
    role: "live" | "standalone";
    target: StreamEvent[];
}

export const applyStack: ApplyFrame[] = [];

export function pushApply(role: "live" | "standalone", target: StreamEvent[]): void {
    applyStack.push({ role, target });
}

export function popApply(): void {
    applyStack.pop();
}

// --- StreamDispatcher hooks ---
// Action(StepType, BEntityId, Dictionary<TagKey,int>)
// StartGroup(GroupType, BEntityId, string sourceId, BEntityId? initialTarget)

const streamDispClass = findClass(
    "BattleLogicAssembly.dll", "IdunBattle.Streams", "StreamDispatcher");
const streamActionMi = streamDispClass ? findMethod(streamDispClass, "Action") : null;
const streamGroupMi = streamDispClass ? findMethod(streamDispClass, "StartGroup") : null;

export function installStreamHooks(): void {
    if (streamActionMi && !streamActionMi.ptr.isNull()) {
        Interceptor.attach(streamActionMi.ptr, {
            onEnter(args) {
                if (applyStack.length === 0) return;
                const top = applyStack[applyStack.length - 1];
                try {
                    top.target.push({
                        kind: "action",
                        step: args[1].toInt32(),
                        entity: args[2].toInt32(),
                        // tags Dictionary — skip for now, rarely needed
                        tags: null,
                    });
                } catch { /* best effort */ }
            },
        });
    }
    if (streamGroupMi && !streamGroupMi.ptr.isNull()) {
        Interceptor.attach(streamGroupMi.ptr, {
            onEnter(args) {
                if (applyStack.length === 0) return;
                const top = applyStack[applyStack.length - 1];
                try {
                    let src: string | null = null;
                    try {
                        const sp = args[3];
                        if (!sp.isNull()) {
                            const len = sp.add(0x10).readS32();
                            if (len > 0 && len < 500) {
                                src = sp.add(0x14).readUtf16String(len);
                            }
                        }
                    } catch { /* ignore */ }
                    top.target.push({
                        kind: "group",
                        group: args[1].toInt32(),
                        entity: args[2].toInt32(),
                        source: src,
                    });
                } catch { /* best effort */ }
            },
        });
    }
}
