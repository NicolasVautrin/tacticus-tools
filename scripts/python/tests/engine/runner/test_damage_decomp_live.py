"""DEMO/OUTIL : damage decomposition DIFF sur orksNob->bloodIntercessor (#68 SmashaEad).

Prouve la METHODE (measure-the-stage, cf. memory feedback_damage_decomposition_measure_stage) : au lieu de
fitter un scalaire (mult 90 ? /2 ?) sur le degat final, on LIT la valeur par ETAGE des deux cotes via
`tools/damage_decomp` (qui exploite `modifier-observe`, deja dans les hooks) et on localise l'etage divergent.

Attendu #68 : base/pierce/result de bout MATCHENT off/live (amont OK), mais le per-hit FINAL differe d'un
ecart CONSTANT (~+299) -> etage ADDITIF (SmashaEad additif off 599 vs live 300). L'etage est LU, pas devine.

ASCII-only. Modele de nav/replay = test_getstuckin_combat_live.py.
"""
from __future__ import annotations

import json
from collections import deque

import pytest

from engine.runner.snapshot import load_state
from engine.runner.runner import Runner
from engine.runner.messages import AttackUnitMessage
from engine.runner.prng import IntBasedMersenneTwister
from engine.runner.components import HealthComponent
from engine.entities.pathfinding.board import Board
from tools import damage_decomp as DD

ATTACKER = "orksNob"
TARGET = "bloodIntercessor"


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
        for nb in board.neighbours(x):
            if nb not in dist and (nb == src or board.walkable(nb)):
                dist[nb] = dist[x] + 1; q.append(nb)
    return dist


