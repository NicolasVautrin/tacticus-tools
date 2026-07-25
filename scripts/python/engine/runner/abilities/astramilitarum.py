"""Abilities actives ASTRA MILITARUM (namespace natif `IdunBattleLogic.Entities.Abilities.Active.Loki.*`).

SupremeCommander (1028, `astraCreed` « Lord Castellan Creed ») — PREMIER consommateur porte du
debloqueur `PerformAIAction` (`abilities/behaviours/ai_control.py` + `operations/summon_ai.py::
ComputerActionOperation`).
"""
from __future__ import annotations

from typing import Optional, TYPE_CHECKING

import gameconfig as GC

from .base import ActiveAbility
from ..components import StatsComponent, get_ability_stat_modification
from ...dsl.base import Const
from ...dsl.effects import ExecutionContext
from ...entities.active_ability_type import ActiveAbilityType
from ...entities.behaviours import AtomicGroup
from ...entities.selectors import (AdjacentTiles, CanAddUnit, Caster, CasterTile,
                                   SurroundingFriends, UnitsWithIds)
from .behaviours import Spawn, PerformAIAction, entities_from_state

if TYPE_CHECKING:
    from ..state import State

# Index des constantes lues par `SupremeCommanderAbility.ExecuteBehaviour @18120df30`
# (`AbilityConfiguration.Get*Constant(config, <index>)`) -> cle gameconfig correspondante.
CONST_UNIT_ID = 0x00           # GetStringConstant(0)       -> "unitId"          = astraSmnGuardsman
CONST_NR_OF_SUMMONS = 0x10     # GetNumberConstant(0x10)    -> "nrOfSummons"     = 2
CONST_RANGE = 0x16             # GetNumberConstant(0x16)    -> "range"           = 2
CONST_AFFECTED_UNIT_IDS = 0x3e  # GetStringArrayConstant(0x3e) -> "affectedUnitIds"


def supreme_commander_spawn_tree(count: int) -> AtomicGroup:
    """1er noeud natif de `SupremeCommanderAbility.ExecuteBehaviour @18120df30` :
        `ExecuteAtomic( Spawn(caster@0x160,
                              PickRandomly(CanAddUnit(AdjacentTiles(caster@0x160)), count, 0x7fffffff),
                              unitId = GetStringConstant(0),
                              SpawnUnitOptions.WithStatsFromConfig(config, level)),
                        entities, 0x48 )`
    `count` = `GetNumberConstant(0x10)` **+** `GetAbilityStatModification(caster, 0x10)` (ADDITIF, calcule
    par la classe d'ability, cf. `SupremeCommanderAbility.execute_behaviour`). Le `PickRandomly` est FOLDE
    dans la feuille `Spawn` (`pick_n`), qui seule voit `ectx.state.rng`."""
    tiles = CanAddUnit(AdjacentTiles(Caster()))
    return AtomicGroup(Spawn(tiles, "SupremeCommander", pick_n=count))


def supreme_commander_ai_tree(radius: int, affected_ids) -> PerformAIAction:
    """2e noeud natif de `SupremeCommanderAbility.ExecuteBehaviour @18120df30` :
        `Execute( PerformAIAction( UnitsWithIds( SurroundingFriends(caster@0x160, casterTile@0x168,
                                                                    radius, 1, 3),
                                                 GetStringArrayConstant(0x3e) ),
                                   asGroup=1, resetTurnFlags=1 ),
                  entities )`
    `SurroundingFriends` @180dfc710 se deplie en `Friends(caster, Units(SurroundingTiles(casterTile, 1,
    radius) - Tiles(casterTile)))` = allies VIVANTS a distance hex <= radius du caster, caster EXCLU —
    exactement le noeud `SurroundingFriends(center, radius)` deja porte.
    `radius` = `GetNumberConstant(0x16)`, **OVERRIDE** par `GetAbilityStatModification(caster, 0x16)`
    quand elle est non nulle (cf. la classe d'ability : semantique de consommation DIFFERENTE de celle
    du count, qui est additive).

    Le CENTRE porte est `CasterTile()` = le `casterTile@0x168` natif (le noeud `SurroundingFriends`
    du port prend une POSITION en centre, cf. son homologue `SurroundingUnits(OwnerTile(), ...)`),
    le filtre d'equipe restant relatif au caster (`Friends(caster@0x160, ...)`)."""
    friends = SurroundingFriends(CasterTile(), Const(int(radius)))
    return PerformAIAction(UnitsWithIds(friends, affected_ids), as_group=True, reset_turn_flags=True)


