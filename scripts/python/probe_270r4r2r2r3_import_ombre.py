#!/usr/bin/env python3
"""#270-r4-r2-r2-r3 -- un import DIFFERE qui OMBRAGE un import module-level du meme nom.

LA QUESTION BINAIRE
-------------------
Un hissage qui AJOUTE l'import module-level sans RETIRER le differe fait-il ECHOUER une garde ?
Avant cette sonde : non. Le tri des differes (`probe_270r4r2r2_tri_differes.py`) compte des
INSTRUCTIONS ; il ne regarde jamais si le nom est DEJA LIE AU MODULE.

LA FAUTE, MESUREE
-----------------
En Python, un `import` dans le corps d'une fonction rend le nom LOCAL A TOUTE LA FONCTION
(`STORE_FAST`) -- pas seulement a partir de sa ligne. Tout chemin d'execution qui n'atteint pas
l'instruction lit une locale NON LIEE :

    UnboundLocalError: cannot access local variable 'StatType'
    engine/entities/effects/loki/status.py  (fn `applied_stat_mods`)

Le hissage `492c722f` (#270-r4-r2-r2) a produit exactement ce regime sur 14 sites / 10 fichiers :
il a ajoute `from ...stats import StatType` au niveau module SANS retirer le differe, qui vivait
sous `if self.value is not None:`. La branche `else` lisait alors une locale non liee.
`test_death_queue_ordering_live.py` rendait **15 failed / 7 passed** sur `master`.
Un hissage cense etre value-preserving a transforme une resolution GLOBALE QUI MARCHAIT en
`UnboundLocalError` -- et aucun cliquet ne le voyait.

LE CRITERE DE LA GARDE : LA REDONDANCE, PAS L'ARMEMENT
------------------------------------------------------
INVARIANT A ZERO : aucun import dans un corps de fonction ne doit lier un nom DEJA lie au niveau
module a l'execution. Le critere est la REDONDANCE elle-meme, pas le fait que le site soit
aujourd'hui ARME. Trois raisons, dont la premiere est MESUREE :

  * la distinction ARME/inoffensif est FRAGILE PAR NATURE. Sur les 14 sites de `492c722f`, TROIS
    changent de camp selon qu'on calcule la dominance depuis l'import SEUL ou depuis l'UNION des
    binders du nom -- c'est ce qui a fait ecrire "12 armes" (le compte des CONDITIONNELS) la ou
    la mesure rend UN SEUL arme. Une garde dont le critere est approximatif se degrade en silence ;
  * un site inoffensif est a UNE edition d'etre arme (deplacer une instruction, ajouter une
    branche) -- et rien ne le rattraperait, puisque c'est precisement l'etage qui manquait ;
  * la redondance n'apporte RIEN : le module est deja charge, le nom deja resolu ; l'instruction
    ne coute qu'un tour de `sys.modules` et un slot de locale.

L'ARMEMENT reste DERIVE et IMPRIME -- il dit la SEVERITE de chaque site -- en TROIS categories,
pas deux, parce que "arme / pas arme" ne sait pas dire JE NE SAIS PAS :

    ARME         une lecture n'est couverte par AUCUN binder du nom qui la DOMINE. Dominance
                 STRUCTURELLE : meme liste d'instructions, le binder DIRECTEMENT dedans (pas
                 enfoui dans un conteneur skippable), et AVANT la lecture. Les binders sont TOUS
                 ceux du nom (autre import, affectation, `with ... as`, walrus), pas seulement
                 l'import mesure : sans ce cran, deux imports du meme nom dans deux branches se
                 declarent mutuellement armes alors que chaque branche se couvre ;
    INDETERMINE  la seule lecture non couverte vit dans une portee IMBRIQUEE (`def`/`lambda`/
                 `class`). Au runtime elle passe par une cellule de fermeture, donc lire avant
                 l'affectation leve, mais l'ordre d'APPEL n'est PAS structurel -> ni vert ni
                 rouge, DIT ;
    REDONDANT    toutes les lectures sont couvertes.

L'ECHAPPATOIRE, AU SITE
-----------------------
Une ligne peut declarer `[import-ombre:voulu] <raison>` dans son commentaire de fin. Ce n'est ni
une liste blanche de fichiers ni un motif devine : c'est une declaration AU SITE, que la sonde
COMPTE et IMPRIME. Une raison VIDE est refusee -- une echappatoire sans motif est une porte
ouverte. Le plafond vit dans la garde
(`tests/engine/test_270r4r2r2r3_gardes_du_hissage_offline.py`).

CE QUE CETTE SONDE NE VOIT PAS -- DIT, PAS SOUS-ENTENDU
-------------------------------------------------------
  * le RESTE de `scripts/python/**` : l'invariant porte sur `engine/`, le gisement que notre
    cadence de hissage alimente. Le hors-perimetre est DECLARE a chaque run et MESURE par
    `--portee` (residu #270-r4-r2-r2-r3-r1) ;
  * les liaisons module-level qui ne sont PAS des imports (`X = ...`, `def X`, `class X`). Un
    import differe qui les ombrage a la meme signature d'echec. `--elargi` les MESURE et les
    imprime, mais l'invariant ne porte que sur les imports : melanger les deux rendrait le
    plafond illisible ;
  * les corps de CLASSE. Un import dans un corps de classe n'ombrage rien : le corps compile en
    `LOAD_NAME`, qui retombe sur le global. Comptes a part, jamais en ecart ;
  * `from x import *` : le nom lie n'est pas derivable statiquement. Compte a part ;
  * un nom soustrait a la portee locale par `global`/`nonlocal` : l'import ECRIT le global, il ne
    cree aucune locale. Compte a part.

Usage :
    python probe_270r4r2r2r3_import_ombre.py                    # invariant sur `engine/` (~2,5 s)
    python probe_270r4r2r2r3_import_ombre.py --mutants          # contre-epreuve (MORD + temoins)
    python probe_270r4r2r2r3_import_ombre.py --portee           # + le hors-perimetre (~25 s)
    python probe_270r4r2r2r3_import_ombre.py --historique 492c722f   # 14 sites, 1 ARME (rc 1)
    python probe_270r4r2r2r3_import_ombre.py --historique d450c362   # 0            (rc 0)
    python probe_270r4r2r2r3_import_ombre.py --racine <dir> [--paquet <nom>]

Sortie 0 = invariant tenu ; 1 sinon ; 2 = mesure IMPOSSIBLE (jamais rabattue sur un zero).
ASCII only (console Windows cp1252).
"""
from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent
PAQUET = "engine"
MARQUEUR_VOULU = "[import-ombre:voulu]"

