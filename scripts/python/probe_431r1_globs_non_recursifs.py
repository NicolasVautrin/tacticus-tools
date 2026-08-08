#!/usr/bin/env python3
"""#431-r1 -- un `**` passe a un matcher qui ne le DEVELOPPE PAS : le cliquet du piege de langage.

LE GISEMENT, ET POURQUOI IL N'A LAISSE AUCUNE TRACE
----------------------------------------------------
`PurePath.match` ne developpe PAS `**` : il le lit comme UN segment, et il matche depuis la
DROITE. `Path("scripts/python/engine/x.py").match("scripts/**/*.py")` rend donc `False`, sans
erreur, sans avertissement, sans que rien ne distingue « ce fichier ne correspond pas » de
« ce motif ne sait pas l'exprimer ». C'est exactement ce qui a rendu `probe_431` VERT sur
**967** fichiers versionnes (#458) -- dont l'INTEGRALITE de `scripts/python/engine/**` et de
`scripts/python/tests/**` -- pendant que son denominateur imprime avait l'air d'une couverture.

Le trou etait BILATERAL, et c'est ce qui le rend impossible a corriger de memoire :
  * TROP PROFOND -- `**` ne vaut qu'UN segment, donc rien au-dela de la profondeur 3 ;
  * PAS ASSEZ PROFOND -- `**/` exige un segment, donc `frida/host/router.ts` et
    `frida/hooks/main.ts` (la racine meme du glob) etaient dehors eux aussi.

DEUX AUTRES MATCHERS PARTAGENT LE VICE, ET AUCUN NE LEVE
---------------------------------------------------------
  * `glob.glob(motif)` SANS `recursive=True` : `**` y degenere en `*` -- silencieusement, la
    signature accepte le motif dans les deux cas ;
  * `fnmatch(nom, motif)` : `*` y matche `/`, donc `**/` n'a pas de sens et exige quand meme
    un `/` -- moitie basse du meme trou.

`Path.glob` / `Path.rglob` et `PurePath.full_match` (3.13), eux, DEVELOPPENT `**` : ils ne
sont pas dans le perimetre, et les compter serait du bruit.

CE QUE CE CLIQUET TIENT, ET CE QU'IL NE PRETEND PAS TENIR
-----------------------------------------------------------
Il tient l'invariant << aucun motif recursif ne part vers un matcher non recursif >>. Il ne
juge PAS la justesse d'un glob correct, ni la pertinence d'un perimetre : un motif exact peut
rester faux, et c'est l'affaire du cliquet qui le consomme.

Mesure d'ouverture (2026-08-08, sur `b3e80f94`) : **0** faute dans 2 083 `.py` versionnes --
le gisement de #431-r1 etait DEJA ferme par #458, et le balayage transverse que #431-r1
demandait ne rend rien non plus. Ce cliquet ne repare donc rien : il empeche le retour, ce
qu'un balayage ponctuel ne peut pas faire.

    python probe_431r1_globs_non_recursifs.py            # ventilation
    python probe_431r1_globs_non_recursifs.py --cliquet  # rc 1 s'il reste une faute

ASCII only (console Windows cp1252).
"""
from __future__ import annotations

import argparse
import ast
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

#: Ce qui doit changer pour que ce cliquet puisse changer d'avis.
#:
#: Le perimetre est `git ls-files` restreint aux `.py` : n'importe lequel d'entre eux peut
#: introduire la faute, et aucun sous-ensemble de chemins ne l'anticipe. `build: False` est
#: MESURE et non suppose -- le critere est purement syntaxique (AST), il ne lit ni le binaire
#: du jeu, ni `data/symbols/`, ni aucun artefact date.
DECLENCHEUR = {
    "chemins": ("**/*.py",),
    "build": False,
    "toujours": False,
    "raison": "Le critere est syntaxique et porte sur TOUT `.py` versionne : la faute (un `**` "
              "passe a `PurePath.match`, `fnmatch` ou `glob.glob` non recursif) peut naitre "
              "dans n'importe lequel, y compris un fichier neuf.",
}

EXCLUS = (".claude/worktrees/", "node_modules/", "frida/dist/")

#: Matchers qui NE developpent PAS `**`. `full_match`, `glob` et `rglob` en sont absents parce
#: qu'ils le developpent : les inclure produirait du bruit, pas de la couverture.
METH_NON_RECURSIVE = ("match",)
FN_FNMATCH = ("fnmatch", "fnmatchcase")
FN_GLOB = ("glob", "iglob")

#: Le litteral doit etre un GLOB DE CHEMIN, pas un texte qui contient deux etoiles. Sans ce
#: discriminant, tout markdown gras (`**PORTE**`) entrerait : mesure du balayage d'ouverture --
#: 531 litteraux `.py` contiennent `**`, dont 495 sont du markdown genere.
def est_glob_recursif(v: str) -> bool:
    return "**" in v and ("/" in v or v.startswith("*."))


