// hook: Turn observer — capture runner, Apply messages, StreamDispatcher mutations, player turn
// requires: _utils/il2cpp-helpers, _utils/il2cpp-invoke, _utils/matchstate-reader, autoplay/action-queue

var _lastTurnSent = 0;

// --- Hook Apply: capture runner + log every message ---
hook("BattleLogicAssembly.dll", "IdunBattle.Runner", "IdunRunner", "Apply", {
    onEnter: function(args) {
        runnerInstance = args[0];

        try {
            var details = readMsgDetails(args[1]);

            if (details.msg === "CheatMoveUnitMessage") {
                details.stack = getStack(this.context);
            }

            send({t: "apply", msg: details});
        } catch(e) {}
    },
    onLeave: function(retval) {
        if (pendingPlay) return;
        var now = Date.now();
        if (now - _lastTurnSent < 500) return;
        if (isPlayerTurn()) {
            _lastTurnSent = now;
            send({t: "your_turn"});
        }
    }
});

// --- Hook ApplyAiMessage: capture AI-specific actions ---
hook("BattleLogicAssembly.dll", "IdunBattle.Core.Services", "AiControl", "ApplyAiMessage", {
    onEnter: function(args) {
        try {
            var details = readMsgDetails(args[1]);
            details._src = "AI";
            send({t: "apply", msg: details});
        } catch(e) {}
    }
});

// --- Hook StreamDispatcher: capture ALL mutations ---
// Action(StepType actionType, BEntityId entityId, Dictionary<TagKey, int> tags)
// StepType and BEntityId are value types (ints), tags is a reference type
hook("BattleLogicAssembly.dll", "IdunBattle.Streams", "StreamDispatcher", "Action", {
    onEnter: function(args) {
        try {
            // args[0] = this, args[1] = StepType (int), args[2] = BEntityId (int),
            // args[3] = Dictionary<TagKey, int> (pointer)
            var stepType = args[1].toInt32();
            var entityId = args[2].toInt32();

            var tags = null;
            try { tags = readDict(args[3], 0); } catch(e) {}

            var evt = {
                step: {_enum: "IdunBattle.Streams.StepType", _value: stepType},
                entity: entityId,
                tags: tags
            };
            send({t: "stream", evt: evt});

            if (pendingPlay && pendingPlay.executed) {
                events.push(evt);
            }
        } catch(e) {}
    }
});

// StartGroup(GroupType, BEntityId, string sourceId, BEntityId? initialTarget)
hook("BattleLogicAssembly.dll", "IdunBattle.Streams", "StreamDispatcher", "StartGroup", {
    onEnter: function(args) {
        try {
            var groupType = args[1].toInt32();
            var entityId = args[2].toInt32();
            var sourceId = readIl2cppString(args[3]);

            var evt = {
                group: {_enum: "IdunBattle.Streams.GroupType", _value: groupType},
                entity: entityId,
                source: sourceId
            };
            send({t: "stream_group", evt: evt});

            if (pendingPlay && pendingPlay.executed) {
                events.push(evt);
            }
        } catch(e) {}
    }
});

// --- Diagnostic hooks: log validation failures ---
var _moveOpClass = findClass("BattleLogicAssembly.dll", "IdunBattle.Operations", "MoveUnitOperation");

if (_moveOpClass) {
    var _validationMethods = ["IsAllowedToMove", "TilesAreWalkable", "TilesAreEmpty", "TilesMatchUnitFeetCount"];
    for (var vi = 0; vi < _validationMethods.length; vi++) {
        (function(name) {
            var info = findMethod(_moveOpClass, name);
            if (info) {
                Interceptor.attach(info.ptr, {
                    onLeave: function(retval) {
                        if (retval.toInt32() === 0) {
                            var evt = {_validation: name, passed: false};
                            send({t: "validation_failed", evt: evt});
                            if (pendingPlay && pendingPlay.executed) events.push(evt);
                        }
                    }
                });
                console.log("[+] MoveUnitOperation." + name);
            }
        })(_validationMethods[vi]);
    }
}

console.log("[*] Turn observer loaded");