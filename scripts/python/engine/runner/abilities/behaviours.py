"""FEUILLES d'effet à EFFET du namespace natif `IdunBattle.Entities.Behaviours.*`, RUNNER-COUPLÉES, +
builder de contexte `entities_from_state` (#149).

Contenu = les `*Behaviour` CONCRETS qui MUTENT l'état en émettant une runner Operation déjà portée :
`Spawn` (`SpawnUnitBehaviour` @180fd5ab0 → `_spawn_config_grot`), `AttackWithAttackDamage`
(`DSLFactory.AttackWithAttackDamage` @180de9fb0 → `AttackDamageOperation.execute_ability_attack`/
`execute_normal_like` : attaque d'ability crit/block), `AttackWithAbilityDamage`
(`DSLFactory.AttackWithAbilityDamage` @180de9c90 → `AttackDamageOperation.execute_direct` : dégât DIRECT
sans crit/block — DoT feu `EnvFireTile`), `AddEffect` (`AddEffectBehaviour` @180f947e0 →
`AddEffectOperation`), `AddBondEffect`
(`AddBondEffectBehaviour` → idem), `PerformAIAttack` (`PerformAIAbilityUnitBehaviour` @180fcb940). Couche
MINCE d'orchestration au-dessus des mutateurs ECS.

Ils vivent ICI (et non dans `entities/behaviours.py` avec les COMBINATEURS purs `Seq`/`Maybe`/`Foreach`/
`If`/`AtomicGroup`, MÊME namespace natif `Entities.Behaviours`) parce qu'ils sont RUNNER-COUPLÉS (appellent
des Operations de `runner/`, que `entities/` ne peut importer sans inverser le layering). Le split
entities/runner = layering, PAS le namespace natif.

Ce fichier ne contient QUE des `Entities.Behaviours` :
- Les COMBINATEURS purs → `engine/entities/behaviours.py`.
- Les SÉLECTEURS/FORMULES (`Children`=`AllAliveMachinesSelector`, `LastUnitAttackedBy`=`LastUnitAttackedBy
  Selector`, `TotalAttacksMade`/`UnitTurnsStarted`=`*Formula`) → `entities/selectors.py` + `entities/formulas.py`
  (leur vrai namespace `Entities.Selectors`/`Formulas`).
- Les ARBRES d'ability SPÉCIFIQUES (`thunderous_assault_tree`/`getemruntz_tree`…) → `abilities/loki.py`
  (namespace natif `Abilities.Active.Loki`, avec leur classe d'ability).

`entities_from_state` construit le `DslContext` (= l'`entities` natif lu par les sélecteurs) depuis le
`State` runner. cf. docs/rl/dsl-effect-nodes.md.
"""
from __future__ import annotations

from ...dsl.base import DslContext, TargetsSelector, resolve_unit, _units_of
from ...dsl.effects import AbilityBehaviour, OperationResult
from ..components import (OwnerComponent, PositionComponent, UnitComponent, StatsComponent,
                          HealthComponent)
from .base import turns_from_rounds, ability_attack_params
from ...entities.traits.unit_trait import UnitTrait, has_trait

def _unit_dict(state, eid: int, entity=None) -> dict | None:
    """Dict d'unite {id, team, player, pos, alive, hp, visualId, _traits} lu du `State` runner — la forme
    `unit` que consomment les selecteurs DSL. `entity` optionnel (evite un `get_entity` redondant)."""
    e = entity if entity is not None else state.get_entity(eid)
    if e is None:
        return None
    oc = e.get_component(OwnerComponent)
    pc = e.get_component(PositionComponent)
    uc = e.get_component(UnitComponent)
    sc = e.get_component(StatsComponent)
    hc = e.get_component(HealthComponent)
    traits = set(getattr(sc.ctx, "traits", None) or ()) if sc is not None else set()
    alive = uc.alive if uc is not None else True
    return {
        "id": eid,
        "team": oc.team if oc is not None else None,
        "player": oc.player if oc is not None else None,
        "pos": {"col": pc.col, "row": pc.row} if pc is not None else None,
        "alive": alive,
        "hp": hc.hp if hc is not None else (1 if alive else 0),
        "visualId": uc.visual_id if uc is not None else None,
        "_traits": traits,
    }


# Champs MUTABLES d'une unite (re-lus du state a chaque acces par LiveUnit). Les autres (id/team/player/
# visualId/_traits) sont quasi-statiques -> servis depuis le snapshot seed.
_LIVE_KEYS = frozenset({"pos", "hp", "alive"})


class LiveUnit(dict):
    """Vue LIVE d'une unite pour le contexte RUNNER (mirror natif : `AbilityEntities` tient une REF
    d'entite @+0x40, position/PV re-derives A LA LECTURE -- jamais un snapshot ; cf.
    docs/rl/dsl-live-context-substrate.md, `get_CasterPosition @180fb4f20` / `UnitPosition..ctor @18102a070`).

    Sous-classe `dict` pour rester reconnue par les `isinstance(v, dict)` du DSL (`resolve_unit`/`_units_of`/
    helpers de `dsl/base.py`) et exposer les champs STATIQUES (id/team/player/visualId/_traits) via le
    snapshot seed (compat `**`/`.items()`/iteration). Les champs MUTABLES (`_LIVE_KEYS` = pos/hp/alive) sont
    RE-LUS du `state` a chaque `get`/`[]` -> une re-eval de predicat (ex. `IsAdjacent`) APRES une mutation
    (Move/degat/mort) voit l'etat COURANT. C'est CE qui permet a UN arbre DSL de rester correct a travers une
    mutation intra-arbre (Voie A, S-chantier).

    L'override `caster_pos` (mode `AbilityEntities+0x48`, decision balayee AI) reste applique par les
    SELECTEURS (`ctx.caster_pos or _pos(...)`), PAS ici : LiveUnit rend la position BRUTE live du `state`.
    Le chemin PREDICTION (`playbook/prediction.py`) construit toujours des dicts FIGES depuis sa scene
    hypothetique -> il n'utilise PAS LiveUnit (frozen-by-design)."""

    def __init__(self, state, eid: int, entity=None):
        self._state = state
        self._eid = eid
        # Ref d'entite STABLE (les composants mutent en place) = l'homologue de AbilityEntities+0x40.
        self._entity = entity if entity is not None else state.get_entity(eid)
        super().__init__(_unit_dict(state, eid, self._entity) or {"id": eid})

    def _live(self, key):
        d = _unit_dict(self._state, self._eid, self._entity)
        return (d or {}).get(key)

    def get(self, key, default=None):
        if key in _LIVE_KEYS:
            v = self._live(key)
            return v if v is not None else default
        return super().get(key, default)

    def __getitem__(self, key):
        if key in _LIVE_KEYS:
            v = self._live(key)
            if v is None:
                raise KeyError(key)
            return v
        return super().__getitem__(key)


