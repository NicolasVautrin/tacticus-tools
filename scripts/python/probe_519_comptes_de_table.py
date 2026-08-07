"""#519 -- LES COMPTES DE `TARGETING_OPTIONS_UNPORTED` SE DERIVENT, ILS NE S'ECRIVENT PLUS.

LE MOTIF. Cette table RETRECIT a chaque face COMBAT portee (contrat de disjonction). Tout compte
ecrit A LA MAIN dans son en-tete se perime donc a la tranche suivante, en silence -- aucun test ne
les lisait. Mesure du 2026-08-07 : QUATRE valeurs fausses corrigees a la main dans la journee,
chacune re-cassee par la tranche d'apres (`16` pour 7, `31` pour 33, `28` pour 27, `30` pour 28).

ET LA CORRECTION DU JOUR ETAIT ELLE-MEME FAUSSE, ce qui est le vrai argument de cet outil : la
ventilation par FORME de ctor annoncait `10 / 4 / 0 / 13` la ou le code en porte `12 / 6 / 0 / 9`.
Trois des quatre nombres etaient faux -- et leur SOMME etait juste (27 des deux cotes), donc le seul
controle qu'un relecteur pouvait faire de tete PASSAIT. Un accord peut etre le produit de fautes qui
se compensent ; c'est exactement ce qui s'est produit ici.

COMMENT LA FORME EST DERIVEE. Elle n'est PAS devinee : chaque entree herite du marqueur

    @FORME <FLAGS-DIRECTS|PRESET+FLAGS|PRESET-SEUL|STATIC-COPY>

le plus proche AU-DESSUS d'elle dans le fichier. Les en-tetes de section en portent un ; les quatre
entrees hors-bloc, qui ne vivent dans aucune section, en portent un chacune. La forme reste un fait
de RE (quelle surcharge de `IdunBattle.Core.Services.TargetingOptions$$.ctor` le ctor de l'ability
appelle, tranche par ses XREFS ENTRANTES) -- ce probe ne fait que la COMPTER.

DEUX MODES :
    --verifier  (defaut) compare le BLOC GENERE de l'en-tete a la derivation. rc 1 si divergence,
                et il imprime le bloc attendu, pret a coller.
    --ecrire    reecrit le bloc en place.

PORTEE DE LA MESURE : ce probe ne voit que `TARGETING_OPTIONS_UNPORTED` et le fichier qui la porte.
Il ne dit RIEN des comptes ecrits ailleurs (`docs/rl/**`, autres modules) ni des TEMOINS figes --
ceux-la sont l'axe de `probe_519_temoins_de_camp.py`. ASCII only.
"""
from __future__ import annotations

import argparse
import ast
import pathlib
import re
import sys

_ICI = pathlib.Path(__file__).resolve().parent
CIBLE = _ICI / "engine" / "runner" / "abilities" / "targeting.py"
TABLE = "TARGETING_OPTIONS_UNPORTED"

#: La banniere qui separe les entrees HORS-BLOC (en tete de table) du lot du pool spawnable.
BANNIERE = "LES ABILITIES ACTIVES DU POOL SPAWNABLE HORS REGISTRE"

FORMES = ["FLAGS-DIRECTS", "PRESET+FLAGS", "PRESET-SEUL", "STATIC-COPY"]
_RE_FORME = re.compile(r"@FORME\s+(" + "|".join(re.escape(f) for f in FORMES) + r")\b")

DEBUT = "    # >>> COMPTES DERIVES (#519) -- BLOC GENERE"
FIN = "    # <<< FIN COMPTES DERIVES"


def _cle_id(noeud):
    """L'id d'ability d'une cle du dict -- membre `ActiveAbilityType` ou entier nu."""
    if isinstance(noeud, ast.Attribute):
        return noeud.attr
    if isinstance(noeud, ast.Constant):
        return str(noeud.value)
    return ast.unparse(noeud)


def deriver(chemin=CIBLE):
    """Les comptes, DERIVES du fichier. Rend un dict de mesures."""
    texte = chemin.read_text(encoding="utf-8")
    lignes = texte.splitlines()
    arbre = ast.parse(texte)

    cles = None
    for noeud in ast.walk(arbre):
        if isinstance(noeud, ast.AnnAssign) and getattr(noeud.target, "id", None) == TABLE:
            cles = noeud.value.keys
            break
        if isinstance(noeud, ast.Assign) and any(
                getattr(t, "id", None) == TABLE for t in noeud.targets):
            cles = noeud.value.keys
            break
    if cles is None:
        raise SystemExit("ECHEC : `%s` introuvable dans %s" % (TABLE, chemin))

    marqueurs = []
    banniere = None
    for i, ligne in enumerate(lignes, 1):
        m = _RE_FORME.search(ligne)
        if m:
            marqueurs.append((i, m.group(1)))
        if BANNIERE in ligne:
            banniere = i
    if banniere is None:
        raise SystemExit("ECHEC : banniere de region introuvable")

    par_forme = {f: [] for f in FORMES}
    sans_forme = []
    hors_bloc, bloc = [], []
    for cle in cles:
        nom = _cle_id(cle)
        (hors_bloc if cle.lineno < banniere else bloc).append(nom)
        candidats = [f for (ln, f) in marqueurs if ln < cle.lineno]
        if candidats:
            par_forme[candidats[-1]].append(nom)
        else:
            sans_forme.append(nom)

    return {
        "total": len(cles),
        "hors_bloc": hors_bloc,
        "bloc": bloc,
        "par_forme": par_forme,
        "sans_forme": sans_forme,
    }


