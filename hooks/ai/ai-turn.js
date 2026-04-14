// hook: AI Turn — fires when AI starts computing actions for a player (throttled to 1 log/2s)
// requires: _utils/il2cpp-helpers
// hooks: AiControl.RunComputerActionsForPlayer (BattleLogicAssembly.dll / IdunBattle.Core.Services)
// output: send({t: "ai_turn"})

var lastAiLog = 0;
hook("BattleLogicAssembly.dll", "IdunBattle.Core.Services", "AiControl", "RunComputerActionsForPlayer", {
    onEnter: function (args) {
        var now = Date.now();
        if (now - lastAiLog < 2000) return;
        lastAiLog = now;
        send({ t: "ai_turn" });
    }
});
