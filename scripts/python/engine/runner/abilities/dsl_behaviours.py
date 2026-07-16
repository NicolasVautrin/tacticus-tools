"""Behaviours d'ability portes en ARBRES DSL EXECUTABLES (#149 slice-2b) + feuilles CONCRETES
(bridge dsl -> runner Operations) + builder `entities_from_state`.

Les combinateurs (`engine.entities.behaviours`) + la base + infra (`engine.dsl.effects`) vivent en amont ; ICI les
feuilles MINCES qui EMETTENT les Operations DEJA portees (`runner/operations`) et les arbres d'ability
(mirror `<Ability>.CreateBehaviour`). `entities_from_state` construit le `DslContext` (= l'`entities`
natif lu par les selecteurs) depuis le `State` runner. cf. docs/rl/dsl-effect-nodes.md.

MIGRATION cote-a-cote : ces arbres reproduisent, en composant les nœuds natifs partages, ce que les
`execute_*` imperatifs (`abilities/loki.py`, `operations/spawn.py`) font a la main ; on les valide
replay-diff (DSL == imperatif == live) AVANT de basculer et retirer l'imperatif.

Arbre GetEmRuntz (`GetEmRuntzAbility.ExecuteBehaviour @1811e2210`, DECOMPILE gqfc5mff6c) :
    ExecuteAtomic( Spawn(Cache(GetSpawnTileSelector), WithStatsFromConfig) )     # spawn tous les grots
    Execute( op_Addition(
        PerformAIAttackFromCurrentPosition(Cache(GetSpawnTileSelector)),          # les grots attaquent
        Foreach(Children=AllAliveMachinesSelector, TauntWithNewChildrenWhoDidDamage) ) )   # + Taunt
Ordre NATIF = TOUS les spawns, PUIS toutes les attaques, PUIS tous les Taunts (l'imperatif interleave
attaque+Taunt par grot ; le DSL suit le NATIF, equivalent tant que le Taunt ne tire pas de RNG).
"""
from __future__ import annotations

from ...dsl.base import DslContext, Const, AAmountFormula, TargetsSelector
from ...dsl.effects import AbilityBehaviour, OperationResult
from ...entities.behaviours import Seq, Foreach, If, AtomicGroup, op_add
from ...entities.selectors import get_spawn_tile_selector, Subject, Cache
from ...entities.triggers import AmountIsGreaterThanZero, AmountIsEqual, IsAlive, TriggerAnd
from ..components import (OwnerComponent, PositionComponent, UnitComponent, StatsComponent,
                          HealthComponent)
from .base import turns_from_rounds
from ...entities.traits.unit_trait import UnitTrait, has_trait
from ...entities.effect_type import EffectType

# 0x1b=27 = `EffectType.Taunted_OnlySpecificTargets` (COMPOSITE 25/26/1237) — l'effet BOND pose par
# `AddBondEffect(0x1b, ...)` du Taunt. (Meme const que `loki.TAUNTED` / CrushingClaws, cf. #158.)
TAUNTED = int(EffectType.Taunted_OnlySpecificTargets)


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


def entities_from_state(state, caster_id: int) -> DslContext:
    """Construit l'`AbilityEntities` (= `DslContext`) lu par les selecteurs d'un behaviour, depuis le
    `State` runner : `units` = dicts (cf. `_unit_dict`), `caster`, `board` (= `state.board`),
    `has_trait(unit, traitId)` (mirror `UnitExtensions.HasFlag`, via l'enum `UnitTrait` + le set de noms
    `ctx.traits`). `children=[]` = accumulateur de spawn FRAIS pour CE cast (mirror factory+0x148)."""
    units: list = []
    caster = None
    for eid, e in state.entities.items():
        u = _unit_dict(state, eid, e)
        units.append(u)
        if eid == caster_id:
            caster = u

    def _has_trait(unit, trait_id):
        try:
            enum = UnitTrait(int(trait_id))
        except ValueError:
            return False
        return has_trait(unit.get("_traits") or set(), enum)

    return DslContext(units=units, caster=caster, board=state.board, has_trait=_has_trait, children=[])


# --- Accesseurs runtime lus par le Taunt (mirror des formules DSLFactory ; lisent le dict enfant que
#     `PerformAIAttack` annote). Le compteur runtime GENERAL n'est pas capte offline -> defaut sur unite
#     non-enfant (documente, meme regime que `accessors.TotalTimesAttacked`).

def _resolve_unit(node, ctx) -> dict | None:
    """Evalue `node` (souvent `Subject()`) en UN dict d'unite (dict direct, ou 1er dict d'une liste)."""
    v = node.evaluate(ctx)
    if isinstance(v, dict):
        return v
    if isinstance(v, (list, tuple)):
        for x in v:
            if isinstance(x, dict):
                return x
    return None


