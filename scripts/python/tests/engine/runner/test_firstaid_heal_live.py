"""B3 (#130) -- `FirstAidHealAbility` (Abilities.Tiles @1811c0490) heal-on-tile au DEBUT DE TOUR.

RE (decompile gqfc5mff6c) : une tuile FirstAid porte `FirstAidHealEffect` (type 10) ; trigger
`On(0x13) & IsTurnOf(Units(units-on-tile))` ; behaviour @180f44090 =
`Heal(PercentageOf(StatAmount(Health=5, Initial=2)=maxHP, Direct(GetNumberConstant(0x13)=firstAidRecovery%)))`,
targets = `UnitsWithoutTrait(Units(tile), 0x19=25=Immune)`. firstAidRecovery = 35 (globalValue).

Board campagne C4_* (FirstAid). On DRIVE un allie DAMAGED sur une tuile FirstAid et on tire `first_aid_heal`
(l'event 0x13 de StartTurn) : heal = 35% maxHP (clamp maxHP). Gate IsTurnOf : un ennemi sur une tuile FirstAid
n'est PAS soigne au tour du player. ASCII only. (Modele : test_lightcover_gate_live.)
"""
from __future__ import annotations

import pytest

import gameconfig as GC
from engine.runner.snapshot import load_state
from engine.runner.components import (HealthComponent, PositionComponent, OwnerComponent,
                                      UnitComponent)
from engine.runner.operations.triggers import first_aid_heal
from engine.entities.pathfinding.board import Board

FIRSTAID = "FirstAid"
# Boards campagne portant des tuiles FirstAid (data/boards/global). On en essaie plusieurs (skip si aucun
# buildable / sans capteur FirstAid).
FIRSTAID_BOARDS = ["C4_33", "C4_35", "C4_36", "C4_37", "C4_39", "C4_40", "C4_41", "C4_45"]


def _ok(r):
    return isinstance(r, dict) and r.get("ok")


@pytest.fixture(scope="session")
def firstaid_capture(live_session, rpc, build_runner):
    """Build sur un board FirstAid + capture live (dv/ob/snap) + board. Skip si aucun buildable."""
    for bd in FIRSTAID_BOARDS:
        b = build_runner("777", extra=["--board", bd, "--p-units", "templHelbrecht",
                                       "--a-units", "templHelbrecht"])
        rid = b["rid"]
        bg = rpc("boardGraph", {"runnerId": rid}, 60)
        if not (isinstance(bg, dict) and bg.get("tiles")):
            continue
        if not any(t.get("tileDefId") == FIRSTAID for t in bg["tiles"]):
            continue
        board = Board(bg["tiles"], adjacency="evenq")
        dv = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
        ob = rpc("observeBattle", {"runnerId": rid}, 40)
        snap = rpc("combatSnapshot", {"runnerId": rid}, 40)
        if not (_ok(dv) and _ok(ob) and _ok(snap)):
            continue
        fa = sorted(board.coords_with_terrain(FIRSTAID))
        if not fa:
            continue
        return {"dv": dv, "ob": ob, "snap": snap, "board": board, "fa": fa,
                "my_team": b["my_team"], "board_id": bd}
    pytest.skip("aucun board FirstAid buildable avec capteur tileDefId")


def _fresh(cap):
    st = load_state(cap["dv"], cap["ob"], cap["snap"])
    st.board = cap["board"]
    return st


def _find_unit(st, team, want_team: bool):
    """1re unite VIVANTE avec HealthComponent dont (team == cap.my_team) == want_team."""
    for uid, e in st.entities.items():
        oc = e.get_component(OwnerComponent)
        hc = e.get_component(HealthComponent)
        uc = e.get_component(UnitComponent)
        if oc is None or hc is None or hc.hp_max is None:
            continue
        if uc is not None and not uc.alive:
            continue
        if (oc.team == team) == want_team:
            return uid, oc.player
    return None, None


def _place(st, uid, col, row):
    pc = st.get_entity(uid).get_component(PositionComponent)
    pc.col, pc.row = col, row


def test_firstaid_heals_35pct_of_maxhp(firstaid_capture):
    """Un allie DAMAGED sur une tuile FirstAid est soigne de `firstAidRecovery`(35)% de sa maxHP au
    StartTurn (event 0x13). Heal clampe a maxHP ; event heal emis."""
    cap = firstaid_capture
    healpct = int(GC.global_value("firstAidRecovery") or 0)
    assert healpct == 35, "firstAidRecovery attendu 35, lu %d" % healpct
    st = _fresh(cap)
    uid, player = _find_unit(st, cap["my_team"], want_team=True)
    if uid is None:
        pytest.skip("pas d'allie avec HealthComponent")
    fa_col, fa_row = cap["fa"][0]
    _place(st, uid, fa_col, fa_row)
    hc = st.get_entity(uid).get_component(HealthComponent)
    maxhp = int(hc.hp_max)
    hc.hp = maxhp // 2
    before = hc.hp
    res = first_aid_heal(st, player)
    after = int(hc.hp)
    expected = min(maxhp - before, round(maxhp * healpct / 100))
    print("[FIRSTAID heal] board=%s maxhp=%d before=%d after=%d expected+%d res=%s" %
          (cap["board_id"], maxhp, before, after, expected, res))
    assert after - before == expected, "heal %d != attendu %d (35%% maxHP clamp)" % (after - before, expected)
    assert any(r.get("unit") == uid and r.get("heal") == expected for r in res), "event heal FirstAid manquant"


def test_firstaid_isturnof_skips_enemy(firstaid_capture):
    """Gate `IsTurnOf(units-on-tile)` : un ENNEMI (autre team) posé sur une tuile FirstAid n'est PAS
    soigne quand c'est le tour du PLAYER (first_aid_heal(player))."""
    cap = firstaid_capture
    st = _fresh(cap)
    _, player = _find_unit(st, cap["my_team"], want_team=True)
    enemy, _ = _find_unit(st, cap["my_team"], want_team=False)
    if player is None or enemy is None:
        pytest.skip("pas d'allie+ennemi")
    fa_col, fa_row = cap["fa"][0]
    _place(st, enemy, fa_col, fa_row)
    hc = st.get_entity(enemy).get_component(HealthComponent)
    hc.hp = int(hc.hp_max) // 2
    before = int(hc.hp)
    res = first_aid_heal(st, player)      # tour du PLAYER : l'ennemi ne doit PAS heal
    print("[FIRSTAID isturnof] enemy before=%d after=%d res=%s" % (before, int(hc.hp), res))
    assert int(hc.hp) == before, "ennemi soigne au tour du player (gate IsTurnOf casse)"
