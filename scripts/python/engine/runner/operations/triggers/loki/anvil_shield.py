"""`IdunBattleLogic.Entities.Abilities.Triggered.Loki.AnvilShieldAbility_*` (passiveAbility `AnvilShield`
de `spaceRockfist` << Arjac >>, Space Wolves) -- le CLUSTER COMPLET : `ApplyIce` (#222) + `ApplyStun`
et `FrozenAttackerAdvantage` (#100).

i2 : « Arjac blocks an additional 728 Damage and when he Blocks he covers the attacker's hex in Ice.
**If Arjac is below 35% Health, or if his attacker is on a hex covered in Ice, he gains +20% Block
chance and if he blocks a melee attack, the attacker is Stunned until the end of the attacker's next
turn.** »

Ce qui MANQUAIT en #222 : le **DISPATCH `On(UnitBlocked=0x3c=60)`**. Le port RESOLVAIT deja le block
(`did_block`, damage_hits.py) mais n'emettait JAMAIS l'evenement -> tout le cluster on-block
d'AnvilShield etait du code inatteignable. L'effet de TUILE `Ice` (0x11) est deja porte (poseur existant :
LordOfTempests AddIce) : #222 a cable SA POSE par AnvilShield.

Ce qui MANQUAIT en #100 (les DEUX autres volets, laisses en residus parce qu'ils auraient ete du
dead-code garanti) : les classes d'effet **1200** (`AnvilShield_BlockChanceBelowHealthCap`, la moitie
« below 35 % Health » du gate) et **1201** (`AnvilShield_FrozenAttackerAdvantage`, la moitie
« attacker on Ice »), le vecteur **`On(0x2a = PreUnitAbility)`** + son pendant
**`On(0xe = UnitPostAbility)`**, et le **canal stat 7 (BLOCK_CHANCE)** avec son driver
d'`ActiveCondition` (`runner/operations/refresh_effects.py`). Cf. `docs/rl/case-100-anvil-shield-residus.md`.

## RE native (decompile ghidra, build gqfc5mff6c)

| Symbole | VA |
|---|---|
| `ADamageOperation$$EvaluateAfterHitTriggers` | `IdunBattle.Operations.ADamageOperation$$EvaluateAfterHitTriggers` (l'EMETTEUR de `On(0x3c = UnitBlocked)`) |
| `AnvilShieldAbility_ApplyIce$$CreateTrigger`   | `IdunBattleLogic.Entities.Abilities.Triggered.Loki.AnvilShieldAbility_ApplyIce$$CreateTrigger` |
| `AnvilShieldAbility_ApplyIce$$CreateBehaviour` | `IdunBattleLogic.Entities.Abilities.Triggered.Loki.AnvilShieldAbility_ApplyIce$$CreateBehaviour` |
| `AnvilShieldAbility_ApplyStun$$CreateTrigger`   | `IdunBattleLogic.Entities.Abilities.Triggered.Loki.AnvilShieldAbility_ApplyStun$$CreateTrigger` (#100) |
| `AnvilShieldAbility_ApplyStun$$CreateBehaviour` | `IdunBattleLogic.Entities.Abilities.Triggered.Loki.AnvilShieldAbility_ApplyStun$$CreateBehaviour` (#100) |
| `AnvilShieldAbility_FrozenAttackerAdvantage$$CreateTrigger`   | `IdunBattleLogic.Entities.Abilities.Triggered.Loki.AnvilShieldAbility_FrozenAttackerAdvantage$$CreateTrigger` (#100) |
| `AnvilShieldAbility_FrozenAttackerAdvantage$$CreateBehaviour` | `IdunBattleLogic.Entities.Abilities.Triggered.Loki.AnvilShieldAbility_FrozenAttackerAdvantage$$CreateBehaviour` (#100) |
| `AnvilShieldAbility_ApplyAdditionalBlockAndBlockChance$$CreateBehaviour` | `IdunBattleLogic.Entities.Abilities.Triggered.Loki.AnvilShieldAbility_ApplyAdditionalBlockAndBlockChance$$CreateBehaviour` (init) |

### L'EMETTEUR : `IdunBattle.Operations.ADamageOperation$$EvaluateAfterHitTriggers`
```
AbilityEntities.ctor(entities, caster=param_3 (ATTAQUANT), owner=actor=target=param_4 (DEFENSEUR),
                     ..., casterTiles = GetTiles(param_3), targetTiles = GetTiles(param_4), ...)
if (param_6 != 0)   FUN_1800280e0(0x50, ..., 0x3c)      # On(UnitBlocked) -- SEULEMENT si BLOCK
                    FUN_1800280e0(0x50, ..., 8)          # On(AttackHit)  -- TOUJOURS
```
=> sur cet evenement : **caster = l'attaquant**, **owner/actor/target = le DEFENSEUR (le bloqueur)**,
et `df@0x168` (CasterTile) = la tuile de l'ATTAQUANT.

### `IdunBattleLogic.Entities.Abilities.Triggered.Loki.AnvilShieldAbility_ApplyIce$$CreateTrigger`
```
On(0x3c = UnitBlocked) & get_OwnerIsTarget & IsUnit(caster@0x160)
```
= << quand le porteur BLOQUE une attaque, et que l'attaquant est une UNITE >>.

### `IdunBattleLogic.Entities.Abilities.Triggered.Loki.AnvilShieldAbility_ApplyIce$$CreateBehaviour`
```
AddEffect( 0x11 = Ice, AbilityStateReference, source = Self@0x148, cible = df@0x168 = CasterTile,
           options = struct ZERO )
```
= glace la TUILE de l'attaquant. `DefaultAmountOfRounds(0x11) = 2` (`idun.Idun.Source.Shared.Battle.StaticBattleRules.StaticBattleRules.Effect$$DefaultAmountOfRounds`).

### `IdunBattleLogic.Entities.Abilities.Triggered.Loki.AnvilShieldAbility_ApplyStun$$CreateTrigger`
```
On(0x3c = UnitBlocked) & get_OwnerIsTarget & IsMeleeAttack
  & !HasTrait(caster@0x160, 0x1b = Steppable) & IsUnit(caster@0x160) & IsAlive(caster@0x160)
  & ( HasEffect(target@0x178, 0x4b0 = 1200, activeOnly=1, sourceFlags=6)
    | HasEffect(target@0x178, 0x4b1 = 1201, activeOnly=1, sourceFlags=6) )
```
### `IdunBattleLogic.Entities.Abilities.Triggered.Loki.AnvilShieldAbility_ApplyStun$$CreateBehaviour`
```
AddEffect( 0x48a = 1162 Stunned, AbilityStateReference, source = Self@0x148, cible = caster@0x160,
           duree = If( IsTurnOf(caster@0x160),
                       TurnsUntilEndOfCurrentPlayersNextTurn,
                       TurnsFromRounds(1) ) )
```

### `IdunBattleLogic.Entities.Abilities.Triggered.Loki.AnvilShieldAbility_FrozenAttackerAdvantage$$CreateTrigger`
```
On(0x2a = PreUnitAbility) & IsNormalAttack & get_OwnerIsTarget
  & IsUnitOnTileWithEffect(caster@0x160, 0x11 = Ice)
  & !HasEffect(Self@0x148, 0x4b0, 1, 6) & !HasEffect(Self@0x148, 0x4b1, 1, 6)
```
### `IdunBattleLogic.Entities.Abilities.Triggered.Loki.AnvilShieldAbility_FrozenAttackerAdvantage$$CreateBehaviour`
```
AddStaticStatModifierEffect( Self@0x148, 0x4b1 = 1201, statType 7 = BLOCK_CHANCE,
                             GetVariableForLevel(0x15 = blockChance) )
```

## Le 4e argument de `IdunBattleLogic.Entities.DSLTriggers$$HasEffect` = ACTIVE-ONLY (pas un minLevel)

`IdunBattleLogic.Entities.DSLTriggers$$HasEffect(sel, type, param4, param5)` construit
`IdunBattle.Entities.Triggers.HasEffectTrigger(sel, type, query, param5, param4)` ; son `ShouldTrigger`
appelle `IdunBattle.Entities.EntityExtensions$$HasOneOfEffects(entity, query, [type], param4, param5)`.
Dans `IdunBattle.Entities.EntityExtensions$$IsOwnerOfEffect` : `if (param_4 != 0) { if
(*(char*)(effect + 0x5c) == '\\0') continue; }` AVANT le test `*(int*)(effect + 0x58) == type` — et
`+0x5c` est le flag **IsActive** (`IdunBattle.Operations.RefreshEffectsOperation$$DeactivateEffect` :
`if (comp+0x5c == 0) return; comp+0x5c = 0;`). `param5 = 6 = 2|4` = les deux branches owned|incoming.

## Volet init (POSE des owner-effects, pas un trigger on-block)
`IdunBattleLogic.Entities.Abilities.Triggered.Loki.AnvilShieldAbility_ApplyAdditionalBlockAndBlockChance$$CreateBehaviour`
= `AddStaticStatModifierEffect(Self, 0x4b2=1202, stat 8, blockDmg[0x14])
   + AddStaticStatModifierEffect(Self, 0x4b0=1200, stat 7, blockChance[0x15])`. Son `CreateTrigger` est
le corps DEDUPLIQUE `IdunBattleLogic.Entities.Abilities.Triggered.LifewardsAddEffectAbility$$CreateTrigger`
(`return df@0xa8`), et `df@0xa8` est construit par `IdunBattleLogic.Entities.DSLTriggers$$InitializeShared`
= `On(0x21 = AbilityInit) & OwnerIsActor` -> ce sont des **owner-effects poses A L'INIT**, PAS on-block
(mis-attribution corrigee en #222). Les deux classes d'effet sont portees (`hits.py`) ; 1200 est en plus
inscrit dans `ABILITY_INIT_OWNER_EFFECTS["AnvilShield"]` parce que, INACTIF au-dessus de 35 % PV, il est
ABSENT du seed live (`decisionView.effects` n'expose que les ACTIFS).

## GROUND TRUTH LIVE (#100, `scripts/python/probe_anvil_shield_residues.py`)
- Arjac a 100 % PV : `blockChance = 0`, 1200 ABSENT de decisionView.
- Arjac a 31.8 % / 8.2 % PV : 1200 PRESENT, `blockChance = 20`.
- Attaquant place sur une tuile GLACEE (Njal/LordOfTempests) frappant Arjac a **PLEINS PV** :
  7 stuns / 15 attaques (les attaques font 3 coups, block 20 %/coup => ~49 % par attaque = la mesure).
  `Stunned` observe : `level 1, remaining 3, source = Arjac` + les 3 sous-effets 1165/1166/1167.
  `remaining 3` = `ConvertRoundsToTurns(1) = 2` **+ 1** => `TurnsUntilEndOfCurrentPlayersNextTurn`
  = `TurnsFromRounds(1) + 1` (mirror de la structure native : le noeud est bati sur
  `TurnsFromRoundsFormula(df, .., 1)` ET un noeud constant `1`).
- Meme scenario, attaquant HORS glace et Arjac > 35 % : **0 stun** (controle negatif).
"""
from __future__ import annotations

