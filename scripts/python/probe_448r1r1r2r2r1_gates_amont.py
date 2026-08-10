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


def _flags(rpc, sid, rid, entity_id):
    """`unitFlags` de l'unite, depuis `combatSnapshot.units[]` (cle `entityId`, canal #210).
    `None` = NON MESURE (capteur muet) -- jamais rabattu sur une liste vide."""
    if entity_id is None:
        return None
    cs = rpc(sid, "combatSnapshot", {"runnerId": rid}, 90)
    us = cs.get("units") or []
    for u in us:
        if u.get("entityId") is not None and int(u["entityId"]) == int(entity_id):
            fl = u.get("unitFlags")
            return None if fl is None else sorted(int(f) for f in fl)
    # Le capteur a repondu mais l'entite n'y est pas : le DIRE, plutot que rendre un `None` muet
    # qu'on lirait comme « capteur mort » (tri-etat, meme regle que `host_inputs`).
    print("[LIVE] combatSnapshot : entityId %r absent (cles top=%s, %d units, ids=%s)"
          % (entity_id, sorted(cs.keys())[:8], len(us),
             [u.get("entityId") for u in us][:12]))
    return None


def volet_live(board_id: str, seed: int) -> int:
    """LE SEUL des sept gates qui soit DRIVABLE de l'exterieur : **G2 `UnitIsOnTiles`**.

    Les six autres ne le sont pas -- `applyAction {kind:"move"}` traverse la validation d'entree
    native avant d'atteindre `MoveUnitOperation$$Execute`, et une destination non walkable / reservee
    / vide n'est dans aucun canal d'action (mesure #448-r1-r1-r2-r2 §7.2). G2, lui, se demande : la
    tuile COURANTE de l'unite est une coordonnee parfaitement legale.

    DISCRIMINANT, et il est OBSERVABLE : un mouvement vers SA PROPRE tuile ne doit poser AUCUN
    `UnitFlag.Moved`. Le port d'AVANT le posait (il jouait toute la sequence : vecteur pre-move,
    ecriture de position, `SetMovedFlag`, `RecordTilesMoved`, vecteur after-move) -- et `Moved` ferme
    la regle de ciblage `CasterHasNotMoved` de tout cast ulterieur du MEME tour. La degradation etait
    donc silencieuse ET consequente.

    Trois bras : le CONTROLE POSITIF (un vrai pas pose `Moved`), le bras G2 en LIVE, et le meme
    bras rejoue COTE PORT sur un etat construit depuis le `boardGraph` du runner, gates ON puis OFF.
    """
    import json
    import subprocess
    import sys as _sys
    from pathlib import Path

    bad = 0
    sid, rpc = P._rpc_factory()
    # `logs/` DE LA RACINE, jamais `scripts/python/logs` (#455, #547-r6). La banque de cliquets
    # ENUMERE `scripts/python/**` en parallele : y creer un fichier le fait apparaitre puis
    # disparaitre sous les pieds d'un voisin -- `probe_440` a deja rougi la-dessus, a raison. Et
    # `probe_273` etape 0 le voyait : `scripts/python/logs` y sortait en `[FAIL]`, ce qui rendait
    # `tests/test_host_inputs_offline.py::test_probe_273_passe` ROUGE sur `master`. La convention
    # du depot est `parents[2] / "logs" / "runners"` (12 probes la portent deja).
    logs = Path(__file__).resolve().parents[2] / "logs" / "runners"
    logs.mkdir(parents=True, exist_ok=True)
    state_file = logs / "p448r1r1r2r2r1_state.json"
    state_file.unlink(missing_ok=True)
    cmd = [_sys.executable, "rl_duel.py", "build", "--seed", str(seed), "--rank", "17",
           "--board", board_id, "--no-ai", "--state-file", str(state_file)]
    pr = subprocess.run(cmd, cwd=str(Path(__file__).resolve().parent), capture_output=True,
                        text=True, encoding="utf-8", errors="replace")
    if not state_file.exists():
        _sys.stdout.write((pr.stdout or "")[-1500:])
        _sys.stdout.write((pr.stderr or "")[-1500:])
        print("[LIVE] build KO -- NON CONFRONTE")
        return 1
    rid = int(json.loads(state_file.read_text(encoding="utf-8"))["runnerId"])
    print("[LIVE] runner %d sur %s (seed %d)" % (rid, board_id, seed))
    try:
        board = P._board_from_graph(rpc, sid, rid)
        neigh, walk, _elev = board.walk_maps_by_pos()
        dv = rpc(sid, "decisionView", {"runnerId": rid, "maxRank": 1}, 90)
        pos0 = P._pos_by_squad(rpc, sid, rid)
        mine = [int(x) for x in (dv.get("toActivate") or []) if pos0.get(int(x)) is not None]
        if not mine:
            print("[LIVE] aucune unite jouable -- NON CONFRONTE")
            return 1
        uid = mine[0]
        p0 = pos0[uid]
        # ⚠ TROIS identifiants circulent, et DEUX portent le meme nom. MESURE sur ce runner :
        # `decisionView.toActivate` et `observeBattle.units[].squadId` valent 77,79,...,95 ;
        # `combatSnapshot.units[].entityId` vaut EXACTEMENT ces memes 77..95 ; mais
        # `observeBattle.units[].entityId` vaut 78,80,...,96 (decale de 1) et n'indexe RIEN dans
        # `combatSnapshot`. La cle des flags est donc le `squadId`, malgre le nom du champ. Passer
        # par `observeBattle.entityId` rendait « capteur muet » sur un capteur vivant.
        eid = uid
        f0 = _flags(rpc, sid, rid, eid)
        if f0 is None:
            print("[LIVE] unitFlags NON MESURE (capteur muet) -- aucun verdict")
            return 1
        # --- BRAS G2 : move vers SA PROPRE tuile.
        r = rpc(sid, "applyAction", {"runnerId": rid,
                                     "action": {"kind": "move", "unitId": uid,
                                                "to": {"col": p0[0], "row": p0[1]}}}, 60)
        p1 = P._pos_by_squad(rpc, sid, rid).get(uid)
        f1 = _flags(rpc, sid, rid, eid)
        ok_g2 = (p1 == p0 and f1 == f0)
        print("[LIVE] G2 move %s -> %s (SA tuile) : pos %s->%s, unitFlags %s->%s (mutated=%s) => %s"
              % (p0, p0, p0, p1, f0, f1, r.get("mutated"),
                 "natif NE BOUGE NI NE MARQUE" if ok_g2 else "*** le natif a mute ***"))
        bad += 0 if ok_g2 else 1
        # --- CONTROLE POSITIF : un vrai pas, lui, pose `Moved`.
        occ = {p for p in P._pos_by_squad(rpc, sid, rid).values() if p is not None}
        libre = next((q for q in sorted(neigh.get(p0) or ()) if walk.get(q) and q not in occ), None)
        if libre is None:
            print("[LIVE] pas de voisine libre -- CONTROLE POSITIF IMPOSSIBLE, aucun verdict")
            return bad + 1
        rpc(sid, "applyAction", {"runnerId": rid,
                                 "action": {"kind": "move", "unitId": uid,
                                            "to": {"col": libre[0], "row": libre[1]}}}, 60)
        p2 = P._pos_by_squad(rpc, sid, rid).get(uid)
        f2 = _flags(rpc, sid, rid, eid)
        ok_ctrl = (p2 == libre and f2 != f1)
        print("[LIVE] CONTROLE POSITIF move %s -> %s : pos %s, unitFlags %s => %s"
              % (p0, libre, p2, f2, "MORD" if ok_ctrl else "*** MONTAGE INERTE ***"))
        bad += 0 if ok_ctrl else 1
        # --- LE MEME BRAS COTE PORT, sur le boardGraph du MEME runner.
        st = P._state(board, [(uid, p0, 0, [])])
        op_on = _mv(st, uid, p0)
        fl_on = st.get_entity(uid).get_component(UnitFlagsComponent)
        st2 = P._state(board, [(uid, p0, 0, [])])
        _mv(st2, uid, p0, enforce_native_gates=False)
        fl_off = st2.get_entity(uid).get_component(UnitFlagsComponent)
        ok_port = (not fl_on.has(UnitFlagsComponent.MOVED)
                   and fl_off.has(UnitFlagsComponent.MOVED)
                   and op_on.last_abandoned == "unit-is-on-tiles")
        print("[LIVE] PORT sur le MEME graphe : gates ON -> Moved=%s (abandon=%r) | gates OFF -> "
              "Moved=%s => %s"
              % (fl_on.has(UnitFlagsComponent.MOVED), op_on.last_abandoned,
                 fl_off.has(UnitFlagsComponent.MOVED),
                 "ACCORD avec le natif" if ok_port else "*** DESACCORD ***"))
        bad += 0 if ok_port else 1
    finally:
        try:
            rpc(sid, "disposeRunner", {"runnerId": rid}, 30)
            print("[LIVE] runner %d dispose" % rid)
        except Exception as exc:                                  # noqa: BLE001
            print("[LIVE] dispose KO : %s" % exc)
    print("[LIVE] BILAN : %d bras KO" % bad)
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
