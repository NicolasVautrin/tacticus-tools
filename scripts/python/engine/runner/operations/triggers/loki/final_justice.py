"""`Abilities.Active.Loki.FinalJusticeAbility` (IdunBattleLogic.Entities.Abilities.Active.Loki.FinalJusticeAbility$$CreateTrigger) — attaque de MORT de worldKharn (trait
`FinalJustice`). Cf. `loki/__init__.py` pour le regroupement « Loki »."""
from __future__ import annotations

from typing import Optional

from ....state import State
from ....components import StatsComponent, HealthComponent
from ....abilities.behaviours import UseActiveAbility, entities_from_state
from ....damage_model import select_weapon_pierce, attacker_modifiers
from .....entities.stats import StatType
from .....entities.effects import hits_bonus_from_effects
from .....entities.selectors import Caster, Target
from .....services.damage_prediction import get_attack_prediction
from .....dsl.effects import ExecutionContext
from .....dsl.event_trigger_type import EventTriggerType
from ..base import TriggeredAbility, TriggerEvent, _adjacent_enemies

# Les poids d'utilité (BC `Utilities`) et le tri lui-même vivent désormais dans le port PARTAGÉ du
# sélecteur natif — `operations/damage_utility.py` (`SortUnitsByDamageUtilitySelector$$Select`) : FinalJustice
# et AncestralFortune (#113) branchent le MÊME étage de tri, seul le nœud de dégât diffère.
def _damage_utility_weights():
    """Alias historique (call-sites/tests existants) — cf. `damage_utility.damage_utility_weights`."""
    from ...damage_utility import damage_utility_weights
    return damage_utility_weights()


def _normal_attack_health_range(state: State, owner_id: int):
    """Plage de dégât SANTÉ (min,max) du TOTAL de l'attaque normale mêlée de l'owner, PRÉ-ARMURE — mirror
    de la `DamagePrediction` que `IdunBattle.Entities.Selectors.SortUnitsByDamageUtilitySelector$$Select bâtit par cible
    (`FUN_18002c910` scénario 0x25, profil `NormalAttackDamage`). La prédiction IA d'attaque normale est
    PRÉ-ARMURE (`armor=0` ; cf. en-tête `services/damage_prediction`) ⇒ le dégât est INDÉPENDANT de la
    cible → calculé UNE fois. Inclut les ×modifiers d'effet de l'attaquant (RapidAssault…) et les hits
    d'arme+effet. Renvoie (dmin, dmax) du total, ou None si stats indispo."""
    owner = state.get_entity(owner_id)
    sc = owner.get_component(StatsComponent) if owner is not None else None
    if sc is None:
        return None
    ctx = sc.ctx
    ahc = owner.get_component(HealthComponent)
    _pierce, _ranged, whits = select_weapon_pierce(ctx, 1)             # dist=1 → arme mêlée
    mods, active = attacker_modifiers(state, owner_id, ahc.hp if ahc else None, is_ranged=False)
    hits = max(1, whits + ctx.stat(StatType.EXTRA_HITS) + hits_bonus_from_effects(active))
    pred = get_attack_prediction(
        target_current_health=0, initial_damage=int(ctx.stat(StatType.ATTACK)), hits=hits,
        profile_type=0, armor=0, pierce_pct=100, mods=mods, spread_pct=20,    # PRÉ-ARMURE (armor=0)
        attacker_effects=active)   # #202 : max-out evalue DANS predict_attack_raw
    return (pred.accurate_health_damage.min, pred.accurate_health_damage.max)


def _finaljustice_target(state: State, owner_id: int) -> Optional[int]:
    """`IdunBattleLogic.Entities.DSLFactory$$ValidNormalAttackTargets → `IdunBattleLogic.Entities.DSLFactory$$SortUnitsByDamageUtility → MEILLEURE cible.

    Tri natif RE LECTURE INTÉGRALE (`IdunBattle.Entities.Selectors.SortUnitsByDamageUtilitySelector$$Select +
    `IdunBattleLogic.Entities.Abilities.Active.Loki.FinalJusticeAbility$$CreateBehaviour) : pour chaque cible normal-attaquable, bâtit une
    `DamagePrediction` de l'attaque normale → score `UtilityDecider.CalculateUtility(UtilityDefinition
    0x22 = 34 = composite Damage, cible, prediction)` → Dict cible→util → `OrderBy(util via lambda
    <Select>b__0)` → 1ʳᵉ. Le lambda `<Select>b__0`IdunBattle.Entities.Selectors.SortUnitsByDamageUtilitySelector.u003Cu003Ec__DisplayClass9_0$$u003CSelectu003Eb__0 renvoie **`Fix64.op_UnaryNegation(util)`**
    (= −util) ⇒ `OrderBy(−util)` = tri DÉCROISSANT par utilité ⇒ la 1ʳᵉ cible = utilité **MAX**.
    ⇒ FinalJustice frappe l'**argmax du composite Damage(34)** = DamageDealt(35)+KillUnit(36)+
    OverkillUnit(37) (`engine.utilities.damage_composite`). Kharn = mêlée ⇒ cibles = ennemis adjacents.

    Prédiction PRÉ-ARMURE (`_normal_attack_health_range`) ⇒ dégât identique pour toutes les cibles ; le
    classement dépend des PV courants/max + flags kill/overkill PAR cible (kill = dmg ≥ PV). Tie-break :
    `OrderBy` natif STABLE → ordre source `ValidNormalAttackTargets` ; approximé ici par id croissant
    (itération `sorted(cands)` + argmax STRICT). Bouclier non modélisé (`shieldBefore=0`, comme le reste
    du moteur — TODO). Fallback PV-bas si la prédiction est indispo (pas de stats)."""
    cands = _adjacent_enemies(state, owner_id)
    if not cands:
        return None

    def _hp(eid: int) -> int:
        e = state.get_entity(eid)
        h = e.get_component(HealthComponent) if e is not None else None
        return int(h.hp) if (h is not None and h.hp is not None) else (1 << 30)

    rng_pred = _normal_attack_health_range(state, owner_id)
    if rng_pred is None:                                   # pas de stats → proxy PV-bas (fallback)
        return min(cands, key=lambda eid: (_hp(eid), eid))

    dmin, dmax = rng_pred
    # `First(SortUnitsByDamageUtility(…), 1)` — étage de tri PARTAGÉ (port du sélecteur natif) : argmax du
    # composite Damage(34), tie-break `id` croissant. Bit-identique à l'ancien corps inline (mêmes champs).
    from ...damage_utility import first_by_damage_utility
    return first_by_damage_utility(state, cands, dmin, dmax)


