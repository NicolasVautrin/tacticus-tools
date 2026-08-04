"""LIVE #433-r4-r2-r1-r2-r2-r1 -- le port attribue-t-il des tuiles que le natif REFUSE ?

ECART PERMISSIF, donc le seul type qu'un entrainement puisse exploiter : avant cette tranche le
port versait dans la zone d'une unite toute tuile NON MARCHABLE, que le natif retire dans
`IdunBattle.Core.Services.TargetingQuery$$GetTilesInRange` -- EN AMONT des trois predicats de
`GetPossibleTargetsForOptions`, ligne de vue comprise.

DEUX REGIMES, ET ILS NE SONT PAS REDONDANTS :

    C5_19   34 tuiles non marchables / 63, 0 mur, 0 fog, 0 obscurcie  -> le volet WALKABLE, PUR
    C6_02   22 non marchables + 31 tuiles `walkable && isInFog`       -> le volet FOG, DISCRIMINANT

Le second porte la contre-epreuve qui interdit de rabattre `TileExtensions$$IsWalkable(t,
checkFog: true)` sur `BattleQuery$$IsWalkableTile` (la source du champ `walkable`) : un port a UN
SEUL volet y laisse encore 26 faux positifs, la ou le port complet en laisse 0.

⚠ Le greffon est en TEAM 1 : les 15 boards a FOG sont TOUS des `C6_*` (space hulk, correlation
EXACTE `RoomID >= 0` <-> `isInFog`), et l'equipe 2 n'y est pas deployee. La zone de
`GetAllTilesInAbilityRange` ne depend d'aucun ennemi -- c'est ce qui rend ce regime confrontable.

COUT : deux runners (un par regime), montes et disposes par le probe. ASCII only.
"""
from __future__ import annotations

import pytest

import probe_433_r4_r2_r1_r2_r2_r1_walkability as W
from rl_collect_batch import _resolve_session


@pytest.fixture(scope="module")
def sid():
    s = _resolve_session()
    if not s:
        pytest.skip("aucune session Frida")
    return s


@pytest.fixture(scope="module")
def pur(sid):
    """Regime WALKABLE pur (`C5_19`). Un montage REFUSE fait ECHOUER : un skip ici se lirait
    << rien a signaler >>."""
    res = W.live(sid, "C5_19")
    if "error" in res:
        pytest.fail("montage REFUSE (C5_19) : %s" % res["error"])
    return res


@pytest.fixture(scope="module")
def brume(sid):
    """Regime FOG (`C6_02`) -- celui qui separe les deux volets."""
    res = W.live(sid, "C6_02")
    if "error" in res:
        pytest.fail("montage REFUSE (C6_02) : %s" % res["error"])
    return res


def test_the_montage_is_not_degenerate(pur):
    """GARDE ANTI-DEGENERESCENCE, evaluee AVANT tout verdict. Le gisement doit MORDRE : sans tuiles
    non marchables dans le plateau, ni sans zone native, la mesure ne prouverait rien -- c'est
    exactement le defaut de la mesure heritee (1 seule tuile)."""
    assert pur["n_nonwalkable"] >= 20, pur
    assert pur["n_move_tiles"] >= 1, pur
    assert pur["n_zone_native"] >= 1, pur
    assert not (int(pur["rules"]) & 1 << 43), pur      # l'ability ne desarme PAS l'etage


def test_the_native_never_puts_an_unwalkable_tile_in_the_zone(pur):
    """LE CRITERE BINAIRE, face NATIVE. Sur 63 tuiles dont 34 non marchables, la zone native n'en
    contient AUCUNE -- et elle vaut exactement les 29 marchables."""
    assert pur["n_nonwalkable_in_zone"] == 0, pur
    assert pur["n_zone_native"] == pur["n_tiles"] - pur["n_nonwalkable"], pur


def test_the_port_stopped_attributing_tiles_the_native_refuses(pur):
    """L'ECART, CHIFFRE. Le port d'AVANT attribuait les 34 tuiles ; celui d'APRES est EXACT dans
    les deux sens. Le `>= 20` sur AVANT est ce qui interdit de lire un << 0 apres >> comme une
    victoire alors que rien n'aurait mordu."""
    assert pur["n_avant_fp"] >= 20, pur
    assert pur["n_avant_fp"] == pur["n_avant_fp_nonwalkable"], pur
    assert pur["n_apres_fp"] == 0, pur
    assert pur["n_apres_fn"] == 0, pur


def test_the_fog_regime_carries_both_volets(brume):
    """GARDE ANTI-DEGENERESCENCE du second regime : il doit porter les DEUX populations, sinon il
    ne separe rien."""
    assert brume["n_nonwalkable"] >= 10, brume
    assert brume["n_walkable_and_fog"] >= 10, brume
    assert brume["n_move_tiles"] >= 1, brume


def test_the_native_removes_fogged_tiles_too(brume):
    """`IsWalkable(t, checkFog: true)` : une tuile MARCHABLE mais en FOG est retiree elle aussi.
    C'est le second volet, et il est invisible du champ `walkable`."""
    assert brume["n_walkable_and_fog_in_zone"] == 0, brume
    assert brume["n_nonwalkable_in_zone"] == 0, brume


def test_one_volet_is_not_enough(brume):
    """LA CONTRE-EPREUVE. Un port qui ne lirait que `walkable` (= `BattleQuery$$IsWalkableTile`)
    laisse encore des faux positifs sur ce terrain ; le port complet n'en laisse aucun. Sans elle,
    le `0` du port complet serait compatible avec un modele a un seul volet."""
    assert brume["n_volet1_fp"] > 0, brume
    assert brume["n_apres_fp"] == 0, brume
    assert brume["n_apres_fn"] == 0, brume
    assert brume["n_avant_fp"] > brume["n_volet1_fp"], brume


def test_the_gap_is_ventilated_by_cause_not_a_bare_total(brume):
    """DECOMPOSITION PAR ETAGE : chaque faux positif d'AVANT est impute a SON volet. Un total nu ne
    dirait pas lequel des deux mord -- et c'est justement ce que le regime `C5_19` seul ne peut
    pas trancher."""
    assert (brume["n_avant_fp_nonwalkable"] + brume["n_avant_fp_onlyfog"]
            + brume["n_avant_fp_autre"]) == brume["n_avant_fp"], brume
    assert brume["n_avant_fp_nonwalkable"] > 0, brume
    assert brume["n_avant_fp_onlyfog"] > 0, brume
    assert brume["n_avant_fp_autre"] == 0, brume     # aucun ecart d'une AUTRE cause ne subsiste


def test_the_read_step_is_self_consistent():
    """La lecture confrontee a elle-meme, sans runner -- la table de verite du foyer."""
    assert W.step_read() == 0
