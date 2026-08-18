#!/usr/bin/env python
"""#485-r1 -- VIDER les barils de re-export d'`engine/`, en marche a blanc par defaut.

LE PROBLEME N'EST PAS LES 262 DIFFERES, C'EST L'UNIQUE CAUSE QUI LES PRODUIT
---------------------------------------------------------------------------
Mesure #485 : 314 imports DIFFERES vers `engine.*` ecrits dans `engine/**`, dont 262 PORTEURS.
Re-mesure de leur RAISON : ~100 % ferment leur boucle par une cascade d'`__init__.py`, une seule
par une dependance mutuelle REELLE. Python execute l'`__init__` de CHAQUE paquet ancetre avant
d'atteindre une feuille : `import engine.entities.stats` execute `engine/entities/__init__.py`,
qui tire `effects` -> `loki` -> ... Toucher une feuille traine donc un millier de modules, et le
differe est ce qui evite la boucle ainsi creee. Il y a UN probleme, pas 262.

CE QUE CET OUTIL FAIT, DANS CET ORDRE
-------------------------------------
    inventaire  derive la table `symbole -> module d'origine` DEPUIS LES BARILS EUX-MEMES
                (elle y est deja ecrite : c'est ce que chaque `__init__.py` re-exporte),
                et ENUMERE tout ce qu'il ne sait pas faire.
    reecrire    `from engine.X import Y` -> `from engine.X.enfant import Y` chez les
                CONSOMMATEURS. Marche a blanc ; `--appliquer` pour ecrire.
    vider       retire du baril les re-exports que PLUS PERSONNE ne reclame, et ajuste
                `__all__`. C'est CE pas qui allege la cascade -- reecrire seul ne change RIEN
                au graphe, puisque Python execute le paquet parent quoi qu'on ecrive.

⚠ L'ORDRE EST CONTRAIGNANT, et ce n'est pas une preference : `vider` avant `reecrire` casse
tous les consommateurs. `vider` REFUSE de retirer un symbole encore reclame par un fichier du
perimetre -- c'est ce refus, et non l'ordre des sous-commandes, qui tient l'invariant.

CE QU'IL NE SAIT PAS FAIRE EST ENUMERE, JAMAIS AVALE
----------------------------------------------------
Un outil qui rend << 784 reecrits >> en ayant saute 30 cas en silence est pire qu'un outil qui
en rend 754 et NOMME les 30. Chaque refus sort avec son motif et son site (`--refus` pour la
liste integrale). Les motifs sont un ENUM (`Refus`), pas des chaines libres : une liste blanche
de motifs ne peut pas montrer le motif qu'elle a oublie -- un cas non classe sort en
`Refus.AUTRE` avec le noeud AST, il ne disparait pas.

LES BARILS A REGISTRE SONT EXCLUS, ET IDENTIFIES MECANIQUEMENT
--------------------------------------------------------------
Certains `__init__.py` importent leurs enfants POUR L'EFFET DE BORD : l'enfant s'enregistre au
chargement (`@register(...)`, `REGISTRY[x] = ...`). Court-circuiter le baril ne leve alors AUCUNE
erreur -- le registre reste vide et `.get(cle)` rend `None`, exactement la panne que `probe_313`
etape 5 a mesuree ailleurs. Ils sont donc EXCLUS du remplacement naif, et l'exclusion est
DERIVEE (imports a effet de bord pur + modules enregistreurs), jamais une liste en dur.

ASCII only (console Windows cp1252).
"""
from __future__ import annotations

import argparse
import ast
import enum
import io
import sys
import tokenize
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

#: Racine RESOLUE DEPUIS `__file__`, jamais depuis le CWD -- meme cran que `probe_485`
#: (`probe_457` a rendu un FAUX `FAIL` pour avoir lu son perimetre depuis le repertoire courant).
ICI = Path(__file__).resolve().parent

EX_VERT, EX_ROUGE, EX_PAS_MESURE = 0, 1, 2

#: Largeur de ligne visee a la re-ecriture. Au-dela, on passe en forme parenthesee.
LARGEUR = 99


def lignes_de(src: str) -> list[str]:
    """Decoupe en lignes AU SENS DE `ast`, c'est-a-dire sur `\\n` SEULEMENT.

    ⚠ NE JAMAIS EMPLOYER `str.splitlines()` ICI, et c'est une panne MESUREE (2026-08-06) :
    `splitlines()` coupe AUSSI sur le form feed `\\x0c`, la tabulation verticale, `\\x1c`,
    `\\u2028`... `ast`, lui, ne compte que les `\\n`. Un seul `\\f` -- il y en a un dans un
    commentaire d'`engine/runner/abilities/blacklegion.py` -- decale donc de +1 TOUS les
    `lineno` suivants, et la re-ecriture remplace la mauvaise plage. Effet mesure :
    **7 fichiers** rendus non parsables, dont un << unterminated string literal >> qui
    n'accusait rien de ce qui etait reellement en cause."""
    return src.split("\n")


class Refus(enum.Enum):
    """Motifs de NON-reecriture. Un ENUM, pas une chaine libre : le compte par motif est une
    PARTITION du refus, et un cas inconnu sort en `AUTRE` plutot que de disparaitre."""

    IMPORT_ETOILE = "from X import * -- la table du baril devient indeterminee"
    DEFINI_DANS_LE_BARIL = "symbole def/class/assigne DANS l'__init__, il n'a pas d'enfant"
    BARIL_A_REGISTRE = "baril dont l'import empresse est FONCTIONNEL (registre)"
    CONFLIT_DE_NOMS = "deux enfants du meme baril exportent ce nom"
    CHAINE_NON_RESOLUE = "re-export d'un re-export dont le maillon casse"
    ORIGINE_HORS_ENGINE = "le baril re-exporte un symbole venu de la stdlib / d'un tiers"
    IMPORT_CONDITIONNEL = "import sous `if`/`try` dans le baril -- l'origine n'est pas garantie"
    SOUS_MODULE = "le nom importe EST un sous-module, pas un symbole"
    INCONNU_DU_BARIL = "symbole absent de la table du baril (dynamique ? perime ?)"
    COMMENTAIRE_INTERCALE = "commentaire a l'interieur de l'import multi-ligne"
    AUTRE = "cas non classe -- a examiner"


@dataclass
class Origine:
    """Ou vit REELLEMENT un symbole re-exporte."""

    module: str                      #: module feuille, ex. `engine.entities.stats`
    nom_amont: str                   #: nom PORTE PAR le module d'origine (avant tout alias)
    profondeur: int = 1              #: 1 = enfant direct ; >1 = re-export d'un re-export


@dataclass
class Baril:
    module: str
    chemin: Path
    exports: dict[str, Origine] = field(default_factory=dict)
    refuses: dict[str, Refus] = field(default_factory=dict)
    definis_ici: set[str] = field(default_factory=set)
    sous_modules: set[str] = field(default_factory=set)
    effets_de_bord: list[str] = field(default_factory=list)
    enregistreurs: list[str] = field(default_factory=list)

    @property
    def registre(self) -> bool:
        return bool(self.effets_de_bord or self.enregistreurs)


@dataclass
class Site:
    """Un import de consommateur vise par la re-ecriture."""

    fichier: Path
    ligne: int
    fin: int
    baril: str
    symboles: list[tuple[str, str | None]]   #: (nom, asname)
    differe: bool                            #: ecrit dans un corps de fonction
    node: ast.ImportFrom


# --------------------------------------------------------------------------------------- outils

def nom_module(p: Path, racine: Path) -> str:
    parts = list(p.relative_to(racine).with_suffix("").parts)
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def cible_absolue(mod: str, node: ast.ImportFrom | ast.Import, racine: Path) -> str | None:
    """Module ABSOLU vise par `node`, `None` si ce n'est pas un `ImportFrom` resoluble.

    ⚠ Pour un `__init__.py`, le module EST son propre paquet : `from .x import Y` y vise
    `<mod>.x`, pas `<parent>.x`. Le discriminant est l'existence du REPERTOIRE, pas le nom."""
    if isinstance(node, ast.Import):
        return None
    if not node.level:
        return node.module or None
    base = mod.split(".")
    pkg = base if (racine / Path(*base)).is_dir() else base[:-1]
    if node.level > 1:
        pkg = pkg[: len(pkg) - (node.level - 1)]
    return ".".join(pkg + ([node.module] if node.module else []))


#: Memoire de `existe_module`. Sans elle, le recenseur de substitutions fait un acces disque
#: par alias importe et depasse les 120 s sur ~1 200 fichiers -- mesure du 2026-08-06.
_CACHE_MODULES: dict[tuple[str, str], bool] = {}
#: Memoire du contenu d'un repertoire, pour la verification de CASSE (voir ci-dessous).
_CACHE_ENTREES: dict[Path, set[str]] = {}


def _entrees(rep: Path) -> set[str]:
    hit = _CACHE_ENTREES.get(rep)
    if hit is None:
        try:
            hit = {e.name for e in rep.iterdir()}
        except OSError:
            hit = set()
        _CACHE_ENTREES[rep] = hit
    return hit


def existe_module(mod: str, racine: Path) -> bool:
    """`mod` designe-t-il un module (fichier ou paquet) sous `racine` ?

    ⚠ LA CASSE EST LE DISCRIMINANT, et `Path.is_file()` NE LA VERIFIE PAS SOUS WINDOWS. Mesure
    du 2026-08-06 : `from engine.runner.operations.triggers import EFFECT_TRIGGERS` importe une
    CONSTANTE, mais `effect_triggers.py` existe a cote -- NTFS repond `True` a
    `EFFECT_TRIGGERS.py`. Consequences en chaine, toutes silencieuses : `_table_modules` lie ce
    nom a un pseudo-module (un lecteur qui l'importe se prend un `ModuleNotFoundError`), et
    `classer_liaisons` classe le couple en forme B -- << point fixe, rien a faire >> -- alors
    qu'il est en forme A ou C. Un symbole en MAJUSCULES homonyme d'un module est exactement le
    cas que nos conventions produisent en masse (`EFFECT_TRIGGERS` / `effect_triggers`)."""
    cle = (str(racine), mod)
    hit = _CACHE_MODULES.get(cle)
    if hit is None:
        bouts = mod.split(".")
        p = racine / Path(*bouts)
        entrees = _entrees(p.parent)
        hit = _CACHE_MODULES[cle] = (
            (p.is_dir() and bouts[-1] in entrees)
            or (p.with_suffix(".py").is_file() and bouts[-1] + ".py" in entrees))
    return hit


