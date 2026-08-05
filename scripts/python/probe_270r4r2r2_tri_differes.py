"""#270-r4-r2-r2 -- TRIER les imports differes restants d'`engine/`, par CAUSE MESUREE.

Un import differe ne casse pas un cycle, il le DEPLACE : l'echec du chargement part vers
le premier appel, et l'ordre d'initialisation devient dependant du chemin d'execution.
#270-r4-r2 a coupe les deux SCC niveau module ; ce probe repond a la question d'apres :
pour CHACUN des differes restants, POURQUOI est-il la ?

Le tri est DERIVE, jamais une liste blanche de causes. Chaque instruction differee tombe
dans exactement une categorie, et la somme des categories est imprimee comme PARTITION
EXHAUSTIVE. Une forme syntaxique non prevue sort sous `autre (<Noeud>)` -- elle ne peut
pas se faire absorber par une categorie voisine.

  TYPE_CHECKING  -- jamais execute au runtime. Inoffensif par construction.
  conditionnel   -- l'import est sous un `if`/`try`/`while` DANS la fonction : le hisser
                    changerait la semantique (il s'executerait toujours). ECARTE, dit.
  hissable       -- MESURE : hisser l'instruction EN TETE laisse l'import vert dans TOUS
                    les ordres d'entree essayes. Candidat au hissage.
  placement      -- MESURE : la TETE rougit, la FIN DE FICHIER passe. Un import module-level
                    place APRES la definition que la boucle consomme n'est PAS un differe :
                    l'echec redevient deterministe a l'import (recette #270-r4-r2 §4,
                    `dsl/base.py` et `services/static_battle_rules.py`).
  brise-cycle    -- MESURE : ni la tete ni la fin ne passent. Il DOIT rester differe.
  autre (...)    -- tout le reste, imprime avec sa forme.

MESURE SANS ECRIRE AUCUN FICHIER : le hissage est SIMULE par un `MetaPathFinder` qui
intercepte le module porteur et `exec`-ute le SEGMENT SOURCE EXACT de l'instruction dans
son namespace, juste AVANT le corps du module. C'est exactement ce que ferait un import
place en tete -- y compris pour `from .x import Y` (le symbole est resolu, donc un module
partiellement initialise leve bien `ImportError: cannot import name`).

DEUX ordres d'entree au minimum (un cycle ne se voit que dans UN sens) : le module
PORTEUR en premier, et chaque CIBLE en premier.

TEMOIN OBLIGATOIRE : avant toute mesure de hissage, les memes modules sont importes SANS
hissage. Un temoin rouge veut dire qu'on mesure un arbre deja casse -> la mesure s'arrete.

Usage :
    python probe_270r4r2r2_tri_differes.py --gratuits     # INVARIANT a zero (rapide, rc != 0)
    python probe_270r4r2r2_tri_differes.py --inventaire   # formes syntaxiques (aucune execution)
    python probe_270r4r2r2_tri_differes.py --mesurer --sortie tri.json [--paquet engine.runner]
    python probe_270r4r2r2_tri_differes.py --resume tri.json

`--mesurer` sur tout `engine/` coute ~10 min (un interpreteur par (site, ordre d'entree)) : il
N'EST PAS dans le cliquet. Le cliquet garde `--gratuits`, qui est purement statique.
"""
from __future__ import annotations

import argparse
import ast
import json
import os
import subprocess
import sys
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

RACINE = Path(__file__).resolve().parent
PAQUET = "engine"


# ============================================================ collecte AST

class _Site:
    """Une INSTRUCTION d'import differee vers `engine/`."""

    __slots__ = ("module", "ligne", "fin", "segment", "cause_syn", "cibles", "forme",
                 "conteneur")

    def __init__(self, module, ligne, fin, segment, cause_syn, cibles, forme, conteneur):
        self.module = module
        self.ligne = ligne
        self.fin = fin
        self.segment = segment
        self.cause_syn = cause_syn      # "TYPE_CHECKING" | "fonction"
        self.cibles = cibles            # modules engine reellement resolus
        self.forme = forme              # "Import" | "ImportFrom"
        self.conteneur = conteneur      # "" | "If" | "Try" | "While" | "ExceptHandler" | ...

    def cle(self):
        return "%s:%d" % (self.module, self.ligne)

    def json(self):
        return {"module": self.module, "ligne": self.ligne, "segment": self.segment,
                "cause_syn": self.cause_syn, "cibles": self.cibles, "forme": self.forme,
                "conteneur": self.conteneur}