#: Les noeuds qui ouvrent une PORTEE nouvelle : un import qui y vit n'ombrage pas la fonction
#: englobante, et une lecture qui y vit n'est pas structurellement ordonnee.
_PORTEES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef)
_FONCTIONS = (ast.FunctionDef, ast.AsyncFunctionDef)


class Ombre:
    """Un import differe dont un nom lie est DEJA lie au niveau module."""

    __slots__ = ("module", "fonction", "ligne", "nom", "ligne_module", "segment", "conteneur",
                 "severite", "raison", "exemption")

    #: TROIS severites, pas deux -- "arme / pas arme" ne sait pas dire "je ne sais pas".
    #:   ARME         une lecture du nom n'est couverte par AUCUN binder qui la domine
    #:                structurellement -> `UnboundLocalError` sur ce chemin ;
    #:   INDETERMINE  la seule lecture non couverte vit dans une portee IMBRIQUEE : au runtime
    #:                elle passe par une cellule de fermeture, et l'ordre d'APPEL n'est pas
    #:                structurel. Ni vert ni rouge : DIT ;
    #:   REDONDANT    toutes les lectures sont couvertes. L'instruction n'apporte rien -- et
    #:                elle est a UNE edition d'etre ARMEE.
    def __init__(self, module, fonction, ligne, nom, ligne_module, segment, conteneur,
                 severite, raison, exemption):
        self.module = module
        self.fonction = fonction
        self.ligne = ligne
        self.nom = nom
        self.ligne_module = ligne_module
        self.segment = segment
        self.conteneur = conteneur          # "" si directement dans le corps de la fonction
        self.severite = severite            # "ARME" | "INDETERMINE" | "REDONDANT"
        self.raison = raison
        self.exemption = exemption          # None | texte du motif declare au site

    def cle(self):
        return "%s:%d:%s" % (self.module, self.ligne, self.nom)

    def __repr__(self):
        return "<Ombre %s>" % self.cle()

    def texte(self):
        return ("%-11s %s:%d  %s  (fn `%s`, module-level ligne %s%s)%s"
                % (self.severite, self.module, self.ligne, self.nom, self.fonction,
                   self.ligne_module, ", sous %s" % self.conteneur if self.conteneur else "",
                   "  " + self.raison if self.raison else ""))


# ============================================================ helpers AST

def _est_type_checking(test: ast.expr) -> bool:
    if isinstance(test, ast.Name) and test.id == "TYPE_CHECKING":
        return True
    if isinstance(test, ast.Attribute) and test.attr == "TYPE_CHECKING":
        return True
    return False


def _listes_filles(noeud):
    """Les listes d'INSTRUCTIONS filles directes de `noeud` (y compris via `ExceptHandler`)."""
    for _, val in ast.iter_fields(noeud):
        if not isinstance(val, list) or not val:
            continue
        if isinstance(val[0], ast.stmt):
            yield val
        elif isinstance(val[0], ast.excepthandler):
            for h in val:
                for sous in _listes_filles(h):
                    yield sous


def _noms_lies(noeud) -> list:
    """Les noms que cette instruction d'import LIE reellement.

    `import a.b.c`      lie `a`      ; `import a.b as z` lie `z`
    `from m import x`   lie `x`      ; `from m import x as z` lie `z`
    `from m import *`   -> non derivable statiquement : rendu vide, compte a part."""
    out = []
    if isinstance(noeud, ast.Import):
        for a in noeud.names:
            out.append(a.asname or a.name.split(".")[0])
    elif isinstance(noeud, ast.ImportFrom):
        for a in noeud.names:
            if a.name == "*":
                continue
            out.append(a.asname or a.name)
    return out


