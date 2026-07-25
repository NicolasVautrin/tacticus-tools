"""VALIDATION du DEBLOQUEUR « cast d'ability par une MACHINE OF WAR hors-plateau ».

CE QUI ETAIT BLOQUE (mesure, pas hypothese) : le cast MoW s'exerce parfaitement LIVE dans le runner
headless (`applyAction {kind:"ability", casterId=<machineId>}` -> cascade native complete ; sweep des
8 MoW du pool : 13 des 16 abilities castent sans erreur), mais `engine.runner.snapshot.load_state`
n'iterait QUE `decisionView.units` -> le caster MoW (qui vit dans `decisionView.mows`) n'existait PAS
dans l'etat offline. Consequence : AUCUN port d'ability MoW n'etait confrontable (chaque test devait
FABRIQUER un faux caster a la main, cf. l'ancien `_fabricate_caster` de test_spore_mine_launcher_live).

CE QUI EST PORTE : `_load_machines` / `_load_machine_stats` (snapshot.py) materialisent la MoW comme
entite ECS, mirror de `AddMachineOperation.Execute @180e4b5e0` (entite EntityType.Machine=6, liee a
ses `MachinePlatform` Type=7 par `MachinePlatformComponent.MachineId` Nullable@+0x14/+0x18, abilities
initialisees par `AddMachineOperation.InitializeAbilitiesStatus`). Jeu de composants MESURE live via
`dumpEntityComponents` sur l'entite Machine : Parent / EffectsOwned / TriggeredAbility / Owner /
Attack / CritChance / CritDamage / ActiveAbility / UnitFlags / ExtraHits / ExtraPierce(Ranged) /
ExtraMaxDamage / Machine / ActorStatistics -> **ni HealthComponent ni PositionComponent** (hors-plateau).

TROIS volets :
  * LOADER : la MoW EST dans `state.entities` (cle = casterId == machineId), avec Unit/Owner/
    TriggeredAbility/Stats, SANS Position ni Health, et level/mult == l'`AbilityState` live.
  * EXERCICE : une ability MoW DEJA PORTEE (SporeMineLauncher 1145, tyranBiovore) s'execute depuis le
    caster CHARGE (zero fabrication) et spawn sur l'equipe du caster.
  * CONFRONT LIVE : le meme cast natif produit le meme summon (equipe / tuile / hp).
  * GARDE anti-regression : `diff(snapshot_live, snapshot(state))` reste VIDE (la forme canonique
    reste symetrique) et aucune entite n'est ajoutee sur un runner SANS MoW.

Drive les positions ; lit l'etat LIVE ; state-file UNIQUE (chemin absolu + agent id) ; ASCII-only.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from engine.runner.components import (HealthComponent, OwnerComponent, PositionComponent,
                                      StatsComponent, TriggeredAbilityComponent, UnitComponent)
from engine.runner.snapshot import diff, load_state, snapshot, snapshot_live

AGENT_ID = "ad2ec6c90cf1a527c"
PYDIR = Path(__file__).resolve().parents[3]                        # scripts/python
ROOT = Path(__file__).resolve().parents[5]                         # racine repo
STATE = ROOT / "data" / f"_pytest_mowload_{AGENT_ID}.json"         # state-file UNIQUE
STATE_NOMOW = ROOT / "data" / f"_pytest_mownone_{AGENT_ID}.json"
STATE_GEN = ROOT / "data" / f"_pytest_mowgen_{AGENT_ID}.json"

CARRIER = "tyranBiovore"        # MoW du pool dont une ability (1145) est DEJA portee
SPORE = 1145
SUMMON_VID = "tyranSmnSporeMine"
BOARD = "C1_02"                 # board MoW-capable (slot MachineOfWarPosition des 2 cotes)
SEED = "4242"


def _build(state_path: Path, extra: list[str]):
    proc = subprocess.run(
        [sys.executable, "rl_duel.py", "build", "--seed", SEED, "--board", BOARD,
         "--p-units", "necroDestroyer,necroWarden", "--a-units", "necroDestroyer,necroWarden",
         "--state-file", str(state_path), *extra],
        cwd=str(PYDIR), capture_output=True, text=True, encoding="utf-8", errors="replace")
    if not state_path.exists():
        return None, (proc.stderr or proc.stdout or "")[-300:]
    return json.loads(state_path.read_text())["runnerId"], None


@pytest.fixture(scope="module")
def mow_runner(host, live_session):
    rid, err = _build(STATE, ["--p-mow", CARRIER])
    if rid is None:
        pytest.skip(f"build MoW {CARRIER} KO: {err}")

    def _rpc(m, b, t=90):
        r = host._rpc(live_session, m, [b], timeout=t)
        return r.get("result") if isinstance(r, dict) and "result" in r else r

    yield rid, _rpc
    try:
        host._rpc(live_session, "disposeRunner", [{"runnerId": rid}], timeout=20)
    except Exception:
        pass


def _load(rpc, rid):
    from engine.entities.pathfinding.board import Board
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    if not (isinstance(bg, dict) and bg.get("tiles")):
        pytest.skip("boardGraph indispo")
    board = Board(bg["tiles"], adjacency="evenq")
    dec = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    ob = rpc("observeBattle", {"runnerId": rid}, 40)
    snap = rpc("combatSnapshot", {"runnerId": rid}, 60)
    return load_state(dec, ob, snap, board=board), board, dec, ob


def _mow(dec):
    m = next((x for x in (dec.get("mows") or []) if x.get("visualId") == CARRIER), None)
    if m is None:
        pytest.skip(f"MoW {CARRIER} absente de decisionView.mows (non deployee)")
    return m


# ------------------------------------------------------------------ LOADER

def test_mow_caster_is_loaded_offline(mow_runner):
    """La MoW existe comme entite ECS offline, cle = casterId (== machineId, l'id qu'attend
    `applyAction`), avec le jeu de composants du natif : Unit(identite) / Owner / TriggeredAbility /
    Stats, et **NI Position NI Health** (hors-plateau, mesure `dumpEntityComponents`)."""
    rid, rpc = mow_runner
    state, _board, dec, _ob = _load(rpc, rid)
    m = _mow(dec)
    cid = m["casterId"]
    ent = state.get_entity(cid)
    assert ent is not None, (f"caster MoW {cid} ABSENT de l'etat offline "
                             f"(entities={sorted(state.entities)}) -> verrou non leve")
    uc = ent.get_component(UnitComponent)
    oc = ent.get_component(OwnerComponent)
    sc = ent.get_component(StatsComponent)
    print(f"\n[MOW/load] caster={cid} vis={uc.visual_id} team={oc.team} player={oc.player} "
          f"lvl={sc.ctx.active_ability_level} mult={sc.ctx.ability_variables_multiplier} "
          f"traits={sc.ctx.traits} pos={ent.get_component(PositionComponent)} "
          f"hp={ent.get_component(HealthComponent)}")
    assert uc is not None and uc.visual_id == CARRIER, "identite MoW absente/incorrecte"
    assert uc.alive is True, "MoW chargee morte"
    assert oc is not None and (oc.team, oc.player) == (m["team"], m["owner"]), \
        f"owner offline ({oc.team},{oc.player}) != live ({m['team']},{m['owner']})"
    assert ent.get_component(TriggeredAbilityComponent) is not None, \
        "TriggeredAbilityComponent absent (present sur l'entite Machine native)"
    assert ent.get_component(PositionComponent) is None, \
        "PositionComponent pose sur une MoW (le natif n'en a PAS : hors-plateau)"
    assert ent.get_component(HealthComponent) is None, \
        "HealthComponent pose sur une MoW (le natif n'en a PAS)"
    # level/mult = AbilityState per-ability live (indexe les variables config des abilities MoW)
    ab = next((a for a in (m.get("abilities") or []) if a.get("level") is not None), None)
    assert ab is not None, "aucune ability MoW ne porte d'AbilityState"
    assert sc is not None, "StatsComponent absent sur la MoW"
    assert sc.ctx.active_ability_level == ab["level"], \
        f"level offline {sc.ctx.active_ability_level} != AbilityState live {ab['level']}"
    assert sc.ctx.ability_variables_multiplier == ab["multiplier"], \
        f"mult offline {sc.ctx.ability_variables_multiplier} != live {ab['multiplier']}"
    assert "MachineOfWar" in (sc.ctx.traits or []), "trait MachineOfWar non porte"


def test_canonical_form_stays_symmetric(mow_runner):
    """GARDE : la forme canonique reste diffable — `snapshot(state)` (qui contient desormais la MoW)
    == `snapshot_live` (qui l'emet aussi). Un desequilibre casserait tout replay-diff MoW."""
    rid, rpc = mow_runner
    state, _board, dec, ob = _load(rpc, rid)
    d = diff(snapshot_live(dec, ob), snapshot(state))
    print(f"\n[MOW/diff] {d}")
    assert d == [], f"forme canonique desequilibree apres chargement MoW: {d}"


def test_no_mow_runner_unchanged(host, live_session):
    """GARDE zero-impact : sur un runner SANS MoW, l'etat charge ne contient QUE les unites de
    `decisionView.units` (aucune entite ajoutee par le nouveau chemin)."""
    rid, err = _build(STATE_NOMOW, [])
    if rid is None:
        pytest.skip(f"build sans MoW KO: {err}")

    def rpc(m, b, t=90):
        r = host._rpc(live_session, m, [b], timeout=t)
        return r.get("result") if isinstance(r, dict) and "result" in r else r

    try:
        state, _board, dec, ob = _load(rpc, rid)
        assert not (dec.get("mows") or []), "runner cense etre sans MoW"
        assert sorted(state.entities) == sorted(u["id"] for u in (dec.get("units") or [])), \
            "entites parasites sur un runner sans MoW"
        assert diff(snapshot_live(dec, ob), snapshot(state)) == []
    finally:
        try:
            host._rpc(live_session, "disposeRunner", [{"runnerId": rid}], timeout=20)
        except Exception:
            pass


# ------------------------------------------------------------------ EXERCICE + CONFRONT

def test_mow_ability_executes_from_loaded_caster(mow_runner):
    """PREUVE du debloqueur : une ability MoW DEJA PORTEE (SporeMineLauncher 1145) s'execute depuis le
    caster CHARGE PAR `load_state` (aucune fabrication), spawn sur l'equipe du caster ; et le cast
    natif de la MEME ability sur la MEME tuile produit le MEME summon (equipe / tuile / hp)."""
    from engine.entities.effects.magnitude import ability_var
    from engine.runner.operations.summon_ai import _apply_active_ability
    rid, rpc = mow_runner
    state, board, dec, ob = _load(rpc, rid)
    m = _mow(dec)
    cid = m["casterId"]
    ab = next((a for a in (m.get("abilities") or []) if a.get("id") == SPORE), None)
    if ab is None:
        pytest.skip("ability 1145 absente du kit MoW")
    exp_hp = int(ability_var("SporeMineLauncher", "summonHp", ab["level"],
                             multiplier_pct=ab["multiplier"]) or 0)

    # tuile-cible legale et LIBRE (cf. gate `GetDynamicInvalidTargetReason @18120a590`)
    at = rpc("abilityTargets", {"runnerId": rid, "unitId": cid, "abilityType": SPORE}, 90) or {}
    row = next((u for u in (at.get("units") or []) if u.get("unitId") == cid), None)
    tiles = [(t["tile"]["col"], t["tile"]["row"])
             for t in ((row.get("abilities") or [{}])[0].get("targets") or [])
             if t.get("kind") == "tile"] if row else []
    occ = {(u.get("col"), u.get("row")) for u in (ob.get("units") or []) if not u.get("isDead")}
    tile = next((t for t in tiles if t not in occ), None)
    if tile is None:
        pytest.skip("aucune tuile-cible libre pour 1145")

    # --- OFFLINE : caster = l'entite CHARGEE (pas de _fabricate_caster)
    before = set(state.entities)
    res = _apply_active_ability(state, cid, board.id_at(*tile), SPORE)
    diag = (res or {}).get("diag") or {}
    spawned = diag.get("spawned") or []
    print(f"\n[MOW/exec] caster={cid} tile={tile} routed={res.get('routed')} "
          f"spawned={spawned} exp_hp={exp_hp}")
    assert res.get("routed") == "handler" and diag.get("ported") is True, f"1145 non porte: {res}"
    assert len(spawned) == 1, f"offline a spawne {len(spawned)} != 1"
    off = state.get_entity(spawned[0])
    assert spawned[0] in (set(state.entities) - before)
    off_oc = off.get_component(OwnerComponent)
    off_pc = off.get_component(PositionComponent)
    off_hc = off.get_component(HealthComponent)
    assert off.get_component(UnitComponent).visual_id == SUMMON_VID
    assert (off_oc.team, off_oc.player) == (m["team"], m["owner"]), \
        f"summon offline owner ({off_oc.team},{off_oc.player}) != caster MoW"
    assert (off_pc.col, off_pc.row) == tile
    assert off_hc.hp == exp_hp

    # --- LIVE : meme cast natif, meme tuile
    before_ids = {u.get("squadId") for u in (ob.get("units") or [])}
    r = rpc("applyAction", {"runnerId": rid, "action": {
        "kind": "ability", "casterId": cid, "abilityType": SPORE,
        "to": {"col": tile[0], "row": tile[1]}}}, 90) or {}
    act = (r.get("actions") or [{}])[0]
    if act.get("error"):
        pytest.skip(f"cast natif bloque: {act.get('error')}")
    ob2 = rpc("observeBattle", {"runnerId": rid}, 40) or {}
    mines = [u for u in (ob2.get("units") or [])
             if u.get("visualId") == SUMMON_VID and u.get("squadId") not in before_ids
             and not u.get("isDead")]
    print(f"[MOW/live] mines={[(x.get('squadId'), x.get('teamId'), x.get('playerId'), x.get('hp'), (x.get('col'), x.get('row'))) for x in mines]}")
    assert len(mines) == 1, f"live a spawne {len(mines)} != 1"
    lm = mines[0]
    assert (lm.get("teamId"), lm.get("playerId")) == (off_oc.team, off_oc.player), \
        "owner live != owner offline"
    assert (lm.get("col"), lm.get("row")) == (off_pc.col, off_pc.row), "tuile live != offline"
    assert lm.get("hp") == off_hc.hp, f"hp live {lm.get('hp')} != offline {off_hc.hp}"


# ------------------------------------------------------------------ GENERALISATION

GEN_P_MOW = "tauBroadside"        # HeavyRailRifle (1160) pose un effet SUR LA MoW elle-meme
GEN_A_MOW = "blackForgefiend"     # 2e MoW, camp ADVERSE, autre faction
GEN_BOARD = "C2_02"               # AUTRE board MoW-capable
HEAVY_RAIL_RIFLE = 1160


@pytest.fixture(scope="module")
def two_mow_runner(host, live_session):
    """Runner de GENERALISATION : DEUX MoW (une par camp), AUTRE board, AUTRES porteurs."""
    proc = subprocess.run(
        [sys.executable, "rl_duel.py", "build", "--seed", "31337", "--board", GEN_BOARD,
         "--p-units", "necroDestroyer,necroWarden", "--a-units", "necroDestroyer,necroWarden",
         "--p-mow", GEN_P_MOW, "--a-mow", GEN_A_MOW, "--state-file", str(STATE_GEN)],
        cwd=str(PYDIR), capture_output=True, text=True, encoding="utf-8", errors="replace")
    if not STATE_GEN.exists():
        pytest.skip(f"build 2 MoW KO: {(proc.stderr or proc.stdout or '')[-300:]}")
    rid = json.loads(STATE_GEN.read_text())["runnerId"]

    def _rpc(m, b, t=90):
        r = host._rpc(live_session, m, [b], timeout=t)
        return r.get("result") if isinstance(r, dict) and "result" in r else r

    yield rid, _rpc
    try:
        host._rpc(live_session, "disposeRunner", [{"runnerId": rid}], timeout=20)
    except Exception:
        pass


def test_both_camps_mow_loaded(two_mow_runner):
    """GENERALISATION : DEUX MoW (une par camp), autre board, autres porteurs -> les DEUX sont
    chargees, avec la BONNE team/player, et la forme canonique reste equilibree."""
    rid, rpc = two_mow_runner
    state, _board, dec, ob = _load(rpc, rid)
    mows = dec.get("mows") or []
    print(f"\n[MOW/gen] mows={[(m['casterId'], m['visualId'], m['team'], m['slot']) for m in mows]}")
    assert len(mows) == 2, f"attendu 2 MoW deployees, vu {len(mows)}"
    teams = set()
    for m in mows:
        ent = state.get_entity(m["casterId"])
        assert ent is not None, f"MoW {m['visualId']} (caster {m['casterId']}) absente offline"
        oc = ent.get_component(OwnerComponent)
        assert (oc.team, oc.player) == (m["team"], m["owner"])
        assert ent.get_component(UnitComponent).visual_id == m["visualId"]
        assert ent.get_component(PositionComponent) is None
        teams.add(oc.team)
    assert teams == {1, 2}, f"les 2 MoW devraient etre sur des camps opposes, vu {teams}"
    assert diff(snapshot_live(dec, ob), snapshot(state)) == []


def test_effect_posed_on_mow_is_loaded(two_mow_runner):
    """GENERALISATION la plus DISCRIMINANTE : plusieurs abilities MoW sont 2-PHASES et posent leur
    etat d'attente SUR LA MoW (mesure : `HeavyRailRifle` -> `HeavyRailRifle_PendingAttack` sur
    l'entite Machine). Apres le cast LIVE, l'effet doit apparaitre sur l'entite MoW CHARGEE, en NOMS
    (`EffectsOwnedComponent`) ET en STRUCTURE (`State.effects`) — sans quoi aucun port 2-phases MoW
    n'est confrontable. AVANT le fix, ce cas etait invisible offline (aucune entite MoW)."""
    rid, rpc = two_mow_runner
    state0, _b, dec0, _ob0 = _load(rpc, rid)
    m = next((x for x in (dec0.get("mows") or []) if x.get("visualId") == GEN_P_MOW), None)
    if m is None:
        pytest.skip(f"MoW {GEN_P_MOW} absente")
    cid = m["casterId"]
    ent0 = state0.get_entity(cid)
    from engine.runner.components import EffectsOwnedComponent
    before = list((ent0.get_component(EffectsOwnedComponent) or EffectsOwnedComponent([])).effects)

    at = rpc("abilityTargets",
             {"runnerId": rid, "unitId": cid, "abilityType": HEAVY_RAIL_RIFLE}, 90) or {}
    row = next((u for u in (at.get("units") or []) if u.get("unitId") == cid), None)
    tgt = next((t for t in ((row.get("abilities") or [{}])[0].get("targets") or [])
                if t.get("kind") == "unit"), None) if row else None
    if tgt is None:
        pytest.skip("aucune cible legale pour HeavyRailRifle")
    r = rpc("applyAction", {"runnerId": rid, "action": {
        "kind": "ability", "casterId": cid, "abilityType": HEAVY_RAIL_RIFLE,
        "targetId": tgt["targetId"]}}, 90) or {}
    act = (r.get("actions") or [{}])[0]
    if act.get("error"):
        pytest.skip(f"cast HeavyRailRifle bloque: {act.get('error')}")

    state1, _b1, dec1, ob1 = _load(rpc, rid)
    ent1 = state1.get_entity(cid)
    assert ent1 is not None, "MoW disparue apres le cast"
    eff = ent1.get_component(EffectsOwnedComponent)
    names = list(eff.effects) if eff is not None else []
    print(f"\n[MOW/effect] caster={cid} effets AVANT={before} APRES={names}")
    assert names != before and names, \
        f"aucun effet capte sur la MoW apres le cast 2-phases (avant={before}, apres={names})"
    assert state1.effects is not None and state1.effects.by_unit.get(int(cid)), \
        "l'effet de la MoW n'est pas materialise dans State.effects (seed EffectsState)"
    assert diff(snapshot_live(dec1, ob1), snapshot(state1)) == []
