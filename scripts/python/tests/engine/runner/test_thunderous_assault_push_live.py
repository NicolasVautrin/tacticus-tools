"""TRANCHE DEPLACEMENT (#149 slice-21a PUSH + slice-21b CHARGE) — ThunderousAssault (1043) : e2e.

`IdunBattleLogic.Entities.Abilities.Active.Loki.ThunderousAssaultAbility$$ExecuteBehaviour` (id 1043) contient, apres l'attaque + le Stun, une
sous-sequence DEPLACEMENT COMPLETE : `... & PushUnit(caster, target) & KillDeadUnits(caster, target)
& MoveUnit(caster, CanAddUnit(<tuile PRE-push de la cible>))`. Ce test valide les DEUX volets :
  - slice-21a PUSH : `PushUnit` -> `DisplaceUnitOperation(type=1=IdunBattle.Operations.DisplaceUnitOperation$$FindTileToPush)` pousse la cible
    d'un hex A L'OPPOSE du caster (delegue a `MoveUnitOperation`, mirror natif DisplaceUnit emet MoveUnit@0x7e).
  - slice-21b CHARGE : `MoveUnit(caster, TargetTile())` -> le CASTER CHARGE dans la tuile LIBEREE par le push.
    `TargetTile()` = tuile PRE-push de la cible (le `DslContext` est un SNAPSHOT pre-cast -> `_pos(ctx.target)`
    reste la tuile d'origine meme apres le push = collapse gratuit du `Cache(...)` natif). Garde `CanAddUnit`
    LIVE : le caster ne suit QUE si le push a libere la tuile. `KillDeadUnits` = no-op observable chez nous
    (mort finalisee inline dans l'attaque) -> non asserte ici (cible survit au cast).

METHODE : DETERMINISTE. On capture un etat REEL (board + stats des unites via `load_state`), puis on place
caster+cible en CHAMP OUVERT (deux tuiles adjacentes avec une tuile libre derriere la cible) et on rejoue le
MESSAGE d'ability. On confronte : (1) la cible poussee sur la tuile geometrique predite (derriere, oppose
caster) ; (2) le caster charge dans la tuile INITIALE de la cible (liberee). On ne DEPEND PAS du placement
live (dans l'arene MC1_67 l'ennemi campe un coin -> push hors-board impossible ; l'IA adverse ne quitte pas
son spawn). Board+stats REELS, seules les positions controlees -> validation robuste de la CHAINE
feuille->Operation->geometrie->MoveUnit pour push ET charge.

DISTANCE : push d'1 HEX (`_PUSH_MAX_DIST=1`, cf. displace.py) — TRANCHE (cas #68, RE + live). La
destination sort de `GetMinimumTiles180Behind` (arc arriere DISTANCE-1, slot d'interface 0x4d de
`IdunBattle.Operations.DisplaceUnitOperation$$FindTileToPush`), PAS de `IdunBattle.Core.Services.BattleQuery$$GetTilesBehind` (ligne multi-hex, reservee aux AoE
ligne/cone) ; le `param_9=2` (+0x84 de DisplaceUnitBehaviour) n'est PAS la distance. Le discriminant
LIVE `test_thunderous_assault_push_distance_live` (dans ce fichier) place C,T,B1,B2 collineaires libres
et prouve l'arret a 1 hex (B2 libre ignore). Le no-op sur trait `BigTarget`/`Immovable` (IsDisplaceable)
est valide par ailleurs (test_effect_stun_live : cible tyranTyrantGuard=BigTarget, push no-op, stun intact).

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


def _find_open_push_quad(board, occupied):
    """(C, T, B1, B2) sur une LIGNE HEX droite : C adjacent a T ; B1 = tuile derriere T (oppose C,
    1 hex) ; B2 = 1 hex AU-DELA dans la MEME direction (2 hex derriere T). Les 4 walkable, distinctes,
    libres (hors `occupied`). B2 LIBRE => un push de 2 hexes serait POSSIBLE -> le scenario DISCRIMINE
    1 vs 2 : si le natif s'arrete a B1 alors que B2 est atteignable, la distance de push = 1."""
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
            b1 = board.id_at(*_step(tc[0], tc[1], di))
            if b1 is None or not board.walkable(b1) or b1 in occupied or b1 in (t, c):
                continue
            b1c = board.coord(b1)
            b2 = board.id_at(*_step(b1c[0], b1c[1], di))
            if b2 is None or not board.walkable(b2) or b2 in occupied or b2 in (t, c, b1):
                continue
            return c, t, b1, b2
    return None


