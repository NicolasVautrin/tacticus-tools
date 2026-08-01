#!/usr/bin/env python3
"""#431 -- les HASHES DE BUILD ecrits en dur : ventilation, et cliquet sur la face EXECUTABLE.

LE GISEMENT, ET POURQUOI AUCUNE GARDE EXISTANTE NE LE VOIT
----------------------------------------------------------
Le hash du dossier de build (`gqfc5mff6c`, `rnca9r7q6c`, ...) change a CHAQUE mise a jour du
jeu. Il apparait dans le depot sous deux natures radicalement differentes :

  * en PROSE, c'est une ESTAMPILLE -- « mesure sur gqfc5mff6c » est un fait date, exact pour
    toujours. La corriger DETRUIT ce qu'elle documente (cas explicite : #420 a laisse a
    dessein `probe_hazeord_blast_radius.py:34`, « cette table portait 55: UnitDefeated, juste
    sur gqfc5mff6c ») ;
  * en CODE, c'est une RESOLUTION D'ARTEFACT -- et la, elle se perime. Mesure du 2026-08-01 :
    cinq probes construisaient le chemin du `GameAssembly.dll` de `gqfc5mff6c`, desinstalle.

`symbols_sync.py` verifie que les artefacts CENTRAUX sont synchrones (sha256 du binaire
installe contre les estampilles des tables versionnees). Il ne peut RIEN dire d'un script qui
n'appelle ni `data/symbols/CURRENT` ni le binaire installe : le litteral court-circuite le
controle. `probe_330` couvre l'autre moitie -- mais seulement la PROSE (`.md/.txt/.tsv` sous
`docs/` et `.claude/`), il ne collecte aucun `.py` ni `.ts`.

Ce probe couvre exactement le trou : la face EXECUTABLE.

LE TRI, ET CE QU'IL A D'AUTOMATISABLE
--------------------------------------
Un seul etage est DECIDABLE, et c'est celui qui porte le danger :

  EXECUTABLE vs PROSE. Pour un `.py`, l'AST tranche EXACTEMENT : un hash dans un
  `ast.Constant` de type `str` qui n'est pas un docstring est du code ; les commentaires
  n'existent meme pas dans l'arbre, et les docstrings s'identifient a la position. Aucune
  heuristique. Pour un `.ts`/`.js` il n'y a pas d'AST ici : on retombe sur la forme de ligne
  (`//`, `/*`, `*`), et c'est DIT -- une heuristique annoncee, pas une exactitude simulee.

Au sein de l'executable, deuxieme partage, lui aussi decidable :

  RESOLUTION (le litteral participe a un chemin d'artefact : separateur, `games`, `symbols`,
  `GameAssembly`, `functions.tsv` dans la meme instruction) vs MESSAGE (une chaine imprimee,
  une cle de dictionnaire de mesure). Seule la premiere fait lire le mauvais binaire ; c'est
  elle que le cliquet tient a zero.

CE QUI N'EST PAS AUTOMATISABLE, ET QU'ON NE PRETEND PAS AUTOMATISER
-------------------------------------------------------------------
Dans la PROSE, « rappel historique volontaire » et « reference vivante perimee » ne se
distinguent par aucun automate : la meme phrase est vraie comme rappel date et fausse comme
etat courant. Ce probe RECENSE la prose et rend deux proxys de position (l'un deja tenu par
`probe_330`), il ne la juge pas :
  * ESTAMPILLE (en-tete ou ligne declarative `build ... <hash>`) -- fait lire tout le document
    contre ce build : c'est le seul axe ou zero est tenable, et c'est `probe_330
    --fail-on-header-stamp` qui le tient deja ;
  * MENTION EN CORPS -- presque toujours un rappel legitime. Comptee, jamais alertee.
Le tri fin reste un acte de lecture, et le case-doc #431 dit lequel a ete fait a la main.

    python probe_431_build_literals.py                 # ventilation complete
    python probe_431_build_literals.py --cliquet        # rc 1 s'il reste une RESOLUTION

ASCII only (console Windows cp1252).
"""
from __future__ import annotations

import argparse
import ast
import re
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
if str(REPO / "scripts" / "python") not in sys.path:
    sys.path.insert(0, str(REPO / "scripts" / "python"))

from symbols_layout import current_build  # noqa: E402

