"""Prediction de degat — orchestration MINCE du playbook (`IdunBattle.AI.Playbook`, RE gqfc5mff6c).

Stratification native (RE) : le PLAYBOOK est mince (enumere cibles, wrap en `ProbableDamageEvent`) ; toute
la mecanique de degat vit dans l'ABILITY (`<Ability>.PredictAttack`, slot +0x21 / per-target +0x27) et les
SERVICES (`BattleQuery` selection d'arme, `DamagePrediction` percage/get_attack_prediction, `DamageCalculations`
defenseur/elevation/bouclier). Ce module porte la couche playbook + assemble la chaine sur le modele objet
(`Scene` + `UnitContext` + `AActiveAbility` + `ProbableDamageEvent`). Remplace le monolithe `predict_validate`
(PV) : MEME calcul (valide), forme objet.

  - `make_normal_attack_predictions` = `ALoki_NormalAttackPlaybook.MakeDamagePredictions @181372730`
    (mono-cible : `ability.PredictAttack @1811afa50` -> 1 `ProbableDamageEvent`).
  - `generate_multi_hit_attack_prediction` = per-cible de `GenerateMultiHitAttackPredictions @181409da0`.
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
                      RANGED_IN_MELEE_PCT)
from .normal_attack import (make_normal_attack_predictions, get_additional_damage_prediction,
                            get_klaw_attack1_prediction)
from .abilities import (generate_multi_hit_attack_prediction, make_damage_predictions,
                        make_hammer_wrath_events)

__all__ = [
    "make_normal_attack_predictions", "make_damage_predictions",
    "generate_multi_hit_attack_prediction", "make_hammer_wrath_events",
    "get_additional_damage_prediction", "get_klaw_attack1_prediction",
    "defender_prediction_block_amount", "_add_positional_and_defender_mods",
    "_apply_ally_attack_dmg_bonus", "_target_damage_limits", "_PROFILE_INDEX", "RANGED_IN_MELEE_PCT",
]
