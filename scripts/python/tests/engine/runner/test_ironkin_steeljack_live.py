"""VALIDATION du port COMBAT de IronkinSteeljack (1219, votanMemnyr/Ammuk, Leagues of Votann) -- case-220 §6.10.

Artefact natif : `IdunBattleLogic.Entities.Abilities.Active.Loki.AberrantHypermorphAbility$$ExecuteBehaviour` -- corps GSHARED DEDUPLIQUE avec
`IdunBattleLogic.Entities.Abilities.Active.Loki.AberrantHypermorphAbility$$ExecuteBehaviour` (RE : les DEUX classes pointent leur slot
ExecuteBehaviour vers le MEME code IdunBattleLogic.Entities.Abilities.Active.Loki.AberrantHypermorphAbility$$ExecuteBehaviour -- table methodPointers, cf. votann.py). Il decompile en :
    Execute( Spawn(caster@0x160, Target@0x178=TUILE, "votanSmnSteeljack",
                   WithStatsFromConfig(config, AbilityLevelAmount(Self@0x148, 1219))
                     .onAppearance = PerformAIAttackFromCurrentPosition(Target@0x178)) )
UN seul noeud Spawn (PAS d'AddEffect, PAS d'ExecuteAtomic, count=1). Cast TILE-target (hex libre adjacent au
caster ; IdunBattleLogic.Entities.Abilities.Active.Loki.IronkinSteeljackAbility$$.ctor = TargetingOptions(0, statsFromClass, 1, 0x1040) IDENTIQUE a AberrantHypermorph
IdunBattleLogic.Entities.Abilities.Active.Loki.AberrantHypermorphAbility$$.ctor). Le summon `votanSmnSteeljack` a DEUX armes (melee Physical 2-hit, ranged Energy 2-hit range-2).

SPAWNABILITE DU PORTEUR (particularite Votann) : `votanMemnyr` (Ammuk) n'est PAS dans le seed BC standard
(`data/seed-bc.json`) -> `rl_duel build --p-units votanMemnyr` echoue (hors pool). On l'INJECTE dans le
catalogue Units en memoire (buildNormalizedBC RECALCULE ses stats depuis gameconfig -- Health/Damage/
AbilityLevel reels au rank cible) : equivalent a une bataille avec Ammuk, sans toucher le fichier partage.
Le carrier spawn alors correctement comme p-unit (verifie : votanMemnyr id vivant, 1219 usable level 50).

DEUX faces :
  - FACE 1 EXECUTE (port offline via le handler, contre un ETAT REEL charge) : spawn UN votanSmnSteeljack sur
    l'EQUIPE DU CASTER, sur la tuile ciblee, stats summonHp/summonDmg[level actif=50] x mult, attaque a
    l'apparition l'ennemi adjacent (drive-positions), termine le tour du caster (no-move-this-turn). Valide
    MON code (SpawnSteeljack -> _spawn_config_grot + perform_ai_attack_from_current_position, Operations deja
    live-validees par AberrantHypermorph/MasterOfTheTutelaries).
  - FACE 2 LIVE (cast natif) : BLOQUE dans le runner HEADLESS -- le spawn natif de `votanSmnSteeljack` leve
    un `FindFirstObjectByType` (query de scene Unity absente en headless), specifique a CE summon (config
    gameconfig ; AberrantHypermorph, lui, spawn OK -> controle passe). Limitation d'ENVIRONNEMENT, orthogonale
    au port (dont le corps natif est BYTE-IDENTIQUE a AberrantHypermorph live-valide). Le test TENTE le cast :
    si un jour l'environnement le permet -> assertions ; sinon skip documente sur le blocker connu.
"""
from __future__ import annotations

import copy
import json

import pytest

from engine.runner.snapshot import load_state
from engine.runner.prng import IntBasedMersenneTwister
from engine.runner.components import (OwnerComponent, PositionComponent, HealthComponent,
                                      UnitComponent, StatsComponent)