def noms_module_level(arbre: ast.Module) -> dict:
    """{nom lie: ligne} par les imports du NIVEAU MODULE, a l'EXECUTION.

    On descend dans les `if`/`try`/`with`/`for` du niveau module (ils s'executent a l'import),
    mais PAS dans `if TYPE_CHECKING:` (jamais execute -- son `orelse`, lui, l'est), ni dans les
    corps de `def`/`class` (portees distinctes)."""
    out: dict = {}

    def descendre(corps):
        for st in corps:
            if isinstance(st, (ast.Import, ast.ImportFrom)):
                for n in _noms_lies(st):
                    out.setdefault(n, st.lineno)
                continue
            if isinstance(st, _PORTEES):
                continue
            if isinstance(st, ast.If) and _est_type_checking(st.test):
                descendre(st.orelse)          # la branche `else` s'execute, elle
                continue
            for liste in _listes_filles(st):
                descendre(liste)

    descendre(arbre.body)
    return out


def autres_liaisons_module_level(arbre: ast.Module) -> dict:
    """{nom: ligne} lie au niveau module par autre chose qu'un import (`X = ...`, `def`, `class`).

    Mesure d'ELARGISSEMENT : meme signature d'echec, mais hors de l'invariant (cf. docstring)."""
    out: dict = {}

    def poser(nom, ligne):
        out.setdefault(nom, ligne)

    def cibles(n):
        if isinstance(n, ast.Name):
            yield n.id
        elif isinstance(n, (ast.Tuple, ast.List)):
            for e in n.elts:
                for x in cibles(e):
                    yield x
        elif isinstance(n, ast.Starred):
            for x in cibles(n.value):
                yield x

    def descendre(corps):
        for st in corps:
            if isinstance(st, _PORTEES):
                poser(getattr(st, "name", ""), st.lineno)
                continue
            if isinstance(st, ast.Assign):
                for t in st.targets:
                    for nom in cibles(t):
                        poser(nom, st.lineno)
                continue
            if isinstance(st, (ast.AnnAssign, ast.AugAssign)):
                for nom in cibles(st.target):
                    poser(nom, st.lineno)
                continue
            if isinstance(st, ast.If) and _est_type_checking(st.test):
                descendre(st.orelse)
                continue
            for liste in _listes_filles(st):
                descendre(liste)

    descendre(arbre.body)
    out.pop("", None)
    return out


def _indexer(corps, prefixe, plan, nom_conteneur=""):
    """Chemin STRUCTUREL de chaque instruction de CETTE portee : [(id(liste), index), ...] depuis
    le corps de la fonction. `plan` recoit (noeud, chemin, conteneur) -- le conteneur est le noeud
    de controle le plus proche, "" si l'instruction est directement dans le corps.

    ATTENTION : on s'ARRETE aux portees imbriquees : leur contenu appartient a une AUTRE portee, et c'est
    aussi ce qui evite de re-parcourir chaque corps de fonction une fois par ancetre (le balayage
    complet passait de quadratique a lineaire)."""
    for i, st in enumerate(corps):
        chemin = prefixe + [(id(corps), i)]
        plan.append((st, chemin, nom_conteneur))
        if isinstance(st, _PORTEES):
            continue                                   # portee distincte
        for liste in _listes_filles(st):
            _indexer(liste, chemin, plan, type(st).__name__)


_NAMEDEXPR = getattr(ast, "NamedExpr", ())


def _analyser_instruction(st):
    """UNE SEULE traversee de l'instruction ELLE-MEME -> (noms LUS directement, noms lus en
    PORTEE IMBRIQUEE, noms lies par WALRUS).

    "L'instruction elle-meme" = son test / son expression, SANS descendre dans ses
    sous-instructions (elles sont visitees pour leur propre compte) ni dans une portee imbriquee
    (dont on ne retient que les noms LUS, pour la severite INDETERMINE : au runtime ces lectures
    passent par une cellule de FERMETURE, et l'ordre d'APPEL n'est pas structurel).

    DEUX RAISONS DE PERFORMANCE, toutes deux MESUREES -- ne pas defaire :
      * ne JAMAIS remplacer par `ast.walk(st)` : un `ast.walk` par instruction re-parcourt le
        corps de chaque bloc une fois par ancetre (quadratique) ;
      * les trois collectes etaient trois parcours distincts du meme sous-arbre. Fusionnees, le
        balayage de `scripts/python` (1 969 fichiers) passe de 33,9 s a ~18 s, et `engine/` seul
        de 10,6 s a 2,4 s."""
    lus, imb, walrus = [], set(), []

    def avaler_portee(noeud):
        for x in ast.walk(noeud):
            if isinstance(x, ast.Name) and isinstance(x.ctx, ast.Load):
                imb.add(x.id)

    if isinstance(st, _PORTEES):
        # l'instruction EST une portee : son CORPS appartient a la portee imbriquee ; son EN-TETE
        # (decorateurs, valeurs par defaut, annotations) s'evalue dans la portee courante.
        avaler_portee(st)
    sous = {id(x) for liste in _listes_filles(st) for x in liste}
    pile, vus = [st], {id(st)}
    while pile:
        n = pile.pop()
        for e in ast.iter_child_nodes(n):
            if id(e) in sous or id(e) in vus:
                continue
            vus.add(id(e))
            if isinstance(e, _PORTEES):
                avaler_portee(e)
                continue
            if isinstance(e, ast.Name):
                if isinstance(e.ctx, ast.Load):
                    lus.append(e.id)
            elif _NAMEDEXPR and isinstance(e, _NAMEDEXPR) and isinstance(e.target, ast.Name):
                walrus.append(e.target.id)
            pile.append(e)
    return lus, imb, walrus


