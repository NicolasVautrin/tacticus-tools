"""`1212 HealingBalms_Heal` -- le soin de `spaceWolfPriest` << Baldr >> (HERO Space Wolves), et son
passif porteur `HealingBalms` (`TriggeredAbilityType` 0x5de = **1502**). #966

i2 (autoritatif) : << When Baldr uses his action to heal a friendly unit, the healed unit has
+{[extraCritChance]}% Crit Chance and deals +{[extraCritDmg]} Crit Damage for {[nrOfRounds]} rounds.
At the start of its next turn, the affected unit is also healed for {[hpToHeal]} Health. Baldr can
heal friendly units even if they are at full Health. >>

## LES TROIS ARTEFACTS NATIFS DU KIT, et leur canal de port

| natif | base LUE dans `frida/classes.tsv` | canal |
|---|---|---|
| `...Triggered.Loki.HealingBalmsAbility` | `IdunBattle.Entities.Abilities.BaseTriggeredAbility` | ce module (§SWAP) |
| `...Active.Loki.HealingBalms_HealAbility` | `IdunBattle.Entities.Abilities.AActiveAbility` | ce module (`ABILITY_CLASSES`) |
| `IdunBattle.Entities.Effects.Loki.HealingBalmsEffect` | `IdunBattle.Entities.Effects.BaseEffect` | `runner/operations/triggers/loki/healing_balms.py` |

⚠ **La base se lit dans `classes.tsv`, jamais dans le namespace** : `HealingBalms_HealAbility` vit
sous `...Abilities.Active.Loki.` et dérive bien d'`AActiveAbility` -- mais le voisinage de nommage
`Active.Loki.SummaryExecutionAddBaseEffectAbility` (dont ce module partage un corps, cf. §SWAP) est
un `BaseTriggeredAbility`. Le namespace ne dit RIEN de la face.

## §SWAP -- `...HealingBalmsAbility$$CreateBehaviour`, et pourquoi il n'a PAS d'entrée de registre

`$$CreateTrigger` de cette classe est un corps **FONDU par l'ICF** : il n'a AUCUN symbole propre
(absent de `ghidra/functions.tsv` ET de `frida/methods.tsv`). Il a été lu au **bloc `methodPointers`
du PE**, où les classes se suivent en ordre alphabétique par triplets `(CreateTrigger,
CreateBehaviour, .ctor)` -- le triplet de `HealingBalmsAbility` est encadré par ceux de
`HaywireMineSteppableAbility` et de `HeadwoppasKillchoppaAbility`, et son slot `CreateTrigger`
pointe sur le corps que possède `...Active.Loki.SummaryExecutionAddBaseEffectAbility$$CreateTrigger` :

    return <DSLTriggers+0x30>      # = On(0x21 = AbilityInit) & <YesTrigger> & get_OwnerIsActor

C'est le trigger d'INIT partagé que `DSLTriggers$$InitializeShared` met en cache -- le MÊME que
`HuntersBeyondDeathAbility` (#952), `SummaryExecution` (#955) et `EnmityForTheUnworthy` (#948).

    $$CreateBehaviour =  AddFlag(Owner@DSLSelectors+0x30, 0x17 = UnitFlag.CanHealFullHealthUnits)
              op_Addition RemoveActiveAbility(Owner@+0x30, 0x12 = ActiveAbilityType.Heal)
              op_Addition AddActiveAbility(Owner@+0x30, 0x4bc = ActiveAbilityType.HealingBalms_Heal,
                                           abilityState)

⚠ **CE SWAP N'A PAS D'ENTRÉE DE REGISTRE CÔTÉ PORT, ET C'EST UNE MESURE, PAS UN OUBLI.** Le substrat
le livre DÉJÀ fait : le runner natif exécute `AbilityInit` au spawn, donc `decisionView` publie sur
Baldr l'active `1212` et PAS `18` -- c'est exactement ce que `#27-4d` a confronté live (la face
DÉCISION de 1212 atteint `_heal_candidates` sans qu'aucun swap soit porté). Le rejouer côté port
serait un no-op au mieux, une double-pose au pire.

⚠ **LE `AddFlag(CanHealFullHealthUnits)` EST DANS LE MÊME CAS, ET C'EST CE PARAGRAPHE QUI ÉTAIT
FAUX (#982-r5).** Il affirmait « le port n'a pas de substrat `UnitFlag` persistant » et « aucun
consommateur porté ne le lit » : les DEUX sont RÉFUTÉS, mesurés (build `rnca9r7q6c`, `MC1_67`,
seed 777, `spaceWolfPriest` injecté au catalogue). Le substrat EXISTE
(`runner/components.UnitFlagsComponent`, seedé par `runner/snapshot._load_unit_flags` depuis
`combatSnapshot.units[].unitFlags` -- relevé `[23]` sur Baldr, `[]` sur les trois autres unités), et
le consommateur porté est `runner/abilities/attack_query.entity_can_be_healed` (disjonction
`HasFlag(caster, 0x17)`), atteint à l'EXÉCUTION par
`IdunBattle.Operations.HealUnitOperation$$Execute` -- donc par la feuille `Heal` de l'arbre §ACTIVE
ci-dessous. Sur une cible à PLEINS PV le port rend `True` pour `caster = Baldr` et `False` pour tout
autre caster : la règle mord, avec témoin.

Ce qui reste vrai : `...HealingBalms_HealAbility$$GetDynamicInvalidTargetReason` ne consulte PAS ce
gate. Le « même à PV pleins » a donc DEUX étages natifs -- l'ABSENCE du gate au CIBLAGE **et** le
flag au GATE D'EXÉCUTION -- pas un seul. Et le lecteur n'est pas le `18 Heal` générique : c'est
`IdunBattle.Core.Services.AttackQuery$$EntityCanBeHealed`. Le résidu #931-r1 (le `18 Heal`
générique hors `ABILITY_CLASSES`) reste ouvert, mais il n'a rien à voir avec ce flag.
Cliquet : `tests/engine/test_982r5_can_heal_full_health_offline.py`.

## §ACTIVE -- `...HealingBalms_HealAbility$$ExecuteBehaviour`, MIRROR feuille par feuille

    nrOfRounds = DSLFormulas.ConfigConst(0x5de = TriggeredAbilityType.HealingBalms,
                                         Owner@DSLSelectors+0x30,
                                         0x45 = AbilityConstantType.nrOfRounds)
    b1 = RemoveEffect(Target@+0x60, Nullable(0x5df = HealingBalms_ExtraCritDamage), null)
           op_Addition RemoveEffect(Target@+0x60, Nullable(0x5e0 = HealingBalms_ExtraCritChance), null)
    b2 = AddDynamicStatModifierEffect(Target@+0x60, source = Owner@+0x30, 0x5df,
                                      statType = 10 = CriticalDamage, AbilityStateReference,
                                      turns = TurnsFromRounds(nrOfRounds), isHidden = false)
           op_Addition AddDynamicStatModifierEffect(Target@+0x60, Owner@+0x30, 0x5e0,
                                      statType = 9 = CriticalChance, ..., TurnsFromRounds(nrOfRounds))
    b3 = AddEffect(0x5e4 = HealingBalms, AbilityStateReference, source = Caster@+0x48,
                   targets = Target@+0x60, options = default -> ref)
    b4 = Heal(healer = Caster@+0x48, selector = Target@+0x60,
              amount = Common.HealAbility.HealAmount(dsl),
              options = HealBehaviourOptions.ForHeal(AbilityOrEffect(<ref de b3>)))
    return Execute( ((b1 op_Addition b2) op_Addition b3) op_Addition b4 )

Trois choses que la STRUCTURE dit et que l'i2 seul ne dirait pas :

* **le `RemoveEffect` d'abord** : re-soigner la même cible RÉ-ARME les deux buffs au lieu de les
  empiler (durée remise à `nrOfRounds`) -- cf. `entities/effects/loki/healing_balms.py` ;
* **le SOIN est INCONDITIONNEL** : il est le dernier terme d'un `op_Addition` plat, il n'y a AUCUN
  `If` dans ce corps (contraste `TwistedScience_HealAbility`, dont le bloc de buffs est gaté) --
  donc les buffs partent AUSSI quand la cible est le caster lui-même ;
* **la magnitude du soin vient de l'ARME, pas du gameconfig** : `Common.HealAbility$$HealAmount` =
  `Multiply(StatAmount(Caster, ATTACK, Current), Max(WeaponHighestHits(Caster), Get(1)))`. Les
  variables `extraCritChance`/`extraCritDmg`/`hpToHeal` de la config du PASSIF alimentent les BUFFS
  et le soin RETARDÉ, jamais ce soin-ci.

`$$GetDynamicInvalidTargetReason` -- MIRROR verbatim, corps ENTIER :

    if (!UnitExtensions.IsAffectedByHealType(target, 0 = NonMechanical))  return 0x100;
    return 0;

⚠ **C'est un corps STRICTEMENT plus court que celui de `TwistedScience_HealAbility`**, et c'est là
que vit le « even if they are at full Health » : aucune consultation d'`AttackQuery.<slot 0x11>`
(`EntityCanBeHealed`), donc aucun refus à PV pleins. Recopier le voisin de forme aurait fermé le
ciblage sur exactement le cas que l'ability existe pour ouvrir.

DOCTRINE #149 : `ExecuteBehaviour` est un VRAI arbre DSL (feuilles `RemoveEffect` /
`AddDynamicStatModifierEffect` / `AddEffect` / `Heal`, qui appellent les Operations impératives) ;
`GetDynamicInvalidTargetReason` est un gate impératif, mirroré tel quel.

ASCII only.
"""
from __future__ import annotations

