// Ghidra headless script: apply IL2CPP method names from Il2CppDumper
// script.json directly (no intermediate il2cpp_full.json needed).
//
// Names only (not types) — enough to make decompiled output readable.
// Type-aware version is GhidraApplyIl2CppSymbols.java which reads our
// canonical il2cpp_full.json + il2cpp.h.
//
// Input: data/win_dump/script.json (produced by Il2CppDumper v39).
//
// @category IL2CPP

import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.FunctionManager;
import ghidra.program.model.symbol.SourceType;

import java.io.*;
import java.nio.file.*;

public class GhidraApplyIl2CppNamesWin extends GhidraScript {

    private static final String SCRIPT_JSON =
        "C:/Users/nicolasv/tacticus-tools/data/win_dump/script.json";

    @Override
    protected void run() throws Exception {
        Address base = currentProgram.getImageBase();
        FunctionManager funcMgr = currentProgram.getFunctionManager();
        println("Reading " + SCRIPT_JSON);

        // Stream-parse the file rather than loading 87MB JSON in memory.
        // We only care about ScriptMethod entries; format is one per line
        // when pretty-printed, but the file is single-line JSON. Use a
        // simple state machine to extract Address + Name pairs.
        String json = new String(Files.readAllBytes(Paths.get(SCRIPT_JSON)));
        int idx = json.indexOf("\"ScriptMethod\"");
        if (idx < 0) { println("ScriptMethod array not found"); return; }
        idx = json.indexOf('[', idx);
        if (idx < 0) { println("ScriptMethod opening bracket not found"); return; }

        int applied = 0;
        int notFound = 0;
        int alreadyNamed = 0;
        long lastReport = System.currentTimeMillis();

        // Walk through {Address: N, Name: "..."} objects.
        int p = idx + 1;
        int len = json.length();
        while (p < len) {
            char c = json.charAt(p);
            if (c == ']') break;          // end of array
            if (c != '{') { p++; continue; }
            int objEnd = findMatching(json, p, '{', '}');
            if (objEnd < 0) break;
            String obj = json.substring(p, objEnd + 1);
            p = objEnd + 1;

            long addr = parseLong(obj, "\"Address\":");
            String name = parseString(obj, "\"Name\":");
            if (addr < 0 || name == null) continue;

            Address fnAddr = base.add(addr);
            Function fn = funcMgr.getFunctionContaining(fnAddr);
            if (fn == null) { notFound++; continue; }
            if (!fn.getName().startsWith("FUN_")) {
                alreadyNamed++;
                continue;
            }
            try {
                String safe = sanitize(name);
                fn.setName(safe, SourceType.USER_DEFINED);
                applied++;
            } catch (Exception e) { /* duplicate name etc. — skip */ }

            if (System.currentTimeMillis() - lastReport > 5000) {
                println(String.format("  applied=%d notFound=%d alreadyNamed=%d",
                    applied, notFound, alreadyNamed));
                lastReport = System.currentTimeMillis();
            }
        }
        println(String.format(
            "Done. applied=%d notFound=%d alreadyNamed=%d",
            applied, notFound, alreadyNamed));
    }

    private static int findMatching(String s, int from, char open, char close) {
        int depth = 0;
        boolean inStr = false;
        boolean esc = false;
        for (int i = from; i < s.length(); i++) {
            char c = s.charAt(i);
            if (esc) { esc = false; continue; }
            if (c == '\\') { esc = true; continue; }
            if (c == '"') { inStr = !inStr; continue; }
            if (inStr) continue;
            if (c == open) depth++;
            else if (c == close) {
                depth--;
                if (depth == 0) return i;
            }
        }
        return -1;
    }

    private static long parseLong(String obj, String key) {
        int k = obj.indexOf(key);
        if (k < 0) return -1;
        int start = k + key.length();
        while (start < obj.length() && Character.isWhitespace(obj.charAt(start))) start++;
        int end = start;
        while (end < obj.length() && (Character.isDigit(obj.charAt(end)) || obj.charAt(end) == '-')) end++;
        try { return Long.parseLong(obj.substring(start, end)); }
        catch (NumberFormatException e) { return -1; }
    }

    private static String parseString(String obj, String key) {
        int k = obj.indexOf(key);
        if (k < 0) return null;
        int start = obj.indexOf('"', k + key.length());
        if (start < 0) return null;
        StringBuilder sb = new StringBuilder();
        boolean esc = false;
        for (int i = start + 1; i < obj.length(); i++) {
            char c = obj.charAt(i);
            if (esc) { sb.append(c); esc = false; continue; }
            if (c == '\\') { esc = true; continue; }
            if (c == '"') return sb.toString();
            sb.append(c);
        }
        return null;
    }

    private static String sanitize(String s) {
        // Ghidra symbol names — strip chars that would confuse the C decompiler
        // output. Keep $ and < > since they appear in generic / nested names
        // and Ghidra tolerates them.
        return s.replace(' ', '_').replace('\t', '_').replace('\n', '_');
    }
}
