#!/usr/bin/env python
"""Probe #462-r5 -- `from X import Y` ou Y n'existe PLUS dans X. Imports DIFFERES compris.

LA FAUTE QUE CE CLIQUET REND VISIBLE (mesuree le 2026-08-03)
------------------------------------------------------------
`BUILD_HASH` a ete retire de `probe_193c_move_playbook_terms` le 2026-08-01 par #431 -- un BON
changement (un hash de build en dur court-circuite `data/symbols/CURRENT`). Quatre probes
l'importaient encore. Consequence mesuree : `test_fabricator_claw_cap_live.py` a rendu
**0 passed / 10 errors** (`ImportError: cannot import name 'BUILD_HASH'`) pendant DEUX JOURS.

Ce qui a rendu la faute invisible tient en une ligne : **l'import est A L'INTERIEUR d'une
fonction**. La fixture fait `from probe_242_fabricator_claw_cap import _drive_cluster` dans son
corps ; `probe_242` importe `BUILD_HASH` au niveau module -- mais personne n'importe `probe_242`
au niveau module. Donc :

  * `pytest --collect-only` sur TOUT le depot : **417/417 fichiers, rc 0** -- SAIN ;
  * `python -c "import <chaque module>"` ne visite pas non plus les corps de fonction ;
  * `probe_365` est aveugle deux fois : il ne lit que le TypeScript de `frida/`, et son critere
    est << la CIBLE est absente ou gitignoree >> -- ici la cible EXISTE, seul le NOM a disparu.

Le seul instrument qui voit ce gisement est une resolution STATIQUE, nom par nom, des imports
de premiere partie -- ceux dont la cible est un fichier du depot, donc dont les liaisons de
module se lisent a l'AST.

CE QUE LE PROBE FAIT
--------------------
0. AUTO-TEST des detecteurs sur des sources SYNTHETIQUES (`--self-test` pour le detail). Un
   cliquet dont le detecteur a cesse de mordre rend VERT sur un depot fautif : l'auto-test fait
   partie du verdict, a chaque run.
1. INDEX des modules de premiere partie -- tout `.py` SUIVI PAR GIT sous `scripts/python`, avec
   son nom pointe (`engine.playbook.base`, `probe_193c_move_playbook_terms`,
   `tests.engine.runner._pilein_owner_turns`). Les repertoires SANS `__init__.py` comptent :
   ce sont des paquets-espaces-de-noms, et `tests.` en est un, reellement importe.
2. LIAISONS de chaque module, au niveau MODULE seulement (les corps de `def`/`class` ne lient
   rien d'importable) : `def`/`class`, affectations sous n'importe quel `if`/`try`/`for`/`with`,
   imports, `global` assigne depuis une fonction, et resolution RECURSIVE des `import *`.
3. BALAYAGE de tout `.py` suivi par git : chaque `from X import Y` dont `X` est a l'index et
   `Y` n'est ni une liaison de `X` ni un sous-module de `X` -> ROUGE.

CE QU'IL NE PRETEND PAS FAIRE, et pourquoi c'est deliberement etroit
--------------------------------------------------------------------
  * `import X` NU ne rend AUCUN signal : un nom absent de l'index peut etre stdlib ou tiers, et
    rien dans l'arbre ne permet de trancher. Seul `from X import Y` porte de l'information,
    parce qu'il faut deja que `X` soit a nous pour qu'on lise `Y`.
  * Un module OPAQUE est ECARTE, et le DIT (`--verbose`) : `import *` d'une cible hors index,
    `globals()[...] = ...`, `__getattr__` de module (PEP 562). Les ecarter est ce qui garde le
    zero faux positif ; les compter fabriquerait des rouges sur des modules dont les liaisons ne
    se lisent PAS a l'AST. Le cout est minuscule et se MESURE : trois fichiers portent
    `globals()[` mais UN SEUL est la cible d'un `from ... import` (`engine_agreement_stages`),
    donc UN SEUL module est reellement soustrait au verdict.
  * Un `from X import Y` dont le `try` englobant attrape `ImportError` est EXEMPTE : l'auteur a
    DECLARE que l'import peut echouer. C'est une dependance optionnelle, pas un import mort.

PERIMETRE : `git ls-files` -- donc le checkout COURANT, et lui seul. C'est ce qui satisfait #434
sans filtre a ecrire : depuis un worktree, git ne liste que ce worktree, et depuis l'arbre
principal il ne descend pas dans `.claude/worktrees` (autres checkouts, hors index).

ASCII only (console Windows cp1252).
Usage: python probe_462r5_dead_imports.py [-v] [--self-test]
"""
from __future__ import annotations

