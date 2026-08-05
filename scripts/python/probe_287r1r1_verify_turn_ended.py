"""#287-r1-r1 -- `VerifyUnitsTurnFinishedOperation$$VerifyUnitTurnEnded` : la voie qui RE-OUVRE.

CE QUE CE PROBE MESURE, ET QUE `probe_287r1_flags_transverse.py` NE PEUT PAS MESURER.
Celui-la joue UN tour et voit la face POSE du flag `UnitFlag.NoActionAvailable`. La face qui donne
son nom a la tranche est l'autre : le RETRAIT (slot `IOperationProcessor` 0x77 =
`Core.Services.OperationProcessor$$MarkUnitAsActionAvailable`), et il n'est OBSERVABLE qu'a cheval
sur DEUX tours -- parce que le flag est COLLANT :

    `IdunBattle.Operations.StartTurnOperation$$Execute` appelle
    `IdunBattle.Entities.Components.UnitFlagsComponent$$RemoveTurnFlags(includeNoAction: 0, ...)`

`includeNoAction = 0` : le changement de tour retire `Moved` / `ArrivedAtFinalTile` / `TurnFinished`
mais **CONSERVE** `NoActionAvailable`. La SEULE voie native qui le retire est `VerifyUnitTurnEnded`,
quand l'unite regagne des options. Sans elle, une unite marquee une fois le resterait POUR TOUJOURS
-- et `IdunBattle.Entities.UnitExtensions$$HasActionLeft` (donc `AnAiGroupOperator$$GetValidUnits`
et `PlayAutomaticUnitsOperation$$Execute`) la considererait comme finie a chaque tour suivant.

LE MONTAGE, en trois temps :
  1. une unite se DEPLACE. Le natif lui pose `Moved` puis, au balayage de fin de phase,
     `NoActionAvailable` (elle a bouge -> plus de tuile ou aller ; et aucune cible a portee) ;
  2. les DEUX joueurs finissent leur tour -> `RemoveTurnFlags(includeNoAction: 0)` passe. Le flag 4
     doit SURVIVRE : c'est le premier fait que ce probe verifie, et c'est lui qui rend le retrait
     necessaire ;
  3. un message quelconque est joue -> `RunPhase` invoque le slot 0x21, `VerifyUnitTurnEnded` voit
     `Has(NoActionAvailable) && HasTilesToMoveTo` et RETIRE le flag.

Le port est confronte au MEME etat (`combatSnapshot` -> `load_state` -> `Runner.apply`), et l'on
exige l'EGALITE d'ensembles sur les flags de l'unite.

REGIMES TEMOINS -- sans eux, une egalite ne prouverait rien :
  * temps 1 : le natif DOIT poser `NoActionAvailable` (sinon rien a retirer ensuite) ;
  * temps 2 : le flag DOIT survivre au changement de tour (sinon le retrait serait sans objet, et
    ce probe mesurerait `RemoveTurnFlags`, pas `VerifyUnitTurnEnded`) ;
  * temps 3 : le natif DOIT l'avoir retire (sinon l'egalite port/natif serait celle de deux etats
    ou rien ne s'est passe).

AMPLITUDE : le probe compte, cote PORT, les poses / retraits / ABSTENTIONS rendus par
`VerifyUnitsTurnFinishedOperation.execute` a chaque message (`Runner.last_verify_turn_finished`).
Une abstention = `_can_act` indetermine (il aurait fallu un verdict que le port ne sait pas rendre) ;
c'est la mesure du residu, et elle est IMPRIMEE, jamais devinee.

Usage :
    python scripts/python/probe_287r1r1_verify_turn_ended.py
    python scripts/python/probe_287r1r1_verify_turn_ended.py --board MC1_67 --seed 28701 --keep
ASCII only ; exit 0 = les trois temps conformes.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import hexgeo
import probe_27_custom_utility_inventory as INV
from engine.entities.pathfinding.board import Board
from engine.entities.unit_flag import UnitFlag
from engine.runner.messages import EndTurnMessage, MoveUnitMessage
from engine.runner.prng import IntBasedMersenneTwister
from engine.runner.snapshot import load_state

HERE = Path(__file__).resolve().parent
LOGS = HERE.parents[1] / "logs"

BOARD = "C1_74"
SEED = 34117
P_UNITS = "ultraTitus,ultraCalgar"
A_UNITS = "thousTzaangor,thousSorcerer"
WALKER_VID = "ultraCalgar"        # celle qui BOUGE puis se fait marquer, puis re-ouvrir


def _rpc(method, args=None, timeout=90000):
    return INV.rpc(INV._session_id(), method, args, timeout)


def _run(args) -> None:
    subprocess.run([sys.executable, "rl_duel.py"] + args, cwd=str(HERE),
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)


def _pos(u):
    p = u.get("pos") or {}
    return (p.get("col"), p.get("row")) if p.get("col") is not None else None


def _dview(rid):
    return _rpc("decisionView", [{"runnerId": rid, "allAbilities": True}])


def _units(dv):
    return {u.get("visualId"): u for u in (dv.get("units") or []) if u.get("alive")}


def _flags_by_id(rid):
    cs = _rpc("combatSnapshot", [{"runnerId": rid}], 60000)
    return ({u.get("entityId"): sorted(u.get("unitFlags") or []) for u in (cs.get("units") or [])},
            cs)


def _seed_rng(s):
    rng = IntBasedMersenneTwister()
    rng.mt = list(s["mt"])
    rng.mti = s["mti"]
    return rng


def _free_at(board, center, radius, occupied):
    for t in sorted(board.by_id):
        c = board.coord(t)
        if board.walkable(t) and hexgeo.distance(center, c) == radius and c not in occupied:
            return c
    return None


def _port_replay(snap, board, uid, jouer):
    """Rejoue OFFLINE sur le MEME etat et rend `(flags du port, bilan VerifyUnitsTurnFinished)`.

    Le bilan porte AUSSI le COUT : `ms_apply` (le message complet, voie comprise) et `ms_verify`
    (la voie seule, re-jouee sur l'etat DEJA mute -- donc idempotente : elle ne change rien, elle
    ne fait que remesurer). C'est le chiffre a regarder si l'on soupconne cette voie de peser sur
    les runs, puisqu'elle balaye les unites du joueur courant a CHAQUE message."""
    import time
    from engine.runner.components import UnitFlagsComponent
    from engine.runner.runner import Runner
    from engine.runner.operations.turnflow import verify_units_turn_finished
    st = load_state(snap["dv"], snap["ob"], snap["snap"], board=board)
    if isinstance(snap["rng"], dict) and snap["rng"].get("mt"):
        st.rng = _seed_rng(snap["rng"])
    runner = Runner(st).install_default_handlers(20)
    t0 = time.perf_counter()
    jouer(runner, st)
    t1 = time.perf_counter()
    verify_units_turn_finished(st)
    t2 = time.perf_counter()
    e = st.get_entity(uid)
    fc = e.get_component(UnitFlagsComponent) if e is not None else None
    bilan = runner.last_verify_turn_finished or {}
    return (sorted(fc.flags) if fc is not None else []),  {
        "marked": bilan.get("marked"), "unmarked": bilan.get("unmarked"),
        "undetermined": bilan.get("undetermined"), "machines_skipped": bilan.get("machines_skipped"),
        "units": len(bilan.get("units") or []),
        "ms_apply": round((t1 - t0) * 1000.0, 1), "ms_verify": round((t2 - t1) * 1000.0, 1)}


