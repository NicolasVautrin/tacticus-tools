#!/usr/bin/env python
"""#485-r1-r1-r1 -- CLIQUET des acces ATTRIBUTAIRES a un module `engine.*`.

CE QU'IL GARDE
--------------
Un module lie a un nom local (`from engine.playbook import noncomparable as NC`,
`import engine.entities as E`) est lu par ATTRIBUT : `NC.NATIVE_PRIORITY`. Cette voie de
consommation ne laisse AUCUNE trace dans un recensement d'`ImportFrom` -- et c'est exactement
par la que le sweep #485-r1-r1 a retire `NATIVE_PRIORITY` / `native_priority` du baril
`engine.playbook.noncomparable`, qui les reclamait pourtant : `test_nc_priority_tiers_offline`
est tombe en `AttributeError`, APRES la vidange, sans qu'aucun controle statique ne l'ait vu.

Le probe MESURE le degat plutot que le risque : il resout chaque acces contre le module
REELLEMENT IMPORTE. Un `AttributeError` en puissance est donc rouge AVANT d'etre joue.

⚠ UN RECENSEUR NE PEUT PAS RENDRE ZERO SUR CE QU'IL NE VISITE PAS. La portee est TOUT `.py` de
`scripts/python/**` -- moteur, tests offline, tests `_live.py`, probes -- et la table des noms
locaux est celle de `migrate_485r1_barils_reexport._table_modules`, IMPORTEE et jamais recopiee
(deux implementations jumelles du meme predicat divergent : lecon #332).

TRI-ETAT
--------
    rc 0   VERT   -- aucun acces attributaire manquant
    rc 1   ROUGE  -- au moins un acces vise un attribut que le module n'expose pas
    rc 2   PAS MESURE -- recensement vide, ou un module cible non importable : un capteur muet
                        ne rend pas un zero.
"""
from __future__ import annotations

import argparse
import ast
import importlib
import sys
from collections import defaultdict
from pathlib import Path

#: Import de MODULE (forme B) et au NIVEAU MODULE : la table des noms locaux est le FOYER de
#: `migrate_485r1_barils_reexport`, jamais recopiee ici -- deux implementations jumelles du meme
#: predicat divergent (lecon #332). Aucun cycle : ce module n'importe rien de celui-ci.
import migrate_485r1_barils_reexport as MIG

#: Ce qui doit changer pour que ce cliquet puisse changer de verdict (#486-r12). Il etait le
#: DERNIER des 36 scripts de la banque a n'en porter aucun, et c'est ce trou qui rendait
#: `probe_486r12_declencheurs` ROUGE sur `master` -- signale par le port #491, hors de son
#: perimetre.
#:
#: DECLARE LARGE, et c'est une MESURE, pas une paresse : le recensement visite TOUT `.py` de
#: `scripts/python/**` (moteur, tests offline, tests `_live.py`, probes -- cf. `_fichiers()`), et
#: la table des noms locaux est IMPORTEE de `migrate_485r1_barils_reexport`, qui vit au meme
#: endroit. N'importe quel fichier ajoute, retire ou modifie sous cette racine change donc ce que
#: ce cliquet prouve. Sur-selectionner est sain ; sous-selectionner serait un faux vert.
#:
#: LES DEUX FORMES DE GLOB SONT NECESSAIRES : `**/` exige un segment, donc `scripts/python/**/*.py`
#: seul raterait `scripts/python/board.py`.
#:
#: `toujours: False` et non `True` : le perimetre s'ARRETE a `scripts/python/**`. Un changement de
#: build ou de `data/` ne peut pas retourner ce verdict -- au pire il rend un module non
#: importable, ce qui sort en `rc 2 PAS MESURE`, jamais en vert.
DECLENCHEUR = {
    "chemins": ("scripts/python/*.py", "scripts/python/**/*.py"),
    "build": False,
    "toujours": False,
    "raison": "Le recensement visite TOUT `.py` de `scripts/python/**` et resout chaque acces "
              "attributaire contre le module reellement importe ; la table des noms locaux est "
              "importee de `migrate_485r1_barils_reexport`, au meme endroit. Tout fichier ajoute, "
              "retire ou modifie sous cette racine change le verdict.",
}

ICI = Path(__file__).resolve().parent