def entities_from_state(state, caster_id: int, target_id: int | None = None,
                        actor_id: int | None = None) -> DslContext:
    """Construit l'`AbilityEntities` (= `DslContext`) lu par les selecteurs d'un behaviour, depuis le
    `State` runner : `units` = `LiveUnit` (vues live-by-ref, pos/hp/alive re-lus du `state` a chaque acces
    -> mirror `AbilityEntities+0x40` ; permet la re-eval de predicat post-mutation, Voie A), `caster`
    (`factory+0x160`, aussi `Self@0x148`
    pour un triggered Owner==Caster), `target` (cible principale = `factory+0x178`, lu par `Target()` —
    None si l'ability est sans cible ; sur un OnPreDeath = l'unite MOURANTE @0x178), `actor` (`factory+
    0x158` = ACTEUR/TUEUR de l'evenement, lu par `Actor()` — threade sur les behaviours de trigger type
    ActOfFaith accumulate ; None sinon), `board` (= `state.board`), `has_trait(unit, traitId)` (mirror
    `UnitExtensions.HasFlag`, via l'enum `UnitTrait` + le set de noms `ctx.traits`). `children=[]` =
    accumulateur de spawn FRAIS pour CE cast (mirror factory+0x148)."""
    units: list = []
    caster = None
    target = None
    actor = None
    for eid, e in state.entities.items():
        u = LiveUnit(state, eid, e)                   # vue LIVE (pos/hp/alive re-lus a chaque acces)
        units.append(u)
        if eid == caster_id:
            caster = u
        if target_id is not None and eid == target_id:
            target = u
        if actor_id is not None and eid == actor_id:
            actor = u

    def _has_trait(unit, trait_id):
        try:
            enum = UnitTrait(int(trait_id))
        except ValueError:
            return False
        return has_trait(unit.get("_traits") or set(), enum)

    # `ctx.faction_of` (mirror `UnitsFromFaction`) — FactionId gameconfig par visualId (`_faction` caché).
    # Lazy import (garde anti-circulaire, comme les Operations importées dans les feuilles).
    from ...ai.action_generators import _faction

    def _faction_of(unit):
        return _faction((unit or {}).get("visualId"))

    # `ctx.get_stat` (mirror `UnitExtensions.GetStat @180ed30d0`) : le nœud `StatAmount(sel, statType,
    # variant)` lit la VRAIE stat de l'unité (Attack/Health/…) via son `StatsComponent.ctx.stats` — sans
    # ce wiring il dégraderait vers Health (hp) via `_default_get_stat`. `variant` = `StatPart` natif
    # (0=Current, 2=Maximum, 3=Initial) ; `level` ignoré offline (stats non scalées par niveau tierce).
    # id de l'unité DSL -> entité ECS -> `UnitStats.get_stat(statType, part)`.
    def _get_stat(unit, stat_type, variant=0, level=None):
        uid = (unit or {}).get("id")
        e = state.get_entity(uid) if uid is not None else None
        sc = e.get_component(StatsComponent) if e is not None else None
        us = getattr(sc.ctx, "stats", None) if sc is not None else None
        # #60 : stat 20 (NUMBER_OF_MEMBERS) = branche DÉDIÉE du GetStat natif (handler jumptable 0x14
        # @180ed3929 : GroupUnitComponent fill-up {+0x10=nrOfMembers, +0x18=restants}, PAS un
        # StatComponent — `GetStatComponent @180ed20c0` n'a pas de case 0x14). Offline : parts dérivées
        # de l'état PV via `group_unit_stat_part` (lu par `SwarmAbility` StatAmount(Self,20,3/4)).
        from ...entities.stats import StatType as _ST
        if int(stat_type) == int(_ST.NUMBER_OF_MEMBERS):
            n = int(getattr(sc.ctx, "number_of_members", 1)) if sc is not None else 1
            hc = e.get_component(HealthComponent) if e is not None else None
            if hc is None or hc.hp is None or hc.hp_max is None:
                return n if int(variant) in (0, 2, 3) else 0
            from ...services.trait_damage_limits import group_unit_stat_part
            return group_unit_stat_part(int(variant), int(hc.hp_max), n, int(hc.hp))
        return us.get_stat(int(stat_type), int(variant)) if us is not None else 0

    # `ctx.get_ability_level` (mirror du niveau d'ability lu par `ConfigVar` sur une unité TIERCE) : le nœud
    # `ConfigVarForEntity(RighteousRepugnance, chance, killer)` lit le niveau PASSIF/ACTIF capté de l'unité
    # (`StatsComponent.ctx.passive_ability_level`/`active_ability_level`, seedé depuis unitConfig).
    def _get_ability_level(unit, slot="passive"):
        uid = (unit or {}).get("id")
        e = state.get_entity(uid) if uid is not None else None
        sc = e.get_component(StatsComponent) if e is not None else None
        if sc is None:
            return None
        return getattr(sc.ctx, "active_ability_level" if slot == "active" else "passive_ability_level", None)

    return DslContext(units=units, caster=caster, target=target, actor=actor, board=state.board,
                      has_trait=_has_trait, faction_of=_faction_of, get_stat=_get_stat,
                      get_ability_level=_get_ability_level, children=[])


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
        from ..operations.spawn import _spawn_config_grot
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
        from .loki import _nearest_enemy
        from ..operations.damage import AttackDamageOperation
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
        from ..operations.spawn import SpawnUnitOperation
        from .loki import _summon_on_appearance_attack
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
    mirror de l'ancien impératif). Emet 'SpawnUnit'/'ReplicaOnAppearance'. Effet PUR (stop=False).

    GAP (inchange) : le cap de duplication (`UnitDuplicationLimitSelector`/`LimitUnitDuplications`) n'est pas
    porte -> recurrence non bornee offline."""
    __slots__ = ("summon_ability", "count")

    def __init__(self, summon_ability: str, count: int):
        self.summon_ability, self.count = summon_ability, int(count)

    def execute(self, entities, ectx):
        import gameconfig as GC
        from ..operations.spawn import SpawnUnitOperation
        from ..operations.damage import AttackDamageOperation
        from .loki import _nearest_enemy
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


class AddBondEffect(AbilityBehaviour):
    """`DSLFactory.AddBondEffect(0x1b, stateRef, source, target, ..., TurnsFromRounds(1)) @1811e27a0` : pose
    l'effet BOND `Taunted_OnlySpecificTargets` (0x1b=27, COMPOSITE 25/26/1237) reliant `source` (l'enfant/
    grot) et `target` (`LastUnitAttackedBy` = l'ennemi frappe), duree `TurnsFromRounds(rounds)`. Wrapper
    MINCE au-dessus de `AddEffectOperation.execute` (mirror exact de l'imperatif : source=grot, target=
    ennemi). `source_ref`/`target_ref` = Nodes resolus au dict courant -> ids. No-op si source/target
    absents. Emet 'AddBondEffect'. Effet PUR (stop=False).

    `duration_rounds` = nb de rounds (`TurnsFromRounds(rounds)`) ; `None` = duree DEFAUT de l'effet
    (`DefaultAmountOfRounds`, mirror de l'arg natif duree-node ZERO d'`AddBondEffect` SANS `TurnsFromRounds`
    -- ex. ValkyrieStrike 1022 : arg7 = struct zero-initialise, PAS un `TurnsFromRounds(n)` explicite) vs
    explicite (CrushingClaws Taunt / GetEmRuntz = `TurnsFromRounds(1)`). MEME semantique None que `AddEffect`."""
    __slots__ = ("effect_type", "name", "source_ref", "target_ref", "duration_rounds")

    def __init__(self, effect_type: int, name: str, source_ref: TargetsSelector, target_ref: TargetsSelector,
                 duration_rounds=1):
        self.effect_type, self.name = effect_type, name
        self.source_ref, self.target_ref = source_ref, target_ref
        self.duration_rounds = duration_rounds

    def execute(self, entities, ectx):
        from ..operations.effects import AddEffectOperation
        su = resolve_unit(self.source_ref, entities)
        tu = resolve_unit(self.target_ref, entities)
        src = su.get("id") if su else None
        tgt = tu.get("id") if tu else None
        if src is None or tgt is None or ectx.state is None:
            return OperationResult.ok()
        # duration_rounds None -> pas d'override = duree DEFAUT (DefaultAmountOfRounds), mirror de l'arg natif
        # duree-node ZERO d'AddBondEffect sans TurnsFromRounds (ValkyrieStrike 1022) ; sinon TurnsFromRounds(rounds).
        dur = turns_from_rounds(self.duration_rounds) if self.duration_rounds is not None else None
        AddEffectOperation.execute(ectx.state, source=src, target=tgt, effect_type=self.effect_type,
                                   name=self.name, duration_override=dur)
        ectx.emit("AddBondEffect", source=src, target=tgt, effect_type=self.effect_type)
        return OperationResult.ok()


class AttackWithAttackDamage(AbilityBehaviour):
    """`DSLFactory.AttackWithAttackDamage @180de9fb0` -> `AttackDamageBehaviour`+`AttackBehaviour.Execute` :
    l'attaque d'une ability (bornes `MinMaxDamage(minDmg/maxDmg[level])`, profil `GetDamageProfile`, nb de
    coups `GetNumberConstant(0x2f)=nrOfHits`) portee sur la cible. Wrapper MINCE au-dessus de l'Operation
    DEJA bit-exact `AttackDamageOperation.execute_ability_attack` (meme pipeline reduce/crit/block/after-hit
    que l'imperatif) : `caster` = `ctx.caster`, `target` = `target_sel` (dict d'unite), et
    `(base_min,base_max,pierce,hits)` via `ability_attack_params(ability_id, profile)` — MEME source que
    l'imperatif -> bit-exact BY CONSTRUCTION (memes args, meme `state.rng`).

    ⚠ Le ciblage natif complet = `Units(Cache(First(Nearest(Tiles(target_ctx), casterPos))))` : pour une
    ability MONO-cible melee (ThunderousAssault) il COLLAPSE en la cible du message (`ctx.target`) — que
    l'IA/caller a deja choisie (== l'imperatif live-valide). La chaine Tiles->Nearest->First->Cache->Units
    n'est materialisee que si une ability re-derive sa cible (differe). Emet 'AttackWithAttackDamage'. PUR.

    `min_key`/`max_key`/`hits_key` = cles config du volet de degat (defaut `minDmg`/`maxDmg`/`nrOfHits` =
    `MinMaxDamage`/`GetDamageProfile`/`GetNumberConstant(0x2f)`) ; une ability a DEUX volets (ex. CrushingClaws
    principal vs splash) passe le 2e jeu (`minDmg_2`/`maxDmg_2`/`nrOfHits_2` = `MinMaxDamage2`/`GetDamageProfile2`
    /`GetNumberConstant(0x32)`).

    `damage_override` = callable `(state, caster, target, bmin, bmax) -> (bmin, bmax)` mirror d'un
    `AActiveAbility.GetAttackDamage` SURCHARGE par-ability (le natif passe la node de degat calculee a
    `AttackWithAttackDamage` — cf. `SpiritLeech.GetAttackDamage @181209dd0` = ConditionalAmount(cible Pinned
    -> +extraDmg)). Defaut None = degat generique `MinMaxDamage` (bornes config brutes) ; sinon le callable
    ajuste (bmin,bmax) APRES `ability_attack_params`, AVANT le tirage per-coup.

    `multi` = mode MULTI-CIBLE (`AttackBehaviour.Execute @180fb91a0` : quand le `targets` natif est un
    SELECTEUR resolvant N unites — le volet SPLASH de PlasmaGrenade/Stikkbomb/... `Enemies(caster,
    AdjacentUnits(target,1))` — le behaviour resout la LISTE, l'`OrderBy` (b__5_0, cle scalaire par-unite =
    ordre de lecture) puis attaque CHAQUE cible dans l'ordre). Port : `evaluate` -> liste, tri par `id`
    (= ordre de lecture natif == l'ordre `sorted` de l'imperatif `_splash_ability_behaviour` -> bit-exact),
    une attaque + un `emit` par cible. `multi=False` (defaut) = mono-cible `resolve_unit` (mirror du collapse
    `Units(Cache(First(Nearest(...))))` -> la cible du message) : chemin INCHANGE pour ThunderousAssault/
    CrushingClaws/SpiritLeech.

    `pick_n` = FOLD du `PickRandomly(selecteur, n) @180df8db0` natif quand il ENVELOPPE le selecteur de cibles
    d'une attaque (SPLASH de Fragstorm @1811e0a00 : `PickRandomly(AdjacentTiles(target) − Tiles(Friends), 4)`).
    Comme `multi=True` folde l'`OrderBy`, `pick_n` folde le PickRandomly DANS la resolution du selecteur
    d'attaque : apres `evaluate`+tri par id, on tire `n` cibles via `_pick_randomly_n(state.rng)` (== l'imperatif
    `_pick_randomly_n(_adjacent_enemies_of, n)` -> bit-exact, meme pool id-trie/meme pick/meme rng). Defaut None
    = pas de tirage (toutes les cibles). Requiert `multi=True`. ⚠ GAP #215 (RNG-exact) : le natif tire des HEXES
    (tuiles VIDES incluses = coup gaspille) et l'ordre/cout exact du tirage ne sont pas cales ; le port tire des
    OCCUPANTS (pas de tuile vide) -> divergence possible quand >n tuiles adjacentes candidates.

    `amount` = FOLD du dégât-node `Direct(amountFormula)` quand le natif passe une **valeur calculée** à
    `AttackWithAttackDamage` en lieu de bornes d'arme (`MinMaxDamage`) — ex. Psyker
    `PercentageOf(StatAmount(Self, Attack), psykerExtraDmg%)` @1812241b0. Défaut None = mode bornes
    (`ability_attack_params`). Quand fourni (un `AAmountFormula`), la feuille calcule `base =
    amount.evaluate(entities)` (Fix64, mirror natif — `entities` porte `get_stat` pour `StatAmount`) et route
    via `AttackDamageOperation.execute_normal_like(base, pierce=profile_pierce, hits, spread_pct=0)` (montant
    MONO-valeur = AUCUNE variance d'arme), même pipeline reduce/crit/block/after-hit que l'attaque normale.
    `hits` = nb de coups EXPLICITE du dégât-node (défaut 1 en mode `amount` ; en mode bornes, None → `hits`
    de la config via `ability_attack_params`)."""
    __slots__ = ("target_sel", "ability_id", "profile", "is_melee", "min_key", "max_key", "hits_key",
                 "damage_override", "multi", "pick_n", "amount", "hits", "ability_type")

    def __init__(self, target_sel: TargetsSelector, ability_id: str, profile: str, is_melee: bool = True,
                 min_key: str = "minDmg", max_key: str = "maxDmg", hits_key: str = "nrOfHits",
                 damage_override=None, multi: bool = False, pick_n=None, amount=None, hits=None,
                 ability_type=None):
        self.target_sel, self.ability_id, self.profile, self.is_melee = target_sel, ability_id, profile, is_melee
        self.min_key, self.max_key, self.hits_key = min_key, max_key, hits_key
        self.damage_override, self.multi, self.pick_n = damage_override, multi, pick_n
        self.amount, self.hits = amount, hits
        # `ability_type` = AbilityOrEffect NUMERIQUE du coup, threade au payload des events after-hit
        # (`TriggerEvent.ability_type`, mirror du champ d'event natif lu par DirectAbilitySelector) —
        # ex. smite Psyker = 0x3f5=1013 (gate branche 2 LordOfTempests AddIce #35). None = non threade.
        self.ability_type = ability_type

    def execute(self, entities, ectx):
        from ..operations.damage import AttackDamageOperation
        state = ectx.state
        caster = (entities.caster or {}).get("id")
        if state is None or caster is None:
            return OperationResult.ok()
        if self.multi:                                     # AttackBehaviour.Execute : selecteur -> N cibles
            targets = sorted((u for u in _units_of(self.target_sel, entities) if (u or {}).get("id") is not None),
                             key=lambda u: u.get("id"))     # OrderBy (b__5_0) = ordre de lecture == id
            if self.pick_n is not None:                    # PickRandomly(selecteur, n) folde (state.rng), == imperatif
                from .loki import _pick_randomly_n
                targets = _pick_randomly_n(state, targets, int(self.pick_n))
        else:                                              # collapse mono-cible (cible du message)
            tu = resolve_unit(self.target_sel, entities)
            targets = [tu] if tu and tu.get("id") is not None else []
        for tu in targets:
            tgt = tu.get("id")
            if self.amount is not None:                    # degat-node Direct(StatAmount/PercentageOf) (Psyker/Fire)
                from .base import profile_pierce
                base = int(self.amount.evaluate(entities))  # Fix64 mirror (entities.get_stat -> StatAmount)
                ce = state.get_entity(caster)
                csc = ce.get_component(StatsComponent) if ce is not None else None
                pierce = profile_pierce(csc.ctx if csc is not None else None, self.profile,
                                        ranged=not self.is_melee)
                atk = AttackDamageOperation.execute_normal_like(  # montant mono-valeur -> spread_pct=0
                    state, caster, tgt, base, pierce,
                    hits=int(self.hits) if self.hits is not None else 1, spread_pct=0,
                    damage_profile=self.profile, is_melee=self.is_melee,
                    ability_type=self.ability_type)
            else:
                bmin, bmax, pierce, hits = ability_attack_params(
                    state, caster, self.ability_id, self.profile, ranged=not self.is_melee,
                    min_key=self.min_key, max_key=self.max_key, hits_key=self.hits_key)
                if self.damage_override is not None:       # GetAttackDamage surchargee (ex. SpiritLeech +extraDmg)
                    bmin, bmax = self.damage_override(state, caster, tgt, bmin, bmax)
                atk = AttackDamageOperation.execute_ability_attack(
                    state, caster, tgt, bmin, bmax, pierce, hits,
                    damage_profile=self.profile, is_melee=self.is_melee,
                    ability_type=self.ability_type)
            ectx.emit("AttackWithAttackDamage", caster=caster, target=tgt,
                      total=(atk or {}).get("total"), attack=atk)
        return OperationResult.ok()


class AttackWithAbilityDamage(AbilityBehaviour):
    """`DSLFactory.AttackWithAbilityDamage @180de9c90` -> `AttackDamageBehaviour` sur un nœud de dégât
    `Direct(...)` : dégât DIRECT (base = un `AAmountFormula`) porté sur la cible, routé par le SEUL
    perçage/armure — AUCUN crit / block / bouclier / spread / tirage RNG / after-hit. Factory NATIVE
    DISTINCTE de `AttackWithAttackDamage @180de9fb0` (l'attaque d'ability crit/block ci-dessus). #149
    slice-19 : la classe Python homonyme précédente mirrorait en réalité `AttackWithAttackDamage` et a
    été RENOMMÉE (directive « coller au natif ») — cette classe-ci est la VRAIE `AttackWithAbilityDamage`.

    Seul usage porté = le DoT de tuile `EnvFireTile` (`EnvFireTileAbility.CreateBehaviour @18121e040` :
    `Foreach(<occupants non-immunes sur tuile en feu>, AttackWithAbilityDamage(Tiles(@0x180), PercentageOf(
    StatAmount(@0x180, Health=5, Max=2), ConfigConst(fireDmgPct)), Direct(Nullable(3)), source=AbilityOrEffect(
    Fire=5)))`). Wrapper MINCE au-dessus de `AttackDamageOperation.execute_direct` (= l'ancien corps impératif
    de `FireTileDoT`) → bit-exact BY CONSTRUCTION (même base, même perçage, même mutation/mort).

    `amount` = le dégât-node `AAmountFormula` (la base ; pour le feu `PercentageOf(fireDmgPct, StatAmount(
    Target(), Health, Max))` — `entities` porte `get_stat`, la base est calculée Fix64 = mirror natif
    `PercentageOf.Calculate`). `profile` = profil de perçage (Flame). `is_melee` n'affecte PAS le perçage :
    la source est une TUILE sans stats ExtraPierce → `profile_pierce(None, profile)` = PiercingRatio brut.
    `hits` = nb d'applications (défaut 1 = 1 tick, live-validé : net 477 = base 1908 × PiercingRatio Flame
    25%). `source_ref` = l'entité-source pour l'attribution de mort (défaut None → `entities.caster` = la
    tuile). Émet 'AttackWithAbilityDamage'. PUR.

    ⚠ `Direct(Nullable(3))` natif : le `3` n'est PAS le nb de coups (live = 1 tick) ; sa sémantique exacte
    (DamageTrait / tag de source) n'est pas RE'd et reste INERTE pour un dégât DIRECT (rien à taguer : pas de
    crit/block/after-hit). Non porté (ne change aucun nombre)."""
    __slots__ = ("target_sel", "profile", "amount", "is_melee", "hits", "source_ref")

    def __init__(self, target_sel: TargetsSelector, profile: str, amount, is_melee: bool = True,
                 hits: int = 1, source_ref=None):
        self.target_sel, self.profile, self.amount = target_sel, profile, amount
        self.is_melee, self.hits, self.source_ref = is_melee, int(hits), source_ref

    def execute(self, entities, ectx):
        from ..operations.damage import AttackDamageOperation
        from .base import profile_pierce
        state = ectx.state
        if state is None:
            return OperationResult.ok()
        su = resolve_unit(self.source_ref, entities) if self.source_ref is not None else entities.caster
        src = (su or {}).get("id")
        tu = resolve_unit(self.target_sel, entities)
        tgt = tu.get("id") if tu and tu.get("id") is not None else None
        if src is None or tgt is None:
            return OperationResult.ok()
        base = int(self.amount.evaluate(entities))            # Fix64 mirror (entities.get_stat -> StatAmount)
        pierce = profile_pierce(None, self.profile, ranged=not self.is_melee)  # source=tuile : PiercingRatio brut
        atk = None
        for _ in range(max(1, self.hits)):
            atk = AttackDamageOperation.execute_direct(state, src, tgt, base, pierce,
                                                       damage_profile=self.profile)   # #202 : cle "recu ce tour"
        ectx.emit("AttackWithAbilityDamage", source=src, target=tgt,
                  total=(atk or {}).get("total"), attack=atk)
        return OperationResult.ok()


class EvaluateAbilities(AbilityBehaviour):
    """`DSLFactory.EvaluateAbilities @180def5b0` -> `EvaluateAbilitiesBehaviour.Execute @180fc48a0` (ctor
    @180fc4e10, champ +0x50 = `EventTriggerType`) : EVALUE les abilities DÉCLENCHÉES du CASTER pour un
    `EventTriggerType`, INLINE dans un behaviour-tree. Nœud DSL GÉNÉRIQUE du natif (callers : NormalAttack
    `EvaluateAbilities(0x26)`, ArmoriumCherub `EvaluateAbilities(0x4b=AttackInAtomicGroup)`, ArmouredMight/
    TheQuickening). Wrapper MINCE au-dessus de la couche dispatch runner (`evaluate_abilities_for_event`) qui
    rejoue les passifs déclenchés PORTÉS de cet event (AttackInAtomicGroup + attaque ranged -> FireOfAbsolution).

    `event` = `EventTriggerType` (int) ; `ranged` = nature de l'attaque du tree (le natif la dérive de la
    position — ici fournie par l'ability : ArmoriumCherub est range-2 -> ranged=True, == le `ranged=True`
    littéral de l'ancien impératif). Émet 'EvaluateAbilities' (la liste de résultats des passifs). PUR."""
    __slots__ = ("event", "ranged")

    def __init__(self, event: int, ranged: bool = False):
        self.event, self.ranged = int(event), ranged

    def execute(self, entities, ectx):
        from ..operations.triggers.dispatch import evaluate_abilities_for_event
        state = ectx.state
        caster = (entities.caster or {}).get("id")
        target = (entities.target or {}).get("id")
        if state is None or caster is None or target is None:
            return OperationResult.ok()
        res = evaluate_abilities_for_event(state, caster, target, self.event, self.ranged) or []
        ectx.emit("EvaluateAbilities", caster=caster, target=target, results=res)
        return OperationResult.ok()


