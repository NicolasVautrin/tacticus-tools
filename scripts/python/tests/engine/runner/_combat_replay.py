"""Helper RÉUTILISABLE de REPLAY-DIFF d'attaque normale (offline vs live) — socle du harnais de
couverture catalogue (valider chaque unité/ability/effet/trait par accord live).

`replay_normal_attack(rpc, build_runner, attacker, target, ...)` : build 1v1 isolé, positionne
l'attaquant au contact HEX de la cible (boardGraph = vérité hex), rejoue LA MÊME attaque normale
live (`applyAction`) ET offline (`AttackUnitMessage`, MT calé via dumpRng), et renvoie une
CLASSIFICATION (pas d'assert ici — le test appelant décide pass/xfail/skip) :

    {ok, reason, exact, hits, live_ph, off_ph, live_after, off_after,
     did_crit, did_block, did_evade, effects}

`ok=False`+`reason` = scénario impossible (skip). `exact` = per-hit ET PV cible identiques.
Mêmes invariants que les tests crit/block (dont il généralise la logique) : lit l'état LIVE,
pas de tuile/RVA hardcodée, seed = simple générateur.
"""
from __future__ import annotations

import json
from collections import deque

from engine.runner.snapshot import load_state
from engine.runner.runner import Runner
from engine.runner.messages import AttackUnitMessage
from engine.runner.prng import IntBasedMersenneTwister
from engine.runner.components import HealthComponent
from engine.entities.pathfinding.board import Board


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


def _skip(reason):
    return {"ok": False, "reason": reason}


def replay_normal_attack(rpc, build_runner, attacker, target="eldarFarseer",
                         extra=None, seed="777", max_turns=20):
    """Rejoue l'attaque normale de `attacker` (visualId) sur `target` en 1v1 mêlée hex. Renvoie
    la classification (cf. en-tête). `extra` = args rl_duel build supplémentaires (ex. --crit)."""
    build_extra = ["--roster", "1", "--p-units", attacker, "--a-units", target, *(extra or [])]
    b = build_runner(seed, extra=build_extra)
    rid = b["rid"]
    if not _ok(rpc("dumpRng", {"runnerId": rid}, 30)):
        return _skip("dumpRng indispo")
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    if not (isinstance(bg, dict) and "tiles" in bg):
        return _skip("boardGraph indispo")
    board = Board(bg["tiles"], adjacency="native_sym")

    def utile(u):
        p = u.get("pos") or {}
        return board.id_at(p.get("col"), p.get("row")) if "col" in p else None

    my_player = None
    for _turn in range(max_turns):
        dec = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
        if not _ok(dec):
            return _skip("decisionView KO")
        units = dec.get("units") or []
        champ = next((u for u in units if u.get("visualId") == attacker and u.get("alive")), None)
        tgt = next((u for u in units if u.get("visualId") == target and u.get("alive")), None)
        if champ is None or tgt is None:
            return _skip(f"unite manquante (champ={bool(champ)} tgt={bool(tgt)})")
        if my_player is None:
            my_player = champ.get("owner")
        if dec.get("currentPlayer") != my_player:
            rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 40)
            continue
        ctile, ttile = utile(champ), utile(tgt)
        if ctile in board.neighbours(ttile):
            return _do_replay(rpc, rid, board, champ, tgt, None)
        dist = _bfs(board, ttile)
        mt = rpc("aiMovableTiles", {"runnerId": rid, "side": "friendly"}, 60)
        cmt = next((x for x in (mt.get("units") or []) if x.get("unitId") == champ["id"]), None)
        reach = {board.id_at(t["col"], t["row"]): (t["col"], t["row"])
                 for t in ((cmt or {}).get("tiles") or [])}
        adj = [(tid, cr) for tid, cr in reach.items() if tid in board.neighbours(ttile)]
        if adj:
            tid, (col, row) = adj[0]
            return _do_replay(rpc, rid, board, champ, tgt, (col, row))
        pool = [tid for tid in reach if tid in dist]
        if not pool:
            rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 40); continue
        best = min(pool, key=lambda t: dist[t]); col, row = reach[best]
        rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "move", "unitId": champ["id"], "to": {"col": col, "row": row}}}, 40)
        rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 40)
    return _skip(f"{attacker} n'a pas atteint {target} en melee en {max_turns} tours")


