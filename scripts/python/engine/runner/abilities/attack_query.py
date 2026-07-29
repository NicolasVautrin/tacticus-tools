"""Mirror des predicats d'ELIGIBILITE HEAL/REPAIR de `IdunBattle.Core.Services.AttackQuery`.

Ce sont les deux slots `IAttackQuery` que la cascade de ciblage native invoque -- directement pour
les bits statiques `TargetIsHealable` (0x100, slot 0x11) et `TargetIsRepairable` (0x10000, slot
0x12) de `IdunBattle.Core.Services.TargetingQuery$$GetInvalidTargetReason`, et indirectement par les
regles DYNAMIQUES de deux abilities lues au decompile :

  * `IdunBattleLogic.Entities.Abilities.Active.RepairAbility$$GetDynamicInvalidTargetReason`
    -> `<slot 0x12>(caster, target, HealScope 0, removeEffects=true)`, refus `0x10000` ;
  * `IdunBattleLogic.Entities.Abilities.Active.Loki.InspiredToGreatnessAbility$$GetDynamicInvalidTargetReason`
    -> `<slot 0x11>(caster, target, 0, 1)` ET `<slot 0x12>(caster, target, 0, 0)` (#247).

Les deux surcharges portees ici sont celles A QUATRE ARGUMENTS (`caster` en tete) :
    `AttackQuery.EntityCanBeHealed  (caster, target, scope:HealScope, removeEffects:bool)`
    `AttackQuery.EntityCanBeRepaired(caster, entity, scope:HealScope, removeEffects:bool)`
La surcharge a TROIS arguments d'`EntityCanBeRepaired` (slot 0x13, consommee par
`IdunBattle.Entities.Selectors.RepairableUnitsSelector$$Select`) n'est pas portee : aucun call-site
du registre ne l'atteint.

⚠ NE PAS CONFONDRE avec `healable_heal_type_0` / `repairable_heal_type_1`
(`abilities/behaviours/stats.py`) : celles-la sont les gardes COTE MUTATION des feuilles `Heal` /
`Repair` (pre-filtre `HealableUnitsSelector` : HP<max + `IsAffectedByHealType`). Les fonctions de ce
module sont le gate COTE CIBLAGE, plus large (flags du caster, heal-blockers, trait `Object`,
armure manquante) -- le natif a bien DEUX chemins distincts.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from ...entities.traits.unit_trait import UnitTrait

if TYPE_CHECKING:
    from ..state import State

# `IdunBattle.Entities.Enum.HealType` (2e argument d'`IdunBattle.Entities.UnitExtensions$$IsAffectedByHealType`)
HEAL_TYPE_NON_MECHANICAL = 0
HEAL_TYPE_MECHANICAL = 1

# `IdunBattle.Entities.Enum.UnitFlag` -- les deux flags du CASTER qui ELARGISSENT l'eligibilite :
# ils rendent legale une cible a PLEINS PV. Aucun chemin du port ne les pose (meme situation que le
# flag 0x11 de `is_targetable`) ; le mirror est ecrit pour que la regle s'active d'elle-meme le jour
# ou le canal les exposera, et pour que le lecteur voie que ce n'est pas un oubli.
UNIT_FLAG_CAN_HEAL_FULL_HEALTH = 23      # CanHealFullHealthUnits
UNIT_FLAG_CAN_REPAIR_FULL_HEALTH = 24    # CanRepairFullHealthUnits


def _has_trait(state: "State", unit_id, trait: int) -> bool:
    """`IdunBattle.Entities.UnitExtensions$$HasTrait(unit, trait)` -- substrat gameconfig, la meme
    source que `targeting._unit_traits` (dont ce helper est l'adaptateur par VALEUR d'enum)."""
    from .targeting import _unit_traits
    try:
        name = UnitTrait(int(trait)).name
    except ValueError:                                        # pragma: no cover - enum incomplete
        return False
    return name in (_unit_traits(state, unit_id) or ())


def _trait_resolver(state: "State"):
    """Adaptateur `has_trait(liveunit, trait_int) -> bool` attendu par
    `operations.triggers.revive_effect.is_affected_by_heal_type` / `is_mechanical`."""
    return lambda liveunit, trait: _has_trait(state, (liveunit or {}).get("id"), trait)


def is_affected_by_heal_type(state: "State", unit_id, heal_type: int) -> bool:
    """`IdunBattle.Entities.UnitExtensions$$IsAffectedByHealType` -- DELEGUE au mirror deja porte
    (`operations/triggers/revive_effect.py`, case-89 volet B1), pour qu'il n'existe qu'UNE lecture de
    ce predicat dans le moteur."""
    from ..operations.triggers.revive_effect import is_affected_by_heal_type as _impl
    return bool(_impl(_trait_resolver(state), {"id": unit_id}, int(heal_type)))


def is_damaged_unit(state: "State", entity_id) -> bool:
    """`IdunBattle.Core.Services.AttackQuery$$IsDamagedUnit` -- MIRROR du decompile :

        if (!EntityExtensions.IsUnit(entity)) return false;
        hc = entity.HealthComponent;
        if (UnitExtensions.IsBoss(entity)) return hc.<+0x18> < hc.<+0x10>;
        return HealthComponent.IsWounded(hc);            // CurrentMaximumValue() - <+0x18> > 0

    Les deux branches disent « PV courants < plafond » ; elles ne different que par le plafond lu
    (`FillUpStatComponent.CurrentMaximumValue()` avec modificateurs contre le champ brut `+0x10`).
    Le canal live n'expose qu'UN plafond (`hp_max`), donc le port les confond -- et la branche BOSS
    est de toute facon INATTEIGNABLE depuis le seul call-site porte (1082 refuse deja toute cible
    `UnitTrait.Boss` en amont, cf. `InspiredToGreatnessAbility.get_dynamic_invalid_target_reason`).

    Une MACHINE OF WAR n'est pas une unite pour le natif (`EntityExtensions.IsUnit`) -> False."""
    from .targeting import _resolves_to_unit
    from ..components import HealthComponent
    if entity_id is None or not _resolves_to_unit(state, entity_id):
        return False
    e = state.get_entity(int(entity_id))
    hc = e.get_component(HealthComponent) if e is not None else None
    if hc is None or hc.hp is None or hc.hp_max is None:
        return False
    return int(hc.hp) < int(hc.hp_max)