def _add_effect_targets(raw):
    """Normalise la sortie du selecteur-cible d'`AddEffect` en LISTE d'elements a poser (mirror de
    l'iteration native du selecteur par `AddEffectBehaviour`) : un dict d'unite / une position (col,row)
    NUE -> `[elem]` ; une liste (d'unites ou de tuiles) -> telle quelle ; None -> `[]`."""
    if raw is None:
        return []
    if isinstance(raw, dict):
        return [raw]
    if (isinstance(raw, tuple) and len(raw) == 2
            and all(isinstance(x, int) and not isinstance(x, bool) for x in raw)):
        return [raw]                      # position (col,row) NUE (ex. TargetTile / Tiles scalaire)
    return list(raw)


def _add_effect_target_id(elem, state):
    """Resout UN element du selecteur-cible en id-cible ECS pour `AddEffectOperation` : dict d'unite -> son
    id (unit-effect) ; position (col,row) -> l'id de TUILE via `board.id_at` (tile-effect, ex. `Tiles(target)`
    d'OnFireDamage) ; int -> deja un id de tuile (domaine `AdjacentTiles`). None si non resolvable. Mirror du
    natif `AddEffectBehaviour.Execute` : le selecteur rend des ENTITES ECS (unites OU tuiles)."""
    if isinstance(elem, dict):
        return elem.get("id")
    if isinstance(elem, bool):            # garde: bool est un int en Python
        return None
    if isinstance(elem, int):
        return elem                       # id de tuile deja resolu
    if (isinstance(elem, (tuple, list)) and len(elem) == 2
            and all(isinstance(x, int) and not isinstance(x, bool) for x in elem)):
        board = getattr(state, "board", None)          # position (col,row) -> id de tuile
        return board.id_at(elem[0], elem[1]) if board is not None else None
    return None