EX_VERT, EX_ROUGE, EX_PAS_MESURE = 0, 1, 2

#: Noms locaux dont un acces attributaire ne dit RIEN du module : `self`, et les alias qu'un
#: fichier reassigne. On ne les traite pas specialement -- la table ne lie que des modules.

#: Attributs presents sur TOUT module : les demander n'est jamais un manque.
_DUNDER = {"__name__", "__doc__", "__file__", "__dict__", "__loader__", "__spec__",
           "__package__", "__path__", "__all__", "__builtins__", "__annotations__"}


def _fichiers(racine: Path):
    for p in sorted(racine.rglob("*.py")):
        if "__pycache__" in str(p) or p.resolve() == Path(__file__).resolve():
            continue
        yield p


def _gardes_hasattr(arbre: ast.Module) -> set[tuple[str, str]]:
    """(nom local, attr) dont le fichier TESTE l'existence -- `hasattr(M, "x")`, `getattr(M,
    "x", defaut)`. L'acces est alors conditionnel : l'absence est un cas PREVU, pas un manque."""
    out: set[tuple[str, str]] = set()
    for n in ast.walk(arbre):
        if not isinstance(n, ast.Call) or not isinstance(n.func, ast.Name):
            continue
        if n.func.id not in ("hasattr", "getattr"):
            continue
        if n.func.id == "getattr" and len(n.args) < 3:
            continue                                   # `getattr(M, "x")` LEVE : pas une garde
        if len(n.args) >= 2 and isinstance(n.args[0], ast.Name) and isinstance(
                n.args[1], ast.Constant) and isinstance(n.args[1].value, str):
            out.add((n.args[0].id, n.args[1].value))
    return out


def recenser(racine: Path = ICI) -> tuple[list[tuple[str, str, str]],
                                          list[tuple[str, str, str]]]:
    """(lectures, ecritures) d'un `<nom local lie a un module engine>.<attr>`.

    ⚠ LES DEUX SENS N'ONT PAS LE MEME CRITERE, et les confondre rend le probe FAUX dans les deux
    directions. Une LECTURE d'attribut absent est un `AttributeError` en puissance -- c'est le
    gisement garde ici. Une ECRITURE (`MV._x = stub`) CREE l'attribut : elle ne peut pas lever,
    mais un attribut ABSENT du module signale une mutation qui ne mord sur rien. Mesure du
    2026-08-06 : `probe_462_..._crush_steppable.py:259` substitue
    `_kill_steppable_remove_effects`, qui n'existe plus dans `movement.py` -- sa contre-epreuve
    `--mutate sans-retrait` est morte, en silence. Signale, non bloquant (dette anterieure).

    Un acces garde par `hasattr` / `getattr(..., defaut)` est ecarte : l'absence y est PREVUE."""
    lectures: list[tuple[str, str, str]] = []
    ecritures: list[tuple[str, str, str]] = []
    for p in _fichiers(racine):
        try:
            src = p.read_text(encoding="utf-8")
            arbre = ast.parse(src)
        except (OSError, SyntaxError, UnicodeDecodeError):
            continue
        mod = MIG.nom_module(p, racine)
        table = MIG._table_modules(arbre, mod, racine)
        if not table:
            continue
        gardes = _gardes_hasattr(arbre)
        for n in ast.walk(arbre):
            if not isinstance(n, ast.Attribute) or not isinstance(n.value, ast.Name):
                continue
            cible = table.get(n.value.id)
            if not cible or cible.split(".")[0] != "engine":
                continue
            if n.attr in _DUNDER or (n.value.id, n.attr) in gardes:
                continue
            site = "%s:%d" % (p.relative_to(racine).as_posix(), n.lineno)
            (lectures if isinstance(n.ctx, ast.Load) else ecritures).append(
                (cible, n.attr, site))
    return lectures, ecritures