def has_negative_unit_effect(state: "State", entity_id) -> bool:
    """`IdunBattle.Core.Services.AttackQuery$$HasNegativeUnitEffect` -- le natif lit un conteneur
    DEDIE de l'`EffectsComponent` de la cible (`comp+0x100`, `Count > 0`).

    NON PORTE, et c'est le SEUL residu de ce module a degrader du cote RESTRICTIF (le port peut
    refuser un cast que le natif accepte) : le canal de seed (`decisionView.units[].effects`) donne
    la LISTE des effets portes mais AUCUN marqueur « negatif », et il n'existe pas de table
    `EffectType -> negatif` cote port. Rendre `True` par defaut serait pire (ce disjunct suffirait a
    lui seul a rendre toute cible « soignable », ce qui desarmerait completement la regle qui le
    consomme). On rend donc `False` et on NOMME la degradation.

    Consequence CHIFFREE sur l'unique consommateur porte (1082) : une cible a pleins PV, actif non
    consomme, mais portant un effet negatif serait refusee par le port alors que le natif l'accepte.
    Aucun cas de ce genre dans les montages de #247/#252 (`abilityReason` d'accord sur 40/40)."""
    return False


def has_heal_blockers(state: "State", entity_id) -> bool:
    """`IdunBattle.Entities.UnitExtensions$$HasHealBlockers` -- MIRROR du decompile :

        if (GetEntityType(entity) != 1 /* Unit */) return false;
        hc = entity.HealthComponent;
        return hc.<+0x78> != null && hc.<+0x78>.Count > 0;      // dict des bloqueurs de soin

    NON PORTE (le dict `+0x78` n'est pas expose par le canal live ; c'est la ou vit `Cursed`, cf.
    `operations/triggers/loki/living_metal.py`). Rendu `False` = « aucun bloqueur », donc PERMISSIF
    ici : le predicat qui l'appelle en negation reste vrai, et l'eligibilite n'est jamais refusee
    pour une raison que le port ne sait pas lire."""
    return False


