"""#151 — Le crit d'une attaque NORMALE ne reset PAS ActOfFaith ; seul le crit d'ABILITY le reset.

Confront DISCRIMINANT du fix #151 (event-mapping ancre decompile) : le natif
`ActOfFaith_RemoveEffectAbility.CreateTrigger @181219f90` = `On(9) & OwnerIsCaster & WasCrit &
HasEffect(0x3f9)`, ou `On(9)=Attack` (attaque d'ABILITY, `EventTriggerType.Attack`) est DISTINCT de
`On(0x26)=NormalAttack`. L'ancien port mappait le reset sur l'after-hit `On(8)=AttackHit` (partage par
les DEUX chemins) -> il fire aussi sur un crit d'attaque NORMALE. #151 route le reset sur `On(9)`
(dispatche par `after_hit_ability_attack` UNIQUEMENT).

Le test ACCUMULE un stack depuis 0 (deltas trackes -> revert exact), puis exerce les DEUX vecteurs
sur la MEME Sister boostee, dans l'ordre :
  1. `after_hit_normal_attack(..., is_crit=True)` -> AUCUN reset : les stats crit RESTENT boostees ;
  2. `after_hit_ability_attack(..., is_crit=True)` -> reset : les stats crit REVIENNENT a la base.
Deterministe (is_crit force a True) : independant du seed/RNG. Complement de
`test_act_of_faith_ability_reset_live` (branche ability) et garde-fou du fix #151.

ADJACENCE/PORTEE = mode evenq.
"""
from __future__ import annotations

import pytest

from engine.entities.stats import StatType
from engine.runner.snapshot import load_state
from engine.runner.components import StatsComponent, HealthComponent
from engine.runner.operations.effects import AddEffectOperation
from engine.runner.operations.triggers import (
    ACTOFFAITH_EFFECT, after_hit_ability_attack, after_hit_normal_attack,
)

SISTER_VIS = "adeptCanoness"        # trait ActOfFaith ; --crit 100,250 -> cd != 0 (gate) + crite toujours
ENEMY_VIS = "necroDestroyer"
ENEMY2_VIS = "necroOverlord"        # 2e ennemi : la bataille survit (snapshot lisible)
BUILD = ["--roster", "1", "--p-units", SISTER_VIS,
         "--a-units", f"{ENEMY_VIS},{ENEMY2_VIS}", "--crit", "100,250", "--hp-target", "800"]


def _ok(r):
    return isinstance(r, dict) and r.get("ok")


def _has_aof_reset(after_hit):
    return any(d.get("trait") == "ActOfFaith" and (d.get("removed") or 0) >= 1
               for d in (after_hit or []))


def test_normal_crit_does_not_reset_ability_crit_does(live_session, rpc, build_runner):
    """#151 : crit NORMAL -> pas de reset (stats boostees conservees) ; crit ABILITY -> reset (base)."""
    from engine.entities.pathfinding.board import Board
    rid = build_runner("777", extra=BUILD)["rid"]
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    if not (isinstance(bg, dict) and bg.get("tiles")):
        pytest.skip("boardGraph indispo")
    board = Board(bg["tiles"], adjacency="evenq")

    dec0 = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    ob0 = rpc("observeBattle", {"runnerId": rid}, 40)
    snap0 = rpc("combatSnapshot", {"runnerId": rid}, 60)
    if not _ok(dec0):
        pytest.skip("decisionView KO")
    units0 = dec0.get("units") or []
    sister = next((u for u in units0 if u.get("visualId") == SISTER_VIS and u.get("alive")), None)
    if sister is None:
        pytest.skip("Sister absente")
    my_team = sister.get("team")
    enemy = next((u for u in units0 if u.get("team") != my_team and u.get("alive") and u.get("pos")), None)
    if enemy is None:
        pytest.skip("aucun ennemi vivant")
    sister_id, enemy_id = sister["id"], enemy["id"]

    state = load_state(dec0, ob0, snap0)
    state.board = board
    si = state.get_entity(sister_id)
    en = state.get_entity(enemy_id)
    if (si is None or si.get_component(StatsComponent) is None
            or en is None or en.get_component(HealthComponent) is None):
        pytest.skip("Sister/ennemi sans composant offline (combatSnapshot ne couvre pas)")
    ctx = si.get_component(StatsComponent).ctx
    base_cc, base_cd = ctx.stat(StatType.CRIT_CHANCE), ctx.stat(StatType.CRIT_DAMAGE)
    if not base_cc or not base_cd:
        pytest.skip(f"Sister sans crit de base (cc={base_cc} cd={base_cd}) - gate ActOfFaith")

    # (1) ACCUMULER un stack via le VRAI chemin de pose (feuille DSL AddEffect -> AddEffectOperation ->
    # ActOfFaithBuffEffect.ApplyModification, keye par-source) -> revert exact au reset.
    AddEffectOperation.execute(state, source=sister_id, target=sister_id,
                               effect_type=ACTOFFAITH_EFFECT, name="ActOfFaith_Effect")
    boost_cc, boost_cd = ctx.stat(StatType.CRIT_CHANCE), ctx.stat(StatType.CRIT_DAMAGE)
    assert boost_cc > base_cc or boost_cd > base_cd, (
        f"accumulation KO : boostee ({boost_cc},{boost_cd}) <= base ({base_cc},{base_cd})")

    # (2) Vecteur NORMAL, crit force -> PAS de reset (On(0x26)+On(8), jamais On(9)).
    ah_normal = after_hit_normal_attack(state, sister_id, enemy_id,
                                        ranged=False, profile=None, is_crit=True)
    n_cc, n_cd = ctx.stat(StatType.CRIT_CHANCE), ctx.stat(StatType.CRIT_DAMAGE)
    print(f"\n[AOF-NORMAL-NO-RESET] base ({base_cc},{base_cd}) boostee ({boost_cc},{boost_cd}) | "
          f"apres NORMAL crit ({n_cc},{n_cd}) aof_reset={_has_aof_reset(ah_normal)}")
    assert not _has_aof_reset(ah_normal), (
        f"#151 REGRESSION : le crit NORMAL a reset ActOfFaith (after_hit={ah_normal})")
    assert (n_cc, n_cd) == (boost_cc, boost_cd), (
        f"#151 REGRESSION : stats crit alterees par un crit NORMAL "
        f"({n_cc},{n_cd}) != boostee ({boost_cc},{boost_cd})")

    # (3) Vecteur ABILITY, crit force -> reset (On(9)) : stats reviennent EXACTEMENT a la base.
    ah_ability = after_hit_ability_attack(state, sister_id, enemy_id, is_crit=True, profile="Flame")
    a_cc, a_cd = ctx.stat(StatType.CRIT_CHANCE), ctx.stat(StatType.CRIT_DAMAGE)
    print(f"[AOF-ABILITY-RESET] apres ABILITY crit ({a_cc},{a_cd}) aof_reset={_has_aof_reset(ah_ability)}")
    assert _has_aof_reset(ah_ability), (
        f"reset ActOfFaith NON declenche par le crit d'ABILITY (after_hit={ah_ability})")
    assert (a_cc, a_cd) == (base_cc, base_cd), (
        f"reset KO : apres crit d'ability ({a_cc},{a_cd}), attendu base ({base_cc},{base_cd})")
