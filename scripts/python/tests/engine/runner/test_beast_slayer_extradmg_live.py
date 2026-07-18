"""#14 (gen-stealer G7) BeastSlayer_ExtraDmg (ATTAQUE) -- FACE POSITIVE live.

Trait BeastSlayer -> effet capte `BeastSlayer_ExtraDmg` = `+beastSlayerExtraDmgPct% de degat MELEE vs
Big Targets / Vehicles` (`BeastSlayer_ExtraDmgEffect.CreateDamageModifier @180f336c0` :
`ForPercentIncrease(0xf=extraDmgPct)` gate `OwnerIsCaster & IsMeleeAttack & (HasTrait(target,BigTarget)
| HasTrait(target,Vehicle))`).

La face DEFENSE (block) est deja live-validee (test_beast_slayer_block_live, orksNob). La face
EXTRA-DMG n'etait couverte qu'en NEGATIF (test_getstuckin_combat_live : orksNob attaque bloodIntercessor
non-Big/Vehicle -> BeastSlayer_ExtraDmg=0). Ce fichier ferme le trou en POSITIF, en deux volets :

 1. DETERMINISTE sur JUDH (genesKelermorph, le porteur genestealer de la tache) : l'effet
    `BeastSlayer_ExtraDmg` capte sur Judh rend `create_effect_damage_bonus_for_attack(is_ranged=False,
    target_traits={Vehicle}) = PercentIncrease beastSlayerExtraDmgPct`, RIEN en RANGED (gate IsMeleeAttack)
    ni vs cible non-Big/Vehicle (gate HasTrait cible). PUR OFFLINE (T0, aucun move) -> aucune interaction
    avec le kit decoy-on-move de Judh (HypersensoryAbilities). Prouve le port du gate + magnitude.
 2. REPLAY-DIFF sur ORKSNOB (BeastSlayer, melee propre, deja navigue dans test_getstuckin) attaquant un
    VEHICLE (admecDestroyer) : per-hit offline == live AU COUP PRES. Meme scenario que test_getstuckin
    mais cible Big/Vehicle -> le +20% BeastSlayer est ENGAGE ; off_ph==live_ph prouve qu'il est applique
    live a l'identique (sans le port, off_ph sous-estimerait de 20%). Complement POSITIF du cas ZERO.

Lit l'etat LIVE (rien de hardcode ; pct lu via trait_var gameconfig). ASCII-only.
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
from engine.runner.damage_model import target_trait_names
from engine.runner.operations.damage import AttackDamageOperation
from engine.entities.pathfinding.board import Board
from engine.entities.stats import StatType
from engine.entities.effects.magnitude import trait_var

BS_DMG_EFFECT = "BeastSlayer_ExtraDmg"
JUDH = "genesKelermorph"          # porteur genestealer de la tache (Ambush+BeastSlayer)
ORKSNOB = "orksNob"               # BeastSlayer, melee 3hmp50 propre (deja navigue dans test_getstuckin)
VEHICLE_TARGET = "admecDestroyer"  # trait Vehicle, defenseur sans block -> gate + replay propres


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


def _bs_effect_of(state, unit_id):
    """L'objet effet `BeastSlayer_ExtraDmg` actif capte sur `unit_id` (None si non seede)."""
    e = state.get_entity(unit_id)
    hc = e.get_component(HealthComponent) if e is not None else None
    active = (state.effects.active_effects(unit_id, {"hp": hc.hp if hc else None})
              if state.effects is not None else [])
    return next((ef for ef in active if getattr(ef, "name", None) == BS_DMG_EFFECT), None)


