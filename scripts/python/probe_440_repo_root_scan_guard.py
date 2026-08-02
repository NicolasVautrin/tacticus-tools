#!/usr/bin/env python
"""Probe #440 -- un balayage qui part de la RACINE du depot doit exclure `.claude/worktrees`.

POURQUOI CE CLIQUET EXISTE
--------------------------
#434 a mesure la faute sur `probe_283` : lance depuis l'arbre principal, il remontait a la racine
sans exclure `.claude/worktrees/`, donc il LISAIT -- et RAPPORTAIT -- le code en cours des autres
agents. Un rouge d'agent etait attribue a l'arbre principal, et le cout croissait avec le nombre
d'agents en vol. #476 a bouche ce trou DANS `probe_283`, et seulement la : c'etait un FAIT, pas un
cliquet. Rien n'empechait un `REPO.rglob` neuf de rentrer.

Mesure du 2026-08-01 (arbre principal a 8 worktrees vivants), sur `probe_274` qui portait encore
le trou : **13 267** `.py` retenus, dont **11 746 (88,5 %) appartenant aux worktrees des autres
agents** -- perimetre propre : **1 521**. Meme probe, meme commit, lance depuis un worktree :
**33,7 s** ; depuis l'arbre principal : **366,6 s**.

LA CORRECTION NAIVE EST PIRE QUE LE TROU, ET C'EST LE POINT PRINCIPAL
---------------------------------------------------------------------
Le reflexe est d'ajouter `worktrees` au filtre de segments deja present -- celui qui teste
`p.parts`, donc les segments du chemin ABSOLU. Or un agent tourne DANS
`.claude/worktrees/agent-<id>/` : tout chemin absolu chez lui contient ce segment. Mesure directe
du meme jour, filtre absolu + `worktrees` :

    depuis l'arbre principal -> 1 521 fichiers retenus   (a l'air juste)
    depuis un worktree       ->     0 fichier retenus    (auto-exclusion TOTALE)

Zero fichier, et `VERDICT: PASS`. C'est le meme faux vert que la 1re version de `probe_283`
(« 0 classe trouvee -- aucun mirror Python ») : un balayage qui rend zero se lit comme « rien a
signaler ». Le filtre doit donc porter sur le chemin RELATIF au depot -- c'est ce qui le rend
correct DANS LES DEUX SENS : depuis l'arbre principal `.claude/worktrees/...` est un AUTRE
checkout (hors perimetre) ; depuis un worktree, `REPO` EST ce checkout, le relatif ne porte pas ce
prefixe, et le balayage ne s'auto-exclut pas.

CE QUE LE PROBE FAIT
--------------------
0. AUTO-TEST des deux detecteurs sur des sources SYNTHETIQUES (`--self-test` pour le detail).
   Un cliquet dont le detecteur a cesse de mordre rend VERT sur un depot fautif -- c'est
   exactement ce que `probe_181` faisait avant #430 (`0` inconditionnel). L'auto-test tourne a
   CHAQUE run : il fait partie du verdict.
1. R1 -- balayage AST de `scripts/python/**` : toute enumeration recursive (`rglob`, `glob("**/…")`,
   `os.walk`, `Path.walk`) dont la racine est LA RACINE DU DEPOT, dans un fichier qui n'exclut
   nulle part `.claude/worktrees`.
2. R2 -- le piege arme : une exclusion de worktree testee sur des SEGMENTS de chemin (`.parts`),
   c'est-a-dire la correction naive ci-dessus.

AUCUNE ALLOWLIST (regle #421 : l'exemption se DERIVE, elle ne se saisit pas). Les deux criteres
se derivent du seul chemin canonique `.claude/worktrees` :
  * conforme  = le fichier porte, DANS SON CODE, un littéral qui est un prefixe de CHEMIN de
    `.claude/worktrees` (donc `.claude` ou `.claude/worktrees`) ;
  * fautif R2 = un SEGMENT de ce meme chemin (`.claude`, `worktrees`) teste contre `.parts`.
Le probe n'a pas besoin de s'exempter lui-meme : il enumere `scripts/python`, pas la racine.

Verdict FAIL si l'auto-test, R1 ou R2 signalent quoi que ce soit.

ASCII only (console Windows cp1252).
Usage: python probe_440_repo_root_scan_guard.py [-v] [--self-test]
"""
from __future__ import annotations

import argparse
import ast
import io
import sys
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
REPO = PYDIR.parents[1]

# LE chemin canonique des checkouts imbriques. Tout le reste en DERIVE -- rien n'est saisi.
WORKTREES = ".claude/worktrees"
# Segments de ce chemin : ce sont eux qu'une exclusion FAUTIVE teste contre `.parts` (R2).
SEGMENTS = tuple(WORKTREES.split("/"))

