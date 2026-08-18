"""#10031 -- CLIQUET : une SUBSTITUTION posee par un instrument de `#381-r4` doit MORDRE.

POURQUOI CE FICHIER EXISTE
--------------------------
Le 2026-08-05, `492c722f` (« hisser 624 imports differes d'engine/ au niveau module ») a passe
`make_can_continue` et `is_like_flying` de la forme C a la FORME A dans
`engine/services/movement_query.py`. CLAUDE.md dit deja ce que ca fait -- « hisser en forme A fait
passer de MORD a NE MORD PAS » -- mais rien ne le CONSTATAIT au site de mesure. Consequence
mesuree, sur les trois instruments qui visent ces deux noms :

  * `tests/engine/runner/test_381r4_imperative_collapses_offline.py` -- joue par le cliquet offline,
    donc il a rougi tout de suite. Il a ete repare AU SITE DE MESURE (patcher aussi le
    consommateur), ce qui l'a reverdi et a laisse la cause en place ;
  * `tests/engine/runner/test_381r4_imperative_collapses_live.py` -- ROUGE 13 jours, sur un message
    qui accusait la GEOMETRIE (« aucune geometrie ou le gate #131 change l'atterrissage sur C2_26 --
    le test ne prouverait rien ») ;
  * `probe_381r4_imperative_collapses.py` -- `rc 1`, « le bras NE DISCRIMINE PAS », meme fausse
    accusation. Aucun cliquet ne joue les probes : personne ne l'a vu.

`#10031` repare le FOYER (retour en forme B, liaison de MODULE) et pose ce cliquet, pour que le
prochain hissage soit vu par une MESURE et non par la lecture d'un message trompeur.

DEUX ETAGES, ET ILS NE TOMBENT PAS POUR LA MEME RAISON
------------------------------------------------------
E1 L'EFFET   -- la mutation `no-gate` doit CHANGER une sortie de site. C'est l'invariant de bout en
                bout : il tombe quel que soit le MECANISME du desarmement (hissage, ref gelee dans
                un defaut d'argument, cache de closure...). Il ne dit pas OU c'est casse.
E2 LA CAUSE  -- les liaisons FIGEES (forme A) sur les noms substitues, DERIVEES : les couples le
                sont des instruments eux-memes (`cibles_substituees`, jamais une liste ecrite a la
                main), et les liaisons le sont d'un balayage AST de tout `engine/**` -- donc E2 voit
                aussi un module qu'AUCUNE passe ne charge, ce que la lecture runtime ne peut pas.

E2 est un RATCHET, pas un invariant a zero : DEUX liaisons figees subsistent hors du chemin de
`#381-r4` (`engine/ai/state_bridge.py` pour `make_can_continue`, `engine/runner/operations/
movement.py` pour `is_like_flying`). Elles sont REELLES -- tout patcheur qui exercerait CES
chemins-la serait muet -- mais les reparer changerait la morsure de mesures qui appartiennent a
d'autres tranches (#448, #381-r1), qu'il faut re-jouer avant. Elles sont donc ATTESTEES, nommees,
et le fichier d'attestation ne doit que DECROITRE. Toute liaison NEUVE rougit.

ASCII only (console Windows cp1252).
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

_PY = Path(__file__).resolve().parents[3]
if str(_PY) not in sys.path:
    sys.path.insert(0, str(_PY))

from morsure_substitution import (cibles_substituees, liaisons_figees_statiques)  # noqa: E402

#: Ce qui doit changer pour que ce FICHIER de test puisse changer de verdict (#486-r15).
DECLENCHEUR = {
    "chemins": (
        "scripts/python/conftest.py", "scripts/python/tests/conftest.py",
        "scripts/python/tests/engine/conftest.py",
        "scripts/python/green_skip_guard.py", "scripts/python/declencheur_guard.py",
        "scripts/python/morsure_substitution.py",
        "scripts/python/probe_381r4_imperative_collapses.py",
        "scripts/python/tests/engine/runner/test_381r4_imperative_collapses_offline.py",
        "scripts/python/tests/engine/runner/test_381r4_imperative_collapses_live.py",
        "scripts/ratchets-10031-liaisons-figees.json",
        # E1 rejoue le sweep du probe : il traverse le foyer, le dispatch de pathfinder, le gate
        # d'expansion et les trois collapses imperatifs. Declarer les seuls fichiers de #381-r4
        # serait DECLARER TROP ETROIT, et un declencheur trop etroit est un FAUX VERT.
        "scripts/python/engine/*.py",
        "scripts/python/engine/**/*.py",
    ),
    "build": False,
    "toujours": False,
    "raison": "E1 mesure l'EFFET de la mutation `no-gate` a travers tout le chemin de mouvement "
              "(`services/movement_query`, `entities/pathfinding/**`, les trois collapses de "
              "`runner/abilities/genestealer.py` et `runner/operations/triggers/**`) ; E2 balaye "
              "l'AST de `engine/**` en entier. Aucune session, aucun runner, aucun build. "
              "DERIVE par `probe_486r15_declencheurs_tests.py --proposer` (fermeture de 727 "
              "modules ; il rend DEUX chemins hors cascade : `morsure_substitution.py` et "
              "`probe_381r4_imperative_collapses.py`) PUIS elargi a la main pour les quatre "
              "entrees que la proposition ne peut PAS voir, parce qu'elles ne sont pas des "
              "IMPORTS : les trois instruments de #381-r4, LUS EN AST par `cibles_substituees` "
              "(donc changer leurs cibles de substitution change le verdict d'E2 sans qu'aucun "
              "import ne bouge), et le ratchet JSON, lu par `read_text`.",
}

#: les instruments dont on DERIVE les couples substitues (jamais la liste des couples elle-meme).
INSTRUMENTS = (
    "probe_381r4_imperative_collapses.py",
    "tests/engine/runner/test_381r4_imperative_collapses_offline.py",
    "tests/engine/runner/test_381r4_imperative_collapses_live.py",
)
ATTESTE = _PY.parent / "ratchets-10031-liaisons-figees.json"
BOARD = "C2_26"


def _couples():
    couples = cibles_substituees(_PY / f for f in INSTRUMENTS)
    assert couples, ("aucun couple substitue derive des instruments %s -- le recenseur ne visite "
                     "plus rien (un cliquet vide passe pour vert)" % (INSTRUMENTS,))
    return sorted(couples)


# --------------------------------------------------------------------------------------------- #
# E1 -- L'EFFET : la mutation `no-gate` change une sortie de site
# --------------------------------------------------------------------------------------------- #
def test_e1_la_mutation_no_gate_change_une_sortie_de_site():
    """L'INVARIANT de bout en bout. Il ne suppose rien du mecanisme : il exige que desarmer le gate
    #131 (`tile_blocking.make_can_continue -> None`) DEPLACE au moins une sortie observable des
    collapses imperatifs. C'est exactement ce que le probe rendait a `0` pendant que le foyer etait
    en forme A."""
    import probe_381r4_imperative_collapses as P
    out = P.run(board_id=BOARD, mutate="no-gate", verbose=False)
    assert out["block_entering_tiles"], (
        "%s ne porte aucune tuile block-entering : le gate y est inerte par construction, ce "
        "cliquet ne prouverait rien sur ce board" % BOARD)
    assert out["n_diff_total"] > 0, (
        "la mutation `no-gate` ne change AUCUNE sortie sur %s : soit le foyer a re-fige "
        "`make_can_continue` en forme A (cf. #10031, `492c722f`), soit le gate #131 a disparu du "
        "chemin. Ventilation : %s" % (BOARD, out["sites"]))
    assert out["ok"] is True


def test_e1bis_le_probe_rend_rc_zero_sur_ses_trois_bras():
    """Le probe est le porteur du montage ; ses trois bras doivent rendre `ok`. `no-fly` est un
    ZERO ATTENDU (aucun porteur des abilities confrontees n'est `IsLikeFlying`) -- et c'est
    precisement pour ca qu'il ne pouvait PAS servir de detecteur de desarmement : son zero avait
    deux causes possibles et il ne les separait pas. E2 le fait a sa place.

    UN SEUL SITE (`charge`) ici, et c'est un choix MESURE : les trois bras sur les trois sites
    coutent ~40 s pour re-mesurer ce qu'E1 mesure deja sur le sweep COMPLET. Ce que cet etage
    ajoute, c'est le verdict des bras `none` et `no-fly`, qui ne depend pas du site."""
    import probe_381r4_imperative_collapses as P
    for bras in ("none", "no-gate", "no-fly"):
        out = P.run(board_id=BOARD, sites=("charge",), mutate=bras, verbose=False)
        assert out["ok"] is True, "bras %s : %s" % (bras, out["verdict"])


# --------------------------------------------------------------------------------------------- #
# E2 -- LA CAUSE : aucune liaison FIGEE neuve sur un nom substitue
# --------------------------------------------------------------------------------------------- #
def test_e2_aucune_liaison_figee_neuve_sur_un_nom_substitue():
    """DERIVE de bout en bout : les couples viennent des instruments, les liaisons d'un balayage AST
    de `engine/**`. Le fichier d'attestation nomme les liaisons CONNUES et ne doit que DECROITRE."""
    atteste = json.loads(ATTESTE.read_text(encoding="utf-8"))
    connues = {tuple(k.split(" . ")): set(v) for k, v in atteste["liaisons"].items()}

    couples = _couples()
    mesure, neuves, disparues = {}, [], []
    for mod, nom in couples:
        figees = liaisons_figees_statiques(mod, nom)
        mesure["%s . %s" % (mod, nom)] = sorted(figees)
        deja = connues.get((mod, nom), set())
        neuves += ["%s . %s -> %s" % (mod, nom, m) for m in sorted(figees - deja)]
        disparues += ["%s . %s -> %s" % (mod, nom, m) for m in sorted(deja - figees)]

    assert any(mesure.values()) or connues == {}, (
        "le balayage AST ne rend AUCUNE liaison alors que %d etaient attestees : le recenseur ne "
        "visite plus rien (un zero de recenseur n'est pas une preuve)" % sum(map(len, connues.values())))
    assert not neuves, (
        "liaison(s) FIGEE(S) NEUVE(S) en forme A sur un nom substitue -- le patch correspondant ne "
        "mordra pas pour ce module : %s. Passer le consommateur en FORME B (`import X as _x` puis "
        "`_x.foo()`), jamais rendre le cliquet vert en l'attestant" % neuves)
    if disparues:                     # un ratchet DECROIT : on le dit, sans rougir
        print("[10031] liaison(s) figee(s) REPAREE(S), a retirer de l'attestation : %s" % disparues)


def test_e2bis_l_attestation_nomme_ce_qu_elle_couvre_et_reste_petite():
    """Un ratchet qui grossit sans qu'on le lise est une liste blanche. Chaque entree attestee porte
    sa RAISON, et le fichier declare le compte qu'il attestait a l'ouverture -- si le compte MESURE
    le depasse, `test_e2` a deja rougi ; s'il descend, c'est un progres a acter."""
    atteste = json.loads(ATTESTE.read_text(encoding="utf-8"))
    assert atteste.get("liaisons"), "attestation vide : elle ne couvre plus rien"
    for cle, mods in atteste["liaisons"].items():
        assert " . " in cle, "cle malformee : %r (attendu `<module source> . <nom>`)" % cle
        assert mods, "entree %r sans aucune liaison : la retirer plutot que l'attester a vide" % cle
        for m in mods:
            assert m in atteste["raisons"], (
                "%s est atteste sans RAISON ecrite -- une liste blanche muette se recopie" % m)
    total = sum(len(v) for v in atteste["liaisons"].values())
    assert total <= int(atteste["ouverture"]), (
        "l'attestation a GROSSI (%d > %d a l'ouverture) : un ratchet ne monte pas"
        % (total, int(atteste["ouverture"])))


if __name__ == "__main__":                       # pragma: no cover
    raise SystemExit(pytest.main([os.path.abspath(__file__), "-q"]))
