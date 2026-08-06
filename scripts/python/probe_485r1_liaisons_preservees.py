#!/usr/bin/env python
"""#485-r1 -- la PREUVE que vider les barils est value-preserving, et ce qu'elle ne prouve PAS.

    python probe_485r1_liaisons_preservees.py --temoin <arbreA> --mesure <arbreB>

TROIS ETAGES, ET AUCUN NE SUFFIT SEUL
-------------------------------------
    [1] SYNTAXE       tout `.py` du perimetre parse encore. Cran trivial, mais un outil de
                      re-ecriture qui casse un fichier doit le dire AVANT les etages couteux.
    [2] AST HORS IMPORTS   pour chaque fichier modifie, l'arbre PRIVE de ses noeuds
                      `Import`/`ImportFrom` doit etre IDENTIQUE. C'est ce qui etablit que la
                      re-ecriture n'a touche QUE des imports -- rien, dans un diff de 400
                      fichiers, ne distingue a l'oeil un import deplace d'une ligne de code
                      emportee avec lui.
    [3] LIAISONS      pour chaque module `engine.**`, on importe dans un process FRAIS et on
                      hache `{attribut: IDENTITE de l'objet lie}`. Deux arbres qui lient les
                      memes noms aux memes objets calculent la meme chose.

⚠ ON HACHE LA VALEUR, PAS LA REPRESENTATION. `repr(<function f at 0x7ff...>)` change a chaque
run : une empreinte par `repr` rendrait des divergences TOUTES FAUSSES (mesure #270-r1-r1, ou
`repr(6)` != `repr(<PathfinderType.TeleportStrikeWalk: 6>)` alors qu'un `IntEnum` EST un `int`).
L'identite retenue est `<module>.<qualname>` pour ce qui est defini, `int(x)` pour les entiers
(donc les `IntEnum`), et une recursion dans les conteneurs.

⚠ LA PORTEE SE PREND LARGE. Une liste de symboles choisis ne peut pas montrer celui qu'elle a
oublie : on visite TOUT attribut public de module ET de classe du paquet.

⚠⚠ CE QUE CES TROIS ETAGES NE PROUVENT PAS, ET C'EST L'ESSENTIEL (#484, PR #741)
--------------------------------------------------------------------------------
La mesure #484 a hisse 624 imports differes : **0 divergence sur 197 017 attributs**, et
**28 fichiers de tests rouges**. Une empreinte verte n'est donc PAS une preuve d'innocuite --
elle etait verte sur exactement le commit qui a casse la banque.

    hisser ne change pas ce que le code CALCULE, il change OU LE NOM EST LIE.

Un `monkeypatch` pose sur le module SOURCE mord tant que le nom est resolu A L'APPEL (import
differe), et ne mord PLUS une fois qu'il est lie AU CHARGEMENT. Les tests n'ont pas mesure
FAUX : ils ont CESSE DE MESURER, ce qui ne rougit nulle part. Le recensement des sites de
substitution vit dans `migrate_485r1_barils_reexport.py substitutions` ; le seul controle qui
voit le desarmement est la CONTRE-EPREUVE de l'etage [4] (`--contre-epreuve`).

ASCII only (console Windows cp1252).
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

#: Import TOP-LEVEL, et deliberement : #485-r1 livre l'outil et sa preuve ensemble, donc la
#: table doit etre derivee par LE MEME code que celui qui a re-ecrit. `derive_barils` prend sa
#: racine en argument -- lire le module voisin ne fait donc PAS lire le mauvais arbre. Un
#: import differe ici serait ironique, et le seul argument en sa faveur (aller chercher la
#: version de l'arbre temoin) est justement celui qu'il ne faut pas suivre.
import migrate_485r1_barils_reexport as mig

EX_VERT, EX_ROUGE, EX_PAS_MESURE = 0, 1, 2

#: Le programme joue DANS l'arbre mesure : il ne peut donc pas etre importe depuis celui-ci.
#: On l'injecte par `-c`, ce qui garde le process totalement frais.
_SONDE = r"""
import importlib, json, sys
mod = importlib.import_module(sys.argv[1])

