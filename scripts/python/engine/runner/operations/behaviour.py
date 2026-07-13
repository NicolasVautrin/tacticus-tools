"""Mecaniques de COMPORTEMENT — **Battle Fatigue** (trait `BattleFatigue`).

RE ghidra (gqfc5mff6c) :
  `BattleFatigueAbility.CreateTrigger` @18121a5c0 = `OnDeath(1) & IsAdjacent(self,dying,2) &
   AreFriends(dying,self) & NOT HasEffect(self, 0x437=1079 IgnoreBattleFatigue) & NOT IsObjectOrSteppable(dying)
   & OwnerActive` -> quand un ALLIE adjacent (<=2 hex) meurt et que self n'est pas immunise.
  `BattleFatigueAbility.CreateBehaviour` @18121a0d0 = `Repeat(numTriggers, If(NOT HasFlag(self,9),
   Maybe(GetFleeChance, self) -> Flee(self,...)))`. `GetFleeChance` @18121a730 = `ConditionalAmount(
   TargetIsOverkilled ? const 0x33 : const 0x2a)` — chances NON sourcables offline (config interne BC).
  `FleeOperation.Execute` @180e72680 = deplace vers une tuile de fuite -> RecordFlee (stats/timelines) ->
   RemoveEffects (3 phases) -> **pose UnitFlag 9** (« a fui » : bloque la ré-action ; re-teste par le trigger)
   -> events.

GROUND TRUTH live (cf. project_instinctive_fatigue_carriers) : `BattleFatigue` est un **TRAIT** (gameconfig)
porte par les gaunts/grots/summons ; les grots invoques par SquigHound (Snotflogga) recoivent
`IgnoreBattleFatigue` (1079) -> immunises (confirme live). Sujets non-immunises spawnables :
genesSmnNeophyte / astraSmnGuardsman / orksOrkBoys / tyranSmnRipperSwarm.

PORTAGE : la CONDITION de trigger (deterministe) est portee+validable. Le `Maybe(fleeChance)` (RNG, chance
un-sourcable offline) est un GATE documente ; par defaut on FUIT quand eligible (pour exercer/valider
FleeOperation), et on ne tire la chance que si `state.battle_fatigue_flee_chance` est fournie (live-mesuree).
La DESTINATION de fuite (pathfinding natif) = approximee par la tuile atteignable maximisant la distance min
aux ennemis. Stats/timelines/remove-effects (non observables) = non portes.
"""
from __future__ import annotations

from typing import Optional

from ..components import OwnerComponent, PositionComponent, UnitComponent, UnitFlagsComponent
from .triggers import TriggeredAbility, _unit_tile, _hex_dist
from ...dsl.event_trigger_type import EventTriggerType

IGNORE_BATTLE_FATIGUE = 0x437    # 1079 IgnoreBattleFatigue (immunite ; posee p.ex. par SquigHound 1078)
BATTLE_FATIGUE_ADJ = 2           # IsAdjacent(self, dying, 2) — rayon de l'allie mourant


class FleeOperation:
    """`IdunBattle.Operations.FleeOperation.Execute` @180e72680 (port STRUCTUREL de l'observable).

    L'unite FUIT : pose le **UnitFlag 9** (`UnitFlagsComponent`, « a fui » -> bloque la ré-action ce tour)
    + se DEPLACE vers la tuile atteignable maximisant la distance min aux ennemis (best-effort ; la
    destination exacte du pathfinding de fuite natif n'est pas portee). Les volets non observables
    (RecordFlee stats/timelines, RemoveEffects 3 phases) ne sont pas portes."""
    __slots__ = ()

    @staticmethod
    def execute(state, unit_id: int, movement: int = 3) -> Optional[dict]:
        e = state.get_entity(unit_id)
        if e is None:
            return None
        fl = e.get_component(UnitFlagsComponent)
        if fl is None:
            fl = e.add_component(UnitFlagsComponent())
        fl.add(UnitFlagsComponent.FLED)                       # UnitFlag 9 = a fui
        to = FleeOperation._safest_tile(state, unit_id, movement)
        if to is not None:
            from .movement import MoveUnitOperation
            from ..events import EventBus
            MoveUnitOperation(unit_id, to).execute(state, EventBus())
        return {"fled": unit_id, "to": to, "flag": UnitFlagsComponent.FLED}

    @staticmethod
    def _safest_tile(state, unit_id: int, movement: int):
        """Tuile atteignable (<= movement) maximisant la distance min a tout ennemi VIVANT. Requiert
        `state.board` (evenq). None si pas de board / pas d'ennemi / aucune tuile."""
        board = state.board
        e = state.get_entity(unit_id)
        if board is None or e is None:
            return None
        oc = e.get_component(OwnerComponent)
        pc = e.get_component(PositionComponent)
        if oc is None or pc is None:
            return None
        from ...entities.pathfinding.walk_pathfinder import get_movable_positions
        occ: dict = {}
        enemies: list = []
        for eid, o in state.entities.items():
            u = o.get_component(UnitComponent)
            p = o.get_component(PositionComponent)
            c = o.get_component(OwnerComponent)
            if p is None:
                continue
            t = board.id_at(p.col, p.row)
            if t is None or (u is not None and not u.alive):
                continue
            occ[t] = eid
            if c is not None and c.team != oc.team:
                enemies.append(t)
        ot = board.id_at(pc.col, pc.row)
        occ.pop(ot, None)
        _, stop = get_movable_positions(board, ot, movement, occ, oc.team)
        if not stop or not enemies:
            return None

        def mind(t):
            return min(_hex_dist(board, t, et, 99) or 99 for et in enemies)

        best = max(stop, key=lambda t: (mind(t), -t))         # plus loin des ennemis (tie-break id bas)
        return board.coord(best)