class AddEffect(AbilityBehaviour):
    """`DSLFactory.AddEffect @180de6d20` -> `AddEffectBehaviour.Execute` : pose un effet, `source` =
    `AbilityStateReference` (= le caster), sur CHAQUE cible du selecteur `target_sel`, duree
    `TurnsFromRounds(rounds)`. Wrapper MINCE au-dessus de `AddEffectOperation.execute` (mirror exact de
    l'imperatif). DIFFERE de `AddBondEffect` (qui LIE source+target = deux unites distinctes) : ici la source
    EST le caster. Emet 'AddEffect' par cible (payload `placed` = l'effet a-t-il ete REELLEMENT pose, i.e.
    `AddEffectOperation` non-None : False si deja present / cible nulle -> laisse l'appelant distinguer la
    re-pose no-op, cf. OnFireDamage). Effet PUR (stop=False).

    Le natif `AddEffectBehaviour` ITERE son selecteur-cible, qui rend des ENTITES ECS (UNITES ou TUILES) :
    - unit-domain (`Target()`/`Subject()`) -> effet sur l'unite (Stunned/Pinned de ThunderousAssault/
      CrushingClaws/SpiritLeech ; selecteurs mono-cible = 1 element -> chemin bit-IDENTIQUE a l'ancien
      `resolve_unit`) ;
    - tile-domain (`Tiles(Target())` d'OnFireDamage @1811c3a60) -> effet de TUILE (le selecteur rend la
      MainTile de la cible ; `_add_effect_target_id` la convertit en id de tuile). MEME `AddEffectOperation`.

    `duration_rounds` = nb de rounds (`TurnsFromRounds(rounds)`) ; `None` = duree DEFAUT de l'effet
    (`DefaultAmountOfRounds`, mirror de l'arg natif `0` d'`AddEffect` SANS `TurnsFromRounds` — ex. Pinned de
    CrushingClaws) vs explicite (ThunderousAssault Stunned = `TurnsFromRounds(1)`)."""
    __slots__ = ("effect_type", "name", "target_sel", "duration_rounds")

    def __init__(self, effect_type: int, name: str, target_sel: TargetsSelector, duration_rounds=1):
        self.effect_type, self.name = effect_type, name
        self.target_sel, self.duration_rounds = target_sel, duration_rounds

    def execute(self, entities, ectx):
        from ..operations.effects import AddEffectOperation
        state = ectx.state
        src = (entities.caster or {}).get("id")               # AbilityStateReference = caster (source)
        if state is None or src is None:
            return OperationResult.ok()
        # duration_rounds None -> pas d'override = duree DEFAUT (DefaultAmountOfRounds), mirror de l'arg natif
        # `0` d'AddEffect sans TurnsFromRounds (Pinned CrushingClaws) ; sinon TurnsFromRounds(rounds).
        dur = turns_from_rounds(self.duration_rounds) if self.duration_rounds is not None else None
        for elem in _add_effect_targets(self.target_sel.evaluate(entities)):  # natif : itere le selecteur
            tgt = _add_effect_target_id(elem, state)          # unit dict->id | (col,row)->tile id | int->tile id
            if tgt is None:
                continue
            eff = AddEffectOperation.execute(state, source=src, target=tgt, effect_type=self.effect_type,
                                             name=self.name, duration_override=dur)
            ectx.emit("AddEffect", source=src, target=tgt, effect_type=self.effect_type,
                      placed=eff is not None)
        return OperationResult.ok()


