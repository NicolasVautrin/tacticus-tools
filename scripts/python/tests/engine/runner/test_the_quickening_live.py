"""TRANCHE ABILITY COMBAT (#217) — TheQuickening (1151, bloodMephiston) : teleport-echange e2e offline.

`IdunBattleLogic.Entities.Abilities.Active.Loki.TheQuickeningAbility$$ExecuteBehaviour` : cast TILE-TARGET. Le caster se TELEPORTE sur la tuile
ciblee ; l'unite presente y est ECHANGEE vers la tuile d'origine du caster ; puis caster + unite-echangee
(SI BloodAngels, `HasFaction 0xe=14`) attaquent en melee depuis leur nouvelle position (Attack OVERRIDE par
`IdunBattleLogic.Entities.DSLFormulas$$PercentageOfAttackCappedAtMax` = min(maxDmg[lvl]xmult, round(Attack x dmgPct[lvl]/100))).

MESURE LIVE (probe_217) : SWAP net des positions ; effets Untargetable(0x414)/ForcedInMelee(0x529)/
TemporaryStatOverride(0x510) TOUS ajoutes ET retires DANS le cast (net-zero, aucun effet persistant).

METHODE (mirror test_thunderous_assault_push, DETERMINISTE) : etat REEL (board+stats via `load_state`),
positions controlees (caster@C, ally@T adjacent, ennemi adjacent a T). On rejoue le MESSAGE d'ability et
on confronte : (1) caster -> tuile T ; (2) ally -> tuile C (echange) ; (3) l'ennemi adjacent a T subit du
degat (free melee attack du caster, gate BloodAngels). MT calee sur le live (`dumpRng`) pour le roll.
"""
from __future__ import annotations

import pytest

from engine.runner.snapshot import load_state
from engine.runner.runner import Runner
from engine.runner.messages import ActiveAbilityMessage
from engine.runner.components import PositionComponent, HealthComponent
from engine.runner.prng import IntBasedMersenneTwister

CASTER_VIS = "bloodMephiston"     # id 1151 TheQuickening (BloodAngels, melee)
ALLY_VIS = "bloodIntercessor"     # allie BloodAngels (echange + free-attack faction-14)
ENEMY_VIS = "necroWarden"         # cible du free-attack (Necron)
ABILITY = 1151
BUILD = ["--roster", "1", "--p-units", f"{CASTER_VIS},{ALLY_VIS}",
         "--a-units", f"{ENEMY_VIS},{ENEMY_VIS}",
         "--hp-target", "300000", "--hp-player", "300000"]


def _ok(r):
    return isinstance(r, dict) and r.get("ok")


def _board(rpc, rid):
    from engine.entities.pathfinding.board import Board
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    if not (isinstance(bg, dict) and bg.get("tiles")):
        return None
    return Board(bg["tiles"], adjacency="native_sym")


def _seed_rng(s):
    rng = IntBasedMersenneTwister()
    rng.mt = list(s["mt"]); rng.mti = s["mti"]
    return rng


def _tile_of(state, board, uid):
    e = state.get_entity(uid)
    pc = e.get_component(PositionComponent) if e is not None else None
    return board.id_at(pc.col, pc.row) if pc is not None else None


def _hp(state, uid):
    e = state.get_entity(uid)
    hc = e.get_component(HealthComponent) if e is not None else None
    return hc.hp if hc is not None else None


def _find_swap_triple(board):
    """(C, T, E) : C,T adjacents walkable distincts ; E adjacent a T, distinct de C ; les 3 libres.
    C = tuile caster ; T = tuile ally (cible du cast) ; E = tuile ennemi (adjacent a T -> free-attack)."""
    for c in board.by_id:
        if not board.walkable(c):
            continue
        for t in board.neighbours(c):
            if t == c or not board.walkable(t):
                continue
            for en in board.neighbours(t):
                if en in (c, t) or not board.walkable(en):
                    continue
                return c, t, en
    return None


