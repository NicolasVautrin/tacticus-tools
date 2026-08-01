"""#381-r5 LIVE -- la branche MOUVEMENT SPECIAL de `GetPathfinderTypeForUnit`, confrontee au JEU.

LA QUESTION BINAIRE
-------------------
« Le type de pathfinder qu'une unite obtient depend-il d'autre chose qu'`IsLikeFlying` ? »
`IdunBattle.Core.Services.MovementQuery$$GetPathfinderTypeForUnit` repond OUI : quatre effets
« je descends du ciel » (1035 / 1140 / 1238 / 1573) le detournent vers un
`IdunBattle.Entities.Pathfinding.ATeleportPathfinder`, dont `IterateReachableTiles` UNIONNE le
pool de la base (marche/vol) avec un pool BOARD-WIDE (`FindTilesReachableByTeleport`, qui ne lit
ni le start ni la portee).

CE QUE CES TESTS EXIGENT
------------------------
`aiMovableTiles` appelle LITTERALEMENT `MovementQuery$$GetMovableTilesFor` : l'egalite attendue
est EXACTE, unite par unite. Les deux tests sont AUTO-DISCRIMINANTS -- ils echouent si aucune
unite n'est en mouvement special, ET si le port MUTE (`_no_special`, l'etat d'AVANT `#381-r5` :
dispatch rabattu sur `IsLikeFlying ? Fly : Walk`) rend le MEME pool. C'est la garde demandee :
elle rougit des que le dispatch retombe sur les deux seuls types 0/3.

Le regime est TRANSITOIRE (l'effet expire) : il faut mesurer au TOUT DEBUT de la bataille, avant
toute fin de tour. Les deux boards sont distincts (`#95` : un resultat geometrique sur un seul
board n'est pas un resultat).

ASCII only (cp1252).
"""
from __future__ import annotations

from contextlib import contextmanager

import pytest

BOARDS = ("C2_26", "MC1_67")
SEED = "38104"
BUILD_POOL = ["--no-ai"]             # roster COMPLET du seed : autant d'unites confrontees
PROBE_RANGE = 2                      # meme portee que la mesure d'ouverture de `#381-r5`


@contextmanager
def _no_special():
    """L'etat d'AVANT `#381-r5` : `GetPathfinderTypeForUnit` rabattu sur sa SEULE branche finale
    (`IsLikeFlying ? Fly : Walk`). On vide la table des effets que la branche
    `!ignoreSpecialMovement` teste -- le foyer la relit a CHAQUE appel (globale du module)."""
    from engine.services import movement_query as MQ
    saved = MQ.SPECIAL_MOVEMENT_EFFECT_TYPES
    MQ.SPECIAL_MOVEMENT_EFFECT_TYPES = ()
    try:
        yield
    finally:
        MQ.SPECIAL_MOVEMENT_EFFECT_TYPES = saved


def _load(rpc, rid):
    from engine.entities.pathfinding.board import Board
    from engine.runner.snapshot import load_state
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    if not (isinstance(bg, dict) and bg.get("tiles")):
        pytest.skip("boardGraph indispo")
    board = Board(bg["tiles"], adjacency="evenq")
    dv = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 120)
    ob = rpc("observeBattle", {"runnerId": rid}, 40)
    snap = rpc("combatSnapshot", {"runnerId": rid}, 60)
    return load_state(dv, ob, snap, board=board), board, dv


