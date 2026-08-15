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

import build_hash  # noqa: E402
import repo_read  # noqa: E402
from symbols_layout import current_build  # noqa: E402

# LA CIBLE DU RECENSEUR -- DERIVEE DE L'ARBRE, PLUS JAMAIS ECRITE ICI (#330-r3).
#
# Ce module portait, comme `probe_330`, le litteral `r"(?<![a-z0-9])([a-z0-9]{8}6c)(?![a-z0-9])"`.
# Le suffixe `6c` etait une REGULARITE des six premiers builds observes, pas une regle : le build
# courant `t6dpr4k06g` finit en `6g`, donc ce cliquet -- dont c'est precisement le metier -- etait
# AVEUGLE AU BUILD COURANT. Mesure du 2026-08-15 : 68 occurrences hors de portee dans le seul seau
# executable, dont une RESOLUTION d'artefact (`BUILD_DE_LECTURE = "t6dpr4k06g"`).
#
# ⚠ Et le piege est ici plus grave qu'ailleurs : les candidats de ce cliquet DERIVENT de cette
# regex. Y ecrire le hash courant -- ou le suffixe `6g` -- l'aurait fait passer au VERT en GAGNANT
# le gisement qu'il existe pour tenir. La forme se DERIVE (`build_hash`), elle ne s'enumere pas ;
# et `build_hash.verifier_la_forme()` REFUSE si un build connu lui echappe (etape 0 ci-dessous).
BUILD_RE = build_hash.build_re()

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

# --------------------------------------------------------- LE PERIMETRE : DERIVE, PAS SAISI
#
# CE QUI ETAIT ECRIT ICI, ET POURQUOI C'ETAIT UN VERT FAUX (#458)
# ----------------------------------------------------------------
# Le perimetre etait une liste de GLOBS passes a `Path.match` :
#
#     EXEC_GLOBS = ("scripts/**/*.py", "frida/hooks/**/*.ts", ...)
#     any(Path(rel).match(g) for g in EXEC_GLOBS)
#
# `PurePath.match` ne developpe PAS `**` recursivement -- il le traite comme UN segment, et
# il matche depuis la DROITE (`full_match`, qui le developpe, n'existe qu'a partir de 3.13 et
# n'etait pas appele ici). Le motif `scripts/**/*.py` selectionnait donc EXACTEMENT les
# fichiers a profondeur 3, ni plus ni moins. Le trou etait BILATERAL, et sa moitie haute
# n'avait meme pas ete soupconnee :
#
#   * TROP PROFOND -- 950 fichiers, dont l'INTEGRALITE de `scripts/python/engine/**` (364) et
#     de `scripts/python/tests/**` (544) ;
#   * PAS ASSEZ PROFOND -- 17 fichiers a la racine meme du glob, parce que le `**` exige un
#     segment : `frida/host/router.ts`, `frida/host/index.ts`, `frida/hooks/main.ts`,
#     `frida/public/app.js`... c'est-a-dire le coeur du host et du hook.
#
# Total : 967 fichiers versionnes dans AUCUN seau -- ni EXECUTABLE, ni PROSE. Le probe les
# lisait (`tracked_files` les rendait), puis les jetait en silence, et imprimait un
# denominateur qui avait l'air d'une couverture.
#
# LA CORRECTION : L'EXTENSION, ET RIEN D'AUTRE
# ---------------------------------------------
# Une liste de RACINES est un inventaire a maintenir -- elle se perime des qu'un repertoire
# nait, et sa peremption est MUETTE. `scripts/frida/*.js` (les scripts Frida vivants, que
# `CLAUDE.md` nomme), `scripts/node/*.mjs`, `lib/*.py`, `frida/tools/*.ts` n'y ont jamais
# figure. Le seul critere qui ne se perime pas est l'EXTENSION : elle dit quel analyseur sait
# lire le fichier, ce qui est exactement la question posee.
#
# Et parce qu'une table d'extensions peut elle aussi se perimer, l'etape 0 la CONFRONTE a
# l'arbre : toute extension presente dans le depot et absente des trois seaux fait ROUGIR
# (mecanisme #421 -- prouver la couverture dans le MEME processus que la conformite).
#
# `data/symbols/<hash>/` est exclu : ces tables PORTENT le hash de leur propre build, c'est
# leur identite, pas une citation. `.claude/worktrees/` l'est au titre de #434 -- et le filtre
# porte sur le chemin RELATIF (`rel.startswith`), jamais sur les segments d'un chemin absolu :
# depuis un worktree, `git ls-files` ne rend que CE checkout et le prefixe n'apparait pas, donc
# le probe ne s'auto-exclut pas (le faux vert a 0 fichier mesure par #440).
EXCLUDED_PREFIXES = ("data/symbols/", ".claude/worktrees/", "node_modules/", "frida/dist/")

