// Battle event stream — processes incoming StreamEvents to update
// `state.eventUnits` (AddUnit, ChangePosition, RemoveUnit) and appends a
// human-readable, collapsible log entry to the right panel.
//
// Each entry is a <details>: summary header (always visible) + body with the
// individual steps. Big entries (PlayTurn → 100+ events) auto-fold so the
// panel stays readable; the user can click summary to expand.
//
// Inside the body, events are rendered with:
//   - unit portrait per entity (via state.manifest + state.eventUnits visualId)
//   - full step / group label (BattleLogicAssembly.dll IdunBattle.Streams enums)
//   - ability name chip on group events whose source is a named ability
// Action events that come right after a group event are visually nested
// under it.

import { state } from "./state.js";
import { $ } from "./dom.js";
import { renderOverlay } from "./board.js";
import { onBattleEndedRender } from "./actions.js";
import { configIdToPortrait } from "./images.js";

// IdunBattle.Streams.StepType / GroupType — tables POSITIONNELLES (index = ordinal).
//
// GENEREES depuis `data/symbols/<CURRENT>/frida/enums.tsv`, la table de symboles VERSIONNEE.
// Ne jamais les retoucher a la main : ces enums sont IMPLICITEMENT numerotees, donc le retrait
// d'un membre au milieu decale tout ce qui suit. C'est arrive — la MAJ `rnca9r7q6c` a retire
// `StepType.RestoreArmorInfo` (7), et cette table, restee sur `gqfc5mff6c`, affichait depuis
// le nom du pas PRECEDENT pour tout ordinal >= 7 (`AddMachine` etiquete « AddUnit », etc.).
// La panne est muette : rien n'est vide, tout est decale d'un cran.
//
// Le garde-fou qui compare ces deux tables a `enums.tsv` :
//     python scripts/python/probe_274_step_ordinals_sweep.py
// Il imprime les valeurs attendues, index par index — la correction est un copier-coller.
const STEP_LABEL = [
    "None", "StartMatch", "StartTurn", "ChangePosition", "UnitDamaged", "HealInfo", "RepairInfo",
    "AddPlayer", "AddTile", "AddUnit", "AddMachine", "RemoveUnit", "ChangeStats", "ChangeAbility",
    "FinishMatch", "ReceiveEffect", "LoseEffect", "ActivateEffect", "DeactivateEffect",
    "UpdateEffect", "UpdateEffectTurns", "AttackTile", "UnitDraft", "SpawnPointDraft",
    "ExtraAttackDamage", "DirectlyKillUnit", "LootInfo", "RemoveUnitFromTiles", "Revive", "Info",
    "TerritoryCapture", "TerritoryScoreModifierChange", "AddVictoryPoints", "RemoveVictoryPoints",
    "UpdateAbilityModification", "TransferDamage", "Resurrect", "OverrideMovementTarget",
    "PrepareTurn", "ChangeUnitOwner", "UpdateEffectLevel", "UnitFled", "RotateUnit",
    "AddMachinePlatform", "MachineHit", "RemoveMachine", "SpendAmmo", "ChangePlayerReinforcement",
    "ChangeUnitConfig", "AddScore", "SetTempPlayer", "ResetTempPlayer", "AddReinforcementShield",
    "PickUnit", "ChangeResurrectDraftingPoints", "AddOrUpdateShield", "RemoveShield",
    "RevealFogOfWar", "HideDoorActivationTile", "OpenDoor", "ReaddMachine", "PlayerInitialRarity",
];

