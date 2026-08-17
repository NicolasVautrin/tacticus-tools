"""`IdunBattleLogic.Entities.Abilities.Triggered.Loki.MasterAnnihilatorAbility` (triggered 1198,
passiveAbility d'`admecDominus` << Vitruvius >>, AdMec) -- la POSE du marqueur `MasterAnnihilator_extraHit`
(0x4e1=1249), avec son **remove-by-source**.

L'EFFET etait deja porte et CONSOMME (`MasterAnnihilatorAdditionalHitEffect`, `entities/effects/loki/
hits.py`). Ce qui MANQUAIT = le maillon qui le POSE : sans entree `ABILITY_TRIGGERS` le marqueur
n'apparaissait JAMAIS dans un runner offline (no-op silencieux).
**#204** : le canal de CONSOMMATION de l'effet a change — il n'est plus un `+1` de la formule de
coups (`create_effect_hits_malus_for_defense`) mais un GROUPE du canal #179
(`create_aura_additional_hits_for_ally`, condition `get_OwnerIsTarget`), l'artefact natif etant
`CreateAdditionalHits` et non `CreateEffectHitsBonusForAttack`. La POSE, elle, est inchangee.

## RE native (decompile ghidra, build gqfc5mff6c)

| Symbole | VA |
|---|---|
| `MasterAnnihilatorAbility$$CreateTrigger`   | `IdunBattleLogic.Entities.Abilities.Triggered.Loki.MasterAnnihilatorAbility$$CreateTrigger` |
| `MasterAnnihilatorAbility$$CreateBehaviour` | `IdunBattleLogic.Entities.Abilities.Triggered.Loki.MasterAnnihilatorAbility$$CreateBehaviour` |
| `MasterAnnihilator_AdditionalHitEffect$$CreateAdditionalHits` | `IdunBattle.Entities.Effects.Loki.MasterAnnihilator_AdditionalHitEffect$$CreateAdditionalHits` |
| `MasterAnnihilator_AdditionalHitEffect$$CreateRemoveEffectTrigger` | `IdunBattle.Entities.Effects.Loki.MasterAnnihilator_AdditionalHitEffect$$CreateRemoveEffectTrigger` |
| `DSLSelectors$$EffectsFromUnitSource` | `IdunBattleLogic.Entities.DSLSelectors$$EffectsFromUnitSource` (-> `EffectWithTypeSelector`) |
| `DSLSelectors$$OwnerOfEffect`         | `IdunBattleLogic.Entities.DSLSelectors$$OwnerOfEffect` |

### `IdunBattleLogic.Entities.Abilities.Triggered.Loki.MasterAnnihilatorAbility$$CreateTrigger` (conjonction `AbilityTrigger.op_BitwiseAnd`)
```
On(0x26=NormalAttack) & get_OwnerIsCaster & AreEnemies(target@0x178, caster@0x160)
```
= << quand Vitruvius fait une ATTAQUE NORMALE contre un ennemi >>. (`On(id, 1, 0)` = `EventNode(id) &
df@0x98`, cf. `IdunBattleLogic.Entities.DSLTriggers$$On`.)

### `IdunBattleLogic.Entities.Abilities.Triggered.Loki.MasterAnnihilatorAbility$$CreateBehaviour` (`AbilityBehaviour.op_Addition` = sequence)
```
RemoveEffect( OwnerOfEffect( EffectsFromUnitSource(self@0x148, 0x4e1) ), Nullable(0x4e1) )
+ AddEffect( 0x4e1, AbilityStateReference, source=caster@0x160, cible=target@0x178,
             options = struct ZERO )
```
1. **remove-by-source** : `EffectsFromUnitSource(Self, 1249)` selectionne les INSTANCES de 1249 dont le
   `EffectComponent.SourceUnit @+0x10` est CE caster ; `OwnerOfEffect` remonte a leurs PORTEURS ;
   `RemoveEffect` les retire. => un SEUL marqueur vivant par Vitruvius, **et le marqueur d'un AUTRE
   poseur n'est PAS touche** (c'est le sens du selecteur keye SOURCE -- le discriminant de validation).
2. **AddEffect** sur la nouvelle cible, duree = struct ZERO -> `DefaultAmountOfRounds(0x4e1)` = **null**
   (`idun.Idun.Source.Shared.Battle.StaticBattleRules.StaticBattleRules.Effect$$DefaultAmountOfRounds` : seuls 0x4f/0x429/0x48a/0x4dc/0x5c4/
   5/0x11/0x12/0x3a y sont) -> le natif retombe sur **1** (`local_588[0]=1` d'`IdunBattle.Operations.AddEffectOperation$$Execute`). Le port passe `duration_rounds=None` = MEME chemin (`AddEffectOperation` porte deja ce
   defaut).

### `IdunBattle.Entities.Effects.Loki.MasterAnnihilator_AdditionalHitEffect$$CreateRemoveEffectTrigger` (cote EFFET, hors de cette ability)
```
On(0=UnitDeath) & AreEqual(target@0x178, EffectSource(thisEffect@0x150))
```
= le marqueur se retire quand SA SOURCE meurt. **NON porte ici** (residu documente) : il faudrait un
registre d'effet-triggers keye `EffectType -> RemoveSelf` ; sans lui un marqueur survit a la mort de
Vitruvius jusqu'a son expiration de timer. Signale dans le rapport.

## Frontiere DSL/imperatif (#149)
Trigger + behaviour = un ARBRE DSL (2 selecteurs S + 2 feuilles E) -- porte comme tel :
`master_annihilator_tree()` = `Seq(RemoveEffect(OwnerOfEffect(EffectsFromUnitSource(Caster(), 1249)),
1249), AddEffect(1249, Target()))`. Les predicats du trigger (`OwnerIsCaster`, `AreEnemies`) sont
COLLAPSES imperativement dans `matches` (doctrine des triggers, cf. SuppressiveFire #74).
"""
from __future__ import annotations

