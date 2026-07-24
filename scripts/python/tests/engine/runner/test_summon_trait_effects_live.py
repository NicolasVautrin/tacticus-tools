"""VALIDATION du seed des OWNER-EFFECTS de trait au spawn d'un summon (gap traits-des-summons).

RE : `InitializeActorAbilitiesOperation.Execute` @180e74660 (boucle TRAITS) ajoute au porteur les effets de
`StaticBattleRules.Trait.GetEffectToBeAddedToOwnerForTrait` @18157e800 (dict `Trait..cctor` @18157f650 +0x30,
4 entrées LUES). `SpawnUnitOperation` mirror ce seed dans `EffectsState`. Ici on spawn des summons PORTEURS
d'un trait de la dict et on vérifie (1) l'effet seedé, (2) qu'il s'applique aux MODIFIERS d'attaque du summon
(ce que le gap ratait), + un CONTRÔLE sans trait.

State seedé depuis un build live (gameconfig réel). NON committe.
"""
from __future__ import annotations

import pytest

from engine.runner.snapshot import load_state
from engine.runner.operations.spawn import SpawnUnitOperation
from engine.runner.damage_model import attacker_modifiers
from engine.runner.components import OwnerComponent, StatsComponent


def _load(rpc, build_runner):
    from engine.entities.pathfinding.board import Board
    rid = build_runner("777")["rid"]
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    board = Board(bg["tiles"], adjacency="evenq") if isinstance(bg, dict) and bg.get("tiles") else None
    dec = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    ob = rpc("observeBattle", {"runnerId": rid}, 40)
    snap = rpc("combatSnapshot", {"runnerId": rid}, 60)
    state = load_state(dec, ob, snap, board=board)
    return state, dec


def _spawn(state, dec, visual):
    """Spawn 1 summon `visual` avec un caster réel (pour level/mult). Renvoie l'entityId."""
    caster = next((u for u in (dec.get("units") or [])), None)
    if caster is None:
        pytest.skip("aucun caster")
    caster_id = caster["id"]
    if state.get_entity(caster_id) is None or \
            state.get_entity(caster_id).get_component(StatsComponent) is None:
        pytest.skip("caster sans StatsComponent")
    target_id = caster_id                      # placement indifférent (on teste les effets, pas la tuile)
    before = set(state.entities.keys())
    SpawnUnitOperation.execute(state, caster_id, target_id, "ScarabHive", visual, 1)
    new = [i for i in state.entities.keys() if i not in before]
    if not new:
        pytest.skip(f"spawn {visual} KO")
    return new[0]


def _eff_names(state, uid):
    return [getattr(e, "name", None) for e in state.effects.active_effects(uid, {"hp": 1})] \
        if state.effects is not None else []


def _has_pct_bonus(state, uid, is_ranged):
    mods, _ = attacker_modifiers(state, uid, 1, is_ranged=is_ranged)
    return bool(mods is not None and getattr(mods, "pct_list", None))


def test_ranged_specialist_summon_seeds_and_applies(rpc, build_runner):
    """tauSmnStealthSuit (trait RangedSpecialist) : effet seedé + +% appliqué SEULEMENT en RANGED."""
    state, dec = _load(rpc, build_runner)
    sid = _spawn(state, dec, "tauSmnStealthSuit")
    names = _eff_names(state, sid)
    print(f"\n[RANGED-SPEC] summon effects={names} "
          f"ranged_bonus={_has_pct_bonus(state, sid, True)} melee_bonus={_has_pct_bonus(state, sid, False)}")
    assert "RangedSpecialist" in names, f"effet RangedSpecialist NON seedé au spawn : {names}"
    assert _has_pct_bonus(state, sid, True) is True, "bonus RANGED du trait non appliqué (gap NON corrigé)"
    assert _has_pct_bonus(state, sid, False) is False, "bonus appliqué en MELEE (gate IsRangedAttack cassée)"


