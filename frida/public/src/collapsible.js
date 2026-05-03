// Collapsible <section.panel-block> support: click on the header toggles
// visibility of the body. State persists per-panel in localStorage so the
// user's layout survives reloads.
//
// Identity for each panel:
//   - section[id] if present, else slug derived from h2 text content.
// Action buttons inside the header (e.g. refresh ↻) stop propagation so
// they don't trigger a collapse when clicked.

const STORAGE_PREFIX = "panel-collapsed:";

function panelKey(section) {
    if (section.id) return section.id;
    const h2 = section.querySelector(".panel-block__head h2");
    if (!h2) return null;
    return h2.textContent.trim().toLowerCase()
        .replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "");
}

function applyState(section, collapsed) {
    section.classList.toggle("panel-block--collapsed", !!collapsed);
}

function readState(key) {
    try {
        return localStorage.getItem(STORAGE_PREFIX + key) === "1";
    } catch { return false; }
}

function writeState(key, collapsed) {
    try {
        if (collapsed) localStorage.setItem(STORAGE_PREFIX + key, "1");
        else localStorage.removeItem(STORAGE_PREFIX + key);
    } catch { /* private mode */ }
}

export function initCollapsiblePanels(root = document) {
    const sections = root.querySelectorAll(".panel-block");
    sections.forEach((section) => {
        const key = panelKey(section);
        if (!key) return;

        // Restore persisted state on init.
        applyState(section, readState(key));

        const head = section.querySelector(".panel-block__head");
        if (!head) return;

        // Don't add a second listener if init runs twice (e.g. dynamic
        // panel re-render).
        if (head.dataset.collapsibleBound === "1") return;
        head.dataset.collapsibleBound = "1";

        head.addEventListener("click", (e) => {
            // Buttons inside the head must not collapse the panel.
            const target = e.target;
            if (target instanceof Element
                && target.closest("button, a, input, select, textarea")) {
                return;
            }
            const collapsed = !section.classList.contains("panel-block--collapsed");
            applyState(section, collapsed);
            writeState(key, collapsed);
        });
    });
}
