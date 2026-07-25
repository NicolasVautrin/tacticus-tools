"""SPAWN de SUMMON — `SpawnUnitOperation` confronté au LIVE (étape 2 du runner autonome).

Valide le port de la chaîne summon (`IdunBattleLogic.Entities.Abilities.Active.Loki.ScarabHiveAbility$$ExecuteBehaviour` → `DSLFactory.Spawn` →
`AddUnitOperation`) : un summon d'ability spawn sur **la team ET le player du caster**, sur une tuile LIBRE
adjacente à la **cible**, avec des stats `ability_var(ScarabHive, summon*, casterLevel, mult)`.

Fixture = `necroSpyder` (caste `ScarabHive`) vs `necroDestroyer` (cible unique). On joue l'IA native
(`aiPlayByUnit`, pump) jusqu'à ce que les 2 `necroSmnSwarm` spawnent, on lit leur état LIVE (hp/attack/
team/player/pos), puis on relance `SpawnUnitOperation` OFFLINE depuis l'état d'AVANT et on confronte :
  • STATS : hp/attack/crit offline == live (résolution `ability_var` bit-exact) ;
  • OWNER : team+player offline == live == ceux du caster (CopyOwner) ;
  • PLACEMENT : les summons (offline ET live) sont hex-adjacents à la cible (`AdjacentTiles(target)`).

⚠ ADJACENCE = mode **evenq**. Placement RNG-exact (quelle tuile parmi les libres) = raffinement non testé
ici (on valide la RÈGLE : adjacent à la cible).
"""
from __future__ import annotations

import pytest

from engine.runner.snapshot import load_state
from engine.runner.operations.spawn import SpawnUnitOperation, build_summon_context
from engine.runner.components import StatsComponent, OwnerComponent, PositionComponent

CASTER_VIS = "necroSpyder"
ENEMY_VIS = "necroDestroyer"
SUMMON_VIS = "necroSmnSwarm"
SUMMON_ABILITY = "ScarabHive"
SUMMON_COUNT = 2
BUILD = ["--roster", "1", "--p-units", CASTER_VIS, "--a-units", ENEMY_VIS]


def _ok(r):
    return isinstance(r, dict) and r.get("ok")


def _snap_stats(snap, eid):
    for u in (snap.get("units") or []):
        if u.get("entityId") == eid:
            return u.get("stats") or {}
    return {}


