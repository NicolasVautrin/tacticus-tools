"""Probe #38b — valider la branche free==0 (Tan ENCERCLE -> emit inconditionnel) NATIVEMENT.

But : construire un etat ou count>0 (ennemi adjacent), cap=False (0 summon), et
GetFreeAdjacentTiles(caster)==0 (tous les voisins libres occupes) -> le natif DOIT emettre 1118
(branche `jle cb1d` du desassemblage). On DRIVE Tan vers un bord/coin, on amene ennemis+allie sur
ses voisins, et a chaque tour de Tan on lit ncEvaluate + free-adj (mirror) tant que 0 summon.
Capture le 1er etat free==0 & count>0 & cap=False et son leaf_emit. Console ASCII.
"""
from __future__ import annotations

import json
import subprocess
import sys
from collections import deque
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
ROOT = Path(r"C:\Users\nicolasv\tacticus-tools")
sys.path.insert(0, str(PYDIR))

from rl_collect_batch import _resolve_session, _rpc  # noqa: E402

STATE = ROOT / "data" / "_solver38b_free0_state.json"
TAN_VIS = "admecMarshall"
SUMMON_LIVE = "admecNpc1Vanguard"
ENEMY_VIS = "necroWarden"
BUILD = ["build", "--seed", "4242", "--state-file", str(STATE),
         "--roster", "1", "--p-units", f"{TAN_VIS},admecRuststalker",
         "--a-units", f"{ENEMY_VIS},{ENEMY_VIS}", "--board", "MC1_67"]


