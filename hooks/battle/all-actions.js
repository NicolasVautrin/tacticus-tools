// hook: All Actions — central hook, every combat action (player + AI) passes through
// requires: _utils/il2cpp-helpers
// hooks: IdunRunner.Apply (BattleLogicAssembly.dll / IdunBattle.Runner)
// output: send({t: "action", detail: {msg, unitId?, casterId?, targetId?, abilityType?, inner?}})

hook("BattleLogicAssembly.dll", "IdunBattle.Runner", "IdunRunner", "Apply", {
    onEnter: function (args) {
        var d = readMsgDetails(args[1]);
        send({ t: "action", detail: d });
    }
});