import argparse
import ast
import subprocess
import sys
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
REPO = PYDIR.parents[1]
if str(PYDIR) not in sys.path:
    sys.path.insert(0, str(PYDIR))
import repo_read  # noqa: E402

#: Racine d'import de premiere partie. C'est celle que tout le depot insere dans `sys.path`
#: (`sys.path.insert(0, str(Path(__file__).resolve().parent))`, ~250 sites).
ROOT_REL = "scripts/python"

#: Exceptions dont la capture DECLARE qu'un import peut echouer -- l'import n'est alors pas mort,
#: il est optionnel. `Exception`/bare `except` incluses : elles attrapent `ImportError`.
EXC_IMPORT = ("ImportError", "ModuleNotFoundError", "Exception", "BaseException")


# ------------------------------------------------------------------------------------------
# Index des modules de premiere partie
# ------------------------------------------------------------------------------------------

def fichiers_suivis() -> list:
    """Chemins RELATIFS (posix) des `.py` suivis par git dans CE checkout.

    `git ls-files` est le perimetre : il ne connait que l'index du checkout courant, donc il
    exclut structurellement `.claude/worktrees` depuis l'arbre principal et ne s'auto-exclut pas
    depuis un worktree -- les deux sens de #434, sans un seul filtre a ecrire.
    """
    out = subprocess.run(["git", "ls-files", "*.py"], cwd=REPO,
                         capture_output=True, text=True, check=True)
    return [l.strip().replace("\\", "/") for l in out.stdout.splitlines() if l.strip()]


def _rel(p: Path) -> "str | None":
    try:
        return p.relative_to(REPO).as_posix()
    except ValueError:
        return None


def nom_pointe(rel: str) -> "str | None":
    """Nom d'import de `rel`, ou None s'il n'est pas sous la racine d'import.

    Les repertoires SANS `__init__.py` comptent : depuis Python 3.3 ce sont des paquets-espaces
    -de-noms, et le depot s'en sert (`from tests.engine.runner._pilein_owner_turns import ...`).
    Exiger `__init__.py` rendrait ces cibles introuvables et les imports correspondants MUETS.
    """
    if not rel.startswith(ROOT_REL + "/"):
        return None
    parts = rel[len(ROOT_REL) + 1:].split("/")
    if parts[-1] == "__init__.py":
        parts = parts[:-1]
        if not parts:
            return None
    else:
        parts[-1] = parts[-1][:-3]
    return ".".join(parts)


# ------------------------------------------------------------------------------------------
# Liaisons de module
# ------------------------------------------------------------------------------------------

#: Champs d'un noeud qui portent des STATEMENTS -- on ne les suit pas quand on ne cherche que
#: les expressions PROPRES a un statement (ses sous-corps sont visites par ailleurs).
_CHAMPS_CORPS = ("body", "orelse", "finalbody", "handlers", "cases")


