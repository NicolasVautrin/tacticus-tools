"""GARDE #328 -- `RelentlessMarchAbility` (passif `RelentlessMarch`, `TriggeredAbilityType` 0x3ec =
1004, de `necroWarden` << Makhotep >>) : au debut de SON tour, le porteur pose
`RelentlessMarch_Effect` (1011, 1 tour) sur les ALLIES ADJACENTS non-`Stationary`, et REPARE
`hpToRepair[niveau]` PV a TOUS les allies adjacents.

Artefacts natifs portes (RE ghidra `rnca9r7q6c` -- lecture in extenso :
`docs/rl/case-328-relentless-march.md` et l'en-tete de
`engine/runner/operations/triggers/loki/relentless_march.py`) :
  - `...RelentlessMarchAbility$$CreateTrigger` = `On(TurnStart_Other = 0x13, ownerNeedsToBeAlive)
    & <DSLTriggers+0x28 = IsTurnOf(Owner)>` ;
  - `...RelentlessMarchAbility$$CreateBehaviour(abilityState, triggerType)` =
        AddEffect(0x3f3 RelentlessMarch_Effect, AbilityStateReference,
                  UnitsWithoutTrait(Friends(AdjacentUnits(Owner)), 0x418 Stationary),
                  turns = Nullable<int>(1))
      + Repair(Owner, Friends(AdjacentUnits(Owner)), Direct(hpToRepair), ForRepair)
    avec, si `triggerType == 0x20 = Custom`, `targets -= HeroUnits(targets)`.

⚠ LE POINT DU CAS : le filtre `UnitsWithoutTrait(Stationary)` porte sur la cible de l'`AddEffect`
SEULE -- la fiche #317 le mettait sur le `Repair`. Un allie adjacent `Stationary` est donc REPARE
sans recevoir le +1 Mouvement.

CE QUE LA GARDE PROUVE (montage `probe_328_relentless_march.measure`, positions DRIVEES) :
  (A) le passif enregistre le trigger sur Makhotep par la voie `passiveAbilities`, sur `On(0x13)` ;
  (B) AGREEMENT live-vs-port a CHAQUE tour du porteur : MEME ensemble de porteurs de 1011, MEME
      `remaining` (= 1, le discriminant du `Nullable<int>(1)` -- un `TurnsFromRounds` ou une duree
      par defaut rendraient une autre valeur), et MEME delta de PV par unite ;
  (C) les DEUX gates d'`AttackQuery$$EntityCanBeRepaired` MORDENT et sont honores a l'identique :
      l'allie ORGANIQUE adjacent (`astraBullgryn`) recoit 1011 et ZERO PV
      (`UnitExtensions$$IsAffectedByHealType(target, 1)`), l'allie MECHANICAL a PV PLEINS
      (`admecDominus`) aussi (`IsDamagedUnit`) ;
  (D) CONTREFACTUELS : neutraliser le gate de CAMP (`Friends`) ou elargir l'adjacence fait diverger
      le port du live sur TOUS les tours -- sans quoi le montage ne testerait pas ces gates ;
  (E) STRUCTURE de l'arbre (offline, sans live) : le `Repair` recoit le selecteur NON filtre et
      l'`AddEffect` le selecteur FILTRE -- l'assertion qui encode la correction de la fiche #317 ;
  (F) branche `triggerType == Custom` : `Sub(targets, hero_units(targets))` (offline -- elle n'a
      aucun appelant cote port tant qu'`AdaptiveStrategy` 1005 n'est pas dans `ABILITY_CLASSES`).

VOLET SEPARE (`test_relentless_march_stationary_live.py` n'existe pas : c'est le meme fichier,
fixture `rm_stationary`) : `UnitsWithoutTrait(0x418)` exige un allie porteur de `Stationary`, trait
qu'AUCUNE unite du gameconfig ne porte en statique -- il n'est pose EN BATAILLE que par les
`AddTrait(0x418)` on-appearance de `ExemplarOfTheKauyon` / `DutyEternal` / `AetherStride`. Le montage
`measure_stationary` passe par `tauShadowsun` (HERO du pool) : son cast fait naître
`tauSmnDroneCommandLink` (`Mechanical` + `Stationary`) sur la tuile qu'elle quitte.

ASCII-only. Skip si pas de session live / montage non montable.
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))))))                  # scripts/python
import probe_328_relentless_march as RM                              # noqa: E402

SEED, BOARD, TURNS = "777", "C1_75", 3


@pytest.fixture(scope="session")
def rm(rpc, live_session):
    """Monte le montage UNE fois (destructif : il joue 3 tours) et rend la mesure brute.
    Le runner est dispose par `measure` (discipline runner.md : liberer au fil de l'eau)."""
    from rl_collect_batch import _resolve_session
    out = RM.measure(_resolve_session(), SEED, BOARD, TURNS, verbose=True)
    if out is None or not out["rows"]:
        pytest.skip("montage RelentlessMarch non montable (board/pool/placement)")
    return out


# ------------------------------------------------------------------------------------------------
# (E)/(F) -- STRUCTURE de l'arbre : offline, aucun live requis.
# ------------------------------------------------------------------------------------------------
def test_rm_tree_filter_applies_to_addeffect_only():
    """(E) LA CORRECTION DE LA FICHE #317, encodee en assertion : `UnitsWithoutTrait(Stationary)`
    enveloppe la cible de l'`AddEffect`, et le `Repair` recoit l'arbre NON filtre.

    Lu au desassemblage de `...RelentlessMarchAbility$$CreateBehaviour` : le resultat de
    `DSLSelectors$$UnitsWithoutTrait` part en 4e argument d'`AddEffect`, tandis que `Repair` recoit
    le meme `Friends(AdjacentUnits(Owner))` que ce filtre CONSOMME."""
    from engine.entities.selectors import Friends, UnitsWithoutTrait
    from engine.entities.traits.unit_trait import UnitTrait
    from engine.runner.operations.triggers.loki.relentless_march import (
        relentless_march_behaviour_tree)
    tree = relentless_march_behaviour_tree(1234)
    add, rep = tree.left, tree.right
    assert isinstance(add.target_sel, UnitsWithoutTrait), \
        "l'AddEffect doit recevoir le selecteur FILTRE par UnitsWithoutTrait(0x418)"
    assert int(add.target_sel.trait) == int(UnitTrait.Stationary) == 0x418
    assert isinstance(rep.targets_sel, Friends), \
        "le Repair doit recevoir l'arbre NON filtre (faute de la fiche #317)"
    # ... et c'est bien le MEME sous-arbre que le filtre enveloppe (le natif reprend `pvVar2`).
    assert add.target_sel.source is rep.targets_sel
    assert add.duration_turns == 1 and add.duration_rounds is None, \
        "turns = Nullable<int>(1) : deja en TOURS, jamais un TurnsFromRounds"
    assert rep.scope == 0 and rep.remove_effects is True, \
        "RepairBehaviourOptions$$ForRepair = (+0x10 = 0 scope, +0x14 = 1 removeEffects)"


def test_rm_custom_branch_subtracts_heroes():
    """(F) `if (triggerType == 0x20 = Custom) targets -= HeroUnits(targets)` -- mirror du
    decompile. Branche SANS appelant cote port (`AdaptiveStrategy` 1005 n'est pas portee) : elle est
    exercee ICI, offline, plutot que laissee muette."""
    from engine.dsl.event_trigger_type import EventTriggerType
    from engine.entities.selectors import Friends, Sub, UnitsWithTrait
    from engine.runner.operations.triggers.loki.relentless_march import relentless_march_targets
    normal = relentless_march_targets(int(EventTriggerType.TurnStart_Other))
    assert isinstance(normal, Friends), "hors Custom : l'arbre est le Friends(AdjacentUnits(Owner))"
    custom = relentless_march_targets(int(EventTriggerType.Custom))
    assert isinstance(custom, Sub), "Custom : op_Subtraction(targets, HeroUnits(targets))"
    assert isinstance(custom.b, UnitsWithTrait) and int(custom.b.trait) == 0x10, \
        "HeroUnits DELEGUE a UnitsWithTrait(src, 0x10 = UnitTrait.Hero)"
    assert custom.b.source is custom.a, "les deux operandes partagent le MEME sous-arbre"


# ------------------------------------------------------------------------------------------------
# (A)-(D) -- confrontation LIVE.
# ------------------------------------------------------------------------------------------------
def test_rm_trigger_registered(rm):
    """(A) Le passif `RelentlessMarch` enregistre le trigger sur Makhotep (voie `passiveAbilities`
    du registre), sur l'event `On(TurnStart_Other = 0x13 = 19)`."""
    from engine.dsl.event_trigger_type import EventTriggerType
    from engine.runner.operations.triggers.dispatch import collect_triggered_abilities
    from engine.runner.operations.triggers.loki.relentless_march import RelentlessMarchAbility
    from engine.runner.snapshot import load_state
    row = rm["rows"][0]
    st = load_state(row["cap"]["dec"], row["cap"]["ob"], row["cap"]["snap"],
                    board=row["cap"]["board"])
    mine = [t for t in collect_triggered_abilities(st)
            if isinstance(t, RelentlessMarchAbility)]
    assert len(mine) == 1, "Makhotep doit porter exactement 1 trigger RelentlessMarch"
    assert mine[0].owner_id == rm["ids"][RM.CARRIER]
    assert mine[0].event_id == EventTriggerType.TurnStart_Other


def test_rm_agreement_effect_targets_and_duration(rm):
    """(B1) A chaque tour du porteur : MEME ensemble de porteurs de 1011 live et port, MEME
    `remaining` (= 1). Les trois allies ADJACENTS l'ont ; ni l'ennemi adjacent, ni l'allie a
    distance 2, ni le porteur lui-meme (`AdjacentUnits` exclut l'origine)."""
    vis, ids = rm["vis_by_id"], rm["ids"]
    for row in rm["rows"]:
        live, port = row["live"], row["port"]
        assert set(live) == set(port), (
            f"tour #{row['k']} : live={sorted(vis[i] for i in live)} "
            f"port={sorted(vis[i] for i in port)}")
        for uid in live:
            assert live[uid] == port[uid], (
                f"tour #{row['k']} : duree de 1011 sur {vis[uid]} live={live[uid]} "
                f"port={port[uid]} (attendu 1 = le `turns = Nullable<int>(1)` natif)")
        assert set(live.values()) <= {1}, (
            f"tour #{row['k']} : le natif ne pose PAS 1 tour ({sorted(set(live.values()))})")
        assert set(live) == {ids[RM.FRIEND_MECH], ids[RM.FRIEND_ORGANIC], ids[RM.FRIEND_FULLHP]}, (
            f"tour #{row['k']} : l'ensemble attendu est les TROIS allies adjacents "
            f"(obtenu {sorted(vis[i] for i in live)})")


def test_rm_agreement_repair_deltas(rm):
    """(B2) MEME delta de PV par unite, live et port -- c'est la face `Repair` du behaviour."""
    vis = rm["vis_by_id"]
    for row in rm["rows"]:
        for uid in row["hp_before"]:
            assert row["d_live"].get(uid) == row["d_port"].get(uid), (
                f"tour #{row['k']} : dPV de {vis.get(uid, uid)} live={row['d_live'].get(uid)} "
                f"port={row['d_port'].get(uid)}")


def test_rm_repair_gates_bite(rm):
    """(C) Les DEUX gates d'`AttackQuery$$EntityCanBeRepaired` MORDENT sur ce montage :
      * `IsAffectedByHealType(target, 1)` -- `astraBullgryn` (organique, ENDOMMAGE) recoit 1011 mais
        ZERO PV ;
      * `IsDamagedUnit(target)` -- `admecDominus` (Mechanical, PV PLEINS) recoit 1011 mais ZERO PV ;
    et la reparation, elle, est bien NON NULLE sur l'allie Mechanical ENDOMMAGE. Sans ces trois
    controles, un port qui ne reparerait PERSONNE passerait l'agreement de (B2)."""
    ids = rm["ids"]
    mech, organic, full = ids[RM.FRIEND_MECH], ids[RM.FRIEND_ORGANIC], ids[RM.FRIEND_FULLHP]
    repaired = [row["d_live"].get(mech, 0) for row in rm["rows"]]
    assert all(d > 0 for d in repaired), (
        f"l'allie Mechanical ENDOMMAGE doit etre repare a chaque tour (dPV={repaired})")
    for row in rm["rows"]:
        assert row["d_live"].get(organic, 0) == 0 and row["d_port"].get(organic, 0) == 0, (
            f"tour #{row['k']} : l'allie ORGANIQUE ne doit RIEN recevoir en PV "
            f"(gate IsAffectedByHealType) -- live={row['d_live'].get(organic)} "
            f"port={row['d_port'].get(organic)}")
        assert row["d_live"].get(full, 0) == 0 and row["d_port"].get(full, 0) == 0, (
            f"tour #{row['k']} : l'allie a PV PLEINS ne doit RIEN recevoir (gate IsDamagedUnit) -- "
            f"live={row['d_live'].get(full)} port={row['d_port'].get(full)}")
        assert organic in row["live"] and full in row["live"], (
            f"tour #{row['k']} : les deux doivent quand meme recevoir l'effet 1011 "
            "(l'AddEffect n'a AUCUN gate de reparation)")


@pytest.mark.parametrize("gate", ["friends", "adjacent"])
def test_rm_gate_counterfactual(rm, gate):
    """(D) CONTREFACTUEL : gate neutralise/elargi -> le port DIVERGE du live sur tous les tours
    mesures. Un gate qui reste inerte signale un montage AVEUGLE, pas un port juste."""
    bites = 0
    for row in rm["rows"]:
        st = RM.offline_fire(row["cap"], rm["p_team"], mutate=gate)
        mo, mhp = RM.carriers_offline(st), RM.hp_offline(st)
        md = {i: mhp.get(i, 0) - row["hp_before"].get(i, 0) for i in row["hp_before"]}
        if (set(mo) != set(row["live"])
                or any(md.get(i) != row["d_live"].get(i) for i in row["hp_before"])):
            bites += 1
    assert bites == len(rm["rows"]), (
        f"le gate '{gate}' ne mord que sur {bites}/{len(rm['rows'])} tours : le montage ne le "
        "teste pas (re-crafter les positions/rosters)")


# ------------------------------------------------------------------------------------------------
# Volet STATIONARY -- le discriminant de la correction #317, montage separe (drone de Shadowsun).
# ------------------------------------------------------------------------------------------------
@pytest.fixture(scope="session")
def rm_stationary(rpc, live_session):
    """`tauShadowsun` caste `ExemplarOfTheKauyon` -> `tauSmnDroneCommandLink` (`Mechanical` +
    `AddTrait(0x418 Stationary)` on-appearance) naît ADJACENT au porteur. Seul montage BON MARCHE du
    build qui exerce `UnitsWithoutTrait(targets, 0x418)`."""
    from rl_collect_batch import _resolve_session
    out = RM.measure_stationary(_resolve_session(), SEED, BOARD, verbose=True)
    if out is None or not out["rows"]:
        pytest.skip("montage Stationary non montable (cast/drone/adjacence)")
    return out


def test_rm_stationary_excluded_from_effect(rm_stationary):
    """L'allie adjacent `Stationary` (le drone) N'EST PAS dans l'ensemble des porteurs de 1011,
    LIVE comme PORT, alors que l'allie adjacent non-Stationary y est. Et la MUTATION qui retire le
    filtre MORD (le port poserait 1011 sur le drone) -- sans quoi le gate serait inerte."""
    drone, mech = rm_stationary["drone"], rm_stationary["mech"]
    for row in rm_stationary["rows"]:
        assert drone not in row["live"], (
            f"tour #{row['k']} : le natif POSE 1011 sur un allie Stationary -- la lecture du "
            "`UnitsWithoutTrait` est a refaire")
        assert drone not in row["port"], f"tour #{row['k']} : le port pose 1011 sur le Stationary"
        assert mech in row["live"] and mech in row["port"], (
            f"tour #{row['k']} : l'allie adjacent NON-Stationary doit, lui, recevoir 1011")
        assert drone in row["mut"]["stationary"], (
            f"tour #{row['k']} : la mutation 'stationary' n'ajoute PAS le drone -> le gate n'est "
            "pas exerce par ce montage")


def test_rm_stationary_agreement(rm_stationary):
    """Agreement complet (effet + PV) sur le montage Stationary."""
    for row in rm_stationary["rows"]:
        assert set(row["live"]) == set(row["port"]), f"tour #{row['k']} : ensembles 1011 differents"
        for uid in row["hp_before"]:
            assert row["d_live"].get(uid) == row["d_port"].get(uid), (
                f"tour #{row['k']} : dPV de u{uid} live={row['d_live'].get(uid)} "
                f"port={row['d_port'].get(uid)}")
