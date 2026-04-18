// Diagnostic: read the actual values at a few unresolved PTR_DAT addresses, and try
// to identify what kind of runtime object they point to (Il2CppClass, Il2CppType, null...).

var il2cpp = Process.findModuleByName("libil2cpp.so");
var base = il2cpp.base;

var RVAS = [0x4779b78, 0x47fca70, 0x47fca78, 0x4711520 /* known-class for comparison */];

for (var i = 0; i < RVAS.length; i++) {
    var rva = RVAS[i];
    var cellAddr = base.add(rva);
    var val;
    try {
        val = cellAddr.readPointer();
    } catch(e) {
        send({t: "diag", rva: rva.toString(16), err: "unreadable: " + e.message});
        continue;
    }
    // Dump the 32 bytes at the value it points to (if readable)
    var preview = "";
    try {
        if (!val.isNull()) {
            preview = hexdump(val, {length: 32, ansi: false});
        }
    } catch(e) { preview = "(unreadable " + e.message + ")"; }
    // Is the value inside libil2cpp.so?
    var insideModule = (!val.isNull() && val.compare(base) >= 0 && val.compare(base.add(il2cpp.size)) < 0);
    send({
        t: "diag",
        rva: rva.toString(16),
        cell_addr: cellAddr.toString(),
        value_at_cell: val.toString(),
        value_inside_module: insideModule,
        preview_bytes_at_value: preview
    });
}
send({t: "progress", msg: "Done."});
