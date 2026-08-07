"""#519 -- LES ORDINAUX D'ENUM CITES EN PROSE, PERIMES PAR UN CHANGEMENT DE BUILD.

LE MOTIF, deuxieme forme. La premiere (`probe_519_temoins_de_camp.py`) est alimentee par NOTRE
cadence de portage ; celle-ci l'est par le JEU. Une seule insertion dans un enum natif decale tous
les membres qui la suivent, et chaque ordinal recopie en commentaire devient faux -- en silence,
puisqu'aucun code ne le lit.

MESURE (`gqfc5mff6c` -> `rnca9r7q6c`) : `IdunBattle.Configuration.UtilityType` a recu UNE insertion,
`AttackTile` en 8, qui a decale de +1 les **73** membres suivants. Resultat dans `engine/**` :
**24** citations de prose encore ecrites avec l'ordinal de l'ancien build, dont le `Damage(34)` que
`#504-r1` avait signale sur un seul fichier.

LE DISCRIMINANT, ET IL EST L'ENJEU. Un premier balayage a compare « nom d'enum + ordinal » et a
rendu **5 faux positifs sur 40** : `Attack(0)` est un `StatType`, `Ranged(2)` un `AttackType`,
`Elevation(2)` un masque `ObscuringType`... Le NOM NE TRANCHE PAS L'ENUM -- exactement ce que la
doctrine du depot dit des ids d'ability, transpose ici. Le critere retenu est plus fort et il est
SANS accusation possible a tort :

    le nom est un membre de l'enum sur le build COURANT,
    ET l'ordinal cite est EXACTEMENT sa valeur sur le build PRECEDENT,
    ET les deux valeurs different.

Un `Elevation(2)` ne le passe pas (l'`Elevation` de `UtilityType` valait 8, pas 2) : c'est bien une
SIGNATURE de decalage qu'on reconnait, pas une coincidence de nom. Le prix de cette rigueur est
qu'on ne voit QUE les citations perimees par le DERNIER changement de build ; une citation perimee
depuis deux builds n'est pas vue, et c'est dit plutot que tu.

MODES :
    --verifier (defaut) liste les citations perimees. rc 1 s'il y en a.
    --ecrire            les reecrit (substitution du seul ordinal, le nom est deja juste).

ASCII only.
"""
from __future__ import annotations

import argparse
import io
import pathlib
import re
import sys

_ICI = pathlib.Path(__file__).resolve().parent
_RACINE = _ICI.parent.parent
SYMBOLES = _RACINE / "data" / "symbols"
CORPUS = _ICI / "engine"

#: L'enum suivi, et les deux builds a confronter. Le build COURANT est lu dans `data/symbols/CURRENT`
#: (jamais recopie) ; le PRECEDENT est celui d'avant lui dans l'ordre du repertoire.
ENUM = "IdunBattle.Configuration.UtilityType"

_RE_CITATION = re.compile(r"\b([A-Z][A-Za-z0-9_]{3,})\((\d{1,4})\)")


def _charger(build):
    """`{nom: ordinal}` de l'enum suivi, pour un build donne."""
    f = SYMBOLES / build / "frida" / "enums.tsv"
    if not f.exists():
        return None
    for ligne in io.open(f, encoding="utf-8"):
        if ligne.startswith(ENUM + "\t"):
            return dict((kv.split("=")[1], int(kv.split("=")[0]))
                        for kv in ligne.split("\t")[1].strip().split(","))
    return None


def builds():
    """(precedent, courant). Le courant vient de `data/symbols/CURRENT`, jamais d'une constante."""
    courant = (SYMBOLES / "CURRENT").read_text(encoding="utf-8").strip()
    autres = sorted(d.name for d in SYMBOLES.iterdir()
                    if d.is_dir() and d.name != courant and (d / "frida" / "enums.tsv").exists())
    if not autres:
        return None, courant
    # Le build PRECEDENT est celui dont l'enum diffère du courant par une insertion -- a defaut
    # d'horodatage fiable, on prend celui qui partage le plus de NOMS avec lui.
    neuf = _charger(courant) or {}
    meilleur, score = None, -1
    for b in autres:
        v = _charger(b)
        if v is None:
            continue
        s = len(set(v) & set(neuf))
        if s > score:
            meilleur, score = b, s
    return meilleur, courant


def balayer():
    """Les citations dont l'ordinal est celui du build PRECEDENT. Rend (liste, vieux, neuf, builds)."""
    prec, cour = builds()
    vieux, neuf = _charger(prec) if prec else None, _charger(cour)
    trouves = []
    if not vieux or not neuf:
        return trouves, vieux, neuf, (prec, cour)
    for f in sorted(CORPUS.rglob("*.py")):
        texte = f.read_text(encoding="utf-8", errors="replace")
        for i, ligne in enumerate(texte.splitlines(), 1):
            for m in _RE_CITATION.finditer(ligne):
                nom, ordi = m.group(1), int(m.group(2))
                if nom in neuf and vieux.get(nom) == ordi and neuf[nom] != ordi:
                    trouves.append((f, i, nom, ordi, neuf[nom]))
    return trouves, vieux, neuf, (prec, cour)


def _reecrire(trouves):
    """Substitue `<Nom>(<vieux>)` -> `<Nom>(<neuf>)`. Le NOM est deja juste : seul l'ordinal bouge."""
    par_fichier = {}
    for f, _i, nom, vieux, neuf in trouves:
        par_fichier.setdefault(f, set()).add((nom, vieux, neuf))
    for f, subs in par_fichier.items():
        texte = f.read_text(encoding="utf-8")
        for nom, vieux, neuf in subs:
            texte = texte.replace("%s(%d)" % (nom, vieux), "%s(%d)" % (nom, neuf))
        f.write_text(texte, encoding="utf-8")
    return len(par_fichier)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--ecrire", action="store_true", help="reecrit les ordinaux perimes")
    args = ap.parse_args(argv)

    trouves, vieux, neuf, (prec, cour) = balayer()
    print("#519 -- ORDINAUX DE `%s` CITES EN PROSE" % ENUM)
    if not vieux or not neuf:
        print("MESURE IMPOSSIBLE : enum introuvable pour %r ou %r." % (prec, cour))
        print("Ce n'est PAS un zero -- aucune conclusion ne se tire de cette sortie.")
        return 2
    decales = [n for n in neuf if n in vieux and vieux[n] != neuf[n]]
    inserts = sorted(set(neuf) - set(vieux))
    print("builds : %s -> %s | membres decales %d | insertions %s"
          % (prec, cour, len(decales), inserts or "aucune"))
    if not decales:
        print("Aucun membre decale entre ces deux builds : ce probe ne peut RIEN trouver, et un")
        print("zero ci-dessous ne dit donc rien de la fraicheur des citations.")
    print("citations PERIMEES : %d" % len(trouves))
    for f, i, nom, o, n in trouves:
        print("  %s:%d  %s(%d) -> %s(%d)" % (f.relative_to(_ICI).as_posix(), i, nom, o, nom, n))
    if trouves and args.ecrire:
        k = _reecrire(trouves)
        print("")
        print("REECRIT dans %d fichier(s)." % k)
        return 0
    return 1 if trouves else 0


if __name__ == "__main__":
    raise SystemExit(main())
