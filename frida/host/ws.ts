// WebSocket streaming for Frida session messages.
// Ring buffer per session for reconnection support via ?last_event_id=N

import { WebSocketServer, WebSocket } from "ws";
import type { Server } from "http";

const RING_SIZE = 10_000;

interface RingBuffer {
    events: unknown[];
    nextId: number;
}

const rings = new Map<number, RingBuffer>();
const subscribers = new Map<number, Set<WebSocket>>();

function getRing(sessionId: number): RingBuffer {
    let ring = rings.get(sessionId);
    if (!ring) {
        ring = { events: [], nextId: 0 };
        rings.set(sessionId, ring);
    }
    return ring;
}

/** Publish an event to all WS subscribers + ring buffer. */
export function publish(sessionId: number, envelope: unknown): void {
    const ring = getRing(sessionId);
    const event = { id: ring.nextId++, ...(envelope as object) };
    ring.events.push(event);
    if (ring.events.length > RING_SIZE) ring.events.shift();

    const subs = subscribers.get(sessionId);
    if (subs) {
        const json = JSON.stringify(event);
        for (const ws of subs) {
            if (ws.readyState === WebSocket.OPEN) ws.send(json);
        }
    }
}

export function cleanupSession(sessionId: number): void {
    rings.delete(sessionId);
    subscribers.delete(sessionId);
}

export function attachWss(server: Server): void {
    const wss = new WebSocketServer({ server });

    wss.on("connection", (ws, req) => {
        const url = new URL(req.url ?? "", `http://${req.headers.host}`);
        const match = url.pathname.match(/^\/ws\/run\/(\d+)$/);
        if (!match) {
            ws.close(4000, "Invalid path — use /ws/run/:id");
            return;
        }
        const sessionId = parseInt(match[1], 10);
        const lastEventId = parseInt(url.searchParams.get("last_event_id") ?? "-1", 10);

        if (!subscribers.has(sessionId)) subscribers.set(sessionId, new Set());
        subscribers.get(sessionId)!.add(ws);

        // Replay missed events since last_event_id
        const ring = getRing(sessionId);
        for (const event of ring.events) {
            if ((event as { id: number }).id > lastEventId) {
                ws.send(JSON.stringify(event));
            }
        }

        ws.on("close", () => {
            subscribers.get(sessionId)?.delete(ws);
        });
    });
}
