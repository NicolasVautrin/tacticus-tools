"""#448-r1-r1-r1-r1 -- `GetNumTilesMoved(GetConnectedPathTo(...))` pour une unite VOLANTE.

LE CRITERE, pose AVANT la methode
---------------------------------
Question binaire : apres qu'un VOLANT s'est deplace de `from` a `to`, de combien le natif
incremente-t-il `ActorStatisticsComponent+0xf0` (`TilesMovedThisTurn`) ? Trois lectures sont en
concurrence, et elles DIVERGENT :

    (a) pas de MARCHE            -- ce que le port faisait AVANT (WalkPathfinder inconditionnel) ;
    (b) pas de VOL               -- la longueur du chemin de vol reellement suivi ;
    (c) chemin RECOUSU           -- ce que la chaine native rend, cf. ci-dessous.

Sur un board SANS MUR les trois peuvent coincider ; le seul trajet qui les separe TOUTES est un
vol DETOURNE, et seul un MUR detourne un vol (`FlyPathfinder$$IsValidPathNode` ne teste que
`TileComponent+0x40` = fog et `+0x41` = `IsWall`). D'ou le bras `FX` sur `C6_25`.

LA CHAINE NATIVE, etablie par RE puis RE-DERIVEE AU RUNTIME
-----------------------------------------------------------
`IdunBattle.Entities.UnitExtensions$$RecordTilesMoved(unit, n, state)` recoit
`n = IdunBattle.Core.Services.BattleQuery$$GetNumTilesMoved(connectedPath)` = `Count - 1`, et
`connectedPath = IdunBattle.Core.Services.MovementQuery$$GetConnectedPathTo(unit, from, to)` :

    type  = MovementQuery$$GetPathfinderTypeForUnit(unit)      // IsLikeFlying ? 3 : 0
    path  = pathfinders.GetPath(unit, from, to, <Nullable<UseTeleporter>>)
    ... puis, pour chaque paire de noeuds consecutifs distants de PLUS DE 1, insertion des
        tuiles intermediaires d'un `GetPath(PathfinderType.Beeline = 2, ...)`.

Pour un MARCHEUR c'est un no-op (les noeuds consecutifs sont adjacents). Pour un VOLANT,
`IdunBattle.Entities.Pathfinding.FlyPathfinder$$FindPath` **OVERRIDE** et ne rend PAS le chemin :
il le reduit a ses WAYPOINTS (extremites, tuiles de teleportation, et virages ayant un MUR dans
leur couronne -- `FlyPathfinder$$IsAnyAdjacentTileWall`). C'est `GetConnectedPathTo` qui recoud,
avec un pathfinder qui TRAVERSE TOUT.

RE-DERIVATIONS AU RUNTIME (`resolveVtableSlot`, build `rnca9r7q6c`, vtable propre depuis `+0x138`
par pas de `0x10`) -- l'absence de ces methodes des tables de symboles ne prouvait rien :

    FlyPathfinder             idx 0x0c WeightCost              -> corps TRIVIAL `return 10`
    FlyPathfinder             idx 0x09 IsValidFinalTile        -> WalkPathfinder$$IsValidFinalTile
    FlyPathfinder             idx 0x0a IsValidContinuePathTile -> corps TRIVIAL `return true`
    IgnoreEverythingPathfinder idx 0x0b IsValidPathNode        -> corps TRIVIAL `return true`
    IgnoreEverythingPathfinder idx 0x09 IsValidFinalTile       -> corps TRIVIAL `return true`

Le `WeightCost` UNIFORME est ce qui rend le port non ambigu : a cout constant, le chemin de cout
minimal EST le chemin de longueur minimale (le residu de departage de `base_pathfinder` ne mord
donc pas sur la branche volante).

CANAL D'OBSERVATION : le RPC `actorStats` (`tilesMovedThisTurn` = `+0xf0`), lu AVANT et APRES le
`applyAction move`. C'est une mesure DIRECTE et DETERMINISTE du scalaire natif -- pas un gate
probabiliste. `+0xf0` est le seul des trois compteurs mesure exact sur le bundle courant (cf.
`engine/runner/snapshot.py::_load_actor_statistics`).

Usage :
    python probe_448_r1_r1_r1_r1_flying_tiles_moved.py --offline
    python probe_448_r1_r1_r1_r1_flying_tiles_moved.py --only FD --turns 4
    python probe_448_r1_r1_r1_r1_flying_tiles_moved.py --only W  --turns 4
    python probe_448_r1_r1_r1_r1_flying_tiles_moved.py --only FX --turns 16
    python probe_448_r1_r1_r1_r1_flying_tiles_moved.py --only FX --turns 16 --mutate-walk
ASCII only.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import subprocess
import sys

PYDIR = pathlib.Path(__file__).resolve().parent
ROOT = PYDIR.parent.parent
LOGSDIR = ROOT / "logs"
sys.path.insert(0, str(PYDIR))

import probe_448_r1_r1_r1_flying_movement_steps as P     # noqa: E402  (montage reutilise)

FLY_UNITS = P.FLY_GRAFTS
WALK_UNITS = P.WALK_GRAFTS


# ------------------------------------------------------------------ ETAPE 0 (offline)
def etape0() -> int:
    """Le cablage OFFLINE de la chaine a TROIS etages, sur un board synthetique.

    Ce que l'etape 0 doit montrer, et qu'aucune valeur isolee ne montrerait :
      * sans mur, le compte volant vaut la DISTANCE (et non les pas de marche des que le
        relief ou un occupant allonge la marche) ;
      * avec des murs, `FlyPathfinder$$FindPath` rend des WAYPOINTS (moins de noeuds que le
        chemin), et `GetConnectedPathTo` les RECOUD ;
      * la beeline de recousure TRAVERSE les murs -- c'est ce qui autorise `connected` a etre
        plus court que le chemin de vol."""
    import hexgeo
    from engine.entities.pathfinding import fly_pathfinder as F
    from engine.entities.pathfinding import beeline_pathfinder as B
    from engine.services.movement_query import get_connected_path_to, get_num_tiles_moved
    from engine.runner.operations.movement import _num_tiles_moved

    bad = 0
    print("== ETAPE 0 (offline) -- la chaine `FindPath -> GetConnectedPathTo -> GetNumTilesMoved`")

    board = P._synth_board()
    src = (4, 4)
    for d in (1, 2, 3, 4):
        dst = P._dest_at_distance(board, src, d)
        if dst is None:
            continue
        fly = _num_tiles_moved(P._synth_state(board, ["Flying"], src), 1, src, dst)
        walk = _num_tiles_moved(P._synth_state(board, [], src), 1, src, dst)
        s, t = board.id_at(*src), board.id_at(*dst)
        wp = F.find_path(board, s, t)
        ok = (fly == d) and (len(wp) == 2)
        bad += 0 if ok else 1
        print("   plat d=%d dst=%-7s : VOLANT=%d (attendu %d) MARCHEUR=%d  waypoints=%d "
              "(attendu 2) %s" % (d, dst, fly, d, walk, len(wp), "OK" if ok else "FAUX"))

    # --- Le DETOUR : les trois lectures divergent.
    walls = [(3, 5), (4, 5), (5, 5), (3, 6), (5, 6)]
    bd = P._synth_board(walls)
    src, dst = (4, 4), (4, 6)
    s, t = bd.id_at(*src), bd.id_at(*dst)
    d = hexgeo.distance(src, dst)
    steps = P._fly_path_steps(bd, src, dst)
    wp = F.find_path(bd, s, t)
    conn = get_connected_path_to(bd, s, t, wp)
    n = get_num_tiles_moved(conn)
    got = _num_tiles_moved(P._synth_state(bd, ["Flying"], src), 1, src, dst)
    ok = (d == 2) and (steps > d) and (n == got) and (len(wp) < len(conn))
    bad += 0 if ok else 1
    print("   DETOUR murs=%s %s -> %s : d=%d  pas_de_vol=%d  waypoints=%d  connecte=%d  "
          "n=%d  _num_tiles_moved=%d %s"
          % (walls, src, dst, d, steps, len(wp), len(conn), n, got, "OK" if ok else "FAUX"))
    print("      waypoints  = %s" % [bd.coord(x) for x in wp])
    print("      connecte   = %s" % [bd.coord(x) for x in conn])

    # --- La beeline TRAVERSE les murs : contre-epreuve du predicat trivial `return true`.
    a, b = bd.id_at(4, 4), bd.id_at(4, 6)
    bl = B.find_path(bd, a, b)
    crosses = any(bd.is_wall(x) for x in (bl or []))
    okb = bl is not None and len(bl) - 1 == d and crosses
    bad += 0 if okb else 1
    print("   BEELINE %s -> %s : %d arete(s) (attendu %d), traverse un mur = %s %s"
          % ((4, 4), (4, 6), len(bl or []) - 1, d, crosses, "OK" if okb else "FAUX"))

    # --- La MARCHE est INCHANGEE (non-regression) : elle ne passe pas par la nouvelle chaine.
    wsrc, wdst = (4, 4), (4, 6)
    wm = _num_tiles_moved(P._synth_state(bd, [], wsrc), 1, wsrc, wdst)
    okw = wm == P._fly_path_steps(bd, wsrc, wdst) or wm >= d
    bad += 0 if okw else 1
    print("   MARCHE %s -> %s (memes murs) : %d %s" % (wsrc, wdst, wm, "OK" if okw else "FAUX"))
    return bad


# ------------------------------------------------------------------ VOLET LIVE
def _build(board: str, seed: int, tag: str, units: list, foes: list):
    """Build SANS greffe -- ce probe n'a besoin d'aucune ability : il lit un compteur."""
    LOGSDIR.mkdir(parents=True, exist_ok=True)
    state_file = LOGSDIR / ("p448r1r1r1r1_state_%s.json" % tag)
    used = list(units)
    p = None
    while used:
        state_file.unlink(missing_ok=True)
        cmd = [sys.executable, "rl_duel.py", "build", "--seed", str(seed), "--rank", "17",
               "--board", board, "--p-units", ",".join(used),
               "--a-units", ",".join(foes), "--no-ai", "--state-file", str(state_file)]
        p = subprocess.run(cmd, cwd=str(PYDIR), capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
        if state_file.exists():
            rid = int(json.loads(state_file.read_text(encoding="utf-8"))["runnerId"])
            if len(used) != len(units):
                print("     [build] %s : equipe reduite a %s" % (board, used))
            return rid, state_file, used
        if "spawns joueur <" not in (p.stdout or "") + (p.stderr or ""):
            break
        used = used[:-1]
    sys.stdout.write((p.stdout or "")[-1500:])
    sys.stdout.write((p.stderr or "")[-1500:])
    raise SystemExit("build KO (%s)" % tag)


def _actor_stats(sid, rpc, rid) -> dict:
    """Payload BRUT du RPC `actorStats`, tel que `load_state(actor_stats=...)` l'attend."""
    return rpc(sid, "actorStats", {"runnerId": rid}, 60)


