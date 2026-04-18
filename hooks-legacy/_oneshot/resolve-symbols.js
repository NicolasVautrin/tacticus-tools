// Oneshot: resolve FUN_ and thunk_FUN_ addresses via DebugSymbol
// requires: _utils/il2cpp-helpers
//
// No memory reads — just DebugSymbol.fromAddress, safe.

var GHIDRA_BASE = 0x100000;

function log(msg) { send({t: "log", msg: msg}); }

recv("addrs", function(msg) {
    var funs = msg.payload;
    log("Resolving " + funs.length + " FUN_/thunk addresses...");

    var results = {};
    var ok = 0;
    for (var i = 0; i < funs.length; i++) {
        var raw = funs[i];
        var hex = raw.replace('thunk_FUN_', '').replace('FUN_', '');
        var ghidraAddr = parseInt(hex, 16);
        if (ghidraAddr <= GHIDRA_BASE) continue;
        var rva = ghidraAddr - GHIDRA_BASE;
        try {
            var addr = il2cppBase.add(rva);
            var sym = DebugSymbol.fromAddress(addr);
            if (sym && sym.name && sym.name.indexOf('0x') === -1) {
                results[raw] = sym.name;
                ok++;
            }
        } catch(e) {}
    }

    log("Resolved: " + ok + "/" + funs.length);
    send({t: "resolved_symbols", count: ok, data: JSON.stringify(results)});
});

log("resolve-symbols: ready");
send({t: "ready"});