#: Ce qui doit changer pour que ce cliquet puisse changer d'avis.
#:
#: `toujours: True`, et c'est l'etape 0 qui l'impose, pas le volume : elle fait ROUGIR sur toute
#: EXTENSION presente dans l'arbre et absente des trois seaux. Un fichier versionne QUELCONQUE --
#: un `.yaml` neuf a la racine, un `.sh` sous `frida/` -- suffit donc a faire basculer le verdict,
#: et aucun sous-ensemble de chemins ne peut l'anticiper. C'est exactement le vice que #458 a
#: repare : le perimetre etait alors une liste de globs, et 967 fichiers tombaient dans un trou
#: MUET. Le borner de nouveau par des chemins rouvrirait cette porte.
#:
#: `build: False` est MESURE, pas suppose : `current_build()` ne sert qu'a ETIQUETER
#: (`PERIME` / `epingle-au-courant`, `COURANT` / `anterieur`). Le `rc` ne depend que de
#: `inconnues` (etape 0) et de `reso` (etape 1) ; et `data/symbols/` est de toute facon exclu
#: du perimetre, ces tables PORTANT le hash de leur propre build.
DECLENCHEUR = {
    "chemins": ("*", "**"),
    "build": False,
    "toujours": True,
    "raison": "Le perimetre est `git ls-files` ENTIER moins quatre prefixes, et l'etape 0 rougit "
              "sur une extension hors seau : tout fichier versionne, quelle que soit sa place et "
              "son extension, peut le faire changer d'avis.",
}

# (ligne ENTIEREMENT commentaire, commentaire de FIN DE LIGNE) par famille de syntaxe.
# Le second compte autant que le premier : `case "X": // retire par <hash>` ferait passer une
# estampille de queue pour du code (mesure : `battle-log.js:242`).
_SLASH = (re.compile(r"^\s*(//|/\*|\*)"), re.compile(r"//.*$"))
_DIESE = (re.compile(r"^\s*#"), re.compile(r"#.*$"))
_TIRET = (re.compile(r"^\s*--"), re.compile(r"--.*$"))

# Extension -> comment la lire. `None` = AST (exact, .py seulement) ; un couple = heuristique
# de ligne, ANNONCEE comme telle. Ajouter une extension ici est le geste normal quand l'arbre
# en accueille une : l'etape 0 le RECLAME, elle ne le devine pas.
EXT_EXEC = {
    ".py": None,
    ".ts": _SLASH, ".js": _SLASH, ".mjs": _SLASH, ".cjs": _SLASH, ".java": _SLASH,
    ".ps1": _DIESE,
    ".sql": _TIRET,
}
PROSE_EXT = {".md", ".txt", ".tsv", ".json"}
# Ni code ni prose : aucun hash n'y a de sens executable, et on le DECLARE plutot que de
# laisser ces fichiers tomber dans un trou muet.
NEUTRE_EXT = {".css", ".html", ".ini", ".example", ""}

