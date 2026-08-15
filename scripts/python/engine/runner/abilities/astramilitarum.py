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
from ...entities.selectors.accessors import ActiveTarget, CasterTile, FixedTileIds, Target
from ...entities.selectors.tiles import AdjacentTiles, CanAddUnit, Caster
from ...entities.selectors.units import Sub, SurroundingFriends, Units, UnitsWithIds
from ...entities.stats import StatType
from ...utilities.tile import sort_tiles_by_utility
from ... import battle_query
from ...services import battle_query as _svc_bq   # `BattleQuery$$GetUnitMaxRange` (#287-r11-r1)
from .targeting import (RANGE_ADJACENT, RANGE_ADJACENT_IF_MELEE_CASTER, RANGE_SELF,
                        RANGE_WHOLE_BOARD, RANGED_BOOL_FALSE, TargetingOptions)
from .targeting_rule import TargetingRule as TR
from .behaviours.ai_control import PerformAIAction
from .behaviours.combat import AttackWithAttackDamage, SortedAttackSeries, UseActiveAbility
from .behaviours.context import entities_from_state, main_tile_id
from .behaviours.effects import AddBondEffect, AddEffect
from .behaviours.summon import PerformAIAttack, Spawn
from ...entities.ability_constant_type import AbilityConstantType   # #270-r1-r1-r3
from ...entities.ability_variable_type import AbilityVariableType   # #270-r1-r1-r3
from ..components import OwnerComponent, UnitComponent
from .targeting import unit_of_entity
from .targeting import tile_is_empty_or_steppable   # `TileExtensions$$IsEmptyOrSteppable` (#287-r11-r1)
from ..abilities.loki.splash import _pick_randomly_n
from .loki.splash import _pick_randomly_n

if TYPE_CHECKING:
    from ..state import State

