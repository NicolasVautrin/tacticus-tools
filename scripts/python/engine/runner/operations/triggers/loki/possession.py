"""`Possession` (passif de `blackPossession` << Archimatos >>, `TriggeredAbilityType` 1034) -- #955.

i2 : « Each time Archimatos kills an enemy unit with a melee attack, he summons a Bloodletter in its
hex. Each time he kills an enemy unit with a ranged attack, he summons a Blue Horror in its hex. »

================================================================================================
RE (decompile ghidra, build `rnca9r7q6c`) -- recensement par le bloc `methodPointers`
================================================================================================
`IdunBattleLogic.Entities.Abilities.Active.Loki.PossessionAbility` occupe **3 slots** du tableau de
pointeurs (`CreateTrigger`, `CreateBehaviour`, `.ctor`), dont **2 corps PROPRES** ; le `.ctor` est
fondu par l'ICF avec `UnityEngine.Scripting.RequiredByNativeCodeAttribute$$.ctor` (corps vide).
Le passif n'a **ni effet, ni playbook** : les classes `AttemptedPossession*` que le nom laisse
croire siennes appartiennent a l'ACTIVE `ActiveAbilityType.AttemptedPossession = 1101` de
`thousSorcerer`, deja portee (`runner/abilities/loki/attempted_possession.py`).

## `PossessionAbility$$CreateTrigger`

      ( On(0x35 = EventTriggerType.PostUnitKill, ownerNeedsToBeAlive = true)
        & get_OwnerIsActor )
    & ( AreEnemies(Owner@<DSLSelectors+0x30>, Target@<DSLSelectors+0x60>, 0)
        & NOT IsObjectOrSteppable(Target@+0x60) )
    & NOT TriggeringAbilityIs( 0x438 = TriggeredAbilityType.ItsGonnaBlow )

Le litteral du dernier conjoint n'est PAS lisible au decompile (`AbilityOrEffect$$op_Implicit`
recoit sa valeur en registre) : il est lu AUX OCTETS -- `BA 38 04 00 00` = `mov edx, 0x438` a
`PossessionAbility$$CreateTrigger+0x13a`, juste avant le `call`.

## `PossessionAbility$$CreateBehaviour`

    unitId  = AbilityConfiguration$$GetStringConstant(cfg, 0 = AbilityConstantType.unitId)
    unitId2 = AbilityConfiguration$$GetStringConstant(cfg, 4 = AbilityConstantType.unitId_2)
    optsA   = SpawnUnitOptions$$WithStatsFromConfig (cfg, abilityState, null, null)   # -> ordinal 1
    optsB   = SpawnUnitOptions$$WithStatsFromConfig2(cfg, abilityState, null, null)   # -> ordinal 2
    hex     = PickRandomly( FreeTilesOrAdjacentFreeTiles( Tiles(Target@+0x60) ),
                            amount = 1, allowDuplicates = false,
                            maxDuplicatesAllowed = 0x7fffffff, ignoreForcedTargets = false )
    cond    = NOT IsDefeatedByMeleeAttack(Target@+0x60, countRevived = true,
                                          countResurrected = true)
    return    DSLBehaviors$$If( cond,
                                Spawn(Owner@+0x30, hex, unitId2, optsB),   # kill NON-melee
                                Spawn(Owner@+0x30, hex, unitId,  optsA) )  # kill MELEE

`WithStatsFromConfig` et `WithStatsFromConfig2` sont DEUX THUNKS vers la meme surcharge a 5
arguments, avec `ordinal = 1` / `ordinal = 2` ; c'est l'ordinal qui choisit le jeu de variables
(`summonHp`/`summonDmg` contre `summonHp_2`/`summonDmg_2`). Cote port c'est exactement le
`key_suffix` que `operations/spawn.py::build_summon_context` porte deja (`""` / `"_2"`).

`FreeTilesOrAdjacentFreeTiles(tiles)` (`IdunBattleLogic.Entities.DSLSelectors$$
FreeTilesOrAdjacentFreeTiles`) = `Otherwise( CanAddUnit(tiles, isSteppable),
CanAddUnit(AdjacentTiles(tiles), isSteppable) )` avec `isSteppable = <DSLTriggers+0x48>` -- le slot
que le port identifie deja comme `op_LogicalNot(YesTrigger)`, donc `allowSteppable` **TOUJOURS
VRAI** a ce call-site (cf. la docstring de `entities/selectors/tiles.py::CanAddUnit`). L'arbre est
donc exprimable SANS nouveau noeud, avec les quatre selecteurs deja portes.

`IsDefeatedByMeleeAttack(u, r, s)` = `AmountIsGreaterThanZero(UnitsDefeatedByMeleeAttack(u, r, s))`,
et `IdunBattle.Entities.Selectors.UnitsDefeatedByMeleeAttackSelector$$IsValidUnit` retient `u` ssi
son marqueur natif `UnitComponent + 0x178` (« defait par une attaque de MELEE », ecrit avec
`+0x179 = 1` par `KillUnitOperation$$Execute` et par `FleeOperation$$RecordFlee`, ou il vaut
`attackRangeType == 1`) est pose ET qu'elle est en etat de defaite (`HasFlag(9 = Fled)` |
`HealthComponent$$IsDead` | `countRevived && HasFlag(0x14)` | `countResurrected && HasFlag(0xe)`).

================================================================================================
FORME DU PORT (doctrine #149) ET RESIDUS NOMMES
================================================================================================
* `CreateTrigger` COLLAPSE imperativement dans `matches` (meme patron que `CosmicHorrorOnKillAbility`,
  l'autre consommateur porte d'`On(PostUnitKill)`), sauf `IsObjectOrSteppable`, qui passe par le
  foyer DSL partage `entities/triggers.py::is_object_or_steppable` (8 call-sites natifs).
* `CreateBehaviour` = un ARBRE DSL dont la feuille `Spawn` appelle l'Operation portee ; seul le
  `If(cond, ., .)` est collapse -- son `cond` est le marqueur melee, qui n'a PAS de noeud porte.

RESIDUS :
* **marqueur « defait par une attaque de MELEE »** -- le natif lit le champ persistant
  `UnitComponent+0x178` ; le vecteur `On(PostUnitKill)` du port ne transporte AUCUN canal melee
  (`move_death.post_unit_kill_triggers` pose `ranged=False` en dur). On approxime donc
  POSITIONNELLEMENT via `_is_ranged_position` -- STRICTEMENT le meme choix, le meme helper et le
  meme residu que `DawnBladeHealAbility` (#317), qui lit le MEME marqueur natif. Ici la
  degradation n'est ni permissive ni restrictive : elle choisit le MAUVAIS SUMMON (Bloodletter au
  lieu de Blue Horror) quand le coup fatal est une attaque a distance depuis une tuile adjacente.
* `countRevived = true` / `countResurrected = true` : les deux drapeaux (`HasFlag(0x14)` revivee /
  `HasFlag(0xe)` ressuscitee) ne sont pas modelises -- dans tout regime porte, une victime REVIVEE
  ne parvient pas jusqu'a `On(PostUnitKill)` avec `alive = False`, donc la seule branche atteignable
  est `HealthComponent.IsDead` (meme constat que #317).
* `NOT TriggeringAbilityIs(ItsGonnaBlow)` : le canal `TriggerEvent.triggering_ability` est
  INCONDITIONNELLEMENT VIDE sur le vecteur MORT (`triggers/base.py`, mirror du champ natif
  `AbilityEntities.CurrentAbility` que `KillUnitOperation` ne renseigne pas). Le gate est donc
  ECRIT mais ne peut pas mordre tant que ce canal n'est pas seede -- il est conserve parce qu'il
  est LU au decompile, et parce que le jour ou le canal existera il mordra sans rien changer
  d'autre. Sens de la degradation : PERMISSIF (un kill par `ItsGonnaBlow` ferait quand meme
  apparaitre un summon). Residu #955-r1.
* `maxDuplicatesAllowed = 0x7fffffff` / `ignoreForcedTargets = false` du `PickRandomly` : sans
  objet pour `amount = 1` sans duplicata (`allowDuplicates = false`), transcrits ici, non portes.
"""
from __future__ import annotations

