#!/usr/bin/env python
"""#485-r1-r1 -- CHIFFRER ce qu'il faudrait pour supprimer les differes PORTEURS restants.

MESURE, PAS EXECUTION. Le sweep des barils fait tomber les differes GRATUITS ; ceux qui
restent sont PORTEURS -- hisser fermerait leur cycle. `CLAUDE.md` prescrit trois leviers,
DANS CET ORDRE : (1) DEPLACER le code partagé vers un module que la cascade ne re-entre pas,
(2) ALLEGER l'`__init__` du paquet, (3) DIFFERER, en dernier. Ce probe repond a : pour
chacun des porteurs, LEQUEL des deux premiers leviers s'applique, et ou est le gisement ?

LE DISCRIMINANT EST LE CHEMIN DU CYCLE, PAS LE COMPTE DES PORTEURS
-------------------------------------------------------------------
Pour un differe `M -> X`, on cherche un chemin `X -> ... -> M` dans le graphe des imports
MODULE-LEVEL, augmente de l'arete `module -> paquet PARENT` (Python execute l'`__init__` de
chaque ancetre, qu'on l'ecrive ou non -- sans cette arete, un lot filtre a casse l'import de
405 des 409 modules, mesure #270-r4-r2-r2).

    PAR_UN_PAQUET   TOUS les chemins traversent un `__init__.py`. Alleger cet `__init__`
                    (levier 2) suffirait -- aucun code a deplacer.
    MODULE_A_MODULE il existe un chemin qui ne traverse AUCUN paquet : c'est une dependance
                    mutuelle REELLE entre deux feuilles. Seul le levier 1 la coupe.
    SANS_CHEMIN     aucun chemin trouve dans le graphe STATIQUE alors que la mesure en
                    process frais dit PORTEUR. Ce n'est PAS un vert : c'est un angle mort du
                    graphe declare (`importlib`, import dans un `__init__` d'un tiers, ...),
                    et il est compte a part plutot qu'assimile a l'un des deux autres.

⚠ CE PROBE NE CONCLUT PAS QU'UN DEPLACEMENT EST SUR. Il dit quel levier serait a tenter, et
sur quel foyer. Le cout reel d'un deplacement (qui d'autre lit le symbole, ce qu'il tire
lui-meme) n'est pas mesure ici -- et ne doit pas etre devine.

TRI-ETAT
--------
    rc 0   la ventilation a abouti
    rc 2   PAS MESURE -- classification porteur/gratuit non aboutie, ou perimetre vide

ASCII only (console Windows cp1252).
"""
from __future__ import annotations

import argparse
import sys
from collections import defaultdict, deque
from pathlib import Path

ICI = Path(__file__).resolve().parent
EX_VERT, EX_ROUGE, EX_PAS_MESURE = 0, 1, 2


def _est_paquet(mod: str, racine: Path) -> bool:
    return (racine / Path(*mod.split("."))).is_dir()


def _graphe(racine: Path):
    """Arêtes module-level + arete vers le paquet PARENT."""
    import probe_270r4r2_cycles_imports as CY

    ml, _tous, _dif = CY.construire(racine / "engine")
    g: dict[str, set[str]] = defaultdict(set)
    noeuds = set(ml)
    for k, v in ml.items():
        g[k] |= set(v)
        noeuds |= set(v)
    for n in list(noeuds):
        if "." in n:
            g[n].add(n.rsplit(".", 1)[0])
    return g


def _chemin_sans_paquet(g, depart: str, arrivee: str, racine: Path) -> list[str] | None:
    """Un chemin `depart -> ... -> arrivee` dont AUCUN noeud intermediaire n'est un paquet.

    BFS restreint : on n'entre jamais dans un noeud-paquet (sauf si c'est l'arrivee)."""
    if depart == arrivee:
        return [depart]
    vus, file = {depart}, deque([(depart, [depart])])
    while file:
        n, chemin = file.popleft()
        for w in sorted(g.get(n, ())):
            if w == arrivee:
                return chemin + [w]
            if w in vus or _est_paquet(w, racine):
                continue
            vus.add(w)
            file.append((w, chemin + [w]))
    return None


