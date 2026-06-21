// Host-side RPC concurrency gate + capacity telemetry, per Frida session.
//
// EVERY host→agent rpcCall passes through a per-session gate. The host is the
// ONLY place that can SEE how the single-threaded Frida pump copes with N
// concurrent callers (sub-agents), and optionally CAP that concurrency.
//
// Default cap = Infinity → pure PASS-THROUGH: behaviour is unchanged, it just
// MEASURES. Set a finite cap to throttle: extra callers wait FIFO for a slot;
// the RPC timeout clock starts only at DISPATCH (slot acquired), never while
// queued — so a queued caller can't time out merely waiting for a slot.
//
// TIMEOUT SCALING: per-call timeout = base × concurrencyFactor, where
//   factor = max(timeoutScale, inFlight + waiting).
// `timeoutScale` is a FLOOR set by the ORCHESTRATOR — only Claude knows how
// many agents it will run, hence the reasonable timeout level (set it via
// POST /api/rpc-queue before launching a batch). `inFlight + waiting` is the
// LIVE queue size, a dynamic component on top. Generous-by-design: a false
// timeout on a MUTATING RPC = zombie mutation/corruption, so we err long.
//
// Reading the gauges ("does Frida breathe?") — cf. docs/rl/design.md:
//   - avgInFlight  : TIME-WEIGHTED concurrency over the window. Near N (≈ agent
//                    count) AND persistent ⇒ Frida saturated, agents stuck
//                    waiting on it instead of reasoning → the parallel-overlap
//                    benefit is gone. Much < N ⇒ Frida mostly idle, headroom.
//   - busyFraction : fraction of wall-time with inFlight≥1. → 1 ⇒ "ça respire pas".
//   - avgRpcMs     : mean dispatch→reply latency. Flat as N grows ⇒ headroom;
//                    climbing ~linearly with N ⇒ serial-queue saturation.
//   - maxInFlight  : a PEAK only (all N coincided once) — NOT saturation by
//                    itself; trust avgInFlight / busyFraction.

export interface RpcGateStats {
    cap: number;            // -1 = uncapped (Infinity isn't JSON-representable)
    timeoutScale: number;   // floor factor set for planned parallelism
    timeoutFactor: number;  // applied = max(timeoutScale, inFlight+waiting)
    inFlight: number;
    waiting: number;
    maxInFlight: number;
    maxWaiting: number;
    avgInFlight: number;    // time-weighted occupancy over the window
    busyFraction: number;   // fraction of window with inFlight≥1
    avgRpcMs: number;       // mean dispatch→settle latency
    maxRpcMs: number;
    avgQueuedMs: number;    // mean wait-for-slot (0 unless capped)
    totalDispatched: number;
    totalTimeouts: number;
    windowMs: number;
}

interface RpcGate {
    cap: number;
    timeoutScale: number;
    inFlight: number;
    waiting: Array<() => void>;
    maxInFlight: number;
    maxWaiting: number;
    // time-weighted occupancy
    since: number;
    lastChangeAt: number;
    inFlightIntegral: number;   // Σ inFlight·dt
    busyMs: number;             // Σ dt where inFlight≥1
    // latency
    rttSum: number; rttCount: number; maxRttMs: number;
    queuedSum: number; queuedCount: number;
    totalDispatched: number;
    totalTimeouts: number;
}

const gates = new Map<number, RpcGate>();
let defaultCap = Infinity;
let defaultTimeoutScale = 1;

function gateFor(id: number): RpcGate {
    let g = gates.get(id);
    if (!g) {
        const t = Date.now();
        g = {
            cap: defaultCap, timeoutScale: defaultTimeoutScale,
            inFlight: 0, waiting: [],
            maxInFlight: 0, maxWaiting: 0,
            since: t, lastChangeAt: t, inFlightIntegral: 0, busyMs: 0,
            rttSum: 0, rttCount: 0, maxRttMs: 0,
            queuedSum: 0, queuedCount: 0,
            totalDispatched: 0, totalTimeouts: 0,
        };
        gates.set(id, g);
    }
    return g;
}

/** Accrue time-weighted occupancy up to now. Call BEFORE every inFlight CHANGE
 *  (and in getStats). Idempotent: a second immediate call accrues ~0. */
function accrue(g: RpcGate): void {
    const t = Date.now();
    const dt = t - g.lastChangeAt;
    if (dt > 0) {
        g.inFlightIntegral += g.inFlight * dt;
        if (g.inFlight > 0) g.busyMs += dt;
        g.lastChangeAt = t;
    }
}

/** Acquire a dispatch slot. Resolves immediately if under cap, else waits FIFO.
 *  Caller MUST releaseSlot() in finally. Resolves with ms spent waiting. */
export function acquireSlot(id: number): Promise<number> {
    const g = gateFor(id);
    if (g.inFlight < g.cap) {
        accrue(g);
        g.inFlight++;
        if (g.inFlight > g.maxInFlight) g.maxInFlight = g.inFlight;
        return Promise.resolve(0);
    }
    const t0 = Date.now();
    return new Promise<number>((resolve) => {
        g.waiting.push(() => resolve(Date.now() - t0));
        if (g.waiting.length > g.maxWaiting) g.maxWaiting = g.waiting.length;
    });
}

