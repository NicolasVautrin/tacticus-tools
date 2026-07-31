"""Prediction de degat — orchestration MINCE du playbook (`IdunBattle.AI.Playbook`, RE gqfc5mff6c).

Stratification native (RE) : le PLAYBOOK est mince (enumere cibles, wrap en `ProbableDamageEvent`) ; toute
la mecanique de degat vit dans l'ABILITY (`<Ability>.PredictAttack`, slot +0x21 / per-target +0x27) et les
SERVICES (`BattleQuery` selection d'arme, `DamagePrediction` percage/get_attack_prediction, `DamageCalculations`
defenseur/elevation/bouclier). Ce module porte la couche playbook + assemble la chaine sur le modele objet
(`Scene` + `UnitContext` + `AActiveAbility` + `ProbableDamageEvent`). Remplace le monolithe `predict_validate`
(PV) : MEME calcul (valide), forme objet.

  - `make_normal_attack_predictions` = `IdunBattle.AI.Playbook.Loki.ALoki_NormalAttackPlaybooku003C__Il2CppFullySharedGenericTypeu003E$$MakeDamagePredictions`
    (mono-cible : `IdunBattleLogic.Entities.Abilities.Active.Loki.ALoki_NormalAttackAbility$$PredictAttack` -> 1 `ProbableDamageEvent`).
  - `generate_multi_hit_attack_prediction` = per-cible de `IdunBattle.AI.Playbook.ComparablePlaybooku003C__Il2CppFullySharedGenericTypeu003E$$GenerateMultiHitAttackPredictions`.
  - `make_damage_predictions` = `<Ability>Playbook.MakeDamagePredictions` (liste : cible + AoE + self).

DECOUPAGE EN PACKAGE (module >1000 lignes scinde par couche ; ré-export ci-dessous pour que les call-sites
`prediction.make_*` / `from .prediction import <helper>` restent inchanges) :
- `_shared`      : bloc d'imports commun, constantes (`_PROFILE_INDEX`, `RANGED_IN_MELEE_PCT`) et les 6
                   helpers d'assemblage des modifiers (positionnels + defenseur + auras).
- `normal_attack`: `make_normal_attack_predictions` + base display `_display_attack_base` + drone MV71 +
                   follow-ups de boss (get_additional / get_klaw).
- `abilities`    : `generate_multi_hit_attack_prediction` + registre per-ability + `make_damage_predictions`
                   + HammerOfWrath. C'est ICI que grossit le port case-220 (handlers `_<ability>_inputs`).
"""
from __future__ import annotations

from ._shared import (defender_prediction_block_amount, _add_positional_and_defender_mods,
                      _apply_ally_attack_dmg_bonus, _target_damage_limits, _PROFILE_INDEX,
                      RANGED_IN_MELEE_PCT, prediction_has_moved, prediction_has_teleported,
                      prediction_tiles_moved_this_turn, _entity_traits)
from .normal_attack import (make_normal_attack_predictions, get_additional_damage_prediction,
                            get_klaw_attack1_prediction)
from .abilities import (generate_multi_hit_attack_prediction, make_damage_predictions,
                        make_hammer_wrath_events, make_secondary_multihit_event)

__all__ = [
    "make_normal_attack_predictions", "make_damage_predictions",
    "generate_multi_hit_attack_prediction", "make_hammer_wrath_events",
    # Event SECONDAIRE (`minDmg` seul x `nrOfHits_2`, sur la CIBLE PRINCIPALE) — call-site natif
    # IDENTIQUE dans les DEUX faces de Stikkbomb 1051 (`MakeDamagePredictions` cote ennemis,
    # `CalculateCustomUtility` cote amis) ET dans `PlasmaGrenadePlaybook$$CalculateCustomUtility`
    # (1098, cote ennemis). Cf. #27 verrou 4.
    "make_secondary_multihit_event",
    "get_additional_damage_prediction", "get_klaw_attack1_prediction",
    "defender_prediction_block_amount", "_add_positional_and_defender_mods",
    "_apply_ally_attack_dmg_bonus", "_target_damage_limits", "_PROFILE_INDEX", "RANGED_IN_MELEE_PCT",
    "prediction_has_moved", "prediction_has_teleported",
    # case-322 : `TilesMovedThisTurn(Self)` vu par la prediction (compteur reel + pas SIMULE) —
    # l'entree de `att_ctx["tiles_moved_this_turn"]` que lit `ModifiedExoarmour_ExtraDmg`.
    "prediction_tiles_moved_this_turn",
    # #267-r1 : FOYER unique du substrat de traits de la face PREDICTION (pendant de
    # `runner.damage_model.target_trait_names`) — consomme aussi par `playbook/fury_of_the_ancients.py`
    # et `playbook/psyker.py`, qui appellent le meme `get_attack_prediction`.
    "_entity_traits",
]
