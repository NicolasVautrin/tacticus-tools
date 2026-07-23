"""Feuilles DSL de SPAWN/invocation : `Spawn` (`SpawnUnitBehaviour`), `PerformAIAttack`
(`PerformAIAbilityUnitBehaviour`), `SpawnSummon` (ScarabHive), `SpawnReplica` (ScarabSummon). Wrappers
MINCES au-dessus des Operations `runner/operations/spawn.py` + `damage.py`. Namespace natif
`Entities.Behaviours.*`. cf. docstring du package (`__init__.py`)."""
from __future__ import annotations

from ....dsl.base import TargetsSelector, resolve_unit
from ....dsl.effects import AbilityBehaviour, OperationResult
from ...components import OwnerComponent, StatsComponent
from .context import _unit_dict


class Spawn(AbilityBehaviour):
    """`DSLFactory.Spawn @180dfbd50` -> `SpawnUnitBehaviour.Execute @180fd3d80` : itere son TILE-SELECTEUR
    EN INTERNE (mirror natif -- le `Spawn` n'est PAS un `Foreach(tiles, SpawnUnit)` externe, il enumere ses
    tuiles lui-meme) et spawn UNE unite par tuile, stats `WithStatsFromConfig(summon_ability)`, owner =
    team+player du caster. Wrapper au-dessus de l'Operation portee `_spawn_config_grot` (mirror de l'inline natif
    `GetEmRuntzAbility.ExecuteBehaviour @1811e2210`) : level/mult lus du `StatsComponent` du caster dans `ectx.state`. Chaque enfant
    est AJOUTE a `entities.children` (accumulateur factory+0x148, relu par `Children` pour le Taunt), annote
    pour le Taunt (`_new_child`/`_turns_started`/`_attacks_made`/`_last_attacked`). L'ordre d'enumeration =
    l'ordre du tile-selecteur (le `Cache` partage) -> `children` en ordre de TUILE (== l'ordre que
    `PerformAIAttack` reparcourt). Effet PUR (`stop=False`) ; journalise chaque spawn."""
    __slots__ = ("tile_selector", "summon_ability")

    def __init__(self, tile_selector: TargetsSelector, summon_ability: str):
        self.tile_selector, self.summon_ability = tile_selector, summon_ability

    def execute(self, entities, ectx):
        import gameconfig as GC
        from ...operations.spawn import _spawn_config_grot
        state = ectx.state
        caster_id = (entities.caster or {}).get("id")
        ce = state.get_entity(caster_id) if (state is not None and caster_id is not None) else None
        if ce is None:
            return OperationResult.ok()
        oc = ce.get_component(OwnerComponent)
        sc = ce.get_component(StatsComponent)
        cctx = sc.ctx if sc is not None else None
        level = getattr(cctx, "active_ability_level", None)
        mult = int(getattr(cctx, "ability_variables_multiplier", 100) or 100)
        vid = ((GC.ability(self.summon_ability) or {}).get("constants") or {}).get("unitId")
        for tile in (self.tile_selector.evaluate(entities) or []):   # itere les tuiles EN INTERNE (natif)
            gid = _spawn_config_grot(state, vid, tile, self.summon_ability, level, mult,
                                     oc.team if oc is not None else None,
                                     oc.player if oc is not None else None)
            if gid is not None:
                child = _unit_dict(state, gid) or {"id": gid}
                child.update({"_new_child": True, "_turns_started": 0, "_attacks_made": 0,
                              "_last_attacked": None})
                entities.children.append(child)       # accumulateur factory+0x148 (relu par Children)
                ectx.emit("SpawnUnit", tile=tile, unit=gid)
        return OperationResult.ok()


