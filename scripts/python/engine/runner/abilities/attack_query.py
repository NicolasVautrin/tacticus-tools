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

La surcharge a TROIS ARGUMENTS d'`EntityCanBeRepaired` (slot 0x13, consommee par
`IdunBattle.Entities.Selectors.RepairableUnitsSelector$$Select`) est desormais ATTEIGNABLE : #303 a
porte `FabricatorClawArrayAbility`, dont le selecteur de cible passe par `DSLSelectors$$Repairable`.
Elle n'a PAS de deuxieme implementation ici -- relue verbatim sur `rnca9r7q6c`, elle EST la 4-args
avec `caster = null` : la seule difference est le disjunct `caster != null && HasFlag(caster,
0x18 CanRepairFullHealthUnits)`, qui disparait de lui-meme. Le noeud DSL `Repairable` l'atteint donc
par `entity_can_be_repaired(state, None, entity, scope, remove_effects)` (accesseur
`ctx.entity_can_be_repaired`, branche par `entities_from_state`).

⚠ NE PAS CONFONDRE avec `healable_heal_type_0` / `repairable_heal_type_1`
(`abilities/behaviours/stats.py`) : celles-la sont les gardes COTE MUTATION des feuilles `Heal` /
`Repair` (pre-filtre `HealableUnitsSelector` : HP<max + `IsAffectedByHealType`). Les fonctions de ce
module sont le gate COTE CIBLAGE, plus large (flags du caster, heal-blockers, trait `Object`,
armure manquante) -- le natif a bien DEUX chemins distincts.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from ...entities.traits.unit_trait import UnitTrait
from ...entities.unit_flag import UnitFlag   # #270-r1-r1-r3
from ..components import HealthComponent
from ..components import UnitComponent
from ..components import UnitFlagsComponent
from ...entities.effects.loki import heal_blocking as _heal_blocking   # forme B (CLAUDE.md) -- GRATUIT :
# `heal_blocking` charge seul en process frais ne tire PAS ce module, donc aucun cycle a differer.
from ..operations.triggers.revive_effect import is_affected_by_heal_type as _impl
from .targeting import _is_machine
from .targeting import _resolves_to_unit
from .targeting import _unit_traits

if TYPE_CHECKING:
    from ..state import State

# `IdunBattle.Entities.Enum.HealType` (2e argument d'`IdunBattle.Entities.UnitExtensions$$IsAffectedByHealType`)
HEAL_TYPE_NON_MECHANICAL = 0
HEAL_TYPE_MECHANICAL = 1

# `IdunBattle.Entities.Enum.UnitFlag` -- les deux flags du CASTER qui ELARGISSENT l'eligibilite :
# ils rendent legale une cible a PLEINS PV.
#
# ⚠ CES DEUX DISJONCTIONS MORDENT (#982-r5). La phrase qui vivait ici -- « aucun chemin du port ne
# les pose ; le mirror est ecrit pour le jour ou le canal les exposera » -- est PERIMEE, et l'avoir
# laissee a produit DEUX verdicts faux d'affilee : #966-r2 (« aucun consommateur porte ne le lit »)
# puis #982-r5 (« le port n'est pas ecrit »). Le port ne POSE toujours pas ces flags, et il n'a pas
# a le faire : `IdunBattle.Entities.Behaviours.AddFlagBehaviour$$Execute` a deja joue COTE NATIF
# avant la capture, et `runner/snapshot._load_unit_flags` recopie `combatSnapshot.units[].unitFlags`
# dans le `UnitFlagsComponent`. La disjonction lit donc une valeur MESUREE, pas un substrat vide.
#
# MESURE (#982-r5, build `rnca9r7q6c`, board `MC1_67`, seed 777, `spaceWolfPriest` injecte au
# catalogue) : `combatSnapshot.unitFlagTypes.CanHealFullHealthUnits = 23` ; `unitFlags = [23]` sur
# `spaceWolfPriest`, `[]` sur les trois autres unites (temoin NON degenere) ; et cote port, sur une
# cible a PLEINS PV, `entity_can_be_healed(caster = spaceWolfPriest) = True` contre `False` pour un
# caster sans le flag ET pour `caster = None`. Le pendant `0x18` a ete mesure de meme sur
# `admecManipulus` (#952, `unitFlags = [24]`).
# ⚠ PIEGE DE MESURE : `combatSnapshot.units[].entityId` est le `squadId` d'`observeBattle`, PAS son
# `entityId`. Un probe qui apparie par `observeBattle.entityId` lit `flags = None` sur TOUTES les
# unites et conclut faussement que rien n'est seede.
# Cliquet : `tests/engine/test_982r5_can_heal_full_health_offline.py`.
UNIT_FLAG_CAN_HEAL_FULL_HEALTH = UnitFlag.CanHealFullHealthUnits      # CanHealFullHealthUnits
UNIT_FLAG_CAN_REPAIR_FULL_HEALTH = UnitFlag.CanRepairFullHealthUnits    # CanRepairFullHealthUnits