def _noms_lies_par(st, walrus=()) -> list:
    """Les noms que CETTE instruction lie dans la portee courante (hors sous-instructions et
    portees imbriquees). C'est ce qui permet de dire qu'une lecture est COUVERTE par un binder
    autre que l'import mesure -- un second import du meme nom dans une autre branche, une
    affectation, un `with ... as`, un walrus (fourni par `_analyser_instruction`)."""
    def cibles(n):
        if isinstance(n, ast.Name):
            yield n.id
        elif isinstance(n, (ast.Tuple, ast.List)):
            for e in n.elts:
                for x in cibles(e):
                    yield x
        elif isinstance(n, ast.Starred):
            for x in cibles(n.value):
                yield x

    out = list(walrus)
    if isinstance(st, (ast.Import, ast.ImportFrom)):
        out.extend(_noms_lies(st))
    elif isinstance(st, ast.Assign):
        for t in st.targets:
            out.extend(cibles(t))
    elif isinstance(st, (ast.AnnAssign, ast.AugAssign)):
        if getattr(st, "value", None) is not None or isinstance(st, ast.AugAssign):
            out.extend(cibles(st.target))
    elif isinstance(st, (ast.For, ast.AsyncFor)):
        out.extend(cibles(st.target))
    elif isinstance(st, (ast.With, ast.AsyncWith)):
        for item in st.items:
            if item.optional_vars is not None:
                out.extend(cibles(item.optional_vars))
    elif isinstance(st, _PORTEES) and getattr(st, "name", None):
        out.append(st.name)
    return out


def _domine(p_imp, p_lec) -> bool:
    """L'instruction d'import DOMINE-t-elle structurellement la lecture ?

    Vrai ssi les deux sont dans la MEME liste d'instructions, l'import DIRECTEMENT (pas enfoui
    dans un conteneur qui peut etre saute), et AVANT elle."""
    n = min(len(p_imp), len(p_lec))
    k = 0
    while k < n and p_imp[k] == p_lec[k]:
        k += 1
    if k >= len(p_imp):
        return True                                    # l'import contient la lecture (impossible)
    if k >= len(p_lec):
        return False
    liste_i, idx_i = p_imp[k]
    liste_l, idx_l = p_lec[k]
    if liste_i != liste_l:
        return False                                   # branches distinctes du meme noeud
    if len(p_imp) != k + 1:
        return False                                   # import enfoui plus profond
    return idx_i < idx_l


# ============================================================ analyse d'un module

def analyser(nom_module: str, src: str, lignes=None) -> tuple:
    """Rend (ombres, stats) pour UNE source. Testable sur une chaine -- c'est ce qui rend la
    contre-epreuve possible sans ecrire un seul fichier."""
    arbre = ast.parse(src, filename=nom_module)
    # `str.splitlines()` ne decoupe PAS comme le compilateur (form feed, \x85) : 7 fichiers
    # d'`engine/` en portent un, et la numerotation AST decalait d'une ligne (#270-r4-r2-r2).
    lignes = lignes if lignes is not None else src.split("\n")
    au_module = noms_module_level(arbre)
    stats = {"fonctions": 0, "imports_differes": 0, "etoile": 0, "corps_de_classe": 0,
             "global_declare": 0, "noms_module_level": len(au_module)}
    ombres = []

    for fn in ast.walk(arbre):
        if not isinstance(fn, _FONCTIONS):
            continue
        stats["fonctions"] += 1
        plan: list = []
        # `plan` ne contient QUE les instructions de CETTE portee : `_indexer` s'arrete aux
        # portees imbriquees, qu'`ast.walk` visitera comme `fn` a leur tour.
        _indexer(fn.body, [], plan)
        imports = [(st, ch, co) for st, ch, co in plan
                   if isinstance(st, (ast.Import, ast.ImportFrom))]
        if not imports:
            continue
        # lectures (nom -> [chemins]), binders (nom -> [chemins]), noms lus en portee imbriquee,
        # et les noms soustraits a la portee locale par `global`/`nonlocal`.
        lectures: dict = {}
        binders: dict = {}
        imbriques = set()
        globaux = set()
        parametres = set()
        for a in fn.args.args + fn.args.posonlyargs + fn.args.kwonlyargs:
            parametres.add(a.arg)
        for a in (fn.args.vararg, fn.args.kwarg):
            if a is not None:
                parametres.add(a.arg)
        for st, chemin, _co in plan:
            if isinstance(st, (ast.Global, ast.Nonlocal)):
                globaux.update(st.names)
            lus, imb, walrus = _analyser_instruction(st)
            for nd in lus:
                lectures.setdefault(nd, []).append(chemin)
            for nb in _noms_lies_par(st, walrus):
                binders.setdefault(nb, []).append(chemin)
            imbriques |= imb

        for st, p_imp, cont in imports:
            stats["imports_differes"] += 1
            if isinstance(st, ast.ImportFrom) and any(a.name == "*" for a in st.names):
                stats["etoile"] += 1
            for nom in _noms_lies(st):
                if nom not in au_module:
                    continue
                if nom in globaux:
                    stats["global_declare"] += 1
                    continue                       # `global X` : l'import ecrit le GLOBAL, pas une locale
                raisons = []
                severite = "REDONDANT"
                if nom not in parametres:
                    # une lecture est COUVERTE des qu'UN binder du nom la domine -- pas seulement
                    # l'import mesure. Sans ce cran, deux imports du meme nom dans deux branches
                    # se declarent mutuellement armes alors que chaque branche se couvre.
                    for p_lec in lectures.get(nom, ()):
                        if not any(_domine(p_b, p_lec) for p_b in binders.get(nom, ())):
                            raisons.append("lecture NON couverte par un binder du nom (ligne "
                                           "d'import non dominante)")
                            severite = "ARME"
                            break
                    if severite == "REDONDANT" and nom in imbriques:
                        raisons.append("lecture en portee imbriquee : l'ordre d'APPEL n'est pas "
                                       "structurel")
                        severite = "INDETERMINE"
                texte = lignes[st.lineno - 1] if 0 < st.lineno <= len(lignes) else ""
                exemption = None
                if MARQUEUR_VOULU in texte:
                    exemption = texte.split(MARQUEUR_VOULU, 1)[1].strip(" #\t\r\n")
                ombres.append(Ombre(
                    module=nom_module,
                    fonction=fn.name,
                    ligne=st.lineno,
                    nom=nom,
                    ligne_module=au_module[nom],
                    segment=texte.strip()[:100],
                    conteneur=cont,
                    severite=severite,
                    raison=" + ".join(dict.fromkeys(raisons)),
                    exemption=exemption))
    # imports en corps de CLASSE : comptes, jamais en ecart (LOAD_NAME retombe sur le global)
    for cl in ast.walk(arbre):
        if isinstance(cl, ast.ClassDef):
            for st in cl.body:
                if isinstance(st, (ast.Import, ast.ImportFrom)):
                    stats["corps_de_classe"] += 1
    return ombres, stats