def ident(o, prof=0):
    if prof > 3:
        return "..."
    if o is None or isinstance(o, bool):
        return "v:%r" % o
    if isinstance(o, int):          # couvre les IntEnum : on hache la VALEUR
        return "i:%d" % int(o)
    if isinstance(o, float):
        return "f:%r" % float(o)
    if isinstance(o, str):
        return "s:%s" % o
    if isinstance(o, (list, tuple)):
        return "[%s]" % ",".join(ident(x, prof + 1) for x in o)
    if isinstance(o, (set, frozenset)):
        return "{%s}" % ",".join(sorted(ident(x, prof + 1) for x in o))
    if isinstance(o, dict):
        return "{%s}" % ",".join(sorted("%s=%s" % (ident(k, prof + 1), ident(v, prof + 1))
                                        for k, v in o.items()))
    m, q = getattr(o, "__module__", None), getattr(o, "__qualname__", None)
    if m and q:
        return "d:%s.%s" % (m, q)
    t = type(o)
    return "o:%s.%s" % (t.__module__, t.__qualname__)

out = {}
for nom in dir(mod):
    if nom.startswith("_"):
        continue
    try:
        val = getattr(mod, nom)
    except Exception as exc:
        out[nom] = "ERR:%s" % type(exc).__name__
        continue
    out[nom] = ident(val)
    if isinstance(val, type) and getattr(val, "__module__", "").startswith("engine"):
        for a in dir(val):
            if a.startswith("_"):
                continue
            try:
                out["%s.%s" % (nom, a)] = ident(getattr(val, a))
            except Exception as exc:
                out["%s.%s" % (nom, a)] = "ERR:%s" % type(exc).__name__
