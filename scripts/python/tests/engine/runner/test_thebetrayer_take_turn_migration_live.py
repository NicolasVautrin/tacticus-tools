"""TheBetrayer_TakeTurn (worldKharn) -- behaviour MIGRE (#149 slice-24), confronte LIVE.

Valide que `_betrayer_take_turn` (`CreateBehaviour @1811a4f70`) route desormais ses DEUX feuilles E par le
DSL (== ThunderousAssault) : le MOVE force par la feuille `MoveUnit(Caster(), FixedTiles([bestTile]))` et
l'ATTAQUE 4 coups Eviscerate par la feuille `AttackWithAttackDamage(Target(), "TheBetrayer", "Eviscerate",
melee)`. Les selecteurs S (cible `GetAttackTarget`, tuile-d'arret pathfinding) restent IMPERATIFS, COLLAPSES
(`_betrayer_target` / `_betrayer_stop_tile`), et les predicats d'adjacence (`_is_adjacent_units`, dist-1)
relus AVANT/APRES le move = la re-eval LIVE native (le move mute la position -> l'attaque re-teste).

PROTOCOLE (live, deterministe -- DRIVE POSITIONS) : build worldKharn vs 3 necrons ; on ECARTE les ennemis
loin (dist >= 5) puis on place UN ennemi-cible a la position voulue -> `_betrayer_target` le choisit sans
ambiguite (nearest-in-reach), stats/PV REELS conserves.
  - CAS MOVE+ATTACK : cible a dist 2 (pas adjacente, atteignable-adjacent en range 2) -> Kharn MOVE (feuille)
    et finit ADJACENT a la cible, puis ATTAQUE (feuille) -> PV cible baissent.
  - CAS ADJACENT : cible adjacente (dist 1) -> AUCUN move, ATTAQUE directe -> PV cible baissent.
ASCII only. NON committe (tests confront live, hors depot)."""
from __future__ import annotations

import pytest

from engine.runner.snapshot import load_state
from engine.runner.operations import triggers as T
from engine.runner.components import (UnitComponent, OwnerComponent, PositionComponent,
                                      StatsComponent, HealthComponent)
from engine.runner.prng import IntBasedMersenneTwister

KHARN = "worldKharn"
BUILD = ["--roster", "1", "--p-units", "worldKharn",
         "--a-units", "necroWarden,necroOverlord,necroWarden"]


def _ok(r):
    return isinstance(r, dict) and r.get("ok")


def _seed_rng(s):
    rng = IntBasedMersenneTwister()
    rng.mt = list(s["mt"]); rng.mti = s["mti"]
    return rng


def _tile(state, board, uid):
    e = state.get_entity(uid)
    pc = e.get_component(PositionComponent) if e is not None else None
    return board.id_at(pc.col, pc.row) if pc is not None else None


def _hp(state, uid):
    e = state.get_entity(uid)
    hc = e.get_component(HealthComponent) if e is not None else None
    return hc.hp if hc is not None else None


def _place(state, board, uid, tid):
    col, row = board.coord(tid)
    pc = state.get_entity(uid).get_component(PositionComponent)
    pc.col, pc.row = col, row


def _kharn_id(state):
    return next((eid for eid in state.entities
                 if _visual(state, eid) == KHARN
                 and state.get_entity(eid).get_component(StatsComponent) is not None), None)


def _visual(state, eid):
    e = state.get_entity(eid)
    uc = e.get_component(UnitComponent) if e is not None else None
    return uc.visual_id if uc is not None else None


def _enemies(state, kid):
    kt = state.get_entity(kid).get_component(OwnerComponent)
    out = []
    for eid, e in state.entities.items():
        if eid == kid:
            continue
        oc = e.get_component(OwnerComponent)
        uc = e.get_component(UnitComponent)
        if oc is None or uc is None or not uc.alive:
            continue
        if oc.team != kt.team:
            out.append(eid)
    return out


def _occupied(state, board):
    occ = set()
    for eid in state.entities:
        t = _tile(state, board, eid)
        if t is not None:
            occ.add(t)
    return occ


def _far_tiles(board, kt, occ, count, min_dist=5):
    out = []
    for tid in board.by_id:
        if tid in occ or not board.walkable(tid):
            continue
        if (T._hex_dist(board, kt, tid, 99) or 0) >= min_dist:
            out.append(tid)
            if len(out) >= count:
                break
    return out


def _setup(rpc, build_runner):
    from engine.entities.pathfinding.board import Board
    rid = build_runner("777", extra=BUILD)["rid"]
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    if not (isinstance(bg, dict) and bg.get("tiles")):
        pytest.skip("boardGraph indispo")
    board = Board(bg["tiles"], adjacency="evenq")
    dec = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 150)
    ob = rpc("observeBattle", {"runnerId": rid}, 60)
    snap = rpc("combatSnapshot", {"runnerId": rid}, 90)
    rng0 = rpc("dumpRng", {"runnerId": rid}, 30)
    if not _ok(dec):
        pytest.skip("decisionView KO")
    state = load_state(dec, ob, snap)
    state.board = board
    if _ok(rng0):
        state.rng = _seed_rng(rng0)                  # rng LIVE -> l'attaque (crit/block par coup) peut rouler
    kid = _kharn_id(state)
    if kid is None:
        pytest.skip("worldKharn (StatsComponent) introuvable offline")
    enemies = _enemies(state, kid)
    if not enemies:
        pytest.skip("aucun ennemi vivant offline")
    return board, state, kid, enemies


