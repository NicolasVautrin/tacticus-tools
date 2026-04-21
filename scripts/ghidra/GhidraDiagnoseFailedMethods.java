// Ghidra diagnostic: for each RVA in the failed-decompile list, print the function's
// body size, the distance to the next known method, and flag mismatches.
//
// Usage: analyzeHeadless ... -postScript GhidraDiagnoseFailedMethods.java
//
// @category IL2CPP

import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.address.AddressSetView;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.FunctionManager;

import java.io.*;
import java.util.*;

public class GhidraDiagnoseFailedMethods extends GhidraScript {

    private static final String TARGETS_FILE = "C:/Users/nicolasv/tacticus-tools/data/all_battlelogic_targets.tsv";
    private static final String FAILED_RVAS_FILE = "C:/Users/nicolasv/tacticus-tools/data/failed_rvas.txt";
    private static final String OUT_FILE = "C:/Users/nicolasv/tacticus-tools/data/failed_bounds.csv";

    @Override
    protected void run() throws Exception {
        // 1) Load all known RVAs (sorted) to compute "next method" gap
        List<long[]> rvas = new ArrayList<>(); // [rva, 0]
        try (BufferedReader br = new BufferedReader(new FileReader(TARGETS_FILE))) {
            String line;
            while ((line = br.readLine()) != null) {
                String[] parts = line.split("\t", -1);
                if (parts.length < 3) continue;
                try {
                    long rva = Long.parseLong(parts[2], 16);
                    rvas.add(new long[]{rva});
                } catch (NumberFormatException e) {}
            }
        }
        rvas.sort(Comparator.comparingLong(r -> r[0]));

        // 2) Load failed RVAs
        Set<Long> failed = new HashSet<>();
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
        println("Loaded " + rvas.size() + " total RVAs, " + failed.size() + " failed");

        Address base = currentProgram.getImageBase();
        FunctionManager funcMgr = currentProgram.getFunctionManager();

        int ok_tight = 0, oversized = 0, no_function = 0;
        try (PrintWriter out = new PrintWriter(new FileWriter(OUT_FILE))) {
            out.println("rva,body_size,next_gap,oversized,func_name");
            for (int i = 0; i < rvas.size(); i++) {
                long rva = rvas.get(i)[0];
                if (!failed.contains(rva)) continue;
                long nextRva = (i + 1 < rvas.size()) ? rvas.get(i + 1)[0] : rva + 0x10000;
                long nextGap = nextRva - rva;
                Address addr = base.add(rva);
                Function f = funcMgr.getFunctionAt(addr);
                if (f == null) {
                    out.println(String.format("0x%X,,%d,,NO_FUNCTION", rva, nextGap));
                    no_function++;
                    continue;
                }
                AddressSetView body = f.getBody();
                long bodySize = body.getNumAddresses();
                boolean isOversized = bodySize > nextGap * 2;
                if (isOversized) oversized++;
                else ok_tight++;
                out.println(String.format("0x%X,%d,%d,%s,%s", rva, bodySize, nextGap, isOversized, f.getName()));
            }
        }
        println(String.format("Results: %d tight-bounds, %d oversized (> 2x gap), %d no_function",
            ok_tight, oversized, no_function));
        println("Output: " + OUT_FILE);
    }
}
