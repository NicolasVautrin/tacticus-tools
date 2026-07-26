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
from ....dsl.effects import ExecutionContext, AbilityBehaviour, OperationResult
from ....entities.behaviours import Seq, Foreach, If, AtomicGroup, op_add
from ....entities.selectors import (Cache, Target, Subject, get_spawn_tile_selector, Children,
                                    LastUnitAttackedBy, Caster)
from ....entities.formulas import TotalAttacksMade, UnitTurnsStarted
from ....entities.triggers import AmountIsGreaterThanZero, AmountIsEqual, IsAlive, TriggerAnd
from ..behaviours import (Spawn, SpawnSummon, SpawnReplica, PerformAIAttack, AddBondEffect,
                          AddEffect, entities_from_state)

if TYPE_CHECKING:
    from ...state import State

TAUNTED = int(EffectType.Taunted_OnlySpecificTargets)   # 27 — COMPOSITE -> 25/26/1237 ; bond (GetEmRuntz)


def scarab_hive_tree() -> SpawnSummon:
    """Arbre de `IdunBattleLogic.Entities.Abilities.Active.Loki.ScarabHiveAbility$$ExecuteBehaviour` (id 1007, necroSpyder — MIRROR du DECOMPILE) :
        Execute( Spawn(caster@0x160, tileSel, unitId=necroSmnSwarm,
                       SpawnUnitOptions.WithStatsFromConfig(config)
                         .effect       = AddEffect(0x4a3 ScarabHive_OverrideDamageProfile=1187, target@0x178)
                         .onAppearance = UseNormalAttackIfAble(target@0x178)) )
    UN SEUL noeud `Spawn` (plain `Execute`, PAS `ExecuteAtomic`) portant DEUX sous-behaviours EMBARQUES dans
    ses options (+0x10 effet, +0x18 on-appearance) — le count-2, le placement (`First(SortByDistance(CanAddUnit(
    AdjacentTiles(target)), caster), i)`) et `WithStatsFromConfig` vivent DANS `IdunBattle.Entities.Behaviours.SpawnUnitBehaviour$$Execute` (GetUnitToSpawn/GetTileIds/GetStatsToOverride), HORS des DSL-selecteurs (`First`=PickAtIndex=1
    element IdunBattle.Entities.Selectors.PickAtIndexSelector$$Select — le count vient des options, pas du selecteur).

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
    """Arbre de `IdunBattleLogic.Entities.Abilities.Active.Loki.ScarabSummonAbility$$ExecuteBehaviour` (id 1047, necroSmnSwarm — MIRROR du DECOMPILE) :
        Execute( Spawn(self@0x160, PickRandomly(CanAddUnit(AdjacentTiles(self@0x160)), 1),
                       unitId=GetStringConstant(config,0)=necroSmnSwarm,
                       SpawnUnitOptions.CopyOwner(caster)
                         .onAppearance = PerformAIAttack(1)) )
    UN SEUL noeud `Spawn` (plain `Execute`, PAS `ExecuteAtomic`) portant UN sous-behaviour EMBARQUE (+0x18
    on-appearance) — PAS de +0x10 effet (contrairement a ScarabHive : ScarabSummon n'a pas l'effet persistant
    0x4a3). Le count-1, le placement (`PickRandomly(CanAddUnit(AdjacentTiles(self)))` = 1 tuile LIBRE adjacente
    a SOI) et `CopyOwner` (clone owner+stats du parent) vivent DANS `IdunBattle.Entities.Behaviours.SpawnUnitBehaviour$$Execute`,
    HORS des DSL-selecteurs.

    Port = feuille `SpawnReplica` (cf. behaviours.py) qui delegue le SPAWN a l'Operation VALIDEE
    `SpawnUnitOperation.execute_self_replica` (`IdunBattle.Entities.Behaviours.SpawnUnitOptions$$CopyOwner` = clone owner+stats du parent, tuiles
    libres adjacentes au caster) puis l'ON-APPEARANCE `PerformAIAttack(1)` = chaque double attaque l'ennemi le
    plus proche (`_nearest_enemy` + `AttackDamageOperation.execute`, approx du choix AI natif). L'imperatif
    `ScarabSummonAbility.execute_behaviour` (spawn + boucle on-appearance cables a la main) est REMPLACE par cet
    arbre. DISTINCT de `scarab_hive_tree` (WithStatsFromConfig summoner-scaled + AddEffect(0x4a3) + attaque de
    la CIBLE ; ici CopyOwner clone-du-parent + attaque AI du double, sans effet). GAP (inchange) : le cap de
    duplication (`UnitDuplicationLimitSelector`) n'est pas porte — recurrence non bornee offline."""
    return SpawnReplica("ScarabSummon", 1)