def analyser_elargi(nom_module: str, src: str, lignes=None) -> list:
    """ELARGISSEMENT : imports differes qui ombragent une liaison module-level NON-import."""
    arbre = ast.parse(src, filename=nom_module)
    lignes = lignes if lignes is not None else src.split("\n")
    imports_ml = noms_module_level(arbre)
    autres = autres_liaisons_module_level(arbre)
    out = []
    for fn in ast.walk(arbre):
        if not isinstance(fn, _FONCTIONS):
            continue
        plan: list = []
        _indexer(fn.body, [], plan)
        for st, _ch, cont in plan:
            if not isinstance(st, (ast.Import, ast.ImportFrom)):
                continue
            for nom in _noms_lies(st):
                if nom in imports_ml or nom not in autres:
                    continue
                texte = lignes[st.lineno - 1] if 0 < st.lineno <= len(lignes) else ""
                out.append(Ombre(nom_module, fn.name, st.lineno, nom, autres[nom],
                                 texte.strip()[:100], cont, "REDONDANT",
                                 "liaison module-level NON-import", None))
    return out


# ============================================================ balayage d'un arbre

def _nom_module(chemin: Path, racine: Path) -> str:
    rel = chemin.relative_to(racine)
    parts = list(rel.parts)
    if parts[-1] == "__init__.py":
        parts = parts[:-1]
    else:
        parts[-1] = parts[-1][: -len(".py")]
    return ".".join(parts) or racine.name


def balayer(racine_paquet: Path, racine: Path | None = None, elargi: bool = False) -> tuple:
    """Rend (ombres, stats, elargies) sur tous les `.py` sous `racine_paquet`."""
    racine = racine or racine_paquet.parent
    ombres, elargies = [], []
    stats = {"fichiers": 0, "fonctions": 0, "imports_differes": 0, "etoile": 0,
             "corps_de_classe": 0, "global_declare": 0, "illisibles": 0}
    for f in sorted(racine_paquet.rglob("*.py")):
        if "__pycache__" in f.parts:
            continue
        src = f.read_text(encoding="utf-8", errors="replace")
        nom = _nom_module(f, racine)
        try:
            lot, st = analyser(nom, src)
        except SyntaxError as e:
            stats["illisibles"] += 1
            print("  ILLISIBLE %s -> %s" % (nom, e))
            continue
        stats["fichiers"] += 1
        for k in ("fonctions", "imports_differes", "etoile", "corps_de_classe",
                  "global_declare"):
            stats[k] += st[k]
        ombres.extend(lot)
        if elargi:
            elargies.extend(analyser_elargi(nom, src))
    return ombres, stats, elargies


def mesurer_hors_perimetre(base: Path):
    """Les ombrages de `scripts/python/**` qui NE SONT PAS sous `engine/`.

    L'invariant ne les couvre pas -- ils vivent dans des fichiers que d'autres tranches editent,
    et les rabattre dans le meme plafond le rendrait illisible. Ils sont MESURES et IMPRIMES :
    "un compte filtre DIT ce qu'il filtre". Rend `None` si la portee est vide (jamais un zero
    fabrique)."""
    ombres, stats, _ = balayer(base, base.parent)
    if stats["fichiers"] < 100:
        return None
    prefixe = "%s.%s" % (base.name, PAQUET)          # `python.engine`
    lot = [o for o in ombres
           if o.module != prefixe and not o.module.startswith(prefixe + ".")]
    return len(lot), sorted(lot, key=lambda x: ({"ARME": 0, "INDETERMINE": 1}.get(x.severite, 2),
                                                x.module, x.ligne))