class PerformAIAttack(AbilityBehaviour):
    """`DSLFactory.PerformAIAttackFromCurrentPosition(Cache(GetSpawnTileSelector)) @180df8a10` ->
    `PerformAIAbilityUnitBehaviour.Execute @180fcb070` : chaque unite SUR les tuiles du SELECTEUR (le natif
    reutilise le MEME `Cache(GetSpawnTileSelector)` que le `Spawn` -> les grots tout juste spawnes) execute
    une attaque AI depuis SA position COURANTE (sans bouger). Port : `tile_selector` = le `Cache` PARTAGE
    (memoise -> memes tuiles PRE-spawn que le Spawn, sinon `CanAddUnit` recalcule les exclurait car
    occupees) ; on parcourt ses tuiles DANS L'ORDRE, on mappe chacune au grot pose dessus (`entities.children`,
    populate par le `Spawn` en ORDRE DE TUILE -> l'ordre d'attaque == l'ordre natif == l'ordre RNG), et il
    attaque l'ennemi le plus proche via `AttackDamageOperation.execute` (approx du choix AI natif,
    confront live #200 tracer-v2 DSLFactory). Annote le dict enfant (`_attacks_made`,
    `_last_attacked` = dict FRAIS post-attaque) pour les predicats du Taunt. Emet 'PerformAIAttack'. PUR."""
    __slots__ = ("tile_selector",)

    def __init__(self, tile_selector: TargetsSelector):
        self.tile_selector = tile_selector

    def execute(self, entities, ectx):
        from ..loki import _nearest_enemy
        from ...operations.damage import AttackDamageOperation
        state = ectx.state
        if state is None:
            return OperationResult.ok()
        board = getattr(state, "board", None)

        def _child_on_tile(tid):                       # grot pose sur la tuile (via sa pos capturee au spawn)
            for c in (entities.children or []):
                p = c.get("pos")
                if p and board is not None and board.id_at(p["col"], p["row"]) == tid:
                    return c
            return None

        attacks: list = []
        for tid in (self.tile_selector.evaluate(entities) or []):   # tuiles du Cache, ORDRE natif (= spawn)
            child = _child_on_tile(tid)
            if child is None:
                continue
            cid = child.get("id")
            tgt = _nearest_enemy(state, cid)
            if tgt is None:
                continue
            r = AttackDamageOperation.execute(state, cid, tgt)
            if r is None:
                continue
            child["_attacks_made"] = int(child.get("_attacks_made", 0) or 0) + 1
            child["_last_attacked"] = _unit_dict(state, tgt)   # etat POST-attaque (alive/hp courants)
            attacks.append({"child": cid, "target": tgt, "total": r.get("total")})
        ectx.emit("PerformAIAttack", attacks=attacks)
        return OperationResult.ok()


class SpawnSummon(AbilityBehaviour):
    """`ScarabHiveAbility.ExecuteBehaviour @181204cb0` = un noeud natif UNIQUE `Execute(Spawn(...))` (plain
    `AActiveAbility.Execute`, PAS `ExecuteAtomic`) ou `Spawn(caster@0x160, tileSel, unitId, SpawnUnitOptions)`
    avec `SpawnUnitOptions.WithStatsFromConfig(config)` portant DEUX sous-behaviours EMBARQUES :
      +0x10 = `AddEffect(0x4a3 = ScarabHive_OverrideDamageProfile = 1187)` sur chaque summon ;
      +0x18 = `UseNormalAttackIfAble(target@0x178)` = attaque normale immediate (profil override Piercing).
    `SpawnUnitBehaviour.Execute @180fd3d80` spawn `count` summons -- count-2, placement et
    `WithStatsFromConfig` vivent DANS SpawnUnitBehaviour (via `GetUnitToSpawn`/`GetTileIds`/`GetStatsToOverride`),
    HORS des DSL-selecteurs : le tile-selecteur natif `First(SortByDistance(CanAddUnit(AdjacentTiles(target)),
    caster), i)` = `PickAtIndexSelector` (UN element, @180ef02e0), le `count` vient des options -- puis
    `TriggerSpawnedUnitBehaviours` fire les 2 sous-behaviours embarques PAR summon.

    Port : delegue le SPAWN a l'Operation VALIDEE LIVE-BIT-EXACT `SpawnUnitOperation.execute` (count/stats
    `ability_var`/owner `CopyOwner`/placement adjacent-cible ; cf. test_summon_spawn_live) -- on ne re-derive
    PAS la selection de tuile via des DSL-selecteurs (le count-2 n'est PAS exprimable par `First`=PickAtIndex
    sans RE de `GetTileIds`/`GetUnitToSpawn`, et sans gain : l'outcome est deja valide). ON-APPEARANCE =
    `_summon_on_appearance_attack(summon, target, unitDamageProfile)` (mirror `UseNormalAttackIfAble`, profil
    Piercing en override de l'arme Energy). L'effet PERSISTANT 0x4a3 (OverrideDamageProfile pour les attaques
    des TOURS SUIVANTS du summon) n'est PAS materialise ici -- le pipeline d'attaque ne le LIT pas encore
    (gap flagge en tache) ; l'attaque immediate porte deja le profil override via `prof`. Emet
    'SpawnUnit'/'SummonOnAppearance'. Effet PUR (stop=False)."""
    __slots__ = ("summon_ability", "count", "target_ref")

    def __init__(self, summon_ability: str, count: int, target_ref: TargetsSelector):
        self.summon_ability, self.count, self.target_ref = summon_ability, int(count), target_ref

    def execute(self, entities, ectx):
        import gameconfig as GC
        from ...operations.spawn import SpawnUnitOperation
        from ..loki import _summon_on_appearance_attack
        state = ectx.state
        caster_id = (entities.caster or {}).get("id")
        tu = resolve_unit(self.target_ref, entities)        # Target()@0x178 -> dict d'unite
        target_id = tu.get("id") if tu else None
        if state is None or caster_id is None or target_id is None:
            return OperationResult.ok()
        consts = (GC.ability(self.summon_ability) or {}).get("constants") or {}
        vid = consts.get("unitId")
        if vid is None:
            return OperationResult.ok()
        prof = consts.get("unitDamageProfile")              # profil override de l'attaque on-appearance (Piercing)
        # [Spawn / WithStatsFromConfig / CopyOwner / placement] -> Operation validee (count/stats/owner/tuiles)
        spawned = SpawnUnitOperation.execute(state, caster_id, target_id, self.summon_ability, vid, self.count)
        for sid in spawned:
            ectx.emit("SpawnUnit", unit=sid)
        # [on-appearance] UseNormalAttackIfAble : chaque summon attaque la CIBLE (profil override immediat).
        for sid in spawned:
            res = _summon_on_appearance_attack(state, sid, target_id, prof)
            if res is not None:
                ectx.emit("SummonOnAppearance", summon=sid, total=res.get("total"))
        return OperationResult.ok()


