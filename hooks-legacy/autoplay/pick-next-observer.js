// Phase B observer: attach-only, emit send() on each fire.
// Goal: confirm the flow before adding Interceptor.replace on PickNextUnit.
//
// Emits:
//   { t: "hook_installed", picks: <ok>, calc: <ok> }
//   { t: "calc_next_action_for_player", thisPtr, teamArg, ts }
//   { t: "pick_next_unit", thisPtr, validUnitsArg, ts }
//
// RPC:
//   stats()  -> { pickCalls, calcCalls, lastPickTs, lastCalcTs }
//   reset()  -> zeros counters

send({ t: "hook_ready", name: "pick-next-observer", version: 1 });

var counters = { pickCalls: 0, calcCalls: 0, lastPickTs: 0, lastCalcTs: 0 };

// List<T> layout (Mono/IL2CPP): at offset 0x10 is the T[] items array,
// at 0x18 is the int _size. Arrays: at 0x18 is the count, elements start at 0x20.
function readIListInfo(listPtr) {
    try {
        if (listPtr.isNull()) return { err: "null" };
        var klassPtr = listPtr.readPointer();
        var klassName = s(class_get_name(klassPtr));
        var itemsArr = listPtr.add(0x10).readPointer();
        var size = listPtr.add(0x18).readS32();
        var ptrs = [];
        if (!itemsArr.isNull() && size >= 0 && size < 64) {
            for (var i = 0; i < size; i++) {
                ptrs.push(itemsArr.add(0x20 + i * Process.pointerSize).readPointer().toString());
            }
        }
        return { klass: klassName, size: size, items: ptrs };
    } catch (e) {
        return { err: e.message };
    }
}

function installHooks() {
    var klass = findClass(
        "BattleLogicAssembly.dll",
        "IdunBattle.AI.OperationalDeciders",
        "DefaultGroupOperator"
    );
    if (!klass) {
        send({ t: "error", msg: "DefaultGroupOperator class not found" });
        return { picks: false, calc: false };
    }

    var picksOk = false, calcOk = false;

    var pickMi = findMethod(klass, "PickNextUnit");
    if (pickMi && !pickMi.ptr.isNull()) {
        Interceptor.attach(pickMi.ptr, {
            onEnter(args) {
                counters.pickCalls++;
                counters.lastPickTs = Date.now();
                var listPtr = args[1];
                var listInfo = readIListInfo(listPtr);
                send({
                    t: "pick_next_unit",
                    thisPtr: args[0].toString(),
                    validUnitsPtr: listPtr.toString(),
                    listInfo: listInfo,
                    ts: counters.lastPickTs
                });
            }
        });
        picksOk = true;
    }

    var calcMi = findMethod(klass, "CalculateNextActionForPlayer");
    if (calcMi && !calcMi.ptr.isNull()) {
        Interceptor.attach(calcMi.ptr, {
            onEnter(args) {
                counters.calcCalls++;
                counters.lastCalcTs = Date.now();
                send({
                    t: "calc_next_action_for_player",
                    thisPtr: args[0].toString(),
                    teamArg: args[1].toString(),
                    ts: counters.lastCalcTs
                });
            }
        });
        calcOk = true;
    }

    return { picks: picksOk, calc: calcOk };
}

var result = installHooks();
send({ t: "hook_installed", picks: result.picks, calc: result.calc });

rpc.exports = {
    stats: function () { return counters; },
    reset: function () {
        counters.pickCalls = 0;
        counters.calcCalls = 0;
        counters.lastPickTs = 0;
        counters.lastCalcTs = 0;
        return { ok: true };
    }
};