class RemoveEffect(AbilityBehaviour):
    """`DSLFactory.RemoveEffect @180df9cc0` -> `RemoveEffectBehaviour.Execute` : retire de la cible TOUS les
    effets du type `effect_type` (non consommes) et ANNULE leur StatModification (`<Effect>.RevertInternal`).
    `target` = `target_sel` (ex. `Caster()`/`Self@0x148` pour le reset ActOfFaith @181219eb0). Wrapper au-dessus
    de l'Operation impurative `revert_change_stat` (mirror exact de l'ancien `_reset_act_of_faith`). No-op si
    `state.effects`/cible absents. Emet 'RemoveEffect' (removed = nb de stacks retires). Effet PUR (stop=False).

    Frontiere classification (#149) : le NOEUD `RemoveEffect` (declaratif) au-dessus ; `ReverseModification`
    (revert par-source, impuratif) EN DESSOUS. L'effet DECLARE ses StatTypes revertes (`reverted_stats()`, DATA
    cote `entities/`) ; la feuille (runner/) EXECUTE le revert (`revert_change_stat`, couche runner) sur chacun,
    keye par `stat_mod_source`. Un stack SEEDE sans `stat_mod_source` = retire mais non reverte (limitation
    pre-existante : delta inconnu dans le residu opaque)."""
    __slots__ = ("effect_type", "target_sel")

    def __init__(self, effect_type: int, target_sel: TargetsSelector):
        self.effect_type, self.target_sel = int(effect_type), target_sel

    def execute(self, entities, ectx):
        from ..operations.stat_ops import revert_change_stat
        state = ectx.state
        if state is None or state.effects is None:
            return OperationResult.ok()
        tu = resolve_unit(self.target_sel, entities)
        tgt = tu.get("id") if tu else None
        if tgt is None:
            return OperationResult.ok()
        removed = 0
        for eff in state.effects.by_unit.get(int(tgt), []):
            if eff.consumed or eff.effect_type != self.effect_type:
                continue
            # revert par SOURCE (ReverseModification) : la valeur se re-clampe au read, sans delta stocke.
            src = getattr(eff, "stat_mod_source", None)
            if src is not None:
                for stat in eff.reverted_stats():
                    revert_change_stat(state, tgt, stat, src)
            eff.consumed = True
            removed += 1
        ectx.emit("RemoveEffect", target=tgt, effect_type=self.effect_type, removed=removed)
        return OperationResult.ok()


class Heal(AbilityBehaviour):
    """`DSLFactory.Heal(source, targets, amount) @...` -> `HealBehaviour.Execute` : soigne CHAQUE unite du
    selecteur `targets_sel` de `amount_fn(entities, ectx)` PV, via l'Operation portee `HealUnitOperation.
    execute` (mutation PV, plafond `hp_max`, gate `Cursed`). Wrapper MINCE au-dessus du mutateur ECS (mirror
    du 3e volet de `SpiritLeech.ExecuteBehaviour` = lifesteal). Le montant est calcule UNE fois par
    `amount_fn` = FOLD du `SetCache(PercentageOf(LastAttackDamageMade, ...))` natif (le Heal natif lit un
    montant CACHE derive de la derniere attaque ; l'`amount_fn` nommee (mirror `GetHealAmountForExecution`)
    le recompute en lisant le total de la derniere `AttackWithAttackDamage` dans `ectx.emitted`). `source`
    de soin = `ctx.caster`. No-op si montant <= 0. Emet 'Heal' (amount + heals=[{target, healed}]). PUR."""
    __slots__ = ("targets_sel", "amount_fn")

    def __init__(self, targets_sel: TargetsSelector, amount_fn):
        self.targets_sel, self.amount_fn = targets_sel, amount_fn

    def execute(self, entities, ectx):
        from ..operations.heal import HealUnitOperation
        state = ectx.state
        amount = int(self.amount_fn(entities, ectx) or 0)
        heals: list = []
        if state is not None and amount > 0:
            src = (entities.caster or {}).get("id")
            for u in (self.targets_sel.evaluate(entities) or []):
                tid = u.get("id") if isinstance(u, dict) else None
                if tid is None:
                    continue
                healed = HealUnitOperation.execute(state, tid, amount, source_id=src)
                heals.append({"target": tid, "healed": healed})
        ectx.emit("Heal", amount=amount, heals=heals)
        return OperationResult.ok()


