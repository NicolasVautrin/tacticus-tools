"""TRANCHE DEPLACEMENT (#149 slice-21a) — PUSH de ThunderousAssault (1043) : validation end-to-end.

`ThunderousAssaultAbility.ExecuteBehaviour @1812158b0` (id 1043) contient, apres l'attaque + le Stun, une
sous-sequence DEPLACEMENT : `... & PushUnit(caster, target) & KillDeadUnits & MoveUnit(caster, <hex libere>)`.
Ce test valide le PUSH (slice-21a) : la feuille `PushUnit` -> `DisplaceUnitOperation(type=1=FindTileToPush
@180e695e0)` pousse la cible d'un hex A L'OPPOSE du caster, en delegant a `MoveUnitOperation` (mirror natif :
DisplaceUnit emet MoveUnit@0x7e).

METHODE : DETERMINISTE. On capture un etat REEL (board + stats des unites via `load_state`), puis on place
caster+cible en CHAMP OUVERT (deux tuiles adjacentes avec une tuile libre derriere la cible) et on rejoue le
MESSAGE d'ability. On confronte le deplacement de la cible a la geometrie hex predite. On ne DEPEND PAS du
placement live (dans l'arene MC1_67 l'ennemi campe un coin -> push hors-board impossible ; drive-positions ne
peut pas l'en sortir car l'IA adverse ne quitte pas son spawn). Le board+stats sont REELS, seules les
positions sont controlees -> validation robuste de la CHAINE feuille->Operation->geometrie->MoveUnit.

DISTANCE : slice-21a pousse d'1 HEX (`_PUSH_MAX_DIST=1`, cf. displace.py). Le natif `GetTilesBehind
@18106a150` marche jusqu'a un `maxCount` lu d'un config GLOBAL runtime -> la distance-vs-natif (1 ou 2 hex)
reste a confirmer LIVE (test separe / observation quand un push firera en bataille) ; ce test valide la
chaine + la DIRECTION a la distance portee. Le no-op sur trait `BigTarget`/`Immovable` (IsDisplaceable) est
valide par ailleurs (test_effect_stun_live : cible tyranTyrantGuard=BigTarget, push no-op, stun intact).

Invariants harnais : board+stats REELS (capture live), aucune tuile/RVA hardcodee, geometrie parity-safe.
"""
from __future__ import annotations

import pytest

from engine.runner.snapshot import load_state
from engine.runner.runner import Runner
from engine.runner.messages import ActiveAbilityMessage
from engine.runner.components import PositionComponent
from engine.runner.operations.displace import _dir_index, _step   # geometrie du port (positionnement)

CASTER_VIS = "templSwordBrother"     # id 1043 ThunderousAssault (melee charge, Power)
TARGET_VIS = "spaceBlackmane"        # Ragnar, DEPLACABLE (pas de BigTarget/Immovable)
ABILITY = 1043
# --hp-target/--hp-player : la cible survit au cast (une cible morte est retiree, pas poussee).
BUILD = ["--roster", "1", "--p-units", CASTER_VIS, "--a-units", TARGET_VIS,
         "--hp-target", "50000", "--hp-player", "50000"]


def _ok(r):
    return isinstance(r, dict) and r.get("ok")


def _board(rpc, rid):
    from engine.entities.pathfinding.board import Board
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    if not (isinstance(bg, dict) and bg.get("tiles")):
        return None
    return Board(bg["tiles"], adjacency="native_sym")


def _off_tile(state, board, uid):
    e = state.get_entity(uid)
    pc = e.get_component(PositionComponent) if e is not None else None
    return board.id_at(pc.col, pc.row) if pc is not None else None


def _find_open_push_triple(board, occupied):
    """Trouve (contact_C, target_T, behind_B) en CHAMP OUVERT : C adjacent a T ; B = tuile derriere T
    (oppose de C) via la geometrie du port ; les 3 walkable, distinctes, libres (hors `occupied`)."""
    for t in board.by_id:
        tc = board.coord(t)
        if not board.walkable(t) or t in occupied:
            continue
        for c in board.neighbours(t):
            cc = board.coord(c)
            if not board.walkable(c) or c in occupied or c == t:
                continue
            di = _dir_index(cc[0], cc[1], tc[0], tc[1])
            if di is None:
                continue
            bcol, brow = _step(tc[0], tc[1], di)
            b = board.id_at(bcol, brow)
            if b is None or b in (t, c) or not board.walkable(b) or b in occupied:
                continue
            return c, t, b
    return None


def test_thunderous_assault_push_offline_endtoend(live_session, rpc, build_runner):
    """ThunderousAssault POUSSE la cible deplacable sur la tuile geometriquement predite (derriere, oppose
    du caster) : chaine feuille PushUnit -> DisplaceUnitOperation -> MoveUnitOperation -> PositionComponent."""
    rid = build_runner("777", extra=BUILD)["rid"]
    board = _board(rpc, rid)
    if board is None:
        pytest.skip("boardGraph indispo")
    dv = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    ob = rpc("observeBattle", {"runnerId": rid}, 40)
    snap = rpc("combatSnapshot", {"runnerId": rid}, 40)
    if not _ok(dv):
        pytest.skip("decisionView KO")
    caster = next((u for u in (dv.get("units") or [])
                   if u.get("visualId") == CASTER_VIS and u.get("alive")), None)
    tgt = next((u for u in (dv.get("units") or [])
                if u.get("visualId") == TARGET_VIS and u.get("alive")), None)
    if caster is None or tgt is None:
        pytest.skip("caster/cible absents")
    att, tid = caster["id"], tgt["id"]

    state = load_state(dv, ob, snap)
    state.board = board                      # load_state ne peuple PAS le board (DisplaceUnit/MoveUnit en depend)
    ca, ta = state.get_entity(att), state.get_entity(tid)
    if ca is None or ta is None or ca.get_component(PositionComponent) is None \
            or ta.get_component(PositionComponent) is None:
        pytest.skip("entites/positions non chargees offline")

    # place caster + cible en champ ouvert (1v1 -> les 2 seules unites ; occupied vide)
    triple = _find_open_push_triple(board, occupied=set())
    if triple is None:
        pytest.skip("aucun triplet (contact, cible, derriere) ouvert sur ce board")
    c_tile, t_tile, b_tile = triple
    (cc, cr), (tc, tr), (bc, br) = board.coord(c_tile), board.coord(t_tile), board.coord(b_tile)
    ca.get_component(PositionComponent).col, ca.get_component(PositionComponent).row = cc, cr
    ta.get_component(PositionComponent).col, ta.get_component(PositionComponent).row = tc, tr
    print(f"\n[PUSH offline e2e] caster@{c_tile}{(cc, cr)} target@{t_tile}{(tc, tr)} "
          f"-> attendu derriere @{b_tile}{(bc, br)}")

    runner = Runner(state).install_default_handlers(20)
    runner.apply(ActiveAbilityMessage(caster_id=att, target_id=tid, ability_type=ABILITY))
    assert (runner.ability_handler.last or {}).get("ported"), "ThunderousAssault non routee (ability-exec)"

    new_tile = _off_tile(state, board, tid)
    assert new_tile != t_tile, ("la cible n'a PAS ete poussee (feuille PushUnit no-op / IsDisplaceable / "
                                f"board ?) - restee @{t_tile}")
    assert new_tile == b_tile, (f"push -> @{new_tile} != tuile geometrique attendue @{b_tile} "
                                f"(direction/geometrie du push)")
    print(f"[PUSH offline e2e] OK : cible poussee @{t_tile} -> @{new_tile} (= derriere, oppose du caster)")
