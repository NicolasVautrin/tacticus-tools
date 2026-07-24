"""Abilities Ultramarines (namespace natif `Abilities.Active.Loki.*`, faction Imperial/Ultramarines).

Module DEDIE (org faction, comme `deathguard.py`/`genestealer.py`) : l'org native est 1 classe par
ability (`Abilities.Active.Loki.<X>Ability`) ; les arbres SPECIFIQUES vivent avec leur classe. RE ghidra
gqfc5mff6c (VA citees). Case-220 §1 P0-HEAL.

Arbre `CombatRestorativesAbility.ExecuteBehaviour @1811cc590` (id 1002, ultraApothecary) — MIRROR du
DECOMPILE (+ `HealTargets @1811cca50`, callback `<ExecuteBehaviour>b__0 @1811e3e90`). JUMEAU IMPERIAL du
Chaos 1037 RevitalizingMalignancy (`deathguard.py`), mais AVEC DEUX DIFFERENCES STRUCTURELLES lues au
decompile (pas devinees par symetrie) :

    base        = Healable( op_Addition( Friends(AdjacentUnits(casterTile, 1)), caster ) )   # PAS d'exclusion trait
    withImperial = SelectUniqueUnits( UnitsWithTrait( base, 0x1a Imperial ) )    heal Get(var0x22)   # allies Imperial
    sans         = SelectUniqueUnits( op_Subtraction( base, withImperial ) )     heal Get(var0x20)   # tout le reste
    ExecuteAtomic( op_Addition( Heal(withImperial, ...) , Heal(sans, ...) ) )                 # withImperial PUIS sans

DIFFERENCE 1 -- PAS DE CUMUL. Le natif lit var0x22 (`GetVariableForLevel(0x22)` @1811cc590 -> +0x20) ET
var0x20 (`GetVariableForLevel(0x20)` -> +0x160) SEPAREMENT, SANS les sommer (contraste le jumeau 1037 ou
+0x160 = `iVar14 + iVar13`, CUMUL Chaos). Chaque groupe recoit UN montant simple :
  - allie IMPERIAL(0x1a) : var0x22 = `hpToHeal_2[level]`  (le PLUS gros, 5456 max)   [callback: 1er Heal]
  - allie NON-Imperial   : var0x20 = `hpToHeal[level]`    (4365 max)                 [callback: 2e Heal]
Les deux vars sont dans `variablesAffectedByRarityBonus` -> scalees par `AbilityVariablesMultiplier`
(mirror `ability_var(..., multiplier_pct=mult)`). Chaque `GetVariableForLevel` est lu+arrondi SEPAREMENT.

DIFFERENCE 2 -- PAS D'EXCLUSION DE TRAIT AU TOP. Le jumeau 1037 exclut Imperial du set entier
(`WithoutTrait(0x1a)`) -> les allies Imperial recoivent 0. Ici 1002 n'exclut RIEN : le set est
`Healable(Union(adjacent friends, self))` puis splitte Imperial / non-Imperial ; TOUS les allies adjacents
+ self (blesses, non-mechanical) sont soignes. `sans = op_Subtraction(base, withImperial)` == non-Imperial
membres de base (Xenos ET Chaos allies inclus, contrairement au 1037 qui excluait Imperial).

La garde `Healable` (`HealableUnitsSelector`, kind 4 du wrapper natif `FUN_180025220(4, ...)` applique a
base AVANT le split) est portee COTE MUTATION (feuille `Heal(guard=healable_heal_type_0)`, cf.
`behaviours/stats.py`) : Healable(base) puis split == split puis Healable-par-feuille (Healable idempotent,
distribue sur l'intersection/soustraction -> sets finaux identiques ; demonstration : withImperial cap
Healable = Imperial cap base cap Healable = Imperial cap Healable(base) ; sans cap Healable = idem).

Le trait Imperial(0x1a) est ABSENT de `gameconfig.unit().traits` (0 unite le porte) -> DERIVE de la
GrandAlliance (`GrandAlliance.GetTrait @1815647a0`) via `_grand_alliance_trait` (context.py), DEJA cable
dans `_unit_dict` (ajoute le trait d'alliance au set runner). REUTILISE tel quel (jumeau 1037)."""
from __future__ import annotations

from typing import Optional, TYPE_CHECKING

from ...dsl.base import Const
from ...dsl.effects import ExecutionContext
from ...entities.behaviours import op_add, AtomicGroup
from ...entities.selectors import (Caster, CasterTile, AdjacentUnits, Friends, Union,
                                   UnitsWithTrait, Sub, Unique)
from ...entities.traits.unit_trait import UnitTrait
from ...entities.active_ability_type import ActiveAbilityType
from ...entities.effects.magnitude import ability_var
from ..components import StatsComponent
from .base import ActiveAbility
from .behaviours import entities_from_state, Heal, healable_heal_type_0

if TYPE_CHECKING:
    from ..state import State

ABILITY_ID = "CombatRestoratives"


