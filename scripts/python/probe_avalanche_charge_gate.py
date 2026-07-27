"""Probe RESIDU `IsCharging` -- `AvalancheOfMuscle_ExtraDamage` (1025, passif `astraBullgryn`).

But : etablir que le +extraDmg de CHARGE manquant offline est un residu du PASSIF (canal modifier
eager, gate `IsCharging` non porte -- deja documente pour `BlackRage_ExtraDamage` /
`FeederTendrils_ExtraDamage`) et NON un defaut du port de FragBomb (1017) : on le reproduit sur
l'ATTAQUE NORMALE du meme porteur, qui ne traverse AUCUNE ligne de FragBomb.

Protocole : le Bullgryn BOUGE (charge) puis attaque NORMALEMENT un ennemi adjacent ; on confronte le
per-coup live au rejeu offline (meme MT). Puis on imprime `extraDmg[niveau passif] x multiplicateur`
pour nommer l'ecart.

Usage : python probe_avalanche_charge_gate.py [--seed 777]
ASCII only.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import hexgeo
import rl_collect_batch as R
from engine.entities.effects.magnitude import ability_var
from engine.entities.pathfinding.board import Board
from engine.runner.components import StatsComponent
from engine.runner.messages import AttackUnitMessage
from engine.runner.prng import IntBasedMersenneTwister
from engine.runner.runner import Runner
from engine.runner.snapshot import load_state

PYDIR = Path(__file__).resolve().parent


def rpc(sid, m, b=None, t=60):
    r = R._rpc(sid, m, [b] if b is not None else [], timeout=t)
    return r.get("result") if isinstance(r, dict) and "result" in r else r


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", default="777")
    ap.add_argument("--board", default="MC1_67")
    ap.add_argument("--move", action="store_true", default=True)
    ap.add_argument("--no-move", dest="move", action="store_false")
    ap.add_argument("--state-file",
                    default=str(Path(__file__).resolve().parents[2] /
                                "logs" / "runners" / "probe-avalanche.json"))
    args = ap.parse_args()
    sid = R._resolve_session()
    Path(args.state_file).parent.mkdir(parents=True, exist_ok=True)
    argv = [sys.executable, "rl_duel.py", "build", "--seed", args.seed, "--board", args.board,
            "--state-file", args.state_file, "--p-units", "astraBullgryn",
            "--a-units", "necroOverlord,necroWarden", "--hp-target", "120000",
            "--hp-player", "120000", "--no-ai"]
    p = subprocess.run(argv, cwd=str(PYDIR), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if not Path(args.state_file).exists():
        print("BUILD KO", (p.stderr or p.stdout)[-500:]); return
    rid = json.loads(Path(args.state_file).read_text())["runnerId"]
    print("runner", rid, "move(charge) =", args.move)
    try:
        bg = rpc(sid, "boardGraph", {"runnerId": rid}, 60)
        byid = {t["id"]: t for t in bg["tiles"]}
        bypos = {(t["col"], t["row"]): t["id"] for t in bg["tiles"]}
        board = Board(bg["tiles"], adjacency="native_sym")

        def dview():
            return rpc(sid, "decisionView", {"runnerId": rid, "maxRank": 1,
                                             "allAbilities": True}, 90)

        def move(uid, tid):
            c = byid[tid]
            return rpc(sid, "applyAction", {"runnerId": rid, "action": {
                "kind": "move", "unitId": uid, "to": {"col": c["col"], "row": c["row"]}}}, 40)

        dv = dview()
        units = [u for u in (dv.get("units") or []) if u.get("alive")]
        me = next(u for u in units if u.get("visualId") == "astraBullgryn")
        myp = me.get("owner")
        ens = [u for u in units if u.get("owner") != myp]
        tgt = ens[0]
        def nb(tid):
            return [n for n in (byid[tid].get("neighbours") or []) if n in byid]
        cands = sorted(t for t in byid if len(nb(t)) == 6)
        centre = cands[len(cands) // 2]
        move(tgt["id"], centre)
        move(ens[1]["id"], nb(centre)[3])
        if not args.move:
            move(me["id"], nb(centre)[0])                 # place AVANT le tour -> pas de charge
        rpc(sid, "applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 40)
        rpc(sid, "applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 40)
        if args.move:
            move(me["id"], nb(centre)[0])                 # <- LE deplacement du tour = la CHARGE

        dv = dview()
        units = [u for u in (dv.get("units") or []) if u.get("alive")]
        pos = {u["id"]: (u["pos"]["col"], u["pos"]["row"]) for u in units}
        print("caster", me["id"], pos[me["id"]], "cible", tgt["id"], pos[tgt["id"]],
              "dist", hexgeo.distance(pos[me["id"]], pos[tgt["id"]]))
        ob = rpc(sid, "observeBattle", {"runnerId": rid}, 40)
        snap = rpc(sid, "combatSnapshot", {"runnerId": rid}, 40)
        s0 = rpc(sid, "dumpRng", {"runnerId": rid}, 30)
        # l'attaque NORMALE est un ActiveAbilityType PAR UNITE (kind='normal' du decisionView)
        nab = next((a.get("id") for u in (dv.get("units") or []) if u.get("id") == me["id"]
                    for a in (u.get("abilities") or []) if a.get("kind") == "normal"), None)
        print("normal attack abilityType =", nab)
        res = rpc(sid, "applyAction", {"runnerId": rid, "action": {
            "kind": "ability", "casterId": me["id"], "targetId": tgt["id"],
            "abilityType": nab}}, 60)
        live = []
        for a in (res.get("actions") or []):
            for e in (a.get("events") or []):
                td = e.get("tags")
                if isinstance(td, str):
                    td = json.loads(td)
                if td and "Amount" in td and td.get("Attacker_Id") == me["id"]:
                    live.append(td["Amount"])
        if not live:
            print("RAW cast:", json.dumps(res)[:1500])
        st = load_state(dv, ob, snap, board=board)
        rng = IntBasedMersenneTwister(); rng.mt = list(s0["mt"]); rng.mti = s0["mti"]
        st.rng = rng
        runner = Runner(st).install_default_handlers(20)
        runner.apply(AttackUnitMessage(attacker_id=me["id"], target_id=tgt["id"]))
        off = (runner.damage_handler.last or {}).get("per_hit") or []
        print("LIVE per-coup :", live)
        print("OFF  per-coup :", list(off))
        print("delta         :", [l - o for l, o in zip(live, off)])
        ce = st.get_entity(me["id"])
        cctx = ce.get_component(StatsComponent).ctx
        lvl = getattr(cctx, "passive_ability_level", None)
        mult = int(getattr(cctx, "ability_variables_multiplier", 100) or 100)
        print("passive_level=%s mult=%s%% -> AvalancheOfMuscle.extraDmg = %s"
              % (lvl, mult, ability_var("AvalancheOfMuscle", "extraDmg", lvl, multiplier_pct=mult)))
    finally:
        rpc(sid, "disposeRunner", {"runnerId": rid}, 20)


if __name__ == "__main__":
    main()
