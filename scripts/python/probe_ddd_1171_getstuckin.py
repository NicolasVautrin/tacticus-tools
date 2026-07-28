"""Probe -- OU part le tirage supplementaire du cast 1171 ? (rattachement du rouge post-PR #177)

Monte le MEME montage que `tests/engine/runner/test_dakka_dakka_dakka_live.py` cas (A) : Snappawrecka
(`orksKillaKan`, porteur du trait `GetStuckIn`) tire sur une cible amenee a distance HEX `--dist`,
puis compare LIVE et OFFLINE **coup par coup** ET imprime, pour la meme configuration :

  * la distance HEX (`hexgeo.distance`) et la distance CHEBYSHEV (`max(|dcol|, |drow|)`) ;
  * le verdict du gate porte `damage_model.getstuckin_combat_chance` (None = trait INACTIF) ;
  * le nombre de tirages `state.rng` consommes par le cast OFFLINE.

Le gate NATIF est `IdunBattleLogic.Entities.Abilities.Triggered.Loki.GetStuckInAbility$$CreateTrigger`
= `On(8) & IsOdd & OwnerIsCaster & !(MinDistance > 2)` -- `MinDistance` est une distance HEX. Le port
utilise un proxy CHEBYSHEV. Les deux ne coincident pas partout : ce probe le rend visible d'un coup
d'oeil (colonne `hex` vs `cheby`).

    python probe_ddd_1171_getstuckin.py [--dist 3] [--a-units eldarFarseer,tauAunShi,ultraApothecary]

ASCII only. Dispose son runner.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys

import hexgeo
import rl_collect_batch as R

_SID = None


def _unwrap(r):
    return r.get("result") if isinstance(r, dict) and "result" in r else r


def rpc(method, params, timeout=90):
    global _SID
    if _SID is None:
        _SID = R._resolve_session()
    return _unwrap(R._rpc(_SID, method, [params], timeout=timeout))


def _cheby(a, b):
    return max(abs(a[0] - b[0]), abs(a[1] - b[1]))


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", default="777")
    ap.add_argument("--board", default="MC1_67")
    ap.add_argument("--dist", type=int, default=3)
    ap.add_argument("--hp-target", default="500000")
    ap.add_argument("--a-units", default="eldarFarseer,tauAunShi,ultraApothecary")
    a = ap.parse_args(argv)

    sf = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "logs",
                                      "probe_ddd_gsi.json"))
    os.makedirs(os.path.dirname(sf), exist_ok=True)
    subprocess.run([sys.executable, os.path.join(os.path.dirname(__file__), "rl_duel.py"), "build",
                    "--seed", a.seed, "--board", a.board, "--state-file", sf,
                    "--p-units", "orksKillaKan", "--a-units", a.a_units,
                    "--crit", "0,0", "--block-target", "0,0", "--hp-target", a.hp_target],
                   check=True, cwd=os.path.dirname(__file__),
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    rid = json.load(open(sf))["runnerId"]
    print("[build] runnerId =", rid, "| dist demandee =", a.dist)
    try:
        from engine.entities.pathfinding.board import Board
        from engine.runner.snapshot import load_state
        from engine.runner.prng import IntBasedMersenneTwister
        from engine.runner.runner import Runner
        from engine.runner.messages import ActiveAbilityMessage
        from engine.runner.components import PositionComponent
        from engine.runner import damage_model as DM

        bg = rpc("boardGraph", {"runnerId": rid}, 60)
        board = Board(bg["tiles"], adjacency="native_sym")
        dv = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True})
        alive = [u for u in (dv.get("units") or []) if u.get("alive")]
        snappa = next(u for u in alive if u.get("visualId") == "orksKillaKan")
        mine = snappa["owner"]
        ens = [u for u in alive if u.get("owner") != mine]
        C = (snappa["pos"]["col"], snappa["pos"]["row"])
        occupied = {(u["pos"]["col"], u["pos"]["row"]) for u in alive}
        dest = next((c for c in (board.coord(t) for t in sorted(board.by_id))
                     if board.walkable(board.id_at(*c)) and c not in occupied
                     and hexgeo.distance(C, c) == a.dist), None)
        if dest is None:
            print("[skip] aucune tuile libre a distance hex", a.dist)
            return 1
        tgt = ens[0]["id"]
        rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "move", "unitId": tgt, "to": {"col": dest[0], "row": dest[1]}}}, 40)
        for _ in range(12):
            dv = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True})
            if dv.get("currentPlayer") == mine:
                break
            rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 40)

        snap = {"dv": dv,
                "ob": rpc("observeBattle", {"runnerId": rid}, 40),
                "snap": rpc("combatSnapshot", {"runnerId": rid}, 60),
                "rng": rpc("dumpRng", {"runnerId": rid}, 30)}

        st = load_state(snap["dv"], snap["ob"], snap["snap"], board=board)
        if isinstance(snap["rng"], dict) and snap["rng"].get("mt"):
            rr = IntBasedMersenneTwister()
            rr.mt = list(snap["rng"]["mt"])
            rr.mti = snap["rng"]["mti"]
            st.rng = rr
        cp = st.get_entity(snappa["id"]).get_component(PositionComponent)
        tp = st.get_entity(tgt).get_component(PositionComponent)
        cpos, tpos = (cp.col, cp.row), (tp.col, tp.row)
        hexd = hexgeo.distance(cpos, tpos)
        chebyd = _cheby(cpos, tpos)
        bd, _aur, _te = DM.build_hits_board(st, snappa["id"], tgt, cpos, tpos, False)
        chance = DM.getstuckin_combat_chance(st, snappa["id"], tgt, cpos, tpos, bd)
        print("[geom] caster=%s cible=%s | hex=%d cheby=%d" % (cpos, tpos, hexd, chebyd))
        print("[gate] getstuckin_combat_chance -> %s   (None = trait INACTIF cote port)" % chance)
        print("[gate] natif = !(MinDistance > 2) : trait actif ssi HEX <= 2  -> attendu %s"
              % ("ACTIF" if hexd <= 2 else "INACTIF"))

        before = st.rng.call_count
        runner = Runner(st).install_default_handlers(20)
        runner.apply(ActiveAbilityMessage(caster_id=snappa["id"], target_id=tgt, ability_type=1171))
        last = runner.ability_handler.last or {}
        off = ((last.get("main_attack") or {}).get("per_hit")) or []
        draws = st.rng.call_count - before
        print("[off ] per_hit=%s  hits=%s  tirages MT=%d" % (off, last.get("hits"), draws))

        res = rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "ability", "casterId": snappa["id"], "targetId": tgt, "abilityType": 1171}}, 60)
        a0 = (res.get("actions") or [{}])[0]
        live = []
        for e in (a0.get("events") or []):
            td = e.get("tags")
            td = json.loads(td) if isinstance(td, str) else td
            if td and "Amount" in td and td.get("Active_Ability_Type") == 1171 \
                    and td.get("Target_Id") == tgt:
                live.append(td["Amount"])
        print("[live] per_hit=%s  mutated=%s  #events=%d"
              % (live, a0.get("mutated"), len(a0.get("events") or [])))
        common = 0
        while common < min(len(off), len(live)) and off[common] == live[common]:
            common += 1
        print("[diff] prefixe commun = %d coups sur %d" % (common, len(live)))
    finally:
        rpc("disposeRunner", {"runnerId": rid}, 20)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
