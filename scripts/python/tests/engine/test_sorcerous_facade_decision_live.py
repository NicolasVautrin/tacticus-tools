"""SorcerousFacade (1100, Yazaghor `thousTzaangor`) -- face DECISION, confrontee au LIVE.

CE QUE CE TEST GARDE, et pourquoi aucun de ces points ne peut passer par accident :

A. **La route ALLIEE existe et sert.** 1100 porte un `damageProfile` mais son masque vaut
   `0x402 = TargetIsFriendly | TargetMatchesDynamicRule` : depuis #217 le VETO de
   `state_bridge._is_attack_ability` la sort de la route ENNEMIE, donc elle n'entre jamais dans
   `plans` et `_best_attack` ne la voit pas. Le bras `noroute` (registre `NONATTACK_PLAYBOOKS`
   vide) rejoue la decision dans l'etat d'AVANT le port -- s'il rend la MEME chose, le port est
   inerte et l'accord vient d'ailleurs.
B. **Le terme custom est NECESSAIRE** : force a 0, le moteur revient sur l'attaque normale dans
   tous les bras ou 1100 gagnait.
C. **Le terme est une DIFFERENCE, pas un booleen sur la tuile de la cible.** Le controle croise
   rejoue la MEME tuile d'allie (elevation 4) avec le caster sur une tuile d'elevation 4 : le natif
   y REFUSE 1100, alors qu'il l'accepte quand le caster est sur une tuile d'elevation 1. Un port qui
   ne regarderait que la tuile de la cible donnerait le meme choix dans les deux configurations.
D. **La route ENNEMIE reste FERMEE (non-regression #217), dans le MEME montage** : cote natif,
   toutes les evals `(1100, ennemi)` de `decisionView.attackPlans` restent a `rankCount = 0` ; cote
   port, `_is_attack_ability` reste False, `_ability_kind` reste `ally`, et 1100 n'entre pas dans
   les abilities d'attaque du porteur.
E. **L'etage PREDICTION coincide avec le natif** : `pairUtility(1100)` natif vs la somme
   `CalculateUtilityFromPredictions` du port, a 1e-6. C'est ce qui attrape le piege
   `_PREDICT_VIA_NORMAL_ATTACK` (deleguer au chemin generique rend DEUX fois l'attaque normale,
   soit le double exact -- mesure du 2026-07-30).

Le confond de prediction est MESURE : les `pairUtility` natives sont bit-identiques d'un bras a
l'autre d'une meme configuration (seul l'allie bouge, et il reste a distance 4 du caster dans les
quatre bras -- aucune feuille d'adjacence ne le voit).

Porteur `thousTzaangor` ET allie Psyker `thousSorcerer` sont tous deux dans le pool spawnable :
aucun `catalog_inject` n'est requis. ASCII only.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

PYDIR = Path(__file__).resolve().parents[2]                 # scripts/python
sys.path.insert(0, str(PYDIR))

import probe_27_4e_facade_ab as AB                          # noqa: E402

FACADE = AB.FACADE
LOW = "caster_bas"
HIGH = "caster_haut"


@pytest.fixture(scope="module")
def rows():
    rws, runners = AB.run_ab()
    try:
        yield rws
    finally:
        for rid in runners:
            try:
                AB.L._rpc("disposeRunner", [{"runnerId": rid}])
            except Exception:                               # noqa: BLE001
                pass


def test_engine_matches_native_on_all_arms(rows):
    """Le moteur reproduit le choix NATIF dans les cinq bras."""
    for k, row in rows.items():
        assert row["engine"]["on"][0] == row["native"][0], (
            "bras %s : moteur %s != natif %s" % (k, row["engine"]["on"], row["native"]))


def test_prediction_stage_matches_native(rows):
    """ETAGE PREDICTION : la somme du port == `pairUtility(1100)` natif (a 1e-6)."""
    for k, row in rows.items():
        nat = row["pairs"].get("ability%d" % FACADE)
        got = row["engine"]["u_pred"]
        assert nat is not None and abs(got - nat) < 1e-6, (
            "bras %s : u_pred moteur %r != pairUtility(1100) natif %r -- un facteur 2 signale que "
            "la prediction a ete deleguee au chemin generique (`_PREDICT_VIA_NORMAL_ATTACK`)"
            % (k, got, nat))


def test_native_switches_with_the_tile_difference(rows):
    """Le natif REFUSE 1100 a custom nul et l'ACCEPTE des que la tuile de l'allie domine."""
    assert rows["%s/e1" % LOW]["native"][0] != FACADE, "custom nul : 1100 ne devrait pas gagner"
    for lab in ("e2", "e3", "e4"):
        assert rows["%s/%s" % (LOW, lab)]["native"][0] == FACADE, (
            "bras %s : custom positif et le natif refuse 1100" % lab)


def test_term_is_a_difference_not_a_target_tile_bonus(rows):
    """CONTROLE CROISE : meme tuile d'allie (elevation 4), choix natif OPPOSE selon la tuile du
    caster. Un terme qui ne lirait que la tuile de la CIBLE ne pourrait pas produire ca."""
    low = rows["%s/e4" % LOW]
    high = rows["%s/e4" % HIGH]
    assert low["engine"]["tile_ally"] == high["engine"]["tile_ally"]
    assert low["native"][0] == FACADE and high["native"][0] != FACADE, (
        "le natif ne distingue pas les deux configurations -> le terme ne serait pas une difference")
    assert abs(high["engine"]["custom"]) < 1e-9 < abs(low["engine"]["custom"])


def test_custom_term_is_necessary(rows):
    """Force a 0, le custom fait DIVERGER le moteur du natif partout ou 1100 gagne."""
    for k, row in rows.items():
        if row["native"][0] == FACADE:
            assert row["engine"]["zero"][0] != FACADE, (
                "bras %s : 1100 gagne encore avec custom=0 -> le terme est inerte" % k)


def test_ally_route_is_necessary(rows):
    """Sans la route non-attaque, le moteur ne PEUT PAS proposer 1100 (absente de tout `plan`)."""
    for k, row in rows.items():
        if row["native"][0] == FACADE:
            assert row["engine"]["noroute"][0] != FACADE, (
                "bras %s : le moteur propose 1100 SANS la route -- une autre voie la fait passer" % k)


def test_enemy_route_stays_closed(rows):
    """NON-REGRESSION #217, dans le MEME montage : natif ET port refusent la cible ennemie."""
    for k, row in rows.items():
        assert all((rc or 0) == 0 for _t, rc in row["ev1100_native"]), (
            "bras %s : le natif rend une eval (1100, ennemi) rankable" % k)
        o = row["engine"]["offline217"]
        assert o["is_attack"] is False, "bras %s : _is_attack_ability(1100) est redevenu True" % k
        assert o["kind"] == "ally", "bras %s : _ability_kind(1100) = %r" % (k, o["kind"])
        assert o["in_attack_abilities"] is False
        assert all((rc or 0) == 0 for _t, rc in o["plans_1100"])


def test_selector_and_gate(rows):
    """`GetTarget` rend l'ennemi le plus proche (`sel`), et `ShouldExecute` laisse passer : les deux
    faces du gate natif sont exercees dans chaque bras."""
    for k, row in rows.items():
        e = row["engine"]
        assert e["sel"] is not None, "bras %s : aucun `sel` -- la regle dynamique ne serait pas " \
                                     "satisfaite et le natif ne proposerait jamais 1100" % k
        assert e["should_execute"] is True
        assert e["n_events"] == 2, (
            "bras %s : %d events au lieu des 2 du natif (attaque normale + batch propre)"
            % (k, e["n_events"]))
        assert e["targets"], "bras %s : aucune cible ALLIEE eligible" % k