const GROUP_LABEL = [
    "None", "AddUnit", "AddMachine", "System_GameSetup", "System_StartMatch",
    "System_ProcessDeaths", "System_ProcessRemovals", "System_UnitDrafting",
    "System_RerollDraftOption", "System_StartTurn", "System_PickUnit", "User_MoveUnit",
    "User_UseAbility", "User_PlaceUnit", "User_RemoveUnit", "User_EndTurn", "User_Surrender",
    "User_CheatAmmo", "Test_AbilityDamage", "Test_DirectDamage", "Test_MachineDamage",
    "Ability_Power", "Effect_Refresh", "User_Effect_Manipulation", "SpawnUnitsOfTurn",
    "SpawnUnitsOfWave", "Damage", "TileDamage", "MachineDamage", "DamageChain", "DarkDragon",
    "Ability_Heal", "Ability_Attack", "Ability_Attack_2", "Ability_Summon", "Ability_Move",
    "Ability_Displace", "Ability_Buff", "Ability_Stance", "Ability_State", "Ability_Other",
    "ResurrectUnit", "Ability_AtomicGroup", "EffectAdditionalHits", "ReviveUnit", "Attack",
    "RarityCapTransform", "StartTurn", "EndTurn", "Ability_CustomGroup",
    "HornOfDespair_LightUnits", "HornOfDespair_DarkUnits", "HornOfDespair_Darkness",
    "SummonIceElemental_Spawn", "AirshipStrike_Attack", "EjectEject", "MechRepair",
    "RocketBarrage", "Zinger", "ZingerAbility", "VolatileRockets", "NormalAttack_AtomicDamage",
    "StormOfFlensingBlades_Attacks", "MortisRound_AttackAndPush", "PrecisionShot_Attack",
    "MultiThreatEliminator_Attack", "ArmoriumCherub_Attack", "FragBomb_Damage",
    "StormOfWrath_Attack", "BringerOfDespair_Attacks", "PsychicMaelstrom_Attack",
    "SpawnTermagants_Spawn", "SupremeCommander_Spawn", "Drachnyen_AtomicGroup",
    "PlagueWind_Attack", "PlagueWind_Attack1", "PlagueWind_Attack2", "PlagueWind_Attack3",
    "FrenziedFiring", "ThunderousAssault_AtomicGroup", "GetEmRuntz_AtomicGroup",
    "IncendiarySheels_AtomicGroup", "TemplarInitiateNormalAttack_AtomicGroup",
    "DrachnyenNormalAttack_AtomicGroup", "BasiliskBarrage", "StranglethornCannon_AtomicGroup",
    "SanctorumMissile_Attack", "ScythingTalons_AtomicGroup", "ProperKilly_Attack1",
    "ProperKilly_Attack2", "EreWeGo_AtomicGroup", "DarkTalon", "MortarionsPlagueWind_Attack",
    "MortarionsPlagueWind_Attack1", "MortarionsPlagueWind_Attack2", "MortarionsPlagueWind_Attack3",
    "AnvilShieldBlock", "Doombolt", "SpiritualLeader_SummonDecoy",
    "SpiritualLeader_SummonNeophyte", "CultDemagogue_SummonDecoy", "CultDemagogue_SummonNeophyte",
    "RevealFogOfWar", "TerritoryCapture",
];

// Step → category. Drives the row's left-border accent + glyph.
const STEP_CATEGORY = (() => {
    const m = {};
    const cats = {
        combat: ["UnitDamaged", "ExtraAttackDamage", "AttackTile", "MachineHit", "TransferDamage", "SpendAmmo"],
        movement: ["ChangePosition", "OverrideMovementTarget", "RotateUnit", "UnitFled"],
        lifecycle: ["AddUnit", "AddMachine", "AddMachinePlatform", "RemoveUnit", "RemoveUnitFromTiles", "RemoveMachine", "ReaddMachine", "DirectlyKillUnit", "Revive", "Resurrect"],
        effect: ["ReceiveEffect", "LoseEffect", "ActivateEffect", "DeactivateEffect", "UpdateEffect", "UpdateEffectTurns", "UpdateEffectLevel", "UpdateAbilityModification", "AddOrUpdateShield", "RemoveShield", "AddReinforcementShield"],
        heal: ["HealInfo", "RepairInfo", "RestoreArmorInfo"],
        stats: ["ChangeStats", "ChangeAbility", "ChangeUnitConfig", "ChangeUnitOwner", "ChangePlayerReinforcement"],
        system: ["StartMatch", "FinishMatch", "StartTurn", "PrepareTurn", "AddPlayer", "AddTile", "Info"],
        score: ["AddScore", "AddVictoryPoints", "RemoveVictoryPoints", "TerritoryCapture", "ChangeResurrectDraftingPoints", "PlayerInitialRarity"],
        draft: ["UnitDraft", "SpawnPointDraft", "PickUnit", "LootInfo"],
        player: ["SetTempPlayer", "ResetTempPlayer"],
        terrain: ["RevealFogOfWar", "HideDoorActivationTile", "OpenDoor"],
    };
    for (const [cat, names] of Object.entries(cats)) {
        for (const n of names) m[n] = cat;
    }
    return m;
})();