from typing import Optional

from ....state import State
from ....components import OwnerComponent, UnitComponent, PositionComponent, HealthComponent
from ....abilities.attack_type import is_normal_attack
from ....abilities.behaviours.context import entities_from_state
from ....abilities.behaviours.effects import AddEffect, RemoveEffect
from ....abilities.base import convert_rounds_to_turns
from .....entities.selectors.accessors import Target
from .....entities.selectors.tiles import Caster
from .....entities.selectors.units import Tiles
from .....entities.effect_type import EffectType
from .....entities.traits.unit_trait import UnitTrait, has_trait
from .....dsl.effects import ExecutionContext
from .....dsl.event_trigger_type import EventTriggerType
from ..base import TriggeredAbility, TriggerEvent, EffectTrigger
from ..base import _is_ranged_position
from ..base import _unit_trait_names

ICE_TILE = int(EffectType.Ice)                          # 0x11 = 17 (effet de TUILE, defaut 2 rounds)
STUNNED = int(EffectType.Stunned)                       # 0x48a = 1162 (COMPOSITE : 1165/1166/1167)
BLOCK_CHANCE_CAP = int(EffectType.AnvilShield_BlockChanceBelowHealthCap)      # 0x4b0 = 1200
FROZEN_ADVANTAGE = int(EffectType.AnvilShield_FrozenAttackerAdvantage)       # 0x4b1 = 1201
_ON_BLOCKED = int(EventTriggerType.UnitBlocked)         # 0x3d = 61
_ON_PRE_ABILITY = int(EventTriggerType.PreUnitAbility)  # 0x2b = 43
_ON_POST_ABILITY = int(EventTriggerType.UnitPostAbility)  # 0xe = 14


