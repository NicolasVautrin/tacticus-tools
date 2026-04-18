// Phase B replace: force unit play order by rewriting <>2__current in MoveNext.
// Default mode = "observe" (no write). Switch via rpc.setMode("reverse"|"same"|"observe").
// Turn boundary detected via CalculateNextActionForPlayer entry.

send({ t: "hook_ready", name: "pick-next-force-order", version: 1 });

var mode = "observe";
var turnQueue = [];
var movenextHooked = false;

var stats = {
    moveNextYields: 0,
    forced: 0,
    sameAsOrig: 0,
    turnsStarted: 0
};

function readInputUnits(thisPtr) {
    var listPtr = thisPtr.add(40).readPointer();
    if (listPtr.isNull()) return [];
    var itemsArr = listPtr.add(0x10).readPointer();
    var size = listPtr.add(0x18).readS32();
    var out = [];
    if (!itemsArr.isNull() && size > 0 && size < 64) {
        for (var i = 0; i < size; i++) {
            out.push(itemsArr.add(0x20 + i * Process.pointerSize).readPointer());
        }
    }
    return out;
}

function installPickHook() {
    var klass = findClass(
        "BattleLogicAssembly.dll",
        "IdunBattle.AI.OperationalDeciders",
        "DefaultGroupOperator"
    );
    if (!klass) { send({ t: "error", msg: "DefaultGroupOperator not found" }); return; }

    var pickMi = findMethod(klass, "PickNextUnit");
    if (!pickMi || pickMi.ptr.isNull()) { send({ t: "error", msg: "PickNextUnit not found" }); return; }

    Interceptor.attach(pickMi.ptr, {
        onLeave: function (retval) {
            if (movenextHooked || retval.isNull()) return;
            try {
                var d7Klass = retval.readPointer();
                var moveNextMi = findMethod(d7Klass, "MoveNext");
                if (moveNextMi && !moveNextMi.ptr.isNull()) {
                    attachMoveNext(moveNextMi.ptr);
                    movenextHooked = true;
                    send({ t: "movenext_installed" });
                }
            } catch (e) {
                send({ t: "error", msg: "install MoveNext failed: " + e.message });
            }
        }
    });
    send({ t: "hooks_installed" });
}

function attachMoveNext(moveNextPtr) {
    Interceptor.attach(moveNextPtr, {
        onEnter: function (args) { this.thisPtr = args[0]; },
        onLeave: function (retval) {
            try {
                var state = this.thisPtr.add(16).readS32();
                var returned = retval.toInt32() !== 0;
                if (state !== 3 || !returned) return;

                stats.moveNextYields++;
                var origCurrent = this.thisPtr.add(24).readPointer();

                if (mode === "observe") {
                    send({ t: "yield", orig: origCurrent.toString(), forced: null });
                    return;
                }

                if (turnQueue.length === 0) {
                    var inputs = readInputUnits(this.thisPtr);
                    if (mode === "reverse") turnQueue = inputs.slice().reverse();
                    else turnQueue = inputs.slice();
                    stats.turnsStarted++;
                    send({ t: "turn_init", mode: mode, size: inputs.length, queue: turnQueue.map(function (p) { return p.toString(); }) });
                }

                var forcedPtr = turnQueue.shift();
                if (forcedPtr.equals(origCurrent)) {
                    stats.sameAsOrig++;
                    send({ t: "yield", orig: origCurrent.toString(), forced: forcedPtr.toString(), same: true });
                    return;
                }
                this.thisPtr.add(24).writePointer(forcedPtr);
                stats.forced++;
                send({ t: "yield", orig: origCurrent.toString(), forced: forcedPtr.toString(), same: false });
            } catch (e) {
                send({ t: "movenext_error", err: e.message });
            }
        }
    });
}

installPickHook();

rpc.exports = {
    setMode: function (m) {
        if (m !== "observe" && m !== "reverse" && m !== "same") {
            throw new Error("mode must be observe|reverse|same");
        }
        mode = m;
        turnQueue = [];
        return { mode: mode };
    },
    stats: function () { return Object.assign({ mode: mode, movenextHooked: movenextHooked }, stats); }
};
