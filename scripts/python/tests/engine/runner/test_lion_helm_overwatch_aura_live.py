"""LionHelm_ExtraDmg (1193) — +extraDmg aux attaques d'OVERWATCH des allies <=2 hexes d'Azrael.

`IdunBattle.Entities.Effects.Loki.LionHelm_ExtraDmgEffect$$CreateEffectDamageBonusForAttack` :
`ForAddition( get_OwnerIsCaster & ((HasEffect(Caster, Overwatch_AutoAttack) & IsOverwatchAttack)
| (HasEffect(Caster, GrimRetribution_CounterAttack) & CurrentAbilityIs(GrimRetribution))),
ConfigVar(extraDmg) )`, selecteur `SurroundingFriends(Azrael, ConfigConst(range) = 2)` — SANS filtre
de faction (contrairement au volet blockChance), donc TOUT allie compte.

Recette RNG-alignee = celle de `test_overwatch_live.py` (approche pas-a-pas, `dumpRng` avant le pas
declencheur, replay `MoveUnitMessage`). DEUX geometries, dont un cas NEGATIF :
  IN_RING   Azrael a <= 2 hexes de l'overwatcher -> aura ACTIVE
  OUT_RING  Azrael a >= 3 hexes                  -> aura INACTIVE
On exige le bit-exact des DEUX cotes DANS LES DEUX CAS (un port qui appliquerait le bonus
inconditionnellement casserait OUT_RING ; un port qui ne l'appliquerait jamais casserait IN_RING).
"""
from __future__ import annotations

from collections import deque

import pytest

CARRIER = "darkaAzrael"
OVERWATCHER = "eldarRanger"       # meme overwatcher que test_overwatch_live (tir Energy, 1 coup)
MOVER = "necroOverlord"           # cible VANILLE tanky (aucune reduction non portee)
BUILD = ["--roster", "1", "--p-units", MOVER, "--a-units", f"{OVERWATCHER},{CARRIER}"]


def _seed_rng(s):
    from engine.runner.prng import IntBasedMersenneTwister
    rng = IntBasedMersenneTwister()
    rng.mt = list(s["mt"]); rng.mti = s["mti"]
    return rng


def _bfs(board, src):
    dist = {src: 0}
    q = deque([src])
    while q:
        x = q.popleft()
        for n in board.neighbours(x):
            if n not in dist and (n == src or board.walkable(n)):
                dist[n] = dist[x] + 1
                q.append(n)
    return dist


def _pos(u):
    p = u.get("pos") or {}
    return (p.get("col"), p.get("row"))


def _place_azrael(rpc, rid, az_id, ow_pos, far: bool):
    """Pose Azrael a >=3 (far) ou 1..2 hexes de l'overwatcher (un move vers une tuile occupee/injouable
    echoue silencieusement -> on essaie des candidates jusqu'a obtenir la distance VOULUE)."""
    import hexgeo
    cands = [(c, r) for c in range(0, 8) for r in range(0, 10)]
    cands.sort(key=lambda p: (-hexgeo.distance(p, ow_pos)) if far else hexgeo.distance(p, ow_pos))
    for c, r in cands[:40]:
        rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "move", "unitId": az_id, "to": {"col": c, "row": r}}}, 40)
        dv = rpc("decisionView", {"runnerId": rid, "maxRank": 1}, 60)
        a = next((u for u in (dv.get("units") or []) if u["id"] == az_id), None)
        if a is None:
            continue
        d = hexgeo.distance(_pos(a), ow_pos)
        if (far and d >= 3) or ((not far) and 1 <= d <= 2):
            return d
    return None