from typing import Optional, TYPE_CHECKING

from ....dsl.effects import AbilityBehaviour, ExecutionContext
from ....entities.ability_constant_type import AbilityConstantType
from ....entities.active_ability_type import ActiveAbilityType
from ....entities.effect_type import EffectType
from ....entities.behaviours import op_add
from ....entities.effects.magnitude import ability_var
from ....entities.selectors.accessors import Owner, Target
from ....entities.stats import StatType
from ....predict import heal_amount_weapon              # `Common.HealAbility$$HealAmount`
from ...components import StatsComponent
from ..attack_query import is_affected_by_heal_type
from ..base import ActiveAbility
from ..behaviours.context import entities_from_state
from ..behaviours.effects import AddDynamicStatModifierEffect, AddEffect, RemoveEffect
from ..behaviours.stats import Heal
from ..targeting import (RANGE_ADJACENT_IF_MELEE_CASTER, RANGED_BOOL_IF_RANGED_CASTER,
                         TargetingOptions)
from ..targeting_rule import TargetingRule as TR

if TYPE_CHECKING:                                        # pragma: no cover
    from ...state import State

#: Nom gameconfig du PASSIF -- c'est SA config que `ConfigConst`/`ConfigVar` indexent. L'active 1212
#: n'a AUCUNE entrée `abilities.*` (elle est SUBSTITUÉE au `18 Heal`), exactement comme 1167.
HEALING_BALMS = "HealingBalms"