def anvil_shield_apply_ice_tree():
    """Mirror 1:1 de `IdunBattleLogic.Entities.Abilities.Triggered.Loki.AnvilShieldAbility_ApplyIce$$CreateBehaviour` :
        `AddEffect(0x11=Ice, AbilityStateReference, source = Self@0x148, cible = CasterTile@0x168)`

    REMAP DE ROLES (documente) : le `DslContext` du port n'a que les slots caster/target/actor, et la
    feuille `AddEffect` lit la SOURCE dans `ctx.caster`. On construit donc l'`entities` avec
    **caster = le PORTEUR** (= `Self@0x148`, la source native) et **target = l'ATTAQUANT** ; la tuile
    `CasterTile@0x168` (celle de l'ATTAQUANT, cf. `GetTiles(param_3)` de `EvaluateAfterHitTriggers`) est
    donc adressee par `Tiles(Target())`. `duration_rounds=None` = struct d'options ZERO ->
    `DefaultAmountOfRounds(0x11) = 2` rounds."""
    return AddEffect(ICE_TILE, "Ice", Tiles(Target()), duration_rounds=None)


class AnvilShieldApplyIceAbility(TriggeredAbility):
    """`AnvilShieldAbility_ApplyIce` (IdunBattleLogic.Entities.Abilities.Triggered.Loki.AnvilShieldAbility_ApplyIce$$CreateTrigger / IdunBattleLogic.Entities.Abilities.Triggered.Loki.AnvilShieldAbility_ApplyIce$$CreateBehaviour) — quand Arjac
    BLOQUE une attaque, la TUILE de l'attaquant est GLACEE. `On(UnitBlocked=60) & OwnerIsTarget &
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


# --- helpers PARTAGES par les deux volets « +20 % block » --------------------------------------------
def _has_active_block_bonus(state: State, owner_id: int) -> bool:
    """`HasEffect(target@0x178, 0x4b0, activeOnly=1, 6) | HasEffect(target@0x178, 0x4b1, activeOnly=1, 6)`
    — le porteur a-t-il l'un des DEUX effets « +20 % Block chance » **ACTIF** ? `activeOnly` est le 4e
    argument natif (flag `EffectComponent+0x5c`, cf. en-tete de module) : cote port, l'`ActiveCondition`
    de la classe d'effet (`BaseEffect.is_active`), ce qui rend `1200` vivant SEULEMENT sous 35 % PV."""
    if state.effects is None:
        return False
    ent = state.get_entity(owner_id)
    hc = ent.get_component(HealthComponent) if ent is not None else None
    ustate = {"hp": hc.hp, "max_hp": hc.hp_max} if hc is not None else {}
    for e in state.effects.by_unit.get(int(owner_id), []):
        if e.consumed or e.expired:
            continue
        if e.effect_type in (BLOCK_CHANCE_CAP, FROZEN_ADVANTAGE) and e.is_active(ustate):
            return True
    return False


