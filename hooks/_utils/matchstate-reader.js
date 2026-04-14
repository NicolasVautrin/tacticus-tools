// util: MatchState reader — runner access, turn detection, raw serialization, game queries
// requires: _utils/il2cpp-helpers, _utils/il2cpp-invoke, _utils/il2cpp-serializer
// provides: runnerInstance, isPlayerTurn(), getSerializedState(),
//           getEntityById(), getUnitTile(), queryReachableTiles(), queryDamagePrediction()

// --- Runner ---
var runnerClass = findClass("BattleLogicAssembly.dll", "IdunBattle.Runner", "IdunRunner");
var runnerApplyInfo = findMethod(runnerClass, "Apply");
var runnerStateOff = getFieldOffset(runnerClass, "_state");
var runnerPathfindersOff = getFieldOffset(runnerClass, "<Pathfinders>k__BackingField");
var runnerDamagePredOff = getFieldOffset(runnerClass, "<DamagePrediction>k__BackingField");
var runnerTargetingOff = getFieldOffset(runnerClass, "<TargetingQuery>k__BackingField");

// --- Entity offsets (for lookup + turn detection) ---
var _entityClass = findClass("BattleLogicAssembly.dll", "IdunBattle.Core", "Entity");
var _entityIdOff = getFieldOffset(_entityClass, "<Id>k__BackingField");
var _entityTypeOff = getFieldOffset(_entityClass, "<Type>k__BackingField");
var _entityComponentsOff = getFieldOffset(_entityClass, "Components");
var _msEntitiesOff = getFieldOffset(
    findClass("BattleLogicAssembly.dll", "IdunBattle.Core", "MatchState"), "_entities");

// --- Turn detection offsets ---
var _turnCompClass = findClass("BattleLogicAssembly.dll", "IdunBattle.Entities.Components", "TurnComponent");
var _turnCurrentPlayerOff = _turnCompClass ? getFieldOffset(_turnCompClass, "_currentPlayerId") : -1;
var _playerCompClass = findClass("BattleLogicAssembly.dll", "IdunBattle.Entities.Components", "PlayerComponent");
var _playerTypeOff = _playerCompClass ? getFieldOffset(_playerCompClass, "Type") : -1;

// --- Foot component offsets (for unit -> tile lookup) ---
var _footCompClass = findClass("BattleLogicAssembly.dll", "IdunBattle.Entities.Components", "UnitFootComponent");
var _footUnitIdOff = _footCompClass ? getFieldOffset(_footCompClass, "UnitId") : -1;
var _footTileIdOff = _footCompClass ? getFieldOffset(_footCompClass, "TileId") : -1;

// --- Movement component (for reachable tiles depth) ---
var _moveCompClass = findClass("BattleLogicAssembly.dll", "IdunBattle.Entities.Components", "MovementComponent");
var _moveInitialOff = _moveCompClass ? getFieldOffset(_moveCompClass, "InitialValue") : -1;

// --- Game service classes + methods ---
var _pathfindersClass = findClass("BattleLogicAssembly.dll", "IdunBattle.Entities.Pathfinding", "Pathfinders");
var _findReachableInfo = _pathfindersClass ? findMethod(_pathfindersClass, "FindReachableTiles") : null;

var _damagePredClass = findClass("BattleLogicAssembly.dll", "IdunBattle.Core.Services", "DamagePrediction");
var _predictNormalInfo = _damagePredClass ? findMethod(_damagePredClass, "PredictNormalAttack") : null;

var runnerInstance = null;
var matchStateRef = null; // fallback: captured from FSM tap before runner is available

// --- Internal helpers ---

function _readListPtrs(listPtr) {
    if (listPtr.isNull()) return [];
    var items = listPtr.add(0x10).readPointer();
    var size = listPtr.add(0x18).readS32();
    if (items.isNull() || size <= 0 || size > 5000) return [];
    var r = [];
    for (var i = 0; i < size; i++)
        r.push(items.add(0x20 + i * Process.pointerSize).readPointer());
    return r;
}

function _findComp(entity, name) {
    var arr = entity.add(_entityComponentsOff).readPointer();
    if (arr.isNull()) return null;
    var len = arr.add(0x18).readS32();
    for (var j = 0; j < Math.min(len, 50); j++) {
        var c = arr.add(0x20 + j * Process.pointerSize).readPointer();
        if (c.isNull()) continue;
        try { if (s(class_get_name(c.readPointer())) === name) return c; } catch(e) {}
    }
    return null;
}

function _getEntities() {
    var state = runnerInstance.add(runnerStateOff).readPointer();
    return _readListPtrs(state.add(_msEntitiesOff).readPointer());
}

// --- Public: entity lookup ---

function getEntityById(entityId) {
    if (!runnerInstance) return null;
    var entities = _getEntities();
    for (var i = 0; i < entities.length; i++) {
        var e = entities[i];
        if (!e.isNull() && e.add(_entityIdOff).readS32() === entityId) return e;
    }
    return null;
}

