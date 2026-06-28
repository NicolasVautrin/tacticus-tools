"""Port FIDÈLE de `IdunBattle.AI.Playbook.ComparablePlaybook<T>` — couche PRÉDICTION→UTILITÉ.

Chaîne native (RE @181409da0 / AncestralFortunePlaybook.MakeDamagePredictions @18111b070) :

  Playbook.MakeDamagePredictions(caster, casterPos, target)
    damage  = ability.GetDamage()            ┐ getters de l'ability (engine.entities.abilities)
    hits    = ability.GetHits()              ├─ (config gameconfig / capture pour l'attaque normale)
    profile = ability.GetDamageProfile()     ┘
    → GenerateMultiHitAttackPredictions(caster, casterPos, target, damage, hits, profile)
        pour chaque membre/coup probable de la cible :
          pred = DamagePredictionQuery.GetAttackPrediction(caster, pos, member, ability,
                                                           damage, hits, profile, …)
          events.Add(ProbableDamageEvent(member, pred, probability))
    → CalculateUtilityFromPredictions = Σ CalculateUtilityFromDamageEvent(event) × probability

`CalculateUtilityFromDamageEvent` consomme la prédiction via le composite Damage(34) déjà porté
(engine/utilities/damage.py : DamageDealt 80/20 + KillUnit + OverkillUnit, devise native ~[0,250]).

⚠ Multi-membres (Blast) : `number_of_members` cible = nb de prédictions (axe d'amélioration b ;
ici 1 membre par défaut = cas mono-membre validé). Probabilité = 1.0 (poids param_10 natif à raffiner).
"""
from __future__ import annotations

from ..entities.unit_context import UnitContext
from ..entities.abilities.active_ability import AActiveAbility, _PROFILE_BY_INDEX
from ..services.damage_prediction import get_attack_prediction
from ..utilities.damage import damage_composite
from ..weights import Weights
from .probable_damage_event import ProbableDamageEvent

# Profil nom → index DamageProfileType (inverse de _PROFILE_BY_INDEX).
_PROFILE_INDEX = {name: idx for idx, name in _PROFILE_BY_INDEX.items()}


def generate_multi_hit_attack_predictions(
        caster: UnitContext, target: UnitContext, ability: AActiveAbility,
        target_reduction_min: int = 0, target_reduction_max: int = 0) -> list[ProbableDamageEvent]:
    """ComparablePlaybook.GenerateMultiHitAttackPredictions (@181409da0) — version mono-membre
    (Blast = axe b). `damage/hits/profile` viennent des getters de l'ability."""
    initial_damage = ability.get_damage()          # base PAR COUP (= stat Attack pour l'attaque normale)
    hits = ability.get_hits()                       # hits de l'ARME (+ ExtraHits)
    profile_name = ability.get_damage_profile()
    profile_idx = _PROFILE_INDEX.get(profile_name, 0)
    mods = caster.attacker_modifiers()              # DamageModifiers (effets actifs du caster §17.8 ; vide=no-op)
    pred = get_attack_prediction(
        target_current_health=target.health, initial_damage=initial_damage, hits=hits,
        profile_type=profile_idx,
        pierce_pct=ability.get_pierce(),            # GetAttackPiercingDamageRatio (profil + ExtraPierce)
        armor=target.fixed_armor,                   # armure CIBLE (GetDamageWithPiercing par bout)
        reduction_min=target_reduction_min, reduction_max=target_reduction_max,
        mods=mods)                                  # ×bonus post-perçage PAR BOUT (§17.7)
    return [ProbableDamageEvent(target=target, prediction=pred, probability=1.0)]


def calculate_utility_from_damage_event(event: ProbableDamageEvent, wt: Weights,
                                        target_max_health: int | None = None) -> float:
    """Playbook.CalculateUtilityFromDamageEvent — score d'UN event via le composite Damage(34).
    Bridge prédiction→dict consommé par engine/utilities/damage.py. × probability."""
    p = event.prediction
    pred_dict = {
        "hpBefore": p.current_health, "shieldBefore": p.shield,
        "healthDmgMin": p.accurate_health_damage.min,
        "healthDmgMax": p.accurate_health_damage.max,
        "kill": p.accurate_health_damage.max >= p.current_health,
        "killSure": p.accurate_health_damage.min >= p.current_health,
    }
    max_hp = target_max_health if target_max_health else p.current_health
    return damage_composite(pred_dict, max_hp, wt) * event.probability


def calculate_utility_from_predictions(events: list[ProbableDamageEvent], wt: Weights,
                                       target_max_health: int | None = None) -> float:
    """ComparablePlaybook.CalculateUtilityFromPredictions = Σ des events (le terme dégât du score)."""
    return sum(calculate_utility_from_damage_event(e, wt, target_max_health) for e in events)
