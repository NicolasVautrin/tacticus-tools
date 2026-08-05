"""Port FIDÈLE de `IdunBattle.AI.Playbook.ProbableDamageEvent` (.IdunBattle.AI.Playbook.ProbableDamageEvent$$.ctor`, RE'd dans
`IdunBattle.AI.Playbook.ComparablePlaybooku003C__Il2CppFullySharedGenericTypeu003E$$GenerateMultiHitAttackPredictions`). Le playbook génère une LISTE de ces events (un par
cible/membre probable), chacun pondéré par DEUX probabilités, puis somme
`IdunBattle.AI.Playbook.Playbooku003C__Il2CppFullySharedGenericTypeu003E$$CalculateUtilityFromDamageEvent(event) = prob1 × prob2 × weight(ForDamagePrediction(prediction))`.

Structure native (offsets lus IdunBattle.AI.Playbook.ProbableDamageEvent$$.ctor, struct 0xD8) :
  Target@0x00 · Prediction:DamagePredictionResult@0x08 (0xC0) · probability1:Fix64@0xC8 · probability2:Fix64@0xD0.
Les 2 probabilités sont des `Nullable<Fix64>` valant 1.0 par défaut :
  - probability1 = poids du BATCH (AoE secondaire = `Fix64.FromIntFraction(maxSecondary, actualCount)`
    dans `<Ability>Playbook.MakeDamagePredictions` ; 1.0 pour la cible primaire) ;
  - probability2 = poids PAR CIBLE (délégué `param_10` du GMHAP ; 1.0 sinon).
"""
from __future__ import annotations

from dataclasses import dataclass

from ..services.damage_prediction import DamagePredictionResult
from ..utilities import damage_composite
from ..utilities.effect import ADDED_EFFECT_UTILITY