def _isolate_target(board, state, kid, enemies):
    """Ecarte tous les ennemis SAUF un (choisi), qui devient l'unique cible en portee. Renvoie (target, kt)."""
    kt = _tile(state, board, kid)
    target = enemies[0]
    others = enemies[1:]
    far = _far_tiles(board, kt, _occupied(state, board), len(others), 5)
    if len(far) < len(others):
        pytest.skip("pas assez de tuiles lointaines pour ecarter les ennemis")
    for e, ft in zip(others, far):
        _place(state, board, e, ft)
    return target, kt


def test_thebetrayer_take_turn_move_then_attack_live(live_session, rpc, build_runner):
    """Cible a dist 2 : Kharn MOVE via la feuille `MoveUnit` et finit ADJACENT, puis ATTAQUE via la feuille
    `AttackWithAttackDamage` (re-eval adjacence post-move) -> PV cible baissent. Les deux feuilles E routees."""
    board, state, kid, enemies = _setup(rpc, build_runner)
    target, kt = _isolate_target(board, state, kid, enemies)

    # place la cible a dist 2 (via un voisin-de-voisin walkable, libre) -> non-adjacente mais atteignable
    occ = _occupied(state, board)
    n1 = next((n for n in board.neighbours(kt) if board.walkable(n) and n not in occ), None)
    if n1 is None:
        pytest.skip("Kharn en coin (aucun voisin libre walkable)")
    d2 = next((n for n in board.neighbours(n1)
               if board.walkable(n) and n not in occ and n != kt
               and (T._hex_dist(board, kt, n, 99) or 0) == 2), None)
    if d2 is None:
        pytest.skip("aucune tuile a dist 2 exploitable")
    _place(state, board, target, d2)

    assert not T._is_adjacent_units(state, kid, target), "cible censee etre a dist 2 (non-adjacente)"
    hp_before = _hp(state, target)

    res = T._betrayer_take_turn(state, kid)

    assert res is not None and res.get("target") == target, f"cible {res.get('target') if res else None} != {target}"
    # MOVE : la feuille a bouge Kharn et il finit ADJACENT a la cible
    assert res.get("moved") is not None, f"aucun move alors que cible a dist 2 (res={res})"
    new_kt = _tile(state, board, kid)
    assert new_kt != kt, "Kharn n'a pas bouge (feuille MoveUnit non effective)"
    tgt_tile = _tile(state, board, target)
    assert new_kt in board.neighbours(tgt_tile), f"Kharn (tuile {new_kt}) pas adjacent a la cible {tgt_tile} apres move"
    assert res.get("moved", {}).get("to") == board.coord(new_kt), "moved.to != position live de Kharn"
    # ATTACK : la feuille a attaque post-move -> PV cible baissent
    assert res.get("attack") is not None, f"aucune attaque post-move (res={res})"
    hp_after = _hp(state, target)
    assert hp_after is not None and hp_before is not None and hp_after < hp_before, \
        f"PV cible non baisses {hp_before}->{hp_after} (attaque non effective)"
    print(f"[BETRAYER move+atk] OK : target={target} move {board.coord(kt)}->{board.coord(new_kt)} "
          f"(adjacent), PV {hp_before}->{hp_after}")


def test_thebetrayer_take_turn_adjacent_no_move_live(live_session, rpc, build_runner):
    """Cible adjacente (dist 1) : AUCUN move (deja adjacent), ATTAQUE directe via la feuille -> PV baissent."""
    board, state, kid, enemies = _setup(rpc, build_runner)
    target, kt = _isolate_target(board, state, kid, enemies)

    occ = _occupied(state, board)
    nb = next((n for n in board.neighbours(kt) if board.walkable(n) and n not in occ), None)
    if nb is None:
        pytest.skip("Kharn en coin (aucun voisin libre walkable)")
    _place(state, board, target, nb)

    assert T._is_adjacent_units(state, kid, target), "cible censee etre adjacente (dist 1)"
    hp_before = _hp(state, target)

    res = T._betrayer_take_turn(state, kid)

    assert res is not None and res.get("target") == target, f"cible {res.get('target') if res else None} != {target}"
    # ADJACENT : pas de move (Kharn reste sur sa tuile)
    assert res.get("moved") is None, f"move alors que cible deja adjacente (res={res})"
    assert _tile(state, board, kid) == kt, "Kharn a bouge alors qu'il etait deja adjacent"
    # ATTACK direct -> PV baissent
    assert res.get("attack") is not None, f"aucune attaque (res={res})"
    hp_after = _hp(state, target)
    assert hp_after is not None and hp_before is not None and hp_after < hp_before, \
        f"PV cible non baisses {hp_before}->{hp_after} (attaque non effective)"
    print(f"[BETRAYER adj] OK : target={target} pas de move, PV {hp_before}->{hp_after}")