from typing import Optional

import gameconfig as GC

from .....dsl.effects import ExecutionContext
from .....dsl.event_trigger_type import EventTriggerType
from .....entities.ability_constant_type import AbilityConstantType
from .....entities.selectors.accessors import Target
from .....entities.selectors.geometry import Otherwise
from .....entities.selectors.tiles import AdjacentTiles, CanAddUnit
from .....entities.selectors.units import Tiles
from .....entities.triggered_ability_type import TriggeredAbilityType
from .....entities.triggers import is_object_or_steppable
from ....abilities.behaviours.context import entities_from_state
from ....abilities.behaviours.summon import Spawn
from ....components import OwnerComponent, UnitComponent
from ....state import State
from ..base import (TriggeredAbility, TriggerEvent, triggered_ability_state,
                    _is_ranged_position)

ABILITY_ID = "Possession"
#: `AbilityConfiguration$$GetStringConstant(cfg, 0)` / `(cfg, 4)` -- LUS au decompile, jamais devines
#: (recopier `unitId` sur un call-site qui lit `unitId_2` rend `None` = spawn silencieusement absent).
CONST_UNIT_MELEE = AbilityConstantType.unitId.name           # 0 -> blackSmnBloodletter
CONST_UNIT_RANGED = AbilityConstantType.unitId_2.name        # 4 -> thousSmnBlueHorror
#: L'`ordinal` de `SpawnUnitOptions$$WithStatsFromConfig` / `...2`, cote port = le suffixe de cle
#: gameconfig lu par `build_summon_context` (`summonHp` vs `summonHp_2`).
STAT_SUFFIX_MELEE = ""                                       # ordinal 1
STAT_SUFFIX_RANGED = "_2"                                    # ordinal 2