@dataclass
class ProbableDamageEvent:
    """Événement de dégât probable : cible + `DamagePredictionResult` + 2 poids de proba (défaut 1.0).

    `target` = id de la cible (int). `friendly` = event de dégât sur un ALLIÉ/self (coût en PV d'une
    ability, ex. DakkaDakkaDakka) → utilité NÉGÉE (`DamageUtility IdunBattle.AI.Utilities.DamageUtility.u003CEvaluateAttackInStepsu003Ed__2$$MoveNext` : friendly-fire negated)."""
    target: int
    prediction: DamagePredictionResult
    probability1: float = 1.0
    probability2: float = 1.0
    friendly: bool = False
    # #419-r1-tr9 : santé/bouclier de l'ENTITÉ `target`, quand ils ne sont PAS ceux de la cible de
    # `prediction`. `DamageUtility` (leaf 36) lit `GetStat(case.Target, Health, Max|Current)` et
    # `DamageUtility$$GetShield(case.Target)`, jamais le `DamagePredictionResult` — cf.
    # `engine/utilities/damage.py::DamageUtility.evaluate`. `None` (défaut) = les deux cibles
    # coïncident, on garde le proxy `hpBefore`/`shieldBefore` de la prédiction.
    target_hp: int | None = None
    target_shield: int | None = None

    @property
    def probability(self) -> float:
        """`Fix64.Multiply(prob1, prob2)` — le poids total consommé par l'utilité."""
        return self.probability1 * self.probability2

    def composite_fields(self) -> dict:
        """Champs consommés par le composite Damage (`IdunBattle.AI.Utilities.UtilityAttackCase$$ForDamagePrediction`
        → poids `Utilities` case 0x22) : santé min/max (cap PV), split bouclier (AccurateShieldDamage@0x78),
        kill/killSure. Mirror de la lecture native des bornes depuis le `DamagePredictionResult`
        (= l'ancien `predict_validate._event_from_dp`).
        `rawHealthDmg*` = dégât santé NON capé par HP (@0x24/@0x28) → over-shoot pour `OverkillUnit`
        (`WillBeOverkill`/`MightBeOverkill` via `IsOverkill`, #84). `forceOverkill` = @0xB2,
        `mightCrit` = @0xB1 (#R34 : le 3ᵉ argument `isCritical` que `MightBeOverkill` passe à
        `IsOverkill`, et que le corps privé RENVOIE dans le cas « létal mais sous le seuil » ;
        `WillBeOverkill`, lui, passe 0 EN DUR — le port posait 0 des deux côtés),
        `preventOverkill` = @0xB3 (#195 : le 5ᵉ argument `isPreventOverkill`, celui-là passé par les
        DEUX bornes — `HasFlag(cible, 0x13)`, posé par `FuelledByFury_BlockOverkillEffect`).
        `cannotBeGuaranteedKilled` = le gate de sortie anticipée de `get_WillBeKill` (#372) : publié
        pour que la trace dise POURQUOI `killSure` est faux, plutôt que de laisser deviner entre
        « bornes insuffisantes » et « gate armé »."""
        dp = self.prediction
        r = dp.accurate_health_damage
        rr = dp.raw_health_damage
        s = dp.accurate_shield_damage
        hp = dp.current_health
        # #54A : `IdunBattle.Core.Services.DamagePredictionResult$$get_WillBeKill` lit `list[0]@0x50` (scénario « tous coups bloqués »)
        # quand la liste est non-vide, sinon le scalaire rawMin@0x24 — killSure compte donc le BLOCK
        # du défenseur (Daemon 25%/50%×Attack, BeastSlayer…). `kill` (MightBeKill IdunBattle.Core.Services.DamagePredictionResult$$get_MightBeKill) reste
        # sur le rawMax scalaire SANS block.
        bmin = dp.block_raw_min
        will_min = bmin if bmin is not None else rr.min
        # #372 : `get_WillBeKill` SORT EN TETE sur `CannotBeGuaranteedKilled@0x89`, avant tout choix
        # de borne. `killSure` est ce verdict-la : le gate doit donc etre ICI aussi, pas seulement
        # dans `DamagePredictionResult.will_be_kill`. Les deux restent DEUX lignes distinctes
        # (et non un appel a `will_be_kill()`) parce que le port y ajoute un gate `hp > 0` PORT-SIDE
        # que le natif n'a pas : `composite_fields` doit rester le mirror NU (`hp == 0` -> le natif
        # rend `true`), sinon on changerait le verdict sur les cibles a 0 PV que `decisionView`
        # conserve. Le flag, lui, est le MEME fait des deux cotes.
        will_sure = (not dp.cannot_be_guaranteed_killed) and will_min >= hp
        # #419-r1-tr9 : la lecture d'ENTITE de `case.Target`, publiee SEULEMENT quand l'appelant a
        # su la distinguer du proxy. Absente -> `DamageUtility` retombe sur `hpBefore`/`shieldBefore`
        # (comportement anterieur, exact des que event.target == prediction.target).
        extra = {}
        if self.target_hp is not None:
            extra["targetHp"] = int(self.target_hp)
        if self.target_shield is not None:
            extra["targetShield"] = int(self.target_shield)
        return {**extra, "hpBefore": hp, "shieldBefore": dp.shield,
                "healthDmgMin": min(r.min, hp), "healthDmgMax": min(r.max, hp),
                "rawHealthDmgMin": rr.min, "rawHealthDmgMax": rr.max, "forceOverkill": dp.force_overkill,
                "mightCrit": dp.might_crit, "preventOverkill": dp.prevent_overkill,
                "shieldDmgMin": s.min, "shieldDmgMax": s.max,
                "limitedByMinHp": dp.limited_by_min_hp, "appliedHits": dp.applied_hits,
                "blockRawMin": bmin,
                "cannotBeGuaranteedKilled": dp.cannot_be_guaranteed_killed,
                "kill": r.max >= hp, "killSure": will_sure}


