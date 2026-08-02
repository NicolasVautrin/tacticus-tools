"""#456-r1 -- gardes OFFLINE des deux fermetures : le playbook 1145 (cause a) et le kit declenche
REEL des foyers runner/scene (cause b).

Ce fichier GARDE ; `probe_456r1_move_kit_vs_playbook.py` MESURE. Les fonctions de verdict du probe
sont PURES, donc exercees ici sans live -- y compris leurs trois etats, que la mesure live ne
produit pas tous dans une meme bataille.

ASCII only.
"""
from __future__ import annotations

import os
import sys

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(_HERE)))   # scripts/python

from engine.entities.triggered_ability_type import (                        # noqa: E402
    TriggeredAbilityType, entity_triggered_ability_ids, triggered_ability_ids)
from engine.entities.unit_context import UnitContext                        # noqa: E402
from engine.playbook.adjacent_unit_preference import (                      # noqa: E402
    TRIGGERED_MOVE_PLAYBOOKS, load_playbook)
from engine.playbook.serene_unifier import (                                # noqa: E402
    SERENE_UNIFIER_PER_ADJACENT_FRIEND, SereneUnifierPlaybook)

import probe_456r1_move_kit_vs_playbook as P                                # noqa: E402


# --------------------------------------------------------------- (a) le playbook 1145

def _ctx(friends, self_pos=None, uid=1, elev=None):
    return {"uid": uid, "self_pos": self_pos, "elev_by_pos": elev,
            "friend_units": [{"id": i, "pos": p} for i, p in friends],
            "enemy_units": []}


def test_le_registre_MOVE_charge_bien_1145():
    """Le patron le plus frequent de cette famille est le mold porte et JAMAIS dispatche : le
    playbook existe, le registre l'ignore, et l'inertie se lit comme « pas de bug »."""
    pb = load_playbook(int(TriggeredAbilityType.SereneUnifier))
    assert isinstance(pb, SereneUnifierPlaybook), (
        "1145 doit etre CHARGE par `load_playbook` -- un playbook hors registre est INERTE")
    assert TRIGGERED_MOVE_PLAYBOOKS[int(TriggeredAbilityType.SereneUnifier)] is pb


def test_le_facteur_est_le_LITTERAL_101_pas_un_poids_BC():
    """`imul eax, 0x65` dans `<CalculateMovementUtilityInStepsInternal>d__1$$MoveNext` : aucune
    `GetUtilityValue(<cle>)` n'apparait dans le corps. Une cle inventee serait une fausse verite."""
    assert SERENE_UNIFIER_PER_ADJACENT_FRIEND == 101


def test_101_par_ami_ADJACENT_a_la_tuile_candidate():
    pb = SereneUnifierPlaybook()
    # tuile candidate (5,5) ; deux amis en ring-1, un ami a distance 2.
    ctx = _ctx([(2, (5, 4)), (3, (6, 5)), (4, (5, 7))])
    assert pb.calculate_movement_utility_in_steps((5, 5), ctx, None) == 202.0


def test_le_MOVER_est_EXCLU_du_comptage():
    """`units.RemoveAll(u => u.Id == case.Unit.Id)`. `GetAdjacentFriends` travaille par TUILE et ne
    connait pas la notion de « soi » : sans ce retrait, l'unite se compterait elle-meme des que son
    origine tombe en ring-1 de la tuile candidate (c'est le terme que la famille
    `friends_in_range` conserve, et que celle-ci neutralise)."""
    pb = SereneUnifierPlaybook()
    sans = pb.calculate_movement_utility_in_steps((5, 5), _ctx([(2, (5, 4))]), None)
    # MEME etat, mais l'origine du mover (uid=1) est elle aussi en ring-1 de la tuile candidate.
    avec = pb.calculate_movement_utility_in_steps(
        (5, 5), _ctx([(2, (5, 4))], self_pos=(6, 5)), None)
    assert sans == 101.0
    assert avec == 101.0, (
        "l'origine du mover ne doit RIEN ajouter -- le `RemoveAll` par Id la retire")


def test_le_retrait_par_ID_ne_retire_QUE_le_mover():
    """Contre-epreuve du predicat : un ami DISTINCT sur la meme tuile-voisine que l'origine du
    mover doit rester compte. Un retrait par POSITION (ou par visualId) le perdrait."""
    pb = SereneUnifierPlaybook()
    ctx = _ctx([(2, (6, 5))], self_pos=(6, 5))     # ami u2 et mover u1 sur la MEME position
    assert pb.calculate_movement_utility_in_steps((5, 5), ctx, None) == 101.0


