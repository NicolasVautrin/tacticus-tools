"""probe_303 -- ISOLE le passif `FabricatorClawArray` du `necroSpyder` (residu N20 de #299).

POURQUOI CE PROBE. La mesure de #299 melangeait DEUX reparations dans un seul delta : la voie ACTIVE
(`28 Repair`) et ce passif. On en tirait un ecart (natif 10457, port 6025) expliquable, mais jamais
un montant OBSERVE isolement. Ce probe separe les etages en n'exercant QUE le passif :

    Le Spyder se DEPLACE au contact d'un allie mecanique blesse, et NE CASTE RIEN.

`IdunBattle.Operations.MoveUnitOperation$$Execute` pose `UnitFlag.ArrivedAtFinalTile` puis publie
`On(0x1c)` ssi le flag venait d'etre ajoute -> le passif tire SUR LE MOVE SEUL. Tout delta de PV
mesure sur l'allie est donc, entierement, `hpToRepair[niveau] x multiplicateur de rarete`.

ETAGES MESURES, cote a cote (natif / port) :
  E1  CONFIG   : `hpToRepair[passive_ability_level]` et le multiplicateur de rarete lus du gameconfig
                 (= `AbilityConfiguration.GetVariableForLevel(config, 0x24, abilityState, 0)`)
  E2  TRIGGER  : le predicat `OwnerIsActor & !AmountIsZero(GetTargetSelector())` du port, evalue sur
                 la capture PRE-move -- avec le detail du selecteur etage par etage
  E3  MOVE SEUL: delta PV de l'allie, LIVE (le natif) vs PORT (`MoveUnitMessage` sur la meme capture)
  E4  CONTROLE : un 2e move dans le MEME tour ne doit RIEN reparer (le flag est deja pose ->
                 `UnitFlagsComponent.Add` rend false -> aucun `On(0x1c)`)

Usage:
    python probe_303_fabricator_claw_array.py [--repairer necroSpyder] [--damaged 1]

ASCII only (console cp1252).
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "tests", "engine", "runner"))

import _repair_stage as S                                        # noqa: E402
from engine.entities.pathfinding.board import Board              # noqa: E402
from engine.runner.components import HealthComponent, StatsComponent   # noqa: E402
from engine.runner.messages import MoveUnitMessage               # noqa: E402
from engine.runner.runner import Runner                          # noqa: E402
from engine.runner.snapshot import load_state                    # noqa: E402


def _unwrap(r):
    return r.get("result") if isinstance(r, dict) and "result" in r else r


def _by_vis(state, vis):
    for uid, e in state.entities.items():
        sc = e.get_component(StatsComponent)
        if sc is not None and getattr(sc.ctx, "visual_id", None) == vis:
            return uid
    return None


def _live_units(rpc, rid):
    ob = rpc("observeBattle", {"runnerId": rid}, 40) or {}
    return {u["squadId"]: u for u in (ob.get("units") or [])}


def _capture(rpc, rid, board):
    """Capture offline + CALAGE du PRNG sur l'etat MT live (`dumpRng`).

    `PickRandomly` CONSOMME le PRNG (deux fois par fire : le trigger et le behaviour ont chacun leur
    instance). Sans calage, `_pick_randomly_n` retombe sur `pool[:n]` -- deterministe, donc juste par
    accident quand le pool tient dans 1 element, et FAUX des qu'il y en a deux."""
    dv = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    ob = rpc("observeBattle", {"runnerId": rid}, 40)
    snap = rpc("combatSnapshot", {"runnerId": rid}, 40)
    if not (dv and ob and snap):
        return None
    state = load_state(dv, ob, snap, board=board)
    s0 = rpc("dumpRng", {"runnerId": rid}, 30)
    if isinstance(s0, dict) and s0.get("mt"):
        from engine.runner.prng import IntBasedMersenneTwister
        rng = IntBasedMersenneTwister()
        rng.mt = list(s0["mt"])
        rng.mti = s0["mti"]
        state.rng = rng
    return state