def is_at_group_unit_heal_limit(state: "State", entity_id) -> bool:
    """`IdunBattle.Core.Services.AttackQuery$$IsAtGroupUnitHealLimit` -- NON PORTE, et SANS OBJET
    pour les call-sites de ce module : les deux appels de 1082 passent `scope = HealType/HealScope 0`,
    valeur sous laquelle le natif ne consulte JAMAIS ce predicat (`if (scope != 0 && ...)` cote heal,
    `if (scope == 0) return true;` cote repair). Ecrit pour que la structure du mirror reste
    complete et que le lecteur voie la condition de garde."""
    return False


def entity_can_be_healed(state: "State", caster_id, target_id, scope: int = 0,
                         remove_effects: bool = False) -> bool:
    """`IdunBattle.Core.Services.AttackQuery$$EntityCanBeHealed(caster, target, scope, removeEffects)`
    -- MIRROR 1:1 du decompile (surcharge 4 arguments) :

        if (EntityExtensions.IsMachine(target)) return false;
        if (!(   AttackQuery.IsDamagedUnit(target)
              || (removeEffects && AttackQuery.HasNegativeUnitEffect(target))
              || (caster != null && UnitExtensions.HasFlag(caster, 0x17 CanHealFullHealthUnits))))
            return false;
        if (UnitExtensions.HasHealBlockers(target))                      return false;
        if (scope != 0 && AttackQuery.IsAtGroupUnitHealLimit(target))    return false;
        if (UnitExtensions.HasTrait(target, 0xd Object))                 return false;
        return UnitExtensions.IsAffectedByHealType(target, 0 NonMechanical);

    Le premier test est bien `IsMachine` (une MoW n'est jamais soignable par ce chemin), pas
    `IsMechanical` : ce sont deux predicats DIFFERENTS, et le second n'intervient qu'au travers
    d'`IsAffectedByHealType`."""
    from .targeting import _is_machine
    from ..components import UnitFlagsComponent
    if target_id is None or _is_machine(state, target_id):
        return False
    eligible = is_damaged_unit(state, target_id)
    if not eligible and remove_effects:
        eligible = has_negative_unit_effect(state, target_id)
    if not eligible and caster_id is not None:
        ce = state.get_entity(int(caster_id))
        fl = ce.get_component(UnitFlagsComponent) if ce is not None else None
        eligible = bool(fl is not None and fl.has(UNIT_FLAG_CAN_HEAL_FULL_HEALTH))
    if not eligible:
        return False
    if has_heal_blockers(state, target_id):
        return False
    if int(scope) != 0 and is_at_group_unit_heal_limit(state, target_id):
        return False
    if _has_trait(state, target_id, int(UnitTrait.Object)):
        return False
    return is_affected_by_heal_type(state, target_id, HEAL_TYPE_NON_MECHANICAL)


