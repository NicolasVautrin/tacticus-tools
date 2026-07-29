// Ghidra headless script: apply IL2CPP symbols dumped via Frida to the Ghidra DB.
// Reads data/il2cpp_methods.tsv and data/il2cpp_classes.tsv, produced from il2cpp_full.json.
//
// ============================ SENS DE CIRCULATION -- A LIRE ============================
// Ce script ALIMENTE Ghidra. Il en existe UN SECOND, complementaire :
// `GhidraApplyIl2CppDumperNames.java`, qui passe APRES et ne renomme que les `FUN_*` restants
// (les corps generiques pleinement partages, que les metadonnees lues par Frida n'exposent pas).
// Aucun des deux ne remplace l'autre -- mesure 2026-07-29 : la chaine Frida nomme 3 165 adresses
// que le dumper laisse anonymes ; le dumper en nomme 4 882 que Frida ne voit pas. Et seul CE
// script-ci FABRIQUE LES STRUCTS : le binaire est strippe, sans lui tout le decompile perd ses
// types.
//
// ⚠ `data/symbols/<build>/ghidra/functions.tsv` N'EST PAS une entree de Ghidra et n'est PAS la
// sortie de ce script : c'est un EXTRAIT pris DEPUIS Ghidra par `ghidra_symbols.py dump`, pour
// les outils offline. Il ne doit jamais etre reinjecte. Appliquer des noms sans relancer ce
// `dump` laisse l'extrait perime, et les deux consommateurs du projet (agents via
// `mcp__ghidra__*` / outils offline) se mettent alors a se contredire silencieusement.
//
// Vue d'ensemble, avec les chiffres et les pieges : `data/symbols/README.md`.
// ======================================================================================
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

    // Racine des tables de symboles, un sous-repertoire PAR BUILD :
    //   data/symbols/<HASH>/frida/{methods,classes,enums}.tsv   (produit par preprocess)
    //   data/symbols/<HASH>/ghidra/functions.tsv                (extrait D'ICI ensuite)
    private static final String SYMBOLS_DIR = "C:/Users/nicolasv/tacticus-tools/data/symbols";

    // Resolus au demarrage par selectBuildDir() : on ne CHOISIT PLUS un chemin en dur, on
    // SELECTIONNE le build dont l'estampille correspond au binaire charge (cf. garde ci-dessous).
    private String METHODS_TSV;
    private String CLASSES_TSV;

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

    // ===== GARDE DE PROVENANCE (2026-07-25) =====
    // Ce script ECRIT dans la base Ghidra (noms, structs, signatures). Applique avec des TSV
    // d'un AUTRE build, il ecrase des symboles corrects par des faux, en silence et sans retour
    // possible. C'est exactement l'etat trouve le 2026-07-25 : les TSV a la racine de data/
    // dataient du build de mai, le projet Ghidra portait celui de juin (`gqfc5mff6c`) — et
    // METHODS_TSV pointe ces fichiers EN DUR. Un simple `run` aurait detruit le projet.
    //
    // Chaque TSV porte desormais en 1re ligne une estampille posee par
    // `scripts/python/preprocess_il2cpp_dump.py` :
    //   #!il2cpp-provenance\tsha256=<64hex>\tbuild=<hash>\tgenerated=<iso>\tsource=<f>
    // On la compare au SHA256 du binaire CHARGE. FAIL-CLOSED : estampille absente = refus
    // (artefact d'origine inconnue, donc inutilisable), estampille discordante = refus.
    private static final String PROVENANCE_MAGIC = "#!il2cpp-provenance";

    private String provenanceSha(String tsvPath) throws IOException {
        try (BufferedReader br = new BufferedReader(new FileReader(tsvPath))) {
            String first = br.readLine();
            if (first == null || !first.startsWith(PROVENANCE_MAGIC)) return null;
            for (String field : first.split("\t")) {
                if (field.startsWith("sha256=")) return field.substring(7).trim().toLowerCase();
            }
        }
        return null;
    }

    private void assertProvenance(String tsvPath) throws Exception {
        String expected = currentProgram.getExecutableSHA256();
        if (expected == null || expected.isEmpty()) {
            throw new IllegalStateException(
                "ABANDON : Ghidra ne fournit pas de SHA256 pour le binaire charge — impossible\n"
                + "de verifier la provenance des symboles. Refus d'ecrire.");
        }
        expected = expected.trim().toLowerCase();
        String got = provenanceSha(tsvPath);

        if (got == null) {
            throw new IllegalStateException(
                "ABANDON : " + tsvPath + " n'a PAS d'estampille de provenance.\n"
                + "  Son build d'origine est INCONNU. L'appliquer ecraserait potentiellement des\n"
                + "  symboles corrects par ceux d'un autre build (incident du 2026-07-25).\n"
                + "  Regenerer la chaine :\n"
                + "    1) jeu lance + injection Frida : hooks-legacy/_oneshot/dump-il2cpp-full.js\n"
                + "       -> data/il2cpp_full.json\n"
                + "    2) python scripts/python/preprocess_il2cpp_dump.py   (pose l'estampille)");
        }
        if (!got.equals(expected)) {
            throw new IllegalStateException(
                "ABANDON : DESYNCHRONISATION build <-> symboles.\n"
                + "  " + tsvPath + "\n"
                + "    provenance sha256 = " + got + "\n"
                + "  binaire charge par Ghidra\n"
                + "    sha256            = " + expected + "\n"
                + "  Ces TSV viennent d'un AUTRE binaire : les appliquer poserait des noms FAUX\n"
                + "  sur des adresses qui ne leur correspondent pas. Regenerer le dump depuis le\n"
                + "  binaire courant avant de relancer.");
        }
        println("provenance OK : " + tsvPath + " <-> binaire charge (sha256 " + expected.substring(0, 16) + "...)");
    }

    // SELECTION DU BUILD — remplace le chemin en dur qui etait la cause de l'incident.
    // On parcourt data/symbols/<HASH>/frida/ et on retient CELUI dont l'estampille porte le
    // sha256 du binaire charge. Le script ne peut donc plus appliquer les symboles d'un AUTRE
    // build : soit il trouve le bon, soit il refuse. Le hash du dossier n'est qu'un indice de
    // lecture — c'est le sha256 qui decide.
    private void selectBuildDir() throws Exception {
        String want = currentProgram.getExecutableSHA256();
        if (want == null || want.isEmpty()) {
            throw new IllegalStateException(
                "ABANDON : Ghidra ne fournit pas de SHA256 pour le binaire charge — impossible\n"
                + "de selectionner les symboles correspondants. Refus d'ecrire.");
        }
        want = want.trim().toLowerCase();

        File root = new File(SYMBOLS_DIR);
        File[] builds = root.listFiles(File::isDirectory);
        List<String> seen = new ArrayList<>();
        if (builds != null) {
            Arrays.sort(builds);
            for (File b : builds) {
                File m = new File(new File(b, "frida"), "methods.tsv");
                if (!m.isFile()) continue;
                String sha = provenanceSha(m.getPath());
                seen.add("    " + b.getName() + " -> " + (sha == null ? "(pas d'estampille)" : sha));
                if (want.equals(sha)) {
                    METHODS_TSV = m.getPath();
                    CLASSES_TSV = new File(new File(b, "frida"), "classes.tsv").getPath();
                    println("build selectionne : " + b.getName()
                            + " (sha256 " + want.substring(0, 16) + "...)");
                    return;
                }
            }
        }
        throw new IllegalStateException(
            "ABANDON : aucun jeu de symboles ne correspond au binaire charge.\n"
            + "  binaire Ghidra sha256 = " + want + "\n"
            + "  builds disponibles sous " + SYMBOLS_DIR + " :\n"
            + (seen.isEmpty() ? "    (aucun)" : String.join("\n", seen)) + "\n"
            + "  Regenerer la chaine pour CE binaire :\n"
            + "    1) jeu lance : python scripts/python/dump_il2cpp.py --pid <pid>\n"
            + "    2)             python scripts/python/preprocess_il2cpp_dump.py");
    }

    @Override
    protected void run() throws Exception {
        // AVANT toute ecriture : selectionner le build qui correspond au binaire charge,
        // puis re-verifier l'estampille de chaque TSV effectivement lu.
        selectBuildDir();
        assertProvenance(METHODS_TSV);
        if (APPLY_CLASSES) assertProvenance(CLASSES_TSV);

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

                if (line.startsWith(PROVENANCE_MAGIC)) continue;   // estampille, deja validee
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
                String safeName = canonicalName(name, declaringClass);

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

    /**
     * FORME CANONIQUE d'un symbole : {@code Namespace.Classe$$Membre}, avec les chevrons
     * echappes en {@code u003C} / {@code u003E}.
     *
     * <p>POURQUOI ce format, et pas le nom complet pointe de methods.tsv (mesure 2026-07-29).
     * Tout le depot cite ses symboles sous cette forme -- 4 230 citations dans 241 fichiers de
     * {@code scripts/python/engine} et {@code docs/rl} -- et c'est la forme que portait la table
     * du build {@code gqfc5mff6c}.
     *
     * <p>D'OU VIENT LE {@code $$} : ce n'est pas une convention maison, c'est celle
     * d'**Il2CppDumper v39**. Elle a ete introduite par
     * {@code scripts/ghidra/GhidraApplyIl2CppNamesWin.java}, qui lisait
     * {@code data/win_dump/script.json} et recopiait le champ {@code Name} VERBATIM -- son
     * {@code sanitize} conservait explicitement {@code $}, {@code <} et {@code >}. Ce script a
     * ete SUPPRIME le 2026-07-25 (commit {@code 8e591496}, « suppression du legacy ») au profit
     * de celui-ci, alimente par Frida.
     *
     * <p>POURQUOI PERSONNE N'A VU LA DIVERGENCE PENDANT QUATRE JOURS : le projet Ghidra de
     * {@code gqfc5mff6c} etait DEJA symbolise par le legacy, et sa table a ete versionnee telle
     * quelle le meme jour ({@code 4c82b367}). Il fallait une re-symbolisation COMPLETE pour que
     * ce script montre qu'il produisait autre chose -- la premiere a eu lieu au changement de
     * build du 2026-07-29.
     *
     * <p>Ce qu'a coute la divergence, sur le build {@code rnca9r7q6c} : ZERO citation sur 1 266
     * resolvait dans la table produite, et le diff inter-build affichait 0,43 % de symboles
     * communs -- une reecriture totale du jeu apparente, qui n'etait qu'un separateur.
     *
     * <p>Le format n'est pas qu'une habitude : le {@code $$} marque la frontiere TYPE / MEMBRE,
     * qu'une chaine pointee ne peut pas exprimer ({@code A.B.C} ne dit pas ou finit le type).
     * C'est ce qui rend le grep code -> table immediat, et l'echappement conserve joue le meme
     * role pour les lambdas generes.
     *
     * <p>La regle est EXACTE : sur les 121 501 methodes de {@code gqfc5mff6c}, le nom complet
     * commence par la classe declarante suivie d'un point dans 121 501 cas -- aucune exception.
     * Le repli sur {@code fullName} ne couvre donc aucun cas connu ; il est la par prudence.
     */
    private String canonicalName(String fullName, String declaringClass) {
        String prefix = declaringClass + ".";
        String member = fullName.startsWith(prefix)
                ? fullName.substring(prefix.length())
                : fullName;
        return escapeAngles(declaringClass) + "$$" + escapeAngles(member);
    }

    private String escapeAngles(String s) {
        return sanitizeName(s).replace("<", "u003C").replace(">", "u003E");
    }

    // ===== Class loading =====

    private void loadClasses() throws IOException {
        try (BufferedReader br = new BufferedReader(new FileReader(CLASSES_TSV), 1 << 20)) {
            String line;
            while ((line = br.readLine()) != null) {
                // L'estampille a EXACTEMENT 5 champs : sans ce saut elle passerait le test
                // `parts.length < 5` et creerait une classe fantome `#!il2cpp-provenance`.
                if (line.startsWith(PROVENANCE_MAGIC)) continue;
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