def test_la_porte_d_ELEVATION_native_s_applique():
    """`TileQuery.<IterateAdjacentTiles>d__8$$MoveNext` : gate INCONDITIONNEL `abs(delta) < 2`.
    Un port sur `hexgeo.distance == 1` nu compterait le voisin surleve (#271)."""
    pb = SereneUnifierPlaybook()
    elev = {(5, 5): 0, (5, 4): 3, (6, 5): 0}
    ctx = _ctx([(2, (5, 4)), (3, (6, 5))], elev=elev)
    assert pb.calculate_movement_utility_in_steps((5, 5), ctx, None) == 101.0, (
        "le voisin a |delta elev| = 3 doit etre EXCLU")


def test_aucun_ami_adjacent_rend_ZERO():
    pb = SereneUnifierPlaybook()
    assert pb.calculate_movement_utility_in_steps((5, 5), _ctx([(2, (9, 9))]), None) == 0.0
    assert pb.calculate_movement_utility_in_steps((5, 5), _ctx([]), None) == 0.0


def test_les_poids_BC_ne_sont_PAS_lus():
    """Le corps natif n'appelle aucun scorer : passer un `wt` qui LEVE ne doit rien changer."""
    class _Boom:
        def sub(self, *_a):
            raise AssertionError("le corps natif ne lit AUCUN poids BC")

    pb = SereneUnifierPlaybook()
    assert pb.calculate_movement_utility_in_steps((5, 5), _ctx([(2, (5, 4))]), _Boom()) == 101.0


# --------------------------------------------------------------- (b) le kit declenche d'ENTITE

def test_kit_TRI_ETAT_none_retombe_sur_le_gameconfig():
    """`triggered_abilities is None` = canal NON MESURE -> repli gameconfig, comportement
    strictement d'avant #456-r1."""
    uc = UnitContext(entity_id=7, visual_id="tauAunShi")
    assert uc.triggered_abilities is None
    assert entity_triggered_ability_ids(uc, "tauAunShi") == triggered_ability_ids("tauAunShi")
    assert entity_triggered_ability_ids(None, "tauAunShi") == triggered_ability_ids("tauAunShi")


def test_kit_MESURE_fait_AUTORITE_et_peut_RETIRER():
    """C'est le point qui distingue REMPLACEMENT et UNION -- et l'union est FAUSSE dans le sens qui
    compte. Mesure #456-r1 : `tauCrisis` greffe porte `[1120, 1030]` a son `AbilitiesComponent`,
    la ou le gameconfig annonce `[1133]`. Une union ferait iterer 1133, que la bataille n'a PAS
    monte."""
    uc = UnitContext(entity_id=7, visual_id="tauCrisis")
    uc.triggered_abilities = [1120, 1030]
    got = entity_triggered_ability_ids(uc, "tauCrisis")
    assert got == [1120, 1030]
    assert 1133 not in got, "le kit MESURE doit pouvoir RETIRER un passif du gameconfig"


def test_kit_MESURE_VIDE_est_une_mesure_pas_une_absence():
    """`[]` = « cette unite n'a AUCUN passif monte » -- ca doit se distinguer de `None`."""
    uc = UnitContext(entity_id=7, visual_id="tauAunShi")
    uc.triggered_abilities = []
    assert entity_triggered_ability_ids(uc, "tauAunShi") == []
    assert triggered_ability_ids("tauAunShi"), "le temoin gameconfig doit etre NON vide"


def test_le_seed_lit_TOUTES_les_hierarchies():
    """`_load_triggered_abilities` mirror la collection ENTIERE du `TriggeredAbilityComponent` : le
    dispatcher natif ne filtre par aucune hierarchie (2 = passif de kit, 3 = relique). Les deux
    seeds voisins, eux, filtrent -- ils servent d'autres consommateurs."""
    from engine.runner.snapshot import _load_triggered_abilities

    class _Ctx:
        triggered_abilities = None

    class _Sc:
        ctx = _Ctx()

    class _Ent:
        def get_component(self, _k):
            return self._sc
        _sc = _Sc()

    class _State:
        def __init__(self):
            self.e = _Ent()

        def get_entity(self, _uid):
            return self.e

    st = _State()
    payload = {"units": [{"entityId": 42, "triggered": [
        {"raw": [1145] + [0] * 9 + [2, 0]},        # hierarchie 2 (passif de kit)
        {"raw": [1457] + [0] * 9 + [3, 0]},        # hierarchie 3 (RELIQUE)
        {"raw": [1145] + [0] * 9 + [2, 0]},        # doublon -> une seule entree (`TryAdd`)
    ]}]}
    assert _load_triggered_abilities(st, payload) == 1
    assert st.e._sc.ctx.triggered_abilities == [1145, 1457]