def _nom_module(chemin: Path, racine: Path | None = None) -> str:
    rel = chemin.relative_to(racine or RACINE)
    parts = list(rel.parts)
    if parts[-1] == "__init__.py":
        parts = parts[:-1]
    else:
        parts[-1] = parts[-1][: -len(".py")]
    return ".".join(parts)


def _est_type_checking(test: ast.expr) -> bool:
    if isinstance(test, ast.Name) and test.id == "TYPE_CHECKING":
        return True
    if isinstance(test, ast.Attribute) and test.attr == "TYPE_CHECKING":
        return True
    return False


class _Visiteur(ast.NodeVisitor):
    """Collecte les imports DIFFERES avec leur CONTEXTE syntaxique complet.

    `_pile` porte les noeuds traverses depuis la racine : c'est ce qui permet de
    distinguer un import inconditionnel en tete de fonction d'un import sous un `if`,
    et de DERIVER la forme du conteneur au lieu de l'enumerer.
    """

    def __init__(self, mod: str, pkg: str, src: str, garde: str = PAQUET) -> None:
        self.mod = mod
        self.pkg = pkg
        self.src = src
        # prefixe des cibles retenues. PARAMETRE, pas fige a `engine` : fige, le detecteur
        # etait intestable sur un arbre synthetique -- et une contre-epreuve qu'on ne peut
        # pas ecrire est une contre-epreuve qui n'existe pas.
        self.garde = garde
        self.sites: list[_Site] = []
        self._pile: list[str] = []
        self._prof_fn = 0
        self._prof_tc = 0

    # -- resolution (meme regle que probe_270r4r2_cycles_imports) --------------
    def _resoudre(self, noeud: ast.ImportFrom) -> list[str]:
        if noeud.level == 0:
            return self._absolu(noeud)
        parts = self.pkg.split(".")
        remontee = noeud.level - 1
        base = parts[: len(parts) - remontee] if remontee else parts
        if not base:
            return []
        cible = ".".join(base)
        if noeud.module:
            cible = f"{cible}.{noeud.module}"
        out = [cible]
        for alias in noeud.names:
            if alias.name != "*":
                out.append(f"{cible}.{alias.name}")
        return out

    def _absolu(self, noeud: ast.ImportFrom) -> list[str]:
        if not noeud.module:
            return []
        out = [noeud.module]
        for alias in noeud.names:
            if alias.name != "*":
                out.append(f"{noeud.module}.{alias.name}")
        return out

    # -- visite ---------------------------------------------------------------
    def _enregistrer(self, noeud, cibles: list[str], forme: str) -> None:
        if self._prof_fn == 0 and self._prof_tc == 0:
            return                                    # niveau module : hors sujet
        if not [c for c in cibles if c.startswith(self.garde)]:
            return
        cause = "fonction" if self._prof_fn else "TYPE_CHECKING"
        # conteneur = le noeud de CONTROLE le plus proche SOUS la fonction porteuse
        conteneur = ""
        for nom in reversed(self._pile):
            if nom in ("FunctionDef", "AsyncFunctionDef", "Module", "ClassDef"):
                break
            conteneur = nom
            break
        seg = ast.get_source_segment(self.src, noeud) or ""
        self.sites.append(_Site(self.mod, noeud.lineno, getattr(noeud, "end_lineno", noeud.lineno),
                                seg, cause, [c for c in cibles if c.startswith(self.garde)],
                                forme, conteneur))

    def visit_Import(self, noeud: ast.Import) -> None:
        self._enregistrer(noeud, [a.name for a in noeud.names], "Import")

    def visit_ImportFrom(self, noeud: ast.ImportFrom) -> None:
        self._enregistrer(noeud, self._resoudre(noeud), "ImportFrom")

    def visit_FunctionDef(self, noeud) -> None:
        self._prof_fn += 1
        self._pile.append("FunctionDef")
        self.generic_visit(noeud)
        self._pile.pop()
        self._prof_fn -= 1

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_ClassDef(self, noeud) -> None:
        self._pile.append("ClassDef")
        self.generic_visit(noeud)
        self._pile.pop()

    def visit_If(self, noeud: ast.If) -> None:
        if _est_type_checking(noeud.test):
            self._prof_tc += 1
            self._pile.append("TYPE_CHECKING")
            for enfant in noeud.body:
                self.visit(enfant)
            self._pile.pop()
            self._prof_tc -= 1
            for enfant in noeud.orelse:
                self.visit(enfant)
            return
        self._pile.append("If")
        self.generic_visit(noeud)
        self._pile.pop()

    def _generique_nomme(self, noeud) -> None:
        self._pile.append(type(noeud).__name__)
        self.generic_visit(noeud)
        self._pile.pop()

    visit_Try = _generique_nomme
    visit_While = _generique_nomme
    visit_For = _generique_nomme
    visit_With = _generique_nomme
    visit_ExceptHandler = _generique_nomme
    if hasattr(ast, "TryStar"):
        visit_TryStar = _generique_nomme
    if hasattr(ast, "Match"):
        visit_Match = _generique_nomme


