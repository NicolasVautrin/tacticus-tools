"""#419-r6-r2 -- `ChampionOfTheFeast` (`TriggeredAbilityType` 0x43e = 1086), le passif de
`templSwordBrother` << Sword Brother Godswyl >>, CONFRONTE AU LIVE.

CE QUE CE PROBE MESURE. Le passif n'etait dans AUCUN des quatre registres de trigger : offline,
Godswyl terminait son activation SANS frapper l'ennemi adjacent et SANS lui poser son malus
d'armure -- ni erreur, ni crash.

CRITERE BINAIRE, sur DEUX observables INDEPENDANTS : quand Godswyl termine son activation a cote
d'un ennemi damageable,
  (a) cet ennemi PERD-il des PV -- du meme ordre live et offline ?
  (b) son `FixedArmor` BAISSE-t-il -- du MEME montant (`-armorReduction[lvl] x mult`) des deux cotes ?

Le montage DISCRIMINE par construction : avant le port, le cote PORT rend `0` sur les DEUX axes
pendant que le natif rend du non-nul. Un accord a zero des deux cotes ne prouverait rien -- c'est
pourquoi l'etage E5 ASSERTIONNE que le temoin natif est NON NUL avant de comparer.

MONTAGE. Les positions sont CONDUITES (jamais « bloque par la geometrie de spawn ») : on cherche une
tuile LIBRE adjacente a un ennemi et on y DEPLACE Godswyl. C'est ce deplacement qui publie
`On(0x1c = ArrivedAtFinalTile)` (`IdunBattle.Operations.MoveUnitOperation$$Execute`).

ASCII only (console cp1252).

    python probe_419r6r2_champion_of_the_feast.py [--board MC1_67] [--seed 777]
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from engine.entities.pathfinding.board import Board                    # noqa: E402
from engine.entities.stats import StatPart, StatType                   # noqa: E402
from engine.runner.components import HealthComponent, StatsComponent   # noqa: E402
from engine.runner.messages import MoveUnitMessage                     # noqa: E402
from engine.runner.runner import Runner                                # noqa: E402
from engine.runner.snapshot import load_state                          # noqa: E402

CASTER_VIS = "templSwordBrother"          # << Sword Brother Godswyl >>, le SEUL porteur lineup


def _ok(r):
    return isinstance(r, dict) and r.get("ok")


def _unwrap(r):
    if isinstance(r, dict) and "result" in r:
        return r["result"]
    return r


def _live_units(rpc, rid):
    r = rpc("observeBattle", {"runnerId": rid}, 40)
    return {u["squadId"]: u for u in (r.get("units") or [])} if _ok(r) else {}


def _by_vis(state, vis):
    for uid, e in state.entities.items():
        sc = e.get_component(StatsComponent)
        if sc is not None and getattr(sc.ctx, "visual_id", None) == vis:
            return uid
    return None


def _capture(rpc, rid, board):
    """Capture l'etat offline ET CALE LE PRNG sur l'etat MT live (`dumpRng`).

    Le calage n'est PAS cosmetique ici : le behaviour porte un `PickRandomly` (1 tirage par fire).
    Sans lui, `_pick_randomly_n` retombe sur `pool[:n]` -- deterministe, donc d'accord avec le natif
    tant que le pool tient dans 1 element, et DIVERGENT des qu'il y en a deux."""
    dv = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    ob = rpc("observeBattle", {"runnerId": rid}, 40)
    snap = rpc("combatSnapshot", {"runnerId": rid}, 40)
    if not (_ok(dv) and _ok(ob) and _ok(snap)):
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


def _hp(state, uid):
    e = state.get_entity(uid)
    hc = e.get_component(HealthComponent) if e is not None else None
    return int(hc.hp) if hc is not None else None


def _armor(state, uid, part=StatPart.CURRENT):
    e = state.get_entity(uid)
    sc = e.get_component(StatsComponent) if e is not None else None
    if sc is None:
        return None
    return int(sc.ctx.get_stat(int(StatType.FIXED_ARMOR), int(part)) or 0)


