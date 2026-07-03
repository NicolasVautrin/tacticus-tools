"""Port FIDÈLE de `IdunBattle.AI.Playbook.ProbableDamageEvent` (.ctor `@181135500`, RE'd dans
`GenerateMultiHitAttackPredictions @181409da0`). Le playbook génère une LISTE de ces events (un par
cible/membre probable), chacun pondéré par DEUX probabilités, puis somme
`CalculateUtilityFromDamageEvent(event) @1814a9f90 = prob1 × prob2 × weight(ForDamagePrediction(prediction))`.

Structure native (offsets lus @181135500, struct 0xD8) :
  Target@0x00 · Prediction:DamagePredictionResult@0x08 (0xC0) · probability1:Fix64@0xC8 · probability2:Fix64@0xD0.
Les 2 probabilités sont des `Nullable<Fix64>` valant 1.0 par défaut :
  - probability1 = poids du BATCH (AoE secondaire = `Fix64.FromIntFraction(maxSecondary, actualCount)`
    dans `<Ability>Playbook.MakeDamagePredictions` ; 1.0 pour la cible primaire) ;
  - probability2 = poids PAR CIBLE (délégué `param_10` du GMHAP ; 1.0 sinon).
"""
from __future__ import annotations

from dataclasses import dataclass

from ..services.damage_prediction import DamagePredictionResult


@dataclass
class ProbableDamageEvent:
    """Événement de dégât probable : cible + `DamagePredictionResult` + 2 poids de proba (défaut 1.0).

    `target` = id de la cible (int). `friendly` = event de dégât sur un ALLIÉ/self (coût en PV d'une
    ability, ex. DakkaDakkaDakka) → utilité NÉGÉE (`DamageUtility @1810e2280` : friendly-fire negated)."""
    target: int
    prediction: DamagePredictionResult
    probability1: float = 1.0
    probability2: float = 1.0
    friendly: bool = False

    @property
    def probability(self) -> float:
        """`Fix64.Multiply(prob1, prob2)` — le poids total consommé par l'utilité."""
        return self.probability1 * self.probability2

    def composite_fields(self) -> dict:
        """Champs consommés par le composite Damage (`UtilityAttackCase.ForDamagePrediction @181104fb0`
        → poids `Utilities` case 0x22) : santé min/max (cap PV), split bouclier (AccurateShieldDamage@0x78),
        kill/killSure. Mirror de la lecture native des bornes depuis le `DamagePredictionResult`
        (= l'ancien `predict_validate._event_from_dp`)."""
        dp = self.prediction
        r = dp.accurate_health_damage
        s = dp.accurate_shield_damage
        hp = dp.current_health
        return {"hpBefore": hp, "shieldBefore": dp.shield,
                "healthDmgMin": min(r.min, hp), "healthDmgMax": min(r.max, hp),
                "shieldDmgMin": s.min, "shieldDmgMax": s.max,
                "limitedByMinHp": dp.limited_by_min_hp, "appliedHits": dp.applied_hits,
                "kill": r.max >= hp, "killSure": r.min >= hp}


def calculate_utility_from_damage_event(event: ProbableDamageEvent, wt, target_max_hp: int | None = None) -> float:
    """`Playbook.CalculateUtilityFromDamageEvent @1814a9f90` = `prob1 × prob2 × weight` où
    `weight = ForDamagePrediction(prediction)` = le composite Damage (`engine.utilities.damage_composite`,
    case 0x22). Event FRIENDLY → utilité NÉGÉE (`DamageUtility` : friendly-fire negated)."""
    from ..utilities import damage_composite
    sign = -1.0 if event.friendly else 1.0
    return sign * event.probability * damage_composite(event.composite_fields(), target_max_hp, wt)


def calculate_utility_from_predictions(events: list[ProbableDamageEvent], wt,
                                       target_max_hp_by_id: dict | None = None) -> float:
    """`ComparablePlaybook.CalculateUtilityFromPredictions @181407890` (terme dégât) = `Σ` des events.
    `target_max_hp_by_id` = {target_id: maxHP} (combinedMax du composite). Défaut None → cible pleine."""
    m = target_max_hp_by_id or {}
    return sum(calculate_utility_from_damage_event(e, wt, m.get(e.target)) for e in events)
