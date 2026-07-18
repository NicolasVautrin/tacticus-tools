"""Abilities actives de SUMMON du namespace natif `Abilities.Active.Loki.*` — spawn d'unites :
ScarabHive (necroSpyder), ScarabSummon (auto-dedoublement necroSmnSwarm), GetEmRuntz (orksRuntherd).
+ les helpers on-appearance partages (`_summon_on_appearance_attack`, `_nearest_enemy`) consommes par
les feuilles `SpawnSummon`/`SpawnReplica`/`PerformAIAttack` (`../behaviours.py`). Cf. `loki/__init__.py`."""
from __future__ import annotations

from typing import Optional, TYPE_CHECKING

import gameconfig as GC
import hexgeo

from ..base import ActiveAbility
from ...operations.damage import AttackDamageOperation
from ...components import StatsComponent, OwnerComponent, PositionComponent, UnitComponent
from ....entities.stats import StatType
from ....entities.effect_type import EffectType
from ....entities.active_ability_type import ActiveAbilityType
from ....dsl.base import Const
from ....dsl.effects import ExecutionContext
from ....entities.behaviours import Seq, Foreach, If, AtomicGroup, op_add
from ....entities.selectors import (Cache, Target, Subject, get_spawn_tile_selector, Children,
                                    LastUnitAttackedBy)
from ....entities.formulas import TotalAttacksMade, UnitTurnsStarted
from ....entities.triggers import AmountIsGreaterThanZero, AmountIsEqual, IsAlive, TriggerAnd
from ..behaviours import (Spawn, SpawnSummon, SpawnReplica, PerformAIAttack, AddBondEffect,
                          entities_from_state)

if TYPE_CHECKING:
    from ...state import State

TAUNTED = int(EffectType.Taunted_OnlySpecificTargets)   # 27 — COMPOSITE -> 25/26/1237 ; bond (GetEmRuntz)


def scarab_hive_tree() -> SpawnSummon:
    """Arbre de `ScarabHiveAbility.ExecuteBehaviour @181204cb0` (id 1007, necroSpyder — MIRROR du DECOMPILE) :
        Execute( Spawn(caster@0x160, tileSel, unitId=necroSmnSwarm,
                       SpawnUnitOptions.WithStatsFromConfig(config)
                         .effect       = AddEffect(0x4a3 ScarabHive_OverrideDamageProfile=1187, target@0x178)
                         .onAppearance = UseNormalAttackIfAble(target@0x178)) )
    UN SEUL noeud `Spawn` (plain `Execute`, PAS `ExecuteAtomic`) portant DEUX sous-behaviours EMBARQUES dans
    ses options (+0x10 effet, +0x18 on-appearance) — le count-2, le placement (`First(SortByDistance(CanAddUnit(
    AdjacentTiles(target)), caster), i)`) et `WithStatsFromConfig` vivent DANS `SpawnUnitBehaviour.Execute
    @180fd3d80` (GetUnitToSpawn/GetTileIds/GetStatsToOverride), HORS des DSL-selecteurs (`First`=PickAtIndex=1
    element @180ef02e0 — le count vient des options, pas du selecteur).

    Port = feuille `SpawnSummon` (cf. behaviours.py) qui delegue le SPAWN a l'Operation VALIDEE LIVE-BIT-EXACT
    `SpawnUnitOperation.execute` (2x necroSmnSwarm team/player du caster, stats `ability_var`, tuiles libres
    adjacentes a la cible) puis l'ON-APPEARANCE `UseNormalAttackIfAble(target)` = `_summon_on_appearance_attack`
    (profil override Piercing immediat). L'imperatif `ScarabHiveAbility.execute_behaviour` (spawn + boucle
    on-appearance cables a la main) est REMPLACE par cet arbre. GAP flagge (tache) : l'effet PERSISTANT 0x4a3
    (OverrideDamageProfile pour les attaques des TOURS SUIVANTS) n'est ni materialise ni lu par le pipeline
    d'attaque — l'attaque immediate porte deja le bon profil via `prof`, mais les attaques subsequentes du
    summon utiliseraient son arme Energy au lieu de Piercing. `count=2` = arg `.ctor AActiveAbility` (== l'ancien
    `COUNT`) ; `Target()` = `target@0x178`."""
    return SpawnSummon("ScarabHive", 2, Target())