def _expressions(n):
    """Sous-noeuds d'EXPRESSION de `n`, sans entrer dans ses sous-corps ni dans un `def`/`class`.

    Sans cet elagage, une collecte par `ast.walk` a chaque niveau de flot relit le meme
    sous-arbre autant de fois qu'il est imbrique -- c'est ce qui coutait 19 s d'index.
    """
    pile = []
    for champ, val in ast.iter_fields(n):
        if champ in _CHAMPS_CORPS:
            continue
        if isinstance(val, list):
            pile += [v for v in val if isinstance(v, ast.AST)]
        elif isinstance(val, ast.AST):
            pile.append(val)
    while pile:
        cur = pile.pop()
        if isinstance(cur, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        yield cur
        pile += list(ast.iter_child_nodes(cur))


def _noms_cible(node, out: set) -> None:
    """Noms lies par une cible d'affectation (`x`, `a, b`, `*rest`, `obj.attr` -> rien)."""
    if isinstance(node, ast.Name):
        out.add(node.id)
    elif isinstance(node, (ast.Tuple, ast.List)):
        for e in node.elts:
            _noms_cible(e, out)
    elif isinstance(node, ast.Starred):
        _noms_cible(node.value, out)


class Liaisons:
    """Les noms qu'un module expose a `from <module> import <nom>`, et son OPACITE.

    `opaque` n'est pas un echec : c'est le refus de conclure. Un module dont les liaisons ne se
    lisent pas a l'AST (`import *` d'une cible inconnue, `globals()[...] = ...`, `__getattr__`)
    ne permet aucun verdict sur ses noms -- et rendre un rouge la-dessus serait exactement le
    faux positif qui fait desactiver un cliquet.
    """

    __slots__ = ("noms", "etoiles", "opaque", "raison")

    def __init__(self):
        self.noms: set = set()
        self.etoiles: list = []          # modules cibles d'un `from <m> import *`
        self.opaque = False
        self.raison = ""

    def _opacifier(self, raison: str) -> None:
        if not self.opaque:
            self.opaque, self.raison = True, raison


def liaisons_de(tree: ast.AST) -> Liaisons:
    """Liaisons de NIVEAU MODULE. On descend dans tout le flot de controle (`if`/`try`/`for`/
    `while`/`with`/`match`) -- une definition conditionnelle lie tout autant -- mais PAS dans les
    corps de `def`/`class`, qui n'exposent rien a un `from ... import`.

    UN SEUL `ast.walk` pour le reste (`global` assigne, walrus, `globals()`) : la version qui
    marchait l'arbre a chaque niveau de flot payait un parcours par statement imbrique."""
    lia = Liaisons()

    def visiter(corps) -> None:
        for n in corps:
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                lia.noms.add(n.name)
                if n.name == "__getattr__" and isinstance(n, (ast.FunctionDef,
                                                             ast.AsyncFunctionDef)):
                    lia._opacifier("__getattr__ de module (PEP 562)")
                continue
            if isinstance(n, ast.Import):
                for a in n.names:
                    lia.noms.add(a.asname or a.name.split(".")[0])
                continue
            if isinstance(n, ast.ImportFrom):
                for a in n.names:
                    if a.name == "*":
                        lia.etoiles.append((n.module, n.level))
                    else:
                        lia.noms.add(a.asname or a.name)
                continue
            if isinstance(n, ast.Assign):
                for t in n.targets:
                    _noms_cible(t, lia.noms)
            elif isinstance(n, (ast.AnnAssign, ast.AugAssign)):
                _noms_cible(n.target, lia.noms)
            elif isinstance(n, (ast.For, ast.AsyncFor)):
                _noms_cible(n.target, lia.noms)
            elif isinstance(n, (ast.With, ast.AsyncWith)):
                for it in n.items:
                    if it.optional_vars is not None:
                        _noms_cible(it.optional_vars, lia.noms)
            elif isinstance(n, ast.Try) or type(n).__name__ == "TryStar":
                for h in n.handlers:
                    if h.name:
                        lia.noms.add(h.name)
            # Un walrus en position d'EXPRESSION de ce statement lie au niveau module. On ne
            # regarde que les expressions PROPRES au statement : ses sous-corps sont visites
            # juste apres, et les `def`/`class` qui s'y trouvent ne lient rien ici.
            for sous in _expressions(n):
                if isinstance(sous, ast.NamedExpr):
                    _noms_cible(sous.target, lia.noms)
            for champ in ("body", "orelse", "finalbody"):
                sous_corps = getattr(n, champ, None)
                if isinstance(sous_corps, list):
                    visiter(sous_corps)
            for h in getattr(n, "handlers", []) or []:
                visiter(h.body)
            for c in getattr(n, "cases", []) or []:      # match/case
                visiter(c.body)

    visiter(getattr(tree, "body", []))

    # Un seul parcours pour les deux signaux restants :
    #  * `global X` + `X = ...` dans une fonction LIE au niveau module (`def init(): global
    #    CACHE; CACHE = {}` expose bien `CACHE` -- sans ce passage, un rouge FAUX) ;
    #  * `globals()[...] = ...` / `globals().update(...)` : liaison DYNAMIQUE, illisible a l'AST.
    declares, assignes = set(), set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Global):
            declares.update(n.names)
        elif isinstance(n, ast.Assign):
            for t in n.targets:
                _noms_cible(t, assignes)
        elif isinstance(n, (ast.AnnAssign, ast.AugAssign, ast.NamedExpr)):
            _noms_cible(n.target, assignes)
        elif isinstance(n, ast.Call):
            f = n.func
            if isinstance(f, ast.Name) and f.id == "globals":
                lia._opacifier("liaison dynamique par globals()")
            elif isinstance(f, ast.Attribute) and isinstance(f.value, ast.Call) \
                    and isinstance(f.value.func, ast.Name) and f.value.func.id == "globals":
                lia._opacifier("liaison dynamique par globals()")
    lia.noms |= (declares & assignes)
    return lia


