// Ghidra diagnostic: pick a few failed methods and try decompiling them with different
// strategies (signature, simplification style) to see which recovers bodies.
//
// @category IL2CPP

import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileResults;
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.FunctionManager;

import java.io.*;
import java.util.*;

public class GhidraInvestigateFailures extends GhidraScript {

    private static final String FAILED_RVAS_FILE = "C:/Users/nicolasv/tacticus-tools/data/failed_rvas.txt";

    @Override
    protected void run() throws Exception {
        // Load a sample of failed RVAs
        List<Long> failed = new ArrayList<>();
        try (BufferedReader br = new BufferedReader(new FileReader(FAILED_RVAS_FILE))) {
            String line;
            while ((line = br.readLine()) != null) {
                line = line.trim();
                if (line.isEmpty()) continue;
                try {
                    failed.add(Long.parseLong(line.replace("0x", ""), 16));
                } catch (NumberFormatException e) {}
            }
        }

        Address base = currentProgram.getImageBase();
        FunctionManager funcMgr = currentProgram.getFunctionManager();

        // Try 10 samples with different strategies
        List<Long> samples = failed.subList(0, Math.min(10, failed.size()));

        String[] styles = {"decompile", "paramid", "register", "normalize", "firstpass"};
        int timeout = 60;

        for (long rva : samples) {
            Address addr = base.add(rva);
            Function f = funcMgr.getFunctionAt(addr);
            if (f == null) { println(String.format("0x%X: no function", rva)); continue; }
            println(String.format("\n=== 0x%X  %s  (body=%d bytes) ===", rva, f.getName(), f.getBody().getNumAddresses()));

            for (String style : styles) {
                DecompInterface decomp = new DecompInterface();
                try {
                    decomp.setSimplificationStyle(style);
                    boolean opened = decomp.openProgram(currentProgram);
                    if (!opened) { println("  " + style + ": openProgram failed"); continue; }
                    long t0 = System.currentTimeMillis();
                    DecompileResults res = decomp.decompileFunction(f, timeout, monitor);
                    long dt = System.currentTimeMillis() - t0;
                    if (res != null && res.getDecompiledFunction() != null) {
                        String c = res.getDecompiledFunction().getC();
                        int lines = c.split("\n").length;
                        println(String.format("  %s: OK in %dms (%d lines)", style, dt, lines));
                    } else {
                        String err = res != null ? res.getErrorMessage() : "null result";
                        println(String.format("  %s: FAIL in %dms (%s)", style, dt, err));
                    }
                } finally {
                    decomp.dispose();
                }
            }
        }
    }
}