def test_le_seed_garde_un_id_HORS_ENUM():
    """Le dispatcher natif presente TOUT id a `PlaybookDatabase$$LoadPlaybook`, qui rend null et le
    skippe. Faire disparaitre l'entree cote port changerait le CARDINAL du kit, pas seulement son
    contenu -- et masquerait un enum perime."""
    from engine.runner.snapshot import _load_triggered_abilities

    class _Ctx:
        triggered_abilities = None

    class _Sc:
        ctx = _Ctx()

    class _Ent:
        _sc = _Sc()

        def get_component(self, _k):
            return self._sc

    class _State:
        e = _Ent()

        def get_entity(self, _uid):
            return self.e

    st = _State()
    inconnu = 999_999
    assert inconnu not in TriggeredAbilityType._value2member_map_
    _load_triggered_abilities(st, {"units": [{"entityId": 1,
                                              "triggered": [{"raw": [inconnu] + [0] * 11}]}]})
    assert st.e._sc.ctx.triggered_abilities == [inconnu]


# --------------------------------------------------------------- verdicts PURS du probe

def _row(uid, nat, port, sans, nat_owner=(0.0,)):
    return {"unitId": uid, "visualId": "u%d" % uid, "kit_natif": list(nat),
            "kit_port": list(port), "sans_playbook": list(sans), "nat_owner": list(nat_owner)}


def test_verdict_cause_b_est_DECIDABLE_sans_valeur():
    v = P.check_kit_gap([_row(81, [1120, 1030], [1133], [1030], [0.0, 20.0])])
    assert v["status"] == "gap"
    assert v["cause_b"] == {81: [1120, 1030]}


def test_verdict_cause_a_ECARTEE_quand_le_natif_rend_ZERO_partout():
    """LE point que #456 avait manque : une ability sans playbook cote port n'est un trou que si le
    natif, lui, en charge un. `nat_owner == {0.0}` prouve qu'il la skippe AUSSI."""
    v = P.check_kit_gap([_row(85, [1143, 1051], [1143, 1051], [1143, 1051], [0.0])])
    assert v["status"] == "ok"
    assert v["cause_a"] == {} and v["ecarte"] == {85: [1143, 1051]}


def test_verdict_cause_a_SUSPECTE_quand_le_natif_est_NON_NUL():
    v = P.check_kit_gap([_row(83, [1145], [1145], [1145], [0.0, 101.0])])
    assert v["status"] == "gap"
    assert v["cause_a"] == {83: [1145]}


def test_verdict_refuse_de_conclure_sur_un_canal_MUET():
    """Kit natif vide partout = `unitAbilityStates` muet. « vide == vide » passerait, et ce serait
    un accord DEGENERE -- exactement le vice que #456 ferme sur l'axe valeur."""
    assert P.check_kit_gap([])["status"] == "no-rows"
    assert P.check_kit_gap([_row(1, [], [], [])])["status"] == "degenerate"


@pytest.mark.parametrize("nat,port,attendu", [
    ([1120], [1120], False),          # identiques -> pas de (b)
    ([1120, 1030], [1120], True),     # natif PLUS large
    ([1120], [1120, 1133], False),    # port plus large : (b) ne le voit pas -- c'est E4 qui mord
])
def test_verdict_cause_b_ne_regarde_QUE_ce_que_le_natif_a_en_plus(nat, port, attendu):
    """(b) est defini comme `kit_natif \\ kit_port` : un port PLUS LARGE n'est pas un trou de canal,
    c'est une iteration en trop -- elle ne se voit qu'a la VALEUR (le port ajouterait un terme que
    le natif ne verse pas), et seulement si l'ability surnumeraire a un playbook porte."""
    v = P.check_kit_gap([_row(1, nat, port, [], [0.0, 1.0])])
    assert bool(v["cause_b"]) is attendu
