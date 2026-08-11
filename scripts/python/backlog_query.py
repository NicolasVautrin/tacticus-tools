"""Interroge `docs/rl/backlog.md` : residus OUVERTS, filtres par FOYER et par BLOCAGE.

POURQUOI
--------
Le backlog porte plusieurs centaines de residus ouverts. Choisir quoi dispatcher
suppose de repondre a deux questions que le fichier ne rend pas lisibles a l'oeil :
<< lesquels touchent tel code ? >> et << lesquels sont DEBLOQUES ? >>.

Le champ `FOYER:` (les fichiers que la tranche va EDITER) est justement l'axe qui
permet de grouper deux residus dans un meme agent sans collision -- il TRAVERSE les
familles : `#287` compte 10 residus sur 5 foyers disjoints, et inversement un meme
fichier est le foyer de residus de familles differentes.

TRI-ETAT, ET IL COMPTE ICI PLUS QU'AILLEURS
-------------------------------------------
`FOYER:` est retro-rempli AU FIL DE L'EAU, jamais en masse (une reecriture globale de
ce fichier entrerait en conflit avec toutes les PR en vol -- 90 % d'entre elles le
touchent). Une partie des lignes n'en a donc pas. Un residu SANS foyer n'est pas
<< hors perimetre >> : il est NON CLASSABLE, et il sort dans sa propre rubrique.
Le rabattre sur << ne correspond pas au filtre >> ferait disparaitre du travail reel.

Un repli heuristique (chercher des chemins dans le CORPS de la ligne) est disponible
via `--repli`, et ce qu'il trouve est ETIQUETE comme tel -- jamais confondu avec un
foyer DECLARE.
"""

from __future__ import annotations

import argparse
import os
import re
import sys

LIGNE = re.compile(r"^\|\s*(~~)?\s*(#[0-9]+(?:-r[0-9a-z]+)*)\s*(~~)?\s*\|(.*)$")
# Le champ est ecrit tantot nu (`FOYER: a.py, b.py`), tantot DECORE en markdown
# (`**FOYER:** \`a.py\`, \`b.py\` -- **BLOCAGE:** \`aucun\``). Les deux formes
# coexistent dans le fichier : tolerer les `**` et les backticks n'est pas du confort,
# c'est ce qui evite de rendre `?` sur des lignes parfaitement renseignees.
FOYER = re.compile(r"\**FOYER:?\**\s*:?\s*(.*?)(?:\s*[-—]*\s*\**BLOCAGE|$)", re.S)
BLOCAGE = re.compile(r"\**BLOCAGE:?\**\s*:?\s*[`\"']?([a-zA-Zé]+)")
CHEMIN = re.compile(r"[\w./-]+\.(?:py|ts|md|json|tsv)")


def charger(chemin: str):
    residus = []
    for brut in open(chemin, encoding="utf-8"):
        m = LIGNE.match(brut.rstrip("\n"))
        if not m:
            continue
        barre = bool(m.group(1) or m.group(3))
        cellules = m.group(4).split("|")
        corps = cellules[0] if cellules else ""
        mf = FOYER.search(corps)
        foyers = []
        if mf:
            for f in mf.group(1).split(","):
                f = f.strip().strip("`*\"' ").rstrip(".").strip()
                if f and f.lower() != "aucun":
                    foyers.append(f)
        mb = BLOCAGE.search(corps)
        residus.append({
            "num": m.group(2),
            "barre": barre,
            "corps": corps,
            "foyers": foyers,
            # TROIS etats, pas deux : le champ peut etre ABSENT (personne ne l'a
            # rempli -- NON CLASSABLE), ou present et valant `aucun` (declare :
            # residu documentaire ou d'outillage, c'est une REPONSE). Les confondre
            # ferait passer du travail non trie pour du travail sans foyer.
            "foyer_declare": mf is not None,
            "blocage": (mb.group(1).lower() if mb else None),
            "modele": cellules[1].strip() if len(cellules) > 1 else "",
        })
    return residus