class BattleFatigueAbility(TriggeredAbility):
    """Trait `BattleFatigue` (cf. en-tete module). Trigger MORT : un ALLIE adjacent (<=2) meurt et self
    n'est pas immunise (1079) -> eligible a la fuite. Behaviour = `FleeOperation` (gate `Maybe(fleeChance)`
    documente). Gate par le trait via `BEHAVIOUR_TRAIT_TRIGGERS` (mirror Psyker/FinalJustice/ActOfFaith)."""
    event_id = EventTriggerType.PreUnitDeath

    def matches(self, state, ev) -> bool:
        if ev.dying_id is None or ev.dying_id == self.owner_id:
            return False
        owner = state.get_entity(self.owner_id)
        dying = state.get_entity(ev.dying_id)
        if owner is None or dying is None:
            return False
        ouc = owner.get_component(UnitComponent)              # OwnerActive : self vivant
        if ouc is not None and not ouc.alive:
            return False
        oo = owner.get_component(OwnerComponent)
        do = dying.get_component(OwnerComponent)
        if oo is None or do is None or oo.team != do.team:    # AreFriends(dying, self)
            return False
        if (state.effects is not None and                    # NOT HasEffect(self, 1079)
                state.effects.has_effect(self.owner_id, effect_type=IGNORE_BATTLE_FATIGUE)):
            return False
        board = state.board
        if board is None:
            return False
        ot = _unit_tile(state, board, self.owner_id)
        dt = _unit_tile(state, board, ev.dying_id)
        if ot is None or dt is None:
            return False
        d = _hex_dist(board, ot, dt, BATTLE_FATIGUE_ADJ)       # IsAdjacent(self, dying, 2)
        return d is not None and d <= BATTLE_FATIGUE_ADJ

    def execute_behaviour(self, state, ev) -> Optional[dict]:
        # Gate natif `Maybe(GetFleeChance)` (RNG, chance un-sourcable offline) : on ne tire que si une chance
        # ET un rng sont fournis ; sinon on FUIT (eligible) pour exercer/valider FleeOperation. `HasFlag(9)`
        # deja-fui : si l'unite a deja le flag, pas de re-fuite (NOT HasFlag(self,9) natif).
        owner = state.get_entity(self.owner_id)
        fl = owner.get_component(UnitFlagsComponent) if owner is not None else None
        if fl is not None and fl.has(UnitFlagsComponent.FLED):
            return {"trait": "BattleFatigue", "owner": self.owner_id, "dying": ev.dying_id,
                    "eligible": True, "flee": None, "note": "deja fui (flag 9)"}
        chance = getattr(state, "battle_fatigue_flee_chance", None)
        if chance is not None and state.rng is not None:
            from ...services.damage_combat import roll_critical  # NextBool(chance) reutilise
            if not roll_critical(state.rng, int(chance)):
                return {"trait": "BattleFatigue", "owner": self.owner_id, "dying": ev.dying_id,
                        "eligible": True, "flee": None, "note": "maybe-flee rate (no flee)"}
        res = FleeOperation.execute(state, self.owner_id)
        return {"trait": "BattleFatigue", "owner": self.owner_id, "dying": ev.dying_id,
                "eligible": True, "flee": res}


# Registre trait -> trigger(s), fusionne LAZILY par `triggers.collect_triggered_abilities` (evite l'import
# circulaire behaviour<->triggers). Mirror de `TRAIT_TRIGGERS` pour les mecaniques de comportement.
BEHAVIOUR_TRAIT_TRIGGERS: dict[str, list[type[TriggeredAbility]]] = {
    "BattleFatigue": [BattleFatigueAbility],
}