# Le fichier qui IMPORTE ce module est son AUTO-TEST : il porte, par construction, un exemple
# de CHAQUE classe que le cliquet distingue -- c'est precisement ce qui prouve que le
# classifieur mord (`classify` est parametre sur des chaines qui SONT des hashes et sur des
# chemins d'artefact ; `scan_python` est confronte a une source factice qui en contient).
# Le faire rougir dessus, ce serait faire rougir le cliquet sur la preuve qu'il rougit.
# L'exemption se DERIVE du nom du module courant -- elle ne se saisit pas -- et elle est
# IMPRIMEE a chaque run : un fichier qui s'y glisserait pour se taire se verrait.
# Pendant exact de `probe_440` (<< le probe n'a pas besoin de s'exempter lui-meme >>).
AUTO_TEST_MODULE = Path(__file__).stem


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


def lire(p: Path) -> str:
    """`Path.read_text(encoding="utf-8")`, sans ouvrir en mode texte (cf. `repo_read`).

    Conserve pour les appelants qui lisent UN fichier ; le balayage, lui, passe par
    `repo_read.read_bytes_many` -- c'est la que le gain se joue (16,8 s -> ~4 s sur les 3254
    fichiers versionnes, mesure du 2026-08-03).
    """
    return repo_read.to_text(p.read_bytes())


class _Index:
    """Les noeuds utiles du fichier, ranges en UN SEUL parcours.

    `importe_le_cliquet`, `_docstring_nodes`, `_foyer_controlled`, le releve des instructions
    et le balayage des constantes relisaient CHACUN l'arbre entier : cinq `ast.walk` par
    fichier. Mesure du 2026-08-03 : 3,7 millions de noeuds visites pour 418 fichiers parses,
    17,3 s cumulees dans `ast.walk`. Le verdict est IDENTIQUE -- seul le nombre de traversees
    change (meme argument, meme mesure, que `_Index` de `probe_440`).
    """

    __slots__ = ("constantes", "docstrings", "foyer", "importe_le_cliquet", "stmt_span")

    def __init__(self, tree: ast.AST):
        self.constantes: list = []
        self.docstrings: set = set()
        self.foyer: set = set()
        self.importe_le_cliquet = False
        self.stmt_span: list = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant):
                if isinstance(node.value, str):
                    self.constantes.append(node)
            elif isinstance(node, ast.Call):
                f = node.func
                nom = f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", "")
                if nom in FOYER_CALLS:
                    for arg in list(node.args) + [k.value for k in node.keywords]:
                        if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                            self.foyer.add(id(arg))
            elif isinstance(node, ast.Import):
                if any(a.name == AUTO_TEST_MODULE for a in node.names):
                    self.importe_le_cliquet = True
            elif isinstance(node, ast.ImportFrom):
                if node.module == AUTO_TEST_MODULE:
                    self.importe_le_cliquet = True
            if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef,
                                 ast.AsyncFunctionDef)):
                body = getattr(node, "body", None)
                if body:
                    first = body[0]
                    if (isinstance(first, ast.Expr)
                            and isinstance(first.value, ast.Constant)
                            and isinstance(first.value.value, str)):
                        self.docstrings.add(id(first.value))
            if isinstance(node, ast.stmt) and hasattr(node, "lineno"):
                self.stmt_span.append((node.lineno,
                                       getattr(node, "end_lineno", node.lineno)))


def scan_python(rel: str, text: str,
                auto_tests: list | None = None) -> list[tuple[int, str, str, str]]:
    """[(ligne, hash, RESOLUTION|MESSAGE, extrait)] des hashes en position EXECUTABLE.

    L'AST est la source de verite : un commentaire n'y est pas, un docstring y est mais
    s'identifie a sa position. Un fichier qui ne parse pas est REMONTE, pas ignore -- un
    parse rate qui rendrait zero serait exactement le faux negatif qu'on chasse.

    `auto_tests` (optionnel) recueille les fichiers exemptes au titre d'AUTO-TEST, pour que
    le run les IMPRIME : une exemption muette est une allowlist deguisee.
    """
    idx = _Index(ast.parse(text, filename=rel))
    if idx.importe_le_cliquet:
        if auto_tests is not None:
            auto_tests.append(rel)
        return []
    docs, foyer = idx.docstrings, idx.foyer
    lines = text.splitlines()
    # instruction englobante -> pour decider RESOLUTION vs MESSAGE
    stmt_span = idx.stmt_span
    out = []
    for node in idx.constantes:
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


