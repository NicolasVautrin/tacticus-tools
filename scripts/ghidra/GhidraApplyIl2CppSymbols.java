// Ghidra headless script: apply IL2CPP symbols dumped via Frida to the Ghidra DB.
// Reads data/il2cpp_methods.tsv and data/il2cpp_classes.tsv, produced from il2cpp_full.json.
//
// Phase 1 (MVP): create function + set name for every method RVA.
// This alone lets Ghidra decompile all 169K methods in a single pass with real names.
//
// Phase 2 (enabled via APPLY_CLASSES=true): create Structure data types for every class
// with fields at correct offsets, then set function signatures with typed parameters.
// This eliminates `long param_1` / `undefined8` in the decompiled output.
//
// @category IL2CPP

import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.data.*;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.FunctionManager;
import ghidra.program.model.listing.Parameter;
import ghidra.program.model.listing.ParameterImpl;
import ghidra.program.model.listing.ReturnParameterImpl;
import ghidra.program.model.listing.Variable;
import ghidra.program.model.symbol.SourceType;
import ghidra.program.model.symbol.SymbolTable;
import ghidra.program.model.util.CodeUnitInsertionException;
import ghidra.util.exception.InvalidInputException;

import java.io.*;
import java.util.*;

public class GhidraApplyIl2CppSymbols extends GhidraScript {

    private static final String DATA_DIR = "C:/Users/nicolasv/tacticus-tools/data";
    private static final String METHODS_TSV = DATA_DIR + "/il2cpp_methods.tsv";
    private static final String CLASSES_TSV = DATA_DIR + "/il2cpp_classes.tsv";

    // Enable phase 2: create struct types + apply function signatures
    private static final boolean APPLY_CLASSES = true;

    // Limit method count for smoke test (0 = unlimited)
    private static final int MAX_METHODS = 0;

    // Only apply signatures for methods in these namespaces (reduces noise and runtime).
    // Methods outside are still named but get a generic signature.
    private static final String[] SIGNATURE_NAMESPACES = {
        "IdunBattle.", "IdunBattleLogic.", "FixMath.", "IdunShared.", "Core.Services.", "idun."
    };

    // Category in the Ghidra data type manager to store our structs
    private static final CategoryPath IL2CPP_CATEGORY = new CategoryPath("/IL2CPP");

    // Map C# type name -> Ghidra DataType (populated lazily)
    private Map<String, DataType> typeCache = new HashMap<>();
    // Map C# class full name -> placeholder/complete Structure
    private Map<String, Structure> structs = new HashMap<>();
    // Parsed class metadata (filled during classes.tsv read)
    private Map<String, ClassInfo> classInfos = new LinkedHashMap<>();

    private DataTypeManager dtm;

    private static class ClassInfo {
        String name;
        int size;
        String parent;
        boolean valueType;
        List<FieldInfo> fields = new ArrayList<>();
    }

    private static class FieldInfo {
        String name;
        String type;
        int offset;
    }

    @Override
    protected void run() throws Exception {
        dtm = currentProgram.getDataTypeManager();
        Address base = currentProgram.getImageBase();
        FunctionManager funcMgr = currentProgram.getFunctionManager();
        SymbolTable symTab = currentProgram.getSymbolTable();

        long startTotal = System.currentTimeMillis();

        // ===== Phase 2 prep: load class metadata and create struct placeholders =====
        if (APPLY_CLASSES) {
            loadClasses();
            println("Loaded " + classInfos.size() + " class definitions");
            createStructPlaceholders();
            println("Created " + structs.size() + " struct placeholders");
            populateStructs();
            println("Populated struct fields");
        }

        // ===== Phase 1: create functions + set names =====
        println("Applying method names from " + METHODS_TSV);
        int ok = 0, created = 0, renamed = 0, skipped = 0, sigApplied = 0, sigFailed = 0;
        long lastReport = System.currentTimeMillis();

        try (BufferedReader br = new BufferedReader(new FileReader(METHODS_TSV), 1 << 20)) {
            String line;
            int count = 0;
            while ((line = br.readLine()) != null) {
                count++;
                if (monitor.isCancelled()) break;
                if (MAX_METHODS > 0 && count > MAX_METHODS) break;

                String[] parts = line.split("\t", -1);
                if (parts.length < 6) continue;

                String rvaHex = parts[0];
                String name = parts[1];
                String declaringClass = parts[2];
                boolean isStatic = "1".equals(parts[3]);
                String returnType = parts[4];
                String paramsStr = parts[5];

                long rva;
                try { rva = Long.parseLong(rvaHex, 16); } catch (NumberFormatException e) { continue; }
                if (rva == 0) { skipped++; continue; }

                Address addr = base.add(rva);
                String safeName = sanitizeName(name);

                Function func = funcMgr.getFunctionAt(addr);
                if (func == null) {
                    try {
                        func = createFunction(addr, safeName);
                        if (func != null) created++;
                    } catch (Exception e) { /* ignore */ }
                }
                if (func == null) { skipped++; continue; }

                try {
                    func.setName(safeName, SourceType.USER_DEFINED);
                    renamed++;
                } catch (Exception e) {
                    // duplicate name — Ghidra may auto-suffix; still counts as ok
                }
                ok++;

                if (APPLY_CLASSES && shouldApplySignature(name)) {
                    if (applySignature(func, returnType, paramsStr, isStatic, declaringClass)) {
                        sigApplied++;
                    } else {
                        sigFailed++;
                    }
                }

                if (count % 10000 == 0) {
                    long now = System.currentTimeMillis();
                    println(String.format("  %d methods processed (%.0f/s) — ok=%d created=%d sig=%d",
                        count, 10000.0 * 1000 / (now - lastReport), ok, created, sigApplied));
                    lastReport = now;
                }
            }
        }

        long totalTime = (System.currentTimeMillis() - startTotal) / 1000;
        println(String.format("\nDone in %ds: ok=%d, created=%d, named=%d, skipped=%d, sigApplied=%d, sigFailed=%d",
            totalTime, ok, created, renamed, skipped, sigApplied, sigFailed));
    }

