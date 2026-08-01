#!/usr/bin/env python
"""Probe `#381-r3` -- l'arete que le `ConnectivityComponent` ne porte pas, mesuree A PORTEE 1.

POURQUOI CE MONTAGE
-------------------
Sur `C1_74` a la position de SPAWN, l'ecart de voisinage arrive dilue : `tauAunShi` sur-atteint de
2 tuiles au bout d'un chemin de 5 pas, et rien ne dit LAQUELLE des aretes est en cause. Ce probe
DEPLACE une unite jusqu'a poser son pied SUR une tuile-charniere, puis mesure a
`overrideRange = 1` : l'ecart se reduit alors a UNE arete, nommee, et l'ambiguite tombe.

Une tuile-charniere = une tuile qui a, dans la GEOMETRIE hex, un voisin a `|dElev| <= 1` que sa
liste d'adjacence STOCKEE ne porte PAS. C'est exactement ce qui separe les deux corps du slot
virtuel `AddNeighbours` :

  * `IdunBattle.Entities.Pathfinding.BasePathfinder$$AddNeighbours` enumere le
    `ConnectivityComponent` de la tuile -> la MARCHE ne franchit pas l'arete ;
  * `IdunBattle.Entities.Pathfinding.FlyPathfinder$$AddNeighbours` interroge la requete de tuiles
    au rayon 1 -> le VOL la franchit.

Les autres aretes geometriques absentes du champ capte (`|dElev| >= 2`) ne prouvent RIEN : la porte
`|dElev| < 2` de `IdunBattle.Core.Services.TileQuery$$IterateAdjacentTiles` les retire du capteur,
mais `WalkPathfinder$$IsValidPathNode` les refuse de toute facon. Le probe les IGNORE et ne retient
que les charnieres -- sinon il compterait comme validation une geometrie qui ne discrimine pas.

L'ORACLE est `aiMovableTiles`, qui appelle LITTERALEMENT
`IdunBattle.Core.Services.MovementQuery$$GetMovableTilesFor` : egalite EXACTE attendue.

CONTRE-EPREUVE, obligatoire : le port monte sur la GEOMETRIE doit DIVERGER sur cette meme unite.
Un bras ou les deux vues coincident est declare NON DISCRIMINANT (rc 2), jamais compte comme un
succes.

ASCII only (cp1252). Usage (depuis scripts/python, host up, session deja warmee) :
    python probe_381r3_bridge_edge.py
    python probe_381r3_bridge_edge.py --board C1_74 --seed 3811
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import uuid
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PYDIR))
ROOT = PYDIR.parents[1]

from rl_collect_batch import _resolve_session, _rpc            # noqa: E402

DEFAULT_BOARD = "C1_74"
DEFAULT_SEED = 3811


def _r(sid, m, b, t=90):
    return (_rpc(sid, m, [b], timeout=t).get("result") or {})


def _build(state_file: Path, seed: int, board: str) -> int:
    state_file.unlink(missing_ok=True)
    cmd = [sys.executable, "rl_duel.py", "build", "--seed", str(seed),
           "--state-file", str(state_file), "--board", board, "--rank", "17", "--no-ai"]
    proc = subprocess.run(cmd, cwd=str(PYDIR), capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    if not state_file.exists():
        raise RuntimeError("build KO : %s" % ((proc.stderr or proc.stdout or "")[-1200:]))
    return int(json.loads(state_file.read_text())["runnerId"])


def _load(sid, rid):
    from engine.entities.pathfinding.board import Board
    from engine.runner.snapshot import load_state
    bg = _r(sid, "boardGraph", {"runnerId": rid}, 60)
    if not (isinstance(bg, dict) and bg.get("tiles")):
        raise RuntimeError("boardGraph indispo")
    board = Board(bg["tiles"], adjacency="evenq")
    dv = _r(sid, "decisionView", {"runnerId": rid, "allAbilities": True}, 150)
    ob = _r(sid, "observeBattle", {"runnerId": rid}, 60)
    snap = _r(sid, "combatSnapshot", {"runnerId": rid}, 90)
    tm = _r(sid, "tileMeta", {"runnerId": rid}, 90)
    return load_state(dv, ob, snap, board=board, tiles=tm), board


def hinge_tiles(board) -> dict:
    """`{tile_id: [voisin geometrique manquant, ...]}` -- les tuiles-charnieres du board.

    Une charniere porte, dans la geometrie, un voisin a `|dElev| <= 1` absent de sa liste stockee.
    Ce sont les SEULES tuiles ou les deux corps d'`AddNeighbours` divergent POUR LA MARCHE."""
    out = {}
    for tid in board.by_id:
        sto = set(board.neighbours_native(tid))
        miss = [n for n in board.neighbours_geometric(tid)
                if n not in sto and abs(board.elevation(n) - board.elevation(tid)) <= 1]
        if miss:
            out[tid] = miss
    return out


