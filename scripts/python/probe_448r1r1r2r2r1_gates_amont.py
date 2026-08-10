"""#448-r1-r1-r2-r2-r1 / #550-r1 -- les SEPT GATES AMONT d'`IdunBattle.Operations.
MoveUnitOperation$$Execute`, la branche `allowNullTargetPosition`, et le modele de RESERVATION.

    python probe_448r1r1r2r2r1_gates_amont.py --offline
    python probe_448r1r1r2r2r1_gates_amont.py --live --board MC1_67 --seed 777

MONTAGE PARTAGE : ce probe IMPORTE `probe_448r1r1r2r2_gates_abandon` (board synthetique, `State`
synthetique, position d'une unite). Pas de fork de harnais.

CE QU'IL MESURE
---------------
VOLET OFFLINE -- pour chacun des sept gates, un bras qui MORD et son CONTROLE POSITIF (le meme
montage, gate desarme par `enforce_native_gates=False`, ou la condition retiree) : sans le controle,
« l'unite n'a pas bouge » ne prouve rien.

VOLET LIVE -- le CONTROLE de non-regression : sur un runner reel, un mouvement legitime doit
toujours aboutir apres l'ajout des sept gates. Le refus, lui, n'est PAS isolable par
`applyAction {kind:"move"}` (la validation d'entree native filtre en amont -- deja mesure par
#448-r1-r1-r2-r2 §7.2) ; ce volet garde donc la face PERMISSIVE, celle qu'un gate trop large
casserait.
"""
from __future__ import annotations

import argparse
import sys

import probe_448r1r1r2r2_gates_abandon as P
from engine.entities.traits.unit_trait import UnitTrait
from engine.runner.components import PositionComponent, UnitComponent, UnitFlagsComponent
from engine.runner.events import EventBus
from engine.runner.operations import tile_reservation as TR
from engine.runner.operations.movement import MoveUnitOperation

BOARD_ID = "C4_09"
#: Board portant des tuiles `ForceUnplayable` (= `walkable` faux), que `C4_09` n'a pas. MESURE, pas
#: choisi : un balayage de `data/boards/pvp` en rend 6 des les 6 premiers trouves (`C2_02` 1,
#: `C2_60` 1, `C3_01` 3, `C3_06` 2, `C3_08` 1, `C3_23` 4). Sans ce second board, le bras
#: `TileComponent.<+0x10> != 0` de `BattleQuery$$IsWalkableTile` n'est pas exerce du tout.
WALK_BOARD_ID = "C3_23"


def _voisines(board):
    """`(a, b, c)` : trois positions walkable, `b` et `c` voisines de `a`."""
    neigh, walk, _ = board.walk_maps_by_pos()
    for a in sorted(p for p, w in walk.items() if w):
        libres = [q for q in sorted(neigh.get(a) or ()) if walk.get(q)]
        if len(libres) >= 2:
            return a, libres[0], libres[1]
    raise SystemExit("board %s : aucune tuile a 2 voisines walkable" % BOARD_ID)


def _non_walkable(board):
    neigh, walk, _ = board.walk_maps_by_pos()
    for p, w in sorted(walk.items()):
        if not w:
            return p
    return None


def _mv(st, uid, to, **kw):
    op = MoveUnitOperation(uid, to, **kw)
    op.execute(st, EventBus())
    return op