def bloc_attendu(mes):
    """Le BLOC GENERE, tel qu'il doit figurer dans l'en-tete de la table."""
    lignes = [
        DEBUT + " -- ne pas editer a la main.",
        "    #     Re-generer : `python scripts/python/probe_519_comptes_de_table.py --ecrire`",
        "    #     Garde : `tests/engine/test_519_comptes_derives_offline.py`. Ces nombres ne sont",
        "    #     PAS des faits de RE -- ils bougent a chaque face COMBAT portee, et c'est pour ca",
        "    #     qu'aucun d'eux n'est ecrit a la main.",
        "    #",
        "    #     len(%s) ......... %d" % (TABLE, mes["total"]),
        "    #       dont hors-bloc (tete de table) ..... %d" % len(mes["hors_bloc"]),
        "    #       dont bloc du pool (#433-r4) ........ %d" % len(mes["bloc"]),
        "    #",
        "    #     VENTILATION PAR FORME DE CTOR (dict ENTIER, hors-bloc compris) :",
    ]
    for f in FORMES:
        lignes.append("    #       %-14s ..................... %d" % (f, len(mes["par_forme"][f])))
    lignes.append("    #       (somme = %d)" % sum(len(v) for v in mes["par_forme"].values()))
    lignes.append(FIN)
    return lignes


def _bornes(lignes):
    """(debut, fin) 0-based du bloc genere, ou `None` s'il est absent."""
    d = f = None
    for i, ligne in enumerate(lignes):
        if ligne.startswith(DEBUT):
            d = i
        elif ligne.startswith(FIN):
            f = i
            break
    return (d, f) if d is not None and f is not None and f > d else None


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--ecrire", action="store_true", help="reecrit le bloc genere en place")
    args = ap.parse_args(argv)

    mes = deriver()
    attendu = bloc_attendu(mes)

    print("#519 -- COMPTES DERIVES de `%s`" % TABLE)
    print("total = %d  (hors-bloc %d + bloc %d)"
          % (mes["total"], len(mes["hors_bloc"]), len(mes["bloc"])))
    for f in FORMES:
        print("  %-14s %d" % (f, len(mes["par_forme"][f])))
    if mes["sans_forme"]:
        print("")
        print("SANS MARQUEUR @FORME (%d) : %s" % (len(mes["sans_forme"]), ", ".join(mes["sans_forme"])))
        print("Une entree sans marqueur n'est comptee dans AUCUNE forme -- la ventilation ne")
        print("sommerait plus au total. C'est un DEFAUT D'OUTIL, pas un vert.")
        return 2
    somme = sum(len(v) for v in mes["par_forme"].values())
    if somme != mes["total"]:
        print("INCOHERENT : la ventilation somme a %d pour un dict de %d" % (somme, mes["total"]))
        return 2

    texte = CIBLE.read_text(encoding="utf-8")
    lignes = texte.splitlines()
    bornes = _bornes(lignes)
    if bornes is None:
        print("")
        print("BLOC GENERE ABSENT de %s. Le voici, a inserer dans l'en-tete de la table :" % CIBLE.name)
        for l in attendu:
            print(l)
        return 1

    d, f = bornes
    actuel = lignes[d:f + 1]
    if actuel == attendu:
        print("")
        print("BLOC GENERE : A JOUR.")
        return 0

    if args.ecrire:
        nouvelles = lignes[:d] + attendu + lignes[f + 1:]
        CIBLE.write_text("\n".join(nouvelles) + "\n", encoding="utf-8")
        print("")
        print("BLOC GENERE : REECRIT (%d lignes)." % len(attendu))
        return 0

    print("")
    print("BLOC GENERE : PERIME. Ecrit dans le fichier :")
    for l in actuel:
        print("  |%s" % l)
    print("Derive du code :")
    for l in attendu:
        print("  |%s" % l)
    print("")
    print("Corriger : `python scripts/python/probe_519_comptes_de_table.py --ecrire`")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