class SetOnFire(AbilityBehaviour):
    """`FireOfAbsolutionAbility.SetOnFire` (child `Func<entities,behaviour>` du `Maybe` natif @18121f380) ->
    pose l'effet FEU DE TUILE (`EnvFireTile`) sur la TUILE COURANTE. Le `Maybe(child, AdjacentTiles(target),
    30)` natif itere ses tuiles et lie la tuile courante en sujet (== `Foreach(tiles, Maybe(30, SetOnFire))`
    cote port) : `SetOnFire` lit `entities.subject` = l'id de TUILE (int, PAS une unite — le `Foreach`
    tile-domain y pose l'element courant). Wrapper MINCE au-dessus de `AddEffectOperation.execute` (target =
    tile id, source = caster). N'emet 'SetOnFire' que si l'effet est REELLEMENT pose (AddEffect non-None :
    no-op si la tuile est deja en feu — == l'ancien imperatif `if AddEffectOperation.execute(...) is not None`).
    Effet PUR (stop=False)."""
    __slots__ = ("effect_type", "name")

    def __init__(self, effect_type: int, name: str = "Fire"):
        self.effect_type, self.name = int(effect_type), name

    def execute(self, entities, ectx):
        from ..operations.effects import AddEffectOperation
        state = ectx.state
        tile = entities.subject                          # tuile COURANTE (id) posee par le Foreach tile-domain
        src = (entities.caster or {}).get("id")
        if state is None or tile is None:
            return OperationResult.ok()
        if AddEffectOperation.execute(state, source=src, target=tile,
                                      effect_type=self.effect_type, name=self.name) is not None:
            ectx.emit("SetOnFire", tile=tile, source=src)
        return OperationResult.ok()


class PushUnit(AbilityBehaviour):
    """`DSLFactory.PushUnit @180df9540` -> `DisplaceUnitBehaviour(type=1).Execute @180fc3ff0` : pousse CHAQUE
    unite du selecteur `pushed_sel` A L'OPPOSE du `pusher_sel`, via N× `DisplaceUnitOperation(type=1=
    FindTileToPush @180e695e0)`. Args natifs : `pusher_sel` = +0x58 (le CASTER pour ThunderousAssault/
    CrushingClaws, PAS la cible), `pushed_sel` = +0x60 (Target() pour ThunderousAssault ; Subject() pour le
    splash CrushingClaws pose par le Foreach). Wrapper MINCE au-dessus du mutateur `DisplaceUnitOperation`.

    DETERMINISTE : la geometrie du push (FindTileToPush/GetTilesBehind) est PURE (aucun tirage rng) -> inserer
    `PushUnit` dans un arbre ne DECALE PAS l'ordre RNG (les tests de degat bit-exact restent valides). Effet
    PUR (stop=False). Itere les poussees triees par id (== ordre de lecture du Foreach natif). Emet 'PushUnit'
    par unite (payload `moved`/`to` = l'unite a-t-elle REELLEMENT ete deplacee, i.e. deplacable + tuile libre
    derriere : False si BigTarget/Immovable/mort ou bord/mur/occupee)."""
    __slots__ = ("pusher_sel", "pushed_sel")

    def __init__(self, pusher_sel: TargetsSelector, pushed_sel: TargetsSelector):
        self.pusher_sel = pusher_sel
        self.pushed_sel = pushed_sel

    def execute(self, entities, ectx):
        from ..operations.displace import DisplaceUnitOperation
        state = ectx.state
        pusher = resolve_unit(self.pusher_sel, entities)     # First(+0x58) = le caster
        if state is None or pusher is None:
            return OperationResult.ok()
        pusher_id = pusher.get("id")
        pushed = [u for u in _units_of(self.pushed_sel, entities)
                  if isinstance(u, dict) and u.get("id") is not None]
        for u in sorted(pushed, key=lambda x: x["id"]):      # ordre de lecture = id (mirror Foreach natif)
            res = DisplaceUnitOperation(pusher_id, u["id"]).execute(state, ectx.bus)
            ectx.emit("PushUnit", pusher=pusher_id, pushed=u["id"],
                      moved=bool((res or {}).get("moved")), to=(res or {}).get("to"))
        return OperationResult.ok()


class MoveUnit(AbilityBehaviour):
    """`DSLFactory.MoveUnit @180df6ae0` -> `MoveUnitBehaviour.Execute @180fca4f0` : deplace le SUJET
    (`subject_sel`, +0x50) vers la 1re tuile-destination LIBRE (`dest_tile_sel`, +0x58 = `CanAddUnit(...)`),
    via l'Operation deja portee `MoveUnitOperation`. 2e volet du DEPLACEMENT de ThunderousAssault : apres le
    PUSH de la cible, le CASTER CHARGE dans la tuile liberee.

    Args natifs (ThunderousAssault) : `subject_sel` = Caster() (+0x160) ; `dest_tile_sel` =
    `CanAddUnit(Cache(First(Nearest(Tiles(target), casterPos))))` = la tuile d'ORIGINE de la cible (le MEME
    `Cache` que l'attaque, MEMOISE avant le push) gated LIBRE.

    FIDELITE du cache -> tuile PRE-push (VRAI noeud `Cache`, #27) : `ctx.target` est un `LiveUnit` (vue
    live-by-ref, pos re-lue du state a chaque acces -- Voie A #6). Donc un `TargetTile()` NU relu APRES le push
    rendrait la tuile POST-push (atterrissage OCCUPE) -> aucune charge. Le natif MEMOISE via
    `Cache(First(Nearest(Tiles(target),casterPos)))` EVALUE a l'attaque (pre-push) et PARTAGE avec la charge ;
    le port passe donc `dest_tile_sel = Cache(TargetTile())` PRIME pre-push par `ThunderousAssaultAbility.
    execute_behaviour` (single-tile target -> collapse `TargetTile()`, meme collapse que l'attaque
    `Units(Cache(First(Nearest(...))))` -> `Target()`). Sans ce `Cache`, le bug #27 : le caster ne charge jamais.

    Garde `CanAddUnit` = tuile LIBRE, lue sur l'ETAT LIVE (post-push) -- mirror `CanAddUnitTileSelector.Select
    @180ee4230` qui teste `TileExtensions.CanAddUnitFromAbility` sur le CONTENU DE TUILE live -- et NON via le
    noeud `CanAddUnit` du port (snapshot-based : il verrait la cible occuper encore sa tuile pre-push -> faux
    post-push). Live = walkable ET aucun occupant VIVANT (`_occupied` ; les MORTS ne comptent pas -> quand
    l'attaque a TUE la cible, sa tuile est deja libre et le caster y entre). La garde `local_308==0` (defaut)
    de `MoveUnitBehaviour.Execute` (dest vide -> `return` sans move) = ici : push echoue (BigTarget/Immovable/
    bord) -> cible restee sur sa tuile -> tuile occupee live -> pas de move (le caster ne suit QUE si le push
    a reussi).

    NON portes (=> slice-21b+, flagges comme le push) : les 5 selecteurs d'OPTIONS (+0x70/+0x78/+0x80/+0x88/
    +0x90) sont TOUS nuls a ce call-site (defauts natifs) -> aucun flag actif ; la cascade after-move
    flag-driven (overwatch au CHARGE, kill-steppable pendant le move) n'est PAS declenchee (comme le push,
    `MoveUnitOperation.execute` direct = position + moved_this_turn + tile-defense, PAS le vecteur after-move
    du handler de message). DETERMINISTE (aucun tirage rng) -> ne decale pas l'ordre RNG. Emet 'MoveUnit'. PUR."""
    __slots__ = ("subject_sel", "dest_tile_sel")

    def __init__(self, subject_sel: TargetsSelector, dest_tile_sel: TargetsSelector):
        self.subject_sel = subject_sel
        self.dest_tile_sel = dest_tile_sel

    def execute(self, entities, ectx):
        from ..operations.movement import MoveUnitOperation
        from ..operations.displace import _occupied      # occupation LIVE (post-mutation), exclut sujet + morts
        state = ectx.state
        subject = resolve_unit(self.subject_sel, entities)
        board = getattr(state, "board", None)
        if state is None or subject is None or board is None:
            return OperationResult.ok()
        sid = subject.get("id")
        dest = self.dest_tile_sel.evaluate(entities)     # tuile(s) candidate(s) = snapshot PRE-push (le cache)
        cands = [dest] if (isinstance(dest, tuple) and len(dest) == 2) else list(dest or [])
        if sid is None:
            return OperationResult.ok()
        occ = _occupied(state, sid)                      # CanAddUnit live : occupants VIVANTS (sujet exclu)
        for pos in cands:
            if not (isinstance(pos, tuple) and len(pos) == 2):
                continue
            tid = board.id_at(pos[0], pos[1])
            if tid is None or not board.walkable(tid) or pos in occ:   # walkable ET libre (post-push)
                continue
            MoveUnitOperation(sid, pos).execute(state, ectx.bus)       # 1re tuile libre -> le caster charge
            ectx.emit("MoveUnit", subject=sid, moved=True, to=pos)
            return OperationResult.ok()
        ectx.emit("MoveUnit", subject=sid, moved=False)  # garde local_308==0 : aucune tuile libre -> pas de move
        return OperationResult.ok()