def _dv(rpc, rid):
    return rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)


def _pos_by_id(dv):
    """{unitId: (col,row)} des unites de la vue decision (positions LIVE)."""
    out = {}
    for u in (dv.get("units") or []) if isinstance(dv, dict) else []:
        p = u.get("pos") or {}
        if p.get("col") is not None:
            out[u.get("id")] = (p["col"], p["row"])
    return out


def _apply_move(rpc, rid, uid, coord):
    """Place l'unite `uid` sur `coord=(col,row)` LIVE (applyAction ne verifie PAS la propriete du
    unitId -> pilote les 2 camps ; la geometrie voulue prime sur les spawns)."""
    rpc("applyAction", {"runnerId": rid, "action": {"kind": "move", "unitId": uid,
                        "to": {"col": coord[0], "row": coord[1]}}}, 40)


def _cast_push(rpc, rid, caster, target, t_coord):
    """Caste ThunderousAssault caster->target LIVE et rend la nouvelle (col,row) de la cible, ou None.
    Gere le tour : placer le caster (son seul move) cloture son activation -> bascule a l'autre camp ;
    on `endturn` jusqu'a ce que le cast POUSSE reellement la cible (pos != t_coord)."""
    for _ in range(4):
        rpc("applyAction", {"runnerId": rid, "action": {"kind": "ability", "casterId": caster,
                            "targetId": target, "abilityType": ABILITY}}, 60)
        pos = _pos_by_id(_dv(rpc, rid)).get(target)
        if pos is not None and pos != t_coord:
            return pos
        rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 40)
    return None