def mesurer_ref_git(ref: str):
    """Rejoue le balayage sur l'`engine/` d'une REVISION GIT -- la contre-epreuve sur la faute
    HISTORIQUE, reproductible par une commande au lieu d'etre affirmee dans un rapport.

    `492c722f` (le hissage de #270-r4-r2-r2) porte les 14 sites ; `d450c362` (le correctif) rend 0.
    Rend `None` si la revision n'est pas atteignable -- une mesure impossible n'est PAS un zero."""
    import subprocess
    import tarfile
    import tempfile

    depot = Path(__file__).resolve().parents[2]
    if subprocess.run(["git", "cat-file", "-e", ref + "^{commit}"], cwd=str(depot),
                      capture_output=True).returncode != 0:
        return None
    tmp = Path(tempfile.mkdtemp(prefix="ombre_hist_"))
    tar = tmp / "arbre.tar"
    r = subprocess.run(["git", "archive", ref, "scripts/python/engine", "-o", str(tar)],
                       cwd=str(depot), capture_output=True, text=True)
    if r.returncode != 0 or not tar.exists():
        return None
    with tarfile.open(tar) as t:
        try:
            t.extractall(tmp, filter="data")          # 3.12+ ; defaut a partir de 3.14
        except TypeError:
            t.extractall(tmp)
    base = tmp / "scripts" / "python"
    if not (base / PAQUET).is_dir():
        return None
    ombres, stats, _ = balayer(base / PAQUET, base)
    return ombres, stats, tmp


# ============================================================ contre-epreuve par mutants

#: Chaque mutant est une SOURCE SYNTHETIQUE. `attendu` = le nombre minimal d'ombres que le
#: detecteur DOIT rendre, `severite` = la severite qu'il DOIT poser. `a_mordu` est imprime
#: SEPAREMENT du verdict : une contre-epreuve inerte passe pour mordante, et ce depot s'est
#: deja fait avoir plusieurs fois de suite.
MUTANTS = [
    ("LA FAUTE HISTORIQUE : differe sous un `if`, lecture dans l'AUTRE chemin (status.py)",
     "from engine.entities.stats import StatType\n"
     "\n"
     "\n"
     "class E:\n"
     "    def applied_stat_mods(self, ctx):\n"
     "        if self.value is not None:\n"
     "            from engine.entities.stats import StatType\n"
     "            return [(int(StatType.FIXED_ARMOR), int(self.value))]\n"
     "        return [(int(StatType.ARMOR), 0)]\n", 1, "ARME"),
    ("import differe INCONDITIONNEL mais lecture ANTERIEURE",
     "from engine.a import X\n"
     "\n"
     "\n"
     "def f():\n"
     "    y = X\n"
     "    from engine.a import X\n"
     "    return y, X\n", 1, "ARME"),
    ("`import a.b` qui ombrage `import a.c` du module (le nom lie est `a`)",
     "import engine.services\n"
     "\n"
     "\n"
     "def f(c):\n"
     "    if c:\n"
     "        import engine.runner\n"
     "    return engine.services\n", 1, "ARME"),
    ("alias : `import x as z` ombrage `import y as z`",
     "import engine.a as z\n"
     "\n"
     "\n"
     "def f(c):\n"
     "    if c:\n"
     "        import engine.b as z\n"
     "    return z\n", 1, "ARME"),
    ("redondant NON arme (import en tete, dominant) -- doit ETRE VU quand meme",
     "from engine.a import X\n"
     "\n"
     "\n"
     "def f():\n"
     "    from engine.a import X\n"
     "    return X\n", 1, "REDONDANT"),
    ("`if TYPE_CHECKING:` DANS la fonction : jamais execute, mais le nom devient LOCAL",
     "from typing import TYPE_CHECKING\n"
     "from engine.a import X\n"
     "\n"
     "\n"
     "def f():\n"
     "    if TYPE_CHECKING:\n"
     "        from engine.a import X\n"
     "    return X\n", 1, "ARME"),
    ("lecture en portee IMBRIQUEE : ni vert ni rouge -- INDETERMINE, et dit",
     "from engine.a import X\n"
     "\n"
     "\n"
     "def f():\n"
     "    from engine.a import X\n"
     "\n"
     "    def g():\n"
     "        return X\n"
     "    return g\n", 1, "INDETERMINE"),
    ("DEUX branches, chacune couverte par SON import : redondant, PAS arme",
     "from engine.a import X\n"
     "\n"
     "\n"
     "def f(c):\n"
     "    if c:\n"
     "        from engine.a import X\n"
     "        return X\n"
     "    from engine.a import X\n"
     "    return X\n", 2, "REDONDANT"),
]

