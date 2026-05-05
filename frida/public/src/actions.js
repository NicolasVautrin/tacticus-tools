// Runner-side actions — RPC calls against the standalone runner currently
// being viewed (state.runnerId).

import { state } from "./state.js";
import { $, status } from "./dom.js";
import { api } from "./api.js";

/** Apply current `state.battleEnded` to the PLAY TURN button + log status.
 * Exposed so battle-log.js can call it as soon as a FinishMatch event lands
 * via the WS stream (without waiting for the next playTurn RPC return). */
export function onBattleEndedRender() {
    const btn = $("play-turn-btn");
    if (!btn) return;
    if (state.battleEnded && state.battleEnded.runnerId === state.runnerId) {
        btn.disabled = true;
        btn.textContent = "BATTLE ENDED";
        btn.classList.add("btn-major--ended");
        const w = state.battleEnded.winner;
        const winLabel = (w === null || w === undefined) ? "" : ` · winner P${w}`;
        status(`Battle finished${winLabel} (runner ${state.battleEnded.runnerId})`);
    } else {
        btn.disabled = false;
        btn.textContent = "PLAY TURN";
        btn.classList.remove("btn-major--ended");
    }
}

export async function playTurn() {
    if (state.sessionId == null) {
        status("no active session — reload if the runner was launched outside");
        return;
    }
    if (state.runnerId == null) {
        status("no runner selected");
        return;
    }
    if (state.battleEnded && state.battleEnded.runnerId === state.runnerId) {
        status("battle already ended for runner " + state.runnerId);
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

        // Belt-and-suspenders end-of-battle detection: if the streamed events
        // already raised it, state.battleEnded is set; otherwise inspect the
        // post-apply BattleStatus snapshot returned by the agent.
        const post = res?.postStatus;
        if (post && post.stageName && post.stageName !== "Running"
            && (!state.battleEnded || state.battleEnded.runnerId !== state.runnerId)) {
            state.battleEnded = {
                runnerId: state.runnerId,
                winner: typeof post.winner === "number" ? post.winner : null,
                stageName: post.stageName,
                finishedAt: Date.now(),
                source: "postStatus",
            };
        }
        if (state.battleEnded && state.battleEnded.runnerId === state.runnerId) {
            onBattleEndedRender();
            return;
        }
        status("AI played turn · " + n + " events");
    } catch (e) {
        status("play turn failed: " + (e.message ?? e));
    } finally {
        // Only flip the button back to PLAY TURN if the battle is still live.
        if (!state.battleEnded || state.battleEnded.runnerId !== state.runnerId) {
            setBtn("PLAY TURN", false);
        }
    }
}
