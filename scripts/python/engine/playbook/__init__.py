"""Namespace `IdunBattle.AI.Playbook` — les playbooks par-ability (2ᵉ étage sous le scorer Utilities).

RE : docs/rl/playbook/architecture.md §2.2 + playbooks.md. Hiérarchie `BasePlaybook -> {ComparablePlaybook,
NonComparablePlaybook}`. Le générateur d'action (engine/ai) fait `LoadPlaybook(ability) -> Evaluate`.

- **Comparable** (attaques/soins) : `base.ComparablePlaybook` -> `common.py` (NormalAttack/Default/
  Heal/Repair). Prédiction déléguée à `prediction.py` (modèle objet : Scene + ability + services).
- **NonComparable** (summons/buffs/retraite) : package `noncomparable/` (1 module par playbook natif).
- **Triggered** (face ATTACK/MOVE, à clés-strings) : registres `psyker.TRIGGERED_ATTACK_PLAYBOOKS` /
  `adjacent_unit_preference.TRIGGERED_MOVE_PLAYBOOKS`, 1 module par playbook natif (`savior_protocols`…).
- Prédiction : `prediction.py` (à venir) = orchestration mince (MakeDamagePredictions) sur le modèle objet
  `engine/entities` + services `engine/services` + `ProbableDamageEvent`. Remplace `predict_validate` (PV).
"""
from __future__ import annotations

from .base import BasePlaybook, ComparablePlaybook, REGISTRY, register, get_playbook, tile_utility
from .probable_damage_event import (
    ProbableDamageEvent, calculate_utility_from_damage_event, calculate_utility_from_predictions,
    ProbableEffectEvent, calculate_utility_from_effect_event,
)
from .common import (
    NormalAttackPlaybook, NormalBossAttackPlaybook, HealPlaybook, RepairPlaybook,
    DefaultActiveAbilityPlaybook, DEFAULT_PLAYBOOK, NORMAL_ATTACK_PLAYBOOK, HEAL_PLAYBOOK,
    NORMAL_BOSS_ATTACK_PLAYBOOK, normal_attack_playbook,
)
from .savior_protocols import SaviorProtocolsPlaybook
from . import loki_custom  # noqa: F401  (#27) enregistre les overrides CalculateCustomUtility par-ability
from . import normal_attack_kill_gate  # noqa: F401  (#419-r1-tr14-r5-r2-r1-r1-r1) gate !WillNormalAttackKill x17
from . import resurrection_orb  # noqa: F401  (#289) 1009 -> route non-attaque (register_nonattack)
from . import plagueburst_mortar  # noqa: F401  (#302) 1169 -> route non-attaque, domaine TUILE
from . import daemonic_ordnance  # noqa: F401  (#302 tranche 3) 1148 -> meme route, domaine TUILE
from . import static_threshold_gate  # noqa: F401  (#419-r1-tr14-r5-r2-r1-r1-r1-r2) gate `utility > <static>` x10
from . import should_execute_gates  # noqa: F401  (#419-r1-tr14-r5-r2-r1-r1-r1) les 4 derniers corps propres portables
from . import spirit_leech  # noqa: F401  (#419-r1-tr14-r5-r2-r1-r1-r3) 1104 : lifesteal au rang natif
from . import might_from_below  # noqa: F401  (#970) 1165 : le terme CalculateCasterPositionUtility (+0x348)
from .noncomparable import (
    choose_action as nc_choose_action, is_noncomp, is_summon, playbook_for as nc_playbook_for
)
from .noncomparable._base import NCContext, NonComparablePlaybook
from .noncomparable.aberrant_hypermorph import AberrantHypermorphPlaybook
from .noncomparable.bloody_fury import BloodyFuryPlaybook
from .noncomparable.fighting_retreat import FightingRetreatPlaybook
from .noncomparable.vexilla_magnifica import VexillaMagnificaPlaybook


def get_playbook_or_default(ability_id: int) -> ComparablePlaybook:
    """Playbook Comparable porté pour `ability_id`, sinon le fallback DefaultActiveAbilityPlaybook.
    Reproduit `PlaybookDatabase.LoadPlaybook(...) ?? LoadDefaultActiveAbilityPlaybook(...)`."""
    return REGISTRY.get(ability_id) or DEFAULT_PLAYBOOK


__all__ = [
    "BasePlaybook", "ComparablePlaybook", "REGISTRY", "register", "get_playbook",
    "get_playbook_or_default", "tile_utility",
    "ProbableDamageEvent", "calculate_utility_from_damage_event", "calculate_utility_from_predictions",
    "ProbableEffectEvent", "calculate_utility_from_effect_event",
    "NormalAttackPlaybook", "NormalBossAttackPlaybook", "HealPlaybook", "RepairPlaybook",
    "DefaultActiveAbilityPlaybook", "normal_attack_playbook",
    "DEFAULT_PLAYBOOK", "NORMAL_ATTACK_PLAYBOOK", "NORMAL_BOSS_ATTACK_PLAYBOOK",
    "HEAL_PLAYBOOK", "SaviorProtocolsPlaybook",
    "NonComparablePlaybook", "NCContext", "nc_choose_action", "is_noncomp", "is_summon",
    "nc_playbook_for", "BloodyFuryPlaybook", "VexillaMagnificaPlaybook",
    "FightingRetreatPlaybook", "AberrantHypermorphPlaybook",
]
