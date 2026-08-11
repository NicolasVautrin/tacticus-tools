"""#951 -- `TrophyTaker` (`TriggeredAbilityType.TrophyTaker` = 1229), passif de `worldExecutions`
(« Tarvakh »). Face TRIGGER : la +CHANCE DE CRIT, re-ecrite a chaque unite vaincue.

L'autre face (le +degat et le +degat de crit contre les cibles entamees) vit dans
`engine/entities/effects/loki/trophy_taker.py` -- ce sont deux `EffectBonus` calc-time, pas un
etat, donc pas un trigger. La RE complete des deux faces est en tete de ce fichier-la.

================================================================================================
RE (decompile ghidra, build `rnca9r7q6c`) -- surcharges tranchees a l'ENCODAGE (`probe_951`)
================================================================================================

## 1. `...TrophyTakerAbility$$CreateTrigger` -- une DISJONCTION, et c'est ce qui donne DEUX faces

    return   <DSLTriggers+0x30>
           | ( On(EventTriggerType.UnitDefeated = 0x36, ownerNeedsToBeAlive: true)
               & get_OwnerIsActor )

`<DSLTriggers+0x30>` n'est pas un litteral : c'est un champ que
`IdunBattleLogic.Entities.DSLTriggers$$InitializeShared` construit une fois --
`On(EventTriggerType.AbilityInit = 0x21) & <+0x70> & get_OwnerIsActor`, le trigger d'INIT que
partagent tous les passifs de sa base. La disjonction fait donc entrer `CreateBehaviour` par DEUX
portes, et le behaviour les DISTINGUE sur son argument `triggerType` (§2).

## 2. `...TrophyTakerAbility$$CreateBehaviour(abilityState, triggerType)`

    if (triggerType == EventTriggerType.UnitDefeated)
        return AddOrUpdateStaticStatModifierEffect(
                   targets:    Owner@DSLSelectors+0x30,
                   effectType: EffectType.TrophyTaker_ExtraCritChance = 0x508,
                   statType:   StatType.CriticalChance = 9,
                   amount:     Multiply( ConfigVar(AbilityVariableType.extraCritChance = 0x41,
                                                   abilityState, config),
                                         GetCritChanceMultiplier() ),
                   turns:      null,
                   isHidden:   false )
    else
        return AddEffect(EffectType.TrophyTaker_ExtraCritDamage = 0x509,
                         AbilityStateReference, targets: Owner@+0x30, turns: Nullable<int> VIDE)

    ...$$GetCritChanceMultiplier
        Count( NormalUnits( UnitsDefeatedBy(Owner@+0x30), UnitSelectionType.Any = 0 ) )

`turns = null` et `isHidden = false` sont LUS aux octets (`xor ebx,ebx` puis `[rsp+0x28] = rbx`
et `[rsp+0x30] = bl`), pas devines : le stat-mod est PERMANENT.

## 3. Les quatre lectures qui ne se devinent pas

1. **`UnitsDefeatedBy` prend l'UNION des deux listes du tueur**
   (`ActorStatisticsComponent` @+0xa8 melee ET @+0xb0), pas seulement la melee -- le selecteur
   melee-seul est une AUTRE factory (`$$UnitsDefeatedByMeleeAttack`). Un porteur qui tue au tir
   compte donc pareil.
2. **`NormalUnits`** = `!HasTrait(Object = 0xd) && !HasTrait(Steppable = 0x1b)`
   (`UnitExtensions$$IsNormalUnit`) : un decoy `Steppable` ecrase ou un objet de plateau detruit
   NE COMPTE PAS. C'est le seul filtre -- ni camp, ni `Hero`, ni liveness.
3. **`AddOrUpdateStaticStatModifierEffect` RE-ECRIT, il n'accumule pas.** Son corps natif est
   `If( NOT AmountIsEqual(amount, CurrentStatModifierAmount(targets, effectType, statType)),
   RemoveEffect(targets, effectType) & AddStaticStatModifierEffect(...) )` : la valeur est
   `extraCritChance x N`, RECALCULEE, jamais `+= extraCritChance`. Porter un cumul donnerait
   `N(N+1)/2` au lieu de `N`.
4. **L'ORDRE avec `RegisterDefeatedUnit` est LOAD-BEARING.** Le natif inscrit la victime a
   `KillUnitOperation$$Execute+0x8b9`, et ne publie `On(UnitDefeated)` qu'a +0xeac : quand ce
   trigger recompte, la victime COURANTE est deja dans la liste. Le port pose l'inscription au
   meme endroit (`operations/damage.py`, juste apres `KilledThisTurn = true`).

## 4. Rarete

`variablesAffectedByRarityBonus == ["extraDmg", "extraCritDmg"]` -- `extraCritChance` n'y est PAS.
`ability_var(multiplier_pct=...)` ne l'applique donc qu'aux deux autres (cf. la face EFFET) ;
ici le multiplicateur est passe quand meme, et c'est `ability_var` qui l'ignore pour cette cle --
le foyer de la regle est le gameconfig, pas ce site.
"""
from __future__ import annotations