def resoudre_relatif(mod: "str | None", level: int, paquet: str) -> "str | None":
    """Nom ABSOLU d'un `from .x import y` ecrit dans le paquet `paquet` (nom pointe du paquet)."""
    if level == 0:
        return mod
    parts = paquet.split(".") if paquet else []
    if level - 1 > len(parts):
        return None
    base = parts[:len(parts) - (level - 1)]
    return ".".join(base + ([mod] if mod else []))


class Index:
    """Les modules de premiere partie, avec leurs liaisons calculees A LA DEMANDE.

    PARESSEUX par mesure : sur l'arbre reel, ~1 635 modules sont a l'index mais une petite
    fraction seulement est la CIBLE d'un `from ... import`. Calculer les liaisons de TOUS
    coutait 19 s pour un verdict identique.
    """

    def __init__(self, arbres: dict):
        self.arbres: dict = {}                     # nom pointe -> AST
        self.paquets: set = set()
        self._lia: dict = {}
        self._exp: dict = {}
        for rel, tree in arbres.items():
            nom = nom_pointe(rel)
            if nom is None:
                continue
            self.arbres[nom] = tree
            parts = nom.split(".")
            for i in range(1, len(parts)):         # tout prefixe est un paquet, `__init__` ou non
                self.paquets.add(".".join(parts[:i]))
            if rel.endswith("/__init__.py"):
                self.paquets.add(nom)

    def __contains__(self, nom) -> bool:
        return nom in self.arbres or nom in self.paquets

    def paquet_de(self, nom: str) -> str:
        return nom if nom in self.paquets else nom.rpartition(".")[0]

    def liaisons(self, nom: str) -> Liaisons:
        lia = self._lia.get(nom)
        if lia is None:
            tree = self.arbres.get(nom)
            lia = liaisons_de(tree) if tree is not None else Liaisons()
            self._lia[nom] = lia
        return lia

    def noms_exposes(self, nom: str, pile: "frozenset | None" = None) -> tuple:
        """(noms exposes, opaque, raison), `import *` RESOLUS recursivement.

        La pile coupe les cycles d'`import *` : deux facades qui se re-exportent l'une l'autre
        boucleraient. Un cycle n'est pas une opacite -- on rend ce qu'on a lu de chaque cote.
        """
        if pile is None and nom in self._exp:
            return self._exp[nom]
        pile = pile or frozenset()
        if nom not in self:
            return frozenset(), True, "module hors index"
        lia = self.liaisons(nom)
        noms, opaque, raison = set(lia.noms), lia.opaque, lia.raison
        paquet = self.paquet_de(nom)
        for cible, level in lia.etoiles:
            abs_nom = resoudre_relatif(cible, level, paquet)
            if abs_nom is None or abs_nom not in self:
                opaque = True
                raison = "import * d'une cible hors index (%s)" % (abs_nom or cible)
                continue
            if abs_nom in pile:
                continue
            sous, sous_op, sous_r = self.noms_exposes(abs_nom, pile | {nom})
            noms |= set(sous)
            if sous_op:
                opaque, raison = True, "import * de %s, opaque : %s" % (abs_nom, sous_r)
        res = (frozenset(noms), opaque, raison)
        if not pile:
            self._exp[nom] = res
        return res


