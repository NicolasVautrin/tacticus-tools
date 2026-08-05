"""LIVE #433-r4-r2-r1-r2-r2-r1-r1-r1-r4 -- le 4e gate CASTER confronte a l'ORACLE NATIF.

L'ORACLE. `abilityReason` invoque `IdunBattle.Core.Services.AttackQuery$$GetInvalidCasterReason(
caster, getUnitMainTile(caster), ability)` et rend le masque `TargetingRule` rompu, EN NOMS. C'est
la cascade COMPLETE (marches a..g), donc le juge exact de ce que ce module porte -- et le seul canal
qui dise QUELLE regle mord, la ou un ensemble de tuiles ne dit que « rien verse ».

DEUX VOLETS, et ils ne se remplacent pas :

  * `cascade` -- L'ETAGE EN LARGEUR. Toutes les paires (unite, ability a masque RE-lu) du runner,
    DEUX fois par tour : avant deplacement, puis apres (le flag `UnitFlag.Moved` est efface au debut
    de chaque tour par `UnitFlagsComponent$$RemoveTurnFlags`, donc la seule fenetre ou il vaut vrai
    est APRES un move et AVANT la fin du tour). Contrat de `probe_115` :
        natif == 0  =>  port == 0            STRICT -- le port n'invente JAMAIS un refus
        natif != 0  =>  port == natif, ou 0  ecart PERMISSIF, compte
    C'est CE volet qui a trouve le bug du prefixe : 11 paires sur 42 ou l'unite a BOUGE mais n'est
    pas du joueur courant -- le natif ACCEPTE, le port refusait.

  * `moved` -- LA REGLE `CasterHasNotMoved` AVEC SA CONTRE-EPREUVE. Un gate qui n'a jamais rougi ne
    prouve rien : on DEPLACE le porteur, on exige que le natif REFUSE et que le port refuse DU MEME
    CODE, puis on retire le bit du masque du port et on exige qu'il ACCEPTE.

Le montage vit dans `probe_433_r4_r2_r1_r2_r2_r1_r1_r1_r4_caster_reason.py` (probe = MESURE, test =
GARDE). Le volet ZONE (`--step live`, deux regimes MORD/PASSE sur `1045`) reste au probe : il coute
un runner de plus et ~26 tours, hors budget d'une passe ciblee.

ASCII only. Detail : `docs/rl/case-433-r4-r2-r1-r2-portees.md`.
"""
from __future__ import annotations

import pytest

import probe_433_r4_r2_r1_r2_r2_r1_r1_r1_r4_caster_reason as PROBE
from engine.runner.abilities.targeting_rule import TargetingRule as TR


@pytest.fixture(scope="module")
def cascade(live_session) -> dict:
    res = PROBE.cascade(live_session, PROBE.BOARD,
                        ("orksWarboss,bloodDante,astraOrdnance,bloodIntercessor,spaceBlackmane",
                         "orksNob,templSwordBrother,bloodMephiston,tyranDeathleaper,astraDreir"),
                        tours=2)
    if res.get("error"):
        pytest.fail("montage cascade KO : %s" % res["error"], pytrace=False)
    return res


@pytest.fixture(scope="module")
def moved(live_session) -> dict:
    res = PROBE.moved(live_session)
    if res.get("error"):
        pytest.fail("montage moved KO : %s" % res["error"], pytrace=False)
    return res


def _paires(res):
    return [d for d in (res.get("paires") or []) if d.get("natif") is not None]


# ------------------------------------------------------------------------------------------------
# VOLET 1 -- l'etage, en largeur
# ------------------------------------------------------------------------------------------------

def test_le_montage_exerce_vraiment_la_regle(cascade):
    """SANS CETTE GARDE, tout le fichier serait vert sur un montage qui n'arme rien. On exige que
    des unites aient REELLEMENT bouge, que le natif ait REELLEMENT refuse au moins une fois, et que
    la separation « a bouge / c'est son tour » soit exercee DANS LES DEUX SENS."""
    p = _paires(cascade)
    assert len(p) >= 30, "trop peu de paires confrontees : %d" % len(p)
    bouge = [d for d in p if d.get("moved") is True]
    assert bouge, "aucune unite n'a bouge -- la regle CasterHasNotMoved n'est pas exercee"
    porteurs = [d for d in bouge if int(d["rules"], 16) & int(TR.CasterHasNotMoved)]
    assert porteurs, "aucune paire (a bouge + porte le bit)"
    assert any(int(d["natif"]) == int(TR.CasterHasNotMoved) for d in porteurs), \
        "le natif n'a JAMAIS refuse : le montage ne separe rien"
    assert any(int(d["natif"]) == 0 for d in porteurs), \
        "le natif n'a JAMAIS accepte une unite qui a bouge : le prefixe IsTurnOfUnit n'est pas " \
        "exerce, et le test ne distinguerait pas les deux ports"


