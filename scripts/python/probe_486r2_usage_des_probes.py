#!/usr/bin/env python
"""Probe #486-r2 -- LE DISCRIMINANT D'USAGE DES PROBES, et le cliquet qui garde l'elagage.

LE PROBLEME
-----------
`scripts/python/` porte des CENTAINES de probes de premier niveau, tous melanges : ceux que la
banque de cliquets joue, ceux qu'un test appelle, ceux qu'un autre script appelle, ceux que plus
rien ne joue -- et ceux que plus rien ne NOMME. Rien ne les distinguait.

DEUX AXES, JAMAIS CONFONDUS
---------------------------
  * USAGE     -- est-il encore EXECUTABLE ? (etapes 2) ; question statique, sans le lancer :
                 beaucoup tapent le live par RPC, les lancer serait un cout absurde et un
                 effet de bord sur la session partagee.
  * CITATION  -- qui le nomme, et COMMENT ? (etape 3) : la banque, un test, un script (citation
                 EXECUTABLE, lue a l'AST) ou seulement de la PROSE (docs, commentaires,
                 docstrings, messages de commit, corps de PR).

<< Rien ne le joue >> n'est PAS << mort >>. Un probe est un INSTRUMENT A MAIN qu'on relance pour
re-deriver un chiffre (`reference_probes_are_not_tests` : 4 % d'assert). Un instrument vivant se
garde. Le SEUL croisement qui prouve la mort est ORPHELIN (nomme NULLE PART, union large) ET NON
EXECUTABLE.

L'ECUEIL, MESURE : 22 FAUX POSITIFS
-----------------------------------
Une premiere tentative de discriminant << le probe resout-il encore ses imports ? >> a rendu 22
morts. TOUS FAUX. Cause : les probes posent `sys.path.insert(0, str(PYDIR / "tests" / "engine" /
"runner"))` puis `from _charge_regime import ...`, et le helper vit dans
`scripts/python/tests/engine/runner/`. Le detecteur cherchait le module A COTE du probe.

=> Le discriminant MODELISE les `sys.path` que le probe pose LUI-MEME, par evaluation symbolique
   des idiomes reels (`Path(__file__).resolve().parent`, `os.path.dirname(os.path.abspath(
   __file__))`, `.parents[2]`, `os.path.join(...)`, `/`), avec propagation des affectations de
   niveau module. Un argument de `sys.path.insert` qu'on ne sait PAS evaluer rend le probe
   INDETERMINE -- jamais MORT. L'etape 2b re-mesure les 22 formes reelles a chaque passage.

LE CRITERE D'EXECUTABILITE (etape 2)
------------------------------------
  1. la source COMPILE (`compile()`) ; sinon MORT ;
  2. chaque import de NIVEAU MODULE resout, contre `sys.path` modelise + stdlib + site-packages ;
     sinon MORT (module INTROUVABLE) ;
  3. pour un `from X import Y` dont `X` est un module du depot : `Y` est bien une liaison de `X`
     (ou un sous-module) ; sinon MORT. C'est le critere de `probe_462r5`, dont les liaisons sont
     REUTILISEES ici plutot que reimplementees -- un second detecteur derive n'a aucune valeur.

CE QU'IL NE COMPTE PAS, ET POURQUOI
-----------------------------------
  * un import DIFFERE (dans un corps de `def`/`class`) qui ne resout pas : rapporte, jamais
    fatal. Il ne casse que la branche qui l'execute, et le juger tuerait des probes dont le
    chemin principal marche. `probe_462r5` le garde deja, lui, sur l'axe << nom disparu >>.
  * un import garde par `try/except ImportError` : l'auteur a DECLARE la dependance optionnelle.
  * un module TIERS absent de CETTE machine : c'est l'environnement, pas le depot. Il sort en
    INDETERMINE, jamais en MORT.

LE CLIQUET (etape 5) -- BLOQUANT
--------------------------------
Un probe a la fois ORPHELIN et NON EXECUTABLE ne doit plus pouvoir entrer. C'est le seul seau
dont la mort est PROUVEE, donc le seul que le cliquet garde. Il SAIT rougir : l'auto-epreuve de
l'etape 0 lui soumet des formes attendues MORTES *et* VIVANTES, et l'etape 2c mute une source
REELLE (en memoire) pour verifier que la mutation MORD.

TRI-ETAT (#471) : toute panne d'outil (git muet, `gh` muet, arbre illisible) sort en
EX_NON_MESURE = 99, jamais en vert ni en rouge. Un corpus ampute ferait declarer ORPHELIN un
probe cite -- exactement la faute qui supprimerait du code vivant.

ASCII only (console Windows cp1252).
Usage: python probe_486r2_usage_des_probes.py [--verbose] [--self-test] [--lister <seau>]
                                              [--csv <fichier>] [--sans-pr]
"""
from __future__ import annotations

import argparse
import ast
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
REPO = PYDIR.parents[1]
if str(PYDIR) not in sys.path:
    sys.path.insert(0, str(PYDIR))

import repo_read  # noqa: E402
from probe_462r5_dead_imports import liaisons_de  # noqa: E402

#: << RIEN N'A ETE MESURE >>. Meme sentinelle que `ratchets-verdict.ps1` / `probe_457`.
EX_NON_MESURE = 99

#: Exceptions dont la capture DECLARE qu'un import peut echouer (identique a `probe_462r5`).
EXC_IMPORT = ("ImportError", "ModuleNotFoundError", "Exception", "BaseException")

#: Les quatre helpers de montage qui vivent SOUS `tests/engine/runner/` et que 22 probes
#: importent apres un `sys.path.insert`. C'est LA forme qui a produit les 22 faux positifs :
#: l'etape 2b re-mesure que TOUS leurs importateurs sortent VIVANTS. La liste des NOMS est
#: derivee du disque, jamais saisie -- voir `helpers_hors_pydir()`.
DIR_HELPERS = ("tests", "engine", "runner")


# ==========================================================================================
#  0. LECTURE DE L'ARBRE
# ==========================================================================================

class Indisponible(RuntimeError):
    """Le corpus n'a PAS pu etre constitue. Ni vert ni rouge -- non mesure."""


def _git(args, quoi: str) -> str:
    try:
        res = subprocess.run(["git", "-C", str(REPO)] + args, capture_output=True, text=True,
                             encoding="utf-8", errors="replace", timeout=180)
    except (OSError, subprocess.SubprocessError) as exc:
        raise Indisponible("%s injouable (%s)" % (quoi, exc)) from exc
    if res.returncode not in (0, 1):          # `git grep` rend 1 quand il ne trouve rien
        raise Indisponible("%s rc=%d -- %s"
                           % (quoi, res.returncode, " ".join((res.stderr or "").split())[:200]))
    return res.stdout


def fichiers_suivis() -> list:
    """Chemins RELATIFS (posix) de TOUT fichier suivi par git dans CE checkout.

    `git ls-files` est le perimetre : depuis un worktree il ne voit que ce worktree, et depuis
    l'arbre principal il ne descend pas dans `.claude/worktrees` (#434). Une liste VIDE serait
    une reponse VALIDE de l'outil, donc un fait sur le depot -- mais un fait qui invaliderait
    tout : elle leve.
    """
    out = [l.strip().replace("\\", "/") for l in _git(["ls-files"], "`git ls-files`").splitlines()
           if l.strip()]
    if not out:
        raise Indisponible("`git ls-files` rc=0 mais liste VIDE -- perimetre effondre")
    return out


def population(suivis) -> list:
    """Les probes de PREMIER NIVEAU de `scripts/python`, DERIVES de `git ls-files`.

    Le filtre est explicite et se DIT (l'appelant l'imprime) : `scripts/python/probe_*.py` sans
    aucun `/` supplementaire. Un recenseur ne peut pas rendre zero sur ce qu'il ne visite pas --
    la population ne se saisit donc nulle part a la main.
    """
    return sorted(r for r in suivis
                  if r.startswith("scripts/python/probe_") and r.endswith(".py")
                  and "/" not in r[len("scripts/python/"):])


def probes_hors_racine(suivis) -> list:
    """CE QUE LE FILTRE ECARTE : les `probe_*.py` qui ne sont PAS a la racine de scripts/python."""
    return sorted(r for r in suivis
                  if r.endswith(".py") and Path(r).name.startswith("probe_")
                  and not (r.startswith("scripts/python/probe_")
                           and "/" not in r[len("scripts/python/"):]))


# ==========================================================================================
#  1. EVALUATION SYMBOLIQUE DES `sys.path` QUE LE PROBE POSE LUI-MEME
# ==========================================================================================
#
#  C'est LE point que la premiere tentative avait rate (22 faux positifs). On n'apparie pas des
#  chaines de caracteres : on evalue les EXPRESSIONS, avec les affectations de niveau module dans
#  l'environnement. Toute expression non evaluable rend le probe INDETERMINE, jamais MORT.

_INCONNU = object()


