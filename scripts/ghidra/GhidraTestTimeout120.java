// Ghidra headless script: re-test a few known-failed methods with a longer timeout
// (120s) and signature stripped. If they pass, the issue is body complexity solvable
// with more time. If not, the method is irrecoverable.
//
// RUN ON data/ghidra_tacticus_untyped
// @category IL2CPP

import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileOptions;
import ghidra.app.decompiler.DecompileResults;
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.data.Undefined8DataType;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.FunctionManager;
import ghidra.program.model.listing.Variable;
import ghidra.program.model.symbol.SourceType;

import java.util.ArrayList;

public class GhidraTestTimeout120 extends GhidraScript {

    private static final long[] TEST_RVAS = {
        0x2b0217cL,  // LionHelmAbility..ctor (prev: timeout in all variants @ 60s)
        0x2B4AE14L,  // AbilityTrigger.op_BitwiseOr (prev: timeout @ 60s)
    };
    private static final int TIMEOUT_S = 120;

    @Override
    protected void run() throws Exception {
        Address base = currentProgram.getImageBase();
        FunctionManager funcMgr = currentProgram.getFunctionManager();

        DecompInterface decomp = new DecompInterface();
        DecompileOptions opts = new DecompileOptions();
        opts.setMaxPayloadMBytes(512);
        decomp.setOptions(opts);
        decomp.openProgram(currentProgram);

        for (long rva : TEST_RVAS) {
            Address addr = base.add(rva);
            Function f = funcMgr.getFunctionAt(addr);
            if (f == null) { println("no function @0x" + Long.toHexString(rva)); continue; }

            // Ensure signature stripped (may already be from previous run, safe to re-apply)
            int tx = currentProgram.startTransaction("strip_" + rva);
            try {
                f.replaceParameters(new ArrayList<>(), Function.FunctionUpdateType.DYNAMIC_STORAGE_ALL_PARAMS, true, SourceType.DEFAULT);
                f.setReturn(Undefined8DataType.dataType, f.getReturn().getVariableStorage(), SourceType.DEFAULT);
                f.setSignatureSource(SourceType.DEFAULT);
                currentProgram.endTransaction(tx, true);
            } catch (Exception e) {
                currentProgram.endTransaction(tx, false);
                throw e;
            }

            println("\n======== 0x" + Long.toHexString(rva) + " " + f.getName() + " (timeout " + TIMEOUT_S + "s, UNTYPED) ========");
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
                println("  " + dt + "ms, " + c.split("\n").length + " lines");
                println(c);
            } else {
                println("  " + dt + "ms FAIL: " + (res != null ? res.getErrorMessage() : "null"));
            }
        }
        decomp.dispose();
    }
}