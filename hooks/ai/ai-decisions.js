// hook: AI Decisions — per-unit tactic calculation + selected action type logging
// requires: _utils/il2cpp-helpers
// hooks: DefaultAiUnitTactic.CalculateNextActionForUnit (BattleLogicAssembly.dll / IdunBattle.AI.Tactics)
//        NullBattleAILogger.AddSelectedAction (BattleLogicAssembly.dll / IdunBattleLogic.AILog)
// output: send({t: "ai_unit_calc"})
//         send({t: "ai_decision", action: "Move"|"Ability"|"EndTurn"|"Skip"})

hook("BattleLogicAssembly.dll", "IdunBattle.AI.Tactics", "DefaultAiUnitTactic", "CalculateNextActionForUnit", {
    onEnter: function (args) {
        send({ t: "ai_unit_calc" });
    }
});

var actionTypes = { 0: "Move", 1: "Ability", 2: "EndTurn", 3: "Skip" };
hook("BattleLogicAssembly.dll", "IdunBattleLogic.AILog", "NullBattleAILogger", "AddSelectedAction", {
    onEnter: function (args) {
        send({ t: "ai_decision", action: actionTypes[args[1].toInt32()] || args[1].toInt32() });
    }
});
