// Dump unit entities from MatchState — find unit names
var runnerClass = findClass("BattleLogicAssembly.dll", "IdunBattle.Runner", "IdunRunner");
var runnerStateOff = runnerClass ? getFieldOffset(runnerClass, "_state") : -1;
var matchStateClass = findClass("BattleLogicAssembly.dll", "IdunBattle.Core", "MatchState");
var msEntitiesOff = matchStateClass ? getFieldOffset(matchStateClass, "_entities") : -1;
var entityClass = findClass("BattleLogicAssembly.dll", "IdunBattle.Core", "Entity");
var entityIdOff = entityClass ? getFieldOffset(entityClass, "<Id>k__BackingField") : -1;

send({t: "offsets", runner_state: runnerStateOff, ms_entities: msEntitiesOff, entity_id: entityIdOff});

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
            var entities = readListPtrs(state.add(msEntitiesOff).readPointer());
            send({t: "info", msg: entities.length + " entities"});

            // Dump just 2 unit entities (IDs 90 and 79) at depth 3
            for (var i = 0; i < entities.length; i++) {
                var e = entities[i];
                if (e.isNull()) continue;
                var eid = e.add(entityIdOff).readS32();
                if (eid === 90 || eid === 79) {
                    send({t: "unit", entityId: eid, data: serialize(e, 3)});
                }
            }
        } catch(ex) {
            send({t: "error", msg: ex.message});
        }
    }
});
