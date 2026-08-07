"""`IdunBattle.Core.Services.BattleQuery$$GetMultiHitAttackPrediction` monte depuis l'ECS `State`.

FOYER UNIQUE, et il a DEUX consommateurs -- c'est pourquoi il vit dans son propre module plutot
que dans celui de l'un d'eux :

  * `operations/damage_prediction_sort.py` -- `SortTargetsByDamagePredictionSelector$$Select`, qui
    l'appelle TROIS fois par cible (min / avg / max) ;
  * `operations/damage_utility.py` -- `SortUnitsByDamageUtilitySelector$$Select`, dont la boucle
    `foreach u` appelle `IBattleQuery` slot `0x26`
    (`GetAttackPrediction(owner, u, ownerPosition, ability, () => damage, () => hits,
    damageProfile: null, defenderInitialHealth: null, previousHitsPrediction: default, null, null)`).

Le natif n'a qu'UNE chaine de prediction : `BattleQuery$$GetAttackPrediction` ->
`DamagePredictionQuery$$GetAttackPrediction` (memset 0xb8 de l'`AttackPredictionRequest` puis slot 5
= `DamagePrediction$$PredictAttack`) -> `DamagePrediction$$PredictAttackRaw`. Le port aussi : les
entrees PAR CIBLE sont assemblees ici avec les MEMES primitives publiques que l'EXECUTION
(`attacker_modifiers` famille ATTACK, les feuilles POSITIONNELLES elevation/trench,
`defender_fixed_armor`, `defender_modifiers`), puis le calcul passe par le foyer unique
`services/damage_prediction`.

⚠ `might_crit` n'est PAS alimente (aucun `attacker_ctx` n'est passe) : c'est un fait MESURE cote
selecteur d'utilite (#419-r6-r1, `test_419r6r1_face_decision_live.py`), pas un oubli.
"""
from __future__ import annotations

from typing import Optional

from ...entities.damage_profile_type import DamageProfileType
from ...services.damage_prediction import get_attack_prediction
from ..components import HealthComponent, StatsComponent
from ..damage_model import (attacker_modifiers, defender_modifiers, defender_fixed_armor,
                            apply_elevation_bonus, apply_trench_reduction, target_trait_names)


def multi_hit_attack_prediction(state, attacker_id: int, target_id: int, amount: int, hits: int,
                                damage_profile: str, pierce: int, is_melee: bool = False,
                                ability_type: Optional[int] = None,
                                is_normal_attack: bool = False):
    """`IdunBattle.Core.Services.BattleQuery$$GetMultiHitAttackPrediction(attacker, target,
    attackerPosition, ability, damage, damageProfile, hits)` monte depuis le `State` runner.

    Les entrees PAR CIBLE sont assemblees avec les MEMES primitives publiques que l'EXECUTION
    (`damage_ops/ability.execute_ability_attack`) -- `attacker_modifiers` (famille ATTACK : nature du
    coup, traits de la cible, profil et ability declenchante threades), les feuilles POSITIONNELLES
    (elevation / trench), `defender_fixed_armor` et `defender_modifiers` -- puis le calcul lui-meme
    passe par le foyer unique `services/damage_prediction`. Ce n'est donc PAS un fork du calcul : le
    natif a lui aussi DEUX chemins (prediction / execution) qui partagent `$$PredictAttackRaw`.

    `is_normal_attack` = l'attaque predite est l'ATTAQUE NORMALE du caster (le cas ou le noeud
    `+0x28` du selecteur de tri est nul et ou le natif retombe sur
    `UnitExtensions$$GetNormalAttackType(owner)`) : les gates d'effet qui distinguent les deux
    familles le lisent.

    Rend `None` quand la cible n'a pas de `HealthComponent` (rien a predire)."""
    att = state.get_entity(attacker_id)
    tgt = state.get_entity(target_id)
    thc = tgt.get_component(HealthComponent) if tgt is not None else None
    if thc is None:
        return None
    asc = att.get_component(StatsComponent) if att is not None else None
    ahc = att.get_component(HealthComponent) if att is not None else None
    _ranged = (not is_melee) if is_melee is not None else None
    if asc is None:
        from ...services.damage_modifiers import DamageModifiers   # differe PORTEUR : cycle services<->runner
        mods, active = DamageModifiers(), []
    else:
        mods, active = attacker_modifiers(state, attacker_id, ahc.hp if ahc else None,
                                          target_id=target_id, is_ranged=_ranged,
                                          is_normal_attack=is_normal_attack,
                                          target_traits=target_trait_names(state, target_id),
                                          damage_profile=damage_profile,
                                          trigger_ability_type=ability_type)
    apply_elevation_bonus(state, mods, attacker_id, target_id)
    apply_trench_reduction(state, mods, attacker_id, target_id, damage_profile)
    armor = defender_fixed_armor(state, target_id)
    def_mods, _da = defender_modifiers(state, target_id, thc.hp, is_melee=is_melee,
                                       damage_profile=damage_profile, attacker_id=attacker_id,
                                       is_normal_attack=is_normal_attack)
    # Differe PORTEUR : `operations.damage` importe `damage_ops`, qui importe ce paquet -> hisser
    # fermerait le cycle (meme raison, ecrite, que le `from ..damage import AttackDamageOperation`
    # de `damage_ops/ability.py`).
    from .damage import AttackDamageOperation
    AttackDamageOperation._apply_defender_flat_reductions(mods, def_mods)
    return get_attack_prediction(
        target_current_health=int(thc.hp or 0), initial_damage=int(amount), hits=int(hits),
        profile_type=int(DamageProfileType[damage_profile]), armor=armor, pierce_pct=int(pierce),
        mods=mods, attacker_effects=active)
