"""Abilities actives ASTRA MILITARUM (namespace natif `IdunBattleLogic.Entities.Abilities.Active.Loki.*`).

SupremeCommander (1028, `astraCreed` « Lord Castellan Creed ») — PREMIER consommateur porte du
debloqueur `PerformAIAction` (`abilities/behaviours/ai_control.py` + `operations/summon_ai.py::
ComputerActionOperation`).
SendInTheNextWave (1016, `astraYarrick` « Commissar Yarrick ») — spawn + on-appearance
`UseNormalAttackIfAble` (case-220 P0-SUMMON) : PAS un consommateur de `PerformAIAction`.
"""
from __future__ import annotations

from typing import Optional, TYPE_CHECKING

import gameconfig as GC
import hexgeo

from .base import ActiveAbility
from ..components import (PositionComponent, StatsComponent, UnitComponent,
                          get_ability_stat_modification)
from ...dsl.base import Const
from ...dsl.effects import ExecutionContext
from ...entities.active_ability_type import ActiveAbilityType
from ...entities.behaviours import AtomicGroup, Inform, op_add
from ...entities.effect_type import EffectType
from ...entities.effects.magnitude import ability_var
from ...entities.selectors import (ActiveTarget, AdjacentTiles, CanAddUnit, Caster, CasterTile,
                                   FixedTileIds, SurroundingFriends, Target, UnitsWithIds)
from .behaviours import (AddBondEffect, AddEffect, Spawn, PerformAIAction, UseActiveAbility,
                         entities_from_state)

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


# =============== SendInTheNextWave (Yarrick `astraYarrick`, actif 1016) -- case-220 P0-SUMMON ===============
#
# `SendInTheNextWaveAbility.ExecuteBehaviour @181206490` (MIRROR du DECOMPILE) :
#     unitId = GetStringConstant(config, 0)                                        # astraSmnGuardsman
#     opts   = SpawnUnitOptions.WithStatsFromConfig(config, level)
#     opts.+0x18 = UseNormalAttackIfAble(activeTarget@0x180, target@0x178, <AbilityOrEffect>, ...)
#     tiles  = GetSpawnTilesSelector(this, level)                                  # @181206cc0
#     AActiveAbility.Execute(this, Spawn(caster@0x160, tiles, unitId, opts), entities)
# UN SEUL `Execute` top-level (PAS d'ExecuteAtomic, PAS de Group) et AUCUN `PerformAIAction` : les Cadians
# tirent via le sous-behaviour ON-APPEARANCE embarque dans les options de spawn.
CONST_SITNW_UNIT_ID = 0x00      # GetStringConstant(0)      -> "unitId"      = astraSmnGuardsman
CONST_SITNW_NR_SUMMONS = 0x10   # GetNumberConstant(0x10)   -> "nrOfSummons" = 2  (MEME index que 1028)
VAR_SITNW_MAX_SUMMONS = 0x31    # GetVariableForLevel(0x31) -> "maxSummons"  (case-38 : 0x31 = 49)
SITNW_SPAWNED_UNIT_RANGE = 2    # `GetSpawnedUnitRange @181206ed0` = portee d'arme du summon spawne
                                # (service `ability+0x20`, vslot 0xaa, sur GetStringConstant(0)) ;
                                # gameconfig `astraSmnGuardsman.weapons[1].Range == 2`. CONSTANTE ici :
                                # le service de config d'unites n'est pas expose offline (residu documente
                                # -- si un autre porteur de 1016 apparaissait avec un summon de portee
                                # differente, il faudrait lire la portee de l'arme du summon).


