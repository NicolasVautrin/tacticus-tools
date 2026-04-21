// Ghidra headless script: parallel batch decompile BattleLogicAssembly methods, grouped by
// top-level class (nested classes + coroutines go into their outer class's .c file).
//
// Input: data/all_battlelogic_targets.tsv — pre-computed by gen_battlelogic_targets.py.
//   Each line: top_class_fs_path \t method_full_name \t rva_hex
// Output: data/decompiled_tacticus/<top_class_fs_path>.c — one file per top-level class.
//
// Parallelism: 16 threads, work-stealing queue over classes. Each thread decompiles all
// methods of a class sequentially into a local StringBuilder, then writes the file
// atomically. Memory stays bounded (~1 class per thread).
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
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicInteger;

public class GhidraDecompileBattleLogicParallel extends GhidraScript {

    private static final String TARGETS_FILE = "C:/Users/nicolasv/tacticus-tools/data/all_battlelogic_targets.tsv";
    private static final String OUTPUT_DIR   = "C:/Users/nicolasv/tacticus-tools/data/decompiled_tacticus";
    private static final int THREAD_COUNT = 16;
    private static final int DECOMPILE_TIMEOUT_S = 120;          // void* sigs converge fast on most, a few op_X bodies need up to 100s

    static class Method {
        final String name;
        final long rva;
        Method(String name, long rva) { this.name = name; this.rva = rva; }
    }

    static class ClassJob {
        final String fsPath;            // e.g. "IdunBattle/AI/DefaultPlayerStrategy"
        final List<Method> methods = new ArrayList<>();
        ClassJob(String fsPath) { this.fsPath = fsPath; }
    }