def _do_replay(rpc, rid, board, champ, tgt, move_to):
    att, tid = champ["id"], tgt["id"]
    if move_to is not None:
        rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "move", "unitId": att, "to": {"col": move_to[0], "row": move_to[1]}}}, 40)
    dv2 = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    ob2 = rpc("observeBattle", {"runnerId": rid}, 40)
    a2 = next((u for u in (dv2.get("units") or []) if u.get("id") == att), None)
    norm = next((ab for ab in ((a2 or {}).get("abilities") or []) if ab.get("kind") == "normal"), None)
    if norm is None:
        return _skip("pas d'attaque normale")
    att_eff = [e.get("name") for e in ((a2 or {}).get("effects") or []) if e.get("name")]
    snap2 = rpc("combatSnapshot", {"runnerId": rid}, 40)
    # #63/#64 : `state.board` peuple A LA SOURCE via `load_state(..., board=board)` -> les feuilles
    # POSITIONNELLES du combat (elevation `CalculateElevationBonusModifier`, trench, LightCover,
    # GetStuckIn) ne sont plus des no-op OFFLINE. Le combat natif applique le bonus d'ELEVATION
    # (+ELEVATION_BONUS_PCT=50% quand l'attaquant surplombe la cible) AVANT percage/armure ; l'omettre
    # rendait l'offline TROP BAS (ratio 0.58-0.67 sur un tir armor-sensitive en surplomb). Le `Board`
    # DEJA construit ici (memes elevations que le boardGraph live) est passe a load_state -> board
    # attache par construction (plus de `state.board=` disperse a oublier). Cf. docs/rl/case-63.
    state = load_state(dv2, ob2, snap2, board=board)
    ae = state.get_entity(att)
    from engine.runner.components import StatsComponent
    if ae is None or ae.get_component(StatsComponent) is None:
        return _skip("attaquant sans StatsComponent offline (stats non chargees)")
    te = state.get_entity(tid)
    hc = te.get_component(HealthComponent) if te is not None else None
    if hc is None or hc.hp is None:
        return _skip("cible introuvable offline")
    hp_before = hc.hp
    s0 = rpc("dumpRng", {"runnerId": rid}, 30)
    if not _ok(s0):
        return _skip("dumpRng KO")
    state.rng = _seed_rng(s0)
    runner = Runner(state).install_default_handlers(20)
    res = rpc("applyAction", {"runnerId": rid, "action": {
        "kind": "ability", "casterId": att, "targetId": tid, "abilityType": norm["id"]}}, 40)
    a0 = (res.get("actions") or [{}])[0]
    if not (_ok(res) and a0.get("ok")):
        return _skip(f"attaque live KO: {str(res)[:120]}")
    live_ph, dc, db, de = [], False, False, False
    for e in (a0.get("events") or []):
        td = e.get("tags")
        if not td:
            continue
        td = json.loads(td) if isinstance(td, str) else td
        if td.get("Target_Id") == tid and "Amount" in td and td.get("Active_Ability_Type") == norm["id"]:
            live_ph.append(td.get("Amount"))
            dc = dc or bool(td.get("Attack_DidCrit"))
            db = db or bool(td.get("Attack_DidBlock"))
            de = de or bool(td.get("Attack_DidEvade"))
    live_after = next((u.get("hp") for u in (res.get("units") or []) if u.get("squadId") == tid), None)
    runner.apply(AttackUnitMessage(att, tid))
    rr = runner.damage_handler.last
    if rr is None:
        return _skip("offline rr=None (non calcule)")
    off_after = state.get_entity(tid).get_component(HealthComponent).hp
    exact = (rr.get("per_hit") == live_ph and off_after == live_after)
    return {"ok": True, "reason": None, "exact": exact, "hits": rr.get("hits"),
            "live_ph": live_ph, "off_ph": rr.get("per_hit"),
            "live_after": live_after, "off_after": off_after,
            "armor": rr.get("armor"), "pierce": rr.get("pierce"),
            "did_crit": dc, "did_block": db, "did_evade": de, "effects": att_eff}


