// Tacticus admin panel: live status banner + INJECT button.
//
// Polls /api/admin/status every 3s. The banner is the source of truth for
// "is the game running, is the hook attached?" — the INJECT button is gated
// by it (disabled when the game isn't running). PID override is optional
// and persisted in localStorage so it survives a page reload.

import { api } from "./api.js";
import { $ } from "./dom.js";

const POLL_INTERVAL_MS = 3000;
const PID_OVERRIDE_KEY = "tacticus.pidOverride";

let pollTimer = null;
let inflight = false;
let lastSessionId = null;

function setStatus(line) {
    const el = $("admin-status");
    if (el) el.textContent = line;
}

function setBanner(level, message) {
    const banner = $("tacticus-banner");
    const msg = $("tacticus-banner-msg");
    if (!banner || !msg) return;
    banner.classList.remove(
        "tacticus-banner--ok", "tacticus-banner--warn",
        "tacticus-banner--err", "tacticus-banner--unknown",
    );
    banner.classList.add("tacticus-banner--" + level);
    msg.textContent = message;
}

function setInjectButton(enabled, label) {
    const btn = $("admin-inject-btn");
    if (!btn) return;
    btn.disabled = !enabled;
    if (label) btn.textContent = label;
}

async function withButton(btn, label, fn) {
    const original = btn.textContent;
    const wasDisabled = btn.disabled;
    btn.disabled = true;
    btn.textContent = label;
    try { return await fn(); }
    finally {
        btn.disabled = wasDisabled;
        btn.textContent = original;
    }
}

function fmtMs(ms) {
    if (ms < 1000) return Math.round(ms) + "ms";
    return (ms / 1000).toFixed(1) + "s";
}

function describeState(state) {
    const t = state.tacticus ?? {};
    const s = state.session ?? null;

    if (!t.running && !t.launcherOnly) {
        return {
            level: "err",
            message: "Tacticus is not running. Start the game — the banner will go green once the runtime is ready.",
            injectEnabled: false,
            injectLabel: "INJECT HOOKS",
        };
    }
    if (t.launcherOnly) {
        return {
            level: "warn",
            message: "Tacticus launcher is open but the game hasn't started. Click PLAY in the launcher.",
            injectEnabled: false,
            injectLabel: "INJECT HOOKS",
        };
    }
    // Game is running.
    if (!s) {
        return {
            level: "warn",
            message: `Tacticus detected (PID ${t.gamePid}) — no hook attached. Click INJECT to attach.`,
            injectEnabled: true,
            injectLabel: "INJECT HOOKS",
        };
    }
    if (s.status === "running") {
        // The button stays clickable so the user can swap the bundle without
        // losing the session: re-injecting tears down the current script and
        // installs a fresh one (host already prunes runners + state).
        return {
            level: "ok",
            message: `Hook active — session #${s.id} on PID ${s.pid}.`,
            injectEnabled: true,
            injectLabel: "RE-INJECT HOOKS",
        };
    }
    // Session present but not running (stopped/error).
    const reason = s.errorMessage ? `: ${s.errorMessage}` : "";
    return {
        level: "err",
        message: `Session ended${reason}. Tacticus is still running — click INJECT to relaunch.`,
        injectEnabled: true,
        injectLabel: "INJECT HOOKS",
    };
}

async function pollStatus() {
    if (inflight) return;
    inflight = true;
    try {
        const state = await api.adminStatus();
        const view = describeState(state);
        setBanner(view.level, view.message);
        setInjectButton(view.injectEnabled, view.injectLabel);

        // Notify the rest of the app whenever the active session id changes
        // (host restarted + restored a session, or a fresh inject finished).
        // Listeners (runners.js via app.js) can re-subscribe to the WS.
        const sid = state.session?.status === "running"
            ? state.session.id
            : null;
        if (sid !== lastSessionId) {
            const prev = lastSessionId;
            lastSessionId = sid;
            window.dispatchEvent(new CustomEvent("tacticus:session-changed", {
                detail: { sessionId: sid, previousSessionId: prev },
            }));
        }
    } catch (e) {
        setBanner("err", "Host unreachable — is the dev server running?");
        setInjectButton(false, "INJECT HOOKS");
        if (lastSessionId !== null) {
            const prev = lastSessionId;
            lastSessionId = null;
            window.dispatchEvent(new CustomEvent("tacticus:session-changed", {
                detail: { sessionId: null, previousSessionId: prev },
            }));
        }
    } finally {
        inflight = false;
    }
}

function startPolling() {
    stopPolling();
    pollStatus();    // immediate first probe
    pollTimer = setInterval(pollStatus, POLL_INTERVAL_MS);
}

function stopPolling() {
    if (pollTimer) {
        clearInterval(pollTimer);
        pollTimer = null;
    }
}

async function onInject() {
    const btn = $("admin-inject-btn");
    if (!btn || btn.disabled) return;
    const overrideInput = $("admin-pid-input");
    const rawPid = overrideInput?.value?.trim() ?? "";
    const pid = rawPid === "" ? undefined : Number(rawPid);
    if (rawPid !== "" && (!Number.isFinite(pid) || pid <= 0)) {
        setStatus("invalid PID override");
        return;
    }
    const t0 = performance.now();
    try {
        const data = await withButton(btn, "INJECTING…",
            () => api.adminInject(pid));
        const kb = (data.bundleBytes / 1024).toFixed(1);
        setStatus(`injected · session ${data.sessionId} · pid=${data.pid}`
            + ` · ${kb}KB bundle · ${fmtMs(performance.now() - t0)}`);
        // Forced refresh — banner reflects the new session immediately
        // instead of waiting for the next 3s tick.
        pollStatus();
    } catch (e) {
        if (e.candidates && Array.isArray(e.candidates)) {
            const list = e.candidates
                .map((c) => `pid=${c.pid} ${c.path ?? c.name}`)
                .join(" · ");
            setStatus(`multiple game candidates — pick one in PID override: ${list}`);
        } else {
            setStatus("inject failed: " + e.message);
        }
    }
}

function loadPidOverride() {
    try {
        const v = localStorage.getItem(PID_OVERRIDE_KEY);
        if (!v) return;
        const input = $("admin-pid-input");
        if (input) input.value = v;
    } catch { /* localStorage unavailable */ }
}

function savePidOverride(value) {
    try {
        if (value) localStorage.setItem(PID_OVERRIDE_KEY, value);
        else localStorage.removeItem(PID_OVERRIDE_KEY);
    } catch { /* localStorage unavailable */ }
}

export function wireAdmin() {
    const inject = $("admin-inject-btn");
    if (inject) inject.addEventListener("click", onInject);

    const pidInput = $("admin-pid-input");
    if (pidInput) {
        loadPidOverride();
        pidInput.addEventListener("input", () => savePidOverride(pidInput.value.trim()));
    }
    const clearBtn = $("admin-pid-clear");
    if (clearBtn) {
        clearBtn.addEventListener("click", () => {
            if (pidInput) pidInput.value = "";
            savePidOverride("");
        });
    }

    startPolling();
}