class ChangeStat(AbilityBehaviour):
    """`DSLFactory.ChangeStat @180debdc0` -> `ChangeStatBehaviour.Execute @180fbfb10` : applique une
    MODIFICATION DE STAT (`ModifyStatMessage` -> `UnitStats.Transform`) sur le(s) sujet(s) de `target_sel`,
    stat `stat_type` (natif `Position(statType,0,0)`), selon `mode` (lu au decompile @180fbfb10, champ
    +0x68) :
        0 = SetAbsolute (new = delta - GetStat)           2 = Add       (new = GetStat + delta)
        1 = Clamp/Min-Max (Min(Max(GetStat+delta,0),max)) 3 = Subtract  (new = Max(GetStat - delta, 0))
        4 = source-scaled (StatModifier depuis une source)   -- seuls 2/3 sont portes (usage actuel).
    Porte via `apply_change_stat`/`revert_change_stat` (`operations.stat_ops` = `ModifyStatMessage` apply
    part5 / revert part6, PAR-SOURCE) : `mode="add"` -> `apply_change_stat(+delta)` attribue a `source` ;
    `mode="revert"` -> `revert_change_stat(source)`. Le revert par-source == le natif mode3 `Max(GetStat -
    delta, 0)` TANT QU'aucun autre modifier ne touche la stat entre l'add et le revert -- cas du buff
    NET-NUL scope-attaque (HeroicFusillade encadre son attaque de `ChangeStat(CRIT_DAMAGE, Add, mag)` /
    `ChangeStat(CRIT_DAMAGE, Sub, mag)`). Le combat relit `ctx.stat(stat_type)` AU ROLL (cf.
    `damage._crit_params`) -> un buff pose AVANT l'attaque est OBSERVABLE (crit +mag), retire apres.

    `amount` = int OU callable `(entities, ectx) -> int` (mag calculee LIVE, ex. `extraCritDmg x nbFree`
    lu POST-move). `source` = cle de source PARTAGEE entre l'add et le revert (revert exact par-source).
    Emet 'ChangeStat'. PUR (stop=False)."""
    __slots__ = ("target_sel", "stat_type", "mode", "source", "amount")

    def __init__(self, target_sel: TargetsSelector, stat_type: int, mode: str, source, amount=0):
        self.target_sel, self.stat_type, self.mode = target_sel, int(stat_type), mode
        self.source, self.amount = source, amount

    def execute(self, entities, ectx):
        from ..operations.stat_ops import apply_change_stat, revert_change_stat
        state = ectx.state
        if state is None:
            return OperationResult.ok()
        for u in _units_of(self.target_sel, entities):
            uid = u.get("id") if isinstance(u, dict) else None
            if uid is None:
                continue
            if self.mode == "revert":                     # ChangeStat mode 3 (Subtract) = undo net-nul
                val = revert_change_stat(state, uid, self.stat_type, self.source)
                ectx.emit("ChangeStat", unit=uid, stat=self.stat_type, mode="revert", value=val)
            else:                                         # ChangeStat mode 2 (Add)
                amt = int(self.amount(entities, ectx) if callable(self.amount) else self.amount)
                val = apply_change_stat(state, uid, self.stat_type, self.source, amt)
                ectx.emit("ChangeStat", unit=uid, stat=self.stat_type, mode="add", amount=amt, value=val)
        return OperationResult.ok()


class KillDeadUnits(AbilityBehaviour):
    """`DSLFactory.KillDeadUnits @180df5c60` = `Kill(subject, DownedUnits(units_sel), options) @180df5cb0`
    -> `KillUnitBehaviour.Execute @180fc8b10` : pour chaque unite DOWNED (flag 0xf, via
    `DownedUnits`=`UnitsWithFlagSelector(units_sel, 0xf, want=1) @180dee790`) NON exemptee (le natif skippe
    `HasFlag(9|6|0x1a)`), emet une Operation de KILL (finalise la mort : retrait + on-death). Args natifs
    (ThunderousAssault) : `subject_sel` = Caster() (+0x160), `units_sel` = Target() (+0x178), options =
    `ForClearDeadUnitsBlockReviveOverkill`.

    Role natif : la mort y est DIFFEREE -- l'attaque « DOWN » la cible (PV<=0, flag 0xf) sans la retirer ; ce
    KillDeadUnits POST-push finalise le cadavre pour que `MoveUnit` trouve la tuile libre meme quand l'attaque
    a TUE la cible.

    Chez NOUS : la mort est finalisee INLINE dans l'attaque (`AttackDamageOperation` : `uc.alive=False` +
    death-triggers, cf. damage.py:152) et les morts ne comptent PAS dans l'occupation (`_occupied`/`CanAddUnit`
    excluent `not alive`). Donc a ce point une cible tuee est DEJA finalisee (alive=False, hors-occupation,
    on-death fire) -> ce volet est OBSERVABLEMENT un NO-OP : re-emettre un kill DOUBLE-FIRE les on-death. La
    feuille MIRROR donc la STRUCTURE (filtre DownedUnits LIVE) SANS re-muter -- elle journalise les downed pour
    le replay-diff. (Si notre modele de mort passait un jour en DIFFERE, l'Operation de kill viendrait ICI.)
    `MoveUnit` trouve la tuile libre via l'occupation LIVE (morts exclus) -> l'ordre natif est respecte sans
    mutation redondante. Filtre DOWNED lu en LIVE (`UnitComponent.alive`) et NON sur le dict snapshot (fige a
    l'etat PRE-attaque -> alive=True meme pour une cible tuee par l'attaque). PUR."""
    __slots__ = ("subject_sel", "units_sel")

    def __init__(self, subject_sel: TargetsSelector, units_sel: TargetsSelector):
        self.subject_sel = subject_sel
        self.units_sel = units_sel

    def execute(self, entities, ectx):
        state = ectx.state
        downed: list = []
        for u in _units_of(self.units_sel, entities):
            uid = u.get("id") if isinstance(u, dict) else None
            if uid is None or state is None:
                continue
            e = state.get_entity(uid)
            uc = e.get_component(UnitComponent) if e is not None else None
            if uc is not None and not uc.alive:          # DOWNED live (flag 0xf) ; mort deja finalisee inline
                downed.append(uid)
        ectx.emit("KillDeadUnits", downed=downed)        # mirror structurel : pas de re-mutation (double-fire)
        return OperationResult.ok()


