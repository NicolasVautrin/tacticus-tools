"""Playbooks COMMUNS — Default / NormalAttack / Heal / Repair (RE docs/rl/playbook-engine.md §14.7).

DÉCOUVERTE CLÉ : ces 4 playbooks ne sont PAS des playbooks bespoke à clés-strings. Ce sont des
sous-classes MINCES de `ComparablePlaybook<T> → Playbook<T>` qui héritent du SCORER GÉNÉRIQUE partagé
`CalculateActionUtility` (= le §13.1) :

    score(action) = CustomUtility
                  + Σ CalculateUtilityFromPredictions   # dégât/soin/effet/repair × utilités composées
                                                          #   (Damage34 / Heal44 / Repair46 / AddedTileEffects45)
                  + base(UtilityAttackCase.Base, idx 54)
                  + CalculateUtilityFromTilePrediction   # positional/move (Tile 7, idx 8)

Le calcul prédiction→utilité est le PIPELINE PARTAGÉ (engine/utility.py + utilities/{damage,tile}.py),
PAS du code par-playbook. Un playbook commun n'override que : (a) le TAG d'ability (ctor), (b)
`ShouldExecute` (gate), (c) `CustomUtility` (constante), (d) le fournisseur de prédiction
(`Make{Damage,Heal,Repair}Predictions`). Aucune nouvelle clé de poids BC : ils consomment les utilités
composées déjà portées.

⚠ Soin/Repair : le MONTANT vient d'une prédiction non-dégât (Heal = `StatAmount(weapon)×max(hits,1)`
clampé HP-manquant → HealRatio ; Repair = prédiction idx 0x29). `aiPredict` est dégât-only → ces
montants sont BLOQUÉS (cf. §13.5). Les gates/tags/custom sont portés ; le scoring soin/repair s'activera
avec un RPC de prédiction complet.

Ids RE'd (constantes plates, pas de DAT) : NormalAttack tag 0x11(17) gate !triggered 0x48(72) custom +1 ;
Heal tag 0x12(18) ; Repair tag 0x1c(28) ; Default = flat 1.5 / cible éligible.
"""
from __future__ import annotations

from ..weights import Weights
from .base import Playbook, register


class NormalAttackPlaybook(Playbook):
    """NormalAttack (tag 17). Dégât = pipeline générique (Damage 34 = damage.py). +CustomUtility 1.
    Gate : l'unité n'a PAS la triggered ability 0x48(72) ET l'ability est dispo (timespan>0)."""
    ability_id = 0x11  # 17

    def should_execute(self, case: dict, wt: Weights) -> bool:
        c = case or {}
        if c.get("unit_has_triggered_72"):
            return False
        return bool(c.get("available", True))

    def custom_utility(self, case: dict, wt: Weights) -> float:
        return 1.0  # Fix64.FromInt(1)


class HealPlaybook(Playbook):
    """Heal (tag 18). Utilité soin = HealRatio × Heal(44) (pipeline générique). Gate : heal prédite >0,
    et un boss ne peut pas se soigner lui-même (peut soigner les autres). ⚠ montant soin BLOQUÉ
    (aiPredict dégât-only) — gate/tag portés, scoring s'active avec prédiction complète."""
    ability_id = 0x12  # 18

    def should_execute(self, case: dict, wt: Weights) -> bool:
        c = case or {}
        if not c.get("predicted_heal_gt0"):
            return False
        if c.get("target_is_boss") and c.get("target_is_caster"):
            return False
        return True


class RepairPlaybook(Playbook):
    """Repair (tag 28). Utilité = Repair(46) (pipeline générique, additif sans ×magnitude). Gate :
    ability off-cooldown (timespan>0) ; cibles = mécaniques endommagées (filtre amont). ⚠ montant
    repair BLOQUÉ (prédiction non-dégât idx 0x29) — gate/tag portés."""
    ability_id = 0x1c  # 28

    def should_execute(self, case: dict, wt: Weights) -> bool:
        return bool((case or {}).get("available", True))


class DefaultActiveAbilityPlaybook(Playbook):
    """Fallback générique (Common) pour toute ability sans playbook bespoke. ENTIÈREMENT porté :
    utilité PLATE 1.5 par cible éligible (aucune prédiction, aucun poids BC). Rend l'ability
    « utilisable, légèrement préférée » ; le ranking fin vient des couches au-dessus.
    N'est PAS enregistré sous un id (c'est le défaut, un par ability-id sans bespoke — voir get_playbook)."""
    ability_id = -1  # fallback (non enregistré dans REGISTRY)
    DEFAULT_UTILITY = 1.5  # Fix64.FromIntFraction(3,2)

    def attack_utility(self, case: dict, wt: Weights) -> float:
        """1.5 si la cible est éligible (case.eligible), sinon 0."""
        return self.DEFAULT_UTILITY if (case or {}).get("eligible") else 0.0


# Instance unique du fallback (utilisée par get_playbook_or_default).
DEFAULT_PLAYBOOK = DefaultActiveAbilityPlaybook()

register(NormalAttackPlaybook())
register(HealPlaybook())
register(RepairPlaybook())
