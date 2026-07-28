"""Cluster DESPOILED GROUND (#85) — les DEUX abilities natives qui font vivre l'effet de TUILE
`DespoiledGround` (EffectType 0x5c4 = 1476) :

| Symbole natif | Role | Porte par |
|---|---|---|
| `IdunBattleLogic.Entities.Abilities.Active.Loki.FleshMetalGuns_TileEffectAbility$$CreateTrigger` / `$$CreateBehaviour` | POSE la tuile sur `On(0x10 = DamageDealt)` | `loki/fleshmetal_guns.py` |
| `IdunBattleLogic.Entities.Abilities.Active.Loki.EnvDespoiledGroundTileAbility$$CreateTrigger` / `$$CreateBehaviour` | ce que la tuile INFLIGE au tick d'environnement `On(0x14)` | ICI (`DespoiledGroundTileDoT`) |

La CLASSE d'effet 1476 elle-meme (`Idun.Source.IdunBattle.Logic.Entities.Effects.DespoiledGroundEffect`)
et le buff 1478 qu'elle fait poser (`IdunBattle.Entities.Effects.Loki.DespoiledGround_ExtraDamagePctEffect`)
vivent dans `entities/effects/loki/status.py` (frontiere declaratif/imperatif : la CONTRIBUTION de degat
est une donnee d'effet, le DoT est une Operation appelee par une feuille DSL).

## RE native (decompile ghidra, build `gqfc5mff6c`)

`EnvDespoiledGroundTileAbility$$CreateTrigger`
```
On(0x14 = TurnStart_EnvironmentEffects, 1)
  & AmountIsGreaterThanZero( Count( EntitiesWithAnyEffect(df@0x78, 0x5c4, 2) ) )
```
= STRICTEMENT la meme forme que `IdunBattleLogic.Entities.Abilities.Active.Loki.EnvFireTileAbility$$
CreateTrigger` (`On(0x14) & Count(EntitiesWithAnyEffect(5)) > 0`) -> meme abstraction de port :
un `TileEffectTrigger` par tuile PORTEUSE de l'effet, le `Foreach`/`Count` etant resolu par le dispatch.

`EnvDespoiledGroundTileAbility$$CreateBehaviour`
```
targets = UnitsWithoutTraits( df@0x88, [0x1b = 27 Steppable, 0x19 = 25 Immune], 3 )
        & Units( EntitiesWithAnyEffect(df@0x78, 0x5c4, 2), 1, 1 )

Foreach( targets,
    AttackWithAbilityDamage(
        Tiles(elem@0x180),                                  # CASTER = la TUILE
        elem@0x180,                                         # CIBLE  = l'occupant
        RandomAmount( PercentageOf( StatAmount(elem, Health=5, Maximum=2), EffectConfig(9) ),
                      PercentageOf( StatAmount(elem, Health=5, Maximum=2), EffectConfig(10) ) ),
        AbilityOrEffect(0x5c4),                             # source du degat = l'EFFET DespoiledGround
        { , Direct(Nullable(0xf)) } )
  + If( IsTurnOf(elem) & HasTrait(elem, 0x7ea = 2026 Chaos) & NOT HasTrait(elem, 0x19 = 25 Immune),
        AddEffect( 0x5c6 = 1478, AbilityStateReference, elem@0x180, df@0xc0 = Direct(1) ) ) )
```

### Les trois lectures qui font le nombre

1. **`EffectConfig(9)` / `EffectConfig(10)`** = `IdunBattle.Core.Services.BattleQuery$$GetEffectConfig`,
   dict peuple par `$$InitEffectConfig` depuis la section `Effect` de la BattleConfiguration, INDEXE
   par l'ordre de ses entrees. Cet ordre (seed-bc.json) est
   `0 PinnedDmgReductionPct · 1 PinnedMovementReduction · 2 StunnedMovement · 3 StunnedDmgReductionPct ·
    4 MarkerlightDmgBonusPct · 5 IceCritDmgBonusPct · 6 ContaminatedArmorReductionPct ·
    7 MachineVengeanceExtraPct · 8 DespoiledGroundExtraDmgPct · 9 DespoiledGroundMinDmgPct ·
    10 DespoiledGroundMaxDmgPct`.
   TRIPLE recoupement de l'indexation 0-based : `6 -> ContaminatedArmorReductionPct` (deja RE'd #132),
   `8 -> DespoiledGroundExtraDmgPct` (= la cle citee VERBATIM par l'i2
   `UnitEffects/DespoiledGround_ExtraDamagePct_Description`), et `9/10` qui donnent MIN/MAX du DoT.
   => **le DoT vaut un tirage uniforme dans `[6 % , 9 % ]` de la PV MAX de l'occupant** (valeurs BC,
   PAS hardcodees : lues via `bc_effect_config`).

2. **`Direct(Nullable(0xf))`** = le champ `+0x90` de l'`AbilityDamageBehaviour`. `0xf = 15` est un
   membre d'`IdunBattle.Entities.Enum.DamageProfileType` : **`15 = DirectDamage`** (`PiercingRatio`
   100). La lecture « ce Nullable est le DamageProfileType du coup » est CORROBOREE par le DoT de feu,
   ou le meme champ vaut `3` et ou le port utilise `Flame` (`3 = Flame` dans la meme enum) — un choix
   valide LIVE (net 477 = base 1908 x PiercingRatio 25 %). Deux points independants, meme enum.

3. **`RandomAmount`** consomme UN tirage `IdunBattle.Utils.PRNG.IntBasedMersenneTwister$$NextInternal(
   min, max + 1)` par occupant affecte (mirror `IdunBattle.Entities.Formulas.RandomAmount$$Calculate`,
   cf. `entities/formulas.py`).

### Ce qui reste hors modele (FLAGGE)

- `IsTurnOf(elem)` du 2e volet est porte par le noeud DSL `IsTurnOf` (`entities/triggers.py`), qui lit
  `ctx.current_player_id` : le tick `On(0x14)` est emis par `IdunBattle.Operations.StartTurnOperation$$
  Execute` APRES que `ChangeTurnOperation` a pose le joueur courant -> l'unite ne recoit le buff qu'au
  debut de SON tour.
- `EnvDespoiledGroundTileAbility` est une ability d'ENVIRONNEMENT : elle n'est pas rattachee a une unite
  du pool. Comme `EnvFireTileAbility`, le port la fait porter par la TUILE (registre `EFFECT_TRIGGERS`),
  ce qui est le seul chemin d'atteignabilite offline ET le seul chemin natif observable (la tuile est
  l'entite qui porte l'effet).
"""
from __future__ import annotations