#: Sources qui NE DOIVENT PAS rougir. Sans elles, un detecteur qui rendrait tout serait vert.
TEMOINS_NEGATIFS = [
    ("differe SANS import module-level du meme nom",
     "def f():\n    from engine.a import X\n    return X\n"),
    ("le module-level est sous `if TYPE_CHECKING:` -> le differe est NECESSAIRE",
     "from typing import TYPE_CHECKING\n"
     "if TYPE_CHECKING:\n"
     "    from engine.a import X\n"
     "\n"
     "\n"
     "def f():\n"
     "    from engine.a import X\n"
     "    return X\n"),
    ("import en corps de CLASSE : LOAD_NAME retombe sur le global, aucun ombrage",
     "from engine.a import X\n"
     "\n"
     "\n"
     "class C:\n"
     "    from engine.a import X\n"),
    ("noms DIFFERENTS : `from m import a` au module, `from m import b` differe",
     "from engine.m import a\n"
     "\n"
     "\n"
     "def f():\n"
     "    from engine.m import b\n"
     "    return a, b\n"),
    ("alias distinct : le differe lie un AUTRE nom",
     "from engine.m import X\n"
     "\n"
     "\n"
     "def f():\n"
     "    from engine.m import X as Y\n"
     "    return X, Y\n"),
    ("portee IMBRIQUEE : l'import vit dans une `def` interne, pas dans la fonction porteuse",
     "from engine.a import X\n"
     "\n"
     "\n"
     "def f():\n"
     "    def g():\n"
     "        import engine.b\n"
     "        return engine.b\n"
     "    return g\n"),
    ("`global X` : l'import ECRIT le global, il ne cree aucune locale",
     "import engine.a as X\n"
     "\n"
     "\n"
     "def f():\n"
     "    global X\n"
     "    import engine.a as X\n"
     "    return X\n"),
]


def severites(lot) -> str:
    return ",".join(sorted({o.severite for o in lot})) or "(aucune)"


def contre_epreuve() -> int:
    print("\nCONTRE-EPREUVE PAR MUTANTS (a_mordu est rendu SEPAREMENT du verdict)")
    inertes = mal_classes = 0
    for nom, src, attendu, sev_attendue in MUTANTS:
        lot, _ = analyser("mutant", src)
        a_mordu = len(lot) >= attendu
        sev_ok = bool(lot) and all(o.severite == sev_attendue for o in lot)
        print("  %-6s severite=%-12s %s"
              % ("MORD" if a_mordu else "INERTE", severites(lot), nom))
        if not a_mordu:
            inertes += 1
        elif not sev_ok:
            mal_classes += 1
            print("         MAL CLASSE : severite attendue %s, mesuree %s"
                  % (sev_attendue, severites(lot)))
    print("  -> %d mutant(s) INERTE(s) et %d MAL CLASSE(s) sur %d"
          % (inertes, mal_classes, len(MUTANTS)))

    print("\nTEMOINS NEGATIFS (aucun ne doit rougir -- un detecteur qui rend TOUT serait vert)")
    faux = 0
    for nom, src in TEMOINS_NEGATIFS:
        lot, _ = analyser("temoin", src)
        if lot:
            faux += 1
            print("  FAUX POSITIF  %s -> %s" % (nom, [o.cle() for o in lot]))
        else:
            print("  OK            %s" % nom)
    print("  -> %d faux positif(s) sur %d" % (faux, len(TEMOINS_NEGATIFS)))
    return inertes + mal_classes + faux


# ============================================================ main

