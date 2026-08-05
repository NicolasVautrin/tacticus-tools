// GhidraDumpFunctionSymbols.java -- extrait la table `<adresse VA>\t<symbole>` d'un programme.
//
// POURQUOI CE SCRIPT EXISTE (#482-r3)
// -----------------------------------
// `ghidra_symbols.py dump` produit la meme table, mais par ghidra-mcp : ~1 h 15 pour 154 176
// symboles, entierement passee en allers-retours HTTP pagines. Il exige en plus que le serveur
// serve CE projet -- or un serveur ne sert qu'UN projet a la fois, et il sert normalement le
// build COURANT. Un build ARCHIVE lui est donc inaccessible sans arreter le service de tout le
// monde.
//
// Ici, `analyzeHeadless -readOnly` ouvre le projet archive INDEPENDAMMENT du serveur (projets
// distincts, verrous distincts) et parcourt le FunctionManager en local. C'est ce qui rend
// archivable un build dont il ne reste que le projet Ghidra.
//
// CE SCRIPT NE NOMME RIEN. Il n'applique aucun symbole, n'ecrit pas dans le projet, et
// `-readOnly` le garantit : on ne modifie JAMAIS un projet dont le binaire d'origine a disparu.
// La FORME des noms est donc celle que l'applier a posee a l'epoque -- elle peut differer de la
// forme canonique `Namespace.Classe$$Membre` si le projet a ete symbolise par un outillage
// anterieur. Le script COMPTE les deux formes dans son en-tete pour que le lecteur le voie au
// lieu de le supposer : une table en notation pointee ne s'apparie PAS avec nos tables actuelles
// (incident du 2026-07-29 -- 0,43 % de symboles communs, qui imitait une reecriture du jeu).
//
// USAGE
//   analyzeHeadless <projectDir> <projectName> -process <binaire> -noanalysis -readOnly \
//     -scriptPath scripts/ghidra -postScript GhidraDumpFunctionSymbols.java <outFile> [<build>]
import ghidra.app.script.GhidraScript;
import ghidra.program.model.listing.Function;

import java.io.File;
import java.io.FileOutputStream;
import java.io.OutputStreamWriter;
import java.io.PrintWriter;
import java.nio.charset.StandardCharsets;

public class GhidraDumpFunctionSymbols extends GhidraScript {

    @Override
    public void run() throws Exception {
        String[] args = getScriptArgs();
        if (args.length < 1) {
            println("ERREUR: argument <outFile> manquant");
            return;
        }
        File out = new File(args[0]);
        if (out.getParentFile() != null) {
            out.getParentFile().mkdirs();
        }
        String build = args.length > 1 ? args[1] : "?";

        // Deux passes : la premiere COMPTE les formes, la seconde ecrit. Le compte doit tomber
        // dans l'EN-TETE (1re ligne) pour qu'un lecteur qui n'ouvre que le debut du fichier sache
        // deja s'il peut apparier cette table avec les autres.
        long total = 0, dollars = 0, placeholders = 0;
        for (Function f : currentProgram.getFunctionManager().getFunctions(true)) {
            total++;
            String n = f.getName();
            if (n.contains("$$")) {
                dollars++;
            }
            if (n.startsWith("FUN_")) {
                placeholders++;
            }
        }

        PrintWriter w = new PrintWriter(new OutputStreamWriter(
                new FileOutputStream(out), StandardCharsets.UTF_8));
        w.print("# build=" + build
                + "  source=analyzeHeadless(" + currentProgram.getName() + ")"
                + "  forme=<adresse VA hexa>\\t<symbole Ghidra verbatim>"
                + "  fonctions=" + total
                + "  avec$$=" + dollars
                + "  FUN_=" + placeholders
                + "  sha256=" + currentProgram.getExecutableSHA256()
                + "\n");
        for (Function f : currentProgram.getFunctionManager().getFunctions(true)) {
            w.print(Long.toHexString(f.getEntryPoint().getOffset()));
            w.print('\t');
            w.print(f.getName());
            w.print('\n');
        }
        w.close();
        println("OK: " + total + " fonctions (" + dollars + " en $$, " + placeholders
                + " FUN_) -> " + out);
    }
}
