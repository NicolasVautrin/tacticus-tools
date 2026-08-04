"""LIVE #433-r4-r2-r1-r2-r2 -- les gardes << ami >> : le port REFUSE-t-il ce que le natif ACCEPTE ?

L'ORACLE est `aiMovableTiles {threat: true}`, qui invoque
`IdunBattle.Core.Services.AttackQuery$$GetAllTilesInAbilityRange(unit, moveTiles, true)` -- le
MEME slot `0xe` que `BattleQuery$$IsTileInRangeOfAnyAbility`. Il n'est PAS l'oracle de #568/#574
(le sweep `ncEvaluate`), et c'est DELIBERE : ce dernier ne balaie que
`GetCurrentAndMovablePositionsFor(caster du playbook)`, c'est-a-dire des tuiles LIBRES, plus
l'origine -- occupee par une unite ENNEMIE du caster natif. Aucune de ces tuiles ne peut porter un
ALLIE du caster : ce montage-la est structurellement AVEUGLE a la garde qu'on mesure ici.

LE DISCRIMINANT EST ENONCE AVANT LA MESURE, et il tient en TROIS tuiles du MEME terrain, dont deux
sont les temoins qui interdisent l'accord degenere :

    T_ami     obscurcie, occupee par un ALLIE du caster   -> natif ACCEPTE  (la garde mord)
    T_ennemi  obscurcie, occupee par un ENNEMI du caster  -> natif REFUSE   (l'occupation ne suffit pas)
    T_vide    obscurcie, VIDE                             -> natif REFUSE   (l'etage mord bien ici)

Puis la CONTRE-EPREUVE : la MEME tuile `T_ami`, l'occupant ECHANGE. Le natif y bascule
ACCEPTE -> REFUSE sans qu'aucune geometrie n'ait change -- le natif compare a LUI-MEME.

COUT : un runner (le probe monte, place, mesure, echange et re-mesure dans le meme). ASCII only.
"""
from __future__ import annotations

import pytest

import probe_433_r4_r2_r1_r2_r2_friend_gates as F
from rl_collect_batch import _resolve_session


@pytest.fixture(scope="module")
def sid():
    s = _resolve_session()
    if not s:
        pytest.skip("aucune session Frida")
    return s


@pytest.fixture(scope="module")
def measured(sid):
    """LA mesure, faite UNE fois -- chaque test en assertionne une face. Un montage REFUSE fait
    ECHOUER, il ne skippe pas : un skip ici se lirait « rien a signaler »."""
    res = F.live(sid, "MC1_67")
    if "error" in res:
        pytest.fail("montage REFUSE : %s" % res["error"])
    return res


def test_the_guard_truth_table_holds_offline(sid):
    """La lecture, confrontee a elle-meme sans runner (`--step read`) : `IsFriend` ne depend que du
    caster, `IsFriendOrHasFriendlyUnitOnIt` que de l'egalite des equipes."""
    assert F.step_read() == 0


def test_the_montage_is_not_degenerate(measured):
    """GARDE ANTI-DEGENERESCENCE, evaluee AVANT les verdicts : sans obscurcissement reel, << zone =
    tout le plateau >> rendrait le meme resultat et la mesure ne prouverait rien.

    Elle exige AUSSI que le caster et son allie soient bien de la MEME equipe, et l'ennemi d'une
    AUTRE -- c'est ce que la mesure fait varier."""
    assert measured["n_obscurcies"] >= 3, measured
    assert measured["n_empty_dark"] >= 1, measured
    assert measured["ally_obscured"] is True, measured
    assert measured["foe_obscured"] is True, measured
    assert measured["n_move_tiles"] >= 1, measured


def test_the_native_keeps_an_obscured_tile_that_carries_a_friendly_unit(measured):
    """LE CRITERE BINAIRE. `IsFriendOrHasFriendlyUnitOnIt` -> `GetTilesObscuringTerrain` rend
    l'ensemble VIDE -> la tuile RESTE dans la zone, alors que la geometrie l'obscurcit."""
    assert measured["natif_accepte_T_ami"] is True, measured


def test_occupancy_alone_does_not_exempt_an_obscured_tile(measured):
    """TEMOIN 1 : une tuile obscurcie occupee par un ENNEMI du caster est REFUSEE. Ce n'est donc
    pas << une tuile occupee est exemptee >>, c'est << une tuile AMIE est exemptee >>."""
    assert measured["natif_accepte_T_ennemi"] is False, measured


def test_an_empty_obscured_tile_is_still_refused(measured):
    """TEMOIN 2 : l'etage d'obscurcissement mord bel et bien sur ce terrain. Sans lui, les deux
    autres verdicts ne diraient rien."""
    assert measured["natif_accepte_T_vide"], measured
    assert all(v is False for v in measured["natif_accepte_T_vide"]), measured


def test_the_port_closed_the_restrictive_gap(measured):
    """L'ECART, CHIFFRE. Le port d'AVANT (gardes non alimentees) rend un faux NEGATIF sur `T_ami` ;
    celui d'APRES est EXACT sur tout le sweep, dans les deux sens."""
    assert measured["avant_accepte_T_ami"] is False, measured
    assert measured["apres_accepte_T_ami"] is True, measured
    assert measured["n_avant_fn"] >= 1, measured
    assert measured["n_apres_fn"] == 0, measured
    assert measured["n_apres_fp"] == 0, measured


def test_the_same_tile_flips_when_the_occupant_changes(measured):
    """LA CONTRE-EPREUVE. Meme tuile, meme caster, meme movable set, meme geometrie -- seul
    l'occupant change d'equipe, et le verdict NATIF bascule. C'est ce qui exclut toute explication
    par le terrain ou par la distance."""
    sw = measured.get("swap") or {}
    assert sw.get("done") is True, measured
    assert sw["obscurcie_geometriquement"] is True, sw
    assert sw["occupant_team"] != measured["caster_team"], sw
    assert sw["natif_accepte"] is False, sw
    assert sw["port_accepte"] is False, sw


def test_the_walkability_stage_is_upstream_and_named(measured):
    """RESIDU NOMME, mesure ici plutot que suppose : le natif retire les tuiles NON MARCHABLES a un
    etage AMONT de la ligne de vue. Le sweep du probe s'y restreint -- sinon il compterait comme
    ecart de CETTE tranche un ecart qui n'est pas le sien."""
    assert measured["n_nonwalkable"] >= 1, measured
    assert measured["n_nonwalkable_in_zone"] == 0, measured