def confronter(acces):
    """(manquants, sous_modules, muets). `muets` non vide ⇒ PAS MESURE."""
    if str(ICI) not in sys.path:
        sys.path.insert(0, str(ICI))
    manquants: list[tuple[str, str, str]] = []
    sous_modules: list[tuple[str, str, str]] = []
    muets: dict[str, str] = {}
    charges: dict[str, object] = {}
    for cible, attr, site in acces:
        if cible in muets:
            continue
        m = charges.get(cible)
        if m is None:
            try:
                m = importlib.import_module(cible)
            except Exception as exc:                       # noqa: BLE001 - tri-etat
                muets[cible] = "%s: %s" % (type(exc).__name__, exc)
                continue
            charges[cible] = m
        if hasattr(m, attr):
            continue
        #: un SOUS-MODULE non encore charge n'est pas un attribut du paquet : c'est une
        #: fragilite d'ordre de chargement, pas un symbole retire. Categorie a part.
        try:
            importlib.import_module("%s.%s" % (cible, attr))
        except Exception:                                  # noqa: BLE001
            manquants.append((cible, attr, site))
        else:
            sous_modules.append((cible, attr, site))
    return manquants, sous_modules, muets


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--verbeux", action="store_true",
                    help="liste aussi les acces vers un SOUS-MODULE (informatif).")
    a = ap.parse_args(argv)

    print("[485-r1-r1-r1] acces ATTRIBUTAIRES a un module `engine.*` -- racine %s" % ICI)
    lectures, ecritures = recenser()
    if not lectures:
        print("  recensement VIDE -- ce n'est pas un zero, c'est un capteur muet.")
        print("[485-r1-r1-r1] rc=%d -- PAS MESURE." % EX_PAS_MESURE)
        return EX_PAS_MESURE
    manquants, sous_modules, muets = confronter(lectures)
    orphelines, _, muets_e = confronter(ecritures)
    muets.update(muets_e)
    cibles = {c for c, _, _ in lectures}
    print("  lectures recensees : %d   ecritures : %d   modules vises : %d"
          % (len(lectures), len(ecritures), len(cibles)))

    if muets:
        print("\n  [0] modules NON IMPORTABLES -- la confrontation n'a pas eu lieu :")
        for cible, err in sorted(muets.items()):
            print("      %-60s %s" % (cible, err[:90]))
        print("[485-r1-r1-r1] rc=%d -- PAS MESURE." % EX_PAS_MESURE)
        return EX_PAS_MESURE

    if sous_modules:
        par_cle = defaultdict(list)
        for cible, attr, site in sous_modules:
            par_cle["%s.%s" % (cible, attr)].append(site)
        print("\n  [2] INFORMATIF -- acces a un SOUS-MODULE (%d) : present seulement si un tiers"
              % len(par_cle))
        print("      l'a deja charge. Fragilite d'ORDRE, pas un symbole retire.")
        if a.verbeux:
            for cle, sites in sorted(par_cle.items()):
                print("      %-64s %s" % (cle, ", ".join(sorted(set(sites))[:4])))

    if orphelines:
        par_cle = defaultdict(list)
        for cible, attr, site in orphelines:
            par_cle["%s.%s" % (cible, attr)].append(site)
        print("\n  [3] INFORMATIF -- SUBSTITUTION d'un attribut ABSENT du module (%d) : la"
              % len(par_cle))
        print("      mutation cree l'attribut, donc elle ne leve pas -- et ne mord sur rien.")
        for cle, sites in sorted(par_cle.items()):
            print("      %-64s %s" % (cle, ", ".join(sorted(set(sites)))))

    if manquants:
        par_cle = defaultdict(list)
        for cible, attr, site in manquants:
            par_cle["%s.%s" % (cible, attr)].append(site)
        print("\n  [1] ACCES MANQUANTS -- le module n'expose pas l'attribut lu :")
        for cle, sites in sorted(par_cle.items()):
            print("      %-64s %s" % (cle, ", ".join(sorted(set(sites)))))
        print("\n      C'est un `AttributeError` en puissance. Cause typique : une VIDANGE de")
        print("      baril qui n'a pas compte cette voie -- un `from pkg import sous_module`")
        print("      lie un MODULE, et tout ce qu'on lui demande ensuite est ATTRIBUTAIRE.")
        print("\n[485-r1-r1-r1] rc=%d -- ROUGE (%d acces, %d couple(s))."
              % (EX_ROUGE, len(manquants), len(par_cle)))
        return EX_ROUGE

    print("\n[485-r1-r1-r1] rc=%d -- VERT : tout acces attributaire resout." % EX_VERT)
    return EX_VERT


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
