// Ghidra headless script: rename functions from enriched .cs sources
// Reads RVA annotations from decompiled sources and renames functions in Ghidra.
// Usage: analyzeHeadless ... -postScript GhidraRename.java
//
// @category IL2CPP

import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.FunctionManager;
import ghidra.program.model.symbol.SourceType;

import java.io.*;
import java.util.*;
import java.util.regex.*;

public class GhidraRename extends GhidraScript {

    private static final String SOURCES_DIR = "C:/Users/nicolasv/tacticus-tools/sources";
    private static final Pattern RVA_PATTERN = Pattern.compile("//\\s*RVA:\\s*0x([0-9A-Fa-f]+)");
    private static final Pattern METHOD_PATTERN = Pattern.compile(
        "(?:public|private|protected|internal|static|\\s)+\\S+\\s+(\\S+)\\s*\\(");

    @Override
    protected void run() throws Exception {
        Address base = currentProgram.getImageBase();
        FunctionManager funcMgr = currentProgram.getFunctionManager();

        // Collect RVAs from enriched sources
        Map<Long, String> rvas = collectRVAs();
        println("Collected " + rvas.size() + " method RVAs from sources");

        int renamed = 0;
        int created = 0;
        int failed = 0;

        for (Map.Entry<Long, String> entry : rvas.entrySet()) {
            long rva = entry.getKey();
            String name = entry.getValue();
            Address addr = base.add(rva);

            Function func = funcMgr.getFunctionAt(addr);
            if (func == null) {
                try {
                    func = createFunction(addr, name);
                    if (func != null) created++;
                } catch (Exception e) {
                    failed++;
                    continue;
                }
            }
            if (func != null) {
                try {
                    func.setName(name, SourceType.USER_DEFINED);
                    renamed++;
                } catch (Exception e) {
                    // Duplicate name - add RVA suffix
                    try {
                        func.setName(name + "_" + Long.toHexString(rva), SourceType.USER_DEFINED);
                        renamed++;
                    } catch (Exception e2) {
                        failed++;
                    }
                }
            }
        }

        println(String.format("Renamed %d functions, created %d new, %d failed", renamed, created, failed));
    }

    private Map<Long, String> collectRVAs() throws IOException {
        Map<Long, String> rvas = new LinkedHashMap<>();
        File sourcesDir = new File(SOURCES_DIR);
        if (!sourcesDir.isDirectory()) {
            println("ERROR: Sources directory not found: " + SOURCES_DIR);
            return rvas;
        }
        walkDir(sourcesDir, rvas);
        return rvas;
    }

    private void walkDir(File dir, Map<Long, String> rvas) throws IOException {
        File[] files = dir.listFiles();
        if (files == null) return;
        for (File file : files) {
            if (file.isDirectory()) {
                walkDir(file, rvas);
            } else if (file.getName().endsWith(".cs")) {
                parseFile(file, rvas);
            }
        }
    }

    private void parseFile(File file, Map<Long, String> rvas) throws IOException {
        // Derive class name from filename
        String className = file.getName().replace(".cs", "")
            .replace("`1", "_T")
            .replace("`2", "_T2")
            .replace("`3", "_T3");

        try (BufferedReader reader = new BufferedReader(new FileReader(file))) {
            String line;
            while ((line = reader.readLine()) != null) {
                Matcher rvaMatcher = RVA_PATTERN.matcher(line);
                if (!rvaMatcher.find()) continue;

                long rva = Long.parseLong(rvaMatcher.group(1), 16);
                if (rva == 0) continue;

                Matcher methodMatcher = METHOD_PATTERN.matcher(line);
                if (methodMatcher.find()) {
                    String methodName = methodMatcher.group(1);
                    // Clean up method names
                    methodName = methodName.replace("<", "_").replace(">", "_");
                    String fullName = className + "__" + methodName;
                    rvas.put(rva, fullName);
                }
            }
        }
    }
}