def entity_can_be_repaired(state: "State", caster_id, target_id, scope: int = 0,
                           remove_effects: bool = False) -> bool:
    """`IdunBattle.Core.Services.AttackQuery$$EntityCanBeRepaired(caster, entity, scope, removeEffects)`
    -- MIRROR 1:1 du decompile (surcharge 4 arguments) :

        if (EntityExtensions.IsMachine(entity)) return false;
        if (!(   AttackQuery.IsDamagedUnit(entity)
              || UnitExtensions.GetStat(entity, StatType.Armor = 4, StatPart.Missing = 4) > 0
              || (removeEffects && AttackQuery.HasNegativeUnitEffect(entity))
              || (caster != null && UnitExtensions.HasFlag(caster, 0x18 CanRepairFullHealthUnits))))
            return false;
        if (UnitExtensions.HasHealBlockers(entity))                       return false;
        if (!UnitExtensions.IsAffectedByHealType(entity, 1 Mechanical))   return false;
        if (scope == 0) return true;
        return !AttackQuery.IsAtGroupUnitHealLimit(entity);

    DEUX ecarts de STRUCTURE avec le jumeau heal, lus et non deduits : le disjunct supplementaire
    `GetStat(Armor, Missing) > 0` (une armure entamee suffit a rendre reparable), et l'ORDRE
    (`IsAffectedByHealType` avant le plafond de groupe, et pas de test `UnitTrait.Object`).

    `StatPart.Missing` de `StatType.Armor` n'est pas dans le catalogue de `combatSnapshot` -> non
    porte, rendu 0 (le disjunct ne peut donc qu'etre RATE : degradation restrictive du meme ordre
    que `has_negative_unit_effect`, et NOMMEE au meme titre)."""
    from .targeting import _is_machine
    from ..components import UnitFlagsComponent
    if target_id is None or _is_machine(state, target_id):
        return False
    eligible = is_damaged_unit(state, target_id)
    # `GetStat(entity, StatType.Armor, StatPart.Missing) > 0` : NON PORTE (StatPart.Missing hors
    # catalogue `combatSnapshot`) -> le disjunct est lu comme 0, jamais devine.
    if not eligible and remove_effects:
        eligible = has_negative_unit_effect(state, target_id)
    if not eligible and caster_id is not None:
        ce = state.get_entity(int(caster_id))
        fl = ce.get_component(UnitFlagsComponent) if ce is not None else None
        eligible = bool(fl is not None and fl.has(UNIT_FLAG_CAN_REPAIR_FULL_HEALTH))
    if not eligible:
        return False
    if has_heal_blockers(state, target_id):
        return False
    if not is_affected_by_heal_type(state, target_id, HEAL_TYPE_MECHANICAL):
        return False
    if int(scope) == 0:
        return True
    return not is_at_group_unit_heal_limit(state, target_id)


def get_owned_effect_is_active(state: "State", unit_id, effect_type: int,
                               has_trait_effect_source: Optional[int] = None):
    """`IdunBattle.Entities.EntityExtensions$$GetOwnedEffect(owner, state, effectType)` suivi de la
    lecture `EffectComponent.IsActive @+0x5c` -- rendu sous forme TERNAIRE :

        None  = l'entite-effet n'existe pas du tout (le natif rend `null`)
        True  = elle existe et son flag `IsActive` vaut 1
        False = elle existe et son flag vaut 0  (l'effet est DESACTIVE)

    POURQUOI UN TERNAIRE, et pourquoi `has_trait_effect_source`. Nativement l'entite-effet d'un
    OWNER-EFFECT de trait (`idun.Idun.Source.Shared.Battle.StaticBattleRules.StaticBattleRules.Trait$$GetEffectToBeAddedToOwnerForTrait`)
    existe EN PERMANENCE sur le porteur du trait : seul son flag bascule. Cote port, le canal de
    seed (`decisionView.units[].effects` via `readEffectsByUnit`) DROPPE les instances
    `IsActive == 0` (case-160, prouve live) -- « absente » et « presente mais desactivee » s'y
    confondent. `has_trait_effect_source` = le TRAIT dont l'owner-effect derive : quand l'unite le
    porte, l'entite-effet EXISTE nativement, et l'absence cote port signifie donc DESACTIVEE."""
    eff = None
    if state.effects is not None and unit_id is not None:
        for e in state.effects.by_unit.get(int(unit_id), []):
            if e.consumed or int(e.effect_type) != int(effect_type):
                continue
            eff = e
            break
    if eff is not None:
        return bool(getattr(eff, "active", True))
    if has_trait_effect_source is not None and _has_trait(state, unit_id, int(has_trait_effect_source)):
        return False                      # entite-effet native presente, seed live muet => DESACTIVEE
    return None