# Hash de build Tacticus : 10 caracteres, suffixe de plateforme `6c`. Meme forme que
# `probe_330.BUILD_RE` -- les deux comptes doivent rester comparables.
# Observes : nb3o9lmt6c, uu2fr8mv6c, kqkbjqfb6c, rmvdp0v56c, gqfc5mff6c, rnca9r7q6c.
BUILD_RE = re.compile(r"(?<![a-z0-9])([a-z0-9]{8}6c)(?![a-z0-9])")

# RESOLUTION vs MESSAGE -- le critere est LOCAL et EXACT, sans lecture du contexte :
#
#   RESOLUTION : la chaine EST le hash (`"gqfc5mff6c"`), ou le hash y est un SEGMENT DE
#                CHEMIN (colle a un separateur). Dans les deux cas la valeur DESIGNE un
#                artefact du build -- un dossier d'installation, une table versionnee, un
#                build de reference passe a un outil.
#   MESSAGE    : le hash est noye dans une phrase, un `help=`, une ligne markdown generee.
#                Il est IMPRIME, il ne designe rien.
#
# DEUX CRITERES ONT ETE ESSAYES ET REJETES, et les deux ratent dans le meme sens (trop
# permissif = vert faux) :
#   * « le contexte contient games/symbols/... » -> classait RESOLUTION quatre lignes de
#     markdown GENERE (`probe_326_dsl_join`, `regen_active_ability_tables`), dont le contexte
#     est une liste de 40 lignes qui contient forcement des `/` -- bruit pur ;
#   * « segment de chemin SEULEMENT » -> laissait passer NEUF `--build default="<hash>"` et
#     `table_owners("<hash>")`, qui selectionnent bel et bien une table de symboles. Un
#     defaut d'argparse ne ressemble pas a un chemin et en est pourtant un.
SEPARATORS = ("/", "\\")

# Le litteral n'est pas INTERDIT : il est interdit HORS DU FOYER. Passe en argument direct
# de ces fonctions, il est CONTROLE (l'archive doit exister, ou le build doit correspondre a
# l'installe) -- c'est le seul usage legitime d'un hash ecrit a la main, et il se derive de
# l'arbre plutot que d'une liste d'exceptions a maintenir.
FOYER_CALLS = ("require_pinned", "archived_build")

# Sources EXECUTABLES versionnees. `data/symbols/<hash>/` est exclu : ces tables PORTENT le
# hash de leur propre build, c'est leur identite, pas une citation.
EXEC_GLOBS = ("scripts/**/*.py", "frida/hooks/**/*.ts", "frida/host/**/*.ts",
              "frida/public/**/*.js", ".claude/**/*.js", "hooks-legacy/**/*.js")
PROSE_EXT = {".md", ".txt", ".tsv", ".json"}
EXCLUDED_PREFIXES = ("data/symbols/", ".claude/worktrees/", "node_modules/", "frida/dist/")

TS_COMMENT = re.compile(r"^\s*(//|/\*|\*)")
# Commentaire de FIN DE LIGNE : `case "X": // retire par <hash>`. Sans ce retrait, une
# estampille en commentaire de queue passe pour du code (mesure : `battle-log.js:242`).
TS_TRAILING_COMMENT = re.compile(r"//.*$")


def classify(text: str, start: int, end: int) -> str:
    """RESOLUTION si la valeur DESIGNE un build, MESSAGE si elle le MENTIONNE.

    `text` = la chaine (ou la ligne) qui porte le hash, `[start, end)` sa position dedans.
    Aucun contexte n'est lu : le critere tient dans la valeur elle-meme.
    """
    if text.strip() == text[start:end]:
        return "RESOLUTION"                       # la chaine EST le hash
    avant = text[start - 1] if start > 0 else ""
    apres = text[end] if end < len(text) else ""
    if avant in SEPARATORS or apres in SEPARATORS:
        return "RESOLUTION"                       # segment de chemin
    return "MESSAGE"


def tracked_files() -> list[str]:
    """Fichiers SUIVIS par git -- le perimetre est le depot, pas le disque."""
    r = subprocess.run(["git", "ls-files", "-z"], cwd=str(REPO),
                       capture_output=True, text=True, timeout=120)
    if r.returncode != 0:
        raise SystemExit("git ls-files a echoue : %s" % (r.stderr or "").strip())
    return [p for p in r.stdout.split("\0") if p]