from typing import Optional

from ....state import State
from ....components import UnitComponent
from ....abilities.behaviours.context import entities_from_state
from ....abilities.behaviours.effects import add_or_update_static_stat_modifier_effect
from .....dsl.base import Const
from .....dsl.effects import ExecutionContext
from .....dsl.event_trigger_type import EventTriggerType
from .....entities.effect_type import EffectType
from .....entities.effects.magnitude import ability_var
from .....entities.formulas import Count, Multiply
from .....entities.selectors.tiles import Caster
from .....entities.selectors.units import NormalUnits, UnitsDefeatedBy
from .....entities.stats import StatType
from .....entities.unit_selection_type import UnitSelectionType
from .....entities.triggered_ability_type import TriggeredAbilityType
from ..base import TriggeredAbility, TriggerEvent, triggered_ability_state

ABILITY_ID = "TrophyTaker"
TROPHY_TAKER = int(TriggeredAbilityType.TrophyTaker)                      # 0x4cd = 1229
EXTRA_CRIT_CHANCE_EFFECT = int(EffectType.TrophyTaker_ExtraCritChance)    # 0x508 = 1288
EXTRA_CRIT_CHANCE_EFFECT_NAME = EffectType.TrophyTaker_ExtraCritChance.name
VAR_EXTRA_CRIT_CHANCE = "extraCritChance"                                 # `AbilityVariableType` 0x41

#: `On(0x36, ownerNeedsToBeAlive: true)` -- le second bras de la disjonction du `CreateTrigger`.
_ON_UNIT_DEFEATED = int(EventTriggerType.UnitDefeated)                    # 0x36 = 54


def trophy_taker_crit_chance_multiplier_tree():
    """`...TrophyTakerAbility$$GetCritChanceMultiplier` = `Count(NormalUnits(UnitsDefeatedBy(
    Owner@+0x30), UnitSelectionType.Any))` -- arbre DSL, pas un compteur imperatif : c'est ce qui
    fait que le filtre `Object`/`Steppable` EMERGE du noeud `NormalUnits` deja porte au lieu d'etre
    recabler ici. `Caster()` = `Owner@+0x30` (pour un `BaseTriggeredAbility`, owner == caster --
    cf. la docstring d'`entities_from_state`)."""
    return Count(NormalUnits(UnitsDefeatedBy(Caster()), int(UnitSelectionType.Any)))