#: Noms pointes qui designent un PAQUET (un `__init__.py`, ou un repertoire-espace-de-noms).
#: Pose par `analyser` -- il sert a resoudre les imports RELATIFS du fichier balaye.
_PAQUETS: set = set()


# ------------------------------------------------------------------------------------------
# Balayage
# ------------------------------------------------------------------------------------------

def _nomme_exc(node) -> bool:
    noms = []
    if isinstance(node, ast.Tuple):
        noms = [e for e in node.elts]
    else:
        noms = [node]
    for n in noms:
        base = n.attr if isinstance(n, ast.Attribute) else (n.id if isinstance(n, ast.Name)
                                                            else None)
        if base in EXC_IMPORT:
            return True
    return False


def imports_de(rel: str, tree: ast.AST) -> list:
    """[(ligne, module absolu, nom importe, differe)] des `from X import Y` du fichier.

    `differe` = l'import est dans un corps de `def`/`class`. Il ne change RIEN au verdict -- il
    est rapporte parce que c'est LUI qui rend la faute invisible a la collecte pytest, donc
    l'information qui explique pourquoi elle a survecu deux jours.
    """
    nom_fichier = nom_pointe(rel)
    paquet = ""
    if nom_fichier:
        paquet = nom_fichier if nom_fichier in _PAQUETS else nom_fichier.rpartition(".")[0]

    out = []

    def visiter(noeud, dans_corps: bool, sous_garde: bool) -> None:
        """UNE seule descente porte les deux etats : `dans_corps` (import differe) et
        `sous_garde` (un `try` englobant attrape ImportError -- import optionnel, exempte)."""
        if isinstance(noeud, ast.Try) or type(noeud).__name__ == "TryStar":
            garde = any(h.type is None or _nomme_exc(h.type) for h in noeud.handlers)
            for n in noeud.body:
                visiter(n, dans_corps, sous_garde or garde)
            for h in noeud.handlers:                       # dans le HANDLER, plus de filet
                for n in h.body:
                    visiter(n, dans_corps, sous_garde)
            for champ in ("orelse", "finalbody"):
                for n in getattr(noeud, champ, []) or []:
                    visiter(n, dans_corps, sous_garde)
            return
        if isinstance(noeud, ast.ImportFrom):
            if not sous_garde:
                abs_nom = resoudre_relatif(noeud.module, noeud.level, paquet)
                if abs_nom:
                    for a in noeud.names:
                        if a.name != "*":
                            out.append((noeud.lineno, abs_nom, a.name, dans_corps))
            return
        corps = dans_corps or isinstance(noeud, (ast.FunctionDef, ast.AsyncFunctionDef,
                                                 ast.ClassDef))
        for enfant in ast.iter_child_nodes(noeud):
            visiter(enfant, corps, sous_garde)

    visiter(tree, False, False)
    return out


