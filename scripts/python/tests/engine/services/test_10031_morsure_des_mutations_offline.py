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

E2 etait un RATCHET a DEUX liaisons attestees hors du chemin de `#381-r4`
(`engine/ai/state_bridge.py` pour `make_can_continue`, `engine/runner/operations/movement.py` pour
`is_like_flying`). `#10031-r1` les a passees en FORME B et re-joue les mesures qu'elles
desarmaient : **le ratchet est REFERME A ZERO**, et E2 est desormais un INVARIANT -- toute liaison
figee, ancienne ou neuve, rougit. Le fichier d'attestation reste, VIDE : il porte le compte
d'ouverture (0) et la borne « ne monte pas ».

⚠ ET C'EST LA QU'UN CLIQUET DEVIENT VERT-SUR-RIEN. Tant que des liaisons etaient attestees, le
non-vide de la mesure prouvait que le balayage AST visitait encore quelque chose. A zero, cette
preuve DISPARAIT : un recenseur casse rendrait `set()` partout et E2 passerait. Le non-vide se
prend donc sur un TEMOIN (`test_e2ter`), jamais sur le GISEMENT -- un arbre jetable ou l'on ECRIT
une forme A et une forme B, et ou le recenseur doit voir exactement la premiere.

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
    # ⚠ Quand `connues == {}` la ligne ci-dessus ne garde plus RIEN -- c'est `test_e2ter` qui prend
    # le relais, sur un TEMOIN, parce qu'un zero de gisement ne peut pas prouver qu'on l'a regarde.
    assert not neuves, (
        "liaison(s) FIGEE(S) NEUVE(S) en forme A sur un nom substitue -- le patch correspondant ne "
        "mordra pas pour ce module : %s. Passer le consommateur en FORME B (`import X as _x` puis "
        "`_x.foo()`), jamais rendre le cliquet vert en l'attestant" % neuves)
    if disparues:                     # un ratchet DECROIT : on le dit, sans rougir
        print("[10031] liaison(s) figee(s) REPAREE(S), a retirer de l'attestation : %s" % disparues)


def test_e2bis_l_attestation_nomme_ce_qu_elle_couvre_et_reste_petite():
    """Un ratchet qui grossit sans qu'on le lise est une liste blanche. Chaque entree attestee porte
    sa RAISON, et le fichier declare le compte qu'il attestait a l'ouverture -- si le compte MESURE
    le depasse, `test_e2` a deja rougi ; s'il descend, c'est un progres a acter.

    ⚠ L'ATTESTATION VIDE EST L'ETAT CIBLE, PAS UNE PANNE (#10031-r1). Ce test exigeait
    `atteste["liaisons"]` non vide -- donc refermer le ratchet a zero, ce qu'il prescrivait, le
    faisait ROUGIR. Un ratchet dont le gardien interdit l'arrivee ne descend jamais. A vide, ce
    qu'on exige change de nature : `ouverture` doit valoir 0 (le fichier DIT qu'il est referme) et
    `_ferme` doit nommer la tranche qui l'a ferme, pour qu'une reouverture soit un geste ECRIT."""
    atteste = json.loads(ATTESTE.read_text(encoding="utf-8"))
    if not atteste.get("liaisons"):
        assert int(atteste["ouverture"]) == 0, (
            "attestation VIDE mais `ouverture` = %s : un ratchet referme declare 0, sinon il laisse "
            "une place libre ou une liaison neuve pourrait rentrer sans rougir" % atteste["ouverture"])
        assert atteste.get("_ferme"), (
            "attestation VIDE sans champ `_ferme` : la fermeture doit nommer la tranche et ce "
            "qu'elle a re-joue, sinon personne ne saura si le zero est un progres ou un effacement")
        assert not atteste.get("raisons"), (
            "attestation VIDE mais `raisons` non vide : des raisons orphelines survivent a leur "
            "objet et se recopient (cf. les 8 raisons perimees sur 8 mesurees le 2026-08-18)")
        return
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


