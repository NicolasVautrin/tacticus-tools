"""`IdunBattleLogic.Entities.Abilities.Triggered.Loki.AnvilShieldAbility_*` (passiveAbility `AnvilShield`
de `spaceRockfist` << Arjac >>, Space Wolves) -- le CLUSTER on-block, dont SEUL le volet `ApplyIce` est
porte ici (les autres volets = residus, cf. bas de docstring).

Ce qui MANQUAIT : le **DISPATCH `On(UnitBlocked=0x3d=61)`**. Le port RESOLVAIT deja le block
(`did_block`, damage_hits.py:99/134) mais n'emettait JAMAIS l'evenement -> tout le cluster on-block
d'AnvilShield etait du code inatteignable. L'effet de TUILE `Ice` (0x11) est deja porte (poseur existant :
LordOfTempests AddIce) : ici on cable SA POSE par AnvilShield.

## RE native (decompile ghidra, build gqfc5mff6c)

| Symbole | VA |
|---|---|
| `ADamageOperation$$EvaluateAfterHitTriggers` | `0x180e25fc0` (l'EMETTEUR de `On(0x3d)`) |
| `AnvilShieldAbility_ApplyIce$$CreateTrigger`   | `0x180e16500` |
| `AnvilShieldAbility_ApplyIce$$CreateBehaviour` | `0x180e16480` |
| `AnvilShieldAbility_ApplyStun$$CreateTrigger`   | `0x180e16680` (residu) |
| `AnvilShieldAbility_ApplyStun$$CreateBehaviour` | `0x180e16590` (residu) |
| `AnvilShieldAbility_FrozenAttackerAdvantage$$CreateTrigger`   | `0x180e168e0` (residu) |
| `AnvilShieldAbility_FrozenAttackerAdvantage$$CreateBehaviour` | `0x180e16840` (residu) |
| `AnvilShieldAbility_ApplyAdditionalBlockAndBlockChance$$CreateBehaviour` | `0x180e16340` (init) |

### L'EMETTEUR : `EvaluateAfterHitTriggers @180e25fc0`
```
AbilityEntities.ctor(entities, caster=param_3 (ATTAQUANT), owner=actor=target=param_4 (DEFENSEUR),
                     ..., casterTiles = GetTiles(param_3), targetTiles = GetTiles(param_4), ...)
if (param_6 != 0)   FUN_180026490(0x50, ..., 0x3d)      # UnitBlocked -- SEULEMENT si BLOCK
                    FUN_180026490(0x50, ..., 8)          # AttackHit  -- TOUJOURS
```
=> sur cet evenement : **caster = l'attaquant**, **owner/actor/target = le DEFENSEUR (le bloqueur)**,
et `df@0x168` (CasterTile) = la tuile de l'ATTAQUANT.

### `ApplyIce.CreateTrigger @180e16500`
```
On(0x3d = UnitBlocked) & get_OwnerIsTarget & IsUnit(caster@0x160)
```
= << quand le porteur BLOQUE une attaque, et que l'attaquant est une UNITE >>.

### `ApplyIce.CreateBehaviour @180e16480`
```
AddEffect( 0x11 = Ice, AbilityStateReference, source = Self@0x148, cible = df@0x168 = CasterTile,
           options = struct ZERO )
```
= glace la TUILE de l'attaquant. `DefaultAmountOfRounds(0x11) = 2` (`@181559ff0`).

## Volets NON portes (residus honnetes)
- **`ApplyAdditionalBlockAndBlockChance` @180e16340** : son `CreateTrigger` est le corps DEDUPLIQUE
  `@180e15880` (`return df@0xa8`), et `df@0xa8` est construit par `InitializeShared @180df2670` =
  `On(0x21 = AbilityInit) & OwnerIsActor`. Ce n'est donc **PAS** un trigger on-block : les deux
  `AddStaticStatModifierEffect` (0x4b2=1202 BLOCK_DAMAGE var `blockDmg`, 0x4b0=1200 BLOCK_CHANCE var
  `blockChance`) sont poses **A L'INIT DE L'ABILITY** (owner-effects). L'effet 1202 est deja porte
  (`AnvilShieldAdditionalBlockEffect`) ET deja present sur Arjac dans un runner (seed live) -> RIEN a
  cabler (la note << pose par le vecteur ON-BLOCK >> de hits.py:384 etait une MIS-ATTRIBUTION, corrigee).
- **`ApplyStun` @180e16590/@180e16680** : `On(0x3d) & OwnerIsTarget & IsMeleeAttack &
  !HasTrait(caster,0x1b) & IsUnit(caster) & IsAlive(caster) & (HasEffect(target, 0x4b0=1200, lvl>=1) |
  HasEffect(target, 0x4b1=1201, lvl>=1))` -> `AddEffect(0x48a=Stunned, source=Self, cible=caster,
  duree = If(IsTurnOf(caster), TurnsUntilEndOfCurrentPlayersNextTurn, TurnsFromRounds(1)))`.
  **Le gate depend de 1200/1201, ni portes ni poses** -> un port serait un no-op garanti. NON porte.
- **`FrozenAttackerAdvantage` @180e16840/@180e168e0** : `On(0x2b = PreUnitAbility) & IsNormalAttack &
  OwnerIsTarget & IsUnitOnTileWithEffect(caster, 0x11=Ice) & !HasEffect(Self,1200) & !HasEffect(Self,1201)`
  -> `AddStaticStatModifierEffect(Self, 0x4b1=1201, stat 7 = BLOCK_CHANCE, GetVariableForLevel(0x15))`.
  Prerequis ABSENTS : vecteur `On(PreUnitAbility=43)` + classe d'effet 1201 + canal stat 7. NON porte.
"""
from __future__ import annotations

