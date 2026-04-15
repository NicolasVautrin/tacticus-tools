// Ghidra headless script: decompile specific methods by RVA + find call sites
// Usage: analyzeHeadless ... -postScript GhidraDecompile.java
//
// @category IL2CPP

import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileResults;
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.FunctionManager;
import ghidra.program.model.symbol.Reference;
import ghidra.program.model.symbol.ReferenceManager;
import ghidra.program.model.symbol.SourceType;
import ghidra.util.task.ConsoleTaskMonitor;

import java.io.FileWriter;
import java.io.PrintWriter;
import java.util.*;

public class GhidraDecompile extends GhidraScript {

    // Target methods to decompile
    private static final Object[][] TARGETS = {
        {"AutomaticBattleRunner__Run", 0x27C298CL},
        {"HeadlessBattleRunnerPopup__GenerateBattleConfig", 0x2691C2CL},
        {"HeadlessBattleRunnerPopup__RunBattle", 0x2692150L},
        {"HeadlessBattleRunnerPopup__OnStartPressed", 0x26917D4L},
        {"HeadlessBattleRunnerPopup__ThreadRoutine", 0x269211CL},
        {"IdunRunner__Initialize", 0x29384F4L},
        {"IdunRunner__Apply", 0x2938CA0L},
        {"IdunRunner__StartMatch", 0x293CC74L},
        {"BattleConfiguration__ShallowClone", 0x2BEE268L},
    };

    // Call site analysis targets
    private static final Object[][] XREF_TARGETS = {
        {"BattleConfiguration__.ctor", 0x2BEE2E4L},
    };

    private static final String OUTPUT_FILE = "C:/Users/nicolasv/tacticus-tools/data/decompiled_methods.c";

    @Override
    protected void run() throws Exception {
        Address base = currentProgram.getImageBase();
        FunctionManager funcMgr = currentProgram.getFunctionManager();
        ReferenceManager refMgr = currentProgram.getReferenceManager();

        DecompInterface decomp = new DecompInterface();
        decomp.openProgram(currentProgram);

        List<String> results = new ArrayList<>();

        // --- Decompile target methods ---
        for (Object[] target : TARGETS) {
            String name = (String) target[0];
            long rva = (Long) target[1];
            Address addr = base.add(rva);

            Function func = funcMgr.getFunctionAt(addr);
            if (func == null) {
                func = createFunction(addr, name);
            }
            if (func == null) {
                results.add(String.format("// ERROR: Could not create function at 0x%x for %s\n", rva, name));
                println("[FAIL] " + name + ": could not create function");
                continue;
            }

            func.setName(name, SourceType.USER_DEFINED);

            DecompileResults res = decomp.decompileFunction(func, 120, monitor);
            if (res != null && res.getDecompiledFunction() != null) {
                String code = res.getDecompiledFunction().getC();
                results.add(String.format("// === %s (RVA: 0x%X) ===\n%s\n", name, rva, code));
                println(String.format("[OK] %s decompiled (%d chars)", name, code.length()));
            } else {
                String err = (res != null) ? res.getErrorMessage() : "unknown error";
                results.add(String.format("// ERROR decompiling %s: %s\n", name, err));
                println("[FAIL] " + name + ": " + err);
            }
        }

        // --- Call site analysis ---
        results.add("// " + "=".repeat(70) + "\n");
        results.add("// CALL SITE ANALYSIS\n");
        results.add("// " + "=".repeat(70) + "\n\n");

        for (Object[] xref : XREF_TARGETS) {
            String name = (String) xref[0];
            long rva = (Long) xref[1];
            Address addr = base.add(rva);

            // Ensure function exists at target
            Function targetFunc = funcMgr.getFunctionAt(addr);
            if (targetFunc == null) {
                targetFunc = createFunction(addr, name);
            }
            if (targetFunc != null) {
                targetFunc.setName(name, SourceType.USER_DEFINED);
            }

            // Find all callers
            Reference[] refs = getReferencesTo(addr);
            List<Function> callers = new ArrayList<>();
            for (Reference ref : refs) {
                if (ref.getReferenceType().isCall()) {
                    Function caller = funcMgr.getFunctionContaining(ref.getFromAddress());
                    if (caller != null && !callers.contains(caller)) {
                        callers.add(caller);
                    }
                }
            }

            results.add(String.format("// --- %s (RVA: 0x%X) called by %d functions ---\n", name, rva, callers.size()));
            for (Function caller : callers) {
                long callerRva = caller.getEntryPoint().subtract(base);
                results.add(String.format("//   caller: %s @ RVA 0x%X\n", caller.getName(), callerRva));
            }
            results.add("\n");

            // Decompile up to 15 callers
            int limit = Math.min(callers.size(), 15);
            for (int i = 0; i < limit; i++) {
                Function caller = callers.get(i);
                long callerRva = caller.getEntryPoint().subtract(base);
                DecompileResults res = decomp.decompileFunction(caller, 120, monitor);
                if (res != null && res.getDecompiledFunction() != null) {
                    String code = res.getDecompiledFunction().getC();
                    results.add(String.format("// === CALLER #%d: %s (RVA: 0x%X) -> %s ===\n%s\n",
                        i + 1, caller.getName(), callerRva, name, code));
                    println(String.format("[OK] caller %s decompiled (%d chars)", caller.getName(), code.length()));
                } else {
                    results.add(String.format("// ERROR decompiling caller %s\n", caller.getName()));
                    println("[FAIL] caller " + caller.getName());
                }
            }
        }

        decomp.dispose();

        // Write output
        try (PrintWriter out = new PrintWriter(new FileWriter(OUTPUT_FILE))) {
            out.println("// Decompiled methods from libil2cpp.so (WH40K Tacticus)");
            out.println("// Generated by GhidraDecompile.java");
            out.println("// Image base: " + base);
            out.println();
            for (String r : results) {
                out.print(r);
                out.println();
            }
        }

        println("\nOutput written to: " + OUTPUT_FILE);
        println("Target methods: " + TARGETS.length);
        println("XREF targets: " + XREF_TARGETS.length);
    }
}