class _Index:
    """Les noeuds utiles du fichier, en UN parcours : appels, noms lies a `re.compile`, et les
    appels NIES par un `assert not` (une contre-epreuve n'est pas une resolution)."""

    __slots__ = ("appels", "regex_noms", "contre_epreuves", "parse_ok")

    def __init__(self, tree: ast.AST):
        self.appels: list = []
        self.regex_noms: set = set()
        self.contre_epreuves: set = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                self.appels.append(node)
            elif isinstance(node, ast.Assert):
                t = node.test
                if isinstance(t, ast.UnaryOp) and isinstance(t.op, ast.Not) \
                        and isinstance(t.operand, ast.Call):
                    self.contre_epreuves.add(id(t.operand))
            if isinstance(node, (ast.Assign, ast.AnnAssign)):
                val = node.value
                if isinstance(val, ast.Call) and isinstance(val.func, ast.Attribute) \
                        and val.func.attr == "compile" \
                        and getattr(val.func.value, "id", "") == "re":
                    cibles = (node.targets if isinstance(node, ast.Assign) else [node.target])
                    for c in cibles:
                        if isinstance(c, ast.Name):
                            self.regex_noms.add(c.id)


def _recepteur(f: ast.Attribute) -> str:
    b = f.value
    if isinstance(b, ast.Name):
        return b.id
    if isinstance(b, ast.Attribute):
        return "%s.%s" % (getattr(b.value, "id", "?"), b.attr)
    if isinstance(b, ast.Call):
        g = b.func
        return (g.attr if isinstance(g, ast.Attribute) else getattr(g, "id", "?")) + "(...)"
    return "<expr>"


def analyser(rel: str, source: str) -> list[tuple[int, str, str, str]]:
    """[(ligne, famille, recepteur, motif)] des `**` qui partent vers un matcher non recursif.

    `source` est parse -- un `SyntaxError` remonte a l'appelant, qui doit le REMONTER et non
    l'avaler : un fichier non lu n'est pas un fichier propre (meme argument que `probe_431`).
    """
    idx = _Index(ast.parse(source, filename=rel))
    out: list[tuple[int, str, str, str]] = []
    for node in idx.appels:
        if id(node) in idx.contre_epreuves:
            continue                     # `assert not X.match(...)` : c'est le TEMOIN du vice
        f = node.func
        args = list(node.args)
        kw = {k.arg: k.value for k in node.keywords}

        if isinstance(f, ast.Attribute) and f.attr in METH_NON_RECURSIVE and args:
            recv = _recepteur(f)
            a0 = args[0]
            if recv not in idx.regex_noms and recv != "re" \
                    and isinstance(a0, ast.Constant) and isinstance(a0.value, str) \
                    and est_glob_recursif(a0.value):
                out.append((node.lineno, "PurePath.match", recv, a0.value))
            continue

        nom = f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", "")
        base = getattr(f.value, "id", "") if isinstance(f, ast.Attribute) else ""

        if nom in FN_GLOB and (base in ("glob", "") or base == "glob"):
            # `glob.glob(m)` / `iglob(m)` : `**` degenere en `*` sans `recursive=True`
            rec = kw.get("recursive")
            recursif = isinstance(rec, ast.Constant) and rec.value is True
            for a in args[:1]:
                if isinstance(a, ast.Constant) and isinstance(a.value, str) \
                        and est_glob_recursif(a.value) and not recursif:
                    out.append((node.lineno, "glob sans recursive=True", base or nom, a.value))
            continue

        if nom in FN_FNMATCH:
            for a in args[1:2]:
                if isinstance(a, ast.Constant) and isinstance(a.value, str) \
                        and est_glob_recursif(a.value):
                    out.append((node.lineno, "fnmatch", base or nom, a.value))
        elif nom == "filter" and base == "fnmatch":
            for a in args[1:2]:
                if isinstance(a, ast.Constant) and isinstance(a.value, str) \
                        and est_glob_recursif(a.value):
                    out.append((node.lineno, "fnmatch.filter", base, a.value))
    return out


