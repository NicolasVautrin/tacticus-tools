// AI-trace single toggle. The agent gates each event emission on
// `traceState.enabled[level]`, defaults are OFF to keep idle runs cheap.
// We treat the three levels (L1/L2/L3) as a single all-or-nothing switch
// from the user's perspective: one click enables/disables all three.
// Status polled every 3s to reflect any out-of-band change.

const POLL_INTERVAL_MS = 3000;

const ctx = {
    on: false,            // true if any level is enabled
    sessionAlive: false,
    timer: null,
    busy: false,
};

async function fetchJson(url, opts = {}) {
    const r = await fetch(url, opts);
    if (!r.ok) {
        const data = await r.json().catch(() => ({}));
        throw new Error(data.error ?? r.statusText);
    }
    return r.json();
}

async function pollStatus() {
    try {
        const data = await fetchJson("/api/ai-trace/status");
        if (data.session === false) {
            ctx.sessionAlive = false;
        } else {
            ctx.sessionAlive = true;
            const en = data.enabled ?? {};
            ctx.on = !!(en.L1 || en.L2 || en.L3);
        }
    } catch {
        ctx.sessionAlive = false;
    }
    render();
}

function render() {
    const btn = document.getElementById("ai-trace-toggle");
    const status = document.getElementById("ai-trace-status");
    if (btn) {
        btn.textContent = ctx.on ? "DISABLE" : "ENABLE";
        btn.disabled = !ctx.sessionAlive || ctx.busy;
        btn.classList.toggle("ai-trace-btn--on", ctx.on);
        btn.title = !ctx.sessionAlive
            ? "no running session"
            : (ctx.on ? "click to stop emitting events"
                      : "click to start emitting events");
    }
    if (status) {
        status.textContent = !ctx.sessionAlive
            ? "— no session"
            : (ctx.on
                ? "active · L1+L2+L3 emitting to JSONL"
                : "off · no events emitted (default)");
    }
}

async function handleToggle() {
    if (ctx.busy || !ctx.sessionAlive) return;
    ctx.busy = true;
    render();
    const target = !ctx.on;
    const url = target ? "/api/ai-trace/enable" : "/api/ai-trace/disable";
    try {
        // Apply to all three levels sequentially. Each call is idempotent;
        // the agent silently no-ops if the requested level is already in
        // the requested state.
        for (const level of ["L1", "L2", "L3"]) {
            await fetchJson(url, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ level }),
            });
        }
        ctx.on = target;
    } catch (e) {
        console.warn("[ai-trace] toggle failed", e);
    } finally {
        ctx.busy = false;
        render();
    }
}

export function initAiTraceToggle() {
    const btn = document.getElementById("ai-trace-toggle");
    if (btn) btn.addEventListener("click", handleToggle);
    pollStatus();
    ctx.timer = setInterval(pollStatus, POLL_INTERVAL_MS);
}