class EvaluateurChemin:
    """Evalue les expressions de chemin d'un module (Path ET str, indifferemment).

    Les idiomes couverts sont ceux REELLEMENT ecrits dans le depot -- ils se re-derivent par
    `--verbose` (etape 2 imprime les arguments non evalues). Un idiome neuf n'est jamais exempte
    en silence : il fait sortir son probe en INDETERMINE, ce qui se voit.
    """

    def __init__(self, fichier: Path):
        self.fichier = fichier
        self.env: dict = {"__file__": fichier}
        self.non_evalues: list = []

    # ---- expressions ---------------------------------------------------------------------
    def ev(self, node):
        """-> Path, ou `_INCONNU`."""
        if isinstance(node, ast.Constant):
            if not isinstance(node.value, str):
                return _INCONNU
            v = node.value
            if v in (".", "./", ""):
                # Le CWD documente d'un probe est `scripts/python` (`ratchets.ps1` fait
                # `Set-Location $WorkDir`, et la doctrine dit << depuis scripts/python >>).
                return PYDIR
            p = Path(v)
            return p if p.is_absolute() else (PYDIR / p)
        if isinstance(node, ast.Name):
            return self.env.get(node.id, _INCONNU)
        if isinstance(node, ast.Attribute):
            base = self.ev(node.value)
            if base is _INCONNU:
                return _INCONNU
            if node.attr == "parent":
                return base.parent
            if node.attr == "parents":
                return _Parents(base)
            return _INCONNU
        if isinstance(node, ast.Subscript):
            base = self.ev(node.value)
            if isinstance(base, _Parents) and isinstance(node.slice, ast.Constant) \
                    and isinstance(node.slice.value, int):
                p = base.origine
                for _ in range(node.slice.value + 1):
                    p = p.parent
                return p
            return _INCONNU
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
            g, d = self.ev(node.left), self.ev(node.right)
            if g is _INCONNU or d is _INCONNU:
                return _INCONNU
            # `d` est deja resolu contre PYDIR par `ev(Constant)` : on ne veut que son nom.
            if isinstance(node.right, ast.Constant):
                return g / node.right.value
            return _INCONNU
        if isinstance(node, ast.Call):
            return self.ev_appel(node)
        return _INCONNU

    def ev_appel(self, node: ast.Call):
        """`nom` = la forme pointee COMPLETE quand elle se lit, `court` = le dernier attribut.

        Les deux sont necessaires, et c'est l'auto-epreuve qui l'a impose : `_dotted` rend `None`
        sur `Path(__file__).resolve()` (la base est un Call, pas un Name), donc un critere fonde
        sur le seul nom pointe manquait l'idiome le PLUS frequent du depot -- exactement la forme
        des 22 faux positifs. `court` se lit toujours, lui.
        """
        nom = _dotted(node.func) or ""
        if isinstance(node.func, ast.Attribute):
            court = node.func.attr
        elif isinstance(node.func, ast.Name):
            court = node.func.id
        else:
            return _INCONNU
        args = node.args
        if court in ("Path", "str", "fspath", "PurePath", "PosixPath", "WindowsPath"):
            return self.ev(args[0]) if args else _INCONNU
        if court in ("resolve", "absolute", "expanduser", "as_posix"):
            base = node.func.value if isinstance(node.func, ast.Attribute) else None
            return self.ev(base) if base is not None else _INCONNU
        if court in ("abspath", "realpath", "normpath"):
            return self.ev(args[0]) if args else _INCONNU
        if court == "dirname":
            base = self.ev(args[0]) if args else _INCONNU
            return _INCONNU if base is _INCONNU else base.parent
        # `join` est le seul nom AMBIGU (`", ".join(...)` n'est pas un chemin) : il n'est reconnu
        # que sous sa forme `os.path.join` / `path.join`, ou en Name nu (`from os.path import
        # join`). Un `join` de chaine porte une Constant en base, donc ne passe ni l'un ni l'autre.
        if nom in ("os.path.join", "path.join") or (isinstance(node.func, ast.Name)
                                                    and node.func.id == "join"):
            if not args:
                return _INCONNU
            base = self.ev(args[0])
            if base is _INCONNU:
                return _INCONNU
            for a in args[1:]:
                if not (isinstance(a, ast.Constant) and isinstance(a.value, str)):
                    return _INCONNU
                base = base / a.value
            return base
        return _INCONNU

    # ---- statements ----------------------------------------------------------------------
    def parcourir(self, tree: ast.AST) -> list:
        """Rend les repertoires AJOUTES a `sys.path`, en propageant les affectations.

        On visite le module dans l'ORDRE, en descendant dans tout le flot de controle ET dans les
        corps de fonction : un `sys.path.insert` ecrit dans une fonction de montage compte quand
        meme. Y entrer ne peut qu'ELARGIR le chemin, donc rendre le verdict PLUS conservateur.
        """
        ajouts: list = []

        def visiter(corps):
            for n in corps:
                if isinstance(n, ast.Assign) and len(n.targets) == 1 \
                        and isinstance(n.targets[0], ast.Name):
                    val = self.ev(n.value)
                    if val is not _INCONNU:
                        self.env[n.targets[0].id] = val
                elif isinstance(n, ast.AnnAssign) and isinstance(n.target, ast.Name) \
                        and n.value is not None:
                    val = self.ev(n.value)
                    if val is not _INCONNU:
                        self.env[n.target.id] = val
                elif isinstance(n, ast.Expr) and isinstance(n.value, ast.Call):
                    self._peut_etre_sys_path(n.value, ajouts)
                for champ in ("body", "orelse", "finalbody"):
                    sous = getattr(n, champ, None)
                    if isinstance(sous, list):
                        visiter(sous)
                for h in getattr(n, "handlers", []) or []:
                    visiter(h.body)
                for c in getattr(n, "cases", []) or []:
                    visiter(c.body)

        visiter(getattr(tree, "body", []))
        return ajouts

    def _peut_etre_sys_path(self, call: ast.Call, ajouts: list) -> None:
        # SEULE la forme pleine `sys.path.<...>` compte. Accepter `path.insert` / `path.append`
        # nus a ete essaye et rend des FAUX INDETERMINES : `probe_124` fait un BFS avec une
        # variable locale `path`, et ses `path.append(p)` passaient pour des `sys.path` non
        # evaluables. Le depot n'ecrit nulle part `from sys import path` (verifie).
        nom = _dotted(call.func) or ""
        if nom not in ("sys.path.insert", "sys.path.append"):
            return
        arg = call.args[1] if (nom.endswith("insert") and len(call.args) > 1) else (
            call.args[0] if (nom.endswith("append") and call.args) else None)
        if arg is None:
            return
        val = self.ev(arg)
        if val is _INCONNU:
            self.non_evalues.append(_src(arg))
            return
        ajouts.append(Path(val))


class _Parents:
    """Valeur intermediaire pour `X.parents[k]` -- `parents` seul n'est pas un chemin."""

    __slots__ = ("origine",)

    def __init__(self, origine: Path):
        self.origine = origine


def _dotted(node) -> "str | None":
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = _dotted(node.value)
        return base + "." + node.attr if base else None
    return None


def _src(node) -> str:
    try:
        return ast.unparse(node)[:110]
    except Exception:                                        # pragma: no cover
        return "<?>"


# ==========================================================================================
#  2. RESOLUTION DES MODULES
# ==========================================================================================

def _stdlib() -> frozenset:
    noms = set(getattr(sys, "stdlib_module_names", ()))
    noms |= set(sys.builtin_module_names)
    return frozenset(noms)


STDLIB = _stdlib()


class Arbre:
    """Le contenu du depot, lu UNE fois : sources + ASTs, indexes par chemin ABSOLU."""

    def __init__(self, suivis):
        self.rels = suivis
        self.abs_par_rel = {r: (REPO / r) for r in suivis}
        self.existe = {os.path.normcase(str(REPO / r)) for r in suivis}
        self.reps = set()
        for r in suivis:
            p = Path(r).parent
            while str(p) not in (".", ""):
                self.reps.add(os.path.normcase(str(REPO / p)))
                p = p.parent
        self._src: dict = {}
        self._ast: dict = {}
        self._lia: dict = {}
        self._noms_artefacts: "set | None" = None

    def artefact(self, top: str) -> bool:
        """Le nom `top` designe-t-il un artefact DU DEPOT (`<top>.py`, ou un repertoire) ?

        C'est le SEUL discriminant disponible entre les deux causes d'un << module introuvable >>
        (le depot ne porte aucun manifeste de dependances -- verifie : ni `requirements*.txt`, ni
        `pyproject.toml`, ni `Pipfile`) :
          * l'artefact EXISTE dans l'arbre -> le depot est accuse (mauvais `sys.path`) -> MORT ;
          * il n'existe pas -> tierce partie absente de CETTE machine, OU module supprime : les
            deux sont INDISCERNABLES ici, donc INDETERMINE. C'est la borne assumee de ce
            discriminant, et elle penche du cote sur : on ne supprime jamais sur un doute.
        """
        if self._noms_artefacts is None:
            noms = set()
            for r in self.rels:
                p = Path(r)
                if p.suffix == ".py":
                    noms.add(p.stem)
                for part in p.parent.parts:
                    noms.add(part)
            self._noms_artefacts = noms
        return top in self._noms_artefacts

    def est_fichier(self, chemin: Path) -> bool:
        return os.path.normcase(str(chemin)) in self.existe

    def est_repertoire(self, chemin: Path) -> bool:
        return os.path.normcase(str(chemin)) in self.reps

    def source(self, chemin: Path) -> "str | None":
        cle = os.path.normcase(str(chemin))
        if cle not in self._src:
            try:
                self._src[cle] = repo_read.to_text(chemin.read_bytes())
            except (OSError, UnicodeDecodeError):
                self._src[cle] = None
        return self._src[cle]

    def arbre(self, chemin: Path):
        cle = os.path.normcase(str(chemin))
        if cle not in self._ast:
            src = self.source(chemin)
            try:
                self._ast[cle] = ast.parse(src, filename=str(chemin)) if src is not None else None
            except (SyntaxError, ValueError):
                self._ast[cle] = None
        return self._ast[cle]

    def liaisons(self, chemin: Path):
        cle = os.path.normcase(str(chemin))
        if cle not in self._lia:
            tree = self.arbre(chemin)
            self._lia[cle] = liaisons_de(tree) if tree is not None else None
        return self._lia[cle]