def _chemin_quelconque(g, depart: str, arrivee: str) -> list[str] | None:
    if depart == arrivee:
        return [depart]
    vus, file = {depart}, deque([(depart, [depart])])
    while file:
        n, chemin = file.popleft()
        for w in sorted(g.get(n, ())):
            if w == arrivee:
                return chemin + [w]
            if w in vus:
                continue
            vus.add(w)
            file.append((w, chemin + [w]))
    return None


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--detail", action="store_true", help="imprime un chemin par porteur")
    ap.add_argument("--top", type=int, default=15, help="taille des palmares")
    a = ap.parse_args(argv)

    print("[485-r1-r1] leviers des differes PORTEURS restants")
    try:
        import probe_485_imports_differes as P485
    except ImportError:
        print("PAS MESURE : `probe_485_imports_differes` introuvable.")
        return EX_PAS_MESURE
    differes = P485.recenser()
    if not differes:
        print("  recensement VIDE -- capteur muet, pas un zero.")
        return EX_PAS_MESURE
    classe = P485.classer(differes)
    if classe is None:
        print("PAS MESURE : la classification porteur/gratuit n'a pas abouti.")
        return EX_PAS_MESURE
    porteurs, gratuits = classe
    print("  recenses : %d   PORTEURS : %d   GRATUITS : %d"
          % (len(differes), len(porteurs), len(gratuits)))

    g = _graphe(ICI)
    par_classe: dict[str, list] = defaultdict(list)
    for mod, cible, ligne, _raison in porteurs:
        direct = _chemin_sans_paquet(g, cible, mod, ICI)
        if direct is not None:
            par_classe["MODULE_A_MODULE"].append((mod, cible, ligne, direct))
        elif _chemin_quelconque(g, cible, mod) is not None:
            par_classe["PAR_UN_PAQUET"].append(
                (mod, cible, ligne, _chemin_quelconque(g, cible, mod)))
        else:
            par_classe["SANS_CHEMIN"].append((mod, cible, ligne, []))

    print("\n  VENTILATION (partition des %d porteurs) :" % len(porteurs))
    for cle in ("PAR_UN_PAQUET", "MODULE_A_MODULE", "SANS_CHEMIN"):
        lot = par_classe.get(cle, [])
        pct = (100.0 * len(lot) / len(porteurs)) if porteurs else 0.0
        print("      %-16s %4d   %5.1f %%" % (cle, len(lot), pct))
    total = sum(len(v) for v in par_classe.values())
    print("      %-16s %4d   (partition %s)"
          % ("TOTAL", total, "OUI" if total == len(porteurs) else "NON -- INCOHERENT"))

    print("\n  GISEMENT -- paquets dont l'`__init__` ferme le plus de cycles (levier 2) :")
    par_paquet: dict[str, int] = defaultdict(int)
    for _mod, _cible, _l, chemin in par_classe.get("PAR_UN_PAQUET", []):
        for n in chemin[1:-1]:
            if _est_paquet(n, ICI):
                par_paquet[n] += 1
    for nom, n in sorted(par_paquet.items(), key=lambda kv: (-kv[1], kv[0]))[:a.top]:
        print("      %-52s %4d" % (nom, n))
    if not par_paquet:
        print("      (aucun -- tous les cycles sont module-a-module)")

    print("\n  GISEMENT -- modules CIBLES les plus frequents (tous porteurs) :")
    par_cible: dict[str, int] = defaultdict(int)
    for _mod, cible, _l, _c in [x for v in par_classe.values() for x in v]:
        par_cible[cible] += 1
    palmares = sorted(par_cible.items(), key=lambda kv: (-kv[1], kv[0]))
    cumul = 0
    for nom, n in palmares[:a.top]:
        cumul += n
        print("      %-52s %4d  (cumul %4.1f %%)"
              % (nom, n, 100.0 * cumul / max(1, len(porteurs))))
    print("      %d cible(s) distincte(s) pour %d porteurs -- une distribution DIFFUSE"
          % (len(palmares), len(porteurs)))
    print("      interdit un second sweep de masse : il n'y a pas de foyer dominant.")

    if a.detail:
        print("\n  DETAIL :")
        for cle in ("MODULE_A_MODULE", "PAR_UN_PAQUET", "SANS_CHEMIN"):
            for mod, cible, ligne, chemin in sorted(par_classe.get(cle, [])):
                print("      [%s] %s:%d -> %s" % (cle, mod, ligne, cible))
                if chemin:
                    print("           cycle : %s" % " -> ".join(chemin))
    return EX_VERT


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