/** Release a slot: hand it to the next FIFO waiter if any (inFlight unchanged —
 *  one leaves, one enters), else decrement. */
export function releaseSlot(id: number): void {
    const g = gates.get(id);
    if (!g) return;
    const next = g.waiting.shift();
    if (next) {
        next();   // slot handed over → inFlight unchanged → no accrue needed
    } else {
        accrue(g);
        g.inFlight = Math.max(0, g.inFlight - 1);
    }
}

export function noteDispatch(id: number, queuedMs: number): void {
    const g = gateFor(id);
    g.totalDispatched++;
    g.queuedSum += queuedMs; g.queuedCount++;
}

export function noteSettle(id: number, rttMs: number, timedOut: boolean): void {
    const g = gates.get(id);
    if (!g) return;
    g.rttSum += rttMs; g.rttCount++;
    if (rttMs > g.maxRttMs) g.maxRttMs = rttMs;
    if (timedOut) g.totalTimeouts++;
}

/** Timeout-scaling factor: effective timeout = base × factor. Combines (1) a
 *  FLOOR set by the orchestrator for its planned parallelism (timeoutScale —
 *  only Claude knows how many agents it will run) and (2) the LIVE queue size
 *  (inFlight + waiting). max() ⇒ at least my plan, more if the real backlog is
 *  deeper. The single Frida pump runs RPCs one at a time, so latency ∝ this. */
export function concurrencyFactor(id: number): number {
    const g = gates.get(id);
    if (!g) return Math.max(1, defaultTimeoutScale);
    return Math.max(1, g.timeoutScale, g.inFlight + g.waiting.length);
}

/** Set the concurrency cap. cap ≤ 0 / non-finite ⇒ uncapped (Infinity).
 *  id omitted ⇒ set the default + apply to all existing gates. */
export function setCap(cap: number, id?: number): void {
    const c = (!Number.isFinite(cap) || cap <= 0) ? Infinity : Math.floor(cap);
    if (id === undefined) {
        defaultCap = c;
        for (const g of gates.values()) g.cap = c;
    } else {
        gateFor(id).cap = c;
    }
}

/** Set the timeout FLOOR factor (≈ planned parallel-agent count). Effective
 *  per-call timeout = base × max(timeoutScale, inFlight+waiting). < 1 ⇒ 1.
 *  id omitted ⇒ set the default + apply to all existing gates. The orchestrator
 *  POSTs this before launching a batch of N agents (timeoutScale = N). */
export function setTimeoutScale(scale: number, id?: number): void {
    const s = (!Number.isFinite(scale) || scale < 1) ? 1 : Math.floor(scale);
    if (id === undefined) {
        defaultTimeoutScale = s;
        for (const g of gates.values()) g.timeoutScale = s;
    } else {
        gateFor(id).timeoutScale = s;
    }
}

export function resetStats(id?: number): void {
    const t = Date.now();
    const reset = (g: RpcGate): void => {
        g.maxInFlight = g.inFlight; g.maxWaiting = g.waiting.length;
        g.since = t; g.lastChangeAt = t; g.inFlightIntegral = 0; g.busyMs = 0;
        g.rttSum = 0; g.rttCount = 0; g.maxRttMs = 0;
        g.queuedSum = 0; g.queuedCount = 0;
        g.totalDispatched = 0; g.totalTimeouts = 0;
    };
    if (id === undefined) gates.forEach(reset);
    else { const g = gates.get(id); if (g) reset(g); }
}

export function getStats(id: number): RpcGateStats {
    const g = gateFor(id);
    accrue(g);
    const windowMs = Math.max(1, Date.now() - g.since);
    return {
        cap: Number.isFinite(g.cap) ? g.cap : -1,
        timeoutScale: g.timeoutScale,
        timeoutFactor: Math.max(1, g.timeoutScale, g.inFlight + g.waiting.length),
        inFlight: g.inFlight, waiting: g.waiting.length,
        maxInFlight: g.maxInFlight, maxWaiting: g.maxWaiting,
        avgInFlight: +(g.inFlightIntegral / windowMs).toFixed(3),
        busyFraction: +(g.busyMs / windowMs).toFixed(3),
        avgRpcMs: g.rttCount ? Math.round(g.rttSum / g.rttCount) : 0,
        maxRpcMs: g.maxRttMs,
        avgQueuedMs: g.queuedCount ? Math.round(g.queuedSum / g.queuedCount) : 0,
        totalDispatched: g.totalDispatched, totalTimeouts: g.totalTimeouts,
        windowMs,
    };
}

export function listGateStats(): {
    defaultCap: number; defaultTimeoutScale: number;
    sessions: Record<number, RpcGateStats>;
} {
    const sessions: Record<number, RpcGateStats> = {};
    for (const id of gates.keys()) sessions[id] = getStats(id);
    return {
        defaultCap: Number.isFinite(defaultCap) ? defaultCap : -1,
        defaultTimeoutScale, sessions,
    };
}