class SpawnReplica(AbilityBehaviour):
    """`ScarabSummonAbility.ExecuteBehaviour @181205290` (id 1047, necroSmnSwarm -- auto-DEDOUBLEMENT) = un
    noeud natif UNIQUE `Execute(Spawn(...))` (plain `AActiveAbility.Execute`, PAS `ExecuteAtomic`), DISTINCT
    du noeud ScarabHive (`SpawnSummon`) : `Spawn(self@0x160, tileSel, unitId=GetStringConstant(config,0)=
    necroSmnSwarm, SpawnUnitOptions.CopyOwner(caster))` ou les options portent UN sous-behaviour EMBARQUE :
      +0x18 = `PerformAIAttack(1)` = le double attaque immediatement -- PAS de +0x10 AddEffect (ScarabSummon
      n'a PAS l'effet persistant 0x4a3 de ScarabHive) ;
    tile-selecteur natif = `PickRandomly(CanAddUnit(AdjacentTiles(self@0x160)), 1, ..., 0x7fffffff)` (UNE tuile
    LIBRE adjacente a SOI). `SpawnUnitBehaviour.Execute @180fd3d80` spawn `count` clones -- count/placement/
    CopyOwner vivent DANS SpawnUnitBehaviour, HORS des DSL-selecteurs -- puis `TriggerSpawnedUnitBehaviours`
    fire le sous-behaviour on-appearance PAR summon.

    Port : delegue le SPAWN a l'Operation VALIDEE `SpawnUnitOperation.execute_self_replica` (`CopyOwner
    @180fd5ba0` = clone owner+stats du parent, count-1, tuiles libres adjacentes au caster ; cf.
    test_summon_spawn_live) -- MEME carve-out que `SpawnSummon` (on ne re-derive PAS le count/placement via
    des DSL-selecteurs : ils vivent dans SpawnUnitBehaviour et l'outcome est deja valide). ON-APPEARANCE =
    `PerformAIAttack(1)` : chaque double attaque l'ennemi le plus proche (`_nearest_enemy` +
    `AttackDamageOperation.execute`, approx du choix AI natif). Le tirage de degat consomme `state.rng` ->
    no-op gracieux si rng non cale (la SEQUENCE reste fidele, seul le roll est differe au flux runner cale ;
    mirror de l'ancien imperatif). Emet 'SpawnUnit'/'ReplicaOnAppearance'. Effet PUR (stop=False).

    GAP (inchange) : le cap de duplication (`UnitDuplicationLimitSelector`/`LimitUnitDuplications`) n'est pas
    porte -> recurrence non bornee offline."""
    __slots__ = ("summon_ability", "count")

    def __init__(self, summon_ability: str, count: int):
        self.summon_ability, self.count = summon_ability, int(count)

    def execute(self, entities, ectx):
        import gameconfig as GC
        from ...operations.spawn import SpawnUnitOperation
        from ...operations.damage import AttackDamageOperation
        from ..loki import _nearest_enemy
        state = ectx.state
        caster_id = (entities.caster or {}).get("id")
        if state is None or caster_id is None:
            return OperationResult.ok()
        vid = ((GC.ability(self.summon_ability) or {}).get("constants") or {}).get("unitId")
        if vid is None:
            return OperationResult.ok()
        # [Spawn / CopyOwner / placement adjacent-self] -> Operation validee (clone owner+stats du parent)
        spawned = SpawnUnitOperation.execute_self_replica(state, caster_id, vid, self.count)
        for sid in spawned:
            ectx.emit("SpawnUnit", unit=sid)
        # [on-appearance] PerformAIAttack : chaque double attaque l'ennemi le plus proche (roll consomme rng).
        if state.rng is not None:
            for sid in spawned:
                tgt = _nearest_enemy(state, sid)
                if tgt is None:
                    continue
                r = AttackDamageOperation.execute(state, sid, tgt)
                if r is not None:
                    ectx.emit("ReplicaOnAppearance", summon=sid, target=tgt, total=r.get("total"))
        return OperationResult.ok()
