// WebSocket subscription to the frida session. Dispatches battle events to
// the battle-log module.
//
// Auto-reconnect: on close, retries every 2s and resumes via `?last_event_id=N`
// so the host's ring buffer replays missed events after a host restart or
// transient network blip. Tracks the highest seen `id` from server-pushed
// events (publish() stamps it in ws.ts).

import { state } from "./state.js";
import { renderBattleEvent } from "./battle-log.js";
import { refreshRunners } from "./runners.js";

// Pluggable handlers per agent message kind. Lets feature modules subscribe
// to push events without ws.js needing to know about each one.
const wsHandlers = new Map();
export function registerWsHandler(t, fn) { wsHandlers.set(t, fn); }

const wsCtx = {
    sessionId: null,
    lastEventId: -1,
    reconnectTimer: null,
    attempt: 0,
};

function setIndicator(cls, label) {
    const ind = document.getElementById("ws-indicator");
    if (!ind) return;
    ind.className = "hdr-chip ws-indicator ws-indicator--" + cls;
    ind.textContent = "WS·" + label;
}

function openSocket() {
    if (wsCtx.sessionId == null) return;
    const proto = location.protocol === "https:" ? "wss:" : "ws:";
    const qs = wsCtx.lastEventId >= 0
        ? "?last_event_id=" + wsCtx.lastEventId : "";
    const url = proto + "//" + location.host + "/ws/run/"
        + wsCtx.sessionId + qs;
    const ws = new WebSocket(url);
    state.ws = ws;
    ws.onopen = () => {
        wsCtx.attempt = 0;
        setIndicator("up", "LIVE");
    };
    ws.onerror = () => setIndicator("err", "ERR");
    ws.onclose = () => {
        setIndicator("down", "OFF");
        // Don't retry if the session was explicitly replaced.
        if (wsCtx.sessionId == null) return;
        wsCtx.attempt = Math.min(wsCtx.attempt + 1, 10);
        const delay = Math.min(1000 + wsCtx.attempt * 500, 5000);
        setIndicator("wait", "RETRY " + Math.round(delay / 1000) + "s");
        wsCtx.reconnectTimer = setTimeout(openSocket, delay);
    };
    ws.onmessage = async (ev) => {
        try {
            const msg = JSON.parse(ev.data);
            if (typeof msg.id === "number" && msg.id > wsCtx.lastEventId) {
                wsCtx.lastEventId = msg.id;
            }
            const inner = msg?.payload?.payload;
            if (!inner?.t) return;
            // Dispatch to feature-specific handlers first (push notifications
            // like builder_ready). They get the full payload and decide what
            // to do.
            const h = wsHandlers.get(inner.t);
            if (h) { try { h(inner); } catch (err) { console.warn("ws handler", err); } }
            if (inner.t !== "battle_event") return;
            if (inner.runnerId !== state.runnerId) {
                refreshRunners();
                return;
            }
            renderBattleEvent(inner);
            refreshRunners();
        } catch (e) { console.warn("ws msg", e); }
    };
}

export function subscribeBattleEvents(sessionId) {
    // Always reopen the socket — even if we're already subscribed to this
    // session. Reason: launchBattle calls us right after /api/launch returns,
    // and the events from initRunner/applyAddUnit/startBattle were emitted
    // while state.runnerId was still null. The live socket received them but
    // the front-side filter (`inner.runnerId !== state.runnerId`) discarded
    // them. Reopening with `?last_event_id=-1` makes the host replay the
    // ring buffer from the start, after state.runnerId has been set —
    // events render correctly.
    //
    // Zombie sockets are prevented by detaching handlers BEFORE close() so
    // the close handshake fires no reconnect (cf. the comment below).
    if (wsCtx.reconnectTimer) {
        clearTimeout(wsCtx.reconnectTimer);
        wsCtx.reconnectTimer = null;
    }
    if (state.ws) {
        // Detach handlers BEFORE close(). close() is async — without nulling
        // these, the OLD socket's onclose would fire later, see a non-null
        // wsCtx.sessionId, and schedule a reconnect → zombie second WS.
        try {
            state.ws.onopen = null;
            state.ws.onerror = null;
            state.ws.onmessage = null;
            state.ws.onclose = null;
            state.ws.close();
        } catch { /* */ }
        state.ws = null;
    }
    wsCtx.sessionId = sessionId;
    wsCtx.lastEventId = -1;
    wsCtx.attempt = 0;
    openSocket();
}
