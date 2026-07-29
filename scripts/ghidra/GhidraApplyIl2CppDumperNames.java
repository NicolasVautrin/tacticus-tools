// Ghidra headless script : COMPLETE la couche Frida avec les noms qu'elle ne peut pas produire.
//
// POURQUOI CE SCRIPT EXISTE (#259)
// --------------------------------
// `GhidraApplyIl2CppSymbols.java` (chaine Frida) fait autorite sur les METADONNEES et nomme la
// quasi-totalite du binaire. Mais il y a une classe de corps qu'il ne PEUT PAS nommer : les
// generiques PLEINEMENT PARTAGES (`__Il2CppFullySharedGenericType`). Les metadonnees IL2CPP lues
// par Frida ne les exposent pas comme methodes distinctes -- mesure 2026-07-29 :
// `frida/methods.tsv` en contient ZERO sur les DEUX builds. Il2CppDumper, lui, les reconstruit :
// 21 552 occurrences dans le `script.json` de `rnca9r7q6c`.
//
// C'est un COMPLEMENT, pas un concurrent : ce script ne renomme QUE les fonctions encore appelees
// `FUN_*`. Il ne peut donc pas ecraser un nom pose par la chaine Frida. ORDRE OBLIGATOIRE :
// `GhidraApplyIl2CppSymbols.java` D'ABORD, celui-ci ENSUITE.
//
// HISTOIRE -- a lire avant de le supprimer a nouveau. Son ancetre
// `GhidraApplyIl2CppNamesWin.java` a ete supprime le 2026-07-25 (`8e591496`, « suppression du
// legacy ») au profit de la chaine Frida. Le projet Ghidra en place etait DEJA symbolise par lui,
// et sa table a ete versionnee telle quelle : personne n'a vu le trou. Il a fallu la
// re-symbolisation complete du 2026-07-29 pour reveler que 4 882 symboles avaient disparu --
// dont les DEUX qui portent l'instrument de decomposition par etage
// (`ComparablePlaybooku003C__Il2CppFullySharedGenericTypeu003E$$CalculateActionUtility` et
// `$$CalculateUtilityFromTilePrediction`). Remplacer un maillon sans re-jouer son aval laisse
// l'ancienne sortie faire foi jusqu'a la regeneration suivante.
//
// ⚠ NE JAMAIS ECRIRE UNE SEQUENCE backslash-u DANS CE FICHIER, MEME EN COMMENTAIRE. Le lexer Java
// resout les echappements Unicode AVANT de parser -- commentaires COMPRIS. Une sequence
// backslash-u suivie de non-hexadecimal est un « illegal unicode escape » et le fichier entier ne
// compile plus. Mesure du 2026-07-29 : deux lignes de COMMENTAIRE ont suffi a rendre ce script
// introuvable pour Ghidra, et le message d'erreur remonte etait `ClassNotFoundException` -- il ne
// pointe pas du tout la vraie cause.
//
// LA FORME `u003C` VIENT D'ICI, et ce n'est pas un accident : `parseString` consomme le `\` d'un
// `backslash-u003C` JSON et recopie le reste tel quel. C'est ce qui produit
// `Classe.u003CMethodeu003Ed__8$$MoveNext` -- la forme EXACTE que citent le code et les fiches du
// depot. Ne pas « corriger » cet echappement : c'est le contrat de citation.
//
// ENTREE : logs/il2cppdumper/<BUILD>/script.json, ou <BUILD> est lu dans data/symbols/CURRENT.
//   Produit par : tools/Il2CppDumper_v39/Il2CppDumper/bin/Release/net8.0/Il2CppDumper.exe
//                 <GameAssembly.dll> <global-metadata.dat> logs/il2cppdumper/<BUILD>
//   (le binaire `Il2CppDumper_net6` NE MARCHE PAS : metadata v39 non supportee. Et son
//    `config.json` porte `RequireAnyKey: true`, qui BLOQUE tout run non interactif.)
//
// @category IL2CPP

import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.FunctionManager;
import ghidra.program.model.symbol.SourceType;

import java.io.*;
import java.nio.file.*;

public class GhidraApplyIl2CppDumperNames extends GhidraScript {

    private static final String REPO = "C:/Users/nicolasv/tacticus-tools";

    // GARDE DE BUILD. Le `script.json` ne porte AUCUNE estampille : rien, dans le fichier, ne dit
    // de quel build il vient. Si on en applique un du MAUVAIS build, chaque adresse tombe a cote
    // et on renomme du code au hasard -- silencieusement, puisque `setName` reussit toujours.
    // Le signal exploitable est le taux d'adresses qui ne tombent sur AUCUNE fonction : sur le bon
    // build il est faible (quelques corps que Ghidra n'a pas decoupes) ; sur le mauvais il explose.
    // On refuse au-dela de ce seuil PLUTOT que de produire une table plausible et fausse.
    private static final double MAX_NOTFOUND_RATIO = 0.25;

