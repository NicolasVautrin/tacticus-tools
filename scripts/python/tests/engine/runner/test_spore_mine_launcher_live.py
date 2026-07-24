"""VALIDATION du port COMBAT de SporeMineLauncher (1145, `tyranBiovore` Biovore MoW, Tyranids) -- case-220 §6.16.

Artefact natif : `SporeMineLauncherAbility$$ExecuteBehaviour @18120a3f0` (DECOMPILE, mirror 1:1). Il decompile
en UN seul noeud Spawn passe a `AActiveAbility.Execute` :
    Execute( Spawn(caster@0x160, Target@0x178 = TUILE ciblee, GetStringConstant(config,0)="tyranSmnSporeMine",
                   WithStatsFromConfig(config 1145, Get(param_2[0]), Get(param_2[1]))) )
STRUCTURELLEMENT == le corps partage `AberrantHypermorph/IronkinSteeljack @1811b0550` (spawn tile-target +
WithStatsFromConfig), MOINS le volet on-appearance : `PerformAIAttackFromCurrentPosition` + `*(options+0x18)
=onAppearance` sont ABSENTS ici (verifie par comparaison des deux decompiles) -> le spore mine ne fait RIEN a
l'apparition (coherent gameconfig : `tyranSmnSporeMine` = weapons=[], activeAbilities=[], summonDmg=0). Le
`ctor @18120a610` fait `AActiveAbility.ctor(..., 2, 0)` (IDENTIQUE Ironkin/Aberrant -> flags de tour defauts).
Cast tile-target ; `GetDynamicInvalidTargetReason @18120a590` = tuile valide ssi PAS occupee par un ennemi.

PORTEUR = MoW (Biovore). Deux specificites :
  - Il est SPAWNABLE dans le pool MoW (`rl_duel build --p-mow tyranBiovore`) -> le cast LIVE natif spawn
    reellement le mine (FACE 2 fonctionne, contrairement a Ironkin bloque en headless).
  - Il n'est PAS charge comme entite offline (`load_state` omet les MoW). Pour la FACE 1 (port offline), on
    FABRIQUE le caster depuis les donnees mow LIVE reelles (team/player/level/mult lus de decisionView.mows) :
    la seule fabrication est de creer l'entite que load_state ne cree pas ; les stats produites derivent de
    donnees live reelles.

TROIS volets :
  - FACE 1 EXECUTE (port offline via le handler, etat REEL charge, caster fabrique) : spawn UN
    tyranSmnSporeMine sur l'EQUIPE DU CASTER, sur la tuile ciblee, hp=summonHp[level]xmult ; AUCUNE attaque a
    l'apparition ('attacks' absent), termine le tour du caster (defauts base.py). Valide MON code
    (SpawnSporeMine -> _spawn_config_grot, Operation deja live-validee par ScarabHive/Aberrant/Ironkin).
  - FACE 2 LIVE (cast natif) : le runner spawn tyranSmnSporeMine (equipe/tuile/hp du port) + AUCUN degat
    on-appearance (mine inerte) ; les tuiles ennemies sont EXCLUES des cibles legales (gate RE).
  - NO-OP : target non-tuile -> spawned=[] sans erreur.

RESIDU DOCUMENTE (case doc §6.16) : le passif de detonation `FloatingDeath` du mine (kit summon SEPARE, non
porte) n'est pas cable -> l'AoE aval = 0 (le mine apparait mais ne detone pas offline). Hors perimetre de CE
port (le behaviour d'ability, lui, est bit-exact).

Drive les positions ; lit l'etat LIVE ; state-file UNIQUE (chemin absolu + agent id) ; ASCII-only.
"""
from __future__ import annotations

import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest

from engine.runner.snapshot import load_state
from engine.runner.components import (OwnerComponent, PositionComponent, HealthComponent,
                                      UnitComponent, StatsComponent)

AGENT_ID = "afa8602ae92c07436"
PYDIR = Path(__file__).resolve().parents[3]                       # scripts/python
ROOT = Path(__file__).resolve().parents[5]                        # racine repo
STATE = ROOT / "data" / f"_pytest_sporemine_{AGENT_ID}.json"      # state-file UNIQUE (discipline runner)

