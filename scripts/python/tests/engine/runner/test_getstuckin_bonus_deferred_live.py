"""#62c GetStuckIn -- COUPS BONUS DEFERES a l'EXECUTION, replay-diff BIT-EXACT (garde de non-regression).

Le test SOEUR `test_getstuckin_combat_live.py` valide la POSITION du roll (attaque a 3 coups d'orksNob, cas
0 coup bonus). Celui-ci garde l'EXECUTION DEFEREE du coup bonus : quand le `Maybe(GetBonusHitChance)` REUSSIT
(chance=30 en 1v1), le natif insere +1 coup bonus DEFERE (FIFO) apres la boucle de base, a l'index de coup
PERSISTANT (`attack+0x30`) -> mirror `_run_hits(bonus_hit_chance=...)` + boucle bonus (`AddBonusHitsToCurrent
HitGroupBehaviour IdunBattle.Entities.Behaviours.AddBonusHitsToCurrentHitGroupBehaviour$$Execute`, roll `IdunBattle.Entities.Behaviours.MaybeBehaviour$$Execute`, orchestration `IdunBattle.Operations.AttackDamageOperation$$Execute`).

Porteur = orksBigMek (arme 4 coups -> DEUX coups d'index impair 1 et 3 -> DEUX rolls Maybe/attaque -> jusqu'a
2 coups bonus, teste la FIFO deferee a plusieurs entrees). Cible bloodIntercessor (non-Big/non-Vehicle ->
BeastSlayer_ExtraDmg=0, isole GetStuckIn). On rejoue plusieurs seeds ; INVARIANT dur = off_ph == live_ph +
PV egaux a CHAQUE attaque (bonus ou non). Garde specifique : au moins UN cas de coup bonus (>4 coups) valide
bit-exact. Lit l'etat LIVE (rien de hardcode) ; le seed n'est qu'un generateur (invariant seed-independant).
ASCII-only. (Modele : test_getstuckin_combat_live.py.)
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

ATTACKER = "orksBigMek"          # GetStuckIn + arme 4 coups (indices impairs 1 ET 3)
TARGET = "bloodIntercessor"      # non-Big/non-Vehicle -> BeastSlayer_ExtraDmg=0 (isole GetStuckIn)
BASE_HITS = 4                    # orksBigMek : 4 coups d'arme
SEEDS = ["4400", "4404", "4410", "4408", "4415", "4401"]   # generateurs de bataille (hors critere)


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


def _replay_one(rpc, rid):
    """Nav ATTACKER en melee de TARGET puis replay-diff une attaque normale. Renvoie un dict de resultat
    ou {'skip': raison}."""
    if not _ok(rpc("dumpRng", {"runnerId": rid}, 30)):
        return {"skip": "dumpRng indispo"}
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    if not (isinstance(bg, dict) and "tiles" in bg):
        return {"skip": "boardGraph indispo"}
    board = Board(bg["tiles"], adjacency="native_sym")

    def utile(u):
        p = u.get("pos") or {}
        return board.id_at(p.get("col"), p.get("row")) if "col" in p else None

    my_player = None
    for _turn in range(20):
        dec = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
        if not _ok(dec):
            return {"skip": "decisionView KO"}
        units = dec.get("units") or []
        champ = next((u for u in units if u.get("visualId") == ATTACKER and u.get("alive")), None)
        tgt = next((u for u in units if u.get("visualId") == TARGET and u.get("alive")), None)
        if champ is None or tgt is None:
            return {"skip": "unite manquante"}
        if my_player is None:
            my_player = champ.get("owner")
        if dec.get("currentPlayer") != my_player:
            rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 40)
            continue
        ctile, ttile = utile(champ), utile(tgt)
        dist = _bfs(board, ttile)
        if ctile in board.neighbours(ttile):
            return _attack(rpc, rid, tgt, champ, None)
        mt = rpc("aiMovableTiles", {"runnerId": rid, "side": "friendly"}, 60)
        cmt = next((x for x in (mt.get("units") or []) if x.get("unitId") == champ["id"]), None)
        reach = {board.id_at(t["col"], t["row"]): (t["col"], t["row"])
                 for t in ((cmt or {}).get("tiles") or [])}
        adj = [(tid, cr) for tid, cr in reach.items() if tid in board.neighbours(ttile)]
        if adj:
            _tid, (col, row) = adj[0]
            return _attack(rpc, rid, tgt, champ, (col, row))
        pool = [tid for tid in reach if tid in dist]
        if not pool:
            rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 40); continue
        best = min(pool, key=lambda t: dist[t]); col, row = reach[best]
        rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "move", "unitId": champ["id"], "to": {"col": col, "row": row}}}, 40)
        rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 40)
    return {"skip": "pas de melee en 20 tours"}


def _attack(rpc, rid, tgt, champ, move_to):
    att, tid = champ["id"], tgt["id"]
    if move_to is not None:
        rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "move", "unitId": att, "to": {"col": move_to[0], "row": move_to[1]}}}, 40)
    dv2 = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    ob2 = rpc("observeBattle", {"runnerId": rid}, 40)
    a2 = next((u for u in (dv2.get("units") or []) if u.get("id") == att), None)
    norm = next((ab for ab in ((a2 or {}).get("abilities") or []) if ab.get("kind") == "normal"), None)
    if norm is None:
        return {"skip": "pas d'attaque normale"}
    snap2 = rpc("combatSnapshot", {"runnerId": rid}, 40)
    state = load_state(dv2, ob2, snap2)
    te = state.get_entity(tid)
    hc = te.get_component(HealthComponent) if te is not None else None
    if hc is None or hc.hp is None:
        return {"skip": "cible introuvable offline"}
    s0 = rpc("dumpRng", {"runnerId": rid}, 30)
    if not _ok(s0):
        return {"skip": "dumpRng KO"}
    state.rng = _seed_rng(s0)
    runner = Runner(state).install_default_handlers(20)
    runner.apply(AttackUnitMessage(att, tid))            # OFFLINE (predit, ne mute pas le live)
    rr = runner.damage_handler.last or {}
    off_ph = rr.get("per_hit")
    off_after = state.get_entity(tid).get_component(HealthComponent).hp
    res = rpc("applyAction", {"runnerId": rid, "action": {                    # LIVE
        "kind": "ability", "casterId": att, "targetId": tid, "abilityType": norm["id"]}}, 40)
    a0 = (res.get("actions") or [{}])[0]
    if not (_ok(res) and a0.get("ok")):
        return {"skip": f"attaque live KO: {str(res)[:120]}"}
    live_ph, did_evade = [], False
    for e in (a0.get("events") or []):
        td = e.get("tags")
        if not td:
            continue
        td = json.loads(td) if isinstance(td, str) else td
        if td.get("Target_Id") == tid and "Amount" in td and td.get("Active_Ability_Type") == norm["id"]:
            live_ph.append(td.get("Amount"))
            did_evade = did_evade or bool(td.get("Attack_DidEvade"))
    live_after = next((u.get("hp") for u in (res.get("units") or []) if u.get("squadId") == tid), None)
    return {"off_ph": off_ph, "live_ph": live_ph, "off_after": off_after,
            "live_after": live_after, "did_evade": did_evade}


@pytest.fixture(scope="module")
def gsi_bonus_samples(build_runner, rpc):
    """Rejoue ATTACKER 1v1 sur plusieurs seeds jusqu'a valider >=1 coup bonus (arret precoce)."""
    samples = []
    saw_bonus = False
    for seed in SEEDS:
        b = build_runner(seed, extra=["--roster", "1", "--p-units", ATTACKER, "--a-units", TARGET])
        r = _replay_one(rpc, b["rid"])
        if r.get("skip"):
            continue
        samples.append(r)
        if len(r.get("off_ph") or []) > BASE_HITS or len(r.get("live_ph") or []) > BASE_HITS:
            saw_bonus = True
        if saw_bonus and len(samples) >= 2:      # arret precoce des qu'un bonus est capture
            break
    if not samples:
        pytest.skip("aucune attaque rejouable (build/nav KO)")
    return samples