# ----------------------------------------------------------------------------------------------------
# Volet 1 : DETERMINISTE sur Judh (aucun move -> pas d'interaction decoy).
# ----------------------------------------------------------------------------------------------------
@pytest.fixture(scope="session")
def judh_bs(live_session, rpc, build_runner):
    b = build_runner("777", extra=["--roster", "1", "--p-units", JUDH, "--a-units", VEHICLE_TARGET])
    rid = b["rid"]
    dv = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    ob = rpc("observeBattle", {"runnerId": rid}, 40)
    snap = rpc("combatSnapshot", {"runnerId": rid}, 40)
    if not (_ok(dv) and isinstance(ob, dict) and isinstance(snap, dict)):
        pytest.skip("RPC etat initial KO")
    judh = next((u for u in (dv.get("units") or []) if u.get("visualId") == JUDH), None)
    veh = next((u for u in (dv.get("units") or []) if u.get("visualId") == VEHICLE_TARGET), None)
    if judh is None or veh is None:
        pytest.skip("build Judh vs Vehicle KO")
    state = load_state(dv, ob, snap)
    jid = judh["id"]
    bs = _bs_effect_of(state, jid)
    veh_traits = target_trait_names(state, veh["id"])
    b_vehicle = b_ranged = b_nonbig = "NO_EFFECT"
    if bs is not None:
        b_vehicle = bs.create_effect_damage_bonus_for_attack(
            is_ranged=False, target_traits=frozenset({"Vehicle"}))
        b_ranged = bs.create_effect_damage_bonus_for_attack(
            is_ranged=True, target_traits=frozenset({"Vehicle"}))
        b_nonbig = bs.create_effect_damage_bonus_for_attack(
            is_ranged=False, target_traits=frozenset({"Infantry"}))
    # FACE BLOCK (defense) sur Judh : capte-t-il AUSSI BeastSlayer_ExtraBlock -> source de block
    # (chance beastSlayerBlockChance / amount = beastSlayerBlockAsMaxArmorPct% du FixedArmor courant) ?
    je = state.get_entity(jid)
    jhc = je.get_component(HealthComponent) if je is not None else None
    jsc = je.get_component(StatsComponent) if je is not None else None
    jactive = (state.effects.active_effects(jid, {"hp": jhc.hp if jhc else None})
               if state.effects is not None else [])
    jarmor = jsc.ctx.stat(StatType.FIXED_ARMOR) if jsc is not None else 0
    jblock = AttackDamageOperation._block_sources(jsc, jactive, jarmor) or []
    has_bs_block = any(getattr(ef, "name", None) == "BeastSlayer_ExtraBlock" for ef in jactive)
    block_chance = trait_var("BeastSlayer", "beastSlayerBlockChance")
    block_pct = trait_var("BeastSlayer", "beastSlayerBlockAsMaxArmorPct")
    exp_amount = int(int(jarmor) * int(block_pct) / 100) if block_pct is not None else None
    return {"has_bs": bs is not None, "veh_traits": veh_traits,
            "expected_pct": trait_var("BeastSlayer", "beastSlayerExtraDmgPct"),
            "b_vehicle": b_vehicle, "b_ranged": b_ranged, "b_nonbig": b_nonbig,
            "has_bs_block": has_bs_block, "armor": jarmor, "block_sources": jblock,
            "block_chance": block_chance, "exp_block_amount": exp_amount}


def test_judh_beast_slayer_extradmg_effect(judh_bs):
    """Judh capte BeastSlayer_ExtraDmg -> +extraDmgPct% MELEE vs Big/Vehicle, RIEN en ranged ou vs
    cible non-Big/Vehicle. La cible admecDestroyer porte bien le trait Vehicle offline."""
    c = judh_bs
    assert "Vehicle" in c["veh_traits"], \
        f"{VEHICLE_TARGET} n'a pas le trait Vehicle offline (traits={sorted(c['veh_traits'])})"
    if not c["has_bs"]:
        pytest.skip(f"{BS_DMG_EFFECT} non seede sur {JUDH} (capture effets)")
    pct = c["expected_pct"]
    assert pct, f"beastSlayerExtraDmgPct absent du gameconfig (={pct})"
    bv = c["b_vehicle"]
    assert getattr(bv, "kind", None) == "PercentIncrease" and getattr(bv, "value", None) == pct, (
        f"bonus MELEE vs Vehicle attendu PercentIncrease {pct}, obtenu {bv}")
    assert c["b_ranged"] is None, f"gate IsMeleeAttack casse : bonus RANGED non-None ({c['b_ranged']})"
    assert c["b_nonbig"] is None, f"gate HasTrait(cible) casse : bonus vs non-Big non-None ({c['b_nonbig']})"


def test_judh_beast_slayer_block_source(judh_bs):
    """FACE BLOCK sur Judh (le porteur de la tache) : il capte aussi BeastSlayer_ExtraBlock -> une source
    de block supplementaire (chance beastSlayerBlockChance / amount = blockAsMaxArmorPct% du FixedArmor).
    Meme mecanique que test_beast_slayer_block_live (orksNob), ici cote Judh, DETERMINISTE (pas de RNG)."""
    c = judh_bs
    if not c["has_bs_block"]:
        pytest.skip(f"BeastSlayer_ExtraBlock non seede sur {JUDH} (capture effets)")
    assert c["block_chance"], f"beastSlayerBlockChance absent du gameconfig (={c['block_chance']})"
    srcs = c["block_sources"] or []
    bs = [s for s in srcs
          if getattr(s, "chance", None) == c["block_chance"] and getattr(s, "amount", None) == c["exp_block_amount"]]
    assert bs, (f"source block BeastSlayer absente de block_sources={srcs} "
                f"(attendu chance={c['block_chance']}, amount={c['exp_block_amount']} "
                f"= {c['block_chance']}%/armor={c['armor']})")