def collecter(racine_paquet: Path, filtre: str = "",
              racine: Path | None = None) -> tuple[list[_Site], set[str]]:
    fichiers = sorted(racine_paquet.rglob("*.py"))
    modules = {_nom_module(f, racine): f for f in fichiers}
    connus = set(modules)
    sites: list[_Site] = []
    for mod, chemin in sorted(modules.items()):
        if filtre and not (mod == filtre or mod.startswith(filtre + ".")):
            continue
        src = chemin.read_text(encoding="utf-8")
        v = _Visiteur(mod, mod if chemin.name == "__init__.py" else mod.rsplit(".", 1)[0], src,
                      racine_paquet.name)
        v.visit(ast.parse(src, filename=str(chemin)))
        for s in v.sites:
            reels = []
            for c in s.cibles:
                r = _reduire(c, connus)
                if r and r != mod and r not in reels:
                    reels.append(r)
            s.cibles = reels
            sites.append(s)
    return sites, connus


def _reduire(cible: str, connus: set[str]) -> str | None:
    if cible in connus:
        return cible
    while "." in cible:
        cible = cible.rsplit(".", 1)[0]
        if cible in connus:
            return cible
    return None


# ============================================================ invariant : le differe GRATUIT

def preambule(arbre: ast.Module, pkg: str, connus: set[str],
              garde: str = PAQUET) -> set[str]:
    """Modules `engine` importes au NIVEAU MODULE, dans le PREAMBULE du fichier.

    Le preambule s'arrete a la premiere `def`/`class` : les imports places APRES une
    definition (recette du PLACEMENT, `# noqa: E402`) n'y entrent PAS. C'est voulu -- eux
    ne garantissent pas que la cible soit chargee quand le corps s'execute.
    """
    out: set[str] = set()
    faux = _Visiteur("", pkg, "", garde)
    for n in arbre.body:
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            break
        if isinstance(n, ast.ImportFrom):
            for c in faux._resoudre(n):
                r = _reduire(c, connus)
                if r:
                    out.add(r)
        elif isinstance(n, ast.Import):
            for a in n.names:
                r = _reduire(a.name, connus)
                if r:
                    out.add(r)
    return out


def gratuits(racine_paquet: Path, filtre: str = "",
             racine: Path | None = None) -> list[tuple[str, int, str]]:
    """Les differes GRATUITS : inconditionnels, dont TOUTES les cibles sont deja chargees
    par le PREAMBULE du meme fichier.

    Invariant a ZERO, pas un seuil : la cible est deja completement importee quand le corps
    du module s'execute, donc hisser l'instruction ne peut ni fermer un cycle (l'arete existe
    deja) ni couter un module de plus (il est deja charge). Un tel differe n'a AUCUNE raison
    d'etre -- ni cycle, ni cout.
    """
    fichiers = sorted(racine_paquet.rglob("*.py"))
    modules = {_nom_module(f, racine): f for f in fichiers}
    connus = set(modules)
    out = []
    for mod, chemin in sorted(modules.items()):
        if filtre and not (mod == filtre or mod.startswith(filtre + ".")):
            continue
        src = chemin.read_text(encoding="utf-8")
        arbre = ast.parse(src, filename=str(chemin))
        pkg = mod if chemin.name == "__init__.py" else mod.rsplit(".", 1)[0]
        deja = preambule(arbre, pkg, connus, racine_paquet.name)
        v = _Visiteur(mod, pkg, src, racine_paquet.name)
        v.visit(arbre)
        for s in v.sites:
            if s.cause_syn != "fonction" or s.conteneur:
                continue
            reels = [r for r in (_reduire(c, connus) for c in s.cibles) if r and r != mod]
            if reels and all(c in deja for c in reels):
                out.append((mod, s.ligne, s.segment.replace("\n", " ")[:100]))
    return out


