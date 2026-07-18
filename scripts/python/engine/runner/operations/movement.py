"""Operations de mouvement — `IdunBattle.Operations.MoveUnitOperation` @180e79ff0.

Tranche 1, INCRÉMENT 1a (POSITION) : écrit la position finale du mover dans son
`PositionComponent`. C'est le cœur observable du move (le natif fait aussi la
validation, CalculatePaths, AddMoveEvent/pas, charging…, mais l'EFFET d'ÉTAT sur
le mover = sa position finale).

G1 (gen-stealer) : `KillSteppableUnits @180e7c410` PORTÉ ici (`_kill_steppable_units`),
INLINE dans l'ordre natif (avant `EvaluateAfterMoveTriggers`) — un occupant Steppable
(decoy/spore-mine) de la tuile d'arrivée est crushé (kill propre, sans death-trigger).

INCRÉMENT 1b (à venir, validé vs la vérité-terrain probe = Maugan Ra 1174 sur le
mover) : `EvaluateAfterMoveTriggers` @180e79770 → cascade OVERWATCH
(`Overwatch_AutoAttackEffect` → auto-attaque → dégât + consommation de l'effet).
`AddMoveEvent` @180e78d20 émet l'event UnitMoved(step 3) + tuiles du chemin sur le bus.
"""
from __future__ import annotations

from ..state import State
from ..events import EventBus
from ..components import PositionComponent, UnitComponent, StatsComponent, HealthComponent
from .base import Operation


def _kill_steppable_units(state: State, dest_tile: tuple[int, int], mover_id: int) -> list:
    """`MoveUnitOperation$$KillSteppableUnits @180e7c410` — étape INLINE du move pipeline (avant
    `EvaluateAfterMoveTriggers`). Quand une unité MOVE sur `dest_tile`, tout occupant `Steppable`
    (`IsSteppable @180ed8fc0` = `HasTrait(0x1b=27)`) VIVANT y est détruit par un kill **propre**
    (`KillUnitOperationOptions$$ForSteppable @180e762c0`, type=2 flags 0x0101) : `alive=False` (hp 0) SANS
    passer par `after_death_triggers`/`On(1)` — un decoy/spore-mine crushé ne déclenche donc PAS les
    death-triggers de combat (ex. l'Ambush du decoy — cf. G3). `mover_id` est exclu (une unité ne se crushe
    pas elle-même). Renvoie les ids crushés. Ordre natif : `AddMoveEvent` → **KillSteppableUnits** →
    `EvaluateAfterMoveTriggers` (d'où le decoy déjà mort quand DecoysAndMisdirection lit `GetValidDeadDecoys`,
    G2)."""
    from ...entities.traits import UnitTrait, has_trait
    killed: list = []
    for uid, e in list(state.entities.items()):
        if uid == mover_id:
            continue
        pc = e.get_component(PositionComponent)
        uc = e.get_component(UnitComponent)
        if pc is None or uc is None or not uc.alive:
            continue
        if (pc.col, pc.row) != dest_tile:
            continue
        sc = e.get_component(StatsComponent)
        traits = getattr(sc.ctx, "traits", None) if sc is not None else None
        if not has_trait(traits or [], UnitTrait.Steppable):
            continue
        uc.alive = False                              # kill PROPRE (ForSteppable) : PAS de after_death_triggers
        hc = e.get_component(HealthComponent)
        if hc is not None:
            hc.hp = 0
        killed.append(uid)
    return killed


class MoveUnitOperation(Operation):
    """@180e79ff0 (1a) — pose la position finale du mover. `to` = (col,row)."""
    __slots__ = ("unit_id", "to")

    def __init__(self, unit_id: int, to: tuple[int, int]):
        self.unit_id = unit_id
        self.to = to

    def execute(self, state: State, bus: EventBus) -> None:
        e = state.get_entity(self.unit_id)
        if e is None:
            return
        pc = e.get_component(PositionComponent)
        old_pos = (pc.col, pc.row) if pc is not None else None
        if pc is None:
            e.add_component(PositionComponent(self.to[0], self.to[1]))
        else:
            pc.col, pc.row = self.to
        # #60 has_moved : marque l'unite "a bouge ce tour" (gate no-move HeavyWeapon lu en combat).
        state.moved_this_turn.add(self.unit_id)
        # #198 : materialisation DYNAMIQUE du stat-mod DEFENSE de tuile (Thorns/famille). En quittant/
        # entrant une tuile a stat-mod DEFENSE, l'occupant non-Immune gagne/perd la modification (mirror
        # ThornsDefenseReductionEffect apply-on-enter/revert-on-leave). No-op hors terrain a stat-mod /
        # sans board / Immune. On saute un ajout d'entite (pc None = spawn, pas un move de tuile-a-tuile).
        if old_pos is not None:
            from .triggers.tiles import apply_tile_defense_on_move
            apply_tile_defense_on_move(state, self.unit_id, old_pos, self.to)
        # G1 (gen-stealer) `KillSteppableUnits @180e7c410` : INLINE ici, dans l'ordre natif (AddMoveEvent ->
        # **KillSteppableUnits** -> EvaluateAfterMoveTriggers). Un occupant Steppable (decoy, spore-mine) de la
        # tuile d'arrivée est crushé (kill propre, pas de death-trigger) AVANT que le vecteur after-move
        # (visit_MoveUnitMessage -> after_move_triggers) ne s'exécute -> le decoy est déjà mort pour G2.
        _kill_steppable_units(state, self.to, self.unit_id)
        # INCRÉMENT 1b : AddMoveEvent (bus) + EvaluateAfterMoveTriggers (overwatch) ici.


class MovementHandler:
    """Visiteur des messages de mouvement (mirror du handler natif qui lance
    MoveUnitOperation). Lié à l'état/bus du runner. `after_move` = résultats du vecteur after-move
    (effet-triggers ; ex. Overwatch) du dernier move."""
    __slots__ = ("state", "bus", "after_move")

    def __init__(self, state: State, bus: EventBus):
        self.state = state
        self.bus = bus
        self.after_move: list = []          # cascade after-move (overwatch…) du dernier move

    def visit_MoveUnitMessage(self, msg) -> None:
        MoveUnitOperation(msg.unit_id, msg.to).execute(self.state, self.bus)
        # VECTEUR AFTER-MOVE : dispatcher générique (mirror `EvaluateAfterMoveTriggers`). Déclenche les
        # effet-triggers after-move (Overwatch…). No-op si pas de board/rng ou aucun trigger en portée.
        from .triggers import after_move_triggers
        self.after_move = after_move_triggers(self.state, msg.unit_id)