def _docstring_nodes(tree: ast.AST) -> set[int]:
    """`id()` des `ast.Constant` qui sont des docstrings (module, classe, fonction)."""
    out = set()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef,
                                 ast.AsyncFunctionDef)):
            continue
        body = getattr(node, "body", None)
        if not body:
            continue
        first = body[0]
        if (isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant)
                and isinstance(first.value.value, str)):
            out.add(id(first.value))
    return out


def _foyer_controlled(tree: ast.AST) -> set[int]:
    """`id()` des `ast.Constant` passes en argument DIRECT a une fonction du foyer.

    Un hash ecrit a la main y est LEGITIME parce qu'il y est CONTROLE : `archived_build`
    exige que la table de ce build soit versionnee, `require_pinned` exige qu'il corresponde
    au build installe. Deriver l'exemption de l'ARBRE plutot que d'une liste d'exceptions
    ecrite a la main est tout l'objet de la manoeuvre -- une liste, il faudrait la maintenir,
    et elle survivrait a son motif.
    """
    out = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        f = node.func
        nom = f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", "")
        if nom not in FOYER_CALLS:
            continue
        for arg in list(node.args) + [k.value for k in node.keywords]:
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                out.add(id(arg))
    return out


def scan_python(rel: str, text: str) -> list[tuple[int, str, str, str]]:
    """[(ligne, hash, RESOLUTION|MESSAGE, extrait)] des hashes en position EXECUTABLE.

    L'AST est la source de verite : un commentaire n'y est pas, un docstring y est mais
    s'identifie a sa position. Un fichier qui ne parse pas est REMONTE, pas ignore -- un
    parse rate qui rendrait zero serait exactement le faux negatif qu'on chasse.
    """
    tree = ast.parse(text, filename=rel)
    docs = _docstring_nodes(tree)
    foyer = _foyer_controlled(tree)
    lines = text.splitlines()
    # instruction englobante -> pour decider RESOLUTION vs MESSAGE
    stmt_span: list[tuple[int, int]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.stmt) and hasattr(node, "lineno"):
            stmt_span.append((node.lineno, getattr(node, "end_lineno", node.lineno)))
    out = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
            continue
        if id(node) in docs or id(node) in foyer:
            continue
        for m in BUILD_RE.finditer(node.value):
            lo = getattr(node, "lineno", 1)
            hi = getattr(node, "end_lineno", lo)
            # contexte = la plus PETITE instruction qui contient le noeud
            best = None
            for a, b in stmt_span:
                if a <= lo and hi <= b and (best is None or (b - a) < (best[1] - best[0])):
                    best = (a, b)
            ctx = "\n".join(lines[(best[0] - 1):best[1]]) if best else node.value
            kind = classify(node.value, m.start(1), m.end(1))
            extrait = node.value if kind == "MESSAGE" else ctx
            out.append((lo, m.group(1), kind, " ".join(extrait.split())[:110]))
    return out


def scan_textual(rel: str, text: str, comment_re) -> list[tuple[int, str, str, str]]:
    """Meme sortie, par HEURISTIQUE de ligne (pas d'AST) -- pour `.ts` / `.js`."""
    out = []
    for lineno, brut in enumerate(text.splitlines(), 1):
        if comment_re.search(brut):
            continue
        line = TS_TRAILING_COMMENT.sub("", brut)
        for m in BUILD_RE.finditer(line):
            kind = classify(line, m.start(1), m.end(1))
            out.append((lineno, m.group(1), kind, " ".join(brut.split())[:110]))
    return out


