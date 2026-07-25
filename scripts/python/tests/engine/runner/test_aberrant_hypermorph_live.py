"""VALIDATION LIVE du port COMBAT de AberrantHypermorph (1166, genesBiophagus/Hollan) -- case-220 P0-SUMMON.

Artefact natif : `IdunBattleLogic.Entities.Abilities.Active.Loki.AberrantHypermorphAbility$$ExecuteBehaviour` (mirror 1:1) :
    Execute( Spawn(caster@0x160, Target@0x178=TUILE, "genesSmnAberrant",
                   WithStatsFromConfig(config, AbilityLevelAmount(Self@0x148, 1166))
                     .onAppearance = PerformAIAttackFromCurrentPosition(Target@0x178)) )
UN seul noeud Spawn (PAS d'AddEffect, PAS d'ExecuteAtomic) -- le summon le plus simple. Cast TILE-target
(hex libre adjacent au caster ; IdunBattleLogic.Entities.Abilities.Active.Loki.AberrantHypermorphAbility$$.ctor = TargetingOptions(0, statsFromClass, 1, 0x1040) IDENTIQUE
a MasterOfTheTutelaries IdunBattleLogic.Entities.Abilities.Active.Loki.MasterOfTheTutelariesAbility$$ExecuteBehaviour).

DEUX faces confrontees au live (board/stats REELS via load_state) :
  - EXECUTE (port offline via le handler) : spawn UN genesSmnAberrant sur l'EQUIPE DU CASTER, sur la tuile
    ciblee, stats summonHp/summonDmg[level actif du caster] x mult, puis attaque a l'apparition l'ennemi
    adjacent (PerformAIAttackFromCurrentPosition -> arme melee 1-hit Physical du summon).
  - LIVE : le MEME cast tile-target (applyAction) dans le runner natif spawn le meme summon (equipe/tuile/
    hpMax == summonHp[level] du port) + inflige du degat a l'ennemi adjacent.

Geometrie DRIVEE (mem. drive-positions) : l'ennemi est place ADJACENT a la tuile de spawn (summon melee r1).
Le degat EXACT de l'attaque a l'apparition est un RAFFINEMENT non asserte (RNG + passive Hypermorph du
summon non portee = buff attaque hors ExecuteBehaviour de 1166) ; on valide COUNTS/EQUIPE/TUILE/hpMax +
attaque-a-eu-lieu.
"""
from __future__ import annotations

import pytest

from engine.runner.snapshot import load_state
from engine.runner.prng import IntBasedMersenneTwister
from engine.runner.components import (OwnerComponent, PositionComponent, HealthComponent,
                                      UnitComponent, StatsComponent)

ABERRANT = 1166
SUMMON_VID = "genesSmnAberrant"
CARRIER = "genesBiophagus"
ENEMY = "ultraTitus"


def _seed_rng(s):
    rng = IntBasedMersenneTwister()
    rng.mt = list(s["mt"]); rng.mti = s["mti"]
    return rng


def _tile_of(board, state, uid):
    pc = state.get_entity(uid).get_component(PositionComponent)
    return board.id_at(pc.col, pc.row) if pc is not None else None


def _build(build_runner):
    return build_runner("4242", extra=["--p-units", CARRIER, "--a-units", ENEMY])["rid"]


def _load(rpc, rid):
    from engine.entities.pathfinding.board import Board
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    if not (isinstance(bg, dict) and bg.get("tiles")):
        pytest.skip("boardGraph indispo")
    board = Board(bg["tiles"], adjacency="evenq")
    dec = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    ob = rpc("observeBattle", {"runnerId": rid}, 40)
    snap = rpc("combatSnapshot", {"runnerId": rid}, 60)
    s0 = rpc("dumpRng", {"runnerId": rid}, 30)
    state = load_state(dec, ob, snap, board=board)
    if isinstance(s0, dict) and s0.get("mt"):
        state.rng = _seed_rng(s0)
    return state, board