print(json.dumps(out, sort_keys=True))
"""


def modules_engine(racine: Path) -> list[str]:
    out = []
    for p in sorted((racine / "engine").rglob("*.py")):
        if "__pycache__" in str(p):
            continue
        parts = list(p.relative_to(racine).with_suffix("").parts)
        if parts[-1] == "__init__":
            parts = parts[:-1]
        out.append(".".join(parts))
    return out


def _sonder(racine: Path, mod: str) -> tuple[str, dict | None]:
    try:
        r = subprocess.run([sys.executable, "-c", _SONDE, mod], cwd=str(racine),
                           capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=180)
    except (OSError, subprocess.SubprocessError):
        return mod, None
    if r.returncode != 0 or not r.stdout:
        return mod, None
    try:
        return mod, json.loads(r.stdout)
    except json.JSONDecodeError:
        return mod, None


class _SansImports(ast.NodeTransformer):
    """Retire TOUT noeud d'import -- et, en regime VIDANGE, l'assignation `__all__`.

    Un bloc qui n'en contenait que devient `pass` : sans quoi l'empreinte varierait selon
    qu'un import etait ou non le seul statement du corps.

    ⚠ `__all__` EST DU CODE, PAS UN IMPORT, et vider un baril le reecrit forcement. Sans ce
    cas, les 15 `__init__.py` vides sortaient tous en << AST HORS IMPORTS DIFFERENT >> --
    un rouge par CONSTRUCTION, qui aurait noye le seul rouge qui compte. Il n'est retire
    QU'EN regime vidange, et jamais en regime re-ecriture seule, ou toute retouche d'`__all__`
    serait au contraire une faute."""

    def __init__(self, sans_all: bool = False) -> None:
        self.sans_all = sans_all

    def visit_Import(self, node):        # noqa: N802
        return None

    def visit_ImportFrom(self, node):    # noqa: N802
        return None

    def visit_Assign(self, node):        # noqa: N802
        if self.sans_all and any(isinstance(t, ast.Name) and t.id == "__all__"
                                 for t in node.targets):
            return None
        return self.generic_visit(node)

    def generic_visit(self, node):
        node = super().generic_visit(node)
        corps = getattr(node, "body", None)
        if isinstance(corps, list) and not corps:
            node.body = [ast.Pass()]
        return node


def empreinte_sans_imports(source: str, sans_all: bool = False) -> str:
    arbre = _SansImports(sans_all=sans_all).visit(ast.parse(source))
    ast.fix_missing_locations(arbre)
    return hashlib.sha256(
        ast.dump(arbre, annotate_fields=True, include_attributes=False).encode()).hexdigest()


def etage_syntaxe(racines: dict[str, Path]) -> list[str]:
    fautes = []
    for etiquette, racine in racines.items():
        for p in sorted(racine.rglob("*.py")):
            if "__pycache__" in str(p):
                continue
            try:
                ast.parse(p.read_text(encoding="utf-8"))
            except (SyntaxError, UnicodeDecodeError) as exc:                # noqa: BLE001
                fautes.append("%s %s : %s" % (etiquette, p, exc))
    return fautes


def etage_ast(a: Path, b: Path, vidange: bool = False) -> tuple[int, list[str]]:
    """(nb de fichiers compares, divergents)."""
    divergents, compares = [], 0
    for pa in sorted(a.rglob("*.py")):
        if "__pycache__" in str(pa):
            continue
        rel = pa.relative_to(a)
        pb = b / rel
        if not pb.is_file():
            divergents.append("%s : ABSENT de l'arbre mesure" % rel)
            continue
        sans_all = vidange and pa.name == "__init__.py"
        try:
            ea = empreinte_sans_imports(pa.read_text(encoding="utf-8"), sans_all)
            eb = empreinte_sans_imports(pb.read_text(encoding="utf-8"), sans_all)
        except (SyntaxError, UnicodeDecodeError) as exc:                    # noqa: BLE001
            divergents.append("%s : ILLISIBLE (%s)" % (rel, exc))
            continue
        compares += 1
        if ea != eb:
            divergents.append("%s : AST HORS IMPORTS DIFFERENT" % rel)
    return compares, divergents


def trier_divergences(divergences, tb: dict, origines: dict, racine: Path):
    """Regime VIDANGE : separe les DEPLACEMENTS legitimes des vraies PERTES.

    Une divergence n'est acquittee QUE si les trois conditions tiennent :
      1. c'est une DISPARITION (le symbole quittait un baril), jamais une MUTATION ;
      2. le couple (baril, symbole) est bien dans la table de re-ecriture ;
      3. le module d'ORIGINE porte, dans l'arbre MESURE, la MEME identite.

    C'est (3) qui fait la preuve. Sans lui on n'aurait verifie que la disparition -- or
    << le symbole a disparu du baril >> et << le symbole est encore joignable >> sont deux
    affirmations distinctes, et seule la seconde autorise a vider.

    ⚠ UNE QUATRIEME CATEGORIE EXISTE, ET LA NOYER DANS LES PERTES SERAIT FAUX DANS LES DEUX
    SENS. Python pose l'attribut `paquet.enfant` UNIQUEMENT si un import a charge l'enfant.
    Vider `engine/ai/__init__.py` retire donc aussi `engine.ai.bucket` -- pas un symbole, un
    SOUS-MODULE. Mesure : 91 des 12 728 divergences. Le module reste parfaitement joignable
    par son chemin complet, mais un `import engine.ai` suivi d'un `engine.ai.bucket.X` casse.
    C'est un effet REEL, a lister integralement, distinct d'un symbole introuvable."""
    acquittees, perdues, sous_modules = [], [], []
    for mod, cle, va, vb in divergences:
        if vb is not None:
            perdues.append("%s.%s : MUTATION %r -> %r (pas une disparition)"
                           % (mod, cle, va, vb))
            continue
        #: ⚠ LA PORTEE EST LARGE : la sonde visite aussi les attributs de CLASSE, sous la cle
        #: `Classe.attribut`. Le sort d'un tel attribut est celui de sa CLASSE -- le chercher
        #: tel quel dans la table le declarerait << hors table >>, et des milliers de
        #: deplacements legitimes seraient comptes comme des pertes.
        tete, _sep, suite = cle.partition(".")
        paire = origines.get((mod, tete))
        if paire is None:
            chemin = racine / Path(*("%s.%s" % (mod, tete)).split("."))
            if chemin.is_dir() or chemin.with_suffix(".py").is_file():
                sous_modules.append("%s.%s" % (mod, cle))
            else:
                perdues.append("%s.%s : disparu, HORS table et ce n'est pas un sous-module"
                               % (mod, cle))
            continue
        org, amont_nom = paire
        cle_amont = amont_nom + ("." + suite if suite else "")
        amont = (tb.get(org) or {}).get(cle_amont)
        if amont is None:
            perdues.append("%s.%s : disparu du baril ET introuvable a l'origine %s (%s)"
                           % (mod, cle, org, cle_amont))
        elif amont != va:
            perdues.append("%s.%s : retrouve a %s mais IDENTITE DIFFERENTE : %r != %r"
                           % (mod, cle, org, amont, va))
        else:
            acquittees.append("%s.%s -> %s.%s" % (mod, cle, org, cle_amont))
    return acquittees, perdues, sous_modules


def etage_liaisons(a: Path, b: Path):
    """(compares, attributs, divergences, muets ASYMETRIQUES, muets des DEUX, table mesuree).

    ⚠ LES DEUX MUTISMES NE SE DISENT PAS AVEC LE MEME MOT. Un module muet d'UN SEUL cote est
    un ROUGE : la re-ecriture l'a casse (ou repare). Un module muet des DEUX cotes n'accuse
    rien -- il ne s'importait deja pas seul -- mais il n'est pas COUVERT, et le confondre avec
    un vert ferait passer pour mesure ce qui est un trou."""
    mods = sorted(set(modules_engine(a)) | set(modules_engine(b)))
    with ThreadPoolExecutor(max_workers=12) as ex:
        ta = dict(ex.map(lambda m: _sonder(a, m), mods))
        tb = dict(ex.map(lambda m: _sonder(b, m), mods))
    muets = sorted(m for m in mods if (ta.get(m) is None) != (tb.get(m) is None))
    aveugles = sorted(m for m in mods if ta.get(m) is None and tb.get(m) is None)
    divergences, attributs, compares = [], 0, 0
    for m in mods:
        va, vb = ta.get(m), tb.get(m)
        if va is None or vb is None:
            continue
        compares += 1
        for cle in sorted(set(va) | set(vb)):
            attributs += 1
            if va.get(cle) != vb.get(cle):
                divergences.append((m, cle, va.get(cle), vb.get(cle)))
    return compares, attributs, divergences, muets, aveugles, tb


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--temoin", type=Path, required=True,
                    help="racine de l'arbre TEMOIN (contient `engine/`)")
    ap.add_argument("--mesure", type=Path, required=True,
                    help="racine de l'arbre MESURE (re-ecrit)")
    ap.add_argument("--max-divergences", type=int, default=30)
    ap.add_argument("--vidange", action="store_true",
                    help="l'arbre mesure a AUSSI ete vide (`migrate_485r1... vider`). Les "
                         "barils perdent alors des attributs PAR CONSTRUCTION : chaque "
                         "disparition doit etre retrouvee, avec la MEME identite, au module "
                         "d'origine. Sans ce drapeau, toute disparition est un ROUGE.")
    a = ap.parse_args(argv)

    ra, rb = a.temoin.resolve(), a.mesure.resolve()
    for r in (ra, rb):
        if not (r / "engine").is_dir():
            print("PAS MESURE : `%s` ne contient pas `engine/`." % r)
            return EX_PAS_MESURE

    print("=== [485-r1] liaisons preservees ===")
    print("  temoin : %s" % ra)
    print("  mesure : %s" % rb)

    print("\n[1] SYNTAXE")
    fautes = etage_syntaxe({"temoin": ra, "mesure": rb})
    print("    %d fichier(s) qui ne parsent plus" % len(fautes))
    for f in fautes[:a.max_divergences]:
        print("        %s" % f)

    print("\n[2] AST HORS IMPORTS%s" % (" (et hors `__all__` des barils)" if a.vidange else ""))
    compares, divergents = etage_ast(ra, rb, vidange=a.vidange)
    print("    %d fichier(s) compare(s), %d divergent(s)" % (compares, len(divergents)))
    if not compares:
        print("    PERIMETRE VIDE -- ce n'est pas un vert, c'est un capteur muet.")
        return EX_PAS_MESURE
    for d in divergents[:a.max_divergences]:
        print("        %s" % d)

    print("\n[3] LIAISONS (process frais, par module)")
    nm, na, div, muets, aveugles, tb = etage_liaisons(ra, rb)
    print("    %d module(s) compare(s), %d attribut(s), %d divergence(s)" % (nm, na, len(div)))
    acquittees: list[str] = []
    if a.vidange and div:
        #: La table se derive de l'arbre TEMOIN : c'est la que les barils exportent encore.
        barils = mig.derive_barils(ra)
        origines = {(nom, sym): (org.module, org.nom_amont)
                    for nom, b in barils.items() for sym, org in b.exports.items()}
        acquittees, perdues, sous_mods = trier_divergences(div, tb, origines, rb)
        print("    regime VIDANGE : %d deplacement(s) ACQUITTE(S), %d attribut(s) SOUS-MODULE, "
              "%d PERTE(S) reelle(s)" % (len(acquittees), len(sous_mods), len(perdues)))
        print("        un acquittement exige les TROIS : disparition (jamais mutation),")
        print("        couple present dans la table, et MEME identite au module d'origine.")
        if sous_mods:
            print("    %d attribut(s) SOUS-MODULE retire(s) du paquet -- pas une perte de "
                  "symbole," % len(sous_mods))
            print("    mais `import <paquet>` puis `<paquet>.<enfant>` cesse de marcher. "
                  "Liste INTEGRALE :")
            for s in sous_mods:
                print("        %s" % s)
        div = [(p, "", "", "") for p in perdues]
    if aveugles:
        print("    %d module(s) muet(s) des DEUX cotes -- pas un rouge, mais PAS COUVERT :"
              % len(aveugles))
        for m in aveugles[:a.max_divergences]:
            print("        %s" % m)
    if muets:
        print("    %d module(s) MUET(S) d'un cote seulement -- c'est un ROUGE, pas un vide :"
              % len(muets))
        for m in muets[:a.max_divergences]:
            print("        %s" % m)
    for d in div[:a.max_divergences]:
        print("        %s" % (d[0] if a.vidange else
                             "%s.%s : %r -> %r" % (d[0], d[1], d[2], d[3])))
    if a.vidange and not acquittees and not div:
        print("    AUCUN deplacement ACQUITTE : en regime vidange, cela veut dire que rien")
        print("    n'a ete vide -- le controle n'a donc rien mesure de ce qu'il pretend garder.")
        return EX_PAS_MESURE
    if not na:
        print("    AUCUN attribut compare -- capteur muet.")
        return EX_PAS_MESURE

    rouge = bool(fautes or divergents or div or muets)
    print("\nVERDICT : %s" % ("ROUGE" if rouge else "VERT"))
    print("  /!\\ Un VERT ici ne dit PAS que la banque de tests survit. Mesure #484 : 0 divergence")
    print("    sur 197 017 attributs, et 28 fichiers rouges -- la liaison des NOMS avait bouge")
    print("    sous les `monkeypatch`. Croiser avec `migrate_485r1... substitutions`.")
    return EX_ROUGE if rouge else EX_VERT


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
