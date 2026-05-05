// Unit roster panel — filters the captured config's deployable unit pool
// against (a) the search input, (b) the campaign's allowedFactions, and
// renders a draggable portrait grid. requiredUnits get a "mandatory"
// badge so the user knows which heroes must be in the deployment.

import { state } from "./state.js";
import { $, status } from "./dom.js";
import { rankImageUrl } from "./images.js";

export function renderUnitRoster() {
    const filterEl = $("unit-filter");
    const filter = (filterEl ? filterEl.value : "").toLowerCase();
    const div = $("unit-list");
    if (!div) return;
    div.innerHTML = "";
    if (!state.configUnits.length) {
        div.innerHTML =
            '<div class="roster__empty">'
          + '<span class="roster__empty-bar"></span>'
          + 'select a config to see its unit pool'
          + '</div>';
        return;
    }

    const allowed = state.constraints?.allowedFactions ?? [];
    const allowedSet = allowed.length ? new Set(allowed) : null;
    const required = new Set(state.constraints?.requiredUnits ?? []);

    const items = state.configUnits.filter((u) => {
        if (allowedSet && !allowedSet.has(u.faction)) return false;
        if (!filter) return true;
        return u.id.toLowerCase().includes(filter)
            || (u.faction ?? "").toLowerCase().includes(filter);
    });

    if (allowedSet) {
        const head = document.createElement("div");
        head.className = "roster__constraints";
        head.textContent = "allowed: " + allowed.join(" · ");
        div.appendChild(head);
    }

    for (const u of items) {
        const isRequired = required.has(u.id);
        const el = document.createElement("div");
        el.classList.add("unit");
        if (isRequired) el.classList.add("unit--mandatory");
        el.title = u.id
            + (u.faction ? " (" + u.faction + ")" : "")
            + (u.level ? " L" + u.level : "")
            + (isRequired ? " — MANDATORY" : "");
        el.draggable = true;
        const rankUrl = rankImageUrl(u.rank);
        el.innerHTML = '<img src="/assets/'
            + state.manifest.units[u.portraitKey]
            + '" loading="lazy" draggable="false">'
            + (rankUrl
                ? '<img class="unit__rank" src="' + rankUrl
                  + '" loading="lazy" draggable="false">'
                : "")
            + (isRequired ? '<span class="unit__badge">!</span>' : "");
        el.addEventListener("dragstart", (ev) => {
            ev.dataTransfer.setData("text/plain", JSON.stringify({
                kind: "deploy", unitId: u.id,
            }));
            ev.dataTransfer.effectAllowed = "copy";
            status("dragging " + u.id + " — drop on a spawn tile");
        });
        div.appendChild(el);
    }
}
