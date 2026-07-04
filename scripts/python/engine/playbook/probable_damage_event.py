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


# ── POSE D'EFFET (branche effet de `CalculateUtilityFromPredictions @181407890`) ─────────────────────
# La fonction native somme QUATRE familles de prédictions via 4 slots vtable : dégât (+0x358), soin
# (+0x368/378), EFFET (+0x388=MakeEffectPredictions), repair (dict). La branche effet (LAB_181407fe0) :
#   pour chaque event {target@0, effectType@1, probability@2} : ForEffect(case, caster, target, effectType)
#   -> AddedEffectUtility (UtilityType 0x2d=45=AddedTileEffects) -> Fix64.op_Multiply(event.probability, U).
# FIDÉLITÉ DE BUILD (gqfc5mff6c) : le SEUL override de MakeEffectPredictions est `SpiritLeechPlaybook`
# @18115d690 (les autres héritent de la base VIDE @18140a930). SpiritLeech pose l'effet 0x429=1065="Pinned",
# ABSENT de la catégorie BC AddedTileEffects (qui ne pondère que Fire/Ice/SpiderWeb) -> son terme effet = 0.
# => ce chemin est structurellement présent mais NUMÉRIQUEMENT INERTE dans ce build. On le porte pour la
# complétude/fidélité (mirror du fold natif) ; il redevient actif dès qu'une BC pondère l'effet posé.
@dataclass
class ProbableEffectEvent:
    """`IdunBattle.AI.Playbook.ProbableEffectEvent` (`.ctor @181135820`). Event porteur d'une POSE D'EFFET
    probable sur une cible. Ctor natif `(target, effectType, probability:Nullable<Fix64>=1.0, _)` ; struct
    lue dans `CalculateUtilityFromPredictions` : target@0 · effectType@1 · probability@2.

    `effect_name` = `Enum.ToString(effectType)` (ex. 0x429 → "Pinned"), la clé de poids AddedTileEffects.
    `friendly` = cible ALLIÉE du caster (`UnitExtensions.IsFriend`) → terme préfixé négé (AddedEffectUtility).
    `target_has_effect` = la cible a DÉJÀ l'effet (`EntityExtensions.HasEffect`) → U=0 (mais SpiritLeech gate
    déjà en amont : pas d'event si HasEffect ; on garde le champ pour rester fidèle au check d'AddedEffectUtility)."""
    target: int
    effect_name: str
    effect_type: int = 0                 # EffectType natif (ex. 0x429=1065), pour référence/trace
    probability: float = 1.0
    friendly: bool = False
    target_has_effect: bool = False


def calculate_utility_from_effect_event(event: ProbableEffectEvent, wt) -> float:
    """Branche effet de `CalculateUtilityFromPredictions @181407890` (LAB_181407fe0) :
    `probability × ForEffect→AddedEffectUtility(name, has_effect, is_friend, weights[AddedTileEffects=45])`.
    Poids = catégorie BC `Utilities.Default.AddedTileEffects` (Fire/Ice/SpiderWeb + `Unit_on_*`)."""
    from ..utilities.effect import ADDED_EFFECT_UTILITY
    weights = wt.category("AddedTileEffects")
    u = ADDED_EFFECT_UTILITY.evaluate(event.effect_name, event.target_has_effect, event.friendly, weights)
    return event.probability * u
