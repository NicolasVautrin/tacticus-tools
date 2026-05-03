// Diagnostic logger — `send({t:"diag", msg})` instead of `console.log`.
//
// Frida's `console.log` from the agent goes to the host process's stdout,
// which is fine for interactive `npm run dev` but can't be tail'd from
// outside (no file handle, lost when the parent terminal detaches).
// `send()` flows through the script.message channel → onMessage in
// host/sessions.ts → appended to logs/run-<sid>_<ts>_<target>.jsonl, where
// it can be inspected after the fact.
//
// Use in place of `console.log(...)` everywhere in hooks/.

export function log(...args: unknown[]): void {
    try {
        const msg = args.map((a) => {
            if (typeof a === "string") return a;
            if (a === null || a === undefined) return String(a);
            try { return String(a); }
            catch { return "<unprintable>"; }
        }).join(" ");
        send({ t: "diag", msg });
    } catch { /* best effort — never break a hook because logging failed */ }
}

// Per-hook trace: emit a sequence number + hook name on each callback entry.
// The session log captures every emit on disk (logs/run-...jsonl) — after a
// crash, the last `traceEnter` call points at the culprit hook.
//
// Heavy by design — this is a diagnostic mode. Hot hooks like main-pump and
// menu-pump are throttled (every 60th call by default) to avoid drowning the
// log in identical entries while still giving us periodic liveness markers.

let _traceCounter = 0;
const _traceEvery: Record<string, number> = {};

export function traceEnter(name: string, every: number = 1): void {
    if (every > 1) {
        const c = (_traceEvery[name] ?? 0) + 1;
        _traceEvery[name] = c;
        if (c % every !== 1) return;
    }
    try {
        _traceCounter++;
        send({ t: "trace", n: _traceCounter, name });
    } catch { /* */ }
}
