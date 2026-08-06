"""Genestealer Cults : `SpiritualLeader` (passif de `genesMagus` << Xybia >>) confronte au port.

SpiritualLeader = **passiveAbility** -> ability-trigger (registre `ABILITY_TRIGGERS`). RE ghidra
gqfc5mff6c (cf. `engine/runner/operations/triggers/loki/spiritual_leader.py`) :
  - `IdunBattleLogic.Entities.Abilities.Triggered.Loki.SpiritualLeaderAbility$$CreateTrigger` =
    `On(0x1c=ArrivedAtFinalTile) & OwnerIsActor` -- UNE seule branche, l'evenement portant lui-meme
    le « apres son move OU en fin de tour si elle ne bouge pas » (les DEUX emetteurs natifs de 0x1c
    sont `MoveUnitOperation$$Execute` et `FinishUnitTurnOperation$$Execute`, tous deux gardes par
    l'AJOUT du flag `UnitFlag.ArrivedAtFinalTile`) ;
  - `...$$CreateBehaviour` = `If(tiles, Spawn(decoy))` op_BitwiseAnd
    `If(AmountIsEqualOrGreater(GetAdjacentDecoys(), 2), Spawn(Neophyte, WithStatsFromConfig))` ;
  - `...$$GetAdjacentDecoys` = `Filter(AdjacentFriends(caster,1,1), HasTrait(Decoy) & (NOT
    HasFlag(Untargetable) | HasEffect(1390)))`.

CE FICHIER (port-agreement offline, board natif evenq + kit gameconfig LIVE ; positions DRIVE'es) --
cas discriminants, dont DEUX ou le passif NE MORD PAS :

  1. POSITIF  : Xybia a DEJA 1 decoy adjacent -> le decoy qu'elle pose porte le compte a 2 ->
                un `genesSmnNeophyte` est invoque SUR l'un des decoys adjacents (qui est ECRASE),
                avec les stats `WithStatsFromConfig` (summonHp/summonDmg/summonArmor du passif) ;
  2. NEGATIF (gate `AmountIsEqualOrGreater(.., 2)`) : Xybia n'a AUCUN decoy adjacent -> elle pose
                bien son decoy (volet 1, hors du gate) mais le compte tombe a 1 -> AUCUN Neophyte.
                C'est le cas ou le passif ne mord qu'a MOITIE : sans ce gate on invoquerait un
                Neophyte a chaque activation ;
  3. NEGATIF (gate one-shot du flag `ArrivedAtFinalTile`) : un SECOND `On(0x1c)` dans la MEME
                activation est un NO-OP (le natif ne publie l'event que si `Add(flag)` a rendu vrai) ;
  4. BRANCHE « n'a pas bouge » : `FinishUnitTurnOperation.execute(xybia, forced=False)` publie
                `On(0x1c)` -> le passif fire a la cloture du tour d'une Xybia immobile.

ASCII only."""
from __future__ import annotations

import pytest

MAGUS_VIS = "genesMagus"               # Xybia (HERO GS Cults, pool rank 17)
DECOY_VIS = "genesSmnDecoy"
NEOPHYTE_VIS = "genesSmnNeophyte"
BUILD = ["--roster", "1", "--p-units", f"{MAGUS_VIS},genesPrimus",
         "--a-units", "necroWarden,necroWarden"]


def _ok(r):
    return isinstance(r, dict) and r.get("ok")


def _load(rpc, build_runner, seed="777"):
    from engine.entities.pathfinding.board import Board
    from engine.runner.snapshot import load_state
    from engine.runner.prng import IntBasedMersenneTwister
    rid = build_runner(seed, extra=BUILD)["rid"]
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    if not (isinstance(bg, dict) and bg.get("tiles")):
        pytest.skip("boardGraph indispo")
    board = Board(bg["tiles"], adjacency="evenq")
    dec = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 150)
    ob = rpc("observeBattle", {"runnerId": rid}, 60)
    snap = rpc("combatSnapshot", {"runnerId": rid}, 90)
    s0 = rpc("dumpRng", {"runnerId": rid}, 30)
    state = load_state(dec, ob, snap, board=board)
    if _ok(s0) and s0.get("mt"):
        rng = IntBasedMersenneTwister()
        rng.mt = list(s0["mt"])
        rng.mti = s0["mti"]
        state.rng = rng
    return state, board


def _unit_by_vis(state, vis):
    from engine.runner.components import UnitComponent
    for eid, e in state.entities.items():
        uc = e.get_component(UnitComponent)
        if uc is not None and uc.visual_id == vis and uc.alive:
            return eid
    return None


def _occupied(state):
    from engine.runner.operations.spawn import _occupied_tiles
    return _occupied_tiles(state)


def _units_of_vis(state, vis):
    from engine.runner.components import UnitComponent
    return sorted(eid for eid, e in state.entities.items()
                  if (uc := e.get_component(UnitComponent)) is not None
                  and uc.alive and uc.visual_id == vis)