SPORE = 1145
CARRIER = "tyranBiovore"
SUMMON_VID = "tyranSmnSporeMine"
SEED = "777"


# ------------------------------------------------------------------ build MoW runner (subprocess)

def _build_mow(seed: str = SEED):
    """Runner ISOLE avec tyranBiovore en MoW (`--p-mow`) sur une board MoW-capable (board-pool pvp seede).
    Renvoie rid ou None (skip). state-file UNIQUE."""
    proc = subprocess.run(
        [sys.executable, "rl_duel.py", "build", "--seed", seed, "--board-pool", "pvp",
         "--p-mow", CARRIER, "--p-units", "necroDestroyer,necroWarden",
         "--a-units", "necroDestroyer,necroWarden", "--state-file", str(STATE)],
        cwd=str(PYDIR), capture_output=True, text=True, encoding="utf-8", errors="replace")
    if not STATE.exists():
        return None, f"build KO: {(proc.stderr or proc.stdout or '')[-300:]}"
    return json.loads(STATE.read_text())["runnerId"], None


@pytest.fixture(scope="module")
def mine_runner(host, live_session):
    rid, err = _build_mow()
    if rid is None:
        pytest.skip(f"build tyranBiovore MoW KO: {err}")

    def _rpc(m, b, t=60):
        r = host._rpc(live_session, m, [b], timeout=t)
        return r.get("result") if isinstance(r, dict) and "result" in r else r

    yield rid, _rpc
    try:
        host._rpc(live_session, "disposeRunner", [{"runnerId": rid}], timeout=20)
    except Exception:
        pass


# ------------------------------------------------------------------ helpers

def _board_and_state(rpc, rid):
    from engine.entities.pathfinding.board import Board
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    if not (isinstance(bg, dict) and bg.get("tiles")):
        pytest.skip("boardGraph indispo")
    board = Board(bg["tiles"], adjacency="evenq")
    dec = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    ob = rpc("observeBattle", {"runnerId": rid}, 40)
    snap = rpc("combatSnapshot", {"runnerId": rid}, 60)
    state = load_state(dec, ob, snap)
    state.board = board
    return state, board, dec, ob


def _mow(dec):
    """(caster_id, team, player, level, mult) du MoW Biovore depuis decisionView.mows."""
    mow = next((m for m in (dec.get("mows") or []) if m.get("visualId") == CARRIER), None)
    if mow is None:
        pytest.skip("MoW Biovore absent de decisionView.mows")
    ab = next((a for a in (mow.get("abilities") or []) if a.get("id") == SPORE), None)
    if ab is None:
        pytest.skip("ability 1145 absente du MoW")
    return mow["casterId"], mow["team"], mow["owner"], ab["level"], ab["multiplier"]


def _fabricate_caster(state, team, player, level, mult):
    """Cree l'entite caster (Biovore) que load_state n'a pas creee (MoW), avec owner/level/mult LIVE reels.
    Le port ne lit que OwnerComponent + StatsComponent.ctx (level/mult) -> pas de position necessaire."""
    from engine.entities import UnitContext
    from engine.entities.stats import UnitStats
    ctx = UnitContext(entity_id=0, visual_id=CARRIER, active_ability_level=level,
                      ability_variables_multiplier=mult, traits=[], range=0, faction=None,
                      number_of_members=1, normal_profile=None, normal_profile_pierce=0,
                      normal_weapon_hits=1, normal_ranged=False, stats=UnitStats())
    e = state.add_entity()
    e.add_component(UnitComponent(visual_id=CARRIER, alive=True))
    e.add_component(OwnerComponent(team=team, player=player))
    e.add_component(StatsComponent(ctx=ctx))
    return e.id


def _exp_hp(level, mult):
    from engine.entities.effects.magnitude import ability_var
    return int(ability_var("SporeMineLauncher", "summonHp", level, multiplier_pct=mult) or 0)


def _legal_tiles(rpc, rid, caster_id):
    at = rpc("abilityTargets", {"runnerId": rid, "unitId": caster_id, "abilityId": SPORE}, 90) or {}
    for u in (at.get("units") or []):
        for ab in (u.get("abilities") or []):
            if ab.get("abilityId") == SPORE:
                return [(t["tile"]["col"], t["tile"]["row"]) for t in (ab.get("targets") or [])]
    return []