STEELJACK = 1219
SUMMON_VID = "votanSmnSteeljack"
CARRIER = "votanMemnyr"
ENEMY = "ultraTitus"


# --- injection catalogue (case-92) : `catalog_inject` remplit les DEUX catalogues -- l'entree
#     `Units` de votanMemnyr ET les configs d'ability IronkinSteeljack/PredictiveGuidance dans
#     `BC.Abilities`. Sans la seconde, le porteur se deploie mais le cast FAUTE
#     (`AbilitiesConfiguration$$GetActive` rend une config VIDE ->
#     `AbilityConfiguration$$GetVariableForLevel` leve). Cf. docs/rl/case-92-catalog-injection.md.
def _build_votan(host, sid, rank: int = 17, seed: str = "4242", board: str = "MC1_67"):
    """Runner ISOLE avec votanMemnyr (p-unit) via BC augmente EN MEMOIRE. Renvoie rid ou None (skip)."""
    import catalog_inject as CI
    R = host
    try:
        seed_bc = R._load_seed_bc()
    except Exception as e:                                # seed BC purge (artefact per-hash)
        return None, f"seed BC absent: {e}"
    bc, _added, _ab, _marker = CI.augment(seed_bc, [CARRIER], rank=rank)
    try:
        board_dump = R._load_board_dump(board)
    except Exception as e:
        return None, f"board dump {board} absent: {e}"
    template, pool, _mow = R._normalize_and_extract_pool(sid, bc, rank, board_dump=board_dump)
    if CARRIER not in pool or ENEMY not in pool:
        return None, f"normalisation KO (carrier in pool={CARRIER in pool}, enemy in pool={ENEMY in pool})"
    out = copy.deepcopy(template)
    R._patch_predefined_units(out, [ENEMY])
    ppts = R._spawn_points_by_twpi(out).get(0) or []
    if not ppts:
        return None, "pas de spawn joueur"
    player_units = [{"unitId": CARRIER, "playerId": R.PLAYER_ID_HUMAN,
                     "col": int(ppts[0][0]), "row": int(ppts[0][1])}]
    resp = R._rpc(sid, "initAndStart",
                  [{"configJson": json.dumps(out), "seed": seed, "playerUnits": player_units}], timeout=40)
    rid = (resp.get("result") or {}).get("runnerId")
    if rid is None:
        return None, f"initAndStart KO: {resp.get('error') or resp}"
    return rid, None


@pytest.fixture
def votan_runner(host, live_session):
    """rid d'un runner avec votanMemnyr (injecte), auto-dispose."""
    rid, err = _build_votan(host, live_session)
    if rid is None:
        pytest.skip(f"build votanMemnyr KO: {err}")
    yield rid
    try:
        host._rpc(live_session, "disposeRunner", [{"runnerId": rid}], timeout=20)
    except Exception:
        pass


# ------------------------------------------------------------------ helpers d'etat

def _seed_rng(s):
    rng = IntBasedMersenneTwister()
    rng.mt = list(s["mt"]); rng.mti = s["mti"]
    return rng


def _tile_of(board, state, uid):
    pc = state.get_entity(uid).get_component(PositionComponent)
    return board.id_at(pc.col, pc.row) if pc is not None else None


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
    """(spawn_tile, enemy_pos_tile) : tuile LIBRE adjacente au caster + position LIBRE adjacente a CETTE tuile
    (dist 1 <= range 2 du summon) ou driver l'ennemi. None sinon."""
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
    hp = int(ability_var("IronkinSteeljack", "summonHp", lvl, multiplier_pct=mult) or 0)
    dmg = int(ability_var("IronkinSteeljack", "summonDmg", lvl, multiplier_pct=mult) or 0)
    return lvl, mult, hp, dmg


# ------------------------------------------------------------------ FACE 1 : PORT (offline, etat reel)

