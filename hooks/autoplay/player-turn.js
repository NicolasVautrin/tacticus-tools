// hook: Auto-play — analyze game state, send options to Claude, receive commands, inject actions
// requires: _utils/il2cpp-helpers, _utils/il2cpp-serializer
// provides: recv("action") handler + turn analysis via game APIs
//
// Flow:
//   1. Hook IdunRunner.Apply to capture runner instance
//   2. When it's player turn, query game APIs (reachable tiles, valid targets, damage predictions)
//   3. send({t: "your_turn", ...}) with all options pre-computed
//   4. recv("action") to receive Claude's decision and inject it
//
// Commands (via POST /api/scripts/{id}/message):
//   {type: "action", payload: {action: "end_turn"}}
//   {type: "action", payload: {action: "ability", casterId: 90, targetId: 79, abilityType: 1123}}

// --- IL2CPP APIs ---
var il2cpp_object_new = new NativeFunction(
    il2cpp.findExportByName("il2cpp_object_new"), "pointer", ["pointer"]);
var il2cpp_runtime_invoke = new NativeFunction(
    il2cpp.findExportByName("il2cpp_runtime_invoke"), "pointer",
    ["pointer", "pointer", "pointer", "pointer"]);

// --- Message classes ---
var endTurnClass = findClass("BattleLogicAssembly.dll", "IdunBattle.Messages", "EndTurnMessage");
var abilityMsgClass = findClass("BattleLogicAssembly.dll", "IdunBattle.Messages", "ActiveAbilityMessage");

// --- Field offsets ---
var abCasterOff = abilityMsgClass ? getFieldOffset(abilityMsgClass, "CasterId") : -1;
var abTargetOff = abilityMsgClass ? getFieldOffset(abilityMsgClass, "TargetId") : -1;
var abTypeOff = abilityMsgClass ? getFieldOffset(abilityMsgClass, "ActiveAbilityType") : -1;
var abSkipFlagsOff = abilityMsgClass ? getFieldOffset(abilityMsgClass, "SkipFlags") : -1;

// --- Runner + services ---
var runnerClass = findClass("BattleLogicAssembly.dll", "IdunBattle.Runner", "IdunRunner");
var applyInfo = findMethod(runnerClass, "Apply");
// IL2CPP method signature on ARM64: fn(this, arg1, ..., MethodInfo*)
// Try both calling conventions
var applyFnWithMethodInfo = new NativeFunction(applyInfo.ptr, "void", ["pointer", "pointer", "pointer"]);
var applyFnSimple = new NativeFunction(applyInfo.ptr, "void", ["pointer", "pointer"]);

function callApply(runner, message) {
    // Try with MethodInfo* as last arg first (IL2CPP convention)
    try {
        applyFnWithMethodInfo(runner, message, applyInfo.info);
        return;
    } catch(e) {
        send({t: "debug", step: "applyFnWithMethodInfo failed", error: e.message});
    }
    // Fallback: try runtime_invoke
    invokeMethod(applyInfo.info, runner, [message]);
}

var runnerStateOff = getFieldOffset(runnerClass, "_state");
var runnerConfigOff = getFieldOffset(runnerClass, "<Configuration>k__BackingField");
var runnerBattleQueryOff = getFieldOffset(runnerClass, "<BattleQuery>k__BackingField");
var runnerDamagePredOff = getFieldOffset(runnerClass, "<DamagePrediction>k__BackingField");
var runnerPathfindersOff = getFieldOffset(runnerClass, "<Pathfinders>k__BackingField");
var runnerTargetingOff = getFieldOffset(runnerClass, "<TargetingQuery>k__BackingField");

// --- MatchState ---
var matchStateClass = findClass("BattleLogicAssembly.dll", "IdunBattle.Core", "MatchState");
var msEntitiesOff = getFieldOffset(matchStateClass, "_entities");

// --- Entity ---
var entityClass = findClass("BattleLogicAssembly.dll", "IdunBattle.Core", "Entity");
var entityIdOff = getFieldOffset(entityClass, "<Id>k__BackingField");
var entityTypeOff = getFieldOffset(entityClass, "<Type>k__BackingField");
var entityComponentsOff = getFieldOffset(entityClass, "Components");