def _confront(rpc, rid, board_name):
    """Confronte `get_movable_tiles_for` a `aiMovableTiles` sur TOUTES les unites, en VENTILANT
    par regime. Rend le dictionnaire de comptes + les divergences."""
    from engine.ai.state_bridge import _occupants
    from engine.entities.pathfinding.fly_pathfinder import is_like_flying
    from engine.entities.traits.unit_trait import unit_trait_names
    from engine.runner.components import OwnerComponent, PositionComponent
    from engine.services.movement_query import get_movable_tiles_for, has_special_movement

    state, board, dv = _load(rpc, rid)
    nat = rpc("aiMovableTiles", {"runnerId": rid, "side": "all",
                                 "overrideRange": PROBE_RANGE}, 120) or {}
    listed = {int(u.get("unitId")): {(int(t["col"]), int(t["row"]))
                                     for t in (u.get("tiles") or []) if t.get("col") is not None}
              for u in (nat.get("units") or [])}
    assert listed, "aiMovableTiles n'a liste aucune unite sur %s" % board_name

    occ = _occupants(state)
    out = {"board": board_name, "special": 0, "special_equal": 0, "special_moved": 0,
           "walk": 0, "walk_equal": 0, "flying": 0, "empty": 0, "rows": [], "bad": []}
    for uid, want in sorted(listed.items()):
        e = state.get_entity(uid)
        pc = e.get_component(PositionComponent) if e is not None else None
        oc = e.get_component(OwnerComponent) if e is not None else None
        if pc is None or oc is None:
            continue
        vis = next((u.get("visualId") for u in (dv.get("units") or [])
                    if int(u.get("id")) == uid), None)
        start = board.id_at(pc.col, pc.row)
        if start is None:
            continue
        special = has_special_movement(state, uid)
        if not special and is_like_flying(unit_trait_names(vis)):
            out["flying"] += 1                  # `#381-r2`, hors perimetre de ce cas
            continue
        if not want:
            out["empty"] += 1                   # garde FLAG non portee (`#381`)
            continue
        got = {board.coord(t) for t in get_movable_tiles_for(
            board, state, uid, start, PROBE_RANGE, occ, oc.team)}
        with _no_special():
            raw = {board.coord(t) for t in get_movable_tiles_for(
                board, state, uid, start, PROBE_RANGE, occ, oc.team)}
        if special:
            out["special"] += 1
            out["special_equal"] += int(got == want)
            out["special_moved"] += int(raw != got)
            out["rows"].append((uid, vis, len(want), len(got), len(raw)))
        else:
            out["walk"] += 1
            out["walk_equal"] += int(got == want)
        if got != want:
            out["bad"].append((uid, vis, "special" if special else "walk",
                               sorted(got - want)[:6], sorted(want - got)[:6]))
    return out


def _run(rpc, build_runner, board_name, seed):
    rid = build_runner(seed, extra=BUILD_POOL, board=board_name)["rid"]
    r = _confront(rpc, rid, board_name)
    print("\n[381-r5] %s/%s : MOUVEMENT SPECIAL %d/%d == natif (dont %d dont le pool CHANGE par "
          "le dispatch) ; WALK %d/%d == natif ; ecartees : %d volantes (#381-r2), %d pool natif "
          "vide (#381)"
          % (board_name, seed, r["special_equal"], r["special"], r["special_moved"],
             r["walk_equal"], r["walk"], r["flying"], r["empty"]))
    for (uid, vis, n_nat, n_got, n_raw) in r["rows"]:
        print("[381-r5]   u%-5s %-22s natif=%-3d port=%-3d port-SANS-dispatch=%d"
              % (uid, vis, n_nat, n_got, n_raw))
    assert r["special"], (
        "aucune unite en MOUVEMENT SPECIAL sur %s/%s -- le test ne prouverait rien. Le regime est "
        "TRANSITOIRE : mesurer au tout debut de bataille." % (board_name, seed))
    assert r["special_moved"], (
        "le dispatch ne change le pool d'AUCUNE des %d unites en mouvement special -- la "
        "configuration ne discrimine pas" % r["special"])
    assert not r["bad"], ("port != natif sur %d unite(s) de %s : %s"
                          % (len(r["bad"]), board_name, r["bad"][:4]))
    return r


def test_mouvement_special_c2_26(rpc, build_runner):
    """`C2_26` -- le board de la mesure d'ouverture (`#381-r4` §4)."""
    _run(rpc, build_runner, BOARDS[0], SEED)


def test_mouvement_special_mc1_67(rpc, build_runner):
    """`MC1_67` -- SECOND board (arene par defaut), pour que le resultat ne soit pas un artefact
    de geometrie. C'est aussi le board du datapoint `bloodIntercessor` de `#381-r2`."""
    _run(rpc, build_runner, BOARDS[1], SEED)


if __name__ == "__main__":                       # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