def getemruntz_taunt_tree() -> If:
    """Corps `Func<entities,behaviour>` de `IdunBattleLogic.Entities.Abilities.Active.Loki.GetEmRuntzAbility$$TauntWithNewChildrenWhoDidDamage` (DECOMPILE) pour
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
    # duree = `TurnsFromRounds(1)` natif -> convertie par `IdunBattle.Core.Services.BattleQuery$$ConvertRoundsToTurns (#98)
    return If(cond, AddBondEffect(TAUNTED, "Taunted_OnlySpecificTargets",
                                  child, LastUnitAttackedBy(child), duration_rounds=1))


def getemruntz_tree() -> Seq:
    """Arbre COMPLET de `IdunBattleLogic.Entities.Abilities.Active.Loki.GetEmRuntzAbility$$ExecuteBehaviour` (id 1045, MIRROR 1:1 du DECOMPILE) :
        cache = Cache(IdunBattleLogic.Entities.Abilities.Active.Loki.GetEmRuntzAbility$$GetSpawnTileSelector)             # IdunBattleLogic.Entities.DSLFactory$$Cache -- PARTAGE Spawn/Attack (memoise)
        ExecuteAtomic( Spawn(cache) )                             # IdunBattle.Entities.Abilities.AActiveAbility$$ExecuteAtomic inline -> grots materialises
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
    cache = Cache(get_spawn_tile_selector())                       # IdunBattleLogic.Entities.DSLFactory$$Cache -- PARTAGE (memoise pre-spawn)
    return Seq(
        AtomicGroup(Spawn(cache, "GetEmRuntz")),                   # ExecuteAtomic(Spawn(cache)) -- inline
        op_add(PerformAIAttack(cache),                             # Execute( op_Addition(
               Foreach(Children(), getemruntz_taunt_tree())))      #   PerformAIAttack(cache), Foreach(Children, Taunt) ))


def _summon_on_appearance_attack(state: "State", summon_id: int, target_id: int,
                                 profile_name):
    """`UseNormalAttackIfAble(Spawned, Target)` à l'apparition : le summon attaque la cible avec son
    attaque NORMALE. `profile_name` = OVERRIDE optionnel du profil (ex. ScarabHive `unitDamageProfile`
    = Piercing, i2 « immediately attack using Piercing ; subsequent attacks use their normal type »).
    `profile_name is None` (aucun override, ex. DeathFromAbove) -> FALLBACK sur le profil de l'arme
    NORMALE du summon (`ctx.normal_profile` + son PiercingRatio) : `UseNormalAttackIfAble` = attaque
    normale, l'override n'est PAS obligatoire (ScarabHive passe "Piercing" -> branche inchangee, aucune
    regression). base = stat Attack du summon, hits = arme du summon, pipeline normal (reduce-then-roll).
    No-op si rng non calé (return None)."""
    e = state.get_entity(summon_id)
    sc = e.get_component(StatsComponent) if e is not None else None
    if sc is None:
        return None
    ctx = sc.ctx
    prof = profile_name if profile_name is not None else getattr(ctx, "normal_profile", None)
    dp = GC.damage_profile(prof) or {}
    pierce = max(0, min(100, int(dp.get("PiercingRatio") or 0) + int(ctx.extra_pierce)))
    hits = max(1, int(ctx.normal_weapon_hits))
    return AttackDamageOperation.execute_normal_like(
        state, summon_id, target_id, int(ctx.stat(StatType.ATTACK)), pierce, hits=hits, spread_pct=20,
        damage_profile=prof, is_melee=ctx.is_melee)