def _prep(rpc, build_runner, min_free_neighbours=2):
    """Xybia DRIVE'e sur une tuile ayant au moins `min_free_neighbours` voisines libres et walkable.
    Renvoie (state, board, magus, tile, free_neighbours)."""
    from engine.runner.components import PositionComponent
    state, board = _load(rpc, build_runner)
    magus = _unit_by_vis(state, MAGUS_VIS)
    if magus is None:
        pytest.skip("genesMagus absent de l'etat offline")
    occ = _occupied(state)
    pc = state.get_entity(magus).get_component(PositionComponent)
    if pc is None:
        pytest.skip("Xybia sans PositionComponent")
    occ.discard(board.id_at(pc.col, pc.row))
    target = None
    for t in sorted(board.by_id):
        if not board.walkable(t) or t in occ:
            continue
        free = [n for n in sorted(board.neighbours(t))
                if n not in occ and board.walkable(n) and n != t]
        if len(free) >= min_free_neighbours:
            target = (t, free)
            break
    if target is None:
        pytest.skip(f"aucune tuile avec >={min_free_neighbours} voisines libres sur ce board")
    tile, free = target
    c, r = board.coord(tile)
    pc.col, pc.row = c, r
    return state, board, magus, tile, free


def test_spiritual_leader_summons_neophyte_when_two_adjacent_decoys(live_session, rpc, build_runner):
    """POSITIF : Xybia a DEJA un decoy adjacent ; a la fin de son activation elle en pose un SECOND
    (`If(tiles, Spawn(decoy))`), le compte passe a 2 -> `AmountIsEqualOrGreater(.., 2)` est vrai
    (RE-EVALUE apres le spawn : le decoy neuf COMPTE, DSL lazy) -> un `genesSmnNeophyte` est invoque
    sur l'un des decoys adjacents, qui est CRUSHE (`AddUnitOperation$$KillSteppableUnits`)."""
    from engine.runner.operations.spawn import spawn_decoy
    from engine.runner.operations.triggers.dispatch.move_death import (
        arrived_at_final_tile_triggers
    )
    from engine.runner.components import UnitComponent, StatsComponent
    state, board, magus, tile, free = _prep(rpc, build_runner, min_free_neighbours=2)
    pre = spawn_decoy(state, free[0], magus)             # 1 decoy ALLIE deja adjacent
    assert pre is not None, "spawn du decoy preexistant KO (pre-cond)"
    decoys0 = set(_units_of_vis(state, DECOY_VIS))

    out = arrived_at_final_tile_triggers(state, magus)
    sl = [r for r in out if isinstance(r, dict) and r.get("passive") == "SpiritualLeader"]
    decoys1 = set(_units_of_vis(state, DECOY_VIS))
    neos = _units_of_vis(state, NEOPHYTE_VIS)
    print(f"[sl +] res={sl} decoys {sorted(decoys0)} -> {sorted(decoys1)} neophytes={neos}")

    assert sl, f"SpiritualLeader n'a pas fire sur On(0x1c) : {out}"
    r = sl[0]
    assert r.get("decoy") is not None, f"aucun decoy pose (volet 1) : {r}"
    assert len(r.get("adjacent_decoys") or []) >= 2, \
        f"le decoy neuf n'a pas ete compte dans GetAdjacentDecoys (lazy KO) : {r}"
    assert r.get("summon") is not None, f"aucun Neophyte invoque malgre >=2 decoys : {r}"
    assert neos, "aucune entite genesSmnNeophyte dans l'etat"
    # le decoy porteur est CRUSHE par l'arrivant (KillSteppableUnits)
    crushed = r.get("summon_on_decoy")
    assert crushed is not None
    cuc = state.get_entity(crushed).get_component(UnitComponent)
    assert cuc is not None and not cuc.alive, \
        f"le decoy porteur du Neophyte n'a PAS ete crushe (alive={cuc and cuc.alive})"
    # stats WithStatsFromConfig (summonHp/summonDmg/summonArmor du passif de Xybia)
    nsc = state.get_entity(neos[0]).get_component(StatsComponent)
    assert nsc is not None and int(nsc.ctx.health) > 0, "Neophyte sans stats de config (summonHp)"
    print(f"[sl + stats] neophyte hp={nsc.ctx.health}")


