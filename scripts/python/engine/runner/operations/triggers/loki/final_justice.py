"""`Abilities.Active.Loki.FinalJusticeAbility` (IdunBattleLogic.Entities.Abilities.Active.Loki.FinalJusticeAbility$$CreateTrigger) — attaque de MORT de worldKharn (trait
`FinalJustice`). Cf. `loki/__init__.py` pour le regroupement « Loki »."""
from __future__ import annotations

from typing import Optional

from ....state import State
from ....components import StatsComponent, HealthComponent
from ....abilities.behaviours.combat import UseActiveAbility
from ....abilities.behaviours.context import entities_from_state
from ....abilities.behaviours.lifecycle import TRIGGERED_ABILITY_BEHAVIOURS   # #1002-r1
from .....entities.stats import StatType
from .....entities.selectors.accessors import Target
from .....entities.selectors.tiles import Caster
from .....dsl.effects import ExecutionContext
from .....dsl.event_trigger_type import EventTriggerType
from ..base import TriggeredAbility, TriggerEvent, _adjacent_enemies
from .....entities.triggered_ability_type import TriggeredAbilityType   # #270-r1-r1-r3
from ...damage_utility import damage_utility_weights
from ...damage_utility import first_by_damage_utility

# Les poids d'utilité (BC `Utilities`) et le tri lui-même vivent désormais dans le port PARTAGÉ du
# sélecteur natif — `operations/damage_utility.py` (`SortUnitsByDamageUtilitySelector$$Select`) : FinalJustice
# et AncestralFortune (#113) branchent le MÊME étage de tri, seul le nœud de dégât diffère.
def _damage_utility_weights():
    """Alias historique (call-sites/tests existants) — cf. `damage_utility.damage_utility_weights`."""
    return damage_utility_weights()


def _normal_attack_damage_node(state: State, owner_id: int):
    """`IdunBattleLogic.Entities.DSLFormulas$$NormalAttackDamage(caster)` — le nœud `+0x40` que
    `FinalJusticeAbility$$CreateBehaviour` branche sur `SortUnitsByDamageUtility`.

    Corps natif, LU : `new StatAmountFormula(unitsSelector, statType: StatType.Attack = 0,
    statPart: 0, modificationEntity: null, selectionType: 0)` — donc **la stat `Attack` du caster**,
    c.-à-d. la base d'**UN** coup, pas le total d'une attaque.

    ⚠ **CE QUE #494-r1-r1 A CORRIGÉ.** Ce call-site passait ici `_normal_attack_health_range` : la
    plage SANTÉ du TOTAL de l'attaque normale (hits d'arme + effets), pré-armure. Tant que la clé de
    tri était pré-armure, l'écart était un facteur COMMUN à toutes les cibles, donc sans effet sur
    l'ordre. Depuis que la clé passe par la prédiction COMPLÈTE (armure + perçage, non linéaires),
    un total mis à la place d'un montant PAR COUP franchit d'autres seuils : le mirror doit être le
    nœud, pas son agrégat.

    Renvoie l'entier `Attack`, ou None si les stats sont indisponibles."""
    owner = state.get_entity(owner_id)
    sc = owner.get_component(StatsComponent) if owner is not None else None
    if sc is None:
        return None
    return int(sc.ctx.stat(StatType.ATTACK))