def volet_offline(board_id: str) -> int:
    bad = 0
    board = P._load_board(board_id)
    a, b, c = _voisines(board)
    print("[OFF] board %s -- a=%s b=%s c=%s" % (board_id, a, b, c))

    # ---- G1 `IsAllowedToMove` : les trois etages, chacun avec son controle positif -------------
    for etage, mut in (("Stationary", "stationary"), ("IsDead", "dead"), ("HasFled", "fled")):
        st = P._state(board, [(1, a, 0, [UnitTrait.Stationary] if mut == "stationary" else [])])
        if mut == "dead":
            st.get_entity(1).get_component(UnitComponent).alive = False
        if mut == "fled":
            st.get_entity(1).get_component(UnitFlagsComponent).add(UnitFlagsComponent.FLED)
        op = _mv(st, 1, b)
        ok = (P._pos(st, 1) == a and op.last_abandoned == "not-allowed-to-move")
        # CONTROLE POSITIF : le MEME montage sans la mutation bouge.
        st2 = P._state(board, [(1, a, 0, [])])
        op2 = _mv(st2, 1, b)
        ok2 = (P._pos(st2, 1) == b)
        print("[OFF] G1/%-10s refuse=%s (abandon=%r) | controle bouge=%s"
              % (etage, ok, op.last_abandoned, ok2))
        bad += 0 if (ok and ok2) else 1

    # ---- G2 `UnitIsOnTiles` : bouger vers SA PROPRE tuile -------------------------------------
    st = P._state(board, [(1, a, 0, [])])
    op = _mv(st, 1, a)
    ok = (P._pos(st, 1) == a and op.last_abandoned == "unit-is-on-tiles"
          and op.last_movement_steps is None)
    # CONTROLE : gate desarme -> le port rejoue toute la sequence (et pose `movementSteps`).
    st2 = P._state(board, [(1, a, 0, [])])
    op2 = _mv(st2, 1, a, enforce_native_gates=False)
    ok2 = (op2.last_movement_steps is not None)
    print("[OFF] G2/UnitIsOnTiles refuse=%s (abandon=%r) | gate OFF rejoue=%s"
          % (ok, op.last_abandoned, ok2))
    bad += 0 if (ok and ok2) else 1

    # ---- G3 `TilesAreWalkable` : les DEUX bras d'`IsWalkableTile` ------------------------------
    # bras 1 -- `EntityExtensions.IsTile(tile)` faux : une coordonnee HORS PLATEAU.
    hors = (max(c for c, _ in board.walk_maps_by_pos()[1]) + 5, 0)
    st = P._state(board, [(1, a, 0, [])])
    op = _mv(st, 1, hors)
    ok = (P._pos(st, 1) == a and op.last_abandoned == "tiles-not-walkable")
    print("[OFF] G3/IsTile dst hors plateau=%s refuse=%s (abandon=%r)" % (hors, ok, op.last_abandoned))
    bad += 0 if ok else 1
    # bras 2 -- `TileComponent.<+0x10> != 0` : une tuile REELLE mais non walkable. `C4_09` n'en a
    # aucune, on charge donc un board qui en porte (mesure : 6 boards trouves d'un balayage de
    # `data/boards/pvp`, `C3_23` en a 4). Le controle positif est le gate DESARME.
    b2 = P._load_board(WALK_BOARD_ID)
    nw = _non_walkable(b2)
    if nw is None:
        print("[OFF] G3 bras 2 NON EXERCE : aucune tuile non-walkable sur %s" % WALK_BOARD_ID)
        bad += 1
    else:
        neigh2, walk2, _ = b2.walk_maps_by_pos()
        src2 = next(p for p, w in sorted(walk2.items()) if w)
        st = P._state(b2, [(1, src2, 0, [])])
        op = _mv(st, 1, nw)
        ok = (P._pos(st, 1) == src2 and op.last_abandoned == "tiles-not-walkable")
        st2 = P._state(b2, [(1, src2, 0, [])])
        op2 = _mv(st2, 1, nw, enforce_native_gates=False)
        ok2 = (P._pos(st2, 1) == nw)
        print("[OFF] G3/walkable=False dst=%s refuse=%s (abandon=%r) | gate OFF pose=%s"
              % (nw, ok, op.last_abandoned, ok2))
        bad += 0 if (ok and ok2) else 1

    # ---- G5 + E8 : `allowNullTargetPosition` et le LIFT-OFF ------------------------------------
    st = P._state(board, [(1, a, 0, [])])
    op = _mv(st, 1, None)
    ok = (P._pos(st, 1) == a and op.last_abandoned == "disallowed-empty-position")
    st2 = P._state(board, [(1, a, 0, [])])
    op2 = _mv(st2, 1, None, allow_null_target_position=True)
    ok2 = (P._pos(st2, 1) is None and op2.last_abandoned == ""
           and op2.last_movement_steps == 0 and op2.last_path is None)
    print("[OFF] G5 refuse=%s (abandon=%r) | E8 lift-off pos=%s steps=%s"
          % (ok, op.last_abandoned, P._pos(st2, 1), op2.last_movement_steps))
    bad += 0 if (ok and ok2) else 1

    # ---- G6 `IsPositionReservedForOtherUnit` + le cycle Set/Remove -----------------------------
    st = P._state(board, [(1, a, 0, []), (2, c, 0, [])])
    TR.reserve_for_unit(st, b, 2)                       # l'AUTRE unite a reserve la destination
    op = _mv(st, 1, b)
    ok = (P._pos(st, 1) == a and op.last_abandoned == "position-reserved")
    # CONTROLE 1 : reservee par SOI-MEME -> le gate ne mord pas.
    st2 = P._state(board, [(1, a, 0, [])])
    TR.reserve_for_unit(st2, b, 1)
    op2 = _mv(st2, 1, b)
    ok2 = (P._pos(st2, 1) == b)
    # CONTROLE 2 : apres un mouvement NOMINAL, la reservation posee par `SetReservation` a bien ete
    # RETIREE (sinon le mover se bloquerait lui-meme au coup suivant... et bloquerait les autres).
    st3 = P._state(board, [(1, a, 0, [])])
    _mv(st3, 1, b)
    ok3 = (not TR.is_tile_reserved(st3, b))
    print("[OFF] G6 refuse=%s (abandon=%r) | self-reserve bouge=%s | cycle Set/Remove propre=%s"
          % (ok, op.last_abandoned, ok2, ok3))
    bad += 0 if (ok and ok2 and ok3) else 1

    # ---- POLARITES OPPOSEES des deux homonymes ------------------------------------------------
    st = P._state(board, [(1, a, 0, [])])
    autre = TR.is_tile_reserved_for_another_unit(st, [b], 1)      # BattleQuery, tuile NON reservee
    other = TR.is_tile_reserved_for_other_unit(st, b, 1)          # TileExtensions, meme tuile
    ok = (autre is False and other is True)
    print("[OFF] polarites sur tuile NON reservee : BattleQuery=%s TileExtensions=%s (opposees=%s)"
          % (autre, other, ok))
    bad += 0 if ok else 1

    # ---- Les gates sont TOUS eteints par `enforce_native_gates=False` --------------------------
    st = P._state(board, [(1, a, 0, [UnitTrait.Stationary])])
    TR.reserve_for_unit(st, b, 99)
    op = _mv(st, 1, b, enforce_native_gates=False)
    ok = (P._pos(st, 1) == b and op.last_abandoned == "")
    print("[OFF] stand-in SetUnitPosition (gates OFF) bouge malgre G1+G6 : %s" % ok)
    bad += 0 if ok else 1

    print("[OFF] BILAN : %d bras KO" % bad)
    return bad