from typing import Optional

from ....state import State
from ....abilities.behaviours import AttackWithAbilityDamage, AddEffect, entities_from_state
from .....entities.stats import StatType, StatPart
from .....entities.traits import UnitTrait, has_any_trait
from .....entities.effect_type import EffectType
from .....entities.effects.magnitude import bc_effect_config
from .....entities.formulas import PercentageOf, StatAmount, RandomAmount
from .....entities.selectors import Target
from .....entities.behaviours import op_add, If as IfBehaviour
from .....entities.triggers import TriggerAnd, Not, HasTrait, IsTurnOf
from .....dsl.base import Const
from .....dsl.effects import ExecutionContext
from .....dsl.event_trigger_type import EventTriggerType
from ..base import TileEffectTrigger, TriggerEvent, _unit_trait_names

DESPOILED_GROUND_TILE = int(EffectType.DespoiledGround)            # 0x5c4 = 1476 (effet de TUILE)
DESPOILED_GROUND_EXTRA_DMG = int(EffectType.DespoiledGround_ExtraDamagePct)   # 0x5c6 = 1478 (buff Chaos)
# `EffectConfig(9)` / `EffectConfig(10)` de `EnvDespoiledGroundTileAbility$$CreateBehaviour` — cles de la
# section `Effect` de la BattleConfiguration (indexation 0-based, cf. en-tete). LUES, jamais hardcodees.
DESPOILED_MIN_PCT_KEY = "DespoiledGroundMinDmgPct"   # EffectConfig(9)  = 6 (% de la PV MAX)
DESPOILED_MAX_PCT_KEY = "DespoiledGroundMaxDmgPct"   # EffectConfig(10) = 9 (% de la PV MAX)
# `UnitsWithoutTraits([0x1b = 27 Steppable, 0x19 = 25 Immune])` — MEME couple que le DoT de feu
# (`EnvFireTileAbility$$CreateBehaviour`) : tokens marchables et immunises sont EXCLUS du DoT.
DESPOILED_IMMUNE_TRAITS = (UnitTrait.Steppable, UnitTrait.Immune)
# `Direct(Nullable(0xf))` -> `DamageProfileType.DirectDamage` (15). PiercingRatio 100 (gameconfig).
DESPOILED_PROFILE = "DirectDamage"
# `HasTrait(elem, 0x7ea)` / `NOT HasTrait(elem, 0x19)` du 2e volet.
DESPOILED_BUFF_TRAIT = UnitTrait.Chaos          # 0x7ea = 2026
DESPOILED_BUFF_EXCLUDE_TRAIT = UnitTrait.Immune  # 0x19 = 25