def _noms_references(arbre: ast.Module, avec_all: bool = True) -> set[str]:
    """Noms REFERENCES dans le fichier hors des imports eux-memes, plus, si `avec_all`, le
    contenu litteral d'`__all__`.

    ⚠ LES DEUX APPELANTS N'ONT PAS BESOIN DU MEME PERIMETRE, et les confondre a failli annuler
    la tranche. Pour classer un import a EFFET DE BORD PUR, `__all__` compte : un nom qui y
    figure est bien SERVI par le baril. Pour la VIDANGE, il ne compte pas -- sinon tout symbole
    exporte se declare << utilise >> par le seul fait d'etre exporte, et le baril ne peut
    JAMAIS se vider. Mesure : **8** re-exports retirables avec `__all__` compte, contre des
    centaines sans."""
    vus: set[str] = set()
    for n in ast.walk(arbre):
        if isinstance(n, (ast.Import, ast.ImportFrom)):
            continue
        if isinstance(n, ast.Name):
            vus.add(n.id)
        elif isinstance(n, ast.Attribute):
            racine = n
            while isinstance(racine, ast.Attribute):
                racine = racine.value
            if isinstance(racine, ast.Name):
                vus.add(racine.id)
    if avec_all:
        for n in arbre.body:
            cibles = n.targets if isinstance(n, ast.Assign) else ([n.target] if isinstance(
                n, ast.AnnAssign) else [])
            if any(isinstance(t, ast.Name) and t.id == "__all__" for t in cibles):
                val = n.value
                if isinstance(val, (ast.List, ast.Tuple)):
                    vus |= {e.value for e in val.elts
                            if isinstance(e, ast.Constant) and isinstance(e.value, str)}
    return vus


def _est_enregistreur(arbre: ast.Module) -> bool:
    """Le TOP-LEVEL du module mute-t-il un objet du MOTEUR venu d'AILLEURS ?

    Trois formes, toutes mesurables a l'AST :
      * appel top-level d'un nom importe d'`engine`   `register(1009, X)`
      * decorateur dont la racine vient d'`engine`    `@register(...)`
      * ecriture dans un conteneur d'`engine`         `REGISTRY[k] = v`, `TABLE.update(...)`
    Un module qui ne fait qu'ecrire ses PROPRES globales n'est pas enregistreur : le retirer de
    la cascade ne prive personne.

    ⚠ LE FILTRE SUR L'ORIGINE `engine` N'EST PAS COSMETIQUE. Sans lui, `@dataclass` et
    `@lru_cache` -- des decorateurs de la STDLIB, donc bien << une racine importee >> -- font
    classer enregistreur a peu pres tout le moteur : premiere mesure, **17 barils sur 25**
    exclus, dont `engine` lui-meme. Un detecteur qui exclut tout ne protege plus rien, il
    annule juste la tranche."""
    importes: set[str] = set()
    for n in arbre.body:
        if isinstance(n, ast.ImportFrom):
            interne = bool(n.level) or (n.module or "").split(".")[0] == "engine"
            if interne:
                importes |= {a.asname or a.name for a in n.names}
        elif isinstance(n, ast.Import):
            importes |= {(a.asname or a.name.split(".")[0]) for a in n.names
                         if a.name.split(".")[0] == "engine"}

    def _racine(node) -> str | None:
        while isinstance(node, (ast.Attribute, ast.Subscript, ast.Call)):
            node = node.value if not isinstance(node, ast.Call) else node.func
        return node.id if isinstance(node, ast.Name) else None

    for n in arbre.body:
        if isinstance(n, ast.Expr) and isinstance(n.value, ast.Call):
            if _racine(n.value.func) in importes:
                return True
        if isinstance(n, (ast.Assign, ast.AugAssign)):
            cibles = n.targets if isinstance(n, ast.Assign) else [n.target]
            for t in cibles:
                if isinstance(t, (ast.Subscript, ast.Attribute)) and _racine(t) in importes:
                    return True
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            for d in n.decorator_list:
                if _racine(d) in importes:
                    return True
    return False


# --------------------------------------------------------- derivation de la table depuis engine

def derive_barils(racine: Path, paquet: str = "engine") -> dict[str, Baril]:
    """La table `symbole -> module d'origine`, LUE dans les barils. Deux passes : la premiere
    remplit les origines DIRECTES, la seconde resout transitivement les re-exports de
    re-exports (un baril qui re-exporte depuis un autre baril)."""
    racine_pkg = racine / paquet
    barils: dict[str, Baril] = {}
    for init in sorted(racine_pkg.rglob("__init__.py")):
        if "__pycache__" in str(init):
            continue
        mod = nom_module(init, racine)
        src = init.read_text(encoding="utf-8")
        arbre = ast.parse(src)
        b = Baril(module=mod, chemin=init)
        references = _noms_references(arbre)

        #: les imports NON top-level (sous `if TYPE_CHECKING`, `try`) ne fondent pas d'origine :
        #: leur execution n'est pas garantie.
        conditionnels = {id(n) for parent in ast.walk(arbre)
                         if not isinstance(parent, ast.Module)
                         for n in ast.iter_child_nodes(parent)
                         if isinstance(n, (ast.Import, ast.ImportFrom))}

        for n in ast.walk(arbre):
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                b.definis_ici.add(n.name)
        for n in arbre.body:
            cibles = n.targets if isinstance(n, ast.Assign) else ([n.target] if isinstance(
                n, ast.AnnAssign) else [])
            b.definis_ici |= {t.id for t in cibles if isinstance(t, ast.Name)}

        for n in ast.walk(arbre):
            if not isinstance(n, (ast.Import, ast.ImportFrom)):
                continue
            conditionnel = id(n) in conditionnels
            cible = cible_absolue(mod, n, racine)
            if isinstance(n, ast.Import):
                # `import engine.p.x` / `import engine.p.x as y` : effet de bord si le nom lie
                # n'est reference nulle part ailleurs.
                for a in n.names:
                    lie = a.asname or a.name.split(".")[0]
                    if a.name.startswith(paquet) and lie not in references:
                        b.effets_de_bord.append(a.name)
                continue
            for a in n.names:
                if a.name == "*":
                    b.refuses["*"] = Refus.IMPORT_ETOILE
                    continue
                expose = a.asname or a.name
                if cible is None:
                    continue
                plein = "%s.%s" % (cible, a.name)
                if existe_module(plein, racine) and not (racine / Path(*cible.split("."))
                                                         ).is_file():
                    # `from . import loki_custom` : le nom EST un sous-module.
                    b.sous_modules.add(expose)
                    if expose not in references:
                        b.effets_de_bord.append(plein)
                    continue
                if conditionnel:
                    b.refuses[expose] = Refus.IMPORT_CONDITIONNEL
                    continue
                if cible.split(".")[0] != paquet:
                    b.refuses[expose] = Refus.ORIGINE_HORS_ENGINE
                    continue
                if expose in b.exports and b.exports[expose].module != cible:
                    b.refuses[expose] = Refus.CONFLIT_DE_NOMS
                    b.exports.pop(expose, None)
                    continue
                b.exports[expose] = Origine(module=cible, nom_amont=a.name)

        for s in b.definis_ici:
            b.exports.pop(s, None)
            b.refuses.setdefault(s, Refus.DEFINI_DANS_LE_BARIL)
        barils[mod] = b

    # ---- modules ENREGISTREURS : un enfant qui mute un objet d'ailleurs au chargement
    for p in sorted(racine_pkg.rglob("*.py")):
        if "__pycache__" in str(p) or p.name == "__init__.py":
            continue
        try:
            if not _est_enregistreur(ast.parse(p.read_text(encoding="utf-8"))):
                continue
        except SyntaxError:
            continue
        mod = nom_module(p, racine)
        parent = mod.rsplit(".", 1)[0]
        if parent in barils:
            barils[parent].enregistreurs.append(mod)

    # ---- passe 2 : re-export d'un re-export -> resolution transitive vers la FEUILLE
    for b in barils.values():
        for sym, org in list(b.exports.items()):
            vus, cur, prof = {b.module}, org, org.profondeur
            while cur.module in barils and cur.module not in vus:
                vus.add(cur.module)
                amont = barils[cur.module]
                if amont.registre:
                    # on ne court-circuite PAS un registre : la chaine s'arrete ici, et le
                    # symbole reste servi par le baril intermediaire.
                    break
                suivant = amont.exports.get(cur.nom_amont)
                if suivant is None:
                    b.refuses[sym] = (Refus.SOUS_MODULE if cur.nom_amont in amont.sous_modules
                                      else Refus.CHAINE_NON_RESOLUE)
                    b.exports.pop(sym, None)
                    cur = None
                    break
                prof += 1
                cur = Origine(module=suivant.module, nom_amont=suivant.nom_amont,
                              profondeur=prof)
            if cur is not None:
                b.exports[sym] = cur
    return barils


# ------------------------------------------------------------------------- sites consommateurs

def recenser_sites(racine: Path, barils: dict[str, Baril],
                   exclure: set[str]) -> tuple[list[Site], list[tuple[Path, int, str, Refus]]]:
    """Tous les `from <baril> import ...` du perimetre. Rend (sites, refus)."""
    sites: list[Site] = []
    refus: list[tuple[Path, int, str, Refus]] = []
    for p in sorted(racine.rglob("*.py")):
        if "__pycache__" in str(p) or p.resolve() == Path(__file__).resolve():
            continue
        try:
            src = p.read_text(encoding="utf-8")
            arbre = ast.parse(src)
        except (OSError, SyntaxError, UnicodeDecodeError):
            continue
        mod = nom_module(p, racine)
        dans_fonction = {id(n) for f in ast.walk(arbre)
                         if isinstance(f, (ast.FunctionDef, ast.AsyncFunctionDef))
                         for n in ast.walk(f) if isinstance(n, ast.ImportFrom)}
        for n in ast.walk(arbre):
            if not isinstance(n, ast.ImportFrom):
                continue
            cible = cible_absolue(mod, n, racine)
            if cible is None or cible not in barils or cible == mod:
                continue
            b = barils[cible]
            if any(a.name == "*" for a in n.names):
                refus.append((p, n.lineno, "%s.*" % cible, Refus.IMPORT_ETOILE))
                continue
            if cible in exclure:
                for a in n.names:
                    refus.append((p, n.lineno, "%s.%s" % (cible, a.name),
                                  Refus.BARIL_A_REGISTRE))
                continue
            gardables, deplacables = [], []
            for a in n.names:
                if a.name in b.exports:
                    deplacables.append((a.name, a.asname))
                else:
                    motif = b.refuses.get(a.name)
                    if motif is None:
                        #: ⚠ `from engine import move` ne demande PAS un symbole du baril : il
                        #: demande le MODULE `engine.move`. Le site est deja a sa forme la plus
                        #: precise -- il n'y a rien a reecrire, et le compter en
                        #: `INCONNU_DU_BARIL` gonflait le refus de **867 faux** a la premiere
                        #: mesure (887 -> 20). Rien ne peut lui epargner l'`__init__` du
                        #: paquet, que Python execute quoi qu'on ecrive : seule la VIDANGE
                        #: l'allege.
                        sous = "%s.%s" % (cible, a.name)
                        motif = (Refus.SOUS_MODULE
                                 if a.name in b.sous_modules or existe_module(sous, racine)
                                 else Refus.INCONNU_DU_BARIL)
                    refus.append((p, n.lineno, "%s.%s" % (cible, a.name), motif))
                    gardables.append((a.name, a.asname))
            if deplacables:
                sites.append(Site(fichier=p, ligne=n.lineno, fin=n.end_lineno or n.lineno,
                                  baril=cible, symboles=deplacables,
                                  differe=id(n) in dans_fonction, node=n))
                if gardables:
                    # import MIXTE : on garde une ligne residuelle vers le baril.
                    sites[-1].symboles = deplacables
                    sites[-1].node = n
    return sites, refus


