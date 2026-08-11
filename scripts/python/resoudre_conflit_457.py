"""Resout les conflits des caches #457 (`ratchets-457-*.json`) PAR LES ETAGES GIT.

POURQUOI CET OUTIL EXISTE
-------------------------
Ces caches sont des dicts indexes par fichier de test. Deux branches qui mesurent
chacune une empreinte entrent en conflit a chaque merge -- c'est arrive a CHACUN des
merges du 2026-08-11. Choisir un cote revient a PERDRE une empreinte : le test
concerne se rejoue alors TOUJOURS (au mieux), ou sort du recensement (au pire).

POURQUOI ON NE RECOLLE PAS LES MARQUEURS
----------------------------------------
Recoller le texte des hunks est fragile et faux :
* git coupe le hunk AVANT l'accolade fermante, qui est du contexte PARTAGE -- coller
  les deux cotes bout a bout produit un JSON INVALIDE ;
* un hunk peut tomber A L'INTERIEUR de la valeur d'une seule cle, auquel cas les deux
  cotes ne sont pas deux ajouts mais DEUX MESURES CONCURRENTES de la meme empreinte.

Git conserve les deux fichiers ENTIERS (`:2:` = notre cote, `:3:` = le leur). On les
lit comme du JSON et on fusionne des STRUCTURES, jamais des lignes.

LA REGLE D'ARBITRAGE, ET ELLE EST MOTIVEE
-----------------------------------------
* cle d'un seul cote            -> on la prend ;
* cle des deux cotes, identique -> rien a decider ;
* cle des deux cotes, DIFFERENTE -> on prefere l'empreinte dont les chemins sont
  NORMALISES. Un chemin qui contient `..` ne peut matcher aucun chemin de fichier
  change : l'empreinte est inerte, le test se rejoue toujours. C'est le defaut
  << declencheur trop etroit >> deja diagnostique (#931). A defaut de discriminant,
  on garde la mesure la PLUS RECENTE (`_at`), et on l'ANNONCE.

Aucune ecriture tant que le resultat n'est pas du JSON valide contenant l'UNION des
cles des deux cotes.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys

DEFAUT = ("scripts/ratchets-457-durations.json", "scripts/ratchets-457-footprints.json")


def _etage_brut(chemin: str, n: int, depot: str):
    """Texte de l'etage git `n` (2 = nous, 3 = eux). None si absent."""
    p = subprocess.run(["git", "show", ":%d:%s" % (n, chemin)],
                       cwd=depot, capture_output=True, text=True)
    return None if p.returncode != 0 else p.stdout


def _etage(chemin: str, n: int, depot: str):
    brut = _etage_brut(chemin, n, depot)
    if brut is None:
        return None
    try:
        return json.loads(brut)
    except ValueError:
        return None


def _serialiser(obj) -> str:
    return json.dumps(obj, indent=1, ensure_ascii=False, sort_keys=True) + "\n"


def _format_fidele(chemin: str, depot: str):
    """Ma serialisation reproduit-elle a l'octet pres ce que le generateur ecrit ?

    Sans ce controle, resoudre un conflit de 2 cles REECRIRAIT les 7500 lignes du
    cache -- un diff illisible, et un conflit garanti pour toute PR en vol. On le
    verifie sur l'etage 2, dont on a le texte EXACT tel qu'il est versionne.
    """
    brut = _etage_brut(chemin, 2, depot)
    if brut is None:
        return None, "etage 2 illisible"
    try:
        obj = json.loads(brut)
    except ValueError as exc:
        return None, "etage 2 non JSON (%s)" % exc
    rendu = _serialiser(obj)
    if rendu == brut:
        return True, "identique a l'octet pres"
    a, b = brut.split("\n"), rendu.split("\n")
    for i, (x, y) in enumerate(zip(a, b)):
        if x != y:
            return False, "1re divergence ligne %d : %r vs %r" % (i + 1, x[:60], y[:60])
    return False, "longueurs differentes (%d vs %d lignes)" % (len(a), len(b))


def _a_des_chemins_non_normalises(valeur) -> bool:
    if isinstance(valeur, str):
        return ".." in valeur.split("/")
    if isinstance(valeur, dict):
        return any(_a_des_chemins_non_normalises(v) for v in valeur.values())
    if isinstance(valeur, list):
        return any(_a_des_chemins_non_normalises(v) for v in valeur)
    return False