def _snapshot(rid):
    return {"dv": _dview(rid), "ob": _rpc("observeBattle", [{"runnerId": rid}], 40000),
            "snap": _rpc("combatSnapshot", [{"runnerId": rid}], 60000),
            "rng": _rpc("dumpRng", [{"runnerId": rid}], 30000)}


def run(keep: bool = False, seed: int = SEED, board_name: str = BOARD,
        state_name: str = "rs_287r1r1_verify.json", p_units: str = P_UNITS,
        a_units: str = A_UNITS, walker: str = WALKER_VID) -> dict:
    global WALKER_VID
    WALKER_VID = walker
    state = LOGS / state_name
    _run(["build", "--seed", str(seed), "--board", board_name, "--rank", "17",
          "--p-units", p_units, "--a-units", a_units, "--state-file", str(state)])
    if not state.exists():
        return {"error": "build KO (state-file absent)"}
    rid = int(json.loads(state.read_text(encoding="utf-8"))["runnerId"])
    out: dict = {"runner": rid, "board": board_name, "seed": seed, "walker": WALKER_VID}
    try:
        bg = _rpc("boardGraph", [{"runnerId": rid}])
        board = Board(bg["tiles"], adjacency="native_sym")
        dv = _dview(rid)
        U = _units(dv)
        if WALKER_VID not in U:
            return dict(out, error="unite %s absente du build" % WALKER_VID)
        walker = U[WALKER_VID]
        wid = walker["id"]
        my_player = walker.get("owner")

        # ---------- TEMPS 1 : l'unite BOUGE -> le natif doit POSER `NoActionAvailable` ----------
        flags_pre, _ = _flags_by_id(rid)
        snap1 = _snapshot(rid)
        occ = {_pos(u) for u in U.values()}
        step = _free_at(board, _pos(walker), 1, occ)
        if step is None:
            return dict(out, error="aucune tuile libre adjacente pour le pas de %s" % WALKER_VID)
        _rpc("applyAction", [{"runnerId": rid, "action": {
            "kind": "move", "unitId": wid, "to": {"col": int(step[0]), "row": int(step[1])}}}],
            40000)
        flags_t1, _ = _flags_by_id(rid)
        port_t1, bilan_t1 = _port_replay(
            snap1, board, wid,
            lambda r, st: r.apply(MoveUnitMessage(unit_id=wid, to=(int(step[0]), int(step[1])))))
        out["temps1_pose"] = {"live": flags_t1.get(wid), "port": port_t1,
                              "flags_pre": flags_pre.get(wid), "bilan_port": bilan_t1,
                              "to": [int(step[0]), int(step[1])]}

        # ---------- TEMPS 2 : le tour PASSE a l'adversaire -> le flag doit SURVIVRE -------------
        # `RemoveTurnFlags` ne s'applique qu'au joueur ENTRANT : le walker n'est pas touche, et le
        # balayage 0x21 porte sur le joueur COURANT (l'adversaire). Le flag DOIT donc etre encore la.
        _rpc("applyAction", [{"runnerId": rid, "action": {"kind": "endturn"}}], 40000)
        flags_t2, _ = _flags_by_id(rid)
        out["temps2_survie"] = {"live": flags_t2.get(wid),
                                "player_courant": _dview(rid).get("currentPlayer"),
                                "player_walker": my_player}

        # ---------- TEMPS 3 : le tour REVIENT -> le natif doit RETIRER le flag ------------------
        # C'est CE message (`EndTurnMessage` de l'adversaire) qui porte tout : il enchaine
        # `ChangeTurn` + `StartTurn` -- donc `RemoveTurnFlags(includeNoAction: 0)` sur le walker,
        # qui retire `Moved`/`ArrivedAtFinalTile` et CONSERVE `NoActionAvailable` -- puis, dans la
        # MEME `RunPhase`, le slot 0x21 balaye le joueur devenu courant (celui du walker) :
        # `Has(NoActionAvailable) && HasTilesToMoveTo` -> slot 0x77, RETRAIT.
        # C'est la mesure du 2026-08-05 qui a impose ce montage : le premier jet placait le retrait
        # sur un message ULTERIEUR, et le temoin « le flag survit » a ete REFUTE (`live=[]`) -- le
        # natif avait deja re-ouvert l'unite dans la sequence d'endturn.
        snap3 = _snapshot(rid)
        _rpc("applyAction", [{"runnerId": rid, "action": {"kind": "endturn"}}], 40000)
        flags_t3, _ = _flags_by_id(rid)
        port_t3, bilan_t3 = _port_replay(snap3, board, wid,
                                         lambda r, st: r.apply(EndTurnMessage()))
        out["temps3_retrait"] = {"live": flags_t3.get(wid), "port": port_t3,
                                 "flags_avant": flags_t2.get(wid), "bilan_port": bilan_t3,
                                 "player_courant": _dview(rid).get("currentPlayer"),
                                 "porteur_du_message": "EndTurnMessage (adversaire)"}
        return out
    finally:
        if not keep:
            _run(["dispose", "--state-file", str(state)])