function getUnitTile(unitEntityId) {
    // FootEntity (type 5) links unit -> tile
    if (!runnerInstance) return null;
    var entities = _getEntities();
    for (var i = 0; i < entities.length; i++) {
        var e = entities[i];
        if (e.isNull() || e.add(_entityTypeOff).readS32() !== 5) continue;
        var fc = _findComp(e, "UnitFootComponent");
        if (fc && fc.add(_footUnitIdOff).readS32() === unitEntityId) {
            var tileId = fc.add(_footTileIdOff).readS32();
            return getEntityById(tileId);
        }
    }
    return null;
}

// --- Turn detection ---

function isPlayerTurn() {
    if (!runnerInstance) return false;
    try {
        var entities = _getEntities();
        var cur = -1, human = -1;
        for (var i = 0; i < entities.length; i++) {
            var e = entities[i];
            if (e.isNull()) continue;
            var t = e.add(_entityTypeOff).readS32();
            if (t === 2) {
                var tc = _findComp(e, "TurnComponent");
                if (tc) cur = tc.add(_turnCurrentPlayerOff).readS32();
            }
            if (t === 4) {
                var pc = _findComp(e, "PlayerComponent");
                if (pc && pc.add(_playerTypeOff).readS32() === 0)
                    human = e.add(_entityIdOff).readS32();
            }
        }
        return cur === human && cur !== -1;
    } catch(e) { return false; }
}

// --- Full state serialization ---

function getSerializedState(depth) {
    if (!runnerInstance) return null;
    try {
        var state = runnerInstance.add(runnerStateOff).readPointer();
        return serialize(state, depth || 4);
    } catch(e) { return {error: e.message}; }
}

// --- Game queries (called on main thread via RPC) ---

// Helper: allocate a value-type arg for il2cpp_runtime_invoke
function _valArg(value) {
    var p = Memory.alloc(8);
    p.writeS32(value);
    return p;
}

function queryReachableTiles(unitId) {
    if (!runnerInstance || !_findReachableInfo) return {error: "not ready"};
    var unit = getEntityById(unitId);
    if (!unit) return {error: "unit not found: " + unitId};
    var tile = getUnitTile(unitId);
    if (!tile) return {error: "tile not found for unit: " + unitId};

    // Read movement value from MovementComponent
    var moveComp = _findComp(unit, "MovementComponent");
    var depth = 3;
    if (moveComp && _moveInitialOff >= 0) {
        depth = moveComp.add(_moveInitialOff).readS32();
    }

    var pathfinders = runnerInstance.add(runnerPathfindersOff).readPointer();

    // Direct NativeFunction call (ARM64 IL2CPP convention):
    // this, PathfinderType(int), IEntity start, int depth, IEntity unit, MethodInfo*
    var findReachableFn = new NativeFunction(_findReachableInfo.ptr, "pointer",
        ["pointer", "int", "pointer", "int", "pointer", "pointer"]);
    var result = findReachableFn(pathfinders, 0, tile, depth, unit, _findReachableInfo.info);

    if (result.isNull()) return {error: "FindReachableTiles returned null"};

    // DisposableList<TileEntity> — read items before they get pooled
    // Read _size and iterate _items array
    var size = result.add(0x18).readS32();
    var items = result.add(0x10).readPointer();
    var tiles = [];
    for (var i = 0; i < Math.min(size, 200); i++) {
        var t = items.add(0x20 + i * Process.pointerSize).readPointer();
        if (t.isNull()) continue;
        var tid = t.add(_entityIdOff).readS32();
        tiles.push(tid);
    }
    return {unitId: unitId, depth: depth, tileIds: tiles, count: size};
}

function queryDamagePrediction(attackerId, defenderId) {
    if (!runnerInstance || !_predictNormalInfo) return {error: "not ready"};
    var attacker = getEntityById(attackerId);
    var defender = getEntityById(defenderId);
    if (!attacker) return {error: "attacker not found: " + attackerId};
    if (!defender) return {error: "defender not found: " + defenderId};

    var damagePred = runnerInstance.add(runnerDamagePredOff).readPointer();
    // PredictNormalAttack(attacker, attackerPosition, defender)
    // attackerPosition is UnitPosition — we need to construct it
    // For now, pass null and see if it works with just the attacker tile
    // TODO: construct UnitPosition properly
    return {error: "not yet implemented — needs UnitPosition construction"};
}

// Note: LocalizationQuery RPC was attempted but returns null for all abilities.
// Ability descriptions are resolved statically by the backend using I2 templates + abilities.json configs.


// queryAbilitiesInfo removed — LocalizationQuery RPC returns null.
// Descriptions are resolved by the backend via I2 templates + abilities.json.

console.log("[*] MatchState reader loaded");
