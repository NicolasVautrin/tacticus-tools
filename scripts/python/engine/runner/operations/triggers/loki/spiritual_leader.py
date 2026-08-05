"""`Abilities.Triggered.Loki.SpiritualLeaderAbility` — passif `SpiritualLeader` de Xybia
(`genesMagus.passiveAbilities=['SpiritualLeader']`, HERO Genestealers du pool). RE (decompile
ghidra, build gqfc5mff6c ; symboles confirmes par `search_symbols_by_name`) :

  - `IdunBattleLogic.Entities.Abilities.Triggered.Loki.SpiritualLeaderAbility$$CreateTrigger` =
        On(0x1c=ArrivedAtFinalTile=28) op_BitwiseAnd get_OwnerIsActor
    UNE SEULE branche -- contrairement a `RadSaturationAbility` (3 branches dont un `On(TurnEnd) &
    NOT moved`), la clause « si elle ne bouge pas, ca se declenche en fin de tour » de l'i2 est
    PORTEE PAR L'EVENEMENT LUI-MEME. Les DEUX emetteurs natifs de `On(0x1c)` ont ete lus :
      * `IdunBattle.Operations.MoveUnitOperation$$Execute` : `UnitFlagsComponent.Add(1=
        ArrivedAtFinalTile)` puis, APRES `EvaluateAfterMoveTriggers`, publie `On(0x1c)` SSI le flag
        venait d'etre AJOUTE (donc au 1er move de l'activation seulement) ;
      * `IdunBattle.Operations.FinishUnitTurnOperation$$Execute` : `Add(1)` puis publie `On(0x1c)`
        SSI le flag venait d'etre AJOUTE **et** `!forced` (donc uniquement si l'unite n'a PAS bouge).
    => `On(0x1c)` fire EXACTEMENT UNE FOIS par activation d'unite : a la fin de son 1er deplacement,
    ou a la cloture de son tour si elle n'a pas bouge. C'est la PREUVE de la lecture jusqu'ici
    seulement supposee dans `loki/arcane_shield.py` (« activation TERMINEE : APRES son move, OU fin
    de tour s'il ne bouge pas ») -- ArcaneShield ecoute le MEME `On(0x1c)`.

  - `IdunBattleLogic.Entities.Abilities.Triggered.Loki.SpiritualLeaderAbility$$CreateBehaviour` =
        decoyId  = GetStringConstant(config, 4=unitId_2)          -> `genesSmnDecoy`
        summonId = GetStringConstant(config, 0=unitId)            -> `genesSmnNeophyte`
        tiles    = First( SortTilesByUtilityForSummon(
                            CanAddUnit(AdjacentTiles(caster@0x148), @0xf8),
                            7=UtilityType.Tile, @0x160 ), 1 )
        picked   = PickRandomly( GetAdjacentDecoys(), 1, 0, 0x7fffffff, false )
        spawnA   = Spawn(caster@0x148, tiles,  decoyId,  SpawnUnitOptions.ForSteppable())
        spawnB   = Spawn(caster@0x148, picked, summonId, SpawnUnitOptions.WithStatsFromConfig(config, lvl))
        cond     = AmountIsEqualOrGreater( GetAdjacentDecoys(), Direct(2) )
        result   = If(tiles, Group(spawnA, Null, 0x62)) op_BitwiseAnd If(cond, Group(spawnB, Null, 99))
  - `IdunBattleLogic.Entities.Abilities.Triggered.Loki.SpiritualLeaderAbility$$GetAdjacentDecoys` =
        Filter( AdjacentFriends(caster@0x148, 1, 1),
                HasTrait(it@0x180, 0x41d=1053=Decoy)
                op_BitwiseAnd ( op_LogicalNot(HasFlag(it@0x180, 0x11=17=UnitFlag.Untargetable))
                                op_BitwiseOr HasEffect(it@0x180, 0x56e=1390=
                                    EffectType.DecoysAndMisdirection_JustSummonedEffect, 0, 6) ) )
  - `IdunBattleLogic.Entities.Abilities.Triggered.Loki.SpiritualLeaderAbility$$GetPossibleDecoySpawnTiles`
    = `CanAddUnit(AdjacentTiles(caster@0x148), @0xf8)` -- le MEME sous-arbre que la 1re ligne du
    behaviour, exporte pour le playbook (`SpiritualLeaderPlaybook`, face DECISION, hors perimetre).

    == i2 : « After moving, places a decoy on an empty adjacent hex. Then, if there are 2 or more
    decoys adjacent to Xybia, summons a Neophyte Hybrid on one adjacent decoy. If Xybia does not
    move, then this ability triggers at the end of her turn. Neophyte Hybrid stats: 2183 Health
    1746 Damage 437 Armour »

ORDRE (decisif) : le DSL est LAZY -- `cond` est evalue quand le 2e `If` s'execute, donc APRES le
spawn du 1er decoy. Le decoy tout juste pose COMPTE dans le « 2 or more » (« Then » de l'i2). C'est
ce que fait ce port : `_adjacent_decoys` est RE-EVALUE apres le spawn.

Enums qualifies (piege homonymie, cf. docs/rl/passive-ability-coverage.md) :
  - `0x41d=1053` = **UnitTrait**.Decoy (PAS EffectType 1053 = ShadowInTheWarp_LessDmg_Effect, PAS
    ActiveAbilityType 1053 = DevoutPush, PAS TriggeredAbilityType 1053 = BroodProgenitor) ;
  - `0x11=17` = **UnitFlag**.Untargetable (`IdunBattle.Entities.Enum.UnitFlag`, table de symboles) ;
  - `0x56e=1390` = **EffectType**.DecoysAndMisdirection_JustSummonedEffect ;
  - `4` / `0` = `IdunBattle.Configuration.AbilityConstantType`.unitId_2 / .unitId -- verifies contre
    le gameconfig (`SpiritualLeader.constants={'unitId_2':'genesSmnDecoy','unitId':
    'genesSmnNeophyte'}`), et `summonHp/summonDmg/summonArmor[64]` = 2183/1746/437, exactement les
    nombres de l'i2 -> confirme l'overload `WithStatsFromConfig` (et non `ForSteppable`) pour le
    Neophyte.

DOCTRINE #149 : le predicat du trigger (`OwnerIsActor`) est COLLAPSE imperativement ; les feuilles
delegue aux Operations deja portees -- `Spawn(ForSteppable)` -> `spawn_decoy` (primitive G1),
`Spawn(WithStatsFromConfig)` -> `_spawn_config_grot` (meme helper que CultDemagogue/GetEmRuntz, qui
appelle `build_summon_context`). Les selecteurs S qui manquent au vocabulaire DSL du port
(`SortTilesByUtilityForSummon`, `PickRandomly`, `AdjacentFriends`+`Filter` compose,
`AmountIsEqualOrGreater` sur un selecteur) sont collapses ici en REUTILISANT les collapses DEJA
portes et valides de `operations/spawn.py` (`_free_tiles_adjacent`, `_sort_tiles_by_utility_for_summon`,
`_first`) et `abilities/loki/splash.py` (`_pick_randomly_n`, loi RNG #130/#215) -- aucun fork.

`Group(child, Null, 0x62 | 99)` : wrapper de sequencement (2e operande `Null`, 3e = un id de
timeline/visuel) -- l'observable est le `child` seul, donc non materialise.

DISPATCH : vecteur NEUF `arrived_at_final_tile_triggers` (`On(0x1c)`) ajoute a `dispatch.py`, emis
aux DEUX points natifs : (a) en queue d'`after_move_triggers` (mirror `MoveUnitOperation$$Execute`,
gate `UnitFlag.ArrivedAtFinalTile` nouvellement pose), (b) dans `FinishUnitTurnOperation.execute`
(mirror `FinishUnitTurnOperation$$Execute`, gate `newly_arrived and not forced` -- deja calcule et
rendu par l'Operation portee). Le gate par flag garantit AU PLUS UN fire par activation.

RESIDUS (honnetes) :
  - `NOT HasFlag(it, Untargetable=17)` et `HasEffect(it, 1390)` : le port ne pose NI le flag 17 sur
    un decoy fraichement invoque, NI l'effet 1390 (`spawn_decoy` ne pose aucun des deux). Le OU se
    reduit donc a TRUE et le filtre a `HasTrait(Decoy)` -- porte quand meme, pour que le jour ou
    l'un des deux sera pose la semantique soit deja juste. Consequence mesurable AUJOURD'HUI : nulle.
  - Le Neophyte spawne SUR la tuile d'un decoy : le natif `AddUnitOperation$$KillSteppableUnits`
    ecrase le decoy porteur. Porte via `movement._kill_steppable_units` (meme helper que le crush
    par move). Ce crush n'emet PAS `On(0x35=PostUnitKill)` ici (le port ne l'emet que pour le
    crush-par-MOVE, cf. `loki/cosmic_horror.py`) : aucun consommateur porte ne le lit sur ce chemin.
  - `SpiritualLeaderPlaybook` (`FilterAdjacentFriends` / `GetAdjacentFriendUtility`) = face DECISION
    (l'IA prefere finir son move a cote de ses decoys) : hors perimetre de la face COMBAT.
"""
from __future__ import annotations

