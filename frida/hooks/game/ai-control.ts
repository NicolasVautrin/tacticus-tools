// AiControl class + entry methods + CheatRunAIMessage class.
//
// AiControl.ApplyAiMessage / ApplyHumanAiMessage are the entry points for
// AI sub-message dispatch. We hook them on live to capture the AI's
// decisions; we also re-invoke them on live to *commit* decisions computed
// by our runner.
//
// CheatRunAIMessage is a debug/cheat IInputMessage that fires the AI for
// the current turn player. We apply it via runner.Apply on the runner
// so its inner AI decides; on live we use it as a fallback direct-play.

import {
    class_get_fields, class_get_name, field_get_name, field_get_offset,
    field_get_type, findClass, findClassAnywhere, findMethod, s,
    type_get_class_or_element_class,
} from "../il2cpp/helpers.js";

export const aiControlClass = findClass(
    "BattleLogicAssembly.dll", "IdunBattle.Core.Services", "AiControl");
if (!aiControlClass) throw new Error("AiControl class not found");

export const applyAiMsgMi = findMethod(aiControlClass, "ApplyAiMessage");
export const applyHumanAiMsgMi = findMethod(aiControlClass, "ApplyHumanAiMessage");

if (!applyAiMsgMi) throw new Error("AiControl.ApplyAiMessage not found");

export const cheatRunAiClass = findClass(
    "BattleLogicAssembly.dll", "IdunBattle.Messages", "CheatRunAIMessage");
if (!cheatRunAiClass) throw new Error("CheatRunAIMessage class not found");

// One-shot probe: dump fields of AiControl + MoveUnitMessage to find any
// RNG / random / seed field that might need explicit sync on the mirror.
// Fires on first module load, sends `diag` events the host JSONL captures.
function dumpClassFields(klass: NativePointer | null, label: string): void {
    if (!klass) {
        send({ t: "diag", msg: "[probe] " + label + " · class not found" });
        return;
    }
    const it = Memory.alloc(Process.pointerSize);
    it.writePointer(ptr(0));
    let f: NativePointer;
    let count = 0;
    while (!(f = class_get_fields(klass, it) as NativePointer).isNull()) {
        const name = s(field_get_name(f) as NativePointer);
        const off = field_get_offset(f) as number;
        const tPtr = field_get_type(f) as NativePointer;
        let tname = "?";
        try {
            const k = type_get_class_or_element_class(tPtr) as NativePointer;
            if (!k.isNull()) {
                tname = s(class_get_name(k) as NativePointer);
            }
        } catch { /* keep "?" */ }
        send({
            t: "diag",
            msg: "[probe] " + label + "." + name
                + " @ +0x" + off.toString(16) + " · type=" + tname,
        });
        count++;
        if (count > 80) break;
    }
}

let probeDumped = false;
export function dumpAiRngProbe(aiCtrl?: NativePointer): void {
    if (probeDumped) return;
    probeDumped = true;
    dumpClassFields(aiControlClass, "AiControl");
    dumpClassFields(
        findClassAnywhere("IdunBattle.Strategies", "WithSomeRandomnessStrategy")
        ?? findClassAnywhere(
            "IdunBattle.Core.Strategies", "WithSomeRandomnessStrategy")
        ?? findClassAnywhere(
            "IdunBattle.Core.Services", "WithSomeRandomnessStrategy"),
        "WithSomeRandomnessStrategy");
    dumpClassFields(
        findClassAnywhere("IdunBattle.Messages", "MoveUnitMessage"),
        "MoveUnitMessage");
    dumpClassFields(
        findClassAnywhere("IdunBattle.Messages", "ActiveAbilityMessage"),
        "ActiveAbilityMessage");

    // Runtime read of live aiControl._randomizeInput + the 2 strategy ptrs.
    // If `_randomizeInput=true` AND a strategy is non-null → live IS
    // mutating AI messages before forwarding to the runner.
    if (aiCtrl && !aiCtrl.isNull()) {
        try {
            const randomizeInput = aiCtrl.add(0x70).readU8();
            const randomStrat = aiCtrl.add(0x60).readPointer();
            const humanRandomStrat = aiCtrl.add(0x68).readPointer();
            send({
                t: "diag",
                msg: "[probe] AiControl runtime · _randomizeInput="
                    + randomizeInput
                    + " · _randomStrategy=" + randomStrat
                    + " · _randomHumanAIStrategy=" + humanRandomStrat,
            });
        } catch (e) {
            send({
                t: "diag",
                msg: "[probe] AiControl runtime read failed: "
                    + (e as Error).message,
            });
        }
    }
}