# Methodes d'enumeration RECURSIVE : elles descendent, donc elles entrent dans les worktrees.
# `iterdir` en est absente A DESSEIN -- elle ne descend pas, elle ne peut pas lire un autre
# checkout. `glob` n'y entre que si son motif porte `**` (teste au site).
RECURSIFS = ("rglob", "walk")


def _rel(p: Path) -> "str | None":
    try:
        return p.relative_to(REPO).as_posix()
    except ValueError:
        return None


def niveau_racine(rel: str) -> int:
    """Nombre de `.parent` a appliquer AU FICHIER pour atteindre la racine du depot.

    Le premier retire le nom de fichier, d'ou l'egalite avec le nombre de segments du chemin
    relatif : `scripts/python/x.py` -> 3 (`Path(__file__).resolve().parents[2]`, ou
    `Path(__file__).resolve().parent.parents[1]`)."""
    return len(Path(rel).parts)


# ------------------------------------------------------------------------------------------
# Resolution symbolique : « cette expression designe-t-elle la racine du depot ? »
# ------------------------------------------------------------------------------------------

def _niveau(node, env: dict) -> "int | None":
    """Niveau de remontee de l'expression depuis le fichier, ou None si indeterminable."""
    if isinstance(node, ast.Name):
        return 0 if node.id == "__file__" else env.get(node.id)
    if isinstance(node, ast.Attribute):
        base = _niveau(node.value, env)
        if node.attr == "parent":
            return None if base is None else base + 1
        return None
    if isinstance(node, ast.Subscript):
        v = node.value
        # `X.parents[k]` remonte de k+1 : `parents[0]` est deja le parent.
        if isinstance(v, ast.Attribute) and v.attr == "parents":
            base = _niveau(v.value, env)
            k = node.slice
            if base is not None and isinstance(k, ast.Constant) \
                    and isinstance(k.value, int) and not isinstance(k.value, bool):
                return base + k.value + 1
        return None
    if isinstance(node, ast.Call):
        f = node.func
        if isinstance(f, ast.Name):
            # `Path(<x>)` ne change pas le niveau de <x>.
            return _niveau(node.args[0], env) if (f.id == "Path" and node.args) else None
        if isinstance(f, ast.Attribute):
            if f.attr in ("resolve", "absolute", "expanduser"):
                return _niveau(f.value, env)
            # `os.path.dirname(<x>)` = un `.parent` ; `abspath`/`realpath`/`normpath` = neutres.
            if node.args:
                if f.attr == "dirname":
                    b = _niveau(node.args[0], env)
                    return None if b is None else b + 1
                if f.attr in ("abspath", "realpath", "normpath"):
                    return _niveau(node.args[0], env)
        return None
    return None