def scan_textual(rel: str, text: str, commentaires) -> list[tuple[int, str, str, str]]:
    """Meme sortie, par HEURISTIQUE de ligne (pas d'AST) -- tout ce qui n'est pas `.py`.

    `commentaires` = (ligne entierement commentaire, commentaire de fin de ligne), pris dans
    `EXT_EXEC` selon l'extension : les familles `//`, `#` et `--` ne se melangent pas.
    """
    ligne_re, queue_re = commentaires
    out = []
    for lineno, brut in enumerate(text.splitlines(), 1):
        if ligne_re.search(brut):
            continue
        line = queue_re.sub("", brut)
        for m in BUILD_RE.finditer(line):
            kind = classify(line, m.start(1), m.end(1))
            out.append((lineno, m.group(1), kind, " ".join(brut.split())[:110]))
    return out


def seau(rel: str) -> str:
    """`EXEC` | `PROSE` | `NEUTRE` | `INCONNU` -- la classification est TOTALE.

    `INCONNU` n'est pas un silence : c'est ce que l'etape 0 fait ROUGIR. C'est la difference
    exacte avec l'ancien `Path.match`, qui laissait 967 fichiers hors de tout seau sans rien
    en dire.
    """
    if any(rel.startswith(x) for x in EXCLUDED_PREFIXES):
        return "NEUTRE"
    ext = Path(rel).suffix.lower()
    if ext in EXT_EXEC:
        return "EXEC"
    if ext in PROSE_EXT:
        return "PROSE"
    if ext in NEUTRE_EXT:
        return "NEUTRE"
    return "INCONNU"


