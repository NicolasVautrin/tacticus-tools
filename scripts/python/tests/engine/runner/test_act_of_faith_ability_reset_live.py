"""RESET ActOfFaith au crit d'une ATTAQUE D'ABILITY / SPLASH — replay MOTEUR offline (#138).

Le natif fait tourner `EvaluateAfterHitTriggers` (porté par `ADamageOperation`) per-coup pour TOUTE
attaque, NORMALE **et** ability → un crit d'ability/splash reset les stacks ActOfFaith. Le port ne
câblait le vecteur after-hit générique que pour l'attaque normale (`after_hit_normal_attack`). #138 :
`execute_ability_attack`/`execute_normal_like` appellent désormais `after_hit_ability_attack` → le reset
fire aussi pour une ability (ArmoriumCherub) ou un coup de splash (AoE FireOfAbsolution).

Ce test valide la BRANCHE MOTEUR (pas le jeu, déjà validé par `test_act_of_faith_reset_live`) et le fait
en ACCUMULANT depuis 0 offline (deltas trackés → revert EXACT), PUIS en faisant crit la Sister via la
voie ability :
  1. `load_state` d'une Sister (`adeptCanoness`, `--crit 100,250` → cc=100 → crite toujours) au déploiement
     (0 stack) ; base crit lue, pas supposée ;
  2. offline : `AddEffectOperation.execute(ActOfFaith_Effect)` → +1 stack (feuille AddEffect ->
     ApplyModification ; cd boostée > base) ;
  3. offline : `execute_ability_attack(Sister -> ennemi, Flame)` → cc=100 → CRIT → `after_hit` déclenche
     le reset ActOfFaith → crit REVIENT EXACTEMENT à la base.
Ennemi non-létalement touché (base=1) pour éviter le vecteur MORT (qui ré-accumulerait via la Sister
Imperial). Déterministe (cc=100) : indépendant du seed/RNG.

⚠ ADJACENCE/PORTÉE = mode **evenq**.
"""
from __future__ import annotations

import pytest

from engine.entities.stats import StatType
from engine.runner.snapshot import load_state
from engine.runner.prng import IntBasedMersenneTwister
from engine.runner.components import StatsComponent, HealthComponent
from engine.runner.operations.damage import AttackDamageOperation
from engine.runner.operations.effects import AddEffectOperation
from engine.runner.operations.triggers import ACTOFFAITH_EFFECT

SISTER_VIS = "adeptCanoness"        # trait ActOfFaith ; --crit 100,250 → cd != 0 (gate) + crite toujours
ENEMY_VIS = "necroDestroyer"
ENEMY2_VIS = "necroOverlord"        # 2e ennemi : la bataille survit (snapshot lisible)
BUILD = ["--roster", "1", "--p-units", SISTER_VIS,
         "--a-units", f"{ENEMY_VIS},{ENEMY2_VIS}", "--crit", "100,250", "--hp-target", "800"]


def _ok(r):
    return isinstance(r, dict) and r.get("ok")


def _seed_rng(s):
    rng = IntBasedMersenneTwister()
    rng.mt = list(s["mt"]); rng.mti = s["mti"]
    return rng


