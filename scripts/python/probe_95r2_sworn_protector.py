"""Probe #95-RESTE2 — chaine OFFLINE `SwornProtector` -> Kell -> `ListenUpMaggots` ->
`GetAbilityStatModification` non nul -> SupremeCommander a 3 gardes / range 3.

Monte un `State` minimal (Creed + 1 ennemi adjacent, board du runner), emet le vecteur
`On(PreUnitAbility)` que la voie d'attaque normale emet nativement, et verifie chaque etage :

  1. Kell apparait (enfant de Creed) et a switche de position avec lui ;
  2. Kell porte `ListenUpMaggotsEffect` ;
  3. Creed porte les DEUX modifications d'ability (`0x16 -> +3`, `0x10 -> +1`) ;
  4. `SupremeCommanderAbility.execute_behaviour` rend `count=3` et `radius=3` ;
  5. la mort de Kell REVERTE les modifications (retour a 2 / 2).

ASCII only (cp1252). Usage : `python probe_95r2_sworn_protector.py`.
"""
from __future__ import annotations

import json
from pathlib import Path

import board as B
from engine.runner.state import State
from engine.runner.components import (UnitComponent, OwnerComponent, PositionComponent,
                                      StatsComponent, HealthComponent,
                                      get_ability_stat_modification, parent_of, children_of)
from engine.runner.prng import IntBasedMersenneTwister
from engine.entities.effects_state import EffectsState
from engine.entities.unit_context import UnitContext
from engine.runner.operations.triggers.dispatch.ability import pre_unit_ability_triggers
from engine.runner.abilities.astramilitarum import SupremeCommanderAbility, CONST_NR_OF_SUMMONS, CONST_RANGE

BOARD_ID = "MC1_67"
BOARD_KIND = "pvp"


def _board():
    """Board du moteur (adjacence `evenq` = l'adjacence hex fidele, cf. `triggers/base.py`) construit
    depuis le dump BC du board choisi. `walkable` = tuile jouable (`ForceUnplayable` false)."""
    p = Path(__file__).resolve().parent.parent.parent / "data" / "boards" / BOARD_KIND / (BOARD_ID + ".json")
    dump = json.loads(p.read_text(encoding="utf-8"))
    bd = B.Board({"Board": dump["board"], "SpawnPointSetIndex": dump.get("spawnPointsSet", 0)})
    tiles = []
    for i, (col, row) in enumerate(sorted(bd.playable_tiles())):
        t = bd.tile(col, row) or {}
        tiles.append({"id": i + 1, "col": col, "row": row, "walkable": True,
                      "tileDefId": t.get("tileId"), "elevation": t.get("elevation")})
    from engine.entities.pathfinding.board import Board as EngineBoard
    return EngineBoard(tiles, adjacency="evenq")


def _add_unit(state, vid, col, row, team, player, hp=100000):
    e = state.add_entity()
    e.add_component(UnitComponent(visual_id=vid, alive=True))
    e.add_component(OwnerComponent(team=team, player=player))
    ctx = UnitContext(entity_id=e.id, visual_id=vid, active_ability_level=50,
                      passive_ability_level=50, ability_variables_multiplier=100)
    ctx.traits = list((__import__("gameconfig").unit(vid) or {}).get("traits") or [])
    e.add_component(StatsComponent(ctx=ctx))
    e.add_component(HealthComponent(hp=hp, hp_max=hp))
    e.add_component(PositionComponent(col=col, row=row))
    return e.id