def main() -> int:
    ap = argparse.ArgumentParser(description="#287-r1-r1 : VerifyUnitTurnEnded pose ET retire")
    ap.add_argument("--board", default=BOARD)
    ap.add_argument("--seed", type=int, default=SEED)
    ap.add_argument("--state-file", default="rs_287r1r1_verify.json")
    ap.add_argument("--p-units", default=P_UNITS)
    ap.add_argument("--a-units", default=A_UNITS)
    ap.add_argument("--walker", default=WALKER_VID,
                    help="visualId de l'unite qui bouge puis se fait marquer/re-ouvrir")
    ap.add_argument("--keep", action="store_true")
    a = ap.parse_args()
    r = run(keep=a.keep, seed=a.seed, board_name=a.board, state_name=a.state_file,
            p_units=a.p_units, a_units=a.a_units, walker=a.walker)
    print(json.dumps(r, indent=1, sort_keys=True))
    if r.get("error"):
        print("[287r1r1] PAS MESURE : %s" % r["error"])
        return 2
    NA = int(UnitFlag.NoActionAvailable)
    ok = True

    t1, t2, t3 = r["temps1_pose"], r["temps2_survie"], r["temps3_retrait"]

    # --- TEMPS 1 : POSE. Temoin + egalite bilaterale. -----------------------------------------
    if NA not in (t1["live"] or []):
        print("[287r1r1] REGIME TEMOIN casse (temps 1) : le natif ne pose PAS %d apres le "
              "deplacement (live=%s) -- il n'y aura rien a retirer, le probe ne mesure rien"
              % (NA, t1["live"]))
        ok = False
    if sorted(t1["live"] or []) != sorted(t1["port"] or []):
        print("[287r1r1] ECHEC temps 1 (POSE) : live=%s port=%s" % (t1["live"], t1["port"]))
        ok = False

    # --- TEMPS 2 : le flag SURVIT tant que le tour n'est pas revenu. -------------------------
    if t2["player_courant"] == t2["player_walker"]:
        print("[287r1r1] PAS MESURE (temps 2) : le tour n'a PAS change de joueur (courant=%s) -- "
              "le montage suppose un adversaire actif entre les deux endturns"
              % t2["player_courant"])
        ok = False
    elif NA not in (t2["live"] or []):
        print("[287r1r1] REGIME TEMOIN casse (temps 2) : %d n'a PAS survecu au changement de tour "
              "(live=%s) -- `RemoveTurnFlags(includeNoAction: 0)` ne se comporte pas comme lu, et "
              "le retrait de `VerifyUnitTurnEnded` serait sans objet" % (NA, t2["live"]))
        ok = False

    # --- TEMPS 3 : RETRAIT. Temoin (le natif retire) + egalite bilaterale. --------------------
    if t3["player_courant"] != t2["player_walker"]:
        print("[287r1r1] PAS MESURE (temps 3) : le tour n'est pas revenu au joueur du walker "
              "(courant=%s attendu=%s)" % (t3["player_courant"], t2["player_walker"]))
        ok = False
    if NA in (t3["live"] or []):
        print("[287r1r1] REGIME TEMOIN casse (temps 3) : le natif n'a PAS retire %d (live=%s) -- "
              "l'unite n'avait donc pas regagne d'options ; le bras ne mesure pas le retrait"
              % (NA, t3["live"]))
        ok = False
    if sorted(t3["live"] or []) != sorted(t3["port"] or []):
        manque = sorted(set(t3["live"] or []) - set(t3["port"] or []))
        trop = sorted(set(t3["port"] or []) - set(t3["live"] or []))
        print("[287r1r1] ECHEC temps 3 (RETRAIT) : live=%s port=%s (manquants=%s en_trop=%s). "
              "`en_trop=[%d]` = le port n'a PAS retire le flag -> la voie 0x77 ne mord plus."
              % (t3["live"], t3["port"], manque, trop, NA))
        ok = False

    print("[287r1r1] POSE  live=%s port=%s | bilan port %s" % (t1["live"], t1["port"],
                                                               t1["bilan_port"]))
    print("[287r1r1] SURVIE au changement de tour : live=%s" % (t2["live"],))
    print("[287r1r1] RETRAIT live=%s port=%s | bilan port %s (message porte par %s)"
          % (t3["live"], t3["port"], t3["bilan_port"], t3["porteur_du_message"]))
    b1, b3 = t1["bilan_port"] or {}, t3["bilan_port"] or {}
    print("[287r1r1] AMPLITUDE (port, par message) : poses %s/%s puis %s/%s ; retraits %s puis %s ; "
          "ABSTENTIONS %s puis %s ; MoW ecartees %s"
          % (b1.get("marked"), b1.get("units"), b3.get("marked"), b3.get("units"),
             b1.get("unmarked"), b3.get("unmarked"), b1.get("undetermined"),
             b3.get("undetermined"), b1.get("machines_skipped")))
    print("[287r1r1] %s" % ("PROBE OK" if ok else "PROBE ECHEC"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
