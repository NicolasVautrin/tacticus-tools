"""`IdunBattleLogic.Entities.Abilities.Triggered.Loki.TerrifyingCrescendoAbility` (triggered 0x59b=1435,
passiveAbility `TerrifyingCrescendo` d'`emperNoiseMarine` << Shiron >>, Emperor's Children) --
l'ACCUMULATION du stack de l'effet `TerrifyingCrescendo_ExtraDmg` (0x590=1424).

L'EFFET etait deja porte et consomme (tache #204 : `TerrifyingCrescendoExtraDmgEffect`,
`entities/effects/loki/extra_damage.py` -> `+extraDmg[ablvl] x mult x LEVEL` additif par coup RANGED,
valide live bit-exact 190/190 en prediction + 7/7 en combat). Ce qui MANQUAIT = le TRIGGER
D'ACCUMULATION : offline le `level` restait celui capte au seed (0 sur un runner frais) et ne montait
JAMAIS -> l'effet etait present-mais-inerte (case-204 §<< Accumulation : NON re-simulee offline >>).

## RE native (decompile ghidra, build gqfc5mff6c)

| Symbole | VA |
|---|---|
| `TerrifyingCrescendoAbility$$CreateTrigger`   | `IdunBattleLogic.Entities.Abilities.Triggered.Loki.TerrifyingCrescendoAbility$$CreateTrigger` |
| `TerrifyingCrescendoAbility$$CreateBehaviour` | `IdunBattleLogic.Entities.Abilities.Triggered.Loki.TerrifyingCrescendoAbility$$CreateBehaviour` |
| `DSLBehaviors$$AddEffectOrIncreaseLevel`        | `IdunBattleLogic.Entities.DSLBehaviors$$AddEffectOrIncreaseLevel` (lambda `b__0 IdunBattleLogic.Entities.DSLFactory.u003Cu003Ec__DisplayClass569_0$$u003CAddEffectOrIncreaseLevelu003Eb__0`) |
| `IncreaseEffectLevelOperation$$Execute`       | `IdunBattle.Operations.IncreaseEffectLevelOperation$$Execute` (le clamp) |
| `TerrifyingCrescendo_ExtraDmgEffect$$CreateEffectDamageBonusForAttack` | `IdunBattle.Entities.Effects.Loki.TerrifyingCrescendo_ExtraDmgEffect$$CreateEffectDamageBonusForAttack` |

### `IdunBattleLogic.Entities.Abilities.Triggered.Loki.TerrifyingCrescendoAbility$$CreateTrigger` (DISJONCTION `op_BitwiseOr` de deux conjonctions)
```
branche1 = On(0 = UnitDeath)      & get_OwnerIsActor & TargetIsOverkilled
branche2 = On(0x3d = PreEffectAdded = 61) & get_OwnerIsActor & TriggeringEffectIs(0x429 = 1065 Pinned)
trigger  = branche1 | branche2
```
= i2 << +218 Damage **for each time he Overkilled or would have Suppressed** an enemy unit >>.
- branche1 : le porteur TUE en OVERKILL. `On(0=UnitDeath)` est emis par `IdunBattle.Operations.KillUnitOperation$$Execute` (sequence verifiee : `FUN_1800280e0(...,1)` PreUnitDeath -> `...,2` -> `...,0` UnitDeath ->
  `...,0x36` UnitDefeated -> `...,0x35` PostUnitKill). Le port emettait deja `On(1)` et `On(0x36 = UnitDefeated)` mais
  PAS `On(0)` -> vecteur ajoute (`unit_death_triggers`, dispatch.py) ENTRE les deux, a la place exacte.
- branche2 : << would have Suppressed >>. `On(0x3d=PreEffectAdded)` est emis par
  `IdunBattle.Operations.AddEffectOperation$$Execute` **TOUT EN HAUT** (`FUN_1800280e0(0x50,...,0x3d)` = `On(PreEffectAdded)`, AVANT le gate
  cible-nulle, AVANT le gate << deja present >> et AVANT le gate d'immunite) -> le compteur monte meme
  quand le Pinned n'est PAS reellement applique (d'ou << WOULD have >>). L'`AbilityEntities` de cet
  evenement est construit `(source, source, target)` -> **actor = la SOURCE de l'effet** : `OwnerIsActor`
  = << c'est MOI qui pose le Suppressed >>. Shiron pose Pinned via son trait `SuppressiveFire` (#74).

### `IdunBattleLogic.Entities.Abilities.Triggered.Loki.TerrifyingCrescendoAbility$$CreateBehaviour`
```
constant = AbilityConfiguration.GetNumberConstant(cfg, 0x62)      # = buffMaxLevel (=6)
AddEffectOrIncreaseLevel( 0x590, AbilityStateReference, self@0x148, selector=self@0x148,
                          amount = df@0xc0 = Const(1), max = Direct(constant) )
```
- `df@0xc0` est construit par `DSLFactory..IdunBattleLogic.Entities.DSLFactory$$.ctor` : `new <DAT_183202d40>(1)` = le noeud
  constant **1** (la meme classe que `IdunBattleLogic.Entities.DSLFormulas$$Get(n)`) -> increment = **+1** par
  declenchement. (Comparatif : `IdunBattleLogic.Entities.Abilities.Active.Loki.HeadClaimerAbility$$CreateBehaviour` passe le MEME `df@0xc0`
  avec un `max` NULL.)
- `GetNumberConstant(0x62)` -> gameconfig `abilities.TerrifyingCrescendo.constants` = **`buffMaxLevel`
  = 6** (seule constante de l'ability ; i2 << up to a maximum of 6 times >>).
- Le clamp exact vit dans `IdunBattle.Operations.IncreaseEffectLevelOperation$$Execute` (mirroré dans la feuille
  `IncreaseEffectLevel`) : `if (!max || max < cur || cur+amount <= max) level += amount; else level = max`.

## Frontiere DSL/imperatif (#149)
`AddEffectOrIncreaseLevel` est une FACTORY natif (elle alloue `Foreach(selector, If(HasEffect,
IncreaseEffectLevel, AddEffect))`) -> portee comme un ARBRE (`add_effect_or_increase_level`), pas comme un
helper impératif fusionné. Les feuilles (`IncreaseEffectLevel` -> `IncreaseEffectLevelOperation`,
`AddEffect` -> `AddEffectOperation`) restent imperatives. Les predicats du trigger sont collapses dans
`matches` (doctrine des triggers).
"""
from __future__ import annotations