def perform_ai_attack_from_current_position(state: "State", unit_id: int) -> Optional[dict]:
    """**L'UNIQUE port du noeud natif `IdunBattleLogic.Entities.DSLFactory$$PerformAIAttackFromCurrentPosition`**
    (un acteur). Tous ses call-sites passent par ici : la feuille DSL `PerformAIAttack` (domaine TUILE ou
    UNITE, cf. `../behaviours/summon.py`), les on-appearance embarques dans `SpawnUnitOptions+0x18`
    (MasterOfTheTutelaries/AberrantHypermorph/AlphaWarrior/IronkinSteeljack/Screamer) et la free-attack
    de `IdunBattleLogic.Entities.Abilities.Active.Loki.TheQuickeningAbility$$GetTriggerAttackBehaviour`.

    STRUCTURE NATIVE (decompile) — le noeud n'est qu'un CONSTRUCTEUR :
      `PerformAIAttackFromCurrentPosition(unit, utilityEntity, customUtility, skipAtomicCheck)` alloue un
      `IdunBattle.Entities.Behaviours.PerformAIAbilityUnitBehaviour` dont les champs sont
        `+0x50` = `unit`            (le selecteur d'ACTEURS, itere par `Execute`) ;
        `+0x68` = le `Func<IEntity,int>` CACHE du `<>c` de `DSLFactory` (= resolveur de l'ability
                  d'ATTAQUE de l'acteur ; c'est le SEUL point qui distingue ce noeud de
                  `IdunBattleLogic.Entities.DSLFactory$$PerformAIAbility`, ou le Func est fourni) ;
        `+0x70` = 0 ; `+0x71` = `skipAtomicCheck` ;
        `+0x78` = **`factory+0xb8` = `Direct(0)`** -> l'option `Nullable<int>` de l'appel IA vaut **0** :
                  c'est LITTERALEMENT le « FromCurrentPosition » (budget de deplacement nul). Le noeud
                  cousin `IdunBattleLogic.Entities.DSLFactory$$PerformAIAttack` est le MEME behaviour avec
                  ce noeud d'amount FOURNI PAR L'APPELANT (ex. `PerformAIAttack(..., 1, ...)` de
                  ForwardSpotter / `PerformAIAttack(1)` de ScarabSummon) ;
        `+0x80` = `utilityEntity`, `+0x90` = `customUtility` (surcharges d'UTILITE du choix de cible) ;
        `+0x88` = 0 -> `IdunBattle.Entities.Behaviours.PerformAIAbilityUnitBehaviour$$Execute` prend la
                  branche « pas de cible imposee » (appel IA slot 0x37, options `{_, skipAtomic, true,
                  Nullable(0), customUtility}`) : **c'est l'IA qui CHOISIT la cible**, aucune contrainte
                  d'adjacence n'est cablee dans le noeud.

    CE QUI EN DECOULE, ET QUI EST LE MEME POUR TOUS LES APPELANTS :
      * **attaque NORMALE COMPLETE** via `AttackDamageOperation.execute` (selection d'arme par distance ->
        le Horror tire son ranged r2 PSYCHIC si non-adjacent, melee Physical si adjacent ; auras
        InfernalPacts/WeaverOfFate incluses) ;
      * **dispatch after-hit INCONDITIONNEL** : l'IA execute une VRAIE ability d'attaque, donc
        `IdunBattle.Operations.FinishAttackOperation$$Execute` emet `On(0x26)`/`On(8)`/`On(9)` comme sur
        n'importe quelle attaque normale. AUCUN champ du noeud ne le gate. MESURE live (diag 202c) : le
        bonus InfernalPacts PSYCHIC (summon Daemon adjacent a Abraxas) met Psychic dans le SET de profils
        -> CHAQUE attaque de summon adjacent a Abraxas re-declenche un Screamer (trigger 1173 sur `On(9)`).
        C'est la PREUVE live que le vecteur after-hit part depuis ce noeud ;
      * **domaine de cible = CONTEXTE, jamais un choix du port** : la portee utilisable est celle de
        `IdunBattle.Core.Services.TargetingQuery$$GetRange`, qui clampe `Math.Min(1, range)` si l'acteur
        porte `ForcedInMelee (0x529)`. La free-attack de TheQuickening pose cet effet AVANT d'appeler ce
        noeud -> son domaine se REDUIT tout seul a l'adjacence, sans variante de code (`_in_attack_range`
        porte le clamp, cf. `operations/triggers/base.py::_forced_in_melee`).

    RESIDU (commun a tous les appelants) : le choix de cible est approxime par `_nearest_enemy` (le moteur
    d'utilite IA natif n'est pas mirrore) ; gate « if able » = `_in_attack_range` (mirror `GetRange`).
    None si pas de cible legale (l'acteur n'attaque pas — fidele : l'IA ne produit aucune action).
    TheQuickening passe en plus un `customUtility` (lambda du display-class de l'ability) qui ne peut que
    reordonner des cibles EQUIVALENTES en portee — non mirrore, meme classe de residu."""
    from ...operations.triggers.base import _in_attack_range
    tgt = _nearest_enemy(state, unit_id)
    if tgt is None or not _in_attack_range(state, unit_id, tgt):
        return None
    r = AttackDamageOperation.execute(state, unit_id, tgt)
    if r is None:
        return None
    # L'attaque du summon est une attaque NORMALE COMPLETE cote natif (FinishAttackOperation emet
    # On(0x26)/On(8)/On(9)) -> dispatcher le vecteur after-attack comme le handler de message
    # (damage.py visit_AttackUnitMessage / summon_ai.py). C'est CE On(9) qui porte la cascade :
    # Horror ranged Psychic -> trigger 1173 -> Screamer (borne : Screamer melee Power ne re-fire pas).
    from ...operations.triggers import after_hit_normal_attack
    profs = {r.get("profile")} - {None}
    profs |= set((r.get("additional_hits") or {}).get("profiles") or [])
    after = after_hit_normal_attack(state, unit_id, tgt, bool(r.get("ranged")),
                                    r.get("profile"), is_crit=bool(r.get("did_crit")),
                                    profiles=profs, did_block=bool(r.get("did_block")))
    return {"summon": unit_id, "target": tgt, "total": r.get("total"), "after_hit": after}


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
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.ScarabHiveAbility$$ExecuteBehaviour (id 1007, necroSpyder — le SUMMONER).

    #149 slice-10 : la behaviour EST l'**arbre DSL** `scarab_hive_tree()` (mirror 1:1 du décompilé IdunBattleLogic.Entities.Abilities.Active.Loki.ScarabHiveAbility$$ExecuteBehaviour :
    un noeud `Spawn` UNIQUE en plain `Execute` portant `WithStatsFromConfig` + AddEffect(0x4a3) + on-appearance
    `UseNormalAttackIfAble` embarqués — cf. la feuille `SpawnSummon`), en remplacement du portage impératif
    (spawn + boucle on-appearance câblés à la main). La feuille délègue le SPAWN à l'Operation VALIDÉE
    LIVE-BIT-EXACT `SpawnUnitOperation.execute` (2× necroSmnSwarm team/player du caster, stats `ability_var`,
    tuiles libres adjacentes à la cible — le count-2/placement/`WithStatsFromConfig` vivent dans
    `SpawnUnitBehaviour`, hors DSL-sélecteurs) puis l'on-appearance `UseNormalAttackIfAble(target)` (profil
    Piercing override immédiat). VALIDÉ live : spawn bit-exact (cf. test_summon_spawn_live, via l'Operation) ;
    wiring message + on-appearance (cf. test_summon_trigger_live, via cette classe -> l'arbre). GAP flaggé
    (tâche) : l'effet PERSISTANT 0x4a3 (OverrideDamageProfile des attaques des TOURS SUIVANTS) non matérialisé/lu.

    ⚠ DISTINCT de `ScarabSummonAbility` IdunBattleLogic.Entities.Abilities.Active.Loki.ScarabSummonAbility$$ExecuteBehaviour (id 1047) = l'auto-DÉDOUBLEMENT porté par le scarab
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
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.ScarabSummonAbility$$ExecuteBehaviour` (id 1047, necroSmnSwarm — auto-DÉDOUBLEMENT).

    #149 slice-11 : la behaviour EST l'**arbre DSL** `scarab_summon_tree()` (mirror 1:1 du décompilé IdunBattleLogic.Entities.Abilities.Active.Loki.ScarabSummonAbility$$ExecuteBehaviour :
    un noeud `Spawn` UNIQUE en plain `Execute` portant `SpawnUnitOptions.CopyOwner(caster)` + un seul
    sous-behaviour embarqué `+0x18 = PerformAIAttack(1)` on-appearance — cf. la feuille `SpawnReplica`), en
    remplacement du portage impératif (spawn + boucle on-appearance câblés à la main). La feuille délègue le
    SPAWN à l'Operation VALIDÉE `SpawnUnitOperation.execute_self_replica` (`IdunBattle.Entities.Behaviours.SpawnUnitOptions$$CopyOwner` = clone
    owner+stats du parent, count-1, tuiles libres adjacentes à SOI) puis l'on-appearance `PerformAIAttack(1)`
    (chaque double attaque l'ennemi le plus proche — approx du choix AI natif ; cible AI-exacte = raffinement).

    Chance gameconfig = 50 ; playbook `ScarabSummonPlaybook`. ⚠ DISTINCT de `ScarabHiveAbility` IdunBattleLogic.Entities.Abilities.Active.Loki.ScarabHiveAbility$$ExecuteBehaviour (id
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
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.GetEmRuntzAbility$$ExecuteBehaviour` (id 1045, orksRuntherd/Snotflogga). Spawn UN grot par
    hex LIBRE adjacent au caster **ET** adjacent à un ennemi, chaque grot attaque à l'apparition
    (`PerformAIAttackFromCurrentPosition`) puis Taunte l'ennemi frappé (`TauntWithNewChildrenWhoDidDamage`).

    #149 slice-2b : la behaviour EST l'**arbre DSL** `getemruntz_tree()` (mirror 1:1 du décompilé
    IdunBattleLogic.Entities.Abilities.Active.Loki.GetEmRuntzAbility$$ExecuteBehaviour : `ExecuteAtomic(Spawn) ; Execute(PerformAIAttack + Foreach(Children, Taunt))`), en
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


MASTER_EFFECT = int(EffectType.MasterOfTheTutelaries)   # 1197 (0x4ad) — marqueur until-EoT (arme 1173)


class SpawnTutelaryHorror(AbilityBehaviour):
    """Feuille `Spawn` du volet Pink Horror de `IdunBattleLogic.Entities.Abilities.Active.Loki.MasterOfTheTutelariesAbility$$ExecuteBehaviour` :
        Spawn( caster@0x160, TARGET@0x178 = la TUILE ciblée par le cast (hex libre adjacent),
               unitId = GetStringConstant(config, 0) = "thousSmnPinkHorror",
               SpawnUnitOptions.WithStatsFromConfig(config 1096,
                                                    AbilityLevelAmount(Self@0x148, AbilityType(1096)))
                 .onAppearance(+0x18) = PerformAIAttackFromCurrentPosition(Spawned@0x180) )
    Le placement N'EST PAS un sélecteur ici : la tuile EST la cible du cast (choisie par le joueur/l'IA,
    légalité = abilityTargets kind="tile") → la feuille porte `tile_id` résolu par la classe d'ability.
    Spawn délégué à `_spawn_config_grot` (WithStatsFromConfig = summonHp/summonDmg[level actif du caster],
    CopyOwner team+player) puis on-appearance `perform_ai_attack_from_current_position` (pipeline attaque
    normale COMPLET, arme par distance → ranged r2 PSYCHIC si non-adjacent, melee Physical+bonus
    InfernalPacts Psychic si adjacent → déclenche le Screamer dans les DEUX cas, l'effet 1197 étant
    posé AVANT ce Spawn dans l'arbre). Émet 'SpawnUnit'/'SummonOnAppearance'."""
    __slots__ = ("tile_id",)

    def __init__(self, tile_id):
        self.tile_id = tile_id

    def execute(self, entities, ectx):
        from ...operations.spawn import _spawn_config_grot
        state = ectx.state
        caster_id = (entities.caster or {}).get("id")
        if state is None or caster_id is None or self.tile_id is None:
            return OperationResult.ok()
        consts = (GC.ability("MasterOfTheTutelaries") or {}).get("constants") or {}
        vid = consts.get("unitId")                       # thousSmnPinkHorror (GetStringConstant(config, 0))
        ce = state.get_entity(caster_id)
        coc = ce.get_component(OwnerComponent) if ce is not None else None
        csc = ce.get_component(StatsComponent) if ce is not None else None
        c_ctx = csc.ctx if csc is not None else None
        if vid is None or coc is None or c_ctx is None:
            return OperationResult.ok()
        level = getattr(c_ctx, "active_ability_level", None)   # AbilityLevelAmount(Self, 1096)
        mult = int(getattr(c_ctx, "ability_variables_multiplier", 100) or 100)
        gid = _spawn_config_grot(state, vid, self.tile_id, "MasterOfTheTutelaries", level, mult,
                                 coc.team, coc.player)
        if gid is None:
            return OperationResult.ok()
        ectx.emit("SpawnUnit", unit=gid)
        att = perform_ai_attack_from_current_position(state, gid)
        if att is not None:
            ectx.emit("SummonOnAppearance", summon=gid, target=att["target"], total=att["total"])
        return OperationResult.ok()


def master_of_the_tutelaries_tree(tile_id) -> Seq:
    """Arbre de `IdunBattleLogic.Entities.Abilities.Active.Loki.MasterOfTheTutelariesAbility$$ExecuteBehaviour` (id 1096, thousInfernalMaster
    Abraxas — MIRROR 1:1 du DÉCOMPILÉ) :
        op_BitwiseAnd( AddEffect(0x4ad=1197, AbilityStateReference, caster@0x160, caster@0x160,
                                 durée @dsl+0xc0),
                       Spawn(caster@0x160, Target@0x178=TUILE, "thousSmnPinkHorror",
                             WithStatsFromConfig(config, AbilityLevelAmount(Self@0x148, 1096))
                               .onAppearance = PerformAIAttackFromCurrentPosition) )
    ORDRE NATIF : AddEffect PUIS Spawn (op_BitwiseAnd gauche→droite, les deux exécutent) — l'effet 1197
    est ACTIF avant l'attaque immédiate du Horror → son attaque déclenche DÉJÀ un Screamer (ranged
    Psychic OU melee+bonus InfernalPacts Psychic — mesure live diag 202c ; la chaîne se poursuit tant
    que chaque summon adjacent à Abraxas attaque). Port : `Seq(AddEffect, SpawnTutelaryHorror)`.
    Durée : nœud `@dsl+0xc0` = **`Direct(1)`** (#98 — le singleton constant alloué par
    `DSLFactory..IdunBattleLogic.Entities.DSLFactory$$.ctor` ; MÊME nœud que le `duree@0xc0` de Waaagh IdunBattleLogic.Entities.Abilities.Active.Loki.WaaaghAbility$$GetBuffBehaviour et que le
    `amount = df@0xc0 = Const(1)` d'AddEffectOrIncreaseLevel). Ce n'est donc PAS un `TurnsFromRounds`
    (résidu « non résolu » FERMÉ) : la valeur arrive telle quelle dans le `param_6` d'`AddEffect
    IdunBattle.Operations.AddEffectOperation$$Execute`, qui ne la convertit pas → **1 TOUR** (`duration_turns=1`,
    comportement inchangé)."""
    return Seq(AddEffect(MASTER_EFFECT, "MasterOfTheTutelaries", Caster(), duration_turns=1),
               SpawnTutelaryHorror(tile_id))


class MasterOfTheTutelariesAbility(ActiveAbility):
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.MasterOfTheTutelariesAbility$$ExecuteBehaviour` (id 1096, Abraxas thousInfernalMaster —
    #202-C). Cast TILE-TARGET (« Summon a Pink Horror on a free hex adjacent to Abraxas ») :
    pose l'effet-marqueur 1197 sur SOI (arme la triggered 1173 = Screamer sur attaque Psychic vs ennemi,
    cf. `EFFECT_TRIGGERS[1197]` + `MasterOfTheTutelariesEffect`) PUIS spawn le Pink Horror sur la tuile
    ciblée, qui attaque immédiatement sans bouger (`PerformAIAttackFromCurrentPosition`).

    `target_id` = id de TUILE (cast tile-target, abilityTargets kind="tile" — même convention que la
    cible d'une self-cast AoE, cf. NCContext.tile_id_by_pos). Un target_id qui n'est pas une tuile du
    board → Spawn no-op (le AddEffect s'exécute quand même : ordre d'arbre préservé, diag `spawned=[]`).
    IdunBattleLogic.Entities.Abilities.Active.Loki.MasterOfTheTutelariesAbility$$.ctor : `TargetingOptions(0, statsFromClass, 1, 0x1040)` + `AActiveAbility(…, 2)`."""
    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.MasterOfTheTutelaries)  # 1096

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        board = state.board
        tile_id = target_id if (board is not None and target_id in board.by_id) else None
        ectx = ExecutionContext(state=state, rng=state.rng)
        master_of_the_tutelaries_tree(tile_id).execute(entities_from_state(state, caster_id), ectx)
        spawned = [p["unit"] for n, p in ectx.emitted if n == "SpawnUnit"]
        attacks = [{"summon": p["summon"], "target": p["target"], "total": p["total"]}
                   for n, p in ectx.emitted if n == "SummonOnAppearance"]
        effect = next((True for n, _p in ectx.emitted if n == "AddEffect"), False)
        return {"summon": "thousSmnPinkHorror", "spawned": spawned, "attacks": attacks,
                "effect_1197": effect, "tile": tile_id, "dsl": True}


class SpawnAberrant(AbilityBehaviour):
    """Feuille `Spawn` de `IdunBattleLogic.Entities.Abilities.Active.Loki.AberrantHypermorphAbility$$ExecuteBehaviour` (id 1166, genesBiophagus) :
        Spawn( caster@0x160, TARGET@0x178 = la TUILE ciblee par le cast (hex libre adjacent au caster),
               unitId = GetStringConstant(config, 0) = "genesSmnAberrant",
               SpawnUnitOptions.WithStatsFromConfig(config 1166,
                                                    AbilityLevelAmount(Self@0x148, AbilityType(1166)))
                 .onAppearance(+0x18) = PerformAIAttackFromCurrentPosition(Target@0x178) )
    Mirror 1:1 de `SpawnTutelaryHorror` (IdunBattleLogic.Entities.Abilities.Active.Loki.MasterOfTheTutelariesAbility$$ExecuteBehaviour volet Spawn) SANS le AddEffect(1197) et avec la config
    1166. Le placement N'EST PAS un selecteur : la tuile EST la cible du cast (choisie par le joueur/l'IA,
    legalite = abilityTargets kind="tile", hex libre adjacent au caster via TargetingOptions 0x1040 --
    ctor IDENTIQUE a MasterOfTheTutelaries IdunBattleLogic.Entities.Abilities.Active.Loki.AberrantHypermorphAbility$$.ctor) -> la feuille porte `tile_id` resolu par la classe.
    Spawn delegue a `_spawn_config_grot` (WithStatsFromConfig = summonHp/summonDmg/summonArmor[level actif
    du caster] x mult, CopyOwner team+player du caster).

    ON-APPEARANCE : le natif passe `Target@0x178` (le MEME selecteur que la tuile de spawn) comme SUJET de
    `PerformAIAttackFromCurrentPosition`, la ou MasterOfTheTutelaries passe `Spawned@0x180` -- les DEUX
    resolvent au MEME summon (Target@0x178 apres le spawn = l'unite POSEE sur la tuile-cible = le summon
    fraichement cree, la tuile etant libre AVANT le spawn par la legalite du cast). Outcome identique ->
    port = `perform_ai_attack_from_current_position(state, gid)` (pipeline attaque normale COMPLET, arme par
    distance : le genesSmnAberrant n'a qu'une arme melee 1-hit Physical -> attaque l'ennemi le plus proche
    s'il est A PORTEE melee, sinon no-op fidele). Emet 'SpawnUnit'/'SummonOnAppearance'. Effet PUR."""
    __slots__ = ("tile_id",)

    def __init__(self, tile_id):
        self.tile_id = tile_id

    def execute(self, entities, ectx):
        from ...operations.spawn import _spawn_config_grot
        state = ectx.state
        caster_id = (entities.caster or {}).get("id")
        if state is None or caster_id is None or self.tile_id is None:
            return OperationResult.ok()
        consts = (GC.ability("AberrantHypermorph") or {}).get("constants") or {}
        vid = consts.get("unitId")                       # genesSmnAberrant (GetStringConstant(config, 0))
        ce = state.get_entity(caster_id)
        coc = ce.get_component(OwnerComponent) if ce is not None else None
        csc = ce.get_component(StatsComponent) if ce is not None else None
        c_ctx = csc.ctx if csc is not None else None
        if vid is None or coc is None or c_ctx is None:
            return OperationResult.ok()
        level = getattr(c_ctx, "active_ability_level", None)   # AbilityLevelAmount(Self, 1166)
        mult = int(getattr(c_ctx, "ability_variables_multiplier", 100) or 100)
        gid = _spawn_config_grot(state, vid, self.tile_id, "AberrantHypermorph", level, mult,
                                 coc.team, coc.player)
        if gid is None:
            return OperationResult.ok()
        ectx.emit("SpawnUnit", unit=gid)
        att = perform_ai_attack_from_current_position(state, gid)
        if att is not None:
            ectx.emit("SummonOnAppearance", summon=gid, target=att["target"], total=att["total"])
        return OperationResult.ok()


def aberrant_hypermorph_tree(tile_id) -> SpawnAberrant:
    """Arbre de `IdunBattleLogic.Entities.Abilities.Active.Loki.AberrantHypermorphAbility$$ExecuteBehaviour` (id 1166, genesBiophagus -- MIRROR
    1:1 du DECOMPILE) :
        Execute( Spawn(caster@0x160, Target@0x178=TUILE, "genesSmnAberrant",
                       WithStatsFromConfig(config, AbilityLevelAmount(Self@0x148, 1166))
                         .onAppearance = PerformAIAttackFromCurrentPosition(Target@0x178)) )
    UN SEUL noeud `Spawn` (plain `AActiveAbility.Execute`, PAS `ExecuteAtomic`, PAS d'AddEffect, PAS de
    op_BitwiseAnd -- le noeud top-level passe a Execute EST le Spawn seul). Count=1 (une seule tuile-cible).
    DISTINCT de MasterOfTheTutelaries IdunBattleLogic.Entities.Abilities.Active.Loki.MasterOfTheTutelariesAbility$$ExecuteBehaviour (op_BitwiseAnd(AddEffect(1197), Spawn) + onAppearance
    Spawned@0x180) : ici PAS d'effet-marqueur et l'onAppearance = Target@0x178 (resout au meme summon).
    Port : feuille `SpawnAberrant` (mirror de `SpawnTutelaryHorror` sans le AddEffect)."""
    return SpawnAberrant(tile_id)


class AberrantHypermorphAbility(ActiveAbility):
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.AberrantHypermorphAbility$$ExecuteBehaviour` (id 1166, genesBiophagus -- le summon le plus
    simple). Cast TILE-TARGET (« Summon a genesSmnAberrant on a free hex adjacent to Biophagus ») : spawn UN
    Aberrant Hypermorph sur la tuile ciblee (hex libre adjacent au caster), qui attaque immediatement sans
    bouger (`PerformAIAttackFromCurrentPosition`). Pas de triggered, pas d'effet pose sur le caster.

    La behaviour EST l'arbre DSL `aberrant_hypermorph_tree(tile_id)` (mirror 1:1 du decompile IdunBattleLogic.Entities.Abilities.Active.Loki.AberrantHypermorphAbility$$ExecuteBehaviour :
    un noeud `Spawn` UNIQUE portant `WithStatsFromConfig` + on-appearance `PerformAIAttackFromCurrentPosition`
    embarque dans ses options -- cf. la feuille `SpawnAberrant`). La feuille delegue le SPAWN a l'Operation
    VALIDEE `_spawn_config_grot` (genesSmnAberrant team/player du caster, stats summonHp/summonDmg/summonArmor
    [level actif] x mult) puis l'on-appearance (le summon attaque l'ennemi le plus proche a portee melee).

    `target_id` = id de TUILE (cast tile-target, abilityTargets kind="tile" -- meme convention que
    MasterOfTheTutelaries : IdunBattleLogic.Entities.Abilities.Active.Loki.AberrantHypermorphAbility$$.ctor = TargetingOptions(0, statsFromClass, 1, 0x1040) IDENTIQUE).
    Un target_id qui n'est pas une tuile du board -> Spawn no-op (diag `spawned=[]`).

    Flags de tour : defauts base (`SetsEndTurnFlags`/`SetsActiveAbilityUsedFlag` = True ; 1166 absent des
    inventaires d'override) -> l'ability termine le tour du caster + pose ActiveAbilityUsed. Le
    « cannot-move-this-turn » que le natif pose SUR LE SUMMON (`IdunBattle.Entities.Behaviours.SpawnUnitBehaviour$$TriggerSpawnedUnitBehaviours :
    flag 0x23 si le summon spawn pendant le tour du joueur courant et n'a ni trait 0x1b ni 0x10) est un
    NO-OP runner : le summon a agi a l'apparition et n'est pas rejoue ce tour dans notre modele (aucune
    boucle qui le referait bouger), donc le flag n'a aucun consommateur offline."""
    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.AberrantHypermorph)  # 1166

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        board = state.board
        tile_id = target_id if (board is not None and target_id in board.by_id) else None
        ectx = ExecutionContext(state=state, rng=state.rng)
        aberrant_hypermorph_tree(tile_id).execute(entities_from_state(state, caster_id), ectx)
        spawned = [p["unit"] for n, p in ectx.emitted if n == "SpawnUnit"]
        attacks = [{"summon": p["summon"], "target": p["target"], "total": p["total"]}
                   for n, p in ectx.emitted if n == "SummonOnAppearance"]
        return {"summon": "genesSmnAberrant", "spawned": spawned, "attacks": attacks,
                "tile": tile_id, "dsl": True}