EXTRA_CRIT_DAMAGE = int(EffectType.HealingBalms_ExtraCritDamage)     # 0x5df = 1503
EXTRA_CRIT_CHANCE = int(EffectType.HealingBalms_ExtraCritChance)     # 0x5e0 = 1504
HEALING_BALMS_EFFECT = int(EffectType.HealingBalms)                  # 0x5e4 = 1508

#: `IdunBattle.Entities.Behaviours.HealBehaviourOptions$$ForHeal` = `(scope 0, removeEffects 1)`.
#: LU aux xrefs (#576) -- ce n'est PAS `ForRegenerate` `(1, 0)`, et les deux ne sont pas
#: interchangeables : `scope 1` armerait le cap de groupe `GetGroupUnitHealLimit` de `PredictHeal`.
FOR_HEAL_SCOPE = 0
FOR_HEAL_REMOVE_EFFECTS = True


def healing_balms_nr_of_rounds(state: "State", caster_id: int) -> Optional[int]:
    """`DSLFormulas.ConfigConst(TriggeredAbilityType.HealingBalms, Owner, AbilityConstantType.nrOfRounds)`.

    Une CONSTANTE d'ability (`constants.nrOfRounds`), donc SANS niveau ni multiplicateur de rareté --
    contrairement aux `variables` du même bloc. `None` si absente : le natif passerait alors
    `TurnsFromRounds(<formule vide>)` et `AddEffectOperation` retomberait sur
    `Effect$$DefaultAmountOfRounds`, ce que `duration_rounds=None` reproduit exactement."""
    v = ability_var(HEALING_BALMS, AbilityConstantType.nrOfRounds.name, is_constant=True)
    return None if v is None else int(v)