def anvil_shield_apply_stun_tree(state: State, attacker_id: int):
    """Mirror 1:1 de `IdunBattleLogic.Entities.Abilities.Triggered.Loki.AnvilShieldAbility_ApplyStun$$CreateBehaviour` :
        `AddEffect(0x48a = Stunned, AbilityStateReference, source = Self@0x148, cible = caster@0x160,
                   duree = If(IsTurnOf(caster), TurnsUntilEndOfCurrentPlayersNextTurn, TurnsFromRounds(1)))`

    REMAP DE ROLES (meme convention que `anvil_shield_apply_ice_tree`) : la feuille `AddEffect` du port
    lit la SOURCE dans `ctx.caster` -> on construit l'`entities` avec **caster = le PORTEUR** (`Self@0x148`)
    et **target = l'ATTAQUANT** (`caster@0x160`), donc la cible s'adresse par `Target()`.

    DUREE — le noeud `If` natif est resolu ICI (les feuilles du port prennent une duree SCALAIRE, meme
    convention que `AddBondEffect`) :
      * `IsTurnOf(caster)` VRAI (cas nominal : l'attaquant frappe pendant SON tour) ->
        `TurnsUntilEndOfCurrentPlayersNextTurn` = `ConvertRoundsToTurns(1) + 1`
        (`IdunBattleLogic.Entities.DSLFormulas$$TurnsUntilEndOfCurrentPlayersNextTurn` bat son noeud sur
        `TurnsFromRoundsFormula(df, .., 1)` + un noeud constant `1` ; GROUND TRUTH LIVE : `remaining = 3`
        pour 2 joueurs, soit 2 + 1). Duree deja en TOURS -> `duration_turns` (NON reconvertie).
      * sinon (attaque hors du tour de l'attaquant : overwatch, contre-attaque) -> `TurnsFromRounds(1)`
        -> `duration_rounds=1` (converti par `ConvertRoundsToTurns`).
    i2 : « the attacker is Stunned until the end of the attacker's next turn »."""
    ent = state.get_entity(attacker_id)
    oc = ent.get_component(OwnerComponent) if ent is not None else None
    is_turn_of_caster = (oc is not None and oc.player is not None
                         and state.current_player_id is not None
                         and int(state.current_player_id) == int(oc.player))
    if is_turn_of_caster:
        return AddEffect(STUNNED, "Stunned", Target(),
                         duration_turns=convert_rounds_to_turns(state, 1) + 1)
    return AddEffect(STUNNED, "Stunned", Target(), duration_rounds=1)


