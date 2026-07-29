"""WIRING TRIGGER + ON-APPEARANCE du summon — `Runner.apply(ActiveAbilityMessage)` → spawn + attaque.

Valide que le cast d'une ability de summon (ici `ScarabHive`, ActiveAbilityType **1007**) route bien par
`AbilityHandler` → `ScarabHiveAbility.execute_behaviour` → `SpawnUnitOperation` (2× necroSmnSwarm, owner
du caster, adjacents à la cible, stats `ability_var`) PUIS l'**attaque on-appearance** (`UseNormalAttackIfAble`,
profil Piercing) qui ampute les PV de la cible.

État seedé depuis un build live (positions/stats réelles) ; on applique le message OFFLINE. Le spawn
est déjà validé bit-exact ailleurs (test_summon_spawn_live) ; ICI on valide le WIRING message +
l'on-appearance (dégât appliqué). Le dégât on-appearance BIT-EXACT (RNG calé sur le cast live) =
raffinement non testé ici.

⚠ #250 — LA PRÉMISSE « le runner n'a pas de gate de portée » N'EST PLUS VRAIE. `ScarabHive` porte
depuis lors ses `TARGETING_OPTIONS` (`TargetHasFreeAdjacentTile | TargetIsEnemy`, `RANGE_ADJACENT`),
donc `AbilityHandler` refuse le cast sur une cible hors CONTACT — exactement comme
`IdunBattle.Operations.ActiveAbilityOperation$$IsInvalidTarget`. Aux positions de SPAWN le
necroSpyder est à 8+ hex de sa cible : le message était donc appliqué sur une géométrie que le natif
REFUSE, et le test ne le voyait pas. On DRIVE désormais le caster (`_summon_montage.
drive_until_castable`, qui s'arrête quand le NATIF publie la cible via `abilityTargets`) avant de
figer l'état — la géométrie est forcée, pas subie.

⚠ ADJACENCE = mode **evenq**.
"""
from __future__ import annotations

import os
import sys

import pytest

import hexgeo

sys.path.insert(0, os.path.dirname(__file__))      # tests/engine/runner -> import du helper sibling

from _summon_montage import board_of                                       # noqa: E402

from engine.runner.snapshot import load_state
from engine.runner.runner import Runner
from engine.runner.messages import ActiveAbilityMessage
from engine.runner.prng import IntBasedMersenneTwister
from engine.runner.components import (StatsComponent, OwnerComponent, PositionComponent,
                                      HealthComponent, UnitComponent)

CASTER_VIS = "necroSpyder"
# #250 : ENNEMI change de `necroDestroyer` a `necroWarden`. Le Destroyer porte `Overwatch_AutoAttack`
# et abattait le necroSpyder PENDANT l'approche imposee par le nouveau gate `RANGE_ADJACENT` (le
# drive skippait alors sur « caster absent »). L'ennemi n'est qu'une CIBLE ici -- le test valide le
# wiring du message et l'on-appearance, pas le kit de la cible.
ENEMY_VIS = "necroWarden"
SUMMON_VIS = "necroSmnSwarm"
SCARABHIVE = 1007
# `--no-ai` (#250) : le drive rapproche le necroSpyder du necroDestroyer, et l'IA native le tuait
# pendant le tour adverse -> `drive_until_castable` skippait sur « caster absent ». Le test fige un
# etat, il n'a besoin d'aucun tour joue par l'IA.
BUILD = ["--roster", "1", "--no-ai", "--p-units", CASTER_VIS, "--a-units", ENEMY_VIS]


def _ok(r):
    return isinstance(r, dict) and r.get("ok")


def _upos(u):
    p = u.get("pos") or {}
    return (p.get("col"), p.get("row"))


def _free_around(board, dv, tile_id, occupied):
    """Tuiles voisines de `tile_id` marchables et LIBRES — le `CanAddUnit(AdjacentTiles(target))` que
    `SpawnUnitBehaviour$$Execute` enumere pour poser les deux necroSmnSwarm."""
    return [n for n in board.neighbours(tile_id)
            if board.walkable(n) and board.coord(n) not in occupied]


