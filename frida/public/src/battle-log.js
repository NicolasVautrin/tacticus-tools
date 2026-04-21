// Battle event stream — processes incoming StreamEvents to update
// `state.eventUnits` (AddUnit, ChangePosition, RemoveUnit) and appends a
// human-readable log entry to the right panel.

import { state } from "./state.js";
import { $ } from "./dom.js";
import { renderOverlay } from "./board.js";

// StepType enum values (subset we care about). Source: BattleLogicAssembly
// IdunBattle.Streams.StepType enum dump.
const STEP = {
    StartMatch: 1, StartTurn: 2, ChangePosition: 3, UnitDamaged: 4,
    AddUnit: 10, AddMachine: 11, RemoveUnit: 12,
    FinishMatch: 15, Revive: 29, DirectlyKillUnit: 26,
};

const STEP_LABEL = {
    1: "MATCH·START", 2: "TURN·START", 3: "MOVE", 4: "DAMAGE",
    10: "SPAWN", 11: "SPAWN·MACHINE", 12: "REMOVE",
    15: "MATCH·END", 29: "REVIVE", 26: "KILL",
};

function processStreamEvents(runnerId, events, unitVisuals) {
    let changed = false;
    for (const e of events) {
        if (e.kind !== "action") continue;
        const tags = e.tags ? JSON.parse(e.tags) : {};
        if (e.step === STEP.AddUnit || e.step === STEP.AddMachine) {
            const tileId = tags.Unit_Foot_Tile_Id_1;
            const coord = state.tileIdToCoord.get(tileId);
            if (!coord) continue;
            state.eventUnits.set(e.entity, {
                col: coord.col, row: coord.row,
                playerId: tags.Unit_Owner_Id ?? null,
                kind: e.step === STEP.AddMachine ? "machine" : "unit",
                visualId: unitVisuals?.[e.entity] ?? null,
            });
            changed = true;
        } else if (e.step === STEP.ChangePosition) {
            const tileId = tags.Unit_Foot_Tile_Id_1;
            const coord = state.tileIdToCoord.get(tileId);
            const u = state.eventUnits.get(e.entity);
            if (u && coord) { u.col = coord.col; u.row = coord.row; changed = true; }
        } else if (e.step === STEP.RemoveUnit || e.step === STEP.DirectlyKillUnit) {
            if (state.eventUnits.delete(e.entity)) changed = true;
        }
    }
    if (changed) renderOverlay();
}

export function renderBattleEvent(ev) {
    const log = $("battle-log");
    const events = ev.events ?? [];
    processStreamEvents(ev.runnerId, events, ev.unitVisuals);
    if (!log) return;

    const li = document.createElement("li");
    li.className = "log-row";
    const hdr = document.createElement("div");
    hdr.className = "log-row__header";
    hdr.innerHTML =
        '<span class="log-row__tag">r' + ev.runnerId + '</span>'
      + '<span class="log-row__msg">' + ev.msg + '</span>'
      + '<span class="log-row__stats">'
      + events.length + ' evt · ' + state.eventUnits.size + ' on map'
      + '</span>';
    li.appendChild(hdr);

    if (events.length) {
        const sub = document.createElement("ul");
        sub.className = "log-row__events";
        for (const e of events.slice(0, 50)) {
            const sli = document.createElement("li");
            if (e.kind === "action") {
                const label = STEP_LABEL[e.step] || ("step·" + e.step);
                sli.innerHTML =
                    '<span class="event-step">' + label + '</span>'
                  + '<span class="event-ent">#' + e.entity + '</span>';
            } else {
                sli.innerHTML =
                    '<span class="event-group">' + e.group + '</span>'
                  + '<span class="event-ent">#' + e.entity + '</span>'
                  + (e.source
                        ? '<span class="event-src">src:' + e.source + '</span>'
                        : '');
            }
            sub.appendChild(sli);
        }
        li.appendChild(sub);
    }
    log.prepend(li);
}