# --------------------------------------------------------------------------------- re-ecriture

def _commentaires(segment: str) -> tuple[str | None, bool]:
    """(commentaire de FIN de segment, y a-t-il un commentaire INTERCALE ?).

    Un `# noqa: F401` ou une raison `(#27)` accrochee a un import doit SURVIVRE a la
    re-ecriture ; un commentaire au milieu d'un import parenthese, lui, ne peut pas etre
    reattache mecaniquement -- on refuse le site plutot que de le perdre."""
    trouves: list[tuple[int, str]] = []
    try:
        for tok in tokenize.generate_tokens(io.StringIO(segment).readline):
            if tok.type == tokenize.COMMENT:
                trouves.append((tok.start[0], tok.string))
    except (tokenize.TokenError, IndentationError, SyntaxError):
        return None, True
    if not trouves:
        return None, False
    dernier_ligne = max(l for l, _ in trouves)
    fin = " ".join(s for l, s in trouves if l == dernier_ligne)
    intercale = len(trouves) > sum(1 for l, _ in trouves if l == dernier_ligne)
    return fin, intercale


def _ligne_import(indent: str, module: str, level: int,
                  noms: list[tuple[str, str | None]], suffixe: str = "") -> list[str]:
    pts = "." * level
    membres = ", ".join(n if a is None else "%s as %s" % (n, a) for n, a in noms)
    tete = "%sfrom %s%s import " % (indent, pts, module)
    plat = tete + membres + suffixe
    if len(plat) <= LARGEUR:
        return [plat]
    out = ["%s(" % tete]
    ligne = indent + "    "
    for i, (n, a) in enumerate(noms):
        bout = (n if a is None else "%s as %s" % (n, a)) + ("," if i < len(noms) - 1 else "")
        if len(ligne) + len(bout) + 1 > LARGEUR and ligne.strip():
            out.append(ligne.rstrip())
            ligne = indent + "    "
        ligne += bout + " "
    out.append(ligne.rstrip())
    out.append("%s)%s" % (indent, suffixe))
    return out


def reecrire_fichier(p: Path, sites: list[Site], barils: dict[str, Baril],
                     racine: Path) -> tuple[list[str] | None, list[tuple[int, str, Refus]]]:
    """Rend (lignes reecrites | None si rien a faire, refus supplementaires)."""
    src = p.read_text(encoding="utf-8")
    lignes = lignes_de(src)
    refus: list[tuple[int, str, Refus]] = []
    edits: list[tuple[int, int, list[str]]] = []
    for s in sorted(sites, key=lambda x: -x.ligne):
        seg = "\n".join(lignes[s.ligne - 1:s.fin])
        # de-indenter pour tokenize (un import differe est indente)
        indent = seg[:len(seg) - len(seg.lstrip())]
        fin_com, intercale = _commentaires("\n".join(
            l[len(indent):] if l.startswith(indent) else l.lstrip()
            for l in lignes_de(seg)))
        if intercale:
            refus.append((s.ligne, s.baril, Refus.COMMENTAIRE_INTERCALE))
            continue
        b = barils[s.baril]
        par_module: dict[str, list[tuple[str, str | None]]] = defaultdict(list)
        for nom, asname in s.symboles:
            org = b.exports[nom]
            expose = asname or nom
            par_module[org.module].append(
                (org.nom_amont, None if expose == org.nom_amont else expose))
        restants = [(a.name, a.asname) for a in s.node.names
                    if not any(a.name == n for n, _ in s.symboles)]

        base_mod = s.node.module or ""
        neuf: list[str] = []
        if restants:
            neuf += _ligne_import(indent, base_mod, s.node.level, restants)
        for m in sorted(par_module):
            #: ⚠ L'ORIGINE N'EST PAS TOUJOURS SOUS LE BARIL. Un baril peut re-exporter un
            #: symbole venu d'une AUTRE branche (`runner.operations.triggers` sert ainsi du
            #: `services.damage_prediction`, par une chaine transitive). Le suffixe relatif
            #: n'existe alors pas, et la forme correcte est l'import ABSOLU. Sans ce cas, deux
            #: sites sortaient en `AUTRE` -- un motif fourre-tout qui, laisse tel quel, aurait
            #: fait passer pour << non classe >> ce qui etait simplement non traite.
            if m.startswith(s.baril + "."):
                neuf += _ligne_import(indent, (base_mod + "." if base_mod else "")
                                      + m[len(s.baril) + 1:], s.node.level,
                                      sorted(par_module[m]))
            else:
                neuf += _ligne_import(indent, m, 0, sorted(par_module[m]))
        if fin_com:
            neuf[-1] = neuf[-1] + "  " + fin_com
        edits.append((s.ligne - 1, s.fin, neuf))

    if not edits:
        return None, refus
    out = list(lignes)
    for deb, fin, neuf in sorted(edits, key=lambda e: -e[0]):
        out[deb:fin] = neuf
    return out, refus


# ------------------------------------------------- HISSABLE vs OMBRAGE : le geste n'est pas le meme

class Geste(enum.Enum):
    """Ce qu'il faut FAIRE d'un differe devenu GRATUIT. Les deux gestes ne sont pas
    interchangeables, et les confondre a un cout MESURE (#484 : 23 rouges de sa propre main,
    trouves au re-jeu apres rebase).

    ⚠ << LA CIBLE EST DEJA IMPORTEE >> DESIGNE LE MODULE, PAS CHAQUE NOM. Qu'un module fasse
    deja `from engine.services.damage import a` en tete n'implique pas que `b`, importe
    tardivement depuis le meme module, y soit lie. Supprimer le differe rend alors `b`
    introuvable -- alors que le HISSER est toujours correct."""

    HISSER = "aucun import top-level ne lie deja ce NOM -- hisser la ligne au niveau module"
    OMBRAGE_MEME_SOURCE = ("le nom est DEJA lie en top-level, depuis la MEME source : le "
                           "differe est redondant, la ligne se supprime")
    OMBRAGE_AUTRE_SOURCE = ("le nom est deja lie en top-level depuis une AUTRE source : le "
                            "differe MASQUE volontairement -- ni hisser ni supprimer sans lire")