    private boolean shouldApplySignature(String methodName) {
        for (String prefix : SIGNATURE_NAMESPACES) {
            if (methodName.startsWith(prefix)) return true;
        }
        return false;
    }

    private String sanitizeName(String name) {
        // Ghidra accepts most chars but some are problematic. Strip nothing, just trim.
        return name.replace(' ', '_');
    }

    // ===== Class loading =====

    private void loadClasses() throws IOException {
        try (BufferedReader br = new BufferedReader(new FileReader(CLASSES_TSV), 1 << 20)) {
            String line;
            while ((line = br.readLine()) != null) {
                String[] parts = line.split("\t", -1);
                if (parts.length < 5) continue;
                ClassInfo ci = new ClassInfo();
                ci.name = parts[0];
                try { ci.size = Integer.parseInt(parts[1]); } catch (Exception e) { ci.size = 0; }
                ci.parent = parts[2];
                ci.valueType = "1".equals(parts[3]);
                String fieldsStr = parts[4];
                if (!fieldsStr.isEmpty()) {
                    for (String f : fieldsStr.split(",")) {
                        String[] fp = f.split(":", -1);
                        if (fp.length < 3) continue;
                        FieldInfo fi = new FieldInfo();
                        fi.name = fp[0];
                        fi.type = fp[1];
                        try { fi.offset = Integer.parseInt(fp[2]); } catch (Exception e) { continue; }
                        ci.fields.add(fi);
                    }
                }
                classInfos.put(ci.name, ci);
            }
        }
    }

    // ===== Struct creation =====

    private void createStructPlaceholders() {
        Category cat = dtm.createCategory(IL2CPP_CATEGORY);
        for (ClassInfo ci : classInfos.values()) {
            int size = Math.max(ci.size, 1);
            String structName = typeNameToStructName(ci.name);
            Structure s = new StructureDataType(IL2CPP_CATEGORY, structName, size);
            Structure added = (Structure) dtm.addDataType(s, DataTypeConflictHandler.REPLACE_HANDLER);
            structs.put(ci.name, added);
        }
    }

    private void populateStructs() {
        for (ClassInfo ci : classInfos.values()) {
            Structure s = structs.get(ci.name);
            if (s == null) continue;
            // Clear then repopulate
            try { s.deleteAll(); s.setCategoryPath(IL2CPP_CATEGORY); } catch (Exception e) {}
            if (ci.size > 0) s.growStructure(ci.size);
            for (FieldInfo fi : ci.fields) {
                DataType ft = resolveType(fi.type);
                if (ft == null) continue;
                try {
                    if (fi.offset >= 0 && fi.offset < s.getLength()) {
                        s.replaceAtOffset(fi.offset, ft, ft.getLength(), fi.name, null);
                    }
                } catch (Exception e) {
                    // field doesn't fit — skip
                }
            }
        }
    }

    private String typeNameToStructName(String csName) {
        return csName.replace('.', '_').replace('<', '_').replace('>', '_')
                     .replace(',', '_').replace(' ', '_').replace('[', '_').replace(']', '_');
    }

    // ===== Type resolution =====

    private DataType resolveType(String csType) {
        if (csType == null || csType.isEmpty()) return null;
        DataType cached = typeCache.get(csType);
        if (cached != null) return cached;

        DataType dt = resolveTypeInner(csType.trim());
        if (dt != null) typeCache.put(csType, dt);
        return dt;
    }

