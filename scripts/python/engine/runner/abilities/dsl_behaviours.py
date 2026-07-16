"""Behaviours d'ability portes en ARBRES DSL EXECUTABLES (#149 slice-2b) + feuilles CONCRETES
(bridge dsl -> runner Operations) + builder `entities_from_state`.

Les combinateurs/EffectNode generiques vivent dans `engine.dsl.effect_nodes` (couche dsl) ; ICI les
feuilles MINCES qui EMETTENT les Operations DEJA portees (`runner/operations`) et les arbres d'ability
(mirror `<Ability>.CreateBehaviour`). `entities_from_state` construit le `DslContext` (= l'`entities`
natif lu par les selecteurs) depuis le `State` runner. cf. docs/rl/dsl-effect-nodes.md.

MIGRATION cote-a-cote : ces arbres reproduisent, en composant les nœuds natifs partages, ce que les
`execute_*` imperatifs (`abilities/loki.py`, `operations/spawn.py`) font a la main ; on les valide
replay-diff (DSL == imperatif == live) AVANT de basculer et retirer l'imperatif.
"""
from __future__ import annotations

from ...dsl.base import DslContext
from ...dsl.effect_nodes import EffectNode, OperationResult, Foreach
from ...dsl.tile_selectors import get_spawn_tile_selector
from ..components import (OwnerComponent, PositionComponent, UnitComponent, StatsComponent,
                          HealthComponent)
from ...entities.traits.unit_trait import UnitTrait, has_trait


def entities_from_state(state, caster_id: int) -> DslContext:
    """Construit l'`AbilityEntities` (= `DslContext`) lu par les selecteurs d'un behaviour, depuis le
    `State` runner : `units` = dicts {id, team, player, pos, alive, hp, visualId, _traits}, `caster`,
    `board` (= `state.board`), `has_trait(unit, traitId)` (mirror `UnitExtensions.HasFlag`, via l'enum
    `UnitTrait` + le set de noms `ctx.traits`)."""
    units: list = []
    caster = None
    for eid, e in state.entities.items():
        oc = e.get_component(OwnerComponent)
        pc = e.get_component(PositionComponent)
        uc = e.get_component(UnitComponent)
        sc = e.get_component(StatsComponent)
        hc = e.get_component(HealthComponent)
        traits = set(getattr(sc.ctx, "traits", None) or ()) if sc is not None else set()
        alive = uc.alive if uc is not None else True
        u = {
            "id": eid,
            "team": oc.team if oc is not None else None,
            "player": oc.player if oc is not None else None,
            "pos": {"col": pc.col, "row": pc.row} if pc is not None else None,
            "alive": alive,
            "hp": hc.hp if hc is not None else (1 if alive else 0),
            "visualId": uc.visual_id if uc is not None else None,
            "_traits": traits,
        }
        units.append(u)
        if eid == caster_id:
            caster = u

    def _has_trait(unit, trait_id):
        try:
            enum = UnitTrait(int(trait_id))
        except ValueError:
            return False
        return has_trait(unit.get("_traits") or set(), enum)

    return DslContext(units=units, caster=caster, board=state.board, has_trait=_has_trait)


class SpawnUnit(EffectNode):
    """Feuille `SpawnUnitBehaviour.Execute @180fd3d80` : spawn UNE unite sur la tuile COURANTE
    (`entities.subject` = id de tuile, pose par le `Foreach` sur le selecteur), stats
    `WithStatsFromConfig(summon_ability)`, owner = team+player du caster. Wrapper MINCE au-dessus de
    l'Operation portee `_spawn_config_grot` (mirror de l'inline de `execute_getemruntz`) : level/mult
    lus du `StatsComponent` du caster dans `ectx.state`. Effet PUR (`stop=False`) ; journalise l'op."""
    __slots__ = ("summon_ability",)

    def __init__(self, summon_ability: str):
        self.summon_ability = summon_ability

    def execute(self, entities, ectx):
        import gameconfig as GC
        from ..operations.spawn import _spawn_config_grot
        state = ectx.state
        caster_id = (entities.caster or {}).get("id")
        tile = entities.subject                       # id de tuile courant (pose par Foreach)
        ce = state.get_entity(caster_id) if (state is not None and caster_id is not None) else None
        if ce is None or tile is None:
            return OperationResult.ok()
        oc = ce.get_component(OwnerComponent)
        sc = ce.get_component(StatsComponent)
        cctx = sc.ctx if sc is not None else None
        level = getattr(cctx, "active_ability_level", None)
        mult = int(getattr(cctx, "ability_variables_multiplier", 100) or 100)
        vid = ((GC.ability(self.summon_ability) or {}).get("constants") or {}).get("unitId")
        gid = _spawn_config_grot(state, vid, tile, self.summon_ability, level, mult,
                                 oc.team if oc is not None else None,
                                 oc.player if oc is not None else None)
        if gid is not None:
            ectx.emit("SpawnUnit", tile=tile, unit=gid)
        return OperationResult.ok()


def getemruntz_spawn_tree() -> Foreach:
    """Sous-arbre SPAWN de `GetEmRuntzAbility.ExecuteBehaviour @1811e2210` (id 1045) =
    `Foreach(GetSpawnTileSelector @1811e26b0, SpawnUnit(WithStatsFromConfig))`. Porte le VOLET SPAWN
    de l'arbre (mirror 1:1) ; l'arbre COMPLET ajoute `& PerformAIAttackFromCurrentPosition @180df8a10`
    (LEFT) + `Foreach(Children @180debed0, TauntWithNewChildrenWhoDidDamage @1811e27a0)` (RIGHT via
    `op_Addition`) -> sous-slice suivante. Replay-diff vs l'imperatif
    `SpawnUnitOperation.execute_getemruntz`."""
    return Foreach(get_spawn_tile_selector(), SpawnUnit("GetEmRuntz"))
