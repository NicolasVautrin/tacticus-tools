"""PROBE #passifs-DA — aura stat-mod LionHelm (BlockDamage 1214 / BlockChance 1232) : offline == live.

Mesure les DEUX faces sur un runner isole (board MC1_67) :
  * SEED     : `combatSnapshot` live (GetStat resolu) vs `UnitStats` offline apres `load_state`
               -> l'attribution de `attribute_aura_stat_modifiers` ne doit RIEN changer a Current.
  * MOBILITE : on ELOIGNE un allie hors du rayon 2 puis on le RAMENE, en live ET offline
               (`MoveUnitMessage`), et on exige la MEME valeur des deux cotes a chaque etape.

Cas discriminants embarques :
  - allie Dark Angels a portee     -> blockDamage ET blockChance
  - allie NON Dark Angels a portee -> blockDamage SEUL (gate UnitsFromFaction(DarkAngels))
  - allie hors rayon               -> RIEN (cas NEGATIF)
  - le porteur lui-meme            -> RIEN (SurroundingFriends exclut la source)

Usage : python probe_lionhelm_block_aura.py [--runner N]   (build automatique sinon). ASCII only.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import urllib.request
from pathlib import Path

BASE = "http://127.0.0.1:8765"
CARRIER = "darkaAzrael"          # LionHelm
ALLY_DA = "darkaHellblaster"     # ami DARK ANGELS (blockDamage + blockChance)
ALLY_OTHER = "ultraApothecary"   # ami NON Dark Angels (blockDamage seul)
FOE = "necroOverlord"
BOARD = "MC1_67"


def rpc(method, args=None, timeout=90000):
    body = json.dumps({"method": method, "args": args or {}, "timeout": timeout}).encode()
    req = urllib.request.Request(BASE + "/api/scripts/1/rpc", data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=180) as r:
        out = json.loads(r.read().decode())
    if "error" in out and out.get("result") is None:
        raise RuntimeError(str(out["error"])[:300])
    return out.get("result", out)


def build(state_file: Path) -> int:
    cmd = [sys.executable, "rl_duel.py", "build", "--seed", "4242", "--board", BOARD,
           "--roster", "1", "--p-units", ",".join([CARRIER, ALLY_DA, ALLY_OTHER]),
           "--a-units", FOE, "--state-file", str(state_file)]
    subprocess.run(cmd, cwd=str(Path(__file__).parent), check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
    return int(json.loads(state_file.read_text(encoding="utf-8"))["runnerId"])


def live_blocks(rid):
    snap = rpc("combatSnapshot", {"runnerId": rid})
    return {int(u["entityId"]): (int((u.get("stats") or {}).get("blockChance") or 0),
                                 int((u.get("stats") or {}).get("blockDamage") or 0))
            for u in (snap.get("units") or [])}


def offline_state(rid):
    from engine.entities.pathfinding.board import Board
    from engine.runner.snapshot import load_state
    dv = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True})
    ob = rpc("observeBattle", {"runnerId": rid})
    snap = rpc("combatSnapshot", {"runnerId": rid})
    bg = rpc("boardGraph", {"runnerId": rid})
    board = Board(bg["tiles"], adjacency="native_sym") if (bg or {}).get("tiles") else None
    return load_state(dv, ob, snap, board=board), dv


def offline_blocks(state):
    from engine.runner.components import StatsComponent
    from engine.entities.stats import StatType
    out = {}
    for uid, e in state.entities.items():
        sc = e.get_component(StatsComponent)
        if sc is None or sc.ctx is None:
            continue
        out[int(uid)] = (int(sc.ctx.stat(StatType.BLOCK_CHANCE)),
                         int(sc.ctx.stat(StatType.BLOCK_DAMAGE)))
    return out


def ids_of(dv):
    return {u.get("visualId"): u["id"] for u in (dv.get("units") or []) if u.get("alive")}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runner", type=int)
    ap.add_argument("--state-file", default=None)
    a = ap.parse_args()
    sf = Path(a.state_file) if a.state_file else \
        Path(__file__).resolve().parents[2] / "logs" / "runners" / "probe_lh_block.json"
    sf.parent.mkdir(parents=True, exist_ok=True)
    rid = a.runner or build(sf)
    print("runner=%d board=%s" % (rid, BOARD))

    from engine.runner.runner import Runner
    from engine.runner.messages import MoveUnitMessage

    state, dv = offline_state(rid)
    ids = ids_of(dv)
    az, da, other = ids[CARRIER], ids[ALLY_DA], ids[ALLY_OTHER]
    runner = Runner(state).install_default_handlers(20)
    ok = True

    def step(label):
        nonlocal ok
        lv, off = live_blocks(rid), offline_blocks(state)
        print("  [%s]" % label)
        for name, uid in ((CARRIER, az), (ALLY_DA, da), (ALLY_OTHER, other)):
            l, o = lv.get(uid), off.get(uid)
            flag = "OK " if l == o else "MISMATCH"
            if l != o:
                ok = False
            print("    %-8s u%-4s %-18s live(bc,bd)=%-12s off=%-12s" % (flag, uid, name, l, o))

    def move(uid, col, row):
        rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "move", "unitId": uid, "to": {"col": col, "row": row}}}, 40000)
        runner.apply(MoveUnitMessage(uid, (col, row)))

    step("SEED (allies a portee)")
    move(da, 5, 5)
    step("ally DA ELOIGNE (5,5) - cas NEGATIF")
    move(other, 4, 4)
    step("ally non-DA ELOIGNE (4,4) - cas NEGATIF")
    move(da, 1, 1)
    step("ally DA REVENU (1,1)")
    move(other, 2, 0)
    step("ally non-DA REVENU (2,0)")

    print("VERDICT:", "OK offline == live sur toutes les etapes" if ok else "MISMATCH (cf. ci-dessus)")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