    private DataType resolveTypeInner(String csType) {
        // Handle pointer syntax "Foo&" (ref) and "Foo*" (pointer)
        if (csType.endsWith("&") || csType.endsWith("*")) {
            DataType inner = resolveType(csType.substring(0, csType.length() - 1));
            return inner != null ? new PointerDataType(inner, 8) : new PointerDataType();
        }
        // Array types "Foo[]" → pointer to Foo
        if (csType.endsWith("[]")) {
            DataType inner = resolveType(csType.substring(0, csType.length() - 2));
            return new PointerDataType(inner != null ? inner : new VoidDataType(), 8);
        }

        // Generic types "List<Foo>" → pointer (we don't instantiate generic structs)
        int lt = csType.indexOf('<');
        if (lt >= 0) {
            // Just treat as pointer-sized opaque
            return new PointerDataType();
        }

        // Primitive mappings (IL2CPP ABI sizes for ARM64)
        switch (csType) {
            case "System.Void":   return new VoidDataType();
            case "System.Boolean":return ByteDataType.dataType;       // 1 byte
            case "System.Byte":   return ByteDataType.dataType;
            case "System.SByte":  return new CharDataType();
            case "System.Char":   return new WideCharDataType();      // 2 bytes UTF-16
            case "System.Int16":  return ShortDataType.dataType;
            case "System.UInt16": return UnsignedShortDataType.dataType;
            case "System.Int32":  return IntegerDataType.dataType;
            case "System.UInt32": return UnsignedIntegerDataType.dataType;
            case "System.Int64":  return LongLongDataType.dataType;
            case "System.UInt64": return UnsignedLongLongDataType.dataType;
            case "System.IntPtr": return new PointerDataType();
            case "System.UIntPtr":return new PointerDataType();
            case "System.Single": return FloatDataType.dataType;
            case "System.Double": return DoubleDataType.dataType;
            case "System.String": return new PointerDataType();       // IL2CPP String object ptr
            case "System.Object": return new PointerDataType();
            case "":              return null;
        }

        // Lookup in our struct cache
        Structure s = structs.get(csType);
        if (s != null) {
            // For value types: use the struct directly. For ref types: pointer to struct.
            ClassInfo ci = classInfos.get(csType);
            if (ci != null && ci.valueType) return s;
            return new PointerDataType(s, 8);
        }

        // Unknown: fallback to pointer
        return new PointerDataType();
    }

    // ===== Function signature =====

    // IMPORTANT: all params are applied as void* (not typed class/interface pointers).
    // Empirical finding: typed pointers caused Ghidra's type-propagation solver to hang
    // on ~8.5% of methods (state machines with many interface params, classes whose `this`
    // struct has size>0 but fields=[] due to inheritance-only). Using void* preserves the
    // param count and calling convention while disabling field propagation, so every method
    // converges quickly. Field access in the decompile ends up as `*(long*)(p + 0x28)`;
    // the transpiler resolves those offsets to real field names via il2cpp_classes metadata.
    //
    // Return type is set to undefined8 for the same reason. The transpiler emits the real
    // return type from il2cpp_methods.tsv when generating the Java signature.

    private boolean applySignature(Function func, String returnType, String paramsStr,
                                    boolean isStatic, String declaringClass) {
        try {
            DataType voidPtr = new PointerDataType(VoidDataType.dataType, 8);
            DataType retDt   = Undefined8DataType.dataType;

            List<Parameter> params = new ArrayList<>();

            // Prepend implicit `this` for instance methods (C# hides it; IL2CPP ABI passes it as first arg)
            if (!isStatic && !declaringClass.isEmpty()) {
                params.add(new ParameterImpl("this", voidPtr, currentProgram));
            }

            if (!paramsStr.isEmpty()) {
                int pi = 0;
                for (String pStr : paramsStr.split(",")) {
                    if (pStr.isEmpty()) continue;
                    int colon = pStr.lastIndexOf(':');
                    if (colon < 0) continue;
                    String pName = pStr.substring(0, colon);
                    if (pName.isEmpty() || !pName.matches("[A-Za-z_][A-Za-z0-9_]*")) {
                        pName = "p" + pi;
                    }
                    params.add(new ParameterImpl(pName, voidPtr, currentProgram));
                    pi++;
                }
            }

            func.updateFunction(
                null,
                new ReturnParameterImpl(retDt, currentProgram),
                params,
                Function.FunctionUpdateType.DYNAMIC_STORAGE_FORMAL_PARAMS,
                true,
                SourceType.USER_DEFINED
            );
            return true;
        } catch (Exception e) {
            return false;
        }
    }
}