def analyser(sources: dict) -> tuple:
    """(hits, ecartes) -- hits = [(rel, ligne, module, nom, differe)]."""
    index = Index(sources)
    _PAQUETS.clear()
    _PAQUETS.update(index.paquets)
    hits, ecartes = [], {}
    for rel, tree in sorted(sources.items()):
        for ligne, mod, nom, differe in imports_de(rel, tree):
            if mod not in index:
                continue                                   # stdlib / tiers : aucun signal
            exposes, opaque, raison = index.noms_exposes(mod)
            if opaque:
                ecartes.setdefault(mod, raison)
                continue
            if nom in exposes:
                continue
            if ("%s.%s" % (mod, nom)) in index:            # sous-module d'un paquet
                continue
            hits.append((rel, ligne, mod, nom, differe))
    return hits, ecartes


# ------------------------------------------------------------------------------------------
# Etape 0 -- auto-test des detecteurs
# ------------------------------------------------------------------------------------------
#
# Chaque cas est un MINI-DEPOT : {chemin relatif: source}, et le nombre de hits attendu. Un cas
# NEGATIF vaut son jumeau positif -- c'est lui qui interdit d'elargir le motif pour faire mordre.

R = ROOT_REL
CAS = [
    ("LA faute de #462 : nom retire, import DIFFERE chez le consommateur",
     {R + "/cible.py": "def garde():\n    pass\n",
      R + "/probe_x.py": "from cible import garde, BUILD_HASH\n",
      R + "/tests/test_y.py": "def fixture():\n    from probe_x import garde\n"}, 1),
    ("nom present : vert",
     {R + "/cible.py": "BUILD_HASH = 'abc'\n",
      R + "/probe_x.py": "from cible import BUILD_HASH\n"}, 0),
    ("import DIFFERE d'un nom mort (le corps de fonction est le gisement)",
     {R + "/cible.py": "A = 1\n",
      R + "/probe_x.py": "def main():\n    from cible import B\n    return B\n"}, 1),
    ("liaison sous un `if` de niveau module : lie quand meme",
     {R + "/cible.py": "import os\nif os.name == 'nt':\n    SEP = '\\\\'\nelse:\n    SEP = '/'\n",
      R + "/probe_x.py": "from cible import SEP\n"}, 0),
    ("liaison par `try/except ImportError` chez la CIBLE : lie quand meme",
     {R + "/cible.py": "try:\n    from json import loads\nexcept ImportError:\n"
                       "    def loads(s):\n        return None\n",
      R + "/probe_x.py": "from cible import loads\n"}, 0),
    ("def / class / alias d'import",
     {R + "/cible.py": "import os as _os\n\n\ndef f():\n    pass\n\n\nclass C:\n    pass\n",
      R + "/probe_x.py": "from cible import f, C, _os\n"}, 0),
    ("deballage de tuple au niveau module",
     {R + "/cible.py": "A, B = 1, 2\n",
      R + "/probe_x.py": "from cible import A, B\n"}, 0),
    ("`global` assigne dans une fonction : LIE (sinon faux positif)",
     {R + "/cible.py": "def init():\n    global CACHE\n    CACHE = {}\n",
      R + "/probe_x.py": "from cible import CACHE\n"}, 0),
    ("nom defini seulement DANS une fonction : ne lie RIEN",
     {R + "/cible.py": "def f():\n    LOCAL = 1\n    return LOCAL\n",
      R + "/probe_x.py": "from cible import LOCAL\n"}, 1),
    ("`import *` resolu : le nom vient de la facade",
     {R + "/paq/__init__.py": "",
      R + "/paq/base.py": "GC = 1\n",
      R + "/paq/facade.py": "from .base import *  # noqa: F401,F403\n",
      R + "/probe_x.py": "from paq.facade import GC\n"}, 0),
    ("`import *` d'une cible HORS index : module OPAQUE, aucun verdict",
     {R + "/facade.py": "from numpy import *  # noqa: F401,F403\n",
      R + "/probe_x.py": "from facade import zeros\n"}, 0),
    ("`globals()[...]` chez la cible : OPAQUE",
     {R + "/cible.py": "for k in ('A', 'B'):\n    globals()[k] = k\n",
      R + "/probe_x.py": "from cible import A\n"}, 0),
    ("`__getattr__` de module (PEP 562) chez la cible : OPAQUE",
     {R + "/cible.py": "def __getattr__(nom):\n    return nom\n",
      R + "/probe_x.py": "from cible import QuoiQueCeSoit\n"}, 0),
    ("import garde par `try/except ImportError` chez le CONSOMMATEUR : optionnel, exempte",
     {R + "/cible.py": "A = 1\n",
      R + "/probe_x.py": "try:\n    from cible import B\nexcept ImportError:\n    B = None\n"},
     0),
    ("meme garde, mais l'import est dans le HANDLER : plus de filet, il compte",
     {R + "/cible.py": "A = 1\n",
      R + "/probe_x.py": "try:\n    import json\nexcept ImportError:\n"
                         "    from cible import B\n"}, 1),
    ("module TIERS / stdlib : aucun signal (on ne lit pas leurs liaisons)",
     {R + "/probe_x.py": "from pathlib import CeQuiNExistePas\n"}, 0),
    ("sous-module d'un paquet importe par son nom",
     {R + "/paq/__init__.py": "",
      R + "/paq/outil.py": "def f():\n    pass\n",
      R + "/probe_x.py": "from paq import outil\n"}, 0),
    ("paquet-espace-de-noms (SANS __init__.py) : indexe, donc lisible",
     {R + "/tests/engine/_aide.py": "def monte():\n    pass\n",
      R + "/probe_x.py": "from tests.engine._aide import monte, DISPARU\n"}, 1),
    ("import RELATIF au sein d'un paquet",
     {R + "/paq/__init__.py": "",
      R + "/paq/base.py": "A = 1\n",
      R + "/paq/sous/__init__.py": "",
      R + "/paq/sous/x.py": "from ..base import A, ABSENT\n"}, 1),
    ("fichier HORS racine d'import : ses imports ne resolvent pas, mais il est balaye",
     {"lib/hex.py": "from cible import RIEN\n",
      R + "/cible.py": "A = 1\n"}, 1),
    ("liaison par `with ... as` et boucle `for` de niveau module",
     {R + "/cible.py": "import contextlib\nwith contextlib.suppress(Exception) as CTX:\n"
                       "    pass\nfor ITEM in (1, 2):\n    pass\n",
      R + "/probe_x.py": "from cible import CTX, ITEM\n"}, 0),
]