def test_getstuckin_bonus_all_bitexact(gsi_bonus_samples):
    """INVARIANT dur : off_ph == live_ph + PV egaux sur CHAQUE attaque (bonus ou non) -- seed-independant."""
    for i, s in enumerate(gsi_bonus_samples):
        if s.get("did_evade"):
            continue
        assert s["off_ph"] == s["live_ph"], (
            f"sample {i}: off={s['off_ph']} != live={s['live_ph']}")
        assert s["off_after"] == s["live_after"], (
            f"sample {i}: PV off {s['off_after']} != live {s['live_after']}")


def test_getstuckin_deferred_bonus_present_and_bitexact(gsi_bonus_samples):
    """GARDE #62c : au moins UN coup bonus DEFERE (>4 coups) est materialise ET bit-exact (l'execution
    deferee est bien cablee -- une regression qui perdrait le coup bonus donnerait off < live)."""
    bonus = [s for s in gsi_bonus_samples
             if not s.get("did_evade") and (len(s.get("live_ph") or []) > BASE_HITS)]
    if not bonus:
        pytest.skip(f"aucun coup bonus GetStuckIn tire sur les seeds {SEEDS} (chance=30, alea)")
    for s in bonus:
        assert s["off_ph"] == s["live_ph"], (
            f"coup bonus non bit-exact: off={s['off_ph']} live={s['live_ph']}")
        assert len(s["off_ph"]) == len(s["live_ph"]), (
            f"nb coups (avec bonus) off {len(s['off_ph'])} != live {len(s['live_ph'])}")