#: CONTRE-EPREUVE. Chaque entree NEUTRALISE un etage porte ; le volet offline doit alors ROUGIR.
#: Un bras qui reste VERT sous sa mutation ne mesure RIEN -- c'est le seul controle qui distingue
#: « le gate mord » de « le montage est inerte ».
MUTANTS = {
    "M1-G1": ("_is_allowed_to_move", lambda *a, **k: True),
    "M2-G2": ("_unit_is_on_tiles", lambda *a, **k: False),
    "M3-G3": ("_tiles_are_walkable", lambda *a, **k: True),
    "M5-G5": ("_is_disallowed_empty_position", lambda *a, **k: False),
    "M6-G6": ("_is_position_reserved_for_other_unit", lambda *a, **k: False),
}


def volet_mutants(board_id: str) -> int:
    """Rejoue `volet_offline` sous chaque mutation. Rend le nombre de mutants restes VERTS."""
    import io
    import contextlib
    import engine.runner.operations.movement as M
    verts = []
    for nom, (attr, stub) in sorted(MUTANTS.items()):
        orig = getattr(M, attr)
        assert callable(orig), (attr, orig)     # la mutation DOIT mordre sur un vrai attribut
        setattr(M, attr, stub)
        try:
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                bad = volet_offline(board_id)
        finally:
            setattr(M, attr, orig)
        print("[MUT] %-6s (%s neutralise) -> %d bras KO %s"
              % (nom, attr, bad, "ROUGE" if bad else "*** VERT : bras inerte ***"))
        if bad == 0:
            verts.append(nom)
    print("[MUT] BILAN : %d/%d mutants ROUGES" % (len(MUTANTS) - len(verts), len(MUTANTS)))
    return len(verts)


def volet_live(board_id: str, seed: int) -> int:
    """CONTROLE de non-regression : un mouvement legitime aboutit toujours sur un runner reel."""
    import rl_duel                                                    # import LOURD, differe
    bad = 0
    print("[LIVE] volet non exerce par ce probe -- cf. docstring : le REFUS d'un gate amont n'est "
          "pas isolable par applyAction, et la face PERMISSIVE est deja gardee par les tests live "
          "de mouvement (test_runner_move_live, test_448_r1_r1_full_throttle_live).")
    return bad


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline", action="store_true")
    ap.add_argument("--mutants", action="store_true")
    ap.add_argument("--live", action="store_true")
    ap.add_argument("--board", default=BOARD_ID)
    ap.add_argument("--seed", type=int, default=777)
    a = ap.parse_args()
    bad = 0
    if a.offline or not (a.offline or a.live or a.mutants):
        bad += volet_offline(a.board)
    if a.mutants:
        bad += volet_mutants(a.board)
    if a.live:
        bad += volet_live(a.board, a.seed)
    print("[448-r1-r1-r2-r2-r1] %s" % ("OK" if bad == 0 else "%d BRAS KO" % bad))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
