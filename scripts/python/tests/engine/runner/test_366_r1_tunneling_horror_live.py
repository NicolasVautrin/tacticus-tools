"""GARDE LIVE #366-r1 -- le cast de `TunnelingHorror` (1011) CONFRONTE au natif.

LE CRITERE, en une question binaire : **apres un cast de 1011, le caster est-il encore sur le
plateau ?** -- posee au NATIF et au PORT sur le MEME etat de depart. Avant ce foyer, le port
repondait « oui » (position INCHANGEE, aucune tuile marquee) : un NO-OP SILENCIEUX -- ni erreur, ni
crash, donc invisible en self-play.

Le montage vit dans `scripts/python/probe_366_r1_tunneling_horror.py` (`run()`) ; ce fichier n'est
que sa PORTE pytest, comme `psychic_aoe_case`/`overkill_gate_case` pour leurs probes. Ce que `run()`
fait :

  * BUILD isole avec GREFFE de 1011 sur DEUX heros du pool (`necroDestroyer`, `necroOverlord`) dans
    une COPIE du seed BC -- le porteur reel `necroSmnDestroyer` est un SUMMON **sans invocateur
    d'unite** (recours 3 de `docs/rl/case-92-catalog-injection.md` §5bis). Greffe legitime :
    `gameconfig.ability("TunnelingHorror")` n'a AUCUNE variable ni constante, et le behaviour ne lit
    ni stat, ni trait, ni arme du caster.
  * CIBLE = la tuile legale la plus ELOIGNEE des deux casters, TEMOIN = la suivante.
  * CAPTURE de l'etat pre-cast -> rejeu OFFLINE par la voie COMPLETE (`Runner.apply(
    ActiveAbilityMessage)` : gates de ciblage, `On(0x2b)`, behaviour, flags de tour) -> cast LIVE ->
    RECHARGEMENT de l'etat natif d'apres -> comparaison terme a terme.

⚠ Un montage qui ne s'installe pas ECHOUE, il ne skippe pas (#268) : un `pytest.skip` sur un regime
non atteint est un VERT qui ment. Seule l'indisponibilite du HARNAIS (pas de session Frida) skippe,
et c'est `live_session` qui la porte.

RE : `docs/rl/case-366-r1-tunneling-horror-pending-summon.md`. ASCII only. Aucune VA en dur.
"""
from __future__ import annotations

import pytest

import probe_366_r1_tunneling_horror as P

TUNNELING = 1011
PENDING = 1113


@pytest.fixture(scope="module")
def tunneling_case(live_session):
    """Le montage, UNE fois pour tout le fichier (un build + un cast live). Le runner est DISPOSE
    par `run()` en sortie, donc rien a liberer au teardown."""
    return P.run()


def test_the_caster_leaves_the_board_on_both_sides(tunneling_case):
    """LA question binaire. `pos`/`feet` doivent devenir vides des DEUX cotes -- et le caster rester
    VIVANT : `RemoveUnitFromTilesOperation` est un retrait de TUILES, pas une mort ni un despawn
    (ni PV touches, ni flag `Dead`, ni flag `Removed`)."""
    c = tunneling_case
    assert c["before"]["pos"] is not None, "montage: le caster n'etait pas sur le plateau AVANT"
    assert c["native"]["pos"] is None and c["native"]["feet"] == [], (
        "le caster NATIF garde une position apres 1011 : %r" % (c["native"],))
    assert c["port"]["pos"] is None and c["port"]["feet"] == [], (
        "le caster PORTE garde sa position -- le cast est reste un no-op : %r" % (c["port"],))
    assert c["native"]["alive"] is True and c["port"]["alive"] is True


def test_the_bond_lands_on_the_targeted_tile_only_on_both_sides(tunneling_case):
    """L'`AddBondEffect` du 3e `Execute` : l'effet 1113 marque la tuile visee, et elle SEULE."""
    c = tunneling_case
    assert c["native"]["marked"] == [c["target"]], (
        "tuiles marquees cote natif = %r" % (c["native"]["marked"],))
    assert c["port"]["marked"] == c["native"]["marked"]


def test_port_and_native_states_agree_term_by_term(tunneling_case):
    """La confrontation complete -- `run()` accumule les ecarts dans `fails` (ce test les REND, il
    ne les re-derive pas : le montage est la source unique)."""
    c = tunneling_case
    assert c["fails"] == [], "ECARTS port <-> natif : %r" % (c["fails"],)


def test_the_ability_actually_executed_offline(tunneling_case):
    """ANTI-TAUTOLOGIE. Le test precedent compare deux etats ; il serait VERT aussi si le port
    n'avait RIEN execute et que le natif n'avait rien fait non plus (montage degenere). On exige
    donc que l'execution ait EU LIEU cote port : ability trouvee au registre (`ported: True`), gate
    de cible NON declenche, et au moins un `AddBondEffect` emis."""
    last = tunneling_case["last"]
    assert last.get("ported") is True, "1011 non executee offline : %r" % (last,)
    assert "invalid_target" not in last, "cast refuse par le gate de cible : %r" % (last,)
    assert last.get("posed"), "aucun `AddBondEffect` emis : %r" % (last,)


def test_the_marker_is_read_by_the_targeting_gate(tunneling_case):
    """E3, le DISCRIMINANT : `GetDynamicInvalidTargetReason` = `HasEffect(target, 0x459)` exclut la
    tuile marquee des cibles legales du SECOND porteur, et le temoin y reste. Sans ce bras, la pose
    ne changerait AUCUN resultat observable. (`run()` a deja joue la mesure ; `fails` la porte.)"""
    c = tunneling_case
    assert not [f for f in c["fails"] if f.startswith("E3")], (
        "le marqueur n'est pas LU par le gate de ciblage : %r" % (c["fails"],))