// --- BaseUnitComponent ---
var bucClass = findClass("BattleLogicAssembly.dll", "IdunBattle.Entities.Components", "BaseUnitComponent");
var bucIdOff = getFieldOffset(bucClass, "Id");
var bucFactionOff = getFieldOffset(bucClass, "Faction");

// --- HealthComponent (fields inherited from FillUpStatComponent) ---
var fillUpClass = findClass("BattleLogicAssembly.dll", "IdunBattle.Entities.Components", "FillUpStatComponent");
var healthRemainingOff = fillUpClass ? getFieldOffset(fillUpClass, "RemainingValue") : -1;
var healthMaxOff = fillUpClass ? getFieldOffset(fillUpClass, "MaximumValue") : -1;

// --- ActiveAbilityComponent ---
var aaCompClass = findClass("BattleLogicAssembly.dll", "IdunBattle.Entities.Components", "ActiveAbilityComponent");
var aaNormalAttackOff = aaCompClass ? getFieldOffset(aaCompClass, "NormalAttackType") : -1;

// --- OwnerComponent ---
var ownerCompClass = findClass("BattleLogicAssembly.dll", "IdunBattle.Entities.Components", "OwnerComponent");
var ownerPlayerOff = ownerCompClass ? getFieldOffset(ownerCompClass, "PlayerEntityId") : -1;

// --- PlayerComponent ---
var playerCompClass = findClass("BattleLogicAssembly.dll", "IdunBattle.Entities.Components", "PlayerComponent");
var playerTypeOff = playerCompClass ? getFieldOffset(playerCompClass, "Type") : -1;
var playerUnitIdsOff = playerCompClass ? getFieldOffset(playerCompClass, "UnitIds") : -1;

// --- TurnComponent (on MatchEntity) ---
var turnCompClass = findClass("BattleLogicAssembly.dll", "IdunBattle.Entities.Components", "TurnComponent");
var turnCurrentPlayerOff = turnCompClass ? getFieldOffset(turnCompClass, "_currentPlayerId") : -1;

// --- Runner instance + pending actions ---
var runnerInstance = null;
var pendingActions = [];  // actions to execute on the next Apply call (main thread)

// --- List reading helper ---
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

function readListInts(listPtr) {
    if (listPtr.isNull()) return [];
    var items = listPtr.add(0x10).readPointer();
    var size = listPtr.add(0x18).readS32();
    if (items.isNull() || size <= 0 || size > 5000) return [];
    var result = [];
    for (var i = 0; i < size; i++) {
        result.push(items.add(0x20 + i * 4).readS32());
    }
    return result;
}

// --- Read component from entity by class name ---
function readComponent(entity, compClassName) {
    var componentsArr = entity.add(entityComponentsOff).readPointer();
    if (componentsArr.isNull()) return null;
    var arrLen = componentsArr.add(0x18).readS32();
    for (var j = 0; j < Math.min(arrLen, 50); j++) {
        var comp = componentsArr.add(0x20 + j * Process.pointerSize).readPointer();
        if (comp.isNull()) continue;
        try {
            if (s(class_get_name(comp.readPointer())) === compClassName) return comp;
        } catch(e) {}
    }
    return null;
}

