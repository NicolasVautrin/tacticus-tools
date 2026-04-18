// hook: Battle End — PvP battle result
// requires: _utils/il2cpp-helpers
// hooks: ShowPvpBattleEndCommand.Execute (Assembly-CSharp.dll / idun.shared.commands)
// output: send({t: "battle_end", win: true|false})

hook("Assembly-CSharp.dll", "idun.shared.commands", "ShowPvpBattleEndCommand", "Execute", {
    onEnter: function (args) {
        send({ t: "battle_end", win: args[1].toInt32() !== 0 });
    }
});
