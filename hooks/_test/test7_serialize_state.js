// Test: serialize MatchState entities via IdunRunner.Apply
// Compose: _utils/il2cpp-helpers.js + _utils/il2cpp-serializer.js + this file

// --- Resolve offsets ---
var runnerClass = findClass("BattleLogicAssembly.dll", "IdunBattle.Runner", "IdunRunner");
var runnerStateOff = runnerClass ? getFieldOffset(runnerClass, "_state") : -1;

var matchStateClass = findClass("BattleLogicAssembly.dll", "IdunBattle.Core", "MatchState");
var msEntitiesOff = matchStateClass ? getFieldOffset(matchStateClass, "_entities") : -1;

send({t: "offsets", runner_state: runnerStateOff, ms_entities: msEntitiesOff});

// --- Read List<T> as pointers ---
function readListPtrs(listPtr) {
    if (listPtr.isNull()) return [];
    var items = listPtr.add(0x10).readPointer();
    var size = listPtr.add(0x18).readS32();
    if (items.isNull() || size <= 0 || size > 5000) return [];
    var result = [];
    for (var i = 0; i < size; i++) {
        result.push(items.add(0x20 + i * Process.pointerSize).readPointer());
    }
    return result;
}

// --- Unit name registry ---
var unitNames = {};
var stateDumped = false;

function dumpState(runnerThis) {
    if (stateDumped) return;
    try {
        var state = runnerThis.add(runnerStateOff).readPointer();
        if (state.isNull()) { send({t: "error", msg: "state is null"}); return; }

        var entitiesList = state.add(msEntitiesOff).readPointer();
        var entities = readListPtrs(entitiesList);
        send({t: "info", msg: entities.length + " entities in MatchState"});

        // Serialize each entity at depth 2 — enough to see components + their fields
        for (var i = 0; i < entities.length; i++) {
            var entity = entities[i];
            if (entity.isNull()) continue;

            var data = serialize(entity, 2);
            // Only send units (entities that have an Id string field from BaseUnitComponent)
            // Check if any component has an "Id" field that's a string
            var isUnit = false;
            if (data && data.Components) {
                for (var j = 0; j < data.Components.length; j++) {
                    var comp = data.Components[j];
                    if (comp && comp.Id && typeof comp.Id === "string") {
                        isUnit = true;
                        // Register in unit names
                        var eid = data.Id;
                        if (typeof eid === "object" && eid.Id !== undefined) eid = eid.Id;
                        if (typeof eid === "number") {
                            unitNames[eid] = {id: comp.Id, faction: comp.Faction || "?"};
                        }
                        break;
                    }
                }
            }
            if (isUnit) {
                send({t: "unit", data: data});
            }
        }
        send({t: "info", msg: Object.keys(unitNames).length + " units mapped"});
        send({t: "unit_names", map: unitNames});
        stateDumped = true;
    } catch(e) {
        send({t: "error", msg: "dumpState: " + e.message});
    }
}

// --- Message details with resolved names ---
var moveMsg = findClass("BattleLogicAssembly.dll", "IdunBattle.Messages", "MoveUnitMessage");
var moveUnitIdOff = moveMsg ? getFieldOffset(moveMsg, "UnitId") : -1;
var abilityMsg = findClass("BattleLogicAssembly.dll", "IdunBattle.Messages", "ActiveAbilityMessage");
var abCasterOff = abilityMsg ? getFieldOffset(abilityMsg, "CasterId") : -1;
var abTargetOff = abilityMsg ? getFieldOffset(abilityMsg, "TargetId") : -1;
var abTypeOff = abilityMsg ? getFieldOffset(abilityMsg, "ActiveAbilityType") : -1;

function resolveUnit(eid) {
    var u = unitNames[eid];
    return u ? u.id : ("unit_" + eid);
}

function readMsg(msg) {
    var cls = "?";
    try { cls = s(class_get_name(msg.readPointer())); } catch(e) {}
    var d = {msg: cls};
    try {
        if (cls === "MoveUnitMessage") {
            var uid = msg.add(moveUnitIdOff).readS32();
            d.unit = resolveUnit(uid);
        } else if (cls === "ActiveAbilityMessage") {
            d.caster = resolveUnit(msg.add(abCasterOff).readS32());
            d.target = resolveUnit(msg.add(abTargetOff).readS32());
            d.abilityType = msg.add(abTypeOff).readS32();
        } else if (cls === "AiContainerMessage" || cls === "ExternalPlayerMessage") {
            var inner = msg.add(16).readPointer();
            if (!inner.isNull()) d.inner = readMsg(inner);
        }
    } catch(e) {}
    return d;
}

// === HOOKS ===
hook("BattleLogicAssembly.dll", "IdunBattle.Runner", "IdunRunner", "Apply", {
    onEnter: function(args) {
        try {
            dumpState(args[0]);
            send({t: "action", detail: readMsg(args[1])});
        } catch(e) {}
    }
});

var lastAiLog = 0;
hook("BattleLogicAssembly.dll", "IdunBattle.Core.Services", "AiControl", "RunComputerActionsForPlayer", {
    onEnter: function(args) {
        var now = Date.now();
        if (now - lastAiLog < 2000) return;
        lastAiLog = now;
        send({t: "ai_turn"});
    }
});

hook("BattleLogicAssembly.dll", "IdunBattle.Core.Services", "AiControl", "ApplyAiMessage", {
    onEnter: function(args) {
        try { send({t: "ai_action", detail: readMsg(args[1])}); } catch(e) {}
    }
});
