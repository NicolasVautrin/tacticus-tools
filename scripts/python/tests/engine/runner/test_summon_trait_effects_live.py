"""VALIDATION du seed des OWNER-EFFECTS de trait au spawn d'un summon (gap traits-des-summons).

RE : `IdunBattle.Operations.InitializeActorAbilitiesOperation$$Execute (boucle TRAITS) ajoute au porteur les effets de
`idun.Idun.Source.Shared.Battle.StaticBattleRules.StaticBattleRules.Trait$$GetEffectToBeAddedToOwnerForTrait (dict `Trait..idun.Idun.Source.Shared.Battle.StaticBattleRules.StaticBattleRules.Trait$$.cctor +0x30,
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
    (BigTarget 0x406)->`IdunBattleLogic.Entities.Abilities.Active.Loki.BigTargetAbility$$CreateBehaviour` AddEffect(0x402). Matérialisé en CLASSE
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


def test_diminutive_summon_seeds_via_derived_ability(rpc, build_runner):
    """#75 — orksGrot (trait Diminutive 0x408=1032) : `Diminutive_HitReduction` seede via le chemin
    trait->ability derivee (`idun.Idun.Source.Shared.Battle.StaticBattleRules.StaticBattleRules.Trait$$GetTriggeredAbility` -> TriggeredAbilityType.Diminutive
    0x43f=1087 -> `DiminutiveAbility` IdunBattleLogic.Entities.Abilities.Triggered.Loki.DiminutiveAbility$$.ctor = `AOwnerEffectSpecificTriggeredAbility(0x43f)`
    IdunBattle.Entities.Abilities.AOwnerEffectSpecificTriggeredAbility$$.ctor, `IdunBattle.Entities.Abilities.AOwnerEffectSpecificTriggeredAbility$$CreateTrigger` = OnOwnerSpecificAbilityInit -> AddEffect(owner)).

    GROUND TRUTH LIVE (runner 1155, orksRuntherd GetEmRuntz) : les grots spawnes portent
    `UnitStats_TriggeredAbility_Id=1087` ET l'effet `Diminutive_HitReduction` (decisionView).
    Materialise en CLASSE (pas un BaseEffect no-op) sinon la reduction de coups serait perdue."""
    state, dec = _load(rpc, build_runner)
    sid = _spawn(state, dec, "orksGrot")
    effs = state.effects.active_effects(sid, {"hp": 1}) if state.effects is not None else []
    names = [getattr(e, "name", None) for e in effs]
    dim = next((e for e in effs if getattr(e, "name", None) == "Diminutive_HitReduction"), None)
    print(f"\n[DIMINUTIVE] summon effects={names} class={type(dim).__name__ if dim else None}")
    assert dim is not None, f"Diminutive_HitReduction NON seede au spawn : {names}"
    assert type(dim).__name__ == "DiminutiveHitReductionEffect", \
        f"effet materialise en {type(dim).__name__} (attendu DiminutiveHitReductionEffect, pas un no-op)"


def test_diminutive_reduces_hits_melee_and_ranged(rpc, build_runner):
    """#75 — le trigger natif IdunBattle.Entities.Effects.Loki.Diminutive_HitReductionEffect$$CreateEffectHitsBonusForAttack est `OwnerIsTarget` SEUL (aucun noeud IsMelee/IsRanged, aucun
    gate de profil) : la reduction s'applique aux DEUX axes. C'est ce qui DISCRIMINE Diminutive de
    Parry (melee-only IdunBattle.Entities.Effects.Loki.ParryEffect$$CreateEffectHitsBonusForAttack) et Camouflage (ranged-only IdunBattleLogic.Entities.Abilities.Triggered.Loki.Camouflage_HitReductionEffect$$CreateEffectHitsBonusForAttack) — un port qui recopierait
    l'un de ces deux jumeaux echouerait ici.

    GROUND TRUTH LIVE (runner 1155, A/B meme attaquant u83 orksBigMek arme 4 coups, ability 69,
    Attack_Weapon_IsMelee=1) : vs u77 orksRuntherd (sans Diminutive) = 4 coups d'arme ; vs u120 Grot
    (Diminutive) = 3 coups d'arme -> exactement -1 EN MELEE."""
    from engine.entities.effects import hits_malus_from_defender_effects
    state, dec = _load(rpc, build_runner)
    sid = _spawn(state, dec, "orksGrot")
    effs = state.effects.active_effects(sid, {"hp": 1}) if state.effects is not None else []
    melee = hits_malus_from_defender_effects(effs, is_melee=True)
    ranged = hits_malus_from_defender_effects(effs, is_melee=False)
    print(f"\n[DIMINUTIVE-HITS] melee={melee} ranged={ranged}")
    assert melee == -1, f"malus MELEE attendu -1 (ground truth live 4->3 coups), obtenu {melee}"
    assert ranged == -1, f"malus RANGED attendu -1 (trigger OwnerIsTarget SEUL), obtenu {ranged}"


def test_control_summon_without_diminutive_keeps_hits(rpc, build_runner):
    """#75 CONTROLE — un summon SANS le trait Diminutive n'ecope d'aucun malus de coups (garde contre
    un seed pose a tort sur tout summon)."""
    from engine.entities.effects import hits_malus_from_defender_effects
    state, dec = _load(rpc, build_runner)
    sid = _spawn(state, dec, "necroSmnSwarm")     # Summon/LivingMetal/Mechanical/Swarm/Flying
    effs = state.effects.active_effects(sid, {"hp": 1}) if state.effects is not None else []
    names = [getattr(e, "name", None) for e in effs]
    assert "Diminutive_HitReduction" not in names, f"Diminutive seede a tort : {names}"
    for melee in (True, False):
        assert hits_malus_from_defender_effects(effs, is_melee=melee) == 0, \
            f"malus de coups non nul sur un summon sans Diminutive : {names}"


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