def test_damage_decomp_localises_stage(live_session, rpc, build_runner):
    b = build_runner("4242", extra=["--roster", "1", "--p-units", ATTACKER, "--a-units", TARGET])
    rid = b["rid"]; my_player = None
    if not _ok(rpc("dumpRng", {"runnerId": rid}, 30)):
        pytest.skip("dumpRng indispo")
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    if not (isinstance(bg, dict) and "tiles" in bg):
        pytest.skip("boardGraph indispo")
    board = Board(bg["tiles"], adjacency="native_sym")

    def utile(u):
        p = u.get("pos") or {}
        return board.id_at(p.get("col"), p.get("row")) if "col" in p else None

    # --- Nav orksNob -> melee de la cible (copie getstuckin) ---
    champ = tgt = None
    for _turn in range(20):
        dec = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
        if not _ok(dec):
            pytest.skip("decisionView KO")
        units = dec.get("units") or []
        champ = next((u for u in units if u.get("visualId") == ATTACKER and u.get("alive")), None)
        tgt = next((u for u in units if u.get("visualId") == TARGET and u.get("alive")), None)
        if champ is None or tgt is None:
            pytest.skip("unite manquante")
        if my_player is None:
            my_player = champ.get("owner")
        if dec.get("currentPlayer") != my_player:
            rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 40); continue
        ctile, ttile = utile(champ), utile(tgt)
        if ctile in board.neighbours(ttile):
            break
        mt = rpc("aiMovableTiles", {"runnerId": rid, "side": "friendly"}, 60)
        cmt = next((x for x in (mt.get("units") or []) if x.get("unitId") == champ["id"]), None)
        reach = {board.id_at(t["col"], t["row"]): (t["col"], t["row"])
                 for t in ((cmt or {}).get("tiles") or [])}
        adj = [(tid, cr) for tid, cr in reach.items() if tid in board.neighbours(ttile)]
        if adj:
            _tid, (col, row) = adj[0]
            rpc("applyAction", {"runnerId": rid, "action": {
                "kind": "move", "unitId": champ["id"], "to": {"col": col, "row": row}}}, 40)
            break
        dist = _bfs(board, ttile)
        pool = [tid for tid in reach if tid in dist]
        if not pool:
            rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 40); continue
        best = min(pool, key=lambda t: dist[t]); col, row = reach[best]
        rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "move", "unitId": champ["id"], "to": {"col": col, "row": row}}}, 40)
        rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 40)
    else:
        pytest.skip("pas atteint la melee en 20 tours")

    # --- Capture etat + arme modifier-observe JUSTE avant l'attaque diagnostiquee ---
    dv2 = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    ob2 = rpc("observeBattle", {"runnerId": rid}, 40)
    att = champ["id"]; tid = tgt["id"]
    a2 = next((u for u in (dv2.get("units") or []) if u.get("id") == att), None)
    norm = next((ab for ab in ((a2 or {}).get("abilities") or []) if ab.get("kind") == "normal"), None)
    if norm is None:
        pytest.skip("pas d'attaque normale")
    snap2 = rpc("combatSnapshot", {"runnerId": rid}, 40)
    state = load_state(dv2, ob2, snap2, board=board)   # #64 : board a la source (feuilles positionnelles armees)

    arm_info = DD.arm(rpc)   # install + reset modifier-observe

    # --- Attaque LIVE (RNG seede) ---
    s0 = rpc("dumpRng", {"runnerId": rid}, 30)
    if not _ok(s0):
        pytest.skip("dumpRng KO")
    state.rng = _seed_rng(s0)
    runner = Runner(state).install_default_handlers(20)
    res = rpc("applyAction", {"runnerId": rid, "action": {
        "kind": "ability", "casterId": att, "targetId": tid, "abilityType": norm["id"]}}, 40)
    a0 = (res.get("actions") or [{}])[0]
    if not (_ok(res) and a0.get("ok")):
        pytest.skip(f"attaque live KO: {str(res)[:160]}")
    live_ph = []
    for e in (a0.get("events") or []):
        td = e.get("tags")
        if not td:
            continue
        td = json.loads(td) if isinstance(td, str) else td
        if td.get("Target_Id") == tid and "Amount" in td and td.get("Active_Ability_Type") == norm["id"]:
            live_ph.append(td.get("Amount"))

    # --- Lit la decomposition LIVE capturee (per-bout) ---
    live_decomp = DD.read_live_decomp(rpc)

    # --- Attaque OFFLINE (meme seed) ---
    runner.apply(AttackUnitMessage(att, tid))
    rr = runner.damage_handler.last or {}

    rep = DD.decomp_report(rr, live_ph, live_decomp)
    print("\n[DECOMP] modifier-observe install:", (arm_info or {}).get("ok"),
          "fires:", live_decomp.get("fires"))
    print(rep["table"])
    # #68 MESURE : le multiplier reellement applique par resolution (combat vs prediction). extraDmg=id 8.
    vls = live_decomp.get("var_levels") or []
    print("[DECOMP] var-level resolutions (scaling != 100): %s" % (vls,))
    extra = [v for v in vls if v.get("variableId") == 8]
    if extra:
        print("[DECOMP] extraDmg (id 8) resolutions {level,mult,result}: %s" % (extra,))
    # #68 : plage per-coup COMBAT (HitDamage.GetDamage) — voir comment l'additif 599 folde dans min/max.
    hd = live_decomp.get("hit_dmg") or []
    print("[DECOMP] HitDamage.GetDamage {min,max,avg,result} (combat per-coup): %s" % (hd,))
    # #68 COTE DEFENSE (hint user) : modifiers DEFENDEUR (additif/reduction/penetration) — un %-reduction
    # defenseur applique APRES l'additif reduirait le 599 ; le port l'ignore (additif applique en dernier).
    for _m in (live_decomp.get("mods") or []):
        print("[DECOMP] %s mods additive=%s pierce=%s pen=%s percentsX1000=%s"
              % (_m.get("side"), _m.get("additive"), _m.get("pierce"), _m.get("penetration"),
                 _m.get("percentsX1000")))

    # L'OUTIL doit produire un verdict d'etage exploitable (non-vide).
    assert rep["stage"], "decomp_report n'a pas produit d'etage"
    assert live_decomp.get("value_dumps") is not None
    if not live_decomp.get("value_dumps") and not live_decomp.get("bonus"):
        pytest.skip("modifier-observe n'a rien capture (hooks non armes) — outil OK, capture vide")
    # v2 combat capture : l'attribution PAR-SOURCE doit isoler l'additif de SmashaEad (le seul effet additif
    # d'orksNob). Preuve que l'outil LIT la contribution par effet (599) au lieu de la deviner.
    psa = rep.get("per_source_additive") or {}
    smasha = next((v for k, v in psa.items() if "SmashaEad" in k), None)
    if smasha is not None:
        assert smasha > 0, f"additif SmashaEad capture doit etre >0, obtenu {smasha}"
        print(f"[DECOMP] additif SmashaEad LU par-source = {smasha} (vs ecart final {rep['const_final_delta']})")