_ON_POST_UNIT_KILL = int(EventTriggerType.PostUnitKill)      # `On(0x35, ownerNeedsToBeAlive = true)`
#: 4e conjoint : `NOT TriggeringAbilityIs(0x438)` -- litteral lu AUX OCTETS (cf. en-tete).
ITS_GONNA_BLOW = int(TriggeredAbilityType.ItsGonnaBlow)      # 0x438 = 1080
#: `NOT IsObjectOrSteppable(Target@+0x60)` -- foyer DSL partage.
_IS_OBJECT_OR_STEPPABLE = is_object_or_steppable(Target())


def possession_spawn_tree(ability_state, ranged_kill: bool) -> Spawn:
    """Le terme `Spawn` retenu par le `If` de `PossessionAbility$$CreateBehaviour`, noeud pour noeud :

        Spawn( Owner@+0x30,
               PickRandomly( FreeTilesOrAdjacentFreeTiles(Tiles(Target@+0x60)), 1, false, ..., false),
               GetStringConstant(cfg, <0 | 4>),
               WithStatsFromConfig{,2}(cfg, abilityState, null, null) )

    `FreeTilesOrAdjacentFreeTiles(tiles)` est DEPLIE en son corps natif --
    `Otherwise(CanAddUnit(tiles, isSteppable), CanAddUnit(AdjacentTiles(tiles), isSteppable))` avec
    `isSteppable` toujours VRAI a ce call-site (cf. en-tete).

    ⚠ **ET LES TROIS AUTRES CONSOMMATEURS PORTES ONT RAISON DE NE PAS PORTER LA BRANCHE** (#955-r2,
    ferme EN REFUS -- ce paragraphe annoncait l'inverse). Le noeud natif a **DEUX surcharges**, et
    elles ne prennent pas leur trigger au meme endroit :

      * `FreeTilesOrAdjacentFreeTiles(tiles)` -- 2 arguments -- le lit dans son PROPRE corps, a
        `<dsl>.<+0x88 = DSLTriggers>.<+0x48>`. C'est CE call-site-ci ;
      * `FreeTilesOrAdjacentFreeTiles(tiles, isSteppable)` -- 3 arguments -- le recoit de l'APPELANT,
        et les trois appelants portes (`Ambush_SummonAbility$$GetSummonBehaviour`,
        `CosmicHorror_OnKillAbility$$CreateBehaviour`,
        `HypersensoryAbilitiesAbility_MoveAndSpawnDecoy$$CreateBehaviour`) passent tous
        `<DSLTriggers>+0x40` -- LU aux octets, `mov r8, [reg+0x40]`.

    Or `IdunBattleLogic.Entities.DSLTriggers$$.ctor` pose `+0x40` = le trigger NU et `+0x48` =
    `op_LogicalNot(<le meme type>)`, et `CanAddUnitTileSelector$$Select` **INVERSE** ce qu'il recoit
    (`allowSteppable = !ShouldTrigger`). Donc `+0x40` -> `allowSteppable` **FAUX**, `+0x48` ->
    **VRAI**. Les trois collapses sont FIDELES ; leur ajouter la branche serait PERMISSIF (le
    summon/decoy se poserait sur un mur, un decor ou un token). Garde :
    `tests/engine/runner/test_955r2_free_tiles_steppable_offline.py`.

    `PickRandomly(., 1)` est porte par le `pick_n` de la feuille (le tirage vit dans la feuille, qui
    seule voit `ectx.state.rng` -- meme convention que `SupremeCommander`)."""
    tiles = Tiles(Target(), as_ids=True)                     # `Tiles(Target@+0x60)`
    free = Otherwise(CanAddUnit(tiles, allow_steppable=True),
                     CanAddUnit(AdjacentTiles(tiles), allow_steppable=True))
    return Spawn(free, ABILITY_ID, pick_n=1,
                 unit_id_constant=(CONST_UNIT_RANGED if ranged_kill else CONST_UNIT_MELEE),
                 stat_key_suffix=(STAT_SUFFIX_RANGED if ranged_kill else STAT_SUFFIX_MELEE),
                 ability_state=ability_state)