def _is_immune_to_despoiled_ground(state: State, unit_id: int) -> bool:
    """`UnitsWithoutTraits(df@0x88, [0x1b = 27 Steppable, 0x19 = 25 Immune], 3)` de
    `IdunBattleLogic.Entities.Abilities.Active.Loki.EnvDespoiledGroundTileAbility$$CreateBehaviour` : le
    DoT EXCLUT les occupants portant `Steppable` (tokens marchables : decoys/mines) OU `Immune`.
    Le couple de traits est LITTERALEMENT le meme que celui du DoT de feu — deux abilities natives
    distinctes qui posent le meme filtre ; on garde donc DEUX helpers homonymes de leur ability
    respective plutot qu'un « helper tile-DoT commun » invente."""
    return has_any_trait(_unit_trait_names(state, unit_id), DESPOILED_IMMUNE_TRAITS)


def env_despoiled_ground_tile_tree(min_pct: int, max_pct: int, profile: str, rng=None):
    """Feuille de `IdunBattleLogic.Entities.Abilities.Active.Loki.EnvDespoiledGroundTileAbility$$
    CreateBehaviour` (MIRROR 1:1 du decompile, cf. en-tete du module) :

        AttackWithAbilityDamage( Tiles(elem), elem,
                                 RandomAmount( PercentageOf(StatAmount(elem, Health, Max), cfg9),
                                               PercentageOf(StatAmount(elem, Health, Max), cfg10) ),
                                 AbilityOrEffect(0x5c4), Direct(Nullable(0xf = DirectDamage)) )
      + If( IsTurnOf(elem) & HasTrait(elem, Chaos) & NOT HasTrait(elem, Immune),
            AddEffect(0x5c6 = 1478, stateRef, elem, Direct(1)) )

    Le `Foreach(<selecteur>)` natif (occupants non-immunes des tuiles DespoiledGround) est resolu EN
    AMONT par le dispatch runner (`TileEffectTrigger` par tuile portant 0x5c4 = `EntitiesWithAnyEffect`,
    `_unit_on_tile` = l'occupant, `_is_immune_to_despoiled_ground` = le `UnitsWithoutTraits`) — MEME
    DSL-ification deferree que `env_fire_tile_tree` (#216). L'occupant RESOLU arrive par `Target()` ;
    sa PV MAX via `StatAmount(Target(), Health, Maximum)`.

    CORRESPONDANCE DES SELECTEURS (`IdunBattle.Entities.Behaviours.AttackBehaviour$$Execute` : +0x50 =
    CASTER resolu en UNE entite, +0x58 = la LISTE des cibles) : la factory recoit `(Tiles(elem), elem)`
    -> CASTER = la TUILE, CIBLE = l'occupant. `source_ref` non passe cote port -> `entities.caster` =
    `owner_id` = la tuile, MEME entite que le natif (attribution de mort incluse).

    `is_melee=None` : l'`AbilityOrEffect` du coup est l'EFFET 0x5c4, pas une ability a `attackRangeType`
    -> `IdunBattle.Core.Services.BattleQuery$$GetAbilityAttackRangeType` rend 0 (absent), donc
    `IsMeleeAttack` ET `IsRangedAttack` sont FAUX (meme table de verite que le DoT de feu).

    `min_pct`/`max_pct`/`profile`/`rng` passes par l'appelant (BC + `state.rng`) pour eviter tout
    couplage d'import — meme convention que `env_fire_tile_tree`."""
    max_hp = StatAmount(Target(), int(StatType.HEALTH), int(StatPart.MAXIMUM))
    amount = RandomAmount(PercentageOf(Const(min_pct), max_hp),
                          PercentageOf(Const(max_pct), max_hp), rng)
    dot = AttackWithAbilityDamage(Target(), profile, amount, is_melee=None, hits=1,
                                  native_operation="ability")
    # 2e volet : le buff +%degat pour l'occupant CHAOS, au debut de SON tour. `Direct(1)` (df@0xc0) est
    # une duree deja en TOURS -> `duration_turns=1` (et non `TurnsFromRounds`), cf. `_resolve_duration`.
    buff = IfBehaviour(
        TriggerAnd(TriggerAnd(IsTurnOf(Target()), HasTrait(Target(), int(DESPOILED_BUFF_TRAIT))),
                   Not(HasTrait(Target(), int(DESPOILED_BUFF_EXCLUDE_TRAIT)))),
        AddEffect(DESPOILED_GROUND_EXTRA_DMG, EffectType.DespoiledGround_ExtraDamagePct.name,
                  Target(), duration_rounds=None, duration_turns=1))
    return op_add(dot, buff)


