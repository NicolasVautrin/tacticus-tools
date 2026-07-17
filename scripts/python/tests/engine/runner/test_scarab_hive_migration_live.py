"""#149 slice-10 : ScarabHive (1007) MIGRATION vers l'arbre DSL -- la behaviour EST `scarab_hive_tree()`.

`ScarabHiveAbility.ExecuteBehaviour @181204cb0` (DECOMPILE) = un noeud `Spawn` UNIQUE (plain `Execute`) :
    Execute( Spawn(caster@0x160, tileSel, unitId=necroSmnSwarm,
                   SpawnUnitOptions.WithStatsFromConfig(config)
                     .effect       = AddEffect(0x4a3 ScarabHive_OverrideDamageProfile, target@0x178)
                     .onAppearance = UseNormalAttackIfAble(target@0x178)) )
`SpawnUnitBehaviour.Execute @180fd3d80` spawn COUNT(2) summons -- count/placement/WithStatsFromConfig vivent
DANS SpawnUnitBehaviour (GetUnitToSpawn/GetTileIds), HORS DSL-selecteurs (`First`=PickAtIndex=1 elt) -- puis
`TriggerSpawnedUnitBehaviours` fire les 2 sous-behaviours par summon.

Le port (feuille `SpawnSummon`) delegue le SPAWN a l'Operation VALIDEE LIVE-BIT-EXACT `SpawnUnitOperation.
execute` (cf. test_summon_spawn_live) puis l'on-appearance `UseNormalAttackIfAble` = `_summon_on_appearance_
attack` (profil Piercing). ICI on valide que la MIGRATION prend bien le chemin DSL (`dsl:True`) et reproduit
la structure attendue : 2 necroSmnSwarm spawnes owner du caster, l'attaque on-appearance ampute la cible, et
`sum(attacks.total) == PV perdus`. (Le spawn bit-exact + le wiring message sont deja couverts par
test_summon_spawn_live / test_summon_trigger_live.) Lit l'etat LIVE. ASCII-only.
"""
from __future__ import annotations

import pytest

from engine.runner.snapshot import load_state
from engine.runner.prng import IntBasedMersenneTwister
from engine.runner.components import HealthComponent, PositionComponent, OwnerComponent, UnitComponent
from engine.runner.abilities.loki import ScarabHiveAbility

CASTER_VIS = "necroSpyder"
ENEMY_VIS = "necroDestroyer"
SUMMON_VIS = "necroSmnSwarm"
BUILD = ["--roster", "1", "--p-units", CASTER_VIS, "--a-units", ENEMY_VIS]


def _ok(r):
    return isinstance(r, dict) and r.get("ok")


def _seed_rng(s):
    rng = IntBasedMersenneTwister()
    rng.mt = list(s["mt"]); rng.mti = s["mti"]
    return rng


def test_scarab_hive_migration_is_dsl_tree(live_session, rpc, build_runner):
    """`ScarabHiveAbility.execute_behaviour` prend le chemin DSL (`scarab_hive_tree`) : 2 spawns + on-appearance
    qui ampute la cible, sum(attacks) == PV perdus."""
    from engine.entities.pathfinding.board import Board
    rid = build_runner("777", extra=BUILD)["rid"]
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    if not (isinstance(bg, dict) and bg.get("tiles")):
        pytest.skip("boardGraph indispo")
    board = Board(bg["tiles"], adjacency="evenq")

    dec = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    ob = rpc("observeBattle", {"runnerId": rid}, 40)
    snap = rpc("combatSnapshot", {"runnerId": rid}, 60)
    s0 = rpc("dumpRng", {"runnerId": rid}, 30)
    caster = next((u for u in (dec.get("units") or []) if u.get("visualId") == CASTER_VIS), None)
    enemy = next((u for u in (dec.get("units") or []) if u.get("visualId") == ENEMY_VIS), None)
    if caster is None or enemy is None or not _ok(s0):
        pytest.skip("caster/cible/rng absent")
    caster_id, enemy_id = caster["id"], enemy["id"]
    my_team, my_player = caster.get("team"), caster.get("owner")

    state = load_state(dec, ob, snap)
    state.board = board
    state.rng = _seed_rng(s0)
    if state.get_entity(caster_id) is None or state.get_entity(enemy_id) is None:
        pytest.skip("caster/cible absents offline")

    before_ids = set(state.entities.keys())
    hp_before = state.get_entity(enemy_id).get_component(HealthComponent).hp

    # === chemin DSL migre (appel DIRECT de la classe d'ability) ===
    res = ScarabHiveAbility().execute_behaviour(state, caster_id, enemy_id)
    print(f"\n[SCARAB migration] dsl={res.get('dsl')} spawned={res.get('spawned')} attacks={res.get('attacks')}")

    assert res is not None and res.get("dsl") is True, f"arbre DSL non pris: {res}"
    spawned = res.get("spawned") or []
    assert len(spawned) == 2, f"{len(spawned)} necroSmnSwarm spawnes (attendu 2)"

    # les spawns sont bien de NOUVELLES entites necroSmnSwarm, owner du caster, adjacentes a la cible
    new_ids = [i for i in state.entities.keys() if i not in before_ids]
    assert set(spawned) == set(new_ids), f"spawned {sorted(spawned)} != nouvelles entites {sorted(new_ids)}"
    epc = state.get_entity(enemy_id).get_component(PositionComponent)
    enemy_neigh = set(board.neighbours(board.id_at(epc.col, epc.row)))
    for sid in spawned:
        e = state.get_entity(sid)
        oc = e.get_component(OwnerComponent)
        uc = e.get_component(UnitComponent)
        pc = e.get_component(PositionComponent)
        assert uc is not None and uc.visual_id == SUMMON_VIS, f"spawn {sid} n'est pas un {SUMMON_VIS}"
        assert oc.team == my_team and oc.player == my_player, "summon owner != caster (CopyOwner)"
        assert pc is not None and board.id_at(pc.col, pc.row) in enemy_neigh, "summon PAS adjacent a la cible"

    # === on-appearance : la cible perd des PV, sum(attacks.total) == PV perdus ===
    hp_after = state.get_entity(enemy_id).get_component(HealthComponent).hp
    attacks = res.get("attacks") or []
    total = sum((a.get("total") or 0) for a in attacks)
    print(f"[SCARAB migration] cible hp {hp_before} -> {hp_after} (on-appearance total={total})")
    assert attacks, "aucune attaque on-appearance emise"
    assert hp_after < hp_before, "l'attaque on-appearance n'a pas ampute la cible"
    assert total == (hp_before - hp_after), f"sum(attacks) {total} != PV perdus {hp_before - hp_after}"