// Ordinaux des pas dont le rendu depend : DERIVES de STEP_LABEL, jamais reecrits a la main.
// Ils etaient figes ici en dur, avec les valeurs de `gqfc5mff6c` : depuis `rnca9r7q6c`,
// `AddUnit`/`AddMachine`/`RemoveUnit`/`FinishMatch`/`DirectlyKillUnit` valaient tous un cran de
// trop, donc `processStreamEvents` posait/deplacait/retirait les pions du plateau sur les
// MAUVAIS events. Un nom disparu rend -1 : le test ne matche plus rien (degradation en
// « aucun rendu »), au lieu de matcher un AUTRE pas — et la console le dit.
const STEP = (() => {
    const noms = ["StartMatch", "StartTurn", "ChangePosition", "UnitDamaged", "HealInfo",
                  "AddUnit", "AddMachine", "RemoveUnit", "FinishMatch", "DirectlyKillUnit"];
    const m = {};
    for (const n of noms) {
        const i = STEP_LABEL.indexOf(n);
        if (i < 0) console.error("battle-log: StepType." + n + " absent de STEP_LABEL "
                                 + "— table a regenerer (probe_274_step_ordinals_sweep.py)");
        m[n] = i;
    }
    return m;
})();

const AUTOFOLD_EVENT_COUNT = 15;
const MAX_RENDER_EVENTS = 80;

function stepName(s) {
    return STEP_LABEL[s] ?? ("step·" + s);
}
function groupName(g) {
    return GROUP_LABEL[g] ?? ("group·" + g);
}

function processStreamEvents(runnerId, events, unitVisuals) {
    let changed = false;
    let finished = false;
    let winner = null;
    for (const e of events) {
        if (e.kind !== "action") continue;
        const tags = e.tags ? safeParseTags(e.tags) : {};
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
        } else if (e.step === STEP.FinishMatch) {
            finished = true;
            for (const k of Object.keys(tags)) {
                if (/winner/i.test(k) && typeof tags[k] === "number") {
                    winner = tags[k];
                    break;
                }
            }
        }
    }
    if (changed) renderOverlay();
    if (finished && (!state.battleEnded || state.battleEnded.runnerId !== runnerId)) {
        state.battleEnded = {
            runnerId, winner,
            stageName: "Finished",
            finishedAt: Date.now(),
            source: "stream",
        };
        try { onBattleEndedRender(); } catch { /* */ }
    }
}

function safeParseTags(s) {
    try { return JSON.parse(s); }
    catch { return {}; }
}

/** Resolve an entity → {visualId, playerId} from runtime state. May be null
 * if the entity hasn't been seen via AddUnit yet (system events, players,
 * tiles) or if it died. */
function entityVisual(entityId, unitVisuals) {
    if (unitVisuals && unitVisuals[entityId]) {
        return { visualId: unitVisuals[entityId], playerId: null };
    }
    const u = state.eventUnits.get(entityId);
    if (u) return { visualId: u.visualId, playerId: u.playerId };
    return null;
}

function portraitImg(visualId) {
    if (!visualId || !state.manifest?.units) return null;
    // Direct hit (already a manifest key like "adept_canoness_01")?
    if (state.manifest.units[visualId]) {
        return "/assets/" + state.manifest.units[visualId];
    }
    // Otherwise resolve camelCase VisualId → snake_case assetNaming via the
    // shared helper which also tries `_01` / `_01_premium` suffixes and
    // falls back to a heuristic snake_case conversion.
    const key = configIdToPortrait(visualId);
    if (!key) return null;
    return "/assets/" + state.manifest.units[key];
}

/** Resolve an ability source string (e.g. "Loki_SwoopingHawk", "AetherStride")
 * to its icon URL, or null if no asset matches. The manifest indexes
 * abilities by lowercase key — see scripts/python/build_asset_manifest.py. */
