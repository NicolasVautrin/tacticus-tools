// Ghidra headless script: decompile virtual method overrides (CreateBehaviour, CreateTrigger, ExecuteBehaviour)
// Reads targets from data/virtual_methods_targets.json, appends to existing .c files in data/decompiled_tacticus/
//
// @category IL2CPP

import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileResults;
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.FunctionManager;
import ghidra.program.model.symbol.SourceType;

import java.io.*;
import java.util.*;

public class GhidraDecompileVirtualMethods extends GhidraScript {

    private static final String TARGETS_FILE = "C:/Users/nicolasv/tacticus-tools/data/virtual_methods_targets.json";
    private static final String OUTPUT_DIR = "C:/Users/nicolasv/tacticus-tools/data/decompiled_tacticus";

    @Override
    protected void run() throws Exception {
        String jsonStr = new String(java.nio.file.Files.readAllBytes(java.nio.file.Paths.get(TARGETS_FILE)));
        Map<String, Long> targets = parseTargets(jsonStr);
        println("Loaded " + targets.size() + " virtual method targets");

        new File(OUTPUT_DIR).mkdirs();

        Address base = currentProgram.getImageBase();
        FunctionManager funcMgr = currentProgram.getFunctionManager();

        DecompInterface decomp = new DecompInterface();
        decomp.openProgram(currentProgram);

        // Group by class for organized output
        Map<String, List<String>> classMethods = new LinkedHashMap<>();

        int ok = 0, fail = 0;
        long startTime = System.currentTimeMillis();
        for (Map.Entry<String, Long> entry : targets.entrySet()) {
            String name = entry.getKey();
            long rva = entry.getValue();
            Address addr = base.add(rva);

            Function func = funcMgr.getFunctionAt(addr);
            if (func == null) {
                try {
                    func = createFunction(addr, name);
                } catch (Exception e) { /* ignore */ }
            }
            if (func == null) {
                fail++;
                continue;
            }

            try {
                func.setName(name, SourceType.USER_DEFINED);
            } catch (Exception e) { /* duplicate name */ }

            DecompileResults res = decomp.decompileFunction(func, 120, monitor);
            if (res != null && res.getDecompiledFunction() != null) {
                String code = res.getDecompiledFunction().getC();

                String[] segments = name.split("\\.");
                String className;
                if (segments.length >= 2) {
                    StringBuilder sb = new StringBuilder();
                    for (int si = 0; si < segments.length - 1; si++) {
                        if (si > 0) sb.append('.');
                        sb.append(segments[si]);
                    }
                    className = sb.toString();
                } else {
                    className = "misc";
                }

                classMethods.computeIfAbsent(className, k -> new ArrayList<>())
                    .add(String.format("// === %s (RVA: 0x%X) ===\n%s\n", name, rva, code));
                ok++;
            } else {
                fail++;
            }

            int total = ok + fail;
            if (total % 100 == 0) {
                long elapsed = (System.currentTimeMillis() - startTime) / 1000;
                double pct = 100.0 * total / targets.size();
                println(String.format("Progress: %d/%d (%.1f%%) — %d ok, %d fail — %ds elapsed",
                    total, targets.size(), pct, ok, fail, elapsed));
            }
        }

        decomp.dispose();

        // APPEND to existing class files (don't overwrite)
        int filesWritten = 0;
        for (Map.Entry<String, List<String>> entry : classMethods.entrySet()) {
            String className = entry.getKey();
            String[] parts = className.split("\\.");
            StringBuilder pathBuilder = new StringBuilder();
            for (int pi = 0; pi < parts.length - 1; pi++) {
                if (pi > 0) pathBuilder.append('/');
                pathBuilder.append(parts[pi]);
            }
            String dir = pathBuilder.toString();
            String filename = parts[parts.length - 1] + ".c";
            String relativePath = dir.isEmpty() ? filename : dir + "/" + filename;
            File outFile = new File(OUTPUT_DIR, relativePath);
            outFile.getParentFile().mkdirs();

            // APPEND mode — add virtual methods to existing file
            try (PrintWriter out = new PrintWriter(new FileWriter(outFile, true))) {
                out.println();
                out.println("// ========== VIRTUAL METHOD OVERRIDES ==========");
                out.println("// Methods: " + entry.getValue().size());
                out.println();
                for (String code : entry.getValue()) {
                    out.println(code);
                }
            }
            filesWritten++;
        }

        long totalTime = (System.currentTimeMillis() - startTime) / 1000;
        println(String.format("\nDone: %d decompiled, %d failed, %d files updated in %s (%ds total)",
            ok, fail, filesWritten, OUTPUT_DIR, totalTime));
    }

    private Map<String, Long> parseTargets(String json) {
        Map<String, Long> result = new LinkedHashMap<>();
        json = json.trim();
        if (json.startsWith("{")) json = json.substring(1);
        if (json.endsWith("}")) json = json.substring(0, json.length() - 1);

        String[] pairs = json.split(",");
        for (String pair : pairs) {
            int colonIdx = pair.indexOf(':');
            if (colonIdx < 0) continue;
            String key = pair.substring(0, colonIdx).trim();
            String val = pair.substring(colonIdx + 1).trim();
            if (key.startsWith("\"")) key = key.substring(1);
            if (key.endsWith("\"")) key = key.substring(0, key.length() - 1);
            try {
                result.put(key, Long.parseLong(val.trim()));
            } catch (NumberFormatException e) { /* skip */ }
        }
        return result;
    }
}