#: Resultats de resolution.
LOCAL, STDLIB_, TIERS, ABSENT = "local", "stdlib", "tiers", "absent"


def _tiers_dispo(top: str) -> bool:
    """`top` est-il installe HORS du depot ? PathFinder n'IMPORTE rien (pas d'effet de bord).

    Les entrees de `sys.path` qui pointent DANS le depot sont retirees : sans cela, un module du
    depot introuvable par le modele de chemins serait blanchi par le `sys.path` de CE processus,
    et une vraie mort passerait pour une dependance tierce.
    """
    import importlib.machinery
    racine = os.path.normcase(str(REPO))
    chemins = [p for p in sys.path
               if p and not os.path.normcase(os.path.abspath(p)).startswith(racine)]
    try:
        return importlib.machinery.PathFinder.find_spec(top, path=chemins) is not None
    except (ImportError, ValueError, AttributeError):
        return False


def resoudre_module(nom: str, chemins, arbre: Arbre, tiers=None):
    """(genre, chemin du fichier ou None). `genre` in {LOCAL, STDLIB_, TIERS, ABSENT}."""
    tiers = tiers or _tiers_dispo
    parts = nom.split(".")
    for base in chemins:
        cur = base
        ok = True
        for p in parts[:-1]:
            cur = cur / p
            if not arbre.est_repertoire(cur):
                ok = False
                break
        if not ok:
            continue
        dernier = cur / parts[-1]
        if arbre.est_fichier(dernier.with_suffix(".py")):
            return LOCAL, dernier.with_suffix(".py")
        if arbre.est_fichier(dernier / "__init__.py"):
            return LOCAL, dernier / "__init__.py"
        if arbre.est_repertoire(dernier):
            return LOCAL, None                    # paquet-espace-de-noms : rien a lire
    top = parts[0]
    if top in STDLIB:
        return STDLIB_, None
    if tiers(top):
        return TIERS, None
    return ABSENT, None


# ==========================================================================================
#  3. LE DISCRIMINANT D'USAGE
# ==========================================================================================

VIVANT, MORT, INDETERMINE = "VIVANT", "MORT", "INDETERMINE"


class Usage:
    def __init__(self, etat: str, motifs=None, differes=None, chemins=None, signales=None):
        self.etat = etat
        self.motifs = motifs or []          # ce qui TUE (etat MORT) ou empeche (INDETERMINE)
        self.differes = differes or []      # imports differes qui ne resolvent pas : rapportes
        self.chemins = chemins or []
        #: Noms de MODULE signales comme non resolus, toutes categories confondues. C'est le
        #: canal MACHINE de l'etape 2c : chercher le nom dans le TEXTE d'un message est un
        #: appariement de chaine qui se casse au premier reformatage -- il l'a fait, et la
        #: contre-epreuve accusait alors le discriminant au lieu de son propre lecteur.
        self.signales = signales or set()


def _imports(tree: ast.AST) -> list:
    """[(ligne, kind, module, nom, differe)] -- `kind` in {'import', 'from'}.

    Les imports gardes par un `try/except ImportError` sont EXEMPTES : l'auteur a declare la
    dependance optionnelle (meme regle que `probe_462r5`). Un import ecrit DANS le handler, lui,
    n'a plus de filet et compte.

    Un `if TYPE_CHECKING:` compte comme DIFFERE : le bloc n'est JAMAIS execute a l'import, donc
    un nom mort qui n'y vit que ne peut pas empecher le probe de demarrer.
    """
    out = []

    def nomme_exc(node) -> bool:
        elts = node.elts if isinstance(node, ast.Tuple) else [node]
        for n in elts:
            base = n.attr if isinstance(n, ast.Attribute) else (
                n.id if isinstance(n, ast.Name) else None)
            if base in EXC_IMPORT:
                return True
        return False

    def visiter(noeud, dans_corps: bool, sous_garde: bool) -> None:
        if isinstance(noeud, ast.Try) or type(noeud).__name__ == "TryStar":
            garde = any(h.type is None or nomme_exc(h.type) for h in noeud.handlers)
            for n in noeud.body:
                visiter(n, dans_corps, sous_garde or garde)
            for h in noeud.handlers:
                for n in h.body:
                    visiter(n, dans_corps, sous_garde)
            for champ in ("orelse", "finalbody"):
                for n in getattr(noeud, champ, []) or []:
                    visiter(n, dans_corps, sous_garde)
            return
        if isinstance(noeud, ast.Import):
            if not sous_garde:
                for a in noeud.names:
                    out.append((noeud.lineno, "import", a.name, None, dans_corps))
            return
        if isinstance(noeud, ast.ImportFrom):
            if not sous_garde and noeud.level == 0 and noeud.module:
                for a in noeud.names:
                    out.append((noeud.lineno, "from", noeud.module,
                                None if a.name == "*" else a.name, dans_corps))
            return
        if isinstance(noeud, ast.If) and "TYPE_CHECKING" in _src(noeud.test):
            for n in noeud.body:                       # jamais execute a l'import
                visiter(n, True, sous_garde)
            for n in noeud.orelse:                     # le `else`, lui, tourne bel et bien
                visiter(n, dans_corps, sous_garde)
            return
        corps = dans_corps or isinstance(noeud, (ast.FunctionDef, ast.AsyncFunctionDef,
                                                 ast.ClassDef))
        for enfant in ast.iter_child_nodes(noeud):
            visiter(enfant, corps, sous_garde)

    visiter(tree, False, False)
    return out


#: Profondeur maximale de la fermeture transitive. Un import casse a la profondeur 2 empeche le
#: probe de demarrer tout autant qu'a la profondeur 1 -- s'arreter a 1 laisserait passer des morts
#: reels. La borne existe pour le COUT, pas pour la doctrine : au-dela, la chaine est rapportee
#: comme NON EXPLOREE (donc jamais comptee comme vivante par omission).
PROFONDEUR_MAX = 6


class Contexte:
    """Ce qui est partage par tous les jugements : l'arbre, et les memos."""

    def __init__(self, arbre: Arbre):
        self.arbre = arbre
        self.memo: dict = {}          # (module local, chemins) -> (morts, differes, indets)
        self.tiers: dict = {}         # top-level -> bool
        self.tronques = 0             # chaines coupees par PROFONDEUR_MAX

    def tiers_dispo(self, top: str) -> bool:
        if top not in self.tiers:
            self.tiers[top] = _tiers_dispo(top)
        return self.tiers[top]


def _chemins_du_module(chemin: Path, tree: ast.AST, base) -> tuple:
    """(chemins visibles depuis ce module, arguments de sys.path NON evaluables)."""
    ev = EvaluateurChemin(chemin)
    ajouts = ev.parcourir(tree)
    chemins = list(base)
    for p in ajouts:
        if p not in chemins:
            chemins.append(p)
    return tuple(chemins), ev.non_evalues


def _analyser(chemin: Path, tree: ast.AST, chemins, ctx: Contexte, prof: int, pile) -> tuple:
    """(morts, differes, indets) de CE module, fermeture transitive comprise.

    La transitivite ne concerne QUE les modules du depot : un module tiers ou stdlib est une
    boite noire dont on n'a pas les sources, et un paquet-espace-de-noms n'a rien a lire.
    """
    morts, differes, indets, signales = [], [], [], set()
    for ligne, kind, mod, nom, differe in _imports(tree):
        genre, cible = _resoudre(mod, chemins, ctx)
        ou = "%s:L%d" % (chemin.name, ligne)
        if genre == ABSENT:
            forme = "from" if kind == "from" else "import"
            signales.add(mod)
            if ctx.arbre.artefact(mod.split(".")[0]):
                msg = ("%s `%s %s` : le DEPOT porte cet artefact mais il n'est pas sur le "
                       "`sys.path` de ce probe" % (ou, forme, mod))
                (differes if differe else morts).append(msg)
            else:
                msg = ("%s `%s %s` : introuvable (ni depot, ni stdlib, ni installe) -- tierce "
                       "partie absente de cette machine ou module supprime, INDISCERNABLE"
                       % (ou, forme, mod))
                # Un DIFFERE reste un differe quelle que soit la cause : il ne tourne pas a
                # l'import, donc il ne peut ni tuer ni empecher de conclure.
                (differes if differe else indets).append(msg)
            continue
        if genre != LOCAL:
            continue
        if kind == "from" and nom is not None:
            if cible is None:                   # paquet-espace-de-noms : seul un sous-module
                gen2, _ = _resoudre("%s.%s" % (mod, nom), chemins, ctx)
                if gen2 == ABSENT:
                    signales.add(mod)
                    msg = ("%s `from %s import %s` : %s est un paquet-espace-de-noms et %s n'y "
                           "est pas" % (ou, mod, nom, mod, nom))
                    (differes if differe else morts).append(msg)
            else:
                lia = ctx.arbre.liaisons(cible)
                if lia is None:
                    indets.append("%s `from %s import %s` : source de %s ILLISIBLE"
                                  % (ou, mod, nom, mod))
                elif not (lia.opaque or lia.etoiles) and nom not in lia.noms:
                    gen2, _ = _resoudre("%s.%s" % (mod, nom), chemins, ctx)
                    if gen2 == ABSENT:
                        signales.add(mod)
                        msg = ("%s `from %s import %s` : le module EXISTE, le nom N'Y EST PLUS"
                               % (ou, mod, nom))
                        (differes if differe else morts).append(msg)
        # ---- fermeture transitive -------------------------------------------------------
        if cible is None or differe:
            continue                            # un differe ne tourne pas a l'import
        if prof >= PROFONDEUR_MAX:
            ctx.tronques += 1
            continue
        cle_pile = os.path.normcase(str(cible))
        if cle_pile in pile:
            continue                            # cycle : Python le tolere, nous aussi
        sm, sd, si, ss = _module_local(cible, chemins, ctx, prof + 1, pile | {cle_pile})
        morts += sm
        indets += si
        signales |= ss
    return morts, differes, indets, signales


