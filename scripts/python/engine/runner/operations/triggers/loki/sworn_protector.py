"""`SwornProtector` (passif d'`astraCreed` « Lord Castellan Creed ») + `SwornProtector_Protect`
(passif d'`astraSmnKell`) — le MAILLON AMONT de la chaine #95-RESTE2 : sans lui, Kell n'existe pas et
`GetAbilityStatModification` ne peut jamais etre non nul.

i2 (Creed) : « When Lord Castellan Creed is first targeted in battle, Colour Sergeant Kell appears in a
free adjacent hex. Any time Creed is attacked, Kell switches hexes with him and takes the Damage
instead, if they are adjacent to each other. »

================================================================================================
RE (decompile ghidra, build `gqfc5mff6c`)
================================================================================================

## `IdunBattleLogic.Entities.Abilities.Active.Loki.SwornProtectorAbility$$CreateTrigger`
(conjonction `AbilityTrigger.op_BitwiseAnd`, slots `AbilityEntities` de
`IdunBattleLogic.Entities.DSLFactory$$InitializeShared` : `0x148 Owner · 0x158 Actor · 0x160 Caster ·
0x178 Target`, `0x130` = l'ability declenchante, `0xc0` = la constante `1` du `.ctor` du factory)

    On(0x2b = PreUnitAbility, 1)
    & AreEnemies(caster@0x160, owner@0x148)
    & GetIsValidTargetForSwornProtectorTrigger(owner@0x148)      # sous-fonction dediee
          = AreEqual(target@0x178, owner) | AreEqual(target@0x178, MainTileOfUnits(owner))
    & GetIsValidAttackForSwornProtectorTrigger()                 # sous-fonction dediee
          = AbilityHasAttackType(@0x130, 0) | AbilityHasAttackType(@0x130, 1)   # melee OU ranged
    & NOT HasTriggeredAbilityBeenTriggered(owner@0x148, this.Id) # << FIRST targeted >> (one-shot)
    & NOT AmountIsEqualOrGreater( UnitsWithId(Children(owner@0x148),
                                              GetStringConstant(cfg, 0), 3), One@0xc0 )
                                                                 # Kell pas deja en jeu
    & AmountIsEqualOrGreater( CanAddUnit(AdjacentTiles(owner@0x148)), One@0xc0 )
                                                                 # >=1 hex libre adjacent

## `IdunBattleLogic.Entities.Abilities.Active.Loki.SwornProtectorAbility$$CreateBehaviour`

    tilesC     = Cache(Tiles(owner@0x148))
    spawnTile  = Cache( GetSpawnTile(this, tilesC) )
                 # `SwornProtectorAbility$$GetSpawnTile` =
                 #   First( SortTilesByUtilityForSummon( CanAddUnit(AdjacentTiles(tilesC)),
                 #                                       UtilityBucket{WeightedUtility(7),
                 #                                                     WeightedUtility(0x33)},
                 #                                       owner@0x148 ), 1 )
    unitId     = GetStringConstant(cfg, 0)                        # astraSmnKell
    opts       = SpawnUnitOptions.WithStatsFromConfig(cfg, level)
    opts+0x10  = AddEffect(0x4ce = SwornProtector_JustSummonedEffect, absRef, target@0x178)
    unitsC     = Cache(Units(spawnTile))                          # les unites POSEES sur ces tuiles
    spawnB     = Spawn(owner@0x148, spawnTile, unitId, opts)
    trigB      = TriggerAbility(unitsC, 0x433 = SwornProtector_Protect, caster@0x160, ..., 1, ...)
    ifB        = If( CanSwitchPosition(owner@0x148), trigB )
    removeB    = RemoveEffect(owner@0x148, Nullable(0x4ce))
    return (spawnB & ifB) & removeB

=> Kell apparait ET (si Creed peut switcher) `SwornProtector_Protect` est declenchee IMMEDIATEMENT sur
lui : le switch a donc lieu AVANT que l'attaque declenchante ne se resolve — c'est bien Kell qui
encaisse. GROUND TRUTH LIVE : Creed (4,4) attaque -> Kell apparait (3,4) -> apres la cascade Creed est
en (2,3) et Kell en (3,4)... les deux ont echange, et les coups sont alles sur Kell (e=92).

## `IdunBattleLogic.Entities.Abilities.Active.Loki.SwornProtector_ProtectAbility$$CreateTrigger`

    parent = Parent(owner@0x148)                                  # Creed
    On(0x2b = PreUnitAbility, 1)
    & ( AreEqual(target@0x178, parent) | AreEqual(target@0x178, MainTileOfUnits(parent)) )
    & ( AbilityHasAttackType(@0x130, 0) | AbilityHasAttackType(@0x130, 1) )
    & NOT AreEqual(actor@0x158, owner@0x148)                      # Kell n'est pas l'acteur
    & IsAdjacent(owner@0x148, parent, 3)                          # « if they are adjacent »
    & CanSwitchPosition(parent) & CanSwitchPosition(owner@0x148)

`IdunBattleLogic.Entities.DSLFactory$$CanSwitchPosition(u)` = `NOT HasEffect(u, 0x1b, 0, 6)`
(0x1b = 27 = `Taunted_OnlySpecificTargets` — une unite tauntee ne peut pas etre deplacee par le switch).

## `IdunBattleLogic.Entities.Abilities.Active.Loki.SwornProtector_ProtectAbility$$CreateBehaviour`

    Inform({ 0xb4 : EntityId(caster@0x160) })                     # notification de vue (no-op moteur)
    & SwitchPosition(owner@0x148, Parent(owner@0x148))            # DisplaceUnitBehaviour(mode 6, ..., 2)
    & ResetPreviousPosition(owner@0x148)
    & RemoveEffect(owner@0x148, Nullable(0x4ce))

================================================================================================
FORME DU PORT
================================================================================================
Les predicats des DEUX triggers sont COLLAPSES imperativement dans `matches` (doctrine #149, comme
SuppressiveFire/MasterAnnihilator) ; les behaviours restent des arbres DSL au-dessus des Operations.

RESIDUS EXPLICITES :
 * `SortTilesByUtilityForSummon` (moteur d'utilite IA complet) n'est pas porte -> la tuile de spawn est
   la PREMIERE tuile libre adjacente dans l'ordre du voisinage `board.neighbours` (MEME collapse que
   `ForwardSpotter`/`SkyStrike`, cf. `abilities/astramilitarum.py`). Le POOL et le CARDINAL sont exacts,
   la TUILE choisie peut differer du live.
 * `Inform({0xb4: EntityId(caster)})` = notification du bus de vue, AUCUNE mutation d'etat -> no-op
   (meme traitement que le `Inform` de MalleusRocketLauncher).
 * `ResetPreviousPosition(owner)` = remise a zero du champ « position precedente » (anti-retour du
   pathfinding). Le port ne materialise pas ce champ -> no-op documente.
 * Le marqueur `SwornProtector_JustSummonedEffect` (0x4ce = 1230) est pose puis retire DANS LE MEME
   behaviour et n'est lu par AUCUN gate porte : le port l'omet plutot que de deviner le slot
   `SpawnUnitOptions+0x10` (contraste `+0x18` = on-appearance, lui identifie). Observable nul.
 * Le vecteur `On(PreUnitAbility)` n'est emis par le port QUE sur la voie d'attaque NORMALE
   (`damage_ops.py`) ; le natif l'emet aussi pour les attaques d'ABILITY -> une ability offensive
   ciblant Creed ne reveille pas encore SwornProtector cote port (residu partage avec AnvilShield).
"""
from __future__ import annotations