def is_exec(rel: str) -> bool:
    return seau(rel) == "EXEC"


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
    # LA CIBLE DU RECENSEUR, DITE AVANT TOUT COMPTE (#330-r3). Un cliquet qui ne dit pas ce
    # qu'il cherche laisse lire ses zeros comme des mesures -- c'est exactement ce que le
    # suffixe `6c` en dur a produit ici.
    try:
        rap = build_hash.verifier_la_forme()
        forme_refusee = ""
    except build_hash.FormeRefusee as exc:
        rap = build_hash.rapport_des_sources()
        forme_refusee = str(exc)
    build_hash.imprimer_les_sources(rap)
    if forme_refusee:
        print("  !! FORME REFUSEE -- %s" % forme_refusee.replace("\n", "\n     "))
    print("")

    files = tracked_files()
    exec_hits: list[tuple[str, int, str, str, str]] = []
    parse_errors: list[tuple[str, str]] = []
    prose_files: Counter = Counter()
    prose_hash: Counter = Counter()
    exec_files: set[str] = set()
    auto_tests: list[str] = []
    inconnues: dict[str, list[str]] = defaultdict(list)
    par_seau: Counter = Counter()
    candidats: Counter = Counter()
    connus = set(rap["connus"])
    n_exec_scanned = n_prose_scanned = 0

    # Lecture PARALLELE des seuls fichiers a balayer (#457-r6). L'ouverture d'un fichier pese
    # ici ~7 ms sous `scripts/` (filtre systeme sur les extensions executables) : en serie,
    # elle coutait a elle seule 16,8 s des ~22 s du cliquet -- plus que tout l'AST. L'ORDRE de
    # `files` est conserve (`read_bytes_many` rend une liste ALIGNEE), donc rien ne bouge dans
    # le rapport. Les deux echecs restent traites au meme endroit et de la meme facon qu'avant.
    a_lire = [rel for rel in files if seau(rel) in ("EXEC", "PROSE")]
    octets = dict(zip(a_lire, repo_read.read_bytes_many([REPO / r for r in a_lire])))

    for rel in files:
        s = seau(rel)
        par_seau[s] += 1
        if s == "INCONNU":
            inconnues[Path(rel).suffix.lower() or "(sans extension)"].append(rel)
            continue
        if s == "NEUTRE":
            continue
        data = octets.get(rel)
        if data is None:                              # OSError -- comme avant, on saute
            continue
        try:
            text = repo_read.to_text(data)
        except UnicodeDecodeError:
            continue
        if s == "EXEC":
            n_exec_scanned += 1
            # INVENTAIRE (non bloquant) : les jetons de la FORME d'un hash qu'aucun build connu
            # ne porte. C'est le seul canal par lequel un build neuf peut se signaler avant
            # d'avoir une table ou un chemin -- et il est BRUYANT par construction, donc il ne
            # decide rien. Le dire explicitement est ce qui empeche de le promouvoir en critere.
            candidats.update(build_hash.candidats_de_forme(text, connus))
            if not BUILD_RE.search(text):
                continue                          # pas de hash -> denominateur seulement
            commentaires = EXT_EXEC[Path(rel).suffix.lower()]
            try:
                hits = (scan_python(rel, text, auto_tests) if commentaires is None
                        else scan_textual(rel, text, commentaires))
            except SyntaxError as exc:
                parse_errors.append((rel, str(exc)))
                continue
            for lineno, h, kind, ctx in hits:
                exec_hits.append((rel, lineno, h, kind, ctx))
                exec_files.add(rel)
        else:                                     # PROSE
            n_prose_scanned += 1
            if not BUILD_RE.search(text):
                continue
            trouves = BUILD_RE.findall(text)
            prose_files[rel] += len(trouves)
            for h in trouves:
                prose_hash[h] += 1

    # ----------------------------------------------------------------- (0) COUVERTURE
    # Le cliquet PROUVE qu'il voit son gisement, dans le MEME processus que la conformite
    # (#421). Sans cette etape, un fichier hors de tout seau est indiscernable d'un fichier
    # propre -- c'est litteralement ce qui a rendu ce probe VERT sur 967 fichiers (#458).
    print("=== (0) COUVERTURE DU PERIMETRE (derive de l'EXTENSION, pas d'une liste de racines) ===")
    print("fichiers suivis                  : %d" % len(files))
    print("  seau EXECUTABLE                : %d" % par_seau["EXEC"])
    print("  seau PROSE                     : %d" % par_seau["PROSE"])
    print("  NEUTRE (ni code ni prose, exclus): %d" % par_seau["NEUTRE"])
    print("  NON CLASSES                    : %d" % par_seau["INCONNU"])
    if inconnues:
        print("  !! extension(s) presente(s) dans l'arbre et dans AUCUN seau :")
        for ext, rels in sorted(inconnues.items()):
            avec = sum(1 for r in rels
                       if BUILD_RE.search((REPO / r).read_bytes()
                                          .decode("utf-8", errors="replace")))
            print("     %-12s %d fichier(s), dont %d citant un hash -- ex. %s"
                  % (ext, len(rels), avec, rels[0]))
    if auto_tests:
        print("  exempte(s) comme AUTO-TEST (importe(nt) %s) : %d"
              % (AUTO_TEST_MODULE, len(auto_tests)))
        for rel in sorted(auto_tests):
            print("     %s" % rel)
    print("")

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
    # ⚠ CHEMIN ENTIER, JAMAIS TRONQUE. Ces lignes portaient `rel[:58]`, ce qui convenait a
    # l'ancien perimetre (profondeur 3 imposee par `Path.match`). Sur le perimetre derive,
    # 641 des 1928 chemins depassent 58 caracteres -- pour un tiers du gisement, le cliquet
    # rougissait donc SANS NOMMER le fichier fautif, la troncature emportant jusqu'au nom de
    # base. Trouve par contre-epreuve adversariale, pas par relecture : les trois cibles de
    # mutation du test avaient toutes un chemin plus court que la troncature.
    if reso:
        print("  --- RESOLUTIONS (chacune resout un artefact du jeu par un hash en dur) ---")
        for rel, lineno, h, _k, ctx in sorted(reso):
            drapeau = "PERIME" if h != courant else "epingle-au-courant"
            print("    %s:%d  [%s %s]" % (rel, lineno, h, drapeau))
            print("        %s" % ctx)
    if msg and args.list_messages:
        print("  --- MESSAGES (litteral executable, mais ne resout aucun artefact) ---")
        for rel, lineno, h, _k, ctx in sorted(msg):
            print("    %s:%d  [%s]  %s" % (rel, lineno, h, ctx[:60]))
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
        print("    %-70s %d" % (rel, n))
    if len(prose_files) > args.top:
        print("    ... et %d autre(s) fichier(s)" % (len(prose_files) - args.top))
    print("")
    print("  L'axe ESTAMPILLE (un hash perime en EN-TETE, qui fait lire tout le document")
    print("  contre le mauvais binaire) est tenu par un autre cliquet, deja en place :")
    print("      python probe_330_prose_va_and_build_stamps.py --fail-on-header-stamp")
    print("")

    # ------------------------------------------------------- (3) INVENTAIRE, jamais un verdict
    print("=== (3) JETONS DE LA FORME D'UN HASH, qu'AUCUN build connu ne porte (inventaire) ===")
    print("Ce canal ne decide RIEN et c'est mesure : la forme generique seule rend %d jeton(s)"
          % len(candidats))
    print("distinct(s) sur le seul seau executable, pour %d build(s) reel(s). Le critere qui"
          % len(connus))
    print("discrimine est la POSITION (`games|dumps|symbols/<x>`), pas la forme -- cf. build_hash.")
    print("Il existe pour qu'un build NEUF puisse se signaler avant d'avoir une table ou un chemin.")
    print("  jetons : %d distinct(s), %d occurrence(s)" % (len(candidats), sum(candidats.values())))
    for h, n in candidats.most_common(args.top):
        print("    %-14s %d" % (h, n))
    if len(candidats) > args.top:
        print("    ... et %d autre(s) jeton(s)" % (len(candidats) - args.top))
    print("")

    if args.cliquet:
        ko = 0
        if forme_refusee:
            ko += 1
            print("CLIQUET ROUGE : la FORME du hash de build ne reconnait plus un build CONNU.")
            print("  %s" % forme_refusee.replace("\n", "\n  "))
        if inconnues:
            ko += len(inconnues)
            print("CLIQUET ROUGE : %d extension(s) hors de tout seau -- le perimetre a un TROU."
                  % len(inconnues))
            print("  Un fichier non classe n'est pas un fichier propre : il n'est PAS LU, et le")
            print("  denominateur imprime plus haut se lit quand meme comme une couverture.")
            print("  C'est le vice mesure par #458 (967 fichiers, dont tout scripts/python/engine).")
            print("  Classer l'extension dans `EXT_EXEC` (avec sa syntaxe de commentaire),")
            print("  `PROSE_EXT` ou `NEUTRE_EXT` -- selon qu'un hash y designe, y mentionne, ou rien.")
        if reso:
            ko += len(reso)
            print("CLIQUET ROUGE : %d resolution(s) d'artefact par hash de build en dur." % len(reso))
            print("  Un chemin en dur court-circuite `data/symbols/CURRENT` ET le binaire installe :")
            print("  aucune garde de synchronisation ne peut le voir. Passer par `build_pin` :")
            print("      from build_pin import game_dll, functions_tsv, install_dir")
            print("  et, pour des VA/ordinaux transcrits a la main, `build_pin.require_pinned`.")
        if ko:
            return 1
        print("CLIQUET VERT : perimetre integralement classe, aucune resolution d'artefact"
              " par hash de build en dur.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
