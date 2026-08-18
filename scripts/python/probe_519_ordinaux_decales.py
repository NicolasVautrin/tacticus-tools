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
    ET l'ordinal cite est sa valeur sur AU MOINS UN build ARCHIVE,
    ET cette valeur n'est PAS sa valeur courante.

Un `Elevation(2)` ne le passe pas (l'`Elevation` de `UtilityType` valait 8, pas 2) : c'est bien une
SIGNATURE de decalage qu'on reconnait, pas une coincidence de nom.

⚠ LA SOURCE N'EST PLUS << LE BUILD PRECEDENT >>, ET C'EST LA REPARATION DE FOND (#10028). Ce probe
elisait son build de reference par une heuristique -- « celui qui partage le plus de NOMS avec le
courant » -- qui est STRUCTURELLEMENT BIAISEE : plus deux tables se ressemblent, plus le score est
haut, donc elle converge vers le build le MOINS informatif. Mesure du 2026-08-18 sur
`t6dpr4k06g` : `rnca9r7q6c` porte **0** membre decale et `gqfc5mff6c` en porte **73** -- et
l'heuristique elisait `rnca9r7q6c`. Le detecteur etait donc VACANT, et son zero ne disait rien de
la fraicheur des citations ; c'est `test_519_comptes_derives_offline.py::
test_le_detecteur_d_ordinaux_a_de_quoi_trouver` qui l'a dit en ROUGE, exactement ce pour quoi il
assertionne son propre non-vide.

La source est desormais la MEMOIRE ARCHIVEE de `probe_283` -- l'UNION des ordinaux portes par un
membre sur AU MOINS UN build archive (`probe_283_enum_ordinal_sweep.memoire_archivee`, #10023).
Cette union est MONOTONE : un build archive de plus ne peut qu'AJOUTER de la memoire, donc le
detecteur devient insensible a la cadence des builds -- et une citation perimee depuis DEUX builds
redevient visible, ce que la redaction precedente disait explicitement ne pas voir. On DELEGUE au
foyer plutot que de recopier la lecture : un cliquet qui reconstruit ce qu'il garde ne garde pas
ce qui tourne (meme lecon que `_olds()` de `test_enum_ordinal_ratchet_offline.py`).

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
if str(_ICI) not in sys.path:
    sys.path.insert(0, str(_ICI))

# Forme B (`import X` puis `X.f()`) -- la SEULE des trois qui reste mordable sous `monkeypatch`
# (cf. CLAUDE.md). C'est ce qui permet aux contre-epreuves de substituer la memoire archivee.
import probe_283_enum_ordinal_sweep as SW                                        # noqa: E402

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
    """(archives PORTEUSES de la table, courant). Le courant vient de `data/symbols/CURRENT`.

    ⚠ IL N'Y A PLUS D'ELECTION D'UN BUILD << PRECEDENT >>, et c'est le fond de #10028. L'ancienne
    version prenait « celui qui partage le plus de NOMS avec le courant », un critere qui
    RECOMPENSE la ressemblance : il elisait donc, par construction, le build sur lequel il n'y a
    RIEN a voir. On rend la LISTE des archives, et la memoire en est l'UNION."""
    courant = (SYMBOLES / "CURRENT").read_text(encoding="utf-8").strip()
    return SW.builds_avec_table_enums(), courant


def memoire_archivee() -> dict:
    """`{nom: frozenset(ordinaux portes sur AU MOINS UN build archive)}` -- DELEGUE au foyer.

    C'est `probe_283_enum_ordinal_sweep.memoire_archivee` (#10023) applique a l'enum suivi ici. On
    ne recopie pas la lecture : le foyer sait deja ecarter les archives sans `frida/enums.tsv` et
    celles dont l'estampille de provenance manque."""
    return SW.memoire_archivee(ENUM)


def membres_decales(vieux: dict, neuf: dict) -> list:
    """Les membres du build COURANT qui ont porte un AUTRE ordinal sur au moins une archive.

    FOYER PARTAGE avec `test_519_comptes_derives_offline.py` -- et ce partage est le cran : la
    comparaison `vieux[n] != neuf[n]`, ecrite a la main cote test, serait TOUJOURS vraie depuis que
    `vieux` rend un `frozenset` (un ensemble n'est jamais egal a un entier). Le test serait alors
    VERT ET VACANT, ce qui est precisement l'etat qu'il existe pour interdire."""
    return sorted(n for n, v in neuf.items()
                  if any(o != v for o in SW._ords(vieux.get(n))))


_BALAYAGE_CACHE = None


def balayer():
    """Les citations dont l'ordinal est celui du build PRECEDENT. Rend (liste, vieux, neuf, builds).

    MEMOISE (#941-r2) : DEUX tests de `test_519_comptes_derives_offline.py` l'appellent, l'un
    pour les citations perimees, l'autre pour attester qu'il EXISTE des membres decales -- deux
    verdicts, le meme balayage (3,90 s + 3,69 s mesures le 2026-08-11). Le releve ne depend que
    du disque (`data/symbols/**` et `engine/**`) ; les deux tables sont RE-CONSTRUITES a chaque
    appel, pour qu'un appelant ne puisse pas muter ce que verra le suivant.
    """
    global _BALAYAGE_CACHE
    if _BALAYAGE_CACHE is not None:
        trouves, vieux, neuf, blds = _BALAYAGE_CACHE
        return (list(trouves), dict(vieux) if vieux is not None else vieux,
                dict(neuf) if neuf is not None else neuf, blds)
    _BALAYAGE_CACHE = _balayer()
    return balayer()


def _balayer():
    """Le BALAYAGE, foyer unique -- appele une seule fois par `balayer`.

    `vieux` est desormais la MEMOIRE ARCHIVEE (`{nom: frozenset}`), plus la table d'UN build."""
    archives, cour = builds()
    neuf = _charger(cour)
    vieux = memoire_archivee() if archives else None
    trouves = []
    if not vieux or not neuf:
        return trouves, vieux, neuf, (tuple(archives), cour)
    for f in sorted(CORPUS.rglob("*.py")):
        texte = f.read_text(encoding="utf-8", errors="replace")
        for i, ligne in enumerate(texte.splitlines(), 1):
            for m in _RE_CITATION.finditer(ligne):
                nom, ordi = m.group(1), int(m.group(2))
                if nom in neuf and ordi in SW._ords(vieux.get(nom)) and neuf[nom] != ordi:
                    trouves.append((f, i, nom, ordi, neuf[nom]))
    return trouves, vieux, neuf, (tuple(archives), cour)


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

    trouves, vieux, neuf, (archives, cour) = balayer()
    print("#519 -- ORDINAUX DE `%s` CITES EN PROSE" % ENUM)
    if not vieux or not neuf:
        print("MESURE IMPOSSIBLE : enum introuvable pour %r ou %r." % (archives, cour))
        print("Ce n'est PAS un zero -- aucune conclusion ne se tire de cette sortie.")
        return 2
    decales = membres_decales(vieux, neuf)
    inserts = sorted(set(neuf) - set(vieux))
    print("archives %s -> %s | membres decales %d | membres neufs %s"
          % (", ".join(archives) or "(aucune)", cour, len(decales), inserts or "aucun"))
    if not decales:
        print("Aucun membre decale sur TOUTE la memoire archivee : ce probe ne peut RIEN trouver,")
        print("et un zero ci-dessous ne dit donc rien de la fraicheur des citations.")
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