def _fusionner(a, b, chemin_cle="", journal=None):
    """Fusion recursive de deux dicts. `a` = notre cote, `b` = le leur."""
    if journal is None:
        journal = []
    if not (isinstance(a, dict) and isinstance(b, dict)):
        return a, journal

    sortie = {}
    for cle in sorted(set(a) | set(b)):
        plein = "%s/%s" % (chemin_cle, cle) if chemin_cle else cle
        if cle not in b:
            sortie[cle] = a[cle]
        elif cle not in a:
            sortie[cle] = b[cle]
        elif a[cle] == b[cle]:
            sortie[cle] = a[cle]
        elif isinstance(a[cle], dict) and isinstance(b[cle], dict) and "_at" not in a[cle]:
            sortie[cle], _ = _fusionner(a[cle], b[cle], plein, journal)
        else:
            sale_a = _a_des_chemins_non_normalises(a[cle])
            sale_b = _a_des_chemins_non_normalises(b[cle])
            if sale_a != sale_b:
                gagnant, motif = (b[cle], "leur") if sale_a else (a[cle], "notre")
                journal.append("  ARBITRE %s -> cote %s (l'autre porte des chemins `..` INERTES)"
                               % (plein, motif))
            else:
                at_a = a[cle].get("_at", 0) if isinstance(a[cle], dict) else 0
                at_b = b[cle].get("_at", 0) if isinstance(b[cle], dict) else 0
                gagnant = a[cle] if at_a >= at_b else b[cle]
                journal.append("  ARBITRE %s -> mesure la plus RECENTE (_at %d vs %d) "
                               "-- aucun discriminant de qualite" % (plein, at_a, at_b))
            sortie[cle] = gagnant
    return sortie, journal


def resoudre(chemin: str, depot: str) -> int:
    if not os.path.isfile(os.path.join(depot, chemin)):
        print("  %s : ABSENT" % chemin)
        return 1

    nous = _etage(chemin, 2, depot)
    eux = _etage(chemin, 3, depot)
    if nous is None or eux is None:
        texte = open(os.path.join(depot, chemin), encoding="utf-8").read()
        if "<<<<<<< " not in texte:
            print("  %s : aucun conflit" % chemin)
            return 0
        print("  %s : etages git ILLISIBLES (nous=%s eux=%s) -- RIEN ECRIT"
              % (chemin, nous is not None, eux is not None))
        return 1

    fusion, journal = _fusionner(nous, eux)

    def _cles(o, acc):
        if isinstance(o, dict):
            for k, v in o.items():
                acc.add(k)
                _cles(v, acc)
    attendues, obtenues = set(), set()
    _cles(nous, attendues)
    _cles(eux, attendues)
    _cles(fusion, obtenues)
    perdues = sorted(attendues - obtenues)
    if perdues:
        print("  %s : %d cle(s) PERDUE(S) (%s...) -- RIEN ECRIT"
              % (chemin, len(perdues), ", ".join(perdues[:3])))
        return 1

    fidele, detail = _format_fidele(chemin, depot)
    if fidele is not True:
        print("  %s : ma serialisation NE REPRODUIT PAS le format versionne (%s)"
              % (chemin, detail))
        print("     -> ecrire reformaterait TOUT le fichier. RIEN ECRIT.")
        return 1

    texte = _serialiser(fusion)
    try:
        json.loads(texte)
    except ValueError as exc:
        print("  %s : re-serialisation INVALIDE (%s) -- RIEN ECRIT" % (chemin, exc))
        return 1

    open(os.path.join(depot, chemin), "w", encoding="utf-8", newline="\n").write(texte)
    n_nous, n_eux = len(nous), len(eux)
    print("  %s : UNION OK -- %d cles (notre cote %d, le leur %d), JSON valide"
          % (chemin, len(fusion), n_nous, n_eux))
    for l in journal:
        print(l)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("fichiers", nargs="*", help="caches (defaut: les deux caches #457)")
    ap.add_argument("--depot", default=".", help="racine du depot / worktree")
    args = ap.parse_args()

    rc = 0
    for f in (args.fichiers or list(DEFAUT)):
        rc |= resoudre(f, args.depot)
    return rc


if __name__ == "__main__":
    sys.exit(main())
