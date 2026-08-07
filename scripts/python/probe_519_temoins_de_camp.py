"""#519 -- LE CLIQUET DU MOTIF : un TEMOIN FIGE qui designe une ability CHANGEANT DE CAMP.

LE MOTIF, mesure le 2026-08-07. Une tranche de portage fait ENTRER une ability dans
`ABILITY_CLASSES` et SORTIR son masque de `TARGETING_OPTIONS_UNPORTED`. Tout site executable qui
avait FIGE l'id de cette ability du cote « pas encore portee » devient FAUX -- silencieusement pour
un `probe`, en ROUGE pour un test. Quatre occurrences dans la seule journee du 2026-08-07, dont
DEUX rouges sur `master` :

  * `1069` COBAYE d'un `TARGETING_OPTIONS_UNPORTED[...]` -> `KeyError` a la sortie de 1069 (#491) ;
  * `1091` TEMOIN de `targeting_options_for(x) is None` dans **DEUX** fichiers de garde -- le brief
    de cette tranche n'en signalait qu'UN, le second a ete trouve par ce balayage meme ;
  * les compteurs d'en-tete de `targeting.py` (volet separe, `probe_519_comptes_de_table.py`).

CE QUE CE PROBE VOIT -- l'axe EXECUTABLE, et lui seul. Il balaie l'AST de `scripts/python/**` et
releve les sites ou un id d'ability **LITTERAL** (entier nu ou membre `ActiveAbilityType`) est
confronte a l'une des deux tables de camp. Quatre formes :

    <lit> in / not in ABILITY_CLASSES | TARGETING_OPTIONS_UNPORTED
    ABILITY_CLASSES[<lit>] | TARGETING_OPTIONS_UNPORTED[<lit>]        (lecture -- un cobaye)
    <table>.get(<lit>)                     compare a None
    targeting_options_for(<lit>)           compare a None

L'ASYMETRIE EST LA CLE, et c'est elle qui rend le tri MECANIQUE. Notre cadence est A SENS UNIQUE :
une ability va de « non portee » vers « portee », jamais l'inverse. Donc une affirmation
  * « x EST au registre / x N'EST PAS dans UNPORTED / son masque EST lu »  -> **STABLE** ;
  * « x N'EST PAS au registre / x EST dans UNPORTED / son masque n'est PAS lu » -> **PERISSABLE**.
Un site PERISSABLE n'est pas une faute : c'est une dette datee, qui tombera a la tranche qui portera
son id. Le probe la NOMME pour qu'elle soit choisie, pas subie.

CE QU'IL NE VOIT PAS, et il faut le lire comme une portee, pas comme un zero :
  * la PROSE (docstrings, commentaires, `docs/rl/**`) -- un id cite dans un paragraphe n'est
    confronte a rien ; ce volet-la n'a pas de critere mecanique et reste OUVERT ;
  * les ids qui arrivent par une VARIABLE (`TARGETING_OPTIONS_UNPORTED[aid]` dans une boucle) --
    ils suivent la table, donc ils ne perissent pas ;
  * les MUTATIONS de table (`T[x] = ...`, `del T[x]`, monkeypatch) -- ce ne sont pas des
    affirmations de camp ; elles sont exclues par le contexte AST (`Store`/`Del`).
  * les autres tables que ces deux-la (`ABILITY_ATTACK_TYPE`, `DYNAMIC_TARGET_GATE_BY_ABILITY`...) :
    elles ne sont pas mutees par la cadence de portage dans le sens qui perime un temoin.

SORTIE : `PERIME` (l'affirmation est FAUSSE aujourd'hui) fait rc 1. `PERISSABLE` et `STABLE` sont
imprimes pour inventaire. ASCII only.
"""
from __future__ import annotations

import argparse
import ast
import pathlib
import sys

_ICI = pathlib.Path(__file__).resolve().parent
if str(_ICI) not in sys.path:
    sys.path.insert(0, str(_ICI))

from engine.entities.active_ability_type import ActiveAbilityType          # noqa: E402
from engine.runner.abilities.handler import ABILITY_CLASSES                # noqa: E402
from engine.runner.abilities.targeting import (                            # noqa: E402
    TARGETING_OPTIONS_UNPORTED, targeting_options_for)

#: Les deux tables que la cadence de portage MUTE, et le sens de cette mutation.
#: `True` = la table GROSSIT quand une ability est portee ; `False` = elle RETRECIT.
TABLES_DE_CAMP = {
    "ABILITY_CLASSES": True,
    "TARGETING_OPTIONS_UNPORTED": False,
}

#: Le lecteur d'UNION des deux tables (`targeting.targeting_options_for`) -- il passe de `None` a
#: non-`None` quand le masque est lu, jamais l'inverse.
LECTEUR_UNION = "targeting_options_for"