def _module_local(cible: Path, chemins, ctx: Contexte, prof: int, pile) -> tuple:
    """Jugement MEMOISE d'un module du depot importe par quelqu'un d'autre.

    Son propre repertoire N'EST PAS ajoute a `sys.path` : seul le script LANCE beneficie de
    `sys.path[0]`. Ce qu'il ajoute, ce sont ses propres `sys.path.insert` litteraux.
    """
    cle = (os.path.normcase(str(cible)), chemins)
    if cle in ctx.memo:
        return ctx.memo[cle]
    ctx.memo[cle] = ([], [], [], set())           # coupe la recursion pendant le calcul
    tree = ctx.arbre.arbre(cible)
    if tree is None:
        res = ([], [], ["source de %s ILLISIBLE" % cible.name], set())
        ctx.memo[cle] = res
        return res
    sous_chemins, non_eval = _chemins_du_module(cible, tree, chemins)
    if non_eval:
        res = ([], [], ["%s : argument de `sys.path` non evaluable (%s)"
                        % (cible.name, non_eval[0])], set())
        ctx.memo[cle] = res
        return res
    res = _analyser(cible, tree, sous_chemins, ctx, prof, pile)
    ctx.memo[cle] = res
    return res


def _resoudre(nom: str, chemins, ctx: Contexte):
    return resoudre_module(nom, chemins, ctx.arbre, ctx.tiers_dispo)


def juger_usage(chemin: Path, src: str, arbre_ou_ctx) -> Usage:
    """Le discriminant. Statique, sans lancer le probe."""
    ctx = arbre_ou_ctx if isinstance(arbre_ou_ctx, Contexte) else Contexte(arbre_ou_ctx)
    try:
        compile(src, str(chemin), "exec")
    except SyntaxError as exc:
        return Usage(MORT, ["ne COMPILE pas : %s ligne %s" % (exc.msg, exc.lineno)])
    except ValueError as exc:
        return Usage(MORT, ["ne COMPILE pas : %s" % exc])
    tree = ast.parse(src, filename=str(chemin))

    # `sys.path[0]` d'un `python <script>.py` est TOUJOURS le repertoire du script : il n'a pas
    # besoin d'etre insere pour etre la, et 209 probes n'inserent que ca.
    chemins, non_eval = _chemins_du_module(chemin, tree, (chemin.parent,))
    if non_eval:
        return Usage(INDETERMINE,
                     ["argument de `sys.path` non evaluable : %s" % a for a in non_eval],
                     chemins=list(chemins))

    morts, differes, indets, signales = _analyser(
        chemin, tree, chemins, ctx, 0, frozenset({os.path.normcase(str(chemin))}))
    if morts:
        return Usage(MORT, morts, differes, list(chemins), signales)
    if indets:
        return Usage(INDETERMINE, indets, differes, list(chemins), signales)
    return Usage(VIVANT, [], differes, list(chemins), signales)


# ==========================================================================================
#  4. CITATION
# ==========================================================================================
#
#  EXECUTABLE  : l'AST du citant -- `import <stem>` / `from <stem> import ...`, ou un
#                `ast.Constant` str CONTENANT le stem (argv de subprocess, chemin, id de banque).
#                Les DOCSTRINGS et chaines flottantes sont EXCLUES : ce sont des commentaires.
#                Mesure du brief : compter toute MENTION dans `tests/` rendait 442 probes
#                << joues par un test >> contre 319 reellement -- 123 de trop.
#  MENTION     : presence TEXTUELLE du stem (ou d'un prefixe a la frontiere de composant) dans
#                n'importe quel fichier, message de commit ou corps de PR. C'est l'union LARGE,
#                et elle seule sert a decider qu'un probe est ORPHELIN.

CLIQUET, PAR_TEST, PAR_SCRIPT, PROSE, ORPHELIN = (
    "CLIQUET", "JOUE PAR TEST", "JOUE PAR SCRIPT", "PROSE SEULE", "ORPHELIN")

#: Tout token qui RESSEMBLE a un nom de probe. Le corpus de MENTION en est extrait d'un seul
#: passage : 825 recherches de sous-chaine par fichier seraient un cout absurde pour un
#: resultat identique.
RE_TOKEN_PROBE = re.compile(r"probe[_-][0-9A-Za-z][0-9A-Za-z_\-]*")


def composants(stem: str) -> tuple:
    return tuple(stem.replace("-", "_").split("_"))


def _index_prefixes(stems) -> dict:
    """{tuple de composants -> [stems]} pour TOUT prefixe de chaque stem.

    Une mention en prose s'ecrit presque toujours par un PREFIXE (`probe_181`, jamais
    `probe_181_targeting_gaps`). N'apparier que le stem plein sous-compterait les mentions, donc
    SUR-compterait les orphelins -- et un orphelin est ce qu'on SUPPRIME. La frontiere de
    composant interdit `probe_46` de matcher `probe_462r5_...` (`46` != `462r5`).
    """
    idx: dict = {}
    for s in stems:
        comp = composants(s)
        for i in range(2, len(comp) + 1):       # >= 2 : `probe` seul ne designe rien
            idx.setdefault(comp[:i], []).append(s)
    return idx


def mentions_du_texte(txt: str, idx: dict) -> set:
    """Les stems mentionnes par ce texte, via l'index de prefixes."""
    out = set()
    for m in RE_TOKEN_PROBE.finditer(txt):
        comp = composants(m.group(0))
        for i in range(len(comp), 1, -1):
            cibles = idx.get(comp[:i])
            if cibles:
                out.update(cibles)
                break
    return out


#: Un chemin de script cite dans une chaine EXECUTABLE (argv de subprocess, chemin construit).
RE_CIBLE_PY = re.compile(r"[A-Za-z_][A-Za-z0-9_.\-/\\]*\.py")


def cibles_py_absentes(tree: ast.AST, moi: str, noms_py: set) -> set:
    """Les `.py` qu'une chaine EXECUTABLE de ce module designe et que l'arbre ne porte PAS.

    QUATRIEME mode de mort exploré : un probe dont le script appele par `subprocess` a disparu ne
    peut plus rien faire, quels que soient ses imports. NON FATAL, et la mesure dit pourquoi : sur
    le depot reel, les seuls noms introuvables sont les fichiers SYNTHETIQUES des auto-epreuves
    (`x.py`, `cible.py`, `mutant_ampute.py`...), qui n'existent que dans un tmpdir a l'execution.
    En faire un critere fabriquerait des rouges sur les cliquets les mieux gardes du depot.
    """
    exclus = _ids_docstrings(tree)
    out = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Constant) and isinstance(n.value, str) and id(n) not in exclus:
            for m in RE_CIBLE_PY.finditer(n.value):
                base = m.group(0).replace("\\", "/").rsplit("/", 1)[-1]
                if base != moi and base not in noms_py:
                    out.add(m.group(0))
    return out


def _ids_docstrings(tree: ast.AST) -> set:
    """`id()` des `Constant` str qui sont des DOCSTRINGS ou des chaines FLOTTANTES.

    Une chaine en position d'instruction n'est jamais executee au sens utile : c'est un
    commentaire. Les exclure est ce qui separe << nomme dans une docstring >> de << joue >>.
    """
    out = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Expr) and isinstance(n.value, ast.Constant) \
                and isinstance(n.value.value, str):
            out.add(id(n.value))
    return out


def citations_executables(tree: ast.AST, idx: dict) -> set:
    """Les stems que CE module cite de facon EXECUTABLE."""
    out = set()
    exclus = _ids_docstrings(tree)
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            for a in n.names:
                out |= mentions_du_texte(a.name.split(".")[0], idx)
        elif isinstance(n, ast.ImportFrom):
            if n.module:
                out |= mentions_du_texte(n.module.split(".")[0], idx)
        elif isinstance(n, ast.Constant) and isinstance(n.value, str) and id(n) not in exclus:
            if "probe" in n.value:
                out |= mentions_du_texte(n.value, idx)
    return out


def est_test(rel: str) -> bool:
    nom = rel.rsplit("/", 1)[-1]
    return (nom.startswith("test_") or nom == "conftest.py"
            or "/tests/" in rel or rel.startswith("tests/"))


