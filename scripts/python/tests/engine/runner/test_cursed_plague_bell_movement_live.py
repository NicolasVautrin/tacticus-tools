"""GARDE #224 item 1 -- `CursedPlagueBellMovementAbility` (volet MOUVEMENT du passif
`CursedPlagueBell` 1071 de `deathBlightbringer`/Corrodius) : au debut de SON tour, le porteur pose
`CursedPlagueBell_ExtraMove` (1073, 1 tour) sur les ALLIES **Chaos** non-**Stationary** de son
disque d'aura Contagion, centre EXCLU.

Artefacts natifs portes (RE ghidra `rnca9r7q6c`, cf. l'en-tete de
`engine/runner/operations/triggers/loki/cursed_plague_bell.py` pour la lecture complete) :
  - `...CursedPlagueBellMovementAbility$$CreateTrigger` (corps PARTAGE avec
    `...RelentlessMarchAbility$$CreateTrigger`, dedup IL2CPP) = `On(TurnStart_Other=0x13) &
    <DSLTriggers+0x28 = OwnerIsActor>` ;
  - `...CursedPlagueBellMovementAbility$$GetTargetsSelector(dsl, isDangerZone)` =
    `UnitsWithoutTrait( UnitsWithTrait( SurroundingFriends(Owner,
        ContagionsOfNurgleRange(Owner, Any, isDangerZone), unique, OnlyAliveAndTargetable),
        Chaos 0x7ea), Stationary 0x418)` ;
  - `...CursedPlagueBellMovementAbility$$CreateBehaviour` =
    `AddEffect(0x431 CursedPlagueBell_ExtraMove, AbilityStateReference, <ci-dessus>,
     turns = Nullable<int>(1))` ;
  - `DSLFormulas$$ContagionsOfNurgleRange` -> `AuraEffectRangeFormula$$Calculate` ->
    `ContagionsOfNurgle_ArmorReduction_Effect$$GetTrait`(=0x7eb) / `$$GetCurrentRange` /
    `$$GetRangeOnOwnerTurn` (1 aux tours 1-2, 2 aux 3-4, 3 a partir du 5).

CE QUE LA GARDE PROUVE (montage `probe_224_cursed_plague_bell.measure`, board a >= 6 spawns, toutes
les positions DRIVEES -- rien n'est subi) :
  (A) le passif enregistre le trigger sur Corrodius par la voie `passiveAbilities`, sur `On(0x13)` ;
  (B) AGREEMENT live-vs-port : a CHAQUE tour du porteur, l'ENSEMBLE des unites qui portent 1073
      cote natif == cote port, et le `remaining` aussi (= 1, le discriminant du `Nullable<int>(1)`
      -- un `TurnsFromRounds` ou une duree par defaut rendraient une autre valeur) ;
  (C) le RAYON est EFFECTIF : l'allie Chaos place a distance 2 n'entre qu'au tour ou
      `TurnsStarted > 2`, celui a distance 3 qu'au tour ou `TurnsStarted > 4` -- les DEUX seuils de
      `GetRangeOnOwnerTurn` sont franchis dans la meme mesure ;
  (D) SCOPING `OwnerIsActor` : au tour ADVERSE, le vecteur ne pose RIEN ;
  (E) CONTREFACTUELS : retirer le gate `Chaos` ou le gate de CAMP (`SurroundingFriends`) fait
      diverger le port du live sur TOUS les tours -- sans quoi le montage ne testerait pas ces gates.

RESIDU ASSUME : le gate `UnitsWithoutTrait(Stationary)` n'est pas exerce par ce montage. Le trait
1048 EXISTE pourtant dans le substrat que le port interroge depuis #270
(`combatSnapshot.units[].traits`) : `probe_264_load_state_traits` montage B le mesure sur le summon
`ultraSmnDreadnought`. Ce qui manque est un porteur **Chaos ET Stationary** (le gate s'applique
apres `UnitsWithTrait(Chaos)`) -- seul candidat : `thousSmnDaemonPrince`, via la MoW
`thousDaemonPrince` absente du seed BC (`catalog_inject` requis). Cf. §5 de la case doc.

ASCII-only. Skip si pas de session live / montage non montable.
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))))))                  # scripts/python
import probe_224_cursed_plague_bell as PB                            # noqa: E402

SEED, BOARD, TURNS = "777", "C1_75", 5


@pytest.fixture(scope="session")
def cpb(rpc, live_session):
    """Monte le montage UNE fois (destructif : il joue 5 tours) et rend la mesure brute.
    Le runner est dispose par `measure` (discipline runner.md : liberer au fil de l'eau)."""
    from rl_collect_batch import _resolve_session
    out = PB.measure(_resolve_session(), SEED, BOARD, TURNS, verbose=True)
    if out is None or not out["rows"]:
        pytest.skip("montage CursedPlagueBell non montable (board/pool/placement)")
    return out


def test_cpb_trigger_registered(cpb):
    """(A) Le passif `CursedPlagueBell` enregistre le trigger MOUVEMENT sur Corrodius (voie
    `passiveAbilities` du registre), sur l'event `On(TurnStart_Other=0x13=19)`."""
    from engine.runner.operations.triggers.dispatch import collect_triggered_abilities
    from engine.runner.operations.triggers.loki.cursed_plague_bell import (
        CursedPlagueBellMovementAbility)
    from engine.runner.snapshot import load_state
    row = cpb["rows"][0]
    st = load_state(row["cap"]["dec"], row["cap"]["ob"], row["cap"]["snap"],
                    board=row["cap"]["board"])
    mine = [t for t in collect_triggered_abilities(st)
            if isinstance(t, CursedPlagueBellMovementAbility)]
    assert len(mine) == 1, "Corrodius doit porter exactement 1 trigger CursedPlagueBellMovement"
    assert mine[0].owner_id == cpb["ids"][PB.CARRIER]
    assert mine[0].event_id == 19, "le trigger ecoute On(0x13=TurnStart_Other)"


def test_cpb_agreement_targets_and_duration(cpb):
    """(B) A chaque tour du porteur : MEME ensemble de porteurs de 1073 live et port, MEME
    `remaining`."""
    vis = cpb["vis_by_id"]
    for row in cpb["rows"]:
        live, port = row["live"], row["port"]
        assert set(live) == set(port), (
            f"tour #{row['k']} (TurnsStarted={row['ts']}, rayon={row['radius']}) : "
            f"live={sorted(vis[i] for i in live)} port={sorted(vis[i] for i in port)}")
        for uid in live:
            assert live[uid] == port[uid], (
                f"tour #{row['k']} : duree de 1073 sur {vis[uid]} live={live[uid]} "
                f"port={port[uid]} (attendu 1 = le `turns = Nullable<int>(1)` natif)")
        assert set(live.values()) <= {1}, (
            f"tour #{row['k']} : le natif ne pose PAS 1 tour ({sorted(set(live.values()))}) -- "
            "la lecture du `turns` de l'AddEffect est a refaire")


def test_cpb_radius_thresholds_are_crossed(cpb):
    """(C) Le RAYON d'aura est EFFECTIF (et le montage le prouve) : l'allie Chaos a distance 2
    n'entre qu'au-dela du 1er seuil, celui a distance 3 qu'au-dela du 2e. Sans ce controle,
    l'agreement du test precedent pourrait tenir avec un rayon fige."""
    ids, rows = cpb["ids"], cpb["rows"]
    far2, far3 = ids[PB.FRIEND_CHAOS_FAR], ids[PB.FRIEND_CHAOS_FAR3]
    seen2 = {r["radius"]: (far2 in r["live"]) for r in rows}
    seen3 = {r["radius"]: (far3 in r["live"]) for r in rows}
    assert {1, 2, 3} <= set(seen2), (
        f"les trois rayons ne sont pas exerces par le montage (vus: {sorted(seen2)}) -- "
        "augmenter --turns")
    assert seen2[1] is False and seen2[2] is True and seen2[3] is True, (
        f"l'allie Chaos a distance 2 ne suit pas le rayon (rayon->present: {seen2})")
    assert seen3[1] is False and seen3[2] is False and seen3[3] is True, (
        f"l'allie Chaos a distance 3 ne suit pas le rayon (rayon->present: {seen3})")


def _load(row):
    from engine.runner.snapshot import load_state
    return load_state(row["cap"]["dec"], row["cap"]["ob"], row["cap"]["snap"],
                      board=row["cap"]["board"])


def _enemy_player(cpb):
    """Le `player` de l'ENNEMI, LU du state (jamais devine depuis `currentPlayer`)."""
    from engine.runner.components import OwnerComponent
    e = _load(cpb["rows"][-1]).get_entity(cpb["ids"][PB.ENEMY_CHAOS])
    return e.get_component(OwnerComponent).player


def test_cpb_owner_is_actor_scoping(cpb):
    """(D) `OwnerIsActor` (`DSLTriggers+0x28`) : rejoue au tour ADVERSE, le vecteur `On(0x13)` ne
    pose AUCUN 1073 supplementaire (l'ensemble des porteurs est celui de la capture)."""
    row = cpb["rows"][-1]
    a_player = _enemy_player(cpb)
    assert a_player != cpb["p_team"], "montage KO : l'ennemi appartient au joueur du porteur"
    before = set(PB.carriers_offline(_load(row)))
    after = set(PB.carriers_offline(PB.offline_fire(row["cap"], a_player)))
    assert after == before, (
        f"le vecteur a pose 1073 au tour adverse (player={a_player}) : {after} vs {before}")


@pytest.mark.parametrize("gate", ["chaos", "friends"])
def test_cpb_gate_counterfactual(cpb, gate):
    """(E) CONTREFACTUEL : gate neutralise -> le port DIVERGE du live sur tous les tours mesures.
    Un gate qui reste inerte signale un montage AVEUGLE, pas un port juste."""
    bites = 0
    for row in cpb["rows"]:
        mo = set(PB.carriers_offline(PB.offline_fire(row["cap"], cpb["p_team"], mutate=gate)))
        if mo != set(row["live"]):
            bites += 1
    assert bites == len(cpb["rows"]), (
        f"le gate '{gate}' ne mord que sur {bites}/{len(cpb['rows'])} tours : le montage ne le "
        "teste pas (re-crafter les positions/rosters)")


def test_cpb_radius_counterfactual(cpb):
    """(E bis) Rayon fige a 1 -> divergence des que le rayon reel depasse 1."""
    bites = sum(1 for row in cpb["rows"]
                if set(PB.carriers_offline(
                    PB.offline_fire(row["cap"], cpb["p_team"], mutate="radius1"))) != set(row["live"]))
    expected = sum(1 for row in cpb["rows"] if row["radius"] > 1)
    assert bites == expected and expected > 0, (
        f"rayon fige a 1 : mord {bites} fois, attendu {expected} (tours a rayon > 1)")