from typing import Optional

from ....state import State
from ....components import OwnerComponent
from ....abilities.behaviours.context import entities_from_state
from ....abilities.behaviours.effects import AddEffect, RemoveEffect
from .....entities.behaviours import op_add
from .....entities.selectors.accessors import Target
from .....entities.selectors.geometry import EffectsFromUnitSource, OwnerOfEffect
from .....entities.selectors.tiles import Caster
from .....entities.effect_type import EffectType
from .....dsl.effects import ExecutionContext
from .....dsl.event_trigger_type import EventTriggerType
from ..base import TriggeredAbility, TriggerEvent

MASTER_ANNIHILATOR_MARK = int(EffectType.MasterAnnihilator_extraHit)   # 0x4e1 = 1249
MASTER_ANNIHILATOR_MARK_NAME = "MasterAnnihilator_extraHit"            # nom d'EffectType capte live
_ON_NORMAL = int(EventTriggerType.NormalAttack)                        # 0x26 = 38


def master_annihilator_tree():
    """Mirror 1:1 de `IdunBattleLogic.Entities.Abilities.Triggered.Loki.MasterAnnihilatorAbility$$CreateBehaviour` :

        RemoveEffect( OwnerOfEffect(EffectsFromUnitSource(Self@0x148, 0x4e1)), 0x4e1 )
        + AddEffect( 0x4e1, source = AbilityStateReference (= le caster), cible = Target@0x178 )

    `Caster()` = `Self@0x148` (triggered Owner==Caster, cf. `entities_from_state`). `duration_rounds=None`
    = struct d'options ZERO du natif -> `DefaultAmountOfRounds(1249)` (null) -> defaut 1 tour."""
    remove_prev = RemoveEffect(MASTER_ANNIHILATOR_MARK,
                               OwnerOfEffect(EffectsFromUnitSource(Caster(), MASTER_ANNIHILATOR_MARK)))
    add_new = AddEffect(MASTER_ANNIHILATOR_MARK, MASTER_ANNIHILATOR_MARK_NAME, Target(),
                        duration_rounds=None, scale_from_source=True)
    return op_add(remove_prev, add_new)                       # `AbilityBehaviour.op_Addition`


class MasterAnnihilatorMarkAbility(TriggeredAbility):
    """`MasterAnnihilatorAbility` (IdunBattleLogic.Entities.Abilities.Triggered.Loki.MasterAnnihilatorAbility$$CreateTrigger / IdunBattleLogic.Entities.Abilities.Triggered.Loki.MasterAnnihilatorAbility$$CreateBehaviour) — triggered 1198
    de la passiveAbility `MasterAnnihilator` d'`admecDominus`. Sur CHAQUE attaque NORMALE de Vitruvius
    contre un ennemi : retire le marqueur 1249 qu'IL avait pose (remove-by-source) puis le pose sur la
    nouvelle cible. L'effet 1249 lui-meme (+1 coup recu de toute attaque non-Psychic) est
    `MasterAnnihilatorAdditionalHitEffect` (deja porte)."""
    event_id = _ON_NORMAL

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        if ev.actor_id != self.owner_id:                   # get_OwnerIsCaster (le porteur EST l'attaquant)
            return False
        if ev.target_id is None:
            return False
        tgt = state.get_entity(ev.target_id)
        owner = state.get_entity(self.owner_id)
        if tgt is None or owner is None:
            return False
        oc = owner.get_component(OwnerComponent)
        tc = tgt.get_component(OwnerComponent)
        if oc is None or tc is None or oc.team == tc.team:  # AreEnemies(target@0x178, caster@0x160)
            return False
        return True

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        if state.effects is None:
            return None                                    # pas d'EffectsState -> pose impossible
        ectx = ExecutionContext(state=state, rng=state.rng)
        master_annihilator_tree().execute(
            entities_from_state(state, self.owner_id, ev.target_id), ectx)
        removed = sum(int(p.get("removed") or 0) for n, p in ectx.emitted if n == "RemoveEffect")
        placed = any(p.get("placed") for n, p in ectx.emitted if n == "AddEffect")
        return {"ability": "MasterAnnihilator", "unit": int(self.owner_id),
                "marked": int(ev.target_id), "placed": bool(placed), "removed_prev": removed}
