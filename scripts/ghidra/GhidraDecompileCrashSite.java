// Ghidra headless script: decompile a small list of RVAs in GameAssembly.dll
// to investigate IL2CPP runtime crash sites. Outputs one .c file per address
// with surrounding context (3 functions before/after the target).
//
// Targets are hardcoded below. Output goes to data/decompiled_gameassembly/_crash_sites/.
//
// @category IL2CPP

import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileResults;
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.FunctionIterator;
import ghidra.program.model.listing.FunctionManager;

import java.io.*;
import java.util.*;

public class GhidraDecompileCrashSite extends GhidraScript {

    private static final String OUTPUT_DIR = "C:/Users/nicolasv/tacticus-tools/data/decompiled_gameassembly/_crash_sites";
    private static final int DECOMPILE_TIMEOUT_S = 300;

    // Crash sites to decompile, with surrounding context. Add more here as needed.
    private static final long[] TARGET_RVAS = {
        0x2560L,   // crash site: rbx ← r8 (3rd arg = 0x2c) → mov r11, [rbx] AVs
    };
    private static final int CONTEXT_FUNCS_BEFORE = 3;
    private static final int CONTEXT_FUNCS_AFTER  = 3;

    @Override
    protected void run() throws Exception {
        new File(OUTPUT_DIR).mkdirs();
        Address base = currentProgram.getImageBase();
        FunctionManager funcMgr = currentProgram.getFunctionManager();

        DecompInterface decomp = new DecompInterface();
        ghidra.app.decompiler.DecompileOptions opts = new ghidra.app.decompiler.DecompileOptions();
        opts.setMaxPayloadMBytes(256);
        decomp.setOptions(opts);
        decomp.openProgram(currentProgram);

        try {
            for (long rva : TARGET_RVAS) {
                Address target = base.add(rva);
                Function targetFn = funcMgr.getFunctionContaining(target);
                if (targetFn == null) {
                    println(String.format("RVA 0x%X: no function defined here", rva));
                    continue;
                }
                println(String.format("RVA 0x%X -> function %s @ %s",
                    rva, targetFn.getName(), targetFn.getEntryPoint()));

                // Collect target + context (functions immediately before/after).
                List<Function> ctx = new ArrayList<>();
                // Walk backward
                Function cur = targetFn;
                List<Function> before = new ArrayList<>();
                for (int i = 0; i < CONTEXT_FUNCS_BEFORE; i++) {
                    Function prev = funcMgr.getFunctionContaining(
                        cur.getEntryPoint().subtract(1));
                    if (prev == null || prev == cur) break;
                    before.add(0, prev);
                    cur = prev;
                }
                ctx.addAll(before);
                ctx.add(targetFn);
                // Walk forward
                cur = targetFn;
                for (int i = 0; i < CONTEXT_FUNCS_AFTER; i++) {
                    Address afterAddr = cur.getBody().getMaxAddress().add(1);
                    Function next = funcMgr.getFunctionContaining(afterAddr);
                    if (next == null || next == cur) break;
                    ctx.add(next);
                    cur = next;
                }

                StringBuilder buf = new StringBuilder(16384);
                buf.append(String.format(
                    "// Crash site decomp around RVA 0x%X\n"
                    + "// Target: %s @ %s\n"
                    + "// Context: %d before + target + %d after\n\n",
                    rva, targetFn.getName(), targetFn.getEntryPoint(),
                    before.size(), ctx.size() - before.size() - 1));

                for (Function f : ctx) {
                    long fnRva = f.getEntryPoint().subtract(base);
                    boolean isTarget = f == targetFn;
                    buf.append(String.format(
                        "// %s=== %s @ 0x%X (RVA) ===\n",
                        isTarget ? ">>> TARGET <<<\n// " : "",
                        f.getName(), fnRva));
                    try {
                        DecompileResults res = decomp.decompileFunction(
                            f, DECOMPILE_TIMEOUT_S, monitor);
                        if (res != null && res.getDecompiledFunction() != null) {
                            buf.append(res.getDecompiledFunction().getC());
                        } else {
                            buf.append("// TIMEOUT/NULL\n");
                        }
                    } catch (Exception e) {
                        buf.append("// ERROR: ").append(e.getMessage()).append("\n");
                    }
                    buf.append("\n");
                }

                File out = new File(OUTPUT_DIR,
                    String.format("rva_%x_%s.c", rva, targetFn.getName()));
                try (FileWriter fw = new FileWriter(out, false)) {
                    fw.write(buf.toString());
                }
                println("Wrote " + out.getAbsolutePath());
            }
        } finally {
            decomp.dispose();
        }
    }
}
