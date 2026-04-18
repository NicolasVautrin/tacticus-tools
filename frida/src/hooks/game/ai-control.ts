// AiControl class + entry methods + CheatRunAIMessage class.
//
// AiControl.ApplyAiMessage / ApplyHumanAiMessage are the entry points for
// AI sub-message dispatch. We hook them on live to capture the AI's
// decisions; we also re-invoke them on live to *commit* decisions computed
// by our standalone runner.
//
// CheatRunAIMessage is a debug/cheat IInputMessage that fires the AI for
// the current turn player. We apply it via runner.Apply on the standalone
// so its inner AI decides; on live we use it as a fallback direct-play.

import { findClass, findMethod } from "../il2cpp/helpers.js";

export const aiControlClass = findClass(
    "BattleLogicAssembly.dll", "IdunBattle.Core.Services", "AiControl");
if (!aiControlClass) throw new Error("AiControl class not found");

export const applyAiMsgMi = findMethod(aiControlClass, "ApplyAiMessage");
export const applyHumanAiMsgMi = findMethod(aiControlClass, "ApplyHumanAiMessage");

if (!applyAiMsgMi) throw new Error("AiControl.ApplyAiMessage not found");

export const cheatRunAiClass = findClass(
    "BattleLogicAssembly.dll", "IdunBattle.Messages", "CheatRunAIMessage");
if (!cheatRunAiClass) throw new Error("CheatRunAIMessage class not found");
