// hook: Recv handlers — bridge between backend POST and script queues
// requires: autoplay/action-queue, _utils/matchstate-reader
// provides: recv("action"), recv("rpc"), recv("query_state")

// --- Action commands (fire-and-forget via POST /api/scripts/{id}/message) ---
recv("action", function onAction(msg) {
    if (!runnerInstance) {
        send({t: "error", msg: "No runner instance yet"});
        recv("action", onAction);
        return;
    }
    pendingActions.push(msg.payload);
    send({t: "queued", cmd: msg.payload, pending: pendingActions.length});
    recv("action", onAction);
});

// --- RPC queries (POST /api/scripts/{id}/rpc) ---
recv("rpc", function onRpc(msg) {
    if (msg.method === "play") {
        // Blocking play: execute action, wait for isPlayerTurn
        if (pendingPlay) {
            // Already a play in flight — reject
            send({t: "rpc_response", id: msg.id, result: {error: "play already in progress"}});
        } else {
            pendingPlay = {id: msg.id, args: msg.args, executed: false};
        }
    } else {
        // Instant RPC (get_state, etc.)
        pendingRpc.push({id: msg.id, method: msg.method, args: msg.args || {}});
    }
    recv("rpc", onRpc);
});

// --- Legacy state query (kept for compatibility) ---
recv("query_state", function onQuery(msg) {
    try {
        send({t: "state", state: buildTurnSummary()});
    } catch(e) {
        send({t: "error", msg: "query failed: " + e.message});
    }
    recv("query_state", onQuery);
});

// --- Cleanup: signal ready for unload ---
// The backend waits for this ack + a short sleep before script.unload(),
// ensuring we're not in the middle of a NativeCallback (Interceptor.replace).
recv("cleanup", function(msg) {
    send({t: "cleanup_done"});
});

send({t: "autoplay_ready", msg: "Hooks installed. Play a turn to capture runner, then auto-play begins."});
