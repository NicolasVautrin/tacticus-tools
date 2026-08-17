"""GARDE case-207 -- `HazeOfCorruption_TargetFinderAbility` consomme `min(|pool|, 2)` `genrand_int32`
A L'ENTREE de chaque ability de `deathBlightlord`, AVANT le premier coup.

Chaines natives portees (symboles) :
  `IdunBattleLogic.Entities.Abilities.Active.Loki.HazeOfCorruption_TargetFinderAbility$$CreateTrigger`
      = `On(0x2a = PreUnitAbility, 1) & get_OwnerIsCaster`
  `IdunBattleLogic.Entities.Abilities.Active.Loki.HazeOfCorruption_TargetFinderAbility$$CreateBehaviour`
      = `PickRandomly( Damageable( AdjacentEnemies(Self@0x148, 1, 3)
                                 & AdjacentFriends(Target@0x178, 1, 3) ), 2, 0, 0x7fffffff, false )`
        + 1 ou 2 `AddBondEffect(0x435 = 1077 HazeOfCorruption_DamageTransfer)`
  `IdunBattle.Entities.Selectors.PickRandomAmountSelector$$Select` (loi case-130)
  `IdunBattleLogic.Entities.DSLSelectors$$AdjacentFriends` (surcharge 4-args : la REFERENCE d'equipe est
      le centre, pas le caster)
Cf. `docs/rl/case-207-haze-of-corruption-target-finder.md`.

Ce que la garde PROUVE (pas « le code est atteint ») :

 1. OFFLINE, le noeud de pool -- `AdjacentFriends(Target)` selectionne les allies DE LA CIBLE. Un
    retour au collapse historique (« team == caster ») rendrait le camp INVERSE : le test monte les
    DEUX camps a portee et exige le bon.
 2. OFFLINE, la CHAINE des bonds : `(Target, units[0])` puis `(units[0], units[1])` -- pas deux
    bonds paralleles depuis la cible.
 3. LIVE, l'ECHELLE `k = 0, 1, 2` sur UNE SEULE emission (geometrie CRAFTEE, cible sans
    `SwornProtector`) : comptage `port == natif`, per-coup `port == live`, `bonds natifs == k`.
    Le test EXIGE que les trois comptes natifs DIFFERENT -- sinon le scenario ne separe plus
    « min(k,2) » d'un forfait, et il le DIT au lieu de passer.
 4. LIVE, anti-tautologie : le modele SANS le trigger (= le port d'avant case-207) est verifie
    INCAPABLE de rendre le compte natif des que `k >= 1`.
 5. LIVE, le montage d'origine (`astraCreed`, DEUX emissions via la re-entree #120bis de
    `SwornProtector`) : natif 5 == port 5, per-coup bit-exact, contrefactuel a 3.

ASCII-only. Skip si pas de session live.
"""
from __future__ import annotations

import argparse
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))))))                  # scripts/python

from engine.dsl.base import DslContext                              # noqa: E402
from engine.runner.operations.triggers.loki.haze_of_corruption import (  # noqa: E402
    HAZE_TARGET_POOL, HAZE_PICK_AMOUNT, HAZE_DAMAGE_TRANSFER,
    HazeOfCorruptionTargetFinderAbility)
import probe_207_haze_pool_ladder as LAD                            # noqa: E402
import probe_207_haze_target_finder as TF                           # noqa: E402

HAZE_TRIGGERED_ABILITY = 1076        # `Effect_SourceTriggeredAbility` des bonds natifs


def _u(uid, col, row, team, hp=1000):
    return {"id": uid, "team": team, "player": team, "pos": {"col": col, "row": row},
            "alive": True, "hp": hp, "visualId": "u%d" % uid, "_traits": set()}


# --------------------------------------------------------------------------- 1-2. OFFLINE (noeuds)


