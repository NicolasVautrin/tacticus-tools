"""#365 -- le montage qui isole l'`origin` des batchs 3/4 doit rester DISCRIMINANT.

Ce que cette garde verrouille, et pourquoi elle existe
-----------------------------------------------------
`probe_361_adjacent_units_selector.py` conclut « `AdjacentUnits` est vivante dans le contexte de
`ComparablePlaybook<T>$$GenerateAttackPredictions` » a partir d'un ACCORD entre l'attendu et le
natif. Un accord ne vaut que si l'attendu aurait DIVERGE sur une lecture fausse : sinon le bras est
tautologique et son vert ne prouve rien.

La garde tient donc trois choses, 100 % OFFLINE :

  1. la table des bras reste celle du decompile -- `MortisRoundPlaybook`,
     `ExplosivePresentsPlaybook` et `RammingSpeedPlaybook` sont les SEULS appelants de
     `GenerateAttackPredictions`, leurs selecteurs sont cites VERBATIM, et chacun porte son ROLE :
     TEMOIN (origin FEUILLE : son accord etablit que la composition est operante) ou SUJET
     (`RammingSpeedPlaybook`, dont l'origin est l'arbre `GetTileToMoveTo()` -- le terme meme sur
     lequel porte la question, donc inutilisable comme temoin sans circularite) ;
  2. `expected_targets` RETIRE le caster (`op_Subtraction Caster@0x48`) quand il est adjacent a la
     cible, et la mutation `no-subtraction` le RAJOUTE -- donc les deux attendus DIFFERENT, ce qui
     est exactement ce qui a fait rougir le probe en live
     (« COMPTE DIFFERENT : 3 events pour 4 attendus ») ;
  3. la mutation `no-adjacency` ampute l'attendu de tout le voisinage -- l'autre terme que le bras
     doit discriminer.

Aucun runner, aucune session : le montage n'est sollicite que par sa fonction de derivation.
"""
from __future__ import annotations

import sys
from pathlib import Path

PYDIR = Path(__file__).resolve().parents[2]
if str(PYDIR) not in sys.path:
    sys.path.insert(0, str(PYDIR))

import montage_361_attack_predictions_selector as M  # noqa: E402


class _Board:
    """Board hex minimal : la cible en (1,1), ses six voisins par `hexgeo`."""

    def __init__(self):
        import hexgeo
        self._hex = hexgeo
        self._ids = {}
        for col in range(4):
            for row in range(4):
                self._ids[(col, row)] = col * 4 + row + 1
        self._pos = {v: k for k, v in self._ids.items()}

    def id_at(self, col, row):
        return self._ids.get((col, row))

    def coord(self, tid):
        return self._pos.get(tid)

    def neighbours(self, tid):
        c = self._pos[tid]
        return [self._ids[p] for p in self._hex.neighbors(*c) if p in self._ids]


def _dv(caster_pos):
    """Cible en (1,1) ; un ami et un ennemi sur deux de ses voisins ; caster ou on veut."""
    import hexgeo
    ring = [p for p in hexgeo.neighbors(1, 1) if 0 <= p[0] < 4 and 0 <= p[1] < 4]
    return {"units": [
        {"id": 1, "visualId": "caster", "alive": True, "team": 1,
         "pos": {"col": caster_pos[0], "row": caster_pos[1]}},
        {"id": 2, "visualId": "cible", "alive": True, "team": 2, "pos": {"col": 1, "row": 1}},
        {"id": 3, "visualId": "ami", "alive": True, "team": 1,
         "pos": {"col": ring[0][0], "row": ring[0][1]}},
        {"id": 4, "visualId": "ennemi", "alive": True, "team": 2,
         "pos": {"col": ring[1][0], "row": ring[1][1]}},
    ]}


def test_les_deux_temoins_sont_ceux_du_decompile():
    """Les TEMOINS sont les appelants de `GenerateAttackPredictions` dont l'origin est une FEUILLE.

    Egalite STRICTE : retirer un temoin, en ajouter un, ou reclasser le sujet en temoin fait
    rougir. C'est la propriete qui empeche un bras d'entrer sans qu'on ait dit ce qu'il temoigne.
    """
    assert {a.ability for a in M.ARMS.values() if a.role == "temoin"} == {1004, 1170}
    assert M.ARMS["control"].playbook == "MortisRoundPlaybook"
    assert M.ARMS["adjacent"].playbook == "ExplosivePresentsPlaybook"
    # Les selecteurs natifs sont cites, pas resumes : c'est ce qui rend le bras relisible.
    assert M.ARMS["control"].selector == "Entity(target)"
    assert "AdjacentUnits(Target@0x60, 1, 3)" in M.ARMS["adjacent"].selector
    assert "Caster@0x48" in M.ARMS["adjacent"].selector