BANQUE = REPO / "scripts" / "ratchets.ps1"
_RX_ARGV = re.compile(r"Argv\s*=\s*@\(([^)]*)\)", re.S)


def stems_de_la_banque(idx: dict) -> set:
    """Les probes que `scripts/ratchets.ps1` JOUE -- lus dans ses `Argv`, jamais recopies."""
    if not BANQUE.is_file():
        raise Indisponible("banque introuvable : %s" % BANQUE)
    src = BANQUE.read_text(encoding="utf-8", errors="replace")
    debut = src.find("$Ratchets = @(")
    if debut < 0:
        raise Indisponible("`$Ratchets = @(` introuvable dans %s" % BANQUE)
    out = set()
    for m in _RX_ARGV.finditer(src[debut:]):
        out |= mentions_du_texte(m.group(1), idx)
    if not out:
        raise Indisponible("aucun probe lu dans les `Argv` de la banque")
    return out


def _pull_requests(actif: bool):
    """([{title, body}], None) si MESURE | (None, raison) si NON MESURE. JAMAIS ([], raison)."""
    if not actif:
        return None, "lecture des PR desactivee (`--sans-pr`)"
    try:
        res = subprocess.run(["gh", "pr", "list", "--state", "all", "--limit", "200",
                              "--json", "number,title,body"],
                             cwd=str(REPO), capture_output=True, text=True, encoding="utf-8",
                             errors="replace", timeout=60)
    except FileNotFoundError:
        return None, "`gh` introuvable sur le PATH"
    except subprocess.TimeoutExpired:
        return None, "`gh` n'a pas repondu en 60 s"
    except (OSError, subprocess.SubprocessError) as exc:
        return None, "`gh` injouable : %s" % exc
    if res.returncode != 0:
        return None, "`gh` rc=%d -- %s" % (res.returncode,
                                           " ".join((res.stderr or "").split())[:160])
    try:
        data = json.loads(res.stdout or "null")
    except ValueError as exc:
        return None, "`gh` rc=0 mais sortie illisible : %s" % exc
    return (data, None) if isinstance(data, list) else (None, "`gh` : sortie inattendue")


# ==========================================================================================
#  5. AUTO-EPREUVE DU DISCRIMINANT (etape 0) -- jouee A CHAQUE PASSAGE
# ==========================================================================================
#
#  Un discriminant qui ne sait pas se tromper ne vaut rien. Chaque cas porte son verdict ATTENDU,
#  et les DEUX sens sont representes : un detecteur qui declarerait tout VIVANT (ou tout MORT)
#  passerait une epreuve unilaterale. Ecritures dans un tmpdir SYSTEME uniquement -- jamais sous
#  `scripts/python/`, que la banque enumere en parallele (#455).

_H = "tests/engine/runner"

CAS = [
    ("LA forme des 22 faux positifs : insert d'un sous-repertoire puis import du helper",
     {"scripts/python/probe_x.py":
      "import sys\nfrom pathlib import Path\nPYDIR = Path(__file__).resolve().parent\n"
      "sys.path.insert(0, str(PYDIR / 'tests' / 'engine' / 'runner'))\n"
      "from _charge_regime import monter\n",
      "scripts/python/" + _H + "/_charge_regime.py": "def monter():\n    pass\n"}, VIVANT),

    ("MEME probe, SANS l'insert : le helper est introuvable",
     {"scripts/python/probe_x.py":
      "import sys\nfrom pathlib import Path\nfrom _charge_regime import monter\n",
      "scripts/python/" + _H + "/_charge_regime.py": "def monter():\n    pass\n"}, MORT),

    ("insert par `os.path.join(os.path.dirname(os.path.abspath(__file__)), ...)`",
     {"scripts/python/probe_x.py":
      "import os, sys\nsys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath("
      "__file__)), 'tests', 'engine', 'runner'))\nfrom _combat_replay import rejouer\n",
      "scripts/python/" + _H + "/_combat_replay.py": "def rejouer():\n    pass\n"}, VIVANT),

    ("insert par `.parents[2]` puis re-descente",
     {"scripts/python/probe_x.py":
      "import sys\nfrom pathlib import Path\nREPO = Path(__file__).resolve().parents[2]\n"
      "sys.path.insert(0, str(REPO / 'scripts' / 'python'))\nimport outil\n",
      "scripts/python/outil.py": "A = 1\n"}, VIVANT),

    ("nom retire de la cible : le module EXISTE, le nom n'y est plus (critere probe_462r5)",
     {"scripts/python/probe_x.py": "from outil import BUILD_HASH\n",
      "scripts/python/outil.py": "def garde():\n    pass\n"}, MORT),

    ("nom PRESENT : vivant",
     {"scripts/python/probe_x.py": "from outil import garde\n",
      "scripts/python/outil.py": "def garde():\n    pass\n"}, VIVANT),

    ("source qui ne compile pas",
     {"scripts/python/probe_x.py": "def f(:\n    pass\n"}, MORT),

    ("stdlib seule",
     {"scripts/python/probe_x.py": "import json, subprocess\nfrom pathlib import Path\n"}, VIVANT),

    ("import mort GARDE par try/except ImportError : dependance optionnelle, exempte",
     {"scripts/python/probe_x.py":
      "try:\n    from absent_total import X\nexcept ImportError:\n    X = None\n"}, VIVANT),

    ("import mort DIFFERE (corps de fonction) : rapporte, jamais fatal",
     {"scripts/python/probe_x.py":
      "def main():\n    from absent_total import X\n    return X\n"}, VIVANT),

    ("argument de sys.path NON EVALUABLE : INDETERMINE, surtout pas MORT",
     {"scripts/python/probe_x.py":
      "import sys\ndef calcule():\n    return '/x'\nsys.path.insert(0, calcule())\n"
      "from _inconnu import f\n"}, INDETERMINE),

    ("cible OPAQUE (`import *` hors index) : aucun verdict sur ses noms",
     {"scripts/python/probe_x.py": "from facade import dumps\n",
      "scripts/python/facade.py": "from json import *  # noqa\n"}, VIVANT),

    ("mort TRANSITIVE : la dependance locale importe un nom disparu de SA propre cible",
     {"scripts/python/probe_x.py": "import intermediaire\n",
      "scripts/python/intermediaire.py": "from outil import DISPARU\n",
      "scripts/python/outil.py": "A = 1\n"}, MORT),

    ("un module du DEPOT hors du sys.path de ce probe : MORT (le depot est accuse)",
     {"scripts/python/probe_x.py": "import range_a_part\n",
      "scripts/python/ailleurs/range_a_part.py": "A = 1\n"}, MORT),

    ("dependance TIERSE absente de CETTE machine : environnement, pas depot -> INDETERMINE",
     {"scripts/python/probe_x.py": "import paquet_tiers_jamais_installe\n"}, INDETERMINE),

    ("paquet-espace-de-noms : sous-module present",
     {"scripts/python/probe_x.py": "from tests.engine.runner import _charge_regime\n",
      "scripts/python/" + _H + "/_charge_regime.py": "A = 1\n"}, VIVANT),

    ("paquet-espace-de-noms : sous-module ABSENT",
     {"scripts/python/probe_x.py": "from tests.engine.runner import _disparu\n",
      "scripts/python/" + _H + "/_charge_regime.py": "A = 1\n"}, MORT),
]


def _mini_arbre(fichiers: dict):
    """Un Arbre SYNTHETIQUE : meme interface, sans toucher au disque du depot."""
    racine = Path(tempfile.gettempdir()) / "__486r2_synthetique__"

    class ArbreSynth(Arbre):
        def __init__(self):
            self.rels = list(fichiers)
            self._noms_artefacts = None
            self.existe = {os.path.normcase(str(racine / r)) for r in fichiers}
            self.reps = set()
            for r in fichiers:
                p = Path(r).parent
                while str(p) not in (".", ""):
                    self.reps.add(os.path.normcase(str(racine / p)))
                    p = p.parent
            self._src = {os.path.normcase(str(racine / r)): s for r, s in fichiers.items()}
            self._ast, self._lia = {}, {}

        def source(self, chemin):
            return self._src.get(os.path.normcase(str(chemin)))

    return ArbreSynth(), racine


def helpers_hors_racine(chemin: Path, src: str, ctx: Contexte) -> list:
    """[(module, fichier)] des imports de NIVEAU MODULE qui ne resolvent QUE grace a un chemin
    que le probe a INSERE lui-meme.

    C'est exactement la forme des 22 faux positifs : `sys.path.insert(0, str(PYDIR / 'tests' /
    'engine' / 'runner'))` puis `from _charge_regime import ...`. La liste des helpers ne se
    saisit nulle part -- elle se DERIVE, et l'etape 2b l'imprime.

    LA CONDITION EST << NE RESOUT PAS SANS L'INSERT >>, pas << vit hors de la racine >>. Le second
    critere a ete essaye et il ramasse `engine` (un paquet FILS de la racine, qui n'a besoin
    d'aucun insert) : la mutation de l'etape 2c le laissait alors VIVANT et criait au laxisme
    sur un probe parfaitement juge. Un sujet de contre-epreuve mal choisi fabrique un rouge.
    """
    try:
        tree = ast.parse(src, filename=str(chemin))
    except (SyntaxError, ValueError):
        return []
    chemins, non_eval = _chemins_du_module(chemin, tree, (chemin.parent,))
    if non_eval or tuple(chemins) == (chemin.parent,):
        return []
    out = []
    for _ligne, _kind, mod, _nom, differe in _imports(tree):
        genre, cible = _resoudre(mod, chemins, ctx)
        if genre != LOCAL or cible is None:
            continue
        seul, _ = _resoudre(mod, (chemin.parent,), ctx)
        if seul == ABSENT:
            out.append((mod, cible, differe))
    return out