def test_pool_node_takes_the_targets_allies_not_the_casters():
    """`AdjacentFriends(Target@0x178, 1, 3)` = les allies DE LA CIBLE. Le collapse historique
    (`team == ctx.caster.team`) rendrait le camp INVERSE : ici l'allie du CASTER est lui aussi
    adjacent aux deux, donc les deux modeles sont DISCRIMINES."""
    caster = _u(1, 5, 5, team=0)
    target = _u(2, 6, 5, team=1)
    # (5,6) et (6,4) sont les DEUX voisins communs de (5,5) et (6,5) (parite offset `evenq`)
    tgt_ally = _u(3, 6, 4, team=1)      # allie de la CIBLE, adjacent au caster ET a la cible
    cst_ally = _u(4, 5, 6, team=0)      # allie du CASTER, adjacent au caster ET a la cible
    ctx = DslContext(units=[caster, target, tgt_ally, cst_ally], caster=caster, target=target)
    import hexgeo
    for u in (tgt_ally, cst_ally):      # le montage n'a de sens que si les deux sont a portee
        assert hexgeo.distance((5, 5), (u["pos"]["col"], u["pos"]["row"])) == 1
        assert hexgeo.distance((6, 5), (u["pos"]["col"], u["pos"]["row"])) == 1
    pool = [x["id"] for x in (HAZE_TARGET_POOL.evaluate(ctx) or [])]
    assert pool == [tgt_ally["id"]], (
        f"pool={pool} : attendu [{tgt_ally['id']}] (allie de la CIBLE). "
        f"[{cst_ally['id']}] = le collapse `team == caster` (camp INVERSE).")


def test_pool_node_is_an_intersection_not_a_union():
    """`IdunBattle.DSL.TargetsSelector$$op_BitwiseAnd` (mode `+0x28` = 0) = INTERSECTION. Un ennemi
    adjacent au CASTER mais PAS a la cible ne doit PAS entrer dans le pool -- c'est ce que le
    controle live 1v1 (0 tirage, 0 bond) mesure, et c'est ce qui exclut la lecture UNION."""
    caster = _u(1, 5, 5, team=0)
    target = _u(2, 6, 5, team=1)
    far = _u(3, 4, 5, team=1)           # adjacent au caster, PAS a la cible
    ctx = DslContext(units=[caster, target, far], caster=caster, target=target)
    assert [x["id"] for x in (HAZE_TARGET_POOL.evaluate(ctx) or [])] == []


def test_bond_pairs_form_a_chain():
    """`if Count > 0 : AddBondEffect(Target@0x178, units[0])` puis
    `if Count > 1 : AddBondEffect(units[0], units[1])` -- une CHAINE (le 2e relais prend le relais
    du 1er), pas deux bonds paralleles depuis la cible."""
    a, b = _u(10, 0, 0, team=1), _u(11, 1, 0, team=1)
    assert HazeOfCorruptionTargetFinderAbility._bond_pairs([]) == []
    one = HazeOfCorruptionTargetFinderAbility._bond_pairs([a])
    assert len(one) == 1 and one[0][1] is a
    two = HazeOfCorruptionTargetFinderAbility._bond_pairs([a, b])
    assert len(two) == 2 and two[0][1] is a and two[1][1] is b
    # la SOURCE du 2e bond est units[0] (et pas la cible) -> un noeud d'ensemble, pas `Target()`
    assert type(two[0][0]).__name__ == "Target"
    assert type(two[1][0]).__name__ == "UnitSet"


def test_pick_amount_and_effect_are_the_read_literals():
    assert HAZE_PICK_AMOUNT == 2            # `PickRandomly(sel, 2, 0, 0x7fffffff, false)`
    assert HAZE_DAMAGE_TRANSFER == 0x435    # `AddBondEffect(0x435, ...)` = 1077


# --------------------------------------------------------------------------- 3-4. LIVE : l'echelle


@pytest.fixture(scope="module")
def ladder(rpc):
    args = argparse.Namespace(hp=90000, armor=6000)
    rows = {}
    for k in (0, 1, 2):
        r = LAD._run(rpc, "777", k, args)
        if r is None:
            pytest.skip(f"echelle k={k} non montee (geometrie/pool indisponible)")
        rows[k] = r
    return rows