def test_spiritual_leader_no_summon_with_single_decoy(live_session, rpc, build_runner):
    """NEGATIF -- gate `AmountIsEqualOrGreater(GetAdjacentDecoys(), Direct(2))`. Xybia n'a AUCUN
    decoy adjacent au depart : elle pose le sien (volet 1, HORS du gate), le compte tombe a 1 ->
    AUCUN Neophyte. C'est ce gate qui distingue le passif d'un summon inconditionnel."""
    from engine.runner.operations.triggers.dispatch.move_death import (
        arrived_at_final_tile_triggers
    )
    state, board, magus, tile, free = _prep(rpc, build_runner, min_free_neighbours=1)
    assert not _units_of_vis(state, DECOY_VIS), "des decoys preexistent (pre-cond KO)"

    out = arrived_at_final_tile_triggers(state, magus)
    sl = [r for r in out if isinstance(r, dict) and r.get("passive") == "SpiritualLeader"]
    neos = _units_of_vis(state, NEOPHYTE_VIS)
    print(f"[sl - one decoy] res={sl} neophytes={neos}")

    assert sl, f"SpiritualLeader n'a pas fire : {out}"
    r = sl[0]
    assert r.get("decoy") is not None, f"volet 1 (decoy) doit fire meme sans gate : {r}"
    assert len(r.get("adjacent_decoys") or []) == 1, \
        f"compte de decoys adjacents inattendu : {r.get('adjacent_decoys')}"
    assert r.get("summon") is None, f"gate >=2 KO : un Neophyte a ete invoque avec 1 seul decoy : {r}"
    assert not neos, f"gate KO : entite Neophyte presente : {neos}"


def test_spiritual_leader_fires_once_per_activation(live_session, rpc, build_runner):
    """NEGATIF -- gate ONE-SHOT. Le natif ne publie `On(0x1c)` que si `UnitFlagsComponent.Add(
    ArrivedAtFinalTile)` a rendu VRAI. Un second passage dans la MEME activation ne doit donc RIEN
    faire (sinon Xybia poserait un decoy par appel du vecteur : move puis fin de tour)."""
    from engine.runner.operations.triggers.dispatch.move_death import (
        arrived_at_final_tile_triggers
    )
    state, board, magus, tile, free = _prep(rpc, build_runner, min_free_neighbours=2)

    out1 = arrived_at_final_tile_triggers(state, magus)
    n1 = len(_units_of_vis(state, DECOY_VIS))
    out2 = arrived_at_final_tile_triggers(state, magus)
    n2 = len(_units_of_vis(state, DECOY_VIS))
    print(f"[sl one-shot] fire1={len(out1)} decoys={n1} | fire2={len(out2)} decoys={n2}")

    assert out1, "le 1er On(0x1c) n'a rien declenche (pre-cond)"
    assert out2 == [], f"gate one-shot KO : le 2e On(0x1c) a re-fire dans la meme activation : {out2}"
    assert n2 == n1, f"gate KO : un decoy supplementaire a ete pose ({n1} -> {n2})"


def test_spiritual_leader_fires_at_turn_end_without_moving(live_session, rpc, build_runner):
    """BRANCHE « n'a pas bouge » : `FinishUnitTurnOperation.execute(xybia, forced=False)` mirror
    `IdunBattle.Operations.FinishUnitTurnOperation$$Execute` -- `Add(ArrivedAtFinalTile)` nouvellement
    pose ET `!forced` -> publication de `On(0x1c)`. Xybia immobile pose donc quand meme son decoy."""
    from engine.runner.operations.turnflow import FinishUnitTurnOperation
    state, board, magus, tile, free = _prep(rpc, build_runner, min_free_neighbours=1)
    assert not _units_of_vis(state, DECOY_VIS), "des decoys preexistent (pre-cond KO)"

    res = FinishUnitTurnOperation.execute(state, magus, forced=False)
    trig = res.get("arrived_triggers") or []
    sl = [r for r in trig if isinstance(r, dict) and r.get("passive") == "SpiritualLeader"]
    decoys = _units_of_vis(state, DECOY_VIS)
    print(f"[sl turn-end] newly_arrived={res.get('newly_arrived')} sl={sl} decoys={decoys}")

    assert res.get("newly_arrived") is True, "pre-cond : le flag ArrivedAtFinalTile etait deja pose"
    assert sl, f"SpiritualLeader n'a pas fire a la cloture du tour d'une Xybia immobile : {res}"
    assert sl[0].get("decoy") is not None and decoys, "aucun decoy pose en fin de tour"


def test_spiritual_leader_turn_end_forced_does_not_fire(live_session, rpc, build_runner):
    """NEGATIF -- gate `!forced` de `FinishUnitTurnOperation$$Execute` : un tour TERMINE de force
    (`forced=True`, flag 27 `TurnTerminated`) pose bien `ArrivedAtFinalTile` mais NE publie PAS
    `On(0x1c)` -> le passif ne fire pas."""
    from engine.runner.operations.turnflow import FinishUnitTurnOperation
    state, board, magus, tile, free = _prep(rpc, build_runner, min_free_neighbours=1)
    assert not _units_of_vis(state, DECOY_VIS), "des decoys preexistent (pre-cond KO)"

    res = FinishUnitTurnOperation.execute(state, magus, forced=True)
    decoys = _units_of_vis(state, DECOY_VIS)
    print(f"[sl turn-end forced] res={res} decoys={decoys}")

    assert res.get("newly_arrived") is True, "pre-cond : le flag etait deja pose"
    assert "arrived_triggers" not in res, f"gate !forced KO : On(0x1c) publie sur un tour force : {res}"
    assert not decoys, f"gate KO : un decoy a ete pose sur un tour termine de force : {decoys}"