def qualifier_gestes(racine: Path, paquet: str = "engine"):
    """Pour chaque differe `engine.*` de `engine/**`, dit le GESTE qui le retirerait.

    Ne classe PAS porteur/gratuit -- c'est le role de `probe_485_imports_differes.py`, qui le
    mesure en process frais. Ici on ne repond qu'a : << si ce differe partait, comment ? >>"""
    out = []
    for p in sorted((racine / paquet).rglob("*.py")):
        if "__pycache__" in str(p):
            continue
        try:
            arbre = ast.parse(p.read_text(encoding="utf-8"))
        except (OSError, SyntaxError, UnicodeDecodeError):
            continue
        mod = nom_module(p, racine)
        #: nom expose -> module source, POUR LES SEULS IMPORTS TOP-LEVEL
        tete: dict[str, str] = {}
        for n in arbre.body:
            if isinstance(n, ast.ImportFrom):
                cible = cible_absolue(mod, n, racine) or ""
                for al in n.names:
                    tete[al.asname or al.name] = cible
        for f in ast.walk(arbre):
            if not isinstance(f, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for n in ast.walk(f):
                if not isinstance(n, ast.ImportFrom):
                    continue
                cible = cible_absolue(mod, n, racine)
                if not cible or cible.split(".")[0] != paquet:
                    continue
                for al in n.names:
                    expose = al.asname or al.name
                    if expose not in tete:
                        g = Geste.HISSER
                    elif tete[expose] == cible:
                        g = Geste.OMBRAGE_MEME_SOURCE
                    else:
                        g = Geste.OMBRAGE_AUTRE_SOURCE
                    out.append((mod, cible, expose, n.lineno, g))
    return out


# ------------------------------------------------------------------- sites de SUBSTITUTION (#484)

class Risque(enum.Enum):
    """Ce qu'une re-ecriture fait a un `monkeypatch` / `mock.patch` deja pose.

    ⚠ CE N'EST PAS LE CALCUL QUI EST EN JEU, C'EST LA LIAISON DU NOM. Mesure #484 (PR #741) :
    hisser 624 differes a rendu **0 divergence sur 197 017 attributs** -- et **28 fichiers de
    tests rouges**. Une substitution posee sur le module SOURCE mord tant que le nom est resolu
    A L'APPEL (import differe) et cesse de mordre des qu'il est lie AU CHARGEMENT. Les tests
    n'ont pas mesure FAUX : ils ont CESSE DE MESURER, ce qui ne rougit pas."""

    PERD_LA_MORSURE = ("le patch vise le BARIL et un consommateur y resout TARDIVEMENT : il "
                       "resoudra l'ENFANT -- le stub ne mord plus, EN SILENCE")
    GAGNE_LA_MORSURE = ("le patch vise l'ENFANT ; un consommateur differe lisait la COPIE du "
                        "baril, il lira desormais l'enfant -- le stub se met a mordre")
    SANS_CONSOMMATEUR_DIFFERE = ("le patch vise le baril mais AUCUN consommateur n'y resout "
                                 "tardivement : la re-ecriture ne peut pas lui retirer sa "
                                 "morsure (elle passe par un acces attributaire, intouche)")
    COUVERT_PAR_DOUBLE_PATCH = ("le MEME fichier patche AUSSI le module d'ORIGINE, avec le "
                                "meme nom : la morsure survit par ce second bout")


_APPELS_SUBSTITUTION = {
    ("monkeypatch", "setattr"), ("monkeypatch", "delattr"), ("mock", "patch"),
    ("patch", "object"), ("mock", "patch.object"),
}


def _nom_pointe(node) -> str | None:
    bouts: list[str] = []
    while isinstance(node, ast.Attribute):
        bouts.append(node.attr)
        node = node.value
    if not isinstance(node, ast.Name):
        return None
    bouts.append(node.id)
    return ".".join(reversed(bouts))


def _table_modules(arbre: ast.Module, mod: str, racine: Path) -> dict[str, str]:
    """Noms LOCAUX qui designent un module, -> nom de module absolu."""
    t: dict[str, str] = {}
    for n in ast.walk(arbre):
        if isinstance(n, ast.Import):
            for a in n.names:
                t[a.asname or a.name.split(".")[0]] = a.name if a.asname else \
                    a.name.split(".")[0]
                if a.asname is None and "." in a.name:
                    t[a.name] = a.name
        elif isinstance(n, ast.ImportFrom):
            cible = cible_absolue(mod, n, racine)
            if not cible:
                continue
            for a in n.names:
                plein = "%s.%s" % (cible, a.name)
                if existe_module(plein, racine):
                    t[a.asname or a.name] = plein
    return t


#: Les noeuds qui OUVRENT une portee de noms Python. `ClassDef` en fait partie, mais sa portee
#: n'est PAS visible des fonctions imbriquees -- `_ResolveurDeModules` la saute, ce qui est la
#: regle du langage, pas une approximation.
_OUVRE_PORTEE = (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef)


def _noeuds_de_portee(portee):
    """Les noeuds qui appartiennent au CODE de cette portee -- sans descendre dans les portees
    imbriquees, mais en rendant le noeud qui les ouvre (un `def f` LIE le nom `f` ici)."""
    corps = [portee.body] if isinstance(portee, ast.Lambda) else list(getattr(portee, "body", []))
    pile = list(corps)
    while pile:
        n = pile.pop()
        yield n
        if isinstance(n, _OUVRE_PORTEE):
            continue
        pile.extend(ast.iter_child_nodes(n))


def _hors_corps(ouvreur):
    """Les sous-noeuds d'un ouvreur de portee EVALUES dans la portee ENGLOBANTE."""
    args = getattr(ouvreur, "args", None)
    if isinstance(args, ast.arguments):
        for d in list(args.defaults) + [x for x in args.kw_defaults if x is not None]:
            yield d
        for a in (list(args.posonlyargs) + list(args.args) + list(args.kwonlyargs)
                  + [args.vararg, args.kwarg]):
            if a is not None and a.annotation is not None:
                yield a.annotation
    for d in getattr(ouvreur, "decorator_list", ()):
        yield d
    if getattr(ouvreur, "returns", None) is not None:
        yield ouvreur.returns
    for b in list(getattr(ouvreur, "bases", ())):
        yield b
    for k in getattr(ouvreur, "keywords", ()):
        yield k.value


#: Les DEUX seules formes d'expression par lesquelles un nom peut recevoir un module :
#: une re-liaison (`M = X`, `M = pkg.sub`) ou un choix entre de telles formes. Tout le reste
#: (appel, litteral, conteneur, indexation, operateur, comprehension, f-string...) designe
#: assurement autre chose -- c'est ce qui autorise a MASQUER (cf. `_liaisons_de_portee`).
_FORMES_DE_RELIAISON = (ast.Name, ast.Attribute)
#: Les seuls APPELS qui rendent un module. Sans cette exception, un
#: `M = importlib.import_module("engine.x")` masquerait une liaison pourtant reelle.
_APPELS_QUI_RENDENT_UN_MODULE = ("import_module", "__import__", "reload")


def _peut_etre_un_module(valeur) -> bool:
    """`True` si cette expression PEUT designer un module -- conservateur par construction."""
    if isinstance(valeur, _FORMES_DE_RELIAISON):
        return True
    if isinstance(valeur, ast.IfExp):
        return _peut_etre_un_module(valeur.body) or _peut_etre_un_module(valeur.orelse)
    if isinstance(valeur, ast.BoolOp):
        return any(_peut_etre_un_module(v) for v in valeur.values)
    if isinstance(valeur, ast.Call):
        f = valeur.func
        nom = f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", "")
        return nom in _APPELS_QUI_RENDENT_UN_MODULE
    return False


def _liaisons_de_portee(portee, mod: str, racine: Path) -> dict[str, str | None]:
    """`{nom: module absolu}` pour ce que cette portee lie, `None` quand le nom est CONNU pour
    designer autre chose qu'un module.

    ⚠ TRI-ETAT, ET LA TROISIEME VALEUR EST L'ABSENCE (#485-r2). Trois classes, pas deux :

      * **module**            -- `import x.y as M`, `from x import y` quand `x.y` EST un module ;
      * **connu NON-module**  -- `from x import OBJET as M`, `def M`, `class M`, `except E as M`,
        et une AFFECTATION `M = <expression qui ne peut PAS designer un module>` (cf. plus bas).
        La valeur est `None`, et elle est PLEINE : c'est elle qui MASQUE une liaison de module
        d'une portee englobante ;
      * **INCONNU**           -- un parametre, une cible de boucle, une affectation dont la
        valeur POURRAIT etre un module. Il n'entre PAS dans la table : le nom continue de se
        resoudre dans la portee englobante.

    ⚠ L'AFFECTATION N'EST PAS UN PARAMETRE, ET LES CONFONDRE FABRIQUE UN FAUX POSITIF (#935).
    L'argument qui rend l'inconnu transparent (ci-dessous) porte sur les PARAMETRES : l'appelant y
    passe reellement le module homonyme, donc l'acces est reel. Une AFFECTATION dont on LIT la
    valeur dans le fichier meme n'a pas cette propriete -- `U = _live_units(rpc, rid)` lie le
    resultat d'un APPEL, jamais un module, et le langage est categorique. Mesure du 2026-08-11 :
    `probe_927_fury_of_the_ancients.py` porte `import engine.entities.selectors.units as U`
    ligne 238 (dans UNE fonction) et `U = _live_units(...)` ligne 376 (dans une AUTRE) ; le
    dernier recours plat attribuait les `U.items()` / `U.values()` de la seconde a la liaison de
    module de la premiere, et `probe_485r1r1` accusait `engine.entities.selectors.units.items` --
    3 acces, rouge de `master`, FAUX, meme forme exacte que le faux positif `F` repare par #485-r2.
    Le critere retenu est CONSERVATEUR : seules les valeurs qui ne peuvent PAS designer un module
    masquent (appel, litteral, conteneur, indexation, operateur, comprehension...). Un
    `M = <Name>` ou `M = <Attribute>` -- les deux seules formes par lesquelles un module se
    re-lie -- reste INCONNU, donc transparent.

    Pourquoi l'inconnu est TRANSPARENT, et c'est une MESURE, pas un principe : le rendre opaque
    (`None`) retirait 8 acces VRAIS du recensement (2026-08-10) -- tous du meme patron, un module
    importe au niveau fichier puis passe en PARAMETRE HOMONYME
    (`from engine.playbook import adjacency as adj` puis `def _non_regression(units, sc, adj)`,
    idem `EF` dans `probe_124_line_elevation_decision` et `ar` dans
    `probe_433_r4_r2_r1_r1_dynamic_target_gate`). L'appelant y passe bien le module ; l'acces est
    reel. Le tri-etat ne retranche donc QUE le cas ou l'on SAIT que ce n'est pas un module.

    CE QUE LA CLASSE << connu NON-module >> REPARE. `_table_modules` ne retient que les liaisons
    de MODULE : un nom rebinde a un OBJET n'y laisse aucune trace, donc une liaison de module
    d'une autre portee lui survit. Mesure du 2026-08-10 sur
    `tests/engine/runner/test_120bis_spawn_tile_offline.py` : `import engine.utilities.
    sworn_protector as F` (ligne 108, dans une fonction) etait attribue au `F` des lignes 182-208,
    ou `from engine.utilities.sworn_protector import SWORN_PROTECTOR_AVOID_ADJACENT_ENEMIES as F`
    lie une FEUILLE. `probe_485r1r1` accusait `engine.utilities.sworn_protector.evaluate` --
    5 acces, un rouge de `master`, FAUX.

    `global` / `nonlocal` retirent la liaison locale : le nom se resout alors dans une portee
    englobante, ce que la remontee de `ResolveurDeModules` fait deja.
    """
    t: dict[str, str | None] = {}
    externes: set[str] = set()
    for n in _noeuds_de_portee(portee):
        if isinstance(n, (ast.Global, ast.Nonlocal)):
            externes.update(n.names)
        elif isinstance(n, ast.Import):
            for a in n.names:
                t[a.asname or a.name.split(".")[0]] = a.name if a.asname else a.name.split(".")[0]
                if a.asname is None and "." in a.name:
                    t[a.name] = a.name
        elif isinstance(n, ast.ImportFrom):
            cible = cible_absolue(mod, n, racine)
            for a in n.names:
                nom = a.asname or a.name
                if cible and existe_module("%s.%s" % (cible, a.name), racine):
                    t[nom] = "%s.%s" % (cible, a.name)
                else:
                    t[nom] = None            # un OBJET, pas un module -- il MASQUE
        elif isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            t[n.name] = None
        elif isinstance(n, ast.ExceptHandler) and n.name:
            t[n.name] = None
        elif isinstance(n, (ast.Assign, ast.AnnAssign)):
            cibles = n.targets if isinstance(n, ast.Assign) else [n.target]
            if n.value is not None and not _peut_etre_un_module(n.value):
                for c in cibles:
                    if isinstance(c, ast.Name):
                        t.setdefault(c.id, None)     # `setdefault` : un `import as` de la MEME
                        #                              portee prime (il est LU, pas devine).
    for nom in externes:
        t.pop(nom, None)
    return t


class ResolveurDeModules:
    """Resout `<nom>.<attr>` DANS SA PORTEE -- foyer unique de cette question (#485-r2).

    `_table_modules` reste ce qu'il est (une table PLATE du fichier) pour ses appelants
    historiques ; ce resolveur est ce qu'il faut des qu'on juge un SITE, parce qu'un site vit
    dans une portee et que Python y resout les noms par portee. Ecrit ICI et pas dans le probe :
    deux implementations jumelles d'un meme predicat divergent (lecon #332), et c'est ce fichier
    qui porte deja `_table_modules`, `cible_absolue` et `existe_module`.
    """

    def __init__(self, arbre: ast.Module, mod: str, racine: Path) -> None:
        self._tables: dict = {}
        self._portee_de: dict = {}
        self._parent_portee: dict = {}
        #: DERNIER RECOURS -- la table PLATE du fichier. Elle n'est consultee que si AUCUNE portee
        #: de la chaine ne dit quoi que ce soit du nom, c'est-a-dire dans le seul cas que le
        #: langage ne tranche pas : un nom recu en PARAMETRE. Mesure du 2026-08-10 : sans ce
        #: recours, 7 acces VRAIS disparaissaient du recensement -- un module importe dans une
        #: fonction puis passe a une AUTRE fonction sous le meme nom (`EF` dans
        #: `probe_124_line_elevation_decision`, `ar` dans
        #: `probe_433_r4_r2_r1_r1_dynamic_target_gate`). Le recours ne peut pas ressusciter le
        #: faux positif repare : une liaison CONNUE non-module masque AVANT lui.
        self._plat = _table_modules(arbre, mod, racine)
        self._indexer(arbre, mod, racine, chaine=[])

    def _indexer(self, portee, mod, racine, chaine) -> None:
        self._tables[id(portee)] = _liaisons_de_portee(portee, mod, racine)
        self._parent_portee[id(portee)] = list(chaine)
        for n in _noeuds_de_portee(portee):
            self._portee_de[id(n)] = portee
            if not isinstance(n, _OUVRE_PORTEE):
                continue
            # Decorateurs, valeurs par defaut, annotations et bases sont EVALUES dans la portee
            # ENGLOBANTE, pas dans celle qu'ouvre ce noeud. Les y rattacher est la regle du
            # langage -- et sans cela un `def f(x=M.y)` n'aurait aucune portee, donc serait
            # silencieusement ecarte du recensement.
            for depart in _hors_corps(n):
                for sous in ast.walk(depart):
                    self._portee_de.setdefault(id(sous), portee)
            self._indexer(n, mod, racine, chaine + [portee])

    def resoudre(self, nom: str, noeud) -> str | None:
        """Le module absolu que `nom` designe A CET ENDROIT, ou `None`.

        Remontee de la portee du site vers le module. Une `ClassDef` ENGLOBANTE est sautee : ses
        noms ne sont pas visibles des fonctions qu'elle contient (regle du langage)."""
        portee = self._portee_de.get(id(noeud))
        if portee is None:
            return None
        chaine = self._parent_portee.get(id(portee), [])
        for i, p in enumerate([portee] + list(reversed(chaine))):
            if i and isinstance(p, ast.ClassDef):
                continue
            table = self._tables.get(id(p), {})
            if nom in table:
                return table[nom]
        return self._plat.get(nom)


def collecter_substitutions(racine: Path) -> dict[Path, list[tuple[int, str, str]]]:
    """FOYER UNIQUE de la lecture des substitutions : fichier -> [(ligne, module vise, attribut)].

    Formes lues : `monkeypatch.setattr(mod, "n", v)`, `monkeypatch.setattr("a.b.n", v)`,
    `mock.patch("a.b.n")`, `patch.object(mod, "n")`, `setattr(mod, "n", v)`, `mod.n = v`.

    ⚠ DEUX AXES LE PARTAGENT, ET C'EST DELIBERE : `recenser_substitutions` (axe BARIL -- ce que
    la RE-ECRITURE fait a un patch) et `recenser_morsure` (axe HISSAGE -- ce que le HISSAGE lui
    fait). Deux implementations jumelles du meme predicat divergeraient, et c'est exactement
    ainsi que le volet LIVE du gisement #484 est passe inapercu : un recenseur rend zero sur ce
    qu'il ne visite pas. La portee ici est TOUT `.py` de la racine -- tests offline, tests
    `_live.py` et probes compris."""
    out: dict[Path, list[tuple[int, str, str]]] = {}
    for p in sorted(racine.rglob("*.py")):
        if "__pycache__" in str(p) or p.resolve() == Path(__file__).resolve():
            continue
        try:
            arbre = ast.parse(p.read_text(encoding="utf-8"))
        except (OSError, SyntaxError, UnicodeDecodeError):
            continue
        mod = nom_module(p, racine)
        table = _table_modules(arbre, mod, racine)

        def _resoudre_cible(expr, _table=table) -> str | None:
            pointe = _nom_pointe(expr)
            if pointe is None:
                return None
            bouts = pointe.split(".")
            for i in range(len(bouts), 0, -1):
                prefixe = ".".join(bouts[:i])
                if prefixe in _table:
                    return ".".join([_table[prefixe]] + bouts[i:])
            return pointe

        vus: list[tuple[int, str, str]] = []
        for n in ast.walk(arbre):
            if isinstance(n, ast.Call):
                f = _nom_pointe(n.func) or ""
                bouts = f.split(".")
                cle = (bouts[-2] if len(bouts) > 1 else "", bouts[-1])
                if cle in _APPELS_SUBSTITUTION or f == "setattr":
                    args = n.args
                    if len(args) >= 2 and isinstance(args[1], ast.Constant) and isinstance(
                            args[1].value, str):
                        cible = _resoudre_cible(args[0])
                        if cible:
                            vus.append((n.lineno, cible, args[1].value))
                    elif args and isinstance(args[0], ast.Constant) and isinstance(
                            args[0].value, str) and "." in args[0].value:
                        chemin = args[0].value
                        vus.append((n.lineno, chemin.rsplit(".", 1)[0],
                                    chemin.rsplit(".", 1)[1]))
            elif isinstance(n, ast.Assign):
                for t in n.targets:
                    if isinstance(t, ast.Attribute):
                        cible = _resoudre_cible(t.value)
                        if cible and cible.split(".")[0] == "engine":
                            vus.append((n.lineno, cible, t.attr))
        if vus:
            out[p] = vus
    return out


def recenser_substitutions(racine: Path, barils: dict[str, Baril], exclure: set[str],
                           sites_reecrits: list[Site]):
    """Tout site qui SUBSTITUE un attribut de module, classe par ce que la re-ecriture lui fait.

    ⚠ LA VOIE DE CONSOMMATION DISCRIMINE, ET NE PAS LA LIRE SURESTIME. Un patch sur le baril
    ne perd sa morsure que s'il existe un consommateur qui resout le nom TARDIVEMENT (import
    dans un corps de fonction). Si tous les consommateurs le lient au chargement, le patch ne
    mordait deja pas par cette voie -- il mord par un acces attributaire, que la re-ecriture ne
    touche pas. Premiere mesure sans ce cran : 27 `PERD_LA_MORSURE`, dont une part etait du
    faux positif."""
    tardifs: set[tuple[str, str]] = {(s.baril, nom) for s in sites_reecrits if s.differe
                                     for nom, _ in s.symboles}
    #: (baril, symbole expose)       -> (module d'origine, nom AMONT) : patch AVANT re-ecriture.
    #: Le nom amont, pas le nom expose : un baril peut re-exporter sous un ALIAS, et c'est le
    #: nom amont qui existera cote enfant.
    origines: dict[tuple[str, str], tuple[str, str]] = {}
    #: (module d'origine, nom amont) -> baril qui le re-exporte  : patch APRES la re-ecriture
    enfants: dict[tuple[str, str], str] = {}
    for nom, b in barils.items():
        if nom in exclure:
            continue
        for sym, org in b.exports.items():
            origines[(nom, sym)] = (org.module, org.nom_amont)
            enfants[(org.module, org.nom_amont)] = nom
    sites = []
    for p, vus in collecter_substitutions(racine).items():
        #: ⚠ CEINTURE ET BRETELLES : un fichier peut patcher LES DEUX bouts -- le baril ET le
        #: module d'origine -- parce que son auteur ne savait pas lequel mordrait. Mesure
        #: (`test_389r2_kill_unit_remove_effects_offline.py`) : `MD.unit_death_triggers` ET
        #: `T.unit_death_triggers`. La re-ecriture retire la morsure du premier bout, le second
        #: continue de mordre, et le test MESURE toujours. Le compter en `PERD_LA_MORSURE`
        #: enverrait reparer ce qui n'est pas casse -- et surtout, ferait passer pour du risque
        #: silencieux ce qui n'en est pas.
        poses = {(m, a) for _, m, a in vus}
        for ligne, cible_mod, attr in vus:
            if (cible_mod, attr) in origines:
                org, amont = origines[(cible_mod, attr)]
                if (org, amont) in poses:
                    r = Risque.COUVERT_PAR_DOUBLE_PATCH
                elif (cible_mod, attr) in tardifs:
                    r = Risque.PERD_LA_MORSURE
                else:
                    r = Risque.SANS_CONSOMMATEUR_DIFFERE
                sites.append((p, ligne, cible_mod, attr, r, "%s.%s" % (org, amont)))
            elif (cible_mod, attr) in enfants:
                sites.append((p, ligne, cible_mod, attr, Risque.GAGNE_LA_MORSURE,
                              enfants[(cible_mod, attr)]))
    return sites


# ------------------------------------------- MORSURE : ce que le HISSAGE fait a une substitution

class Forme(enum.Enum):
    """Les TROIS formes d'import, et ce qu'elles font a un `monkeypatch` pose sur la source.

    Mesure (2026-08-06, banc `probe_485r1r1_formes_dimport.py`), meme symbole, meme patch :

        A  `from X import foo` au NIVEAU MODULE   avant=VRAI  apres=VRAI     <- NE MORD PAS
        B  `import X` / `from pkg import X`       avant=VRAI  apres=PATCHE   <- mord
        C  `from X import foo` DANS la fonction   avant=VRAI  apres=PATCHE   <- mord

    ⚠ C MORD PAR ACCIDENT. L'instruction differee est RE-EXECUTEE a chaque appel, donc elle
    relit l'attribut du module -- le test en profite sans l'avoir demande. HISSER fait passer
    de C a A, et A est la seule des trois qui ne morde pas : c'est la cause EXACTE des
    28 fichiers rouges de #484 et des 12 rouges de la famille #429-r1, pas une maladresse
    d'ecriture des tests.

    ⚠ B EST LE SEUL POINT FIXE. Il ne differe rien (le nom est lie au chargement) et il mord
    (l'attribut est relu a l'appel). Et il ne coute RIEN en cascade : mesure sur ce depot,
    `from pkg.sub.mod import nom`, `from pkg.sub import mod` et `import pkg.sub.mod` chargent
    les MEMES 272 modules `engine.*` -- ecart 0. B ne rouvre donc aucun cycle : il ne resout
    pas non plus les cycles, un porteur reste un porteur quelle que soit sa forme."""

    A = "from X import Y au niveau module -- nom GELE au chargement : le patch NE MORD PAS"
    B = "import de MODULE -- l'attribut est relu a l'appel : le patch MORD, quel que soit l'ordre"
    C = "from X import Y differe -- re-execute a chaque appel : le patch mord, PAR ACCIDENT"


class Morsure(enum.Enum):
    """Ce que le HISSAGE d'un differe fait a une substitution deja posee.

    ⚠ L'ORDRE DE PRIORITE EST LE CRAN, ET IL ETAIT INVERSE. `DEJA_INERTE` etait teste EN
    PREMIER et faisait `continue` : des qu'UNE liaison de forme A existait quelque part --
    fut-ce dans un baril que personne n'appelle -- le couple sortait << deja inerte >> et le
    site de forme C qu'on s'appretait a HISSER n'etait plus examine. Mesure du 2026-08-06 :
    `phase_end_triggers` avait une liaison A dans le baril `runner/operations/triggers/
    __init__.py` ET un differe C dans `runner/runner.py`, son consommateur REEL. Le patch de
    `test_389_ramming_speed_combat_offline::test_runner_apply_closes_the_phase` mordait par la
    voie C ; le hissage la lui a retiree, et le recenseur qui devait le voir l'avait classe
    << rien a faire >>. Une liaison A dans un module TIERS ne dit RIEN du module qu'on hisse."""

    HISSAGE_DESARMERAIT = ("le differe est GRATUIT (donc a hisser) et son symbole est "
                           "SUBSTITUE : hisser en forme A rendrait le patch INERTE -- hisser "
                           "en forme B (import de module) le garde mordant")
    DIFFERE_MORDANT = ("le differe est PORTEUR : il reste, donc le patch mord encore. Fragile "
                       "quand meme -- le jour ou le cycle disparait, hisser le desarme")
    DEJA_INERTE = ("une liaison de forme A existe DEJA dans `engine/**` et AUCUN site hissable "
                   "ne subsiste : pour ce module le patch ne mord pas, et selon l'ordre de "
                   "chargement il capture le STUB")


def classer_liaisons(racine: Path, paquet: str = "engine"):
    """(module vise, nom) -> {Forme: [porteur:ligne]} pour tout `from` ecrit dans `<paquet>/**`.

    Le discriminant de B n'est PAS la syntaxe (`import x` vs `from p import x`) mais le fait
    que le nom importe SOIT un module : `from engine.runner import components` lie un MODULE,
    donc tout acces y est attributaire -- c'est une forme B, et c'est ce que sont les
    900+ refus `SOUS_MODULE` de la re-ecriture. Ils ne sont pas un obstacle a contourner : ils
    sont deja la bonne reponse, et les reecrire vers A serait une regression."""
    out: dict[tuple[str, str], dict[Forme, list[str]]] = defaultdict(lambda: defaultdict(list))
    for p in sorted((racine / paquet).rglob("*.py")):
        if "__pycache__" in str(p):
            continue
        mod = nom_module(p, racine)
        try:
            arbre = ast.parse(p.read_text(encoding="utf-8"))
        except (OSError, SyntaxError, UnicodeDecodeError):
            continue
        differes = {id(n) for f in ast.walk(arbre)
                    if isinstance(f, (ast.FunctionDef, ast.AsyncFunctionDef))
                    for n in ast.walk(f) if isinstance(n, ast.ImportFrom)}
        for n in ast.walk(arbre):
            if not isinstance(n, ast.ImportFrom):
                continue
            cible = cible_absolue(mod, n, racine)
            if not cible or cible.split(".")[0] != paquet:
                continue
            for al in n.names:
                if al.name == "*":
                    continue
                if existe_module("%s.%s" % (cible, al.name), racine):
                    forme = Forme.B
                elif id(n) in differes:
                    forme = Forme.C
                else:
                    forme = Forme.A
                out[(cible, al.name)][forme].append("%s:%d" % (mod, n.lineno))
    return out


def recenser_morsure(racine: Path, gratuits: set[tuple[str, str]] | None,
                     paquet: str = "engine"):
    """Croise les SUBSTITUTIONS du depot avec les liaisons d'`engine/**`. Rend (lignes, bilan).

    `gratuits` = les couples (module porteur, module cible) que `probe_485_imports_differes.py`
    a mesures GRATUITS, donc destines au hissage. `None` = non fourni : on ne PRETEND alors
    rien sur le hissage (tri-etat), on ne rabat pas sur l'ensemble vide."""
    subs: dict[tuple[str, str], list[str]] = defaultdict(list)
    for p, vus in collecter_substitutions(racine).items():
        for ligne, m, a in vus:
            if m.split(".")[0] == paquet:
                subs[(m, a)].append("%s:%d" % (p.name, ligne))
    liaisons = classer_liaisons(racine, paquet)
    lignes, bilan = [], defaultdict(int)
    for (cible, nom), sites in sorted(subs.items()):
        formes = liaisons.get((cible, nom))
        if not formes:
            bilan["sans liaison `from` dans %s/** (acces attributaire seul)" % paquet] += 1
            continue
        porteurs_c = list(formes.get(Forme.C, []))
        #: ⚠ LE SITE HISSABLE SE TESTE AVANT `DEJA_INERTE`, ET L'INVERSE ETAIT LE TROU
        #: (cf. `Morsure`) : une liaison A ailleurs n'ote rien a la morsure que le site C
        #: procure, et c'est CE site que le hissage va reecrire.
        vise = [s for s in porteurs_c
                if gratuits is not None and (s.split(":")[0], cible) in gratuits]
        if vise:
            lignes.append((Morsure.HISSAGE_DESARMERAIT, cible, nom, formes, sites))
            bilan[Morsure.HISSAGE_DESARMERAIT.name] += 1
            continue
        if formes.get(Forme.A):
            lignes.append((Morsure.DEJA_INERTE, cible, nom, formes, sites))
            bilan[Morsure.DEJA_INERTE.name] += 1
            continue
        if not porteurs_c:
            bilan["forme B seule -- point fixe, rien a faire"] += 1
        elif gratuits is None:
            bilan["differe, classement du hissage NON MESURE (base absente)"] += 1
        else:
            lignes.append((Morsure.DIFFERE_MORDANT, cible, nom, formes, sites))
            bilan[Morsure.DIFFERE_MORDANT.name] += 1
    return lignes, bilan


def _gratuits_attestes(racine: Path) -> set[tuple[str, str]] | None:
    """Les couples (module, cible) declares GRATUITS par la base versionnee de `probe_485`.

    ⚠ TRI-ETAT : base absente ou illisible -> `None`, jamais un ensemble vide. Un zero fabrique
    ferait conclure << aucun hissage ne desarme rien >> sur une mesure qui n'a pas eu lieu."""
    base = racine.parent / "ratchets-485-differes-attestes.json"
    try:
        import json
        d = json.loads(base.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return {(mod, cible) for mod, cibles in d.items() for cible in cibles}


def _gratuits_frais(racine: Path) -> set[tuple[str, str]] | None:
    """Les couples GRATUITS **mesures sur l'arbre courant**, par `probe_485_imports_differes`.

    ⚠ LA BASE ATTESTEE EST EN RETARD D'UNE VIDANGE, ET C'EST LA SECONDE CAUSE DU RATE. Un
    differe est GRATUIT ou PORTEUR *par rapport a un arbre* : vider les barils allege la
    cascade et RETOURNE le verdict. Mesure du 2026-08-06 : sur `master`, charger
    `runner.operations.triggers.dispatch.phase` tirait `runner.runner` -- donc PORTEUR, donc
    absent de la base ; apres vidange le meme differe est devenu GRATUIT, a ete hisse, et a
    desarme un patch. `morsure` jouee avec la base ATTESTEE ne pouvait pas le voir : elle
    decrivait l'arbre d'AVANT. On mesure donc a FRAIS par defaut, et on ne se replie sur la
    base attestee qu'en le DISANT."""
    if racine != ICI:
        return None            # `probe_485` lit SON PROPRE arbre : il ne mesurerait pas celui-la
    try:
        import probe_485_imports_differes as P485
    except ImportError:
        return None
    differes = P485.recenser()
    classe = P485.classer(differes) if differes else None
    if classe is None:
        return None
    _porteurs, gratuits = classe
    return {(mod, cible) for mod, cible, _l, _r in gratuits}


# ------------------------------------------------------------------------------------- vidange

def _cibles_chargeuses_de_registre(barils: dict[str, Baril]) -> set[str]:
    """Modules dont l'import CHARGE un registre -- les barils a registre EUX-MEMES et tous
    leurs ancetres qui sont des barils.

    ⚠ LA PROPRIETE << A REGISTRE >> SE PROPAGE VERS LE HAUT, et l'ignorer produit exactement
    la panne qu'on croyait avoir ecartee. Mesure (2026-08-06) : `engine.runner.abilities.loki`
    est bien exclu du vidage -- mais vider son PARENT `engine.runner.abilities` retire le
    `from .loki import (...)` qui etait le SEUL chemin chargeant `loki/__init__.py`, donc
    `facade`. Resultat lu par l'etage [3] du probe :

        TRIGGERED_ABILITY_DELAYED_BEHAVIOURS  {1180: facade._run_switch} -> {}

    Un registre vide, sans erreur, sans que rien ne rougisse -- la panne meme que l'exclusion
    devait empecher. Exclure le baril a registre ne suffit donc pas : il faut PROTEGER l'import
    qui le charge, partout ou il se trouve."""
    protegees: set[str] = set()
    for nom, b in barils.items():
        if not b.registre:
            continue
        protegees.add(nom)
        bouts = nom.split(".")
        for i in range(1, len(bouts)):
            prefixe = ".".join(bouts[:i])
            if prefixe in barils:
                protegees.add(prefixe)
    return protegees


def _attributs_lus(arbre: ast.Module, local: str) -> tuple[set[str], bool]:
    """Attributs demandes a `local`, et si le nom ECHAPPE (utilise autrement qu'en `local.x`).

    Un nom qui echappe -- passe en argument, `getattr(M, ...)`, range dans une structure -- peut
    etre interroge par une voie qu'aucune analyse statique ne suit. On rend alors `True`, et
    l'appelant reclame TOUT le baril : le repli conservateur est le comportement DEJA en place
    pour `import X as E` (l'autre forme de liaison de module)."""
    bases = {id(n.value) for n in ast.walk(arbre)
             if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name)
             and n.value.id == local}
    attrs = {n.attr for n in ast.walk(arbre)
             if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name)
             and n.value.id == local}
    echappe = any(isinstance(n, ast.Name) and n.id == local and id(n) not in bases
                  and isinstance(n.ctx, ast.Load) for n in ast.walk(arbre))
    return attrs, echappe


