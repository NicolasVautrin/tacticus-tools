"""VALIDATION LIVE du port COMBAT d'AlphaWarrior (1112, `tyranWingedPrime` Winged Prime, Tyranids) -- case-220 §6.16.

Artefact natif : `IdunBattleLogic.Entities.Abilities.Active.Loki.AlphaWarriorAbility$$ExecuteBehaviour` (DECOMPILE, mirror 1:1). Il decompile en
UN seul noeud Spawn passe a `AActiveAbility.Execute` :
    Execute( Spawn(caster@0x160, Target@0x178 = TUILE ciblee, GetStringConstant(config,0)="tyranSmnWarrior",
                   WithStatsFromConfig(config 1112, amount=null))
             .onAppearance(+0x18) = PerformAIAttackFromCurrentPosition(Spawned@0x180) )
STRUCTURELLEMENT == le TEMPLATE `AberrantHypermorph IdunBattleLogic.Entities.Abilities.Active.Loki.AberrantHypermorphAbility$$ExecuteBehaviour` (Spawn tile-target + WithStatsFromConfig +
on-appearance PerformAIAttackFromCurrentPosition), a TROIS details pres (verifies par comparaison des deux
decompiles) : config AlphaWarrior ; nœud amount de WithStatsFromConfig = null (vs AbilityLevelAmount) ; sujet
de l'on-appearance = Spawned@0x180 (vs Target@0x178, resolvent au MEME summon, cf. MasterOfTheTutelaries).
Le `IdunBattleLogic.Entities.Abilities.Active.Loki.AlphaWarriorAbility$$.ctor` fait `AActiveAbility.ctor(..., 2, 0)` (IDENTIQUE Aberrant/Spore -> flags de tour defauts,
1112 hors des frozensets base.py). Cast tile-target ; `IdunBattleLogic.Entities.Abilities.Active.Loki.AlphaWarriorAbility$$GetDynamicInvalidTargetReason` ->
`IsInTeamSynapseRange` = legalite live/RPC (HORS ExecuteBehaviour, ABSENT du port -> IA sur-permissive).

PORTEUR = unite NORMALE (non-MoW) -> SPAWNABLE en p-unit (`rl_duel build --p-units tyranWingedPrime`) et
chargee comme entite offline (`load_state`) : PAS de fabrication de caster (contrairement au MoW Biovore).

NOTE visualId : le natif Spawn recoit le constant config "tyranSmnWarrior" (== `IdunBattleLogic.Entities.Abilities.Active.Loki.AlphaWarriorAbility$$GetSummonId`), mais
la resolution DOWNSTREAM (SpawnUnitBehaviour, HORS ExecuteBehaviour) spawn la variante NPC concrete
`tyranNpc4Warrior` (MEME kit -- memes armes melee 3-hit Physical + ranged r2 3-hit Bio, memes abilities/passifs
-- SEULE difference : `tyranNpc4Warrior` n'a pas le trait `Summon`). Le port mirror l'ExecuteBehaviour ->
spawn le constant config "tyranSmnWarrior" ; les stats (summonHp/summonDmg/summonArmor) viennent de la config
d'ABILITY (AlphaWarrior), BIT-EXACT quel que soit le visualId, et les armes sont identiques -> l'on-appearance
est identique. Cote LIVE on identifie le summon par l'evenement `appeared` (squadId neuf), PAS par visualId.

QUATRE volets :
  - FACE 1 EXECUTE (port offline via le handler, etat REEL, ennemi DRIVE adjacent) : spawn UN tyranSmnWarrior
    sur l'EQUIPE DU CASTER, sur la tuile ciblee, hp=summonHp[level]xmult, atk=summonDmg[level]xmult, puis
    attaque a l'apparition l'ennemi adjacent (PerformAIAttackFromCurrentPosition). Termine le tour du caster.
  - FACE 2 LIVE (cast natif) : le runner spawn le summon (equipe/tuile/hpMax == port, BIT-EXACT via l'event
    `appeared.hpAfter`) sur la tuile ciblee.
  - FACE 2bis LIVE (on-appearance) : ennemi DRIVE adjacent a la tuile de spawn (applyAction ignore portee/
    propriete) -> le summon attaque a l'apparition (l'ennemi perd des HP). Best-effort.
  - NO-OP : target non-tuile -> spawned=[] sans erreur.

Le degat EXACT de l'attaque a l'apparition est un RAFFINEMENT non asserte (RNG + choix d'arme/cible AI natif) ;
on valide COUNTS/EQUIPE/TUILE/hp/atk BIT-EXACT + attaque-a-eu-lieu (meme discipline que test_aberrant_hypermorph).

Drive les positions ; lit l'etat LIVE ; state-file UNIQUE (chemin absolu + agent id) ; dispose ses runners ;
ASCII-only.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from engine.runner.snapshot import load_state
from engine.runner.prng import IntBasedMersenneTwister
from engine.runner.components import (OwnerComponent, PositionComponent, HealthComponent,
                                      UnitComponent, StatsComponent)

AGENT_ID = "af9c9499961ce9958"
PYDIR = Path(__file__).resolve().parents[3]                        # scripts/python
ROOT = Path(__file__).resolve().parents[5]                         # racine repo
STATE = ROOT / "data" / f"_pytest_alphawarrior_{AGENT_ID}.json"    # state-file UNIQUE (discipline runner)

ALPHA = 1112
CARRIER = "tyranWingedPrime"
SUMMON_VID = "tyranSmnWarrior"          # constant config (GetStringConstant(config,0) = IdunBattleLogic.Entities.Abilities.Active.Loki.AlphaWarriorAbility$$GetSummonId)
ENEMY = "ultraTitus"                    # tanky : encaisse l'on-appearance sans mourir
SEED = "4242"
BOARD = "MC1_67"


# ------------------------------------------------------------------ build runner (subprocess, unique state-file)

@pytest.fixture(scope="module")
def alpha(host, live_session):
    """Fabrique de runners ISOLES frais (tyranWingedPrime vs ultraTitus), state-file UNIQUE, tous disposes au
    teardown. Renvoie (build() -> rid, rpc)."""
    created: list[int] = []

    def _build(seed: str = SEED):
        proc = subprocess.run(
            [sys.executable, "rl_duel.py", "build", "--seed", seed, "--board", BOARD,
             "--p-units", CARRIER, "--a-units", ENEMY, "--state-file", str(STATE)],
            cwd=str(PYDIR), capture_output=True, text=True, encoding="utf-8", errors="replace")
        if not STATE.exists():
            pytest.skip(f"build tyranWingedPrime KO: {(proc.stderr or proc.stdout or '')[-300:]}")
        rid = json.loads(STATE.read_text())["runnerId"]
        created.append(rid)
        return rid

    def _rpc(m, b, t=90):
        r = host._rpc(live_session, m, [b], timeout=t)
        return r.get("result") if isinstance(r, dict) and "result" in r else r

    yield _build, _rpc
    for rid in created:
        try:
            host._rpc(live_session, "disposeRunner", [{"runnerId": rid}], timeout=20)
        except Exception:
            pass


# ------------------------------------------------------------------ helpers

def _seed_rng(s):
    rng = IntBasedMersenneTwister()
    rng.mt = list(s["mt"]); rng.mti = s["mti"]
    return rng


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


def _tile_of(board, state, uid):
    pc = state.get_entity(uid).get_component(PositionComponent)
    return board.id_at(pc.col, pc.row) if pc is not None else None


def _occupied(state, board):
    return {_tile_of(board, state, u) for u in list(state.entities)
            if state.get_entity(u).get_component(PositionComponent) is not None}


def _pick_free_adjacent(state, board, caster):
    """(spawn_tile, enemy_pos_tile) : tuile LIBRE adjacente au caster + tuile LIBRE adjacente a CELLE-ci
    (ou driver l'ennemi). None sinon."""
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
    hp = int(ability_var("AlphaWarrior", "summonHp", lvl, multiplier_pct=mult) or 0)
    dmg = int(ability_var("AlphaWarrior", "summonDmg", lvl, multiplier_pct=mult) or 0)
    return lvl, mult, hp, dmg


def _live_units(rpc, rid):
    return (rpc("observeBattle", {"runnerId": rid}, 40) or {}).get("units") or []


# ------------------------------------------------------------------ FACE 1 : PORT (offline, driven)

def test_alpha_spawn_onappearance_port(alpha):
    """PORT (execute) : spawn tyranSmnWarrior EQUIPE-DU-CASTER sur la tuile ciblee, hp=summonHp[level],
    atk=summonDmg[level], puis attaque a l'apparition l'ennemi adjacent (drive-positions)."""
    from engine.runner.operations.summon_ai import _apply_active_ability
    from engine.entities.stats import StatType
    build, rpc = alpha
    rid = build()
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

    coc = state.get_entity(caster).get_component(OwnerComponent)
    cteam, cplayer = coc.team, coc.player
    lvl, mult, exp_hp, exp_dmg = _expected_summon_stats(state, caster)
    before = set(state.entities)

    res = _apply_active_ability(state, caster, spawn_tile, ALPHA)
    diag = (res or {}).get("diag") or {}
    spawned = diag.get("spawned") or []
    attacks = diag.get("attacks") or []
    print(f"\n[ALPHA/port] routed={res.get('routed')} level={lvl} mult={mult} "
          f"exp_hp={exp_hp} exp_dmg={exp_dmg} spawned={spawned} attacks={attacks} tile={diag.get('tile')}")

    assert res.get("routed") == "handler" and diag.get("ported") is True, f"1112 non porte: {res}"
    assert diag.get("summon") == SUMMON_VID, f"mauvais summon: {diag.get('summon')}"
    assert len(spawned) == 1, f"count summon != 1: {spawned}"
    sid = spawned[0]
    assert sid in (set(state.entities) - before), "le summon n'a pas ete ajoute a l'etat"
    suc = state.get_entity(sid)
    soc = suc.get_component(OwnerComponent)
    assert (soc.team, soc.player) == (cteam, cplayer), \
        f"summon owner ({soc.team},{soc.player}) != caster ({cteam},{cplayer}) (CopyOwner)"
    assert suc.get_component(UnitComponent).visual_id == SUMMON_VID, "mauvais visual_id summon"
    assert _tile_of(board, state, sid) == spawn_tile, "summon pas sur la tuile ciblee"
    hc = suc.get_component(HealthComponent)
    assert hc.hp == hc.hp_max == exp_hp, \
        f"hp {hc.hp}/{hc.hp_max} != summonHp[{lvl}]x{mult}={exp_hp} (WithStatsFromConfig)"
    got_atk = int(suc.get_component(StatsComponent).ctx.stat(StatType.ATTACK))
    assert got_atk == exp_dmg, f"atk {got_atk} != summonDmg[{lvl}]x{mult}={exp_dmg}"
    assert len(attacks) == 1, f"attaque a l'apparition absente/multiple: {attacks}"
    at = attacks[0]
    assert at["summon"] == sid and at["target"] == enemy, f"attaquant/cible KO: {at} (enemy={enemy})"
    assert at["total"] and at["total"] > 0, f"degat a l'apparition nul: {at}"
    # 1112 hors des frozensets base.py -> termine le tour + pose ActiveAbilityUsed
    flags = diag.get("flags") or {}
    assert flags.get("turn_finished") is True, f"le caster devrait finir son tour: {flags}"


# ------------------------------------------------------------------ FACE 2 : LIVE (spawn confront)

def test_alpha_live_spawn_confront(alpha):
    """LIVE : cast tile-target sur une tuile libre adjacente au caster -> le runner natif spawn le summon sur
    l'EQUIPE DU CASTER, hpAfter == summonHp[level]xmult du port (WithStatsFromConfig, BIT-EXACT)."""
    build, rpc = alpha
    rid = build()
    state, board = _load(rpc, rid)
    caster = _find(state, CARRIER)
    if caster is None:
        pytest.skip("caster absent")
    coc = state.get_entity(caster).get_component(OwnerComponent)
    cteam, cplayer = coc.team, coc.player
    lvl, mult, exp_hp, _exp_dmg = _expected_summon_stats(state, caster)
    ctile = _tile_of(board, state, caster)
    occ = _occupied(state, board)
    spawn = next((t for t in board.neighbours(ctile)
                  if t not in occ and board.walkable(t) and t in board.by_id), None)
    if spawn is None:
        pytest.skip("pas de tuile libre adjacente au caster")
    info = board.by_id[spawn]

    before = {u.get("squadId") for u in _live_units(rpc, rid)}
    res = rpc("applyAction", {"runnerId": rid, "action": {
        "kind": "ability", "casterId": caster, "abilityType": ALPHA,
        "to": {"col": info["col"], "row": info["row"]}}}, 60) or {}
    act = (res.get("actions") or [{}])[0]
    if act.get("error"):
        pytest.skip(f"cast natif bloque: {act.get('error')}")
    # event `appeared` = le summon fraichement pose (hpAfter BIT-EXACT, tuile de spawn)
    appeared = [c for c in (act.get("changes") or []) if c.get("appeared")]
    ob2 = _live_units(rpc, rid)
    summons = [u for u in ob2 if u.get("squadId") not in before and not u.get("isDead")
               and u.get("visualId") not in (CARRIER, ENEMY)]
    print(f"\n[ALPHA/live-spawn] level={lvl} exp_hp={exp_hp} caster=({cteam},{cplayer}) spawn_tile={info} "
          f"appeared={appeared} summons={[(u.get('squadId'), u.get('visualId'), u.get('teamId'), u.get('playerId'), u.get('hpMax'), (u.get('col'), u.get('row'))) for u in summons]}")

    assert len(appeared) == 1, f"event appeared != 1: {appeared}"
    ap = appeared[0]
    assert ap.get("hpAfter") == exp_hp, \
        f"summon live hpAfter {ap.get('hpAfter')} != summonHp[{lvl}]x{mult}={exp_hp} (WithStatsFromConfig)"
    assert (ap.get("to") or {}).get("col") == info["col"] and (ap.get("to") or {}).get("row") == info["row"], \
        f"summon live pos {ap.get('to')} != tuile ciblee {info}"
    assert len(summons) == 1, f"observeBattle summons != 1: {summons}"
    su = summons[0]
    assert su.get("teamId") == cteam and su.get("playerId") == cplayer, \
        f"summon live owner ({su.get('teamId')},{su.get('playerId')}) != caster ({cteam},{cplayer})"
    assert su.get("hpMax") == exp_hp, \
        f"summon live hpMax {su.get('hpMax')} != summonHp[{lvl}]x{mult}={exp_hp}"
    # CONFRONT port<->live : `exp_hp` = `ability_var("AlphaWarrior","summonHp",level,mult)` == le calcul EXACT
    # de la feuille `SpawnAlphaWarrior` (`_spawn_config_grot`) ; l'egalite live `hpAfter/hpMax == exp_hp`
    # ci-dessus EST donc le confront bit-exact du port contre le spawn natif.


# ------------------------------------------------------------------ FACE 2bis : LIVE (attaque a l'apparition)

def test_alpha_live_onappearance_attack(alpha):
    """LIVE : ennemi DRIVE adjacent a une tuile de spawn (applyAction ignore portee/propriete) -> le summon
    attaque a l'apparition (l'ennemi perd des HP). Best-effort : skip si drive/cast impossible."""
    build, rpc = alpha
    rid = build()
    state, board = _load(rpc, rid)
    caster = _find(state, CARRIER)
    enemy = _find(state, ENEMY)
    if caster is None or enemy is None:
        pytest.skip("caster/enemy absents")
    coc = state.get_entity(caster).get_component(OwnerComponent)
    picked = _pick_free_adjacent(state, board, caster)
    if picked is None:
        pytest.skip("pas de tuile libre adjacente drivable")
    spawn_tile, enemy_pos = picked
    sinfo, einfo = board.by_id[spawn_tile], board.by_id[enemy_pos]

    # s'assurer que c'est le tour du caster
    for _ in range(4):
        dec = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
        cp = dec.get("currentPlayer")
        cu = next((u for u in dec.get("units", []) if u.get("id") == caster), None)
        if cu is not None and cp == cu.get("owner"):
            break
        rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 40)

    # DRIVE l'ennemi adjacent a la tuile de spawn (applyAction ignore portee/propriete)
    mv = rpc("applyAction", {"runnerId": rid, "action": {
        "kind": "move", "unitId": enemy, "to": {"col": einfo["col"], "row": einfo["row"]}}}, 40) or {}
    if ((mv.get("actions") or [{}])[0]).get("error"):
        pytest.skip(f"drive ennemi bloque: {(mv.get('actions') or [{}])[0].get('error')}")

    hp0 = next((u.get("hp") for u in _live_units(rpc, rid) if u.get("squadId") == enemy), None)
    if hp0 is None:
        # squadId != entity id cote observeBattle : retrouver l'ennemi par visualId
        eu = next((u for u in _live_units(rpc, rid) if u.get("visualId") == ENEMY and not u.get("isDead")), None)
        hp0 = eu.get("hp") if eu else None
        enemy_sq = eu.get("squadId") if eu else None
    else:
        enemy_sq = enemy
    res = rpc("applyAction", {"runnerId": rid, "action": {
        "kind": "ability", "casterId": caster, "abilityType": ALPHA,
        "to": {"col": sinfo["col"], "row": sinfo["row"]}}}, 60) or {}
    act = (res.get("actions") or [{}])[0]
    if act.get("error"):
        pytest.skip(f"cast natif bloque: {act.get('error')}")
    ob1 = _live_units(rpc, rid)
    eu2 = next((u for u in ob1 if u.get("squadId") == enemy_sq), None)
    hp1 = eu2.get("hp") if eu2 else None
    summons = [u for u in ob1 if u.get("squadId") not in () and u.get("visualId") not in (CARRIER, ENEMY)
               and not u.get("isDead")]
    print(f"\n[ALPHA/live-attack] spawn_tile={sinfo} enemy_pos={einfo} summons={len(summons)} "
          f"enemy hp {hp0}->{hp1}")
    assert summons, "aucun summon spawne"
    assert hp0 is not None and hp1 is not None and hp1 < hp0, \
        f"l'ennemi n'a pas pris de degat a l'apparition ({hp0}->{hp1})"


# ------------------------------------------------------------------ Degenere

def test_alpha_noop_on_non_tile(alpha):
    """target_id non-tuile du board -> Spawn no-op (spawned=[]) sans erreur."""
    from engine.runner.operations.summon_ai import _apply_active_ability
    build, rpc = alpha
    rid = build()
    state, board = _load(rpc, rid)
    caster = _find(state, CARRIER)
    if caster is None:
        pytest.skip("caster absent")
    bogus = max(board.by_id) + 999999
    res = _apply_active_ability(state, caster, bogus, ALPHA)
    diag = (res or {}).get("diag") or {}
    assert res.get("routed") == "handler" and diag.get("ported") is True, res
    assert (diag.get("spawned") or []) == [], f"spawn sur une non-tuile: {diag}"
