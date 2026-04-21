// Runner-side actions — RPC calls against the standalone runner currently
// being viewed (state.runnerId).

import { state } from "./state.js";
import { $, status } from "./dom.js";
import { api } from "./api.js";

export async function playTurn() {
    if (state.sessionId == null) {
        status("no active session — reload if the runner was launched outside");
        return;
    }
    if (state.runnerId == null) {
        status("no runner selected");
        return;
    }
    const btn = $("play-turn-btn");
    const setBtn = (txt, disabled) => {
        if (!btn) return;
        btn.disabled = !!disabled;
        btn.textContent = txt;
    };
    setBtn("PLAYING…", true);
    try {
        // playTurn(runnerId) fires CheatRunAIMessage on the registry runner.
        // The game's own AI decides the active team's turn. Events flow back
        // via the same battle_event stream as applyAddUnit / startBattle.
        const res = await api.rpc(state.sessionId, "playTurn",
            [{ runnerId: state.runnerId }], 60000);
        const n = res?.eventCount ?? 0;
        status("AI played turn · " + n + " events");
    } catch (e) {
        status("play turn failed: " + (e.message ?? e));
    } finally {
        setBtn("PLAY TURN", false);
    }
}
