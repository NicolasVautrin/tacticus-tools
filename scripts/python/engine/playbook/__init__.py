"""Subsystem Playbook (port Python) — 2ᵉ étage de l'IA sous le scorer Utilities.

RE : docs/rl/playbook-engine.md §14. Deux familles :
- COMMUNS (Default/NormalAttack/Heal/Repair, §14.7) = sous-classes MINCES du scorer générique partagé
  `ComparablePlaybook<T>.CalculateActionUtility` (= §13.1) ; n'overrident que tag + ShouldExecute +
  CustomUtility + fournisseur de prédiction. Le scoring prédiction→utilité est le pipeline partagé
  (engine/utility.py + utilities/{damage,tile}.py), pas du code par-playbook.
- BESPOKE (ex. SaviorProtocols, Loki.*, §14.4) = ajoutent des termes positionnels à CLÉS-STRINGS BC
  (`Calculate*UtilityInSteps` + GetUtilityValue), résolues offline via `playbook_keys.py`.

Le natif rend UN Fix64 par (ability, case), sommé par le dispatcher Tile (leaves TriggeredAbilities 2 /
NonOwner 4 / UnitSpecificBehaviours 3, §13.14). DORMANT comme les tile-leaves : chaque playbook lit un
`case`/`ctx` documenté et rend 0 / False quand la metadata n'est pas plombée.
"""
from __future__ import annotations

from .base import Playbook, REGISTRY, get_playbook
from .probable_damage_event import ProbableDamageEvent
from .comparable_playbook import (
    generate_multi_hit_attack_predictions,
    calculate_utility_from_damage_event,
    calculate_utility_from_predictions,
)
from .common import (
    NormalAttackPlaybook, HealPlaybook, RepairPlaybook,
    DefaultActiveAbilityPlaybook, DEFAULT_PLAYBOOK,
)
from .savior_protocols import SaviorProtocolsPlaybook


def get_playbook_or_default(ability_id: int) -> Playbook:
    """Playbook porté pour `ability_id`, sinon le fallback DefaultActiveAbilityPlaybook (flat 1.5).
    Reproduit `PlaybookDatabase.LoadPlaybook(...) ?? LoadDefaultActiveAbilityPlaybook(...)`."""
    return REGISTRY.get(ability_id) or DEFAULT_PLAYBOOK


__all__ = [
    "Playbook", "REGISTRY", "get_playbook", "get_playbook_or_default",
    "ProbableDamageEvent", "generate_multi_hit_attack_predictions",
    "calculate_utility_from_damage_event", "calculate_utility_from_predictions",
    "NormalAttackPlaybook", "HealPlaybook", "RepairPlaybook",
    "DefaultActiveAbilityPlaybook", "DEFAULT_PLAYBOOK", "SaviorProtocolsPlaybook",
]
