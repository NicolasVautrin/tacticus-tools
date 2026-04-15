// Ghidra headless script: decompile AI coroutine MoveNext methods
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

public class GhidraDecompileAICore extends GhidraScript {

    private static final String TARGETS_FILE = "C:/Users/nicolasv/tacticus-tools/data/ai_coroutine_targets.json";
    private static final String OUTPUT_DIR = "C:/Users/nicolasv/tacticus-tools/data/decompiled_tacticus";

    @Override
    protected void run() throws Exception {
        String jsonStr = new String(java.nio.file.Files.readAllBytes(java.nio.file.Paths.get(TARGETS_FILE)));
        Map<String, Long> targets = parseTargets(jsonStr);
        println("Loaded " + targets.size() + " coroutine targets");

        Address base = currentProgram.getImageBase();
        FunctionManager funcMgr = currentProgram.getFunctionManager();
        DecompInterface decomp = new DecompInterface();
        decomp.openProgram(currentProgram);

        Map<String, List<String>> classMethods = new LinkedHashMap<>();
        int ok = 0, fail = 0;

        for (Map.Entry<String, Long> entry : targets.entrySet()) {
            String name = entry.getKey();
            long rva = entry.getValue();
            Address addr = base.add(rva);

            Function func = funcMgr.getFunctionAt(addr);
            if (func == null) {
                try { func = createFunction(addr, name); } catch (Exception e) {}
            }
            if (func == null) { fail++; continue; }
            try { func.setName(name, SourceType.USER_DEFINED); } catch (Exception e) {}

            DecompileResults res = decomp.decompileFunction(func, 120, monitor);
            if (res != null && res.getDecompiledFunction() != null) {
                String code = res.getDecompiledFunction().getC();
                String[] parts = name.split("\\.");
                String className = parts.length >= 2 ?
                    name.substring(0, name.lastIndexOf('.')) : "misc";
                classMethods.computeIfAbsent(className, k -> new ArrayList<>())
                    .add(String.format("// === %s (RVA: 0x%X) ===\n%s\n", name, rva, code));
                ok++;
            } else {
                fail++;
            }
        }

        decomp.dispose();

        // Write files
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
            // Append to existing file if present
            try (PrintWriter out = new PrintWriter(new FileWriter(outFile, true))) {
                out.println("\n// ---- Coroutine state machines ----\n");
                for (String code : entry.getValue()) {
                    out.println(code);
                }
            }
            filesWritten++;
        }

        println("Done: " + ok + " decompiled, " + fail + " failed, " + filesWritten + " files");
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
            String key = pair.substring(0, colonIdx).trim().replace("\"", "");
            String val = pair.substring(colonIdx + 1).trim();
            try { result.put(key, Long.parseLong(val.trim())); } catch (NumberFormatException e) {}
        }
        return result;
    }
}