class AnvilShieldApplyStunAbility(TriggeredAbility):
    """`AnvilShieldAbility_ApplyStun` (`...AnvilShieldAbility_ApplyStun$$CreateTrigger` /
    `$$CreateBehaviour`) — quand Arjac BLOQUE une attaque de MELEE et qu'il beneficie du « +20 % Block
    chance » (1200 sous 35 % PV **ou** 1201 attaquant-sur-glace), l'ATTAQUANT est **Stunned**.

    `On(UnitBlocked=0x3c)` : `AbilityEntities.ctor(caster = ATTAQUANT, owner = actor = target =
    DEFENSEUR)` -> `get_OwnerIsTarget` = `ev.target_id == owner_id`, `caster@0x160` = `ev.actor_id`.
    Les predicats du `CreateTrigger` sont COLLAPSES imperativement (doctrine #149 : la feuille
    `AddEffect` reste l'arbre DSL)."""
    event_id = _ON_BLOCKED

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        if ev.target_id != self.owner_id:                 # get_OwnerIsTarget (le porteur a bloque)
            return False
        att = state.get_entity(ev.actor_id) if ev.actor_id is not None else None
        if att is None:
            return False
        uc = att.get_component(UnitComponent)
        if uc is None or att.get_component(OwnerComponent) is None:      # IsUnit(caster@0x160)
            return False
        if not uc.alive:                                                 # IsAlive(caster@0x160)
            return False
        # IsMeleeAttack : le natif lit le TYPE DE TIMELINE de l'ability courante ; le port dispose du
        # discriminant POSITION (`_is_ranged_position`, mirror `IdunBattleLogic.Entities.DSLTriggers$$IsRangedAttack`) — meme
        # discriminant deja utilise par SuppressiveFire pour sa face ranged.
        if _is_ranged_position(state, ev.actor_id, ev.target_id):
            return False
        # !HasTrait(caster@0x160, 0x1b = Steppable) : exclut les objets « marchables » (decoys, ...).
        if has_trait(_unit_trait_names(state, ev.actor_id), UnitTrait.Steppable):
            return False
        return _has_active_block_bonus(state, self.owner_id)

    def execute_behaviour(self, state: State, ev: TriggerEvent):
        if state.effects is None or ev.actor_id is None:
            return None
        ectx = ExecutionContext(state=state, rng=state.rng)
        anvil_shield_apply_stun_tree(state, ev.actor_id).execute(
            entities_from_state(state, self.owner_id, ev.actor_id), ectx)
        placed = any(p.get("placed") for n, p in ectx.emitted if n == "AddEffect")
        return {"ability": "AnvilShield", "unit": int(self.owner_id),
                "stunned_attacker": int(ev.actor_id), "placed": bool(placed)}


