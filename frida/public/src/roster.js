// Unit roster (left of the three columns? — actually right panel, "ROSTER"
// section). Filters state.configUnits via the text input and renders as a
// grid of draggable portraits.

import { state } from "./state.js";
import { $, status } from "./dom.js";

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
    const items = state.configUnits.filter((u) =>
        u.id.toLowerCase().includes(filter)
        || (u.faction ?? "").toLowerCase().includes(filter));
    for (const u of items) {
        const el = document.createElement("div");
        el.classList.add("unit");
        el.title = u.id
            + (u.faction ? " (" + u.faction + ")" : "")
            + (u.level ? " L" + u.level : "");
        el.draggable = true;
        el.innerHTML = '<img src="/assets/'
            + state.manifest.units[u.portraitKey]
            + '" loading="lazy" draggable="false">';
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
