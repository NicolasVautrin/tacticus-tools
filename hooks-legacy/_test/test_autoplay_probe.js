// Probe: check il2cpp_object_new + test recv/post pipeline
var il2cpp = Process.findModuleByName("libil2cpp.so");

// Check if il2cpp_object_new exists
var objectNewPtr = il2cpp.findExportByName("il2cpp_object_new");
send({t: "probe", il2cpp_object_new: objectNewPtr ? objectNewPtr.toString() : null});

// Also check il2cpp_runtime_invoke (alternative for calling constructors)
var runtimeInvokePtr = il2cpp.findExportByName("il2cpp_runtime_invoke");
send({t: "probe", il2cpp_runtime_invoke: runtimeInvokePtr ? runtimeInvokePtr.toString() : null});

// Test recv — listen for messages from backend
recv("ping", function onPing(msg) {
    send({t: "pong", received: msg});
    recv("ping", onPing);
});

send({t: "ready", msg: "Probe ready. Send a ping via POST /api/scripts/{id}/message"});