def _run(rpc, rid, az_far: bool):
    import hexgeo
    import gameconfig as GC
    from engine.entities.pathfinding.board import Board
    from engine.runner.snapshot import load_state
    from engine.runner.runner import Runner
    from engine.runner.messages import MoveUnitMessage
    from engine.runner.components import HealthComponent

    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    if not (isinstance(bg, dict) and bg.get("tiles")):
        pytest.skip("boardGraph indispo")
    board = Board(bg["tiles"], adjacency="evenq")

    def tof(u):
        p = u.get("pos") or {}
        return board.id_at(p.get("col"), p.get("row")) if p.get("col") is not None else None

    dec = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    units = dec.get("units") or []
    mover = next((u for u in units if u.get("visualId") == MOVER and u.get("alive")), None)
    ow = next((u for u in units if u.get("visualId") == OVERWATCHER and u.get("alive")), None)
    az = next((u for u in units if u.get("visualId") == CARRIER and u.get("alive")), None)
    if not (mover and ow and az):
        pytest.skip("unite absente du build")
    mover_id, ow_id, az_id = mover["id"], ow["id"], az["id"]
    my_player = mover.get("owner")
    d0 = _place_azrael(rpc, rid, az_id, _pos(ow), az_far)
    if d0 is None:
        pytest.skip("geometrie Azrael non atteignable sur ce board")

    R = max([int(w.get("Range") or 0) for w in ((GC.unit(OVERWATCHER) or {}).get("weapons") or [])]
            or [0]) or 1
    for _turn in range(30):
        dec = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
        mv = next((u for u in (dec.get("units") or []) if u["id"] == mover_id and u.get("alive")), None)
        owl = next((u for u in (dec.get("units") or []) if u["id"] == ow_id and u.get("alive")), None)
        azl = next((u for u in (dec.get("units") or []) if u["id"] == az_id and u.get("alive")), None)
        if mv is None or owl is None or azl is None:
            pytest.skip("unite disparue pendant l'approche")
        if dec.get("currentPlayer") != my_player:
            rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 40)
            continue
        dgoal = _bfs(board, tof(owl))
        mt = rpc("aiMovableTiles", {"runnerId": rid, "side": "friendly"}, 60)
        cmt = next((x for x in (mt.get("units") or []) if x.get("unitId") == mover_id), None)
        reach = {board.id_at(t["col"], t["row"]): (t["col"], t["row"])
                 for t in ((cmt or {}).get("tiles") or [])}
        cur = tof(mv)
        out_pool = [t for t in reach if t in dgoal and dgoal[t] > R and dgoal[t] < dgoal.get(cur, 99)]
        if dgoal.get(cur, 99) > R and out_pool:
            col, row = reach[min(out_pool, key=lambda t: dgoal[t])]
            rpc("applyAction", {"runnerId": rid, "action": {
                "kind": "move", "unitId": mover_id, "to": {"col": col, "row": row}}}, 40)
            dv2 = rpc("decisionView", {"runnerId": rid, "maxRank": 1}, 60)
            if dv2.get("currentPlayer") == my_player:
                rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 40)
            continue
        step_pool = [t for t in reach if t in dgoal and t in set(board.neighbours(cur))]
        if not step_pool:
            rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 40)
            continue
        col, row = reach[min(step_pool, key=lambda t: dgoal[t])]

        ob = rpc("observeBattle", {"runnerId": rid}, 40)
        snap = rpc("combatSnapshot", {"runnerId": rid}, 40)
        hp_before = next((u.get("hp") for u in (ob.get("units") or []) if u.get("squadId") == mover_id), None)
        s0 = rpc("dumpRng", {"runnerId": rid}, 30)
        state = load_state(dec, ob, snap, board=board)
        if not (isinstance(s0, dict) and "mt" in s0):
            pytest.skip("dumpRng KO")
        state.rng = _seed_rng(s0)
        d_az_ow = hexgeo.distance(_pos(azl), _pos(owl))

        rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "move", "unitId": mover_id, "to": {"col": col, "row": row}}}, 40)
        ob2 = rpc("observeBattle", {"runnerId": rid}, 40)
        hp_after = next((u.get("hp") for u in (ob2.get("units") or []) if u.get("squadId") == mover_id), None)
        if hp_before is None or hp_after is None or hp_after >= hp_before:
            continue                                   # pas d'overwatch sur ce pas -> approcher encore

        runner = Runner(state).install_default_handlers(20)
        runner.apply(MoveUnitMessage(mover_id, (col, row)))
        am = runner.movement_handler.after_move
        off_hp = state.get_entity(mover_id).get_component(HealthComponent).hp
        fired = [a for a in (am or []) if a.get("effect") == "Overwatch_AutoAttack"]
        return {"d_az_ow": d_az_ow, "hp_before": hp_before, "live_hp": hp_after, "off_hp": off_hp,
                "live_dmg": hp_before - hp_after, "off_dmg": hp_before - off_hp, "fired": bool(fired)}
    pytest.skip("aucun overwatch declenche en 30 tours")


@pytest.fixture(scope="module")
def ow_in_ring(rpc, build_runner):
    return _run(rpc, build_runner("777", extra=BUILD)["rid"], az_far=False)


@pytest.fixture(scope="module")
def ow_out_ring(rpc, build_runner):
    return _run(rpc, build_runner("777", extra=BUILD)["rid"], az_far=True)


def test_in_ring_bit_exact(ow_in_ring):
    """Azrael a <= 2 hexes de l'overwatcher : le tir d'overwatch (avec +extraDmg) est reproduit
    bit-exact offline."""
    c = ow_in_ring
    assert c["d_az_ow"] <= 2, f"Azrael pas dans le rayon (d={c['d_az_ow']})"
    assert c["fired"], "le vecteur after-move offline n'a pas declenche l'overwatch"
    assert c["off_hp"] == c["live_hp"], (
        f"PV mover offline {c['off_hp']} != live {c['live_hp']} "
        f"(live dmg={c['live_dmg']} offline dmg={c['off_dmg']})")


def test_out_ring_bit_exact(ow_out_ring):
    """CAS NEGATIF — Azrael a >= 3 hexes : AUCUN bonus, et le tir reste reproduit bit-exact."""
    c = ow_out_ring
    assert c["d_az_ow"] >= 3, f"Azrael encore dans le rayon (d={c['d_az_ow']})"
    assert c["fired"], "le vecteur after-move offline n'a pas declenche l'overwatch"
    assert c["off_hp"] == c["live_hp"], (
        f"PV mover offline {c['off_hp']} != live {c['live_hp']} "
        f"(live dmg={c['live_dmg']} offline dmg={c['off_dmg']})")


def test_aura_changes_the_observable(ow_in_ring, ow_out_ring):
    """Le comportement porte CHANGE le resultat observable : le tir d'overwatch fait STRICTEMENT
    plus de degat quand Azrael est dans le rayon (sinon le port serait un no-op silencieux)."""
    assert ow_in_ring["live_dmg"] > ow_out_ring["live_dmg"], (
        f"degat overwatch identique in-ring ({ow_in_ring['live_dmg']}) et out-ring "
        f"({ow_out_ring['live_dmg']}) -> l'aura LionHelm ne se voit pas")
    assert ow_in_ring["off_dmg"] - ow_out_ring["off_dmg"] == \
        ow_in_ring["live_dmg"] - ow_out_ring["live_dmg"], (
        "l'ecart in/out offline ne reproduit pas l'ecart live")
