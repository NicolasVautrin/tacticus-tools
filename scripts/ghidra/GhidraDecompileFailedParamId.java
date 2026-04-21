// Ghidra headless script: 2nd-pass decompile of methods that failed (TIMEOUT/NULL) in
// the main run, using the "paramid" simplification style. Less aggressive than the
// default "decompile" (no final CFG structuring pass that diverges on coroutines /
// complex switches) but retains typed params + named calls + clean identifier names.
//
// Input: data/failed_targets.tsv (produced by scripts/python/extract_failed_targets.py)
//   Each line: top_class_fs_path \t method_full_name \t rva_hex
// Output: appends `// === ... === [PARAMID RECOVERY] ...` blocks to the existing
//   top-class files in data/decompiled_tacticus/, and marks the RVA as recovered by
//   replacing the original `TIMEOUT/NULL` line inline.
//
// @category IL2CPP

import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileOptions;
import ghidra.app.decompiler.DecompileResults;
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.FunctionManager;

import java.io.*;
import java.nio.file.*;
import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicInteger;

public class GhidraDecompileFailedParamId extends GhidraScript {

    private static final String TARGETS_FILE = "C:/Users/nicolasv/tacticus-tools/data/failed_targets.tsv";
    private static final String OUTPUT_DIR   = "C:/Users/nicolasv/tacticus-tools/data/decompiled_tacticus";
    private static final int THREAD_COUNT = 16;
    private static final int TIMEOUT_S = 60; // generous — paramid converges further if given time

    static class Target {
        final String fsPath;
        final String name;
        final long rva;
        Target(String fsPath, String name, long rva) { this.fsPath = fsPath; this.name = name; this.rva = rva; }
    }

    @Override
    protected void run() throws Exception {
        List<Target> targets = new ArrayList<>();
        try (BufferedReader br = new BufferedReader(new FileReader(TARGETS_FILE), 1 << 16)) {
            String line;
            while ((line = br.readLine()) != null) {
                String[] p = line.split("\t", -1);
                if (p.length < 3) continue;
                try {
                    targets.add(new Target(p[0], p[1], Long.parseLong(p[2], 16)));
                } catch (NumberFormatException e) {}
            }
        }
        println("Loaded " + targets.size() + " failed targets to retry with paramid (timeout " + TIMEOUT_S + "s)");

        Address base = currentProgram.getImageBase();
        FunctionManager funcMgr = currentProgram.getFunctionManager();

        // Group recoveries by fsPath so each class-file is appended once
        Map<String, StringBuilder> recoveriesByFile = new ConcurrentHashMap<>();

        final AtomicInteger ok = new AtomicInteger(0);
        final AtomicInteger fail = new AtomicInteger(0);
        final AtomicInteger done = new AtomicInteger(0);
        final int total = targets.size();
        final long startTime = System.currentTimeMillis();
        final AtomicInteger cursor = new AtomicInteger(0);

        Thread reporter = new Thread(() -> {
            while (true) {
                try { Thread.sleep(10000); } catch (InterruptedException e) { return; }
                long elapsed = (System.currentTimeMillis() - startTime) / 1000;
                if (elapsed < 1) continue;
                int d = done.get();
                double rate = d / (double) elapsed;
                long eta = (long) ((total - d) / Math.max(1, rate));
                println(String.format("Paramid: %d/%d  ok=%d fail=%d  %ds  %.1f m/s  ETA %ds",
                    d, total, ok.get(), fail.get(), elapsed, rate, eta));
            }
        });
        reporter.setDaemon(true);
        reporter.start();

        ExecutorService pool = Executors.newFixedThreadPool(THREAD_COUNT);
        List<Future<?>> futures = new ArrayList<>();

        for (int t = 0; t < THREAD_COUNT; t++) {
            futures.add(pool.submit(() -> {
                DecompInterface decomp = new DecompInterface();
                DecompileOptions opts = new DecompileOptions();
                opts.setMaxPayloadMBytes(512);
                decomp.setOptions(opts);
                decomp.setSimplificationStyle("paramid");
                decomp.openProgram(currentProgram);

                try {
                    while (true) {
                        if (monitor.isCancelled()) break;
                        int idx = cursor.getAndIncrement();
                        if (idx >= total) break;
                        Target tg = targets.get(idx);
                        Address addr = base.add(tg.rva);
                        Function func = funcMgr.getFunctionAt(addr);
                        StringBuilder per = new StringBuilder();
                        boolean recovered = false;
                        if (func != null) {
                            try {
                                DecompileResults res = decomp.decompileFunction(func, TIMEOUT_S, monitor);
                                if (res != null && res.getDecompiledFunction() != null) {
                                    per.append(String.format("// === %s (RVA: 0x%X) === [PARAMID RECOVERY]\n%s\n",
                                        tg.name, tg.rva, res.getDecompiledFunction().getC()));
                                    recovered = true;
                                }
                            } catch (Exception e) {
                                // fall through
                            }
                        }
                        if (recovered) {
                            recoveriesByFile.computeIfAbsent(tg.fsPath, k -> new StringBuilder())
                                .append(per);
                            ok.incrementAndGet();
                        } else {
                            fail.incrementAndGet();
                        }
                        done.incrementAndGet();
                    }
                } finally {
                    decomp.dispose();
                }
            }));
        }

        for (Future<?> f : futures) {
            try { f.get(); } catch (Exception e) { println("Worker error: " + e.getMessage()); }
        }
        pool.shutdown();
        reporter.interrupt();

        // Append recoveries per file (single-threaded to keep FS writes safe)
        int filesPatched = 0;
        for (Map.Entry<String, StringBuilder> e : recoveriesByFile.entrySet()) {
            File outFile = new File(OUTPUT_DIR, e.getKey() + ".c");
            outFile.getParentFile().mkdirs();
            try (FileWriter fw = new FileWriter(outFile, /* append */ true)) {
                fw.write("\n// ---- PARAMID recoveries ----\n");
                fw.write(e.getValue().toString());
            } catch (IOException ioe) {
                println("Append failed for " + outFile + ": " + ioe.getMessage());
            }
            filesPatched++;
        }

        long totalTime = (System.currentTimeMillis() - startTime) / 1000;
        println(String.format("Paramid done: %d ok / %d fail / %d files patched (%ds)",
            ok.get(), fail.get(), filesPatched, totalTime));
    }
}