def test_ladder_is_discriminant_live(live_session, ladder):
    """Sans CONTRASTE entre les trois k, le scenario ne separe pas `min(k,2)` d'un forfait :
    on le DIT au lieu de passer."""
    counts = {k: r["n_native"] for k, r in ladder.items()}
    print(f"\n[207] natif par k : {counts}")
    assert counts[0] < counts[1] < counts[2], (
        f"echelle NON discriminante {counts} : le montage ne mesure plus le cardinal du pool.")


@pytest.mark.parametrize("k", [0, 1, 2])
def test_ladder_port_matches_native_live(live_session, ladder, k):
    """Comptage `port == natif`, per-coup `port == live`, et `bonds natifs == min(k, 2)`."""
    r = ladder[k]
    print(f"\n[207] k={k} natif={r['n_native']} port={r['n_off']} contref={r['n_off_cf']} "
          f"bonds={r['bonds']} live={r['live']} port_hits={r['off']}")
    assert r["n_native"] == r["n_off"], (
        f"k={k} : flux desaligne (natif={r['n_native']} port={r['n_off']})")
    assert r["live"] == r["off"], (
        f"k={k} : per-coup port={r['off']} != live={r['live']}")
    assert r["bonds"] == min(k, HAZE_PICK_AMOUNT), (
        f"k={k} : {r['bonds']} bond(s) natif(s) 1076, attendu {min(k, HAZE_PICK_AMOUNT)} -- "
        "la geometrie craftee ne donne pas le pool voulu.")


@pytest.mark.parametrize("k", [1, 2])
def test_ladder_counterfactual_cannot_reproduce_live(live_session, ladder, k):
    """ANTI-TAUTOLOGIE : le port d'AVANT case-207 (trigger neutralise) ne rend NI le compte NI les
    coups des que le pool est non vide."""
    r = ladder[k]
    assert r["n_off_cf"] != r["n_native"], (
        f"k={k} : le contrefactuel rend AUSSI {r['n_native']} tirages -- garde AVEUGLE.")
    assert r["cf"] != r["live"], (
        f"k={k} : le contrefactuel reproduit AUSSI les coups live {r['live']} -- garde AVEUGLE.")


# --------------------------------------------------------------------------- 5. LIVE : le montage
#                                                                                d'origine case-207


@pytest.fixture(scope="module")
def creed_row(rpc):
    args = argparse.Namespace(carrier="deathBlightlord", target="astraCreed", rank=None,
                              hp=90000, armor=6000, max_turns=30)
    r = TF._run_seed(rpc, "777", args)
    if r is None:
        pytest.skip("montage deathBlightlord vs astraCreed non monte")
    return r


def test_two_emissions_two_draws_live(live_session, creed_row):
    """Le residu D'ORIGINE : `SwornProtector` fait re-entrer `ExecuteForReplacedTarget` (#120bis),
    donc `On(0x2a = PreUnitAbility)` est emis DEUX fois -> DEUX pools de 1 -> DEUX tirages, puis les 3 coups."""
    r = creed_row
    print(f"\n[207] creed natif={r['n_native']} port={r['n_off']} contref={r['n_off_cf']} "
          f"bonds={r['bonds']} live={r['live']} port={r['off_hits']} contref={r['cf_hits']}")
    assert r["bonds"] == 2, (
        f"{r['bonds']} bond(s) natif(s) 1076 : le montage ne produit plus DEUX emissions.")
    assert r["n_native"] == r["n_off"], (
        f"flux desaligne (natif={r['n_native']} port={r['n_off']})")
    assert r["n_off"] - r["n_off_cf"] == 2, (
        f"le trigger ne coute pas 2 tirages ici (port={r['n_off']} contrefactuel={r['n_off_cf']})")
    assert r["live"] == r["off_hits"], (
        f"per-coup port={r['off_hits']} != live={r['live']}")
    assert r["cf_hits"] != r["live"], (
        f"le contrefactuel reproduit AUSSI le live {r['live']} -- garde AVEUGLE.")