def _find(state, visual_id):
    for eid, e in state.entities.items():
        uc = e.get_component(UnitComponent)
        if uc is not None and uc.visual_id == visual_id and uc.alive:
            return eid
    return None


def _occupied(state, board):
    return {_tile_of(board, state, u) for u in list(state.entities)
            if state.get_entity(u).get_component(PositionComponent) is not None}


def _pick_free_adjacent(state, board, caster):
    """(spawn_tile, enemy_pos_tile) : une tuile LIBRE adjacente au caster (mirror des `now[..]` de la
    decisionView) + une position LIBRE adjacente a CETTE tuile ou driver l'ennemi. None sinon."""
    ctile = _tile_of(board, state, caster)
    occ = _occupied(state, board)
    for st in board.neighbours(ctile):
        info = board.by_id.get(st)
        if info is None or st in occ or not board.walkable(st):
            continue
        for nb in board.neighbours(st):
            ninfo = board.by_id.get(nb)
            if ninfo is None or nb == ctile or not board.walkable(nb) or nb in occ:
                continue
            return st, nb
    return None


def _expected_summon_stats(state, caster):
    from engine.entities.effects.magnitude import ability_var
    ctx = state.get_entity(caster).get_component(StatsComponent).ctx
    lvl = ctx.active_ability_level
    mult = ctx.ability_variables_multiplier
    hp = int(ability_var("AberrantHypermorph", "summonHp", lvl, multiplier_pct=mult) or 0)
    dmg = int(ability_var("AberrantHypermorph", "summonDmg", lvl, multiplier_pct=mult) or 0)
    return lvl, mult, hp, dmg


# ------------------------------------------------------------------ FACE 1 : PORT (offline, driven)

def test_aberrant_spawn_onappearance_port(rpc, build_runner):
    """PORT (execute) : spawn genesSmnAberrant EQUIPE-DU-CASTER sur la tuile ciblee, hp=summonHp[level],
    atk=summonDmg[level], puis attaque a l'apparition l'ennemi adjacent (drive-positions)."""
    from engine.runner.operations.summon_ai import _apply_active_ability
    from engine.entities.stats import StatType
    rid = _build(build_runner)
    state, board = _load(rpc, rid)
    caster = _find(state, CARRIER)
    enemy = _find(state, ENEMY)
    if caster is None or enemy is None:
        pytest.skip(f"caster/enemy absents: caster={caster} enemy={enemy}")
    picked = _pick_free_adjacent(state, board, caster)
    if picked is None:
        pytest.skip("pas de tuile libre adjacente drivable")
    spawn_tile, enemy_pos = picked
    einfo = board.by_id[enemy_pos]
    epc = state.get_entity(enemy).get_component(PositionComponent)
    epc.col, epc.row = einfo["col"], einfo["row"]        # DRIVE : ennemi adjacent a la tuile de spawn

    cteam = state.get_entity(caster).get_component(OwnerComponent).team
    lvl, mult, exp_hp, exp_dmg = _expected_summon_stats(state, caster)
    before = set(state.entities)

    res = _apply_active_ability(state, caster, spawn_tile, ABERRANT)
    diag = (res or {}).get("diag") or {}
    spawned = diag.get("spawned") or []
    attacks = diag.get("attacks") or []
    print(f"\n[ABERRANT/port] routed={res.get('routed')} level={lvl} mult={mult} "
          f"exp_hp={exp_hp} exp_dmg={exp_dmg} spawned={spawned} attacks={attacks} tile={diag.get('tile')}")

    assert res.get("routed") == "handler" and diag.get("ported") is True, f"1166 non porte: {res}"
    assert len(spawned) == 1, f"count summon != 1: {spawned}"
    sid = spawned[0]
    assert sid in (set(state.entities) - before), "le summon n'a pas ete ajoute a l'etat"
    suc = state.get_entity(sid)
    assert suc.get_component(OwnerComponent).team == cteam, "summon pas sur l'equipe du caster"
    assert suc.get_component(UnitComponent).visual_id == SUMMON_VID, "mauvais visual_id summon"
    assert _tile_of(board, state, sid) == spawn_tile, "summon pas sur la tuile ciblee"
    assert suc.get_component(HealthComponent).hp_max == exp_hp, \
        f"hp_max {suc.get_component(HealthComponent).hp_max} != summonHp[{lvl}]x{mult}={exp_hp}"
    got_atk = int(suc.get_component(StatsComponent).ctx.stat(StatType.ATTACK))
    assert got_atk == exp_dmg, f"atk {got_atk} != summonDmg[{lvl}]x{mult}={exp_dmg}"
    assert len(attacks) == 1, f"attaque a l'apparition absente/multiple: {attacks}"
    at = attacks[0]
    assert at["summon"] == sid and at["target"] == enemy, f"attaquant/cible KO: {at} (enemy={enemy})"
    assert at["total"] and at["total"] > 0, f"degat a l'apparition nul: {at}"