def test_steeljack_spawn_onappearance_port(rpc, votan_runner):
    """PORT (execute, etat REEL charge) : spawn votanSmnSteeljack EQUIPE-DU-CASTER sur la tuile ciblee,
    hp=summonHp[level], atk=summonDmg[level], puis attaque a l'apparition l'ennemi adjacent (drive-positions)
    + no-move caster. Valide MON code (le corps natif est byte-identique a AberrantHypermorph IdunBattleLogic.Entities.Abilities.Active.Loki.AberrantHypermorphAbility$$ExecuteBehaviour)."""
    from engine.runner.operations.summon_ai import _apply_active_ability
    from engine.entities.stats import StatType
    rid = votan_runner
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

    res = _apply_active_ability(state, caster, spawn_tile, STEELJACK)
    diag = (res or {}).get("diag") or {}
    spawned = diag.get("spawned") or []
    attacks = diag.get("attacks") or []
    flags = diag.get("flags") or {}
    print(f"\n[STEELJACK/port] routed={res.get('routed')} level={lvl} mult={mult} "
          f"exp_hp={exp_hp} exp_dmg={exp_dmg} spawned={spawned} attacks={attacks} "
          f"tile={diag.get('tile')} flags_turn_finished={flags.get('turn_finished')}")

    assert res.get("routed") == "handler" and diag.get("ported") is True, f"1219 non porte: {res}"
    assert len(spawned) == 1, f"count summon != 1: {spawned}"
    sid_ = spawned[0]
    assert sid_ in (set(state.entities) - before), "le summon n'a pas ete ajoute a l'etat"
    suc = state.get_entity(sid_)
    assert suc.get_component(OwnerComponent).team == cteam, "summon pas sur l'equipe du caster"
    assert suc.get_component(UnitComponent).visual_id == SUMMON_VID, "mauvais visual_id summon"
    assert _tile_of(board, state, sid_) == spawn_tile, "summon pas sur la tuile ciblee"
    assert suc.get_component(HealthComponent).hp_max == exp_hp, \
        f"hp_max {suc.get_component(HealthComponent).hp_max} != summonHp[{lvl}]x{mult}={exp_hp}"
    got_atk = int(suc.get_component(StatsComponent).ctx.stat(StatType.ATTACK))
    assert got_atk == exp_dmg, f"atk {got_atk} != summonDmg[{lvl}]x{mult}={exp_dmg}"
    assert len(attacks) == 1, f"attaque a l'apparition absente/multiple: {attacks}"
    at = attacks[0]
    assert at["summon"] == sid_ and at["target"] == enemy, f"attaquant/cible KO: {at} (enemy={enemy})"
    assert at["total"] and at["total"] > 0, f"degat a l'apparition nul: {at}"
    # no-move-this-turn : 1219 hors des frozensets base.py -> defauts -> FinishUnitTurn (turn_finished=True)
    assert flags.get("turn_finished") is True, f"le caster devrait finir son tour (no-move): {flags}"


def test_steeljack_noop_on_non_tile(rpc, votan_runner):
    """target_id non-tuile du board -> Spawn no-op (spawned=[]) sans erreur (pas d'AddEffect a executer)."""
    from engine.runner.operations.summon_ai import _apply_active_ability
    rid = votan_runner
    state, board = _load(rpc, rid)
    caster = _find(state, CARRIER)
    if caster is None:
        pytest.skip("caster absent")
    bogus = max(board.by_id) + 999999
    res = _apply_active_ability(state, caster, bogus, STEELJACK)
    diag = (res or {}).get("diag") or {}
    assert res.get("routed") == "handler" and diag.get("ported") is True, res
    assert (diag.get("spawned") or []) == [], f"spawn sur une non-tuile: {diag}"


# ------------------------------------------------------------------ FACE 2 : LIVE (cast natif, best-effort)

