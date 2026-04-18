// Phase A POC: prove that gc-rooting via ArrayList keeps IL2CPP objects alive.
//
// Full interactive shape: send() for progress + rpc.exports for re-runnable actions.
// Inject once, drive from curl with:
//   curl -X POST http://127.0.0.1:8765/api/scripts/:id/rpc \
//     -d '{"method":"run","args":[]}'   — run the full POC
//   curl ... -d '{"method":"pressure"}' — force GC pressure
//   curl ... -d '{"method":"verify"}'   — re-check alive objects
//   curl ... -d '{"method":"cleanup"}'  — clear root + cleanup

send({ t: "hook_ready", name: "phase-a-gc-root-poc", version: 1 });

var state = {
    createdPtrs: [],
    objectKlass: null,
    initialized: false
};

function ensureInit() {
    if (state.initialized) return;
    if (!gcRoot.init()) throw new Error("gcRoot.init failed");
    state.objectKlass = findClass("mscorlib.dll", "System", "Object");
    if (!state.objectKlass) throw new Error("System.Object class not found");
    state.initialized = true;
    send({ t: "progress", msg: "Initialized: gcRoot ArrayList + System.Object class" });
}

function rssKb() {
    try {
        var fd = new File("/proc/self/status", "r");
        var content = "";
        var line;
        while ((line = fd.readLine()) !== "") {
            content += line;
            if (content.indexOf("VmRSS:") !== -1 && content.indexOf("\n", content.indexOf("VmRSS:")) !== -1) break;
        }
        fd.close();
        var m = content.match(/VmRSS:\s+(\d+)\s*kB/);
        return m ? parseInt(m[1], 10) : -1;
    } catch (e) { return -1; }
}

function createAndRoot(n) {
    ensureInit();
    state.createdPtrs = [];
    for (var i = 0; i < n; i++) {
        var obj = il2cpp_object_new(state.objectKlass);
        if (obj.isNull()) throw new Error("il2cpp_object_new returned null at i=" + i);
        state.createdPtrs.push(obj);
        gcRoot.add(obj);
    }
    return { created: n, rootCount: gcRoot.count(), rssKb: rssKb() };
}

function pressureGc() {
    ensureInit();
    var allocated = 0;
    // ~10000 throwaway objects → create GC pressure indirectly (safer than GC.Collect)
    for (var i = 0; i < 10000; i++) {
        var obj = il2cpp_object_new(state.objectKlass);
        if (!obj.isNull()) allocated++;
    }
    return { allocated: allocated, rssKb: rssKb() };
}

function verifyAlive() {
    var alive = 0, dead = 0;
    for (var i = 0; i < state.createdPtrs.length; i++) {
        try {
            var klassPtr = state.createdPtrs[i].readPointer();
            if (klassPtr.equals(state.objectKlass)) alive++;
            else dead++;
        } catch (e) { dead++; }
    }
    return { alive: alive, dead: dead, expected: state.createdPtrs.length };
}

function cleanup() {
    ensureInit();
    gcRoot.clear();
    state.createdPtrs = [];
    return { rootCount: gcRoot.count(), rssKb: rssKb() };
}

function runFull() {
    var report = [];
    function step(name, fn) {
        var t0 = Date.now();
        var rssBefore = rssKb();
        var extra;
        try { extra = fn() || {}; }
        catch (e) { report.push({ name: name, error: e.message }); return false; }
        var entry = { name: name, elapsed_ms: Date.now() - t0, rss_before_kb: rssBefore, rss_after_kb: rssKb() };
        for (var k in extra) entry[k] = extra[k];
        report.push(entry);
        send({ t: "progress", msg: "  [ok] " + name + " (" + entry.elapsed_ms + " ms, rss delta " + (entry.rss_after_kb - entry.rss_before_kb) + " kB)" });
        return true;
    }

    step("0_init", function() { ensureInit(); return {}; });
    step("1_create_100_rooted", function() { return createAndRoot(100); });
    step("2_gc_pressure", function() { return pressureGc(); });
    step("3_verify_alive", function() { return verifyAlive(); });
    step("4_cleanup", function() { return cleanup(); });
    step("5_gc_pressure_after_cleanup", function() { return pressureGc(); });
    step("6_final", function() { return { rootCount: gcRoot.count(), rssKb: rssKb() }; });

    send({ t: "phase_a_report", report: report });
    return report;
}

rpc.exports = {
    run: runFull,
    init: function() { ensureInit(); return { initialized: true, rssKb: rssKb() }; },
    createAndRoot: function(n) { return createAndRoot(n || 100); },
    pressure: pressureGc,
    verify: verifyAlive,
    cleanup: cleanup,
    state: function() { return { count: state.createdPtrs.length, rootCount: gcRoot.count(), rssKb: rssKb() }; }
};

send({ t: "progress", msg: "Phase A POC ready. RPC: run, init, createAndRoot(n), pressure, verify, cleanup, state" });