def _heal_amounts(state: "State", caster_id: int) -> tuple[int, int]:
    """(imperial, sans) — mirror des lectures de `ExecuteBehaviour @1811cc590` :
        var0x22 = GetVariableForLevel(config, 0x22) = `hpToHeal_2`  -> withImperial (allies Imperial)   [+0x20]
        var0x20 = GetVariableForLevel(config, 0x20) = `hpToHeal`    -> sans (non-Imperial)               [+0x160]
    AUCUNE somme (contraste 1037 ou +0x160 = iVar14 + iVar13). Chaque var est lue+arrondie SEPAREMENT via
    `ability_var` (le natif bake le scaling rarete/progression `AbilityVariablesMultiplierPercentage` dans
    la config par-unite ; les DEUX vars sont dans `variablesAffectedByRarityBonus`). ANGLE VALIDATOR : ne
    pas fitter un scalaire -- imperial et sans sont deux vars distinctes (hpToHeal_2 != hpToHeal)."""
    e = state.get_entity(caster_id)
    sc = e.get_component(StatsComponent) if e is not None else None
    ctx = sc.ctx if sc is not None else None
    level = getattr(ctx, "active_ability_level", 0) if ctx is not None else 0
    mult = getattr(ctx, "ability_variables_multiplier", 100) if ctx is not None else 100
    imperial = int(ability_var(ABILITY_ID, "hpToHeal_2", level, multiplier_pct=mult) or 0)  # var0x22 (Imperial)
    sans = int(ability_var(ABILITY_ID, "hpToHeal", level, multiplier_pct=mult) or 0)        # var0x20 (non-Imperial)
    return imperial, sans


def combat_restoratives_tree(imperial_amount: int, sans_amount: int) -> AtomicGroup:
    """Arbre de `CombatRestorativesAbility.ExecuteBehaviour @1811cc590` (MIRROR 1:1 du decompile + callback
    `b__0 @1811e3e90`). `base` = self + allies adjacents (hex 1), filtre `Healable` porte cote mutation
    (`Heal(guard=healable_heal_type_0)`). Split par trait Imperial(0x1a) : allies Imperial = `imperial_amount`
    (var0x22 = hpToHeal_2), tout le reste = `sans_amount` (var0x20 = hpToHeal). `withImperial` /`sans` sont
    chacun wrappes `SelectUniqueUnits` (dedup natif, no-op sur des sets deja uniques -> mirror fidele).
    `sans = op_Subtraction(base, withImperial)` = membres non-Imperial de base. `AtomicGroup` (`ExecuteAtomic`,
    id 0x1f). Ordre callback natif : Heal(withImperial) PUIS Heal(sans) ; feuilles pures (aucun rng) + sets
    DISJOINTS -> ordre sans effet observable (fidelite conservee)."""
    base = Union(Friends(AdjacentUnits(CasterTile(), Const(1))), Caster())    # op_Addition(Friends(AdjacentUnits(casterTile,1)), caster)
    with_imperial = Unique(UnitsWithTrait(base, int(UnitTrait.Imperial)))     # SelectUniqueUnits(UnitsWithTrait(base, 0x1a))
    sans = Unique(Sub(base, with_imperial))                                   # SelectUniqueUnits(op_Subtraction(base, withImperial))
    heal_imperial = Heal(with_imperial, lambda entities, ectx: imperial_amount,
                         guard=healable_heal_type_0)                          # Get(var0x22) = hpToHeal_2
    heal_sans = Heal(sans, lambda entities, ectx: sans_amount,
                     guard=healable_heal_type_0)                              # Get(var0x20) = hpToHeal
    return AtomicGroup(op_add(heal_imperial, heal_sans))                      # ExecuteAtomic( withImperial + sans )


class CombatRestorativesAbility(ActiveAbility):
    """`CombatRestorativesAbility.ExecuteBehaviour @1811cc590` (id 1002, ultraApothecary — Ultramarines).

    Heal-splitte-par-trait (jumeau IMPERIAL de 1037 RevitalizingMalignancy) : soigne le caster + ses allies
    adjacents (hex 1). Le montant depend du trait Imperial de la cible :
      - allie IMPERIAL(0x1a) : `hpToHeal_2[level]`  (var0x22)
      - allie NON-Imperial   : `hpToHeal[level]`    (var0x20)
    PAS de cumul (contraste 1037) ; PAS d'exclusion de trait (tous les allies adjacents + self, blesses +
    non-mechanical, sont soignes). Garde `Healable` (HP<max ET non-mechanical) portee cote mutation (feuille
    `Heal(guard=...)`). Behaviour = arbre DSL `combat_restoratives_tree` (mirror 1:1 du decompile + callback
    `b__0 @1811e3e90`). Deterministe (aucun rng)."""
    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.CombatRestoratives)  # 1002
    ABILITY_ID = ABILITY_ID

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        # Montants lus AU CAST (mirror : le natif lit var0x22/var0x20 dans ExecuteBehaviour et les fige dans
        # le closure de l'AtomicGroup) ; l'arbre cible Caster() (pas Target()) -> target_id indifferent.
        imperial_amount, sans_amount = _heal_amounts(state, caster_id)
        ectx = ExecutionContext(state=state, rng=state.rng)
        entities = entities_from_state(state, caster_id, target_id)
        combat_restoratives_tree(imperial_amount, sans_amount).execute(entities, ectx)
        heals = [p for n, p in ectx.emitted if n == "Heal"]
        return {"ability": ABILITY_ID, "caster": caster_id, "target": target_id,
                "imperial_amount": imperial_amount, "sans_amount": sans_amount,
                "heals": heals, "dsl": True}