class Children(TargetsSelector):
    """`DSLFactory.Children @180debed0` = `AllAliveMachinesSelector` : les enfants (summons) produits par
    CE cast. Port = l'accumulateur `ctx.children` (mirror factory+0x148) alimente par les feuilles
    `SpawnUnit`. ⚠ Le filtre `AllAlive` du natif est un no-op offline pour l'on-appearance de CE cast
    (les grots survivent a leur propre apparition — ils ne bougent pas -> pas d'overwatch ; l'imperatif
    ne filtre pas non plus les morts). cf. `TauntWithNewChildrenWhoDidDamage`."""
    def select(self, ctx):
        return list(getattr(ctx, "children", None) or [])


class TotalAttacksMade(AAmountFormula):
    """`DSLFactory.TotalAttacksMade @180dfe090` : nb d'attaques faites par l'unite (compteur runtime). Port
    on-appearance : `PerformAIAttack` pose `_attacks_made` sur le dict enfant (0 si pas d'attaque). Unite
    hors-cast -> 0 (compteur general non capte offline, cf. `accessors.TotalTimesAttacked`)."""
    def __init__(self, unit: TargetsSelector):
        self.unit = unit

    def calculate(self, ctx):
        u = _resolve_unit(self.unit, ctx)
        return int((u or {}).get("_attacks_made", 0) or 0)


class LastUnitAttackedBy(TargetsSelector):
    """`DSLFactory.LastUnitAttackedBy @180df5ee0` : derniere unite attaquee par l'unite. Port : le dict
    FRAIS (etat POST-attaque, relu de `ectx.state` par `PerformAIAttack`) de la cible frappee -> champ
    `_last_attacked` de l'enfant (None si aucune). Ce dict porte `alive`/`hp` COURANTS -> `IsAlive(
    LastUnitAttackedBy(child))` lit l'etat vivant APRES l'attaque (mirror de la garde live de l'imperatif)."""
    def __init__(self, unit: TargetsSelector):
        self.unit = unit

    def select(self, ctx):
        u = _resolve_unit(self.unit, ctx)
        return (u or {}).get("_last_attacked")


class UnitTurnsStarted(AAmountFormula):
    """`DSLFactory.UnitTurnsStarted @180dff280` : nb de tours entames par l'unite (compteur runtime). Le
    natif compare (via `AmountIsEqual`) le `turnsStarted` de l'owner CAPTURE au cast (`factory+0xb8`) au
    `UnitTurnsStarted(child)` -> ne retient que les enfants NEUFS de CE cast. Offline le compteur n'est pas
    capte -> `_turns_started` de l'enfant (SpawnUnit pose 0) ; couple a `Const(0)` (owner fraichement dans
    nos runners) l'egalite tient EXACTEMENT comme le natif la satisfait pour les enfants neufs. Unite
    hors-cast -> 0. ⚠ Mid-bataille (owner turnsStarted>0) ce couple degrade demanderait les vrais compteurs
    runtime (gap offline documente, meme regime que `times_attacked`/`turns_per_round`)."""
    def __init__(self, unit: TargetsSelector):
        self.unit = unit

    def calculate(self, ctx):
        u = _resolve_unit(self.unit, ctx)
        return int((u or {}).get("_turns_started", 0) or 0)


