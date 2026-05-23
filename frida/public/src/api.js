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

    async deleteConfig(id) {
        const r = await fetch("/api/configs/" + encodeURIComponent(id),
            { method: "DELETE" });
        if (!r.ok) {
            const data = await r.json().catch(() => ({}));
            throw new Error(data.error ?? r.statusText);
        }
        return r.json();
    },

    /** Set/update the user-facing description on a saved capture. */
    async updateConfigDescription(id, description) {
        const r = await fetch("/api/configs/" + encodeURIComponent(id), {
            method: "PATCH",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ description }),
        });
        if (!r.ok) {
            const data = await r.json().catch(() => ({}));
            throw new Error(data.error ?? r.statusText);
        }
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

    /** Build a transient PREVIEW runner (NOT a build, NOT in runners panel)
     * from a saved bundle. Used to render the saved matchstate on the
     * central board for inspection. Returns { ok, stage, matchState }. */
    async simPreviewBuild(configId) {
        const r = await fetch("/api/sim/preview-build", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ configId }),
        });
        const data = await r.json();
        if (!r.ok) throw new Error(data.error ?? r.statusText);
        return data;
    },

    /** Re-project the current preview matchstate. */
    async simGetPreviewState() {
        const r = await fetch("/api/sim/preview-state");
        const data = await r.json();
        if (!r.ok) throw new Error(data.error ?? r.statusText);
        return data;
    },

    /** Drop the preview slot. */
    async simDisposePreview() {
        const r = await fetch("/api/sim/preview-dispose", { method: "POST" });
        const data = await r.json();
        if (!r.ok) throw new Error(data.error ?? r.statusText);
        return data;
    },

    /** LOAD a saved bundle into a fresh BUILD runner. Disposes any prior
     * build + preview. The new BUILD shows up in the runners panel. */
    async simLoadFromSaved(configId) {
        const r = await fetch("/api/sim/load-from-saved", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ configId }),
        });
        const data = await r.json();
        if (!r.ok) throw new Error(data.error ?? r.statusText);
        return data;
    },

    async sessions() {
        const r = await fetch("/api/sessions");
        return r.json();
    },

    async launch(configId, placements, opts = {}) {
        const body = { configId, placements };
        if (opts.inlineConfig) body.inlineConfig = opts.inlineConfig;
        if (opts.inlineMeta) body.inlineMeta = opts.inlineMeta;
        const r = await fetch("/api/launch", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(body),
        });
        const data = await r.json();
        if (!r.ok) throw new Error(data.error ?? r.statusText);
        return data;
    },

    async adminStatus() {
        const r = await fetch("/api/admin/status");
        const data = await r.json();
        if (!r.ok) throw new Error(data.error ?? r.statusText);
        return data;
    },

    async adminCandidates() {
        const r = await fetch("/api/admin/candidates");
        const data = await r.json();
        if (!r.ok) throw new Error(data.error ?? r.statusText);
        return data;
    },

    async adminInject(pid) {
        const body = (pid !== undefined && pid !== null && pid !== "") ? { pid: Number(pid) } : {};
        const r = await fetch("/api/admin/inject", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(body),
        });
        const data = await r.json();
        if (!r.ok) {
            const err = new Error(data.error ?? r.statusText);
            if (data.candidates) err.candidates = data.candidates;
            err.status = r.status;
            throw err;
        }
        return data;
    },

    // Campaign builder API — Phase 1.
    campaigns: {
        async builderStatus() {
            const r = await fetch("/api/campaigns/builder-status");
            const data = await r.json();
            if (!r.ok) throw new Error(data.error ?? r.statusText);
            return data;
        },
        async refreshCatalog() {
            const r = await fetch("/api/campaigns/catalog/refresh", { method: "POST" });
            const data = await r.json();
            if (!r.ok) throw new Error(data.error ?? r.statusText);
            return data;
        },
        // Fetch the cached catalog file directly. `version` comes from
        // /api/admin/status and is the current Tacticus build slug.
        async fetchCatalog(version) {
            const r = await fetch("/meta/" + encodeURIComponent(version)
                                  + "/campaign-catalog.json");
            if (!r.ok) return null;
            return r.json();
        },
        async build(campaignType, campaignId, locationIndex) {
            const r = await fetch("/api/campaigns/build", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ campaignType, campaignId, locationIndex }),
            });
            const data = await r.json();
            if (!r.ok) throw new Error(data.error ?? r.statusText);
            return data;
        },
    },

    // MachinesOfWar event builder API. Mirrors the campaign API shape.
    mow: {
        async builderStatus() {
            const r = await fetch("/api/mow/builder-status");
            const data = await r.json();
            if (!r.ok) throw new Error(data.error ?? r.statusText);
            return data;
        },
        async refreshCatalog() {
            const r = await fetch("/api/mow/catalog/refresh", { method: "POST" });
            const data = await r.json();
            if (!r.ok) throw new Error(data.error ?? r.statusText);
            return data;
        },
        async fetchCatalog(version) {
            const r = await fetch("/meta/" + encodeURIComponent(version)
                                  + "/mow-catalog.json");
            if (!r.ok) return null;
            return r.json();
        },
        async build(tier, battle) {
            const r = await fetch("/api/mow/build", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ tier, battle }),
            });
            const data = await r.json();
            if (!r.ok) throw new Error(data.error ?? r.statusText);
            return data;
        },
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
