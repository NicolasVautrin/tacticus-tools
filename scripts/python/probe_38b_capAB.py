"""Probe #38b — A/B DISCRIMINANT natif : la branche count>0 emet-elle par CAP ou par free==0 ?

Craft : Tan (admecMarshall) + 1 ennemi, board MC1_67. On DRIVE Tan adjacent a l'ennemi (count>0)
et on lit la leaf native `ncEvaluate(1118)` a la position courante A DEUX INSTANTS :
  (A) AVANT toute attaque de Tan : 0 summon -> cap FAUX. free adjacents > 0 (open).
      -> modele CAP : count>0 & free>0 & !cap => PAS d'emission.
      -> modele free==0 : si free>0 => PAS d'emission NON PLUS (indistinct ici) ; on VERIFIE
         free>0 via aiMovableTiles/boardGraph pour lever l'ambiguite.
  (B) APRES avoir fait attaquer Tan >=5 fois sous Protector (>=maxSummons summons, morts inclus) :
      cap VRAI. -> modele CAP : count>0 & cap => EMISSION. C'est la preuve de causation.
On loggue, a chaque instant : leaf_emit, count(normal fromHere), free-adjacent (mirror), #summons ever.
Discipline runner : state-file unique absolu, dispose. Console ASCII.
"""
from __future__ import annotations

import json
import sys
from collections import deque
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
ROOT = Path(r"C:\Users\nicolasv\tacticus-tools")
sys.path.insert(0, str(PYDIR))

from rl_collect_batch import _resolve_session, _rpc  # noqa: E402

STATE = ROOT / "logs" / "runners" / "_solver38b_capAB_state.json"
TAN_VIS = "admecMarshall"
SUMMON_LIVE = "admecNpc1Vanguard"
ENEMY_VIS = "necroWarden"
BUILD = ["build", "--seed", "777", "--state-file", str(STATE),
         "--roster", "1", "--p-units", f"{TAN_VIS},admecRuststalker",
         "--a-units", f"{ENEMY_VIS},{ENEMY_VIS}", "--board", "MC1_67"]
PROTECTOR = 1247


