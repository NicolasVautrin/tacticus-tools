"""Plage de tirage de dégât calculée PAR LE RUNNER depuis son ECS (stats + effets).

Le but du chantier : un runner AUTONOME (fidèle ET modifiable). Cette couche assemble,
depuis les composants ECS (`StatsComponent` + `State.effects`), les entrées de la chaîne
de dégât VALIDÉE (`engine.services.damage_prediction.get_attack_prediction`) — au lieu de
relire l'oracle live. Elle expose la **plage BRUTE d'un coup** (pré-armure, pré-perçage,
mono-coup) = le `HitDamage` que `AttackDamageOperation.ExecuteHit` tire.

Découpage volontaire (couche stats+effets uniquement) :
  • base PAR COUP = `stat Attack` (StatAmountFormula(Attack)) → spread BC (CalculateDamageSpread).
  • × MODIFIERS attaquant bâtis depuis les EFFETS actifs (post-perçage §17.7 ; pré-perçage = id
    ici car armure/perçage = 0). Effets pré-tirage (ex. +ExtraDmg sur le stat) déjà cuits dans
    `ctx.attack`.
  • PAS de hits / arme / perçage / armure / cible : ce sont des paliers DAMAGE séparés. La plage
    d'UN coup est indépendante d'eux (perçage/armure s'appliquent APRÈS le tirage).

Validé par agrément : plage runner == plage `aiPredict` (pré-armure) PAR COUP, sur les unités
(`tests/engine/runner/test_runner_stats_effects_live.py`).
"""
from __future__ import annotations

from typing import Optional, Tuple

from .state import State
from .components import StatsComponent, HealthComponent
from ..services.damage_prediction import get_attack_prediction, apply_pierce_and_modifiers
from ..entities.effects import (
    build_attacker_modifiers_from_effects, build_defender_modifiers_from_effects,
    hits_bonus_from_effects,
)

_BIG_HP = 1 << 30          # santé cible « infinie » → scenario sans overkill/cap


def _cheby(a: Tuple[int, int], b: Tuple[int, int]) -> int:
    return max(abs(a[0] - b[0]), abs(a[1] - b[1]))


def select_weapon(ctx, dist: Optional[int]):
    """Arme de l'attaque normale sélectionnée par PORTÉE (mêlée si adjacent & arme mêlée existe ; sinon
    tir si arme ranged). Renvoie le dict d'arme gameconfig (ou None si aucune)."""
    import gameconfig as GC
    gu = GC.unit(ctx.visual_id or "") or {}
    weapons = gu.get("weapons") or []
    if not weapons:
        return None
    melee = [w for w in weapons if not w.get("Range")]
    ranged = [w for w in weapons if w.get("Range")]
    adjacent = dist is not None and dist <= 1
    cand = melee if (adjacent and melee) else (ranged if ranged else (melee or weapons))
    return next((x for x in cand if int(x.get("hits") or 0) == ctx.normal_hits), cand[0])


def select_weapon_pierce(ctx, dist: Optional[int]) -> Tuple[int, bool, int]:
    """Arme de l'attaque normale + perçage, sélection mêlée/ranged par PORTÉE (port de
    `predict_validate._normal_weapon_pierce`) : cible adjacente (dist≤1) → mêlée ; sinon
    tir si une arme ranged existe. pierce = clamp(0,100, profil.PiercingRatio + ExtraPierce(26)
    + ExtraPierce{Melee21|Ranged22}). Renvoie (pierce, is_ranged, whits)."""
    import gameconfig as GC
    w = select_weapon(ctx, dist)
    if w is None:
        return 100, False, 1
    dp = GC.damage_profile(w.get("DamageProfile")) or {}
    is_ranged = bool(w.get("Range"))
    dir_pierce = ctx.extra_pierce_ranged if is_ranged else ctx.extra_pierce_melee
    pierce = max(0, min(100, int(dp.get("PiercingRatio") or 0) + ctx.extra_pierce + dir_pierce))
    return pierce, is_ranged, int(w.get("hits") or 1)


def resolve_one_hit(roll: int, pierce: int, armor: int, mods=None) -> int:
    """Réduction d'UN coup tiré = **BASE COMMUNE** avec la prédiction : délègue à
    `apply_pierce_and_modifiers` (la fn par-valeur que la prédiction applique à ses bornes).
    Combat = même fn sur la valeur TIRÉE ⇒ dégâts identiques à la prédiction par construction."""
    return apply_pierce_and_modifiers(roll, pierce, armor, mods)


def attacker_modifiers(state: State, unit_id: int, hp: Optional[int], is_ranged: Optional[bool] = None):
    """`DamageModifiers` de l'attaquant depuis ses EFFETS actifs (None-safe). `is_ranged` = nature du coup
    (propagée aux bonus gated `IsRangedAttack`, ex. HeavyWeapon_ExtraDmg)."""
    active = (state.effects.active_effects(unit_id, {"hp": hp})
              if state.effects is not None else [])
    return build_attacker_modifiers_from_effects(active, is_ranged), active


def defender_modifiers(state: State, unit_id: int, hp: Optional[int]):
    """`DamageModifiers` de réduction du DÉFENSEUR (cible) depuis ses EFFETS actifs (symétrique attaquant ;
    `CalculateDefenderModifiersForPrediction`). Renvoie (mods, active_effects). None-safe (mods vide → no-op)."""
    active = (state.effects.active_effects(unit_id, {"hp": hp})
              if state.effects is not None else [])
    return build_defender_modifiers_from_effects(active), active


def normal_attack_per_hit_range(state: State, unit_id: int) -> Optional[dict]:
    """Plage BRUTE (pré-armure) d'UN coup d'attaque normale de l'unité, calculée depuis
    l'ECS (StatsComponent + effets actifs). Renvoie `{min, max, base, effects, hasMods}`
    ou None si l'unité n'a pas de StatsComponent (stats non chargées).

    `min/max` = ce que `HitDamage.GetDamage` tirera (avant réduction perçage/armure)."""
    e = state.get_entity(unit_id)
    sc = e.get_component(StatsComponent) if e is not None else None
    if sc is None:
        return None
    ctx = sc.ctx
    hc = e.get_component(HealthComponent) if e is not None else None
    hp = hc.hp if hc is not None else None
    active = (state.effects.active_effects(unit_id, {"hp": hp})
              if state.effects is not None else [])
    mods = build_attacker_modifiers_from_effects(active)
    # armure=0 & perçage=100 → réduction = identité ⇒ la plage retournée est BRUTE (pré-armure),
    # = ce que `aiPredict` (pré-armure) renvoie par coup ; les MODIFIERS d'effet sont inclus.
    res = get_attack_prediction(
        target_current_health=_BIG_HP, initial_damage=ctx.attack, hits=1,
        profile_type=ctx.damage_type, armor=0, pierce_pct=100, mods=mods)
    r = res.accurate_health_damage
    return {
        "min": r.min, "max": r.max, "base": ctx.attack,
        "effects": [getattr(ef, "name", None) for ef in active],
        "hasMods": bool(mods is not None and (mods.pct_list or getattr(mods, "additive", 0))),
    }