def _occ(ob):
    return {(u.get("col"), u.get("row")) for u in (ob.get("units") or []) if not u.get("isDead")}


# ------------------------------------------------------------------ FACE 1 : PORT offline (caster fabrique)

def test_spore_mine_port_offline(mine_runner):
    """PORT (execute, etat REEL, caster fabrique) : spawn UN tyranSmnSporeMine EQUIPE-DU-CASTER sur la tuile
    ciblee, hp=summonHp[level]xmult, AUCUNE attaque a l'apparition ('attacks' absent), termine le tour."""
    from engine.runner.operations.summon_ai import _apply_active_ability
    rid, rpc = mine_runner
    state, board, dec, ob = _board_and_state(rpc, rid)
    caster_id, team, player, level, mult = _mow(dec)
    exp_hp = _exp_hp(level, mult)
    cid = _fabricate_caster(state, team, player, level, mult)

    # tuile-cible LIBRE (legale, non occupee)
    occ = _occ(ob)
    tile = next(((c, r) for (c, r) in _legal_tiles(rpc, rid, caster_id) if (c, r) not in occ), None)
    if tile is None:
        pytest.skip("aucune tuile-cible libre")
    tile_id = board.id_at(*tile)
    before = set(state.entities)

    res = _apply_active_ability(state, cid, tile_id, SPORE)
    diag = (res or {}).get("diag") or {}
    spawned = diag.get("spawned") or []
    flags = diag.get("flags") or {}
    print(f"\n[SPORE/port] routed={res.get('routed')} lvl={level} mult={mult} exp_hp={exp_hp} "
          f"spawned={spawned} attacks={diag.get('attacks')} tile={diag.get('tile')} "
          f"turn_finished={flags.get('turn_finished')}")

    assert res.get("routed") == "handler" and diag.get("ported") is True, f"1145 non porte: {res}"
    assert diag.get("summon") == SUMMON_VID, f"mauvais summon: {diag.get('summon')}"
    assert len(spawned) == 1, f"count summon != 1: {spawned}"
    sid_ = spawned[0]
    assert sid_ in (set(state.entities) - before), "le summon n'a pas ete ajoute a l'etat"
    su = state.get_entity(sid_)
    assert su.get_component(UnitComponent).visual_id == SUMMON_VID, "mauvais visual_id summon"
    soc = su.get_component(OwnerComponent)
    assert soc.team == team and soc.player == player, \
        f"summon owner ({soc.team},{soc.player}) != caster ({team},{player}) (CopyOwner)"
    spc = su.get_component(PositionComponent)
    assert spc is not None and board.id_at(spc.col, spc.row) == tile_id, "summon pas sur la tuile ciblee"
    hc = su.get_component(HealthComponent)
    assert hc.hp == hc.hp_max == exp_hp, \
        f"hp {hc.hp}/{hc.hp_max} != summonHp[{level}]x{mult}={exp_hp} (WithStatsFromConfig)"
    # NO on-appearance : la structure natif (@18120a3f0) N'A PAS de PerformAIAttackFromCurrentPosition
    assert not diag.get("attacks"), f"attaque a l'apparition INATTENDUE (natif sans on-appearance): {diag.get('attacks')}"
    # termine le tour (1145 hors des frozensets base.py -> defauts)
    assert flags.get("turn_finished") is True, f"le caster devrait finir son tour: {flags}"


def test_spore_mine_noop_on_non_tile(mine_runner):
    """target_id non-tuile -> Spawn no-op (spawned=[]) sans erreur."""
    from engine.runner.operations.summon_ai import _apply_active_ability
    rid, rpc = mine_runner
    state, board, dec, _ob = _board_and_state(rpc, rid)
    _cid, team, player, level, mult = _mow(dec)
    cid = _fabricate_caster(state, team, player, level, mult)
    bogus = max(board.by_id) + 999999
    res = _apply_active_ability(state, cid, bogus, SPORE)
    diag = (res or {}).get("diag") or {}
    assert res.get("routed") == "handler" and diag.get("ported") is True, res
    assert (diag.get("spawned") or []) == [], f"spawn sur une non-tuile: {diag}"


# ------------------------------------------------------------------ FACE 2 : LIVE cast + confront