def calculate_utility_from_damage_event(event: ProbableDamageEvent, wt, target_max_hp: int | None = None) -> float:
    """`IdunBattle.AI.Playbook.Playbooku003C__Il2CppFullySharedGenericTypeu003E$$CalculateUtilityFromDamageEvent` = `prob1 × prob2 × weight` où
    `weight = ForDamagePrediction(prediction)` = le composite Damage (`engine.utilities.damage_composite`,
    case 0x22). Event FRIENDLY → utilité NÉGÉE (`DamageUtility` : friendly-fire negated)."""
    sign = -1.0 if event.friendly else 1.0
    return sign * event.probability * damage_composite(event.composite_fields(), target_max_hp, wt)


def calculate_utility_from_predictions(events: list[ProbableDamageEvent], wt,
                                       target_max_hp_by_id: dict | None = None) -> float:
    """`IdunBattle.AI.Playbook.ComparablePlaybooku003C__Il2CppFullySharedGenericTypeu003E$$CalculateUtilityFromPredictions` (terme dégât) = `Σ` des events.
    `target_max_hp_by_id` = {target_id: maxHP} (combinedMax du composite). Défaut None → cible pleine."""
    m = target_max_hp_by_id or {}
    return sum(calculate_utility_from_damage_event(e, wt, m.get(e.target)) for e in events)


# ── POSE D'EFFET (branche effet de `IdunBattle.AI.Playbook.ComparablePlaybooku003C__Il2CppFullySharedGenericTypeu003E$$CalculateUtilityFromPredictions`) ─────────────────────
# La fonction native somme QUATRE familles de prédictions via 4 slots vtable : dégât (+0x358), soin
# (+0x368/378), EFFET (+0x388=MakeEffectPredictions), repair (dict). La branche effet (LAB_181407fe0) :
#   pour chaque event {target@0, effectType@1, probability@2} : ForEffect(case, caster, target, effectType)
#   -> AddedEffectUtility (UtilityType 0x2d=46=AddedTileEffects) -> Fix64.op_Multiply(event.probability, U).
# FIDÉLITÉ DE BUILD (gqfc5mff6c) : le SEUL override de MakeEffectPredictions est `SpiritLeechPlaybook`
# IdunBattle.AI.Playbook.Loki.SpiritLeechPlaybook$$MakeEffectPredictions (les autres héritent de la base VIDE IdunBattle.AI.Playbook.ComparablePlaybooku003C__Il2CppFullySharedGenericTypeu003E$$MakeEffectPredictions). SpiritLeech pose l'effet 0x429=1065="Pinned",
# ABSENT de la catégorie BC AddedTileEffects (qui ne pondère que Fire/Ice/SpiderWeb) -> son terme effet = 0.
# => ce chemin est structurellement présent mais NUMÉRIQUEMENT INERTE dans ce build. On le porte pour la
# complétude/fidélité (mirror du fold natif) ; il redevient actif dès qu'une BC pondère l'effet posé.
@dataclass
class ProbableEffectEvent:
    """`IdunBattle.AI.Playbook.ProbableEffectEvent` (`.IdunBattle.AI.Playbook.ProbableEffectEvent$$.ctor`). Event porteur d'une POSE D'EFFET
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
    """Branche effet de `IdunBattle.AI.Playbook.ComparablePlaybooku003C__Il2CppFullySharedGenericTypeu003E$$CalculateUtilityFromPredictions` (LAB_181407fe0) :
    `probability × ForEffect→AddedEffectUtility(name, has_effect, is_friend, weights[AddedTileEffects=46])`.
    Poids = catégorie BC `Utilities.Default.AddedTileEffects` (Fire/Ice/SpiderWeb + `Unit_on_*`)."""
    weights = wt.category("AddedTileEffects")
    u = ADDED_EFFECT_UTILITY.evaluate(event.effect_name, event.target_has_effect, event.friendly, weights)
    return event.probability * u