def _free_tile_adjacent_to(board, occupied, target_tile, exclude=()):
    """Une tuile LIBRE et marchable adjacente a `target_tile` (hors `exclude`). None si aucune."""
    for n in board.neighbours(target_tile):
        if n in exclude or n not in board.by_id:
            continue
        if board.walkable(n) and n not in occupied:
            return n
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repairer", default="necroSpyder")
    ap.add_argument("--damaged", type=int, default=1,
                    help="RemainingHealth pose sur la cible : 1 = manque MAXIMAL, pour que "
                         "`FillUpStatComponent$$MaxFillUp` ne sature pas")
    ap.add_argument("--hp-player", type=int, default=300000, dest="hp_player")
    args = ap.parse_args()

    import rl_collect_batch as R          # meme voie host que le conftest (import PARESSEUX)
    sid = R._resolve_session()

    def rpc(method, body=None, timeout=90):
        return _unwrap(R._rpc(sid, method, [body] if body is not None else [], timeout=timeout))

    S.REPAIRER_VIS = args.repairer
    stage = S.build_stage(rpc, hp_player=args.hp_player, advance=0, damaged_repairee=args.damaged)
    rid = stage["rid"]
    print("runner=%d repairer=%s repairee=%s" % (rid, args.repairer, S.REPAIREE_VIS))
    rc = 0
    try:
        bg = rpc("boardGraph", {"runnerId": rid}, 60)
        board = Board(bg["tiles"], adjacency="native_sym") if bg and bg.get("tiles") else None
        if board is None:
            print("boardGraph indispo")
            return 1

        U = _live_units(rpc, rid)
        sq_c = next((sq for sq, u in U.items() if u.get("visualId") == args.repairer), None)
        sq_t = next((sq for sq, u in U.items() if u.get("visualId") == S.REPAIREE_VIS), None)
        if sq_c is None or sq_t is None:
            print("repareur/cible absents live (%s / %s)" % (sq_c, sq_t))
            return 1
        occupied = {board.id_at(u["col"], u["row"]) for u in U.values()}
        t_tile = board.id_at(U[sq_t]["col"], U[sq_t]["row"])
        c_tile = board.id_at(U[sq_c]["col"], U[sq_c]["row"])
        dest = _free_tile_adjacent_to(board, occupied, t_tile, exclude=(c_tile,))
        if dest is None:
            print("aucune tuile libre adjacente a la cible -- montage a revoir")
            return 1
        dcol, drow = board.coord(dest)
        print("move: %s (%d,%d) -> (%d,%d) ; cible en (%d,%d)"
              % (args.repairer, U[sq_c]["col"], U[sq_c]["row"], dcol, drow,
                 U[sq_t]["col"], U[sq_t]["row"]))

        # --- capture PRE-move (l'etat commun aux deux cotes) ----------------------------------------
        state = _capture(rpc, rid, board)
        if state is None:
            print("capture pre-move KO")
            return 1
        cid, tid = _by_vis(state, args.repairer), _by_vis(state, S.REPAIREE_VIS)
        if cid is None or tid is None:
            print("roster incomplet offline (%s / %s)" % (cid, tid))
            return 1

        # --- E1 CONFIG ------------------------------------------------------------------------------
        from engine.runner.operations.triggers.loki.fabricator_claw_array import (
            hp_to_repair, fabricator_claw_array_trigger_tree,
            fabricator_claw_array_target_selector)
        ctx = state.get_entity(cid).get_component(StatsComponent).ctx
        lvl = getattr(ctx, "passive_ability_level", None)
        mult = int(getattr(ctx, "ability_variables_multiplier", 100) or 100)
        amount = hp_to_repair(state, cid)
        print("\n[E1 CONFIG] passive_ability_level=%s multiplier=%d%% hpToRepair=%d"
              % (lvl, mult, amount))

        # --- E2 TRIGGER (etage par etage du selecteur) ----------------------------------------------
        from engine.runner.abilities.behaviours.context import entities_from_state
        from engine.entities.selectors.accessors import Owner
        from engine.entities.selectors.units import (
            AdjacentFriends, Repairable, UnitsAffectedByHealType
        )
        from engine.dsl.base import Const
        ents = entities_from_state(state, cid, None, actor_id=cid)
        adj = AdjacentFriends(Owner(), Const(1), reference=Owner()).select(ents)
        aff = UnitsAffectedByHealType(AdjacentFriends(Owner(), Const(1), reference=Owner()),
                                      1).select(ents)
        rep = Repairable(UnitsAffectedByHealType(
            AdjacentFriends(Owner(), Const(1), reference=Owner()), 1), 0, True, 3).select(ents)
        print("\n[E2 TRIGGER] PRE-move (le Spyder n'est pas encore au contact)")
        print("  AdjacentFriends(Owner,1,3)        = %s" % [u.get("id") for u in adj])
        print("  UnitsAffectedByHealType(., 1)     = %s" % [u.get("id") for u in aff])
        print("  Repairable(., 0, 1, 3)            = %s" % [u.get("id") for u in rep])
        print("  trigger tree                      = %s"
              % bool(fabricator_claw_array_trigger_tree().evaluate(ents)))
        _ = fabricator_claw_array_target_selector()          # construction seule (pas d'eval : RNG)

        hc = state.get_entity(tid).get_component(HealthComponent)
        print("  cible hp=%s max=%s manque=%s" % (hc.hp, hc.hp_max, int(hc.hp_max) - int(hc.hp)))

        # --- E3 MOVE SEUL ---------------------------------------------------------------------------
        off_pre = int(hc.hp)
        runner = Runner(state).install_default_handlers(20)
        runner.apply(MoveUnitMessage(unit_id=cid, to=(dcol, drow)))
        off_delta = int(state.get_entity(tid).get_component(HealthComponent).hp) - off_pre

        live_pre = _live_units(rpc, rid)[sq_t]["hp"]
        rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "move", "unitId": sq_c, "to": {"col": dcol, "row": drow}}}, 60)
        U2 = _live_units(rpc, rid)
        live_delta = U2[sq_t]["hp"] - live_pre
        print("\n[E3 MOVE SEUL] live=%d  port=%d  hpToRepair=%d  ECART(live-port)=%d"
              % (live_delta, off_delta, amount, live_delta - off_delta))
        if live_delta != off_delta:
            rc = 1

        # --- E4 CONTROLE : 2e move dans le MEME tour = aucun nouvel `On(0x1c)` ----------------------
        occupied2 = {board.id_at(u["col"], u["row"]) for u in U2.values()}
        dest2 = _free_tile_adjacent_to(board, occupied2, t_tile,
                                       exclude=(board.id_at(U2[sq_c]["col"], U2[sq_c]["row"]),))
        if dest2 is None:
            print("\n[E4 CONTROLE] pas de 2e tuile libre adjacente -- controle non joue")
        else:
            d2c, d2r = board.coord(dest2)
            off2_pre = int(state.get_entity(tid).get_component(HealthComponent).hp)
            runner.apply(MoveUnitMessage(unit_id=cid, to=(d2c, d2r)))
            off2 = int(state.get_entity(tid).get_component(HealthComponent).hp) - off2_pre
            live2_pre = _live_units(rpc, rid)[sq_t]["hp"]
            rpc("applyAction", {"runnerId": rid, "action": {
                "kind": "move", "unitId": sq_c, "to": {"col": d2c, "row": d2r}}}, 60)
            live2 = _live_units(rpc, rid)[sq_t]["hp"] - live2_pre
            print("\n[E4 CONTROLE] 2e move MEME tour : live=%d port=%d (attendu 0 des deux cotes)"
                  % (live2, off2))
            if live2 != 0 or off2 != 0:
                rc = 1
    finally:
        rpc("disposeRunner", {"runnerId": rid}, 40)
    return rc


if __name__ == "__main__":
    sys.exit(main())
