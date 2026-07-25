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
from .behaviours import (AddBondEffect, AddEffect, Spawn, PerformAIAction, PerformAIAttack,
                         UseActiveAbility, entities_from_state)

if TYPE_CHECKING:
    from ..state import State

# Index des constantes lues par `IdunBattleLogic.Entities.Abilities.Active.Loki.SupremeCommanderAbility$$ExecuteBehaviour`
# (`AbilityConfiguration.Get*Constant(config, <index>)`) -> cle gameconfig correspondante.
CONST_UNIT_ID = 0x00           # GetStringConstant(0)       -> "unitId"          = astraSmnGuardsman
CONST_NR_OF_SUMMONS = 0x10     # GetNumberConstant(0x10)    -> "nrOfSummons"     = 2
CONST_RANGE = 0x16             # GetNumberConstant(0x16)    -> "range"           = 2
CONST_AFFECTED_UNIT_IDS = 0x3e  # GetStringArrayConstant(0x3e) -> "affectedUnitIds"


def supreme_commander_spawn_tree(count: int) -> AtomicGroup:
    """1er noeud natif de `IdunBattleLogic.Entities.Abilities.Active.Loki.SupremeCommanderAbility$$ExecuteBehaviour` :
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
    """2e noeud natif de `IdunBattleLogic.Entities.Abilities.Active.Loki.SupremeCommanderAbility$$ExecuteBehaviour` :
        `Execute( PerformAIAction( UnitsWithIds( SurroundingFriends(caster@0x160, casterTile@0x168,
                                                                    radius, 1, 3),
                                                 GetStringArrayConstant(0x3e) ),
                                   asGroup=1, resetTurnFlags=1 ),
                  entities )`
    `IdunBattleLogic.Entities.DSLFactory$$SurroundingFriends se deplie en `Friends(caster, Units(SurroundingTiles(casterTile, 1,
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
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.SupremeCommanderAbility$$ExecuteBehaviour` (id 1028, `astraCreed` « Creed »,
    AstraMilitarum) — MIRROR du DECOMPILE.

    Corps natif (ordre de lecture) :
        unitId   = GetStringConstant(config, 0)                                 # astraSmnGuardsman
        nSummons = GetNumberConstant(config, 0x10)                              # nrOfSummons = 2
        ids      = GetStringArrayConstant(config, 0x3e)                         # affectedUnitIds
        modN     = GetAbilityStatModification(caster@0x168, VarOrConst(0x10))   # IdunBattleLogic.Entities.Abilities.Active.Loki.SupremeCommanderAbility$$ExecuteBehaviour+0x16b
        range    = GetNumberConstant(config, 0x16)                              # range = 2
        modR     = GetAbilityStatModification(caster@0x168, VarOrConst(0x16))   # IdunBattleLogic.Entities.Abilities.Active.Loki.SupremeCommanderAbility$$ExecuteBehaviour+0x24a
        if (modR != 0) range = modR                                             # OVERRIDE (pas additif)
        opts     = SpawnUnitOptions.WithStatsFromConfig(config, level)
        spawnB   = Spawn(caster, PickRandomly(CanAddUnit(AdjacentTiles(caster)), nSummons + modN), unitId, opts)
        aiB      = PerformAIAction(UnitsWithIds(SurroundingFriends(caster, casterTile, range, 1, 3), ids), 1, 1)
        AActiveAbility.ExecuteAtomic(this, spawnB, entities, 0x48)
        AActiveAbility.Execute(this, aiB, entities)

    Les DEUX consommations de `GetAbilityStatModification` ont des semantiques DIFFERENTES (lu, pas
    devine) : **ADDITIVE** pour `nrOfSummons`, **OVERRIDE si non nulle** pour `range`. La seule source
    native de ces modifications est `ListenUpMaggotsEffect` IdunBattle.Entities.Effects.Loki.ListenUpMaggotsEffect$$ApplyInternal (passif de `astraSmnKell`,
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
        # --- constantes + modifications d'ability (mirror des 2 call-sites IdunBattleLogic.Entities.Abilities.Active.Loki.SupremeCommanderAbility$$ExecuteBehaviour+0x16b/IdunBattleLogic.Entities.Abilities.Active.Loki.SupremeCommanderAbility$$ExecuteBehaviour+0x24a) ---
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
# `IdunBattleLogic.Entities.Abilities.Active.Loki.SendInTheNextWaveAbility$$ExecuteBehaviour` (MIRROR du DECOMPILE) :
#     unitId = GetStringConstant(config, 0)                                        # astraSmnGuardsman
#     opts   = SpawnUnitOptions.WithStatsFromConfig(config, level)
#     opts.+0x18 = UseNormalAttackIfAble(activeTarget@0x180, target@0x178, <AbilityOrEffect>, ...)
#     tiles  = GetSpawnTilesSelector(this, level)                                  # IdunBattleLogic.Entities.Abilities.Active.Loki.SendInTheNextWaveAbility$$GetSpawnTilesSelector
#     AActiveAbility.Execute(this, Spawn(caster@0x160, tiles, unitId, opts), entities)
# UN SEUL `Execute` top-level (PAS d'ExecuteAtomic, PAS de Group) et AUCUN `PerformAIAction` : les Cadians
# tirent via le sous-behaviour ON-APPEARANCE embarque dans les options de spawn.
CONST_SITNW_UNIT_ID = 0x00      # GetStringConstant(0)      -> "unitId"      = astraSmnGuardsman
CONST_SITNW_NR_SUMMONS = 0x10   # GetNumberConstant(0x10)   -> "nrOfSummons" = 2  (MEME index que 1028)
VAR_SITNW_MAX_SUMMONS = 0x31    # GetVariableForLevel(0x31) -> "maxSummons"  (case-38 : 0x31 = 49)
SITNW_SPAWNED_UNIT_RANGE = 2    # `IdunBattleLogic.Entities.Abilities.Active.Loki.SendInTheNextWaveAbility$$GetSpawnedUnitRange` = portee d'arme du summon spawne
                                # (service `ability+0x20`, vslot 0xaa, sur GetStringConstant(0)) ;
                                # gameconfig `astraSmnGuardsman.weapons[1].Range == 2`. CONSTANTE ici :
                                # le service de config d'unites n'est pas expose offline (residu documente
                                # -- si un autre porteur de 1016 apparaissait avec un summon de portee
                                # differente, il faudrait lire la portee de l'arme du summon).


def send_in_the_next_wave_num_summons(state: "State", caster_id: int) -> int:
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.SendInTheNextWaveAbility$$GetNumSummons` -- MIRROR :
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
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.SendInTheNextWaveAbility$$GetSpawnTilesSelector` -- MIRROR :
        r         = GetSpawnedUnitRange()                                       # = 2
        possible  = CanAddUnit(SurroundingTiles(target@0x178, 0, r))            # IdunBattleLogic.Entities.Abilities.Active.Loki.SendInTheNextWaveAbility$$GetPossibleSpawnTiles
        preferred = AttackTilesForTarget(CanAddUnit(SurroundingTiles(target, 0, r)), target)  # IdunBattleLogic.Entities.Abilities.Active.Loki.SendInTheNextWaveAbility$$GetPreferredSpawnTiles
        k         = Min(n, Count(preferred))
        pickA     = PickRandomly(preferred, k)
        rest      = Sum(n, Multiply(k, Direct(-1)))                             # = n - k
        pickB     = PickRandomly(possible, rest)
        return    pickA op_Addition pickB
    -> on remplit d'abord avec les tuiles d'ou le Cadian pourra TIRER sur la cible, puis on complete avec
    n'importe quelle tuile libre du rayon.

    COLLAPSE (le selecteur est un arbre S avec DEUX `PickRandomly` imbriques -> le tirage vit dans le
    collapse, qui seul voit `state.rng` ; meme doctrine que le `pick_n` de `Spawn`). `AttackTilesForTarget`
    (`AttackTilesForTargetSelector IdunBattleLogic.Entities.DSLFactory$$AttackTilesForTarget`, qui consulte la config d'arme + la geometrie de tir) est
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
    """Arbre de `IdunBattleLogic.Entities.Abilities.Active.Loki.SendInTheNextWaveAbility$$ExecuteBehaviour` : UN noeud `Spawn` dont les options
    portent le sous-behaviour ON-APPEARANCE `UseNormalAttackIfAble(activeTarget@0x180, target@0x178)`
    (`IdunBattleLogic.Entities.DSLFactory$$UseNormalAttackIfAble` -> `UseActiveAbilityBehaviour(actor=@0x180,
    targets=@0x178, TestUnitProvider(@0x180), ...)`) = chaque Cadian fraichement pose TIRE immediatement
    sur la cible du cast. Les tuiles sont le collapse de `GetSpawnTilesSelector` (cf. ci-dessus)."""
    return Spawn(FixedTileIds(tiles), "SendInTheNextWave",
                 on_appearance=UseActiveAbility(ActiveTarget(), Target()))


class SendInTheNextWaveAbility(ActiveAbility):
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.SendInTheNextWaveAbility$$ExecuteBehaviour` (id 1016, `astraYarrick` "Commissar Yarrick",
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
# `DSLFactory.Inform(dict{0x9a: UnitsTeamId(owner@0x148)})` IdunBattleLogic.Entities.Abilities.Active.Loki.MalleusRocketLauncherAbility$$ExecuteBehaviour : cle de message 0x9a = 154.
MALLEUS_INFORM_MESSAGE = 0x9a


def malleus_rocket_launcher_tree(target_tile_id: int):
    """Arbre de `IdunBattleLogic.Entities.Abilities.Active.Loki.MalleusRocketLauncherAbility$$ExecuteBehaviour` -- MIRROR 1:1 du DECOMPILE :

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
    (1308/1309/1310 hors table idun.Idun.Source.Shared.Battle.StaticBattleRules.StaticBattleRules.Effect$$DefaultAmountOfRounds -> `remaining = 0` = permanent, CONFIRME live).

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
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.MalleusRocketLauncherAbility$$ExecuteBehaviour` (id 1142, `astraOrdnanceBattery` --
    Ordnance Battery, Astra Militarum, MachineOfWar). Cast TILE-TARGET (`abilityTargets` kind="tile").

    RE (ghidra gqfc5mff6c) :
    - `IdunBattleLogic.Entities.Abilities.Active.Loki.MalleusRocketLauncherAbility$$ExecuteBehaviour` : cf. `malleus_rocket_launcher_tree` (1 `AddBondEffect` + 1 `Inform`
      + 2 `AddEffect`, zero attaque).
    - `.IdunBattleLogic.Entities.Abilities.Active.Loki.MalleusRocketLauncherAbility$$.ctor` ; `IdunBattleLogic.Entities.Abilities.Active.Loki.MalleusRocketLauncherAbility$$GetAdditionalTargets` (preview/playbook).
    - PHASE 2 (NON PORTEE) : `IdunBattleLogic.Entities.Abilities.Active.Loki.MalleusRocketLauncher_AttackAbility$$GetTargetTiles` +
      `IdunBattleLogic.Entities.Abilities.Active.Loki.MalleusRocketLauncher_AttackAbility$$CreateBehaviour` (le barrage differe, `nrOfProjectiles`/`nrOfProjectiles_2`/`_3`,
      `damageProfile=Blast`), et les effets `MalleusRocketLauncherEffect .IdunBattle.Entities.Effects.Loki.MalleusRocketLauncherEffect$$.ctor` /
      `MalleusRocketLauncher_SpottedTargetEffect .IdunBattle.Entities.Effects.Loki.MalleusRocketLauncher_SpottedTargetEffect$$.ctor` (+ `IdunBattle.Entities.Effects.Loki.MalleusRocketLauncher_SpottedTargetEffect$$CreateTargetSelector`).

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


# =================================================================================================== #
# ForwardSpotter (1143, `astraOrdnanceBattery` -- Ordnance Battery, MachineOfWar) -- lot #90 groupe C
# Patron « SPAWN template » (seul de son patron dans le lot) : c'est EXACTEMENT le template deja porte
# `Spawn + WithStatsFromConfig + on-appearance PerformAIAttack` (AberrantHypermorph / AlphaWarrior /
# DeathFromAbove), la seule specificite etant la chaine de SELECTION DE TUILE.
#
# `IdunBattleLogic.Entities.Abilities.Active.Loki.ForwardSpotterAbility$$ExecuteBehaviour` (MIRROR) :
#   opts        = SpawnUnitOptions.WithStatsFromConfig(config@0x60, entities)
#   opts+0x18   = PerformAIAttack(ActiveTarget@0x180, 1, ...)            # sous-behaviour on-appearance
#   nrOfSummons = GetNumberConstant(config, 0x10)                        # = 1
#   unitId      = GetStringConstant(config, 0)                           # = astraSmnGuardsman
#   base        = CanAddUnit(AdjacentTiles(target@0x178))
#   sel         = TilesUnitCanAttackFrom(base, caster@0x160, unitId, 1).Otherwise(base)
#   sel         = SortTilesByUtilityForSummon(sel, 7, owner@0x148)
#   tiles       = First(sel, Direct(nrOfSummons))                        # = PickFirstN
#   AActiveAbility.Execute( Spawn(caster@0x160, tiles, unitId, opts), entities )
#
# (`IdunBattleLogic.Entities.Abilities.Active.Loki.ForwardSpotterAbility$$PickTiles` = la MEME chaine,
#  exposee pour la face DECISION.)
#
# COLLAPSE ASSUME (doctrine slice-18/19, meme classe que `SendInTheNextWaveAbility$$GetSpawnTilesSelector`) :
#  * `TilesUnitCanAttackFrom(...).Otherwise(base)` est un NO-OP POUR CE CALL-SITE, et ce par les DEUX
#    lectures possibles de son referent (`ClosestPositionToTarget..ctor` : +0x28 = `caster@0x160`) :
#      - referent = le CASTER : c'est une MACHINE OF WAR HORS PLATEAU (aucune position) -> la portee
#        d'attaque ne se calcule pas -> selecteur VIDE -> `.Otherwise(base)` rend `base` ;
#      - referent = la cible du barrage : `base` ne contient que des tuiles ADJACENTES a la cible
#        (distance 1) et la portee max du summon `astraSmnGuardsman` est 2 (arme Las, gameconfig) ->
#        TOUTES passent -> selecteur == `base`.
#    Les deux lectures CONVERGENT sur le meme ensemble -> l'ambiguite ne change AUCUN observable.
#  * `SortTilesByUtilityForSummon(sel, 7, owner)` = `SortTilesByUtility(sel, <units>, UtilityDefinition(7),
#    owner)` -> `IdunBattle.Entities.Selectors.SortTilesByUtilitySelector$$Select` = un tri par
#    `IdunBattleLogic.AI.Utilities.UtilityDecider$$CalculateUtility` (moteur d'utilite IA COMPLET, cle =
#    `-utilite`). NON PORTE : meme collapse que SkyStrike/HeroicFusillade. Le referent `owner@0x148` etant
#    ici une MoW SANS POSITION, le collapse « la plus proche du caster » des autres call-sites n'a meme pas
#    de sens -> on conserve l'ORDRE DU SELECTEUR (voisinage natif `board.neighbours`, deterministe).
#    RESIDU EXPLICITE : quand `|base| > nrOfSummons`, la TUILE choisie peut differer du live ; le POOL et le
#    CARDINAL, eux, sont exacts (meme classe de residu que le GAP RNG #215 de PickRandomly).
# =================================================================================================== #

FORWARD_SPOTTER_ID = "ForwardSpotter"
FS_CONST_NR_OF_SUMMONS = 0x10        # GetNumberConstant(0x10) -> "nrOfSummons" = 1
FS_CONST_UNIT_ID = 0x00              # GetStringConstant(0)    -> "unitId"      = astraSmnGuardsman


def forward_spotter_num_summons() -> int:
    """`GetNumberConstant(config, 0x10)` = `nrOfSummons` (CONSTANTE, hors niveau) de 1143."""
    consts = (GC.ability(FORWARD_SPOTTER_ID) or {}).get("constants") or {}
    return int(consts.get("nrOfSummons") or 0)


def forward_spotter_pick_tiles(state: "State", target_id: Optional[int], n: int) -> list:
    """COLLAPSE de `IdunBattleLogic.Entities.Abilities.Active.Loki.ForwardSpotterAbility$$PickTiles`
    (cf. le bloc ci-dessus) : `First(SortTilesByUtilityForSummon(CanAddUnit(AdjacentTiles(target))
    .Otherwise-filtre, 7, owner), nrOfSummons)`.

    Rendu = les `n` premieres tuiles LIBRES (walkable + inoccupees par un vivant) ADJACENTES a la tuile
    ciblee, dans l'ordre du voisinage natif. `target_id` = une UNITE (l'ability cible une unite ennemie,
    cf. `ForwardSpotterAbility$$GetDynamicInvalidTargetReason` : `IsUnit(target) && target != caster`)."""
    board = state.board
    te = state.get_entity(target_id) if target_id is not None else None
    tpc = te.get_component(PositionComponent) if te is not None else None
    if board is None or tpc is None:
        return []
    tid = board.id_at(tpc.col, tpc.row)
    if tid is None:
        return []
    occ = set()
    for e in state.entities.values():                     # CanAddUnit : LIBRE = aucun occupant VIVANT
        uc = e.get_component(UnitComponent)
        pc = e.get_component(PositionComponent)
        if pc is None or (uc is not None and not uc.alive):
            continue
        t = board.id_at(pc.col, pc.row)
        if t is not None:
            occ.add(t)
    free = [t for t in board.neighbours(tid) if t not in occ and board.walkable(t)]
    return free[:max(0, int(n))]


def forward_spotter_tree(tiles: list) -> Spawn:
    """Arbre de `IdunBattleLogic.Entities.Abilities.Active.Loki.ForwardSpotterAbility$$ExecuteBehaviour` :
    UN noeud `Spawn` (owner = caster@0x160, `WithStatsFromConfig`) dont les options portent le
    sous-behaviour ON-APPEARANCE `PerformAIAttack(ActiveTarget@0x180)` -- le Cadian fraichement pose
    execute immediatement une attaque IA. Les tuiles sont le collapse de `PickTiles` (cf. ci-dessus).

    ⚠ Le on-appearance est un `IdunBattleLogic.Entities.DSLFactory$$PerformAIAttack` (routine IA depuis la
    position du summon), PAS un `UseNormalAttackIfAble(target)` dirige (contraste SendInTheNextWave) :
    le natif ne lui passe QUE l'acteur (`@0x180`), aucune cible."""
    return Spawn(FixedTileIds(tiles), FORWARD_SPOTTER_ID,
                 on_appearance=PerformAIAttack(ActiveTarget()))


class ForwardSpotterAbility(ActiveAbility):
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.ForwardSpotterAbility$$ExecuteBehaviour` (id 1143,
    `astraOrdnanceBattery` -- Ordnance Battery, Astra Militarum, MACHINE OF WAR). Cast UNIT-TARGET.

    Kit gameconfig 1143 : `nrOfSummons=1`, `unitId=astraSmnGuardsman`, `summonHp`/`summonDmg`/`summonArmor`
    [level] (rarity-affected), `initialCooldownTurns=2`. AUCUN volet degat propre : l'ability EST le spawn.

    OBSERVABLE : 1 `astraSmnGuardsman` apparait sur une tuile libre adjacente a la cible et attaque
    immediatement. Turn-flags = defauts base (1143 absent des overrides).

    Retour : {spawned, attacks, tiles, count, dsl}."""
    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.ForwardSpotter)   # 1143
    ABILITY_ID = FORWARD_SPOTTER_ID

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        if target_id is None or state.get_entity(caster_id) is None:
            return None
        n = forward_spotter_num_summons()
        tiles = forward_spotter_pick_tiles(state, target_id, n)
        ectx = ExecutionContext(state=state, rng=state.rng)
        forward_spotter_tree(tiles).execute(
            entities_from_state(state, caster_id, target_id), ectx)
        spawned = [p["unit"] for nm, p in ectx.emitted if nm == "SpawnUnit"]
        attacks = [p for nm, p in ectx.emitted if nm == "PerformAIAttack"]
        return {"spawned": spawned, "attacks": attacks, "tiles": tiles, "count": n, "dsl": True}