def trophy_taker_crit_chance_tree(extra_crit_chance: int):
    """Le behaviour de la branche `triggerType == UnitDefeated` :
    `AddOrUpdateStaticStatModifierEffect(Owner, 0x508, CriticalChance, Multiply(ConfigVar(
    extraCritChance), GetCritChanceMultiplier()), turns: null, isHidden: false)`.

    `extra_crit_chance` est passe par l'appelant (mirror du `ConfigVar` -- meme geste que
    `blacklegion.daemonic_ordnance`, dont le `Multiply` a lui aussi un facteur de config resolu en
    amont et un facteur COMPTEUR reste en noeud DSL). `turns` n'est pas passe : la factory du port
    ne pose pas de duree, ce qui EST le `turns = null` natif."""
    return add_or_update_static_stat_modifier_effect(
        Caster(), EXTRA_CRIT_CHANCE_EFFECT, int(StatType.CRIT_CHANCE),
        Multiply(Const(int(extra_crit_chance)), trophy_taker_crit_chance_multiplier_tree()),
        name=EXTRA_CRIT_CHANCE_EFFECT_NAME)


class TrophyTakerOnUnitDefeatedAbility(TriggeredAbility):
    """`On(UnitDefeated) & get_OwnerIsActor` -> re-ecriture du stat-mod de chance de critique.

    Lisible : chaque unite NORMALE que Tarvakh abat lui donne `extraCritChance` points de chance de
    critique de plus, pour le reste de la bataille."""

    event_id = _ON_UNIT_DEFEATED
    TRIGGERED_ABILITY_ID = TROPHY_TAKER

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        """`get_OwnerIsActor` -- le SEUL conjoint non-`On` du bras. Le gate `ownerNeedsToBeAlive`
        du `On(...)` est deja porte par le dispatch.

        ⚠ AUCUN gate de camp, AUCUN gate sur la nature de la victime ICI : le filtre
        `Object`/`Steppable` vit dans le SELECTEUR (`NormalUnits`), donc il s'applique au COMPTE,
        pas au declenchement. Un porteur qui ecrase un decoy re-ecrit bien son stat-mod -- a la
        MEME valeur, puisque le decoy ne compte pas. Le natif fait exactement cela, et la
        difference est observable : un `matches` qui filtrerait la victime ne re-ecrirait pas."""
        return ev.actor_id is not None and int(ev.actor_id) == int(self.owner_id)

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        lvl, mult = triggered_ability_state(state, int(self.owner_id), ABILITY_ID)
        # `ConfigVar(0x41 = extraCritChance, abilityState, config)`. `lvl is None` = l'ability n'est
        # pas montee sur cette unite -> variable a 0 -> `Multiply` nul -> la factory RE-ECRIT a 0,
        # ce qui est ce que ferait le natif avec une config absente. `extraCritChance` n'est PAS
        # rarity-scale (cf. l'en-tete) ; `ability_var` le sait par le gameconfig.
        v = ability_var(ABILITY_ID, VAR_EXTRA_CRIT_CHANCE, lvl, multiplier_pct=mult)
        entities = entities_from_state(state, self.owner_id, ev.target_id, actor_id=ev.actor_id)
        ectx = ExecutionContext(state=state, rng=state.rng)
        trophy_taker_crit_chance_tree(int(v or 0)).execute(entities, ectx)
        poses = [p for (n, p) in ectx.emitted
                 if n in ("AddStaticStatModifierEffect", "AddEffect", "RemoveEffect")]
        if not poses:
            # La factory est un `If(NOT AmountIsEqual(...))` : rien n'est emis quand la valeur
            # COURANTE du stat-mod est deja la bonne. Ce n'est PAS un echec -- c'est le no-op natif.
            return None
        e = state.get_entity(int(self.owner_id))
        uc = e.get_component(UnitComponent) if e is not None else None
        return {"passive": ABILITY_ID, "owner": int(self.owner_id),
                "victim": (int(ev.target_id) if ev.target_id is not None else None),
                "effect": EXTRA_CRIT_CHANCE_EFFECT,
                "defeated": (len(uc.defeated_units) if uc is not None else None),
                "extra_crit_chance": int(v or 0), "dsl": True}
