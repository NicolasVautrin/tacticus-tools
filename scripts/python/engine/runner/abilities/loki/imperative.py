"""DoctrinaImperatives (id 1118, Tan Gi'da / admecMarshall) — active TOGGLE, namespace natif
`Abilities.Active.Loki`. Cf. `loki/__init__.py`.

RE (build gqfc5mff6c) `DoctrinaImperativesAbility.ExecuteBehaviour @1811d4d20` (DECOMPILE MIRROR) :

    If( HasEffect(caster@+0x148, 0x4df=1247 Protector, domain 6),
        THEN = op_Addition( AddEffect(0x4e0=1248 Conqueror, src=AbilityStateReference, caster),
                            RemoveEffect(caster, Nullable(0x4df=1247)) ),
        ELSE = op_Addition( AddDynamicStatModifierEffectToOwner(0x4df=1247 Protector, stat=0x10=16 FixedArmor),
                            RemoveEffect(caster, Nullable(0x4e0=1248)) ) )

Le TOGGLE est deterministe (pas un choix d'IA) : si Protector present -> bascule Conqueror ; sinon -> Protector.
L'etat "Imperative courant" = quel des 2 effets (1247/1248) est present sur le caster (lu via HasEffect ;
pas de composant dedie). Etat initial = Protector, pose par `DoctrinaImperatives_SetStart(1201)` en debut de
bataille (GROUND-TRUTH live : Tan Gi'da a 1247 avant tout cast).

Le predicat `If(HasEffect(...))` (kind T) est COLLAPSE imperativement (lecture d'etat `state.effects.has_effect`,
doctrine slice-18/19/24 : les predicats/selecteurs S/T se replient, seule l'ossature E reste feuilles DSL) ;
les DEUX branches routent par les feuilles DSL portees `AddEffect`/`RemoveEffect` (self-cast : selecteur
`Caster()`). Increment A : Protector = stat-mod SELF +FixedArmor (materialise) ; Conqueror = present-inerte
(contribution +dmg = increment C). Increment B (FAIT) : portee aura Protector +FixedArmor aux amis Mechanical
adjacents (canal `create_aura_fixed_armor_bonus_for_defense`, foyer runner `defender_fixed_armor`, self auto-exclu).

DUREE : le decompile passe `0` (aucun `TurnsFromRounds`) aux deux `AddEffect` -> `DefaultAmountOfRounds`
(@181559ff0 : null pour 1247/1248) -> fallback 1 round (`AddEffectOperation`). La PERSISTANCE de la stance
(l'Imperative doit durer jusqu'au prochain toggle) au-dela d'1 round = detail non tranche (n'affecte pas la
validation single-turn ; flagge, cf. le `3` de FUN_180002560 dans le helper `AddDynamicStatModifierEffectToOwner`).
"""
from __future__ import annotations

from typing import Optional, TYPE_CHECKING

from ..base import ActiveAbility
from ....entities.active_ability_type import ActiveAbilityType
from ....entities.effect_type import EffectType
from ....dsl.effects import ExecutionContext
from ....entities.selectors import Caster
from ..behaviours import AddEffect, RemoveEffect, entities_from_state

if TYPE_CHECKING:
    from ...state import State

PROTECTOR = int(EffectType.ProtectorImperative)   # 1247 (0x4df)
CONQUEROR = int(EffectType.ConquerorImperative)    # 1248 (0x4e0)


class DoctrinaImperativesAbility(ActiveAbility):
    """`DoctrinaImperativesAbility` (1118) — toggle Protector <-> Conqueror sur le caster (self-cast).
    Mirror du `If(HasEffect(1247), add 1248 + remove 1247, else add 1247 + remove 1248)` @1811d4d20."""
    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.DoctrinaImperatives)   # 1118

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        eff = state.effects
        has_protector = eff is not None and eff.has_effect(caster_id, effect_type=PROTECTOR)
        # self-cast : le caster EST la cible (selecteur `Caster()` des feuilles). `entities.caster` = source.
        entities = entities_from_state(state, caster_id, caster_id)
        ectx = ExecutionContext(state=state, rng=state.rng)
        # duree = None -> DefaultAmountOfRounds (fallback 1), mirror du `0` (pas de TurnsFromRounds) du decompile.
        if has_protector:
            # THEN : add Conqueror PUIS remove Protector (ordre op_Addition du decompile).
            AddEffect(CONQUEROR, "ConquerorImperative", Caster(), duration_rounds=None).execute(entities, ectx)
            RemoveEffect(PROTECTOR, Caster()).execute(entities, ectx)
            active = "Conqueror"
        else:
            # ELSE : add Protector PUIS remove Conqueror.
            AddEffect(PROTECTOR, "ProtectorImperative", Caster(), duration_rounds=None).execute(entities, ectx)
            RemoveEffect(CONQUEROR, Caster()).execute(entities, ectx)
            active = "Protector"
        return {"imperative": active, "caster": int(caster_id)}