def send_in_the_next_wave_num_summons(state: "State", caster_id: int) -> int:
    """`SendInTheNextWaveAbility.GetNumSummons @181206a70` -- MIRROR :
        `Min( Sum( Direct(GetNumberConstant(0x10)=nrOfSummons),
                   Count(Attackable(Friends(owner@0x148, AllDeadOrResurrectedUnits()))) ),
              Direct(GetVariableForLevel(0x31)=maxSummons[level]) )`
    = `nrOfSummons` + le nombre d'ALLIES MORTS (ou ressuscites) du caster, plafonne a `maxSummons`.
    C'est la formule de count DYNAMIQUE annoncee par case-220 P0-SUMMON ("la vague suivante grossit avec
    les pertes").

    COLLAPSE (noeud VALEUR RNG-libre, folde comme le `pick_n` des feuilles) : `AllDeadOrResurrectedUnits`
    -> les entites-unites du `state` avec `UnitComponent.alive == False` ; `Friends(owner)` -> meme team
    que le caster ; `Attackable` -> filtre de ciblabilite natif, sans equivalent offline distinct sur des
    unites MORTES (aucun modele de non-attaquable parmi les cadavres) -> IDENTITE (residu documente)."""
    from ..components import OwnerComponent, UnitComponent
    consts = (GC.ability("SendInTheNextWave") or {}).get("constants") or {}
    base = int(consts.get("nrOfSummons") or 0)
    ce = state.get_entity(caster_id)
    coc = ce.get_component(OwnerComponent) if ce is not None else None
    team = coc.team if coc is not None else None
    dead = 0
    for e in state.entities.values():
        uc = e.get_component(UnitComponent)
        oc = e.get_component(OwnerComponent)
        if uc is None or oc is None or oc.team != team or uc.alive:
            continue
        dead += 1
    sc = ce.get_component(StatsComponent) if ce is not None else None
    cctx = sc.ctx if sc is not None else None
    level = getattr(cctx, "active_ability_level", None)
    mult = int(getattr(cctx, "ability_variables_multiplier", 100) or 100)
    cap = int(ability_var("SendInTheNextWave", "maxSummons", level, multiplier_pct=mult) or 0)
    return min(base + dead, cap) if cap else base + dead


def send_in_the_next_wave_spawn_tiles(state: "State", caster_id: int, target_id: int, n: int) -> list:
    """`SendInTheNextWaveAbility.GetSpawnTilesSelector @181206cc0` -- MIRROR :
        r         = GetSpawnedUnitRange()                                       # = 2
        possible  = CanAddUnit(SurroundingTiles(target@0x178, 0, r))            # @181206bc0
        preferred = AttackTilesForTarget(CanAddUnit(SurroundingTiles(target, 0, r)), target)  # @181206c30
        k         = Min(n, Count(preferred))
        pickA     = PickRandomly(preferred, k)
        rest      = Sum(n, Multiply(k, Direct(-1)))                             # = n - k
        pickB     = PickRandomly(possible, rest)
        return    pickA op_Addition pickB
    -> on remplit d'abord avec les tuiles d'ou le Cadian pourra TIRER sur la cible, puis on complete avec
    n'importe quelle tuile libre du rayon.

    COLLAPSE (le selecteur est un arbre S avec DEUX `PickRandomly` imbriques -> le tirage vit dans le
    collapse, qui seul voit `state.rng` ; meme doctrine que le `pick_n` de `Spawn`). `AttackTilesForTarget`
    (`AttackTilesForTargetSelector @180de9a50`, qui consulte la config d'arme + la geometrie de tir) est
    l'IDENTITE offline : `possible` est deja le disque de rayon = portee d'arme du summon autour de la
    cible, et aucun modele de cover/ligne de vue n'existe cote port (residu documente) -> `preferred ==
    possible` -> k = min(n, |possible|), rest = n - k.
    ATTENTION : quand `|possible| < n`, l'union native produit des DOUBLONS de tuiles (deux PickRandomly sur le meme
    ensemble) ; le port les elimine (une 2e pose sur une tuile deja occupee par le summon precedent serait
    de toute facon un no-op cote natif). HYPOTHESE flaguee (cas rare : plateau tres encombre)."""
    from ..abilities.loki.splash import _pick_randomly_n
    board = state.board
    te = state.get_entity(target_id)
    tpc = te.get_component(PositionComponent) if te is not None else None
    if board is None or tpc is None:
        return []
    occ = set()
    for e in state.entities.values():
        uc = e.get_component(UnitComponent)
        pc = e.get_component(PositionComponent)
        if pc is None or (uc is not None and not uc.alive):
            continue
        t = board.id_at(pc.col, pc.row)
        if t is not None:
            occ.add(t)
    possible = []
    for (col, row) in hexgeo.disk(tpc.col, tpc.row, SITNW_SPAWNED_UNIT_RANGE):
        if (col, row) == (tpc.col, tpc.row):                 # SurroundingTiles(includeCenter=0)
            continue
        t = board.id_at(col, row)
        if t is not None and t not in occ and board.walkable(t):   # CanAddUnit
            possible.append(t)
    preferred = list(possible)                               # AttackTilesForTarget -> identite offline
    k = min(int(n), len(preferred))                          # Min(n, Count(preferred))
    picked = list(_pick_randomly_n(state, preferred, k))     # PickRandomly(preferred, k)
    rest = int(n) - k                                        # Sum(n, Multiply(k, -1))
    if rest > 0:
        picked += [t for t in _pick_randomly_n(state, possible, rest) if t not in picked]
    return picked