from typing import Optional

from ....state import State
from ....abilities.behaviours.context import entities_from_state
from ....abilities.behaviours.effects import add_effect_or_increase_level
from .....entities.selectors.tiles import Caster
from .....entities.effect_type import EffectType
from .....dsl.base import Const
from .....dsl.effects import ExecutionContext
from .....dsl.event_trigger_type import EventTriggerType
from ..base import TriggeredAbility, TriggerEvent

CRESCENDO_EFFECT = int(EffectType.TerrifyingCrescendo_ExtraDmg)     # 0x590 = 1424
CRESCENDO_EFFECT_NAME = "TerrifyingCrescendo_ExtraDmg"              # nom d'EffectType capte live
PINNED = int(EffectType.Pinned)                                     # 0x429 = 1065 (UI << Suppressed >>)
_ON_UNIT_DEATH = int(EventTriggerType.UnitDeath)                    # 0
_ON_PRE_EFFECT_ADDED = int(EventTriggerType.PreEffectAdded)         # 0x3d = 61
_MAX_LEVEL_CONST = "buffMaxLevel"                                   # `GetNumberConstant(0x62)`


def crescendo_max_level() -> Optional[int]:
    """`AbilityConfiguration.GetNumberConstant(cfg, 0x62)` = gameconfig
    `abilities.TerrifyingCrescendo.constants.buffMaxLevel` (=6). None si la constante est absente ->
    `IncreaseEffectLevel` sans cap (mirror du `max` NULL natif)."""
    import gameconfig as GC
    v = ((GC.ability("TerrifyingCrescendo") or {}).get("constants") or {}).get(_MAX_LEVEL_CONST)
    return int(v) if v is not None else None


def terrifying_crescendo_tree():
    """Mirror 1:1 de `IdunBattleLogic.Entities.Abilities.Triggered.Loki.TerrifyingCrescendoAbility$$CreateBehaviour` :
    `AddEffectOrIncreaseLevel(0x590, stateRef, self@0x148, selector=self@0x148, amount=Const(1),
    max=Direct(buffMaxLevel))`. `Caster()` = `Self@0x148` (triggered Owner==Caster)."""
    return add_effect_or_increase_level(
        CRESCENDO_EFFECT, CRESCENDO_EFFECT_NAME, Caster(),
        amount=Const(1), max_level=crescendo_max_level())


class _CrescendoAccumulateBase(TriggeredAbility):
    """Socle commun aux DEUX branches de `IdunBattleLogic.Entities.Abilities.Triggered.Loki.TerrifyingCrescendoAbility$$CreateTrigger` (disjonction `op_BitwiseOr` portee
    comme deux entrees de registre, comme ActOfFaith accumulate/reset) : meme behaviour."""

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        if state.effects is None:
            return None
        ectx = ExecutionContext(state=state, rng=state.rng)
        terrifying_crescendo_tree().execute(entities_from_state(state, self.owner_id, None), ectx)
        lvl = None
        for n, p in ectx.emitted:
            if n in ("IncreaseEffectLevel", "AddEffect"):
                lvl = p.get("level")
        return {"ability": "TerrifyingCrescendo", "unit": int(self.owner_id),
                "level": lvl, "on_event": int(ev.event_id)}


class TerrifyingCrescendoOverkillAbility(_CrescendoAccumulateBase):
    """Branche 1 : `On(UnitDeath=0) & OwnerIsActor & TargetIsOverkilled` — Shiron OVERKILL une cible."""
    event_id = _ON_UNIT_DEATH

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        if not ev.overkill:                       # TargetIsOverkilled
            return False
        killer = ev.killer_id if ev.killer_id is not None else ev.actor_id
        return killer == self.owner_id            # get_OwnerIsActor (le porteur EST le tueur)


class TerrifyingCrescendoSuppressAbility(_CrescendoAccumulateBase):
    """Branche 2 : `On(PreEffectAdded=61) & OwnerIsActor & TriggeringEffectIs(0x429=Pinned)` — Shiron
    POSE (ou aurait pose) un Suppressed. L'event natif precede TOUS les gates d'`AddEffectOperation` ->
    le compteur monte meme si la cible portait deja Pinned (<< would have Suppressed >>)."""
    event_id = _ON_PRE_EFFECT_ADDED

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        if ev.triggering_effect is None or int(ev.triggering_effect) != PINNED:
            return False                          # TriggeringEffectIs(0x429)
        return ev.actor_id == self.owner_id       # get_OwnerIsActor (actor = SOURCE de l'effet pose)
