"""#65 NoBlocking (profil de degat) — le BLOCK est BYPASSE pour un profil `NoBlocking` (ex. `Psychic`).

Racine : `AttackDamageOperation.ExecuteHit @180e5eff0` teste `DamageProfile.HasTrait(0=NoBlocking)` et pose
un flag (metadata +0x2a) qui SKIP toute la branche block/evade de `CalculateDamageOperation @18102dc30`
(`if ((metadata>>0x30)==0) { ...block/evade... }`). L'offline ignorait ce trait -> il roulait un block
SPURIOUS sur les attaques Psychic (ex. seed 123 : astraPrimarisPsy Psychic -> genesKelermorph BeastSlayer,
off 1569 vs live 2873). Le fix gate `AttackDamageOperation._block_sources(..., damage_profile)` : profil
NoBlocking -> aucune source -> 0 tirage block.

Test LIVE-agreement DETERMINISTE (independant version/seed) : astraPrimarisPsy (arme Psychic = NoBlocking)
attaque orksNob (trait BeastSlayer -> source de block chance 10 / 100% FixedArmor). Sans le fix, l'offline
aurait une source de block et pourrait la rouler ; AVEC le fix, `execute()` renvoie did_block=False et le
per-hit == live AU COUP PRES (RNG seede via dumpRng). On verifie AUSSI que la source de block EXISTE quand
on ignore le profil (sinon le test ne discrimine rien), et disparait quand on passe le profil Psychic.
ASCII-only."""
from __future__ import annotations

import json
from collections import deque

import pytest

from engine.runner.snapshot import load_state
from engine.runner.runner import Runner
from engine.runner.messages import AttackUnitMessage
from engine.runner.prng import IntBasedMersenneTwister
from engine.runner.components import HealthComponent, StatsComponent
from engine.runner.operations.damage import AttackDamageOperation
from engine.entities.pathfinding.board import Board
from engine.entities.stats import StatType

ATTACKER = "astraPrimarisPsy"    # arme normale Psychic (Traits=['NoBlocking']) melee ET range
TARGET = "orksNob"               # BeastSlayer -> source de block (chance 10 / 100% FixedArmor)


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


@pytest.fixture(scope="session")
def nb_case(live_session, rpc, build_runner):
    b = build_runner("777", extra=["--roster", "1", "--p-units", ATTACKER, "--a-units", TARGET])
    rid, my_player = b["rid"], None
    if not _ok(rpc("dumpRng", {"runnerId": rid}, 30)):
        pytest.skip("dumpRng indispo")
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    if not (isinstance(bg, dict) and "tiles" in bg):
        pytest.skip("boardGraph indispo")
    board = Board(bg["tiles"], adjacency="native_sym")

    def utile(u):
        p = u.get("pos") or {}
        return board.id_at(p.get("col"), p.get("row")) if "col" in p else None

    for _turn in range(20):
        dec = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
        if not _ok(dec):
            pytest.skip("decisionView KO")
        units = dec.get("units") or []
        champ = next((u for u in units if u.get("visualId") == ATTACKER and u.get("alive")), None)
        tgt = next((u for u in units if u.get("visualId") == TARGET and u.get("alive")), None)
        if champ is None or tgt is None:
            pytest.skip("unite manquante (build 1v1 KO)")
        if my_player is None:
            my_player = champ.get("owner")
        if dec.get("currentPlayer") != my_player:
            rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 40)
            continue
        ctile, ttile = utile(champ), utile(tgt)
        dist = _bfs(board, ttile)
        # Psychic = arme a portee (range 2) : on attaque des qu'on est a portee (dist<=2 sur le graphe).
        if dist.get(ctile, 99) <= 2:
            return _replay(rpc, rid, tgt, champ, None, board)
        mt = rpc("aiMovableTiles", {"runnerId": rid, "side": "friendly"}, 60)
        cmt = next((x for x in (mt.get("units") or []) if x.get("unitId") == champ["id"]), None)
        reach = {board.id_at(t["col"], t["row"]): (t["col"], t["row"])
                 for t in ((cmt or {}).get("tiles") or [])}
        near = [(tid, cr) for tid, cr in reach.items() if dist.get(tid, 99) <= 2]
        if near:
            _tid, (col, row) = min(near, key=lambda kv: dist[kv[0]])
            return _replay(rpc, rid, tgt, champ, (col, row), board)
        pool = [tid for tid in reach if tid in dist]
        if not pool:
            rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 40); continue
        best = min(pool, key=lambda t: dist[t]); col, row = reach[best]
        rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "move", "unitId": champ["id"], "to": {"col": col, "row": row}}}, 40)
        rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 40)
    pytest.skip(f"{ATTACKER} n'a pas atteint la portee de {TARGET} en 20 tours")