def _has_trait(state: "State", unit_id, trait: int) -> bool:
    """`IdunBattle.Entities.UnitExtensions$$HasTrait(unit, trait)` -- substrat d'ENTITE, la meme
    source que `targeting._unit_traits` (dont ce helper est l'adaptateur par VALEUR d'enum) : depuis
    #264 la MESURE live (`combatSnapshot.units[].traits`) quand elle existe, sinon kit gameconfig +
    grande-alliance + traits accordes en bataille."""
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
    if entity_id is None or not _resolves_to_unit(state, entity_id):
        return False
    e = state.get_entity(int(entity_id))
    hc = e.get_component(HealthComponent) if e is not None else None
    if hc is None or hc.hp is None or hc.hp_max is None:
        return False
    return int(hc.hp) < int(hc.hp_max)


def health_is_readable(state: "State", entity_id) -> bool:
    """Les PV de la cible sont-ils LISIBLES offline (`HealthComponent` seede avec `hp` ET `hp_max`) ?

    Ce n'est pas un predicat natif : c'est le garde-fou d'HONNETETE de ce module. `is_damaged_unit`
    rend `False` aussi bien pour « cible a pleins PV » (verdict REEL) que pour « le port ne sait pas
    lire ses PV » (verdict INCONNU). Un appelant qui REFUSE sur la conjonction de plusieurs
    disjuncts faux doit distinguer les deux, sinon il fabrique un refus la ou le natif, lui, a lu
    une vraie valeur. Meme role que le `None` d'`entity_can_have_active_ability_reset`."""
    if entity_id is None or not _resolves_to_unit(state, entity_id):
        return False
    e = state.get_entity(int(entity_id))
    hc = e.get_component(HealthComponent) if e is not None else None
    return hc is not None and hc.hp is not None and hc.hp_max is not None


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

    PORTE depuis #927. Le dict `+0x78` n'est toujours pas materialise -- il n'a pas besoin de
    l'etre : les DEUX seules methodes qui l'ecrivent sont
    `IdunBattle.Entities.Effects.HealBlockingEffect$$ApplyInternal` (`Add(effect.Id, effect.Id)`) et
    `...$$RevertInternal` (`Remove(effect.Id)`), donc son contenu est EXACTEMENT l'ensemble des
    instances vivantes de cette famille sur la cible. Le port teste cette famille par son TYPE
    (`entities/effects/loki/heal_blocking.HealBlockingEffect`), ce qui est equivalent PAR
    CONSTRUCTION.

    ⚠ AUCUN filtre `IsActive @+0x5c` : ni `ApplyInternal`/`RevertInternal`, ni `HasHealBlockers` ne
    consultent le flag. On lit donc la liste BRUTE du porteur (`EffectsState.by_unit`), non
    `active_effects` -- exactement comme `components.has_effect_of_type`, et pour la meme raison.
    On ecarte les seules instances que le natif a DEJA retirees de la liste possedee : `consumed`
    (retire d'`EffectsOwnedComponent`) et `expired` (timer a 0, `RevertInternal` joue).

    ⚠ CE PREDICAT DEGRADE DU COTE RESTRICTIF quand il rend `True` (il REFUSE un soin), a l'inverse
    de la quasi-totalite des non-ports de ce module. Il ne peut donc rendre `True` que sur un effet
    dont la classe est INSCRITE au registre `EffectFactory` : un `EffectType` bloqueur non encore
    porte (`MischiefMakers` 1469, cf. `heal_blocking.py`) reste materialise en `BaseEffect` nu et ne
    mord pas -- meme dégradation PERMISSIVE qu'avant #927, et bornee a ce seul id.

    Une entite non-unite (tuile, MoW) n'a pas d'entree dans `EffectsState.by_unit` cote unite ; le
    garde `_resolves_to_unit` reproduit `GetEntityType(entity) != 1`."""
    if entity_id is None or not _resolves_to_unit(state, entity_id):
        return False
    st = getattr(state, "effects", None)
    if st is None:
        return False
    return any(isinstance(e, _heal_blocking.HealBlockingEffect) and not e.consumed and not e.expired
               for e in st.by_unit.get(int(entity_id), []))


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


def can_be_resurrected(state: "State", target_id, heal_type: int) -> bool:
    """`IdunBattle.Core.Services.BattleQuery$$CanBeResurrected(target, healType)` -- MIRROR 1:1 du
    decompile (`rnca9r7q6c`) :

        fled = UnitExtensions.HasFlag(target, 9 Fled);
        if (UnitExtensions.HasFlag(target, 0x16 PreventResurrect))          return false;
        if (!fled) {
            if (UnitExtensions.GetStat(target, 5 Health, 0 Current) > 0)    return false;
            if (!UnitExtensions.HasFlag(target, 6 Dead))                    return false;
        }
        return UnitExtensions.IsAffectedByHealType(target, healType)
               && !UnitExtensions.HasTrait(target, 0x41a PermaDeath);

    Ce n'est PAS un predicat d'`AttackQuery` mais un slot d'`IBattleQuery` (`<slot 0x31>`) ; il vit
    ici parce que ses DEUX etages terminaux (`IsAffectedByHealType`, `HasTrait`) sont ceux de ce
    module et qu'une deuxieme ecriture de `IsAffectedByHealType` serait un troisieme mirror du meme
    natif. Ses DEUX consommateurs natifs l'appellent par ce slot, avec le MEME `healType` :

      * `IdunBattle.Operations.ResurrectUnitOperation$$Execute` (gate #2, apres `IsDefeated`) --
        c'est le point de branchement porte (`runner/operations/resurrect.py`) ;
      * `IdunBattle.Entities.Behaviours.ResurrectBehaviour$$IsValidTarget` (et son jumeau
        `u003CExecuteu003Eb__9_0`, la negation passee a `ListExtensions.Remove`) -- le pre-filtre du
        behaviour DSL, porte par la feuille `Resurrect`.

    ⚠ LA BRANCHE `fled` EST UN OU, PAS UN ET : une unite qui a FUI (`UnitFlag.Fled`) est
    ressuscitable SANS etre morte ni a 0 PV -- le natif court-circuite les deux tests de mort pour
    elle. Ecrit tel quel ; aucun chemin du port ne pose `Fled` sur un vivant, donc la branche est
    inerte cote port et le rester est une MESURE, pas un oubli.

    `heal_type` est un `IdunBattle.Entities.Enum.HealType` (0 = non-mecanique, 1 = mecanique) : c'est
    lui qui separe les deux resurrections du build -- `RitesOfRestorationAbility$$ExecuteBehaviour`
    passe `0` (i2 « Only affects non-Mechanical units ») et
    `ResurrectionOrbAbility$$GetResurrectBehaviour` passe `1` (heros MECANIQUES). Le confondre
    inverserait exactement l'ensemble des cibles."""
    if target_id is None:
        return False
    tid = int(target_id)
    e = state.get_entity(tid)
    fl = e.get_component(UnitFlagsComponent) if e is not None else None
    if fl is not None and fl.has(int(UnitFlag.PreventResurrect)):
        return False
    if not (fl is not None and fl.has(int(UnitFlag.Fled))):
        hc = e.get_component(HealthComponent) if e is not None else None
        if hc is not None and hc.hp is not None and int(hc.hp) > 0:
            return False
        # `HasFlag(target, 6 Dead)` : cote port le flag `UnitFlagsComponent.DEAD` n'est pose QUE par
        # les chemins qui le mirrorent explicitement, alors que la mort d'une unite est portee par
        # `UnitComponent.alive`. On lit donc les DEUX (disjonction), sans quoi le gate refuserait
        # toute unite tuee par le pipeline de degat -- c'est-a-dire toutes celles que Rites vise.
        uc = e.get_component(UnitComponent) if e is not None else None
        dead = bool(fl is not None and fl.has(UnitFlagsComponent.DEAD)) or \
            bool(uc is not None and not uc.alive)
        if not dead:
            return False
    if not is_affected_by_heal_type(state, tid, int(heal_type)):
        return False
    return not _has_trait(state, tid, int(UnitTrait.PermaDeath))


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
