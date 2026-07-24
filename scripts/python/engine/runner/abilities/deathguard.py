"""Abilities Death Guard (namespace natif `Abilities.Active.Loki.*`, faction Nurgle/Chaos).

Module DEDIE (org faction, comme `genestealer.py`) : l'org native est 1 classe par ability
(`Abilities.Active.Loki.<X>Ability`) ; les arbres SPECIFIQUES vivent avec leur classe. RE ghidra
gqfc5mff6c (VA citees). Case-220 §1 P0-HEAL, jumeau heal 1002 CombatRestoratives cote Chaos.

Arbre `RevitalizingMalignancyAbility.ExecuteBehaviour @181200eb0` (id 1037, deathRotbone) — MIRROR
du DECOMPILE (+ `GetAllHealTargets @181201150`, `GetChaosHealTargets @181201230`,
`GetRegularHealTargets @181201280`, callback `<ExecuteBehaviour>b__0 @181218d00`) :

    AllHealTargets = Healable( UnitsWithoutTrait( 0x1a Imperial,
                                op_Addition( Friends(AdjacentUnits(caster, 1)), caster ) ) )
    regular = UnitsWithoutTrait(0x7ea Chaos, AllHealTargets)   heal Direct(var0x20)             # non-Chaos
    chaos   = UnitsWithTrait(0x7ea Chaos, AllHealTargets)      heal Direct(var0x22 + var0x20)   # Chaos (CUMUL)
    ExecuteAtomic( op_Addition( Heal(regular, ...) , Heal(chaos, ...) ) )                       # regular PUIS chaos

var0x20 = `GetVariableForLevel(config, 0x20)` = `hpToHeal` (regular) ; var0x22 =
`GetVariableForLevel(config, 0x22)` = `hpToHeal_2`. Le montant Chaos est la SOMME de DEUX vars lues
et arrondies SEPAREMENT (`iVar14 + iVar13` @181200eb0), PAS un scalaire cale ni `round((a+b)*mult)`.
La garde `Healable` (`HealableUnitsSelector`, prerequis case-220 manquant) est portee COTE MUTATION
(feuille `Heal(guard=...)`, cf. `_healable_heal_type_0`)."""
from __future__ import annotations

from typing import Optional, TYPE_CHECKING

from ...dsl.base import Const
from ...dsl.effects import ExecutionContext
from ...entities.behaviours import op_add, AtomicGroup
from ...entities.selectors import (Caster, CasterTile, AdjacentUnits, Friends, Union,
                                   UnitsWithoutTrait, UnitsWithTrait)
from ...entities.traits.unit_trait import UnitTrait
from ...entities.active_ability_type import ActiveAbilityType
from ...entities.effects.magnitude import ability_var
from ..components import StatsComponent
from .base import ActiveAbility
from .behaviours import entities_from_state, Heal, healable_heal_type_0

if TYPE_CHECKING:
    from ..state import State

ABILITY_ID = "RevitalizingMalignancy"


def _heal_amounts(state: "State", caster_id: int) -> tuple[int, int]:
    """(regular, chaos) — mirror des lectures de `ExecuteBehaviour @181200eb0` :
        iVar13 = GetVariableForLevel(config, 0x20) = `hpToHeal`   -> regular
        iVar14 = GetVariableForLevel(config, 0x22) = `hpToHeal_2`
        chaos  = iVar14 + iVar13                                  (CUMUL des DEUX vars)
    Chaque `GetVariableForLevel` est lu + arrondi SEPAREMENT (le natif bake le scaling rarete/progression
    `AbilityVariablesMultiplierPercentage` dans la config par-unite) via `ability_var` : la somme Chaos =
    round(hpToHeal*mult) + round(hpToHeal_2*mult), PAS round((hpToHeal+hpToHeal_2)*mult) (ANGLE VALIDATOR :
    ne pas fitter un scalaire ; `hpToHeal`/`hpToHeal_2` sont dans `variablesAffectedByRarityBonus`)."""
    e = state.get_entity(caster_id)
    sc = e.get_component(StatsComponent) if e is not None else None
    ctx = sc.ctx if sc is not None else None
    level = getattr(ctx, "active_ability_level", 0) if ctx is not None else 0
    mult = getattr(ctx, "ability_variables_multiplier", 100) if ctx is not None else 100
    reg = int(ability_var(ABILITY_ID, "hpToHeal", level, multiplier_pct=mult) or 0)      # var0x20 (iVar13)
    bonus = int(ability_var(ABILITY_ID, "hpToHeal_2", level, multiplier_pct=mult) or 0)  # var0x22 (iVar14)
    return reg, reg + bonus                                                              # regular, chaos = iVar14 + iVar13