def _sans_sys_path(src: str) -> str:
    """La MEME source, privee de ses `sys.path.insert` / `append`. Mutation de l'etape 2c.

    C'est la contre-epreuve DECISIVE : si un probe importateur de helper reste VIVANT une fois
    ses inserts retires, c'est que le discriminant est LAXISTE et non qu'il modelise `sys.path`.
    Les 22 faux positifs seraient alors << rattrapes >> par accident.
    """
    try:
        tree = ast.parse(src)
    except (SyntaxError, ValueError):
        return src
    a_blanchir = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Expr) and isinstance(n.value, ast.Call):
            if (_dotted(n.value.func) or "") in ("sys.path.insert", "sys.path.append"):
                for i in range(n.lineno, (n.end_lineno or n.lineno) + 1):
                    a_blanchir.add(i)
    lignes = src.splitlines(keepends=True)
    return "".join("\n" if (i + 1) in a_blanchir else l for i, l in enumerate(lignes))


#: Combien de probes REELS la mutation de l'etape 2c doit faire basculer. Bornee pour le cout :
#: chaque mutation rejoue une fermeture transitive complete.
ECHANTILLON_MUTATION = 12


def contre_epreuve_reelle(probes, arbre: Arbre, ctx: Contexte, verbeux: bool) -> tuple:
    """(ko, lignes de rapport) -- etapes 2b et 2c, sur les sources REELLES du depot."""
    ko, rapport = 0, []

    # ---- 2b : les faux positifs de la premiere tentative, RE-MESURES ---------------------
    porteurs, helpers, n_module, n_differe = [], {}, 0, 0
    for rel in probes:
        chemin = REPO / rel
        src = arbre.source(chemin)
        if src is None:
            continue
        hs = helpers_hors_racine(chemin, src, ctx)
        if hs:
            porteurs.append((rel, src, hs))
            for mod, cible, differe in hs:
                helpers.setdefault(mod, cible.parent.relative_to(REPO).as_posix())
                if differe:
                    n_differe += 1
                else:
                    n_module += 1
    fautifs = [rel for rel, src, _ in porteurs
               if juger_usage(REPO / rel, src, ctx).etat == MORT]
    rapport.append("[486r2] etape 2b : %d probe(s) n'importent leur helper QUE grace a un chemin "
                   "qu'ils inserent (%d import(s) de niveau module, %d differe(s)) -- %d "
                   "helper(s) : %s" % (len(porteurs), n_module, n_differe, len(helpers),
                                       ", ".join(sorted(helpers))))
    if verbeux:
        for mod, rep in sorted(helpers.items()):
            rapport.append("           %-34s <- %s" % (mod, rep))
    if fautifs:
        ko += len(fautifs)
        rapport.append("  ROUGE  %d de ces probes sont classes MORTS : c'est EXACTEMENT le faux "
                       "positif que #486-r2 existe pour ne plus produire (%s)"
                       % (len(fautifs), ", ".join(Path(r).stem for r in fautifs[:4])))
    else:
        rapport.append("           tous VIVANTS -- les faux positifs de la premiere tentative "
                       "(le detecteur cherchait le helper A COTE du probe) ne se reproduisent pas.")

    # ---- 2c : la mutation MORD-ELLE ? ---------------------------------------------------
    #  Un discriminant qui ne sait pas se tromper ne vaut rien. On retire les inserts et on exige
    #  que CHAQUE helper concerne soit SIGNALE -- fatal s'il est de niveau module, rapporte en
    #  differe sinon. Exiger `etat == MORT` partout serait faux : un import differe ne tue pas,
    #  et le reclamer aurait rendu ROUGE des probes parfaitement juges.
    if not porteurs:
        ko += 1
        rapport.append("  ROUGE  aucun porteur de helper : la contre-epreuve 2c n'a PAS DE SUJET, "
                       "donc l'etape 2b ci-dessus ne prouve rien.")
        return ko, rapport
    echantillon = porteurs[:ECHANTILLON_MUTATION]
    muets, attendus = [], 0
    for rel, src, hs in echantillon:
        u = juger_usage(REPO / rel, _sans_sys_path(src), ctx)
        for mod, _cible, differe in hs:
            attendus += 1
            if mod not in u.signales:
                muets.append((rel, mod))
            elif not differe and u.etat != MORT:
                muets.append((rel, mod))
    rapport.append("[486r2] etape 2c : MUTATION sur %d source(s) REELLE(s) -- inserts `sys.path` "
                   "retires, les %d import(s) de helper doivent etre SIGNALES"
                   % (len(echantillon), attendus))
    if muets:
        ko += len(muets)
        rapport.append("  ROUGE  %d import(s) restent MUETS apres mutation : le discriminant ne "
                       "modelise PAS `sys.path`, il est simplement laxiste (%s)"
                       % (len(muets), ", ".join("%s/%s" % (Path(r).stem, m)
                                                for r, m in muets[:3])))
    else:
        rapport.append("           %d/%d signales : c'est bien la modelisation de `sys.path` qui "
                       "les sauve, pas une indulgence." % (attendus, attendus))
    return ko, rapport


#: Appels de NIVEAU MODULE tenus pour sans effet de bord -- le pre-filtre de `--confronter-import`.
#: Tout le reste ECARTE le probe de la confrontation et le fait NOMMER : importer un module qui
#: monte un runner au niveau module laisserait un runner orphelin.
APPELS_SURS = ("sys.path.insert", "sys.path.append", "print", "warnings.filterwarnings",
               "logging.basicConfig", "sys.setrecursionlimit", "sys.stdout.reconfigure",
               "os.environ.setdefault")


def _effets_de_module(tree: ast.AST) -> list:
    """Les appels de niveau module qui ne sont PAS dans `APPELS_SURS`."""
    mauvais = []

    def visiter(corps):
        for n in corps:
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                continue
            if isinstance(n, ast.If) and "__name__" in _src(n.test):
                continue
            if isinstance(n, ast.Expr) and isinstance(n.value, ast.Call):
                nom = _dotted(n.value.func) or "?"
                if nom not in APPELS_SURS:
                    mauvais.append(nom)
            for champ in ("body", "orelse", "finalbody"):
                s = getattr(n, champ, None)
                if isinstance(s, list):
                    visiter(s)
            for h in getattr(n, "handlers", []) or []:
                visiter(h.body)

    visiter(getattr(tree, "body", []))
    return mauvais


def confronter_import(probes, arbre: Arbre, usages: dict, workers: int = 8) -> int:
    """LE SOL du discriminant : `python -c "import <stem>"` dans un process FRAIS.

    C'est la seule chose qui puisse dire si le verdict STATIQUE ment. Elle n'est PAS jouee a
    chaque passage -- 800+ process, plusieurs minutes -- mais elle est ICI, dans le probe, et pas
    dans un scratchpad : une mesure qui ne se rejoue pas n'est plus une mesure au bout d'une
    semaine.

    Le corps de module s'execute ; `main()` reste sous `if __name__ == "__main__"`, donc rien
    n'est joue. C'est PUREMENT OFFLINE : aucun runner, aucun RPC -- d'ou le pre-filtre.
    """
    import concurrent.futures as cf

    a_faire, ecartes = [], []
    for rel in probes:
        tree = arbre.arbre(REPO / rel)
        if tree is None:
            ecartes.append((Path(rel).stem, ["source illisible"]))
            continue
        m = _effets_de_module(tree)
        (ecartes if m else a_faire).append((Path(rel).stem, sorted(set(m))[:2]))

    #: Ce qui, dans une trace d'import, accuse le MONTAGE et non le depot -- une entree
    #: gitignoree qu'un worktree ne voit PAS (invariant 3, troisieme categorie). `host_inputs`
    #: leve exactement pour ca, et son tri-etat fait son travail : le confondre avec une mort
    #: ferait accuser le depot d'une panne d'hote. Le motif se cherche dans la trace ENTIERE --
    #: la derniere ligne d'un message multi-ligne ne porte PAS le nom de l'exception (mesure).
    MONTAGE = ("HostInputUnavailable", "host_inputs", "TACTICUS_HOST_DATA_ROOT")

    def _un(stem):
        try:
            p = subprocess.run([sys.executable, "-c", "import %s" % stem], cwd=str(PYDIR),
                               capture_output=True, text=True, encoding="utf-8",
                               errors="replace", timeout=180)
        except (subprocess.TimeoutExpired, OSError) as exc:
            return stem, "PANNE", str(exc)[:120], False
        if p.returncode == 0:
            return stem, "OK", "", False
        err = p.stderr or ""
        lignes = [l for l in err.splitlines() if l.strip()]
        return stem, "KO", (lignes[-1][:130] if lignes else "?"), any(m in err for m in MONTAGE)

    print("[486r2] CONFRONTATION SOL : %d probe(s) importes en process frais, %d ECARTE(s) "
          "(effet de module)" % (len(a_faire), len(ecartes)))
    for stem, m in ecartes:
        print("        ECARTE  %-54s %s" % (stem, ", ".join(m)))
    ok, ko = 0, []
    with cf.ThreadPoolExecutor(max_workers=workers) as ex:
        for stem, etat, msg, montage in ex.map(_un, [s for s, _ in a_faire]):
            if etat == "OK":
                ok += 1
            else:
                ko.append((stem, etat, msg, montage))
    print("        %d import(s) REUSSI(s), %d ECHEC(s)" % (ok, len(ko)))
    desaccords = 0
    for stem, etat, msg, montage in ko:
        statique = usages.get(stem, Usage(INDETERMINE)).etat
        # DESACCORD = le statique dit VIVANT et l'import echoue POUR UNE CAUSE DU DEPOT.
        marque = "MONTAGE" if montage else "DESACCORD"
        if not montage and statique == VIVANT:
            desaccords += 1
        print("        %-10s %-46s statique=%-12s %s" % (marque, stem, statique, msg))
    if desaccords:
        print("  ROUGE  %d desaccord(s) statique/reel : le discriminant MENT." % desaccords)
    return desaccords


