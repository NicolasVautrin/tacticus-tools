"""WIRING TRIGGER + ON-APPEARANCE du summon — `Runner.apply(ActiveAbilityMessage)` → spawn + attaque.

Valide que le cast d'une ability de summon (ici `ScarabHive`, ActiveAbilityType **1007**) route bien par
`AbilityHandler` → `ScarabHiveAbility.execute_behaviour` → `SpawnUnitOperation` (2× necroSmnSwarm, owner
du caster, adjacents à la cible, stats `ability_var`) PUIS l'**attaque on-appearance** (`UseNormalAttackIfAble`,
profil Piercing) qui ampute les PV de la cible.

État seedé depuis un build live (positions/stats réelles) ; on applique le message OFFLINE (le runner
n'a pas de gate de portée — c'est l'IA/légalité qui l'aurait, hors scope). Le spawn est déjà validé
bit-exact ailleurs (test_summon_spawn_live) ; ICI on valide le WIRING message + l'on-appearance (dégât
appliqué). Le dégât on-appearance BIT-EXACT (RNG calé sur le cast live) = raffinement non testé ici.

⚠ ADJACENCE = mode **evenq**.
"""
from __future__ import annotations

import pytest

from engine.runner.snapshot import load_state
from engine.runner.runner import Runner
from engine.runner.messages import ActiveAbilityMessage
from engine.runner.prng import IntBasedMersenneTwister
from engine.runner.components import (StatsComponent, OwnerComponent, PositionComponent,
                                      HealthComponent, UnitComponent)

CASTER_VIS = "necroSpyder"
ENEMY_VIS = "necroDestroyer"
SUMMON_VIS = "necroSmnSwarm"
SCARABHIVE = 1007
BUILD = ["--roster", "1", "--p-units", CASTER_VIS, "--a-units", ENEMY_VIS]


def _ok(r):
    return isinstance(r, dict) and r.get("ok")


def _seed_rng(s):
    rng = IntBasedMersenneTwister()
    rng.mt = list(s["mt"]); rng.mti = s["mti"]
    return rng


def test_summon_trigger_and_on_appearance(live_session, rpc, build_runner):
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

    state = load_state(dec, ob, snap, board=board)
    state.rng = _seed_rng(s0)
    if state.get_entity(caster_id) is None or state.get_entity(enemy_id) is None:
        pytest.skip("caster/cible absents offline")

    # entites AVANT (pour isoler les summons spawnes) + PV cible avant.
    before_ids = set(state.entities.keys())
    thc = state.get_entity(enemy_id).get_component(HealthComponent)
    hp_before = thc.hp if thc is not None else None

    # === apply le cast (wiring AbilityHandler -> ScarabHiveAbility, id 1007) ===
    runner = Runner(state).install_default_handlers(20)
    runner.apply(ActiveAbilityMessage(caster_id, enemy_id, SCARABHIVE))
    diag = runner.ability_handler.last or {}

    # === spawn ===
    new_ids = [i for i in state.entities.keys() if i not in before_ids]
    swarms = [i for i in new_ids
              if (state.get_entity(i).get_component(UnitComponent) or UnitComponent(None, False)).visual_id == SUMMON_VIS]
    print(f"\n[SUMMON-TRIG] ported={diag.get('ported')} spawned={diag.get('spawned')} "
          f"attacks={diag.get('attacks')} | new swarms={len(swarms)}")
    assert diag.get("ported") is True, f"ActiveAbilityMessage 1007 non route (last={diag})"
    assert len(swarms) == 2, f"{len(swarms)} necroSmnSwarm spawnes (attendu 2)"

    et = board.id_at(state.get_entity(enemy_id).get_component(PositionComponent).col,
                     state.get_entity(enemy_id).get_component(PositionComponent).row)
    enemy_neigh = set(board.neighbours(et))
    for sid in swarms:
        e = state.get_entity(sid)
        oc = e.get_component(OwnerComponent)
        sc = e.get_component(StatsComponent)
        pc = e.get_component(PositionComponent)
        assert oc.team == my_team and oc.player == my_player, \
            f"summon owner (team={oc.team},player={oc.player}) != caster ({my_team},{my_player})"
        assert sc is not None and sc.ctx.health == 2218, f"summon hp {sc and sc.ctx.health} != 2218"
        assert pc is not None and board.id_at(pc.col, pc.row) in enemy_neigh, \
            "summon PAS adjacent (evenq) a la cible"

    # === on-appearance : la cible a perdu des PV (attaque immediate des summons) ===
    hp_after = state.get_entity(enemy_id).get_component(HealthComponent).hp
    print(f"[SUMMON-TRIG] cible hp {hp_before} -> {hp_after} (on-appearance dmg={hp_before - hp_after})")
    assert hp_after < hp_before, "l'attaque on-appearance n'a pas ampute les PV de la cible"
    total_attacks = sum((a.get("total") or 0) for a in (diag.get("attacks") or []))
    assert total_attacks == (hp_before - hp_after), \
        f"somme attaques on-appearance {total_attacks} != PV perdus {hp_before - hp_after}"