function abilityImg(source) {
    if (!source || !state.manifest?.abilities) return null;
    const path = state.manifest.abilities[source.toLowerCase()];
    if (!path) return null;
    return "/assets/" + path;
}

/** Pick a 1-line summary of the most informative tag for this step. */
function actionTagSummary(stepNum, tags) {
    if (!tags) return "";
    const pick = (...keys) => {
        for (const k of keys) {
            const v = tags[k];
            if (v !== undefined && v !== null && v !== 0) {
                return k + "=" + v;
            }
        }
        return null;
    };
    // On branche sur le NOM du pas, pas sur son ordinal : les `case 13:` / `case 16:` d'avant
    // etaient ceux de `gqfc5mff6c` et designaient, depuis `rnca9r7q6c`, les pas VOISINS.
    switch (stepName(stepNum)) {
        case "UnitDamaged":
        case "ExtraAttackDamage":
        case "TransferDamage":
        case "MachineHit":
            return pick("Hit_Damage", "Hit_DamageHealth", "Hit_DamageArmor",
                        "Damage_Damage", "Damage_OnTile") || "";
        case "HealInfo":
        case "RepairInfo":
        case "RestoreArmorInfo":   // retire par `rnca9r7q6c` — inoffensif, jamais atteint
            return pick("HealInfo_Amount", "HealInfo_Health",
                        "RepairInfo_Amount", "RestoreArmor_Amount") || "";
        case "ChangePosition":
            return pick("Unit_Foot_Tile_Id_1") || "";
        case "ChangeStats":
            // tags often contain UnitStats_RemainingHealth / Armor / etc.
            // pick first non-zero stat key for a hint
            for (const k of Object.keys(tags)) {
                if (k.startsWith("UnitStats_") && tags[k] !== 0) {
                    return k.slice("UnitStats_".length) + "=" + tags[k];
                }
            }
            return "";
        case "ReceiveEffect":
        case "LoseEffect":
        case "ActivateEffect":
        case "DeactivateEffect":
        case "UpdateEffect":
        case "UpdateEffectTurns":
        case "UpdateEffectLevel":
            return pick("Effect_Id", "Effect_Level", "Effect_Turns", "Effect_Stacks") || "";
        case "DirectlyKillUnit":
        case "RemoveUnit":
            return pick("Unit_Owner_Id") || "";
        default:
            return "";
    }
}

export function renderBattleEvent(ev) {
    const log = $("battle-log");
    const events = ev.events ?? [];
    processStreamEvents(ev.runnerId, events, ev.unitVisuals);
    if (!log) return;

    const li = document.createElement("li");
    li.className = "log-row";
    const details = document.createElement("details");
    details.className = "log-row__fold";
    details.open = events.length < AUTOFOLD_EVENT_COUNT;

    const summary = document.createElement("summary");
    summary.className = "log-row__header";
    summary.innerHTML =
        '<span class="log-row__caret" aria-hidden="true">▸</span>'
      + '<span class="log-row__tag">r' + ev.runnerId + '</span>'
      + '<span class="log-row__msg">' + escapeHtml(ev.msg ?? "") + '</span>'
      + '<span class="log-row__stats">'
      + events.length + ' evt · ' + state.eventUnits.size + ' on map'
      + '</span>';
    details.appendChild(summary);

    if (events.length) {
        details.appendChild(buildEventsList(events, ev.unitVisuals));
    }
    li.appendChild(details);
    log.prepend(li);
}

/** Render the event list with single-level group nesting:
 *   [group A header]
 *     ├ action 1
 *     ├ action 2
 *   [group B header]
 *     ├ action 3
 * Group/action ordering preserved as emitted by StreamDispatcher. */
