"""Gen-stealer G6a : passif HypersensoryAbilities (Judh genesKelermorph) HP-FLOOR, valide LIVE.

i2 : « The first time each enemy turn that Judh is attacked, she cannot fall below 50% of her current
Health. » = effet 0x564=1380 `HypersensoryAbilities_MinimalHealthEffect` :
  - `IdunBattleLogic.Entities.Abilities.Triggered.Loki.HypersensoryAbilitiesAbility$$CreateBehaviour : `AddEffect(0x564, owner)` self a l'init de l'ability passive (owner-effect).
  - `IdunBattle.Entities.Effects.Idun.HypersensoryAbilities_MinimalHealthEffect$$ApplyInternal : `MinimalHealth = Min(Round(hp x hpPct/100), hp-1)` (snapshot du HP courant).
  - `IdunBattle.Entities.Effects.Idun.HypersensoryAbilities_MinimalHealthEffect$$RevertInternal : `MinimalHealth = null`.
  - `IdunBattle.Entities.Effects.Idun.HypersensoryAbilities_MinimalHealthEffect$$CreateActiveCondition : `IsEnemyTurn(owner) & Not(HasBeenAttackedAmountThisTurn(owner)>=1)`.
  - clamp `IdunBattle.Entities.Components.FillUpStatComponent$$Reduce` : les PV ne descendent pas sous `min(hp, MinimalHealth)`.
hpPct[L1..65] = 30..50 (var 0x26, level-indexee, NON rarity-scalee).

VALIDATION : deterministe-sur-etat-live (comme G2/G3/G4/G5). BUILD un runner (Judh + ennemi), capture l'etat
LIVE, charge offline, et asserte le WIRING du port :
  (A) Judh porte l'effet 1380 des le build (auto-pose via InitializeActorAbilities boucle ABILITIES) ;
  (B) driver ActiveCondition : au tour ENNEMI -> floor = round(50% du HP courant) pose ; au tour de JUDH -> efface ;
  (C) clamp `HealthComponent.reduce` : un degat letal est borne au floor (Judh survit a exactement le floor) ;
  (D) 1re attaque survit (floor) + compteur=1 + floor efface -> la 2e attaque du tour TUE ;
  (E) reset du compteur `times_attacked_this_turn` au start_turn.
ASCII-only. Skip si pas de session / Judh non buildable.
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))      # import du helper sibling
from _config_oracle import ability_variable_levels  # noqa: E402

JUDH_VIS = "genesKelermorph"     # Judh : passif HypersensoryAbilities + actif HeroicFusillade
ENEMY_VIS = "necroWarden"
BUILD = ["--p-units", "genesKelermorph", "--a-units", "necroWarden"]
MINIMAL_HEALTH_EFFECT = "HypersensoryAbilities_MinimalHealth"


# ------------------------------------------------------------------ helpers etat

def _find_by_vis(state, vis, alive_only=True):
    from engine.runner.components import UnitComponent
    for uid, e in state.entities.items():
        uc = e.get_component(UnitComponent)
        if uc is not None and uc.visual_id == vis and (uc.alive or not alive_only):
            return uid
    return None


def _player(state, uid):
    from engine.runner.components import OwnerComponent
    e = state.get_entity(uid)
    oc = e.get_component(OwnerComponent) if e is not None else None
    return oc.player if oc is not None else None


def _hc(state, uid):
    from engine.runner.components import HealthComponent
    e = state.get_entity(uid)
    return e.get_component(HealthComponent) if e is not None else None


def _uc(state, uid):
    from engine.runner.components import UnitComponent
    e = state.get_entity(uid)
    return e.get_component(UnitComponent) if e is not None else None


def _minimal_effect(state, uid):
    from engine.entities.effects.loki.status import HypersensoryMinimalHealthEffect
    for e in (state.effects.by_unit.get(int(uid), []) if state.effects is not None else []):
        if isinstance(e, HypersensoryMinimalHealthEffect) and not e.consumed:
            return e
    return None


def _set_pos(state, uid, col, row):
    from engine.runner.components import PositionComponent
    e = state.get_entity(uid)
    pc = e.get_component(PositionComponent) if e is not None else None
    if pc is not None:
        pc.col, pc.row = int(col), int(row)


# ------------------------------------------------------------------ fixture

@pytest.fixture(scope="session")
def g6_state(rpc, build_runner):
    """Etat LIVE reel (Judh + necron) charge offline, rejouable a volonte."""
    from engine.entities.pathfinding.board import Board
    from engine.runner.snapshot import load_state
    from engine.runner.prng import IntBasedMersenneTwister

    rid = build_runner("777", extra=BUILD)["rid"]
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    if not (isinstance(bg, dict) and bg.get("tiles")):
        pytest.skip("boardGraph indispo")
    board = Board(bg["tiles"], adjacency="evenq")
    dv = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    ob = rpc("observeBattle", {"runnerId": rid}, 40)
    snap = rpc("combatSnapshot", {"runnerId": rid}, 60)
    rng0 = rpc("dumpRng", {"runnerId": rid}, 30)

    def build_state():
        st = load_state(dv, ob, snap, board=board)
        if isinstance(rng0, dict) and rng0.get("mt"):
            r = IntBasedMersenneTwister()
            r.mt = list(rng0["mt"]); r.mti = rng0["mti"]
            st.rng = r
        return st

    probe = build_state()
    judh = _find_by_vis(probe, JUDH_VIS)
    enemy = _find_by_vis(probe, ENEMY_VIS)
    if judh is None or enemy is None:
        pytest.skip("Judh (genesKelermorph) et/ou ennemi (necroWarden) absents du build")
    if _hc(probe, judh) is None or _hc(probe, judh).hp is None:
        pytest.skip("Judh sans HealthComponent capte")
    return {"build_state": build_state, "board": board}


def _judh_enemy(state):
    judh = _find_by_vis(state, JUDH_VIS)
    enemy = _find_by_vis(state, ENEMY_VIS)
    return judh, enemy


# ------------------------------------------------------------------ tests

def test_g6_judh_carries_minimal_health_effect(g6_state):
    """(A) Judh porte l'effet 1380 HypersensoryAbilities_MinimalHealth des le build initial (auto-pose via la
    boucle ABILITIES d'InitializeActorAbilities) -- l'effet est INACTIF au capture (pas tour ennemi) donc
    ABSENT de decisionView.effects : sa presence PROUVE le seed ability-owner-effect. Aucun floor pose encore."""
    state = g6_state["build_state"]()
    judh, _ = _judh_enemy(state)
    eff = _minimal_effect(state, judh)
    assert eff is not None, "Judh doit porter HypersensoryAbilities_MinimalHealth (auto-pose init passif)"
    # pct = hpPct[niveau passif]. VALEUR BRUTE level-indexee (var 0x26, NON rarity-scalee :
    # `variablesAffectedByRarityBonus` = [minDmg, maxDmg]) -> l'oracle est la CONFIG. La plage n'est PAS
    # ecrite : elle est DERIVEE du tableau per-niveau `abilities.HypersensoryAbilities.variables.hpPct`,
    # dont les DEUX bornes sont le min et le max. On exige l'APPARTENANCE (plus fort qu'un encadrement :
    # une valeur intermediaire absente du tableau serait rejetee).
    levels = ability_variable_levels("HypersensoryAbilities", "hpPct")
    pct = eff.minimal_health_pct()
    assert pct in levels, (
        f"hpPct {pct} absent de abilities.HypersensoryAbilities.variables.hpPct "
        f"(plage per-niveau [{min(levels)},{max(levels)}])")
    # Pas de floor tant que le driver n'a pas tourne pour un tour ennemi.
    assert _hc(state, judh).minimal_health is None, "aucun floor pose avant evaluation"


def test_g6_floor_applied_enemy_turn_cleared_own_turn(g6_state):
    """(B) Driver ActiveCondition : au tour ENNEMI de Judh -> floor = Min(Round(hp x pct/100), hp-1) pose ;
    au tour de JUDH -> efface (IsEnemyTurn faux)."""
    from engine.runner.operations.minimal_health import evaluate_minimal_health, reset_times_attacked
    state = g6_state["build_state"]()
    judh, enemy = _judh_enemy(state)
    jp, ep = _player(state, judh), _player(state, enemy)
    assert jp is not None and ep is not None and jp != ep
    hc = _hc(state, judh)
    eff = _minimal_effect(state, judh)
    hp0 = hc.hp
    expected = eff.compute_floor(hp0)
    assert expected is not None and 0 < expected < hp0

    # tour ENNEMI -> Apply
    reset_times_attacked(state)
    evaluate_minimal_health(state, ep)
    assert hc.minimal_health == expected, f"floor tour ennemi {hc.minimal_health} != {expected}"
    # coherence 1:1 avec la formule d'effet + ~pct% du HP
    assert hc.minimal_health == min(round(hp0 * eff.minimal_health_pct() / 100.0), hp0 - 1)

    # tour de JUDH -> Revert
    reset_times_attacked(state)
    evaluate_minimal_health(state, jp)
    assert hc.minimal_health is None, "floor doit etre efface au tour de Judh (pas tour ennemi)"


def test_g6_reduce_clamps_to_floor(g6_state):
    """(C) `HealthComponent.reduce` (mirror FillUpStatComponent.Reduce) : avec un floor pose, un degat LETAL
    est borne -> les PV finissent a exactement le floor (pas 0)."""
    from engine.runner.operations.minimal_health import evaluate_minimal_health, reset_times_attacked
    state = g6_state["build_state"]()
    judh, enemy = _judh_enemy(state)
    ep = _player(state, enemy)
    hc = _hc(state, judh)
    reset_times_attacked(state)
    evaluate_minimal_health(state, ep)
    floor = hc.minimal_health
    assert floor is not None and floor > 0
    hp0 = hc.hp
    applied = hc.reduce(hp0 * 4)             # degat tres largement letal
    assert hc.hp == floor, f"PV clamped attendu {floor}, obtenu {hc.hp}"
    assert applied == hp0 - floor
    # bypass explicite -> descend a 0 (param_3 natif)
    hc.minimal_health = floor
    hc.hp = hp0
    applied2 = hc.reduce(hp0 * 4, ignore_minimal=True)
    assert hc.hp == 0 and applied2 == hp0


def test_g6_first_attack_survives_second_kills(g6_state):
    """(D) Pipeline complet : au tour ENNEMI, la 1re attaque LETALE est bornee au floor (Judh survit) +
    compteur=1 + floor efface ; la 2e attaque (plus de floor) TUE. Attaques via `execute_normal_like`
    (degat controle, perce l'armure) pour garantir la letalite quel que soit l'ennemi."""
    from engine.runner.operations.minimal_health import evaluate_minimal_health, reset_times_attacked
    from engine.runner.operations.damage import AttackDamageOperation
    state = g6_state["build_state"]()
    judh, enemy = _judh_enemy(state)
    ep = _player(state, enemy)
    hc = _hc(state, judh)
    uc = _uc(state, judh)
    hp0 = hc.hp
    lethal = hp0 * 50                        # base >> PV, percage 100 -> total letal certain

    # debut de tour ennemi -> floor pose
    reset_times_attacked(state)
    evaluate_minimal_health(state, ep)
    floor = hc.minimal_health
    assert floor is not None and floor > 0
    assert uc.times_attacked_this_turn == 0

    # 1re attaque letale -> clampee au floor, Judh survit
    r1 = AttackDamageOperation.execute_normal_like(state, enemy, judh, base=lethal,
                                                   profile_pierce=100, spread_pct=0)
    assert r1 is not None
    assert uc.alive is True, "Judh ne doit PAS mourir a la 1re attaque du tour ennemi"
    assert hc.hp == floor, f"1re attaque : PV {hc.hp} != floor {floor}"
    assert uc.times_attacked_this_turn == 1, "compteur d'attaques recues doit etre 1"
    assert hc.minimal_health is None, "floor efface apres la 1re attaque (attacked>=1)"

    # 2e attaque (plus de floor) -> Judh meurt
    AttackDamageOperation.execute_normal_like(state, enemy, judh, base=lethal,
                                              profile_pierce=100, spread_pct=0)
    assert hc.hp == 0, f"2e attaque : Judh doit tomber a 0 (obtenu {hc.hp})"
    assert uc.alive is False, "Judh doit mourir a la 2e attaque (floor retire)"
    assert uc.times_attacked_this_turn == 2


def test_g6_reset_times_attacked(g6_state):
    """(E) `reset_times_attacked` (start_turn) remet le compteur d'attaques recues a 0 pour toutes les unites."""
    from engine.runner.operations.minimal_health import reset_times_attacked, record_attacked
    state = g6_state["build_state"]()
    judh, _ = _judh_enemy(state)
    record_attacked(state, judh)
    record_attacked(state, judh)
    assert _uc(state, judh).times_attacked_this_turn == 2
    reset_times_attacked(state)
    assert _uc(state, judh).times_attacked_this_turn == 0