# ============================================================ mesure (sous-process)

_GABARIT = r'''
import sys, importlib, importlib.util, importlib.abc, json

PORTEUR = %(porteur)r
SEGMENT = %(segment)r
ENTREE  = %(entree)r
HISSER  = %(hisser)r
POSITION = %(position)r     # "tete" | "fin"

class _Loader(importlib.abc.Loader):
    def __init__(self, vrai):
        self._vrai = vrai
    def create_module(self, spec):
        return self._vrai.create_module(spec)
    def exec_module(self, module):
        # HISSAGE SIMULE : le segment source EXACT s'execute dans le namespace du
        # module -- avant son corps (= import en tete) ou apres (= import place en
        # FIN DE FICHIER, ce qui reste un import MODULE-LEVEL, pas un differe).
        if POSITION == "tete":
            exec(compile(SEGMENT, "<hissage>", "exec"), module.__dict__)
            self._vrai.exec_module(module)
        else:
            self._vrai.exec_module(module)
            exec(compile(SEGMENT, "<hissage>", "exec"), module.__dict__)

class _Finder(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path, target=None):
        if fullname != PORTEUR:
            return None
        sys.meta_path.remove(self)
        try:
            spec = importlib.util.find_spec(fullname)
        finally:
            sys.meta_path.insert(0, self)
        if spec is None or spec.loader is None:
            return None
        spec.loader = _Loader(spec.loader)
        return spec

if HISSER:
    sys.meta_path.insert(0, _Finder())

try:
    importlib.import_module(ENTREE)
except BaseException as e:
    print(json.dumps({"rc": 1, "err": "%%s: %%s" %% (type(e).__name__, e)})[:4000])
    raise SystemExit(0)
print(json.dumps({"rc": 0, "err": ""}))
'''


def _lancer(porteur: str, segment: str, entree: str, hisser: bool,
            position: str = "tete") -> tuple[int, str]:
    code = _GABARIT % {"porteur": porteur, "segment": segment, "entree": entree,
                       "hisser": hisser, "position": position}
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    try:
        r = subprocess.run([sys.executable, "-c", code], cwd=str(RACINE),
                           capture_output=True, text=True, timeout=300, env=env)
    except subprocess.TimeoutExpired:
        return 1, "TimeoutExpired"
    sortie = (r.stdout or "").strip().splitlines()
    if r.returncode != 0:
        lignes = [l for l in (r.stderr or "").strip().splitlines() if l.strip()]
        return 1, "process rc=%d: %s" % (r.returncode, lignes[-1] if lignes else "(stderr vide)")
    for ligne in reversed(sortie):
        try:
            d = json.loads(ligne)
        except ValueError:
            continue
        return int(d["rc"]), d["err"]
    return 1, "(pas de verdict JSON)"


# ============================================================ orchestration

def _ordres(site: _Site) -> list[str]:
    """Les ordres d'entree a essayer. Un cycle ne se voit que dans UN sens."""
    out = [site.module]
    for c in site.cibles:
        if c not in out:
            out.append(c)
    return out


