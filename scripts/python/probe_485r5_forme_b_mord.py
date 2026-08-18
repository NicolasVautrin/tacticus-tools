#!/usr/bin/env python
"""#485-r5 -- CLIQUET : les quatre imports hisses le sont en FORME B, et elle MORD.

CE QU'IL GARDE
--------------
#485-r5 a hisse quatre differes mesures GRATUITS. La doctrine impose la FORME B (`import X` puis
`X.foo()`) et pas la forme A (`from X import foo` au niveau module), pour une raison qui n'est PAS
esthetique : sous `monkeypatch.setattr("X.foo", stub)`, A NE MORD PAS -- le nom est resolu une fois
pour toutes a l'import, donc un patch pose apres est ignore EN SILENCE.

Le danger n'est pas theorique : c'est la cause exacte des 28 fichiers rouges de #484 et des 12 de
la famille #429-r1, et elle a RECIDIVE dans #485-r1-r1. Un hissage se relit mal -- rien, dans
`from ..entities.effects.base import BaseEffect` place en tete, ne signale qu'on vient de desarmer
un patcheur. Ce probe rend la propriete EXECUTABLE sur les quatre sites livres.

CE QU'IL NE GARDE PAS
---------------------
Il ne dit rien de la CLASSE du differe (porteur / gratuit) -- c'est `probe_485_imports_differes`,
ni des cycles -- c'est `probe_477r35_import_isole` et `probe_270r4r2_cycles_imports`. Il garde une
seule chose : la FORME de ce qui a ete hisse.

POURQUOI UN TEMOIN DE DISCRIMINATION (etape 0), ET POURQUOI IL EST OBLIGATOIRE
------------------------------------------------------------------------------
L'etape 1 verifie que le porteur ne porte PAS de copie gelee du symbole. Ecrite seule, elle serait
verte sur un mecanisme casse -- et surtout, elle serait verte sur un arbre ou la forme A serait,
elle aussi, mordante (si Python changeait de semantique, si le symbole etait un descripteur...).
L'etape 0 construit donc les DEUX formes dans un paquet jetable et EXIGE de les voir diverger :
A ne mord pas, B mord. Un test qui ne peut pas montrer sa propre discrimination ne prouve rien --
c'est la lecon << asserter son propre non-vide >>.

TRI-ETAT
--------
    rc 0   VERT   -- les quatre sites sont en forme B, et la forme B mord
    rc 1   ROUGE  -- un site a perdu sa forme B (ou le temoin ne discrimine plus)
    rc 2   PAS MESURE -- un module n'a pas pu etre charge / le registre ne decrit plus l'arbre.
                        JAMAIS un verdict : un capteur muet ne rend pas un zero.
"""
from __future__ import annotations

import ast
import importlib
import sys
import tempfile
from pathlib import Path

ICI = Path(__file__).resolve().parent
if str(ICI) not in sys.path:
    sys.path.insert(0, str(ICI))

EX_VERT, EX_ROUGE, EX_PAS_MESURE = 0, 1, 2

#: Les quatre sites hisses par #485-r5.
#:   (module PORTEUR, nom de la LIAISON de module, module CIBLE, symbole CONSOMME)
#: Le symbole consomme est celui que le corps lit a travers la liaison -- c'est LUI qu'une forme A
#: aurait gele. Le registre est ecrit a la main parce qu'il DECRIT une decision de tranche ; il est
#: confronte a l'arbre a chaque run (etape 1a), donc il ne peut pas se perimer en silence.
SITES = (
    ("engine.playbook.prediction.abilities", "CUSTODES",
     "engine.runner.abilities.custodes", "talons_used_abilities_level_from_effects"),
    ("engine.services.movement_query", "_effects_base",
     "engine.entities.effects.base", "BaseEffect"),
    ("engine.services.movement_query", "_components",
     "engine.runner.components", "unit_state_for_effects"),
    ("engine.services.movement_query", "_range_bonus",
     "engine.services.range_bonus", "MovementBonusContext"),
)


