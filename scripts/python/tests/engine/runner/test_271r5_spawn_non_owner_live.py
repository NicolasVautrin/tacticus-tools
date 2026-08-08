#!/usr/bin/env python3
"""#271-r5 -- garde de la CONFRONTATION LIVE du regime SPAWN de la feuille non-owner.

Ce que #271-r3 avait livre : les trois corps non-owner qui yieldent AUSSI en regime SPAWN
(`PsychicFortress` 20, `BookOfFate` 5, branche SPAWN de `MawClawsOfThyrax` 5), mirror-1:1,
gardes par 8 tests offline + 5 mutations. Ce qu'il n'avait pas : l'OBSERVABLE natif -- **quelle
tuile le jeu choisit pour faire apparaitre un summon**.

Mesure du 2026-08-08 (`MC1_67`, seed 777, C=t13 / Tigurius=t14 / ennemi=t12) :

    port SANS le terme -> t22        port AVEC -> t23        NATIF -> t23

avec un DOUBLE ecart strictement positif (t22 bat t23 de 10 sans le terme ; t23 bat t22 de 10
avec). Le bras SANS est obligatoire : sans lui, un accord natif/port ne distinguerait pas
<< le terme porte le resultat >> de << il vient d'ailleurs >>.

ASCII only (console Windows cp1252).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

PYDIR = Path(__file__).resolve().parents[3]
if str(PYDIR) not in sys.path:
    sys.path.insert(0, str(PYDIR))

import probe_271r5_spawn_non_owner_live as P  # noqa: E402
import probe_130_placement_sort_rng as P130  # noqa: E402

DECLENCHEUR = {
    "chemins": ("scripts/python/engine/playbook/non_owner.py",
                "scripts/python/engine/utilities/tile.py",
                "scripts/python/engine/runner/operations/spawn.py",
                "scripts/python/probe_271r5_spawn_non_owner_live.py"),
    "build": False,
    "toujours": False,
    "raison": "Il confronte le terme SPAWN non-owner au choix de tuile du jeu : le corps du "
              "playbook, le composite qui le porte, le call-site de spawn et le harnais.",
}

BOARD = "MC1_67"
SEED = "777"


@pytest.fixture(scope="module")
def mesure():
    from engine.entities.pathfinding.board import Board
    import uuid
    rpc = P130.Rpc()
    sonde = P.ROOT / "logs" / "runners" / ("t271r5-sonde-%s.json" % uuid.uuid4().hex[:8])
    sonde.parent.mkdir(parents=True, exist_ok=True)
    rid = P._build(SEED, BOARD, sonde)
    if rid is None:
        pytest.fail("montage impossible : `rl_duel build` a echoue (ce n'est pas un verdict "
                    "sur le port -- reparer le montage)")
    try:
        bg = rpc("boardGraph", {"runnerId": rid}, 60)
    finally:
        rpc("disposeRunner", {"runnerId": rid}, 30)
        Path(sonde).unlink(missing_ok=True)
    assert isinstance(bg, dict) and bg.get("tiles"), "boardGraph indispo -- NON MESURE"
    board = Board(bg["tiles"], adjacency="native_sym")
    cands = P.cherche_geometrie(board)
    stricts = [d for d in cands if min(d["strict"], d["marge"]) > 0]
    resultat = None
    for geo in stricts[:6]:
        r = P.confronte(rpc, SEED, BOARD, geo)
        if r.get("ok") and r["port_sans"] != r["port_avec"]:
            resultat = r
            break
    return {"board": board, "cands": cands, "stricts": stricts, "r": resultat}


def test_une_geometrie_a_DOUBLE_ecart_strictement_positif_existe(mesure):
    """Le prealable, et il n'est pas acquis : `ElevationUtility` vaut `10 x elev`, donc deux
    crans d'elevation annulent exactement le `+20`.

    `strict == 0` (ex aequo AVANT) : un tie-break natif fixe produirait le meme renversement.
    `marge == 0` (ex aequo APRES) : le terme n'a fait qu'egaliser. Les deux sont exiges --
    c'est la lecon que le residu voisin #271-r1 paie encore.
    """
    assert mesure["cands"], "aucune geometrie ou le +20 renverse l'argmax sur %s" % BOARD
    assert mesure["stricts"], (
        "aucune geometrie a DOUBLE ecart strictement positif : la confrontation ne "
        "trancherait pas (%d geometries a ecart nul d'un cote)" % len(mesure["cands"]))


def test_le_terme_SPAWN_non_owner_DEPLACE_le_choix_du_port(mesure):
    """Le contre-controle. Un accord natif/port sur deux bras identiques ne prouverait rien."""
    r = mesure["r"]
    assert r is not None, "aucune des geometries essayees n'a pu etre montee -- NON CONFRONTE"
    assert r["port_sans"] != r["port_avec"], (
        "les deux bras du PORT coincident : le terme ne deplace pas le choix, "
        "la confrontation qui suit serait tautologique (%r)" % (r["port_sans"],))


def test_le_NATIF_suit_le_port_AVEC_le_terme(mesure):
    """L'observable de #271-r5 : quelle tuile le jeu choisit pour faire apparaitre le summon.

    Si ce test tombe en rendant `port_sans`, ce n'est pas un bug de montage : le natif ne
    verse PAS ce terme en regime spawn, et le port a un terme de TROP.
    """
    r = mesure["r"]
    assert r is not None, "NON CONFRONTE"
    assert r["natif"] == r["port_avec"], (
        "natif=%r  port_avec=%r  port_sans=%r -- %s"
        % (r["natif"], r["port_avec"], r["port_sans"],
           "le terme est de TROP en regime spawn" if r["natif"] == r["port_sans"]
           else "le natif ne rend AUCUN des deux bras"))


def test_le_summon_a_bien_ete_pose(mesure):
    """Temoin NON NUL : un accord entre deux listes VIDES passerait pour un vert.

    C'est le meme cran que les 44 temoins non nuls de #287-r14.
    """
    r = mesure["r"]
    assert r is not None, "NON CONFRONTE"
    assert r["natif"], "le natif n'a pose AUCUN summon -- rien n'a ete confronte"
    assert len(r["natif"]) == 1, \
        "ControlEdict pose UN summon ; %d observe(s) : le montage a change" % len(r["natif"])
