"""#448-r1-r2-r1 -- LA RESERVATION DE `MoveUnitOperation`, ET LE SEUL REGIME OU ELLE S'OBSERVE.

L'ENONCE DU RESIDU EST PERIME -- TOUT EST PORTE DEPUIS #550-r1
--------------------------------------------------------------
Il dit : « La RESERVATION de `MoveUnitOperation` n'est pas portee [...] Sans lecteur porte,
l'ecrire serait un no-op ; le fermer suppose de porter d'abord le gate G6 et de monter ce regime. »

Re-mesure sur `88471bcd` : les TROIS pieces existent.

  * `MoveUnitOperation$$SetReservation(unit, position)` -> `movement.py::execute`, boucle
    `tile_reservation.reserve_for_unit`, posee AVANT le vecteur `On(0x1f = PreUnitMove)` ;
  * `MoveUnitOperation$$RemoveReservation(unit, position)` -> `movement.py::_remove_reservation`,
    aux CINQ chemins (quatre abandons + le nominal) ;
  * le lecteur `MoveUnitOperation$$IsPositionReservedForOtherUnit` = `BattleQuery.<slot 0xa5>`
    -> le gate G6, `movement.py::_is_position_reserved_for_other_unit`.

Les trois mirrors natifs sont relus ici et sont exacts :

    SetReservation(unit, position)     foreach (tile in position) TileExtensions.ReserveForUnit(tile, unit)
    RemoveReservation(unit, position)  foreach (tile in position) TileExtensions.RemoveReserveForUnit(tile, unit)
    IsPositionReservedForOtherUnit     BattleQuery.<0xa5>(position, unit) + un log

CE QUI RESTAIT VRAI, ET QUE CE PROBE MONTE
------------------------------------------
La reservation n'a **aucune duree de vie hors d'un mouvement** : les quatre autres poseurs du
binaire (`DSLBehaviors$$Reserve`, xrefs = `TheQuickeningAbility$$ExecuteBehaviour` x2,
`NovaBoost_AttackAbility$$CreateBehaviour`, `EreWeGo_AttackAbility$$CreateBehaviour`,
`ItItchesAbility$$ExecuteBehaviour` x2) la RETIRENT dans le meme arbre. Le seul intervalle ou une
tuile est reservee est donc **entre `SetReservation` et `RemoveReservation` d'un mouvement en
cours** -- c'est-a-dire pendant le vecteur `On(0x1f = PreUnitMove)` et pendant le corps du move.

⇒ G6 ne peut mordre que sur un **mouvement IMBRIQUE dans un autre**, ce que le port mono-thread
n'atteint que si un trigger `PreUnitMove` lance lui-meme un `MoveUnitOperation` vers la meme
tuile. C'est ce regime-la que le residu declarait non montable, et c'est celui-ci qu'on monte :
on substitue `move_death.pre_move_triggers` (forme MODULE cote `execute`, donc le `setattr` MORD)
par un trigger qui lance le mouvement concurrent.

Quatre bras, dont DEUX TEMOINS -- sans eux, « la seconde unite n'a pas bouge » se lirait comme un
verdict alors que ce pourrait etre un montage inerte :

  B1 TEMOIN      aucun mouvement en cours -> le mouvement de U2 vers T REUSSIT
  B2 REGIME      U1 bouge vers T, et son trigger pre-move lance U2 vers T -> U2 est REFUSE,
                 `last_abandoned == "position-reserved"`
  B3 CONTRE-EPREUVE  meme regime, `SetReservation` neutralise -> U2 PASSE et se SUPERPOSE a U1
  B4 CYCLE       apres le mouvement de U1, la tuile n'est PLUS reservee -> U2 y va librement

    python probe_448r1r2r1_reservation_regime.py --board C4_09
"""
from __future__ import annotations

import argparse
import pathlib
import sys

PYDIR = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(PYDIR))

import probe_448r1r1r2r2_gates_abandon as GA                                   # noqa: E402
import probe_448r1r1r3_double_parcours as DP                                   # noqa: E402
from engine.runner.components import PositionComponent                         # noqa: E402
from engine.runner.events import EventBus                                      # noqa: E402
from engine.runner.operations import tile_reservation as TR                    # noqa: E402
from engine.runner.operations.movement import MoveUnitOperation                # noqa: E402
from engine.runner.operations.triggers.dispatch import move_death              # noqa: E402


def _pos(st, uid):
    e = st.get_entity(uid)
    pc = e.get_component(PositionComponent) if e is not None else None
    return None if pc is None else (pc.col, pc.row)


def _geometrie(board):
    """`(a, b, t)` : `a` et `b` walkable et NON adjacentes entre elles, toutes deux adjacentes a
    `t`. Les deux unites peuvent donc VISER `t` sans se bloquer l'une l'autre par le pathfinder --
    sans quoi un refus s'expliquerait par `UnitIsBlockedByEnemyUnit`, pas par la reservation."""
    neigh, walk, _elev = board.walk_maps_by_pos()
    for t in sorted(q for q, w in walk.items() if w):
        vois = sorted(q for q in (neigh.get(t) or ()) if walk.get(q))
        for i, a in enumerate(vois):
            for b in vois[i + 1:]:
                if b not in (neigh.get(a) or ()):
                    return a, b, t
    return None