def test_thunderous_assault_push_distance_live(live_session, rpc, build_runner):
    """DISCRIMINANT LIVE 1-vs-2 hex du PUSH (slice-21a, cas #68 : hardcode-mesure tranche).

    RE (decompile = verite) : `IdunBattle.Operations.DisplaceUnitOperation$$FindTileToPush` (case 1 de `IdunBattle.Operations.DisplaceUnitOperation$$Execute`) choisit la destination dans la liste rendue par le slot d'interface 0x4d =
    `IdunBattle.Core.Services.BattleQuery$$GetMinimumTiles180Behind+0x38`->`IdunBattle.Core.Services.BattleQuery$$GetMinimumTiles180BehindFromTile` (arc ARRIERE,
    tuiles TOUTES a distance 1 ; cas aligne melee = 1 seule tuile straight-back). Le pull symetrique
    (`IdunBattle.Operations.DisplaceUnitOperation$$FindTileToPull`) utilise le slot 0x4c = arc AVANT (`IdunBattle.Core.Services.BattleQuery$$GetMinimumTiles180Front`).
    Le champ +0x84=2 de `DisplaceUnitBehaviour` (`.IdunBattle.Entities.Behaviours.DisplaceUnitBehaviour$$.ctor`, 9e arg pose par
    `IdunBattleLogic.Entities.DSLBehaviors$$PushUnit`) N'ATTEINT PAS FindTileToPush (appele avec `0` litteral) : ce
    n'est PAS la distance de push. => push NATIF = 1 hex (la seule source list >1 hex, `IdunBattle.Core.Services.BattleQuery$$GetTilesBehind`, sert aux AoE ligne/cone, pas au push).

    Le test place caster+cible sur une LIGNE de 4 tuiles collineaires LIBRES (C, T, B1, B2), caste LIVE
    (moteur natif), et exige que la cible bouge d'EXACTEMENT 1 hex (-> B1), PAS 2 (-> B2, pourtant LIBRE
    et atteignable). B2 libre => 1 et 2 sont DISTINGUABLES ; l'arret a B1 tranche la distance a 1."""
    rid = build_runner("777", extra=BUILD)["rid"]
    board = _board(rpc, rid)
    if board is None:
        pytest.skip("boardGraph indispo")
    dv = _dv(rpc, rid)
    if not _ok(dv):
        pytest.skip("decisionView KO")
    caster = next((u for u in (dv.get("units") or [])
                   if u.get("visualId") == CASTER_VIS and u.get("alive")), None)
    tgt = next((u for u in (dv.get("units") or [])
                if u.get("visualId") == TARGET_VIS and u.get("alive")), None)
    if caster is None or tgt is None:
        pytest.skip("caster/cible absents")
    att, tid = caster["id"], tgt["id"]

    quad = _find_open_push_quad(board, occupied=set())
    if quad is None:
        pytest.skip("aucune ligne (C,T,B1,B2) collineaire libre sur ce board")
    c_tile, t_tile, b1_tile, b2_tile = quad
    C, T, B1, B2 = (board.coord(x) for x in (c_tile, t_tile, b1_tile, b2_tile))

    # place les 2 unites en champ ouvert (la geometrie voulue prime sur les spawns)
    _apply_move(rpc, rid, tid, T)
    _apply_move(rpc, rid, att, C)
    pos0 = _pos_by_id(_dv(rpc, rid))
    if pos0.get(att) != C or pos0.get(tid) != T:
        pytest.skip(f"placement non realise (caster={pos0.get(att)} target={pos0.get(tid)})")
    print(f"\n[PUSH live disc] caster@{C} target@{T} | B1(1hex)@{B1} LIBRE, B2(2hex)@{B2} LIBRE "
          f"-> push doit s'arreter a B1 si distance=1")

    newT = _cast_push(rpc, rid, att, tid, T)
    assert newT is not None, "cast ThunderousAssault n'a PAS pousse la cible (turn/no-op)"
    assert newT != T, f"cible non poussee (restee @{T})"
    assert newT != B2, (f"push -> B2@{B2} = 2 hexes : distance NATIVE = 2, pas 1 -> _PUSH_MAX_DIST "
                        f"doit passer a 2 + porter la marche multi-hex (slice-21b) !")
    assert newT == B1, (f"push -> @{newT} != B1@{B1} (1 hex, oppose caster). B2@{B2} etait LIBRE et "
                        f"atteignable : l'arret a 1 hex tranche la distance NATIVE de push a 1")
    posC = _pos_by_id(_dv(rpc, rid)).get(att)
    print(f"[PUSH live disc] OK : distance push NATIVE = 1 hex (cible {T}->{newT}, B2@{B2} libre "
          f"IGNORE) ; caster CHARGE ->{posC} (tuile T liberee)")


def test_thunderous_assault_push_offline_endtoend(live_session, rpc, build_runner):
    """ThunderousAssault : (1) POUSSE la cible deplacable sur la tuile geometrique predite (derriere, oppose
    du caster) ; (2) le CASTER CHARGE dans la tuile initiale de la cible (liberee). Chaine feuilles
    PushUnit + MoveUnit -> DisplaceUnitOperation/MoveUnitOperation -> PositionComponent."""
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

    state = load_state(dv, ob, snap, board=board)   # #64 : board a la source (DisplaceUnit/MoveUnit en depend)
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

    # slice-21b CHARGE : le caster suit dans la tuile INITIALE de la cible (liberee par le push).
    caster_tile = _off_tile(state, board, att)
    assert caster_tile != c_tile, ("le caster n'a PAS charge (feuille MoveUnit no-op / garde CanAddUnit live / "
                                   f"TargetTile snapshot ?) - reste @{c_tile}")
    assert caster_tile == t_tile, (f"charge -> @{caster_tile} != tuile INITIALE de la cible @{t_tile} "
                                   f"(dest MoveUnit = tuile PRE-push liberee)")
    print(f"[CHARGE offline e2e] OK : caster @{c_tile} -> @{caster_tile} (= tuile initiale de la cible, liberee)")