def anvil_shield_frozen_attacker_advantage_tree():
    """Mirror 1:1 de `...AnvilShieldAbility_FrozenAttackerAdvantage$$CreateBehaviour` :
        `AddStaticStatModifierEffect(Self@0x148, 0x4b1 = 1201, statType 7 = BLOCK_CHANCE,
                                     GetVariableForLevel(0x15 = blockChance))`

    Decomposition PORT (frontiere #149) : la feuille DECLARATIVE est un `AddEffect(1201, Caster())` sur
    le porteur ; la MAGNITUDE (stat 7, `blockChance[activeAbilityLevel]`) est la part DATA de la classe
    d'effet (`AnvilShieldFrozenAttackerAdvantageEffect.applied_stat_mods`), executee par l'Operation
    `AddEffectOperation._apply_stat_mods` (`ChangeStat` part 5) et revertee par `RemoveEffect`.
    `Caster()` = le PORTEUR ici (l'`entities` est construit avec caster = owner, cf. `execute_behaviour`).
    Aucune duree : `AddStaticStatModifierEffect` ne passe pas d'override et 0x4b1 est ABSENT de
    `DefaultAmountOfRounds` -> `remaining = 0` = PERMANENT ; c'est le trigger propre de l'effet
    (`On(UnitPostAbility)`) qui le consomme."""
    return AddEffect(FROZEN_ADVANTAGE, "AnvilShield_FrozenAttackerAdvantage", Caster(),
                     duration_rounds=None)