def _endturn(sid, rid):
    return _r(sid, "applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 90)


def _move(sid, rid, uid, col, row):
    return _r(sid, "applyAction", {"runnerId": rid, "action": {
        "kind": "move", "unitId": int(uid), "to": {"col": int(col), "row": int(row)}}}, 90)


def _friendly_pools(sid, rid, override_range=None):
    """`{unitId: (pos, set((col,row)))}` du joueur COURANT. Le pool natif d'une unite qui a deja
    joue est VIDE (garde FLAG `#381`) -- l'appelant doit le lire comme « pas la main », pas comme
    « bloquee »."""
    body = {"runnerId": rid, "side": "friendly"}
    if override_range is not None:
        body["overrideRange"] = int(override_range)
    res = _r(sid, "aiMovableTiles", body, 120)
    out = {}
    for u in (res.get("units") or []):
        p = u.get("pos") or {}
        out[int(u["unitId"])] = ((p.get("col"), p.get("row")),
                                 {(int(t["col"]), int(t["row"])) for t in (u.get("tiles") or [])
                                  if t.get("col") is not None})
    return out


def drive_onto(sid, rid, board, targets: set, max_turns: int = 24):
    """Amene UNE unite du joueur courant sur l'une des `targets` (en (col,row)), pas a pas, en
    passant la main entre les tours. Rend `(unitId, position)` ou `(None, None)`."""
    import hexgeo
    for _ in range(max_turns):
        pools = _friendly_pools(sid, rid)
        for uid, (pos, reach) in sorted(pools.items()):
            if pos in targets:
                return uid, pos
            hit = sorted(reach & targets)
            if hit:
                _move(sid, rid, uid, hit[0][0], hit[0][1])
                return uid, hit[0]
        # aucune unite ne touche une cible : on rapproche la meilleure, puis on passe la main
        best = None
        for uid, (pos, reach) in sorted(pools.items()):
            for t in reach:
                d = min(hexgeo.distance(t, g) for g in targets)
                if best is None or d < best[0]:
                    best = (d, uid, t)
        if best is None:
            return None, None
        _move(sid, rid, best[1], best[2][0], best[2][1])
        _endturn(sid, rid)
        _endturn(sid, rid)
    return None, None


def _port_pool(state, board, uid, rng, neighbours=None):
    """Le pool du port pour `uid` a portee `rng`, via le foyer `movable_positions_for_unit`."""
    from engine.ai.state_bridge import _occupants
    from engine.runner.components import OwnerComponent, PositionComponent
    from engine.services.movement_query import get_movable_tiles_for
    e = state.get_entity(uid)
    pc = e.get_component(PositionComponent)
    oc = e.get_component(OwnerComponent)
    start = board.id_at(pc.col, pc.row)
    if neighbours is None:
        return {board.coord(t) for t in get_movable_tiles_for(
            board, state, uid, start, rng, _occupants(state), oc.team)}
    from engine.entities.pathfinding import walk_pathfinder as WP
    saved = WP.get_movable_positions

    def _mut(b, s, d, occ, team, **kw):
        kw["neighbours"] = neighbours(b)
        return saved(b, s, d, occ, team, **kw)
    WP.get_movable_positions = _mut
    try:
        return {board.coord(t) for t in get_movable_tiles_for(
            board, state, uid, start, rng, _occupants(state), oc.team)}
    finally:
        WP.get_movable_positions = saved


def run(board_name: str = DEFAULT_BOARD, seed: int = DEFAULT_SEED, rng: int = 1,
        verbose: bool = True) -> dict:
    sid = _resolve_session()
    logs = ROOT / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    sf = logs / ("p381r3-%s.json" % uuid.uuid4().hex[:8])
    out: dict = {"board": board_name, "seed": seed, "range": rng}
    rid = None
    try:
        rid = _build(sf, seed, board_name)
        out["runner"] = rid
        _state0, board = _load(sid, rid)
        hinges = hinge_tiles(board)
        out["n_hinges"] = len(hinges)
        out["hinges"] = sorted((board.coord(t), [board.coord(n) for n in ns])
                               for t, ns in hinges.items())
        if not hinges:
            out["ok"] = False
            out["verdict"] = (
                "NON DISCRIMINANT : aucune tuile-charniere sur %s -- les deux corps "
                "d'`AddNeighbours` y rendent la MEME chose pour la marche, ce board ne peut rien "
                "prouver." % board_name)
            return out
        targets = {board.coord(t) for t in hinges}
        uid, pos = drive_onto(sid, rid, board, targets)
        out["driven"] = {"unitId": uid, "pos": list(pos) if pos else None}
        if uid is None:
            out["ok"] = False
            out["verdict"] = ("NON CONFRONTE : aucune unite du joueur courant n'a pu atteindre une "
                              "tuile-charniere de %s en %d tours." % (board_name, 24))
            return out
        # La garde FLAG (`#381`) vide le pool natif d'une unite qui a deja joue : on repasse la
        # main jusqu'a ce que le natif reponde de nouveau pour cette unite.
        for _ in range(4):
            pools = _friendly_pools(sid, rid, override_range=rng)
            if pools.get(uid) and pools[uid][1]:
                break
            _endturn(sid, rid)
            _endturn(sid, rid)
        pools = _friendly_pools(sid, rid, override_range=rng)
        want = (pools.get(uid) or (None, set()))[1]
        out["n_native"] = len(want)
        if not want:
            out["ok"] = False
            out["verdict"] = ("NON CONFRONTE : le pool natif de u%s reste VIDE (garde FLAG "
                              "`UnitFlagsComponent$$Has(unitFlags, 1)`, #381)." % uid)
            return out
        state, board = _load(sid, rid)
        got = _port_pool(state, board, uid, rng)
        geo = _port_pool(state, board, uid, rng,
                         neighbours=lambda b: b.neighbours_geometric)
        out["n_port"] = len(got)
        out["n_port_geo"] = len(geo)
        out["port_extra"] = sorted(list(x) for x in (got - want))
        out["port_missing"] = sorted(list(x) for x in (want - got))
        out["geo_extra"] = sorted(list(x) for x in (geo - want))
        equal = (got == want)
        discriminates = (geo != got)
        if not discriminates:
            out["ok"] = False
            out["verdict"] = (
                "NON DISCRIMINANT : depuis %s a portee %d, la vue GEOMETRIE rend le MEME pool que "
                "la liste STOCKEE (%d tuiles) -- ce bras ne prouve rien." % (pos, rng, len(got)))
        else:
            out["ok"] = equal
            out["verdict"] = (
                "PORT %s NATIF depuis la charniere %s a portee %d : port=%d natif=%d ; la vue "
                "GEOMETRIE, elle, rend %d (en trop : %s) -- le bras DISCRIMINE."
                % ("==" if equal else "!=", pos, rng, len(got), len(want), len(geo),
                   out["geo_extra"]))
    finally:
        if rid is not None:
            _r(sid, "disposeRunner", {"runnerId": rid}, 30)
        sf.unlink(missing_ok=True)
    if verbose:
        print("[%s/%s range=%d] %s" % (board_name, seed, rng, out["verdict"]))
        print("   charnieres du board : %s" % (out.get("hinges") or [])[:8])
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--board", default=DEFAULT_BOARD, help="board CHOISI (runner.md sec.2)")
    ap.add_argument("--seed", type=int, default=DEFAULT_SEED)
    ap.add_argument("--range", dest="rng", type=int, default=1)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    out = run(board_name=a.board, seed=a.seed, rng=a.rng, verbose=not a.json)
    if a.json:
        print(json.dumps(out, indent=1))
    if out.get("ok"):
        return 0
    return 2 if "NON DISCRIMINANT" in out.get("verdict", "") \
        or "NON CONFRONTE" in out.get("verdict", "") else 1


if __name__ == "__main__":
    raise SystemExit(main())