    @Override
    protected void run() throws Exception {
        String build = new String(Files.readAllBytes(
                Paths.get(REPO, "data/symbols/CURRENT"))).trim();
        Path scriptJson = Paths.get(REPO, "logs/il2cppdumper", build, "script.json");
        println("build (data/symbols/CURRENT) = " + build);
        println("entree = " + scriptJson);
        if (!Files.isRegularFile(scriptJson)) {
            println("ABANDON : " + scriptJson + " introuvable. Lancer Il2CppDumper d'abord.");
            return;
        }

        Address base = currentProgram.getImageBase();
        FunctionManager funcMgr = currentProgram.getFunctionManager();

        String json = new String(Files.readAllBytes(scriptJson));
        int idx = json.indexOf("\"ScriptMethod\"");
        if (idx < 0) { println("ABANDON : tableau ScriptMethod absent"); return; }
        idx = json.indexOf('[', idx);
        if (idx < 0) { println("ABANDON : crochet ouvrant de ScriptMethod absent"); return; }

        int applied = 0, notFound = 0, alreadyNamed = 0, refused = 0;
        long lastReport = System.currentTimeMillis();

        int p = idx + 1;
        int len = json.length();
        while (p < len) {
            char c = json.charAt(p);
            if (c == ']') break;
            if (c != '{') { p++; continue; }
            int objEnd = findMatching(json, p, '{', '}');
            if (objEnd < 0) break;
            String obj = json.substring(p, objEnd + 1);
            p = objEnd + 1;

            long addr = parseLong(obj, "\"Address\":");
            String name = parseString(obj, "\"Name\":");
            if (addr < 0 || name == null) continue;

            Function fn = funcMgr.getFunctionContaining(base.add(addr));
            if (fn == null) { notFound++; continue; }
            // LA regle qui fait de ce script un COMPLEMENT : on ne touche QUE l'anonyme.
            if (!fn.getName().startsWith("FUN_")) { alreadyNamed++; continue; }
            try {
                fn.setName(sanitize(name), SourceType.USER_DEFINED);
                applied++;
            } catch (Exception e) {
                refused++;      // nom en double, caractere refuse... : on passe, on ne masque pas
            }

            if (System.currentTimeMillis() - lastReport > 5000) {
                println(String.format("  applied=%d notFound=%d alreadyNamed=%d refused=%d",
                        applied, notFound, alreadyNamed, refused));
                lastReport = System.currentTimeMillis();
            }
        }

        int total = applied + notFound + alreadyNamed + refused;
        double ratio = total > 0 ? ((double) notFound) / total : 0.0;
        println(String.format("Termine. applied=%d notFound=%d alreadyNamed=%d refused=%d "
                + "(notFound = %.1f%% du total)", applied, notFound, alreadyNamed, refused,
                ratio * 100.0));
        if (ratio > MAX_NOTFOUND_RATIO) {
            println(String.format("!! ALERTE : %.1f%% des adresses ne tombent sur AUCUNE fonction "
                    + "(seuil %.0f%%). Le script.json vient probablement d'un AUTRE build que "
                    + "celui charge -- les noms poses sont a jeter, re-dumper puis recommencer.",
                    ratio * 100.0, MAX_NOTFOUND_RATIO * 100.0));
        }
    }

    private static int findMatching(String s, int from, char open, char close) {
        int depth = 0;
        boolean inStr = false, esc = false;
        for (int i = from; i < s.length(); i++) {
            char c = s.charAt(i);
            if (esc) { esc = false; continue; }
            if (c == '\\') { esc = true; continue; }
            if (c == '"') { inStr = !inStr; continue; }
            if (inStr) continue;
            if (c == open) depth++;
            else if (c == close) { depth--; if (depth == 0) return i; }
        }
        return -1;
    }

    private static long parseLong(String obj, String key) {
        int k = obj.indexOf(key);
        if (k < 0) return -1;
        int start = k + key.length();
        while (start < obj.length() && Character.isWhitespace(obj.charAt(start))) start++;
        int end = start;
        while (end < obj.length()
                && (Character.isDigit(obj.charAt(end)) || obj.charAt(end) == '-')) end++;
        try { return Long.parseLong(obj.substring(start, end)); }
        catch (NumberFormatException e) { return -1; }
    }

    /** ⚠ Consomme le `\` d'une sequence `d'echappement JSON` et recopie le reste VERBATIM : `backslash-u003C` -> `u003C`.
     *  C'est VOULU -- cf. l'en-tete, c'est ce qui produit la forme de citation du depot. */
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

    /** On GARDE `$`, `<` et `>` : ils font partie des noms generiques/imbriques et Ghidra les
     *  tolere. Seuls les blancs deviennent `_`. */
    private static String sanitize(String s) {
        return s.replace(' ', '_').replace('\t', '_').replace('\n', '_');
    }
}
