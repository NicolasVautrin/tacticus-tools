"""Operation de PUSH (knockback) — `IdunBattle.Operations.DisplaceUnitOperation` @180e685a0.

Le PUSH d'ability (ThunderousAssault, CrushingClaws splash) = `DisplaceUnitOperation(type=1)` : le natif
`Execute(pusher, pushed, DisplacementType, ...)` route sur un switch `DisplacementType` ; **type 1 =
`FindTileToPush @180e695e0`** = pousser l'unite A L'OPPOSE du pousseur, le long de la ligne hex
pousseur->poussee PROLONGEE.

Geometrie (mirror `GetTilesBetweenInLineFromUnit @18106a580` -> `GetTilesBehind @18106a150`) : le natif
reflechit la tuile poussee a travers le pousseur (`reflected = 2*pushedCube - pusherCube`) puis marche
d'un pas UNITAIRE dans `CubeCoordinate.DirectionTo(pusher, pushed)` (PAS de pathfinding). Comme le
pousseur est ADJACENT a la poussee (push melee), la direction pousseur->poussee est l'une des 6
directions hex ; la tuile "derriere" = poussee + cette meme direction. On evite la conversion cube
(sensible a la parite even-q, deja inversee par le passe cf. project_hexgeo_parity_fix) en utilisant
directement les tables `EVENQ_EVEN`/`EVENQ_ODD` VALIDEES du board (62/62 vs natif) : les DEUX tables
listent les 6 directions dans le MEME ordre cube (verifie), donc l'index de direction est stable a
travers la parite -> marche parity-safe par lookup.

Destination (mirror partie commune de `Execute`) :
- tuile LIBRE (walkable, non occupee) -> **emet `MoveUnitOperation @180e79ff0`** (le natif reutilise
  MoveUnit ; DisplaceUnit NE reecrit PAS la position lui-meme) -> pose PositionComponent + moved_this_turn
  + tile-defense + cascade after-move (overwatch) deja cablees.
- aucune tuile valide (hors-board / mur / occupee) -> **push ANNULE** (`lVar7==0` : return sans move).
- garde `IsDisplaceable(pushed)` en tete : mort OU trait non-deplacable (Immovable=17, BigTarget=1017)
  -> **no-op** (c'est pourquoi le test de Stun utilise tyranTyrantGuard=BigTarget pour neutraliser le push).

SCOPE slice-21a (1-hex simple) : push 1 tuile, stop sur mur/bord/occupee. NON portes (=> slice-21b,
flagges) : push MULTI-hex (`maxCount`/param_9=2 natif), steppable-crush (occupant petit ecrase), knockback
DAMAGE (`ApplyKnockbackTo @180e67fc0`, peut TUER -> death-triggers), fall-damage d'elevation, absorption
par allie. La feuille `PushUnit` (DSLFactory.PushUnit @180df9540 -> DisplaceUnitBehaviour @180fc3ff0)
emet 1 DisplaceUnitOperation par unite poussee.
"""
from __future__ import annotations

from ..state import State
from ..events import EventBus
from ..components import PositionComponent, UnitComponent, StatsComponent
from .base import Operation
from .movement import MoveUnitOperation
from ...entities.pathfinding.board import EVENQ_EVEN, EVENQ_ODD
from ...entities.traits.unit_trait import UnitTrait, has_any_trait

# Distance du push, en tuiles. HARDCODE (slice-21a) : HYPOTHESE 1 hex. Le natif `PushUnit` passe
# `param_9=2` (+0x84 de DisplaceUnitBehaviour) = maxCount PROBABLE (RE non tranche) -> le push pourrait
# aller jusqu'a 2 hexes (FindTileToPush prend la tuile la plus loin atteignable). A CONFIRMER LIVE
# (test_thunderous_assault_push_live imprime dist(target,casterOrig) d0->d1 ; push = d1 - 1). Bump a 2
# si live montre 2 hexes. Le multi-hex complet (marche bornee + validite par pas) = slice-21b.
_PUSH_MAX_DIST = 1