def croiser(seaux: dict, usages: dict) -> list:
    """LA REGLE DU CLIQUET, isolee pour etre TESTABLE : ORPHELIN *et* NON EXECUTABLE.

    C'est le seul croisement qui prouve la mort. << Rien ne le joue >> ne suffit pas : un probe
    est un instrument A MAIN, et PROSE SEULE est le seau le plus peuple du depot.
    """
    return sorted(s for s in seaux[ORPHELIN] if usages[s].etat == MORT)


#: Scenarios de la regle du cliquet. Les DEUX sens, pour la meme raison qu'a l'etape 0 : une
#: regle qui rendrait tout (ou rien) passerait une epreuve unilaterale. `probe_439` garde
#: << ce cliquet PEUT-il rendre non nul ? >> ; ceci garde << rougit-il sur SON gisement ? >>.
CAS_REGLE = [
    ("orphelin ET mort -> ROUGE", {ORPHELIN: ["a"]}, {"a": MORT}, ["a"]),
    ("orphelin mais VIVANT -> garde (un instrument a main se garde)",
     {ORPHELIN: ["a"]}, {"a": VIVANT}, []),
    ("orphelin et INDETERMINE -> garde (on ne supprime jamais sur un doute)",
     {ORPHELIN: ["a"]}, {"a": INDETERMINE}, []),
    ("mort mais CITE en prose -> garde (la citation le rend retrouvable)",
     {ORPHELIN: []}, {"a": MORT}, []),
]


def auto_epreuve_regle(verbeux: bool) -> int:
    ko = 0
    for nom, seaux, etats, attendu in CAS_REGLE:
        obtenu = croiser({ORPHELIN: seaux.get(ORPHELIN, [])},
                         {k: Usage(v) for k, v in etats.items()})
        if obtenu != attendu:
            ko += 1
            print("  ROUGE  AUTO-EPREUVE (regle) %-58s attendu=%s obtenu=%s"
                  % (nom[:58], attendu, obtenu))
        elif verbeux:
            print("  epreuve ok   (regle) %s" % nom)
    if not ko:
        print("[486r2] etape 0b : regle du cliquet -- %d/%d scenarios (%d attendus ROUGES). "
              "<< Peut rendre non nul >> n'est pas << rougit sur son gisement >> : ceci garde "
              "le second." % (len(CAS_REGLE), len(CAS_REGLE),
                              sum(1 for c in CAS_REGLE if c[3])))
    return ko


def auto_epreuve(verbeux: bool) -> int:
    ko = 0
    for nom, fichiers, attendu in CAS:
        arbre, racine = _mini_arbre(fichiers)
        cible = racine / "scripts/python/probe_x.py"
        u = juger_usage(cible, fichiers["scripts/python/probe_x.py"], arbre)
        ok = u.etat == attendu
        if not ok:
            ko += 1
            print("  ROUGE  AUTO-EPREUVE %-72s attendu=%s obtenu=%s (%s)"
                  % (nom[:72], attendu, u.etat, "; ".join(u.motifs)[:120]))
        elif verbeux:
            print("  epreuve ok   %-72s %s" % (nom[:72], attendu))
    if ko:
        print("[486r2] ROUGE -- %d forme(s) mal classee(s) : le discriminant a DERIVE. Son "
              "verdict sur les probes ne vaut plus rien." % ko)
    else:
        print("[486r2] etape 0 : auto-epreuve du discriminant -- %d/%d formes bien classees "
              "(%d attendues MORTES, %d VIVANTES, %d INDETERMINEES)."
              % (len(CAS), len(CAS), sum(1 for c in CAS if c[2] == MORT),
                 sum(1 for c in CAS if c[2] == VIVANT),
                 sum(1 for c in CAS if c[2] == INDETERMINE)))
    return ko


# ==========================================================================================
#  6. MAIN
# ==========================================================================================