def test_act_of_faith_resets_on_ability_crit_moteur(live_session, rpc, build_runner):
    """Un crit porté par la Sister via `execute_ability_attack` reset ses stacks ActOfFaith (moteur)."""
    from engine.entities.pathfinding.board import Board
    rid = build_runner("777", extra=BUILD)["rid"]
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    if not (isinstance(bg, dict) and bg.get("tiles")):
        pytest.skip("boardGraph indispo")
    board = Board(bg["tiles"], adjacency="evenq")

    dec0 = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    ob0 = rpc("observeBattle", {"runnerId": rid}, 40)
    snap0 = rpc("combatSnapshot", {"runnerId": rid}, 60)
    s0 = rpc("dumpRng", {"runnerId": rid}, 30)
    if not (_ok(dec0) and _ok(s0)):
        pytest.skip("decisionView / dumpRng KO")
    units0 = dec0.get("units") or []
    sister = next((u for u in units0 if u.get("visualId") == SISTER_VIS and u.get("alive")), None)
    if sister is None:
        pytest.skip("Sister absente")
    my_team = sister.get("team")
    enemy = next((u for u in units0 if u.get("team") != my_team and u.get("alive") and u.get("pos")), None)
    if enemy is None:
        pytest.skip("aucun ennemi vivant")
    sister_id, enemy_id = sister["id"], enemy["id"]

    # === MOTEUR offline : etat live au deploiement (0 stack ActOfFaith) ===
    state = load_state(dec0, ob0, snap0)
    state.board = board
    state.rng = _seed_rng(s0)
    si = state.get_entity(sister_id)
    en = state.get_entity(enemy_id)
    if (si is None or si.get_component(StatsComponent) is None
            or en is None or en.get_component(HealthComponent) is None):
        pytest.skip("Sister/ennemi sans composant offline (combatSnapshot ne couvre pas)")
    ctx = si.get_component(StatsComponent).ctx
    base_cc, base_cd = ctx.stat(StatType.CRIT_CHANCE), ctx.stat(StatType.CRIT_DAMAGE)
    if not base_cc or not base_cd:
        pytest.skip(f"Sister sans crit de base (cc={base_cc} cd={base_cd}) — gate ActOfFaith")

    # (1) ACCUMULER un stack offline via le VRAI chemin de pose (feuille DSL AddEffect ->
    # AddEffectOperation -> ActOfFaithBuffEffect.ApplyModification, keye par-source) -> revert exact au reset.
    AddEffectOperation.execute(state, source=sister_id, target=sister_id,
                               effect_type=ACTOFFAITH_EFFECT, name="ActOfFaith_Effect")
    boost_cc, boost_cd = ctx.stat(StatType.CRIT_CHANCE), ctx.stat(StatType.CRIT_DAMAGE)
    assert boost_cc > base_cc or boost_cd > base_cd, (
        f"accumulation KO : boostee ({boost_cc},{boost_cd}) <= base ({base_cc},{base_cd})")

    # (2) La Sister CRITE via une ability (base=1 -> non letal, pas de vecteur MORT). cc=100 => crit sur.
    hp_en_before = en.get_component(HealthComponent).hp
    res = AttackDamageOperation.execute_ability_attack(
        state, sister_id, enemy_id, base_min=1, base_max=1, profile_pierce=0,
        hits=1, damage_profile="Flame", is_melee=False)
    if res is None:
        pytest.skip("execute_ability_attack a rendu None (rng non cale)")
    hp_en_after = en.get_component(HealthComponent).hp

    reset_cc, reset_cd = ctx.stat(StatType.CRIT_CHANCE), ctx.stat(StatType.CRIT_DAMAGE)
    after_hit = res.get("after_hit") or []
    print(f"\n[AOF-ABILITY-RESET] base cc={base_cc} cd={base_cd} | boostee ({boost_cc},{boost_cd}) | "
          f"did_crit={res.get('did_crit')} | apres cast ({reset_cc},{reset_cd}) | "
          f"after_hit={[d.get('trait') for d in after_hit]}")

    # ennemi survit (pas de vecteur MORT parasite qui re-accumulerait).
    assert hp_en_after > 0, f"ennemi mort (hp {hp_en_before}->{hp_en_after}) — base trop haute, MORT parasite"
    # la Sister a bien crit via l'ability (cc=100).
    assert res.get("did_crit") is True, f"la Sister n'a pas crit (cc={boost_cc}) — reset non exercé"
    # le vecteur after-hit d'ability a declenche le RESET ActOfFaith.
    assert any(d.get("trait") == "ActOfFaith" and (d.get("removed") or 0) >= 1 for d in after_hit), (
        f"reset ActOfFaith NON declenche par le crit d'ability (after_hit={after_hit})")
    # crit REVIENT EXACTEMENT a la base (accumulate-from-0 => revert exact).
    assert (reset_cc, reset_cd) == (base_cc, base_cd), (
        f"reset KO : apres crit d'ability ({reset_cc},{reset_cd}), attendu base ({base_cc},{base_cd})")
