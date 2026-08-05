"""#429-r1-r3 -- LE GATE DE MESSAGE : un cast sur un CADAVRE n'atteint jamais l'operation.

CE QUI EST GARDE ICI, ET EN QUOI CE N'EST PAS #429-r1
-----------------------------------------------------
`IdunBattle.Messages.InputMessageProcessor$$Visit(ActiveAbilityMessage)` teste
`IdunBattle.Entities.UnitExtensions$$IsAliveAndNotFled` sur le CASTER puis sur la CIBLE, AVANT
`RunPhase` -- donc avant l'ouverture du groupe de stream `User_UseAbility` et avant
`Core.Services.OperationProcessor$$ActiveAbility`. Ce gate NE LIT NI l'ability NI ses
`TargetingOptions` : il ne DEROGE pour personne.

C'est la derniere divergence de la famille #429 : `GreatFrostAxe` (1089), unique porteur du bit 38
`AllowDeadTarget`, echappe CORRECTEMENT au gate d'OPERATION
(`ActiveAbilityOperation$$IsDeadUnitAndNotAllowedByAbility`, #429-r1) -- et le natif le refuse un
cran plus haut, ici.

L'ATTRIBUTION D'ETAGE EST MESUREE, pas deduite : le compte d'EVENEMENTS DE STREAM separe les deux
rangs, et le bras TEMOIN (refus au rang de l'OPERATION) est ce qui rend « 0 evenement »
interpretable. Sans lui, un zero pourrait venir de n'importe quel refus.

⚠ LES TIRAGES RNG NE DISCRIMINENT RIEN ICI : l'arbre de 1089 est
`op_and(AddEffect(Ice), If(IsAlive(target), attaque))` -- sur un cadavre la garde `IsAlive` eteint
deja l'attaque, donc 0 tirage des DEUX cotes, gate ou pas. Les observables qui mordent sont la
GLACE et les FLAGS DE TOUR.

LIVE-agreement, ASCII only. Cf. docs/rl/case-429r1r3-gate-message-cible-morte.md.
"""
from __future__ import annotations

import pytest

import probe_429r1r3_dead_target_message_gate as P
from engine.runner.components import UnitFlagsComponent, is_alive_and_not_fled, unit_is_dead
from engine.runner.state import Entity


@pytest.fixture(scope="module")
def signature(live_session, tmp_path_factory):
    sf = tmp_path_factory.mktemp("t429r1r3s") / "state.json"
    r = P.scenario_signature(str(sf), seed="777", board="MC1_67", verbose=False)
    if r.get("why"):
        pytest.fail("montage SIGNATURE non installe : %s" % r["why"], pytrace=False)
    return r


@pytest.fixture(scope="module")
def port(live_session, tmp_path_factory):
    sf = tmp_path_factory.mktemp("t429r1r3p") / "state.json"
    r = P.scenario_port(str(sf), seed="777", board="MC1_67", verbose=False)
    if r.get("why"):
        pytest.fail("montage PORT non installe : %s" % r["why"], pytrace=False)
    return r


@pytest.fixture(scope="module")
def port_seed2(live_session, tmp_path_factory):
    """GENERALISATION : meme montage, autre seed. Le discriminant est structurel (la glace part ou
    ne part pas), donc il doit etre INSENSIBLE au seed."""
    sf = tmp_path_factory.mktemp("t429r1r3g") / "state.json"
    r = P.scenario_port(str(sf), seed="31337", board="MC1_67", verbose=False)
    if r.get("why"):
        pytest.fail("montage PORT seed 31337 non installe : %s" % r["why"], pytrace=False)
    return r


# ---------------------------------------------------------------------------------------------
def test_le_montage_pose_bien_un_cadavre_positionne(port):
    """Prealable. Un cadavre SANS position ferait refuser le port pour une autre raison (portee) et
    la mesure ne discriminerait plus rien."""
    assert port["cadavre_alive"] is False, "la cible doit etre MORTE"
    assert port["cadavre_pos"] is not None, "le cadavre doit garder une position"


def test_le_refus_natif_est_EN_AMONT_de_l_operation(signature):
    """L'ATTRIBUTION D'ETAGE, et son TEMOIN. Le groupe de stream `User_UseAbility` (12) est ouvert
    par la lambda du Visit, donc APRES son gate et AVANT l'operation :
      * un refus au rang de l'OPERATION (cast hors portee sur une cible VIVANTE) l'OUVRE ;
      * le refus cible-morte ne l'ouvre PAS.
    Les deux bras viennent du MEME montage et du MEME caster : la seule variable est la cible."""
    temoin = signature["vivant_hors_portee"]
    assert temoin["events"] == 2 and 12 in (temoin["groups"] or []), (
        "TEMOIN casse : un refus au rang de l'OPERATION doit OUVRIR le groupe User_UseAbility, "
        "obtenu %s -- sans lui, `0 evenement` sur le cadavre ne prouverait aucun etage" % temoin)
    for bras in ("cadavre_1089", "cadavre_normale", "cadavre_1003"):
        m = signature[bras]
        assert m["events"] == 0 and not m["groups"], (
            "%s : le gate de MESSAGE ne doit ouvrir AUCUN groupe, obtenu %s" % (bras, m))
        assert m["mutated"] is False and m["action_consumed"] is False


def test_le_gate_ne_mord_PAS_sur_une_cible_TUILE(signature):
    """`IsAliveAndNotFled` SAUTE le test de mort quand `TryGetComponent<HealthComponent>` echoue :
    une entite-TUILE le passe. Mesure : le meme cast, sur la TUILE du cadavre, OUVRE bien le groupe
    (son refus vient alors de l'operation). C'est la contre-epreuve qui interdit de porter le gate
    en « toute cible sur une tuile occupee par un mort »."""
    m = signature["cadavre_tuile_1089"]
    assert m["events"] == 2 and 12 in (m["groups"] or []), (
        "cible TUILE : le gate de message ne doit pas mordre, obtenu %s" % m)