def revitalizing_malignancy_tree(regular_amount: int, chaos_amount: int) -> AtomicGroup:
    """Arbre de `RevitalizingMalignancyAbility.ExecuteBehaviour @181200eb0` (MIRROR 1:1 du decompile +
    callback `b__0 @181218d00`). `AllHealTargets` = self + allies adjacents (hex 1) NON-Imperial, filtre
    `Healable` porte cote mutation (`Heal(guard=healable_heal_type_0)`). Split par trait Chaos(0x7ea) :
    non-Chaos = `regular_amount` (var0x20), Chaos = `chaos_amount` (var0x20+var0x22). `AtomicGroup`
    (`ExecuteAtomic`, id 0x1f) inline (RE #201). Ordre callback natif : Heal(regular) PUIS Heal(chaos) ;
    les deux feuilles sont pures (aucun rng) et les sets DISJOINTS -> ordre sans effet observable."""
    all_heal = UnitsWithoutTrait(
        Union(Friends(AdjacentUnits(CasterTile(), Const(1))), Caster()),
        int(UnitTrait.Imperial))                              # WithoutTrait(0x1a, Union(Friends(AdjacentUnits(self,1)), self))
    regular_sel = UnitsWithoutTrait(all_heal, int(UnitTrait.Chaos))   # regular = WithoutTrait(0x7ea)
    chaos_sel = UnitsWithTrait(all_heal, int(UnitTrait.Chaos))        # chaos   = WithTrait(0x7ea)
    regular = Heal(regular_sel, lambda entities, ectx: regular_amount, guard=healable_heal_type_0)  # Direct(var0x20)
    chaos = Heal(chaos_sel, lambda entities, ectx: chaos_amount, guard=healable_heal_type_0)        # Direct(var0x22+var0x20)
    return AtomicGroup(op_add(regular, chaos))                # ExecuteAtomic( regular + chaos )


class RevitalizingMalignancyAbility(ActiveAbility):
    """`RevitalizingMalignancyAbility.ExecuteBehaviour @181200eb0` (id 1037, deathRotbone — Death Guard).

    Heal-splitte-par-trait (jumeau Chaos de 1002 CombatRestoratives) : soigne le caster + ses allies
    adjacents (hex 1) NON-Imperial. Le montant depend du trait Chaos de la cible :
      - allie NON-Chaos : `hpToHeal[level]`                      (var0x20)
      - allie Chaos     : `hpToHeal[level] + hpToHeal_2[level]`  (var0x22 + var0x20, CUMUL)
    Garde `Healable` (HP<max ET non-mechanical) portee cote mutation (feuille `Heal(guard=...)`). Behaviour
    = arbre DSL `revitalizing_malignancy_tree` (mirror 1:1 du decompile + callback `b__0 @181218d00`).
    Deterministe (aucun rng)."""
    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.RevitalizingMalignancy)  # 1037
    ABILITY_ID = ABILITY_ID

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        # Montants lus AU CAST (mirror : le natif lit var0x20/var0x22 dans ExecuteBehaviour et les fige dans
        # le closure de l'AtomicGroup) ; l'arbre cible Caster() (pas Target()) -> target_id indifferent.
        regular_amount, chaos_amount = _heal_amounts(state, caster_id)
        ectx = ExecutionContext(state=state, rng=state.rng)
        entities = entities_from_state(state, caster_id, target_id)
        revitalizing_malignancy_tree(regular_amount, chaos_amount).execute(entities, ectx)
        heals = [p for n, p in ectx.emitted if n == "Heal"]
        return {"ability": ABILITY_ID, "caster": caster_id, "target": target_id,
                "regular_amount": regular_amount, "chaos_amount": chaos_amount,
                "heals": heals, "dsl": True}