def titre(corps: str, largeur: int = 96) -> str:
    t = re.sub(r"\s+", " ", corps).strip()
    t = re.sub(r"\*\*(.*?)\*\*", r"\1", t)
    t = t.split(" MESURE")[0].split(" MESURÉ")[0]
    return (t[:largeur] + "...") if len(t) > largeur else t


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--fichier", default=None)
    ap.add_argument("--foyer", default=None,
                    help="sous-chaine a chercher dans les FOYERS declares (ex: engine/)")
    ap.add_argument("--blocage", default=None, help="filtre sur BLOCAGE (ex: aucun)")
    ap.add_argument("--repli", action="store_true",
                    help="a defaut de FOYER declare, chercher des chemins dans le CORPS")
    ap.add_argument("--barres", action="store_true", help="inclure les residus barres (resolus)")
    ap.add_argument("--liste-foyers", action="store_true",
                    help="au lieu de lister les residus, compter les fichiers-foyers")
    args = ap.parse_args()

    chemin = args.fichier or os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "..", "..", "docs", "rl", "backlog.md")
    residus = charger(chemin)
    ouverts = [r for r in residus if args.barres or not r["barre"]]

    print("backlog : %d lignes de residu, %d OUVERTS, %d barres"
          % (len(residus), sum(1 for r in residus if not r["barre"]),
             sum(1 for r in residus if r["barre"])))

    avec = [r for r in ouverts if r["foyers"]]
    vide = [r for r in ouverts if r["foyer_declare"] and not r["foyers"]]
    sans = [r for r in ouverts if not r["foyer_declare"]]
    print("FOYER nommant des fichiers : %d | declare `aucun` (une REPONSE) : %d "
          "| champ ABSENT (NON CLASSABLE, pas 'hors filtre') : %d"
          % (len(avec), len(vide), len(sans)))

    if args.liste_foyers:
        compte = {}
        for r in avec:
            for f in r["foyers"]:
                compte[f] = compte.get(f, 0) + 1
        print("")
        print("fichiers-foyers partages par plusieurs residus :")
        for f, n in sorted(compte.items(), key=lambda kv: -kv[1]):
            if n > 1:
                print("  %2d  %s" % (n, f))
        print("")
        print("total fichiers-foyers distincts : %d" % len(compte))
        return 0

    retenus, replis = [], []
    for r in ouverts:
        if args.blocage and (r["blocage"] or "") != args.blocage.lower():
            continue
        if args.foyer:
            if r["foyers"]:
                if any(args.foyer in f for f in r["foyers"]):
                    retenus.append(r)
            elif args.repli and args.foyer in r["corps"]:
                trouves = [c for c in CHEMIN.findall(r["corps"]) if args.foyer in c]
                if trouves:
                    r["_repli"] = sorted(set(trouves))[:3]
                    replis.append(r)
        else:
            retenus.append(r)

    def montrer(lot, etiquette):
        if not lot:
            return
        print("")
        print("=== %s : %d ===" % (etiquette, len(lot)))
        for r in lot:
            b = r["blocage"] or "?"
            print("  %-12s [%-8s] %s" % (r["num"], b, titre(r["corps"])))
            src = r["foyers"] if r["foyers"] else r.get("_repli", [])
            for f in src[:4]:
                print("                          %s" % f)

    montrer(retenus, "FOYER DECLARE correspondant" if args.foyer else "residus ouverts")
    if args.repli:
        montrer(replis, "REPLI -- chemin trouve dans le CORPS, foyer NON declare")

    if args.foyer:
        print("")
        print("BILAN : %d par foyer declare | %d par repli | %d sans foyer NON EXAMINES"
              % (len(retenus), len(replis), len(sans) - len(replis)))
        if not args.repli and sans:
            print("  ⚠ %d residus SANS FOYER n'ont pas ete examines -- relancer avec --repli"
                  % len(sans))
    return 0


if __name__ == "__main__":
    sys.exit(main())