from typing import Optional

from ....state import State
from ....components import OwnerComponent, UnitComponent
from ....abilities.behaviours import AddEffect, entities_from_state
from .....entities.selectors import Tiles, Target
from .....entities.effect_type import EffectType
from .....dsl.effects import ExecutionContext
from .....dsl.event_trigger_type import EventTriggerType
from ..base import TriggeredAbility, TriggerEvent

ICE_TILE = int(EffectType.Ice)                          # 0x11 = 17 (effet de TUILE, defaut 2 rounds)
_ON_BLOCKED = int(EventTriggerType.UnitBlocked)         # 0x3d = 61


def anvil_shield_apply_ice_tree():
    """Mirror 1:1 de `AnvilShieldAbility_ApplyIce.CreateBehaviour @180e16480` :
        `AddEffect(0x11=Ice, AbilityStateReference, source = Self@0x148, cible = CasterTile@0x168)`

    REMAP DE ROLES (documente) : le `DslContext` du port n'a que les slots caster/target/actor, et la
    feuille `AddEffect` lit la SOURCE dans `ctx.caster`. On construit donc l'`entities` avec
    **caster = le PORTEUR** (= `Self@0x148`, la source native) et **target = l'ATTAQUANT** ; la tuile
    `CasterTile@0x168` (celle de l'ATTAQUANT, cf. `GetTiles(param_3)` de `EvaluateAfterHitTriggers`) est
    donc adressee par `Tiles(Target())`. `duration_rounds=None` = struct d'options ZERO ->
    `DefaultAmountOfRounds(0x11) = 2` rounds."""
    return AddEffect(ICE_TILE, "Ice", Tiles(Target()), duration_rounds=None)


class AnvilShieldApplyIceAbility(TriggeredAbility):
    """`AnvilShieldAbility_ApplyIce` (CreateTrigger @180e16500 / CreateBehaviour @180e16480) — quand Arjac
    BLOQUE une attaque, la TUILE de l'attaquant est GLACEE. `On(UnitBlocked=61) & OwnerIsTarget &
    IsUnit(caster)`. L'effet de tuile Ice (0x11) est deja porte (meme effet que LordOfTempests AddIce)."""
    event_id = _ON_BLOCKED

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        # get_OwnerIsTarget : le porteur est la CIBLE de l'attaque bloquee (c'est lui qui a bloque).
        if ev.target_id != self.owner_id:
            return False
        # IsUnit(caster@0x160) : l'attaquant est une UNITE (pas une tuile/machine sans UnitComponent).
        att = state.get_entity(ev.actor_id) if ev.actor_id is not None else None
        if att is None or att.get_component(UnitComponent) is None:
            return False
        if att.get_component(OwnerComponent) is None:
            return False
        return getattr(state, "board", None) is not None      # sans board, pas de tuile a glacer

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        if state.effects is None or getattr(state, "board", None) is None:
            return None
        ectx = ExecutionContext(state=state, rng=state.rng)
        # caster = le PORTEUR (source de l'effet, `Self@0x148`) ; target = l'ATTAQUANT (dont on glace la
        # tuile, `CasterTile@0x168`). Cf. le REMAP documente dans `anvil_shield_apply_ice_tree`.
        anvil_shield_apply_ice_tree().execute(
            entities_from_state(state, self.owner_id, ev.actor_id), ectx)
        placed = any(p.get("placed") for n, p in ectx.emitted if n == "AddEffect")
        return {"ability": "AnvilShield", "unit": int(self.owner_id),
                "iced_attacker": int(ev.actor_id), "placed": bool(placed)}