def test_heavy_weapon_summon_seeds(rpc, build_runner):
    """necroSmnDeathmark (trait HeavyWeapon) : effet HeavyWeapon_ExtraDmg seedé au spawn."""
    state, dec = _load(rpc, build_runner)
    sid = _spawn(state, dec, "necroSmnDeathmark")
    names = _eff_names(state, sid)
    print(f"\n[HEAVY-WPN] summon effects={names}")
    assert "HeavyWeapon_ExtraDmg" in names, f"effet HeavyWeapon_ExtraDmg NON seedé : {names}"


def test_control_summon_without_trait_effect(rpc, build_runner):
    """necroSmnSwarm (Summon/LivingMetal/Mechanical/Swarm/Flying — AUCUN trait de la dict) : aucun owner-effect."""
    state, dec = _load(rpc, build_runner)
    sid = _spawn(state, dec, "necroSmnSwarm")
    names = _eff_names(state, sid)
    print(f"\n[CONTROL] necroSmnSwarm effects={names}")
    assert "RangedSpecialist" not in names and "HeavyWeapon_ExtraDmg" not in names, \
        f"owner-effect seedé à tort sur un summon sans trait de la dict : {names}"


def test_bigtarget_summon_seeds_via_derived_ability(rpc, build_runner):
    """tyranSmnWarrior (trait BigTarget) : BigTarget_AdjacentEffect seedé via le chemin trait->ability dérivée
    (BigTarget 0x406)->`BigTargetAbility.CreateBehaviour @18121a910` AddEffect(0x402). Matérialisé en CLASSE
    aura (pas un BaseEffect no-op)."""
    state, dec = _load(rpc, build_runner)
    sid = _spawn(state, dec, "tyranSmnWarrior")
    effs = state.effects.active_effects(sid, {"hp": 1}) if state.effects is not None else []
    names = [getattr(e, "name", None) for e in effs]
    bt = next((e for e in effs if getattr(e, "name", None) == "BigTarget_AdjacentEffect"), None)
    print(f"\n[BIGTARGET] summon effects={names} class={type(bt).__name__ if bt else None}")
    assert bt is not None, f"BigTarget_AdjacentEffect NON seedé au spawn : {names}"
    assert type(bt).__name__ == "BigTargetAdjacentEffect", \
        f"effet materialise en {type(bt).__name__} (attendu BigTargetAdjacentEffect, pas un no-op)"
    assert hasattr(bt, "create_aura_hits_malus_for_defense"), "methode aura absente"


def test_shadow_in_the_warp_summon_seeds_via_derived_ability(rpc, build_runner):
    """tyranSmnWarrior (trait ShadowInTheWarp) : ShadowInTheWarp_LessDmg_Effect seede via trait->ability
    derivee (ShadowInTheWarp_AddEffectAbility)->AddEffect, materialise en classe aura de reduction Psychique
    (-25%), pas un BaseEffect no-op."""
    state, dec = _load(rpc, build_runner)
    sid = _spawn(state, dec, "tyranSmnWarrior")
    effs = state.effects.active_effects(sid, {"hp": 1}) if state.effects is not None else []
    names = [getattr(e, "name", None) for e in effs]
    sw = next((e for e in effs if getattr(e, "name", None) == "ShadowInTheWarp_LessDmg_Effect"), None)
    print(f"\n[SHADOW-WARP] summon effects={names} class={type(sw).__name__ if sw else None}")
    assert sw is not None, f"ShadowInTheWarp_LessDmg_Effect NON seede au spawn : {names}"
    assert type(sw).__name__ == "ShadowInTheWarpLessDmgEffect", \
        f"effet materialise en {type(sw).__name__} (attendu ShadowInTheWarpLessDmgEffect, pas un no-op)"
    # aura Psychique -25% appliquee a un ENNEMI attaquant a portee, None sinon
    aura = sw.create_aura_attack_damage_malus_for_enemy(
        {"owner_pos": (5, 5), "owner_team": 2, "att_pos": (6, 5), "att_team": 1, "damage_profile": "Psychic"})
    assert aura is not None and aura.kind == "PercentDecrease" and aura.value == 25, \
        f"aura Psychique attendue -25%, obtenu {aura}"
