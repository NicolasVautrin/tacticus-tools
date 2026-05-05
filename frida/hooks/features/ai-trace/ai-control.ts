// AI control hooks: action selected + turn boundaries.
//
// `AiControl.RunComputerActionsForPlayer(BEntityId)` is the top-level
// entry point invoked once per AI player turn — onEnter gives us the
// turn fence (`ai_turn_begin`). The method returns an IEnumerator
// (coroutine) so onLeave fires immediately at allocation time, not at
// turn end — we only emit `ai_turn_begin`. The next `ai_turn_begin`
// implicitly closes the prior turn's bracket.
//
// `AiControl.ApplyAiMessage(IInputMessage)` fires once per applied AI
// message — these are the actions the AI actually committed to (ability
// use, unit movement, end-turn). This is the "winner" signal: the
// preceding playbook_action events with their utilities show what was
// considered, this event shows what was picked.

import { findClass, findMethod } from "../../il2cpp/helpers.js";
import { abilityName } from "../../data/ability-names.js";
import {
    traceState, installStatus,
    emit, safeKlassName, entityNameOrId,
} from "./state.js";

/** Read List<Position> at a heap pointer. Position is an inline
 * 8-byte {Column,Row} struct stored in the array starting at +0x20. */
function readPositionList(
    listPtr: NativePointer, max = 32,
): Array<{ col: number; row: number }> {
    if (listPtr.isNull()) return [];
    try {
        const items = listPtr.add(0x10).readPointer();
        const size = listPtr.add(0x18).readS32();
        if (items.isNull() || size <= 0 || size > 1000) return [];
        const out: Array<{ col: number; row: number }> = [];
        const n = Math.min(size, max);
        for (let i = 0; i < n; i++) {
            const base = items.add(0x20 + i * 8);
            out.push({ col: base.readS32(), row: base.add(0x4).readS32() });
        }
        return out;
    } catch { return []; }
}

/** Decode the per-class fields of an IInputMessage. Cls names match
 * IL2CPP class names (no namespace). BEntityId fields are resolved via
 * the projection cache, falling back to `id:N` if the entity hasn't
 * been seen yet. */
function decodeAiMessage(
    msgPtr: NativePointer, cls: string,
): Record<string, unknown> {
    try {
        switch (cls) {
            case "ActiveAbilityMessage":
                return {
                    caster: entityNameOrId(msgPtr.add(0x10).readS32()),
                    target: entityNameOrId(msgPtr.add(0x14).readS32()),
                    ability: abilityName(msgPtr.add(0x18).readS32()),
                };
            case "MoveUnitMessage": {
                const unit = entityNameOrId(msgPtr.add(0x10).readS32());
                const listPtr = msgPtr.add(0x18).readPointer();
                return { unit, path: readPositionList(listPtr) };
            }
            case "FinishUnitTurnMessage":
                return { unit: entityNameOrId(msgPtr.add(0x10).readS32()) };
            case "EndTurnMessage":
                return {};
            default:
                return {};
        }
    } catch { return {}; }
}

export function installAiControlHooks(): void {
    const aiClass = findClass(
        "BattleLogicAssembly.dll",
        "IdunBattle.Core.Services", "AiControl");
    if (!aiClass) {
        installStatus.AiControl = "class not found";
        return;
    }

    const am = findMethod(aiClass, "ApplyAiMessage");
    if (am && !am.ptr.isNull()) {
        try {
            Interceptor.attach(am.ptr, {
                onEnter(args): void {
                    if (!traceState.enabled.L1) return;
                    const msgPtr = args[1];
                    if (msgPtr.isNull()) return;
                    let cls = "?";
                    try {
                        cls = safeKlassName(msgPtr.readPointer());
                    } catch { /* ? */ }
                    const decoded = decodeAiMessage(msgPtr, cls);
                    emit({ evt: "ai_action_applied", kind: cls, ...decoded });
                },
            });
            installStatus.ApplyAiMessage = "ok";
        } catch (e) {
            installStatus.ApplyAiMessage = "attach_failed: "
                + (e as Error).message;
        }
    } else {
        installStatus.ApplyAiMessage = "method not found";
    }

    // BEntityId is a 4-byte struct, passed by value in RDX (= args[1]).
    const rc = findMethod(aiClass, "RunComputerActionsForPlayer");
    if (rc && !rc.ptr.isNull()) {
        try {
            Interceptor.attach(rc.ptr, {
                onEnter(args): void {
                    if (!traceState.enabled.L1) return;
                    emit({
                        evt: "ai_turn_begin",
                        playerEntityId: args[1].toInt32(),
                    });
                },
            });
            installStatus.RunComputerActions = "ok";
        } catch (e) {
            installStatus.RunComputerActions = "attach_failed: "
                + (e as Error).message;
        }
    } else {
        installStatus.RunComputerActions = "method not found";
    }
}
