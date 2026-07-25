"""VECTEUR AFTER-HIT — splash « Smite » du trait PSYKER : replay-diff LIVE vs moteur porté.

Valide `triggers.psyker_extra_attack` (mirror `PsykerExtraAttackAbility` IdunBattleLogic.Entities.Abilities.Active.Loki.PsykerExtraAttackAbility$$CreateBehaviour..) : après une attaque
NORMALE RANGED de profil PSYCHIQUE, le trait Psyker déclenche une extra-attaque sur UN ennemi adjacent
(hex) à la cible primaire — `PickRandomly(1)` de `Damageable(Enemies(AdjacentUnits(cible)))` — pour
`round(Attack × psykerExtraDmg%)` Psychic, montant `StatAmount` PLAT (aucune variance d'arme), Psychic
pierce 100 → armure ignorée.

Fixture = astraPrimarisPsy vs un cluster MÊLÉE (ennemis adjacents entre eux). On CONDUIT le psyker (qui
ne fait que se déplacer → survit) jusqu'à d=2 (portée de l'arme RANGED psychique : à d=1 c'est l'arme
MÊLÉE → pas de trigger, vérifié) d'une cible primaire ayant EXACTEMENT 1 ennemi adjacent (pas
d'ambiguïté de tirage). On confronte : (a) per-coup primaire bit-exact, (b) le splash FIRE live,
(c) la cible splash live == offline, (d) le dégât splash live == offline.

⚠ ADJACENCE = mode **evenq** (géométrie hex recalculée), PAS `native_sym` : la capture native de
`boardGraph.neighbours` est partielle/asymétrique (tile coin vide, ~13 arêtes one-way) et SOUS-rapporte
l'adjacence — le JEU, lui, splashe un ennemi evenq-adjacent que le graphe natif ne liste pas (preuve
live que l'adjacence fidèle = evenq, pas la capture).
"""
from __future__ import annotations

import json
from collections import deque

import pytest

from engine.runner.snapshot import load_state
from engine.runner.runner import Runner
from engine.runner.messages import AttackUnitMessage
from engine.runner.prng import IntBasedMersenneTwister
from engine.runner.components import HealthComponent, StatsComponent

CASTER_VIS = "astraPrimarisPsy"
# cluster mêlée : ennemis qui spawnent groupés (adjacents entre eux en evenq), tanky => survivent au coup.
ENEMIES = "darkaCompanion,tyranWingedPrime,ultraInceptorSgt,spaceBlackmane,necroSpyder"
BUILD = ["--roster", "1", "--p-units", CASTER_VIS, "--a-units", ENEMIES]


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