def mesurer(sites: list[_Site], jobs: int) -> dict:
    """Rend {cle: {"categorie":..., "detail":...}}. TEMOIN d'abord, hissage ensuite."""
    testables = [s for s in sites if s.cause_syn == "fonction" and not s.conteneur]
    # -- TEMOIN : les memes modules, SANS hissage. Un temoin rouge = arbre deja casse.
    a_temoigner = sorted({m for s in testables for m in _ordres(s)})
    print("[270-r4-r2-r2] TEMOIN : %d module(s) importes SANS hissage" % len(a_temoigner))
    if not a_temoigner:
        print("[270-r4-r2-r2] ECHEC : 0 module a temoigner -- un zero ne prouve RIEN")
        return {}
    temoin_ko = []
    with ThreadPoolExecutor(max_workers=jobs) as ex:
        for mod, (rc, err) in zip(a_temoigner,
                                  ex.map(lambda m: _lancer(m, "pass", m, False, "tete"),
                                         a_temoigner)):
            if rc != 0:
                temoin_ko.append((mod, err))
    if temoin_ko:
        print("[270-r4-r2-r2] ECHEC TEMOIN : %d module(s) ne s'importent DEJA pas"
              % len(temoin_ko))
        for m, e in temoin_ko[:20]:
            print("   %s -> %s" % (m, e))
        return {}
    print("[270-r4-r2-r2] TEMOIN VERT : %d/%d" % (len(a_temoigner), len(a_temoigner)))

    # -- HISSAGE simule, tous les ordres d'entree
    taches = []
    for s in testables:
        for entree in _ordres(s):
            taches.append((s, entree))
    print("[270-r4-r2-r2] mesure : %d instruction(s) x ordres = %d import(s) a jouer"
          % (len(testables), len(taches)))
    res = defaultdict(list)
    with ThreadPoolExecutor(max_workers=jobs) as ex:
        sorties = ex.map(lambda t: _lancer(t[0].module, t[0].segment, t[1], True, "tete"), taches)
        for (s, entree), (rc, err) in zip(taches, sorties):
            res[s.cle()].append((entree, rc, err))
    out = {}
    rouges_tete = []
    for s in testables:
        essais = res[s.cle()]
        rouges = [(e, m) for e, rc, m in essais if rc != 0]
        if rouges:
            out[s.cle()] = {"categorie": "brise-cycle",
                            "detail": "TETE : %s en premier -> %s" % (rouges[0][0], rouges[0][1]),
                            "ordres": len(essais)}
            rouges_tete.append(s)
        else:
            out[s.cle()] = {"categorie": "hissable", "detail": "",
                            "ordres": len(essais)}

    # -- SECONDE PASSE : les rouges de la TETE, re-testes en FIN DE FICHIER.
    # Un import module-level place APRES la definition que la boucle consomme reste
    # un import DETERMINISTE ; il sort donc du gisement des differes.
    if rouges_tete:
        taches2 = [(s, e) for s in rouges_tete for e in _ordres(s)]
        print("[270-r4-r2-r2] seconde passe (PLACEMENT en fin de fichier) : %d instruction(s), "
              "%d import(s)" % (len(rouges_tete), len(taches2)))
        res2 = defaultdict(list)
        with ThreadPoolExecutor(max_workers=jobs) as ex:
            sorties = ex.map(lambda t: _lancer(t[0].module, t[0].segment, t[1], True, "fin"),
                             taches2)
            for (s, entree), (rc, err) in zip(taches2, sorties):
                res2[s.cle()].append((entree, rc, err))
        for s in rouges_tete:
            rouges = [(e, m) for e, rc, m in res2[s.cle()] if rc != 0]
            if not rouges:
                out[s.cle()] = {"categorie": "placement",
                                "detail": "TETE rouge, FIN DE FICHIER verte (%d ordres)"
                                          % len(res2[s.cle()])}
            else:
                out[s.cle()]["detail"] += " | FIN : %s -> %s" % (rouges[0][0], rouges[0][1])
    return out


def ventiler(sites: list[_Site], mesures: dict) -> dict:
    """Categorie DERIVEE par site. La somme est une PARTITION EXHAUSTIVE."""
    out = {}
    for s in sites:
        if s.cause_syn == "TYPE_CHECKING":
            out[s.cle()] = {"categorie": "TYPE_CHECKING", "detail": ""}
        elif s.conteneur:
            out[s.cle()] = {"categorie": "conditionnel", "detail": s.conteneur}
        elif s.cle() in mesures:
            out[s.cle()] = mesures[s.cle()]
        else:
            out[s.cle()] = {"categorie": "autre (%s/%s)" % (s.forme, s.cause_syn),
                            "detail": "non mesure"}
    return out