def _replay(rpc, rid, tgt, champ, move_to, board):
    att, tid = champ["id"], tgt["id"]
    if move_to is not None:
        rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "move", "unitId": att, "to": {"col": move_to[0], "row": move_to[1]}}}, 40)
    dv2 = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    ob2 = rpc("observeBattle", {"runnerId": rid}, 40)
    a2 = next((u for u in (dv2.get("units") or []) if u.get("id") == att), None)
    norm = next((ab for ab in ((a2 or {}).get("abilities") or []) if ab.get("kind") == "normal"), None)
    if norm is None:
        pytest.skip("pas d'attaque normale")
    snap2 = rpc("combatSnapshot", {"runnerId": rid}, 40)
    state = load_state(dv2, ob2, snap2); state.board = board
    te = state.get_entity(tid)
    hc = te.get_component(HealthComponent) if te is not None else None
    if hc is None or hc.hp is None:
        pytest.skip("cible introuvable offline")
    tsc = te.get_component(StatsComponent)
    active = state.effects.active_effects(tid, {"hp": hc.hp}) if state.effects is not None else []
    armor = tsc.ctx.stat(StatType.FIXED_ARMOR) if tsc is not None else 0
    # source de block SANS gate profil (doit exister -> le test discrimine bien le bypass)
    bsrc_nogate = AttackDamageOperation._block_sources(tsc, active, armor)
    # source de block AVEC profil Psychic (doit etre None -> bypass NoBlocking)
    bsrc_psychic = AttackDamageOperation._block_sources(tsc, active, armor, "Psychic")
    hp_before = hc.hp
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
    runner.apply(AttackUnitMessage(att, tid))
    rr = runner.damage_handler.last
    off_after = state.get_entity(tid).get_component(HealthComponent).hp
    return {"hp_before": hp_before, "live_after": live_after, "off_after": off_after,
            "live_ph": live_ph, "off_ph": (rr or {}).get("per_hit"), "armor": armor,
            "bsrc_nogate": bsrc_nogate, "bsrc_psychic": bsrc_psychic,
            "off_block": (rr or {}).get("did_block"), "did_evade": did_evade, "rr": rr,
            "profile": (rr or {}).get("profile"),
            "has_bs_effect": any(getattr(ef, "name", None) == "BeastSlayer_ExtraBlock" for ef in active)}


def test_noblocking_source_gated(nb_case):
    """DETERMINISTE : la source de block d'orksNob EXISTE sans gate profil, et DISPARAIT sous profil
    Psychic (NoBlocking). Sans cette dualite, le test ne discriminerait pas le bypass."""
    c = nb_case
    if not c["has_bs_effect"]:
        pytest.skip("BeastSlayer_ExtraBlock non seede sur orksNob (capture effets)")
    assert c["bsrc_nogate"], (
        f"pre-condition : source de block attendue sans gate profil, obtenu {c['bsrc_nogate']}")
    assert c["bsrc_psychic"] is None, (
        f"profil Psychic (NoBlocking) doit BYPASSER le block -> _block_sources None, obtenu {c['bsrc_psychic']}")


def test_noblocking_replay_bit_exact(nb_case):
    """COEUR #65 : attaque Psychic (NoBlocking) contre orksNob (source de block presente) -> l'offline NE
    bloque PAS (did_block False) et le per-hit == live AU COUP PRES (0 tirage block spurious)."""
    c = nb_case
    assert c["rr"] is not None, "runner offline n'a rien calcule"
    assert c["profile"] == "Psychic", f"profil attendu Psychic (NoBlocking), obtenu {c['profile']}"
    if c["did_evade"]:
        pytest.skip("coup avec evade live (hors slice)")
    print(f"\n[NoBlocking replay] profile={c['profile']} live per-hit={c['live_ph']} off per-hit={c['off_ph']} "
          f"off_block={c['off_block']} bsrc_nogate={c['bsrc_nogate']} live_after={c['live_after']} "
          f"off_after={c['off_after']}")
    assert c["off_block"] is False, (
        f"profil NoBlocking : l'offline ne doit PAS bloquer, did_block={c['off_block']}")
    assert c["off_ph"] == c["live_ph"], (
        f"per-hit offline != live : off={c['off_ph']} live={c['live_ph']} (block spurious non bypasse ?)")
    assert c["off_after"] == c["live_after"], (
        f"PV cible offline {c['off_after']} != live {c['live_after']}")
