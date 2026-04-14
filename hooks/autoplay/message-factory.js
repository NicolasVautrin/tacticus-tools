// hook: Message factory — create IL2CPP battle messages
// requires: _utils/il2cpp-helpers, _utils/il2cpp-invoke, _utils/matchstate-reader
// provides: createMessage(cmd)

// --- Message classes ---
var endTurnClass = findClass("BattleLogicAssembly.dll", "IdunBattle.Messages", "EndTurnMessage");
var abilityMsgClass = findClass("BattleLogicAssembly.dll", "IdunBattle.Messages", "ActiveAbilityMessage");
var moveMsgClass = findClass("BattleLogicAssembly.dll", "IdunBattle.Messages", "MoveUnitMessage");
var positionClass = findClass("BattleLogicAssembly.dll", "IdunBattle.Messages", "Position");
var _posIsValueType = positionClass ? class_is_valuetype(positionClass) : -1;
var _posInstanceSize = positionClass ? class_instance_size(positionClass) : -1;
send({t: "debug", positionClass: !!positionClass, isValueType: _posIsValueType, instanceSize: _posInstanceSize});

// --- ActiveAbilityMessage field offsets ---
var abCasterOff = abilityMsgClass ? getFieldOffset(abilityMsgClass, "CasterId") : -1;
var abTargetOff = abilityMsgClass ? getFieldOffset(abilityMsgClass, "TargetId") : -1;
var abTypeOff = abilityMsgClass ? getFieldOffset(abilityMsgClass, "ActiveAbilityType") : -1;
var abSkipFlagsOff = abilityMsgClass ? getFieldOffset(abilityMsgClass, "SkipFlags") : -1;

// --- MoveUnitMessage field offsets ---
var mvUnitIdOff = moveMsgClass ? getFieldOffset(moveMsgClass, "UnitId") : -1;
var mvPositionsOff = moveMsgClass ? getFieldOffset(moveMsgClass, "UnitFeetPositions") : -1;
var mvSkipFlagsOff = moveMsgClass ? getFieldOffset(moveMsgClass, "SkipFlags") : -1;

// --- Position field offsets ---
var posColumnOff = positionClass ? getFieldOffset(positionClass, "Column") : -1;
var posRowOff = positionClass ? getFieldOffset(positionClass, "Row") : -1;

function createEndTurnMessage() {
    return createObject(endTurnClass);
}

function createAbilityMessage(casterId, targetId, abilityType) {
    var msg = createObject(abilityMsgClass);
    msg.add(abCasterOff).writeS32(casterId);
    msg.add(abTargetOff).writeS32(targetId);
    msg.add(abTypeOff).writeS32(abilityType);
    msg.add(abSkipFlagsOff).writeU8(0);
    return msg;
}

function createPosition(col, row) {
    // Position is a VALUE TYPE (struct) — for List<Position>.Add we need a boxed object
    // but the data pointer for runtime_invoke is at object+0x10
    var pos = il2cpp_object_new(positionClass);
    pos.add(posColumnOff).writeS32(col);
    pos.add(posRowOff).writeS32(row);
    return pos;
}

// For il2cpp_runtime_invoke, value type args need pointer to unboxed data
function createPositionUnboxed(col, row) {
    // Allocate raw struct: just Column (4 bytes) + Row (4 bytes)
    var buf = Memory.alloc(8);
    buf.writeS32(col);
    buf.add(4).writeS32(row);
    return buf;
}

// --- Resolve List<Position> class from the field type ---
var _listPositionClass = (function() {
    var it = Memory.alloc(Process.pointerSize);
    it.writePointer(ptr(0));
    var f;
    while (!(f = class_get_fields(moveMsgClass, it)).isNull()) {
        if (s(field_get_name(f)) === "UnitFeetPositions") {
            var ft = field_get_type(f);
            return class_from_type(ft);
        }
    }
    return null;
})();
var _listAddInfo = _listPositionClass ? findMethod(_listPositionClass, "Add") : null;

function createMoveMessage(unitId, positions) {
    // positions = [{col, row}] — 1 element for standard units
    var msg = il2cpp_object_new(moveMsgClass);
    msg.add(mvUnitIdOff).writeS32(unitId);
    msg.add(mvSkipFlagsOff).writeU8(0);

    // Create List<Position> — Position is a value type (8 bytes: Column + Row)
    // Write directly into List internals instead of using Add()
    var list = createObject(_listPositionClass);
    // List<T> layout: [klass:8][monitor:8][_items:8][_size:4][_version:4]
    // _items is a T[] (szarray): [klass:8][monitor:8][bounds:8][max_length:4][padding:4][data...]
    // For value type T, data is inline: items[0] at offset 0x20, size = sizeof(T) = 8

    var count = positions.length;
    // Ensure _items array is big enough — the .ctor creates a default empty array
    // We need to create a new T[] with enough capacity
    // Find the array class for Position[]
    var itemsArray = list.add(0x10).readPointer();
    var maxLen = itemsArray.isNull() ? 0 : itemsArray.add(0x18).readS32();

    if (maxLen < count) {
        // Value type param for runtime_invoke = pointer to raw struct data
        for (var i = 0; i < count; i++) {
            var unboxed = createPositionUnboxed(positions[i].col, positions[i].row);
            invokeMethod(_listAddInfo.info, list, [unboxed]);
        }
    } else {
        // Write directly
        for (var i = 0; i < count; i++) {
            itemsArray.add(0x20 + i * 8).writeS32(positions[i].col);
            itemsArray.add(0x20 + i * 8 + 4).writeS32(positions[i].row);
        }
        list.add(0x18).writeS32(count); // _size
    }

    msg.add(mvPositionsOff).writePointer(list);
    return msg;
}

function createMessage(cmd) {
    if (cmd.action === "end_turn") return createEndTurnMessage();
    if (cmd.action === "ability") return createAbilityMessage(cmd.casterId, cmd.targetId, cmd.abilityType);
    if (cmd.action === "move") return createMoveMessage(cmd.unitId, cmd.positions);
    throw new Error("Unknown action: " + cmd.action);
}

console.log("[*] Message factory loaded");
