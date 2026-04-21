// Routing layer for Frida `send()` messages.
//
// Every hook-emitted `send({t:"...", ...})` flows through sessions.ts.onMessage,
// which asks this router to dispatch on the `t` discriminator. Handlers can:
//   - perform side effects (persist to disk, update state)
//   - rewrite `ctx.envelope.payload` before broadcast/log (typically to redact
//     heavy fields the browser will fetch on demand)
//
// If no handler matches, the envelope is broadcast + logged untouched.
// Handlers register at boot via `registerHandler(t, handler)`.

export interface RouteContext {
    sessionId: number;
    /** The raw inner payload (after unwrapping frida.SendMessage). */
    payload: Record<string, unknown>;
    /** The envelope that will be broadcast + logged. Handlers may mutate `.payload`. */
    envelope: Record<string, unknown>;
}

export type MessageHandler = (ctx: RouteContext) => void;

const handlers = new Map<string, MessageHandler>();

export function registerHandler(t: string, handler: MessageHandler): void {
    if (handlers.has(t)) {
        console.log(`[router-messages] overriding handler for t="${t}"`);
    }
    handlers.set(t, handler);
}

/** Return true if a handler ran. Always safe to call — no-op if `t` unknown. */
export function routeMessage(ctx: RouteContext): boolean {
    const t = ctx.payload.t;
    if (typeof t !== "string") return false;
    const h = handlers.get(t);
    if (!h) return false;
    try {
        h(ctx);
    } catch (e) {
        console.log(`[router-messages] handler for t="${t}" threw: ${(e as Error).message}`);
    }
    return true;
}