def _temoin_discrimine() -> tuple[bool, str]:
    """Construit les DEUX formes dans un paquet jetable : A doit NE PAS mordre, B doit mordre."""
    with tempfile.TemporaryDirectory() as d:
        racine = Path(d)
        pkg = racine / "p485r5"
        pkg.mkdir()
        (pkg / "__init__.py").write_text("", encoding="utf-8")
        (pkg / "cible.py").write_text("def foo():\n    return 'ORIGINE'\n", encoding="utf-8")
        (pkg / "forme_a.py").write_text(
            "from .cible import foo\n\n\ndef appeler():\n    return foo()\n", encoding="utf-8")
        (pkg / "forme_b.py").write_text(
            "from . import cible\n\n\ndef appeler():\n    return cible.foo()\n", encoding="utf-8")
        sys.path.insert(0, str(racine))
        try:
            cible = importlib.import_module("p485r5.cible")
            a = importlib.import_module("p485r5.forme_a")
            b = importlib.import_module("p485r5.forme_b")
            if a.appeler() != "ORIGINE" or b.appeler() != "ORIGINE":
                return False, "avant patch, les deux formes ne rendent pas l'ORIGINE"
            setattr(cible, "foo", lambda: "PATCHE")
            mord_a = a.appeler() == "PATCHE"
            mord_b = b.appeler() == "PATCHE"
        finally:
            sys.path.remove(str(racine))
            for m in [k for k in sys.modules if k.startswith("p485r5")]:
                del sys.modules[m]
    if mord_a:
        return False, "la forme A MORD : le temoin ne discrimine plus, l'etape 1 serait vide de sens"
    if not mord_b:
        return False, "la forme B NE MORD PAS : la propriete que ce probe garde n'existe plus"
    return True, "A ne mord pas, B mord -- les deux formes divergent bien"


def _noms_nus(mod_nom: str, symbole: str) -> int:
    """Combien de fois `symbole` apparait comme NOM NU (donc potentiellement lie en forme A).

    Lit l'AST : une occurrence en docstring ou en commentaire n'en est pas une. Zero est la seule
    valeur juste -- tout usage doit passer par `<liaison>.<symbole>`, qui est un `Attribute`.
    """
    chemin = ICI / Path(*mod_nom.split("."))
    src = (chemin.with_suffix(".py") if chemin.with_suffix(".py").is_file()
           else chemin / "__init__.py").read_text(encoding="utf-8")
    return sum(1 for n in ast.walk(ast.parse(src))
               if isinstance(n, ast.Name) and n.id == symbole)


def main() -> int:
    print("[485-r5] FORME B des quatre imports hisses -- et sa MORSURE")

    ok, detail = _temoin_discrimine()
    print("  [0] TEMOIN de discrimination : %s" % detail)
    if not ok:
        print("[485-r5] rc=%d -- ROUGE (temoin)." % EX_ROUGE)
        return EX_ROUGE

    if not SITES:
        print("  registre VIDE -- ce n'est pas un zero, c'est un capteur muet.")
        return EX_PAS_MESURE

    fautes: list[str] = []
    for porteur, liaison, cible, symbole in SITES:
        try:
            mp = importlib.import_module(porteur)
            mc = importlib.import_module(cible)
        except ImportError as e:
            print("  CHARGEMENT IMPOSSIBLE : %s / %s -> %s" % (porteur, cible, e))
            print("[485-r5] rc=%d -- PAS MESURE." % EX_PAS_MESURE)
            return EX_PAS_MESURE

        # (a) la LIAISON existe et designe bien le MODULE cible (le registre decrit l'arbre)
        lie = getattr(mp, liaison, None)
        if lie is not mc:
            fautes.append("%s.%s ne designe PAS le module %s (vu : %r)"
                          % (porteur, liaison, cible, lie))
            continue

        # (b) le porteur ne porte AUCUNE copie gelee du symbole -- c'est ca, << pas de forme A >>
        if hasattr(mp, symbole):
            fautes.append("%s porte une liaison DIRECTE `%s` : forme A, un patch de %s.%s serait "
                          "IGNORE" % (porteur, symbole, cible, symbole))
            continue
        nus = _noms_nus(porteur, symbole)
        if nus:
            fautes.append("%s lit `%s` comme NOM NU %d fois : la resolution n'est plus "
                          "attributaire" % (porteur, symbole, nus))
            continue

        # (c) MORSURE : un patch pose sur le module cible est vu a travers la liaison
        avant = getattr(mc, symbole)
        sentinelle = object()
        setattr(mc, symbole, sentinelle)
        try:
            vu = getattr(getattr(mp, liaison), symbole)
        finally:
            setattr(mc, symbole, avant)
        if vu is not sentinelle:
            fautes.append("%s ne VOIT PAS un patch de %s.%s" % (porteur, cible, symbole))
            continue
        print("  [1] OK  %-44s -> %s.%s" % (porteur, liaison, symbole))

    if fautes:
        print()
        for f in fautes:
            print("  FAUTE : %s" % f)
        print("  La forme B (`import X` puis `X.foo()`) est la SEULE des trois qui garde la")
        print("  morsure. Hisser en forme A ne leve aucune erreur -- il desarme le patcheur en")
        print("  SILENCE, et c'est pour ca que ce cliquet existe.")
        print("[485-r5] rc=%d -- ROUGE (%d faute(s) sur %d site(s))."
              % (EX_ROUGE, len(fautes), len(SITES)))
        return EX_ROUGE

    print("[485-r5] rc=%d -- VERT : %d/%d sites en forme B, morsure verifiee."
          % (EX_VERT, len(SITES), len(SITES)))
    return EX_VERT


if __name__ == "__main__":
    raise SystemExit(main())
