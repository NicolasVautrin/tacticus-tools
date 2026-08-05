// GhidraDumpCodeBytes.java -- extrait les OCTETS des blocs memoire d'un programme Ghidra.
//
// POURQUOI CE SCRIPT EXISTE
// -------------------------
// L'empreinte structurelle par fonction (#482) doit comparer les CORPS de deux builds. Le
// build courant a son `GameAssembly.dll` sur disque, donc lisible par pefile. Un build
// ARCHIVE, lui, n'existe plus que sous forme de projet Ghidra (`ghidra-projects/ghidra_<hash>/`)
// -- le `.dll` d'origine a ete efface par la mise a jour du jeu. Ce script rend ses octets.
//
// SYMETRIE DU PIPELINE -- c'est la propriete qui compte. Le blob produit ici est traite par
// `fingerprint_functions.py` EXACTEMENT comme le `.text` extrait d'un PE : meme desassemblage,
// meme normalisation, meme hash. Un ecart mesure entre deux builds ne peut donc pas venir
// d'une difference de chaine d'extraction.
//
// Les octets rendus sont ceux du bloc memoire tel que Ghidra l'a charge. Pour un PE charge a
// son ImageBase preferee (0x180000000, ce qui est le cas de tous nos builds), aucune relocation
// n'a ete appliquee : ils sont identiques aux octets du fichier. Le script ECRIT l'ImageBase
// effective dans le meta pour que le lecteur puisse le VERIFIER au lieu de le supposer.
//
// USAGE (toujours en -readOnly : on ne modifie jamais un projet archive)
//   analyzeHeadless <projectDir> <projectName> -process GameAssembly.dll -noanalysis -readOnly \
//     -scriptPath scripts/ghidra -postScript GhidraDumpCodeBytes.java <outDir>
//
// SORTIES dans <outDir> :
//   blocks.meta            TSV : nom, start VA, taille, r/w/x, initialise, fichier
//   block_<nom>.bin        octets bruts du bloc (seulement les blocs EXECUTABLES initialises)
//   image.meta             TSV : imageBase, langage, compilateur, executablePath, sha256 connu
import ghidra.app.script.GhidraScript;
import ghidra.program.model.mem.MemoryBlock;

import java.io.BufferedOutputStream;
import java.io.File;
import java.io.FileOutputStream;
import java.io.OutputStreamWriter;
import java.io.PrintWriter;
import java.nio.charset.StandardCharsets;

public class GhidraDumpCodeBytes extends GhidraScript {

    /** Taille de lecture par morceau : borne la memoire quel que soit le bloc. */
    private static final int CHUNK = 1 << 20;

    @Override
    public void run() throws Exception {
        String[] args = getScriptArgs();
        if (args.length < 1) {
            println("ERREUR: argument <outDir> manquant");
            return;
        }
        File outDir = new File(args[0]);
        if (!outDir.exists() && !outDir.mkdirs()) {
            println("ERREUR: impossible de creer " + outDir);
            return;
        }

        // -- image.meta : de quoi VERIFIER, cote lecteur, que le blob est comparable.
        PrintWriter img = newWriter(new File(outDir, "image.meta"));
        img.println("imageBase\t" + currentProgram.getImageBase());
        img.println("language\t" + currentProgram.getLanguageID());
        img.println("compiler\t" + currentProgram.getCompilerSpec().getCompilerSpecID());
        img.println("executablePath\t" + currentProgram.getExecutablePath());
        img.println("executableFormat\t" + currentProgram.getExecutableFormat());
        img.println("executableSHA256\t" + currentProgram.getExecutableSHA256());
        img.println("functionCount\t" + currentProgram.getFunctionManager().getFunctionCount());
        img.close();

        PrintWriter meta = newWriter(new File(outDir, "blocks.meta"));
        meta.println("#nom\tstartVA\ttaille\tr\tw\tx\tinitialise\tfichier");

        int dumped = 0;
        long totalBytes = 0;
        for (MemoryBlock b : currentProgram.getMemory().getBlocks()) {
            String safe = b.getName().replaceAll("[^A-Za-z0-9_.-]", "_");
            boolean take = b.isInitialized() && b.isExecute();
            String fileName = "";
            if (take) {
                fileName = "block_" + safe + ".bin";
                long n = writeBlock(b, new File(outDir, fileName));
                totalBytes += n;
                dumped++;
            }
            meta.println(String.format("%s\t%s\t%d\t%b\t%b\t%b\t%b\t%s",
                    safe, b.getStart(), b.getSize(), b.isRead(), b.isWrite(),
                    b.isExecute(), b.isInitialized(), fileName));
        }
        meta.close();
        println("OK: " + dumped + " bloc(s) executable(s) ecrit(s), " + totalBytes + " octets -> " + outDir);
    }

    /** Ecrit les octets d'un bloc par morceaux de CHUNK. Rend le nombre d'octets ecrits. */
    private long writeBlock(MemoryBlock b, File dest) throws Exception {
        byte[] buf = new byte[CHUNK];
        long remaining = b.getSize();
        long offset = 0;
        try (BufferedOutputStream out = new BufferedOutputStream(new FileOutputStream(dest), 1 << 16)) {
            while (remaining > 0) {
                int want = (int) Math.min(CHUNK, remaining);
                int got = b.getBytes(b.getStart().add(offset), buf, 0, want);
                if (got <= 0) {
                    break;
                }
                out.write(buf, 0, got);
                offset += got;
                remaining -= got;
            }
        }
        return offset;
    }

    private PrintWriter newWriter(File f) throws Exception {
        return new PrintWriter(new OutputStreamWriter(new FileOutputStream(f), StandardCharsets.UTF_8));
    }
}