def _dir_index(pc: int, pr: int, uc: int, ur: int) -> int | None:
    """Index (0..5) de la direction hex pousseur(pc,pr) -> poussee(uc,ur), via la table even-q de la
    PARITE du pousseur. Adjacents (push melee) => `(uc-pc,ur-pr)` est une entree de la table. None si
    non-adjacents (pas de direction unitaire)."""
    delta = (uc - pc, ur - pr)
    table = EVENQ_EVEN if pc % 2 == 0 else EVENQ_ODD
    return table.index(delta) if delta in table else None


def _step(col: int, row: int, dir_idx: int) -> tuple[int, int]:
    """Tuile suivante depuis (col,row) dans la direction hex `dir_idx`. Meme direction cube quelle que
    soit la parite (les 2 tables listent les 6 directions dans le meme ordre) -> parity-safe."""
    dc, dr = (EVENQ_EVEN if col % 2 == 0 else EVENQ_ODD)[dir_idx]
    return (col + dc, row + dr)


def _occupied(state: State, exclude_id: int) -> set[tuple[int, int]]:
    """(col,row) des unites VIVANTES sur le board, hors l'unite poussee (`exclude_id`). Base du gate
    d'occupation (mirror `TileContentComponent.IsFilled` cote destination)."""
    occ: set[tuple[int, int]] = set()
    for eid, e in state.entities.items():
        if eid == exclude_id:
            continue
        uc = e.get_component(UnitComponent)
        if uc is not None and not uc.alive:
            continue
        pc = e.get_component(PositionComponent)
        if pc is not None:
            occ.add((pc.col, pc.row))
    return occ


class DisplaceUnitOperation(Operation):
    """@180e685a0 (type=1=FindTileToPush) — push 1-hex away-from-pusher. Delegue le deplacement effectif
    a `MoveUnitOperation` (mirror natif : DisplaceUnit emet MoveUnit@0x7e, ne reecrit pas la position).
    Retour dict {moved, to, reason} pour le journal `ectx.emit` (replay-diff live)."""
    __slots__ = ("pusher_id", "pushed_id")

    def __init__(self, pusher_id: int, pushed_id: int):
        self.pusher_id = pusher_id
        self.pushed_id = pushed_id

    def execute(self, state: State, bus: EventBus) -> dict:
        board = getattr(state, "board", None)
        pushed = state.get_entity(self.pushed_id)
        pusher = state.get_entity(self.pusher_id)
        if board is None or pushed is None or pusher is None:
            return {"moved": False, "reason": "missing board/unit"}
        ppos = pushed.get_component(PositionComponent)
        upos = pusher.get_component(PositionComponent)
        if ppos is None or upos is None:
            return {"moved": False, "reason": "no position"}
        # --- IsDisplaceable (tete de Execute natif) : mort ou non-deplacable -> no-op ---
        uc = pushed.get_component(UnitComponent)
        if uc is not None and not uc.alive:
            return {"moved": False, "reason": "dead"}
        sc = pushed.get_component(StatsComponent)
        traits = getattr(sc.ctx, "traits", None) if sc is not None else None
        if has_any_trait(traits, (UnitTrait.Immovable, UnitTrait.BigTarget)):
            return {"moved": False, "reason": "not displaceable"}
        # --- direction hex pousseur->poussee (adjacent en melee) ; away = meme direction depuis poussee ---
        dir_idx = _dir_index(upos.col, upos.row, ppos.col, ppos.row)
        if dir_idx is None:
            return {"moved": False, "reason": "pusher not adjacent"}
        occ = _occupied(state, self.pushed_id)
        cur = (ppos.col, ppos.row)
        dest: tuple[int, int] | None = None
        for _ in range(_PUSH_MAX_DIST):
            nxt = _step(cur[0], cur[1], dir_idx)
            nt = board.id_at(*nxt)
            if nt is None or not board.walkable(nt):     # hors-board / mur -> stop (21b: fall/knockback ici)
                break
            if nxt in occ:                               # occupee -> stop (21b: steppable-crush / absorb)
                break
            dest = nxt
            cur = nxt
        if dest is None:
            return {"moved": False, "reason": "blocked"}  # push annule (mirror lVar7==0 : pas de move)
        MoveUnitOperation(self.pushed_id, dest).execute(state, bus)
        return {"moved": True, "to": dest}