def self_test(verbose: bool) -> list:
    bad = []
    for nom, fichiers, attendu in CAS:
        sources = {}
        for rel, src in fichiers.items():
            try:
                sources[rel] = ast.parse(src, filename=rel)
            except SyntaxError as exc:                       # noqa: PERF203
                print("   FAIL auto-test %s : source invalide (%s)" % (nom, exc))
                bad.append(nom)
                sources = None
                break
        if sources is None:
            continue
        hits, _ = analyser(sources)
        ok = len(hits) == attendu
        if verbose or not ok:
            print("   %-5s %-62s hits=%d/%d" % ("OK" if ok else "FAIL", nom, len(hits), attendu))
        if not ok:
            bad.append(nom)
    return bad


# ------------------------------------------------------------------------------------------

def charger_arbre() -> tuple:
    """({rel: AST}, lus, illisibles) de tous les `.py` suivis par git."""
    rels = fichiers_suivis()
    chemins = [REPO / r for r in rels]
    sources, illisibles = {}, []
    for rel, data in zip(rels, repo_read.read_bytes_many(chemins)):
        if data is None:
            illisibles.append(rel)
            continue
        try:
            src = repo_read.to_text(data)
        except UnicodeDecodeError:
            illisibles.append(rel)
            continue
        try:
            sources[rel] = ast.parse(src, filename=rel)
        except (SyntaxError, ValueError):
            illisibles.append(rel)
    return sources, len(rels), illisibles