def scarab_summon_tree() -> SpawnReplica:
    """Arbre de `ScarabSummonAbility.ExecuteBehaviour @181205290` (id 1047, necroSmnSwarm — MIRROR du DECOMPILE) :
        Execute( Spawn(self@0x160, PickRandomly(CanAddUnit(AdjacentTiles(self@0x160)), 1),
                       unitId=GetStringConstant(config,0)=necroSmnSwarm,
                       SpawnUnitOptions.CopyOwner(caster)
                         .onAppearance = PerformAIAttack(1)) )
    UN SEUL noeud `Spawn` (plain `Execute`, PAS `ExecuteAtomic`) portant UN sous-behaviour EMBARQUE (+0x18
    on-appearance) — PAS de +0x10 effet (contrairement a ScarabHive : ScarabSummon n'a pas l'effet persistant
    0x4a3). Le count-1, le placement (`PickRandomly(CanAddUnit(AdjacentTiles(self)))` = 1 tuile LIBRE adjacente
    a SOI) et `CopyOwner` (clone owner+stats du parent) vivent DANS `SpawnUnitBehaviour.Execute @180fd3d80`,
    HORS des DSL-selecteurs.

    Port = feuille `SpawnReplica` (cf. behaviours.py) qui delegue le SPAWN a l'Operation VALIDEE
    `SpawnUnitOperation.execute_self_replica` (`CopyOwner @180fd5ba0` = clone owner+stats du parent, tuiles
    libres adjacentes au caster) puis l'ON-APPEARANCE `PerformAIAttack(1)` = chaque double attaque l'ennemi le
    plus proche (`_nearest_enemy` + `AttackDamageOperation.execute`, approx du choix AI natif). L'imperatif
    `ScarabSummonAbility.execute_behaviour` (spawn + boucle on-appearance cables a la main) est REMPLACE par cet
    arbre. DISTINCT de `scarab_hive_tree` (WithStatsFromConfig summoner-scaled + AddEffect(0x4a3) + attaque de
    la CIBLE ; ici CopyOwner clone-du-parent + attaque AI du double, sans effet). GAP (inchange) : le cap de
    duplication (`UnitDuplicationLimitSelector`) n'est pas porte — recurrence non bornee offline."""
    return SpawnReplica("ScarabSummon", 1)


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
    Taunts (NATIF, prouve RE #200). CONFRONTE LIVE (tracer-v2 DSLFactory #200 : arbre natif capture == ce
    mirror) ; l'imperatif `SpawnUnitOperation.execute_getemruntz` a ete RETIRE (#199)."""
    cache = Cache(get_spawn_tile_selector())                       # @180deb0d0 -- PARTAGE (memoise pre-spawn)
    return Seq(
        AtomicGroup(Spawn(cache, "GetEmRuntz")),                   # ExecuteAtomic(Spawn(cache)) -- inline
        op_add(PerformAIAttack(cache),                             # Execute( op_Addition(
               Foreach(Children(), getemruntz_taunt_tree())))      #   PerformAIAttack(cache), Foreach(Children, Taunt) ))


def _summon_on_appearance_attack(state: "State", summon_id: int, target_id: int,
                                 profile_name):
    """`PerformAIAttack` à l'apparition : le summon attaque la cible. Profil = `unitDamageProfile` de
    l'ability de summon (ex. Piercing) en OVERRIDE de l'arme normale (i2 « immediately attack using
    Piercing ; subsequent attacks use their normal type »). base = stat Attack du summon, hits = arme du
    summon, pipeline normal (reduce-then-roll). No-op si rng non calé (return None)."""
    e = state.get_entity(summon_id)
    sc = e.get_component(StatsComponent) if e is not None else None
    if sc is None:
        return None
    ctx = sc.ctx
    dp = GC.damage_profile(profile_name) or {}
    pierce = max(0, min(100, int(dp.get("PiercingRatio") or 0) + int(ctx.extra_pierce)))
    hits = max(1, int(ctx.normal_weapon_hits))
    return AttackDamageOperation.execute_normal_like(
        state, summon_id, target_id, int(ctx.stat(StatType.ATTACK)), pierce, hits=hits, spread_pct=20,
        damage_profile=profile_name, is_melee=ctx.is_melee)