class AnvilShieldFrozenAttackerAdvantageAbility(TriggeredAbility):
    """`AnvilShieldAbility_FrozenAttackerAdvantage` — AVANT qu'une attaque NORMALE ne resolve contre
    Arjac, si l'attaquant se tient sur une tuile GLACEE et qu'Arjac n'a pas deja un des deux bonus de
    block, Arjac gagne 1201 (+20 % Block chance) pour CETTE ability.

    `On(0x2a = PreUnitAbility)` est emis par `IdunBattle.Operations.ActiveAbilityOperation$$ExecuteInternal`
    (`FUN_1800280e0(0x4d, .., 0x2a)`, soit `On(PreUnitAbility)`) **AVANT** l'execution de l'ability — donc avant le calcul du block ;
    la MEME operation emet ensuite `0xb`, `0xc` puis `0xe (UnitPostAbility)`. L'attaque normale passe par
    cette operation (l'attaque normale EST une active ability, cf. `NormalAttackType`), et le gate
    `IsNormalAttack` la restreint a la voie normale.

    #120 — le gate `IsNormalAttack` etait jusqu'ici satisfait STRUCTURELLEMENT (le port n'emettait
    `0x2b` que depuis `AttackDamageOperation`). Depuis que le vecteur part AUSSI de
    `AbilityHandler.visit_ActiveAbilityMessage` (de-fork du site natif unique), il est PORTE
    explicitement : `abilities/attack_type.is_normal_attack` (mirror
    `IdunBattleLogic.Entities.DSLTriggers$$IsNormalAttack`). Sans lui, Arjac gagnerait +20 % de block
    sur n'importe quel cast adverse — un faux-positif que le natif refuse."""
    event_id = _ON_PRE_ABILITY

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        if not is_normal_attack(ev.ability_type):         # IsNormalAttack (#120, cf. docstring)
            return False
        if ev.target_id != self.owner_id:                 # get_OwnerIsTarget (Arjac est la cible)
            return False
        if ev.actor_id is None or state.effects is None:
            return False
        board = getattr(state, "board", None)
        if board is None:
            return False
        att = state.get_entity(ev.actor_id)
        pc = att.get_component(PositionComponent) if att is not None else None
        if pc is None:
            return False
        # IsUnitOnTileWithEffect(caster@0x160, 0x11 = Ice) : la TUILE OCCUPEE par l'attaquant est glacee.
        tile = board.id_at(pc.col, pc.row)
        if tile is None or not state.effects.has_effect(int(tile), effect_type=ICE_TILE):
            return False
        # !HasEffect(Self, 1200, active) & !HasEffect(Self, 1201, active)
        return not _has_active_block_bonus(state, self.owner_id)

    def execute_behaviour(self, state: State, ev: TriggerEvent):
        if state.effects is None:
            return None
        ectx = ExecutionContext(state=state, rng=state.rng)
        # caster = target = le PORTEUR (`Self@0x148` des deux cotes de la feuille).
        anvil_shield_frozen_attacker_advantage_tree().execute(
            entities_from_state(state, self.owner_id, self.owner_id), ectx)
        placed = any(p.get("placed") for n, p in ectx.emitted if n == "AddEffect")
        return {"ability": "AnvilShield", "unit": int(self.owner_id),
                "frozen_attacker": int(ev.actor_id), "placed": bool(placed)}


def _frozen_advantage_instances(state: State, owner_id: int) -> list:
    """Les instances d'effet 1201 NON consommees portees par `owner_id` — c'est-a-dire les
    entites-effet dont
    `IdunBattle.Entities.Effects.Loki.AnvilShield_FrozenAttackerAdvantageEffect$$CreateTargetTrigger`
    est evalue. Liste (et non instance unique) parce que le natif raisonne PAR ENTITE-EFFET ; en
    pratique `AddEffectOperation` no-ope sur un meme-type deja present, donc il y en a 0 ou 1.
    [] si l'etat n'a pas d'`EffectsState`."""
    if state.effects is None:
        return []
    return [e for e in state.effects.by_unit.get(int(owner_id), [])
            if not e.consumed and e.effect_type == FROZEN_ADVANTAGE]