class _Index:
    """Les noeuds du fichier ranges par type, en UN SEUL `ast.walk`.

    Le point fixe des parametres et les trois detecteurs relisaient chacun l'arbre entier : six
    parcours par fichier. Mesure du 2026-08-01 sur les 665 fichiers analyses : 92,3 s -> 42,0 s
    pour un verdict IDENTIQUE."""

    __slots__ = ("assigns", "calls", "defs", "compares", "comps", "constantes", "docstrings")

    def __init__(self, tree: ast.AST):
        self.assigns, self.calls, self.compares, self.comps, self.constantes = [], [], [], [], []
        self.defs, self.docstrings = {}, set()
        for n in ast.walk(tree):
            if isinstance(n, ast.Assign) and n.value is not None:
                self.assigns.append((n.targets, n.value))
            elif isinstance(n, (ast.AnnAssign, ast.NamedExpr)) and n.value is not None:
                self.assigns.append(([n.target], n.value))
            elif isinstance(n, ast.Call):
                self.calls.append(n)
            elif isinstance(n, ast.Compare):
                self.compares.append(n)
            elif isinstance(n, (ast.GeneratorExp, ast.ListComp, ast.SetComp)):
                self.comps.append(n)
            elif isinstance(n, ast.Constant) and isinstance(n.value, str):
                self.constantes.append(n)
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
                self.defs[n.name] = n
            if isinstance(n, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                corps = getattr(n, "body", None)
                if corps and isinstance(corps[0], ast.Expr) \
                        and isinstance(corps[0].value, ast.Constant) \
                        and isinstance(corps[0].value.value, str):
                    self.docstrings.add(id(corps[0].value))


def _env_racines(idx: "_Index", racine: int) -> dict:
    """{nom: niveau} des variables du fichier, PARAMETRES compris.

    Les parametres sont lies par point fixe intra-fichier : `def f(root): root.rglob(...)`
    n'est fautif que si un appelant lui passe la racine -- c'est le motif de `probe_281`, et le
    lire demande de suivre l'appel. On DERIVE la liaison des appels du fichier ; on n'ecrit
    aucune liste de noms « suspects »."""
    env: dict = {}
    for cibles, val in idx.assigns:
        lv = _niveau(val, env)
        if lv is not None:
            for t in cibles:
                if isinstance(t, ast.Name):
                    env[t.id] = lv

    defs = idx.defs
    # Point fixe : une liaison neuve peut rendre racine un argument d'un appel deja vu.
    for _ in range(4):
        avant = len(env)
        for n in idx.calls:
            if not isinstance(n.func, ast.Name):
                continue
            d = defs.get(n.func.id)
            if d is None:
                continue
            params = [a.arg for a in (d.args.posonlyargs + d.args.args)]
            decale = 1 if (params and params[0] in ("self", "cls")) else 0
            for i, a in enumerate(n.args):
                j = i + decale
                if j < len(params) and _niveau(a, env) == racine:
                    env.setdefault(params[j], racine)
            for kw in n.keywords:
                if kw.arg in params and _niveau(kw.value, env) == racine:
                    env.setdefault(kw.arg, racine)
        # valeurs par defaut : `def f(root=REPO)`
        for d in defs.values():
            params = [a.arg for a in (d.args.posonlyargs + d.args.args)]
            for a, dv in zip(params[len(params) - len(d.args.defaults):], d.args.defaults):
                if _niveau(dv, env) == racine:
                    env.setdefault(a, racine)
        if len(env) == avant:
            break
    return env


def _segments(node, env: dict, racine: int) -> "list | None":
    """Segments litteraux qui suivent la RACINE dans l'expression, ou None si l'expression
    n'est pas ancree a la racine du depot.

    Etre ancre a la racine NE SUFFIT PAS a etre fautif, et confondre les deux a produit un faux
    positif MESURE : `glob.glob(str(PYDIR.parents[1] / "data" / "symbols" / "*" / "frida" /
    "classes.tsv"))` (`test_356_noncomparable_oracle_live.py`) part bien de la racine, mais le
    segment `data` le CONFINE -- il ne verra jamais un worktree. C'est le PREMIER segment qui
    tranche, pas la presence de la racine."""
    if _niveau(node, env) == racine:
        return []
    if isinstance(node, ast.Call):
        f = node.func
        if isinstance(f, ast.Name) and f.id == "str" and node.args:
            return _segments(node.args[0], env, racine)
        if isinstance(f, ast.Attribute) and f.attr == "join" and node.args:
            base = _segments(node.args[0], env, racine)
            if base is None:
                return None
            return base + [a.value if isinstance(a, ast.Constant)
                           and isinstance(a.value, str) else "*" for a in node.args[1:]]
        return None
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
        base = _segments(node.left, env, racine)
        if base is None:
            return None
        d = node.right
        if isinstance(d, ast.Constant) and isinstance(d.value, str):
            return base + [x for x in d.value.replace("\\", "/").split("/") if x]
        # segment DYNAMIQUE (`REPO / var`) : indeterminable. Compte comme NON confinant --
        # cote sur. Aucun site du depot n'est dans ce cas (mesure du 2026-08-01).
        return base + ["*"]
    return None


def _balaye_la_racine(node, env: dict, racine: int) -> bool:
    """Le balayage part de la racine SANS etre confine par un segment litteral.

    `REPO / "scripts" / "python"` est confine, et `REPO / ".claude"` aussi : une descente
    EXPLICITEMENT dirigee vers `.claude` est intentionnelle (lire les transcripts d'agents en
    est un usage legitime). Le gisement vise est l'inverse -- un balayage du depot qui ramasse
    les autres checkouts SANS le vouloir."""
    segs = _segments(node, env, racine)
    if segs is None:
        return False
    return not (segs and "*" not in segs[0] and segs[0] not in ("", "."))


# ------------------------------------------------------------------------------------------
# Conformite : le fichier exclut-il `.claude/worktrees` ?
# ------------------------------------------------------------------------------------------

def _exclut_worktrees(idx: "_Index") -> bool:
    """Un littéral chaine du CODE qui est un prefixe de CHEMIN de `.claude/worktrees`.

    « du CODE », pas d'une docstring : une docstring qui PARLE des worktrees ne les exclut pas.
    On ne verifie pas que le filtre est bien cable -- ce serait une re-implementation ; on
    verifie que le fichier connait le chemin. R2 couvre l'autre moitie : que ce littéral ne soit
    pas applique a des SEGMENTS."""
    for n in idx.constantes:
        if id(n) in idx.docstrings:
            continue
        s = n.value.replace("\\", "/").strip("/")
        if s and (s == WORKTREES or WORKTREES.startswith(s + "/") or s.startswith(WORKTREES)):
            return True
    return False


# ------------------------------------------------------------------------------------------
# R1 -- enumerations depuis la racine
# ------------------------------------------------------------------------------------------

def _sites_r1(idx: "_Index", env: dict, racine: int) -> list:
    """[(ligne, forme)] des enumerations recursives partant de la racine du depot."""
    out = []
    for n in idx.calls:
        f = n.func
        if isinstance(f, ast.Attribute):
            module = f.value.id if isinstance(f.value, ast.Name) else None
            motif = n.args[0] if n.args else None
            # ⚠ `os.walk(REPO)` d'ABORD : `walk` est aussi une methode de `Path` (3.12), donc la
            # branche RECURSIFS l'attrape et teste le module `os` au lieu de l'ARGUMENT. Bug
            # trouve par l'auto-test, pas par relecture.
            if f.attr == "walk" and module == "os":
                if motif is not None and _balaye_la_racine(motif, env, racine):
                    out.append((n.lineno, "os.walk()"))
            elif module == "glob" and f.attr in ("glob", "iglob"):
                # `glob.glob(<x>)` : la racine est DANS l'argument, et c'est l'argument ENTIER
                # qu'il faut lire -- chercher la racine parmi les SOUS-noeuds prend un chemin
                # confine (`REPO / "data" / ...`) pour un balayage de la racine.
                if motif is not None and _balaye_la_racine(motif, env, racine):
                    out.append((n.lineno, "glob.%s()" % f.attr))
            elif f.attr in RECURSIFS:
                if _balaye_la_racine(f.value, env, racine):
                    out.append((n.lineno, "%s()" % f.attr))
            elif f.attr in ("glob", "iglob"):
                # `glob` n'entre dans les worktrees que si son motif descend.
                recursif = isinstance(motif, ast.Constant) \
                    and isinstance(motif.value, str) and "**" in motif.value
                if recursif and _balaye_la_racine(f.value, env, racine):
                    out.append((n.lineno, "glob('**')"))
    return sorted(set(out))


# ------------------------------------------------------------------------------------------
# R2 -- l'exclusion appliquee a des SEGMENTS (le piege arme)
# ------------------------------------------------------------------------------------------

def _seqs_de_chaines(idx: "_Index") -> dict:
    """{nom: [chaines]} des constantes affectees a un tuple/liste/set de chaines."""
    out: dict = {}
    for cibles, val in idx.assigns:
        if not isinstance(val, (ast.Tuple, ast.List, ast.Set)):
            continue
        vals = [e.value for e in val.elts
                if isinstance(e, ast.Constant) and isinstance(e.value, str)]
        if vals and len(vals) == len(val.elts):
            for t in cibles:
                if isinstance(t, ast.Name):
                    out[t.id] = vals
    return out


def _chaines_de(node, seqs: dict) -> list:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return [node.value]
    if isinstance(node, (ast.Tuple, ast.List, ast.Set)):
        return [e.value for e in node.elts
                if isinstance(e, ast.Constant) and isinstance(e.value, str)]
    if isinstance(node, ast.Name):
        return seqs.get(node.id, [])
    return []


def _est_parts(node) -> bool:
    return isinstance(node, ast.Attribute) and node.attr == "parts"


def _sites_r2(idx: "_Index") -> list:
    """[(ligne, segment)] : un SEGMENT du chemin worktree teste contre des `.parts`.

    Deux formes, ce sont les seules rencontrees : le test direct (`"worktrees" in p.parts`) et
    la comprehension (`any(part in SKIP for part in p.parts)`), ou le littéral est loin du
    `.parts` et ne se voit qu'en liant la variable de boucle."""
    seqs = _seqs_de_chaines(idx)
    out = []

    def _fautifs(noeud):
        return [s for s in _chaines_de(noeud, seqs) if s in SEGMENTS]

    for n in idx.compares:
        if n.ops and isinstance(n.ops[0], (ast.In, ast.NotIn)) and _est_parts(n.comparators[0]):
            for s in _fautifs(n.left):
                out.append((n.lineno, s))
    for n in idx.comps:
        for gen in n.generators:
            if not (_est_parts(gen.iter) and isinstance(gen.target, ast.Name)):
                continue
            boucle = gen.target.id
            for sous in ast.walk(n):
                if not (isinstance(sous, ast.Compare) and sous.ops
                        and isinstance(sous.ops[0], (ast.In, ast.NotIn))):
                    continue
                if isinstance(sous.left, ast.Name) and sous.left.id == boucle:
                    for s in _fautifs(sous.comparators[0]):
                        out.append((n.lineno, s))
    return sorted(set(out))


# ------------------------------------------------------------------------------------------
# R3 -- un CLIQUET DE LA BANQUE qui ECRIT dans l'arbre de production
# ------------------------------------------------------------------------------------------
#
# MEME LECON QUE R1/R2, DANS L'AUTRE SENS. R1 garde un cliquet qui LIT hors de son perimetre ;
# R3 garde celui qui y ECRIT. La banque tourne en PARALLELE par conception
# (`ForEach-Object -Parallel`) : un cliquet qui depose un repertoire sous `scripts/python/`
# le fait apparaitre -- puis DISPARAITRE -- pendant que ses voisins enumerent ce meme arbre.
#
# MESURE (#455, 2026-08-02) : `probe_455` deposait `_probe455_hors_<pid>` sous `scripts/python/`
# le temps d'un run pytest. Joue SEUL il est vert ; `probe_391` joue SEUL est vert ; joues
# ENSEMBLE dans la banque, `probe_391` tombe en
# `FileNotFoundError: ... \scripts\python\_probe455_hors_87960`. La PR a ete renvoyee sur ce
# rouge, attribue au mauvais cliquet.
#
# POURQUOI UN GARDE STATIQUE, et pas << on rejoue la banque quelques fois >> : le symptome est
# une COURSE. Un rejeu qui passe ne prouve RIEN -- c'est le piege << verifier que la mutation a
# mordu >>, en negatif. La seule garantie qui vaille est STRUCTURELLE : aucune ecriture.
#
# PERIMETRE : les seules entrees de `scripts/ratchets.ps1`, DERIVEES de ce fichier (jamais
# saisies) via `probe_439.banque_par_texte`. C'est la ou la propriete est NECESSAIRE : un probe
# hors banque n'est pas lance en parallele de la banque.

#: Appels qui font APPARAITRE ou DISPARAITRE une entree de repertoire -- c'est cela qui casse un
#: enumerateur concurrent. Une reecriture EN PLACE (`write_text` sur un fichier existant, ce que
#: font les modes `--fix`) ne deplace aucune entree et n'est donc PAS retenue.
#: Cle = nom appele ; valeur = ou lire le chemin. `recv` = le receveur (methode de `Path`),
#: `a<N>` = l'argument positionnel N, `dir` = le mot-cle `dir=`.
_ECRITURES = {
    "mkdir": ("recv", "a0"), "makedirs": ("a0",), "touch": ("recv",),
    "rmdir": ("recv", "a0"), "unlink": ("recv", "a0"), "remove": ("a0",),
    "rmtree": ("a0",), "copytree": ("a1",), "move": ("a1",),
    "rename": ("recv", "a0", "a1"), "replace": ("recv", "a0", "a1"),
    "symlink_to": ("recv",), "hardlink_to": ("recv",), "symlink": ("a1",),
    "mkdtemp": ("dir",), "mkstemp": ("dir",), "TemporaryDirectory": ("dir",),
    "NamedTemporaryFile": ("dir",),
    # `write_text`/`write_bytes`/`open(..., "w")` CREENT le fichier s'il n'existe pas -- mais ils
    # sont aussi la forme normale d'un `--fix`. On ne les retient QUE via `touch`/`mkdir` qui les
    # accompagnent en pratique ; les inclure ferait rougir les modes de correction legitimes.
}

#: Niveau de `scripts/python` VU DEPUIS le fichier analyse. `scripts/python/x.py` -> 1 (le parent),
#: `scripts/python/tests/x.py` -> 2. Se derive du chemin relatif, comme `niveau_racine`.
def niveau_pydir(rel: str) -> int:
    return len(Path(rel).parts) - 2


def _cibles(n: ast.Call, ou: tuple) -> list:
    """Les noeuds-chemin d'un appel d'ecriture, selon la table `_ECRITURES`."""
    out = []
    for spec in ou:
        if spec == "recv":
            if isinstance(n.func, ast.Attribute):
                out.append(n.func.value)
        elif spec == "dir":
            out += [kw.value for kw in n.keywords if kw.arg == "dir"]
        else:
            i = int(spec[1:])
            if i < len(n.args):
                out.append(n.args[i])
    return out


def _ancre_sous_pydir(node, env: dict, pydir: int, derives: dict, prof: int = 0) -> bool:
    """Le chemin designe par `node` part-il de `scripts/python` ?

    `_segments` seul ne suffit PAS, et le cas qui l'a montre est la faute REELLE de #455 :
    `d = PYDIR / ('_travail_%d' % os.getpid())` puis `d.mkdir()`. `_niveau` ne sait pas lire un
    `BinOp`, donc `d` n'entre pas dans `env` et le receveur `d` ne resout rien. On suit donc UN
    CRAN DE PLUS les affectations simples -- c'est le seul ajout, et son jumeau negatif
    (`mkdtemp` sans `dir=`) le borne."""
    if _segments(node, env, pydir) is not None:
        return True
    if isinstance(node, ast.Name) and prof < 4 and node.id in derives:
        return _ancre_sous_pydir(derives[node.id], env, pydir, derives, prof + 1)
    return False


def _sites_r3(idx: "_Index", env: dict, pydir: int) -> list:
    """[(ligne, appel)] : une ecriture dont le chemin est ANCRE sous `scripts/python`.

    L'ancrage se lit avec le MEME resolveur symbolique que R1 (`_segments`), a une autre racine :
    tout chemin qui part de `scripts/python` est fautif, quel que soit son premier segment -- il
    n'y a pas de sous-repertoire << sur >> la-dedans, `probe_391` et pytest enumerent tout."""
    derives = {t.id: val for cibles, val in idx.assigns for t in cibles
               if isinstance(t, ast.Name)}
    out = []
    for n in idx.calls:
        nom = n.func.attr if isinstance(n.func, ast.Attribute) else (
            n.func.id if isinstance(n.func, ast.Name) else None)
        ou = _ECRITURES.get(nom)
        if ou is None:
            continue
        for cible in _cibles(n, ou):
            if _ancre_sous_pydir(cible, env, pydir, derives):
                out.append((n.lineno, "%s()" % nom))
                break
    return sorted(set(out))


# ------------------------------------------------------------------------------------------
# Analyse d'un fichier
# ------------------------------------------------------------------------------------------

def analyser(rel: str, src: str) -> tuple:
    """(hits R1, hits R2, hits R3). `rel` sert a calculer, depuis CE fichier, le niveau de la
    racine du depot (R1) et celui de `scripts/python` (R3)."""
    try:
        tree = ast.parse(src, filename=rel)
    except (SyntaxError, ValueError):
        return [], [], []
    idx = _Index(tree)
    r2 = _sites_r2(idx)
    pydir = niveau_pydir(rel)
    r3 = _sites_r3(idx, _env_racines(idx, pydir), pydir)
    if _exclut_worktrees(idx):
        return [], r2, r3
    racine = niveau_racine(rel)
    return _sites_r1(idx, _env_racines(idx, racine), racine), r2, r3


# ------------------------------------------------------------------------------------------
# Etape 0 -- l'auto-test des detecteurs
# ------------------------------------------------------------------------------------------

_REL = "scripts/python/faux.py"

# (nom, source, attendu R1, attendu R2). Chaque cas MESURE une decision du detecteur ; un cas
# NEGATIF vaut le cas positif jumeau -- c'est lui qui interdit de faire mordre le probe en
# elargissant le motif.
CAS = [
    ("racine par parents[k]",
     "from pathlib import Path\nREPO = Path(__file__).resolve().parents[2]\n"
     "for p in sorted(REPO.rglob('*.py')):\n    pass\n", 1, 0),
    ("racine par parent puis parents[k]",
     "from pathlib import Path\nimport os\nPYDIR = Path(__file__).resolve().parent\n"
     "REPO = PYDIR.parents[1]\nfor d, _n, _f in os.walk(REPO):\n    pass\n", 1, 0),
    ("racine passee en parametre",
     "from pathlib import Path\nREPO = Path(__file__).resolve().parents[2]\n"
     "def scan(root):\n    return sorted(root.rglob('*.py'))\nscan(REPO)\n", 1, 0),
    ("glob('**') depuis la racine",
     "from pathlib import Path\nREPO = Path(__file__).resolve().parents[2]\n"
     "F = list(REPO.glob('**/*.ts'))\n", 1, 0),
    ("glob.glob depuis la racine",
     "import glob, os\nfrom pathlib import Path\nREPO = Path(__file__).resolve().parents[2]\n"
     "F = glob.glob(os.path.join(str(REPO), '**', '*.py'), recursive=True)\n", 1, 0),
    # --- negatifs ---
    # Une descente EXPLICITEMENT dirigee vers `.claude` est intentionnelle (lire les
    # transcripts d'agents), pas le ramassage involontaire que ce cliquet vise.
    ("descente explicite dans .claude : intentionnelle",
     "from pathlib import Path\nREPO = Path(__file__).resolve().parents[2]\n"
     "F = list((REPO / '.claude').rglob('*.jsonl'))\n", 0, 0),
    # Le faux positif MESURE le 2026-08-01 sur `test_356_noncomparable_oracle_live.py:112` :
    # ancre a la racine, mais CONFINE par le segment `data`. Sans ce cas, resserrer le critere
    # aurait pu passer pour un affaiblissement du detecteur.
    ("glob.glob ancre a la racine mais CONFINE",
     "import glob\nfrom pathlib import Path\nPYDIR = Path(__file__).resolve().parent\n"
     "F = glob.glob(str(PYDIR.parents[1] / 'data' / 'symbols' / '*' / 'frida' / 'c.tsv'))\n",
     0, 0),
    ("sous-repertoire : hors cause",
     "from pathlib import Path\nREPO = Path(__file__).resolve().parents[2]\n"
     "F = sorted((REPO / 'scripts' / 'python').rglob('*.py'))\n", 0, 0),
    ("racine MAIS exclusion presente",
     "from pathlib import Path\nREPO = Path(__file__).resolve().parents[2]\n"
     "SKIP = ('.claude/worktrees',)\n"
     "F = [p for p in REPO.rglob('*.py')\n"
     "     if not any(p.relative_to(REPO).as_posix().startswith(s) for s in SKIP)]\n", 0, 0),
    ("iterdir ne descend pas",
     "from pathlib import Path\nREPO = Path(__file__).resolve().parents[2]\n"
     "F = list(REPO.iterdir())\n", 0, 0),
    ("docstring seule : ne protege pas",
     "'''parle de .claude/worktrees sans les exclure'''\nfrom pathlib import Path\n"
     "REPO = Path(__file__).resolve().parents[2]\nF = list(REPO.rglob('*.py'))\n", 1, 0),
    # --- R2 : le piege arme ---
    ("exclusion par segment ABSOLU (comprehension)",
     "from pathlib import Path\nSKIP = ('.git', 'node_modules', 'worktrees')\n"
     "def ok(p):\n    return not any(x in SKIP for x in p.parts)\n", 0, 1),
    ("exclusion par segment ABSOLU (test direct)",
     "def ok(p):\n    return '.claude' not in p.parts\n", 0, 1),
    ("filtre de segments SANS segment worktree",
     "SKIP = ('.git', 'node_modules', 'logs')\n"
     "def ok(p):\n    return not any(x in SKIP for x in p.parts)\n", 0, 0),
    ("exclusion par prefixe RELATIF : la forme correcte",
     "SKIP = ('.claude/worktrees',)\n"
     "def ok(rel):\n    return not any(rel == s or rel.startswith(s + '/') for s in SKIP)\n",
     0, 0),
    # --- R3 : l'ECRITURE dans l'arbre de production (le vice mesure de #455) ---
    ("mkdir sous scripts/python : LA faute de #455",
     "import os\nfrom pathlib import Path\nPYDIR = Path(__file__).resolve().parent\n"
     "d = PYDIR / ('_travail_%d' % os.getpid())\nd.mkdir(parents=True, exist_ok=True)\n",
     0, 0, 1),
    ("mkdir sous tests/, depuis un fichier de tests/",
     "from pathlib import Path\nTESTS = Path(__file__).resolve().parent\n"
     "(TESTS / 'cas').mkdir()\n", 0, 0, 1),
    ("rmtree sous scripts/python : la DISPARITION casse aussi un enumerateur",
     "import shutil\nfrom pathlib import Path\nPYDIR = Path(__file__).resolve().parent\n"
     "shutil.rmtree(PYDIR / 'tmp', ignore_errors=True)\n", 0, 0, 1),
    ("mkdtemp(dir=PYDIR) : le tmpdir ancre dans l'arbre compte aussi",
     "import tempfile\nfrom pathlib import Path\nPYDIR = Path(__file__).resolve().parent\n"
     "t = tempfile.mkdtemp(prefix='x_', dir=str(PYDIR))\n", 0, 0, 1),
    # --- jumeaux NEGATIFS de R3 : ce sont eux qui interdisent d'elargir le critere ---
    ("mkdtemp SANS dir= : le tmpdir systeme, la forme CORRECTE",
     "import tempfile\nt = tempfile.mkdtemp(prefix='x_')\n", 0, 0, 0),
    ("mkdir sous logs/ (ancre RACINE, hors arbre de production)",
     "from pathlib import Path\nREPO = Path(__file__).resolve().parents[2]\n"
     "(REPO / 'logs' / 'x').mkdir(parents=True, exist_ok=True)\n", 0, 0, 0),
    ("LECTURE sous scripts/python : hors cause, c'est le pain quotidien",
     "from pathlib import Path\nPYDIR = Path(__file__).resolve().parent\n"
     "src = (PYDIR / 'engine' / 'x.py').read_text()\n", 0, 0, 0),
    ("write_text EN PLACE (mode --fix) : ne deplace aucune entree de repertoire",
     "from pathlib import Path\nPYDIR = Path(__file__).resolve().parent\n"
     "(PYDIR / 'engine' / 'x.py').write_text('corrige')\n", 0, 0, 0),
]


def self_test(verbose: bool) -> list:
    bad = []
    for cas in CAS:
        nom, src, a1, a2 = cas[:4]
        a3 = cas[4] if len(cas) > 4 else 0
        r1, r2, r3 = analyser(_REL, src)
        ok = (len(r1) == a1) and (len(r2) == a2) and (len(r3) == a3)
        if verbose or not ok:
            print("   %-5s %-44s R1=%d/%d R2=%d/%d R3=%d/%d"
                  % ("OK" if ok else "FAIL", nom, len(r1), a1, len(r2), a2, len(r3), a3))
        if not ok:
            bad.append(nom)
    return bad


# ------------------------------------------------------------------------------------------

# Pre-filtre DERIVE des detecteurs eux-memes : un fichier qui ne porte AUCUN de ces tokens ne
# peut produire ni hit R1 (aucune enumeration recursive) ni hit R2 (aucun `.parts`). Ce n'est pas
# une allowlist -- c'est la condition necessaire des deux motifs, ecrite une fois.
# Mesure du 2026-08-01, 1 492 fichiers dont 665 analyses : 118,7 s sans, 42,0 s avec, verdict
# IDENTIQUE -- la contre-epreuve `--sans-prefiltre` est la pour le re-verifier a tout moment.
_TOKENS = ("rglob", "walk", "glob", ".parts")


def fichiers_de_la_banque() -> list:
    """Chemins RELATIFS des fichiers Python que `scripts/ratchets.ps1` LANCE.

    DERIVE de la banque, jamais saisi : on reutilise le parse textuel de `probe_439` (source
    unique deja eprouvee, et qui n'a pas besoin de `pwsh`). Une entree `pytest` a la forme
    `-m pytest <fichier> -q` : on retient l'argument qui finit par `.py`."""
    from probe_439_cliquet_peut_rougir import banque_par_texte
    out = []
    for _id, argv in sorted(banque_par_texte().items()):
        cible = next((a for a in argv if a.endswith(".py")), None)
        if cible is None:
            continue
        rel = "scripts/python/" + cible.replace("\\", "/")
        if rel not in out:
            out.append(rel)
    return out


def balayer(verbose: bool, prefiltre: bool = True) -> tuple:
    r1s, r2s, r3s, lus, parses = [], [], [], 0, 0
    # R3 ne porte QUE sur les cliquets de la banque -- c'est la que le parallelisme rend la
    # propriete necessaire. Le perimetre se DERIVE de `ratchets.ps1`.
    try:
        banque = set(fichiers_de_la_banque())
    except Exception as exc:                              # noqa: BLE001
        banque = set()
        r3s.append(("<banque illisible>", 0, str(exc)))
    for p in sorted((REPO / "scripts" / "python").rglob("*.py")):
        rel = _rel(p)
        if rel is None:
            continue
        try:
            src = io.open(p, encoding="utf-8").read()
        except (UnicodeDecodeError, OSError):
            continue
        lus += 1
        dans_banque = rel in banque
        if prefiltre and not dans_banque and not any(t in src for t in _TOKENS):
            continue
        parses += 1
        a, b, c = analyser(rel, src)
        r1s += [(rel, ln, forme) for ln, forme in a]
        r2s += [(rel, ln, seg) for ln, seg in b]
        if dans_banque:
            r3s += [(rel, ln, forme) for ln, forme in c]
    if verbose:
        print("   (%d fichiers lus, %d analyses en AST, %d entree(s) de banque)"
              % (lus, parses, len(banque)))
    return r1s, r2s, r3s, lus


def main(argv) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("-v", "--verbose", action="store_true")
    ap.add_argument("--self-test", action="store_true",
                    help="ne joue QUE l'auto-test des detecteurs, en detail")
    ap.add_argument("--sans-prefiltre", action="store_true",
                    help="contre-epreuve : analyse TOUS les fichiers, sans le pre-filtre textuel")
    args = ap.parse_args(argv)

    print("[440] racine : %s" % REPO)
    mauvais = self_test(args.verbose or args.self_test)
    print("[440] etape 0 : auto-test des detecteurs -- %d/%d cas, %d en echec"
          % (len(CAS) - len(mauvais), len(CAS), len(mauvais)))
    for nom in mauvais:
        print("   FAIL auto-test : %s" % nom)
    if args.self_test:
        print("[440] VERDICT: %s" % ("PASS" if not mauvais else "FAIL (%d)" % len(mauvais)))
        return 0 if not mauvais else 1

    r1, r2, r3, lus = balayer(args.verbose, prefiltre=not args.sans_prefiltre)
    print("[440] etape 1 : %d enumeration(s) depuis la RACINE sans exclusion de %s "
          "(%d fichiers lus)" % (len(r1), WORKTREES, lus))
    for rel, ln, forme in r1:
        print("   FAIL %s:%d  %s part de la racine du depot ; ce fichier n'exclut nulle part "
              "%s -- il lira les checkouts des autres agents" % (rel, ln, forme, WORKTREES))
    print("[440] etape 2 : %d exclusion(s) de worktree testee(s) sur des SEGMENTS" % len(r2))
    for rel, ln, seg in r2:
        print("   FAIL %s:%d  segment %r teste contre `.parts` (chemin ABSOLU) -- depuis un "
              "worktree, TOUT chemin le porte : auto-exclusion, 0 fichier, verdict vert. "
              "Filtrer sur le chemin RELATIF au depot." % (rel, ln, seg))
    print("[440] etape 3 : %d ecriture(s) d'un CLIQUET dans l'arbre de production" % len(r3))
    for rel, ln, forme in r3:
        print("   FAIL %s:%d  %s cree ou supprime une entree sous scripts/python -- la banque "
              "tourne en PARALLELE, un voisin qui enumere cet arbre verra le chemin apparaitre "
              "puis DISPARAITRE (mesure #455 : FileNotFoundError chez probe_391, rouge attribue "
              "au mauvais cliquet). Travailler dans un tmpdir SYSTEME (`mkdtemp()` sans `dir=`)."
              % (rel, ln, forme))

    ko = len(mauvais) + len(r1) + len(r2) + len(r3)
    print("[440] VERDICT: %s" % ("PASS" if ko == 0 else "FAIL (%d)" % ko))
    return 0 if ko == 0 else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