def vider_barils(racine: Path, barils: dict[str, Baril], exclure: set[str],
                 appliquer: bool) -> list[tuple[str, int, int]]:
    """Retire d'un baril les re-exports que PLUS AUCUN fichier du perimetre ne reclame ET que
    le baril lui-meme n'utilise pas. Rend [(baril, retires, gardes)].

    ⚠ C'est ce pas -- pas la re-ecriture -- qui allege la cascade. Reecrire seul ne change RIEN
    au graphe : Python execute l'`__init__` du paquet parent quoi qu'on ecrive."""
    reclames: dict[str, set[str]] = defaultdict(set)
    for p in sorted(racine.rglob("*.py")):
        if "__pycache__" in str(p) or p.resolve() == Path(__file__).resolve():
            continue
        try:
            arbre = ast.parse(p.read_text(encoding="utf-8"))
        except (OSError, SyntaxError, UnicodeDecodeError):
            continue
        mod = nom_module(p, racine)
        #: LA TABLE DES LIAISONS DE MODULE, LUE UNE FOIS ET AVANT la boucle -- c'est elle qui
        #: rend le repli en bloc EVITABLE quand une forme PRECISE existe (cf. plus bas).
        table = _table_modules(arbre, mod, racine)
        for n in ast.walk(arbre):
            if isinstance(n, ast.ImportFrom):
                cible = cible_absolue(mod, n, racine)
                if cible in barils:
                    #: ⚠ UN `import *` RECLAME TOUT LE BARIL, et l'oublier ne rate pas un cas
                    #: rare : c'est un vidage qui compile parfaitement et casse a l'IMPORT.
                    #: Mesure -- `engine/dsl/nodes.py` fait `from ...entities.selectors
                    #: import *` ; vider les 100 re-exports de ce baril a fait tomber
                    #: `dsl.Damageable`, donc 6 modules non chargeables, dont tout
                    #: `engine.playbook`. Le refus cote CONSOMMATEUR (on ne reecrit pas une
                    #: etoile) ne suffisait pas : il faut aussi la compter cote VIDANGE.
                    if any(a.name == "*" for a in n.names):
                        reclames[cible] |= set(barils[cible].exports)
                    reclames[cible] |= {a.name for a in n.names}
            elif isinstance(n, ast.Import):
                # `import engine.entities as E` puis `E.StatType` : l'acces est ATTRIBUTAIRE,
                # invisible d'un recensement d'`ImportFrom`. On reclame alors TOUT le baril
                # plutot que de vider sous les pieds d'un acces qu'on ne sait pas suivre.
                #
                # ⚠ SAUF QUAND LA FORME `as` EST DEJA SUIVIE PRECISEMENT, et ce repli-la
                # COUTAIT LE GISEMENT ENTIER D'UN BARIL (#485-r3). `_table_modules` lie
                # `import engine.X as E` -> `E`, et `_attributs_lus` rend alors les attributs
                # EXACTS plus un drapeau d'ECHAPPEMENT : le bloc ci-dessous s'applique
                # (conservateur) des que le nom echappe. Mesure du 2026-08-18 : UN SEUL
                # `import engine.runner.abilities.loki as LK` dans `probe_r28_pick_order.py`
                # -- qui ne demande que `LK._pick_randomly_n` -- reclamait les **114**
                # symboles du baril, donc `vider` y rendait **0 retirable** sur 68 morts
                # reels. Le repli n'est leve que si la table resout `asname` VERS CE MODULE
                # (sinon deux `as` homonymes dans le meme fichier se masqueraient l'un
                # l'autre, et l'attribution deviendrait fausse au lieu d'etre large).
                for al in n.names:
                    if al.name not in barils:
                        continue
                    if al.asname and table.get(al.asname) == al.name:
                        continue          # traite finement par `_table_modules` ci-dessous
                    reclames[al.name] |= set(barils[al.name].exports)
        #: ⚠ LA MEME LIAISON DE MODULE EXISTE EN `ImportFrom`, ET ELLE ETAIT LE TROU. Le cas
        #: ci-dessus (`import X as E`) ne couvre qu'UNE des deux ecritures : `from engine.playbook
        #: import noncomparable as NC` lie AUSSI un module, et tout ce qu'on lui demande ensuite
        #: (`NC.NATIVE_PRIORITY`) est ATTRIBUTAIRE -- donc invisible du recensement d'`ImportFrom`
        #: ci-dessus, qui n'y voit qu'une reclamation du nom `noncomparable` au baril PARENT.
        #: Mesure du 2026-08-06 : la vidange a retire `NATIVE_PRIORITY`, `native_priority` et
        #: `_has_valid_targets` du baril `engine.playbook.noncomparable` et `DslContext` de
        #: `engine.dsl` -- 4 couples, dont DEUX lus par `engine/**` lui-meme
        #: (`ai/action_generators.py`, `playbook/tile_targets.py`), qu'aucun des tests tombes ne
        #: montrait. Cliquet : `probe_485r1r1_acces_attributaires.py`.
        for local, vise in table.items():
            if vise not in barils:
                continue
            attrs, echappe = _attributs_lus(arbre, local)
            reclames[vise] |= set(barils[vise].exports) if echappe else attrs

    chargeuses = _cibles_chargeuses_de_registre(barils)
    garde_registre: set[str] = set()
    bilan: list[tuple[str, int, int]] = []
    for nom, b in sorted(barils.items()):
        if nom in exclure or not b.exports:
            continue
        src = b.chemin.read_text(encoding="utf-8")
        arbre = ast.parse(src)
        utilises = _noms_references(arbre, avec_all=False)
        demandes = reclames.get(nom, set())
        retirables = {s for s in b.exports if s not in demandes and s not in utilises}
        #: LES DEUX FAMILLES D'IMPORTS INTOUCHABLES D'UN BARIL, ET LA SECONDE MANQUAIT.
        #:   * CHARGEUR DE REGISTRE (`chargeuses`) -- la cible est elle-meme un baril a
        #:     registre, ou l'ancetre d'un tel baril ;
        #:   * ENREGISTREUR (`b.enregistreurs`) -- la cible est un module FEUILLE dont le
        #:     top-level MUTE un conteneur du moteur. C'est le meme effet de bord, un cran
        #:     plus bas, et `vider` ne le regardait PAS : `derive_barils` remplit pourtant
        #:     ce champ. Mesure du 2026-08-18 -- sans ce cran, vider `engine.utilities`
        #:     SUPPRIME `from .move import ...` (ses trois noms sont morts), donc
        #:     `UTILITY_BY_TYPE[UtilityType.UnitMovement]` n'est plus jamais inscrit :
        #:     `utilities_database()` rend `None` la ou elle rendait l'utilite de mouvement,
        #:     sans erreur et sans qu'un test rougisse. Exactement la panne que l'exclusion
        #:     en bloc de #485-r1-r1 devait empecher, et qu'un vidage baril par baril
        #:     rouvre par le bas.
        proteges = set(chargeuses) | set(b.enregistreurs)
        #: Les noms apportes par un import PROTEGE restent lies au module (son import n'est
        #: pas retire) : les oter d'`__all__` creerait une incoherence entre ce que le baril
        #: expose et ce qu'il declare.
        for n in arbre.body:
            if isinstance(n, ast.ImportFrom) and (
                    cible_absolue(nom, n, racine) or "") in proteges:
                retirables -= {a.asname or a.name for a in n.names}
        if not retirables:
            bilan.append((nom, 0, len(b.exports)))
            continue
        lignes = lignes_de(src)
        edits: list[tuple[int, int, list[str]]] = []
        for n in arbre.body:
            if not isinstance(n, ast.ImportFrom):
                continue
            #: L'import qui CHARGE un registre -- ou qui tire un module ENREGISTREUR -- reste
            #: INTACT, meme si plus personne ne lui reclame de symbole : c'est son EXECUTION
            #: qui compte, pas ce qu'il expose.
            vise = cible_absolue(nom, n, racine) or ""
            if vise in proteges:
                garde_registre.add(vise)
                continue
            gardes = [(a.name, a.asname) for a in n.names
                      if (a.asname or a.name) not in retirables]
            if len(gardes) == len(n.names):
                continue
            seg = "\n".join(lignes[n.lineno - 1:n.end_lineno])
            fin_com, intercale = _commentaires(seg)
            if intercale:
                continue
            if gardes:
                neuf = _ligne_import("", n.module or "", n.level, gardes)
                if fin_com:
                    neuf[-1] += "  " + fin_com
            else:
                neuf = []
            edits.append((n.lineno - 1, n.end_lineno, neuf))
        # `__all__` suit
        for n in arbre.body:
            cibles = n.targets if isinstance(n, ast.Assign) else []
            if not any(isinstance(t, ast.Name) and t.id == "__all__" for t in cibles):
                continue
            if not isinstance(n.value, (ast.List, ast.Tuple)):
                continue
            gardes = [e.value for e in n.value.elts
                      if isinstance(e, ast.Constant) and e.value not in retirables]
            neuf = _ligne_all(gardes)
            edits.append((n.lineno - 1, n.end_lineno, neuf))
        out = list(lignes)
        for deb, fin, neuf in sorted(edits, key=lambda e: -e[0]):
            out[deb:fin] = neuf
        if appliquer:
            # `lignes_de` garde le dernier element VIDE d'un fichier termine par `\n` : le
            # rajouter ici creerait une ligne blanche a chaque passage.
            b.chemin.write_text("\n".join(out), encoding="utf-8")
        bilan.append((nom, len(retirables), len(b.exports) - len(retirables)))
    if garde_registre:
        print("  imports GARDES parce qu'ils CHARGENT un registre : %s"
              % ", ".join(sorted(garde_registre)))
    return bilan


