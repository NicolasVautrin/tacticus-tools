// hook: Player Input — human player actions only, with stack trace
// requires: _utils/il2cpp-helpers
// hooks: StateMachineActions.ApplyInput (Assembly-CSharp.dll / IdunBattle.View.FSM)
// output: send({t: "player", detail: {msg, ...}, stack: ["il2cpp+0x..."]})

hook("Assembly-CSharp.dll", "IdunBattle.View.FSM", "StateMachineActions", "ApplyInput", {
    onEnter: function (args) {
        var d = readMsgDetails(args[1]);
        send({ t: "player", detail: d, stack: getStack(this.context) });
    }
});