PERIME, PERISSABLE, STABLE = "PERIME", "PERISSABLE", "STABLE"

#: Les jetons TEXTUELS sans lesquels un fichier ne peut porter aucun site (cf. `balayer`).
_JETONS = tuple(TABLES_DE_CAMP) + (LECTEUR_UNION,)


class Site:
    """Une affirmation de camp trouvee dans du code EXECUTABLE."""

    __slots__ = ("chemin", "ligne", "aid", "texte", "vrai_si", "verdict")

    def __init__(self, chemin, ligne, aid, texte, vrai_si):
        self.chemin, self.ligne, self.aid, self.texte = chemin, ligne, aid, texte
        #: L'affirmation ecrite au site, sous forme booleenne : `True` = « x est du cote PORTE ».
        self.vrai_si = vrai_si
        self.verdict = None

    def __str__(self):
        return "%s:%d  %-46s  id=%-5s  %s" % (
            self.chemin, self.ligne, self.texte, self.aid, self.verdict)


def _id_litteral(noeud):
    """L'id d'ability d'un noeud, s'il est LITTERAL. `None` sinon (variable, expression...).

    Deux ecritures valides et une seule verite : l'entier nu (heritage) et le membre
    `ActiveAbilityType` (la regle « un entier qui DESIGNE passe par son ENUM »)."""
    if isinstance(noeud, ast.Constant) and isinstance(noeud.value, int) \
            and not isinstance(noeud.value, bool):
        return int(noeud.value)
    if isinstance(noeud, ast.Attribute) and isinstance(noeud.value, ast.Name) \
            and noeud.value.id == "ActiveAbilityType":
        membre = getattr(ActiveAbilityType, noeud.attr, None)
        return int(membre) if membre is not None else None
    return None


def _nom_table(noeud):
    """Le nom de table d'un noeud `Name` ou `Attribute` (`T.TARGETING_OPTIONS_UNPORTED`)."""
    if isinstance(noeud, ast.Name):
        return noeud.id if noeud.id in TABLES_DE_CAMP else None
    if isinstance(noeud, ast.Attribute):
        return noeud.attr if noeud.attr in TABLES_DE_CAMP else None
    return None


def _est_lecteur_union(noeud):
    """`targeting_options_for` ou `<mod>.targeting_options_for`."""
    if isinstance(noeud, ast.Name):
        return noeud.id == LECTEUR_UNION
    if isinstance(noeud, ast.Attribute):
        return noeud.attr == LECTEUR_UNION
    return False


def _compare_a_none(noeud):
    """Rend `True` si le noeud est `<x> is None`, `False` si `<x> is not None`, `None` sinon.

    Le noeud passe est le `Compare` ; l'appelant a deja identifie l'operande gauche."""
    if not isinstance(noeud, ast.Compare) or len(noeud.ops) != 1:
        return None
    op, droite = noeud.ops[0], noeud.comparators[0]
    if not (isinstance(droite, ast.Constant) and droite.value is None):
        return None
    if isinstance(op, ast.Is):
        return True
    if isinstance(op, ast.IsNot):
        return False
    return None


def _releve(chemin, texte_source):
    """Tous les sites d'affirmation de camp d'un fichier."""
    sites = []
    arbre = ast.parse(texte_source)
    rel = chemin
    for noeud in ast.walk(arbre):

        # --- forme 1 : `<lit> in <table>` / `<lit> not in <table>`
        if isinstance(noeud, ast.Compare) and len(noeud.ops) == 1 \
                and isinstance(noeud.ops[0], (ast.In, ast.NotIn)):
            aid = _id_litteral(noeud.left)
            table = _nom_table(noeud.comparators[0])
            if aid is not None and table is not None:
                dedans = isinstance(noeud.ops[0], ast.In)
                # « x est du cote PORTE » : vrai si (dedans and table grossit) ou
                # (not dedans and table retrecit).
                sites.append(Site(rel, noeud.lineno, aid,
                                  "%s %s %s" % (aid, "in" if dedans else "not in", table),
                                  vrai_si=(dedans == TABLES_DE_CAMP[table])))
                continue

        # --- forme 2 : `<table>[<lit>]` EN LECTURE (un cobaye : `KeyError` a la sortie de l'id)
        if isinstance(noeud, ast.Subscript) and isinstance(noeud.ctx, ast.Load):
            table = _nom_table(noeud.value)
            aid = _id_litteral(noeud.slice)
            if aid is not None and table is not None:
                sites.append(Site(rel, noeud.lineno, aid, "%s[%s]" % (table, aid),
                                  vrai_si=TABLES_DE_CAMP[table]))
                continue

        # --- formes 3 et 4 : un appel compare a `None`
        if isinstance(noeud, ast.Compare):
            gauche = noeud.left
            if not isinstance(gauche, ast.Call) or len(gauche.args) != 1:
                continue
            aid = _id_litteral(gauche.args[0])
            if aid is None:
                continue
            est_none = _compare_a_none(noeud)
            if est_none is None:
                continue
            if _est_lecteur_union(gauche.func):
                sites.append(Site(rel, noeud.lineno, aid,
                                  "%s(%s) is%s None" % (LECTEUR_UNION, aid,
                                                        "" if est_none else " not"),
                                  vrai_si=not est_none))
                continue
            if isinstance(gauche.func, ast.Attribute) and gauche.func.attr == "get":
                table = _nom_table(gauche.func.value)
                if table is not None:
                    present = not est_none
                    sites.append(Site(rel, noeud.lineno, aid,
                                      "%s.get(%s) is%s None" % (table, aid,
                                                                "" if est_none else " not"),
                                      vrai_si=(present == TABLES_DE_CAMP[table])))
    return sites


