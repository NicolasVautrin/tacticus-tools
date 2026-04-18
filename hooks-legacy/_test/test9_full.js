// Full battle logger: MatchState dump + unit names + player stack + AI actions
// Compose: _utils/il2cpp-helpers.js + _utils/il2cpp-serializer.js + this file

// --- Resolve offsets ---
var runnerClass = findClass("BattleLogicAssembly.dll", "IdunBattle.Runner", "IdunRunner");
var runnerStateOff = runnerClass ? getFieldOffset(runnerClass, "_state") : -1;
var matchStateClass = findClass("BattleLogicAssembly.dll", "IdunBattle.Core", "MatchState");
var msEntitiesOff = matchStateClass ? getFieldOffset(matchStateClass, "_entities") : -1;
var entityClass = findClass("BattleLogicAssembly.dll", "IdunBattle.Core", "Entity");
var entityIdOff = entityClass ? getFieldOffset(entityClass, "<Id>k__BackingField") : -1;

var moveMsg = findClass("BattleLogicAssembly.dll", "IdunBattle.Messages", "MoveUnitMessage");
var moveUnitIdOff = moveMsg ? getFieldOffset(moveMsg, "UnitId") : -1;
var abilityMsg = findClass("BattleLogicAssembly.dll", "IdunBattle.Messages", "ActiveAbilityMessage");
var abCasterOff = abilityMsg ? getFieldOffset(abilityMsg, "CasterId") : -1;
var abTargetOff = abilityMsg ? getFieldOffset(abilityMsg, "TargetId") : -1;
var abTypeOff = abilityMsg ? getFieldOffset(abilityMsg, "ActiveAbilityType") : -1;

// --- List reader ---
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

function dumpUnitNames(runnerThis) {
    if (stateDumped) return;
    try {
        var state = runnerThis.add(runnerStateOff).readPointer();
        if (state.isNull()) return;
        var entities = readListPtrs(state.add(msEntitiesOff).readPointer());

        // Find BaseUnitComponent field offsets once
        var bucClass = findClass("BattleLogicAssembly.dll", "IdunBattle.Entities.Components", "BaseUnitComponent");
        var bucIdOff = bucClass ? getFieldOffset(bucClass, "Id") : -1;
        var bucFactionOff = bucClass ? getFieldOffset(bucClass, "Faction") : -1;

        for (var i = 0; i < entities.length; i++) {
            var e = entities[i];
            if (e.isNull()) continue;
            var eid = e.add(entityIdOff).readS32();

            // Read Components array to find UnitComponent
            var entityComponentsOff = getFieldOffset(entityClass, "Components");
            var componentsArr = e.add(entityComponentsOff).readPointer();
            if (componentsArr.isNull()) continue;
            var arrLen = componentsArr.add(0x18).readS32();

            for (var j = 0; j < Math.min(arrLen, 50); j++) {
                var comp = componentsArr.add(0x20 + j * Process.pointerSize).readPointer();
                if (comp.isNull()) continue;
                var compName = "?";
                try { compName = s(class_get_name(comp.readPointer())); } catch(ex) {}
                if (compName === "UnitComponent") {
                    // UnitComponent inherits BaseUnitComponent — fields are at same offsets
                    var unitId = null;
                    var faction = null;
                    try { unitId = readIl2cppString(comp.add(bucIdOff).readPointer()); } catch(ex) {}
                    try { faction = readIl2cppString(comp.add(bucFactionOff).readPointer()); } catch(ex) {}
                    if (unitId) {
                        unitNames[eid] = {id: unitId, faction: faction};
                    }
                    break;
                }
            }
        }
        send({t: "units_mapped", count: Object.keys(unitNames).length, map: unitNames});
        stateDumped = true;
    } catch(ex) {
        send({t: "error", msg: "dumpUnitNames: " + ex.message});
    }
}

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

// === HOOK: IdunRunner.Apply — all actions + initial state dump ===
hook("BattleLogicAssembly.dll", "IdunBattle.Runner", "IdunRunner", "Apply", {
    onEnter: function(args) {
        try {
            dumpUnitNames(args[0]);
            send({t: "action", detail: readMsg(args[1])});
        } catch(e) {}
    }
});

// === HOOK: StateMachineActions.ApplyInput — player actions with stack trace ===
hook("Assembly-CSharp.dll", "IdunBattle.View.FSM", "StateMachineActions", "ApplyInput", {
    onEnter: function(args) {
        try {
            var d = readMsg(args[1]);
            send({t: "player", detail: d, stack: getStack(this.context)});
        } catch(e) {}
    }
});

// === HOOK: AiControl.RunComputerActionsForPlayer — AI turn start ===
var lastAiLog = 0;
hook("BattleLogicAssembly.dll", "IdunBattle.Core.Services", "AiControl", "RunComputerActionsForPlayer", {
    onEnter: function(args) {
        var now = Date.now();
        if (now - lastAiLog < 2000) return;
        lastAiLog = now;
        send({t: "ai_turn", stack: getStack(this.context)});
    }
});

// === HOOK: AiControl.ApplyAiMessage — each AI action ===
hook("BattleLogicAssembly.dll", "IdunBattle.Core.Services", "AiControl", "ApplyAiMessage", {
    onEnter: function(args) {
        try { send({t: "ai_action", detail: readMsg(args[1]), stack: getStack(this.context)}); } catch(e) {}
    }
});