def _find_elev_pair(board, want_dist, require_higher_elev):
    """Cherche (tuile_cible T, tuile_attaquant A) toutes deux walkable, a hex-distance `want_dist`,
    avec elev(A) > elev(T) si `require_higher_elev` (pour armer le bonus d'ELEVATION). Renvoie
    ((tcol,trow),(acol,arow), t_elev, a_elev) ou None. Deterministe (parcours trie par id)."""
    import hexgeo
    tiles = [t for t in board.by_id.values() if t.get("walkable") and not t.get("isWall")]
    tiles.sort(key=lambda t: t["id"])
    for tt in tiles:
        tp = (tt["col"], tt["row"]); te = tt["elevation"]
        for at in tiles:
            if at["id"] == tt["id"]:
                continue
            ap = (at["col"], at["row"]); ae = at["elevation"]
            if hexgeo.distance(ap, tp) != want_dist:
                continue
            if require_higher_elev and not (ae > te):
                continue
            return tp, ap, te, ae
    return None


def replay_attack_driven(rpc, build_runner, attacker, target, want_dist=2,
                         require_higher_elev=True, seed="777", extra=None, max_turns=6):
    """Comme `replay_normal_attack` mais POSITIONS DRIVEES (applyAction ignore la portee) : place la
    cible et l'attaquant sur des tuiles a hex-distance `want_dist` (et, si `require_higher_elev`, avec
    l'attaquant EN SURPLOMB) pour exercer le bonus d'ELEVATION du chemin combat (feuille positionnelle
    `apply_elevation_bonus`). Charge le board dans l'etat de replay (via `_do_replay`, corrige #63).
    Renvoie la classification enrichie de {a_elev, t_elev, dist} ou {ok:False,reason}."""
    build_extra = ["--roster", "1", "--p-units", attacker, "--a-units", target, *(extra or [])]
    b = build_runner(seed, extra=build_extra)
    rid = b["rid"]
    if not _ok(rpc("dumpRng", {"runnerId": rid}, 30)):
        return _skip("dumpRng indispo")
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    if not (isinstance(bg, dict) and "tiles" in bg):
        return _skip("boardGraph indispo")
    board = Board(bg["tiles"], adjacency="native_sym")
    pair = _find_elev_pair(board, want_dist, require_higher_elev)
    if pair is None:
        return _skip(f"aucune paire de tuiles dist={want_dist} "
                     f"{'avec surplomb' if require_higher_elev else ''} sur ce board")
    tp, ap, t_elev, a_elev = pair
    dv = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    if not _ok(dv):
        return _skip("decisionView KO")
    champ = next((u for u in (dv.get("units") or []) if u.get("visualId") == attacker and u.get("alive")), None)
    tgt = next((u for u in (dv.get("units") or []) if u.get("visualId") == target and u.get("alive")), None)
    if champ is None or tgt is None:
        return _skip(f"unite manquante (champ={bool(champ)} tgt={bool(tgt)})")
    # place cible puis attaquant sur les tuiles choisies
    rpc("applyAction", {"runnerId": rid, "action": {
        "kind": "move", "unitId": tgt["id"], "to": {"col": tp[0], "row": tp[1]}}}, 40)
    rpc("applyAction", {"runnerId": rid, "action": {
        "kind": "move", "unitId": champ["id"], "to": {"col": ap[0], "row": ap[1]}}}, 40)
    # caler le tour de l'attaquant
    my_player = champ.get("owner")
    for _ in range(max_turns):
        dv = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
        if dv.get("currentPlayer") == my_player:
            break
        rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 40)
    dv = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    champ = next((u for u in (dv.get("units") or []) if u.get("id") == champ["id"] and u.get("alive")), None)
    tgt = next((u for u in (dv.get("units") or []) if u.get("id") == tgt["id"] and u.get("alive")), None)
    if champ is None or tgt is None:
        return _skip("unite manquante post-move")
    r = _do_replay(rpc, rid, board, champ, tgt, None)
    if r.get("ok"):
        r.update({"a_elev": a_elev, "t_elev": t_elev, "dist": want_dist})
    return r