class Spawn(AbilityBehaviour):
    """`DSLFactory.Spawn @180dfbd50` -> `SpawnUnitBehaviour.Execute @180fd3d80` : itere son TILE-SELECTEUR
    EN INTERNE (mirror natif -- le `Spawn` n'est PAS un `Foreach(tiles, SpawnUnit)` externe, il enumere ses
    tuiles lui-meme) et spawn UNE unite par tuile, stats `WithStatsFromConfig(summon_ability)`, owner =
    team+player du caster. Wrapper au-dessus de l'Operation portee `_spawn_config_grot` (mirror de l'inline
    de `execute_getemruntz`) : level/mult lus du `StatsComponent` du caster dans `ectx.state`. Chaque enfant
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
    attaque l'ennemi le plus proche via `AttackDamageOperation.execute` (approx du choix AI natif = MEME que
    l'imperatif `GetEmRuntzAbility.execute_behaviour`, live-valide). Annote le dict enfant (`_attacks_made`,
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


class AddBondEffect(AbilityBehaviour):
    """`DSLFactory.AddBondEffect(0x1b, stateRef, source, target, ..., TurnsFromRounds(1)) @1811e27a0` : pose
    l'effet BOND `Taunted_OnlySpecificTargets` (0x1b=27, COMPOSITE 25/26/1237) reliant `source` (l'enfant/
    grot) et `target` (`LastUnitAttackedBy` = l'ennemi frappe), duree `TurnsFromRounds(rounds)`. Wrapper
    MINCE au-dessus de `AddEffectOperation.execute` (mirror exact de l'imperatif : source=grot, target=
    ennemi). `source_ref`/`target_ref` = Nodes resolus au dict courant -> ids. No-op si source/target
    absents. Emet 'AddBondEffect'. Effet PUR (stop=False)."""
    __slots__ = ("effect_type", "name", "source_ref", "target_ref", "duration_rounds")

    def __init__(self, effect_type: int, name: str, source_ref: TargetsSelector, target_ref: TargetsSelector,
                 duration_rounds: int = 1):
        self.effect_type, self.name = effect_type, name
        self.source_ref, self.target_ref = source_ref, target_ref
        self.duration_rounds = duration_rounds

    def execute(self, entities, ectx):
        from ..operations.effects import AddEffectOperation
        su = _resolve_unit(self.source_ref, entities)
        tu = _resolve_unit(self.target_ref, entities)
        src = su.get("id") if su else None
        tgt = tu.get("id") if tu else None
        if src is None or tgt is None or ectx.state is None:
            return OperationResult.ok()
        AddEffectOperation.execute(ectx.state, source=src, target=tgt, effect_type=self.effect_type,
                                   name=self.name, duration_override=turns_from_rounds(self.duration_rounds))
        ectx.emit("AddBondEffect", source=src, target=tgt, effect_type=self.effect_type)
        return OperationResult.ok()


def getemruntz_taunt_tree() -> If:
    """Corps `Func<entities,behaviour>` de `TauntWithNewChildrenWhoDidDamage @1811e27a0` (DECOMPILE) pour
    l'enfant COURANT (`Subject()`, pose par le `Foreach(Children)`) :
        If( AmountIsGreaterThanZero(TotalAttacksMade(child))            # le grot a attaque
            & AmountIsEqual(capturedTurns, UnitTurnsStarted(child))     # enfant NEUF de ce cast
            & IsAlive(LastUnitAttackedBy(child)),                       # l'ennemi frappe est vivant
            AddBondEffect(0x1b Taunted, source=child, target=LastUnitAttackedBy(child), TurnsFromRounds(1)) )
    `op_BitwiseAnd` (2x) = `TriggerAnd`. Nœud STATIQUE (lit `Subject()` a l'eval) -> passe en body de
    `Foreach`. `capturedTurns` = `Const(0)` (owner fraichement, cf. `UnitTurnsStarted`)."""
    child = Subject()
    cond = TriggerAnd(
        TriggerAnd(AmountIsGreaterThanZero(TotalAttacksMade(child)),
                   AmountIsEqual(Const(0), UnitTurnsStarted(child))),
        IsAlive(LastUnitAttackedBy(child)))
    return If(cond, AddBondEffect(TAUNTED, "Taunted_OnlySpecificTargets",
                                  child, LastUnitAttackedBy(child), 1))


def getemruntz_tree() -> Seq:
    """Arbre COMPLET de `GetEmRuntzAbility.ExecuteBehaviour @1811e2210` (id 1045, MIRROR 1:1 du DECOMPILE) :
        cache = Cache(GetSpawnTileSelector @1811e26b0)             # @180deb0d0 -- PARTAGE Spawn/Attack (memoise)
        ExecuteAtomic( Spawn(cache) )                             # @180fb0930 inline -> grots materialises
        Execute( op_Addition( PerformAIAttackFromCurrentPosition(cache),   # les grots (sur les tuiles cache) attaquent
                              Foreach(Children, Taunt) ) )        # + Taunt de la cible frappee
    Port : `Seq(AtomicGroup(Spawn(cache)), op_add(PerformAIAttack(cache), Foreach(Children(), taunt)))`.
    Le `cache` est PARTAGE entre `Spawn` et `PerformAIAttack` (mirror natif : le MEME `Cache(GetSpawnTileSelector)`
    est passe aux deux nœuds) -> memoise les tuiles LIBRES PRE-spawn (RE #200 : le CacheSelector memoise ;
    sans ca `PerformAIAttack` relirait `CanAddUnit` post-spawn et exclurait les tuiles occupees par les grots).
    `AtomicGroup` = inline (RE #201 : `AtomicGroupOperation.Execute` invoque son child sur-le-champ, PAS
    differe). `op_add`/`Seq` = `CombinedBehaviour` (effets PURS -> pas de court-circuit -> les 3 volets
    s'executent). Ordre = tous les spawns (inline dans l'AtomicGroup) PUIS toutes les attaques PUIS tous les
    Taunts (NATIF, prouve RE #200). Replay-diff vs l'imperatif `GetEmRuntzAbility.execute_behaviour`."""
    cache = Cache(get_spawn_tile_selector())                       # @180deb0d0 -- PARTAGE (memoise pre-spawn)
    return Seq(
        AtomicGroup(Spawn(cache, "GetEmRuntz")),                   # ExecuteAtomic(Spawn(cache)) -- inline
        op_add(PerformAIAttack(cache),                             # Execute( op_Addition(
               Foreach(Children(), getemruntz_taunt_tree())))      #   PerformAIAttack(cache), Foreach(Children, Taunt) ))