from typing import Optional

import gameconfig as GC

from ....state import State
from ....components import (OwnerComponent, PositionComponent, UnitComponent, StatsComponent,
                            parent_of, children_of)
from ....abilities.behaviours import Spawn, entities_from_state
from .....entities.selectors import AdjacentTiles, CanAddUnit, Caster, First
from .....entities.effect_type import EffectType
from .....dsl.effects import ExecutionContext
from .....dsl.event_trigger_type import EventTriggerType
from ..base import TriggeredAbility, TriggerEvent

SWORN_PROTECTOR_ABILITY = "SwornProtector"
SWORN_PROTECTOR_CONST_UNIT_ID = 0x00      # GetStringConstant(cfg, 0) -> "unitId" = astraSmnKell
_ON_PRE_UNIT_ABILITY = int(EventTriggerType.PreUnitAbility)     # 0x2b = 43
# `IdunBattleLogic.Entities.DSLFactory$$CanSwitchPosition(u)` = `NOT HasEffect(u, 0x1b, 0, 6)`.
TAUNTED_EFFECT = int(EffectType.Taunted_OnlySpecificTargets)    # 0x1b = 27


def _has_effect(state: State, unit_id: int, effect_type: int) -> bool:
    eff = getattr(state, "effects", None)
    if eff is None:
        return False
    return any((not e.consumed) and e.effect_type == effect_type
               for e in eff.by_unit.get(int(unit_id), []))


def can_switch_position(state: State, unit_id: Optional[int]) -> bool:
    """`IdunBattleLogic.Entities.DSLFactory$$CanSwitchPosition(u)` = `NOT HasEffect(u, 27=Taunted, 0, 6)`."""
    if unit_id is None:
        return False
    return not _has_effect(state, unit_id, TAUNTED_EFFECT)