# ------------------------------------------------------------------ PREUVE DE MORSURE (#421)
#
# Le cliquet PROUVE qu'il mord dans le MEME processus que la conformite. Les sources ci-dessous
# sont des CHAINES : elles ne sont jamais des appels dans CE fichier, donc le cliquet ne rougit
# pas sur sa propre preuve -- et l'exemption est structurelle, pas une allowlist.
MUTANTS = (
    ("Path.match avec ** -- LA faute de #458",
     "from pathlib import Path\nok = Path(rel).match('scripts/**/*.py')\n", 1),
    ("glob.glob avec ** sans recursive",
     "import glob\nfs = glob.glob('scripts/**/*.py')\n", 1),
    ("glob.glob avec ** ET recursive=True -- CORRECT",
     "import glob\nfs = glob.glob('scripts/**/*.py', recursive=True)\n", 0),
    ("fnmatch avec **",
     "from fnmatch import fnmatch\nok = fnmatch(rel, 'scripts/**/*.py')\n", 1),
    ("rglob -- developpe ** par construction, hors perimetre",
     "fs = list(root.rglob('*.py'))\n", 0),
    ("full_match (3.13) -- developpe **",
     "ok = Path(rel).full_match('scripts/**/*.py')\n", 0),
    ("markdown gras -- ce n'est pas un glob",
     "lignes.append('- **PORTE** : %d\\n')\n", 0),
    ("regex compile puis .match sur un SUJET",
     "import re\nRX = re.compile('x')\nok = RX.match('a/**/b')\n", 0),
    ("contre-epreuve `assert not` -- le TEMOIN du vice, pas le vice",
     "from pathlib import Path\nassert not Path(rel).match('scripts/**/*.py')\n", 0),
    ("glob correct sans ** -- rien a signaler",
     "import glob\nfs = glob.glob('data/symbols/*/BUILD')\n", 0),
)


def etape_morsure() -> list[str]:
    ecarts = []
    for titre, src, attendu in MUTANTS:
        obtenu = len(analyser("<mutant>", src))
        if obtenu != attendu:
            ecarts.append("%s : attendu %d, obtenu %d" % (titre, attendu, obtenu))
    return ecarts


def tracked_py() -> list[str]:
    r = subprocess.run(["git", "ls-files", "-z"], cwd=str(REPO),
                       capture_output=True, text=True, timeout=120)
    if r.returncode != 0:
        raise SystemExit("git ls-files a echoue : %s" % (r.stderr or "").strip())
    return [p for p in r.stdout.split("\0")
            if p.endswith(".py") and not p.startswith(EXCLUS)]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0],
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cliquet", action="store_true",
                    help="rc 1 s'il reste un `**` vers un matcher non recursif")
    args = ap.parse_args()

    print("=== (0) PREUVE DE MORSURE (le cliquet voit-il son gisement ?) ===")
    ecarts = etape_morsure()
    print("mutants joues : %d" % len(MUTANTS))
    if ecarts:
        for e in ecarts:
            print("  !! %s" % e)
    else:
        print("  les %d cas discriminent : %d faute(s) attendue(s), autant obtenues"
              % (len(MUTANTS), sum(a for _t, _s, a in MUTANTS)))
    print("")

    fichiers = tracked_py()
    fautes: list[tuple[str, int, str, str, str]] = []
    non_parses: list[tuple[str, str]] = []
    for rel in fichiers:
        try:
            src = (REPO / rel).read_text(encoding="utf-8", errors="replace")
            for ln, fam, recv, motif in analyser(rel, src):
                fautes.append((rel, ln, fam, recv, motif))
        except SyntaxError as exc:
            non_parses.append((rel, str(exc)[:90]))
        except OSError as exc:
            non_parses.append((rel, str(exc)[:90]))

    print("=== (1) PERIMETRE ET CONFORMITE ===")
    print("fichiers .py versionnes balayes : %d" % len(fichiers))
    print("fautes (`**` -> matcher non recursif) : %d" % len(fautes))
    if non_parses:
        print("  !! %d fichier(s) NON PARSES -- non mesures, pas 'propres' :" % len(non_parses))
        for rel, exc in non_parses:
            print("     %s : %s" % (rel, exc))
    for rel, ln, fam, recv, motif in sorted(fautes):
        print("    %s:%d  [%s]  %s.match/%s -> %r" % (rel, ln, fam, recv, fam, motif))
    print("")

    if args.cliquet:
        ko = len(ecarts) + len(fautes) + len(non_parses)
        if ecarts:
            print("CLIQUET ROUGE : la preuve de morsure a bouge -- le critere ne discrimine")
            print("  plus ce qu'il annonce. Reparer l'analyseur, jamais le mutant.")
        if non_parses:
            print("CLIQUET ROUGE : %d fichier(s) non parses -- ils ne sont PAS mesures."
                  % len(non_parses))
        if fautes:
            print("CLIQUET ROUGE : %d motif(s) recursif(s) vers un matcher qui ne developpe"
                  " PAS `**`." % len(fautes))
            print("  `PurePath.match` lit `**` comme UN segment et matche depuis la DROITE ;")
            print("  `glob.glob` sans `recursive=True` le degrade en `*` ; `fnmatch` fait")
            print("  matcher `*` a travers les `/`. Aucun ne leve. Remplacer par :")
            print("      Path.rglob / glob.glob(..., recursive=True) / un glob->regex explicite")
            print("      (cf. `declencheur_cliquet._regex`, ou `**/` vaut ZERO segment ou plus)")
        if ko:
            return 1
        print("CLIQUET VERT : %d fichiers .py balayes, aucun `**` vers un matcher non recursif."
              % len(fichiers))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