def _finaljustice_target(state: State, owner_id: int) -> Optional[int]:
    """`IdunBattleLogic.Entities.DSLSelectors$$ValidNormalAttackTargets → `IdunBattleLogic.Entities.DSLSelectors$$SortUnitsByDamageUtility → MEILLEURE cible.

    Tri natif RE LECTURE INTÉGRALE (`IdunBattle.Entities.Selectors.SortUnitsByDamageUtilitySelector$$Select +
    `IdunBattleLogic.Entities.Abilities.Active.Loki.FinalJusticeAbility$$CreateBehaviour) : pour chaque cible normal-attaquable, bâtit une
    `DamagePrediction` de l'attaque normale → score `UtilityDecider.CalculateUtility(UtilityDefinition
    0x22 = 34 = composite Damage, cible, prediction)` → Dict cible→util → `OrderBy(util via lambda
    <Select>b__0)` → 1ʳᵉ. Le lambda `<Select>b__0`IdunBattle.Entities.Selectors.SortUnitsByDamageUtilitySelector.u003Cu003Ec__DisplayClass9_0$$u003CSelectu003Eb__0 renvoie **`Fix64.op_UnaryNegation(util)`**
    (= −util) ⇒ `OrderBy(−util)` = tri DÉCROISSANT par utilité ⇒ la 1ʳᵉ cible = utilité **MAX**.
    ⇒ FinalJustice frappe l'**argmax du composite Damage(35)** = DamageDealt(36)+KillUnit(37)+
    OverkillUnit(38) (`engine.utilities.damage_composite`). Kharn = mêlée ⇒ cibles = ennemis adjacents.

    Le nœud `+0x28` est `UnitNormalAttackType` et le nœud `+0x48` (hits) est **null** ⇒ la clé est la
    prédiction de l'ATTAQUE NORMALE du caster, montant = la stat `Attack`, **UN** coup (#494-r1-r1).
    Elle porte donc l'armure, le perçage, la défense et les modificateurs par cible ; le classement
    ne dépend plus des seuls PV. Tie-break : `OrderBy` natif STABLE → ordre source
    `ValidNormalAttackTargets`. Bouclier non modélisé côté cible du composite (résidu partagé).
    Fallback PV-bas si les stats sont indisponibles."""
    cands = _adjacent_enemies(state, owner_id)
    if not cands:
        return None

    def _hp(eid: int) -> int:
        e = state.get_entity(eid)
        h = e.get_component(HealthComponent) if e is not None else None
        return int(h.hp) if (h is not None and h.hp is not None) else (1 << 30)

    amount = _normal_attack_damage_node(state, owner_id)
    if amount is None:                                     # pas de stats → proxy PV-bas (fallback)
        return min(cands, key=lambda eid: (_hp(eid), eid))

    # `First(SortUnitsByDamageUtility(…), 1)` — étage de tri PARTAGÉ (port du sélecteur natif) : argmax
    # du composite Damage. Profil/perçage NON passés : le nœud d'ability est `UnitNormalAttackType`,
    # donc le foyer résout l'ARME NORMALE du caster (`normal_attack_profile_and_pierce`).
    return first_by_damage_utility(state, cands, amount, amount, owner_id=owner_id)


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
    TRIGGERED_ABILITY_ID = TriggeredAbilityType.FinalJustice
    fire_on_death = True

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        if ev.dying_id != self.owner_id:                 # OwnerIsTarget (owner = unité mourante)
            return False
        if ev.overkill:                                  # NOT TargetIsOverkilled
            return False
        return _finaljustice_target(state, self.owner_id) is not None   # Count(validTargets) > 0

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        return _finaljustice_attack(state, self.owner_id)


def _finaljustice_triggered_directly(state: State, owner_id: int, entities, ectx) -> Optional[dict]:
    """Entree du noeud `TriggerAbility(_, 0x400 = TriggeredAbilityType.FinalJustice, ...)` -- le
    SECOND point d'entree de ce behaviour, et il court-circuite `CreateTrigger` (#1002-r1).

    Son unique declencheur porte est `IdunBattleLogic.Entities.Abilities.Triggered.Loki.
    FinalVengeance_UnitEffect$$CreateTargetTriggerBehaviour` (effet 0x5ae = 1454, pose par
    `RelicOfLostCadia` sur les summons imperiaux allies adjacents) : le summon ne PORTE pas
    `FinalJustice`, l'effet la lui prete -- d'ou l'`ignoreUnitHavingAbility = true` de ce call-site.

    ⚠ **CE QUE CETTE FONCTION DOIT RE-MATERIALISER, ET POURQUOI.** Le gate natif
    `AmountIsGreater(Count(sortedTargets), Zero) & NOT TargetIsOverkilled` vit dans le
    `...FinalJusticeAbility$$CreateBehaviour`, PAS dans son `CreateTrigger` -- le port l'a collapse
    dans `FinalJusticeAbility.matches()` (choix de forme, deja documente sur la classe). Ce point
    d'entree-ci ne passe PAS par `matches` : sans re-materialisation, le bras `Count > 0` survivrait
    (il est dans `_finaljustice_attack`, qui rend `target: None`) mais le bras `NOT
    TargetIsOverkilled` DISPARAITRAIT. Il est donc applique par l'APPELANT, qui seul dispose de
    l'evenement (cf. `triggers/loki/final_vengeance.py`) ; ici on ne rejoue que le behaviour.

    Signature imposee par `TRIGGERED_ABILITY_BEHAVIOURS` : `(state, owner_id, entities, ectx)`.
    `entities`/`ectx` sont ceux du DECLENCHEUR ; `_finaljustice_attack` reconstruit son propre
    contexte autour de `owner_id`, qui est l'unite declenchee -- exactement ce que fait le natif
    (`TriggerAbilityBehaviour$$Execute` appelle le slot `0x56` PAR unite de `targets`)."""
    return _finaljustice_attack(state, int(owner_id))


# Inscription au registre du noeud `TriggerAbility` -- a l'IMPORT, comme `full_throttle` (1134) et
# `abilities/tau.py` (1127). Ce module est deja importe par `dispatch/registry.py` (il y fournit
# `FinalJusticeAbility`), donc l'entree existe des que le registre est charge.
TRIGGERED_ABILITY_BEHAVIOURS[int(TriggeredAbilityType.FinalJustice)] = _finaljustice_triggered_directly