    @Override
    protected void run() throws Exception {
        // --- Load TSV and group by top class ---
        Map<String, ClassJob> byClass = new LinkedHashMap<>();
        int totalMethods = 0;
        try (BufferedReader br = new BufferedReader(new FileReader(TARGETS_FILE), 1 << 20)) {
            String line;
            while ((line = br.readLine()) != null) {
                String[] parts = line.split("\t", -1);
                if (parts.length < 3) continue;
                String fsPath = parts[0];
                String name = parts[1];
                long rva;
                try { rva = Long.parseLong(parts[2], 16); } catch (NumberFormatException e) { continue; }
                byClass.computeIfAbsent(fsPath, ClassJob::new).methods.add(new Method(name, rva));
                totalMethods++;
            }
        }
        List<ClassJob> jobs = new ArrayList<>(byClass.values());
        println("Loaded " + totalMethods + " methods across " + jobs.size() + " top-level classes");
        println("Using " + THREAD_COUNT + " threads, timeout " + DECOMPILE_TIMEOUT_S + "s/method");

        new File(OUTPUT_DIR).mkdirs();

        Address base = currentProgram.getImageBase();
        FunctionManager funcMgr = currentProgram.getFunctionManager();
        final AtomicInteger classCursor = new AtomicInteger(0);
        final AtomicInteger methodsOk = new AtomicInteger(0);
        final AtomicInteger methodsFail = new AtomicInteger(0);
        final AtomicInteger methodsTotal = new AtomicInteger(0);
        final AtomicInteger classesDone = new AtomicInteger(0);
        final long startTime = System.currentTimeMillis();
        final int jobsSize = jobs.size();
        final int targetsSize = totalMethods;

        Thread reporter = new Thread(() -> {
            while (true) {
                try { Thread.sleep(10000); } catch (InterruptedException e) { return; }
                long elapsed = (System.currentTimeMillis() - startTime) / 1000;
                if (elapsed < 1) continue;
                int t = methodsTotal.get();
                double mPct = 100.0 * t / targetsSize;
                double cPct = 100.0 * classesDone.get() / jobsSize;
                double rate = t / (double) elapsed;
                long eta = (long) ((targetsSize - t) / Math.max(1, rate));
                println(String.format("Methods: %d/%d (%.1f%%)  Classes: %d/%d (%.1f%%)  ok=%d fail=%d  %ds  %.0f m/s  ETA %ds",
                    t, targetsSize, mPct, classesDone.get(), jobsSize, cPct, methodsOk.get(), methodsFail.get(), elapsed, rate, eta));
            }
        });
        reporter.setDaemon(true);
        reporter.start();

        ExecutorService pool = Executors.newFixedThreadPool(THREAD_COUNT);
        List<Future<?>> futures = new ArrayList<>();

        for (int t = 0; t < THREAD_COUNT; t++) {
            futures.add(pool.submit(() -> {
                DecompInterface decomp = new DecompInterface();
                ghidra.app.decompiler.DecompileOptions opts = new ghidra.app.decompiler.DecompileOptions();
                // 128MB/thread × 16 threads = 2GB max payload. Was 512MB when we needed it to
                // recover buffer-overflow timeouts in typed mode; void* mode produces smaller output.
                opts.setMaxPayloadMBytes(128);
                decomp.setOptions(opts);
                decomp.openProgram(currentProgram);

                try {
                    while (true) {
                        if (monitor.isCancelled()) break;
                        int idx = classCursor.getAndIncrement();
                        if (idx >= jobsSize) break;
                        ClassJob job = jobs.get(idx);

                        StringBuilder buf = new StringBuilder(8192);
                        buf.append("// Decompiled top-level class: ").append(job.fsPath.replace('/', '.')).append('\n');
                        buf.append("// Methods: ").append(job.methods.size()).append("\n\n");

                        int localOk = 0, localFail = 0;
                        for (Method m : job.methods) {
                            if (monitor.isCancelled()) break;
                            Address addr = base.add(m.rva);
                            Function func = funcMgr.getFunctionAt(addr);
                            if (func == null) {
                                buf.append(String.format("// === %s (RVA: 0x%X) === NO FUNCTION AT ADDRESS\n\n", m.name, m.rva));
                                localFail++;
                            } else {
                                try {
                                    DecompileResults res = decomp.decompileFunction(func, DECOMPILE_TIMEOUT_S, monitor);
                                    if (res != null && res.getDecompiledFunction() != null) {
                                        buf.append(String.format("// === %s (RVA: 0x%X) ===\n%s\n", m.name, m.rva, res.getDecompiledFunction().getC()));
                                        localOk++;
                                    } else {
                                        buf.append(String.format("// === %s (RVA: 0x%X) === TIMEOUT/NULL\n\n", m.name, m.rva));
                                        localFail++;
                                    }
                                } catch (Exception e) {
                                    buf.append(String.format("// === %s (RVA: 0x%X) === ERROR: %s\n\n", m.name, m.rva, e.getMessage()));
                                    localFail++;
                                }
                            }
                            methodsTotal.incrementAndGet();
                        }

                        try {
                            writeClassFile(job.fsPath, buf.toString());
                            methodsOk.addAndGet(localOk);
                            methodsFail.addAndGet(localFail);
                            classesDone.incrementAndGet();
                        } catch (IOException ioe) {
                            println("Write failed for " + job.fsPath + ": " + ioe.getMessage());
                        }
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

        long totalTime = (System.currentTimeMillis() - startTime) / 1000;
        println(String.format("Done: %d classes written, %d ok, %d failed (%ds total)",
            classesDone.get(), methodsOk.get(), methodsFail.get(), totalTime));
    }

    private void writeClassFile(String fsPath, String content) throws IOException {
        File outFile = new File(OUTPUT_DIR, fsPath + ".c");
        outFile.getParentFile().mkdirs();
        IOException last = null;
        for (int attempt = 0; attempt < 3; attempt++) {
            try (FileWriter fw = new FileWriter(outFile, false)) {
                fw.write(content);
                return;
            } catch (IOException e) {
                last = e;
                try { Thread.sleep(50L * (attempt + 1)); } catch (InterruptedException ignore) {}
            }
        }
        throw last;
    }
}
