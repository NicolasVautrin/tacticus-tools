// Test: serialize first few entities at depth 3 to see the real structure

var runnerClass = findClass("BattleLogicAssembly.dll", "IdunBattle.Runner", "IdunRunner");
var runnerStateOff = runnerClass ? getFieldOffset(runnerClass, "_state") : -1;
var matchStateClass = findClass("BattleLogicAssembly.dll", "IdunBattle.Core", "MatchState");
var msEntitiesOff = matchStateClass ? getFieldOffset(matchStateClass, "_entities") : -1;

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

var dumped = false;

hook("BattleLogicAssembly.dll", "IdunBattle.Runner", "IdunRunner", "Apply", {
    onEnter: function(args) {
        if (dumped) return;
        dumped = true;
        try {
            var state = args[0].add(runnerStateOff).readPointer();
            var entitiesList = state.add(msEntitiesOff).readPointer();
            var entities = readListPtrs(entitiesList);
            send({t: "info", msg: entities.length + " entities"});

            // Serialize first 5 entities at depth 3
            for (var i = 0; i < Math.min(entities.length, 5); i++) {
                var entity = entities[i];
                if (entity.isNull()) continue;
                var data = serialize(entity, 3);
                send({t: "entity_" + i, data: data});
            }
        } catch(e) {
            send({t: "error", msg: e.message});
        }
    }
});