class DespoiledGroundTileDoT(TileEffectTrigger):
    """`EnvDespoiledGroundTileAbility` (`$$CreateTrigger` = `On(0x14) & Count(EntitiesWithAnyEffect(
    0x5c4)) > 0` ; `$$CreateBehaviour`) — ce que la tuile DespoiledGround INFLIGE au tick d'environnement.

    Au tick `On(0x14 = TurnStart_EnvironmentEffects)`, l'occupant NON-immune d'une tuile DespoiledGround
    subit un degat tire uniformement dans `[DespoiledGroundMinDmgPct, DespoiledGroundMaxDmgPct]` % de sa
    PV MAX (BC : 6 % .. 9 %), porte par le profil `DirectDamage` (perçage 100 %) via la famille ABILITY
    (`IdunBattle.Operations.AbilityDamageOperation`) — donc armure/mods DEFENSEUR/block/bouclier + etage
    LIMITES mode 2 (member-cap / Resilient), AUCUN crit. Puis, si c'est SON tour et qu'il est **Chaos**
    (2026) sans **Immune** (25), il recoit `DespoiledGround_ExtraDamagePct` (1478) pour 1 TOUR.

    behaviour = arbre DSL `env_despoiled_ground_tile_tree()` (mirror 1:1). Mort routee par
    `_fire_death_if_killed` (source = la tuile). Decay via `on_turn_end`
    (`DefaultAmountOfRounds(0x5c4) = 2 rounds` -> `ConvertRoundsToTurns`, #98/#138).

    ⚠ RNG : ce trigger consomme UN `next_internal` par occupant affecte et par tick (le `RandomAmount`
    natif). Aucune regression possible sur l'existant : avant #85, l'effet 1476 ne pouvait PAS etre pose
    offline (ni vecteur `On(0x10)`, ni classe d'effet), donc ce trigger ne fire jamais sur un etat qui ne
    porte pas deja de DespoiledGround."""
    effect_type = DESPOILED_GROUND_TILE
    event_ids = (EventTriggerType.TurnStart_EnvironmentEffects,)

    def matches(self, state: State, ev: "TriggerEvent") -> bool:
        return self._unit_on_tile(state) is not None

    def execute_behaviour(self, state: State, ev: "TriggerEvent") -> Optional[dict]:
        uid = self._unit_on_tile(state)
        if uid is None:
            return None
        if _is_immune_to_despoiled_ground(state, uid):    # `UnitsWithoutTraits([Steppable, Immune])`
            return None
        lo = bc_effect_config(DESPOILED_MIN_PCT_KEY)      # EffectConfig(9)  (BC, non hardcode)
        hi = bc_effect_config(DESPOILED_MAX_PCT_KEY)      # EffectConfig(10) (BC, non hardcode)
        if not lo or not hi:
            return None
        ectx = ExecutionContext(state=state, rng=state.rng)
        env_despoiled_ground_tile_tree(int(lo), int(hi), DESPOILED_PROFILE, state.rng).execute(
            entities_from_state(state, self.owner_id, uid), ectx)
        hit = next((p for n, p in ectx.emitted if n == "AttackWithAbilityDamage"), None)
        atk = (hit or {}).get("attack")
        placed = [p.get("effect_type") for n, p in ectx.emitted
                  if n == "AddEffect" and p.get("placed")]
        if not (atk and atk.get("total")) and not placed:
            return None
        return {"tile_effect": "DespoiledGround", "tile": self.owner_id, "unit": uid,
                "dot": (atk or {}).get("total"), "hp_before": (atk or {}).get("hp_before"),
                "hp_after": (atk or {}).get("hp_after"), "placed": placed,
                "on_event": ev.event_id}