def main() -> int:
    proc = subprocess.run([sys.executable, "rl_duel.py", *BUILD], cwd=str(PYDIR),
                          capture_output=True, text=True, encoding="utf-8", errors="replace")
    if not STATE.exists():
        print("[free0] build KO:", (proc.stderr or proc.stdout or "")[-300:])
        return 1
    rid = json.loads(STATE.read_text())["runnerId"]
    sid = _resolve_session()
    print(f"[free0] runner={rid}")

    def _r(m, b, t=60):
        return _rpc(sid, m, [b], timeout=t).get("result") or {}

    bg = _r("boardGraph", {"runnerId": rid}, 60)
    idc = {t.get("id"): (t.get("col"), t.get("row")) for t in (bg.get("tiles") or [])}
    neigh_by_pos, walkable = {}, {}
    for t in (bg.get("tiles") or []):
        k = (t.get("col"), t.get("row"))
        walkable[k] = bool(t.get("walkable"))
        neigh_by_pos[k] = [idc[n] for n in (t.get("neighbours") or []) if n in idc]

    def dv_tan():
        dec = _r("decisionView", {"runnerId": rid, "allAbilities": True}, 150)
        tan = next((u for u in (dec.get("units") or []) if u.get("visualId") == TAN_VIS
                    and u.get("alive")), None)
        return dec, tan

    def advance():
        for _ in range(30):
            dec, tan = dv_tan()
            if tan is None:
                return None, None
            if dec.get("currentPlayer") == tan.get("owner"):
                return dec, tan
            _r("applyAction", {"runnerId": rid, "action": {"kind": "endturn"},
                               "captureEvents": False}, 60)
        return None, None

    def occ_live():
        ob = _r("observeBattle", {"runnerId": rid}, 60)
        return ob, {(u.get("col"), u.get("row")) for u in (ob.get("units") or [])
                    if not u.get("isDead") and u.get("col") is not None}

    def free_adj(pos, occ):
        from engine import battle_query as bq
        return bq.adjacent_addable_count(pos, neigh_by_pos, walkable, occ - {pos}, None)

    def bfs(start):
        seen = {start: 0}; q = deque([start])
        while q:
            x = q.popleft()
            for n in neigh_by_pos.get(x, []):
                if n not in seen:
                    seen[n] = seen[x] + 1; q.append(n)
        return seen

    def move_unit(uid, dest):
        _r("applyAction", {"runnerId": rid, "action": {"kind": "move", "unitId": uid,
                           "to": {"col": dest[0], "row": dest[1]}}}, 40)

    def reach(uid):
        mt = _r("aiMovableTiles", {"runnerId": rid, "side": "friendly"}, 60)
        mte = _r("aiMovableTiles", {"runnerId": rid, "side": "enemy"}, 60)
        for src in (mt, mte):
            cmt = next((x for x in (src.get("units") or []) if x.get("unitId") == uid), None)
            if cmt:
                return [(t["col"], t["row"]) for t in (cmt.get("tiles") or [])
                        if t.get("col") is not None]
        return []

    best = None
    for turn in range(30):
        dec, tan = advance()
        if tan is None:
            break
        ob, occ = occ_live()
        summ = len({u.get("squadId") for u in (ob.get("units") or [])
                    if u.get("visualId") == SUMMON_LIVE})
        if summ > 0:
            print(f"[free0] turn {turn}: summons deja apparus ({summ}) -> cap non-nul, stop craft")
            break
        pos = (tan.get("pos") or {})
        org = (pos.get("col"), pos.get("row"))
        fa = free_adj(org, occ)
        # count : fromHere de l'attaque normale
        na = next((a for a in (tan.get("abilities") or [])
                   if a.get("kind") == "normal" and a.get("id") is not None), None)
        fh = 0
        if na:
            at = _r("abilityTargets", {"runnerId": rid, "unitId": tan["id"],
                                       "abilityId": na["id"]}, 60)
            for uu in (at.get("units") or []):
                if uu.get("unitId") == tan["id"]:
                    for a in (uu.get("abilities") or []):
                        if a.get("abilityId") == na["id"]:
                            fh = int(a.get("fromHereCount") or 0)
        print(f"  turn {turn} tan@{org} free={fa} count={fh} summ={summ}")
        if fh > 0 and fa == 0:
            ncev = _r("ncEvaluate", {"runnerId": rid, "unitId": tan["id"],
                                     "abilityType": 1118, "sweep": False}, 60)
            p0 = (ncev.get("positions") or [{}])[0]
            emit = bool(p0.get("action")) and p0.get("util") is not None
            best = {"org": org, "free": fa, "count": fh, "summ": summ,
                    "leaf_emit": emit, "util": p0.get("util")}
            print(f"  *** FREE==0 & count>0 & cap-false : leaf_emit={emit} util={p0.get('util')} ***")
            break
        # sinon : essayer d'amener enemies + allie sur les voisins libres de Tan pour saturer.
        occ_now = occ
        free_ring = [n for n in neigh_by_pos.get(org, [])
                     if walkable.get(n) and n not in occ_now]
        others = [u for u in (dec.get("units") or [])
                  if u.get("alive") and u.get("id") != tan["id"]
                  and (u.get("pos") or {}).get("col") is not None]
        moved = False
        for slot in free_ring:
            # trouver une unite (n'importe quel camp) qui peut atteindre `slot`
            for u in others:
                up = (u.get("pos") or {})
                if (up.get("col"), up.get("row")) == slot:
                    continue
                rr = reach(u["id"])
                if slot in rr:
                    move_unit(u["id"], slot)
                    moved = True
                    break
            if moved:
                break
        if not moved:
            # rapprocher Tan d'un ennemi pour garantir count>0 au prochain tour, sinon endturn
            enemies = [u for u in others if u.get("owner") != tan.get("owner")]
            if enemies and fh == 0:
                et = (enemies[0]["pos"]["col"], enemies[0]["pos"]["row"])
                dgoal = bfs(et)
                rr = reach(tan["id"])
                pool = [t for t in rr if t in dgoal and dgoal[t] >= 1]
                if pool:
                    move_unit(tan["id"], min(pool, key=lambda t: dgoal[t]))
            _r("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 40)

    _r("disposeRunner", {"runnerId": rid}, 20)
    try:
        STATE.unlink()
    except OSError:
        pass
    print(f"[free0] RESULT: {json.dumps(best)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
