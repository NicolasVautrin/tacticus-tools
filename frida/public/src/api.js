// HTTP API wrappers. All endpoints served by the Frida host at :8765.
// Keep fetches here so error handling stays centralized and no fetch URL
// leaks into business logic.

export const api = {
    async manifest() {
        const r = await fetch("/assets/manifest.json");
        return r.json();
    },

    async assetMap() {
        const r = await fetch("/assets/unit-asset-map.json");
        if (!r.ok) return null;
        return r.json();
    },

    async configs() {
        const r = await fetch("/api/configs");
        return r.json();
    },

    async config(id) {
        const r = await fetch("/api/configs/" + encodeURIComponent(id));
        return r.json();
    },

    async runners() {
        const r = await fetch("/api/runners");
        return r.json();
    },

    async syncRunners() {
        const r = await fetch("/api/runners/sync", { method: "POST" });
        if (!r.ok) throw new Error(await r.text());
        return r.json();
    },

    async deleteRunner(runnerId) {
        const r = await fetch("/api/runners/" + runnerId, { method: "DELETE" });
        if (!r.ok) throw new Error(await r.text());
        return r;
    },

    async latestState(runnerId) {
        const r = await fetch("/api/runners/" + runnerId + "/latest-state");
        if (!r.ok) return null;
        return r.json();
    },

    async sessions() {
        const r = await fetch("/api/sessions");
        return r.json();
    },

    async launch(configId, placements) {
        const r = await fetch("/api/launch", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ configId, placements }),
        });
        const data = await r.json();
        if (!r.ok) throw new Error(data.error ?? r.statusText);
        return data;
    },

    // Generic Frida RPC forwarder. sessionId is the host's run_session_id,
    // not the runnerId — the host routes via /api/scripts/:id/rpc.
    async rpc(sessionId, method, args = [], timeoutMs = 30000) {
        const r = await fetch("/api/scripts/" + sessionId + "/rpc", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ method, args, timeout: timeoutMs }),
        });
        const data = await r.json();
        if (!r.ok) throw new Error(data.error ?? r.statusText);
        return data.result;
    },
};