from typing import Optional

from ....state import State
from ....components import (OwnerComponent, UnitComponent, PositionComponent, StatsComponent,
                            UnitFlagsComponent)
from .....entities.traits.unit_trait import UnitTrait, has_trait
from .....entities.effect_type import EffectType
from .....dsl.event_trigger_type import EventTriggerType
from ..base import TriggeredAbility, TriggerEvent, _hex_dist
from .....entities.unit_flag import UnitFlag   # #270-r1-r1-r3
from ....abilities.loki.splash import _pick_randomly_n
from ...movement import _kill_steppable_units
from ...spawn import _free_tiles_adjacent, _sort_tiles_by_utility_for_summon, _first
from ...spawn import _spawn_config_grot
from ...spawn import spawn_decoy, _spawn_config_grot

ABILITY_ID = "SpiritualLeader"
DECOY_UNIT_KEY = "unitId_2"                        # AbilityConstantType 4  (GetStringConstant(config, 4))
SUMMON_UNIT_KEY = "unitId"                         # AbilityConstantType 0  (GetStringConstant(config, 0))
DECOY_TRAIT = UnitTrait.Decoy                      # 0x41d = 1053
UNTARGETABLE_FLAG = UnitFlag.Untargetable                             # UnitFlag.Untargetable (0x11)
JUST_SUMMONED = int(EffectType.DecoysAndMisdirection_JustSummonedEffect)   # 0x56e = 1390
ADJACENT_RANGE = 1                                 # AdjacentFriends(caster@0x148, 1, 1)
MIN_DECOYS_FOR_SUMMON = 2                          # AmountIsEqualOrGreater(GetAdjacentDecoys(), Direct(2))