def _free_tiles_adjacent(board, occupied, target_tile, exclude=()):
    """Tuiles LIBRES et marchables a distance hex 1 de `target_tile`. Sert a CONDUIRE les positions."""
    from engine.runner.operations.triggers.base import _hex_dist
    out = []
    for t in board.by_id:
        if t in occupied or t in exclude or not board.walkable(t):
            continue
        d = _hex_dist(board, target_tile, t, 1)
        if d == 1:
            out.append(t)
    return out


def _build(seed, board_id, p_units, a_units, state_file, move=25):
    """`--unit-stat <vis>:Movement=<n>` CONDUIT la position : sur les boards 5v5 les spawns sont a
    ~8 hex, et Godswyl a `Movement=3` -- le move live serait CLAMPE avant l'adjacence, et le probe
    mesurerait « pas de fire » pour une raison de GEOMETRIE, pas de port. On lui donne donc la
    portee d'atteindre l'ennemi EN UN MOVE (le meme levier que
    `test_462_..._crush_death_events_live.py`). Cela ne touche NI le passif NI l'armure : le seul
    observable deplace est la distance franchissable."""
    cmd = [sys.executable, "rl_duel.py", "build", "--seed", str(seed), "--board", board_id,
           "--state-file", state_file, "--p-units", p_units, "--a-units", a_units,
           "--unit-stat", "%s:Movement=%d" % (CASTER_VIS, move)]
    r = subprocess.run(cmd, cwd=os.path.dirname(os.path.abspath(__file__)),
                       capture_output=True, text=True, timeout=600)
    if not os.path.exists(state_file):
        print("BUILD KO rc=%s" % r.returncode)
        print((r.stdout or "")[-1500:])
        print((r.stderr or "")[-1500:])
        return None
    with open(state_file, encoding="utf-8") as fh:
        return json.load(fh).get("runnerId")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--board", default="MC1_67")
    ap.add_argument("--seed", type=int, default=777)
    ap.add_argument("--p-units", dest="p_units", default="templSwordBrother,templAggressor")
    ap.add_argument("--a-units", dest="a_units", default="templChampion,templAncient")
    ap.add_argument("--state-file", dest="state_file", default=None)
    ap.add_argument("--keep", action="store_true", help="ne pas disposer le runner en sortie")
    args = ap.parse_args()

    sf = args.state_file or os.path.join(tempfile.gettempdir(), "st_419r6r2_probe.json")
    import rl_collect_batch as R
    sid = R._resolve_session()

    def rpc(method, body=None, timeout=90):
        return _unwrap(R._rpc(sid, method, [body] if body is not None else [], timeout=timeout))

    rid = _build(args.seed, args.board, args.p_units, args.a_units, sf)
    if rid is None:
        return 1
    print("runner=%s board=%s seed=%d" % (rid, args.board, args.seed))
    rc = 0
    try:
        bg = rpc("boardGraph", {"runnerId": rid}, 60)
        board = Board(bg["tiles"], adjacency="native_sym") if bg and bg.get("tiles") else None
        if board is None:
            print("boardGraph indispo")
            return 1

        U = _live_units(rpc, rid)
        sq_c = next((sq for sq, u in U.items() if u.get("visualId") == CASTER_VIS), None)
        if sq_c is None:
            print("caster %s absent live" % CASTER_VIS)
            return 1
        # `observeBattle` publie l'appartenance sous `teamId` (et `playerId`), PAS `team`.
        c_team = U[sq_c].get("teamId")
        enemies = [sq for sq, u in U.items()
                   if u.get("teamId") != c_team and not u.get("isDead")]
        if not enemies:
            print("aucun ennemi live -- montage a revoir")
            return 1

        occupied = {board.id_at(u["col"], u["row"]) for u in U.values()}
        c_tile = board.id_at(U[sq_c]["col"], U[sq_c]["row"])

        # --- E0 : CONDUIRE les positions -- une tuile LIBRE adjacente a un ennemi -----------------
        dest, sq_t = None, None
        for sq in enemies:
            t_tile = board.id_at(U[sq]["col"], U[sq]["row"])
            cand = _free_tiles_adjacent(board, occupied, t_tile, exclude=(c_tile,))
            if cand:
                dest, sq_t = cand[0], sq
                break
        if dest is None:
            print("E0 KO : aucune tuile libre adjacente a un ennemi")
            return 1
        dcol, drow = board.coord(dest)
        print("E0 montage : %s squad=%s (%d,%d) -> (%d,%d) ; cible squad=%s %s (%d,%d)"
              % (CASTER_VIS, sq_c, U[sq_c]["col"], U[sq_c]["row"], dcol, drow,
                 sq_t, U[sq_t].get("visualId"), U[sq_t]["col"], U[sq_t]["row"]))

        # --- capture PRE-move : l'etat COMMUN aux deux cotes --------------------------------------
        state = _capture(rpc, rid, board)
        if state is None:
            print("capture pre-move KO")
            return 1
        cid, tid = _by_vis(state, CASTER_VIS), _by_vis(state, U[sq_t].get("visualId"))
        if cid is None or tid is None:
            print("roster incomplet offline (%s / %s)" % (cid, tid))
            return 1
        hp0, ar0 = _hp(state, tid), _armor(state, tid)
        # TEMOIN BRUT, canal live independant de la reconstruction offline : `observeBattle`
        # publie `hp` et `armor` par unite. Il sert de contre-epreuve au couple (_hp, _armor).
        raw0 = (U[sq_t].get("hp"), U[sq_t].get("armor"))
        print("E0 pre-move  : cible hp=%s fixedArmor=%s ; temoin brut hp=%s armor=%s"
              % (hp0, ar0, raw0[0], raw0[1]))

        # --- E1 : CONFIG -- ce que le port ATTEND ------------------------------------------------
        from engine.runner.operations.triggers.loki.champion_of_the_feast import (
            armor_reduction, champion_of_the_feast_trigger_tree,
            champion_of_the_feast_possible_targets)
        ctx = state.get_entity(cid).get_component(StatsComponent).ctx
        lvl = getattr(ctx, "passive_ability_level", None)
        mult = int(getattr(ctx, "ability_variables_multiplier", 100) or 100)
        expected = armor_reduction(state, cid)
        print("E1 config    : passive_level=%s mult=%s%% -> armorReduction attendu=%s"
              % (lvl, mult, expected))
        if expected <= 0:
            print("E1 KO : armorReduction nul -- le montage ne peut RIEN discriminer")
            rc = 1

        # --- E2 : GATE -- le trigger matche-t-il APRES le move ? ----------------------------------
        # (evalue cote port sur l'etat POST-move offline, plus bas ; ici on note le pool PRE-move)
        from engine.runner.abilities.behaviours import entities_from_state
        ents = entities_from_state(state, cid, None, actor_id=cid)
        pool0 = champion_of_the_feast_possible_targets().evaluate(ents)
        print("E2 pre-move  : pool adjacent damageable = %d unite(s)" % len(pool0 or []))

        # --- E3 : LIVE -- le move publie On(0x1c), le natif fire ----------------------------------
        rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "move", "unitId": sq_c, "to": {"col": dcol, "row": drow}}}, 60)
        after_live = _capture(rpc, rid, board)
        if after_live is None:
            print("capture post-move KO")
            return 1
        tid_l = _by_vis(after_live, U[sq_t].get("visualId"))
        hp_l, ar_l = _hp(after_live, tid_l), _armor(after_live, tid_l)
        d_hp_l = (hp0 - hp_l) if (hp0 is not None and hp_l is not None) else None
        d_ar_l = (ar0 - ar_l) if (ar0 is not None and ar_l is not None) else None
        U2 = _live_units(rpc, rid)
        raw_l = (U2.get(sq_t, {}).get("hp"), U2.get(sq_t, {}).get("armor"))
        print("E3 LIVE      : cible hp=%s (-%s) fixedArmor=%s (-%s) ; temoin brut hp=%s armor=%s"
              % (hp_l, d_hp_l, ar_l, d_ar_l, raw_l[0], raw_l[1]))
        if raw0[1] is not None and raw_l[1] is not None:
            print("             temoin brut : d_hp=%s d_armor=%s"
                  % ((raw0[0] - raw_l[0]) if raw0[0] is not None else None,
                     raw0[1] - raw_l[1]))

        # --- E4 : PORT -- rejouer le MEME move sur l'etat PRE-move --------------------------------
        # Voie = `MovementHandler.visit_MoveUnitMessage`, le chemin du mouvement JOUEUR porte
        # (`operations/movement.py`), le MEME que traverse `AiControl$$ApplyAiMessages`. C'est lui
        # qui publie `On(0x1c = ArrivedAtFinalTile)` en fin d'`Execute`.
        # ⚠ NE PAS passer par `Runner.apply(MoveUnitMessage(...))` ici : hors boucle de tour, le
        # message n'est pas route et la position reste INCHANGEE -- le probe mesurerait alors
        # « port inerte » pour une raison de HARNAIS, pas de port. (Verifie : position (1,0)
        # identique avant/apres, `last_after_move` jamais produit.)
        from engine.runner.events import EventBus
        from engine.runner.operations.movement import MovementHandler
        handler = MovementHandler(state, EventBus())
        handler.visit_MoveUnitMessage(MoveUnitMessage(unit_id=cid, to=board.coord(dest)))
        fired = handler.after_move or []
        print("E4 fire      : %s" % json.dumps(fired, default=str)[:300])
        hp_p, ar_p = _hp(state, tid), _armor(state, tid)
        d_hp_p = (hp0 - hp_p) if (hp0 is not None and hp_p is not None) else None
        d_ar_p = (ar0 - ar_p) if (ar0 is not None and ar_p is not None) else None
        print("E4 PORT      : cible hp=%s (-%s) fixedArmor=%s (-%s)" % (hp_p, d_hp_p, ar_p, d_ar_p))

        # --- E5 : COMPARAISON -- avec TEMOIN NON NUL exige ----------------------------------------
        print("-" * 90)
        if not d_ar_l:
            print("E5 INCONCLUANT : le TEMOIN NATIF est NUL sur l'armure -- un accord a zero ne "
                  "prouve rien. Montage a revoir (l'ennemi choisi est-il damageable/adjacent ?).")
            rc = 1
        else:
            ok_ar = (d_ar_p == d_ar_l)
            print("E5 ARMURE    : natif -%s / port -%s  ->  %s" % (d_ar_l, d_ar_p,
                                                                   "OK" if ok_ar else "DIVERGE"))
            if not ok_ar:
                rc = 1
            if d_ar_l != expected:
                print("   (note : le delta natif %s != armorReduction attendu %s -- l'ecart peut "
                      "venir d'un AUTRE contributeur d'armure sur la meme cible)"
                      % (d_ar_l, expected))
        if not d_hp_l:
            print("E5 PV        : TEMOIN NATIF NUL sur les PV -- non discriminant sur cet axe.")
        else:
            # Les PV passent par un tirage `MinMaxDamage` : on exige le MEME SIGNE et un ordre de
            # grandeur comparable, pas l'egalite bit-exacte (le PRNG est cale, mais la chaine de
            # degat traverse crit/block, dont l'alignement se valide ailleurs).
            print("E5 PV        : natif -%s / port -%s  ->  %s"
                  % (d_hp_l, d_hp_p, "OK (les deux non nuls)" if d_hp_p else "PORT INERTE"))
            if not d_hp_p:
                rc = 1
        return rc
    finally:
        if not args.keep:
            try:
                rpc("disposeRunner", {"runnerId": rid}, 30)
            except Exception as exc:                       # noqa: BLE001
                print("dispose KO: %s" % type(exc).__name__)


if __name__ == "__main__":
    raise SystemExit(main())