class RemoveUnit(AbilityBehaviour):
    """`DSLFactory.RemoveUnit @180df9fd0` -> `RemoveUnitBehaviour.Execute @180fce1d0` : RETIRE de la
    bataille chaque unite du selecteur — un DESPAWN, PAS une mort (i2 MV71 : « the one with the lowest
    Health is REMOVED ») : AUCUN vecteur on-death (pas de PreUnitDeath/UnitDefeated, pas d'attribution
    de tueur). Call-sites portes (MV71SniperDroneSquadAttack @181108900) : eviction (a)
    `RemoveUnit(Units(Get(tile),1,3))` = le drone occupant la tuile choisie (fallback PickTile) ;
    eviction (b) `RemoveUnit(First(AlreadySpawnedSummonsSortedSelector,1,0))` = le drone le plus faible
    au cap maxSummons.

    Port : marque `alive=False` (libere l'occupation — `_occupied`/`CanAddUnit` excluent les morts) et
    consomme les effets portes par l'unite (l'entite-effet native part avec son porteur). SANS
    death-triggers (difference structurelle avec la mort d'`AttackDamageOperation`). Emet 'RemoveUnit'
    par unite. PUR (stop=False)."""
    __slots__ = ("units_sel",)

    def __init__(self, units_sel: TargetsSelector):
        self.units_sel = units_sel

    def execute(self, entities, ectx):
        state = ectx.state
        if state is None:
            return OperationResult.ok()
        for u in sorted((x for x in _units_of(self.units_sel, entities)
                         if isinstance(x, dict) and x.get("id") is not None),
                        key=lambda x: x["id"]):              # ordre de lecture = id
            uid = u["id"]
            e = state.get_entity(uid)
            uc = e.get_component(UnitComponent) if e is not None else None
            if uc is None or not uc.alive:
                continue
            uc.alive = False                                 # despawn : PAS de vecteur on-death
            if state.effects is not None:                    # les effets portes partent avec l'unite
                for eff in state.effects.by_unit.get(int(uid), []):
                    eff.consumed = True
            ectx.emit("RemoveUnit", unit=uid)
        return OperationResult.ok()


class UseActiveAbility(AbilityBehaviour):
    """`DSLFactory.UseActiveAbility @180e015e0` -> `UseActiveAbilityBehaviour.Execute @180fd9930` : pour
    CHAQUE cible du selecteur `targets_sel` (+0x58), le SUJET (`subject_sel`, +0x50) UTILISE son ability
    active `ability_type` (+0x60) -- dispatch RECURSIF de l'ability sur la cible (le natif emet 1 Operation
    <<use-ability>> par cible via le collecteur `proc`, en fixant `subject`=cible courante dans le ctx).

    Seul usage porte (Groupe 3) : FinalJustice `UseActiveAbility(Self@0x148, SortUnitsByDamageUtility(
    ValidNormalAttackTargets(...)), UnitNormalAttackType(self))` = en MOURANT, Kharn porte UNE attaque
    NORMALE sur la meilleure cible. `UnitNormalAttackType` = l'attaque normale du sujet ; chez nous, la
    dispatcher = `AttackDamageOperation.execute` (resolveur d'attaque normale ECS : selection d'arme par
    distance, spread, reduce/armure -- DEJA bit-exact). ⇒ la feuille SPECIALISE le dispatch a l'attaque
    normale (== le corps imperatif `_finaljustice_attack` valide) : `subject`=Caster(), `target`=la cible.

    COLLAPSE du selecteur AI-target (doctrine slice-18/19) : `SortUnitsByDamageUtility(ValidNormalAttack
    Targets)` = un selecteur AI LOURD (kind S, chevauche le playbook), reste IMPERATIF (`_finaljustice
    _target`) et resolu AVANT le cast -> passe comme `Target()` (meme collapse que ThunderousAssault
    `Units(Cache(First(Nearest(...))))` -> la cible du message). DSL-ification du selecteur = tache S-family.

    NON porte / flagge : (1) dispatch d'une ability NON-normale -- aucun usage Groupe 3 ; si un jour une
    ability `UseActiveAbility(<active non-normale>)` apparait, il faudra re-entrer le pipeline d'ability via
    le handler (`visit_ActiveAbilityMessage`), pas `AttackDamageOperation.execute` ; (2) les OPTIONS
    +0x68..+0xac (source AbilityOrEffect, flags) inertes pour une attaque normale. `spread_pct` = variance
    d'arme du dispatch normal (defaut 20 = defaut de `AttackDamageOperation.execute`). Itere les cibles
    triees par id (ordre de lecture natif). Emet 'UseActiveAbility' par cible. PUR (non court-circuitant)."""
    __slots__ = ("subject_sel", "targets_sel", "spread_pct")

    def __init__(self, subject_sel: TargetsSelector, targets_sel: TargetsSelector, spread_pct: int = 20):
        self.subject_sel = subject_sel
        self.targets_sel = targets_sel
        self.spread_pct = int(spread_pct)

    def execute(self, entities, ectx):
        from ..operations.damage import AttackDamageOperation
        state = ectx.state
        subject = resolve_unit(self.subject_sel, entities)
        if state is None or subject is None:
            return OperationResult.ok()
        sid = subject.get("id")
        targets = [u for u in _units_of(self.targets_sel, entities)
                   if isinstance(u, dict) and u.get("id") is not None]
        for tu in sorted(targets, key=lambda x: x["id"]):    # ordre de lecture = id (mirror OrderBy natif)
            tid = tu["id"]
            res = AttackDamageOperation.execute(state, sid, tid, self.spread_pct)  # dispatch attaque normale
            ectx.emit("UseActiveAbility", subject=sid, target=tid, attack=res)
        return OperationResult.ok()


class CreateShield(AbilityBehaviour):
    """`DSLFactory.CreateShield @180ded000` -> `CreateShieldBehaviour.Execute @180fc2650` : pour CHAQUE cible
    du selecteur `target_sel` (+0x50), accorde/rafraichit un bouclier de `amount` (formule +0x58, scalaire)
    duree `duration` rounds via `ShieldComponent.add_or_update_shield` (cumule meme-source/meme-duree, sinon
    nouvelle instance ; no-op si amount<=0). Options +0x60..+0x88 (2e amount Nullable +0x78, flags) non
    portees (aucun usage Groupe 3). `source` = `AbilityOrEffect(self.Id)` natif (attribution / stack same-source).

    Seul usage porte (Groupe 3) : ArcaneShield `CreateShield(Cache(First(SortByFormula(Randomize(Units
    WithoutTrait(SurroundingFriends(self,range),0x1b)) .Otherwise self, Sum(dist,faction,chaos,not-self),
    asc))), ConfigVar(0x27=shieldHp), self.Id, TurnsFromRounds(1))` = Thaumachus accorde un bouclier 1 round
    a l'ami prefere (faction > distance > pas-soi) sinon soi. Le selecteur AI-target LOURD (kind S :
    SurroundingFriends -> UnitsWithoutTrait -> Randomize -> SortByFormula -> First) reste IMPERATIF
    (`_arcaneshield_target`) et est COLLAPSE en `Target()` ; le montant `ConfigVar(0x27)` (formule V,
    `shieldHp[level] x mult%`) est calcule IMPERATIVEMENT (`ability_var`) et passe comme SCALAIRE -- meme
    collapse que FinalJustice (doctrine slice-18/19). DSL-ification du selecteur AI + de la formule ConfigVar
    = taches S/V (flaggees).

    `amount` = scalaire (int) OU noeud-formule (`.evaluate(entities)`). `duration` = rounds restants
    (ArcaneShield=1 ; None=permanent). `source` = etiquette de source (stack same-source). Itere les cibles
    triees par id (ordre de lecture natif). Emet 'CreateShield' par cible. PUR (non court-circuitant)."""
    __slots__ = ("target_sel", "amount", "duration", "source")

    def __init__(self, target_sel: TargetsSelector, amount, duration=None, source=None):
        self.target_sel = target_sel
        self.amount = amount
        self.duration = duration
        self.source = source

    def execute(self, entities, ectx):
        from ..components import ShieldComponent
        state = ectx.state
        if state is None:
            return OperationResult.ok()
        amt = int(self.amount.evaluate(entities)) if hasattr(self.amount, "evaluate") else int(self.amount)
        if amt <= 0:                                     # no-op (mirror add_or_update_shield amount<=0)
            return OperationResult.ok()
        targets = [u for u in _units_of(self.target_sel, entities)
                   if isinstance(u, dict) and u.get("id") is not None]
        for tu in sorted(targets, key=lambda x: x["id"]):    # ordre de lecture = id
            tid = tu["id"]
            te = state.get_entity(tid)
            if te is None:
                continue
            shc = te.get_component(ShieldComponent)
            if shc is None:
                shc = ShieldComponent()
                te.add_component(shc)
            shc.add_or_update_shield(amt, source=self.source, remaining=self.duration)
            ectx.emit("CreateShield", target=tid, amount=amt, remaining=self.duration,
                      shield_total=shc.get_total_shield())
        return OperationResult.ok()