_ON_ARRIVED = int(EventTriggerType.ArrivedAtFinalTile)    # 0x1c = 28


def _adjacent_decoys(state: State, owner_id: int) -> list:
    """`IdunBattleLogic.Entities.Abilities.Triggered.Loki.SpiritualLeaderAbility$$GetAdjacentDecoys`
    (collapse S) :

        Filter( AdjacentFriends(caster, 1, 1),
                HasTrait(it, Decoy) & ( NOT HasFlag(it, Untargetable) | HasEffect(it, 1390) ) )

    = les decoys ALLIES VIVANTS a distance hex 1 de Xybia. Ordre = ids d'entite croissants (l'ordre
    d'enumeration natif d'`AdjacentFriends` n'est pas observable offline ; il n'influence que la
    BORNE du tirage `PickRandomly`, pas sa consommation PRNG -- cf. `_pick_randomly_n`, loi #215).
    Le sous-predicat `NOT Untargetable | JustSummoned` est porte litteralement (cf. RESIDUS du
    module : ni le flag 17 ni l'effet 1390 ne sont poses par le port aujourd'hui)."""
    board = state.board
    owner = state.get_entity(owner_id)
    if board is None or owner is None:
        return []
    ooc = owner.get_component(OwnerComponent)
    opc = owner.get_component(PositionComponent)
    if ooc is None or opc is None:
        return []
    otile = board.id_at(opc.col, opc.row)
    if otile is None:
        return []
    out: list = []
    for uid, e in sorted(state.entities.items()):
        if uid == owner_id:
            continue
        uc = e.get_component(UnitComponent)
        if uc is None or not uc.alive:
            continue
        oc = e.get_component(OwnerComponent)
        if oc is None or oc.team != ooc.team:                 # AdjacentFriends : meme team
            continue
        sc = e.get_component(StatsComponent)
        traits = getattr(sc.ctx, "traits", None) if sc is not None else None
        if not has_trait(traits or [], DECOY_TRAIT):          # HasTrait(it, Decoy=1053)
            continue
        pc = e.get_component(PositionComponent)
        if pc is None:
            continue
        t = board.id_at(pc.col, pc.row)
        d = _hex_dist(board, otile, t, ADJACENT_RANGE) if t is not None else None
        if d is None or d > ADJACENT_RANGE:                   # AdjacentFriends(caster, 1, 1)
            continue
        fl = e.get_component(UnitFlagsComponent)
        untargetable = fl is not None and fl.has(UNTARGETABLE_FLAG)
        just_summoned = (state.effects is not None
                         and state.effects.has_effect(uid, effect_type=JUST_SUMMONED))
        if untargetable and not just_summoned:                # NOT HasFlag(17) OR HasEffect(1390)
            continue
        out.append(uid)
    return out