def _ligne_all(noms: list[str]) -> list[str]:
    if not noms:
        return ["__all__ = []"]
    plat = "__all__ = [" + ", ".join('"%s"' % n for n in noms) + "]"
    if len(plat) <= LARGEUR:
        return [plat]
    out, ligne = ["__all__ = ["], "    "
    for n in noms:
        bout = '"%s",' % n
        if len(ligne) + len(bout) + 1 > LARGEUR and ligne.strip():
            out.append(ligne.rstrip())
            ligne = "    "
        ligne += bout + " "
    out.append(ligne.rstrip())
    out.append("]")
    return out


# ------------------------------------------------------------------------------------ rapports

def _imprimer_inventaire(barils: dict[str, Baril], exclure: set[str], verbeux: bool) -> None:
    tot_sym = sum(len(b.exports) for b in barils.values())
    reels = {k: v for k, v in barils.items() if v.exports or v.effets_de_bord}
    print("  barils (`__init__.py` qui re-exportent) : %d   symboles re-exportes : %d"
          % (len(reels), tot_sym))
    print("  barils a REGISTRE (exclus du remplacement naif) : %d" % len(exclure))
    for nom in sorted(exclure):
        b = barils[nom]
        print("      %-44s effets de bord: %-2d  enregistreurs: %d"
              % (nom, len(b.effets_de_bord), len(b.enregistreurs)))
        if verbeux:
            for m in b.effets_de_bord:
                print("          effet de bord PUR   %s" % m)
            for m in b.enregistreurs:
                print("          enregistreur        %s" % m)
    prof = defaultdict(int)
    for b in barils.values():
        for o in b.exports.values():
            prof[o.profondeur] += 1
    print("  profondeur des origines : %s"
          % ", ".join("%d maillon(s) x%d" % (k, v) for k, v in sorted(prof.items())))
    if verbeux:
        for nom, b in sorted(reels.items()):
            marque = "  [REGISTRE]" if nom in exclure else ""
            print("\n  %s%s -- %d symbole(s)" % (nom, marque, len(b.exports)))
            for s, o in sorted(b.exports.items()):
                print("      %-46s -> %s%s" % (s, o.module,
                                               "" if o.nom_amont == s else " (%s)" % o.nom_amont))