def _turn_counter(ast: dict, uid: int):
    """`tilesMovedThisTurn` de `uid`, ou `None` (= NON MESURE, jamais 0 par defaut : un echec
    rendu ne doit pas pouvoir se lire comme une mesure)."""
    for u in ((ast or {}).get("units") or []):
        if u.get("entityId") is not None and int(u["entityId"]) == int(uid):
            v = u.get("tilesMovedThisTurn")
            return None if v is None else int(v)
    return None


def bras(name: str, board_id: str, seed: int, units: list, foes: list,
         mode: str, want: int, max_turns: int) -> dict:
    """Un bras : chaque porteur joue le trajet demande ; on lit `tilesMovedThisTurn` AVANT et
    APRES son move, et on compare le DELTA natif a ce que le port calcule sur l'etat d'AVANT."""
    rid, _sf, units = _build(board_id, seed, "%s_%s_%d" % (name, board_id, seed), units, foes)
    sid, rpc = P._rpc_factory()
    print("== BRAS %s  mode=%s want=%d  board=%s seed=%d  runner=%s"
          % (name, mode, want, board_id, seed, rid))
    from engine.entities.pathfinding.board import Board
    from engine.runner.components import PositionComponent
    from engine.runner.operations.movement import _num_tiles_moved
    bg = rpc(sid, "boardGraph", {"runnerId": rid}, 90)
    brd = Board(bg["tiles"], adjacency="native_sym")
    dsrcs = []
    if mode == "flyd":
        dpairs = P._detour_pairs(brd, want)
        dsrcs = sorted(dpairs)
        nwall = sum(1 for t in bg["tiles"] if t.get("isWall"))
        print("     [board] %d mur(s) ; %d depart(s) offrant un trajet DETOURNE a d=%d"
              % (nwall, len(dsrcs), want))
    rows, accord, desaccord, skips = [], 0, 0, 0
    try:
        for turn in range(max_turns):
            state, dv, _ob = P._port_state(sid, rpc, rid, brd)
            alive = P._alive_map(dv)
            to_act = [int(u) for u in (dv.get("toActivate") or [])]
            if not to_act:
                print("     t%d : toActivate vide -> fin" % turn)
                break
            carriers = P._carriers(dv, units)
            for uid in to_act:
                if not alive.get(uid, False) or uid not in carriers:
                    continue
                legal = P._legal_moves(sid, rpc, rid, uid)
                state, _, _ = P._port_state(sid, rpc, rid, brd)
                got = P._pick(state, brd, uid, legal, mode, want)
                if got is None:
                    e = state.get_entity(int(uid))
                    pc = e.get_component(PositionComponent) if e is not None else None
                    step = (P._approach(brd, (pc.col, pc.row), legal, dsrcs)
                            if (mode == "flyd" and pc is not None) else None)
                    if step is not None:
                        rpc(sid, "applyAction", {"runnerId": rid, "action": {
                            "kind": "move", "unitId": int(uid),
                            "to": {"col": int(step[0]), "row": int(step[1])}}}, 120)
                        print("     t%d u%s (%d,%d) -> %s : APPROCHE" % (turn, uid, pc.col,
                                                                        pc.row, step))
                        continue
                    skips += 1
                    continue
                dest, info = got
                src = info["src"]
                port_n = _num_tiles_moved(state, int(uid), src, dest)
                before = _turn_counter(_actor_stats(sid, rpc, rid), uid)
                rpc(sid, "applyAction", {"runnerId": rid, "action": {
                    "kind": "move", "unitId": int(uid),
                    "to": {"col": int(dest[0]), "row": int(dest[1])}}}, 120)
                after = _turn_counter(_actor_stats(sid, rpc, rid), uid)
                if before is None or after is None:
                    print("     t%d u%s : capteur MUET (tilesMovedThisTurn absent) -- NON MESURE"
                          % (turn, uid))
                    skips += 1
                    continue
                nat = after - before
                ok = nat == port_n
                accord += 1 if ok else 0
                desaccord += 0 if ok else 1
                rows.append({"turn": turn, "unit": uid, "src": list(src), "dest": list(dest),
                             "natif": nat, "port": port_n, "info": info})
                print("     t%d u%s %s -> %s (%s) : NATIF=%d PORT=%d %s"
                      % (turn, uid, src, dest,
                         " ".join("%s=%s" % kv for kv in sorted(info.items()) if kv[0] != "src"),
                         nat, port_n, "OK" if ok else "DESACCORD"))
            rpc(sid, "applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 120)
    finally:
        try:
            rpc(sid, "disposeRunner", {"runnerId": rid}, 60)
        except Exception:
            pass
    print("   -> BRAS %s : %d accord(s) / %d mesure(s)  (%d skip)"
          % (name, accord, accord + desaccord, skips))
    return {"name": name, "mode": mode, "want": want, "accord": accord,
            "desaccord": desaccord, "skips": skips, "rows": rows,
            "board": board_id, "seed": seed}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline", action="store_true")
    ap.add_argument("--board", default="MC1_67")
    ap.add_argument("--detour-board", default="C6_25",
                    help="le SEUL board mesure a offrir des trajets de vol DETOURNES a d=2 "
                         "(cf. case-448-r1-r1-r1 : 17 boards a murs balayes, C6_09 en a 16 et "
                         "n'en produit AUCUN -- sa barriere deconnecte le plateau)")
    ap.add_argument("--seed", type=int, default=777)
    ap.add_argument("--foes", default="tauCrisis")
    ap.add_argument("--turns", type=int, default=4)
    ap.add_argument("--want", type=int, default=2)
    ap.add_argument("--only", default="", help="sous-ensemble des bras (FD,FD3,W,FX)")
    ap.add_argument("--mutate-walk", action="store_true",
                    help="CONTRE-EPREUVE : le volant repasse par le WalkPathfinder (le port "
                         "d'AVANT #448-r1-r1-r1-r1). Le bras FX doit DIVERGER du natif.")
    ap.add_argument("--json", default="")
    a = ap.parse_args()

    if a.mutate_walk:
        from engine.entities.pathfinding import fly_pathfinder as FP
        FP.is_like_flying = lambda traits: False      # le vol redevient de la marche
        print("!! CONTRE-EPREUVE --mutate-walk : branche volante NIEE (WalkPathfinder partout)")

    bad = etape0()
    print("   etape 0 : %d anomalie(s)" % bad)
    if a.offline:
        return 1 if bad else 0

    foes = [s for s in a.foes.split(",") if s]
    want = {k: True for k in (a.only.split(",") if a.only else ["FD", "W", "FX"])}
    out = {}
    if want.get("FD"):
        out["FD"] = bras("FD", a.board, a.seed, FLY_UNITS, foes, "fly", a.want, a.turns)
    if want.get("FD3"):
        out["FD3"] = bras("FD3", a.board, a.seed, FLY_UNITS, foes, "fly", 3, a.turns)
    if want.get("W"):
        out["W"] = bras("W", a.board, a.seed, WALK_UNITS, foes, "walk", a.want, a.turns)
    if want.get("FX"):
        out["FX"] = bras("FX", a.detour_board, a.seed, FLY_UNITS, foes, "flyd", a.want, a.turns)

    print("\n== SYNTHESE")
    for k in ("FD", "FD3", "W", "FX"):
        b = out.get(k)
        if b:
            print("   %-3s %-4s d=%d : %d accord / %d mesure(s), %d desaccord"
                  % (k, b["mode"], b["want"], b["accord"], b["accord"] + b["desaccord"],
                     b["desaccord"]))
    if a.json:
        pathlib.Path(a.json).write_text(json.dumps(out, indent=1), encoding="utf-8")
    bad += sum(b["desaccord"] for b in out.values())
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