# ------------------------------------------------------------------ FACE 2 : LIVE (spawn confront)

def _live_units(rpc, rid):
    return (rpc("observeBattle", {"runnerId": rid}, 40) or {}).get("units") or []


def test_aberrant_live_spawn_confront(rpc, build_runner):
    """LIVE : cast tile-target sur une tuile libre adjacente au caster -> le runner natif spawn UN
    genesSmnAberrant sur l'EQUIPE DU CASTER, hpMax == summonHp[level] du port (WithStatsFromConfig)."""
    rid = _build(build_runner)
    state, board = _load(rpc, rid)
    caster = _find(state, CARRIER)
    if caster is None:
        pytest.skip("caster absent")
    cteam = state.get_entity(caster).get_component(OwnerComponent).team
    lvl, mult, exp_hp, _exp_dmg = _expected_summon_stats(state, caster)
    ctile = _tile_of(board, state, caster)
    occ = _occupied(state, board)
    spawn = next((t for t in board.neighbours(ctile)
                  if t not in occ and board.walkable(t) and t in board.by_id), None)
    if spawn is None:
        pytest.skip("pas de tuile libre adjacente au caster")
    info = board.by_id[spawn]

    before = {u["squadId"] for u in _live_units(rpc, rid) if u.get("visualId") == SUMMON_VID}
    rpc("applyAction", {"runnerId": rid, "action": {
        "kind": "ability", "casterId": caster, "abilityType": ABERRANT,
        "to": {"col": info["col"], "row": info["row"]}}}, 60)
    summons = [u for u in _live_units(rpc, rid)
               if u.get("visualId") == SUMMON_VID and u["squadId"] not in before and not u.get("isDead")]
    print(f"\n[ABERRANT/live-spawn] level={lvl} exp_hp={exp_hp} cteam={cteam} spawn_tile={info} "
          f"summons={[(u['squadId'], u.get('teamId'), u.get('hpMax'), u.get('col'), u.get('row')) for u in summons]}")

    assert summons, "aucun genesSmnAberrant spawne live"
    su = summons[0]
    assert su.get("teamId") == cteam, f"summon live team {su.get('teamId')} != caster {cteam}"
    assert (su.get("col"), su.get("row")) == (info["col"], info["row"]), "summon pas sur la tuile ciblee"
    assert su.get("hpMax") == exp_hp, \
        f"hpMax live {su.get('hpMax')} != summonHp[{lvl}]x{mult}={exp_hp} (port WithStatsFromConfig)"


# ------------------------------------------------------------------ FACE 2bis : LIVE (attaque a l'apparition)