def healing_balms_heal_amount(state: "State", caster_id: int) -> int:
    """`IdunBattleLogic.Entities.Abilities.Active.Common.HealAbility$$HealAmount(dsl)` =

        Multiply( StatAmount(Caster@DSLSelectors+0x48, 0 = ATTACK, 0 = Current),
                  Max( WeaponHighestHits(Caster@+0x48), Get(1) ) )

    COLLAPSE V assumé, MÊME arbitrage que `genestealer.py::twisted_science_heal_amount` (#931) : les
    trois feuilles se résolvent en deux lectures du `UnitContext` du caster, et le produit vit déjà
    dans `engine.predict.heal_amount_weapon` -- LA seule lecture de cette formule dans le moteur,
    déjà confrontée live côté DÉCISION. On l'appelle, on ne la duplique pas. Sans `ctx` -> `0`."""
    e = state.get_entity(int(caster_id)) if caster_id is not None else None
    sc = e.get_component(StatsComponent) if e is not None else None
    ctx = getattr(sc, "ctx", None)
    if ctx is None:
        return 0
    return int(heal_amount_weapon(int(ctx.stat(StatType.ATTACK)),
                                  int(getattr(ctx, "normal_weapon_hits", 1) or 1)))


def healing_balms_heal_tree(state: "State", caster_id: int) -> AbilityBehaviour:
    """Arbre de `...HealingBalms_HealAbility$$ExecuteBehaviour` -- MIRROR, feuille par feuille et
    dans SON ordre (cf. l'en-tête de module pour le décompilé).

    `turns = TurnsFromRounds(nrOfRounds)` est FOLDÉ en scalaire : `ConfigConst` est résolue par le
    natif AU MOMENT DE CONSTRUIRE le behaviour (l'appel est dans `ExecuteBehaviour` lui-même), pas à
    l'exécution -- même collapse que `tough_to_kill_regen_tree`.

    ⚠ `RemoveEffect(selector, Nullable(effectType), null)` porte sur la CIBLE, PAS sur le caster :
    l'overload natif est `(selector, effectType, replaceableEffectType)`, dont le 1er argument est
    `Target@DSLSelectors+0x60`. Le lire comme un self-clean laisserait deux instances empilées."""
    rounds = healing_balms_nr_of_rounds(state, caster_id)
    # `RemoveEffect(Target, Nullable(<type>), null)` x2, joints par `op_Addition`.
    purge = op_add(RemoveEffect(EXTRA_CRIT_DAMAGE, Target()),
                   RemoveEffect(EXTRA_CRIT_CHANCE, Target()))
    # `AddDynamicStatModifierEffect(targets = Target, source = Owner, ...)` -- le couple
    # (+0x58 source, +0x60 targets) tranche QUI porte : la CIBLE porte, Baldr n'est que la source.
    buffs = op_add(
        AddDynamicStatModifierEffect(Target(), Owner(), EXTRA_CRIT_DAMAGE,
                                     int(StatType.CRIT_DAMAGE),
                                     name=EffectType.HealingBalms_ExtraCritDamage.name,
                                     duration_rounds=rounds),
        AddDynamicStatModifierEffect(Target(), Owner(), EXTRA_CRIT_CHANCE,
                                     int(StatType.CRIT_CHANCE),
                                     name=EffectType.HealingBalms_ExtraCritChance.name,
                                     duration_rounds=rounds))
    # `AddEffect(0x5e4, AbilityStateReference, source = Caster@+0x48, targets = Target@+0x60)` --
    # le MARQUEUR du soin RETARDÉ. `options = default(0)` -> aucun override de durée, donc
    # `Effect$$DefaultAmountOfRounds`. `scale_from_source=True` = l'`AbilityStateReference` natif :
    # le `ConfigVar(hpToHeal)` du trigger se lira au niveau/multiplicateur de BALDR.
    # ⚠ Le slot SOURCE natif est `Caster@DSLSelectors+0x48`, pas `Owner@+0x30` -- ÉCART DE FORME
    # NOMMÉ : le port laisse `source_ref` à son défaut (le caster de l'exécution), et les deux
    # coïncident sur un cast d'ACTIVE (le caster EST le porteur de l'ability). Ils divergeraient sur
    # une exécution déléguée, régime qui n'existe pas pour 1212.
    marker = AddEffect(HEALING_BALMS_EFFECT, EffectType.HealingBalms.name, Target(),
                       duration_rounds=None, scale_from_source=True)
    # `Heal(healer = Caster@+0x48, selector = Target@+0x60, HealAmount(dsl), ForHeal(<ref>))`.
    heal = Heal(Target(), healing_balms_heal_amount(state, caster_id), guard=None,
                scope=FOR_HEAL_SCOPE, remove_effects=FOR_HEAL_REMOVE_EFFECTS)
    return op_add(op_add(op_add(purge, buffs), marker), heal)