def test_the_quickening_swap_offline_endtoend(live_session, rpc, build_runner):
    """TheQuickening : (1) le caster se TELEPORTE sur la tuile ciblee ; (2) l'ally y est ECHANGE vers la
    tuile du caster ; (3) l'ennemi adjacent a la tuile d'arrivee subit le free melee attack (gate
    BloodAngels). Chaine execute_behaviour -> MoveUnitOperation (swap) + set_stat_override + AttackDamage."""
    rid = build_runner("31337", extra=BUILD)["rid"]
    board = _board(rpc, rid)
    if board is None:
        pytest.skip("boardGraph indispo")
    if not _ok(rpc("dumpRng", {"runnerId": rid}, 30)):
        pytest.skip("dumpRng indispo (rebuild+reinject hooks ?)")
    dv = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    ob = rpc("observeBattle", {"runnerId": rid}, 40)
    snap = rpc("combatSnapshot", {"runnerId": rid}, 40)
    if not _ok(dv):
        pytest.skip("decisionView KO")
    meph = next((u for u in (dv.get("units") or [])
                 if u.get("visualId") == CASTER_VIS and u.get("alive")), None)
    ally = next((u for u in (dv.get("units") or [])
                 if u.get("visualId") == ALLY_VIS and u.get("alive")), None)
    enemy = next((u for u in (dv.get("units") or [])
                  if u.get("visualId") == ENEMY_VIS and u.get("alive")), None)
    if meph is None or ally is None or enemy is None:
        pytest.skip("meph/ally/enemy absents")
    mid, aid, eid = meph["id"], ally["id"], enemy["id"]

    state = load_state(dv, ob, snap, board=board)   # #64 : board a la source (MoveUnit en depend)
    me, ae, ee = state.get_entity(mid), state.get_entity(aid), state.get_entity(eid)
    if any(x is None or x.get_component(PositionComponent) is None for x in (me, ae, ee)):
        pytest.skip("entites/positions non chargees offline")

    triple = _find_swap_triple(board)
    if triple is None:
        pytest.skip("aucun triplet (caster, ally, ennemi) sur ce board")
    c_tile, t_tile, e_tile = triple
    (cc, cr), (tc, tr), (ec, er) = board.coord(c_tile), board.coord(t_tile), board.coord(e_tile)
    me.get_component(PositionComponent).col, me.get_component(PositionComponent).row = cc, cr
    ae.get_component(PositionComponent).col, ae.get_component(PositionComponent).row = tc, tr
    ee.get_component(PositionComponent).col, ee.get_component(PositionComponent).row = ec, er
    print(f"\n[QUICK offline e2e] meph@{c_tile}{(cc, cr)} ally@{t_tile}{(tc, tr)} "
          f"enemy@{e_tile}{(ec, er)}")

    hp0 = _hp(state, eid)
    s1 = rpc("dumpRng", {"runnerId": rid}, 30)
    if not _ok(s1):
        pytest.skip("dumpRng KO")
    state.rng = _seed_rng(s1)

    runner = Runner(state).install_default_handlers(20)
    # target_id = id de TUILE (cast tile-target) = la tuile de l'ally (T)
    runner.apply(ActiveAbilityMessage(caster_id=mid, target_id=t_tile, ability_type=ABILITY))
    last = runner.ability_handler.last or {}
    assert last.get("ported"), "TheQuickening non routee (ability-exec)"

    # (1)(2) SWAP : meph -> T, ally -> C
    meph_tile = _tile_of(state, board, mid)
    ally_tile = _tile_of(state, board, aid)
    assert meph_tile == t_tile, (f"caster n'a pas teleporte sur la tuile ciblee : @{meph_tile} != T@{t_tile}")
    assert ally_tile == c_tile, (f"ally n'a pas ete echange vers la tuile du caster : @{ally_tile} != C@{c_tile}")
    print(f"[QUICK offline e2e] SWAP OK : meph @{c_tile}->@{meph_tile} ; ally @{t_tile}->@{ally_tile}")

    # (3) free melee attack du caster BloodAngels sur l'ennemi adjacent a T
    hp1 = _hp(state, eid)
    attacks = last.get("attacks") or []
    assert any(a.get("attacker") == mid and a.get("target") == eid for a in attacks), \
        f"free-attack du caster BloodAngels absente (attacks={attacks})"
    assert hp1 is not None and hp0 is not None and hp1 < hp0, \
        f"l'ennemi n'a pas subi le free melee attack (hp {hp0} -> {hp1})"
    print(f"[QUICK offline e2e] FREE-ATTACK OK : enemy hp {hp0} -> {hp1} (attacks={attacks})")
