"""Probe LIVE — confirmer + mesurer un OVERWATCH déclenché par un MOVE.

Objectif : vérité-terrain pour la tranche 1 (move + cascade after-move). On bâtit un
runner (seed 777 = a eldarMauganRa team2, overwatch ranged), on bouge une unité team1
vers l'ennemi ranged le plus proche, et on diffe l'état avant/après pour isoler :
  - qui a pris des dégâts SANS être la cible d'une attaque volontaire (= overwatch),
  - quel watcher a tiré (effet/cooldown consommé).

NB : c'est une CONFIRMATION du mécanisme RE'd (Overwatch_AutoAttackEffect via
EvaluateAfterMoveTriggers), pas une découverte par expérimentation. Usage :
  python _probe_overwatch.py [--seed 777]
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import rl_collect_batch as R

ROOT = Path(__file__).resolve().parents[2]
# State-file dedie (pas le duel_state.json partage) : depuis le replace scope
# de `rl_duel build` (2026-07-03), un build dispose le runner enregistre dans
# SON state-file — sur le fichier par defaut ca toucherait le runner de
# travail de l'utilisateur.
STATE = ROOT / "logs" / "runners" / "_probe_overwatch_state.json"


def _res(r):
    return r.get("result") if isinstance(r, dict) and "result" in r else r


def rpc(sid, m, b, t=60):
    return _res(R._rpc(sid, m, [b] if b is not None else [], timeout=t))


def cheby(a, b):
    return max(abs(a[0] - b[0]), abs(a[1] - b[1]))


def snap(sid, rid):
    dv = rpc(sid, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    ob = rpc(sid, "observeBattle", {"runnerId": rid}, 40)
    hp = {u["squadId"]: u["hp"] for u in (ob.get("units") or []) if u.get("squadId") is not None}
    units = {}
    for u in (dv.get("units") or []):
        units[u["id"]] = {
            "vis": u.get("visualId"), "team": u.get("team"), "alive": u.get("alive"),
            "pos": (u["pos"]["col"], u["pos"]["row"]) if u.get("pos") else None,
            "hp": hp.get(u["id"]),
            "effects": sorted(e.get("name") for e in (u.get("effects") or []) if e.get("name")),
        }
    return units, dv.get("currentPlayer")


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=777)
    a = ap.parse_args(argv)
    sid = R._resolve_session()
    subprocess.run([sys.executable, "rl_duel.py", "build", "--seed", str(a.seed),
                    "--state-file", str(STATE)],
                   capture_output=True, text=True, encoding="utf-8", errors="replace")
    rid = json.loads(STATE.read_text())["runnerId"]
    print(f"[probe] session={sid} runner={rid} seed={a.seed}")

    before, cur = snap(sid, rid)
    my_team = 1 if cur == 3 else 2          # currentPlayer 3 -> team1, 4 -> team2
    enemies = [(uid, u["pos"]) for uid, u in before.items()
               if u["team"] != my_team and u["alive"] and u["pos"]]
    print(f"[probe] currentPlayer={cur} myTeam={my_team} enemies={len(enemies)}")

    # mover = unité team1 dont on peut se rapprocher le plus d'un ennemi
    mov = rpc(sid, "aiMovableTiles", {"runnerId": rid}, 60)
    best = None  # (dist, unitId, tile)
    for mu in (mov.get("units") or []):
        uid = mu.get("unitId")
        if uid not in before or before[uid]["team"] != my_team:
            continue
        for t in (mu.get("tiles") or []):
            if t.get("col") is None:
                continue
            tile = (t["col"], t["row"])
            d = min(cheby(tile, e[1]) for e in enemies)
            if best is None or d < best[0]:
                best = (d, uid, tile)
    if best is None:
        print("[probe] aucun move team1 dispo"); rpc(sid, "disposeRunner", {"runnerId": rid}, 20); return 1
    _, mover, tile = best
    print(f"[probe] move u{mover} ({before[mover]['vis']}) {before[mover]['pos']} -> {tile} "
          f"(dist min ennemi={best[0]})")

    rpc(sid, "applyAction", {"runnerId": rid, "action": {
        "kind": "move", "unitId": mover, "to": {"col": tile[0], "row": tile[1]}}}, 40)

    after, _ = snap(sid, rid)
    print("\n=== DIFF avant/après move ===")
    fired = False
    for uid in sorted(before):
        b, af = before[uid], after.get(uid, {})
        dhp = (af.get("hp") or 0) - (b.get("hp") or 0)
        deff = set(af.get("effects") or []) ^ set(b.get("effects") or [])
        if dhp != 0 or deff or b["pos"] != af.get("pos"):
            tag = ""
            if dhp < 0 and uid == mover:
                tag = "  <<< MOVER a pris des dégâts (OVERWATCH probable)"; fired = True
            print(f"  u{uid:<3} {b['vis']:<18} t{b['team']} hp{b['hp']}->{af.get('hp')} "
                  f"(Δ{dhp:+}) pos{b['pos']}->{af.get('pos')} effΔ{sorted(deff) or ''}{tag}")
    print(f"\n[probe] overwatch déclenché sur le mover : {fired}")
    rpc(sid, "disposeRunner", {"runnerId": rid}, 20)
    print(f"[probe] disposed {rid}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