def _resume(seaux: dict, total: int) -> None:
    print("")
    print("[486r2] PARTITION (exhaustive) :")
    somme = 0
    for cle in (CLIQUET, PAR_TEST, PAR_SCRIPT, PROSE, ORPHELIN):
        n = len(seaux[cle])
        somme += n
        print("   %-16s %5d  %5.1f %%" % (cle, n, 100.0 * n / total if total else 0.0))
    print("   %-16s %5d   (doit valoir %d)" % ("SOMME", somme, total))
    if somme != total:
        print("   ROUGE  la partition N'EST PAS exhaustive : %d != %d" % (somme, total))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--verbose", action="store_true")
    ap.add_argument("--self-test", action="store_true",
                    help="ne joue QUE l'auto-epreuve du discriminant")
    ap.add_argument("--lister", default=None,
                    help="imprime le detail d'un seau (CLIQUET / TEST / SCRIPT / PROSE / "
                         "ORPHELIN / MORT / INDETERMINE)")
    ap.add_argument("--csv", default=None, help="ecrit la ventilation complete (hors data/)")
    ap.add_argument("--sans-pr", action="store_true",
                    help="ne pas interroger `gh` (le corps des PR sort alors NON MESURE)")
    ap.add_argument("--confronter-import", action="store_true",
                    help="CONFRONTATION SOL : importe reellement chaque probe en process frais "
                         "(offline, plusieurs minutes). Hors passage courant.")
    a = ap.parse_args(argv)

    ko = auto_epreuve(a.verbose or a.self_test) + auto_epreuve_regle(a.verbose or a.self_test)
    if a.self_test:
        print("[486r2] VERDICT: %s" % ("PASS" if ko == 0 else "FAIL (%d)" % ko))
        return 0 if ko == 0 else 1

    try:
        suivis = fichiers_suivis()
        probes = population(suivis)
        hors = probes_hors_racine(suivis)
        arbre = Arbre(suivis)
        stems = [Path(r).stem for r in probes]
        idx = _index_prefixes(stems)
        banque = stems_de_la_banque(idx)
        commits = _git(["log", "--all", "--format=%s%n%b", "--no-merges"], "`git log --all`")
    except Indisponible as exc:
        print("[486r2] NON MESURE -- %s" % exc)
        print("        Un corpus ampute ferait declarer ORPHELIN un probe cite : ce probe REFUSE")
        print("        de conclure plutot que de rendre un vert ou un rouge.")
        return EX_NON_MESURE

    print("[486r2] etape 1 : %d fichier(s) suivi(s) ; POPULATION = %d probe(s) de premier niveau"
          % (len(suivis), len(probes)))
    print("        filtre : `scripts/python/probe_*.py` sans sous-repertoire -- ECARTE %d "
          "`probe_*.py` ailleurs dans l'arbre%s"
          % (len(hors), (" (%s)" % ", ".join(hors[:4])) if hors else ""))
    if not probes:
        print("[486r2] NON MESURE -- population VIDE")
        return EX_NON_MESURE

    # ---- USAGE -------------------------------------------------------------------------
    ctx = Contexte(arbre)
    usages: dict = {}
    for rel, stem in zip(probes, stems):
        chemin = REPO / rel
        src = arbre.source(chemin)
        if src is None:
            usages[stem] = Usage(INDETERMINE, ["source ILLISIBLE"])
            continue
        usages[stem] = juger_usage(chemin, src, ctx)
    par_etat = {e: [s for s in stems if usages[s].etat == e]
                for e in (VIVANT, MORT, INDETERMINE)}
    n_differes = sum(1 for s in stems if usages[s].differes)
    print("[486r2] etape 2 : USAGE -- %d VIVANT(s), %d MORT(s), %d INDETERMINE(s)"
          % (len(par_etat[VIVANT]), len(par_etat[MORT]), len(par_etat[INDETERMINE])))
    print("        fermeture TRANSITIVE : %d module(s) du depot visite(s) (profondeur max %d, "
          "%d chaine(s) tronquee(s)) ; %d probe(s) portent un import DIFFERE qui ne resout pas "
          "-- rapporte, JAMAIS fatal"
          % (len(ctx.memo), PROFONDEUR_MAX, ctx.tronques, n_differes))
    ko_ce, rapport_ce = contre_epreuve_reelle(probes, arbre, ctx, a.verbose)
    ko += ko_ce
    for l in rapport_ce:
        print(l)
    if a.confronter_import:
        ko += confronter_import(probes, arbre, usages)

    # ---- CITATION ----------------------------------------------------------------------
    citants_exec: dict = {s: set() for s in stems}
    #: QUATRE corpus de mention, pour que la PORTEE du critere soit une mesure et non une
    #: affirmation. Deux axes : la FORME du nom (prefixe a la frontiere de composant vs stem
    #: PLEIN) et la SOURCE (l'arbre seul vs l'arbre + ce qui n'y est pas -- messages de commit et
    #: corps de PR). Le critere retenu est le plus LARGE des quatre : c'est celui qui rend le
    #: moins d'orphelins, donc celui qui supprime le moins.
    mentionne: set = set()                # prefixe, arbre + hors-arbre  (retenu)
    mentionne_plein: set = set()          # stem PLEIN, arbre + hors-arbre
    ment_arbre: set = set()               # prefixe, arbre seul
    ment_arbre_plein: set = set()         # stem PLEIN, arbre seul
    cibles_absentes: dict = {}
    noms_py = {Path(r).name for r in suivis if r.endswith(".py")}
    chemins = [REPO / r for r in suivis]
    textes = repo_read.read_bytes_many(chemins)
    illisibles = 0
    for rel, data in zip(suivis, textes):
        if data is None:
            illisibles += 1
            continue
        try:
            txt = repo_read.to_text(data)
        except UnicodeDecodeError:
            illisibles += 1
            continue
        if "probe" not in txt:
            continue
        vus = mentions_du_texte(txt, idx)
        moi = Path(rel).stem
        vus.discard(moi)
        mentionne |= vus
        ment_arbre |= vus
        for s in vus:
            if s != moi and s in txt:
                mentionne_plein.add(s)
                ment_arbre_plein.add(s)
        if not rel.endswith(".py"):
            if rel.endswith(".ps1"):            # un script PowerShell : pas d'AST, le texte fait foi
                for s in vus:
                    citants_exec[s].add(rel)
            continue
        try:
            tree = ast.parse(txt, filename=rel)
        except (SyntaxError, ValueError):
            continue
        ex = citations_executables(tree, idx)
        ex.discard(moi)
        for s in ex:
            citants_exec[s].add(rel)
        if rel in set(probes):
            abs_py = cibles_py_absentes(tree, Path(rel).name, noms_py)
            if abs_py:
                cibles_absentes[Path(rel).stem] = sorted(abs_py)
    mentionne |= mentions_du_texte(commits, idx)
    mentionne_plein |= {s for s in mentions_du_texte(commits, idx) if s in commits}

    prs, panne_pr = _pull_requests(not a.sans_pr)
    if prs is not None:
        for pr in prs:
            txt_pr = "%s\n%s" % (pr.get("title") or "", pr.get("body") or "")
            vus = mentions_du_texte(txt_pr, idx)
            mentionne |= vus
            mentionne_plein |= {s for s in vus if s in txt_pr}

    seaux = {CLIQUET: [], PAR_TEST: [], PAR_SCRIPT: [], PROSE: [], ORPHELIN: []}
    for s in stems:
        if s in banque:
            seaux[CLIQUET].append(s)
        elif any(est_test(c) for c in citants_exec[s]):
            seaux[PAR_TEST].append(s)
        elif citants_exec[s]:
            seaux[PAR_SCRIPT].append(s)
        elif s in mentionne:
            seaux[PROSE].append(s)
        else:
            seaux[ORPHELIN].append(s)

    print("[486r2] etape 2d : QUATRIEME mode de mort explore -- un `.py` cite dans une chaine "
          "EXECUTABLE et absent de l'arbre : %d probe(s) concerne(s)%s"
          % (len(cibles_absentes),
             (" (%s)" % ", ".join(sorted(cibles_absentes)[:3])) if cibles_absentes else ""))
    print("           NON FATAL, et la mesure dit pourquoi : ces noms sont les fichiers "
          "SYNTHETIQUES des auto-epreuves, ecrits dans un tmpdir a l'execution.")
    print("[486r2] etape 3 : CITATION -- corpus = %d fichier(s) suivi(s) (%d illisible(s)), "
          "messages de commit (`--all`), corps des PR : %s"
          % (len(suivis), illisibles,
             ("%d PR lues" % len(prs)) if prs is not None else ("NON MESURE -- %s" % panne_pr)))
    def _orphelins(corpus) -> list:
        return sorted(s for s in stems
                      if s not in banque and not citants_exec[s] and s not in corpus)

    portee = [("PREFIXE + hors-arbre (RETENU)", mentionne),
              ("PREFIXE, arbre seul", ment_arbre),
              ("stem PLEIN + hors-arbre", mentionne_plein),
              ("stem PLEIN, arbre seul", ment_arbre_plein)]
    print("        PORTEE DU CRITERE DE MENTION -- deux axes, quatre corpus. Le RETENU est le")
    print("        plus large, donc celui qui rend le MOINS d'orphelins, donc qui supprime le")
    print("        moins. Un critere plus etroit ne prouve pas une mort, il fabrique un suspect :")
    for libelle, corpus in portee:
        print("           %-32s -> %3d orphelin(s)" % (libelle, len(_orphelins(corpus))))
    orph_strict = _orphelins(ment_arbre_plein)
    supplement = [s for s in orph_strict if s not in set(seaux[ORPHELIN])]
    if supplement:
        print("        les %d probe(s) que seul le critere le plus ETROIT accuse sont LISTES, "
              "jamais supprimes :" % len(supplement))
        for s in supplement:
            print("           suspect sans preuve  %-56s %s" % (s, usages[s].etat))
    _resume(seaux, len(probes))

    # ---- CROISEMENT ---------------------------------------------------------------------
    morts_orphelins = croiser(seaux, usages)
    print("")
    print("[486r2] etape 4 : CROISEMENT usage x citation")
    for cle in (CLIQUET, PAR_TEST, PAR_SCRIPT, PROSE, ORPHELIN):
        v = sum(1 for s in seaux[cle] if usages[s].etat == VIVANT)
        m = sum(1 for s in seaux[cle] if usages[s].etat == MORT)
        i = sum(1 for s in seaux[cle] if usages[s].etat == INDETERMINE)
        print("   %-16s vivant=%-4d mort=%-3d indetermine=%d" % (cle, v, m, i))

    if a.lister:
        cle = {"CLIQUET": CLIQUET, "TEST": PAR_TEST, "SCRIPT": PAR_SCRIPT, "PROSE": PROSE,
               "ORPHELIN": ORPHELIN}.get(a.lister.upper())
        if cle:
            for s in sorted(seaux[cle]):
                print("   %-16s %-58s %s" % (cle, s, usages[s].etat))
        elif a.lister.upper() in (MORT, INDETERMINE, VIVANT):
            for s in sorted(par_etat[a.lister.upper()]):
                seau = next(k for k, v in seaux.items() if s in v)
                print("   %-12s %-58s %-16s %s"
                      % (a.lister.upper(), s, seau, "; ".join(usages[s].motifs)[:110]))
        else:
            print("   (seau inconnu : %s)" % a.lister)

    if a.csv:
        import csv
        dest = Path(a.csv)
        with dest.open("w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(["stem", "seau", "usage", "citants_executables", "motifs"])
            for s in stems:
                seau = next(k for k, v in seaux.items() if s in v)
                w.writerow([s, seau, usages[s].etat, ";".join(sorted(citants_exec[s])),
                            " | ".join(usages[s].motifs)])
        print("   ventilation ecrite : %s" % dest)

    # ---- CLIQUET ------------------------------------------------------------------------
    #  TRI-ETAT, et son ASYMETRIE, qui est le point : ne pas lire le corps des PR ne peut
    #  qu'AJOUTER des mentions, donc RETRECIR l'ensemble des orphelins. Un PASS calcule sans `gh`
    #  reste donc valide -- mais une ACCUSATION, elle, ne l'est pas : le probe accuse pourrait
    #  n'etre nomme que dans une PR en vol. Un rouge sans `gh` sort en NON MESURE.
    print("")
    if morts_orphelins and prs is None:
        print("[486r2] NON MESURE -- %d probe(s) seraient ORPHELIN(s) et MORT(s), mais le corps "
              "des PR n'a PAS ete lu (%s)." % (len(morts_orphelins), panne_pr))
        print("        Un probe nomme SEULEMENT dans une PR en vol serait accuse a tort : le")
        print("        squash-merge ne recopie pas le corps d'une PR dans l'arbre (#468-r11).")
        for s in morts_orphelins:
            print("        candidat : %-52s %s" % (s, "; ".join(usages[s].motifs)[:90]))
        return EX_NON_MESURE
    if morts_orphelins:
        ko += len(morts_orphelins)
        print("[486r2] ROUGE -- %d probe(s) a la fois ORPHELIN(s) et NON EXECUTABLE(s) :"
              % len(morts_orphelins))
        for s in morts_orphelins:
            print("  ROUGE  %-58s %s" % (s, "; ".join(usages[s].motifs)[:110]))
        print("  => nomme NULLE PART (docs, code, tests, commits, PR) ET incapable de demarrer.")
        print("     Le supprimer, ou le reparer et le citer la ou on le joue.")
    else:
        print("[486r2] etape 5 : 0 probe ORPHELIN et NON EXECUTABLE -- le cliquet tient.")

    print("\n[486r2] VERDICT: %s" % ("PASS" if ko == 0 else "FAIL (%d)" % ko))
    return 0 if ko == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