def test_le_natif_no_oppe_completement(port):
    """NATIF : aucun evenement, aucune mutation, action NON consommee -- le cast n'a laisse AUCUNE
    trace, pas meme la glace que le port posait."""
    assert port["natif"]["events"] == 0
    assert port["natif"]["mutated"] is False
    assert port["natif"]["draws"] == 0
    assert port["natif_caster_has_action"] is True, (
        "natif : le caster doit GARDER son action -- un cast execute la consommerait")


def test_le_port_refuse_par_le_gate_de_MESSAGE_et_ne_pose_rien(port):
    """PORT : le refus vient du gate de MESSAGE (role `target`), et il ne laisse RIEN -- ni glace,
    ni flags de tour."""
    assert port["port_gate_role"] == "target", (
        "le port doit sortir par le gate de message sur la CIBLE, obtenu %s" % port["port_last"])
    assert port["port_iced"] == 0, "aucune tuile de glace ne doit etre posee"
    assert port["port_flags"] is False, "aucun flag de tour ne doit etre pose"


def test_contre_epreuve_sans_le_gate_le_port_posait_la_glace_ET_le_tour(port):
    """LA MORSURE. Gate neutralise AU FOYER (`engine.runner.components.is_alive_and_not_fled`, que
    le handler importe PARESSEUSEMENT -- la substitution mord donc vraiment), le meme cast pose la
    glace et consomme le tour. Sans cette mesure, le vert precedent pourrait venir d'un montage
    inerte."""
    assert port["port_sans_gate_iced"] > 0, (
        "la mutation n'a pas mordu : sans le gate, le port doit poser la glace, obtenu %s tuiles"
        % port["port_sans_gate_iced"])
    assert port["port_sans_gate_flags"] is True, (
        "sans le gate, le port doit consommer le tour du caster")
    assert (port["port_sans_gate_last"] or {}).get("not_alive_and_not_fled") is None, (
        "gate cense etre neutralise")


def test_generalisation_autre_seed(port_seed2):
    """Le discriminant est STRUCTUREL (la glace part ou ne part pas), donc insensible au seed."""
    assert port_seed2["natif"]["events"] == 0
    assert port_seed2["port_gate_role"] == "target"
    assert port_seed2["port_iced"] == 0
    assert port_seed2["port_sans_gate_iced"] > 0, (
        "contre-epreuve inerte sur ce seed : %s" % port_seed2["port_sans_gate_iced"])


def test_le_gate_d_OPERATION_reste_inerte_pour_1089(port):
    """NON-REGRESSION du mirror pose par #429-r1 : le gate d'OPERATION, lui, DEROGE pour le porteur
    du bit 38. Les deux gates vivent a deux rangs differents et ne doivent pas fusionner -- si
    celui-ci se mettait a refuser 1089, on aurait ferme la divergence par le MAUVAIS mecanisme."""
    from engine.runner.abilities.handler import ABILITY_CLASSES
    from engine.runner.operations.active_ability import is_dead_unit_and_not_allowed_by_ability
    klass = ABILITY_CLASSES.get(P.ABILITY_GREAT_FROST_AXE)
    assert klass is not None and klass.can_continue_on_dead_target() is True
    # L'etat n'est pas rejoue ici : le predicat est offline, seule la classe compte.
    assert is_dead_unit_and_not_allowed_by_ability.__doc__ is not None
    assert (port["port_last"] or {}).get("dead_target_not_allowed") is None, (
        "1089 ne doit PAS sortir par le gate d'operation, obtenu %s" % port["port_last"])


# --- OFFLINE : le mirror lui-meme -------------------------------------------------------------
def _ent(hp=None, fled=False):
    from engine.runner.components import HealthComponent
    e = Entity(1)
    if hp is not None:
        e.add_component(HealthComponent(hp, 100))
    e.add_component(UnitFlagsComponent([UnitFlagsComponent.FLED] if fled else None))
    return e


def test_is_alive_and_not_fled_mirror_les_quatre_branches_du_decompile():
    """`IsAliveAndNotFled` n'est PAS la negation d'`IsDead`, et les quatre branches sont lues :
    null -> faux ; `HealthComponent.IsDead` -> faux ; flag 9 `UnitFlag.Fled` -> faux ; pas de
    `HealthComponent` (TryGet echoue) -> le test de mort est SAUTE."""
    assert is_alive_and_not_fled(None) is False
    assert is_alive_and_not_fled(_ent(hp=10)) is True
    assert is_alive_and_not_fled(_ent(hp=0)) is False
    assert is_alive_and_not_fled(_ent(hp=10, fled=True)) is False
    assert is_alive_and_not_fled(_ent(hp=None)) is True, (
        "entite sans HealthComponent : le natif saute le test de mort")


def test_les_deux_predicats_ne_sont_PAS_complementaires():
    """La ligne qui interdit de reutiliser `unit_is_dead` a la place : une unite FLED est refusee
    par le gate de MESSAGE alors qu'`IdunBattle.Entities.UnitExtensions$$IsDead` l'exclut
    EXPRESSEMENT de la mort."""
    fled = _ent(hp=0, fled=True)
    assert unit_is_dead(fled) is False, "IsDead exclut le flag Fled"
    assert is_alive_and_not_fled(fled) is False, "IsAliveAndNotFled le refuse quand meme"