def _camp_courant(aid, texte):
    """L'etat REEL, aujourd'hui : `True` = l'ability est du cote PORTE pour CETTE forme."""
    if texte.startswith(LECTEUR_UNION):
        return targeting_options_for(aid) is not None
    if "ABILITY_CLASSES" in texte:
        return aid in ABILITY_CLASSES
    return aid not in TARGETING_OPTIONS_UNPORTED


def balayer(racine=None):
    """Tous les sites du corpus, verdict pose. Le corpus est `scripts/python/**/*.py`."""
    racine = pathlib.Path(racine) if racine else _ICI
    sites = []
    for f in sorted(racine.rglob("*.py")):
        if f.name == pathlib.Path(__file__).name:
            continue                                   # ce probe cite les tables, il n'affirme rien
        try:
            src = f.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        # PRE-FILTRE TEXTUEL, et il est SUR : une affirmation de camp cite forcement le NOM de la
        # table ou celui du lecteur d'union, puisque c'est ce nom que l'AST reconnait. Un fichier
        # qui ne contient aucun de ces jetons ne peut porter aucun site -- le filtre ne peut donc
        # pas en cacher un. Effet mesure : 22,9 s -> 1,3 s sur `scripts/python/**`.
        if not any(j in src for j in _JETONS):
            continue
        try:
            trouves = _releve(f.relative_to(racine).as_posix(), src)
        except SyntaxError:
            continue
        sites.extend(trouves)
    for s in sites:
        reel = _camp_courant(s.aid, s.texte)
        if reel != s.vrai_si:
            s.verdict = PERIME
        else:
            # STABLE = l'affirmation va dans le SENS de la cadence (elle ne peut plus tomber).
            s.verdict = STABLE if s.vrai_si else PERISSABLE
    return sites


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--tout", action="store_true", help="imprime aussi les sites STABLE")
    args = ap.parse_args(argv)

    sites = balayer()
    par_verdict = {PERIME: [], PERISSABLE: [], STABLE: []}
    for s in sites:
        par_verdict[s.verdict].append(s)

    print("#519 -- TEMOINS DE CAMP FIGES, axe EXECUTABLE (`scripts/python/**`)")
    print("corpus : %d sites d'affirmation" % len(sites))
    if not sites:
        print("AUCUN SITE TROUVE -- le balayage ne mesure RIEN ; c'est un defaut d'outil, pas un vert.")
        return 2

    print("")
    print("PERIME     (%d) -- l'affirmation est FAUSSE aujourd'hui" % len(par_verdict[PERIME]))
    for s in par_verdict[PERIME]:
        print("  %s" % s)
    print("")
    print("PERISSABLE (%d) -- vraie aujourd'hui, tombera a la tranche qui portera son id"
          % len(par_verdict[PERISSABLE]))
    for s in par_verdict[PERISSABLE]:
        print("  %s" % s)
    print("")
    print("STABLE     (%d) -- va dans le sens de la cadence, ne peut plus tomber"
          % len(par_verdict[STABLE]))
    if args.tout:
        for s in par_verdict[STABLE]:
            print("  %s" % s)

    print("")
    print("PORTEE DE LA MESURE : axe EXECUTABLE seul. La PROSE (docstrings, commentaires,")
    print("`docs/rl/**`) n'est PAS balayee -- un id cite dans un paragraphe n'est confronte a rien.")
    print("Les ids arrivant par une VARIABLE suivent la table et ne perissent pas ; les MUTATIONS")
    print("de table (Store/Del, monkeypatch) ne sont pas des affirmations et sont exclues.")
    return 1 if par_verdict[PERIME] else 0


if __name__ == "__main__":
    raise SystemExit(main())