def _nearest_enemy(state: "State", unit_id: int) -> Optional[int]:
    """Ennemi VIVANT le plus proche (distance hex) de `unit_id` — cible de `PerformAIAttack` (approx du
    choix AI natif). None si pas de position/board ou aucun ennemi. Tie-break `id` (déterministe)."""
    e = state.get_entity(unit_id)
    pc = e.get_component(PositionComponent) if e is not None else None
    oc = e.get_component(OwnerComponent) if e is not None else None
    if pc is None or oc is None:
        return None
    src = (pc.col, pc.row)
    best = None
    best_key = None
    for eid, o in state.entities.items():
        if eid == unit_id:
            continue
        ooc = o.get_component(OwnerComponent)
        ouc = o.get_component(UnitComponent)
        opc = o.get_component(PositionComponent)
        if ooc is None or opc is None or ooc.team == oc.team:      # ennemis uniquement
            continue
        if ouc is not None and not ouc.alive:
            continue
        key = (hexgeo.distance(src, (opc.col, opc.row)), eid)
        if best_key is None or key < best_key:
            best_key, best = key, eid
    return best


class ScarabHiveAbility(ActiveAbility):
    """`ScarabHiveAbility.ExecuteBehaviour` @181204cb0 (id 1007, necroSpyder — le SUMMONER).

    #149 slice-10 : la behaviour EST l'**arbre DSL** `scarab_hive_tree()` (mirror 1:1 du décompilé @181204cb0 :
    un noeud `Spawn` UNIQUE en plain `Execute` portant `WithStatsFromConfig` + AddEffect(0x4a3) + on-appearance
    `UseNormalAttackIfAble` embarqués — cf. la feuille `SpawnSummon`), en remplacement du portage impératif
    (spawn + boucle on-appearance câblés à la main). La feuille délègue le SPAWN à l'Operation VALIDÉE
    LIVE-BIT-EXACT `SpawnUnitOperation.execute` (2× necroSmnSwarm team/player du caster, stats `ability_var`,
    tuiles libres adjacentes à la cible — le count-2/placement/`WithStatsFromConfig` vivent dans
    `SpawnUnitBehaviour`, hors DSL-sélecteurs) puis l'on-appearance `UseNormalAttackIfAble(target)` (profil
    Piercing override immédiat). VALIDÉ live : spawn bit-exact (cf. test_summon_spawn_live, via l'Operation) ;
    wiring message + on-appearance (cf. test_summon_trigger_live, via cette classe -> l'arbre). GAP flaggé
    (tâche) : l'effet PERSISTANT 0x4a3 (OverrideDamageProfile des attaques des TOURS SUIVANTS) non matérialisé/lu.

    ⚠ DISTINCT de `ScarabSummonAbility` @181205290 (id 1047) = l'auto-DÉDOUBLEMENT porté par le scarab
    SPAWNÉ lui-même (spawn adjacent à SOI, stats clonées du parent via CopyOwner, on-appearance
    PerformAIAttack) — encore impératif. Ne PAS confondre les deux (même unitId necroSmnSwarm, mais
    summoner-scaled vs clone-du-parent)."""
    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.ScarabHive)  # 1007

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        if target_id is None:
            return None
        # behaviour = arbre DSL (feuille SpawnSummon) : émet les MÊMES Operations que l'impératif
        # (`SpawnUnitOperation.execute` + `_summon_on_appearance_attack`) -> même mutation, même diag.
        ectx = ExecutionContext(state=state, rng=state.rng)
        scarab_hive_tree().execute(entities_from_state(state, caster_id, target_id), ectx)
        spawned = [p["unit"] for n, p in ectx.emitted if n == "SpawnUnit"]
        attacks = [{"summon": p["summon"], "total": p["total"]}
                   for n, p in ectx.emitted if n == "SummonOnAppearance"]
        visual_id = ((GC.ability("ScarabHive") or {}).get("constants") or {}).get("unitId")
        return {"summon": visual_id, "spawned": spawned, "attacks": attacks, "dsl": True}