def test_aberrant_live_onappearance_attack(rpc, build_runner):
    """LIVE : caster + ennemi DRIVES adjacents (aiMovableTiles greedy), cast sur une tuile adjacente aux
    DEUX -> le summon attaque a l'apparition (l'ennemi perd des HP). Best-effort : skip si pas d'adjacence."""
    import hexgeo
    rid = _build(build_runner)
    _state, board = _load(rpc, rid)

    def live_pos():
        dec = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
        cp = dec.get("currentPlayer")
        by = {u["visualId"]: u for u in dec.get("units", []) if u.get("alive")}
        return cp, by

    cp, by = live_pos()
    if CARRIER not in by or ENEMY not in by:
        pytest.skip("caster/enemy absents live")
    cid, eid = by[CARRIER]["id"], by[ENEMY]["id"]
    cowner = by[CARRIER]["owner"]

    def P(u):
        p = u["pos"]; return (p["col"], p["row"])

    for _ in range(10):
        cp, by = live_pos()
        if CARRIER not in by or ENEMY not in by:
            pytest.skip("unite disparue")
        c, e = P(by[CARRIER]), P(by[ENEMY])
        if hexgeo.distance(c, e) <= 2:
            break
        mov = rpc("aiMovableTiles", {"runnerId": rid}, 60) or {}
        for mu in mov.get("units", []):
            uid = mu.get("unitId")
            goal = e if uid == cid else (c if uid == eid else None)
            if goal is None:
                continue
            src = (mu.get("pos") or {}).get("col"), (mu.get("pos") or {}).get("row")
            tiles = [(t["col"], t["row"]) for t in (mu.get("tiles") or []) if t.get("col") is not None]
            if not tiles:
                continue
            best = min(tiles, key=lambda t: hexgeo.distance(t, goal))
            if hexgeo.distance(best, goal) < hexgeo.distance(src, goal):
                rpc("applyAction", {"runnerId": rid, "action": {
                    "kind": "move", "unitId": uid, "to": {"col": best[0], "row": best[1]}}}, 40)
        rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 40)

    cp, by = live_pos()
    c, e = P(by[CARRIER]), P(by[ENEMY])
    ctile, etile = board.id_at(*c), board.id_at(*e)
    occ = {board.id_at(*P(u)) for u in by.values()}
    spawn = next((t for t in board.neighbours(ctile)
                  if t not in occ and board.walkable(t) and etile in board.neighbours(t)), None)
    if spawn is None:
        pytest.skip(f"pas de tuile libre adjacente au caster ET a l'ennemi (dist={hexgeo.distance(c, e)})")
    # tour du caster
    for _ in range(4):
        cp, by = live_pos()
        if cp == cowner:
            break
        rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 40)
    info = board.by_id[spawn]
    hp0 = next((u["hp"] for u in _live_units(rpc, rid) if u["squadId"] == eid), None)
    rpc("applyAction", {"runnerId": rid, "action": {
        "kind": "ability", "casterId": cid, "abilityType": ABERRANT,
        "to": {"col": info["col"], "row": info["row"]}}}, 60)
    ob1 = _live_units(rpc, rid)
    summons = [u for u in ob1 if u.get("visualId") == SUMMON_VID and not u.get("isDead")]
    hp1 = next((u["hp"] for u in ob1 if u["squadId"] == eid), None)
    print(f"\n[ABERRANT/live-attack] spawn_tile={info} summons={len(summons)} enemy hp {hp0}->{hp1}")
    assert summons, "aucun summon spawne"
    assert hp0 is not None and hp1 is not None and hp1 < hp0, \
        f"l'ennemi n'a pas pris de degat a l'apparition ({hp0}->{hp1})"


# ------------------------------------------------------------------ Degenere

def test_aberrant_noop_on_non_tile(rpc, build_runner):
    """target_id non-tuile du board -> Spawn no-op (spawned=[]) sans erreur (pas d'AddEffect a executer)."""
    from engine.runner.operations.summon_ai import _apply_active_ability
    rid = _build(build_runner)
    state, board = _load(rpc, rid)
    caster = _find(state, CARRIER)
    if caster is None:
        pytest.skip("caster absent")
    bogus = max(board.by_id) + 999999
    res = _apply_active_ability(state, caster, bogus, ABERRANT)
    diag = (res or {}).get("diag") or {}
    assert res.get("routed") == "handler" and diag.get("ported") is True, res
    assert (diag.get("spawned") or []) == [], f"spawn sur une non-tuile: {diag}"
