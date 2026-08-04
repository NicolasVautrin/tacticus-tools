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

DEUX SCENARIOS DE GENERALISATION s'y ajoutent, sur des kits NATIFS (aucune greffe) et a une AUTRE
distance : l'ATTAQUE NORMALE (`necroWarden`, arme 3 obscurcie + ability de portee 1 exemptee) et le
trait `IndirectFire` (`astraOrdnance`). Chacun porte son CONTREFACTUEL -- ce que le port rendrait
sans le volet teste -- parce qu'un accord dont le contrefactuel ne differe pas est DEGENERE.

COUT : sept runners (plus deux, memoises, pour les cartes de board). ASCII only.
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


# ------------------------------------------------------------------------------------------------
# GENERALISATION -- l'ATTAQUE NORMALE et le trait, sur des kits NATIFS (aucune greffe)
#
# Les deux temoins ci-dessus sont des abilities `UseWholeBoard` GREFFEES : ils ne disent rien de
# l'autre terme de l'union de `AttackQuery$$GetAllTilesInAbilityRange`, l'attaque NORMALE, qui
# concerne TOUTE unite a distance du jeu. Ces deux montages l'exercent, a une distance et sur une
# region du plateau differentes, et chacun porte son CONTREFACTUEL -- ce que le port rendrait sans
# le volet teste. Un accord dont le contrefactuel ne differe pas est un accord DEGENERE.
# ------------------------------------------------------------------------------------------------
def test_normal_attack_is_subject_to_the_line_of_sight(sid):
    """`necroWarden`, kit NATIF : arme de portee 3 (masque `0x4002`, donc OBSCURCIE) et
    `1005 AdaptiveStrategy` de portee 1 dont le masque porte les deux bits `AllowObscured*`.

    Tout ce qui depasse `d = 1` vient donc de l'ARME, et le predicat neuf y est SEUL responsable
    de la forme de la zone. Le montage est FORCE vers la paire qui maximise les obstructions : le
    natif refuse alors une part SUBSTANTIELLE du disque de rayon 3, ce que le modele concurrent
    (« zone = disque ») accepterait en bloc."""
    res = _ok(L.sweep_normal_attack(sid, "necroWarden"))
    assert len(res["refus_dans_le_disque"]) >= 5, \
        "regime trop faible (%d refus) : « zone = disque » serait presque indiscernable" \
        % (len(res["refus_dans_le_disque"]),)
    assert set(map(tuple, res["delta_sans_los"])) == set(map(tuple, res["refus_dans_le_disque"])), \
        "le predicat doit retirer EXACTEMENT ce que le natif refuse : %r vs %r" \
        % (res["delta_sans_los"], res["refus_dans_le_disque"])
    assert res["exact"], "FP=%r FN=%r" % (res["faux_positifs"], res["faux_negatifs"])


def test_indirect_fire_exempts_the_caster_from_the_elevation_volet(sid):
    """`astraOrdnance`, kit NATIF : le seul porteur du pool a la fois `IndirectFire` et
    `UseWholeBoard` sans gate (`1026 BasiliskBarrage`).

    `TargetingQuery$$GetTilesObscuringTerrain` teste `HasTrait(caster, 0x3ed)` AVANT le bit 25 :
    le volet ELEVATION tombe, et le natif lui laisse tout le plateau. L'accord serait DEGENERE
    (les deux cotes disent « tout ») si l'on ne montrait pas que le trait est ce qui le produit --
    d'ou le contrefactuel : un port qui l'aurait OUBLIE retrecirait la zone."""
    res = _ok(L.sweep_normal_attack(sid, "astraOrdnance"))
    for d, (n, tot) in res["par_distance"].items():
        assert n == tot, "d = %d : le plateau ENTIER est attendu, lu %d/%d" % (d, n, tot)
    assert res["delta_sans_trait"], \
        "contrefactuel VIDE : oublier `IndirectFire` ne changerait rien ici -- le trait n'est pas " \
        "exerce par ce montage, le relire"
    assert res["exact"], "FP=%r FN=%r" % (res["faux_positifs"], res["faux_negatifs"])


def test_walls_block_the_line_and_the_isWall_channel_is_what_makes_it_exact(sid):
    """Le volet MURS, ISOLE -- et c'est le trait qui l'isole.

    `C6_17` porte SIX tuiles `HulkWall` (`TileComponent+0x41`). `astraOrdnance` y a `IndirectFire`,
    donc `ObscuringType == 4` : le volet ELEVATION tombe et **seul un MUR peut encore bloquer**.
    Tout refus mesure ici est donc attribuable au mur, sans partage.

    ⚠ LE MONTAGE EST FORCE, pas subi : avec la premiere paire walkable venue `(0,0)/(0,3)`, aucun
    mur ne se trouve sur une ligne et le natif rend 36/36 -- un accord DEGENERE. Le probe DEPLACE
    donc les unites vers la paire qui maximise les obstructions.

    Le contrefactuel `delta_sans_murs` chiffre ce que le canal `boardGraph.isWall` apporte : sans
    lui, le port sur-attribuerait exactement les tuiles que le natif refuse."""
    L.set_board("C6_17")
    try:
        res = _ok(L.sweep_normal_attack(sid, "astraOrdnance"))
    finally:
        L.set_board("MC1_67")
    assert res["indirect_fire"] is True, "le montage repose sur `IndirectFire` du porteur"
    assert res["n_walls_board"] > 0, "C6_17 doit publier des murs, sinon le canal est casse"
    assert res["refus_dans_le_disque"], \
        "regime DEGENERE : le natif accepte tout -- aucun mur ne coupe une ligne, le montage " \
        "n'isole rien"
    assert res["delta_sans_murs"], \
        "contrefactuel VIDE : la carte des murs ne change rien ici, le volet n'est pas exerce"
    assert set(map(tuple, res["delta_sans_murs"])) == set(map(tuple, res["refus_dans_le_disque"])), \
        "les tuiles que le natif refuse doivent etre EXACTEMENT celles que la carte des murs " \
        "retire : %r vs %r" % (res["delta_sans_murs"], res["refus_dans_le_disque"])
    assert res["exact"], "FP=%r FN=%r" % (res["faux_positifs"], res["faux_negatifs"])
