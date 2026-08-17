"""Probe #1026 BasiliskBarrage -- ORDRE DES TIRAGES + ORDRE DU POOL de `PickRandomly`.

`IdunBattleLogic.Entities.Abilities.Active.Loki.BasiliskBarrageAbility$$ExecuteBehaviour` tire ses obus
via TROIS `IdunBattleLogic.Entities.DSLSelectors$$PickRandomly(<tuiles>, <n>, allowRepeat=1,
maxRepeats=0x7fffffff)` puis attaque les tuiles tirees (`AttackWithAbilityDamage`, nrOfHits coups par
obus). `IdunBattle.Entities.Selectors.PickRandomAmountSelector$$Select` fait
`candidates.ElementAt(rng.NextInternal(0, candidates.Count))` : l'ORDRE du pool ET l'ORDRE des trois
tirages decident QUELLES tuiles sont touchees.

Ce probe capture l'etat MT (`dumpRng`) juste avant le cast, mesure le MULTI-ENSEMBLE de tuiles
reellement touchees (events live, multiplicites comprises), puis confronte plusieurs HYPOTHESES
(ordre des 3 tirages x ordre du pool) au rejeu offline du meme MT.

Usage (scripts/python, session warmee) :
    python probe_basilisk_shell_rng.py --seeds 777,31337,4242,999,12345
ASCII only.
"""
from __future__ import annotations

import argparse
import itertools
import json
import subprocess
import sys
from pathlib import Path

import hexgeo
import rl_collect_batch as R
from engine.runner.prng import IntBasedMersenneTwister

PYDIR = Path(__file__).resolve().parent
BASILISK = 1026


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
        print("BUILD KO:", (p.stderr or p.stdout or "")[-800:])
        raise SystemExit(2)
    return json.loads(sf.read_text())["runnerId"]