def main() -> int:
    ap = argparse.ArgumentParser(description="import differe qui OMBRAGE un import module-level")
    ap.add_argument("--racine", default="", help="arbre a balayer (defaut : `engine/` du depot)")
    ap.add_argument("--paquet", default=PAQUET, help="nom du repertoire paquet sous la racine")
    ap.add_argument("--mutants", action="store_true", help="contre-epreuve (chaque etage MORD)")
    ap.add_argument("--elargi", action="store_true",
                    help="MESURE aussi l'ombrage d'une liaison module-level NON-import")
    ap.add_argument("--portee", action="store_true",
                    help="MESURE le hors-perimetre (tout `scripts/python`, ~18 s) -- hors verdict")
    ap.add_argument("--historique", default="", metavar="REF",
                    help="rejoue le balayage sur l'`engine/` d'une revision git (ex. 492c722f, le "
                         "hissage fautif : 14 sites / 1 ARME ; d450c362, le correctif : 0)")
    ap.add_argument("--verbeux", action="store_true")
    args = ap.parse_args()

    if args.historique:
        res = mesurer_ref_git(args.historique)
        if res is None:
            print("[270r4r2r2r3] MESURE IMPOSSIBLE : revision `%s` inatteignable ou sans "
                  "`scripts/python/engine` -- ce n'est PAS un zero" % args.historique)
            return 2
        ombres, stats, tmp = res
        print("[270r4r2r2r3] REVISION %s : %d fichier(s), %d ombrage(s) "
              "(ARME=%d, INDETERMINE=%d, REDONDANT=%d)"
              % (args.historique, stats["fichiers"], len(ombres),
                 len([o for o in ombres if o.severite == "ARME"]),
                 len([o for o in ombres if o.severite == "INDETERMINE"]),
                 len([o for o in ombres if o.severite == "REDONDANT"])))
        for o in sorted(ombres, key=lambda x: ({"ARME": 0, "INDETERMINE": 1}.get(x.severite, 2),
                                               x.module, x.ligne)):
            print("    " + o.texte())
        print("[270r4r2r2r3] arbre extrait -> %s" % tmp)
        return 1 if ombres else 0

    base = Path(args.racine).resolve() if args.racine else RACINE
    racine_paquet = base / args.paquet
    if not racine_paquet.is_dir():
        print("[270r4r2r2r3] ECHEC : paquet introuvable -> %s" % racine_paquet)
        return 2

    ombres, stats, elargies = balayer(racine_paquet, base, args.elargi)

    print("[270r4r2r2r3] TEMOIN : %d fichier(s), %d fonction(s), %d import(s) differe(s) "
          "(%d en corps de classe, %d etoile, %d sous `global`, %d illisible(s))"
          % (stats["fichiers"], stats["fonctions"], stats["imports_differes"],
             stats["corps_de_classe"], stats["etoile"], stats["global_declare"],
             stats["illisibles"]))
    if stats["fichiers"] < 10 or stats["fonctions"] < 100:
        print("[270r4r2r2r3] ECHEC : portee DERISOIRE -- un zero ne prouve RIEN")
        return 2

    exemptees = [o for o in ombres if o.exemption is not None]
    sans_motif = [o for o in exemptees if not o.exemption]
    ecarts = [o for o in ombres if o.exemption is None]
    par_sev = {s: [o for o in ombres if o.severite == s]
               for s in ("ARME", "INDETERMINE", "REDONDANT")}

    print("\nINVARIANT A ZERO -- un import differe ne lie JAMAIS un nom deja lie au module")
    print("  ombrages TOTAL = %d   (ARME=%d, INDETERMINE=%d, REDONDANT=%d ; la somme vaut le "
          "total : %s)"
          % (len(ombres), len(par_sev["ARME"]), len(par_sev["INDETERMINE"]),
             len(par_sev["REDONDANT"]),
             "OUI" if sum(len(v) for v in par_sev.values()) == len(ombres) else "NON -- INCOHERENT"))
    print("  /!\\ le CRITERE de la garde est la REDONDANCE, pas l'armement : les trois "
          "severites sont des ecarts.")
    print("  EXEMPTIONS declarees au site %s : %d" % (MARQUEUR_VOULU, len(exemptees)))
    for o in exemptees:
        print("    %s  -- motif : %s" % (o.texte(), o.exemption or "(VIDE -- REFUSE)"))
    if sans_motif:
        print("  ECHEC : %d exemption(s) SANS MOTIF -- une echappatoire sans raison est une "
              "porte ouverte" % len(sans_motif))
    print("  %s  ecarts = %d (dont %d ARMES, %d INDETERMINES)"
          % ("OK" if not (ecarts or sans_motif) else "ECHEC", len(ecarts),
             len([o for o in ecarts if o.severite == "ARME"]),
             len([o for o in ecarts if o.severite == "INDETERMINE"])))
    for o in sorted(ecarts, key=lambda x: ({"ARME": 0, "INDETERMINE": 1}.get(x.severite, 2),
                                           x.module, x.ligne))[: (10 ** 9 if args.verbeux else 60)]:
        print("    " + o.texte())
        if args.verbeux:
            print("        " + o.segment)

    if args.elargi:
        print("\nELARGISSEMENT (MESURE, hors invariant) -- ombrage d'une liaison module-level "
              "NON-import : %d" % len(elargies))
        for o in elargies[: (10 ** 9 if args.verbeux else 40)]:
            print("    " + o.texte())

    # -- PORTEE : un compte filtre DIT ce qu'il filtre (CLAUDE.md). L'invariant porte sur
    # `engine/` -- le gisement que notre cadence de hissage alimente. Le RESTE de
    # `scripts/python` n'est PAS garde : il est nomme ici a chaque run, et MESURE sur demande
    # (le balayage complet coute ~18 s pour 1 969 fichiers). Residu #270-r4-r2-r2-r3-r1.
    print("\nPORTEE -- CE QUE L'INVARIANT NE GARDE PAS")
    print("  perimetre de l'invariant : `%s/` (%d fichier(s))" % (args.paquet, stats["fichiers"]))
    print("  HORS perimetre : le reste de `scripts/python/**` -- residu #270-r4-r2-r2-r3-r1, "
          "mesurable par --portee")
    print("  HORS PORTEE par construction : corps de CLASSE (LOAD_NAME retombe sur le global), "
          "`from x import *` (nom non derivable), liaisons module-level NON-import (--elargi)")
    if args.portee and not args.racine:
        hors = mesurer_hors_perimetre(base)
        if hors is None:
            print("  MESURE REFUSEE : portee derisoire -- un zero ne prouverait RIEN")
        else:
            n_hors, lot = hors
            print("  MESURE : %d ombrage(s) sous `scripts/python/**` HORS `%s/`"
                  % (n_hors, args.paquet))
            for o in lot[: (10 ** 9 if args.verbeux else 20)]:
                print("    " + o.texte())

    rc = 1 if (ecarts or sans_motif) else 0
    if args.mutants:
        rc = 1 if (contre_epreuve() or rc) else 0

    print("\nVERDICT : " + ("OK -- aucun import differe n'ombrage un import module-level"
                            if rc == 0 else "ECHEC"))
    return rc


if __name__ == "__main__":
    sys.exit(main())