def _drive_adjacent_with_room(rpc, rid, board, caster_vis, enemy_vis, need=2, tries=16):
    """DRIVE la geometrie EXACTE dont ce test a besoin, et pas seulement « castable » (#250) :

      * le caster doit etre AU CONTACT de sa cible -- sinon le gate `RANGE_ADJACENT` pose sur 1007
        refuse le message et rien ne mute ;
      * la cible doit garder **au moins `need` tuiles libres au contact** -- le spawn en pose une par
        tuile disponible, et le caster qui vient au contact en CONSOMME une. Mesure : caster (5,8),
        cible (6,8) au bord du plateau -> 1 seule tuile libre -> 1 seul summon, la ou le test en
        attend 2. C'est une contrainte de MONTAGE, pas un ecart de port.

    Rend `(caster_live, enemy_live)`. Skip si la geometrie n'est pas atteinte."""
    for _ in range(tries):
        dv = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
        c = next((u for u in (dv.get("units") or []) if u.get("visualId") == caster_vis), None)
        e = next((u for u in (dv.get("units") or []) if u.get("visualId") == enemy_vis), None)
        if c is None or e is None:
            pytest.skip(f"{caster_vis}/{enemy_vis} absent")
        cp, ep = _upos(c), _upos(e)
        if cp[0] is None or ep[0] is None:
            pytest.skip("positions absentes")
        et = board.id_at(*ep)
        if dv.get("currentPlayer") != c.get("owner"):
            # TOUR ADVERSE (runner `--no-ai` : personne ne bouge tout seul) -> on en profite pour
            # amener la CIBLE en terrain OUVERT. Au bord du plateau elle n'a pas 2 voisines libres,
            # et aucune position du caster ne peut y remedier : c'est la cible qu'il faut deplacer.
            occ = {_upos(u) for u in (dv.get("units") or []) if u.get("alive")}
            if len(_free_around(board, dv, et, occ)) < need + 1:
                mov = rpc("aiMovableTiles", {"runnerId": rid}, 60)
                me = next((m for m in (mov.get("units") or []) if m.get("unitId") == e["id"]), None)
                ts = [(t["col"], t["row"]) for t in ((me or {}).get("tiles") or [])
                      if t.get("col") is not None]
                if ts:
                    best_e = max(ts, key=lambda t: (len(_free_around(
                        board, dv, board.id_at(*t), (occ - {ep}) | {t})), -hexgeo.distance(t, cp)))
                    rpc("applyAction", {"runnerId": rid, "action": {
                        "kind": "move", "unitId": e["id"],
                        "to": {"col": best_e[0], "row": best_e[1]}}}, 60)
            rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
            continue
        occupied = {_upos(u) for u in (dv.get("units") or []) if u.get("alive")}
        if hexgeo.distance(cp, ep) == 1 and len(_free_around(board, dv, et, occupied)) >= need:
            return c, e
        mov = rpc("aiMovableTiles", {"runnerId": rid}, 60)
        mu = next((m for m in (mov.get("units") or []) if m.get("unitId") == c["id"]), None)
        tiles = [(t["col"], t["row"]) for t in ((mu or {}).get("tiles") or [])
                 if t.get("col") is not None]
        # 1) une tuile AU CONTACT qui laisse assez de place autour de la cible
        best = next((t for t in tiles
                     if hexgeo.distance(t, ep) == 1
                     and len(_free_around(board, dv, et, (occupied - {cp}) | {t})) >= need), None)
        # 2) a defaut, se RAPPROCHER strictement
        if best is None and tiles:
            cand = min(tiles, key=lambda t: (hexgeo.distance(t, ep), t))
            best = cand if hexgeo.distance(cand, ep) < hexgeo.distance(cp, ep) else None
        if best is None:
            rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
            continue
        rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "move", "unitId": c["id"], "to": {"col": best[0], "row": best[1]}}}, 60)
    pytest.skip(f"{caster_vis} : geometrie contact + {need} tuiles libres non atteinte")


def _seed_rng(s):
    rng = IntBasedMersenneTwister()
    rng.mt = list(s["mt"]); rng.mti = s["mti"]
    return rng


def test_summon_trigger_and_on_appearance(live_session, rpc, build_runner):
    rid = build_runner("777", extra=BUILD)["rid"]
    board = board_of(rpc, rid)                       # adjacency="evenq", meme convention qu'avant
    # DRIVE la geometrie jusqu'a ce que le NATIF publie la cible pour 1007 (`abilityTargets`) : sans
    # ca le cast est refuse par le gate `RANGE_ADJACENT` pose en #250, et le message ne mute rien.
    _drive_adjacent_with_room(rpc, rid, board, CASTER_VIS, ENEMY_VIS, need=2)

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
    cpos = state.get_entity(caster_id).get_component(PositionComponent)
    epos = state.get_entity(enemy_id).get_component(PositionComponent)
    print(f"\n[SUMMON-TRIG] ported={diag.get('ported')} spawned={diag.get('spawned')} "
          f"attacks={diag.get('attacks')} | new swarms={len(swarms)}")
    print(f"[SUMMON-TRIG] caster=({cpos.col},{cpos.row}) cible=({epos.col},{epos.row}) "
          f"summons={[(i, getattr(state.get_entity(i).get_component(PositionComponent), 'col', None), getattr(state.get_entity(i).get_component(PositionComponent), 'row', None)) for i in swarms]}")
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
    # OVERKILL (#250) : les PV sont CLAMPES a 0, donc la somme brute des degats peut DEPASSER les PV
    # perdus. L'egalite stricte n'etait vraie que tant que le montage laissait la cible survivre --
    # elle survivait par la seule variance des jets, pas par construction. L'invariant exact est
    # `PV perdus == min(somme des degats, PV avant)`.
    attendu = min(total_attacks, hp_before)
    assert (hp_before - hp_after) == attendu, \
        f"PV perdus {hp_before - hp_after} != min(somme attaques {total_attacks}, PV {hp_before})"
