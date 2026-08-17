"""GARDE LIVE #448-r1-r1-r3-r1 -- `movementStartPosition` confronte au natif sur une unite HORS
PLATEAU.

Le montage vit dans `scripts/python/probe_448r1r1r3r1_movement_start_live.py` (`run()`), qui
reutilise les briques de #448-r2b (greffe du passif `StormboyzStrike` sur une unite du pool ; le
porteur reel `orksNpc6Stormboy` est un npc sans summoner). Ce fichier n'en est que la PORTE pytest.

CE QUE LA MESURE ETABLIT, et pourquoi elle a failli conclure l'INVERSE : cf. la docstring du probe.
En resume -- le canal `tilesMoved*` vient du RPC `actorStats` et NON de `combatSnapshot` (sans quoi
les deux cotes s'accordent sur un canal vide), et il faut lire le cumul BATAILLE (`@+0xec`) et non
celui du tour (`@+0xf0`), que `ActorStatisticsComponent$$ResetThisTurn` roule en fin de tour --
c'est-a-dire exactement pendant le pas mesure ici.

⚠ Un montage qui ne s'installe pas ECHOUE, il ne skippe pas (#268) : `run()` leve. Seule
l'indisponibilite du HARNAIS skippe, et c'est `live_session` qui la porte.

ASCII only. Aucune VA en dur. `run()` DISPOSE son runner.
"""
from __future__ import annotations

import pytest

import probe_448r1r1r3r1_movement_start_live as P


@pytest.fixture(scope="module")
def pas_hors_plateau(live_session):
    """Le montage, UNE fois pour tout le fichier."""
    return P.run()


def test_le_montage_a_bien_pose_un_porteur_HORS_PLATEAU(pas_hors_plateau):
    """ANTI-TAUTOLOGIE. Sans ce controle, un porteur reste SUR le plateau ferait passer tout le
    fichier en regime NOMINAL -- ou le port d'avant et le port d'apres rendent la MEME chose."""
    c = pas_hors_plateau
    assert c["graftReport"]["abilityId"] == 1141, c["graftReport"]
    assert c["start"]["pos"] is None and c["start"]["feet"] == [], (
        "le porteur garde une position : %r" % (c["start"],))
    assert c["startMovementStart"] == [], (
        "le porteur a un `previousPositionThisTurn` : c'est le SECOND BRAS, pas la branche "
        "degeneree -- la mesure ci-dessous ne porte plus sur ce que ce fichier annonce (%r)"
        % (c["startMovementStart"],))


def test_le_canal_actorStats_SAIT_bouger_dans_ce_runner(pas_hors_plateau):
    """LE TEMOIN NON NUL, et il est la raison d'etre de ce fichier autant que l'assertion suivante.
    Un delta `0` cote natif ne dit RIEN tant qu'on n'a pas montre que le canal repond ici. C'est ce
    controle qui a revele que `load_state` n'ingerait pas `actorStats`, et que le compteur DU TOUR
    etait roule par la fin de tour que le pas mesure declenche."""
    c = pas_hors_plateau
    assert c["temoinOk"] is True, "le 2e pas (regime NOMINAL) a ete refuse : %r" % (c,)
    assert c["temoinDelta"] and c["temoinDelta"] > 0, (
        "le canal `tilesMovedThisBattle` ne bouge pas sur un pas NOMINAL (delta %r) -- le compte du "
        "pas hors plateau ne prouverait RIEN, ni pour ni contre." % (c["temoinDelta"],))


def test_le_natif_COMPTE_la_branche_degeneree_et_le_port_le_suit(pas_hors_plateau):
    """LA CONFRONTATION. `CalculatePaths` rend `path = connectedPath = [endTile, endTile]` quand
    `movementStartPosition` est vide, donc `GetNumTilesMoved(connectedPath) = Count - 1 = 1`, et
    `RecordTilesMoved(unit, 1, state)` incremente les DEUX compteurs."""
    c = pas_hors_plateau
    assert c["nativeTilesMoved"] is not None, (
        "`actorStats.tilesMovedThisBattle` NON MESURE (avant=%r apres=%r) -- aucune conclusion"
        % (c["nativeAvant"], c["nativeApres"]))
    assert c["portTilesMoved"] == c["nativeTilesMoved"], (
        "tilesMovedThisBattle : port=%r != natif=%r" % (c["portTilesMoved"],
                                                        c["nativeTilesMoved"]))
    assert c["nativeTilesMoved"] >= 1, (
        "le natif ne compte rien sur ce pas (%r) : le regime est degenere et ne separe pas les deux "
        "ports." % (c["nativeTilesMoved"],))


def test_la_CONTRE_EPREUVE_n_est_pas_vide(pas_hors_plateau):
    """Le port d'AVANT (`_num_tiles_moved(from_pos = position COURANTE = None)`) sur le MEME etat.
    S'il rendait deja le compte natif, l'accord ci-dessus ne dirait pas si le fix a mordu."""
    c = pas_hors_plateau
    assert c["portAvantTilesMoved"] != c["nativeTilesMoved"], (
        "le port d'AVANT rendait deja %r, comme le natif -- ce montage n'exerce pas "
        "#448-r1-r1-r3-r1" % (c["portAvantTilesMoved"],))
    assert c["portAvantTilesMoved"] == 0


def test_la_position_finale_coincide(pas_hors_plateau):
    """Le pas lui-meme n'a pas change : ce residu porte sur le COMPTE, pas sur la trajectoire. Le
    porteur peut avoir ete DEVIE par `...StormboyzStrike_MissAbility` -- des DEUX cotes, le flux MT
    etant aligne."""
    c = pas_hors_plateau
    assert c["portPos"] == c["nativePos"], ("position finale : port=%r != natif=%r"
                                            % (c["portPos"], c["nativePos"]))


if __name__ == "__main__":                                  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