def _imprimer_refus(refus, entete: str, verbeux: bool) -> None:
    par_motif = defaultdict(list)
    for item in refus:
        par_motif[item[-1]].append(item)
    total = sum(len(v) for v in par_motif.values())
    print("\n  %s : %d" % (entete, total))
    for motif in Refus:
        lot = par_motif.get(motif)
        if not lot:
            continue
        print("      %-24s x%-4d  %s" % (motif.name, len(lot), motif.value))
        if verbeux:
            for item in sorted(lot, key=lambda x: str(x[0])):
                print("          %s:%s  %s" % (item[0], item[1], item[2]))
    inconnus = set(par_motif) - set(Refus)
    if inconnus:
        print("      *** motifs HORS ENUM : %s ***" % inconnus)


# ----------------------------------------------------------------------------------------- cli

def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("commande",
                    choices=("inventaire", "reecrire", "vider", "substitutions", "gestes",
                             "morsure"))
    ap.add_argument("--racine", type=Path, default=ICI,
                    help="repertoire qui CONTIENT `engine/` (defaut : celui de ce fichier). "
                         "Pointe un arbre TEMOIN pour mesurer sans toucher au depot.")
    ap.add_argument("--appliquer", action="store_true",
                    help="ECRIT les fichiers. Sans lui, marche a blanc.")
    ap.add_argument("--inclure-registres", action="store_true",
                    help="ne PAS exclure les barils a registre. A n'employer qu'avec la forme "
                         "`charger_tout()` deja cablee -- sinon le registre se vide en SILENCE.")
    ap.add_argument("--refus", action="store_true", help="liste INTEGRALE des refus et de la "
                                                         "table")
    ap.add_argument("--sortie", metavar="tri.json",
                    help="`gestes` : ECRIT le tri des differes GRATUITS (mesures par "
                         "`probe_485_imports_differes`) au format attendu par "
                         "`migrate_270r4r2r2_hisser_differes.py`. Le hissage a son propre "
                         "foyer -- on ne le re-implemente pas ici.")
    ap.add_argument("--baril", action="append", default=None, metavar="engine.X",
                    help="ne traiter QUE ce(s) baril(s). Repetable. Sert a mesurer si le "
                         "sweep est ADDITIF baril par baril -- il ne l'est pas, et c'est "
                         "cette option qui l'etablit plutot qu'un avis.")
    a = ap.parse_args(argv)

    racine = a.racine.resolve()
    if not (racine / "engine").is_dir():
        print("PAS MESURE : `%s` ne contient pas `engine/`." % racine)
        return EX_PAS_MESURE

    print("[485-r1] barils de re-export d'`engine/` -- racine %s" % racine)
    barils = derive_barils(racine)
    if not barils:
        print("  recensement VIDE -- ce n'est pas un zero, c'est un capteur muet.")
        return EX_PAS_MESURE
    exclure = set() if a.inclure_registres else {k for k, v in barils.items() if v.registre}
    if a.baril:
        inconnus = [x for x in a.baril if x not in barils]
        if inconnus:
            print("PAS MESURE : baril(s) inconnu(s) : %s" % ", ".join(inconnus))
            return EX_PAS_MESURE
        exclure |= set(barils) - set(a.baril)

    if a.commande == "gestes" and a.sortie:
        if racine != ICI:
            print("PAS MESURE : `--sortie` classe par `probe_485_imports_differes`, qui lit")
            print("SON PROPRE arbre. Joue cette commande depuis l'arbre a hisser.")
            return EX_PAS_MESURE
        try:
            import json

            import probe_485_imports_differes as P485
        except ImportError:
            print("PAS MESURE : `probe_485_imports_differes` introuvable.")
            return EX_PAS_MESURE
        differes = P485.recenser()
        classe = P485.classer(differes) if differes else None
        if classe is None:
            print("PAS MESURE : la classification porteur/gratuit n'a pas abouti -- on ne")
            print("hisse RIEN sur une mesure absente (un ensemble vide serait un faux zero).")
            return EX_PAS_MESURE
        porteurs, gratuits = classe
        #: une instruction peut viser PLUSIEURS cibles ; le hissage raisonne par INSTRUCTION,
        #: donc on regroupe par (module, ligne) et on unit les cibles.
        par_site: dict[tuple[str, int], set[str]] = defaultdict(set)
        for mod, cible, ligne, _ in gratuits:
            par_site[(mod, ligne)].add(cible)
        sites = [{"module": m, "ligne": l, "cibles": sorted(c)}
                 for (m, l), c in sorted(par_site.items())]
        cats = {"%s:%d" % (s["module"], s["ligne"]): {"categorie": "hissable"} for s in sites}
        Path(a.sortie).write_text(json.dumps({"sites": sites, "categories": cats}, indent=1),
                                  encoding="utf-8")
        print("\n  TRI ECRIT : %s -- %d instruction(s) GRATUITE(S) sur %d differe(s) recense(s)"
              % (a.sortie, len(sites), len(differes)))
        print("      (%d porteurs restent, et RESTERONT : hisser fermerait leur cycle.)"
              % len(porteurs))
        print("      A donner a `migrate_270r4r2r2_hisser_differes.py --tri <f> --ecrire`, qui")
        print("      porte les gardes du hissage -- dont le filtre ACYCLIQUE avec l'arete vers")
        print("      le paquet PARENT, sans lequel un lot a casse l'import de 405/409 modules.")
        print("      ⚠ AVANT d'ecrire : `morsure` dit lesquels desarmeraient un `monkeypatch`.")
        return EX_VERT

    if a.commande == "morsure":
        gratuits, source = _gratuits_frais(racine), "MESUREE A FRAIS sur cet arbre"
        if gratuits is None:
            gratuits, source = _gratuits_attestes(racine), ("base ATTESTEE -- elle decrit "
                                                            "l'arbre de sa DERNIERE ecriture")
        lignes, bilan = recenser_morsure(racine, gratuits)
        print("\n  base des GRATUITS : %s" % source)
        print("\n  MORSURE -- ce que le HISSAGE fait aux substitutions deja posees")
        print("      L'axe est DISTINCT de `substitutions` (qui mesure la RE-ECRITURE). Les")
        print("      confondre laisse passer le gisement mesure sur la famille #429-r1 : un")
        print("      hissage a rendu INERTE une mutation posee sur le module SOURCE, sur des")
        print("      tests LIVE que le recensement 100 %% offline de #484 ne pouvait pas voir.")
        if gratuits is None:
            print("      /!\\ base des GRATUITS absente -> le volet hissage n'est PAS mesure")
            print("          (tri-etat : on ne rend pas un zero pour une mesure absente).")
        for m in Morsure:
            lot = [x for x in lignes if x[0] is m]
            if not lot:
                continue
            print("\n      %-22s x%-4d %s" % (m.name, len(lot), m.value))
            for _, cible, nom, formes, sites in lot:
                print("          %s . %s" % (cible, nom))
                for f in Forme:
                    for s in sorted(formes.get(f, [])):
                        print("              [%s] %s" % (f.name, s))
                print("              patche par : %s" % ", ".join(sorted(set(sites))))
        print("\n      BILAN (partition des couples (module `engine`, attribut) substitues) :")
        for k in sorted(bilan):
            print("          %-62s %4d" % (k, bilan[k]))
        print("          %-62s %4d" % ("TOTAL", sum(bilan.values())))
        return EX_VERT

    if a.commande == "gestes":
        lot = qualifier_gestes(racine)
        print("\n  DIFFERES `engine.*` dans `engine/**` : %d -- geste de retrait" % len(lot))
        print("      Ce classement ne dit PAS porteur/gratuit (`probe_485_imports_differes.py`")
        print("      le mesure en process frais). Il dit COMMENT retirer celui qui peut l'etre.")
        par_geste = defaultdict(list)
        for x in lot:
            par_geste[x[4]].append(x)
        for g in Geste:
            gr = par_geste.get(g, [])
            print("\n      %-22s x%-4d %s" % (g.name, len(gr), g.value))
            if a.refus or g is not Geste.HISSER:
                for mod, cible, sym, ligne, _ in sorted(gr):
                    print("          %s:%d  %s <- %s" % (mod, ligne, sym, cible))
        return EX_VERT

    _imprimer_inventaire(barils, exclure, a.refus)
    if a.commande == "inventaire":
        return EX_VERT

    if a.commande == "substitutions":
        subs = recenser_substitutions(racine, barils, exclure,
                                      recenser_sites(racine, barils, exclure)[0])
        print("\n  SITES DE SUBSTITUTION croisant la table de re-ecriture : %d" % len(subs))
        print("      Ce n'est PAS le calcul qui est en jeu (mesure #484 : 0 divergence sur")
        print("      197 017 attributs), c'est la LIAISON DU NOM. Un stub qui cesse de mordre")
        print("      ne rougit pas -- le test cesse de mesurer.")
        par_risque = defaultdict(list)
        for s in subs:
            par_risque[s[4]].append(s)
        for r in Risque:
            lot = par_risque.get(r)
            if not lot:
                continue
            print("\n      %-18s x%d  %s" % (r.name, len(lot), r.value))
            for p, ligne, cible, attr, _, autre in sorted(lot, key=lambda x: str(x[0])):
                print("          %s:%d" % (p, ligne))
                print("              patch %s.%s   (autre bout : %s)" % (cible, attr, autre))
        if not subs:
            print("      AUCUN. Ce zero est une MESURE, pas un silence : le recenseur visite")
            print("      `monkeypatch.setattr/delattr`, `mock.patch`, `patch.object`,")
            print("      `setattr(mod, ...)` et l'affectation `mod.nom = ...`.")
        return EX_VERT

    sites, refus = recenser_sites(racine, barils, exclure)
    par_fichier: dict[Path, list[Site]] = defaultdict(list)
    for s in sites:
        par_fichier[s.fichier].append(s)

    if a.commande == "vider":
        bilan = vider_barils(racine, barils, exclure, a.appliquer)
        retires = sum(r for _, r, _ in bilan)
        print("\n  VIDANGE : %d re-export(s) retirable(s) sur %d baril(s)%s"
              % (retires, len([b for b in bilan if b[1]]),
                 " -- ECRIT" if a.appliquer else " -- marche a blanc"))
        for nom, r, g in bilan:
            if r:
                print("      %-46s -%-4d  restent %d" % (nom, r, g))
        return EX_VERT

    total_sym, ecrits, refus_ecriture = 0, 0, []
    for p, lot in sorted(par_fichier.items()):
        neuf, r = reecrire_fichier(p, lot, barils, racine)
        refus_ecriture += [(p, l, m, mo) for l, m, mo in r]
        if neuf is None:
            continue
        total_sym += sum(len(s.symboles) for s in lot)
        ecrits += 1
        if a.appliquer:
            p.write_text("\n".join(neuf), encoding="utf-8")
    print("\n  RE-ECRITURE : %d symbole(s) dans %d fichier(s)%s"
          % (total_sym, ecrits, " -- ECRIT" if a.appliquer else " -- marche a blanc"))
    _imprimer_refus(refus, "REFUS cote consommateur", a.refus)
    if refus_ecriture:
        _imprimer_refus(refus_ecriture, "REFUS a l'ecriture", a.refus)
    return EX_VERT


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
