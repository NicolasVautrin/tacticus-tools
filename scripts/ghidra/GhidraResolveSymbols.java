// Ghidra headless script: resolve PTR_DAT_, FUN_, thunk_FUN_ symbols
// Reads unresolved addresses from data/*_addrs.txt, looks up their
// names/labels in the analyzed binary, writes mapping to data/resolved_symbols.json
//
// @category IL2CPP

import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Data;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.FunctionManager;
import ghidra.program.model.symbol.Symbol;
import ghidra.program.model.symbol.SymbolTable;

import java.io.*;
import java.util.*;

public class GhidraResolveSymbols extends GhidraScript {

    private static final String DATA_DIR = "C:/Users/nicolasv/tacticus-tools/data";

    @Override
    protected void run() throws Exception {
        Address base = currentProgram.getImageBase();
        FunctionManager funcMgr = currentProgram.getFunctionManager();
        SymbolTable symTable = currentProgram.getSymbolTable();

        Map<String, String> resolved = new LinkedHashMap<>();

        // --- Resolve PTR_DAT_ ---
        List<String> ptrAddrs = readLines(DATA_DIR + "/ptr_dat_addrs.txt");
        println("Resolving " + ptrAddrs.size() + " PTR_DAT addresses...");
        int ptrOk = 0;
        for (String entry : ptrAddrs) {
            String hex = entry.replace("PTR_DAT_", "").trim();
            try {
                Address addr = currentProgram.getAddressFactory().getDefaultAddressSpace().getAddress(Long.parseLong(hex, 16));
                // Read the pointer value at this address
                Data data = currentProgram.getListing().getDataAt(addr);
                if (data != null && data.getValue() instanceof Address) {
                    Address target = (Address) data.getValue();
                    // Look up symbols at the target
                    Symbol[] symbols = symTable.getSymbols(target);
                    if (symbols.length > 0) {
                        String name = symbols[0].getName();
                        if (!name.startsWith("DAT_") && !name.startsWith("PTR_")) {
                            resolved.put(entry, name);
                            ptrOk++;
                            continue;
                        }
                    }
                    // Try function at target
                    Function func = funcMgr.getFunctionAt(target);
                    if (func != null) {
                        resolved.put(entry, func.getName());
                        ptrOk++;
                        continue;
                    }
                }
                // Fallback: check symbols at the PTR_DAT address itself
                Symbol[] syms = symTable.getSymbols(addr);
                for (Symbol sym : syms) {
                    if (!sym.getName().startsWith("PTR_DAT_")) {
                        resolved.put(entry, sym.getName());
                        ptrOk++;
                        break;
                    }
                }
            } catch (Exception e) { /* skip */ }
        }
        println("PTR_DAT: " + ptrOk + "/" + ptrAddrs.size() + " resolved");

        // --- Resolve FUN_ and thunk_FUN_ ---
        List<String> funAddrs = readLines(DATA_DIR + "/fun_addrs.txt");
        List<String> thunkAddrs = readLines(DATA_DIR + "/thunk_addrs.txt");
        funAddrs.addAll(thunkAddrs);
        println("Resolving " + funAddrs.size() + " FUN_/thunk addresses...");
        int funOk = 0;
        for (String entry : funAddrs) {
            String hex = entry.replace("thunk_FUN_", "").replace("FUN_", "").trim();
            try {
                Address addr = currentProgram.getAddressFactory().getDefaultAddressSpace().getAddress(Long.parseLong(hex, 16));
                Function func = funcMgr.getFunctionAt(addr);
                if (func != null) {
                    String name = func.getName();
                    if (!name.startsWith("FUN_") && !name.startsWith("thunk_")) {
                        resolved.put(entry, name);
                        funOk++;
                        continue;
                    }
                }
                // Check symbol table
                Symbol[] syms = symTable.getSymbols(addr);
                for (Symbol sym : syms) {
                    String name = sym.getName();
                    if (!name.startsWith("FUN_") && !name.startsWith("thunk_")) {
                        resolved.put(entry, name);
                        funOk++;
                        break;
                    }
                }
            } catch (Exception e) { /* skip */ }
        }
        println("FUN_: " + funOk + "/" + funAddrs.size() + " resolved");

        // --- Write results ---
        String outPath = DATA_DIR + "/resolved_symbols.json";
        try (PrintWriter out = new PrintWriter(new FileWriter(outPath))) {
            out.println("{");
            int count = 0;
            for (Map.Entry<String, String> e : resolved.entrySet()) {
                count++;
                String comma = (count < resolved.size()) ? "," : "";
                out.println("  \"" + escapeJson(e.getKey()) + "\": \"" + escapeJson(e.getValue()) + "\"" + comma);
            }
            out.println("}");
        }
        println("Written " + resolved.size() + " mappings to " + outPath);

        // --- Preview ---
        int shown = 0;
        for (Map.Entry<String, String> e : resolved.entrySet()) {
            println("  " + e.getKey() + " -> " + e.getValue());
            if (++shown >= 30) {
                println("  ... (" + resolved.size() + " total)");
                break;
            }
        }
    }

    private List<String> readLines(String path) throws IOException {
        List<String> lines = new ArrayList<>();
        File f = new File(path);
        if (!f.exists()) return lines;
        try (BufferedReader r = new BufferedReader(new FileReader(f))) {
            String line;
            while ((line = r.readLine()) != null) {
                line = line.trim();
                if (!line.isEmpty()) lines.add(line);
            }
        }
        return lines;
    }

    private String escapeJson(String s) {
        return s.replace("\\", "\\\\").replace("\"", "\\\"");
    }
}