def main() -> int:
    import subprocess
    proc = subprocess.run([sys.executable, "rl_duel.py", *BUILD], cwd=str(PYDIR),
                          capture_output=True, text=True, encoding="utf-8", errors="replace")
    if not STATE.exists():
        print("[capAB] build KO:", (proc.stderr or proc.stdout or "")[-300:])
        return 1
    rid = json.loads(STATE.read_text())["runnerId"]
    sid = _resolve_session()
    print(f"[capAB] runner={rid}")

    def _r(m, b, t=60):
        return _rpc(sid, m, [b], timeout=t).get("result") or {}

    def board_maps():
        bg = _r("boardGraph", {"runnerId": rid}, 60)
        neigh = {}
        walk = {}
        for t in (bg.get("tiles") or []):
            key = (t.get("col"), t.get("row"))
            walk[key] = bool(t.get("walkable"))
        # neighbours as coords
        idc = {t.get("id"): (t.get("col"), t.get("row")) for t in (bg.get("tiles") or [])}
        for t in (bg.get("tiles") or []):
            key = (t.get("col"), t.get("row"))
            neigh[key] = [idc[n] for n in (t.get("neighbours") or []) if n in idc]
        return neigh, walk

    neigh_by_pos, walkable = board_maps()

    def occ_live():
        ob = _r("observeBattle", {"runnerId": rid}, 60)
        return ob, {(u.get("col"), u.get("row")) for u in (ob.get("units") or [])
                    if not u.get("isDead") and u.get("col") is not None}

    def free_adj(pos, occ):
        from engine import battle_query as bq
        return bq.adjacent_addable_count(pos, neigh_by_pos, walkable, occ, None)

    def tan_now():
        dec = _r("decisionView", {"runnerId": rid, "allAbilities": True}, 150)
        tan = next((u for u in (dec.get("units") or []) if u.get("visualId") == TAN_VIS
                    and u.get("alive")), None)
        return dec, tan

    def advance_to_tan(max_iter=25):
        for _ in range(max_iter):
            dec, tan = tan_now()
            if tan is None:
                return None, None
            if dec.get("currentPlayer") == tan.get("owner"):
                return dec, tan
            _r("applyAction", {"runnerId": rid, "action": {"kind": "endturn"},
                               "captureEvents": False}, 60)
        return None, None

    def measure(label):
        dec, tan = tan_now()
        if tan is None:
            print(f"[{label}] Tan absent")
            return
        tid = tan["id"]
        pos = (tan.get("pos") or {})
        org = (pos.get("col"), pos.get("row"))
        ob, occ = occ_live()
        # normal attack fromHere
        na = next((a for a in (tan.get("abilities") or [])
                   if a.get("kind") == "normal" and a.get("id") is not None), None)
        fh = 0
        if na:
            at = _r("abilityTargets", {"runnerId": rid, "unitId": tid,
                                       "abilityId": na["id"]}, 60)
            for uu in (at.get("units") or []):
                if uu.get("unitId") != tid:
                    continue
                for a in (uu.get("abilities") or []):
                    if a.get("abilityId") == na["id"]:
                        fh = int(a.get("fromHereCount") or 0)
        summ = len({u.get("squadId") for u in (ob.get("units") or [])
                    if u.get("visualId") == SUMMON_LIVE})
        fa = free_adj(org, occ - {org})
        ncev = _r("ncEvaluate", {"runnerId": rid, "unitId": tid,
                                 "abilityType": 1118, "sweep": False}, 60)
        p0 = (ncev.get("positions") or [{}])[0]
        emit = bool(p0.get("action")) and p0.get("util") is not None
        effs = {e.get("effectType") for e in (tan.get("effects") or [])}
        print(f"[{label}] org={org} prot={PROTECTOR in effs} count(fh)={fh} "
              f"free_adj={fa} summons_ever={summ} -> leaf_emit={emit} util={p0.get('util')}")
        return tid, org, fh, fa, summ, emit

    # ---- instant A : 0 summon, drive Tan adjacent a un ennemi ----
    dec, tan = advance_to_tan()
    if tan is None:
        print("[capAB] Tan pas atteint")
        _r("disposeRunner", {"runnerId": rid}, 20)
        return 2
    # drive Tan vers un ennemi jusqu'a count>0 (sans attaquer)
    def bfs(start):
        seen = {start: 0}; q = deque([start])
        while q:
            x = q.popleft()
            for n in neigh_by_pos.get(x, []):
                if n not in seen:
                    seen[n] = seen[x] + 1; q.append(n)
        return seen
    for _ in range(8):
        dec, tan = advance_to_tan()
        if tan is None:
            break
        tid = tan["id"]
        na = next((a for a in (tan.get("abilities") or [])
                   if a.get("kind") == "normal" and a.get("id") is not None), None)
        fh = 0
        if na:
            at = _r("abilityTargets", {"runnerId": rid, "unitId": tid, "abilityId": na["id"]}, 60)
            for uu in (at.get("units") or []):
                if uu.get("unitId") == tid:
                    for a in (uu.get("abilities") or []):
                        if a.get("abilityId") == na["id"]:
                            fh = int(a.get("fromHereCount") or 0)
        if fh > 0:
            break
        # approcher un ennemi
        enemies = [u for u in (dec.get("units") or [])
                   if u.get("alive") and u.get("owner") != tan.get("owner")
                   and (u.get("pos") or {}).get("col") is not None]
        if not enemies:
            break
        et = (enemies[0]["pos"]["col"], enemies[0]["pos"]["row"])
        dgoal = bfs(et)
        mt = _r("aiMovableTiles", {"runnerId": rid, "side": "friendly"}, 60)
        cmt = next((x for x in (mt.get("units") or []) if x.get("unitId") == tid), None)
        reach = [(t["col"], t["row"]) for t in ((cmt or {}).get("tiles") or [])
                 if t.get("col") is not None]
        pool = [t for t in reach if t in dgoal]
        if not pool:
            _r("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 40)
            continue
        best = min(pool, key=lambda t: dgoal[t])
        _r("applyAction", {"runnerId": rid, "action": {"kind": "move", "unitId": tid,
                           "to": {"col": best[0], "row": best[1]}}}, 40)
    measure("A(0-summon)")

    # ---- driver : faire attaquer Tan sous Protector plusieurs fois pour generer >=5 summons ----
    def bfs2(start):
        seen = {start: 0}; q = deque([start])
        while q:
            x = q.popleft()
            for n in neigh_by_pos.get(x, []):
                if n not in seen:
                    seen[n] = seen[x] + 1; q.append(n)
        return seen
    for turn in range(14):
        dec, tan = advance_to_tan()
        if tan is None:
            break
        tid = tan["id"]
        effs = {e.get("effectType") for e in (tan.get("effects") or [])}
        # attaque normale si a portee (eval attackPlans)
        na = next((a for a in (tan.get("abilities") or [])
                   if a.get("kind") == "normal" and a.get("id") is not None), None)
        tgt = None
        for p in (dec.get("attackPlans") or []):
            if p.get("unitId") != tid:
                continue
            for ev in (p.get("evals") or []):
                if ev.get("targetId") is not None and (na is None or ev.get("abilityId") == na["id"]):
                    # a portee depuis la tuile courante ?
                    tgt = ev.get("targetId"); ab = ev.get("abilityId"); break
            if tgt:
                break
        # verifier portee reelle depuis tuile courante
        pos = (tan.get("pos") or {})
        org = (pos.get("col"), pos.get("row"))
        did_attack = False
        if tgt is not None:
            e = next((u for u in (dec.get("units") or []) if u.get("id") == tgt), None)
            ep = (e.get("pos") or {}) if e else {}
            etile = (ep.get("col"), ep.get("row"))
            dgoal = bfs2(etile)
            R = 1
            import gameconfig as GC
            ranges = [int(w.get("Range") or 0) for w in ((GC.unit(TAN_VIS) or {}).get("weapons") or [])]
            R = max([r for r in ranges if r > 0] + [1])
            if dgoal.get(org, 99) <= R:
                _r("applyAction", {"runnerId": rid, "action": {"kind": "ability",
                    "casterId": tid, "targetId": tgt, "abilityType": ab}, "captureEvents": False}, 120)
                did_attack = True
        if not did_attack:
            # approcher
            enemies = [u for u in (dec.get("units") or [])
                       if u.get("alive") and u.get("owner") != tan.get("owner")
                       and (u.get("pos") or {}).get("col") is not None]
            if enemies:
                et = (enemies[0]["pos"]["col"], enemies[0]["pos"]["row"])
                dgoal = bfs2(et)
                mt = _r("aiMovableTiles", {"runnerId": rid, "side": "friendly"}, 60)
                cmt = next((x for x in (mt.get("units") or []) if x.get("unitId") == tid), None)
                reach = [(t["col"], t["row"]) for t in ((cmt or {}).get("tiles") or [])
                         if t.get("col") is not None]
                pool = [t for t in reach if t in dgoal]
                if pool:
                    best = min(pool, key=lambda t: dgoal[t])
                    _r("applyAction", {"runnerId": rid, "action": {"kind": "move",
                        "unitId": tid, "to": {"col": best[0], "row": best[1]}}}, 40)
        _r("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 40)
        # check summons count
        ob, _o = occ_live()
        summ = len({u.get("squadId") for u in (ob.get("units") or [])
                    if u.get("visualId") == SUMMON_LIVE})
        if summ >= 5 and (PROTECTOR in effs):
            break

    # ---- instant B : cap atteint, re-lire a une position count>0 ----
    advance_to_tan()
    measure("B(cap)")

    _r("disposeRunner", {"runnerId": rid}, 20)
    try:
        STATE.unlink()
    except OSError:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
