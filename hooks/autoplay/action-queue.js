// hook: Action queue — execute actions + RPC on the main thread via Update
// requires: _utils/il2cpp-helpers, _utils/il2cpp-invoke, _utils/matchstate-reader, autoplay/message-factory
// provides: pendingActions, pendingRpc, pendingPlay, events
//
// Uses Interceptor.replace (not attach) so that nested Interceptor hooks
// on methods called during Apply (StreamDispatcher, MoveUnitOperation, etc.)
// fire correctly — Frida suppresses nested hooks inside attach callbacks
// (same-thread suppression) but not inside replace functions.

var pendingActions = [];
var pendingRpc = [];
var pendingPlay = null; // {id, args, executed}
var events = [];

var _gameViewsClass = findClass("Assembly-CSharp.dll", "IdunBattle.View.Game", "IdunGameViews");
var _gvRunnerOff = _gameViewsClass ? getFieldOffset(_gameViewsClass, "_runner") : -1;
var _updateMethod = _gameViewsClass ? findMethod(_gameViewsClass, "Update") : null;

if (_updateMethod) {
    var _originalUpdate = new NativeFunction(_updateMethod.ptr, "void", ["pointer", "pointer"]);

    Interceptor.replace(_updateMethod.ptr, new NativeCallback(function(self, methodInfo) {
        // --- Capture runner from GameViews._runner ---
        if (!runnerInstance && _gvRunnerOff >= 0) {
            var r = self.add(_gvRunnerOff).readPointer();
            if (!r.isNull()) {
                runnerInstance = r;
                console.log("[+] Runner captured from GameViews");
            }
        }

        // --- Instant RPCs — always process, even without runner ---
        if (pendingRpc.length > 0) {
            var req = pendingRpc.shift();
            try {
                var result = null;
                if (req.method === "get_state") {
                    result = getSerializedState(req.args.depth);
                } else if (req.method === "get_reachable_tiles") {
                    result = queryReachableTiles(req.args.unitId);
                } else if (req.method === "get_damage_prediction") {
                    result = queryDamagePrediction(req.args.attackerId, req.args.defenderId);
                } else {
                    result = {error: "unknown RPC method: " + req.method};
                }
                send({t: "rpc_response", id: req.id, result: result});
            } catch(e) {
                send({t: "rpc_response", id: req.id, result: {error: e.message}});
            }
        }

        if (runnerInstance) {
            // --- Blocking play: execute then wait for player turn ---
            if (pendingPlay) {
                if (!pendingPlay.executed) {
                    events = [];
                    pendingPlay.executed = true;
                    try {
                        var message = createMessage(pendingPlay.args);
                        invokeMethod(runnerApplyInfo.info, runnerInstance, [message]);
                    } catch(e) {
                        send({t: "rpc_response", id: pendingPlay.id, result: {error: "play failed: " + e.message}});
                        pendingPlay = null;
                    }
                } else {
                    if (isPlayerTurn()) {
                        try {
                            var state = getSerializedState();
                            if (state) state._events = events;
                            send({t: "rpc_response", id: pendingPlay.id, result: state});
                        } catch(e) {
                            send({t: "rpc_response", id: pendingPlay.id, result: {error: e.message}});
                        }
                        pendingPlay = null;
                        events = [];
                    }
                }
            }
            // --- Fire-and-forget actions (via POST /message) ---
            else if (pendingActions.length > 0) {
                var cmd = pendingActions.shift();
                try {
                    var msg = createMessage(cmd);
                    invokeMethod(runnerApplyInfo.info, runnerInstance, [msg]);
                    send({t: "played", cmd: cmd});
                } catch(e) {
                    send({t: "error", msg: "play failed: " + e.message});
                }
            }
        }

        // Call original Update
        _originalUpdate(self, methodInfo);
    }, "void", ["pointer", "pointer"]));

    console.log("[+] IdunGameViews.Update (replaced)");
} else {
    console.log("[-] IdunGameViews.Update not found");
}

console.log("[*] Action queue loaded");