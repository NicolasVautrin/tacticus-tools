"""ActOfFaith reset au crit : les DEUX voies (attaque NORMALE et ability) resettent le buff (port offline).

Contrepartie OFFLINE de `test_act_of_faith_normal_crit_resets_live.py` (confirmation LIVE) : valide la MATH de
revert exacte du port. `On(9)=Attack` etant un event GENERIQUE (`FinishAttackOperation`, emis pour TOUTE
attaque) et le reset @181219f90 = `On(9) & OwnerIsCaster & WasCrit & HasEffect(0x3f9)` SANS gate normal/ability,
un crit reset ActOfFaith **quelle que soit la voie** — normale ET ability. (Correction de l'ancien verdict
#151 qui croyait `On(9)` ability-only via `OnNormalAttackOrSmite` ; confirme en LIVE, cf. le test dedie.)

Le test ACCUMULE un stack depuis 0 (deltas trackes -> revert exact), puis exerce CHAQUE voie sur la MEME Sister
boostee : `after_hit_normal_attack(is_crit=True)` reset -> base, PUIS re-accumule et
`after_hit_ability_attack(is_crit=True)` reset -> base. Deterministe (is_crit force). ADJACENCE = evenq.
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
ENEMY2_VIS = "necroOverlord"
BUILD = ["--roster", "1", "--p-units", SISTER_VIS,
         "--a-units", f"{ENEMY_VIS},{ENEMY2_VIS}", "--crit", "100,250", "--hp-target", "800"]


def _ok(r):
    return isinstance(r, dict) and r.get("ok")


def _has_aof_reset(after_hit):
    return any(d.get("trait") == "ActOfFaith" and (d.get("removed") or 0) >= 1
               for d in (after_hit or []))


def test_normal_and_ability_crit_both_reset(live_session, rpc, build_runner):
    """Les DEUX voies resettent ActOfFaith : crit NORMAL -> reset (base) ; crit ABILITY -> reset (base)."""
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

    def _accumulate_one():
        """Pose UN stack via le VRAI chemin (feuille DSL AddEffect -> ActOfFaithBuffEffect.ApplyModification,
        keye par-source) -> revert exact au reset. Renvoie (cc, cd) boostes."""
        AddEffectOperation.execute(state, source=sister_id, target=sister_id,
                                   effect_type=ACTOFFAITH_EFFECT, name="ActOfFaith_Effect")
        return ctx.stat(StatType.CRIT_CHANCE), ctx.stat(StatType.CRIT_DAMAGE)

    # (1) VOIE NORMALE : accumuler -> crit force -> RESET a la base.
    boost_cc, boost_cd = _accumulate_one()
    assert boost_cc > base_cc or boost_cd > base_cd, (
        f"accumulation KO : boostee ({boost_cc},{boost_cd}) <= base ({base_cc},{base_cd})")
    ah_normal = after_hit_normal_attack(state, sister_id, enemy_id,
                                        ranged=False, profile=None, is_crit=True)
    n_cc, n_cd = ctx.stat(StatType.CRIT_CHANCE), ctx.stat(StatType.CRIT_DAMAGE)
    print(f"\n[AOF-NORMAL-CRIT-RESET] base ({base_cc},{base_cd}) boostee ({boost_cc},{boost_cd}) | "
          f"apres NORMAL crit ({n_cc},{n_cd}) aof_reset={_has_aof_reset(ah_normal)}")
    assert _has_aof_reset(ah_normal), (
        f"le crit NORMAL doit reset ActOfFaith (On(9) generique -- corrige #151 ; after_hit={ah_normal})")
    assert (n_cc, n_cd) == (base_cc, base_cd), (
        f"reset NORMAL KO : stats crit ({n_cc},{n_cd}) != base ({base_cc},{base_cd})")

    # (2) VOIE ABILITY : re-accumuler -> crit force -> RESET a la base (inchange).
    boost2_cc, boost2_cd = _accumulate_one()
    assert boost2_cc > base_cc or boost2_cd > base_cd, "re-accumulation KO avant la voie ability"
    ah_ability = after_hit_ability_attack(state, sister_id, enemy_id, is_crit=True, profile="Flame")
    a_cc, a_cd = ctx.stat(StatType.CRIT_CHANCE), ctx.stat(StatType.CRIT_DAMAGE)
    print(f"[AOF-ABILITY-CRIT-RESET] apres ABILITY crit ({a_cc},{a_cd}) aof_reset={_has_aof_reset(ah_ability)}")
    assert _has_aof_reset(ah_ability), (
        f"le crit d'ABILITY doit reset ActOfFaith (after_hit={ah_ability})")
    assert (a_cc, a_cd) == (base_cc, base_cd), (
        f"reset ABILITY KO : apres crit d'ability ({a_cc},{a_cd}), attendu base ({base_cc},{base_cd})")