class ScarabSummonAbility(ActiveAbility):
    """`ScarabSummonAbility.ExecuteBehaviour @181205290` (id 1047, necroSmnSwarm — auto-DÉDOUBLEMENT).

    #149 slice-11 : la behaviour EST l'**arbre DSL** `scarab_summon_tree()` (mirror 1:1 du décompilé @181205290 :
    un noeud `Spawn` UNIQUE en plain `Execute` portant `SpawnUnitOptions.CopyOwner(caster)` + un seul
    sous-behaviour embarqué `+0x18 = PerformAIAttack(1)` on-appearance — cf. la feuille `SpawnReplica`), en
    remplacement du portage impératif (spawn + boucle on-appearance câblés à la main). La feuille délègue le
    SPAWN à l'Operation VALIDÉE `SpawnUnitOperation.execute_self_replica` (`CopyOwner @180fd5ba0` = clone
    owner+stats du parent, count-1, tuiles libres adjacentes à SOI) puis l'on-appearance `PerformAIAttack(1)`
    (chaque double attaque l'ennemi le plus proche — approx du choix AI natif ; cible AI-exacte = raffinement).

    Chance gameconfig = 50 ; playbook `ScarabSummonPlaybook`. ⚠ DISTINCT de `ScarabHiveAbility` @181204cb0 (id
    1007, necroSpyder) = spawn summoner-scaled `WithStatsFromConfig` + AddEffect(0x4a3) + attaque de la CIBLE ;
    ici clone-du-parent `CopyOwner` + attaque AI du double, sans effet. GAP (inchangé) : cap de duplication
    (`UnitDuplicationLimitSelector`/`LimitUnitDuplications`) non porté (récurrence non bornée offline)."""
    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.ScarabSummon)  # 1047

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        # behaviour = arbre DSL (feuille SpawnReplica) : émet les MÊMES Operations que l'impératif
        # (`SpawnUnitOperation.execute_self_replica` + `AttackDamageOperation.execute`) -> même mutation, même diag.
        ectx = ExecutionContext(state=state, rng=state.rng)
        scarab_summon_tree().execute(entities_from_state(state, caster_id, target_id), ectx)
        spawned = [p["unit"] for n, p in ectx.emitted if n == "SpawnUnit"]
        attacks = [{"summon": p["summon"], "target": p["target"], "total": p["total"]}
                   for n, p in ectx.emitted if n == "ReplicaOnAppearance"]
        visual_id = ((GC.ability("ScarabSummon") or {}).get("constants") or {}).get("unitId")
        return {"summon": visual_id, "spawned": spawned, "attacks": attacks, "replica": True, "dsl": True}


class GetEmRuntzAbility(ActiveAbility):
    """`GetEmRuntzAbility.ExecuteBehaviour @1811e2210` (id 1045, orksRuntherd/Snotflogga). Spawn UN grot par
    hex LIBRE adjacent au caster **ET** adjacent à un ennemi, chaque grot attaque à l'apparition
    (`PerformAIAttackFromCurrentPosition`) puis Taunte l'ennemi frappé (`TauntWithNewChildrenWhoDidDamage`).

    #149 slice-2b : la behaviour EST l'**arbre DSL** `getemruntz_tree()` (mirror 1:1 du décompilé
    @1811e2210 : `ExecuteAtomic(Spawn) ; Execute(PerformAIAttack + Foreach(Children, Taunt))`), en
    remplacement du portage impératif (spawn + on-appearance + Taunt câblés à la main). **PROUVÉ bit-exact**
    (replay-diff DSL == impératif) puis **CONFRONTÉ LIVE** (tracer-v2 DSLFactory #200 : arbre natif capturé
    == ce mirror, cf. docs/rl/dsl-effect-nodes.md). L'impératif `SpawnUnitOperation.execute_getemruntz` a été
    **RETIRÉ** (#199) — la behaviour est le seul arbre DSL."""
    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.GetEmRuntz)  # 1045

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        # behaviour = arbre DSL (couche effet-nœuds) ; les feuilles émettent les MÊMES Operations que
        # l'impératif (`AttackDamageOperation`/`AddEffectOperation`/`_spawn_config_grot`) -> même mutation.
        ectx = ExecutionContext(state=state, rng=state.rng)
        getemruntz_tree().execute(entities_from_state(state, caster_id), ectx)
        # diag depuis les émissions de l'arbre (mêmes champs que l'ancien retour impératif)
        spawned = [p["unit"] for n, p in ectx.emitted if n == "SpawnUnit"]
        attacks = next((p["attacks"] for n, p in ectx.emitted if n == "PerformAIAttack"), [])
        taunted = [p["target"] for n, p in ectx.emitted if n == "AddBondEffect"]
        return {"summon": "orksGrot", "spawned": spawned, "attacks": attacks, "taunted": taunted,
                "getemruntz": True, "dsl": True}