def imprimer(sites: list[_Site], cats: dict, verbeux: bool = False) -> None:
    par_cat = defaultdict(list)
    for s in sites:
        par_cat[cats[s.cle()]["categorie"]].append(s)
    total = sum(len(v) for v in par_cat.values())
    print("[270-r4-r2-r2] PARTITION EXHAUSTIVE des %d instruction(s) differee(s) :" % total)
    for cat in sorted(par_cat):
        print("   %-22s %4d" % (cat, len(par_cat[cat])))
    print("   %-22s %4d  (somme des categories == total : %s)"
          % ("TOTAL", total, "OUI" if total == len(sites) else "NON -- INCOHERENT"))
    for cat in sorted(par_cat):
        if cat in ("hissable", "TYPE_CHECKING") and not verbeux:
            continue
        print("   -- %s --" % cat)
        for s in par_cat[cat][: (10 ** 9 if verbeux else 40)]:
            print("      %s:%d  %s   [%s]"
                  % (s.module, s.ligne, s.segment.replace("\n", " ")[:90],
                     cats[s.cle()].get("detail", "")[:110]))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--inventaire", action="store_true", help="formes syntaxiques, aucune execution")
    ap.add_argument("--gratuits", action="store_true",
                    help="INVARIANT a zero : differes dont la cible est deja au preambule")
    ap.add_argument("--mesurer", action="store_true", help="hissage simule + import (lent)")
    ap.add_argument("--paquet", default="", help="borner a un prefixe de module")
    ap.add_argument("--jobs", type=int, default=12)
    ap.add_argument("--sortie", default="")
    ap.add_argument("--resume", default="")
    ap.add_argument("--verbeux", action="store_true")
    args = ap.parse_args()

    racine_paquet = RACINE / PAQUET
    if not racine_paquet.is_dir():
        print("[270-r4-r2-r2] ECHEC : paquet introuvable -> %s" % racine_paquet)
        return 2
    sites, _ = collecter(racine_paquet, args.paquet)
    print("[270-r4-r2-r2] TEMOIN : %d instruction(s) differee(s) vers %s/ (%s)"
          % (len(sites), PAQUET, args.paquet or "TOUT engine/"))
    if not sites:
        print("[270-r4-r2-r2] ECHEC : 0 site collecte -- un zero de balayage ne prouve RIEN")
        return 2

    if args.resume:
        d = json.loads(Path(args.resume).read_text(encoding="utf-8"))
        cats = d["categories"]
        manquants = [s for s in sites if s.cle() not in cats]
        if manquants:
            print("[270-r4-r2-r2] ATTENTION : %d site(s) absents du fichier de mesure "
                  "(l'arbre a bouge depuis)" % len(manquants))
            for s in manquants[:20]:
                print("      %s:%d" % (s.module, s.ligne))
            sites = [s for s in sites if s.cle() in cats]
        imprimer(sites, cats, args.verbeux)
        return 0

    if args.gratuits:
        lot = gratuits(racine_paquet, args.paquet)
        print("[270-r4-r2-r2] INVARIANT : %d differe(s) GRATUIT(s) (cible deja chargee par le "
              "preambule du meme fichier -- ni cycle possible, ni cout)" % len(lot))
        for mod, ligne, seg in lot[: (10 ** 9 if args.verbeux else 40)]:
            print("   %s:%d  %s" % (mod, ligne, seg))
        return 1 if lot else 0

    if args.inventaire:
        par_forme = defaultdict(int)
        for s in sites:
            cle = "%s / %s / %s" % (s.cause_syn, s.forme, s.conteneur or "(inconditionnel)")
            par_forme[cle] += 1
        print("[270-r4-r2-r2] INVENTAIRE syntaxique (aucune execution) :")
        for k in sorted(par_forme):
            print("   %-52s %4d" % (k, par_forme[k]))
        print("   %-52s %4d" % ("TOTAL", sum(par_forme.values())))
        return 0

    if args.mesurer:
        mesures = mesurer(sites, args.jobs)
        if not mesures:
            return 2
        cats = ventiler(sites, mesures)
        imprimer(sites, cats, args.verbeux)
        if args.sortie:
            Path(args.sortie).write_text(json.dumps(
                {"sites": [s.json() for s in sites], "categories": cats},
                sort_keys=True, indent=1), encoding="utf-8")
            print("[270-r4-r2-r2] ecrit -> %s" % args.sortie)
        return 0

    print("[270-r4-r2-r2] rien a faire : passer --inventaire, --mesurer ou --resume")
    return 0


if __name__ == "__main__":
    sys.exit(main())