def test_psyker_smite_splash_bit_exact(live_session, rpc, build_runner):
    """Le splash Psyker (cible adjacente + dégât StatAmount plat) est reproduit bit-exact offline."""
    from engine.entities.pathfinding.board import Board
    rid = build_runner("777", extra=BUILD)["rid"]
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    if not (isinstance(bg, dict) and bg.get("tiles")):
        pytest.skip("boardGraph indispo")
    board = Board(bg["tiles"], adjacency="evenq")     # evenq = adjacence FIDÈLE (cf. docstring)

    def tile_of(u):
        p = u.get("pos") or {}
        return board.id_at(p.get("col"), p.get("row")) if p.get("col") is not None else None

    def enemies(dec, mp):
        return [u for u in (dec.get("units") or []) if u.get("owner") != mp and u.get("alive")]

    def adj_enemy_ids(t_tile, ens):
        nb = set(board.neighbours(t_tile))
        return [e for e in ens if tile_of(e) in nb]

    # 1) découvrir le caster + l'ability normale
    dec = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    if not _ok(dec):
        pytest.skip("decisionView KO")
    ps0 = next((u for u in (dec.get("units") or []) if u.get("visualId") == CASTER_VIS and u.get("alive")), None)
    if ps0 is None:
        pytest.skip("psyker absent")
    my_player = ps0.get("owner")
    norm = next((ab for ab in (ps0.get("abilities") or []) if ab.get("kind") == "normal"), None)
    if norm is None:
        pytest.skip("ability normale du psyker introuvable")
    norm_id = norm.get("id")

    # 2) conduire le psyker vers une cible T (en fromHere à d>=2, donc arme RANGED) ayant EXACTEMENT
    #    1 ennemi adjacent (evenq). Le psyker ne fait que bouger -> survit indéfiniment.
    chosen = None
    for _turn in range(60):
        dec = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
        if not _ok(dec):
            pytest.skip("decisionView KO")
        ps = next((u for u in (dec.get("units") or []) if u["id"] == ps0["id"] and u.get("alive")), None)
        if ps is None:
            pytest.skip("psyker mort pendant l'approche")
        ens = enemies(dec, my_player)
        if len(ens) < 2:
            pytest.skip("moins de 2 ennemis vivants")
        if dec.get("currentPlayer") != my_player:
            rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 40); continue
        # fromHere du normal (légalité de cast SANS bouger = vérité jeu portée/LoS)
        at = rpc("abilityTargets", {"runnerId": rid, "unitId": ps["id"], "allAbilities": True}, 90)
        fh = set()
        for unit in (at.get("units") or []):
            if unit.get("unitId") != ps["id"]:
                continue
            for ab in (unit.get("abilities") or []):
                if ab.get("abilityId") != norm_id:
                    continue
                for tg in (ab.get("fromHere") or []):
                    if tg.get("kind") == "unit":
                        fh.add(tg.get("targetId"))
        dist_ps = _bfs(board, tile_of(ps))
        # cible idéale : dans fromHere, à d>=2 (RANGED), exactement 1 ennemi adjacent
        cands = []
        for T in ens:
            if T["id"] not in fh:
                continue
            if dist_ps.get(tile_of(T), 99) < 2:        # d<2 => arme mêlée => pas de trigger
                continue
            adjE = adj_enemy_ids(tile_of(T), ens)
            if len(adjE) == 1:
                cands.append((T, adjE[0]))
        if cands:
            chosen = cands[0]
            break
        # approcher la cible la plus proche ayant un voisin ennemi (sans coller : viser d>=2)
        goals = [T for T in ens if adj_enemy_ids(tile_of(T), ens)]
        goal = min(goals or ens, key=lambda T: dist_ps.get(tile_of(T), 99))
        dgoal = _bfs(board, tile_of(goal))
        mt = rpc("aiMovableTiles", {"runnerId": rid, "side": "friendly"}, 60)
        cmt = next((x for x in (mt.get("units") or []) if x.get("unitId") == ps["id"]), None)
        reach = {board.id_at(t["col"], t["row"]): (t["col"], t["row"])
                 for t in ((cmt or {}).get("tiles") or [])}
        pool = [t for t in reach if t in dgoal and dgoal[t] >= 2] or [t for t in reach if t in dgoal]
        if pool:
            best = min(pool, key=lambda t: dgoal[t]); col, row = reach[best]
            rpc("applyAction", {"runnerId": rid, "action": {
                "kind": "move", "unitId": ps["id"], "to": {"col": col, "row": row}}}, 40)
        dv2 = rpc("decisionView", {"runnerId": rid, "maxRank": 1}, 60)
        if dv2.get("currentPlayer") == my_player:
            rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 40)
    if chosen is None:
        pytest.skip("aucun scénario splash (cible RANGED avec 1 voisin ennemi) atteint en 60 tours")

    T, adjE = chosen
    att, tid, eid = ps0["id"], T["id"], adjE["id"]

    # 3) capture AVANT + seed rng
    dv = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    ob = rpc("observeBattle", {"runnerId": rid}, 40)
    snap = rpc("combatSnapshot", {"runnerId": rid}, 40)
    state = load_state(dv, ob, snap, board=board)
    ae = state.get_entity(att)
    if ae is None or ae.get_component(StatsComponent) is None:
        pytest.skip("psyker sans StatsComponent")
    if "Psyker" not in (ae.get_component(StatsComponent).ctx.traits or []):
        pytest.skip("le caster n'a pas le trait Psyker offline")
    s0 = rpc("dumpRng", {"runnerId": rid}, 30)
    if not _ok(s0):
        pytest.skip("dumpRng KO")
    state.rng = _seed_rng(s0)

    # 4) tir LIVE de l'attaque NORMALE (= Smite ; le splash en est le déclenchement after-hit)
    res = rpc("applyAction", {"runnerId": rid, "action": {
        "kind": "ability", "casterId": att, "targetId": tid, "abilityType": norm_id}}, 60)
    a0 = (res.get("actions") or [{}])[0]
    if not (_ok(res) and a0.get("ok")):
        pytest.skip(f"cast KO: {str(res)[:160]}")
    by_target: dict[int, list[int]] = {}
    crit_block = False
    for e in (a0.get("events") or []):
        td = e.get("tags")
        if not td:
            continue
        td = json.loads(td) if isinstance(td, str) else td
        if "Amount" in td and td.get("Target_Id") is not None:
            by_target.setdefault(td["Target_Id"], []).append(td["Amount"])
            if td.get("Target_Id") == tid and (td.get("Attack_DidCrit") or td.get("Attack_DidBlock")
                                               or td.get("Attack_DidEvade")):
                crit_block = True
    live_primary = by_target.get(tid)
    live_splash = by_target.get(eid)
    if not live_primary:
        pytest.skip("aucun dégât primaire live capturé")
    if crit_block:
        pytest.skip("coup primaire non propre (crit/block/evade) hors axe")
    # le splash DOIT firer live (attaque ranged psychique + 1 ennemi adjacent)
    assert live_splash, (f"splash Psyker n'a PAS firé live (by_target={by_target}, primary={tid}, "
                         f"adjE={eid}) — trigger ranged-psychic attendu")

    # 5) OFFLINE : l'attaque NORMALE dérive le splash via le vecteur after-hit
    runner = Runner(state).install_default_handlers(20)
    runner.apply(AttackUnitMessage(att, tid))
    dh = runner.damage_handler
    off_primary = (dh.last or {}).get("per_hit")
    splash = [a for a in (dh.after_hit or []) if a.get("trait") == "Psyker"]
    off_splash_tid = splash[0]["target"] if splash else None
    off_splash_ph = splash[0]["result"]["per_hit"] if splash else None
    print(f"\n[PSYKER splash] primary T={tid} live={live_primary} off={off_primary} | "
          f"splash live tgt={eid} amt={live_splash} | off tgt={off_splash_tid} amt={off_splash_ph} | "
          f"ranged={dh.last.get('ranged')} profile={dh.last.get('profile')}")
    assert dh.last.get("ranged") is True, "l'attaque offline doit être RANGED (arme psychique d=2)"
    assert dh.last.get("profile") == "Psychic", "profil offline doit être Psychic"
    assert off_primary == live_primary, f"per-coup primaire offline {off_primary} != live {live_primary}"
    assert off_splash_tid == eid, f"cible splash offline {off_splash_tid} != live {eid}"
    assert off_splash_ph == live_splash, f"dégât splash offline {off_splash_ph} != live {live_splash}"
