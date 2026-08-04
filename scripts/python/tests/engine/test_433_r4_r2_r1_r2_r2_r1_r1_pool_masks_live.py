"""LIVE #433-r4-r2-r1-r2-r2-r1-r1 -- les 32 masques du POOL rendent-ils le port EXACT ?

L'ECART etait PERMISSIF, le seul type qu'un entrainement puisse exploiter : sans leur masque
`rules`, les 32 abilities actives du pool spawnable hors `ABILITY_CLASSES` desarmaient TROIS etages
du port (convention permissive `rules is None` -> aucun retrait), alors que leur volet PORTEE, lui,
etait deja lu et versait sa zone.

DEUX MONTAGES, ET ILS NE SONT PAS REDONDANTS -- chacun isole UN etage, sur une ability REELLE du
pool (aucune greffe) :

    templAncient / 1061 UnbreakableDuty   rules = 0x8400, friendly-only, arme 1 < config 2
        -> le court-circuit `TargetIsFriendly && !TargetIsEnemy` de
           `IdunBattle.Core.Services.TargetingQuery$$GetPossibleTargetTiles`. Le kit tient en UNE
           ability : aucun autre etage ne peut expliquer l'ecart.

    tauMarksman / 1069 SeekerMissileFrequencyLock   rules = 0x4002, portee 5, board C5_19
        -> le `RemoveAll` de `IdunBattle.Core.Services.TargetingQuery$$GetTilesInRange`, gate par le
           bit 43 `AllowUnwalkableTargetTile` -- qu'AUCUNE des 32 ne porte.

L'ORACLE est `aiMovableTiles {threat: true}` = `AttackQuery$$GetAllTilesInAbilityRange`, le MEME
slot 0xe que `BattleQuery$$IsTileInRangeOfAnyAbility` interroge, et le port y est evalue en UNION
sur le MEME movable set -- sinon on comparerait deux questions differentes.

COUT : deux runners (un par montage), montes et disposes par le probe. ASCII only.
"""
from __future__ import annotations

import pytest

import probe_433_r4_r2_r1_r2_r2_r1_r1_pool_masks as P
from rl_collect_batch import _resolve_session


@pytest.fixture(scope="module")
def sid():
    s = _resolve_session()
    if not s:
        pytest.skip("aucune session Frida")
    return s


@pytest.fixture(scope="module")
def ami(sid):
    """Le court-circuit. Un montage REFUSE fait ECHOUER : un skip ici se lirait « rien a signaler »."""
    res = P.friendly(sid)
    if "error" in res:
        pytest.fail("montage REFUSE (friendly) : %s" % res["error"])
    return res


@pytest.fixture(scope="module")
def marche(sid):
    """L'etage AMONT de walkability, sur une ability REELLE du pool."""
    res = P.walkability(sid)
    if "error" in res:
        pytest.fail("montage REFUSE (walkability) : %s" % res["error"])
    return res


def test_the_friendly_montage_is_not_degenerate(ami):
    """GARDE ANTI-DEGENERESCENCE, evaluee AVANT tout verdict. Les deux modeles doivent etre
    SEPARABLES : si `unit_threat_reach` valait la meme chose avant et apres, la mesure serait
    compatible avec les deux et ne prouverait rien."""
    assert ami["reach_before"] != ami["reach_after"], ami
    assert (ami["reach_before"], ami["reach_after"]) == (2, 1), ami
    assert ami["n_move_tiles"] >= 1, ami
    assert ami["n_native"] >= 1, ami


def test_the_friendly_only_ability_contributes_no_tile_to_the_native_zone(ami):
    """LE CRITERE BINAIRE. `1061 UnbreakableDuty` porte `TargetIsFriendly` SANS `TargetIsEnemy` :
    `GetPossibleTargetTiles` rend un `OrderedSet` VIDE avant meme d'appeler `GetRange`, donc sa
    portee de config (2) ne verse RIEN. La zone native ne depasse donc pas la portee d'ARME (1),
    depuis un movable set qui la decale d'au plus 1."""
    assert ami["maxd_native"] <= 2, ami
    assert ami["maxd_before"] > ami["maxd_native"], ami
    assert ami["maxd_after"] <= ami["maxd_native"], ami


def test_the_port_stopped_over_attributing_on_the_friendly_montage(ami):
    """L'ECART, CHIFFRE et dans le bon sens. Le `>= 5` sur AVANT interdit de lire la baisse comme
    une victoire alors que rien n'aurait mordu."""
    assert len(ami["fp_before"]) >= 5, ami
    assert len(ami["fn_before"]) == 0, ami
    assert len(ami["fp_after"]) < len(ami["fp_before"]), ami
    assert len(ami["fn_after"]) == 0, ami


def test_the_residual_false_positive_is_the_source_tile_only(ami):
    """RESIDU NOMME, et il n'est PAS un ecart de masque : `GetTilesInRange` branche
    `range.OnlyAdjacent` sur `<IBattleQuery slot 0x51>` = les tuiles ADJACENTES, qui EXCLUENT
    `casterTiles`. Le port modelise la zone par un RAYON et teste `d <= 1`, donc il inclut `d = 0`.
    Chaque tuile du set d'ENTREE est ainsi un faux positif -- et aucune autre.

    Ce test le BORNE : si le residu debordait de cet ensemble, la cause ne serait plus celle-la."""
    assert set(ami["fp_after"]) <= set(map(tuple, ami["move_tiles"])), ami


def test_the_walkability_montage_is_not_degenerate(marche):
    """Le gisement doit MORDRE : sans tuiles non marchables, la mesure ne prouverait rien."""
    assert marche["n_nonwalkable"] >= 20, marche
    assert marche["n_move_tiles"] >= 1, marche
    assert marche["n_native"] >= 1, marche
    assert not (int(marche["rules"]) & 1 << 43), marche   # l'ability ne desarme PAS l'etage


def test_a_real_pool_ability_now_matches_the_native_zone_exactly(marche):
    """LE VERDICT. La tranche precedente avait valide le MECANISME sur une ability GREFFEE ; ici
    c'est une ability du pool, avec le masque que ce lot a lu, et le port est EXACT dans les DEUX
    sens. Le `>= 20` sur AVANT est ce qui interdit de lire le `0` comme une victoire vide."""
    assert len(marche["fp_before"]) >= 20, marche
    assert len(marche["fn_before"]) == 0, marche
    assert len(marche["fp_after"]) == 0, marche
    assert len(marche["fn_after"]) == 0, marche
    assert marche["n_after"] == marche["n_native"], marche