// --- Build turn summary for Claude ---
function buildTurnSummary() {
    if (!runnerInstance) return null;

    try {
        var state = runnerInstance.add(runnerStateOff).readPointer();
        var entities = readListPtrs(state.add(msEntitiesOff).readPointer());

        // Find current player ID from MatchEntity's TurnComponent
        var currentPlayerId = -1;
        var humanPlayerEntityId = -1;
        var units = [];
        var unitEntities = {}; // entityId -> entity pointer

        for (var i = 0; i < entities.length; i++) {
            var e = entities[i];
            if (e.isNull()) continue;
            var eid = e.add(entityIdOff).readS32();
            var etype = e.add(entityTypeOff).readS32();

            // Match entity (type 2) — get current player turn
            if (etype === 2) {
                var turnComp = readComponent(e, "TurnComponent");
                if (turnComp && turnCurrentPlayerOff >= 0) {
                    currentPlayerId = turnComp.add(turnCurrentPlayerOff).readS32();
                }
            }

            // Player entity (type 4) — find human player
            if (etype === 4) {
                var playerComp = readComponent(e, "PlayerComponent");
                if (playerComp && playerTypeOff >= 0) {
                    var playerType = playerComp.add(playerTypeOff).readS32();
                    if (playerType === 0) { // 0 = human player
                        humanPlayerEntityId = eid;
                    }
                }
            }

            // Unit entity (type 1) — collect all units
            if (etype === 1) {
                unitEntities[eid] = e;
                var unitComp = readComponent(e, "UnitComponent");
                var ownerComp = readComponent(e, "OwnerComponent");
                var healthComp = readComponent(e, "HealthComponent");
                var aaComp = readComponent(e, "ActiveAbilityComponent");

                var unitInfo = {entityId: eid};

                if (unitComp && bucIdOff >= 0) {
                    try { unitInfo.name = readIl2cppString(unitComp.add(bucIdOff).readPointer()); } catch(ex) {}
                    try { unitInfo.faction = readIl2cppString(unitComp.add(bucFactionOff).readPointer()); } catch(ex) {}
                }
                if (ownerComp && ownerPlayerOff >= 0) {
                    unitInfo.owner = ownerComp.add(ownerPlayerOff).readS32();
                }
                if (healthComp) {
                    if (healthRemainingOff >= 0) unitInfo.hp = healthComp.add(healthRemainingOff).readS32();
                    if (healthMaxOff >= 0) unitInfo.maxHp = healthComp.add(healthMaxOff).readS32();
                }
                if (aaComp && aaNormalAttackOff >= 0) {
                    unitInfo.normalAttack = aaComp.add(aaNormalAttackOff).readS32();
                }
                unitInfo.alive = (unitInfo.hp || 0) > 0;

                units.push(unitInfo);
            }
        }

        // Separate player units vs enemy units
        var playerUnits = [];
        var enemyUnits = [];
        for (var u = 0; u < units.length; u++) {
            if (units[u].owner === humanPlayerEntityId) {
                playerUnits.push(units[u]);
            } else {
                enemyUnits.push(units[u]);
            }
        }

        return {
            currentPlayerId: currentPlayerId,
            humanPlayerEntityId: humanPlayerEntityId,
            isPlayerTurn: currentPlayerId === humanPlayerEntityId,
            playerUnits: playerUnits,
            enemyUnits: enemyUnits
        };
    } catch(e) {
        return {error: e.message};
    }
}

// --- Message creation ---

// --- Helper: invoke IL2CPP method via runtime_invoke ---
function invokeMethod(methodInfo, obj, args) {
    // il2cpp_runtime_invoke(MethodInfo* method, void* obj, void** params, Il2CppException** exc)
    // For reference type args: params[i] is the pointer to the object directly (NOT pointer-to-pointer)
    var exc = Memory.alloc(Process.pointerSize);
    exc.writePointer(ptr(0));
    var params = ptr(0);
    if (args && args.length > 0) {
        params = Memory.alloc(args.length * Process.pointerSize);
        for (var i = 0; i < args.length; i++) {
            params.add(i * Process.pointerSize).writePointer(args[i]);
        }
    }
    var result = il2cpp_runtime_invoke(methodInfo, obj, params, exc);
    var excVal = exc.readPointer();
    if (!excVal.isNull()) {
        // Try to read exception message
        var excMsg = "IL2CPP exception";
        try {
            var excClass = s(class_get_name(excVal.readPointer()));
            excMsg += " (" + excClass + ")";
        } catch(e) {}
        throw new Error(excMsg);
    }
    return result;
}

