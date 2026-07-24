"""VECTEUR AFTER-MOVE — effet-trigger OVERWATCH (`Overwatch_AutoAttackEffect`) : replay-diff LIVE vs moteur.

Valide le volet EFFET-trigger du dispatcher générique (`EvaluateEffectTrigger*`) sur l'Overwatch :
quand une unité ENNEMIE se déplace dans la portée d'attaque d'un overwatcher (effet 1009 actif), ce
dernier déclenche une **attaque NORMALE** sur le mover (`RangedAutoAttackEffect.CreateTargetTrigger` =
`On(4) & NOT AreFriends & IsInAttackRange(...,3) & additional` ; `GetAttackBehaviour` =
`UseActiveAbility(NormalAttack)`).

Fixture = une unité MÊLÉE tanky (mienne) conduite vers **eldarMauganRa** (ennemi overwatcher). Le mover
ne fait que se déplacer (survit). Sur le move qui le fait perdre des PV (overwatch live), on REJOUE le
move offline (MT calé via dumpRng AVANT le move : l'attaque overwatch est le 1er conso RNG, le
pathfinding étant déterministe) et on confronte les PV du mover (live == offline). L'attaque overwatch =
attaque NORMALE de l'overwatcher → chemin `AttackDamageOperation.execute` déjà validé bit-exact.

⚠ ADJACENCE/PORTÉE = mode **evenq** (cf. test_psyker_splash_live : la capture native est partielle).
"""
from __future__ import annotations

from collections import deque

import pytest

from engine.runner.snapshot import load_state
from engine.runner.runner import Runner
from engine.runner.messages import MoveUnitMessage
from engine.runner.prng import IntBasedMersenneTwister
from engine.runner.components import HealthComponent, StatsComponent

MOVER_VIS = "necroOverlord"          # cible VANILLE tanky (hp~8536, effects=[]) : pas de réduction non portée
OVERWATCHER_VIS = "eldarRanger"      # trait HeavyWeapon (→ Overwatch + HeavyWeapon_ExtraDmg +25% RANGED,
                                     # PORTÉ) ; tir Energy 1 coup → overwatch = attaque normale ×1.25 propre
                                     # (necroDestroyer écarté : son boost = InescapableDeath, non porté)
OVERWATCH_EFFECT = 1009
BUILD = ["--roster", "1", "--p-units", MOVER_VIS, "--a-units", OVERWATCHER_VIS]


def _ok(r):
    return isinstance(r, dict) and r.get("ok")


def _seed_rng(s):
    rng = IntBasedMersenneTwister()
    rng.mt = list(s["mt"]); rng.mti = s["mti"]
    return rng


def _bfs(board, src):
    dist = {src: 0}; q = deque([src])
    while q:
        x = q.popleft()
        for n in board.neighbours(x):
            if n not in dist and (n == src or board.walkable(n)):
                dist[n] = dist[x] + 1; q.append(n)
    return dist