def is_exec(rel: str) -> bool:
    p = Path(rel)
    if any(rel.startswith(x) for x in EXCLUDED_PREFIXES):
        return False
    return any(Path(rel).match(g) for g in EXEC_GLOBS)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0],
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cliquet", action="store_true",
                    help="rc 1 s'il reste une RESOLUTION d'artefact par litteral de build")
    ap.add_argument("--top", type=int, default=20)
    ap.add_argument("--list-messages", action="store_true",
                    help="lister aussi les litteraux executables classes MESSAGE")
    args = ap.parse_args()

    courant = current_build()
    print("build courant (data/symbols/CURRENT) : %s" % courant)
    print("")

    files = tracked_files()
    exec_hits: list[tuple[str, int, str, str, str]] = []
    parse_errors: list[tuple[str, str]] = []
    prose_files: Counter = Counter()
    prose_hash: Counter = Counter()
    exec_files: set[str] = set()
    n_exec_scanned = n_prose_scanned = 0

    for rel in files:
        if any(rel.startswith(x) for x in EXCLUDED_PREFIXES):
            continue
        p = REPO / rel
        try:
            text = p.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        if not BUILD_RE.search(text):
            # pas de hash du tout -> on ne compte que le denominateur
            if is_exec(rel):
                n_exec_scanned += 1
            elif p.suffix.lower() in PROSE_EXT:
                n_prose_scanned += 1
            continue
        if is_exec(rel):
            n_exec_scanned += 1
            try:
                hits = (scan_python(rel, text) if rel.endswith(".py")
                        else scan_textual(rel, text, TS_COMMENT))
            except SyntaxError as exc:
                parse_errors.append((rel, str(exc)))
                continue
            for lineno, h, kind, ctx in hits:
                exec_hits.append((rel, lineno, h, kind, ctx))
                exec_files.add(rel)
        elif p.suffix.lower() in PROSE_EXT:
            n_prose_scanned += 1
            n = len(BUILD_RE.findall(text))
            prose_files[rel] += n
            for h in BUILD_RE.findall(text):
                prose_hash[h] += 1

    # ------------------------------------------------------------------ (1) EXECUTABLE
    reso = [h for h in exec_hits if h[3] == "RESOLUTION"]
    msg = [h for h in exec_hits if h[3] == "MESSAGE"]
    print("=== (1) FACE EXECUTABLE (AST pour .py, heuristique de ligne pour .ts/.js) ===")
    print("fichiers executables versionnes balayes : %d" % n_exec_scanned)
    print("occurrences en position executable      : %d  (dans %d fichier(s))"
          % (len(exec_hits), len(exec_files)))
    print("  RESOLUTION d'artefact (DANGEREUX)     : %d" % len(reso))
    print("  MESSAGE / cle de mesure               : %d" % len(msg))
    if parse_errors:
        print("  !! %d fichier(s) NON PARSES -- non mesures, pas 'propres' :" % len(parse_errors))
        for rel, exc in parse_errors:
            print("     %s : %s" % (rel, exc[:90]))
    print("")
    if reso:
        print("  --- RESOLUTIONS (chacune resout un artefact du jeu par un hash en dur) ---")
        for rel, lineno, h, _k, ctx in sorted(reso):
            drapeau = "PERIME" if h != courant else "epingle-au-courant"
            print("    %-58s:%-5d [%s %s]" % (rel[:58], lineno, h, drapeau))
            print("        %s" % ctx)
    if msg and args.list_messages:
        print("  --- MESSAGES (litteral executable, mais ne resout aucun artefact) ---")
        for rel, lineno, h, _k, ctx in sorted(msg):
            print("    %-58s:%-5d [%s]  %s" % (rel[:58], lineno, h, ctx[:60]))
    print("")

    # ---------------------------------------------------------------------- (2) PROSE
    print("=== (2) FACE PROSE (recensement -- le tri fin n'est PAS automatisable) ===")
    print("fichiers de prose versionnes balayes : %d" % n_prose_scanned)
    print("fichiers citant au moins un hash     : %d" % len(prose_files))
    print("occurrences                          : %d" % sum(prose_files.values()))
    for h, n in prose_hash.most_common():
        etiquette = "COURANT" if h == courant else "anterieur"
        print("    hash %s (%s) : %d mention(s)" % (h, etiquette, n))
    print("")
    print("  top fichiers par volume :")
    for rel, n in prose_files.most_common(args.top):
        print("    %-70s %d" % (rel[:70], n))
    if len(prose_files) > args.top:
        print("    ... et %d autre(s) fichier(s)" % (len(prose_files) - args.top))
    print("")
    print("  L'axe ESTAMPILLE (un hash perime en EN-TETE, qui fait lire tout le document")
    print("  contre le mauvais binaire) est tenu par un autre cliquet, deja en place :")
    print("      python probe_330_prose_va_and_build_stamps.py --fail-on-header-stamp")
    print("")

    if args.cliquet:
        if reso:
            print("CLIQUET ROUGE : %d resolution(s) d'artefact par hash de build en dur." % len(reso))
            print("  Un chemin en dur court-circuite `data/symbols/CURRENT` ET le binaire installe :")
            print("  aucune garde de synchronisation ne peut le voir. Passer par `build_pin` :")
            print("      from build_pin import game_dll, functions_tsv, install_dir")
            print("  et, pour des VA/ordinaux transcrits a la main, `build_pin.require_pinned`.")
            return 1
        print("CLIQUET VERT : aucune resolution d'artefact par hash de build en dur.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
