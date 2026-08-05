// GhidraDecompileAt.java -- decompile les fonctions dont les ADRESSES sont passees en argument.
//
// POURQUOI PAR ADRESSE ET NON PAR NOM : un build ARCHIVE se compare au build courant par
// l'empreinte de #482, qui rend des couples (va_avant, va_apres). Le nom, lui, ne suffit pas
// a designer un corps -- IL2CPP DEDUPLIQUE les corps triviaux, donc un meme nom peut coiffer
// des corps differents d'un build a l'autre (mesure #482 : 53,5 % des fonctions vivent dans un
// groupe de corps partage). L'adresse est la seule cle sans ambiguite DANS un build donne.
//
// USAGE
//   analyzeHeadless <projectDir> <projectName> -process GameAssembly.dll -noanalysis -readOnly \
//     -scriptPath scripts/ghidra -postScript GhidraDecompileAt.java <outFile> <va1> [<va2> ...]
import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileResults;
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;

import java.io.File;
import java.io.FileOutputStream;
import java.io.OutputStreamWriter;
import java.io.PrintWriter;
import java.nio.charset.StandardCharsets;

public class GhidraDecompileAt extends GhidraScript {

    @Override
    public void run() throws Exception {
        String[] args = getScriptArgs();
        if (args.length < 2) {
            println("ERREUR: usage <outFile> <va1> [<va2> ...]");
            return;
        }
        DecompInterface dec = new DecompInterface();
        dec.openProgram(currentProgram);
        try (PrintWriter out = new PrintWriter(new OutputStreamWriter(
                new FileOutputStream(new File(args[0])), StandardCharsets.UTF_8))) {
            for (int i = 1; i < args.length; i++) {
                Address a = currentProgram.getAddressFactory().getAddress(args[i]);
                Function f = getFunctionAt(a);
                out.println("//===== " + args[i] + " =====");
                if (f == null) {
                    out.println("// AUCUNE FONCTION a cette adresse");
                    continue;
                }
                out.println("// symbole: " + f.getName());
                out.println("// taille : " + f.getBody().getNumAddresses());
                DecompileResults r = dec.decompileFunction(f, 120, monitor);
                if (r != null && r.decompileCompleted()) {
                    out.println(r.getDecompiledFunction().getC());
                } else {
                    out.println("// ECHEC decompilation: " + (r == null ? "?" : r.getErrorMessage()));
                }
                out.flush();
            }
        }
        dec.dispose();
        println("OK: decompilation ecrite dans " + args[0]);
    }
}