function createEndTurnMessage() {
    var msg = il2cpp_object_new(endTurnClass);
    if (msg.isNull()) throw new Error("il2cpp_object_new returned null for EndTurnMessage");
    // Call .ctor() via runtime_invoke
    var ctor = findMethod(endTurnClass, ".ctor");
    if (ctor) {
        invokeMethod(ctor.info, msg, null);
    }
    return msg;
}

function createAbilityMessage(casterId, targetId, abilityType) {
    var msg = il2cpp_object_new(abilityMsgClass);
    if (msg.isNull()) throw new Error("il2cpp_object_new returned null for ActiveAbilityMessage");
    // Call parameterless .ctor first to initialize
    var ctor = findMethod(abilityMsgClass, ".ctor");
    if (ctor) {
        invokeMethod(ctor.info, msg, null);
    }
    // Then set fields
    msg.add(abCasterOff).writeS32(casterId);
    msg.add(abTargetOff).writeS32(targetId);
    msg.add(abTypeOff).writeS32(abilityType);
    msg.add(abSkipFlagsOff).writeU8(0);
    return msg;
}

function createMessage(cmd) {
    if (cmd.action === "end_turn") {
        return createEndTurnMessage();
    }
    if (cmd.action === "ability") {
        return createAbilityMessage(cmd.casterId, cmd.targetId, cmd.abilityType);
    }
    throw new Error("Unknown action: " + cmd.action);
}

// --- Hook Apply to capture runner + execute pending actions + send turn summary ---
var lastTurnSent = 0;

hook("BattleLogicAssembly.dll", "IdunBattle.Runner", "IdunRunner", "Apply", {
    onEnter: function(args) {
        runnerInstance = args[0];
    },
    onLeave: function(retval) {
        // Execute any pending actions (we're on the main thread here)
        while (pendingActions.length > 0) {
            var cmd = pendingActions.shift();
            try {
                var message = createMessage(cmd);
                // Call Apply directly — we're on the correct thread
                var applyDirect = new NativeFunction(applyInfo.ptr, "void", ["pointer", "pointer", "pointer"]);
                applyDirect(runnerInstance, message, applyInfo.info);
                send({t: "played", cmd: cmd});
            } catch(e) {
                send({t: "error", msg: "play failed: " + e.message});
                break; // stop processing on error
            }
        }

        // After each action, check if it's now the player's turn and send summary
        var now = Date.now();
        if (now - lastTurnSent < 500) return; // debounce
        try {
            var summary = buildTurnSummary();
            if (summary && summary.isPlayerTurn) {
                lastTurnSent = now;
                send({t: "your_turn", state: summary});
            }
        } catch(e) {}
    }
});

// --- recv handler for commands ---
// Actions are queued and executed on the next Apply call (main thread)
recv("action", function onAction(msg) {
    if (!runnerInstance) {
        send({t: "error", msg: "No runner instance yet"});
        recv("action", onAction);
        return;
    }
    var cmd = msg.payload;
    pendingActions.push(cmd);
    send({t: "queued", cmd: cmd, pending: pendingActions.length});
    recv("action", onAction);
});

// --- recv handler for state query on demand ---
recv("query_state", function onQuery(msg) {
    try {
        var summary = buildTurnSummary();
        send({t: "state", state: summary});
    } catch(e) {
        send({t: "error", msg: "query failed: " + e.message});
    }
    recv("query_state", onQuery);
});

// --- Hook Update to process pending actions on main thread ---
hook("Assembly-CSharp.dll", "IdunBattle.View.Game", "IdunGameViews", "Update", {
    onEnter: function(args) {
        if (pendingActions.length === 0 || !runnerInstance) return;
        while (pendingActions.length > 0) {
            var cmd = pendingActions.shift();
            try {
                var message = createMessage(cmd);
                var applyDirect = new NativeFunction(applyInfo.ptr, "void", ["pointer", "pointer", "pointer"]);
                applyDirect(runnerInstance, message, applyInfo.info);
                send({t: "played", cmd: cmd});
            } catch(e) {
                send({t: "error", msg: "play failed: " + e.message});
                break;
            }
        }
    }
});

send({t: "autoplay_ready", msg: "Hooks installed. Play a turn to capture runner, then auto-play begins."});