def _is_adjacent(state: State, a_id: Optional[int], b_id: Optional[int]) -> bool:
    """`IdunBattleLogic.Entities.DSLFactory$$IsAdjacent(a, b, 3)` — adjacence hex via `board.neighbours`."""
    board = getattr(state, "board", None)
    if board is None or a_id is None or b_id is None:
        return False
    ae, be = state.get_entity(int(a_id)), state.get_entity(int(b_id))
    ap = ae.get_component(PositionComponent) if ae is not None else None
    bp = be.get_component(PositionComponent) if be is not None else None
    if ap is None or bp is None:
        return False
    at, bt = board.id_at(ap.col, ap.row), board.id_at(bp.col, bp.row)
    return at is not None and bt is not None and bt in set(board.neighbours(at))


def switch_position(state: State, a_id: int, b_id: int) -> bool:
    """`IdunBattleLogic.Entities.DSLFactory$$SwitchPosition(a, b)` ->
    `IdunBattle.Entities.Behaviours.DisplaceUnitBehaviour..ctor(6, a, b, 0,0,0,0, 2)` : les deux unites
    ECHANGENT leur hexagone (mode de deplacement 6 = switch, priorite 2). Port : echange des
    `PositionComponent` (les positions sont exclusives, l'echange est toujours legal). False si une
    position manque."""
    ae, be = state.get_entity(int(a_id)), state.get_entity(int(b_id))
    ap = ae.get_component(PositionComponent) if ae is not None else None
    bp = be.get_component(PositionComponent) if be is not None else None
    if ap is None or bp is None:
        return False
    ap.col, ap.row, bp.col, bp.row = bp.col, bp.row, ap.col, ap.row
    return True


def _is_attack_event(ev: TriggerEvent) -> bool:
    """`AbilityHasAttackType(@0x130, 0) | AbilityHasAttackType(@0x130, 1)` = « l'ability declenchante est
    une ATTAQUE (melee OU ranged) ». Le vecteur `On(PreUnitAbility)` du port n'est emis QUE depuis la
    voie d'attaque normale (`damage_ops.py`, `ability_type=1013`) -> la disjonction est satisfaite
    STRUCTURELLEMENT (meme raisonnement que le gate `IsNormalAttack` d'AnvilShield). On garde le test
    d'acteur/cible present pour ne pas fire sur un evenement degenere."""
    return ev.actor_id is not None and ev.target_id is not None


def sworn_protector_spawn_tree() -> Spawn:
    """Arbre du 1er terme de
    `IdunBattleLogic.Entities.Abilities.Active.Loki.SwornProtectorAbility$$CreateBehaviour` :
        `Spawn(owner@0x148, GetSpawnTile(...), GetStringConstant(0) = astraSmnKell,
               WithStatsFromConfig(cfg, level))`
    COLLAPSE de `GetSpawnTile` : `First(SortTilesByUtilityForSummon(CanAddUnit(AdjacentTiles(owner))),
    1)` -> `First(CanAddUnit(AdjacentTiles(Caster())))` (le tri par utilite IA n'est pas porte, cf.
    l'en-tete du module). `Caster()` = l'owner (triggered : Owner == Caster)."""
    return Spawn(First(CanAddUnit(AdjacentTiles(Caster()))), SWORN_PROTECTOR_ABILITY)


