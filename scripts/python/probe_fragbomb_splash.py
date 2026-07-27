"""Probe #1017 FragBomb (astraBullgryn « Kut Skoden ») -- GEOMETRIE + ORDRE du volet splash.

`IdunBattleLogic.Entities.Abilities.Active.Loki.FragBombAbility$$ExecuteBehaviour` (DECOMPILE) :
    splash = AdjacentUnits(Target@0x178, 0, 3) - Caster@0x160
    main   = AttackDamage(Caster@0x160, ActiveTarget@0x180, MinMaxDamage, GetDamageProfile(0),
                          Get(GetNumberConstant(0x2f)=nrOfHits), <AbilityOrEffect>)
    splashA= idem avec Get(GetNumberConstant(0x32)=nrOfHits_2)
    ExecuteAtomic( SortedAttackSeries(Caster@0x160, Units(Target@0x178,1,1), main, splash, splashA,
                                      <AbilityOrEffect>), entities, 0x43 )

Ce probe DRIVE les deux camps (applyAction ignore propriete/portee) pour poser une cible entouree,
caste, et imprime l'ORDRE et les COUPS par unite touchee -> confronte le mirror (main = nrOfHits sur
la cible ; splash = nrOfHits_2 sur TOUTE unite adjacente a la cible, caster exclu -- FRIENDLY-FIRE
comme Stikkbomb, cf. i2 « ALL units adjacent to the target hex, except Kut Skoden himself »).

Usage : python probe_fragbomb_splash.py [--seed 777]
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

PYDIR = Path(__file__).resolve().parent
FRAGBOMB = 1017


def rpc(sid, m, b=None, t=60):
    r = R._rpc(sid, m, [b] if b is not None else [], timeout=t)
    return r.get("result") if isinstance(r, dict) and "result" in r else r


def build(state_file, seed, board, extra):
    argv = [sys.executable, "rl_duel.py", "build", "--seed", str(seed), "--board", board,
            "--state-file", state_file, *extra]
    p = subprocess.run(argv, cwd=str(PYDIR), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    sf = Path(state_file)
    if not sf.exists():
        print("BUILD KO:", (p.stderr or p.stdout or "")[-900:])
        raise SystemExit(2)
    return json.loads(sf.read_text())["runnerId"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", default="777")
    ap.add_argument("--board", default="MC1_67")
    ap.add_argument("--state-file",
                    default=str(Path(__file__).resolve().parents[2] /
                                "logs" / "runners" / "probe-fragbomb.json"))
    ap.add_argument("--keep", action="store_true")
    args = ap.parse_args()
    sid = R._resolve_session()
    Path(args.state_file).parent.mkdir(parents=True, exist_ok=True)
    rid = build(args.state_file, args.seed, args.board,
                ["--p-units", "astraBullgryn,astraCreed",
                 "--a-units", "necroOverlord,necroWarden,necroDestroyer,necroSpyder",
                 "--hp-target", "90000", "--hp-player", "90000", "--no-ai"])
    print("runner", rid)
    try:
        bg = rpc(sid, "boardGraph", {"runnerId": rid}, 60)
        tiles = bg["tiles"]
        bypos = {(t["col"], t["row"]): t["id"] for t in tiles}
        byid = {t["id"]: t for t in tiles}
        dv = rpc(sid, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
        units = [u for u in (dv.get("units") or []) if u.get("alive")]
        me = next(u for u in units if u.get("visualId") == "astraBullgryn")
        ally = next(u for u in units if u.get("visualId") == "astraCreed")
        myp = me.get("owner")
        ens = [u for u in units if u.get("owner") != myp]
        print("caster", me["id"], "ally", ally["id"], "enemies", [e["id"] for e in ens])

        # --- geometrie : cible T sur une tuile a 6 voisins ; caster + 1 allie + 2 ennemis autour ---
        def nb_ids(tid):
            return [n for n in (byid[tid].get("neighbours") or []) if n in byid]
        cands = [tid for tid in byid if len(nb_ids(tid)) == 6]
        if not cands:
            print("aucune tuile a 6 voisins"); return
        # tuile centrale (max de voisins a 6 voisins eux-memes) pour laisser de la place
        centre = sorted(cands)[len(cands) // 2]
        ring = nb_ids(centre)
        tgt = ens[0]
        placements = [(tgt["id"], centre), (me["id"], ring[0]), (ally["id"], ring[1]),
                      (ens[1]["id"], ring[2]), (ens[2]["id"], ring[3]),
                      (ens[3]["id"], ring[5])]
        for uid, tid in placements:
            c = byid[tid]
            r = rpc(sid, "applyAction", {"runnerId": rid, "action": {
                "kind": "move", "unitId": uid, "to": {"col": c["col"], "row": c["row"]}}}, 40)
            if not (isinstance(r, dict) and r.get("ok")):
                print("move KO", uid, tid, str(r)[:200])
        dv = rpc(sid, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
        units = [u for u in (dv.get("units") or []) if u.get("alive")]
        posu = {u["id"]: (u["pos"]["col"], u["pos"]["row"]) for u in units}
        tp = posu[tgt["id"]]
        ttile = bypos[tp]
        print("cible", tgt["id"], tp, "tile", ttile, "voisins natifs", nb_ids(ttile))
        for u in units:
            print("  u%-3d %-16s %s tile=%-4s dist_cible=%d %s"
                  % (u["id"], u.get("visualId"), posu[u["id"]], bypos.get(posu[u["id"]]),
                     hexgeo.distance(tp, posu[u["id"]]),
                     "MINE" if u.get("owner") == myp else "ENEMY"))
        s0 = rpc(sid, "dumpRng", {"runnerId": rid}, 30)
        res = rpc(sid, "applyAction", {"runnerId": rid, "action": {
            "kind": "ability", "casterId": me["id"], "targetId": tgt["id"],
            "abilityType": FRAGBOMB}}, 90)
        a0 = (res.get("actions") or [{}])[0]
        print("cast ok:", res.get("ok"), a0.get("ok"), a0.get("error"))
        seq, per = [], {}
        for a in (res.get("actions") or []):
            for e in (a.get("events") or []):
                td = e.get("tags")
                if isinstance(td, str):
                    td = json.loads(td)
                if not td:
                    continue
                if td.get("Active_Ability_Type") == FRAGBOMB and "Amount" in td:
                    seq.append((td["Target_Id"], td["Amount"], td.get("Attack_Is_First_Hit")))
                    per[td["Target_Id"]] = per.get(td["Target_Id"], 0) + 1
                elif "Effect_Id" in td and "Effect_SourceId" in td:
                    seq.append(("effect", td))
        print("ordre live des coups :")
        for s in seq:
            print("   ", s)
        print("coups par unite :", per)
        print("rng mti avant :", s0.get("mti"))
    finally:
        if not args.keep:
            rpc(sid, "disposeRunner", {"runnerId": rid}, 20)


if __name__ == "__main__":
    main()
