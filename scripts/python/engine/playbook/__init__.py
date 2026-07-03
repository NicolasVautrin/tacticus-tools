"""Namespace `IdunBattle.AI.Playbook` — les playbooks par-ability (2ᵉ étage sous le scorer Utilities).

RE : docs/rl/playbook/architecture.md §2.2 + playbooks.md. Hiérarchie `BasePlaybook -> {ComparablePlaybook,
NonComparablePlaybook}`. Le générateur d'action (engine/ai) fait `LoadPlaybook(ability) -> Evaluate`.

- **Comparable** (attaques/soins) : `base.ComparablePlaybook` -> `common.py` (NormalAttack/Default/
  Heal/Repair). Prédiction déléguée à `prediction.py` (modèle objet : Scene + ability + services).
- **NonComparable** (summons/buffs/retraite) : `noncomparable.py` (heuristique entière par feuille).
- **Bespoke** (SaviorProtocols, à clés-strings) : dormant, référence RE.
- Prédiction : `prediction.py` (à venir) = orchestration mince (MakeDamagePredictions) sur le modèle objet
  `engine/entities` + services `engine/services` + `ProbableDamageEvent`. Remplace `predict_validate` (PV).
"""
from __future__ import annotations

from .base import BasePlaybook, ComparablePlaybook, REGISTRY, register, get_playbook, tile_utility
from .probable_damage_event import (
    ProbableDamageEvent, calculate_utility_from_damage_event, calculate_utility_from_predictions,
)
from .common import (
    NormalAttackPlaybook, HealPlaybook, RepairPlaybook,
    DefaultActiveAbilityPlaybook, DEFAULT_PLAYBOOK, NORMAL_ATTACK_PLAYBOOK, HEAL_PLAYBOOK,
)
from .savior_protocols import SaviorProtocolsPlaybook
from .noncomparable import (
    NonComparablePlaybook, NCContext, choose_action as nc_choose_action,
    is_noncomp, is_summon, playbook_for as nc_playbook_for,
    BloodyFuryPlaybook, VexillaMagnificaPlaybook,
    FightingRetreatPlaybook, AberrantHypermorphPlaybook,
)


def get_playbook_or_default(ability_id: int) -> ComparablePlaybook:
    """Playbook Comparable porté pour `ability_id`, sinon le fallback DefaultActiveAbilityPlaybook.
    Reproduit `PlaybookDatabase.LoadPlaybook(...) ?? LoadDefaultActiveAbilityPlaybook(...)`."""
    return REGISTRY.get(ability_id) or DEFAULT_PLAYBOOK


__all__ = [
    "BasePlaybook", "ComparablePlaybook", "REGISTRY", "register", "get_playbook",
    "get_playbook_or_default", "tile_utility",
    "ProbableDamageEvent", "calculate_utility_from_damage_event", "calculate_utility_from_predictions",
    "NormalAttackPlaybook", "HealPlaybook", "RepairPlaybook", "DefaultActiveAbilityPlaybook",
    "DEFAULT_PLAYBOOK", "NORMAL_ATTACK_PLAYBOOK", "HEAL_PLAYBOOK", "SaviorProtocolsPlaybook",
    "NonComparablePlaybook", "NCContext", "nc_choose_action", "is_noncomp", "is_summon",
    "nc_playbook_for", "BloodyFuryPlaybook", "VexillaMagnificaPlaybook",
    "FightingRetreatPlaybook", "AberrantHypermorphPlaybook",
]
