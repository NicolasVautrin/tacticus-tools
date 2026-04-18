// Phase B observer: hook <PickNextUnit>d__7.MoveNext to inspect <>2__current.
// Installs lazily: on first PickNextUnit onLeave, we grab the returned d__7 ptr,
// read its klass, find MoveNext, and attach.

send({ t: "hook_ready", name: "pick-next-movenext-observer", version: 1 });

var moveNextHooked = false;
var counters = { moveNextCalls: 0, pickCalls: 0, lastCurrentPtr: null };

function installPickNextHook() {
    var klass = findClass(
        "BattleLogicAssembly.dll",
        "IdunBattle.AI.OperationalDeciders",
        "DefaultGroupOperator"
    );
    if (!klass) {
        send({ t: "error", msg: "DefaultGroupOperator not found" });
        return;
    }
    var pickMi = findMethod(klass, "PickNextUnit");
    if (!pickMi || pickMi.ptr.isNull()) {
        send({ t: "error", msg: "PickNextUnit not found" });
        return;
    }

    Interceptor.attach(pickMi.ptr, {
        onLeave: function (retval) {
            counters.pickCalls++;
            if (retval.isNull()) return;

            if (!moveNextHooked) {
                // First return — retval is d__7*. Find its MoveNext.
                try {
                    var d7Klass = retval.readPointer();
                    var d7KlassName = s(class_get_name(d7Klass));
                    var moveNextMi = findMethod(d7Klass, "MoveNext");
                    if (!moveNextMi || moveNextMi.ptr.isNull()) {
                        send({ t: "error", msg: "MoveNext not found on " + d7KlassName });
                        return;
                    }
                    attachMoveNext(moveNextMi.ptr, d7KlassName);
                    moveNextHooked = true;
                    send({ t: "movenext_installed", d7Klass: d7KlassName, ptr: moveNextMi.ptr.toString() });
                } catch (e) {
                    send({ t: "error", msg: "install MoveNext failed: " + e.message });
                }
            }
        }
    });
    send({ t: "pick_hook_installed" });
}

function attachMoveNext(moveNextPtr, d7KlassName) {
    Interceptor.attach(moveNextPtr, {
        onEnter: function (args) {
            this.thisPtr = args[0];
        },
        onLeave: function (retval) {
            counters.moveNextCalls++;
            try {
                var returnedTrue = retval.toInt32() !== 0;
                var currentPtr = this.thisPtr.add(24).readPointer();
                var statePtr = this.thisPtr.add(16).readS32();
                counters.lastCurrentPtr = currentPtr.toString();
                send({
                    t: "movenext",
                    thisPtr: this.thisPtr.toString(),
                    state: statePtr,
                    returned: returnedTrue,
                    currentPtr: currentPtr.toString(),
                    ts: Date.now()
                });
            } catch (e) {
                send({ t: "movenext_error", err: e.message });
            }
        }
    });
}

installPickNextHook();

rpc.exports = {
    stats: function () { return counters; }
};