def volet(board_id: str) -> int:
    bad = 0
    board = GA._load_board(board_id)
    g = _geometrie(board)
    if g is None:
        print("[RES] SANS OBJET : pas de couple non-adjacent partageant une voisine sur %s"
              % board_id)
        return 1
    a, b, t = g
    print("[RES] board %s : U1 en %s, U2 en %s, cible COMMUNE %s (U1 et U2 NON adjacentes)"
          % (board_id, a, b, t))

    # ---- B1 : TEMOIN -- hors de tout mouvement en cours, U2 atteint `t`.
    st = DP._state(board, [(1, a, 1, []), (2, b, 1, [])])
    op = MoveUnitOperation(2, t)
    op.execute(st, EventBus())
    ok = (_pos(st, 2) == t and op.last_abandoned == "")
    bad += 0 if ok else 1
    print("[B1] TEMOIN   U2 %s -> %s hors regime : pos=%s abandon=%r => %s"
          % (b, t, _pos(st, 2), op.last_abandoned, "OK (le montage MORD)" if ok else "INERTE"))
    if not ok:
        print("[B1] le temoin ne mord pas : les bras suivants ne prouveraient RIEN")
        return bad

    # ---- B2 : LE REGIME -- U1 bouge vers `t`, son trigger pre-move lance U2 vers `t`.
    # `execute` resout `move_death.pre_move_triggers` par le GLOBAL du module `move_death`
    # (`from .triggers.dispatch import move_death` puis `move_death.pre_move_triggers(...)`),
    # donc ce `setattr` MORD -- une liaison directe hissee le rendrait INERTE, en silence.
    def _lance_le_concurrent(etat, sous_op):
        vrai = move_death.pre_move_triggers

        def stub(state, mover_id, dest_tile=None):
            if int(mover_id) == 1:                      # pendant le mouvement de U1, et lui seul
                sous_op.execute(state, EventBus())
            return vrai(state, mover_id, dest_tile=dest_tile)
        move_death.pre_move_triggers = stub
        try:
            MoveUnitOperation(1, t).execute(etat, EventBus())
        finally:
            move_death.pre_move_triggers = vrai

    st = DP._state(board, [(1, a, 1, []), (2, b, 1, [])])
    sous = MoveUnitOperation(2, t)
    _lance_le_concurrent(st, sous)
    ok = (_pos(st, 2) == b and sous.last_abandoned == "position-reserved" and _pos(st, 1) == t)
    bad += 0 if ok else 1
    print("[B2] REGIME   U1 %s -> %s ; son trigger pre-move lance U2 vers %s"
          % (a, t, t))
    print("[B2]          U2 pos=%s (attendu %s) abandon=%r ; U1 pos=%s => %s"
          % (_pos(st, 2), b, sous.last_abandoned, _pos(st, 1), "OK" if ok else "ROUGE"))

    # ---- B3 : CONTRE-EPREUVE -- `SetReservation` neutralise, U2 PASSE et se SUPERPOSE.
    # Sans ce bras, le refus de B2 serait compatible avec « U2 est refuse pour une autre raison ».
    st = DP._state(board, [(1, a, 1, []), (2, b, 1, [])])
    sous = MoveUnitOperation(2, t)
    vrai_res = TR.reserve_for_unit
    TR.reserve_for_unit = lambda *a_, **k_: False       # `SetReservation` devient un no-op
    try:
        _lance_le_concurrent(st, sous)
    finally:
        TR.reserve_for_unit = vrai_res
    ok = (_pos(st, 2) == t and sous.last_abandoned == "")
    bad += 0 if ok else 1
    print("[B3] CONTRE-EPREUVE  `SetReservation` no-op : U2 pos=%s abandon=%r => %s"
          % (_pos(st, 2), sous.last_abandoned,
             "OK (SUPERPOSITION -- c'est bien la reservation qui refusait)"
             if ok else "ROUGE (le refus de B2 vient d'ailleurs)"))

    # ---- B4 : LE CYCLE -- apres le mouvement de U1, plus rien n'est reserve.
    st = DP._state(board, [(1, a, 1, []), (2, b, 1, [])])
    MoveUnitOperation(1, t).execute(st, EventBus())
    reste = dict(getattr(st, "tile_reservations", None) or {})
    # U1 occupe `t` : U2 ne peut plus y aller (gate `TilesAreEmpty`), mais le refus doit venir de
    # l'OCCUPATION, pas d'une reservation qui aurait survecu -- deux raisons distinctes.
    op2 = MoveUnitOperation(2, t)
    op2.execute(st, EventBus())
    ok = (not reste and op2.last_abandoned == "tiles-not-empty")
    bad += 0 if ok else 1
    print("[B4] CYCLE    reservations restantes=%s ; U2 refuse pour %r => %s"
          % (reste, op2.last_abandoned,
             "OK (retrait complet ; le refus vient de l'OCCUPATION)" if ok else "ROUGE"))
    return bad


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--board", default="C4_09")
    a = ap.parse_args()
    bad = volet(a.board)
    print("\n[448-r1-r2-r1] %s (%d rouge(s))" % ("OK" if bad == 0 else "ROUGE", bad))
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