def test_steeljack_live_spawn_confront(rpc, votan_runner):
    """LIVE : le cast tile-target natif spawn le Steeljack (equipe / tuile / hpMax du port).

    Le "blocage headless FindFirstObjectByType" documente jusqu'ici etait un DOUBLE faux negatif
    (case-92) : (a) la config d'ability d'IronkinSteeljack manquait dans `BC.Abilities` ->
    `AbilityConfiguration$$GetVariableForLevel` levait ("system error") ; (b) la tuile-cible n'etait
    pas ADJACENTE au caster -> `ok:true` / `spawned:0`. Les deux corriges, le cast passe.
    PIEGE : le summon apparait sous le `visualId` du gameconfig (`votanNpc2Steeljack`), pas sous
    l'id de son entree (`votanSmnSteeljack`) -- chercher l'id ne le trouve jamais."""
    rid = votan_runner
    state, board = _load(rpc, rid)
    caster = _find(state, CARRIER)
    if caster is None:
        pytest.skip("caster absent")
    cteam = state.get_entity(caster).get_component(OwnerComponent).team
    lvl, mult, exp_hp, _dmg = _expected_summon_stats(state, caster)
    # tuile legale immediate (fromHere) via abilityTargets (respecte le placement natif du BigTarget)
    at = rpc("abilityTargets", {"runnerId": rid, "unitId": caster, "abilityType": STEELJACK}, 60) or {}
    fh = []
    for u in at.get("units", []):
        for ab in u.get("abilities", []):
            if ab.get("abilityId") == STEELJACK:
                fh = [(t["tile"]["col"], t["tile"]["row"]) for t in ab.get("fromHere", [])]
    assert fh, "aucune tuile fromHere legale pour 1219"
    # ADJACENCE OBLIGATOIRE : le behaviour de Spawn exige une tuile voisine du caster ; une tuile
    # legale mais distante donne un cast `ok:true` sans effet (mutated=false, spawned=0).
    import hexgeo
    cpc = state.get_entity(caster).get_component(PositionComponent)
    adj = [t for t in fh if hexgeo.distance(t, (cpc.col, cpc.row)) == 1]
    assert adj, f"aucune tuile fromHere ADJACENTE au caster ({cpc.col},{cpc.row}) parmi {fh}"
    col, row = adj[0]
    before = {u["squadId"] for u in (rpc("observeBattle", {"runnerId": rid}, 40) or {}).get("units", [])}
    res = rpc("applyAction", {"runnerId": rid, "action": {
        "kind": "ability", "casterId": caster, "abilityType": STEELJACK,
        "to": {"col": col, "row": row}}}, 60) or {}
    act = (res.get("actions") or [{}])[0]
    assert not act.get("error"), f"cast natif en erreur: {act.get('error')} spawned={act.get('spawned')}"
    # le summon porte le visualId du gameconfig (`votanNpc2Steeljack`), pas l'id de son entree
    import gameconfig as GC
    smn_vid = (GC.unit(SUMMON_VID) or {}).get("visualId") or SUMMON_VID
    summons = [u for u in (rpc("observeBattle", {"runnerId": rid}, 40) or {}).get("units", [])
               if u.get("visualId") == smn_vid and u["squadId"] not in before and not u.get("isDead")]
    print(f"\n[STEELJACK/live-spawn] exp_hp={exp_hp} cteam={cteam} tile=({col},{row}) "
          f"summons={[(u['squadId'], u.get('teamId'), u.get('hpMax')) for u in summons]}")
    assert summons, "aucun votanSmnSteeljack spawne live"
    su = summons[0]
    assert su.get("teamId") == cteam, f"summon live team {su.get('teamId')} != caster {cteam}"
    assert su.get("hpMax") == exp_hp, \
        f"hpMax live {su.get('hpMax')} != summonHp[{lvl}]x{mult}={exp_hp} (WithStatsFromConfig)"