def _decoy_spawn_tile(state: State, owner_id: int):
    """`First( SortTilesByUtilityForSummon( CanAddUnit(AdjacentTiles(caster@0x148), @0xf8),
    7=UtilityType.Tile, @0x160 ), 1 )` (collapse S) -> id de tuile ou None.

    Delegue INTEGRALEMENT aux collapses deja portes et valides live de `operations/spawn.py` :
    `_free_tiles_adjacent(native_order=True)` (= `CanAddUnit(AdjacentTiles(...))` dans l'ordre
    d'enumeration natif `boardGraph.neighbours`), puis `_sort_tiles_by_utility_for_summon`
    (= tri DESCENDANT par l'utilite composite `Tile(7)`, `OrderBy` LINQ donc STABLE -- ex aequo
    departages par l'ordre SOURCE), puis `_first`. ZERO tirage RNG sur ce chemin."""
    tiles = _free_tiles_adjacent(state, owner_id, set(), native_order=True)
    return _first(_sort_tiles_by_utility_for_summon(state, tiles, owner_id))


class SpiritualLeaderAbility(TriggeredAbility):
    """`SpiritualLeaderAbility` (`IdunBattleLogic.Entities.Abilities.Triggered.Loki.SpiritualLeaderAbility$$CreateTrigger`
    / `...$$CreateBehaviour` / `...$$GetAdjacentDecoys`). A la fin de l'activation de Xybia
    (`On(0x1c=ArrivedAtFinalTile) & OwnerIsActor` -- apres son 1er move, ou a la cloture de son tour
    si elle n'a pas bouge) : pose un decoy `genesSmnDecoy` sur la meilleure tuile adjacente libre,
    PUIS -- si elle a alors >=2 decoys adjacents -- invoque un `genesSmnNeophyte` (stats
    `WithStatsFromConfig` = summonHp/summonDmg/summonArmor du passif) sur l'UN de ces decoys tire au
    hasard, ecrasant le decoy porteur."""
    event_id = _ON_ARRIVED

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        if ev.actor_id != self.owner_id:                      # get_OwnerIsActor
            return False
        owner = state.get_entity(self.owner_id)
        if owner is None:
            return False
        uc = owner.get_component(UnitComponent)
        return not (uc is not None and not uc.alive)          # un acteur mort n'agit pas (#70)

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        import gameconfig as GC
        consts = (GC.ability(ABILITY_ID) or {}).get("constants") or {}
        out: dict = {"passive": ABILITY_ID, "owner": self.owner_id,
                     "decoy": None, "decoy_tile": None, "summon": None, "summon_on_decoy": None}
        if state.board is None:
            return None
        # --- If(tiles, Group(Spawn(caster, tiles, unitId_2, ForSteppable()), Null, 0x62)) ---------
        # `If(<selecteur>, behaviour)` = « le selecteur rend au moins une tuile » ; `_decoy_spawn_tile`
        # rend None quand `CanAddUnit(AdjacentTiles(caster))` est vide -> le 1er volet est saute.
        tile = _decoy_spawn_tile(state, self.owner_id)
        if tile is not None:
            out["decoy_tile"] = tile
            out["decoy"] = spawn_decoy(state, tile, self.owner_id,
                                       visual_id=consts.get(DECOY_UNIT_KEY) or "genesSmnDecoy")
        # --- If(AmountIsEqualOrGreater(GetAdjacentDecoys(), Direct(2)), Group(spawnB, Null, 99)) --
        # RE-EVALUATION (DSL lazy) : le decoy qu'on vient de poser COMPTE (« Then » de l'i2).
        decoys = _adjacent_decoys(state, self.owner_id)
        out["adjacent_decoys"] = list(decoys)
        if len(decoys) < MIN_DECOYS_FOR_SUMMON:
            return out
        picked = _pick_randomly_n(state, decoys, 1)           # PickRandomly(GetAdjacentDecoys(), 1)
        if not picked:
            return out
        target_decoy = picked[0]
        out["summon_on_decoy"] = target_decoy
        out["summon"] = self._spawn_neophyte(state, target_decoy,
                                             consts.get(SUMMON_UNIT_KEY) or "genesSmnNeophyte")
        return out

    def _spawn_neophyte(self, state: State, decoy_id: int, visual_id: str) -> Optional[int]:
        """`Spawn(caster@0x148, PickRandomly(GetAdjacentDecoys(),1), unitId,
        SpawnUnitOptions.WithStatsFromConfig(config, level))` -> `SpawnUnitBehaviour.Execute` ->
        `AddUnitOperation.Execute`. Le selecteur de destination rend une UNITE (le decoy tire) : le
        natif en prend la MainTile. `WithStatsFromConfig` = `_spawn_config_grot` (qui appelle
        `build_summon_context` -> `ability_var(SpiritualLeader, summon*[niveau du PASSIF], mult)`).
        `ai_controlled=False` : le Neophyte porte Ambush+BattleFatigue, PAS le trait `Summon` -- il
        est joue au tour de sa team, pas auto-joue au turn-start (meme choix que CultDemagogue).
        `AddUnitOperation$$KillSteppableUnits` ecrase ensuite le decoy sous la nouvelle unite."""
        board = state.board
        decoy = state.get_entity(decoy_id)
        owner = state.get_entity(self.owner_id)
        if board is None or decoy is None or owner is None:
            return None
        dpc = decoy.get_component(PositionComponent)
        ooc = owner.get_component(OwnerComponent)
        osc = owner.get_component(StatsComponent)
        if dpc is None or ooc is None:
            return None
        tile = board.id_at(dpc.col, dpc.row)
        if tile is None:
            return None
        octx = osc.ctx if osc is not None else None
        # `ConfigVar`/`WithStatsFromConfig` lisent l'`abilityState` du PASSIF du porteur.
        level = getattr(octx, "passive_ability_level", None) if octx is not None else None
        mult = int(getattr(octx, "ability_variables_multiplier", 100) or 100) if octx is not None else 100
        neo = _spawn_config_grot(state, visual_id, tile, ABILITY_ID, level, mult,
                                 ooc.team, ooc.player, ai_controlled=False,
                                 parent_id=self.owner_id)
        if neo is not None:
            # `AddUnitOperation$$KillSteppableUnits` : le decoy porteur est CRUSHE par l'arrivant.
            _kill_steppable_units(state, (dpc.col, dpc.row), neo)
        return neo