function buildEventsList(events, unitVisuals) {
    const ul = document.createElement("ul");
    ul.className = "log-row__events";

    const visible = events.slice(0, MAX_RENDER_EVENTS);
    let currentGroupSubList = null;
    let rendered = 0;

    for (const e of visible) {
        const li = document.createElement("li");
        if (e.kind === "group") {
            li.className = "evt evt--group";
            li.appendChild(renderGroupRow(e, unitVisuals));
            ul.appendChild(li);
            // Subsequent actions go into a nested ul under this group.
            currentGroupSubList = document.createElement("ul");
            currentGroupSubList.className = "evt-subgroup";
            ul.appendChild(currentGroupSubList);
        } else {
            li.className = "evt evt--action";
            const cat = STEP_CATEGORY[stepName(e.step)] ?? "other";
            li.classList.add("evt--" + cat);
            li.appendChild(renderActionRow(e, unitVisuals));
            (currentGroupSubList ?? ul).appendChild(li);
        }
        rendered++;
    }

    if (events.length > rendered) {
        const more = document.createElement("li");
        more.className = "log-row__more";
        more.textContent = "… +" + (events.length - rendered) + " more events";
        ul.appendChild(more);
    }
    return ul;
}

function renderGroupRow(e, unitVisuals) {
    const wrap = document.createElement("div");
    wrap.className = "evt-row evt-row--group";
    wrap.dataset.entity = String(e.entity);    // exposed via title for debug

    // Caster portrait (the entity that triggered the group)
    const portrait = renderEntityPortrait(e.entity, unitVisuals);
    if (portrait) wrap.appendChild(portrait);

    const label = document.createElement("span");
    label.className = "evt-step";
    label.textContent = groupName(e.group);
    wrap.appendChild(label);

    if (e.source) {
        const src = document.createElement("span");
        src.className = "evt-src";
        src.title = "#" + e.entity + " · " + e.source;
        const iconUrl = abilityImg(e.source);
        if (iconUrl) {
            src.innerHTML =
                '<img class="evt-src__icon" src="' + iconUrl
              + '" alt="" loading="lazy">'
              + '<span class="evt-src__name">' + escapeHtml(e.source) + '</span>';
        } else {
            // Generic glyph for sources without an asset
            // (e.g. unit "<Name>_NormalAttack" — basic attacks have no icon).
            src.innerHTML =
                '<span class="evt-src__glyph" aria-hidden="true">⚡</span>'
              + '<span class="evt-src__name">' + escapeHtml(e.source) + '</span>';
        }
        wrap.appendChild(src);
    }
    return wrap;
}

function renderActionRow(e, unitVisuals) {
    const wrap = document.createElement("div");
    wrap.className = "evt-row evt-row--action";
    wrap.dataset.entity = String(e.entity);    // exposed via title for debug

    const portrait = renderEntityPortrait(e.entity, unitVisuals);
    if (portrait) wrap.appendChild(portrait);

    const label = document.createElement("span");
    label.className = "evt-step";
    label.textContent = stepName(e.step);
    wrap.appendChild(label);

    const tags = e.tags ? safeParseTags(e.tags) : null;
    const summary = actionTagSummary(e.step, tags);
    if (summary) {
        const tag = document.createElement("span");
        tag.className = "evt-tag";
        tag.textContent = summary;
        if (tags) tag.title = "#" + e.entity + " · " + compactTagsForHover(tags);
        wrap.appendChild(tag);
    } else {
        // No specialised summary — surface the entity index + tags via row hover.
        const tagsLabel = (tags && Object.keys(tags).length > 0)
            ? compactTagsForHover(tags) : "";
        wrap.title = "#" + e.entity + (tagsLabel ? " · " + tagsLabel : "");
    }
    return wrap;
}

function renderEntityPortrait(entityId, unitVisuals) {
    const v = entityVisual(entityId, unitVisuals);
    const url = v ? portraitImg(v.visualId) : null;
    if (url) {
        const img = document.createElement("img");
        img.className = "evt-portrait";
        img.alt = v.visualId ?? "";
        img.title = v.visualId ?? "";
        img.src = url;
        if (v.playerId !== null && v.playerId !== undefined) {
            img.dataset.player = String(v.playerId);
        }
        return img;
    }
    // Fallback when we don't have a visual yet (system events, abstract
    // entities, players/tiles). A muted dot keeps the column aligned.
    const dot = document.createElement("span");
    dot.className = "evt-portrait evt-portrait--placeholder";
    return dot;
}

function compactTagsForHover(tags) {
    return Object.entries(tags)
        .filter(([, v]) => v !== 0 && v !== null && v !== undefined)
        .map(([k, v]) => k + "=" + v)
        .join(" · ");
}

function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, (ch) => ({
        "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
    }[ch]));
}