# Index des constantes lues par `IdunBattleLogic.Entities.Abilities.Active.Loki.SupremeCommanderAbility$$ExecuteBehaviour`
# (`AbilityConfiguration.Get*Constant(config, <index>)`) -> cle gameconfig correspondante.
CONST_UNIT_ID = 0x00           # GetStringConstant(0)       -> "unitId"          = astraSmnGuardsman
CONST_NR_OF_SUMMONS = AbilityConstantType.nrOfSummons     # GetNumberConstant(0x10)    -> "nrOfSummons"     = 2
CONST_RANGE = AbilityConstantType.range             # GetNumberConstant(0x16)    -> "range"           = 2
CONST_AFFECTED_UNIT_IDS = AbilityConstantType.affectedUnitIds  # GetStringArrayConstant(0x3e) -> "affectedUnitIds"


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
    `IdunBattleLogic.Entities.DSLSelectors$$SurroundingFriends se deplie en `Friends(caster, Units(SurroundingTiles(casterTile, 1,
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

    # `IdunBattleLogic.Entities.Abilities.Active.Loki.SupremeCommanderAbility$$.ctor` :
    #     preset = <TargetingRange statics+0x60>                     # copie de 0x18 octets
    #     TargetingOptions..ctor(&opts, isSelfCasting=1, &preset, forceMeleeTarget=1, 0x208000, 0,0,0)
    #     AActiveAbility..ctor(this, &opts, 2, 0)                    # AbilityAttackType.Others
    # FORME 1 « FLAGS DIRECTS » (surcharge 8 arguments de `IdunBattle.Core.Services.TargetingOptions$$.ctor`,
    # celle qui ecrit `+0x28 <- param_5` SANS OR) -> le litteral **EST** le masque effectif. Ce n'est
    # PAS l'overload piege « PRESET + flags » a 4 arguments : le 3e argument recu ici est un
    # `TargetingRange` de 0x18 octets (recopie de `TargetingRange$$.cctor`), qui n'a pas de `+0x28`.
    #   0x208000 = CasterHasFreeAdjacentTile (1<<21 = 0x200000)
    #            | CasterIsPossibleTarget    (1<<15 = 0x008000)      -> somme EXACTE, 0 bit residuel
    #   range = `TargetingRange$$.cctor` statics+0x60 = `{onlyAdjacent = RangedBool.False,
    #           overrideRange = Nullable(0)}` -> RANGE_SELF : portee NULLE (le cast ne porte que sur
    #           la propre tuile du caster).
    #   forceMeleeTarget = param_4 = 1 = RangedBool.False
    # `isSelfCasting = 1` (le BYTE `options+0x00`) : c'est l'AIGUILLAGE de l'overload 5 arguments de
    # `IdunBattle.Core.Services.TargetingQuery$$GetInvalidTargetReason`, pas un bit de `Rules` --
    # caste sur lui-meme, Creed part sur `TargetingQuery$$GetCasterNotAddedReason` et la cascade
    # CIBLE n'est JAMAIS evaluee. Coherent avec l'i2 (« Summons up to N Cadian Guardsman in free
    # adjacent hexes ») et avec `supreme_commander_spawn_tree` (`AdjacentTiles(Caster())`).
    # CONSEQUENCE DE PORT : `CasterHasFreeAdjacentTile` (regle du filtre statique CIBLE, juste apres
    # `TargetHasFreeAdjacentTile` et avant `TargetTileIsFree`) est INERTE pour ce porteur -- le seul
    # chemin qui l'atteindrait (cible != caster) est deja refuse en amont par la portee 0. Elle reste
    # donc NON PORTEE dans `targeting.py`, et c'est dit dans son inventaire.
    TARGETING_OPTIONS = TargetingOptions(rules=(
          TR.CasterHasFreeAdjacentTile
        | TR.CasterIsPossibleTarget
    ), self_cast=True, range=RANGE_SELF, force_melee_target=RANGED_BOOL_FALSE)

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
SITNW_ID = "SendInTheNextWave"
CONST_SITNW_UNIT_ID = AbilityConstantType.unitId          # GetStringConstant(0x0)    -> "unitId"      = astraSmnGuardsman
CONST_SITNW_NR_SUMMONS = AbilityConstantType.nrOfSummons   # GetNumberConstant(0x10)   -> "nrOfSummons" = 2  (MEME index que 1028)
VAR_SITNW_MAX_SUMMONS = AbilityVariableType.maxSummons    # GetVariableForLevel(0x31) -> "maxSummons"  (case-38 : 0x31 = 49)


def send_in_the_next_wave_spawned_unit_range() -> int:
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.SendInTheNextWaveAbility$$GetSpawnedUnitRange`
    -- MIRROR, qui tient en une ligne :

        return battleQuery.GetUnitMaxRange( GetStringConstant(0x0 unitId) );   // slot 171

    ⚠ ETAIT UNE CONSTANTE EN DUR (`SITNW_SPAWNED_UNIT_RANGE = 2`), sur le motif « le service de
    config d'unites n'est pas expose offline ». C'etait vrai du SERVICE et faux de la SOURCE : le
    natif passe par `BattleQuery$$GetUnitConfig`, donc par le CATALOGUE, que `gameconfig` porte.
    Le mirror `services/battle_query.get_unit_max_range` le lit ; il n'y a plus qu'UN foyer, celui
    que la regle dynamique de ciblage (#287-r11-r1) partage avec `GetSpawnTilesSelector`.
    Sur le gameconfig courant : `astraSmnGuardsman.weapons = [Physical(sans portee), Las(Range 2)]`
    -> `max(1, 2)` = **2**, la valeur que la constante portait (garde offline `etage 1` de
    `test_287r11r1_regles_ciblage_offline.py`, qui FIGE la valeur mesuree a la conversion).

    Unite du summon inconnue du catalogue -> `0` (mirror du `return 0` natif) : le disque de
    `GetSurroundingTiles` se reduit alors a la tuile centre, il n'est jamais fabrique plus large."""
    unit_id = ((GC.ability(SITNW_ID) or {}).get("constants") or {}).get(CONST_SITNW_UNIT_ID.name)
    return _svc_bq.get_unit_max_range(unit_id)


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
    (`AttackTilesForTargetSelector IdunBattleLogic.Entities.DSLSelectors$$AttackTilesForTarget`, qui consulte la config d'arme + la geometrie de tir) est
    l'IDENTITE offline : `possible` est deja le disque de rayon = portee d'arme du summon autour de la
    cible, et aucun modele de cover/ligne de vue n'existe cote port (residu documente) -> `preferred ==
    possible` -> k = min(n, |possible|), rest = n - k.
    ATTENTION : quand `|possible| < n`, l'union native produit des DOUBLONS de tuiles (deux PickRandomly sur le meme
    ensemble) ; le port les elimine (une 2e pose sur une tuile deja occupee par le summon precedent serait
    de toute facon un no-op cote natif). HYPOTHESE flaguee (cas rare : plateau tres encombre)."""
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
    for (col, row) in hexgeo.disk(tpc.col, tpc.row, send_in_the_next_wave_spawned_unit_range()):
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
    (`IdunBattleLogic.Entities.DSLBehaviors$$UseNormalAttackIfAble` -> `UseActiveAbilityBehaviour(actor=@0x180,
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

    # `IdunBattleLogic.Entities.Abilities.Active.Loki.SendInTheNextWaveAbility$$.ctor` :
    #     preset = <TargetingRange statics+0x00>                     # copie de 0x18 octets
    #     TargetingOptions..ctor(&opts, isSelfCasting=0, &preset, forceMeleeTarget=1, 0x4002, 0,0,0)
    #     AActiveAbility..ctor(this, &opts, 1, 0)      # AbilityAttackType.SummonAndAttackTarget
    # FORME 1 « FLAGS DIRECTS » -> le litteral EST le masque.
    #   0x4002 = TargetIsEnemy             (1<<14 = 0x4000)
    #          | TargetMatchesDynamicRule  (1<<1  = 0x0002)          -> somme EXACTE, 0 bit residuel
    #   range = `TargetingRange$$.cctor` statics+0x00 = `{onlyAdjacent = RangedBool.IfNotRangedCaster}`
    #           (aucun `overrideRange`, `useRangeFromConfig` faux) -> RANGE_ADJACENT_IF_MELEE_CASTER.
    #           Yarrick porte une arme `Range = 2` (gameconfig `astraYarrick.weapons[1]`) donc
    #           `UnitExtensions$$IsRanged` est VRAI -> `onlyAdjacent` retombe a faux et la portee vaut
    #           `ExtraRange + 2`. C'est l'i2 mot pour mot : « Select a target within 2 hexes ».
    #   forceMeleeTarget = param_4 = 1 = RangedBool.False (aucun clamp a 1 au contact)
    # ⚠ `constants.range` n'existe pas pour 1016 et le preset ne pose PAS `useRangeFromConfig` :
    # `AActiveAbility$$SetConfigValuesInTargetingOptions` ne touche donc a rien ici.
    # `TargetMatchesDynamicRule` -> PORTE depuis #287-r11-r1 (surcharge ci-dessous).
    # ⚠ LE SLOT ETAIT MAL LU, ET LE « NON RESOLU » VENAIT DE LA. La note precedente disait
    # « slot 0x66 d'`IBattleQuery`, non resolu (aucune lambda du decorateur
    # `RecordedSimulationRequestsBattleQuery` ne l'a donne) » : le decompile du build courant montre
    # `+ 0x67`, et la table de METADONNEE (`data/symbols/<build>/metadata/interface_slots.tsv`, lue
    # dans le champ `slot` d'`Il2CppMethodDefinition`) donne `IBattleQuery 103 GetSurroundingTiles/6`.
    # Chercher une lambda de proxy n'etait pas la bonne voie : la table le dit directement, et elle
    # departage aussi les homonymes (le slot 111 est `GetMinDistance`, PAS `GetDistance`).
    TARGETING_OPTIONS = TargetingOptions(rules=(
          TR.TargetIsEnemy
        | TR.TargetMatchesDynamicRule
    ), range=RANGE_ADJACENT_IF_MELEE_CASTER, force_melee_target=RANGED_BOOL_FALSE)

    def get_dynamic_invalid_target_reason(self, state: "State", caster_id: int,
                                          target_id: Optional[int]) -> int:
        """`IdunBattleLogic.Entities.Abilities.Active.Loki.SendInTheNextWaveAbility$$GetDynamicInvalidTargetReason`
        -- MIRROR du decompile, ligne a ligne (#287-r11-r1) :

            range = GetSpawnedUnitRange();          // battleQuery.GetUnitMaxRange(unitId), slot 171
            tiles = battleQuery.GetSurroundingTiles(targetTiles, range,
                                                    onlyEmptyOrSteppable: 1, onlyWalkable: 1,
                                                    onlyMovable: 0, includeCenter: 1);   // slot 103
            return tiles.Count() < 1 ? 2 : 0;                   // ICollection<ITile>.get_Count, slot 0

        SEMANTIQUE : « la vague suivante doit avoir OU se poser ». Yarrick ne peut pas designer une
        cible entierement encerclee : il faut au moins une tuile VIDE-OU-STEPPABLE et MARCHABLE dans
        le disque de rayon `range` autour d'elle.

        ⚠ `includeCenter = 1` ET `onlyEmptyOrSteppable = 1` VONT ENSEMBLE, et le second est ce qui
        rend le premier inoffensif : le centre est la tuile de la CIBLE, donc occupee, donc rejetee
        par `IsEmptyOrSteppable` -- sauf si la cible est `Steppable`, auquel cas le natif la compte
        VRAIMENT. Retirer le centre « parce qu'il est occupe » aurait ete une simplification FAUSSE.

        ⚠ CE N'EST PAS LE MEME ENSEMBLE QUE `GetSpawnTilesSelector` (l'ExecuteBehaviour), et les
        confondre aurait produit un SUR-refus. Le selecteur de spawn, lui, passe par
        `CanAddUnit(SurroundingTiles(target, includeCenter=0, r))` -- `CanAddUnit` ajoute trois
        rejets (blocker, `NotWalkable`, tuile RESERVEE) et EXCLUT le centre. Le gate de ciblage est
        donc STRICTEMENT PLUS PERMISSIF que ce que l'ability saura utiliser ; il existe une
        configuration ou le cast est LEGAL et ne pose rien (cible `Steppable` seule tuile libre).
        Le natif l'assume ; le port aussi.

        SUBSTRAT : `tile_is_empty_or_steppable` est le mirror deja porte d'`IsEmptyOrSteppable`
        (`runner/abilities/targeting.py`) ; `board.walkable` porte `IsTileValidForList(checkWalkable
        = 1, checkElevation = 0)`. Cible non resolue / board absent -> `0`, la convention permissive
        du module (on ne fabrique pas un refus sur un substrat non mesure)."""
        if target_id is None:
            return 0
        board = state.board
        te = state.get_entity(int(target_id))
        tpc = te.get_component(PositionComponent) if te is not None else None
        if board is None or tpc is None:
            return 0
        tpos = (tpc.col, tpc.row)
        tiles = battle_query.get_surrounding_tiles(
            tpos, radius=send_in_the_next_wave_spawned_unit_range(),
            include_center=True,                               # `includeCenter = 1`
            check_walkable=True,                               # `onlyWalkable = 1`
            only_empty_or_steppable=True,                      # `onlyEmptyOrSteppable = 1`
            empty_or_steppable_at=lambda p: tile_is_empty_or_steppable(state, p),
            walkable_at=lambda p: board.walkable(board.id_at(p[0], p[1])),
            elevation_at=lambda p: board.elevation(board.id_at(p[0], p[1])),
            tile_exists=lambda p: board.id_at(p[0], p[1]) is not None)
        return 0 if len(tiles) >= 1 else int(TR.TargetMatchesDynamicRule)

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

    # `IdunBattleLogic.Entities.Abilities.Active.Loki.MalleusRocketLauncherAbility$$.ctor` :
    #     preset = <TargetingRange statics+0x48>                     # copie de 0x18 octets
    #     TargetingOptions..ctor(&opts, isSelfCasting=0, &preset, forceMeleeTarget=1,
    #                            0x10000040000040, 0, 0, 0)
    #     AActiveAbility..ctor(this, &opts, 2, 0)                    # AbilityAttackType.Others
    # FORME 1 « FLAGS DIRECTS » -> le litteral EST le masque.
    #   0x10000040000040 = CasterHas2TurnsLeft (1<<52 = 0x10000000000000)
    #                    | AllowNullCasterTile (1<<30 = 0x000000040000000)
    #                    | TargetIsTile        (1<<6  = 0x000000000000040)
    #                                                          -> somme EXACTE, 0 bit residuel
    #   range = `TargetingRange$$.cctor` statics+0x48 = `{onlyAdjacent = RangedBool.False,
    #           useWholeBoard = true}` -> RANGE_WHOLE_BOARD : le filtre statique NE TESTE PAS la
    #           portee (« Marks a hex on the battlefield », i2).
    #   forceMeleeTarget = param_4 = 1 = RangedBool.False
    # ⚠ PIEGE ECARTE : la config 1142 porte bien un `constants.range = 2`, mais le preset ne pose PAS
    # `useRangeFromConfig` -> `AActiveAbility$$SetConfigValuesInTargetingOptions` ne le recopie pas.
    # Ce `range` sert au barrage de PHASE 2 (`MalleusRocketLauncher_AttackAbility`), pas au ciblage.
    # Les deux bits CASTER sont des regles de `IdunBattle.Core.Services.TargetingQuery$$GetInvalidCasterReason`
    # (cf. `targeting.py::get_invalid_caster_reason`), et leur sort DIFFERE :
    #   * `AllowNullCasterTile` est une PERMISSION (elle DESARME le refus 0x40000000 « caster sans
    #     tuile ») -- indispensable ici, la MoW `astraOrdnanceBattery` n'a AUCUNE position ; le port
    #     porte le refus depuis #366-r1 et sort par le meme premier terme que le natif ;
    #   * `CasterHas2TurnsLeft` refuse quand le slot **0x1b** d'`IBattleQuery` rend faux sur
    #     `(caster, 2)`. **PORTEE depuis #287-r11-r1-r1.** Ce commentaire ecrivait `0x1a` et en
    #     concluait « slot non resolu » : c'etait un DECALAGE DE UN -- `0x1a` = 26
    #     `ShouldPlayerSkipTurn` publie **1** parametre, quand le call-site en passe deux. Le slot
    #     0x1b = 27 est `IdunBattle.Core.Services.BattleQuery$$HasMinimumRemainingTurns` (arite 2),
    #     dont le premier bras rend `true` des que `BC.Victory.VictoryConditions` ne porte pas
    #     `MainPlayerRoundLimitation` -- ce qui est le cas de la seed versionnee, donc la regle est
    #     INERTE sur les runners d'arene sans qu'aucune convention permissive n'y soit pour rien.
    TARGETING_OPTIONS = TargetingOptions(rules=(
          TR.CasterHas2TurnsLeft
        | TR.AllowNullCasterTile
        | TR.TargetIsTile
    ), range=RANGE_WHOLE_BOARD, force_melee_target=RANGED_BOOL_FALSE)

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        # #287-r14 RESOLUTION DE CIBLE -- `IdunBattle.Core.Services.TargetingQuery$$GetActualTarget`
        # via le slot 16 d'`IActiveAbility` : pour un masque `TargetIsTile`, le role `target` du
        # natif est TOUJOURS l'entite-TUILE, que l'appelant ait passe la tuile ou son occupant.
        # IDEMPOTENT (`GetMainTile(<tuile>)` rend la tuile) -> inerte quand `AbilityHandler` a
        # deja resolu, mordant sur tout appel DIRECT (tests de migration, probes).
        target_id = self.get_actual_target(state, caster_id, target_id)
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
#
# TRI PORTE (#165) : `SortTilesByUtilityForSummon(sel, 7, owner@0x148)` -> surcharge
# `IdunBattleLogic.Entities.DSLSelectors$$SortTilesByUtilityForSummon(dsl, tiles, int, parent)` qui
# construit `AllAliveMachinesSelector` + `UtilityDefinition(7 = Tile)` et delegue a
# `IdunBattleLogic.Entities.DSLSelectors$$SortTilesByUtility` ->
# `IdunBattle.Entities.Selectors.SortTilesByUtilitySelector$$Select` = tri DECROISSANT **stable** par
# `IdunBattleLogic.AI.Utilities.UtilityDecider$$CalculateUtility` sur le composite `Tile(7)`. C'est
# EXACTEMENT le sortilege deja porte et LIVE-VALIDE pour le placement des summons
# (`runner/operations/spawn.py::_sort_tiles_by_utility_for_summon`, case-130 SS5) : les deux appellent
# desormais le FOYER UNIQUE `engine/utilities/tile.py::sort_tiles_by_utility`. Le referent `owner@0x148`
# est le `parent` du `UtilityMovementCase` : case-205 a etabli que le `dc.unit` de cette surcharge vaut
# **null**, donc `get_IsSpawning` (= unit null ET parent non nul) est VRAI ici. Le port le transmet en
# `parent_id=` ; seule la PRESENCE du parent compte (ici une MoW SANS POSITION).
# =================================================================================================== #

FORWARD_SPOTTER_ID = "ForwardSpotter"
FS_CONST_NR_OF_SUMMONS = AbilityConstantType.nrOfSummons        # GetNumberConstant(0x10) -> "nrOfSummons" = 1
FS_CONST_UNIT_ID = 0x00              # GetStringConstant(0)    -> "unitId"      = astraSmnGuardsman


def forward_spotter_num_summons() -> int:
    """`GetNumberConstant(config, 0x10)` = `nrOfSummons` (CONSTANTE, hors niveau) de 1143."""
    consts = (GC.ability(FORWARD_SPOTTER_ID) or {}).get("constants") or {}
    return int(consts.get("nrOfSummons") or 0)


def forward_spotter_pick_tiles(state: "State", target_id: Optional[int], n: int,
                               owner_id: Optional[int] = None) -> list:
    """MIRROR de `IdunBattleLogic.Entities.Abilities.Active.Loki.ForwardSpotterAbility$$PickTiles`
    (cf. le bloc ci-dessus) : `First(SortTilesByUtilityForSummon(CanAddUnit(AdjacentTiles(target))
    .Otherwise-filtre, 7, owner), nrOfSummons)`.

    Rendu = les `n` MEILLEURES tuiles LIBRES (walkable + inoccupees par un vivant) ADJACENTES a la
    tuile ciblee, au sens du composite `Tile(7)` (#165 : le tri EST porte, cf. le foyer
    `engine/utilities/tile.py::sort_tiles_by_utility`). Le tri etant STABLE, les egalites (carte plate)
    sont tranchees par l'ordre du SELECTEUR SOURCE = `AdjacentTilesSelector$$Select` ->
    `BattleQuery$$GetAdjacentTiles`, donc `board.neighbours_native` (liste d'adjacence STOCKEE, ni
    triee ni symetrisee ; ordre etabli case-130 SS5 / #117 / FragBomb) -- et NON `board.neighbours`
    (ids tries) que ce port utilisait. `target_id` = une UNITE **ALLIEE** (masque `0x40000422`, bit
    `TargetIsFriendly` -- confirme live : `abilityTargets` ne rend que des unites de la team du
    caster ; cf. `ForwardSpotterAbility$$GetDynamicInvalidTargetReason` : `IsUnit(target) &&
    target != caster`)."""
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
    free = [t for t in board.neighbours_native(tid) if t not in occ and board.walkable(t)]
    # PAS d'`unit_id`, mais le `parent` (`owner@0x148`) : case-205 a etabli au decompile que le
    # `dc.unit` de `SortTilesByUtilityForSummon` vaut **null** (et non « un ENSEMBLE d'unites »
    # comme le supposait le residu case-165b). Le foyer produit alors le ctx `{"is_spawning": True}`
    # = `IdunBattle.AI.Utilities.UtilityMovementCase$$get_IsSpawning`, et chaque feuille applique SA
    # degradation nommee. Ici `owner@0x148` est une MoW SANS position : seule sa PRESENCE compte.
    return sort_tiles_by_utility(state, free,
                                 parent_id=owner_id)[:max(0, int(n))]   # ForSummon + First(n)


def forward_spotter_tree(tiles: list) -> Spawn:
    """Arbre de `IdunBattleLogic.Entities.Abilities.Active.Loki.ForwardSpotterAbility$$ExecuteBehaviour` :
    UN noeud `Spawn` (owner = caster@0x160, `WithStatsFromConfig`) dont les options portent le
    sous-behaviour ON-APPEARANCE `PerformAIAttack(ActiveTarget@0x180)` -- le Cadian fraichement pose
    execute immediatement une attaque IA. Les tuiles sont le collapse de `PickTiles` (cf. ci-dessus).

    ⚠ Le on-appearance est un `IdunBattleLogic.Entities.DSLBehaviors$$PerformAIAttack` (routine IA = un TOUR
    complet du summon), PAS un `PerformAIAttackFromCurrentPosition` ni un `UseNormalAttackIfAble(target)`
    dirige (contraste SendInTheNextWave) : le natif ne lui passe QUE l'acteur (`@0x180`), aucune cible.
    Le decompile donne `PerformAIAttack(ActiveTarget@0x180, 1, 0, 0, 0)` -> `+0x70 allowMoveAction = 1`,
    `+0x78 moveAmount = null` : la feuille les porte explicitement (i2 « The Cadian Guardsman immediately
    takes a turn », a opposer au « cannot move this turn » des noeuds FromCurrentPosition). Depuis #348
    l'observable DIFFERE bien : le guardsman s'APPROCHE avant de frapper. C'est d'ailleurs par CE
    porteur que l'approche est confrontee au live (`probe_348_ai_approach.py` : son masque
    `TargetIsFriendly` fait naitre le summon adjacent a un ALLIE choisi, donc la distance
    spawn<->ennemi est pilotable au hex pres)."""
    return Spawn(FixedTileIds(tiles), FORWARD_SPOTTER_ID,
                 on_appearance=PerformAIAttack(ActiveTarget(), allow_move_action=True,
                                               move_amount=None))


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

    # `IdunBattleLogic.Entities.Abilities.Active.Loki.ForwardSpotterAbility$$.ctor` :
    #     preset = <TargetingRange statics+0x48>                     # copie de 0x18 octets
    #     TargetingOptions..ctor(&opts, isSelfCasting=0, &preset, forceMeleeTarget=1, 0x40000422,
    #                            0, 0, 0)
    #     AActiveAbility..ctor(this, &opts, 2, 0)                    # AbilityAttackType.Others
    # FORME 1 « FLAGS DIRECTS » -> le litteral EST le masque.
    #   0x40000422 = AllowNullCasterTile      (1<<30 = 0x40000000)
    #              | TargetIsFriendly         (1<<10 = 0x00000400)
    #              | TargetHasFreeAdjacentTile(1<<5  = 0x00000020)
    #              | TargetMatchesDynamicRule (1<<1  = 0x00000002)
    #                                                          -> somme EXACTE, 0 bit residuel
    #   range = `TargetingRange$$.cctor` statics+0x48 = `{onlyAdjacent = RangedBool.False,
    #           useWholeBoard = true}` -> RANGE_WHOLE_BOARD (MEME preset que 1142, l'autre ability de
    #           cette MoW) : aucun test de portee, l'i2 ne mentionne d'ailleurs aucune distance.
    #   forceMeleeTarget = param_4 = 1 = RangedBool.False
    # Les trois bits CIBLE tombent mot pour mot sur l'i2 « Summons a Cadian Guardsman in a hex
    # ADJACENT to the TARGETED FRIENDLY UNIT » : `TargetIsFriendly` (le camp), `TargetHasFreeAdjacentTile`
    # (il faut une tuile libre au contact pour y poser le summon -- meme predicat que le
    # `CanAddUnit(AdjacentTiles(target))` de `forward_spotter_pick_tiles`), `TargetMatchesDynamicRule`
    # (la cible doit etre une UNITE, cf. `get_dynamic_invalid_target_reason` ci-dessous).
    # `AllowNullCasterTile` est la PERMISSION qui rend le cast possible depuis une MoW sans position
    # (regle CASTER `IdunBattle.Core.Services.TargetingQuery$$GetInvalidCasterReason`, non portee).
    TARGETING_OPTIONS = TargetingOptions(rules=(
          TR.AllowNullCasterTile
        | TR.TargetIsFriendly
        | TR.TargetHasFreeAdjacentTile
        | TR.TargetMatchesDynamicRule
    ), range=RANGE_WHOLE_BOARD, force_melee_target=RANGED_BOOL_FALSE)

    def get_dynamic_invalid_target_reason(self, state: "State", caster_id: int,
                                          target_id: Optional[int]) -> int:
        """`IdunBattleLogic.Entities.Abilities.Active.Loki.ForwardSpotterAbility$$GetDynamicInvalidTargetReason`
        -- MIRROR 1:1 du decompile, qui tient en trois lignes :

            if (EntityExtensions.IsUnit(target)) return caster == target;
            return true;

        Le retour est un `TargetingRule` : la comparaison booleenne s'y elargit en le litteral `1`,
        c'est-a-dire `TargetingRule.ValidRequest` -- le natif REUTILISE cette valeur comme CODE DE
        REFUS (exactement le meme quirk que la branche `TargetIsTile` du filtre statique, cf.
        l'en-tete de `targeting.py`). Donc REFUS des que la cible n'est pas une UNITE (une TUILE, la
        MoW elle-meme) ou qu'elle EST le caster ; 0 sinon.

        ⚠ LE `target` QUE RECOIT CETTE REGLE EST DEJA RESOLU. Le filtre statique invoque la
        regle-delegue avec `pcVar12`, c'est-a-dire `IdunBattle.Entities.UnitExtensions$$GetUnit(target,
        state)` -- sur une TUILE, l'OCCUPANT. Le port passe l'id BRUT, d'ou l'appel a
        `targeting.unit_of_entity`, qui EST ce `GetUnit`. MESURE (#253) : caste sur la TUILE d'un
        allie, le natif rend `0` (VALIDE) ; sans cette resolution le port y posait un FAUX REFUS.
        La branche `uid is None` est donc inerte en pratique -- le preambule `TargetIsUnit` de la
        cascade l'a deja refusee plus haut --, mais elle est ecrite parce que le natif l'ecrit.

        La clause `caster == target` ne peut pas mordre pour ce porteur (le caster est une MACHINE,
        la cible une unite) : elle est ecrite parce que le natif l'ecrit."""
        uid = unit_of_entity(state, target_id)
        if uid is None:
            return int(TR.ValidRequest)              # `!IsUnit(target)` -> `return true` = 1
        return int(TR.ValidRequest) if uid == int(caster_id) else 0

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        if target_id is None or state.get_entity(caster_id) is None:
            return None
        n = forward_spotter_num_summons()
        tiles = forward_spotter_pick_tiles(state, target_id, n, owner_id=caster_id)
        ectx = ExecutionContext(state=state, rng=state.rng)
        forward_spotter_tree(tiles).execute(
            entities_from_state(state, caster_id, target_id), ectx)
        spawned = [p["unit"] for nm, p in ectx.emitted if nm == "SpawnUnit"]
        attacks = [p for nm, p in ectx.emitted if nm == "PerformAIAttack"]
        return {"spawned": spawned, "attacks": attacks, "tiles": tiles, "count": n, "dsl": True}


# =================================================================================================== #
# FragBomb (1017, `astraBullgryn` -- « Kut Skoden », HERO) -- patron DAMAGE(Blast) main + splash, mais
# plombe par un `SortedAttackSeries` (et NON par un `op_Addition` de deux `AttackWithAttackDamage`).
# =================================================================================================== #

FRAG_BOMB_ID = "FragBomb"
FB_CONST_NR_OF_HITS = AbilityConstantType.nrOfHits       # GetNumberConstant(0x2f) -> "nrOfHits"   = 6  (volet principal)
FB_CONST_NR_OF_HITS_2 = AbilityConstantType.nrOfHits_2     # GetNumberConstant(0x32) -> "nrOfHits_2" = 3  (volet splash)


def frag_bomb_tree() -> AtomicGroup:
    """Arbre de `IdunBattleLogic.Entities.Abilities.Active.Loki.FragBombAbility$$ExecuteBehaviour`
    (id 1017, `astraBullgryn`) -- MIRROR 1:1 du DECOMPILE :

        profile = Direct( GetDamageProfile(config, 0) )                          # Blast
        h1      = GetNumberConstant(config, 0x2f)                                # nrOfHits   = 6
        h2      = GetNumberConstant(config, 0x32)                                # nrOfHits_2 = 3
        splash  = AdjacentUnits(Target@0x178, 0, 3) - Caster@0x160
                  # = Units(AdjacentTiles(target), 0, 3) - target - caster   [IdunBattleLogic.Entities.DSLSelectors$$AdjacentUnits]
        dmg     = MinMaxDamage(this, entities)                                   # minDmg/maxDmg[level]
        main    = AttackDamage(Caster@0x160, ActiveTarget@0x180, dmg, profile, Get(h1), <AbilityOrEffect>)
        splashA = AttackDamage(Caster@0x160, ActiveTarget@0x180, dmg, profile, Get(h2), <AbilityOrEffect>)
        ExecuteAtomic( SortedAttackSeries(Caster@0x160, Units(Target@0x178,1,1), main,
                                          splash, splashA, <AbilityOrEffect>), entities, 0x43 )

    TROIS points de fidelite qui distinguent ce patron du splash « classique » (Stikkbomb/PlasmaGrenade) :

    1. **`SortedAttackSeries`, pas `op_Addition`** : la factory native n'est PAS
       `AttackWithAttackDamage(selecteur-multi)`. Le noeud regroupe les attaques PAR CIBLE puis les joue
       dans l'ORDRE D'INSERTION -- il n'y a **AUCUN `OrderBy`** (contraste
       `IdunBattle.Entities.Behaviours.AttackBehaviour$$Execute`, qui trie des que `Count > 1`). L'ordre
       des cibles splash, donc la sequence de tirages `state.rng`, est celui du SELECTEUR.
    2. **Ordre du selecteur = ordre NATIF du voisinage** (`AdjacentTiles` -> `Board.neighbours_native`
       = table de directions de `BattleQuery$$GetAdjacentTiles`), pas l'ordre trie par id. C'est deja
       la loi INCONDITIONNELLE d'`AdjacentTiles` (R28-1) ; ce call-site en est le 2e confront live.
       MESURE (probe_fragbomb_splash, MC1_67, cible sur la tuile 44, voisins natifs
       `[45, 53, 52, 43, 34, 35]`) : coups splash live dans l'ordre `53, 52, 43, 35` = l'ordre natif
       prive du caster (45) et de la tuile vide (34) ; l'ordre trie aurait donne `35, 43, 52, 53`.
    3. **FRIENDLY-FIRE** : le selecteur est `AdjacentUnits` BRUT (aucun wrapper `Enemies(...)`), moins la
       cible et le CASTER -- exactement l'i2 (« ALL units adjacent to the target hex, except Kut Skoden
       himself »). MESURE LIVE : l'allie `astraCreed` adjacent a la cible a bien encaisse 3 coups.

    Volet principal et volet splash PARTAGENT la plage `MinMaxDamage(minDmg/maxDmg)` et le profil
    `GetDamageProfile(0)` = Blast (la config 1017 n'a AUCUNE variable `_2`) ; seule la constante de coups
    differe. `attackRangeType = Melee` -> `is_melee=True`. Factory `AttackDamage` = `AttackDamageBehaviour`
    NU (famille ATTACK, crit/block) -> `native_factory="attack"` (defaut)."""
    main_sel = Units(Target())                                       # `Units(Target@0x178, 1, 1)`
    splash_sel = Sub(Sub(Units(AdjacentTiles(Target())), Target()), Caster())
    main = AttackWithAttackDamage(ActiveTarget(), FRAG_BOMB_ID, "Blast", is_melee=True,
                                  ability_type=int(ActiveAbilityType.FragBomb))
    splash = AttackWithAttackDamage(ActiveTarget(), FRAG_BOMB_ID, "Blast", is_melee=True,
                                    hits_key="nrOfHits_2",
                                    ability_type=int(ActiveAbilityType.FragBomb))
    return AtomicGroup(SortedAttackSeries([(main_sel, main), (splash_sel, splash)],
                                          # `<AbilityOrEffect>` = 6e argument de la factory, LU au
                                          # call-site cite ci-dessus (#512-r2).
                                          ability_type=int(ActiveAbilityType.FragBomb)))


class FragBombAbility(ActiveAbility):
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.FragBombAbility$$ExecuteBehaviour` (id 1017,
    `astraBullgryn` « Kut Skoden », Astra Militarum, HERO). Cast UNIT-TARGET, MELEE (cible adjacente).

    Kit gameconfig 1017 : `damageProfile=Blast`, `nrOfHits=6`, `nrOfHits_2=3`, `minDmg`/`maxDmg`[level]
    (rarity-affected). AUCUNE variable `_2` -> plage de degat PARTAGEE entre la cible et le splash.

    OBSERVABLE (mesure live, runner MC1_67, cible entouree) : la cible encaisse **6** coups Blast ;
    **CHAQUE** unite adjacente a la tuile ciblee -- ALLIES DU CASTER COMPRIS, caster exclu -- en encaisse
    **3**. AVANT ce port, 1017 etait absente d'`ABILITY_CLASSES` : `visit_ActiveAbilityMessage` rendait
    `ported:False` -> **0 degat, aucune erreur** (divergence d'etat SILENCIEUSE de 6 + 3xN coups).

    Flags de tour : defauts base (1017 absente des overrides) -> termine le tour + ActiveAbilityUsed.
    Retour : {main_attack, splash, order, dsl}."""
    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.FragBomb)   # 1017
    ABILITY_ID = FRAG_BOMB_ID

    # `IdunBattleLogic.Entities.Abilities.Active.Loki.FragBombAbility$$.ctor` :
    #     preset = <TargetingRange statics+0x30>                     # copie de 0x18 octets
    #     TargetingOptions..ctor(&opts, 0, &preset, 1, 0x80040, 0, 0)
    # Overload « FLAGS DIRECTS » a 7 arguments (`IdunBattle.Core.Services.TargetingOptions$$.ctor`,
    # celui qui ecrit `+0x28 <- param_5` SANS OR) -> le litteral **EST** le masque effectif. Ce n'est
    # PAS l'overload piege « PRESET + flags » a 3 arguments, dont le corps fait `+0x28 = flags |
    # preset[+0x28]` : celui-ci ne recoit qu'un `TargetingRange` de 0x18 octets, qui n'a pas de +0x28.
    #   0x80040 = TargetIsTile | TargetTileHasEnemyUnit
    #   forceMeleeTarget = param_4 = 1 = RangedBool.False
    #   range = `TargetingRange$$.cctor` statics+0x30 = onlyAdjacent + overrideRange=1 -> RANGE_ADJACENT,
    #           coherent avec `attackRangeType = Melee` de la config 1017.
    TARGETING_OPTIONS = TargetingOptions(rules=(
          TR.TargetIsTile
        | TR.TargetTileHasEnemyUnit
    ), range=RANGE_ADJACENT, force_melee_target=RANGED_BOOL_FALSE)

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        # #287-r14 RESOLUTION DE CIBLE -- `IdunBattle.Core.Services.TargetingQuery$$GetActualTarget`
        # via le slot 16 d'`IActiveAbility` : pour un masque `TargetIsTile`, le role `target` du
        # natif est TOUJOURS l'entite-TUILE, que l'appelant ait passe la tuile ou son occupant.
        # IDEMPOTENT (`GetMainTile(<tuile>)` rend la tuile) -> inerte quand `AbilityHandler` a
        # deja resolu, mordant sur tout appel DIRECT (tests de migration, probes).
        target_id = self.get_actual_target(state, caster_id, target_id)
        if target_id is None:
            return None
        ectx = ExecutionContext(state=state, rng=state.rng)
        entities = entities_from_state(state, caster_id, target_id)
        # VENTILATION du diagnostic (aucun effet sur la mutation) : la cible PRINCIPALE est ce que
        # rend le selecteur natif du 1er groupe, `Units(Target@0x178, 1, 1)` -- PAS `target_id`, qui
        # est une TUILE des que le cast est tile-target (`TargetIsTile` au masque, et le natif y met
        # l'entite-tuile). Comparer les cibles emises a `target_id` rangeait alors la cible
        # principale dans `splash` et rendait `main_attack: None`, alors que les COUPS, eux, etaient
        # deja exacts (#287-r12). Evalue AVANT l'arbre : apres, la cible peut etre morte et la tuile
        # vide. `Units` ne consomme aucun tirage.
        main_uid = next((u.get("id") for u in Units(Target()).evaluate(entities)), None)
        frag_bomb_tree().execute(entities, ectx)
        atks = [p for n, p in ectx.emitted if n == "AttackWithAttackDamage"]
        main = next((p["attack"] for p in atks if p.get("target") == main_uid), None)
        splash = [{"target": p["target"], "attack": p["attack"]}
                  for p in atks if p.get("target") != main_uid]
        order = next((p["order"] for n, p in ectx.emitted if n == "SortedAttackSeries"), [])
        return {"ability": FRAG_BOMB_ID, "caster": caster_id, "target": target_id,
                "main_attack": main, "splash": splash, "order": order, "dsl": True}


# =================================================================================================== #
# BasiliskBarrage (1026, `astraOrdnance` -- « Thaddeus Noble », HERO) -- BARRAGE d'obus sur des TUILES.
# Patron unique du lot : les cibles ne sont pas des unites mais des TUILES tirees au sort, en TROIS
# tranches (guaranteed / maybe / miss) dont les cardinaux dependent du nb de tours entames par le caster.
# =================================================================================================== #

BASILISK_ID = "BasiliskBarrage"
BB_CONST_NR_OF_PROJECTILES = AbilityConstantType.nrOfProjectiles     # GetNumberConstant(0x1f) -> "nrOfProjectiles"   = 5 (total)
BB_CONST_NR_OF_PROJECTILES_2 = AbilityConstantType.nrOfProjectiles_2   # GetNumberConstant(0x38) -> "nrOfProjectiles_2" = 3
BB_CONST_NR_OF_HITS = AbilityConstantType.nrOfHits            # GetNumberConstant(0x2f) -> "nrOfHits"          = 2 (par obus)
# `PickRandomly(..., allowRepeat=1, maxRepeats=0x7fffffff)` : les TROIS tirages d'obus de 1026 passent
# ces litteraux (contraste Fragstorm `0`/`0x7fffffff`) -> pool JAMAIS retreci, doublons possibles.
BB_MAX_REPEATS = 0x7fffffff


def basilisk_num_shells(state: "State", caster_id: int) -> tuple:
    """`BasiliskBarrageAbility$$GetNumShells{Guaranteed,Miss,Maybe}` -- MIRROR des trois formules :

        total      = Direct( GetNumberConstant(0x1f) = nrOfProjectiles )                # $$GetNumShellsTotal
        guaranteed = Min( Max( Zero@0xb8, Difference( StatAmount(Caster@0x160, 0xc = TurnsStarted),
                                                      One@0xc0 ) ),
                          total )                                                       # $$GetNumShellsGuaranteed
        miss       = Max( Zero@0xb8, Difference( Difference( total,
                                                             Direct(GetNumberConstant(0x38)
                                                                    = nrOfProjectiles_2) ),
                                                 guaranteed ) )                         # $$GetNumShellsMiss
        maybe      = Max( Zero@0xb8, Difference( total, Sum(guaranteed, miss) ) )       # $$GetNumShellsMaybe

    (`DSLFactory@0xb8` = `Direct(0)` et `@0xc0` = `Direct(1)`, poses par
    `IdunBattleLogic.Entities.DSLFactory$$.ctor` -- LUS, pas devines.)

    Soit, avec la config 1026 (`nrOfProjectiles=5`, `nrOfProjectiles_2=3`) : `guaranteed` = nb de ROUNDS
    TERMINES par le caster (`TurnsStarted - 1`, plafonne a 5), `miss` = `max(0, 2 - guaranteed)`,
    `maybe` = le reste. C'est exactement l'i2 : « {nrOfProjectiles_2} randomly hit the target hex or
    surrounding hexes and the remaining 2 hit the hexes surrounding those. For each round that has ended,
    1 more of the shells hits the target hex, starting with the shells hitting the outer hexes. »

    Rend `(guaranteed, maybe, miss, total)`.

    ⚠ FOYER PARTAGE (#1026-r1) : le CALCUL vit dans `basilisk_num_shells_from_turns` ci-dessous,
    parce que la face DECISION (`playbook/basilisk_barrage.py`) evalue les MEMES trois formules
    natives sur une `Scene` -- qui n'a pas de `State`, mais publie `turns_started(uid)`. Cette
    fonction-ci ne garde que la LECTURE de la stat depuis l'ECS. Forker le calcul est le vice que
    #197 et #950-r2 ont paye."""
    ce = state.get_entity(caster_id)
    csc = ce.get_component(StatsComponent) if ce is not None else None
    cctx = csc.ctx if csc is not None else None
    turns = int((cctx.stat(StatType.TURNS_STARTED) if cctx is not None else 0) or 0)
    return basilisk_num_shells_from_turns(turns)


def basilisk_num_shells_from_turns(turns_started: int) -> tuple:
    """Les TROIS formules de `BasiliskBarrageAbility$$GetNumShells{Guaranteed,Miss,Maybe}`, a partir
    du SEUL `StatAmount(Caster@0x160, 0xc = TurnsStarted)` qu'elles lisent.

    Foyer UNIQUE des deux faces (cf. `basilisk_num_shells` pour le decompile terme a terme) :
    la face COMBAT lit la stat sur le `StatsComponent` de l'ECS, la face DECISION sur
    `Scene.turns_started(uid)`. Le calcul, lui, ne peut exister qu'a un seul endroit.

    Rend `(guaranteed, maybe, miss, total)`."""
    consts = (GC.ability(BASILISK_ID) or {}).get("constants") or {}
    total = int(consts.get("nrOfProjectiles") or 0)
    second = int(consts.get("nrOfProjectiles_2") or 0)
    turns = int(turns_started or 0)
    guaranteed = min(max(0, turns - 1), total)
    miss = max(0, (total - second) - guaranteed)
    maybe = max(0, total - (guaranteed + miss))
    return guaranteed, maybe, miss, total


def basilisk_tiles_at_distance(state: "State", pos: tuple, distance: int) -> list:
    """`IdunBattleLogic.Entities.DSLSelectors$$TilesAtDistance(source, d)` ->
    `IdunBattle.Entities.Selectors.TilesAtDistanceSelector$$Select` -> slot 0x63 =
    `IdunBattle.Core.Services.BattleQuery$$GetTilesAtDistance(tile, d, false)` :

        surrounding = GetSurroundingTiles(tile, d, requireEmptyOrSteppable=false, checkWalkable=0,
                                          unitFilter=0, includeSelf=1)
        return surrounding.Where(t => PositionComponent.Distance(t, tile) == d)   # anneau EXACT

    -> disque cube puis filtre `== d`. **L'ORDRE compte** (il decide quelle tuile `ElementAt(idx)` du
    `PickRandomly` designe) et c'est celui de la triple boucle cube ASCENDANTE de
    `IdunBattle.Core.Services.TileQuery.u003CIterateSurroundingTilesu003Ed__6$$MoveNext`, deja mirroree
    par `battle_query.get_surrounding_tiles`. Les tuiles OCCUPEES restent dans le pool
    (`requireEmptyOrSteppable=false`) -- confirme live (des obus tombent sur des tuiles habitees).

    CONFRONTE LIVE (probe_basilisk_shell_rng, 7 seeds, MC1_67) : cet ordre est le SEUL des 24
    permutations du pool ring-2 qui reproduise 7/7 les tuiles d'impact rejouees depuis le MT capture.

    ⚠ FILTRE DU POOL = `isWall`, **PAS** `walkable`. `IsTileValidForList(tile, ref, checkWalkable=0, 0)`
    se reduit, dans cette branche, a `TileComponent+0x41 == 0 && TileComponent+0x40 == 0` : ni la porte
    `IsWalkable` (occupation + mur) ni la porte d'elevation ne s'appliquent.

    ⚠ ATTRIBUTION DES DEUX OCTETS CORRIGEE (#967-r10) -- elle etait INVERSEE ici, et le comportement
    ci-dessous (filtrer `isWall`) etait juste par ailleurs : c'est la PROSE qui designait le mauvais
    champ. Les deux octets sont adjacents, donc les confondre ne leve rien ; ils ont ete LUS :
      * `+0x41` = **IsWall** -- `IdunBattle.Entities.Pathfinding.FlyPathfinder$$IsAnyAdjacentTileWall`
        rend `true` sur `*(char*)(comp+0x41) != 0`, et rien d'autre. C'est DONC lui que la cle
        `isWall` du `boardGraph` alimente, et lui que ce filtre porte.
      * `+0x40` = **IsInFogOfWar** -- `IdunBattle.Entities.TileExtensions$$IsInFogOfWar` rend
        EXACTEMENT `*(byte*)(comp+0x40)`. Celui-la n'est PAS filtre ici (residu #967-r11).
    (`walkable`, lui, est `BattleQuery.IsWalkableTile` = mur **ET** occupation : trop restrictif ici.)

    GROUND TRUTH : board `C3_01` a 14 tuiles `walkable=false` / `isWall=false`, et le
    LIVE fait tomber un obus sur l'une d'elles (tuile 41, ring-1 de la cible) -- un filtre `walkable`
    l'excluait du pool et DESYNCHRONISAIT tout le tirage.

    ⚠ FOYER PARTAGE (#1026-r1) : le corps vit dans `basilisk_tiles_at_distance_on_board`, parce que
    la face DECISION evalue le MEME `TilesAtDistance` sur `Scene.board`. Mesure : ce noeud ne lit du
    `State` QUE `state.board` -- rien d'autre. Le partage est donc un simple changement de porte
    d'entree, pas une reimplementation."""
    return basilisk_tiles_at_distance_on_board(state.board, pos, distance)


def basilisk_tiles_at_distance_on_board(board, pos: tuple, distance: int) -> list:
    """`TilesAtDistance(source, d)` sur un BOARD -- foyer UNIQUE des deux faces.

    Cf. `basilisk_tiles_at_distance` pour le decompile, l'ordre cube natif et les deux pieges
    (`isWall` et non `walkable` ; l'ordre est load-bearing pour le tirage de la face COMBAT)."""
    if board is None or pos is None:
        return []
    def _exists(p):
        return board.id_at(p[0], p[1]) is not None
    def _not_wall(p):
        tid = board.id_at(p[0], p[1])
        return tid is not None and not bool(board.by_id.get(tid, {}).get("isWall"))
    out = []
    for p in battle_query.get_surrounding_tiles(pos, radius=int(distance), include_center=True,
                                                check_walkable=False, walkable_at=_not_wall,
                                                tile_exists=_exists):
        if hexgeo.distance(pos, p) != int(distance):
            continue
        tid = board.id_at(p[0], p[1])
        if tid is not None:
            out.append(tid)
    return out


def basilisk_shell_tiles(state: "State", caster_id: int, target_id: int) -> list:
    """COLLAPSE des TROIS `PickRandomly` de
    `IdunBattleLogic.Entities.Abilities.Active.Loki.BasiliskBarrageAbility$$ExecuteBehaviour` -- MIRROR :

        missTiles  = TilesAtDistance(Target@0x178, Direct(2))                    # $$GetPossibleTargetTilesMiss
        maybeTiles = TargetTiles@0x190 op_Addition TilesAtDistance(Target@0x178, Direct(1))
                                                                                 # $$GetPossibleTargetTilesMaybe
        guarTiles  = TargetTiles@0x190                                            # $$GetPossibleTargetTileGuaranteed
        sel = ( Cache(PickRandomly(missTiles,  numShellsMiss,       1, 0x7fffffff, false))
              + Cache(PickRandomly(maybeTiles, numShellsMaybe,      1, 0x7fffffff, false)) )
              + Cache(PickRandomly(guarTiles,  numShellsGuaranteed, 1, 0x7fffffff, false))

    L'ORDRE des tirages (miss, PUIS maybe, PUIS guaranteed) est celui de l'`op_Addition`
    `(miss + maybe) + guar`, evalue de gauche a droite -- il fixe la sequence `state.rng`.
    CONFRONTE LIVE (probe_basilisk_shell_rng, 7 seeds) : des 6 ordres possibles x 3 hypotheses de pool,
    seul ce couple (ordre miss/maybe/guar + pools dans l'ordre cube natif, `TargetTiles` EN TETE du pool
    « maybe ») rejoue 7/7 les tuiles d'impact depuis le MT capture avant le cast.

    Le tirage vit ICI (et non dans un noeud SELECTEUR) parce que seul le niveau ability voit `state.rng`
    -- meme doctrine de collapse que `send_in_the_next_wave_spawn_tiles` / le `pick_n` des feuilles.
    `Cache` = no-op offline (chaque pool n'est resolu qu'une fois).

    Rend la liste des tuiles d'IMPACT (une entree par obus, DOUBLONS COMPRIS : `allowRepeat=1`).

    ⚠ `target@0x178` est une ENTITE, et pour 1026 (`TargetIsTile` au masque) le natif y met
    l'entite-TUILE : la normalisation passe donc par le foyer `main_tile_id`
    (`IdunBattle.Entities.EntityExtensions$$GetMainTileId`), pas par un `get_entity` local. Ce site
    ne lisait QUE le cas UNITE -- un `target_id` de TUILE lui rendait `[]`, donc **zero obus, aucune
    erreur** (#287-r12, mesure `probe_287r12_role_target_tuile.py`)."""
    board = state.board
    ttile = main_tile_id(state, target_id)
    if board is None or ttile is None:
        return []
    tp = board.coord(ttile)
    guaranteed, maybe, miss, _total = basilisk_num_shells(state, caster_id)
    pool_miss = basilisk_tiles_at_distance(state, tp, 2)
    pool_maybe = [ttile] + basilisk_tiles_at_distance(state, tp, 1)
    pool_guar = [ttile]
    tiles = _pick_randomly_n(state, pool_miss, miss, allow_repeat=True, max_repeats=BB_MAX_REPEATS)
    tiles += _pick_randomly_n(state, pool_maybe, maybe, allow_repeat=True, max_repeats=BB_MAX_REPEATS)
    tiles += _pick_randomly_n(state, pool_guar, guaranteed, allow_repeat=True,
                              max_repeats=BB_MAX_REPEATS)
    return tiles


def basilisk_barrage_tree(tiles: list) -> AtomicGroup:
    """Arbre de `IdunBattleLogic.Entities.Abilities.Active.Loki.BasiliskBarrageAbility$$ExecuteBehaviour`
    (id 1026, `astraOrdnance`) -- MIRROR :

        dmg   = MinMaxDamage(this, entities)                                    # minDmg/maxDmg[level]
        prof  = GetDamageProfile(config, 0)                                     # Blast
        hits  = GetNumberConstant(config, 0x2f)                                 # nrOfHits = 2 / obus
        atk   = AttackWithAbilityDamage(Caster@0x160, <tuiles d'impact>, dmg, prof, hits, <AbilityOrEffect>)
        Execute( AtomicGroup(0x54, atk), entities )

    `AttackWithAbilityDamage` = `AttackBehaviour(caster, tuiles, AbilityDamageBehaviour(...))` ->
    `IdunBattle.Operations.AbilityDamageOperation$$ExecuteHits` : famille ABILITY (1 tirage/coup, AUCUN
    crit) -> `native_factory="ability"` (meme classification que PlasmaGrenade, rngcrit-1202). Le
    selecteur de cibles est TILE-domain -> mode `tile_domain=True` de la feuille (tri par id de tuile,
    doublons conserves, tuile vide = op visuelle seule). `attackRangeType=Ranged` -> `is_melee=False`.

    `AtomicGroup(0x54, ...)` inline (#201) ; plain `Execute` (PAS `ExecuteAtomic`)."""
    return AtomicGroup(AttackWithAttackDamage(
        FixedTileIds(tiles), BASILISK_ID, "Blast", is_melee=False,
        native_factory="ability", multi=True, tile_domain=True,
        ability_type=int(ActiveAbilityType.BasiliskBarrage)))


class BasiliskBarrageAbility(ActiveAbility):
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.BasiliskBarrageAbility$$ExecuteBehaviour` (id 1026,
    `astraOrdnance` « Thaddeus Noble », Astra Militarum, HERO). Cast UNIT-TARGET, SANS contrainte de
    portee (i2 : « on any target on the battlefield »).

    Kit gameconfig 1026 : `damageProfile=Blast`, `nrOfHits=2`, `nrOfProjectiles=5`,
    `nrOfProjectiles_2=3`, `minDmg`/`maxDmg`[level] (rarity-affected).

    MECANIQUE (RE + mesure live) : le cast lance `nrOfProjectiles` OBUS sur des TUILES, en trois tranches
    (cf. `basilisk_num_shells`) : `guaranteed` sur la tuile CIBLE, `maybe` sur {tuile cible} u anneau 1,
    `miss` sur l'anneau 2 -- tirage AVEC REMISE (deux obus peuvent tomber sur la meme tuile). Chaque obus
    inflige `nrOfHits` coups Blast a l'occupant de sa tuile ; un obus sur tuile VIDE ne fait rien
    (operation visuelle seule). Une unite touchee par k obus encaisse donc `k x nrOfHits` coups.
    `guaranteed` croit d'1 par round termine (via `TurnsStarted` du caster).

    MESURE LIVE (tour 1, cible entouree, MC1_67) : 5 obus = 2 sur l'anneau 2 + 3 sur {cible} u anneau 1,
    chacun 2 coups Blast ; les unites touchees recoivent en plus `Pinned`/Suppressed (trait
    `SuppressiveFire` du carrier -- i2 : « The Suppressive Fire trait applies also to this ability »),
    canal deja porte cote trigger.

    AVANT ce port, 1026 etait absente d'`ABILITY_CLASSES` : `ported:False` -> **0 degat, aucune erreur**.

    Flags de tour : defauts base (1026 absente des overrides). Le gate « si Thaddeus n'a pas bouge »
    (trait `HeavyWeapon` du carrier) vit dans la couche de DISPONIBILITE d'ability, hors face COMBAT.
    Retour : {tiles, shells, attacks, empty, dsl}."""
    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.BasiliskBarrage)   # 1026
    ABILITY_ID = BASILISK_ID

    # `IdunBattleLogic.Entities.Abilities.Active.Loki.BasiliskBarrageAbility$$.ctor` :
    #     preset = <TargetingRange statics+0x48>
    #     TargetingOptions..ctor(&opts, 0, &preset, 1, 0x80050, 0, 0)
    # Meme overload « FLAGS DIRECTS » que 1017 (cf. la note la-bas) -> litteral = masque effectif.
    #   0x80050 = CasterHasNotMoved | TargetIsTile | TargetTileHasEnemyUnit
    #   range = `TargetingRange$$.cctor` statics+0x48 = useWholeBoard -> RANGE_WHOLE_BOARD : le volet
    #           generique de portee NE TESTE RIEN (i2 : « on any target on the battlefield »).
    # `CasterHasNotMoved` EST le gate i2 « If Thaddeus Noble has not moved » : il vit dans le MASQUE
    # DE CIBLAGE, pas dans une couche de disponibilite separee -- confirmation croisee de la lecture.
    TARGETING_OPTIONS = TargetingOptions(rules=(
          TR.CasterHasNotMoved
        | TR.TargetIsTile
        | TR.TargetTileHasEnemyUnit
    ), range=RANGE_WHOLE_BOARD, force_melee_target=RANGED_BOOL_FALSE)

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        # #287-r14 RESOLUTION DE CIBLE -- `IdunBattle.Core.Services.TargetingQuery$$GetActualTarget`
        # via le slot 16 d'`IActiveAbility` : pour un masque `TargetIsTile`, le role `target` du
        # natif est TOUJOURS l'entite-TUILE, que l'appelant ait passe la tuile ou son occupant.
        # IDEMPOTENT (`GetMainTile(<tuile>)` rend la tuile) -> inerte quand `AbilityHandler` a
        # deja resolu, mordant sur tout appel DIRECT (tests de migration, probes).
        target_id = self.get_actual_target(state, caster_id, target_id)
        if target_id is None or state.get_entity(caster_id) is None:
            return None
        guaranteed, maybe, miss, total = basilisk_num_shells(state, caster_id)
        tiles = basilisk_shell_tiles(state, caster_id, target_id)
        ectx = ExecutionContext(state=state, rng=state.rng)
        basilisk_barrage_tree(tiles).execute(
            entities_from_state(state, caster_id, target_id), ectx)
        attacks = [{"target": p["target"], "attack": p["attack"]}
                   for n, p in ectx.emitted if n == "AttackWithAttackDamage"]
        empty = [p["tile"] for n, p in ectx.emitted if n == "AttackEmptyTile"]
        return {"ability": BASILISK_ID, "caster": caster_id, "target": target_id,
                "tiles": tiles, "attacks": attacks, "empty": empty,
                "shells": {"guaranteed": guaranteed, "maybe": maybe, "miss": miss, "total": total},
                "dsl": True}