def main(argv) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("-v", "--verbose", action="store_true")
    ap.add_argument("--self-test", action="store_true",
                    help="ne joue QUE l'auto-test des detecteurs, en detail")
    args = ap.parse_args(argv)

    print("[462r5] racine : %s" % REPO)
    mauvais = self_test(args.verbose or args.self_test)
    print("[462r5] etape 0 : auto-test des detecteurs -- %d/%d cas, %d en echec"
          % (len(CAS) - len(mauvais), len(CAS), len(mauvais)))
    for nom in mauvais:
        print("   FAIL auto-test : %s" % nom)
    if args.self_test:
        print("[462r5] VERDICT: %s" % ("PASS" if not mauvais else "FAIL (%d)" % len(mauvais)))
        return 0 if not mauvais else 1

    sources, lus, illisibles = charger_arbre()
    hits, ecartes = analyser(sources)
    index_n = sum(1 for r in sources if nom_pointe(r) is not None)
    print("[462r5] etape 1 : %d fichier(s) .py suivi(s), %d analyse(s), %d module(s) a l'index"
          % (lus, len(sources), index_n))

    # ANCRAGE du perimetre. Un balayage qui rend ZERO fichier rend aussi ZERO hit, et se lit
    # << rien a signaler >> -- c'est le faux vert que #440 a mesure sur la correction naive du
    # filtre de worktrees (0 fichier, VERDICT: PASS). Le temoin ne se saisit pas : c'est CE
    # fichier. S'il n'est ni suivi par git, ni sous la racine d'import, ni a l'index, alors ce
    # que le probe vient de balayer n'est pas ce qu'il croit balayer.
    moi_rel = _rel(Path(__file__).resolve())
    moi_nom = nom_pointe(moi_rel) if moi_rel else None
    perimetre_ko = []
    if moi_rel is None or moi_rel not in sources:
        perimetre_ko.append("ce fichier n'est pas dans le balayage (%s)" % moi_rel)
    elif moi_nom is None or moi_nom not in Index(sources):
        perimetre_ko.append("ce fichier ne resout pas en module de 1re partie (%s)" % moi_rel)
    for msg in perimetre_ko:
        print("   FAIL ancrage du perimetre : %s -- un balayage vide rend 0 hit et se lit"
              " comme un verdict. Racine d'import attendue : %s/" % (msg, ROOT_REL))
    if illisibles:
        print("   (%d fichier(s) ECARTE(s) -- illisible ou non parsable : %s)"
              % (len(illisibles), ", ".join(illisibles[:3])))
    if args.verbose and ecartes:
        print("   modules OPAQUES (aucun verdict sur leurs noms) :")
        for mod, raison in sorted(ecartes.items()):
            print("      %-52s %s" % (mod, raison))

    print("[462r5] etape 2 : %d import(s) de premiere partie qui ne resolvent PAS" % len(hits))
    for rel, ligne, mod, nom, differe in hits:
        print("   FAIL %s:%d  `from %s import %s` -- le module EXISTE, le nom N'Y EST PLUS%s"
              % (rel, ligne, mod, nom,
                 " (import DIFFERE : invisible a `pytest --collect-only`)" if differe else ""))
    if hits:
        print("   => soit le nom a ete retire et l'appelant doit suivre (mesure #462 : BUILD_HASH")
        print("      retire par #431, 10 tests morts 2 jours), soit la cible a change de foyer.")

    ko = len(mauvais) + len(hits) + len(perimetre_ko)
    print("[462r5] VERDICT: %s" % ("PASS" if ko == 0 else "FAIL (%d)" % ko))
    return 0 if ko == 0 else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