def test_le_port_n_invente_AUCUN_refus(cascade):
    """LE CONTRAT STRICT. Natif valide => port valide. C'est la moitie du contrat qui a rougi avant
    la correction du prefixe (11 refus inventes), et la seule dont la degradation soit
    RESTRICTIVE -- donc invisible en self-play et exploitable a l'entrainement."""
    faux = [d for d in _paires(cascade) if int(d["natif"]) == 0 and int(d["port"] or 0) != 0]
    assert faux == [], "refus INVENTES : %r" % [
        {k: d[k] for k in ("unit", "ability", "moved", "port")} for d in faux[:10]]


def test_quand_le_port_refuse_il_refuse_du_MEME_code(cascade):
    """L'autre moitie : un refus porte doit etre le MEME `TargetingRule` que le natif, pas « un
    refus quelconque ». Un port qui rendrait un bit voisin passerait le test precedent."""
    faux = [d for d in _paires(cascade)
            if int(d["port"] or 0) != 0 and int(d["port"]) != int(d["natif"])]
    assert faux == [], "refus FAUX : %r" % [
        {k: d[k] for k in ("unit", "ability", "natif", "natif_noms", "port")} for d in faux[:10]]


def test_la_separation_est_exactement_has_moved_ET_is_turn_of_unit(cascade):
    """LE DISCRIMINANT DU PREFIXE, enonce comme une PARTITION et non comme un compte : sur les
    porteurs du bit, le natif rend `CasterHasNotMoved` si et seulement si l'unite a bouge ET c'est
    le tour de son proprietaire d'ORIGINE (`BattleQuery$$IsTurnOfUnit`)."""
    tour = {}
    for d in _paires(cascade):
        if int(d["rules"], 16) & int(TR.CasterHasNotMoved) and d.get("moved") is not None:
            refuse = int(d["natif"]) == int(TR.CasterHasNotMoved)
            tour.setdefault((bool(d["moved"]), refuse), 0)
            tour[(bool(d["moved"]), refuse)] += 1
    assert tour.get((False, True), 0) == 0, \
        "le natif refuse une unite qui n'a PAS bouge : %r" % (tour,)
    assert tour.get((True, True), 0) > 0 and tour.get((True, False), 0) > 0, \
        "les deux moities du prefixe ne sont pas exercees : %r" % (tour,)


def test_UnitFlag_Moved_n_a_pas_ete_renumerote(cascade):
    """Le probe REFUSE si l'id lu au runtime (`combatSnapshot.unitFlagTypes`) differe de celui
    d'`enums.tsv`. Une renumerotation au prochain build doit rougir, pas passer en silence."""
    assert not cascade.get("error")
    assert PROBE.UNIT_FLAG_MOVED == 0


# ------------------------------------------------------------------------------------------------
# VOLET 2 -- la regle, avec sa contre-epreuve
# ------------------------------------------------------------------------------------------------

def _phases(res):
    ph = {d.get("phase"): d for d in (res.get("phases") or [])}
    for k in ("avant", "apres"):
        if k not in ph or ph[k].get("error"):
            pytest.fail("phase %s absente : %r" % (k, ph.get(k)), pytrace=False)
    return ph["avant"], ph["apres"]


def test_le_porteur_a_REELLEMENT_bouge(moved):
    """Le montage avant la mesure : sans deplacement effectif, « le natif refuse » ne dirait rien."""
    av, ap = _phases(moved)
    assert av["has_moved"] is False and ap["has_moved"] is True
    assert tuple(av["pos"]) != tuple(ap["pos"])
    assert int(moved["rules"], 16) & int(TR.CasterHasNotMoved), \
        "le porteur choisi ne porte pas le bit : %s" % moved["rules"]


def test_avant_le_move_les_deux_acceptent(moved):
    """LE TEMOIN. Sans lui, un port qui refuserait TOUJOURS passerait le test suivant."""
    av, _ap = _phases(moved)
    assert int(av["natif"]) == 0 and int(av["port"] or 0) == 0


def test_apres_le_move_le_natif_ET_le_port_refusent_du_meme_code(moved):
    """LE LIVRABLE."""
    _av, ap = _phases(moved)
    assert ap["natif_noms"] == ["CasterHasNotMoved"]
    assert int(ap["natif"]) == int(TR.CasterHasNotMoved)
    assert int(ap["port"]) == int(TR.CasterHasNotMoved)


def test_contre_epreuve_sans_le_bit_du_masque_le_port_ACCEPTE(moved):
    """LA CONTRE-EPREUVE, sur la mesure DEJA PRISE. On retire le bit `CasterHasNotMoved` du masque
    -- « et si le natif ne l'armait pas ? », le reste de la cascade continuant de s'appliquer -- et
    on exige que le port accepte. Un gate dont on ne sait pas produire l'ACCEPTATION ne prouve pas
    qu'il gate : il pourrait refuser pour une tout autre raison."""
    _av, ap = _phases(moved)
    assert int(ap["port_sans_la_regle"] or 0) == 0, \
        "le port refuse encore sans le bit -- son refus ne vient pas de cette regle"