def capture(sid, rid, board_id):
    """Un cast -> (contexte geometrique, etat MT avant, multi-ensemble de tuiles touchees)."""
    bg = rpc(sid, "boardGraph", {"runnerId": rid}, 60)
    tiles = bg["tiles"]
    bypos = {(t["col"], t["row"]): t["id"] for t in tiles}
    raw_nb = {t["id"]: [n for n in (t.get("neighbours") or []) if n in bypos.values()]
              for t in tiles}
    dv = rpc(sid, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    units = [u for u in (dv.get("units") or []) if u.get("alive")]
    me = next(u for u in units if u.get("visualId") == "astraOrdnance")
    myp = me.get("owner")
    ens = [u for u in units if u.get("owner") != myp]
    tgt = ens[0]
    tp = (tgt["pos"]["col"], tgt["pos"]["row"])
    ttile = bypos[tp]
    ring1 = sorted(bypos[q] for q in bypos if hexgeo.distance(tp, q) == 1)
    ring2 = sorted(bypos[q] for q in bypos if hexgeo.distance(tp, q) == 2)
    pos_of = {u["id"]: (u["pos"]["col"], u["pos"]["row"]) for u in units}
    s0 = rpc(sid, "dumpRng", {"runnerId": rid}, 30)
    res = rpc(sid, "applyAction", {"runnerId": rid, "action": {
        "kind": "ability", "casterId": me["id"], "targetId": tgt["id"],
        "abilityType": BASILISK}}, 90)
    hits_per_unit, empties, seq = {}, [], []
    for a in (res.get("actions") or []):
        for e in (a.get("events") or []):
            td = e.get("tags")
            if isinstance(td, str):
                td = json.loads(td)
            if not td:
                continue
            if "Damage_Empty_Target_Tile_Id" in td:
                empties.append(td["Damage_Empty_Target_Tile_Id"])
                seq.append(("empty", td["Damage_Empty_Target_Tile_Id"]))
            elif td.get("Active_Ability_Type") == BASILISK and "Amount" in td:
                uid = td["Target_Id"]
                hits_per_unit[uid] = hits_per_unit.get(uid, 0) + 1
                seq.append(("hit", uid, td["Amount"], td.get("Attack_Is_First_Hit")))
    hit_tiles = []
    for uid, n in hits_per_unit.items():
        assert n % 2 == 0, f"unit {uid}: {n} coups (nrOfHits=2 attendu par obus)"
        hit_tiles += [bypos[pos_of[uid]]] * (n // 2)
    got = sorted(empties + hit_tiles)
    return {"board": board_id, "ttile": ttile, "ring1": ring1, "ring2": ring2,
            "raw_nb": raw_nb.get(ttile, []), "mt": s0, "got": got, "seq": seq,
            "caster": me["id"], "target": tgt["id"]}


def replay(mt, pools_in_order):
    """Rejoue le MT : pour chaque (pool, n) dans l'ordre, n tirages allowRepeat."""
    rng = IntBasedMersenneTwister()
    rng.mt = list(mt["mt"]); rng.mti = mt["mti"]
    out = []
    for pool, n in pools_in_order:
        for _ in range(n):
            if not pool:
                break
            out.append(pool[rng.next_internal(0, len(pool))])
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", default="777,31337,4242,999,12345")
    ap.add_argument("--board", default="MC1_67")
    ap.add_argument("--state-file",
                    default=str(Path(__file__).resolve().parents[2] /
                                "logs" / "runners" / "probe-basilisk-rng.json"))
    args = ap.parse_args()
    sid = R._resolve_session()
    Path(args.state_file).parent.mkdir(parents=True, exist_ok=True)
    caps = []
    for seed in args.seeds.split(","):
        rid = build(args.state_file, seed.strip(), args.board,
                    ["--p-units", "astraOrdnance",
                     "--a-units", "necroOverlord,necroWarden,necroDestroyer,necroSpyder",
                     "--hp-target", "60000", "--hp-player", "60000", "--no-ai"])
        try:
            c = capture(sid, rid, args.board)
        finally:
            rpc(sid, "disposeRunner", {"runnerId": rid}, 20)
        c["seed"] = seed.strip()
        caps.append(c)
        print("seed %-6s rid=%-4d ttile=%-4d ring1=%s ring2=%s -> touches=%s"
              % (c["seed"], rid, c["ttile"], c["ring1"], c["ring2"], c["got"]))

    # --- HYPOTHESES : ordre des 3 tirages x ordre du pool ---------------------
    # tour 1 -> guaranteed = max(0, TurnsStarted-1) = 0, miss = 5-3-0 = 2, maybe = 5-0-2 = 3
    NMISS, NMAYBE, NGUAR = 2, 3, 0
    def pools(c, pool_order, seq_order):
        r1 = list(c["ring1"]); r2 = list(c["ring2"]); t = c["ttile"]
        if pool_order == "asc":
            miss, maybe = sorted(r2), [t] + sorted(r1)
        elif pool_order == "asc_maybe_sorted":
            miss, maybe = sorted(r2), sorted([t] + r1)
        elif pool_order == "nb":                     # ring1 = ordre NATIF des voisins
            nb = [n for n in c["raw_nb"]]
            miss, maybe = sorted(r2), [t] + nb
        else:
            raise ValueError(pool_order)
        by = {"miss": (miss, NMISS), "maybe": (maybe, NMAYBE), "guar": ([t], NGUAR)}
        return [by[k] for k in seq_order]

    orders = list(itertools.permutations(("miss", "maybe", "guar")))
    for pool_order in ("asc", "asc_maybe_sorted", "nb"):
        for seq_order in orders:
            hits = sum(1 for c in caps
                       if sorted(replay(c["mt"], pools(c, pool_order, seq_order))) == c["got"])
            print("pool=%-17s ordre=%-22s -> %d/%d %s"
                  % (pool_order, ",".join(seq_order), hits, len(caps),
                     "OK" if hits == len(caps) else ""))

    # --- BRUTE-FORCE de l'ORDRE des deux pools (geometrie identique sur tous les seeds) ------
    r2 = caps[0]["ring2"]; r1 = caps[0]["ring1"]; t = caps[0]["ttile"]
    if all(c["ring2"] == r2 and c["ring1"] == r1 and c["ttile"] == t for c in caps):
        best = []
        for pm in itertools.permutations(r2):
            for pa in itertools.permutations([t] + r1):
                n = sum(1 for c in caps
                        if sorted(replay(c["mt"], [(list(pm), NMISS), (list(pa), NMAYBE),
                                                   ([t], NGUAR)])) == c["got"])
                best.append((n, pm, pa))
        best.sort(key=lambda x: -x[0])
        print("\n[brute-force ordre des pools] top 6 :")
        for n, pm, pa in best[:6]:
            print("  %d/%d  miss=%s  maybe=%s" % (n, len(caps), list(pm), list(pa)))
        full = [(pm, pa) for n, pm, pa in best if n == len(caps)]
        print("  solutions PARFAITES : %d" % len(full))
        for pm, pa in full:
            print("    miss=%s maybe=%s" % (list(pm), list(pa)))


if __name__ == "__main__":
    main()