# ----------------------------------------------------------------------------------------------------
# Volet 2 : REPLAY-DIFF end-to-end sur orksNob attaquant un Vehicle (+20% ENGAGE).
# ----------------------------------------------------------------------------------------------------
@pytest.fixture(scope="session")
def orks_replay(live_session, rpc, build_runner):
    b = build_runner("777", extra=["--roster", "1", "--p-units", ORKSNOB, "--a-units", VEHICLE_TARGET])
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
        champ = next((u for u in units if u.get("visualId") == ORKSNOB and u.get("alive")), None)
        tgt = next((u for u in units if u.get("visualId") == VEHICLE_TARGET and u.get("alive")), None)
        if champ is None or tgt is None:
            pytest.skip("unite manquante (build 1v1 KO)")
        if my_player is None:
            my_player = champ.get("owner")
        if dec.get("currentPlayer") != my_player:
            rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 40)
            continue
        ctile, ttile = utile(champ), utile(tgt)
        dist = _bfs(board, ttile)
        if ctile in board.neighbours(ttile):
            return _replay(rpc, rid, tgt, champ, None)
        mt = rpc("aiMovableTiles", {"runnerId": rid, "side": "friendly"}, 60)
        cmt = next((x for x in (mt.get("units") or []) if x.get("unitId") == champ["id"]), None)
        reach = {board.id_at(t["col"], t["row"]): (t["col"], t["row"])
                 for t in ((cmt or {}).get("tiles") or [])}
        adj = [(tid, cr) for tid, cr in reach.items() if tid in board.neighbours(ttile)]
        if adj:
            _tid, (col, row) = adj[0]
            return _replay(rpc, rid, tgt, champ, (col, row))
        pool = [tid for tid in reach if tid in dist]
        if not pool:
            rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 40); continue
        best = min(pool, key=lambda t: dist[t]); col, row = reach[best]
        rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "move", "unitId": champ["id"], "to": {"col": col, "row": row}}}, 40)
        rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 40)
    pytest.skip(f"{ORKSNOB} n'a pas atteint {VEHICLE_TARGET} en melee en 20 tours")


def _replay(rpc, rid, tgt, champ, move_to):
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
    state = load_state(dv2, ob2, snap2)
    te = state.get_entity(tid)
    hc = te.get_component(HealthComponent) if te is not None else None
    if hc is None or hc.hp is None:
        pytest.skip("cible introuvable offline")
    tgt_traits = target_trait_names(state, tid)
    bs = _bs_effect_of(state, att)
    b_vehicle = None
    if bs is not None:
        b_vehicle = bs.create_effect_damage_bonus_for_attack(is_ranged=False, target_traits=tgt_traits)
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
            "live_ph": live_ph, "off_ph": (rr or {}).get("per_hit"), "did_evade": did_evade,
            "rr": rr, "tgt_traits": tgt_traits, "has_bs": bs is not None, "b_vehicle": b_vehicle,
            "expected_pct": trait_var("BeastSlayer", "beastSlayerExtraDmgPct")}


def test_orksnob_beast_slayer_extradmg_engaged(orks_replay):
    """L'attaquant (BeastSlayer) attaque un VEHICLE -> son BeastSlayer_ExtraDmg est ENGAGE :
    +extraDmgPct% (sinon le replay bit-exact testerait un +20% inerte)."""
    c = orks_replay
    assert "Vehicle" in c["tgt_traits"] or "BigTarget" in c["tgt_traits"], \
        f"{VEHICLE_TARGET} n'est ni Vehicle ni BigTarget offline (traits={sorted(c['tgt_traits'])})"
    if not c["has_bs"]:
        pytest.skip(f"{BS_DMG_EFFECT} non seede sur {ORKSNOB}")
    pct = c["expected_pct"]
    bv = c["b_vehicle"]
    assert getattr(bv, "kind", None) == "PercentIncrease" and getattr(bv, "value", None) == pct, (
        f"BeastSlayer_ExtraDmg non engage vs Vehicle : attendu PercentIncrease {pct}, obtenu {bv}")


def test_beast_slayer_extradmg_replay_bit_exact(orks_replay):
    """COEUR : attaque melee contre le Vehicle rejouee RNG-seede -> per-hit offline == live AU COUP PRES
    (le +extraDmgPct% BeastSlayer applique a l'identique du natif) + PV cible egaux. Complement POSITIF
    du cas ZERO de test_getstuckin_combat_live."""
    c = orks_replay
    assert c["rr"] is not None, "runner offline n'a rien calcule"
    if c["did_evade"]:
        pytest.skip("coup avec evade live (hors slice extra-dmg)")
    print(f"\n[BS-EXTRADMG replay] live per-hit={c['live_ph']} off per-hit={c['off_ph']} "
          f"tgt_traits={sorted(c['tgt_traits'])} pct={c['expected_pct']} "
          f"live_after={c['live_after']} off_after={c['off_after']}")
    assert c["off_ph"] == c["live_ph"], (
        f"per-hit offline != live : off={c['off_ph']} live={c['live_ph']} "
        f"(+extraDmgPct% BeastSlayer non applique identiquement ?)")
    assert c["off_after"] == c["live_after"], (
        f"PV cible offline {c['off_after']} != live {c['live_after']}")
