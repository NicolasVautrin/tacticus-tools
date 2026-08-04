"""LIVE #433-r4-r2-r1-r2 -- le SECOND predicat de `GetPossibleTargetsForOptions` (LIGNE DE VUE).

L'ORACLE est le natif : « cette tuile est-elle dans la zone de menace de cette unite ». On l'isole
par la branche A d'`EarlyWarningOverridePlaybook` (`bonus = util + 10 * Sum_E d(P,E)` vaut `0` en
zone, `50` hors zone), sur un sweep de 40 positions `d = 2..10`, avec EXACTEMENT UN ennemi vivant.
Montage importe TEL QUEL de #568 (`probe_433_r4_r2_r1_r1_a_whole_board_gates`), garde
anti-degenerescence comprise : l'ability est greffee SEULE sur un porteur a arme de MELEE, et le
probe REFUSE un greffon dont l'arme porterait plus loin.

LE DISCRIMINANT EST ENONCE AVANT LA MESURE, et il est fourni par les deux temoins que #568 a
isoles -- deux abilities SANS gate dynamique (`rules & 2 == 0`), donc dont la zone ne depend que du
`TargetingRange` et de ce predicat :

    `1161 TwinSmartMissileSystem`  aucun `AllowObscuredTarget*`  -> natif 35/40, port EXACT
    `1147 HadesAutocannons`        les DEUX bits                 -> natif 40/40, port EXACT

Le second est la NON-REGRESSION du premier : un port qui obscurcirait sans lire le masque
retirerait des tuiles ici aussi, et un port qui ne lirait pas la geometrie rendrait 40/40 partout.
Les deux ensemble ne peuvent etre satisfaits que par le modele LU.

COUT : trois runners (plus un, memoise, pour le board). ASCII only.
"""
from __future__ import annotations

import pytest

import probe_433_r4_r2_r1_r1_a_whole_board_gates as P
import probe_433_r4_r2_r1_r2_line_of_sight as L
from rl_collect_batch import _resolve_session


@pytest.fixture(scope="module")
def sid():
    s = _resolve_session()
    if not s:
        pytest.skip("aucune session Frida")
    return s


def _ok(res):
    if "error" in res:
        pytest.fail("montage REFUSE : %s" % res["error"])
    return res


def _graft(aid):
    seed, reports = P._grafted_seed(aid)
    assert reports and reports[0]["activeAbilitiesAfter"] == [aid], "greffe %d : %r" % (aid, reports)
    return seed, [aid]


def test_the_mask_predicts_every_measurement_already_on_file():
    """CONTRE-EPREUVE OFFLINE, gratuite et FALSIFIABLE : `obscuring_type_for` doit separer les DIX
    abilities deja mesurees (#568 + #558) en « 40/40 » et « ecart >= 5 ».

    Elle est ici, dans le fichier LIVE, parce qu'elle porte sur des mesures LIVE -- et parce qu'un
    modele qui expliquerait un seul temoin n'expliquerait rien. Une seule ability a
    `ObscuringType == 0` mesuree en dessous de 40/40, ou une seule a `!= 0` mesuree sans ecart,
    refute le modele."""
    assert L.step_read() == 0


def test_obscured_target_is_removed_when_the_mask_allows_nothing(sid):
    """`1161 TwinSmartMissileSystem` -- le temoin DISCRIMINANT.

    Aucun gate dynamique, aucun bit `AllowObscuredTarget*` : l'ecart qu'elle montrait (5 tuiles sur
    40, mesure #568) appartenait integralement a ce predicat. Le port doit desormais rendre la
    partition EXACTE dans les DEUX sens -- 0 faux positif ET 0 faux negatif.

    Le sweep doit rester NON DEGENERE : si le natif rendait 40/40, ce test ne prouverait plus rien
    (le port aussi rendrait 40/40, par un chemin different)."""
    res = _ok(P.sweep(sid, P.GRAFT_HOST, *_graft(1161)))
    assert res["entity_abilities"] == [1161]
    total = sum(tot for _n, tot in res["par_distance"].values())
    hit = sum(n for n, _tot in res["par_distance"].values())
    assert 0 < hit < total, \
        "regime DEGENERE (%d/%d) : le predicat ne mord pas sur ce montage, le relire" % (hit, total)
    assert res["exact"], "FP=%r FN=%r" % (res["faux_positifs"], res["faux_negatifs"])


def test_both_allow_bits_disable_the_stage_entirely(sid):
    """`1147 HadesAutocannons` -- la NON-REGRESSION, sur le MEME board et le MEME sweep.

    Elle porte `AllowObscuredTargetByElevation | AllowObscuredTargetByWalls`, donc
    `ObscuringType == 0` et `GetTilesObscuringTerrain` rend l'ensemble VIDE sans rien calculer :
    le natif la laisse voir tout le plateau. Le port ne doit RIEN retirer -- c'est ce qui prouve
    que le predicat neuf lit le masque au lieu de s'appliquer partout."""
    res = _ok(P.sweep(sid, P.GRAFT_HOST, *_graft(1147)))
    assert res["entity_abilities"] == [1147]
    for d, (n, tot) in res["par_distance"].items():
        assert n == tot, "d = %d : le plateau ENTIER est attendu, lu %d/%d" % (d, n, tot)
    assert res["exact"], "FP=%r FN=%r" % (res["faux_positifs"], res["faux_negatifs"])


def test_the_two_witnesses_disagree_natively_on_the_same_board(sid):
    """LE POINT DE METHODE : les deux temoins ne different QUE par leur masque -- meme greffon,
    meme board, meme sweep, meme paire de positions. Ce test verrouille que le NATIF les separe,
    donc que l'accord des deux tests precedents n'est pas obtenu en regime degenere.

    Sans lui, un port qui rendrait « en zone » partout passerait le second test et pourrait
    passer le premier si le natif rendait lui aussi 40/40 sur `1161`."""
    a = _ok(P.sweep(sid, P.GRAFT_HOST, *_graft(1161)))
    b = _ok(P.sweep(sid, P.GRAFT_HOST, *_graft(1147)))
    assert a["O"] == b["O"] and a["Y"] == b["Y"], "les deux sweeps doivent partager le montage"
    na = set(map(tuple, a["natif_in_range"]))
    nb = set(map(tuple, b["natif_in_range"]))
    assert na < nb, "le natif doit RETIRER des tuiles a 1161 que 1147 garde : %r vs %r" % (
        len(na), len(nb))
    assert len(nb) - len(na) >= 5, \
        "ecart attendu >= 5 tuiles (mesure #568), lu %d" % (len(nb) - len(na),)
