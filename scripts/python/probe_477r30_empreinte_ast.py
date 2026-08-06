"""#477-r30 -- l'EMPREINTE AST : une tranche de CITATIONS n'a pas le droit de bouger du CODE.

    python scripts/python/probe_477r30_empreinte_ast.py [--base origin/master]

CE QUE CE PROBE TRANCHE
-----------------------
Corriger des slots d'interface cites dans des docstrings et des commentaires touche des
dizaines de fichiers du moteur. Rien, dans un diff de cette taille, ne distingue a l'oeil une
docstring reecrite d'une ligne de code deplacee -- et une relecture qui doit chercher ca sur
des centaines de lignes de prose ne le trouvera pas.

L'empreinte le tranche mecaniquement : pour chaque fichier Python modifie, on parse les DEUX
versions, on RETIRE les docstrings, et on compare les arbres. Un fichier qui ne devait porter
que des corrections de citation doit rendre des arbres IDENTIQUES.

CE QUI DIVERGE LEGITIMEMENT EST NOMME, JAMAIS TU
------------------------------------------------
Les fichiers dont le CODE a change dans la meme tranche (l'instrument de mesure et son cliquet)
sont DECLARES ici, un par un, avec la raison. Tout autre divergent est un ROUGE.

⚠ LES COMMENTAIRES NE SONT PAS DANS L'AST. Ce probe ne dit donc RIEN d'un commentaire modifie
-- et c'est voulu : c'est exactement la classe de modification qu'on revendique. Ce qu'il
garantit, c'est qu'aucune de ces modifications n'a EMPORTE du code avec elle.

⚠ IL ASSERTIONNE SON PROPRE NON-VIDE. Un perimetre vide rendrait « 0 divergent » et se lirait
comme un vert, alors qu'il n'aurait RIEN mesure.

ASCII only (console Windows cp1252).
"""
from __future__ import annotations

import argparse
import ast
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent

#: Les fichiers dont le CODE EXECUTABLE change legitimement dans cette tranche, et pourquoi.
#: Tout divergent hors de cette table est un ROUGE -- la liste n'est pas une echappatoire,
#: c'est une DECLARATION relue avec le diff.
DIVERGENTS_ATTENDUS = {
    "scripts/python/probe_477r25_slots_autres_interfaces.py":
        "l'instrument : appariement du couple (slot, nom) sur une FENETRE de lignes",
    "scripts/python/tests/engine/test_477r25_slots_autres_interfaces_offline.py":
        "le cliquet de la fenetre : 7 etages neufs (3bis)",
    "scripts/python/probe_477r30_empreinte_ast.py":
        "ce probe lui-meme, qui n'existait pas avant la tranche",
}


class _SansDocstring(ast.NodeTransformer):
    """Retire la docstring d'un module, d'une classe et d'une fonction.

    ⚠ On retire le NOEUD, pas seulement sa valeur : remplacer la chaine par `None` laisserait
    un `Expr` dont la presence depend de l'existence d'une docstring, donc l'empreinte
    changerait quand meme si on en AJOUTAIT une -- ce qui n'est pas du code.
    """

    def _nettoyer(self, node):
        corps = getattr(node, "body", None)
        if (corps and isinstance(corps[0], ast.Expr)
                and isinstance(corps[0].value, ast.Constant)
                and isinstance(corps[0].value.value, str)):
            node.body = corps[1:] or [ast.Pass()]
        return self.generic_visit(node)

    visit_Module = _nettoyer
    visit_ClassDef = _nettoyer
    visit_FunctionDef = _nettoyer
    visit_AsyncFunctionDef = _nettoyer


def empreinte(source: str) -> str:
    arbre = _SansDocstring().visit(ast.parse(source))
    ast.fix_missing_locations(arbre)
    #: `include_attributes=False` : les numeros de ligne BOUGENT des qu'une docstring gagne
    #: ou perd une ligne. Les inclure ferait rougir toute la tranche, pour rien.
    return ast.dump(arbre, annotate_fields=True, include_attributes=False)


