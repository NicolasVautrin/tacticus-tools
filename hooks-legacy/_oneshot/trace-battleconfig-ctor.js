// oneshot: Trace all call sites of BattleConfiguration..ctor()
// Hooks the constructor and logs a backtrace each time it's called.
// The stack offsets are sent as numbers — the backend resolves them via symbols.json.
//
// Usage: inject via POST /api/scripts/run (include il2cpp-helpers.js first).

var ctorRva = 0x2BEE5A8;
var ctorAddr = il2cppBase.add(ctorRva);

var callCount = 0;

Interceptor.attach(ctorAddr, {
    onEnter: function (args) {
        callCount++;
        var stack = getStack(this.context);
        send({
            t: "trace",
            target: "BattleConfiguration..ctor",
            call: callCount,
            thisPtr: args[0].toString(),
            stack: stack
        });
    }
});

console.log("[+] Tracing BattleConfiguration..ctor at RVA 0x" + ctorRva.toString(16));