class PossessionSummonOnKillAbility(TriggeredAbility):
    """`PossessionAbility` -- Archimatos acheve un ennemi non-objet : un summon apparait sur l'hex du
    mort (ou, si elle n'est pas libre, sur une tuile libre adjacente). MELEE -> `unitId`
    (`blackSmnBloodletter`) avec les stats `summonHp`/`summonDmg` ; a DISTANCE -> `unitId_2`
    (`thousSmnBlueHorror`) avec `summonHp_2`/`summonDmg_2`."""
    event_id = _ON_POST_UNIT_KILL
    TRIGGERED_ABILITY_ID = int(TriggeredAbilityType.Possession)          # 0x40a = 1034

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        # `get_OwnerIsActor` : l'ACTEUR d'`On(PostUnitKill)` est le TUEUR
        # (`move_death.post_unit_kill_triggers` construit l'event avec `actor = killer ?? killed`).
        if ev.actor_id != self.owner_id:
            return False
        victim = ev.dying_id if ev.dying_id is not None else ev.target_id
        if victim is None or victim == self.owner_id:
            return False
        owner, target = state.get_entity(self.owner_id), state.get_entity(victim)
        if owner is None or target is None:
            return False
        # `On(..., ownerNeedsToBeAlive = true)` : un acteur mort n'agit pas.
        ouc = owner.get_component(UnitComponent)
        if ouc is not None and not ouc.alive:
            return False
        oo, to = owner.get_component(OwnerComponent), target.get_component(OwnerComponent)
        if oo is None or to is None or oo.team == to.team:   # AreEnemies(Owner@+0x30, Target@+0x60, 0)
            return False
        # `NOT TriggeringAbilityIs(0x438 = ItsGonnaBlow)` -- canal vide sur le vecteur MORT, cf.
        # residu #955-r1 de l'en-tete : le test est ECRIT, il ne mord que si le canal est seede.
        if ev.triggering_ability is not None and int(ev.triggering_ability) == ITS_GONNA_BLOW:
            return False
        # `NOT IsObjectOrSteppable(Target@+0x60)` -- meme foyer DSL que `BattleFatigueAbility`.
        return not _IS_OBJECT_OR_STEPPABLE.should_trigger(
            entities_from_state(state, self.owner_id, victim))

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        victim = ev.dying_id if ev.dying_id is not None else ev.target_id
        # `If( NOT IsDefeatedByMeleeAttack(Target), Spawn(unitId_2), Spawn(unitId) )` : la branche
        # VRAIE (kill NON-melee) prend `unitId_2`. Marqueur approxime positionnellement (residu).
        ranged_kill = _is_ranged_position(state, int(self.owner_id), int(victim))
        ability_state = triggered_ability_state(state, self.owner_id, ABILITY_ID)
        ectx = ExecutionContext(state=state, rng=state.rng)
        entities = entities_from_state(state, self.owner_id, victim, actor_id=ev.actor_id)
        possession_spawn_tree(ability_state, ranged_kill).execute(entities, ectx)
        spawned = [p["unit"] for n, p in ectx.emitted if n == "SpawnUnit"]
        consts = (GC.ability(ABILITY_ID) or {}).get("constants") or {}
        return {"passive": ABILITY_ID, "owner": int(self.owner_id), "victim": int(victim),
                "ranged_kill": bool(ranged_kill), "spawned": spawned,
                "unit_id": consts.get(CONST_UNIT_RANGED if ranged_kill else CONST_UNIT_MELEE)}