class SupremeCommanderAbility(ActiveAbility):
    """`SupremeCommanderAbility.ExecuteBehaviour @18120df30` (id 1028, `astraCreed` « Creed »,
    AstraMilitarum) — MIRROR du DECOMPILE.

    Corps natif (ordre de lecture) :
        unitId   = GetStringConstant(config, 0)                                 # astraSmnGuardsman
        nSummons = GetNumberConstant(config, 0x10)                              # nrOfSummons = 2
        ids      = GetStringArrayConstant(config, 0x3e)                         # affectedUnitIds
        modN     = GetAbilityStatModification(caster@0x168, VarOrConst(0x10))   # @18120e09b
        range    = GetNumberConstant(config, 0x16)                              # range = 2
        modR     = GetAbilityStatModification(caster@0x168, VarOrConst(0x16))   # @18120e17a
        if (modR != 0) range = modR                                             # OVERRIDE (pas additif)
        opts     = SpawnUnitOptions.WithStatsFromConfig(config, level)
        spawnB   = Spawn(caster, PickRandomly(CanAddUnit(AdjacentTiles(caster)), nSummons + modN), unitId, opts)
        aiB      = PerformAIAction(UnitsWithIds(SurroundingFriends(caster, casterTile, range, 1, 3), ids), 1, 1)
        AActiveAbility.ExecuteAtomic(this, spawnB, entities, 0x48)
        AActiveAbility.Execute(this, aiB, entities)

    Les DEUX consommations de `GetAbilityStatModification` ont des semantiques DIFFERENTES (lu, pas
    devine) : **ADDITIVE** pour `nrOfSummons`, **OVERRIDE si non nulle** pour `range`. La seule source
    native de ces modifications est `ListenUpMaggotsEffect` @180f56590 (passif de `astraSmnKell`,
    +1 summon / range=3) — NON portee (cf. `components.ActiveAbilityModificationsComponent`), donc
    offline les deux modifications valent 0. CONFRONTE LIVE : meme avec Kell VIVANT en jeu au moment du
    cast, le natif summon 2 gardes -> modification NULLE cote natif aussi (2 probes, cf.
    docs/rl/case-perform-ai-action.md).

    DEUX executions top-level distinctes (`ExecuteAtomic` puis `Execute`) -> DEUX arbres, executes
    successivement. Le contexte `entities` est RE-MATERIALISE entre les deux : l'`AbilityEntities` natif
    porte une REF d'etat (les selecteurs du 2e arbre VOIENT les gardes tout juste spawnes), alors que le
    `DslContext` du port fige la LISTE d'unites a sa construction (`entities_from_state`). Sans cette
    re-materialisation, `SurroundingFriends` manquerait les gardes du 1er arbre = no-op silencieux.

    Retour : {spawned, ai_units, ai_results, count, radius, dsl}."""
    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.SupremeCommander)   # 1028

    ABILITY_ID = "SupremeCommander"

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        consts = (GC.ability(self.ABILITY_ID) or {}).get("constants") or {}
        caster = state.get_entity(caster_id)
        if caster is None:
            return None
        # --- constantes + modifications d'ability (mirror des 2 call-sites @18120e09b/@18120e17a) ---
        n_summons = int(consts.get("nrOfSummons") or 0)
        n_summons += get_ability_stat_modification(caster, CONST_NR_OF_SUMMONS)     # ADDITIF
        radius = int(consts.get("range") or 0)
        mod_range = get_ability_stat_modification(caster, CONST_RANGE)
        if mod_range != 0:                                                          # OVERRIDE
            radius = mod_range
        affected_ids = consts.get("affectedUnitIds") or ""

        ectx = ExecutionContext(state=state, rng=state.rng)
        # 1) `ExecuteAtomic(spawnB, entities, 0x48)`
        supreme_commander_spawn_tree(n_summons).execute(
            entities_from_state(state, caster_id, target_id), ectx)
        # 2) `Execute(aiB, entities)` — entities RE-MATERIALISE (cf. docstring : ref d'etat natif).
        supreme_commander_ai_tree(radius, affected_ids).execute(
            entities_from_state(state, caster_id, target_id), ectx)

        spawned = [p["unit"] for n, p in ectx.emitted if n == "SpawnUnit"]
        ai = next((p for n, p in ectx.emitted if n == "PerformAIAction"), {})
        return {"spawned": spawned, "ai_units": ai.get("units") or [],
                "ai_results": ai.get("results") or [], "count": n_summons, "radius": radius,
                "dsl": True}