class SwornProtectorSummonKellAbility(TriggeredAbility):
    """`SwornProtectorAbility` (triggered 1050) — la PREMIERE fois que Creed est CIBLE par une attaque
    ennemie, Kell apparait sur un hex libre adjacent, puis (si Creed peut switcher) prend sa place
    immediatement via `SwornProtector_Protect`."""
    event_id = _ON_PRE_UNIT_ABILITY

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        owner = state.get_entity(self.owner_id)
        if owner is None or ev.target_id != self.owner_id:     # GetIsValidTargetForSwornProtectorTrigger
            return False
        if not _is_attack_event(ev):                            # GetIsValidAttackForSwornProtectorTrigger
            return False
        att = state.get_entity(ev.actor_id) if ev.actor_id is not None else None
        oc = owner.get_component(OwnerComponent)
        ac = att.get_component(OwnerComponent) if att is not None else None
        if oc is None or ac is None or oc.team == ac.team:      # AreEnemies(caster@0x160, owner@0x148)
            return False
        # `NOT HasTriggeredAbilityBeenTriggered(owner, this.Id)` : one-shot par bataille (« FIRST
        # targeted »). Porte par le compteur de phase deja materialise (`TriggeredAbilityComponent`) ?
        # NON — celui-la est per-PHASE. Le natif lit le flag `hasBeenTriggered` PERMANENT du
        # `TriggeredAbilityComponent`. Le port l'exprime par la presence d'un ENFANT Kell (vivant OU
        # MORT), qui est la consequence observable exacte du 1er declenchement : Kell ne peut apparaitre
        # qu'une fois. (Le terme suivant du trigger natif, `NOT AmountIsEqualOrGreater(UnitsWithId(
        # Children(owner), astraSmnKell), 1)`, est le MEME test restreint aux VIVANTS ; les deux
        # ensemble = « aucun Kell n'a jamais ete invoque ».)
        if self._kell_ids(state, alive_only=False):
            return False
        return bool(self._free_adjacent_tiles(state))           # AmountIsEqualOrGreater(CanAddUnit(...), 1)

    def _kell_ids(self, state: State, alive_only: bool = True) -> list:
        """`UnitsWithId(Children(owner@0x148), GetStringConstant(cfg, 0) = astraSmnKell, 3)`."""
        vid = ((GC.ability(SWORN_PROTECTOR_ABILITY) or {}).get("constants") or {}).get("unitId")
        out = []
        for cid in children_of(state, self.owner_id, alive_only=alive_only):
            e = state.get_entity(cid)
            uc = e.get_component(UnitComponent) if e is not None else None
            if uc is not None and uc.visual_id == vid:
                out.append(cid)
        return out

    def _free_adjacent_tiles(self, state: State) -> list:
        """`CanAddUnit(AdjacentTiles(owner@0x148))` — evalue par le MEME arbre DSL que le behaviour."""
        sel = CanAddUnit(AdjacentTiles(Caster()))
        return list(sel.evaluate(entities_from_state(state, self.owner_id)) or [])

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        ectx = ExecutionContext(state=state, rng=state.rng)
        sworn_protector_spawn_tree().execute(
            entities_from_state(state, self.owner_id, ev.target_id), ectx)
        spawned = [p["unit"] for n, p in ectx.emitted if n == "SpawnUnit"]
        switched = None
        # `If( CanSwitchPosition(owner@0x148), TriggerAbility(unitsC, 0x433 = SwornProtector_Protect) )`
        # -> le switch a lieu DANS le behaviour de SwornProtector, pas par le dispatch (le registre de
        # l'event courant a ete materialise AVANT que Kell n'existe).
        if spawned and can_switch_position(state, self.owner_id):
            kell = spawned[0]
            if SwornProtectorProtectSwitchAbility(kell).protect_behaviour(state) :
                switched = kell
        return {"ability": "SwornProtector", "unit": self.owner_id, "spawned": spawned,
                "switched": switched}


class SwornProtectorProtectSwitchAbility(TriggeredAbility):
    """`SwornProtector_ProtectAbility` (triggered 1075, passiveAbility d'`astraSmnKell`) — a CHAQUE
    attaque visant Creed, Kell echange sa position avec lui (et encaisse donc le coup), s'ils sont
    adjacents et que ni l'un ni l'autre n'est taunte."""
    event_id = _ON_PRE_UNIT_ABILITY

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        par = parent_of(state, self.owner_id)                   # Parent(owner@0x148) = Creed
        if par is None or ev.target_id != par.id:               # AreEqual(target@0x178, parent)
            return False
        if not _is_attack_event(ev):                            # AbilityHasAttackType(melee|ranged)
            return False
        if ev.actor_id == self.owner_id:                        # NOT AreEqual(actor@0x158, owner@0x148)
            return False
        owner = state.get_entity(self.owner_id)
        uc = owner.get_component(UnitComponent) if owner is not None else None
        if uc is None or not uc.alive:
            return False
        if not _is_adjacent(state, self.owner_id, par.id):      # IsAdjacent(owner, parent, 3)
            return False
        return can_switch_position(state, par.id) and can_switch_position(state, self.owner_id)

    def protect_behaviour(self, state: State) -> bool:
        """`SwornProtector_ProtectAbility$$CreateBehaviour` — MIRROR :
            Inform({0xb4: EntityId(caster)})     -> no-op moteur (bus de vue)
            & SwitchPosition(owner, Parent(owner))
            & ResetPreviousPosition(owner)       -> no-op (champ non materialise)
            & RemoveEffect(owner, 0x4ce)         -> no-op (marqueur non porte, cf. en-tete)
        Renvoie True si l'echange a eu lieu."""
        par = parent_of(state, self.owner_id)
        if par is None:
            return False
        return switch_position(state, self.owner_id, par.id)

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        par = parent_of(state, self.owner_id)
        ok = self.protect_behaviour(state)
        return {"ability": "SwornProtector_Protect", "unit": self.owner_id,
                "parent": par.id if par is not None else None, "switched": bool(ok)}
