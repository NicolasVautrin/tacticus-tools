"""Probe #480-r6 -- deux bundles sont-ils EQUIVALENTS malgre un deplacement de fichiers ?

POURQUOI PAS UN `sha256` NU -- c'est MESURE, pas suppose
--------------------------------------------------------
Le bundle produit par `frida-compile` (esbuild) ECRIT le chemin de chaque module, deux fois :
en commentaire de separation (`// hooks/<chemin>.ts`) et en cle de la fonction d'init
(`__esm({ "hooks/<chemin>.ts"() { ... } })`). Mesure du 2026-08-05 sur `dist/hooks.js` :
**226** chemins de module, dont **66** contenant `scratch`. Un `git mv` change donc le `sha256`
du bundle par CONSTRUCTION, sans qu'une seule instruction ait bouge.

Le `sha256` nu reste le bon invariant quand rien ne se DEPLACE : il a servi ici a etablir que
le build est reproductible bit-a-bit (le bundle reconstruit dans un worktree frais est identique
a celui de la session injectee). C'est pour le seul cas du DEPLACEMENT qu'il faut descendre d'un
cran.

L'INVARIANT, A TROIS NIVEAUX QUI SE RESSERRENT
----------------------------------------------
  N1. **CONTRAT RPC** -- l'ensemble des `rpc.<nom> =` exposes. C'est ce qu'un appelant VOIT.
      Un module perdu en route s'y lit immediatement.
  N2. **JEU DE MODULES** -- l'ensemble des noms de BASE des modules embarques. Un `git mv` ne
      change pas le nom d'un fichier ; le repertoire, oui. Si un module disparait du bundle
      (import casse, tree-shaking declenche par le deplacement), il manque ici.
  N3. **CORPS NORMALISE** -- le bundle entier, chaque chemin de module remplace par son nom de
      base, puis `sha256`. C'est le niveau le plus fort : il compare toutes les INSTRUCTIONS,
      l'ordre des modules, et jusqu'aux identifiants generes par esbuild.

Un invariant qui ne peut pas rougir ne vaut rien : `--casser <module>` mute une ligne du bundle
COURANT et exige que la comparaison passe au ROUGE. C'est la contre-epreuve, et elle est
executable.

Usage :
    python probe_480r6_bundle_equivalent.py --ref <hooks-REF.js> --neuf <dist/hooks.js>
    python probe_480r6_bundle_equivalent.py --ref A.js --neuf B.js --casser rpc
    python probe_480r6_bundle_equivalent.py --ref A.js --neuf B.js --casser module

Sortie ASCII stricte (console Windows cp1252).
"""
from __future__ import annotations

import argparse
import hashlib
import re
import sys
from pathlib import Path

# esbuild ecrit le chemin du module en commentaire de separation ET en cle de `__esm`.
MODULE_PATH_RE = re.compile(r"""(?:^//\s*|["'])((?:hooks|il2cpp|node_modules)[\w@/.\-]*\.\w+)"""
                            r"""(?=["']|\s*$)""", re.M)
# ⚠ Le lookbehind ne doit exclure qu'un caractere de MOT (`xrpc.foo`), JAMAIS le point : dans le
#   bundle la forme est `ctx.rpc.<nom> =`. Mesure du 2026-08-05 : avec `(?<![\w.])`, ce probe
#   rendait `ref=0 neuf=0` sur un bundle qui porte 325 affectations, et concluait VERT sur un
#   contrat VIDE -- un invariant qui ne mesure rien ne peut pas rougir. D'ou le garde ci-dessous.
RPC_DECL_RE = re.compile(r"""(?<![\w$])rpc\.([A-Za-z_$][\w$]*)\s*=(?!=)""")
# Un bundle de production expose forcement des dizaines de methodes. En dessous, c'est le
# CAPTEUR qui est casse, pas le contrat qui est vide -- et il doit le dire, pas verdir.
PLANCHER_RPC = 50


def lire(p: Path) -> str:
    return p.read_text(encoding="utf-8", errors="replace")


def chemins(txt: str) -> list[str]:
    return MODULE_PATH_RE.findall(txt)


