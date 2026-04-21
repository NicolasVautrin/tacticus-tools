// Ghidra headless script: test Codex hypothesis — replace typed params with void*
// (keeping param count and calling convention intact) to see if type propagation
// is the killer, independent of ABI stack spill.
//
// For each test RVA:
// 1. Replace every param's DataType with `void*` (via PointerDataType over VoidDataType)
// 2. Replace return with `undefined8`
// 3. Decompile, timeout 60s, report
//
// RUN ON data/ghidra_tacticus_untyped (keeps main project clean).
// @category IL2CPP

import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileOptions;
import ghidra.app.decompiler.DecompileResults;
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.data.*;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.FunctionManager;
import ghidra.program.model.listing.Parameter;
import ghidra.program.model.listing.ParameterImpl;
import ghidra.program.model.listing.Variable;
import ghidra.program.model.symbol.SourceType;

import java.util.ArrayList;
import java.util.List;

public class GhidraTestVoidStarSigs extends GhidraScript {

    // Same 5 RVAs as the first untyped test so we compare apples-to-apples.
    // Each entry: {rva, param_count_including_implicit_this}.
    // Previous tests stripped signatures, so we can't read param count from DB — hardcode from il2cpp_methods.tsv.
    private static final long[][] TEST_RVAS = {
        {0x2B4EC7CL, 2},  // op_BitwiseAnd: static, 2 explicit = 2 total
        {0x1F9F684L, 9},  // AGameModeSource..ctor: 1 this + 8 explicit = 9 total (>= 9 = stack spill!)
        {0x1F9F718L, 1},  // State_BattleLoading: 1 this, 0 explicit = 1 total (empty-big edge case)
        {0x2AEFBE4L, 6},  // RepairBehaviour..ctor: 1 this + 5 explicit = 6 total
        {0x2B4AE14L, 2},  // op_BitwiseOr: static, 2 explicit = 2 total
        {0x2b0217cL, 1},  // LionHelmAbility..ctor: 1 this, 0 explicit = 1 total (empty-big parent)
    };
    private static final int TIMEOUT_S = 120;

    @Override
    protected void run() throws Exception {
        Address base = currentProgram.getImageBase();
        FunctionManager funcMgr = currentProgram.getFunctionManager();
        DataTypeManager dtm = currentProgram.getDataTypeManager();

        // Build the void* type once
        PointerDataType voidPtr = new PointerDataType(VoidDataType.dataType, 8, dtm);

        DecompInterface decomp = new DecompInterface();
        DecompileOptions opts = new DecompileOptions();
        opts.setMaxPayloadMBytes(512);
        decomp.setOptions(opts);
        decomp.openProgram(currentProgram);

        for (long[] entry : TEST_RVAS) {
            long rva = entry[0];
            int paramCount = (int) entry[1];
            Address addr = base.add(rva);
            Function f = funcMgr.getFunctionAt(addr);
            if (f == null) { println("no function @0x" + Long.toHexString(rva)); continue; }

            // --- Retype to void* × paramCount (preserve param count + storage) ---
            int tx = currentProgram.startTransaction("voidstar_" + rva);
            try {
                List<Variable> newParams = new ArrayList<>();
                for (int i = 0; i < paramCount; i++) {
                    String name = (i == 0 && !isStaticMethod(rva)) ? "this" : ("p" + i);
                    newParams.add(new ParameterImpl(name, voidPtr, currentProgram, SourceType.USER_DEFINED));
                }
                f.replaceParameters(newParams, Function.FunctionUpdateType.DYNAMIC_STORAGE_ALL_PARAMS,
                                    true, SourceType.USER_DEFINED);
                f.setReturn(Undefined8DataType.dataType, f.getReturn().getVariableStorage(), SourceType.USER_DEFINED);
                currentProgram.endTransaction(tx, true);
            } catch (Exception e) {
                currentProgram.endTransaction(tx, false);
                println("retype failed for 0x" + Long.toHexString(rva) + ": " + e.getMessage());
                continue;
            }

            println("\n======== 0x" + Long.toHexString(rva) + " " + f.getName()
                    + " (void* × " + paramCount + " + undefined8 return, timeout " + TIMEOUT_S + "s) ========");
            long t0 = System.currentTimeMillis();
            DecompileResults res = null;
            try {
                res = decomp.decompileFunction(f, TIMEOUT_S, monitor);
            } catch (Exception e) {
                println("Exception: " + e.getMessage());
            }
            long dt = System.currentTimeMillis() - t0;
            if (res != null && res.getDecompiledFunction() != null) {
                String c = res.getDecompiledFunction().getC();
                String[] lines = c.split("\n");
                println("  OK " + dt + "ms, " + lines.length + " lines");
                // Print only signature + first 5 lines to keep log short
                for (int i = 0; i < Math.min(lines.length, 8); i++) println("    " + lines[i]);
                if (lines.length > 8) println("    ... (" + (lines.length - 8) + " more lines)");
            } else {
                println("  FAIL " + dt + "ms: " + (res != null ? res.getErrorMessage() : "null"));
            }
        }
        decomp.dispose();
    }

    private boolean isStaticMethod(long rva) {
        // op_BitwiseAnd and op_BitwiseOr are the only static methods in our test set
        return rva == 0x2B4EC7CL || rva == 0x2B4AE14L;
    }
}