class HealingBalms_HealAbility(ActiveAbility):
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.HealingBalms_HealAbility`
    (`ActiveAbilityType.HealingBalms_Heal` = 0x4bc = **1212**) -- le soin de `spaceWolfPriest`.

    Cette ability n'est PAS dans le kit gameconfig de l'unité : le passif `HealingBalms` (1502) la
    SUBSTITUE au `18 Heal` que le trait `Healer` accorde (§SWAP de l'en-tête). Elle n'a donc AUCUNE
    entrée `units.abilities` -> `ABILITY_ID = None`, comme `TwistedScience_HealAbility` (1167) et
    `RepairAbility` (28), et pour la même raison ; ses trois variables (`extraCritChance`,
    `extraCritDmg`, `hpToHeal`) et sa constante (`nrOfRounds`) vivent dans la config du PASSIF.

    ⚠ CE QUE CETTE ENTRÉE AU REGISTRE NE FAIT PAS : porter le `18 Heal` GÉNÉRIQUE, qui reste hors
    d'`ABILITY_CLASSES` -- résidu #931-r1, inchangé."""
    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.HealingBalms_Heal)      # 0x4bc = 1212
    ABILITY_ID = None

    # `...HealingBalms_HealAbility$$.ctor` -- FORME "COPIE STATIQUE + SEPT ARGUMENTS", lue au
    # décompilé et non recopiée d'un voisin :
    #
    #   puVar1 = *(Il2CppClass<TargetingRange>+0xb8)          # -> static_fields
    #   local_68/uStack_60/local_58 = puVar1[0..2]            # 3 qwords = LE PREMIER `TargetingRange`
    #   TargetingOptions..ctor(&opts, 0, &local_68, 2, 0x8402, 0, 0)
    #   AActiveAbility..ctor(this, &opts, 2)
    #
    #     isSelfCasting    = 0
    #     range            = `TargetingRange` statics+0x00 = RANGE_ADJACENT_IF_MELEE_CASTER
    #                        (`onlyAdjacent = 3 = IfNotRangedCaster`, deux qwords nuls) -- LU dans
    #                        `IdunBattle.Core.Services.TargetingRange$$.cctor`. Le `+0xb8` du
    #                        décompilé est l'offset `static_fields` d'`Il2CppClass`, PAS un indice
    #                        dans la table : le range est bien le PREMIER statique, celui-là même
    #                        que prend `TwistedScience_HealAbility`.
    #     forceMeleeTarget = 2 = RangedBool.IfRangedCaster
    #     rules            = 0x8402  (littéral DIRECT : ni preset combiné, ni masque de `cctor`)
    #   puis `AActiveAbility..ctor(this, &opts, 2)` -> `AbilityAttackType.Others`.
    #
    # Décomposition du masque (`IdunBattle.Core.Services.TargetingRule`, bit à bit, RESTE = 0) :
    #     0x0002  TargetMatchesDynamicRule  -> le refus réel vit dans la règle DYNAMIQUE ci-dessous
    #     0x0400  TargetIsFriendly          -> une cible ENNEMIE est refusée par le masque STATIQUE
    #                                          (d'où l'absence de test `IsEnemy` dans la dynamique)
    #     0x8000  CasterIsPossibleTarget    -> Baldr PEUT se cibler lui-même, et l'arbre ne le gate
    #                                          pas (contraste `!OwnerIsTarget` de TwistedScience)
    # Seconde source concordante : `docs/rl/case-302-4/tile-target-population.tsv` ligne 1212
    # (`measured`, `literal`, `0x8402`).
    TARGETING_OPTIONS = TargetingOptions(
        rules=(TR.TargetMatchesDynamicRule | TR.TargetIsFriendly | TR.CasterIsPossibleTarget),
        self_cast=False, range=RANGE_ADJACENT_IF_MELEE_CASTER,
        force_melee_target=RANGED_BOOL_IF_RANGED_CASTER)

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        if target_id is None:
            return None
        ents = entities_from_state(state, caster_id, int(target_id))
        ectx = ExecutionContext(state=state, rng=state.rng)
        healing_balms_heal_tree(state, caster_id).execute(ents, ectx)
        posed = [{"target": p.get("target"), "effect_type": p.get("effect_type"),
                  "placed": p.get("placed")}
                 for n, p in ectx.emitted if n in ("AddEffect", "AddDynamicStatModifierEffect")]
        healed = next((p for n, p in ectx.emitted if n == "Heal"), None)
        return {"ability": "HealingBalms_Heal", "caster": caster_id, "target": target_id,
                "nr_of_rounds": healing_balms_nr_of_rounds(state, caster_id),
                "effects": posed, "heal": healed, "dsl": True}

    def get_dynamic_invalid_target_reason(self, state: "State", caster_id: int,
                                          target_id: Optional[int]) -> int:
        """`...HealingBalms_HealAbility$$GetDynamicInvalidTargetReason` -- MIRROR verbatim, et le
        corps natif s'arrête là :

            if (!UnitExtensions.IsAffectedByHealType(target, 0 = NonMechanical))  return 0x100;
            return 0;

        `0x100` = `TargetingRule.TargetMatchesDynamicRule`-échoué tel que le natif le rend (même
        littéral que `TwistedScience_HealAbility`). ⚠ AUCUN appel à `AttackQuery.EntityCanBeHealed`
        ICI, et c'est le PREMIER des DEUX étages du « can heal friendly units even if they are at
        full Health » de l'i2 : au CIBLAGE, il vient de l'ABSENCE du gate. Le SECOND est à
        l'EXÉCUTION -- la feuille `Heal` passe par `IdunBattle.Operations.HealUnitOperation$$Execute`,
        dont le gate en tête EST `EntityCanBeHealed`, et là c'est bien le flag
        `CanHealFullHealthUnits` posé par le passif (mesuré `unitFlags = [23]` sur Baldr, #982-r5)
        qui rend éligible une cible pleine. N'en lire qu'un seul est exactement ce qui a produit le
        verdict faux de #966-r2."""
        if target_id is None:
            return 0
        # `IsAffectedByHealType(target, 0)` -- le `0` est le littéral du call-site (`HealType`
        # NonMechanical), le MÊME que celui de `TwistedScience_HealAbility`.
        return 0 if is_affected_by_heal_type(state, int(target_id), 0) else 0x100
