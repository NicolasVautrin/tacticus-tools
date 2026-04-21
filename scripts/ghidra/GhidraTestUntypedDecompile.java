// Ghidra headless script: validate the hypothesis that applied IL2CPP types are
// causing decompilation failures. For a hardcoded list of RVAs (known TIMEOUT/NULL
// cases), strip the function's typed signature (clear params, reset signature source
// to DEFAULT), then decompile. Output to stdout.
//
// RUN ON THE DUPLICATED PROJECT (data/ghidra_tacticus_untyped) — modifies the DB.
//
// @category IL2CPP

import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileOptions;
import ghidra.app.decompiler.DecompileResults;
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.FunctionManager;
import ghidra.program.model.listing.Parameter;
import ghidra.program.model.listing.ReturnParameterImpl;
import ghidra.program.model.listing.Variable;
import ghidra.program.model.data.DataTypeManager;
import ghidra.program.model.data.Undefined8DataType;
import ghidra.program.model.data.VoidDataType;
import ghidra.program.model.symbol.SourceType;

import java.util.ArrayList;
import java.util.List;

public class GhidraTestUntypedDecompile extends GhidraScript {

    // Sample of known-failed methods (TIMEOUT/NULL in the main run).
    // Mix of patterns: operator overload, ctor, coroutine MoveNext, state machine.
    private static final long[] TEST_RVAS = {
        0x2B4EC7CL,  // IdunBattle.DSL.AbilityBehaviour.op_BitwiseAnd  (operator)
        0x1F9F684L,  // IdunBattle.ViewLogic.BattleSource.AGameModeSource..ctor  (ctor)
        0x1F9F718L,  // IdunBattle.ViewLogic.BattleSource.AGameModeSource.State_BattleLoading  (state_machine)
        0x2AEFBE4L,  // IdunBattle.Entities.Behaviours.RepairBehaviour..ctor  (ctor)
        0x2B4AE14L,  // IdunBattle.DSL.AbilityTrigger.op_BitwiseOr  (operator)
    };

    private static final int TIMEOUT_S = 60;

    @Override
    protected void run() throws Exception {
        Address base = currentProgram.getImageBase();
        FunctionManager funcMgr = currentProgram.getFunctionManager();

        // First pass: strip all typed signatures on our test set
        println("=== STRIP PHASE ===");
        int stripped = 0;
        for (long rva : TEST_RVAS) {
            Address addr = base.add(rva);
            Function f = funcMgr.getFunctionAt(addr);
            if (f == null) {
                println(String.format("0x%X: no function (skip)", rva));
                continue;
            }
            try {
                // Clear all existing parameters
                List<Variable> empty = new ArrayList<>();
                f.replaceParameters(empty, Function.FunctionUpdateType.DYNAMIC_STORAGE_ALL_PARAMS,
                                    true, SourceType.DEFAULT);
                // Also nuke return to undefined
                f.setReturn(Undefined8DataType.dataType,
                            f.getReturn().getVariableStorage(), SourceType.DEFAULT);
                f.setSignatureSource(SourceType.DEFAULT);
                stripped++;
                println(String.format("0x%X: stripped %s", rva, f.getName()));
            } catch (Exception e) {
                println(String.format("0x%X: strip failed: %s", rva, e.getMessage()));
            }
        }
        println("Stripped " + stripped + " functions");

        // Second pass: decompile each with the default "decompile" style
        println("\n=== DECOMPILE PHASE ===");
        DecompInterface decomp = new DecompInterface();
        DecompileOptions opts = new DecompileOptions();
        opts.setMaxPayloadMBytes(512);
        decomp.setOptions(opts);
        decomp.openProgram(currentProgram);

        int ok = 0, fail = 0;
        for (long rva : TEST_RVAS) {
            Address addr = base.add(rva);
            Function f = funcMgr.getFunctionAt(addr);
            if (f == null) continue;
            long t0 = System.currentTimeMillis();
            DecompileResults res = null;
            try {
                res = decomp.decompileFunction(f, TIMEOUT_S, monitor);
            } catch (Exception e) {
                println(String.format("0x%X: exception %s", rva, e.getMessage()));
            }
            long dt = System.currentTimeMillis() - t0;
            if (res != null && res.getDecompiledFunction() != null) {
                String c = res.getDecompiledFunction().getC();
                int lines = c.split("\n").length;
                println(String.format("\n---- 0x%X: %s (%dms, %d lines) ----", rva, f.getName(), dt, lines));
                println(c);
                ok++;
            } else {
                String err = res != null ? res.getErrorMessage() : "null";
                println(String.format("\n---- 0x%X: %s (%dms) FAIL: %s ----", rva, f.getName(), dt, err));
                fail++;
            }
        }
        decomp.dispose();
        println(String.format("\n=== SUMMARY: %d ok / %d fail ===", ok, fail));
    }
}