def main() -> int:
    state = State()
    state.board = _board()
    state.effects = EffectsState.seed({})
    state.rng = IntBasedMersenneTwister(777)
    creed = _add_unit(state, "astraCreed", 2, 2, team=1, player=3)
    foe = _add_unit(state, "necroSpyder", 2, 1, team=2, player=4)

    print("[0] creed=%d foe=%d" % (creed, foe))
    base_n = get_ability_stat_modification(state.get_entity(creed), CONST_NR_OF_SUMMONS)
    base_r = get_ability_stat_modification(state.get_entity(creed), CONST_RANGE)
    print("[0] modifications avant: nrOfSummons=%d range=%d (attendu 0/0)" % (base_n, base_r))
    assert base_n == 0 and base_r == 0

    # --- 1. l'ennemi cible Creed -> On(PreUnitAbility) -------------------------------------------
    res = pre_unit_ability_triggers(state, foe, creed, ranged=False, profile=None, ability_type=1013)
    print("[1] triggers: %s" % json.dumps(res, default=str))
    kids = children_of(state, creed)
    assert kids, "AUCUN enfant de Creed -> SwornProtector n'a pas fire"
    kell = kids[0]
    kuc = state.get_entity(kell).get_component(UnitComponent)
    print("[1] enfant spawne: u%d visual=%s" % (kell, kuc.visual_id))
    assert kuc.visual_id == "astraSmnKell"
    assert parent_of(state, kell).id == creed

    cp = state.get_entity(creed).get_component(PositionComponent)
    kp = state.get_entity(kell).get_component(PositionComponent)
    print("[1] positions apres switch: creed=(%d,%d) kell=(%d,%d)" % (cp.col, cp.row, kp.col, kp.row))
    assert (kp.col, kp.row) == (2, 2), "Kell n'a pas pris la place de Creed (switch manquant)"

    # --- 2. l'effet est pose sur Kell -------------------------------------------------------------
    names = [e.name for e in state.effects.by_unit.get(kell, []) if not e.consumed]
    print("[2] effets de Kell: %s" % names)
    assert "ListenUpMaggotsEffect" in names

    # --- 3. les modifications sont sur CREED (pas sur Kell) ---------------------------------------
    mn = get_ability_stat_modification(state.get_entity(creed), CONST_NR_OF_SUMMONS)
    mr = get_ability_stat_modification(state.get_entity(creed), CONST_RANGE)
    kn = get_ability_stat_modification(state.get_entity(kell), CONST_NR_OF_SUMMONS)
    print("[3] creed: nrOfSummons=+%d range=+%d | kell: nrOfSummons=+%d (attendu 1/3/0)" % (mn, mr, kn))
    assert (mn, mr, kn) == (1, 3, 0)

    # --- 4. SupremeCommander consomme les modifications -------------------------------------------
    out = SupremeCommanderAbility().execute_behaviour(state, creed, creed)
    print("[4] SupremeCommander: count=%s radius=%s spawned=%d"
          % (out["count"], out["radius"], len(out["spawned"])))
    assert out["count"] == 3, "count attendu 3 (2 + modification additive)"
    assert out["radius"] == 3, "radius attendu 3 (OVERRIDE, pas 2+3=5)"

    # --- 5. la mort de Kell reverte ----------------------------------------------------------------
    # #389-r2 : le volet etroit `_revert_ability_modifications_of_dead` est remplace par le
    # `RemoveEffects` complet de `IdunBattle.Operations.KillUnitOperation$$Execute` (step 0).
    from engine.runner.operations.remove_effects import remove_effects_operation
    from engine.entities.kill_unit_step import KillUnitStep
    state.get_entity(kell).get_component(UnitComponent).alive = False
    remove_effects_operation(state, kell, step=KillUnitStep.PreUnitRemove)
    mn2 = get_ability_stat_modification(state.get_entity(creed), CONST_NR_OF_SUMMONS)
    mr2 = get_ability_stat_modification(state.get_entity(creed), CONST_RANGE)
    print("[5] apres mort de Kell: nrOfSummons=+%d range=+%d (attendu 0/0)" % (mn2, mr2))
    assert (mn2, mr2) == (0, 0)

    # --- 6. ONE-SHOT : une 2e attaque ne re-spawne pas Kell ---------------------------------------
    before = len(children_of(state, creed, alive_only=False))
    pre_unit_ability_triggers(state, foe, creed, ranged=False, profile=None, ability_type=1013)
    after = len(children_of(state, creed, alive_only=False))
    print("[6] enfants avant/apres 2e attaque: %d -> %d (one-shot: doit etre egal)" % (before, after))
    assert before == after

    print("PROBE OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