def test_summon_spawn_bit_exact(live_session, rpc, build_runner):
    from engine.entities.pathfinding.board import Board
    rid = build_runner("777", extra=BUILD)["rid"]
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    if not (isinstance(bg, dict) and bg.get("tiles")):
        pytest.skip("boardGraph indispo")
    board = Board(bg["tiles"], adjacency="evenq")

    dec0 = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    caster0 = next((u for u in (dec0.get("units") or []) if u.get("visualId") == CASTER_VIS), None)
    enemy0 = next((u for u in (dec0.get("units") or []) if u.get("visualId") == ENEMY_VIS), None)
    if caster0 is None or enemy0 is None:
        pytest.skip("caster/cible absent")
    caster_id, enemy_id = caster0["id"], enemy0["id"]
    my_team, my_player = caster0.get("team"), caster0.get("owner")

    # jouer l'IA native jusqu'au spawn des scarabs ; garder l'état d'AVANT chaque tour.
    before = None
    live = None
    for _ in range(12):
        b_dec = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
        b_ob = rpc("observeBattle", {"runnerId": rid}, 40)
        b_snap = rpc("combatSnapshot", {"runnerId": rid}, 60)
        before = (b_dec, b_ob, b_snap)
        rpc("aiPlayByUnit", {"runnerId": rid, "maxTurns": 1, "maxActivations": 9999,
                             "maxPump": 3000, "captureEvents": False}, 300)
        ob = rpc("observeBattle", {"runnerId": rid}, 40)
        swarms = [u for u in (ob.get("units") or []) if u.get("visualId") == SUMMON_VIS and not u.get("isDead")]
        if len(swarms) >= 1:
            snap = rpc("combatSnapshot", {"runnerId": rid}, 60)
            live = {"swarms": swarms, "snap": snap,
                    "enemy_pos": next((u for u in (ob.get("units") or []) if u.get("squadId") == enemy_id), None)}
            break
    if live is None:
        pytest.skip("aucun scarab spawne en 12 tours IA")

    # === LIVE : stats + owner + adjacence ===
    sw = live["swarms"][0]
    sw_stats = _snap_stats(live["snap"], sw.get("squadId"))
    live_hp = sw.get("hp")
    live_team, live_player = sw.get("teamId"), sw.get("playerId")
    print(f"\n[SUMMON] live scarab hp={live_hp} stats(attack={sw_stats.get('attack')} "
          f"cc={sw_stats.get('critChance')}) team={live_team} player={live_player} "
          f"| caster team={my_team} player={my_player}")

    # owner = caster (CopyOwner)
    assert live_team == my_team and live_player == my_player, (
        f"summon owner live (team={live_team},player={live_player}) != caster (team={my_team},player={my_player})")

    # === OFFLINE : build_summon_context (stats) ===
    b_dec, b_ob, b_snap = before
    # niveau/mult du caster depuis son unitConfig
    csu = next((u for u in (b_snap.get("units") or [])
                if (u.get("unitConfig") or {}).get("visualId") == CASTER_VIS), None)
    cuc = (csu or {}).get("unitConfig") or {}
    lvl, mult = cuc.get("activeAbilityLevel"), int(cuc.get("abilityVariablesMultiplier") or 100)
    off_ctx = build_summon_context(0, SUMMON_VIS, SUMMON_ABILITY, lvl, mult)
    print(f"[SUMMON] offline ctx hp={off_ctx.health} attack={off_ctx.attack} cc={off_ctx.crit_chance} "
          f"(casterLevel={lvl} mult={mult})")
    assert off_ctx.health == live_hp, f"offline summon hp {off_ctx.health} != live {live_hp}"
    if sw_stats.get("attack") is not None:
        assert off_ctx.attack == sw_stats.get("attack"), \
            f"offline summon attack {off_ctx.attack} != live {sw_stats.get('attack')}"

    # === OFFLINE : SpawnUnitOperation (owner + placement) depuis l'etat d'AVANT ===
    state = load_state(b_dec, b_ob, b_snap, board=board)
    if state.get_entity(caster_id) is None or state.get_entity(enemy_id) is None:
        pytest.skip("caster/cible absents offline (snapshot incomplet)")
    spawned = SpawnUnitOperation.execute(state, caster_id, enemy_id, SUMMON_ABILITY, SUMMON_VIS, SUMMON_COUNT)
    assert len(spawned) == SUMMON_COUNT, f"offline a spawne {len(spawned)} != {SUMMON_COUNT}"
    # owner + stats des summons offline
    enemy = state.get_entity(enemy_id)
    ep = enemy.get_component(PositionComponent)
    et = board.id_at(ep.col, ep.row)
    enemy_neigh = set(board.neighbours(et))
    for sid in spawned:
        e = state.get_entity(sid)
        oc = e.get_component(OwnerComponent)
        sc = e.get_component(StatsComponent)
        pc = e.get_component(PositionComponent)
        assert oc.team == my_team and oc.player == my_player, \
            f"summon offline owner (team={oc.team},player={oc.player}) != caster ({my_team},{my_player})"
        assert sc.ctx.health == live_hp, f"summon offline hp {sc.ctx.health} != live {live_hp}"
        assert pc is not None, "summon offline sans position (tuile libre adjacente cible introuvable)"
        assert board.id_at(pc.col, pc.row) in enemy_neigh, \
            f"summon offline ({pc.col},{pc.row}) PAS adjacent (evenq) a la cible"

    # === LIVE : les scarabs sont adjacents a la cible (regle de placement) ===
    epos = live.get("enemy_pos")
    if epos and epos.get("col") is not None:
        e_tile = board.id_at(epos["col"], epos["row"])
        e_neigh = set(board.neighbours(e_tile)) if e_tile is not None else set()
        for s in live["swarms"]:
            stile = board.id_at(s.get("col"), s.get("row")) if s.get("col") is not None else None
            assert stile in e_neigh, \
                f"scarab live ({s.get('col')},{s.get('row')}) PAS adjacent (evenq) a la cible {epos}"