def test_e2ter_le_recenseur_mord_sur_un_temoin_ecrit(tmp_path):
    """LE NON-VIDE SE PREND SUR UN TEMOIN, JAMAIS SUR LE GISEMENT (#10031-r1).

    Depuis que l'attestation est vide, `test_e2` attend `set()` partout -- et un recenseur cassé
    rendrait exactement ça. On lui donne donc un arbre JETABLE où l'on ECRIT les trois formes que
    CLAUDE.md distingue, et on exige qu'il rende EXACTEMENT la forme A :

      A `from <src> import foo` au niveau module + appel    -> FIGEE   (ne mord pas)
      B `from pkg import src as _s` + `_s.foo()`            -> LIBRE   (mord)
      C `from <src> import foo` DANS la fonction + appel    -> LIBRE   (mord, par re-execution)
      RE-EXPORT : forme A SANS aucun appel                  -> LIBRE   (ne change la morsure de
                                                                        personne)
      HOMONYME  : forme A depuis un AUTRE module + appel     -> LIBRE   (ce n'est pas notre nom)

    Les cinq sont ECRITS ici : un recenseur qui n'en verrait aucune, ou qui les verrait toutes,
    tombe. Le second cas est le plus important -- c'est le sur-comptage qui ferait attester des
    modules sains, donc grossir la liste blanche. L'HOMONYME garde la reconnaissance par SUFFIXE
    de module (`_lie_en_forme_a`) : sans lui, un recenseur qui accepterait n'importe quel
    `ImportFrom` portant le nom passerait ce test sans que rien ne le dise."""
    src = "engine.entities.pathfinding.tile_blocking"
    (tmp_path / "forme_a.py").write_text(
        "from %s import make_can_continue\n"
        "def f():\n    return make_can_continue(None, [], board=None)\n" % src, encoding="utf-8")
    (tmp_path / "forme_b.py").write_text(
        "from engine.entities.pathfinding import tile_blocking as _tb\n"
        "def f():\n    return _tb.make_can_continue(None, [], board=None)\n", encoding="utf-8")
    (tmp_path / "forme_c.py").write_text(
        "def f():\n    from %s import make_can_continue\n"
        "    return make_can_continue(None, [], board=None)\n" % src, encoding="utf-8")
    (tmp_path / "reexport.py").write_text(
        "from %s import make_can_continue\n__all__ = ['make_can_continue']\n" % src, encoding="utf-8")
    (tmp_path / "homonyme.py").write_text(
        "from engine.services.un_autre_module import make_can_continue\n"
        "def f():\n    return make_can_continue(None, [], board=None)\n", encoding="utf-8")

    vu = liaisons_figees_statiques(src, "make_can_continue", racine=tmp_path)
    assert vu == {"forme_a.py"}, (
        "le recenseur AST ne discrimine plus les formes de liaison : attendu {'forme_a.py'}, "
        "mesure %s. Un zero du gisement ne prouve alors plus rien (vert-sur-rien)" % sorted(vu))


def test_e2quater_le_recenseur_voit_l_import_relatif(tmp_path):
    """L'ecriture RELATIVE est celle de tout `engine/runner/**` (`from ...entities.pathfinding.
    fly_pathfinder import is_like_flying`) -- c'est-a-dire EXACTEMENT la liaison que `#10031-r1`
    vient de reparer dans `runner/operations/movement.py`. Un recenseur aveugle a cette forme-la
    rendrait zero sur le gisement meme qu'il est cense garder, et ce test-ci serait le seul a le
    dire : le TEMOIN ci-dessus n'ecrit que la forme ABSOLUE."""
    src = "engine.entities.pathfinding.fly_pathfinder"
    (tmp_path / "relatif.py").write_text(
        "from ...entities.pathfinding.fly_pathfinder import is_like_flying\n"
        "def f(t):\n    return is_like_flying(t)\n", encoding="utf-8")
    vu = liaisons_figees_statiques(src, "is_like_flying", racine=tmp_path)
    assert vu == {"relatif.py"}, (
        "le recenseur ne voit pas la forme A ecrite en import RELATIF (`from ...pkg.mod import "
        "nom`), qui est l'ecriture de tout `engine/runner/**` : mesure %s" % sorted(vu))


if __name__ == "__main__":                       # pragma: no cover
    raise SystemExit(pytest.main([os.path.abspath(__file__), "-q"]))
