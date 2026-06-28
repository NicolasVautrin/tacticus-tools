"""Base scaffolding du subsystem Playbook + registry (RE docs/rl/playbook-engine.md §14.3/§14.5).

Hiérarchie native : `Playbook<T> → TriggeredAbilityPlaybook<T> → …NonOwnerPlaybook<T>`. Méthodes
`Calculate{Movement,Attack,Repair}UtilityInSteps` → `IEnumerable<Fix64>` qui yield **un seul Fix64**
(= utilité totale de l'ability pour ce case), sommé par le dispatcher. `GetUtilityValue(key)` =
`Dictionary<string,int>.TryGetValue` (défaut 0) → Fix64.

Ici on modélise un playbook comme un objet exposant `attack_utility`/`movement_utility`/`repair_utility`
qui rendent un `float` (on compare l'argmax, pas la valeur Fix64 bit-exacte — cf. doc §6). Le poids est
lu via `Weights.sub(dispatcher_category, key)` — les clés sont les littéraux résolus offline
(`playbook_keys.py`), qui vivent dans `Utilities.Default.{TriggeredAbilities|TriggeredAbilitiesNonOwner|
UnitSpecificBehaviours|ActiveAbilities}`.
"""
from __future__ import annotations

from ..weights import Weights

# Catégories BC où vivent les poids de playbook, par type de dispatcher (§14.6).
CAT_OWNER = "TriggeredAbilities"
CAT_NONOWNER = "TriggeredAbilitiesNonOwner"
CAT_UNITSPEC = "UnitSpecificBehaviours"
CAT_ACTIVE = "ActiveAbilities"


class Playbook:
    """Base : un playbook par-ability. Sous-classes overrident le gate + l'énumération + les clés.

    `ability_id` = l'AbilityType (clé du registry, = id posé par le ctor natif). `cat` = la catégorie BC
    du dispatcher (owner par défaut). Les 3 méthodes rendent un `float` (0 si gate non tenu / metadata
    absente = dégradation native). `case` = dict décrivant l'action candidate + l'état pertinent
    (contrat documenté par sous-classe) ; `wt` = poids BC chargés."""

    ability_id: int = -1
    cat: str = CAT_OWNER

    def w(self, wt: Weights, key: str) -> float:
        """Poids BC `Utilities.Default.<cat>.<key>` (défaut 0 = comportement natif GetUtilityValue)."""
        return wt.sub(self.cat, key)

    # --- Hooks du scorer générique (ComparablePlaybook<T>, §14.7) ---
    # Les playbooks COMMUNS (Default/NormalAttack/Heal/Repair) n'overrident que ces hooks ; le calcul
    # prédiction→utilité (dégât/soin/effet/repair × utilités composées Damage34/Heal44/Repair46/Tile7)
    # est le PIPELINE PARTAGÉ = engine/utility.py + utilities/{damage,tile}.py — PAS du code par-playbook.

    def should_execute(self, case: dict, wt: Weights) -> bool:
        """Gate `ShouldExecute` natif (ability éligible pour ce case). Défaut : True."""
        return True

    def custom_utility(self, case: dict, wt: Weights) -> float:
        """`CalculateCustomUtility` natif (constante ajoutée au score d'action). Défaut : 0
        (NonComparable/ComparablePlaybook base) ; certains playbooks rendent une constante."""
        return 0.0

    # --- Chaîne PRÉDICTION→UTILITÉ (ComparablePlaybook, RE §14.7 + comparable_playbook.py) ---
    def make_damage_predictions(self, caster, target, ability,
                                reduction_min: int = 0, reduction_max: int = 0):
        """Playbook.MakeDamagePredictions : prédictions de dégât pour (caster→target) via l'ability.
        Base = GenerateMultiHitAttackPredictions ; les playbooks à dégât bespoke overrident."""
        from .comparable_playbook import generate_multi_hit_attack_predictions
        return generate_multi_hit_attack_predictions(
            caster, target, ability, reduction_min, reduction_max)

    def calculate_action_utility(self, caster, target, ability, wt: Weights,
                                 case: dict | None = None,
                                 target_max_health: int | None = None) -> float:
        """ComparablePlaybook.CalculateActionUtility = CustomUtility + Σ des prédictions de dégât
        (CalculateUtilityFromPredictions). (Soin/effet/position/tile = couches additionnelles à
        câbler ensuite ; ici = terme dégât + custom, le cœur attaque.)"""
        from .comparable_playbook import calculate_utility_from_predictions
        events = self.make_damage_predictions(caster, target, ability)
        return (self.custom_utility(case or {}, wt)
                + calculate_utility_from_predictions(events, wt, target_max_health))

    # --- Termes par-ability bespoke (string-keyed), pour les playbooks type SaviorProtocols ---
    def attack_utility(self, case: dict, wt: Weights) -> float:
        return 0.0

    def movement_utility(self, case: dict, wt: Weights) -> float:
        return 0.0

    def repair_utility(self, case: dict, wt: Weights) -> float:
        return 0.0


# Registry AbilityType id -> instance Playbook (§14.2 : 351 registrations natives ; port incrémental).
# On enregistre au fur et à mesure les playbooks portés ; les ids absents = pas encore portés (→ 0).
REGISTRY: dict[int, Playbook] = {}


def register(pb: Playbook) -> Playbook:
    REGISTRY[pb.ability_id] = pb
    return pb


def get_playbook(ability_id: int) -> Playbook | None:
    return REGISTRY.get(ability_id)