def _git(*args: str) -> tuple[int, str]:
    try:
        p = subprocess.run(["git", "-C", str(REPO), *args], capture_output=True, text=True,
                           timeout=60)
    except (OSError, subprocess.SubprocessError) as exc:                # noqa: BLE001
        raise SystemExit("PAS MESURE : git muet (%s) -- une empreinte qu'on ne peut pas "
                         "calculer ne rend pas un vert." % exc)
    return p.returncode, p.stdout


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base", default="origin/master",
                    help="la revision TEMOIN (defaut : origin/master)")
    args = ap.parse_args()

    print("=== #477-r30 -- empreinte AST (docstrings retirees) vs %s ===" % args.base)
    #: ⚠ LE TEMOIN DOIT ETRE UN ANCETRE DE `HEAD`, et ce cran n'est pas cosmetique : mesure du
    #: 2026-08-06, un `origin/master` qui avait avance de quelques PR faisait rendre
    #: 17 divergents NON DECLARES -- tous etant le travail des AUTRES, pas le notre. Une
    #: empreinte qui accuse le voisin fait renoncer a un controle pourtant juste. On REFUSE,
    #: en disant quoi faire (`git rebase origin/master`), plutot que de rendre un rouge faux.
    rc_anc, _ = _git("merge-base", "--is-ancestor", args.base, "HEAD")
    if rc_anc != 0:
        raise SystemExit(
            "PAS MESURE : `%s` n'est PAS un ancetre de HEAD -- le diff contiendrait le travail\n"
            "  d'autres branches, et chacun de leurs fichiers sortirait en « NON DECLARE ».\n"
            "  Rebaser (`git fetch origin && git rebase origin/master`) puis rejouer, ou\n"
            "  passer explicitement `--base $(git merge-base HEAD %s)`." % (args.base, args.base))
    rc, sortie = _git("diff", "--name-only", args.base, "--", "*.py")
    if rc != 0:
        raise SystemExit("PAS MESURE : `git diff --name-only %s` a echoue (rc=%d)."
                         % (args.base, rc))
    fichiers = [f.strip() for f in sortie.splitlines() if f.strip().endswith(".py")]
    if not fichiers:
        raise SystemExit("PAS MESURE : AUCUN fichier Python ne differe de %s. Un perimetre "
                         "vide rend « 0 divergent » et se lirait comme un vert." % args.base)

    identiques: list[str] = []
    divergents: list[tuple[str, str]] = []
    neufs: list[str] = []
    illisibles: list[tuple[str, str]] = []
    for rel in fichiers:
        courant = REPO / rel
        rc_base, base_src = _git("show", "%s:%s" % (args.base, rel))
        if rc_base != 0:
            neufs.append(rel)
            continue
        if not courant.is_file():
            divergents.append((rel, "SUPPRIME"))
            continue
        try:
            a = empreinte(base_src)
            b = empreinte(courant.read_text(encoding="utf-8"))
        except (SyntaxError, OSError, UnicodeDecodeError) as exc:       # noqa: BLE001
            illisibles.append((rel, str(exc)))
            continue
        (identiques if a == b else divergents).append(rel if a == b else (rel, "AST DIFFERENT"))

    print("  %d fichier(s) Python compare(s)" % len(fichiers))
    print("  %d identique(s) AST -- seules des docstrings/commentaires ont bouge"
          % len(identiques))
    print("  %d fichier(s) NEUF(S) (absent(s) du temoin) : %s"
          % (len(neufs), ", ".join(neufs) or "-"))
    for rel, quoi in illisibles:
        print("  ILLISIBLE : %s (%s)" % (rel, quoi))

    inattendus = [r for r, _ in divergents if r not in DIVERGENTS_ATTENDUS]
    print("  %d divergent(s), dont %d DECLARE(S) :" % (len(divergents), len(divergents)
                                                       - len(inattendus)))
    for rel, quoi in divergents:
        motif = DIVERGENTS_ATTENDUS.get(rel)
        print("      %-70s %s -- %s" % (rel, quoi, motif or "*** NON DECLARE ***"))
    for rel in neufs:
        if rel not in DIVERGENTS_ATTENDUS:
            inattendus.append(rel)

    rouge = bool(inattendus or illisibles)
    print()
    print("VERDICT : %s" % ("ROUGE" if rouge else "VERT"))
    if rouge:
        print("  %d fichier(s) dont le CODE a bouge sans etre declare : %s"
              % (len(inattendus), ", ".join(inattendus)))
    return 1 if rouge else 0


if __name__ == "__main__":
    sys.exit(main())