def _frozen_advantage_flag_is_set(state: State, owner_id: int) -> bool:
    """Le flag `EffectComponent.IsActive @+0x5c` (`BaseEffect.active`) de l'instance 1201 du porteur
    — mirror du gate qu'applique
    `IdunBattle.Operations.EvaluateTriggerOperation$$EvaluateEffectTriggerTargets` AVANT d'evaluer le
    trigger de CIBLE. Dans sa boucle PAR CIBLE, le natif RECHARGE l'`EffectComponent` depuis
    l'entite-effet (`comp = effect.Get<EffectComponent>()`) et fait `if (*(char *)(comp + 0x5c) !=
    '\\0')` avant `ShouldTrigger` (slot 0x13) puis `Execute` (slot 0x14) : une instance INERTE n'est
    meme pas EVALUEE. (Le test d'entree sur le meme flag, lui, ne porte qu'un court-circuit
    d'allocation « actif ET aucune cible -> return » — cf. `docs/rl/case-231-effect-1201-active-gate.md`.)

    N'IMPORTE QUEL effet peut devenir inerte : `IdunBattle.Operations.RefreshEffectsOperation$$RefreshEffect`
    fait `ShouldBeActive == false -> DeactivateEffect` pour tous, et
    `IdunBattle.Operations.RefreshEffectsOperation$$ShouldBeActive` renvoie `false` des que
    `EffectComponent+0x5e` est leve — sans passer par un `CreateActiveCondition` propre (1201 n'en a
    pas : son `.ctor` appelle `ADynamicStatModifierEffect$$.ctor` sans condition). Cote port, le
    vecteur est le SEED : `EffectFactory.create` lit la cle `active` du capte, que
    `decisionView { includeInactive: true }` publie a `false`.

    Aucune instance trouvee -> True : degradation PERMISSIVE (on ne fabrique pas un refus), MEME
    convention que `_ranged_auto_attack_flag_is_set` (1009, `triggers/effect_triggers.py`). Le cas se
    presente quand l'etat n'a pas d'`EffectsState` ; si l'effet est reellement absent, c'est
    `collect_effect_triggers` qui n'aura instancie aucun trigger."""
    insts = _frozen_advantage_instances(state, owner_id)
    return (not insts) or any(e.active for e in insts)


class AnvilShieldFrozenAdvantageExpire(EffectTrigger):
    """Trigger PROPRE de l'effet 1201 —
    `IdunBattle.Entities.Effects.Loki.AnvilShield_FrozenAttackerAdvantageEffect$$CreateTargetTrigger` :
        `On(0xe = UnitPostAbility) & AreEqual(target@0x178, EffectSource(thisEffect@0x150))`
    (le `CreateTargetTriggerBehaviour` herite de `ADynamicStatModifierEffect` est
    `RefreshDynamicStatModifierValue(this)`).

    OBSERVABLE LIVE (#100) : des la fin de l'attaque qui l'a pose, l'effet a DISPARU de
    `decisionView.effects` et `blockChance` est retombe a 0 — alors que le STUN, lui, a bien eu lieu
    PENDANT l'attaque. Le port execute donc la consommation ICI (`RemoveEffect(1201, Caster())`, qui
    reverte aussi le `ChangeStat` par-source via `reverted_stats()`), a l'evenement EXACT du trigger
    natif. C'est ce qui donne au bonus sa portee « une attaque » de l'i2.

    #231 — venant de `CreateTargetTrigger`, ce trigger est du rail TARGETS : son evaluation est
    GATEE par `EffectComponent.IsActive @+0x5c` (`_frozen_advantage_flag_is_set`). Le rail voisin
    (`CreateHandleTriggerAbilitiesInternal`, evalue par `EvaluateEffectTriggerEffectAbilities`)
    n'a AUCUN gate — l'y poser serait une infidelite ; 1201 n'a pas de trigger sur ce rail."""
    event_id = _ON_POST_ABILITY
    effect_type = FROZEN_ADVANTAGE

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        # Gate `IsActive @+0x5c` de l'instance (#231) : une instance INERTE n'est pas evaluee par
        # `EvaluateEffectTriggerTargets` -> pas de consommation, le +20 % de block ne bouge pas.
        if not _frozen_advantage_flag_is_set(state, self.owner_id):
            return False
        # AreEqual(target@0x178, EffectSource(this)) : la cible de l'ability qui s'acheve est le porteur
        # (= la SOURCE de l'effet, pose par `AddStaticStatModifierEffect(Self, ...)`).
        return ev.target_id == self.owner_id

    def execute_behaviour(self, state: State, ev: TriggerEvent):
        if state.effects is None:
            return None
        ectx = ExecutionContext(state=state, rng=state.rng)
        RemoveEffect(FROZEN_ADVANTAGE, Caster()).execute(
            entities_from_state(state, self.owner_id, self.owner_id), ectx)
        removed = sum(int(p.get("removed") or 0) for n, p in ectx.emitted if n == "RemoveEffect")
        return ({"ability": "AnvilShield", "unit": int(self.owner_id),
                 "frozen_advantage_expired": removed} if removed else None)