def send_in_the_next_wave_tree(tiles: list) -> Spawn:
    """Arbre de `SendInTheNextWaveAbility.ExecuteBehaviour @181206490` : UN noeud `Spawn` dont les options
    portent le sous-behaviour ON-APPEARANCE `UseNormalAttackIfAble(activeTarget@0x180, target@0x178)`
    (`DSLFactory.UseNormalAttackIfAble @180e01870` -> `UseActiveAbilityBehaviour(actor=@0x180,
    targets=@0x178, TestUnitProvider(@0x180), ...)`) = chaque Cadian fraichement pose TIRE immediatement
    sur la cible du cast. Les tuiles sont le collapse de `GetSpawnTilesSelector` (cf. ci-dessus)."""
    return Spawn(FixedTileIds(tiles), "SendInTheNextWave",
                 on_appearance=UseActiveAbility(ActiveTarget(), Target()))


class SendInTheNextWaveAbility(ActiveAbility):
    """`SendInTheNextWaveAbility.ExecuteBehaviour @181206490` (id 1016, `astraYarrick` "Commissar Yarrick",
    AstraMilitarum). Fait apparaitre `nrOfSummons + nb d'allies morts` (plafonne a `maxSummons[level]`)
    Cadian Guardsmen (`astraSmnGuardsman`, stats `WithStatsFromConfig`) sur des tuiles libres a <= 2 hex de
    la cible -- en PRIORISANT celles d'ou ils peuvent tirer -- puis CHACUN tire immediatement sur la cible
    (`UseNormalAttackIfAble` on-appearance).

    N'utilise NI `PerformAIAction` NI `PerformAIAttackFromCurrentPosition` : l'on-appearance est une
    attaque NORMALE dirigee sur la cible du cast (pas un tour d'IA). Retour : {spawned, attacks, count,
    tiles, dsl}."""
    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.SendInTheNextWave)   # 1016
    ABILITY_ID = "SendInTheNextWave"

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        if target_id is None or state.get_entity(caster_id) is None:
            return None
        n = send_in_the_next_wave_num_summons(state, caster_id)
        tiles = send_in_the_next_wave_spawn_tiles(state, caster_id, target_id, n)
        ectx = ExecutionContext(state=state, rng=state.rng)
        send_in_the_next_wave_tree(tiles).execute(
            entities_from_state(state, caster_id, target_id), ectx)
        spawned = [p["unit"] for nm, p in ectx.emitted if nm == "SpawnUnit"]
        attacks = [p for nm, p in ectx.emitted if nm == "UseActiveAbility"]
        return {"spawned": spawned, "attacks": attacks, "count": n, "tiles": tiles, "dsl": True}


# =================================================================================================== #
# MalleusRocketLauncher (1142, `astraOrdnanceBattery` -- Ordnance Battery, MachineOfWar) -- lot #90-B
# Patron « pose d'effet(s) seule » : le CAST ne fait que MARQUER la tuile ciblee (3 effets), aucune
# attaque immediate ; le barrage vient de la phase 2 (`MalleusRocketLauncher_AttackAbility`), NON portee.
# =================================================================================================== #

MALLEUS_ID = "MalleusRocketLauncher"
MALLEUS_BOND = int(EffectType.MalleusRocketLauncher)                  # 0x51c = 1308
MALLEUS_PENDING_TARGET = int(EffectType.MalleusRocketLauncher_PendingTarget)   # 0x51d = 1309
MALLEUS_SPOTTED_TARGET = int(EffectType.MalleusRocketLauncher_SpottedTarget)   # 0x51e = 1310
# `DSLFactory.Inform(dict{0x9a: UnitsTeamId(owner@0x148)})` @1811f1d90 : cle de message 0x9a = 154.
MALLEUS_INFORM_MESSAGE = 0x9a