def test_overwatch_after_move_bit_exact(live_session, rpc, build_runner):
    """L'overwatch (attaque normale de l'overwatcher sur le mover) est reproduit bit-exact offline."""
    from engine.entities.pathfinding.board import Board
    rid = build_runner("777", extra=BUILD)["rid"]
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    if not (isinstance(bg, dict) and bg.get("tiles")):
        pytest.skip("boardGraph indispo")
    board = Board(bg["tiles"], adjacency="evenq")

    def tof(u):
        p = u.get("pos") or {}
        return board.id_at(p.get("col"), p.get("row")) if p.get("col") is not None else None

    dec = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    if not _ok(dec):
        pytest.skip("decisionView KO")
    units = dec.get("units") or []
    mover0 = next((u for u in units if u.get("visualId") == MOVER_VIS and u.get("alive")), None)
    ow = next((u for u in units if u.get("visualId") == OVERWATCHER_VIS and u.get("alive")), None)
    if mover0 is None or ow is None:
        pytest.skip(f"unite absente (mover={bool(mover0)} overwatcher={bool(ow)})")
    my_player = mover0.get("owner")
    # l'overwatcher doit porter l'effet Overwatch_AutoAttack (1009) actif au déploiement
    ow_effs = [e.get("effectType") for e in (ow.get("effects") or [])]
    if OVERWATCH_EFFECT not in ow_effs:
        pytest.skip(f"overwatcher sans effet Overwatch_AutoAttack(1009) actif (effets={ow_effs})")

    mover_id, ow_id = mover0["id"], ow["id"]
    # portée d'attaque max de l'overwatcher (R) : on s'approche VITE en restant hors portée (dist>R),
    # puis on entre d'1 pas (dist R) → 1 seule tuile de chemin en portée → 1 SEUL tir d'overwatch.
    import gameconfig as GC
    ow_weapons = (GC.unit(OVERWATCHER_VIS) or {}).get("weapons") or []
    R = max([int(w.get("Range") or 0) for w in ow_weapons] or [0]) or 1
    fired = None
    for _turn in range(30):
        dec = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
        mv = next((u for u in (dec.get("units") or []) if u["id"] == mover_id and u.get("alive")), None)
        owl = next((u for u in (dec.get("units") or []) if u["id"] == ow_id and u.get("alive")), None)
        if mv is None or owl is None:
            pytest.skip("mover/overwatcher disparu pendant l'approche")
        if dec.get("currentPlayer") != my_player:
            rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 40); continue
        dgoal = _bfs(board, tof(owl))
        mt = rpc("aiMovableTiles", {"runnerId": rid, "side": "friendly"}, 60)
        cmt = next((x for x in (mt.get("units") or []) if x.get("unitId") == mover_id), None)
        reach = {board.id_at(t["col"], t["row"]): (t["col"], t["row"])
                 for t in ((cmt or {}).get("tiles") or [])}
        cur = tof(mv)
        # Phase 1 : s'approcher VITE (multi-tuiles) en RESTANT hors portée (dist>R) ET strictement plus
        # proche (sinon on oscille au bord de portée sans jamais entrer).
        out_pool = [t for t in reach if t in dgoal and dgoal[t] > R and dgoal[t] < dgoal.get(cur, 99)]
        if dgoal.get(cur, 99) > R and out_pool:
            best = min(out_pool, key=lambda t: dgoal[t]); col, row = reach[best]
            rpc("applyAction", {"runnerId": rid, "action": {
                "kind": "move", "unitId": mover_id, "to": {"col": col, "row": row}}}, 40)
            dv2 = rpc("decisionView", {"runnerId": rid, "maxRank": 1}, 60)
            if dv2.get("currentPlayer") == my_player:
                rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 40)
            continue
        # Phase 2 : on est à dist<=R+1 → entrer d'1 pas DANS la portée (voisin de min dgoal) = 1 seul tir.
        step_pool = [t for t in reach if t in dgoal and t in set(board.neighbours(cur))]
        if not step_pool:
            rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 40); continue
        best = min(step_pool, key=lambda t: dgoal[t]); col, row = reach[best]

        # === capture AVANT le move (etat + MT cale) ===
        ob = rpc("observeBattle", {"runnerId": rid}, 40)
        snap = rpc("combatSnapshot", {"runnerId": rid}, 40)
        hp_before = next((u.get("hp") for u in (ob.get("units") or []) if u.get("squadId") == mover_id), None)
        s0 = rpc("dumpRng", {"runnerId": rid}, 30)
        state = load_state(dec, ob, snap, board=board)
        if not _ok(s0):
            pytest.skip("dumpRng KO")
        state.rng = _seed_rng(s0)

        # === move LIVE ===
        rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "move", "unitId": mover_id, "to": {"col": col, "row": row}}}, 40)
        ob2 = rpc("observeBattle", {"runnerId": rid}, 40)
        hp_after = next((u.get("hp") for u in (ob2.get("units") or []) if u.get("squadId") == mover_id), None)
        if hp_before is None or hp_after is None:
            continue
        if hp_after >= hp_before:
            continue                                   # pas d'overwatch sur ce move → approcher encore

        # overwatch a firé live → REPLAY offline depuis l'etat AVANT
        oe = state.get_entity(ow_id)
        if oe is None or oe.get_component(StatsComponent) is None:
            pytest.skip("overwatcher sans StatsComponent offline (combatSnapshot ne couvre pas)")
        runner = Runner(state).install_default_handlers(20)
        runner.apply(MoveUnitMessage(mover_id, (col, row)))
        am = runner.movement_handler.after_move
        off_hp = state.get_entity(mover_id).get_component(HealthComponent).hp
        fired = {"hp_before": hp_before, "hp_after_live": hp_after, "off_hp": off_hp,
                 "after_move": am, "tile": (col, row)}
        break
    if fired is None:
        pytest.skip("aucun overwatch declenche en 20 tours (portee/geometrie)")

    _r = ([a for a in (fired["after_move"] or []) if a.get("effect") == "Overwatch_AutoAttack"] or [{}])[0].get("result") or {}
    print(f"\n[OVERWATCH] mover hp {fired['hp_before']} -> live {fired['hp_after_live']} "
          f"(live dmg={fired['hp_before'] - fired['hp_after_live']}) | offline {fired['off_hp']} "
          f"(off dmg={fired['hp_before'] - fired['off_hp']})")
    print(f"[OVERWATCH] offline result: per_hit={_r.get('per_hit')} pierce={_r.get('pierce')} "
          f"armor={_r.get('armor')} ranged={_r.get('ranged')} profile={_r.get('profile')} "
          f"base=[{_r.get('base_min')},{_r.get('base_max')}] clean=[{_r.get('clean_min')},{_r.get('clean_max')}]")
    ow_results = [a for a in (fired["after_move"] or []) if a.get("effect") == "Overwatch_AutoAttack"]
    assert ow_results, ("le vecteur after-move offline n'a PAS declenche l'overwatch "
                        f"(after_move={fired['after_move']})")
    assert fired["off_hp"] == fired["hp_after_live"], (
        f"PV mover offline {fired['off_hp']} != live {fired['hp_after_live']} "
        f"(overwatch dmg live={fired['hp_before'] - fired['hp_after_live']})")