def rpc_exposes(txt: str) -> set[str]:
    """Noms RPC ecrits dans le bundle. `rpc.exports` est l'API Frida qui PUBLIE la table,
    pas une entree de la table -- l'inclure ferait porter au contrat un nom qui n'en est pas."""
    return {n for n in RPC_DECL_RE.findall(txt) if n != "exports"}


def normalise(txt: str) -> str:
    """Chaque chemin de module -> son nom de BASE.

    Un `git mv` change le REPERTOIRE, jamais le nom de fichier : normaliser par le nom de base
    neutralise exactement la difference que le deplacement introduit, et RIEN d'autre. Un
    module renomme, disparu, reordonne ou dont une instruction change reste visible.
    """
    return MODULE_PATH_RE.sub(lambda m: m.group(0).replace(m.group(1), m.group(1).rsplit("/", 1)[-1]),
                              txt)


def sha(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8", "replace")).hexdigest().upper()


def casser(txt: str, mode: str) -> str:
    """Mutation VOLONTAIRE du bundle neuf, pour verifier que l'invariant sait rougir."""
    if mode == "rpc":
        # Retire UNE methode du contrat -- le cas « un module n'a pas suivi le deplacement ».
        m = RPC_DECL_RE.search(txt)
        if not m:
            raise SystemExit("[480r6] --casser rpc : aucun `rpc.<nom> =` dans le bundle")
        return txt[:m.start(1)] + "zzMutantRpc" + txt[m.end(1):]
    if mode == "module":
        # Renomme UN module -- le cas « un fichier a change de nom, pas seulement de dossier ».
        c = chemins(txt)
        if not c:
            raise SystemExit("[480r6] --casser module : aucun chemin de module")
        cible = c[len(c) // 2]
        base = cible.rsplit("/", 1)[-1]
        return txt.replace(cible, cible[: -len(base)] + "zz-mutant.ts")
    if mode == "corps":
        # Change UNE instruction sans toucher ni aux chemins ni aux RPC : N1 et N2 restent
        # verts, seul N3 doit rougir. C'est ce qui prouve que les trois niveaux ne sont pas
        # redondants.
        i = txt.find('"use strict";')
        if i < 0:
            raise SystemExit("[480r6] --casser corps : motif introuvable")
        return txt[:i] + '"use strict"; var zzMutant = 1;' + txt[i + len('"use strict";'):]
    raise SystemExit("[480r6] mode de cassure inconnu : %s" % mode)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--ref", required=True, type=Path, help="bundle de REFERENCE (avant)")
    ap.add_argument("--neuf", required=True, type=Path, help="bundle a comparer (apres)")
    ap.add_argument("--casser", choices=("rpc", "module", "corps"),
                    help="muter le bundle NEUF pour verifier que la comparaison rougit")
    a = ap.parse_args()

    for p in (a.ref, a.neuf):
        if not p.is_file():
            print("[480r6] %s ABSENT -- NON MESURE (le bundle est gitignore : le construire "
                  "d'abord)" % p)
            return 2

    tref, tneuf = lire(a.ref), lire(a.neuf)
    if a.casser:
        tneuf = casser(tneuf, a.casser)
        print("[480r6] CONTRE-EPREUVE : bundle neuf MUTE (--casser %s). La comparaison DOIT "
              "rougir." % a.casser)

    print("[480r6] ref  : %s  (%d o, %d chemins de module)"
          % (a.ref, len(tref), len(chemins(tref))))
    print("[480r6] neuf : %s  (%d o, %d chemins de module)"
          % (a.neuf, len(tneuf), len(chemins(tneuf))))
    print()

    rouges = 0

    # --- sha256 NU : informatif. Son inegalite ne prouve rien apres un deplacement. ---
    egal_nu = sha(tref) == sha(tneuf)
    print("[N0] sha256 NU               : %s" % ("IDENTIQUE" if egal_nu else "DIFFERENT"))
    print("     ref  = %s" % sha(tref))
    print("     neuf = %s" % sha(tneuf))
    print("     (informatif : un `git mv` le change PAR CONSTRUCTION -- le chemin de chaque")
    print("      module est ecrit dans la sortie. Ce n'est un invariant que SANS deplacement.)")
    print()

    # --- N1 : contrat RPC ---
    ra, rb = rpc_exposes(tref), rpc_exposes(tneuf)
    perdus, gagnes = sorted(ra - rb), sorted(rb - ra)
    print("[N1] CONTRAT RPC             : ref=%d  neuf=%d  perdus=%d  apparus=%d"
          % (len(ra), len(rb), len(perdus), len(gagnes)))
    if len(ra) < PLANCHER_RPC or len(rb) < PLANCHER_RPC:
        print("     ROUGE  moins de %d methodes vues -- c'est le CAPTEUR qui est casse, pas le"
              % PLANCHER_RPC)
        print("            contrat qui est vide. Un ensemble vide compare a un ensemble vide")
        print("            rend un OK qui ne prouve RIEN.")
        rouges += 1
    if perdus:
        print("     ROUGE  disparus du bundle : %s" % ", ".join(perdus))
        rouges += 1
    if gagnes:
        print("     ROUGE  apparus dans le bundle : %s" % ", ".join(gagnes))
        rouges += 1
    if not perdus and not gagnes:
        print("     OK     meme ensemble de methodes exposees")
    print()

    # --- N2 : jeu de modules (noms de base) ---
    ba = sorted(c.rsplit("/", 1)[-1] for c in chemins(tref))
    bb = sorted(c.rsplit("/", 1)[-1] for c in chemins(tneuf))
    print("[N2] JEU DE MODULES          : ref=%d  neuf=%d" % (len(ba), len(bb)))
    if ba != bb:
        sa, sb = set(ba), set(bb)
        print("     ROUGE  manquants : %s" % (sorted(sa - sb) or "(aucun)"))
        print("     ROUGE  en trop   : %s" % (sorted(sb - sa) or "(aucun)"))
        if sa == sb:
            print("     ROUGE  meme ensemble mais MULTIPLICITE differente (un module embarque "
                  "deux fois ?)")
        rouges += 1
    else:
        print("     OK     memes modules, memes multiplicites")
    print()

    # --- N3 : corps normalise ---
    na, nb = normalise(tref), normalise(tneuf)
    print("[N3] CORPS NORMALISE         : %s" % ("IDENTIQUE" if na == nb else "DIFFERENT"))
    print("     ref  = %s" % sha(na))
    print("     neuf = %s" % sha(nb))
    if na != nb:
        rouges += 1
        # Premiere divergence, en clair : sans elle le rouge n'est pas diagnostique.
        i = next((k for k in range(min(len(na), len(nb))) if na[k] != nb[k]), min(len(na), len(nb)))
        lig = na[:i].count("\n") + 1
        print("     ROUGE  1re divergence a l'offset %d (ligne ~%d du bundle normalise)" % (i, lig))
        print("            ref  ...%s..." % na[max(0, i - 60):i + 60].replace("\n", "\\n"))
        print("            neuf ...%s..." % nb[max(0, i - 60):i + 60].replace("\n", "\\n"))
    else:
        print("     OK     toutes les instructions, l'ordre des modules et les identifiants")
        print("            generes par esbuild sont identiques a la normalisation des chemins pres")
    print()

    if a.casser:
        if rouges:
            print("[480r6] CONTRE-EPREUVE OK -- la mutation a bien ete VUE (%d niveau(x) rouge)."
                  % rouges)
            return 0
        print("[480r6] CONTRE-EPREUVE ECHOUEE -- la mutation est passee INAPERCUE. L'invariant")
        print("        ne mord pas : ne pas s'en servir pour valider un deplacement.")
        return 1

    if rouges:
        print("[480r6] ROUGE -- les deux bundles ne sont PAS equivalents (%d niveau(x))." % rouges)
        return 1
    print("[480r6] OK -- bundles EQUIVALENTS : meme contrat RPC, memes modules, meme corps a la")
    print("        normalisation des chemins pres. Le deplacement n'a rien change d'observable.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
