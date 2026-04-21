// Ghidra headless script: test flatten-vs-composition fix for "empty-big" classes.
// Picks ONE test method on a class where the dump has fields=[] but parent has real fields,
// tries 3 variants, decompiles each, prints C to stdout.
//
// RUN ON data/ghidra_tacticus_untyped (not the main project).
// @category IL2CPP

import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileOptions;
import ghidra.app.decompiler.DecompileResults;
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.data.*;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.FunctionManager;
import ghidra.program.model.listing.ParameterImpl;
import ghidra.program.model.listing.Variable;
import ghidra.program.model.symbol.SourceType;

import java.util.ArrayList;
import java.util.List;

public class GhidraTestStructFix extends GhidraScript {

    // Test method: LionHelmAbility..ctor
    private static final long TEST_RVA = 0x2b0217cL;
    private static final String CHILD_CLASS  = "IdunBattleLogic_Entities_Abilities_Triggered_Loki_LionHelmAbility";
    private static final String PARENT_CLASS = "IdunBattle_Entities_Abilities_BaseTriggeredAbility";

    private static final int TIMEOUT_S = 120;

    private DataTypeManager dtm;
    private CategoryPath cat = new CategoryPath("/IL2CPP");

    @Override
    protected void run() throws Exception {
        dtm = currentProgram.getDataTypeManager();
        Address base = currentProgram.getImageBase();
        FunctionManager funcMgr = currentProgram.getFunctionManager();

        Address addr = base.add(TEST_RVA);
        Function f = funcMgr.getFunctionAt(addr);
        if (f == null) { println("No function at 0x" + Long.toHexString(TEST_RVA)); return; }
        println("Test function: " + f.getName() + " @ 0x" + Long.toHexString(TEST_RVA));

        DecompInterface decomp = new DecompInterface();
        DecompileOptions opts = new DecompileOptions();
        opts.setMaxPayloadMBytes(512);
        decomp.setOptions(opts);
        decomp.openProgram(currentProgram);

        // --- Look up current (empty) struct and parent struct
        Structure childOrig = (Structure) dtm.getDataType(cat, CHILD_CLASS);
        Structure parent = (Structure) dtm.getDataType(cat, PARENT_CLASS);
        if (childOrig == null || parent == null) {
            println("Cannot find child or parent struct: child=" + childOrig + " parent=" + parent);
            return;
        }
        println("Child orig: " + childOrig.getName() + " size=" + childOrig.getLength() + " components=" + childOrig.getNumDefinedComponents());
        println("Parent:     " + parent.getName() + " size=" + parent.getLength() + " components=" + parent.getNumDefinedComponents());

        // --- Variant A: BASELINE (empty struct, current state) -------------
        runOne(decomp, f, "BASELINE (empty struct + typed sig)");

        // --- Variant B: FLATTEN — replicate parent fields into child struct
        int txFlatten = currentProgram.startTransaction("flatten");
        try {
            int childSz = childOrig.getLength();
            // Clear child struct to blank, then copy parent's defined components
            // (iterate parent's defined components in offset order)
            childOrig.deleteAll();
            childOrig.growStructure(childSz);
            for (DataTypeComponent pc : parent.getDefinedComponents()) {
                int off = pc.getOffset();
                if (off + pc.getLength() > childSz) continue;
                try {
                    childOrig.replaceAtOffset(off, pc.getDataType(), pc.getLength(), pc.getFieldName(), pc.getComment());
                } catch (Exception e) {
                    println("  flatten replaceAtOffset fail @0x" + Integer.toHexString(off) + ": " + e.getMessage());
                }
            }
            currentProgram.endTransaction(txFlatten, true);
        } catch (Exception e) {
            currentProgram.endTransaction(txFlatten, false);
            throw e;
        }
        runOne(decomp, f, "V1 FLATTEN");

        // --- Variant C: COMPOSITION — parent struct embedded as first field
        int txComp = currentProgram.startTransaction("compose");
        try {
            int childSz = childOrig.getLength();
            childOrig.deleteAll();
            childOrig.growStructure(childSz);
            childOrig.replaceAtOffset(0, parent, parent.getLength(), "_base", null);
            currentProgram.endTransaction(txComp, true);
        } catch (Exception e) {
            currentProgram.endTransaction(txComp, false);
            throw e;
        }
        runOne(decomp, f, "V2 COMPOSITION");

        // --- Variant D: UNTYPED (strip signature, struct stays composition) -
        int txStrip = currentProgram.startTransaction("strip");
        try {
            f.replaceParameters(new ArrayList<>(), Function.FunctionUpdateType.DYNAMIC_STORAGE_ALL_PARAMS, true, SourceType.DEFAULT);
            f.setReturn(Undefined8DataType.dataType, f.getReturn().getVariableStorage(), SourceType.DEFAULT);
            f.setSignatureSource(SourceType.DEFAULT);
            currentProgram.endTransaction(txStrip, true);
        } catch (Exception e) {
            currentProgram.endTransaction(txStrip, false);
            throw e;
        }
        runOne(decomp, f, "V3 UNTYPED (no signature)");

        decomp.dispose();
    }

    private void runOne(DecompInterface decomp, Function f, String label) {
        println("\n======== " + label + " ========");
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
}