def malleus_rocket_launcher_tree(target_tile_id: int):
    """Arbre de `MalleusRocketLauncherAbility.ExecuteBehaviour @1811f1d90` -- MIRROR 1:1 du DECOMPILE :

        bond   = AddBondEffect(0x51c=1308 MalleusRocketLauncher, absRef, source=owner@0x148,
                               targets=target@0x178, bond=owner@0x148, opts=0)
        inform = Inform( { 0x9a : UnitsTeamId(owner@0x148) } )
        pend   = AddEffect(0x51d=1309 MalleusRocketLauncher_PendingTarget, absRef,
                           source=owner@0x148, targets=target@0x178, opts=0)
        spot   = AddEffect(0x51e=1310 MalleusRocketLauncher_SpottedTarget, absRef,
                           source=owner@0x148, targets=target@0x178, opts=0)
        Execute( ((inform + bond) + pend) + spot )

    (`op_Addition` x3, `AActiveAbility.Execute`.) Les TROIS effets se posent sur la MEME entite = la
    TUILE ciblee (cast tile-target) ; les options-structs sont ZERO -> duree `DefaultAmountOfRounds`
    (1308/1309/1310 hors table @181559ff0 -> `remaining = 0` = permanent, CONFIRME live).

    `Inform` = notification du bus de messages natif (charge utile = l'id d'equipe de l'owner) :
    AUCUNE mutation d'etat -> no-op cote runner (cf. `entities/behaviours.py::Inform`), present pour le
    mirror structurel de l'arbre."""
    tgt = FixedTileIds([target_tile_id])
    inform = Inform(MALLEUS_INFORM_MESSAGE)
    bond = AddBondEffect(MALLEUS_BOND, EffectType.MalleusRocketLauncher.name,
                         Caster(), tgt, duration_rounds=None)
    pend = AddEffect(MALLEUS_PENDING_TARGET, EffectType.MalleusRocketLauncher_PendingTarget.name,
                     tgt, duration_rounds=None)
    spot = AddEffect(MALLEUS_SPOTTED_TARGET, EffectType.MalleusRocketLauncher_SpottedTarget.name,
                     tgt, duration_rounds=None)
    return op_add(op_add(op_add(inform, bond), pend), spot)


class MalleusRocketLauncherAbility(ActiveAbility):
    """`MalleusRocketLauncherAbility.ExecuteBehaviour @1811f1d90` (id 1142, `astraOrdnanceBattery` --
    Ordnance Battery, Astra Militarum, MachineOfWar). Cast TILE-TARGET (`abilityTargets` kind="tile").

    RE (ghidra gqfc5mff6c) :
    - `ExecuteBehaviour @1811f1d90` : cf. `malleus_rocket_launcher_tree` (1 `AddBondEffect` + 1 `Inform`
      + 2 `AddEffect`, zero attaque).
    - `.ctor @1811f20f0` ; `GetAdditionalTargets @1811f20b0` (preview/playbook).
    - PHASE 2 (NON PORTEE) : `MalleusRocketLauncher_AttackAbility.GetTargetTiles @181222aa0` +
      `CreateBehaviour @1812226b0` (le barrage differe, `nrOfProjectiles`/`nrOfProjectiles_2`/`_3`,
      `damageProfile=Blast`), et les effets `MalleusRocketLauncherEffect .ctor @180f57ed0` /
      `MalleusRocketLauncher_SpottedTargetEffect .ctor @180f58120` (+ `CreateTargetSelector @180f57f80`).

    OBSERVABLE DU CAST (mesure live, runner MoW C1_02, caster 53, cible = tuile (0,0)) : la tuile (0,0)
    porte les TROIS effets `MalleusRocketLauncher` (1308), `_PendingTarget` (1309), `_SpottedTarget`
    (1310), tous `source 53, remaining 0, level 1`. AUCUN effet sur la MoW, AUCUN degat.

    `target_id` = id de TUILE. Flags de tour : defauts base -> termine le tour + ActiveAbilityUsed."""
    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.MalleusRocketLauncher)   # 1142
    ABILITY_ID = MALLEUS_ID

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        board = state.board
        tile_id = target_id if (board is not None and target_id in board.by_id) else None
        if tile_id is None:
            return {"tile": None, "posed": [], "dsl": True}
        ectx = ExecutionContext(state=state, rng=state.rng)
        entities = entities_from_state(state, caster_id)
        malleus_rocket_launcher_tree(tile_id).execute(entities, ectx)
        posed = [{"target": p["target"], "effect": p["effect_type"]}
                 for nm, p in ectx.emitted if nm in ("AddEffect", "AddBondEffect")]
        return {"tile": tile_id, "posed": posed, "dsl": True}