def _finaljustice_attack(state: State, owner_id: int) -> Optional[dict]:
    """Behaviour FinalJustice (IdunBattleLogic.Entities.Abilities.Active.Loki.FinalJusticeAbility$$CreateBehaviour), MIGRÉ en ARBRE DSL (#149 slice-22) :
    `UseActiveAbility(Self@0x148, <best>, UnitNormalAttackType)` = UNE attaque NORMALE (chemin
    `AttackDamageOperation.execute`, déjà bit-exact) sur la meilleure cible normal-attaquable. Le sélecteur
    AI-target `SortUnitsByDamageUtility(ValidNormalAttackTargets)` (kind S lourd, chevauche le playbook)
    reste IMPÉRATIF (`_finaljustice_target`) et est COLLAPSÉ en `Target()` (== ThunderousAssault
    `Units(Cache(First(Nearest(...))))`). Le gate natif `Count(validTargets)>0 AND NOT TargetIsOverkilled`
    + le nœud `Inform` sont portés dans `matches()` (déjà fidèle). Bit-exact vs l'ancien corps impératif
    BY CONSTRUCTION : la feuille `UseActiveAbility` appelle le MÊME `AttackDamageOperation.execute(owner,
    best, 20)`. No-op si pas de cible. (L'owner est `alive=False` — death-rattle ; l'attaque s'exécute
    quand même.)"""
    target = _finaljustice_target(state, owner_id)
    if target is None:
        return {"trait": "FinalJustice", "owner": owner_id, "target": None}
    ectx = ExecutionContext(state=state, rng=state.rng)
    UseActiveAbility(Caster(), Target()).execute(entities_from_state(state, owner_id, target), ectx)
    res = next((p for (n, p) in ectx.emitted if n == "UseActiveAbility"), {}).get("attack")
    return {"trait": "FinalJustice", "owner": owner_id, "target": target, "attack": res}


class FinalJusticeAbility(TriggeredAbility):
    """`FinalJusticeAbility` (IdunBattleLogic.Entities.Abilities.Active.Loki.FinalJusticeAbility$$CreateTrigger CreateTrigger / IdunBattleLogic.Entities.Abilities.Active.Loki.FinalJusticeAbility$$CreateBehaviour CreateBehaviour) — attaque de MORT de
    worldKharn (trait `FinalJustice`).

    CreateTrigger = `OnPreDeath & OwnerIsTarget` — l'owner EST l'unité qui meurt (slot 0x178=dying).
    Behaviour = `UseActiveAbility(UnitNormalAttackType, best)` sur la meilleure cible normal-attaquable
    (`ValidNormalAttackTargets` -> `SortUnitsByDamageUtility`), GATÉ `Count(validTargets)>0 AND NOT
    TargetIsOverkilled`. ⇒ en mourant, Kharn porte UNE attaque normale sur l'ennemi le plus rentable —
    SAUF si le coup fatal l'a OVERKILL (dmg >= 2*PV ; cf. `is_overkill`). `fire_on_death` car l'owner est
    déjà `alive=False` au moment du dispatch MORT (bypass du gate vivant, comme `CanGetAbilityTrigger`)."""
    event_id = EventTriggerType.PreUnitDeath
    # `TriggeredAbilityType.FinalJustice = 0x400 = 1024` — l'id que
    # `IdunBattle.Entities.Abilities.BaseTriggeredAbility$$Execute` inscrit dans l'`AbilityEntities`
    # AVANT le behaviour : les kills portes par la riposte le transportent donc, et c'est EXACTEMENT ce
    # que teste `TriggeringAbilityIs(AbilityOrEffect(0x400))` du
    # `IdunBattleLogic.Entities.Abilities.Triggered.Loki.FuelledByFury_ReviveAbility$$CreateTrigger`
    # (i2 : « the first time each turn he defeats an enemy **with an attack triggered by Final
    # Vengeance** »). Cf. `dispatch/core.py` (foyer d'ecriture) et `triggers/base.py`.
    TRIGGERED_ABILITY_ID = 1024
    fire_on_death = True

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        if ev.dying_id != self.owner_id:                 # OwnerIsTarget (owner = unité mourante)
            return False
        if ev.overkill:                                  # NOT TargetIsOverkilled
            return False
        return _finaljustice_target(state, self.owner_id) is not None   # Count(validTargets) > 0

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        return _finaljustice_attack(state, self.owner_id)