def test_le_sujet_est_ramming_speed_et_lui_seul():
    """`RammingSpeedPlaybook` est le SUJET : son origin est l'arbre `GetTileToMoveTo()`, le terme
    en cause. Un second sujet, ou un sujet qui disparait, fait rougir."""
    assert {a.ability for a in M.ARMS.values() if a.role == "sujet"} == {1059}
    assert M.ARMS["ramming"].playbook == "RammingSpeedPlaybook"
    assert "GetTileToMoveTo()" in M.ARMS["ramming"].selector


def test_tout_bras_declare_un_role_du_vocabulaire_ferme():
    """Un bras ajoute sans role -- ou avec un role invente -- ne doit PAS passer inapercu.
    Et l'union des deux roles doit rester EXACTEMENT les trois appelants du decompile."""
    assert all(a.role in M.ROLES for a in M.ARMS.values()), \
        "role hors vocabulaire : %s" % sorted({a.role for a in M.ARMS.values()} - set(M.ROLES))
    assert {a.ability for a in M.ARMS.values()} == {1004, 1170, 1059}


def test_expected_targets_REFUSE_le_bras_sujet():
    """Sur le sujet, l'attendu ne se derive PAS de la geometrie (c'est un POOL de tuiles que seul
    le capteur `tileProbe` lit). Le montage doit LEVER, jamais fabriquer un nombre."""
    import pytest
    board, dv = _Board(), _dv(caster_pos=(3, 3))
    with pytest.raises(ValueError, match="TEMOIN"):
        M.expected_targets(M.ARMS["ramming"], board, dv, caster_id=1, target_id=2)


def test_le_caster_adjacent_est_retire_par_la_soustraction():
    board, dv = _Board(), _dv(caster_pos=(1, 0))
    exp = M.expected_targets(M.ARMS["adjacent"], board, dv, caster_id=1, target_id=2)
    assert 1 not in exp["ids"], "le caster doit sortir : `op_Subtraction Caster@0x48`"
    assert exp["n"] == 3 and sorted(exp["ids"]) == [2, 3, 4]


def test_la_mutation_no_subtraction_fait_diverger_l_attendu():
    """Sans cette divergence, l'accord du bras caster-adjacent serait tautologique."""
    board, dv = _Board(), _dv(caster_pos=(1, 0))
    droit = M.expected_targets(M.ARMS["adjacent"], board, dv, 1, 2)
    mute = M.expected_targets(M.ARMS["adjacent"], board, dv, 1, 2, mutate="no-subtraction")
    assert 1 in mute["ids"] and mute["n"] == droit["n"] + 1
    assert sorted(mute["ids"]) != sorted(droit["ids"])


def test_la_mutation_no_adjacency_ampute_le_voisinage():
    board, dv = _Board(), _dv(caster_pos=(3, 3))
    mute = M.expected_targets(M.ARMS["adjacent"], board, dv, 1, 2, mutate="no-adjacency")
    assert mute["ids"] == [2] and mute["n"] == 1


def test_le_bras_de_controle_ne_selectionne_que_la_cible():
    board, dv = _Board(), _dv(caster_pos=(3, 3))
    exp = M.expected_targets(M.ARMS["control"], board, dv, 1, 2)
    assert exp["ids"] == [2], "`Entity(target)` ne rend que la cible"


def test_un_caster_hors_du_ring_ne_change_rien_a_l_attendu():
    """Le caster LOIN et le caster ADJACENT doivent donner le MEME attendu -- c'est la propriete
    que le 3e bras live confronte (le natif rend 3 events dans les deux cas)."""
    board = _Board()
    loin = M.expected_targets(M.ARMS["adjacent"], board, _dv((3, 3)), 1, 2)
    pres = M.expected_targets(M.ARMS["adjacent"], board, _dv((1, 0)), 1, 2)
    assert sorted(loin["ids"]) == sorted(pres["ids"]) == [2, 3, 4]