def test_spore_mine_live_spawn_confront(mine_runner):
    """LIVE : cast tile-target natif -> spawn tyranSmnSporeMine (equipe/tuile/hp == port) ; AUCUN degat
    on-appearance (mine inerte) ; tuiles ennemies EXCLUES des cibles legales (gate RE @18120a590)."""
    rid, rpc = mine_runner
    state, board, dec, ob = _board_and_state(rpc, rid)
    caster_id, team, player, level, mult = _mow(dec)
    exp_hp = _exp_hp(level, mult)

    # GATE : tuiles ennemies exclues des cibles legales
    legal = set(_legal_tiles(rpc, rid, caster_id))
    enemies = {(u.get("col"), u.get("row")) for u in (ob.get("units") or [])
               if u.get("teamId") != team and not u.get("isDead")}
    enemy_in_legal = enemies & legal
    assert not enemy_in_legal, f"gate KO : tuiles ennemies {enemy_in_legal} dans les cibles legales"

    occ = _occ(ob)
    tile = next(((c, r) for (c, r) in legal if (c, r) not in occ), None)
    if tile is None:
        pytest.skip("aucune tuile-cible libre")

    hp_before = {u.get("squadId"): u.get("hp") for u in (ob.get("units") or [])
                 if u.get("teamId") != team and not u.get("isDead")}
    before_ids = {u.get("squadId") for u in (ob.get("units") or [])}

    res = rpc("applyAction", {"runnerId": rid, "action": {
        "kind": "ability", "casterId": caster_id, "abilityType": SPORE,
        "to": {"col": tile[0], "row": tile[1]}}}, 60) or {}
    act = (res.get("actions") or [{}])[0]
    if act.get("error"):
        pytest.skip(f"cast natif bloque: {act.get('error')}")

    ob2 = rpc("observeBattle", {"runnerId": rid}, 40) or {}
    mines = [u for u in (ob2.get("units") or [])
             if u.get("visualId") == SUMMON_VID and u.get("squadId") not in before_ids and not u.get("isDead")]
    hp_after = {u.get("squadId"): u.get("hp") for u in (ob2.get("units") or [])}
    dmg = {k: hp_before[k] - hp_after.get(k, hp_before[k]) for k in hp_before
           if hp_before[k] != hp_after.get(k, hp_before[k])}
    print(f"\n[SPORE/live] tile={tile} exp_hp={exp_hp} mines={[(m.get('squadId'), m.get('teamId'), m.get('playerId'), m.get('hp'), (m.get('col'), m.get('row'))) for m in mines]} enemy_dmg={dmg}")

    assert len(mines) == 1, f"live a spawne {len(mines)} tyranSmnSporeMine != 1"
    lm = mines[0]
    assert lm.get("teamId") == team and lm.get("playerId") == player, \
        f"mine live owner ({lm.get('teamId')},{lm.get('playerId')}) != caster ({team},{player})"
    assert lm.get("hp") == exp_hp, f"mine live hp {lm.get('hp')} != summonHp[{level}]x{mult}={exp_hp}"
    assert (lm.get("col"), lm.get("row")) == tile, f"mine live pos {(lm.get('col'), lm.get('row'))} != cible {tile}"
    assert not dmg, f"degat on-appearance INATTENDU {dmg} (mine inerte, natif sans on-appearance)"

    # CONFRONT offline : le port fabrique reproduit hp/owner/tile bit-exact
    cid = _fabricate_caster(state, team, player, level, mult)
    from engine.runner.abilities.tyranids import SporeMineLauncherAbility
    tile_id = board.id_at(*tile)
    off = SporeMineLauncherAbility().execute_behaviour(state, cid, tile_id)
    osp = off.get("spawned") or []
    assert len(osp) == 1, f"offline a spawne {len(osp)} != 1"
    oe = state.get_entity(osp[0])
    ohc = oe.get_component(HealthComponent)
    ooc = oe.get_component(OwnerComponent)
    opc = oe.get_component(PositionComponent)
    assert ohc.hp == lm.get("hp"), f"confront hp off {ohc.hp} != live {lm.get('hp')}"
    assert (ooc.team, ooc.player) == (lm.get("teamId"), lm.get("playerId")), "confront owner off != live"
    assert (opc.col, opc.row) == (lm.get("col"), lm.get("row")), "confront pos off != live"
